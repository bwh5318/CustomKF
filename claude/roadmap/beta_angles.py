"""Guarded eclipse/beta-angle inventory for bench design (roadmap step 4). Reference products only.

    python -m customkf.guard -- claude.roadmap.beta_angles --day 2026-08-02 --start 00:00 --end 23:45

For each GPS satellite in the IGS rapid SP3: Sun beta angle (angle between the Sun direction and the
orbital plane) at the window start, and the fraction of 5-minute samples inside Earth's penumbra/umbra
using the same conical shadow function as the force model. Eclipse season for GPS is |beta| < ~13.9 deg.
Descriptive only; never an estimator input or a satellite-selection rule for scoring.
"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import DATA as DYN
from customkf.sp3 import epoch_tag
from customkf.ephemeris import DE440
from customkf.orbit_forces import shadow_fraction
from claude.roadmap.common import DatedReference, satellite_blocks, block_group, write_json


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--start", default="00:00")
    parser.add_argument("--end", default="23:45")
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    date = datetime.strptime(args.day, "%Y-%m-%d")
    midnight = epoch_tag(date.strftime("* %Y %m %d 00 00 00"))
    reference = DatedReference(args.day, midnight)
    ephemeris = DE440(DYN/"de440s.bsp")
    h0, m0 = map(int, args.start.split(":"))
    h1, m1 = map(int, args.end.split(":"))
    times = np.arange(h0*3600+m0*60, h1*3600+m1*60+1, 300.)
    blocks = satellite_blocks(args.day)
    out = {}
    for sat in sorted(reference.precise.orbits):
        if sat not in blocks:
            continue
        try:
            state = reference.precise.state(sat, float(times[0]))
        except ValueError:
            continue
        sun, _ = ephemeris.sun_moon_m(reference.epoch.tdb_seconds(float(times[0])))
        normal = np.cross(state[:3], state[3:])
        normal /= np.linalg.norm(normal)
        beta = float(np.degrees(np.arcsin(np.clip(normal@(sun/np.linalg.norm(sun)), -1, 1))))
        shaded, samples = 0, 0
        for t in times:
            try:
                r = reference.precise.state(sat, float(t))[:3]
            except ValueError:
                continue
            s, _ = ephemeris.sun_moon_m(reference.epoch.tdb_seconds(float(t)))
            samples += 1
            shaded += shadow_fraction(r, s) < 1.
        out[sat] = dict(block=block_group(blocks[sat][0]), svn=blocks[sat][1], beta_deg=beta, eclipse_season=abs(beta) < 13.9,
                        shadow_samples=int(shaded), samples=int(samples))
    report = dict(status="descriptive_eclipse_inventory", day=args.day, window=[args.start, args.end], reference_sha256=reference.sha256,
                  satellites=out, eclipse_season_satellites=sorted(s for s, v in out.items() if v["eclipse_season"]),
                  satellites_entering_shadow=sorted(s for s, v in out.items() if v["shadow_samples"]))
    write_json(folder/"beta_angles.json", report)
    print({k: report[k] for k in ("day", "eclipse_season_satellites", "satellites_entering_shadow")}, flush=True)


if __name__ == "__main__":
    main()
