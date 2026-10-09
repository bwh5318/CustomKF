"""Serial Stage 4 validation controller, using the unchanged Windows guard.

Run directly with existing Python; do not place this controller inside a guard.
All numerical work is delegated to one guarded worker at a time. No downloads.
"""
from datetime import datetime, timezone
import importlib.metadata
import json
import os
import shutil
import sys
from .guard import ROOT, Limits, run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest the resource guard")
    destination = ROOT/"validation/stage4"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True, exist_ok=False)
    sources = [*(ROOT/"customkf").glob("*.py"), *(ROOT/"tests").glob("*.py"),
               *(ROOT/"data/stage3").glob("*manifest.json"), ROOT/"data/stage2/manifest.json"]
    report = {"status": "running", "python": sys.version, "executable": sys.executable,
        "source_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)},
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ("numpy", "scipy", "numba", "pyerfa", "psutil", "threadpoolctl")}, "runs": {}}

    def save():
        (destination/"validation.json").write_text(json.dumps(report, indent=2)+"\n")

    def launch(name, args):
        print("Starting "+name, flush=True)
        result, folder = run(args, Limits(timeout_s=300 if name == "network" else 120))
        shutil.copytree(folder, destination/name)
        report["runs"][name] = {**result, "run_directory": str(folder)}
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s', 0):.2f}s, "
              f"{result.get('peak_sampled_rss_mib', 0):.1f} MiB RSS", flush=True)
        if result["status"] != "ok":
            raise RuntimeError(f"Guarded validation failed: {folder}")

    save()
    try:
        modules = ["tests.test_"+name for name in
                   ("comparison", "sp3", "dynamics", "propagation", "stage2", "stage3", "stage3_models", "stage4")]
        launch("unit_tests", ["unittest", *modules, "-v"])
        launch("network", ["customkf.run_stage4"])
        network = json.loads((destination/"network/stage4.json").read_text())
        if network["status"] != "passed_stage4_linear_algebra_gate":
            raise RuntimeError("Network audit did not pass")
        for path, digest in report["source_sha256"].items():
            if sha(ROOT/path) != digest:
                raise RuntimeError("Source changed during validation")
            target = destination/"source"/path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/path, target)
        report.update(status="passed_stage4_linear_algebra_gate",
            total_guarded_seconds=sum(r["elapsed_s"] for r in report["runs"].values()),
            peak_sampled_rss_mib=max(r["peak_sampled_rss_mib"] for r in report["runs"].values()),
            peak_private_commit_mib=max(r["windows_peak_job_memory_mib"] for r in report["runs"].values()),
            minimum_system_available_gib=min(r["minimum_system_available_gib"] for r in report["runs"].values()),
            scientific_scope="Estimates/covariance/datum/event algebra passed; independent POD and rapid-latency validation remain future gates")
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        save()
    print("Stage 4 archived: "+str(destination), flush=True)


if __name__ == "__main__":
    main()
