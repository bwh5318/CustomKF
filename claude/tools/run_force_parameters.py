"""Direct serial-guard controller; resumable checkpoints for free-force diagnostics.

Default pilot: G04,G19,G23. --all runs both frozen variants for all 31.
--resume CAMPAIGN continues unfinished work only, verifying all completed hashes.
No production source edits, report rebuilds, nested guards or increased limits.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
from customkf.guard import ROOT,Limits,run
from customkf.prepare_stage2 import sha
from claude.tools.dynamics_six_step import locate


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    parser=argparse.ArgumentParser(); parser.add_argument("--all",action="store_true")
    parser.add_argument("--resume",type=Path); args=parser.parse_args()
    _,_,_,arc=locate("six")
    helpers=("force_parameter_fit","force_parameter_step","force_parameter_checks","force_parameter_review","run_force_parameters",
             "dynamics_six_step","pinned_sources","evaluate_ablation","dynamics_ceiling_step")
    sources={**arc["source_sha256"],**{f"claude/tools/{n}.py":sha(ROOT/f"claude/tools/{n}.py") for n in helpers},
             "FORCE_PARAMETER_PROTOCOL.md":sha(ROOT/"FORCE_PARAMETER_PROTOCOL.md")}
    for name,digest in sources.items():assert sha(ROOT/name)==digest,name
    if args.resume:
        folder=args.resume.resolve(); report=json.loads((folder/"validation.json").read_text())
        if report["status"]=="force_parameter_campaign_complete_not_POD":raise ValueError("Already complete")
        assert sources==report["source_sha256"]
        # Do not resume while a controller/guard may still be active. Operator must check PID.
        if report.get("active_worker"):raise RuntimeError("Unresolved active worker; inspect saved PID/guard and archive result first")
        for name,digest in report.get("artifacts_sha256",{}).items():assert sha(folder/name)==digest,name
        report["status"]="running"
    else:
        folder=ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-force-parameters");folder.mkdir()
        six=json.loads((ROOT/"claude/runs/20260912T025241Z-dynamics-six/validation.json").read_text())
        sats=sorted(six["completed"]) if args.all else ["G04","G19","G23"]
        report=dict(status="running",satellites=sats,variants=["d0","ecom5"],completed=[],runs={},active_worker=None,
            source_sha256=sources,report_sha256=arc["report_sha256"],controller_pid=os.getpid(),
            scope="all_31" if args.all else "selected_three_satellite_pilot_not_constellation_summary",
            source_six_manifest_sha256=sha(ROOT/"claude/runs/20260912T025241Z-dynamics-six/validation.json"))
        for name in sources:
            target=folder/"source"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        repeat=ROOT/"runs/20260912T030715Z-c90c6025"
        if repeat.exists():shutil.copytree(repeat,folder/"opus-repeat-review")
    def save():
        pending=folder/"pending.json";pending.write_text(json.dumps(report,indent=2)+"\n");pending.replace(folder/"validation.json")
    def worker(name,arguments,timeout=300):
        for group in ("source_sha256","report_sha256"):
            for path,digest in report[group].items():assert sha(ROOT/path)==digest,path
        if name in report["runs"] and report["runs"][name]["status"]=="ok":return
        # Keep failed attempts; successful name is stable for downstream review.
        if (folder/name).exists():
            failure=folder/(name+"-failed-"+datetime.now(timezone.utc).strftime("%H%M%S"))
            (folder/name).rename(failure)
        report["active_worker"]=dict(name=name,module_args=arguments,controller_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat());save()
        print("Starting "+name,flush=True);result,path=run(arguments,Limits(timeout_s=timeout))
        shutil.copytree(path,folder/name);report["runs"][name]={**result,"original_directory":str(path)}
        report["active_worker"]=None;save()
        print(f"{name}: {result['status']} {result.get('elapsed_s',0):.1f}s",flush=True)
        if result["status"]!="ok":raise RuntimeError("Worker failed: "+name)
    save();print("Campaign: "+str(folder),flush=True)
    try:
        worker("checks",["claude.tools.force_parameter_checks"])
        for sat in ["G04","G19","G23"]:
            worker("fixed-"+sat,["claude.tools.force_parameter_step","--satellite",sat,"--variant","fixed"])
        for sat in report["satellites"]:
            for variant in report["variants"]:
                name=variant+"-"+sat
                if name in report["completed"]:continue
                worker(name,["claude.tools.force_parameter_step","--satellite",sat,"--variant",variant])
                report["completed"].append(name);save()
        worker("review",["claude.tools.force_parameter_review",str(folder)],120)
        report["status"]="force_parameter_campaign_complete_not_POD"
    except Exception as error:
        report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s",0) for v in values),
            peak_job_memory_mib=max((v.get("windows_peak_job_memory_mib",0) for v in values),default=0),
            minimum_system_available_gib=min((v.get("minimum_system_available_gib",float("inf")) for v in values),default=None))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"}
        save()
    print("Archived: "+str(folder),flush=True)


if __name__=="__main__":main()
