"""Serial station PPP checks. Run directly; this controller launches the guards.

Existing Windows Python only, no downloads, unchanged 2 GiB / one CPU / 8 GiB
reserve. Each worker is capped at 120 s; failures stop the campaign. Coordinate
and residual-quality findings remain distinct from orbit accuracy acceptance.
"""
from datetime import datetime,timezone
import json
import os
import shutil

from .guard import ROOT,Limits,run
from .prepare_stage2 import sha

BASELINE=ROOT/"runs/20260911T014843Z-63402b03"


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    folder=ROOT/"validation/stage5b_stations"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py")]
    report_files=[ROOT/("GPS_POD_PROGRESS_REPORT"+suffix) for suffix in (".md",".pdf",".manifest.json")]
    manifests=[*(ROOT/"data/stage3").glob("*manifest.json"),ROOT/"data/stage2/manifest.json"]
    pinned={p.relative_to(ROOT).as_posix():sha(p) for p in manifests}
    for manifest in manifests:
        for entry in json.loads(manifest.read_text()).get("files",[]):
            if "path" in entry and "sha256" in entry:
                if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Input changed: "+entry["path"])
                pinned[entry["path"]]=entry["sha256"]
    report={"status":"running","source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},
            "input_sha256":pinned,"report_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in report_files},
            "runs":{},"coordinate_gates":{},"residual_quality_gate":"review_pending",
            "limits":"unchanged guard; each worker 120 seconds"}
    for p in sources:
        target=folder/"source"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    shutil.copytree(BASELINE,folder/"BRUX_before")
    report["runs"]["BRUX_before"]=json.loads((BASELINE/"result.json").read_text())
    if report["runs"]["BRUX_before"]["status"]!="ok":raise ValueError("Baseline failed")
    def save():(folder/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    def launch(name,args):
        print("Starting "+name,flush=True)
        result,path=run(args,Limits(timeout_s=120));shutil.copytree(path,folder/name)
        report["runs"][name]={**result,"original_directory":str(path)};save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.2f} s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError("Worker failed: "+name)
        return folder/name
    save()
    try:
        launch("tests",["unittest","tests.test_stage3","tests.test_stage3_models","tests.test_stage5b_inputs","-v"])
        launch("BRUX",["customkf.run_stage3","--station","BRUX"])
        launch("regression",["customkf.audit_stage5b_stations",str(folder),"--regression-only"])
        for station in ("DAV1","FALK","FAA1","GLPS"):
            path=launch(station,["customkf.run_stage3","--station",station])
            report["coordinate_gates"][station]=json.loads((path/"ppp.json").read_text())["status"];save()
        launch("diagnostics",["customkf.audit_stage5b_stations",str(folder)])
        for group in ("source_sha256","input_sha256","report_sha256"):
            for path,digest in report[group].items():
                if sha(ROOT/path)!=digest:raise ValueError("Changed during campaign: "+path)
        report["status"]="numerical_station_checks_complete_residual_review_pending"
    except Exception as error:
        report.update(status="failed",error=str(error));raise
    finally:
        values=list(report["runs"].values())
        report.update(total_guarded_seconds=sum(r.get("elapsed_s",0) for r in values),
                      peak_sampled_rss_mib=max(r.get("peak_sampled_rss_mib",0) for r in values),
                      minimum_system_available_gib=min(r.get("minimum_system_available_gib",float("inf")) for r in values))
        report["artifacts_sha256"]={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="validation.json"}
        save()
    print("Archived: "+str(folder),flush=True)


if __name__=="__main__":main()
