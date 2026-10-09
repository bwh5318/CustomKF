"""Guarded cost decomposition and independent fixed-orbit/reference checks."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from claude.tools.observation_profile import BASE, REF, SATS
from claude.tools.yell_continuation_review import residual_structure


def prior_cost(x, index, sats, stations):
    orbit = sum((x[index[f"orbit:{s}:{k}"]]/(1000. if k<3 else 1.))**2 for s in sats for k in range(6))
    level = sum((x[index[f"wet:{s}:{k}"]]/.3)**2 for s in stations for k in (0,1))
    change = sum(((x[index[f"wet:{s}:1"]]-x[index[f"wet:{s}:0"]])/.03)**2 for s in stations)
    return {"orbit":float(orbit),"wet_level":float(level),"wet_change":float(change)}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("campaign",type=Path)
    folder=parser.parse_args().campaign
    manifest=json.loads((folder/"validation.json").read_text())
    for group in ("source_sha256","report_sha256"):
        for name,digest in manifest[group].items():assert sha(ROOT/name)==digest,name
    prepared=folder/"prepare";final=folder/manifest["final"]
    p=json.loads((prepared/"profile.json").read_text());f=json.loads((final/"profile.json").read_text())
    assert f["status"]=="converged" and sha(final/"diagnostic_nuisance.npz")==f["archive_sha256"]
    assert sha(prepared/"linear_profiles.npz")==p["archive_sha256"]
    fit=np.load(final/"diagnostic_nuisance.npz");linear=np.load(prepared/"linear_profiles.npz")
    baseline=np.load(BASE/"iteration-1/solution.npz")
    fixture=json.loads((BASE/"prepare/fixture.json").read_text())
    index={str(n):i for i,n in enumerate(fit["names"])}
    np.testing.assert_array_equal(fit["names"],baseline["names"])
    np.testing.assert_array_equal(fit["sigma_m"],baseline["sigma_m"])
    for si,sat in enumerate(fit["satellites"]):
        k=index[f"orbit:{sat}:0"]
        if sat in SATS:
            target=np.load(REF/str(sat)/"diagnostic_fit.npz")
            np.testing.assert_allclose(np.array(fixture["seeds"][str(sat)])+fit["x"][k:k+6],target["initial_state"],rtol=0,atol=1e-8)
            np.testing.assert_allclose(fit["states"][si,::3],target["states"],rtol=0,atol=2e-7)
        else:
            np.testing.assert_array_equal(fit["x"][k:k+6],baseline["x"][k:k+6])
            np.testing.assert_array_equal(fit["states"][si],baseline["states"][si])
    before,labels,r0,z0=residual_structure(fixture,baseline)
    after,_,r1,z1=residual_structure(fixture,fit)
    priors0=prior_cost(baseline["x"],index,baseline["satellites"],fixture["context"]["stations"])
    priors1=prior_cost(fit["x"],index,baseline["satellites"],fixture["context"]["stations"])
    cost0=float(z0@z0)+sum(priors0.values());cost1=float(z1@z1)+sum(priors1.values())
    np.testing.assert_allclose(cost0,p["original_cost"],rtol=0,atol=1e-8)
    np.testing.assert_allclose(cost1,f["history"][-1]["cost_after"],rtol=0,atol=1e-8)
    difference=r1-r0
    row_change=z1*z1-z0*z0
    groups={}
    for grouping in ("station","satellite","epoch","station_hour","kind"):
        buckets=defaultdict(list)
        for i,(row,kind) in enumerate(labels):
            key=(f"{row['station']}:{min(row['epoch']//12,2)}" if grouping=="station_hour" else
                 ("phase" if kind else "code") if grouping=="kind" else str(row[grouping]))
            buckets[key].append(i)
        groups[grouping]={key:{"rows":len(v),"objective_change":float(np.sum(row_change[v])),
                              "residual_shift_rms_mm":float(1000*np.sqrt(np.mean(difference[v]**2))),
                              "baseline_rms_mm":float(1000*np.sqrt(np.mean(r0[v]**2))),
                              "substitution_rms_mm":float(1000*np.sqrt(np.mean(r1[v]**2)))} for key,v in buckets.items()}
        np.testing.assert_allclose(sum(v["objective_change"] for v in groups[grouping].values()),float(z1@z1-z0@z0),rtol=0,atol=1e-8)
    max_linear_difference=float(np.max(abs(r1-linear["joint_residual_m"])))
    np.testing.assert_allclose(cost1,p["cases"]["joint"]["predicted_cost"],rtol=0,atol=.01)
    changes={str(n):float(fit["x"][i]-baseline["x"][i]) for i,n in enumerate(fit["names"]) if not str(n).startswith("orbit:")}
    top=sorted(changes.items(),key=lambda item:abs(item[1]),reverse=True)[:20]
    report={"status":"observation_profile_reviewed_reference_dependent_diagnostic", "baseline_total_cost":cost0,
            "substitution_total_cost":cost1,"total_cost_increase":cost1-cost0,
            "observation_cost_increase":float(z1@z1-z0@z0),"prior_costs":{"baseline":priors0,"substitution":priors1},
            "linearized_joint_cost":p["cases"]["joint"]["predicted_cost"],"nonlinear_minus_linear_cost":cost1-p["cases"]["joint"]["predicted_cost"],
            "max_nonlinear_minus_linear_residual_m":max_linear_difference,"grouped_changes":groups,
            "station_residuals":{"baseline":before,"substitution":after},"largest_nuisance_changes_m":top,
            "linear_profiles":p["cases"],"reference_dependent":True,
            "interpretation_limit":"No calibrated chi-square probabilities; supplied sigmas and priors are not empirically calibrated. Group contributions can be negative and are not causal station attribution.",
            "review_source_sha256":sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"review.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ("baseline_total_cost","substitution_total_cost","total_cost_increase","observation_cost_increase","nonlinear_minus_linear_cost","max_nonlinear_minus_linear_residual_m")},indent=2))


if __name__=="__main__":main()
