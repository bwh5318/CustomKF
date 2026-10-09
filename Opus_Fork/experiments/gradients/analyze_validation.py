"""Gradient validation (option A): analysis under VALIDATION_PROTOCOL.md (+ amendment A1).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.gradients.analyze_validation

Reads the completed campaigns and the production evaluations (`Opus_Fork/results/gradval_YYYYMMDD.json`, written by
`Opus_Fork.evaluate`), then:
- the lin0 control (trajectory arrays bitwise equal to each comparator's);
- independent-oracle scores (validation.oracle, sub-daily frame) against the production scores;
- the pre-registered reading for each candidate;
- the per-date GRAD input-support account (amendment A1).
Writes `validation_analysis.json` in the run folder. No fit, no integration.

Hardened 5 Oct 2026 (Astra review R02), for any rerun; the saved 3 Oct analysis and the protocol are unchanged:
- a candidate's reading is withheld ("not read (a control failed)") unless every lin0 and oracle control passes;
- solutions come from the evaluation's provenance, with their hashes verified, not from the latest campaign name;
- the common population is reconstructed from the reference, NGA and every arm, and its sorted-key digest is recorded.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from Opus_Fork.experiments.transfer.common import run_dir, sha
from Opus_Fork.paths import ROOT
from validation.oracle import frame as O2, metrics as O1

R = ROOT/"Opus_Fork/runs"
HERE = Path(__file__).resolve().parent
DATES = {"0606": ("2026-06-06", "runs/20260929T202245Z-21f63ba3", "20260930T012728Z-fit-U-elw13-0606"),
         "0620": ("2026-06-20", "runs/20260929T203924Z-224f1e22", "20260929T233503Z-fit-U-elw13-0620"),
         "0623": ("2026-06-23", "runs/20260929T201929Z-5b2b3e42", "20261001T012217Z-fit-U-elw13-0623r"),
         "0706": ("2026-07-06", "runs/20260929T204645Z-ba94e895", "20260930T234445Z-fit-U-elw13-0706"),
         "0723": ("2026-07-23", "runs/20260929T203059Z-40b5a8d7", "20260930T220757Z-fit-U-elw13-0723")}
CANDIDATES = {"grad_op": "V-op", "gpt3": "V-gpt3"}
SCORE_TOL_M = 1e-4


def campaign(label):
    found = sorted(R.glob(f"*-fit-{label}"))
    if not found:
        raise ValueError(f"no campaign {label}")
    return found[-1]


def final_solution(folder):
    v = json.loads((folder/"validation.json").read_text())
    if not v["status"].startswith("long_fit_complete"):
        raise ValueError(f"{folder.name} is not complete: {v['status']}")
    path = folder/v["final"]/"solution.npz"
    step = json.loads((path.parent/"step.json").read_text())
    assert step["status"] == "converged" and sha(path) == step["solution_sha256"]
    with np.load(path) as f:
        return dict(states=f["states"][:, :, :3].copy(), sats=[str(s) for s in f["satellites"]], times=f["times_s"].copy(),
                    path=str(path), final=v["final"], force_model=json.loads((path.parent/"force_model.json").read_text()))


def provenance_solution(evaluation, arm):
    """The arm's converged solution exactly as the evaluation scored it (path and hash from its provenance)."""
    record = evaluation["provenance"][arm]
    path = Path(record["solution"])
    if sha(path) != record["sha256"]:
        raise ValueError(f"{arm}: solution bytes differ from the evaluated ones")
    step = json.loads((path.parent/"step.json").read_text())
    if step["status"] != "converged" or step["solution_sha256"] != record["sha256"]:
        raise ValueError(f"{arm}: the evaluated solution is not a recorded converged step")
    with np.load(path) as f:
        return dict(states=f["states"][:, :, :3].copy(), sats=[str(s) for s in f["satellites"]], times=f["times_s"].copy(),
                    path=str(path), final=path.parent.name, campaign=path.parent.parent,
                    force_model=json.loads((path.parent/"force_model.json").read_text()))


