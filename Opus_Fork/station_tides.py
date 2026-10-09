"""Station tidal displacement models more complete than `customkf.station_models` (fork-only; nothing in customkf edited).

Why (26 Sep 2026, results/SDEOP_RESULTS.md, follow-up 2): after the sub-daily EOP fix, the POD's remaining 12 h/24 h
common-height swing is a pure network-scale oscillation (0.16–0.36 ppb, about 1–2 mm of network-mean height). It is absent
from the station-free census. `customkf.station_models` uses a reduced RTKLIB-style solid tide and an 11-constituent
ocean loading without nodal modulation. This module provides the IERS versions so their difference can be tested.

1. `dehant(xsta, xsun, xmon, year, month, day, fhr)`: a Python port of IERS Conventions 2010 DEHANTTIDEINEL.F with
   ST1IDIU, ST1ISEM, ST1L1, STEP2DIU and STEP2LON. Derived work, not IERS software: routines are merged and renamed,
   and the algorithm and coefficients are unchanged. Sources retrieved 26 Sep 2026 into
   `datastore/static/iers_ch7/` (SHA-256 in IERS_CH7), where the IERS Conventions Software License notice is kept
   intact. Reproduces the IERS test cases (`self_test`). Neither distributed by nor endorsed by the IERS Conventions
   Center.
2. `ocean_loading_nodal(utc_mjd, coefficients)`: the customkf 11-constituent ocean loading (same arguments, same
   BLQ, same sign conventions) with the standard nodal modulation factors f and phase corrections u
   (Schureman/Doodson) applied per constituent. This approximates what IERS HARDISP captures through nodal sidelines;
   the full 342-line admittance port is not done here.

Coordinates are ITRF metres, ECEF, as in customkf. Both functions return ECEF displacement vectors (m).
"""
import numpy as np
import erfa

IERS_CH7 = {
    "DEHANTTIDEINEL.F": "bc6039a1704761881bb785ce44ce084ea82783107ff64c576e69155a4914e2cb",
    "ST1IDIU.F": "d2976b8b76be8dd1d57e57a8d6b48f5764676126515bada3592753a07d3acd1e",
    "ST1ISEM.F": "efdf284bd977826a1f4aea4c79c5dbd0c38fc1c403a2376010048b511a11f2c6",
    "ST1L1.F": "b1dfd0e797a3ce950631ad7dbbf5f576bf6b58dc515688253a3d84ca059bc282",
    "STEP2DIU.F": "898c70d4b8d50e09e0c717c911c4117b3ad1ca4996d369c258b68d00ea3a5674",
    "STEP2LON.F": "f9d3bf0317222986d22e53557020bb13a6fbb90f8e3c9915137da6184d82813a",
}

_DATDI_DIU = np.array([
    (-3, 0, 2, 0, 0, -0.01, 0, 0, 0), (-3, 2, 0, 0, 0, -0.01, 0, 0, 0), (-2, 0, 1, -1, 0, -0.02, 0, 0, 0),
    (-2, 0, 1, 0, 0, -0.08, 0, -0.01, 0.01), (-2, 2, -1, 0, 0, -0.02, 0, 0, 0), (-1, 0, 0, -1, 0, -0.10, 0, 0, 0),
    (-1, 0, 0, 0, 0, -0.51, 0, -0.02, 0.03), (-1, 2, 0, 0, 0, 0.01, 0, 0, 0), (0, -2, 1, 0, 0, 0.01, 0, 0, 0),
    (0, 0, -1, 0, 0, 0.02, 0, 0, 0), (0, 0, 1, 0, 0, 0.06, 0, 0, 0), (0, 0, 1, 1, 0, 0.01, 0, 0, 0),
    (0, 2, -1, 0, 0, 0.01, 0, 0, 0), (1, -3, 0, 0, 1, -0.06, 0, 0, 0), (1, -2, 0, -1, 0, 0.01, 0, 0, 0),
    (1, -2, 0, 0, 0, -1.23, -0.07, 0.06, 0.01), (1, -1, 0, 0, -1, 0.02, 0, 0, 0), (1, -1, 0, 0, 1, 0.04, 0, 0, 0),
    (1, 0, 0, -1, 0, -0.22, 0.01, 0.01, 0), (1, 0, 0, 0, 0, 12.00, -0.80, -0.67, -0.03), (1, 0, 0, 1, 0, 1.73, -0.12, -0.10, 0),
    (1, 0, 0, 2, 0, -0.04, 0, 0, 0), (1, 1, 0, 0, -1, -0.50, -0.01, 0.03, 0), (1, 1, 0, 0, 1, 0.01, 0, 0, 0),
    (0, 1, 0, 1, -1, -0.01, 0, 0, 0), (1, 2, -2, 0, 0, -0.01, 0, 0, 0), (1, 2, 0, 0, 0, -0.11, 0.01, 0.01, 0),
    (2, -2, 1, 0, 0, -0.01, 0, 0, 0), (2, 0, -1, 0, 0, -0.02, 0, 0, 0), (3, 0, 0, 0, 0, 0, 0, 0, 0),
    (3, 0, 0, 1, 0, 0, 0, 0, 0)], dtype=float)
