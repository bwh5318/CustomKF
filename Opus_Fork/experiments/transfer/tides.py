"""Worker 1: station-tide model differences at every row time of the Aug 3 fixture (plain daily EOP, as the fixture).

    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.experiments.transfer.tides

For each station and each row time t (10 + 600 k s):
- solid: `Opus_Fork.station_tides.dehant` (IERS DEHANTTIDEINEL) − `customkf.station_models.solid_displacement`;
- otl:   ENU→ECEF of `station_tides.ocean_loading_nodal` − `customkf.station_models.ocean_loading`;
exactly the arithmetic of `experiments/stationtides/screen.py`. Also checks that the fixture's `receiver_xyz` is
reproduced by `station_displacement` with this EOP/ephemeris/BLQ (so "the fixture's model" is what is differenced).
No sub-daily EOP is installed in this process. Writes `tides.npz` and `step.json`.
"""
import json
import time
import numpy as np
import erfa

from Opus_Fork.experiments.transfer.common import FIXTURE, run_dir, check_protocol, sha, write_json


def main():
    folder = run_dir()
    check_protocol()
    start = time.perf_counter()
    from claude.tools.dated_fixture import restore
    from customkf.measurement import enu_matrix
    from customkf.prepare_stage3 import DATA
    from customkf.station_models import solid_displacement, ocean_loading, read_loading, station_displacement
    from Opus_Fork import station_tides
    station_tides.self_test()
    context, rows, _ = restore(FIXTURE)
    epoch, eph = context["epoch"], context["ephemeris"]
    assert getattr(epoch.eop, "subdaily", None) is None, "plain EOP required"
    stations = sorted(context["stations"])
    times = np.array(sorted({float(r["time_s"]) for r in rows}))
    assert np.allclose((times-10) % 600, 0)
    blq_path = DATA/"FES2014b.BLQ"
    solid = np.zeros((len(stations), len(times), 3))
    otl = np.zeros_like(solid)
    fixture_disp = np.zeros_like(solid)
    xyz = {s: np.array(context["stations"][s]["fixed_xyz"], dtype=float) for s in stations}
    loading = {s: read_loading(blq_path, s) for s in stations}
    for ti, t in enumerate(times):
        rot = epoch.celestial_to_terrestrial(t)
        sun, moon = eph.sun_moon_m(epoch.tdb_seconds(t))
        sun, moon = rot@sun, rot@moon
        tt1, tt2, u1, u2, *_ = epoch.times(t)
        gmst = erfa.gmst06(u1, u2, tt1, tt2)
        utc1, utc2 = erfa.taiutc(*erfa.tttai(tt1, tt2))
        y, m, d, frac = erfa.jd2cal(utc1, utc2)
        mjd = (utc1-2400000.5)+utc2
        for si, s in enumerate(stations):
            x = xyz[s]
            solid[si, ti] = station_tides.dehant(x, sun, moon, y, m, d, frac*24.)-solid_displacement(x, sun, moon, gmst)
            otl[si, ti] = enu_matrix(x).T@(station_tides.ocean_loading_nodal(mjd, loading[s])-ocean_loading(mjd, loading[s]))
            fixture_disp[si, ti] = station_displacement(x, t, epoch, eph, loading[s])
    # Fixture self-check: receiver_xyz = fixed + eccentricity + station_displacement(fixed, t) for every row.
    ecc = {s: enu_matrix(xyz[s]).T@np.array(context["stations"][s]["header"]["antenna_hen"])[[1, 2, 0]] for s in stations}
    s_index = {s: i for i, s in enumerate(stations)}
    t_index = {t: i for i, t in enumerate(times)}
    worst = 0.
    for r in rows:
        si, ti = s_index[r["station"]], t_index[float(r["time_s"])]
        worst = max(worst, float(np.max(np.abs(r["receiver_xyz"]-(xyz[r["station"]]+ecc[r["station"]]+fixture_disp[si, ti])))))
    up = np.array([enu_matrix(xyz[s])[2] for s in stations])
    np.savez_compressed(folder/"tides.npz", stations=np.array(stations), times_s=times, solid=solid, otl=otl,
                        fixture_displacement=fixture_disp, up=up)
    record = dict(status="tides_ready", fixture_sha256=sha(FIXTURE), blq=str(blq_path), blq_sha256=sha(blq_path),
                  stations=len(stations), times=len(times), rows=len(rows),
                  fixture_receiver_xyz_max_abs_diff_m=worst,
                  solid_up_rms_mm=float(np.sqrt(np.mean(np.sum(solid*up[:, None, :], -1)**2))*1000),
                  otl_up_rms_mm=float(np.sqrt(np.mean(np.sum(otl*up[:, None, :], -1)**2))*1000),
                  solid_max_mm=float(np.max(np.linalg.norm(solid, axis=-1))*1000),
                  otl_max_mm=float(np.max(np.linalg.norm(otl, axis=-1))*1000),
                  tides_sha256=sha(folder/"tides.npz"), seconds=time.perf_counter()-start)
    write_json(folder/"step.json", record)
    print(json.dumps(record, indent=1), flush=True)


if __name__ == "__main__":
    main()
