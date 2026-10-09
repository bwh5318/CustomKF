"""Independent guarded archive/history and direct objective reconstruction audit."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from claude.tools.wet_step import BASE


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    folder = parser.parse_args().campaign
    manifest = json.loads((folder / "validation.json").read_text())
    assert manifest["status"] == "wet_experiment_complete_not_accuracy_acceptance"
    assert manifest["active_worker"] is None
    for name, digest in manifest["artifacts_sha256"].items():
        assert sha(folder / name) == digest, name
    for group in ("source_sha256", "report_sha256"):
        for name, digest in manifest[group].items():
            assert sha(ROOT / name) == digest, name
    assert sha(BASE / "validation.json") == manifest["baseline_manifest_sha256"]
    original = json.loads((BASE / "validation.json").read_text())
    for name, digest in original["artifacts_sha256"].items():
        assert sha(BASE / name) == digest, name
    fixture = json.loads((BASE / "prepare/fixture.json").read_text())
    for name, digest in fixture["context"]["inputs"].items():
        assert sha(ROOT / name) == digest, name
    baseline = np.load(BASE / "iteration-1/solution.npz")
    results = {}
    for name, case in manifest["cases"].items():
        history = []
        prior_fit = None
        for item in case["iterations"]:
            step = json.loads((folder / item / "step.json").read_text())
            assert manifest["runs"][item]["status"] == "ok"
            assert step["history"][:-1] == history
            history = step["history"]
            assert sha(folder / item / "solution.npz") == step["solution_sha256"]
            saved = np.load(folder / item / "solution.npz")
            if not history[-1]["update_applied"]:
                prior = prior_fit if prior_fit is not None else np.load(folder / item / "initial_parameters/solution.npz")
                for key in set(prior.files) & {"x", "states", "residual_m", "sigma_m"}:
                    np.testing.assert_array_equal(saved[key], prior[key])
            prior_fit = saved
        assert step["status"] == "converged"
        index = {str(n): i for i, n in enumerate(saved["names"])}
        x = saved["x"]
        prior_terms = []
        for sat in saved["satellites"]:
            for k in range(6):
                prior_terms.append((x[index[f"orbit:{sat}:{k}"]] / (1000. if k < 3 else 1.))**2)
        for station in sorted(fixture["context"]["stations"]):
            prior_terms.extend((x[index[f"wet:{station}:{k}"]] / .3)**2 for k in ("0", "1"))
            suffixes = ("0", "1") if name == "two-node" else ("0", "hour1", "hour2", "1")
            nodes = [x[index[f"wet:{station}:{k}"]] for k in suffixes]
            prior_terms.extend((np.diff(nodes) / (.03 / np.sqrt(len(nodes) - 1)))**2)
        obs_cost = float(np.sum((saved["residual_m"] / saved["sigma_m"])**2))
        prior_cost = float(sum(prior_terms))
        np.testing.assert_allclose(obs_cost + prior_cost, history[-1]["cost_after"], rtol=0, atol=1e-8)
        if name == "two-node":
            for key in ("x", "states", "residual_m", "sigma_m"):
                np.testing.assert_array_equal(saved[key], baseline[key])
        results[name] = {"observation_weighted_cost": obs_cost, "prior_cost": prior_cost,
                         "reconstructed_total_cost": obs_cost + prior_cost,
                         "total_cost_difference": obs_cost + prior_cost - history[-1]["cost_after"],
                         "history_entries": len(history), "final_stationary": not history[-1]["update_applied"]}
    report = {"status": "wet_archive_history_and_independent_objective_checks_pass", "cases": results,
              "campaign_manifest_sha256": sha(folder / "validation.json"), "review_source_sha256": sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
