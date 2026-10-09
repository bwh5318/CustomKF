"""Independent geometry, ephemeris, force, and estimator checks for Stage 2."""
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
import erfa
from customkf.prepare_stage2 import DATA
from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation,FrameEpoch,Environment
from customkf.sp3 import epoch_tag
from customkf.gravity import acceleration,read_gravity
from customkf.dynamics import TestForceModel
from customkf.orbit_forces import OrbitForceModel,srp_basis,shadow_fraction,AU
from customkf.fitting import fit_orbit


class Stage2Tests(unittest.TestCase):
    def test_sp3_export_columns_missing_clocks_and_prediction_flags(self):
        from customkf.export_stage2 import write_fit_sp3
        from customkf.sp3 import read_sp3
        epochs=epoch_tag("* 2026 8 2 0 0 0")+np.array([0,900*10**9],dtype=np.int64)
        xyz=np.array([[2.2e7+.0004,-1.1e7,1.4e7],[2.1e7,-1.2e7,1.5e7]])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"fit.sp3"
            write_fit_sp3(path,"G08",epochs,xyz,frame="IGc20",predicted=[False,True])
            lines=path.read_text().splitlines()
            self.assertEqual(lines[0][46:51],"IGc20")
            self.assertEqual(lines[2][4:6]," 1")
            self.assertEqual(lines[2][9:12],"G08")
            self.assertEqual(lines[12][9:12],"GPS")
            product=read_sp3(path)
            for i,record in enumerate(product.samples.values()):
                self.assertEqual(record.epoch_ns,epochs[i])
                np.testing.assert_allclose(record.xyz_m,xyz[i],rtol=0,atol=.000501)
                self.assertIsNone(record.clock_s)
                self.assertEqual(record.orbit_predicted,bool(i))
            with self.assertRaises(ValueError):write_fit_sp3(path,"G08",epochs,xyz*np.nan,frame="IGc20")

    @classmethod
    def setUpClass(cls):
        if not all((DATA/name).is_file() for name in ("finals2000A.all","de440s.bsp")):
            raise unittest.SkipTest("needs data/stage2 (run customkf.prepare_stage2; SETUP.md section 5)")
        cls.eop=EarthOrientation(DATA/"finals2000A.all")
        cls.epoch=FrameEpoch(epoch_tag("* 2026 8 2 0 0 0"),cls.eop)
        cls.ephemeris=DE440(DATA/"de440s.bsp")
        cls.environment=Environment(cls.epoch,cls.ephemeris,3600.)
        cls.model=OrbitForceModel(cls.environment,DATA/"EGM2008_degree12.gfc")

    def test_type2_reader_against_analytic_chebyshev_record(self):
        raw=bytearray(4096);raw[:8]=b"DAF/SPK ";raw[88:96]=b"LTL-IEEE"
        struct.pack_into("<ii",raw,8,2,6);struct.pack_into("<i",raw,76,2)
        struct.pack_into("<ddd",raw,1024,0,0,1)
        struct.pack_into("<ddiiiiii",raw,1048,0,20,301,399,1,2,385,399)
        values=[10,10,10,3,2,20,4,-2,30,-5,.5,0,20,11,1]
        struct.pack_into("<15d",raw,3072,*values)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"synthetic.bsp";path.write_bytes(raw)
            reader=DE440(path)
            np.testing.assert_array_equal(reader.position_km(399,301,10),[8,22,29.5])
            np.testing.assert_array_equal(reader.position_km(399,301,0),[9,14,35.5])
            with self.assertRaises(ValueError):reader.position_km(399,301,21)
            del reader

    def test_de440_against_independent_horizons_de441(self):
        # Explicitly allow a small DE440/DE441 difference; query is geometric ICRF.
        calculated=self.ephemeris.sun_moon_m((2461254.5-2451545.)*86400)
        for name,position in zip(("sun","moon"),calculated):
            text=(DATA/f"horizons_{name}.txt").read_text()
            self.assertIn("{source: DE441}",text)
            row=text.split("$$SOE\n")[1].splitlines()[0].split(",")
            expected=np.array([float(x) for x in row[2:5]])*1000
            self.assertLess(np.linalg.norm(position-expected),10.,name)

    def test_official_erfa_c2t06a_vector_and_composition(self):
        a,b=2400000.5,53736.;xp,yp=2.55060238e-7,1.860359247e-6
        expected=np.array([[-.1810332128305897282,.9834769806938592296,.6555550962998436505e-4],
            [-.9834768134136214897,-.1810332203649130832,.5749800844905594110e-3],
            [.5773474024748545878e-3,.3961816829632690581e-4,.9999998325501747785]])
        x,y,s=erfa.xys06a(a,b)
        actual=erfa.c2tcio(erfa.c2ixys(x,y,s),erfa.era00(a,b),erfa.pom00(xp,yp,erfa.sp00(a,b)))
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-12)

    def test_gpst_tt_utc_offsets_and_rotation_inverse(self):
        tai=erfa.tttai(self.epoch.tt1,self.epoch.tt2)
        utc=erfa.taiutc(*tai)
        y,m,d,time=erfa.d2dtf("UTC",3,*utc)
        self.assertEqual((y,m,d,time["h"],time["m"],time["s"]),(2026,8,1,23,59,42))
        self.assertAlmostEqual(self.epoch.tt2*86400,51.184,places=10)
        r=self.epoch.celestial_to_terrestrial(1234.56)
        np.testing.assert_allclose(r@r.T,np.eye(3),atol=5e-16,rtol=0)

    def test_eop_no_prediction_extrapolation_and_leap_continuity(self):
        with self.assertRaises(ValueError):self.eop.at(90000)
        # Across 2016-12-31: UT1-UTC jumps by a second; UT1-TAI is smooth.
        a=self.eop.at(57753.)[2];b=self.eop.at(57754.)[2];mid=self.eop.at(57753.5)[2]
        self.assertAlmostEqual(mid,(a+b-1)/2,places=9)

    def test_environment_interpolation_and_ephemeris_outside_arc(self):
        r,sun,moon=self.environment.at(123.45)
        exact=self.epoch.celestial_to_terrestrial(123.45)
        self.assertLess(np.max(np.abs(r-exact))*26560000,.0001)
        direct=self.ephemeris.sun_moon_m(self.epoch.tdb_seconds(123.45))
        self.assertLess(np.linalg.norm(sun-direct[0]),.02)
        self.assertLess(np.linalg.norm(moon-direct[1]),.002)
        with self.assertRaises(ValueError):self.environment.at(10000)

    def test_normalized_gravity_reduces_to_stage1_j2(self):
        mu,radius,c,s,norms=read_gravity(DATA/"EGM2008_degree12.gfc")
        j2=-c[2,0];low=np.zeros_like(c);low[0,0]=1;low[2,0]=c[2,0]
        state=np.array([2.2e7,-1.1e7,1.4e7,1000,2000,-3000.])
        expected=TestForceModel(mu_m3ps2=mu,radius_m=radius).evaluate(0,state,[j2,0,0,0])[0]
        np.testing.assert_allclose(acceleration(state[:3],mu,radius,low,np.zeros_like(s)),expected,atol=3e-16,rtol=0)
        self.assertEqual(norms[2,0],np.sqrt(5))

    def test_dyb_axes_shadow_and_harmonic_parameter_order(self):
        state=np.array([26560000.,0,0,0,2200.,3100.]);sun=np.array([1e11,1e11,8e10])
        basis=srp_basis(state,sun,5)
        factor=(AU/np.linalg.norm(sun-state[:3]))**2
        axes=basis[:,:3]/factor
        np.testing.assert_allclose(axes.T@axes,np.eye(3),atol=1e-15)
        self.assertAlmostEqual(np.linalg.det(axes),1,places=14)
        self.assertEqual(shadow_fraction(np.array([-26560000.,0,0]),np.array([AU,0,0])),0)
        self.assertEqual(shadow_fraction(np.array([26560000.,0,0]),np.array([AU,0,0])),1)
        self.assertAlmostEqual((np.linalg.norm(basis[:,3])**2+np.linalg.norm(basis[:,4])**2)/factor**2,1,places=14)

    def test_force_partials_independent_finite_difference_scales(self):
        state=np.array([2.2e7,-1.1e7,1.4e7,1000,2000,-3000.]);p=np.array([-1e-7,2e-10,-3e-10,1e-9,-1e-9])
        _,dr,dv,dp=self.model.evaluate(234.,state,p)
        for factor in (1.,.1):
            for k in range(6):
                h=(1000. if k<3 else 1.)*factor;delta=np.zeros(6);delta[k]=h
                difference=(self.model.evaluate(234.,state+delta,p,partials=False)[0]-self.model.evaluate(234.,state-delta,p,partials=False)[0])/(2*h)
                np.testing.assert_allclose(difference,(dr if k<3 else dv)[:,k%3],rtol=1e-6,atol=3e-16)
        for k in range(5):
            delta=np.eye(5)[k]*1e-8
            difference=(self.model.evaluate(234.,state,p+delta,partials=False)[0]-self.model.evaluate(234.,state,p-delta,partials=False)[0])/2e-8
            np.testing.assert_allclose(difference,dp[:,k],rtol=1e-7,atol=1e-8)

    def test_qr_fit_recovers_independent_polynomial_trajectory(self):
        class ConstantModel:
            mu_m3ps2=3.986004418e14
            parameter_scales=np.full(3,1e-7)
            def evaluate(self,t,x,p,partials=True):
                return np.asarray(p),np.zeros((3,3)),np.zeros((3,3)),np.eye(3)
        initial=np.array([2.2e7,-1.1e7,1.4e7,1000,2000,-3000.]);p=np.array([1e-7,-2e-7,3e-7])
        times=np.arange(0,3601,300.)
        positions=initial[:3]+times[:,None]*initial[3:]+.5*times[:,None]**2*p
        result=fit_orbit(times,positions,ConstantModel(),initial=initial+np.array([100,-50,20,.01,-.02,.03]),parameters=np.zeros(3))
        self.assertTrue(result.converged)
        self.assertEqual(result.rank,9)
        np.testing.assert_allclose(result.initial_state,initial,atol=1e-6,rtol=0)
        np.testing.assert_allclose(result.parameters,p,atol=1e-13,rtol=0)

    def test_qr_fit_rejects_rank_deficiency(self):
        class DegenerateModel:
            mu_m3ps2=3.986004418e14
            parameter_scales=np.full(2,1e-7)
            def evaluate(self,t,x,p,partials=True):
                return np.array([p.sum(),0,0]),np.zeros((3,3)),np.zeros((3,3)),np.array([[1.,1.],[0,0],[0,0]])
        initial=np.array([2.2e7,0,1e7,1000,2000,0.]);times=np.arange(0,3601,300.)
        positions=initial[:3]+times[:,None]*initial[3:]
        with self.assertRaisesRegex(ValueError,"Rank-deficient"):
            fit_orbit(times,positions,DegenerateModel(),initial=initial,parameters=np.zeros(2))
