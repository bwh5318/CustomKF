"""Initial PPP station atmosphere/loading models, with explicit approximation scope.

NMF coefficients and the reduced 11-line ocean/solid-tide implementation were
checked against RTKLIB rtkcmn.c/ppp.c (T. Takasu, 2007–2018). See
THIRD_PARTY_NOTICES.md. This is not the complete IERS DEHANTTIDEINEL/HARDISP suite.
"""
from datetime import datetime,timedelta
import numpy as np
import erfa
from .measurement import geodetic,enu_matrix
from .sp3 import GPS_START

NMF=np.array([
[1.2769934e-3,1.2683230e-3,1.2465397e-3,1.2196049e-3,1.2045996e-3],
[2.9153695e-3,2.9152299e-3,2.9288445e-3,2.9022565e-3,2.9024912e-3],
[62.610505e-3,62.837393e-3,63.721774e-3,63.824265e-3,64.258455e-3],
[0.,1.2709626e-5,2.6523662e-5,3.4000452e-5,4.1202191e-5],
[0.,2.1414979e-5,3.0160779e-5,7.2562722e-5,11.723375e-5],
[0.,9.0128400e-5,4.3497037e-5,84.795348e-5,170.37206e-5],
[5.8021897e-4,5.6794847e-4,5.8118019e-4,5.9727542e-4,6.1641693e-4],
[1.4275268e-3,1.5138625e-3,1.4572752e-3,1.5007428e-3,1.7599082e-3],
[4.3472961e-2,4.6729510e-2,4.3908931e-2,4.4626982e-2,5.4736038e-2]])


def mapping(elevation,coefficients):
    a,b,c=coefficients;s=np.sin(elevation)
    return (1+a/(1+b/(1+c)))/(s+a/(s+b/(s+c)))


def troposphere(xyz,elevation,doy):
    lat,_,height=geodetic(xyz)
    coeff=np.array([np.interp(abs(np.rad2deg(lat)),[15,30,45,60,75],row) for row in NMF])
    phase=2*np.pi*((doy-28)/365.25+(.5 if lat<0 else 0))
    dry=coeff[:3]-coeff[3:6]*np.cos(phase);wet=coeff[6:]
    mh=mapping(elevation,dry)+(1/np.sin(elevation)-mapping(elevation,[2.53e-5,5.49e-3,1.14e-3]))*height/1000
    mw=mapping(elevation,wet)
    pressure=1013.25*(1-2.2557e-5*height)**5.2568
    zhd=.0022768*pressure/(1-.00266*np.cos(2*lat)-.00028*height/1000)
    return zhd*mh,mw


def read_loading(path,station):
    with open(path) as stream:
        for line in stream:
            if line.strip()==station:
                rows=[]
                while len(rows)<6:
                    line=stream.readline()
                    if not line:raise ValueError("Truncated loading coefficients")
                    if line.startswith("$$"):continue
                    rows.append([float(x) for x in line.split()])
                values=np.array(rows)
                if values.shape!=(6,11):raise ValueError("Expected 11 ocean-loading constituents")
                return values
    raise ValueError("Station absent from loading table")


OCEAN_ARGUMENTS=np.array([[1.40519e-4,2,-2,0,0],[1.45444e-4,0,0,0,0],[1.37880e-4,2,-3,1,0],
[1.45842e-4,2,0,0,0],[.72921e-4,1,0,0,.25],[.67598e-4,1,-2,0,-.25],
[.72523e-4,-1,0,0,-.25],[.64959e-4,1,-3,1,-.25],[.53234e-5,0,2,0,0],
[.26392e-5,0,1,-1,0],[.03982e-5,2,0,0,0]])


def ocean_loading(utc_mjd,coefficients):
    day=np.floor(utc_mjd);seconds=(utc_mjd-day)*86400
    days=day-42413+1  # 1975-01-01 MJD
    t=(27392.500528+1.000000035*days)/36525
    angles=np.deg2rad([279.69668+36000.768930485*t+3.03e-4*t*t,
                      270.434358+481267.88314137*t-.001133*t*t+1.9e-6*t**3,
                      334.329653+4069.0340329577*t-.010325*t*t-1.2e-5*t**3])
    arguments=OCEAN_ARGUMENTS@np.r_[seconds,angles,2*np.pi]
    uws=np.sum(coefficients[:3]*np.cos(arguments-np.deg2rad(coefficients[3:])),axis=1)
    return uws[[1,2,0]]*[-1,-1,1]


