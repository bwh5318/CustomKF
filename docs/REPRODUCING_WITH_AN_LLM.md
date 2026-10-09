# Reproducing customKF: the complete specification

**Appendix to the project report.** Written 5 October 2026 for anyone, a person or an LLM coding agent, who wants to
rebuild this project from nothing, or to extend it without repeating its mistakes.
- Every model choice, constant and rule below is the one the current code uses, with the file that implements it.
- Every expected number comes from a recorded evaluation file.
- Where something was tried and failed, it says so.

**How to use this file with an LLM.** Give the agent this file, [SETUP.md](../SETUP.md) and
[DATA_SOURCES.md](DATA_SOURCES.md). Ask it to implement in the order of section 3, and after each stage to check
the numbers in section 13 before moving on. The rules in section 14 are what kept this project honest; ask the
agent to follow them too.

---

## 1. Objective and success criterion

- **Product.** Precise orbits for the eligible healthy GPS satellites with adequate navigation support over a 24 h
  arc, estimated only from:
  - station observations (dual-frequency code and carrier phase, 30 s RINEX 3) from about 25 public IGS stations;
  - the broadcast navigation message;
  - published models and calibrations.
- **No precise orbit or clock product enters the fit.** The code enforces this:
  `customkf/stage5_pilot.py:forbid_precise_product_reads`.
- **Bar.** Be closer to the IGS final orbit than the NGA precise ephemeris (NGA PE) is, on the same
  satellite-epochs.
- **Reference.** IGS final is a reference, not truth.
- **Latency goal.** Inputs should be plausibly available at rapid latency, roughly within a day. No rapid-deadline
  replay has been done yet; every result so far is retrospective.

## 2. Metrics (exact definitions)

Scores are computed against IGS final at its native 15-minute epochs, from 00:00:00 to 23:45:00 GPST: arc offsets
t = 10 s to 85,510 s from the 23:59:50 origin (corrected 8 Oct 2026; documentation review F2).
The satellite-epoch keys are those common to every arm being compared **and** to NGA PE. Scores are raw: no
Helmert alignment, no mean removal, and no satellite exclusion by score.

- **Frame.** Positions are compared in ECEF. Each solution is rotated with the Earth-orientation model it was
  fitted with: the daily IERS EOP, plus IERS 2010 sub-daily ocean-tide EOP when the fit used it.
- **RAC axes**, from the reference orbit:
  - radial: the unit vector of r;
  - cross-track: along r × v;
  - along-track: completes the right-handed set.
- **Reference velocity:** from a 9-point polynomial through the reference positions in the inertial frame.
- **3D RMS** = sqrt(mean |Δr|²).
- **Orbit-only URE** = sqrt(mean(0.98² R² + (A² + C²)/49)), with R, A, C the radial, along-track and cross-track
  errors. Clocks are not part of it.
- **Ratio to NGA** = our URE / NGA's URE on the same keys. Below 1 is better than NGA.
- **Epoch share:** the fraction of 15-min epochs at which our constellation URE is below NGA's. The constellation URE
  is the RMS of the instantaneous URE over the satellites at that epoch.
- **Satellite-epoch share:** the fraction of individual satellite-epochs at which our instantaneous URE is below
  NGA's.

Implementations: `Opus_Fork/evaluate.py` (production) and `validation/oracle/` (independent). On the scored metrics
they agree within 0.1 mm (largest recorded difference 13.6 micrometres, 4 Oct 2026). The oracle's default CIP method
(ERFA `xy06`, series) differs from production's (`xys06a`, angles) by up to 1.5 microarcseconds, about 0.2 mm at GPS
radius; strict reproduction uses the oracle's opt-in angles path, `Frame(..., cip="angles")`.

## 3. Architecture and build order

