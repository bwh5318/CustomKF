# A-priori gradients: validation on five further dates — result

Opus, 3 October 2026. Protocol: `VALIDATION_PROTOCOL.md` in this folder, with amendment A1, both pinned before any
validation fit.
- **Chain:** `Opus_Fork/runs/gradval-chain.status`, with the external-load and sleep resumes recorded there. Two
  stops were not external:
  - a PC-sleep timeout (V-op-0723);
  - a Windows file-lock race during a folder move after a CPU-limit stop (V-gpt3-0723).

  Both were resumed, and both fits completed.
- **Scoring:** production `Opus_Fork/results/gradval_YYYYMMDD.json` (`Opus_Fork.evaluate`), and analysis
  `validation_analysis.json` (`runs/20261004T004541Z-baf6018c`). The latter covers the lin0 controls, the independent
  oracle, the readings and the input support.

**Scope.** These are new-arm contrasts on dates outside the gradient selection:
- the adopted default's scores on these dates were known;
- no gradient decision used them.

They are not fresh untouched validation. IGS final is a reference, not truth. The gradient fields are independent
fit inputs, but choosing one is reference-scored model selection.

## Controls (all pass)

- **lin0:** trajectory arrays bitwise equal to each comparator's, both groups, all ten arms.
- **Independent oracle against production:** the same samples on every date, with agreement within 1.4–6.7 µm
  (tolerance 0.1 mm).

## Scores against IGS final (full day; URE change against the adopted default)

| Date | Default URE (cm) | NGA URE (cm) | + GRAD operational | 3D | radial | satellites better | worst satellite 3D | + GPT3 | 3D |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Jun 6 | 2.911 | 3.804 | **−1.15%** | −2.03% | −0.93% | 23/30 | +1.98 cm (G24) | −0.56% | −0.11% |
| Jun 20 | 3.395 | 3.911 | **−1.72%** | −1.56% | −1.75% | 21/31 | +1.15 cm (G12) | −0.19% | −0.04% |
| Jun 23 | 2.964 | 4.306 | **−2.14%** | −1.67% | −2.23% | 19/31 | +0.83 cm (G08) | −0.74% | +0.29% |
| Jul 6 | 2.914 | 3.798 | **−0.42%** | −1.74% | −0.10% | 21/31 | +0.80 cm (G06) | −0.21% | −0.28% |
| Jul 23 | 3.127 | 4.210 | **−4.07%** | −4.95% | −3.91% | 25/31 | +1.73 cm (G12) | −1.33% | +0.11% |
| **Mean** | | | **−1.90%** | **−2.39%** | | | max +1.98 cm | **−0.61%** | −0.01% |

Mean URE ratio to NGA PE: default 0.766, **+ GRAD operational 0.752**, + GPT3 0.762.

## Reading (pre-registered)

| Candidate | Rule | Category |
|---|---|---|
| **GRAD operational** | better on 5/5 (≥ 4 needed); mean −1.90% (≤ −1.0% needed); worst satellite +1.98 cm (≤ 10 cm); radial never worse (≤ +3%) | **Validated on these dates** |
| **GPT3** | better on 5/5, but mean −0.61% (≤ −1.0% needed); 3D unchanged on average | **Inconclusive** |

## Input support for GRAD operational (amendment A1)

Every arc needs three daily files: the previous day, the same day, and the following day for the midnight endpoint.
On all five dates, the last required file's observed server Last-Modified is **40.1 h after the arc ends**, at about
16:03–16:04 UTC two days later. These are observed modification times, not verified issue times. **The GRAD
operational input is therefore retrospective** for this purpose. A product built with it would be available about two
days after the observation day: later than IGS rapid (about 17 h), earlier than IGS final.

## What this means for the objective

- **Across six dates (Aug 3 plus these five), adding external weather-model gradients consistently improves the
  orbit.** The gain on the five validation dates (mean −1.9% URE, −2.4% 3D) is smaller than on Aug 3 (−4.2%) but
  present on every date. The radial component improves on every date.
- **The empirical GPT3 gradients help a little** (5/5 dates, mean −0.6%), but less than the registered 1% bar. They
  cannot replace weather-model gradients.
- **The rapid-latency objective is not met with the operational product.** The latency-appropriate route is TU Wien's
  **forecast** gradients (GRAD_FC, nominally available before the day starts). Those need credentials, which the user
  could request. A forecast arm would need its own as-of ledger and validation.

## Next steps

1. **Adoption is the user's decision.** Proposal:
   - add GRAD operational gradients as an **optional, labelled** model change for retrospective (final-latency)
     products only;
   - keep the default unchanged for anything claiming rapid latency.
2. If near-real-time matters: obtain GRAD_FC access, then run a forecast-input validation with an as-of ledger.
3. Fresh untouched dates (option C) would be the stronger test of the operational-gradient gain.

## Erratum E1 (5 Oct 2026, Astra review R03; append-only)

The "Input support" section says a product using GRAD operational "would be available about two days after the
observation day". **That inference is withdrawn.**
- **What was observed:** the server Last-Modified times recorded at acquisition, months after the dates. The last
  required file's time lies 40.06–40.07 h after each arc's end.
- **What that does not show:** Last-Modified does not prove when a file first became available. A product's delivery
  time would also depend on every other input's readiness and on processing time.
- **What stands:** the classification is unchanged. The input is **retrospective**, and no delivery deadline or
  operational latency is claimed.
