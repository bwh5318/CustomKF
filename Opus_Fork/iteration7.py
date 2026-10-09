"""ECOM-7-capable copy of `Opus_Fork.iteration` (which earlier campaigns pin, unchanged).

FORKED_FROM = {"Opus_Fork/iteration.py": "65a8c51776facb8a978d7bc7a59971042b9fc41d987a9d186e78a3419b737fd8"}

**One line differs.** The step-bound computation in `mode_solve` named force columns with the literal
`('D0','Y0','B0','Bc1','Bs1')[k]`, which raises for ECOM-7's columns 5 and 6. It now reads
`claude.roadmap.long_pilot.FORCE_NAMES[k]` at call time, so it follows whatever column names the
running pilot uses. With ECOM5 names it is byte-for-byte the same arithmetic. Everything else is the
original: objective, elimination, rank rule, stationarity, line search, checkpoint bindings and the
precise-product audit hook.
"""
"""Opus_Fork copy of claude/roadmap/long_iteration.py with a configurable workspace budget.

FORKED_FROM = {"claude/roadmap/long_iteration.py": "fea840d43ad5ab1cf978de050e323af83b563d6b64583278c08e345944e7ddb1"}

**One line differs.** The original hardcodes a 256 MiB streaming-workspace preflight. A
31-satellite 24 h fit needs about 265 MiB, because 31 satellites carry roughly 170 more
ambiguities than 27 and the per-epoch recovery term accumulates across the arc; the estimate
runs 233.6 -> 246.9 -> 255.3 MiB and tips over at chunk 9 of 12.

The 256 MiB figure is named in RESOURCE_POLICY_20260917.md and dates from a 2 GiB job cap.
These fits are measured at about 500 MiB peak job memory inside a 4 GiB cap, so 265 MiB of
workspace is not a resource risk. The user authorized raising it for the fork on 20 September
2026; the budget is `OPUSFORK_WORKSPACE_MIB`, default 512. **Astra's module is untouched and
her path keeps 256 MiB.**

This is a stopgap, not the answer. Any larger network breaches any fixed cap, so ambiguity
elimination at arc end -- folding each ambiguity out once its arc ends, which Astra's own
handoff asks for -- is still required before Phase 3.1 grows the network past 25 stations.

Everything else below is byte-for-byte the original, including the objective, local
elimination, rank rule, stationarity thresholds, line-search fractions, checkpoint bindings
and the precise-product audit hook.
"""

# --- original module docstring, preserved ---
# """Guarded, checkpoint-split iteration for LongPilot (roadmap steps 2-3).
# 
#     state:  ... long_iteration state  --fixture F --config C
#     chunk:  ... long_iteration chunk  --fixture F --config C --state S [--previous SOL] --start a --stop b [--checkpoint K]
#     solve:  ... long_iteration solve  --fixture F --config C --state S [--previous SOL] --checkpoint K
#     trial:  ... long_iteration trial  --fixture F --config C --state S --linear L --alpha 1.0
# 
# Objective, local elimination, rank rule, stationarity thresholds (customkf.nonlinear_stop.stationary)
# and line-search fractions are those of Astra's split iteration; only the linear algebra is streamed.
# Every checkpoint is bound to the fixture, config, state and linearization-point hashes.
# No precise product is opened (audit hook).
# """

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.nonlinear_stop import stationary
from claude.tools.dated_fixture import restore
from claude.roadmap.long_pilot import LongPilot
from claude.roadmap import long_pilot as _lp
from claude.roadmap.streaming import Accumulator
from claude.roadmap.traj_cache import cached_products
from claude.roadmap.common import write_json
from claude.tools.dated_d0 import SCALE


def array_sha(x):
    return hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()


def load_config(args):
    config = json.loads(args.config.read_text())
    nominal = None
    if config["nominal"] != "unit":
        path = Path(config["nominal"]["path"])
        if not path.is_absolute():
            path = ROOT/path
        assert sha(path) == config["nominal"]["sha256"], "Calibration changed"
        nominal = json.loads(path.read_text())["nominal_d0_mps2"]
    prior = {int(k): float(v) for k, v in config.get("prior_sigma_mps2", {}).items()}
    return config, nominal, tuple(config.get("estimate", ())), prior


def build(args, with_state=True):
    context, rows, seeds = restore(args.fixture)
    context.update(fixture_sha256=sha(args.fixture), config_sha256=sha(args.config))  # caller identity for cached_products (M10)
    config, nominal, estimate, prior = load_config(args)
    state = None
    if with_state:
        state = json.loads(args.state.read_text())
        assert state["fixture_sha256"] == sha(args.fixture) and state["config_sha256"] == sha(args.config)
    return LongPilot(context, rows, seeds, nominal=nominal, estimate=estimate, prior_sigma=prior, state=state), config


