"""claude.roadmap.streaming.EliminatingAccumulator against Accumulator (7 Oct 2026, network test S50).

    C:\\anaconda\\python.exe -m unittest tests.test_eliminating_accumulator -v

Synthetic problems shaped like LongPilot's:
- permanent parameters first (the covariance prefix);
- ambiguities with staggered arc lifetimes;
- two to four epoch-local clocks per block;
- prior constraints on the prefix.

The eliminating solve must equal the full solve to rounding: the estimate, including recovered ambiguities and
clocks; the predicted reduction; and the prefix covariance.
"""
import io
import unittest

import numpy as np

from claude.roadmap.streaming import Accumulator, EliminatingAccumulator

PERMANENT, AMBIGUITIES, EPOCHS, PREFIX = 10, 40, 36, 6


def problem(seed=11):
    rng = np.random.default_rng(seed)
    n = PERMANENT+AMBIGUITIES
    starts = rng.integers(0, EPOCHS-6, AMBIGUITIES)
    ends = np.minimum(EPOCHS-1, starts+rng.integers(4, 14, AMBIGUITIES))
    last = np.r_[np.full(PERMANENT, -1), ends]
    truth = rng.normal(size=n)
    blocks = []
    for ei in range(EPOCHS):
        live = [PERMANENT+j for j in range(AMBIGUITIES) if starts[j] <= ei <= ends[j]]
        rows = 3*max(len(live), 2)+6
        g = np.zeros((rows, n))
        g[:, :PERMANENT] = rng.normal(size=(rows, PERMANENT))
        for j in live:                            # each ambiguity in a few phase-like rows
            g[rng.choice(rows, 3, replace=False), j] = 1.
        local = rng.normal(size=(rows, int(rng.integers(2, 5))))
        clocks = rng.normal(size=local.shape[1])
        sigma = rng.uniform(.5, 2., rows)
        y = g@truth+local@clocks+rng.normal(scale=.01, size=rows)*sigma
        blocks.append((g, local, y, sigma))
    c = np.eye(n)[:PREFIX]
    constraints = (c, c@truth+.01, np.full(PREFIX, 10.))
    return n, last, blocks, constraints


def run_full(n, blocks, constraints):
    acc = Accumulator(n)
    for b in blocks:
        acc.add_block(*b)
    acc.add_constraints(*constraints)
    return acc.solve()


def run_eliminating(n, last, blocks, constraints, chunk=6, roundtrip=False):
    acc = EliminatingAccumulator(n, last, PREFIX)
    for ei, b in enumerate(blocks):
        acc.add_block(*b)
        if (ei+1) % chunk == 0 or ei == len(blocks)-1:
            acc.eliminate_through(ei)
            if roundtrip:                         # checkpoint between "workers"
                buffer = io.BytesIO()
                np.savez(buffer, **acc.state())
                buffer.seek(0)
                with np.load(buffer) as data:
                    acc = EliminatingAccumulator.restore(data)
    acc.add_constraints(*constraints)
    return acc.solve(), acc


