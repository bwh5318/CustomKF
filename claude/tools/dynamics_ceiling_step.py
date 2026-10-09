"""Guarded fixed-force fit to native IGS positions with a frozen temporal holdout.

Seven half-hour positions train; six interleaved quarter-hours validate. These
are IGS-dependent diagnostics and must never initialize station-based POD.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5b_step import restore
from customkf.stage5_pilot import ORIGIN
from customkf.dynamic_observation import Trajectory, SETTINGS
from claude.tools.evaluate_ablation import Reference
from claude.tools.fixed_force_fit import solve_fixed

BASE = ROOT / "validation/guam/20260911T155927Z"
TRAIN = np.arange(0, 13, 2)
HELD = np.arange(1, 13, 2)


def stats(delta):
    distances = np.linalg.norm(delta, axis=1)
    return {"samples": len(distances), "rms_3d_m": float(np.sqrt(np.mean(distances**2))),
            "max_3d_m": float(distances.max())}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--satellite", required=True)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    baseline_manifest = json.loads((BASE / "validation.json").read_text())
    for name, digest in baseline_manifest["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    fixture = BASE / "prepare/fixture.json"
    baseline_path = BASE / baseline_manifest["final"] / "solution.npz"
    for path in (fixture, baseline_path):
        assert sha(path) == baseline_manifest["artifacts_sha256"][path.relative_to(BASE).as_posix()]
    context, _, seeds = restore(fixture)
    sat = args.satellite
    assert sat in seeds and context["epoch_count"] == 37
    baseline = np.load(baseline_path)
    si = list(baseline["satellites"]).index(sat)
    ix = list(baseline["names"]).index(f"orbit:{sat}:0")
    observation_state = seeds[sat] + baseline["x"][ix:ix + 6]
    model, duration = context["model"], context["duration_s"]
    reproduced = Trajectory(observation_state, model, duration)
    original_grid = baseline["times_s"]
    np.testing.assert_array_equal(np.array([reproduced.state(t) for t in original_grid]), baseline["states"][si])
    times = original_grid[::3]
    assert len(times) == 13
    reference = Reference()
    ecef, rotations = [], []
    for t in times:
        sample = reference.raw.samples[(ORIGIN + int(round(float(t) * 1e9)), sat)]
        assert sample.xyz_m is not None and not sample.maneuver and not sample.orbit_predicted
        ecef.append(sample.xyz_m)
        rotations.append(reference.epoch.celestial_to_terrestrial(float(t)))
    ecef, rotations = np.array(ecef), np.array(rotations)
    positions = np.einsum("tji,tj->ti", rotations, ecef)
    if args.validate:
        # Same-model synthetic closure, starting from broadcast, independent of IGS positions.
        truth = observation_state + np.array([25., -15., 10., .005, -.003, .002])
        truth_trajectory = Trajectory(truth, model, duration)
        synthetic = np.array([truth_trajectory.state(t)[:3] for t in times])
        estimate, fitted, history = solve_fixed(seeds[sat], times[TRAIN], synthetic[TRAIN], model, duration)
        delta = np.array([fitted.state(t)[:3] for t in times]) - synthetic
        assert np.linalg.norm(delta, axis=1).max() < 1e-4
        # Finite differences of all six trajectory columns at training and held epochs.
        max_error = 0.
        for k in range(6):
            h = 1. if k < 3 else .001
            d = np.eye(6)[k] * h
            plus, minus = Trajectory(truth + d, model, duration), Trajectory(truth - d, model, duration)
            for t in times:
                finite = (plus.state(t)[:3] - minus.state(t)[:3]) / (2 * h)
                analytic = truth_trajectory.partial(t)[:3, k]
                # Test discrepancy in metres for a 1m or 1mm/s perturbation.
                error = float(np.max(abs((finite - analytic) * h)))
                max_error = max(max_error, error)
                assert error < 1e-4
        result = {"status": "fixed_force_synthetic_and_partial_checks_pass", "satellite": sat,
                  "synthetic_all": stats(delta), "synthetic_held": stats(delta[HELD]),
                  "finite_difference_max_position_discrepancy_m": max_error, "finite_difference_entries": 6 * 13 * 3,
                  "history": history, "production_trajectory_reproduced_bitwise": True}
    else:
        estimate, fitted, history = solve_fixed(seeds[sat], times[TRAIN], positions[TRAIN], model, duration)
        states = np.array([fitted.state(t) for t in times])
        inertial_delta = states[:, :3] - positions
        cartesian_delta = np.einsum("tij,tj->ti", rotations, states[:, :3]) - ecef
        np.testing.assert_allclose(np.linalg.norm(cartesian_delta, axis=1), np.linalg.norm(inertial_delta, axis=1), rtol=0, atol=2e-8)
        baseline_delta = baseline["states"][si, ::3, :3] - positions
        result = {"status": "reference_only_fixed_force_fit_complete_not_independent_POD", "satellite": sat,
                  "fit": {"train": stats(cartesian_delta[TRAIN]), "held": stats(cartesian_delta[HELD]), "all": stats(cartesian_delta)},
                  "observation_baseline": {"train": stats(baseline_delta[TRAIN]), "held": stats(baseline_delta[HELD]), "all": stats(baseline_delta)},
                  "initial_state_correction_from_broadcast": (estimate - seeds[sat]).tolist(),
                  "history": history, "production_trajectory_reproduced_bitwise": True,
                  "heldout_below_10_cm": stats(cartesian_delta[HELD])["rms_3d_m"] < .1}
        np.savez_compressed(output / "diagnostic_fit.npz", initial_state=estimate, states=states, times_s=times,
                            reference_ecef_m=ecef, rotations=rotations, reference_inertial_m=positions,
                            train_indices=TRAIN, held_indices=HELD, baseline_states=baseline["states"][si, ::3], satellite=np.array(sat))
        result["solution_sha256"] = sha(output / "diagnostic_fit.npz")
    result.update(train_indices=TRAIN.tolist(), held_indices=HELD.tolist(), times_s=times.tolist(),
                  force_coefficients_mps2=[-1e-7, 0., 0., 0., 0.], parameter_count=6, orbit_priors=False,
                  reference_sha256=reference.sha256, baseline_sha256=sha(baseline_path), fixture_sha256=sha(fixture),
                  helper_sources_sha256={f"claude/tools/{n}.py": sha(ROOT / f"claude/tools/{n}.py") for n in ("fixed_force_fit", "dynamics_ceiling_step")})
    (output / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
