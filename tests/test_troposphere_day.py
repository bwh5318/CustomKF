"""Troposphere day of year in customkf.dynamic_observation (OBS-01 defect fix, checkpoint-A Q5).

    C:\\anaconda\\python.exe -m unittest tests.test_troposphere_day -v

The real-data parity (Aug 2 bitwise, Aug 3 equal to the dated module) is
docs/consolidation/evidence/obs01_parity.py, run under the root guard.
"""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

import numpy as np

from customkf import dynamic_observation as obs
from customkf.sp3 import epoch_tag
from customkf.station_models import troposphere
from claude.tools import dated_observation
from tests.test_stage5 import Bodies, Central, StaticEpoch, calibration, record

GPS_START = datetime(1980, 1, 6)


def calendar_day(origin_ns, receive_s):
    """Independent calendar arithmetic: 1 + days since 1 January of the origin's GPST year."""
    origin = GPS_START+timedelta(microseconds=origin_ns//1000)
    return 1+(origin+timedelta(seconds=receive_s)-datetime(origin.year, 1, 1)).total_seconds()/86400


def dated_row(origin_dt):
    """The fields the preparers write (Opus_Fork/prepare.py, claude/roadmap/long_prepare.py)."""
    return {"origin_doy": int(origin_dt.strftime("%j")),
            "origin_second_of_day": float(origin_dt.hour*3600+origin_dt.minute*60+origin_dt.second)}


class Products:
    def __init__(self, origin_ns):
        self.origin_ns = origin_ns


class Wrapper:
    def __init__(self, base):
        self.base = base


class TroposphereDay(unittest.TestCase):
    def test_legacy_origin_is_the_stage5_origin(self):
        from customkf.stage5_pilot import ORIGIN
        self.assertEqual(obs.LEGACY_ORIGIN_NS, ORIGIN)
        self.assertEqual(obs.LEGACY_ORIGIN_NS, epoch_tag("* 2026 8 2 11 59 50"))

    def test_undated_rows_keep_the_former_expression_bitwise(self):
        for receive_s in (0., 10.000123, 43200.5, 86399.9):
            for products in (Products(obs.LEGACY_ORIGIN_NS), Wrapper(Products(obs.LEGACY_ORIGIN_NS)),
                             Wrapper(Wrapper(Products(obs.LEGACY_ORIGIN_NS)))):
                self.assertEqual(obs.troposphere_day(products, {}, receive_s), 214+(43190+receive_s)/86400)

    def test_undated_rows_refused_away_from_the_stage5_origin(self):
        other = epoch_tag("* 2026 8 3 11 59 50")
        for products in (Products(other), Products(0), Wrapper(Products(other)), object(), Wrapper(object())):
            with self.assertRaisesRegex(ValueError, "Undated observation row"):
                obs.troposphere_day(products, {}, 10.)

    def test_dated_rows_use_their_own_date_on_the_gpst_calendar(self):
        for text in ("2026 8 3 11 59 50", "2026 6 23 0 0 0", "2026 3 1 23 59 50"):
            origin_dt = datetime.strptime(text, "%Y %m %d %H %M %S")
            origin = epoch_tag("* "+text)
            row = dated_row(origin_dt)
            for receive_s in (10., 43210.25, 86400.):
                value = obs.troposphere_day(Products(origin), row, receive_s)
                # Exactly the dated module's expression ...
                self.assertEqual(value, row["origin_doy"]+(row["origin_second_of_day"]+receive_s)/86400)
                # ... which is the GPST calendar day of the receive epoch, by independent arithmetic.
                self.assertLess(abs(value-calendar_day(origin, receive_s)), 2e-11)

    def test_another_date_is_an_intended_difference(self):
        """A Jun 23 dated row: formerly given Aug 2 seasonality (day 214), now its own (about 1 cm at 5 degrees)."""
        text = "2026 6 23 11 59 50"
        row = dated_row(datetime.strptime(text, "%Y %m %d %H %M %S"))
        new = obs.troposphere_day(Products(epoch_tag("* "+text)), row, 100.)
        former = 214+(43190+100.)/86400
        self.assertAlmostEqual(former-new, 40., places=9)
        xyz = np.array([4027893., 307045., 4919475.])
        difference = troposphere(xyz, np.deg2rad(5.), new)[0]-troposphere(xyz, np.deg2rad(5.), former)[0]
        self.assertGreater(abs(difference), 5e-3)

    def test_year_and_leap_boundaries(self):
        """The count runs on past 31 December, so it is continuous within an arc; wrapping would move <0.2 mm."""
        for text, last in (("2026 12 31 23 59 50", 365), ("2028 12 31 23 59 50", 366)):
            origin_dt = datetime.strptime(text, "%Y %m %d %H %M %S")
            row = dated_row(origin_dt)
            self.assertEqual(row["origin_doy"], last)
            products = Products(epoch_tag("* "+text))
            before, after = (obs.troposphere_day(products, row, s) for s in (9., 11.))
            self.assertLess(before, last+1)
            self.assertGreater(after, last+1)
            self.assertAlmostEqual(after-before, 2/86400, places=12)
            self.assertLess(abs(after-calendar_day(products.origin_ns, 11.)), 2e-11)
        xyz = np.array([4027893., 307045., 4919475.])
        for elevation in (5., 10., 30.):
            unwrapped = troposphere(xyz, np.deg2rad(elevation), 366.)[0]
            wrapped = troposphere(xyz, np.deg2rad(elevation), 1.)[0]
            self.assertLess(abs(unwrapped-wrapped), 2e-4)

    def test_modeled_link_passes_the_date_to_the_troposphere(self):
        initial = np.array([26560000., 1e6, 2e6, 0., 3800., 100.])
        trajectory = obs.Trajectory(initial, Central(), 300.)
        cal, bodies = calibration(), Bodies()
        base = {"satellite": "G01", "time_s": 132.125, "receiver_xyz": np.array([6378137., 0., 0.])}
        cases = [(obs.LEGACY_ORIGIN_NS, base, lambda r: 214+(43190+r)/86400),
                 (epoch_tag("* 2026 8 3 11 59 50"), base | {"origin_doy": 215, "origin_second_of_day": 43190.},
                  lambda r: 215+(43190.+r)/86400)]
        for origin, row, expected in cases:
            products = obs.DynamicProducts(StaticEpoch(), origin, {"G01": record(af1=2e-5, gps_ns=origin)},
                                           {"G01": trajectory})
            seen = []

            def spy(xyz, elevation, doy):
                seen.append(doy)
                return troposphere(xyz, elevation, doy)
            with patch.object(obs, "troposphere", side_effect=spy):
                g, _ = obs.modeled_link(products, row, cal, cal, bodies, 20., -5., .1, 15., details=True)
                obs.link_jacobian(products, row, cal, cal, bodies, 20., -5., .1, 15., 0.)
            self.assertEqual(seen[0], expected(g["receive_s"]))
            self.assertGreater(len(seen), 13)          # the Jacobian stencils (PerturbedProducts) resolve the origin too
            with patch.object(dated_observation, "troposphere", side_effect=spy):
                if "origin_doy" in row:
                    seen.clear()
                    dated_observation.modeled_link(products, row, cal, cal, bodies, 20., -5., .1, 15., details=True)
                    self.assertEqual(seen[0], expected(g["receive_s"]))


if __name__ == "__main__":
    unittest.main()
