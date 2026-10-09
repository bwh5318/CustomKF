"""Station-network tests: controls, readings and descriptive scores (PROTOCOL.md §6 with amendments A2, A3 and A4).

    Run by score_networks.py, never by hand on loose files:
    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 3600 -- \
        Opus_Fork.experiments.networks.analyze_networks --scoring Opus_Fork/runs/networks-scoring-<UTC>/scoring.json

Repaired before any network score existed (A3, Astra N1-N4). The pre-outcome version is sha256 f71a76b2... (commit
8ced1e5). Evaluations are read only through the scoring record, with their hashes checked. Controls, any failure of
which withholds every reading and exits 1:
- C1: the independent oracle, on its angles-based CIP path (A4), reproduces each fitted arm's URE, 3D, R/A/C and
  per-satellite 3D within 0.1 mm; malformed metrics are refused (NR-02). The series-based path is a reported,
  ungated cross-method diagnostic;
- C2: lin0 trajectories bitwise equal to V-op's where the satellite sets match;
- C3: the same oracle reproduction for NGA PE;
- C4: provenance: reference, NGA and EOP hashes, indexed solutions and fixtures (rehashed at use), day, window; each
  force model's identity with its campaign pin and record (A4, NR-03), then cross-arm comparability;
- C5: the reconstructed population has the evaluation's recorded digest and satellite list.
Also reported (N3): stations, observations and satellites per date and arm, the S17 site distances with the A1
substitution, and the A2 parity difference. Time shares below NGA use `ure_time_share.per_sample_ure`.

Writes `networks_analysis.json` in the run folder. No fit, no integration.
"""
import argparse
import json
import math
import numbers
from pathlib import Path
import sys

import numpy as np

from Opus_Fork.experiments.gradients.analyze_validation import ROOT, SCORE_TOL_M, key_digest, lin0_control
from Opus_Fork.experiments.gradients.ure_time_share import per_sample_ure
from Opus_Fork.experiments.networks.score_networks import MODELS, check_model_identity
from Opus_Fork.experiments.transfer.common import run_dir, sha
from validation.oracle import frame as O2, metrics as O1

HERE = ROOT/"Opus_Fork/experiments/networks"
INDEX = HERE/"scoring_index.json"
EOP = ROOT/"data/stage2/finals2000A.all"
DATES = ("2026-06-06", "2026-06-20", "2026-06-23", "2026-07-06", "2026-07-23")
ARMS = ("U", "V-op", "S17-op", "S50-op")
NETWORKS = ("S17-op", "S50-op")
GRADIENT_ARMS = ("V-op", "S17-op", "S50-op")
VARIANT = "erp+thrust+iiia2600+sdeop+elw13"
WINDOW = ["00:00", "23:45"]
PARITY = ROOT/"runs/20261007T215551Z-1e19cd4c/parity.json"
A1_SUBSTITUTION = dict(site="Hermitage, England", selected="HERS", fitted="BRUX", distance_km=404.5)
U_MAY_DIFFER = ("gradients", "elev_sha256")          # A3 §3, C4: the 1 Oct gradient hook only


class CachedFrame:
    """The oracle frame with its rotations memoized: identical values, each epoch computed once."""

    def __init__(self, frame):
        self.frame, self.cache = frame, {}

    def rotation(self, t):
        if t not in self.cache:
            self.cache[t] = self.frame.rotation(t)
        return self.cache[t]


def model_core(model):
    """A force model without the gradients entry's input list and module hash (the A2 normalization)."""
    core = dict(model)
    if "gradients" in core:
        core["gradients"] = {k: v for k, v in core["gradients"].items() if k not in ("inputs", "module_sha256")}
    return core


def check_force_models(models):
    """C4 force models: problems, empty when the arms differ only as designed (A3 §3)."""
    problems = [f"{arm}: variant {m.get('variant')}" for arm, m in models.items() if m.get("variant") != VARIANT]
    if len({json.dumps(m.get("subdaily_eop")) for m in models.values()}) != 1 or not models["V-op"].get("subdaily_eop"):
        problems.append("the sub-daily EOP models differ or are absent")
    reference = model_core(models["V-op"])
    for arm in GRADIENT_ARMS:
        if (models[arm].get("gradients") or {}).get("source") != "grad_op":
            problems.append(f"{arm}: gradients are not grad_op")
        elif model_core(models[arm]) != reference:
            problems.append(f"{arm}: force model differs from V-op's")
    if "gradients" in models["U"]:
        problems.append("U has gradients")
    differing = sorted(k for k in set(models["U"]) | set(reference) if models["U"].get(k) != reference.get(k))
    if set(differing)-set(U_MAY_DIFFER):
        problems.append(f"U: force model differs from V-op's in {differing}")
    return problems


