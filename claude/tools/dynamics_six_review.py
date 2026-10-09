"""Guarded independent review and aggregation for the six-hour fixed-force reference campaign.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 240 -- claude.tools.dynamics_six_review CAMPAIGN

Mirrors claude/tools/dynamics_extension_review.py at the longer arc: guard status, NPZ and
reference hashes, the 13/12 native split and times, bitwise reintegration of the saved states,
exact native reference samples and rotations, independent per-group RMS, and an SVD least-squares
stationarity check. The observation-solution RMS recomputed here must equal Astra's arc evaluation,
per satellite over all 25 native samples and over the common first-three-hour 13, and pooled over
775 and 403 samples. The three-hour reproductions are checked separately for bitwise agreement with
the archived campaign. Writes only review.json. IGS-dependent diagnostic, not POD accuracy.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.stage5b_step import restore
from customkf.stage5_pilot import ORIGIN
from customkf.dynamic_observation import Trajectory
from claude.tools.evaluate_ablation import Reference
from claude.tools.dynamics_six_step import ARC, CASES, HELPERS
from claude.tools.pinned_sources import DYNAMICS, ROOT, sha, verify

SCALES = np.array([100.] * 3 + [.01] * 3)


def rms(delta):
    return float(np.sqrt(np.sum(delta**2) / len(delta)))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    campaign = parser.parse_args().campaign.resolve()
    manifest = json.loads((campaign / "validation.json").read_text())
    assert verify(HELPERS) == manifest["source_policy"]
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    assert sha(ARC / "validation.json") == manifest["arc_manifest_sha256"]
    arc = json.loads((ARC / "validation.json").read_text())
    for name in ("six-1/solution.npz", "six-prepare/fixture.json", "evaluation/evaluation.json"):
        assert sha(ARC / name) == arc["artifacts_sha256"][name], name

    baseline = np.load(ARC / "six-1/solution.npz")
    evaluation = json.loads((ARC / "evaluation/evaluation.json").read_text())
    assert evaluation["status"] == "arc_experiment_evaluated_not_accuracy_acceptance"
    full, common = evaluation["full"]["six"], evaluation["common"]["six"]
    assert full["solution_sha256"] == sha(ARC / "six-1/solution.npz") == common["solution_sha256"]
    context, _, _ = restore(ARC / "six-prepare/fixture.json")
    reference = Reference()
    satellites = [str(s) for s in baseline["satellites"]]
    assert sorted(manifest["completed"]) == sorted(manifest["satellites"]) == sorted(satellites)

    native = CASES["six"]["native"]
    train, held, whole = np.arange(0, native, 2), np.arange(1, native, 2), np.arange(native)
    first = np.arange(CASES["three"]["native"])
    groups = {"train": train, "held": held, "all": whole, "first_three_hours": first}
    per, squares = {}, {key: [] for key in ("fit_train", "fit_held", "fit_all", "fit_first",
                                            "obs_held", "obs_all", "obs_first")}
    for sat in manifest["satellites"]:
        name = manifest["completed"][sat]
        path = campaign / name
        report = json.loads((path / "diagnostic.json").read_text())
        assert manifest["runs"][name]["status"] == "ok"
        assert report["status"] == "reference_only_fixed_force_fit_complete_not_independent_POD"
        assert report["satellite"] == sat and report["case"] == "six"
        assert report["parameter_count"] == 6 and not report["orbit_priors"]
        assert report["force_coefficients_mps2"] == [-1e-7, 0., 0., 0., 0.]
        assert not report["held_out_positions_used_in_fit"]
        assert sha(path / "diagnostic_fit.npz") == report["solution_sha256"] and reference.sha256 == report["reference_sha256"]
        fit = np.load(path / "diagnostic_fit.npz")
        assert str(fit["satellite"]) == sat
        np.testing.assert_array_equal(fit["train_indices"], train)
        np.testing.assert_array_equal(fit["held_indices"], held)
        np.testing.assert_array_equal(fit["times_s"], 10. + whole * 900.)
        trajectory = Trajectory(fit["initial_state"], context["model"], context["duration_s"])
        np.testing.assert_array_equal(np.array([trajectory.state(t) for t in fit["times_s"]]), fit["states"])
        np.testing.assert_array_equal(fit["baseline_states"], baseline["states"][satellites.index(sat), ::3])
        for i, t in enumerate(fit["times_s"]):
            raw = reference.raw.samples[(ORIGIN + int(round(float(t) * 1e9)), sat)]
            assert raw.xyz_m is not None and not raw.maneuver and not raw.orbit_predicted
            np.testing.assert_array_equal(fit["reference_ecef_m"][i], raw.xyz_m)
            rotation = reference.epoch.celestial_to_terrestrial(float(t))
            np.testing.assert_array_equal(fit["rotations"][i], rotation)
            np.testing.assert_allclose(fit["reference_inertial_m"][i], rotation.T @ raw.xyz_m, rtol=0, atol=1e-8)
        delta = fit["states"][:, :3] - fit["reference_inertial_m"]
        observed = fit["baseline_states"][:, :3] - fit["reference_inertial_m"]
        scores = {}
        for label, indices in groups.items():
            scores[label] = {"fit_m": rms(delta[indices]), "observation_m": rms(observed[indices])}
            np.testing.assert_allclose(scores[label]["fit_m"], report["fit"][label]["rms_3d_m"], rtol=0, atol=2e-8)
            np.testing.assert_allclose(scores[label]["observation_m"], report["observation_baseline"][label]["rms_3d_m"], rtol=0, atol=2e-8)
        # The station-fit control must equal Astra's own evaluation on both sample sets.
        np.testing.assert_allclose(scores["all"]["observation_m"], full["per_satellite"][sat]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
        np.testing.assert_allclose(scores["first_three_hours"]["observation_m"], common["per_satellite"][sat]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
        design = np.array([trajectory.partial(t)[:3] for t in fit["times_s"][train]]).reshape(-1, 6) * SCALES
        step, _, rank, singular = np.linalg.lstsq(design, -delta[train].ravel(), rcond=1e-11)
        correction = step * SCALES
        bound = float(np.linalg.norm(correction[:3]) + context["duration_s"] * np.linalg.norm(correction[3:]))
        assert rank == 6 and bound < 1e-4, (sat, rank, bound)
        for key, values in (("fit_train", delta[train]), ("fit_held", delta[held]), ("fit_all", delta),
                            ("fit_first", delta[first]), ("obs_held", observed[held]),
                            ("obs_all", observed), ("obs_first", observed[first])):
            squares[key].extend(np.sum(values**2, axis=1).tolist())
        per[sat] = {"scores": scores, "iterations": len(report["history"]),
                    "accepted_updates": sum(h["update_applied"] for h in report["history"]),
                    "scaled_condition": report["history"][-1]["scaled_condition"], "svd_rank": int(rank),
                    "svd_condition": float(singular[0] / singular[-1]), "svd_step_bound_m": bound,
                    "heldout_below_10_cm": scores["held"]["fit_m"] < .1,
                    "formal_position_sigma_m": full["per_satellite"][sat]["formal_position_sigma_m"],
                    "class": full["per_satellite"][sat]["class"], "reintegrated_states_bitwise_equal": True}

    pooled = {key: float(np.sqrt(np.mean(values))) for key, values in squares.items()}
    assert len(squares["obs_all"]) == 775 and len(squares["obs_first"]) == 403
    assert len(squares["fit_train"]) == 403 and len(squares["fit_held"]) == 372
    np.testing.assert_allclose(pooled["obs_all"], full["groups"]["all"]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
    np.testing.assert_allclose(pooled["obs_first"], common["groups"]["all"]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)

    # The three-hour reproductions are a separate adaptation check, not part of the six-hour scores.
    archived = json.loads((DYNAMICS / "validation.json").read_text())
    reproductions = {}
    for sat, name in manifest["reproduced"].items():
        report = json.loads((campaign / name / "diagnostic.json").read_text())
        assert report["case"] == "three" and report["archived_reproduction"]["arrays"] == "bitwise equal"
        assert report["archived_reproduction"]["shared_diagnostic_fields"] == "equal"
        assert sha(DYNAMICS / sat / "diagnostic.json") == archived["artifacts_sha256"][f"{sat}/diagnostic.json"]
        old = json.loads((DYNAMICS / sat / "diagnostic.json").read_text())
        assert report["fit"]["held"] == old["fit"]["held"]
        reproductions[sat] = {"held_fit_m": report["fit"]["held"]["rms_3d_m"], "bitwise_equal_to_archive": True}

    held_fit = {sat: v["scores"]["held"]["fit_m"] for sat, v in per.items()}
    ratio = {sat: v["scores"]["held"]["fit_m"] / v["scores"]["held"]["observation_m"] for sat, v in per.items()}
    result = {
        "status": "independent_six_hour_fixed_force_checks_pass_not_POD_accuracy_acceptance",
        "campaign_manifest_sha256": sha(campaign / "validation.json"),
        "arc_manifest_sha256": sha(ARC / "validation.json"), "satellites": per, "pooled_rms_m": pooled,
        "three_hour_reproductions": reproductions,
        "summary": {"satellites": len(per), "heldout_below_10_cm": sum(v["heldout_below_10_cm"] for v in per.values()),
                    "worst_held_fit": max(held_fit.items(), key=lambda item: item[1]),
                    "best_held_fit": min(held_fit.items(), key=lambda item: item[1]),
                    "median_held_fit_m": float(np.median(list(held_fit.values()))),
                    "pooled_held_fit_m": pooled["fit_held"], "pooled_held_observation_m": pooled["obs_held"],
                    "held_fit_fraction_of_observation": pooled["fit_held"] / pooled["obs_held"],
                    "median_per_satellite_ratio": float(np.median(list(ratio.values()))),
                    "scaled_condition_range": [min(v["scaled_condition"] for v in per.values()),
                                               max(v["scaled_condition"] for v in per.values())],
                    "iterations": sorted({v["iterations"] for v in per.values()})},
        "review_source_sha256": sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"pooled_rms_m": pooled, "summary": result["summary"],
                      "three_hour_reproductions": reproductions,
                      "per_satellite_held_fit_vs_observation_m": {
                          sat: [round(v["scores"]["held"]["fit_m"], 6), round(v["scores"]["held"]["observation_m"], 6)]
                          for sat, v in per.items()}}, indent=1), flush=True)


if __name__ == "__main__":
    main()
