"""Navigation applicability and already-applied RINEX correction regressions."""
import io
import unittest
from customkf.rinex import header, epochs
from customkf.nominal_navigation import NominalProducts
from tests.test_stage3 import obs_header,hline
from tests import test_navigation_fit as navigation_tests
from tests.test_stage5 import StaticEpoch


class Stage5bInputTests(unittest.TestCase):
    def test_reported_phase_shift_is_not_applied_twice(self):
        h=obs_header(3.05).replace(hline("","END OF HEADER"),hline("G L2W -0.25000","SYS / PHASE SHIFT")+hline("","END OF HEADER"))
        row="G08"+"".join(f"{v:14.3f}  " for v in (22000000,22000002,120000000,93000000))
        stream=io.StringIO(h+"> 2026 08 02 00 00  0.0000000  0  1\n"+row+"\n")
        meta=header(stream,allow_declared_phase_shifts=True)
        self.assertEqual(meta.phase_shift_metadata[0]["applied_cycles"],-.25)
        self.assertEqual(next(epochs(stream,meta)).satellites["G08"]["L2W"].value,93000000.)
        with self.assertRaises(ValueError):header(io.StringIO(h))

    def test_incomplete_satellite_shift_list_fails(self):
        h=obs_header(3.05).replace(hline("","END OF HEADER"),hline("G L2W -0.25000    2 G08","SYS / PHASE SHIFT")+hline("","END OF HEADER"))
        with self.assertRaises(ValueError):header(io.StringIO(h),allow_declared_phase_shifts=True)

    def test_clock_uses_applicable_future_reference(self):
        maker=navigation_tests.NavigationFitTests();old=maker.example(8);new=maker.example(12)
        old["af0"]=1e-5;new["af0"]=2e-5
        p=NominalProducts(StaticEpoch(),0,{"G08":[old,new]}, {},available_before_ns=int(86400e9))
        self.assertAlmostEqual(p.clock("G08",43190),2e-5)
        with self.assertRaises(ValueError):p.clock("G08",18*3600)


if __name__=="__main__":unittest.main()
