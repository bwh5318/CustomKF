"""Observation-model gradient hook (claude.tools.dated_observation.GRADIENT) and its elev wiring.

    C:\\anaconda\\python.exe -m unittest tests.test_gradient_hook -v
"""
import os
import unittest
from unittest import mock

import numpy as np

from claude.tools import dated_observation as D
from Opus_Fork import elev, gradients
from tests.test_stage5 import Bodies, Central, StaticEpoch, calibration, record

VARIANT = "erp+thrust+iiia2600+sdeop+elw13"


def setup():
    initial = np.array([26560000., 1e6, 2e6, 0., 3800., 100.])
    trajectory = D.Trajectory(initial, Central(), 300.)
    products = D.DynamicProducts(StaticEpoch(), 0, {"G01": record(af1=2e-5)}, {"G01": trajectory})
    row = {"satellite": "G01", "time_s": 132.125, "receiver_xyz": np.array([6378137., 0., 0.]), "station": "TEST",
           "origin_doy": 215, "origin_second_of_day": 43190.}
    return products, row, calibration(), Bodies()


class Hook(unittest.TestCase):
    def tearDown(self):
        D.GRADIENT = None

    def test_default_is_none(self):
        self.assertIsNone(D.GRADIENT)

    def test_zero_hook_is_bitwise_the_model_and_a_constant_shifts_code_and_phase(self):
        products, row, cal, bodies = setup()
        args = (products, row, cal, cal, bodies, 20., -5., .1, 15.)
        plain = D.modeled_link(*args)
        plain_details = D.modeled_link(*args, details=True)[1]
        D.GRADIENT = lambda p, r, g: 0.
        for a, b in zip(D.modeled_link(*args), plain):
            np.testing.assert_array_equal(a, b)
        D.GRADIENT = lambda p, r, g: 0.0123
        shifted = D.modeled_link(*args)
        np.testing.assert_allclose(shifted[0]-plain[0], [0.0123, 0.0123], rtol=0, atol=1e-8)   # ulp of a 2e7 m range
        np.testing.assert_allclose(D.modeled_link(*args, details=True)[1]-plain_details, [0.0123, 0.0123], rtol=0, atol=1e-12)

    def test_hook_receives_geometry_and_enters_the_jacobian(self):
        products, row, cal, bodies = setup()
        args = (products, row, cal, cal, bodies, 20., -5., .1, 15., 0.)
        plain = D.link_jacobian(*args)
        seen = []

        def hook(p, r, g):
            seen.append((r["station"], g["elevation_rad"], g["azimuth_rad"], g["receive_s"]))
            return 0.05*g["elevation_rad"]                      # geometry-dependent: must reach the derivative
        D.GRADIENT = hook
        with_hook = D.link_jacobian(*args)
        self.assertTrue(seen and seen[0][0] == "TEST")
        self.assertFalse(np.array_equal(with_hook[0], plain[0]))
        self.assertLess(float(np.max(np.abs(with_hook[0]-plain[0]))), 1e-3)


class ElevWiring(unittest.TestCase):
    def test_none_change_keeps_rows_and_checks_the_sigma_rule(self):
        rows = [dict(sigma=np.array([0.9/0.5, 0.009/0.5]), x=1), dict(sigma=np.array([0.9, 0.009]), x=2)]
        out = elev.transform(rows, "none")
        self.assertEqual([r["x"] for r in out], [1, 2])
        self.assertIs(out[0], rows[0])
        with self.assertRaisesRegex(ValueError, "sigma"):
            elev.transform([dict(sigma=np.array([0.9, 0.01]))], "none")
        self.assertIn("erp+thrust+iiia2600+sdeop+none", elev.VARIANTS)

    def test_install_sets_the_hook_from_the_current_source_every_time(self):
        """Astra C02: grad_op or gpt3, then none, in one interpreter, must leave no hook; repeat installs agree."""
        from claude.tools import dated_observation as D2
        from Opus_Fork import iteration, ngv_pilot, ngv_traj_cache, sdeop
        from claude.tools import dated_fixture
        from claude.roadmap import long_iteration
        from customkf.frames import EarthOrientation
        # elev.install -> sdeop.install puts the sub-daily EOP model on EarthOrientation for the whole process; restore it
        # afterwards so later tests in the same run see the plain class (test_stage2 caught the leak).
        saved = dict(restore=dated_fixture.restore, long_restore=long_iteration.restore, it=dict(vars(iteration)),
                     ngv=ngv_pilot.model_binding, cache=ngv_traj_cache.model_binding,
                     subdaily=EarthOrientation.__dict__.get("subdaily"))
        try:
            for active in ("grad_op", "gpt3"):
                if not gradients.files(active) or not all(p.is_file() for p in gradients.files(active)):
                    continue
                with self.subTest(active=active):
                    with mock.patch.dict(os.environ, {elev.ENVIRONMENT: VARIANT, gradients.ENVIRONMENT: active}):
                        elev.install()
                        self.assertIsNotNone(D2.GRADIENT)
                        self.assertEqual(elev.binding()["gradients"]["source"], active)
                    with mock.patch.dict(os.environ, {elev.ENVIRONMENT: VARIANT, gradients.ENVIRONMENT: "none"}):
                        elev.install()
                        self.assertIsNone(D2.GRADIENT)
                        self.assertNotIn("gradients", elev.binding())
                        elev.install()                                   # repeat install stays off
                        self.assertIsNone(D2.GRADIENT)
        finally:
            D2.GRADIENT = None
            dated_fixture.restore, long_iteration.restore = saved["restore"], saved["long_restore"]
            for key in ("restore", "LongPilot", "cached_products", "MODEL_IDENTITY"):
                if key in saved["it"]:
                    setattr(iteration, key, saved["it"][key])
            ngv_pilot.model_binding, ngv_traj_cache.model_binding = saved["ngv"], saved["cache"]
            EarthOrientation.subdaily = saved["subdaily"]

    def test_binding_gains_gradients_only_when_active(self):
        with mock.patch.dict(os.environ, {elev.ENVIRONMENT: VARIANT, gradients.ENVIRONMENT: "none"}):
            plain = elev.binding()
        self.assertNotIn("gradients", plain)
        if not gradients.files("grad_op"):
            self.skipTest("GRAD_OP files not acquired")
        with mock.patch.dict(os.environ, {elev.ENVIRONMENT: VARIANT, gradients.ENVIRONMENT: "grad_op"}):
            active = elev.binding()
        self.assertEqual(active["gradients"]["source"], "grad_op")
        self.assertEqual({k: v for k, v in active.items() if k != "gradients"}, plain)


if __name__ == "__main__":
    unittest.main()