```
inputs (OBS, NAV, EOP, ephemeris, gravity, ANTEX, coordinates, loading, metadata)
  -> preparation: signal choice, ionosphere-free combinations, slip screening, solve epochs, station models,
     navigation merge and eligibility, broadcast seeds; frozen into fixture.json
  -> estimator: integrate trajectories + variational equations; model observations; streaming
     square-root (QR) accumulation per chunk of epochs; eliminate epoch clocks; solve; line search;
     relinearize until stationary
  -> evaluation against IGS final with NGA PE beside it; SP3 export with a QA gate
```

Build and verify in this order. Each stage has its own check.
1. **Time and frames.** Check against ERFA test values and the IERS ORTHO_EOP test case.
2. **Readers:** RINEX 3 observations (after CRX2RNX), RINEX navigation, SP3, ANTEX, SINEX, BLQ.
3. **Integrator with variational equations.**
   - Check against two-body analytic orbits: about 0.5 µm over 24 h.
   - Check against finite differences of independent integrations: about 10 µm.
4. **Reference fit to IGS positions.** This checks only that the force model can represent the orbit (section 6):
   ECOM5 reaches a few cm. **Never** use the result as a fit input.
5. **PPP of a few stations** with precise orbits held fixed, as a check of the observation model. Coordinates should
   agree with IGS20 to a few mm.
6. **Network orbit estimation** from broadcast seeds. Then add, one change at a time, the items of section 12, each
   with its own matched comparison.

## 4. Conventions

- **Time scales:** GPST = TAI − 19 s; TT = TAI + 32.184 s; UTC − GPST = −18 s (2026). UT1 comes from IERS finals.
  TDB is used for the planetary ephemeris.
- **Celestial–terrestrial transformation:** IAU 2006/2000A through ERFA. Daily x, y and UT1 come from
  `finals2000A.all`, interpolated.
- **Sub-daily EOP (default):** IERS 2010 ORTHO_EOP diurnal and semidiurnal ocean-tide terms on x, y and UT1, applied
  in **both** the dynamics and the station geometry (`Opus_Fork/subdaily_eop.py`). Libration terms are omitted.
- **Units and keys:** SI throughout. Satellites are keyed by PRN ("G01"), stations by the four-character site code.
- **Arc:**
  - origin 23:59:50 GPST on the previous day;
  - 144 solve epochs at 600 s, from t = 10 s to 85,810 s;
  - scored 00:00:00 to 23:45:00 GPST, the offsets t = 10 s to 85,510 s on IGS final's 15-minute grid. Keep solve
    offsets distinct from wall-clock times.

## 5. Preparation (`Opus_Fork/prepare.py`)

- **Signals.** Ionosphere-free code from C1W/C2W, and phase from L1C or L1W with L2W
  (`customkf/preprocess.choose_signals`). Receivers without a P(Y)-compatible pair are rejected; code-bias handling
  is not implemented.
- **Epochs.** Observations at the solve epochs (every 600 s), with elevation of at least 10°. Half-cycle-flagged
  phase is dropped.
- **Arcs and slips** (`customkf/preprocess.ArcTracker`). Tracking runs on the **native 30 s observations, before**
  the 600 s solve sampling. A new ambiguity arc starts on any of:
  - a satellite seen for the first time;
  - a native gap of more than 60 s;
  - a loss-of-lock (LLI) or half-cycle flag;
  - a receiver event or slip record (epoch flag 1 or 6);
  - a geometry-free jump over 0.08 m + 0.002 m/s × Δt;
  - a Melbourne–Wübbena jump over 5 m.

  An arc needs at least three phase rows.
  - **Known weakness:** a phase jump after a single blank epoch without an LLI flag passed every test once (SGOC,
    G07, 8 Aug).
- **Navigation:**
  - **Merging.** The previous day's broadcast file is merged with the day's (`--previous-day-nav`). The arc starts
    10 s before midnight, so the light-time offset needs a record from the previous day. Without the merge, three
    satellites are lost.
  - **Record selection.** Records are de-duplicated by (toc, week, toe, IODE), first wins, in a deterministic merge.
  - **Eligibility.** A record must be healthy, with a four-hour fit interval, hour-aligned toe = toc, and
    |t − toe| ≤ 2 h, at both the −0.2 s and the 0 s offset of each epoch (`customkf/broadcast.select_fit_record`).
  - **Per-epoch rule** (`--per-epoch-nav`). A satellite needs an eligible record at the arc start, for its seed.
    Rows at uncovered epochs elsewhere are dropped. G13 has been unhealthy throughout and is always rejected.
