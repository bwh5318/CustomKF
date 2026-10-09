"""Evaluator-side scoring of Claude's Stage 5b ablations and Astra's baselines, with the
predeclared determinability split (claude/SCORING_RULE.md). Guarded; never estimator input.

    (launched by claude.tools.run_ablation)  customkf.guard -- claude.tools.evaluate_ablation CAMPAIGN_DIR
"""
from collections import defaultdict
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT, DATA as DYN, sha
from customkf.prepare_stage3 import DATA
from customkf.stage5_pilot import ORIGIN
from customkf.frames import FrameEpoch, EarthOrientation
from customkf.precise import PreciseProducts
from customkf.sp3 import read_sp3
from customkf.comparison import rac_difference, summarize

ARCHIVE = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
SIGMA_LIMIT_M = 10.0
SITE_MERGE_M = 50e3


class Reference:
    def __init__(self):
        self.epoch = FrameEpoch(ORIGIN, EarthOrientation(DYN / "finals2000A.all"))
        path = DATA / "IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
        pin = next(f["sha256"] for f in json.loads((DATA / "manifest.json").read_text())["files"]
                   if f["path"] == path.relative_to(ROOT).as_posix())
        if sha(path) != pin:
            raise ValueError("Reference input changed")
        self.sha256 = pin
        self.precise = PreciseProducts([path], [], ORIGIN, self.epoch.eop)
        self.raw = read_sp3(path)
        if self.raw.frame != "IGc20":
            raise ValueError("Unexpected reference frame")

    def rac(self, sat, t, xyz):
        sample = self.raw.samples.get((ORIGIN + int(round(t * 1e9)), sat))
        if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:
            return None
        r = self.epoch.celestial_to_terrestrial(t).T @ sample.xyz_m
        return rac_difference(r, xyz, self.precise.state(sat, t)[3:])


