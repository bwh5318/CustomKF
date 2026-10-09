"""Guarded cached-data coverage screen for frozen poorly determined satellites. No IGS products,
downloads, fit or accuracy prediction.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.weak_coverage_screen

Parameterized from Astra's claude/tools/astra_weak_coverage.py; its scoring method is unchanged.
1. Regression: rerun on the 12-station Stage 5b masks and its five weak satellites. Every
   candidate number must equal Astra's archived coverage.json, or the tool stops.
2. Screen: the 13-station YELL-continuation masks and the satellites its final covariance
   classifies as poorly determined under the frozen 10 m rule (expected G16, G26, G31). Adds
   newly gained multi-site epochs, candidate elevations, nearest-site distance and
   per-satellite rankings. Writes only coverage.json in the guarded run directory.
"""
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import ORIGIN, forbid_precise_product_reads
from customkf.rinex import read_gps_navigation
from customkf.broadcast import position, select_fit_record
from customkf.station_models import reference_coordinate, read_loading
from customkf.measurement import enu_matrix
from claude.tools.evaluate_ablation import coverage, SIGMA_LIMIT_M, SITE_MERGE_M

DATA = ROOT / "data/stage3"
ARCHIVE = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
ASTRA_SCREEN = ROOT / "validation/stage5b_stations/20260911T015113Z/followup-review"
CAMPAIGN = ROOT / "claude/runs/20260911T022428Z-yell-continuation"
LISTING = ROOT / "data/stage5b/bkg-2026214-listing.html"
HEADERS = ROOT / "runs/20260910T015027Z-4dc3d5cc/headers.json"
BASELINE_FOCUS = ("G16", "G18", "G26", "G29", "G31")


def screen(fixture, focus, nav, extras):
    """Astra's method verbatim for the archived fields; extras only add new fields."""
    header_info = json.loads(HEADERS.read_text())
    markers = sorted(set(re.findall(r'([A-Z0-9]{9})_R_20262140000_01D_30S_MO\.crx\.gz', LISTING.read_text())))
    psd = (DATA / "psd_IGc20.snx").read_text(); candidates = {}; rejected = {}
    baseline = {r["station"]: np.array(r["receiver_xyz"]) for r in fixture["rows"]}
    for marker in markers:
        station = marker[:4]
        if station in baseline: continue
        try:
            if station in psd: raise ValueError("Unsupported PSD")
            xyz, _ = reference_coordinate(DATA / "IGc20.ssc", DATA / "soln_IGc20.snx", station, datetime(2026, 8, 2, 12))
            read_loading(DATA / "FES2014b.BLQ", station)
            candidates[station] = (marker, xyz)
        except ValueError as error: rejected[station] = str(error)
    times = 10 + 300 * np.arange(37); cutoff = fixture["context"]["navigation_cutoff_ns"]
    states = {s: np.array([position(select_fit_record(nav[s], ORIGIN + int(t * 1e9), available_before_ns=cutoff), ORIGIN + int(t * 1e9)) for t in times]) for s in focus}
    def views(xyz, s):
        d = states[s] - xyz; u = d / np.linalg.norm(d, axis=1)[:, None]; sine = u @ enu_matrix(xyz)[2]
        return u, np.where(sine >= np.sin(np.deg2rad(10)), sine**2, 0)
    existing = {st: {s: views(xyz, s) for s in focus} for st, xyz in baseline.items()}
    masks = {s: [{r["station"] for r in fixture["rows"] if r["satellite"] == s and r["epoch"] == i} for i in range(37)] for s in focus}
    _, merged = coverage(fixture)
    site = {s: s for s in baseline}
    for root, members in merged.items():
        for m in members: site[m] = root
    results = []
    for st, (marker, xyz) in candidates.items():
        per = {}; total = 0.
        for sat in focus:
            u, w = views(xyz, sat); gain = 0.; potential = 0; separation = []
            elevation = []; gained = []
            for i, stations in enumerate(masks[sat]):
                if w[i] == 0 or not stations: continue
                distinct = [s for s in stations if np.linalg.norm(xyz - baseline[s]) >= 50000]
                if distinct: potential += 1
                if extras:
                    if distinct: elevation.append(float(np.degrees(np.arcsin(np.sqrt(w[i])))))
                    if len({site[s] for s in stations}) == 1 and len(distinct) == len(stations): gained.append(i)
                weights = np.array([existing[s][sat][1][i] for s in stations]); directions = np.array([existing[s][sat][0][i] for s in stations])
                weight = float(weights.sum())
                if weight <= 0: continue
                mean = np.sum(weights[:, None] * directions, axis=0) / weight
                # Increment in trace of clock-centred LOS information; receiver
                # clocks assumed known. All focus satellites have equal weight.
                gain += float(weight * w[i] / (weight + w[i]) * np.sum((u[i] - mean)**2))
                if distinct: separation.append(max(float(np.degrees(np.arccos(np.clip(u[i] @ existing[s][sat][0][i], -1, 1)))) for s in distinct))
            total += gain
            per[sat] = {"potential_distinct_co_visible_epochs": potential,
                "geometric_visible_epochs": np.flatnonzero(w > 0).tolist(), "los_information_trace_gain": gain,
                "median_max_los_separation_deg": float(np.median(separation)) if separation else None}
            if extras:
                per[sat].update(newly_gained_multi_site_epochs=gained,
                                co_visible_elevation_deg={"min": min(elevation), "median": float(np.median(elevation)), "max": max(elevation)} if elevation else None)
        info = header_info.get(marker, {"status": "not_header_screened"})
        if st == "REUN": info = {"status": "previous_full_file_compatible"}
        result = {"station": st, "marker": marker, "score": total, "header_status": info["status"], "header_reason": info.get("reason"),
                  "full_local_rinex_present": (DATA / f"{marker}_R_20262140000_01D_30S_MO.rnx.gz").exists(), "per_satellite": per}
        if extras:
            result["nearest_network_station_km"] = min(float(np.linalg.norm(xyz - v)) / 1e3 for v in baseline.values())
        results.append(result)
    results.sort(key=lambda v: (-v["score"], v["station"]))
    current = {s: {"multi_site_epochs": [i for i, m in enumerate(masks[s]) if len({site[x] for x in m}) >= 2],
                   "single_site_epochs": [i for i, m in enumerate(masks[s]) if len({site[x] for x in m}) == 1],
                   "unobserved_epochs": [i for i, m in enumerate(masks[s]) if not m]} for s in focus}
    return results, rejected, current


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15)
    return a == b


