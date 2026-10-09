"""Oracle O2 CIP methods (network amendment A4, Astra review 8 Oct 2026).

    C:\\anaconda\\python.exe -m unittest tests.test_oracle_cip_methods -v

- The default series path is unchanged: bitwise equal to the original composition from `erfa.xy06`.
- The opt-in angles path reproduces production (`customkf.frames` + `Opus_Fork.subdaily_eop`) within 1e-12 per matrix
  element, Astra's predeclared diagnostic bound, on all 96 scored epochs of Jul 6, the date with the largest difference.
- The two methods differ by a measured microarcsecond-level amount, so the angles path is not a no-op.
"""
from datetime import datetime
import unittest

import erfa
import numpy as np

from validation.oracle import frame as O

EOP = O.ROOT/"data/stage2/finals2000A.all"
MIDNIGHT = int((datetime(2026, 7, 6)-datetime(1980, 1, 6)).total_seconds())*10**9
EPOCHS = [MIDNIGHT+k*900*10**9 for k in range(96)]
RAD2UAS = 1/O.AS2R*1e6


def original_series(frame, t):
    """The composition before 8 Oct 2026, written out."""
    tt, ut1, _, (xp, yp, _, dx, dy) = frame.times(t)
    x, y = erfa.xy06(*tt)
    x, y = x+dx*1e-3*O.AS2R, y+dy*1e-3*O.AS2R
    bpn = erfa.c2ixys(x, y, erfa.s06(*tt, x, y))
    return erfa.pom00(xp*O.AS2R, yp*O.AS2R, erfa.sp00(*tt))@O._r3(erfa.era00(*ut1))@bpn


def angle_uas(a, b):
    d = a@b.T
    return np.linalg.norm([d[2, 1]-d[1, 2], d[0, 2]-d[2, 0], d[1, 0]-d[0, 1]])/2*RAD2UAS


class CipMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EOP.is_file():
            raise unittest.SkipTest("needs data/stage2/finals2000A.all (run customkf.prepare_stage2)")
        cls.finals = O.Finals(EOP)

    def test_default_series_path_is_unchanged(self):
        for subdaily in (False, True):
            frame = O.Frame(self.finals, subdaily=subdaily)
            self.assertEqual(frame.cip, "series")
            for t in EPOCHS[::7]:
                np.testing.assert_array_equal(frame.rotation(t), original_series(frame, t))

    def test_angles_path_reproduces_production(self):
        from customkf.frames import EarthOrientation, FrameEpoch
        from Opus_Fork import subdaily_eop
        origin = MIDNIGHT-10*10**9
        for subdaily in (False, True):
            production = FrameEpoch(origin, (subdaily_eop.earth_orientation_class() if subdaily else EarthOrientation)(EOP))
            angles, series = O.Frame(self.finals, subdaily, "angles"), O.Frame(self.finals, subdaily)
            worst_angles = worst_series = 0.
            for t in EPOCHS:
                p = production.celestial_to_terrestrial((t-origin)/1e9)
                worst_angles = max(worst_angles, float(np.max(np.abs(p-angles.rotation(t)))))
                worst_series = max(worst_series, angle_uas(p, series.rotation(t)))
            self.assertLess(worst_angles, 1e-12, subdaily)
            self.assertGreater(worst_series, 0.5, subdaily)       # 1.5 uas on this date (Astra); not a no-op
            self.assertLess(worst_series, 5., subdaily)

    def test_unknown_method_refused(self):
        with self.assertRaises(ValueError):
            O.Frame(self.finals, cip="other")


if __name__ == "__main__":
    unittest.main()
