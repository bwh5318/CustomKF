"""Direct serial-guard controller for bounded 3h/6h ten-minute arc experiment.

Imports completed preparation guards; verifies fresh source pins, checks models,
then cold-starts each fit for at most five 300-second iterations. No limit changes.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha
from claude.tools.pinned_sources import verify

BASE = ROOT/"validation/guam/20260911T155927Z"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Do not nest guards")
    parser = argparse.ArgumentParser(); parser.add_argument("--three",type=Path,required=True); parser.add_argument("--six",type=Path,required=True)
    args = parser.parse_args(); drift = verify()
    old = json.loads((BASE/"validation.json").read_text())
    for name,digest in old["artifacts_sha256"].items(): assert sha(BASE/name)==digest,name
    sources = {p.relative_to(ROOT).as_posix():sha(p) for d in ("customkf","tests") for p in sorted((ROOT/d).glob("*.py"))}
    for name in ("arc_pilot","arc_step","arc_checks","evaluate_arc","run_arc","ablation_step","evaluate_ablation","pinned_sources"):
        path = f"claude/tools/{name}.py"; sources[path] = sha(ROOT/path)
    folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-arc")
    folder.mkdir()
    for name in sources:
        target=folder/"source"/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,target)
    report = dict(status="running",cases={},runs={},active_worker=None,source_sha256=sources,
        source_transition=drift,report_sha256=old["report_sha256"],baseline_manifest_sha256=sha(BASE/"validation.json"),
        predeclared_evaluation="Same 14 stations and 31 satellites. Cold-start both 10-minute cases. Compare 403 common native IGS samples (12-15 GPST); full six-hour 775 samples separate. Existing 3h/5min solution is density control. >=5% RMS improvement is a candidate-benefit flag, not accuracy acceptance. Disclose >0.1m per-SV regressions and unchanged 10m formal-sigma classes. Keep native tracking, fixed weights and all station rows. Retain original 0h/3h wet priors and add only a .03m 3h-to-6h continuity equation. Inspect known GUAM 17:20-17:35 PPP episode; no automatic exclusion.")
    def save():
        pending=folder/"pending.json"; pending.write_text(json.dumps(report,indent=2)+"\n"); pending.replace(folder/"validation.json")
    def check_sources():
        for group in ("source_sha256","report_sha256"):
            for name,digest in report[group].items(): assert sha(ROOT/name)==digest,name
    def worker(name,arguments,timeout=300):
        check_sources(); report["active_worker"] = dict(name=name,module_args=arguments,started_utc=datetime.now(timezone.utc).isoformat()); save()
        print("Starting "+name,flush=True)
        result,path=run(arguments,Limits(timeout_s=timeout)); shutil.copytree(path,folder/name)
        report["runs"][name]={**result,"original_directory":str(path)}; report["active_worker"]=None; save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f}s",flush=True)
        if result["status"]!="ok": raise RuntimeError("Worker failed: "+name)
        return folder/name
    save(); print("Campaign: "+str(folder),flush=True)
    try:
        for case,path in (("three",args.three),("six",args.six)):
            result=json.loads((path/"result.json").read_text()); meta=json.loads((path/"step.json").read_text())
            assert result["status"]=="ok" and result["module_args"]==["claude.tools.arc_step","prepare","--case",case]
            assert meta["budget_pass"] and sha(path/"fixture.json")==meta["fixture_sha256"]
            for name,digest in meta["source_sha256"].items(): assert sources[name]==digest,name
            shutil.copytree(path,folder/f"{case}-prepare")
            report["runs"][f"{case}-prepare"]={**result,"original_directory":str(path)}
            report["cases"][case]=dict(prepare=f"{case}-prepare",final=None,iterations=[])
        save()
        tests = ["test_comparison","test_sp3","test_dynamics","test_propagation","test_stage2","test_stage3","test_stage3_models","test_stage4","test_stage5","test_navigation_fit","test_reduced_network","test_stage5b_inputs","test_nonlinear_stop","test_arc_profile"]
        worker("tests",["unittest",*["tests."+n for n in tests],"-v"],120)
        worker("oracle-checks",["claude.tools.arc_checks",str(BASE/"prepare/fixture.json")])
        worker("six-checks",["claude.tools.arc_checks",str(folder/"six-prepare/fixture.json")])
        for case in ("three","six"):
            previous=None
            for i in range(5):
                arguments=["claude.tools.arc_step","iterate","--case",case,"--fixture",str(folder/f"{case}-prepare/fixture.json")]
                if previous: arguments.extend(["--previous",str(previous)])
                previous=worker(f"{case}-{i}",arguments)
                report["cases"][case]["iterations"].append(previous.name)
                if json.loads((previous/"step.json").read_text())["status"]=="converged":
                    report["cases"][case]["final"]=previous.name; save(); break
                save()
            if not report["cases"][case]["final"]: raise RuntimeError("Iteration cap: "+case)
        worker("evaluation",["claude.tools.evaluate_arc",str(folder)],120)
        check_sources(); report["status"]="arc_experiment_complete_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed",error=str(error)); raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s",0) for v in values),
                      peak_sampled_rss_mib=max((v.get("peak_sampled_rss_mib",0) for v in values),default=0),
                      peak_job_memory_mib=max((v.get("windows_peak_job_memory_mib",0) for v in values),default=0),
                      minimum_system_available_gib=min((v.get("minimum_system_available_gib",float("inf")) for v in values),default=None))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"}
        save()
    print("Archived: "+str(folder),flush=True)


if __name__ == "__main__": main()
