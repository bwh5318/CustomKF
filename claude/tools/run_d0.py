"""Direct serial guard controller for the station-only six-hour D0 diagnostic.

Import a completed preparation; split each iteration into <=300s linearization
and individual trials. Checkpoints and active-worker records survive interruption.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
from customkf.guard import ROOT,Limits,run
from customkf.prepare_stage2 import sha
from claude.tools.d0_step import BASE


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    parser=argparse.ArgumentParser();parser.add_argument("--prepare",type=Path,required=True);args=parser.parse_args()
    old=json.loads((BASE/"validation.json").read_text());meta=json.loads((args.prepare/"step.json").read_text())
    prepared=json.loads((args.prepare/"result.json").read_text())
    assert prepared["status"]=="ok" and meta["budget_pass"] and meta["embedded_baseline_bitwise"]
    assert sha(args.prepare/"fixture.json")==meta["fixture_sha256"]
    sources={**old["source_sha256"],**{f"claude/tools/{n}.py":sha(ROOT/f"claude/tools/{n}.py") for n in
        ("d0_pilot","d0_step","d0_iteration","evaluate_d0","run_d0","force_parameter_fit","yell_continuation_review")},
        "D0_POD_PROTOCOL.md":sha(ROOT/"D0_POD_PROTOCOL.md")}
    assert sources["D0_POD_PROTOCOL.md"]==meta["protocol_sha256"]
    for name,digest in sources.items():assert sha(ROOT/name)==digest,name
    folder=ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-station-d0");folder.mkdir()
    shutil.copytree(args.prepare,folder/"prepare")
    for name in sources:
        target=folder/"source"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    report=dict(status="running",source_sha256=sources,report_sha256=old["report_sha256"],baseline_manifest_sha256=sha(BASE/"validation.json"),
        runs={"prepare":{**prepared,"original_directory":str(args.prepare)}},active_worker=None,final=None,accepted_trials=[],
        controller_pid=os.getpid(),stationarity_note="1mm threshold additionally includes force-plus-state tangent displacement on 5-minute grid")
    def save():
        pending=folder/"pending.json";pending.write_text(json.dumps(report,indent=2)+"\n");pending.replace(folder/"validation.json")
    def worker(name,arguments,timeout=300):
        for group in ("source_sha256","report_sha256"):
            for path,digest in report[group].items():assert sha(ROOT/path)==digest,path
        report["active_worker"]=dict(name=name,module_args=arguments,controller_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat());save()
        print("Starting "+name,flush=True);result,path=run(arguments,Limits(timeout_s=timeout));shutil.copytree(path,folder/name)
        report["runs"][name]={**result,"original_directory":str(path)};report["active_worker"]=None;save()
        print(f"{name}: {result['status']} {result.get('elapsed_s',0):.1f}s",flush=True)
        if result["status"]!="ok":raise RuntimeError("Worker failed: "+name)
        return folder/name
    save();print("Campaign: "+str(folder),flush=True)
    try:
        previous=folder/"prepare/warm";fixture=folder/"prepare/fixture.json"
        for i in range(4):
            linear=worker(f"linear-{i}",["claude.tools.d0_iteration","linear","--fixture",str(fixture),"--previous",str(previous)])
            if json.loads((linear/"step.json").read_text())["status"]=="converged":report["final"]=linear.name;save();break
            accepted=False
            for ai,alpha in enumerate((1.,.5,.25,.125)):
                trial=worker(f"trial-{i}-{ai}",["claude.tools.d0_iteration","trial","--fixture",str(fixture),"--linear",str(linear),"--alpha",str(alpha)])
                if json.loads((trial/"step.json").read_text())["status"]=="iteration_complete":
                    previous=trial;report["accepted_trials"].append(trial.name);save();accepted=True;break
            if not accepted:raise RuntimeError("No accepted trial")
        if report["final"] is None:raise RuntimeError("Iteration cap")
        worker("evaluation",["claude.tools.evaluate_d0",str(folder)],120)
        report["status"]="station_d0_complete_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values());report.update(total_guarded_seconds=sum(v.get("elapsed_s",0) for v in values),
            peak_job_memory_mib=max(v.get("windows_peak_job_memory_mib",0) for v in values),
            minimum_system_available_gib=min(v.get("minimum_system_available_gib",float("inf")) for v in values))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"};save()
    print("Archived: "+str(folder),flush=True)


if __name__=="__main__":main()
