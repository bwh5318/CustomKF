"""Transfer diagnostic prerequisite K1 (checkpoint-A review A05): enforced over the whole chunk chain, and a K1 failure
keeps candidate analysis unavailable.

    C:\\anaconda\\python.exe -m unittest tests.test_transfer_k1 -v

Synthetic chunk step records in a temporary folder; no solve, no guard needed.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from Opus_Fork.experiments.transfer.common import K1_TOLERANCE_M, candidates_allowed, chunk_chain

PASSING = dict(K1_pass=True, K2_pass=True, K3_pass=True)


class ChunkChain(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="k1-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def chain(self, spans, k1=None, status=None):
        previous = None
        for i, (start, stop) in enumerate(spans):
            folder = self.root/f"chunk-{i}"
            folder.mkdir()
            step = dict(status=(status or {}).get(i, "transfer_chunk_complete"), start=start, stop=stop,
                        checks=dict(max_abs_vs_fit_residual_m=(k1 or {}).get(i, 0.)),
                        previous=str(previous) if previous else None)
            (folder/"step.json").write_text(json.dumps(step))
            previous = folder
        return previous

    def test_contiguous_chain_passes(self):
        result = chunk_chain(self.chain([(0, 12), (12, 24), (24, 36)]), 36)
        self.assertTrue(result["K1_pass"])
        self.assertEqual([c["start"] for c in result["chunks"]], [0, 12, 24])

    def test_k1_failure_in_any_chunk_fails_and_blocks_candidates(self):
        """Failure injection: one early chunk's misclosure differs from the fit by 1 mm."""
        result = chunk_chain(self.chain([(0, 12), (12, 24), (24, 36)], k1={0: 1e-3}), 36)
        self.assertFalse(result["K1_pass"])
        self.assertEqual(result["K1_max_abs_m"], 1e-3)
        checks = dict(PASSING, K1_pass=result["K1_pass"])
        self.assertFalse(candidates_allowed(checks, dict(**{"pass": True})))

    def test_tolerance_is_inclusive(self):
        self.assertTrue(chunk_chain(self.chain([(0, 12)], k1={0: K1_TOLERANCE_M}), 12)["K1_pass"])

    def test_gap_overlap_short_chain_and_incomplete_chunk_raise(self):
        cases = (("gap", [(0, 12), (13, 24)], 24, None), ("overlap", [(0, 12), (11, 24)], 24, None),
                 ("short", [(0, 12), (12, 24)], 36, None), ("incomplete", [(0, 12), (12, 24)], 24, {0: "running"}))
        for name, spans, count, status in cases:
            with self.subTest(name):
                folder = self.root/name
                folder.mkdir()
                self.root, saved = folder, self.root
                try:
                    with self.assertRaises(ValueError):
                        chunk_chain(self.chain(spans, status=status), count)
                finally:
                    self.root = saved

    def test_invalid_k1_values_refused(self):
        """Addendum review AA03: NaN in a later chunk (max() would keep 0.0), negative, infinite, non-numeric."""
        for name, value in (("nan_later", float("nan")), ("negative", -1e-9), ("inf", float("inf")), ("text", "0")):
            with self.subTest(name):
                folder = self.root/name
                folder.mkdir()
                self.root, saved = folder, self.root
                try:
                    with self.assertRaisesRegex(ValueError, "invalid K1"):
                        chunk_chain(self.chain([(0, 12), (12, 24)], k1={1: value}), 24)
                finally:
                    self.root = saved

    def test_backwards_zero_length_and_out_of_range_spans_refused(self):
        """Addendum review AA03: 0->12, 12->6, 6->24 is continuous and ends at 24, but revisits epochs."""
        cases = (("backwards", [(0, 12), (12, 6), (6, 24)], 24), ("zero_length", [(0, 12), (12, 12), (12, 24)], 24),
                 ("beyond_count", [(0, 30)], 24), ("negative_start", [(-6, 24)], 24),
                 ("float_bounds", [(0, 12.0)], 12))
        for name, spans, count in cases:
            with self.subTest(name):
                folder = self.root/name
                folder.mkdir()
                self.root, saved = folder, self.root
                try:
                    with self.assertRaisesRegex(ValueError, "invalid span|gap or overlap"):
                        chunk_chain(self.chain(spans), count)
                finally:
                    self.root = saved

    def test_epoch_count_must_be_a_positive_integer(self):
        last = self.chain([(0, 12)])
        for count in (0, -12, 12.0, True):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "positive integer"):
                chunk_chain(last, count)

    def test_gate_requires_every_prerequisite_and_calibration(self):
        self.assertTrue(candidates_allowed(PASSING, {"pass": True}))
        self.assertFalse(candidates_allowed(PASSING, {"pass": False}))
        for missing in PASSING:
            with self.subTest(missing):
                self.assertFalse(candidates_allowed({k: v for k, v in PASSING.items() if k != missing}, {"pass": True}))


if __name__ == "__main__":
    unittest.main()
