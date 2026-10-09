"""External a-priori tropospheric horizontal gradients (BACKLOG B14; experiments/gradients/PROTOCOL.md).

Two sources, each evaluated per station and epoch, then applied by the observation-model hook
`claude.tools.dated_observation.GRADIENT` as a slant-delay addition with the Chen-Herring mapping. Hydrostatic and wet
parts are mapped separately (Landskron and Boehm 2018, eqs. 2-4: C_h = 0.0031, C_w = 0.0007):

    delta(e, az) = mg(e; C_h) * (Gn_h cos az + Ge_h sin az) + mg(e; C_w) * (Gn_w cos az + Ge_w sin az),
    mg(e; C) = 1 / (sin(e) tan(e) + C);   az from north, clockwise (east positive).

- `grad_op`: TU Wien GRAD operational site-wise gradients (`*.grad_g`). Columns: station, MJD, Gn_h, Ge_h, Gn_w, Ge_w,
  in mm (vmf.geo.tuwien.ac.at/products.html), at 00/06/12/18 UT. Linear in time between epochs; any gap over 6 h,
  or a missing station or epoch, is refused. The time argument is MJD(UTC) = GPST - 18 s (valid 2017-), so the
  epochs' UT labels are honoured.
- `gpt3`: the empirical GPT3 gradients of the 1x1 degree grid (`gpt3_1.grd`), following the official gpt3_1.f90:
  - columns a0 A1 B1 A2 B2 per gradient, in 1e-5 m;
  - seasonal terms cos/sin of 2*pi*doy/365.25 and 4*pi*doy/365.25, with doy the calendar day of year plus the
    fraction of the day;
  - bilinear interpolation in polar distance and longitude between cell centres (nearest cell within 0.5 degrees
    of a pole).

No reference product is read. The input files are hashed into `binding()`.

**Arc inputs (3 Oct 2026, defect fix).** Until then `grad_op` loaded and hashed every `.grad_g` file present, so
acquiring files for another date changed a running campaign's binding, and its next worker or resume was refused.
`run_fit_elev` now sets `OPUSFORK_GRADIENT_DAYS` from the fixture (`arc_days`: every UTC day the arc spans plus the
following day, whose midnight brackets the last interval; VALIDATION_PROTOCOL.md amendment A1), and only those files
are read and bound; a missing one is refused. Without that variable (the Stage 1 replay, older tools) every file is
used, as before. The gradient values are unchanged: interpolation reads the same bracketing samples.
"""
from datetime import datetime, timedelta
import hashlib
import math
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE/"datastore/gradients"
ENVIRONMENT = "OPUSFORK_GRADIENTS"
ARC_ENVIRONMENT = "OPUSFORK_GRADIENT_DAYS"
SOURCES = ("none", "grad_op", "gpt3")
C_H, C_W = 0.0031, 0.0007
GPS_UTC_S = 18.
MJD0 = datetime(1858, 11, 17)
GPS0_MJD = 44244


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current():
    name = os.environ.get(ENVIRONMENT, "none")
    if name not in SOURCES:
        raise RuntimeError(f"{ENVIRONMENT} must be one of {SOURCES}, got {name!r}")
    return name


def mapping(elevation, c):
    return 1./(math.sin(elevation)*math.tan(elevation)+c)


def slant(gradients_mm, elevation, azimuth):
    """Slant delay (m) of (Gn_h, Ge_h, Gn_w, Ge_w) in mm at elevation/azimuth (rad)."""
    gnh, geh, gnw, gew = gradients_mm
    ca, sa = math.cos(azimuth), math.sin(azimuth)
    return 1e-3*(mapping(elevation, C_H)*(gnh*ca+geh*sa)+mapping(elevation, C_W)*(gnw*ca+gew*sa))


def utc_mjd(gps_ns):
    return GPS0_MJD+(int(gps_ns)/1e9-GPS_UTC_S)/86400.


# ----- GRAD operational site-wise files ---------------------------------------------------------------------------
class GradSitewise:
    def __init__(self, paths):
        table = {}
        for path in paths:
            for line in Path(path).read_text().splitlines():
                parts = line.split()
                if len(parts) != 6 or parts[0].startswith(("!", "#", "%")):
                    continue
                station, mjd, values = parts[0], float(parts[1]), tuple(map(float, parts[2:]))
                previous = table.setdefault(station, {}).setdefault(mjd, values)
                if previous != values:
                    raise ValueError(f"Conflicting GRAD values for {station} at MJD {mjd}")
        self.table = {s: (np.array(sorted(v)), np.array([v[m] for m in sorted(v)])) for s, v in table.items()}
        self.paths = [str(p) for p in paths]

    def at(self, station, mjd):
        if station not in self.table:
            raise ValueError(f"No GRAD gradients for station {station}")
        times, values = self.table[station]
        k = int(np.searchsorted(times, mjd, side="right"))-1
        if k < 0 or k+1 >= len(times) or times[k+1]-times[k] > 0.25+1e-9:
            raise ValueError(f"GRAD gradients for {station} do not bracket MJD {mjd}")
        w = (mjd-times[k])/(times[k+1]-times[k])
        return tuple(values[k]*(1-w)+values[k+1]*w)


