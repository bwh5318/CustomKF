"""Fork copy of `claude.roadmap.traj_cache integrate` with a named ERP + thrust variant.

Same as `Opus_Fork.nongrav_traj_cache` (pinned by P1/R7, unchanged) but bound to `Opus_Fork.ngv_pilot`,
whose variant comes from `OPUSFORK_NONGRAV_VARIANT`.

FORKED_FROM = {"claude/roadmap/traj_cache.py": "cd7e160eedeb8077caa6cb3d7021c515cb330b03cc9e125acb1e8652a0764ef0"}

Two differences, nothing else:

1. Each satellite is propagated with `Opus_Fork.nongrav.PhysicalRadiation` wrapping the
   unchanged model, instead of the shared `context["model"]`.
2. `trajectories.json` records `force_model` (variant, `nongrav.py` hash, metadata hash).
   Astra's cache key hashes only initial state and parameters, so without this binding a cache
   from the plain model would be indistinguishable. `Opus_Fork.nongrav_pilot` refuses caches
   that lack it or carry a different one.

The output arrays and file layout are the original's, so `claude.roadmap.traj_cache.cached_products`
loads them unchanged.
"""
import argparse
import hashlib
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
from claude.roadmap.traj_cache import accepted_point, initial_and_parameters, key
from claude.roadmap.common import write_json

from .ngv_pilot import model_binding, satellite_models


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("integrate",))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--solution", type=Path)
    parser.add_argument("--linear", type=Path)
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--group", type=int, required=True)
    parser.add_argument("--groups", type=int, required=True)
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    from claude.roadmap.long_iteration import build, load_config
    from claude.tools.dated_fixture import restore
    from claude.roadmap.long_pilot import LongPilot
    args.previous = args.solution
    if args.state is None:
        assert args.solution is None and args.linear is None, "Only the x=0 point may be integrated without a state"
        context, rows, seeds = restore(args.fixture)
        _, nominal, estimate, prior = load_config(args)
        pilot = LongPilot(context, rows, seeds, nominal=nominal, estimate=estimate, prior_sigma=prior,
                          state=dict(clock_seeds=[], windup=[], amb_origins={}))
    else:
        pilot, _ = build(args)
    if args.linear is not None or args.solution is not None:
        # Accepted, identity-bound points only (Sol review SOL-05; claude.roadmap.traj_cache.accepted_point).
        identity = dict(fixture=sha(args.fixture), config=sha(args.config), state=sha(args.state))
        if args.linear is not None:
            x, _ = accepted_point(args.linear, pilot.names, identity, force_model=model_binding(), alpha=args.alpha)
        else:
            x, _ = accepted_point(args.solution, pilot.names, identity, force_model=model_binding())
    else:
        x = np.zeros(len(pilot.names))
    group = pilot.sats[args.group::args.groups]
    models = satellite_models(pilot.context, group)
    times = np.r_[np.arange(0., pilot.duration, 15.), pilot.duration]
    arrays, keys = dict(times=times), {}
    start = time.perf_counter()
    for sat in group:
        initial, p = initial_and_parameters(pilot, sat, x)
        result = propagate(initial, times, models[sat], p, settings=SETTINGS)
        arrays[f"{sat}_states"] = result.states_m_mps
        arrays[f"{sat}_stm"] = result.state_transition
        arrays[f"{sat}_sensitivity"] = result.parameter_sensitivity
        keys[sat] = key(initial, p)
        print(sat, round(time.perf_counter()-start, 1), flush=True)
    np.savez_compressed(folder/"trajectories.npz", **arrays)
    write_json(folder/"trajectories.json", dict(status="trajectory_cache", satellites=group, keys=keys, group=args.group, groups=args.groups,
               x_sha256=hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest(), seconds=time.perf_counter()-start,
               cache_sha256=sha(folder/"trajectories.npz"), fixture_sha256=sha(args.fixture), config_sha256=sha(args.config),
               force_model=model_binding()))


if __name__ == "__main__":
    main()
