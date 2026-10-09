"""Read-only independent archive review; write findings only in the guarded run.

From the project root, with existing Python and unchanged resource limits:
    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.astra_verify_stage5b

Recompute Cartesian (not RAC) RMS from archived states and native IGS samples,
check Claude's split and exact exclusions, and verify the stationary stop kept
the accepted state. This is diagnostic verification, not POD accuracy acceptance.
"""
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import ORIGIN
from claude.tools.evaluate_ablation import ARCHIVE, Reference

BASE = ARCHIVE.parent
CLAUDE = ROOT / "claude/runs/20260910T222851Z-kour-ablation"


def read(path):
    return json.loads(path.read_text())


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    manifests = [read(BASE / "validation.json"), read(ARCHIVE / "validation.json")]
    checked = 0
    for directory, manifest in zip((BASE, ARCHIVE), manifests):
        for name, digest in manifest["artifacts_sha256"].items():
            assert sha(directory / name) == digest, name
            checked += 1
        for name, digest in manifest["report_sha256"].items():
            assert sha(ROOT / name) == digest, name
    for name, digest in manifests[1]["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    assert manifests[0]["status"] == "failed"
    assert manifests[1]["original_campaign_sha256"] == sha(BASE / "validation.json")

    previous = np.load(BASE / "expanded-long-iteration-1/solution.npz")
    final = np.load(ARCHIVE / "expanded-long-final/solution.npz")
    for key in ("x", "names", "states", "times_s", "satellites", "residual_m", "sigma_m"):
        np.testing.assert_array_equal(previous[key], final[key], err_msg=key)
    stop = read(ARCHIVE / "expanded-long-final/step.json")["history"][-1]
    assert not stop["update_applied"] and stop["step_fraction"] == 0

    campaign = read(CLAUDE / "campaign.json")
    assert all(w["status"] == "ok" for w in campaign["workers"].values())
    assert all(c["status"] == "converged" for c in campaign["cases"].values())
    for name, digest in campaign["astra_sources_at_start"].items():
        assert sha(ROOT / name) == digest, name
    evaluated = read(CLAUDE / "evaluation/evaluation.json")
    assert evaluated == read(ROOT / "claude/diagnostics/kour_ablation_evaluation.json")
    exclusions = {}
    cases = {}
    for name, value in evaluated["baselines"].items():
        cases[name] = (ARCHIVE / manifests[1]["final_steps"][name],
                       ARCHIVE / f"{name}-prepare/fixture.json",
                       ARCHIVE / f"{name}-prepare/initial.npz", value)
    for name, spec in campaign["cases"].items():
        before = read(ARCHIVE / f"{spec['base']}-prepare/fixture.json")
        path = CLAUDE / spec["prepare"] / "fixture.json"
        after = read(path)
        # Independent predicate, not the ablation worker's filtering function.
        rules = after["ablation"]["rules"]
        expected = [r for r in before["rows"] if not any(
            r["station"] == rule["station"] and
            (rule["epochs"] is None or rule["epochs"][0] <= r["epoch"] <= rule["epochs"][1])
            for rule in rules)]
        assert after["rows"] == expected
        assert after["seeds"] == before["seeds"]
        for key in before["context"]:
            if key != "stations":
                assert after["context"][key] == before["context"][key], key
        retained_stations = {r["station"] for r in expected}
        assert after["context"]["stations"] == {k: v for k, v in before["context"]["stations"].items() if k in retained_stations}
        assert sha(ARCHIVE / f"{spec['base']}-prepare/fixture.json") == after["ablation"]["source_fixture_sha256"]
        exclusions[name] = len(before["rows"]) - len(expected)
        cases[name] = (CLAUDE / spec["final"], path,
                       ARCHIVE / f"{spec['base']}-prepare/initial.npz", evaluated["ablations"][name])

    reference = Reference()
    metrics = {}
    for name, (directory, fixture_path, initial_path, expected) in cases.items():
        assert sha(directory / "solution.npz") == expected["solution_sha256"]
        assert sha(fixture_path) == expected["fixture_sha256"]
        assert read(directory / "step.json")["status"] == "converged"
        fit, initial = np.load(directory / "solution.npz"), np.load(initial_path)
        np.testing.assert_array_equal(fit["satellites"], initial["satellites"])
        np.testing.assert_array_equal(fit["times_s"], initial["times_s"])
        names = list(fit["names"])
        groups = {g: {"fit": [], "initial": []} for g in ("all", "determined", "poorly_determined")}
        per_sat = {}
        for si, sat in enumerate(fit["satellites"]):
            idx = [names.index(f"orbit:{sat}:{k}") for k in range(3)]
            sigma = float(np.sqrt(sum(fit["retained_covariance"][k, k] for k in idx)))
            np.testing.assert_allclose(sigma, expected["per_satellite"][sat]["formal_position_sigma_m"], rtol=1e-12)
            group = "determined" if sigma <= 10. else "poorly_determined"
            assert (expected["per_satellite"][sat]["class"] == "determined") == (group == "determined")
            per_sat[str(sat)] = []
            for ti, t in enumerate(fit["times_s"]):
                sample = reference.raw.samples.get((ORIGIN + int(round(t * 1e9)), str(sat)))
                if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:
                    continue
                rotation = reference.epoch.celestial_to_terrestrial(float(t))
                for kind, array in (("fit", fit), ("initial", initial)):
                    diff = rotation @ array["states"][si, ti, :3] - sample.xyz_m
                    squared = float(diff @ diff)
                    groups["all"][kind].append(squared)
                    groups[group][kind].append(squared)
                    if kind == "fit":
                        per_sat[str(sat)].append(squared)
        result = {}
        for g, kinds in groups.items():
            result[g] = {}
            for kind, squares in kinds.items():
                if not squares:
                    continue
                rms = float(np.sqrt(np.mean(squares)))
                target = expected["groups"][g][kind]
                assert len(squares) == target["samples"]
                np.testing.assert_allclose(rms, target["rms_3d_m"], rtol=0, atol=2e-8)
                result[g][kind + "_3d_rms_m"] = rms
        if name == "expanded-long":
            result["g18_squared_error_percent"] = 100 * sum(per_sat["G18"]) / sum(groups["all"]["fit"])
            result["excluding_g18_diagnostic_rms_m"] = float(np.sqrt(np.mean([v for s, a in per_sat.items() if s != "G18" for v in a])))
        metrics[name] = result
    report = {"status": "verified_diagnostics_not_accuracy_acceptance", "checked_archive_artifacts": checked,
              "stationary_state_and_residuals_bitwise_unchanged": True, "report_unchanged": True,
              "current_estimator_and_tests_match_completion_and_claude_campaign": True,
              "exact_removed_links": exclusions, "cartesian_recomputed_metrics": metrics,
              "tool_sha256": sha(Path(__file__)),
              "claude_tool_current_sha256": {p.name: sha(p) for p in (ROOT / "claude/tools").glob("*.py")},
              "historical_claude_tool_hashes_available": False,
              "evidence_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
                  (BASE / "validation.json", ARCHIVE / "validation.json", CLAUDE / "campaign.json", CLAUDE / "evaluation/evaluation.json", ROOT / "claude/SCORING_RULE.md")}}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
