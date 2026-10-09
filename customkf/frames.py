"""Explicit GPST -> TT/UTC/UT1 and IAU 2006/2000A rotations with pinned EOP.

No network access or extrapolation. EOP convention is the frozen USNO snapshot,
not an asserted historical rapid vintage. Subdaily EOP tides are opt-in through
EarthOrientation.subdaily (default None: daily interpolation only, unchanged).
"""
import erfa
import numpy as np
from scipy.interpolate import CubicSpline


class EarthOrientation:
    # Opt-in sub-daily EOP model (Opus 26 Sep 2026, see Opus_Fork/results/subdaily_eop_handoff/): a callable
    # MJD(UTC) -> (delta_x uas, delta_y uas, delta_UT1 us) added to every `at` result, e.g. the IERS 2010
    # ocean-tidal ORTHO_EOP in Opus_Fork/subdaily_eop.py. None (the default) leaves `at` bit-identical.
    # Assign it to an instance, or to the class wrapped in staticmethod().
    subdaily=None

    def __init__(self,path):
        rows=[]
        with open(path) as stream:
            for line in stream:
                if len(line)<125:continue
                try:
                    mjd=float(line[7:15])
                    if line[134:144].strip() and line[164:175].strip():
                        values=[float(line[a:b]) for a,b in ((134,144),(144,154),(154,165),(165,175),(175,185))]
                        source="B"
                    else:
                        if any(line[i]!="I" for i in (16,57,95)):continue
                        values=[float(line[a:b]) for a,b in ((18,27),(37,46),(58,68),(97,106),(116,125))]
                        source="A-observed"
                    rows.append((mjd,*values,source))
                except ValueError:continue
        self.table=np.array([r[:6] for r in rows],dtype=float)
        self.sources=[r[6] for r in rows]
        if len(rows)<2 or np.any(np.diff(self.table[:,0])<=0):raise ValueError("Invalid EOP table")

    def at(self,mjd):
        k=np.searchsorted(self.table[:,0],mjd,side="right")-1
        if k<0 or k>=len(self.table)-1 or self.table[k+1,0]-self.table[k,0]>1.01:
            raise ValueError("Missing observed EOP coverage; no extrapolation")
        a,b=self.table[k:k+2]
        fraction=(mjd-a[0])/(b[0]-a[0])
        result=a[1:]+(b[1:]-a[1:])*fraction
        def dat(day):
            y,m,d,f=erfa.jd2cal(2400000.5,day)
            return erfa.dat(y,m,d,f)
        # Interpolate continuous UT1-TAI, then restore the epoch's leap offset.
        da,db,dt=dat(a[0]),dat(b[0]),dat(mjd)
        result[2]=(a[3]-da)+(b[3]-db-a[3]+da)*fraction+dt
        if self.subdaily is not None:
            dx,dy,dut1=self.subdaily(mjd)
            result[0]+=dx*1e-6;result[1]+=dy*1e-6;result[2]+=dut1*1e-6
        return result


class FrameEpoch:
    def __init__(self,gps_epoch_ns,eop):
        if not isinstance(gps_epoch_ns,(int,np.integer)):raise ValueError("Require integer GPST nanoseconds")
        days,ns=divmod(int(gps_epoch_ns),86400*10**9)
        self.tt1=2444244.5+days
        self.tt2=(ns/1e9+51.184)/86400
        self.eop=eop

    def times(self,elapsed_s):
        tt1,tt2=self.tt1,self.tt2+float(elapsed_s)/86400
        tai1,tai2=erfa.tttai(tt1,tt2)
        utc1,utc2=erfa.taiutc(tai1,tai2)
        xp,yp,dut1,dx,dy=self.eop.at((utc1-2400000.5)+utc2)
        ut11,ut12=erfa.utcut1(utc1,utc2,dut1)
        return tt1,tt2,ut11,ut12,xp*erfa.DAS2R,yp*erfa.DAS2R,dx*erfa.DAS2R/1000,dy*erfa.DAS2R/1000

    def celestial_to_terrestrial(self,elapsed_s):
        tt1,tt2,ut11,ut12,xp,yp,dx,dy=self.times(elapsed_s)
        x,y,_=erfa.xys06a(tt1,tt2)
        x+=dx;y+=dy
        celestial=erfa.c2ixys(x,y,erfa.s06(tt1,tt2,x,y))
        polar=erfa.pom00(xp,yp,erfa.sp00(tt1,tt2))
        return erfa.c2tcio(celestial,erfa.era00(ut11,ut12),polar)

    def tdb_seconds(self,elapsed_s):
        tt1,tt2=self.tt1,self.tt2+float(elapsed_s)/86400
        correction=erfa.dtdb(tt1,tt2,0.,0.,0.,0.)
        return ((tt1-2451545.)+tt2)*86400+correction


class Environment:
    def __init__(self,epoch,ephemeris,duration_s,step_s=30.):
        self.epoch=epoch
        self.start=-120.;self.end=duration_s+120.
        grid=np.arange(self.start,self.end+step_s/2,step_s)
        matrices=np.array([epoch.celestial_to_terrestrial(t) for t in grid])
        bodies=np.array([ephemeris.sun_moon_m(epoch.tdb_seconds(t)) for t in grid])
        self.rotation=CubicSpline(grid,matrices,extrapolate=False)
        self.bodies=CubicSpline(grid,bodies,extrapolate=False)

    def at(self,t):
        if not self.start<=t<=self.end:raise ValueError("Environment interpolation outside arc")
        sun,moon=self.bodies(t)
        return self.rotation(t),sun,moon
