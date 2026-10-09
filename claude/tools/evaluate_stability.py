"""Guarded trajectory stability gates and separate IGS scoring of prior/start tests."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT,sha
from claude.tools.stability_step import BASE
from claude.tools.evaluate_ablation import Reference,score,pooled,strip


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("campaign",type=Path);args=parser.parse_args()
    campaign=args.campaign;manifest=json.loads((campaign/"validation.json").read_text())
    old=json.loads((BASE/"validation.json").read_text());baseline_path=BASE/old["final"]
    baseline=np.load(baseline_path/"solution.npz");reference=Reference()
    before=score(reference,baseline_path,BASE/"prepare/fixture.json",BASE/"prepare/initial.npz")
    comparisons={};solutions={};scores={}
    for name,case in manifest["cases"].items():
        assert case["final"],"No converged result"
        path=campaign/case["final"];step=json.loads((path/"step.json").read_text())
        assert step["status"]=="converged" and sha(path/"solution.npz")==step["solution_sha256"]
        saved=np.load(path/"solution.npz");solutions[name]=saved
        for key in ("names","satellites","times_s"):np.testing.assert_array_equal(saved[key],baseline[key])
        delta=saved["states"][:,:,:3]-baseline["states"][:,:,:3];distance=np.linalg.norm(delta,axis=2)
        maximum=float(distance.max());rms=float(np.sqrt(np.mean(distance**2)))
        per={str(s):{"rms_m":float(np.sqrt(np.mean(distance[i]**2))),"max_m":float(distance[i].max())} for i,s in enumerate(saved["satellites"])}
        comparisons[name]={"trajectory_rms_vs_baseline_m":rms,"trajectory_max_vs_baseline_m":maximum,
                           "one_cm_stability_gate_pass":maximum<=.01,"per_satellite":per}
        result=score(reference,path,BASE/"prepare/fixture.json",BASE/"prepare/initial.npz")
        both=[s for s,v in result["per_satellite"].items() if v["class"]==before["per_satellite"][s]["class"]=="determined"]
        scores[name]={"determined_in_both":{"baseline":pooled(before,both),"test":pooled(result,both)},"score":strip(result)}
    if "weak-warm" in solutions:
        for name in ("weak-perturbed","weak-cold"):
            if name in solutions:
                distance=np.linalg.norm(solutions[name]["states"][:,:,:3]-solutions["weak-warm"]["states"][:,:,:3],axis=2)
                comparisons[name]["same_prior_start_max_difference_m"]=float(distance.max())
                comparisons[name]["same_prior_start_gate_pass"]=bool(distance.max()<=.01)
    report={"status":"stability_evaluated_not_absolute_accuracy_acceptance","threshold_m":.01,
            "comparisons":comparisons,"scores":scores,"reference_sha256":reference.sha256,
            "baseline_solution_sha256":sha(baseline_path/"solution.npz")}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:{x:y for x,y in v.items() if x!="per_satellite"} for k,v in comparisons.items()},indent=2))


if __name__=="__main__":main()
