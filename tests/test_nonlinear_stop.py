"""Termination must check nuisance-parameter progress as well as orbit steps."""
import unittest
import numpy as np
from customkf.nonlinear_stop import stationary,model_reduction
from customkf.network_square_root import Block


class NonlinearStopTests(unittest.TestCase):
    def test_model_reduction_against_hand_computed_whitened_system(self):
        b=Block(np.array([[1.],[0.]]),np.array([[0.],[1.]]),np.array([3.,4.]),np.array([1.,2.]))
        c=(np.ones((1,1)),np.array([2.]),np.array([2.]))
        reduction,norm2=model_reduction([b],c,np.array([1.,2.]))
        self.assertEqual(reduction,8.75)
        self.assertEqual(norm2,2.25)

    def test_tiny_orbit_step_with_large_objective_improvement_is_not_done(self):
        self.assertFalse(stationary(1e-5,1500.,.01,.01))

    def test_small_objective_change_does_not_hide_large_weak_orbit_step(self):
        self.assertFalse(stationary(.1,1500.,1e-10,1e-10))

    def test_direction_must_also_be_small(self):
        self.assertFalse(stationary(1e-5,1500.,0.,.01))

    def test_stationary_and_invalid_values(self):
        self.assertTrue(stationary(1e-5,1500.,1e-10,1e-10))
        for value in (float("nan"),float("inf"),-1.):
            for k in range(4):
                args=[1e-5,1500.,1e-10,1e-10];args[k]=value
                self.assertFalse(stationary(*args))


if __name__=="__main__":unittest.main()