_DATDI_LON = np.array([
    (0, 0, 0, 1, 0, 0.47, 0.23, 0.16, 0.07), (0, 2, 0, 0, 0, -0.20, -0.12, -0.11, -0.05),
    (1, 0, -1, 0, 0, -0.11, -0.08, -0.09, -0.04), (2, 0, 0, 0, 0, -0.13, -0.11, -0.15, -0.07),
    (2, 0, 0, 1, 0, -0.05, -0.05, -0.06, -0.03)], dtype=float)


def _geo(xsta):
    rsta = np.linalg.norm(xsta)
    sinphi = xsta[2]/rsta
    cosphi = np.hypot(xsta[0], xsta[1])/rsta
    return rsta, sinphi, cosphi, xsta[1]/cosphi/rsta, xsta[0]/cosphi/rsta


def _to_xyz(dr, dn, de, sinphi, cosphi, sinla, cosla):
    return np.array([dr*cosla*cosphi-de*sinla-dn*sinphi*cosla, dr*sinla*cosphi+de*cosla-dn*sinphi*sinla,
                     dr*sinphi+dn*cosphi])


def _st1idiu(xsta, xsun, xmon, fac2sun, fac2mon):
    dhi, dli = -0.0025, -0.0007
    rsta, sinphi, cosphi, sinla, cosla = _geo(xsta)
    cos2phi = cosphi*cosphi-sinphi*sinphi
    out = []
    for x, fac in ((xsun, fac2sun), (xmon, fac2mon)):
        r2 = np.dot(x, x)
        q = x[2]*(x[0]*sinla-x[1]*cosla)/r2
        out.append((-3*dhi*sinphi*cosphi*fac*q, -3*dli*cos2phi*fac*q,
                    -3*dli*sinphi*fac*x[2]*(x[0]*cosla+x[1]*sinla)/r2))
    dr, dn, de = (out[0][k]+out[1][k] for k in range(3))
    return _to_xyz(dr, dn, de, sinphi, cosphi, sinla, cosla)


def _st1isem(xsta, xsun, xmon, fac2sun, fac2mon):
    dhi, dli = -0.0022, -0.0007
    rsta, sinphi, cosphi, sinla, cosla = _geo(xsta)
    costwola, sintwola = cosla*cosla-sinla*sinla, 2*cosla*sinla
    out = []
    for x, fac in ((xsun, fac2sun), (xmon, fac2mon)):
        r2 = np.dot(x, x)
        a = ((x[0]**2-x[1]**2)*sintwola-2*x[0]*x[1]*costwola)/r2
        b = ((x[0]**2-x[1]**2)*costwola+2*x[0]*x[1]*sintwola)/r2
        out.append((-3/4*dhi*cosphi**2*fac*a, 3/2*dli*sinphi*cosphi*fac*a, -3/2*dli*cosphi*fac*b))
    dr, dn, de = (out[0][k]+out[1][k] for k in range(3))
    return _to_xyz(dr, dn, de, sinphi, cosphi, sinla, cosla)


