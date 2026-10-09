"""Build a re-weighted fixture: variance components per station, elevation and time window.

    python -m Opus_Fork.guard --profile fork8 --timeout 900 --label reweight -- Opus_Fork.reweight \
        --fixture DIR --solution DIR --arm W1 --out DIR

PREDECLARED BEFORE ANY RESULT WAS SEEN (19 September 2026). `results/DIAGNOSIS.md` establishes
that the single frozen law, phase sigma = 9 mm/sin(el) for every station, satellite and hour,
misstates the observed scatter three ways: the pooled whitened RMS is 0.461, the elevation
slope is too shallow, and station quality varies 2.9x between stations and a further 2x within
a station across the day. Relative weights are therefore wrong, and the satellites that fail
are the ones the over-weighted stations track late.

This estimates the error model from the observed residual scatter and writes a new fixture
with corrected sigmas. **No estimator code changes**: sigma is a fixture field, so the
unmodified `LongPilot` fits the reweighted problem.

Two arms, differing only in whether the station scale may vary within the day:

  W1  global elevation law + one scale per station, constant over the day
  W2  W1 plus a scale per station per 3-hour window

W1 transfers to another day, because station quality is a property of the site; W2 captures
within-day variation that only a same-day estimate can see. Comparing them says which matters.

**Why this is not tuning against a score.** The estimate uses only postfit residual scatter.
No reference orbit, no IGS or NGA product, and no accuracy score enters. It is an empirical
residual-reweighting heuristic with declared groups (shrunk grouped residual scales). It is **not** formal Helmert
variance-component estimation: it ignores the residual-maker matrix (Cov(r) = (I-H)Σ(I-H)^T), the leverage of clocks,
wet delays, orbits and forces, and residual correlation (corrected 28 Sep 2026, Astra review M05).

**Why groups, not individual residuals.** Down-weighting an observation because *it*
disagrees with the current orbit reinforces that orbit. Down-weighting a *group* because the
group's scatter is large estimates a variance instead, which does not select agreeable data.
That is why there is no per-observation robust weight here.

Declared before running: group scales are shrunk toward 1 as
`k^2 = (n*s^2 + NU) / (n + NU)` with **NU = 20**, so thin groups cannot swing far; the
elevation law is fitted once globally over all stations; code and phase are modelled
separately; and no row is deleted or excluded by any arm.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np

from customkf.prepare_stage2 import ROOT, sha

from .paths import RESULTS
from .store import resolve

NU = 20.0                  # shrinkage pseudo-count for a group scale
WINDOW_H = 3.0             # W2 time-window width
MIN_SIGMA_SCALE = 0.25     # never claim a group is more than 4x better than the nominal law
MAX_SIGMA_SCALE = 8.0      # nor more than 8x worse; both bounds are declared, not fitted


def residual_table(fixture, solution):
    """Reproduce LongPilot's residual emission order (long_pilot.py:81-88, 184-199)."""
    rows, context = fixture["rows"], fixture["context"]
    epoch_count = context["epoch_count"]
    counts = {}
    for r in rows:
        counts[r["arc"]] = counts.get(r["arc"], 0)+1
    arcset = {a for a, n in counts.items() if n >= 3}
    by_epoch = [[] for _ in range(epoch_count)]
    for i, r in enumerate(rows):
        by_epoch[r["epoch"]].append(i)
    table = [(i, kind) for ei in range(epoch_count) for i in by_epoch[ei]
             for kind in range(2 if rows[i]["arc"] in arcset else 1)]
    if len(table) != len(solution["residual_m"]):
        raise ValueError(f"Row reconstruction gives {len(table)} entries against "
                         f"{len(solution['residual_m'])} residuals")
    return table, arcset


def elevation_of(sigma_phase):
    """The frozen profile is sigma_phase = 9 mm / sin(el), so elevation inverts exactly."""
    return np.arcsin(np.clip(0.009/np.asarray(sigma_phase), 1e-6, 1.0))


