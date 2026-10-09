# Atmosphere transfer (Sol SCI-01/02, B4): result

Opus, 1 October 2026, 20:27 UTC. Protocol: `PROTOCOL.md` in this folder.
- Its body is pinned (`2158e9a1…badc`) and was written before any code or output.
- Amendments A1 (one thread, after a timeout with no output) and A2 (sign-aligned R1; the converged `y` step judged
  on the response scale) were each appended and pinned **before any candidate was analysed**.

Result: `atmosphere_result.json`, a copy of `runs/20261001T202428Z-770e6ec0/atmosphere.json` (`3c43d406…63cc`), with
`atmosphere.npz` (`70b20237…055a`).

**Diagnostic only.** This is a linear response at one converged point: SD-3, Aug 3, 25 stations, through the transfer
operator validated against the S-nopcv nonlinear refit. It is not a fit or an accuracy acceptance. The illustrative
magnitudes are **assumptions, not measured atmosphere**. IGS final is a reference, not truth.

## Reproduction of the saved operator (all pass)

| Check | Rule | Result |
|---|---|---|
| R1 R, sign-aligned | ≤ 1e-10 relative | 2.3e-15 (89 rows flipped; raw 1.447, as in the transfer's K2) |
| R2 `nopcv` δx | ≤ 1e-9 relative | 4.3e-14 |
| R2 `y` δx, on the `nopcv` scale | ≤ 1e-9 | 5.0e-14 (raw relative 6.2e-9) |
| R2 `y` reduction | ≤ 1e-6 relative | 7.5e-14 |
| R3 saved K1–K3 and calibration | all recorded as passed | pass; K1 re-checked |

## Absorption and orbit response (primary arm, SD-3 weights)

| Perturbation | Absorbed by clocks / retained / left in residual | Orbit RMS 3D | URE |
|---|---|---|---|
| Common pressure +10 hPa | 0.87 / 0.13 / 0.00 (wet response 22.5 mm) | 0.23 cm | 0.068 cm |
| S2 pressure tide, 1 hPa·cos³φ (cos, sin) | 0.89 / 0.11 / 0.003 | 0.12 cm | 0.033 cm |
| Mapping error, 1 mm at 10° | 0.48 / 0.52 / 0.00 | 0.002 cm | 0.0007 cm |
| North gradient, 1 mm at every station | 0.54 / 0.31 / 0.16 | 4.39 cm (along 3.76) | 1.85 cm |
| East gradient, 1 mm at every station | 0.07 / 0.72 / 0.21 | 3.75 cm (along 3.52) | 0.71 cm |
| One station's N gradient, 1 mm (median) | 0.10 / 0.42 / 0.49 | — | 0.13–0.40 cm per mm, N and E combined; largest at GLPS, DJIG, FAA1, SGOC, KIRI |

Closure (clocks + retained + residual = total) holds to ≤ 1e-15 for every column.

## Pre-registered readings (primary arm)

| Illustrative magnitude | URE response | Ratio to 3.165 cm | Category |
|---|---|---|---|
| Independent station pressure errors, σ = 10 hPa | 0.035 cm | 0.011 | **negligible** |
| Common pressure error, 10 hPa | 0.068 cm | 0.022 | **negligible** |
| Mapping error, 1 mm at 10° | 0.0007 cm | 0.0002 | **negligible** |
| S2 climatology (1.16 hPa·cos³φ, maxima 10 h LST) | 0.040 cm | 0.013 | **negligible** |
| Independent station gradients, σ = 0.5 mm per component | **0.73 cm** | **0.23** | **material** (removing it would gain about 2.7% URE) |

- **S2 and the scale breathing (B4).** The implied "ours − reference" 12 h scale is 0.0036 ppb at 5.4 h UT, which is
  1.2% of the observed 0.311 ppb: **negligible**. The S2 pressure tide is disfavoured as the cause of the breathing
  **for this configuration**.
- **Gradient identifiability** (constant per station and day, all 25 estimated jointly, a-posteriori scaled): formal
  σ is 0.13–0.25 mm per component (median 0.17), so all 25 stations are **weak**. The largest residual correlation
  among station columns is 0.41 (KIT3 pressure with KIT3 east gradient). Gradient north–east correlations are
  ≤ 0.19.
- **Secondary arm (elw13 weights; descriptive only, uncalibrated).** It gives the same pattern:
  - pressure, mapping and S2 negligible;
  - gradients 0.64 cm URE (ratio 0.20, at the material boundary);
  - identifiability 21 weak, 4 not identifiable (σ 0.18–0.35 mm).

  Down-weighting low elevations reduces both the gradient response and the information about gradients.

## What this means (level of inference as declared)

1. **Pressure, the S2 pressure tide and a mapping-shape error are disfavoured** as material orbit error sources at
   this configuration. Clocks and the wet nodes absorb almost all of a pressure error. That is the joint-absorption
   effect Sol asked to quantify, now measured through the actual weighted POD rather than the zenith-only control.
2. **Unmodelled horizontal gradients are the one atmosphere term that matters, if they are as large as assumed.**
   - A 0.5 mm per-component gradient field would cost about 0.7 cm URE.
   - The response is mainly along-track: per mm, 3.8 cm along-track RMS for a network-wide north gradient.
   - Along-track was the component where the untouched-date orbits were worse than NGA on 3 of 5 dates. That is a
     coincidence of direction, not an identification.
   - The real gradient size at these stations on this day is **not measured** here.
3. **Estimating gradients freely would be weakly determined** (σ ≈ 0.17 mm against an assumed 0.5 mm signal), and
   weaker with elw13 weights. A useful trial would use external a-priori gradients, or estimation with a declared
   prior, not unconstrained per-station parameters.

## Next step (decision rule: a material term)

Per the protocol, no estimator change is adopted from this diagnostic. The next steps are:
1. **An as-of input ledger for gradients.** It lists the candidate sources with their latency and availability:
   - empirical GPT3 gradients, a static grid with no latency;
   - operational or forecast VMF3 gradients;
   - the IGS troposphere products, as a reference only, never as a fit input.
   Downloading any of them is a data acquisition and is listed for the user.
2. **A matched nonlinear check on Aug 3, which needs the user's go-ahead.** It adds a-priori gradients from the chosen
   source to the observation model, with everything else equal to SD-3/E-elw13-3, and compares with this linear
   prediction. A gradient-estimation trial would need its own frozen protocol (interval, priors, untouched validation
   dates; Sol SCI-02).

## Erratum E-03 (appended 2 Oct 2026, from Astra's evening review; the text above is unchanged)

"Formal σ is 0.13–0.25 mm per component" above is the range of each station's **worse** N/E component. Across all 50
components the range is:
- **0.0965–0.2495 mm** (SD-3 weights);
- **0.1359–0.3483 mm** (elw13 weights; the "0.18–0.35 mm" above is likewise the worse component per station).

The station categories are unchanged, because they were based on each station's worse component: 25 weak (SD-3), and
21 weak / 4 not identifiable (elw13). These are conditional formal uncertainties at the adopted weights and nuisance
model, not calibrated real-world prior widths. The "about 2.7% gain if removed" assumes the hypothetical 0.5 mm
field is present and combines in quadrature; it is not a measured improvement.

Replay precision, from Astra's independent replay `runs/20261002T031551Z-5ff6ce52`:
- the primary arrays are byte-identical;
- the secondary (elw13) derived per-epoch scale series differs from this run by 8.4e-9 ppb (1.1e-8 relative). That is
  above a 1e-12 strict array tolerance, though far below any diagnostic threshold.

The atmosphere result is therefore **not** "bitwise reproducible in every array". The likely amplifier, the unscaled
seven-parameter Helmert design, has not been isolated.
