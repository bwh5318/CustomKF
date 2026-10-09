"""Independent Stage 3 ingestion, combination, interpolation and geometry tests."""
import io
from pathlib import Path
import tempfile
import unittest
import numpy as np
from customkf.rinex import header,epochs,decode_fields,Observable,read_gps_navigation
from customkf.precise import read_clocks,polynomial_state
from customkf.preprocess import ALPHA,BETA,F1,F2,LAMBDA1,LAMBDA2,C,SignalPair,combinations,ArcTracker,choose_signals
from customkf.measurement import geodetic,enu_matrix,geometry
from customkf.sp3 import epoch_tag


def hline(body,label):return body.ljust(60)+label+"\n"


def obs_header(version=2.11):
    first=f"{version:9.2f}".ljust(20)+"OBSERVATION DATA".ljust(20)+"G".ljust(20)+"RINEX VERSION / TYPE\n"
    lines=[first,hline("  6378137.0 0.0 0.0","APPROX POSITION XYZ"),hline("0 0 0","ANTENNA: DELTA H/E/N"),
           hline("".ljust(48)+"GPS","TIME OF FIRST OBS")]
    if version<3:lines.append(hline("     4    P1    P2    L1    L2","# / TYPES OF OBSERV"))
    else:lines.append(hline("G    4 C1W C2W L1W L2W","SYS / # / OBS TYPES"))
    return "".join(lines)+hline("","END OF HEADER")


