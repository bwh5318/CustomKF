"""Guarded independent review and aggregation for the fixed-force extension campaign.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.dynamics_extension_review CAMPAIGN

For every satellite it mirrors Astra's dynamics_ceiling_review: guard status, NPZ and reference
hashes, the fixed 7/6 split and times, bitwise reintegration of the saved states, exact native
reference samples and rotations, independent train/held/all RMS, and an SVD least-squares
stationarity check. It also recomputes the observation-solution RMS on the same epochs. The
per-SV and pooled 31 x 13 observation values must equal the GUAM evaluation's scores. Results are
aggregated per SV and pooled. Writes only review.json. IGS-dependent diagnostic, not POD.
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
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/fixed_force_fit.py", "claude/tools/dynamics_ceiling_step.py", "claude/tools/evaluate_ablation.py")
TRAIN, HELD, ALL = np.arange(0, 13, 2), np.arange(1, 13, 2), np.arange(13)


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
    assert sha(GUAM / "validation.json") == manifest["baseline_manifest_sha256"]
    base = json.loads((GUAM / "validation.json").read_text())
    for name in (f"{base['final']}/solution.npz", "evaluation/evaluation.json", "prepare/fixture.json"):
        assert sha(GUAM / name) == base["artifacts_sha256"][name], name
    baseline = np.load(GUAM / base["final"] / "solution.npz")
    evaluation = json.loads((GUAM / "evaluation/evaluation.json").read_text())["GUAM"]
    context, _, _ = restore(GUAM / "prepare/fixture.json")
    reference = Reference()
    satellites = [str(s) for s in baseline["satellites"]]
    assert sorted(manifest["completed"]) == sorted(manifest["satellites"]) == sorted(satellites)
    per, squares = {}, {key: [] for key in ("fit_train", "fit_held", "fit_all", "obs_held", "obs_all")}
    for sat in manifest["satellites"]:
        name = manifest["completed"][sat]
        path = campaign / name
        report = json.loads((path / "diagnostic.json").read_text())
        assert manifest["runs"][name]["status"] == "ok"
        assert report["status"] == "reference_only_fixed_force_fit_complete_not_independent_POD" and report["satellite"] == sat
        assert sha(path / "diagnostic_fit.npz") == report["solution_sha256"] and reference.sha256 == report["reference_sha256"]
        if sat in manifest["reproduce"]:
            assert report["archived_reproduction"]["arrays"] == "bitwise equal"
        fit = np.load(path / "diagnostic_fit.npz")
        assert str(fit["satellite"]) == sat
        np.testing.assert_array_equal(fit["train_indices"], TRAIN)
        np.testing.assert_array_equal(fit["held_indices"], HELD)
        np.testing.assert_array_equal(fit["times_s"], 10. + ALL * 900.)
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
        for label, indices in (("train", TRAIN), ("held", HELD), ("all", ALL)):
            scores[label] = {"fit_m": rms(delta[indices]), "observation_m": rms(observed[indices])}
            np.testing.assert_allclose(scores[label]["fit_m"], report["fit"][label]["rms_3d_m"], rtol=0, atol=2e-8)
            np.testing.assert_allclose(scores[label]["observation_m"], report["observation_baseline"][label]["rms_3d_m"], rtol=0, atol=2e-8)
        # Same 13 native epochs the GUAM evaluator scored for this satellite.
        np.testing.assert_allclose(scores["all"]["observation_m"], evaluation["per_satellite"][sat]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
        scales = np.array([100.] * 3 + [.01] * 3)
        design = np.array([trajectory.partial(t)[:3] for t in fit["times_s"][TRAIN]]).reshape(-1, 6) * scales
        step, _, rank, singular = np.linalg.lstsq(design, -delta[TRAIN].ravel(), rcond=1e-11)
        correction = step * scales
        bound = float(np.linalg.norm(correction[:3]) + context["duration_s"] * np.linalg.norm(correction[3:]))
        assert rank == 6 and bound < 1e-4
        for key, values in (("fit_train", delta[TRAIN]), ("fit_held", delta[HELD]), ("fit_all", delta),
                            ("obs_held", observed[HELD]), ("obs_all", observed)):
            squares[key].extend(np.sum(values**2, axis=1).tolist())
        per[sat] = {"scores": scores, "iterations": len(report["history"]),
                    "accepted_updates": sum(h["update_applied"] for h in report["history"]),
                    "scaled_condition": report["history"][-1]["scaled_condition"], "svd_rank": int(rank),
                    "svd_condition": float(singular[0] / singular[-1]), "svd_step_bound_m": bound,
                    "heldout_below_10_cm": scores["held"]["fit_m"] < .1,
                    "reproduced_archive": sat in manifest["reproduce"], "reintegrated_states_bitwise_equal": True}
    pooled = {key: float(np.sqrt(np.mean(values))) for key, values in squares.items()}
    assert len(squares["obs_all"]) == 403
    np.testing.assert_allclose(pooled["obs_all"], evaluation["groups"]["all"]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
    held = {sat: v["scores"]["held"]["fit_m"] for sat, v in per.items()}
    result = {
        "status": "independent_fixed_force_extension_checks_pass_not_POD_accuracy_acceptance",
        "campaign_manifest_sha256": sha(campaign / "validation.json"), "satellites": per, "pooled_rms_m": pooled,
        "summary": {"satellites": len(per), "heldout_below_10_cm": sum(v["heldout_below_10_cm"] for v in per.values()),
                    "worst_held_fit": max(held.items(), key=lambda item: item[1]),
                    "best_held_fit": min(held.items(), key=lambda item: item[1]),
                    "median_held_fit_m": float(np.median(list(held.values()))),
                    "scaled_condition_range": [min(v["scaled_condition"] for v in per.values()), max(v["scaled_condition"] for v in per.values())],
                    "iterations": sorted({v["iterations"] for v in per.values()})},
        "review_source_sha256": sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"pooled_rms_m": pooled, "summary": result["summary"],
                      "per_satellite_held_fit_vs_observation_m": {sat: [round(v["scores"]["held"]["fit_m"], 6), round(v["scores"]["held"]["observation_m"], 6)]
                                                                  for sat, v in per.items()}}, indent=1), flush=True)


if __name__ == "__main__":
    main()
