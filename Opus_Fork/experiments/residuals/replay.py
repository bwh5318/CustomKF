"""Replay a converged sub-daily-EOP fit at its final linearization point; post-fit residuals with geometry, binned.

    ... -- Opus_Fork.experiments.residuals.replay CAMPAIGN_DIR

Purpose (results/STATION_TIDES_SCREEN.md): the POD's remaining scale breathing repeats with the constellation geometry.
With per-epoch satellite clocks, orbit scale is observable only through nadir- and elevation-dependent terms, so a
systematic error of that shape should leave a signature in the post-fit residuals.

What it does, read-only:
- Rebuilds the campaign's pilot exactly as its workers did: `sdeop.install()` with the campaign's variant, and the same
  fixture, config and state.
- Loads x from the final solve and the final linearization's trajectory caches. The caches record the pre-26-Sep
  hash of `subdaily_eop.py`, whose hook switch was verified bit-identical, so the fork's binding check would refuse them.
  Instead this checks that every other binding field matches, then loads them with the unbound
  `claude.roadmap.traj_cache.cached_products`.
- Evaluates every epoch's misclosures at x (`epoch_block`, jacobian=False). Clock values live in x, and at convergence
  the local increments are ~0. That is verified on three epochs by solving the per-epoch clock block (jacobian=True)
  and reporting the change.
- Records elevation, azimuth and satellite nadir angle for every residual, and bins the phase (kind 1) and code (kind 0)
  residuals by nadir, elevation, block and station.
Outputs `replay.npz` and `replay_summary.json` in the run folder.
"""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np

from Opus_Fork.paths import ROOT


