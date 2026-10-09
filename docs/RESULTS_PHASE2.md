# Results, second phase (19-29 September 2026)

The 24-hour production line against IGS final with NGA PE alongside: forces, Earth orientation, weighting and the experiments that failed. Each section is one original write-up, unchanged except that its headings are one level deeper. The last section is the append-only correction index.

This document is generated for the public release. Links inside the sections point to files of the private working repository, which may not be here.

## Contents

1. `Opus_Fork/results/BASELINE.md`
2. `Opus_Fork/results/DIAGNOSIS.md`
3. `Opus_Fork/results/WEIGHTS_PROTOCOL.md`
4. `Opus_Fork/results/WEIGHTS_W1.md`
5. `Opus_Fork/results/WEIGHTS_W2_AND_CAUSE.md`
6. `Opus_Fork/results/ARC_CENSUS.md`
7. `Opus_Fork/results/ARC_CENSUS_ERRATA.md`
8. `Opus_Fork/results/T0_T1_RESULTS.md`
9. `Opus_Fork/results/URE_REVIEW_AND_TEST_PLAN.md`
10. `Opus_Fork/results/T2_1_ERP_PROTOCOL.md`
11. `Opus_Fork/results/T2_1_ERP_RESULTS.md`
12. `Opus_Fork/results/IIIA_AUG345_PROTOCOL.md`
13. `Opus_Fork/results/IIIA_AUG345_RESULTS.md`
14. `Opus_Fork/results/DIP_AND_NGA_DISTRIBUTIONS.md`
15. `Opus_Fork/results/ECOM7_PROTOCOL.md`
16. `Opus_Fork/results/ECOM7_RESULTS.md`
17. `Opus_Fork/results/ECOM7P_PROTOCOL.md`
18. `Opus_Fork/results/ECOM7P_RESULTS.md`
19. `Opus_Fork/results/ECOM7P_HOLDOUT_PROTOCOL.md`
20. `Opus_Fork/results/ECOM7P_HOLDOUT_RESULTS.md`
21. `Opus_Fork/results/BOXWING_CENSUS_RESULTS.md`
22. `Opus_Fork/results/SWING_ORIGIN_NOTES.md`
23. `Opus_Fork/results/SDEOP_PROTOCOL.md`
24. `Opus_Fork/results/SDEOP_RESULTS.md`
25. `Opus_Fork/results/SENSITIVITY_PROTOCOL.md`
26. `Opus_Fork/results/SENSITIVITY_RESULTS.md`
27. `Opus_Fork/results/STATION_TIDES_SCREEN.md`
28. `Opus_Fork/results/RESIDUAL_BINNING.md`
29. `Opus_Fork/results/ELEVATION_PROTOCOL.md`
30. `Opus_Fork/results/ELEVATION_RESULTS.md`
31. `Opus_Fork/results/TRANSFER_CALCULATION.md`
32. `Opus_Fork/results/CORRECTIONS.md`

---

<!-- original: Opus_Fork/results/BASELINE.md -->

## The real bar, measured: NGA PE against IGS final on our own day

Opus, 19 September 2026. Campaigns `Opus_Fork/runs/20260920T014500Z-baseline`,
`…T014752Z-g21-signature`, `…T014950Z-597ef639` (window scan). Inputs were already
pinned on disk; nothing was downloaded, no fit was run, and no file outside
`Opus_Fork/` was written.

### Why this measurement was needed

The project's stated target has been a **stored 359-day average** of the historical
NGA-versus-IGS study: 10.13 cm 3D and 3.62 cm orbit-only URE
(`COMPARISON_CONTRACT.md`, "Target and rapid-latency boundary"). Every fit so far has
been scored against IGS **rapid**. The objective the user actually names is different
and sharper: be closer to IGS **final** than NGA PE is.

Both files needed to settle that were already here and unused:

| File | What it is |
|---|---|
| `data/stage0/IGS0OPSFIN_20262140000_01D_15M_ORB.SP3` | IGS **final**, 2026-08-02 |
| `data/stage0/nga24300.sp3` | **NGA PE**, 2026-08-02 (`EPOCHA v9.3 SMOOTHER`, 2 days of data) |

2026-08-02 is the same day as our best fit. So the head-to-head is directly computable.

Frames are not relabelled or fitted: NGA is WGS84(G2296), IGS is IGc20, and both headers
declare satellite centre of mass (`SATCOM`). Raw unaligned candidate-minus-reference is
the primary score per `COMPARISON_CONTRACT.md`; a 7-parameter Helmert fit appears only as
a separately labelled diagnostic and absorbs 18% of NGA's squared error and 15% of ours.

### Result 1 — the bar is 10.84 cm, and we are 0.2% from it

Raw, unaligned, equal weight per satellite-epoch, 15-minute native SP3 epochs.

| Candidate vs IGS final | Sats | n | 3D | URE | R / A / C |
|---|---:|---:|---:|---:|---|
| **NGA PE** | 32 | 3072 | **11.17 cm** | **4.42 cm** | 4.25 / 6.79 / 7.78 cm |
| **NGA PE**, restricted to our 27 | 27 | 2592 | **10.84 cm** | **4.43 cm** | 4.28 / 6.49 / 7.56 cm |
| **Our 25-station 24 h ECOM5 fit** | 27 | 2592 | 14.67 cm | 4.63 cm | 4.25 / **12.04** / 7.22 cm |
| IGS rapid | 32 | 3072 | 0.59 cm | 0.30 cm | 0.30 / 0.39 / 0.31 cm |

Four things follow immediately.

1. **Scoring against IGS rapid was never the problem.** Rapid and final differ by
   0.59 cm 3D, which is 4% of our error. Every past score stands as written.
2. **Radial is already a tie** (4.25 cm against 4.28 cm) and **cross-track is already a
   win** (7.22 against 7.56 cm).
3. **Along-track is the entire deficit**: 12.04 cm against 6.49 cm, a factor 1.85.
   Substituting NGA's along-track into our own radial and cross-track gives
   sqrt(4.25² + 6.49² + 7.22²) = 10.6 cm, which beats the bar.
4. **URE is within 4.4%** (4.63 against 4.43 cm), because URE weights along-track and
   cross-track by 1/7 and we already match NGA radially.

### Result 2 — one satellite carries 46% of our squared error

| | 3D | URE | R / A / C |
|---|---:|---:|---|
| Ours, 27 satellites | 14.67 cm | 4.63 cm | 4.25 / 12.04 / 7.22 |
| Ours, the 26 without G21 | **10.96 cm** | **4.28 cm** | 4.25 / 7.20 / — |
| NGA, the same 26 | 10.94 cm | 4.50 cm | 4.28 / 6.49 / — |

Set G21 aside and **we already match NGA in 3D and beat it by 5% in URE over the full
day.** On 00:00–18:00 without G21 we are at 9.94 cm against NGA's 10.93, a 9% win.
We beat NGA on 3D for **13 of 27 satellites** as things stand.

By block the picture is not uniform:

| Block | NGA 3D | Ours 3D | |
|---|---:|---:|---|
| IIF | 10.16 | 10.43 | tie |
| **IIIA (GPS III)** | 11.19 | **21.44** | we lose 1.9x |
| IIR | 13.62 | **9.34** | **we win 31%** |
| IIR-M | 11.09 | 11.62 | tie |

G21 is IIIA. The block that hurts is the block whose nominal SRP coefficient
`PROJECT_REVIEW.md` already identified as biased, and IIIA is also where the one >0.1 m
regression of the 25-station run sat.

### Result 3 — the deficit is confined to the last six hours of the arc

Identical satellite-epochs for both products in every window.

| Window | Ours 3D | NGA 3D | Ratio | Ours along | NGA along |
|---|---:|---:|---:|---:|---:|
| 00–06 h | 11.04 | 10.52 | 1.05 | 7.74 | 5.96 |
| 06–12 h | 10.95 | 10.35 | 1.06 | 6.53 | 6.05 |
| 12–18 h | 12.19 | 11.60 | 1.05 | 9.93 | 7.73 |
| **18–24 h** | **21.84** | 10.85 | **2.01** | **19.60** | 6.04 |
| 00–16 h | 10.86 | 10.79 | **1.006** | 7.33 | 6.59 |

Through 16:00 we are level with NGA. The last six hours are twice as bad.

The per-epoch shape says the same thing and rules out several candidate causes. G21's
along-track error stays inside ±18 cm from 00:00 to about 13:00, then climbs
monotonically to **+96 cm at 21:00** before easing. G27, the second-worst satellite,
does the same thing in the same window, smaller: flat within ±8 cm to 16:00, then +30 cm
at 19:30–21:00. NGA stays inside ±10 cm for both, all day.

What this excludes:

- **Not eclipse or attitude.** G21's β angle is 36.0–36.1° with zero shadow epochs, so
  nominal yaw is correct for it all day. G01, the one genuinely eclipsing IIIA satellite
  (β 4.7–5.3°, 8 shadow epochs), has the *best* along-track of the block at 4.22 cm.
- **Not a flagged manoeuvre.** No SP3 event, manoeuvre or prediction flag appears for
  G21 or G27 in IGS final, IGS rapid or NGA PE.
- **Not a static force-model bias.** A constant mismodelled acceleration would grow from
  both arc ends. This grows only from the late end, and fitted ECOM5 is free per
  satellite here.
- **Not broadly bad station data.** Both satellites are well determined for two thirds
  of the same day, over the same network.

What it points at: **the last hours of a 24 h batch arc are weakly constrained, and
float ionosphere-free ambiguities on arcs that begin late trade directly against
along-track position.** This is consistent with the one independent clue already in the
project: Astra's G21 residual localization selected `VACS:G21:59`, **16:20–23:50 GPST** —
precisely this window — and masking it recovered 0.92 of the error. On this reading the
mask worked because it removed a late, short, poorly determined ambiguity arc, not
because the VACS observations are defective.

### What this changes

The project is closer than its own documentation says. Against the reference the
objective actually names, on a like-for-like day and satellite set:

- the bar is **10.84 cm 3D / 4.43 cm URE**;
- we are at **14.67 / 4.63**, and at **10.96 / 4.28** once one satellite's late-arc
  runaway is set aside;
- radial is tied, cross-track is won, and **along-track in the final six hours is the
  only thing standing between this estimator and the objective.**

Four caveats, none of which change the direction. This is one day, which is also the
day the 25-station configuration was developed on. Our 27 satellites are not NGA's 32,
and a deliverable product needs all of them. Setting G21 aside is descriptive, not an
exclusion. And agreement with IGS final is not absolute accuracy.

### Recommended next step

Attack the arc end, not the force model: restore the five satellites lost at 00:00 from
the previous-day broadcast file that is already on disk, then test late-ambiguity
handling and an extended arc. See `../PLAN.md` phase 1. The physics omissions
(Earth radiation pressure, antenna thrust, ocean tide gravity, subdaily EOP) are real
but they are radial-and-URE work, and radial is already at parity; they belong after the
along-track fix, where they decide the margin rather than the outcome.

---

<!-- original: Opus_Fork/results/DIAGNOSIS.md -->

## What actually causes the along-track deficit: two hypotheses tested and rejected, one supported

Opus, 19 September 2026. Five read-only diagnostics over the archived 25-station 24 h
ECOM5 solution and its fixture. No fit, no download, no edit. Campaigns in
`Opus_Fork/runs/`; JSON evidence in this folder.

### The thing to explain

Against IGS final on 2026-08-02, on identical satellite-epochs (`BASELINE.md`): NGA PE is at
10.84 cm 3D, we are at 14.67 cm, radial ties, cross-track wins, and **along-track loses
12.04 cm to 6.49 cm**. The deficit is confined in time — 18–24 h scores 2.01x NGA while
00–16 h scores 1.006x — and concentrated on one satellite: G21 carries 46% of our squared
error, as a +96 cm along-track excursion peaking at 21:00. G27 shows the same shape,
smaller, from 16:00.

Already excluded by `g21_signature.json`: eclipse or attitude (G21's β is 36° with zero
shadow epochs, and the one genuinely eclipsing IIIA satellite has the block's *best*
along-track), a flagged manoeuvre (no event flag in IGS final, IGS rapid or NGA PE), and a
static force-model bias (which would grow from both arc ends, not only the late one).

### Hypothesis 1: late, short ambiguity arcs absorb along-track. **Rejected.**

Float ionosphere-free ambiguities on arcs that begin late carry few epochs, so they should
be nearly free and trade against along-track position. This is testable from the archive: the
saved covariance spans all 1694 non-clock parameters, 1172 of them ambiguities, and
`C[p,a]/C[a,a]` scaled by the narrow-lane wavelength gives the orbit shift one unresolved
cycle would produce.

It does not hold (`ambiguity_health.json`):

- Rank correlation between per-satellite ambiguity-borne leverage and measured along-track
  RMS is **0.20**. G21, worst by a factor of four in measured along-track, is **13th of 27**
  in leverage. G25, first in leverage, has an along-track RMS of 7.84 cm.
- Leverage does not depend on arc length. Median formal ambiguity sigma is 7.2 cm for arcs of
  1–3 epochs and 6.7 cm for arcs of 21+; the median indicative leverage is flat across all
  buckets.

One number worth keeping: **every ambiguity has a formal sigma near 7 cm against a
narrow-lane wavelength of 10.7 cm**, that is 0.65 cycles. Integer resolution needs that well
below ~0.3 cycles, so ambiguity fixing is not yet reliable here — useful for phase 2 planning,
but not the cause of this failure.

This also contradicts the reading I sent Astra in `NOTES_FOR_ASTRA.md`. Her `VACS:G21:59`
mask does not work because the arc is late and short.

### Hypothesis 2: gross outliers, with no postfit clipping to catch them. **Rejected as stated.**

`run_stage3.py:166` records the profile honestly: "no postfit clipping". Nothing is robustly
weighted or edited, so a bad phase observation at 9 mm sigma carries a good one's weight.

The tails are too thin to be the story (`residual_outliers.json`):

| Beyond | Phase rows | Share of rows | Share of phase squared cost |
|---|---:|---:|---:|
| 3σ | 28 | 0.10% | 10.0% |
| 4σ | 12 | 0.04% | 6.8% |
| 5σ | 3 | 0.01% | 3.8% |

Twelve rows of 28,393 carry 6.8% of the cost. Clipping them would be worth having and would
not close a 35% gap.

**But the diagnostic found the decisive clue.** G21 has the *highest* phase whitened RMS of
all 27 satellites, and it doubles in the late window (0.510 → 1.042). Large residuals are
evidence *against* both preceding hypotheses: a free parameter absorbing error leaves
residuals small. Something in that window cannot be reconciled with any orbit the model can
represent, and the fit's compromise is the excursion we see.

### Hypothesis 3: the weights are wrong, and wrong in a structured way. **Supported.**

The frozen error model is a single elevation law, phase sigma = 9 mm / sin(el), identical for
every station, satellite and hour. `error_model.json` measures what the residuals say instead.

**Overall scale.** Pooled phase whitened RMS is **0.461**, so the assumed sigma is about 2.2x
too pessimistic. A uniform scale error does not move a least-squares solution, only its
covariance — so this alone is harmless. The structure is not.

**The elevation law has the wrong slope.**

| Elevation | Rows | Whitened RMS | Implied actual sigma |
|---|---:|---:|---:|
| 10–20° | 6252 | 0.581 | 19.9 mm |
| 20–30° | 6247 | 0.495 | 10.7 mm |
| 30–45° | 7359 | 0.424 | 6.3 mm |
| 45–60° | 4988 | 0.377 | 4.3 mm |
| 60–90° | 3547 | 0.323 | 3.1 mm |

True error grows 6.4x from zenith to the 10–20° band while the assumed sigma grows only 3.5x.
The law is too *shallow*, confirming Astra's earlier correction of my predecessor. Consequence:
**low-elevation observations are systematically over-weighted** relative to high-elevation ones.

**Some stations degrade sharply in the late window and the model does not know.**

| Station | 00–08 h | 08–16 h | 16–24 h | late / early |
|---|---:|---:|---:|---:|
| DJIG | 0.415 | 0.509 | **0.917** | 1.97 |
| CHPI | 0.288 | 0.292 | 0.466 | 1.61 |
| GUAM | 0.637 | 0.427 | **0.831** | 1.53 |
| SUTH | 0.251 | 0.294 | 0.403 | 1.47 |
| VACS | 0.421 | 0.551 | 0.711 | 1.45 |
| NNOR | 0.472 | 0.429 | 0.628 | 1.39 |
| … | | | | |
| BRUX | 0.254 | 0.370 | 0.295 | 0.93 |
| ABMF | 0.649 | 0.630 | 0.414 | 0.65 |

Station quality varies by a factor of 2.9 at any given hour (BRUX 0.313 against GUAM 0.664
overall) and by a further factor of 2 within one station across the day. Every one of those
observations is weighted identically at a given elevation.

**The affected satellites are exactly the ones those stations track late.**

| Late-window pair | Rows | Whitened RMS |
|---|---:|---:|
| **DJIG:G21** | 41 | **2.240** |
| GUAM:G30 | 25 | 1.478 |
| GUAM:G27 | 20 | 1.429 |
| VACS:G21 | 46 | 1.341 |
| GUAM:G07 | 37 | 1.152 |

The four satellites whose late misfit is worst — G07 2.36x, G21 2.05x, G30 1.99x, G27 1.60x —
are the four tracked by DJIG and GUAM in 16–24 h. G21 is hit twice, by DJIG at 2.24 and VACS
at 1.34.

### The mechanism, stated plainly

There is no robust weighting and no empirical error model. A station whose phase noise triples
for eight hours keeps its nominal weight for those eight hours, and low-elevation data is
over-weighted on top of that. Where such a station is a large share of a satellite's late
tracking, the fit is pulled toward observations it should have distrusted, and the cheapest
direction for a 24 h arc to move is along-track. G21, seen late by both DJIG and VACS, moves
furthest.

This explains Astra's mask result without implicating VACS as defective: removing those rows
removes over-weighted rows. It predicts that **down-weighting** them achieves the same thing
without deleting data, and that the effect is satellite-agnostic and reproducible on other
days — which a station blacklist derived from one day's orbit scores would not be.

### What this implies for the plan

The first experiment is no longer late-ambiguity handling. It is a **calibrated,
station-and-elevation-dependent error model with robust down-weighting**, of the form
sigma² = a_s² + b_s²/sin²(el), with coefficients estimated per station from a *prior day* and
frozen before the target-day fit. That mirrors the block-D0 precedent exactly: correct a fixed
input, calibrate strictly beforehand, change no parameter count, and predeclare the outcome.
It is orbit-independent to calibrate, so it cannot be tuned against a score.

`PLAN.md` phase 1 is revised accordingly. Two things carry over unchanged: restoring the five
satellites dropped at 00:00, which `nav_coverage.json` shows the on-disk previous-day
broadcast file recovers three of (27 → 30, with G13 correctly excluded as broadcast-unhealthy
and G02 losing 23 of 288 epochs to a mid-day ephemeris gap), and clipping the handful of rows
beyond 4σ, which is cheap and worth 6.8% of the phase cost.

### Caveats

The error-model numbers are postfit residuals from a converged solution, so they are
correlated with the fit they came from; calibrating on a different day is what makes the
resulting weights independent. Whitened RMS is a proxy for elevation here, recovered from the
retained sigma rather than recomputed geometry. And the mechanism is an inference from
consistent residual structure, not yet a demonstrated cause: the demonstration is the
reweighted fit, which has not been run.

---

<!-- original: Opus_Fork/results/WEIGHTS_PROTOCOL.md -->

## Frozen protocol: does correcting the error model fix the along-track deficit?

Opus, 19 September 2026, **written while the W1 fit was running and before any reweighted
score existed**. The reweighted fixtures were built first
(`Opus_Fork/runs/20260920T030109Z-reweight-W1`, `…T030121Z-reweight-W2`), so the weights are
already frozen and cannot be revised in response to what the fits produce.

### Hypothesis under test

`results/DIAGNOSIS.md`: the frozen error model — one law, phase sigma = 9 mm/sin(el), for every
station, satellite and hour — misstates relative weights, and the satellites that fail
along-track are the ones the over-weighted stations track late. Two rival explanations were
already tested against the archive and rejected (late short ambiguity arcs, rank correlation
0.20; gross outliers, 12 rows of 28,393 carrying 6.8% of phase cost).

### Arms

All four share the same 25-station 24 h Aug-2 fixture rows, observations, seeds, priors,
station set, satellite set, config (`unit-ecom5`) and convergence rules. **Only sigma differs.**
No row is deleted in any arm.

| Arm | Weights | Campaign |
|---|---|---|
| **P0** | archived baseline, 9 mm/sin(el) | `claude/runs/20260913T220409Z-long-NL-25st-24h` |
| **W1** | fitted elevation law + one scale per station | `Opus_Fork/runs/20260920T030309Z-fit-W1-25st-24h` |
| **W2** | W1 plus a scale per station per 3-hour window | not yet run |

Fitted model, from P0's postfit residual scatter only — no reference product, no orbit score:

- phase: `sigma = sqrt(0.65² + (2.49 / sin^1.41 el)²)` mm; median 16.46 → 6.83 mm;
  pooled whitened RMS 0.461 → 1.001
- code: `sigma = sqrt(35.20² + (377.82 / sin^0.90 el)²)` mm; median 1658 → 722 mm
- W1 station scales span 0.82 (BRUX) to 1.77 (DAV1); W2's 200 groups span 0.64 (BRUX 00–03 h)
  to 3.98 (DAV1 21–24 h), with DJIG 15–21 h at 2.1–2.2 and GUAM 15–18 h at 2.27

The exponent was freed from the predeclared `a² + b²/sin²(el)` because that form hit its
non-negativity boundary — it can only be flatter than 1/sin, and the observed scatter is
steeper. That change was made on residual scatter, before any orbit was refitted, and is
recorded in `reweight.py:fit_elevation_law`.

### Declared outcomes

Scored with `Opus_Fork.evaluate` against **IGS final**, raw and unaligned, on satellite-epochs
common to every arm and to NGA PE, on the 27 satellites the fixture retains.

**Primary.** W1 or W2 improves pooled along-track RMS over P0 by **≥20%** on the full day
(00:00–23:45), while the 00:00–16:00 window changes by **≤5%** in either direction. The
asymmetry is the point: the diagnosis says the damage is late, so a fix that also moves the
early window is doing something else.

**Secondary, all reported whether they pass or fail.**

1. G21's full-day along-track RMS falls from 50.64 cm by at least a third, and its peak
   excursion (+96 cm at 21:00) shrinks.
2. The 18:00–23:45 ratio against NGA falls from 2.01.
3. Pooled 3D against NGA's 10.84 cm, and pooled URE against NGA's 4.43 cm.
4. Count of satellites where we beat NGA in 3D, from 13 of 27.
5. Every satellite regressing by more than 0.1 m against P0, named.
6. W2 versus W1: if W2 is materially better, within-day variation matters and same-day
   estimation is required; if W1 captures most of it, a prior-day calibration suffices and the
   correction transfers across days.

**Falsification.** If neither arm reaches a 10% along-track improvement, the error-model
explanation is wrong too, and `results/DIAGNOSIS.md` must be revised the same way the
ambiguity and outlier hypotheses were. Three failed hypotheses would say the cause is
something none of the archive diagnostics can see, and the next step is a manoeuvre or
attitude check against an independent source rather than more estimator work.

### What this cannot establish

One day, and the day the 25-station configuration was developed on. W1's and W2's weights are
calibrated from that same day's residuals, so this measures whether the *mechanism* is real,
not what the correction is worth operationally. The operational question is a prior-day
calibration applied to an unexposed day, which needs 2026-08-01 station data (not yet
acquired) and a fresh date. Agreement with IGS final is agreement, not absolute accuracy.
Setting G21 aside anywhere remains descriptive, never an exclusion.

### Resources

W1 launched with the fork's `fork8` profile: 4 GiB, 50% machine CPU, 1 numerical thread, 8
processes, 600 s worker timeout, 75% total-machine stop threshold, 8 GiB memory reserve, same
mutex as Astra's guard. Early workers run about 15% faster than the reference run's
(traj 69.9/65.0 s against 82.2/75.8 s; state 42.6 s against 49.5 s), so the higher CPU quota
helps modestly. The remaining cost is per-row Python, which more cores cannot reach until the
chunk workers run in parallel; that optimization is deferred until the science is settled.
Budget about 50 guarded minutes per arm, against the reference run's 56.

---

<!-- original: Opus_Fork/results/WEIGHTS_W1.md -->

## Result: W1, a calibrated station-and-elevation error model — mechanism confirmed, threshold missed

Opus, 20 September 2026 UTC. Protocol frozen beforehand in [WEIGHTS_PROTOCOL.md](WEIGHTS_PROTOCOL.md).
Campaign `Opus_Fork/runs/20260920T030309Z-fit-W1-25st-24h`; fixture
`…T030109Z-reweight-W1`; evaluation `…T034945Z-eval-W1` and `arm_W1.json`. Raw unaligned
scores against **IGS final**, on satellite-epochs common to P0, W1 and NGA PE, 27 satellites.

### Verdict against the declared outcomes

| Declared | Result | |
|---|---|---|
| **Primary:** along-track improves ≥20% full day | **−11.4%** | **fails** |
| **Primary:** 00:00–16:00 changes ≤5% | −1.9% | passes |
| G21 along-track falls by ≥1/3 | −16.9% | fails |
| 18:00–23:45 ratio against NGA falls from 2.01 | 1.78 | improves |
| Satellites beating NGA in 3D, from 13/27 | 14/27 | improves |
| Regressions >0.1 m against P0 | none | passes |

**The mechanism is real and acts exactly where the diagnosis said it would. Its size is about
half of what would close the gap.**

### Scores

| Domain | Samples | | 3D | URE | R / A / C |
|---|---:|---|---:|---:|---|
| **Full day** 00:00–23:45 | 2592 | P0 | 14.67 | 4.63 | 4.25 / 12.04 / 7.22 |
| | | **W1** | **13.48** | **4.46** | 4.15 / 10.67 / 7.11 |
| | | NGA | 10.84 | 4.43 | 4.28 / 6.49 / 7.56 |
| **00:00–16:00** | 1755 | P0 | 10.86 | 4.47 | 4.33 / 7.33 / 6.75 |
| | | **W1** | **10.74** | 4.42 | 4.27 / 7.19 / 6.74 |
| | | NGA | 10.79 | 4.23 | 4.06 / 6.59 / 7.52 |
| **18:00–23:45** | 648 | P0 | 21.84 | 5.08 | 4.13 / 19.60 / 8.69 |
| | | **W1** | **19.33** | 4.74 | 3.97 / 16.87 / 8.56 |
| | | NGA | 10.85 | 4.93 | 4.82 / 6.04 / 7.62 |
| **12:00–18:00** | 675 | P0 | 12.19 | 3.89 | 3.59 / 9.93 / 6.09 |
| | | **W1** | **10.42** | **3.53** | 3.30 / 8.02 / 5.77 |
| | | NGA | 11.60 | 4.49 | 4.31 / 7.73 / 7.51 |

Three things in that table matter more than the failed threshold.

1. **W1 beats NGA outright on two of the four domains.** On 12:00–18:00 it is **10.42 cm
   against 11.60**, a ratio of 0.898, and on URE **3.53 against 4.49** — a 21% URE win. On
   00:00–16:00 it is 10.74 against 10.79, ratio 0.995.
2. **Full-day URE is now 4.46 cm against NGA's 4.43** — 0.7% short of the bar, from 4.4% short.
3. **The improvement is asymmetric as predicted.** Late window −11.5% in 3D and −13.9%
   along-track; early window −1.1% and −1.9%. A weighting error that was uniformly wrong would
   have moved both equally. This is the signature the protocol asked for.

### Per satellite

15 of 27 satellites improve, 12 worsen slightly, and **nothing regresses by more than 2.5 cm**.

| Satellite | Block | P0 3D | W1 3D | Change | NGA |
|---|---|---:|---:|---:|---:|
| **G21** | IIIA | 51.83 | **43.14** | **−8.70** | 7.79 |
| G27 | IIF | 16.75 | 13.67 | −3.08 | 7.90 |
| G08 | IIF | 13.04 | 10.48 | −2.55 | 9.00 |
| G07 | IIR-M | 12.59 | 11.30 | −1.29 | 7.52 |
| G12 | IIR-M | 10.80 | 9.59 | −1.21 | 16.02 |
| … | | | | | |
| G22 | IIR | 12.34 | 14.34 | +2.01 | 16.14 |
| G10 | IIF | 9.11 | 11.21 | +2.09 | 7.68 |
| G23 | IIIA | 13.01 | 15.44 | +2.43 | 7.61 |

The four satellites the diagnosis named — G21, G27, G07 and G30 — are four of the five largest
improvements, which is direct confirmation that the over-weighted station-hours were doing the
damage. But **G21 is still 43 cm against NGA's 7.8**, and it alone still carries about a third
of our squared error. Reweighting is not the whole story for that satellite.

### Convergence and cost

Three linearizations, same as P0, converging to a step bound of 4.6e-6 m. 40 workers,
**2725 guarded s against P0's 3374** — the fork's higher CPU quota is worth about 19%, as
expected for a workload whose cost is per-row Python rather than BLAS.

An incidental fix worth recording: reading the solution `.npz` peaked at 2852 MiB in earlier
diagnostics and hit a `MemoryError` once two solutions were loaded at once. `NpzFile.__getitem__`
decompresses the whole array on every access, so indexing `f["states"][si, ti]` inside a loop
re-read a 27×287×6 array 7749 times. Reading each member once took the peak to **98.7 MiB**.
`claude/roadmap/streaming.py` carries the same warning for the same reason.

### What this changes

The error model was the third hypothesis tested, and it is the first to survive. It is worth
keeping on its own terms: it costs nothing, it needs no new data, it improves 15 of 27
satellites with no meaningful regression, and it wins two of four scoring domains against NGA.

It does not close the gap, and the residue is concentrated on G21 in the last third of the day.
Since weighting, ambiguity leverage and outliers are now all accounted for, the next candidate
is the one our own observations cannot test: **that G21's true trajectory on this day is not a
single smooth arc.** `Opus_Fork/reference_dynamics.py` tests that against IGS final alone — fit
state plus ECOM5 directly to the reference positions and see whether the reference orbit itself
resists a 24 h arc where control satellites do not. If it does, no weighting or estimator change
fixes this day for G21 and the single-arc-per-day assumption is what needs revisiting.

W2, which lets the station scale vary in 3-hour windows and down-weights DAV1 21–24 h by 3.98
and DJIG 15–21 h by 2.1–2.2, is running and will say whether within-day variation is worth the
extra 175 groups.

### Caveats

One day, and the day the configuration was developed on. W1's weights are calibrated from this
same day's postfit residuals, so this measures whether the mechanism is real, not what a
prior-day calibration would be worth operationally. Agreement with IGS final is agreement, not
absolute accuracy. No satellite was excluded and no row deleted in any arm.

---

<!-- original: Opus_Fork/results/WEIGHTS_W2_AND_CAUSE.md -->

## W2 and the attribution question — SEE CORRECTIONS: several claims below are superseded

