# First product with the optional gradient model on a new date — protocol

Opus, 4 October 2026, before any acquisition, preparation or fit for the date below. User go-ahead (3/4 Oct): "go
ahead and start that new test", the test proposed after the adoption (`docs/consolidation/configurations.md` §1a):
one default-plus-gradients fit on a new date, exported as a product.

## 1. Purpose

Exercise the adopted optional model end to end on a date it has never seen:
1. acquisition, including its GRAD files and their as-of record;
2. preparation;
3. the fit;
4. the labelled product;
5. scoring.

This is an operational test of the path. It is not a test of the gradient gain: there is no matched default arm, so
nothing here attributes accuracy to the gradients.

## 2. Date

- **Rule:** the next date of the pinned untouched-date stream
  (`Opus_Fork/experiments/untouched_dates/date_stream.json`, seed 20260929), examined in stream order under that
  protocol's usability rules U1–U6, with its clarifications.
- **Stream positions 1–8** were examined in September.
- **Position 9 (2026-08-13)** is recorded there as failing U3 (its own BKG file is the incomplete one found at
  position 2) and is skipped for that reason.
- **The candidate is therefore position 10, 2026-06-27.** Positions 11 onwards replace it, in order, only if it
  fails a rule.
- **Seen before writing this:** U1 and U2 existence only. The IGS final file and `nga24246.sp3` are listed in the
  store index; neither was opened.
- **Exposure:** the date used here is consumed. Any later fresh-date test continues the stream after it.

## 3. Pipeline (frozen)

- **Acquisition.** `Opus_Fork.fetch` under the root `usage75` guard:
  - the availability screen;
  - the stations passing U4;
  - BRDC for the day and the previous day.

  GRAD files come from `experiments/gradients/acquire_day.sh` and are appended to `acquisition_record.tsv`.
- **Preparation.** `Opus_Fork.prepare --start 00:00 --epochs 144 --previous-day-nav --per-epoch-nav`, with an
  explicit `--stations` list (the 25-station network minus the U4 failures), under the root `usage75` guard.
- **Fit.** `Opus_Fork.run_fit_elev`, label `N-op-MMDD`:
  - variant `erp+thrust+iiia2600+sdeop+elw13`, `OPUSFORK_GRADIENTS=grad_op`;
  - config `claude/roadmap/configs/unit-ecom5.json`, chunk epochs 12, trajectory groups 2;
  - worker timeout 900 s, at most 6 linearizations;
  - profile `fork8`, through a resumable chain, with this file as `--protocol`.

  These are the option-A settings.
- **Product.** `Opus_Fork.export write` to the product store (`OPUS0OPSFIN_YYYYMMDD.SP3`), plus
  `export.roundtrip` with its plain-EOP negative control, run in a guard folder.
- **Scoring.** `Opus_Fork.evaluate`, full day 00:00–23:45, against IGS final, with NGA PE added by the evaluator.
  It is checked by the independent oracle (`validation/oracle`) on the same samples.

## 4. Reading (pre-registered)

**The operational path passes** if all of these hold:
- P1: every input is acquired with its record, including each GRAD file's server Last-Modified;
- P2: the fit completes converged (`long_fit_complete`);
- P3: the export passes its QA gate; the roundtrip is within 0.51 mm while the negative control fails; and the
  header carries the gradient and final-latency labels;
- P4: the production scores are reproduced by the oracle within 0.1 mm on identical samples.

A failure is reported as such, with its stage. A defect found is fixed in its own commit, and the step rerun is
recorded as an amendment.

**Accuracy is descriptive only:**
- URE, 3D and RAC against IGS final;
- the URE and 3D ratios to NGA PE;
- the number of satellites whose URE beats NGA's.

IGS final is a reference, not truth. One date carries no adoption or rejection rule.

**Stated expectation, not a rule:** the five validation dates gave URE ratios to NGA of 0.67–0.85 with this
configuration, so a ratio in that range would be unsurprising. A ratio above 1.0 would be investigated, and reported
whatever the outcome.

**Latency:** retrospective by construction, since the date is months old. The GRAD files' observed Last-Modified
times are recorded, but they are not verified issue times.

## 5. Not part of this test

- A matched default arm (`U-elw13-MMDD`) on the same date. That would be a separate fit, needing the user's
  go-ahead.
- Any change to the default.
- GRAD_FC (forecast gradients).
- Any report or PDF update.

## Amendments

(append only; record whether any outcome existed)

### A1 — matched default arm (4 Oct 2026, user go-ahead: "go ahead and do that")

**Outcome state when written:**
- `N-op-0627` is complete and scored (`NEW_DATE_RESULTS.md`: URE 2.750 cm, NGA 3.795 cm). That outcome existed.
- No default arm exists on this date, and the gradient contrast is unknown.
- The text above this amendment is unchanged (SHA-256 `a35bf2cf…db5460`).

**Addition:** one fit `U-elw13-0627`, identical to §3 except `OPUSFORK_GRADIENTS=none` (the adopted default). It is
the next step of `run_chain_newdate.ps1`. The two arms are scored together by `Opus_Fork.evaluate`, with `U` as the
baseline and NGA PE alongside, and the oracle checks both.

**Controls:**
- C1: the lin0 trajectory arrays of both arms are bitwise equal (gradients enter only the observations);
- C2: the oracle reproduces both arms' production scores within 0.1 mm on identical samples.

If a control fails, the contrast is not read.

**Reading of the gradient contrast** (N-op against U, full day, URE). Per date, these are the option-A thresholds:

| Category | Rule |
|---|---|
| gain reproduced | URE change ≤ −1.0%, worst satellite 3D increase ≤ 10 cm, radial change ≤ +3% |
| smaller gain | −1.0% < change < 0, with the same satellite and radial limits |
| not reproduced | change ≥ 0, or a satellite or radial limit exceeded |

**Scope:**
- This is one fresh date, a new-arm contrast on a date not used for selection.
- It adds to, and does not replace, the five-date validation.
- It carries no adoption rule: the model is already adopted as optional.
- The default's own Jun 27 score is reported descriptively against NGA PE, like N-op's.
