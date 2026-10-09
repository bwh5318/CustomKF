"""Independent oracle O1: SP3 reading and raw orbit metrics (docs/consolidation/CONTRACTS_AND_ORACLE.md §4).

Extracted from Astra's review scorer `research/opus_work_review_20260926/recompute.py` (`sp3`, `summarize`). That code
was written independently of the project's evaluators; its one project dependency, `customkf.frames`, is replaced by
the separately written frame of `validation.oracle.frame` (O2). Nothing here imports `customkf` or `Opus_Fork`.

Conventions, as in the review scorer:
- GPS satellites only; zero positions skipped; records flagged as maneuver ("M", column 79) or predicted ("P",
  column 80) are skipped;
- along-track/cross-track from the reference's own velocity: a local 9-point polynomial in the inertial frame;
- orbit-only URE = sqrt(mean(0.98^2 R^2 + (A^2 + C^2)/49)).
"""
from datetime import datetime, timedelta
import gzip
from pathlib import Path

import numpy as np

GPS0 = datetime(1980, 1, 6)


def read_sp3(path):
    """{(satellite, GPST ns): ECEF position (m)} for GPS satellites.

    Refuses (ValueError), since 8 Oct 2026 (Astra PI-11): a declared time system other than GPS (SP3-a's unspecified
    "ccc" is read as GPS, as the products here declare); a position record before any epoch; a duplicate
    satellite-epoch; a non-finite position. Files without these defects read exactly as before."""
    data = Path(path).read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    values, ns, declared = {}, None, False
    for line in data.decode("ascii").splitlines():
        if line.startswith("%c") and not declared:
            declared = True
            if line[9:12] not in ("GPS", "ccc"):
                raise ValueError(f"{path}: time system {line[9:12]!r} is not GPS")
        elif line.startswith("*"):
            f = line[1:].split()
            when = datetime(*map(int, f[:5]))+timedelta(seconds=float(f[5]))
            ns = int(round((when-GPS0).total_seconds()*1e9))
        elif line.startswith("P"):
            if ns is None:
                raise ValueError(f"{path}: position record before any epoch")
            sat = line[1:4].strip()
            if sat.isdigit():
                sat = "G"+sat.zfill(2)
            if not sat.startswith("G"):
                continue
            xyz = np.array([float(line[k:k+14]) for k in (4, 18, 32)])*1000
            if not np.all(np.isfinite(xyz)):
                raise ValueError(f"{path}: non-finite position for {sat} at {ns}")
            if np.all(xyz == 0):
                continue
            if len(line) > 78 and (line[78] == "M" or (len(line) > 79 and line[79] == "P")):
                continue
            if (sat, ns) in values:
                raise ValueError(f"{path}: duplicate record for {sat} at {ns}")
            values[sat, ns] = xyz
    return values


def solution_ecef(states, satellites, times_s, origin_ns, frame):
    """{(satellite, GPST ns): ECEF} from a solution's inertial states (m) on its time grid, through `frame`."""
    out = {}
    for k, t in enumerate(times_s):
        tag = int(origin_ns)+int(round(float(t)*1e9))
        r = frame.rotation(tag)
        for i, s in enumerate(satellites):
            out[str(s), tag] = r@np.asarray(states[i, k, :3], dtype=float)
    return out


def summarize(reference, candidate, frame, keys):
    """Raw (unaligned) differences candidate - reference on `keys`: RMS 3D, R/A/C RMS and orbit-only URE (m)."""
    rotations = {t: frame.rotation(t) for _, t in reference}
    per = {}
    for s, t in sorted(reference):
        per.setdefault(s, []).append(t)
    rows, squares = [], []
    for s, t in sorted(keys):
        ts = np.array(per[s], dtype=np.int64)
        k = int(np.searchsorted(ts, t))
        lo = max(0, min(k-4, len(ts)-9))
        ix = ts[lo:lo+9]
        x = (ix-t)/1e9/900.
        positions = np.array([rotations[int(q)].T@reference[s, int(q)] for q in ix])
        coefficients = np.linalg.solve(np.vander(x, N=9, increasing=True), positions)
        velocity = coefficients[1]/900.
        r = rotations[t].T@reference[s, t]
        delta = rotations[t].T@(candidate[s, t]-reference[s, t])
        radial = r/np.linalg.norm(r)
        cross = np.cross(r, velocity)
        cross /= np.linalg.norm(cross)
        along = np.cross(cross, radial)
        rows.append([delta@radial, delta@along, delta@cross])
        squares.append(delta@delta)
    a, d2 = np.array(rows), np.array(squares)
    ure2 = .98**2*a[:, 0]**2+(a[:, 1]**2+a[:, 2]**2)/49.
    return dict(samples=len(keys), satellites=len({s for s, _ in keys}), rms_3d_m=float(np.sqrt(d2.mean())),
                rms_rac_m=np.sqrt((a*a).mean(axis=0)).tolist(), orbit_ure_m=float(np.sqrt(ure2.mean())))
