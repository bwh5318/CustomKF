"""Selected absolute ANTEX calibrations and nominal IGS-axis phase corrections."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import numpy as np
from .sp3 import GPS_START
from .measurement import enu_matrix
from .preprocess import ALPHA,BETA,LAMBDA1,LAMBDA2


def unit(x):
    norm=np.linalg.norm(x)
    if norm<1e-12:raise ValueError("Degenerate antenna geometry")
    return x/norm


@dataclass
class Calibration:
    name:str
    serial:str
    svn:str
    frequencies:dict
    zenith:np.ndarray
    dazi:float

    def variation(self,freq,angle_deg,azimuth_deg=0.):
        data=self.frequencies[freq]
        if not self.zenith[0]-1e-8<=angle_deg<=self.zenith[-1]+1e-8:
            raise ValueError("ANTEX angular extrapolation")
        if data["azimuth"]:
            angles=np.array(sorted(data["azimuth"]))
            values=np.array([np.interp(angle_deg,self.zenith,data["azimuth"][a]) for a in angles])
            return float(np.interp(azimuth_deg%360,angles,values))
        return float(np.interp(angle_deg,self.zenith,data["noazi"]))


def load_calibrations(path,receiver_names,gps_ns):
    satellites={};receivers={};current=None;frequency=None;active=False
    with open(path) as stream:
        first=stream.readline()
        if "ANTEX VERSION" not in first:raise ValueError("Not ANTEX")
        second=stream.readline()
        if second[0]!="A":raise ValueError("Absolute ANTEX calibration required")
        for line in stream:
            label=line[60:].strip();body=line[:60]
            if label=="START OF ANTENNA":current={"start":0,"end":2**63-1,"frequencies":{}};frequency=None;active=False
            elif current is None:continue
            elif label=="TYPE / SERIAL NO":
                name=body[:20].rstrip();serial=body[20:40].strip();svn=body[40:50].strip()
                current.update(name=name,serial=serial,svn=svn)
                active=name in receiver_names or (len(serial)==3 and serial.startswith("G"))
            elif not active:continue
            elif label in ("VALID FROM","VALID UNTIL"):
                fields=body.split();year,month,day,hour,minute=map(int,fields[:5])
                delta=datetime(year,month,day,hour,minute)-GPS_START
                current["start" if label=="VALID FROM" else "end"]=(delta.days*86400+delta.seconds)*10**9+int(Decimal(fields[5])*10**9)
            elif label=="DAZI":current["dazi"]=float(body)
            elif label=="ZEN1 / ZEN2 / DZEN":
                lo,hi,step=map(float,body.split());current["zenith"]=np.arange(lo,hi+step/2,step)
            elif label=="START OF FREQUENCY":
                frequency=body.strip();current["frequencies"][frequency]={"azimuth":{}}
            elif label=="END OF FREQUENCY":frequency=None
            elif label=="NORTH / EAST / UP" and frequency:
                current["frequencies"][frequency]["pco"]=np.array(body.split(),dtype=float)/1000
            elif label=="END OF ANTENNA":
                if not current["start"]<=gps_ns<=current["end"]:continue
                for freq in ("G01","G02"):
                    if freq not in current["frequencies"]:break
                    data=current["frequencies"][freq]
                    if "pco" not in data or "noazi" not in data or len(data["noazi"])!=len(current["zenith"]):
                        raise ValueError("Incomplete selected GPS ANTEX calibration")
                    if not np.isfinite(data["pco"]).all() or not np.isfinite(data["noazi"]).all():
                        raise ValueError("Nonfinite selected ANTEX calibration")
                    if data["azimuth"]:
                        angles=sorted(data["azimuth"])
                        if angles[0]!=0 or angles[-1]!=360 or any(
                            len(row)!=len(current["zenith"]) or not np.isfinite(row).all()
                            for row in data["azimuth"].values()):
                            raise ValueError("Incomplete ANTEX azimuth grid")
                        if not np.allclose(data["azimuth"][0.],data["azimuth"][360.],atol=1e-9,rtol=0):
                            raise ValueError("Discontinuous ANTEX azimuth wrap")
                else:
                    cal=Calibration(current["name"],current["serial"],current["svn"],current["frequencies"],current["zenith"],current["dazi"])
                    if current["name"] in receiver_names:
                        # Use type-mean calibration only, never pick another serial's individual calibration.
                        if not current["serial"]:receivers[current["name"]]=cal
                    else:
                        if current["serial"] in satellites:raise ValueError("Overlapping satellite ANTEX validity")
                        satellites[current["serial"]]=cal
            elif frequency and not label:
                fields=line.split()
                if not fields:continue
                data=current["frequencies"][frequency]
                if fields[0]=="NOAZI":data["noazi"]=np.array(fields[1:],dtype=float)/1000
                elif fields[0].replace(".","",1).isdigit():
                    data["azimuth"][float(fields[0])]=np.array(fields[1:],dtype=float)/1000
            elif frequency and line[:8].strip()=="NOAZI":
                # ANTEX numeric PCV rows extend beyond column 60.
                current["frequencies"][frequency]["noazi"]=np.array(line.split()[1:],dtype=float)/1000
            elif frequency:
                try:azimuth=float(line[:8])
                except ValueError:continue
                current["frequencies"][frequency]["azimuth"][azimuth]=np.array(line[8:].split(),dtype=float)/1000
    if set(receivers)!=set(receiver_names):raise ValueError("Missing exact receiver antenna/radome calibration")
    return satellites,receivers


def corrections(g,receiver_xyz,receiver_cal,satellite_cal,sun_inertial,rotation):
    state=g["satellite_inertial"];z=-unit(state[:3]);sun=unit(sun_inertial-state[:3])
    y=unit(np.cross(z,sun));x=np.cross(y,z)
    axes=rotation@np.c_[x,y,z]
    los=g["los_ecef"];enu=enu_matrix(receiver_xyz)
    nadir=np.rad2deg(np.arccos(np.clip((-los)@axes[:,2],-1,1)))
    zenith=90-np.rad2deg(g["elevation_rad"]);azimuth=np.rad2deg(g["azimuth_rad"])
    corrections=[]
    for freq in ("G01","G02"):
        receiver_neu=receiver_cal.frequencies[freq]["pco"]
        receiver_offset=enu.T@receiver_neu[[1,0,2]]
        satellite_offset=axes@satellite_cal.frequencies[freq]["pco"]
        corrections.append(los@(satellite_offset-receiver_offset)+
            receiver_cal.variation(freq,zenith,azimuth)+satellite_cal.variation(freq,nadir))
    # Wu effective dipoles; receiver x=north and y=west, satellite x/y IGS axes.
    k=-los;xr=enu[1];yr=-enu[0];xs=axes[:,0];ys=axes[:,1]
    dr=xr-k*(k@xr)+np.cross(k,yr)
    ds=xs-k*(k@xs)-np.cross(k,ys)
    phase=np.arctan2(k@np.cross(ds,dr),ds@dr)/(2*np.pi)
    return ALPHA*corrections[0]+BETA*corrections[1],phase
