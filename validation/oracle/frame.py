"""Independent oracle O2: GPST epoch -> GCRS-to-ITRS rotation, daily IERS EOP and IERS 2010 ocean-tidal sub-daily EOP.

Written separately from `customkf.frames` and `Opus_Fork.subdaily_eop` (docs/consolidation/CONTRACTS_AND_ORACLE.md §4):
it imports neither, and shares only the ERFA library. It implements the same *declared* conventions, so that a
disagreement measures an implementation error rather than a convention choice:

- EOP values: IERS finals2000A (fixed columns of the IERS readme). Bulletin B where its five values are present,
  otherwise the Bulletin A values flagged observed ("I") for polar motion, UT1 and nutation. Rows without either
  are not used.
- Daily interpolation: linear between consecutive daily rows (gaps over one day and extrapolation refused). UT1-UTC is
  interpolated as UT1-TAI, and the leap offset of the epoch itself is restored.
- Sub-daily EOP (opt-in): IERS 2010 ORTHO_EOP/CNMTX (ocean tides, 71 lines, 12x3 orthoweights). The coefficient tables
  are parsed at run time from the IERS Fortran sources themselves. The time argument is MJD(UTC), as in production.
  `ocean_tidal_eop` is a derived work, not IERS software, and is neither distributed by nor endorsed by the IERS
  Conventions Center: a vectorised NumPy re-implementation of ORTHO_EOP.F with CNMTX.F, whose algorithm and tables are
  unchanged. The original files, with the IERS Conventions Software License notice intact, are in
  `Opus_Fork/datastore/static/iers_ch8/`.
- Rotation: IAU 2006/2000A, CIO based. X and Y come from the series (`erfa.xy06`, not `xys06a`) plus dX/dY; then
  s06(X, Y), the CIO-based bias-precession-nutation matrix, the Earth rotation angle as an explicit R3, and polar
  motion with s'.
- Opt-in `cip="angles"` (8 Oct 2026, network amendment A4, Astra review): X and Y from the angles-based
  `bpn2xy(pnm06a(TT))`, the method production's `xys06a` uses; everything else above is unchanged. ERFA documents
  microarcsecond differences between the two methods (`xy06` Note 4), up to 1.5 uas (0.19 mm at GPS radius) on the
  network dates. The angles path is for strict reproduction of production scores; the series default stays a
  cross-method check, and every earlier oracle result is unchanged.
- Time: TAI = GPST + 19 s, TT = TAI + 32.184 s. UTC comes from TAI with ERFA's leap-second table, and UT1 = UTC +
  (UT1-UTC).
"""
from pathlib import Path
import re

import erfa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
IERS_CH8 = ROOT/"Opus_Fork/datastore/static/iers_ch8"
MJD_GPS0 = 44244          # MJD of 1980-01-06 (GPS time origin)
AS2R = np.pi/648000.      # arcseconds to radians
DAY_NS = 86400*10**9


# ----- IERS finals2000A ------------------------------------------------------------------------------------------
# 1-based inclusive column ranges from the IERS finals2000A readme.
_B = dict(x=(135, 144), y=(145, 154), dut1=(155, 165), dx=(166, 175), dy=(176, 185))
_A = dict(x=(19, 27), y=(38, 46), dut1=(59, 68), dx=(98, 106), dy=(117, 125))
_A_FLAGS = (17, 58, 96)


def _field(line, columns):
    return line[columns[0]-1:columns[1]].strip()


