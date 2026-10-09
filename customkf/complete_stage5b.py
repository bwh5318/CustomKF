"""Preserve the failed campaign and finish after an audited stopping-rule fix.

Run directly. Reuse pinned unchanged fixtures, run tests and the corrected final
step under serial guards, then evaluate against IGS outside the estimator.
"""
from datetime import datetime,timezone
import json
import os
import shutil
from .guard import ROOT,Limits,run
from .prepare_stage2 import sha

BASE=ROOT/"validation/stage5b/20260910T203254Z"
AUDIT=ROOT/"runs/20260910T205232Z-1c3b9e5a"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    old=json.loads((BASE/"validation.json").read_text())
    allowed={"customkf/stage5b_step.py":"Add audited stationary-stop branch; observations, force model, weighting and QR unchanged",
        "customkf/prepare_stage4.py":"Correct acquisition manifest purpose text",
        "customkf/prepare_stage5b.py":"Set default downloads to the final four selected stations",
        "customkf/validate_stage5b.py":"Include new stopping-rule tests"}
    changes={}
    for path,digest in old["source_sha256"].items():
        if sha(ROOT/path)!=digest:
            if path not in allowed:raise ValueError("Unexpected source change: "+path)
            changes[path]={"old":digest,"new":sha(ROOT/path),"reason":allowed[path]}
    for path,digest in old["artifacts_sha256"].items():
        if sha(BASE/path)!=digest:raise ValueError("Earlier artifact changed: "+path)
    if json.loads((AUDIT/"result.json").read_text())["status"]!="ok":raise ValueError("Stationarity audit failed")
    folder=BASE/("completion-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"));folder.mkdir()
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py")]
    report={"status":"running","runs":{},"final_steps":{},"original_campaign_status":old["status"],"original_campaign_sha256":sha(BASE/"validation.json"),"source_changes":changes,"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},"report_sha256":old["report_sha256"]}
    def save():(folder/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    for p in sources:
        target=folder/"source"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    shutil.copytree(AUDIT,folder/"stationarity_audit")
    report["runs"]["stationarity_audit"]=json.loads((AUDIT/"result.json").read_text())
    for case in ("eight-short","eight-long","expanded-long"):
        shutil.copytree(BASE/(case+"-prepare"),folder/(case+"-prepare"))
        if case!="expanded-long":
            name=old["final_steps"][case];shutil.copytree(BASE/name,folder/name);report["final_steps"][case]=name
    # Migration changes provenance only. Fixture and initial states remain byte-
    # identical. Scientific model files were checked above against the archive.
    prep=folder/"expanded-long-prepare/step.json";metadata=json.loads(prep.read_text())
    metadata["source_migration"]={"original_step_sha256":sha(BASE/"expanded-long-prepare/step.json"),"allowed_changes":changes}
    metadata["source_sha256"]={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}
    prep.write_text(json.dumps(metadata,indent=2)+"\n")
    save()
    def worker(name,args):
        print("Starting "+name,flush=True);result,path=run(args,Limits(timeout_s=300))
        shutil.copytree(path,folder/name);report["runs"][name]={**result,"original_directory":str(path)};save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f}s",flush=True)
        if result["status"]!="ok":raise RuntimeError("Worker failed: "+name)
        return folder/name
    try:
        modules=["tests.test_"+n for n in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5","navigation_fit","reduced_network","stage5b_inputs","nonlinear_stop")]
        worker("tests",["unittest",*modules,"-v"])
        last=worker("expanded-long-final",["customkf.stage5b_step","--case","expanded-long","--fixture",str(folder/"expanded-long-prepare/fixture.json"),"--previous",str(BASE/"expanded-long-iteration-1")])
        stop=json.loads((last/"step.json").read_text())
        if stop["status"]!="converged" or stop["history"][-1]["termination"]!="small_step_and_linearized_progress":raise ValueError("Stationarity confirmation did not pass")
        report["final_steps"]["expanded-long"]="expanded-long-final";save()
        worker("evaluation",["customkf.evaluate_stage5b",str(folder)])
        for path,digest in report["source_sha256"].items():
            if sha(ROOT/path)!=digest:raise ValueError("Source changed during completion")
        for path,digest in report["report_sha256"].items():
            if sha(ROOT/path)!=digest:raise ValueError("Report changed")
        report["status"]="completed_after_stationarity_review_not_accuracy_acceptance"
    except Exception as error:report.update(status="failed",error=str(error));raise
    finally:
        values=list(old["runs"].values())+list(report["runs"].values())
        report.update(total_guarded_seconds=sum(r.get("elapsed_s",0) for r in values),peak_sampled_rss_mib=max(r.get("peak_sampled_rss_mib",0) for r in values),minimum_system_available_gib=min(r.get("minimum_system_available_gib",float("inf")) for r in values))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"};save()
    print("Completion archived: "+str(folder),flush=True)


if __name__=="__main__":main()
