"""Guarded G26 diagnostic for the YELL continuation. Evaluator-side only; no fit or data editing.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.diag_g26_yell CAMPAIGN

Question: G26 stayed at its broadcast seed in the 12-station baseline (no simultaneous sites) but
moved ~60 m from IGS after YELL added seven two-site epochs. Is that move along the formally
weakest initial-state direction (weak geometry), or do G26 residuals / new outliers point at data?
Writes only g26.json in the guarded run directory.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.comparison import rac_basis
from claude.tools.evaluate_ablation import Reference
from claude.tools.yell_continuation_review import BASE, labelled

SAT = "G26"


def rows_with_residuals(fixture, fit):
    labels = labelled(fixture)
    residual, sigma = fit["residual_m"], fit["sigma_m"]
    np.testing.assert_allclose(sigma, [r["sigma"][k] for r, k in labels], rtol=1e-12, atol=0)
    return [{"station": r["station"], "satellite": r["satellite"], "epoch": r["epoch"], "kind": "phase" if k else "code",
             "elevation_deg": float(np.degrees(np.arcsin(.9 / r["sigma"][0]))),
             "residual_mm": 1e3 * float(residual[i]), "normalized": float(residual[i] / sigma[i])}
            for i, (r, k) in enumerate(labels)]


def by_station(rows):
    out = {}
    for kind in ("code", "phase"):
        for s in sorted({r["station"] for r in rows}):
            z = np.array([r["normalized"] for r in rows if r["station"] == s and r["kind"] == kind])
            v = np.array([r["residual_mm"] for r in rows if r["station"] == s and r["kind"] == kind])
            if len(z):
                out.setdefault(s, {})[kind] = {"count": int(len(z)), "rms_mm": float(np.sqrt(np.mean(v * v))),
                                               "max_abs_normalized": float(np.max(abs(z)))}
    return out


def state_analysis(fit, seed, reference):
    names = [str(n) for n in fit["names"]]
    k = names.index(f"orbit:{SAT}:0")
    x = fit["x"][k:k + 6]
    c = fit["retained_covariance"][k:k + 6, k:k + 6]
    basis = rac_basis(seed[:3], seed[3:])
    values, vectors = np.linalg.eigh(c[:3, :3])
    order = np.argsort(values)[::-1]
    top = vectors[:, order[0]]
    whitened = np.linalg.solve(np.linalg.cholesky(c), x)
    si = [str(s) for s in fit["satellites"]].index(SAT)
    errors = []
    for ti, t in enumerate(float(v) for v in fit["times_s"]):
        a = reference.rac(SAT, t, fit["states"][si, ti, :3])
        if a is not None:
            errors.append({"epoch": ti, "rac_m": [float(v) for v in a]})
    return {"correction_from_seed_position_rac_m": (basis @ x[:3]).tolist(),
            "correction_from_seed_velocity_rac_mps": (basis @ x[3:]).tolist(),
            "position_sigma_rac_m": np.sqrt(np.diag(basis @ c[:3, :3] @ basis.T)).tolist(),
            "position_covariance_eigen_sigma_m": np.sqrt(values[order]).tolist(),
            "weakest_position_direction_rac": (basis @ top).tolist(),
            "fraction_of_position_correction_along_weakest": float((top @ x[:3]) ** 2 / (x[:3] @ x[:3])) if x[:3] @ x[:3] > 0 else None,
            "correction_in_formal_sigmas_6d": float(np.linalg.norm(whitened)),
            "igs_error_rac_by_reference_epoch": errors}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    campaign = parser.parse_args().campaign.resolve()
    manifest = json.loads((campaign / "validation.json").read_text())
    assert manifest["status"] == "YELL_continuation_complete_not_accuracy_acceptance", manifest["status"]
    base_manifest = json.loads((BASE / "validation.json").read_text())
    pins = {campaign / name: digest for name, digest in manifest["artifacts_sha256"].items()
            if name in ("prepare/fixture.json", manifest["final"] + "/solution.npz")}
    pins.update({BASE / name: base_manifest["artifacts_sha256"][name]
                 for name in ("expanded-long-prepare/fixture.json", "expanded-long-final/solution.npz")})
    assert len(pins) == 4
    for path, digest in pins.items():
        assert sha(path) == digest, path
    reference = Reference()
    runs = {"baseline": (BASE / "expanded-long-prepare/fixture.json", BASE / "expanded-long-final/solution.npz"),
            "YELL": (campaign / "prepare/fixture.json", campaign / manifest["final"] / "solution.npz")}
    report = {"status": "G26_diagnostic_not_accuracy_acceptance", "satellite": SAT, "tool_sha256": sha(Path(__file__)),
              "input_sha256": {p.relative_to(ROOT).as_posix(): d for p, d in pins.items()}, "runs": {}}
    for label, (fixture_path, solution_path) in runs.items():
        fixture = json.loads(fixture_path.read_text())
        fit = np.load(solution_path)
        rows = rows_with_residuals(fixture, fit)
        sat_rows = [r for r in rows if r["satellite"] == SAT]
        stations = {}
        for r in fixture["rows"]:
            if r["satellite"] == SAT:
                stations.setdefault(r["epoch"], []).append(r["station"])
        report["runs"][label] = {
            "stations_by_epoch": {e: sorted(v) for e, v in sorted(stations.items())},
            "state": state_analysis(fit, np.asarray(fixture["seeds"][SAT], float), reference),
            "residuals_by_station": by_station(sat_rows),
            "rows_above_2_sigma": [r for r in sat_rows if abs(r["normalized"]) > 2],
            "all_satellite_rows_above_4_sigma": [r for r in rows if abs(r["normalized"]) > 4]}
    b, y = report["runs"]["baseline"]["state"], report["runs"]["YELL"]["state"]
    report["position_change_YELL_minus_baseline_rac_m"] = (np.array(y["correction_from_seed_position_rac_m"]) - b["correction_from_seed_position_rac_m"]).tolist()
    report["velocity_change_YELL_minus_baseline_rac_mps"] = (np.array(y["correction_from_seed_velocity_rac_mps"]) - b["correction_from_seed_velocity_rac_mps"]).tolist()
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "g26.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"position_change_rac_m": report["position_change_YELL_minus_baseline_rac_m"],
                      "velocity_change_rac_mps": report["velocity_change_YELL_minus_baseline_rac_mps"],
                      "state": {k: {n: v for n, v in r["state"].items() if n != "igs_error_rac_by_reference_epoch"} for k, r in report["runs"].items()},
                      "igs_error_rac": {k: r["state"]["igs_error_rac_by_reference_epoch"] for k, r in report["runs"].items()},
                      "residuals_by_station": {k: r["residuals_by_station"] for k, r in report["runs"].items()},
                      "G26_rows_above_2_sigma": {k: r["rows_above_2_sigma"] for k, r in report["runs"].items()},
                      "all_rows_above_4_sigma": {k: r["all_satellite_rows_above_4_sigma"] for k, r in report["runs"].items()},
                      "YELL_stations_by_epoch": report["runs"]["YELL"]["stations_by_epoch"]}, indent=1))


if __name__ == "__main__":
    main()