def fit_elevation_law(residual, elevation, bins=12):
    """Robust fit of sigma(el) = sqrt(a^2 + b^2 / sin(el)^(2p)).

    The predeclared form fixed p = 1. On the first run that hit its non-negativity
    boundary: the least-squares solution wanted a^2 < 0, because `a^2 + b^2/sin^2` can only
    be *flatter* than 1/sin and the observed scatter is steeper (the 60-90 degree band
    implies about 3.1 mm against 19.9 mm at 10-20 degrees, a ratio of 6.4 where 1/sin gives
    3.7). Freeing the exponent is a change of functional form made **after** seeing residual
    scatter and **before** any orbit was refitted; it is still estimated from scatter alone,
    with no reference product or accuracy score involved. Fixing p = 1 is kept available so
    the original declaration can still be run.

    Bin-wise robust sigma (median absolute deviation, 1.4826) keeps the fit off the tails,
    then p and b come from a log-log regression and a is recovered from the high-elevation
    bins where the constant term is resolvable.
    """
    sine = np.sin(elevation)
    edges = np.quantile(sine, np.linspace(0, 1, bins+1))
    edges = np.unique(edges)
    centres, sigmas, counts = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (sine >= lo) & (sine <= hi if hi == edges[-1] else sine < hi)
        if m.sum() < 30:
            continue
        r = residual[m]
        centres.append(float(np.median(sine[m])))
        sigmas.append(float(np.median(np.abs(r-np.median(r)))*1.4826))
        counts.append(int(m.sum()))
    centres, sigmas, counts = np.array(centres), np.array(sigmas), np.array(counts)
    if len(centres) < 3 or not np.all(sigmas > 0):
        raise ValueError("Too few usable elevation bins to fit an error model")
    slope, intercept = np.polyfit(np.log(1/centres), np.log(sigmas), 1, w=np.sqrt(counts))
    p = float(np.clip(slope, 0.5, 3.0))
    b = float(np.exp(intercept))
    # a absorbs whatever the power law leaves at the top of the elevation range.
    top = centres >= np.median(centres)
    left = sigmas[top]**2 - (b/centres[top]**p)**2
    a = float(np.sqrt(max(0.0, float(np.average(left, weights=counts[top])))))
    return a, b, p, dict(bin_sine=centres.tolist(), bin_sigma_m=sigmas.tolist(),
                         bin_rows=counts.tolist(), fitted_exponent=p,
                         predeclared_exponent_1_available=True)


