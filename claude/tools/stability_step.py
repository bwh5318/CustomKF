"""One guarded prior/start sensitivity iteration, using the existing iteration engine.

No root estimator source changes. The only injected dependency is the Pilot
factory's orbit prior factor. Priors remain centred on the archived broadcast
seed; a starting-point change affects x, never seeds or the prior centre.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT,sha
from customkf.stage5_pilot import Pilot,forbid_precise_product_reads
from customkf.stage5b_step import restore
from claude.tools import ablation_step as engine

BASE=ROOT/"validation/guam/20260911T155927Z"
CASES={"baseline-check":(1.,"warm"),"weak-warm":(10.,"warm"),
       "weak-perturbed":(10.,"perturbed"),"weak-cold":(10.,"cold")}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("--case",choices=CASES,required=True)
    parser.add_argument("--previous",type=Path);args=parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"]);factor,start=CASES[args.case]
    manifest=json.loads((BASE/"validation.json").read_text())
    for name,digest in manifest["source_sha256"].items():assert sha(ROOT/name)==digest,name
    fixture=BASE/"prepare/fixture.json";baseline=BASE/manifest["final"]/"solution.npz"
    for path in (fixture,baseline):assert sha(path)==manifest["artifacts_sha256"][path.relative_to(BASE).as_posix()]
    spec={"case":args.case,"prior_factor":factor,"start":start,
          "position_prior_sigma_m":1000*factor,"velocity_prior_sigma_mps":factor,
          "prior_centres":"unchanged original broadcast seeds; x=0", "fixture_sha256":sha(fixture),
          "baseline_solution_sha256":sha(baseline),"worker_sha256":sha(Path(__file__)),
          "iteration_engine_sha256":sha(ROOT/"claude/tools/ablation_step.py")}
    if args.previous:
        before=json.loads((args.previous/"step.json").read_text())
        assert before["experiment"]==spec,"Different experiment checkpoint"
    else:
        initial=np.load(baseline);x=initial["x"].copy() if start=="warm" else np.zeros(len(initial["x"]))
        if start=="perturbed":
            fixture_data=json.loads(fixture.read_text());names=list(initial["names"])
            # Deterministic alternating perturbations in each seed's inertial RAC.
            for si,sat in enumerate(initial["satellites"]):
                seed=np.array(fixture_data["seeds"][str(sat)])
                radial=seed[:3]/np.linalg.norm(seed[:3]);cross=np.cross(seed[:3],seed[3:]);cross/=np.linalg.norm(cross)
                along=np.cross(cross,radial);basis=np.column_stack((radial,along,cross));sign=(-1.)**si
                indices=[names.index(f"orbit:{sat}:{k}") for k in range(6)]
                x[indices[:3]]=basis@np.array([100.,-70.,40.])*sign
                x[indices[3:]]=basis@np.array([.02,-.01,.01])*sign
        args.previous=folder/"initial_parameters";args.previous.mkdir()
        np.savez_compressed(args.previous/"solution.npz",x=x,names=initial["names"])
        (args.previous/"step.json").write_text(json.dumps({"status":"parameter_initialization_not_orbit_product", "history":[],
            "fixture_sha256":sha(fixture),"solution_sha256":sha(args.previous/"solution.npz"),"experiment":spec})+"\n")
    def pilot_factory(path):
        context,rows,seeds=restore(path);pilot=Pilot(context,rows,seeds,prior_factor=factor)
        count=6*len(pilot.sats)
        np.testing.assert_array_equal(pilot.prior_sigma[:count],np.tile([1000*factor]*3+[factor]*3,len(pilot.sats)))
        np.testing.assert_array_equal(pilot.prior_sigma[count:],np.full(2*len(pilot.stations),.3))
        return pilot
    # Reuse the already tested nonlinear line search and stationary-stop engine.
    engine.build_pilot=pilot_factory
    engine.iterate(argparse.Namespace(fixture=fixture,previous=args.previous),folder)
    step=json.loads((folder/"step.json").read_text());step["experiment"]=spec
    if args.case=="baseline-check":
        saved=np.load(folder/"solution.npz");reference=np.load(baseline)
        for key in ("x","names","states","times_s","satellites","residual_m","sigma_m"):
            np.testing.assert_array_equal(saved[key],reference[key],err_msg=key)
        np.testing.assert_allclose(saved["retained_covariance"],reference["retained_covariance"],rtol=1e-12,atol=1e-12)
        assert step["status"]=="converged" and not step["history"][-1]["update_applied"]
        step["baseline_reproduction"]="arrays bitwise equal; covariance agrees at 1e-12"
    (folder/"step.json").write_text(json.dumps(step,indent=2)+"\n")


if __name__=="__main__":main()
