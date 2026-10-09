"""Measures of `results/SENSITIVITY_PROTOCOL.md` for the sensitivity arms against SD-3 on 2026-08-03.

    ... -- Opus_Fork.experiments.sensitivity.analyze

For each complete `*-fit-S-<name>-3` campaign, using `dip_nga.build` with sub-daily-aware scoring (`sd_scoring`):
- hourly pooled radial and per-epoch Helmert scale against IGS final, for the arm, SD-3 and NGA;
- 12 h / 24 h amplitude and UT phase;
- correlation of the arm's hourly scale series with SD-3's, and with the mean of the SD arms on Aug 2, 4 and 7
  (`results/nga_dist_sd.json`: the day-repeating pattern);
- full-day URE and R/A/C from the same samples.
Writes `sensitivity_analysis.json` (run folder and results/).
"""
import json
import os
from pathlib import Path
import numpy as np

from Opus_Fork.experiments.subdaily import sd_scoring

R = "Opus_Fork/runs/"
FIXTURE = R+"20260922T225652Z-prepare-2026-08-03/fixture.json"
SD3 = R+"20260925T215927Z-fit-SD-3-25st/lin2-solve"
DAY = "2026-08-03"


def harm(y):
    h = np.arange(24)+0.5
    w = 2*np.pi/24
    a = np.column_stack([np.ones(24), np.cos(w*h), np.sin(w*h), np.cos(2*w*h), np.sin(2*w*h)])
    c, *_ = np.linalg.lstsq(a, np.asarray(y, dtype=float), rcond=None)
    return dict(mean=float(c[0]), amp12=float(np.hypot(c[3], c[4])), peak12_ut=float((np.degrees(np.arctan2(c[4], c[3])) % 360)/30),
                amp24=float(np.hypot(c[1], c[2])), peak24_ut=float((np.degrees(np.arctan2(c[2], c[1])) % 360)/15))


def hourly(rows, helmert, arm):
    hours = np.array([r["hour"] for r in rows])
    rad = np.array([r[arm][0] for r in rows])*100
    radial = [float(rad[(hours >= h) & (hours < h+1)].mean()) for h in range(24)]
    sc = helmert[arm]
    ep = sorted(sc)
    ep_h = np.array([(ns-rows[0]["ns"]+rows[0]["hour"]*3600e9)/3600e9 for ns in ep])
    s = np.array([sc[ns]["scale_ppb"] for ns in ep])
    scale = [float(s[(ep_h >= h) & (ep_h < h+1)].mean()) for h in range(24)]
    return radial, scale


def scores(rows, arm):
    rac = np.array([r[arm] for r in rows])
    ure = np.sqrt((0.98*rac[:, 0])**2+(rac[:, 1]**2+rac[:, 2]**2)/49)
    return dict(ure_cm=float(np.sqrt(np.mean(ure**2)))*100, rms_rac_cm=(np.sqrt(np.mean(rac**2, 0))*100).tolist(),
                rms_3d_cm=float(np.sqrt(np.mean(np.sum(rac**2, 1))))*100)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    sd_scoring.install()
    from customkf.ephemeris import DE440
    from customkf.frames import EarthOrientation
    from Opus_Fork import dip_nga
    from Opus_Fork.paths import STAGE2, RESULTS, ROOT
    eop, eph = EarthOrientation(STAGE2/"finals2000A.all"), DE440(STAGE2/"de440s.bsp")
    pattern_src = json.loads((RESULTS/"nga_dist_sd.json").read_text())["part_a_midday_dip"]
    others = np.mean([pattern_src[d]["helmert_scale_ppb_hourly"]["ERP"] for d in ("2026-08-02", "2026-08-04", "2026-08-07")], axis=0)
    report = dict(status="diagnostic_not_accuracy_acceptance", day=DAY, comparator=SD3, arms={})
    for name in ("nopcv", "cut15", "wet1h"):
        runs = sorted((ROOT/"Opus_Fork"/"runs").glob(f"*-fit-S-{name}-3"), reverse=True)
        done = [f for f in runs if json.loads((f/"validation.json").read_text())["status"].startswith("long_fit_complete")]
        if not done:
            print(name, "not complete", flush=True)
            continue
        v = json.loads((done[0]/"validation.json").read_text())
        arm_path = (done[0]/v["final"]).relative_to(ROOT).as_posix()
        rows, helmert, prov, _ = dip_nga.build(DAY, FIXTURE, [("B", SD3), ("ERP", arm_path)], eop, eph)
        entry = dict(campaign=done[0].name, final=v["final"], linearizations=len(v["linearizations"]), samples=len(rows))
        series = {}
        for label, arm in (("SD3", "B"), ("arm", "ERP"), ("NGA", "NGA")):
            radial, scale = hourly(rows, helmert, arm)
            series[label] = scale
            entry[label] = dict(scores(rows, arm), radial=harm(radial), scale=harm(scale), hourly_scale_ppb=scale)
        entry["corr_scale_arm_vs_SD3"] = float(np.corrcoef(series["arm"], series["SD3"])[0, 1])
        entry["corr_scale_arm_vs_other_days_mean"] = float(np.corrcoef(series["arm"], others)[0, 1])
        entry["corr_scale_SD3_vs_other_days_mean"] = float(np.corrcoef(series["SD3"], others)[0, 1])
        entry["scale12_change_pct"] = 100*(entry["arm"]["scale"]["amp12"]/entry["SD3"]["scale"]["amp12"]-1)
        report["arms"][name] = entry
        a, s = entry["arm"], entry["SD3"]
        print(f"{name}: URE {s['ure_cm']:.3f} -> {a['ure_cm']:.3f} | R/A/C {np.round(s['rms_rac_cm'],2)} -> {np.round(a['rms_rac_cm'],2)} | "
              f"scale 12h {s['scale']['amp12']:.3f} -> {a['scale']['amp12']:.3f} ppb ({entry['scale12_change_pct']:+.0f}%) "
              f"peak {s['scale']['peak12_ut']:.1f} -> {a['scale']['peak12_ut']:.1f} h | 24h {s['scale']['amp24']:.3f} -> {a['scale']['amp24']:.3f} | "
              f"r(arm,SD3) {entry['corr_scale_arm_vs_SD3']:+.2f}, r(arm,other days) {entry['corr_scale_arm_vs_other_days_mean']:+.2f} "
              f"(SD3 {entry['corr_scale_SD3_vs_other_days_mean']:+.2f}) | mean scale {s['scale']['mean']:+.3f} -> {a['scale']['mean']:+.3f}", flush=True)
    text = json.dumps(report, indent=1)+"\n"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"sensitivity_analysis.json").write_text(text)
    (RESULTS/"sensitivity_analysis.json").write_text(text)


if __name__ == "__main__":
    main()
