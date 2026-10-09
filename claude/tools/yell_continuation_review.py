"""Guarded review of Claude's YELL continuation; evaluator-side only, no fit or data editing.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.yell_continuation_review CAMPAIGN

Astra's claude/tools/yell_result_review.py is hard-wired to the interrupted original campaign,
so this applies its checks (pinned artifacts/sources, stationary-checkpoint identity, daily
YELL PPP residual screen, per-satellite changes) to the continuation archive. It adds the
handoff's follow-ups: actual versus screened co-visibility, stability of previously determined
satellites, network residual structure at YELL and the weak-satellite tails. The frozen
scoring rule is unchanged. Writes only review.json in the guarded run directory.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from claude.tools.evaluate_ablation import Reference, coverage

BASE = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
FOCUS = ("G16", "G18", "G26", "G29", "G31")
# Astra's cached-data screen (STAGE5B_STATION_CHECKS.md), recorded before any YELL observation was read.
SCREEN_CO_VISIBLE = {"G16": 10, "G18": 23, "G26": 7, "G29": 21, "G31": 1}
SCREEN_G18_MEDIAN_MAX_LOS_DEG = 20.97


def rms(values):
    values = np.asarray([v for v in values if v is not None], float)
    return float(np.sqrt(np.mean(values * values))) if len(values) else None


def labelled(fixture):
    """(row, kind) in the estimator's residual order: epoch, fixture row, code then phase for arcs with >=3 rows."""
    counts = {}
    for r in fixture["rows"]:
        counts[r["arc"]] = counts.get(r["arc"], 0) + 1
    out = []
    for ei in range(fixture["context"]["epoch_count"]):
        for r in fixture["rows"]:
            if r["epoch"] == ei:
                out.extend((r, kind) for kind in range(2 if counts[r["arc"]] >= 3 else 1))
    return out


def residual_structure(fixture, fit):
    labels = labelled(fixture)
    residual, sigma = fit["residual_m"], fit["sigma_m"]
    if len(labels) != len(residual):
        raise ValueError("Residual label mismatch")
    # Row sigmas are elevation dependent, so this also checks the label order row by row.
    np.testing.assert_allclose(sigma, [r["sigma"][k] for r, k in labels], rtol=1e-12, atol=0)
    station = np.array([r["station"] for r, _ in labels])
    kind = np.array([k for _, k in labels])
    z = residual / sigma
    per_station = {}
    for s in sorted(set(station)):
        per_station[s] = {}
        for k, label in ((0, "code"), (1, "phase")):
            m = (station == s) & (kind == k)
            if m.any():
                per_station[s][label] = {"count": int(m.sum()), "rms_mm": 1e3 * rms(residual[m]),
                                         "normalized_rms": rms(z[m]), "above_4_sigma": int(np.sum(abs(z[m]) > 4))}
    return per_station, labels, residual, z


def yell_residual_detail(labels, residual, z):
    rows = [(i, r, k) for i, (r, k) in enumerate(labels) if r["station"] == "YELL"]
    by_epoch, by_sat = {}, {}
    for i, r, k in rows:
        if k:
            by_epoch.setdefault(r["epoch"], []).append(residual[i])
            by_sat.setdefault(r["satellite"], []).append(residual[i])
    return {"phase_rms_mm_by_epoch": {e: 1e3 * rms(v) for e, v in sorted(by_epoch.items())},
            "phase_rms_mm_by_satellite": {s: 1e3 * rms(v) for s, v in sorted(by_sat.items())},
            "above_4_sigma_rows": [{"epoch": r["epoch"], "satellite": r["satellite"], "kind": "phase" if k else "code",
                                    "residual_mm": 1e3 * float(residual[i]), "normalized": float(z[i])}
                                   for i, r, k in rows if abs(z[i]) > 4]}


