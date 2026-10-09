"""Separate guarded fixed-domain IGS and nuisance diagnostics for wet experiment."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import ORIGIN
from claude.tools.wet_step import BASE
from claude.tools.evaluate_ablation import Reference, score, pooled, strip
from claude.tools.yell_continuation_review import residual_structure


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    folder = parser.parse_args().campaign
    manifest = json.loads((folder / "validation.json").read_text())
    reference = Reference()
    fixture = BASE / "prepare/fixture.json"
    initial = BASE / "prepare/initial.npz"
    before = score(reference, BASE / "iteration-1", fixture, initial)
    baseline = np.load(BASE / "iteration-1/solution.npz")
    case = manifest["cases"]["hourly"]
    path = folder / case["final"]
    step = json.loads((path / "step.json").read_text())
    assert step["status"] == "converged" and sha(path / "solution.npz") == step["solution_sha256"]
    fitted = np.load(path / "solution.npz")
    for key in ("times_s", "satellites"):
        np.testing.assert_array_equal(fitted[key], baseline[key])
    after = score(reference, path, fixture, initial)
    both = [s for s in before["per_satellite"] if before["per_satellite"][s]["class"] == after["per_satellite"][s]["class"] == "determined"]
    squares = []
    per = {}
    for si, sat in enumerate(fitted["satellites"]):
        local = []
        for ti, t in enumerate(fitted["times_s"]):
            sample = reference.raw.samples.get((ORIGIN + int(round(float(t) * 1e9)), str(sat)))
            if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:
                continue
            d = reference.epoch.celestial_to_terrestrial(float(t)) @ fitted["states"][si, ti, :3] - sample.xyz_m
            local.append(float(d @ d))
        cartesian = float(np.sqrt(np.mean(local)))
        old_rms = before["per_satellite"][str(sat)]["fit"]["rms_3d_m"]
        new_rms = after["per_satellite"][str(sat)]["fit"]["rms_3d_m"]
        np.testing.assert_allclose(cartesian, new_rms, rtol=0, atol=2e-8)
        delta = np.linalg.norm(fitted["states"][si, :, :3] - baseline["states"][si, :, :3], axis=1)
        per[str(sat)] = {"baseline_rms_m": old_rms, "hourly_rms_m": new_rms, "change_m": new_rms - old_rms,
                         "trajectory_delta_by_epoch_m": delta.tolist(), "trajectory_max_change_m": float(delta.max())}
        squares.extend(local)
    assert len(squares) == 403
    cartesian = float(np.sqrt(np.mean(squares)))
    np.testing.assert_allclose(cartesian, after["groups"]["all"]["fit"]["rms_3d_m"], rtol=0, atol=2e-8)
    data = json.loads(fixture.read_text())
    station_before, _, _, _ = residual_structure(data, baseline)
    station_after, _, _, _ = residual_structure(data, fitted)
    names = {str(n): i for i, n in enumerate(fitted["names"])}
    old_names = {str(n): i for i, n in enumerate(baseline["names"])}
    wet = {}
    for station in sorted(data["context"]["stations"]):
        nodes = [float(fitted["x"][names[f"wet:{station}:{k}"]]) for k in ("0", "hour1", "hour2", "1")]
        endpoints = [float(baseline["x"][old_names[f"wet:{station}:{k}"]]) for k in ("0", "1")]
        wet[station] = {"hourly_nodes_m": nodes, "baseline_endpoints_m": endpoints,
                        "interior_departure_from_own_endpoint_line_mm": (1000 * (np.array(nodes) - np.linspace(nodes[0], nodes[-1], 4))).tolist()}
    report = {"status": "wet_experiment_evaluated_not_accuracy_acceptance", "reference_sha256": reference.sha256,
              "cartesian_independent_rms_m": cartesian, "samples": len(squares), "per_satellite_change": per,
              "five_percent_rms_improvement": cartesian <= .95 * before["groups"]["all"]["fit"]["rms_3d_m"],
              "regressions_over_10_cm": [s for s, p in per.items() if p["change_m"] > .1],
              "determined_in_both": {"baseline": pooled(before, both), "hourly": pooled(after, both)},
              "baseline": strip(before), "hourly": strip(after), "station_residuals": {"baseline": station_before, "hourly": station_after},
              "wet": wet, "history": step["history"]}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("cartesian_independent_rms_m", "five_percent_rms_improvement", "regressions_over_10_cm")}, indent=2))


if __name__ == "__main__":
    main()
