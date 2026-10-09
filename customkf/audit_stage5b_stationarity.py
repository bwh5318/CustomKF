"""Guarded diagnosis of a rejected near-stationary nonlinear step.

Do not change line-search tolerances or claim convergence. Record the proposed
physical step, cancellation-resistant linear-model reduction and fresh costs at
zero/full/fractional steps for independent review.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from .stage5b_step import restore,write_json
from .stage5_pilot import Pilot,forbid_precise_product_reads
from .reduced_network import reduced_qr
from .prepare_stage2 import ROOT,sha


def predicted_reduction(blocks,constraints,step):
    n=constraints[0].shape[1];offset=n;reduction=0.;direction_norm2=0.
    for b in blocks:
        k=b.local.shape[1];d=(b.retained@step[:n]+b.local@step[offset:offset+k])/b.sigma
        y=b.target/b.sigma
        reduction+=float(2*y@d-d@d);direction_norm2+=float(d@d);offset+=k
    c,y,s=constraints;d=c@step[:n]/s;y=y/s
    return reduction+float(2*y@d-d@d),direction_norm2+float(d@d)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",type=Path,required=True);parser.add_argument("--previous",type=Path,required=True);args=parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    context,rows,seeds=restore(args.fixture);pilot=Pilot(context,rows,seeds)
    prior=json.loads((args.previous/"step.json").read_text())
    if sha(args.fixture)!=prior["fixture_sha256"] or sha(args.previous/"solution.npz")!=prior["solution_sha256"]:raise ValueError("Checkpoint changed")
    for name,digest in prior["source_sha256"].items():
        if sha(ROOT/name)!=digest:raise ValueError("Model source changed: "+name)
    saved=np.load(args.previous/"solution.npz");np.testing.assert_array_equal(saved["names"],pilot.names);x=saved["x"]
    blocks,constraints,residual,sigma,_,cost,products=pilot.evaluate(x)
    solution=reduced_qr(blocks,constraints);step=solution.estimate
    bound=max(np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]:pilot.index[f"orbit:{s}:0"]+3])+pilot.duration*np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]+3:pilot.index[f"orbit:{s}:0"]+6]) for s in pilot.sats)
    reduction,dnorm=predicted_reduction(blocks,constraints,step)
    report={"status":"stationarity_diagnostic_only","cost":cost,"trajectory_step_bound_m":bound,"predicted_reduction":reduction,"whitened_direction_norm_squared":dnorm,"trials":[],"previous_solution_sha256":sha(args.previous/"solution.npz"),"fixture_sha256":sha(args.fixture),"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}}
    print(json.dumps({k:v for k,v in report.items() if k!="source_sha256"}),flush=True)
    for alpha in (0.,1.,.5,.25,.125):
        _,_,r2,_,_,cost2,p2=pilot.evaluate(x+alpha*step,jacobian=False)
        report["trials"].append({"alpha":alpha,"cost":cost2,"cost_change":cost2-cost,"max_residual_change_m":float(np.max(np.abs(r2-residual)))})
        print(report["trials"][-1],flush=True)
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"]);write_json(folder/"stationarity.json",report)


if __name__=="__main__":main()
