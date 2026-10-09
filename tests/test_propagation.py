from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
from customkf.propagation import propagate, IntegrationSettings, PropagationStopped
from tests.orbit_oracle import kepler_states


class PropagationTests(unittest.TestCase):
    def setUp(self):
        self.state=kepler_states([0])[0]

    def test_guard_and_actual_library_threads(self):
        from threadpoolctl import threadpool_info
        self.assertTrue(os.environ.get("CUSTOMKF_RUN_DIR"),"Run numerical tests with customkf.guard")
        self.assertTrue(all(pool["num_threads"]<=int(os.environ["MKL_NUM_THREADS"]) for pool in threadpool_info()))

    def test_initial_transition_and_parameter_sensitivity(self):
        result=propagate(self.state,[0,60])
        np.testing.assert_allclose(result.states_m_mps[0],self.state,atol=4e-9,rtol=0)
        np.testing.assert_array_equal(result.state_transition[0],np.eye(6))
        np.testing.assert_array_equal(result.parameter_sensitivity[0],np.zeros((6,4)))

    def test_two_body_oracle_and_export_interpolation(self):
        times=np.array([0,37,1441,3659,7193,10800.])
        result=propagate(self.state,times)
        truth=kepler_states(times)
        self.assertLess(np.max(np.linalg.norm(result.states_m_mps[:,:3]-truth[:,:3],axis=1)),.003)
        self.assertLess(np.max(np.linalg.norm(result.states_m_mps[:,3:]-truth[:,3:],axis=1)),1e-6)

    def test_backward_propagation(self):
        state=kepler_states([3600])[0]
        result=propagate(state,[3600,1901,0],initial_time_s=3600,partials=False)
        np.testing.assert_allclose(result.states_m_mps,kepler_states([3600,1901,0]),atol=1e-4,rtol=0)
        self.assertIsNone(result.state_transition)

    def test_short_arc_independent_perturbation(self):
        delta=np.array([.1,-.2,.3,1e-5,-2e-5,3e-5])
        dp=np.array([1e-9,1e-10,-1e-10,2e-10])
        reference=propagate(self.state,[0,1800])
        changed=propagate(self.state+delta,[0,1800],parameters=dp,partials=False)
        prediction=reference.state_transition[-1]@delta+reference.parameter_sensitivity[-1]@dp
        np.testing.assert_allclose(changed.states_m_mps[-1]-reference.states_m_mps[-1],prediction,atol=1e-6,rtol=0)

    def test_cooperative_stop_and_evaluation_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            stop=Path(folder)/"STOP.json";stop.write_text("{}")
            with self.assertRaises(PropagationStopped):propagate(self.state,[0,600],stop_file=stop)
        with self.assertRaises(PropagationStopped):propagate(self.state,[0,600],settings=replace(IntegrationSettings(),max_evaluations=1))

    def test_invalid_time_grid_and_tolerances(self):
        for times in ([0],[0,1,1],[0,5,2],[0,-1,2],[0,172801],[0,np.nan]):
            with self.assertRaises(ValueError):propagate(self.state,times)
        for settings in (replace(IntegrationSettings(),rtol=1e-18),replace(IntegrationSettings(),max_step_s=0)):
            with self.assertRaises(ValueError):propagate(self.state,[0,60],settings=settings)
