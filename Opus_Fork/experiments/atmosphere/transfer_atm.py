"""Atmosphere transfer worker (protocol: `PROTOCOL.md` in this folder, pinned by hash below).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --timeout 1800 -- \
        Opus_Fork.experiments.atmosphere.transfer_atm

Re-accumulates the saved whitening inputs of the validated SD-3 Aug 3 transfer (no Jacobian is recomputed) with new
right-hand sides for pressure, pressure tides, mapping and gradients; checks R1-R3; solves the primary (SD-3 weights)
and secondary (elw13 weights) arms; maps δx to orbits; writes `atmosphere.json` and `atmosphere.npz` in the run folder.
"""
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from Opus_Fork.experiments.transfer.common import (COL as SAVED_COL, SD3, MultiAccumulator, chunk_chain, harm, helmert_scale,
                                                   hourly, load_linearization_point, run_dir, sha, ut_hours, write_json)
from Opus_Fork.paths import ROOT
from customkf.measurement import geodetic
from customkf.station_models import troposphere

HERE = Path(__file__).resolve().parent
PROTOCOL_SHA256 = "2158e9a1969d7a532828c312a4ab8eab2cfd89b652378d84a134960b0cf3badc"
TRANSFER = ROOT/"Opus_Fork/experiments/transfer"
LAST_CHUNK = ROOT/"runs/20260928T222827Z-52e813a0"
SAVED_SOLVE = ROOT/"runs/20260929T014726Z-8e470a08"
TRANSFER_RESULT_SHA256 = "3ed123852ac3db47153fc653e946a427a71c7fd1780c7326d0adce498ec2e27e"
TRANSFER_NPZ_SHA256 = "b32c727821477138fae8e02d242eca750cea4f05de4335420e88a137a7383b8c"
DAY_OF_YEAR = 215
URE_REFERENCE_CM = 3.165
OBSERVED_AMP12, OBSERVED_PEAK12 = 0.311, 4.5
VARIANCE_FACTOR = 0.23707813376800185
SIGMA_PRESSURE_UNITS = 1.0           # 10 hPa = one unit of a p_<STA>_10hPa column
SIGMA_GRADIENT_MM = 0.5
S2_AMPLITUDE_HPA, S2_MAX_LST_H = 1.16, 10.0
PHASE_POWER, SIGMA0 = 1.3, (0.9, 0.009)
NETWORK = ("y", "nopcv", "p_net_10hPa", "s2_cos_1hPa", "s2_sin_1hPa", "s1_cos_1hPa", "s1_sin_1hPa",
           "gN_net_1mm", "gE_net_1mm", "map_net_1mm10")
W = 2*np.pi/24


# Appended amendments, each pinned before its effect was known (the body above stays pinned unchanged).
AMENDMENTS_SHA256 = {"A1": "8d517db692f2c8dea8ef1af03910654560c07947273e128d3267b203a651ff5d", "A2": "e5322ba23755c2369827997816e63eb89905817260e5e424ca75e88587cdc427"}


def check_protocol():
    """The pinned body (everything before the first "## Amendment") and each appended amendment, separately."""
    text = (HERE/"PROTOCOL.md").read_bytes()
    parts = text.split(b"\n## Amendment ")
    got = hashlib.sha256(parts[0].rstrip(b"\n")+b"\n").hexdigest()
    if got != PROTOCOL_SHA256:
        raise RuntimeError(f"PROTOCOL.md body changed after it was pinned: {got}")
    names = [part.split(b" ", 1)[0].decode() for part in parts[1:]]
    if names != list(AMENDMENTS_SHA256):
        raise RuntimeError(f"PROTOCOL.md amendments {names} differ from the pinned set {list(AMENDMENTS_SHA256)}")
    for name, part in zip(names, parts[1:]):
        if hashlib.sha256(b"## Amendment "+part).hexdigest() != AMENDMENTS_SHA256[name]:
            raise RuntimeError(f"PROTOCOL.md amendment {name} changed after it was pinned")
    return got