def solid_displacement(xyz,sun_ecef,moon_ecef,gmst):
    """Reduced tide model; geodetic local vertical, not full IERS compliance."""
    # Complete permanent part is included for conventional tide-free coordinates.
    lat,lon,_=geodetic(xyz);enu=enu_matrix(xyz);up=enu[2];result=np.zeros(3)
    for body,gm in ((sun_ecef,1.327124400419394e20),(moon_ecef,4.90280011845755e12)):
        distance=np.linalg.norm(body);direction=body/distance
        k2=gm/3.986004415e14*6378137.**4/distance**3;k3=k2*6378137/distance
        shape=(3*np.sin(lat)**2-1)/2;h2=.6078-.0006*shape;l2=.0847+.0002*shape
        a=direction@up
        tangent=k2*3*l2*a+k3*.015*(7.5*a*a-1.5)
        radial=k2*(h2*(1.5*a*a-.5)-3*l2*a*a)+k3*(.292*(2.5*a**3-1.5*a)-.015*(7.5*a*a-1.5)*a)
        body_lat=np.arcsin(direction[2]);body_lon=np.arctan2(direction[1],direction[0])
        radial+=.75*.0025*k2*np.sin(2*body_lat)*np.sin(2*lat)*np.sin(lon-body_lon)
        radial+=.75*.0022*k2*np.cos(body_lat)**2*np.cos(lat)**2*np.sin(2*(lon-body_lon))
        result+=tangent*direction+radial*up
    result+=-.012*np.sin(2*lat)*np.sin(gmst+lon)*up
    return result


def station_displacement(xyz,t,epoch,ephemeris,loading):
    rotation=epoch.celestial_to_terrestrial(t)
    sun,moon=ephemeris.sun_moon_m(epoch.tdb_seconds(t))
    tt1,tt2,u1,u2,xp,yp,_,_=epoch.times(t)
    result=solid_displacement(xyz,rotation@sun,rotation@moon,erfa.gmst06(u1,u2,tt1,tt2))
    lat,lon,_=geodetic(xyz);enu=enu_matrix(xyz)
    tai=erfa.tttai(tt1,tt2);utc1,utc2=erfa.taiutc(*tai);mjd=(utc1-2400000.5)+utc2
    year=2000+(mjd-51544.5)/365.25
    m1=xp/erfa.DAS2R-(55+1.677*(year-2000))/1000
    m2=-yp/erfa.DAS2R+(320.5+3.460*(year-2000))/1000
    common=m1*np.cos(lon)+m2*np.sin(lon)
    pole=np.array([.009*np.sin(lat)*(m1*np.sin(lon)-m2*np.cos(lon)),
                   -.009*np.cos(2*lat)*common,-.033*np.sin(2*lat)*common])
    return result+enu.T@(pole+ocean_loading(mjd,loading))


def sinex_time(text,zero):
    if text=="00:000:00000":return zero
    year,day,seconds=map(int,text.split(":"));year+=1900 if year>=80 else 2000
    return datetime(year,1,1)+timedelta(days=day-1,seconds=seconds)


def reference_coordinate(ssc,solutions,station,date):
    solution=None
    for line in open(solutions):
        f=line.split()
        if len(f)>=8 and f[0]==station and f[3]=="P" and f[6]=="P":
            if sinex_time(f[4],datetime.min)<=date<sinex_time(f[5],datetime.max):solution=int(f[2])
    if solution is None:raise ValueError("No current station position interval")
    values={};reference_epoch=None
    for line in open(ssc):
        f=line.split()
        if len(f)>=10 and f[1] in ("STAX","STAY","STAZ","VELX","VELY","VELZ") and f[2]==station and int(f[4])==solution:
            values[f[1]]=float(f[8]);reference_epoch=sinex_time(f[5],datetime.min)
    if len(values)!=6:raise ValueError("Coordinate file lacks the current station solution")
    years=(date-reference_epoch).total_seconds()/(365.25*86400)
    return np.array([values["STA"+a]+years*values["VEL"+a] for a in "XYZ"]),solution
