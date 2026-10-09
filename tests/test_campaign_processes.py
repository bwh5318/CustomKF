"""customkf.runtime.processes: which Python processes the fork guard and Opus_Fork.run_fit_elev wait for (user
decision, 3 Oct 2026: this project's guard and campaign-controller processes only).

    C:\\anaconda\\python.exe -m unittest tests.test_campaign_processes -v

The real-process tests start short-lived sleepers: one plain script (not counted), and one module named like a
campaign controller from a temporary package directory, so no project code runs. Both are killed afterwards.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import psutil

from customkf.runtime import processes as P
from Opus_Fork import guard

PY = "C:\\anaconda\\python.exe"


class ModuleOf(unittest.TestCase):
    def test_module_forms(self):
        cases = {
            (PY, "-m", "Opus_Fork.guard", "--profile", "fork8"): "Opus_Fork.guard",
            (PY, "-u", "-m", "customkf.guard"): "customkf.guard",
            (PY, "-um", "Opus_Fork.run_fit_elev"): "Opus_Fork.run_fit_elev",
            (PY, "-mOpus_Fork.guard"): "Opus_Fork.guard",
            (PY, "-X", "utf8", "-W", "ignore", "-m", "Opus_Fork.guard"): "Opus_Fork.guard",
            (PY, "-Xutf8", "-m", "Opus_Fork.guard"): "Opus_Fork.guard",
            (PY, "--check-hash-based-pycs", "never", "-m", "customkf.guard"): "customkf.guard",
            (PY, "-m", "Opus_Fork.evaluate", "-m", "Opus_Fork.guard"): "Opus_Fork.evaluate",
        }
        for cmdline, module in cases.items():
            self.assertEqual(P.module_of(cmdline), module, cmdline)

    def test_not_a_module(self):
        for cmdline in [(PY, "script.py", "-m", "Opus_Fork.guard"), (PY, "-c", "pass", "-m", "Opus_Fork.guard"),
                        (PY, "-cpass", "-m", "Opus_Fork.guard"), (PY,), (PY, "-m"), (PY, "-", "-m", "Opus_Fork.guard"),
                        (PY, "--", "-m", "Opus_Fork.guard"), None, []]:
            self.assertIsNone(P.module_of(cmdline), cmdline)

    def test_campaign_pattern(self):
        for module in ("customkf.guard", "Opus_Fork.guard", "Opus_Fork.run_fit", "Opus_Fork.run_fit_elev",
                       "Opus_Fork.run_fit_e7"):
            self.assertTrue(P.CAMPAIGN_MODULE.match(module), module)
        for module in ("Opus_Fork.evaluate", "Opus_Fork.guardian", "customkf.guard.x", "Opus_Fork.run_fitx.y",
                       "unittest", "Opus_Fork.experiments.gradients.analyze_validation", "xOpus_Fork.guard"):
            self.assertFalse(P.CAMPAIGN_MODULE.match(module), module)


def fake(pid, name, cmdline):
    return mock.Mock(info=dict(pid=pid, name=name, cmdline=cmdline))


class Selection(unittest.TestCase):
    def test_only_project_guards_and_controllers_count(self):
        procs = [fake(11, "python.exe", [PY, "-m", "Opus_Fork.guard", "--", "Opus_Fork.evaluate"]),
                 fake(12, "python.exe", [PY, "-m", "Opus_Fork.run_fit_elev", "--variant", "x"]),
                 fake(13, "pythonw.exe", [PY, "-m", "customkf.guard", "--", "m"]),
                 fake(14, "python.exe", [PY, "-m", "unittest", "tests.test_guard"]),        # a test run
                 fake(15, "python.exe", [PY, "other_project/train.py"]),                    # another project
                 fake(16, "python.exe", None),                                              # unreadable command line
                 fake(17, "node.exe", ["node", "-m", "Opus_Fork.guard"]),                   # not Python
                 fake(18, None, None)]
        with mock.patch.object(P.psutil, "process_iter", return_value=procs):
            self.assertEqual(P.campaign_processes(), [11, 12, 13])
            self.assertEqual(P.campaign_processes(exclude=[12]), [11, 13])
            self.assertEqual(guard.other_python_processes(allowed=[11]), [12, 13])

    def test_own_process_is_excluded(self):
        import os
        procs = [fake(os.getpid(), "python.exe", [PY, "-m", "Opus_Fork.run_fit_elev"])]
        with mock.patch.object(P.psutil, "process_iter", return_value=procs):
            self.assertEqual(P.campaign_processes(), [])

    def test_guard_refusal_names_the_process_and_keeps_its_opening_words(self):
        """The chain scripts match "Another Python process is running" as an external stop."""
        with mock.patch.object(guard, "other_python_processes", return_value=[4242]):
            with self.assertRaisesRegex(RuntimeError, r"^Another Python process is running .*4242"):
                guard.run(["Opus_Fork.evaluate"], guard.Limits(memory_mib=128, cpu_percent=10, threads=1, processes=1,
                                                               timeout_s=5), usage_ceiling=None, label="never-starts")


class RealProcesses(unittest.TestCase):
    def wait_listed(self, pid, expected):
        for _ in range(100):
            if (pid in P.campaign_processes()) == expected and psutil.pid_exists(pid):
                return True
            time.sleep(.05)
        return False

    def spawn(self, argv, cwd):
        proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (proc.kill(), proc.wait(10)))
        time.sleep(.3)
        self.assertIsNone(proc.poll(), "sleeper exited early")
        return proc

    def test_plain_python_is_not_counted_and_a_campaign_module_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)/"Opus_Fork"
            package.mkdir()
            (package/"__init__.py").write_text("")
            (package/"run_fit_probe.py").write_text("import time\ntime.sleep(30)\n")
            plain = self.spawn([sys.executable, "-c", "import time; time.sleep(30)", "-m", "Opus_Fork.guard"], tmp)
            probe = self.spawn([sys.executable, "-m", "Opus_Fork.run_fit_probe"], tmp)
            self.assertTrue(self.wait_listed(probe.pid, True), "campaign-named module not counted")
            self.assertNotIn(plain.pid, P.campaign_processes())
            probe.kill(), probe.wait(10)
            plain.kill(), plain.wait(10)


if __name__ == "__main__":
    unittest.main()
