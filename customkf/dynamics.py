"""Stage 1 smooth inertial test forces in SI units; not an IGS force model.

J2's symmetry axis is the fixed inertial z axis. Third bodies are prescribed
fixed inertial positions, deliberately useful as reproducible test problems.
Parameters are absolute [J2, ax, ay, az], the last three in m/s^2.
"""
from dataclasses import dataclass
import numpy as np

MU_EARTH = 3.986004418e14
R_EARTH = 6378136.3
PARAMETER_NAMES = ("j2", "ax_mps2", "ay_mps2", "az_mps2")
PARAMETER_SCALES = np.array([1e-3, 1e-7, 1e-7, 1e-7])


@dataclass(frozen=True)
class FixedThirdBody:
    mu_m3ps2: float
    position_m: tuple

    def __post_init__(self):
        b = np.asarray(self.position_m, dtype=float)
        if not np.isfinite(self.mu_m3ps2) or self.mu_m3ps2 <= 0 or b.shape != (3,) or not np.isfinite(b).all() or np.linalg.norm(b) <= 1:
            raise ValueError("Invalid fixed third body")
        object.__setattr__(self, "position_m", tuple(float(x) for x in b))


@dataclass(frozen=True)
class TestForceModel:
    mu_m3ps2: float = MU_EARTH
    radius_m: float = R_EARTH
    third_bodies: tuple = ()

    def __post_init__(self):
        if not np.isfinite([self.mu_m3ps2,self.radius_m]).all() or self.mu_m3ps2 <= 0 or self.radius_m <= 0:
            raise ValueError("GM and reference radius must be positive finite SI values")
        if not all(isinstance(b, FixedThirdBody) for b in self.third_bodies):
            raise ValueError("Only explicit fixed third bodies are supported in Stage 1")
        object.__setattr__(self, "third_bodies", tuple(self.third_bodies))

    def evaluate(self, t_s, state_m_mps, parameters, *, partials=True):
        state, p = np.asarray(state_m_mps,dtype=float), np.asarray(parameters,dtype=float)
        if state.shape != (6,) or p.shape != (4,) or not np.isfinite(state).all() or not np.isfinite(p).all() or not np.isfinite(t_s):
            raise ValueError("Require finite time, six SI state values and four parameters")
        r = state[:3]
        q = float(r@r)
        s = np.sqrt(q)
        if s <= self.radius_m:
            raise ValueError("Satellite inside reference sphere; check state units")
        mu = self.mu_m3ps2
        acceleration = -mu*r/s**3+p[1:]
        u = 5*r[2]**2/q
        w = r*np.array([u-1,u-1,u-3])
        factor = 1.5*mu*self.radius_m**2/s**5
        j2_unit = factor*w
        acceleration = acceleration+p[0]*j2_unit
        jac = None
        if partials:
            jac = mu*(3*np.outer(r,r)/s**5-np.eye(3)/s**3)
            du = -10*r[2]**2*r/q**2
            du[2] += 10*r[2]/q
            dw = np.diag([u-1,u-1,u-3])+np.outer(r,du)
            jac += p[0]*factor*(dw-5*np.outer(w,r)/q)
        for body in self.third_bodies:
            b = np.asarray(body.position_m)
            delta = b-r
            distance, origin_distance = np.linalg.norm(delta), np.linalg.norm(b)
            if distance <= 1:
                raise ValueError("Third-body singularity")
            # Direct satellite attraction minus acceleration of the origin.
            acceleration += body.mu_m3ps2*(delta/distance**3-b/origin_distance**3)
            if partials:
                jac += body.mu_m3ps2*(3*np.outer(delta,delta)/distance**5-np.eye(3)/distance**3)
        if not np.isfinite(acceleration).all() or (partials and not np.isfinite(jac).all()):
            raise ValueError("Nonfinite force evaluation")
        parameter_jac = np.column_stack((j2_unit,np.eye(3))) if partials else None
        return acceleration, jac, np.zeros((3,3)) if partials else None, parameter_jac

    def potential_m2ps2(self, position_m, parameters):
        """Specific potential for independent conservation/gradient checks."""
        r, p = np.asarray(position_m,dtype=float), np.asarray(parameters,dtype=float)
        s = np.linalg.norm(r)
        value = -self.mu_m3ps2/s*(1-p[0]*(self.radius_m/s)**2*(3*(r[2]/s)**2-1)/2)-p[1:]@r
        for body in self.third_bodies:
            b = np.asarray(body.position_m)
            value += -body.mu_m3ps2/np.linalg.norm(b-r)+body.mu_m3ps2*(r@b)/np.linalg.norm(b)**3
        return float(value)