- **Station models.**
  - **Coordinates:** IGS20 SSC with velocities, propagated to the date. The solution interval must be valid on the
    date, and stations in the post-seismic deformation list are refused.
  - **Antenna eccentricity:** from the RINEX header.
  - **Displacement:** reduced solid-Earth tide (`customkf/station_models.solid_displacement`); pole tide with the IERS
    2010 linear mean pole; ocean loading from FES2014b BLQ, 11 constituents.
- **Broadcast seed.** The broadcast position at the arc origin is the antenna phase centre. It is converted to the
  centre of mass by subtracting the ANTEX satellite PCO in nominal attitude (three iterations). Velocity is a ±0.5 s
  central difference (`customkf/nominal_navigation.corrected_state`).
  - **Lesson:** skipping this conversion gave a 27 m start error, later 1.2 m.
- **Output:** everything is frozen into `fixture.json`, whose hash is recorded and bound to every later step.

## 6. Dynamic model (`customkf/orbit_forces.py`, `Opus_Fork/nongrav.py`)

| Term | Model |
|---|---|
| Central gravity | GM of EGM2008, analytic in inertial axes |
| Non-spherical gravity | EGM2008 to degree and order 12 (Numba kernel) |
| Solid-Earth tides (gravity) | IERS 2010 §6.2.1 step 1 (eqs. 6.6, 6.7): anelastic Love numbers k2, k3 and the k(+) degree-4 terms, from Sun and Moon, on a 120 s cubic-spline grid. **Omitted:** step-2 frequency-dependent corrections, ocean tides and pole tides in the gravity field |
| Third bodies | Sun and Moon from DE440s, direct minus indirect |
| Relativity | Schwarzschild term |
| Solar radiation pressure | **ECOM5** with D0 nominal −1e-7 m/s² (the "unit" nominal) and five estimated corrections, each scaled by 1e-7 m/s²: **D0, Y0, B0, Bc1, Bs1**. They are scaled by (1 AU / r_sun)² and the shadow fraction (conical Earth penumbra; Sun radius 696,340 km, Earth radius 6,378,136.3 m; no Moon shadow). No priors on the corrections |
| Earth radiation (ERP) | Analytic uniform Earth, absorption only. Longwave: exitance 238 W/m² ((1 − 0.3) S/4, S = 1361 W/m²). Shortwave: albedo 0.3 with the full-disc Lambert phase law. Radial direction. Area = +Z bus + solar panels × \|d̂·r̂\| |
| Antenna thrust | a = P/(m c) radially outward, with P and m from the IGS satellite metadata SINEX |
| Box-wing areas (m²) | IIR: bus 4.25, panels 13.92. IIF: 5.40, 22.25. IIIA: 5.0, 28.2 |
| Masses | IIR 1080 and IIF 1633 kg (metadata). **IIIA 2600 kg** (published effective value; metadata 2161) |
| Attitude | Nominal yaw steering (z to Earth, y = z × Sun). **No eclipse yaw manoeuvre model** |

**ECOM basis** (`customkf/orbit_forces.srp_basis`; corrected 8 Oct 2026, documentation review F1). With r̂ the unit
satellite position: **D** = unit(r_sun − r), **Y** = unit(r̂ × D), **B** = D × Y. The angle u is measured in the orbit
plane, with cos u = r̂·o and sin u = r̂·(n̂ × o), n̂ the orbit normal unit(r × v):
- **ECOM5:** o = unit(ẑ × n̂), the ascending-node direction;
- **seven-term variant:** o = the unit projection of the Sun direction on the orbit plane.

This force basis is not the antenna body frame. With the Earth-pointing body z = −r̂, the attitude row's body y axis
(z × Sun) is −Y. Do not mix the two; a freely estimated cos/sin pair can absorb a phase change, but its coefficients
are then not the same numbers.

