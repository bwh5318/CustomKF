"""diagnose_c1.scored_epochs (Astra NR-01, 8 Oct 2026): the full scored day, without integer overflow.

    C:\\anaconda\\python.exe -m unittest tests.test_diagnose_c1_epochs -v
"""
import unittest

from Opus_Fork.experiments.networks.diagnose_c1 import scored_epochs


class ScoredEpochs(unittest.TestCase):
    origin = 1467331190000000000                          # 2026-07-06 00:00:00 GPST minus 10 s, as in the fixtures

    def test_96_tags_900_s_apart_over_the_full_day(self):
        tags = scored_epochs(self.origin)
        self.assertEqual(len(tags), 96)
        self.assertEqual(len(set(tags)), 96)
        self.assertTrue(all(isinstance(t, int) for t in tags))
        self.assertEqual({b-a for a, b in zip(tags, tags[1:])}, {900*10**9})
        self.assertEqual(tags[0], self.origin+10*10**9)                          # 00:00
        self.assertEqual(tags[-1]-tags[0], (23*3600+45*60)*10**9)               # 23:45


if __name__ == "__main__":
    unittest.main()
