"""Gradient experiment, Stage 1: linear predictions through the saved SD-3 Aug 3 operator (PROTOCOL.md here).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.gradients.transfer_grad

Re-accumulates the saved whitening inputs (no Jacobian is recomputed) with right-hand sides for the external gradient
fields (`Opus_Fork.gradients`). It runs the atmosphere experiment's reproduction checks (R1-R3 as amended there), then
solves both arms and maps δx to orbits. The predicted orbits (comparator + δr) are scored against IGS final by the
independent oracle (validation.oracle). Writes `gradients_linear.json` and `.npz` in the run folder.
"""
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from Opus_Fork import gradients as G
from Opus_Fork.experiments.atmosphere.transfer_atm import (GramAccumulator, LAST_CHUNK, SAVED_SOLVE, TRANSFER,
                                                           TRANSFER_NPZ_SHA256, TRANSFER_RESULT_SHA256, elw13_sigma,
                                                           load_chunks, rac, station_geometry, ure_cm)
from Opus_Fork.experiments.transfer.common import (COL as SAVED_COL, SD3, chunk_chain, harm, helmert_scale, hourly,
                                                   load_linearization_point, run_dir, sha, ut_hours, write_json)
from Opus_Fork.paths import ROOT

HERE = Path(__file__).resolve().parent
PROTOCOL_SHA256 = "51764fe2d9f3da260b84266b7417cba6044e84607463956228a2f3e9abc52ae4"
E13 = ROOT/"Opus_Fork/runs/20260927T163208Z-fit-E-elw13-3"
IGS_FINAL = Path(r"E:\pythontests\autocomparesp3\data\sp3_cache\IGS0OPSFIN_20262150000_01D_15M_ORB.SP3")
IGS_FINAL_SHA256 = "24bf0537593c803fd71c6ba135de828f38a5235521b2a85995792a96f13f8776"
MIDNIGHT_MJD = 61255             # 2026-08-03 00:00 GPST
TARGETS = ("y", "nopcv", "grad_op", "grad_op_h", "grad_op_w", "gpt3")
FIELDS = ("grad_op", "grad_op_h", "grad_op_w", "gpt3")


def check_protocol():
    got = hashlib.sha256((HERE/"PROTOCOL.md").read_bytes()).hexdigest()
    if got != PROTOCOL_SHA256:
        raise RuntimeError(f"PROTOCOL.md differs from its pin: {got}")
    return got


def build_targets(ep, stations, geo, fields):
    m = ep["meta"]
    T = np.zeros((len(ep["sigma"]), len(TARGETS)))
    T[:, 0] = m["targets"][:, SAVED_COL["y"]]
    T[:, 1] = m["targets"][:, SAVED_COL["nopcv"]]
    for k in range(len(T)):
        st = stations[int(m["station_index"][k])]
        e, az = math.radians(float(m["elevation_deg"][k])), math.radians(float(m["azimuth_deg"][k]))
        mjd = MIDNIGHT_MJD+float(m["ut_hour"][k])/24.-G.GPS_UTC_S/86400.
        gnh, geh, gnw, gew = fields["grad_op"].at(st, mjd)
        g3 = fields["gpt3"].at_position(geo[st]["lat"], geo[st]["lon"], mjd)
        dm = (G.slant((gnh, geh, gnw, gew), e, az), G.slant((gnh, geh, 0., 0.), e, az),
              G.slant((0., 0., gnw, gew), e, az), G.slant(g3, e, az))
        T[k, 2:] = [-v for v in dm]
    return T


def oracle_score(states, satellites, times, origin, frame, reference, keys=None):
    from validation.oracle import metrics as O1
    ours = O1.solution_ecef(states, satellites, times, origin, frame)
    start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
    if keys is None:
        keys = {k for k in set(reference) & set(ours) if start <= k[1] <= stop}
    return O1.summarize(reference, ours, frame, keys), keys


