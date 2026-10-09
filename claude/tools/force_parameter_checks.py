"""Guarded trajectory identity, force/state finite differences and synthetic closure."""
import json
import os
from pathlib import Path
import numpy as np
from customkf.dynamic_observation import Trajectory
from customkf.stage5b_step import restore
from claude.tools.dynamics_six_step import locate
from claude.tools.force_parameter_fit import ForceTrajectory, INITIAL_P, solve_force, design_at


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    _,fixture,_,_=locate("six"); context,_,seeds=restore(fixture)
    model=context["model"]; duration=context["duration_s"]; state=seeds["G04"]
    times=10.+np.arange(25)*900.
    original=Trajectory(state,model,duration); candidate=ForceTrajectory(state,model,duration,INITIAL_P)
    for t in times:
        np.testing.assert_array_equal(candidate.state(t),original.state(t))
        np.testing.assert_array_equal(candidate.partial(t),original.partial(t))
    checked=0; maximum=0.; selected=times[[0,3,6,12,18,24]]
    design=design_at(candidate,selected,list(range(5))).reshape(len(selected),3,11)
    steps=np.r_[[1.]*3,[1e-4]*3,[1e-9]*5]
    for k,h in enumerate(steps):
        a,b=state.copy(),state.copy(); pa,pb=INITIAL_P.copy(),INITIAL_P.copy()
        if k<6: a[k]+=h; b[k]-=h
        else: pa[k-6]+=h; pb[k-6]-=h
        plus=ForceTrajectory(a,model,duration,pa); minus=ForceTrajectory(b,model,duration,pb)
        finite=np.array([(plus.state(t)[:3]-minus.state(t)[:3])/2 for t in selected])
        analytic=design[:,:,k]*h; maximum=max(maximum,float(np.max(abs(finite-analytic)))); checked+=finite.size
        np.testing.assert_allclose(finite,analytic,rtol=0,atol=2e-5)
    truth_state=state+np.array([2.,-1.,3.,.0002,-.0001,.0003])
    truth_p=INITIAL_P+np.array([2e-8,-3e-9,4e-9,2e-9,-1e-9])
    truth=ForceTrajectory(truth_state,model,duration,truth_p); train=times[::2]
    positions=np.array([truth.state(t)[:3] for t in train])
    estimated,p,fitted,history,_=solve_force(state,train,positions,model,duration,"ecom5")
    error=max(np.linalg.norm(fitted.state(t)[:3]-truth.state(t)[:3]) for t in times)
    assert error<1e-4,error
    np.testing.assert_allclose(p,truth_p,rtol=0,atol=1e-10)
    report=dict(status="force_parameter_checks_pass",production_states_and_stm_bitwise_equal=True,
        finite_difference_entries=checked,max_finite_displacement_error_m=maximum,
        synthetic_max_position_error_m=float(error),synthetic_max_coefficient_error_mps2=float(np.max(abs(p-truth_p))),
        synthetic_history=history)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"checks.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__": main()