class Equivalence(unittest.TestCase):
    def test_same_solution_reduction_and_prefix_covariance(self):
        n, last, blocks, constraints = problem()
        x, cov, red = run_full(n, blocks, constraints)
        (y, cov_e, red_e), acc = run_eliminating(n, last, blocks, constraints)
        self.assertGreater(len(acc.eliminated), 0)
        self.assertLess(acc.max_active, n)
        np.testing.assert_allclose(y, x, rtol=0, atol=1e-9*np.max(np.abs(x)))
        self.assertAlmostEqual(red_e, red, delta=1e-9*red)
        np.testing.assert_allclose(cov_e, cov[:PREFIX, :PREFIX], rtol=1e-8, atol=1e-14)

    def test_chunk_length_and_checkpoints_do_not_change_the_answer(self):
        n, last, blocks, constraints = problem(seed=5)
        (y1, c1, r1), _ = run_eliminating(n, last, blocks, constraints, chunk=6)
        (y2, c2, r2), _ = run_eliminating(n, last, blocks, constraints, chunk=6, roundtrip=True)
        np.testing.assert_array_equal(y1, y2)               # a checkpoint round trip is bitwise
        np.testing.assert_array_equal(c1, c2)
        self.assertEqual(r1, r2)
        (y3, _, r3), _ = run_eliminating(n, last, blocks, constraints, chunk=1)
        np.testing.assert_allclose(y3, y1, rtol=0, atol=1e-9*np.max(np.abs(y1)))
        self.assertAlmostEqual(r3, r1, delta=1e-9*r1)

    def test_workspace_estimate_counts_only_active_parameters(self):
        n, last, blocks, constraints = problem()
        full = Accumulator(n)
        for b in blocks:
            full.add_block(*b)
        _, acc = run_eliminating(n, last, blocks, constraints)
        rows = max(len(b[2]) for b in blocks)
        self.assertLess(acc.workspace_bytes(rows), full.workspace_bytes(rows))


class Refusals(unittest.TestCase):
    def test_a_row_in_an_eliminated_column_is_refused(self):
        n, last, blocks, _ = problem()
        early = np.r_[np.full(PERMANENT, -1), np.zeros(AMBIGUITIES, dtype=int)]   # claims every arc ends at epoch 0
        acc = EliminatingAccumulator(n, early, PREFIX)
        acc.add_block(*blocks[0])
        acc.eliminate_through(0)
        with self.assertRaisesRegex(ValueError, "already eliminated"):
            for b in blocks[1:]:
                acc.add_block(*b)

    def test_rank_deficient_ambiguities_are_refused(self):
        n, last, blocks, _ = problem()
        twin = PERMANENT+1
        blocks = [(np.column_stack([g, g[:, twin]]), l, y, s) for g, l, y, s in blocks]   # a duplicate ambiguity
        acc = EliminatingAccumulator(n+1, np.r_[last, last[twin]], PREFIX)
        with self.assertRaisesRegex(ValueError, "Rank deficient"):
            for ei, b in enumerate(blocks):
                acc.add_block(*b)
                acc.eliminate_through(ei)

    def test_unobserved_parameter_and_bad_schedule_are_refused(self):
        n, last, blocks, constraints = problem()
        acc = EliminatingAccumulator(n+1, np.r_[last, 3], PREFIX)    # one ambiguity never observed
        for b in blocks:
            acc.add_block(np.column_stack([b[0], np.zeros(len(b[2]))]), *b[1:])
        with self.assertRaisesRegex(ValueError, "without any observation"):
            acc.add_constraints(np.column_stack([constraints[0], np.zeros(PREFIX)]), *constraints[1:])
            acc.solve()
        with self.assertRaises(ValueError):
            EliminatingAccumulator(n, last, PERMANENT+1)              # prefix reaching an ambiguity

    def test_tampered_checkpoint_is_refused(self):
        n, last, blocks, _ = problem()
        acc = EliminatingAccumulator(n, last, PREFIX)
        for ei, b in enumerate(blocks[:12]):                  # a mid-arc checkpoint, as after chunk 2
            acc.add_block(*b)
            acc.eliminate_through(ei)
        state = acc.state()
        self.assertGreater(len(state["elim_z"]), 0)
        bad = dict(state, column_state=np.where(state["column_state"] == 2, 1, state["column_state"]))
        with self.assertRaisesRegex(ValueError, "column states"):
            EliminatingAccumulator.restore(bad)
        bad = dict(state, elim_z=state["elim_z"][:-1])
        with self.assertRaisesRegex(ValueError, "elimination record"):
            EliminatingAccumulator.restore(bad)
        with self.assertRaisesRegex(ValueError, "Not an eliminating"):
            EliminatingAccumulator.restore({k: v for k, v in state.items() if k != "kind"})


if __name__ == "__main__":
    unittest.main()
