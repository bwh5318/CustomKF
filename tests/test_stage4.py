"""Independent SVD, analytic covariance and datum tests for block QR."""
import unittest
import numpy as np
from customkf.network_square_root import Block, assemble, dense_qr, eliminated_qr, require_connected


class NetworkSquareRootTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(831)
        blocks = [Block(rng.normal(size=(15, 4)), rng.normal(size=(15, k)),
                        rng.normal(size=15), rng.uniform(.2, 2., 15)) for k in (2, 3, 1)]
        constraints = (np.eye(4), np.arange(4.) * .1, np.ones(4) * 3.)
        return blocks, constraints

    def test_independent_svd_estimates_and_full_covariance(self):
        blocks, constraints = self.fixture()
        a, y, s = assemble(blocks, constraints)
        u, singular, vt = np.linalg.svd(a / s[:, None], full_matrices=False)
        inverse = vt.T / singular
        expected = inverse @ (u.T @ (y / s))
        covariance = inverse @ inverse.T
        for solve in (dense_qr(a, y, s), eliminated_qr(blocks, constraints)):
            np.testing.assert_allclose(solve.estimate, expected, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(solve.covariance, covariance, rtol=1e-11, atol=1e-12)

    def test_analytic_shared_global_cross_epoch_covariance(self):
        # y_i = g+l_i and z = g; unit variances. C(l1,l2)=Var(z)=1.
        blocks = [Block(np.ones((1, 1)), np.ones((1, 1)), np.array([v]), np.ones(1)) for v in (4., 8.)]
        constraints = (np.ones((1, 1)), np.array([2.]), np.ones(1))
        result = eliminated_qr(blocks, constraints)
        np.testing.assert_allclose(result.estimate, [2., 2., 6.])
        np.testing.assert_allclose(result.covariance, [[1., -1., -1.], [-1., 2., 1.], [-1., 1., 2.]])

    def test_mixed_physical_units(self):
        blocks, constraints = self.fixture()
        scale = np.array([1e-6, 1e3, 1., 1e6])
        scaled = [Block(b.retained * scale, b.local * 1e-4, b.target, b.sigma) for b in blocks]
        c, z, s = constraints
        original = eliminated_qr(blocks, constraints)
        result = eliminated_qr(scaled, (c * scale, z, s))
        physical = np.r_[scale, np.full(len(result.estimate)-4, 1e-4)]
        np.testing.assert_allclose(result.estimate * physical, original.estimate, rtol=1e-11, atol=1e-12)
        np.testing.assert_allclose(result.covariance * physical[:, None] * physical,
                                   original.covariance, rtol=1e-10, atol=1e-12)

    def test_block_and_row_order(self):
        blocks, constraints = self.fixture()
        original = eliminated_qr(blocks, constraints)
        changed = [Block(b.retained[::-1], b.local[::-1], b.target[::-1], b.sigma[::-1]) for b in blocks[::-1]]
        result = eliminated_qr(changed, constraints)
        order = np.r_[np.arange(4), 9, np.arange(6, 9), np.arange(4, 6)]
        np.testing.assert_allclose(result.estimate, original.estimate[order], atol=1e-12)
        np.testing.assert_allclose(result.covariance, original.covariance[np.ix_(order, order)], atol=1e-12)

    def test_missing_clock_datum_is_rejected(self):
        b = Block(np.ones((3, 1)), np.array([[1., -1.]] * 3), np.ones(3), np.ones(3))
        with self.assertRaisesRegex(ValueError, "Rank deficient"):
            eliminated_qr([b], (np.ones((1, 1)), np.zeros(1), np.ones(1)))

    def test_unobservable_retained_parameter_is_rejected(self):
        b = Block(np.ones((4, 1)), np.ones((4, 1)), np.ones(4), np.ones(4))
        with self.assertRaisesRegex(ValueError, "Rank deficient"):
            eliminated_qr([b], (np.zeros((0, 1)), np.zeros(0), np.ones(0)))

    def test_graph_datum_checks(self):
        self.assertEqual(require_connected([("A", "G01"), ("B", "G01"), ("B", "G02")], "A"), 4)
        with self.assertRaisesRegex(ValueError, "Disconnected"):
            require_connected([("A", "G01"), ("B", "G02")], "A")
        with self.assertRaisesRegex(ValueError, "absent"):
            require_connected([("A", "G01")], "B")

    def test_bad_inputs_and_budget(self):
        blocks, constraints = self.fixture()
        blocks[0].sigma[0] = 0
        with self.assertRaises(ValueError):
            eliminated_qr(blocks, constraints)
        for a, y, s in [(np.ones((2, 3)), np.zeros(2), np.ones(2)),
                         (np.ones((1, 1)), np.array([np.nan]), np.ones(1)),
                         (np.zeros((901, 901)), np.zeros(901), np.ones(901))]:
            with self.assertRaises(ValueError):
                dense_qr(a, y, s)


if __name__ == "__main__":
    unittest.main()
