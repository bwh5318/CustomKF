"""Serial guarded validation of Stage 5a, not full daily-constellation POD.

Run with the existing Windows Python directly; each numerical worker is guarded.
The external evaluator runs only after estimation has finished. No downloads.
"""
from datetime import datetime, timezone
import importlib.metadata
import json
import os
import shutil
import sys
from .guard import ROOT, Limits, run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    destination=ROOT/"validation/stage5"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True,exist_ok=False)
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py"),
             *(ROOT/"data/stage3").glob("*manifest.json"),ROOT/"data/stage2/manifest.json"]
    report={"status":"running","python":sys.version,"executable":sys.executable,
        "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(sources)},
        "dependencies":{name:importlib.metadata.version(name) for name in ("numpy","scipy","numba","pyerfa","psutil","threadpoolctl")},"runs":{}}
    def save():(destination/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    def launch(name,args,timeout=300):
        print("Starting "+name,flush=True)
        result,folder=run(args,Limits(timeout_s=timeout))
        shutil.copytree(folder,destination/name)
        report["runs"][name]={**result,"run_directory":str(folder)}
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.2f}s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError("Guarded worker failed: "+str(folder))
    # Capture source before running so a failed campaign remains reproducible.
    for path in sources:
        target=destination/"source"/path.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
    save()
    try:
        modules=["tests.test_"+name for name in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5")]
        launch("unit_tests",["unittest",*modules,"-v"],120)
        launch("derivatives",["customkf.audit_stage5"],120)
        for mode in ("real","perturbed","synthetic","weak-prior"):
            launch(mode,["customkf.stage5_pilot","--mode",mode])
            result=json.loads((destination/mode/"pilot.json").read_text())
            if mode=="weak-prior":
                report["prior_stress_convergence_gate"]="passed" if result["converged"] else "open"
            elif not result["converged"]:
                raise AssertionError(mode+" nonlinear gate open")
            if mode=="synthetic":
                recovery=result["synthetic_recovery"]
                if recovery["max_orbit_position_error_m"]>=.001 or recovery["max_observation_error_m"]>=1e-6:
                    raise AssertionError("Synthetic recovery gate open")
        launch("evaluation",["customkf.evaluate_stage5",str(destination)],120)
        for path,digest in report["source_sha256"].items():
            if sha(ROOT/path)!=digest:raise RuntimeError("Source changed during validation")
        report.update(status="passed_stage5a_integration_with_open_scientific_gates",
            scientific_scope="Short-arc dynamic observation closure, synthetic recovery and start consistency only. Prior independence, daily POD accuracy and rapid-vintage gates remain open.")
    except Exception as error:
        report.update(status="failed",error=str(error))
        raise
    finally:
        if report["runs"]:
            report.update(total_guarded_seconds=sum(r["elapsed_s"] for r in report["runs"].values()),
                peak_sampled_rss_mib=max(r["peak_sampled_rss_mib"] for r in report["runs"].values()),
                peak_private_commit_mib=max(r["windows_peak_job_memory_mib"] for r in report["runs"].values()),
                minimum_system_available_gib=min(r["minimum_system_available_gib"] for r in report["runs"].values()))
        save()
    print("Stage 5a archived: "+str(destination),flush=True)


if __name__=="__main__":main()
