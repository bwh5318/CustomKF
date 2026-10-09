"""Independent sign/scale/rank and published-reference checks for PPP models."""
from datetime import datetime
import io
import tempfile
from pathlib import Path
import unittest
import erfa
import numpy as np
from customkf.square_root import weighted_qr
from customkf.antenna import Calibration,corrections,load_calibrations
from customkf.station_models import mapping,troposphere,ocean_loading,solid_displacement,reference_coordinate
from customkf.rinex import header,epochs
from tests.test_stage3 import obs_header,hline


def tide_reference_cases():
    # Official DEHANTTIDEINEL.F header, first three published test cases.
    # https://iers-conventions.obspm.fr/content/chapter7/software/dehanttideinel/DEHANTTIDEINEL.F
    cases=[((2009,4,13),[4075578.385,931852.890,4801570.154],
        [137859926952.015,54228127881.435,23509422341.696],
        [-179996231.920342,-312468450.131567,-169288918.592160],
        [.07700420357108126,.06304056321824968,.05516568152597247]),
        ((2012,7,13),[1112189.660,-4842955.026,3985352.284],
        [-54537460436.2357,130244288385.279,56463429031.5996],
        [300396716.912,243238281.451,120548075.939],
        [-.02036831479592076,.05658254776225972,-.07597679676871742]),
        ((2015,7,15),[1112200.5696,-4842957.8511,3985345.9122],
        [100210282451.6279,103055630398.3160,56855096480.4475],
        [369817604.4348,1897917.5258,120804980.8284],
        [.005095708691723638,.08286630259835287,-.06366349254041896])]
    result=[]
    for date,xyz,sun,moon,expected in cases:
        utc=erfa.dtf2d("UTC",*date,0,0,0.)
        tt=erfa.taitt(*erfa.utctai(*utc))
        # UT1=UTC approximation is confined to this check; production uses EOP.
        actual=solid_displacement(np.array(xyz),np.array(sun),np.array(moon),erfa.gmst06(*utc,*tt))
        result.append({"date":"%04d-%02d-%02d"%date,"reference_m":expected,
                       "reduced_model_m":actual.tolist(),"difference_m":(actual-expected).tolist(),
                       "difference_norm_m":float(np.linalg.norm(actual-expected))})
    return result


