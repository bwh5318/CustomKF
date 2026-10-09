"""Hourly pooled mean radial and 12 h / 24 h amplitudes, ERP arm vs E7 (prediction 1 of ECOM7_PROTOCOL.md).

    ... -- Opus_Fork.experiments.ecom7.quick_dip E7_SOLUTION_DIR [DAY FIXTURE ERP_SOLUTION_DIR]
(defaults: Aug 2, the N0 fixture and P1)."""
import json
import os
import sys
from pathlib import Path
import numpy as np

from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation

from Opus_Fork.dip_nga import build
from Opus_Fork.paths import STAGE2


def amplitudes(hourly):
    h = np.arange(24)+0.5
    w = 2*np.pi/24
    a = np.column_stack([np.ones(24), np.cos(w*h), np.sin(w*h), np.cos(2*w*h), np.sin(2*w*h)])
    c, *_ = np.linalg.lstsq(a, np.array(hourly), rcond=None)
    return dict(mean=float(c[0]), amp_24h=float(np.hypot(c[1], c[2])), amp_12h=float(np.hypot(c[3], c[4])))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    e7 = sys.argv[1]
    day, fixture, erp = (sys.argv[2], sys.argv[3], sys.argv[4]) if len(sys.argv) > 4 else         ("2026-08-02", "Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json", "Opus_Fork/runs/20260922T205445Z-fit-P1-erp-31sat/lin2-solve")
    eop, eph = EarthOrientation(STAGE2/"finals2000A.all"), DE440(STAGE2/"de440s.bsp")
    rows, _, _, _ = build(day, fixture, [("B", erp), ("ERP", e7)], eop, eph)
    hours = np.array([r["hour"] for r in rows])
    out = {}
    for label, key in (("ERP-arm", "B"), ("E7", "ERP"), ("NGA", "NGA")):
        rad = np.array([r[key][0] for r in rows])*100
        hourly = [float(rad[(hours >= h) & (hours < h+1)].mean()) for h in range(24)]
        out[label] = dict(amplitudes(hourly), hourly=hourly)
        print(label, {k: round(v, 2) for k, v in out[label].items() if k != "hourly"}, " ".join(f"{x:+.1f}" for x in hourly), flush=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"quick_dip.json").write_text(json.dumps(out, indent=1)+"\n")


if __name__ == "__main__":
    main()
