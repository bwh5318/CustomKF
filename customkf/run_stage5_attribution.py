"""Serial bounded controller for attribution experiments; does not rebuild PDF."""
from datetime import datetime, timezone
import json
import os
import shutil
from .guard import ROOT, Limits, run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    folder=ROOT/"validation/stage5/20260909-attribution"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py")]
    report={"status":"running","source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},"runs":{}}
    for p in sources:
        target=folder/"source"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    def save():(folder/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    for name,path in (("initial_diagnosis","20260909T204417Z-9880aa32"),("nonlinear_noise","20260909T204525Z-72059965")):
        original=ROOT/"runs"/path
        shutil.copytree(original,folder/name)
        report["runs"][name]=json.loads((original/"result.json").read_text())
    save()
    try:
        modules=["tests.test_"+name for name in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5")]
        jobs=[("unit_tests",["unittest",*modules,"-v"])]
        jobs += [(case,["customkf.stage5_geometry_noise","--case",case]) for case in ("baseline","without-koug","without-djig","longer")]
        jobs += [("seed_audit",["customkf.audit_stage5_seed"])]
        for name,args in jobs:
            print("Starting "+name,flush=True)
            result,path=run(args,Limits(timeout_s=180))
            shutil.copytree(path,folder/name)
            report["runs"][name]={**result,"run_directory":str(path)};save()
            print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.2f}s",flush=True)
            if result["status"]!="ok":raise RuntimeError("Worker failed: "+str(path))
        for path,digest in report["source_sha256"].items():
            if sha(ROOT/path)!=digest:raise RuntimeError("Source changed during campaign")
        report["status"]="completed_attribution_diagnostics_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed",error=str(error));raise
    finally:
        report.update(total_guarded_seconds=sum(r["elapsed_s"] for r in report["runs"].values()),
            peak_sampled_rss_mib=max(r["peak_sampled_rss_mib"] for r in report["runs"].values()),
            minimum_system_available_gib=min(r["minimum_system_available_gib"] for r in report["runs"].values()))
        save()
    print("Attribution archived: "+str(folder),flush=True)


if __name__=="__main__":main()
