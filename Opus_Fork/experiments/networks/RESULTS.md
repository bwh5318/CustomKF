# Station-network tests: results

8 Oct 2026 (Opus). Protocol: `PROTOCOL.md` §6 with amendments A1–A4.

**Run:** `Opus_Fork/runs/networks-scoring-20261009T003314Z` failed its A3 controls and is preserved. The accepted
rerun under A4 is `Opus_Fork/runs/networks-scoring-20261009T011000Z`, with its analysis in
`runs/20261009T011102Z-d11ad8e8/networks_analysis.json`. Tracked copies, hash-checked against the scoring record:
`networks_analysis.json` and `scoring_record.json` in this folder, and `Opus_Fork/results/networks_YYYYMMDD.json`.

**Scope:**
- **Descriptive only:** IGS final is the reference, not truth. These are exposed dates, not an untouched-date
  validation.
- **Final latency:** every network arm uses GRAD operational gradients. No rapid-operation claim follows, and neither
  test changes the default network.

## Controls

All controls passed on all five dates.

| Control | Result |
|---|---|
| C1: oracle (angles-based CIP, A4) reproduces production URE, 3D, R/A/C and per-satellite 3D | largest difference 4.2e-8 m (limit 1e-4 m) |
| C1 cross-method diagnostic (series CIP, not gated) | 0.04–0.05 mm in June, 0.11 mm in July, as diagnosed |
| C2: lin0 trajectories bitwise equal to V-op's | pass, both groups, every network arm |
| C3: NGA PE rescored by the oracle | largest difference 3.6e-10 m |
| C4: references, EOP, index, force-model identity and comparability | no problems |
| C5: population digest and satellite list | equal |

## S17: 17 selected IGS stations near the NGA and USAF monitor sites

S17 is not NGA's observation data and not NGA's estimator.
- **Distances:** 8 of the 17 stations are more than 1,000 km from their nominal sites: UNSA 1,304, BSHM 1,664,
  GLPS 1,317, PIMO 2,576, SYDN 2,245, NKLG 2,819, NLIB 1,772 and SGOC 1,779 km.
- **Substitution:** BRUX replaces HERS at Hermitage, 404.5 km from the site (A1).

Orbit-only URE against IGS final, in cm:

| Date | NGA PE | V-op (25) | S17 (17) | S17 / NGA | S17 vs V-op |
|---|---:|---:|---:|---:|---:|
| Jun 6 | 3.80 | 2.88 | 6.89 | 1.81 | +139% |
| Jun 20 | 3.91 | 3.34 | 4.17 | 1.07 | +25% |
| Jun 23 | 4.31 | 2.90 | 4.03 | 0.94 | +39% |
| Jul 6 | 3.80 | 2.90 | 4.49 | 1.18 | +55% |
| Jul 23 | 4.21 | 3.00 | 4.55 | 1.08 | +52% |
| **Mean** | **4.01** | **3.00** | **4.83** | **1.22** | **+62%** |

- **Against NGA:** S17 is below NGA PE on **1 of 5 dates**. Its URE is below NGA's at **40% of 15-minute epochs** and
  at 43% of satellite-epochs. For the 25-station V-op arm the epoch figure is 91%.
- **Worst satellite:** the largest per-satellite 3D increase over V-op is G25 on Jun 6, +45 cm. S17's mean 3D change
  is +73%.
- **Reading:** on these dates, a 17-station network with this geometry does **not** stay closer to IGS final than NGA
  PE.
  - The test changes station count and geometry together, so it does not say which matters.
  - It does not say why NGA does better with a network of similar size.

## S50: the 25-station network doubled (up to 50 stations; ambiguity elimination, A2)

| Date | Stations (S50 / 25-arm) | NGA PE | V-op | S50 | S50 / NGA | S50 vs V-op (URE) | 3D change |
|---|---|---:|---:|---:|---:|---:|---:|
| Jun 6 | 49 / 24 | 3.80 | 2.88 | 2.72 | 0.72 | −5.4% | −7.4% |
| Jun 20 | 50 / 25 | 3.91 | 3.34 | 2.66 | 0.68 | −20.2% | −19.5% |
| Jun 23 | 50 / 25 | 4.31 | 2.90 | 2.45 | 0.57 | −15.6% | −17.9% |
| Jul 6 | 49 / 24 | 3.80 | 2.90 | 2.36 | 0.62 | −18.5% | −25.3% |
| Jul 23 | 50 / 25 | 4.21 | 3.00 | 2.54 | 0.60 | −15.3% | −21.7% |
| **Mean** | | **4.01** | **3.00** | **2.55** | **0.64** | **−15.0%** | **−18.4%** |

- **Category (A3/A4 rule):** **improves.** S50 is better on 5 of 5 dates, with a mean of −15.0% (rule: at least 4 of 5
  and at most −1.0%).
- **Radial:** the radial RMS falls on every date; the smallest reduction is −4.9%.
- **Worst satellite:** the largest per-satellite 3D increase over V-op is G26 on Jun 20, +4.2 cm.
- **Against NGA:** S50's URE is below NGA's at **99.6% of 15-minute epochs** and at 70% of satellite-epochs. For V-op
  the figures are 91% and 63%.
- **Solver qualification:** S50 used the eliminating solver. Its real-data parity with the standard solver is a
  maximum of 1.02e-5 m (A2).
- **Doubling changes geometry as well as count.** The 25 added stations were spread by farthest-point selection.

## Other arms (for reference)

U (25 stations, default, no gradients):
- mean URE 3.06 cm, ratio 0.766 to NGA;
- epoch share 90%;
- this reproduces the earlier untouched-date validation, mean ratio 0.766.

## What this means for the objective

- **Station count and geometry matter a lot.** Against the 25-station gradient arm:
  - S50 lowers the URE by 15%;
  - S17 raises it by 62% and no longer beats NGA.
- **A denser network is the largest single gain measured in this project so far,** larger than the gradient model's
  2–4%. It is also the most expensive: one S50 fit takes about 1.5 h.
- **Next, if wanted:** a frozen validation of a 50-station network as the default, on untouched dates, without
  gradients (the rapid candidate). Its station selection must be frozen before any outcome is seen. This would be
  needed before any adoption, and adoption is the user's decision.
