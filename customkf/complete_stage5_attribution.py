"""Archive attribution follow-ups with serial guarded tests and evaluation.

Launch directly, never inside a guard. Preserve failed earlier attempts. The
result is a diagnostic completion, not an orbit-accuracy or rapid-product pass.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from .guard import ROOT, Limits, run
from .prepare_stage2 import sha

BASE=ROOT/"validation/stage5/20260909-attribution/20260910T011512Z"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-run",type=Path,required=True)
    args=parser.parse_args()
    folder=BASE/("completion-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir()
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py")]
    report={"status":"running","source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},"runs":{}}
    def save():(folder/"completion.json").write_text(json.dumps(report,indent=2)+"\n")
    for p in sources:
        target=folder/"source"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    report["earlier_evidence_sha256"]={p.relative_to(ROOT).as_posix():sha(p) for p in BASE.rglob("*") if p.is_file() and not p.is_relative_to(folder)}
    report["earlier_status_preserved"]=json.loads((BASE/"validation.json").read_text())["status"]
    report_files=[ROOT/f"GPS_POD_PROGRESS_REPORT{suffix}" for suffix in (".md",".pdf",".manifest.json")]
    report["unchanged_report_sha256"]={p.name:sha(p) for p in report_files}
    save()
    try:
        for name,original in (("seed_audit",ROOT/"runs/20260910T012033Z-4c9dd769"),
                              ("navigation_gap_inventory",ROOT/"runs/20260910T012757Z-13297563"),
                              ("failed_full_clock_correction",ROOT/"runs/20260910T012650Z-caa08628"),
                              ("corrected_seed_fit",args.fit_run.resolve())):
            result=json.loads((original/"result.json").read_text())
            shutil.copytree(original,folder/name)
            report["runs"][name]={**result,"original_directory":str(original)}
            if name!="failed_full_clock_correction" and result["status"]!="ok":raise RuntimeError("Unsuccessful required worker: "+name)
        modules=["tests.test_"+n for n in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5","navigation_fit")]
        for name,command in (("unit_tests",["unittest",*modules,"-v"]),
                             ("evaluation",["customkf.evaluate_stage5_attribution","--fit-run",str(folder/"corrected_seed_fit")])):
            print("Starting "+name,flush=True)
            result,path=run(command,Limits(timeout_s=180))
            shutil.copytree(path,folder/name)
            report["runs"][name]={**result,"original_directory":str(path)};save()
            if result["status"]!="ok":raise RuntimeError("Worker failed: "+str(path))
        for path,digest in report["source_sha256"].items():
            if sha(ROOT/path)!=digest:raise RuntimeError("Source changed during completion")
        for p in report_files:
            if sha(p)!=report["unchanged_report_sha256"][p.name]:raise RuntimeError("Report unexpectedly changed")
        evaluation=json.loads((folder/"evaluation/evaluation.json").read_text())
        report["results"]={"aggregate":evaluation["aggregate"],"corrected_fit_residual_rms_m":evaluation["corrected_fit_residual_rms_m"]}
        report["open_gates"]=["Independent orbit accuracy", "Rapid-vintage input availability", "Complete navigation applicability policy", "Weak-prior robustness", "Geographically broader continuous-arc experiment"]
        report["status"]="completed_attribution_diagnostics_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed",error=str(error));raise
    finally:
        previous=json.loads((BASE/"validation.json").read_text())["runs"]
        # Count a worker once even where its artifacts were copied or superseded.
        resources=list(previous.values())+list(report["runs"].values())
        report.update(total_guarded_seconds=sum(r.get("elapsed_s",0) for r in resources),
            peak_sampled_rss_mib=max(r.get("peak_sampled_rss_mib",0) for r in resources),
            minimum_system_available_gib=min(r.get("minimum_system_available_gib",float("inf")) for r in resources),
            resource_scope="Retained main campaign plus completion workers, including failed seed/clock attempts; excludes exploratory earlier campaign and focused-test runs")
        report["artifact_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="completion.json"}
        save()
    print("Attribution completion: "+str(folder),flush=True)


if __name__=="__main__":main()
