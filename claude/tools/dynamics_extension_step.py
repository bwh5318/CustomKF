"""Guarded fixed-force reference fit for one satellite under the documented source-drift policy.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 300 -- claude.tools.dynamics_extension_step --satellite G01 [--compare-archive]

Same computation as the real-fit branch of Astra's pinned claude/tools/dynamics_ceiling_step.py.
That script cannot run unchanged now, because it asserts every GUAM source pin and root
customkf/stage5_pilot.py has a documented prepare()-only change (claude/tools/pinned_sources.py).
Seven half-hour native IGS positions train and six quarter-hours are withheld. This is an
IGS-dependent diagnostic and never an input to station-based POD. --compare-archive requires
bitwise agreement with Astra's archived G18/G03/G22 results.
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
from claude.tools.dynamics_ceiling_step import BASE, TRAIN, HELD, stats
from claude.tools.pinned_sources import DYNAMICS, ROOT, sha, verify

HELPERS = ("claude/tools/fixed_force_fit.py", "claude/tools/dynamics_ceiling_step.py", "claude/tools/evaluate_ablation.py")


def compare_with_archive(sat, result, output):
    manifest = json.loads((DYNAMICS / "validation.json").read_text())
    for name in ("diagnostic.json", "diagnostic_fit.npz"):
        assert sha(DYNAMICS / sat / name) == manifest["artifacts_sha256"][f"{sat}/{name}"], name
    archived = json.loads((DYNAMICS / sat / "diagnostic.json").read_text())
    old, new = np.load(DYNAMICS / sat / "diagnostic_fit.npz"), np.load(output / "diagnostic_fit.npz")
    assert sorted(old.files) == sorted(new.files)
    for key in old.files:
        np.testing.assert_array_equal(new[key], old[key], err_msg=key)
    # The NPZ file hash embeds zip timestamps, so arrays are compared instead of solution_sha256.
    current = json.loads(json.dumps(result))
    ignored = {"solution_sha256", "helper_sources_sha256"}
    differing = sorted(k for k in set(current) | set(archived) if k not in ignored and current.get(k) != archived.get(k))
    assert not differing, differing
    return {"campaign": DYNAMICS.relative_to(ROOT).as_posix(), "arrays": "bitwise equal",
            "diagnostic_fields": "equal except solution/helper hashes", "archived_solution_sha256": archived["solution_sha256"]}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--satellite", required=True)
    parser.add_argument("--compare-archive", action="store_true")
    args = parser.parse_args()
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    policy = verify(HELPERS)
    baseline_manifest = json.loads((BASE / "validation.json").read_text())
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
                  helper_sources_sha256={name: sha(ROOT / name) for name in
                                         (*HELPERS, "claude/tools/dynamics_extension_step.py", "claude/tools/pinned_sources.py")})
    if args.compare_archive:
        result["archived_reproduction"] = compare_with_archive(sat, result, output)
    result["source_policy"] = policy
    (output / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("history", "source_policy")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
