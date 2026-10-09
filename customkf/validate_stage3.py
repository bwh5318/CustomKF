"""Serial, guarded Stage 3 validation; physical residual review remains explicit."""
from datetime import datetime,timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import sys
from .guard import ROOT,Limits,run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest the resource guard")
    target=ROOT/"validation/stage3"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True,exist_ok=False)
    manifests=[ROOT/"data/stage3"/name for name in ("manifest.json","rinex3_manifest.json","support_manifest.json")]
    files=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py"),*manifests,
           ROOT/"COMPARISON_CONTRACT.md",ROOT/"THIRD_PARTY_NOTICES.md"]
    report={"status":"running","stage3_gate":"not_evaluated","python":sys.version,"executable":sys.executable,
        "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)},
        "dependencies":{n:importlib.metadata.version(n) for n in ("numpy","scipy","pyerfa","numba","psutil","threadpoolctl","matplotlib")},
        "runs":{},"input_manifests":{p.name:json.loads(p.read_text()) for p in manifests}}
    def save():(target/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    def launch(name,args,timeout=180):
        print(f"Starting {name}",flush=True)
        result,folder=run(args,Limits(timeout_s=timeout));shutil.copytree(folder,target/name)
        report["runs"][name]={**result,"run_directory":str(folder)};save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.2f} s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError(f"{name} failed: {folder}")
        return target/name
    save()
    try:
        for manifest in report["input_manifests"].values():
            for entry in manifest["files"]:
                if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Pinned input changed")
        decoder=report["input_manifests"]["rinex3_manifest.json"]["decoder"]
        if sha(ROOT/"vendor/rnxcmp-4.2.0/CRX2RNX.exe")!=decoder["exe_sha256"]:raise ValueError("Decoder changed")
        modules=["tests.test_"+name for name in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models")]
        launch("unit_tests",["unittest",*modules,"-v"],120)
        launch("ingestion_audit",["customkf.audit_stage3_inputs"],120)
        folders=[];results={}
        for station in ("BRUX","KOUR","HOB2"):
            folder=launch(station,["customkf.run_stage3","--station",station])
            folders.append(folder);results[station]=json.loads((folder/"ppp.json").read_text())
        stress=launch("BRUX_perturbed",["customkf.run_stage3","--station","BRUX","--initial-offset","100","-70","40"])
        stress=json.loads((stress/"ppp.json").read_text())
        difference=math.sqrt(sum((a-b)**2 for a,b in zip(stress["estimated_xyz_m"],results["BRUX"]["estimated_xyz_m"])))
        report["starting_position_stress_difference_m"]=difference
        if difference>1e-4 or not stress["converged"]:raise RuntimeError("Starting-position stress test failed")
        padding=launch("BRUX_next_day_diagnostic",["customkf.run_stage3","--station","BRUX","--allow-next-day-products"])
        padding=json.loads((padding/"ppp.json").read_text())
        report["next_day_padding_coordinate_difference_m"]=math.sqrt(sum((a-b)**2 for a,b in zip(padding["estimated_xyz_m"],results["BRUX"]["estimated_xyz_m"])))
        launch("diagnostics",["customkf.diagnose_stage3",*[str(p) for p in folders]],120)
        report["position_gates"]={s:r["status"] for s,r in results.items()}
        if any(r["status"]!="development_position_gate_pass" for r in results.values()):raise RuntimeError("Position development gate failed")
        if any(sha(ROOT/p)!=digest for p,digest in report["source_sha256"].items()):raise RuntimeError("Source changed during validation")
        report.update(status="numerical_checks_and_position_gates_pass",stage3_gate="residual_review_pending",
            interpretation="Single development day, three receivers from one manufacturer. Coordinate thresholds and numerical checks do not certify the full observation model or rapid latency.")
    except Exception as error:
        report.update(status="fail",error=str(error));raise
    finally:save()
    print(f"Stage 3 archived: {target}",flush=True)


if __name__=="__main__":main()