| Acceleration term | Direction | Period |
|---|---|---|
| D0·D | D | constant |
| Y0·Y | Y | constant |
| B0·B | B | constant |
| Bc1·cos u·B | B | **once per revolution** |
| Bs1·sin u·B | B | **once per revolution** |

**Per-revolution terms, the full history:**
- **Estimated in every fit since the 24 h arcs:** the once-per-revolution Bc1 and Bs1, for every satellite in every
  arc, with no prior.
- **Earlier six-hour fits** estimated D0 only, or no force parameter.
- **ECOM-7** adds the twice-per-revolution Dc2·cos 2u·D and Ds2·sin 2u·D:
  - free ECOM-7: URE worse by 29.5% (Aug 2) and 16.9% (Aug 3); rejected;
  - with zero-mean priors of 2 nm/s² (the σ taken from an IGS-fitted census, so reference-informed): better on Aug 2–5,
    but worse by 4.5% on Aug 7, failing the hold-out rule; rejected.
- **No other empirical acceleration** (along-track or cross-track once per revolution, stochastic pulses) has been
  used.
- **The 12 h radial "swing"** that motivated ECOM-7 shrank when the sub-daily EOP was added (URE −14% across the
  studied days; amplitude lower on Aug 2–5, but higher on Aug 7, 0.47 to 1.07 cm). The sub-daily EOP was a major
  contributor on those dates, not a proven sole cause; a 12-hour pattern does not identify its source uniquely.

**Integration** (`customkf/propagation.py`):
- DOP853 (SciPy) with state, state-transition matrix and parameter sensitivities;
- maximum step 60 s, rtol 1e-12, position atol 1e-7 m, velocity atol 1e-11 m/s, scaled-partial atol 1e-13;
- Hermite interpolation of states and partials at a 15 s output spacing (`claude/tools/dated_observation.Trajectory`).

## 7. Observation model (`claude/tools/dated_observation.modeled_link`, `customkf/measurement.geometry`)

**Code:** P = ρ + δ_Shapiro − c·dt_sat + c·dt_rx + T_hydro + m_w·ZWD + ΔAPC.

**Phase:** L = P (with the same terms) + λ_IF·wind-up + ambiguity, where λ_IF·wind-up = (α λ1 + β λ2)·wind-up.

- **Geometry.**
  - **Light time:** iterated in the inertial frame. The receive time is corrected by the estimated receiver clock,
    so Earth rotation is exact.
  - **Satellite clock:** carries the relativistic −2 r·v/c² correction once.
  - **Shapiro delay:** included.
- **Antenna.** ANTEX PCO and PCV for satellite and receiver, ionosphere-free combined, in nominal attitude.
  Phase wind-up uses a continuity reference per arc.
- **Troposphere** (`customkf/station_models.troposphere`):
  - **Zenith hydrostatic delay:** Saastamoinen with standard pressure 1013.25·(1 − 2.2557e-5 h)^5.2568 hPa.
  - **Mapping:** Niell (NMF) hydrostatic and wet, including the height correction.
  - **Zenith wet delay:** estimated per station on nodes every 3 h with linear interpolation. Level priors 0.3 m on
    the first two nodes; increments between nodes constrained at 0.03 m.
- **Optional gradients** (not in the default):
  - Chen–Herring: δ [m] = 1e-3 × [m(e; 0.0031)·(Gn_h cos az + Ge_h sin az) + m(e; 0.0007)·(Gn_w cos az + Ge_w sin az)],
    with m(e; C) = 1/(sin e tan e + C), the G values in mm and azimuth from north (the 1e-3 converts to metres, as in
    `Opus_Fork/gradients.py`);
  - fields from TU Wien GRAD operational, linear in time between the 6-hourly values (`Opus_Fork/gradients.py`).

## 8. Estimation (`claude/roadmap/long_pilot.py`, `streaming.py`, `Opus_Fork/run_fit_elev.py`)

