"""Three-hour wet nodes for the bounded 3h/6h cadence experiment.

The original wet:station:0/1 parameters remain the 0h/3h endpoints and retain
their original level priors and increment sigma. The 6h node has only a new
3h->6h increment equation (sigma .03m), no added level prior. Marginalizing it
therefore leaves the original two-node prior distribution unchanged.
"""
import numpy as np
from customkf.stage5_pilot import Pilot


class ArcPilot(Pilot):
    def __init__(self,context,rows,seeds):
        self.extended=context["duration_s"]>11000
        super().__init__(context,rows,seeds)
        if self.extended:
            assert self.epoch_count==37 and context["step_s"]==600
            extra=[f"wet:{s}:6h" for s in self.stations]
            self.names[self.n:self.n]=extra;self.n+=len(extra)
            self.index={name:k for k,name in enumerate(self.names)}

    def wet_indices(self,station):
        return [self.index[f"wet:{station}:{k}"] for k in ("0","1","6h")]

    def weights(self,epoch):
        q=epoch/18;left=min(int(q),1)
        if not 0<=q<=2:raise ValueError("Outside fixed wet-node span")
        w=np.zeros(3);w[left]=1-(q-left);w[left+1]=q-left
        return w

    def state_for(self,x,row):
        rc,sc,wet,amb=super().state_for(x,row)
        if self.extended:wet=self.weights(row["epoch"])@x[self.wet_indices(row["station"])]
        return rc,sc,wet,amb

    def evaluate(self,x,jacobian=True,observations=None):
        result=super().evaluate(x,jacobian,observations)
        if not self.extended:return result
        blocks,(c,_,s),residual,sigma,modeled,_,products=result
        for ei,block in enumerate(blocks):
            for station in self.stations:
                indices=self.wet_indices(station)
                mw=block.retained[:,indices[0]]+block.retained[:,indices[1]]
                block.retained[:,indices]=mw[:,None]*self.weights(ei)
        new=[]
        for station in self.stations:
            indices=self.wet_indices(station);v=np.zeros(self.n);v[indices[1]]=-1;v[indices[2]]=1;new.append(v)
        c=np.vstack([c,new]);s=np.r_[s,np.full(len(new),.03)];z=-c@x[:self.n]
        cost=float(np.sum((residual/sigma)**2)+np.sum((z/s)**2))
        return blocks,(c,z,s),residual,sigma,modeled,cost,products
