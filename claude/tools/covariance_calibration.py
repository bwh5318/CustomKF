"""Guarded calibration check of the 14-station formal covariance across the arc.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.covariance_calibration

Astra's open gate: the formal covariance has never been compared with realized error. This
propagates each satellite's archived initial-state covariance to the 13 native IGS epochs with the
production trajectory partials, projects both the predicted sigma and the actual error into the
same radial/along/cross basis the evaluator uses, and reports normalized errors per direction.

Read-only over the GUAM archive, its fixture and the pinned IGS reference. No fit, no data editing,
no root source touched. Limits: the archived covariance is the pre-step linearization, includes the
broad orbit priors and the assumed weights, and excludes force, EOP and reference-product error;
the actual error includes IGS product error. A normalized spread is a diagnostic ratio, not a
probability statement. Writes only calibration.json.
"""
import json
import os
from pathlib import Path

import numpy as np

from customkf.stage5b_step import restore
from customkf.stage5_pilot import ORIGIN
from customkf.comparison import rac_basis
from customkf.dynamic_observation import Trajectory
from claude.tools.evaluate_ablation import Reference
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)
DIRECTIONS = ("radial", "along", "cross")


def summarize(values):
    values = np.asarray(values, float)
    return {"samples": int(len(values)), "mean": float(values.mean()), "rms": float(np.sqrt(np.mean(values**2))),
            "max_abs": float(np.max(abs(values)))}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    for name in (f"{base['final']}/solution.npz", "prepare/fixture.json"):
        assert sha(GUAM / name) == base["artifacts_sha256"][name], name
    fit = np.load(GUAM / base["final"] / "solution.npz")
    context, _, seeds = restore(GUAM / "prepare/fixture.json")
    reference = Reference()
    names = [str(n) for n in fit["names"]]
    satellites = [str(s) for s in fit["satellites"]]
    times = [float(v) for v in fit["times_s"]]
    per_satellite = {}
    pooled = {direction: [] for direction in DIRECTIONS}
    mahalanobis = []
    for si, sat in enumerate(satellites):
        k = names.index(f"orbit:{sat}:0")
        covariance = fit["retained_covariance"][k:k + 6, k:k + 6]
        trajectory = Trajectory(seeds[sat] + fit["x"][k:k + 6], context["model"], context["duration_s"])
        np.testing.assert_array_equal(np.array([trajectory.state(t) for t in times]), fit["states"][si])
        normalized = {direction: [] for direction in DIRECTIONS}
        sigmas = {direction: [] for direction in DIRECTIONS}
        distances = []
        for ti, t in enumerate(times):
            error = reference.rac(sat, t, fit["states"][si, ti, :3])
            if error is None:
                continue
            sample = reference.raw.samples[(ORIGIN + int(round(t * 1e9)), sat)]
            inertial = reference.epoch.celestial_to_terrestrial(t).T @ np.asarray(sample.xyz_m, float)
            basis = rac_basis(inertial, reference.precise.state(sat, t)[3:])
            # Same projection the evaluator applies to the error, so sigma and error share a basis.
            np.testing.assert_allclose(basis @ (fit["states"][si, ti, :3] - inertial), error, rtol=0, atol=1e-9)
            partial = trajectory.partial(t)[:3]
            rotated = basis @ (partial @ covariance @ partial.T) @ basis.T
            for index, direction in enumerate(DIRECTIONS):
                sigma = float(np.sqrt(rotated[index, index]))
                sigmas[direction].append(sigma)
                normalized[direction].append(float(error[index]) / sigma)
                pooled[direction].append(float(error[index]) / sigma)
            distances.append(float(error @ np.linalg.solve(rotated, error)))
        mahalanobis.extend(distances)
        per_satellite[sat] = {
            "epochs": len(distances),
            "error_rms_m": {direction: float(np.sqrt(np.mean(np.square(
                np.array(normalized[direction]) * np.array(sigmas[direction]))))) for direction in DIRECTIONS},
            "formal_sigma_median_m": {direction: float(np.median(sigmas[direction])) for direction in DIRECTIONS},
            "normalized_rms": {direction: float(np.sqrt(np.mean(np.square(normalized[direction])))) for direction in DIRECTIONS},
            "mahalanobis_mean_3dof": float(np.mean(distances)),
            "initial_position_root_trace_sigma_m": float(np.sqrt(np.trace(covariance[:3, :3])))}
    report = {
        "status": "formal_covariance_calibration_diagnostic_not_a_probability_statement",
        "source_policy": policy, "baseline": GUAM.relative_to(ROOT).as_posix(),
        "baseline_manifest_sha256": sha(GUAM / "validation.json"), "reference_sha256": reference.sha256,
        "samples": {"satellites": len(per_satellite), "per_direction": len(pooled["radial"])},
        "pooled_normalized": {direction: summarize(pooled[direction]) for direction in DIRECTIONS},
        "pooled_variance_scale_factor": {direction: float(np.mean(np.square(pooled[direction]))) for direction in DIRECTIONS},
        "pooled_mahalanobis_mean_3dof": float(np.mean(mahalanobis)),
        "fraction_within": {f"{limit}_sigma": float(np.mean([abs(v) <= limit for direction in DIRECTIONS for v in pooled[direction]]))
                            for limit in (1, 2, 3)},
        "per_satellite": per_satellite,
        "interpretation": "Normalized error is the actual IGS-referenced RAC error divided by the propagated formal sigma. "
                          "A pooled RMS below one means the formal covariance is conservative in that direction. It includes "
                          "IGS product error and the broad orbit priors, and excludes force, EOP and reference model error.",
        "tool_sha256": sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "calibration.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("per_satellite", "source_policy", "interpretation")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
