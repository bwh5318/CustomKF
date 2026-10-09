# A-priori gradients: validation on five further dates — protocol (written before any validation fit exists)

Opus, 2 October 2026. User decision of 2 Oct: "go ahead and start option A". This follows `PROTOCOL.md` and `RESULTS.md`
in this folder. Two Aug 3 **candidates** are under test, each added to the adopted default
(`erp+thrust+iiia2600+sdeop+elw13`):
- `grad_op`: TU Wien GRAD operational site-wise gradients (next-day latency);
- `gpt3`: GPT3 empirical gradients (zero latency).

When this was written, no gradient had been applied on any of these dates and no fit or prediction existed for them.

## Dates and their status

Jun 6, Jun 20, Jun 23, Jul 6 and Jul 23 2026, the untouched-date set of 30 Sep
(`experiments/untouched_dates/RESULTS.md`).
- The adopted default's scores on these dates **are known**: they validated the default. So the dates are not
  untouched for the default.
- **No gradient decision used them.** The gradient fields are external and were not tuned. The only choice under
  test, adding the field or not and which one, was made on Aug 3 alone.
- Results here are **new-arm contrasts on dates outside the gradient selection**. Fresh untouched dates (option C)
  remain the stronger test.

GRAD coverage was checked before this protocol: every fixture station on every date has epochs from 18:00 the day
before through 00:00 the day after. That is 24 stations on Jun 6 and Jul 6, and 25 on the others. All files are in
`acquisition_record.tsv`.

## Arms (matched to the existing comparators)

| Date | Fixture (prepare run) | Comparator (adopted default) | New arms |
|---|---|---|---|
| Jun 6 | `runs/20260929T202245Z-21f63ba3` | `Opus_Fork/runs/20260930T012728Z-fit-U-elw13-0606` | V-op-0606, V-gpt3-0606 |
| Jun 20 | `runs/20260929T203924Z-224f1e22` | `Opus_Fork/runs/20260929T233503Z-fit-U-elw13-0620` | V-op-0620, V-gpt3-0620 |
| Jun 23 | `runs/20260929T201929Z-5b2b3e42` | `Opus_Fork/runs/20261001T012217Z-fit-U-elw13-0623r` (the repaired fit, amendment A3) | V-op-0623, V-gpt3-0623 |
| Jul 6 | `runs/20260929T204645Z-ba94e895` | `Opus_Fork/runs/20260930T234445Z-fit-U-elw13-0706` | V-op-0706, V-gpt3-0706 |
| Jul 23 | `runs/20260929T203059Z-40b5a8d7` | `Opus_Fork/runs/20260930T220757Z-fit-U-elw13-0723` | V-op-0723, V-gpt3-0723 |

Each new arm uses the comparator's settings: config `unit-ecom5`, chunks of 12 epochs, 2 trajectory groups, `fork8`,
up to 6 linearizations, 900 s worker timeout. The only change is `OPUSFORK_GRADIENTS`. Order: the five `grad_op`
arms first, then the five `gpt3` arms.

**Control:** each arm's lin0 trajectory arrays must be bitwise equal to its comparator's. If not, the date is reported
but labelled unmatched.

## Scoring

Raw, unaligned, against IGS final, with NGA PE in the same table on common samples. Both
`Opus_Fork.experiments.subdaily.evaluate_sd` (production) and `validation/oracle` (independent; agreement within
0.1 mm required) are used. Measures per arm and date:
- URE, 3D, R/A/C;
- the change against the comparator;
- per-satellite 3D change;
- the URE ratio to NGA.

## Reading (fixed now; separately for each candidate)

| Outcome over the five dates | Reading |
|---|---|
| URE better than the comparator on **≥ 4 of 5** dates, **mean URE change ≤ −1.0%**, no satellite 3D worse by > 0.1 m on any date, and radial RMS not worse by > 3% on any date | **Validated on these dates** |
| URE worse on ≥ 2 dates, or a mean URE change > 0 | **Not validated** |
| anything else | **Inconclusive** |

Adoption is **not** automatic. A validated candidate goes to the user as a model-change proposal with its latency
label: `grad_op` cannot be part of a rapid product without the forecast product; `gpt3` can. No Aug 3 linear
prediction transfers to these dates, so none is made.

## Resources

`fork8` full fits (user-authorized) in a resumable chain (`run_chain_gradval.ps1`; `resume_chain.ps1 -Chain
gradval`). It waits for GPU below 50%, at least 6.5 GiB free and no Python (memory policy of 2 Oct). One guarded job
at a time. About 1 h per fit, so about 10 h in all.

## Amendment A1 (appended 2 Oct 2026, before any validation fit; from Astra's check-in review C03)

The "next-day latency" shorthand for `grad_op` is replaced by a full input-support account. For each date the result
will list:
- the GRAD files the arc's interpolation needs, including the following day's midnight endpoint;
- each file's observed server Last-Modified (UTC);
- the resulting retrospective label.

Observed modification times are not verified issue times. Adopting either field remains reference-scored model
selection, whatever the inputs are. Arms, controls, scoring and the reading rule are unchanged.
