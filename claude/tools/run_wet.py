"""Direct controller: serial guarded two-node oracle and hourly wet experiment.

--checks-run must be the just-completed wet_checks guard folder. It is copied
and hashed into this archive. Each fit iteration <=300s, at most four hourly
iterations. Does not relax limits or resume an interrupted campaign in place.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha

BASE = ROOT / "validation/guam/20260911T155927Z"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks-run", type=Path, required=True)
    check_path = parser.parse_args().checks_run
    checked = json.loads((check_path / "checks.json").read_text())
    assert checked["status"] == "wet_basis_checks_pass"
    check_result = json.loads((check_path / "result.json").read_text())
    assert check_result["status"] == "ok" and check_result["module_args"] == ["claude.tools.wet_checks"]
    old = json.loads((BASE / "validation.json").read_text())
    sources = {**old["source_sha256"], **{f"claude/tools/{n}.py": sha(ROOT / f"claude/tools/{n}.py") for n in
               ("wet_pilot", "wet_step", "wet_checks", "run_wet", "evaluate_wet", "ablation_step", "yell_continuation_review")}}
    for name, digest in sources.items():
        assert sha(ROOT / name) == digest, name
    for name, digest in old["artifacts_sha256"].items():
        assert sha(BASE / name) == digest, name
    folder = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-wet")
    folder.mkdir()
    shutil.copytree(check_path, folder / "checks")
    for name in sources:
        destination = folder / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    report = {"status": "running", "cases": {}, "runs": {"checks": {**check_result, "original_directory": str(check_path)}},
              "active_worker": None, "source_sha256": sources, "report_sha256": old["report_sha256"],
              "baseline_manifest_sha256": sha(BASE / "validation.json"),
              "predeclared_evaluation": "Same 31 SVs/403 IGS samples; >=5% pooled RMS reduction flags candidate benefit; disclose every >0.1m per-SV regression. Neither is an absolute accuracy gate. Original endpoint level priors retained; increment variance .03^2/3; no other model/data changes."}
    def save():
        pending = folder / "pending.json"
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(folder / "validation.json")
    def worker(name, args, timeout=300):
        report["active_worker"] = {"name": name, "module_args": args, "started_utc": datetime.now(timezone.utc).isoformat()}
        save()
        print("Starting " + name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        shutil.copytree(path, folder / name)
        report["runs"][name] = {**result, "original_directory": str(path)}
        report["active_worker"] = None
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s', 0):.1f}s, {result.get('peak_sampled_rss_mib', 0):.1f} MiB RSS", flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Worker failed: " + name)
        return folder / name
    save()
    try:
        for case, nodes in (("two-node", 2), ("hourly", 4)):
            report["cases"][case] = {"final": None, "iterations": []}
            previous = None
            for i in range(1 if nodes == 2 else 4):
                args = ["claude.tools.wet_step", "--nodes", str(nodes)]
                if previous:
                    args.extend(["--previous", str(previous)])
                previous = worker(f"{case}-{i}", args)
                report["cases"][case]["iterations"].append(previous.name)
                if json.loads((previous / "step.json").read_text())["status"] == "converged":
                    report["cases"][case]["final"] = previous.name
                    save()
                    break
            if not report["cases"][case]["final"]:
                raise RuntimeError("Iteration cap reached: " + case)
        worker("evaluation", ["claude.tools.evaluate_wet", str(folder)], 120)
        for group in ("source_sha256", "report_sha256"):
            for name, digest in report[group].items():
                assert sha(ROOT / name) == digest, name
        report["status"] = "wet_experiment_complete_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        values = list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                      peak_sampled_rss_mib=max(v.get("peak_sampled_rss_mib", 0) for v in values),
                      minimum_system_available_gib=min(v.get("minimum_system_available_gib", float("inf")) for v in values))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*") if p.is_file() and p.name != "validation.json"}
        save()
    print("Archived: " + str(folder), flush=True)


if __name__ == "__main__":
    main()
