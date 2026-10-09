"""Per-station size of the IERS-vs-fixture station tide differences on Aug 2 (companion to screen.py).

    ... -- Opus_Fork.experiments.stationtides.per_station
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
from Opus_Fork.paths import STAGE2, ROOT


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    eop, eph = EarthOrientation(STAGE2/"finals2000A.all"), DE440(STAGE2/"de440s.bsp")
    context = json.loads((ROOT/"Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json").read_text())["context"]
    epoch = FrameEpoch(context["origin_ns"], eop)
    out = {}
    for s in sorted(context["stations"]):
        x = np.array(context["stations"][s]["fixed_xyz"], dtype=float)
        enu, blq = enu_matrix(x), read_loading(DATA/"FES2014b.BLQ", s)
        ds, do = [], []
        for t in np.arange(0., 86400., 900.):
            rot = epoch.celestial_to_terrestrial(t)
            sun, moon = (rot@v for v in eph.sun_moon_m(epoch.tdb_seconds(t)))
            tt1, tt2, u1, u2, *_ = epoch.times(t)
            utc1, utc2 = erfa.taiutc(*erfa.tttai(tt1, tt2))
            y, m, d, frac = erfa.jd2cal(utc1, utc2)
            mjd = (utc1-2400000.5)+utc2
            ds.append(enu@(station_tides.dehant(x, sun, moon, y, m, d, frac*24.)-solid_displacement(x, sun, moon, erfa.gmst06(u1, u2, tt1, tt2))))
            do.append(station_tides.ocean_loading_nodal(mjd, blq)-ocean_loading(mjd, blq))
        ds, do = np.array(ds)*1000, np.array(do)*1000
        out[s] = dict(solid_up_max_mm=float(abs(ds[:, 2]).max()), solid_horiz_max_mm=float(np.hypot(ds[:, 0], ds[:, 1]).max()),
                      otl_up_max_mm=float(abs(do[:, 2]).max()), otl_horiz_max_mm=float(np.hypot(do[:, 0], do[:, 1]).max()))
        print(s, " ".join(f"{k} {v:.2f}" for k, v in out[s].items()), flush=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"per_station.json").write_text(json.dumps(out, indent=1)+"\n")


if __name__ == "__main__":
    main()
