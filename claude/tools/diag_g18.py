"""Guarded, evaluator-side diagnostic of the Stage 5b G18 outlier (Claude support work).

Reads the immutable Stage 5b completion archive plus the pinned IGS rapid SP3 that
the separate evaluator already uses. Never feeds anything back into estimation,
writes nothing outside the guard's run folder.

Run from E:\\pythontests\\customKF (no nesting, one guarded job at a time):
    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.diag_g18
"""
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT, DATA as DYN, sha
from customkf.prepare_stage3 import DATA
from customkf.stage5_pilot import ORIGIN
from customkf.frames import FrameEpoch, EarthOrientation
from customkf.precise import PreciseProducts
from customkf.sp3 import read_sp3
from customkf.comparison import rac_difference

CAMPAIGN = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
FOCUS = {"eight-long": ["G18", "G22", "G24"], "expanded-long": ["G18", "G16", "G29", "G25"]}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    campaign = json.loads((CAMPAIGN / "validation.json").read_text())
    epoch = FrameEpoch(ORIGIN, EarthOrientation(DYN / "finals2000A.all"))
    reference = DATA / "IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
    pin = next(f["sha256"] for f in json.loads((DATA / "manifest.json").read_text())["files"]
               if f["path"] == reference.relative_to(ROOT).as_posix())
    if sha(reference) != pin:
        raise ValueError("Reference input changed")
    precise = PreciseProducts([reference], [], ORIGIN, epoch.eop)
    raw = read_sp3(reference)
    out = {"campaign": str(CAMPAIGN), "reference_sha256": pin, "cases": {}}

    for case, focus in FOCUS.items():
        folder = CAMPAIGN / campaign["final_steps"][case]
        fit = np.load(folder / "solution.npz")
        initial = np.load(CAMPAIGN / (case + "-prepare") / "initial.npz")
        fixture = json.loads((CAMPAIGN / (case + "-prepare") / "fixture.json").read_text())
        rows = fixture["rows"]
        sats = [str(s) for s in fit["satellites"]]
        times = [float(t) for t in fit["times_s"]]
        tindex = {round(t): k for k, t in enumerate(times)}
        names = [str(n) for n in fit["names"]]
        cov = fit["retained_covariance"]
        report = {"formal_position_sigma_m": {}, "satellites": {}}

        # Formal (pre-step linearization, diagnostic-only) initial-position sigma.
        for s in sats:
            k = names.index(f"orbit:{s}:0")
            if k + 3 <= cov.shape[0]:
                report["formal_position_sigma_m"][s] = float(np.sqrt(np.trace(cov[k:k + 3, k:k + 3])))

        # Residual labels in the evaluator's exact order.
        counts = defaultdict(int)
        for r in rows:
            counts[r["arc"]] += 1
        labels = []
        for ei in range(fixture["context"]["epoch_count"]):
            for r in rows:
                if r["epoch"] != ei:
                    continue
                for kind in range(2 if counts[r["arc"]] >= 3 else 1):
                    labels.append((r, "phase" if kind else "code"))
        if len(labels) != len(fit["residual_m"]):
            raise ValueError("Residual label mismatch")

        for sat in focus:
            si = sats.index(sat)
            per_epoch = []
            for ti, t in enumerate(times):
                sample = raw.samples.get((ORIGIN + int(round(t * 1e9)), sat))
                entry = {"t_s": t}
                if sample is not None and sample.xyz_m is not None and not sample.maneuver and not sample.orbit_predicted:
                    r_ref = epoch.celestial_to_terrestrial(t).T @ sample.xyz_m
                    v_ref = precise.state(sat, t)[3:]
                    entry["fit_rac_m"] = [float(x) for x in rac_difference(r_ref, fit["states"][si, ti, :3], v_ref)]
                    entry["initial_rac_m"] = [float(x) for x in rac_difference(r_ref, initial["states"][si, ti, :3], v_ref)]
                per_epoch.append(entry)

            links = defaultdict(list)
            for k, (r, kind) in enumerate(labels):
                if r["satellite"] != sat:
                    continue
                ti = tindex.get(round(r["time_s"]))
                elev = None
                if ti is not None:
                    sat_ecef = epoch.celestial_to_terrestrial(times[ti]) @ fit["states"][si, ti, :3]
                    rx = np.asarray(r["receiver_xyz"], float)
                    los = sat_ecef - rx
                    elev = float(np.degrees(np.arcsin(los @ rx / (np.linalg.norm(los) * np.linalg.norm(rx)))))
                links[r["station"]].append({"epoch": r["epoch"], "kind": kind, "arc": r["arc"],
                                            "residual_m": float(fit["residual_m"][k]),
                                            "normalized": float(fit["residual_m"][k] / fit["sigma_m"][k]),
                                            "elevation_deg": elev})
            stations = {}
            for st, v in links.items():
                ph = [x for x in v if x["kind"] == "phase"]
                cd = [x for x in v if x["kind"] == "code"]
                el = [x["elevation_deg"] for x in v if x["elevation_deg"] is not None]
                stations[st] = {"epochs": sorted({x["epoch"] for x in v}),
                                "arcs": sorted({x["arc"] for x in v}),
                                "elevation_deg_min_max": [min(el), max(el)] if el else None,
                                "code_rms_m": float(np.sqrt(np.mean([x["residual_m"] ** 2 for x in cd]))) if cd else None,
                                "phase_rms_mm": float(1e3 * np.sqrt(np.mean([x["residual_m"] ** 2 for x in ph]))) if ph else None,
                                "max_abs_normalized": float(max(abs(x["normalized"]) for x in v))}
            report["satellites"][sat] = {"per_epoch": per_epoch, "stations": stations}
        out["cases"][case] = report

    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "g18_diagnostic.json").write_text(json.dumps(out, indent=2) + "\n")

    for case, rep in out["cases"].items():
        sig = rep["formal_position_sigma_m"]
        med = float(np.median(list(sig.values()))) if sig else float("nan")
        print(f"=== {case}: median formal initial-position sigma {med:.2f} m")
        for sat, info in rep["satellites"].items():
            print(f"  {sat}: formal sigma {sig.get(sat, float('nan')):.2f} m")
            for st, s in info["stations"].items():
                print(f"    {st}: epochs {s['epochs'][0]}-{s['epochs'][-1]} (n={len(s['epochs'])}) arcs={len(s['arcs'])} "
                      f"elev={s['elevation_deg_min_max']} code={s['code_rms_m']} phase_mm={s['phase_rms_mm']} max|norm|={s['max_abs_normalized']:.2f}")
            for e in info["per_epoch"]:
                if "fit_rac_m" in e:
                    f = e["fit_rac_m"]
                    print(f"    t={e['t_s']:7.0f}s fit RAC=[{f[0]:8.2f} {f[1]:8.2f} {f[2]:8.2f}] |3D|={np.linalg.norm(f):8.2f}  initial |3D|={np.linalg.norm(e['initial_rac_m']):.2f}")


if __name__ == "__main__":
    main()
