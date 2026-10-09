# Isolated date-aware adaptation; see dated_module_origins.json.
"""Dynamically consistent state/partial interpolation and full observation closure.

Every nonlinear trial reintegrates its initial states. Positions and velocities
come from the same Hermite polynomial, as do state-transition positions and
velocities. No SP3/precise-clock access is provided by this module.
"""
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from customkf.propagation import propagate, IntegrationSettings
from customkf.measurement import geometry
from customkf.antenna import corrections
from customkf.station_models import troposphere
from customkf.preprocess import ALPHA, BETA, LAMBDA1, LAMBDA2, C
from customkf.broadcast import clock, select_record

SETTINGS = IntegrationSettings(max_step_s=60., rtol=1e-12, position_atol_m=1e-7,
                               velocity_atol_mps=1e-11, scaled_partial_atol=1e-13)


class Trajectory:
    def __init__(self, initial, model, duration, step=15., settings=SETTINGS):
        times = np.r_[np.arange(0., duration, step), duration]
        p = np.r_[-1e-7, np.zeros(len(model.parameter_scales)-1)]
        result = propagate(initial, times, model, p, settings=settings)
        self.position = CubicHermiteSpline(times, result.states_m_mps[:, :3], result.states_m_mps[:, 3:], extrapolate=False)
        self.phi_position = CubicHermiteSpline(times, result.state_transition[:, :3], result.state_transition[:, 3:], extrapolate=False)
        self.duration = duration

    def state(self, t):
        if not 0 <= t <= self.duration:
            raise ValueError("Dynamic trajectory extrapolation refused")
        return np.r_[self.position(t), self.position(t, 1)]

    def partial(self, t):
        if not 0 <= t <= self.duration:
            raise ValueError("Dynamic partial extrapolation refused")
        return np.vstack([self.phi_position(t), self.phi_position(t, 1)])


class DynamicProducts:
    def __init__(self, epoch, origin_ns, records, trajectories):
        self.epoch, self.origin_ns, self.records, self.trajectories = epoch, origin_ns, records, trajectories

    def state(self, sat, t):
        return self.trajectories[sat].state(t)

    def clock(self, sat, t):
        tag = self.origin_ns+int(round(t*1e9))
        records = self.records[sat]
        record = select_record(records, tag) if isinstance(records, list) else records
        return clock(record, tag)

    def clock_rate(self, sat, t):
        tag = self.origin_ns+int(round(t*1e9))
        records = self.records[sat]
        record = select_record(records, tag) if isinstance(records, list) else records
        return record["af1"]+2*record["af2"]*((tag-record["gps_ns"])/1e9)


class PerturbedProducts:
    """Tangent-trajectory perturbation for the local measurement Jacobian only.

    Independent derivative validation must instead reintegrate plus/minus states.
    """
    def __init__(self, products, sat, delta):
        self.base, self.sat, self.delta, self.epoch = products, sat, delta, products.epoch

    def state(self, sat, t):
        state = self.base.state(sat, t)
        return state+self.base.trajectories[sat].partial(t)@self.delta if sat == self.sat else state

    def clock(self, sat, t):
        return self.base.clock(sat, t)


# Optional a-priori tropospheric gradients (1 Oct 2026; Opus_Fork/gradients.py, experiments/gradients/PROTOCOL.md):
# GRADIENT(products, row, g) -> slant delay (m), added to the hydrostatic term, so it enters code, phase and the
# correction stencils of the measurement Jacobian. None (the default) leaves the model exactly as before.
GRADIENT = None


def modeled_link(products, row, receiver_cal, satellite_cal, ephemeris, receiver_clock,
                 satellite_clock, wet, ambiguity, windup_reference=None, details=False):
    g = geometry(products, row["satellite"], row["time_s"], row["receiver_xyz"], receiver_clock)
    hydro, mw = troposphere(row["receiver_xyz"], g["elevation_rad"], row["origin_doy"]+(row["origin_second_of_day"]+g["receive_s"])/86400)
    if GRADIENT is not None:
        hydro = hydro+GRADIENT(products, row, g)
    sun, _ = ephemeris.sun_moon_m(products.epoch.tdb_seconds(g["transmit_s"]))
    antenna, windup = corrections(g, row["receiver_xyz"], receiver_cal, satellite_cal, sun,
                                  products.epoch.celestial_to_terrestrial(g["receive_s"]))
    if windup_reference is not None:
        windup += np.floor(windup_reference-windup+.5)
    base = g["modeled_code_without_trop_m"]+hydro+antenna-satellite_clock+mw*wet
    phase = base+(ALPHA*LAMBDA1+BETA*LAMBDA2)*windup+ambiguity
    if details:
        state = g["satellite_inertial"]
        small = g["shapiro_m"]+2*np.dot(state[:3],state[3:])/C+hydro+antenna+mw*wet
        return g, np.array([small, small+(ALPHA*LAMBDA1+BETA*LAMBDA2)*windup])
    return np.array([base, phase]), mw, windup, g["elevation_rad"]