class GramAccumulator(MultiAccumulator):
    """MultiAccumulator that also keeps K x K Gram matrices: total, clock-absorbed (local) and residual (lost)."""

    def __init__(self, n, k):
        super().__init__(n, k)
        self.total_gram = np.zeros((k, k))
        self.local_gram = np.zeros((k, k))
        self.lost_gram = np.zeros((k, k))

    def _update(self, a, t):
        if not len(t):
            return
        m = np.vstack([self.R, a])
        rhs = np.vstack([self.Z, t])
        from scipy.linalg import qr_multiply
        qt, r = qr_multiply(m, rhs.T, mode="right")
        self.lost_gram += rhs.T@rhs-qt@qt.T
        self.lost += np.sum(rhs*rhs, axis=0)-np.sum(qt*qt, axis=1)
        self.R, self.Z = r, np.ascontiguousarray(qt.T)
        self.largest_update_rows = max(self.largest_update_rows, len(rhs))

    def add_block(self, retained, local, targets, sigma):
        from customkf.network_square_root import _factor
        y = targets/sigma[:, None]
        l = local/sigma[:, None]
        self.total_gram += y.T@y
        q, _ = _factor(l, full=True)
        qy = q[:, :l.shape[1]].T@y
        self.local_gram += qy.T@qy
        super().add_block(retained, local, targets, sigma)

    def add_constraints(self, c, z, s):
        zz = z/s[:, None]
        self.total_gram += zz.T@zz
        super().add_constraints(c, z, s)


def load_chunks(chain):
    """Per-epoch (retained dense, local, sigma, rows-meta) from the saved chunk files, hash-checked."""
    epochs = []
    for link in chain["chunks"]:
        folder = Path(link["folder"])
        step = json.loads((folder/"step.json").read_text())
        assert sha(folder/"blocks.npz") == step["blocks_sha256"] and sha(folder/"rows.npz") == step["rows_sha256"]
        with np.load(folder/"blocks.npz") as b, np.load(folder/"rows.npz") as r:
            g_rows, g_cols, g_vals = b["g_rows"], b["g_cols"], b["g_vals"]
            counts, local, shapes, sigma, n = b["g_row_counts"], b["local"], b["local_shapes"], b["sigma"], int(b["n"])
            meta = {k: r[k].copy() for k in ("epoch", "station_index", "satellite_index", "kind", "elevation_deg",
                                            "azimuth_deg", "ut_hour", "targets", "sigma")}
            stations = [str(s) for s in r["stations"]]
            assert [str(t) for t in r["target_names"]] == list(SAVED_COL)
        # Split the concatenated nonzeros by epoch: row indices restart at 0 for every epoch (row-major nonzero order).
        starts = np.r_[0, np.flatnonzero(np.diff(g_rows) < 0)+1, len(g_rows)]
        assert len(starts)-1 == len(counts) and np.all(g_rows[starts[:-1]] == 0)
        np.testing.assert_array_equal(sigma, meta["sigma"])
        row0 = lsplit = 0
        for e, count in enumerate(counts):
            lo, hi = starts[e], starts[e+1]
            assert g_rows[lo:hi].max() == count-1
            dense = np.zeros((count, n))
            dense[g_rows[lo:hi], g_cols[lo:hi]] = g_vals[lo:hi]
            rows_l, cols_l = shapes[e]
            assert rows_l == count
            loc = local[lsplit:lsplit+rows_l*cols_l].reshape(rows_l, cols_l)
            lsplit += rows_l*cols_l
            sl = slice(row0, row0+count)
            row0 += count
            epochs.append(dict(retained=dense, local=loc, sigma=sigma[sl], meta={k: v[sl] for k, v in meta.items()}))
        assert row0 == len(sigma) and lsplit == len(local)
    return epochs, stations, n


