"""Domain-aware correction stencil of claude.tools.dated_observation.link_jacobian (Sol SOL-01; untouched A3).

    C:\\anaconda\\python.exe -m unittest tests.test_link_jacobian_domain -v

Synthetic sample functions only. The real-data regression (the Jun 23 GLPS-G10 link from the saved caches) is
Opus_Fork/experiments/untouched_dates/check_stencil_fix.py, run under the root guard.
"""
import unittest

import numpy as np

from claude.tools.dated_observation import OUT_OF_DOMAIN, correction_difference

UNIT = np.eye(6)[0]


def smooth(delta):
    s = float(delta[0])
    # Smooth at the stencil scale, like the antenna/troposphere corrections (truncation << tolerance).
    return np.array([np.sin(1e-3*s)+2e-5*s*s, np.cos(7e-4*s)+3e-6*s])


def limited(limit_low, limit_high, log=None):
    def sample(delta):
        s = float(delta[0])
        if log is not None:
            log.append(s)
        if not limit_low <= s <= limit_high:
            raise ValueError(OUT_OF_DOMAIN)
        return smooth(delta)
    return sample


class Stencil(unittest.TestCase):
    def test_valid_standard_step_is_bitwise_the_former_expression(self):
        for h in (10., .01):
            d = UNIT*h
            former = (smooth(d)-smooth(-d))/(2*h)
            self.assertTrue(np.array_equal(correction_difference(smooth, UNIT, h, h/64, smooth(UNIT*0.)), former))

    def test_step_is_halved_only_when_a_sample_leaves_the_domain(self):
        log = []
        result = correction_difference(limited(-6., 50., log), UNIT, 10., 10./64, smooth(UNIT*0.))
        self.assertEqual(log[:2], [10., -10.])                 # the standard stencil is tried first
        d = UNIT*5.
        self.assertTrue(np.array_equal(result, (smooth(d)-smooth(-d))/10.))
        self.assertEqual(sorted(set(abs(s) for s in log)), [5., 10.])

    def test_one_sided_when_no_symmetric_stencil_fits(self):
        """AF-02: the fallback is second order: (-3 f0 + 4 f(m) - f(2m)) / 2m on the in-domain side."""
        base = smooth(UNIT*0.)
        m = 10./64
        result = correction_difference(limited(0., 50.), UNIT, 10., m, base)
        self.assertTrue(np.allclose(result, (-3*base+4*smooth(UNIT*m)-smooth(UNIT*2*m))/(2*m)))
        result = correction_difference(limited(-50., 0.), UNIT, 10., m, base)
        self.assertTrue(np.allclose(result, -(-3*base+4*smooth(-UNIT*m)-smooth(-UNIT*2*m))/(2*m)))

    def test_one_sided_fallback_is_exact_for_a_quadratic(self):
        """Astra's AF-02 control: f(x) = x^2 at its boundary has derivative 0 (first order gave 0.15625)."""
        def quadratic(delta):
            s = float(delta[0])
            if s < 0:
                raise ValueError(OUT_OF_DOMAIN)
            return np.array([s*s, 2*s*s])
        result = correction_difference(quadratic, UNIT, 10., 10./64, np.zeros(2))
        self.assertTrue(np.allclose(result, 0., atol=1e-12))

    def test_unstable_one_sided_fallback_refused(self):
        def kinked(delta):
            s = float(delta[0])
            if s < 0:
                raise ValueError(OUT_OF_DOMAIN)
            return np.array([abs(s-.1), 0.])          # not smooth at the fallback scale
        with self.assertRaisesRegex(ValueError, "not stable"):
            correction_difference(kinked, UNIT, 10., 10./64, np.array([.1, 0.]))

    def test_nonfinite_values_refused(self):
        def nan_sample(delta):
            return np.array([np.nan, 0.])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            correction_difference(nan_sample, UNIT, 10., 10./64, np.zeros(2))

        def boundary_nan(delta):
            s = float(delta[0])
            if s < 0:
                raise ValueError(OUT_OF_DOMAIN)
            return np.array([np.inf if s > .2 else s, 0.])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            correction_difference(boundary_nan, UNIT, 10., 10./64, np.zeros(2))

    def test_scalar_unit_matches_the_former_clock_expression(self):
        """The receiver-clock stencil: unit 1.0, step 10 m; bitwise the former (f(rc+10) - f(rc-10)) / 20."""
        rc = 123.456

        def clock_sample(delta):
            return np.array([np.sin(1e-3*(rc+delta)), np.cos(2e-3*(rc+delta))])
        former = (np.array([np.sin(1e-3*(rc+10.)), np.cos(2e-3*(rc+10.))]) -
                  np.array([np.sin(1e-3*(rc-10.)), np.cos(2e-3*(rc-10.))]))/20.
        self.assertTrue(np.array_equal(correction_difference(clock_sample, 1., 10., 10./64, clock_sample(0.)), former))

    def test_refused_when_no_sample_is_in_domain(self):
        def never(delta):
            raise ValueError(OUT_OF_DOMAIN)
        with self.assertRaisesRegex(ValueError, "no in-domain derivative stencil"):
            correction_difference(never, UNIT, 10., 10./64, np.zeros(2))

    def test_other_errors_propagate_immediately(self):
        calls = []

        def broken(delta):
            calls.append(1)
            raise ValueError("Degenerate antenna geometry")
        with self.assertRaisesRegex(ValueError, "Degenerate"):
            correction_difference(broken, UNIT, 10., 10./64, np.zeros(2))
        self.assertEqual(len(calls), 1)

    def test_halved_derivative_agrees_with_the_standard_one_on_a_smooth_function(self):
        standard = correction_difference(smooth, UNIT, 10., 10./64, smooth(UNIT*0.))
        halved = correction_difference(limited(-6., 50.), UNIT, 10., 10./64, smooth(UNIT*0.))
        self.assertTrue(np.allclose(standard, halved, rtol=1e-3, atol=1e-9))


if __name__ == "__main__":
    unittest.main()
