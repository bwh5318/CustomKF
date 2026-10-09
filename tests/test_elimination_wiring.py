"""--eliminate-ambiguities wiring (7 Oct 2026): campaign specification, elimination schedule, checkpoint mode.

    C:\\anaconda\\python.exe -m unittest tests.test_elimination_wiring -v
"""
import io
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

import numpy as np

from claude.roadmap.streaming import Accumulator, EliminatingAccumulator
from Opus_Fork import iteration as I
from Opus_Fork import run_fit_elev as C


def args(**extra):
    return NS(label="t", variant="erp+thrust+iiia2600+sdeop+elw13", protocol=None, chunk_epochs=12,
              trajectory_groups=2, max_linearizations=6, profile="fork8", **extra)


class Specification(unittest.TestCase):
    def test_flag_recorded_only_when_set(self):
        fixture = C.ROOT/"runs/20260929T203924Z-224f1e22/fixture.json"
        if not fixture.exists():
            self.skipTest("fixture not present")
        config = C.ROOT/"claude/roadmap/configs/unit-ecom5.json"
        meta = dict(fixture_sha256="0"*64)
        plain = C.specification(args(), fixture, meta, config, "c", {})
        old_style = C.specification(args(eliminate_ambiguities=False), fixture, meta, config, "c", {})
        flagged = C.specification(args(eliminate_ambiguities=True), fixture, meta, config, "c", {})
        self.assertNotIn("eliminate_ambiguities", plain)
        self.assertEqual(plain, old_style)                  # specifications of earlier campaigns are unchanged
        self.assertIs(flagged["eliminate_ambiguities"], True)


class Schedule(unittest.TestCase):
    def test_last_epochs_and_prefix_from_the_rows(self):
        names = ["orbit:G01:0", "orbit:G01:1", "wet:A:0", "amb:A:G01:0", "amb:A:G01:1", "wet:A:H03", "srpD0:G01"]
        rows = [dict(arc="A:G01:0", epoch=e) for e in (0, 1, 2, 3)] + [dict(arc="A:G01:1", epoch=e) for e in (5, 6, 9)] \
            + [dict(arc="A:G01:2", epoch=7)]                                   # a short arc: no ambiguity
        pilot = NS(n=len(names), rows=rows, arcs=["A:G01:0", "A:G01:1"], arcset={"A:G01:0", "A:G01:1"},
                   index={k: i for i, k in enumerate(names)})
        acc = I.eliminating_accumulator(pilot)
        np.testing.assert_array_equal(acc.last_epoch, [-1, -1, -1, 3, 9, -1, -1])
        self.assertEqual(acc.covariance_prefix, 3)


class CheckpointMode(unittest.TestCase):
    @staticmethod
    def npz(state):
        buffer = io.BytesIO()
        np.savez(buffer, **state)
        buffer.seek(0)
        return np.load(buffer)

    def test_each_mode_refuses_the_other_checkpoint(self):
        plain = Accumulator(4).state()
        eliminating = EliminatingAccumulator(4, [-1, -1, 0, 1], 2).state()
        with self.npz(plain) as data:
            self.assertIsInstance(I.restore_accumulator(data, False), Accumulator)
            with self.assertRaisesRegex(ValueError, "disagree"):
                I.restore_accumulator(data, True)
        with self.npz(eliminating) as data:
            self.assertIsInstance(I.restore_accumulator(data, True), EliminatingAccumulator)
            with self.assertRaisesRegex(ValueError, "disagree"):
                I.restore_accumulator(data, False)


if __name__ == "__main__":
    unittest.main()
