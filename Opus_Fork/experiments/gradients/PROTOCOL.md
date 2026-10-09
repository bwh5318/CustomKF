# A-priori tropospheric gradients on Aug 3 — protocol (written before any gradient fit or prediction exists)

Opus, 1 October 2026 UTC. Follows `experiments/atmosphere/RESULTS.md` (decision rule for a material term) and Astra's
`research/astra_evening_review_20261001/GRADIENT_ADVICE.md`. **The user authorized downloading the data and running the
tests on 1 Oct 2026.** When this was written:
- the inputs had been downloaded, and a descriptive comparison of the two fields had been printed (listed in the
  ledger below);
- no gradient had been applied to any observation, no linear prediction had been computed, and no fit had started.

## Question

Does adding an **external, fixed** a-priori gradient field to the observation model improve the Aug 3 orbit? Does the
linear transfer predict the nonlinear refit response to that field? Gradients are not estimated here; estimating them
would be a separate experiment with its own protocol (Astra's advice; Sol SCI-02).

## Input ledger (`acquisition_record.tsv`, `acquire.sh`)

| Source | Files | Character, as documented by the provider | Latency label used here |
|---|---|---|---|
| `grad_op`, TU Wien GRAD operational, site-wise | `2026213…220.grad_g` (Aug 1–8) and the untouched-date neighbourhoods, from `trop_products/GNSS/GRAD/GRAD_OP/daily/2026/` | Ray traced through a numerical weather model. Station, MJD, Gn_h, Ge_h, Gn_w, Ge_w in mm, at 00/06/12/18 UT. "made available at about 18 UT for the previous day". Server Last-Modified for 2026215 (Aug 3): 2026-08-04 18:04 | **next-day.** The issue time is not independently verified; the archive timestamp is recorded as found |
| `gpt3`, GPT3 1°×1° grid | `gpt3_1.grd` (with the official `gpt3_1.f90`/`.m`) | Empirical seasonal gradients (mean, annual, semiannual) | **none** (static model) |
| GRAD forecast (FC) | not acquired | The 2026 directory returned **401 Unauthorized** (credentials needed) | n/a |
| IGS troposphere products | not acquired | Reference only by project decision; never a fit input | n/a |

All 25 network stations are present in `grad_op`, with 4 epochs per day. Conventions (`Opus_Fork/gradients.py`):
- the Chen–Herring form with separate hydrostatic (C = 0.0031) and wet (C = 0.0007) mappings (Landskron and Böhm
  2018, eqs. 2–4);
- azimuth from north, clockwise; mm → m;
- `grad_op` is linear in time, at MJD(UTC) = GPST − 18 s; a gap over 6 h or a missing station is refused;
- `gpt3` follows `gpt3_1.f90`: bilinear in polar distance and longitude, seasonal terms on the calendar day of year,
  grid values in 1e-5 m.

Descriptive comparison seen before this protocol (not a result): on Aug 3, the RMS over stations of the `grad_op`
daily means was
- 0.12 / 0.12 mm (hydrostatic N/E) and 0.22 / 0.23 mm (wet N/E);
- within-day wet standard deviation 0.15 / 0.12 mm;
- correlation with `gpt3` over stations 0.74 / 0.76 / 0.09 / 0.71.

## Stage 1: linear predictions (diagnostic)

Re-accumulate the saved SD-3 Aug 3 operator with new right-hand sides, exactly as in `experiments/atmosphere/`. The
reproduction checks are its R1–R3 as amended there: sign-aligned R1 ≤ 1e-10; R2 `nopcv` ≤ 1e-9; `y` ≤ 1e-9 on the
`nopcv` scale with its reduction within 1e-6; R3 recorded passes.

**Columns (δy = −δm):**
- `y` and `nopcv` (reproduction);
- `grad_op`, `grad_op_h` (hydrostatic part only) and `grad_op_w` (wet part only), each evaluated at every row's
  epoch, elevation and azimuth;
- `gpt3`.

**Arms:** SD-3 weights (primary, calibrated) and elw13 weights (secondary, descriptive), as in the atmosphere
transfer.

**Per column:**
- absorption;
- orbit RMS 3D, R/A/C, and the orbit-only URE of the change;
- per-epoch scale (mean, 12 h/24 h);
- **the predicted score.** SD-3 states plus δr are scored against IGS final by the independent oracle
  (`validation/oracle`, O1+O2, sub-daily frame), on the satellite-epochs common with SD-3's own oracle score. The
  result is ΔURE and Δ3D relative to SD-3.

## Stage 2: matched nonlinear Aug 3 fits (authorized by the user)

Same fixture (`Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03`), config (`unit-ecom5`), chunking, trajectory
groups and `fork8` policy as the comparators. The only change is the gradient field in the observation model
(`--gradients`).

| Arm | Variant | Gradients | Comparator (existing campaign) |
|---|---|---|---|
| **G-op-sd3** | `erp+thrust+iiia2600+sdeop+none`: SD-3's model and weights (no elevation change), run through `run_fit_elev` | `grad_op` | SD-3 `20260925T215927Z-fit-SD-3-25st` (the calibration contrast for Stage 1) |
| **G-op-e13** | `erp+thrust+iiia2600+sdeop+elw13` | `grad_op` | E-elw13-3 `20260927T163208Z-fit-E-elw13-3` (the adopted default) |
| **G-gpt3-e13** | `erp+thrust+iiia2600+sdeop+elw13` | `gpt3` | E-elw13-3 |

**Comparator equivalence.** The comparators were fitted before the 30 Sep–1 Oct repairs. Those repairs are bitwise
neutral on every path these fits used:
- SOL-01/AF-02 change only links the former code refused; these campaigns converged, so they had none;
- the empty-epoch change alters unused NaN seeds only, and the used values are bitwise
  (`docs/consolidation/evidence/empty_epoch_parity.json` covers E-elw13-3);
- OBS-01 is off the adopted path.

**Control:** each new arm's lin0 trajectory arrays must be bitwise equal to its comparator's. Gradients do not enter
the dynamics. If this control fails, the arm is reported, but the comparison is labelled unmatched.

**Calibration of Stage 1 (G-op-sd3 versus SD-3 against the `grad_op` column, primary arm).** Actual = G-op-sd3 −
SD-3 final states (inertial, 5-min grid, 31 satellites):
- C3: RMS3D(actual − predicted) ≤ 0.30 · RMS3D(actual);
- C2': Pearson r between the actual and predicted along-track component over all samples ≥ 0.80.

If either fails, the Stage 1 predictions for other fields are not used quantitatively.

**Scoring.** Raw, unaligned, against IGS final, with both `Opus_Fork/evaluate.py` and the oracle:
- URE, 3D, R/A/C;
- per-satellite 3D changes against the comparator, with NGA PE in the same table on common samples.

## Reading (fixed now)

Aug 3 is a **previously studied day**. Results are new-arm contrasts, not validation.

| Outcome for G-op-e13 or G-gpt3-e13 against E-elw13-3 | Reading and next step |
|---|---|
| URE better by ≥ 1.0%, and no satellite 3D worse by > 0.1 m | **Candidate.** Next: a separately frozen validation, both as new-arm contrasts on Aug 2/4/5/7 and on dates not yet used. Nothing is adopted from Aug 3 |
| −1.0% < change < +1.0% | **No material effect** at this configuration; recorded |
| URE worse by ≥ 1.0% | **Rejected** for this configuration; recorded |

The `gpt3` arm alone qualifies as zero-latency. The `grad_op` arm is labelled next-day latency in any claim.

## Implementation (behaviour changes, each its own commit, default off)

1. `claude.tools.dated_observation.GRADIENT`: an optional hook (default `None`). When set, it adds its slant delay to
   the hydrostatic term of `modeled_link`, so it enters code, phase and the measurement Jacobian's correction
   stencil. Parity: `None` is bitwise the current model.
2. `Opus_Fork/elev.py`: an `OPUSFORK_GRADIENTS` source (`none` | `grad_op` | `gpt3`), installed by `elev.install()`.
   `elev.binding()` gains a `gradients` entry (source, convention, module and input hashes) only when it is not
   `none`.
3. `Opus_Fork/run_fit_elev.py`:
   - `--gradients` (default `none`), recorded in the campaign spec;
   - the elevation change `none` (variant `<base>+none`: rows unchanged after the sigma-rule check), so that SD-3's
     model runs through this controller;
   - `Opus_Fork/gradients.py` pinned.

Unit tests: the hook's sign, units, mapping and time interpolation against hand values, refusal paths, `None`
parity, and the binding.

## Resources

- Stage 1: root guard `usage75 --threads 1`.
- Stage 2: `fork8` full fits (user-authorized policy) as a resumable chain (`resume_chain.ps1`), one guarded job at
  a time.
- No Python is started while the chain is live.
