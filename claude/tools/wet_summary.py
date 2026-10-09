"""Guarded compact reporting arithmetic from completed wet experiment evidence."""
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    path = ROOT / "claude/runs/20260911T172336Z-wet/evaluation/evaluation.json"
    data = json.loads(path.read_text())
    residuals = {}
    for case, stations in data["station_residuals"].items():
        residuals[case] = {}
        for kind in ("code", "phase"):
            values = [s[kind] for s in stations.values()]
            count = sum(v["count"] for v in values)
            residuals[case][kind] = {"count": count,
                "rms_mm": float(np.sqrt(sum(v["count"] * v["rms_mm"]**2 for v in values) / count)),
                "above_4_sigma": sum(v["above_4_sigma"] for v in values)}
    before = data["baseline"]["groups"]["all"]["fit"]["rms_3d_m"]
    after = data["hourly"]["groups"]["all"]["fit"]["rms_3d_m"]
    per = data["per_satellite_change"]
    report = {"evaluation_sha256": sha(path), "improvement_percent": 100 * (before - after) / before,
              "improved_satellites": sum(v["change_m"] < 0 for v in per.values()),
              "worsened_satellites": sum(v["change_m"] > 0 for v in per.values()),
              "pooled_residuals": residuals,
              "class_counts": {label: sum(v["class"] == label for v in data["hourly"]["per_satellite"].values()) for label in ("determined", "poorly_determined", "prior_only")}}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
