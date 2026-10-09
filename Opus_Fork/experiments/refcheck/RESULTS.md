# Pairwise scale-breathing consistency check: result

Opus, 29 Sep 2026 02:18 UTC. Protocol `PROTOCOL.md` (written before the run). Run `runs/20260929T021813Z-b9021e0a`;
output `Opus_Fork/results/refcheck_scale_pairs.json`. Evaluation only. **A consistency check, not an attribution**
(Astra checkpoint-A review A06).

## 12 h term of the per-epoch Helmert scale (ppb, peak UT)

| Pair | Aug 2 | Aug 3 | Aug 4 | Aug 5 | Aug 7 | Day repetition r (range) |
|---|---|---|---|---|---|---|
| ours − IGS final | 0.162 @ 4.7 h | 0.311 @ 4.5 h | 0.247 @ 5.7 h | 0.235 @ 7.0 h | 0.365 @ 5.0 h | 0.21 – 0.95 |
| ours − IGS rapid | 0.155 @ 4.8 | 0.313 @ 4.5 | 0.262 @ 5.5 | 0.203 @ 6.6 | 0.352 @ 4.9 | 0.20 – 0.96 |
| ours − NGA PE | 0.137 @ 10.0 | 0.233 @ 3.7 | 0.074 @ 5.1 | 0.223 @ 9.7 | 0.422 @ 5.5 | −0.16 – 0.94 |
| NGA PE − IGS final | 0.293 @ 4.4 | 0.144 @ 6.0 | 0.178 @ 5.9 | 0.301 @ 5.4 | 0.122 @ 1.3 | 0.10 – 0.74 |
| IGS rapid − IGS final | 0.012 | 0.005 | 0.030 | 0.052 | 0.029 | — |
| NGA PE − IGS rapid | 0.285 @ 4.4 | 0.143 @ 6.0 | 0.190 @ 5.6 | 0.310 @ 5.1 | 0.151 @ 1.3 | 0.11 – 0.77 |

Mean scale:
- ours − final: −0.17 to +0.06 ppb;
- NGA − final: −0.00 to +0.11 ppb;
- ours − NGA: −0.28 to +0.06 ppb.

Each day uses a common satellite-epoch set across all four products: 2,496–2,976 samples and 96 epochs. Pairwise
closure is at most 3.6e-8 ppb, which only confirms the measure is linear. 24 h terms and hourly series are in the
JSON.

## Reading (descriptive, as declared)

1. **IGS rapid and IGS final agree** to ≤ 0.05 ppb in the 12 h term. Scoring against rapid instead of final changes
   ours − reference by at most 0.03 ppb (Aug 5). The two IGS products are not independent of each other, so this
   says nothing about either one's absolute scale.
2. **NGA PE also differs from IGS by a semidiurnal scale term** of 0.12–0.30 ppb. On four of five days its peak is
   at 4.4–6.0 h UT, the same window as ours − IGS (4.5–7.0 h). So the "breathing" is not unique to our orbits:
   operational NGA shows the same kind of 12 h scale difference from IGS, of comparable size.
3. **Ours − NGA** has an amplitude comparable to ours − IGS (within ± 30%) on Aug 3, 5 and 7, and smaller on Aug 2
   and 4. Its phase varies more from day to day, and it repeats least consistently.
4. **What this does not settle.** The pattern is shared relative to IGS by two separately produced orbits. That is
   consistent with an IGS-side component, *and* with a deficiency common to ours and NGA (for example a model both
   omit and IGS analysis centres include). Because every comparison shares products, this check cannot tell those
   apart. It does make the 0.3 ppb breathing look less like a defect specific to our fit, and more like a
   systematic difference between processing families.

## Implication for next steps (a suggestion, not a decision)

A cheap, still evaluation-only step: find a model component that NGA-style and our processing plausibly share, but
that IGS analysis centres apply. Then test it with the transfer kernel or a scoring-side check. The current forced
list of observation-model candidates (station tides, antenna terms) came out small in `TRANSFER_CALCULATION.md`.
Without such a candidate, the breathing stays documented as an unexplained difference of about 0.2–0.4 ppb
relative to IGS. It is the same order as NGA's own difference from IGS.
