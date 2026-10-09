"""Guarded prepare-invariance and separate IGS evaluation of YELL addition.

The estimator does not call the scoring functions. Frozen sigma split and full
and common scoring sets are retained. No fit or data editing here.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from .prepare_stage2 import ROOT,sha

BASE=ROOT/"validation/stage5b/20260910T203254Z/completion-20260910T205844Z"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("campaign",type=Path)
    parser.add_argument("--prepare-only",action="store_true");args=parser.parse_args()
    folder=args.campaign;output=Path(os.environ["CUSTOMKF_RUN_DIR"])
    old=json.loads((BASE/"expanded-long-prepare/fixture.json").read_text())
    new=json.loads((folder/"prepare/fixture.json").read_text())
    assert [r for r in new["rows"] if r["station"]!="YELL"]==old["rows"]
    assert new["seeds"]==old["seeds"]
    for key,value in old["context"].items():
        if key=="stations":
            assert {s:v for s,v in new["context"][key].items() if s!="YELL"}==value
        elif key=="inputs":
            assert all(new["context"][key][s]==v for s,v in value.items())
        else:assert new["context"][key]==value,key
    initial=np.load(folder/"prepare/initial.npz");old_initial=np.load(BASE/"expanded-long-prepare/initial.npz")
    for key in old_initial.files:np.testing.assert_array_equal(initial[key],old_initial[key],err_msg=key)
    coverage={}
    for sat in ("G16","G18","G26","G29","G31"):
        epochs={i:{r["station"] for r in new["rows"] if r["satellite"]==sat and r["epoch"]==i} for i in range(37)}
        coverage[sat]={"YELL_epochs":[i for i,s in epochs.items() if "YELL" in s],
                       "two_receiver_epochs":[i for i,s in epochs.items() if len(s)>=2]}
    report={"status":"unchanged_baseline_rows_seeds_and_sampled_initial_states_verified",
            "YELL_links":sum(r["station"]=="YELL" for r in new["rows"]),"coverage":coverage}
    if not args.prepare_only:
        from claude.tools.evaluate_ablation import Reference,score,pooled,strip
        campaign=json.loads((folder/"validation.json").read_text());final=folder/campaign["final"]
        assert json.loads((final/"step.json").read_text())["status"]=="converged"
        reference=Reference()
        baseline=score(reference,BASE/"expanded-long-final",BASE/"expanded-long-prepare/fixture.json",BASE/"expanded-long-prepare/initial.npz")
        fitted=score(reference,final,folder/"prepare/fixture.json",folder/"prepare/initial.npz")
        common=sorted(set(baseline["per_satellite"])&set(fitted["per_satellite"]))
        both=[s for s in common if baseline["per_satellite"][s]["class"]==fitted["per_satellite"][s]["class"]=="determined"]
        # Initial array equality above verifies identical satellite/time domains.
        # Check RMS independently in ECEF, without the evaluator's RAC basis.
        saved=np.load(final/"solution.npz");squares=[]
        from .stage5_pilot import ORIGIN
        for si,s in enumerate(saved["satellites"]):
            for ti,t in enumerate(saved["times_s"]):
                sample=reference.raw.samples.get((ORIGIN+int(round(float(t)*1e9)),str(s)))
                if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:continue
                diff=reference.epoch.celestial_to_terrestrial(float(t))@saved["states"][si,ti,:3]-sample.xyz_m
                squares.append(float(diff@diff))
        cartesian=float(np.sqrt(np.mean(squares)))
        np.testing.assert_allclose(cartesian,fitted["groups"]["all"]["fit"]["rms_3d_m"],rtol=0,atol=2e-8)
        report.update(status="same_arc_YELL_comparison_complete_not_accuracy_acceptance",reference_sha256=reference.sha256,
                      all_common={"baseline":pooled(baseline,common),"YELL":pooled(fitted,common)},
                      determined_in_both={"baseline":pooled(baseline,both),"YELL":pooled(fitted,both)},
                      cartesian_independent_rms_m=cartesian,baseline=strip(baseline),YELL=strip(fitted))
    (output/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("baseline","YELL","coverage")},indent=2))


if __name__=="__main__":main()