> **CORRECTIONS, 20 September 2026 — read these before anything below.** An independent
> review (`w2_interpretation_review/REVIEW.md`) found overclaims in this note. It is right on
> every point. The original text is kept unedited below so the record stays honest.
>
> 1. **"First full-day metric on which this project beats NGA" is wrong.** P0 already beat
>    NGA on full-day radial (4.255 vs 4.280) and cross-track (7.218 vs 7.558). W2's first is
>    the URE composite only, by 0.079 cm — small next to NGA's WGS84-vs-IGc20 frame offset,
>    though the ordering survives the Helmert diagnostic (3.81 vs 4.06).
> 2. **W2 worsened cross-track**, 7.218 → 7.439 cm; 12 of 27 satellites worsen, and G22's
>    +5.90 cm 3D regression is almost entirely cross-track (+6.85 cm). Not mentioned below.
> 3. **Satellites beating NGA stayed at 13 of 27** (W1 had 14). Not reported below.
> 4. **G21 metric mix-up.** The declared endpoint is along-track, 50.64 → 38.64 cm
>    (−23.70%). The "51.83 → 39.60" below is 3D. The verdict is unchanged only because the
>    two percentages coincide.
> 5. **"W2 > W1 settles transferability" is not established.** Both arms are in-sample on
>    the same day, and W2 fits 200 scales against W1's 25, so an in-sample advantage is
>    expected regardless. Transfer needs a prior-day arm on an unseen date.
> 6. **"Modelling is exonerated; the residue must sit in the initial state" is not
>    established.** The reference fit shows representational capacity only.
>    `reference_dynamics.py:63` discards the fitted state and covariance, so the "truth"
>    coefficients carry no uncertainty. A sustained 0.35 nm/s² along-track error accumulates
>    to about 1 m in 12 h, state and force estimates compensate each other, and observation
>    errors bias the state. Attribution stays open until the full six-state plus five-force
>    difference is propagated with covariance.
> 7. **The early-window reinterpretation was made after the score** and is a revised
>    hypothesis, not a finding.
>
> **And one consequence that outranks all of these.** Weights estimated from residual
> scatter cannot tell noise from an unsplit phase discontinuity. On 2026-08-08 a single
> unsplit arc, SGOC:G07:65, carried 50.4% of the network's phase cost
> (`sgoc_g07_native_audit/REVIEW.md`). A W2-style scale would down-weight it and hide an
> arc-handling defect behind a weight. **Weighting and arc integrity are confounded until arc
> QC is settled**, so no weighting result here should be read as causal.
>
> **The clean number.** The 31-satellite fit with the *original, unweighted* error model
> (`arm_N0_31.json`) has none of these confounds: full-day URE **4.427 vs NGA 4.427**, a tie;
> radial and cross-track both wins; 17 of 31 satellites beat NGA in 3D; 3D 14.11 vs 10.91.

---

Opus, 20 September 2026 UTC. Protocol frozen beforehand in [WEIGHTS_PROTOCOL.md](WEIGHTS_PROTOCOL.md).
Campaigns `Opus_Fork/runs/20260920T035014Z-fit-W2-25st-24h`, evaluation `…T193122Z-eval-W2`
(`arm_W2.json`), reference dynamics `…T193221Z-refdyn` (`reference_dynamics.json`).

### 1. W2 beats NGA on full-day URE

Raw unaligned against IGS final, satellite-epochs common to every arm and to NGA, 27 satellites.

| Full day 00:00–23:45 | 3D | URE | R / A / C |
|---|---:|---:|---|
| P0 baseline | 14.67 | 4.63 | 4.25 / 12.04 / 7.22 |
| W1 station-constant weights | 13.48 | 4.46 | 4.15 / 10.67 / 7.11 |
| **W2 station × 3-hour weights** | **13.05** | **4.351** | 4.05 / 9.93 / 7.44 |
| NGA PE | 10.84 | **4.430** | 4.28 / 6.49 / 7.56 |

**4.351 against 4.430: the first full-day metric on which this project beats NGA.** W2 also
wins 3D on 00:00–16:00 (10.55 vs 10.79) and on 12:00–18:00 (10.15 vs 11.60, URE 3.48 vs 4.49),
and its early-window along-track now matches NGA outright, 6.55 against 6.59.

Along-track against P0: **−17.5%** full day, −10.6% early, −18.9% late, −26.3% at noon.
17 of 27 satellites improve; the worst regression is +5.9 cm (G22). G21 falls 51.83 → 39.60 cm.

#### Against the declared outcomes, honestly

| Declared | W2 | |
|---|---|---|
| Along-track ≥20% better, full day | −17.5% | **fails, narrowly** |
| 00:00–16:00 changes ≤5% | −10.6% | **fails** (it is an improvement) |
| G21 along-track falls ≥1/3 | −23.6% | fails |
| 18:00–23:45 ratio against NGA below 2.01 | 1.706 | improves |
| No regression >0.1 m against P0 | worst +5.9 cm | passes |

The asymmetry clause was meant to catch a "fix" that moves the early window too, on the
reasoning that the damage was late. W2 moves it by 10.6%. The correct revision is that
**within-day station noise is not confined to the late hours, it is merely worst there**:
W1, whose scales are constant over the day, left the early window alone, while W2's 3-hour
groups improve it everywhere. The clause failed because my framing was too narrow, not
because the correction misbehaved.

**W2 > W1 settles transferability, unhelpfully.** 13.05 against 13.48 full day, 15.89 against
16.87 late. Within-day variation carries real signal that a prior-day station calibration
cannot capture, so the operational form is a two-pass same-day fit rather than a frozen input.
That remains legitimate — it reads only residual scatter, never a reference orbit — but it is
a different operational shape from the block-D0 precedent.

### 2. There is no manoeuvre. The fourth hypothesis is rejected too.

Fitting initial state + ECOM5 **directly to IGS final's own positions**, with no station
observation involved:

| Satellite | Block | 3D misfit | Along-track | max abs along |
|---|---|---:|---:|---:|
| **G21** | IIIA | **3.37 cm** | **0.78 cm** | 2.23 cm |
| G27 | IIF | 3.72 cm | 0.85 cm | 1.80 cm |
| G01 | IIIA | 5.58 cm | 2.29 cm | 5.20 cm |
| G23 | IIIA | fit did not converge | — | — |

G21's true trajectory on this day **is** a single smooth arc, and our own force model
represents it to **0.78 cm along-track** — better than G01, which fits fine and scores fine.
So the arc does not need splitting, there was no unflagged momentum dump, and the
single-arc-per-day assumption is sound for this satellite on this day.

(G23's reference fit failed with "No decreasing training-only step". That is a robustness
limit of `solve_force`'s line search on a 24 h arc, not a statement about G23; it is recorded
rather than retried with different settings.)

### 3. Our force parameters are right. So the residue is the initial state.

Total ECOM5 is nominal + estimated correction; the `unit-ecom5` config sets the nominal D0 to
−100 nm/s² and the rest to zero. Compared against the reference-fitted values above:

| Satellite | | D0 | Y0 | B0 | Bc1 | Bs1 |
|---|---|---:|---:|---:|---:|---:|
| **G21** | reference | −81.70 | +0.62 | +0.52 | −0.38 | +2.71 |
| | P0 | −82.28 | +0.48 | +0.13 | −1.01 | +4.78 |
| | **W2** | **−82.07** | +0.53 | +0.07 | **−0.34** | **+3.06** |
| G27 | reference | −107.76 | +0.16 | −1.01 | −1.40 | +0.06 |
| | W2 | −108.45 | +0.19 | −1.26 | −4.55 | −0.66 |
| G01 | reference | −80.80 | +0.86 | +0.26 | +0.82 | −0.08 |
| | W2 | −80.35 | +1.09 | −0.86 | −1.55 | +1.04 |

All in nm/s². Our D0 recovers the reference value to **0.4–0.8 nm/s²** on every satellite, and
**W2 markedly improved G21's once-per-revolution terms** — Bc1 from −1.01 to −0.34 against a
truth of −0.38, Bs1 from 4.78 to 3.06 against 2.71. That is independent confirmation that the
reweighting fixed something real, from a direction the orbit score cannot see.

**This is the important conclusion.** The dynamics can represent the truth to 0.78 cm. The
force parameters are recovered to under 2 nm/s². Yet G21's orbit is 39.60 cm off along-track.
With correct forces and adequate dynamics, that residue has to sit in the **estimated initial
state** — and an along-track error that is flat early and grows late is the classic signature
of a small semi-major-axis or along-track-velocity error.

So the remaining problem is **not modelling of any kind**. It is that the observations, as
weighted and with the nuisance parameters as currently parameterized, do not pin G21's initial
state tightly enough.

One caveat on the covariance: W2's deviations are 3–6 formal sigma even though its absolute
agreement is better than P0's. Recalibrating the weights to a whitened RMS of 1.0 sharpened the
formal sigmas, but time-correlated residual structure remains, so the covariance is now
over-confident. Formal sigma should not be quoted as an accuracy claim.

### 4. Hypotheses tested, in order

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| 1 | Late short ambiguity arcs absorb along-track | rejected | rank correlation 0.20; G21 13th of 27 in leverage |
| 2 | Gross outliers, with no postfit clipping | rejected | 12 rows of 28,393, 6.8% of phase cost |
| 3 | Mis-specified error model | **confirmed, partial** | W1 −11.4%, W2 −17.5% along-track; G21 −23.6% |
| 4 | Unflagged manoeuvre / non-smooth arc | rejected | reference fits to 0.78 cm along-track |
| 5 | Wrong force parameters | rejected | D0 recovered to 0.4–0.8 nm/s² |

What remains is observation strength and nuisance-parameter coupling for one satellite — which
is what the two big Phase 2/3 levers were always aimed at: **integer ambiguity resolution**,
which tightens exactly the along-track and cross-track directions, and **more stations**. Both
were in the plan on general grounds; they are now the specific answer to a specific question.

### Limits

One day, and the day the configuration was developed on. W2's weights come from that same day's
residuals, so this measures whether the mechanism is real, not its operational value. The
reference-dynamics fits use IGS final deliberately and feed nothing; the estimator's SP3 read
prohibition stays installed on every fitting path. No satellite was excluded and no row deleted
in any arm. Agreement with IGS final is agreement, not absolute accuracy.

---

<!-- original: Opus_Fork/results/ARC_CENSUS.md -->

The arc-splitting rule has one systematic hole, and it is open on every day we have fitted

Opus, 21 September 2026 UTC. Frozen protocol in the `Opus_Fork/arc_census.py` docstring,
written before any output was read. Campaigns `Opus_Fork/runs/20260921T011932Z-census-220`
(2026-08-08) and `…T012048Z-census-214` (2026-08-02). Read-only replay of the unchanged
parser, `choose_signals`, `combinations` and `ArcTracker` over native RINEX. No fixture, fit,
weight, mask, arc-rule change or download.

### The mechanism

`customkf/preprocess.py:47-52`:

```python
elif (tag - old[0])/1e9 > 60:  reason.append("gap")
else:                          <geometry-free and Melbourne-Wubbena jump tests>
```

A step of **exactly 60 s** — one missed epoch in 30 s data — fails the strict `> 60` test and
falls through to the jump tests, which then apply a 60 s allowance of
`0.08 + 0.002*60 = 0.20 m` in geometry-free. A phase discontinuity smaller than that, with no
loss-of-lock flag, stays inside one arc and one ambiguity. The rule behaves exactly as
written; the rule is what admits the discontinuity.

### Census criterion, declared in advance

Every pair of consecutive selected samples of one satellite at one station that the tracker
kept in the **same arc** while the step exceeded the file's nominal interval. No jump
threshold and no margin fraction enters the definition, so the census cannot be tuned by its
own output. A step longer than the interval means the receiver stopped reporting usable
phase, which is exactly when an undetected slip can occur, whatever the jump size.

### Result: the hole is the whole story

| Day | Stations read | Candidates | At the 60 s boundary | With loss-of-lock |
|---|---:|---:|---:|---:|
| 2026-08-08 | 24 of 25 (YELL unreadable) | 66 | **66** | **0** |
| 2026-08-02 | 25 of 25 | 54 | **54** | **0** |

**Every single candidate on both days is the same one-missed-epoch case, and not one carries a
loss-of-lock flag.** This is not a scattering of marginal calls; it is one rule boundary.

### Positive control

The census was required to rediscover the known case or be treated as untrustworthy.
`SGOC:G07` at 12:38:00 on 2026-08-08 — the arc that `sgoc_g07_native_audit/REVIEW.md` showed
carries **50.4% of the whole network's phase cost** — is found, and ranks **1st of 66** by
Melbourne-Wubbena step at **−3.01 widelane cycles**.

Melbourne-Wubbena is the discriminator, not geometry-free. Geometry-free changes naturally
over 60 s through ionosphere and geometry, so a large `dGF` means little on its own: the
worst `dGF` on 2026-08-08 is KOUG:G27 at 17.4 cm with only −0.65 widelane cycles, which looks
ionospheric. Melbourne-Wubbena is both geometry-free and ionosphere-free, so a step there in
near-integer widelane cycles is the slip signature. Ranking by it puts the one case already
proven damaging at the top.

### How much of the network is affected

| Day | Candidates | ≥ 0.5 widelane cycle | ≥ 1.0 widelane cycle |
|---|---:|---:|---:|
| 2026-08-08 | 66 | 42 | **19** |
| 2026-08-02 | 54 | 32 | **24** |

Worst on **2026-08-02**, the day every result in this fork was measured on: FAA1:G13 −5.72
cycles, EUR2:G08 −4.61, FAA1:G12 +3.82, FALK:G08 −3.12, KIT3:G25 −2.92, FAA1:G12 +2.58,
FAA1:G03 +2.57, FAA1:G29 +2.56, FAA1:G30 +2.53. FAA1 supplies five of the worst ten.
G13 is excluded from our fits under the broadcast-health rule, so that one is harmless; the
rest are in the fitted set.

### What this means for results already reported

**Every fit in this fork, and the baselines it was compared against, was run over a network
carrying roughly two dozen probable unsplit cycle slips.** That includes P0, W1, W2, N0 and
the 31-satellite fixture. The weighting experiments are the most exposed: a residual-scatter
scale cannot tell a slip from noise, so W1 and W2 may be partly down-weighting slips rather
than correcting a noise model, exactly as `w2_interpretation_review/REVIEW.md` section 4
warned. This does not invalidate the measurements, but it does mean no weighting result here
can be read as causal until the arc rule is settled.

**Astra's just-completed cross-date campaign is affected too.** Its four arms on 2026-08-07
and 08-08 used the same tracker, and 2026-08-08 carries 19 candidates over a full widelane
cycle including the SGOC:G07 arc. That is worth knowing before its scores are read.

**One thing this does not explain: G21.** There is no candidate on G21 at any station on
2026-08-02. The dominant error in every fit this fork has produced is not an unsplit slip.
Of the satellites that scored worst, only FAA1:G30 (2.53 cycles), MAS1:G07 (1.46) and
MDO1:G22 (1.29) have candidates at all — MDO1:G22 being mildly interesting, since G22 was
W2's worst regression at +5.90 cm.

### The fix, and why it is not applied here

The natural rule is to split on **any** step longer than the nominal sampling interval, which
is what the criterion above already identifies and what common practice does. It is a small
change, but it is an arc-rule change to `customkf/preprocess.py`, which is Astra's, and the
proposed weight protocol requires one identical arc rule frozen across every arm including
the baseline before anything is refitted. So this census stops at evidence.

Recommended order, unchanged from `w2_interpretation_review/PROPOSED_WEIGHT_VALIDATION.md`:
freeze one arc rule, refit the baseline under it, and only then run any weighting or
ambiguity-fixing arm. Integer fixing in particular cannot proceed across an unsplit slip: it
would force a wrong integer.

### Limits

A 60 s step with a widelane jump is a **candidate**, not a proven slip. Melbourne-Wubbena at
30 s carries code noise of a few tenths of a cycle, so a 1.1-cycle step is suggestive and a
3-cycle step is strong, but confirmation needs the phase-level check the SGOC audit performed
sample by sample. Two days are censused; the rule hole is structural and will appear on any
day with a one-epoch phase outage. YELL on 2026-08-08 could not be read at all, so its
candidates are unknown.

---

<!-- original: Opus_Fork/results/ARC_CENSUS_ERRATA.md -->

## Errata to ARC_CENSUS.md

Opus, 21 September 2026 UTC. **`ARC_CENSUS.md` is immutable evidence**: Astra's native-gap
campaign pins it by hash, so corrections live here instead of being edited into it. An earlier
attempt to edit it in place aborted her running fit; see "Why this is a separate file" below.

Astra's independent replay (`claude/reviews/NATIVE_GAP_PREFLIGHT_REVIEW.md`) reproduced all 66
August-8 candidates exactly — station, satellite, time, step, geometry-free and
Melbourne-Wübbena changes, and flags. The census is correct as a **measurement**. Two of its
**readings** overstate, and a third is narrower than written.

### 1. The 60 s concentration is substantially tautological

`ARC_CENSUS.md` presents "every single candidate on both days is the same one-missed-epoch
case" as striking confirmation. It is a consequence of the selection. The criterion picks
consecutive samples the tracker kept in the **same arc** whose step exceeds the native
interval; the legacy rule splits every step `> 60 s`; so in 30 s data the only admissible step
is exactly 60 s. Nothing else could have been found.

What the census does measure, and what is not circular: the **count** of such gaps — 66 on
2026-08-08, 42 on 2026-08-07, 54 on 2026-08-02 — and their Melbourne-Wübbena distribution.

### 2. Native candidates are not fitted impact

"Every fit in this fork ... was run over a network carrying roughly two dozen probable unsplit
cycle slips" conflates a native census with the fitted arc partition. Fixtures retain rows on
the 600 s solve grid after a 10-degree elevation mask, NAV eligibility and arc trimming, so a
native gap changes the partition only if it separates two **retained** rows into non-empty
pieces.

Measured by Astra's uniform candidate preparation:

| Date / arm | Native candidates | Retained arcs split | Phase rows | Eligible ambiguities |
|---|---:|---:|---|---:|
| Aug 7 core14 | 42 | 0 | 15,516 → 15,516 | 613 → 613 |
| Aug 7 expanded25 | 42 | 0 | 27,589 → 27,589 | 1,068 → 1,068 |
| Aug 8 core13 | 66 | 0 | 16,017 → 16,017 | 630 → 630 |
| Aug 8 expanded24 | 66 | **2** | 29,309 → **29,306** | 1,173 → 1,173 |

So the entire fitted consequence is **three phase observations** on one arm, from two splits:
`SGOC:G07:65` → 2+44 rows (epochs 74, 75 lose phase eligibility) and `KIT3:G01:137` → 4+1
(epoch 116). All code rows are retained and no ambiguity is added. The August-2 fitted impact
is unmeasured and, on this evidence, likely small.

### 3. The G21 negative is narrower than stated

No gap candidate on G21 excludes **this signature** only. It does not exclude a discontinuity
with no gap, one below the existing geometry-free and Melbourne-Wübbena thresholds at 30 s
spacing, or one inside a sub-interval outage. On 2026-08-08 G21 has three native candidates
(ABMF +0.29, MDO1 −1.79, NKLG −0.16 widelane cycles), none of which becomes a retained split.

### 4. A gap candidate may not even be a carrier outage

`customkf/preprocess.py:combinations` returns `None` unless all four selected observables are
present, so a missing **code** with unbroken carrier tracking also produces a candidate. Where
that is the case the ambiguity remains valid and splitting would add a parameter that should
not exist. Only `SGOC:G07` has sample-by-sample phase-level confirmation, from the native
audit. The recommended per-candidate check is in
`native_gap_partition_review/REVIEW.md` §2.

### What survives unchanged

- The rule boundary at `customkf/preprocess.py:48` is real: a strict `> 60 s` gap test means a
  60 s step is judged by jump thresholds carrying a 0.20 m geometry-free allowance.
- The census reproduces independently, candidate for candidate.
- The positive control works: `SGOC:G07` 12:38:00 ranks 1st of 66 by Melbourne-Wübbena step at
  −3.01 widelane cycles, and it is the arc already shown to carry 50.4% of the network's phase
  cost.
- Melbourne-Wübbena, not geometry-free, is the discriminator. The largest geometry-free jump on
  2026-08-08 (KOUG:G27, 17.4 cm) carries only −0.65 widelane cycles and looks ionospheric.

### Why this is a separate file

On 21 September I added a correction block directly to `ARC_CENSUS.md`. Astra's
`native_gap_fit` campaign pins eight files in `Opus_Fork/` as evidence inputs, including that
one, and re-verifies every pin before each worker. The edit changed its hash and aborted her
campaign after 24 workers and 1,542 guarded seconds. The original bytes were reconstructed and
restored, and all her pins verify again.

The lesson is general: **a file in this fork can be immutable evidence for someone else's live
campaign.** `Opus_Fork/pinned_by_live.py` lists every path pinned by a campaign that is
currently running, and should be consulted before editing anything here.

---

<!-- original: Opus_Fork/results/T0_T1_RESULTS.md -->

## T0–T1 results: the radial offset is a missing-force problem, and physics removes most of it

Opus, 22 September 2026 UTC. Tests from `URE_REVIEW_AND_TEST_PLAN.md`, run in order. Everything
here is evaluation-only or reference-only: no station fit, no estimator input, no file of
Astra's edited. IGS final and NGA PE were read only by evaluation code.

### T0.3 — August-6 close-out (documentation)

The campaign's honest stop is now recorded: `native_gap_aug6_validation/RESULTS.md`,
`ASTRA_HANDOFF.md` and `MANIFEST.json` (33 files hashed), and `RUN.md` shows terminal status.
The baseline converged. The candidate stalled on a 0.046 mm G11 ambiguity step, a numerical
floor, and was not scored.

### Input acquired — IGS satellite metadata

`Opus_Fork/datastore/static/igs_satellite_metadata.snx`: 273,931 bytes, SHA256 `191f7e04…e824`,
from files.igs.org (DLR, created 2026:245), with a sidecar record. It gives PRN→SVN, mass and
transmit power. It has **no body dimensions**. Those were transcribed from the published
box-wing tables cited in `Opus_Fork/nongrav.py`. `Opus_Fork/satmeta.py` parses it and
re-checks the hash on every load. For 2026-08-02, antenna thrust predicts a downward shift of
2.9 mm (IIR-A/B, 60 W), 7.0 mm (IIR-M, 145 W), 7.7 mm (IIF, 240 W) and 7.3 mm (IIIA, 300 W).

### T0.1 — where the radial error lives (`radial_budget.json`)

Archived solutions were re-scored against **IGS final**, with NGA PE on the same keys. Per
satellite, nested fits of mean, 1/rev and 2/rev in argument of latitude.

| Day / arm | URE cm | Radial MS cm²: const / 1-rev / 2-rev / rest | Const share | Sats with R̄ > 0 |
|---|---:|---|---:|---:|
| Aug 2 N0 (27 common) | 4.534 | 5.27 / 6.43 / 0.39 / 5.17 | 31% | 24/27 |
| Aug 2 W2 | 4.351 | 4.59 / 5.99 / 0.42 / 5.44 | 28% | 24/27 |
| Aug 2 **NGA** | 4.430 | 1.59 / 14.75 / 0.25 / 1.73 | 9% | 17/27 |
| Aug 7 expanded25 | **3.557** | 3.11 / 3.98 / 0.34 / 3.16 | 29% | 22/26 |
| Aug 7 **NGA** | 4.195 | 1.12 / 13.02 / 0.25 / 1.91 | 7% | 18/26 |
| Aug 8 native-gap 24 | **3.676** | 3.37 / 4.43 / 0.56 / 3.11 | 29% | 22/29 |
| Aug 8 **NGA** | 4.047 | 1.71 / 11.39 / 0.25 / 1.63 | 11% | 20/29 |

- **The constant is about 30% of our radial mean square on every 25-station arm, and about 9%
  of NGA's.** The declared expectations were a constant ≥20% of radial MS and positive on ≥80%
  of satellites. They hold on all 25-station arms, with one exception: the Aug-8 native-gap
  arm is positive on only 76% of satellites. They fail on the 13/14-station core arms.
- **Block ordering:** only IIF > IIIA holds on every day. IIF sits at +1.7..+2.1 cm on all
  25-station arms, where NGA's IIF sits at −0.5..−0.7.
- **Correlation with thrust alone** is weak or negative (−0.15 to −0.33 on Aug 2). Thrust
  cannot be the whole story, which pointed to Earth radiation.
- **Our "rest" term** (radial variation that is not 1/rev or 2/rev) is 3× NGA's. It is spread
  across satellites: median per-satellite RMS 1.6–2.0 cm against NGA's 1.2. G21 is the outlier
  on Aug 2. NGA's radial error is instead almost all 1/rev.
- **New, against IGS final:** the 25-station network beats NGA on URE on **Aug 7 (3.557 vs
  4.195)** and on **Aug 8 with the continuity rule (3.676 vs 4.047)**. These are descriptive
  scores on dates Astra used for rule development, not held-out results.

### T1 — the model's floor, fitted straight to IGS final (`reference_census_2026-08-02*.json`)

State plus forces fitted to 96 IGS-final positions per satellite over 24 h. No station data.

| Variant | Sats | Radial / Along / Cross RMS cm | Mean radial cm |
|---|---:|---|---:|
| E5 — state + ECOM5 (our POD's model) | 30 | 2.38 / 1.26 / 3.35 | **+1.75** |
| E5R — + estimated constant radial accel. | 31 | 1.44 / 1.26 / 3.34 | 0.00 |
| E5T — + antenna thrust (metadata, fixed) | 31 | 1.98 / 1.29 / 3.37 | +1.20 |
| E7 — ECOM-7 | 31 | 2.11 / 1.20 / 3.13 | +1.65 |
| **E5P — + physical ERP + thrust (fixed)** | 31 | **1.56** / 1.26 / 3.36 | **+0.33** |
| E5PR — E5P + estimated constant | 30 | 1.45 / 1.20 / 3.29 | 0.00 |

Estimated radial acceleration by block (nm/s²):

| Block | E5R: total missing | E5PR: left after physics | Physics explains |
|---|---:|---:|---:|
| IIF (11) | 1.68 ± 0.18 | 0.49 ± 0.22 | 71% |
| IIR (4) | 1.56 ± 0.10 | 0.76 ± 0.30 | 51% |
| IIR-M (7) | 1.37 ± 0.21 | 0.24 ± 0.19 | 83% |
| IIIA (8–9) | 0.94 ± 0.35 | −0.19 ± 0.26 | 120% |

Mean radial by block, E5 → E5P (cm): IIF +2.19 → +0.63, IIR +1.70 → +0.78,
IIR-M +1.80 → +0.30, IIIA +1.13 → −0.20.

**Reading.**

1. **The offset is in the force model, not in the station data.** The dynamics-only fit sits
   +1.75 cm above IGS. On the 25 common satellites (G21 excluded) it averages +1.82 cm against
   the station POD's +1.93 cm. The per-satellite correlation is weak (0.25; 1.1 cm scatter), so
   the common and block-level part is dynamics and the satellite-to-satellite part is POD noise.
2. **A fixed physical model removes 81% of it, and nothing in it was fitted to IGS.** The
   pooled mean falls +1.75 → +0.33 cm and radial RMS falls 34%. That is 90% of the way to the
   best a freely fitted constant achieves (1.56 against 1.44 cm).
3. **The model is absorption-only by declaration, so shortfalls were expected.** IIR is 51%
   explained, a plausible gap for missing reflection. IIIA is over-corrected by
   0.2 nm/s² (0.3 cm), consistent with its uncertain +Z area (published models range
   4.0–6.0 m²) and mass (2161 kg in the metadata; SRP studies suggest heavier). No coefficient
   was adjusted in response.
4. **The cross-track floor (3.1–3.4 cm) is untouched by every force variant.** The frame/EOP
   explanation (T1.3: no sub-daily EOP, linear UT1 interpolation) remains the candidate. It
   costs little URE (cross-track carries 1/49) but a lot of 3D.

**Predictions against outcome.**

| # | Prediction | Outcome |
|---|---|---|
| 1 | E5R radial acceleration positive, order 1e-9, lowers radial misfit | held |
| 2 | E5T shifts mean by 0.3–0.8 cm; cannot remove all | held (0.55 cm) |
| 3 | E7 changes the floor little | held |
| 4 | Cross-track floor untouched | held |
| 5 | E5P mean to +0.8..+1.1 cm | missed, favourably: +0.33 |
| 6 | E5PR residual 0.5–0.9 for IIR/IIR-M/IIF, about 0 for IIIA | mostly held (IIR-M lower, 0.24) |

**Failures, recorded and not retried.** G01, the eclipsing IIIA satellite at β ≈ 5°, failed its
state-only stage-1 fit in both runs ("No decreasing step"). G18 failed E5 and E5PR but passed
E5R/E5T/E7/E5P. Both are line-search robustness limits of this diagnostic solver across shadow
boundaries, not statements about those satellites.

### Resources

All under `Opus_Fork.guard --profile fork8` (4 GiB, 50% CPU quota, 75% machine ceiling, 8 GiB
reserve), serial, with no other Python process:

| Run | Guarded s | Peak job memory |
|---|---:|---:|
| metadata fetch | 1.5 | |
| T0.1 | 14.9 | 127 MiB |
| smoke tests | 11.4 + 99.9 | |
| T1 census | 449.1 | 658 MiB |
| T1.5 census | 397.7 | 662 MiB |

The census peak machine CPU was 30.0% and minimum available memory 16.14 GiB.

### Next

T2.1 is running: the same physical model inserted unchanged into the Aug-2 N0 station POD,
with the protocol frozen in `T2_1_ERP_PROTOCOL.md`.

---

<!-- original: Opus_Fork/results/URE_REVIEW_AND_TEST_PLAN.md -->

## Review: where our URE difference with IGS comes from, and the tests that should reduce it

Opus, 22 September 2026 UTC. Written at the user's request after a whole-project review.
Read-only: existing evaluation JSON, force/frame/observation code and archived step records
were inspected. No fit, propagation, download or estimator change, and no existing file was
edited. No Python process was live before or during this review.

### Bottom line

1. **URE is mostly radial.** Orbit-only URE is `sqrt(0.98²R² + (A²+C²)/49)`. In every
   scored case we have, radial is 81–83% of URE², along-track 10–14% and cross-track 5–9%.
   Most of the fork's work so far has targeted the along-track deficit. That is the right
   target for 3D, but it is a small share of URE.
2. **Our orbits are consistently 1.2–1.7 cm too high.** The pooled signed mean radial
   difference against IGS is positive on every day and in every arm, and it is positive on
   28 of 31 satellites on 2026-08-02. Weighting does not touch it (P0/W1/W2: +1.74/+1.71/+1.73
   cm). The Helmert diagnostic absorbs it as a +0.62 ppb scale. NGA's pooled mean is +0.26 cm.
   A per-satellite constant radial offset accounts for **23–25% of our URE²** on all five
   evaluated cases.
3. **The likely cause is unmodelled outward radial forces.** The force model has no Earth
   radiation pressure (albedo and infrared) and no antenna thrust
   (`customkf/run_stage2.py:57` lists both as omissions; `customkf/orbit_forces.py` confirms
   it). Station observations with epoch-wise clocks hardly see a constant radial offset, so
   the dynamics set the radius from the observed mean motion. A missing outward acceleration
   f leaves the fitted orbit higher by about f/(3n²). Our +1.66 cm implies f ≈ 1.1e-9 m/s²,
   which is the size expected for GPS albedo, infrared and antenna thrust together. The block
   pattern also fits (IIR highest, IIIA lowest). Removing only the common offset would take
   2026-08-02 full-day URE from 4.427 to about **4.12 cm**. Removing the per-satellite offsets
   would take it to about **3.87 cm**, against NGA's 4.427.
4. **The model has a representation floor, and part of it is probably frame, not force.**
   Fitting state plus ECOM5 directly to IGS final positions leaves 1.4–2.4 cm radial and
   2.7–4.7 cm cross-track. EOP are daily values interpolated linearly, with no sub-daily
   ocean-tide or libration terms and no zonal-tide handling (`customkf/frames.py`). That is a
   plausible cm-level cross-track and along-track floor.
5. **The observation model has a structural gap that the weighting work may have been
   absorbing.** It has no tropospheric gradients, uses Niell mapping with standard-atmosphere
   pressure, and constrains the wet delay to 3-hour nodes with 3 cm steps. A 1 mm gradient
   reaches about 3 cm at 10° elevation. That fits the findings "elevation law too shallow" and
   "station quality varies within the day", which were modelled as noise.
6. **The August-6 native-gap validation stopped honestly.** Its candidate's last step is a
   0.046 mm change to a G11 late-arc ambiguity, so it failed the stationarity rule at the
   numerical floor. The question it asks has very little power (two phase rows out of 15,523).
   `RUN.md` there still says RUNNING and needs a terminal record.

### 1. The URE budget

Raw, unaligned, native epochs. Shares are fractions of URE². "Pooled mean" removes one
common radial constant. "Per-satellite mean" removes each satellite's own constant; it is an
upper bound for what a radial force model could remove.

| Case | URE cm | R / A / C cm | Mean R cm | R / A / C share | URE without pooled mean | URE without per-sat means |
|---|---:|---|---:|---|---:|---:|
| Aug 2, N0, 31 sats, vs IGS final | 4.427 | 4.06 / 11.57 / 6.99 | +1.66 | 81 / 14 / 5% | 4.117 | 3.866 |
| Aug 2, NGA PE, same 31 | 4.427 | 4.27 / 6.72 / 7.46 | +0.26 | 90 / 5 / 6% | 4.420 | 4.244 |
| Aug 2, W2, 27 sats | 4.351 | 4.05 / 9.93 / 7.44 | +1.73 | 83 / 11 / 6% | 4.009 | 3.811 |
| Aug 7, expanded25, vs IGS rapid | 3.552 | 3.26 / 7.89 / 7.58 | +1.35 | 81 / 10 / 9% | 3.297 | 3.073 |
| Aug 8, native-gap candidate, vs rapid | 3.657 | 3.37 / 8.40 / 7.13 | +1.19 | 81 / 11 / 8% | 3.467 | 3.161 |

Sources: `results/arm_N0_31.json`, `results/arm_W2.json`,
`runs/20260920T224823Z-2b28e63f/evaluation.json`, `runs/20260921T230230Z-e4e50a18/evaluation.json`.

Two more facts from the same files:

- **G21 is 17% of the pooled URE² on Aug 2** (its own URE 10.21 cm). Half of that is its
  along-track runaway (52 cm / 7). If it scored at the constellation median, pooled URE
  would be about 4.09 cm. Its −3.80 cm mean radial comes from the along-track runaway, not
  from a force bias.
- **Even the weighting gain was mostly radial.** P0 → W2 lowered URE² by 2.5 cm², and
  1.6 cm² of that came from radial (4.25 → 4.05 cm).

What this means for priorities: halving the pooled along-track RMS (11.6 → 5.8 cm) is worth
about −5% URE. Removing the radial offset is worth −7% to −13%. Fixing G21 is worth about −8%.

### 2. Finding: a systematic radial offset of physical size

**Per block** (N0, Aug 2, mean radial in cm): IIR +2.71, IIF +2.09, IIR-M +1.87, IIIA +0.51.
P0/W1/W2 show the same ordering. NGA's per-block means are −0.68 to +1.25 and show no
common sign.

**Mechanism.** With per-epoch satellite clocks estimated, a radial shift δr changes every
range by δr·cos(nadir). Nadir is at most 13.9° at GPS altitude, so only about 3% of δr
differs between stations; the clock absorbs the rest. Along-track is observed well, so the
24 h fit pins the mean motion n, and the dynamics then set the radius. An outward
acceleration f that the model lacks leaves the model orbit higher by

    δr ≈ f / (3n²),   3n² = 6.38e-8 s⁻² at GPS altitude.

Our +1.66 cm needs f ≈ 1.06e-9 m/s². Order-of-magnitude physics for GPS:

- **Antenna thrust.** f = P/(m·c). This gives roughly 2–5e-10 m/s² across blocks, depending
  on transmit power and mass.
- **Earth albedo plus infrared** on a nadir-pointing bus. This gives roughly 3–6e-10 m/s²
  orbit-averaged, and falls with area-to-mass. That is consistent with IIIA, the heaviest
  block, having the smallest offset.

Both push outward, so both make an unmodelled orbit sit high, which matches the sign we see.
All IGS analysis centres model both, so IGS final carries them and we do not.

**Ruled out from the code.** GM is the TT-compatible 3.986004415e14 (EGM2008 header).
Schwarzschild relativity is modelled. The J2 permanent-tide handling cannot produce a
mean radial offset at 55° inclination. A satellite PCO-z error goes into the clock, not the
radius.

**Also consistent, smaller.** The pooled mean cross-track is negative on every day
(−1.1 to −2.1 cm). A constant origin offset T projects onto the six planes' normals as
0.574·T_z on average. N0's Helmert mean Z translation is −13.4 mm, which predicts −7.7 mm
against −13.5 mm observed. This is worth a diagnostic, but a Z-translation adds only about
0.58·T_z of radial RMS, around 3% of URE², so it is not a priority.

### 3. Finding: the model floor

Opus's reference-dynamics fits (`results/reference_dynamics.json`; state plus ECOM5 fitted to
IGS final, no station data):

