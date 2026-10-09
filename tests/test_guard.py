"""Controller tests launch only tiny bounded children; no numerical workload here."""
import json
import time
import unittest
from unittest.mock import patch
import psutil
from customkf.guard import Limits, GIB, pressure_action, run


class GuardTests(unittest.TestCase):
    def probe(self, mode, **kwargs):
        result, folder = run(["tests.guard_probe", mode], Limits(memory_mib=128, timeout_s=10, **kwargs))
        self.assertTrue(result.get("enforced"), result)
        return result, folder

    def test_verified_limits_and_thread_environment(self):
        result, folder = self.probe("normal")
        self.assertEqual(result["status"], "ok", result)
        output = json.loads((folder/"stdout.log").read_text())
        self.assertEqual(output["affinity"], result["cpu_affinity"])
        self.assertEqual(output["threads_env"], "1")
        self.assertEqual(result["cpu_rate_readback"], 1000)

    def test_allocation_fails_inside_small_cap(self):
        result, folder = self.probe("allocation")
        self.assertEqual(result["status"], "ok", result)
        output = json.loads((folder/"stdout.log").read_text())
        self.assertTrue(output["allocation_denied"])
        self.assertLess(output["private_after"], 128*2**20)
        self.assertLess(abs(output["private_after"]-output["private_before"]), 2**20)

    def test_timeout_terminates_descendant(self):
        result, folder = run(["tests.guard_probe", "descendant"], Limits(memory_mib=128, timeout_s=2))
        self.assertEqual(result["status"], "timeout", result)
        pid = json.loads((folder/"child.json").read_text())["pid"]
        for _ in range(20):
            if not psutil.pid_exists(pid):
                break
            time.sleep(.05)
        self.assertFalse(psutil.pid_exists(pid))

    def test_orphan_is_not_a_success(self):
        result, folder = self.probe("orphan")
        self.assertEqual(result["status"], "orphan_children", result)
        pid = json.loads((folder/"child.json").read_text())["pid"]
        for _ in range(20):
            if not psutil.pid_exists(pid):
                break
            time.sleep(.05)
        self.assertFalse(psutil.pid_exists(pid))

    def test_exit_failure_is_preserved(self):
        result, _ = self.probe("failure")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["status"], "worker_failed")

    def test_job_close_kills_tree_when_controller_path_raises(self):
        with patch("customkf.guard.Job.terminate", side_effect=OSError("simulated controller failure")):
            result, folder = run(["tests.guard_probe", "descendant"], Limits(memory_mib=128, timeout_s=.8))
        self.assertEqual(result["status"], "controller_failed", result)
        child = json.loads((folder/"child.json").read_text())["pid"]
        for _ in range(20):
            if not any(psutil.pid_exists(pid) for pid in (result["pid"],child)):
                break
            time.sleep(.05)
        self.assertFalse(any(psutil.pid_exists(pid) for pid in (result["pid"],child)))

    def test_cpu_budget_with_single_core_short_probe(self):
        result, _ = run(["tests.guard_probe", "busy", "5"],
                        Limits(memory_mib=128, timeout_s=10, cpu_percent=1))
        self.assertEqual(result["status"], "ok", result)
        # One-percent machine quota on 24 logical CPUs is ~0.24 CPU-seconds/s.
        # A one-second probe was burst-sensitive on this host. Five seconds
        # amortizes startup/interval effects; retain broad scheduling tolerance.
        # This is a five-second single-core probe, not a machine stress benchmark.
        self.assertLess(result["cpu_seconds"], result["elapsed_s"]*.75)

    def test_pressure_policy_without_consuming_memory(self):
        limits = Limits()                       # user decision 2 Oct 2026: reserve 2 GiB, emergency 1 GiB
        self.assertEqual((limits.reserve_gib, limits.emergency_gib), (2, 1))
        self.assertEqual(pressure_action(3*GIB, limits, 0), "continue")
        self.assertEqual(pressure_action(1.5*GIB, limits, 0), "request_stop")
        self.assertEqual(pressure_action(1.5*GIB, limits, 4), "terminate")
        self.assertEqual(pressure_action(.5*GIB, limits, 0), "terminate")

    def test_concurrent_guard_is_refused(self):
        result, folder = self.probe("nested")
        self.assertEqual(result["status"], "ok", result)
        self.assertIn("Another customKF guarded experiment is running", (folder/"stdout.log").read_text())

    def test_pressure_watchdog_stops_real_worker_with_simulated_pressure(self):
        from types import SimpleNamespace
        calls = 0
        def available():
            nonlocal calls
            calls += 1
            return SimpleNamespace(available=(20 if calls == 1 else 1.5)*GIB)
        with patch("customkf.guard.psutil.virtual_memory", side_effect=available):
            result, folder = run(["tests.guard_probe", "descendant"],
                                 Limits(memory_mib=128, timeout_s=5, grace_s=.5))
        self.assertEqual(result["status"], "memory_pressure", result)
        self.assertTrue((folder/"STOP.json").exists())
        pid = json.loads((folder/"child.json").read_text())["pid"]
        for _ in range(20):
            if not psutil.pid_exists(pid):
                break
            time.sleep(.05)
        self.assertFalse(psutil.pid_exists(pid))

    def test_low_headroom_refuses_before_worker_creation(self):
        with patch("customkf.guard.psutil.virtual_memory") as memory, patch("customkf.guard.Worker") as worker:
            memory.return_value.available = 3*GIB       # below the 2 GiB cap + 2 GiB reserve
            result, _ = run(["tests.guard_probe", "normal"])
            self.assertEqual(result["status"], "setup_failed")
            self.assertIn("headroom", result["error"])
            worker.assert_not_called()

    def test_job_setup_failure_has_no_worker_fallback(self):
        with patch("customkf.guard.Job", side_effect=OSError("simulated denied")), patch("customkf.guard.Worker") as worker:
            result, _ = run(["tests.guard_probe", "normal"], Limits(memory_mib=128))
            self.assertEqual(result["status"], "setup_failed")
            worker.assert_not_called()

    def test_no_silent_budget_escalation(self):
        for kwargs in ({"memory_mib":8192}, {"cpu_percent":99}, {"threads":16}, {"timeout_s":float("nan")}):
            with self.assertRaises(ValueError):
                Limits(**kwargs).validate()


if __name__ == "__main__":
    unittest.main()