def _st1l1(xsta, xsun, xmon, fac2sun, fac2mon):
    l1d, l1sd = 0.0012, 0.0024
    rsta, sinphi, cosphi, sinla, cosla = _geo(xsta)
    dn = de = 0.
    for x, fac in ((xsun, fac2sun), (xmon, fac2mon)):
        r2 = np.dot(x, x)
        dn += -l1d*sinphi**2*fac*x[2]*(x[0]*cosla+x[1]*sinla)/r2
        de += l1d*sinphi*(cosphi**2-sinphi**2)*fac*x[2]*(x[0]*sinla-x[1]*cosla)/r2
    de, dn = 3*de, 3*dn
    corr = np.array([-de*sinla-dn*sinphi*cosla, de*cosla-dn*sinphi*sinla, dn*cosphi])
    costwola, sintwola = cosla**2-sinla**2, 2.*cosla*sinla
    dn = de = 0.
    for x, fac in ((xsun, fac2sun), (xmon, fac2mon)):
        r2 = np.dot(x, x)
        dn += -l1sd/2*sinphi*cosphi*fac*((x[0]**2-x[1]**2)*costwola+2*x[0]*x[1]*sintwola)/r2
        de += -l1sd/2*sinphi**2*cosphi*fac*((x[0]**2-x[1]**2)*sintwola-2*x[0]*x[1]*costwola)/r2
    de, dn = 3*de, 3*dn
    return corr+np.array([-de*sinla-dn*sinphi*cosla, de*cosla-dn*sinphi*sinla, dn*cosphi])


def _fundamental(t):
    s = 218.31664563+(481267.88194+(-0.0014663889+0.00000185139*t)*t)*t
    pr = (1.396971278+(0.000308889+(0.000000021+0.000000007*t)*t)*t)*t
    h = 280.46645+(36000.7697489+(0.00030322222+(0.000000020+(-0.00000000654)*t)*t)*t)*t
    p = 83.35324312+(4069.01363525+(-0.01032172222+(-0.0000124991+0.00000005263*t)*t)*t)*t
    zns = 234.95544499+(1934.13626197+(-0.00207561111+(-0.00000213944+0.00000001650*t)*t)*t)*t
    ps = 282.93734098+(1.71945766667+(0.00045688889+(-0.00000001778+(-0.00000000334)*t)*t)*t)*t
    return s, pr, h, p, zns, ps


def _step2diu(xsta, fhr, t):
    s, pr, h, p, zns, ps = _fundamental(t)
    tau = fhr*15+280.4606184+(36000.7700536+(0.00038793+(-0.0000000258)*t)*t)*t+(-s)
    s = s+pr
    s, tau, h, p, zns, ps = (np.mod(v, 360.) for v in (s, tau, h, p, zns, ps))
    rsta, sinphi, cosphi, sinla, cosla = _geo(xsta)
    zla = np.arctan2(xsta[1], xsta[0])
    d = _DATDI_DIU
    thetaf = np.deg2rad(tau+d[:, 0]*s+d[:, 1]*h+d[:, 2]*p+d[:, 3]*zns+d[:, 4]*ps)
    sn, cs = np.sin(thetaf+zla), np.cos(thetaf+zla)
    dr = d[:, 5]*2*sinphi*cosphi*sn+d[:, 6]*2*sinphi*cosphi*cs
    dn = d[:, 7]*(cosphi**2-sinphi**2)*sn+d[:, 8]*(cosphi**2-sinphi**2)*cs
    de = d[:, 7]*sinphi*cs-d[:, 8]*sinphi*sn
    return _to_xyz(dr, dn, de, sinphi, cosphi, sinla, cosla).sum(axis=1)/1000.


