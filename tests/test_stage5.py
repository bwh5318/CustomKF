"""Independent broadcast and dynamic-observation closure checks."""
import unittest
import numpy as np
from customkf.broadcast import position, select_record, clock, MU, OMEGA
from customkf.dynamic_observation import Trajectory, DynamicProducts, modeled_link, link_jacobian
from customkf.antenna import Calibration


def record(**updates):
    r={k:0. for k in ("m0","delta_n","omega","cuc","cus","crc","crs","cic","cis","i0","idot","omega0","omega_dot",
                       "toe","week","af0","af1","af2","health","gps_ns")}
    r.update(sqrt_a=np.sqrt(26560000.),e=0.)
    r.update(updates)
    return r


class Central:
    mu_m3ps2=MU
    parameter_scales=np.ones(5)*1e-7
    def evaluate(self,t,state,p,partials=True):
        r=state[:3];length=np.linalg.norm(r)
        a=-MU*r/length**3
        return (a,MU*(3*np.outer(r,r)/length**5-np.eye(3)/length**3),np.zeros((3,3)),np.zeros((3,5))) if partials else (a,None,None,None)


class StaticEpoch:
    def celestial_to_terrestrial(self,t):return np.eye(3)
    def tdb_seconds(self,t):return t


class Bodies:
    def sun_moon_m(self,t):return np.array([1e11,1e11,4e10]),np.array([3e8,1e8,1e8])


def calibration():
    return Calibration("test","","",{f:{"pco":np.array([.1,.2,1.]),"noazi":np.array([0.,.005]),"azimuth":{}}
                                           for f in ("G01","G02")},np.array([0.,90.]),0.)


class Stage5Tests(unittest.TestCase):
    def test_estimator_precise_product_access_policy(self):
        from customkf.stage5_pilot import forbid_precise_product_reads
        for path in ("target.SP3.gz",b"target.CLK.gz"):
            with self.assertRaises(RuntimeError):forbid_precise_product_reads("open",(path,"r",0))
        forbid_precise_product_reads("open",("observation.rnx.gz","r",0))

    def test_current_healthy_broadcast_clock_record_selection(self):
        old=record(af0=1e-5)
        new=record(gps_ns=7200*10**9,toe=7200.,af0=2e-5)
        bad=record(gps_ns=7300*10**9,toe=7300.,af0=3e-5,health=1)
        products=DynamicProducts(StaticEpoch(),0,{"G01":[old,new,bad]}, {})
        self.assertAlmostEqual(products.clock("G01",7199.),1e-5)
        self.assertAlmostEqual(products.clock("G01",15000.),2e-5)
        with self.assertRaises(ValueError):products.clock("G01",22000.)

    def test_broadcast_circular_analytic(self):
        a=26560000.;n=np.sqrt(MU/a**3)
        for t in (0.,1200.,7200.):
            expected=a*np.array([np.cos((n-OMEGA)*t),np.sin((n-OMEGA)*t),0.])
            np.testing.assert_allclose(position(record(),int(t*1e9)),expected,atol=1e-6,rtol=0)

    def test_broadcast_perigee_quadrature_and_harmonics(self):
        r=record(e=.01,m0=0.,crc=20.,cuc=.001,cic=.002,i0=.8)
        radius=26560000.*.99+20.
        expected=radius*np.array([np.cos(.001),np.sin(.001)*np.cos(.802),np.sin(.001)*np.sin(.802)])
        np.testing.assert_allclose(position(r,0),expected,atol=1e-6,rtol=0)

    def test_full_week_boundary_and_age(self):
        r=record(week=2200,toe=604790.,gps_ns=int((2200*604800+604790)*1e9))
        tag=int((2201*604800+10)*1e9)
        self.assertIs(select_record([r],tag),r)
        self.assertTrue(np.isfinite(position(r,tag)).all())
        with self.assertRaises(ValueError):position(r,tag+int(5*3600*1e9))
        with self.assertRaises(ValueError):select_record([r],tag-int(100*1e9))

    def test_clock_polynomial_has_no_extra_relativity_or_tgd(self):
        r=record(af0=1e-5,af1=2e-12,af2=3e-18,tgd=5e-9)
        self.assertAlmostEqual(clock(r,1000*10**9),1e-5+2e-9+3e-12,places=18)
        with self.assertRaises(ValueError):clock(r,20000*10**9)

    def test_dynamic_state_and_velocity_use_same_curve(self):
        initial=np.array([26560000.,1e6,2e6,0.,3800.,100.])
        trajectory=Trajectory(initial,Central(),300.)
        t=132.125;h=.1
        derivative=(trajectory.state(t+h)[:3]-trajectory.state(t-h)[:3])/(2*h)
        np.testing.assert_allclose(derivative,trajectory.state(t)[3:],atol=2e-6,rtol=0)
        with self.assertRaises(ValueError):trajectory.state(-.1)
        np.testing.assert_allclose(trajectory.state(0),initial,atol=1e-12)

    def test_full_link_partials_against_independent_reintegration(self):
        initial=np.array([26560000.,1e6,2e6,0.,3800.,100.])
        trajectory=Trajectory(initial,Central(),300.)
        # Deliberately amplified clock slope makes missing chain-rule terms
        # visible; it is an algebra stress case, not a physical GPS clock.
        products=DynamicProducts(StaticEpoch(),0,{"G01":record(af1=2e-5)},{"G01":trajectory})
        # The synthetic origin is not the stage-5 origin, so the row declares its date (OBS-01): the former Aug 2 values.
        row={"satellite":"G01","time_s":132.125,"receiver_xyz":np.array([6378137.,0.,0.]),
             "origin_doy":214,"origin_second_of_day":43190}
        cal=calibration();bodies=Bodies()
        reference=modeled_link(products,row,cal,cal,bodies,20.,-5.,.1,15.)[2]
        jac,cjac=link_jacobian(products,row,cal,cal,bodies,20.,-5.,.1,15.,reference)
        delta=np.array([100.,-70.,40.,.01,-.02,.015])
        differences=[]
        for factor in (1.,.1):
            values=[]
            for sign in (1,-1):
                perturbed=DynamicProducts(StaticEpoch(),0,{"G01":record(af1=2e-5)},
                    {"G01":Trajectory(initial+sign*factor*delta,Central(),300.)})
                values.append(modeled_link(perturbed,row,cal,cal,bodies,20.,-5.,.1,15.,reference)[0])
            differences.append(float(np.max(np.abs((values[0]-values[1])/2-jac@(factor*delta)))))
        self.assertLess(max(differences),5e-5)
        self.assertLess(np.max(np.abs(cjac-1.)),1e-4)


if __name__=="__main__":unittest.main()
