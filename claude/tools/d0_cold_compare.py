"""Cold-versus-warm comparison for the station-only D0 solution (guarded evaluator).

Predeclared in Astra's handoff before this run: maximum sampled position difference
below 1 mm and maximum D0 difference below 1e-10 m/s^2. These are numerical
start-independence gates, not orbit-accuracy gates. Actual values are always
reported, and a failure is preserved rather than explained away.

Reads the reference SP3 for scoring only. It never builds a pilot and never feeds
anything back into the estimator.
"""
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import ORIGIN
from claude.tools.evaluate_ablation import Reference
from claude.tools.d0_step import BASE
from claude.tools.d0_review import CAMPAIGN as WARM, NOMINAL_D0, cartesian
from claude.tools.d0_pilot import SCALE

POSITION_GATE_M = 1e-3
COEFFICIENT_GATE_MPS2 = 1e-10
COMMON_LIMIT_S = 10810.


def load(campaign, manifest):
    final = campaign/manifest["final"]
    step = json.loads((final/"step.json").read_text())
    if step["status"] != "converged":
        raise ValueError(f"{campaign.name} did not converge")
    if sha(final/"solution.npz") != step["solution_sha256"]:
        raise ValueError(f"{campaign.name} final solution hash changed")
    return np.load(final/"solution.npz"), step


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder = Path(sys.argv[1])
    cold_manifest = json.loads((folder/"validation.json").read_text())
    warm_manifest = json.loads((WARM/"validation.json").read_text())
    cold, cold_step = load(folder, cold_manifest)
    warm, warm_step = load(WARM, warm_manifest)
    prepare = json.loads((folder/"prepare/step.json").read_text())
    if prepare["fixture_sha256"] != warm_manifest["artifacts_sha256"]["prepare/fixture.json"]:
        raise ValueError("Cold start did not use the warm fixture")

    np.testing.assert_array_equal(cold["names"], warm["names"])
    np.testing.assert_array_equal(cold["satellites"], warm["satellites"])
    np.testing.assert_array_equal(cold["times_s"], warm["times_s"])
    names = {str(n): i for i, n in enumerate(cold["names"])}
    satellites = [str(s) for s in cold["satellites"]]

    position = np.linalg.norm(cold["states"][:, :, :3]-warm["states"][:, :, :3], axis=2)
    velocity = np.linalg.norm(cold["states"][:, :, 3:]-warm["states"][:, :, 3:], axis=2)
    per_satellite = {}
    for si, sat in enumerate(satellites):
        j = names[f"srpD0:{sat}"]
        cold_d0 = NOMINAL_D0+SCALE*float(cold["x"][j])
        warm_d0 = NOMINAL_D0+SCALE*float(warm["x"][j])
        per_satellite[sat] = {
            "max_position_difference_m": float(position[si].max()),
            "rms_position_difference_m": float(np.sqrt(np.mean(position[si]**2))),
            "max_velocity_difference_mps": float(velocity[si].max()),
            "cold_D0_mps2": cold_d0, "warm_D0_mps2": warm_d0,
            "D0_difference_mps2": cold_d0-warm_d0,
        }
    max_position = float(position.max())
    max_coefficient = max(abs(v["D0_difference_mps2"]) for v in per_satellite.values())
    worst_sat = max(per_satellite, key=lambda s: per_satellite[s]["max_position_difference_m"])

    cold_cost = cold_step["history"][-1]["cost_after"]
    warm_cost = warm_step["history"][-1]["cost_after"]
    residual_difference = float(np.max(np.abs(cold["residual_m"]-warm["residual_m"])))

    reference = Reference()
    domains = {}
    for domain, limit in (("common", COMMON_LIMIT_S), ("full", None)):
        cold_rms, cold_n, cold_per = cartesian(reference, cold["states"], cold["times_s"], cold["satellites"], limit)
        warm_rms, warm_n, _ = cartesian(reference, warm["states"], warm["times_s"], warm["satellites"], limit)
        baseline = np.load(BASE/"six-1/solution.npz")
        fixed_rms, fixed_n, _ = cartesian(reference, baseline["states"], baseline["times_s"],
                                          baseline["satellites"], limit)
        expected = 403 if domain == "common" else 775
        if not cold_n == warm_n == fixed_n == expected:
            raise ValueError(f"Sample count mismatch in {domain}")
        domains[domain] = {"samples": cold_n, "cold_rms_m": cold_rms, "warm_rms_m": warm_rms,
                           "fixed_d0_baseline_rms_m": fixed_rms, "cold_minus_warm_m": cold_rms-warm_rms,
                           "cold_reduction_versus_fixed_percent": 100*(1-cold_rms/fixed_rms),
                           "warm_reduction_versus_fixed_percent": 100*(1-warm_rms/fixed_rms),
                           "per_satellite_cold_rms_m": {s: v["rms_3d_m"] for s, v in cold_per.items()}}

    covariance = cold["retained_covariance"]
    np.testing.assert_allclose(covariance, covariance.T, rtol=0, atol=1e-12)
    np.linalg.cholesky(covariance)
    classes = {}
    for sat in satellites:
        k = names[f"orbit:{sat}:0"]
        sigma = float(np.sqrt(np.trace(covariance[k:k+3, k:k+3])))
        classes[sat] = {"initial_position_sigma_m": sigma,
                        "class": "determined" if sigma <= 10. else "poorly_determined"}

    report = {
        "status": "cold_start_compared",
        "gates": {"position_m": POSITION_GATE_M, "coefficient_mps2": COEFFICIENT_GATE_MPS2,
                  "declared_in": "claude/ASTRA_VERIFICATION_HANDOFF.md before this run",
                  "meaning": "numerical start independence, not an accuracy gate"},
        "max_position_difference_m": max_position,
        "max_velocity_difference_mps": float(velocity.max()),
        "max_coefficient_difference_mps2": max_coefficient,
        "position_gate_pass": bool(max_position < POSITION_GATE_M),
        "coefficient_gate_pass": bool(max_coefficient < COEFFICIENT_GATE_MPS2),
        "worst_satellite": worst_sat,
        "sampled_positions": int(position.size), "satellites": len(satellites),
        "epochs": int(len(cold["times_s"])),
        "cold_cost": cold_cost, "warm_cost": warm_cost, "cost_difference": cold_cost-warm_cost,
        "max_residual_difference_m": residual_difference,
        "cold_iterations": len(cold_step["history"]),
        "cold_accepted_trials": cold_manifest["accepted_trials"],
        "cold_history": cold_step["history"],
        "cold_zero_start_cost": prepare["zero_start_cost"],
        "cold_seed_trajectory_bitwise": prepare.get("seed_trajectory_bitwise"),
        "scoring": domains,
        "determinability": {"determined": sorted(s for s, v in classes.items() if v["class"] == "determined"),
                            "poorly_determined": sorted(s for s, v in classes.items() if v["class"] != "determined"),
                            "per_satellite": classes},
        "per_satellite": per_satellite,
        "reference_sha256": reference.sha256,
        "covariance_positive_definite": True,
    }
    if not (report["position_gate_pass"] and report["coefficient_gate_pass"]):
        report["status"] = "cold_start_gate_failed"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"comparison.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("per_satellite", "determinability", "cold_history", "scoring")},
                     indent=2), flush=True)
    for domain, value in domains.items():
        print(domain, {k: v for k, v in value.items() if k != "per_satellite_cold_rms_m"}, flush=True)
    if report["status"] != "cold_start_compared":
        raise RuntimeError(f"Cold start failed a predeclared gate: position {max_position} m, "
                           f"coefficient {max_coefficient} m/s^2")


if __name__ == "__main__":
    main()
