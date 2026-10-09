"""Smoke check of the sub-daily-EOP worker install (no fit). Run under the guard:

    ... -- Opus_Fork.experiments.subdaily.check_sd FIXTURE_DIR

Asserts that after `sdeop.install()` (a) the fixture's observation-side Earth rotation and the dynamics'
Environment rotation both differ from the plain daily-EOP rotation by the ORTHO_EOP angles, (b) the binding
workers will record declares the sub-daily EOP, and (c) the scoring hook maps positions by the same rotation.
"""
import os
import sys
from pathlib import Path
import numpy as np

os.environ.setdefault("OPUSFORK_SD_VARIANT", "erp+thrust+iiia2600+sdeop")


def angle_uas(a, b):
    # Small-angle rotation vector from the antisymmetric part (arccos of the trace underflows below ~1e-8 rad).
    d = a@b.T
    w = np.array([d[2, 1]-d[1, 2], d[0, 2]-d[2, 0], d[1, 0]-d[0, 1]])/2
    return np.degrees(np.linalg.norm(w))*3.6e9


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    fixture = Path(sys.argv[1])/"fixture.json"
    from Opus_Fork import sdeop, subdaily_eop, ngv_pilot, ngv_traj_cache
    from customkf.frames import EarthOrientation, FrameEpoch
    from customkf.prepare_stage2 import DATA as DYN
    sdeop.install()
    assert ngv_pilot.model_binding() == sdeop.binding() == ngv_traj_cache.model_binding()
    assert sdeop.binding()["subdaily_eop"] and sdeop.binding()["variant"] == os.environ["OPUSFORK_SD_VARIANT"]
    from claude.tools.dated_fixture import restore
    context, rows, seeds = restore(fixture)
    plain_eop = EarthOrientation(DYN/"finals2000A.all")
    plain_eop.subdaily = None  # instance override of the class-level hook sdeop.install() set
    plain = FrameEpoch(context["origin_ns"], plain_eop)
    env = context["model"].environment
    for t in (0., 21600., 43200., 64800.):
        obs = context["epoch"].celestial_to_terrestrial(t)
        dyn = env.rotation(t)
        ref = plain.celestial_to_terrestrial(t)
        mjd = 44244.+(context["origin_ns"]/1e9+t)/86400.  # GPS days -> MJD (UTC offset irrelevant here)
        dx, dy, dut1 = subdaily_eop.ocean_tidal_eop(mjd)
        expected = np.sqrt(dx**2+dy**2+(dut1*15.041)**2)
        print(f"t={t/3600:4.1f} h  obs-vs-plain {angle_uas(obs, ref):7.1f} uas  dyn-vs-plain {angle_uas(dyn, ref):7.1f} uas  "
              f"ORTHO_EOP magnitude {expected:7.1f} uas", flush=True)
        assert abs(angle_uas(obs, ref)-expected) < 0.05*expected+5 and abs(angle_uas(dyn, obs)) < 5
    from Opus_Fork.experiments.subdaily.sd_scoring import SubdailyFit
    print("binding", sdeop.binding())
    print("SMOKE OK", flush=True)


if __name__ == "__main__":
    main()