def key_digest(keys):
    return hashlib.sha256(repr(sorted(keys)).encode()).hexdigest()


def classify(changes, worst_m, worst_radial_pct, controls_pass):
    """The pre-registered reading (VALIDATION_PROTOCOL.md); withheld when any control failed (Astra R02)."""
    if not controls_pass:
        return "not read (a control failed)"
    better, mean = sum(c < 0 for c in changes), float(np.mean(changes))
    if better >= 4 and mean <= -1.0 and worst_m <= 0.1 and worst_radial_pct <= 3.0:
        return "validated on these dates"
    if sum(c > 0 for c in changes) >= 2 or mean > 0:
        return "not validated"
    return "inconclusive"


def lin0_control(arm, comparator):
    out = {}
    for g in (0, 1):
        with np.load(arm/f"lin0-traj-{g}/trajectories.npz") as a, np.load(comparator/f"lin0-traj-{g}/trajectories.npz") as b:
            names = sorted(a.files)
            out[f"group{g}"] = bool(names == sorted(b.files) and all(np.array_equal(a[k], b[k]) for k in names))
    return out


def input_support(day):
    """GRAD files the arc's interpolation needs (previous, same and next day) and their observed Last-Modified."""
    date = datetime.strptime(day, "%Y-%m-%d")
    rows = {Path(r["file"]).name: r for r in csv.DictReader(open(HERE/"acquisition_record.tsv"), delimiter="\t")}
    arc_end = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)+timedelta(days=1)
    needed = []
    for offset in (-1, 0, 1):
        name = (date+timedelta(days=offset)).strftime("%Y%j")+".grad_g"
        r = rows.get(name)
        modified = parsedate_to_datetime(r["last_modified"]) if r else None
        needed.append(dict(file=name, sha256=r["sha256"] if r else None,
                           last_modified_utc=modified.isoformat() if modified else None,
                           hours_after_arc_end=(modified-arc_end).total_seconds()/3600 if modified else None))
    latest = max(n["hours_after_arc_end"] for n in needed if n["hours_after_arc_end"] is not None)
    return dict(files=needed, latest_observed_hours_after_arc_end=latest,
                label="retrospective (observed server modification times, not verified issue times)")


