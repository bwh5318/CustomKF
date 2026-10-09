"""Guard scratch accounting survives a worker deleting its temporary files mid-walk (Astra follow-up AF-01).

    C:\\anaconda\\python.exe -m unittest tests.test_guard_scratch -v

Temporary folders only; no guard or worker is started.
"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from customkf import guard


class ScratchBytes(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="scratch-"))
        (self.dir/"a").write_bytes(b"x"*100)
        (self.dir/"sub").mkdir()
        (self.dir/"sub"/"b").write_bytes(b"y"*50)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_ordinary_total(self):
        self.assertEqual(guard.scratch_bytes(self.dir), 150)

    def test_file_disappearing_between_enumeration_and_stat_is_skipped(self):
        real = os.scandir

        class Vanishing:
            def __init__(self, entry):
                self.entry, self.path, self.name = entry, entry.path, entry.name

            def is_dir(self, follow_symlinks=True):
                return self.entry.is_dir(follow_symlinks=follow_symlinks)

            def is_file(self, follow_symlinks=True):
                return self.entry.is_file(follow_symlinks=follow_symlinks)

            def stat(self, follow_symlinks=True):
                if self.name == "a":
                    os.remove(self.path)                    # the worker deletes it right after enumeration
                    raise FileNotFoundError(2, "vanished", self.path)
                return self.entry.stat(follow_symlinks=follow_symlinks)

        def scandir(path):
            return [Vanishing(e) for e in real(path)]
        with mock.patch.object(guard.os, "scandir", side_effect=scandir):
            self.assertEqual(guard.scratch_bytes(self.dir), 50)

    def test_directory_disappearing_before_its_walk_is_skipped(self):
        real = os.scandir

        def scandir(path):
            if Path(path).name == "sub":
                raise FileNotFoundError(2, "vanished", path)
            return real(path)
        with mock.patch.object(guard.os, "scandir", side_effect=scandir):
            self.assertEqual(guard.scratch_bytes(self.dir), 100)

    def test_other_errors_still_propagate(self):
        with mock.patch.object(guard.os, "scandir", side_effect=PermissionError(13, "denied")):
            with self.assertRaises(PermissionError):
                guard.scratch_bytes(self.dir)

    def test_limit_breach_still_visible(self):
        (self.dir/"big").write_bytes(b"z"*(2*2**20))
        self.assertGreater(guard.scratch_bytes(self.dir), 1*2**20)

    def test_both_guards_use_it(self):
        from Opus_Fork import guard as fork
        self.assertIs(fork.scratch_bytes, guard.scratch_bytes)
        for module in (guard, fork):
            source = Path(module.__file__).read_text()
            self.assertNotIn('folder.rglob("*") if p.is_file()', source)


if __name__ == "__main__":
    unittest.main()
