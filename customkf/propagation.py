"""Scaled DOP853 state/variational integration for smooth Stage 1 test forces.

Time is elapsed uniform coordinate seconds, never a naive UTC date. Absolute
GPST/TT/UT1 and terrestrial frame transformations are not implemented here.
Returned states and derivatives are SI; internal coordinates are dimensionless.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import time
import numpy as np
from scipy.integrate import solve_ivp

from .dynamics import PARAMETER_SCALES, TestForceModel


class PropagationStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class IntegrationSettings:
    max_step_s: float = 120.
    rtol: float = 1e-11
    position_atol_m: float = 1e-5
    velocity_atol_mps: float = 1e-9
    scaled_partial_atol: float = 1e-12
    max_evaluations: int = 200000

    def validate(self):
        numbers = (self.max_step_s,self.rtol,self.position_atol_m,self.velocity_atol_mps,self.scaled_partial_atol)
        if not np.isfinite(numbers).all() or min(numbers) <= 0 or not 2.3e-14 <= self.rtol <= 1e-3:
            raise ValueError("Invalid integration tolerances; do not rely on SciPy clipping rtol")
        if not isinstance(self.max_evaluations,int) or not 1 <= self.max_evaluations <= 2000000:
            raise ValueError("Invalid evaluation budget")


@dataclass
class PropagationResult:
    times_s: np.ndarray
    states_m_mps: np.ndarray
    state_transition: np.ndarray | None
    parameter_sensitivity: np.ndarray | None
    evaluations: int
    elapsed_s: float


def propagate(initial_state, output_times_s, model=None, parameters=None, *, initial_time_s=0.,
              settings=IntegrationSettings(), partials=True, stop_file=None):
    """Integrate at most 48 hours, forward or backward, at explicit output times.

    Phi[i,j] = d x_i(t)/d x_j(t0); S[i,k] = d x_i(t)/d p_k for fixed x(t0).
    No impulses/discontinuous forces are supported: split and restart such arcs.
    """
    settings.validate()
    model = TestForceModel() if model is None else model
    initial = np.asarray(initial_state,dtype=float)
    times = np.asarray(output_times_s,dtype=float)
    parameter_scales=np.asarray(getattr(model,"parameter_scales",PARAMETER_SCALES),dtype=float)
    if parameter_scales.ndim!=1 or not np.isfinite(parameter_scales).all() or np.any(parameter_scales<=0):
        raise ValueError("Invalid force-parameter scaling")
    count=len(parameter_scales)
    p = np.zeros(count) if parameters is None else np.asarray(parameters,dtype=float).copy()
    if p.shape!=(count,):raise ValueError("Force parameter count does not match model")
    if initial.shape != (6,) or not np.isfinite(initial).all() or times.ndim != 1 or not len(times) or len(times)>20000 or not np.isfinite(times).all() or not np.isfinite(initial_time_s):
        raise ValueError("Invalid initial state or output times")
    model.evaluate(initial_time_s,initial,p,partials=False)
    direction = np.sign(times[-1]-initial_time_s)
    if direction == 0 or np.any(direction*(times-initial_time_s)<0) or np.any(direction*np.diff(times)<=0) or abs(times[-1]-initial_time_s)>172800:
        raise ValueError("Require strictly ordered times on one side of start, with a nonzero arc <=48 hours")
    length = 26560000.
    speed = np.sqrt(model.mu_m3ps2/length)
    scale = np.array([length]*3+[speed]*3)
    y0 = initial/scale
    atol = np.array([settings.position_atol_m/length]*3+[settings.velocity_atol_mps/speed]*3)
    if partials:
        y0 = np.r_[y0,np.eye(6).ravel(),np.zeros(6*count)]
        atol = np.r_[atol,np.full(36+6*count,settings.scaled_partial_atol)]
    stop_path = stop_file if stop_file is not None else os.environ.get("CUSTOMKF_STOP_FILE")
    stop_path = Path(stop_path) if stop_path else None
    calls = 0
    def rhs(t,y):
        nonlocal calls
        calls += 1
        if calls > settings.max_evaluations:
            raise PropagationStopped("Right-hand-side evaluation budget exceeded")
        if (calls == 1 or calls%32 == 0) and stop_path is not None and stop_path.exists():
            raise PropagationStopped("Resource watchdog requested a cooperative stop")
        state = y[:6]*scale
        acc, dr, dv, dp = model.evaluate(t,state,p,partials=partials)
        out = np.empty_like(y)
        out[:6] = np.r_[state[3:],acc]/scale
        if partials:
            system = np.zeros((6,6))
            system[:3,3:] = np.eye(3)
            system[3:,:3], system[3:,3:] = dr,dv
            scaled_system = system*scale[None,:]/scale[:,None]
            out[6:42] = (scaled_system@y[6:42].reshape(6,6)).ravel()
            source = np.zeros((6,count))
            source[3:] = dp
            out[42:] = (scaled_system@y[42:].reshape(6,count)+source*parameter_scales[None,:]/scale[:,None]).ravel()
        return out
    started = time.perf_counter()
    solution = solve_ivp(rhs,(initial_time_s,float(times[-1])),y0,method="DOP853",t_eval=times,
                         max_step=settings.max_step_s,rtol=settings.rtol,atol=atol)
    if not solution.success or solution.status != 0 or solution.y.shape != (len(y0),len(times)) or not np.isfinite(solution.y).all():
        raise RuntimeError(f"Incomplete propagation: {solution.message}")
    states = solution.y[:6].T*scale
    phi = sensitivity = None
    if partials:
        phi = solution.y[6:42].T.reshape(-1,6,6)*scale[None,:,None]/scale[None,None,:]
        sensitivity = solution.y[42:].T.reshape(-1,6,count)*scale[None,:,None]/parameter_scales[None,None,:]
    return PropagationResult(times.copy(),states,phi,sensitivity,calls,time.perf_counter()-started)
