"""Guarded gate evaluation for STREAMING_AND_ARCS_PROTOCOL.md (G2c, G2d). No precise products.

    python -m customkf.guard -- claude.roadmap.gate_checks g2c --parity DIR [DIR ...]
    python -m customkf.guard -- claude.roadmap.gate_checks g2d --campaign DIR --archive DIR
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import sha
from claude.roadmap.common import write_json


def g2c(args, folder):
    results = {}
    ok = True
    for directory in args.parity:
        report = json.loads((Path(directory)/"parity.json").read_text())
        n = report["retained"]
        for label, r in report["results"].items():
            # Estimate tolerance relative to the largest estimate magnitude of that solve.
            passed = (r["max_abs_estimate_difference"] <= 1e-6*r["max_abs_reference_estimate"] and
                      r["max_relative_covariance_diagonal_difference"] <= 1e-6)
            if label == "split18":
                passed = passed and r["bitwise_equal_to_whole"]
            results[f"{report['x']}:{label}"] = dict(passed=bool(passed), **r)
            ok = ok and passed
    write_json(folder/"g2c.json", dict(gate="G2c", passed=bool(ok), results=results))
    print("G2c", ok, flush=True)
    if not ok:
        raise SystemExit(3)


def g2d(args, folder):
    manifest = json.loads((Path(args.campaign)/"validation.json").read_text())
    assert manifest["status"] == "long_fit_complete_not_accuracy_acceptance" and manifest["final"]
    final = Path(args.campaign)/manifest["final"]
    step = json.loads((final/"step.json").read_text())
    assert step["status"] == "converged" and sha(final/"solution.npz") == step["solution_sha256"]
    archive = Path(args.archive)
    old_step = json.loads((archive/"step.json").read_text())
    assert sha(archive/"solution.npz") == old_step["solution_sha256"]
    new, old = np.load(final/"solution.npz"), np.load(archive/"solution.npz")
    np.testing.assert_array_equal(new["names"], old["names"])
    np.testing.assert_array_equal(new["times_s"], old["times_s"])
    position = float(np.max(np.linalg.norm(new["states"][:, :, :3]-old["states"][:, :, :3], axis=2)))
    cost_new, cost_old = step["history"][-1]["cost_after"], old_step["history"][-1]["cost_after"]
    relative = abs(cost_new-cost_old)/cost_old
    chunks = {k: v for k, v in manifest["runs"].items() if "-chunk-" in k}
    per_epoch, integration, overhead = [], [], []
    for name in chunks:
        meta = json.loads((Path(args.campaign)/name/"step.json").read_text())
        per_epoch.append((meta["seconds"]-meta["integration_seconds"])/(meta["stop"]-meta["start"]))
        integration.append(meta["integration_seconds"])
        overhead.append(manifest["runs"][name]["elapsed_s"]-meta["seconds"])
    passed = position <= 1e-3 and relative <= 1e-6
    report = dict(gate="G2d", passed=bool(passed), max_sampled_position_difference_m=position, objective=cost_new, archived_objective=cost_old,
                  relative_objective_difference=relative, linearizations=len(manifest["linearizations"]),
                  max_chunk_seconds_per_epoch=max(per_epoch), mean_chunk_seconds_per_epoch=float(np.mean(per_epoch)),
                  max_chunk_integration_seconds=max(integration), max_chunk_startup_overhead_seconds=max(overhead),
                  six_hour_epochs=37,
                  total_guarded_seconds=manifest["total_guarded_seconds"], peak_job_memory_mib=manifest["peak_job_memory_mib"],
                  longest_worker_s=manifest["longest_worker_s"])
    write_json(folder/"g2d.json", report)
    print(json.dumps(report, indent=2), flush=True)
    if not passed:
        raise SystemExit(3)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=("g2c", "g2d"))
    parser.add_argument("--parity", nargs="+")
    parser.add_argument("--campaign")
    parser.add_argument("--archive")
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (g2c if args.gate == "g2c" else g2d)(args, folder)


if __name__ == "__main__":
    main()