def visibility(fixture, reference, initial):
    _, merged = coverage(fixture)
    site = {r["station"]: r["station"] for r in fixture["rows"]}
    for root, members in merged.items():
        for m in members:
            site[m] = root
    count = fixture["context"]["epoch_count"]
    sats = [str(s) for s in initial["satellites"]]
    out = {}
    for sat in FOCUS:
        per = [dict() for _ in range(count)]
        for r in fixture["rows"]:
            if r["satellite"] == sat:
                per[r["epoch"]][r["station"]] = r
        n_sites = [len({site[s] for s in p}) for p in per]
        entry = {"multi_site_epochs": [i for i in range(count) if n_sites[i] >= 2],
                 "single_site_epochs": [i for i in range(count) if n_sites[i] == 1],
                 "unobserved_epochs": [i for i in range(count) if n_sites[i] == 0]}
        if "YELL" in site:
            yell = [i for i in range(count) if "YELL" in per[i]]
            shared = [i for i in yell if any(site[s] != site["YELL"] for s in per[i])]
            separation = []
            for i in shared:
                t = float(initial["times_s"][i])
                if abs(t - per[i]["YELL"]["time_s"]) > 1e-6:
                    raise ValueError("Epoch/time mismatch")
                # Broadcast seed geometry, as in the screen; metre-level orbit error is irrelevant to LOS angles.
                xyz = reference.epoch.celestial_to_terrestrial(t) @ initial["states"][sats.index(sat), i, :3]
                los = {s: (xyz - np.asarray(r["receiver_xyz"])) / np.linalg.norm(xyz - np.asarray(r["receiver_xyz"])) for s, r in per[i].items()}
                separation.append(max(float(np.degrees(np.arccos(np.clip(los["YELL"] @ los[s], -1, 1))))
                                      for s in per[i] if site[s] != site["YELL"]))
            elevation = [float(np.degrees(np.arcsin(.9 / per[i]["YELL"]["sigma"][0]))) for i in yell]
            entry.update(YELL_epochs=yell, YELL_co_visible_epochs=shared, YELL_co_visible_count=len(shared),
                         screen_potential_co_visible=SCREEN_CO_VISIBLE[sat],
                         YELL_elevation_deg={"min": min(elevation), "median": float(np.median(elevation)), "max": max(elevation)} if yell else None,
                         median_max_LOS_separation_deg=float(np.median(separation)) if separation else None)
        out[sat] = entry
    return out


