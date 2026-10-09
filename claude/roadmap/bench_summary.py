"""Guarded bench summary (roadmap step 4, BENCH_PROTOCOL.md). Reads per-day bench_evaluate outputs only.

    python -m customkf.guard -- claude.roadmap.bench_summary --day-report DAY FILE [--day-report ...] --window common
"""
import argparse
import json
import math
import os
from pathlib import Path
import numpy as np
from claude.roadmap.common import write_json


def sign_test_p(improved, worsened):
    """One-sided binomial P(X >= improved | n, 1/2) over non-tied satellite-days."""
    n = improved+worsened
    return float(sum(math.comb(n, k) for k in range(improved, n+1))/2**n) if n else 1.


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-report", nargs=2, action="append", required=True, metavar=("DAY", "FILE"))
    parser.add_argument("--window", default="common")
    args = parser.parse_args()
    days, pooled, logs = {}, {}, {}
    for day, path in args.day_report:
        report = json.loads(Path(path).read_text())
        domain = report["domains"][args.window]
        days[day] = dict(samples=domain["common_samples"], rms={a: v["all"]["rms_3d_m"] for a, v in domain["arms"].items()},
                         ure={a: v["all"]["rms_orbit_ure_m"] for a, v in domain["arms"].items()},
                         by_block={a: {g: b["rms_3d_m"] for g, b in v["by_block"].items()} for a, v in domain["arms"].items()})
        arms = domain["arms"]
        for a in arms:
            pooled.setdefault(a, []).append(arms[a]["all"]["rms_3d_m"])
        for a in arms:
            for b in arms:
                if a == b:
                    continue
                ratios = [math.log(arms[a]["per_satellite"][s]["rms_3d_m"]/arms[b]["per_satellite"][s]["rms_3d_m"]) for s in arms[b]["per_satellite"]]
                logs.setdefault((a, b), []).extend(ratios)
    comparisons = {}
    for (a, b), ratios in logs.items():
        per_day = {d: 100*(v["rms"][a]/v["rms"][b]-1) for d, v in days.items()}
        improved, worsened = sum(r < 0 for r in ratios), sum(r > 0 for r in ratios)
        comparisons[f"{a}_vs_{b}"] = dict(per_day_pooled_change_percent=per_day, days_at_least_5_percent_better=sum(v <= -5 for v in per_day.values()),
                                          satellite_days=len(ratios), improved=improved, worsened=worsened, sign_test_p_one_sided=sign_test_p(improved, worsened),
                                          median_ratio=float(math.exp(np.median(ratios))))
    flags = {}
    if "FB6_vs_A0" in comparisons:
        c = comparisons["FB6_vs_A0"]
        flags["FB6_consistent"] = bool(c["days_at_least_5_percent_better"] >= 4 and c["sign_test_p_one_sided"] < .05)
    if "L*_vs_FB6" in comparisons:
        flags["Lstar_adds_value"] = bool(comparisons["L*_vs_FB6"]["days_at_least_5_percent_better"] >= 4)
    report = dict(status="bench_summary_not_accuracy_acceptance", window=args.window, days=days,
                  mean_pooled_rms_m={a: float(np.mean(v)) for a, v in pooled.items()}, comparisons=comparisons, flags=flags,
                  sources={d: p for d, p in args.day_report})
    write_json(Path(os.environ["CUSTOMKF_RUN_DIR"])/"bench_summary.json", report)
    print(json.dumps(dict(mean=report["mean_pooled_rms_m"], flags=flags,
                          per_day={k: v["per_day_pooled_change_percent"] for k, v in comparisons.items() if k.endswith("_vs_A0") or k == "L*_vs_FB6"}), indent=2), flush=True)


if __name__ == "__main__":
    main()
