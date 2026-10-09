"""Small transparent square-root (pivoted QR) iterative dynamic SP3 fitting.

No normal matrix inversion, robust residual deletion or fitted frame alignment.
Only explicitly supplied training positions enter initialization and the solve.
"""
from dataclasses import dataclass
import numpy as np
from scipy.linalg import qr,solve_triangular
from scipy.interpolate import BarycentricInterpolator
from .propagation import propagate,IntegrationSettings


@dataclass
class FitResult:
    initial_state:np.ndarray
    parameters:np.ndarray
    iterations:list
    converged:bool
    rank:int
    singular_values:np.ndarray


def initial_state_from_positions(times,positions):
    if times[0]!=0 or len(times)<10:raise ValueError("Need at least 10 training positions including t0")
    # Fixed deterministic weights; barycentric interpolation of 10 training samples.
    x=times[:10]/10000.
    w=np.array([1/np.prod(x[k]-np.delete(x,k)) for k in range(len(x))])
    polynomial=BarycentricInterpolator(x,positions[:10],wi=w,axis=0)
    return np.r_[positions[0],polynomial.derivative(0.)/10000.]


def fit_orbit(times,positions,model,*,initial=None,parameters=None,max_iterations=6,
              settings=IntegrationSettings(),callback=None):
    times=np.asarray(times,dtype=float);positions=np.asarray(positions,dtype=float)
    if times.ndim!=1 or positions.shape!=(len(times),3) or not np.isfinite(positions).all() or np.any(np.diff(times)<=0):
        raise ValueError("Invalid training data")
    state=initial_state_from_positions(times,positions) if initial is None else np.asarray(initial,dtype=float).copy()
    p=np.r_[-1e-7,np.zeros(len(model.parameter_scales)-1)] if parameters is None else np.asarray(parameters,dtype=float).copy()
    scales=np.r_[np.full(3,100.),np.full(3,.01),model.parameter_scales]
    history=[];converged=False;rank=0;singular=np.empty(0)
    for iteration in range(max_iterations):
        solution=propagate(state,times,model,p,settings=settings)
        residual=positions-solution.states_m_mps[:,:3]
        design=np.concatenate((solution.state_transition[:,:3,:],solution.parameter_sensitivity[:,:3,:]),axis=2).reshape(-1,len(scales))
        design=design*scales
        q,r,pivot=qr(design,mode="economic",pivoting=True)
        singular=np.linalg.svd(design,compute_uv=False)
        rank=int(np.sum(singular>singular[0]*1e-11))
        if rank<len(scales):raise ValueError("Rank-deficient dynamic fit; parameters not silently regularized")
        step=np.zeros(len(scales));step[pivot]=solve_triangular(r,q.T@residual.ravel())
        correction=step*scales
        predicted_update_rms=float(np.sqrt(np.mean(np.sum((design@step).reshape(-1,3)**2,axis=1))))
        cost=float(np.mean(np.sum(residual**2,axis=1)))
        accepted=False
        for alpha in (1.,.5,.25,.125):
            # Keep the same augmented integration/error norm for objective and
            # trial evaluations, including near penumbra transitions.
            proposed=propagate(state+alpha*correction[:6],times,model,p+alpha*correction[6:],settings=settings)
            next_cost=float(np.mean(np.sum((positions-proposed.states_m_mps[:,:3])**2,axis=1)))
            if next_cost<=cost+1e-12:
                state+=alpha*correction[:6];p+=alpha*correction[6:];accepted=True;break
        record={"iteration":iteration,"training_rms_before_m":cost**.5,"training_rms_after_m":next_cost**.5,
                "step_fraction":alpha,"accepted":accepted,"rank":rank,"scaled_condition":float(singular[0]/singular[-1]),
                "predicted_update_rms_m":predicted_update_rms,
                "initial_state":state.tolist(),"parameters":p.tolist()}
        history.append(record)
        if callback:callback(record)
        if not accepted:
            # Roundoff floor is distinct from failure to accept a material update.
            converged=predicted_update_rms<1e-4 and abs(next_cost**.5-cost**.5)<1e-5
            break
        if abs(cost**.5-next_cost**.5)<1e-5:
            converged=True;break
    return FitResult(state,p,history,converged,rank,singular)
