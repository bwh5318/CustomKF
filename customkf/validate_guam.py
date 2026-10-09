"""Run directly: serial bounded GUAM PPP and same-three-hour orbit experiment.

Defaults unchanged: 2 GiB / one CPU / 8 GiB reserve; 120 s preparation/PPP,
300 s per orbit iteration, at most five iterations. Failures stop and preserve
checkpoints; no unguarded fallback and no increase of matrix or OS limits.
"""
from datetime import datetime,timezone
import json
import os
import shutil

from .guard import ROOT,Limits,run
from .prepare_stage2 import sha

BASE=ROOT/"claude/runs/20260911T022428Z-yell-continuation"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    folder=ROOT/"validation/guam"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");folder.mkdir(parents=True)
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py"),ROOT/"claude/tools/evaluate_ablation.py",ROOT/"claude/SCORING_RULE.md"]
    old=json.loads((BASE/"validation.json").read_text());changes={}
    for name,digest in old["source_sha256"].items():
        current=sha(ROOT/name)
        if current!=digest:
            if name not in ("customkf/run_stage3.py","customkf/stage5_pilot.py","customkf/stage5b_step.py"):
                raise ValueError("Unexpected scientific source change: "+name)
            changes[name]={"old":digest,"current":current}
    for name,digest in old["artifacts_sha256"].items():assert sha(BASE/name)==digest,name
    report={"status":"running","runs":{},"final":None,"source_changes_since_baseline":changes,
            "baseline_manifest_sha256":sha(BASE/"validation.json"),"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},
            "report_sha256":old["report_sha256"],"predeclared_case":"Original 13 stations including YELL plus GUAM, 2 August 12:00-15:00 GPST, 300 s cadence, identical model/weights/priors; frozen 10 m initial formal sigma split; no KOUR exclusions"}
    for p in sources:
        target=folder/"source"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    for label,path in (("download",ROOT/"runs/20260911T155746Z-70c38da2"),("YELL_verification",ROOT/"runs/20260911T155725Z-eb7c6763")):
        shutil.copytree(path,folder/label);report["runs"][label]=json.loads((path/"result.json").read_text())
    def save():
        temporary=folder/"validation.pending.json"
        temporary.write_text(json.dumps(report,indent=2)+"\n")
        temporary.replace(folder/"validation.json")
    def launch(name,args,timeout=120):
        report["active_worker"]={"name":name,"module_args":args,"started_utc":datetime.now(timezone.utc).isoformat()};save()
        print("Starting "+name,flush=True);result,path=run(args,Limits(timeout_s=timeout));shutil.copytree(path,folder/name)
        report["active_worker"]=None
        report["runs"][name]={**result,"original_directory":str(path)};save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f}s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError("Worker failed: "+name)
        return folder/name
    save()
    try:
        modules=["tests.test_"+n for n in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5","navigation_fit","reduced_network","stage5b_inputs","nonlinear_stop")]
        launch("tests",["unittest",*modules,"-v"])
        ppp=launch("GUAM_PPP",["customkf.run_stage3","--station","GUAM"])
        position=json.loads((ppp/"ppp.json").read_text());report["PPP_coordinate_gate"]=position["status"]
        if position["status"]!="development_position_gate_pass":raise ValueError("GUAM coordinate validation did not pass")
        launch("prepare",["customkf.stage5b_step","--case","guam-long"])
        launch("invariance",["customkf.evaluate_guam",str(folder),"--prepare-only"])
        previous=None
        for iteration in range(5):
            args=["customkf.stage5b_step","--case","guam-long","--fixture",str(folder/"prepare/fixture.json")]
            if previous:args.extend(["--previous",str(previous)])
            previous=launch(f"iteration-{iteration}",args,300)
            state=json.loads((previous/"step.json").read_text())
            if state["status"]=="converged":report["final"]=previous.name;save();break
        if not report["final"]:raise RuntimeError("Not converged within five bounded iterations")
        launch("evaluation",["customkf.evaluate_guam",str(folder)])
        for group in ("source_sha256","report_sha256"):
            for name,digest in report[group].items():assert sha(ROOT/name)==digest,name
        report["status"]="GUAM_experiment_complete_not_accuracy_acceptance"
    except Exception as error:report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(r.get("elapsed_s",0) for r in values),peak_sampled_rss_mib=max(r.get("peak_sampled_rss_mib",0) for r in values),minimum_system_available_gib=min(r.get("minimum_system_available_gib",float("inf")) for r in values))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"};save()
    print("Archived: "+str(folder),flush=True)


if __name__=="__main__":main()

