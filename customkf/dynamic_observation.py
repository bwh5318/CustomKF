"""Dynamically consistent state/partial interpolation and full observation closure.

Every nonlinear trial reintegrates its initial states. Positions and velocities
come from the same Hermite polynomial, as do state-transition positions and
velocities. No SP3/precise-clock access is provided by this module.
"""
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from .propagation import propagate, IntegrationSettings
from .measurement import geometry
from .antenna import corrections
from .station_models import troposphere
from .preprocess import ALPHA, BETA, LAMBDA1, LAMBDA2, C
from .broadcast import clock, select_record

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


# The stage-5 origin, 2 Aug 2026 11:59:50 GPST (customkf.stage5_pilot.ORIGIN): day 214, second 43190.
LEGACY_ORIGIN_NS = 1469707190000000000


def _origin_ns(products):
    while not hasattr(products, "origin_ns") and hasattr(products, "base"):
        products = products.base
    return getattr(products, "origin_ns", None)


def troposphere_day(products, row, receive_s):
    """Day-of-year argument of the troposphere model at the receive epoch (OBS-01 defect fix, 1 Oct 2026).

    The epoch is the receive time `receive_s` seconds after the origin, on the GPST calendar of the origin, as
    `origin_doy + (origin_second_of_day + receive_s)/86400`. The count runs on past the end of a year, so it is
    continuous within an arc. Dated rows carry the origin's day of year and second of day (they are written by the
    preparers from the same GPST origin as the products); the result is then exactly the date-aware expression of
    claude.tools.dated_observation. Rows without those fields are legacy stage-5 rows, defined relative to the
    stage-5 origin; they keep exactly the former expression and are refused on any other origin. Before this fix,
    every row was given 2 August seasonality.
    """
    if "origin_doy" in row or "origin_second_of_day" in row:
        return row["origin_doy"]+(row["origin_second_of_day"]+receive_s)/86400
    if _origin_ns(products) != LEGACY_ORIGIN_NS:
        raise ValueError("Undated observation row away from the stage-5 origin: troposphere day of year unknown")
    return 214+(43190+receive_s)/86400


def modeled_link(products, row, receiver_cal, satellite_cal, ephemeris, receiver_clock,
                 satellite_clock, wet, ambiguity, windup_reference=None, details=False):
    g = geometry(products, row["satellite"], row["time_s"], row["receiver_xyz"], receiver_clock)
    hydro, mw = troposphere(row["receiver_xyz"], g["elevation_rad"], troposphere_day(products, row, g["receive_s"]))
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
    g, _ = evaluate(products)
    sat = row["satellite"]
    rotation = products.epoch.celestial_to_terrestrial(g["receive_s"])
    u = rotation.T@g["los_ecef"]
    velocity = g["satellite_inertial"][3:]
    rate = products.clock_rate(sat, g["transmit_s"])
    principal = (1+rate)*(u@products.trajectories[sat].partial(g["transmit_s"])[:3])/(1+u@velocity/C)
    jac = np.empty((2, 6))
    for k in range(6):
        h = 10. if k < 3 else .01
        d = np.eye(6)[k]*h
        jac[:, k] = principal[k]+(evaluate(PerturbedProducts(products, sat, d))[1]-
                     evaluate(PerturbedProducts(products, sat, -d))[1])/(2*h)
    t = g["receive_s"]
    receiver_velocity = (products.epoch.celestial_to_terrestrial(t+.5).T@row["receiver_xyz"]-
                         products.epoch.celestial_to_terrestrial(t-.5).T@row["receiver_xyz"])
    range_rate = -u@(velocity-receiver_velocity)/(C+u@velocity)
    clock_jac = (1+rate)*(1+range_rate)+(evaluate(products, receiver_clock+10.)[1]-evaluate(products, receiver_clock-10.)[1])/20.
    return jac, clock_jac
