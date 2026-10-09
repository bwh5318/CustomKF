"""Midday radial dip diagnosis, and distribution metrics against NGA PE.

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 1800 --label dip-nga -- Opus_Fork.dip_nga

Evaluation only, over archived converged solutions. IGS final and NGA PE are read here and
nowhere else. No fit, no estimator input.

Cases, all against IGS final, on satellite-epochs common to both arms and NGA PE:

| Day | Baseline | ERP arm | Notes |
|---|---|---|---|
| Aug 2 | N0 | P1 (erp+thrust) | 25 stations |
| Aug 3 | B-3 | P2-3 (erp+thrust+iiia2600) | 25 stations |
| Aug 4 | B-4 | P2-4 | 23 stations |
| Aug 5 | B-5 | P2-5 | 23 stations |
| Aug 7 | B7 (Astra expanded25) | R7 (erp+thrust) | 25 stations; Astra's fixture |

## Part A: the midday dip, fixed before running

Baseline pooled mean radial by window (early 00–16 h / noon 12–18 h / late 18–24 h) was
+1.7 / +0.3 / +1.7 cm on Aug 2, with similar dips on Aug 3, 4 and 5. Each check below separates
candidate explanations:

1. **Hourly pooled mean radial** for the arms and for NGA. If NGA shows the same dip against
   IGS, it is in the reference (IGS) rather than in our orbits.
2. **Constellation-wide or a few satellites?** Per-epoch 7-parameter Helmert scale, with
   translation for context, against the pooled mean radial. The noon shift is decomposed by
   satellite (each satellite's noon-window mean minus its full-day mean) and aggregated by
   orbital plane, by block, and by in-plane angle from the Sun (Δu).
3. **Tied to Earth-fixed or Sun-fixed geometry?** Radial residuals are binned after removing
   each satellite's daily constant, by sub-satellite longitude and by Δu, for all days
   together.
4. **Network coverage.** Links per epoch, and stations per satellite-epoch, from the fixture,
   against the pooled mean radial.
5. **Dynamics-only fits** (T1 census, Aug 2, E5 and E5P, fitted to IGS positions with no
   station data). If their pooled residual shows the same UT dip, the dip is a property of the
   dynamics/frame against IGS, not of our observations.

## Part B: distributions against NGA

Per sample, orbit-only URE = sqrt(0.98²R² + (A²+C²)/49), plus 3D. For each case and arm:

- percentiles (50/68/90/95/99/max);
- the share of samples below 1, 2, 3, 4, 5, 7.5 and 10 cm;
- the paired share of samples where the arm is lower than NGA;
- per-satellite daily RMS wins; per-epoch (constellation RMS) wins; per-hour wins.

All days are also pooled. NGA is WGS84 against an IGc20 reference, so a per-epoch-Helmert
version of the paired win share is given as a labelled diagnostic, never as the score.
Satellite-epochs are strongly correlated in time, so shares are descriptive, not independent
trials.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.comparison import orbit_ure_m
from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation, FrameEpoch
from customkf.prepare_stage2 import ROOT, sha

from .baseline import Fit, OnOrigin
from .blocks import satellite_blocks, group
from .evaluate import load_reference, midnight_of
from .paths import STAGE2, RESULTS
from .score import helmert_residual

R = "Opus_Fork/runs/"
CASES = [
    ("2026-08-02", R+"20260920T200910Z-prepare-31sat/fixture.json",
     ("B", R+"20260920T203126Z-fit-N0-31sat/lin2-solve"), ("ERP", R+"20260922T205445Z-fit-P1-erp-31sat/lin2-solve"), "erp+thrust"),
    ("2026-08-03", R+"20260922T225652Z-prepare-2026-08-03/fixture.json",
     ("B", R+"20260922T230936Z-fit-B-3-25st/lin2-solve"), ("ERP", R+"20260923T000354Z-fit-P2-3-25st/lin2-solve"), "erp+thrust+iiia2600"),
    ("2026-08-04", R+"20260922T230119Z-prepare-2026-08-04/fixture.json",
     ("B", R+"20260923T010309Z-fit-B-4-25st/lin2-solve"), ("ERP", R+"20260923T200747Z-fit-P2-4-25st/lin2-solve"), "erp+thrust+iiia2600"),
    ("2026-08-05", R+"20260922T230410Z-prepare-2026-08-05/fixture.json",
     ("B", R+"20260923T210059Z-fit-B-5-25st/lin4-solve"), ("ERP", R+"20260923T230743Z-fit-P2-5-25st/lin3-solve"), "erp+thrust+iiia2600"),
    ("2026-08-07", "runs/20260920T155655Z-7b703635/fixture.json",
     ("B", "runs/20260920T180129Z-38cb5d57"), ("ERP", R+"20260922T215245Z-fit-R7-erp-aug7-25st/lin2-solve"), "erp+thrust"),
]
WINDOWS = {"early": (0, 16), "noon": (12, 18), "late": (18, 24)}
THRESHOLDS_CM = (1, 2, 3, 4, 5, 7.5, 10)


def sun_geometry(r, v, sun):
    h = np.cross(r, v)
    h /= np.linalg.norm(h)
    s = sun/np.linalg.norm(sun)
    beta = np.arcsin(np.clip(s@h, -1, 1))
    sp = s-(s@h)*h
    sp /= np.linalg.norm(sp)
    rh = r/np.linalg.norm(r)
    du = np.arctan2(np.cross(sp, rh)@h, sp@rh)
    return float(du), float(beta)


def load_solution(path, fixture, eop, midnight):
    p = ROOT/path
    solution = p/"solution.npz" if p.is_dir() else p
    step = json.loads((solution.parent/"step.json").read_text())
    if step["status"] != "converged" or sha(solution) != step["solution_sha256"]:
        raise ValueError("Not a verified converged solution: "+str(solution))
    return OnOrigin(Fit(solution, ROOT/fixture, eop), midnight), dict(solution=str(solution), sha256=step["solution_sha256"])


def coverage(fixture):
    """Links per epoch-second (GPS second of the fixture's day) and stations per satellite-epoch."""
    f = json.loads((ROOT/fixture).read_text())
    origin = int(f["context"]["origin_ns"])
    links, per = {}, {}
    for row in f["rows"]:
        ns = origin+int(round(row["time_s"]*1e9))
        links[ns] = links.get(ns, 0)+1
        per[(row["satellite"], ns)] = per.get((row["satellite"], ns), 0)+1
    return links, per


def build(day, fixture, arms, eop, ephemeris):
    midnight = midnight_of(day)
    reference, ref_prov = load_reference("reference_igs_final", day, midnight, eop, "IGS final", "IGc20")
    nga, nga_prov = load_reference("reference_nga_pe", day, midnight, eop, "NGA PE", "WGS84", legacy="GPS")
    products, prov = {}, dict(igs_final=ref_prov, NGA=nga_prov)
    for label, path in arms:
        products[label], prov[label] = load_solution(path, fixture, eop, midnight)
    products["NGA"] = nga
    common = set(reference.keys())
    for p in products.values():
        common &= p.keys()
    keys = sorted(common, key=lambda k: (k[1], k[0]))
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(day).items()}
    epoch = FrameEpoch(midnight, eop)
    links, per = coverage(fixture)
    rows = []
    for sat, ns in keys:
        t = (ns-midnight)/1e9
        r, v = reference.position(sat, t), reference.velocity(sat, t)
        radial = r/np.linalg.norm(r)
        normal = np.cross(r, v)/np.linalg.norm(np.cross(r, v))
        axes = np.array([radial, np.cross(normal, radial), normal])
        sun, _ = ephemeris.sun_moon_m(epoch.tdb_seconds(t))
        du, beta = sun_geometry(r, v, sun)
        ecef = reference.rotation(t)@r
        lon = float(np.degrees(np.arctan2(ecef[1], ecef[0])))
        node = float(np.degrees(np.arctan2(normal[0], -normal[1])))  # RAAN (inertial) identifies the plane
        # Coverage at the nearest solve epoch (10 min grid) at or before this 15-min sample.
        near = max((k for k in links if k <= ns), default=None)
        row = dict(sat=sat, ns=ns, hour=t/3600., du=du, beta=beta, lon=lon, raan=node, block=blocks.get(sat),
                   links=links.get(near, 0) if near else 0, stations=per.get((sat, near), 0) if near else 0)
        for label, p in products.items():
            row[label] = axes@(p.position(sat, t)-r)
        rows.append(row)
    helmert, resid = {}, {}
    for label, p in products.items():
        resid[label], params = helmert_residual(reference, p, set(keys))
        helmert[label] = {ns: dict(scale_ppb=q["scale"]*1e9, translation_mm=(np.array(q["translation_m"])*1000).tolist())
                          for ns, q in params.items()}
    return rows, helmert, prov, resid


