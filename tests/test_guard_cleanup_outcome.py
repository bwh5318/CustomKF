"""Guards report worker outcome and cleanup outcome separately (Sol review SOL-07).

    C:\\anaconda\\python.exe -m unittest tests.test_guard_cleanup_outcome -v

Runs the real root and fork guards in-process with a tiny file-wait worker and an isolated coordination directory.
Run directly, never inside a guard, and only when no other guarded job or campaign is running.
"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from customkf import guard as G
from customkf.runtime import lease as L


class CleanupOutcome(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cleanup-outcome-")).resolve()
        self.env = mock.patch.dict(os.environ, {L.DIR_ENV: str(self.tmp/"coordination")})
        self.env.start()
        self.addCleanup(self.env.stop)
        (self.tmp/"release").write_text("go")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_root(self):
        result, folder = G.run(["tests.lease_guard_worker", str(self.tmp/"start"), str(self.tmp/"release")],
                               G.Limits(memory_mib=128, timeout_s=60))
        self.addCleanup(shutil.rmtree, folder, True)
        return result

    def run_fork(self):
        from Opus_Fork import guard as F
        result, folder = F.run(["tests.lease_guard_worker", str(self.tmp/"start"), str(self.tmp/"release")],
                               F.Limits(memory_mib=128, threads=1, processes=4, timeout_s=60), usage_ceiling=None,
                               label="cleanup-outcome-test", ignore_other_python=True)
        self.addCleanup(shutil.rmtree, folder, True)
        return result

    def test_normal_release(self):
        for run in (self.run_root, self.run_fork):
            with self.subTest(run.__name__):
                result = run()
                self.assertEqual((result["status"], result["exit_code"], result["lease"]["released"]), ("ok", 0, True))
                self.assertNotIn("worker_status", result)

    def test_release_exception_is_not_a_successful_boundary(self):
        for run in (self.run_root, self.run_fork):
            with self.subTest(run.__name__):
                with mock.patch.object(L.Admission, "release", side_effect=OSError("injected release failure")):
                    result = run()
                self.assertEqual(result["status"], "cleanup_failed")
                self.assertEqual(result["worker_status"], "ok")
                self.assertNotEqual(result["exit_code"], 0)
                self.assertIn("injected release failure", result["lease"]["release_error"])
                # Fail closed: the admission stays recorded until inspected; clear it for the next case.
                status, record = L.check(self.tmp/"coordination")
                self.assertNotEqual(status, "free")
                (self.tmp/"coordination"/L.NAME).unlink()

    def test_already_absent_admission_is_reported_not_failed(self):
        for run in (self.run_root, self.run_fork):
            with self.subTest(run.__name__):
                with mock.patch.object(L.Admission, "release", return_value=False):
                    result = run()
                self.assertEqual(result["status"], "ok")
                self.assertIs(result["lease"]["released"], False)
                self.assertIn("already absent", result["lease"]["release_note"])
                lease_file = self.tmp/"coordination"/L.NAME
                if lease_file.exists():
                    lease_file.unlink()


if __name__ == "__main__":
    unittest.main()
