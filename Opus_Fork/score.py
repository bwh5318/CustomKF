"""Multi-reference orbit scoring under the frozen comparison contract.

Primary score is always raw, unaligned, candidate-minus-reference, equal weight per
retained satellite-epoch (COMPARISON_CONTRACT.md). A 7-parameter Helmert fit is
computed only as a separately labelled diagnostic and never replaces a raw number.

Reference inertial velocity comes from the reference product's own positions through
`customkf.precise.polynomial_state`, so R/A/C axes are the reference's orbital frame
expressed in the same inertial axes as the reference position, as the contract requires.
"""
from dataclasses import dataclass
import numpy as np

from customkf.comparison import orbit_ure_m
from customkf.frames import FrameEpoch
from customkf.precise import polynomial_state
from customkf.sp3 import read_sp3


@dataclass(frozen=True)
class Declared:
    """Provenance a caller must state; headers alone do not establish these."""
    label: str
    frame: str               # the literal SP3 frame label
    origin: str              # "COM" or "APC" - declared, not inferred
    legacy_a_time_system: str | None = None


class Product:
    """One SP3 orbit product with declared conventions, in inertial axes.

    Positions are rotated to the celestial frame with the pinned EOP and ERFA
    IAU 2006/2000A chain (not the historical approximate GMST rotation), so the
    comparison is frame-consistent apart from the terrestrial realization itself.
    """

    def __init__(self, path, declared, origin_ns, eop):
        self.path, self.declared = path, declared
        self.raw = read_sp3(path, legacy_a_time_system=declared.legacy_a_time_system)
        if self.raw.frame != declared.frame:
            raise ValueError(f"{declared.label}: frame {self.raw.frame!r} != declared {declared.frame!r}")
        self.origin_ns = int(origin_ns)
        self.epoch = FrameEpoch(self.origin_ns, eop)
        self._rotations = {}
        inertial = {}
        for row in self.raw.samples.values():
            if row.xyz_m is None or row.maneuver or row.orbit_predicted:
                continue
            t = (row.epoch_ns-self.origin_ns)/1e9
            inertial.setdefault(row.sat, {})[t] = self.rotation(t).T@np.asarray(row.xyz_m)
        self.inertial = {s: (np.array(sorted(d)), np.array([d[t] for t in sorted(d)]))
                         for s, d in inertial.items()}

    def rotation(self, t):
        if t not in self._rotations:
            self._rotations[t] = self.epoch.celestial_to_terrestrial(t)
        return self._rotations[t]

    def keys(self):
        """(satellite, absolute GPS ns) for every sample valid under the contract."""
        return {(r.sat, r.epoch_ns) for r in self.raw.samples.values()
                if r.xyz_m is not None and not r.maneuver and not r.orbit_predicted}

    def position(self, sat, t):
        """Inertial position at an exact stored sample time; no interpolation."""
        times, values = self.inertial[sat]
        k = int(np.searchsorted(times, t))
        if k >= len(times) or abs(times[k]-t) > 1e-6:
            raise ValueError("Requested time is not a stored sample")
        return values[k]

    def velocity(self, sat, t):
        """Inertial velocity by local barycentric differentiation of this product."""
        return polynomial_state(*self.inertial[sat], t)[3:]


def rac(reference, candidate, sat, t):
    """Candidate-minus-reference difference on the reference's R/A/C axes."""
    r = reference.position(sat, t)
    v = reference.velocity(sat, t)
    d = candidate.position(sat, t)-r
    radial = r/np.linalg.norm(r)
    cross = np.cross(r, v)
    normal = cross/np.linalg.norm(cross)
    along = np.cross(normal, radial)
    return np.array([d@radial, d@along, d@normal])


def pooled(values):
    a = np.asarray(values, dtype=float)
    if a.ndim != 2 or not len(a):
        raise ValueError("Cannot summarize an empty comparison")
    return dict(samples=int(len(a)),
                rms_3d_m=float(np.sqrt(np.mean(np.sum(a**2, axis=1)))),
                rms_rac_m=np.sqrt(np.mean(a**2, axis=0)).tolist(),
                rms_orbit_ure_m=float(np.sqrt(np.mean(orbit_ure_m(a)**2))),
                mean_rac_m=np.mean(a, axis=0).tolist())


def helmert_residual(reference, candidate, keys):
    """DIAGNOSTIC ONLY: per-epoch 7-parameter similarity fit in terrestrial axes.

    Returns the residual RAC table and the fitted parameters per epoch. This
    measures how much of the difference a datum/scale/orientation change could
    absorb. It is never the reported score.
    """
    residual, parameters = {}, {}
    by_epoch = {}
    for sat, ns in keys:
        by_epoch.setdefault(ns, []).append(sat)
    for ns, sats in sorted(by_epoch.items()):
        if len(sats) < 4:
            continue
        t = (ns-reference.origin_ns)/1e9
        rot = reference.rotation(t)
        ref = np.array([rot@reference.position(s, t) for s in sats])
        can = np.array([rot@candidate.position(s, t) for s in sats])
        design = np.zeros((3*len(sats), 7))
        for i, p in enumerate(ref):
            design[3*i:3*i+3, :3] = np.eye(3)
            design[3*i:3*i+3, 3:6] = np.array([[0, p[2], -p[1]], [-p[2], 0, p[0]], [p[1], -p[0], 0]])
            design[3*i:3*i+3, 6] = p
        solution, *_ = np.linalg.lstsq(design, (can-ref).reshape(-1), rcond=None)
        left = (can-ref).reshape(-1)-design@solution
        parameters[int(ns)] = dict(translation_m=solution[:3].tolist(),
                                   rotation_rad=solution[3:6].tolist(), scale=float(solution[6]))
        for i, s in enumerate(sats):
            inertial = rot.T@left[3*i:3*i+3]
            r = reference.position(s, t)
            v = reference.velocity(s, t)
            radial = r/np.linalg.norm(r)
            normal = np.cross(r, v)/np.linalg.norm(np.cross(r, v))
            residual[s, ns] = np.array([inertial@radial, inertial@np.cross(normal, radial), inertial@normal])
    return residual, parameters
