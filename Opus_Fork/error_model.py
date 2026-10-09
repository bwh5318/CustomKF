"""Is the late-window misfit station-side, satellite-side, or elevation-side?

    python -m Opus_Fork.guard --profile fork8 --timeout 900 --label error-model -- Opus_Fork.error_model

Two facts from the preceding diagnostics need reconciling. G21's phase whitened RMS doubles
after 16:00 (0.510 -> 1.042) and is the worst of 27 satellites, yet the residual tails are
thin: 12 rows beyond 4 sigma out of 28,393. So this is not a handful of gross outliers being
absorbed. It is a broad loss of consistency, and the fit's compromise is a +96 cm along-track
excursion.

Critically, large residuals in the late window are evidence *against* the earlier
free-parameter explanation: a parameter absorbing error would leave residuals small, not
large. Something in that window cannot be reconciled with any orbit the model can represent.

The worst rows name GUAM three times and DJIG twice, all between 17:00 and 20:30, across
four different satellites. If the excess is station-side it will show as a few stations
degrading across many satellites at once; if satellite-side, as a few satellites degrading
across many stations. This separates them, and also reports what the elevation-dependent
sigma is actually worth, since the global whitened RMS of 0.46 says the assumed model is
about 2.2x too pessimistic overall while varying by 3x across satellites.

Read-only over the saved solution and fixture. Nothing is edited, reweighted or excluded.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.prepare_stage2 import sha

from .baseline import BEST_FIXTURE, BEST_SOLUTION
from .blocks import satellite_blocks, group
from .paths import RESULTS

WINDOWS = ((0, 8), (8, 16), (16, 24))


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values)**2))) if len(values) else None


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    f = np.load(BEST_SOLUTION)
    residual, sigma = f["residual_m"], f["sigma_m"]
    fixture = json.loads(Path(BEST_FIXTURE).read_text())
    rows, context = fixture["rows"], fixture["context"]
    epoch_count, step = context["epoch_count"], context["step_s"]
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(context["day"]).items()}

    counts = {}
    for r in rows:
        counts[r["arc"]] = counts.get(r["arc"], 0)+1
    arcset = {a for a, n in counts.items() if n >= 3}
    by_epoch = [[] for _ in range(epoch_count)]
    for i, r in enumerate(rows):
        by_epoch[r["epoch"]].append(i)
    table = [(i, kind) for ei in range(epoch_count) for i in by_epoch[ei]
             for kind in range(2 if rows[i]["arc"] in arcset else 1)]
    if len(table) != len(residual):
        raise ValueError("Row reconstruction does not match the saved residual vector")

    whitened = residual/sigma
    phase = np.array([k == 1 for _, k in table])
    idx = np.array([i for i, _ in table])
    sats = np.array([rows[i]["satellite"] for i in idx])
    stations = np.array([rows[i]["station"] for i in idx])
    hours = np.array([(rows[i]["epoch"]*step+10)/3600. for i in idx])
    # sigma_phase = 9 mm / sin(elevation) in the frozen profile, so elevation is recoverable
    # from the retained sigma itself without recomputing geometry.
    sigma_phase = np.array([rows[i]["sigma"][1] for i in idx])
    elevation = np.rad2deg(np.arcsin(np.clip(0.009/sigma_phase, -1, 1)))

    report = dict(status="error_model_diagnostic_not_accuracy_acceptance",
                  inputs=dict(solution=sha(BEST_SOLUTION), fixture=sha(BEST_FIXTURE)),
                  note="Whitened phase residuals at the converged solution. A value of 1.0 would "
                       "mean the assumed sigma is right; the pooled value is 0.46.",
                  global_phase_whitened_rms=rms(whitened[phase]))

    per_station, per_satellite = {}, {}
    for label, keys, store in (("station", stations, per_station), ("satellite", sats, per_satellite)):
        for key in sorted(set(keys)):
            m = phase & (keys == key)
            entry = dict(rows=int(m.sum()), all=rms(whitened[m]))
            for lo, hi in WINDOWS:
                entry[f"h{lo:02d}_{hi:02d}"] = rms(whitened[m & (hours >= lo) & (hours < hi)])
            early = entry["h00_08"], entry["h08_16"]
            latest = entry["h16_24"]
            base = rms([v for v in early if v is not None]) if any(v is not None for v in early) else None
            entry["late_ratio"] = (latest/base) if (latest and base) else None
            if label == "satellite":
                entry["block"] = blocks.get(key)
            store[key] = entry
    report["per_station"] = per_station
    report["per_satellite"] = per_satellite

    # Station x satellite for the late window only, to see whether the excess is a product of
    # one station's late behaviour or one satellite's, or specific to their intersection.
    late = phase & (hours >= 16)
    pairs = {}
    for station in sorted(set(stations)):
        for sat in sorted(set(sats)):
            m = late & (stations == station) & (sats == sat)
            if m.sum() >= 4:
                pairs[f"{station}:{sat}"] = dict(rows=int(m.sum()), whitened_rms=rms(whitened[m]))
    report["late_window_pairs"] = dict(sorted(pairs.items(), key=lambda kv: -kv[1]["whitened_rms"])[:30])

    bands = [(10, 20), (20, 30), (30, 45), (45, 60), (60, 90)]
    report["by_elevation"] = {f"{lo}-{hi}deg": dict(
        rows=int((phase & (elevation >= lo) & (elevation < hi)).sum()),
        whitened_rms=rms(whitened[phase & (elevation >= lo) & (elevation < hi)]),
        implied_sigma_mm=(rms(whitened[phase & (elevation >= lo) & (elevation < hi)]) or 0)*1000 *
                         float(np.median(sigma_phase[phase & (elevation >= lo) & (elevation < hi)]))
                         if (phase & (elevation >= lo) & (elevation < hi)).any() else None)
        for lo, hi in bands}

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"error_model.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"error_model.json").write_text(text)

    print(f"pooled phase whitened RMS {report['global_phase_whitened_rms']:.3f} "
          f"(1.0 would mean the assumed sigma is right)\n")
    print(f"{'station':8s} {'rows':>5s} {'all':>6s} {'00-08':>6s} {'08-16':>6s} {'16-24':>6s} {'late/early':>10s}")
    print("-"*54)
    for key, d in sorted(per_station.items(), key=lambda kv: -(kv[1]["late_ratio"] or 0)):
        print(f"{key:8s} {d['rows']:5d} {d['all']:6.3f} "
              + " ".join(f"{(d[f'h{lo:02d}_{hi:02d}'] or float('nan')):6.3f}" for lo, hi in WINDOWS)
              + f" {(d['late_ratio'] or float('nan')):10.2f}")
    print(f"\n{'sat':5s} {'blk':6s} {'all':>6s} {'00-08':>6s} {'08-16':>6s} {'16-24':>6s} {'late/early':>10s}")
    print("-"*52)
    for key, d in sorted(per_satellite.items(), key=lambda kv: -(kv[1]["late_ratio"] or 0))[:10]:
        print(f"{key:5s} {str(d['block']):6s} {d['all']:6.3f} "
              + " ".join(f"{(d[f'h{lo:02d}_{hi:02d}'] or float('nan')):6.3f}" for lo, hi in WINDOWS)
              + f" {(d['late_ratio'] or float('nan')):10.2f}")
    print("\nworst station:satellite pairs in 16-24 h:")
    for key, d in list(report["late_window_pairs"].items())[:14]:
        print(f"  {key:12s} {d['rows']:3d} rows  whitened RMS {d['whitened_rms']:6.3f}")
    print("\nby elevation (phase):")
    for key, d in report["by_elevation"].items():
        if d["whitened_rms"]:
            print(f"  {key:10s} {d['rows']:6d} rows  whitened RMS {d['whitened_rms']:.3f}  "
                  f"implied sigma {d['implied_sigma_mm']:5.1f} mm")
    print("\nWrote "+str(out/"error_model.json"))


if __name__ == "__main__":
    main()
