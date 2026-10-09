"""Fixed precise-orbit/clock inputs for Stage 3; no orbit parameters are fitted."""
from pathlib import Path
import numpy as np
from scipy.interpolate import BarycentricInterpolator
from .rinex import text_stream
from .sp3 import read_sp3, epoch_tag


def read_clocks(paths,*,missing_time_system=None):
    rows={}
    for path in paths:
        with text_stream(path) as stream:
            first=stream.readline()
            if "RINEX VERSION / TYPE" not in first or first[20:21]!="C":raise ValueError("Not RINEX clocks")
            time_system=None
            for _ in range(2000):
                line=stream.readline()
                if "TIME SYSTEM ID" in line:time_system=line[:60].strip()
                if "END OF HEADER" in line:break
            else:raise ValueError("Truncated clock header")
            if time_system is None:time_system=missing_time_system
            if time_system!="GPS":raise ValueError("Explicit GPS clocks required")
            for count,line in enumerate(stream):
                if count>2000000:raise ValueError("Clock record budget exceeded")
                if not line.startswith("AS G"):continue
                f=line.split()
                if len(f)<10:raise ValueError("Truncated satellite clock")
                tag=epoch_tag("* "+" ".join(f[2:8]));value=float(f[9])
                if not np.isfinite(value):raise ValueError("Nonfinite satellite clock")
                sat=rows.setdefault(f[1],{})
                if tag in sat and sat[tag]!=value:raise ValueError("Conflicting duplicate clock")
                sat[tag]=value
    return {sat:(np.array(sorted(data),dtype=np.int64),np.array([data[t] for t in sorted(data)])) for sat,data in rows.items()}


def polynomial_state(times,positions,t):
    """Local deterministic barycentric position and derivative; no extrapolation."""
    if len(times)<11 or t<times[0] or t>times[-1]:raise ValueError("Orbit interpolation lacks bracketing coverage")
    k=int(np.searchsorted(times,t));first=max(0,min(k-5,len(times)-11))
    x=(times[first:first+11]-t)/1000.
    if np.max(np.diff(x))>1.001:raise ValueError("Orbit interpolation crosses a gap")
    weights=np.array([1/np.prod(x[i]-np.delete(x,i)) for i in range(11)])
    poly=BarycentricInterpolator(x,positions[first:first+11],wi=weights,axis=0)
    return np.r_[poly(0.),poly.derivative(0.)/1000.]


class PreciseProducts:
    def __init__(self,orbit_paths,clock_paths,gps_epoch_ns,eop,*,missing_clock_time_system=None):
        from .frames import FrameEpoch
        self.epoch=epoch=FrameEpoch(gps_epoch_ns,eop)
        self.origin_ns=int(gps_epoch_ns)
        records={};frames=set();rotations={}
        for path in orbit_paths:
            product=read_sp3(path);frames.add(product.frame)
            for row in product.samples.values():
                if row.xyz_m is None or row.maneuver or row.orbit_predicted:continue
                t=(row.epoch_ns-self.origin_ns)/1e9
                if t not in rotations:rotations[t]=epoch.celestial_to_terrestrial(t)
                position=rotations[t].T@row.xyz_m
                sat=records.setdefault(row.sat,{})
                if t in sat and np.linalg.norm(sat[t]-position)>1e-6:raise ValueError("Conflicting orbit boundary")
                sat[t]=position
        if len(frames)!=1:raise ValueError("Mixed orbit reference frames")
        self.frame=frames.pop()
        self.orbits={sat:(np.array(sorted(data)),np.array([data[t] for t in sorted(data)])) for sat,data in records.items()}
        self.clocks=read_clocks(clock_paths,missing_time_system=missing_clock_time_system)

    def state(self,satellite,t):
        return polynomial_state(*self.orbits[satellite],t)

    def clock(self,satellite,t):
        tags,values=self.clocks[satellite]
        seconds=(tags-self.origin_ns)/1e9
        k=int(np.searchsorted(seconds,t,side="right"))-1
        if k<0 or k>=len(seconds)-1 or seconds[k+1]-seconds[k]>300.01:
            raise ValueError("Satellite clock gap/extrapolation")
        f=(t-seconds[k])/(seconds[k+1]-seconds[k])
        return float(values[k]*(1-f)+values[k+1]*f)