def point(args, pilot):
    if args.previous is None:
        return np.zeros(len(pilot.names)), []
    step = json.loads((args.previous/"step.json").read_text())
    assert sha(args.previous/"solution.npz") == step["solution_sha256"]
    saved = np.load(args.previous/"solution.npz")
    np.testing.assert_array_equal(saved["names"], pilot.names)
    return saved["x"].copy(), step["history"]


def mode_state(args, folder):
    if args.trajectories:
        # Exact cached x=0 trajectories replace LongPilot.initial_state's integration (bitwise identical products).
        files = list(args.trajectories)

        class CachedStatePilot(LongPilot):
            def products(self, x):
                return cached_products(self, x, files)
        context, rows, seeds = restore(args.fixture)
        context.update(fixture_sha256=sha(args.fixture), config_sha256=sha(args.config))  # caller identity for cached_products (M10)
        _, nominal, estimate, prior = load_config(args)
        pilot = CachedStatePilot(context, rows, seeds, nominal=nominal, estimate=estimate, prior_sigma=prior)
    else:
        pilot, _ = build(args, with_state=False)
    record = pilot.state_record()
    record.update(fixture_sha256=sha(args.fixture), config_sha256=sha(args.config))
    (folder/"state.json").write_text(json.dumps(record)+"\n")
    write_json(folder/"step.json", dict(status="state_ready", state_sha256=sha(folder/"state.json"), retained=pilot.n,
               local=sum(map(len, pilot.local_names)), links=len(pilot.rows), epochs=pilot.epoch_count, nodes=pilot.nodes,
               arcs=len(pilot.arcs), satellites=len(pilot.sats)))
    print(open(folder/"step.json").read(), flush=True)


def mode_chunk(args, folder):
    pilot, _ = build(args)
    x, _ = point(args, pilot)
    binding = dict(fixture=sha(args.fixture), config=sha(args.config), state=sha(args.state), x=array_sha(x))
    if args.checkpoint is not None:
        meta = json.loads((args.checkpoint/"step.json").read_text())
        assert meta["binding"] == binding and meta["stop"] == args.start
        assert sha(args.checkpoint/"checkpoint.npz") == meta["checkpoint_sha256"]
        with np.load(args.checkpoint/"checkpoint.npz") as data:
            acc = Accumulator.restore(data)
            residual, sigma = list(data["residual"]), list(data["sigma"])
    else:
        assert args.start == 0
        acc, residual, sigma = Accumulator(pilot.n), [], []
    start = time.perf_counter()
    products = cached_products(pilot, x, args.trajectories) if args.trajectories else pilot.products(x)
    integrate_s = time.perf_counter()-start
    largest = 0
    for ei in range(args.start, args.stop):
        block, ys, ss = pilot.epoch_block(x, ei, products)
        largest = max(largest, len(ys))
        acc.add_block(block.retained, block.local, block.target, block.sigma)
        residual += ys
        sigma += ss
        print(f"epoch {ei} rows {len(ys)} elapsed {time.perf_counter()-start:.1f}", flush=True)
    budget = int(os.environ.get("OPUSFORK_WORKSPACE_MIB", "512"))
    if acc.workspace_bytes(largest) > budget*2**20:
        raise ValueError(f"Streaming workspace estimate exceeds the {budget} MiB solve preflight")
    np.savez(folder/"checkpoint.npz", **acc.state(), residual=np.array(residual), sigma=np.array(sigma))
    write_json(folder/"step.json", dict(status="chunk_complete", binding=binding, start=args.start, stop=args.stop,
               epoch_count=pilot.epoch_count, checkpoint_sha256=sha(folder/"checkpoint.npz"), seconds=time.perf_counter()-start,
               integration_seconds=integrate_s, largest_block_rows=largest,
               workspace_estimate_mib=acc.workspace_bytes(largest)/2**20))


def save_solution(folder, pilot, x, products, residual, sigma, cov, history, status, binding):
    times = np.arange(10., pilot.duration-9., 300.)
    np.savez_compressed(folder/"solution.npz", x=x, names=np.array(pilot.names), states=np.array([[products.state(s, t) for t in times] for s in pilot.sats]),
                        satellites=np.array(pilot.sats), times_s=times, residual_m=residual, sigma_m=sigma, retained_covariance=cov)
    report = dict(status=status, history=history, binding=binding, solution_sha256=sha(folder/"solution.npz"), precise_products_used=False,
                  retained_covariance_at="pre-step linearization; diagnostic only")
    write_json(folder/"step.json", report)
    print(json.dumps(report, indent=2), flush=True)