def coverage(fixture):
    rows = fixture["rows"]
    xyz = {}
    for r in rows:
        xyz.setdefault(r["station"], np.asarray(r["receiver_xyz"], float))
    names = sorted(xyz)
    site = {s: s for s in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if np.linalg.norm(xyz[a] - xyz[b]) < SITE_MERGE_M and site[a] != site[b]:
                old = site[b]
                for s in names:
                    if site[s] == old:
                        site[s] = site[a]
    epochs, stations = defaultdict(lambda: defaultdict(set)), defaultdict(set)
    for r in rows:
        epochs[r["satellite"]][r["epoch"]].add(site[r["station"]])
        stations[r["satellite"]].add(r["station"])
    out = {}
    for sat, per in epochs.items():
        out[sat] = {"stations": sorted(stations[sat]), "sites": sorted({s for v in per.values() for s in v}),
                    "multi_site_epochs": sum(len(v) >= 2 for v in per.values()),
                    "observed_epochs": [min(per), max(per)]}
    groups = defaultdict(list)
    for s, root in site.items():
        groups[root].append(s)
    return out, {k: sorted(v) for k, v in groups.items() if len(v) > 1}


def reason(c, count):
    if c is None:
        return "no retained observations; prior only"
    n = len(c["sites"])
    parts = [f"{n} viewing site{'s' if n != 1 else ''} ({', '.join(c['stations'])})"]
    if n == 1:
        parts.append("single viewing site: per-epoch satellite clock absorbs line-of-sight range")
    parts.append(f"{c['multi_site_epochs']} of {count} solve epochs seen simultaneously from >=2 sites")
    lo, hi = c["observed_epochs"]
    if lo > 0 or hi < count - 1:
        parts.append(f"observed only in epochs {lo}-{hi}; other scored epochs are extrapolated")
    return "; ".join(parts)


def summary(racs):
    return summarize(np.array(racs)) if racs else None


def score(reference, solution_dir, fixture_path, initial_path):
    fit = np.load(solution_dir / "solution.npz")
    initial = np.load(initial_path)
    np.testing.assert_array_equal(fit["satellites"], initial["satellites"])
    np.testing.assert_array_equal(fit["times_s"], initial["times_s"])
    fixture = json.loads(fixture_path.read_text())
    count = fixture["context"]["epoch_count"]
    cov, merged = coverage(fixture)
    names = [str(n) for n in fit["names"]]
    matrix = fit["retained_covariance"]
    per_sat, groups = {}, defaultdict(lambda: {"initial": [], "fit": []})
    for si, sat in enumerate(str(s) for s in fit["satellites"]):
        k = names.index(f"orbit:{sat}:0")
        sigma = float(np.sqrt(np.trace(matrix[k:k + 3, k:k + 3])))
        label = "prior_only" if sat not in cov else ("determined" if sigma <= SIGMA_LIMIT_M else "poorly_determined")
        values = {"initial": [], "fit": []}
        for ti, t in enumerate(float(v) for v in fit["times_s"]):
            a = reference.rac(sat, t, initial["states"][si, ti, :3])
            if a is None:
                continue
            values["initial"].append(a)
            values["fit"].append(reference.rac(sat, t, fit["states"][si, ti, :3]))
        for kind in values:
            groups["all"][kind].extend(values[kind])
            groups["determined" if label == "determined" else "poorly_determined"][kind].extend(values[kind])
        per_sat[sat] = {"class": label, "formal_position_sigma_m": sigma,
                        "fit": summary(values["fit"]), "initial": summary(values["initial"]),
                        "coverage": cov.get(sat), "reason": reason(cov.get(sat), count), "_racs": values}
    # Phase RMS by station, residual order as in customkf.evaluate_stage5b.
    counts = defaultdict(int)
    for r in fixture["rows"]:
        counts[r["arc"]] += 1
    k = 0
    phase = defaultdict(list)
    for ei in range(count):
        for r in fixture["rows"]:
            if r["epoch"] != ei:
                continue
            for kind in range(2 if counts[r["arc"]] >= 3 else 1):
                if kind:
                    phase[r["station"]].append(float(fit["residual_m"][k]))
                k += 1
    if k != len(fit["residual_m"]):
        raise ValueError("Residual label mismatch")
    return {"solution": str(solution_dir), "solution_sha256": sha(solution_dir / "solution.npz"),
            "fixture_sha256": sha(fixture_path), "merged_sites": merged,
            "groups": {g: {kind: summary(v[kind]) for kind in v} | {"satellites": sorted(s for s, p in per_sat.items() if g == "all" or (p["class"] == "determined") == (g == "determined"))}
                       for g, v in groups.items()},
            "phase_rms_mm": {s: 1e3 * float(np.sqrt(np.mean(np.square(v)))) for s, v in sorted(phase.items())},
            "per_satellite": per_sat}


def pooled(result, sats):
    racs = {"initial": [], "fit": []}
    for s in sats:
        for kind in racs:
            racs[kind].extend(result["per_satellite"][s]["_racs"][kind])
    return {kind: summary(v) for kind, v in racs.items()} | {"satellites": sorted(sats)}


def strip(result):
    for p in result["per_satellite"].values():
        p.pop("_racs", None)
    return result


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    campaign_dir = Path(sys.argv[1])
    campaign = json.loads((campaign_dir / "campaign.json").read_text())
    astra = json.loads((ARCHIVE / "validation.json").read_text())
    reference = Reference()
    baselines = {case: score(reference, ARCHIVE / astra["final_steps"][case], ARCHIVE / f"{case}-prepare/fixture.json",
                             ARCHIVE / f"{case}-prepare/initial.npz") for case in ("eight-short", "eight-long", "expanded-long")}
    ablations, comparisons = {}, {}
    for name, case in campaign["cases"].items():
        if not case.get("final"):
            continue
        base = case["base"]
        result = score(reference, campaign_dir / case["final"], campaign_dir / case["prepare"] / "fixture.json",
                       ARCHIVE / f"{base}-prepare/initial.npz")
        both = sorted(s for s, p in result["per_satellite"].items()
                      if p["class"] == "determined" and baselines[base]["per_satellite"][s]["class"] == "determined")
        comparisons[name] = {"base": base, "determined_in_both": {"baseline": pooled(baselines[base], both), "ablation": pooled(result, both)},
                             "satellite_fit_3d_change_m": {s: [baselines[base]["per_satellite"][s]["fit"]["rms_3d_m"], p["fit"]["rms_3d_m"]]
                                                           for s, p in result["per_satellite"].items()
                                                           if p["fit"] and abs(p["fit"]["rms_3d_m"] - baselines[base]["per_satellite"][s]["fit"]["rms_3d_m"]) > 1.0}}
        ablations[name] = result
    report = {"status": "evaluation_only_not_accuracy_acceptance", "rule": {"formal_sigma_limit_m": SIGMA_LIMIT_M, "site_merge_m": SITE_MERGE_M, "document": "claude/SCORING_RULE.md"},
              "reference_sha256": reference.sha256, "comparisons": comparisons,
              "baselines": {k: strip(v) for k, v in baselines.items()}, "ablations": {k: strip(v) for k, v in ablations.items()}}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")

    def line(label, g):
        if not g or not g.get("fit"):
            return f"    {label:22s} (none)"
        f, i = g["fit"], g["initial"]
        return (f"    {label:22s} fit 3D {f['rms_3d_m']:9.3f} m  RAC {'/'.join(f'{v:.2f}' for v in f['rms_rac_m'])}  "
                f"seed 3D {i['rms_3d_m']:.3f}  sats {len(g['satellites'])}  samples {f['samples']}")

    for label, results in (("BASELINE", report["baselines"]), ("ABLATION", report["ablations"])):
        for name, r in results.items():
            print(f"=== {label} {name}  merged sites {r['merged_sites']}")
            for g in ("all", "determined", "poorly_determined"):
                print(line(g, r["groups"].get(g)))
            for s, p in sorted(r["per_satellite"].items()):
                if p["class"] != "determined":
                    fit = p["fit"]["rms_3d_m"] if p["fit"] else float("nan")
                    print(f"      {s} sigma {p['formal_position_sigma_m']:8.1f} m  IGS 3D {fit:8.2f} m  -- {p['reason']}")
            print("    phase RMS mm: " + " ".join(f"{s}:{v:.1f}" for s, v in r["phase_rms_mm"].items()))
    for name, c in comparisons.items():
        print(f"=== COMPARISON {name} vs {c['base']} on satellites determined in both ({len(c['determined_in_both']['baseline']['satellites'])})")
        print(line("baseline", c["determined_in_both"]["baseline"]))
        print(line("ablation", c["determined_in_both"]["ablation"]))
        print("    per-satellite 3D changes > 1 m: " + ", ".join(f"{s} {a:.2f}->{b:.2f}" for s, (a, b) in sorted(c["satellite_fit_3d_change_m"].items())))


if __name__ == "__main__":
    main()
