"""Direct serial guarded observation-information diagnostic controller."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
from customkf.guard import ROOT,Limits,run
from customkf.prepare_stage2 import sha

BASE=ROOT/"validation/guam/20260911T155927Z"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    parser=argparse.ArgumentParser();parser.add_argument("--prepared-run",type=Path,required=True)
    prepared=parser.parse_args().prepared_run
    p=json.loads((prepared/"profile.json").read_text());guard=json.loads((prepared/"result.json").read_text())
    assert guard["status"]=="ok" and p["status"]=="linear_profiles_complete_not_accuracy_acceptance"
    assert sha(ROOT/"claude/tools/observation_profile.py")==p["experiment"]["helper_sha256"]
    assert sha(prepared/"linear_profiles.npz")==p["archive_sha256"]
    base=json.loads((BASE/"validation.json").read_text())
    sources={**base["source_sha256"],**{f"claude/tools/{n}.py":sha(ROOT/f"claude/tools/{n}.py") for n in
             ("observation_profile","observation_profile_review","run_observation_profile","yell_continuation_review")}}
    for name,digest in sources.items():assert sha(ROOT/name)==digest,name
    folder=ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-observation-profile");folder.mkdir()
    shutil.copytree(prepared,folder/"prepare")
    for name in sources:
        target=folder/"source"/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    report={"status":"running","final":None,"source_sha256":sources,"report_sha256":base["report_sha256"],
            "runs":{"prepare":{**guard,"original_directory":str(prepared)}},"active_worker":None,
            "predeclared_protocol":"Reference-dependent G18/G03/G22 substitution, other 28 orbits fixed for primary test. Same rows/weights/clock datum/two-node wet model/priors. Re-estimate nuisance states only. Compare individual and joint linear profiles; other-orbits-free joint linear check with covariance identity; nonlinear joint nuisance fit <=3 iterations and linear cost agreement within 0.01. No probability calibration, outlier deletion or independent-POD output."}
    def save():
        pending=folder/"pending.json";pending.write_text(json.dumps(report,indent=2)+"\n");pending.replace(folder/"validation.json")
    def worker(name,args,timeout=300):
        report["active_worker"]={"name":name,"module_args":args,"started_utc":datetime.now(timezone.utc).isoformat()};save()
        print("Starting "+name,flush=True);result,path=run(args,Limits(timeout_s=timeout));shutil.copytree(path,folder/name)
        report["runs"][name]={**result,"original_directory":str(path)};report["active_worker"]=None;save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f}s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError("Failed: "+name)
        return folder/name
    save()
    try:
        previous=None
        for i in range(3):
            args=["claude.tools.observation_profile","iterate","--prepared",str(folder/"prepare")]
            if previous:args.extend(["--previous",str(previous)])
            previous=worker(f"iteration-{i}",args)
            if json.loads((previous/"profile.json").read_text())["status"]=="converged":
                report["final"]=previous.name;save();break
        if not report["final"]:raise RuntimeError("Nonconvergence within cap")
        worker("review",["claude.tools.observation_profile_review",str(folder)],120)
        for group in ("source_sha256","report_sha256"):
            for name,digest in report[group].items():assert sha(ROOT/name)==digest,name
        report["status"]="observation_profile_complete_reference_dependent_not_POD"
    except Exception as error:report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s",0) for v in values),peak_sampled_rss_mib=max(v.get("peak_sampled_rss_mib",0) for v in values),minimum_system_available_gib=min(v.get("minimum_system_available_gib",float("inf")) for v in values))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"};save()
    print("Archived: "+str(folder),flush=True)


if __name__=="__main__":main()
