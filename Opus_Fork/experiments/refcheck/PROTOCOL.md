# Pairwise scale-breathing consistency check: protocol (written before any output)

Opus, 29 Sep 2026. User decision item 7 (`docs/consolidation/DECISIONS_NEEDED.md`), with the wording changed per Astra's
checkpoint-A review A06. **Evaluation only**: no fit, no model change, no new input. Diagnostic, not accuracy acceptance.

## Question

The per-epoch Helmert scale of our SD solutions against IGS final shows a 12 h "breathing": 0.311 ppb, peaking at
4.5 h UT on Aug 3. Is that pattern consistent across the pairwise differences between four products on the same
satellite-epochs?

The four products:

- ours (the SD arms);
- IGS final;
- IGS rapid;
- NGA PE.

**What this can and cannot say.** Every comparison shares products. Agreement or disagreement between pairs
constrains *consistency*: which products share a pattern, and whether the pairwise scales close. It cannot uniquely
assign the pattern to "reference error" versus "our force model". IGS rapid and final are not independent of each
other, and NGA and ours could share a model deficiency. No causal conclusion is drawn from this check alone.

## Inputs (unchanged, hash-verified by the loaders)

- **Days and solutions.** The five SD days: Aug 2, 3, 4, 5 and 7. Each uses its converged SD solution and fixture,
  exactly the list in `experiments/review_fixes/check_fixes.py` (`SD`). Solutions are loaded with sub-daily-aware
  scoring (`sd_scoring.install`, then `dip_nga.load_solution`).
- **References.** IGS final (`reference_igs_final`), IGS rapid (`reference_igs_rapid`) and NGA PE
  (`reference_nga_pe`, legacy GPS time label). All three come from the single store and are declared as the
  existing evaluators declare them.
- **Common set.** One common satellite-epoch set per day, across all four products.

## Measures (fixed now)

- **Per-epoch scale.** For each pair A − B (B the reference argument): the 7-parameter per-epoch scale from
  `Opus_Fork/score.py:helmert_residual`, as in every earlier scale result.
- **Pairs:**
  - ours − final;
  - ours − rapid;
  - ours − NGA;
  - NGA − final;
  - rapid − final;
  - NGA − rapid.
- **Hourly harmonics.** Hourly means over UT hours 0–23, then the harmonic fit of
  `experiments/sensitivity/analyze.py:harm`: mean, 12 h and 24 h amplitude and peak UT.
- **Closure,** per epoch:
  - s(ours − final) − s(ours − NGA) − s(NGA − final);
  - s(ours − final) − s(ours − rapid) − s(rapid − final).

  Report max |·| and RMS. A small closure only confirms the linearity of the measure. It is not a finding.
- **Day repetition.** For each pair and day, the correlation of the hourly series with the mean of the other four
  days.

## Reading (descriptive only)

For each day, report whether ours − NGA and ours − rapid show a 12 h amplitude comparable to ours − final
(within ± 30%). Also report whether NGA − final and rapid − final show a 12 h term, with its amplitude and phase,
and how strongly each pair repeats from day to day. Nothing here changes a model or a default.

## Resources

Root guard `--profile usage75 --timeout 600`; one worker.
