# First product with the optional gradient model on a new date — result

Opus, 4 October 2026. Protocol: `NEW_DATE_PROTOCOL.md` (`beea93e`, pinned before acquisition), with no amendments.
Acquisition: `NEW_DATE_ACQUISITION.md`. Analysis: `newdate_analysis.json` (run `runs/20261004T164746Z-a87afc6a`).

**Date:** 2026-06-27, untouched-date stream position 10, now consumed.
**Configuration:** the adopted default plus TU Wien GRAD operational gradients (`configurations.md` §1a).
**Product:** `Opus_Fork/datastore/products/OPUS0OPSFIN_20260627.SP3` (SHA-256 `0784be1d1392…`, store data,
git-ignored).

## Operational path (pre-registered readings): passes

| | Check | Result |
|---|---|---|
| P1 | Inputs and their records | Every input acquired. The three GRAD files (177–179) are recorded; the last was observed 40.1 h after the arc ended |
| P2 | Fit | `long_fit_complete`, converged at `lin3-solve` (campaign `20261004T151817Z-fit-N-op-0627`); the binding names exactly the arc's three GRAD files |
| P3 | Product | QA gate passed. The roundtrip matches the scoring path within 0.50 mm; the plain-EOP negative control misses by 116 mm. The header carries the gradient and final-latency labels; product type `FIN` |
| P4 | Independent oracle | Same 2,976 samples; within 4.0 µm of production (tolerance 0.1 mm) |

**Chain:** one external stop. The guard's machine-wide CPU ceiling stopped a worker after 4 s (machine CPU 100%), and
the chain resumed automatically after a quiet period. Its cause is not established: it may have coincided with an
unguarded import check by Opus, which is allowed under the 3 Oct decision.

## Accuracy against IGS final (descriptive, one date)

| | URE (cm) | 3D (cm) | Radial | Along-track | Cross-track (cm) |
|---|---:|---:|---:|---:|---:|
| **Ours, default + GRAD op** | **2.750** | **9.00** | 2.51 | 6.27 | 5.95 |
| NGA PE | 3.795 | 10.05 | 3.62 | 5.89 | 7.30 |

- **URE ratio to NGA 0.725, i.e. 27.5% lower.** This is inside the 0.67–0.85 range stated beforehand.
- 3D ratio 0.895.
- 25 of 31 satellites have a lower URE than NGA's. The largest excesses are G11 +0.91 cm, G02 +0.65 cm and
  G19 +0.55 cm.
- Along-track is the one component where NGA is lower (5.89 against 6.27 cm), as it was in several earlier arms.

IGS final is a reference, not truth. This is one date with no matched default arm, so it says nothing about the
gradients' share of the result. The inputs are retrospective (final latency).

## What this means

The optional model works end to end on a date it had never seen: acquisition with as-of records, the arc-only
binding, the fit, a labelled product and independently reproduced scoring. The accuracy is in line with the
validation dates. A matched default arm on Jun 27 would isolate the gradient contribution; that is a separate fit
needing the user's go-ahead.

## Matched default arm (amendment A1, added 4 Oct 2026 after the default fit)

`U-elw13-0627` is the adopted default without gradients, on the same fixture. It converged at `lin2-solve`
(campaign `20261004T180057Z-fit-U-elw13-0627`). The chain recorded four further external-load stops, each resumed
automatically. Both arms were scored together (`Opus_Fork/results/newdate_matched_20260627.json`); the analysis is
`newdate_matched_analysis.json` (run `runs/20261004T221431Z-0db3dcc1`).

**Controls pass:**
- C1: the lin0 trajectories are bitwise equal in both groups;
- C2: the oracle is within 0.1 mm for both arms, on identical samples.

| | URE (cm) | 3D (cm) | Radial | Along-track | Cross-track (cm) | URE ratio to NGA |
|---|---:|---:|---:|---:|---:|---:|
| Default (U) | 2.859 | 9.26 | 2.61 | 6.32 | 6.25 | 0.753 |
| Default + GRAD op (N-op) | 2.750 | 9.00 | 2.51 | 6.27 | 5.95 | 0.725 |
| NGA PE | 3.795 | 10.05 | 3.62 | 5.89 | 7.30 | 1 |

**Gradient contrast:**
- URE −3.83%, 3D −2.88%;
- radial −4.09%, along-track −0.81%, cross-track −4.82%;
- 19 of 31 satellites better in 3D; the worst satellite is G12 at +1.09 cm.

**Reading (A1): gain reproduced.** On this fresh date the gain is larger than the validation mean (−1.90%) and close
to Aug 3 (−4.16%). This is one date; it adds to the five-date validation.

## How often our URE is below NGA's (user question, 4 Oct)

Source: `ure_time_share.py` and `ure_time_share.json` (run `runs/20261004T221549Z-c9bbab5b`). It uses the oracle's
frame and metric, on the scorer's exact population, and reproduces every production URE within 0.1 mm. The dates are
the five untouched/validation dates and Jun 27.

| Date | 15-min epochs with lower constellation URE: default | + GRAD op | Satellite-epochs with lower URE: default | + GRAD op |
|---|---:|---:|---:|---:|
| Jun 6 | 89/96 (92.7%) | 90/96 (93.8%) | 59.2% | 59.7% |
| Jun 20 | 84/96 (87.5%) | 85/96 (88.5%) | 60.0% | 59.5% |
| Jun 23 | 88/96 (91.7%) | 88/96 (91.7%) | 66.9% | 67.6% |
| Jul 6 | 83/96 (86.5%) | 83/96 (86.5%) | 64.5% | 64.6% |
| Jul 23 | 90/96 (93.8%) | 92/96 (95.8%) | 63.8% | 65.3% |
| Jun 27 | 96/96 (100%) | 96/96 (100%) | 63.4% | 65.8% |
| **Pooled** | **530/576 (92.0%)** | **534/576 (92.7%)** | **63.0%** of 17,760 | **63.8%** |

- **Epoch share:** at each epoch, the RMS over satellites of the instantaneous orbit URE.
- **Satellite-epoch share:** one satellite at one epoch; individual samples are noisier.

Descriptive only: IGS final is the reference, not truth.

## Qualifications (5 Oct 2026, Astra review of 4 Oct; append-only)

- **Chronology.** The matched default arm was added by amendment A1 after the gradient arm had been scored
  (`ab3f7e7` → `6b1a656` → `4d4a744`). The Jun 27 comparison is a **sequentially amended fresh-date comparison**,
  not a blind, jointly preregistered two-arm confirmation. Jun 27 is now consumed.
- **The 92% statement.** It describes the **sampled 15-minute constellation epochs on six summer dates** (530/576
  default, 534/576 with gradients). It is not continuous time, a per-satellite probability, or a forecast for future
  dates, and the epochs are not independent trials. Astra's independent check reproduces the counts.
- **Latency.** As in `VALIDATION_RESULTS.md` erratum E1, the GRAD timestamps are observed Last-Modified metadata, not
  verified issue times. This test makes no delivery-time claim.
