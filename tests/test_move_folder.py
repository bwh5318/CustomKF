"""Opus_Fork.run_fit_elev.move_folder: a finished guard folder enters its campaign by rename only (defect of 3 Oct
2026: `shutil.move` fell back to copy-and-delete while an exiting worker descendant held stderr.log open, leaving
both folders on disk).

    C:\\anaconda\\python.exe -m unittest tests.test_move_folder -v

Temporary folders only; a real open handle reproduces the Windows sharing violation.
"""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from Opus_Fork import run_fit_elev as C


class MoveFolder(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source, self.target = Path(tmp.name)/"20261003T203307Z-x-lin2-traj-1", Path(tmp.name)/"campaign-lin2-traj-1"
        self.source.mkdir()
        (self.source/"result.json").write_text("{}")
        self.log = self.source/"stderr.log"
        self.log.write_text("worker output\n")

    def test_waits_for_the_handle_and_moves_whole(self):
        handle = open(self.log)
        sleeps = []

        def sleep(seconds):          # the exiting process closes its handle during the first wait
            sleeps.append(seconds)
            if not handle.closed:
                handle.close()
        with mock.patch.object(C.time, "sleep", side_effect=sleep):
            C.move_folder(self.source, self.target)
        self.assertEqual(sleeps, [.25], "the first rename must have met the open handle")
        self.assertFalse(self.source.exists())
        self.assertEqual(sorted(p.name for p in self.target.iterdir()), ["result.json", "stderr.log"])
        self.assertEqual((self.target/"stderr.log").read_text(), "worker output\n")

    def test_a_handle_that_stays_open_leaves_the_source_intact(self):
        with open(self.log), mock.patch.object(C.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                C.move_folder(self.source, self.target, attempts=4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [.25, .5, 1.])
        self.assertFalse(self.target.exists(), "no partial copy")
        self.assertEqual(sorted(p.name for p in self.source.iterdir()), ["result.json", "stderr.log"])

    def test_never_overwrites_and_does_not_retry_other_errors(self):
        self.target.mkdir()
        with mock.patch.object(C.time, "sleep") as sleep:
            with self.assertRaises(FileExistsError):
                C.move_folder(self.source, self.target)
        sleep.assert_not_called()
        self.assertTrue((self.source/"stderr.log").exists())

    def test_backoff_is_capped(self):
        with open(self.log), mock.patch.object(C.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                C.move_folder(self.source, self.target)
        delays = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(len(delays), 31)
        self.assertEqual(max(delays), 2.)
        self.assertLess(sum(delays), 65)


if __name__ == "__main__":
    unittest.main()
