# A-priori tropospheric gradients on Aug 3: result

Opus, 2 October 2026. Protocol: `PROTOCOL.md` in this folder (`51764fe2…2ae4`), pinned before any prediction or fit.

- **Stage 1** (linear predictions, `stage1_linear_result.json`) was committed (`afe71c0`) before any Stage 2 fit
  outcome existed.
- **Stage 2:** matched fits from the chain of 1 Oct (`Opus_Fork/runs/gradients-chain.status`). G-op-sd3 had one
  automatic external-load resume.
- **Scoring:**
  - production: `Opus_Fork/results/arm_gradients_aug3.json`;
  - analysis: `stage2_analysis.json`, which covers the lin0 control, the calibration and the independent-oracle
    scores.

**Scope.** Aug 3 is a **previously studied day**. These are new-arm contrasts, not validation. IGS final is a
reference, not truth. The gradient inputs are external weather-model products (fit inputs). The choice of field is
not reference-derived.

## Controls (all pass)

| Check | Result |
|---|---|
| lin0 trajectory arrays against each comparator (gradients do not enter the dynamics) | **bitwise equal**, both groups, all three arms (49 + 46 members) |
| Stage 1 reproduction of the saved operator | R1 aligned 2.3e-15; R2 `nopcv` 4.3e-14 |
| **Calibration (G-op-sd3 − SD-3 against the `grad_op` prediction, primary arm)** | **C3 = 9.4e-5** (limit 0.30): 1.3 µm residual on a 1.42 cm RMS change. **C2' along-track r = 0.99999999** (limit 0.80). Radial and cross-track r > 0.999999998 |
| The elw13-weight predictions (descriptive arm; operator at the SD-3 point) | also reproduced: C3-type ratio 1.3e-4 (G-op-e13) and 2.1e-4 (G-gpt3-e13) |
| Independent oracle against the production evaluator on the same 2,976 samples | URE agrees within 0.8 µm and 3D within 13 µm for all five solutions (tolerance 0.1 mm) |

The linear transfer predicted these refits essentially exactly. That supports using the operator to screen
observation-model candidates at this point. It does not establish it for other dates or larger perturbations.

## Scores against IGS final (Aug 3, full day, 2,976 satellite-epochs)

| Arm | Comparator | URE (cm) | URE change | 3D (cm) | 3D change | R / A / C (cm) | Stage 1 predicted URE change |
|---|---|---:|---:|---:|---:|---|---:|
| E-elw13-3 (adopted default) | — | 3.035 | — | 9.28 | — | 2.82 / 6.30 / 6.20 | — |
| **G-op-e13** (default + GRAD operational) | E-elw13-3 | **2.909** | **−4.16%** | 9.04 | −2.66% | 2.69 / 6.17 / 6.03 | −4.16% |
| **G-gpt3-e13** (default + GPT3) | E-elw13-3 | **2.990** | **−1.50%** | 9.21 | −0.75% | 2.77 / 6.24 / 6.18 | −1.50% |
| SD-3 | — | 3.165 | — | 9.67 | — | 2.94 / 6.64 / 6.39 | — |
| G-op-sd3 (SD-3 + GRAD operational) | SD-3 | 3.014 | −4.76% | 9.35 | −3.27% | 2.79 / 6.45 / 6.17 | −4.76% |
| NGA PE | — | 4.289 | — | 10.78 | — | 4.13 / 6.29 / 7.72 | — |

- **Sub-windows (G-op-e13 / G-gpt3-e13 against E-elw13-3):**
  - early (00:00–16:00) −3.63% / −2.50% URE;
  - late (18:00–23:45) −5.04% / −0.27%.
- **Per satellite (3D against the comparator):**
  - G-op-e13: 20 of 31 better; worst +0.53 cm (G11); best −1.28 cm (G14);
  - G-gpt3-e13: 17 of 31 better; worst +0.56 cm (G11);
  - G-op-sd3: 21 of 31 better; worst +0.60 cm (G24).
- **Stage 1 attribution** (SD-3 weights): the wet part of the operational gradients gives −4.31% of the −4.76%, the
  hydrostatic part −0.59%.

## Reading (pre-registered categories)

| Arm | Rule | Category |
|---|---|---|
| G-op-e13 | URE better by ≥ 1.0% and no satellite 3D worse by > 0.1 m (−4.16%; worst +0.53 cm) | **Candidate**, next-day latency |
| G-gpt3-e13 | the same rule (−1.50%; worst +0.56 cm) | **Candidate**, zero latency |

**What this means:**
- Adding external a-priori gradients to the observation model improved the Aug 3 orbit, as the atmosphere transfer
  had indicated. The size of the change was predicted before the fits, and the fits confirmed it.
- The weather-model gradients (GRAD operational) help about three times as much as the climatological GPT3
  gradients. Most of the gain is in the wet part.
- On **Aug 3 only**, that is a 4.2% URE improvement over the adopted default. The URE ratio to NGA PE improves from
  0.708 to 0.678.
- **Nothing is adopted from Aug 3.**

**Limits:**
- One studied day.
- The GRAD operational product's ~18 UT next-day latency (taken as documented, not independently verified)
  qualifies any rapid-latency claim. GPT3 alone is latency-free.
- The forecast product, the latency-appropriate weather-model version, was not accessible (credentials).

## Next step (protocol decision rule: candidate)

A separately frozen validation, written before any of its fits:
- new-arm contrasts on Aug 2/4/5/7, where the E-elw13 comparators exist;
- dates not yet used.

Both candidates go through it, with the same scoring and categories. That validation is new full fits and needs the
user's go-ahead.

## Erratum C03 (appended 2 Oct 2026, from Astra's check-in review; the text above and the pinned protocol are unchanged)

- **Timestamps.** The server Last-Modified of `2026215.grad_g` is **2026-08-04 16:04:20 UTC**. The "18:04" written in
  the protocol ledger and this result is the directory listing's local server time.
- **Input support for the Aug 3 arc.** Interpolating the whole arc needs three files:
  - `2026214` and `2026215`;
  - **`2026216`**, for the following midnight endpoint.

  All 25 stations need all three. The last required file's observed Last-Modified is **2026-08-05 16:04:26 UTC**,
  about 40 h after the arc ends. These are observed modification times, not verified issue or first-availability
  times. The archived operational input is therefore **retrospective** until actual as-of availability is shown.
  "Next-day latency" understates it for a full arc.
- **GPT3** needs no epoch-specific gradient file once its grid is installed. That does not make the whole OBS/NAV/EOP
  pipeline zero-latency.
- **Fit inputs versus model selection.** GRAD operational is an external weather-model field and GPT3 a static
  empirical climatology; neither is derived from the IGS orbit reference, so both are independent **fit inputs**.
  **Deciding whether, and which, field to adopt is reference-scored model selection.** The sentence "the choice of
  field is not reference-derived" above should be read with that qualification. The numerical scores and the
  studied-day candidate category are unaffected.
