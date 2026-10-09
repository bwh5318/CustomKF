"""Do weakly determined ambiguity arcs predict which satellites go wrong along-track?

    python -m Opus_Fork.guard --profile fork8 --timeout 900 --label ambiguity-health -- Opus_Fork.ambiguity_health

The measured failure is an along-track runaway confined to the last third of the 24 h arc,
on G21 above all (`results/BASELINE.md`). The proposed mechanism is that a float
ionosphere-free ambiguity on a short, late arc is barely separable from the satellite's
own orbit and force parameters, so it absorbs along-track error instead of fixing it.

That is testable from the archive alone, with no fit. The saved solution carries the
retained covariance over all 1694 non-clock parameters, of which 1172 are ambiguities. For
each ambiguity `a` and each orbit or force parameter `p` of the same satellite, the
conditional shift in `p` for a unit error in `a` is `C[p,a]/C[a,a]`. Scaling by the
narrow-lane wavelength, 10.695 cm, gives the orbit shift that one unresolved cycle would
produce: a leverage in the parameter's own units.

Summed in quadrature over a satellite's ambiguities, that is a per-satellite
ambiguity-borne uncertainty. **The prediction is that this ranking matches the along-track
error ranking.** If it does not, the mechanism is wrong and the arc-end plan needs
rethinking; that outcome is recorded either way.

Leverage on initial velocity and on the SRP coefficients is also converted to an
order-of-magnitude along-track displacement at 21 h, using the standard along-track
responses to a velocity change and to a constant acceleration. Those two factors are
approximate by construction and are labelled as indicative, not as a propagated covariance.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.prepare_stage2 import sha

from .baseline import BEST_FIXTURE, BEST_SOLUTION
from .blocks import satellite_blocks, group
from .paths import ROOT, RESULTS

NARROW_LANE_M = 0.10695            # c / (f1 + f2)
HORIZON_S = 21*3600.               # where the measured runaway peaks
SRP_SCALE = 1e-7                   # customkf.orbit_forces.parameter_scales
FORCES = ("srpD0", "srpY0", "srpB0", "srpBc1", "srpBs1")


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    f = np.load(BEST_SOLUTION)
    names = [str(s) for s in f["names"]]
    retained = [n for n in names if not n.startswith("clock")]
    cov = f["retained_covariance"]
    if cov.shape != (len(retained), len(retained)):
        raise ValueError("Retained covariance does not match the non-clock parameter list")
    index = {n: i for i, n in enumerate(retained)}
    variance = np.diag(cov)
    if not np.all(variance > 0):
        raise ValueError("Non-positive formal variance in the retained covariance")

    fixture = json.loads(Path(BEST_FIXTURE).read_text())
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(fixture["context"]["day"]).items()}
    epoch_count = fixture["context"]["epoch_count"]

    # Phase rows carry the small sigma; code rows the large one. Arc geometry comes from
    # the phase rows, because only those carry an ambiguity.
    arcs = {}
    for row in fixture["rows"]:
        if row["sigma"][1] > row["sigma"][0]:
            raise ValueError("Unexpected sigma ordering")
        a = arcs.setdefault(row["arc"], {"epochs": [], "station": row["station"], "satellite": row["satellite"]})
        a["epochs"].append(row["epoch"])

    rows, per_satellite = [], {}
    for name in retained:
        if not name.startswith("amb:"):
            continue
        _, station, sat, arc_id = name.split(":")
        arc = arcs.get(f"{station}:{sat}:{arc_id}")
        if arc is None:
            raise ValueError("Ambiguity without a fixture arc: "+name)
        epochs = sorted(set(arc["epochs"]))
        ai = index[name]
        sigma_a = float(np.sqrt(variance[ai]))
        leverage = {}
        for k, component in enumerate("xyzXYZ"):
            key = f"orbit:{sat}:{k}"
            if key in index:
                leverage[component] = float(cov[index[key], ai]/variance[ai]*NARROW_LANE_M)
        for force in FORCES:
            key = f"{force}:{sat}"
            if key in index:
                leverage[force] = float(cov[index[key], ai]/variance[ai]*NARROW_LANE_M)
        position_m = float(np.linalg.norm([leverage.get(c, 0.) for c in "xyz"]))
        velocity_mps = float(np.linalg.norm([leverage.get(c, 0.) for c in "XYZ"]))
        force_mps2 = float(np.linalg.norm([leverage.get(k, 0.) for k in FORCES]))*SRP_SCALE
        # Indicative along-track responses: 3*dv*t for a velocity change (semi-major axis
        # coupling) and 1.5*a*t^2 for a constant acceleration. Order of magnitude only.
        indicative = position_m + 3*velocity_mps*HORIZON_S + 1.5*force_mps2*HORIZON_S**2
        entry = dict(name=name, station=station, satellite=sat, block=blocks.get(sat),
                     phase_epochs=len(epochs), first_epoch=min(epochs), last_epoch=max(epochs),
                     span_epochs=max(epochs)-min(epochs)+1,
                     starts_in_last_third=min(epochs) >= 2*epoch_count//3,
                     sigma_m=sigma_a, leverage_position_m=position_m,
                     leverage_velocity_mps=velocity_mps, leverage_force_mps2=force_mps2,
                     indicative_along_at_21h_m=indicative)
        rows.append(entry)
        acc = per_satellite.setdefault(sat, dict(satellite=sat, block=blocks.get(sat), arcs=0,
                                                 short_arcs=0, late_arcs=0, late_short_arcs=0,
                                                 sum_sq=0., worst=None))
        acc["arcs"] += 1
        acc["short_arcs"] += entry["phase_epochs"] <= 6
        acc["late_arcs"] += entry["starts_in_last_third"]
        acc["late_short_arcs"] += entry["starts_in_last_third"] and entry["phase_epochs"] <= 6
        acc["sum_sq"] += indicative**2
        if acc["worst"] is None or indicative > acc["worst"]["indicative_along_at_21h_m"]:
            acc["worst"] = entry

    for acc in per_satellite.values():
        acc["ambiguity_borne_m"] = float(np.sqrt(acc["sum_sq"]))
        del acc["sum_sq"]

    # Measured along-track RMS from the baseline run, for the rank correlation.
    measured = {}
    baseline = RESULTS/"baseline_nga_vs_igs_final.json"
    if baseline.exists():
        per = json.loads(baseline.read_text())["comparisons"]["our_fit_vs_igs_final"]["per_satellite"]
        measured = {s: abs(v["rms_rac_m"][1]) for s, v in per.items()}

    ranking = sorted(per_satellite.values(), key=lambda a: -a["ambiguity_borne_m"])
    spearman = None
    if measured:
        shared = [a["satellite"] for a in ranking if a["satellite"] in measured]
        predicted = np.array([per_satellite[s]["ambiguity_borne_m"] for s in shared])
        actual = np.array([measured[s] for s in shared])
        pr = np.argsort(np.argsort(predicted))
        ar = np.argsort(np.argsort(actual))
        spearman = float(np.corrcoef(pr, ar)[0, 1])

    by_length = {}
    for entry in rows:
        bucket = "1-3" if entry["phase_epochs"] <= 3 else "4-6" if entry["phase_epochs"] <= 6 else \
                 "7-20" if entry["phase_epochs"] <= 20 else "21+"
        b = by_length.setdefault(bucket, dict(count=0, sigma=[], indicative=[]))
        b["count"] += 1
        b["sigma"].append(entry["sigma_m"])
        b["indicative"].append(entry["indicative_along_at_21h_m"])
    for b in by_length.values():
        b["median_sigma_m"] = float(np.median(b.pop("sigma")))
        b["median_indicative_m"] = float(np.median(b.pop("indicative")))

    report = dict(status="ambiguity_health_diagnostic_not_accuracy_acceptance",
                  inputs=dict(solution=sha(BEST_SOLUTION), fixture=sha(BEST_FIXTURE)),
                  narrow_lane_m=NARROW_LANE_M, horizon_s=HORIZON_S,
                  caveat="Leverage is exact from the saved covariance. The conversion to an "
                         "along-track displacement uses approximate orbital responses and is "
                         "indicative only; it is not a propagated covariance.",
                  ambiguities=len(rows), by_arc_length=by_length,
                  spearman_predicted_vs_measured_along=spearman,
                  per_satellite={a["satellite"]: a for a in ranking},
                  worst_arcs=sorted(rows, key=lambda e: -e["indicative_along_at_21h_m"])[:25])
    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"ambiguity_health.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"ambiguity_health.json").write_text(text)

    print(f"{len(rows)} ambiguities over {len(per_satellite)} satellites\n")
    print("by arc length (phase epochs):")
    print(f"  {'bucket':8s} {'count':>6s} {'median sigma':>13s} {'median indicative along @21h':>30s}")
    for bucket in ("1-3", "4-6", "7-20", "21+"):
        b = by_length.get(bucket)
        if b:
            print(f"  {bucket:8s} {b['count']:6d} {b['median_sigma_m']*100:11.2f} cm {b['median_indicative_m']*100:27.2f} cm")
    print(f"\nrank correlation, predicted ambiguity-borne vs measured along-track RMS: {spearman:.3f}"
          if spearman is not None else "")
    print(f"\n{'sat':5s} {'blk':6s} {'arcs':>5s} {'short':>6s} {'late':>5s} {'late&short':>10s} "
          f"{'amb-borne':>10s} {'measured A':>11s}  worst arc")
    print("-"*104)
    for a in ranking:
        m = measured.get(a["satellite"])
        w = a["worst"]
        print(f"{a['satellite']:5s} {str(a['block']):6s} {a['arcs']:5d} {a['short_arcs']:6d} {a['late_arcs']:5d} "
              f"{a['late_short_arcs']:10d} {a['ambiguity_borne_m']*100:9.1f}c "
              f"{(m*100 if m else float('nan')):10.2f}c  {w['name']} "
              f"({w['phase_epochs']}ep, e{w['first_epoch']}-{w['last_epoch']}, {w['indicative_along_at_21h_m']*100:.1f}cm)")
    print("\nWrote "+str(out/"ambiguity_health.json"))


if __name__ == "__main__":
    main()
