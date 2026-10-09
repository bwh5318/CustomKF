"""Worker 3: solve the accumulated transfer system, map δx to orbits, run the calibration, then (only if it passes)
the candidate analysis. Protocol: `PROTOCOL.md` (pinned by hash in `common.py`).

    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.experiments.transfer.solve --last LAST_CHUNK_RUN

Outputs `transfer.json` (checks, calibration, candidates) and `transfer.npz` (δx per target, per-epoch scale
responses, 15-min orbit responses) in the run folder.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np

from Opus_Fork.experiments.transfer.common import (AMENDMENTS_SHA256, TARGETS, K, COL, NOPCV, SD3, MultiAccumulator, harm,
                                                   candidates_allowed, chunk_chain,
                                                   helmert_scale,
                                                   hourly, load_linearization_point, run_dir, scale_operator, sha,
                                                   ut_hours, write_json)
from Opus_Fork.paths import RESULTS

OBSERVED_AMP12, OBSERVED_PEAK12 = 0.311, 4.5
TIDES = ("solid_iers_minus_fixture", "otl_nodal_minus_fixture", "tides_both")


def rac_axes(r, v):
    radial = r/np.linalg.norm(r)
    normal = np.cross(r, v)/np.linalg.norm(np.cross(r, v))
    return np.array([radial, np.cross(normal, radial), normal])


def category(amp, peak):
    ratio = amp/OBSERVED_AMP12
    dphase = abs(((peak-OBSERVED_PEAK12)+6) % 12-6)
    if ratio < 0.10:
        return "negligible"
    if ratio >= 0.50 and dphase <= 1.5:
        return "capable of the magnitude"
    return "minor contributor"


def main():
    folder = run_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument("--last", type=Path, required=True)
    args = parser.parse_args()
    t0 = time.perf_counter()
    lp = load_linearization_point()
    pilot, x, products = lp.pilot, lp.x, lp.products
    last = json.loads((args.last/"step.json").read_text())
    assert last["status"] == "transfer_chunk_complete" and last["stop"] == pilot.epoch_count
    assert {k: v for k, v in last["binding"].items() if k != "tides"} == lp.binding
    assert sha(args.last/"acc.npz") == last["acc_sha256"]
    with np.load(args.last/"acc.npz") as data:
        acc = MultiAccumulator.restore(data)
    checks = {}
    # K1 over the whole contiguous chunk chain (checkpoint-A review A05; it was recorded per chunk but not enforced).
    chain = chunk_chain(args.last, pilot.epoch_count)
    checks["K1_max_abs_m"], checks["K1_pass"] = chain["K1_max_abs_m"], chain["K1_pass"]

    # K2: the accumulated R (and y column of Z) against the fit's own final lin2 checkpoint.
    with np.load(SD3/"lin2-chunk-132-144"/"checkpoint.npz") as fit:
        fit_R, fit_z, fit_norm2 = fit["R"], fit["z"], fit["norm2"]
    # Amendment A1 (PROTOCOL.md, 28 Sep, made before any candidate was analysed): a QR factor is unique only up to
    # the sign of each row (Householder convention), so R and the y column of Z are compared after aligning every
    # row's sign to the fit's. The raw, sign-sensitive difference is kept for the record.
    sign = np.sign(np.diag(acc.R))*np.sign(np.diag(fit_R))
    sign[sign == 0] = 1.
    checks["K2_R_raw_max_abs_diff_rel"] = float(np.max(np.abs(acc.R-fit_R))/np.max(np.abs(fit_R)))
    checks["K2_rows_sign_flipped"] = int(np.sum(sign < 0))
    checks["K2_R_max_abs_diff_rel"] = float(np.max(np.abs(acc.R*sign[:, None]-fit_R))/np.max(np.abs(fit_R)))
    checks["K2_absR_max_abs_diff_rel"] = float(np.max(np.abs(np.abs(acc.R)-np.abs(fit_R)))/np.max(np.abs(fit_R)))
    checks["K2_z_max_abs_diff_rel"] = float(np.max(np.abs(acc.Z[:, COL["y"]]*sign-fit_z))/np.max(np.abs(fit_z)))
    checks["K2_norm2_max_rel_diff"] = float(np.max(np.abs(acc.norm2-fit_norm2)/np.maximum(fit_norm2, 1e-300)))
    checks["K2_pass"] = checks["K2_R_max_abs_diff_rel"] <= 1e-6 and checks["K2_z_max_abs_diff_rel"] <= 1e-6
    del fit_R, fit_z, fit_norm2

    c, z, s = pilot.constraints(x)
    zc = np.zeros((len(z), K))
    zc[:, COL["y"]] = z
    acc.add_constraints(c, zc, s)
    ts = time.perf_counter()
    est, mapping, reduction = acc.solve()
    solve_s = time.perf_counter()-ts
    index = pilot.index
    fit_record = lp.step["history"][-1]
    checks["K3_reduction_y"] = float(reduction[COL["y"]])
    checks["K3_fit_predicted_reduction"] = float(fit_record["predicted_reduction"])
    checks["K3_reduction_rel_diff"] = abs(checks["K3_reduction_y"]/checks["K3_fit_predicted_reduction"]-1)

    # Orbit responses on the solution's 5-min grid (00:00-23:50 UT) and the 96 epochs at 15 min.
    with np.load(SD3/"lin2-solve"/"solution.npz") as f:
        times5, sd3_states, sats = f["times_s"].copy(), f["states"].copy(), [str(v) for v in f["satellites"]]
    assert sats == pilot.sats
    hours5 = ut_hours(pilot.context, times5)
    i15 = np.flatnonzero(np.isclose(np.round(hours5*4), hours5*4, rtol=0, atol=1e-9) & (hours5 < 24))
    assert len(i15) == 96 and np.allclose(hours5[i15], np.arange(96)/4)
    i15_set = set(int(j) for j in i15)
    ns, nt = len(sats), len(times5)
    dr = np.zeros((ns, nt, 3, K))
    pos, vel = np.zeros((ns, nt, 3)), np.zeros((ns, nt, 3))
    jac = {}
    step_bound = force_bound = 0.
    for si, sat in enumerate(sats):
        k0 = index[f"orbit:{sat}:0"]
        srp = [index[f"srp{('D0', 'Y0', 'B0', 'Bc1', 'Bs1')[col]}:{sat}"] for col in pilot.estimate]
        tr = products.trajectories[sat]
        step_bound = max(step_bound, float(np.linalg.norm(est[k0:k0+3, 0])+pilot.duration*np.linalg.norm(est[k0+3:k0+6, 0])))
        for ti, t in enumerate(times5):
            st = products.state(sat, t)
            pos[si, ti], vel[si, ti] = st[:3], st[3:]
            J = np.hstack([tr.partial(t)[:3], tr.force_partial(t)[:3, list(pilot.estimate)]*1e-7])
            dr[si, ti] = J@est[np.r_[k0:k0+6, srp]]
            if ti in i15_set:
                jac[si, ti] = (J, np.r_[k0:k0+6, srp])
            force_bound = max(force_bound, float(np.linalg.norm(dr[si, ti, :, 0])))
    checks["K3_trajectory_step_bound_m"] = step_bound
    checks["K3_force_inclusive_sampled_bound_m"] = force_bound
    checks["K3_fit_trajectory_step_bound_m"] = float(fit_record["trajectory_step_bound_m"])
    checks["K3_pass"] = checks["K3_reduction_rel_diff"] <= 0.10 and max(step_bound, force_bound) < 1e-3
    checks["states_vs_products_max_abs_m"] = float(np.max(np.abs(sd3_states[:, :, :3]-pos)))

    # Per-epoch Helmert scale of every response column.
    scale = np.array([helmert_scale(pos[:, j], dr[:, j]) for j in i15])       # (96, K)
    hourly_scale = np.array([hourly(scale[:, kk]) for kk in range(K)])        # (K, 24)

    # ---------------- Calibration: S-nopcv-3 minus SD-3 (actual) vs the nopcv column (predicted) ----------------
    step_n = json.loads((NOPCV/"lin2-solve"/"step.json").read_text())
    assert step_n["status"] == "converged" and sha(NOPCV/"lin2-solve"/"solution.npz") == step_n["solution_sha256"]
    with np.load(NOPCV/"lin2-solve"/"solution.npz") as f:
        n_states, n_x, n_names = f["states"].copy(), f["x"].copy(), f["names"]
        assert [str(v) for v in f["satellites"]] == sats and np.array_equal(f["times_s"], times5)
    actual = n_states[:, :, :3]-sd3_states[:, :, :3]
    pred = dr[:, :, :, COL["nopcv"]]
    act_scale = np.array([helmert_scale(pos[:, j], actual[:, j])[0] for j in i15])
    pred_scale = scale[:, COL["nopcv"]]
    rms = lambda a: float(np.sqrt(np.mean(np.sum(a**2, axis=-1))))
    c1 = abs(pred_scale.mean()-act_scale.mean()) <= 0.20*abs(act_scale.mean())
    r2 = float(np.corrcoef(pred_scale, act_scale)[0, 1])
    c3_ratio = rms(actual-pred)/rms(actual)
    axes_all = np.array([[rac_axes(pos[s, t], vel[s, t]) for t in range(nt)] for s in range(ns)])
    rac_act = np.einsum("stij,stj->sti", axes_all, actual)
    rac_pred = np.einsum("stij,stj->sti", axes_all, pred)
    per_sat = {sat: dict(rms_actual_cm=rms(actual[si])*100, rms_residual_cm=rms(actual[si]-pred[si])*100,
                         ratio=rms(actual[si]-pred[si])/max(rms(actual[si]), 1e-12)) for si, sat in enumerate(sats)}
    sens = json.loads((RESULTS/"sensitivity_analysis.json").read_text())["arms"]["nopcv"]
    known_sd3 = np.array(sens["SD3"]["hourly_scale_ppb"])
    known_arm = np.array(sens["arm"]["hourly_scale_ppb"])
    implied = known_sd3+hourly(pred_scale)
    same_names = bool(np.array_equal(n_names, pilot.names))
    param = {}
    if same_names:
        sel = np.r_[[index[f"orbit:{s}:{k}"] for s in sats for k in range(6)],
                    [index[f"srp{('D0', 'Y0', 'B0', 'Bc1', 'Bs1')[col]}:{s}"] for s in sats for col in pilot.estimate]]
        dxa, dxp = n_x[sel]-x[sel], est[sel, COL["nopcv"]]
        param = dict(orbit_force_params_corr=float(np.corrcoef(dxa, dxp)[0, 1]),
                     orbit_force_params_rms_ratio_residual=float(np.linalg.norm(dxa-dxp)/np.linalg.norm(dxa)))
    calibration = dict(
        criteria=dict(C1="|mean_pred-mean_act| <= 0.20|mean_act|", C2="r >= 0.80 (96 per-epoch scales)",
                      C3="RMS3D(act-pred) <= 0.30 RMS3D(act)"),
        mean_scale_actual_ppb=float(act_scale.mean()), mean_scale_predicted_ppb=float(pred_scale.mean()),
        mean_scale_rel_error=float(abs(pred_scale.mean()-act_scale.mean())/abs(act_scale.mean())), C1_pass=bool(c1),
        scale_corr=r2, C2_pass=bool(r2 >= 0.80),
        rms3d_actual_cm=rms(actual)*100, rms3d_predicted_cm=rms(pred)*100, rms3d_residual_cm=rms(actual-pred)*100,
        residual_ratio=c3_ratio, C3_pass=bool(c3_ratio <= 0.30),
        rac_rms_actual_cm=(np.sqrt(np.mean(rac_act**2, axis=(0, 1)))*100).tolist(),
        rac_rms_predicted_cm=(np.sqrt(np.mean(rac_pred**2, axis=(0, 1)))*100).tolist(),
        rac_rms_residual_cm=(np.sqrt(np.mean((rac_act-rac_pred)**2, axis=(0, 1)))*100).tolist(),
        per_satellite=per_sat, worst_satellite_ratio=max(v["ratio"] for v in per_sat.values()),
        hourly_actual=harm(hourly(act_scale)), hourly_predicted=harm(hourly(pred_scale)),
        per_epoch_scale_actual_ppb=act_scale.tolist(), per_epoch_scale_predicted_ppb=pred_scale.tolist(),
        K4_helmert_vs_sensitivity_json_max_abs_ppb=float(np.max(np.abs(hourly(act_scale)-(known_arm-known_sd3)))),
        implied_nopcv_series=dict(harm(implied), known_amp12=sens["arm"]["scale"]["amp12"], known_mean=sens["arm"]["scale"]["mean"],
                                  known_peak12=sens["arm"]["scale"]["peak12_ut"], sd3_amp12=sens["SD3"]["scale"]["amp12"]),
        parameters=param, names_identical=same_names)
    calibration["pass"] = bool(c1 and r2 >= 0.80 and c3_ratio <= 0.30)
    print("calibration:", json.dumps({k: v for k, v in calibration.items() if not isinstance(v, (dict, list))}, indent=1), flush=True)

    report = dict(status="diagnostic_linear_transfer_not_accuracy_acceptance", protocol_sha256=lp.binding["protocol"],
                  protocol_amendments_sha256=AMENDMENTS_SHA256,
                  binding=lp.binding, tides_run=last["binding"]["tides"], last_chunk=str(args.last),
                  binding_fields_not_checked=lp.binding_fields_not_checked, targets=list(TARGETS), checks=checks,
                  solve_seconds=solve_s, accumulated_rows=acc.rows, local_total=acc.local_total, retained=acc.n,
                  calibration=calibration)
    arrays = dict(estimate=est, targets=np.array(TARGETS), names=np.array(pilot.names), scale_per_epoch_ppb=scale,
                  hours15=hours5[i15], dr15=dr[:, i15], pos15=pos[:, i15], actual_nopcv=actual, pred_nopcv=pred,
                  actual_scale_ppb=act_scale)

    report["chunk_chain"] = chain["chunks"]
    prerequisites = all(checks.get(k) for k in ("K1_pass", "K2_pass", "K3_pass"))
    report["prerequisites_pass"] = bool(prerequisites)
    if not candidates_allowed(checks, calibration):
        report["candidates"] = "NOT ANALYSED: prerequisite or calibration failed (PROTOCOL.md)"
    else:
        observed = known_sd3
        obs_h = harm(observed)
        o12 = np.array(obs_h["c12"])
        cand = {}
        cols = dict(COL)
        series = {name: hourly_scale[j] for name, j in cols.items()}
        per_epoch = {name: scale[:, j] for name, j in cols.items()}
        series["tides_both"] = series["solid_iers_minus_fixture"]+series["otl_nodal_minus_fixture"]
        per_epoch["tides_both"] = per_epoch["solid_iers_minus_fixture"]+per_epoch["otl_nodal_minus_fixture"]
        drs = {name: dr[:, :, :, j] for name, j in cols.items()}
        drs["tides_both"] = drs["solid_iers_minus_fixture"]+drs["otl_nodal_minus_fixture"]
        for name in [t for t in TARGETS if t != "y"]+["tides_both"]:
            h = harm(series[name])
            sign = -1. if name in TIDES else 1.
            imp = harm(sign*series[name])
            radial = np.einsum("stj,stj->st", drs[name], pos/np.linalg.norm(pos, axis=-1, keepdims=True))
            entry = dict(response=h, implied_sign=sign, implied_ours_minus_reference=imp,
                         projection_on_observed_12h=float(np.dot(imp["c12"], o12)/np.dot(o12, o12)),
                         amp12_ratio_to_observed=imp["amp12"]/OBSERVED_AMP12,
                         corr_hourly_with_observed=float(np.corrcoef(sign*series[name], observed)[0, 1]),
                         per_epoch_scale_rms_ppb=float(np.std(per_epoch[name])),
                         rms3d_cm=rms(drs[name])*100, rms_radial_cm=float(np.sqrt(np.mean(radial**2)))*100,
                         mean_radial_cm=float(radial.mean())*100, hourly_scale_ppb=series[name].tolist())
            if name in TIDES:
                entry["category"] = category(imp["amp12"], imp["peak12_ut"])
            if name in COL:
                j = COL[name]
                wet = [index[p] for p in pilot.names[:pilot.n] if p.startswith("wet:")]
                amb = [index[p] for p in pilot.names[:pilot.n] if p.startswith("amb:")]
                entry.update(wet_response_rms_mm=float(np.sqrt(np.mean(est[wet, j]**2)))*1000,
                             ambiguity_response_rms_mm=float(np.sqrt(np.mean(est[amb, j]**2)))*1000)
            cand[name] = entry
        # Height kernel: which network-height signal reproduces the observed 24 h + 12 h harmonics?
        rows_out = []
        for name in ("h24_cos_1mm", "h24_sin_1mm", "h12_cos_1mm", "h12_sin_1mm"):
            hh = cand[name]["response"]
            rows_out.append(hh["c24"]+hh["c12"])
        m4 = np.array(rows_out).T            # outputs [c24cos, c24sin, c12cos, c12sin] per unit input
        need = np.linalg.solve(m4, np.array(obs_h["c24"]+obs_h["c12"]))
        m12 = m4[2:, 2:]
        need12 = np.linalg.solve(m12, o12)
        w12, w24 = 2*np.pi/12, 2*np.pi/24
        gains = np.linalg.svd(m12, compute_uv=False)
        kernel = dict(
            constant_height_ppb_per_mm=cand["h_const_1mm"]["response"]["mean"],
            similarity_expectation_ppb_per_mm=float(1e-3/np.mean(np.linalg.norm(
                np.array([pilot.context["stations"][st]["fixed_xyz"] for st in pilot.stations]), axis=1))*1e9),
            h12_gain_ppb_per_mm_range=[float(gains[-1]), float(gains[0])],
            h12_only_required_height=dict(amp_mm=float(np.hypot(*need12)), peak_ut=float((np.arctan2(need12[1], need12[0])/w12) % 12)),
            joint_required_height=dict(amp24_mm=float(np.hypot(need[0], need[1])), peak24_ut=float((np.arctan2(need[1], need[0])/w24) % 24),
                                       amp12_mm=float(np.hypot(need[2], need[3])), peak12_ut=float((np.arctan2(need[3], need[2])/w12) % 12)),
            h24_to_12h_crosstalk_ppb_per_mm=[float(np.hypot(*m4[2:, 0])), float(np.hypot(*m4[2:, 1]))],
            h12_to_24h_crosstalk_ppb_per_mm=[float(np.hypot(*m4[:2, 2])), float(np.hypot(*m4[:2, 3]))])
        # Formal (unit-weight and a-posteriori-scaled) uncertainty of the hourly 12 h scale coefficients.
        a = np.zeros((96, acc.n))
        for e, j in enumerate(i15):
            h_op = scale_operator(pos[:, j])
            for si in range(ns):
                J, idx = jac[si, j]
                a[e, idx] += h_op[3*si:3*si+3]@J
        ah = a.reshape(24, 4, acc.n).mean(1)
        hh = np.arange(24)+0.5
        w = 2*np.pi/24
        design = np.column_stack([np.ones(24), np.cos(w*hh), np.sin(w*hh), np.cos(2*w*hh), np.sin(2*w*hh)])
        cfun = np.linalg.pinv(design)@ah
        cov_c = (cfun@mapping)@(cfun@mapping).T
        dof = acc.rows-acc.n-acc.local_total
        sigma0_sq = float(fit_record["cost_before"])/dof
        formal = dict(unit_weight_sigma_mean_ppb=float(np.sqrt(cov_c[0, 0])),
                      unit_weight_sigma_c12_ppb=[float(np.sqrt(cov_c[3, 3])), float(np.sqrt(cov_c[4, 4]))],
                      unit_weight_sigma_c24_ppb=[float(np.sqrt(cov_c[1, 1])), float(np.sqrt(cov_c[2, 2]))],
                      aposteriori_variance_factor=sigma0_sq, dof=int(dof),
                      note="formal only: fixture sigmas, white noise, no time correlation; not a calibrated uncertainty")
        report.update(observed_sd3=obs_h, candidates=cand, height_kernel=kernel, formal_scale_uncertainty=formal)
        for name, e in cand.items():
            imp = e["implied_ours_minus_reference"]
            print(f"{name:26s} resp mean {e['response']['mean']:+.4f} 12h {e['response']['amp12']:.4f}@{e['response']['peak12_ut']:.1f} "
                  f"24h {e['response']['amp24']:.4f}@{e['response']['peak24_ut']:.1f} | implied 12h {imp['amp12']:.4f}@{imp['peak12_ut']:.1f} "
                  f"proj {e['projection_on_observed_12h']:+.3f} r {e['corr_hourly_with_observed']:+.2f} {e.get('category', '')}", flush=True)
        print("kernel:", json.dumps(kernel, indent=1), flush=True)
        print("formal:", json.dumps(formal, indent=1), flush=True)
    report["seconds"] = time.perf_counter()-t0
    np.savez_compressed(folder/"transfer.npz", **arrays)
    report["transfer_npz_sha256"] = sha(folder/"transfer.npz")
    write_json(folder/"transfer.json", report)
    write_json(folder/"step.json", dict(status="transfer_solved", calibration_pass=calibration["pass"],
                                        prerequisites_pass=report["prerequisites_pass"], checks=checks,
                                        transfer_json_sha256=sha(folder/"transfer.json"), seconds=report["seconds"]))
    print("checks:", json.dumps(checks, indent=1), flush=True)


if __name__ == "__main__":
    main()