def main():
    folder = run_dir()
    t0 = time.perf_counter()
    protocol = check_protocol()
    lp = load_linearization_point()
    pilot, x, products = lp.pilot, lp.x, lp.products
    result = json.loads((TRANSFER/"transfer_result.json").read_text())
    chain = chunk_chain(LAST_CHUNK, pilot.epoch_count)
    epochs, stations, n = load_chunks(chain)
    geo = station_geometry(pilot, stations)
    fields = {"grad_op": G.field("grad_op"), "gpt3": G.field("gpt3")}
    targets = [build_targets(ep, stations, geo, fields) for ep in epochs]
    print(f"targets built, {time.perf_counter()-t0:.0f} s", flush=True)
    K = len(TARGETS)
    c, z, s = pilot.constraints(x)
    zc = np.zeros((len(z), K))
    zc[:, 0] = z
    arms = {}
    for arm in ("sd3", "elw13"):
        acc = GramAccumulator(n, K)
        for ep, T in zip(epochs, targets):
            acc.add_block(ep["retained"], ep["local"], T, ep["sigma"] if arm == "sd3" else elw13_sigma(ep))
        if arm == "sd3":
            with np.load(LAST_CHUNK/"acc.npz") as saved:
                saved_r = saved["R"]
            sign = np.sign(np.diag(acc.R))*np.sign(np.diag(saved_r))
            sign[sign == 0] = 1.
            r1 = float(np.max(np.abs(acc.R*sign[:, None]-saved_r)))/float(np.max(np.abs(saved_r)))
            del saved_r
        acc.add_constraints(c, zc, s)
        est, _, reduction = acc.solve()
        arms[arm] = dict(acc=acc, est=est, reduction=reduction)
        print(f"{arm} solved, {time.perf_counter()-t0:.0f} s", flush=True)
    with np.load(SAVED_SOLVE/"transfer.npz") as saved:
        saved_est = saved["estimate"]
    est = arms["sd3"]["est"]
    scale_n = float(np.max(np.abs(saved_est[:, SAVED_COL["nopcv"]])))
    r2 = dict(nopcv_rel=float(np.max(np.abs(est[:, 1]-saved_est[:, SAVED_COL["nopcv"]])))/scale_n,
              y_over_nopcv_scale=float(np.max(np.abs(est[:, 0]-saved_est[:, SAVED_COL["y"]])))/scale_n,
              y_reduction_rel=abs(float(arms["sd3"]["reduction"][0])/float(result["checks"]["K3_reduction_y"])-1))
    r3 = (sha(TRANSFER/"transfer_result.json") == TRANSFER_RESULT_SHA256 and sha(SAVED_SOLVE/"transfer.npz") == TRANSFER_NPZ_SHA256
          and all(result["checks"][k] for k in ("K2_pass", "K3_pass")) and result["calibration"]["pass"] and chain["K1_pass"])
    checks = dict(R1_aligned_rel=r1, R2=r2, R3_pass=bool(r3), K1_max_abs_m=chain["K1_max_abs_m"])
    checks["pass"] = bool(r1 <= 1e-10 and r2["nopcv_rel"] <= 1e-9 and r2["y_over_nopcv_scale"] <= 1e-9
                          and r2["y_reduction_rel"] <= 1e-6 and r3)
    print("checks:", json.dumps(checks), flush=True)
    report = dict(status="diagnostic_linear_prediction_not_accuracy_acceptance", protocol_sha256=protocol,
                  binding=lp.binding, gradient_bindings={k: G.binding(k) for k in ("grad_op", "gpt3")},
                  targets=list(TARGETS), checks=checks)
    arrays = {}
    if not checks["pass"]:
        report["predictions"] = "NOT ANALYSED: a reproduction check failed"
    else:
        from validation.oracle import frame as O2, metrics as O1
        assert sha(IGS_FINAL) == IGS_FINAL_SHA256
        reference = O1.read_sp3(IGS_FINAL)
        sd_frame = O2.Frame(O2.Finals(ROOT/"data/stage2/finals2000A.all"), subdaily=True)
        with np.load(SD3/"lin2-solve"/"solution.npz") as f:
            times5, sd3_states, sats = f["times_s"].copy(), f["states"].copy(), [str(v) for v in f["satellites"]]
        e13_validation = json.loads((E13/"validation.json").read_text())
        with np.load(E13/e13_validation["final"]/"solution.npz") as f:
            e13_states = f["states"].copy()
            assert [str(v) for v in f["satellites"]] == sats and np.array_equal(f["times_s"], times5)
        origin = int(pilot.context["origin_ns"])
        hours5 = ut_hours(pilot.context, times5)
        i15 = np.flatnonzero(np.isclose(np.round(hours5*4), hours5*4, rtol=0, atol=1e-9) & (hours5 < 24))
        ns, nt = len(sats), len(times5)
        pos, vel = np.zeros((ns, nt, 3)), np.zeros((ns, nt, 3))
        jac = []
        for si, sat in enumerate(sats):
            k0 = pilot.index[f"orbit:{sat}:0"]
            srp = [pilot.index[f"srp{('D0', 'Y0', 'B0', 'Bc1', 'Bs1')[cc]}:{sat}"] for cc in pilot.estimate]
            tr = products.trajectories[sat]
            row = []
            for ti, t in enumerate(times5):
                st = products.state(sat, t)
                pos[si, ti], vel[si, ti] = st[:3], st[3:]
                row.append((np.hstack([tr.partial(t)[:3], tr.force_partial(t)[:3, list(pilot.estimate)]*1e-7]),
                            np.r_[k0:k0+6, srp]))
            jac.append(row)
        axes = rac(pos, vel)
        base_sd3, keys = oracle_score(sd3_states[:, :, :3], sats, times5, origin, sd_frame, reference)
        base_e13, _ = oracle_score(e13_states[:, :, :3], sats, times5, origin, sd_frame, reference, keys)
        report["oracle_baselines"] = dict(SD3=base_sd3, E_elw13_3=base_e13)
        report["arms"] = {}
        for arm, a in arms.items():
            est = a["est"]
            dr = np.zeros((ns, nt, 3, K))
            for si in range(ns):
                for ti in range(nt):
                    J, idx = jac[si][ti]
                    dr[si, ti] = J@est[idx]
            acc = a["acc"]
            total, retained = np.diag(acc.total_gram), np.diag(acc.Z.T@acc.Z)
            base_states, base = (sd3_states, base_sd3) if arm == "sd3" else (e13_states, base_e13)
            out = {}
            for j, name in enumerate(TARGETS):
                if name not in FIELDS:
                    continue
                d = dr[:, :, :, j]
                scale = np.array([helmert_scale(pos[:, i], d[:, i])[0] for i in i15])
                predicted, _ = oracle_score(base_states[:, :, :3]+d, sats, times5, origin, sd_frame, reference, keys)
                out[name] = dict(
                    absorbed_by_clocks=float(acc.local_gram[j, j]/total[j]),
                    absorbed_by_retained=float(retained[j]/total[j]), left_in_residual=float(acc.lost_gram[j, j]/total[j]),
                    change_rms3d_cm=float(np.sqrt(np.mean(np.sum(d**2, axis=-1))))*100,
                    change_rac_rms_cm=[float(np.sqrt(np.mean(np.einsum("stj,stj->st", ax, d)**2)))*100 for ax in axes],
                    change_ure_cm=ure_cm(d, axes), change_scale=harm(hourly(scale)),
                    predicted_vs_igs=predicted,
                    predicted_ure_change_pct=100*(predicted["orbit_ure_m"]/base["orbit_ure_m"]-1),
                    predicted_3d_change_pct=100*(predicted["rms_3d_m"]/base["rms_3d_m"]-1))
                arrays[f"{arm}_dr_{name}"] = d
            report["arms"][arm] = dict(role="primary (calibrated)" if arm == "sd3" else "secondary (descriptive)",
                                       base="SD-3" if arm == "sd3" else "E-elw13-3 (operator at the SD-3 point)", fields=out)
            for name, v in out.items():
                print(arm, name, f"change URE {v['change_ure_cm']:.4f} cm, predicted vs IGS URE {v['predicted_ure_change_pct']:+.2f}% "
                      f"3D {v['predicted_3d_change_pct']:+.2f}%", flush=True)
        arrays.update(times5=times5, satellites=np.array(sats), pos=pos)
    report["seconds"] = time.perf_counter()-t0
    np.savez_compressed(folder/"gradients_linear.npz", **arrays)
    report["npz_sha256"] = sha(folder/"gradients_linear.npz")
    write_json(folder/"gradients_linear.json", report)
    write_json(folder/"step.json", dict(status="gradient_linear_done", checks_pass=checks["pass"],
                                        json_sha256=sha(folder/"gradients_linear.json")))


if __name__ == "__main__":
    main()