def group_scales(residual, model_sigma, keys):
    """Shrunk variance-component scale per declared group."""
    scales, detail = {}, {}
    ratio = (residual/model_sigma)**2
    for key in sorted(set(keys)):
        m = np.asarray(keys) == key
        n = int(m.sum())
        s2 = float(np.mean(ratio[m]))
        shrunk = (n*s2+NU)/(n+NU)
        k = float(np.clip(np.sqrt(shrunk), MIN_SIGMA_SCALE, MAX_SIGMA_SCALE))
        scales[key] = k
        detail[key] = dict(rows=n, raw_variance_ratio=s2, shrunk_scale=k)
    return scales, detail


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, help="prepared directory holding fixture.json/step.json")
    parser.add_argument("--solution", required=True, help="converged solve directory whose residuals calibrate the model")
    parser.add_argument("--arm", choices=("W1", "W2"), required=True)
    parser.add_argument("--out", required=True, help="new prepared directory to create")
    args = parser.parse_args()
    run_dir = Path(os.environ["CUSTOMKF_RUN_DIR"])

    prep = resolve(args.fixture)
    meta = json.loads((prep/"step.json").read_text())
    fixture_path = prep/"fixture.json"
    if meta["status"] != "prepared" or sha(fixture_path) != meta["fixture_sha256"]:
        raise ValueError("Source fixture is not a verified prepared directory")
    solution_dir = resolve(args.solution)
    solution_path = solution_dir/"solution.npz" if solution_dir.is_dir() else solution_dir
    step = json.loads((solution_path.parent/"step.json").read_text())
    if step["status"] != "converged" or sha(solution_path) != step["solution_sha256"]:
        raise ValueError("Calibrating solution is not a verified converged checkpoint")

    fixture = json.loads(fixture_path.read_text())
    with np.load(solution_path) as data:
        solution = {"residual_m": data["residual_m"].copy(), "sigma_m": data["sigma_m"].copy()}
    table, arcset = residual_table(fixture, solution)
    rows = fixture["rows"]
    residual, sigma = solution["residual_m"], solution["sigma_m"]
    kinds = np.array([k for _, k in table])
    idx = np.array([i for i, _ in table])
    stations = np.array([rows[i]["station"] for i in idx])
    hours = np.array([(rows[i]["epoch"]*fixture["context"]["step_s"]+10)/3600. for i in idx])
    windows = np.minimum(hours//WINDOW_H, int(24/WINDOW_H)-1).astype(int)

    report = dict(status="reweighted_fixture", arm=args.arm, nu=NU, window_h=WINDOW_H,
                  scale_bounds=[MIN_SIGMA_SCALE, MAX_SIGMA_SCALE],
                  source_fixture=str(fixture_path), source_fixture_sha256=meta["fixture_sha256"],
                  calibrating_solution=str(solution_path), calibrating_solution_sha256=step["solution_sha256"],
                  note="Sigmas recalibrated from postfit residual scatter only. No reference "
                       "product, orbit score, row deletion or estimator change.",
                  models={})

    new_sigma = np.array([list(rows[i]["sigma"]) for i in range(len(rows))], dtype=float)
    for kind, name in ((1, "phase"), (0, "code")):
        m = kinds == kind
        if not m.any():
            continue
        # Elevation comes from the phase sigma, which the frozen profile ties to sin(el)
        # exactly; code rows at the same row index share that elevation.
        elevation = elevation_of(np.array([rows[i]["sigma"][1] for i in idx[m]]))
        a, b, p, law = fit_elevation_law(residual[m], elevation)
        model = np.sqrt(a**2+(b/np.sin(elevation)**p)**2)
        if args.arm == "W1":
            keys = list(stations[m])
        else:
            keys = [f"{s}:{w:02d}" for s, w in zip(stations[m], windows[m])]
        scales, detail = group_scales(residual[m], model, keys)
        applied = np.array([scales[k] for k in keys])*model
        report["models"][name] = dict(
            rows=int(m.sum()), a_mm=a*1000, b_mm=b*1000, exponent=p, law_fit=law,
            old_sigma_median_mm=float(np.median(sigma[m])*1000),
            new_sigma_median_mm=float(np.median(applied)*1000),
            old_whitened_rms=float(np.sqrt(np.mean((residual[m]/sigma[m])**2))),
            new_whitened_rms=float(np.sqrt(np.mean((residual[m]/applied)**2))),
            groups=len(scales), group_detail=detail)
        for position, value in zip(idx[m], applied):
            new_sigma[position, kind] = value

    # A row whose phase is ineligible keeps its original phase sigma untouched; only rows the
    # pilot actually emits were recalibrated, and every row keeps both entries.
    changed = 0
    for i, row in enumerate(rows):
        before = list(row["sigma"])
        row["sigma"] = [float(new_sigma[i, 0]), float(new_sigma[i, 1])]
        changed += row["sigma"] != before
    report["rows_total"] = len(rows)
    report["rows_reweighted"] = int(changed)

    out = resolve(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out/"fixture.json"
    target.write_text(json.dumps(fixture)+"\n")
    digest = sha(target)
    # The controller requires status "prepared" and a matching hash; carry the source's
    # provenance forward so the reweighted fixture's lineage stays explicit.
    prepared = dict(json.loads((prep/"step.json").read_text()))
    prepared.update(status="prepared", fixture_sha256=digest, reweighted=report)
    (out/"step.json").write_text(json.dumps(prepared, indent=2, default=float)+"\n")
    report["output_fixture"] = str(target)
    report["output_fixture_sha256"] = digest

    text = json.dumps(report, indent=2, default=float)+"\n"
    (run_dir/"reweight.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/f"reweight_{args.arm}.json").write_text(text)

    print(f"arm {args.arm}: {changed} of {len(rows)} rows reweighted -> {target}")
    for name, d in report["models"].items():
        print(f"  {name:6s} law sigma = sqrt({d['a_mm']:.2f}^2 + ({d['b_mm']:.2f}/sin^{d['exponent']:.2f} el)^2) mm, "
              f"{d['groups']} groups")
        print(f"         median sigma {d['old_sigma_median_mm']:7.2f} -> {d['new_sigma_median_mm']:7.2f} mm, "
              f"whitened RMS {d['old_whitened_rms']:.3f} -> {d['new_whitened_rms']:.3f}")
    phase = report["models"].get("phase", {}).get("group_detail", {})
    worst = sorted(phase.items(), key=lambda kv: -kv[1]["shrunk_scale"])[:8]
    best = sorted(phase.items(), key=lambda kv: kv[1]["shrunk_scale"])[:4]
    print("  most down-weighted phase groups: "+", ".join(f"{k} x{v['shrunk_scale']:.2f}" for k, v in worst))
    print("  most up-weighted phase groups:   "+", ".join(f"{k} x{v['shrunk_scale']:.2f}" for k, v in best))
    print("\nWrote "+str(run_dir/"reweight.json"))


if __name__ == "__main__":
    main()
