"""Guarded fixed-force reference fit for one satellite on either arc length (three or six hours).

    C:\\anaconda\\python.exe -m customkf.guard --timeout 300 -- claude.tools.dynamics_six_step --case six --satellite G23

Astra's completed arc-length experiment showed a six-hour ten-minute fit scoring 0.5437 m on the
common first three hours. This worker asks how much of that 0.55 m the fixed-force representation
itself can explain at six hours: it fits six initial-state parameters only to native IGS positions
with unchanged force coefficients, then reports withheld error.

claude/tools/dynamics_extension_step.py is hard-coded to three hours (its BASE, TRAIN, HELD and
13-sample assertion). This module takes the case as an argument and reads every dimension from the
selected fixture, reusing claude/tools/fixed_force_fit.solve_fixed unchanged. --case three
reproduces the original diagnostic and, with --compare-archive, requires bitwise agreement with
claude/runs/20260911T211901Z-dynamics-ceiling.

These are IGS-dependent reference diagnostics. They are never an input to station-based POD, and a
0.1 m withheld flag stays diagnostic; it is not an accuracy acceptance.
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
from claude.tools.fixed_force_fit import solve_fixed
from claude.tools.dynamics_ceiling_step import stats
from claude.tools.pinned_sources import DYNAMICS, GUAM, ROOT, sha, verify

ARC = ROOT / "claude/runs/20260912T021739Z-arc"
HELPERS = ("claude/tools/fixed_force_fit.py", "claude/tools/dynamics_ceiling_step.py", "claude/tools/evaluate_ablation.py")
OWN = ("claude/tools/dynamics_six_step.py", "claude/tools/pinned_sources.py")
# Native IGS spacing; the saved output grids are denser than the solve cadence in both cases.
NATIVE_S = 900.0
CASES = {
    "three": {"campaign": GUAM, "fixture": "prepare/fixture.json", "solution": None,
              "duration_s": 10820.0, "step_s": 300, "grid": 37, "native": 13},
    "six": {"campaign": ARC, "fixture": "six-prepare/fixture.json", "solution": "six-1/solution.npz",
            "duration_s": 21620.0, "step_s": 600, "grid": 73, "native": 25},
}


def locate(case):
    """Hash-verify the selected campaign and return its fixture, comparison orbit and manifest."""
    spec = CASES[case]
    campaign = spec["campaign"]
    manifest = json.loads((campaign / "validation.json").read_text())
    if case == "three":
        solution = manifest["final"] + "/solution.npz"
    else:
        assert manifest["status"] == "arc_experiment_complete_not_accuracy_acceptance", manifest["status"]
        assert manifest["active_worker"] is None
        assert manifest["cases"]["six"]["final"] == "six-1"
        solution = spec["solution"]
        # The arc campaign re-pinned the tree; require the pins it recorded, not only the GUAM ones.
        for name, digest in manifest["source_sha256"].items():
            assert sha(ROOT / name) == digest, name
    fixture = campaign / spec["fixture"]
    orbit = campaign / solution
    for path in (fixture, orbit):
        assert sha(path) == manifest["artifacts_sha256"][path.relative_to(campaign).as_posix()], str(path)
    return spec, fixture, orbit, manifest


def reference_positions(times, sat):
    """Native IGS ECEF samples and their celestial-to-terrestrial rotations, validity checked."""
    reference = Reference()
    ecef, rotations = [], []
    for t in times:
        sample = reference.raw.samples[(ORIGIN + int(round(float(t) * 1e9)), sat)]
        assert sample.xyz_m is not None and not sample.maneuver and not sample.orbit_predicted
        ecef.append(sample.xyz_m)
        rotations.append(reference.epoch.celestial_to_terrestrial(float(t)))
    return reference, np.array(ecef), np.array(rotations)


def compare_with_archive(sat, result, output):
    """Bitwise agreement with Astra's archived three-hour diagnostic, ignoring hash-only fields."""
    manifest = json.loads((DYNAMICS / "validation.json").read_text())
    for name in ("diagnostic.json", "diagnostic_fit.npz"):
        assert sha(DYNAMICS / sat / name) == manifest["artifacts_sha256"][f"{sat}/{name}"], name
    archived = json.loads((DYNAMICS / sat / "diagnostic.json").read_text())
    old, new = np.load(DYNAMICS / sat / "diagnostic_fit.npz"), np.load(output / "diagnostic_fit.npz")
    for key in old.files:
        np.testing.assert_array_equal(new[key], old[key], err_msg=key)
    current = json.loads(json.dumps(result))
    # This module adds groupings and its own provenance, so every archived field must agree, and the
    # per-group statistics are compared group by group rather than as whole dictionaries.
    ignored = {"solution_sha256", "helper_sources_sha256"}
    nested = ("fit", "observation_baseline")
    differing = sorted(k for k in set(archived) - ignored - set(nested) if current.get(k) != archived[k])
    differing += sorted(f"{outer}.{inner}" for outer in nested for inner, value in archived[outer].items()
                        if current[outer].get(inner) != value)
    assert not differing, differing
    added = sorted(set(current) - set(archived) - ignored)
    assert added == ["arc", "campaign", "campaign_manifest_sha256", "case", "groups",
                     "held_out_positions_used_in_fit"], added
    return {"campaign": DYNAMICS.relative_to(ROOT).as_posix(), "arrays": "bitwise equal",
            "shared_diagnostic_fields": "equal", "archived_solution_sha256": archived["solution_sha256"]}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=sorted(CASES))
    parser.add_argument("--satellite", required=True)
    parser.add_argument("--compare-archive", action="store_true")
    args = parser.parse_args()
    if args.compare_archive and args.case != "three":
        raise ValueError("Only the three-hour case has an archived diagnostic")
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    policy = verify(HELPERS)
    spec, fixture, orbit_path, manifest = locate(args.case)

    context, _, seeds = restore(fixture)
    sat = args.satellite
    assert sat in seeds and len(seeds) == 31
    assert context["epoch_count"] == 37 and context["step_s"] == spec["step_s"]
    assert float(context["duration_s"]) == spec["duration_s"]
    model, duration = context["model"], context["duration_s"]

    baseline = np.load(orbit_path)
    si = list(baseline["satellites"]).index(sat)
    ix = list(baseline["names"]).index(f"orbit:{sat}:0")
    observation_state = seeds[sat] + baseline["x"][ix:ix + 6]
    original_grid = baseline["times_s"]
    assert len(original_grid) == spec["grid"]
    # The station solution must be reproducible from its own estimate before it is used as a control.
    reproduced = Trajectory(observation_state, model, duration)
    np.testing.assert_array_equal(np.array([reproduced.state(t) for t in original_grid]), baseline["states"][si])

    times = original_grid[::3]
    assert len(times) == spec["native"]
    np.testing.assert_array_equal(np.diff(times), np.full(len(times) - 1, NATIVE_S))
    train = np.arange(0, len(times), 2)
    held = np.arange(1, len(times), 2)
    assert not set(train.tolist()) & set(held.tolist())
    assert sorted(train.tolist() + held.tolist()) == list(range(len(times)))

    reference, ecef, rotations = reference_positions(times, sat)
    positions = np.einsum("tji,tj->ti", rotations, ecef)
    estimate, fitted, history = solve_fixed(seeds[sat], times[train], positions[train], model, duration)
    # Only training epochs may reach the estimator; assert it on the arrays actually passed in.
    assert len(times[train]) == len(train) and not np.isin(times[held], times[train]).any()

    states = np.array([fitted.state(t) for t in times])
    inertial_delta = states[:, :3] - positions
    cartesian_delta = np.einsum("tij,tj->ti", rotations, states[:, :3]) - ecef
    np.testing.assert_allclose(np.linalg.norm(cartesian_delta, axis=1), np.linalg.norm(inertial_delta, axis=1), rtol=0, atol=2e-8)
    baseline_delta = baseline["states"][si, ::3, :3] - positions

    first = np.arange(min(len(times), CASES["three"]["native"]))
    groups = {"train": train, "held": held, "all": np.arange(len(times)), "first_three_hours": first}
    result = {"status": "reference_only_fixed_force_fit_complete_not_independent_POD", "satellite": sat,
              "case": args.case, "arc": {"duration_s": float(duration), "native_samples": len(times),
                                         "train_samples": len(train), "held_samples": len(held)},
              "fit": {name: stats(cartesian_delta[index]) for name, index in groups.items()},
              "observation_baseline": {name: stats(baseline_delta[index]) for name, index in groups.items()},
              "initial_state_correction_from_broadcast": (estimate - seeds[sat]).tolist(),
              "history": history, "production_trajectory_reproduced_bitwise": True,
              "held_out_positions_used_in_fit": False,
              "heldout_below_10_cm": stats(cartesian_delta[held])["rms_3d_m"] < .1}
    np.savez_compressed(output / "diagnostic_fit.npz", initial_state=estimate, states=states, times_s=times,
                        reference_ecef_m=ecef, rotations=rotations, reference_inertial_m=positions,
                        train_indices=train, held_indices=held, baseline_states=baseline["states"][si, ::3],
                        satellite=np.array(sat))
    result["solution_sha256"] = sha(output / "diagnostic_fit.npz")
    result.update(train_indices=train.tolist(), held_indices=held.tolist(), times_s=times.tolist(),
                  groups={name: index.tolist() for name, index in groups.items()},
                  force_coefficients_mps2=[-1e-7, 0., 0., 0., 0.], parameter_count=6, orbit_priors=False,
                  reference_sha256=reference.sha256, baseline_sha256=sha(orbit_path), fixture_sha256=sha(fixture),
                  campaign=spec["campaign"].relative_to(ROOT).as_posix(),
                  campaign_manifest_sha256=sha(spec["campaign"] / "validation.json"),
                  helper_sources_sha256={name: sha(ROOT / name) for name in (*HELPERS, *OWN)})
    if args.compare_archive:
        result["archived_reproduction"] = compare_with_archive(sat, result, output)
    result["source_policy"] = policy
    (output / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("history", "source_policy", "groups", "times_s")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
