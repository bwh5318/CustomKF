"""Validate the Stage 3 ingestion/geometry foundation, not the full PPP gate."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
import os
from .guard import ROOT,Limits,run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest the resource guard")
    target=ROOT/"validation/stage3"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True,exist_ok=False)
    paths=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py"),ROOT/"data/stage3/manifest.json"]
    report={"status":"running","stage3_ppp_gate":"not_run","python":sys.version,"executable":sys.executable,
            "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in paths},"runs":{}}
    def save():(target/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    save()
    try:
        for name,args in (("tests",["unittest","tests.test_stage3","-v"]),
                          ("inputs",["customkf.audit_stage3_inputs"]),
                          ("code_diagnostic",["customkf.code_position_stage3"])):
            result,folder=run(args,Limits(timeout_s=120))
            shutil.copytree(folder,target/name)
            report["runs"][name]={**result,"run_directory":str(folder)};save()
            print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.2f} s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
            if result["status"]!="ok":raise RuntimeError(f"Foundation check failed: {folder}")
        if any(sha(ROOT/p)!=digest for p,digest in report["source_sha256"].items()):raise RuntimeError("Source changed during validation")
        report["status"]="foundation_pass"
    except Exception as error:
        report.update(status="fail",error=str(error));raise
    finally:save()
    print(f"Foundation validated: {target}; full Stage 3 PPP gate has not run.",flush=True)


if __name__=="__main__":main()
