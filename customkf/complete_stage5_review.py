"""Finish evaluation of an archived Stage 5a campaign without repeating fits.

The original campaign correctly failed its weak-prior convergence assertion.
Preserve that status. Verify unchanged numerical sources, run strengthened
unit checks and a corrected post-fit evaluator, then report gates separately.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil
from .guard import ROOT, Limits, run
from .prepare_stage2 import sha


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Do not nest guards")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    archive=(ROOT/parser.parse_args().archive).resolve()
    archive.relative_to(ROOT/"validation/stage5")
    original=json.loads((archive/"validation.json").read_text())
    allowed={"customkf/evaluate_stage5.py","customkf/validate_stage5.py","tests/test_stage5.py"}
    for path,digest in original["source_sha256"].items():
        if path not in allowed and sha(ROOT/path)!=digest:
            raise RuntimeError("Numerical/input source changed: "+path)
    cases={name:json.loads((archive/name/"pilot.json").read_text()) for name in ("real","perturbed","synthetic","weak-prior")}
    if not all(cases[name]["converged"] for name in ("real","perturbed","synthetic")):
        raise AssertionError("Primary nonlinear checks did not pass")
    recovery=cases["synthetic"]["synthetic_recovery"]
    if recovery["max_orbit_position_error_m"]>=.001 or recovery["max_observation_error_m"]>=1e-6:
        raise AssertionError("Synthetic closure did not pass")
    destination=archive/("review-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    destination.mkdir(exist_ok=False)
    sources=[*(ROOT/"customkf").glob("*.py"),*(ROOT/"tests").glob("*.py")]
    report={"status":"running","original_campaign_status":original["status"],
        "original_validation_sha256":sha(archive/"validation.json"),
        "reason":"Separate primary integration checks from failed weak-prior stress; evaluator omits unconverted broadcast APC comparison; strengthen absolute broadcast and clock-chain-rule unit checks",
        "unchanged_numerical_sources_verified":True,"allowed_review_changes":sorted(allowed),
        "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in sources},"runs":{}}
    def save():(destination/"review.json").write_text(json.dumps(report,indent=2)+"\n")
    save()
    try:
        modules=["tests.test_"+name for name in ("comparison","sp3","dynamics","propagation","stage2","stage3","stage3_models","stage4","stage5")]
        for name,args in (("unit_tests",["unittest",*modules,"-v"]),("evaluation",["customkf.evaluate_stage5",str(archive)])):
            result,folder=run(args,Limits(timeout_s=120))
            shutil.copytree(folder,destination/name)
            report["runs"][name]={**result,"run_directory":str(folder)}
            save()
            if result["status"]!="ok":raise RuntimeError("Review worker failed: "+str(folder))
        for path,digest in report["source_sha256"].items():
            if sha(ROOT/path)!=digest:raise RuntimeError("Source changed during review")
            target=destination/"source"/path
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/path,target)
        all_runs=[*original["runs"].values(),*report["runs"].values()]
        report.update(status="passed_stage5a_integration_with_open_prior_stress",
            integration_gate="passed",prior_stress_convergence_gate="passed" if cases["weak-prior"]["converged"] else "open",
            full_stage5_accuracy_gate="not passed",rapid_vintage_gate="not certified",
            total_guarded_seconds=sum(r["elapsed_s"] for r in all_runs),
            peak_sampled_rss_mib=max(r["peak_sampled_rss_mib"] for r in all_runs),
            peak_private_commit_mib=max(r["windows_peak_job_memory_mib"] for r in all_runs),
            minimum_system_available_gib=min(r["minimum_system_available_gib"] for r in all_runs))
    except Exception as error:
        report.update(status="failed",error=str(error))
        raise
    finally:save()
    print("Stage 5a review archived: "+str(destination),flush=True)


if __name__=="__main__":main()
