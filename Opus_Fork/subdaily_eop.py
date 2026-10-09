"""Diurnal/semidiurnal ocean-tidal variations of polar motion and UT1 (IERS Conventions 2010, Chapter 8).

Derived work, not IERS software: a Python port of the IERS Conventions routines ORTHO_EOP.F and CNMTX.F
(R. Eanes 1997; B.E. Stetzler 2008-2010), retrieved 25 September 2026 from
https://iers-conventions.obspm.fr/conventions/content/chapter8/software/ into
`Opus_Fork/datastore/static/iers_ch8/` (SHA-256 in IERS_SOURCES below). The algorithm, the 71 tidal lines
and the 12x3 orthoweights are unchanged; the routines are renamed (`tidal_potential_partials`,
`ocean_tidal_eop`) and vectorised over time. The IERS Conventions Software License applies to the
original routines; their notice is kept in the retrieved files. Libration terms (PMSDNUT2, UTLIBR) are
not included here. This module is neither distributed by nor endorsed by the IERS Conventions Center.

Why (25 Sep 2026, results/SWING_ORIGIN_NOTES.md): `customkf.frames.EarthOrientation.at` interpolates the
daily IERS finals values linearly, and those values exclude the sub-daily ocean-tidal terms that IERS
analysis centres apply. An unmodelled UT1 wobble rotates every GPS satellite along-track in the same
sense (cos i is the same for all planes); a dynamic fit can only absorb that through eccentricity,
leaving a radial residual once per revolution with the same UT phase on every satellite, which is what
the census shows on Aug 2-5.

`install()` sets the opt-in hook `customkf.frames.EarthOrientation.subdaily` (default None) for every instance in the
process. History: until 26 Sep 2026 it replaced `EarthOrientation.at` with a wrapper (the version the five SD
campaigns pinned). The hook was then added to `customkf/frames.py` with the user's approval
(`results/subdaily_eop_handoff/`). The two produce bit-identical `at` results, verified on 997 epochs and by re-running
the Aug 2 census and the SD-2 scoring.
"""
import hashlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
IERS_SOURCES = {
    "datastore/static/iers_ch8/ORTHO_EOP.F": "dfd1524b583f2a0f11baf2f03282d0f5ba5731026ac1fdaff4aa6e9460995022",
    "datastore/static/iers_ch8/CNMTX.F": "8a29c599275110990e6ce93254995d498edbccc523edb2de508455736f45fc93",
}

# CNMTX: (n, m, amplitude HS, phase, frequency rad/day) for the 71 dominant lines of the
# Cartwright-Tayler-Edden degree-2 potential (the Doodson numbers are in CNMTX.F).
_LINES = np.array([
    (1, -1.94, 9.0899831, 5.18688050), (1, -1.25, 8.8234208, 5.38346657), (1, -6.64, 12.1189598, 5.38439079),
    (1, -1.51, 1.4425700, 5.41398343), (1, -8.02, 4.7381090, 5.41490765), (1, -9.47, 4.4715466, 5.61149372),
    (1, -50.20, 7.7670857, 5.61241794), (1, -1.80, -2.9093042, 5.64201057), (1, -9.54, 0.3862349, 5.64293479),
    (1, 1.52, -3.1758666, 5.83859664), (1, -49.45, 0.1196725, 5.83952086), (1, -262.21, 3.4152116, 5.84044508),
    (1, 1.70, 12.8946194, 5.84433381), (1, 3.43, 5.5137686, 5.87485066), (1, 1.94, 6.4441883, 6.03795537),
    (1, 1.37, -4.2322016, 6.06754801), (1, 7.41, -0.9366625, 6.06847223), (1, 20.62, 8.5427453, 6.07236095),
    (1, 4.14, 11.8382843, 6.07328517), (1, 3.94, 1.1618945, 6.10287781), (1, -7.14, 5.9693878, 6.24878055),
    (1, 1.37, -1.2032249, 6.26505830), (1, -122.03, 2.0923141, 6.26598252), (1, 1.02, -1.7847596, 6.28318449),
    (1, 2.89, 8.0679449, 6.28318613), (1, -7.30, 0.8953321, 6.29946388), (1, 368.78, 4.1908712, 6.30038810),
    (1, 50.01, 7.4864102, 6.30131232), (1, -1.08, 10.7819493, 6.30223654), (1, 2.93, 0.3137975, 6.31759007),
    (1, 5.25, 6.2894282, 6.33479368), (1, 3.95, 7.2198478, 6.49789839), (1, 20.62, -0.1610030, 6.52841524),
    (1, 4.09, 3.1345361, 6.52933946), (1, 3.42, 2.8679737, 6.72592553), (1, 1.69, -4.5128771, 6.75644239),
    (1, 11.29, 4.9665307, 6.76033111), (1, 7.23, 8.2620698, 6.76125533), (1, 1.51, 11.5576089, 6.76217955),
    (1, 2.16, 0.6146566, 6.98835826), (1, 1.38, 3.9101957, 6.98928248),
    (2, 1.80, 20.6617051, 11.45675174), (2, 4.67, 13.2808543, 11.48726860), (2, 16.01, 16.3098310, 11.68477889),
    (2, 19.32, 8.9289802, 11.71529575), (2, 1.30, 5.0519065, 11.73249771), (2, -1.02, 15.8350306, 11.89560406),
    (2, -4.51, 8.6624178, 11.91188181), (2, 120.99, 11.9579569, 11.91280603), (2, 1.13, 8.0808832, 11.93000800),
    (2, 22.98, 4.5771061, 11.94332289), (2, 1.06, 0.7000324, 11.96052486), (2, -1.90, 14.9869335, 12.11031632),
    (2, -2.18, 11.4831564, 12.12363121), (2, -23.58, 4.3105437, 12.13990896), (2, 631.92, 7.6060827, 12.14083318),
    (2, 1.92, 3.7290090, 12.15803515), (2, -4.66, 10.6350594, 12.33834347), (2, -17.86, 3.2542086, 12.36886033),
    (2, 4.47, 12.7336164, 12.37274905), (2, 1.97, 16.0291555, 12.37367327), (2, 17.20, 10.1602590, 12.54916865),
    (2, 294.00, 6.2831853, 12.56637061), (2, -2.46, 2.4061116, 12.58357258), (2, -1.02, 5.0862033, 12.59985198),
    (2, 79.96, 8.3817423, 12.60077620), (2, 23.83, 11.6772814, 12.60170041), (2, 2.59, 14.9728205, 12.60262463),
    (2, 4.47, 4.0298682, 12.82880334), (2, 1.95, 7.3254073, 12.82972756), (2, 1.17, 9.1574019, 13.06071921),
])
assert len(_LINES) == 71
_SP = {1: (0.0298, 0.1408, 0.0805, 0.6002, 0.3025, 0.1517), 2: (0.0200, 0.0905, 0.0638, 0.3476, 0.1645, 0.0923)}
# ORTHO_EOP orthoweights, ORTHOW(12,3) in Fortran column order: columns x (uas), y (uas), UT1 (us).
_ORTHOW = np.array([
    [-6.77832, -14.86323, 0.47884, -1.45303, 0.16406, 0.42030, 0.09398, 25.73054, -4.77974, 0.28080, 1.94539, -0.73089],
    [14.86283, -6.77846, 1.45234, 0.47888, -0.42056, 0.16469, 15.30276, -4.30615, 0.07564, 2.28321, -0.45717, -1.62010],
    [-1.76335, 1.03364, -0.27553, 0.34569, -0.12343, -0.10146, -0.47119, 1.28997, -0.19336, 0.02724, 0.08955, 0.04726],
]).T
_TWOPI, _D1960, _DT = 2*np.pi, 37076.5, 2.


