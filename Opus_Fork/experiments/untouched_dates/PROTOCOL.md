# Untouched-date validation of the current default: protocol

Opus, 29 Sep 2026. User decision item 2 (`docs/consolidation/DECISIONS_NEEDED.md`), approved 29 Sep with downloads
pre-authorized. This is the open science gate named in review findings M03 and C02 and in `configurations.md` §6.
Every result so far is on 1–8 August, which is fully exposed.

**This protocol is written, and the dates drawn, before any data for them is downloaded or looked at.** Astra's
checkpoint-A review (A06) notes that this gate is independent of code consolidation. Its fits are a new campaign,
so under A02 they wait until the campaign lease is repaired and integrated, or until a separately reviewed bridge
exists. They also wait for the user's go-ahead to fit.

## 1. Question

Does the current default keep beating NGA PE, in raw orbit-only URE against IGS final, on dates whose data, residuals,
diagnostics and scores have informed nothing in this project? And by how much?

## 2. Date selection (deterministic; `draw_dates.py`)

- **Window:** 2026-06-01 to 2026-08-27. The end is the last date with NGA PE indexed in the store at protocol time.
  IGS final and EOP (measured values to 2026-09-03) both cover the window.
- **Excluded:** 2026-07-30 to 2026-08-09. That covers every date used so far (Jul 31 – Aug 8) plus one day either
  side, because previous-day navigation data enters each fit.
- **Draw:** `random.Random(20260929).shuffle` of the eligible dates in calendar order. The shuffled list is a stream.
  The first five usable dates are the test set, and later dates are replacements, taken strictly in stream order.
- **Usability rules,** checked in stream order. A date that fails any rule is replaced, with the reason recorded:
  - U1: the IGS final SP3 for the day is retrievable.
  - U2: NGA PE for the day is in the store.
  - U3: broadcast navigation for the day and the previous day is retrievable.
  - U4: at least 22 of the 25 frozen network stations pass the existing availability screen (`Opus_Fork.fetch
    availability`: header, antenna calibration, selectable signal pair) and download intact.
  - U5: no satellite-metadata change within the arc (the N05 refusal).
  - U6: fixture preparation succeeds.
- **No other replacement.** A date is never replaced because of a fit, residual, diagnostic or score outcome, and it
  is never replaced by inspecting its orbit products beyond U1/U2 existence.

## 3. Frozen pipeline

- **Configuration:** the adopted default, `run_fit_elev --variant erp+thrust+iiia2600+sdeop+elw13`.
  - ECOM5 with fixed ERP/thrust (IIIA 2,600 kg);
  - IERS 2010 sub-daily EOP;
  - phase sigma 9 mm/sin(e)^1.3;
  - the fit's usual linearization sequence and stopping rule;
  - no reference-derived priors.
- **Network:** the 25-station network (`Opus_Fork/fetch.py:NETWORK_25`), minus stations failing U4 on that date.
  There is no substitution.
- **Inputs:** Opus preparer policy (two-day merged navigation). Daily EOP from the existing
  `data/stage2/finals2000A.all`, which is retrospective, as for every earlier campaign (M01; labelled).
- **Code:** frozen at a git commit recorded in an appended amendment to this file before the first fit. It must be a
  commit whose numerical estimator, frame and scoring paths are unchanged from the adopted campaigns, or
  parity-proven against them per the consolidation plan.
- **Reference-informed choices** (C02 labels): the elw13 exponent and W-scales are station-derived and were
  selected using reference scores on studied days. They are frozen here and not re-tuned.

## 4. Scoring (frozen)

- **Scorer:** `Opus_Fork/evaluate.py`, raw unaligned. The reference is IGS final. NGA PE is always in the same
  table, on the satellite-epochs common to ours, NGA PE and IGS final.
- **Time and satellites:** full day, 00:00–23:45 at 15 min. No satellite is excluded beyond common availability.
  Per-satellite results are reported.