def _step2lon(xsta, t):
    s, pr, h, p, zns, ps = _fundamental(t)
    s = s+pr
    s, h, p, zns, ps = (np.mod(v, 360.) for v in (s, h, p, zns, ps))
    rsta, sinphi, cosphi, sinla, cosla = _geo(xsta)
    d = _DATDI_LON
    thetaf = np.deg2rad(d[:, 0]*s+d[:, 1]*h+d[:, 2]*p+d[:, 3]*zns+d[:, 4]*ps)
    dr = d[:, 5]*(3*sinphi**2-1)/2*np.cos(thetaf)+d[:, 7]*(3*sinphi**2-1)/2*np.sin(thetaf)
    dn = d[:, 6]*(cosphi*sinphi*2)*np.cos(thetaf)+d[:, 8]*(cosphi*sinphi*2)*np.sin(thetaf)
    return _to_xyz(dr, dn, np.zeros_like(dr), sinphi, cosphi, sinla, cosla).sum(axis=1)/1000.


def dehant(xsta, xsun, xmon, year, month, day, fhr):
    """IERS 2010 DEHANTTIDEINEL: solid Earth tide displacement (m, ECEF) at UTC date + fhr hours."""
    xsta, xsun, xmon = (np.asarray(v, dtype=float) for v in (xsta, xsun, xmon))
    h20, l20, h3, l3 = 0.6078, 0.0847, 0.292, 0.015
    rsta, rsun, rmon = np.linalg.norm(xsta), np.linalg.norm(xsun), np.linalg.norm(xmon)
    scsun, scmon = np.dot(xsta, xsun)/rsta/rsun, np.dot(xsta, xmon)/rsta/rmon
    cosphi = np.hypot(xsta[0], xsta[1])/rsta
    h2 = h20-0.0006*(1-3/2*cosphi**2)
    l2 = l20+0.0002*(1-3/2*cosphi**2)
    p2sun, p2mon = 3*(h2/2-l2)*scsun**2-h2/2, 3*(h2/2-l2)*scmon**2-h2/2
    p3sun = 5/2*(h3-3*l3)*scsun**3+3/2*(l3-h3)*scsun
    p3mon = 5/2*(h3-3*l3)*scmon**3+3/2*(l3-h3)*scmon
    x2sun, x2mon = 3*l2*scsun, 3*l2*scmon
    x3sun, x3mon = 3*l3/2*(5*scsun**2-1), 3*l3/2*(5*scmon**2-1)
    re = 6378136.6
    fac2sun = 332946.0482*re*(re/rsun)**3
    fac2mon = 0.0123000371*re*(re/rmon)**3
    fac3sun, fac3mon = fac2sun*(re/rsun), fac2mon*(re/rmon)
    dx = (fac2sun*(x2sun*xsun/rsun+p2sun*xsta/rsta)+fac2mon*(x2mon*xmon/rmon+p2mon*xsta/rsta)
          + fac3sun*(x3sun*xsun/rsun+p3sun*xsta/rsta)+fac3mon*(x3mon*xmon/rmon+p3mon*xsta/rsta))
    dx = dx+_st1idiu(xsta, xsun, xmon, fac2sun, fac2mon)
    dx = dx+_st1isem(xsta, xsun, xmon, fac2sun, fac2mon)
    dx = dx+_st1l1(xsta, xsun, xmon, fac2sun, fac2mon)
    jd0, jd1 = erfa.cal2jd(year, month, day)
    fhrd = fhr/24.
    t = ((jd0-2451545.0)+jd1+fhrd)/36525.
    dtt = erfa.dat(year, month, day, fhrd)+32.184
    t = t+dtt/(3600.*24.*36525.)
    return dx+_step2diu(xsta, fhr, t)+_step2lon(xsta, t)


