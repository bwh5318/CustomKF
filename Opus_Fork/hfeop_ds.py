"""Desai & Sibois (2016) diurnal/semidiurnal ocean-tidal EOP model: the high-frequency EOP model of IGS repro3/ITRF2020.

Coefficients: `datastore/static/hfeop/desai_model_jgrb51665-sup-0002-ds01.txt`, the supporting table of Desai, S. D. and
Sibois, A. E. (2016), "Evaluating predicted diurnal and semidiurnal tidal variations in polar motion with GPS-based
observations", JGR Solid Earth 121, doi:10.1002/2016JB013125. Retrieved 26 September 2026 from the IVS high-frequency
EOP working group (https://ivscc.gsfc.nasa.gov/hfeop_wg/models/); SHA-256 in SOURCE below.

Each of the 159 lines gives Delaunay multipliers (l, l', F, D, Omega), a multiplier gamma of (GMST + pi), and sine/cosine
amplitudes for x, y (uas), UT1 (us) and LOD. The argument is theta = gamma*(GMST+pi) + sum N_j F_j. Checked against the
Doodson numbers: M2 (255.555) gives 2*tau, O1 (145.555) gives tau - s, and S2 (273.555) gives twice the mean solar time.
The correction is sum(S sin theta + C cos theta). Libration terms are not included. Corrected 27 Sep 2026 (Astra
review N04): an earlier "under about 2 mm at GPS altitude" was never computed. The IERS UTLIBR test value (-2.66 us)
is about 5.1 mm at 26,560 km, and PMSDNUT2's test gives about 3.7 mm. The omission over these arcs is not quantified.
TT_MINUS_UTC_S below is hard-coded for 2026 (37 leap seconds) and needs an epoch-aware value for other dates.

Same interface as `Opus_Fork.subdaily_eop` (which stays unchanged: the SD campaigns pin it), so it can be swapped in
for a test: `ds_eop(mjd)`, `earth_orientation_class()`, `install()` (through the `EarthOrientation.subdaily` hook).

Why (26 Sep 2026, results/SDEOP_RESULTS.md): with ORTHO_EOP (IERS 2010, Ray 1994) in the POD, a 0.45–1.07 cm
constellation-wide 12 h radial swing against IGS final remains. NGA PE shows 0.34–0.73 cm against IGS. IGS switched to this
model for repro3/IGS20, so part of that residual may be the ORTHO-vs-Desai-Sibois difference.
"""
import hashlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = ("datastore/static/hfeop/desai_model_jgrb51665-sup-0002-ds01.txt",
          "53398e40b70ccfa411d292e9a7f752a01cbac1be07d4e7fb18906d6481e57dd8")
TT_MINUS_UTC_S = 69.184  # 37 s leap seconds (since 2017) + 32.184 s; tidal arguments are insensitive to it at this level


def _table():
    path = HERE/SOURCE[0]
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE[1], "Desai-Sibois coefficient file changed"
    rows = []
    for line in data.decode().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        f = line.split()
        rows.append([float(x) for x in f[1:7]]+[float(x) for x in f[9:15]])
    table = np.array(rows)
    assert table.shape == (159, 12), table.shape
    return table


_T = None


def ds_eop(mjd):
    """(delta_x uas, delta_y uas, delta_UT1 us) at UTC MJD `mjd` (scalar or array); shape (..., 3)."""
    import erfa
    global _T
    if _T is None:
        _T = _table()
    mjd = np.asarray(mjd, dtype=float)
    tt = mjd+TT_MINUS_UTC_S/86400.
    t = (tt-51544.5)/36525.
    fundamental = np.stack([erfa.fal03(t), erfa.falp03(t), erfa.faf03(t), erfa.fad03(t), erfa.faom03(t)], axis=-1)
    gmst = erfa.gmst06(2400000.5, mjd, 2400000.5, tt)  # UT1-UTC (< 1 s) is negligible for tidal arguments
    theta = _T[:, 0]*(gmst[..., None]+np.pi)+fundamental@_T[:, 1:6].T
    s, c = np.sin(theta), np.cos(theta)
    return np.stack([s@_T[:, 6]+c@_T[:, 7], s@_T[:, 8]+c@_T[:, 9], s@_T[:, 10]+c@_T[:, 11]], axis=-1)


def earth_orientation_class():
    """`EarthOrientation` subclass with this model on its `subdaily` hook (for scoring beside plain-EOP arms)."""
    from customkf.frames import EarthOrientation

    class DesaiSiboisEarthOrientation(EarthOrientation):
        subdaily = staticmethod(ds_eop)
    return DesaiSiboisEarthOrientation


def install():
    """Put this model on `customkf.frames.EarthOrientation.subdaily`, so every instance in this process adds it."""
    from customkf.frames import EarthOrientation
    current = EarthOrientation.__dict__.get("subdaily")
    if current is not None and getattr(current, "__func__", None) is not ds_eop:
        raise RuntimeError("A different sub-daily EOP model is already installed in this process")
    EarthOrientation.subdaily = staticmethod(ds_eop)
