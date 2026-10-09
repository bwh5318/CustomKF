# Atmosphere transfer: pressure, mapping and gradients (Sol SCI-01/02) — protocol (written before any output exists)

Opus, 1 October 2026 UTC. Sol review `SOL_REVIEW_FOR_ASTRA_OPUS_55.md` SCI-01 and SCI-02 (first science
recommendation, also Astra's); BACKLOG B11 and B4. **No fit, no new Jacobians, no reference product read.** Bounded,
linearized, diagnostic only. When this file was written no code of this experiment existed and no number from it had
been computed.

## Question

The troposphere model (`customkf/station_models.py:troposphere`) has three approximations that a fitted wet delay
cannot fully absorb:
- hydrostatic delay from a fixed height law for pressure, independent of date and weather;
- NMF mapping functions;
- no horizontal gradients.

Through the actual weighted station POD, how much of each perturbation is absorbed by clocks, wet nodes, ambiguities
and orbits, how much reaches the orbits, how much would stay in residuals, and could station gradients be estimated?
Separately: can the semidiurnal atmospheric pressure tide S2, which our standard-atmosphere pressure lacks but
weather-model hydrostatic delays contain, produce the unexplained 12 h scale breathing (B4)?

## Operator (reused, already validated)

The joint weighted transfer of `experiments/transfer/` (`PROTOCOL.md` there; result `results/TRANSFER_CALCULATION.md`)
at its pinned linearization point: SD-3, Aug 3, 25 stations, final `lin2-solve`. That operator passed K1–K3 and its
calibration against the matched nonlinear S-nopcv contrast:
- mean scale relative error 2.4e-6;
- per-epoch correlation 0.99999999999;
- 3D residual 1.4e-5 of the change.

Its 12 chunk workers saved every epoch's whitening inputs (`blocks.npz`: sparse retained Jacobian, local Jacobian, σ)
and per-row geometry (`rows.npz`) "so other targets can be re-accumulated later without recomputing Jacobians". This
experiment does exactly that, with new right-hand sides. Chunk runs are those recorded in
`experiments/transfer/driver_status.json`; the last is `runs/20260928T222827Z-52e813a0` (chunk 132–144). They are
verified by `chunk_chain` (K1) and by the saved hashes.

**Re-accumulation checks (prerequisites; candidates are analysed only if all pass):**
- R1: the re-accumulated R (SD-3 weights) equals the saved last-chunk `acc.npz` R, max |ΔR| ≤ 1e-10·max|R|.
- R2: the re-solved δx for the `y` and `nopcv` columns (copied from the saved `rows.npz` targets) equals the saved
  `transfer_result` estimate (`runs/20260929T014726Z-8e470a08/transfer.npz`), max |Δ| ≤ 1e-9·max|δx| per column.
- R3: the saved transfer result (`experiments/transfer/transfer_result.json`, `3ed12385…2e27e`) records K2, K3 and the
  calibration as passed, with that `transfer.npz` hash (`b32c7278…3b8c`); `k1_validation.json` records K1 as passed
  for the same last chunk; and `chunk_chain` re-checks K1 now.

## Perturbation columns (model changes δm; δy = −δm on code and phase rows alike)

Per row, from the saved geometry: station, elevation e, azimuth az, UT hour. Station latitude φ, longitude λ and
height h come from the fixture's `fixed_xyz` through `customkf.station_models.geodetic`. Day of year is 215 + UT/24.
`hyd(e)` and `mw(e)` are the two outputs of the production `troposphere(xyz, e, doy)`. `P(h)` is the model's own
pressure, 1013.25·(1 − 2.2557e-5·h)^5.2568 hPa.

| Column | δm (metres) |
|---|---|
| `y`, `nopcv` | copied from the saved targets (reproduction, R2) |
| `p_net_10hPa` | every station: hyd(e)·10/P(h) |
| `s2_cos_1hPa`, `s2_sin_1hPa` | hyd(e)·δP/P(h), δP = cos³φ·{cos, sin}(2·2π·LST/24), LST = UT + λ/15 h |
| `s1_cos_1hPa`, `s1_sin_1hPa` | as S2 with 2π·LST/24 |
| `gN_net_1mm`, `gE_net_1mm` | every station: 1e-3·mg(e)·{cos az, sin az}, mg = 1/(sin e·tan e + 0.0031) (IERS 2010 eq. 9.12, 9.14) |
| `map_net_1mm10` | every station: 1e-3·(mh(e) − 1)/(mh(10°) − 1), mh = hyd/ZHD at that station and time (a relative error of the hydrostatic mapping's elevation dependence, 1 mm at 10°) |
| `p_<STA>_10hPa` (25) | that station only: hyd(e)·10/P(h) |
| `gN_<STA>_1mm`, `gE_<STA>_1mm` (50) | that station only, as the network gradient columns |

Sign reading: a column answers "what a refit with this model change would do". The current model's error from a true
atmosphere that differs by that change is the **negative** of the response.

## Arms

- **Primary (calibrated): SD-3 weights**, the saved σ. All reading categories apply here only.
- **Secondary (descriptive, uncalibrated): elw13 weights at the same point.** Phase σ multiplied by sin(e)^−0.3, with
  sin(e) = 0.009/σ_phase, exactly the `Opus_Fork/elev.py` elw13 rule; code σ unchanged. Constraint rows unchanged. This
  shows whether the adopted default's down-weighting of low elevations changes the conclusions. It is not the E-elw13-3
  linearization point and has no nonlinear calibration.

## Measures (per column and arm)

- **Absorption** of the whitened δy norm²: by the per-epoch clocks (local elimination); by the retained parameters
  (orbits, ECOM, wet nodes, ambiguities, with the constraint rows); left in the residual.
- **Orbit response** on the solution's 5-min grid (31 satellites): RMS 3D; R/A/C RMS; orbit-only URE
  sqrt(mean(0.98²R² + (A² + C²)/49)); per-satellite RMS 3D. Per-epoch Helmert scale (15-min epochs, hourly means):
  mean, 12 h and 24 h amplitudes and peak UT. Wet-node and ambiguity response RMS.
- **Per-station columns:** orbit URE response per station. Identifiability if the parameter were estimated: residual
  fraction and formal σ = 1/√(residual norm² per unit). This is at unit weight and also scaled by the a-posteriori
  variance factor of the fit (0.2371, the transfer result's). Correlations from the residual Gram matrix: gN–gE, p–gN
  and p–gE at each station, and the largest |r| among all station columns.
- **Illustrative magnitudes** (assumptions stated here, applied linearly):
  - independent station pressure errors of σ = 10 hPa;
  - independent station gradients of σ = 0.5 mm per component.

  The expected URE of a sum of independent zero-mean terms is σ·√(Σ URE_s²), which is exact in expectation.
  - **S2 climatology:** 1.16·cos³φ hPa with maxima at 10 h LST. This is an approximate literature climatology
    (Haurwitz–Cowley type), used only as an illustration.
  - Mapping: 1 mm at 10°.

## Reading categories (fixed now; primary arm only)

Reference levels for SD-3 on Aug 3: URE 3.165 cm (`results/ELEVATION_RESULTS.md`); 12 h scale breathing 0.311 ppb at
4.5 h UT (`results/TRANSFER_CALCULATION.md`).

| Measure | Category |
|---|---|
| Illustrative URE response ratio r = URE_resp/3.165 cm. If the error contains this component independently, removing it would gain 1 − √(1 − r²) | **material** r ≥ 0.20 (≥ 2%); **minor** 0.10 ≤ r < 0.20; **negligible** r < 0.10 |
| S2 climatology, implied "ours − reference" 12 h scale (−response), assuming the reference's hydrostatic delays contain S2 | **capable of the magnitude** ≥ 50% of 0.311 ppb and peak within ±1.5 h of 4.5 h (mod 12); **minor contributor** 10–50%, or ≥ 50% at the wrong phase; **negligible** < 10% |
| Station gradient identifiability (constant per station and day), a-posteriori-scaled formal σ per component | **identifiable** ≤ 0.1 mm; **weak** 0.1–0.3 mm; **not identifiable** > 0.3 mm |

## Decision rules (fixed now)

- If any illustrative term is **material**, or S2 is **capable**, the next step is a matched nonlinear check of that
  term on Aug 3. That is a refit with the changed model, which needs the user's go-ahead. Before it, an as-of ledger
  of real pressure or weather-model inputs (availability and latency) is made. No estimator change is adopted from
  this diagnostic alone.
- If gradients are **identifiable** and material, a gradient-estimation trial needs its own frozen protocol:
  interval, priors and untouched validation dates (Sol SCI-02).
- If everything is minor or negligible, the result is recorded, and the next candidates are SCI-03 (attitude) and the
  force-side kernel (B5).

## Level of inference

This is a linear response at one converged point on one day (Aug 3), with one network and one weighting (plus the
descriptive elw13 arm). It predicts first-order refit responses to model changes. It measures neither truth nor the
real atmosphere: the illustrative magnitudes are assumptions, not measurements. A negligible term is disfavoured
**for this configuration**. A material or capable term is a hypothesis for a controlled refit, not an
identification. Comparisons with IGS final are agreement with a reference.

## Resources

One worker under the root guard (`--profile usage75`, timeout 1800 s), serial, no other numerical job at the same
time. Inputs are read-only; outputs go only to the guard's run folder, and a copy of the result goes to this
folder.

## Amendment A1 (appended 1 Oct 2026, 20:22 UTC; no output of this experiment exists)

The first run (`runs/20261001T195023Z-1f1604f8`) reached the 1,800 s guard timeout:
- status `timeout`, 1,678 CPU s;
- it printed nothing, because the worker reports only after both arms are accumulated;
- it wrote no result file.

Nothing was analysed or seen.

**Likely cause.** One unconstrained QR update of this system takes 0.28 s on a single thread. The original transfer
chunks, by comparison, spent about 6.5 s per epoch under the same profile. Two math-library threads under the job's
CPU-rate cap are the likely cause.

**Changes:**
- The rerun uses `--threads 1`, which is below the profile's 2. Every other limit is unchanged, as is the 1,800 s
  timeout.
- The worker prints progress (load, targets, every 24 epochs per arm).

**Unchanged:** columns, checks R1–R3, measures, illustrative magnitudes, categories and decision rules.

Thread count can change the last bits of BLAS results. R1 (1e-10) and R2 (1e-9) are relative tolerances that allow
for this.

## Amendment A2 (appended 1 Oct 2026, 20:26 UTC; no candidate has been analysed)

The A1 rerun (`runs/20261001T202110Z-8f65406e`) completed. The reproduction gate failed, so as the protocol
requires **no candidate was analysed**; the worker computes nothing past the gate. Both failures are check-design
defects.

- **R1:** raw relative difference 1.447. QR factors are unique only up to the sign of each row (Householder), and
  the earlier transfer protocol hit exactly this in its K2 (amendment A1 there: raw 1.45, |R| matched to 2.3e-15).
  - *Amended:* R1 compares R after aligning each row's sign to the saved R, still at 1e-10 relative.
  - The raw difference, the number of flipped rows and the |R| difference are recorded.
- **R2:** the `nopcv` column reproduced to 4.3e-14 relative, which passes. The `y` column gave 6.2e-9 relative. That
  column is the fit's own step at a **converged** point, a vector near zero, so a relative criterion on its maximum
  compares rounding noise.
  - *Amended:* `nopcv` keeps its 1e-9 relative rule.
  - `y` must reproduce the saved reduction (the transfer's K3 quantity) within 1e-6 relative, **and** satisfy
    max |Δδx_y| ≤ 1e-9 · max |δx_nopcv|. That is the same 1e-9, on the scale of a real response.
  - The raw relative values are recorded.

Everything else is unchanged.