class Finals:
    """Daily EOP rows: MJD, xp ("), yp ("), UT1-UTC (s), dX (mas), dY (mas)."""

    def __init__(self, path):
        rows, kinds = [], []
        with open(path) as stream:
            for line in stream:
                if len(line.rstrip("\n")) < 68:
                    continue
                mjd_text = _field(line, (8, 15))
                if not mjd_text:
                    continue
                b = [_field(line, c) for c in _B.values()] if len(line) >= 185 else []
                if b and all(b):
                    rows.append([float(mjd_text), *map(float, b)])
                    kinds.append("B")
                    continue
                flags = [line[c-1] if len(line) >= c else " " for c in _A_FLAGS]
                a = [_field(line, c) for c in _A.values()]
                if flags == ["I", "I", "I"] and all(a):
                    rows.append([float(mjd_text), *map(float, a)])
                    kinds.append("A-observed")
        self.rows = np.array(rows)
        self.kinds = kinds
        if len(rows) < 2 or not np.all(np.diff(self.rows[:, 0]) > 0):
            raise ValueError("finals table unusable")

    def at(self, mjd_utc):
        """(xp ", yp ", UT1-UTC s, dX mas, dY mas) at MJD(UTC), linear, UT1 interpolated as UT1-TAI."""
        days = self.rows[:, 0]
        i = int(np.searchsorted(days, mjd_utc, side="right"))-1
        if i < 0 or i+1 >= len(days) or days[i+1]-days[i] > 1.01:
            raise ValueError(f"No bracketing daily EOP rows for MJD {mjd_utc}")
        w = (mjd_utc-days[i])/(days[i+1]-days[i])
        lo, hi = self.rows[i, 1:], self.rows[i+1, 1:]
        value = lo*(1-w)+hi*w
        leap = [leap_seconds(m) for m in (days[i], days[i+1], mjd_utc)]
        value[2] = ((lo[2]-leap[0])*(1-w)+(hi[2]-leap[1])*w)+leap[2]
        return value


def leap_seconds(mjd_utc):
    """TAI-UTC (s) on the UTC date of MJD `mjd_utc` (ERFA's table)."""
    year, month, day, fraction = erfa.jd2cal(2400000.5, mjd_utc)
    return float(erfa.dat(year, month, day, fraction))


# ----- IERS 2010 ocean-tidal sub-daily EOP, from the Fortran tables ----------------------------------------------
_NUMBER = r"[-+]?\d*\.?\d+(?:[DdEe][-+]?\d+)?"


def _numbers(text):
    return [float(v.replace("D", "e").replace("d", "e")) for v in re.findall(_NUMBER, text)]


def _fortran_code(path):
    """The source without comment lines (column-1 '*'), continuation markers kept."""
    return "\n".join(line for line in Path(path).read_text().splitlines() if not line.startswith("*"))


def _tables():
    """(lines: n, m, HS, phase, freq per line; SP 6x2; ORTHOW 12x3) parsed from CNMTX.F and ORTHO_EOP.F."""
    cnmtx = _fortran_code(IERS_CH8/"CNMTX.F")
    lines = []
    for block in re.findall(r"DATA \(NJ\(J\),MJ\(J\),HS\(J\),PHASE\(J\),FREQ\(J\),NUMARG\(J\),J=\d+,\d+\)\s*\n(.*?)/\s*\n",
                            cnmtx, flags=re.S):
        for entry in re.findall(r"([^,/\n]+,[^,]+,[^,]+,[^,]+,[^,]+),'(\d{3}\.\d{3})'", block):
            values = _numbers(entry[0])
            lines.append(values[-5:])
    sp = re.search(r"DATA \(\(SP\(I,M\),I=1,6\),M=1,2\) /(.*?)/", cnmtx, flags=re.S).group(1)
    sp = np.array(_numbers(sp.replace("\n     .", " "))).reshape(2, 6).T            # SP(I, M), Fortran order
    ortho = _fortran_code(IERS_CH8/"ORTHO_EOP.F")
    w = re.search(r"DATA ORTHOW /(.*?)/", ortho, flags=re.S).group(1)
    w = np.array(_numbers(w.replace("\n     .", " "))).reshape(3, 12).T             # ORTHOW(J, K), column major
    lines = np.array(lines)
    if lines.shape != (71, 5) or sp.shape != (6, 2) or w.shape != (12, 3):
        raise ValueError(f"IERS tables parsed with unexpected shapes {lines.shape}, {sp.shape}, {w.shape}")
    return lines, sp, w


_LINES, _SP, _ORTHOW = None, None, None


