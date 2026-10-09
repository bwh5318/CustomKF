"""GPS reference time is a fit epoch, not a first-received timestamp."""
import unittest
import numpy as np
from customkf.broadcast import select_fit_record
from customkf.diagnose_stage5 import offset_inertial
from customkf.preprocess import ALPHA, BETA
from tests.test_stage5 import record, calibration


class NavigationFitTests(unittest.TestCase):
    def test_nominal_if_antenna_offset_axes_and_sign(self):
        cal=calibration()
        cal.frequencies["G01"]["pco"]=np.array([.1,.2,1.])
        cal.frequencies["G02"]["pco"]=np.array([.3,.4,2.])
        # Earth radial +X, Sun direction +Y: body x=+Y, y=-Z, z=-X.
        r=np.array([26560000.,0.,0.]);sun=r+np.array([0.,1e11,0.])
        expected=ALPHA*np.array([-1.,.1,-.2])+BETA*np.array([-2.,.3,-.4])
        np.testing.assert_allclose(offset_inertial(r,sun,cal),expected,rtol=0,atol=1e-14)

    def example(self, hour, **kwargs):
        return record(gps_ns=int(hour*3600e9),toe=hour*3600.,fit_interval=4.,transmission_time=max(0.,(hour-2)*3600),**kwargs)

    def test_future_reference_time_is_valid(self):
        old,new=self.example(8),self.example(12)
        self.assertIs(select_fit_record([old,new],int(43190e9),available_before_ns=int(45000e9)),new)

    def test_four_hours_is_total_fit_span(self):
        r=self.example(8)
        for t in (6*3600,10*3600):self.assertIs(select_fit_record([r],int(t*1e9),available_before_ns=int(40000e9)),r)
        with self.assertRaises(ValueError):select_fit_record([r],int(11*3600e9),available_before_ns=int(40000e9))

    def test_cutoff_and_unsupported_profiles(self):
        r=self.example(12)
        with self.assertRaises(ValueError):select_fit_record([r],int(43190e9),available_before_ns=int(43190e9))
        for key,value in (("health",1),("fit_interval",6),("toe",43184.),("transmission_time",60000.)):
            bad=r.copy();bad[key]=value
            with self.assertRaises(ValueError):select_fit_record([bad],int(43190e9),available_before_ns=int(45000e9))

    def test_continuous_week_boundary(self):
        r=record(week=2201,toe=0.,gps_ns=int(2201*604800e9),fit_interval=4.,transmission_time=597600.)
        tag=int((2201*604800-10)*1e9)
        self.assertIs(select_fit_record([r],tag,available_before_ns=tag+int(60e9)),r)


if __name__=="__main__":unittest.main()
