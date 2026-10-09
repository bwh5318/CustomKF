"""Weak-versus-nominal orbit-prior comparison for the station-only D0 fit (guarded).

Predeclared before the run, in the same terms as the cold-start control: maximum
sampled position difference below 1 mm and maximum D0 difference below 1e-10 m/s^2.
These are prior-sensitivity flags, not accuracy gates; actual values are reported
whether or not they pass.

`evaluate_d0.py` hardcodes the original 1000 m / 1 m/s orbit prior in its cost
audit, so it is deliberately not reused here. The independent objective below uses
the explicitly declared weak sigmas.
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


def declared_cost(fit, names, satellites, stations, position_sigma, velocity_sigma):
    """Objective with the sigmas this run actually declared, written out here."""
    z = fit["residual_m"]/fit["sigma_m"]
    prior = []
    for sat in satellites:
        k = names[f"orbit:{sat}:0"]
        prior.extend(float(fit["x"][k+j])/(position_sigma if j < 3 else velocity_sigma) for j in range(6))
    for station in stations:
        a, b, c = (float(fit["x"][names[f"wet:{station}:{k}"]]) for k in ("0", "1", "6h"))
        prior.extend([a/.3, b/.3, (b-a)/.03, (c-b)/.03])
    return float(z@z+np.sum(np.square(prior))), len(prior)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder = Path(sys.argv[1])
    weak_manifest = json.loads((folder/"validation.json").read_text())
    nominal_manifest = json.loads((NOMINAL/"validation.json").read_text())
    weak, weak_step = load(folder, weak_manifest)
    nominal, nominal_step = load(NOMINAL, nominal_manifest)
    prepare = json.loads((folder/"prepare/step.json").read_text())
    if prepare["fixture_sha256"] != nominal_manifest["artifacts_sha256"]["prepare/fixture.json"]:
        raise ValueError("Weak-prior run did not use the nominal fixture")

    np.testing.assert_array_equal(weak["names"], nominal["names"])
    np.testing.assert_array_equal(weak["satellites"], nominal["satellites"])
    np.testing.assert_array_equal(weak["times_s"], nominal["times_s"])
    names = {str(n): i for i, n in enumerate(weak["names"])}
    satellites = [str(s) for s in weak["satellites"]]
    stations = sorted({n.split(":")[1] for n in names if n.startswith("wet:")})

    position = np.linalg.norm(weak["states"][:, :, :3]-nominal["states"][:, :, :3], axis=2)
    velocity = np.linalg.norm(weak["states"][:, :, 3:]-nominal["states"][:, :, 3:], axis=2)
    per_satellite = {}
    for si, sat in enumerate(satellites):
        j = names[f"srpD0:{sat}"]
        weak_d0 = NOMINAL_D0+SCALE*float(weak["x"][j])
        nominal_d0 = NOMINAL_D0+SCALE*float(nominal["x"][j])
        per_satellite[sat] = {
            "max_position_difference_m": float(position[si].max()),
            "rms_position_difference_m": float(np.sqrt(np.mean(position[si]**2))),
            "max_velocity_difference_mps": float(velocity[si].max()),
            "weak_D0_mps2": weak_d0, "nominal_D0_mps2": nominal_d0,
            "D0_difference_mps2": weak_d0-nominal_d0,
        }
    max_position = float(position.max())
    max_coefficient = max(abs(v["D0_difference_mps2"]) for v in per_satellite.values())

    audit, prior_terms = declared_cost(weak, names, satellites, stations,
                                       1000.*ORBIT_FACTOR, 1.*ORBIT_FACTOR)
    weak_cost = weak_step["history"][-1]["cost_after"]
    np.testing.assert_allclose(audit, weak_cost, rtol=0, atol=2e-8)

    reference = Reference()
    domains = {}
    baseline = np.load(BASE/"six-1/solution.npz")
    for domain, limit in (("common", COMMON_LIMIT_S), ("full", None)):
        weak_rms, weak_n, weak_per = cartesian(reference, weak["states"], weak["times_s"], weak["satellites"], limit)
        nominal_rms, nominal_n, _ = cartesian(reference, nominal["states"], nominal["times_s"],
                                              nominal["satellites"], limit)
        fixed_rms, fixed_n, _ = cartesian(reference, baseline["states"], baseline["times_s"],
                                          baseline["satellites"], limit)
        expected = 403 if domain == "common" else 775
        if not weak_n == nominal_n == fixed_n == expected:
            raise ValueError(f"Sample count mismatch in {domain}")
        domains[domain] = {"samples": weak_n, "weak_rms_m": weak_rms, "nominal_rms_m": nominal_rms,
                           "fixed_d0_baseline_rms_m": fixed_rms, "weak_minus_nominal_m": weak_rms-nominal_rms,
                           "weak_reduction_versus_fixed_percent": 100*(1-weak_rms/fixed_rms),
                           "per_satellite_weak_rms_m": {s: v["rms_3d_m"] for s, v in weak_per.items()}}

    covariance = weak["retained_covariance"]
    np.testing.assert_allclose(covariance, covariance.T, rtol=0, atol=1e-12)
    np.linalg.cholesky(covariance)
    classes = {}
    for sat in satellites:
        k = names[f"orbit:{sat}:0"]
        sigma = float(np.sqrt(np.trace(covariance[k:k+3, k:k+3])))
        classes[sat] = {"initial_position_sigma_m": sigma,
                        "class": "determined" if sigma <= 10. else "poorly_determined"}

    report = {
        "status": "weak_orbit_prior_compared",
        "declared_priors": {"position_sigma_m": 1000.*ORBIT_FACTOR, "velocity_sigma_mps": 1.*ORBIT_FACTOR,
                            "factor": ORBIT_FACTOR, "wet_priors_unchanged": True, "d0_prior": None},
        "gates": {"position_m": POSITION_GATE_M, "coefficient_mps2": COEFFICIENT_GATE_MPS2,
                  "meaning": "prior sensitivity flag, not an accuracy gate"},
        "max_position_difference_m": max_position,
        "max_velocity_difference_mps": float(velocity.max()),
        "max_coefficient_difference_mps2": max_coefficient,
        "position_gate_pass": bool(max_position < POSITION_GATE_M),
        "coefficient_gate_pass": bool(max_coefficient < COEFFICIENT_GATE_MPS2),
        "worst_satellite": max(per_satellite, key=lambda s: per_satellite[s]["max_position_difference_m"]),
        "sampled_positions": int(position.size), "epochs": int(len(weak["times_s"])),
        "weak_cost": weak_cost, "nominal_cost": nominal_step["history"][-1]["cost_after"],
        "independent_cost_with_declared_sigmas": audit, "independent_cost_prior_terms": prior_terms,
        "independent_cost_difference": audit-weak_cost,
        "note_evaluate_d0_not_reused": "evaluate_d0.py hardcodes the 1000 m / 1 m/s orbit prior",
        "max_residual_difference_m": float(np.max(np.abs(weak["residual_m"]-nominal["residual_m"]))),
        "weak_iterations": len(weak_step["history"]),
        "weak_accepted_trials": weak_manifest["accepted_trials"],
        "weak_history": weak_step["history"],
        "preparation": {k: prepare[k] for k in ("weak_cost", "nominal_cost", "nominal_orbit_prior_terms",
                                                "cost_difference_from_analytic", "observation_residuals_bitwise")},
        "scoring": domains,
        "determinability": {"determined": sorted(s for s, v in classes.items() if v["class"] == "determined"),
                            "poorly_determined": sorted(s for s, v in classes.items() if v["class"] != "determined"),
                            "per_satellite": classes},
        "per_satellite": per_satellite,
        "reference_sha256": reference.sha256,
        "covariance_positive_definite": True,
    }
    if not (report["position_gate_pass"] and report["coefficient_gate_pass"]):
        report["status"] = "weak_orbit_prior_flag_exceeded"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"comparison.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("per_satellite", "determinability", "weak_history", "scoring")},
                     indent=2), flush=True)
    for domain, value in domains.items():
        print(domain, {k: v for k, v in value.items() if k != "per_satellite_weak_rms_m"}, flush=True)
    if report["status"] != "weak_orbit_prior_compared":
        raise RuntimeError(f"Weak-prior run exceeded a predeclared flag: position {max_position} m, "
                           f"coefficient {max_coefficient} m/s^2")


if __name__ == "__main__":
    main()
