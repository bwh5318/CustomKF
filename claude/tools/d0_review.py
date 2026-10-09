"""Independent Opus review of Astra's station-only D0 campaign (guarded, read-only).

Three separate guarded workers, none of which reuses Astra's evaluator:

  reproduce : pins, checkpoint lineage and step algebra, then a *fresh* forward
              evaluation at the final x. Residuals, sigmas, cost and the 73-epoch
              sampled states must reproduce the archived solution. Also re-derives
              the D0 column absence from the prior block, the retained counts, the
              coefficients and the determinability classes, and cross-checks the
              station-estimated D0 against the independent reference-only fits.
  partials  : reintegrated plus/minus force partials for five satellites Astra did
              NOT check, at a ten times larger perturbation (less integrator noise).
  score     : Cartesian IGS scoring of the states recomputed by `reproduce`,
              pinned by hash, versus the archived six-hour fixed-D0 baseline.

`reproduce` and `partials` run the estimator and keep the precise-product audit
hook installed. `score` reads the reference SP3 and never builds a pilot.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import ORIGIN, forbid_precise_product_reads
from customkf.stage5b_step import restore
from claude.tools.ablation_step import sources
from claude.tools.d0_pilot import D0Pilot, SCALE
from claude.tools.force_parameter_fit import ForceTrajectory, INITIAL_P

CAMPAIGN = ROOT/"claude/runs/20260912T145220Z-station-d0"
BASE = ROOT/"claude/runs/20260912T021739Z-arc"
FORCE = ROOT/"claude/runs/20260912T032414Z-force-parameters"
UNCHECKED = ("G01", "G07", "G12", "G22", "G26")
NOMINAL_D0 = -1e-7


def folder():
    return Path(os.environ["CUSTOMKF_RUN_DIR"])


def pins(manifest):
    """Re-verify every pin the campaign recorded, against the current tree."""
    out = {}
    for group in ("source_sha256", "report_sha256"):
        bad = [n for n, d in manifest[group].items() if not (ROOT/n).exists() or sha(ROOT/n) != d]
        out[group] = {"pinned": len(manifest[group]), "mismatched": bad}
    bad = [r for r, d in manifest["artifacts_sha256"].items()
           if not (CAMPAIGN/r).exists() or sha(CAMPAIGN/r) != d]
    out["artifacts_sha256"] = {"pinned": len(manifest["artifacts_sha256"]), "mismatched": bad}
    out["baseline_manifest"] = sha(BASE/"validation.json") == manifest["baseline_manifest_sha256"]
    for key, value in out.items():
        if isinstance(value, dict) and value["mismatched"]:
            raise ValueError(f"Pin mismatch in {key}: {value['mismatched'][:4]}")
    if not out["baseline_manifest"]:
        raise ValueError("Six-hour baseline manifest changed")
    return out


def lineage(manifest):
    """Checkpoint chain warm -> linear-0 -> trial-0-0 -> linear-1, by hash and by value."""
    warm = CAMPAIGN/"prepare/warm"
    linear0, trial, final = CAMPAIGN/"linear-0", CAMPAIGN/manifest["accepted_trials"][0], CAMPAIGN/manifest["final"]
    meta = json.loads((CAMPAIGN/"prepare/step.json").read_text())
    warm_meta = json.loads((warm/"step.json").read_text())
    l0 = json.loads((linear0/"step.json").read_text())
    t0 = json.loads((trial/"step.json").read_text())
    f1 = json.loads((final/"step.json").read_text())
    checks = {
        "prepare_status_prepared": meta["status"] == "prepared",
        "warm_history_empty": warm_meta["history"] == [],
        "warm_fixture_matches_prepare": warm_meta["fixture_sha256"] == meta["fixture_sha256"],
        "warm_solution_hash": sha(warm/"solution.npz") == warm_meta["solution_sha256"],
        "linear0_direction_hash": sha(linear0/"direction.npz") == l0["direction_sha256"],
        "linear0_fixture": l0["fixture_sha256"] == meta["fixture_sha256"],
        "trial_solution_hash": sha(trial/"solution.npz") == t0["solution_sha256"],
        "final_solution_hash": sha(final/"solution.npz") == f1["solution_sha256"],
        "final_converged": f1["status"] == "converged",
        "final_update_not_applied": not f1["history"][-1]["update_applied"],
        "single_accepted_trial": manifest["accepted_trials"] == ["trial-0-0"],
    }
    w = np.load(warm/"solution.npz")
    d = np.load(linear0/"direction.npz")
    t = np.load(trial/"solution.npz")
    f = np.load(final/"solution.npz")
    np.testing.assert_array_equal(d["names"], w["names"])
    np.testing.assert_array_equal(f["names"], w["names"])
    checks["direction_x_is_warm_x"] = bool(np.array_equal(d["x"], w["x"]))
    alpha = t0["history"][-1]["step_fraction"]
    checks["trial_step_fraction"] = alpha
    checks["trial_x_is_direction_plus_alpha_step"] = bool(np.array_equal(t["x"], d["x"]+alpha*d["step"]))
    for key in ("x", "states", "residual_m", "sigma_m", "times_s", "satellites"):
        checks[f"final_{key}_equals_accepted_trial"] = bool(np.array_equal(f[key], t[key]))
    # The converged linearization re-formed its own QR, so its covariance is a new
    # matrix at the final iterate rather than a copy of the pre-step direction file.
    checks["final_covariance_is_refreshed"] = not np.array_equal(f["retained_covariance"], d["retained_covariance"])
    cost = [h["cost_before"] for h in f1["history"]]+[f1["history"][-1]["cost_after"]]
    checks["cost_monotone"] = all(b >= a for a, b in zip(cost[1:], cost[:-1]))
    checks["cost_sequence"] = cost
    failed = [k for k, v in checks.items() if v is False]
    if failed:
        raise ValueError("Lineage failure: "+", ".join(failed))
    return checks


def independent_cost(pilot, x, residual, sigma):
    """Rebuild the objective from the declared priors without reusing the evaluator."""
    z = residual/sigma
    prior = []
    for sat in pilot.sats:
        k = pilot.index[f"orbit:{sat}:0"]
        prior.extend(float(x[k+j])/(1000. if j < 3 else 1.) for j in range(6))
    for station in pilot.stations:
        a, b, c = (float(x[pilot.index[f"wet:{station}:{k}"]]) for k in ("0", "1", "6h"))
        prior.extend([a/.3, b/.3, (b-a)/.03, (c-b)/.03])
    return float(z@z+np.sum(np.square(prior))), len(prior)


def reference_d0():
    out = {}
    for path in sorted(FORCE.glob("d0-G*/fit.json")):
        fit = json.loads(path.read_text())
        if fit["variant"] != "d0":
            raise ValueError("Unexpected reference variant")
        out[fit["satellite"]] = float(fit["coefficients_mps2"][0])
    return out


def rank_correlation(a, b):
    def ranks(v):
        order = np.argsort(np.argsort(np.asarray(v, float)))
        return order.astype(float)
    ra, rb = ranks(a), ranks(b)
    return float(np.corrcoef(ra, rb)[0, 1])


def reproduce(manifest,args):
    report = {"pins": pins(manifest), "lineage": lineage(manifest)}
    fixture = CAMPAIGN/"prepare/fixture.json"
    final = CAMPAIGN/manifest["final"]
    fit = np.load(final/"solution.npz")
    pilot = D0Pilot(*restore(fixture))
    names = [str(n) for n in fit["names"]]
    if names != list(pilot.names):
        raise ValueError("Rebuilt parameter names differ from the archived solution")
    d0_columns = [pilot.index[f"srpD0:{s}"] for s in pilot.sats]
    report["structure"] = {
        "total_parameters": len(pilot.names), "retained_parameters": pilot.n,
        "local_clock_parameters": sum(map(len, pilot.local_names)),
        "d0_columns": len(d0_columns), "prior_sigma_entries": len(pilot.prior_sigma),
        "d0_columns_after_prior_block": min(d0_columns) >= len(pilot.prior_sigma),
        "expected_retained_541": pilot.n == 541,
    }

    # The warm start really is the archived fixed-D0 solution with zero corrections.
    warm = np.load(CAMPAIGN/"prepare/warm/solution.npz")
    embedded = pilot.embed(np.load(BASE/"six-1/solution.npz"))
    report["warm_start"] = {
        "embedding_reproduced_bitwise": bool(np.array_equal(embedded, warm["x"])),
        "warm_d0_exactly_zero": bool(np.all(warm["x"][d0_columns] == 0.)),
    }
    if not all(report["warm_start"].values()):
        raise ValueError("Warm start is not the unmodified fixed-D0 solution")

    x = fit["x"].copy()
    _, constraints, residual, sigma, _, cost, products = pilot.evaluate(x, jacobian=False)
    history = json.loads((final/"step.json").read_text())["history"][-1]
    states = np.array([[products.state(s, float(t)) for t in fit["times_s"]] for s in pilot.sats])
    report["forward_reproduction"] = {
        "residual_bitwise": bool(np.array_equal(residual, fit["residual_m"])),
        "sigma_bitwise": bool(np.array_equal(sigma, fit["sigma_m"])),
        "states_bitwise": bool(np.array_equal(states, fit["states"])),
        "cost": cost, "archived_cost_after": history["cost_after"],
        "cost_difference": cost-history["cost_after"],
        "rows": int(len(residual)),
    }
    if not report["forward_reproduction"]["residual_bitwise"]:
        raise ValueError("Fresh evaluation does not reproduce the archived residuals")
    np.testing.assert_allclose(cost, history["cost_after"], rtol=0, atol=1e-9)

    rebuilt, prior_rows = independent_cost(pilot, x, residual, sigma)
    report["independent_cost"] = {"value": rebuilt, "prior_terms": prior_rows,
                                  "difference": rebuilt-history["cost_after"]}
    np.testing.assert_allclose(rebuilt, history["cost_after"], rtol=0, atol=2e-8)

    c = constraints[0]
    report["no_d0_prior"] = {
        "prior_rows": int(c.shape[0]),
        "max_abs_prior_entry_in_d0_columns": float(np.max(np.abs(c[:, d0_columns]))),
        "any_nonzero": bool(np.any(c[:, d0_columns])),
    }
    if report["no_d0_prior"]["any_nonzero"]:
        raise ValueError("A prior row touches a D0 column")

    cov = fit["retained_covariance"]
    reference = reference_d0()
    station, ref, coefficients = [], [], {}
    for sat in pilot.sats:
        j = pilot.index[f"srpD0:{sat}"]
        k = pilot.index[f"orbit:{sat}:0"]
        total = NOMINAL_D0+SCALE*float(x[j])
        coefficients[sat] = {
            "scaled_correction": float(x[j]), "D0_mps2": total,
            "formal_sigma_mps2": SCALE*float(np.sqrt(cov[j, j])),
            "ratio_to_nominal": total/NOMINAL_D0,
            "reference_only_D0_mps2": reference[sat],
            "difference_mps2": total-reference[sat],
            "initial_position_sigma_m": float(np.sqrt(np.trace(cov[k:k+3, k:k+3]))),
        }
        station.append(total)
        ref.append(reference[sat])
    station, ref = np.array(station), np.array(ref)
    report["coefficients"] = coefficients
    report["d0_versus_reference"] = {
        "pearson": float(np.corrcoef(station, ref)[0, 1]), "spearman": rank_correlation(station, ref),
        "mean_difference_mps2": float(np.mean(station-ref)), "rms_difference_mps2": float(np.sqrt(np.mean((station-ref)**2))),
        "max_abs_difference_mps2": float(np.max(np.abs(station-ref))),
        "station_mean_mps2": float(np.mean(station)), "reference_mean_mps2": float(np.mean(ref)),
        "station_sd_mps2": float(np.std(station)), "reference_sd_mps2": float(np.std(ref)),
        "median_formal_sigma_mps2": float(np.median([c["formal_sigma_mps2"] for c in coefficients.values()])),
        "satellites_within_one_formal_sigma": int(sum(
            abs(c["difference_mps2"]) <= c["formal_sigma_mps2"] for c in coefficients.values())),
        "satellites_within_three_formal_sigma": int(sum(
            abs(c["difference_mps2"]) <= 3*c["formal_sigma_mps2"] for c in coefficients.values())),
    }
    classes = {s: ("determined" if coefficients[s]["initial_position_sigma_m"] <= 10. else "poorly_determined")
               for s in pilot.sats}
    report["determinability"] = {"rule": "initial position sigma <= 10 m (claude/SCORING_RULE.md)",
                                "determined": sorted(s for s, v in classes.items() if v == "determined"),
                                "poorly_determined": sorted(s for s, v in classes.items() if v != "determined"),
                                "max_initial_position_sigma_m": max(
                                    c["initial_position_sigma_m"] for c in coefficients.values())}
    np.savez_compressed(folder()/"states.npz", states=states, times_s=fit["times_s"],
                        satellites=fit["satellites"], x=x, names=fit["names"])
    report["states_sha256"] = sha(folder()/"states.npz")
    report["status"] = "independent_reproduction_pass"
    return report


def partials(manifest,args):
    """Reintegrated force partials for satellites Astra's preparation did not check."""
    fixture = CAMPAIGN/"prepare/fixture.json"
    final = CAMPAIGN/manifest["final"]
    fit = np.load(final/"solution.npz")
    pilot = D0Pilot(*restore(fixture))
    x = fit["x"].copy()
    products = pilot.products(x)
    checked_by_astra = json.loads((CAMPAIGN/"prepare/step.json").read_text())
    h = .01
    per_sat, worst = {}, 0.
    for sat in UNCHECKED:
        k = pilot.index[f"orbit:{sat}:0"]
        initial = pilot.seeds[sat]+x[k:k+6]
        j = pilot.index[f"srpD0:{sat}"]
        base_p = INITIAL_P.copy()
        base_p[0] += SCALE*float(x[j])
        plus, minus = base_p.copy(), base_p.copy()
        plus[0] += h*SCALE
        minus[0] -= h*SCALE
        tp = ForceTrajectory(initial, pilot.context["model"], pilot.duration, plus)
        tm = ForceTrajectory(initial, pilot.context["model"], pilot.duration, minus)
        original = products.trajectories[sat]
        available = [r for r in pilot.rows if r["satellite"] == sat]
        errors, magnitudes = [], []
        for row in [available[i] for i in np.linspace(0, len(available)-1, 6, dtype=int)]:
            analytic = pilot.force_partial_for(products, row, x)
            products.trajectories[sat] = tp
            yp = pilot.link(products, row, *pilot.state_for(x, row), pilot.windup[id(row)])[0]
            products.trajectories[sat] = tm
            ym = pilot.link(products, row, *pilot.state_for(x, row), pilot.windup[id(row)])[0]
            products.trajectories[sat] = original
            finite = (yp-ym)/(2*h)
            errors.append(float(np.max(np.abs(finite-analytic))))
            magnitudes.append(float(np.max(np.abs(analytic))))
        per_sat[sat] = {"rows_checked": 6, "entries": 12, "max_abs_error_m_per_scaled_D0": max(errors),
                        "max_abs_partial_m_per_scaled_D0": max(magnitudes),
                        "max_relative_error": max(errors)/max(magnitudes)}
        worst = max(worst, max(errors))
    report = {"status": "independent_force_partial_pass", "satellites": list(UNCHECKED),
              "astra_checked": ["G04", "G19", "G23", "G27"],
              "astra_max_error_m_per_scaled_D0": checked_by_astra["max_force_derivative_error_m_per_scaled_D0"],
              "astra_perturbation_scaled": .001, "perturbation_scaled": h,
              "entries": 12*len(UNCHECKED), "max_abs_error_m_per_scaled_D0": worst,
              "tolerance_m_per_scaled_D0": 5e-5, "per_satellite": per_sat}
    if worst > 5e-5:
        report["status"] = "independent_force_partial_fail"
        (folder()/"partials.json").write_text(json.dumps(report, indent=2)+"\n")
        raise ValueError(f"Force partial mismatch {worst}")
    return report


