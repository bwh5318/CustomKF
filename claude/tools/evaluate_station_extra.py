"""Guarded IGS scoring and coverage comparison for the 15-station diagnostic fixture.

    customkf.guard --timeout 120 -- claude.tools.evaluate_station_extra CAMPAIGN

Evaluator side only. Frozen sigma <= 10 m split (claude/SCORING_RULE.md), the same native IGS
samples as every earlier comparison, all 31 satellites kept visible, plus the determined and
determined-in-both sets. Also reports what the extra station actually adds geometrically: retained
links, elevation spread and the change in simultaneous-site epochs per satellite under the 50 km
site merge. Writes only evaluation.json. Not an accuracy acceptance and not a new baseline.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from claude.tools.evaluate_ablation import Reference, coverage, score, pooled, strip
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)


def site_map(fixture):
    _, merged = coverage(fixture)
    site = {row["station"]: row["station"] for row in fixture["rows"]}
    for root, members in merged.items():
        for member in members:
            site[member] = root
    return site


def multi_site_epochs(fixture):
    site = site_map(fixture)
    count = fixture["context"]["epoch_count"]
    per = {}
    for row in fixture["rows"]:
        per.setdefault(row["satellite"], {}).setdefault(row["epoch"], set()).add(site[row["station"]])
    return {sat: [epoch for epoch in range(count) if len(epochs.get(epoch, ())) >= 2] for sat, epochs in per.items()}


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
    for name in (f"{base['final']}/solution.npz", "prepare/fixture.json", "prepare/initial.npz"):
        assert sha(GUAM / name) == base["artifacts_sha256"][name], name
    initial = GUAM / "prepare/initial.npz"
    reference = Reference()
    baseline = score(reference, GUAM / base["final"], GUAM / "prepare/fixture.json", initial)
    old_fixture = json.loads((GUAM / "prepare/fixture.json").read_text())
    final = campaign / manifest["final"]
    step = json.loads((final / "step.json").read_text())
    assert step["status"] == "converged" and sha(final / "solution.npz") == step["solution_sha256"]
    prepared = json.loads((campaign / manifest["prepare"] / "step.json").read_text())
    fixture_path = campaign / manifest["prepare"] / "fixture.json"
    assert sha(fixture_path) == prepared["fixture_sha256"]
    new_fixture = json.loads(fixture_path.read_text())
    result = score(reference, final, fixture_path, initial)
    solution, reference_solution = np.load(final / "solution.npz"), np.load(GUAM / base["final"] / "solution.npz")
    np.testing.assert_array_equal(solution["satellites"], reference_solution["satellites"])
    np.testing.assert_array_equal(solution["times_s"], reference_solution["times_s"])
    both = [s for s in result["per_satellite"]
            if result["per_satellite"][s]["class"] == baseline["per_satellite"][s]["class"] == "determined"]
    changes = {s: {"baseline_rms_3d_m": baseline["per_satellite"][s]["fit"]["rms_3d_m"],
                   "extended_rms_3d_m": result["per_satellite"][s]["fit"]["rms_3d_m"],
                   "delta_m": result["per_satellite"][s]["fit"]["rms_3d_m"] - baseline["per_satellite"][s]["fit"]["rms_3d_m"],
                   "baseline_sigma_m": baseline["per_satellite"][s]["formal_position_sigma_m"],
                   "extended_sigma_m": result["per_satellite"][s]["formal_position_sigma_m"],
                   "baseline_class": baseline["per_satellite"][s]["class"],
                   "extended_class": result["per_satellite"][s]["class"]}
               for s in sorted(result["per_satellite"])}
    deltas = {s: changes[s]["delta_m"] for s in both}
    old_multi, new_multi = multi_site_epochs(old_fixture), multi_site_epochs(new_fixture)
    station = prepared["station"]
    report = {
        "status": "station_extension_evaluation_not_accuracy_acceptance", "station": station,
        "reference_sha256": reference.sha256, "baseline_manifest_sha256": sha(GUAM / "validation.json"),
        "history": step["history"], "extra_station_detail": prepared["extra_station"],
        "groups": {"baseline": baseline["groups"], "extended": result["groups"]},
        "determined_in_both": {"count": len(both), "baseline": pooled(baseline, both), "extended": pooled(result, both)},
        "determined_in_both_delta_m": {"max_abs": max(map(abs, deltas.values())) if deltas else None,
                                       "median": float(np.median(list(deltas.values()))) if deltas else None,
                                       "largest_five": dict(sorted(deltas.items(), key=lambda item: -abs(item[1]))[:5])},
        "class_changes": {s: [c["baseline_class"], c["extended_class"]] for s, c in changes.items()
                          if c["baseline_class"] != c["extended_class"]},
        "per_satellite_changes": changes,
        "phase_rms_mm": {"baseline": baseline["phase_rms_mm"], "extended": result["phase_rms_mm"]},
        "multi_site_epochs": {sat: {"baseline": len(old_multi.get(sat, [])), "extended": len(new_multi.get(sat, [])),
                                    "gained": sorted(set(new_multi.get(sat, [])) - set(old_multi.get(sat, [])))}
                              for sat in sorted(new_multi)},
        "score": strip(result)}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "station": station, "extra_station_detail": report["extra_station_detail"],
        "all_satellites": [baseline["groups"]["all"]["fit"]["rms_3d_m"], result["groups"]["all"]["fit"]["rms_3d_m"]],
        "determined_in_both": [report["determined_in_both"]["baseline"]["fit"]["rms_3d_m"],
                               report["determined_in_both"]["extended"]["fit"]["rms_3d_m"], len(both)],
        "determined_in_both_delta_m": report["determined_in_both_delta_m"], "class_changes": report["class_changes"],
        "multi_site_gained": {sat: v["gained"] for sat, v in report["multi_site_epochs"].items() if v["gained"]},
        "new_station_phase_rms_mm": result["phase_rms_mm"].get(station),
        "iterations": len(step["history"])}, indent=2), flush=True)


if __name__ == "__main__":
    main()
