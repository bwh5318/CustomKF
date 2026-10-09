import unittest
import numpy as np
from customkf.dynamics import TestForceModel, FixedThirdBody, MU_EARTH, R_EARTH


class DynamicsTests(unittest.TestCase):
    def setUp(self):
        self.state = np.array([2.1e7,-1.3e7,1.1e7,1700,2300,-2100.])
        self.p = np.array([1.08262668e-3,1e-9,-2e-9,3e-9])
        self.model = TestForceModel(third_bodies=(FixedThirdBody(4.9048695e12,(3e8,2e8,-1e8)),))

    def test_central_force_and_circular_speed(self):
        r = 26560000.
        a,dr,dv,dp = TestForceModel().evaluate(0,[r,0,0,0,np.sqrt(MU_EARTH/r),0],np.zeros(4))
        np.testing.assert_allclose(a,[-MU_EARTH/r**2,0,0],rtol=1e-15)
        np.testing.assert_allclose(dr,np.diag([2,-1,-1])*MU_EARTH/r**3,rtol=1e-15)
        np.testing.assert_array_equal(dv,np.zeros((3,3)))
        np.testing.assert_array_equal(dp[:,1:],np.eye(3))

    def test_j2_equator_and_pole_signs(self):
        r = 26560000.
        k = 1.5*MU_EARTH*R_EARTH**2/r**4
        for state,expected in (([r,0,0,0,0,0],[-k,0,0]),([0,0,r,0,0,0],[0,0,2*k])):
            a,*_ = TestForceModel().evaluate(0,state,[1,0,0,0])
            central,*_ = TestForceModel().evaluate(0,state,np.zeros(4))
            np.testing.assert_allclose(a-central,expected,rtol=1e-14,atol=1e-16)

    def test_indirect_third_body_term(self):
        r,b,mu = 26560000.,1.5e11,1.3271244e20
        model = TestForceModel(third_bodies=(FixedThirdBody(mu,(b,0,0)),))
        a,*_ = model.evaluate(0,[r,0,0,0,0,0],np.zeros(4))
        expected = -MU_EARTH/r**2+mu*(1/(b-r)**2-1/b**2)
        np.testing.assert_allclose(a,[expected,0,0],rtol=0,atol=2e-16)

    def test_force_jacobian_central_differences_multiple_scales(self):
        _,jac,_,_=self.model.evaluate(0,self.state,self.p)
        errors=[]
        for h in (1000.,100.,10.):
            fd=np.empty((3,3))
            for k in range(3):
                delta=np.zeros(6);delta[k]=h
                plus=self.model.evaluate(0,self.state+delta,self.p,partials=False)[0]
                minus=self.model.evaluate(0,self.state-delta,self.p,partials=False)[0]
                fd[:,k]=(plus-minus)/(2*h)
            errors.append(np.max(np.abs(fd-jac)))
        self.assertLess(min(errors),2e-17)
        self.assertLess(errors[1],errors[0])
        np.testing.assert_allclose(jac,jac.T,rtol=0,atol=1e-22)
        self.assertLess(abs(np.trace(jac)),1e-21)

    def test_force_parameter_derivatives(self):
        _,_,_,dp=self.model.evaluate(0,self.state,self.p)
        for k,h in enumerate((1e-5,1e-5,1e-5,1e-5)):
            delta=np.zeros(4);delta[k]=h
            fd=(self.model.evaluate(0,self.state,self.p+delta)[0]-self.model.evaluate(0,self.state,self.p-delta)[0])/(2*h)
            np.testing.assert_allclose(fd,dp[:,k],rtol=1e-8,atol=3e-12)

    def test_acceleration_matches_independent_potential_gradient(self):
        acceleration=self.model.evaluate(0,self.state,self.p)[0]
        gradient=[]
        for k in range(3):
            delta=np.eye(3)[k]*100
            gradient.append((self.model.potential_m2ps2(self.state[:3]+delta,self.p)-self.model.potential_m2ps2(self.state[:3]-delta,self.p))/200)
        np.testing.assert_allclose(acceleration,-np.array(gradient),rtol=0,atol=1e-8)

    def test_invalid_states_parameters_and_bodies(self):
        with self.assertRaises(ValueError):TestForceModel(mu_m3ps2=-1)
        with self.assertRaises(ValueError):FixedThirdBody(1,(0,0,0))
        for state,p in (([26560,0,0,0,0,0],self.p),(self.state,[0,0,0]),(self.state,[np.nan,0,0,0])):
            with self.assertRaises(ValueError):self.model.evaluate(0,state,p)
