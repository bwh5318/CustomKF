"""Separate guarded reference scoring and checkpoint audit for station-only D0."""
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import ORIGIN
from claude.tools.d0_step import BASE
from claude.tools.evaluate_ablation import Reference,score,pooled,strip
from claude.tools.yell_continuation_review import residual_structure


class CommonReference:
    def __init__(self,base):self.base=base
    def rac(self,sat,t,xyz):return None if t>10810 else self.base.rac(sat,t,xyz)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    folder=Path(sys.argv[1]);manifest=json.loads((folder/"validation.json").read_text());final=folder/manifest["final"]
    step=json.loads((final/"step.json").read_text());assert step["status"]=="converged"
    assert sha(final/"solution.npz")==step["solution_sha256"]
    fit=np.load(final/"solution.npz");fixture=folder/"prepare/fixture.json";initial=folder/"prepare/initial.npz"
    reference=Reference();before={};after={};comparisons={}
    for domain,ref in (("full",reference),("common",CommonReference(reference))):
        before[domain]=score(ref,BASE/"six-1",BASE/"six-prepare/fixture.json",BASE/"six-prepare/initial.npz")
        after[domain]=score(ref,final,fixture,initial)
        a,b=before[domain],after[domain]
        both=[s for s in a["per_satellite"] if a["per_satellite"][s]["class"]==b["per_satellite"][s]["class"]=="determined"]
        per={s:dict(before_m=p["fit"]["rms_3d_m"],after_m=b["per_satellite"][s]["fit"]["rms_3d_m"],
            change_m=b["per_satellite"][s]["fit"]["rms_3d_m"]-p["fit"]["rms_3d_m"]) for s,p in a["per_satellite"].items()}
        ar=a["groups"]["all"]["fit"]["rms_3d_m"];br=b["groups"]["all"]["fit"]["rms_3d_m"]
        comparisons[domain]=dict(before_rms_m=ar,after_rms_m=br,reduction_percent=100*(1-br/ar),
            five_percent_improvement=br<=.95*ar,regressions_over_10_cm=[s for s,p in per.items() if p["change_m"]>.1],
            per_satellite=per,determined_in_both=dict(before=pooled(a,both),after=pooled(b,both)))
        squares=[]
        for si,sat in enumerate(map(str,fit["satellites"])):
            for ti,t in enumerate(map(float,fit["times_s"])):
                if domain=="common" and t>10810:continue
                sample=reference.raw.samples.get((ORIGIN+int(round(t*1e9)),sat))
                if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:continue
                d=reference.epoch.celestial_to_terrestrial(t)@fit["states"][si,ti,:3]-sample.xyz_m;squares.append(float(d@d))
        assert len(squares)==(403 if domain=="common" else 775)
        np.testing.assert_allclose(np.sqrt(np.mean(squares)),br,rtol=0,atol=2e-8)
    data=json.loads(fixture.read_text());station,labels,residual,z=residual_structure(data,fit)
    names={str(n):i for i,n in enumerate(fit["names"])};x=fit["x"];prior=[];coefficients={};cov=fit["retained_covariance"]
    for sat in fit["satellites"]:
        prior.extend(x[names[f"orbit:{sat}:{k}"]]/(1000 if k<3 else 1) for k in range(6))
        j=names[f"srpD0:{sat}"];coefficients[str(sat)]=dict(D0_mps2=-1e-7+1e-7*float(x[j]),formal_sigma_mps2=1e-7*float(np.sqrt(cov[j,j])))
    for station_name in data["context"]["stations"]:
        a,b,c=[x[names[f"wet:{station_name}:{k}"]] for k in ("0","1","6h")]
        prior.extend([a/.3,b/.3,(b-a)/.03,(c-b)/.03])
    cost=float(z@z+np.sum(np.square(prior)));last=step["history"][-1]
    np.testing.assert_allclose(cost,last["cost_after"],rtol=0,atol=2e-8)
    assert last["trajectory_step_bound_m"]<.001 and not last["update_applied"]
    np.testing.assert_allclose(cov,cov.T,rtol=0,atol=1e-12);np.linalg.cholesky(cov)
    previous=np.load(folder/manifest["accepted_trials"][-1]/"solution.npz")
    for key in ("x","states","residual_m","sigma_m"):np.testing.assert_array_equal(fit[key],previous[key])
    report=dict(status="station_d0_evaluated_and_audited_not_accuracy_acceptance",reference_sha256=reference.sha256,
        comparisons=comparisons,before={k:strip(v) for k,v in before.items()},after={k:strip(v) for k,v in after.items()},
        coefficients=coefficients,station_residuals=station,independent_cost=cost,history=step["history"],
        independent_cartesian_scores_pass=True,stationary_checkpoint_bitwise_pass=True,covariance_positive_definite=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:{key:v for key,v in value.items() if key not in ("per_satellite","determined_in_both")} for k,value in comparisons.items()},indent=2),flush=True)


if __name__=="__main__":main()
