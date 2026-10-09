"""Guarded parity checks: LongPilot versus Astra's dated pilots on the August-3 six-hour fixture.

    dump:    python -m customkf.guard -- claude.roadmap.long_checks dump --arm fixed|d0
    compare: python -m customkf.guard -- claude.roadmap.long_checks compare --arm fixed|d0 --dump DIR

dump    : the dated ArcPilot/D0Pilot (with CachedEpoch, whose exactness stream_checks proves) at the archived
          final x; saves its Jacobian blocks, constraints, residuals and cost.
compare : LongPilot at the same x must (1) reproduce the archived residuals, sigmas, sampled states and cost
          bitwise, (2) reproduce every dumped block and the constraints bitwise, and (3) its streaming solve of
          that linearization is compared with reduced_qr. One Jacobian per worker keeps each under 300 s.
No precise products are read.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.reduced_network import reduced_qr
from customkf.network_square_root import Block
from claude.tools.dated_fixture import restore
from claude.tools.dated_arc import ArcPilot
from claude.tools.dated_d0 import D0Pilot
from claude.roadmap.long_pilot import LongPilot
from claude.roadmap.streaming import Accumulator, CachedEpoch
from claude.roadmap.common import ROOT, write_json

FIXTURE = ROOT/"claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json"
ARCHIVE = {"fixed": ROOT/"claude/runs/20260912T193417Z-day215-pod/fixed-linear-2",
           "d0": ROOT/"claude/runs/20260912T193417Z-day215-pod/d0-linear-3"}


def archived(arm):
    step = json.loads((ARCHIVE[arm]/"step.json").read_text())
    assert sha(ARCHIVE[arm]/"solution.npz") == step["solution_sha256"]
    return step, np.load(ARCHIVE[arm]/"solution.npz")


def dump(args, folder):
    context, rows, seeds = restore(FIXTURE)
    context = dict(context)
    context["epoch"] = CachedEpoch(context["epoch"])
    step, archive = archived(args.arm)
    start = time.perf_counter()
    pilot = (D0Pilot if args.arm == "d0" else ArcPilot)(context, rows, seeds)
    blocks, (c, z, s), residual, sigma, _, cost, _ = pilot.evaluate(archive["x"])
    seconds = time.perf_counter()-start
    arrays = dict(c=c, z=z, s=s, residual=residual, sigma=sigma, cost=np.array(cost), names=np.array(pilot.names),
                  block_rows=np.array([len(b.target) for b in blocks]), block_locals=np.array([b.local.shape[1] for b in blocks]),
                  retained=np.concatenate([b.retained for b in blocks]), local_flat=np.concatenate([b.local.ravel() for b in blocks]),
                  target=np.concatenate([b.target for b in blocks]), block_sigma=np.concatenate([b.sigma for b in blocks]))
    np.savez_compressed(folder/"dump.npz", **arrays)
    write_json(folder/"dump.json", dict(status="dated_pilot_jacobian_dump", arm=args.arm, seconds=seconds, cost=cost,
                                       dump_sha256=sha(folder/"dump.npz"), fixture_sha256=sha(FIXTURE)))
    print("dump", args.arm, seconds, cost, flush=True)


def compare(args, folder):
    meta = json.loads((args.dump/"dump.json").read_text())
    assert meta["arm"] == args.arm and sha(args.dump/"dump.npz") == meta["dump_sha256"]
    d = np.load(args.dump/"dump.npz")
    report = dict(arm=args.arm)
    context, rows, seeds = restore(FIXTURE)
    step, archive = archived(args.arm)
    start = time.perf_counter()
    pilot = LongPilot(context, rows, seeds, estimate=(0,) if args.arm == "d0" else ())
    report["long_init_seconds"] = time.perf_counter()-start
    np.testing.assert_array_equal(pilot.names, archive["names"])
    np.testing.assert_array_equal(pilot.names, d["names"])
    x = archive["x"]
    start = time.perf_counter()
    blocks, constraints, residual, sigma, cost, products = pilot.evaluate(x)
    report["long_jacobian_seconds"] = time.perf_counter()-start
    report["long_ms_per_link"] = 1000*report["long_jacobian_seconds"]/len(rows)
    np.testing.assert_array_equal(residual, archive["residual_m"])
    np.testing.assert_array_equal(sigma, archive["sigma_m"])
    states = np.array([[products.state(s, t) for t in archive["times_s"]] for s in pilot.sats])
    np.testing.assert_array_equal(states, archive["states"])
    assert cost == step["history"][-1]["cost_after"], (cost, step["history"][-1]["cost_after"])
    report["forward_bitwise_equal_to_archive"] = True
    assert float(d["cost"]) == cost
    np.testing.assert_array_equal(d["residual"], residual)
    row = local = 0
    for i, b in enumerate(blocks):
        m, k = int(d["block_rows"][i]), int(d["block_locals"][i])
        np.testing.assert_array_equal(d["retained"][row:row+m], b.retained)
        np.testing.assert_array_equal(d["local_flat"][local:local+m*k].reshape(m, k), b.local)
        np.testing.assert_array_equal(d["target"][row:row+m], b.target)
        np.testing.assert_array_equal(d["block_sigma"][row:row+m], b.sigma)
        row, local = row+m, local+m*k
    assert row == len(d["target"]) and len(blocks) == len(d["block_rows"])
    for key, value in zip("czs", constraints):
        np.testing.assert_array_equal(d[key], value)
    report["jacobian_and_constraints_bitwise_equal_to_dated_pilot"] = True
    dense = reduced_qr(blocks, constraints)
    acc = Accumulator(pilot.n)
    for b in blocks:
        acc.add_block(b.retained, b.local, b.target, b.sigma)
    acc.add_constraints(*constraints)
    estimate, covariance, reduction = acc.solve()
    report["streaming_vs_reduced_qr"] = dict(
        max_abs_estimate_difference=float(np.max(np.abs(estimate-dense.estimate))), max_abs_estimate=float(np.max(np.abs(dense.estimate))),
        max_relative_covariance_diagonal_difference=float(np.max(np.abs(np.diag(covariance)-np.diag(dense.retained_covariance))/np.diag(dense.retained_covariance))),
        predicted_reduction=reduction, archived_predicted_reduction=step["history"][-1]["predicted_reduction"])
    report["status"] = "long_pilot_parity_pass"
    write_json(folder/"long_checks.json", report)
    print(json.dumps(report, indent=2), flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dump", "compare"))
    parser.add_argument("--arm", choices=("fixed", "d0"), required=True)
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (dump if args.mode == "dump" else compare)(args, folder)


if __name__ == "__main__":
    main()
