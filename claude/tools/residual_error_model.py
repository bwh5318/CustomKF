"""Guarded empirical error-model check on the archived 14-station residuals.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.residual_error_model

The weighted objective sits far below its degrees of freedom, so the assumed sigmas are loose, and
every cost-based diagnostic (formal sigma, the observation-profile penalties) is expressed in those
units. This measures three things the project has not characterized:

1. The a-posteriori variance factor, overall and per observation kind.
2. Elevation-binned residual means, which reveal systematic mismodelling that RMS hides
   (troposphere mapping or antenna phase-centre signatures), per kind and per station.
3. Within-pass residual correlation, which shows how far the white-noise weighting overstates the
   independent information.

Read-only over the GUAM archive and its fixture; no fit, no data editing, no root source touched.
Correlated residuals make a single variance factor an incomplete error model: these are descriptive
measurements, not a calibrated stochastic model or a licence to retune weights. Writes only
error_model.json.
"""
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from claude.tools.pinned_sources import GUAM, ROOT, sha, verify
from claude.tools.yell_continuation_review import labelled
from claude.tools.observation_profile_review import prior_cost

HELPERS = ("claude/tools/evaluate_ablation.py",)
BINS = (0., 10., 15., 20., 30., 50., 90.1)


def stats(values):
    values = np.asarray(values, float)
    return {"rows": int(len(values)), "mean": float(values.mean()), "rms": float(np.sqrt(np.mean(values**2)))}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    for name in (f"{base['final']}/solution.npz", "prepare/fixture.json"):
        assert sha(GUAM / name) == base["artifacts_sha256"][name], name
    fit = np.load(GUAM / base["final"] / "solution.npz")
    fixture = json.loads((GUAM / "prepare/fixture.json").read_text())
    labels = labelled(fixture)
    residual, sigma = fit["residual_m"], fit["sigma_m"]
    assert len(labels) == len(residual)
    # Row sigmas are elevation dependent, so this also verifies the label order row by row.
    np.testing.assert_allclose(sigma, [row["sigma"][kind] for row, kind in labels], rtol=1e-12, atol=0)
    z = residual / sigma
    elevation = np.degrees(np.arcsin(.9 / np.array([row["sigma"][0] for row, _ in labels])))
    kind = np.array([k for _, k in labels])
    station = np.array([row["station"] for row, _ in labels])
    index = {str(n): i for i, n in enumerate(fit["names"])}
    priors = prior_cost(fit["x"], index, [str(s) for s in fit["satellites"]], fixture["context"]["stations"])
    observation_cost = float(z @ z)
    retained = len(fit["retained_covariance"])
    locals_total = len(fit["names"]) - retained
    prior_rows = 6 * len(fit["satellites"]) + 3 * len(fixture["context"]["stations"])
    dof = len(residual) + prior_rows - retained - locals_total
    report = {
        "status": "empirical_error_model_measurement_not_a_calibrated_model", "source_policy": policy,
        "baseline": GUAM.relative_to(ROOT).as_posix(), "baseline_manifest_sha256": sha(GUAM / "validation.json"),
        "counts": {"observation_rows": int(len(residual)), "prior_rows": prior_rows, "retained_parameters": retained,
                   "local_clock_parameters": locals_total, "degrees_of_freedom": dof},
        "cost": {"observations": observation_cost, "priors": priors, "total": observation_cost + sum(priors.values())},
        "variance_factor": {"overall": (observation_cost + sum(priors.values())) / dof,
                            "observations_only_per_row": observation_cost / len(residual),
                            "code_per_row": float(np.mean(z[kind == 0]**2)), "phase_per_row": float(np.mean(z[kind == 1]**2))},
        "by_kind": {label: stats(z[kind == value]) for value, label in ((0, "code"), (1, "phase"))},
        "by_elevation": {}, "by_station": {}, "worst_station_elevation_means": {}, "within_pass_correlation": {},
    }
    for value, label in ((0, "code"), (1, "phase")):
        bins = {}
        for low, high in zip(BINS, BINS[1:]):
            mask = (kind == value) & (elevation >= low) & (elevation < high)
            if mask.any():
                bins[f"{low:.0f}-{high:.0f}_deg"] = stats(z[mask]) | {
                    "residual_mean_mm": float(1e3 * residual[mask].mean()), "residual_rms_mm": float(1e3 * np.sqrt(np.mean(residual[mask]**2)))}
        report["by_elevation"][label] = bins
    for name in sorted(set(station)):
        report["by_station"][name] = {label: stats(z[(station == name) & (kind == value)])
                                      for value, label in ((0, "code"), (1, "phase"))}
    ranked = sorted(report["by_station"], key=lambda name: -abs(report["by_station"][name]["phase"]["mean"]))
    for name in ranked[:4]:
        bins = {}
        for low, high in zip(BINS, BINS[1:]):
            mask = (station == name) & (kind == 1) & (elevation >= low) & (elevation < high)
            if mask.any():
                bins[f"{low:.0f}-{high:.0f}_deg"] = {"rows": int(mask.sum()), "phase_mean_mm": float(1e3 * residual[mask].mean())}
        report["worst_station_elevation_means"][name] = bins
    # Lag-1 and lag-2 correlation of normalized phase residuals inside each retained arc.
    arcs = defaultdict(list)
    for position, (row, row_kind) in enumerate(labels):
        if row_kind == 1:
            arcs[row["arc"]].append((row["epoch"], z[position]))
    products = {1: [], 2: []}
    squares, used = [], 0
    for series in arcs.values():
        if len(series) < 5:
            continue
        used += 1
        values = np.array([value for _, value in sorted(series)])
        squares.extend(values**2)
        for lag in (1, 2):
            products[lag].extend((values[:-lag] * values[lag:]).tolist())
    variance = float(np.mean(squares))
    correlation = {f"lag_{lag}": float(np.mean(products[lag]) / variance) for lag in (1, 2)}
    rho = correlation["lag_1"]
    report["within_pass_correlation"] = {
        "arcs_used": used, "minimum_rows_per_arc": 5, "phase_rows_considered": int(len(squares)), **correlation,
        "effective_sample_factor_ar1": (1 - rho) / (1 + rho) if rho > -1 else None,
        "note": "Pooled correlation of normalized phase residuals within an arc, in epoch order. The per-arc ambiguity "
                "removes each pass mean by construction. An AR(1) reading of lag_1 implies the independent-information "
                "factor shown; it is an indication, not a fitted stochastic model."}
    report["tool_sha256"] = sha(Path(__file__))
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "error_model.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_policy", "by_station")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