OUT_OF_DOMAIN = "ANTEX angular extrapolation"


def _finite(value):
    value = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(value)):
        raise ValueError("Non-finite correction sample or derivative in a measurement stencil")
    return value


def correction_difference(sample, unit, h, minimum, base):
    """Central difference (sample(d) - sample(-d)) / (2h), d = unit*h, of the small corrections on a tangent stencil.

    Hardened 30 Sep 2026 (Sol review SOL-01; untouched-date amendment A3). The standard step is evaluated first,
    with exactly the former expression, so the result is bitwise identical wherever it is valid. Only when a stencil
    sample leaves a model's calibrated domain (the strict ANTEX refusal) is the symmetric step halved, down to
    `minimum`. The evaluator itself stays strict; an out-of-domain unperturbed observation is refused by the caller.

    Completed 1 Oct 2026 (Astra follow-up AF-02):
    - every result, and every sample of the fallback, must be finite, otherwise refused;
    - when no symmetric step fits, the one-sided fallback is second order (exact for quadratics:
      (-3 f0 + 4 f(m) - f(2m)) / 2m on the in-domain side);
    - the fallback is accepted only if its estimates at `minimum` and `minimum/2` agree (rtol 1e-6, atol 1e-10).
    """
    step = h
    while True:
        d = unit*step
        try:
            plus, minus = sample(d), sample(-d)
        except ValueError as error:
            if OUT_OF_DOMAIN not in str(error):
                raise
        else:
            return _finite((plus-minus)/(2*step))
        if step/2 < minimum:
            break
        step /= 2
    base = _finite(base)
    for side in (1., -1.):
        try:
            estimates = [side*(-3*base+4*_finite(sample(side*unit*m))-_finite(sample(2*side*unit*m)))/(2*m)
                         for m in (minimum, minimum/2)]
        except ValueError as error:
            if OUT_OF_DOMAIN not in str(error):
                raise
            continue
        if not np.allclose(estimates[0], estimates[1], rtol=1e-6, atol=1e-10):
            raise ValueError(OUT_OF_DOMAIN+": one-sided derivative is not stable between step sizes")
        return estimates[0]
    raise ValueError(OUT_OF_DOMAIN+": no in-domain derivative stencil")


def link_jacobian(products, row, receiver_cal, satellite_cal, ephemeris, receiver_clock,
                  satellite_clock, wet, ambiguity, windup_reference):
    """Full corrected-observation derivative, including implicit light time.

    Analytic implicit-light-time range/clock terms avoid differencing two
    20-Mm observables. Only small antenna, relativistic, atmospheric and wind-up
    corrections are differenced on tangent trajectories. Validation separately
    reintegrates perturbed initial states, including all force terms.
    """
    def evaluate(p, rc=receiver_clock):
        return modeled_link(p, row, receiver_cal, satellite_cal, ephemeris, rc,
                            satellite_clock, wet, ambiguity, windup_reference, details=True)
    g, base = evaluate(products)
    sat = row["satellite"]
    rotation = products.epoch.celestial_to_terrestrial(g["receive_s"])
    u = rotation.T@g["los_ecef"]
    velocity = g["satellite_inertial"][3:]
    rate = products.clock_rate(sat, g["transmit_s"])
    principal = (1+rate)*(u@products.trajectories[sat].partial(g["transmit_s"])[:3])/(1+u@velocity/C)
    jac = np.empty((2, 6))
    for k in range(6):
        h = 10. if k < 3 else .01
        jac[:, k] = principal[k]+correction_difference(
            lambda delta: evaluate(PerturbedProducts(products, sat, delta))[1], np.eye(6)[k], h, h/64, base)
    t = g["receive_s"]
    receiver_velocity = (products.epoch.celestial_to_terrestrial(t+.5).T@row["receiver_xyz"]-
                         products.epoch.celestial_to_terrestrial(t-.5).T@row["receiver_xyz"])
    range_rate = -u@(velocity-receiver_velocity)/(C+u@velocity)
    # Receiver-clock stencil through the same domain-aware difference (AF-02); bitwise as before where valid.
    clock_jac = (1+rate)*(1+range_rate)+correction_difference(
        lambda delta: evaluate(products, receiver_clock+delta)[1], 1., 10., 10./64, base)
    return jac, clock_jac
