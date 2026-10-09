"""Opus_Fork.store.find: one product held as a gzip copy and a plain copy resolves; different content still refuses.

    C:\anaconda\python.exe -m unittest tests.test_store_find -v

Temporary files and an in-memory index only; the real store is not read.
"""
import gzip
from pathlib import Path
import shutil
import tempfile
import unittest

from customkf.prepare_stage2 import sha
from Opus_Fork import store


class Find(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="store-find-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def index(self, *files):
        return {"entries": {str(i): dict(role="reference_igs_final", date="2026-06-20", path=str(p), sha256=sha(p))
                            for i, p in enumerate(files)}}

    def product(self, name, content, compressed=False):
        path = self.dir/name
        path.write_bytes(gzip.compress(content) if compressed else content)
        return path

    def test_gzip_and_plain_copies_of_one_product_resolve(self):
        plain = self.product("a.SP3", b"#dP2026  6 20 orbit content\n")
        packed = self.product("a.SP3.gz", b"#dP2026  6 20 orbit content\n", compressed=True)
        path, entry = store.find("reference_igs_final", "2026-06-20", self.index(plain, packed))
        self.assertIn(path, (plain, packed))

    def test_different_content_still_refused(self):
        plain = self.product("a.SP3", b"#dP2026  6 20 orbit content\n")
        other = self.product("b.SP3.gz", b"#dP2026  6 20 DIFFERENT\n", compressed=True)
        with self.assertRaisesRegex(KeyError, "DIFFERENT files"):
            store.find("reference_igs_final", "2026-06-20", self.index(plain, other))

    def test_a_copy_changed_after_indexing_is_refused(self):
        plain = self.product("a.SP3", b"#dP2026  6 20 orbit content\n")
        packed = self.product("a.SP3.gz", b"#dP2026  6 20 orbit content\n", compressed=True)
        index = self.index(plain, packed)
        packed.write_bytes(gzip.compress(b"#dP2026  6 20 orbit content\n", compresslevel=1))
        with self.assertRaisesRegex(ValueError, "changed on disk"):
            store.find("reference_igs_final", "2026-06-20", index)


if __name__ == "__main__":
    unittest.main()
