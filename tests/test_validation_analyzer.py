"""Opus_Fork/experiments/gradients/analyze_validation.py acceptance gates (Astra review R02, 4 Oct 2026).

    C:\\anaconda\\python.exe -m unittest tests.test_validation_analyzer -v

Synthetic inputs only: no fit, no evaluation, no historical campaign touched.
"""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from Opus_Fork.experiments.gradients import analyze_validation as A
from Opus_Fork.experiments.transfer.common import sha

GOOD = dict(changes=[-1.15, -1.72, -2.14, -0.42, -4.07], worst_m=0.0198, worst_radial_pct=-0.10)


class Reading(unittest.TestCase):
    def test_a_failed_control_withholds_the_reading(self):
        """R02: the reading used to be chosen without looking at the controls."""
        self.assertEqual(A.classify(**GOOD, controls_pass=True), "validated on these dates")
        self.assertEqual(A.classify(**GOOD, controls_pass=False), "not read (a control failed)")
        self.assertEqual(A.classify([1.0, 2.0, -0.1, 0.5, 0.3], 0.01, 0.0, False), "not read (a control failed)")

    def test_registered_categories_unchanged(self):
        self.assertEqual(A.classify([-0.56, -0.19, -0.74, -0.21, -1.33], 0.02, 0.5, True), "inconclusive")
        self.assertEqual(A.classify([0.5, 0.4, -2.0, -0.1, -0.2], 0.01, 0.0, True), "not validated")
        self.assertEqual(A.classify(GOOD["changes"], 0.11, 0.0, True), "inconclusive")       # satellite limit
        self.assertEqual(A.classify(GOOD["changes"], 0.01, 3.1, True), "inconclusive")       # radial limit


class Population(unittest.TestCase):
    def test_key_digest_is_order_free_and_identity_sensitive(self):
        keys = [("G01", 10), ("G02", 10), ("G01", 20)]
        self.assertEqual(A.key_digest(keys), A.key_digest(set(reversed(keys))))
        self.assertNotEqual(A.key_digest(keys), A.key_digest([("G01", 10), ("G02", 10), ("G03", 20)]))  # same count


class Provenance(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.step = Path(tmp.name)/"campaign"/"lin2-solve"
        self.step.mkdir(parents=True)
        self.path = self.step/"solution.npz"
        np.savez(self.path, states=np.zeros((2, 3, 6)), satellites=np.array(["G01", "G02"]), times_s=np.arange(3.))
        (self.step/"force_model.json").write_text(json.dumps({"gradients": {"source": "grad_op"}}))
        self.write_step("converged", sha(self.path))

    def write_step(self, status, digest):
        (self.step/"step.json").write_text(json.dumps({"status": status, "solution_sha256": digest}))

    def evaluation(self, digest):
        return {"provenance": {"V-op": {"solution": str(self.path), "sha256": digest}}}

    def test_the_evaluated_solution_is_used(self):
        got = A.provenance_solution(self.evaluation(sha(self.path)), "V-op")
        self.assertEqual(got["campaign"], self.step.parent)
        self.assertEqual(got["sats"], ["G01", "G02"])

    def test_changed_bytes_or_unconverged_step_are_refused(self):
        with self.assertRaisesRegex(ValueError, "differ"):
            A.provenance_solution(self.evaluation("0"*64), "V-op")
        self.write_step("diverged", sha(self.path))
        with self.assertRaisesRegex(ValueError, "converged"):
            A.provenance_solution(self.evaluation(sha(self.path)), "V-op")


if __name__ == "__main__":
    unittest.main()
