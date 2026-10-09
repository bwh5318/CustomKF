from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from customkf.sp3 import Sample, Product, read_sp3, epoch_tag, matched_samples


def text_fixture(*, epoch="0.00000001", frame="IGc20", system="GPS", row=None, version="c"):
    header = list(" "*60)
    header[0:3] = list(f"#{version}P")
    header[32:39] = list(f"{1:7d}")
    header[46:51] = list(f"{frame:5s}")
    record = row or "PG01"+"".join(f"{x:14.6f}" for x in (26560,0,0,2))
    return "".join(header)+f"\n%c G  cc {system} ccc\n*  2026  8  2  0  0 {epoch}\n"+record+"\nEOF\n"


class Sp3Tests(unittest.TestCase):
    def parse(self,text,**kwargs):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"input.sp3"
            path.write_text(text,encoding="ascii")
            return read_sp3(path,**kwargs)

    def test_units_and_exact_epoch(self):
        p = self.parse(text_fixture())
        sample = next(iter(p.samples.values()))
        self.assertEqual(sample.xyz_m,(26560000.,0.,0.))
        self.assertEqual(sample.clock_s,2e-6)
        self.assertEqual(sample.epoch_ns%10**9,10)
        self.assertEqual(p.frame,"IGc20")

    def test_zero_component_is_valid_but_zero_vector_missing(self):
        p = self.parse(text_fixture(row="PG01"+"".join(f"{x:14.6f}" for x in (0,0,0,999999.999999))))
        sample = next(iter(p.samples.values()))
        self.assertIsNone(sample.xyz_m)
        self.assertIsNone(sample.clock_s)

    def test_bad_z_not_only_x_and_y(self):
        p = self.parse(text_fixture(row="PG01"+"".join(f"{x:14.6f}" for x in (1,2,999999.999999,0))))
        self.assertIsNone(next(iter(p.samples.values())).xyz_m)

    def test_event_columns(self):
        row = list(("PG01"+"".join(f"{x:14.6f}" for x in (26560,0,0,0))).ljust(80))
        for pos,char in ((74,"E"),(75,"P"),(78,"M"),(79,"P")):row[pos]=char
        sample = next(iter(self.parse(text_fixture(row="".join(row))).samples.values()))
        self.assertTrue(sample.clock_event and sample.clock_predicted and sample.maneuver and sample.orbit_predicted)

    def test_time_system_must_be_explicit(self):
        with self.assertRaises(ValueError):self.parse(text_fixture(system="UTC"))
        with self.assertRaises(ValueError):self.parse(text_fixture(system="ccc",version="a"))
        self.assertEqual(self.parse(text_fixture(system="ccc",version="a"),legacy_a_time_system="GPS").time_system,"GPS")

    def test_no_duplicate_or_truncated_silence(self):
        text = text_fixture()
        row = text.splitlines()[-2]
        with self.assertRaises(ValueError):self.parse(text.replace("EOF",row+"\nEOF"))
        with self.assertRaises(ValueError):self.parse(text.replace("EOF\n",""))
        with self.assertRaises(ValueError):self.parse(text.replace(row,row[:50]))

    def test_bad_epoch_and_nonfinite_rejected(self):
        for sec in ("60.0","0.0000000001","-1"):
            with self.assertRaises(ValueError):epoch_tag(f"* 2026 8 2 0 0 {sec}")
        with self.assertRaises(ValueError):self.parse(text_fixture(row="PG01"+"".join(f"{x:14.6f}" for x in (float('nan'),1,2,3))))

    def test_exact_matching_and_explicit_exclusions(self):
        a = Sample(0,"G01",(26560000,0,0),None)
        b = replace(a,epoch_ns=1)
        event = replace(a,epoch_ns=2,maneuver=True)
        ref = Product("c","IGc20","GPS",{(x.epoch_ns,x.sat):x for x in (a,event)},[],0)
        cmp = Product("c","IGc20","GPS",{(x.epoch_ns,x.sat):x for x in (a,b,event)},[],0)
        rows,counts = matched_samples(ref,cmp,position_origin=("COM","COM"))
        self.assertEqual(len(rows),1)
        self.assertEqual(counts["candidate_only"],1)
        self.assertEqual(counts["orbit_event_or_prediction"],1)
        rows,counts = matched_samples(ref,cmp,position_origin=("COM","COM"),exclude_satellite_days={(0,"G01")})
        self.assertEqual(counts["declared_exclusion"],1)
        with self.assertRaises(ValueError):matched_samples(ref,replace(cmp,frame="WGS84"),position_origin=("COM","COM"))
        with self.assertRaises(ValueError):matched_samples(ref,cmp,position_origin=("APC","COM"))

    def test_sp3_to_rac_and_clock_known_answer(self):
        import numpy as np
        from customkf.comparison import rac_difference, clock_sisre_m
        ref = self.parse(text_fixture())
        row = "PG01"+"".join(f"{x:14.6f}" for x in (26560.000010,-.000020,.000030,2.001))
        cmp = self.parse(text_fixture(row=row))
        pairs, _ = matched_samples(ref,cmp,position_origin=("COM","COM"))
        a,b = pairs[0]
        rac = rac_difference(a.xyz_m,b.xyz_m,[0,3874,0])
        np.testing.assert_allclose(rac,[.01,-.02,.03],rtol=0,atol=3e-9)
        dt = b.clock_s-a.clock_s
        self.assertAlmostEqual(dt,1e-9,places=18)
        expected = np.sqrt((.98*.01-.299792458)**2+(.02**2+.03**2)/49)
        self.assertAlmostEqual(float(clock_sisre_m(rac,dt)),expected,places=8)
