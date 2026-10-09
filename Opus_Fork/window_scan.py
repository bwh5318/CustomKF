"""Where in the day does our 24 h fit lose to NGA?

    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.window_scan

G21 and G27 both track IGS final well for roughly two thirds of the arc and then
run away along-track. If the deficit is concentrated at the arc end, the fix is
arc geometry and late ambiguity handling, not force modelling. This scores our fit
and NGA on identical satellite-epochs over a sliding set of windows, always on the
27 satellites our 24 h fixture retains, so the two products are strictly comparable.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.frames import EarthOrientation
from customkf.prepare_stage2 import sha

from .baseline import BEST_FIXTURE, BEST_SOLUTION, MIDNIGHT, Fit, OnOrigin
from .paths import ROOT, STAGE0, STAGE2, RESULTS
from .score import Declared, Product, pooled, rac

WINDOWS = [(0, 24), (0, 6), (6, 12), (12, 18), (18, 24), (0, 12), (0, 16), (0, 18), (0, 20), (2, 22), (4, 20)]


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    final_path = STAGE0/"IGS0OPSFIN_20262140000_01D_15M_ORB.SP3"
    reference = Product(final_path, Declared("IGS final", "IGc20", "COM"), MIDNIGHT, eop)
    nga = Product(STAGE0/"nga24300.sp3", Declared("NGA PE", "WGS84", "COM", legacy_a_time_system="GPS"), MIDNIGHT, eop)
    fit = OnOrigin(Fit(BEST_SOLUTION, BEST_FIXTURE, eop), MIDNIGHT)

    keys = sorted(reference.keys() & fit.keys() & nga.keys())
    ours = {k: rac(reference, fit, k[0], (k[1]-MIDNIGHT)/1e9) for k in keys}
    theirs = {k: rac(reference, nga, k[0], (k[1]-MIDNIGHT)/1e9) for k in keys}
    satellites = sorted({s for s, _ in keys})

    report = dict(status="window_scan_diagnostic_not_accuracy_acceptance", day="2026-08-02",
                  satellites=satellites, note="identical satellite-epochs for both products in every window",
                  inputs={"igs_final": sha(final_path), "solution": sha(BEST_SOLUTION)}, windows={})
    print(f"{'window':>9s} {'n':>5s} | {'ours 3D':>8s} {'NGA 3D':>7s} {'ratio':>6s} | "
          f"{'ours URE':>8s} {'NGA URE':>8s} {'ratio':>6s} | {'ours A':>7s} {'NGA A':>6s} | beats NGA")
    print("-"*108)
    for lo, hi in WINDOWS:
        inside = [k for k in keys if lo*3.6e12 <= k[1]-MIDNIGHT <= hi*3.6e12]
        a, b = pooled([ours[k] for k in inside]), pooled([theirs[k] for k in inside])
        drop = []
        for s in satellites:
            sub = [k for k in inside if k[0] == s]
            if pooled([ours[k] for k in sub])["rms_3d_m"] < pooled([theirs[k] for k in sub])["rms_3d_m"]:
                drop.append(s)
        report["windows"][f"{lo:02d}-{hi:02d}"] = dict(window_h=[lo, hi], ours=a, nga=b,
                                                       ratio_3d=a["rms_3d_m"]/b["rms_3d_m"],
                                                       ratio_ure=a["rms_orbit_ure_m"]/b["rms_orbit_ure_m"],
                                                       satellites_we_beat=drop)
        print(f"{lo:3d}-{hi:02d} h {len(inside):7d} | {a['rms_3d_m']*100:7.2f} {b['rms_3d_m']*100:7.2f} "
              f"{a['rms_3d_m']/b['rms_3d_m']:6.3f} | {a['rms_orbit_ure_m']*100:8.2f} {b['rms_orbit_ure_m']*100:8.2f} "
              f"{a['rms_orbit_ure_m']/b['rms_orbit_ure_m']:6.3f} | {a['rms_rac_m'][1]*100:7.2f} {b['rms_rac_m'][1]*100:6.2f} "
              f"| {len(drop):2d}/{len(satellites)}")

    # The same scan with G21 alone withheld, to size its share. Descriptive only:
    # a satellite is never excluded from a reported score on the strength of this.
    print("\nwithout G21 (descriptive; not an exclusion):")
    for lo, hi in ((0, 24), (0, 18)):
        inside = [k for k in keys if lo*3.6e12 <= k[1]-MIDNIGHT <= hi*3.6e12 and k[0] != "G21"]
        a, b = pooled([ours[k] for k in inside]), pooled([theirs[k] for k in inside])
        report["windows"][f"{lo:02d}-{hi:02d}-noG21"] = dict(window_h=[lo, hi], excluded=["G21"], ours=a, nga=b,
                                                             ratio_3d=a["rms_3d_m"]/b["rms_3d_m"])
        print(f"{lo:3d}-{hi:02d} h {len(inside):7d} | {a['rms_3d_m']*100:7.2f} {b['rms_3d_m']*100:7.2f} "
              f"{a['rms_3d_m']/b['rms_3d_m']:6.3f} | {a['rms_orbit_ure_m']*100:8.2f} {b['rms_orbit_ure_m']*100:8.2f} "
              f"{a['rms_orbit_ure_m']/b['rms_orbit_ure_m']:6.3f} | {a['rms_rac_m'][1]*100:7.2f} {b['rms_rac_m'][1]*100:6.2f}")

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"window_scan.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"window_scan.json").write_text(text)
    print("\nWrote "+str(out/"window_scan.json"))


if __name__ == "__main__":
    main()
