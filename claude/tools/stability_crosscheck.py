"""Guarded cross-campaign check for the weak-prior cold start. Trajectories only; no IGS reads.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.stability_crosscheck COLD_CAMPAIGN

The standalone weak-cold evaluator compares only with the nominal-prior GUAM solution. This
compares its converged trajectory with the weak-warm and weak-perturbed solutions of Astra's
passed campaign (same 10x-weaker priors, same broadcast prior centres). It uses all 31
satellites and 37 solve epochs and applies the same predeclared 1 cm diagonal threshold.
It also reproduces that campaign's perturbed-vs-warm maximum as a method check. Writes only
crosscheck.json in the guarded run directory.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import forbid_precise_product_reads
from claude.tools.stability_step import BASE

EARLIER = ROOT / "claude/runs/20260911T162036Z-stability"
THRESHOLD_M = .01


def load(campaign, case):
    manifest = json.loads((campaign / "validation.json").read_text())
    # A failed nominal-prior gate is still a completed campaign worth cross-checking; report it.
    assert manifest["status"] in ("stability_checks_pass_not_absolute_accuracy_acceptance", "stability_gate_failed"), (campaign, manifest["status"])
    assert manifest["active_worker"] is None
    final = manifest["cases"][case]["final"]
    for name in (f"{final}/solution.npz", f"{final}/step.json"):
        assert sha(campaign / name) == manifest["artifacts_sha256"][name], name
    step = json.loads((campaign / final / "step.json").read_text())
    assert step["status"] == "converged" and step["experiment"]["prior_factor"] == 10.
    return manifest, step, np.load(campaign / final / "solution.npz")


def compare(a, b, satellites):
    distance = np.linalg.norm(a["states"][:, :, :3] - b["states"][:, :, :3], axis=2)
    si, ti = np.unravel_index(int(np.argmax(distance)), distance.shape)
    return {"max_m": float(distance.max()), "rms_m": float(np.sqrt(np.mean(distance**2))),
            "argmax": {"satellite": satellites[si], "epoch": int(ti)}, "one_cm_gate_pass": bool(distance.max() <= THRESHOLD_M),
            "per_satellite_max_m": {s: float(distance[i].max()) for i, s in enumerate(satellites)}}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    cold_campaign = parser.parse_args().campaign.resolve()
    cold_manifest, cold_step, cold = load(cold_campaign, "weak-cold")
    earlier_manifest, warm_step, warm = load(EARLIER, "weak-warm")
    _, perturbed_step, perturbed = load(EARLIER, "weak-perturbed")
    base_manifest = json.loads((BASE / "validation.json").read_text())
    base_path = BASE / base_manifest["final"] / "solution.npz"
    assert sha(base_path) == base_manifest["artifacts_sha256"][f"{base_manifest['final']}/solution.npz"]
    nominal = np.load(base_path)
    for other in (warm, perturbed, nominal):
        for key in ("names", "satellites", "times_s"):
            np.testing.assert_array_equal(cold[key], other[key], err_msg=key)
    shared = set(cold_manifest["source_sha256"]) & set(earlier_manifest["source_sha256"])
    source_differences = sorted(n for n in shared if cold_manifest["source_sha256"][n] != earlier_manifest["source_sha256"][n])
    satellites = [str(s) for s in cold["satellites"]]
    pairs = {"cold_vs_warm": compare(cold, warm, satellites), "cold_vs_perturbed": compare(cold, perturbed, satellites),
             "cold_vs_nominal_prior": compare(cold, nominal, satellites),
             "perturbed_vs_warm_method_check": compare(perturbed, warm, satellites)}
    names = [str(n) for n in cold["names"]]
    orbit = np.array([n.startswith("orbit:") for n in names])
    velocity = np.array([n.startswith("orbit:") and int(n.rsplit(":", 1)[1]) >= 3 for n in names])
    costs = {case: step["history"][-1]["cost_after"] for case, step in
             (("weak-cold", cold_step), ("weak-warm", warm_step), ("weak-perturbed", perturbed_step))}
    report = {
        "status": "cross_campaign_trajectory_check_not_accuracy_acceptance", "threshold_m": THRESHOLD_M,
        "cold_campaign": cold_campaign.relative_to(ROOT).as_posix(), "earlier_campaign": EARLIER.relative_to(ROOT).as_posix(),
        "cold_campaign_status": cold_manifest["status"], "earlier_campaign_status": earlier_manifest["status"],
        "cold_manifest_sha256": sha(cold_campaign / "validation.json"), "earlier_manifest_sha256": sha(EARLIER / "validation.json"),
        "shared_pinned_sources": len(shared), "shared_source_hash_differences": source_differences,
        "pairs": pairs, "final_cost": costs,
        "cold_minus_perturbed_cost": costs["weak-cold"] - costs["weak-perturbed"],
        "cold_minus_warm_cost": costs["weak-cold"] - costs["weak-warm"],
        "max_abs_parameter_difference_cold_vs_perturbed": {
            "initial_position_m": float(np.max(abs(cold["x"] - perturbed["x"])[orbit & ~velocity])),
            "initial_velocity_mps": float(np.max(abs(cold["x"] - perturbed["x"])[velocity]))},
        "histories": {"weak-cold": cold_step["history"], "weak-warm": warm_step["history"], "weak-perturbed": perturbed_step["history"]},
        "tool_sha256": sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "crosscheck.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("histories",)} | {
        "pairs": {k: {x: y for x, y in v.items() if x != "per_satellite_max_m"} for k, v in pairs.items()}}, indent=1))


if __name__ == "__main__":
    main()