_TESTS = [  # IERS DEHANTTIDEINEL.F test cases
    ((4075578.385, 931852.890, 4801570.154), (137859926952.015, 54228127881.4350, 23509422341.6960),
     (-179996231.920342, -312468450.131567, -169288918.592160), (2009, 4, 13, 0.),
     (0.7700420357108125891e-01, 0.6304056321824967613e-01, 0.5516568152597246810e-01)),
    ((1112189.660, -4842955.026, 3985352.284), (-54537460436.2357, 130244288385.279, 56463429031.5996),
     (300396716.912, 243238281.451, 120548075.939), (2012, 7, 13, 0.),
     (-0.2036831479592075833e-01, 0.5658254776225972449e-01, -0.7597679676871742227e-01)),
    ((1112200.5696, -4842957.8511, 3985345.9122), (100210282451.6279, 103055630398.3160, 56855096480.4475),
     (369817604.4348, 1897917.5258, 120804980.8284), (2015, 7, 15, 0.),
     (.00509570869172363845, .0828663025983528700, -.0636634925404189617)),
]


def self_test():
    worst = 0.
    for xsta, xsun, xmon, (y, m, d, h), want in _TESTS:
        got = dehant(xsta, xsun, xmon, y, m, d, h)
        worst = max(worst, float(np.max(np.abs(got-np.array(want)))))
    assert worst < 1e-12, worst
    return worst


# Ocean loading: customkf.station_models.ocean_loading plus nodal modulation. Column order of the BLQ / customkf
# arrays: M2 S2 N2 K2 K1 O1 P1 Q1 MF MM SSA.
def nodal_factors(utc_mjd):
    """Standard nodal factors f and phase corrections u (rad) for the 11 BLQ constituents."""
    t = (utc_mjd-51544.5)/36525.
    n = np.deg2rad(125.04452-1934.136261*t)  # mean longitude of the Moon's ascending node
    c1, c2, c3 = np.cos(n), np.cos(2*n), np.cos(3*n)
    s1, s2, s3 = np.sin(n), np.sin(2*n), np.sin(3*n)
    fm2 = 1.0004-0.0373*c1+0.0002*c2
    um2 = -2.14*s1
    fk2 = 1.0241+0.2863*c1+0.0083*c2-0.0015*c3
    uk2 = -17.74*s1+0.68*s2-0.04*s3
    fk1 = 1.0060+0.1150*c1-0.0088*c2+0.0006*c3
    uk1 = -8.86*s1+0.68*s2-0.07*s3
    fo1 = 1.0089+0.1871*c1-0.0147*c2+0.0014*c3
    uo1 = 10.80*s1-1.34*s2+0.19*s3
    fmf = 1.043+0.414*c1
    umf = -23.7*s1+2.7*s2-0.4*s3
    fmm = 1.0-0.130*c1
    f = np.array([fm2, 1., fm2, fk2, fk1, fo1, 1., fo1, fmf, fmm, 1.])
    u = np.deg2rad([um2, 0., um2, uk2, uk1, uo1, 0., uo1, umf, 0., 0.])
    return f, u


def ocean_loading_nodal(utc_mjd, coefficients):
    """customkf.station_models.ocean_loading with nodal f/u applied; returns ENU (m) like the original."""
    from customkf.station_models import OCEAN_ARGUMENTS
    day = np.floor(utc_mjd)
    seconds = (utc_mjd-day)*86400
    days = day-42413+1
    t = (27392.500528+1.000000035*days)/36525
    angles = np.deg2rad([279.69668+36000.768930485*t+3.03e-4*t*t,
                         270.434358+481267.88314137*t-.001133*t*t+1.9e-6*t**3,
                         334.329653+4069.0340329577*t-.010325*t*t-1.2e-5*t**3])
    arguments = OCEAN_ARGUMENTS@np.r_[seconds, angles, 2*np.pi]
    f, u = nodal_factors(utc_mjd)
    uws = np.sum(f*coefficients[:3]*np.cos(arguments+u-np.deg2rad(coefficients[3:])), axis=1)
    return uws[[1, 2, 0]]*[-1, -1, 1]
