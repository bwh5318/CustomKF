"""Independent algebraic elliptic Kepler solution, used only for validation."""
import numpy as np
from customkf.dynamics import MU_EARTH


def kepler_states(times, *, a=26560000., eccentricity=.1, mu=MU_EARTH):
    times = np.asarray(times,dtype=float)
    e = eccentricity
    mean = np.remainder(np.sqrt(mu/a**3)*times+.43+np.pi,2*np.pi)-np.pi
    anomaly = mean.copy()
    for _ in range(30):
        correction = (anomaly-e*np.sin(anomaly)-mean)/(1-e*np.cos(anomaly))
        anomaly -= correction
        if np.max(np.abs(correction))<2e-15:
            break
    else:
        raise AssertionError("Kepler oracle failed to converge")
    c,s = np.cos(anomaly),np.sin(anomaly)
    b = np.sqrt(1-e*e)
    positions = a*np.column_stack((c-e,b*s,np.zeros_like(c)))
    velocities = np.sqrt(mu/a)/(1-e*c)[:,None]*np.column_stack((-s,b*c,np.zeros_like(c)))
    ci,si = np.cos(np.deg2rad(55)),np.sin(np.deg2rad(55))
    co,so = np.cos(.61),np.sin(.61)
    rotation = np.array([[co,-so*ci,so*si],[so,co*ci,-co*si],[0,si,ci]])
    return np.column_stack((positions@rotation.T,velocities@rotation.T))


def rk4_endpoint(initial, duration_s, step_s, model, parameters):
    """Independent fixed-step classical RK4, validation only; no partials."""
    state=np.array(initial,dtype=float)
    steps=int(round(duration_s/step_s))
    if steps*step_s != duration_s:
        raise ValueError("Oracle interval must divide exactly")
    def rhs(t,x):
        return np.r_[x[3:],model.evaluate(t,x,parameters,partials=False)[0]]
    for k in range(steps):
        t=k*step_s
        a=rhs(t,state)
        b=rhs(t+step_s/2,state+step_s*a/2)
        c=rhs(t+step_s/2,state+step_s*b/2)
        d=rhs(t+step_s,state+step_s*c)
        state += step_s*(a+2*b+2*c+d)/6
    return state