def ocean_tidal_eop(mjd):
    """(delta_x uas, delta_y uas, delta_UT1 us) at MJD `mjd`, as IERS ORTHO_EOP."""
    global _LINES, _SP, _ORTHOW
    if _LINES is None:
        _LINES, _SP, _ORTHOW = _tables()
    two_pi = 2*np.pi
    n, m, hs, phase, freq = _LINES.T
    a = {(mm, k): 0. for mm in (1, 2) for k in (-1, 0, 1)}
    b = dict(a)
    for k in (-1, 0, 1):
        t = (mjd-2.*k)-37076.5
        pinm = np.mod(n+m, 2)*two_pi/4.
        alpha = np.mod(phase-pinm, two_pi)+np.mod(freq*t, two_pi)
        for mm in (1, 2):
            sel = m == mm
            a[mm, k] = float(np.sum(hs[sel]*np.cos(alpha[sel])))
            b[mm, k] = float(-np.sum(hs[sel]*np.sin(alpha[sel])))
    h = []
    for mm in (1, 2):
        s = _SP[:, mm-1]
        ap, am = a[mm, 1]+a[mm, -1], a[mm, 1]-a[mm, -1]
        bp, bm = b[mm, 1]+b[mm, -1], b[mm, 1]-b[mm, -1]
        p = (s[0]*a[mm, 0], s[1]*a[mm, 0]-s[2]*ap, s[3]*a[mm, 0]-s[4]*ap+s[5]*bm)
        q = (s[0]*b[mm, 0], s[1]*b[mm, 0]-s[2]*bp, s[3]*b[mm, 0]-s[4]*bp-s[5]*am)
        for k in range(3):
            h += [p[k], q[k]]
    return np.array(h)@_ORTHOW


# ----- rotation ----------------------------------------------------------------------------------------------------
def _r3(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])


def compose(tt, ut1, xp, yp, dx=0., dy=0., cip="series"):
    """GCRS -> ITRS matrix from two-part TT and UT1 JDs, polar motion and celestial pole offsets (radians).
    `cip`: "series" (erfa.xy06, the default) or "angles" (bpn2xy of pnm06a)."""
    if cip == "series":
        x, y = erfa.xy06(*tt)
    elif cip == "angles":
        x, y = erfa.bpn2xy(erfa.pnm06a(*tt))
    else:
        raise ValueError(f"unknown CIP method {cip!r}")
    x, y = x+dx, y+dy
    bpn = erfa.c2ixys(x, y, erfa.s06(*tt, x, y))
    polar = erfa.pom00(xp, yp, erfa.sp00(*tt))
    return polar@_r3(erfa.era00(*ut1))@bpn


class Frame:
    """GCRS -> ITRS rotation at a GPST epoch, from a Finals table, optionally with ocean-tidal sub-daily EOP."""

    def __init__(self, finals, subdaily=False, cip="series"):
        if cip not in ("series", "angles"):
            raise ValueError(f"unknown CIP method {cip!r}")
        self.finals, self.subdaily, self.cip = finals, bool(subdaily), cip

    def times(self, gps_ns):
        """(TT, UT1) as two-part JDs, plus MJD(UTC) and the EOP used, for an integer GPST nanosecond tag."""
        days, rest = divmod(int(gps_ns), DAY_NS)
        tai1, tai2 = 2400000.5+MJD_GPS0+days, (rest/1e9+19.)/86400.
        tt1, tt2 = erfa.taitt(tai1, tai2)
        utc1, utc2 = erfa.taiutc(tai1, tai2)
        mjd_utc = (utc1-2400000.5)+utc2
        xp, yp, dut1, dx, dy = self.finals.at(mjd_utc)
        if self.subdaily:
            sx, sy, sut = ocean_tidal_eop(mjd_utc)
            xp, yp, dut1 = xp+sx*1e-6, yp+sy*1e-6, dut1+sut*1e-6
        ut11, ut12 = erfa.utcut1(utc1, utc2, dut1)
        return (tt1, tt2), (ut11, ut12), mjd_utc, (xp, yp, dut1, dx, dy)

    def rotation(self, gps_ns):
        tt, ut1, _, (xp, yp, _, dx, dy) = self.times(gps_ns)
        return compose(tt, ut1, xp*AS2R, yp*AS2R, dx*1e-3*AS2R, dy*1e-3*AS2R, self.cip)

    def to_itrs(self, gps_ns, gcrs_xyz):
        return self.rotation(gps_ns)@np.asarray(gcrs_xyz, dtype=float)

    def to_gcrs(self, gps_ns, itrs_xyz):
        return self.rotation(gps_ns).T@np.asarray(itrs_xyz, dtype=float)
