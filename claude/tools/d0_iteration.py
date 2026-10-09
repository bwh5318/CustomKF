"""Guarded split D0 iteration: linearization/QR, then one trial per worker.

Splitting bounds wall time without changing the inherited objective, QR, line
search or stationarity rule. Each stage verifies the preceding checkpoint hash.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore
from customkf.prepare_stage2 import sha
from customkf.reduced_network import reduced_qr
from customkf.nonlinear_stop import model_reduction,stationary
from claude.tools.d0_pilot import D0Pilot
from claude.tools.ablation_step import sources


def save_solution(folder,pilot,x,products,residual,sigma,cov,meta,history,status):
    times=np.arange(10.,pilot.duration-9.,300.)
    np.savez_compressed(folder/"solution.npz",x=x,names=np.array(pilot.names),
        states=np.array([[products.state(s,t) for t in times] for s in pilot.sats]),
        satellites=np.array(pilot.sats),times_s=times,residual_m=residual,sigma_m=sigma,retained_covariance=cov)
    report=dict(status=status,case=meta["case"],history=history,fixture_sha256=meta["fixture_sha256"],
        solution_sha256=sha(folder/"solution.npz"),precise_products_used=False,
        retained_covariance_at="pre-step linearization; diagnostic only")
    (folder/"step.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("linear","trial"))
    parser.add_argument("--fixture",type=Path,required=True);parser.add_argument("--previous",type=Path)
    parser.add_argument("--linear",type=Path);parser.add_argument("--alpha",type=float,choices=(1.,.5,.25,.125))
    args=parser.parse_args();folder=Path(os.environ["CUSTOMKF_RUN_DIR"]);sys.addaudithook(forbid_precise_product_reads)
    meta=json.loads((args.fixture.parent/"step.json").read_text())
    assert meta["status"]=="prepared" and sha(args.fixture)==meta["fixture_sha256"] and sources()==meta["source_sha256"]
    pilot=D0Pilot(*restore(args.fixture))
    if args.mode=="linear":
        previous=json.loads((args.previous/"step.json").read_text())
        assert previous["fixture_sha256"]==meta["fixture_sha256"] and sha(args.previous/"solution.npz")==previous["solution_sha256"]
        saved=np.load(args.previous/"solution.npz");np.testing.assert_array_equal(saved["names"],pilot.names)
        x=saved["x"].copy();history=previous["history"]
        blocks,constraints,residual,sigma,_,cost,products=pilot.evaluate(x)
        print("Jacobian complete",flush=True);solution=reduced_qr(blocks,constraints);step=solution.estimate
        bound=max(np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]:pilot.index[f"orbit:{s}:0"]+3])+
                  pilot.duration*np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]+3:pilot.index[f"orbit:{s}:0"]+6]) for s in pilot.sats)
        # Include the force contribution; the old six-state bound alone is insufficient.
        force_bound=max(np.linalg.norm(products.trajectories[s].partial(t)[:3]@step[pilot.index[f"orbit:{s}:0"]:pilot.index[f"orbit:{s}:0"]+6]+
            products.trajectories[s].force_partial(t)[:3,0]*1e-7*step[pilot.index[f"srpD0:{s}"]])
            for s in pilot.sats for t in np.arange(10.,pilot.duration-9.,300.))
        bound=max(float(bound),float(force_bound));reduction,dnorm=model_reduction(blocks,constraints,step)
        record=dict(iteration=len(history),cost_before=cost,predicted_reduction=reduction,whitened_direction_norm_squared=dnorm,
                    trajectory_step_bound_m=bound,force_inclusive_sampled_step_bound_m=float(force_bound))
        if stationary(bound,cost,reduction,dnorm):
            record.update(cost_after=cost,accepted=True,update_applied=False,termination="small_step_and_linearized_progress",step_fraction=0.)
            save_solution(folder,pilot,x,products,residual,sigma,solution.retained_covariance,meta,history+[record],"converged")
        else:
            np.savez_compressed(folder/"direction.npz",x=x,step=step,names=np.array(pilot.names),retained_covariance=solution.retained_covariance)
            report=dict(status="linearized",fixture_sha256=meta["fixture_sha256"],direction_sha256=sha(folder/"direction.npz"),
                        history=history,record=record,workspace_estimate_mib=solution.workspace_estimate_bytes/2**20)
            (folder/"step.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2),flush=True)
    else:
        linear=json.loads((args.linear/"step.json").read_text())
        assert linear["status"]=="linearized" and linear["fixture_sha256"]==meta["fixture_sha256"]
        assert sha(args.linear/"direction.npz")==linear["direction_sha256"]
        saved=np.load(args.linear/"direction.npz");np.testing.assert_array_equal(saved["names"],pilot.names)
        x=saved["x"]+args.alpha*saved["step"]
        _,_,residual,sigma,_,cost,products=pilot.evaluate(x,jacobian=False)
        before=linear["record"]["cost_before"];accepted=cost<=before+max(1e-6,1e-9*before)
        record=linear["record"]|dict(cost_after=cost,accepted=accepted,update_applied=accepted,termination="line_search",step_fraction=args.alpha)
        if accepted:save_solution(folder,pilot,x,products,residual,sigma,saved["retained_covariance"],meta,linear["history"]+[record],"iteration_complete")
        else:
            (folder/"step.json").write_text(json.dumps(dict(status="trial_rejected",record=record),indent=2)+"\n")
            print("Trial rejected",flush=True)


if __name__=="__main__":main()
