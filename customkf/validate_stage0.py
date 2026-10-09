"""Lightweight test controller. All numerical workloads are launched in guarded jobs."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

import psutil
from .guard import ROOT, Limits, run
from .prepare_stage0 import digest


def main():
    started = time.monotonic()
    report = {"started_utc":datetime.now(timezone.utc).isoformat(), "python":sys.version,
              "python_executable":sys.executable, "platform":platform.platform(),
              "logical_cpus":psutil.cpu_count(), "physical_cpus":psutil.cpu_count(logical=False),
              "physical_memory_gib":psutil.virtual_memory().total/2**30}
    tested_files = [*(ROOT/"customkf").glob("*.py"), *(ROOT/"tests").glob("*.py"),
                    ROOT/"COMPARISON_CONTRACT.md", ROOT/"data"/"stage0"/"manifest.json"]
    report["tested_file_sha256"] = {path.relative_to(ROOT).as_posix():digest(path) for path in sorted(tested_files)}
    from tests.test_guard import GuardTests
    stream = io.StringIO()
    previous_runs = set((ROOT/"runs").glob("*"))
    control = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    print(stream.getvalue())
    report["controller_tests"] = {"count":control.testsRun, "successful":control.wasSuccessful(),
                                  "log":stream.getvalue()}
    report["controller_probe_runs"] = []
    for folder in sorted(set((ROOT/"runs").glob("*"))-previous_runs):
        record = json.loads((folder/"result.json").read_text())
        output = folder/"stdout.log"
        report["controller_probe_runs"].append({**record,"run_directory":str(folder),
                                                "stdout":output.read_text() if output.exists() else ""})
    if not control.wasSuccessful():
        return 1
    result, folder = run(["unittest","tests.test_comparison","tests.test_sp3","-v"], Limits(timeout_s=60))
    report["numerical_tests"] = {**result, "run_directory":str(folder), "log":(folder/"stderr.log").read_text()}
    print(report["numerical_tests"]["log"])
    if result["status"] != "ok":
        return 1
    audit, folder = run(["customkf.audit_stage0"], Limits(timeout_s=60))
    report["real_data_audit"] = {**audit, "run_directory":str(folder)}
    if audit["status"] != "ok":
        print((folder/"stderr.log").read_text())
        return 1
    report["audit_findings"] = json.loads((folder/"audit.json").read_text())
    report.update(status="pass",elapsed_s=time.monotonic()-started)
    target = ROOT/"validation"/"stage0"
    target.mkdir(parents=True, exist_ok=True)
    # A prior successful report is not overwritten by a failing validation.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = target/f"{stamp}.json"
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":"pass", "report":str(output), "elapsed_s":report["elapsed_s"],
                      "audit_sampled_rss_mib":audit["peak_sampled_rss_mib"],
                      "audit_minimum_available_gib":audit["minimum_system_available_gib"]},indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