def cartesian(reference, states, times, satellites, limit=None):
    squares, per = [], {}
    for si, sat in enumerate(str(s) for s in satellites):
        values = []
        for ti, t in enumerate(float(v) for v in times):
            if limit is not None and t > limit:
                continue
            sample = reference.raw.samples.get((ORIGIN+int(round(t*1e9)), sat))
            if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:
                continue
            d = reference.epoch.celestial_to_terrestrial(t)@states[si, ti, :3]-sample.xyz_m
            values.append(float(d@d))
        squares.extend(values)
        per[sat] = {"samples": len(values), "rms_3d_m": float(np.sqrt(np.mean(values))) if values else None}
    return float(np.sqrt(np.mean(squares))), len(squares), per


def score(manifest,args):
    from claude.tools.evaluate_ablation import Reference
    source = Path(args.source)
    recomputed = json.loads((source/"reproduce.json").read_text())
    if sha(source/"states.npz") != recomputed["states_sha256"]:
        raise ValueError("Recomputed states changed since the reproduction worker")
    mine = np.load(source/"states.npz")
    fit = np.load(CAMPAIGN/manifest["final"]/"solution.npz")
    baseline = np.load(BASE/"six-1/solution.npz")
    np.testing.assert_array_equal(mine["states"], fit["states"])
    np.testing.assert_array_equal(baseline["times_s"], mine["times_s"])
    np.testing.assert_array_equal(baseline["satellites"], mine["satellites"])
    reference = Reference()
    astra = json.loads((CAMPAIGN/"evaluation/evaluation.json").read_text())["comparisons"]
    report = {"status": "independent_scoring_pass", "reference_sha256": reference.sha256,
              "states_from": "recomputed by claude.tools.d0_review reproduce", "domains": {}}
    for domain, limit in (("common", 10810.), ("full", None)):
        after, n_after, per_after = cartesian(reference, mine["states"], mine["times_s"], mine["satellites"], limit)
        before, n_before, per_before = cartesian(reference, baseline["states"], baseline["times_s"],
                                                 baseline["satellites"], limit)
        expected = 403 if domain == "common" else 775
        changes = {s: {"before_m": per_before[s]["rms_3d_m"], "after_m": per_after[s]["rms_3d_m"],
                       "change_m": per_after[s]["rms_3d_m"]-per_before[s]["rms_3d_m"]} for s in per_after}
        report["domains"][domain] = {
            "samples": n_after, "samples_expected": expected, "sample_counts_match": n_after == n_before == expected,
            "before_rms_m": before, "after_rms_m": after, "reduction_percent": 100*(1-after/before),
            "astra_before_rms_m": astra[domain]["before_rms_m"], "astra_after_rms_m": astra[domain]["after_rms_m"],
            "before_difference_m": before-astra[domain]["before_rms_m"],
            "after_difference_m": after-astra[domain]["after_rms_m"],
            "improved": sorted(s for s, v in changes.items() if v["change_m"] < 0),
            "regressions_over_10_cm": sorted(s for s, v in changes.items() if v["change_m"] > .1),
            "astra_regressions_over_10_cm": sorted(astra[domain]["regressions_over_10_cm"]),
            "per_satellite": changes,
        }
        d = report["domains"][domain]
        if not d["sample_counts_match"]:
            raise ValueError(f"Sample count mismatch in {domain}: {n_after}/{n_before}")
        np.testing.assert_allclose(after, astra[domain]["after_rms_m"], rtol=0, atol=1e-9)
        np.testing.assert_allclose(before, astra[domain]["before_rms_m"], rtol=0, atol=1e-9)
        if d["regressions_over_10_cm"] != d["astra_regressions_over_10_cm"]:
            raise ValueError(f"Regression set mismatch in {domain}")
    return report


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("reproduce", "partials", "score"))
    parser.add_argument("source", nargs="?", help="reproduce worker folder (score mode)")
    args = parser.parse_args()
    if args.mode != "score":
        # Every worker that builds a pilot keeps the precise-product prevention active.
        sys.addaudithook(forbid_precise_product_reads)
    manifest = json.loads((CAMPAIGN/"validation.json").read_text())
    if manifest["status"] != "station_d0_complete_not_accuracy_acceptance":
        raise ValueError("Campaign is not complete")
    report = {"reproduce": reproduce, "partials": partials, "score": score}[args.mode](manifest, args)
    report["campaign"] = str(CAMPAIGN)
    report["review_sources_sha256"] = {**sources(), "claude/tools/d0_review.py": sha(ROOT/"claude/tools/d0_review.py")}
    (folder()/f"{args.mode}.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("coefficients", "review_sources_sha256")}, indent=2)[:6000], flush=True)


if __name__ == "__main__":
    main()
