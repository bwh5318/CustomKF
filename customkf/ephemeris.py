"""Restricted read-only little-endian DAF/SPK type-2 reader for pinned DE440s.

No generic SPICE API, aberration, frame conversion or automatic data retrieval.
NAIF DAF/SPK specifications: summaries ND=2 NI=6, J2000 frame, km and TDB seconds.
"""
import struct
import numpy as np


class DE440:
    def __init__(self,path):
        self.data=np.memmap(path,dtype="u1",mode="r")
        raw=self.data[:1024].tobytes()
        if raw[:8]!=b"DAF/SPK " or raw[88:96]!=b"LTL-IEEE":raise ValueError("Unsupported SPK format")
        if struct.unpack_from("<ii",raw,8)!=(2,6):raise ValueError("Unsupported SPK summary")
        record=struct.unpack_from("<i",raw,76)[0]
        self.segments={};seen=set()
        while record:
            if record in seen:raise ValueError("Cyclic SPK summary")
            seen.add(record)
            block=self.data[(record-1)*1024:record*1024].tobytes()
            nxt,_,count=struct.unpack_from("<ddd",block)
            if count!=int(count) or not 0<=count<=25:raise ValueError("Invalid summary count")
            for i in range(int(count)):
                offset=24+i*40
                start,end=struct.unpack_from("<dd",block,offset)
                target,center,frame,kind,first,last=struct.unpack_from("<iiiiii",block,offset+16)
                if frame!=1 or kind!=2:raise ValueError("Only J2000 type-2 segments are supported")
                if not 1<=first<=last<=len(self.data)//8:raise ValueError("Invalid SPK data range")
                coefficients=np.ndarray((last-first+1,),dtype="<f8",buffer=self.data,offset=(first-1)*8)
                init,interval,size,n=coefficients[-4:]
                if size!=int(size) or n!=int(n) or int(size)*int(n)+4!=len(coefficients) or (int(size)-2)%3:
                    raise ValueError("Invalid Chebyshev record layout")
                key=(center,target)
                if key in self.segments:raise ValueError("Overlapping segments unsupported")
                self.segments[key]=(start,end,init,interval,coefficients[:-4].reshape(int(n),int(size)))
            record=int(nxt)

    def position_km(self,center,target,tdb_seconds):
        start,end,init,interval,records=self.segments[center,target]
        t=float(tdb_seconds)
        if not np.isfinite(t) or not start<=t<=end:raise ValueError("Time outside pinned ephemeris")
        i=min(int((t-init)//interval),len(records)-1)
        if i<0:raise ValueError("Invalid ephemeris record")
        row=records[i];tau=(t-row[0])/row[1]
        if abs(tau)>1+1e-12:raise ValueError("Time outside Chebyshev record")
        return np.polynomial.chebyshev.chebval(tau,row[2:].reshape(3,-1).T)

    def sun_moon_m(self,tdb_seconds):
        earth=self.position_km(0,3,tdb_seconds)+self.position_km(3,399,tdb_seconds)
        sun=self.position_km(0,10,tdb_seconds)-earth
        moon=self.position_km(3,301,tdb_seconds)-self.position_km(3,399,tdb_seconds)
        return sun*1000,moon*1000
