"""Guarded post-campaign audit: hashes, histories, residual labels and ECEF RMS.

Run after run_stability has finished, under customkf.guard --timeout 120.
Writes review.json only to the guard directory; never modifies fitted results.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import ORIGIN
from claude.tools.stability_step import BASE
from claude.tools.evaluate_ablation import Reference
from claude.tools.yell_continuation_review import residual_structure


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    folder = parser.parse_args().campaign
    manifest = json.loads((folder / "validation.json").read_text())
    assert manifest["status"] in ("stability_checks_pass_not_absolute_accuracy_acceptance", "stability_gate_failed")
    assert manifest["active_worker"] is None
    for name, digest in manifest["artifacts_sha256"].items():
        assert sha(folder / name) == digest, name
    for group in ("source_sha256", "report_sha256"):
        for name, digest in manifest[group].items():
            assert sha(ROOT / name) == digest, name
    assert sha(BASE / "validation.json") == manifest["baseline_manifest_sha256"]
    base_manifest = json.loads((BASE / "validation.json").read_text())
    for name, digest in base_manifest["artifacts_sha256"].items():
        assert sha(BASE / name) == digest, name
    fixture = json.loads((BASE / "prepare/fixture.json").read_text())
    for name, digest in fixture["context"]["inputs"].items():
        assert sha(ROOT / name) == digest, name
    baseline = np.load(BASE / base_manifest["final"] / "solution.npz")
    evaluated = json.loads((folder / "evaluation/evaluation.json").read_text())
    reference = Reference()
    assert reference.sha256 == evaluated["reference_sha256"]
    results = {}
    for name, case in manifest["cases"].items():
        previous_history = []
        for item in case["iterations"]:
            step = json.loads((folder / item / "step.json").read_text())
            assert manifest["runs"][item]["status"] == "ok"
            assert sha(folder / item / "solution.npz") == step["solution_sha256"]
            assert step["history"][:-1] == previous_history
            previous_history = step["history"]
        assert step["status"] == "converged"
        fit = np.load(folder / case["final"] / "solution.npz")
        for key in ("names", "satellites", "times_s"):
            np.testing.assert_array_equal(fit[key], baseline[key])
        stationary_identity = None
        if not step["history"][-1]["update_applied"]:
            prior = (folder / case["iterations"][-2] / "solution.npz") if len(case["iterations"]) > 1 else (folder / case["final"] / "initial_parameters/solution.npz")
            before = np.load(prior)
            for key in set(before.files) & set(("x", "states", "residual_m", "sigma_m")):
                np.testing.assert_array_equal(fit[key], before[key])
            stationary_identity = True
        stations, _, _, _ = residual_structure(fixture, fit)
        per_satellite = {}
        all_squares = []
        for si, sat in enumerate(fit["satellites"]):
            squares = []
            for ti, t in enumerate(fit["times_s"]):
                sample = reference.raw.samples.get((ORIGIN + int(round(float(t) * 1e9)), str(sat)))
                if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:
                    continue
                delta = reference.epoch.celestial_to_terrestrial(float(t)) @ fit["states"][si, ti, :3] - sample.xyz_m
                squares.append(float(delta @ delta))
            rms = float(np.sqrt(np.mean(squares)))
            rac_rms = evaluated["scores"][name]["score"]["per_satellite"][str(sat)]["fit"]["rms_3d_m"]
            np.testing.assert_allclose(rms, rac_rms, rtol=0, atol=2e-8)
            per_satellite[str(sat)] = {"samples": len(squares), "ecef_rms_m": rms}
            all_squares.extend(squares)
        assert len(all_squares) == 403
        rms = float(np.sqrt(np.mean(all_squares)))
        np.testing.assert_allclose(rms, evaluated["scores"][name]["score"]["groups"]["all"]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
        distance = np.linalg.norm(fit["states"][:, :, :3] - baseline["states"][:, :, :3], axis=2)
        results[name] = {"ecef_rms_m": rms, "samples": len(all_squares), "per_satellite": per_satellite,
                         "history": step["history"], "stationary_identity": stationary_identity,
                         "station_residuals": stations,
                         "trajectory_delta_vs_baseline_m": {str(s): distance[i].tolist() for i, s in enumerate(fit["satellites"])},
                         "times_s": fit["times_s"].tolist()}
    report = {"status": "hash_history_residual_and_cartesian_checks_pass_not_accuracy_acceptance",
              "campaign_manifest_sha256": sha(folder / "validation.json"), "cases": results,
              "review_sources_sha256": {p: sha(ROOT / p) for p in ("claude/tools/stability_review.py", "claude/tools/yell_continuation_review.py")}}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: {"ecef_rms_m": v["ecef_rms_m"], "samples": v["samples"]} for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