def check_references(evaluation, find):
    """C4 reference files: each matches the hash the evaluation recorded and the store's entry for the day."""
    problems = []
    for role, key in (("reference_igs_final", "igs_final"), ("reference_nga_pe", "NGA")):
        recorded = evaluation["provenance"][key]
        if sha(recorded["path"]) != recorded["sha256"]:
            problems.append(f"{key}: file bytes differ from the evaluated ones")
        _, entry = find(role, evaluation["day"])
        if entry["sha256"] != recorded["sha256"]:
            problems.append(f"{key}: not the store's {role} for {evaluation['day']}")
    return problems


def check_population(keys, evaluation):
    """C5: the reconstructed keys are the evaluation's scored population by content, not only by count."""
    window = evaluation["domains"]["full"]
    problems = []
    if len(keys) != window["samples"] or key_digest(keys) != window.get("key_digest"):
        problems.append("reconstructed population differs from the scored one")
    if sorted({s for s, _ in keys}) != evaluation["satellites"]:
        problems.append("satellite list differs")
    return problems


def _rms(value):
    return isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _count(value):
    return isinstance(value, numbers.Integral) and not isinstance(value, bool) and value > 0


def malformed(production, oracle, per_satellite):
    """A4 §3 (Astra NR-02): every metric on both sides is a finite, nonnegative RMS, R/A/C has exactly three, sample
    counts are positive integers, and both sides cover the same satellites. Returns the problems found."""
    raw, problems = production.get("raw", {}), []
    sides = (("production", raw, "rms_orbit_ure_m"), ("oracle", oracle, "orbit_ure_m"))
    for side, row, ure in sides:
        if not (_rms(row.get(ure)) and _rms(row.get("rms_3d_m"))):
            problems.append(f"{side}: URE or 3D is not a finite nonnegative RMS")
        rac = row.get("rms_rac_m")
        if not (isinstance(rac, (list, tuple)) and len(rac) == 3 and all(_rms(v) for v in rac)):
            problems.append(f"{side}: R/A/C is not three finite nonnegative RMS values")
        if not _count(row.get("samples")):
            problems.append(f"{side}: sample count is not a positive integer")
    produced = production.get("per_satellite", {})
    if sorted(produced) != sorted(per_satellite):
        problems.append("production and oracle cover different satellites")
    for side, rows in (("production", produced), ("oracle", per_satellite)):
        for s, row in rows.items():
            if not (_rms(row.get("rms_3d_m")) and _count(row.get("samples"))):
                problems.append(f"{side} {s}: 3D is not a finite nonnegative RMS or the sample count is invalid")
    return problems


def score_difference(production, oracle, per_satellite):
    """(largest |oracle - production| in m over URE, 3D, R/A/C and each satellite's 3D, sample counts all equal,
    problems). Malformed metrics are refused: an infinite difference and the problems (A4 §3)."""
    problems = malformed(production, oracle, per_satellite)
    if problems:
        return math.inf, False, problems
    raw = production["raw"]
    diffs = [abs(oracle["orbit_ure_m"]-raw["rms_orbit_ure_m"]), abs(oracle["rms_3d_m"]-raw["rms_3d_m"])]
    diffs += [abs(a-b) for a, b in zip(oracle["rms_rac_m"], raw["rms_rac_m"])]
    equal = oracle["samples"] == raw["samples"]
    for s, o in per_satellite.items():
        p = production["per_satellite"][s]
        diffs.append(abs(o["rms_3d_m"]-p["rms_3d_m"]))
        equal = equal and o["samples"] == p["samples"]
    return float(max(diffs)), bool(equal), []


def s50_reading(changes):
    """A3 §5: the first matching rule, on unrounded values."""
    mean = float(np.mean(changes))
    if sum(c < 0 for c in changes) >= 4 and mean <= -1.0:
        return "improves"
    if -1.0 < mean < 1.0:
        return "no material change"
    if mean >= 1.0:
        return "worse"
    return "mixed"


def shares(u, u_nga, keys):
    epochs = sorted({t for _, t in keys})
    at = {t: [k for k in keys if k[1] == t] for t in epochs}
    lower = sum(np.sqrt(np.mean([u[k]**2 for k in at[t]])) < np.sqrt(np.mean([u_nga[k]**2 for k in at[t]])) for t in epochs)
    samples_lower = sum(u[k] < u_nga[k] for k in keys)
    return dict(epochs_lower=int(lower), epochs=len(epochs), epoch_share=lower/len(epochs),
                samples_lower=int(samples_lower), samples=len(keys), sample_share=samples_lower/len(keys))


