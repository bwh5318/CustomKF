"""Serial guarded three-case campaign; direct controller, never nest in guard."""
from datetime import datetime,timezone
import json
import os
import shutil
from .guard import ROOT,Limits,run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    folder=ROOT/"validation/stage5b"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");folder.mkdir(parents=True)
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py")]
    report={"status":"running","runs":{},"final_steps":{},"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},"report_sha256":{p.name:sha(p) for p in ROOT.glob("GPS_POD_PROGRESS_REPORT.*")}}
    for p in sources:
        target=folder/"source"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    def save():(folder/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    def worker(name,args):
        print("Starting "+name,flush=True)
        result,path=run(args,Limits(timeout_s=300))
        shutil.copytree(path,folder/name);report["runs"][name]={**result,"original_directory":str(path)};save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f} seconds",flush=True)
        if result["status"]!="ok":raise RuntimeError("Guarded worker did not complete: "+name)
        return folder/name
    save()
    try:
        modules=["tests.test_"+n for n in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5","navigation_fit","reduced_network","stage5b_inputs","nonlinear_stop")]
        worker("tests",["unittest",*modules,"-v"])
        worker("legacy_regression",["customkf.stage5_geometry_noise","--case","baseline"])
        for case in ("eight-short","eight-long","expanded-long"):
            prepared=worker(case+"-prepare",["customkf.stage5b_step","--case",case]);previous=None
            for iteration in range(5):
                command=["customkf.stage5b_step","--case",case,"--fixture",str(prepared/"fixture.json")]
                if previous:command += ["--previous",str(previous)]
                name=f"{case}-iteration-{iteration}";previous=worker(name,command)
                step=json.loads((previous/"step.json").read_text())
                if step["status"]=="converged":report["final_steps"][case]=name;save();break
            else:raise RuntimeError("Case did not converge in five bounded iterations: "+case)
        worker("evaluation",["customkf.evaluate_stage5b",str(folder)])
        for name,digest in report["source_sha256"].items():
            if sha(ROOT/name)!=digest:raise RuntimeError("Source changed during campaign")
        for name,digest in report["report_sha256"].items():
            if sha(ROOT/name)!=digest:raise RuntimeError("PDF/report unexpectedly changed")
        report["status"]="completed_station_and_arc_diagnostics_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(r.get("elapsed_s",0) for r in values),peak_sampled_rss_mib=max((r.get("peak_sampled_rss_mib",0) for r in values),default=0),minimum_system_available_gib=min((r.get("minimum_system_available_gib",float("inf")) for r in values),default=None))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"}
        save()
    print("Campaign archived: "+str(folder),flush=True)


if __name__=="__main__":main()