| Sat | Radial | Along | Cross | cm RMS |
|---|---:|---:|---:|---|
| G21 IIIA | 1.40 | 0.78 | 2.97 | |
| G27 IIF | 2.44 | 0.85 | 2.67 | |
| G01 IIIA | 2.02 | 2.29 | 4.67 | eclipsing |

A 24 h fit with a complete model usually reaches about 1 cm. Two parts of this floor matter:

- **Radial 1.4–2.4 cm** is about the size of our POD's per-satellite radial offset: G27 +1.89,
  G01 +1.69. That is the missing radial force, seen without any station data.
- **Cross-track 2.7–4.7 cm** cannot come from radial forces. The frame module interpolates
  daily UT1 and pole linearly (`customkf/frames.py:32-45`). It omits the IERS sub-daily
  ocean-tide and libration terms (0.02–0.05 ms UT1 and a few 0.1 mas pole amplitude, several
  cm at GPS radius). It also does not remove zonal tides before interpolating UT1: the
  fortnightly term's curvature alone gives about a 1–2 cm mid-day error. The effects partly
  cancel between stations and satellite, so the size that reaches the orbit has to be
  measured.

The script that produced these fits discards the fitted state and covariance
(`reference_dynamics.py:63`) and does not save signed means. The census below uses a new
script.

### 4. Finding: the troposphere model

`customkf/station_models.py` and `claude/roadmap/long_pilot.py`:

- Saastamoinen with standard-atmosphere pressure, Niell mapping, no gradient parameters;
- piecewise-linear wet delay with nodes every 3 h and 0.03 m increment constraints;
- `troposphere(..., 214+(43190+receive_s)/86400)` in `customkf/dynamic_observation.py:79`
  hardcodes day 214 and the six-hour origin in the Niell season argument. That is harmless at
  the mm level, but it is wrong on other days and at 24 h origins, and should be recorded.

The gradient mapping function is about 29.6 at 10° elevation. So a 1 mm north or east
gradient, which is ordinary and larger in the tropics, gives about 3 cm azimuth-dependent
delay at the mask. That is systematic and repeats with azimuth, but a sin(el) law cannot
represent it. It would explain two things: the elevation scatter growing 6.4× while the model
grows 3.5×, and tropical stations (DJIG, GUAM, VACS, CHPI) degrading through the day. W1 and
W2 may have been partly down-weighting a missing troposphere parameter, which is the same
confound the SGOC/G07 audit raised for slips. Low-elevation data is also what separates
satellite radial from clock through nadir-angle diversity, so this reaches radial as well.

### 5. Finding: arc integrity is a URE lever, and its size on Aug 2 is unmeasured

On 2026-08-08 the continuity rule split two retained arcs and removed three phase rows. URE
fell **4.64 → 3.66 cm (−21%)** and radial 4.31 → 3.37 cm
(`claude/reviews/NATIVE_GAP_COMPLETION_REVIEW.md`). One unsplit slip damaged every satellite
through the clocks. Every fork result (P0, W1, W2, N0) is on 2026-08-02 under the old rule,
and its retained impact there has never been screened.

### 6. State of the fork: the August-6 native-gap validation

`Opus_Fork/runs/20260921T233923Z-native-gap-aug6-validation/validation.json`: status
`failed`, `RuntimeError('Line search exhausted')`, scoring not performed.

- **Readiness passed** (409.5 / 900 guarded s). **The baseline converged** after three
  linearizations (2,149.6 / 5,400 s).
- **Candidate at lin2.** Step bound 0.185 mm; predicted reduction 3.28e-4 against the
  threshold max(1e-5, 1e-8·cost) = 5.28e-5, so it is not stationary. All four trials raised
  the cost: +4.18e-4, +1.47e-4, +7.5e-5 and +4.8e-5 at α = 1, ½, ¼, ⅛. Used 2,843.0 / 5,400 s.
  The campaign total is 5,402.1 of 12,900.
- **The stalled direction** (from `runs/20260922T005657Z-77e1affb/direction.npz`): the largest
  component is −0.046 mm on `amb:GUAM:G11:89` (3e-4 formal σ), followed by `amb:YELL:G11:175`
  and G11 satellite clocks over 21:40–23:40. None of the three split arcs is involved. This is
  a cost/Jacobian consistency floor at tens of micrometres, not a modelling failure. It has no
  bearing on a centimetre score.
- `Opus_Fork/results/native_gap_aug6_validation/RUN.md` still reads "RUNNING" and must be
  corrected. The handoff also asks for `RESULTS.md`, `MANIFEST.json` and `ASTRA_HANDOFF.md`
  recording the stop and the remaining budget.

**Recommendation.** Record the honest stop and do not score. This contrast removes two of
15,523 phase rows and adds no ambiguity, so even a clean answer can move URE only
negligibly. Test the continuity rule where the URE work lives instead (T2.2 on the Aug-2
25-station fixture). Separately, and before any future score is seen, declare a
numerical-floor stationarity clause: for example, step bound < 1 mm and every trial's
|Δcost| < 1e-3 means "stationary at the numerical floor". That stops a 0.05 mm wobble from
ending a campaign. The August-6 protocol is Astra's, so these choices belong to the user and
Astra.

### 7. Proposed tests

Each test predeclares its outcome before running, and all of them respect the fork's
standing rules: IGS and NGA are evaluation-only, no satellite is excluded, and results are
raw and unaligned. IGS-fitted numbers never enter a product fit. They are used only to
decide which physical model to implement.

#### Tier 0: archive-only, no fit, minutes

**T0.1 Radial error decomposition. Do this first.** New script, evaluation-only. For N0, W2,
Aug-7 expanded25, the Aug-8 baseline and the Aug-8 candidate, re-score the saved solutions
epoch by epoch. For each satellite, fit mean + 1/rev + 2/rev harmonics in argument of
latitude to the radial and cross-track error series.
*Reports:* the share of radial MS in each term, per block, and the per-satellite mean against
block, area-to-mass and β.
*Decides:* how much a radial force model can buy (mean term) against SRP-type 1/rev error,
which box-wing or ECOM work would target.
*Declared expectation:* the mean term is ≥20% of radial MS on every case, positive on ≥80% of
satellites, and has the same sign and block ordering on all days.

**T0.2 Troposphere signature in residuals.** Take N0's post-fit phase residuals below 30°
elevation. Per station and per 3 h window, fit `m_g(el)·(G_N cos az + G_E sin az)` and report
the variance explained, with an azimuth-permutation control.
*Declared outcome:* gradients are "supported" if they explain ≥15% of low-elevation residual
variance at ≥⅓ of stations and beat the permutation control's 95th percentile. DJIG, GUAM
and VACS late windows should be among the largest. A negative result shields the weighting
work from this confound.

**T0.3 Close out August 6.** Update `RUN.md` to a terminal state. Write `RESULTS.md` with the
stop reason, budget, stalled-direction diagnosis and the fact that no score exists. Add
`MANIFEST.json` and `ASTRA_HANDOFF.md` as the handoff specifies. Documentation only; no
scoring unless the user says otherwise.

#### Tier 1: reference-orbit ceiling census, evaluation-only, about 10 guarded min per variant

A new script, not an edit of `reference_dynamics.py`. It fits state plus force parameters to
IGS final positions for **all 31 satellites** on 2026-08-02 (24 h), and saves signed RAC
series, fitted state and covariance. Variants:

| ID | Model | Question |
|---|---|---|
| T1.1 | state + ECOM5 (current) | Per-satellite floor, with signed mean radial |
| T1.2 | T1.1 + one estimated constant radial acceleration per satellite | Is the missing radial force ≈1e-9 m/s² with block structure, and does the mean radial misfit go to about 0? |
| T1.3 | T1.1 with IERS 2010 sub-daily EOP plus zonal-tide-aware UT1 interpolation | How much of the 2.7–4.7 cm cross-track floor is frame? |
| T1.4 | ECOM-7 (D2c, D2s; already implemented, `count==7`) | Does the 2/rev term lower the radial and along floor? |
| T1.5 | T1.1 + physical ERP and thrust (after T2.1 is implemented), no estimated term | Does physics reproduce most of T1.2's gain without fitting to IGS? |

*Adoption rule, declared now:* a component is adopted only if it lowers the floor on a
majority of satellites in **every** block, and only as a physical model with published
constants. T1.2's fitted accelerations are a diagnostic, never an input.

#### Tier 2: station POD arms

Each arm uses the 2026-08-02, 24 h, 25-station N0 configuration (unweighted, ECOM5, zero
start), about 45–55 guarded minutes per fit, one change at a time. Replicate on Aug 7
expanded25 and on the Aug-8 candidate (IGS rapid) before any claim.

**T2.1 Earth radiation pressure plus antenna thrust, a priori. Highest expected value.**
Implement the model in a fork-side `OrbitForceModel` subclass and a `restore` wrapper; no edit
to `customkf/` or `claude/`:

- antenna thrust f = P/(m·c), radial;
- an analytical Earth radiation model: uniform Lambertian Earth, albedo about 0.3, IR about
  240 W/m², nadir-pointing bus plus panels.

*Input decision for the user:* per-satellite mass, transmit power and dimensions. Cleanest is
the IGS satellite metadata SINEX (one small static file, rapid-legal, needs a download).
The alternative is a typed, cited literature table.

*Two predictions, frozen before fitting:*

- **Mechanistic, no IGS.** Each satellite's fitted orbit moves down relative to N0 by
  f̄ᵣ/(3n²), computed from the model alone. Pass if the pooled fitted shift is within 30% of
  the prediction.
- **Agreement.** The pooled mean radial against IGS falls from +1.66 cm to within ±0.6 cm.
  Full-day URE improves by ≥5% (4.427 → ≤4.21). No satellite regresses by more than 0.1 m
  in 3D. The block ordering of residual offsets flattens.

A pass on the first but not the second says the physics works and something else also
biases the radius, which would be the next test.

**T2.2 Continuity-rule screen on Aug 2.** Run Astra's unchanged native-gap retained-impact
screen on the Aug-2 25-station 24 h fixture (about 30 guarded s). Fit only if it splits
retained arcs. Same favourable-transfer gate as August 6: lower pooled 3D and URE, and no
>0.1 m regression. This settles the rule where the fork's scores live, and it must precede
any weighting arm.

**T2.3 Tropospheric gradients and a finer wet delay, conditional on T0.2.** Add one N/E
gradient pair per station, either daily or piecewise-linear over 6 h, and 1 h wet-delay nodes.
*Declared outcome:* the post-fit elevation law steepens toward 1/sin(el); late-window
whitened RMS at DJIG/GUAM/VACS falls ≥20%; URE improves ≥3% with no >0.1 m regression.
Then rerun the W1 residual diagnosis: whatever structure remains is the true noise model.

**T2.4 Sub-daily EOP in the POD, conditional on T1.3.** Expect mostly along- and
cross-track, so it helps 3D more than URE.

**T2.5 A 48 h arc delivering only Aug 2.** Use 2026-08-01 00:00 → 08-02 24:00. The Aug-1
station data for all 25 stations and the Aug-1 broadcast file are already in
`Opus_Fork/datastore/2026213/`, so no download is needed. This moves the Aug-2 start away from
the arc edge, restores G05/G18/G29 at 00:00, and strengthens SRP/state separation, which is
the standard analysis-centre remedy for end effects.
*Declared outcome:* ≥5% URE and ≥10% along-track on the delivered day. G21's 18–24 h
excursion is reported whatever it does. Memory must be checked first: 48 h at 25 stations
roughly doubles the streamed workspace (211 MiB at 24 h).

**T2.6 Weighting, out of sample.** `w2_interpretation_review/PROPOSED_WEIGHT_VALIDATION.md`
as drafted, but only after T2.2, and after T2.3 if T0.2 is positive. Those change the
residual structure the weights would be calibrated on.

#### Tier 3: larger programmes, after Tiers 0–2

- **Network expansion to about 50 stations** via a C1C–C1W code-bias product. 14 → 25
  stations lowered Aug-7 radial 4.77 → 3.26 cm, so this is a radial lever, not only a 3D one.
- **Box-wing a priori SRP**, if T0.1 shows 1/rev radial dominates what remains.
- **Wide-lane then narrow-lane ambiguity resolution.** Its prerequisites are in
  `w2_interpretation_review/REVIEW.md` §5. It is the largest along/cross lever and a
  moderate radial one.
- **Multi-day head-to-head** on unexposed dates against IGS final and NGA, with dates and
  sets frozen first (`PLAN.md` 4.1).

### 8. Suggested order

1. **T0.3** (documentation) and **T0.1** (a few guarded minutes). T0.1 either confirms the
   radial-offset priority with per-satellite structure or redirects it.
2. **T1.1 + T1.2** (about 20 guarded min). These confirm the missing radial force without
   station data.
3. **User decision:** where the satellite metadata for T2.1 comes from.
4. **T2.1** on Aug 2, then replicated on Aug 7 and Aug 8.
5. **T0.2**, then **T2.2**. Then T1.3/T1.4 and whichever of T2.3–T2.5 they support.

Projected, if T2.1 behaves as physics predicts: Aug-2 URE about 4.1 cm, against NGA's
4.43. Adding the arc rule, the G21 late-arc fix and troposphere is plausibly 3.7–3.9 cm.
These are projections from the budget above, not results.

### 9. What I would not do

- Estimate a constant radial acceleration inside the station POD. It is nearly unobservable
  there (≈3% nadir leverage), and it would trade against clocks.
- Adopt any IGS-fitted coefficient, including T1.2's, as a model input.
- Tune ERP albedo or reflectivity until the offset vanishes. The physics inputs must be
  fixed before the POD fit.
- Keep optimising along-track weighting for URE before the radial offset is dealt with.
- Spend more budget on the August-6 contrast.

### Evidence pointers

- Budget: `results/arm_N0_31.json` (`domains.full.arms.{N0,NGA}.{raw,per_satellite,by_block,helmert_diagnostic}`),
  `results/arm_W2.json`, `runs/20260920T224823Z-2b28e63f/evaluation.json`,
  `runs/20260921T230230Z-e4e50a18/evaluation.json`.
- Force model and omissions: `customkf/orbit_forces.py`, `customkf/run_stage2.py:57`.
- Frame and EOP: `customkf/frames.py:1-45`.
- Troposphere: `customkf/station_models.py:30-36`, `customkf/dynamic_observation.py:79`,
  `claude/roadmap/long_pilot.py:4-5,91-107`.
- Reference floor: `results/reference_dynamics.json`, `reference_dynamics.py:63`.
- Stationarity rule: `customkf/nonlinear_stop.py:20-24`. August-6 records:
  `runs/20260922T005657Z-77e1affb/{step.json,direction.npz}`, lin2 trials
  `runs/20260922T010000Z-099c7cd1`, `…010312Z-853510c3`, `…010624Z-a27ef6d6`, `…010944Z-dc8d80ab`.

---

<!-- original: Opus_Fork/results/T2_1_ERP_PROTOCOL.md -->

## T2.1 protocol: physical Earth radiation pressure + antenna thrust in the station POD

Opus, 22 September 2026 UTC. **Frozen before the fit was launched**; no T2.1 orbit or score
existed when this was written.

### Question

The station POD's orbits sit 1.2–1.7 cm above IGS on every day scored (T0.1). The dynamics-only
census puts the same +1.75 cm in the force model itself (T1, E5). A fixed physical ERP +
antenna-thrust model, with nothing fitted to IGS, removes 81% of it there (T1.5, E5P: +1.75 →
+0.33 cm). Does the same model, inserted unchanged into the station POD, remove the offset
from our orbit product and lower URE against IGS final?

### Arms

| Arm | What | Campaign |
|---|---|---|
| **N0** | archived baseline: 25 stations, 24 h, 31 satellites, unit-ECOM5, original weights | `Opus_Fork/runs/20260920T203126Z-fit-N0-31sat` |
| **P1** | N0 with the `Opus_Fork.nongrav` ERP + thrust model on every satellite | new, `Opus_Fork.run_fit_nongrav` |

P1 is identical to N0 in everything else: fixture
`Opus_Fork/runs/20260920T200910Z-prepare-31sat` (same rows, sigmas, seeds, priors), config
`claude/roadmap/configs/unit-ecom5.json`, 12-epoch chunks, 2 trajectory groups, fork8, 900 s
workers, at most 4 linearizations, zero-correction start, and its own freshly integrated x=0
caches. Only the force acting on each satellite differs. The estimated parameters are the same
five ECOM terms per satellite.

Model (`Opus_Fork/nongrav.py`, pinned by hash): antenna thrust P/(m·c) with P and m from the IGS
satellite metadata SINEX; analytical uniform-Earth IR (238 W/m²) plus Lambert-phase albedo
(A = 0.3); an Earth-facing area of +Z bus plus |d̂·r̂|-projected panels; absorption only;
geometry from Duan & Hugentobler (2021) and Steigenberger et al. (2020). Every constant was
fixed before any orbit was fitted with it. The T1 fits against IGS were used to test the model,
never to set it.

### Predictions

Raw, unaligned, against IGS final on 2026-08-02, on satellite-epochs common to N0, P1 and NGA
PE (31 satellites, as scored in `arm_N0_31.json`), evaluated with `Opus_Fork.evaluate`.

1. **Mechanism.** The pooled mean radial moves from +1.66 cm (N0) to between −0.3 and +0.7 cm.
   In T1 the model shifted the dynamics-only mean by −1.42 cm; the POD should shift by the same
   amount within ±0.5 cm.
2. **Primary.** Full-day orbit-only URE improves by **≥ 5%**: 4.427 → ≤ 4.206 cm. The budget
   projection for a −1.42 cm pooled shift is about 4.12 cm.
3. **No damage.** No satellite's 3D RMS regresses by more than 0.1 m. Along-track and
   cross-track pooled RMS change by less than 5% either way, since the model is almost purely
   radial.
4. **Block pattern.** The residual radial constants flatten. IIIA may go slightly negative (T1:
   E5P over-corrects IIIA by about 0.2 nm/s²), and IIR keeps the most positive residual.

**Falsification.** If the pooled mean radial moves by less than 0.7 cm, the POD's radius is not
set the way the mechanism says, and the T0.1/T1 interpretation must be revised. If the mean
moves but URE does not improve by ≥ 2%, the offset is being traded against another radial
error, which would need its own diagnosis.

### Replication, declared while P1 was still running and before any P1 score existed

**R7: 2026-08-07, 25 stations.** The arm is the archived Astra fixture
`runs/20260920T155655Z-7b703635` (prepared, 26 satellites, 24 h), config
`claude/experiments/cross_date_preparation/config.json` (unit ECOM5, all five estimated), 18-epoch
chunks and 4 trajectory groups, as in the baseline, with the same ERP + thrust model. The
baseline is Astra's converged expanded25 solution `runs/20260920T180129Z-38cb5d57`. Its
iteration workers differ from the fork's only in the streamed-workspace preflight cap.

Scored against IGS final on 2026-08-07 on keys common to both arms and NGA PE. Predictions:

1. The pooled mean radial falls by 1.0–1.6 cm and ends within ±0.6 cm of zero.
2. URE improves by ≥ 5% (T0.1 baseline against final: 3.557 → ≤ 3.379 cm).
3. No satellite regresses by more than 0.1 m in 3D. Along- and cross-track change by less than 5%.

This runs whatever P1's outcome is, so P1 cannot select whether it is reported.

### What it cannot establish

One day, and the day the configuration was developed on (the model itself was fixed from
publications, not from this day). A pass says the physics transfers into the POD as predicted.
It is not a multi-day or operational claim; a replication on 2026-08-07/08 (IGS final is
already in the store) follows before any claim. Agreement with IGS final is agreement, not
absolute accuracy.

---

<!-- original: Opus_Fork/results/T2_1_ERP_RESULTS.md -->

## T2.1 results: physical ERP + antenna thrust in the station POD — passes, URE −5.9%, beats NGA

Opus, 22 September 2026 UTC. Protocol frozen before launch: `T2_1_ERP_PROTOCOL.md`.
Campaign `Opus_Fork/runs/20260922T205445Z-fit-P1-erp-31sat`. Evaluation
`Opus_Fork/runs/20260922T215100Z-eval-P1` (`arm_P1_31.json`). Radial decomposition
`…T215145Z-radial-budget-P1` (`radial_budget_P1.json`). Raw, unaligned, against **IGS final**,
2026-08-02, 2,976 satellite-epochs common to N0, P1 and NGA PE (31 satellites).

### Headline

| Full day | 3D cm | **URE cm** | R / A / C cm | Mean R cm | Helmert scale ppb |
|---|---:|---:|---|---:|---:|
| N0 (current model) | 14.114 | 4.427 | 4.06 / 11.57 / 6.99 | +1.66 | +0.62 |
| **P1 (+ ERP + thrust)** | 14.042 | **4.167** | **3.77** / 11.56 / 7.02 | **−0.10** | −0.04 |
| NGA PE | 10.912 | 4.427 | 4.27 / 6.72 / 7.46 | +0.26 | +0.11 |

**Full-day URE improves 5.9% and now beats NGA PE by 5.9% (4.167 vs 4.427).** Nothing in the
model was fitted to IGS or tuned to this day. Along-track and cross-track are unchanged,
because the model is almost purely radial. 3D still loses to NGA: 3D is dominated by
along-track, especially G21's late excursion, which this test does not address.

### Against the frozen predictions

| # | Prediction | Result | |
|---|---|---|---|
| 1 | Mean radial from +1.66 into [−0.3, +0.7] cm; shift = −1.42 ± 0.5 cm | +1.66 → **−0.10**; shift −1.76 | pass |
| 2 | URE improves ≥ 5% (≤ 4.206 cm) | **4.427 → 4.167 (−5.9%)** | pass |
| 3 | No satellite 3D regression > 0.1 m; along/cross change < 5% | worst +0.38 cm (G27); along −0.1%, cross +0.4% | pass |
| 4 | Blocks flatten; IIIA "may go slightly negative"; IIR keeps most positive | IIF +2.09→+0.21, IIR-M +1.87→+0.08, IIR +2.71→+1.42, **IIIA +0.51→−1.30** | partial: IIIA over-corrected by more than "slightly" |
| F | Falsified if the mean moves < 0.7 cm, or it moves and URE improves < 2% | neither | not triggered |

URE improved on 23 of 31 satellites. By block: IIF 4.25 → 3.73, IIR 4.09 → 3.61, IIR-M 4.11 → 3.75,
IIIA 4.99 → 5.11 cm.

### By window

| Window | N0 URE | P1 URE | NGA URE | N0 mean R | P1 mean R |
|---|---:|---:|---:|---:|---:|
| Full 00:00–23:45 | 4.427 | **4.167** | 4.427 | +1.66 | −0.10 |
| Early 00:00–16:00 | 4.241 | **3.950** | 4.251 | +1.68 | −0.09 |
| Late 18:00–23:45 | 4.895 | **4.664** | 4.828 | +1.74 | −0.01 |
| Noon 12:00–18:00 | 3.797 | **4.066** (worse) | 4.506 | +0.32 | −1.46 |

The shift is uniform through the day: −1.77, −1.78 and −1.75 cm in the early, noon and late
windows, which is what a constant radial force should produce. **The noon window gets worse**
because the baseline's pooled radial mean was already only +0.32 cm there. The 12:00–18:00
dip of about 1.4 cm in both arms is a separate, time-varying pooled radial signal, and a
constant correction overshoots it. That dip is unexplained. It is a candidate for the Z-origin
and once-per-rev terms, not for this model. P1 still beats NGA in that window (4.066 vs 4.506).

### The mechanism, satellite by satellite

The shift in each satellite's POD radial constant (P1 − N0) against the shift the same model
produced in the dynamics-only reference fit (E5P − E5, `reference_census_2026-08-02_physics.json`),
over 29 satellites:

- **Pearson 0.98.** The POD shift is 1.22× the reference-fit shift (−1.75 vs −1.43 cm mean), by
  block: IIF −1.88 / −1.56, IIR-M −1.79 / −1.49, IIIA −1.75 / −1.45, IIR −1.28 / −0.92 cm.
- **The larger POD shift is expected.** In the POD the radius is set by the dynamics alone
  (δr ≈ f/3n²). In the reference fit, direct radial observations let the ECOM terms partly
  absorb the added force.

**The data cannot see this change, which is the mechanism working as described.** The
observation objective moved from 13,499.13 (N0) to 13,508.17 (P1): +9.0, or 0.07% of about
65,000 observations. Epoch-wise clocks absorb a common radial shift. So a radial force error of
this kind is invisible in our own residuals and can only be set by physics and checked against
an independent reference. It could never have been found by tuning weights.

### What remains in the radial error (`radial_budget_P1.json`, all 31 satellites)

| Arm | Radial MS cm² | const | 1/rev | 2/rev | rest | Sats with R̄ > 0 |
|---|---:|---:|---:|---:|---:|---:|
| N0 | 16.52 | 4.84 | 6.33 | 0.41 | 4.94 | 28/31 |
| **P1** | **14.19** | **2.39** | 6.49 | 0.40 | 4.91 | 15/31 |
| NGA | 18.27 | 1.65 | 14.44 | 0.25 | 1.93 | 20/31 |

The per-satellite constant halves and changes sign balance (15/31 positive). The 1/rev and
"rest" terms are untouched, as a pure radius correction should leave them. What remains of the
constant is per-satellite scatter:

- G21's along-track-contaminated −5.5 cm;
- IIIA over-correction: G04 −2.19, G23 −2.05, G11 −1.41 cm;
- IIR under-correction: +1.42 cm mean.

