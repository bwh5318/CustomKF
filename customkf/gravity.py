"""Degree-12 EGM2008 and nominal IERS solid Earth tides. Existing Numba only.

Fully normalized input is converted once to unnormalized positive-sign Legendre
coefficients. The spherical formula is not intended for trajectories on the pole.
"""
import math
import numpy as np
from numba import njit


def normalization(n,m):
    return math.sqrt((1 if m==0 else 2)*(2*n+1)*math.factorial(n-m)/math.factorial(n+m))


def read_gravity(path,degree=12):
    c=np.zeros((degree+1,degree+1));s=c.copy();header={};seen=set()
    with open(path) as stream:
        for line in stream:
            f=line.split()
            if not f:continue
            if f[0]=="gfc":
                n,m=map(int,f[1:3])
                if n>degree:continue
                if (n,m) in seen:raise ValueError("Duplicate gravity coefficient")
                seen.add((n,m))
                c[n,m],s[n,m]=[float(x.replace("d","e").replace("D","e")) for x in f[3:5]]
            elif len(f)==2:header[f[0]]=f[1]
    expected={(n,m) for n in range(2,degree+1) for m in range(n+1)}|{(0,0)}
    if seen!=expected or header.get("norm")!="fully_normalized" or header.get("tide_system")!="tide_free":
        raise ValueError("Incomplete or incompatible gravity field")
    norms=np.array([[normalization(n,m) if m<=n else 0 for m in range(degree+1)] for n in range(degree+1)])
    return float(header["earth_gravity_constant"]),float(header["radius"]),c*norms,s*norms,norms


@njit(cache=False)
def legendre(sine,cosine,degree):
    p=np.zeros((degree+1,degree+1));dp=p.copy();p[0,0]=1.
    for m in range(degree+1):
        if m:
            p[m,m]=(2*m-1)*cosine*p[m-1,m-1]
            dp[m,m]=(2*m-1)*(-sine*p[m-1,m-1]+cosine*dp[m-1,m-1])
        if m<degree:
            p[m+1,m]=(2*m+1)*sine*p[m,m]
            dp[m+1,m]=(2*m+1)*(cosine*p[m,m]+sine*dp[m,m])
        for n in range(m+2,degree+1):
            p[n,m]=((2*n-1)*sine*p[n-1,m]-(n+m-1)*p[n-2,m])/(n-m)
            dp[n,m]=((2*n-1)*(cosine*p[n-1,m]+sine*dp[n-1,m])-(n+m-1)*dp[n-2,m])/(n-m)
    return p,dp


@njit(cache=False)
def acceleration(r,mu,radius,c,s):
    distance=np.sqrt(np.dot(r,r));rho=np.sqrt(r[0]*r[0]+r[1]*r[1])
    if rho<1. or distance<radius:raise ValueError("Gravity outside supported domain")
    sine=r[2]/distance;cosine=rho/distance;cl=r[0]/rho;sl=r[1]/rho
    longitude=np.arctan2(r[1],r[0]);degree=len(c)-1
    p,dp=legendre(sine,cosine,degree)
    radial=0.;north=0.;east=0.
    for n in range(degree+1):
        power=(radius/distance)**n
        for m in range(n+1):
            co=np.cos(m*longitude);si=np.sin(m*longitude)
            harmonic=c[n,m]*co+s[n,m]*si
            radial-=(n+1)*power*p[n,m]*harmonic
            north+=power*dp[n,m]*harmonic
            east+=power*m*p[n,m]*(-c[n,m]*si+s[n,m]*co)/cosine
    return mu/distance**2*np.array([radial*cosine*cl-north*sine*cl-east*sl,
        radial*cosine*sl-north*sine*sl+east*cl,radial*sine+north*cosine])


def solid_tides(rotation,sun,moon,mu,radius,c,s,norms):
    """IERS 2010 6.2.1 step 1 (6.6,6.7), anelastic Table 6.3.

    Frequency corrections and ocean/pole tides are separate, not claimed here.
    Tide-free input needs the complete permanent component of these terms.
    """
    c=c.copy();s=s.copy()
    love2=np.array([.30190,.29830-.00144j,.30102-.00130j])
    love4=np.array([-.00089,-.00080,-.00057])
    for body,gm in ((sun,1.327124400419394e20),(moon,4.90280011845755e12)):
        r=rotation@body;distance=np.linalg.norm(r);longitude=np.arctan2(r[1],r[0])
        p,_=legendre(r[2]/distance,np.hypot(r[0],r[1])/distance,3)
        for n in (2,3):
            for m in range(n+1):
                tide=gm/mu*(radius/distance)**(n+1)*p[n,m]*norms[n,m]*np.exp(-1j*m*longitude)/(2*n+1)
                value=(love2[m] if n==2 else (.094 if m==3 else .093))*tide
                c[n,m]+=value.real*norms[n,m];s[n,m]-=value.imag*norms[n,m]
                if n==2:
                    value=love4[m]*tide
                    c[4,m]+=value.real*norms[4,m];s[4,m]-=value.imag*norms[4,m]
    return c,s
