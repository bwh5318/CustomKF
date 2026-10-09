"""Guarded, training-only free-force fit with fixed native IGS holdout."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from customkf.stage5b_step import restore
from claude.tools.dynamics_six_step import locate, reference_positions, stats
from claude.tools.pinned_sources import ROOT, sha, verify
from claude.tools.force_parameter_fit import solve_force, VARIANTS

SIX = ROOT/"claude/runs/20260912T025241Z-dynamics-six"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(); parser.add_argument("--satellite",required=True)
    parser.add_argument("--variant",choices=VARIANTS,required=True); args=parser.parse_args()
    verify(); _,fixture,orbit,_=locate("six"); context,_,seeds=restore(fixture)
    assert tuple(context["model"].parameter_names)==("D0","Y0","B0","Bc1","Bs1")
    sat=args.satellite; assert sat in seeds
    times=10.+np.arange(25)*900.; train=np.arange(0,25,2); held=np.arange(1,25,2)
    reference,ecef,rotations=reference_positions(times,sat)
    positions=np.einsum("tji,tj->ti",rotations,ecef)
    state,p,trajectory,history,cov=solve_force(seeds[sat],times[train],positions[train],context["model"],context["duration_s"],args.variant)
    states=np.array([trajectory.state(t) for t in times])
    delta=np.einsum("tij,tj->ti",rotations,states[:,:3])-ecef
    oldmeta=json.loads((SIX/"validation.json").read_text()); oldpath=SIX/oldmeta["completed"][sat]
    oldreport=json.loads((oldpath/"diagnostic.json").read_text())
    assert sha(oldpath/"diagnostic_fit.npz")==oldreport["solution_sha256"]
    old=np.load(oldpath/"diagnostic_fit.npz")
    np.testing.assert_array_equal(times,old["times_s"])
    np.testing.assert_array_equal(ecef,old["reference_ecef_m"])
    if args.variant=="fixed":
        np.testing.assert_array_equal(state,old["initial_state"])
        np.testing.assert_array_equal(states,old["states"])
    active=list(VARIANTS[args.variant]); std=np.sqrt(np.diag(cov)); corr=cov/std[:,None]/std[None,:]
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    np.savez_compressed(folder/"fit.npz",initial_state=state,parameters=p,states=states,times_s=times,
        train_indices=train,held_indices=held,reference_ecef_m=ecef,rotations=rotations,
        covariance_unit_position_weight=cov,satellite=np.array(sat),active=np.array(active,dtype=int))
    scores={label:stats(delta[index]) for label,index in (("train",train),("held",held),("all",np.arange(25)),("first_three_hours",np.arange(13)))}
    fixed=oldreport["fit"]["held"]["rms_3d_m"]; current=scores["held"]["rms_3d_m"]
    report=dict(status="reference_force_parameter_fit_complete_not_POD",satellite=sat,variant=args.variant,
        estimated_parameters=6+len(active),parameter_names=[context["model"].parameter_names[i] for i in active],
        coefficients_mps2=p.tolist(),unit_position_weight_parameter_std=std.tolist(),
        max_abs_state_force_correlation=float(np.max(abs(corr[:6,6:]))) if active else None,
        scaled_condition=history[-1]["scaled_condition"],condition_over_1e8=history[-1]["scaled_condition"]>1e8,
        coefficient_abs_over_1e_minus6_mps2=bool(np.any(abs(p)>1e-6)),
        fit=scores,fixed_force_held_rms_m=fixed,held_improvement_percent=100*(1-current/fixed),
        held_regression_over_1_cm=current-fixed>.01,held_reduction_at_least_half=current<=.5*fixed,
        history=history,held_positions_used_in_fit=False,priors=False,reference_sha256=reference.sha256,
        fixture_sha256=sha(fixture),source_protocol_sha256=sha(ROOT/"FORCE_PARAMETER_PROTOCOL.md"),
        fixed_fit_sha256=sha(oldpath/"diagnostic_fit.npz"),solution_sha256=sha(folder/"fit.npz"))
    (folder/"fit.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__": main()