def epoch_errors(reference, solution_dir):
    fit = np.load(solution_dir / "solution.npz")
    out = {}
    for si, sat in enumerate(str(s) for s in fit["satellites"]):
        if sat in FOCUS:
            values = [reference.rac(sat, float(t), fit["states"][si, ti, :3]) for ti, t in enumerate(fit["times_s"])]
            out[sat] = [None if v is None else float(np.linalg.norm(v)) for v in values]
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    campaign = parser.parse_args().campaign.resolve()
    manifest = json.loads((campaign / "validation.json").read_text())
    assert manifest["status"] == "YELL_continuation_complete_not_accuracy_acceptance", manifest["status"]
    for name, digest in manifest["artifacts_sha256"].items():
        assert sha(campaign / name) == digest, name
    for group in ("source_sha256", "report_sha256"):
        for name, digest in manifest[group].items():
            assert sha(ROOT / name) == digest, name
    original = ROOT / manifest["original_campaign"]
    for name, digest in manifest["original_inventory_sha256"].items():
        assert sha(original / name) == digest, name
    fixture = json.loads((campaign / "prepare/fixture.json").read_text())
    for name, digest in fixture["context"]["inputs"].items():
        assert sha(ROOT / name) == digest, name
    evaluation = json.loads((campaign / "evaluation/evaluation.json").read_text())
    assert evaluation["status"] == "same_arc_YELL_comparison_complete_not_accuracy_acceptance"

    final = campaign / manifest["final"]
    step = json.loads((final / "step.json").read_text())
    fit = np.load(final / "solution.npz")
    stationary = not step["history"][-1]["update_applied"]
    if stationary:
        number = int(manifest["final"].split("-")[-1])
        before = np.load(ROOT / manifest["checkpoints"][f"iteration-{number - 1}"] / "solution.npz")
        for key in ("x", "states", "residual_m", "sigma_m", "times_s", "satellites"):
            np.testing.assert_array_equal(before[key], fit[key], err_msg=key)

    ppp = np.load(original / "YELL_PPP/ppp.npz")
    phase = ppp["phase"]
    residual = ppp["residual_m"][phase]
    hours = ppp["time_s"][phase] / 3600
    normalized = residual * np.sin(ppp["elevation_rad"][phase]) / .009

    def ppp_stats(mask):
        r, z = residual[mask], normalized[mask]
        return {"count": int(len(r)), "rms_mm": 1e3 * rms(r), "max_abs_mm": 1e3 * float(np.max(abs(r))),
                "normalized_rms": rms(z), "above_4_sigma": int(np.sum(abs(z) > 4))}

    ppp_review = {"daily": ppp_stats(np.ones(len(hours), dtype=bool)), "network_interval": ppp_stats((hours >= 12) & (hours <= 15)),
                  "flagged_rows": [{"hour_gpst": float(hours[i]), "satellite": str(ppp["satellite"][phase][i]),
                                    "phase_mm": 1e3 * float(residual[i]), "normalized": float(normalized[i])}
                                   for i in np.flatnonzero(abs(normalized) > 4)]}

    reference = Reference()
    base_fixture = json.loads((BASE / "expanded-long-prepare/fixture.json").read_text())
    initial = np.load(campaign / "prepare/initial.npz")
    geometry = {"baseline": visibility(base_fixture, reference, initial), "YELL": visibility(fixture, reference, initial)}
    for sat in FOCUS:
        old, new = set(geometry["baseline"][sat]["multi_site_epochs"]), set(geometry["YELL"][sat]["multi_site_epochs"])
        geometry["YELL"][sat].update(gained_multi_site_epochs=sorted(new - old), lost_multi_site_epochs=sorted(old - new))

    base_residuals = residual_structure(base_fixture, np.load(BASE / "expanded-long-final/solution.npz"))[0]
    new_residuals, labels, network_residual, z = residual_structure(fixture, fit)

    b, y = evaluation["baseline"]["per_satellite"], evaluation["YELL"]["per_satellite"]
    changes = {s: {"baseline_class": b[s]["class"], "YELL_class": y[s]["class"],
                   "baseline_formal_sigma_m": b[s]["formal_position_sigma_m"], "YELL_formal_sigma_m": y[s]["formal_position_sigma_m"],
                   "baseline_rms_3d_m": b[s]["fit"]["rms_3d_m"], "YELL_rms_3d_m": y[s]["fit"]["rms_3d_m"],
                   "delta_rms_3d_m": y[s]["fit"]["rms_3d_m"] - b[s]["fit"]["rms_3d_m"], "YELL_reason": y[s]["reason"]}
               for s in sorted(b)}
    both = evaluation["determined_in_both"]["baseline"]["satellites"]
    deltas = {s: changes[s]["delta_rms_3d_m"] for s in both}
    errors = {"baseline": epoch_errors(reference, BASE / "expanded-long-final"), "YELL": epoch_errors(reference, final)}
    segments = {}
    for sat in FOCUS:
        g = geometry["YELL"][sat]
        segments[sat] = {label: {"epochs": epochs, "reference_samples": sum(errors["YELL"][sat][i] is not None for i in epochs),
                                 "baseline_rms_3d_m": rms([errors["baseline"][sat][i] for i in epochs]),
                                 "YELL_rms_3d_m": rms([errors["YELL"][sat][i] for i in epochs])}
                         for label, epochs in (("multi_site", g["multi_site_epochs"]), ("single_site", g["single_site_epochs"]),
                                               ("unobserved", g["unobserved_epochs"]))}

    report = {
        "status": "YELL_continuation_reviewed_not_accuracy_acceptance",
        "campaign": campaign.relative_to(ROOT).as_posix(), "manifest_sha256": sha(campaign / "validation.json"),
        "tool_sha256": sha(Path(__file__)), "reference_sha256": reference.sha256,
        "checks": {"artifacts_sources_report_original_inventory_and_inputs_pinned": True,
                   "stationary_checkpoint_identity_checked": stationary,
                   "network_residual_labels_verified_against_row_sigma": True},
        "history": step["history"],
        "scores": {"all_satellites": {"baseline": evaluation["baseline"]["groups"]["all"], "YELL": evaluation["YELL"]["groups"]["all"]},
                   "all_common": evaluation["all_common"], "determined_in_both": evaluation["determined_in_both"],
                   "groups": {"baseline": evaluation["baseline"]["groups"], "YELL": evaluation["YELL"]["groups"]},
                   "cartesian_independent_rms_m": evaluation["cartesian_independent_rms_m"]},
        "class_changes": {s: [c["baseline_class"], c["YELL_class"]] for s, c in changes.items() if c["baseline_class"] != c["YELL_class"]},
        "determined_in_both_rms_change_m": {"count": len(deltas), "max_abs": max(map(abs, deltas.values())),
                                            "median": float(np.median(list(deltas.values()))),
                                            "largest_five": dict(sorted(deltas.items(), key=lambda v: -abs(v[1]))[:5])},
        "per_satellite_changes": changes,
        "co_visibility": geometry, "screen_G18_median_max_LOS_deg": SCREEN_G18_MEDIAN_MAX_LOS_DEG,
        "focus_epoch_3d_error_m": errors, "focus_error_by_coverage": segments,
        "network_residuals": {"baseline": base_residuals, "YELL": new_residuals,
                              "YELL_detail": yell_residual_detail(labels, network_residual, z)},
        "PPP_residual_review": ppp_review,
    }
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"scores": {k: report["scores"][k] for k in ("all_common", "determined_in_both")},
                      "class_changes": report["class_changes"], "determined_in_both_rms_change_m": report["determined_in_both_rms_change_m"],
                      "focus": {s: {k: changes[s][k] for k in ("baseline_formal_sigma_m", "YELL_formal_sigma_m", "baseline_rms_3d_m", "YELL_rms_3d_m", "YELL_class")} for s in FOCUS},
                      "co_visible_actual_vs_screen": {s: [geometry["YELL"][s]["YELL_co_visible_count"], SCREEN_CO_VISIBLE[s]] for s in FOCUS},
                      "G18_median_max_LOS_deg": geometry["YELL"]["G18"]["median_max_LOS_separation_deg"],
                      "focus_error_by_coverage": segments, "YELL_network_residuals": new_residuals["YELL"],
                      "PPP": {k: ppp_review[k] for k in ("daily", "network_interval")}, "PPP_flagged": len(ppp_review["flagged_rows"])}, indent=2))


if __name__ == "__main__":
    main()
