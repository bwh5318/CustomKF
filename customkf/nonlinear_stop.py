"""Physical-step and linearized-objective stationarity, separate from line search.

Returning true permits retaining the current accepted iterate. It never accepts
a worse trial. Thresholds use the existing 1 mm trajectory and objective-change
scales; this is a local numerical stopping rule, not orbit-accuracy validation.
"""
import math


def model_reduction(blocks,constraints,step):
    """Evaluate 2 r.T A dx - ||A dx||^2 without subtracting nearly equal costs."""
    n=constraints[0].shape[1];offset=n;reduction=0.;norm2=0.
    for b in blocks:
        k=b.local.shape[1];d=(b.retained@step[:n]+b.local@step[offset:offset+k])/b.sigma
        y=b.target/b.sigma;reduction+=float(2*y@d-d@d);norm2+=float(d@d);offset+=k
    c,y,s=constraints;d=c@step[:n]/s;y=y/s
    return reduction+float(2*y@d-d@d),norm2+float(d@d)


def stationary(step_bound_m,cost,predicted_reduction,direction_norm_squared):
    values=(step_bound_m,cost,predicted_reduction,direction_norm_squared)
    if not all(math.isfinite(v) and v>=0 for v in values):return False
    threshold=max(1e-5,1e-8*cost)
    return step_bound_m<.001 and predicted_reduction<threshold and direction_norm_squared<threshold
