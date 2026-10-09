"""External a-priori gradients (Opus_Fork/gradients.py; experiments/gradients/PROTOCOL.md).

    C:\\anaconda\\python.exe -m unittest tests.test_gradients -v
"""
import math
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import numpy as np

from Opus_Fork import gradients as G


class Slant(unittest.TestCase):
    def test_chen_herring_hand_values(self):
        e = math.radians(10.)
        mg_h = 1/(math.sin(e)*math.tan(e)+0.0031)
        mg_w = 1/(math.sin(e)*math.tan(e)+0.0007)
        self.assertAlmostEqual(mg_h, 29.657, places=3)              # Sol's sensitivity scale: 29.66 at 10 deg
        self.assertAlmostEqual(G.slant((1., 0., 0., 0.), e, 0.), 1e-3*mg_h, places=15)
        self.assertAlmostEqual(G.slant((0., 0., 1., 0.), e, 0.), 1e-3*mg_w, places=15)
        self.assertGreater(mg_w, mg_h)                                # wet uses the smaller C

    def test_azimuth_from_north_clockwise(self):
        e = math.radians(30.)
        g = (0.2, -0.1, 0.3, 0.4)
        north, east = G.slant(g, e, 0.), G.slant(g, e, math.pi/2)
        self.assertAlmostEqual(north, 1e-3*(G.mapping(e, G.C_H)*0.2+G.mapping(e, G.C_W)*0.3), places=15)
        self.assertAlmostEqual(east, 1e-3*(G.mapping(e, G.C_H)*-0.1+G.mapping(e, G.C_W)*0.4), places=15)
        self.assertAlmostEqual(G.slant(g, e, math.pi), -north, places=15)

    def test_utc_mjd(self):
        tag = ((61255-G.GPS0_MJD)*86400+18)*10**9                      # 2026-08-03 00:00:18 GPST = 00:00:00 UTC
        self.assertAlmostEqual(G.utc_mjd(tag), 61255., places=12)


class GradSitewise(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="grad-"))
        (self.dir/"a.grad_g").write_text("AAAA      61255.00   0.100  -0.200   0.300   0.400\n"
                                         "AAAA      61255.25   0.300   0.000   0.100   0.000\n"
                                         "BBBB      61255.00   1.000   1.000   1.000   1.000\n"
                                         "BBBB      61256.00   1.000   1.000   1.000   1.000\n")

    def test_linear_in_time(self):
        f = G.GradSitewise([self.dir/"a.grad_g"])
        np.testing.assert_allclose(f.at("AAAA", 61255.125), (0.2, -0.1, 0.2, 0.2), rtol=0, atol=1e-12)
        np.testing.assert_allclose(f.at("AAAA", 61255.0), (0.1, -0.2, 0.3, 0.4), rtol=0, atol=1e-12)

    def test_refusals(self):
        f = G.GradSitewise([self.dir/"a.grad_g"])
        for station, mjd in (("AAAA", 61254.99), ("AAAA", 61255.3), ("CCCC", 61255.1), ("BBBB", 61255.5)):
            with self.subTest(station=station, mjd=mjd), self.assertRaises(ValueError):
                f.at(station, mjd)                                       # outside, missing station, 1-day gap
        (self.dir/"b.grad_g").write_text("AAAA      61255.00   0.900  -0.200   0.300   0.400\n")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            G.GradSitewise([self.dir/"a.grad_g", self.dir/"b.grad_g"])

    def test_real_operational_files_cover_aug3(self):
        files = G.files("grad_op")
        if not files:
            self.skipTest("GRAD_OP files not acquired")
        f = G.GradSitewise(files)
        for station in ("BRUX", "GLPS", "YELL"):
            for mjd in np.linspace(61254.999, 61256.0, 9):
                self.assertTrue(np.all(np.isfinite(f.at(station, mjd))))


class Gpt3(unittest.TestCase):
    def test_day_of_year_with_fraction(self):
        self.assertAlmostEqual(G.Gpt3Gradients.day_of_year(61255.5), 215.5, places=12)     # 3 Aug 2026 12:00
        self.assertAlmostEqual(G.Gpt3Gradients.day_of_year(61041.0), 1.0, places=12)       # 1 Jan 2026

    def synthetic(self):
        g = G.Gpt3Gradients.__new__(G.Gpt3Gradients)
        rng = np.random.default_rng(3)
        g.coefficients = rng.normal(size=(64800, 4, 5))
        return g

    def test_cell_centre_returns_the_cell_and_bilinear_is_a_convex_mix(self):
        g = self.synthetic()
        lat, lon = math.radians(50.5), math.radians(4.5)             # centre of polar-distance row 40, lon cell 5
        seasonal = lambda mjd: (lambda w: np.array([1, math.cos(w), math.sin(w), math.cos(2*w), math.sin(2*w)]))(
            2*math.pi*G.Gpt3Gradients.day_of_year(mjd)/365.25)
        np.testing.assert_allclose(g.at_position(lat, lon, 61255.5), g._cell(40, 5, seasonal(61255.5)), atol=1e-12)
        a, b = g.at_position(math.radians(50.5), math.radians(4.5), 61255.5), g.at_position(math.radians(50.5), math.radians(5.5), 61255.5)
        mid = g.at_position(math.radians(50.5), math.radians(5.0), 61255.5)
        np.testing.assert_allclose(mid, (np.array(a)+np.array(b))/2, atol=1e-12)

    def test_real_grid_units_and_shape(self):
        path = G.DATA/"gpt3/gpt3_1.grd"
        if not path.exists():
            self.skipTest("GPT3 grid not acquired")
        g = G.Gpt3Gradients(path)
        v = np.array(g.at_position(math.radians(50.8), math.radians(4.36), 61255.5))
        self.assertTrue(np.all(np.abs(v) < 2.))                       # mm; empirical gradients are sub-mm to ~1 mm


