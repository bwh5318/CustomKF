"""Is the Aug 2-5 12 h common-height swing carried by the satellites that Aug 7's fixture rejects?

Diagnostic after the ECOM7P held-out failure on Aug 7 (results/ECOM7P_HOLDOUT_RESULTS.md). The Aug 7 fixture
rejects G03, G05, G13, G15, G18 and G26; the Aug 2-5 fixtures reject only G13. On Aug 2-5 the ECOM5 ERP arms'
pooled hourly mean radial has a 12 h amplitude of 1.74-1.95 cm; on Aug 7 it is 0.47. This recomputes the amplitude on
each day with all satellites and without the five extra Aug 7 rejections. No fit; existing solutions only.

    ... -- Opus_Fork.experiments.ecom7.swing_subset
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation

from Opus_Fork.dip_nga import build
from Opus_Fork.paths import STAGE2
from Opus_Fork.experiments.ecom7.quick_dip import amplitudes

DROP = {"G03", "G05", "G15", "G18", "G26"}
CASES = [  # day, fixture, ECOM5 ERP arm, E7P arm
    ("2026-08-02", "Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json",
     "Opus_Fork/runs/20260922T205445Z-fit-P1-erp-31sat/lin2-solve", "Opus_Fork/runs/20260925T014057Z-fit-E7P-2-25st/lin2-solve"),
    ("2026-08-03", "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03/fixture.json",
     "Opus_Fork/runs/20260923T000354Z-fit-P2-3-25st/lin2-solve", "Opus_Fork/runs/20260925T025949Z-fit-E7P-3-25st/lin2-solve"),
    ("2026-08-04", "Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04/fixture.json",
     "Opus_Fork/runs/20260923T200747Z-fit-P2-4-25st/lin2-solve", "Opus_Fork/runs/20260925T142121Z-fit-E7P-4-25st/lin2-solve"),
    ("2026-08-05", "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05/fixture.json",
     "Opus_Fork/runs/20260923T230743Z-fit-P2-5-25st/lin3-solve", "Opus_Fork/runs/20260925T153204Z-fit-E7P-5-25st/lin2-solve"),
    ("2026-08-07", "runs/20260920T155655Z-7b703635/fixture.json",
     "Opus_Fork/runs/20260922T215245Z-fit-R7-erp-aug7-25st/lin2-solve", "Opus_Fork/runs/20260925T164050Z-fit-E7P-7-25st/lin2-solve"),
]


def amp12(rows, key, keep):
    rows = [r for r in rows if keep(r["sat"])]
    if not rows:
        return None, 0
    hours = np.array([r["hour"] for r in rows])
    rad = np.array([r[key][0] for r in rows])*100
    hourly = [float(rad[(hours >= h) & (hours < h+1)].mean()) for h in range(24)]
    return amplitudes(hourly)["amp_12h"], len({r["sat"] for r in rows})


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    eop, eph = EarthOrientation(STAGE2/"finals2000A.all"), DE440(STAGE2/"de440s.bsp")
    out = {}
    for day, fixture, erp, e7p in CASES:
        rows, _, _, _ = build(day, fixture, [("B", erp), ("ERP", e7p)], eop, eph)
        res = {}
        for label, key in (("ECOM5", "B"), ("E7P", "ERP"), ("NGA", "NGA")):
            a_all, n_all = amp12(rows, key, lambda s: True)
            a_sub, n_sub = amp12(rows, key, lambda s: s not in DROP)
            a_only, n_only = amp12(rows, key, lambda s: s in DROP)
            res[label] = dict(all=round(a_all, 2), n_all=n_all, without_drop=round(a_sub, 2), n_without=n_sub,
                              drop_only=None if a_only is None else round(a_only, 2), n_drop=n_only)
        out[day] = res
        print(day, json.dumps(res), flush=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"swing_subset.json").write_text(json.dumps(out, indent=1)+"\n")


if __name__ == "__main__":
    main()
