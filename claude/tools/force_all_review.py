"""Independent review and all-satellite aggregation of the frozen force-parameter protocol.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 300 -- claude.tools.force_all_review CAMPAIGN

Astra's claude/tools/force_parameter_review.py checks each case and is capped at 120 s, which was
sized for the three-satellite pilot. This worker repeats those per-case checks independently for
every completed case and adds what a per-case pass cannot give: pooled all-31 aggregation against
the fixed-force floor from claude/runs/20260912T025241Z-dynamics-six and against the six-hour
station fit, and the behaviour of each variant inside the high- and low-ratio groups of
claude/DYNAMICS_SIX_HOUR.md. Those groups are exploratory priorities, not causal labels, per root
FORCE_PARAMETER_PROTOCOL.md.

Reference-only throughout. No reference state or coefficient may seed station POD, a >=50%
withheld reduction flags representation improvement only, and nothing here authorizes adding
parameters to the estimator.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.stage5b_step import restore
from claude.tools.dynamics_six_step import ARC, locate, reference_positions
from claude.tools.force_parameter_fit import ForceTrajectory, VARIANTS, design_at
from claude.tools.pinned_sources import ROOT, sha, verify

SIX = ROOT / "claude/runs/20260912T025241Z-dynamics-six"
# Exploratory priority groups from claude/DYNAMICS_SIX_HOUR.md: fixed-force floor over station error.
HIGH_RATIO = ("G01", "G04", "G06", "G09", "G10", "G11", "G14", "G18", "G20", "G21", "G24", "G25", "G28", "G32")
LOW_RATIO = ("G05", "G07", "G15", "G16", "G17", "G19", "G22", "G26", "G29", "G31")


def pooled(squares):
    return float(np.sqrt(np.mean(squares))) if len(squares) else None


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    campaign = parser.parse_args().campaign.resolve()
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    policy = verify()
    manifest = json.loads((campaign / "validation.json").read_text())
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    assert manifest["source_six_manifest_sha256"] == sha(SIX / "validation.json")
    assert sha(ROOT / "FORCE_PARAMETER_PROTOCOL.md") == manifest["source_sha256"]["FORCE_PARAMETER_PROTOCOL.md"]

    _, fixture, orbit_path, arc = locate("six")
    context, _, seeds = restore(fixture)
    model, duration = context["model"], context["duration_s"]
    assert tuple(model.parameter_names) == ("D0", "Y0", "B0", "Bc1", "Bs1")
    times = 10. + np.arange(25) * 900.
    train, held, whole = np.arange(0, 25, 2), np.arange(1, 25, 2), np.arange(25)
    first = np.arange(13)
    groups = {"train": train, "held": held, "all": whole, "first_three_hours": first}

    # The fixed-force floor and the station fit, both taken from the archives, not recomputed here.
    six = json.loads((SIX / "validation.json").read_text())
    floor, station = {}, {}
    baseline = np.load(orbit_path)
    satellites = [str(s) for s in baseline["satellites"]]
    for sat, name in six["completed"].items():
        report = json.loads((SIX / name / "diagnostic.json").read_text())
        assert sha(SIX / name / "diagnostic_fit.npz") == report["solution_sha256"]
        floor[sat] = {label: report["fit"][label]["rms_3d_m"] for label in groups}
        station[sat] = {label: report["observation_baseline"][label]["rms_3d_m"] for label in groups}

    per, squares, case_squares, failures = {}, {}, {}, []
    # The controller records only the two frozen variants in "completed"; the fixed controls are the
    # bitwise link back to the six-hour archive, so review them too.
    cases = list(manifest["completed"]) + sorted(name for name, run in manifest["runs"].items()
                                                 if name.startswith("fixed-") and run["status"] == "ok")
    for name in cases:
        folder = campaign / name
        report = json.loads((folder / "fit.json").read_text())
        fit = np.load(folder / "fit.npz")
        assert sha(folder / "fit.npz") == report["solution_sha256"], name
        assert manifest["runs"][name]["status"] == "ok", name
        assert report["status"] == "reference_force_parameter_fit_complete_not_POD"
        sat, variant = str(fit["satellite"]), report["variant"]
        assert sat == report["satellite"] and variant in VARIANTS
        active = list(VARIANTS[variant])
        np.testing.assert_array_equal(fit["active"], active)
        np.testing.assert_array_equal(fit["times_s"], times)
        np.testing.assert_array_equal(fit["train_indices"], train)
        np.testing.assert_array_equal(fit["held_indices"], held)
        assert not report["held_positions_used_in_fit"] and not report["priors"]
        assert report["estimated_parameters"] == 6 + len(active)
        assert report["parameter_names"] == [model.parameter_names[i] for i in active]

        reference, ecef, rotations = reference_positions(times, sat)
        assert reference.sha256 == report["reference_sha256"]
        np.testing.assert_array_equal(ecef, fit["reference_ecef_m"])
        np.testing.assert_array_equal(rotations, fit["rotations"])
        trajectory = ForceTrajectory(fit["initial_state"], model, duration, fit["parameters"])
        states = np.array([trajectory.state(t) for t in times])
        np.testing.assert_array_equal(states, fit["states"])
        delta = np.einsum("tij,tj->ti", rotations, states[:, :3]) - ecef
        scores = {}
        for label, index in groups.items():
            scores[label] = float(np.sqrt(np.mean(np.sum(delta[index]**2, axis=1))))
            np.testing.assert_allclose(scores[label], report["fit"][label]["rms_3d_m"], rtol=0, atol=2e-8)

        # Independent rank, conditioning, stationarity and unit-weight covariance at the solution.
        scales = np.r_[[100.] * 3, [.01] * 3, np.asarray(model.parameter_scales)[active]]
        design = design_at(trajectory, times[train], active) * scales
        target = (np.einsum("tji,tj->ti", rotations, ecef) - states[:, :3])[train].ravel()
        u, s, vt = np.linalg.svd(design, full_matrices=False)
        rank = int(np.sum(s > s[0] * 1e-11))
        assert rank == len(scales), (name, rank)
        correction = (vt.T @ ((u.T @ target) / s)) * scales
        bound = float(np.linalg.norm(correction[:3]) + duration * np.linalg.norm(correction[3:6]))
        assert bound < 1e-4, (name, bound)
        covariance = (vt.T / s**2) @ vt * scales[:, None] * scales[None, :]
        std = np.sqrt(np.diag(covariance))
        np.testing.assert_allclose(fit["covariance_unit_position_weight"] / std[:, None] / std[None, :],
                                   covariance / std[:, None] / std[None, :], rtol=0, atol=1e-7)
        correlation = covariance / std[:, None] / std[None, :]
        coupling = float(np.max(np.abs(correlation[:6, 6:]))) if active else None
        if coupling is not None:
            np.testing.assert_allclose(coupling, report["max_abs_state_force_correlation"], rtol=0, atol=1e-7)
        assert report["history"][-1]["termination"] == "stationary", name

        # Fixed controls must reproduce the archived six-hour diagnostic exactly, checked here
        # independently of the assertion inside Astra's step worker.
        control = None
        if variant == "fixed":
            archived = np.load(SIX / six["completed"][sat] / "diagnostic_fit.npz")
            np.testing.assert_array_equal(fit["initial_state"], archived["initial_state"])
            np.testing.assert_array_equal(fit["states"], archived["states"])
            np.testing.assert_array_equal(fit["parameters"], np.array([-1e-7, 0., 0., 0., 0.]))
            control = "bitwise equal to claude/runs/20260912T025241Z-dynamics-six"

        reduction = 1. - scores["held"] / floor[sat]["held"]
        flags = {"condition_over_1e8": bool(s[0] / s[-1] > 1e8),
                 "coefficient_abs_over_1e_minus6_mps2": bool(np.any(np.abs(fit["parameters"]) > 1e-6)),
                 "held_regression_over_1_cm": bool(scores["held"] - floor[sat]["held"] > .01),
                 "held_reduction_at_least_half": bool(scores["held"] <= .5 * floor[sat]["held"]),
                 "state_force_coupling_over_0_9": bool(coupling is not None and coupling > .9)}
        per[name] = {"satellite": sat, "variant": variant, "scores": scores,
                     "fixed_force_floor": floor[sat], "station_fit": station[sat],
                     "held_reduction_fraction": reduction, "rank": rank,
                     "scaled_condition": float(s[0] / s[-1]), "svd_stationarity_bound_m": bound,
                     "max_abs_state_force_correlation": coupling,
                     "coefficients_mps2": fit["parameters"].tolist(),
                     "unit_weight_parameter_std": std[6:].tolist(),
                     "group": "high_ratio" if sat in HIGH_RATIO else "low_ratio" if sat in LOW_RATIO else "middle",
                     "iterations": len(report["history"]), "fixed_control": control, "flags": flags}
        case_squares[name] = np.sum(delta[held]**2, axis=1).tolist()
        if variant != "fixed":
            squares.setdefault(variant, []).extend(case_squares[name])
        if any(v for k, v in flags.items() if k != "held_reduction_at_least_half"):
            failures.append({"case": name, "flags": {k: v for k, v in flags.items() if v}})

    # Aggregate only over satellites that completed both variants, so the comparison is balanced.
    complete = sorted({v["satellite"] for v in per.values() if v["variant"] == "d0"}
                      & {v["satellite"] for v in per.values() if v["variant"] == "ecom5"})
    floor_squares, station_squares, floor_held_squares = [], [], {}
    for sat in complete:
        archived = np.load(SIX / six["completed"][sat] / "diagnostic_fit.npz")
        d = np.einsum("tij,tj->ti", archived["rotations"], archived["states"][:, :3]) - archived["reference_ecef_m"]
        o = np.einsum("tij,tj->ti", archived["rotations"], archived["baseline_states"][:, :3]) - archived["reference_ecef_m"]
        floor_held_squares[sat] = np.sum(d[held]**2, axis=1).tolist()
        floor_squares.extend(floor_held_squares[sat])
        station_squares.extend(np.sum(o[held]**2, axis=1).tolist())
        # The archived per-satellite scores must reproduce from the archived arrays.
        np.testing.assert_allclose(pooled(floor_held_squares[sat]), floor[sat]["held"], rtol=0, atol=2e-8)
    summary = {"satellites_with_both_variants": len(complete), "cases_reviewed": len(per),
               "pooled_held_rms_m": {"fixed_force_floor": pooled(floor_squares),
                                     "station_fit": pooled(station_squares),
                                     **{variant: pooled(values) for variant, values in sorted(squares.items())}}}
    for variant in ("d0", "ecom5"):
        rows = {v["satellite"]: v for v in per.values() if v["variant"] == variant and v["satellite"] in complete}
        if not rows:
            continue
        reductions = {sat: v["held_reduction_fraction"] for sat, v in rows.items()}
        by_group = {}
        for group in ("high_ratio", "low_ratio", "middle"):
            members = [sat for sat, v in rows.items() if v["group"] == group]
            if not members:
                continue
            by_group[group] = {
                "satellites": len(members),
                "median_held_reduction_fraction": float(np.median([reductions[sat] for sat in members])),
                "pooled_held_rms_m": pooled([q for sat in members for q in case_squares[f"{variant}-{sat}"]]),
                "pooled_fixed_force_floor_m": pooled([q for sat in members for q in floor_held_squares[sat]]),
                "median_state_force_coupling": float(np.median([rows[sat]["max_abs_state_force_correlation"]
                                                                for sat in members]))}
        summary[variant] = {
            "pooled_held_rms_m": summary["pooled_held_rms_m"][variant],
            "median_held_reduction_fraction": float(np.median(list(reductions.values()))),
            "satellites_at_least_half_reduction": sum(v["flags"]["held_reduction_at_least_half"] for v in rows.values()),
            "satellites_with_held_regression_over_1_cm": sum(v["flags"]["held_regression_over_1_cm"] for v in rows.values()),
            "worst_held_rms": max(((sat, v["scores"]["held"]) for sat, v in rows.items()), key=lambda item: item[1]),
            "best_held_rms": min(((sat, v["scores"]["held"]) for sat, v in rows.items()), key=lambda item: item[1]),
            "max_abs_coefficient_mps2": max(max(abs(c) for c in v["coefficients_mps2"]) for v in rows.values()),
            "state_force_coupling_range": [min(v["max_abs_state_force_correlation"] for v in rows.values()),
                                           max(v["max_abs_state_force_correlation"] for v in rows.values())],
            "scaled_condition_range": [min(v["scaled_condition"] for v in rows.values()),
                                       max(v["scaled_condition"] for v in rows.values())],
            "by_priority_group": by_group}

    result = {"status": "independent_force_parameter_all_satellite_review_pass_not_POD",
              "scope": manifest.get("scope"), "campaign": campaign.relative_to(ROOT).as_posix(),
              "campaign_manifest_sha256": sha(campaign / "validation.json"),
              "six_manifest_sha256": sha(SIX / "validation.json"),
              "arc_manifest_sha256": sha(ARC / "validation.json"),
              "protocol_sha256": sha(ROOT / "FORCE_PARAMETER_PROTOCOL.md"),
              "source_policy": policy, "summary": summary, "flagged_cases": failures, "cases": per,
              "caveats": ["Reference-only IGS-dependent diagnostic; no state or coefficient may seed station POD.",
                          "A >=50% withheld reduction flags representation improvement only.",
                          "Priority groups are exploratory, not causal attributions.",
                          "Withheld epochs informed the research direction and are not fresh model-selection evidence.",
                          "One day and one arc; generalization needs another."],
              "review_source_sha256": sha(Path(__file__))}
    (output / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("cases", "source_policy")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