**Parameters:**
- per satellite: initial position and velocity corrections to the broadcast seed (6) and five ECOM5 corrections;
- per station: wet-delay nodes;
- per arc: float ionosphere-free ambiguities;
- per epoch: receiver and satellite clocks. These are eliminated epoch by epoch with orthogonal transformations, never
  formed explicitly in the normal equations.

**Priors:**
- orbit corrections: 1,000 m (position) and 1 m/s (velocity), effectively free;
- force corrections: none;
- wet delay: as in section 7.

**Weights:**
- code σ = 0.9 m / sin e;
- phase σ = **9 mm / sin^1.3 e** ("elw13", the default since 27 Sep). Before that it was 9 mm / sin e.

**Solve:**
- whitened rows are folded epoch by epoch into a square-root information system with Householder QR, in chunks of
  12 epochs, run as separate guarded workers;
- the trajectories are integrated in two groups of satellites per linearization;
- the chunk folds are associative, so chunks can run separately and be combined;
- **optional, for large networks** (`--eliminate-ambiguities`, `claude/roadmap/streaming.EliminatingAccumulator`):
  each ambiguity is folded out of the square-root system once its arc has ended and recovered by back-substitution
  after the solve. It is exact for a full-rank system; on Jun 20 it reproduced the standard solve to 0.01 mm. It is
  what made the 50-station fits fit their 512 MiB workspace.

**Iteration:**
1. Linearize at the current state.
2. Solve for the Gauss–Newton step.
3. Try step fractions α = 1, ½, ¼, ⅛, each reintegrated, and accept the first that lowers the cost.
4. Stop when the trajectory step is under 1 mm and both the predicted reduction and the squared direction norm are
   below max(1e-5, 1e-8 × cost) (`customkf/nonlinear_stop.py`).

Cold start from the broadcast seed, at most 6 linearizations. Typically 3–4 linearizations, about one hour of
guarded time for 25 stations.

## 9. Default configuration (the current best rapid-candidate configuration)

```
variant   erp+thrust+iiia2600+sdeop+elw13   (Opus_Fork/elev.py, sdeop.py, nongrav_variants.py)
config    claude/roadmap/configs/unit-ecom5.json   ({"nominal": "unit", "estimate": [0,1,2,3,4]})
network   25 stations: BRUX HOB2 KOUR ABMF KOUG DJIG NNOR MAS1 DAV1 FALK FAA1 GLPS YELL GUAM
          + SGOC KOKB SUTH KIT3 KIRI NKLG MDO1 EUR2 VACS PIMO CHPI
arc       24 h, 144 epochs at 600 s, 10° cutoff, previous-day + per-epoch navigation
solve     chunk-epochs 12, trajectory-groups 2, worker-timeout 900 s, max-linearizations 6
optional  OPUSFORK_GRADIENTS=grad_op: TU Wien GRAD operational gradients (final latency only)
```

## 10. Inputs and their latency

Sources and citations are in [DATA_SOURCES.md](DATA_SOURCES.md).

