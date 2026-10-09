"""Run directly, never nested: serial 14-station prior/start sensitivity campaign.

Default: baseline reproduction, 10x-weaker warm start, 10x-weaker perturbed start.
--cases weak-cold is a separate optional broadcast cold-start confirmation.
Each numerical iteration uses an unchanged 300 s guard; at most four per case.
"""
import argparse
from datetime import datetime,timezone
import json
import os
import shutil

from customkf.guard import ROOT,Limits,run
from customkf.prepare_stage2 import sha

BASE=ROOT/"validation/guam/20260911T155927Z"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    parser=argparse.ArgumentParser();parser.add_argument("--cases",default="baseline-check,weak-warm,weak-perturbed")
    names=parser.parse_args().cases.split(",")
    if len(set(names))!=len(names) or not set(names)<=set(("baseline-check","weak-warm","weak-perturbed","weak-cold")):raise ValueError("Invalid cases")
    folder=ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-stability");folder.mkdir()
    old=json.loads((BASE/"validation.json").read_text())
    sources={**old["source_sha256"],**{f"claude/tools/{n}.py":sha(ROOT/f"claude/tools/{n}.py") for n in ("stability_step","run_stability","evaluate_stability","ablation_step")}}
    for name,digest in sources.items():assert sha(ROOT/name)==digest,name
    for name,digest in old["artifacts_sha256"].items():assert sha(BASE/name)==digest,name
    report={"status":"running","cases":{},"runs":{},"active_worker":None,"source_sha256":sources,
            "report_sha256":old["report_sha256"],"baseline_manifest_sha256":sha(BASE/"validation.json"),
            "predeclared_gate":"Max sampled 3D orbit difference <=0.01 m; retain all SVs. Original broadcast prior centres unchanged. Perturbed start: alternating RAC [100,-70,40] m and [.02,-.01,.01] m/s; nuisance parameters zero."}
    for name in sources:
        target=folder/"source"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    def save():
        pending=folder/"pending.json";pending.write_text(json.dumps(report,indent=2)+"\n");pending.replace(folder/"validation.json")
    def worker(name,args,timeout=300):
        report["active_worker"]={"name":name,"module_args":args,"started_utc":datetime.now(timezone.utc).isoformat()};save()
        print("Starting "+name,flush=True);result,path=run(args,Limits(timeout_s=timeout));shutil.copytree(path,folder/name)
        report["runs"][name]={**result,"original_directory":str(path)};report["active_worker"]=None;save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f}s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError("Worker failed: "+name)
        return folder/name
    save()
    try:
        for case in names:
            report["cases"][case]={"final":None,"iterations":[]};save();previous=None
            for i in range(1 if case=="baseline-check" else 4):
                args=["claude.tools.stability_step","--case",case]
                if previous:args.extend(["--previous",str(previous)])
                previous=worker(f"{case}-{i}",args);report["cases"][case]["iterations"].append(previous.name)
                if json.loads((previous/"step.json").read_text())["status"]=="converged":
                    report["cases"][case]["final"]=previous.name;save();break
            if not report["cases"][case]["final"]:raise RuntimeError("Nonconvergence within case cap: "+case)
        evaluation=worker("evaluation",["claude.tools.evaluate_stability",str(folder)],120)
        findings=json.loads((evaluation/"evaluation.json").read_text())["comparisons"]
        report["gates"]={n:{k:v for k,v in result.items() if k.endswith("gate_pass")} for n,result in findings.items()}
        for group in ("source_sha256","report_sha256"):
            for name,digest in report[group].items():assert sha(ROOT/name)==digest,name
        report["status"]="stability_checks_pass_not_absolute_accuracy_acceptance" if all(all(v.values()) for v in report["gates"].values()) else "stability_gate_failed"
    except Exception as error:report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(r.get("elapsed_s",0) for r in values),peak_sampled_rss_mib=max((r.get("peak_sampled_rss_mib",0) for r in values),default=0),minimum_system_available_gib=min((r.get("minimum_system_available_gib",float("inf")) for r in values),default=None))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"};save()
    print("Archived: "+str(folder),flush=True)


if __name__=="__main__":main()
