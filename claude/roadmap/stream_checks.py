"""Guarded checks for roadmap step 2 (streaming solve and exact frame caching).

    profile: python -m customkf.guard -- claude.roadmap.stream_checks profile --epochs 3
    parity:  python -m customkf.guard -- claude.roadmap.stream_checks parity --x cold|final

profile: cProfile of Astra's dated D0Pilot.evaluate on the first N epochs of the August-3 fixture,
         with and without CachedEpoch; the two Jacobians/residuals must agree bitwise.
parity:  one full six-hour D0 linearization; reduced_qr versus the streaming Accumulator (whole and
         checkpoint-split at epoch 18): estimate, retained covariance, predicted reduction.
No precise products are read.
"""
import argparse
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time
import numpy as np
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.reduced_network import reduced_qr
from customkf.nonlinear_stop import model_reduction
from claude.tools.dated_fixture import restore
from claude.tools.dated_d0 import D0Pilot
from claude.roadmap.streaming import Accumulator, CachedEpoch
from claude.roadmap.common import write_json, ROOT

FIXTURE = ROOT/"claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json"
FINAL = ROOT/"claude/runs/20260912T193417Z-day215-pod/d0-linear-3/solution.npz"
FIRST = ROOT/"claude/runs/20260912T193417Z-day215-pod/d0-trial-0-0/solution.npz"


class Truncated(D0Pilot):
    """Restrict evaluate() to the first N epochs without touching the parent's logic."""
    def __init__(self, context, rows, seeds, epochs):
        super().__init__(context, rows, seeds)
        self.keep = epochs

    def evaluate(self, x, jacobian=True, observations=None):
        full, self.epoch_count = self.epoch_count, self.keep
        try:
            return super().evaluate(x, jacobian, observations)
        finally:
            self.epoch_count = full


def profile(args, folder):
    context, rows, seeds = restore(FIXTURE)
    report = {}
    outputs = {}
    for label in ("original", "cached"):
        c = dict(context)
        if label == "cached":
            c["epoch"] = CachedEpoch(context["epoch"])
        pilot = Truncated(c, rows, seeds, args.epochs)
        x = np.load(FINAL)["x"]
        links = sum(1 for r in rows if r["epoch"] < args.epochs)
        profiler = cProfile.Profile()
        start = time.perf_counter()
        profiler.enable()
        blocks, constraints, residual, sigma, _, cost, _ = pilot.evaluate(x)
        profiler.disable()
        elapsed = time.perf_counter()-start
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(25)
        (folder/f"profile_{label}.txt").write_text(stream.getvalue())
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("tottime").print_stats(25)
        (folder/f"profile_{label}_tottime.txt").write_text(stream.getvalue())
        outputs[label] = (blocks, residual, sigma)
        report[label] = dict(epochs=args.epochs, links=links, seconds=elapsed, ms_per_link=1000*elapsed/links)
        print(label, report[label], flush=True)
    (b0, r0, s0), (b1, r1, s1) = outputs["original"], outputs["cached"]
    np.testing.assert_array_equal(r0, r1)
    np.testing.assert_array_equal(s0, s1)
    for u, v in zip(b0, b1):
        np.testing.assert_array_equal(u.retained, v.retained)
        np.testing.assert_array_equal(u.local, v.local)
        np.testing.assert_array_equal(u.target, v.target)
    report["cached_bitwise_equal"] = True
    report["speedup"] = report["original"]["seconds"]/report["cached"]["seconds"]
    write_json(folder/"profile.json", report)
    print(json.dumps(report, indent=2), flush=True)


def parity(args, folder):
    context, rows, seeds = restore(FIXTURE)
    context["epoch"] = CachedEpoch(context["epoch"])
    pilot = D0Pilot(context, rows, seeds)
    x = np.zeros(len(pilot.names)) if args.x == "cold" else np.load(FINAL if args.x == "final" else FIRST)["x"]
    start = time.perf_counter()
    blocks, constraints, residual, sigma, _, cost, _ = pilot.evaluate(x)
    jacobian_s = time.perf_counter()-start
    start = time.perf_counter()
    dense = reduced_qr(blocks, constraints)
    dense_s = time.perf_counter()-start
    reduction, dnorm = model_reduction(blocks, constraints, dense.estimate)
    results = {}
    for label, split in (("whole", None), ("split18", 18)):
        start = time.perf_counter()
        acc = Accumulator(constraints[0].shape[1])
        for ei, b in enumerate(blocks):
            if split is not None and ei == split:
                np.savez_compressed(folder/"checkpoint.npz", **acc.state())
                with np.load(folder/"checkpoint.npz") as data:
                    acc = Accumulator.restore(data)
            acc.add_block(b.retained, b.local, b.target, b.sigma)
        acc.add_constraints(*constraints)
        estimate, covariance, predicted = acc.solve()
        seconds = time.perf_counter()-start
        n = constraints[0].shape[1]
        scale = np.maximum(np.abs(dense.estimate), 1e-12)
        results[label] = dict(seconds=seconds,
            max_abs_estimate_difference=float(np.max(np.abs(estimate-dense.estimate))),
            max_abs_reference_estimate=float(np.max(np.abs(dense.estimate))),
            max_relative_retained_difference=float(np.max(np.abs(estimate[:n]-dense.estimate[:n])/np.maximum(np.abs(dense.estimate[:n]), 1e-9))),
            max_abs_covariance_difference=float(np.max(np.abs(covariance-dense.retained_covariance))),
            max_relative_covariance_diagonal_difference=float(np.max(np.abs(np.diag(covariance)-np.diag(dense.retained_covariance))/np.diag(dense.retained_covariance))),
            predicted_reduction=predicted, model_reduction=reduction, direction_norm_squared=dnorm,
            relative_reduction_difference=abs(predicted-reduction)/max(abs(reduction), 1e-300),
            accumulated_rows=acc.rows, local_total=acc.local_total, R_shape=list(acc.R.shape),
            largest_update_rows=acc.largest_update_rows)
        if label == "split18":
            whole = results["whole"]
            results[label]["bitwise_equal_to_whole"] = bool(np.array_equal(estimate, whole_estimate))
        else:
            whole_estimate = estimate
        print(label, results[label], flush=True)
    report = dict(status="streaming_parity_check", x=args.x, cost=cost, jacobian_seconds=jacobian_s, reduced_qr_seconds=dense_s,
                  reduced_qr_workspace_mib=dense.workspace_estimate_bytes/2**20, retained=len(pilot.names) - sum(map(len, pilot.local_names)),
                  results=results)
    write_json(folder/"parity.json", report)
    print(json.dumps(report, indent=2), flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("profile", "parity"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--x", choices=("cold", "first", "final"), default="cold")
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (profile if args.mode == "profile" else parity)(args, folder)


if __name__ == "__main__":
    main()
