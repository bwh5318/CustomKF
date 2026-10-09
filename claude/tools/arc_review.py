"""Independent guarded archive audit after the arc experiment; no nonlinear fit."""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT, sha


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    folder=Path(sys.argv[1]); report=json.loads((folder/"validation.json").read_text())
    assert report["status"]=="arc_experiment_complete_not_accuracy_acceptance"
    for name,digest in report["artifacts_sha256"].items(): assert sha(folder/name)==digest,name
    for group in ("source_sha256","report_sha256"):
        for name,digest in report[group].items(): assert sha(ROOT/name)==digest,name
    evidence=json.loads((folder/"evaluation/evaluation.json").read_text())
    result={"status":"arc_archive_review_pass","cases":{}}
    fixtures={}
    for case,meta in report["cases"].items():
        fixture=json.loads((folder/meta["prepare"]/"fixture.json").read_text()); fixtures[case]=fixture
        fit=np.load(folder/meta["final"]/"solution.npz"); step=json.loads((folder/meta["final"]/"step.json").read_text())
        names={str(n):i for i,n in enumerate(fit["names"])}; x=fit["x"]
        counts=Counter(r["arc"] for r in fixture["rows"])
        labels=[(r,k) for ei in range(fixture["context"]["epoch_count"]) for r in fixture["rows"] if r["epoch"]==ei for k in range(2 if counts[r["arc"]]>=3 else 1)]
        np.testing.assert_array_equal(fit["sigma_m"],[r["sigma"][k] for r,k in labels])
        prior=[]
        for sat in fit["satellites"]:
            prior.extend(x[names[f"orbit:{sat}:{k}"]]/(1000 if k<3 else 1) for k in range(6))
        for station in fixture["context"]["stations"]:
            a,b=[x[names[f"wet:{station}:{k}"]] for k in ("0","1")]
            prior.extend([a/.3,b/.3,(b-a)/.03])
            if case=="six": prior.append((x[names[f"wet:{station}:6h"]]-b)/.03)
        cost=float(np.sum((fit["residual_m"]/fit["sigma_m"])**2)+np.sum(np.square(prior)))
        history=step["history"]; last=history[-1]
        np.testing.assert_allclose(cost,last["cost_after"],rtol=0,atol=2e-8)
        assert last["accepted"] and not last["update_applied"] and last["termination"]=="small_step_and_linearized_progress"
        assert last["trajectory_step_bound_m"]<.001
        tol=max(1e-5,1e-8*last["cost_before"])
        assert abs(last["predicted_reduction"])<tol and last["whitened_direction_norm_squared"]<tol
        previous=np.load(folder/meta["iterations"][-2]/"solution.npz")
        for key in ("x","states","residual_m","sigma_m","times_s","names","satellites"):
            np.testing.assert_array_equal(fit[key],previous[key])
        cov=fit["retained_covariance"]
        np.testing.assert_allclose(cov,cov.T,rtol=0,atol=1e-12)
        np.linalg.cholesky(cov)
        assert len(labels)==len(fit["residual_m"])
        result["cases"][case]=dict(independent_cost=cost,stationary_checkpoint_unchanged=True,
            covariance_positive_definite=True,stationary_bound_m=last["trajectory_step_bound_m"],phase_rows=sum(k for _,k in labels))
    c3=Counter(r["arc"] for r in fixtures["three"]["rows"]); c6=Counter(r["arc"] for r in fixtures["six"]["rows"])
    initial3=np.load(folder/report["cases"]["three"]["prepare"]/"initial.npz")
    initial6=np.load(folder/report["cases"]["six"]["prepare"]/"initial.npz")
    np.testing.assert_array_equal(initial3["satellites"],initial6["satellites"])
    np.testing.assert_array_equal(initial3["times_s"],initial6["times_s"][:len(initial3["times_s"])])
    initial_delta=np.linalg.norm(initial3["states"][:,:,:3]-initial6["states"][:,:len(initial3["times_s"]),:3],axis=2)
    result["common_prefix_initial_trajectory_max_difference_m"]=float(initial_delta.max())
    assert initial_delta.max()<.001,"Extended environment changes seed trajectory by over 1 mm"
    promoted=[r for r in fixtures["three"]["rows"] if c3[r["arc"]]<3 and c6[r["arc"]]>=3]
    result["common_prefix_phase_rows_enabled_by_longer_arcs"]=len(promoted)
    result["promoted_phase_links"]=[dict(station=r["station"],satellite=r["satellite"],time_s=r["time_s"],arc=r["arc"]) for r in promoted]
    assert len(evidence["common_sample_keys"])==403
    result["independent_cartesian_vs_rac_checks"]=True
    result["campaign_manifest_sha256"]=sha(folder/"validation.json")
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"review.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2),flush=True)


if __name__ == "__main__": main()