def load_scoring(path):
    """{day: evaluation path} from the wrapper's record; refuses anything but a clean, current scoring run."""
    record = json.loads(Path(path).read_text())
    if record.get("status") != "analyzing" or record.get("preflight_problems"):
        raise ValueError(f"scoring record status {record.get('status')}")
    if record["index_sha256"] != sha(INDEX):
        raise ValueError("the scoring index changed since the evaluations")
    if record.get("models_sha256") != sha(MODELS) or json.loads(MODELS.read_text())["index_sha256"] != sha(INDEX):
        raise ValueError("the force-model sidecar changed since the evaluations or is not bound to the index")
    out = {}
    for day in DATES:
        e = record["evaluations"].get(day) or {}
        if e.get("problems") != [] or e.get("exit_code") != 0 or sha(e["output"]) != e["output_sha256"]:
            raise ValueError(f"{day}: evaluation not accepted or changed since")
        out[day] = Path(e["output"])
    return record, out


def solution(entry):
    path = ROOT/entry["campaign"]/entry["final"]/"solution.npz"
    with np.load(path) as f:
        return dict(path=path, states=f["states"][:, :, :3].copy(), sats=[str(s) for s in f["satellites"]],
                    times=f["times_s"].copy(), force_model=json.loads((path.parent/"force_model.json").read_text()))