- **Metrics:** orbit-only URE = sqrt(mean(0.98² R² + (A² + C²)/49)) and 3D RMS, for ours and NGA PE.
- **Second scorer:** if the independent oracle scorer (checkpoint-A A03) exists before scoring, it scores the same
  files as well. Any disagreement above 0.5 mm is investigated before a result is reported.

## 5. Pre-registered claims and rules

- **Primary (URE).** For each date, the ratio URE_ours / URE_NGA. The transfer claim "the default is closer to IGS
  final than NGA PE in orbit-only URE" holds on this set if the ratio is < 1 on at least 4 of 5 dates **and** the
  mean ratio is < 1.
- **Secondary (3D).** The same, with 3D RMS. Reported whatever the outcome; no claim unless the same 4-of-5 plus
  mean rule holds.
- **Descriptive only.**
  - the per-epoch Helmert-scale 12 h breathing, ours − IGS final and NGA − IGS final (as in
    `experiments/refcheck/`);
  - per-satellite outliers;
  - convergence behaviour.
- **Always reported.** Every result is reported, including failed fits, which count as failures for the claim.
  None is re-run with a changed configuration inside this test. A fit stopped by an external guard event (not by
  its own numerics) is resumed, not replaced.
- **Explicitly not claimed:**
  - rapid-latency operation (inputs are retrospective);
  - absolute truth (IGS final is a reference);
  - that the SD-EOP or elw13 gains transfer, which would need matched comparator arms, optional later work.

## 6. Resources

- **Downloads and preparation:** root guard `usage75`, one guarded job at a time.
- **Fits:** the user-authorized `fork8` policy for full fits, as resumable chains (the PC is switched off
  overnight). Nothing starts while another campaign is running.

## Amendment A1 (29 Sep 2026, before any fit; no orbit solution or score for any untouched date exists)

**Seen before writing this.** The availability screens and downloads for stream dates 1–5, and one preparation
attempt per date (`ACQUISITION.md`). The attempts showed three things:

- **Incomplete broadcast navigation.** BKG's archived `BRDC00WRD` for 2026-06-15 (DOY 166), 08-13 (225) and 08-14
  (226) is a same-day merge (run at 23:10 UTC) that was never replaced. It holds about 4 GPS records per satellite,
  against the normal 14–15. The resulting fixtures had 6 and 4 satellites.
- **A reader limitation.** On 06-20 and 06-23, YELL00CAN carries a header-information event, "E L6C 0.00000
  SYS / PHASE SHIFT", which the RINEX reader refused.
- **An interface gap.** For 06-06, the preparer was not given the station list without DAV1.

**Clarifications** (they apply to every date in the stream, past and future):

- **U3, complete navigation.** Each daily broadcast file, for the day and the previous day, must hold at least
  9 GPS LNAV records per GPS satellite present, which is a cadence of about 2–3 h or better. Normal files hold
  14–15, and the incomplete ones about 4. Failing dates are replaced. The rule is about data, not outcome, and no
  alternative navigation source is introduced.
- **U6, preparation.** A preparation failure caused by a reader or preparer limitation that would affect any date
  is fixed by a general, tested and parity-proven code change, not by replacing the date.
  - Such a fix is its own commit.
  - The Aug 2 preparation must reproduce the adopted fixture exactly.
  - Only defective data replaces a date under U6.
  - Applied: commit `333bd85` (zero phase-shift events).
- **U4 station set.** It is passed explicitly: `--stations` = the 25-station network minus the stations failing U4
  on that date. This is what §3 already required.

**Replacements,** in stream order:

