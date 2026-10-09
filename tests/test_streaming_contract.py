"""Streaming accumulator input contract (Sol review SOL-08): raw sigmas finite and positive, shapes exact, checkpoint
layout consistent. Valid systems are unchanged and still agree with a dense least-squares solve.

    C:\\anaconda\\python.exe -m unittest tests.test_streaming_contract -v
"""
import unittest

import numpy as np

from claude.roadmap.streaming import Accumulator


def system(seed=1, blocks=6, rows=8, n=4):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(blocks):
        retained = rng.normal(size=(rows, n))
        local = rng.normal(size=(rows, 1))
        target = rng.normal(size=rows)
        sigma = rng.uniform(.5, 2., size=rows)
        out.append((retained, local, target, sigma))
    return out


class Contract(unittest.TestCase):
    def accumulate(self, blocks, n=4):
        acc = Accumulator(n)
        for b in blocks:
            acc.add_block(*b)
        return acc

    def test_valid_system_matches_dense_least_squares(self):
        blocks = system()
        acc = self.accumulate(blocks)
        estimate, _, _ = acc.solve()
        a = np.zeros((48, 4+6))
        y = np.zeros(48)
        for i, (g, l, t, s) in enumerate(blocks):
            a[8*i:8*i+8, :4] = g/s[:, None]
            a[8*i:8*i+8, 4+i] = l[:, 0]/s
            y[8*i:8*i+8] = t/s
        dense = np.linalg.lstsq(a, y, rcond=None)[0]
        self.assertTrue(np.allclose(estimate, dense, atol=1e-10))

    def test_infinite_or_nonpositive_observation_sigma_refused(self):
        for bad in (np.inf, 0., -1., np.nan):
            with self.subTest(sigma=bad):
                g, l, t, s = system()[0]
                s = s.copy()
                s[3] = bad
                with self.assertRaisesRegex(ValueError, "sigma"):
                    Accumulator(4).add_block(g, l, t, s)

    def test_mismatched_block_shapes_refused(self):
        g, l, t, s = system()[0]
        for args in ((g[:7], l, t, s), (g, l, t[:7], s), (g[:, :3], l, t, s), (g, l[:7], t, s)):
            with self.subTest(shapes=[a.shape for a in args]), self.assertRaisesRegex(ValueError, "dimensions"):
                Accumulator(4).add_block(*args)

    def test_invalid_constraint_sigma_refused(self):
        acc = self.accumulate(system())
        c, z = np.eye(4), np.zeros(4)
        for bad in (np.inf, 0., np.nan):
            with self.subTest(sigma=bad):
                s = np.ones(4)
                s[1] = bad
                with self.assertRaisesRegex(ValueError, "sigma"):
                    acc.add_constraints(c, z, s)
        with self.assertRaisesRegex(ValueError, "dimensions"):
            acc.add_constraints(c[:, :3], z, np.ones(4))

    def test_checkpoint_round_trip_and_malformed_layout_refused(self):
        acc = self.accumulate(system())
        state = acc.state()
        restored = Accumulator.restore(state)
        self.assertTrue(np.array_equal(restored.solve()[0], acc.solve()[0]))
        for key, value in (("local_lengths", state["local_lengths"][:-1]), ("d", state["d"][:-1]),
                           ("active", state["active"]+100), ("R", np.full_like(state["R"], np.nan))):
            with self.subTest(corrupt=key):
                with self.assertRaises(ValueError):
                    Accumulator.restore(dict(state, **{key: value}))

    def test_recovery_layout_refusals(self):
        """Astra AR-03: two retained parameters, three one-parameter local blocks (the review's probe shape)."""
        acc = self.accumulate(system(seed=7, blocks=3, rows=6, n=2), n=2)
        state = acc.state()
        restored = Accumulator.restore(state)
        self.assertTrue(np.array_equal(restored.solve()[0], acc.solve()[0]))
        duplicate = state["active"].copy()
        duplicate[:2] = [0, 0]
        decreasing = state["active"].copy()
        decreasing[:2] = [1, 0]
        cases = {"duplicate index": dict(active=duplicate), "decreasing index": dict(active=decreasing),
                 "local_total 0": dict(local_total=0), "local_total too large": dict(local_total=state["local_total"]+1),
                 "float lengths": dict(local_lengths=state["local_lengths"].astype(float)),
                 "float indices": dict(active=state["active"].astype(float)),
                 "zero local length": dict(local_lengths=np.r_[0, state["local_lengths"][1:]+0],
                                           d=state["d"][1:], B=state["B"][2:], local_total=state["local_total"]-1)}
        for label, change in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                Accumulator.restore(dict(state, **change))

    def test_unsigned_recovery_indices(self):
        """Astra E-02: unsigned indices must not bypass the ordering check through wrapping subtraction."""
        acc = self.accumulate(system(seed=7, blocks=3, rows=6, n=4), n=4)      # each block's active columns: 0..3
        state = acc.state()
        valid = Accumulator.restore(dict(state, active=state["active"].astype(np.uint64)))
        self.assertTrue(np.array_equal(valid.solve()[0], acc.solve()[0]))
        for label, first in (("nonadjacent duplicate", [0, 1, 0]), ("descending", [1, 0])):
            active = state["active"].astype(np.uint64)
            active[:len(first)] = first
            with self.subTest(label), self.assertRaisesRegex(ValueError, "unique and increasing"):
                Accumulator.restore(dict(state, active=active))


if __name__ == "__main__":
    unittest.main()
