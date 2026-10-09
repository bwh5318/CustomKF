"""Serial Stage 2 controller: every numerical worker has the native resource guard."""
from datetime import datetime, timezone
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from .guard import ROOT, Limits, run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Launch this controller without an outer guard")
    target=ROOT/"validation/stage2"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True,exist_ok=False)
    files=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py"),ROOT/"COMPARISON_CONTRACT.md",
           ROOT/"data/stage0/manifest.json",ROOT/"data/stage2/manifest.json",ROOT/"data/stage2/check_vectors.json"]
    report={"status":"running","python":sys.version,"executable":sys.executable,"platform":platform.platform(),
            "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)},
            "dependencies":{n:importlib.metadata.version(n) for n in ("numpy","scipy","pyerfa","numba","psutil","threadpoolctl")},
            "runs":{}}
    def save():
        (target/"validation.json").write_text(json.dumps(report,indent=2)+"\n")
    def launch(name,args,timeout=180):
        print(f"Starting {name}",flush=True)
        result,folder=run(args,Limits(timeout_s=timeout))
        report["runs"][name]={**result,"run_directory":str(folder)}
        shutil.copytree(folder,target/name)
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s',0):.1f} s, {result.get('peak_sampled_rss_mib',0):.1f} MiB RSS",flush=True)
        if result["status"]!="ok":raise RuntimeError(f"{name} failed; inspect {folder}")
        return folder
    save()
    try:
        launch("unit_tests",["unittest","tests.test_comparison","tests.test_sp3","tests.test_dynamics","tests.test_propagation","tests.test_stage2","-v"],120)
        fits={}
        for sat in ("G08","G01"):
            for count in (5,7):
                name=f"{sat}_ECOM{count}"
                fits[name]=launch(name,["customkf.run_stage2","--sat",sat,"--ecom",str(count)])
        launch("G08_no_tides",["customkf.run_stage2","--sat","G08","--no-tides"])
        launch("real_force_partials",["customkf.audit_stage2",str(fits["G08_ECOM5"]),str(fits["G01_ECOM5"])],300)
        launch("stage1_regression",["customkf.audit_stage1"],300)
        if any(sha(ROOT/p)!=digest for p,digest in report["source_sha256"].items()):
            raise RuntimeError("Source changed during validation")
        report["fit_gates"]={n:json.loads((p/"fit.json").read_text())["status"] for n,p in fits.items()}
        report["status"]="pass" if all(v=="pass" for v in report["fit_gates"].values()) else "gate_not_met"
    except Exception as error:
        report.update(status="fail",error=str(error))
        raise
    finally:save()
    print(f"Stage 2 {report['status']}: {target}",flush=True)
    return 0 if report["status"]=="pass" else 1


if __name__=="__main__":sys.exit(main())
