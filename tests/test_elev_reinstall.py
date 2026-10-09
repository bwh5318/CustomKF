"""Opus_Fork.elev.install is idempotent within one interpreter (Astra PI-10, 8 Oct 2026): repeated or changed
installs apply exactly one transform, the current variant's, to the restored rows. Global state is restored after.

    C:\\anaconda\\python.exe -m unittest tests.test_elev_reinstall -v
"""
import os
import unittest
from unittest import mock

import numpy as np

from Opus_Fork import elev, gradients

BASE = "erp+thrust+iiia2600+sdeop"
SIN_E = (0.5, 0.2)                                     # 30 degrees, and 11.5 degrees (below the 15 degree cutoff)


def fake_restore(path):
    rows = [dict(sigma=np.array([elev.SIGMA0[0]/s, elev.SIGMA0[1]/s]), tag=s) for s in SIN_E]
    return {"path": path}, rows, {}


class Reinstall(unittest.TestCase):
    def setUp(self):
        from claude.tools import dated_fixture, dated_observation
        from claude.roadmap import long_iteration
        from customkf.frames import EarthOrientation
        from Opus_Fork import iteration, ngv_pilot, ngv_traj_cache
        self.modules = dict(dated_fixture=dated_fixture, long_iteration=long_iteration, iteration=iteration,
                            ngv_pilot=ngv_pilot, ngv_traj_cache=ngv_traj_cache, observation=dated_observation,
                            EarthOrientation=EarthOrientation)
        self.saved = dict(restore=dated_fixture.restore, long_restore=long_iteration.restore,
                          it=dict(vars(iteration)), ngv=ngv_pilot.model_binding, cache=ngv_traj_cache.model_binding,
                          subdaily=EarthOrientation.__dict__.get("subdaily"), gradient=dated_observation.GRADIENT)
        dated_fixture.restore = fake_restore

    def tearDown(self):
        m, s = self.modules, self.saved
        m["dated_fixture"].restore, m["long_iteration"].restore = s["restore"], s["long_restore"]
        for key in ("restore", "LongPilot", "cached_products", "MODEL_IDENTITY"):
            if key in s["it"]:
                setattr(m["iteration"], key, s["it"][key])
        m["ngv_pilot"].model_binding, m["ngv_traj_cache"].model_binding = s["ngv"], s["cache"]
        m["EarthOrientation"].subdaily = s["subdaily"]
        m["observation"].GRADIENT = s["gradient"]

    def install(self, change):
        with mock.patch.dict(os.environ, {elev.ENVIRONMENT: f"{BASE}+{change}", gradients.ENVIRONMENT: "none"}):
            elev.install()
        return self.modules["dated_fixture"].restore("fixture.json")[1]

    def expected(self, change):
        return elev.transform(fake_restore("fixture.json")[1], change)

    def assert_rows(self, rows, change):
        want = self.expected(change)
        self.assertEqual([r["tag"] for r in rows], [r["tag"] for r in want])
        for a, b in zip(rows, want):
            np.testing.assert_array_equal(a["sigma"], b["sigma"])

    def test_repeated_elw13_install_transforms_once(self):
        self.assert_rows(self.install("elw13"), "elw13")
        self.assert_rows(self.install("elw13"), "elw13")          # raised "Row sigma does not follow" before PI-10

    def test_changed_installs_keep_only_the_current_variant(self):
        self.assert_rows(self.install("cut15s"), "cut15s")
        self.assertEqual(len(self.install("none")), len(SIN_E))   # the earlier cutoff no longer filters
        self.assert_rows(self.install("elw13"), "elw13")
        self.assert_rows(self.install("none"), "none")
        for name in ("long_iteration", "iteration"):
            self.assertIs(self.modules[name].restore, self.modules["dated_fixture"].restore)


if __name__ == "__main__":
    unittest.main()
