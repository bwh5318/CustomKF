"""Nonlinear confirmation of one pinned Stage 5 observation-noise realization."""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from .stage5_pilot import prepare, Pilot, forbid_precise_product_reads
from .prepare_stage2 import sha


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("noise",type=Path)
    args=parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    data=np.load(args.noise)
    context,rows,seeds=prepare()
    pilot=Pilot(context,rows,seeds)
    np.testing.assert_array_equal(data["names"],pilot.names)
    x,history,converged=pilot.solve(observations=data["observations"],max_iterations=5)
    _,_,residual,sigma,_,cost,products=pilot.evaluate(x,jacobian=False,observations=data["observations"])
    states=np.array([[products.state(s,t) for t in data["times_s"]] for s in pilot.sats])
    error=states[:,:,:3]-data["truth_states"][:,:,:3]
    linear_products=pilot.products(data["linear_step"])
    linear_states=np.array([[linear_products.state(s,t) for t in data["times_s"]] for s in pilot.sats])
    delta=states[:,:,:3]-linear_states[:,:,:3]
    report={"scope":"One nonlinear realization confirms a linearized Gaussian-noise experiment; not real-data accuracy",
        "converged":converged,"history":history,"noise_sha256":sha(args.noise),"noise_input":str(args.noise),
        "network_3d_rms_m":float(np.sqrt(np.mean(np.sum(error**2,axis=2)))),
        "linearized_prediction_3d_rms_m":float(data["linear_network_rms_m"][0]),
        "nonlinear_minus_reintegrated_linear_solution_rms_m":float(np.sqrt(np.mean(np.sum(delta**2,axis=2)))),
        "residual_rms_m":float(np.sqrt(np.mean(residual**2))),"cost_with_priors":cost,"precise_products_used":False}
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"recovery.json").write_text(json.dumps(report,indent=2)+"\n")
    np.savez_compressed(folder/"recovery.npz",x=x,states=states,error_m=error)
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":main()
