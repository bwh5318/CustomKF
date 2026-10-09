"""Campaign lease integrated into the real guards (M14; checkpoint A: A02, addendum AA01/AA02).

    C:\\anaconda\\python.exe -m unittest tests.test_guard_lease_integration -v

Run directly, never inside a guard, and only when no other guarded job or campaign is running (the tests start real
guards, one at a time, with a 128 MiB tiny worker that only waits on a file). Each test uses its own temporary
coordination directory (CUSTOMKF_COORDINATION_DIR), so the machine's real lease is never touched.

Cases (the addendum review's list): bare admission; a controller's gap between two workers; cancellation (release)
with a live worker; exclusion of a guard started from a separate replay root; the fork guard records its admission.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from customkf.runtime import lease as L

ROOT = Path(__file__).resolve().parents[1]


class GuardLease(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="guard-lease-"))
        self.coord = (self.tmp/"coordination").resolve()
        self.coord.mkdir()
        self.env = {**os.environ, L.DIR_ENV: str(self.coord), "PYTHONPATH": str(ROOT)}
        self.env.pop(L.ENV, None)
        self.running = []

    def tearDown(self):
        for process in self.running:
            if process.poll() is None:
                process.kill()
                process.wait(30)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def guard(self, name, env, root=ROOT, wait=False):
        """Start `python -m customkf.guard -- tests.lease_guard_worker START RELEASE` (legacy profile, tiny)."""
        start, release = self.tmp/f"{name}.start", self.tmp/f"{name}.release"
        process = subprocess.Popen([sys.executable, "-m", "customkf.guard", "--memory-mib", "128", "--timeout", "90",
                                    "--", "tests.lease_guard_worker", str(start), str(release)],
                                   cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.running.append(process)
        if wait:
            end = time.monotonic()+60
            while not start.exists():
                self.assertIsNone(process.poll(), process.communicate()[1] if process.poll() is not None else "")
                self.assertLess(time.monotonic(), end, "worker did not start")
                time.sleep(0.05)
        return process, release

    def finish(self, process, release=None):
        if release is not None:
            release.write_text("go")
        out, err = process.communicate(timeout=90)
        result = json.loads(out[:out.rindex("}")+1]) if process.returncode == 0 else None
        return process.returncode, result, err

    def test_bare_job_takes_a_bare_lease_that_blocks_campaigns(self):
        process, release = self.guard("bare", self.env, wait=True)
        status, record = L.check(self.coord)
        self.assertEqual((status, record["kind"]), ("live", "bare"))
        with self.assertRaisesRegex(L.LeaseHeld, "bare"):
            L.acquire("campaign", "test", directory=self.coord)
        code, result, _ = self.finish(process, release)
        self.assertEqual(code, 0)
        self.assertEqual(result["lease"]["kind"], "bare")
        self.assertEqual(result["lease"]["released"], True)
        self.assertEqual(L.check(self.coord)[0], "free")

    def test_controller_gap_refuses_a_bare_job_and_admits_its_own_workers(self):
        held = L.acquire("campaign", "stand-in controller", directory=self.coord)
        child_env = held.child_environment(self.env)
        for step in ("worker1", "worker2"):
            process, release = self.guard(step, child_env)
            code, result, _ = self.finish(process, release)
            self.assertEqual((code, result["lease"]["kind"]), (0, "child"))
            if step == "worker1":                              # the gap: no worker of the campaign is running
                process, release = self.guard("intruder", self.env)
                code, _, err = self.finish(process, release)
                self.assertEqual(code, 126)
                self.assertIn("Campaign lease refused admission", err)
        self.assertEqual(held.release(), "released")
        self.assertEqual(L.check(self.coord)[0], "free")

    def test_release_with_a_live_worker_keeps_the_machine_closing(self):
        held = L.acquire("campaign", "stand-in controller", directory=self.coord)
        process, release = self.guard("worker", held.child_environment(self.env), wait=True)
        self.assertEqual(held.release(), "closing")
        with self.assertRaisesRegex(L.LeaseHeld, r"\[closing\]"):
            L.acquire("second campaign", "test", directory=self.coord)
        code, result, _ = self.finish(process, release)
        self.assertEqual((code, result["lease"]["kind"]), (0, "child"))
        self.assertEqual(L.check(self.coord)[0], "free")          # the last worker closed the released lease

    def test_guard_from_a_replay_root_is_excluded(self):
        replay = self.tmp/"replay"
        shutil.copytree(ROOT/"customkf", replay/"customkf", ignore=shutil.ignore_patterns("__pycache__"))
        (replay/"tests").mkdir()
        shutil.copy(ROOT/"tests"/"__init__.py", replay/"tests"/"__init__.py")
        shutil.copy(ROOT/"tests"/"lease_guard_worker.py", replay/"tests"/"lease_guard_worker.py")
        process, release = self.guard("workspace", self.env, wait=True)
        replay_env = {**self.env, "PYTHONPATH": str(replay)}
        intruder, intruder_release = self.guard("replay", replay_env, root=replay)
        code, _, err = self.finish(intruder, intruder_release)
        self.assertEqual(code, 126)                   # its per-root mutex differs; the shared lease refuses it
        self.assertIn("Campaign lease refused admission", err)
        self.assertEqual(self.finish(process, release)[0], 0)

    def test_same_campaign_worker_from_a_replay_root_is_refused(self):
        """Astra Part B, B02: the per-root worker mutex cannot see another root; the lease allows one live child."""
        replay = self.tmp/"replay"
        shutil.copytree(ROOT/"customkf", replay/"customkf", ignore=shutil.ignore_patterns("__pycache__"))
        (replay/"tests").mkdir()
        shutil.copy(ROOT/"tests"/"__init__.py", replay/"tests"/"__init__.py")
        shutil.copy(ROOT/"tests"/"lease_guard_worker.py", replay/"tests"/"lease_guard_worker.py")
        held = L.acquire("campaign", "stand-in controller", directory=self.coord)
        child_env = held.child_environment(self.env)
        process, release = self.guard("first", child_env, wait=True)
        intruder, intruder_release = self.guard("same-token-replay", {**child_env, "PYTHONPATH": str(replay)}, root=replay)
        code, _, err = self.finish(intruder, intruder_release)
        self.assertEqual(code, 126)
        self.assertIn("one worker at a time", err)
        self.assertEqual(self.finish(process, release)[0], 0)
        self.assertEqual(held.release(), "released")

    def test_in_process_controller_campaign_covers_its_workers_and_gaps(self):
        """The shape of Opus_Fork.run_fit_elev: lease.campaign() around serial in-process guard.run() workers."""
        from Opus_Fork import guard as fork
        with L.campaign("controller", "test", directory=self.coord) as held:
            for i in range(2):
                start, release = self.tmp/f"c{i}.start", self.tmp/f"c{i}.release"
                release.write_text("go")
                result, folder = fork.run(["tests.lease_guard_worker", str(start), str(release)],
                                          fork.Limits(memory_mib=128, threads=1, processes=4, timeout_s=60),
                                          usage_ceiling=None, label=f"lease-campaign-{i}", ignore_other_python=True)
                shutil.rmtree(folder, ignore_errors=True)
                self.assertEqual((result["status"], result["lease"]["kind"], result["lease"]["lease_id"]),
                                 ("ok", "child", held.id))
                if i == 0:                                         # the gap between the two workers
                    process, gap_release = self.guard("intruder", self.env)
                    code, _, err = self.finish(process, gap_release)
                    self.assertEqual(code, 126)
                    self.assertIn("Campaign lease refused admission", err)
        self.assertNotIn(L.ENV, os.environ)
        self.assertEqual(L.check(self.coord)[0], "free")

    def test_fork_guard_records_its_admission(self):
        from Opus_Fork import guard as fork
        start, release = self.tmp/"fork.start", self.tmp/"fork.release"
        release.write_text("go")
        os.environ[L.DIR_ENV] = str(self.coord)
        try:
            result, folder = fork.run(["tests.lease_guard_worker", str(start), str(release)],
                                      fork.Limits(memory_mib=128, threads=1, processes=4, timeout_s=60),
                                      usage_ceiling=None, label="lease-integration-test", ignore_other_python=True)
        finally:
            os.environ.pop(L.DIR_ENV, None)
        shutil.rmtree(folder, ignore_errors=True)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["lease"]["kind"], "bare")
        self.assertEqual(result["lease"]["released"], True)
        self.assertEqual(L.check(self.coord)[0], "free")


if __name__ == "__main__":
    unittest.main()
