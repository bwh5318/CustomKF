"""Opus_Fork.evaluate provenance fields: population_digest (Astra N1, 6 Oct 2026), the scored population bound by
content, not count; model_sha256 (Astra NR-03, 8 Oct 2026), the scored force model bound by its file hash.

    C:\\anaconda\\python.exe -m unittest tests.test_evaluate_population -v
"""
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from Opus_Fork.evaluate import model_sha256, population_digest
from Opus_Fork.experiments.gradients.analyze_validation import key_digest


class PopulationDigest(unittest.TestCase):
    keys = {("G01", 1_000_000_000), ("G02", 1_000_000_000), ("G01", 1_900_000_000_000)}

    def test_equals_the_analysis_digest(self):
        self.assertEqual(population_digest(self.keys), key_digest(self.keys))

    def test_order_and_integer_type_do_not_matter(self):
        numpy_keys = [(np.str_(s), np.int64(t)) for s, t in sorted(self.keys, reverse=True)]
        self.assertEqual(population_digest(numpy_keys), population_digest(self.keys))

    def test_same_count_different_keys_differ(self):
        swapped = (self.keys - {("G02", 1_000_000_000)}) | {("G03", 1_000_000_000)}
        self.assertEqual(len(swapped), len(self.keys))
        self.assertNotEqual(population_digest(swapped), population_digest(self.keys))


class ModelHash(unittest.TestCase):
    def test_hash_of_the_model_beside_the_solution(self):
        with tempfile.TemporaryDirectory() as tmp:
            solution = Path(tmp)/"solution.npz"
            solution.write_bytes(b"x")
            self.assertIsNone(model_sha256(solution))
            (Path(tmp)/"force_model.json").write_text('{"variant": "v"}')
            self.assertEqual(model_sha256(solution), hashlib.sha256(b'{"variant": "v"}').hexdigest())


if __name__ == "__main__":
    unittest.main()