def mode_solve(args, folder):
    pilot, config = build(args)
    x, history = point(args, pilot)
    binding = dict(fixture=sha(args.fixture), config=sha(args.config), state=sha(args.state), x=array_sha(x))
    meta = json.loads((args.checkpoint/"step.json").read_text())
    assert meta["binding"] == binding and meta["stop"] == pilot.epoch_count and sha(args.checkpoint/"checkpoint.npz") == meta["checkpoint_sha256"]
    with np.load(args.checkpoint/"checkpoint.npz") as data:
        acc = Accumulator.restore(data)
        residual, sigma = data["residual"].copy(), data["sigma"].copy()
    constraints = pilot.constraints(x)
    cost = float(np.sum((residual/sigma)**2)+np.sum((constraints[1]/constraints[2])**2))
    acc.add_constraints(*constraints)
    start = time.perf_counter()
    step, covariance, reduction = acc.solve()
    solve_s = time.perf_counter()-start
    products = cached_products(pilot, x, args.trajectories) if args.trajectories else pilot.products(x)
    index = pilot.index
    bound = max(np.linalg.norm(step[index[f"orbit:{s}:0"]:index[f"orbit:{s}:0"]+3]) +
                pilot.duration*np.linalg.norm(step[index[f"orbit:{s}:0"]+3:index[f"orbit:{s}:0"]+6]) for s in pilot.sats)
    force_bound = 0.
    if pilot.estimate:
        grid = np.arange(10., pilot.duration-9., 300.)
        force_bound = max(np.linalg.norm(products.trajectories[s].partial(t)[:3]@step[index[f"orbit:{s}:0"]:index[f"orbit:{s}:0"]+6] +
                          sum(products.trajectories[s].force_partial(t)[:3, k]*SCALE*step[index[f"srp{_lp.FORCE_NAMES[k]}:{s}"]] for k in pilot.estimate))
                          for s in pilot.sats for t in grid)
    bound = max(float(bound), float(force_bound))
    record = dict(iteration=len(history), cost_before=cost, predicted_reduction=reduction, whitened_direction_norm_squared=reduction,
                  trajectory_step_bound_m=bound, force_inclusive_sampled_step_bound_m=float(force_bound), solve_seconds=solve_s,
                  accumulated_rows=acc.rows, largest_update_rows=acc.largest_update_rows)
    if stationary(bound, cost, reduction, reduction):
        record.update(cost_after=cost, accepted=True, update_applied=False, termination="small_step_and_linearized_progress", step_fraction=0.)
        save_solution(folder, pilot, x, products, residual, sigma, covariance, history+[record], "converged", binding)
    else:
        np.savez_compressed(folder/"direction.npz", x=x, step=step, names=np.array(pilot.names), retained_covariance=covariance)
        write_json(folder/"step.json", dict(status="linearized", binding=binding, direction_sha256=sha(folder/"direction.npz"),
                   history=history, record=record))
        print(json.dumps(record, indent=2), flush=True)


def mode_trial(args, folder):
    pilot, _ = build(args)
    lin = json.loads((args.linear/"step.json").read_text())
    assert lin["status"] == "linearized" and sha(args.linear/"direction.npz") == lin["direction_sha256"]
    assert lin["binding"]["fixture"] == sha(args.fixture) and lin["binding"]["config"] == sha(args.config) and lin["binding"]["state"] == sha(args.state)
    saved = np.load(args.linear/"direction.npz")
    np.testing.assert_array_equal(saved["names"], pilot.names)
    x = saved["x"]+args.alpha*saved["step"]
    products = cached_products(pilot, x, args.trajectories) if args.trajectories else pilot.products(x)
    residual, sigma = [], []
    for ei in range(pilot.epoch_count):
        _, ys, ss = pilot.epoch_block(x, ei, products, jacobian=False)
        residual += ys
        sigma += ss
    residual, sigma = np.array(residual), np.array(sigma)
    cost = pilot.cost(residual, sigma, x)
    before = lin["record"]["cost_before"]
    accepted = cost <= before+max(1e-6, 1e-9*before)
    record = lin["record"] | dict(cost_after=cost, accepted=accepted, update_applied=accepted, termination="line_search", step_fraction=args.alpha)
    binding = dict(fixture=lin["binding"]["fixture"], config=lin["binding"]["config"], state=lin["binding"]["state"], x=array_sha(x))
    if accepted:
        save_solution(folder, pilot, x, products, residual, sigma, saved["retained_covariance"], lin["history"]+[record], "iteration_complete", binding)
    else:
        write_json(folder/"step.json", dict(status="trial_rejected", record=record))
        print("Trial rejected", cost, before, flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("state", "chunk", "solve", "trial"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--linear", type=Path)
    parser.add_argument("--start", type=int)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--alpha", type=float, choices=(1., .5, .25, .125))
    parser.add_argument("--trajectories", nargs="*", help="exact trajectory cache files for this x (traj_cache)")
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    dict(state=mode_state, chunk=mode_chunk, solve=mode_solve, trial=mode_trial)[args.mode](args, folder)


if __name__ == "__main__":
    main()
