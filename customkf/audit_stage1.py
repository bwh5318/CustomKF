"""Numerical acceptance experiment; launch with customkf.guard (300-second cap)."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import time


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use python -m customkf.guard -- customkf.audit_stage1")
    import numpy as np
    import scipy
    from threadpoolctl import threadpool_info
    from .dynamics import TestForceModel, FixedThirdBody, MU_EARTH, PARAMETER_NAMES, PARAMETER_SCALES
    from .propagation import propagate, IntegrationSettings
    from tests.orbit_oracle import kepler_states, rk4_endpoint

    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    report={"status":"running", "numpy":np.__version__, "scipy":scipy.__version__,
            "threadpools":threadpool_info(), "scope":"Synthetic inertial numerical validation; not a fitted or observed GPS orbit",
            "checks":{}}
    def record(name,values,passed):
        report["checks"][name]={"pass":bool(passed),**values}
        if not passed:
            report["status"]="fail"
        (folder/"audit.json").write_text(json.dumps(report,indent=2)+"\n")
        print(f"{name}: {'pass' if passed else 'FAIL'}",flush=True)
        if not passed:
            raise AssertionError(f"Stage 1 gate failed: {name}; see audit.json")
    def errors(a,b):
        position=np.linalg.norm(a[:,:3]-b[:,:3],axis=1)
        velocity=np.linalg.norm(a[:,3:]-b[:,3:],axis=1)
        return {"position_rms_m":float(np.sqrt(np.mean(position**2))),
                "position_max_m":float(np.max(position)), "velocity_max_mps":float(np.max(velocity)),
                "endpoint_max_m":float(max(position[0],position[-1]))}
    def position_pass(metrics):
        return metrics["position_rms_m"]<.001 and metrics["position_max_m"]<.003
    started=time.perf_counter()
    times=np.unique(np.r_[np.arange(0,86401,300),np.arange(37,86400,277),86400.])
    base=IntegrationSettings()
    fine=replace(base,max_step_s=60,rtol=3e-12,position_atol_m=3e-6,velocity_atol_mps=3e-10,scaled_partial_atol=3e-13)
    finest=replace(base,max_step_s=30,rtol=3e-13,position_atol_m=1e-6,velocity_atol_mps=1e-10,scaled_partial_atol=1e-13)
    report.update(duration_s=86400.,export_samples=len(times),
                  export_description="300-second epochs plus off-grid dense-interpolation probes, including both endpoints",
                  settings={"baseline":asdict(base),"fine":asdict(fine),"finest":asdict(finest)})
    for eccentricity in (0.,.1):
        truth=kepler_states(times,eccentricity=eccentricity)
        result=propagate(truth[0],times)
        metric=errors(result.states_m_mps,truth)
        position,velocity=result.states_m_mps[:,:3],result.states_m_mps[:,3:]
        energy=np.sum(velocity**2,axis=1)/2-MU_EARTH/np.linalg.norm(position,axis=1)
        momentum=np.cross(position,velocity)
        metric.update(energy_relative_drift=float(np.max(np.abs(energy-energy[0]))/abs(energy[0])),
                      angular_momentum_relative_drift=float(np.max(np.linalg.norm(momentum-momentum[0],axis=1))/np.linalg.norm(momentum[0])),
                      rhs_evaluations=result.evaluations,elapsed_s=result.elapsed_s)
        record(f"kepler_e_{eccentricity}",metric,position_pass(metric) and metric["velocity_max_mps"]<1e-6
               and metric["energy_relative_drift"]<1e-10 and metric["angular_momentum_relative_drift"]<1e-10)

    model=TestForceModel(third_bodies=(FixedThirdBody(4.9048695e12,(3e8,2e8,-1e8)),))
    p=np.array([1.08262668e-3,1e-9,-2e-9,3e-9])
    initial=kepler_states([0])[0]
    report["perturbed_model"]={"earth_mu_m3ps2":model.mu_m3ps2,"reference_radius_m":model.radius_m,
                               "parameters":dict(zip(PARAMETER_NAMES,p)),"third_bodies":[asdict(b) for b in model.third_bodies],
                               "warning":"Fixed synthetic lunar-strength body and fixed-axis J2; no real ephemeris or Earth-orientation data"}
    reference=propagate(initial,times,model,p,settings=finest)
    for name,settings in (("120_to_30_second_refinement",base),("60_to_30_second_refinement",fine)):
        trial=propagate(initial,times,model,p,settings=settings)
        metric=errors(trial.states_m_mps,reference.states_m_mps)
        metric.update(rhs_evaluations=trial.evaluations,elapsed_s=trial.elapsed_s)
        record(name,metric,position_pass(metric))
    record("24h_66_equation_profile",{"rhs_evaluations":reference.evaluations,"elapsed_s":reference.elapsed_s,
                                     "returned_array_bytes":sum(a.nbytes for a in (reference.times_s,reference.states_m_mps,reference.state_transition,reference.parameter_sensitivity))},True)
    states=reference.states_m_mps
    energy=np.array([.5*(x[3:]@x[3:])+model.potential_m2ps2(x[:3],p) for x in states])
    drift=float(np.max(np.abs(energy-energy[0]))/abs(energy[0]))
    record("perturbed_conservative_energy",{"relative_drift":drift},drift<1e-10)

    # Fixed-step RK4 is only a test oracle. It shares forces, not integration code.
    endpoint=propagate(initial,[0,21600],model,p,settings=finest,partials=False).states_m_mps[-1]
    rk_errors=[]
    for step in (20.,10.,5.):
        rk=rk4_endpoint(initial,21600.,step,model,p)
        rk_errors.append(float(np.linalg.norm(rk[:3]-endpoint[:3])))
    ratio=rk_errors[0]/rk_errors[1]
    record("independent_RK4_6h",{"steps_s":[20,10,5],"endpoint_position_errors_m":rk_errors,
                                "coarse_to_middle_error_ratio":ratio},rk_errors[-1]<.003 and 8<ratio<25)

    # Full-arc finite differences independently reintegrate each column at three
    # physical perturbation scales. Report displacement error, not mixed-unit norms.
    fd_rows=[]
    for index in range(10):
        is_state=index<6
        column=reference.state_transition[:,:,index] if is_state else reference.parameter_sensitivity[:,:,index-6]
        first_h=100. if index<3 else (.01 if index<6 else (1e-6 if index==6 else 1e-8))
        trials=[]
        for factor in (1.,.1,.01):
            h=first_h*factor
            delta=np.zeros(6 if is_state else 4);delta[index if is_state else index-6]=h
            plus=propagate(initial+delta if is_state else initial,times,model,p if is_state else p+delta,settings=finest,partials=False)
            minus=propagate(initial-delta if is_state else initial,times,model,p if is_state else p-delta,settings=finest,partials=False)
            measured=(plus.states_m_mps-minus.states_m_mps)/2
            predicted=column*h
            metric=errors(measured,predicted)
            metric.update(perturbation=h,predicted_position_max_m=float(np.max(np.linalg.norm(predicted[:,:3],axis=1))))
            trials.append(metric)
        fd_rows.append({"column":("x0","y0","z0","vx0","vy0","vz0",*PARAMETER_NAMES)[index],"trials":trials})
        print(f"Full-arc derivative column {index+1}/10 complete",flush=True)
    fd_max=max(row["position_max_m"] for column in fd_rows for row in column["trials"])
    velocity_max=max(row["velocity_max_mps"] for column in fd_rows for row in column["trials"])
    record("full_arc_central_difference_partials",{"columns":fd_rows,"worst_displacement_error_m":fd_max,
                                                 "worst_velocity_displacement_error_mps":velocity_max},fd_max<1e-4 and velocity_max<1e-7)

    # Actual one-sided prediction errors should shrink quadratically before the
    # finite-precision floor: this tests all initial/force columns together.
    dx=np.array([100.,-70,40,.01,-.006,.003])
    dp=np.array([1e-6,1e-8,-2e-8,3e-8])
    linear=np.einsum("nij,j->ni",reference.state_transition,dx)+np.einsum("nik,k->ni",reference.parameter_sensitivity,dp)
    taylor=[]
    for factor in (1.,.1,.01):
        trial=propagate(initial+factor*dx,times,model,p+factor*dp,settings=finest,partials=False)
        metric=errors(trial.states_m_mps-reference.states_m_mps,factor*linear)
        taylor.append({"factor":factor,**metric})
    ratios=[taylor[k]["position_rms_m"]/taylor[k+1]["position_rms_m"] for k in (0,1)]
    record("shrinking_perturbation_prediction",{"trials":taylor,"successive_rms_ratios":ratios},all(30<x<300 for x in ratios))

    # Chain rule is checked with independent half-arc initializations.
    first=propagate(initial,[0,43200],model,p,settings=finest)
    second=propagate(first.states_m_mps[-1],[43200,86400],model,p,initial_time_s=43200,settings=finest)
    composed_phi=second.state_transition[-1]@first.state_transition[-1]
    composed_s=second.state_transition[-1]@first.parameter_sensitivity[-1]+second.parameter_sensitivity[-1]
    scale=np.array([26560000.]*3+[np.sqrt(MU_EARTH/26560000.)]*3)
    phi_error=float(np.max(np.abs((composed_phi-reference.state_transition[-1])*scale[None,:]/scale[:,None])))
    sensitivity_error=float(np.max(np.abs((composed_s-reference.parameter_sensitivity[-1])*PARAMETER_SCALES[None,:]/scale[:,None])))
    j=np.block([[np.zeros((3,3)),np.eye(3)],[-np.eye(3),np.zeros((3,3))]])
    phi=reference.state_transition[-1]*scale[None,:]/scale[:,None]
    symplectic_error=float(np.max(np.abs(phi.T@j@phi-j)))
    record("transition_chain_and_symplectic_identity",{"scaled_transition_chain_error":phi_error,
             "scaled_sensitivity_chain_error":sensitivity_error,"scaled_symplectic_error":symplectic_error},
           max(phi_error,sensitivity_error,symplectic_error)<1e-8)
    back=propagate(reference.states_m_mps[-1],[86400,0],model,p,initial_time_s=86400,settings=finest,partials=False)
    backward_error=float(np.linalg.norm(back.states_m_mps[-1,:3]-initial[:3]))
    record("24h_backward_return",{"position_error_m":backward_error},backward_error<.003)
    report.update(status="pass",elapsed_s=time.perf_counter()-started)
    (folder/"audit.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":"pass","elapsed_s":report["elapsed_s"],"report":str(folder/"audit.json")}),flush=True)


if __name__ == "__main__":
    main()
