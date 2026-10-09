"""Direct serial controller for three selected fixed-force reference-only fits.

--validation-run supplies the successful guarded synthetic/derivative check.
No observation-estimator outputs are overwritten; each worker <=300 seconds.
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
    parser.add_argument("--validation-run", type=Path, required=True)
    checked_path = parser.parse_args().validation_run
    checks = json.loads((checked_path / "diagnostic.json").read_text())
    checked_run = json.loads((checked_path / "result.json").read_text())
    assert checks["status"] == "fixed_force_synthetic_and_partial_checks_pass" and checked_run["status"] == "ok"
    for name, digest in checks["helper_sources_sha256"].items():
        assert sha(ROOT / name) == digest, name
    baseline = json.loads((BASE / "validation.json").read_text())
    sources = {**baseline["source_sha256"], **{f"claude/tools/{n}.py": sha(ROOT / f"claude/tools/{n}.py") for n in
                ("fixed_force_fit", "dynamics_ceiling_step", "dynamics_ceiling_review", "run_dynamics_ceiling")}}
    for name, digest in sources.items():
        assert sha(ROOT / name) == digest, name
    for name, digest in baseline["artifacts_sha256"].items():
        assert sha(BASE / name) == digest, name
    folder = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-dynamics-ceiling")
    folder.mkdir()
    shutil.copytree(checked_path, folder / "checks")
    for name in sources:
        target = folder / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    report = {"status": "running", "source_sha256": sources, "report_sha256": baseline["report_sha256"],
              "baseline_manifest_sha256": sha(BASE / "validation.json"), "completed": {}, "active_worker": None,
              "runs": {"checks": {**checked_run, "original_directory": str(checked_path)}},
              "predeclared_protocol": "G18/G03/G22, unchanged Trajectory and ECOM5 [-1e-7,0,0,0,0]. Six initial-state components only, no priors, broadcast initialization. 7 half-hour native IGS positions train; 6 interleaved quarter-hours held out. Report rank, scaled condition and train/held/all Cartesian RMS. Held-out <0.1m is a diagnostic flag, not an independent POD gate. Four nonlinear iterations per satellite; no force release or retuning in this campaign."}
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
            raise RuntimeError("Failed worker: " + name)
        return folder / name
    save()
    try:
        for sat in ("G18", "G03", "G22"):
            worker(sat, ["claude.tools.dynamics_ceiling_step", "--satellite", sat])
            report["completed"][sat] = sat
            save()
        worker("review", ["claude.tools.dynamics_ceiling_review", str(folder)], 120)
        for group in ("source_sha256", "report_sha256"):
            for name, digest in report[group].items():
                assert sha(ROOT / name) == digest, name
        report["status"] = "fixed_force_reference_diagnostic_complete_not_independent_POD"
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
