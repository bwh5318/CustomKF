"""Refusal paths of the 27-28 Sep review fixes (Opus_Fork/results/CORRECTIONS.md: C01, M11, N05).

    C:\\anaconda\\python.exe -m unittest tests.test_review_fix_refusals -v

Synthetic step/provenance files only: every refusal fires before a solution is read or an orbit is integrated,
and the accepted paths replace the scoring/model loaders with stubs. `check_fixes` (under the guard) covers the
numerical round trip against real solutions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest import mock
import unittest

from Opus_Fork import evaluate, export, ngv_pilot
from Opus_Fork.export import KNOWN_SUBDAILY

KNOWN = next(iter(KNOWN_SUBDAILY))
needs_eop = unittest.skipUnless((Path(__file__).resolve().parents[1]/"data/stage2/finals2000A.all").is_file(),
                   "needs data/stage2/finals2000A.all (run customkf.prepare_stage2; SETUP.md section 5)")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Case(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="refusals-"))
        self.solution_dir = self.root/"run"/"lin2-solve"
        self.solution_dir.mkdir(parents=True)
        self.solution = self.solution_dir/"solution.npz"
        self.solution.write_bytes(b"stand-in solution bytes")
        self.fixture = self.root/"fixture.json"
        self.fixture.write_text(json.dumps({"context": {"origin_ns": 1469750390000000000}}))
        self.other_fixture = self.root/"other_fixture.json"
        self.other_fixture.write_text(json.dumps({"context": {"origin_ns": 1}}))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def step(self, status="converged", solution_sha=None, fixture=True, model=None):
        step = dict(status=status, solution_sha256=solution_sha or digest(self.solution))
        if fixture:
            step["binding"] = dict(fixture=digest(self.fixture))
        (self.solution_dir/"step.json").write_text(json.dumps(step))
        if model is not None:
            (self.solution_dir/"force_model.json").write_text(json.dumps(model))


class ExportRefusals(Case):
    def args(self, fixture=None, **extra):
        return argparse.Namespace(solution=str(self.solution_dir), fixture=str(fixture or self.fixture),
                                  day="2026-08-02", cadence=900., out=None, **extra)

    def test_unconverged_refused(self):
        self.step(status="iteration_complete", model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "verified converged"):
            export.write_from_solution(self.args(), self.root)

    def test_hash_mismatch_refused(self):
        self.step(solution_sha="0"*64, model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "verified converged"):
            export.write_from_solution(self.args(), self.root)

    def test_wrong_fixture_refused(self):
        self.step(model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "not the one bound"):
            export.write_from_solution(self.args(fixture=self.other_fixture), self.root)

    @needs_eop
    def test_missing_provenance_refused_unless_declared(self):
        self.step()
        with self.assertRaisesRegex(ValueError, "No force_model.json"):
            export.earth_orientation_for(self.solution)
        _, description, info = export.earth_orientation_for(self.solution, assume_plain=True)
        self.assertIn("ASSUMED", description)
        self.assertTrue(info["assumed_plain"])

    @needs_eop
    def test_declared_plain_is_not_labelled_assumed(self):
        self.step(model={"subdaily_eop": None})
        eop, description, info = export.earth_orientation_for(self.solution)
        self.assertNotIn("ASSUMED", description)
        self.assertNotIn("assumed_plain", info)
        self.assertIsNone(getattr(eop, "subdaily", None))

    @needs_eop
    def test_unknown_model_refused(self):
        self.step(model={"subdaily_eop": "Desai-Sibois 2016 (not accepted by export)"})
        with self.assertRaisesRegex(ValueError, "Unsupported Earth-orientation model"):
            export.earth_orientation_for(self.solution)

    @needs_eop
    def test_forced_plain_is_labelled_negative_control(self):
        self.step(model={"subdaily_eop": KNOWN})
        _, description, info = export.earth_orientation_for(self.solution, force_plain=True)
        self.assertTrue(description.startswith("NEGATIVE CONTROL"))
        self.assertTrue(info["negative_control"])


class EvaluateRefusals(Case):
    def accept(self, fixture=None, allow_iterate=False):
        with mock.patch("Opus_Fork.experiments.subdaily.sd_scoring.fit_for", return_value="FIT") as fit_for:
            result = evaluate.accept_arm("A", self.solution_dir, fixture or self.fixture, "EOP",
                                         allow_iterate=allow_iterate)
        return result, fit_for

    def test_unconverged_refused_by_default(self):
        self.step(status="iteration_complete", model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "diagnostic-allow-iterate"):
            self.accept()

    def test_iterate_accepted_only_as_diagnostic(self):
        self.step(status="iteration_complete", model={"subdaily_eop": None})
        (fit, record), fit_for = self.accept(allow_iterate=True)
        self.assertEqual(fit, "FIT")
        self.assertEqual(record["status"], "iteration_complete")
        fit_for.assert_called_once()

    def test_unknown_status_refused_even_with_diagnostic_flag(self):
        self.step(status="failed", model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "verified converged"):
            self.accept(allow_iterate=True)

    def test_hash_mismatch_refused(self):
        self.step(solution_sha="0"*64, model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "verified converged"):
            self.accept()

    def test_wrong_fixture_refused(self):
        self.step(model={"subdaily_eop": None})
        with self.assertRaisesRegex(ValueError, "not the one bound"):
            self.accept(fixture=self.other_fixture)

    def test_unknown_model_refused(self):
        self.step(model={"subdaily_eop": "some other tidal EOP"})
        with self.assertRaisesRegex(ValueError, "unsupported Earth-orientation model"):
            self.accept()

    def test_provenance_labels(self):
        self.step(model={"subdaily_eop": KNOWN})
        self.assertEqual(self.accept()[0][1]["earth_orientation"], KNOWN)
        self.step(model={"subdaily_eop": None})
        self.assertEqual(self.accept()[0][1]["earth_orientation"], "daily finals only")
        (self.solution_dir/"force_model.json").unlink()
        self.step()
        self.assertIn("ASSUMED", self.accept()[0][1]["earth_orientation"])

    def test_unbound_fixture_recorded(self):
        self.step(fixture=False, model={"subdaily_eop": None})
        self.assertFalse(self.accept()[0][1]["fixture_bound_in_step"])


class MetadataArc(unittest.TestCase):
    """N05: the metadata day is the arc midpoint, and an in-arc metadata change is refused."""
    ORIGIN = 1469663990000000000   # Aug 2 fixture: 2026-08-01 23:59:50 GPS, a midnight fixture starts 10 s early

    def context(self, duration_s=85820.):
        return dict(origin_ns=self.ORIGIN, duration_s=duration_s)

    def test_midpoint_day(self):
        self.assertEqual(ngv_pilot._date_at(self.ORIGIN), "2026-08-01")
        self.assertEqual(ngv_pilot.day_of(self.context()), "2026-08-02")

    def test_in_arc_change_refused(self):
        tables = {"2026-08-01": {"G01": ("SVN063", "IIF")}, "2026-08-02": {"G01": ("SVN080", "IIIA")}}
        with mock.patch("Opus_Fork.satmeta.load", side_effect=tables.__getitem__), \
                mock.patch.object(ngv_pilot.nv, "satellite_models") as models:
            with self.assertRaisesRegex(ValueError, "change within the arc"):
                ngv_pilot.satellite_models(self.context(), ["G01"])
            models.assert_not_called()

    def test_unchanged_metadata_passes_midpoint_day(self):
        same = {"G01": ("SVN063", "IIF")}
        with mock.patch("Opus_Fork.satmeta.load", return_value=same), \
                mock.patch.object(ngv_pilot.nv, "current", return_value="VARIANT"), \
                mock.patch.object(ngv_pilot.nv, "satellite_models", return_value="MODELS") as models:
            self.assertEqual(ngv_pilot.satellite_models(self.context(), ["G01"]), "MODELS")
            models.assert_called_once_with(self.context(), ["G01"], "VARIANT", "2026-08-02")


if __name__ == "__main__":
    unittest.main()