class Stage3ModelTests(unittest.TestCase):
    def test_weighted_qr_analytic_means_and_extreme_column_scaling(self):
        # Two independently observed constants; analytic inverse-variance means.
        a=np.array([[1.,0],[1,0],[0,1],[0,1]])
        y=np.array([1.,5.,-2.,4.]);sigma=np.array([1.,2.,3.,1.])
        expected=np.array([(1+5/4)/(1+1/4),(-2/9+4)/(1/9+1)])
        for scales in ([1.,1.],[1e-9,1e9]):
            answer,rank=weighted_qr(a*scales,y,sigma)
            np.testing.assert_allclose(answer*scales,expected,atol=1e-13,rtol=0)
            self.assertEqual(rank,2)

    def test_weighted_qr_rejects_rank_loss_and_bad_weights(self):
        with self.assertRaisesRegex(ValueError,"Rank deficient"):
            weighted_qr(np.ones((4,2)),np.ones(4),np.ones(4))
        for sigma in ([1,0],[1,np.nan]):
            with self.assertRaises(ValueError):weighted_qr(np.eye(2),np.ones(2),sigma)
        with self.assertRaises(ValueError):weighted_qr(np.empty((2,0)),np.ones(2),np.ones(2))

    def test_rinex401_observation_compatibility(self):
        row="G08"+"".join(f"{v:14.3f}  " for v in (22e6,22e6,120e6,93e6))
        stream=io.StringIO(obs_header(4.01)+"> 2026 08 02 00 00  0.0000000  0  1\n"+row+"\n")
        meta=header(stream);self.assertEqual(meta.version,4.01)
        self.assertEqual(next(epochs(stream,meta)).satellites["G08"]["C1W"].value,22e6)

    def test_antex_pco_sign_and_pcv_azimuth_interpolation(self):
        def cal(pco):
            return Calibration("test","","",{f:{"pco":np.array(pco),"noazi":np.zeros(2),"azimuth":{}}
                                                   for f in ("G01","G02")},np.array([0.,90.]),0.)
        receiver=np.array([6378137.,0,0])
        g={"satellite_inertial":np.array([26560000.,0,0,0,3000,0]),"los_ecef":np.array([1.,0,0]),
           "elevation_rad":np.pi/2,"azimuth_rad":0.}
        # Receiver up +1 m and satellite body z (toward Earth) +2 m shorten range by 3 m.
        correction,phase=corrections(g,receiver,cal([0,0,1]),cal([0,0,2]),np.array([0,1.5e11,0]),np.eye(3))
        self.assertAlmostEqual(correction,-3.,places=12);self.assertTrue(np.isfinite(phase))
        self.assertAlmostEqual(phase,-.25,places=12)
        phases=[]
        for angle in np.linspace(0,2*np.pi,33):
            sun=1.5e11*np.array([0,np.cos(angle),np.sin(angle)])
            phases.append(corrections(g,receiver,cal([0,0,0]),cal([0,0,0]),sun,np.eye(3))[1])
        unwrapped=np.unwrap(2*np.pi*np.array(phases))/(2*np.pi)
        self.assertAlmostEqual(abs(unwrapped[-1]-unwrapped[0]),1.,places=12)
        c=cal([0,0,0]);c.frequencies["G01"]["azimuth"]={0.:np.array([0.,.02]),180.:np.array([.02,.04]),360.:np.array([0.,.02])}
        self.assertAlmostEqual(c.variation("G01",45,90),.02)
        self.assertEqual(c.variation("G01",45,0),c.variation("G01",45,360))
        with self.assertRaises(ValueError):c.variation("G01",100)

    def test_antex_units_validity_and_exact_radome(self):
        def block(serial,start):
            lines=[hline("","START OF ANTENNA"),hline("BLOCK IIF".ljust(20)+serial.ljust(20)+"G065","TYPE / SERIAL NO"),
                   hline("0","DAZI"),hline("0 90 90","ZEN1 / ZEN2 / DZEN"),hline(start,"VALID FROM")]
            for freq in ("G01","G02"):
                lines += [hline(freq,"START OF FREQUENCY"),hline("1 2 3000","NORTH / EAST / UP"),
                          "   NOAZI 0 10\n",hline(freq,"END OF FREQUENCY")]
            return "".join(lines)+hline("","END OF ANTENNA")
        text=hline("1.4","ANTEX VERSION / SYST")+hline("A","PCV TYPE / REFANT")
        text+=block("G01","1978 1 1 0 0 0")+block("G02","2099 1 1 0 0 0")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"test.atx";path.write_text(text)
            sats,rx=load_calibrations(path,[],0)
            self.assertEqual(set(sats),{"G01"})
            np.testing.assert_array_equal(sats["G01"].frequencies["G01"]["pco"],[.001,.002,3.])
            self.assertAlmostEqual(sats["G01"].variation("G01",45),.005)
            with self.assertRaisesRegex(ValueError,"exact receiver"):
                load_calibrations(path,["UNKNOWN         NONE"],0)

    def test_mapping_zenith_unity_and_ocean_direction_phase(self):
        self.assertAlmostEqual(mapping(np.pi/2,[.001,.003,.06]),1.)
        _,wet=troposphere([6378137.,0,0],np.pi/2,214);self.assertAlmostEqual(wet,1.)
        # Only S2 at UTC midnight: phase 0 gives amplitude, phase 180 reverses it.
        loading=np.zeros((6,11));loading[:3,1]=[1,2,3]
        np.testing.assert_allclose(ocean_loading(60000.,loading),[-2,-3,1],atol=1e-14)
        loading[3:,1]=180
        np.testing.assert_allclose(ocean_loading(60000.,loading),[2,3,-1],atol=1e-14)

    def test_reduced_solid_tides_against_published_iers_vectors(self):
        # A 20 mm approximation bound, deliberately not a full IERS conformance test.
        for case in tide_reference_cases():self.assertLess(case["difference_norm_m"],.020,case)

    def test_reference_coordinate_active_solution_and_velocity(self):
        with tempfile.TemporaryDirectory() as tmp:
            ssc=Path(tmp)/"c";sol=Path(tmp)/"s"
            sol.write_text(" TEST A 1 P 00:001:00000 20:001:00000 P -\n TEST A 2 P 20:001:00000 00:000:00000 P -\n")
            ssc.write_text("".join(f" {i} {kind}{axis} TEST A 2 20:001:00000 m 2 {value} 0\n"
                for i,(kind,axis,value) in enumerate([(k,a,v) for k,vals in [("STA",[10,20,30]),("VEL",[1,2,3])]
                                                     for a,v in zip("XYZ",vals)])))
            xyz,solution=reference_coordinate(ssc,sol,"TEST",datetime(2021,1,1))
            np.testing.assert_allclose(xyz,np.array([10,20,30])+366/365.25*np.array([1,2,3]))
            self.assertEqual(solution,2)
            with self.assertRaises(ValueError):reference_coordinate(ssc,sol,"MISS",datetime(2021,1,1))