class HookAndBinding(unittest.TestCase):
    def test_binding_none_and_sources(self):
        with mock.patch.dict(os.environ, {G.ENVIRONMENT: "none"}):
            self.assertIsNone(G.binding())
        with mock.patch.dict(os.environ, {G.ENVIRONMENT: "bogus"}), self.assertRaises(RuntimeError):
            G.current()
        if G.files("grad_op"):
            b = G.binding("grad_op")
            self.assertEqual(b["source"], "grad_op")
            self.assertTrue(b["inputs"] and all(len(v) == 64 for v in b["inputs"].values()))

    def test_hook_resolves_the_origin_through_wrappers(self):
        if not G.files("grad_op"):
            self.skipTest("GRAD_OP files not acquired")
        hook = G.hook("grad_op")
        origin = ((61255-G.GPS0_MJD)*86400-10)*10**9
        products = NS(origin_ns=origin)
        wrapper = NS(base=NS(base=products))
        row = {"station": "BRUX", "receiver_xyz": np.array([4027881.6, 306998.6, 4919499.0])}
        g = {"receive_s": 3610.0, "elevation_rad": math.radians(15.), "azimuth_rad": 1.0}
        self.assertEqual(hook(products, row, g), hook(wrapper, row, g))
        want = G.slant(G.field("grad_op").at("BRUX", G.utc_mjd(origin+3610*10**9)), math.radians(15.), 1.0)
        self.assertAlmostEqual(hook(products, row, g), want, places=15)


# The option-A validation fixtures and the files amendment A1 records for each (validation_analysis.json).
VALIDATION = {"runs/20260929T202245Z-21f63ba3": ["2026156", "2026157", "2026158"],
              "runs/20260929T203924Z-224f1e22": ["2026170", "2026171", "2026172"],
              "runs/20260929T201929Z-5b2b3e42": ["2026173", "2026174", "2026175"],
              "runs/20260929T204645Z-ba94e895": ["2026186", "2026187", "2026188"],
              "runs/20260929T203059Z-40b5a8d7": ["2026203", "2026204", "2026205"]}


def context(fixture_dir):
    import json
    return json.loads((G.HERE.parent/fixture_dir/"fixture.json").read_text())["context"]


class ArcInputs(unittest.TestCase):
    """Defect of 3 Oct 2026: grad_op bound every file present, so acquiring another date changed a running binding."""

    def test_arc_days_follow_amendment_a1(self):
        origin = ((61255-G.GPS0_MJD)*86400-10)*10**9                   # Aug 3 fixture origin, 23:59:50 GPST Aug 2
        self.assertEqual(G.arc_days(origin, 85820), ["2026214", "2026215", "2026216"])
        self.assertEqual(G.arc_days(origin+30*10**9, 3600), ["2026215", "2026216"])       # 00:00:02 UTC Aug 3
        self.assertEqual(G.arc_days(origin, 2*86400), ["2026214", "2026215", "2026216", "2026217"])
        for fixture_dir, days in VALIDATION.items():
            if not (G.HERE.parent/fixture_dir/"fixture.json").exists():
                continue
            c = context(fixture_dir)
            self.assertEqual(G.arc_days(int(c["origin_ns"]), c["duration_s"]), days, fixture_dir)

    def test_only_the_arc_files_are_bound_and_missing_ones_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data/"GRAD_OP").mkdir()
            for d in ("2026214", "2026215", "2026216"):
                (data/"GRAD_OP"/f"{d}.grad_g").write_text(d)
            arc = {G.ARC_ENVIRONMENT: "2026214,2026215,2026216"}
            with mock.patch.object(G, "DATA", data), mock.patch.dict(os.environ, arc):
                before = G.binding("grad_op")
                (data/"GRAD_OP"/"2026300.grad_g").write_text("another date, acquired mid-campaign")
                self.assertEqual(G.binding("grad_op"), before)
                self.assertEqual(sorted(before["inputs"]), ["2026214.grad_g", "2026215.grad_g", "2026216.grad_g"])
                (data/"GRAD_OP"/"2026216.grad_g").unlink()
                with self.assertRaisesRegex(FileNotFoundError, "2026216.grad_g"):
                    G.files("grad_op")
            for bad in ("", "2026214,", "26214", "2026214;2026215"):
                with mock.patch.object(G, "DATA", data), mock.patch.dict(os.environ, {G.ARC_ENVIRONMENT: bad}):
                    with self.assertRaises(RuntimeError, msg=bad):
                        G.files("grad_op")

    def test_values_unchanged_on_the_validation_dates(self):
        """Parity: the arc's files give bitwise the same gradients as every file, at every station, every 5 min."""
        os.environ.pop(G.ARC_ENVIRONMENT, None)
        everything = G.field("grad_op") if G.files("grad_op") else None
        checked = 0
        for fixture_dir, days in VALIDATION.items():
            if everything is None or not (G.HERE.parent/fixture_dir/"fixture.json").exists():
                continue
            c = context(fixture_dir)
            with mock.patch.dict(os.environ, {G.ARC_ENVIRONMENT: ",".join(days)}):
                arc = G.field("grad_op")
            origin = int(c["origin_ns"])
            for station in c["stations"]:
                for t in range(10, int(c["duration_s"])+1, 300):
                    mjd = G.utc_mjd(origin+t*10**9)
                    self.assertEqual(arc.at(station, mjd), everything.at(station, mjd), (fixture_dir, station, t))
                    checked += 1
        if not checked:
            self.skipTest("validation fixtures or GRAD files not present")


if __name__ == "__main__":
    unittest.main()