def main():
    from Opus_Fork.store import find
    parser = argparse.ArgumentParser()
    parser.add_argument("--scoring", required=True)
    args = parser.parse_args()
    folder = run_dir()
    record, evaluations = load_scoring(args.scoring)
    index, models = json.loads(INDEX.read_text())["dates"], json.loads(MODELS.read_text())["dates"]
    finals = O2.Finals(EOP)
    frame = CachedFrame(O2.Frame(finals, subdaily=True, cip="angles"))     # A4 section 1: the strict C1/C3 path
    series = CachedFrame(O2.Frame(finals, subdaily=True))                  # cross-method diagnostic, not gated
    networks = json.loads((HERE/"networks.json").read_text())
    report = dict(protocol_sha256=sha(HERE/"PROTOCOL.md"), scoring=str(args.scoring), index_sha256=sha(INDEX),
                  wording="S17 = 17 selected IGS stations near the publicly described NGA and USAF monitor sites; "
                          "not NGA's data or estimator. IGS final is the reference, not truth. Exposed dates; "
                          "final-latency (gradient) arms; descriptive only.",
                  S17_sites=networks["S17"], S17_A1_substitution=A1_SUBSTITUTION,
                  S50_parity=dict(path=str(PARITY), sha256=sha(PARITY),
                                  **{k: json.loads(PARITY.read_text())[k] for k in
                                     ("max_position_difference_m", "rms_position_difference_m", "passed")}),
                  frames=dict(strict="validation.oracle frame, angles-based CIP (A4 section 1): C1, C3, time shares",
                              diagnostic="validation.oracle frame, series-based CIP (default): reported, not gated"),
                  dates={})
    controls_ok = True
    for day in DATES:
        path = evaluations[day]
        evaluation = json.loads(path.read_text())
        arms, entries = evaluation["domains"]["full"]["arms"], index[day]
        c4 = []
        if evaluation["day"] != day or evaluation["domains"]["full"]["window"] != WINDOW:
            c4.append("day or window")
        c4 += check_references(evaluation, find)
        eop = evaluation.get("earth_orientation_input", {}).get("sha256")
        if not (eop == record["eop_sha256_before"] == record["eop_sha256_after"] == sha(EOP)):
            c4.append("Earth-orientation file differs from the evaluated one")
        solutions, ecefs, series_ecefs, fixtures, orientation = {}, {}, {}, {}, set()
        for arm in ARMS:
            p, e = evaluation["provenance"][arm], entries[arm]
            s = solutions[arm] = solution(e)
            if not (p["sha256"] == e["solution_sha256"] == sha(s["path"]) and p["fixture_sha256"] == e["fixture_sha256"]
                    and Path(p["solution"]).resolve() == s["path"].resolve() and p["status"] == "converged"):
                c4.append(f"{arm}: evaluated solution or fixture is not the indexed one")
            expected_model = models[day][arm]["sha256"]                       # A4 §4: identity before normalization
            c4 += [f"{arm}: {problem}" for problem in check_model_identity(e, expected_model)]
            if p.get("force_model_sha256") != expected_model:
                c4.append(f"{arm}: evaluated force model is not the expected one")
            if sha(ROOT/e["fixture"]) != e["fixture_sha256"]:
                c4.append(f"{arm}: fixture changed since it was indexed")
            orientation.add(p["earth_orientation"])
            fixture = json.loads((ROOT/e["fixture"]).read_text())
            fixtures[arm] = dict(origin=int(fixture["context"]["origin_ns"]), stations=sorted(fixture["context"]["stations"]),
                                 observations=len(fixture["rows"]))
            ecefs[arm] = O1.solution_ecef(s["states"], s["sats"], s["times"], fixtures[arm]["origin"], frame)
            series_ecefs[arm] = O1.solution_ecef(s["states"], s["sats"], s["times"], fixtures[arm]["origin"], series)
        if len(orientation) != 1:
            c4.append(f"Earth-orientation models differ: {sorted(orientation)}")
        c4 += check_force_models({arm: solutions[arm]["force_model"] for arm in ARMS})
        if len({f["origin"] for f in fixtures.values()}) != 1:
            c4.append("fixture origins differ")
        reference = O1.read_sp3(evaluation["provenance"]["igs_final"]["path"])
        nga = O1.read_sp3(evaluation["provenance"]["NGA"]["path"])
        origin = fixtures["V-op"]["origin"]
        start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
        keys = {k for k in set(reference) & set(nga) if start <= k[1] <= stop}
        for ecef in ecefs.values():
            keys &= set(ecef)
        c5 = check_population(keys, evaluation)
        sats = sorted({s for s, _ in keys})
        by_sat = {s: {k for k in keys if k[0] == s} for s in sats}

        def oracle(candidate, production, used=frame):
            whole = O1.summarize(reference, candidate, used, keys)
            each = {s: O1.summarize(reference, candidate, used, by_sat[s]) for s in sats}
            return whole, score_difference(production, whole, each)

        def cross_method(candidate, production):
            _, (difference, equal, bad) = oracle(candidate, production, series)
            return dict(difference_m=difference, samples_equal=equal, malformed=bad, gated=False)

        u_nga = per_sample_ure(reference, nga, frame, keys)
        nga_oracle, (nga_diff, nga_equal, nga_bad) = oracle(nga, arms["NGA"])
        nga_raw = arms["NGA"]["raw"]
        entry = dict(evaluation=str(path), evaluation_sha256=sha(path), common_keys=len(keys),
                     common_key_digest=key_digest(keys), satellites_scored=len(sats),
                     C4_problems=c4, C5_problems=c5,
                     NGA=dict(ure_cm=nga_raw["rms_orbit_ure_m"]*100, d3_cm=nga_raw["rms_3d_m"]*100,
                              rac_cm=[x*100 for x in nga_raw["rms_rac_m"]], oracle_ure_cm=nga_oracle["orbit_ure_m"]*100,
                              C3_oracle_difference_m=nga_diff, C3_samples_equal=nga_equal, C3_malformed=nga_bad,
                              series_cross_method=cross_method(nga, arms["NGA"])),
                     u_model_fields_differing_from_vop=sorted(
                         k for k in set(solutions["U"]["force_model"]) | set(solutions["V-op"]["force_model"])
                         if solutions["U"]["force_model"].get(k) != solutions["V-op"]["force_model"].get(k)),
                     arms={})
        ok = not c4 and not c5 and nga_diff <= SCORE_TOL_M and nga_equal
        base = arms["V-op"]
        for arm in ARMS:
            raw = arms[arm]["raw"]
            whole, (diff, equal, bad) = oracle(ecefs[arm], arms[arm])
            u = per_sample_ure(reference, ecefs[arm], frame, keys)
            row = dict(campaign=entries[arm]["campaign"].split("/")[-1], final=entries[arm]["final"],
                       stations=len(fixtures[arm]["stations"]), observations=fixtures[arm]["observations"],
                       solution_satellites=len(solutions[arm]["sats"]),
                       ure_cm=raw["rms_orbit_ure_m"]*100, d3_cm=raw["rms_3d_m"]*100, rac_cm=[x*100 for x in raw["rms_rac_m"]],
                       oracle_ure_cm=whole["orbit_ure_m"]*100, oracle_d3_cm=whole["rms_3d_m"]*100,
                       ure_ratio_to_nga=raw["rms_orbit_ure_m"]/nga_raw["rms_orbit_ure_m"],
                       d3_ratio_to_nga=raw["rms_3d_m"]/nga_raw["rms_3d_m"],
                       C1_oracle_difference_m=diff, C1_samples_equal=equal, C1_malformed=bad,
                       series_cross_method=cross_method(series_ecefs[arm], arms[arm]),
                       time_share_below_nga=shares(u, u_nga, keys))
            if arm in NETWORKS:
                row["station_list"] = fixtures[arm]["stations"]
            if arm != "V-op":
                per_a, per_b = arms[arm]["per_satellite"], base["per_satellite"]
                increases = sorted((per_a[s]["rms_3d_m"]-per_b[s]["rms_3d_m"], s) for s in per_b if s in per_a)
                row.update(ure_change_vs_vop_pct=100*(raw["rms_orbit_ure_m"]/base["raw"]["rms_orbit_ure_m"]-1),
                           d3_change_vs_vop_pct=100*(raw["rms_3d_m"]/base["raw"]["rms_3d_m"]-1),
                           radial_change_vs_vop_pct=100*(raw["rms_rac_m"][0]/base["raw"]["rms_rac_m"][0]-1),
                           worst_satellite_3d_increase_vs_vop_m=increases[-1][0], worst_satellite=increases[-1][1])
            if arm in NETWORKS:
                same = sorted(solutions[arm]["sats"]) == sorted(solutions["V-op"]["sats"])
                row["C2_lin0_bitwise"] = lin0_control(ROOT/entries[arm]["campaign"], ROOT/entries["V-op"]["campaign"]) \
                    if same else "not applicable (satellite sets differ)"
                if same and not all(row["C2_lin0_bitwise"].values()):
                    ok = False
            if not (diff <= SCORE_TOL_M and equal):
                ok = False
            entry["arms"][arm] = row
        entry["controls_pass"] = ok
        controls_ok = controls_ok and ok
        report["dates"][day] = entry
        print(day, "controls", "pass" if ok else "FAIL", flush=True)

    def collect(arm, field):
        return [report["dates"][d]["arms"][arm][field] for d in DATES]
    report["controls_pass"] = controls_ok
    withheld = "not read (a control failed)"
    s17_ratios = collect("S17-op", "ure_ratio_to_nga")
    s50_changes = collect("S50-op", "ure_change_vs_vop_pct")
    report["S17"] = dict(ure_ratios_to_nga=s17_ratios, dates_below_nga=sum(r < 1 for r in s17_ratios),
                         mean_ure_ratio_to_nga=float(np.mean(s17_ratios)),
                         ure_changes_vs_vop_pct=collect("S17-op", "ure_change_vs_vop_pct"),
                         mean_ure_change_vs_vop_pct=float(np.mean(collect("S17-op", "ure_change_vs_vop_pct"))),
                         reading="descriptive (PROTOCOL.md §6)" if controls_ok else withheld)
    report["S50"] = dict(ure_changes_vs_vop_pct=s50_changes, dates_better=sum(c < 0 for c in s50_changes),
                         mean_ure_change_vs_vop_pct=float(np.mean(s50_changes)),
                         mean_3d_change_vs_vop_pct=float(np.mean(collect("S50-op", "d3_change_vs_vop_pct"))),
                         worst_satellite_3d_increase_m=max(collect("S50-op", "worst_satellite_3d_increase_vs_vop_m")),
                         worst_radial_change_pct=max(collect("S50-op", "radial_change_vs_vop_pct")),
                         reading=s50_reading(s50_changes) if controls_ok else withheld)
    pooled = {}
    for arm in ARMS:
        ts = [report["dates"][d]["arms"][arm]["time_share_below_nga"] for d in DATES]
        pooled[arm] = dict(epoch_share=sum(t["epochs_lower"] for t in ts)/sum(t["epochs"] for t in ts),
                           sample_share=sum(t["samples_lower"] for t in ts)/sum(t["samples"] for t in ts),
                           mean_ure_ratio_to_nga=float(np.mean(collect(arm, "ure_ratio_to_nga"))),
                           mean_ure_cm=float(np.mean(collect(arm, "ure_cm"))))
    report["pooled"] = pooled
    report["NGA_mean_ure_cm"] = float(np.mean([report["dates"][d]["NGA"]["ure_cm"] for d in DATES]))
    (folder/"networks_analysis.json").write_text(json.dumps(report, indent=1, default=float)+"\n")
    print(json.dumps(dict(controls=controls_ok, S17=report["S17"]["reading"], S50=report["S50"]["reading"]),
                     default=float), flush=True)
    if not controls_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
