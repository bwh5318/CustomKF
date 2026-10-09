"""Opus_Fork/export.py product labels: SP3 header comments are written whole or refused, and a-priori gradients
are named.

    C:\\anaconda\\python.exe -m unittest tests.test_export_labels -v

Header construction and temporary force_model.json files only; no solution or product is written.
"""
import json
from pathlib import Path
import tempfile
import unittest

from Opus_Fork import export as E

GPS_DAY = 2425*604800.+86400.          # some emitted epoch, GPS seconds


def header(comments):
    return E.header_lines("2026-06-06", [GPS_DAY, GPS_DAY+900.], ["G01", "G02"], {}, agency="OPUS", frame="IGc20",
                          comments=comments)


class Comments(unittest.TestCase):
    def test_standard_comments_fit_and_are_written_whole(self):
        for subdaily in (True, False):
            comments = E.standard_comments(subdaily)
            self.assertTrue(all(len(c) <= E.COMMENT_WIDTH for c in comments), comments)
            lines = header(comments)
            for text in comments:
                self.assertIn("/* "+text.ljust(E.COMMENT_WIDTH), lines)
        self.assertIn("RETROSPECTIVE INPUTS: NOT A LATENCY-CERTIFIED PRODUCT", E.standard_comments(True))

    def test_an_overlong_comment_is_refused_not_cut(self):
        """Defect of 3 Oct 2026: the 59-character latency label was written cut to "...RAPID PRODU"."""
        header(["X"*E.COMMENT_WIDTH])
        with self.assertRaisesRegex(ValueError, "longer than 57"):
            header(["RETROSPECTIVE INPUTS: NOT A LATENCY-CERTIFIED RAPID PRODUCT"])


class GradientLabels(unittest.TestCase):
    """User adoption, 3 Oct 2026: GRAD operational is optional and labelled; its products are final class."""

    def solution(self, binding):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        if binding is not None:
            (folder/"force_model.json").write_text(json.dumps(binding))
        return folder/"solution.npz"

    def test_labels_fit_the_header(self):
        for comments, _ in E.GRADIENT_LABELS.values():
            header(E.standard_comments(True)+comments)              # raises if any is too long

    def test_each_source_is_named(self):
        self.assertEqual(E.gradients_for(self.solution({"subdaily_eop": "x"})), ([], None, None))
        self.assertEqual(E.gradients_for(self.solution(None)), ([], None, None))
        recorded = {"source": "grad_op", "inputs": {"2026157.grad_g": "0"*64}}
        comments, kind, info = E.gradients_for(self.solution({"gradients": recorded}))
        self.assertEqual(kind, "FIN")
        self.assertEqual(info, recorded)
        self.assertTrue(any("GRAD OPERATIONAL" in c for c in comments) and any("RETROSPECTIVE; ISSUE TIME NOT VERIFIED" in c for c in comments))
        comments, kind, _ = E.gradients_for(self.solution({"gradients": {"source": "gpt3"}}))
        self.assertIsNone(kind)
        self.assertTrue(any("GPT3" in c and "NOT ADOPTED" in c for c in comments))

    def test_an_unknown_gradient_model_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unsupported gradient model"):
            E.gradients_for(self.solution({"gradients": {"source": "grad_fc"}}))


if __name__ == "__main__":
    unittest.main()
