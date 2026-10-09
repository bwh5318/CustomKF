"""Guarded IGS scoring of the fixture variants against the archived 14-station baseline.

    customkf.guard --timeout 120 -- claude.tools.evaluate_variant CAMPAIGN

Evaluator side only: the estimator never calls this. Uses the frozen sigma <= 10 m split
(claude/SCORING_RULE.md) and the same native IGS samples as every earlier comparison, scoring all
31 satellites, the determined groups and the determined-in-both intersection. For holdout-2h it
splits the native epochs into the fitted first two hours and the withheld third hour, which is the
point of that variant. Writes only evaluation.json.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.stage5_pilot import ORIGIN
from claude.tools.evaluate_ablation import Reference, score, pooled, strip
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)
WITHHELD_FROM_EPOCH = 24


def epoch_errors(reference, solution, satellites, times):
    """3D error per satellite and solve epoch, at the epochs with native reference samples."""
    out = {}
    for si, sat in enumerate(satellites):
        values = {}
        for ti, t in enumerate(times):
            error = reference.rac(sat, t, solution["states"][si, ti, :3])
            if error is not None:
                values[ti] = float(np.linalg.norm(error))
        out[sat] = values
    return out


def split_rms(errors, keep):
    squares = [value**2 for values in errors.values() for epoch, value in values.items() if keep(epoch)]
    return {"samples": len(squares), "rms_3d_m": float(np.sqrt(np.mean(squares))) if squares else None}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    campaign = parser.parse_args().campaign.resolve()
    manifest = json.loads((campaign / "validation.json").read_text())
    assert verify(HELPERS) == manifest["source_policy"]
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    base = json.loads((GUAM / "validation.json").read_text())
    baseline_dir = GUAM / base["final"]
    initial = GUAM / "prepare/initial.npz"
    for name in (f"{base['final']}/solution.npz", "prepare/fixture.json", "prepare/initial.npz"):
        assert sha(GUAM / name) == base["artifacts_sha256"][name], name
    reference = Reference()
    baseline = score(reference, baseline_dir, GUAM / "prepare/fixture.json", initial)
    baseline_solution = np.load(baseline_dir / "solution.npz")
    satellites = [str(s) for s in baseline_solution["satellites"]]
    times = [float(t) for t in baseline_solution["times_s"]]
    baseline_errors = epoch_errors(reference, baseline_solution, satellites, times)
    report = {"status": "variant_evaluation_not_accuracy_acceptance", "reference_sha256": reference.sha256,
              "baseline": {"groups": baseline["groups"], "phase_rms_mm": baseline["phase_rms_mm"]},
              "baseline_epoch_split": {"fitted_first_two_hours": split_rms(baseline_errors, lambda e: e < WITHHELD_FROM_EPOCH),
                                       "withheld_third_hour": split_rms(baseline_errors, lambda e: e >= WITHHELD_FROM_EPOCH)},
              "variants": {}}
    for variant, case in manifest["cases"].items():
        assert case["final"], variant
        final = campaign / case["final"]
        step = json.loads((final / "step.json").read_text())
        assert step["status"] == "converged" and sha(final / "solution.npz") == step["solution_sha256"]
        fixture_path = campaign / case["prepare"] / "fixture.json"
        prepared = json.loads((campaign / case["prepare"] / "step.json").read_text())
        assert sha(fixture_path) == prepared["fixture_sha256"]
        result = score(reference, final, fixture_path, initial)
        solution = np.load(final / "solution.npz")
        np.testing.assert_array_equal(solution["satellites"], baseline_solution["satellites"])
        np.testing.assert_array_equal(solution["times_s"], baseline_solution["times_s"])
        errors = epoch_errors(reference, solution, satellites, times)
        both = [s for s in result["per_satellite"]
                if result["per_satellite"][s]["class"] == baseline["per_satellite"][s]["class"] == "determined"]
        changes = {s: {"baseline_rms_3d_m": baseline["per_satellite"][s]["fit"]["rms_3d_m"],
                       "variant_rms_3d_m": result["per_satellite"][s]["fit"]["rms_3d_m"],
                       "delta_m": result["per_satellite"][s]["fit"]["rms_3d_m"] - baseline["per_satellite"][s]["fit"]["rms_3d_m"],
                       "baseline_class": baseline["per_satellite"][s]["class"], "variant_class": result["per_satellite"][s]["class"]}
                   for s in sorted(result["per_satellite"])}
        deltas = {s: changes[s]["delta_m"] for s in both}
        report["variants"][variant] = {
            "variant_detail": prepared["variant_detail"], "history": step["history"],
            "groups": result["groups"], "phase_rms_mm": result["phase_rms_mm"],
            "determined_in_both": {"count": len(both), "baseline": pooled(baseline, both), "variant": pooled(result, both)},
            "epoch_split": {"fitted_first_two_hours": split_rms(errors, lambda e: e < WITHHELD_FROM_EPOCH),
                            "withheld_third_hour": split_rms(errors, lambda e: e >= WITHHELD_FROM_EPOCH)},
            "per_satellite_changes": changes,
            "class_changes": {s: [c["baseline_class"], c["variant_class"]] for s, c in changes.items()
                              if c["baseline_class"] != c["variant_class"]},
            "determined_in_both_delta_m": {"max_abs": max(map(abs, deltas.values())) if deltas else None,
                                           "median": float(np.median(list(deltas.values()))) if deltas else None,
                                           "largest_five": dict(sorted(deltas.items(), key=lambda item: -abs(item[1]))[:5])},
            "per_satellite_withheld_hour_m": {s: split_rms({s: errors[s]}, lambda e: e >= WITHHELD_FROM_EPOCH)["rms_3d_m"]
                                              for s in satellites},
            "score": strip(result)}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    printable = {"baseline_all": report["baseline"]["groups"]["all"]["fit"]["rms_3d_m"],
                 "baseline_epoch_split": report["baseline_epoch_split"],
                 "variants": {v: {"all": d["groups"]["all"]["fit"]["rms_3d_m"],
                                  "determined": d["groups"].get("determined", {}).get("fit", {}).get("rms_3d_m"),
                                  "determined_in_both": [d["determined_in_both"]["baseline"]["fit"]["rms_3d_m"],
                                                         d["determined_in_both"]["variant"]["fit"]["rms_3d_m"],
                                                         d["determined_in_both"]["count"]],
                                  "epoch_split": d["epoch_split"], "class_changes": d["class_changes"],
                                  "determined_in_both_delta_m": d["determined_in_both_delta_m"],
                                  "iterations": len(d["history"])} for v, d in report["variants"].items()}}
    print(json.dumps(printable, indent=2), flush=True)


if __name__ == "__main__":
    main()