def regression(results, rejected):
    archived = json.loads((ASTRA_SCREEN / "coverage/coverage.json").read_text())
    if [c["station"] for c in results] != [c["station"] for c in archived["candidates"]] or rejected != archived["rejected_metadata"]:
        raise AssertionError("Candidate set, order or rejections differ from Astra's archived screen")
    rinex_changed = []
    for new, old in zip(results, archived["candidates"]):
        for key in ("marker", "score", "header_status", "header_reason"):
            if not same(new[key], old[key]): raise AssertionError(f"{new['station']} {key}: {new[key]} != {old[key]}")
        if new["full_local_rinex_present"] != old["full_local_rinex_present"]: rinex_changed.append(new["station"])
        for sat, values in old["per_satellite"].items():
            for key, value in values.items():
                if not same(new["per_satellite"][sat][key], value): raise AssertionError(f"{new['station']} {sat} {key}")
    return {"status": "reproduced_astra_archived_screen", "candidates": len(results), "rejected": len(rejected),
            "full_local_rinex_present_changed_since": rinex_changed}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    astra_manifest = json.loads((ASTRA_SCREEN / "manifest.json").read_text())
    assert sha(ASTRA_SCREEN / "coverage/coverage.json") == astra_manifest["artifacts_sha256"]["coverage\\coverage.json"]
    archived_inputs = json.loads((ASTRA_SCREEN / "coverage/coverage.json").read_text())["input_sha256"]
    for name, digest in archived_inputs.items(): assert sha(ROOT / name) == digest, name
    base_manifest = json.loads((ARCHIVE / "validation.json").read_text())
    base_path = ARCHIVE / "expanded-long-prepare/fixture.json"
    assert sha(base_path) == base_manifest["artifacts_sha256"]["expanded-long-prepare/fixture.json"]
    campaign = json.loads((CAMPAIGN / "validation.json").read_text())
    assert campaign["status"] == "YELL_continuation_complete_not_accuracy_acceptance"
    yell_path = CAMPAIGN / "prepare/fixture.json"; final = CAMPAIGN / campaign["final"] / "solution.npz"
    for path in (yell_path, final): assert sha(path) == campaign["artifacts_sha256"][path.relative_to(CAMPAIGN).as_posix()], path
    base_fixture = json.loads(base_path.read_text()); yell_fixture = json.loads(yell_path.read_text())
    for fixture in (base_fixture, yell_fixture):
        for name, digest in fixture["context"]["inputs"].items(): assert sha(ROOT / name) == digest, name
    nav = read_gps_navigation(DATA / "BRDC00WRD_R_20262140000_01D_MN.rnx.gz")

    report = {"status": "candidate_geometry_screen_only",
              "regression": regression(*screen(base_fixture, BASELINE_FOCUS, nav, extras=False)[:2])}
    # Frozen classifier from the final retained covariance only (claude/SCORING_RULE.md); no IGS-derived input.
    fit = np.load(final); names = [str(n) for n in fit["names"]]; observed = {r["satellite"] for r in yell_fixture["rows"]}
    sigma = {}
    for sat in (str(s) for s in fit["satellites"]):
        k = names.index(f"orbit:{sat}:0"); sigma[sat] = float(np.sqrt(np.trace(fit["retained_covariance"][k:k + 3, k:k + 3])))
    focus = tuple(s for s in sorted(sigma) if s not in observed or sigma[s] > SIGMA_LIMIT_M)
    results, rejected, current = screen(yell_fixture, focus, nav, extras=True)
    compatible = [r for r in results if r["header_status"] in ("compatible_header", "previous_full_file_compatible")]
    def brief(r, sat):
        p = r["per_satellite"][sat]
        return {"station": r["station"], "gain": p["los_information_trace_gain"], "potential": p["potential_distinct_co_visible_epochs"],
                "newly_gained_multi_site_epochs": p["newly_gained_multi_site_epochs"], "median_max_los_separation_deg": p["median_max_los_separation_deg"],
                "co_visible_elevation_deg": p["co_visible_elevation_deg"], "nearest_network_station_km": r["nearest_network_station_km"],
                "header_status": r["header_status"], "full_local_rinex_present": r["full_local_rinex_present"]}
    report.update(
        method="Astra's unchanged screen: equal-weight sum over focus satellites of incremental clock-centred LOS information trace; "
               "actual retained 13-station masks; candidate broadcast elevation >=10 deg; receiver clocks assumed known; no orbit-error inputs. "
               "Newly gained multi-site epochs: epochs with exactly one current viewing site (50 km merge) and the candidate >=50 km from it.",
        limitation="Potential visibility is not verified observation availability; unchecked headers say nothing about signals, calibration or data quality. "
                   "Heuristic, not a dynamic covariance or error forecast.",
        network=sorted({r["station"] for r in yell_fixture["rows"]}), site_merge_m=SITE_MERGE_M,
        focus=list(focus), focus_formal_position_sigma_m={s: sigma[s] for s in focus}, focus_current_coverage=current,
        candidates=results, compatible_candidates=compatible,
        per_satellite_top={sat: [brief(r, sat) for r in sorted(results, key=lambda v: (-v["per_satellite"][sat]["los_information_trace_gain"], v["station"]))[:10]] for sat in focus},
        rejected_metadata=rejected,
        input_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in (base_path, yell_path, final, LISTING, HEADERS, ASTRA_SCREEN / "coverage/coverage.json")},
        tool_sha256=sha(Path(__file__)), method_source_sha256=sha(ROOT / "claude/tools/astra_weak_coverage.py"))
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "coverage.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"regression": report["regression"], "focus_sigma_m": report["focus_formal_position_sigma_m"],
                      "focus_current_coverage": current,
                      "top_overall": [{"station": r["station"], "score": r["score"], "header": r["header_status"], "rinex": r["full_local_rinex_present"],
                                       "nearest_km": round(r["nearest_network_station_km"]),
                                       **{s: [r["per_satellite"][s]["potential_distinct_co_visible_epochs"], len(r["per_satellite"][s]["newly_gained_multi_site_epochs"])] for s in focus}}
                                      for r in results[:15]],
                      "compatible": [{"station": r["station"], "score": r["score"], "header": r["header_status"], "rinex": r["full_local_rinex_present"],
                                      **{s: [r["per_satellite"][s]["potential_distinct_co_visible_epochs"], len(r["per_satellite"][s]["newly_gained_multi_site_epochs"])] for s in focus}}
                                     for r in compatible],
                      "per_satellite_top5": {s: v[:5] for s, v in report["per_satellite_top"].items()}}, indent=1))


if __name__ == "__main__":
    main()
