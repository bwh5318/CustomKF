"""Guarded Helmert decomposition of the 14-station orbit error field against IGS.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.frame_decomposition

The calibration diagnostic showed a small pooled cross-track offset. This asks how much of the
0.8211 m error field looks like a single global datum effect rather than 31 independent orbit
errors: least squares of the 403 ECEF error vectors against translation, rotation and scale, in
the frame where the fixed station coordinates live. A rotation or scale would point at the station
frame, EOP or the clock datum; per-satellite structure would not.

Read-only over the GUAM archive, its fixture and the pinned IGS reference. No fit, no data editing,
no root source touched, and nothing here changes the project's scoring, which deliberately applies
no Helmert alignment. On a single three-hour arc these parameters are partly degenerate with real
orbit error, so this is a decomposition and not attribution. Writes only frame.json.
"""
import json
import os
from pathlib import Path

import numpy as np

from customkf.stage5_pilot import ORIGIN
from customkf.comparison import rac_basis
from claude.tools.evaluate_ablation import Reference
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)
MAS = 4.84813681109536e-9  # radians per milliarcsecond
MODELS = {"translation": (0, 1, 2), "rotation": (4, 5, 6), "scale": (3,),
          "rotation_scale": (3, 4, 5, 6), "full_helmert": (0, 1, 2, 3, 4, 5, 6)}


def rms(values):
    values = np.asarray(values, float)
    return float(np.sqrt(np.mean(np.sum(values.reshape(-1, 3)**2, axis=1))))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    for name in (f"{base['final']}/solution.npz", "prepare/fixture.json"):
        assert sha(GUAM / name) == base["artifacts_sha256"][name], name
    fit = np.load(GUAM / base["final"] / "solution.npz")
    reference = Reference()
    satellites = [str(s) for s in fit["satellites"]]
    times = [float(v) for v in fit["times_s"]]
    rows, errors, labels, bases = [], [], [], []
    for si, sat in enumerate(satellites):
        for ti, t in enumerate(times):
            expected = reference.rac(sat, t, fit["states"][si, ti, :3])
            if expected is None:
                continue
            sample = reference.raw.samples[(ORIGIN + int(round(t * 1e9)), sat)]
            rotation = reference.epoch.celestial_to_terrestrial(t)
            position = np.asarray(sample.xyz_m, float)
            error = rotation @ fit["states"][si, ti, :3] - position
            inertial = rotation.T @ position
            basis = rac_basis(inertial, reference.precise.state(sat, t)[3:])
            # Same error the evaluator scores, expressed in the terrestrial frame. The extra
            # rotate-out-and-back costs a few nanometres, so this uses the project's 2e-8 m
            # cross-check tolerance rather than an exact comparison.
            np.testing.assert_allclose(basis @ (rotation.T @ error), expected, rtol=0, atol=2e-8)
            x, y, z = position
            # Columns: translation (m), scale (ppb), rotation (mas) about X, Y, Z.
            block = np.zeros((3, 7))
            block[:, :3] = np.eye(3)
            block[:, 3] = position * 1e-9
            block[:, 4:] = np.array([[0., z, -y], [-z, 0., x], [y, -x, 0.]]) * MAS
            rows.append(block)
            errors.append(error)
            labels.append((sat, ti))
            bases.append(basis @ rotation.T)
    design = np.vstack(rows)
    observed = np.concatenate(errors)
    samples = len(errors)
    assert samples == 403 and design.shape == (3 * samples, 7)
    report = {"status": "frame_decomposition_diagnostic_not_an_alignment_or_attribution",
              "source_policy": policy, "baseline": GUAM.relative_to(ROOT).as_posix(),
              "baseline_manifest_sha256": sha(GUAM / "validation.json"), "reference_sha256": reference.sha256,
              "samples": samples, "units": {"translation": "m", "scale": "ppb", "rotation": "mas"},
              "before": {"rms_3d_m": rms(observed),
                         "rms_rac_m": [float(np.sqrt(np.mean([(b @ e)[k]**2 for b, e in zip(bases, errors)]))) for k in range(3)],
                         "mean_rac_m": [float(np.mean([(b @ e)[k] for b, e in zip(bases, errors)])) for k in range(3)]},
              "models": {}}
    names = ["translation_x", "translation_y", "translation_z", "scale", "rotation_x", "rotation_y", "rotation_z"]
    for model, columns in MODELS.items():
        sub = design[:, list(columns)]
        estimate, _, rank, _ = np.linalg.lstsq(sub, observed, rcond=None)
        assert rank == len(columns), model
        residual = observed - sub @ estimate
        degrees = 3 * samples - len(columns)
        variance = float(residual @ residual) / degrees
        sigma = np.sqrt(variance * np.diag(np.linalg.inv(sub.T @ sub)))
        pieces = [residual[i * 3:(i + 1) * 3] for i in range(samples)]
        report["models"][model] = {
            "parameters": {names[c]: {"value": float(estimate[i]), "sigma": float(sigma[i]), "ratio": float(estimate[i] / sigma[i])}
                           for i, c in enumerate(columns)},
            "residual_rms_3d_m": rms(residual),
            "residual_rms_rac_m": [float(np.sqrt(np.mean([(b @ p)[k]**2 for b, p in zip(bases, pieces)]))) for k in range(3)],
            "variance_explained": 1 - (rms(residual) / report["before"]["rms_3d_m"])**2}
        if model == "full_helmert":
            per_satellite = {}
            for sat in satellites:
                indices = [i for i, (s, _) in enumerate(labels) if s == sat]
                per_satellite[sat] = {"epochs": len(indices),
                                      "before_rms_3d_m": rms(np.concatenate([errors[i] for i in indices])),
                                      "after_rms_3d_m": rms(np.concatenate([pieces[i] for i in indices]))}
            report["models"][model]["per_satellite"] = per_satellite
            improved = sum(v["after_rms_3d_m"] < v["before_rms_3d_m"] for v in per_satellite.values())
            report["models"][model]["satellites_improved"] = improved
    report["interpretation"] = ("A large, well-determined rotation or scale with a big variance-explained share would "
                               "indicate a datum/EOP-like effect common to the constellation. Small or poorly determined "
                               "parameters, or improvement concentrated in a few satellites, would indicate per-satellite "
                               "orbit error instead. Parameters are estimated from one three-hour arc and are partly "
                               "degenerate with real orbit error; no alignment is applied to project scoring.")
    report["tool_sha256"] = sha(Path(__file__))
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "frame.json").write_text(json.dumps(report, indent=2) + "\n")
    printable = {k: v for k, v in report.items() if k not in ("source_policy", "interpretation")}
    printable["models"] = {m: {k: v for k, v in d.items() if k != "per_satellite"} for m, d in report["models"].items()}
    print(json.dumps(printable, indent=2), flush=True)


if __name__ == "__main__":
    main()
