"""Opus_Fork.iteration contracts from the Sol review: strict forward chunk spans (SOL-03).

    C:\\anaconda\\python.exe -m unittest tests.test_iteration_contracts -v

Pure checks plus a mocked chunk worker; no fixture is restored and no orbit is integrated.
"""
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock

from Opus_Fork import iteration as I


class Spans(unittest.TestCase):
    def test_valid_forward_spans(self):
        for start, stop in ((0, 12), (132, 144), (0, 144)):
            I.check_span(start, stop, 144)

    def test_backward_empty_and_out_of_range_spans_refused(self):
        for start, stop in ((12, 6), (12, 12), (-6, 12), (0, 150), (0.0, 12), (0, True)):
            with self.subTest(span=(start, stop)), self.assertRaisesRegex(ValueError, "Invalid chunk span"):
                I.check_span(start, stop, 144)

    def test_chunk_worker_refuses_before_loading_or_writing(self):
        """Sol's probe chain (0,12),(12,6),(6,144): the backward chunk is refused before any work or output."""
        folder = Path(tempfile.mkdtemp(prefix="chunk-span-"))
        self.addCleanup(shutil.rmtree, folder, True)
        pilot = NS(epoch_count=144)
        args = NS(start=12, stop=6, checkpoint=None, trajectories=None)
        with mock.patch.object(I, "build", return_value=(pilot, None)), \
                mock.patch.object(I, "point", side_effect=AssertionError("must not load a point")):
            with self.assertRaisesRegex(ValueError, "Invalid chunk span"):
                I.mode_chunk(args, folder)
        self.assertEqual(list(folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
