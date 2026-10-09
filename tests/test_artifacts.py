"""Worker-array validation (Opus_Fork/artifacts.py; Astra E-01 and check-in C01).

    C:\\anaconda\\python.exe -m unittest tests.test_artifacts -v
"""
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

import numpy as np

from Opus_Fork import artifacts as A
from claude.roadmap.streaming import Accumulator


def npz(path, arrays, truncate=None, cut=4):
    """Write an NPZ member by member; `truncate` names a member whose payload loses its last `cut` bytes."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in arrays.items():
            buffer = io.BytesIO()
            np.save(buffer, value, allow_pickle=False)
            data = buffer.getvalue()
            archive.writestr(name+".npy", data[:-cut] if name == truncate else data)


def checkpoint_arrays(seed=3):
    rng = np.random.default_rng(seed)
    acc = Accumulator(4)
    for _ in range(3):
        acc.add_block(rng.normal(size=(6, 4)), rng.normal(size=(6, 1)), rng.normal(size=6), np.ones(6))
    return dict(acc.state(), residual=rng.normal(size=18), sigma=np.ones(18))


def solution_arrays():
    rng = np.random.default_rng(4)
    return dict(x=rng.normal(size=5), names=np.array([f"p{i}" for i in range(5)]), states=rng.normal(size=(2, 3, 6)),
                satellites=np.array(["G01", "G02"]), times_s=np.arange(3.), residual_m=rng.normal(size=4),
                sigma_m=np.ones(4), retained_covariance=np.eye(2))


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="artifacts-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_valid_outputs_are_accepted_and_restore(self):
        npz(self.dir/"checkpoint.npz", checkpoint_arrays())
        npz(self.dir/"solution.npz", solution_arrays())
        self.assertIsNone(A.rejection("checkpoint", self.dir/"checkpoint.npz"))
        self.assertIsNone(A.rejection("solution", self.dir/"solution.npz"))
        with np.load(self.dir/"checkpoint.npz") as data:
            Accumulator.restore(data)                                   # the consumer agrees

    def test_truncated_non_floating_payloads_are_refused(self):
        """C01: names.npy (unicode) and active.npy (integer) with four payload bytes removed were accepted."""
        npz(self.dir/"solution.npz", solution_arrays(), truncate="names")
        self.assertIn("truncated", A.rejection("solution", self.dir/"solution.npz"))
        npz(self.dir/"checkpoint.npz", checkpoint_arrays(), truncate="active")
        self.assertIn("truncated", A.rejection("checkpoint", self.dir/"checkpoint.npz"))
        with self.assertRaises(ValueError), np.load(self.dir/"checkpoint.npz") as data:
            data["active"]                                               # what a consumer would hit

    def test_truncated_floating_payload_is_refused(self):
        npz(self.dir/"solution.npz", solution_arrays(), truncate="x", cut=8)
        self.assertIn("truncated", A.rejection("solution", self.dir/"solution.npz"))

    def test_checkpoint_layout_matches_the_consumer(self):
        """C01: duplicate recovery indices passed the validator but Accumulator.restore refuses them."""
        arrays = checkpoint_arrays()
        active = arrays["active"].copy()
        active[:3] = [0, 1, 0]
        bad = {"duplicate index": dict(arrays, active=active),
               "out of range": dict(arrays, active=np.where(np.arange(len(active)) == 2, 99, arrays["active"])),
               "local total": dict(arrays, local_total=np.int64(0)),
               "uint64 descending": dict(arrays, active=np.r_[[1, 0], arrays["active"][2:]].astype(np.uint64))}
        for label, change in bad.items():
            with self.subTest(label):
                npz(self.dir/"checkpoint.npz", change)
                self.assertIsNotNone(A.rejection("checkpoint", self.dir/"checkpoint.npz"))
                with self.assertRaises(ValueError), np.load(self.dir/"checkpoint.npz") as data:
                    Accumulator.restore(data)

    def test_scalar_shape_checked_before_reading(self):
        """C01: `n` with shape (2,) reached the whole-array reader before scalar validation."""
        npz(self.dir/"checkpoint.npz", dict(checkpoint_arrays(), n=np.array([4, 4])))
        with mock.patch.object(A.npformat, "read_array", side_effect=AssertionError("whole-array read")):
            reason = A.rejection("checkpoint", self.dir/"checkpoint.npz")
        self.assertIn("must be a scalar", reason)

    def test_corrupt_member_is_refused(self):
        npz(self.dir/"solution.npz", solution_arrays())
        data = bytearray((self.dir/"solution.npz").read_bytes())
        start = data.find(b"x.npy")+200
        data[start] ^= 0xFF                                              # flip a payload byte: CRC mismatch
        (self.dir/"solution.npz").write_bytes(bytes(data))
        self.assertIsNotNone(A.rejection("solution", self.dir/"solution.npz"))

    def test_eliminating_checkpoint_is_accepted_and_tampering_refused(self):
        """7 Oct 2026: EliminatingAccumulator checkpoints (R over the active columns plus the elimination record)."""
        from claude.roadmap.streaming import EliminatingAccumulator
        from tests.test_eliminating_accumulator import PREFIX, problem
        n, last, blocks, _ = problem()
        acc = EliminatingAccumulator(n, last, PREFIX)
        for ei, b in enumerate(blocks[:18]):
            acc.add_block(*b)
            acc.eliminate_through(ei)
        state = dict(acc.state(), residual=np.zeros(5), sigma=np.ones(5))
        npz(self.dir/"checkpoint.npz", state)
        self.assertIsNone(A.rejection("checkpoint", self.dir/"checkpoint.npz"))
        with np.load(self.dir/"checkpoint.npz") as data:
            EliminatingAccumulator.restore(data)                       # the consumer agrees
        bad = {"column state": dict(state, column_state=np.where(state["column_state"] == 2, 1, state["column_state"])),
               "elimination layout": dict(state, elim_Rrest=state["elim_Rrest"][:-1]),
               "R width": dict(state, R=np.zeros((2, 3)), z=np.zeros(2)),
               "unknown kind": dict(state, kind=np.int64(7))}
        for label, change in bad.items():
            with self.subTest(label):
                npz(self.dir/"checkpoint.npz", change)
                self.assertIsNotNone(A.rejection("checkpoint", self.dir/"checkpoint.npz"))

    def test_wide_items_are_refused_at_the_header(self):
        """Astra peek (2 Oct): the carry between chunks grows to the item size, so items are bounded."""
        wide = {"fixed-width string": np.zeros(2, dtype=f"S{A.MAX_ITEM_BYTES+1}"),
                "unicode": np.zeros(1, dtype=f"<U{A.MAX_ITEM_BYTES//4+1}"),
                "structured subarray": np.zeros(1, dtype=[("a", "f8", (A.MAX_ITEM_BYTES//8+1,))])}
        for label, value in wide.items():
            with self.subTest(label):
                npz(self.dir/"solution.npz", dict(solution_arrays(), names=value))
                with mock.patch.object(A.np, "frombuffer", side_effect=AssertionError("payload read")):
                    reason = A.rejection("solution", self.dir/"solution.npz")
                self.assertIn("-byte items", reason)

    def test_stream_buffer_is_bounded_by_chunk_plus_item(self):
        """An item at the limit, larger than the chunk: every buffer stays within CHUNK_BYTES + MAX_ITEM_BYTES."""
        rng = np.random.default_rng(6)
        value = np.array([rng.bytes(A.MAX_ITEM_BYTES) for _ in range(5)], dtype=f"S{A.MAX_ITEM_BYTES}")
        npz(self.dir/"wide.npz", dict(wide=value))
        sizes, seen, real = [], [], np.frombuffer

        def frombuffer(buffer, dtype):
            sizes.append(len(buffer))
            return real(buffer, dtype=dtype)
        with mock.patch.object(A, "CHUNK_BYTES", 1000), mock.patch.object(A.np, "frombuffer", side_effect=frombuffer):
            self.assertEqual(A.stream_payloads(self.dir/"wide.npz", {"wide": seen.append}), [])
        self.assertLessEqual(max(sizes), 1000+A.MAX_ITEM_BYTES)
        self.assertEqual(b"".join(v.tobytes() for v in seen), value.tobytes())


if __name__ == "__main__":
    unittest.main()
