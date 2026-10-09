"""Stage 0 SI-unit, GPS-only comparison mathematics. No propagation or interpolation.

Reference position and inertial velocity must be expressed in the same axes.
The caller owns the dated terrestrial/celestial transformation and EOP vintage.
"""
import numpy as np

C_LIGHT = 299792458.0


def vectors(value, name):
    result = np.asarray(value, dtype=np.float64)
    if result.shape[-1:] != (3,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain finite 3-vectors")
    return result


def rac_basis(position_m, inertial_velocity_mps):
    r = vectors(position_m, "position")
    v = vectors(inertial_velocity_mps, "inertial velocity")
    if r.shape != v.shape:
        raise ValueError("Position/velocity shapes differ")
    rn = np.linalg.norm(r, axis=-1, keepdims=True)
    vn = np.linalg.norm(v, axis=-1, keepdims=True)
    cross = np.cross(r, v)
    cn = np.linalg.norm(cross, axis=-1, keepdims=True)
    if np.any(rn == 0) or np.any(vn == 0) or np.any(cn <= 1e-12*rn*vn):
        raise ValueError("Undefined orbital plane: zero or parallel position/velocity")
    radial, normal = r/rn, cross/cn
    return np.stack((radial, np.cross(normal, radial), normal), axis=-2)


def rac_difference(reference_m, candidate_m, reference_inertial_velocity_mps):
    ref, candidate = vectors(reference_m, "reference"), vectors(candidate_m, "candidate")
    if candidate.shape != ref.shape:
        raise ValueError("Candidate/reference shapes differ")
    basis = rac_basis(ref, reference_inertial_velocity_mps)
    return np.einsum("...ij,...j->...i", basis, candidate-ref)


def orbit_ure_m(rac_m):
    rac = vectors(rac_m, "RAC")
    return np.sqrt((.98*rac[..., 0])**2 + (rac[..., 1]**2+rac[..., 2]**2)/49)


def clock_sisre_m(rac_m, candidate_minus_reference_clock_s):
    rac = vectors(rac_m, "RAC")
    clock = np.asarray(candidate_minus_reference_clock_s, dtype=np.float64)
    if clock.shape != rac.shape[:-1] or not np.isfinite(clock).all():
        raise ValueError("Clock must be finite and match the sample shape")
    return np.sqrt((.98*rac[..., 0]-C_LIGHT*clock)**2 +
                   (rac[..., 1]**2+rac[..., 2]**2)/49)


def remove_epoch_clock_datum(epoch_ns, clock_difference_s):
    epochs = np.asarray(epoch_ns)
    clock = np.asarray(clock_difference_s, dtype=np.float64)
    if (epochs.ndim != 1 or epochs.dtype.kind not in "iu" or epochs.shape != clock.shape
            or not np.isfinite(clock).all()):
        raise ValueError("Require one finite clock per epoch/sample")
    centered = clock.copy()
    offsets = {}
    for epoch in np.unique(epochs):
        selected = epochs == epoch
        offsets[int(epoch)] = float(np.mean(clock[selected]))
        centered[selected] -= offsets[int(epoch)]
    return centered, offsets


def summarize(rac_m):
    rac = vectors(rac_m, "RAC")
    if rac.ndim != 2 or not len(rac):
        raise ValueError("Cannot summarize an empty or non-tabular comparison")
    rms = np.sqrt(np.mean(rac**2, axis=0))
    return {"samples":len(rac), "rms_rac_m":rms.tolist(),
            "rms_3d_m":float(np.sqrt(np.mean(np.sum(rac**2, axis=1)))),
            "rms_orbit_ure_m":float(np.sqrt(np.mean(orbit_ure_m(rac)**2))),
            "mean_rac_m":np.mean(rac, axis=0).tolist()}
