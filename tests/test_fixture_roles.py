"""claude.tools.dated_fixture: the model files restore() opens must be the recorded inputs (Sol review SOL-04).

    C:\\anaconda\\python.exe -m unittest tests.test_fixture_roles -v
"""
import json
from pathlib import Path
import unittest

from customkf.prepare_stage2 import ROOT
from claude.tools import dated_fixture as F

FIXTURES = ["Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json",
            "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03/fixture.json",
            "runs/20260929T203924Z-224f1e22/fixture.json"]


class Roles(unittest.TestCase):
    def canonical(self):
        return {p.relative_to(ROOT).as_posix(): "0"*64 for p in F.ROLE_FILES.values()}

    def test_canonical_bindings_pass(self):
        F.check_roles(self.canonical())

    def test_alternate_copy_with_the_same_name_is_refused(self):
        """Sol's case: the fixture records alternate path A for a role; restore must not open canonical path B."""
        for role, path in F.ROLE_FILES.items():
            with self.subTest(role):
                inputs = self.canonical()
                del inputs[path.relative_to(ROOT).as_posix()]
                inputs["Opus_Fork/datastore/alternate/"+path.name] = "1"*64
                with self.assertRaisesRegex(ValueError, f"{role}: restore opens .*" + r"\(it records .*alternate"):
                    F.check_roles(inputs)

    def test_missing_role_is_refused(self):
        inputs = self.canonical()
        inputs.pop(next(iter(inputs)))
        with self.assertRaisesRegex(ValueError, "does not record"):
            F.check_roles(inputs)

    def test_real_fixtures_pass(self):
        for name in FIXTURES:
            path = ROOT/name
            if not path.exists():
                continue
            with self.subTest(name):
                F.check_roles(json.loads(path.read_text())["context"]["inputs"])


if __name__ == "__main__":
    unittest.main()
