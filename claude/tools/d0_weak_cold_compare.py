"""Weak-prior cold start versus the nominal-prior warm solution (guarded evaluator).

Same predeclared flags as the other two controls: maximum sampled position
difference below 1 mm and maximum D0 difference below 1e-10 m/s^2. Numerical
robustness, not accuracy.

Unlike the warm weak-prior run, this one re-derives the solution from a zero start,
so a small difference here is a real re-convergence agreement rather than a step
the solver declined to take. `evaluate_d0.py` is deliberately not reused: it
hardcodes the original 1000 m / 1 m/s orbit prior in its cost audit.
"""
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import sha
from claude.tools.evaluate_ablation import Reference
from claude.tools.d0_step import BASE
from claude.tools.d0_review import CAMPAIGN as NOMINAL, NOMINAL_D0, cartesian
from claude.tools.d0_pilot import SCALE
from claude.tools.d0_weak_pilot import ORBIT_FACTOR
from claude.tools.d0_weak_compare import POSITION_GATE_M, COEFFICIENT_GATE_MPS2, COMMON_LIMIT_S, load, declared_cost


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder = Path(sys.argv[1])
    manifest = json.loads((folder/"validation.json").read_text())
    nominal_manifest = json.loads((NOMINAL/"validation.json").read_text())
    fit, step = load(folder, manifest)
    nominal, nominal_step = load(NOMINAL, nominal_manifest)
    prepare = json.loads((folder/"prepare/step.json").read_text())
    if prepare["fixture_sha256"] != nominal_manifest["artifacts_sha256"]["prepare/fixture.json"]:
        raise ValueError("Weak-cold run did not use the nominal fixture")
    if not (prepare["cold_start"] and prepare["weak_orbit_prior"]):
        raise ValueError("Preparation is not the weak-prior cold start")

    np.testing.assert_array_equal(fit["names"], nominal["names"])
    np.testing.assert_array_equal(fit["satellites"], nominal["satellites"])
    np.testing.assert_array_equal(fit["times_s"], nominal["times_s"])
    names = {str(n): i for i, n in enumerate(fit["names"])}
    satellites = [str(s) for s in fit["satellites"]]
    stations = sorted({n.split(":")[1] for n in names if n.startswith("wet:")})

    position = np.linalg.norm(fit["states"][:, :, :3]-nominal["states"][:, :, :3], axis=2)
    velocity = np.linalg.norm(fit["states"][:, :, 3:]-nominal["states"][:, :, 3:], axis=2)
    per_satellite = {}
    for si, sat in enumerate(satellites):
        j = names[f"srpD0:{sat}"]
        a = NOMINAL_D0+SCALE*float(fit["x"][j])
        b = NOMINAL_D0+SCALE*float(nominal["x"][j])
        per_satellite[sat] = {"max_position_difference_m": float(position[si].max()),
                              "rms_position_difference_m": float(np.sqrt(np.mean(position[si]**2))),
                              "max_velocity_difference_mps": float(velocity[si].max()),
                              "weak_cold_D0_mps2": a, "nominal_D0_mps2": b, "D0_difference_mps2": a-b}
    max_position = float(position.max())
    max_coefficient = max(abs(v["D0_difference_mps2"]) for v in per_satellite.values())

    audit, prior_terms = declared_cost(fit, names, satellites, stations, 1000.*ORBIT_FACTOR, 1.*ORBIT_FACTOR)
    cost = step["history"][-1]["cost_after"]
    np.testing.assert_allclose(audit, cost, rtol=0, atol=2e-8)

    reference = Reference()
    baseline = np.load(BASE/"six-1/solution.npz")
    domains = {}
    for domain, limit in (("common", COMMON_LIMIT_S), ("full", None)):
        rms, n, per = cartesian(reference, fit["states"], fit["times_s"], fit["satellites"], limit)
        nominal_rms, nominal_n, _ = cartesian(reference, nominal["states"], nominal["times_s"],
                                              nominal["satellites"], limit)
        fixed_rms, fixed_n, _ = cartesian(reference, baseline["states"], baseline["times_s"],
                                          baseline["satellites"], limit)
        expected = 403 if domain == "common" else 775
        if not n == nominal_n == fixed_n == expected:
            raise ValueError(f"Sample count mismatch in {domain}")
        domains[domain] = {"samples": n, "weak_cold_rms_m": rms, "nominal_rms_m": nominal_rms,
                           "fixed_d0_baseline_rms_m": fixed_rms, "weak_cold_minus_nominal_m": rms-nominal_rms,
                           "weak_cold_reduction_versus_fixed_percent": 100*(1-rms/fixed_rms),
                           "per_satellite_rms_m": {s: v["rms_3d_m"] for s, v in per.items()}}

    covariance = fit["retained_covariance"]
    np.testing.assert_allclose(covariance, covariance.T, rtol=0, atol=1e-12)
    np.linalg.cholesky(covariance)
    classes = {}
    for sat in satellites:
        k = names[f"orbit:{sat}:0"]
        sigma = float(np.sqrt(np.trace(covariance[k:k+3, k:k+3])))
        classes[sat] = {"initial_position_sigma_m": sigma,
                        "class": "determined" if sigma <= 10. else "poorly_determined"}

    report = {
        "status": "weak_cold_start_compared",
        "declared_priors": {"position_sigma_m": 1000.*ORBIT_FACTOR, "velocity_sigma_mps": 1.*ORBIT_FACTOR,
                            "factor": ORBIT_FACTOR, "wet_priors_unchanged": True, "d0_prior": None},
        "gates": {"position_m": POSITION_GATE_M, "coefficient_mps2": COEFFICIENT_GATE_MPS2,
                  "meaning": "start and prior independence, not an accuracy gate"},
        "max_position_difference_m": max_position,
        "max_velocity_difference_mps": float(velocity.max()),
        "max_coefficient_difference_mps2": max_coefficient,
        "position_gate_pass": bool(max_position < POSITION_GATE_M),
        "coefficient_gate_pass": bool(max_coefficient < COEFFICIENT_GATE_MPS2),
        "worst_satellite": max(per_satellite, key=lambda s: per_satellite[s]["max_position_difference_m"]),
        "sampled_positions": int(position.size), "epochs": int(len(fit["times_s"])),
        "weak_cold_cost": cost, "nominal_cost": nominal_step["history"][-1]["cost_after"],
        "independent_cost_with_declared_sigmas": audit, "independent_cost_prior_terms": prior_terms,
        "independent_cost_difference": audit-cost,
        "note_costs_use_different_priors": "weak-cold cost uses 10000 m / 10 m/s orbit priors; not comparable term by term",
        "max_residual_difference_m": float(np.max(np.abs(fit["residual_m"]-nominal["residual_m"]))),
        "iterations": len(step["history"]), "accepted_trials": manifest["accepted_trials"],
        "history": step["history"],
        "zero_start_cost": prepare["zero_start_cost"],
        "seed_trajectory_bitwise": prepare["seed_trajectory_bitwise"],
        "scoring": domains,
        "determinability": {"determined": sorted(s for s, v in classes.items() if v["class"] == "determined"),
                            "poorly_determined": sorted(s for s, v in classes.items() if v["class"] != "determined"),
                            "per_satellite": classes},
        "per_satellite": per_satellite,
        "reference_sha256": reference.sha256,
        "covariance_positive_definite": True,
    }
    if not (report["position_gate_pass"] and report["coefficient_gate_pass"]):
        report["status"] = "weak_cold_start_flag_exceeded"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"comparison.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("per_satellite", "determinability", "history", "scoring")}, indent=2), flush=True)
    for domain, value in domains.items():
        print(domain, {k: v for k, v in value.items() if k != "per_satellite_rms_m"}, flush=True)
    if report["status"] != "weak_cold_start_compared":
        raise RuntimeError(f"Weak cold start exceeded a predeclared flag: position {max_position} m, "
                           f"coefficient {max_coefficient} m/s^2")


if __name__ == "__main__":
    main()