class Stage3Tests(unittest.TestCase):
    def test_rinex2_known_fields_missing_and_flags(self):
        row=f"{22000000.:14.3f}  {22000002.:14.3f}  {120000000.:14.3f}14"+" "*16
        stream=io.StringIO(obs_header()+" 26  8  2  0  0  0.0000000  0  1G08\n"+row+"\n")
        meta=header(stream);result=list(epochs(stream,meta))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].gps_ns,epoch_tag("* 2026 8 2 0 0 0"))
        obs=result[0].satellites["G08"]
        self.assertEqual(obs["P1"].value,22000000)
        self.assertEqual((obs["L1"].lli,obs["L1"].strength),(1,4))
        self.assertIsNone(obs["L2"].value)

    def test_rinex3_signal_identifiers_and_epoch(self):
        row="G08"+"".join(f"{v:14.3f}  " for v in (22000000,22000002,120000000,93000000))
        stream=io.StringIO(obs_header(3.05)+"> 2026 08 02 00 00  0.0000000  0  1\n"+row+"\n")
        meta=header(stream);records=list(epochs(stream,meta))
        self.assertEqual(list(records[0].satellites["G08"]),["C1W","C2W","L1W","L2W"])

    def test_comment_event_kept_and_same_time_observation_allowed(self):
        data=obs_header()+" 26  8  2  0  0  0.0000000  4  1\n"+hline("receiver annotation","COMMENT")
        data+=" 26  8  2  0  0  0.0000000  0  1G08\n"+" "*64+"\n"
        stream=io.StringIO(data);meta=header(stream)
        self.assertEqual(len(list(epochs(stream,meta))),1)
        self.assertEqual(len(meta.comment_events),1)

    def test_equipment_event_is_not_silently_ignored(self):
        stream=io.StringIO(obs_header()+" 26  8  2  0  0  0.0000000  4  1\n"+hline("new antenna","ANT # / TYPE"))
        with self.assertRaisesRegex(ValueError,"event 4"):list(epochs(stream,header(stream)))

    def test_truncated_observation_and_unknown_clock_time_fail(self):
        stream=io.StringIO(obs_header()+" 26  8  2  0  0  0.0000000  0  1G08\n")
        with self.assertRaisesRegex(ValueError,"Truncated"):list(epochs(stream,header(stream)))
        with self.assertRaisesRegex(ValueError,"Hatanaka"):header(io.StringIO("3.0 CRINEX VERS / TYPE\n"))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"test.clk"
            path.write_text("     3.00           C".ljust(60)+"RINEX VERSION / TYPE\n"+hline("","END OF HEADER")+
                            "AS G08 2026 08 02 00 00 0.000000 1 1.0E-4\n")
            with self.assertRaisesRegex(ValueError,"Explicit GPS"):read_clocks([path])
            tags,values=read_clocks([path],missing_time_system="GPS")["G08"]
            self.assertEqual(tags[0],epoch_tag("* 2026 8 2 0 0 0"));self.assertEqual(values[0],1e-4)

    def test_navigation_glonass305_extra_line_does_not_shift_gps(self):
        first="     3.05           NAVIGATION DATA     MIXED".ljust(60)+"RINEX VERSION / TYPE\n"
        def block(sat,n):
            return f"{sat} 2026 08 02 00 00 00"+"".join(f"{0.:19.12E}" for _ in range(3))+"\n"+(
                "    "+"".join(f"{1.:19.12E}" for _ in range(4))+"\n")*(n-1)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"nav.rnx";path.write_text(first+hline("","END OF HEADER")+block("R01",5)+block("G08",8))
            nav=read_gps_navigation(path)
            self.assertEqual(list(nav),["G08"]);self.assertEqual(nav["G08"][0]["sqrt_a"],1.)

    def test_if_cancels_dispersive_delay_and_cycle_units(self):
        rho=23000000.;iono1=10.;iono2=iono1*(F1/F2)**2
        obs={k:Observable(v,0,0) for k,v in zip(("P1","P2","L1","L2"),
              (rho+iono1,rho+iono2,(rho-iono1)/LAMBDA1,(rho-iono2)/LAMBDA2))}
        pair=choose_signals(list(obs));data=combinations(obs,pair)
        self.assertAlmostEqual(data["code_if_m"],rho,places=7)
        self.assertAlmostEqual(data["phase_if_m"],rho,places=7)
        self.assertAlmostEqual(np.hypot(ALPHA,BETA),2.978255,places=5)
        obs["L1"]=Observable(obs["L1"].value+1,0,0)
        self.assertAlmostEqual(combinations(obs,pair)["phase_if_m"]-rho,ALPHA*LAMBDA1,places=7)

    def test_antispoofing_flag_does_not_split_arc(self):
        obs={k:Observable(v,4,0) for k,v in zip(("P1","P2","L1","L2"),(23000000,23000000,120000000,93000000))}
        data=combinations(obs,choose_signals(list(obs)))
        self.assertFalse(data["loss_of_lock"]);self.assertFalse(data["half_cycle"])
        tracker=ArcTracker();self.assertEqual(tracker.update(0,"G08",data),tracker.update(30*10**9,"G08",data))

    def test_native_slip_between_decimated_epochs_splits_later_arc(self):
        tracker=ArcTracker();data={"geometry_free_m":1.,"mw_m":2.,"loss_of_lock":False,"half_cycle":False}
        first=tracker.update(0,"G08",data)
        changed={**data,"geometry_free_m":1.+LAMBDA1,"loss_of_lock":True}
        after=tracker.update(30*10**9,"G08",changed)
        for t in range(60,301,30):last=tracker.update(t*10**9,"G08",{**changed,"loss_of_lock":False})
        self.assertNotEqual(first,after);self.assertEqual(last,after)

    def test_unknown_signal_pair_is_not_substituted(self):
        with self.assertRaisesRegex(ValueError,"biases"):choose_signals(["C1","C2","L1","L2"])

    def test_slip_record_without_code_values_splits_next_arc(self):
        tracker=ArcTracker();data={"geometry_free_m":1.,"mw_m":2.,"loss_of_lock":False,"half_cycle":False}
        first=tracker.update(0,"G08",data)
        tracker.observe_epoch_event(15*10**9,["G08"],6)
        second=tracker.update(30*10**9,"G08",data)
        self.assertNotEqual(first,second)
        self.assertIn("slip_record",tracker.events[-1]["reasons"])

    def test_orbit_interpolation_independent_polynomial_and_derivative(self):
        times=np.arange(-4500.,5401,900.);u=times/1000
        positions=np.c_[2e7+100*u+u**3,-1e7+30*u*u,2e7-20*u]
        t=123.4;u=t/1000
        expected=np.array([2e7+100*u+u**3,-1e7+30*u*u,2e7-20*u,(100+3*u*u)/1000,60*u/1000,-.02])
        np.testing.assert_allclose(polynomial_state(times,positions,t),expected,atol=1e-7,rtol=0)
        with self.assertRaises(ValueError):polynomial_state(times,positions,6000)

    def test_geodetic_enu_axes(self):
        lat,lon,h=geodetic([6378137.,0.,0.])
        self.assertEqual((lat,lon,h),(0.,0.,0.))
        np.testing.assert_allclose(enu_matrix([6378137.,0.,0.]),[[0,1,0],[0,0,1],[1,0,0]],atol=1e-15)

    def test_light_time_matches_independent_sagnac_formula_and_shapiro(self):
        omega=7.2921151467e-5
        def rotation(t):
            a=omega*t;c,s=np.cos(a),np.sin(a)
            return np.array([[c,s,0],[-s,c,0],[0,0,1.]])
        sat_fixed=np.array([2e7,1.7e7,1e7]);receiver=np.array([6378137.,0.,0.])
        class Epoch:
            celestial_to_terrestrial=staticmethod(rotation)
        class Products:
            epoch=Epoch()
            def state(self,sat,t):
                r=rotation(t).T@sat_fixed
                return np.r_[r,np.cross([0,0,omega],r)]
            def clock(self,sat,t):return 1e-4
        result=geometry(Products(),"G08",0.,receiver)
        first_order=np.linalg.norm(sat_fixed-receiver)+omega/C*(sat_fixed[0]*receiver[1]-sat_fixed[1]*receiver[0])
        self.assertAlmostEqual(result["geometric_range_m"],first_order,places=3)
        self.assertTrue(.01<result["shapiro_m"]<.03)
        self.assertAlmostEqual(result["satellite_clock_s"],1e-4,places=15)
        # Independent perturbation of receiver geometry, including light time.
        for k in range(3):
            d=np.eye(3)[k]
            measured=(geometry(Products(),"G08",0.,receiver+d)["geometric_range_m"]-
                      geometry(Products(),"G08",0.,receiver-d)["geometric_range_m"])/2
            self.assertLess(abs(measured+result["los_ecef"][k]),2e-5)