def binned(values, weights, key, edges):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (key >= lo) & (key < hi)
        if m.sum() < 30:
            out.append(dict(lo=float(lo), hi=float(hi), n=int(m.sum())))
            continue
        w = weights[m]
        mean = float(np.sum(w*values[m])/np.sum(w))
        out.append(dict(lo=float(lo), hi=float(hi), n=int(m.sum()), mean_mm=mean*1000,
                        rms_mm=float(np.sqrt(np.mean(values[m]**2)))*1000,
                        sem_mm=float(np.std(values[m])/np.sqrt(m.sum()))*1000))
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--check-epochs", default="10,70,130")
    args = parser.parse_args()
    camp = (ROOT/args.campaign).resolve() if not args.campaign.is_absolute() else args.campaign
    v = json.loads((camp/"validation.json").read_text())
    assert v["status"].startswith("long_fit_complete")
    final = v["final"]
    lin = final.split("-")[0]
    os.environ["OPUSFORK_SD_VARIANT"] = v["force_model"]["variant"]

    from Opus_Fork import sdeop
    iteration = sdeop.install()
    from claude.roadmap.traj_cache import cached_products
    from customkf.measurement import geometry
    from customkf.prepare_stage2 import sha

    fixture, config = ROOT/v["fixture"], ROOT/v["config"]
    state = camp/v["state"]["path"]
    assert sha(state) == v["state"]["sha256"]
    pilot, _ = iteration.build(SimpleNamespace(fixture=fixture, config=config, state=state))
    saved = np.load(camp/final/"solution.npz")
    np.testing.assert_array_equal(saved["names"], pilot.names)
    x = saved["x"].copy()
    files = sorted(str(p) for p in camp.glob(f"{lin}-traj-*/trajectories.npz"))
    expected = sdeop.binding()
    for f in files:
        got = json.loads((Path(f).parent/"trajectories.json").read_text())["force_model"]
        diff = {k for k in set(got) | set(expected) if got.get(k) != expected.get(k)}
        assert diff <= {"subdaily_eop_sha256", "sdeop_sha256"}, diff
    products = cached_products(pilot, x, files)

    rows_out = []
    ys_all, ss_all = [], []
    for ei in range(pilot.epoch_count):
        _, ys, ss = pilot.epoch_block(x, ei, products, jacobian=False)
        ys_all += ys
        ss_all += ss
        for i in pilot.by_epoch[ei]:
            row = pilot.rows[i]
            rc, sc, wet, amb = pilot.state_for(x, row)
            g = geometry(products, row["satellite"], row["time_s"], row["receiver_xyz"], rc)
            rot = products.epoch.celestial_to_terrestrial(g["receive_s"])
            z = rot@(-g["satellite_inertial"][:3]/np.linalg.norm(g["satellite_inertial"][:3]))
            nadir = float(np.degrees(np.arccos(np.clip(-g["los_ecef"]@z, -1, 1))))
            for kind in range(2 if row["arc"] in pilot.arcset else 1):
                rows_out.append((ei, row["station"], row["satellite"], kind, np.degrees(g["elevation_rad"]),
                                 np.degrees(g["azimuth_rad"]), nadir, row["time_s"]/3600.))
        if ei % 24 == 0:
            print(f"epoch {ei}: {len(ys_all)} residuals", flush=True)
    res, sig = np.array(ys_all), np.array(ss_all)
    assert len(res) == len(rows_out)
    # The fit's own record of residuals at this point, for a consistency check.
    fit_res = saved["residual_m"]
    same = len(fit_res) == len(res) and np.allclose(fit_res, res, atol=1e-6)

    # Local (clock) re-solve on a few epochs: at convergence it should change nothing material.
    local_check = {}
    for ei in [int(e) for e in args.check_epochs.split(",")]:
        block, ys, ss = pilot.epoch_block(x, ei, products, jacobian=True)
        w = 1/np.asarray(ss)
        L = block.local*w[:, None]
        sol, *_ = np.linalg.lstsq(L, np.asarray(ys)*w, rcond=None)
        post = np.asarray(ys)-block.local@sol
        local_check[ei] = dict(rms_before_mm=float(np.sqrt(np.mean(np.square(ys))))*1000,
                               rms_after_local_solve_mm=float(np.sqrt(np.mean(post**2)))*1000,
                               max_local_increment_m=float(np.max(np.abs(sol))))
    print("local re-solve check:", local_check, flush=True)

    meta = np.array(rows_out, dtype=object)
    kind = meta[:, 3].astype(int)
    elev, azim, nadir, hour = (meta[:, k].astype(float) for k in (4, 5, 6, 7))
    stations, sats = meta[:, 1].astype(str), meta[:, 2].astype(str)
    from Opus_Fork import satmeta
    day = json.loads(fixture.read_text())["context"]["day"]
    blocks = {s: m.block for s, m in satmeta.load(day).items()}
    block = np.array([blocks.get(s, "?") for s in sats])
    np.savez_compressed(Path(os.environ["CUSTOMKF_RUN_DIR"])/"replay.npz", residual_m=res, sigma_m=sig, kind=kind,
                        elevation_deg=elev, azimuth_deg=azim, nadir_deg=nadir, hour=hour, station=stations,
                        satellite=sats, block=block, epoch=meta[:, 0].astype(int))
    summary = dict(campaign=str(camp.relative_to(ROOT)), final=final, day=day, residuals=len(res),
                   matches_fit_record=bool(same), local_check=local_check, kinds={})
    for k, name in ((1, "phase"), (0, "code")):
        m = kind == k
        wts = 1/sig[m]**2
        entry = dict(n=int(m.sum()), rms_mm=float(np.sqrt(np.mean(res[m]**2)))*1000,
                     by_nadir=binned(res[m], wts, nadir[m], np.arange(0, 15, 1.)),
                     by_elevation=binned(res[m], wts, elev[m], np.array([10, 15, 20, 25, 30, 40, 50, 60, 70, 90.])),
                     by_block_nadir={b: binned(res[m][block[m] == b], wts[block[m] == b], nadir[m][block[m] == b],
                                               np.array([0, 3, 6, 9, 12, 15.])) for b in sorted(set(block[m]))},
                     by_station_elevation={s: binned(res[m][stations[m] == s], wts[stations[m] == s], elev[m][stations[m] == s],
                                                     np.array([10, 20, 30, 50, 90.])) for s in sorted(set(stations[m]))})
        summary["kinds"][name] = entry
        print(f"{name}: n={entry['n']} rms {entry['rms_mm']:.1f} mm", flush=True)
        print("  by nadir (deg: mean mm):", " ".join(f"{b['lo']:.0f}:{b.get('mean_mm', float('nan')):+.2f}" for b in entry["by_nadir"]), flush=True)
        print("  by elevation:", " ".join(f"{b['lo']:.0f}:{b.get('mean_mm', float('nan')):+.2f}" for b in entry["by_elevation"]), flush=True)
        for b, bins in entry["by_block_nadir"].items():
            print(f"  {b:6s} nadir:", " ".join(f"{x['lo']:.0f}:{x.get('mean_mm', float('nan')):+.2f}" for x in bins), flush=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"replay_summary.json").write_text(json.dumps(summary, indent=1)+"\n")


if __name__ == "__main__":
    main()