# ----- GPT3 empirical gradients ------------------------------------------------------------------------------------
class Gpt3Gradients:
    def __init__(self, path):
        rows = []
        with open(path) as stream:
            for line in stream:
                if line.startswith("%"):
                    continue
                values = line.split()
                if values:
                    rows.append(values)
        grid = np.array(rows, dtype=float)
        if grid.shape != (64800, 64):
            raise ValueError(f"Unexpected GPT3 1x1 grid shape {grid.shape}")
        # lat lon | p T Q dT (4x5) | undu Hs | ah aw la Tm (4x5) | Gn_h Ge_h Gn_w Ge_w (4x5)
        self.lat, self.lon = grid[:, 0], grid[:, 1]
        self.coefficients = grid[:, 44:64].reshape(64800, 4, 5)*1e-5*1e3   # 1e-5 m -> mm
        self.path = str(path)

    @staticmethod
    def day_of_year(mjd):
        when = MJD0+timedelta(days=float(mjd))
        return float((when.date()-datetime(when.year, 1, 1).date()).days+1)+(mjd-math.floor(mjd))

    def _cell(self, ipod, ilon, seasonal):
        return self.coefficients[(ipod-1)*360+ilon-1]@seasonal

    def at_position(self, lat, lon, mjd):
        """(Gn_h, Ge_h, Gn_w, Ge_w) in mm at geodetic lat/lon (rad) and MJD, as gpt3_1.f90."""
        doy = self.day_of_year(mjd)
        w = 2*math.pi*doy/365.25
        seasonal = np.array([1., math.cos(w), math.sin(w), math.cos(2*w), math.sin(2*w)])
        plon = math.degrees(lon+2*math.pi if lon < 0 else lon)
        ppod = math.degrees(-lat+math.pi/2)
        ipod, ilon = math.floor(ppod+1), math.floor(plon+1)
        diffpod, difflon = ppod-(ipod-0.5), plon-(ilon-0.5)
        ipod = 180 if ipod == 181 else ipod
        ilon = 1 if ilon == 361 else (360 if ilon == 0 else ilon)
        if not 0.5 < ppod < 179.5:
            return tuple(self._cell(ipod, ilon, seasonal))
        ipod1 = ipod+int(math.copysign(1., diffpod))
        ilon1 = ilon+int(math.copysign(1., difflon))
        ilon1 = 1 if ilon1 == 361 else (360 if ilon1 == 0 else ilon1)
        g = [self._cell(a, b, seasonal) for a, b in ((ipod, ilon), (ipod1, ilon), (ipod, ilon1), (ipod1, ilon1))]
        dnpod1, dnlon1 = abs(diffpod), abs(difflon)
        dnpod2, dnlon2 = 1-dnpod1, 1-dnlon1
        r1 = dnpod2*g[0]+dnpod1*g[1]
        r2 = dnpod2*g[2]+dnpod1*g[3]
        return tuple(dnlon2*r1+dnlon1*r2)


# ----- installation -------------------------------------------------------------------------------------------------
def arc_days(origin_ns, duration_s):
    """YYYYDDD of the GRAD daily files an arc needs: every UTC day it spans, plus the following day."""
    first, last = (MJD0+timedelta(days=math.floor(utc_mjd(t))) for t in (origin_ns, int(origin_ns)+int(duration_s*1e9)))
    return [(first+timedelta(days=k)).strftime("%Y%j") for k in range((last-first).days+2)]


def files(source):
    if source == "grad_op":
        days = os.environ.get(ARC_ENVIRONMENT)
        if days is None:        # no arc declared: every file present (the Stage 1 replay; behaviour before 3 Oct 2026)
            return sorted((DATA/"GRAD_OP").glob("*.grad_g"))
        names = days.split(",")
        if not names or not all(len(n) == 7 and n.isdigit() for n in names):
            raise RuntimeError(f"{ARC_ENVIRONMENT} must list YYYYDDD days, got {days!r}")
        paths = [DATA/"GRAD_OP"/f"{n}.grad_g" for n in names]
        missing = [p.name for p in paths if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"GRAD operational files missing for this arc: {', '.join(missing)} "
                                    "(Opus_Fork/experiments/gradients/acquire_day.sh)")
        return paths
    if source == "gpt3":
        return [DATA/"gpt3/gpt3_1.grd"]
    return []


def binding(source=None):
    source = current() if source is None else source
    if source == "none":
        return None
    return dict(source=source, convention="Chen-Herring, hydrostatic C=0.0031 and wet C=0.0007, mm, az from north",
                module_sha256=sha(__file__), inputs={p.name: sha(p) for p in files(source)})


def field(source):
    if source == "grad_op":
        return GradSitewise(files(source))
    if source == "gpt3":
        return Gpt3Gradients(files(source)[0])
    raise ValueError(f"No gradient field for {source!r}")


def hook(source):
    """GRADIENT(products, row, g) -> slant delay (m), for `claude.tools.dated_observation.GRADIENT`.

    The epoch is the row's receive time on the products' GPST origin; tangent and perturbed product wrappers are
    walked to their base. GPT3 is evaluated at each station's geodetic latitude/longitude, taken once from the first
    row's receiver position (tidal displacements of millimetres do not matter on a 1-degree grid).
    """
    from customkf.measurement import geodetic
    model = field(source)
    places = {}

    def gradient(products, row, g):
        base = products
        while not hasattr(base, "origin_ns") and hasattr(base, "base"):     # tangent/perturbed product wrappers
            base = base.base
        mjd = utc_mjd(int(base.origin_ns)+int(round(float(g["receive_s"])*1e9)))
        if source == "grad_op":
            values = model.at(row["station"], mjd)
        else:
            if row["station"] not in places:
                lat, lon, _ = geodetic(row["receiver_xyz"])
                places[row["station"]] = (float(lat), float(lon))
            values = model.at_position(*places[row["station"]], mjd)
        return slant(values, float(g["elevation_rad"]), float(g["azimuth_rad"]))
    return gradient