The largest radial terms left are now **1/rev (6.5 cm²)** and **rest (4.9 cm², 2.5× NGA's)**.

### The IIIA over-correction

The model gives IIIA the same radius shift as IIF (−1.75 cm), but IIIA's original offset was
about half of IIF's. The model therefore over-drives IIIA by about 0.9 cm (G21 excluded). Its
inputs are the least certain of any block:

- the +Z area is the midpoint of two published box-wing variants (4.0 and 6.0 m²);
- the mass is the metadata value of 2,161 kg, while Steigenberger et al. (2020) report that SRP
  estimates indicate a higher mass and adopt 2,600 kg.

Either would lower IIIA's acceleration. **Nothing is changed in response to this score.** A
revised IIIA input, with its source, may be declared before a *new* test and judged on a date
it was not chosen from. The reflection terms that would raise IIR (absorption-only by design)
fall under the same rule.

### Resources

- 52 workers under fork8. 3,267.2 guarded s (N0: 3,371.5). Peak job memory 576.2 MiB; longest
  worker 91.4 s. Sampled machine peaks: CPU 45.0%, GPU 25.8%. Minimum available memory 14.9 GiB.
- One worker (`lin0-chunk-024-036`) was stopped by the unchanged 75% machine-GPU ceiling when a
  Firefox video-decode spike reached 84.7%. The content-bound resume re-verified and reused
  five workers and reran that one. No limit was changed.
- The campaign manifest keeps the first attempt's `error` text next to the final
  `long_fit_complete` status. That is a resume-bookkeeping leftover: the fit converged.

### R7 — declared replication on 2026-08-07: primary threshold missed

Campaign `Opus_Fork/runs/20260922T215245Z-fit-R7-erp-aug7-25st`: converged in 3 linearizations,
2,790.4 guarded s, peak 480.9 MiB, no interruption. Evaluation
`Opus_Fork/runs/20260922T223956Z-eval-R7` (`arm_R7_aug7.json`). Against IGS final on 2026-08-07,
2,496 samples common to the arms and NGA (26 satellites). Baseline B7 is Astra's converged
expanded25 solution on the same fixture.

| Full day | 3D cm | URE cm | R / A / C cm | Mean R cm | Helmert scale ppb |
|---|---:|---:|---|---:|---:|
| B7 | 11.501 | 3.557 | 3.25 / 7.94 / 7.65 | +1.25 | +0.41 |
| **R7** (+ ERP + thrust) | 11.493 | **3.403** | 3.07 / 7.95 / 7.71 | **−0.50** | −0.25 |
| NGA PE | 10.561 | 4.195 | 4.04 / 6.21 / 7.53 | +0.25 | +0.10 |

| # | Declared | Result | |
|---|---|---|---|
| 1 | Mean R falls 1.0–1.6 cm and ends within ±0.6 | falls **1.75**, ends **−0.50** | end point within bounds; fall above the stated range |
| 2 | URE ≥ 5% better (≤ 3.379) | **−4.3% (3.403)** | **fail** |
| 3 | No > 0.1 m regression; along/cross < 5% | worst +0.45 cm (G02); +0.1% / +0.7% | pass |

By window (URE): early 3.519 → **3.169**, noon 3.321 → **3.218**, late 3.637 → **3.888 (worse)**.
Baseline mean radial by window: +1.62 / +1.02 / +0.44 cm. By block (mean R, URE):

- IIF +1.67 → −0.26, URE 3.44 → 3.01;
- IIR +1.95 → +0.67, URE 4.14 → 3.90;
- IIR-M +0.83 → −0.94, URE 3.80 → 3.84;
- IIIA +0.70 → −1.09, URE 3.20 → 3.26.

URE improved on 12 of 26 satellites.

**Reading across both days.** The model moves the pooled radius by the same amount on both days
(−1.76 on Aug 2, −1.75 on Aug 7), as a fixed physical force should. The baseline offset it acts
on is not fixed: +1.66 on Aug 2 against +1.25 on Aug 7, and within a day it varies by window
from +0.3 to +1.7 cm. Where the baseline offset is smaller than the model's shift, the result
overshoots:

- **IIF** lands within ±0.3 cm on both days. It is the best-described block.
- **IIIA** is over-corrected on both days (−1.30, −1.09). That is consistent with its
  least-certain mass and area inputs.
- **IIR-M** is over-corrected on Aug 7 only.

**Verdict.** ERP + thrust improved full-day URE on both days (−5.9%, −4.3%), with no
satellite regressing by more than 0.5 cm in 3D. It passed its protocol on Aug 2 and missed the
5% bar on the declared replication. It is a real physical improvement. On this evidence it is
not yet a validated ≥5% gain, and part of the pooled radial offset is day- and time-varying,
which a static force model cannot remove. Both failures stand as written. Nothing was retuned.

### Limits and next step

Two days, both previously used in this project, and IGS final is agreement, not absolute truth.
What should come next, each needing its own protocol declared before scoring:

1. **The IIIA inputs.** Declare, from the source, either Steigenberger et al.'s adopted
   2,600 kg or the smaller +Z area. Test on a date not yet scored with ERP (Aug 3–5 have IGS
   final in the store).
2. **The day- and time-varying pooled radial offset**, now the main radial systematic besides
   1/rev. Decompose it by epoch and relate it to the Helmert per-epoch scale and translation,
   and to Sun geometry.
3. **The 1/rev radial term** (6.5 cm² on Aug 2), the largest remaining radial component, which
   is an SRP-modelling target.

---

<!-- original: Opus_Fork/results/IIIA_AUG345_PROTOCOL.md -->

## Protocol: ERP + thrust with the declared IIIA mass fix, on 2026-08-03, 08-04 and 08-05

Opus, 22 September 2026 UTC. **Frozen before any fit on these days.** No orbit from these fixtures
has been fitted or scored. These dates had earlier 14-station bench runs in the project; no score
from those was read to choose anything here.

### What changes, and why only this

Model variant `erp+thrust+iiia2600` (`Opus_Fork/nongrav_variants.py`) is the P1/R7 physics
(`Opus_Fork/nongrav.py`, SHA256 `267b7703…b8fcc4b8`, unchanged) with one declared input change:
**the GPS-IIIA mass goes from 2,161 kg to 2,600 kg**, for both thrust and ERP.

The source is Steigenberger, Thoelert & Montenbruck (2020), Adv Space Res 66:2773. Table 3
states "A satellite mass of 2600 kg is adopted in both models", and footnote b of Table 1 says
"Solar radiation pressure estimates indicate a higher mass". This is the one IIIA input that
paper fixes unambiguously. The +Z area stays at the originally declared midpoint (5.0 m²),
because choosing between its two published values after seeing an over-correction would be
selection by score. Every other block is unchanged.

### Data and fixtures (frozen by availability and parser rules, not scores)

The 11 added stations were acquired on 22 September for 3–5 August
(`Opus_Fork/datastore/2026215..217/`). The 14 core stations and broadcast files are Astra's
inherited copies.

| Day | Stations | Why not 25 | Satellites | Links | Fixture |
|---|---:|---|---:|---:|---|
| Aug 3 | 25 | — | 31 (G13 rejected: no LNAV at arc start) | 32,885 | `Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03` |
| Aug 4 | 23 | CHPI absent from the archive (404); YELL has a RINEX event-4 record the frozen parser refuses | 31 | 30,529 | `…T230119Z-prepare-2026-08-04` |
| Aug 5 | 23 | same | 31 | 30,294 | `…T230410Z-prepare-2026-08-05` |

YELL's exclusion on Aug 4–5 is the same parser limitation the earlier bench recorded. On each
day it was the only station with an event-4 record. Prepare flags are N0's: `--previous-day-nav
--per-epoch-nav`, 144 epochs from 00:00.

### Arms, per day

| Arm | Controller | Force model |
|---|---|---|
| **B** (baseline) | `Opus_Fork.run_fit` (as N0) | unchanged `OrbitForceModel` |
| **P2** | `Opus_Fork.run_fit_ngv --variant erp+thrust+iiia2600` | + ERP + thrust, IIIA 2,600 kg |

Both arms of a day share the fixture, `claude/roadmap/configs/unit-ecom5.json`, 12-epoch chunks,
2 trajectory groups, fork8, 900 s workers, at most 4 linearizations and a zero-correction cold
start. Run order: B3, P2-3, B4, P2-4, B5, P2-5. A failed arm stops the chain; a resume is
explicit and content-bound, and no limit is raised.

### Scoring

`Opus_Fork.evaluate` scores each day against **IGS final**, raw and unaligned, with NGA PE on
the same keys and the domains full, early (00:00–16:00), late (18:00–23:45) and noon
(12:00–18:00). The IIIA analysis uses the per-satellite radial constants from
`Opus_Fork.radial_budget`.

### Predictions

1. **Mechanism, pooled.** On each day the pooled mean radial shifts (P2 − B) by −1.70 ± 0.4 cm.
   The non-IIIA satellites shift about −1.78 cm, IIIA about −1.46 cm, and IIIA is 9 of 31.
2. **Mechanism, IIIA — the test of the fix.** This uses only our own fits, no IGS. The ratio
   of the mean IIIA shift to the mean IIF shift (P2 − B radial constants) is **0.80 ± 0.15**.
   With 2,161 kg it would have been about 0.97 (Aug 2: −1.75 against −1.88 cm).
3. **Primary: URE.** URE against IGS final improves on **every** day, and the mean of the three
   per-day improvements is **≥ 4%**.
4. **IIIA outcome against IGS, honest expectation.** The fix removes only about 0.3 cm of the
   0.9–1.3 cm IIIA overshoot seen on Aug 2/7. The mean IIIA radial (all 9 satellites) after P2
   is therefore expected to remain negative, between −1.3 and 0.0 cm. That is a partial fix, and
   it will be reported as one.
5. **No damage.** No satellite's full-day 3D RMS regresses by more than 0.1 m on any day, and
   pooled along- and cross-track change by less than 5%.

**Falsification.** If the IIIA/IIF shift ratio falls outside 0.65–0.95, the per-block mass
scaling is not acting as modelled. If URE worsens on any day, the physics is not a reliable gain
at this network size.

Also reported, not predicted: the per-day and per-window baseline radial offset. On Aug 2/7 that
day- and time-varying part is what made a fixed correction overshoot.

### Resources

Six fits of about 50–55 guarded minutes each, serial, under fork8 (4 GiB, 50% CPU quota, 75%
sampled machine ceiling, 8 GiB reserve), about 5.5 hours in total. There are three evaluations
plus radial budgets, and a keep-awake request is held while the chain runs.

### Amendment, 23 September 2026 — before any Aug-5 score existed

B-5 stopped because stationarity was not reached within the 4-linearization cap. Its step bound
fell 0.39 → 0.32 → 0.16 mm, with predicted reduction 6.8e-4 against a threshold of 1.3e-4. On the
user's decision, **both Aug-5 arms (B-5 and P2-5) run with a cap of 6 linearizations**, the cap
Astra's cross-date runner uses. The stationarity rule (`customkf/nonlinear_stop.py`), line-search
fractions, tolerances, limits and every scientific setting are unchanged. B-5 resumes from its
four verified linearizations, content-bound. P2-5 runs fresh under the same cap. Aug 3 and 4
(cap 4, both converged in 3) are unaffected. No Aug-5 orbit had been scored when this was written.

---

<!-- original: Opus_Fork/results/IIIA_AUG345_RESULTS.md -->

## Results: ERP + thrust with the IIIA mass fix on 3–5 August — passes on all three days, mean URE −8.3%

Opus, 23 September 2026. Protocol frozen before any fit: `IIIA_AUG345_PROTOCOL.md`. Variant
`erp+thrust+iiia2600` (`Opus_Fork/nongrav_variants.py`), with the GPS-IIIA mass at 2,600 kg per
Steigenberger et al. (2020). Scored raw and unaligned against **IGS final**, with NGA PE on the
same keys, 31 satellites and 2,976 samples per day.

### Status of the six fits

| Arm | Campaign | Status | Linearizations | Guarded s |
|---|---|---|---:|---:|
| B-3 | `Opus_Fork/runs/20260922T230936Z-fit-B-3-25st` | converged | 3 | 3,234 |
| P2-3 | `…-fit-P2-3-25st` | converged | 3 | 3,520 |
| B-4 | `Opus_Fork/runs/20260923T010309Z-fit-B-4-25st` | converged, after 3 external-cause interruptions | 3 | 3,363 |
| P2-4 | `Opus_Fork/runs/20260923T200747Z-fit-P2-4-25st` | converged, after 1 external-cause interruption | 3 | 3,057 |
| B-5 | `Opus_Fork/runs/20260923T210059Z-fit-B-5-25st` | stopped at the 4-linearization cap; resumed under the amended cap of 6 and converged; 2 external interruptions | 5 | 5,167 |
| P2-5 | `Opus_Fork/runs/20260923T230743Z-fit-P2-5-25st` | converged under cap 6 (inside 4); 1 external interruption | 4 | 4,882 |

Interruptions, all external and all resumed content-bound with limits unchanged (chain log
`Opus_Fork/runs/iiia345-chain.status`):

- one transient Windows GPU-telemetry error (`0xc0000bba`);
- two stops at the 75% machine-GPU ceiling from other applications (Firefox 3D engine at 64–94%);
- one loss of every process when the previous session ended.

**B-5 is at the numerical floor, not diverging.** After its first update the step bound is
0.39, 0.32 and then 0.16 mm, and the predicted reduction is 2.4e-3, 2.7e-3 and then 6.8e-4,
against a threshold of 1.3e-4. The cost falls 13,085.02585 → 13,085.02407. This is the same
behaviour as the August-6 candidate. The protocol's cap was 4, so the arm stopped honestly.

### Aug 3 and Aug 4

| Day | Stations | Arm | 3D cm | **URE cm** | R / A / C cm | Mean R cm |
|---|---:|---|---:|---:|---|---:|
| Aug 3 | 25 | B | 11.048 | 4.263 | 4.08 / 7.04 / 7.47 | +1.92 |
| | | **P2** | 10.941 | **3.876 (−9.1%)** | 3.66 / 7.06 / 7.51 | +0.24 |
| | | NGA | 10.780 | 4.289 | 4.13 / 6.29 / 7.72 | |
| Aug 4 | 23 | B | 11.529 | 4.331 | 4.13 / 8.27 / 6.89 | +1.70 |
| | | **P2** | 11.435 | **4.045 (−6.6%)** | 3.82 / 8.25 / 6.93 | +0.02 |
| | | NGA | 10.935 | 4.359 | 4.20 / 6.26 / 7.92 | |

**P2 beats NGA PE on full-day URE on both days** (3.876 vs 4.289; 4.045 vs 4.359). URE improved on
25/31 and 21/31 satellites. In 3D the baseline is already within 2.5–5.4% of NGA, and P2 is within
1.5–4.6%.

#### Against the frozen predictions

| # | Prediction | Aug 3 | Aug 4 | |
|---|---|---|---|---|
| 1 | Pooled mean radial shift −1.70 ± 0.4 cm | −1.68 | −1.68 | pass |
| 2 | **IIIA/IIF shift ratio 0.80 ± 0.15** (own fits only) | **0.806** | **0.802** | pass |
| 3 | URE improves every day; mean improvement ≥ 4% | −9.1% | −6.6% | pass; with Aug 5 (−9.2%) the mean is 8.3% |
| 4 | IIIA mean radial after P2 in [−1.3, 0.0] cm | −0.48 | −0.37 | pass |
| 5 | No > 0.1 m 3D regression; along/cross < 5% | worst +0.49 cm (G04); +0.4 / +0.5% | worst +0.42 cm (G21); −0.2 / +0.7% | pass |

**The IIIA mass fix behaves exactly as the physics says.** IIIA now shifts 0.80× as far as IIF,
where the undeclared-mass model shifted it about 0.97× as far (Aug 2). The IIIA block's URE
improves on both days: 4.00 → 3.91 and 3.86 → 3.75 cm.

On these days IIIA's baseline offset was +1.04 / +1.14 cm, about twice its Aug-2/7 value.
IIIA's offset therefore varies from day to day more than the other blocks' does. With the fix
IIIA ends at −0.48 / −0.37 cm: still slightly over-corrected, as predicted, but no longer the
worst block.

By block, radial constant before → after (cm):

| Block | Aug 3 | Aug 4 | Shift |
|---|---|---|---:|
| IIF | +2.26 → +0.38 | +1.88 → +0.00 | −1.88 |
| IIR-M | +2.28 → +0.47 | +2.01 → +0.22 | −1.80 |
| IIIA | +1.04 → −0.48 | +1.14 → −0.37 | −1.52 |
| IIR | +2.39 → +1.10 | +1.90 → +0.62 | −1.28 |

IIR is still under-corrected on every day, consistent with the absorption-only model leaving out
reflection.

#### What remains in the radial error (`radial_budget_IIIA_aug34.json`)

| Day / arm | Radial MS cm²: const / 1-rev / 2-rev / rest | Sats with R̄ > 0 |
|---|---|---:|
| Aug 3 B | 5.56 / 6.59 / 0.60 / 3.94 | 28/31 |
| Aug 3 P2 | **2.03** / 6.86 / 0.52 / 3.97 | 19/31 |
| Aug 3 NGA | 1.46 / 13.40 / 0.25 / 1.93 | 21/31 |
| Aug 4 B | 4.71 / 6.88 / 0.45 / 5.04 | 28/31 |
| Aug 4 P2 | **1.96** / 7.10 / 0.50 / 5.01 | 13/31 |
| Aug 4 NGA | 1.42 / 14.01 / 0.26 / 1.93 | 19/31 |

The constant term falls about 60% and is now close to NGA's. The 1/rev and "rest" terms are
untouched and are now the largest radial components.

#### The midday dip: now on three days

| Day | Baseline mean radial by window, early / noon / late (cm) |
|---|---|
| Aug 2 | +1.68 / +0.32 / +1.74 |
| Aug 3 | +1.89 / +0.72 / +2.05 |
| Aug 4 | +1.59 / +0.25 / +2.24 |
| Aug 7 | +1.62 / +1.02 / +0.44 (a different shape) |

A fixed physical force moves every window by the same amount, so the noon window, which starts
low, ends negative and its URE worsens slightly (Aug 3 3.171 → 3.256, Aug 4 3.146 → 3.445). This
time-of-day-dependent common radial signal of about 1.2–1.8 cm is the most visible systematic
the model does not address. It is the natural next investigation: epoch-wise Helmert scale and
translation, and its geometry against station coverage and Sun direction.

### Aug 5 (cap of 6, per the amendment declared before any Aug-5 score)

| Arm | 3D cm | **URE cm** | R / A / C cm | Mean R cm |
|---|---:|---:|---|---:|
| B | 11.518 | 4.225 | 4.01 / 7.19 / 8.05 | +1.88 |
| **P2** | **11.426** | **3.836 (−9.2%)** | 3.58 / 7.25 / 8.08 | +0.20 |
| NGA | 11.756 | 4.826 | 4.67 / 7.71 / 7.55 | |

**P2 beats NGA on both URE (3.836 vs 4.826) and 3D (11.426 vs 11.756) on Aug 5.** URE improved
on 23 of 31 satellites.

Checked against the predictions:

- Pooled shift −1.67 cm (prediction 1: pass).
- IIIA/IIF ratio **0.803** (prediction 2: pass).
- Worst 3D regression +0.53 cm (G19); along/cross +0.8% / +0.3% (prediction 5: pass).
- IIIA block mean radial +1.53 → **+0.02 cm** (per-satellite constants +1.54 → +0.03). That is
  **just outside** the predicted [−1.3, 0.0] band, on the favourable side: IIIA is almost
  exactly corrected on this day. IIIA URE 4.09 → 3.83 cm.
- By block, constant before → after (cm): IIF +2.24 → +0.36, IIR-M +1.88 → +0.09,
  IIIA +1.54 → +0.03, IIR +1.63 → +0.36.
- Radial MS const / 1-rev / 2-rev / rest (cm²): B 5.49 / 5.65 / 0.79 / 4.20; P2 **2.02** / 5.85 /
  0.81 / 4.13; NGA 2.13 / 13.80 / 0.58 / 5.27.
- Baseline window means, early / noon / late: +1.56 / **+0.12** / +3.21 cm. The midday dip appears
  again, and noon URE worsens 3.089 → 3.407.

### Verdict across 3–5 August

| Day | Stations | B URE | **P2 URE** | Change | NGA URE | B 3D | P2 3D | NGA 3D |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Aug 3 | 25 | 4.263 | **3.876** | −9.1% | 4.289 | 11.05 | 10.94 | 10.78 |
| Aug 4 | 23 | 4.331 | **4.045** | −6.6% | 4.359 | 11.53 | 11.43 | 10.93 |
| Aug 5 | 23 | 4.225 | **3.836** | −9.2% | 4.826 | 11.52 | 11.43 | 11.76 |

- **Primary (prediction 3): pass.** URE improves every day; the mean improvement is **8.3%**
  against the ≥ 4% bar.
- **The fix's mechanism (prediction 2): pass on every day.** The IIIA/IIF ratio is
  0.806 / 0.802 / 0.803 against 0.80 ± 0.15. The published 2,600 kg mass does exactly what the
  physics says, measured on our own fits alone.
- **Predictions 1 and 5 pass every day.** Prediction 4 passes on two days; on Aug 5 IIIA lands
  at +0.02, 0.02 cm above the band.
- **P2 beats NGA PE on full-day URE on all three days** (by 9.6%, 7.2% and 20.5%), and in 3D on
  Aug 5.

Together with Aug 2 (P1, −5.9%) and Aug 7 (R7, −4.3%), the physical ERP + thrust model has now
improved URE against IGS final on **five of five days**, with no satellite regressing by more than
0.53 cm in 3D. The IIIA mass fix is validated on three dates it was not chosen from.

**What remains**, ranked by URE² now:

1. **The 1/rev radial term**, 5.9–7.1 cm², now the largest radial component. It is an SRP-model
   target: box-wing a priori or an ECOM refinement.
2. **The "rest" term**, 4.0–5.0 cm², about 2–2.5× NGA's. It is observation-driven: arc QC,
   ambiguity resolution, network.
3. **The midday pooled radial dip**, seen on Aug 2, 3, 4 and 5 (noon mean 1.2–1.8 cm below the
   early/late windows). No force-model change touches it, and it makes the noon window worse
   after any constant correction. It is the best-defined next diagnostic.

---

<!-- original: Opus_Fork/results/DIP_AND_NGA_DISTRIBUTIONS.md -->

## The "midday dip" diagnosed, and performance against NGA as distributions

Opus, 24 September 2026 UTC. Evaluation only; no fit.

- Scripts: `Opus_Fork/dip_nga.py` (run `Opus_Fork/runs/20260924T005201Z-dip-nga`, 23 s) and
  `Opus_Fork/dip_mechanism.py` (run `…-dip-mechanism`).
- Evidence: `dip_nga.json`, `dip_mechanism.json`.
- Scope: five days against **IGS final**, with NGA PE on the same satellite-epochs, 14,400 in
  total.

| Day | Baseline | ERP arm | Stations |
|---|---|---|---:|
| Aug 2 | N0 | P1 (erp+thrust) | 25 |
| Aug 3 | B-3 | P2-3 (erp+thrust+iiia2600) | 25 |
| Aug 4 | B-4 | P2-4 (same variant) | 23 |
| Aug 5 | B-5 | P2-5 (same variant) | 23 |
| Aug 7 | Astra's expanded25 | R7 (erp+thrust) | 25 |

---

### Part A — the "midday dip" is a 12-hour oscillation of the constellation's mean height

#### What it is

The "noon window is low" pattern is one face of a **~12 h oscillation of the pooled mean radial
error, locked to UT**. Baseline pooled mean radial by hour (cm):

| UT (h) | 0 | 3 | 6 | 7 | 10 | 13 | 16 | 19 | 22 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Aug 2 | −0.0 | +1.3 | +4.9 | +4.9 | +2.0 | −0.4 | +0.7 | +2.2 | +1.4 |
| Aug 3 | +0.8 | +1.3 | +4.4 | +4.6 | +2.5 | −0.1 | +1.2 | +2.8 | +1.5 |
| Aug 4 | +0.5 | +0.5 | +4.1 | +4.4 | +2.8 | −0.2 | +0.3 | +2.4 | +2.3 |
| Aug 5 | +0.6 | +1.4 | +3.0 | +3.2 | +2.7 | +0.1 | −0.2 | +2.9 | +3.8 |
| Aug 7 | +1.0 | +2.1 | +2.6 | +2.2 | +1.0 | +1.4 | +0.7 | +0.2 | +0.6 |

The peak-to-peak range is 4.7–5.5 cm on Aug 2–5 and 2.7 cm on Aug 7, with a different shape on
Aug 7 (26 satellites, different fixture). The ERP arms carry exactly the same oscillation, shifted
down by the constant ERP correction. That is why a constant correction improves the peaks and
worsens the troughs.

#### What it is not, and what it is tied to

| Check | Finding | Implication |
|---|---|---|
| NGA against IGS on the same keys | range 1.4–2.5 cm, different shape | **not in the IGS reference** |
| Per-epoch Helmert scale against pooled radial | r ≈ 1.00 (0.98 on Aug 7) | a **common, constellation-wide height change**, not a few satellites |
| Satellites whose noon mean falls below their daily mean | 74–81% (Aug 2–5) | broad; all blocks; 5–6 of 6 planes |
| Network coverage by hour | 223–235 links per epoch, 7.2–7.6 stations per satellite, flat | **not tracking geometry** |
| Dynamics-only fits to IGS positions (T1 census, no station data) | same UT shape: +3.4 at 07 h, +0.3 at 13 h, +2.8 at 19 h | **in the force-model representation, not the observations**. The POD roughly doubles its amplitude. |
| Sun-fixed 1/rev per satellite, R ≈ a cos Δu + b sin Δu (declared hypothesis) | correlation with the pooled curve −0.68…+0.11; explains ≈ 0% | **rejected** |
| Same, per block | correlation 0.64–0.88, explains 12–27% | partial at best |
| Earth-fixed (sub-satellite longitude harmonics) | correlation −0.47…+0.63; explains ≈ 0% | **rejected** |

**Which force parameterization reduces it without station data** (Aug 2 census, 12 h amplitude
of the pooled residual):

| Variant | Pooled mean | 24 h amplitude | **12 h amplitude** |
|---|---:|---:|---:|
| E5 (current ECOM5) | +1.75 | 0.32 | **1.33** |
| E5T (+ thrust) | +1.20 | 0.31 | 1.26 |
| E5P (+ physical ERP + thrust) | +0.33 | 0.32 | 1.22 |
| E5R / E5PR (+ fitted radial constant) | 0.00 | 0.32–0.33 | 1.20–1.24 |
| **E7 (ECOM-7: adds Dc2/Ds2, twice per revolution in the Sun direction)** | +1.65 | 0.30 | **0.57 (−57%)** |

**Diagnosis.** The 12 h common-height oscillation is a solar-radiation-pressure parameterization
limit. ECOM5 cannot represent a Sun-direction acceleration that varies twice per revolution.
The missing term is the D2 family CODE added in ECOM2. The radial, ERP and thrust changes act on
the mean and leave the oscillation untouched. The simple Sun-fixed-1/rev mechanism I proposed
first does not reproduce it.

#### Consequence for the NGA comparison (Part B)

The hours where we lose to NGA cluster at **00–08 UT**, the positive peak of this oscillation:

| Day | Hours worse than NGA |
|---|---|
| Aug 2 | 0–2, 6–7, 23 |
| Aug 3 | 0–2, 6–8, 23 |
| Aug 4 | 0–8 |
| Aug 5 | 23 |

Removing the oscillation would convert most of those hours.

#### Next test (proposed, not run)

Estimate Dc2/Ds2 in the station POD (ECOM-7) on top of `erp+thrust+iiia2600`, over the same
five days against their baselines. Proposed predictions, to be frozen before running:

- the 12 h amplitude of the pooled radial falls by ≥ 40%;
- the noon window no longer worsens against the baseline;
- URE improves beyond the ERP arms on at least 4 of 5 days.

Implementation needs a fork-side pilot with the `count == 7` model and two extra estimated
columns; `LongPilot` names only the five ECOM5 terms.

---

### Part B — performance against NGA PE, as distributions

Per satellite-epoch orbit-only URE = sqrt(0.98²R² + (A²+C²)/49). Raw and unaligned; NGA is
WGS84 against the IGc20 reference. Samples are correlated in time, so shares are descriptive.

#### Pooled over all five days (14,400 satellite-epochs)

| Metric | Our ERP arm | Our baseline | NGA PE |
|---|---:|---:|---:|
| **Share of satellite-epochs where our URE < NGA's** | **54.7%** | 50.7% | — |
| URE RMS | **3.89 cm** | 4.19 | 4.43 |
| URE median (p50) | **2.72** | 2.98 | 3.02 |
| p68 | **3.68** | 4.12 | 4.05 |
| p90 | **6.07** | 6.60 | 6.36 |
| p95 | **7.34** | 7.87 | 7.55 |
| **p99** | **10.67** | 10.92 | **14.68** |
| Share with URE < 2 cm | **33%** | 29% | 27% |
| < 3 cm | **56%** | 50% | 50% |
| < 5 cm | **83%** | 78% | 80% |
| < 7.5 cm | 95% | 94% | 95% |
| Share of satellite-epochs where our **3D** error < NGA's | 49.8% | 49.0% | — |
| 3D median / p90 / p95 | 8.79 / 16.59 / 19.92 | 8.90 / 16.67 / 20.20 | 8.86 / 16.54 / 19.37 |

**Reading.**

- **With ERP, our URE is lower than NGA's at every percentile.** The gap is largest in the tail:
  our 99th percentile is 10.7 cm against NGA's 14.7, and our worst single sample on any day is
  12–18 cm against NGA's 20–53 cm.
- **For a single satellite at a single epoch, ours is the lower URE 55% of the time.** That is a
  modest but consistent edge. In 3D it is a coin flip.
- The baseline, before ERP, was essentially level with NGA on URE: 50.7% of samples, median
  2.98 against 3.02.

#### Per day, ERP arm against NGA

| Day | URE lower on % of samples | Median / p95 / p99, ours (cm) | Median / p95 / p99, NGA (cm) | < 3 cm, ours / NGA | Satellites better (daily RMS) | 15-min epochs better (constellation RMS) | Hours better |
|---|---:|---|---|---:|---:|---:|---:|
| Aug 2 | 56.8% | 2.80 / 8.17 / 13.62 | 3.21 / 7.66 / 13.88 | 54% / 45% | 19/31 | 69/96 | 18/24 |
| Aug 3 | 50.0% | 3.01 / 7.13 / 9.77 | 2.92 / 7.41 / 15.10 | 50% / 52% | 18/31 | 69/96 | 17/24 |
| Aug 4 | 54.0% | 2.75 / 7.75 / 11.13 | 3.12 / 7.15 / 15.05 | 55% / 47% | 18/31 | 58/96 | 15/24 |
| Aug 5 | 54.9% | 2.55 / 7.23 / 10.64 | 2.95 / 8.34 / 15.02 | 58% / 51% | 20/31 | **91/96** | **23/24** |
| Aug 7 | 58.2% | 2.43 / 6.39 / 9.23 | 2.85 / 7.57 / 14.19 | 64% / 53% | 16/26 | 80/96 | 20/24 |

- **Constellation-wide at any instant:** our constellation RMS URE beats NGA's in **58–91 of 96**
  fifteen-minute epochs per day, 367 of 480 over the five days (76%).
- **Per hour:** we beat NGA in 15–23 of 24 hours per day, 93 of 120 over the five days (78%).
  The losses sit at 00–08 UT (Part A).
- **Per satellite:** 16–20 satellites per day beat NGA's daily RMS URE, 91 of 150 satellite-days
  (61%). The recurring losers are G05 (on four of five days), G21, G27 and G08. These are
  individual-satellite problems, not constellation-wide ones.
- **Frame-neutral diagnostic:** after a per-epoch Helmert fit on each side, the paired share is
  51.0–56.4% per day. The ordering is not an artefact of NGA's WGS84 frame offset.

#### What this says about the claim

- **URE: we beat NGA as a distribution.** The margin is modest at the median (10% lower) and
  larger at the tail (27% lower at p99), with a 55% paired win rate.
- **3D: we do not beat NGA.** The paired share is 49.8%, and the tail is slightly worse
  (p95 19.9 vs 19.4 cm), because along-track dominates 3D and is not what the radial work
  addressed.
- All five days were previously used in this project, and IGS final is agreement, not absolute
  truth.

---

<!-- original: Opus_Fork/results/ECOM7_PROTOCOL.md -->

## Protocol: ECOM-7 (adding Dc2/Ds2) in the station POD, on 2, 3, 4, 5 and 7 August

Opus, 24 September 2026 UTC. **Frozen before any ECOM-7 station fit existed.**

### Why

`DIP_AND_NGA_DISTRIBUTIONS.md` found three things:

- The baseline's pooled mean radial oscillates with a ~12 h period, locked to UT. The 12 h
  harmonic amplitude is **1.74–1.95 cm on Aug 2–5**, identical in the baseline and ERP arms,
  against 0.34–0.73 cm for NGA.
- The oscillation is present in dynamics-only fits to IGS positions, and our hours lost to NGA
  cluster at its 00–08 UT peak.
- Of every force variant fitted to IGS positions, only **ECOM-7** (the Sun-direction
  twice-per-revolution terms Dc2/Ds2) reduced it: 12 h amplitude 1.33 → 0.57 cm (−57%).

The question: does estimating Dc2/Ds2 in the station POD remove the oscillation and improve URE?

### Arms

For each day, one new arm **E7** is compared with that day's existing ERP arm (ECOM5 + the same
ERP variant), with its baseline B, and with NGA PE. E7 differs from the ERP arm **only** in
estimating ECOM-7.

| Day | Fixture | ERP variant (unchanged from the day's ERP arm) | ERP arm | Baseline | Chunks / groups |
|---|---|---|---|---|---|
| Aug 2 | `Opus_Fork/runs/20260920T200910Z-prepare-31sat` | `erp+thrust` | P1 | N0 | 12 / 2 |
| Aug 3 | `…T225652Z-prepare-2026-08-03` | `erp+thrust+iiia2600` | P2-3 | B-3 | 12 / 2 |
| Aug 4 | `…T230119Z-prepare-2026-08-04` | same | P2-4 | B-4 | 12 / 2 |
| Aug 5 | `…T230410Z-prepare-2026-08-05` | same | P2-5 | B-5 | 12 / 2 |
| Aug 7 | `runs/20260920T155655Z-7b703635` (Astra's) | `erp+thrust` | R7 | Astra's expanded25 | 18 / 4 |

ECOM-7 is the existing `OrbitForceModel(count=7)`: D0, Y0, B0, Bc1, Bs1, Dc2, Ds2. It is the
model the census E7 used. Its B and D harmonics are referenced to the Sun's in-plane direction
rather than the node. All seven are estimated per satellite, from nominal D0 = −1e-7 m/s² with
the rest zero, with no priors. Config: `Opus_Fork/experiments/ecom7/config_ecom7.json`.

Controller `Opus_Fork.run_fit_e7`. Workers `e7_traj_cache` and `e7_iteration` apply ECOM-7 at
runtime: they patch module constants in the worker process, and the one hardcoded ECOM5 tuple in
the step-bound code is replaced in the copy `iteration7.py`. No pinned file is edited. Every
cache and worker carries a force-model binding (variant, ECOM count, source hashes), and a
mismatch is refused.

Settings match the day's ERP arm: fork8, 900 s workers, zero-correction cold start, unchanged
stationarity rule. The linearization cap is 6 on all five days, declared now because Aug 5
needed it. Order: Aug 2, 3, 4, 5, 7. Only external-load stops (usage ceiling or telemetry) are
waited out and resumed automatically; any other failure stops the chain.

### Scoring

`Opus_Fork.evaluate` against IGS final, with NGA on the same keys (full, early, noon, late).
`Opus_Fork.dip_nga`-style hourly pooled radial, with 12 h and 24 h harmonic amplitudes, plus the
NGA distribution metrics (paired share, percentiles, per-epoch, per-hour and per-satellite wins).

### Predictions

1. **Mechanism.** On each of Aug 2–5 the 12 h amplitude of the pooled hourly mean radial falls by
   **≥ 40%** against the ERP arm (1.74–1.95 cm → ≤ 1.05–1.17 cm). Aug 7 has almost no 12 h term
   (0.47 cm) and is only reported.
2. **Noon window.** E7's noon URE (12:00–18:00) is at or below the baseline's on **≥ 3 of 4** of
   Aug 2–5. The ERP arms worsened noon on all four.
3. **Primary: URE.** Full-day URE of E7 is lower than the ERP arm's on **≥ 4 of 5** days.
4. **No damage.** No satellite's full-day 3D RMS regresses by more than 0.1 m against the ERP
   arm on any day.

**Falsification.** If the 12 h amplitude falls by less than 20% on a majority of Aug 2–5, the
census finding does not transfer to the station POD and the dip needs another explanation. Two
extra parameters per satellite can also absorb observation errors. If URE worsens on 2 or more
days, ECOM-7 is not an improvement at this network size, whatever it does to the oscillation.

### Resources

Five fits of about 60–80 guarded minutes each (two more parameters per satellite; possibly more
linearizations), about 6 h serial, under fork8 (4 GiB, 50% CPU quota, 75% machine ceiling, 8 GiB
reserve), with keep-awake held throughout.

---

<!-- original: Opus_Fork/results/ECOM7_RESULTS.md -->

## ECOM-7 in the station POD — FALSIFIED on 2 of 2 days run: the swing shrinks 30–37%, URE worsens 17–30%

Opus, 24 September 2026 UTC. Protocol: `ECOM7_PROTOCOL.md`, frozen before any fit. The chain
(`Opus_Fork/experiments/ecom7/run_chain_e7.ps1`, log `Opus_Fork/runs/ecom7-chain.status`) was paused overnight at the user's request,
resumed for Aug 3 only, and then **concluded**: the falsification rule was met.

### Status

| Arm | Campaign | Status |
|---|---|---|
| E7-2 (Aug 2) | `Opus_Fork/runs/20260924T010239Z-fit-E7-2-25st` | **converged**, 3 linearizations |
| E7-3 (Aug 3) | `Opus_Fork/runs/20260924T021610Z-fit-E7-3-25st` | **converged**, 3 linearizations, 3,892 guarded s. Three external interruptions, all resumed content-bound: the user's overnight stop, one GPU-ceiling stop, one memory-headroom refusal while a game ran. |
| E7-4, E7-5, E7-7 | — | **not run**: the protocol's falsification rule was met after Aug 3 |

### Aug 2, against IGS final

Evaluation: `Opus_Fork/runs/*-eval-E7-2`, `arm_E7_aug2.json`.

| Arm | 3D cm | URE cm | R / A / C cm |
|---|---:|---:|---|
| P1 (ERP, ECOM5) | 14.042 | **4.167** | 3.77 / 11.56 / 7.02 |
| **E7 (ERP, ECOM-7)** | 15.270 | **5.397 (+29.5%)** | **5.09** / 11.73 / **8.34** |
| NGA PE | 10.912 | 4.427 | 4.27 / 6.72 / 7.46 |

URE by window, P1 → E7:

| Window | P1 | E7 |
|---|---:|---:|
| Early | 3.950 | 5.250 |
| Noon | 4.066 | 5.376 |
| Late | 4.664 | 5.938 |

Pooled hourly mean radial (`Opus_Fork/runs/*-e7-quick-dip`):

| Arm | 12 h amplitude | 24 h amplitude | Mean |
|---|---:|---:|---:|
| P1 | 1.95 | 1.16 | −0.10 |
| E7 | **1.22 (−37%)** | 0.93 | −0.05 |
| NGA | 0.71 | 0.29 | +0.26 |

### Against the predictions, on Aug 2 only

| # | Prediction | Aug 2 | |
|---|---|---|---|
| 1 | 12 h amplitude falls ≥ 40% | −37% | **miss** (close) |
| 2 | Noon URE ≤ baseline's (3.797) | 5.376 | **fail** |
| 3 | Full-day URE below the ERP arm (≥ 4 of 5 days) | +29.5% | fails on this day |
| 4 | No satellite 3D regression > 0.1 m | not yet checked | — |

**Reading.** The census finding partly transfers: estimating Dc2/Ds2 removes about a third of the
12 h common-height swing. But with station data those two extra parameters per satellite are
weakly determined. They trade against radial position, radial RMS rises 35%, and cross-track
rises 19%. This is the failure mode the protocol named ("extra parameters can absorb observation
errors"). Freely estimated ECOM-7 does not suit this 25-station, 24 h configuration.

**Falsification status after Aug 2 (superseded by the verdict below).** The protocol's rule is URE worsening on two or more days. With one day
at +30%, that needs one more worsening day; the remaining four fits (about 5 h) would settle
it. Worth weighing first: a +30% radial degradation is unlikely to reverse on other days, and
the better-motivated follow-ups are either Dc2/Ds2 **with priors** (constrained, as CODE-style
processing does) or a **fixed a-priori box-wing SRP** model, which adds the physics without the
free parameters. Either needs its own protocol.

### Aug 3 — and the verdict

Evaluation: `Opus_Fork/runs/*-eval-E7-3`, `arm_E7_aug3.json`. Swing check:
`Opus_Fork/runs/*-e7-quick-dip-3`.

| Arm | 3D cm | URE cm | R / A / C cm | Noon URE |
|---|---:|---:|---|---:|
| Baseline B-3 | 11.048 | 4.263 | 4.08 / 7.04 / 7.47 | 3.171 |
| P2-3 (ERP + IIIA fix, ECOM5) | 10.941 | **3.876** | 3.66 / 7.06 / 7.51 | 3.256 |
| **E7-3 (same, ECOM-7)** | 11.217 | **4.530 (+16.9% vs P2; worse than baseline)** | 4.37 / 7.45 / 7.15 | 4.203 |
| NGA PE | 10.780 | 4.289 | 4.13 / 6.29 / 7.72 | 4.195 |

12 h amplitude of the pooled radial: P2 1.82 → E7 **1.28 cm (−30%)**; NGA 0.34.

| # | Prediction | Aug 2 | Aug 3 | |
|---|---|---|---|---|
| 1 | 12 h amplitude falls ≥ 40% | −37% | −30% | **fail** (partial effect; the < 20% mechanism-falsification line is not crossed) |
| 2 | Noon URE ≤ baseline's on ≥ 3 of 4 days | 5.376 vs 3.797 | 4.203 vs 3.171 | **fail** |
| 3 | Full-day URE below the ERP arm on ≥ 4 of 5 days | +29.5% | +16.9% | **fail** (cannot reach 4 of 5) |
| 4 | No satellite 3D regression > 0.1 m against the ERP arm | G30 +18.6 cm | worst +5.7 cm (G30) | **fail** on Aug 2 |
| F | Falsified if URE worsens on ≥ 2 days | worse | worse | **met** |

**Verdict.** Freely estimated ECOM-7 (Dc2/Ds2) is **not an improvement** in the 25-station,
24 h station POD. It does act on the target: it removes 30–37% of the 12 h common-height swing,
which confirms that the swing is a Sun-direction twice-per-revolution SRP effect. But the two free
parameters per satellite are weakly determined from station data and cost far more in radial
accuracy than they recover. URE is better on only 14–15 of 31 satellites, and some, G30 above
all, are badly damaged. Following the protocol, Aug 4, 5 and 7 were not run.

**What this points to.** The physics (Sun-direction 2/rev acceleration) belongs in the model, but
as known a-priori forces, not free parameters. There are two routes:

- **(a) A fixed box-wing SRP a priori** from the published geometry and optical properties already
  cited in `nongrav.py`. It adds no parameters, so the ECOM5 set stays unchanged.
- **(b) Dc2/Ds2 with tight priors**, centred on zero or on a-priori values.

Route (a) is preferred. Each needs its own protocol. Before any station fit, the census (dynamics
fitted to IGS positions) can test cheaply whether a box-wing a priori reduces the 12 h swing
without the free terms.

---

<!-- original: Opus_Fork/results/ECOM7P_PROTOCOL.md -->

## Protocol: ECOM-7 with priors on Dc2/Ds2 (σ = 2 nm/s²) in the station POD, 2 and 3 August

Opus, 25 September 2026 UTC. **Frozen before any constrained fit existed.**

### Why

- Free Dc2/Ds2 remove 30–37% of the 12 h common-height swing but worsen URE by 17–30%
  (`ECOM7_RESULTS.md`). With 25 stations over 24 h the two extra terms per satellite are weakly
  determined, and they trade against radial position.
- A fixed published box-wing removes only 11% of the swing (`BOXWING_CENSUS_RESULTS.md`).
- The dynamics-only census measured the size the terms need when fitted straight to IGS
  positions: |D2| ≈ 1.5 (IIF), 2.2 (IIIA), 2.4 (IIR) and 2.3 (IIR-M) nm/s².

A zero-centred prior of that size should let Dc2/Ds2 take their physical values while stopping
them from absorbing station noise.

### What changes

Only the config: `Opus_Fork/experiments/ecom7/config_ecom7_prior2.json` =
`{"nominal":"unit","estimate":[0..6],"prior_sigma_mps2":{"5":2e-9,"6":2e-9}}`.

- This is `LongPilot`'s existing force-prior mechanism: a zero-centred pseudo-observation on each
  satellite's Dc2 and Ds2 correction, σ = 2e-9 m/s².
- The value 2 nm/s² is the census scale above, fixed now and not tuned afterwards on these days.
- D0, Y0, B0, Bc1 and Bs1 stay unconstrained, as before.

Everything else is identical to the free ECOM-7 arms E7-2 and E7-3: controller `run_fit_e7`, the
same ERP variant per day (`erp+thrust` on Aug 2, `erp+thrust+iiia2600` on Aug 3), fixture,
12-epoch chunks, 2 trajectory groups, fork8, cap 6, cold start, and the unchanged stationarity
rule.

### Arms and comparators

| Day | New arm | ERP arm (ECOM5) | Free ECOM-7 | Baseline |
|---|---|---|---|---|
| Aug 2 | E7P-2 | P1: URE 4.167, radial 3.77, 12 h amplitude 1.95 | E7-2: 5.397, 5.09, 1.22 | N0: 4.427 |
| Aug 3 | E7P-3 | P2-3: URE 3.876, radial 3.66, 12 h amplitude 1.82 | E7-3: 4.530, 4.37, 1.28 | B-3: 4.263 |

All are scored against IGS final with NGA on the same keys. The 12 h amplitude is that of the
pooled hourly mean radial.

### Predictions

1. **Primary.** Full-day URE is no worse than the ERP arm's plus 1% on **both** days
   (≤ 4.209 and ≤ 3.915 cm), and at least 10% better than the free ECOM-7 arm on both.
2. **Swing.** The 12 h amplitude falls by **≥ 15%** against the ERP arm on both days
   (≤ 1.66 and ≤ 1.55 cm).
3. **No damage.** Radial RMS is at most the ERP arm's plus 3%, and no satellite's 3D RMS regresses
   by more than 0.1 m against the ERP arm.
4. **Priors hold.** At least 90% of satellites end with |Dc2| and |Ds2| within 3σ (6 nm/s²).

**Falsification.** URE worse than the ERP arm by more than 3% on either day means constrained
ECOM-7 at σ = 2 nm/s² is not viable here. No other σ will be tried on these two days.
Predictions 1 and 3 passing together with prediction 2 failing would mean the priors simply
switch the terms off: harmless, but not a fix for the swing.

### Resources

Two fits of about 70–80 guarded minutes each, serial, under fork8 with keep-awake. The chain
`Opus_Fork/experiments/ecom7/run_chain_e7p.ps1` waits out external GPU/memory load, and can be
stopped and resumed with `Opus_Fork/resume_chain.ps1 -Chain ecom7p`.

---

<!-- original: Opus_Fork/results/ECOM7P_RESULTS.md -->

## Constrained ECOM-7 (Dc2/Ds2 priors σ = 2 nm/s²) in the station POD — all four predictions pass on both days (URE −2.9% / −6.1%)

Opus, 25 September 2026 UTC. Protocol: `ECOM7P_PROTOCOL.md`, frozen before any constrained fit.
Chain `Opus_Fork/experiments/ecom7/run_chain_e7p.ps1`, log `Opus_Fork/runs/ecom7p-chain.status`.

### Status

| Arm | Campaign | Status |
|---|---|---|
| E7P-2 (Aug 2) | `Opus_Fork/runs/20260925T014057Z-fit-E7P-2-25st` | **converged**, 3 linearizations (last step 0.016 mm), 4,401 guarded s, peak 622 MiB, min free 14.4 GiB. One GPU-ceiling stop at lin0-chunk-132-144, resumed content-bound. |
| E7P-3 (Aug 3) | `Opus_Fork/runs/20260925T025949Z-fit-E7P-3-25st` | **converged**, 3 linearizations (last step 0.006 mm), 4,090 guarded s, peak 624 MiB, min free 14.6 GiB. Interrupted at lin2-chunk-096-108: the guard refused the next worker because another project's Python processes had started (an app server on port 5077 and a browser-driver script; neither is a campaign). The chain waited about 10 h for them to exit (00:08–10:12), then resumed content-bound. |

**Orchestration change (no scientific file touched).** `run_chain_e7p.ps1` now treats the guard's
"Another Python process is running" refusal as an external stop. It waits for GPU below 50%,
at least 12.5 GiB free and **no Python process** for 3 min, and checks that condition before starting each fit.
`resume_chain.ps1` gained `-WaitIfBusy` (ecom7p only) so the chain can be launched while an unrelated
Python process runs; the guard's other-Python rule itself is unchanged.

### Aug 2, against IGS final (2,976 common satellite-epochs, 31 satellites)

Evaluation `Opus_Fork/runs/20260925T040552Z-eval-E7P-2`, copied to `results/arm_E7P_aug2.json`.
(The evaluator's "ECOM5" candidate description is a fixed string; E7P is ECOM-7.)

| Arm | 3D cm | URE cm | R / A / C cm | URE sats beating NGA |
|---|---:|---:|---|---:|
| P1 (ERP, ECOM5) | 14.042 | 4.167 | 3.77 / 11.56 / 7.02 | 19/31 |
| E7 (ERP, free ECOM-7) | 15.270 | 5.397 | 5.09 / 11.73 / 8.34 | — |
| **E7P (ERP, ECOM-7, priors)** | **13.843** | **4.047** | **3.64** / 11.51 / **6.78** | **20/31** |
| NGA PE | 10.912 | 4.427 | 4.27 / 6.72 / 7.46 | — |

URE by window (P1 → E7P): early 3.950 → **3.818**, noon 4.066 → **3.988**, late 4.664 → **4.575**.
E7P is better than P1 in every window and every component.

Pooled hourly mean radial (`Opus_Fork/runs/20260925T040615Z-dip-E7P-2`, copied to
`results/quick_dip_E7P_aug2.json`; the script labels the new arm "E7"):

| Arm | 12 h amplitude | 24 h amplitude | Mean |
|---|---:|---:|---:|
| P1 | 1.95 | 1.16 | −0.10 |
| E7 (free) | 1.22 | 0.93 | −0.05 |
| **E7P** | **1.63 (−16%)** | 1.07 | −0.05 |
| NGA | 0.71 | 0.29 | +0.26 |

**Estimated Dc2/Ds2** (acceleration = a-priori + 1e-7 · x). E7P: median |D2| **1.5 nm/s²**, largest
component G30 Dc2 = −3.8 nm/s², **0 of 31** satellites beyond 6 nm/s². Free E7: median |D2| 2.5,
largest 13.6 nm/s² (G30). The constrained values sit at the dynamics-only census scale (1.5–2.4).

**Fit cost** (whitened, final linearization): P1 13,508; E7P 13,435 (includes the 62 prior rows);
E7 13,374.

**Per satellite against P1.** 21 of 31 improve in URE. The largest 3D regressions are G30 +4.0 cm and G16 +3.2 cm;
none approaches 10 cm. G30 remains the weak case: its URE goes 2.50 → 5.29 cm under E7P, against 14.59 under free
E7. It carries the largest Dc2. The biggest gains are G29 (3D −6.9 cm, URE 2.97 → 1.96) and G27 (3D −4.6, URE 5.40 → 3.59).

#### Predictions, Aug 2

| # | Prediction | Aug 2 | |
|---|---|---|---|
| 1 | URE ≤ 4.209 and ≥ 10% better than free E7 | 4.047 (−2.9% vs P1); −25.0% vs E7 | **pass** |
| 2 | 12 h amplitude ≤ 1.66 | 1.63 (−16%) | **pass** (narrowly) |
| 3 | Radial ≤ 3.88; no satellite 3D regression > 0.1 m | 3.64; max +4.0 cm (G30) | **pass** |
| 4 | ≥ 90% of satellites with \|Dc2\|, \|Ds2\| ≤ 6 nm/s² | 31/31 | **pass** |

### Aug 3, against IGS final (2,976 common satellite-epochs, 31 satellites)

Evaluation `Opus_Fork/runs/20260925T141828Z-eval-E7P-3`, copied to `results/arm_E7P_aug3.json`.

| Arm | 3D cm | URE cm | R / A / C cm | URE sats beating NGA |
|---|---:|---:|---|---:|
| P2-3 (ERP + IIIA 2600, ECOM5) | 10.941 | 3.876 | 3.66 / 7.06 / 7.51 | 18/31 |
| E7-3 (free ECOM-7) | 11.217 | 4.530 | 4.37 / 7.45 / 7.15 | — |
| **E7P-3 (ECOM-7, priors)** | **10.189** | **3.640** | **3.44** / 7.13 / **6.42** | 15/31 |
| NGA PE | 10.780 | 4.289 | 4.13 / 6.29 / 7.72 | — |

**E7P-3 beats NGA in 3D on this day** (0.945× NGA) as well as URE. That is the first 3D win on Aug 3.
URE by window (P2 → E7P): early 3.868 → **3.592**, noon 3.256 → **2.994**, late 4.039 → **3.950**.

12 h amplitude (`Opus_Fork/runs/20260925T141855Z-dip-E7P-3`, `results/quick_dip_E7P_aug3.json`):
P2 **1.82 → 1.53 (−16%)**; free E7 1.28; NGA 0.34.

Dc2/Ds2: E7P median |D2| **1.5 nm/s²**, largest 4.5 (G29), **0 of 31** beyond 6. Free E7: median 2.8, largest 9.9.

Per satellite: 17 of 31 improve in URE. The gains concentrate on the worst satellites: G29 4.87 → 3.55, G05 6.80 → 5.37,
G19 4.43 → 3.19. That is why the total improves while the count of satellites beating NGA falls from 18 to 15. The
largest 3D regressions are G27 +2.6 cm and G12 +1.7 cm.

#### Predictions, Aug 3

| # | Prediction | Aug 3 | |
|---|---|---|---|
| 1 | URE ≤ 3.915 and ≥ 10% better than free E7 | 3.640 (−6.1% vs P2); −19.6% vs E7 | **pass** |
| 2 | 12 h amplitude ≤ 1.55 | 1.53 (−16%) | **pass** (narrowly) |
| 3 | Radial ≤ 3.77; no satellite 3D regression > 0.1 m | 3.44; max +2.6 cm (G27) | **pass** |
| 4 | ≥ 90% of satellites with \|Dc2\|, \|Ds2\| ≤ 6 nm/s² | 31/31 | **pass** |

### Verdict on 2 and 3 August

**All four predictions pass on both days; the falsification rule is not met.** Holding Dc2/Ds2 to their
physical size, as fitted to IGS positions, keeps about half of the swing reduction that free ECOM-7 gave
(−16% against −30 to −37%) without its URE penalty. It lowers URE, radial and cross-track against the
ECOM5 arms on both days. The priors do what they were meant to do: the estimates settle at the census
scale (median 1.5 nm/s²) instead of the free fit's 2.5–2.8 with outliers to 10–14.

Both days were used to choose this approach, so they do not validate it. The held-out test on 4, 5 and
7 August (`ECOM7P_HOLDOUT_PROTOCOL.md`, frozen before those fits) decides adoption.

---

<!-- original: Opus_Fork/results/ECOM7P_HOLDOUT_PROTOCOL.md -->

## Protocol: constrained ECOM-7 (Dc2/Ds2 priors σ = 2 nm/s²) on held-out days 4, 5 and 7 August

Opus, 25 September 2026 UTC. **Frozen before any E7P-4, E7P-5 or E7P-7 fit existed.** The user
approved running these days ("go ahead and run those").

### Why

On 2 and 3 August the constrained arm passed all four predictions of `ECOM7P_PROTOCOL.md`
(`ECOM7P_RESULTS.md`):

| Day | URE vs ECOM5 arm | vs free ECOM-7 | 12 h amplitude | Radial |
|---|---:|---:|---:|---:|
| Aug 2 | 4.167 → 4.047 (−2.9%) | −25% | 1.95 → 1.63 (−16%) | 3.77 → 3.64 |
| Aug 3 | 3.876 → 3.640 (−6.1%) | −20% | 1.82 → 1.53 (−16%) | 3.66 → 3.44 |

Those two days were used to choose the approach. Before this configuration becomes the fork's default, it has to
repeat on days that played no part in choosing it. Held out here: 4, 5 and 7 August.

### What runs

Nothing changes but the day. Controller `Opus_Fork.run_fit_e7`, config
`Opus_Fork/experiments/ecom7/config_ecom7_prior2.json` (unchanged, σ = 2e-9 m/s² on columns 5–6),
12-epoch chunks, 2 trajectory groups, fork8, cap 6, cold start, unchanged stationarity rule.
Each arm uses **the same ERP variant as its existing ECOM5 comparator**, so the only difference is
the SRP parameterization:

| Day | New arm | Variant | Fixture | Comparator (ECOM5) | Baseline |
|---|---|---|---|---|---|
| Aug 4 | E7P-4 | `erp+thrust+iiia2600+ecom7` | `Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04` | P2-4 `20260923T200747Z-fit-P2-4-25st`: URE 4.045, radial 3.82, 12 h 1.93 | B-4 4.331 |
| Aug 5 | E7P-5 | `erp+thrust+iiia2600+ecom7` | `Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05` | P2-5 `20260923T230743Z-fit-P2-5-25st`: URE 3.836, radial 3.58, 12 h 1.74 | B-5 4.225 |
| Aug 7 | E7P-7 | `erp+thrust+ecom7` | `runs/20260920T155655Z-7b703635` (Astra's cross-date fixture) | R7 `20260922T215245Z-fit-R7-erp-aug7-25st`: URE 3.403, radial 3.07, 12 h 0.47 | B7 3.557 |

R7 predates the IIIA mass fix, so E7P-7 matches it (`erp+thrust`). It isolates the ECOM-7 change;
the combined default (IIIA 2600 kg + constrained ECOM-7) is exercised on Aug 3, 4 and 5. R7 ran
with 18-epoch chunks and 4 groups. Chunking only partitions the streamed normal equations, so it is
kept at 12/2 like every E7/E7P arm.

All three are scored with `Opus_Fork.evaluate` against IGS final, with NGA PE on the same keys and
the same four windows (full, early, late, noon). The 12 h amplitude is that of the pooled hourly mean
radial (`Opus_Fork.experiments.ecom7.quick_dip`).

### Predictions

1. **Primary (adoption gate).** URE is below the comparator on **at least 2 of 3** days, **no** day
   is worse by more than 1%, and the mean URE change over the three days is **≤ −2%**.
2. **Swing.** On Aug 4 and 5 the 12 h amplitude falls by **≥ 10%** (≤ 1.74 and ≤ 1.57 cm). On Aug 7
   the ECOM5 arm has almost no swing (0.47 cm, unlike Aug 2–5). There the prediction is that E7P
   does not create one: **≤ 0.60 cm**.
3. **No damage.** Radial RMS is at most the comparator's plus 3% (≤ 3.93, 3.69 and 3.16 cm), and no
   satellite's 3D RMS regresses by more than 0.1 m.
4. **Priors hold.** Each day, at least 90% of satellites end with |Dc2| and |Ds2| ≤ 6 nm/s².

**Falsification.** URE worse than the comparator by more than 3% on any held-out day means
constrained ECOM-7 is **not** adopted. σ will not be retuned on these days.

**Adoption.** If 1, 3 and 4 pass, constrained ECOM-7 at σ = 2 nm/s² becomes the default force model
for new fork fits, with `erp+thrust+iiia2600`. Prediction 2 is diagnostic and does not gate adoption.

**Reported, not gated.** The five-day NGA distribution comparison of `DIP_AND_NGA_DISTRIBUTIONS.md`
will be recomputed with the E7P arms: share of samples with lower URE, percentiles, and epochs, hours and
satellite-days won.

### Resources

Three serial fits of about 70–75 guarded minutes each (about 3½ h), under fork8, with keep-awake.
Chain `Opus_Fork/experiments/ecom7/run_chain_e7p.ps1` (steps appended; the completed E7P-2 and
E7P-3 are skipped). It waits out external GPU and memory load and any Python process, and is
resumable after a shutdown with `Opus_Fork/resume_chain.ps1 -Chain ecom7p -WaitIfBusy`.

---

<!-- original: Opus_Fork/results/ECOM7P_HOLDOUT_RESULTS.md -->

## Constrained ECOM-7, held-out days 4, 5 and 7 August — NOT ADOPTED: Aug 7 worsens URE by 4.5%

Opus, 25 September 2026 UTC. Protocol `ECOM7P_HOLDOUT_PROTOCOL.md`, frozen before any held-out fit.
Chain `Opus_Fork/runs/ecom7p-chain.status`.

### Fits

| Arm | Campaign | Status |
|---|---|---|
| E7P-4 | `Opus_Fork/runs/20260925T142121Z-fit-E7P-4-25st` | converged, 3 linearizations, 3,820 guarded s, peak 593 MiB. One stop: the guard refused a worker because another Python process was running. The chain waited 5 min and resumed. |
| E7P-5 | `Opus_Fork/runs/20260925T153204Z-fit-E7P-5-25st` | converged, 3 linearizations, 3,776 guarded s, peak 580 MiB. One GPU-telemetry error (0xc0000bba), resumed after 3 min. |
| E7P-7 | `Opus_Fork/runs/20260925T164050Z-fit-E7P-7-25st` | converged, 3 linearizations, 3,193 guarded s, peak 515 MiB, no interruption |

### Scores against IGS final (NGA PE on the same keys)

Evaluations `Opus_Fork/runs/20260925T1736*Z-eval-E7P-4/5`, `…T173832Z-eval-E7P-7`; copied to `results/arm_E7P_aug{4,5,7}.json`.

| Day | Comparator (ECOM5) URE | **E7P URE** | Change | Radial R→E7P | 3D R→E7P | NGA URE / 3D | 12 h amplitude R→E7P |
|---|---:|---:|---:|---|---|---|---|
| Aug 4 | P2-4 4.045 | **3.851** | **−4.8%** | 3.82 → 3.62 | 11.44 → 11.08 | 4.359 / 10.94 | 1.93 → **1.45 (−25%)** |
| Aug 5 | P2-5 3.836 | **3.753** | **−2.2%** | 3.58 → 3.52 | 11.43 → **10.97** (beats NGA 11.76) | 4.826 / 11.76 | 1.74 → **1.33 (−24%)** |
| Aug 7 | R7 3.403 | **3.557** | **+4.5%** | 3.07 → 3.25 | 11.49 → 11.49 | 4.195 / 10.56 | 0.47 → **0.74 (+57%)** |

URE by window, comparator → E7P:

| Day | Early | Noon | Late |
|---|---|---|---|
| Aug 4 | 4.266 → 4.024 | 3.445 → 3.224 | 3.574 → 3.477 |
| Aug 5 | 3.766 → 3.791 | 3.407 → 3.469 | 4.050 → 3.703 |
| Aug 7 | 3.169 → 3.409 | 3.218 → 3.258 | 3.888 → 3.997 |

**Dc2/Ds2.** Median |D2| is 1.48, 1.29 and 1.58 nm/s² on the three days; the largest are 4.9 (G29), 4.7 (G30) and 5.2 (G29).
**None** is beyond 6 nm/s² on any day.

**Per satellite against the comparator.** Satellites improving in URE: 21/31, 15/31 and 11/26. The largest 3D
regressions are G10 +3.5 cm (Aug 4), G12 +7.6 cm (Aug 5) and G29 **+9.5 cm** (Aug 7, URE 3.47 → 5.70).

### Against the frozen predictions

| # | Prediction | Result | |
|---|---|---|---|
| 1 | Better on ≥ 2 of 3 days, no day worse by > 1%, mean change ≤ −2% | better on 2 of 3; **Aug 7 +4.5%**; mean **−0.8%** | **FAIL** |
| 2 | 12 h amplitude −10% on Aug 4 and 5; ≤ 0.60 on Aug 7 | −25%, −24%; **0.74** on Aug 7 | pass on 4/5, **fail on 7** |
| 3 | Radial ≤ comparator + 3%; no satellite 3D regression > 0.1 m | 3.62 ✓, 3.52 ✓, **3.25 > 3.16** ✗; max +9.5 cm ✓ | **FAIL** (Aug 7 radial) |
| 4 | ≥ 90% of satellites with \|Dc2\|, \|Ds2\| ≤ 6 nm/s² | 100% on all days | pass |

**Falsification rule met** (Aug 7 worse by more than 3%). Constrained ECOM-7 at σ = 2 nm/s² is **not adopted** as
the default. σ will not be retuned on these days. The ERP + thrust + IIIA 2600 kg ECOM5 model stays the default.

### Across all five days (descriptive; Aug 2 and 3 chose the approach)

| Day | ECOM5 12 h swing | URE change with constrained ECOM-7 |
|---|---:|---:|
| Aug 2 | 1.95 | −2.9% |
| Aug 3 | 1.82 | −6.1% |
| Aug 4 | 1.93 | −4.8% |
| Aug 5 | 1.74 | −2.2% |
| **Aug 7** | **0.47** | **+4.5%** |

The gain follows the swing. On the four days with the 1.7–1.95 cm swing, constrained Dc2/Ds2 cut it by 16–25%
and lower URE by 2–6%. On Aug 7 there is no swing to remove. There the terms *create* one (0.47 → 0.74) and
cost 4.5%. A rule such as "use ECOM-7 only when the swing is present" would be chosen after seeing these results,
so this protocol cannot adopt it.

### Why Aug 7 has no swing: satellite set ruled out

The Aug 7 fixture (Astra's cross-date preparation, `runs/20260920T155655Z-7b703635`) has the **same 25 stations** as
Aug 2. It rejects six satellites (G03, G05, G13, G15, G18, G26) for lack of a four-hour broadcast fit; the Aug 2–5
fixtures reject only G13. `Opus_Fork/experiments/ecom7/swing_subset.py` (`results/swing_subset.json`) recomputes each
day's 12 h amplitude without those five extra satellites:

| Day | ECOM5 arm, all | without G03/05/15/18/26 | those five alone |
|---|---:|---:|---:|
| Aug 2 | 1.95 | 1.75 | 2.96 |
| Aug 3 | 1.82 | 1.74 | 2.88 |
| Aug 4 | 1.93 | 1.84 | 3.44 |
| Aug 5 | 1.74 | 1.70 | 3.14 |
| Aug 7 | 0.47 | 0.47 | — |

The five satellites swing harder than the rest, but removing them leaves 1.70–1.84 cm on Aug 2–5. The satellite set
does not explain Aug 7. What remains is the day itself or how its fixture was prepared. Aug 7 uses a different
preparation path (Astra's cross-date preparation, `BRDC00WRD` navigation, a four-hour LNAV-fit rule) from the
fork-prepared Aug 2–5 fixtures (`BRDCMERGED`).

### What this means for the objective

- The 12 h common-height swing is worth about 6% of URE on Aug 2–5. Whether it is an **orbit-model limit that varies by
  day** or an **artifact of the fork's fixture preparation** is now the deciding question. Aug 7 is the only day that
  lacks it, and also the only day with a different preparation path.
- **Recommended next test.** First, run the dynamics-only census (dynamics fitted straight to IGS positions, no station
  data, about 10 min) on Aug 7 and compare it with Aug 2's census (12 h amplitude 1.21 cm for E5P).
  - A small census swing on Aug 7 means the day differs physically. Force-model work should then target the swing's
    day-to-day driver.
  - A census swing near 1.2 cm, while the Aug 7 POD shows 0.47, means the station POD on Astra's fixture suppresses it.
    The fork's preparation path then becomes the lever, possibly a larger URE gain than any SRP term.
  - A second check is to prepare Aug 7 with the fork's own preparation tool and run the ECOM5 ERP arm (about 1 h).

---

<!-- original: Opus_Fork/results/BOXWING_CENSUS_RESULTS.md -->

## Box-wing a-priori SRP, dynamics-only census on 2026-08-02: small gain, does not remove the 12 h swing

Opus, 25 September 2026 UTC. Predictions 7–8, frozen before any box-wing run, are in the
`Opus_Fork/reference_census.py` docstring. Model: `Opus_Fork/boxwing.py`. It uses nominal yaw
steering and the published surfaces and optical properties (Duan & Hugentobler 2021 for IIR/IIF;
Steigenberger et al. 2020 for IIIA, at the papers' masses). It adds no parameter; ECOM5 is still
estimated, from zero.

### Runs, all kept

| Run | Change | Outcome |
|---|---|---|
| `…T235841Z-ref-census-boxwing` | box-wing started from E5's state (another model's solution) | 10–12 of 32 satellites "No decreasing step" |
| `…T001700Z-ref-census-boxwing2` | box-wing started from its own state-only stage | 18–20 of 32 fail, **worse** |
| `…T005207Z-ref-census-boxwing3` | + numerical-floor acceptance (declared in the docstring) | **all 32 fit, in every variant** |

**Diagnosis of the failures** (`Opus_Fork/experiments/boxwing_debug.py`, G02 E5PB): the fit reaches
4.89 cm RMS in two iterations and stays flat. Every trial then changes the cost by a random
±1e-4 relative amount, whatever α. The box-wing's surface switching (±Z faces as the Sun crosses
the body XY plane, and the yaw-steering attitude) leaves integration-level noise that swamps the
0.1 mm stopping rule. The fits had converged; they could not show it.

Floor terminations in run 3: E5 2 (G01, G18, which failed outright before), E5P 0, E5B 8,
E5PB 13.

### Result (all 32 satellites, the same set in every variant)

| Variant | Radial / along / cross RMS cm | Mean radial cm | **12 h amplitude** | 24 h amplitude |
|---|---|---:|---:|---:|
| E5 (ECOM5) | 2.37 / 1.37 / 3.44 | +1.74 | 1.28 | 0.30 |
| E5P (+ ERP + thrust) | 1.54 / 1.29 / 3.41 | +0.32 | 1.21 | 0.30 |
| E5B (+ box-wing) | 2.05 / 1.32 / 3.37 | +1.27 | 1.15 | 0.29 |
| **E5PB (+ ERP + thrust + box-wing)** | **1.45** / 1.22 / 3.37 | −0.15 | **1.08** | 0.31 |
| *E7, earlier census: free Dc2/Ds2* | *2.11 / 1.20 / 3.13* | *+1.65* | *0.57* | *0.30* |

| # | Prediction | Result | |
|---|---|---|---|
| 7 | E5PB 12 h amplitude ≤ 0.85 cm (≥ 30% below E5P) and radial RMS below E5P's | 1.08 (**−11%**); radial 1.54 → **1.45 (−6%)** | **fail** on the swing; pass on radial RMS |
| 8 | Box-wing leaves the mean radius near E5's (+1.75) | +1.27 (moved 0.47 cm) | **miss** |

### Why the published box-wing does not reproduce what free Dc2/Ds2 capture

ECOM-7 fitted to IGS positions (census E7) needs twice-per-revolution Sun-direction terms of
|D2| ≈ 1.5 (IIF), 2.2 (IIIA), 2.4 (IIR) and 2.3 (IIR-M) nm/s² per satellite. Their **phases scatter
from satellite to satellite**: the block means of Dc2 and Ds2 are much smaller than |D2|. The
box-wing's bus faces produce a Sun-direction variation of the right order, a cos 2E coefficient of
1.8–3.9 nm/s². But it gives every satellite of a block the same, β-driven pattern. So the
consistent part of the needed 2/rev signal is small, and a fixed published model removes only
about a tenth of the swing. The remaining, satellite-specific part is what ECOM-7 absorbs. In the
station POD, that same freedom costs 17–30% URE.

### What this leaves

- **The 12 h common-height swing is not explained by any fixed physics tried**: ERP, thrust,
  radial constant, or the published box-wing. Only free Sun-direction 2/rev terms remove it, and
  unconstrained they hurt the station POD. Its URE share is about 1.9 cm² of about 15 cm² of URE²
  (≈ 6% of URE) on Aug 2–5.
- The box-wing gives a small, parameter-free radial gain (−6% radial RMS here). In the station POD
  it would first need the surface switching **smoothed**, because the POD's stationarity rule would
  hit the same floor.
- The best remaining handle on the swing is **Dc2/Ds2 with priors**. The census fixes their scale
  (|D2| ≈ 1.5–2.4 nm/s²). A prior σ of about 2 nm/s² keeps them physical while limiting what they can
  absorb from station noise. It needs only a config change on the existing ECOM-7 path
  (`prior_sigma_mps2` for columns 5–6). It would need its own protocol.

### Resources

Three census runs under fork8: 1,035 s, 1,548 s and 2,102 s guarded. Peak job memory 686 MiB.
Plus one short debug run.

---

<!-- original: Opus_Fork/results/SWING_ORIGIN_NOTES.md -->

## Where does the 12 h common-height swing come from? Investigation log

Opus, 25 September 2026 UTC. Follows `ECOM7P_HOLDOUT_RESULTS.md`. Aug 7 lacks the swing (0.47 cm, against
1.74–1.95 on Aug 2–5), and constrained ECOM-7 failed there. The user authorised open-ended investigation
("do as much investigation as you feel necessary").

### Hypothesis, written before the Aug 3–5 census existed (14:15 local)

The ECOM5+ERP arms' pooled-radial 12 h harmonic peaks at 7.45, 7.51, 8.21 and 8.75 h UT on Aug 2, 3, 4 and 5. That is a
drift of about +0.4 h/day, with amplitude 1.74–1.95 cm, then 0.47 cm on Aug 7 with the phase near 4 h. A Sun-fixed or
Earth-fixed cause would hold the UT phase fixed. A drifting phase and a changing amplitude point to a **lunar-period force
missing from the dynamics**. The candidate is ocean tides: `customkf/orbit_forces.py` has solid Earth tides (IERS
2010 step 1) but no ocean tides, no step-2 frequency corrections and no pole tide. The M2/S2 mix gives a 12 h UT
pattern whose phase drifts and whose amplitude beats over the 14.8-day spring–neap cycle.

**Predictions for the dynamics-only census (E5, fitted to IGS final, no station data):**

- **L1.** The census 12 h amplitude varies by day like the POD's: Aug 7 is clearly below Aug 2 (≤ 60% of it).
- **L2.** The census 12 h peak drifts later by 0.3–0.9 h/day from Aug 2 to Aug 5, in step with the POD phases.
- **Against.** A census Aug 7 amplitude near Aug 2's, with the POD on Aug 7 near zero, means the POD suppresses the
  swing on Aug 7's data. The cause would then be in the observation or data path, not the dynamics. A constant phase
  means a Sun- or Earth-fixed cause.

### Census result (14:21): L1 and L2 pass, and the swing is a common mode

| Census E5 | Aug 2 | Aug 3 | Aug 4 | Aug 5 | Aug 7 |
|---|---:|---:|---:|---:|---:|
| Pooled 12 h amplitude (cm) | 1.33 | 1.27 | 1.16 | 0.97 | **0.18** |
| Pooled 12 h peak (UT) | 7.6 | 8.0 | 8.4 | 8.9 | 11.1 |
| Median per-satellite 12 h amplitude | 1.33 | 1.28 | 1.22 | 1.05 | 1.12 |
| Phase coherence across satellites | 0.92 | 0.90 | 0.87 | 0.76 | **0.08** |

- The census drifts +0.43 h/day like the POD, and Aug 7 collapses without any station data. **The day-to-day change is in
  dynamics against IGS, not in the fixture or the POD.**
- Coherence 0.9 means every satellite, in every plane, peaks at the same UT. A force tied to satellite position
  cannot do that. The signal is a function of **time**, common to the constellation.

### Second hypothesis, written before any sub-daily-EOP run (14:30)

`customkf.frames.EarthOrientation.at` interpolates daily IERS values linearly. Those exclude the IERS 2010 diurnal and
semidiurnal ocean-tidal EOP terms that IGS analysis centres apply. A UT1 error δθ(t) displaces every satellite along-track
by δθ·r·cos i. The factor is the same for all planes, so it is a constellation-wide common mode. A dynamic fit absorbs
the ~12 h part through eccentricity, which leaves a common radial error once per revolution.

`Opus_Fork/subdaily_eop.py` ports IERS ORTHO_EOP/CNMTX and reproduces the IERS test case to 1e-9. Its δUT1 for these days:

| Day | 12 h amp (µs) | 12 h peak (UT) | 24 h amp (µs) | 12 h along-track equivalent (cm) |
|---|---:|---:|---:|---:|
| Aug 2 | 23.7 | 10.7 | 5.8 | 2.6 |
| Aug 3 | 22.1 | 11.4 | 9.9 | 2.5 |
| Aug 4 | 20.0 | 12.1 | 20.3 | 2.2 |
| Aug 5 | 17.9 | 13.0 | 29.7 | 2.0 |
| Aug 7 | 15.4 | 15.2 | 42.9 | 1.7 |

On Aug 2–5 the census peak runs 3.1–4.1 h, about a quarter cycle, ahead of the δUT1 12 h peak. That is the
lag expected if the fit absorbs the error through eccentricity. The δUT1 24 h term grows sevenfold by Aug 7, where the census 24 h amplitude
jumps (0.83 against 0.2–0.3).

**Predictions for the census with the ocean-tidal sub-daily EOP applied (E5, Aug 2 and Aug 7):**

- **S1.** Aug 2's pooled 12 h amplitude falls from 1.33 to **≤ 0.6 cm**, and cross-satellite coherence falls below 0.6.
- **S2.** Aug 7's pooled 24 h amplitude falls from 0.83 to **≤ 0.5 cm**.
- **S3.** Mean radial, along-track and cross-track RMS fall on both days, because a frame error is removed. Any rise
  means the port or its sign is wrong.
- **Against.** An Aug 2 12 h amplitude above 1.0 cm means sub-daily EOP is not the main cause.

### Census with sub-daily EOP (14:26–14:31): S1 and S2 pass

`Opus_Fork/experiments/subdaily/census_sd.py`, E5, 6 workers. Results in `results/reference_census_2026-08-0{2,7}_sdEOP.json`.

| Census E5 | Aug 2 without | Aug 2 **with** | Aug 7 without | Aug 7 **with** |
|---|---:|---:|---:|---:|
| Pooled 12 h amplitude (cm) | 1.33 | **0.27** | 0.18 | 0.29 |
| Pooled 24 h amplitude (cm) | 0.32 | 0.13 | 0.83 | **0.23** |
| Per-satellite 12 h median (cm) | 1.36 | 0.50 | 1.16 | 0.63 |
| Coherence | 0.92 | 0.39 | 0.15 | 0.41 |
| RMS R / A / C (cm) | 2.38 / 1.26 / 3.35 | **1.85 / 0.90 / 1.29** | 1.88 / 1.13 / 3.19 | 2.03 / 1.05 / **1.33** |
| Mean radial (cm) | +1.75 | +1.50 | +1.17 | +1.70 |
| Satellites fitted | 30 (G01, G18 failed) | **32** | 31 | 31 |

- **S1 passes**: 1.33 → 0.27 (−80%), coherence 0.92 → 0.39.
- **S2 passes**: Aug 7's 24 h amplitude is 0.83 → 0.23.
- **S3** passes except Aug 7's radial RMS (1.88 → 2.03). That rise is entirely the mean: +1.17 → +1.70 matches the
  other days' known missing-ERP offset. With the mean removed, radial scatter falls 1.47 → 1.11 cm.
- **Cross-track falls about 60% on both days** (3.35 → 1.29, 3.19 → 1.33). The long-standing 2.7–4.7 cm census cross-track
  "floor" was mostly this missing frame model.
- **Consequence for R7.** Aug 7's apparently smaller missing-radial offset (+1.25 against +1.66–1.9), which made the fixed
  ERP shift overshoot there, was an artifact of the EOP error.

**Diagnosis.** The 12 h common-height swing, its day-to-day drift, and Aug 7's anomaly come from **missing IERS 2010
diurnal/semidiurnal ocean-tidal EOP** in `customkf/frames.py`, not from SRP. That is why ECOM-7 "helped" only on days
when the UT1 wobble projected coherently onto the 12 h radial.

### Census runs

- Aug 7, E5/E5P/E7, 4 workers: `Opus_Fork/runs/*ref-census-aug7` → `results/reference_census_2026-08-07.json`.
- Aug 3, 4, 5, E5 only, 6 workers: `Opus_Fork/runs/*ref-census-aug0{3,4,5}-e5` → `results/reference_census_2026-08-0{3,4,5}_swingE5.json`.
- Analysis: `Opus_Fork/experiments/ecom7/census_swing.py`.

---

<!-- original: Opus_Fork/results/SDEOP_PROTOCOL.md -->

## Protocol: IERS 2010 sub-daily (ocean-tidal) EOP in the station POD, 2, 3, 4, 5 and 7 August

Opus, 25 September 2026 UTC. **Frozen before any sub-daily-EOP POD fit existed.** The user authorised open-ended
investigation.

### Why

`SWING_ORIGIN_NOTES.md`: `customkf/frames.py` interpolates the daily IERS EOP and omits the IERS 2010 Class 1
diurnal/semidiurnal ocean-tidal terms in x, y and UT1. IGS analysis centres apply them. In the dynamics-only
census, adding them (`Opus_Fork/subdaily_eop.py`, a port of IERS ORTHO_EOP/CNMTX that reproduces the IERS test case):

- removes 80% of the constellation-wide 12 h radial swing on Aug 2 (1.33 → 0.27 cm);
- removes Aug 7's 24 h swing (0.83 → 0.23 cm);
- cuts cross-track RMS about 60% on both days.

The missing terms are a frame-model omission, not an SRP deficiency. This test asks whether the station POD
benefits the same way.

### What runs

Controller `Opus_Fork.run_fit_sd`, workers `Opus_Fork.sd_traj_cache` / `Opus_Fork.sd_iteration`: the ECOM5 ERP
path (`ngv_pilot`) with `subdaily_eop.install()` in every worker. Both the dynamics' Earth rotation and the
station geometry get the terms (smoke check `Opus_Fork/runs/20260925T183541Z-check-sd`: 369–566 µas, as ORTHO_EOP
predicts). Each arm copies its comparator exactly except for the sub-daily EOP: same fixture, config, ERP variant,
chunking and groups. Cap 6, cold start, unchanged stationarity rule.

| Day | New arm | Variant | Comparator (plain EOP): URE / radial / cross cm, 12 h amp | Config, chunk/groups |
|---|---|---|---|---|
| Aug 2 | SD-2 | `erp+thrust+sdeop` | P1: 4.167 / 3.77 / 7.02, 1.95 | unit-ecom5, 12/2 |
| Aug 7 | SD-7 | `erp+thrust+sdeop` | R7: 3.403 / 3.07 / 7.71, 0.47 (24 h 0.89) | cross_date config, 18/4 |
| Aug 3 | SD-3 | `erp+thrust+iiia2600+sdeop` | P2-3: 3.876 / 3.66 / 7.51, 1.82 | unit-ecom5, 12/2 |
| Aug 4 | SD-4 | `erp+thrust+iiia2600+sdeop` | P2-4: 4.045 / 3.82 / 6.93, 1.93 | unit-ecom5, 12/2 |
| Aug 5 | SD-5 | `erp+thrust+iiia2600+sdeop` | P2-5: 3.836 / 3.58 / 8.08, 1.74 | unit-ecom5, 12/2 |

**Scoring.** A sub-daily fit publishes R_sd(t)·r. `Opus_Fork.experiments.subdaily.evaluate_sd` (and `quick_dip_sd`)
present such a fit to the unchanged evaluator as R_plain(t)ᵀ·R_sd(t)·r. Every arm is thus scored as its own Earth-fixed
product against IGS final, with NGA PE on the same keys, over the same four windows. Plain-EOP arms, IGS and NGA are untouched.

### Predictions

1. **Primary.** URE is below the comparator on **at least 4 of 5** days, and the mean URE change is **≤ −3%**.
2. **Swing.** The pooled-radial 12 h amplitude falls by **≥ 40%** on Aug 2–5 (≤ 1.17, 1.09, 1.16 and 1.04 cm). Aug 7's 24 h
   amplitude falls from 0.89 to **≤ 0.60 cm**.
3. **Cross-track.** Cross-track RMS falls on at least 4 of 5 days.
4. **No damage.** No satellite's 3D RMS regresses by more than 0.1 m, and radial RMS is at most the comparator's plus 3%
   on every day.

**Falsification.** URE worse than the comparator on 2 or more days, or a mean change above 0. Either means the POD does
not gain from the terms as implemented. The model is an IERS Class 1 convention, so that would point to an
implementation or consistency error to find, not a reason to drop the convention.

**Adoption.** If 1 and 4 pass, sub-daily EOP becomes the default for all new fork fits and their scoring. It would also be
handed to Astra as a proposed change to `customkf/frames.py`, which this fork does not edit.

### Resources

Five serial fits of about 55–75 guarded minutes each (about 5–6 h), under fork8, with keep-awake. Chain
`Opus_Fork/experiments/subdaily/run_chain_sd.ps1`, resumable with `Opus_Fork/resume_chain.ps1 -Chain sdeop -WaitIfBusy`.
It waits out external GPU and memory load and any other Python process.

---

<!-- original: Opus_Fork/results/SDEOP_RESULTS.md -->

## IERS 2010 sub-daily EOP in the station POD — ADOPTED: URE −13.7% over five days, 3D now beats NGA on 3 of 5 days

Opus, 26 September 2026 UTC. Protocol `SDEOP_PROTOCOL.md` (frozen before any fit, pinned by the campaigns).
Diagnosis `SWING_ORIGIN_NOTES.md`. Chain `Opus_Fork/runs/sdeop-chain.status`.

The only change is the IERS 2010 diurnal/semidiurnal ocean-tidal EOP (`Opus_Fork/subdaily_eop.py`, a port of IERS
ORTHO_EOP/CNMTX that reproduces the IERS test case), in both the dynamics' Earth rotation and the station geometry.
Each SD arm otherwise copies its comparator exactly: fixture, config, ERP variant, chunking. Every arm is scored as its
own Earth-fixed product against IGS final (`Opus_Fork.experiments.subdaily.evaluate_sd`).

### Fits

| Arm | Campaign | Linearizations | Guarded s | Obs. cost SD vs plain | Stops (all resumed content-bound) |
|---|---|---:|---:|---|---|
| SD-2 | `20260925T183701Z-fit-SD-2-25st` | 3 | 3,374 | 13,310.7 vs 13,508.2 (−197.5) | none |
| SD-7 | `20260925T193347Z-fit-SD-7-25st` | **5** (R7: 3) | 4,826 | 12,462.2 vs 12,574.5 (−112.3) | memory headroom (10.55 GiB), CPU 75% ceiling, one deliberate pause to score SD-2 |
| SD-3 | `20260925T215927Z-fit-SD-3-25st` | 3 | 3,393 | 13,211.9 vs 13,419.2 (−207.3) | none |
| SD-4 | `20260925T225732Z-fit-SD-4-25st` | 3 | 3,531 | 14,270.9 vs 14,400.3 (−129.4) | memory headroom ×2 (10.98, 11.74 GiB), CPU ceiling ×2, and one Windows file lock on a worker's `stderr.log` during the folder move (the only non-external stop; the chain was restarted at 21:00) |
| SD-5 | `20260926T025926Z-fit-SD-5-25st` | 3 (P2-5: 4) | 3,301 | 12,920.5 vs 13,087.3 (−166.8) | none |

Every fit converged (final steps 0.008–0.04 mm). **The station observations fit better with the IERS terms on every day,
by 112–207 in cost, with no added parameter.** Wall time was 14:37–23:55 for 18,425 guarded s. External load (other programs'
memory, CPU and GPU) accounted for about 4 h of waiting.

### Scores against IGS final (full day)

| Day | Comparator | URE cm | Change | 3D cm | R / A / C cm | 3D vs NGA | URE sats beating NGA |
|---|---|---|---:|---|---|---|---|
| Aug 2 | P1 → **SD** | 4.167 → **3.401** | **−18.4%** | 14.04 → 12.92 | 3.77/11.56/7.02 → 2.95/11.29/5.56 | 1.29 → 1.18 | 17 → 23 /31 |
| Aug 3 | P2-3 → **SD** | 3.876 → **3.165** | **−18.3%** | 10.94 → **9.67** | 3.66/7.06/7.51 → 2.94/6.64/6.39 | 1.02 → **0.90** | 16 → 21 /31 |
| Aug 4 | P2-4 → **SD** | 4.045 → **3.364** | **−16.8%** | 11.44 → **10.41** | 3.82/8.25/6.93 → 3.11/8.06/5.80 | 1.05 → **0.95** | 14 → 16 /31 |
| Aug 5 | P2-5 → **SD** | 3.836 → **3.249** | **−15.3%** | 11.43 → **9.69** | 3.58/7.25/8.08 → 3.03/6.48/6.53 | 0.97 → **0.82** | 15 → 19 /31 |
| Aug 7 | R7 → SD | 3.403 → 3.409 | +0.2% | 11.49 → 10.71 | 3.07/7.95/7.71 → 3.14/7.80/6.63 | 1.09 → 1.01 | 11 → 15 /26 |

Evaluations are in `Opus_Fork/runs/*-eval-SD-{2,7,3,4,5}`, copied to `results/arm_SD_aug{2,3,4,5,7}.json`. NGA URE is 4.427,
4.289, 4.359, 4.826 and 4.195. **3D now beats NGA PE on Aug 3, 4 and 5.**

**12 h swing** (`results/quick_dip_SD_aug*.json`): Aug 2 1.95 → 0.45 (−77%), Aug 3 1.82 → 0.87 (−52%), Aug 4 1.93 → 0.67
(−65%), Aug 5 1.74 → 0.67 (−61%). On Aug 7 the 24 h amplitude is 0.89 → 0.42, **but the 12 h amplitude rose 0.47 → 1.07**.

**Per satellite.** URE improves on 26/31, 24/31, 25/31, 23/31 and 15/26 satellites. The largest 3D regression on any day is
+5.4 cm (G17, Aug 3). **G17 (IIR-M) regresses by 2.3–5.4 cm on every day**, the one consistent loser.

### Against the frozen predictions

| # | Prediction | Result | |
|---|---|---|---|
| 1 | URE below comparator on ≥ 4 of 5 days, mean change ≤ −3% | 4 of 5 (Aug 7 +0.2%); mean **−13.7%** | **pass** |
| 2 | 12 h amplitude −40% on Aug 2–5; Aug 7 24 h ≤ 0.60 | −77, −52, −65, −61%; Aug 7 24 h 0.42 | **pass** (Aug 7 12 h rose, unpredicted) |
| 3 | Cross-track falls on ≥ 4 of 5 days | 5 of 5 (−14% to −21%) | **pass** |
| 4 | No satellite 3D regression > 0.1 m; radial ≤ comparator + 3% | max +5.4 cm; Aug 7 radial +2.3%, others fall | **pass** |

**Falsification not met. Adopted:** sub-daily EOP is the default for all new fork fits (`Opus_Fork.run_fit_sd`,
variant `erp+thrust+iiia2600+sdeop`) and their scoring (`evaluate_sd`).

### Against NGA, five days pooled (14,400 satellite-epochs; `results/nga_dist_sd.json`)

| | Plain-EOP arms | **Sub-daily-EOP arms** | NGA PE |
|---|---:|---:|---:|
| URE lower than NGA, share of samples | 54.7% | **63.5%** | |
| 3D lower than NGA, share of samples | 49.8% | **58.8%** | |
| URE p50 / p68 / p90 / p95 / p99 (cm) | 2.72 / 3.68 / 6.07 / 7.34 / 10.67 | **2.24 / 3.08 / 5.07 / 6.33 / 9.17** | 3.02 / 4.05 / 6.36 / 7.55 / 14.68 |
| 3D p50 / p90 / p95 (cm) | 8.79 / 16.59 / 19.92 | **7.56 / 15.05 / 18.02** | 8.86 / 16.54 / 19.37 |
| URE RMS (cm) | 3.89 | **3.32** | 4.43 |
| Satellite-days better than NGA | 91/150 | **112/150** | |
| 15-min epochs better (constellation RMS) | 367/480 | **442/480** | |
| Hours better | 93/120 | **111/120** | |

Our URE is now below NGA's at every percentile, and so is our 3D. On Aug 2 the late-window along-track problem (18 cm after
18 UT) remains and is the main 3D gap on that day.

### Follow-up investigations (26 Sep, after adoption)

**1. Desai & Sibois (2016) instead of ORTHO_EOP.** IGS repro3/ITRF2020 moved to that model. `Opus_Fork/hfeop_ds.py`
reads the IVS HF-EOP working group's coefficient table (159 lines;
`datastore/static/hfeop/desai_model_jgrb51665-sup-0002-ds01.txt`, SHA-256 in the module). Against ORTHO_EOP it correlates
at r ≥ 0.992 in x, y and UT1 on every day. The differences are 1.2–2.2 µs in UT1 (about 0.25 cm along-track) and 9–32 µas
in polar motion. Census E5 (`results/reference_census_2026-08-0{2,7}_dsEOP.json`):

| | 12 h amp | RMS R / A / C cm |
|---|---:|---|
| Aug 2 ORTHO → DS | 0.27 → 0.18 | 1.849/0.897/1.285 → 1.813/0.884/1.255 |
| Aug 7 ORTHO → DS | 0.29 → 0.29 | 2.035/1.045/1.331 → 2.016/1.059/1.376 |

The results are mixed and within ±3%, so the choice is second-order. **ORTHO_EOP (IERS 2010, Class 1) stays the default**, with
DS available as an option.

**2. The POD's remaining 12 h swing is station-network scale.** In every POD arm the pooled radial swing correlates 0.98–1.00
with the per-epoch Helmert scale. With sub-daily EOP it is 0.16–0.36 ppb, peaking at 4.6–6.9 h UT. **NGA shows the same
thing against IGS**: 0.12–0.30 ppb, peaking at 4.3–6.2 h UT on Aug 2–5. The census, which has no stations, stays at 0.2–0.3 cm. At
GPS altitude 1 mm of network-mean station height is about 0.4 cm of radius. The candidates are station-side tidal
models, where ours and possibly NGA's are simpler than the IGS ACs': RTKLIB-style reduced solid tide rather than IERS
DEHANTTIDEINEL, 11-line ocean loading without the centre-of-mass correction, and no S1/S2 atmospheric tidal loading.

**3. Aug 7 is explained.** Its plain-EOP 12 h vector (0.47 cm at 4.1 h) is the sum of the EOP-induced part (≈ 0.67 cm at
≈ 11.5 h) and the station-scale part (1.07 cm at 4.9 h). They were nearly opposite and cancelled, so Aug 7 only
*looked* swing-free. Removing the EOP error exposes the station-scale swing, which is why Aug 7's URE stayed flat.

**4. G17 is not a G17 defect.** Its β is +44° to +47° (not eclipse season) and its Y0 is ordinary and unchanged. Its POD
cross-track error is an almost constant per-satellite offset: −6 to −15 cm in every window. Such offsets are common, in NGA
too (+13 to +14 cm on G12, G16 and G22 on Aug 3). They come from a weakly determined "displaced orbit" mode: a constant normal
force such as D0·sin β shifts the plane by a/n², so 1 nm/s² ≈ 3.3 cm at β = 45°. Sub-daily EOP moves each satellite's
offset by ±2–6 cm, systematically: the per-satellite change correlates 0.93–0.94 between consecutive days and decorrelates
over about 5 days, as polar-motion geometry would. G17 (−4.5 ± 1.9 cm), G16 and G19 move the wrong way; G14 and G22 (+5 cm)
improve. Net cross-track still improves on 5 of 5 days.

**5. The customkf hook.** With the user's approval the fork now uses a 10-line opt-in hook in `customkf/frames.py`
(`EarthOrientation.subdaily`, default None) instead of replacing `EarthOrientation.at`. The default is bit-identical to the
original on 997 epochs. The Aug 2 sub-daily census rerun through the hook reproduces the pooled numbers and all 32
per-satellite residual series exactly. SD-2's rescored raw numbers are identical. Only the Helmert diagnostic differs,
by about 1e-8 mm of summation-order noise that also affects the untouched NGA arm. Details in `subdaily_eop_handoff/ASTRA_HANDOFF.md`.

### What remains

1. **Residual 12 h swing of 0.45–1.07 cm, largest on Aug 7.** NGA shows a comparable 0.34–0.73 cm against IGS. That
   suggests IGS applies a different sub-daily EOP model from ORTHO_EOP (Ray 1994): the Desai & Sibois (2016) model used in IGS
   repro3/IGS20-era processing, or ORTHO_EOP plus libration. Next test: implement the alternatives and compare them in the
   census on Aug 2 and 7, which takes minutes each.
2. **G17** regresses on every day. Check its attitude, eclipse season or metadata.
3. **Mean radial now slightly negative on some days** (Aug 2 −0.45 cm). With the frame error gone, the fixed ERP shift can be
   re-examined.
4. **Hand-off:** the fix belongs in Astra's `customkf/frames.py`. This fork does not edit it, and does not claim the change.

---

<!-- original: Opus_Fork/results/SENSITIVITY_PROTOCOL.md -->

## Protocol: one-change sensitivity fits on 2026-08-03 — which channel drives the remaining scale breathing?

Opus, 26 September 2026 UTC. **Written before any sensitivity fit existed.** The user asked for the tests and for them to
proceed without step-by-step consultation. This is a diagnostic, not an adoption test: no variant becomes a default here.

### Background

With sub-daily EOP (`SDEOP_RESULTS.md`), the POD's remaining common-height swing is a pure Helmert-scale oscillation
(0.16–0.37 ppb) that **repeats with the constellation geometry**: the hourly pattern correlates 0.73–0.92 between Aug 2,
3, 4 and 7 (`STATION_TIDES_SCREEN.md`). Station tide models are ruled out. The post-fit phase residuals show no leftover
nadir or elevation shape (`RESIDUAL_BINNING.md`), so the systematic is absorbed into parameters. With per-epoch satellite
clocks, orbit scale is visible to the data only through nadir- and elevation-dependent terms.

### Arms (each is SD-3 with exactly one change; `Opus_Fork.sens`, `run_fit_sens`)

| Arm | Change | Probes |
|---|---|---|
| S-nopcv | satellite PCV (nadir-dependent, up to ±14 mm) set to zero; PCOs kept | the nadir channel's coupling to scale |
| S-cut15 | 15° elevation cutoff; drops the 3,579 rows below 15° (10.9%) in the frozen list `experiments/sensitivity/drop_below15_aug03.json` | low-elevation troposphere mapping and multipath |
| S-wet1h | wet-delay nodes hourly instead of 3-hourly; random-walk σ scaled √(1/3), so process noise per unit time is unchanged | temporal resolution of the troposphere |

Comparator: SD-3 (`20260925T215927Z-fit-SD-3-25st`) on the same fixture, config (unit-ecom5), ERP variant, chunking
(12/2) and cap. Smoke checks: `Opus_Fork/runs/*check-sens-*`.

### Measures

For each arm against SD-3 (via `evaluate_sd` / `quick_dip_sd`, IGS final truth, NGA alongside):
1. The pooled-radial and Helmert-scale 12 h and 24 h amplitudes, and the UT phase.
2. **Pattern change:** the correlation of the arm's hourly scale series with SD-3's, and with the mean of the SD arms on
   Aug 2, 4 and 7 (the day-repeating pattern).
3. Full-day URE and radial / along / cross.

### Reading rules (fixed in advance)

- An arm that **cuts the 12 h scale amplitude by ≥ 30%**, or **decorrelates the pattern** (r with SD-3 < 0.5), identifies a
  coupled channel. Its model term becomes the target of a physical fix (a better PCV/PCO, mapping function or tropospheric
  a priori). The perturbation itself is **not** a fix: removing PCVs or data is not a model improvement.
- An arm that leaves amplitude and pattern within ±15% and r ≥ 0.8 shows that channel is weakly coupled. An error of
  plausible size there cannot produce the breathing.
- URE changes are recorded but not used to adopt anything.

### Resources

Three serial fits of about 60 guarded minutes each, fork8, keep-awake. Chain `Opus_Fork/experiments/sensitivity/run_chain_sens.ps1`,
resumable with `Opus_Fork/resume_chain.ps1 -Chain sens -WaitIfBusy`.

---

<!-- original: Opus_Fork/results/SENSITIVITY_RESULTS.md -->

## Sensitivity fits on 2026-08-03: no tested channel drives the scale breathing; low-elevation weighting costs ~5% URE

Opus, 26 September 2026 UTC. Protocol `SENSITIVITY_PROTOCOL.md`, written before any fit. Chain `Opus_Fork/runs/sens-chain.status`.
Analysis `Opus_Fork/experiments/sensitivity/analyze.py` → `results/sensitivity_analysis.json`.

### Fits

All three converged in 3 linearizations. S-wet1h had one external-load pause and resumed content-bound.

| Arm | Campaign | Guarded s |
|---|---|---:|
| S-nopcv-3 | `20260926T173845Z-fit-S-nopcv-3` | 3,349 |
| S-cut15-3 | `20260926T183508Z-fit-S-cut15-3` | 3,116 |
| S-wet1h-3 | `20260926T192737Z-fit-S-wet1h-3` | 4,076 |

### Result against SD-3 (IGS final truth, 2,976 samples)

| Arm | URE cm | R / A / C cm | Scale 12 h amp (peak) | 24 h amp | r(arm, SD-3) | r(arm, Aug 2/4/7 mean) | Mean scale ppb |
|---|---|---|---|---|---:|---:|---|
| SD-3 | 3.165 | 2.94 / 6.64 / 6.39 | 0.311 ppb (4.5 h) | 0.185 | — | 0.90 | −0.031 |
| S-nopcv | 3.965 (+25%) | 3.66 / 9.16 / 7.52 | 0.245 (−21%) (5.0 h) | 0.092 | **0.94** | 0.81 | **+0.260** |
| S-cut15 | **3.007 (−5.0%)** | 2.79 / 6.42 / 6.03 | 0.329 (+6%) (4.5 h) | 0.177 | **0.98** | 0.87 | −0.015 |
| S-wet1h | 3.120 (−1.4%) | 2.91 / 6.32 / 6.19 | 0.352 (+13%) (4.2 h) | 0.149 | **0.98** | 0.82 | −0.031 |

### Reading, by the rules fixed in advance

- **Satellite PCV (nadir channel): weakly coupled to the breathing.** Removing the whole ±14 mm nadir-dependent PCV shifts
  the constant scale by +0.29 ppb (about 0.8 cm of radius; the nadir channel does set the mean scale). But it changes the 12 h
  breathing by only −21%, below the 30% threshold, and the pattern is unchanged (r = 0.94). A realistic millimetre-level PCV
  error cannot produce a 0.3 ppb breathing. Removing PCVs is also clearly wrong physics (URE +25%).
- **Low elevations and troposphere resolution: not coupled.** Amplitudes change by +6% and +13%, and the pattern stays at r = 0.98.
- **The breathing's source remains unidentified.** It is robust to all three channels, and it repeats with the geometry. Untested
  candidates: receiver antenna PCV; the interaction of the dynamic model with the station network (the census shows only 0.27 cm
  against the POD's 0.87 cm on Aug 3); and a residual error in the sub-daily EOP model's solar and sidereal terms (S2, K1, K2 and
  P1 repeat daily, M2 does not). This is now a diminishing-returns item: the breathing is 0.3 ppb, about 0.8 cm amplitude.

### By-product: the low-elevation data are over-weighted

The 15° cutoff improved URE by 5.0%, with radial, along-track and cross-track all better. The fixtures weight observations as
σ = (0.9 m, 9 mm)/sin(e). The SD-3 post-fit residuals show the phase error grows faster than that:

| Elevation | Phase σ assigned | Phase residual rms | rms/σ |
|---|---:|---:|---:|
| 10–15° | 41.9 mm | 25.4 mm | 0.61 |
| 15–20° | 30.1 | 16.0 | 0.53 |
| 20–30° | 21.7 | 10.3 | 0.47 |
| 30–50° | 14.5 | 5.8 | 0.39 |
| 50–90° | 10.3 | 4.1 | 0.38 |

Phase residual rms follows 1/sin(e)^1.27 in every bin. Code rms/σ is flat (0.41–0.47), so code weighting is consistent.
The principled remedy keeps the data but weights phase as σ = 9 mm/sin(e)^p with p ≈ 1.3. This is calibrated from our own
post-fit residuals, not from IGS. The next test (`ELEVATION_PROTOCOL.md`) compares that weighting and the 15° cutoff on
held-out days.

---

<!-- original: Opus_Fork/results/STATION_TIDES_SCREEN.md -->

## IERS station tide models: screened out as the cause of the POD's remaining scale breathing

Opus, 26 September 2026 UTC. Follows `SDEOP_RESULTS.md` (follow-up 2). With sub-daily EOP, the POD's remaining 12 h/24 h
common-height swing is a pure Helmert-scale oscillation of 0.16–0.37 ppb (about 1–2 mm of network-mean height). The
user asked to test fuller station tide models.

### What was built (fork only; nothing in customkf edited)

`Opus_Fork/station_tides.py`:
- **`dehant`**: a port of IERS 2010 DEHANTTIDEINEL with ST1IDIU, ST1ISEM, ST1L1, STEP2DIU and STEP2LON. Sources are
  hash-pinned in `datastore/static/iers_ch7/`. It reproduces all three IERS test cases to 1.4e-17 m.
- **`ocean_loading_nodal`**: the customkf 11-constituent ocean loading with the standard nodal f/u. August 2026 factors:
  M2 0.968, K2 1.278, K1 1.102, O1 1.165. The HARDISP 342-line sources are downloaded too, but not ported, since the screen
  below makes that unnecessary.

### Screen (`Opus_Fork/experiments/stationtides/screen.py` → `results/stationtide_screen.json`)

Every 15 min on each POD day, the stations' displacement difference (IERS minus the fixtures' models) gets a 7-parameter
Helmert fit. The resulting network scale is compared with the SD arms' residual scale against IGS.

| Day | Observed residual, 12 h | Solid-tide difference, 12 h | OTL-nodal difference, 12 h | Network-mean up, rms |
|---|---:|---:|---:|---:|
| Aug 2 | 0.162 ppb | 0.004 | 0.007 | 0.10 / 0.04 mm |
| Aug 3 | 0.311 | 0.003 | 0.009 | 0.10 / 0.05 |
| Aug 4 | 0.247 | 0.002 | 0.009 | 0.12 / 0.05 |
| Aug 5 | 0.235 | 0.001 | 0.011 | 0.14 / 0.07 |
| Aug 7 | 0.365 | 0.002 | 0.020 | 0.14 / 0.12 |

The model differences are **10–100 times too small**, and their correlation with the residual changes sign from day to day.
Per station (Aug 2, `per_station.py`) the IERS models differ by at most 2.7 mm vertically (solid) and 2.3 mm (ocean loading),
and these cancel across the network. **A POD run would move orbits only at the millimetre level. It was not run: its predicted
effect is below the day-to-day noise.**

### What the residual is instead

- **Not an IGS-side signal.** Hour by hour, our residual scale correlates with NGA's (against IGS) at only −0.32 to +0.55.
- **It repeats with the geometry.** The hourly residual scale correlates 0.73–0.92 between Aug 2, 3, 4 and 7. That includes
  Aug 7, whose fixture was prepared differently, five days later. The mean pattern explains 70–85% of each of those days' variance.
  Aug 5 is the exception (r ≈ 0–0.4). GPS geometry over a fixed network repeats each sidereal day, so a UT-locked, day-repeating
  pattern points to an **observation-model systematic that depends on geometry**, not to a missing force (ocean tides would
  drift with the Moon). The census, fitted to IGS positions without stations, does not show it.
- **Mechanism.** With satellite clocks estimated every epoch, a constellation-wide radial change alters all ranges by
  cos(nadir) ≈ 0.97–1.00, which the clocks nearly absorb. The data therefore see the orbit scale only through the nadir- and
  elevation-dependent part of the observation model. Errors of that shape leak straight into scale, and they repeat with the geometry.

### Candidates for the next test (not run)

In order of prior:
1. **Satellite antenna nadir terms**: PCV/PCO in `customkf/antenna.py`, nominal-yaw axes; IGS20 PCVs are tied to scale.
2. **Troposphere a priori**: standard pressure, NMF, 3 h wet nodes.
3. **Receiver antenna PCV / elevation weighting.**

A cheap first step is to bin the SD fits' post-fit residuals by nadir angle and elevation and look for a systematic
shape. Only then would sensitivity POD arms be worth running (for example satellite PCV off, or an elevation cutoff of 15°),
at about 1 h each on Aug 3 or 4, the most repeatable days.

---

<!-- original: Opus_Fork/results/RESIDUAL_BINNING.md -->

## Post-fit residuals of the sub-daily-EOP fits, binned by nadir and elevation: flat, so the systematic is absorbed

Opus, 26 September 2026 UTC. Follows `STATION_TIDES_SCREEN.md`: the POD's remaining 0.16–0.37 ppb scale breathing repeats
with the constellation geometry, which points to a nadir- or elevation-dependent observation-model term.

### Method (`Opus_Fork/experiments/residuals/replay.py`, read-only)

The converged SD-3 and SD-4 fits were rebuilt exactly as their workers built them (`sdeop.install()`, same fixture,
config and state). Each was evaluated at its final linearization point (x from `lin2-solve`, the `lin2` trajectory
caches) for every epoch, recording each residual with elevation, azimuth and satellite nadir angle.

- Clock values live in x. Re-solving the per-epoch clock block on three epochs changed them by at most 7e-7 m, so these
  are true post-fit residuals.
- The caches record the pre-hook hash of `subdaily_eop.py`. Every other binding field was checked equal, and the caches
  were loaded without the fork's binding check. The hook switch was verified bit-identical beforehand.
- Summaries: `results/replay_summary_SD3.json` and `results/replay_summary_SD4.json`. Per-residual arrays are in the
  `Opus_Fork/runs/*-replay-SD-{3,4}` folders. Each replay takes about 47 s.

### Result

| | Aug 3 | Aug 4 |
|---|---|---|
| Phase residual RMS | 11.6 mm (32,234) | 13.0 mm (30,141) |
| Phase mean, by nadir bin 0–14° | −0.35 … +0.30 mm | −0.69 … +0.16 mm |
| Phase mean, by elevation bin 10–90° | −0.32 … +0.36 mm | −0.76 … +0.29 mm |
| Phase mean, by block × nadir | within ±0.5 mm | — |
| Code RMS | 97 cm | 98 cm |
| Code mean vs elevation | +11.8 cm at 10° → −4 cm above 40° | +12.4 cm → −4.5 cm |

**There is no leftover nadir or elevation signature in phase at the half-millimetre level.** The code trend is ordinary
low-elevation multipath and bias. Code carries far too little weight to set a millimetre-level scale.

### What this means

A phase-based fit absorbs a systematic shape into its parameters rather than leaving it in the residuals: clocks take the
constant part, the tropospheric wet delay takes the elevation part, orbit scale and eccentricity take the nadir part.
Flat residuals are therefore consistent with the breathing hypothesis, but **residuals cannot localize it**. That needs
a sensitivity test: perturb one model term and see whether the breathing (amplitude, UT phase, day-to-day pattern) moves.

### Next step (not run)

Sensitivity POD arms on Aug 3 or 4 (the most repeatable days), about 1 h each through the resumable chain. Each changes one
thing in the workers at run time:
1. **Satellite PCV zeroed** (nadir-dependent satellite antenna term): tests the nadir channel directly.
2. **Elevation cutoff 15° instead of 10°**: tests low-elevation troposphere mapping and multipath.
3. **Hourly instead of 3-hourly wet-delay nodes**: tests troposphere temporal resolution.

A day-repeating breathing that shrinks or shifts under one arm identifies the channel. A cheaper linear-response calculation
(propagating a model perturbation through the fit's normal equations) is possible but needs more plumbing than one arm.

---

<!-- original: Opus_Fork/results/ELEVATION_PROTOCOL.md -->

## Protocol: elevation handling on held-out days — 15° cutoff vs steeper phase weighting

Opus, 26 September 2026 UTC. **Frozen before any E-* fit existed.** The user asked for the work to proceed without
step-by-step consultation.

### Why

On Aug 3 a 15° cutoff improved URE by 5.0%, with radial, along-track and cross-track all better (`SENSITIVITY_RESULTS.md`).
The SD-3 phase residuals grow as 1/sin(e)^1.27, but the fixtures weight phase as 1/sin(e), so low-elevation phase is
over-weighted. Aug 3 chose both the idea and the calibration, so it is **not** evidence here. The test is on the held-out
days Aug 2, 4, 5 and 7.

### Arms (`Opus_Fork.elev`, `run_fit_elev`; each copies its SD comparator exactly except the change)

- **cut15s**: drop rows below 15°. sin(e) is recovered from each row's sigma; on Aug 3 this selection matches the
  orbit-based list exactly (3,579 rows).
- **elw13**: phase sigma = 9 mm/sin(e)^1.3 (was /sin(e)); code and zenith sigma unchanged; p frozen from Aug 3.

| Day | Comparator (SD) | URE | Base variant | Config, chunk/groups |
|---|---|---:|---|---|
| Aug 4 | SD-4 | 3.364 | erp+thrust+iiia2600+sdeop | unit-ecom5, 12/2 |
| Aug 7 | SD-7 | 3.409 | erp+thrust+sdeop | cross_date config, 18/4 |
| Aug 2 | SD-2 | 3.401 | erp+thrust+sdeop | unit-ecom5, 12/2 |
| Aug 5 | SD-5 | 3.249 | erp+thrust+iiia2600+sdeop | unit-ecom5, 12/2 |
| Aug 3 (in-sample, last) | SD-3 | 3.165 | erp+thrust+iiia2600+sdeop | elw13 only; cut15s = S-cut15-3 (3.007) |

Order: cut15s-4, elw13-4, cut15s-7, elw13-7, cut15s-2, elw13-2, cut15s-5, elw13-5, elw13-3. Cap 6, cold start, the
unchanged stationarity rule. Scoring uses `evaluate_sd` against IGS final with NGA on the same keys.

### Predictions

1. **cut15s**: URE below the SD comparator on **≥ 3 of 4** held-out days, with a mean change **≤ −2%**.
2. **elw13**: the same criteria.
3. elw13's mean change is at least as good as cut15s's. Down-weighting keeps the geometry, so it should do no worse.
4. **No damage**, for any adopted variant: no satellite's 3D RMS regresses by more than 0.1 m, and radial RMS is at most
   the comparator's plus 3% on every held-out day.

**Falsification per variant.** URE worse than the comparator on 2 or more held-out days: that variant is not adopted.

**Adoption.** Among the variants that meet 1 or 2, and 4, the one with the better mean held-out change becomes the default
for new fork fits, together with sub-daily EOP. Within 0.5% of each other, elw13 is preferred because it keeps the data.
p = 1.3 and the 15° value are not retuned on these days.

### Resources

Nine serial fits of about 55–65 guarded minutes each (about 9 h), fork8, keep-awake. Chain
`Opus_Fork/experiments/sensitivity/run_chain_elev.ps1`, resumable with `Opus_Fork/resume_chain.ps1 -Chain elev -WaitIfBusy`.

---

<!-- original: Opus_Fork/results/ELEVATION_RESULTS.md -->

## Elevation handling: steeper phase weighting (elw13) ADOPTED; 15° cutoff REJECTED

Opus, 27 September 2026 UTC. Protocol `ELEVATION_PROTOCOL.md`, written before any E-* fit and pinned in every E-* fit
record through `--protocol`. Chain `Opus_Fork/runs/elev-chain.status`. Scoring `experiments/sensitivity/score_elev.sh`
→ `results/arm_elev_aug{2,3,4,5,7}.json`, `results/elevation_summary.json`.

**Scope, in the terms of the correction index (`CORRECTIONS.md`).**
- Aug 2, 4, 5 and 7 are **new-arm contrasts on previously studied days** (M03), not untouched holdouts. They did not
  choose p = 1.3; Aug 3 did.
- p = 1.3 is a weighting choice justified by its outcome on those days, **not a calibrated noise law** (M05).
- Scores are against the IGS-final reference. Inputs are retrospective.

### Fits

All nine converged in 3 linearizations.
- E-elw13-4 had two interruptions: an external-load stop, and one caused by Opus's own manifest scan.
- E-cut15s-5 was interrupted by an external-load stop and the user's overnight stop.
- All resumed content-bound. Guarded time totalled about 29,500 s. Campaigns are `Opus_Fork/runs/*-fit-E-{cut15s,elw13}-{2,3,4,5,7}`.

### Scores (full day, URE and R/A/C in cm)

| Day | SD (current default) | cut15s | **elw13** | NGA URE |
|---|---|---|---|---:|
| Aug 4 | 3.364 · 3.11/8.06/5.80 | 3.347 (−0.5%) | **3.218 (−4.3%)** · 3.00/7.33/5.58 | 4.359 |
| Aug 7 | 3.409 · 3.14/7.80/6.63 | 3.297 (−3.3%) | **3.272 (−4.0%)** · 3.03/7.11/6.53 | 4.195 |
| Aug 2 | 3.401 · 2.95/11.29/5.56 | 3.457 (+1.7%) | **3.299 (−3.0%)** · 2.88/10.57/5.59 | 4.427 |
| Aug 5 | 3.249 · 3.03/6.48/6.53 | 3.326 (+2.4%) | **3.199 (−1.5%)** · 3.01/6.12/6.16 | 4.826 |
| *Aug 3 (calibration day, not evidence)* | 3.165 | 3.007 (−5.0%) | 3.035 (−4.1%) | 4.289 |

3D (cm), full day and the 18–24 h window:

| Day | SD | elw13 | NGA | Late window: SD → elw13 |
|---|---:|---:|---:|---|
| Aug 4 | 10.41 | **9.69** | 10.93 | 11.90 → 11.24 |
| Aug 7 | 10.71 | **10.12** | 10.56 | 12.12 → 10.97 |
| Aug 2 | 12.92 | 12.30 | 10.91 | 19.72 → 18.60 |
| Aug 5 | 9.69 | **9.19** | 11.76 | 10.99 → 10.51 |
| Aug 3 | 9.67 | **9.28** | 10.78 | 11.99 → 11.35 |

With elw13, 3D is below NGA PE's on 4 of 5 days: Aug 7 joins Aug 3, 4 and 5. Aug 2 remains behind because of its
late-window along-track error.

### Against the frozen predictions

| # | Prediction | cut15s | elw13 |
|---|---|---|---|
| 1/2 | Better on ≥ 3 of 4 held-out days, mean ≤ −2% | 2 of 4, mean **+0.06%**: **fail** | **4 of 4, mean −3.22%: pass** |
| 3 | elw13 at least as good as cut15s | — | −3.22% vs +0.06%: **pass** |
| 4 | No satellite 3D regression > 0.1 m; radial ≤ comparator + 3% | worst +3.3 cm; radial Aug 5 +3.3%: **fail** | worst **+1.4 cm**; radial within +3% on all days: **pass** |
| Falsification | Worse on ≥ 2 held-out days | **met: not adopted** | not met |

**Adopted:** elw13 (phase sigma = 9 mm/sin(e)^1.3, code unchanged), together with sub-daily EOP. The default for new
fork fits is now `Opus_Fork.run_fit_elev --variant erp+thrust+iiia2600+sdeop+elw13`, or `erp+thrust+sdeop+elw13` where
the IIIA mass variant is not wanted. p and the 15° value were not retuned.

**Reading.**
- The 15° cutoff's 5.0% gain on Aug 3 did not transfer: it helped on two days and hurt on two. Throwing low-elevation data
  away costs geometry.
- Down-weighting the same data instead of discarding it helped on every day. Along-track improved most: 0.2 to 0.7 cm, the
  largest share of the 3D gain.
- This supports "the fixtures' 1/sin(e) law over-weights low-elevation phase relative to what helps the orbit". It does
  not identify the true noise law (M05). A calibration using leverage-corrected residual variance, or one independent of
  these days, would be the proper next step if the exponent matters.

---

<!-- original: Opus_Fork/results/TRANSFER_CALCULATION.md -->

## Joint weighted transfer calculation: result (review follow-up #2, M08)

Opus, 29 Sep 2026 01:47 UTC. Protocol: `experiments/transfer/PROTOCOL.md`. Its body is pinned
(`e4c39bff…6edc9`) and was written before any output existed. Amendment A1 is pinned separately (`35c35fbd…fae8`)
and was written before any candidate had been analysed. Result:
`experiments/transfer/transfer_result.json`, a copy of the run `runs/20260929T014726Z-8e470a08/transfer.json`,
with `transfer.npz` `b32c7278…3b8c`. The earlier run's output is kept as `transfer_result_A0_not_analysed.json`;
its candidates are recorded there as "NOT ANALYSED".

**Diagnostic only.** This is a linear response at one converged point: SD-3, Aug 3, 25 stations, the SD-3
configuration and weighting. It is not a fit and not an accuracy acceptance. IGS final is a reference, not truth.

### Prerequisites and calibration (all pass)

| Check | Rule | Result |
|---|---|---|
| K2 R (after row-sign alignment, A1) | ≤ 1e-6 relative | 2.3e-15; 89 rows sign-flipped; the raw sign-sensitive difference, 1.45, is kept in the output |
| K2 z (after alignment) | ≤ 1e-6 relative | 1.4e-13 |
| K3 predicted reduction | within 10% of the fit's 6.289e-06 | relative difference 2.4e-13; trajectory step bound 0.038 mm |
| C1 mean scale, nopcv | within 20% | predicted 0.290288 ppb vs actual 0.290289 ppb (relative error 2.4e-6) |
| C2 per-epoch scale pattern | r ≥ 0.80 | r = 0.99999999999 |
| C3 orbit level | residual ≤ 30% of the change | 1.4e-5 of 6.77 cm 3D; worst satellite 6.0e-5 |

The linear transfer reproduces the actual S-nopcv nonlinear refit almost exactly. It can therefore be used to
predict first-order refit responses to the other observation-model perturbations at this point.

### Candidates against the observed SD-3 breathing

Observed (per-epoch Helmert scale against IGS final, hourly means):
- 12 h: **0.311 ppb**, peaking at 4.53 h UT;
- 24 h: 0.185 ppb at 9.4 h UT;
- mean: −0.031 ppb.

For the tide candidates, "ours − IGS" is the negative of the response (protocol sign convention). The categories
are the protocol's thresholds on the implied 12 h amplitude.

| Candidate (δ model) | Implied 12 h amplitude | Fraction of observed | Peak (UT) | Hourly r with observed | Category |
|---|---|---|---|---|---|
| Solid tide, IERS DEHANT − fixture | 0.0047 ppb | 1.5% | 11.7 h | −0.31 | **negligible** |
| OTL nodal f/u − fixture | 0.0037 ppb | 1.2% | 6.7 h | −0.07 | **negligible** |
| Both tides together | 0.0024 ppb | 0.8% | 10.1 h | −0.34 | **negligible** |
| Satellite PCO z +1 cm (G01, G02 only) | 0.0019 ppb | 0.6% | 5.4 h | −0.11 | (sensitivity) |
| Satellite PCV removed (the calibration arm) | 0.093 ppb | 30% | 9.2 h | −0.76 | (calibration, not a candidate) |

Unit kernels, 1 mm, all stations or all satellites (per-mm gains; no category, because the size is not a model
difference):

| Kernel | Mean scale | 12 h amplitude (peak UT) | 24 h amplitude | Needed for 50% of observed 12 h |
|---|---|---|---|---|
| Station height, constant | +0.018 ppb/mm | 0.004 (5.5 h) | 0.008 | — |
| Station height, 12 h cos / sin | — | 0.031–0.033 ppb/mm | — | **≈ 9.5 mm** synchronous semidiurnal height at every station, peaking 4.3 h UT (the joint 12 h + 24 h inversion gives 9.7 mm at 4.5 h, plus 9.8 mm at 9.7 h for the 24 h term) |
| Satellite antenna, +1 mm × (nadir/14°) | +0.028 ppb/mm | 0.0058 (5.5 h) | 0.013 | ≈ 27 mm |
| Satellite antenna, +1 mm × (nadir/14°)² | +0.030 ppb/mm | 0.0063 (5.4 h) | 0.014 | ≈ 25 mm |
| Receiver antenna, +1 mm × cos(elevation) | +0.029 ppb/mm | 0.0059 (5.6 h) | 0.013 | ≈ 26 mm |

- **Constant network height.** It transfers to scale at 0.018 ppb/mm. A pure similarity transform would give
  0.157 ppb/mm, so about 89% is absorbed by clocks, wet delay and ambiguities.
- **Crosstalk** between the 12 h and 24 h height kernels is ≤ 0.0024 ppb/mm.
- **Formal uncertainty** of a 12 h scale coefficient: about 0.11 ppb at unit weight, with an a-posteriori variance
  factor of 0.24. This uses fixture sigmas and white noise. It is not a calibrated uncertainty and is not used for
  any decision here.

### Reading (level of inference as declared in the protocol)

1. **Station tides (M08).** The joint weighted transfer confirms the earlier screen, which the review had said
   could not settle the question. Replacing the fixture's solid-tide and ocean-loading models with the IERS
   DEHANT and nodal versions would change the 12 h breathing by ≤ 1.5% of its size. For this configuration, tide
   model differences are **disfavoured as the main cause**. This is not an exclusion under other networks or
   weightings, and not a statement about the reference's own tide handling.
2. **Antenna-type observation errors.**
   - Nadir- and elevation-shaped antenna terms have the right phase (peaks 5.4–5.6 h vs 4.5 h UT) but a small gain,
     about 0.006 ppb/mm.
   - Reaching half the observed amplitude would need a network-wide systematic term of about 25–27 mm of that
     shape. For comparison, the whole satellite PCV table produces a 30% response at the wrong phase.
   - Such terms are therefore **minor contributors at most** unless errors of centimetre size exist. That is a
     hypothesis for a controlled refit, not an identification.
3. **A network height signal.** It would have to be about 1 cm, semidiurnal and in phase in UT at all 25
   stations. The tide candidates tested produce nothing close. This kernel only says what magnitude would be
   required. It does not identify a source.
4. **What remains untested by this calculation.** It is limited to observation-model perturbations δy.
   Dynamical (force-model) errors and the reference product's own scale behaviour are outside it. The 0.3 ppb
   breathing remains **unexplained**.

### Recommended next step

The next step is a reference cross-check, evaluation only, with no fit. It asks whether the same 12 h scale
pattern appears in NGA PE − IGS final and in SD-3 − IGS rapid, both available for Aug 3.
- If NGA − IGS final shows it, the breathing is at least partly in the reference.
- If only our orbits show it, a dynamical term becomes the leading candidate, and a force-side transfer kernel
  (trajectory partials for a twice-per-revolution acceleration) would be the next diagnostic.

---

<!-- original: Opus_Fork/results/CORRECTIONS.md -->

## Correction index for Opus_Fork (and related claude/) claims

Opus, 26 September 2026 UTC, opened in response to Astra's external review
`research/opus_work_review_20260926/findings.md` (2 Critical, 15 Major, 7 Minor, 3 Improvement).

**How this file works.** It is append-only. The original documents are **not edited**: several are pinned by
campaigns, and all were hashed by the review as examined. Each row maps an original claim → the finding → the statement
that should be read instead → the status of any fix. Entry points (`Opus_Fork/README.md`) link here. Code fixes are
tracked here and made separately. The corrected statements are my acceptance of the review; where I add nuance, it
says so.

### What the review confirmed as sound (kept)

- The saved raw scores. Aug 2 SD/P1/NGA reproduce to 4e-9 m (3D) with independently written scoring arithmetic. The
  baseline P0/NGA reproduce too.
- The orbit-only URE formula, the NGA convention handling, and same-key scoring.
- The sub-daily EOP (SD) result under its declared gate: URE −18.38, −18.35, −16.82, −15.31 and +0.16% (mean −13.74%).
  These are **retrospective diagnostic gains on previously studied days**, not five runs of one operational configuration.
- The constrained ECOM-7 negative result was respected and not adopted.
- Fixed ERP/thrust is physically motivated; no sign or unit reversal was found.
- The ORTHO_EOP and DEHANT ports reproduce their published tests.
- Archive practice: content hashes, source snapshots, negative results kept, and SD/sensitivity/elevation protocols pinned.

### Corrections to read instead of the original wording

| # | Where (original, unchanged) | Original claim | Finding | Read instead | Status |
|---|---|---|---|---|---|
| C01 | `Opus_Fork/export.py:176–214` (`write_from_solution`) | Export is QA-checked and correct | Uses plain EOP for **SD solutions**. Wrong by 4.9 cm RMS (8.4 cm max); its own QA passes | **Do not publish SD solutions through `export.py`** until fixed. Saved SD scores are unaffected (`evaluate_sd` maps correctly) | Fix scheduled (step 2): model-aware frame choice, round-trip of all 5 SD arms, a wrong-model negative control |
| C02 | `README.md:115`; `results/URE_REVIEW_AND_TEST_PLAN.md:195–198,331` | "No fit reads them"; IGS-fitted numbers never enter a fit | `ECOM7P_PROTOCOL.md:11,19–24` set the Dc2/Ds2 prior width (2 nm/s²) from the IGS-position census. `claude/roadmap/BLOCK_D0_PROTOCOL.md:15–43` used IGS-rapid-derived block coefficients | Three categories. **(a) Station-only with predeclared external models:** the current default (ERP+thrust, published effective IIIA mass, IERS sub-daily EOP, no reference-derived priors). **(b) Reference-informed development:** ECOM7P prior width, block-D0, census diagnostics. **(c) Evaluation-only:** IGS final, NGA PE. Only (a) supports a reference-independence claim | README fixed here |
| M01 | Rapid-latency framing (`AGENTS.md` objective; `fetch_metadata.py:8–14`) | Inputs rapid-feasible; metadata "does not depend on the day" | Retrospective inputs (e.g. finals2000A resolves to Bulletin B for MJD 61252–61253); no as-of replay | All results are **retrospective**. A rapid-latency claim needs an as-of input replay | Open (later step) |
| M02 | `T2_1_ERP_PROTOCOL.md`, `WEIGHTS_*`, `IIIA_AUG345_*`, `ECOM7*_PROTOCOL.md`, `SWING_ORIGIN_NOTES.md:38–67` | "Frozen before any fit" | P1 started 20:54:45, protocol file created 21:02:48. W1 was running when its protocol was written. Most early protocols are not pinned in fit records. The SWING notes chronology is ambiguous | These are **not** proven pre-registrations. The SD, sensitivity and elevation protocols are pinned in their fit records via `--protocol` (the positive examples). From now on, every protocol is pinned before launch, and amendments are an append-only record | Practice adopted |
| M03 | `ECOM7P_HOLDOUT_PROTOCOL.md:16`; `ELEVATION_PROTOCOL.md` (running) | Days "played no part in choosing it" / held-out | Those dates' baselines and patterns had informed the diagnosis | "**New-arm contrasts on previously studied days**", not untouched holdouts. Truly untouched dates are needed for a transfer claim | Label corrected here |
| M04 | `README.md:30–35`; `PLAN.md:26–45,158–160`; `NOTES_FOR_ASTRA.md:119–152`; `results/BASELINE.md:100–117,137`; `results/DIAGNOSIS.md:16–44,59–66,123–144`; `results/WEIGHTS_W1.md:1,19–20,65–67,102–104`; `claude/DYNAMICS_EXTENSION.md:72–83`; `claude/FORCE_PARAMETER_ALL31.md:53–61` | "The cause is the error model, not the force model"; "mechanism confirmed"; "force model is not the bottleneck anywhere" | Weight sensitivity and reference-fit capacity do not isolate a physical cause. Later ERP/thrust and SD gains contradict the exoneration | "**Weight-sensitive on this fixture; physical cause unresolved.**" Forces and frame did matter (ERP/thrust −4 to −9% URE; SD −15 to −18%) | README fixed here |
| M05 | `Opus_Fork/reweight.py:25–31`; `results/DIAGNOSIS.md:73–75`; `results/SENSITIVITY_RESULTS.md` (elevation table) | "Helmert VCE"; normalized residual RMS certifies σ over-estimate; post-fit slope shows low elevations over-weighted | Post-fit residual variance ≠ observation variance: Cov(r) = (I−H)Σ(I−H)ᵀ, and leverage and nuisance parameters are ignored | "**Empirical residual reweighting.**" The elevation slope is a reason to test weights, not a calibrated noise law. The running elevation test (elw13) tests one weighting, not the noise law | Wording corrected here |
| M06 | `claude/roadmap/BENCH_RESULTS.md:46–53,62–63`; W2 "beats NGA" (0.79 mm); `results/DIP_AND_NGA_DISTRIBUTIONS.md:123–159` | p ≈ 1e-20; "beats NGA" | Satellite-days and samples are not independent. The W2 margin is tiny, and its cross-track worsened | Descriptive only. Report paired daily changes and ranges; no population inference from five studied days | — |
| M07 | `results/IIIA_AUG345_RESULTS.md:142–159` | "2,600 kg does exactly what the physics says"; "mass fix validated on three dates" | Compared B against the composite erp+thrust+iiia2600 package; no same-day 2161 kg control. 2600 kg is a published **effective** value (Steigenberger 2020, GPS74) | "**Composite package gain; mass contribution not isolated.**" The 0.80 shift ratio is supportive, not a control | Control fit optional (later) |
| M08 | `results/STATION_TIDES_SCREEN.md:13–14,29–41`; `results/SDEOP_RESULTS.md:88–99`; `experiments/stationtides/screen.py:40–47` | Station tides "screened out", "10–100× too small", "POD would move orbits only at mm"; "not an IGS-side signal"; scale correlation proves a network cause | An unweighted 7-parameter network projection is not the joint orbit/clock/troposphere transfer. A radial common mode projects onto Helmert scale almost by construction. Weak correlation against a shared reference does not exclude reference error | "**The unweighted network-scale projection of the IERS-vs-fixture tide differences is small (0.001–0.02 ppb); the orbit response was not computed.**" Station-side, reference-side and dynamics-side origins of the residual breathing all remain open. HARDISP is not shown to be unnecessary | Transfer calculation planned (step 3) |
| M09 | `reference_census.py:176–188`; `results/T0_T1_RESULTS.md:57–64`; `results/BOXWING_CENSUS_RESULTS.md`; `results/SWING_ORIGIN_NOTES.md:79` | Numerical-floor acceptance; pooled % changes | A 1 cm floor bound is not small against ~1 mm claims. Variants compared over 30/31/32 different satellites | Census comparisons across **different satellite populations are not matched effects**. Floor-terminated fits must not rank small physical differences. (The SD census Aug 2 used 30 vs 32 satellites; its large changes survive, but the percentages are approximate) | Recompute on common keys when next used |
| M10 | `claude/roadmap/traj_cache.py:62–79` (+ fork bindings) | Cache validated | Accepts wrong fixture/config/origin and short coverage (reproduced) | **Latent loader bug**; no scored campaign shown affected | Fix planned (step 2; the shared file needs approval) |
| M11 | `Opus_Fork/evaluate.py:74–79` | "Verified converged checkpoint" | Also accepts `iteration_complete`; the fixture is not cross-checked against the solution; EOP choice is independent of solution provenance | Acceptance-grade scoring must bind final state, fixture, config, model and EOP | Fix planned (step 2) |
| M12 | `Opus_Fork/prepare.py:247–252`, `merge_navigation:127–181` | "Deterministic content … same hash" | gzip mtime makes the bytes differ; overwrites a fixed store path. First-23-character de-duplication is a risk | Content is deterministic; **bytes are not** | Fix planned (step 2) |
| M13 | `README.md:88–97`; `guard.py` | "75% CPU/GPU/RAM stop threshold" unchanged | Since 25 Sep, GPU and telemetry gaps use a **10 s continuous hold**. Intermittent high GPU with <10 s dips never stops (95% high over 40 s shown) | Sampled CPU/RAM thresholds plus a continuous 10 s GPU/telemetry hold. Not an absolute GPU ceiling | README fixed here |
| M14 | `README.md:72–74`; `guard.py` mutex; `resume_chain.ps1` | Mutex prevents collisions with Astra's campaigns | The mutex is held per worker and released between workers. A sleeping chain has no Python process (observed 22:13 UTC). The process check has a race. Opus's own "placeholder Python" pause relied on the same gap | **No campaign-level lease exists yet.** Collisions are possible between workers or during back-off | Lease planned (step 4) |
| M15 | `results/SENSITIVITY_RESULTS.md:27–39`; `results/RESIDUAL_BINNING.md:1,30–38`; `experiments/residuals/replay.py:41–44` | PCV "weakly coupled"; cut15/wet1h "not coupled"; flat bins show an absorbed systematic | PCV (−21.1%, r = 0.938) lies **between** the protocol's categories. Removing one nominal PCV curve does not bound all error shapes. Flat pooled means can hide cancelling structure. The SEM is unweighted and assumes independence | PCV: "**inconclusive under the written protocol.**" cut15/wet1h: "weak numerical response of the breathing in these two arms." Residual bins: "no pooled nadir/elevation mean offset; not an identification." Use "IGS-final reference", not "IGS final truth" | Wording corrected here |
| N01 | `results/BASELINE.md:58–59`; `README.md:25`; `PLAN.md:17` | Without G21: radial P0 4.25, NGA 4.28 cm | Copied from the all-satellite table | **P0 4.11 cm, NGA 4.35 cm** (2,496 keys). 3D/URE unchanged | README fixed here |
| N02 | `claude/ERROR_MODEL_AND_FRAME.md:39–60,78` | Flatten the elevation law | Residual ratio 7.88 against σ ratio 4.33 needs a **steeper** law | Steeper, as already acknowledged in `claude/FIXTURE_VARIANTS.md:36–69`; still subject to M05 | — |
| N03 | `export.py:58–65,111–136,198–201` | Export QA passes | Partial-day header says midnight while data start at noon. Accuracy codes come from the initial covariance | Header must be derived from the emitted epochs; accuracy codes unknown unless calibrated | Fix planned (step 2) |
| N04 | `Opus_Fork/hfeop_ds.py:11–12,28`; `STATION_TIDES_SCREEN`/`SDEOP_RESULTS` mentions | "Libration under 2 mm at GPS" | Never computed. The IERS tests imply up to ≈5.1 mm (UT1) and ≈3.7 mm (polar motion) | "**Libration omitted; up to ~5 mm at GPS altitude; not quantified over these arcs.**" TT−UTC is hard-coded (valid for 2026 only) | Docstring fix (step 2); quantify when next used |
| N05 | `Opus_Fork/ngv_pilot.py:19–20` (`day_of`) | Metadata for the fit day | Origin is 10 s before midnight, so the **previous day's** metadata is used (confirmed: the Aug 3 fixture gives 2026-08-02) | No PRN/mass change shown at these boundaries; no score shown affected | Fix planned after the running campaign (file pinned by it) |
| N06 | `README.md:52,83` | fork8 = 8 threads | fork8 = **1 numerical thread × 8 processes** (fork8t = 8 threads). The validator admits up to 6 GiB/60%/12, beyond the authorized profile | Authorized policy is the named fork8 profile, not the validator maximum | README fixed here |
| N07 | `claude/roadmap/streaming.py:11` | Memory independent of arc length | Global parameters (wet nodes, ambiguities) and recovery blocks grow with the arc | Streaming avoids the full design matrix; memory grows with global parameters and stored blocks | — |
| I01 | `Opus_Fork/run_fit.py:117–134` | Controller exempt from drift refusal on resume | Transparent, but unbounded | Only reviewed diff classes; keep both sources | Later |
| I02 | `results/ARC_CENSUS.md`; `native_gap_partition_review/REVIEW.md:57` | Native-gap candidates as slips; "correction block added" | Correction reverted to keep pins | Read `results/ARC_CENSUS_ERRATA.md:74–82`; REVIEW.md:57's reference to an in-file correction is obsolete | This index |
| I03 | `results/DIP_AND_NGA_DISTRIBUTIONS.md:45–49,65–68`; `results/ECOM7_RESULTS.md:87`; `results/BOXWING_CENSUS_RESULTS.md:3–5,54–63`; `results/IIIA_AUG345_RESULTS.md` ("1/rev is SRP", "rest" observation-driven); `results/T2_1_ERP_RESULTS.md:59–67`; `results/URE_REVIEW_AND_TEST_PLAN.md:99–102`; `claude/ERROR_MODEL_AND_FRAME.md:82–105`; `claude/PROJECT_REVIEW.md:12–14,63–65,91`; `claude/STATION_EXTENSION_PIMO.md:1–6,56–65` | "Oscillation is an SRP limit", "not in the IGS reference"; D2 "confirms missing 2/rev SRP"; harmonic shares as physical components; "PCO-z goes into the clock, not the radius"; "EOP excluded" by a constant Helmert; stations "unbiased"; station dimension "exhausted" | Harmonic allocations are order-dependent reductions, not physical variances. An extra force basis can absorb a frame error, as the SD finding showed. A constant Helmert cannot test time-varying EOP. PCO/radial/clock are nearly, not exactly, degenerate | Read as **hypotheses at the time**. The 12 h swing was largely missing sub-daily EOP, not SRP. "Radius set by dynamics" is a near-degeneracy, not exact. EOP was *not* excluded (time-varying SD EOP was untested until 25 Sep) | This index |

### Cross-check discipline adopted from the review

1. Separate **observed statistic → intervention tested → assumptions → alternatives → level of inference** for every
   conclusion. Correlation, harmonic share and one-factor sensitivity are not attribution.
2. Pin the protocol (exact bytes) in the campaign before launch. Amendments are append-only, with before/after hashes and
   whether outcome data existed.
3. Call reused dates "new-arm contrasts on previously studied days". Reserve untouched dates for transfer claims.
4. Before a multi-hour fit to test a mechanism, run the **joint weighted transfer calculation** (review follow-up #2).
5. Keep the three input categories of C02 explicit in every result.

### Status update, 28 Sep 2026 (append-only; earlier rows are unchanged)

Statuses follow the ledger's terms (`docs/consolidation/finding_ledger.md`): documented / implemented / tested /
independently reviewed. **Nothing below has been independently reviewed yet.** Astra's review predates every fix.

| # | Status | Evidence | Remaining |
|---|---|---|---|
| C01 | implemented, tested | `Opus_Fork/export.py` (frame from the solution's `force_model.json`, unknown model refused, fixture binding, `roundtrip` mode). `results/review_fixes_check.json`: the 5 SD arms match the scoring path ≤ 0.50 mm; the forced plain-EOP control differs 82–126 mm while its own QA passes; plain P1 matches both | The round-trip shares the frame/SD/SP3 code with the exporter, so it cannot catch a shared error. An independent oracle is still needed (consolidation Phase 4). The SD model and EOP-file hashes are recorded, not enforced. Refusal paths were not triggered by a test (added below). A solution with no provenance was exported as plain EOP silently (fixed below). The Aug 2 SD round-trip file was overwritten by P1's (fixed below) |
| N03 | implemented, tested | `export.py` header derived from the emitted epochs, `header_consistency`; selftest: noon-start file passes, mislabelled header caught; accuracy codes 0 | — |
| M11 | implemented | `Opus_Fork/evaluate.py` converged-only unless `--diagnostic-allow-iterate`, fixture binding, frame from provenance. Generic evaluate re-scored SD-2 with raw scores identical to the saved ones | Refusal paths not triggered by a test (added below) |
| M12 | implemented, tested | `Opus_Fork/prepare.py` deterministic gzip, no conflicting overwrite, conflicts reported; `review_fixes_check.json`. 8,675 duplicate-key conflicts on the Aug 1/2 pair (Galileo 6,789, BeiDou 1,712, GLONASS 84, GPS 73, SBAS 7, IRNSS 6, QZSS 4) | The GPS "non-material" classification was checked interactively; an evidence file is added below. The first-wins policy is unchanged; the conflict policy is a user decision |
| N05 | implemented | `Opus_Fork/ngv_pilot.py` metadata day = arc midpoint; in-arc metadata change refused; metadata identical for all campaign day pairs | Still day-granular (not the record's validity interval); no midnight regression test yet (added below) |
| N04 | documented | `Opus_Fork/hfeop_ds.py` docstring corrected | The bound over these arcs is still not quantified |
| M10 | implemented, tested | commit `39ba52f`: `claude/roadmap/traj_cache.py` loader contract, writer records origin, duration, grid and integration fingerprint. `tests/test_traj_cache_contract.py` 18/18 (Astra's probe now refused). `tests/traj_cache_compat.py` under usage75: archived SD-3 caches accepted, states bitwise equal to the saved solution, wrong fixture/config refused | Fork copies of the cache writer (`ngv_traj_cache`, `e7_traj_cache`, `nongrav_traj_cache`) do not record the new fields; they are checked on fixture/config/grid only. They are merged in consolidation Phase 3 |
| M08 | implemented (diagnostic) | `Opus_Fork/experiments/transfer/`: the linear transfer reproduces the S-nopcv nonlinear fit to 1.4e-5 relative | Candidate analysis pending (protocol amendment A1: the K2 check compared QR rows including sign) |
| M14, M13/N06 tests, I01, M01, M07 | documented only | — | Campaign lease: module and design next; unified guard in Phase 3 |

### Follow-up, 28–29 Sep 2026 (append-only; completes the "added below" items above)

| # | Status now | Evidence |
|---|---|---|
| C01 | implemented, tested | Export now refuses a solution with no `force_model.json` unless `--assume-plain-eop` (labelled ASSUMED). Round-trip and negative-control files are named per solution. `tests/test_review_fix_refusals.py` (18/18) triggers the export refusals: unconverged, hash mismatch, wrong fixture, missing provenance, unknown model. `check_fixes` rerun 29 Sep 01:45 UTC (`runs/20260929T014531Z-accead18`): ALL PASSED. **The independent oracle is still open** (Phase 4) |
| M11 | implemented, tested | `evaluate.accept_arm` has the same logic, now testable. A no-provenance arm is labelled "daily finals only (ASSUMED …)". Tests: unconverged refused unless the diagnostic flag is given; a failed status is refused even with the flag; hash mismatch, wrong fixture and unknown model refused; provenance labels checked |
| N05 | implemented, tested | Test on the real Aug 2 origin (23:59:50 GPS): metadata day = 2026-08-02. An in-arc metadata change is refused before any model is built. Still day-granular |
| M12 | implemented, tested; GPS classification evidenced | `experiments/review_fixes/nav_conflicts.py` → `results/nav_conflicts_gps.json` (`runs/20260929T014552Z-d497ef9e`). All five campaign day pairs: 386 GPS conflicts, none with a different IODE/IODC or health. 172 differ in orbit/clock fields only by print precision; both records evaluated every 300 s over toe ± 2 h differ by ≤ 0.32 mm in position and ≤ 0.15 µm in clock; 0 unevaluated. The other systems are unused by the GPS-only fit. **The first-wins policy is unchanged and remains a user decision** |
| M13, N06 | characterized (tests) | `tests/test_guard_hold_semantics.py` 10/10 (commit `ab3ed98`): the review's intermittent series (95% of samples high) never stops, which confirms and pins the documented limitation. The validator range (6 GiB/60%/12/12) is wider than any profile. No guard behaviour changed; named maxima are Phase 3 step 6 |
| M14 | implemented, tested; **not wired** | `customkf/runtime/lease.py`, `tests/test_campaign_lease.py` 14/14 (commit `961c414`), including a second controller refused between two serial workers and during back-off. Integration design: `docs/consolidation/M10_M14_FIXES.md` |
| M08 | implemented (diagnostic), result | `results/TRANSFER_CALCULATION.md`. Prerequisites K2 (after amendment A1) and K3 pass; calibration C1–C3 pass (relative error 2.4e-6, r ≈ 1, residual 1.4e-5). The IERS-vs-fixture solid tide and OTL nodal differences imply ≤ 1.5% of the 0.311 ppb 12 h breathing: negligible **for this configuration** (Aug 3, SD-3), not an exclusion. The protocol pin check now pins the body and each appended amendment separately (`common.check_protocol`, tamper-tested); the body hash is unchanged |

Nothing above has been independently reviewed.

### Follow-up, 1 Oct 2026: Sol review and Astra follow-up (append-only)

| # | Status | Evidence |
|---|---|---|
| SOL-01 / AF-02 | implemented, tested (adopted path) | Domain-aware correction stencil with finite checks and a stable second-order fallback, used by the link Jacobian, the receiver-clock stencil and the force-column partials (`08acbe7`, `126328b`). On the real Jun 23 data, 2,776 of 2,777 link Jacobians and all 13,885 force partials are bitwise equal to the former code. Off-path copies remain: BACKLOG B12 |
| SOL-02 | implemented, tested | Resume must match the immutable campaign `spec` before any mutation; legacy records need `--legacy-resume` (`0452811`) |
| SOL-03 | implemented, tested | The chunk worker refuses empty, backward or out-of-range spans (`2fb0d46`) |
| SOL-04 | implemented, tested | Dated restore opens only model files recorded at that path (`aedb725`) |
| SOL-05 | implemented, tested | Accepted, identity-bound previous points and directions, through one loader (`8676f41`) |
| SOL-06 | implemented, tested | Semantic worker acceptance before `ok` and on reuse; rejected workers recorded `rejected` (`66535aa`) |
| SOL-07 | implemented, tested | The guards report `cleanup_failed` (keeping `worker_status`) when release raises; an already-absent admission is recorded as a note (`eee0e97`) |
| SOL-08 | implemented, tested | The streaming accumulator validates raw sigmas, shapes and checkpoint layout (`a8a7936`) |
| AF-01 | implemented, tested | Disappearance-safe scratch accounting in both guards (`168f51a`) |
| AF-03 | documented | Errata E1 in the untouched-date protocol and errata in its RESULTS (`85f0919`) |
| SCI-06 | documented here; the code wording change is deferred | `Opus_Fork/elev.py` says low-elevation phase is "therefore over-weighted" because residuals grow as 1/sin(e)^1.27. A post-fit residual slope does not identify an optimal noise law. **Correct reading:** elw13 is a frozen empirical weighting candidate, motivated by studied-date residuals and selected using reference scores. The docstring is not edited now, because `elev.binding()` includes the file hash, so a wording edit would change the force-model identity recorded by new campaigns. It is fixed when the module moves in consolidation |

None of these is independently reviewed yet. None changes a completed result: each repair changes behaviour only on paths that previously raised or accepted invalid input, as the bitwise checks show.

### Follow-up, 1 Oct 2026 (evening): pre-freeze defect fixes and Astra's repair review (append-only)

Astra's review of the repairs above: `research/astra_repair_review_20261001/REVIEW.md`.
- **Closed at the tested boundary:** SOL-03, SOL-04, SOL-07, AF-01 and AF-03. AF-02 is supported on the adopted path,
  with B12 open.
- **Left partial:** SOL-02, SOL-05, SOL-06 and SOL-08, with four reproduced gaps, AR-01 to AR-04. Each is now repaired
  as its own defect commit, below.
- The two scheduled pre-freeze defects (`CONTRACTS_AND_ORACLE.md` §6 step 1) are also done.

| # | Status | Evidence |
|---|---|---|
| OBS-01 | implemented, tested | `customkf/dynamic_observation.py` uses the row's GPST origin day for the troposphere (the dated module's exact expression). Legacy undated stage-5 rows keep the former expression and are refused away from the stage-5 origin (`96e4fb4`). Real data, `docs/consolidation/evidence/obs01_parity.json`: Aug 2 links, Jacobians and D0 partials bitwise equal to the former module (960 entries); Aug 3 dated rows bitwise equal to the dated module; the former module differed there by ≤ 13 µm (intended). `tests/test_troposphere_day.py` 7/7 |
| Empty epoch (Q7) | implemented, tested | `LongPilot.initial_state` omits seeds for (epoch, station) pairs without rows, and `state_record` refuses non-finite values (`5dd7fbe`). 22 of 43 saved campaign states carried such NaN seeds, among them the adopted Aug 3/4/5 and Jul 23 runs; none was used by any row. The production state step re-run on four campaigns (`evidence/empty_epoch_parity.json`) omits exactly those keys and keeps every other value bitwise; Jun 20 regenerates byte-identical. No fitted number changes |
| AR-01 (SOL-05) | implemented, tested | `accepted_point` requires the caller's force-model identity (keyword-only; `None` = bare roadmap model). It also requires non-empty fixture/config/state identities, a finite alpha and a finite combined point. `iteration.point` takes the identity from the installed model (`7152ccc`). `tests/test_accepted_point.py` 12/12 |
| AR-02 (SOL-06) | implemented, tested | `run_fit_elev.worker_rejection` requires each worker kind's complete output set (arrays present and hash-equal, permitted status, campaign fixture/config/state) at first acceptance and on reuse. A rejected trial remains an inspectable completed worker (`d586af4`). Every ok worker of the real Jun 20 campaign is accepted |
| AR-03 (SOL-08) | implemented, tested | Checkpoint restore validates recovery indices (integral, strictly increasing per block), counts and `local_total` (`bbb57c5`). `tests/test_streaming_contract.py` 6/6 |
| AR-04 (SOL-02) | implemented, tested | A later `--legacy-resume` must match the values earlier continuations assumed, and the protocol recovered from the record's pins (`c7a264d`). It is refused before any mutation. `tests/test_run_fit_elev_lease.py` 19/19 |

The new AR tests fail or error against the pre-repair code. None of these repairs changes a completed result. **None is
independently reviewed yet.**

### Follow-up, 1 Oct 2026 (late evening): repaired-baseline candidate and first independent-oracle run (append-only)

| # | Status | Evidence |
|---|---|---|
| Repaired baseline (A03 step 2) | **candidate**, tag `repaired-baseline-candidate-20261001` | `docs/consolidation/REPAIRED_BASELINE.md`: every intended difference from the historical pinned code. Regression at the tag: 340 discovered tests (338 direct + 2 guard-only, passing under the guard) and 7/7 real-guard scenarios. **Not independently accepted** |
| Independent oracle (A03 step 3, SCI-10) | first acceptance run passed | `validation/oracle/` (O1 extracted review metrics, O2 separately written frame/EOP/ORTHO_EOP). O3a: the IERS and SOFA reference cases pass. O2 matches the production frames within 8.7e-12 (0.23 mm at GPS radius). O4 negative controls all caught. The untouched-date scores reproduce within 6.6 µm, giving 5/5 and a mean URE ratio of 0.766352. Run `runs/20261001T203046Z-8c3e1b50`, `validation/oracle/oracle_check_20261001.json`. O3b and the Aug-arm coverage remain (BACKLOG B15) |
| C01 / M11 (oracle open) | the oracle part is now addressed for the untouched-date scores | as above; the export path is still to be covered |

The untouched-date claim (repaired analysis) is now **independently recomputed with no shared project code**,
sharing only ERFA. The as-registered result remains not established.

### Follow-up, 2 Oct 2026: Astra's evening review (append-only)

`research/astra_evening_review_20261001/REVIEW.md`: AR-01 and AR-04 accepted; OBS-01 and empty-epoch accepted at
their real-data scope; the oracle rerun passes.

| # | Status | Evidence |
|---|---|---|
| E-01 (AR-02 follow-up) | implemented, tested | `Opus_Fork/artifacts.py`: bounded-memory NPZ header, layout and finiteness validation, plus strict state JSON, in `worker_rejection` (`b2881cb`). Tests 20/20, including the real Jun 20 campaign |
| E-02 (AR-03 follow-up) | implemented, tested | Adjacent-element order check; unsigned arrays no longer wrap (`92f8b68`). Tests 7/7 |
| E-03 | documented | Erratum appended to `Opus_Fork/experiments/atmosphere/RESULTS.md`: the per-component σ ranges, and the replay-precision qualification |
| Oracle scope | documented | `docs/consolidation/REPAIRED_BASELINE.md` §6 |
| Gradient experiment (Aug 3) | result | `Opus_Fork/experiments/gradients/RESULTS.md`: GRAD operational −4.16% URE and GPT3 −1.50% against the adopted default; the linear prediction reproduced (C3 9.4e-5). Candidates on a studied day; nothing adopted |

None of E-01 to E-03 has been reviewed by Astra yet.

### Follow-up, 2 Oct 2026 (afternoon): Astra's check-in review (append-only)

`research/astra_checkin_review_20261002/REVIEW.md`:
- E-02 and E-03 accepted;
- the gradient result reproduced: the Stage 1 replay is byte-identical, an independent GPT3 port agrees within
  6.2e-15 mm, and 1,615 provenance files audited.

| # | Status | Evidence |
|---|---|---|
| C01 (E-01 partial) | implemented, tested | `Opus_Fork/artifacts.py`: every payload streamed (byte count, CRC, no trailing bytes), scalars shape-checked before reading, checkpoint layout identical to `Accumulator.restore`, recovery indices checked while streaming (`b4a7a39`). `tests/test_artifacts.py` 6/6 and the real Jun 20 campaign |
| C02 | implemented, tested | `elev.install` assigns the gradient hook from the current source every time (`08386fc`). `tests/test_gradient_hook.py` 6/6 |
| C03 | documented | Erratum in `experiments/gradients/RESULTS.md`: UTC timestamps, full-arc input support (`2026216` needed, ~40 h after arc end), retrospective label, fit-input versus model-selection wording. `VALIDATION_PROTOCOL.md` amendment A1, before any validation fit |

### Follow-up, 3 Oct 2026: gradient validation, the other-Python narrowing and two defect fixes (append-only)

| # | Status | Evidence |
|---|---|---|
| Gradient validation (option A) | result | `Opus_Fork/experiments/gradients/VALIDATION_RESULTS.md` (`b601cdd`). GRAD operational: **validated on these dates** (Jun 6, 20, 23, Jul 6, 23; 5/5 better, mean −1.90% URE, −2.39% 3D, radial never worse, worst satellite +1.98 cm). GPT3: **inconclusive** (5/5 better, mean −0.61%, below the 1% bar). lin0 controls bitwise; independent oracle within 6.7 µm. The GRAD input is retrospective (last needed file observed 40.1 h after the arc end). Nothing adopted; adoption is the user's decision |
| Other-Python check | behaviour change (user decision, 3 Oct) | `customkf/runtime/processes.py`: the fork guard and `run_fit_elev` count only this project's guard and campaign-controller Python (`991d419`). `tests/test_campaign_processes.py` |
| Folder-move race | implemented, tested | `run_fit_elev.move_folder`: rename only, retried while Windows holds a handle; no copy-and-delete fallback (`c633388`). Cause: V-gpt3-0723 lin2-traj-1, WinError 32 after a CPU-limit stop. `tests/test_move_folder.py` 4/4. The guard returning before its job's processes exit is recorded as BACKLOG B16, not changed |
| Validator buffer bound | implemented, tested | `Opus_Fork/artifacts.py`: items above 4 KiB refused at the header, so the streaming buffer is bounded (`5aff3b2`; Astra's 2 Oct peek). No recorded member exceeds 64 bytes. `tests/test_artifacts.py` 8/8 |

Regression at `991d419`: 372 discovered tests, 370 direct plus the 2 guard-only modules (19/19); real-guard scenarios
7/7. None of these has been reviewed by Astra yet.

### Follow-up, 3 Oct 2026 (later): optional gradient model adopted (append-only)

User: "go with option 1, adopt it as optional". `docs/consolidation/configurations.md` §1a.

| # | Status | Evidence |
|---|---|---|
| Arc inputs for grad_op | implemented, tested | Only the arc's GRAD files are read and bound; a missing one is refused (`d281a93`). Before, every file present was bound, so acquiring another date would have stopped a running gradient campaign. Parity: the five validation arcs' days equal A1's record, and values are bitwise identical at every station every 5 min |
| SP3 comment width | implemented, tested | Over-long header comments are refused, not cut. The latency label had been written as "...RAPID PRODU" (`9e8fcdb`). No exported product exists in the store |
| Gradient product labels | behaviour change (user adoption) | The exporter names the gradient model and the final latency class, and writes `OPUS0OPSFIN_` by default for GRAD products; unknown sources are refused. Export check `runs/20261004T020128Z-23360571`: 5/5 model-aware roundtrips within 0.5 mm, negative controls 63–90 mm off, labels present |
| Acquisition | tool | `experiments/gradients/acquire_day.sh`: the three files per day, never re-downloaded, appended to the as-of ledger |
