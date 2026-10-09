"""Guarded independent free-force archive scoring and SVD stationarity audit."""
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.stage5b_step import restore
from claude.tools.pinned_sources import ROOT,sha
from claude.tools.dynamics_six_step import locate,reference_positions
from claude.tools.force_parameter_fit import ForceTrajectory,VARIANTS,design_at


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    campaign=Path(sys.argv[1]); manifest=json.loads((campaign/"validation.json").read_text())
    for name,digest in manifest["source_sha256"].items(): assert sha(ROOT/name)==digest,name
    _,fixture,_,_=locate("six"); context,_,_=restore(fixture); times=10.+np.arange(25)*900.
    train=np.arange(0,25,2); held=np.arange(1,25,2); per={}
    for name in manifest["completed"]:
        folder=campaign/name; report=json.loads((folder/"fit.json").read_text()); fit=np.load(folder/"fit.npz")
        assert sha(folder/"fit.npz")==report["solution_sha256"]
        sat=str(fit["satellite"]); active=list(VARIANTS[report["variant"]])
        np.testing.assert_array_equal(fit["active"],active); np.testing.assert_array_equal(fit["times_s"],times)
        np.testing.assert_array_equal(fit["train_indices"],train); np.testing.assert_array_equal(fit["held_indices"],held)
        reference,ecef,rotations=reference_positions(times,sat)
        assert reference.sha256==report["reference_sha256"]
        np.testing.assert_array_equal(ecef,fit["reference_ecef_m"]); np.testing.assert_array_equal(rotations,fit["rotations"])
        trajectory=ForceTrajectory(fit["initial_state"],context["model"],context["duration_s"],fit["parameters"])
        states=np.array([trajectory.state(t) for t in times]); np.testing.assert_array_equal(states,fit["states"])
        delta=np.einsum("tij,tj->ti",rotations,states[:,:3])-ecef
        for label,index in (("train",train),("held",held),("all",np.arange(25)),("first_three_hours",np.arange(13))):
            rms=float(np.sqrt(np.mean(np.sum(delta[index]**2,axis=1))))
            np.testing.assert_allclose(rms,report["fit"][label]["rms_3d_m"],rtol=0,atol=2e-8)
        scales=np.r_[[100.]*3,[.01]*3,np.asarray(context["model"].parameter_scales)[active]]
        design=design_at(trajectory,times[train],active)*scales
        target=(np.einsum("tji,tj->ti",rotations,ecef)-states[:,:3])[train].ravel()
        u,s,vt=np.linalg.svd(design,full_matrices=False); assert sum(s>s[0]*1e-11)==len(scales)
        correction=(vt.T@((u.T@target)/s))*scales
        bound=float(np.linalg.norm(correction[:3])+context["duration_s"]*np.linalg.norm(correction[3:6]))
        assert bound<1e-4,(name,bound)
        covariance=(vt.T/s**2)@vt*scales[:,None]*scales[None,:]
        std=np.sqrt(np.diag(covariance))
        np.testing.assert_allclose(fit["covariance_unit_position_weight"]/std[:,None]/std[None,:],
            covariance/std[:,None]/std[None,:],rtol=0,atol=1e-7)
        assert report["history"][-1]["termination"]=="stationary" and not report["held_positions_used_in_fit"] and not report["priors"]
        per[name]=dict(held_rms_m=report["fit"]["held"]["rms_3d_m"],fixed_held_rms_m=report["fixed_force_held_rms_m"],
            scaled_condition=float(s[0]/s[-1]),svd_stationarity_bound_m=bound,rank=len(s),
            max_abs_state_force_correlation=report["max_abs_state_force_correlation"],
            coefficients_mps2=report["coefficients_mps2"])
    result=dict(status="force_parameter_independent_review_pass_not_POD",cases=per,source_hashes_verified=True,
                raw_cartesian_scores_verified=True,reintegration_bitwise=True,svd_covariance_and_stationarity_verified=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"review.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2),flush=True)


if __name__=="__main__":main()
