"""Explicit Stage 3 light-time geometry and elementary atmospheric baseline.

This module alone is not a complete PPP measurement model: antenna, wind-up,
station tides/loading and signal-bias conventions must also be supplied.
"""
import numpy as np
from .preprocess import C

MU=3.986004415e14


def geodetic(xyz):
    x,y,z=np.asarray(xyz,dtype=float);a=6378137.;e2=6.6943799901413165e-3
    p=np.hypot(x,y);lon=np.arctan2(y,x);lat=np.arctan2(z,p*(1-e2))
    for _ in range(10):
        n=a/np.sqrt(1-e2*np.sin(lat)**2)
        new=np.arctan2(z+e2*n*np.sin(lat),p)
        if abs(new-lat)<1e-14:break
        lat=new
    n=a/np.sqrt(1-e2*np.sin(lat)**2)
    h=p*np.cos(lat)+z*np.sin(lat)-n*(1-e2*np.sin(lat)**2)
    return lat,lon,h


def enu_matrix(xyz):
    lat,lon,_=geodetic(xyz);s,c=np.sin(lat),np.cos(lat);sl,cl=np.sin(lon),np.cos(lon)
    return np.array([[-sl,cl,0.],[-s*cl,-s*sl,c],[c*cl,c*sl,s]])


def hydrostatic_baseline(xyz,elevation):
    """Saastamoinen with standard-atmosphere pressure, simple mapping baseline.

    Precision PPP must replace the cosecant mapping and verify pressure inputs.
    """
    lat,_,height=geodetic(xyz)
    if not -500<height<10000 or elevation<=0:raise ValueError("Unsupported troposphere geometry")
    pressure=1013.25*(1-2.2557e-5*height)**5.2568
    zhd=.0022768*pressure/(1-.00266*np.cos(2*lat)-.00028*height/1000)
    return zhd/np.sin(elevation),1/np.sin(elevation)


def geometry(products,sat,receive_tag_s,receiver_xyz,receiver_clock_m=0.):
    """Inertial transmit/receive geometry; exact Earth rotation, one clock correction.

    The receiver epoch tag is normalized by the estimated receiver clock before
    solving geometric light time. Precise satellite clocks exclude the periodic
    eccentricity correction; we include -2 r.v/c² once in the satellite clock.
    """
    receiver=np.asarray(receiver_xyz,dtype=float)
    receive=receive_tag_s-receiver_clock_m/C
    rotation=products.epoch.celestial_to_terrestrial(receive)
    receiver_inertial=rotation.T@receiver
    delay=.075
    for _ in range(8):
        state=products.state(sat,receive-delay)
        delta=state[:3]-receiver_inertial;rho=np.linalg.norm(delta)
        new=rho/C
        if abs(new-delay)*C<1e-6:break
        delay=new
    else:raise ValueError("Light-time iteration did not converge")
    los=rotation@(delta/rho)
    enu=enu_matrix(receiver)@los
    elevation=np.arcsin(np.clip(enu[2],-1,1));azimuth=np.arctan2(enu[0],enu[1])%(2*np.pi)
    rs=np.linalg.norm(state[:3]);rr=np.linalg.norm(receiver)
    path=2*MU/C**2*np.log((rs+rr+rho)/(rs+rr-rho))
    clock=products.clock(sat,receive-delay)-2*np.dot(state[:3],state[3:])/C**2
    return {"geometric_range_m":rho,"satellite_clock_s":clock,"shapiro_m":path,
            "elevation_rad":elevation,"azimuth_rad":azimuth,"los_ecef":los,
            "transmit_s":receive-delay,"receive_s":receive,"satellite_inertial":state,
            "modeled_code_without_trop_m":rho+path-C*clock+receiver_clock_m}