def station_geometry(pilot, stations):
    geo = {}
    for name in stations:
        xyz = np.asarray(pilot.context["stations"][name]["fixed_xyz"], dtype=float)
        lat, lon, h = geodetic(xyz)
        geo[name] = dict(xyz=xyz, lat=float(lat), lon=float(lon), h=float(h),
                         pressure_hpa=float(1013.25*(1-2.2557e-5*h)**5.2568))
    return geo


def target_names(stations):
    return (list(NETWORK)+[f"p_{s}_10hPa" for s in stations]+[f"gN_{s}_1mm" for s in stations]
            +[f"gE_{s}_1mm" for s in stations])


def build_targets(ep, stations, geo, col):
    """δy = −δm for every column (PROTOCOL.md table)."""
    m = ep["meta"]
    T = np.zeros((len(ep["sigma"]), len(col)))
    T[:, col["y"]] = m["targets"][:, SAVED_COL["y"]]
    T[:, col["nopcv"]] = m["targets"][:, SAVED_COL["nopcv"]]
    for k in range(len(T)):
        st = stations[int(m["station_index"][k])]
        g = geo[st]
        e, az = math.radians(float(m["elevation_deg"][k])), math.radians(float(m["azimuth_deg"][k]))
        hour = float(m["ut_hour"][k])
        doy = DAY_OF_YEAR+hour/24
        hyd, _ = troposphere(g["xyz"], e, doy)
        zhd, _ = troposphere(g["xyz"], math.pi/2, doy)
        hyd10, _ = troposphere(g["xyz"], math.radians(10.), doy)
        lst = hour+math.degrees(g["lon"])/15
        tide = math.cos(g["lat"])**3
        mg = 1/(math.sin(e)*math.tan(e)+0.0031)
        per_hpa = hyd/g["pressure_hpa"]
        dm = {"p_net_10hPa": per_hpa*10,
              "s2_cos_1hPa": per_hpa*tide*math.cos(2*W*lst), "s2_sin_1hPa": per_hpa*tide*math.sin(2*W*lst),
              "s1_cos_1hPa": per_hpa*tide*math.cos(W*lst), "s1_sin_1hPa": per_hpa*tide*math.sin(W*lst),
              "gN_net_1mm": 1e-3*mg*math.cos(az), "gE_net_1mm": 1e-3*mg*math.sin(az),
              "map_net_1mm10": 1e-3*(hyd/zhd-1)/(hyd10/zhd-1),
              f"p_{st}_10hPa": per_hpa*10, f"gN_{st}_1mm": 1e-3*mg*math.cos(az), f"gE_{st}_1mm": 1e-3*mg*math.sin(az)}
        for name, value in dm.items():
            T[k, col[name]] = -value
    return T


def elw13_sigma(ep):
    """`Opus_Fork/elev.py` elw13 on the saved σ: phase σ × sin(e)^−0.3, sin(e) = 0.009/σ_phase; code unchanged."""
    s, kind = ep["sigma"].copy(), ep["meta"]["kind"]
    for k in np.flatnonzero(kind == 1):
        sin_e = SIGMA0[1]/s[k]
        if not (k > 0 and kind[k-1] == 0 and np.isclose(s[k-1], SIGMA0[0]/sin_e, rtol=1e-9, atol=0)):
            raise ValueError("Saved σ does not follow (0.9, 0.009)/sin(e)")
        s[k] = SIGMA0[1]/sin_e**PHASE_POWER
    return s


def rac(pos, vel):
    radial = pos/np.linalg.norm(pos, axis=-1, keepdims=True)
    normal = np.cross(pos, vel)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return radial, np.cross(normal, radial), normal


def ure_cm(dr, axes):
    radial, along, cross = (np.einsum("stj,stj...->st...", a, dr) for a in axes)
    return float(np.sqrt(np.mean(0.98**2*radial**2+(along**2+cross**2)/49)))*100


