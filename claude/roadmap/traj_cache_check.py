"""Guarded exactness check for claude.roadmap.traj_cache (gate for using the cache in step 3).

    python -m customkf.guard -- claude.roadmap.traj_cache_check

On the August-3 six-hour fixture at Astra's archived D0 final x: integrate all satellites exactly as
traj_cache's worker does, save and reload the arrays, then require bitwise equality with a fresh
LongPilot.products(x) for every satellite's state, state-transition partial and force partial on the
300 s output grid, plus bitwise-equal Jacobian blocks for two epochs. No precise products are read.
"""
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.propagation import propagate
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.dynamic_observation import SETTINGS
from claude.tools.dated_fixture import restore
from claude.roadmap.long_pilot import LongPilot
from claude.roadmap.traj_cache import initial_and_parameters, key, cached_products
from claude.roadmap.common import ROOT, write_json

FIXTURE = ROOT/"claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json"
FINAL = ROOT/"claude/runs/20260912T193417Z-day215-pod/d0-linear-3"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    context, rows, seeds = restore(FIXTURE)
    step = json.loads((FINAL/"step.json").read_text())
    assert sha(FINAL/"solution.npz") == step["solution_sha256"]
    x = np.load(FINAL/"solution.npz")["x"]
    pilot = LongPilot(context, rows, seeds, estimate=(0,))
    times = np.r_[np.arange(0., pilot.duration, 15.), pilot.duration]
    arrays, keys = dict(times=times), {}
    start = time.perf_counter()
    for sat in pilot.sats:
        initial, p = initial_and_parameters(pilot, sat, x)
        result = propagate(initial, times, pilot.context["model"], p, settings=SETTINGS)
        arrays[f"{sat}_states"], arrays[f"{sat}_stm"], arrays[f"{sat}_sensitivity"] = result.states_m_mps, result.state_transition, result.parameter_sensitivity
        keys[sat] = key(initial, p)
    integrate_s = time.perf_counter()-start
    np.savez_compressed(folder/"trajectories.npz", **arrays)
    write_json(folder/"trajectories.json", dict(satellites=pilot.sats, keys=keys, cache_sha256=sha(folder/"trajectories.npz")))
    start = time.perf_counter()
    cached = cached_products(pilot, x, [folder/"trajectories.npz"])
    load_s = time.perf_counter()-start
    fresh = pilot.products(x)
    grid = np.arange(10., pilot.duration-9., 300.)
    for sat in pilot.sats:
        a, b = cached.trajectories[sat], fresh.trajectories[sat]
        for t in grid:
            np.testing.assert_array_equal(a.state(t), b.state(t))
            np.testing.assert_array_equal(a.partial(t), b.partial(t))
            np.testing.assert_array_equal(a.force_partial(t), b.force_partial(t))
    for ei in (0, pilot.epoch_count-1):
        u, ys_u, ss_u = pilot.epoch_block(x, ei, cached)
        v, ys_v, ss_v = pilot.epoch_block(x, ei, fresh)
        np.testing.assert_array_equal(u.retained, v.retained)
        np.testing.assert_array_equal(u.local, v.local)
        np.testing.assert_array_equal(ys_u, ys_v)
    wrong = x.copy()
    wrong[pilot.index[f"orbit:{pilot.sats[0]}:0"]] += 1e-3
    try:
        cached_products(pilot, wrong, [folder/"trajectories.npz"])
        raise AssertionError("Mismatched linearization point was accepted")
    except ValueError:
        pass
    report = dict(status="trajectory_cache_bitwise_pass", integrate_seconds=integrate_s, load_seconds=load_s,
                  cache_mib=(folder/"trajectories.npz").stat().st_size/2**20, satellites=len(pilot.sats), grid_points=len(grid),
                  mismatch_refused=True)
    write_json(folder/"traj_cache_check.json", report)
    (folder/"trajectories.npz").unlink()
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
