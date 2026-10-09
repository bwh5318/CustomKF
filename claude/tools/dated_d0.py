# Isolated date-aware adaptation; see dated_module_origins.json.
"""Station-only six-hour pilot with one unregularized D0 correction per satellite."""
import numpy as np
from claude.tools.dated_observation import correction_difference, modeled_link
from customkf.nominal_navigation import NominalProducts
from customkf.preprocess import C
from claude.tools.dated_arc import ArcPilot
from claude.tools.force_parameter_fit import ForceTrajectory,INITIAL_P

SCALE=1e-7


class ForceTangent:
    def __init__(self,base,satellite,delta):
        self.base,self.satellite,self.delta,self.epoch=base,satellite,delta,base.epoch
    def state(self,sat,t):
        state=self.base.state(sat,t)
        if sat==self.satellite:state=state+self.base.trajectories[sat].force_partial(t)[:,0]*SCALE*self.delta
        return state
    def clock(self,sat,t):return self.base.clock(sat,t)


def d0_link_partial(products,row,receiver_cal,satellite_cal,ephemeris,rc,sc,wet,amb,windup):
    def evaluate(p):
        return modeled_link(p,row,receiver_cal,satellite_cal,ephemeris,rc,sc,wet,amb,windup,details=True)
    g,base=evaluate(products);sat=row["satellite"]
    u=products.epoch.celestial_to_terrestrial(g["receive_s"]).T@g["los_ecef"]
    velocity=g["satellite_inertial"][3:];rate=products.clock_rate(sat,g["transmit_s"])
    sensitivity=products.trajectories[sat].force_partial(g["transmit_s"])[:3,0]*SCALE
    principal=(1+rate)*(u@sensitivity)/(1+u@velocity/C)
    h=.001
    # Domain-aware correction difference (Sol SOL-01 / Astra AF-02); bitwise as before wherever the step is valid.
    return principal+correction_difference(lambda delta:evaluate(ForceTangent(products,sat,delta))[1],1.,h,h/64,base)


class D0Pilot(ArcPilot):
    def __init__(self,context,rows,seeds):
        super().__init__(context,rows,seeds)
        assert self.extended and context["step_s"]==600
        self.names[self.n:self.n]=[f"srpD0:{s}" for s in self.sats];self.n+=len(self.sats)
        self.index={name:k for k,name in enumerate(self.names)}

    def products(self,x):
        trajectories={}
        for sat in self.sats:
            k=self.index[f"orbit:{sat}:0"];p=INITIAL_P.copy();j=self.index.get(f"srpD0:{sat}")
            if j is not None:p[0]+=SCALE*x[j]
            trajectories[sat]=ForceTrajectory(self.seeds[sat]+x[k:k+6],self.context["model"],self.duration,p)
        return NominalProducts(self.context["epoch"],self.context["origin_ns"],self.context["records"],trajectories,
                               available_before_ns=self.context["navigation_cutoff_ns"])

    def embed(self,old):
        x=np.zeros(len(self.names))
        for name,value in zip(map(str,old["names"]),old["x"]):x[self.index[name]]=value
        return x

    def force_partial_for(self,products,row,x):
        c=self.context;antenna=c["stations"][row["station"]]["header"]["antenna"]
        return d0_link_partial(products,row,c["rx_cal"][antenna],c["sat_cal"][row["satellite"]],c["ephemeris"],
                               *self.state_for(x,row),self.windup[id(row)])

    def evaluate(self,x,jacobian=True,observations=None):
        result=super().evaluate(x,jacobian,observations)
        if not jacobian:return result
        blocks=result[0];products=result[-1]
        for ei,block in enumerate(blocks):
            offset=0
            for row in (r for r in self.rows if r["epoch"]==ei):
                count=2 if row["arc"] in self.arcs else 1
                partial=self.force_partial_for(products,row,x)
                block.retained[offset:offset+count,self.index[f"srpD0:{row['satellite']}"]]=partial[:count]
                offset+=count
            assert offset==len(block.target)
        return result
