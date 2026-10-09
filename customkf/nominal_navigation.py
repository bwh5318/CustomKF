"""Explicit retrospective nominal-LNAV profile for the next bounded fixture.

The data cutoff is independent of orbit epoch. Unknown receipt timestamps remain
unknown; file membership alone never certifies rapid-vintage availability.
"""
import numpy as np
from .broadcast import select_fit_record, position, clock
from .dynamic_observation import DynamicProducts
from .diagnose_stage5 import offset_inertial


def corrected_state(records,epoch,ephemeris,calibration,origin_ns,cutoff_ns):
    record=select_fit_record(records,origin_ns,available_before_ns=cutoff_ns)
    def com(t):
        tag=origin_ns+int(round(t*1e9))
        apc=epoch.celestial_to_terrestrial(t).T@position(record,tag)
        sun,_=ephemeris.sun_moon_m(epoch.tdb_seconds(t));r=apc.copy()
        for _ in range(3):r=apc-offset_inertial(r,sun,calibration)
        return r
    return np.r_[com(0),com(.5)-com(-.5)]


class NominalProducts(DynamicProducts):
    def __init__(self,*args,available_before_ns):
        super().__init__(*args);self.available_before_ns=available_before_ns

    def record(self,sat,t):
        return select_fit_record(self.records[sat],self.origin_ns+int(round(t*1e9)),available_before_ns=self.available_before_ns)

    def clock(self,sat,t):
        return clock(self.record(sat,t),self.origin_ns+int(round(t*1e9)))

    def clock_rate(self,sat,t):
        r=self.record(sat,t);dt=(self.origin_ns+int(round(t*1e9))-r["gps_ns"])/1e9
        return r["af1"]+2*r["af2"]*dt