def main():
    folder = run_dir()
    frame = O2.Frame(O2.Finals(ROOT/"data/stage2/finals2000A.all"), subdaily=True)
    report = dict(protocol_sha256=sha(HERE/"VALIDATION_PROTOCOL.md"), dates={}, candidates={})
    for tag, (day, fixture_dir, comparator_name) in DATES.items():
        evaluation_path = ROOT/f"Opus_Fork/results/gradval_{day.replace('-', '')}.json"
        evaluation = json.loads(evaluation_path.read_text())
        arms = evaluation["domains"]["full"]["arms"]
        fixture = json.loads((ROOT/fixture_dir/"fixture.json").read_text())
        origin = int(fixture["context"]["origin_ns"])
        reference = O1.read_sp3(evaluation["provenance"]["igs_final"]["path"])
        base = provenance_solution(evaluation, "U")
        comparator = base["campaign"]
        nga = O1.read_sp3(evaluation["provenance"]["NGA"]["path"])
        start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
        solutions = {"U": base, **{prefix: provenance_solution(evaluation, prefix) for prefix in CANDIDATES.values()}}
        ecefs = {k: O1.solution_ecef(v["states"], v["sats"], v["times"], origin, frame) for k, v in solutions.items()}
        keys = {k for k in set(reference) & set(nga) if start <= k[1] <= stop}
        for ecef in ecefs.values():
            keys &= set(ecef)
        oracle = {"U": O1.summarize(reference, ecefs["U"], frame, keys)}
        entry = dict(day=day, comparator=comparator.name, comparator_final=base["final"],
                     evaluation_sha256=sha(evaluation_path), input_support=input_support(day), arms={},
                     common_keys=len(keys), common_key_digest=key_digest(keys))
        for source, prefix in CANDIDATES.items():
            new = solutions[prefix]
            folder_arm = new["campaign"]
            assert new["force_model"]["gradients"]["source"] == source and "gradients" not in base["force_model"]
            oracle[prefix] = O1.summarize(reference, ecefs[prefix], frame, keys)
            a, u = arms[prefix]["raw"], arms["U"]["raw"]
            per_sat = arms[prefix]["per_satellite"]
            worst = max(((per_sat[s]["rms_3d_m"]-arms["U"]["per_satellite"][s]["rms_3d_m"]), s) for s in arms["U"]["per_satellite"])
            entry["arms"][prefix] = dict(
                campaign=folder_arm.name, final=new["final"], lin0_bitwise=lin0_control(folder_arm, comparator),
                ure_cm=a["rms_orbit_ure_m"]*100, ure_change_pct=100*(a["rms_orbit_ure_m"]/u["rms_orbit_ure_m"]-1),
                d3_cm=a["rms_3d_m"]*100, d3_change_pct=100*(a["rms_3d_m"]/u["rms_3d_m"]-1),
                radial_change_pct=100*(a["rms_rac_m"][0]/u["rms_rac_m"][0]-1),
                rac_cm=[x*100 for x in a["rms_rac_m"]], worst_satellite_3d_increase_m=worst[0], worst_satellite=worst[1],
                satellites_better=sum(per_sat[s]["rms_3d_m"] < arms["U"]["per_satellite"][s]["rms_3d_m"] for s in per_sat),
                ure_ratio_to_nga=a["rms_orbit_ure_m"]/arms["NGA"]["raw"]["rms_orbit_ure_m"],
                oracle_ure_change_pct=100*(oracle[prefix]["orbit_ure_m"]/oracle["U"]["orbit_ure_m"]-1))
        entry["oracle_vs_production_max_m"] = max(
            max(abs(oracle[k]["orbit_ure_m"]-arms[k]["raw"]["rms_orbit_ure_m"]), abs(oracle[k]["rms_3d_m"]-arms[k]["raw"]["rms_3d_m"]))
            for k in oracle)
        entry["oracle_samples_equal"] = all(oracle[k]["samples"] == arms[k]["raw"]["samples"] for k in oracle)
        entry["U_ure_cm"], entry["NGA_ure_cm"] = arms["U"]["raw"]["rms_orbit_ure_m"]*100, arms["NGA"]["raw"]["rms_orbit_ure_m"]*100
        report["dates"][tag] = entry
        print(tag, {p: round(e["ure_change_pct"], 2) for p, e in entry["arms"].items()}, flush=True)
    report["oracle_within_tolerance"] = all(e["oracle_vs_production_max_m"] <= SCORE_TOL_M and e["oracle_samples_equal"]
                                            for e in report["dates"].values())
    for source, prefix in CANDIDATES.items():
        rows = [report["dates"][t]["arms"][prefix] for t in DATES]
        changes = [r["ure_change_pct"] for r in rows]
        worst = max(r["worst_satellite_3d_increase_m"] for r in rows)
        radial = max(r["radial_change_pct"] for r in rows)
        controls = all(all(r["lin0_bitwise"].values()) for r in rows)
        reading = classify(changes, worst, radial, controls and report["oracle_within_tolerance"])
        report["candidates"][source] = dict(dates_better=sum(c < 0 for c in changes), ure_changes_pct=changes,
                                            mean_ure_change_pct=float(np.mean(changes)),
                                            mean_3d_change_pct=float(np.mean([r["d3_change_pct"] for r in rows])),
                                            worst_satellite_3d_increase_m=worst, worst_radial_change_pct=radial,
                                            lin0_controls_all_bitwise=controls, reading=reading)
        print(source, json.dumps(report["candidates"][source]), flush=True)
    (folder/"validation_analysis.json").write_text(json.dumps(report, indent=1)+"\n")


if __name__ == "__main__":
    main()
