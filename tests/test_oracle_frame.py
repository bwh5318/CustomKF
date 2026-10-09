"""Oracle O2 against external reference cases (O3a; docs/consolidation/CONTRACTS_AND_ORACLE.md §4).

    C:\\anaconda\\python.exe -m unittest tests.test_oracle_frame -v

Tolerances are declared here, before any comparison with production code, and are physically justified:
- ORTHO_EOP: 1e-9 uas/us. The IERS test values are given to about 16 digits; this is double-precision agreement.
- Rotation elements: 2e-11, about 4 uas. That is 0.53 mm at the GPS orbit radius (26,560 km), half the 1 mm
  quantization of an SP3 position.
"""
from pathlib import Path
import re
import unittest

import numpy as np

from validation.oracle import frame as O

ORTHO_TOLERANCE = 1e-9
ROTATION_TOLERANCE = 2e-11


class IersOrthoEop(unittest.TestCase):
    def test_published_test_case(self):
        """The test case printed in the header of the IERS ORTHO_EOP.F itself (MJD 47100)."""
        header = (O.IERS_CH8/"ORTHO_EOP.F").read_text()
        want = [float(v.replace("D", "e")) for v in re.findall(
            r"delta_(?:x|y|UT1) = (-?\d+\.\d+D0)", header)]
        self.assertEqual(len(want), 3)
        self.assertIn("MJD = 47100D0", header)
        got = O.ocean_tidal_eop(47100.)
        self.assertTrue(np.allclose(got, want, rtol=0, atol=ORTHO_TOLERANCE), (got, want))

    def test_tables_parsed_from_the_fortran_sources(self):
        lines, sp, w = O._tables()
        self.assertEqual(lines.shape, (71, 5))
        self.assertTrue(np.all(lines[:, 0] == 2) and set(lines[:, 1]) == {1., 2.})
        self.assertEqual(int(np.sum(lines[:, 1] == 1)), 41)               # diurnal lines 1-41, semidiurnal 42-71
        largest = lines[np.argmax(np.abs(lines[:, 2]))]
        self.assertEqual(tuple(largest[1:]), (2., 631.92, 7.6060827, 12.14083318))   # M2, '255.555'
        self.assertEqual((sp[0, 0], sp[5, 1]), (0.0298, 0.0923))
        self.assertEqual((w[0, 0], w[11, 2]), (-6.77832, 0.04726))


class SofaRotationVector(unittest.TestCase):
    def test_c2t06a_reference_matrix(self):
        """SOFA/ERFA published test vector for c2t06a (t_sofa_c; pyerfa test_ufunc.test_c2t06a): TT = UT1 = MJD 53736,
        xp = 2.55060238e-7 rad, yp = 1.860359247e-6 rad, no celestial pole offsets."""
        want = np.array([[-0.1810332128305897282, 0.9834769806938592296, 0.6555550962998436505e-4],
                         [-0.9834768134136214897, -0.1810332203649130832, 0.5749800844905594110e-3],
                         [0.5773474024748545878e-3, 0.3961816829632690581e-4, 0.9999998325501747785]])
        got = O.compose((2400000.5, 53736.), (2400000.5, 53736.), 2.55060238e-7, 1.860359247e-6)
        self.assertLess(float(np.max(np.abs(got-want))), ROTATION_TOLERANCE)

    def test_orthogonal_and_inverse(self):
        r = O.compose((2400000.5, 61254.5), (2400000.5, 61254.5), 1e-6, 2e-6, 1e-9, -1e-9)
        self.assertLess(float(np.max(np.abs(r@r.T-np.eye(3)))), 1e-15)


class FinalsReader(unittest.TestCase):
    def setUp(self):
        self.path = Path(O.ROOT)/"data/stage2/finals2000A.all"
        if not self.path.exists():
            self.skipTest("finals2000A.all not present")
        self.finals = O.Finals(self.path)

    def test_campaign_days_are_covered_and_interpolation_is_linear(self):
        for mjd in (61254.25, 61212.5, 61257.9):        # 2 Aug, 21 Jun and 5 Aug 2026 (UTC)
            v = self.finals.at(mjd)
            self.assertEqual(v.shape, (5,))
            self.assertTrue(np.all(np.isfinite(v)))
        a, b, mid = self.finals.at(61254.), self.finals.at(61255.), self.finals.at(61254.5)
        self.assertTrue(np.allclose(mid[[0, 1, 3, 4]], (a[[0, 1, 3, 4]]+b[[0, 1, 3, 4]])/2, rtol=0, atol=1e-15))

    def test_extrapolation_refused(self):
        with self.assertRaises(ValueError):
            self.finals.at(self.finals.rows[-1, 0]+0.5)


if __name__ == "__main__":
    unittest.main()
