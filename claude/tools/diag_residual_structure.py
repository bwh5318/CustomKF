"""Guarded diagnostic: Stage 5b postfit residual structure by station, elevation and time.

Question: are the large and growing KOUR/KOUG phase residuals (9 mm at 55 min ->
15-20 mm at 3 h) elevation-dependent and/or time-dependent, as a too-coarse
two-knot wet-delay basis or low-elevation multipath would predict?
Reads only the immutable Stage 5b archive and pinned EOP; no reference orbits.

Run from E:\\pythontests\\customKF (no nesting, one guarded job at a time):
    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.diag_residual_structure
"""
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT, DATA as DYN
from customkf.stage5_pilot import ORIGIN
from customkf.frames import FrameEpoch, EarthOrientation

CAMPAIGN = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
ELEV_BINS = ((10, 20), (20, 30), (30, 50), (50, 91))


def rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    campaign = json.loads((CAMPAIGN / "validation.json").read_text())
    epoch = FrameEpoch(ORIGIN, EarthOrientation(DYN / "finals2000A.all"))
    out = {}
    top = []
    for case in ("eight-short", "eight-long", "expanded-long"):
        fit = np.load(CAMPAIGN / campaign["final_steps"][case] / "solution.npz")
        fixture = json.loads((CAMPAIGN / (case + "-prepare") / "fixture.json").read_text())
        rows = fixture["rows"]
        ne = fixture["context"]["epoch_count"]
        sats = [str(s) for s in fit["satellites"]]
        times = [float(t) for t in fit["times_s"]]
        tindex = {round(t): k for k, t in enumerate(times)}
        rot = {k: epoch.celestial_to_terrestrial(t) for k, t in enumerate(times)}
        counts = defaultdict(int)
        for r in rows:
            counts[r["arc"]] += 1
        # Residual order copied from evaluate_stage5b.
        k = 0
        acc = defaultdict(lambda: defaultdict(list))
        wet = {}
        for ei in range(ne):
            for r in rows:
                if r["epoch"] != ei:
                    continue
                ti = tindex.get(round(r["time_s"]))
                elev = None
                if ti is not None:
                    sat_ecef = rot[ti] @ fit["states"][sats.index(r["satellite"]), ti, :3]
                    rx = np.asarray(r["receiver_xyz"], float)
                    los = sat_ecef - rx
                    elev = float(np.degrees(np.arcsin(los @ rx / (np.linalg.norm(los) * np.linalg.norm(rx)))))
                third = min(2, 3 * ei // ne)
                # Stage 3 KOUR_INVESTIGATION flagged ~13:30-14:30 GPST on this day.
                # Solve epoch ei is at 12:00 + 300 s * ei, so that is epochs 18-30.
                window = "burstwin" if 18 <= ei <= 30 else "outside"
                for kind in range(2 if counts[r["arc"]] >= 3 else 1):
                    name = "phase" if kind else "code"
                    res = float(fit["residual_m"][k])
                    norm = float(res / fit["sigma_m"][k])
                    st = acc[r["station"]]
                    st[f"{name}:all"].append(res)
                    st[f"{name}:norm"].append(norm)
                    st[f"{name}:third{third}"].append(res)
                    st[f"{name}:{window}"].append(res)
                    if name == "phase" and r["station"] in ("KOUR", "KOUG"):
                        top.append((abs(res), case, r["station"], r["satellite"], ei, res, elev))
                    if elev is not None:
                        for lo, hi in ELEV_BINS:
                            if lo <= elev < hi:
                                st[f"{name}:el{lo}-{hi}"].append(res)
                    k += 1
        if k != len(fit["residual_m"]):
            raise ValueError("Residual label mismatch")
        names = [str(n) for n in fit["names"]]
        for station in acc:
            w = [fit["x"][names.index(f"wet:{station}:{j}")] for j in (0, 1) if f"wet:{station}:{j}" in names]
            wet[station] = [float(v) for v in w]
        summary = {}
        for station, groups in sorted(acc.items()):
            summary[station] = {g: {"n": len(v), "rms": rms(v)} for g, v in sorted(groups.items())}
            summary[station]["wet_increment_m"] = wet.get(station)
        out[case] = summary

    top.sort(reverse=True)
    out["largest_kourou_phase_residuals"] = [
        {"case": c, "station": s, "satellite": sat, "epoch": ei, "gpst": f"{12 + (300 * ei) // 3600:02d}:{((300 * ei) % 3600) // 60:02d}",
         "residual_mm": 1e3 * res, "elevation_deg": el} for _, c, s, sat, ei, res, el in top[:25]]
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "residual_structure.json").write_text(json.dumps(out, indent=2) + "\n")
    for case in ("eight-short", "eight-long", "expanded-long"):
        summary = out[case]
        print(f"=== {case}: phase RMS mm [all | epoch thirds | elevation 10-20/20-30/30-50/50+ | 13:30-14:30 window / outside] | code RMS m | wet increments m")
        for station, g in summary.items():
            def mm(key):
                v = g.get(key, {}).get("rms")
                return f"{1e3 * v:6.1f}" if v is not None else "     -"
            thirds = " ".join(mm(f"phase:third{i}") for i in range(3))
            elevs = " ".join(mm(f"phase:el{lo}-{hi}") for lo, hi in ELEV_BINS)
            wet = g.get("wet_increment_m")
            print(f"  {station}: {mm('phase:all')} | {thirds} | {elevs} | {mm('phase:burstwin')} / {mm('phase:outside')} | code {g['code:all']['rms']:.3f} | wet {[round(x, 3) for x in wet] if wet else None}")
    print("=== largest KOUR/KOUG phase residuals (all cases)")
    for e in out["largest_kourou_phase_residuals"]:
        print(f"  {e['case']:13s} {e['station']} {e['satellite']} epoch {e['epoch']:2d} ({e['gpst']} GPST) {e['residual_mm']:8.1f} mm  elev {e['elevation_deg']:.1f}")


if __name__ == "__main__":
    main()
