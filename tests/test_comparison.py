import unittest
import numpy as np
from customkf.comparison import (rac_basis, rac_difference, orbit_ure_m,
                                 clock_sisre_m, remove_epoch_clock_datum, summarize, C_LIGHT)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.r = np.array([26560000., 0, 0])
        angle = np.deg2rad(55)
        self.v = np.array([0, 3874*np.cos(angle), 3874*np.sin(angle)])

    def test_identity(self):
        np.testing.assert_array_equal(rac_difference(self.r, self.r, self.v), np.zeros(3))

    def test_known_centimetre_displacements_all_axes(self):
        # Independent analytic basis for this inclined orbit at its node.
        c, s = np.cos(np.deg2rad(55)), np.sin(np.deg2rad(55))
        expected_basis = np.array([[1,0,0], [0,c,s], [0,-s,c]])
        for axis in range(3):
            for sign in (-1,1):
                expected = np.zeros(3)
                expected[axis] = .01*sign
                candidate = self.r+.01*sign*expected_basis[axis]
                np.testing.assert_allclose(rac_difference(self.r,candidate,self.v), expected, atol=3e-9, rtol=0)

    def test_orthogonal_right_handed_basis(self):
        b = rac_basis(self.r, self.v)
        np.testing.assert_allclose(b@b.T,np.eye(3),atol=1e-14)
        self.assertAlmostEqual(np.linalg.det(b),1,places=14)

    def test_rigid_rotation_does_not_change_rac(self):
        theta = .37
        q = np.array([[np.cos(theta),-np.sin(theta),0], [np.sin(theta),np.cos(theta),0], [0,0,1]])
        delta = np.array([.03,-.04,.02])
        a = rac_difference(self.r,self.r+delta,self.v)
        b = rac_difference(q@self.r,q@(self.r+delta),q@self.v)
        np.testing.assert_allclose(a,b,atol=6e-9,rtol=0)

    def test_earth_fixed_velocity_is_detectably_wrong(self):
        earth_velocity = self.v-np.cross([0,0,7.2921151467e-5],self.r)
        b = rac_basis(self.r,self.v)
        correct = rac_difference(self.r,self.r+.1*b[1],self.v)
        wrong = rac_difference(self.r,self.r+.1*b[1],earth_velocity)
        self.assertLess(abs(correct[2]),1e-12)
        self.assertGreater(abs(wrong[2]),.02)

    def test_vectorized_matches_individual(self):
        r = np.stack([self.r]*3)
        v = np.stack([self.v]*3)
        p = r+np.eye(3)*.01
        np.testing.assert_allclose(rac_difference(r,p,v),np.array([rac_difference(a,b,c) for a,b,c in zip(r,p,v)]))

    def test_ure_amplitude_weight_and_cross_weight(self):
        np.testing.assert_allclose(orbit_ure_m(np.eye(3)),[.98,1/7,1/7],atol=1e-15)
        self.assertGreater(abs(float(orbit_ure_m([1,0,0]))-np.sqrt(.98)),.009)

    def test_clock_radial_cancellation(self):
        self.assertAlmostEqual(float(clock_sisre_m([1,0,0],.98/C_LIGHT)),0,places=14)
        self.assertAlmostEqual(float(clock_sisre_m([0,0,0],1e-9)),.299792458,places=14)

    def test_epoch_clock_datum(self):
        centered, offsets = remove_epoch_clock_datum([1,1,2,2],[1e-8,3e-8,9e-8,11e-8])
        np.testing.assert_allclose(centered,[-1e-8,1e-8,-1e-8,1e-8],atol=1e-22)
        self.assertAlmostEqual(offsets[1],2e-8)

    def test_rms_not_mean_of_norms(self):
        summary = summarize([[.03,0,0],[0,.04,0]])
        self.assertAlmostEqual(summary["rms_3d_m"],np.sqrt(.00125))
        self.assertNotAlmostEqual(summary["rms_3d_m"],.035,places=5)

    def test_invalid_geometry_and_data_fail(self):
        for r,v in (([0,0,0],[0,1,0]),([1,0,0],[2,0,0]),([np.nan,0,0],[0,1,0])):
            with self.assertRaises(ValueError):rac_basis(r,v)
        with self.assertRaises(ValueError):summarize(np.empty((0,3)))
        with self.assertRaises(ValueError):clock_sisre_m([[1,0,0]],np.nan)
        with self.assertRaises(ValueError):remove_epoch_clock_datum([float("nan")],[0.])
        with self.assertRaises(ValueError):remove_epoch_clock_datum([1.5],[0.])

    def test_numeric_threads_really_limited(self):
        from threadpoolctl import threadpool_info
        import os
        self.assertTrue(os.environ.get("CUSTOMKF_RUN_DIR"),"Numerical tests must use customkf.guard")
        self.assertTrue(all(p["num_threads"] <= int(os.environ["MKL_NUM_THREADS"]) for p in threadpool_info()))