def tidal_potential_partials(mjd):
    """CNMTX: the 12 partials H of the orthoweight model at MJD `mjd` (scalar or array); shape (..., 12)."""
    mjd = np.asarray(mjd, dtype=float)
    m_of, hs, phase, freq = _LINES[:, 0].astype(int), _LINES[:, 1], _LINES[:, 2], _LINES[:, 3]
    pinm = ((2+m_of) % 2)*_TWOPI/4
    anm, bnm = {}, {}
    for k in (-1, 0, 1):
        dt60 = (mjd - k*_DT) - _D1960
        alpha = np.mod(phase - pinm, _TWOPI) + np.mod(freq*dt60[..., None], _TWOPI)
        for m in (1, 2):
            sel = m_of == m
            anm[m, k] = (hs[sel]*np.cos(alpha[..., sel])).sum(-1)
            bnm[m, k] = -(hs[sel]*np.sin(alpha[..., sel])).sum(-1)
    h = []
    for m in (1, 2):
        s = _SP[m]
        ap, am = anm[m, 1]+anm[m, -1], anm[m, 1]-anm[m, -1]
        bp, bm = bnm[m, 1]+bnm[m, -1], bnm[m, 1]-bnm[m, -1]
        p = (s[0]*anm[m, 0], s[1]*anm[m, 0]-s[2]*ap, s[3]*anm[m, 0]-s[4]*ap+s[5]*bm)
        q = (s[0]*bnm[m, 0], s[1]*bnm[m, 0]-s[2]*bp, s[3]*bnm[m, 0]-s[4]*bp-s[5]*am)
        for k in range(3):
            h += [p[k], q[k]]
    return np.stack(h, axis=-1)


def ocean_tidal_eop(mjd):
    """ORTHO_EOP: (delta_x uas, delta_y uas, delta_UT1 us) at MJD `mjd`; shape (..., 3)."""
    return tidal_potential_partials(mjd) @ _ORTHOW


def self_test():
    """The IERS test case of ORTHO_EOP.F (MJD 47100)."""
    got = ocean_tidal_eop(47100.)
    want = np.array([-162.8386373279636530, 117.7907525842668974, -23.39092370609808214])
    assert np.allclose(got, want, rtol=0, atol=1e-9), (got, want)
    return got


def verify_sources():
    for rel, digest in IERS_SOURCES.items():
        assert hashlib.sha256((HERE/rel).read_bytes()).hexdigest() == digest, rel


def earth_orientation_class():
    """`EarthOrientation` subclass with this model on its `subdaily` hook, for use beside the plain class in one process
    (the evaluator needs both: plain for IGS/NGA and old arms, sub-daily for arms fitted with it)."""
    from customkf.frames import EarthOrientation

    class SubdailyEarthOrientation(EarthOrientation):
        subdaily = staticmethod(ocean_tidal_eop)
    return SubdailyEarthOrientation


def install():
    """Put this model on `customkf.frames.EarthOrientation.subdaily`, so every instance in this process adds it."""
    from customkf.frames import EarthOrientation
    current = EarthOrientation.__dict__.get("subdaily")
    if current is not None and getattr(current, "__func__", None) is not ocean_tidal_eop:
        raise RuntimeError("A different sub-daily EOP model is already installed in this process")
    EarthOrientation.subdaily = staticmethod(ocean_tidal_eop)
