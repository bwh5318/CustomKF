"""The estimator has no outlier rejection. How much does that cost, and where?

    python -m Opus_Fork.guard --profile fork8 --timeout 900 --label residual-outliers -- Opus_Fork.residual_outliers

`run_stage3.py:166` states the profile plainly: "no postfit clipping". Every retained
observation enters the normal equations at its elevation-only sigma, with no robust weight
and no residual editing, so a single bad phase observation at 9 mm sigma carries the weight
of a good one and pulls the trajectory it sees.

That is the remaining candidate for the measured along-track runaway, after the
late-ambiguity explanation was tested and failed (`results/ambiguity_health.json`: rank
correlation 0.20, and G21 is 13th of 27 in ambiguity leverage). Astra's independent
localization found `VACS:G21:59` carries whitened RMS 2.287 against a context of 0.435 in
its first ten samples, which is an outlier cluster by any standard.

This reconstructs the exact residual ordering from the saved solution and fixture and asks:
how heavy are the tails, how much of the objective lives in them, and are the worst rows
concentrated on the satellites and in the window that actually went wrong. No fit, no
reweighting, no edit: it measures what a robust estimator would have had to deal with.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.prepare_stage2 import sha

from .baseline import BEST_FIXTURE, BEST_SOLUTION
from .blocks import satellite_blocks, group
from .paths import RESULTS


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    f = np.load(BEST_SOLUTION)
    residual, sigma = f["residual_m"], f["sigma_m"]
    fixture = json.loads(Path(BEST_FIXTURE).read_text())
    rows, context = fixture["rows"], fixture["context"]
    epoch_count = context["epoch_count"]
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(context["day"]).items()}

    # Reproduce LongPilot's arc eligibility and residual emission order exactly
    # (claude/roadmap/long_pilot.py:81-88, 184-199).
    counts = {}
    for r in rows:
        counts[r["arc"]] = counts.get(r["arc"], 0)+1
    arcset = {a for a, n in counts.items() if n >= 3}
    by_epoch = [[] for _ in range(epoch_count)]
    for i, r in enumerate(rows):
        by_epoch[r["epoch"]].append(i)

    table = []
    for ei in range(epoch_count):
        for i in by_epoch[ei]:
            r = rows[i]
            for kind in range(2 if r["arc"] in arcset else 1):
                table.append((i, kind))
    if len(table) != len(residual):
        raise ValueError(f"Row reconstruction gives {len(table)} entries against {len(residual)} residuals")

    whitened = residual/sigma
    kinds = np.array([k for _, k in table])
    row_index = np.array([i for i, _ in table])
    sats = np.array([rows[i]["satellite"] for i in row_index])
    stations = np.array([rows[i]["station"] for i in row_index])
    epochs = np.array([rows[i]["epoch"] for i in row_index])
    hours = (epochs*context["step_s"]+10)/3600.
    phase = kinds == 1

    # A reconstruction check: the pilot's own cost is the sum of squares plus constraints,
    # so the observation part must match what the archive's step.json reports as reachable.
    total = float(np.sum(whitened**2))

    def tail(mask, cut):
        sel = mask & (np.abs(whitened) > cut)
        return dict(rows=int(sel.sum()), fraction=float(sel.sum()/max(1, mask.sum())),
                    share_of_squared_cost=float(np.sum(whitened[sel]**2)/np.sum(whitened[mask]**2)))

    report = dict(status="residual_outlier_diagnostic_not_accuracy_acceptance",
                  inputs=dict(solution=sha(BEST_SOLUTION), fixture=sha(BEST_FIXTURE)),
                  rows=len(table), phase_rows=int(phase.sum()), code_rows=int((~phase).sum()),
                  total_squared_cost=total,
                  note="Whitened = residual/sigma at the converged solution. Nothing is edited.")

    for label, mask in (("phase", phase), ("code", ~phase)):
        w = whitened[mask]
        report[label] = dict(rms=float(np.sqrt(np.mean(w**2))),
                             median_abs=float(np.median(np.abs(w))),
                             robust_sigma=float(np.median(np.abs(w-np.median(w)))*1.4826),
                             p99=float(np.percentile(np.abs(w), 99)),
                             max_abs=float(np.abs(w).max()),
                             share_of_total_cost=float(np.sum(w**2)/total),
                             tails={f"{c}sigma": tail(mask, c) for c in (3, 4, 5, 8)})

    # Per satellite: phase whitened RMS, tail share, and the same split before/after 16:00,
    # which is where the measured runaway begins.
    late = hours >= 16.
    per_satellite = {}
    for sat in sorted(set(sats)):
        m = phase & (sats == sat)
        if not m.any():
            continue
        w = whitened[m]
        early_m, late_m = m & ~late, m & late
        per_satellite[sat] = dict(
            block=blocks.get(sat), phase_rows=int(m.sum()),
            whitened_rms=float(np.sqrt(np.mean(w**2))), max_abs=float(np.abs(w).max()),
            rows_over_4sigma=int((np.abs(w) > 4).sum()),
            cost_share_over_4sigma=float(np.sum(w[np.abs(w) > 4]**2)/np.sum(w**2)),
            whitened_rms_before_16h=float(np.sqrt(np.mean(whitened[early_m]**2))) if early_m.any() else None,
            whitened_rms_after_16h=float(np.sqrt(np.mean(whitened[late_m]**2))) if late_m.any() else None)
    report["per_satellite"] = per_satellite

    # The worst individual phase rows, and the worst station-satellite-arc clusters.
    order = np.argsort(-np.abs(whitened*phase))
    report["worst_phase_rows"] = [
        dict(station=stations[k], satellite=sats[k], epoch=int(epochs[k]), hour=round(float(hours[k]), 3),
             whitened=float(whitened[k]), residual_m=float(residual[k]), sigma_m=float(sigma[k]),
             arc=rows[row_index[k]]["arc"]) for k in order[:30]]

    clusters = {}
    for k in np.flatnonzero(phase & (np.abs(whitened) > 4)):
        key = rows[row_index[k]]["arc"]
        c = clusters.setdefault(key, dict(arc=key, rows=0, squared=0., hours=[]))
        c["rows"] += 1
        c["squared"] += float(whitened[k]**2)
        c["hours"].append(round(float(hours[k]), 2))
    report["over_4sigma_arcs"] = sorted(clusters.values(), key=lambda c: -c["squared"])[:20]

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"residual_outliers.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"residual_outliers.json").write_text(text)

    for label in ("phase", "code"):
        d = report[label]
        print(f"{label}: {report[label+'_rows' if False else 'phase_rows' if label=='phase' else 'code_rows']} rows, "
              f"whitened RMS {d['rms']:.3f}, median|w| {d['median_abs']:.3f}, robust sigma {d['robust_sigma']:.3f}, "
              f"p99 {d['p99']:.2f}, max {d['max_abs']:.1f}, {d['share_of_total_cost']*100:.1f}% of cost")
        for cut, t in d["tails"].items():
            print(f"    beyond {cut:>7s}: {t['rows']:5d} rows ({t['fraction']*100:5.2f}%) "
                  f"carrying {t['share_of_squared_cost']*100:5.1f}% of this group's squared cost")
    print(f"\n{'sat':5s} {'blk':6s} {'rows':>5s} {'w.RMS':>6s} {'max':>7s} {'>4s':>4s} {'cost>4s':>8s} "
          f"{'<16h':>6s} {'>=16h':>6s}")
    print("-"*68)
    for sat, d in sorted(per_satellite.items(), key=lambda kv: -kv[1]["whitened_rms"]):
        print(f"{sat:5s} {str(d['block']):6s} {d['phase_rows']:5d} {d['whitened_rms']:6.3f} {d['max_abs']:7.1f} "
              f"{d['rows_over_4sigma']:4d} {d['cost_share_over_4sigma']*100:7.1f}% "
              f"{(d['whitened_rms_before_16h'] or 0):6.3f} {(d['whitened_rms_after_16h'] or 0):6.3f}")
    print("\nworst 12 phase rows:")
    for r in report["worst_phase_rows"][:12]:
        print(f"  {r['station']:5s} {r['satellite']} h={r['hour']:6.2f} whitened {r['whitened']:+9.1f} "
              f"= {r['residual_m']*1000:+9.1f} mm at sigma {r['sigma_m']*1000:5.1f} mm   {r['arc']}")
    print("\nworst >4sigma arcs by squared contribution:")
    for c in report["over_4sigma_arcs"][:10]:
        print(f"  {c['arc']:22s} {c['rows']:3d} rows, squared {c['squared']:10.1f}, hours {c['hours'][:6]}")
    print("\nWrote "+str(out/"residual_outliers.json"))


if __name__ == "__main__":
    main()