**Plausibly rapid** (receipt times were not recorded):
- daily 30 s observations;
- broadcast navigation (the message is real time; the merged daily file's availability was not recorded);
- published analytical models: DE440s, EGM2008, FES2014b, IERS 2010 ORTHO_EOP.

**Retrospective as used** (no version was verified to exist at a cut-off):
- `finals2000A.all`, downloaded after the dates. It holds final and rapid values, whereas a rapid product would use
  predictions; the effect of predictions has not been measured;
- IGS20 coordinates and igs20.atx: dated, cumulative products; the versions used were retrieved later;
- the satellite metadata SINEX, retrieved in September;
- GRAD operational gradients: the last needed file carried a server Last-Modified time about 40 h after the arc,
  read later. That is not an observed first availability or a verified issue time.

## 11. Evaluation and export

- `Opus_Fork/evaluate.py` resolves the references by role and date from a hash-checked store index, and always adds
  NGA PE.
- `Opus_Fork/export.py` writes SP3:
  - centre of mass, IGc20, GPS time;
  - clocks omitted (999999.999999), accuracy codes 0;
  - the EOP model and any gradient model named in the header.

  It rotates with the same EOP model the fit used. A plain-EOP export of a sub-daily solution is wrong by about 5 cm;
  this happened once and was fixed (CORRECTIONS C01). Every file is written to a temporary sibling, re-read and
  compared with the solution, and moved into place only if it passes. An existing product is never overwritten, and
  the default name carries the solution hash: `OPUS0OPS{RAP|FIN}_YYYYMMDD_<12 hex>.SP3` (8 Oct 2026, PI-09).

## 12. Improvement history (what moved the numbers)

**First phase** (6–13 Sep): 14 → 25 stations; 3 h → 6 h → 24 h arcs; against IGS final or rapid.

| Step | Result |
|---|---|
| First observation-fitted orbit, 8 stations, 3 h | 158 m 3D: weakly viewed satellites amplified small errors |
| Seed APC → COM fix | start error 27.4 m → 1.2 m; fit still 157 m |
| 12 stations | 56.4 m (G18 dominated) |
| + YELL (13) | 11.2 m |
| + GUAM (14) | **0.821 m** 3D (Aug 2, 3 h) |
| 6 h arc | 0.544 m |
| + estimated D0 (6 h) | 0.442 m on Aug 2, but **worse on Aug 3** (0.621 → 0.713 m); not adopted |
| 24 h arc + ECOM5 (14 stations, vs IGS rapid) | 0.171 m 3D, 6.1 cm URE; bench of 5 days, mean 0.156 m |
| 25 stations (greedy geometry screen) | **14.6 cm 3D, 4.6 cm URE** (Aug 2) |

**Second phase**, orbit-only URE in cm against IGS final, with NGA PE on the same keys:

| Change (matched same-day contrast) | Aug 2 | Aug 3 | Aug 4 | Aug 5 | Aug 7 |
|---|---:|---:|---:|---:|---:|
| Baseline (B; Aug 2: N0, which also restores 27 → 31 satellites) | 4.427 | 4.263 | 4.331 | 4.225 | 3.557 |
| + ERP and antenna thrust (+ IIIA 2600 kg on Aug 3–5) | 4.167 | 3.876 | 4.045 | 3.836 | 3.403 |
| + IERS 2010 sub-daily EOP | 3.401 | 3.165 | 3.364 | 3.249 | 3.409 |
| + elevation weighting elw13 (= current default) | 3.299 | 3.035 | 3.218 | 3.199 | 3.272 |
| NGA PE on the same keys | 4.427 | 4.289 | 4.359 | 4.826 | 4.195 |

- **Mean URE change of each step:**
  - ERP/thrust: −5.9% on Aug 2, −8.3% on Aug 3–5 with the IIIA mass, −4.3% on Aug 7;
  - sub-daily EOP: −13.7% over five days;
  - elw13: −3.2% over four held-out comparisons.
- **Untouched dates, default** (URE cm; ratio to NGA):
  - Jun 6: 2.911 (0.765); Jun 20: 3.395 (0.868); Jun 23: 2.964 (0.688); Jul 6: 2.914 (0.767); Jul 23: 3.127 (0.743);
  - **mean ratio 0.766**; 3D mean ratio 0.855.
- **+ GRAD operational gradients:**
  - Aug 3: −4.16%;
  - five dates: −1.15, −1.72, −2.14, −0.42, −4.07% (mean −1.90%; ratio 0.752);
  - Jun 27, a fresh date: −3.83% (2.859 → 2.750 cm; NGA 3.795).

## 13. What did not work (do not repeat without a new reason)

| Tried | Outcome |
|---|---|
| Estimated D0 on 6 h arcs | Better on Aug 2, worse in 3D on Aug 3 (G27) |
| Block-mean D0 calibrated from IGS rapid | Helped 6 h arcs, but is reference-informed; superseded by 24 h + ECOM5 |
| Hourly wet-delay nodes; uniformly stronger phase weight | +0.3% gain; worse (0.962 vs 0.821 m) |
| Empirical reweighting per station (W1/W2) | In-sample gains on the day they were tuned on; not adopted |
| Free ECOM-7 (twice-per-rev D terms) | URE +29.5% / +16.9% |
| Constrained ECOM-7 (σ 2 nm/s²) | Failed the hold-out (Aug 7 +4.5%) |
| 15° cutoff instead of 10° | Held-out mean +0.06%; rejected |
| GPT3 empirical gradients | 5/5 slightly better, but a mean of −0.61% is under the 1% bar; inconclusive |
| Zeroing satellite PCVs (diagnostic) | URE +25%: PCVs matter |

## 14. Pitfalls that cost the most time

1. **A small phase residual does not mean a good orbit.** With weak geometry, nuisance parameters and weak orbit
   directions absorb errors: 7 mm residuals came with a 158 m orbit. Network geometry, meaning which satellites are
   seen together from where, mattered more than anything else.
2. **Antenna phase centre versus centre of mass** in the broadcast seed.
3. **The arc start needs the previous day's navigation:** 10 s before midnight, with a −0.2 s light-time offset.
4. **Sub-daily EOP must be applied consistently** in the dynamics, the station geometry, the evaluator and the
   exporter. A mismatch anywhere is a 5 cm error that looks like a physical signal.
5. **A finite-difference stencil that crosses an ANTEX domain boundary** produced a bad derivative at 10.0002°
   elevation (GLPS–G10). The repair: domain-aware differences (`correction_difference`).
6. **A slip that passes every detector** (SGOC G07, 8 Aug): one blank epoch, no LLI flag, and a 60 s gap.
7. **Thread oversubscription under a CPU-rate cap.** Two BLAS threads under a 15% quota made QR more than 10× slower.
8. **Do not trust file modification times as availability times.**
9. **Windows packaged apps virtualize AppData.** Put shared coordination files under `%ProgramData%`.
10. **Selection effects.** A model chosen because it scored well on a day is not validated by that day. Use new
    dates drawn by a fixed rule, with the protocol written first.

## 15. Rules that kept the results trustworthy

- **Pin a protocol before every adoption test**, with predictions and pass/fail rules. Append amendments; never edit
  the body. Record whether any outcome existed when an amendment was written.
- **Change one thing per comparison** and compare against a matched same-day arm.
- **Separate fit inputs from model selection.** A model chosen by IGS-scored outcomes is "reference-scored
  selection" even when its inputs are independent.
- **Validate on untouched dates** drawn by a seeded stream (`Opus_Fork/experiments/untouched_dates/date_stream.json`)
  with fixed usability rules.
- **Score with an independent implementation** as well as the production evaluator.
- **Keep an append-only correction index** (this project's is the last section of `docs/RESULTS_PHASE2.md`).
- **Run everything under resource guards** in resumable chains (see SETUP.md).

## 16. Open problems

- **Along-track:** NGA PE is still better on several dates (3 of the 5 fresh dates).
- **The rapid as-of replay:** which exact input bytes existed by a cut-off.
- **Forecast gradients (GRAD_FC):** credentials needed.
- **Integer ambiguity resolution.**
- **The unexplained 12 h scale "breathing"** of 0.16–0.37 ppb against IGS. NGA PE shows a similar term.
- **Eclipse attitude**, and stations rejected for signal-pair or post-seismic reasons.
- **Station networks** (`Opus_Fork/experiments/networks/RESULTS.md`, 8 Oct 2026; final latency, exposed dates,
  descriptive). 17 selected IGS stations near NGA's public monitor sites did not stay closer to IGS final than NGA PE
  (mean URE ratio 1.22). Doubling the 25-station network to up to 50 stations lowered URE by 15.0% on 5 of 5 dates.
  A frozen untouched-date test of a 50-station default, without gradients, would be needed before adopting it.
- **Known limitations and open integrity items:** `docs/KNOWN_LIMITATIONS.md`.
