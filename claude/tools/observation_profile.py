"""Reference-dependent observation profiling; support diagnostic, never POD input.

Prepare one exact baseline linearization. Profile fixed orbital displacements
by eliminating free parameters with the existing block QR, then verify the joint
three-SV displacement with nonlinear nuisance re-estimation. No data editing.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from scipy.linalg import solve_triangular
from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5b_step import restore
from customkf.stage5_pilot import Pilot, forbid_precise_product_reads
from customkf.network_square_root import Block
from customkf.reduced_network import reduced_qr
from customkf.nonlinear_stop import model_reduction

BASE = ROOT / "validation/guam/20260911T155927Z"
REF = ROOT / "claude/runs/20260911T211901Z-dynamics-ceiling"
SATS = ("G18", "G03", "G22")


def checked_inputs():
    for folder in (BASE, REF):
        manifest = json.loads((folder / "validation.json").read_text())
        for name, digest in manifest["source_sha256"].items():
            assert sha(ROOT / name) == digest, name
        for name, digest in manifest["artifacts_sha256"].items():
            assert sha(folder / name) == digest, name
    context, rows, seeds = restore(BASE / "prepare/fixture.json")
    pilot = Pilot(context, rows, seeds)
    saved = np.load(BASE / "iteration-1/solution.npz")
    np.testing.assert_array_equal(saved["names"], pilot.names)
    delta = np.zeros(len(pilot.names))
    for sat in SATS:
        target = np.load(REF / sat / "diagnostic_fit.npz")["initial_state"]
        k = pilot.index[f"orbit:{sat}:0"]
        delta[k:k+6] = target - seeds[sat] - saved["x"][k:k+6]
    return pilot, saved, delta


def profile(blocks, constraints, fixed, free):
    """Solve J_free u against r-J_fixed d, including original prior equations."""
    n = constraints[0].shape[1]
    reduced = [Block(b.retained[:, free], b.local, b.target - b.retained @ fixed[:n], b.sigma) for b in blocks]
    c, z, s = constraints
    con = (c[:, free], z - c @ fixed[:n], s)
    solved = reduced_qr(reduced, con)
    full = fixed.copy()
    full[free] = solved.estimate[:len(free)]
    full[n:] = solved.estimate[len(free):]
    residual = []
    start = n
    for b in blocks:
        k = b.local.shape[1]
        residual.extend(b.target - b.retained @ full[:n] - b.local @ full[start:start+k])
        start += k
    prior_residual = z - c @ full[:n]
    sigma = np.concatenate([b.sigma for b in blocks])
    cost = float(np.sum((np.array(residual)/sigma)**2) + np.sum((prior_residual/s)**2))
    return full, np.array(residual), cost, solved


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "iterate"))
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    # Reference states are explicitly loaded from diagnostic NPZs. No direct
    # SP3/CLK reads are needed here; this is nevertheless reference-dependent.
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    pilot, baseline, delta = checked_inputs()
    orbit_count = 6 * len(pilot.sats)
    free = np.arange(orbit_count, pilot.n)
    spec = {"scope": "reference-dependent diagnostic; all other orbits fixed; nuisance-only nonlinear solve",
            "baseline_sha256": sha(BASE / "iteration-1/solution.npz"), "reference_manifest_sha256": sha(REF / "validation.json"),
            "helper_sha256": sha(Path(__file__)), "fixed_satellites": list(SATS)}
    if args.mode == "prepare":
        x = baseline["x"].copy()
        blocks, constraints, residual, sigma, _, cost, _ = pilot.evaluate(x)
        np.testing.assert_array_equal(residual, baseline["residual_m"])
        np.testing.assert_array_equal(sigma, baseline["sigma_m"])
        unrestricted = reduced_qr(blocks, constraints)
        np.testing.assert_allclose(unrestricted.retained_covariance, baseline["retained_covariance"], rtol=1e-10, atol=1e-10)
        reduction, _ = model_reduction(blocks, constraints, unrestricted.estimate)
        unconstrained_minimum = cost - reduction
        cases = {}
        outputs = {}
        for name, selected in (("baseline", ()), *((sat, (sat,)) for sat in SATS), ("joint", SATS)):
            fixed = np.zeros(len(x))
            for sat in selected:
                k = pilot.index[f"orbit:{sat}:0"]
                fixed[k:k+6] = delta[k:k+6]
            correction, post, predicted_cost, solved = profile(blocks, constraints, fixed, free)
            outputs[f"{name}_correction"] = correction
            outputs[f"{name}_residual_m"] = post
            cases[name] = {"predicted_cost": predicted_cost, "increase_vs_original_cost": predicted_cost-cost,
                           "nuisance_max_change_m": float(np.max(abs(correction[orbit_count:]))),
                           "workspace_mib": solved.workspace_estimate_bytes/2**20}
            if not selected:
                assert np.max(abs(correction[orbit_count:])) < .001
                assert abs(predicted_cost-cost) < 1e-5
        selected = np.array([pilot.index[f"orbit:{sat}:{k}"] for sat in SATS for k in range(6)])
        others_free = np.array([i for i in range(pilot.n) if i not in set(selected)])
        correction, post, predicted_cost, solved = profile(blocks, constraints, delta, others_free)
        # Independent covariance identity, allowing other orbit states to adjust.
        scales = np.tile([100.]*3+[.01]*3, len(SATS))
        cov = baseline["retained_covariance"][np.ix_(selected, selected)] / scales[:,None] / scales[None,:]
        root = np.linalg.cholesky(cov)
        z = solve_triangular(root, (delta[selected]-unrestricted.estimate[selected])/scales, lower=True)
        mahalanobis = float(z @ z)
        np.testing.assert_allclose(predicted_cost-unconstrained_minimum, mahalanobis, rtol=1e-6, atol=1e-5)
        cases["joint_other_orbits_free_linearized"] = {"predicted_cost": predicted_cost,
             "increase_vs_unconstrained_minimum": predicted_cost-unconstrained_minimum,
             "covariance_mahalanobis_squared": mahalanobis, "workspace_mib": solved.workspace_estimate_bytes/2**20}
        outputs["joint_other_orbits_free_correction"] = correction
        outputs["joint_other_orbits_free_residual_m"] = post
        np.savez_compressed(folder/"linear_profiles.npz", **outputs, baseline_x=x, baseline_input_residual_m=residual,
                            sigma_m=sigma, names=np.array(pilot.names), reference_delta=delta)
        report = {"status": "linear_profiles_complete_not_accuracy_acceptance", "experiment": spec,
                  "original_cost": cost, "unconstrained_linearized_minimum": unconstrained_minimum,
                  "cases": cases, "archive_sha256": sha(folder/"linear_profiles.npz")}
        (folder/"profile.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2),flush=True)
        return
    prepared = json.loads((args.prepared/"profile.json").read_text())
    assert prepared["experiment"] == spec
    assert sha(args.prepared/"linear_profiles.npz") == prepared["archive_sha256"]
    init = np.load(args.prepared/"linear_profiles.npz")
    history = []
    if args.previous:
        old = json.loads((args.previous/"profile.json").read_text())
        assert old["experiment"] == spec and sha(args.previous/"diagnostic_nuisance.npz") == old["archive_sha256"]
        x = np.load(args.previous/"diagnostic_nuisance.npz")["x"].copy()
        history = old["history"]
    else:
        x = init["baseline_x"] + init["joint_correction"]
    np.testing.assert_array_equal(x[:orbit_count], (baseline["x"]+delta)[:orbit_count])
    blocks, constraints, residual, sigma, _, cost, products = pilot.evaluate(x)
    correction, _, predicted_cost, solved = profile(blocks, constraints, np.zeros(len(x)), free)
    correction[:orbit_count] = 0
    predicted_reduction, dnorm = model_reduction(blocks, constraints, correction)
    maximum = float(np.max(abs(correction[orbit_count:])))
    stopped = maximum < .001 and abs(predicted_reduction) < 1e-5 and dnorm < 1e-5
    applied = False
    alpha = 0.
    if not stopped:
        for alpha in (1., .5, .25, .125):
            trial = x + alpha * correction
            _, _, trial_residual, _, _, trial_cost, trial_products = pilot.evaluate(trial,jacobian=False)
            if trial_cost <= cost:
                x, residual, products = trial, trial_residual, trial_products
                applied = True
                break
        if not applied:
            raise RuntimeError("No decreasing nuisance step; preserve failure")
    else:
        trial_cost = cost
    history.append({"iteration":len(history), "cost_before":cost, "cost_after":trial_cost,
                    "update_applied":applied, "step_fraction":alpha, "max_nuisance_step_m":maximum,
                    "predicted_reduction":predicted_reduction, "whitened_direction_norm_squared":dnorm})
    np.savez_compressed(folder/"diagnostic_nuisance.npz",x=x,names=np.array(pilot.names),residual_m=residual,sigma_m=sigma,
                        times_s=baseline["times_s"],satellites=baseline["satellites"],
                        states=np.array([[products.state(s,t) for t in baseline["times_s"]] for s in pilot.sats]))
    report = {"status":"converged" if stopped else "iteration_complete", "experiment":spec,"history":history,
              "archive_sha256":sha(folder/"diagnostic_nuisance.npz"),"workspace_mib":solved.workspace_estimate_bytes/2**20}
    (folder/"profile.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


if __name__ == "__main__":
    main()