def main():
    folder = run_dir()
    t0 = time.perf_counter()
    protocol = check_protocol()
    lp = load_linearization_point()
    pilot, x, products = lp.pilot, lp.x, lp.products
    # R3 and K1 on the saved operator.
    result = json.loads((TRANSFER/"transfer_result.json").read_text())
    k1 = json.loads((TRANSFER/"k1_validation.json").read_text())
    chain = chunk_chain(LAST_CHUNK, pilot.epoch_count)
    r3 = dict(transfer_result_sha256=sha(TRANSFER/"transfer_result.json"), saved_npz_sha256=sha(SAVED_SOLVE/"transfer.npz"),
              K2_pass=bool(result["checks"]["K2_pass"]), K3_pass=bool(result["checks"]["K3_pass"]),
              calibration_pass=bool(result["calibration"]["pass"]), K1_record_pass=bool(k1["K1_pass"]),
              K1_recheck_pass=bool(chain["K1_pass"]),
              same_last_chunk=Path(result["last_chunk"]).name == LAST_CHUNK.name == Path(k1["last_chunk"]).name)
    r3["pass"] = bool(r3["transfer_result_sha256"] == TRANSFER_RESULT_SHA256 and r3["saved_npz_sha256"] == TRANSFER_NPZ_SHA256
                      and result["transfer_npz_sha256"] == TRANSFER_NPZ_SHA256 and all(
                          r3[k] for k in ("K2_pass", "K3_pass", "calibration_pass", "K1_record_pass", "K1_recheck_pass",
                                          "same_last_chunk")))
    epochs, stations, n = load_chunks(chain)
    assert n == pilot.n and len(epochs) == pilot.epoch_count
    geo = station_geometry(pilot, stations)
    names = target_names(stations)
    col = {name: j for j, name in enumerate(names)}
    K = len(names)
    print(f"loaded {len(epochs)} epochs, {K} columns, {time.perf_counter()-t0:.0f} s", flush=True)
    targets = [build_targets(ep, stations, geo, col) for ep in epochs]
    setup_s = time.perf_counter()-t0
    print(f"targets built, {setup_s:.0f} s", flush=True)
    c, z, s = pilot.constraints(x)
    zc = np.zeros((len(z), K))
    zc[:, col["y"]] = z
    arms = {}
    for arm in ("sd3", "elw13"):
        acc = GramAccumulator(n, K)
        for ei, (ep, T) in enumerate(zip(epochs, targets)):
            acc.add_block(ep["retained"], ep["local"], T, ep["sigma"] if arm == "sd3" else elw13_sigma(ep))
            if ei % 24 == 23:
                print(f"{arm}: epoch {ei+1}/{len(epochs)}, {time.perf_counter()-t0:.0f} s", flush=True)
        if arm == "sd3":
            # Amendment A2: QR rows are unique only up to sign; compare after aligning each row's sign to the saved R.
            with np.load(LAST_CHUNK/"acc.npz") as saved:
                saved_r = saved["R"]
            sign = np.sign(np.diag(acc.R))*np.sign(np.diag(saved_r))
            sign[sign == 0] = 1.
            scale = float(np.max(np.abs(saved_r)))
            r1 = dict(aligned_rel=float(np.max(np.abs(acc.R*sign[:, None]-saved_r)))/scale,
                      raw_rel=float(np.max(np.abs(acc.R-saved_r)))/scale, rows_sign_flipped=int(np.sum(sign < 0)),
                      abs_rel=float(np.max(np.abs(np.abs(acc.R)-np.abs(saved_r))))/scale)
            del saved_r
        acc.add_constraints(c, zc, s)
        est, mapping, reduction = acc.solve()
        arms[arm] = dict(acc=acc, est=est, reduction=reduction)
    with np.load(SAVED_SOLVE/"transfer.npz") as saved:
        saved_est = saved["estimate"]
    est = arms["sd3"]["est"]
    # Amendment A2: nopcv at 1e-9 relative; the converged step y on the scale of a real response, and its reduction.
    nopcv_scale = float(np.max(np.abs(saved_est[:, SAVED_COL["nopcv"]])))
    dy = float(np.max(np.abs(est[:, col["y"]]-saved_est[:, SAVED_COL["y"]])))
    saved_reduction = float(result["checks"]["K3_reduction_y"])
    r2 = dict(nopcv_rel=float(np.max(np.abs(est[:, col["nopcv"]]-saved_est[:, SAVED_COL["nopcv"]])))/nopcv_scale,
              y_raw_rel=dy/float(np.max(np.abs(saved_est[:, SAVED_COL["y"]]))), y_over_nopcv_scale=dy/nopcv_scale,
              y_reduction=float(arms["sd3"]["reduction"][col["y"]]), saved_y_reduction=saved_reduction,
              y_reduction_rel=abs(float(arms["sd3"]["reduction"][col["y"]])/saved_reduction-1))
    checks = dict(R1=r1, R1_pass=bool(r1["aligned_rel"] <= 1e-10), R2=r2,
                  R2_pass=bool(r2["nopcv_rel"] <= 1e-9 and r2["y_over_nopcv_scale"] <= 1e-9 and r2["y_reduction_rel"] <= 1e-6),
                  R3=r3, R3_pass=r3["pass"], K1_max_abs_m=chain["K1_max_abs_m"])
    checks["pass"] = bool(checks["R1_pass"] and checks["R2_pass"] and checks["R3_pass"])
    print("checks:", json.dumps(checks, indent=1), flush=True)

    report = dict(status="diagnostic_linear_transfer_not_accuracy_acceptance", protocol_sha256=protocol,
                  binding=lp.binding, binding_fields_not_checked=lp.binding_fields_not_checked, last_chunk=str(LAST_CHUNK),
                  targets=names, stations=stations, station_geometry={k: {kk: (vv if kk != "xyz" else vv.tolist())
                                                                          for kk, vv in v.items()} for k, v in geo.items()},
                  checks=checks, setup_seconds=setup_s)
    arrays = dict(targets=np.array(names))
    if not checks["pass"]:
        report["candidates"] = "NOT ANALYSED: a reproduction check failed (PROTOCOL.md R1-R3)"
    else:
        with np.load(SD3/"lin2-solve"/"solution.npz") as f:
            times5 = f["times_s"].copy()
        hours5 = ut_hours(pilot.context, times5)
        i15 = np.flatnonzero(np.isclose(np.round(hours5*4), hours5*4, rtol=0, atol=1e-9) & (hours5 < 24))
        assert len(i15) == 96
        sats = pilot.sats
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
        wet = [pilot.index[p] for p in pilot.names[:pilot.n] if p.startswith("wet:")]
        amb = [pilot.index[p] for p in pilot.names[:pilot.n] if p.startswith("amb:")]
        report["arms"] = {}
        for arm, a in arms.items():
            est = a["est"]
            dr = np.zeros((ns, nt, 3, K))
            for si in range(ns):
                for ti in range(nt):
                    J, idx = jac[si][ti]
                    dr[si, ti] = J@est[idx]
            scale = np.array([helmert_scale(pos[:, j], dr[:, j]) for j in i15])     # (96, K)
            acc = a["acc"]
            retained_gram = acc.Z.T@acc.Z
            total = np.diag(acc.total_gram)
            columns = {}
            for name, j in col.items():
                if name == "y":
                    continue
                d = dr[:, :, :, j]
                h = harm(hourly(scale[:, j]))
                columns[name] = dict(
                    absorbed_by_clocks=float(acc.local_gram[j, j]/total[j]),
                    absorbed_by_retained=float(retained_gram[j, j]/total[j]),
                    left_in_residual=float(acc.lost_gram[j, j]/total[j]),
                    closure=float((acc.local_gram[j, j]+retained_gram[j, j]+acc.lost_gram[j, j])/total[j]-1),
                    rms3d_cm=float(np.sqrt(np.mean(np.sum(d**2, axis=-1))))*100,
                    rac_rms_cm=[float(np.sqrt(np.mean(np.einsum("stj,stj->st", ax, d)**2)))*100 for ax in axes],
                    ure_cm=ure_cm(d, axes), scale=h,
                    wet_rms_mm=float(np.sqrt(np.mean(est[wet, j]**2)))*1000,
                    ambiguity_rms_mm=float(np.sqrt(np.mean(est[amb, j]**2)))*1000,
                    formal_sigma_unit=float(1/np.sqrt(acc.lost_gram[j, j])) if acc.lost_gram[j, j] > 0 else None)
                if name in NETWORK:
                    columns[name]["per_satellite_rms3d_cm"] = {sat: float(np.sqrt(np.mean(np.sum(d[si]**2, axis=-1))))*100
                                                               for si, sat in enumerate(sats)}
            # Identifiability: all station gradients estimated jointly (50 x 50 residual Gram), and per station (2 x 2).
            g_idx = [col[f"g{c_}_{st}_1mm"] for st in stations for c_ in "NE"]
            cov_all = np.linalg.inv(acc.lost_gram[np.ix_(g_idx, g_idx)])
            ident = {}
            for i_s, st in enumerate(stations):
                pair = [col[f"gN_{st}_1mm"], col[f"gE_{st}_1mm"]]
                trio = pair+[col[f"p_{st}_10hPa"]]
                L = acc.lost_gram[np.ix_(trio, trio)]
                corr = L/np.sqrt(np.outer(np.diag(L), np.diag(L)))
                cov2 = np.linalg.inv(L[:2, :2])
                joint = np.sqrt(np.diag(cov_all)[2*i_s:2*i_s+2])
                ident[st] = dict(single_station_sigma_mm=np.sqrt(np.diag(cov2)).tolist(),
                                 all_stations_joint_sigma_mm=joint.tolist(),
                                 all_stations_joint_sigma_mm_aposteriori=(joint*math.sqrt(VARIANCE_FACTOR)).tolist(),
                                 residual_corr_gN_gE=float(corr[0, 1]), residual_corr_p_gN=float(corr[2, 0]),
                                 residual_corr_p_gE=float(corr[2, 1]),
                                 pressure_10hPa_formal_sigma_units=float(1/np.sqrt(L[2, 2])),
                                 ure_cm_p_10hPa=columns[f"p_{st}_10hPa"]["ure_cm"],
                                 ure_cm_gN_1mm=columns[f"gN_{st}_1mm"]["ure_cm"], ure_cm_gE_1mm=columns[f"gE_{st}_1mm"]["ure_cm"])
                worst = max(ident[st]["all_stations_joint_sigma_mm_aposteriori"])
                ident[st]["category"] = ("identifiable" if worst <= 0.1 else "weak" if worst <= 0.3 else "not identifiable")
            station_cols = [j for name, j in col.items() if name not in NETWORK]
            Ls = acc.lost_gram[np.ix_(station_cols, station_cols)]
            Cs = Ls/np.sqrt(np.outer(np.diag(Ls), np.diag(Ls)))
            np.fill_diagonal(Cs, 0)
            largest = np.unravel_index(np.argmax(np.abs(Cs)), Cs.shape)
            # Illustrative magnitudes (PROTOCOL.md), applied linearly.
            p_ure = SIGMA_PRESSURE_UNITS*math.sqrt(sum(columns[f"p_{st}_10hPa"]["ure_cm"]**2 for st in stations))
            g_ure = SIGMA_GRADIENT_MM*math.sqrt(sum(columns[f"g{c_}_{st}_1mm"]["ure_cm"]**2 for st in stations for c_ in "NE"))
            a2, b2 = S2_AMPLITUDE_HPA*math.cos(2*W*S2_MAX_LST_H), S2_AMPLITUDE_HPA*math.sin(2*W*S2_MAX_LST_H)
            s2_dr = a2*dr[:, :, :, col["s2_cos_1hPa"]]+b2*dr[:, :, :, col["s2_sin_1hPa"]]
            s2_scale = a2*scale[:, col["s2_cos_1hPa"]]+b2*scale[:, col["s2_sin_1hPa"]]
            implied = harm(-hourly(s2_scale))
            observed = np.array(json.loads((ROOT/"Opus_Fork/results/sensitivity_analysis.json").read_text())
                                ["arms"]["nopcv"]["SD3"]["hourly_scale_ppb"])
            o12 = np.array(harm(observed)["c12"])
            dphase = abs(((implied["peak12_ut"]-OBSERVED_PEAK12)+6) % 12-6)
            ratio = implied["amp12"]/OBSERVED_AMP12
            s2_category = ("negligible" if ratio < 0.10 else "capable of the magnitude" if ratio >= 0.5 and dphase <= 1.5
                           else "minor contributor")

            def ure_category(u):
                r = u/URE_REFERENCE_CM
                return dict(ure_cm=u, ratio=r, gain_if_removed=1-math.sqrt(max(0., 1-r*r)),
                            category="material" if r >= 0.20 else "minor" if r >= 0.10 else "negligible")
            illustrative = dict(
                station_pressure_sigma_10hPa=ure_category(p_ure),
                station_gradients_sigma_0p5mm=ure_category(g_ure),
                common_pressure_10hPa=ure_category(columns["p_net_10hPa"]["ure_cm"]),
                mapping_1mm_at_10deg=ure_category(columns["map_net_1mm10"]["ure_cm"]),
                s2_climatology=dict(ure_category(ure_cm(s2_dr, axes)), implied_ours_minus_reference_scale=implied,
                                    amp12_ratio_to_observed=ratio, projection_on_observed_12h=float(
                                        np.dot(implied["c12"], o12)/np.dot(o12, o12)),
                                    corr_hourly_with_observed=float(np.corrcoef(-hourly(s2_scale), observed)[0, 1]),
                                    breathing_category=s2_category))
            report["arms"][arm] = dict(
                role="primary (calibrated operator)" if arm == "sd3" else "secondary (descriptive, uncalibrated)",
                columns=columns, identifiability=ident,
                largest_station_column_residual_corr=dict(a=[n_ for n_ in col if col[n_] == station_cols[largest[0]]][0],
                                                         b=[n_ for n_ in col if col[n_] == station_cols[largest[1]]][0],
                                                         r=float(Cs[largest])),
                illustrative=illustrative, accumulated_rows=acc.rows, local_total=acc.local_total)
            arrays[f"{arm}_estimate"] = est
            arrays[f"{arm}_scale_per_epoch_ppb"] = scale
            arrays[f"{arm}_lost_gram"] = acc.lost_gram
            arrays[f"{arm}_total_gram"] = acc.total_gram
            arrays[f"{arm}_local_gram"] = acc.local_gram
            arrays[f"{arm}_retained_gram"] = retained_gram
            print(arm, json.dumps({k: {kk: vv for kk, vv in v.items() if not isinstance(vv, dict)}
                                   for k, v in illustrative.items()}, indent=1), flush=True)
    report["seconds"] = time.perf_counter()-t0
    np.savez_compressed(folder/"atmosphere.npz", **arrays)
    report["atmosphere_npz_sha256"] = sha(folder/"atmosphere.npz")
    write_json(folder/"atmosphere.json", report)
    write_json(folder/"step.json", dict(status="atmosphere_transfer_done", checks_pass=checks["pass"],
                                        atmosphere_json_sha256=sha(folder/"atmosphere.json"), seconds=report["seconds"]))


if __name__ == "__main__":
    main()
