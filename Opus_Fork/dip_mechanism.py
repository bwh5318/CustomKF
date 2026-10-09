"""Is the "midday dip" the constellation sum of a Sun-fixed once-per-revolution radial error?

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 1800 --label dip-mechanism -- Opus_Fork.dip_mechanism

Evaluation only. It follows `dip_nga.py`, which found:

- the baseline's pooled mean radial oscillates with a ~12 h period, locked to UT, peaking near
  06–07 and 19 UT and dipping near 01 and 13 UT on Aug 2–5;
- NGA does not show it; the dynamics-only fits to IGS positions (T1 census) do; ERP barely
  changes it; network coverage is flat;
- radial residuals binned by in-plane angle from the Sun (Δu) show a once-per-revolution
  pattern.

**Hypothesis, stated before this runs.** Each satellite carries a Sun-fixed 1/rev radial error,
R ≈ a·cos Δu + b·sin Δu. All satellites share one orbital period, and the constellation is not
uniform in Δu, so the mean over satellites at epoch t, (1/N)Σ[a cos Δu_s(t) + b sin Δu_s(t)], is
itself a ~12 h UT-locked oscillation. It repeats day to day, because the ground track repeats
and the Sun moves about 1°/day, and it changes with the satellite set.

**Test.** Per day and arm, after removing each satellite's daily constant:

- **S** (Sun-fixed): one global (a, b), fitted to all satellite-epochs.
- **S-block**: (a, b) per block.
- **E** (Earth-fixed control): 1st + 2nd harmonics of sub-satellite longitude, with the same
  number of parameters as S-block.

For each model, the predicted per-epoch pooled mean (averaged over the satellites present) is
compared with the observed per-epoch pooled mean. The report gives correlation, explained
fraction of pooled-mean variance, and amplitudes.

**Declared reading.** S "explains the dip" if its predicted pooled mean correlates ≥ 0.8 with
the observed one and explains ≥ 60% of its variance on each of Aug 2–5, and beats E. The same
test on NGA shows whether IGS and NGA differ by their own Sun-fixed term. A census comparison
(E5, E7, E5P, E5R: 12 h + 24 h harmonic amplitude of the pooled residual) shows whether an
extra SRP parameterization reduces it without station data.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation

from .dip_nga import CASES, build
from .paths import STAGE2, RESULTS


def design(kind, rows):
    du = np.array([r["du"] for r in rows])
    lon = np.radians([r["lon"] for r in rows])
    if kind == "S":
        return np.column_stack([np.cos(du), np.sin(du)])
    if kind == "S-block":
        blocks = sorted({str(r["block"]) for r in rows})
        cols = []
        for b in blocks:
            m = np.array([str(r["block"]) == b for r in rows], dtype=float)
            cols += [m*np.cos(du), m*np.sin(du)]
        return np.column_stack(cols)
    if kind == "E":
        return np.column_stack([np.cos(lon), np.sin(lon), np.cos(2*lon), np.sin(2*lon)]*2)[:, :8]
    raise ValueError(kind)


def analyse(rows, arm):
    sats = np.array([r["sat"] for r in rows])
    ns = np.array([r["ns"] for r in rows])
    x = np.array([r[arm][0] for r in rows])*100
    for s in set(sats):
        m = sats == s
        x[m] -= x[m].mean()
    epochs = sorted(set(ns))
    observed = np.array([x[ns == k].mean() for k in epochs])
    out = dict(pooled_mean_rms_cm=float(np.sqrt(np.mean(observed**2))),
               pooled_mean_range_cm=float(observed.max()-observed.min()))
    for kind in ("S", "S-block", "E"):
        a = design(kind, rows)
        coef, *_ = np.linalg.lstsq(a, x, rcond=None)
        fit = a@coef
        predicted = np.array([fit[ns == k].mean() for k in epochs])
        resid = observed-predicted
        entry = dict(corr=float(np.corrcoef(observed, predicted)[0, 1]),
                     explained_pooled_variance=float(1-np.var(resid)/np.var(observed)),
                     per_sample_variance_explained=float(1-np.var(x-fit)/np.var(x)))
        if kind == "S":
            entry.update(amplitude_cm=float(np.hypot(*coef)), phase_deg=float(np.degrees(np.arctan2(coef[1], coef[0]))),
                         a_cos_cm=float(coef[0]), b_sin_cm=float(coef[1]))
        out[kind] = entry
    return out


def harmonic_amplitudes(hourly):
    h = np.arange(24)+0.5
    y = np.array([np.nan if v is None else v for v in hourly])
    m = np.isfinite(y)
    w = 2*np.pi/24
    a = np.column_stack([np.ones(m.sum()), np.cos(w*h[m]), np.sin(w*h[m]), np.cos(2*w*h[m]), np.sin(2*w*h[m])])
    c, *_ = np.linalg.lstsq(a, y[m], rcond=None)
    return dict(mean=float(c[0]), amp_24h=float(np.hypot(c[1], c[2])), amp_12h=float(np.hypot(c[3], c[4])))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    run = Path(os.environ["CUSTOMKF_RUN_DIR"])
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    ephemeris = DE440(STAGE2/"de440s.bsp")
    report = dict(status="evaluation_only_not_accuracy_acceptance", days={})
    for day, fixture, base, erp, _ in CASES:
        rows, _, _, _ = build(day, fixture, [base, erp], eop, ephemeris)
        report["days"][day] = {arm: analyse(rows, arm) for arm in ("B", "ERP", "NGA")}
        for arm in ("B", "ERP", "NGA"):
            r = report["days"][day][arm]
            print(f"{day} {arm:4s} pooled-mean rms {r['pooled_mean_rms_cm']:.2f} range {r['pooled_mean_range_cm']:.2f} | "
                  f"S corr {r['S']['corr']:.2f} expl {r['S']['explained_pooled_variance']:.2f} amp {r['S']['amplitude_cm']:.2f} phase {r['S']['phase_deg']:+.0f} | "
                  f"S-block corr {r['S-block']['corr']:.2f} expl {r['S-block']['explained_pooled_variance']:.2f} | "
                  f"E corr {r['E']['corr']:.2f} expl {r['E']['explained_pooled_variance']:.2f}", flush=True)
    census = {}
    for fn in ("reference_census_2026-08-02.json", "reference_census_2026-08-02_physics.json"):
        c = json.loads((RESULTS/fn).read_text())
        for variant in c["variants"]:
            acc = {h: [] for h in range(24)}
            for s, v in c["satellites"].items():
                for hour, rr, _, _ in v.get("variants", {}).get(variant, {}).get("series_cm", []):
                    if hour < 24:
                        acc[int(hour)].append(rr)
            hourly = [float(np.mean(acc[h])) if acc[h] else None for h in range(24)]
            census[variant] = harmonic_amplitudes(hourly) | dict(hourly=hourly)
    report["census_pooled_harmonics_2026-08-02"] = census
    for v, c in census.items():
        print(f"census {v:5s} mean {c['mean']:+.2f}  24h amp {c['amp_24h']:.2f}  12h amp {c['amp_12h']:.2f}", flush=True)
    text = json.dumps(report, indent=1)+"\n"
    (run/"dip_mechanism.json").write_text(text)
    (RESULTS/"dip_mechanism.json").write_text(text)


if __name__ == "__main__":
    main()
