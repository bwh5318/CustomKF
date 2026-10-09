"""Reference-only adjustable ECOM trajectories; production force model unchanged.

Same augmented propagation, tolerances and Hermite output as production Trajectory.
Retains force sensitivities already computed by propagate(). Never a POD seed.
"""
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.linalg import qr, solve_triangular
from customkf.propagation import propagate
from customkf.dynamic_observation import SETTINGS

INITIAL_P = np.array([-1e-7, 0., 0., 0., 0.])
VARIANTS = {"fixed": (), "d0": (0,), "ecom5": (0,1,2,3,4)}


class ForceTrajectory:
    def __init__(self, initial, model, duration, parameters):
        times = np.r_[np.arange(0.,duration,15.),duration]
        result = propagate(initial,times,model,parameters,settings=SETTINGS)
        self.position = CubicHermiteSpline(times,result.states_m_mps[:,:3],result.states_m_mps[:,3:],extrapolate=False)
        self.phi = CubicHermiteSpline(times,result.state_transition[:,:3],result.state_transition[:,3:],extrapolate=False)
        self.sensitivity = CubicHermiteSpline(times,result.parameter_sensitivity[:,:3],result.parameter_sensitivity[:,3:],extrapolate=False)
        self.duration = duration

    def state(self,t):
        if not 0<=t<=self.duration: raise ValueError("No extrapolation")
        return np.r_[self.position(t),self.position(t,1)]

    def partial(self,t):
        if not 0<=t<=self.duration: raise ValueError("No extrapolation")
        return np.vstack([self.phi(t),self.phi(t,1)])

    def force_partial(self,t):
        if not 0<=t<=self.duration: raise ValueError("No extrapolation")
        return np.vstack([self.sensitivity(t),self.sensitivity(t,1)])


def design_at(trajectory,times,active):
    return np.array([np.concatenate((trajectory.partial(t)[:3],trajectory.force_partial(t)[:3,active]),axis=1)
                     for t in times]).reshape(-1,6+len(active))


def solve_force(initial,times,positions,model,duration,variant,max_iterations=5):
    active = list(VARIANTS[variant]); times=np.asarray(times,float); positions=np.asarray(positions,float)
    if times.ndim!=1 or positions.shape!=(len(times),3) or not np.isfinite(positions).all() or np.any(np.diff(times)<=0):
        raise ValueError("Invalid training-only positions")
    state=np.array(initial,float).copy(); p=INITIAL_P.copy()
    scales=np.r_[[100.]*3,[.01]*3,np.asarray(model.parameter_scales)[active]]
    history=[]; trajectory=ForceTrajectory(state,model,duration,p)
    for iteration in range(max_iterations):
        residual=positions-np.array([trajectory.state(t)[:3] for t in times])
        design=design_at(trajectory,times,active)*scales
        singular=np.linalg.svd(design,compute_uv=False); rank=int(np.sum(singular>singular[0]*1e-11))
        if rank!=len(scales): raise ValueError(f"Rank deficient {variant}: {rank}/{len(scales)}")
        q,r,pivot=qr(design,mode="economic",pivoting=True)
        scaled=np.zeros(len(scales)); scaled[pivot]=solve_triangular(r,q.T@residual.ravel())
        delta=scaled*scales; direction=(design@scaled).reshape(-1,3)
        bound=float(max(np.linalg.norm(delta[:3])+duration*np.linalg.norm(delta[3:6]),np.max(np.linalg.norm(direction,axis=1))))
        predicted=float(np.sqrt(np.mean(np.sum(direction**2,axis=1)))); cost=float(np.sum(residual**2))
        record=dict(iteration=iteration,rank=rank,scaled_condition=float(singular[0]/singular[-1]),
                    training_rms_before_m=float(np.sqrt(cost/len(times))),predicted_update_rms_m=predicted,step_bound_m=bound)
        if bound<1e-4 and predicted<1e-5:
            record.update(termination="stationary",update_applied=False,step_fraction=0.,training_rms_after_m=record["training_rms_before_m"])
            history.append(record)
            inv=solve_triangular(r,np.eye(len(scales))); cp=inv@inv.T
            covariance=np.zeros_like(cp); covariance[np.ix_(pivot,pivot)]=cp
            covariance*=scales[:,None]*scales[None,:]
            return state,p,trajectory,history,covariance
        accepted=False
        for alpha in (1.,.5,.25,.125):
            trial_p=p.copy(); trial_p[active]+=alpha*delta[6:]
            trial=ForceTrajectory(state+alpha*delta[:6],model,duration,trial_p)
            error=positions-np.array([trial.state(t)[:3] for t in times]); cost2=float(np.sum(error**2))
            if cost2<=cost:
                state+=alpha*delta[:6]; p=trial_p; trajectory=trial; accepted=True; break
        record.update(termination="line_search",update_applied=accepted,step_fraction=alpha,
                      training_rms_after_m=float(np.sqrt(cost2/len(times))))
        history.append(record); print(record,flush=True)
        if not accepted: raise RuntimeError("No decreasing training-only step")
    raise RuntimeError("Force fit iteration cap; do not regularize or change model silently")