- 2026-06-15 (#5) fails U3 on its own day file.
- 2026-08-14 (#2) fails U3 on its own day and the previous day.
- 2026-08-13 (#9) will fail U3 when reached.
- The next stream dates, 2026-07-23 (#6) and 2026-06-05 (#7), are examined under U1–U4 plus the U3 completeness
  count, then prepared.

**Preparation code** is `Opus_Fork/prepare.py` at the commit current when each fixture is prepared, recorded with
the fixture. The fit code freeze in §3 is unchanged.

## Amendment A2 (29 Sep 2026, before the first fit): fit configuration and code freeze

**No fit has started, and no orbit solution or score for any untouched date exists.** Astra's Part B integration
repairs (B01–B04) are done: her 4 probes and 7 real-guard checks pass (`0831750`). The user gave the go-ahead.

- **Controller.** `Opus_Fork.run_fit_elev`, which holds the campaign lease. It runs through
  `Opus_Fork/experiments/untouched_dates/run_chain_untouched.ps1`, resumed after any stop with
  `Opus_Fork/resume_chain.ps1 -Chain untouched`.
- **Order** (stream order): Jun 20, Jun 6, Jun 23, Jul 23, Jul 6. Labels `U-elw13-MMDD`.
- **Configuration.** These are exactly the settings of the adopted Aug 3–5 E-elw13 campaigns:
  - variant `erp+thrust+iiia2600+sdeop+elw13`;
  - `claude/roadmap/configs/unit-ecom5.json`;
  - `--chunk-epochs 12 --trajectory-groups 2 --max-linearizations 6 --worker-timeout 900`;
  - profile `fork8`.
- **Code.** The last code change is commit `0831750`. Each campaign pins all 229 sources by SHA-256 (this protocol
  included) and copies them into its `source/` folder. A resume refuses if any pinned file changes, so **no pinned
  file may be edited until the chain completes**.
- **Differences from the adopted E-elw13-3 campaign's pinned sources.** Nine files changed. None changes estimator,
  frame or scoring arithmetic:
  - `customkf/guard.py`, `Opus_Fork/guard.py`, `Opus_Fork/run_fit_elev.py`: docstrings, campaign-lease admission,
    runtime pins. These are runtime and control only.
  - `claude/roadmap/traj_cache.py`, `claude/roadmap/long_iteration.py`, `Opus_Fork/iteration.py`: the M10 cache
    contract. Archived caches gave states bitwise equal to the saved solution (`tests/traj_cache_compat.py`).
  - `Opus_Fork/ngv_pilot.py`: N05, the metadata day becomes the arc midpoint and an in-arc change is refused. U5
    shows no metadata change within any of the five arcs, so the models are identical either way.
  - `customkf/rinex.py`: the zero phase-shift event fix. It is used in preparation only, and parity was proven on
    Aug 2.
  - `claude/roadmap/streaming.py`: docstring only.

  Added pins: this protocol and `customkf/runtime/{__init__,lease}.py`.
- **Scoring (§4) is unchanged** and runs after the chain completes.

## Amendment A3 (written 30 Sep 2026 about 18:30 local, before any scoring; appended after the chain completed)

The text below was committed unchanged as `AMENDMENT_A3_PENDING.md` (commit `227fa59`), while `PROTOCOL.md` was pinned by
running campaigns. Afterwards the fix was merged (`08acbe7`). Its regressions pass: `tests/test_link_jacobian_domain.py`
6/6, and the real-data check `stencil_check.json` (runs/20261001T012010Z-934ba950): 2,776 of 2,777 links in Jun 23
epochs 96-108 are bitwise equal to the former formula, and the formerly refused GLPS-G10 link equals the 5 m
difference. Status when appended: Jun 20, Jun 6, Jul 23 and Jul 6 complete; Jun 23 failed and preserved; nothing
scored.

## What happened

Campaign `Opus_Fork/runs/20260930T183604Z-fit-U-elw13-0623` stopped in worker `lin0-chunk-096-108`, at epoch 105,
fixture row 11880. The error was `ANTEX angular extrapolation`, raised inside the finite-difference measurement
Jacobian.

The observation itself was valid:
- link GLPS–G10;
- elevation 10.000226°;
- receiver antenna `ASH701945B_M SCIT`, whose calibration table covers 0–80° zenith.

The failure came from the −10 m initial-x tangent sample. It moved the evaluated zenith to 80.00013°, outside the
table. Two independent diagnostics agree: Opus (`runs/20260930T220600Z-789b6ee2`) and Sol
(`SOL_REVIEW_FOR_ASTRA_OPUS_55.md`, SOL-01). Smaller symmetric steps (5, 2.5, 1.25 m) stay inside the table and give
the same correction derivative to about 1e-14 relative.

This is a derivative-domain defect in the estimator. It is not a data defect and not an outcome.

## Amendment

1. **Classification.** A fit stopped by an estimator defect that would affect any date is not a "failed fit" in the
   sense of §5. It is repaired by one general defect fix with a regression test, and the date is re-fitted as a new
   campaign. The failed campaign is preserved unchanged.
2. **The fix.** The correction-difference stencil in `claude/tools/dated_observation.link_jacobian`:
   - first tries the standard step (±10 m, ±0.01 m/s) exactly as before;
   - only when a sample leaves a model's valid domain (ANTEX), halves the symmetric step down to a documented
     minimum, then falls back to a one-sided difference;
   - still refuses an out-of-domain base observation.

   The calibration evaluator stays strict: no clamping, and no change to the cutoff, weights or population.
3. **Parity with every completed fit.** Wherever the standard stencil is valid, the result is bitwise identical,
   because the same expression is evaluated first. Any completed fit that had needed the fallback would have
   stopped, so no completed fit (Jun 20, Jun 6, Jul 23 and Jul 6 if they complete, and all August campaigns) is
   affected. Their pins stay as they were.
4. **The re-fit.** Jun 23 is re-fitted as campaign `U-elw13-0623r`: same fixture, configuration and settings as A2,
   with the fixed code pinned.
5. **Reporting both results.**
   - **(i) As registered:** Jun 23 is a failed fit. It counts as not beating NGA, and its URE ratio is undefined, so
     the as-registered five-date mean ratio is undefined and the as-registered claim is **not established**. It is
     never computed from the other four alone (Sol, SCI-08).
   - **(ii) Repaired:** all five dates, with Jun 23 from `U-elw13-0623r`, scored exactly as in §4 and §5.

   The report states both. The repaired result is labelled as depending on this amendment.
6. **Order.** No untouched-date orbit is scored until this amendment is appended to `PROTOCOL.md` and the Jun 23
   re-fit has completed or failed.

## Erratum E1 (1 Oct 2026; Astra follow-up review AF-03; appended, nothing above is changed)

1. **Scope of A3's classification.** A3 item 1, "not a 'failed fit' in the sense of §5", applies **only to the
   repaired analysis**. In the original as-registered test, the Jun 23 failure stands. It is counted exactly as in A3
   item 5(i), and that claim remains not established. The repaired pipeline includes a defect change (`08acbe7`)
   prompted by the Jun 23 fit failure. The repaired result is therefore "initially unexposed dates, repaired under
   A3", not an untouched implementation passing its original frozen test.
2. **Precision of the derivative controls.** The A3 text ("What happened") says the smaller symmetric steps "give
   the same correction derivative to about 1e-14 relative". The saved controls actually differ by at most
   **7.816e-15 in derivative units**, which is about **1.485e-10 relative** at their magnitude of 5.264e-5. The
   stability is still excellent, but the relative figure was wrong. The same correction applies to the
   corresponding sentence in `SOL_REVIEW_FOR_ASTRA_OPUS_55.md` (SOL-01) and in `AMENDMENT_A3_PENDING.md`. Both are
   preserved unchanged as historical records.
3. **Timestamp.** `AMENDMENT_A3_PENDING.md` gives an approximate writing time of "about 18:30 local". Its commit
   `227fa59` records 18:12 EDT, and that commit time is the authoritative one.
