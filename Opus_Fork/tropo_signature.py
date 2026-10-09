"""T0.2: is there an unmodelled tropospheric-gradient signature in the post-fit phase residuals?

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 900 --label tropo-signature \
        -- Opus_Fork.tropo_signature

Archive-only diagnostic over the N0 solution (Aug 2, 25 stations, 24 h, 31 satellites,
original 9 mm/sin(el) weights) and its fixture. No reference product, fit, reweighting or
exclusion.

**Why.** The estimator has no gradient parameters (`customkf/station_models.py`). A 1 mm N/E
gradient is about 3 cm of azimuth-dependent delay at 10° elevation. W1/W2 treated the steep
elevation growth of residual scatter, and its station- and hour-dependence, as noise. If part of
it is an unmodelled gradient, the residuals carry a cos/sin(azimuth) × m_g(el) signature that
noise would not have.

**Method, fixed before running.** Phase rows below 30° elevation, per station and per 8-hour
window (00–08, 08–16, 16–24 GPST), with at least 40 rows. Weighted least squares of the
residual on m_g(el)·cos(az) and m_g(el)·sin(az), where m_g = 1/(sin e·tan e + 0.0032)
(Chen & Herring 1997), with weights 1/σ². Statistics:

- the fraction of whitened sum of squares explained;
- the fitted gradients G_N and G_E in mm;
- an **azimuth-permutation control**: 200 shuffles of azimuth within the group, keeping
  elevations, sigmas and residuals. The 95th percentile of their explained fraction is the
  bar a real signature must clear.

Azimuth comes from the receiver coordinates and the fitted satellite position at the epoch,
rotated to Earth-fixed axes with the pinned EOP. Light time is ignored; its effect on azimuth
is about 1e-5 rad.

**Declared outcome.** Gradients are *supported* if, in at least ⅓ of stations, one or more
windows explains ≥15% of the low-elevation whitened SS **and** beats its permutation 95th
percentile. The prediction is that DJIG, GUAM and VACS late windows are among the largest. A
negative result removes this confound from the weighting work.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.frames import EarthOrientation, FrameEpoch
from customkf.prepare_stage2 import ROOT, sha

from .paths import STAGE2, RESULTS

SOLUTION = ROOT/"Opus_Fork/runs/20260920T203126Z-fit-N0-31sat/lin2-solve/solution.npz"
FIXTURE = ROOT/"Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json"
WINDOWS = ((0, 8), (8, 16), (16, 24))
PERMUTATIONS = 200
MIN_ROWS = 40


def enu_axes(xyz):
    x, y, z = xyz
    lon = np.arctan2(y, x)
    lat = np.arctan2(z, np.hypot(x, y))  # geocentric latitude suffices for azimuth at this level
    east = np.array([-np.sin(lon), np.cos(lon), 0.])
    north = np.array([-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)])
    up = np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    return east, north, up


def explained(r, s, e, az):
    """Whitened SS fraction explained by the gradient signature, and the fitted gradients (m)."""
    mg = 1/(np.sin(e)*np.tan(e)+0.0032)
    a = np.column_stack([mg*np.cos(az), mg*np.sin(az)])/s[:, None]
    y = r/s
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    left = y-a@coef
    return 1-float(left@left)/float(y@y), coef


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    run = Path(os.environ["CUSTOMKF_RUN_DIR"])
    with np.load(SOLUTION) as f:
        residual, sigma = f["residual_m"].copy(), f["sigma_m"].copy()
        states, sats, times = f["states"][:, :, :3].copy(), [str(s) for s in f["satellites"]], f["times_s"].copy()
    fixture = json.loads(FIXTURE.read_text())
    rows, context = fixture["rows"], fixture["context"]
    counts = {}
    for r in rows:
        counts[r["arc"]] = counts.get(r["arc"], 0)+1
    eligible = {a for a, n in counts.items() if n >= 3}
    by_epoch = [[] for _ in range(context["epoch_count"])]
    for i, r in enumerate(rows):
        by_epoch[r["epoch"]].append(i)
    table = [(i, kind) for ei in range(context["epoch_count"]) for i in by_epoch[ei]
             for kind in range(2 if rows[i]["arc"] in eligible else 1)]
    if len(table) != len(residual):
        raise ValueError("Row reconstruction does not match the saved residual vector")
    epoch = FrameEpoch(int(context["origin_ns"]), EarthOrientation(STAGE2/"finals2000A.all"))
    sat_index = {s: k for k, s in enumerate(sats)}
    rotations, axes = {}, {}
    data = {}
    for (i, kind), res, sig in zip(table, residual, sigma):
        if kind != 1:
            continue
        row = rows[i]
        t = row["time_s"]
        ti = int(np.argmin(np.abs(times-t)))
        if abs(times[ti]-t) > 1e-6:
            raise ValueError("Row time is not on the saved state grid")
        if t not in rotations:
            rotations[t] = epoch.celestial_to_terrestrial(t)
        sat_ecef = rotations[t]@states[sat_index[row["satellite"]], ti]
        rx = np.asarray(row["receiver_xyz"])
        station = row["station"]
        if station not in axes:
            axes[station] = enu_axes(rx)
        east, north, up = axes[station]
        los = sat_ecef-rx
        los /= np.linalg.norm(los)
        elevation = np.arcsin(los@up)
        azimuth = np.arctan2(los@east, los@north)
        hour = (t+context["origin_ns"] % 86400_000_000_000/1e9) % 86400/3600.
        data.setdefault(station, []).append((hour, elevation, azimuth, res, sig))
    rng = np.random.default_rng(20260922)
    report = dict(status="archive_diagnostic_not_accuracy_acceptance", test="T0.2 troposphere gradient signature",
                  inputs=dict(solution=str(SOLUTION), solution_sha256=sha(SOLUTION),
                              fixture=str(FIXTURE), fixture_sha256=sha(FIXTURE)),
                  method=dict(elevation_below_deg=30, windows_h=WINDOWS, min_rows=MIN_ROWS,
                              permutations=PERMUTATIONS, mapping="Chen-Herring 1/(sin e tan e + 0.0032)"),
                  stations={})
    supported = 0
    for station, values in sorted(data.items()):
        a = np.array(values)
        entry = {}
        for lo, hi in WINDOWS:
            m = (a[:, 0] >= lo) & (a[:, 0] < hi) & (a[:, 1] < np.deg2rad(30))
            if m.sum() < MIN_ROWS:
                entry[f"{lo:02d}-{hi:02d}"] = dict(rows=int(m.sum()), skipped="too few low-elevation rows")
                continue
            _, e, az, r, s = a[m].T
            frac, coef = explained(r, s, e, az)
            null = np.array([explained(r, s, e, rng.permutation(az))[0] for _ in range(PERMUTATIONS)])
            p95 = float(np.percentile(null, 95))
            entry[f"{lo:02d}-{hi:02d}"] = dict(rows=int(m.sum()), explained=frac, permutation_p95=p95,
                                                beats_control=bool(frac > p95),
                                                gradient_north_mm=float(coef[0]*1000), gradient_east_mm=float(coef[1]*1000),
                                                low_el_whitened_rms=float(np.sqrt(np.mean((r/s)**2))))
        hits = [k for k, v in entry.items() if v.get("explained", 0) >= .15 and v.get("beats_control")]
        entry["supported_windows"] = hits
        supported += bool(hits)
        report["stations"][station] = entry
        line = " | ".join(f"{k} {v['explained']*100:5.1f}% (p95 {v['permutation_p95']*100:4.1f}) "
                          f"G {v['gradient_north_mm']:+.2f}/{v['gradient_east_mm']:+.2f} mm"
                          if "explained" in v else f"{k} -" for k, v in entry.items() if k != "supported_windows")
        print(f"{station:5s} {line}{'  <== supported' if hits else ''}", flush=True)
    report["stations_supported"] = supported
    report["stations_total"] = len(report["stations"])
    report["verdict"] = "supported" if supported >= len(report["stations"])/3 else "not_supported"
    print(f"\n{supported}/{len(report['stations'])} stations with a supported window -> {report['verdict']}", flush=True)
    text = json.dumps(report, indent=2, default=float)+"\n"
    (run/"tropo_signature.json").write_text(text)
    (RESULTS/"tropo_signature.json").write_text(text)


if __name__ == "__main__":
    main()
