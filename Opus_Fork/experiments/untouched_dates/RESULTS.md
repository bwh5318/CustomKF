# Untouched-date validation of the current default: result

Scored 30 Sep 2026, after the chain and the Jun 23 re-fit completed. Protocol: `PROTOCOL.md` (the body, plus
amendments A1, A2 and A3, each pinned before the outcomes it governs). Scores come from `Opus_Fork/evaluate.py`: raw
and unaligned, with IGS final as the reference and NGA PE in the same table. They use the satellite-epochs common to
ours, NGA PE and IGS final, 00:00–23:45 every 15 min, with no satellite exclusion beyond common availability. Machine
record: `scores.json`; per-day output: `Opus_Fork/results/untouched_YYYYMMDD.json`.

## Scores (orbit-only URE = sqrt(mean(0.98² R² + (A² + C²)/49)); cm)

| Date | Satellites / samples | URE ours | URE NGA | **URE ratio** | 3D ours | 3D NGA | 3D ratio | R/A/C ours | R/A/C NGA | Satellites better than NGA (3D) |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| 2026-06-20 | 31 / 2,976 | 3.395 | 3.911 | **0.868** | 9.447 | 10.216 | 0.925 | 3.21 / 6.16 / 6.40 | 3.74 / 6.68 / 6.77 | 22/31 |
| 2026-06-06 | 30 / 2,880 | 2.911 | 3.804 | **0.765** | 9.172 | 10.303 | 0.890 | 2.68 / 7.05 / 5.23 | 3.62 / 5.50 / 7.93 | 18/30 |
| 2026-06-23 (re-fit, A3) | 31 / 2,976 | 2.964 | 4.306 | **0.688** | 8.417 | 10.633 | 0.792 | 2.79 / 5.62 / 5.61 | 4.16 / 6.95 / 6.89 | 24/31 |
| 2026-07-23 | 31 / 2,976 | 3.127 | 4.210 | **0.743** | 8.775 | 10.818 | 0.811 | 2.95 / 6.36 / 5.27 | 4.04 / 6.09 / 7.98 | 23/31 |
| 2026-07-06 | 31 / 2,976 | 2.914 | 3.798 | **0.767** | 9.062 | 10.552 | 0.859 | 2.69 / 7.06 / 5.01 | 3.60 / 6.12 / 7.81 | 21/31 |
| **Mean ratio** | | | | **0.766** | | | **0.855** | | | |

## Verdicts under the pre-registered rules (§5, amendment A3)

- **Repaired result** (A3; Jun 23 from the re-fit `U-elw13-0623r`):
  - **Primary (URE): holds.** The ratio is below 1 on 5 of 5 dates, and the mean ratio of 0.766 is below 1.
  - **Secondary (3D): holds.** The ratio is below 1 on 5 of 5 dates, with a mean of 0.855.
- **As registered** (no A3): **not established.** The original Jun 23 fit stopped on an estimator defect (SOL-01).
  It counts as not beating NGA, so its ratio, and the five-date mean, are undefined. The other four dates all have
  URE ratios below 1, but the mean rule cannot be evaluated, and it is not recomputed over four dates.

## Reading (what this does and does not show)

- **What it shows.** On five dates drawn by a fixed seed and never used before in this project, and with a pipeline
  frozen before any of them was fitted, the default product agrees with IGS final better than NGA PE does:
  - by 13–31% in orbit-only URE;
  - by 8–21% in 3D.

  This is the first evidence for the default that does not come from the studied 1–8 August days (M03).
- **Where the advantage comes from.** Radial is better on all five dates (2.7–3.2 cm against NGA's 3.6–4.2 cm), and
  so is cross-track (5.0–6.4 cm against 6.8–8.0 cm). **Along-track is mixed**: worse than NGA on Jun 6
  (7.05 vs 5.50 cm), Jul 23 (6.36 vs 6.09 cm) and Jul 6 (7.06 vs 6.12 cm). The URE gain is therefore mainly radial
  and cross-track. Along-track is the component to watch.
- **Limits.**
  - **IGS final is a reference, not truth.**
  - The inputs are **retrospective**: final observation files and a later EOP file. This is not a rapid-latency
    demonstration (M01, SCI-09).
  - Five dates in one season (June–July 2026), one 24–25-station network, one configuration. That is not a
    population claim across seasons or networks (Sol, SCI-08).
  - Model choices made earlier (elw13, sub-daily EOP, IIIA mass) were **selected using reference scores** on the
    August days (C02 labels). This test checks whether those choices transfer; it does not make them
    reference-independent.
  - The independent oracle scorer (A03) does not exist yet. Scores come from the production evaluator only.
  - The Jun 23 value depends on amendment A3, which the user approved. Astra's view on A3 was requested and is
    pending.
- **Process record.** Jun 23 first failed on the SOL-01 derivative-domain defect, then was re-fitted with the fix
  (bitwise identical wherever the old stencil was valid). Scoring needed a store fix (`55734f5`), because the IGS
  final existed as identical gzip and plain copies. No fit was repeated or altered after any score was seen.

## Next steps (recommendations)

1. Ask Astra to review A3 and this result. Recompute the scores with the independent oracle once it exists.
2. Optionally, matched comparator arms on these dates (BACKLOG B3) to test whether the sub-daily EOP and elw13 gains
   transfer.
3. Look at along-track, the weak component. It is a natural target for Sol's science recommendations: attitude and
   force-model omissions (SCI-03/04), after the atmosphere transfer (SCI-01/02).
4. Gather more seasons and an as-of (latency) input ledger before any broader or operational claim.

## Errata (1 Oct 2026; Astra follow-up review AF-03)

- **Wording.** "A pipeline frozen before any of them was fitted" (Reading, first bullet) needs the A3 exception.
  The pipeline was frozen before the first fit, but the repaired analysis includes a defect fix (`08acbe7`)
  prompted by the Jun 23 failure. Read it as **initially unexposed dates, repaired under A3**. The original
  as-registered test is not established. See `PROTOCOL.md` erratum E1.
- **Independent check.** Astra independently recomputed the scores (`research/astra_followup_review_20260930/`). It
  used separate SP3 parsing and metric arithmetic, but shared the production frame and EOP code. All five daily wins
  and both means were reproduced: URE 0.7663532781 and 3D 0.8553120076. The largest daily metric difference was
  9.02e-9 m. This is numerical agreement, not physical precision. The independent frame oracle (O2) is still open.
