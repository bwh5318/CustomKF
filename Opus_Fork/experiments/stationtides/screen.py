"""Pre-screen: would IERS station tide models change the POD's network scale the way the residual swing looks?

    ... -- Opus_Fork.experiments.stationtides.screen

For each POD day's 25 stations, every 15 min, compute the displacement difference between the IERS models and those
baked into the fixtures (`customkf.station_models`, plain daily EOP):

- solid: `Opus_Fork.station_tides.dehant` (IERS DEHANTTIDEINEL) minus `customkf.station_models.solid_displacement`;
- OTL nodal: `Opus_Fork.station_tides.ocean_loading_nodal` minus `customkf.station_models.ocean_loading`.

Each epoch's network difference gets a 7-parameter Helmert fit (translation, rotation, scale). The hourly network scale
(ppb) is then compared with the sub-daily-EOP POD arms' residual scale against IGS final (`results/nga_dist_sd.json`,
arm "ERP"): correlation, regression and 12 h / 24 h harmonics. A model difference can only explain the residual if it has
comparable size (0.16–0.36 ppb at 12 h) and correlates the same way on every day. No fit; no fixture is modified.
"""
import json
import os
from pathlib import Path
import numpy as np
import erfa

from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation, FrameEpoch
from customkf.measurement import enu_matrix
from customkf.prepare_stage3 import DATA
from customkf.station_models import solid_displacement, ocean_loading, read_loading

from Opus_Fork import station_tides
from Opus_Fork.paths import STAGE2, RESULTS, ROOT

FIXTURES = {
    "2026-08-02": "Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json",
    "2026-08-03": "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03/fixture.json",
    "2026-08-04": "Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04/fixture.json",
    "2026-08-05": "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05/fixture.json",
    "2026-08-07": "runs/20260920T155655Z-7b703635/fixture.json",
}


def helmert_scale(x, d):
    rows, rhs = [], []
    for xi, di in zip(x, d):
        skew = np.array([[0, -xi[2], xi[1]], [xi[2], 0, -xi[0]], [-xi[1], xi[0], 0]])
        rows.append(np.hstack([np.eye(3), -skew, xi[:, None]]))
        rhs.append(di)
    c, *_ = np.linalg.lstsq(np.vstack(rows), np.concatenate(rhs), rcond=None)
    return c[6]*1e9  # ppb


def harm(y):
    h = np.arange(24)+0.5
    y = np.asarray(y, dtype=float)
    w = 2*np.pi/24
    a = np.column_stack([np.ones(24), np.cos(w*h), np.sin(w*h), np.cos(2*w*h), np.sin(2*w*h)])
    c, *_ = np.linalg.lstsq(a, y, rcond=None)
    return dict(amp12=float(np.hypot(c[3], c[4])), peak12=float((np.degrees(np.arctan2(c[4], c[3])) % 360)/30),
                amp24=float(np.hypot(c[1], c[2])), peak24=float((np.degrees(np.arctan2(c[2], c[1])) % 360)/15))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    station_tides.self_test()
    eop, eph = EarthOrientation(STAGE2/"finals2000A.all"), DE440(STAGE2/"de440s.bsp")
    eop.subdaily = None
    observed = json.loads((RESULTS/"nga_dist_sd.json").read_text())["part_a_midday_dip"]
    report = {}
    for day, fixture in FIXTURES.items():
        context = json.loads((ROOT/fixture).read_text())["context"]
        epoch = FrameEpoch(context["origin_ns"], eop)
        names = sorted(context["stations"])
        xyz = np.array([context["stations"][s]["fixed_xyz"] for s in names], dtype=float)
        loading = [read_loading(DATA/"FES2014b.BLQ", s) for s in names]
        enus = [enu_matrix(x) for x in xyz]
        series = {k: [] for k in ("solid", "otl", "both")}
        mean_up = {k: [] for k in ("solid", "otl")}
        for t in np.arange(0., 86400., 900.):
            rot = epoch.celestial_to_terrestrial(t)
            sun, moon = eph.sun_moon_m(epoch.tdb_seconds(t))
            sun, moon = rot@sun, rot@moon
            tt1, tt2, u1, u2, *_ = epoch.times(t)
            gmst = erfa.gmst06(u1, u2, tt1, tt2)
            utc1, utc2 = erfa.taiutc(*erfa.tttai(tt1, tt2))
            y, m, d, frac = erfa.jd2cal(utc1, utc2)
            mjd = (utc1-2400000.5)+utc2
            ds, do = [], []
            for x, enu, blq in zip(xyz, enus, loading):
                ds.append(station_tides.dehant(x, sun, moon, y, m, d, frac*24.)-solid_displacement(x, sun, moon, gmst))
                do.append(enu.T@(station_tides.ocean_loading_nodal(mjd, blq)-ocean_loading(mjd, blq)))
            ds, do = np.array(ds), np.array(do)
            series["solid"].append(helmert_scale(xyz, ds))
            series["otl"].append(helmert_scale(xyz, do))
            series["both"].append(helmert_scale(xyz, ds+do))
            up = xyz/np.linalg.norm(xyz, axis=1)[:, None]
            mean_up["solid"].append(float(np.mean(np.sum(ds*up, 1)))*1000)
            mean_up["otl"].append(float(np.mean(np.sum(do*up, 1)))*1000)
        hourly = {k: np.array(v).reshape(24, 4).mean(1) for k, v in series.items()}
        obs = np.array(observed[day]["helmert_scale_ppb_hourly"]["ERP"], dtype=float)
        entry = dict(observed_sd_residual=dict(harm(obs), hourly=obs.tolist()))
        for k, v in hourly.items():
            r = float(np.corrcoef(v, obs)[0, 1])
            slope = float(np.dot(v-v.mean(), obs-obs.mean())/np.dot(v-v.mean(), v-v.mean()))
            entry[k] = dict(harm(v), rms_ppb=float(np.std(v)), corr_with_observed=r, regression_observed_on_model=slope,
                            hourly=v.tolist())
        entry["network_mean_up_mm_rms"] = {k: float(np.std(v)) for k, v in mean_up.items()}
        report[day] = entry
        o = entry["observed_sd_residual"]
        print(f"{day} observed SD residual: 12h {o['amp12']:.3f} ppb @{o['peak12']:4.1f}h, 24h {o['amp24']:.3f} @{o['peak24']:4.1f}h", flush=True)
        for k in ("solid", "otl", "both"):
            e = entry[k]
            print(f"    {k:5s}: 12h {e['amp12']:.3f} ppb @{e['peak12']:4.1f}h, 24h {e['amp24']:.3f} @{e['peak24']:4.1f}h, rms {e['rms_ppb']:.3f} | "
                  f"corr {e['corr_with_observed']:+.2f}, slope {e['regression_observed_on_model']:+.2f}", flush=True)
        print(f"    network-mean up (mm, rms): solid {entry['network_mean_up_mm_rms']['solid']:.2f}, otl {entry['network_mean_up_mm_rms']['otl']:.2f}", flush=True)
    text = json.dumps(report, indent=1)+"\n"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"stationtide_screen.json").write_text(text)
    (RESULTS/"stationtide_screen.json").write_text(text)


if __name__ == "__main__":
    main()