def ure(rac):
    return orbit_ure_m(np.atleast_2d(rac))*100


def plane_labels(rows):
    """Six planes by clustering RAAN (inertial node) into 60-degree sectors around their medians."""
    raan = {}
    for r in rows:
        raan.setdefault(r["sat"], []).append(r["raan"])
    med = {s: float(np.median(v)) for s, v in raan.items()}
    order = sorted(med, key=lambda s: med[s] % 360)
    base = med[order[0]] % 360
    return {s: "ABCDEF"[int(((med[s]-base) % 360+30)//60) % 6] for s in med}


def part_a(all_rows, helmert, census):
    out = {}
    for day, rows in all_rows.items():
        arms = [k for k in ("B", "ERP", "NGA")]
        hours = np.array([r["hour"] for r in rows])
        entry = dict(hourly_mean_radial_cm={}, window_mean_radial_cm={}, helmert_scale_ppb_hourly={},
                     corr_pooled_radial_vs_scale={}, noon_shift_by_plane_cm={}, noon_shift_by_block_cm={},
                     noon_shift_top_satellites_cm={}, coverage={})
        planes = plane_labels(rows)
        for a in arms:
            rad = np.array([r[a][0] for r in rows])*100
            entry["hourly_mean_radial_cm"][a] = [float(rad[(hours >= h) & (hours < h+1)].mean()) for h in range(24)]
            entry["window_mean_radial_cm"][a] = {w: float(rad[(hours >= lo) & (hours < hi)].mean()) for w, (lo, hi) in WINDOWS.items()}
            sc = helmert[day][a]
            ep = sorted(sc)
            ep_h = np.array([(ns-rows[0]["ns"]+rows[0]["hour"]*3600e9)/3600e9 for ns in ep])
            scale = np.array([sc[ns]["scale_ppb"] for ns in ep])
            entry["helmert_scale_ppb_hourly"][a] = [float(scale[(ep_h >= h) & (ep_h < h+1)].mean()) for h in range(24)]
            per_epoch = {}
            for r in rows:
                per_epoch.setdefault(r["ns"], []).append(r[a][0]*100)
            pm = np.array([np.mean(per_epoch[ns]) for ns in ep])
            entry["corr_pooled_radial_vs_scale"][a] = float(np.corrcoef(pm, scale)[0, 1])
            # Noon shift per satellite: noon-window mean minus full-day mean.
            by_sat = {}
            for r, x in zip(rows, rad):
                by_sat.setdefault(r["sat"], []).append((r["hour"], x))
            shift = {}
            for s, v in by_sat.items():
                v = np.array(v)
                m = (v[:, 0] >= 12) & (v[:, 0] < 18)
                if m.sum() >= 6:
                    shift[s] = float(v[m, 1].mean()-v[:, 1].mean())
            entry["noon_shift_top_satellites_cm"][a] = dict(sorted(shift.items(), key=lambda kv: kv[1])[:6])
            for label, key in (("noon_shift_by_plane_cm", planes), ("noon_shift_by_block_cm", {r["sat"]: r["block"] for r in rows})):
                agg = {}
                for s, x in shift.items():
                    agg.setdefault(key[s], []).append(x)
                entry[label][a] = {k: dict(n=len(v), mean=float(np.mean(v))) for k, v in sorted(agg.items(), key=lambda kv: str(kv[0]))}
            entry.setdefault("noon_shift_mean_over_satellites_cm", {})[a] = float(np.mean(list(shift.values())))
            entry.setdefault("noon_shift_share_negative", {})[a] = float(np.mean([x < 0 for x in shift.values()]))
        links = np.array([r["links"] for r in rows])
        stations = np.array([r["stations"] for r in rows])
        entry["coverage"] = dict(links_hourly=[float(links[(hours >= h) & (hours < h+1)].mean()) for h in range(24)],
                                 stations_per_sat_hourly=[float(stations[(hours >= h) & (hours < h+1)].mean()) for h in range(24)])
        out[day] = entry
    # Pooled over days: residual radial (daily constant removed) binned by longitude and by du.
    geo = {}
    for a in ("B", "ERP", "NGA"):
        lon_bins, du_bins = {}, {}
        for day, rows in all_rows.items():
            const = {}
            for r in rows:
                const.setdefault(r["sat"], []).append(r[a][0])
            const = {s: np.mean(v) for s, v in const.items()}
            for r in rows:
                x = (r[a][0]-const[r["sat"]])*100
                lon_bins.setdefault(int((r["lon"]+180)//30), []).append(x)
                du_bins.setdefault(int((np.degrees(r["du"])+180)//30), []).append(x)
        geo[a] = dict(by_subsatellite_lon_30deg={f"{-180+30*k}..{-150+30*k}": dict(n=len(v), mean=float(np.mean(v)))
                                                 for k, v in sorted(lon_bins.items())},
                      by_du_from_sun_30deg={f"{-180+30*k}..{-150+30*k}": dict(n=len(v), mean=float(np.mean(v)))
                                            for k, v in sorted(du_bins.items())})
    out["pooled_geometry_bins_constant_removed"] = geo
    # Dynamics-only census (Aug 2): pooled residual by hour.
    cen = {}
    for variant in ("E5", "E5P"):
        acc = {h: [] for h in range(24)}
        for s, v in census["satellites"].items():
            e = v.get("variants", {}).get(variant, {})
            for hour, rr, _, _ in e.get("series_cm", []):
                if hour < 24:
                    acc[int(hour)].append(rr)
        hourly = [float(np.mean(acc[h])) if acc[h] else None for h in range(24)]
        win = {w: float(np.mean([x for h in range(lo, hi) for x in acc[h]])) for w, (lo, hi) in WINDOWS.items()}
        cen[variant] = dict(hourly_mean_radial_cm=hourly, window_mean_radial_cm=win)
    out["dynamics_only_census_2026-08-02"] = cen
    return out


def part_b(all_rows, all_helmert_resid):
    out, pooled = {}, {a: dict(ure=[], ure_nga=[], d3=[], d3_nga=[]) for a in ("B", "ERP")}
    for day, rows in all_rows.items():
        entry = {}
        u = {a: np.array([ure(r[a])[0] for r in rows]) for a in ("B", "ERP", "NGA")}
        d3 = {a: np.array([np.linalg.norm(r[a])*100 for r in rows]) for a in ("B", "ERP", "NGA")}
        hours = np.array([r["hour"] for r in rows])
        sats = np.array([r["sat"] for r in rows])
        ns = np.array([r["ns"] for r in rows])
        for a in ("B", "ERP", "NGA"):
            entry[a] = dict(
                ure_percentiles_cm={p: float(np.percentile(u[a], p)) for p in (50, 68, 90, 95, 99)} | {"max": float(u[a].max())},
                ure_rms_cm=float(np.sqrt(np.mean(u[a]**2))),
                share_ure_below_cm={str(t): float(np.mean(u[a] < t)) for t in THRESHOLDS_CM},
                d3_percentiles_cm={p: float(np.percentile(d3[a], p)) for p in (50, 68, 90, 95, 99)} | {"max": float(d3[a].max())})
        for a in ("B", "ERP"):
            e = entry[a]
            e["paired_share_ure_lower_than_nga"] = float(np.mean(u[a] < u["NGA"]))
            e["paired_share_3d_lower_than_nga"] = float(np.mean(d3[a] < d3["NGA"]))
            persat = {s: (np.sqrt(np.mean(u[a][sats == s]**2)), np.sqrt(np.mean(u["NGA"][sats == s]**2))) for s in sorted(set(sats))}
            e["satellites_daily_rms_ure_better_than_nga"] = f"{sum(x < y for x, y in persat.values())}/{len(persat)}"
            e["worst_satellites_vs_nga_cm"] = {s: [round(float(x), 3), round(float(y), 3)] for s, (x, y) in
                                               sorted(persat.items(), key=lambda kv: kv[1][1]-kv[1][0])[:4]}
            epochs = sorted(set(ns))
            per_ep = np.array([(np.sqrt(np.mean(u[a][ns == k]**2)), np.sqrt(np.mean(u["NGA"][ns == k]**2))) for k in epochs])
            e["epochs_constellation_rms_ure_better_than_nga"] = f"{int(np.sum(per_ep[:, 0] < per_ep[:, 1]))}/{len(epochs)}"
            e["epoch_constellation_rms_ure_percentiles_cm"] = {p: [float(np.percentile(per_ep[:, 0], p)), float(np.percentile(per_ep[:, 1], p))]
                                                               for p in (50, 90, 95)} | {"note": "[arm, NGA]"}
            hours_better = [h for h in range(24) if np.sqrt(np.mean(u[a][(hours >= h) & (hours < h+1)]**2)) <
                            np.sqrt(np.mean(u["NGA"][(hours >= h) & (hours < h+1)]**2))]
            e["hours_rms_ure_better_than_nga"] = f"{len(hours_better)}/24"
            e["hours_worse_than_nga"] = [h for h in range(24) if h not in hours_better]
            hr = all_helmert_resid[day]
            e["diagnostic_after_helmert_paired_share_ure_lower_than_nga"] = float(np.mean(
                [ure(hr[a][(r["sat"], r["ns"])])[0] < ure(hr["NGA"][(r["sat"], r["ns"])])[0] for r in rows]))
            pooled[a]["ure"] += list(u[a]); pooled[a]["ure_nga"] += list(u["NGA"])
            pooled[a]["d3"] += list(d3[a]); pooled[a]["d3_nga"] += list(d3["NGA"])
        out[day] = entry
    agg = {}
    for a in ("B", "ERP"):
        x, y = np.array(pooled[a]["ure"]), np.array(pooled[a]["ure_nga"])
        x3, y3 = np.array(pooled[a]["d3"]), np.array(pooled[a]["d3_nga"])
        agg[a] = dict(samples=len(x),
                      ure_percentiles_cm={p: [float(np.percentile(x, p)), float(np.percentile(y, p))] for p in (50, 68, 90, 95, 99)} | {"note": "[arm, NGA]"},
                      ure_rms_cm=[float(np.sqrt(np.mean(x**2))), float(np.sqrt(np.mean(y**2)))],
                      share_ure_below_cm={str(t): [float(np.mean(x < t)), float(np.mean(y < t))] for t in THRESHOLDS_CM},
                      paired_share_ure_lower_than_nga=float(np.mean(x < y)),
                      paired_share_3d_lower_than_nga=float(np.mean(x3 < y3)),
                      d3_percentiles_cm={p: [float(np.percentile(x3, p)), float(np.percentile(y3, p))] for p in (50, 90, 95)})
    out["pooled_all_days"] = agg
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    run = Path(os.environ["CUSTOMKF_RUN_DIR"])
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    ephemeris = DE440(STAGE2/"de440s.bsp")
    all_rows, helmert, resid, provenance = {}, {}, {}, {}
    for day, fixture, base, erp, variant in CASES:
        rows, h, prov, r = build(day, fixture, [base, erp], eop, ephemeris)
        all_rows[day], helmert[day], resid[day] = rows, h, r
        provenance[day] = dict(prov, variant=variant, fixture=fixture, common_samples=len(rows))
        print(day, len(rows), "samples", flush=True)
    census = json.loads((RESULTS/"reference_census_2026-08-02_physics.json").read_text())
    a = part_a(all_rows, helmert, census)
    b = part_b(all_rows, resid)
    report = dict(status="evaluation_only_not_accuracy_acceptance", reference="IGS final", provenance=provenance,
                  part_a_midday_dip=a, part_b_nga_distributions=b)
    text = json.dumps(report, indent=1, default=float)+"\n"
    (run/"dip_nga.json").write_text(text)
    (RESULTS/"dip_nga.json").write_text(text)
    for day in all_rows:
        w = a[day]["window_mean_radial_cm"]
        print(day, " ".join(f"{k}: " + "/".join(f"{w[k][x]:+.2f}" for x in ("early", "noon", "late")) for k in ("B", "ERP", "NGA")),
              "| corr(pooled R, scale) B %.2f" % a[day]["corr_pooled_radial_vs_scale"]["B"],
              "| noon shift mean B %+.2f, share<0 %.2f" % (a[day]["noon_shift_mean_over_satellites_cm"]["B"], a[day]["noon_shift_share_negative"]["B"]), flush=True)
    print("census E5 windows", a["dynamics_only_census_2026-08-02"]["E5"]["window_mean_radial_cm"])
    for day in all_rows:
        e = b[day]["ERP"]
        print(day, "ERP vs NGA: URE lower on %.1f%% of samples; p50/p95 %.2f/%.2f vs NGA %.2f/%.2f; sats %s; epochs %s; hours %s" % (
            100*e["paired_share_ure_lower_than_nga"], e["ure_percentiles_cm"][50], e["ure_percentiles_cm"][95],
            b[day]["NGA"]["ure_percentiles_cm"][50], b[day]["NGA"]["ure_percentiles_cm"][95],
            e["satellites_daily_rms_ure_better_than_nga"], e["epochs_constellation_rms_ure_better_than_nga"], e["hours_rms_ure_better_than_nga"]), flush=True)
    print("Wrote", run/"dip_nga.json")


if __name__ == "__main__":
    main()
