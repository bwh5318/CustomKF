"""Opus_Fork.export destination and write path (Astra PI-09, 8 Oct 2026): distinct solutions never share a default
name, an existing product is never replaced, and a failing replacement leaves the earlier bytes untouched.

    C:\\anaconda\\python.exe -m unittest tests.test_export_preservation -v
"""
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest

from Opus_Fork import export as E


class Destination(unittest.TestCase):
    def test_two_solutions_on_one_day_get_different_default_names(self):
        args = NS(out=None, day="2026-06-06")
        a, b = E.destination(args, "FIN", "a"*64), E.destination(args, "FIN", "b"*64)
        self.assertNotEqual(a, b)
        self.assertEqual(a.name, "OPUS0OPSFIN_20260606_aaaaaaaaaaaa.SP3")
        self.assertEqual(E.destination(args, None, "c"*64).name, "OPUS0OPSRAP_20260606_cccccccccccc.SP3")

    def test_explicit_out_is_used(self):
        self.assertEqual(E.destination(NS(out="x/y.SP3", day="2026-06-06"), "FIN", "a"*64), Path("x/y.SP3"))


class WriteVerified(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.out = self.folder/"product.SP3"

    def tearDown(self):
        self.tmp.cleanup()

    def leftovers(self):
        return sorted(p.name for p in self.folder.iterdir() if p.name != self.out.name)

    def test_passing_write_lands_and_leaves_no_temporary(self):
        written, result, size, digest = E.write_verified(self.out, lambda p: p.write_text("good") and (1, 2),
                                                         lambda p: dict(passed=p.read_text() == "good"))
        self.assertTrue(result["passed"])
        self.assertEqual(self.out.read_text(), "good")
        self.assertEqual(size, 4)
        self.assertEqual(digest, E.sha(self.out))
        self.assertEqual(self.leftovers(), [])

    def test_existing_product_is_refused_and_unchanged(self):
        self.out.write_text("earlier valid product")
        with self.assertRaises(FileExistsError):
            E.write_verified(self.out, lambda p: p.write_text("other configuration"), lambda p: dict(passed=True))
        self.assertEqual(self.out.read_text(), "earlier valid product")
        self.assertEqual(self.leftovers(), [])

    def test_failing_write_publishes_nothing(self):
        _, result, size, digest = E.write_verified(self.out, lambda p: p.write_text("bad"), lambda p: dict(passed=False))
        self.assertFalse(result["passed"])
        self.assertIsNone(size)
        self.assertIsNone(digest)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.leftovers(), [])

    def test_failing_replacement_keeps_earlier_bytes(self):
        """A replacement of an existing product is refused before writing, so even a failing one cannot touch it."""
        self.out.write_text("earlier valid product")
        with self.assertRaises(FileExistsError):
            E.write_verified(self.out, lambda p: p.write_text("bad"), lambda p: dict(passed=False))
        self.assertEqual(self.out.read_text(), "earlier valid product")

    def test_error_during_write_leaves_no_temporary(self):
        def broken(path):
            path.write_text("partial")
            raise RuntimeError("disk full")
        with self.assertRaises(RuntimeError):
            E.write_verified(self.out, broken, lambda p: dict(passed=True))
        self.assertFalse(self.out.exists())
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
