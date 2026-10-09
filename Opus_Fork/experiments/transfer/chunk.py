"""Worker 2: one chunk of epochs of the transfer calculation (Jacobians + perturbation targets + streaming QR).

    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.experiments.transfer.chunk \
        --start A --stop B --tides TIDES_RUN [--previous PREVIOUS_CHUNK_RUN]

For every epoch in [A, B): `pilot.epoch_block(x, ei, products, jacobian=True)` exactly as the SD-3 fit's lin2 chunks
computed it, plus the perturbation targets of `common.TARGETS` (PROTOCOL.md table), folded into a `MultiAccumulator`
restored from the previous chunk. Outputs in the run folder:
- `acc.npz`   accumulator state (R, Z, …) for the next chunk / the solve;
- `rows.npz`  per-row geometry and targets (elevation, nadir, los·up, UT hour, δy columns, analytic checks);
- `blocks.npz` the whitening inputs (sparse retained Jacobian, local Jacobian, σ) so other targets can be re-accumulated
  later without recomputing Jacobians;
- `step.json` binding, checks and timing.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np

from Opus_Fork.experiments.transfer.common import (TARGETS, K, COL, MultiAccumulator, load_linearization_point,
                                                   run_dir, sha, shift_pco_z, ut_hours, write_json, zero_pcv)


def main():
    folder = run_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--stop", type=int, required=True)
    parser.add_argument("--tides", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    t0 = time.perf_counter()
    lp = load_linearization_point()
    pilot, x, products = lp.pilot, lp.x, lp.products
    setup_s = time.perf_counter()-t0
    from claude.tools.dated_observation import modeled_link
    from customkf.preprocess import ALPHA, BETA

    tides_meta = json.loads((args.tides/"step.json").read_text())
    assert tides_meta["status"] == "tides_ready" and sha(args.tides/"tides.npz") == tides_meta["tides_sha256"]
    assert tides_meta["fixture_sha256"] == lp.binding["fixture"]
    with np.load(args.tides/"tides.npz") as f:
        t_stations, t_times = [str(s) for s in f["stations"]], f["times_s"].copy()
        solid, otl, up = f["solid"].copy(), f["otl"].copy(), f["up"].copy()
    s_index = {s: i for i, s in enumerate(t_stations)}
    t_index = {float(t): i for i, t in enumerate(t_times)}

    binding = dict(lp.binding, tides=tides_meta["tides_sha256"])
    if args.previous is not None:
        meta = json.loads((args.previous/"step.json").read_text())
        assert meta["status"] == "transfer_chunk_complete" and meta["binding"] == binding and meta["stop"] == args.start
        assert sha(args.previous/"acc.npz") == meta["acc_sha256"]
        with np.load(args.previous/"acc.npz") as data:
            acc = MultiAccumulator.restore(data)
    else:
        assert args.start == 0
        acc = MultiAccumulator(pilot.n, K)

    c = pilot.context
    cal_nopcv = {s: zero_pcv(cal) for s, cal in c["sat_cal"].items()}
    cal_pcoz = {s: shift_pco_z(cal, 0.01) for s, cal in c["sat_cal"].items()}
    offsets = np.r_[0, np.cumsum([sum(2 if pilot.rows[i]["arc"] in pilot.arcset else 1 for i in pilot.by_epoch[e])
                                  for e in range(pilot.epoch_count)])]
    assert offsets[-1] == len(lp.residual)
    w12, w24 = 2*np.pi/12, 2*np.pi/24
    meta_rows, targets_all, checks = [], [], dict(max_abs_vs_fit_residual_m=0., max_abs_reevaluated_vs_block_m=0.,
                                                  max_abs_nopcv_exact_minus_analytic_m=0.,
                                                  max_abs_solid_exact_minus_linear_m=0., max_abs_otl_exact_minus_linear_m=0.)
    g_rows, g_cols, g_vals, g_shape, locals_, local_shapes, sigmas = [], [], [], [], [], [], []
    loop_start = time.perf_counter()
    for ei in range(args.start, args.stop):
        block, ys, ss = pilot.epoch_block(x, ei, products, jacobian=True)
        ys = np.asarray(ys)
        fit = lp.residual[offsets[ei]:offsets[ei+1]]
        difference = float(np.max(np.abs(ys-fit)))
        if not np.isfinite(difference):        # never let max() hide a NaN (addendum review AA03)
            raise ValueError(f"Non-finite misclosure difference at epoch {ei}")
        checks["max_abs_vs_fit_residual_m"] = max(checks["max_abs_vs_fit_residual_m"], difference)
        T = np.zeros((len(ys), K))
        T[:, COL["y"]] = ys
        k = 0
        for i in pilot.by_epoch[ei]:
            row = pilot.rows[i]
            sat, st = row["satellite"], row["station"]
            rc, sc, wet, amb = pilot.state_for(x, row)
            rx = c["rx_cal"][c["stations"][st]["header"]["antenna"]]

            def out(cal=c["sat_cal"][sat], r=row):
                return modeled_link(products, r, rx, cal, c["ephemeris"], rc, sc, wet, amb, pilot.windup[i])[0]
            o0 = out()
            g, _ = modeled_link(products, row, rx, c["sat_cal"][sat], c["ephemeris"], rc, sc, wet, amb, pilot.windup[i], details=True)
            los, elev = g["los_ecef"], float(g["elevation_rad"])
            rot = products.epoch.celestial_to_terrestrial(g["receive_s"])
            zaxis = rot@(-g["satellite_inertial"][:3]/np.linalg.norm(g["satellite_inertial"][:3]))
            nadir = float(np.degrees(np.arccos(np.clip(-los@zaxis, -1, 1))))
            si, ti = s_index[st], t_index[float(row["time_s"])]
            lu = float(los@up[si])
            hour = float(ut_hours(c, row["time_s"]))
            d_nopcv = o0-out(cal=cal_nopcv[sat])
            d_pcoz = o0-out(cal=cal_pcoz[sat])
            r_solid = dict(row, receiver_xyz=row["receiver_xyz"]+solid[si, ti])
            r_otl = dict(row, receiver_xyz=row["receiver_xyz"]+otl[si, ti])
            d_solid = o0-out(r=r_solid)
            d_otl = o0-out(r=r_otl)
            cal = c["sat_cal"][sat]
            analytic_pcv = ALPHA*cal.variation("G01", nadir)+BETA*cal.variation("G02", nadir)
            checks["max_abs_nopcv_exact_minus_analytic_m"] = max(checks["max_abs_nopcv_exact_minus_analytic_m"],
                                                                 float(np.max(np.abs(d_nopcv-analytic_pcv))))
            checks["max_abs_solid_exact_minus_linear_m"] = max(checks["max_abs_solid_exact_minus_linear_m"],
                                                               float(np.max(np.abs(d_solid-los@solid[si, ti]))))
            checks["max_abs_otl_exact_minus_linear_m"] = max(checks["max_abs_otl_exact_minus_linear_m"],
                                                             float(np.max(np.abs(d_otl-los@otl[si, ti]))))
            for kind in range(2 if row["arc"] in pilot.arcset else 1):
                checks["max_abs_reevaluated_vs_block_m"] = max(checks["max_abs_reevaluated_vs_block_m"],
                                                               float(abs(row["observation"][kind]-o0[kind]-ys[k])))
                T[k, COL["nopcv"]] = d_nopcv[kind]
                T[k, COL["pcoz_p1cm"]] = d_pcoz[kind]
                T[k, COL["solid_iers_minus_fixture"]] = d_solid[kind]
                T[k, COL["otl_nodal_minus_fixture"]] = d_otl[kind]
                T[k, COL["h_const_1mm"]] = 1e-3*lu
                T[k, COL["h12_cos_1mm"]] = 1e-3*lu*np.cos(w12*hour)
                T[k, COL["h12_sin_1mm"]] = 1e-3*lu*np.sin(w12*hour)
                T[k, COL["h24_cos_1mm"]] = 1e-3*lu*np.cos(w24*hour)
                T[k, COL["h24_sin_1mm"]] = 1e-3*lu*np.sin(w24*hour)
                T[k, COL["sat_nadir_lin_1mm"]] = -1e-3*(nadir/14.)
                T[k, COL["sat_nadir_quad_1mm"]] = -1e-3*(nadir/14.)**2
                T[k, COL["rx_elev_cos_1mm"]] = -1e-3*np.cos(elev)
                meta_rows.append((ei, si, pilot.sats.index(sat), kind, np.degrees(elev), np.degrees(float(g["azimuth_rad"])),
                                  nadir, lu, hour, float(analytic_pcv), float(los@solid[si, ti]), float(los@otl[si, ti])))
                k += 1
        assert k == len(ys)
        acc.add_block(block.retained, block.local, T, block.sigma)
        targets_all.append(T)
        nz = np.nonzero(block.retained)
        g_rows.append(nz[0].astype(np.int32)); g_cols.append(nz[1].astype(np.int32)); g_vals.append(block.retained[nz])
        g_shape.append(block.retained.shape[0])
        locals_.append(block.local.ravel()); local_shapes.append(block.local.shape); sigmas.append(block.sigma)
        print(f"epoch {ei} rows {len(ys)} elapsed {time.perf_counter()-t0:.1f}", flush=True)
    np.savez(folder/"acc.npz", **acc.state())
    m = np.array(meta_rows, dtype=float)
    np.savez_compressed(folder/"rows.npz", epoch=m[:, 0].astype(int), station_index=m[:, 1].astype(int),
                        satellite_index=m[:, 2].astype(int), kind=m[:, 3].astype(int), elevation_deg=m[:, 4],
                        azimuth_deg=m[:, 5], nadir_deg=m[:, 6], los_dot_up=m[:, 7], ut_hour=m[:, 8],
                        analytic_pcv_m=m[:, 9], linear_solid_m=m[:, 10], linear_otl_m=m[:, 11],
                        targets=np.vstack(targets_all), sigma=np.concatenate(sigmas), target_names=np.array(TARGETS),
                        stations=np.array(t_stations), satellites=np.array(pilot.sats))
    np.savez_compressed(folder/"blocks.npz", g_rows=np.concatenate(g_rows), g_cols=np.concatenate(g_cols),
                        g_vals=np.concatenate(g_vals), g_row_counts=np.array(g_shape), local=np.concatenate(locals_),
                        local_shapes=np.array(local_shapes), sigma=np.concatenate(sigmas), n=pilot.n,
                        epochs=np.arange(args.start, args.stop))
    record = dict(status="transfer_chunk_complete", binding=binding, start=args.start, stop=args.stop,
                  epoch_count=pilot.epoch_count, acc_sha256=sha(folder/"acc.npz"), rows_sha256=sha(folder/"rows.npz"),
                  blocks_sha256=sha(folder/"blocks.npz"), checks=checks,
                  binding_fields_not_checked=lp.binding_fields_not_checked, retained=pilot.n,
                  accumulated_rows=acc.rows, local_total=acc.local_total, setup_seconds=setup_s,
                  loop_seconds=time.perf_counter()-loop_start, seconds=time.perf_counter()-t0,
                  previous=str(args.previous) if args.previous else None)
    write_json(folder/"step.json", record)
    print(json.dumps(record, indent=1), flush=True)


if __name__ == "__main__":
    main()
