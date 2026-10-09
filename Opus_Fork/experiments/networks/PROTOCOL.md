# Station-network tests: an NGA-sized network and a doubled network — protocol

Opus, 5 October 2026. Written and committed before any station selection, download, preparation or fit for these
tests.

**User request (5 Oct):** "the other two tests are station availability … 1) a test which has 17 stations similar to
NGA across let's say a 5 days 2) a test which uses far more. maybe 40 or 50? up to you to determine. Using the
models that have given us the best results."

## 1. Questions

- **S17:** with a network of NGA's size placed like NGA's monitor stations, is our orbit still closer to IGS final
  than NGA PE is?
- **S50:** does doubling our 25-station network to 50 stations improve the orbit?

## 2. Configuration, dates and comparators

- **Model:** the best configuration so far, the adopted default plus the optional TU Wien GRAD operational gradients
  (`docs/consolidation/configurations.md` §1, §1a): variant `erp+thrust+iiia2600+sdeop+elw13`,
  `OPUSFORK_GRADIENTS=grad_op`.

  The gradients make every arm here **retrospective (final latency)**. The default without gradients is the
  rapid-candidate configuration; these tests do not change it.
- **Dates:** the five option-A dates, 2026-06-06, 06-20, 06-23, 07-06 and 07-23. Each already has matched 25-station
  arms:
  - `V-op-MMDD` (25 stations + GRAD operational), the primary comparator;
  - `U-elw13-MMDD` (25 stations, default).

  These dates are exposed: they were scored for the default and for the gradients. The network contrasts here are
  new-arm contrasts on them, not untouched-date validation. Using them gives each network a matched same-day
  comparator without new 25-station fits.
- **Fits:** `S17-op-MMDD` and `S50-op-MMDD` through `Opus_Fork.run_fit_elev`, with the option-A settings:
  - config `claude/roadmap/configs/unit-ecom5.json`, chunk epochs 12, trajectory groups 2;
  - worker timeout 900 s, at most 6 linearizations;
  - profile `fork8`, with this file as `--protocol`;
  - one resumable chain, `run_chain_networks.ps1`: S17 on all dates first, then S50.

  At 25 stations the heaviest worker took 70 s and 587 MiB (V-op-0620), so 50 stations is expected to stay within
  the existing limits. No limit is changed. If a worker meets a limit, that is recorded and handled by an amendment,
  never by raising the limit.

## 3. Station pool (deterministic)

A station is eligible when all of these hold:
1. A daily 30 s RINEX 3 file `XXXX00CCC_R_YYYYDDD0000_01D_30S_MO.crx.gz` is listed at BKG
   (`igs.bkg.bund.de/root_ftp/IGS/obs/YYYY/DDD/`) **for all five dates**. If several markers share a four-character
   site, the lexically first nine-character marker is used.
2. It has an IGc20 position solution valid at each date (`customkf.station_models.reference_coordinate`, as
   preparation uses).
3. It is not named in `psd_IGc20.snx` (the preparer refuses post-seismic stations).
4. It has an entry in `FES2014b.BLQ`.
5. It has four GRAD operational epochs in every file each date's arc needs (`gradients.arc_days`).
6. Its header passes `Opus_Fork.fetch`'s availability screen (signal pair, cadence, time system, ANTEX antenna) on
   all five dates. This is checked on demand, in the order the rules below consider candidates. Every screen result
   is recorded.

Distances are great-circle distances on a sphere, computed from the IGc20 coordinates. Ties are broken by marker
name.

## 4. Networks

**S17 (NGA-like).** NGA's GPS monitoring network as publicly described: 11 NGA stations and the 6 U.S. Air Force
stations. For each site in the order below, the nearest pool station not already taken is chosen. Coordinates are
approximate public locations; the rule uses only nearest-station ranking.

| # | Site | Lat (deg) | Lon (deg) |
|---:|---|---:|---:|
| 1 | Adelaide, Australia | −34.93 | 138.60 |
| 2 | Buenos Aires, Argentina | −34.60 | −58.38 |
| 3 | Hermitage, England | 51.45 | −1.27 |
| 4 | Manama, Bahrain | 26.23 | 50.59 |
| 5 | Quito, Ecuador | −0.18 | −78.47 |
| 6 | Washington DC (USNO), USA | 38.92 | −77.07 |
| 7 | Fairbanks, Alaska | 64.84 | −147.72 |
| 8 | Osan, South Korea | 37.09 | 127.03 |
| 9 | Papeete, Tahiti | −17.55 | −149.56 |
| 10 | Pretoria, South Africa | −25.75 | 28.19 |
| 11 | Wellington, New Zealand | −41.29 | 174.78 |
| 12 | Ascension Island (USAF) | −7.95 | −14.36 |
| 13 | Cape Canaveral, Florida (USAF) | 28.39 | −80.60 |
| 14 | Colorado Springs, Colorado (USAF) | 38.80 | −104.53 |
| 15 | Diego Garcia (USAF) | −7.31 | 72.41 |
| 16 | Hawaii, Oahu (USAF) | 21.57 | −158.27 |
| 17 | Kwajalein Atoll (USAF) | 8.72 | 167.73 |

Each choice's distance to its site is recorded. A substitute farther than 1,000 km is still taken, but flagged.

**S50 (doubled).**
- Start from the frozen 25-station network (`Opus_Fork/fetch.py:NETWORK_25`).
- Repeatedly add the pool station that maximizes the minimum great-circle distance to the stations already chosen
  (farthest-point selection), until there are 50.
- This spreads the added stations evenly over the Earth. No orbit or residual information enters the choice.

The selection runs once, as one guarded job (`select_networks.py`). It writes `networks.json` with the pool, the
order of consideration, every screen result and the final lists. Selection uses no orbit, residual or reference
product.

## 5. Acquisition and preparation

- **Acquisition:** `Opus_Fork.fetch station` per added marker and date under the root `usage75` guard, followed by a
  store index rebuild and verification.
- **Availability rule:** a station that fails to download intact on a date is dropped for that date and recorded.
  A date needs at least 15 of 17 (S17) or 45 of 50 (S50) stations.
- **Preparation:** `Opus_Fork.prepare --start 00:00 --epochs 144 --previous-day-nav --per-epoch-nav
  --stations <list>`, under the root `usage75` guard, as the untouched dates were prepared.

## 6. Scoring, controls and reading

**Scoring.** For each date, `Opus_Fork.evaluate` scores U, V-op, S17-op and S50-op together over the full day
(00:00–23:45), against IGS final, with NGA PE added and V-op as the baseline. The population is the satellite-epochs
common to every arm and NGA.

**Analysis** (`analyze_networks.py`, written before any network fit completes):
- Solutions are resolved from evaluator provenance and their hashes verified (Astra R02).
- The common key set is reconstructed and its digest recorded.
- The analysis also computes the time shares of `ure_time_share.py` against NGA.

**Controls.** The reading is withheld if any control fails.
- **C1:** the oracle reproduces every arm's production URE and 3D within 0.1 mm, on the same key set.
- **C2:** where a network arm and V-op have the same satellite set, their lin0 trajectory arrays are bitwise equal.
  Satellite seeds come from the broadcast navigation, so the network should not change them.

**Reading for S17** (descriptive; IGS final is the reference, not truth):
- the per-date URE ratio to NGA PE, the number of dates below 1.0, and the mean;
- the epoch and satellite-epoch shares below NGA;
- the URE change against V-op.

Stated expectation, not a rule: a sparser network should be worse than 25 stations. Whether it stays below NGA is
the open question.

**Reading for S50** (URE change against V-op, per date and mean):

| Category | Rule |
|---|---|
| improves | better on ≥ 4 of 5 dates and mean ≤ −1.0% |
| no material change | mean within ±1.0% |
| worse | mean ≥ +1.0% |
| mixed | any other outcome |

The 3D and radial changes, the worst satellite and the time shares are reported alongside.

**Neither test changes the default network.** Any adoption is the user's decision and would need its own frozen
validation.

## Amendments

(append only; record whether any outcome existed)

### A1 — clock datum and markers (5 Oct 2026, before any fixture or fit)

**Outcome state when written:** the station selection (`networks.json`) and the downloads existed. No fixture had
been prepared, and no fit or score existed.

1. **Clock datum.** The estimator (`claude/roadmap/long_pilot.py`, unchanged) fixes the receiver clock of **BRUX** as
   the per-epoch clock datum, and `Opus_Fork/prepare.py` refuses a network without BRUX. S17's rule did not select
   BRUX, so **S17's Hermitage site takes BRUX** (404.5 km from the site) instead of HERS (141.3 km). S17 keeps 17
   stations. S50 already contains BRUX. Generalizing the datum would change the core estimator during a test; it is
   recorded as a follow-up instead.
2. **Markers.** `Opus_Fork/prepare.py` accepts nine-character markers for stations outside the frozen 25 (its own
   commit, with a unit test and a byte-for-byte parity preparation of the Jun 20 fixture). Four-character names
   resolve as before.
3. **Station lists.** `station_lists.py` applies the substitution and lists each date's acquired stations.

### A2 — S50 under its workspace budget (7 Oct 2026, before the parity fit and any new S50 fit)

**Outcome state when written:**
- S17 is complete on all five dates. Nothing in it has been scored or opened.
- S50-op-0606 stopped in its first chunk on the 512 MiB workspace preflight (Astra PI-13): 49 stations, 3,453 retained
  parameters, estimate 749 MiB. No S50 result exists.

**User decision (7 Oct): make the solve leaner.**
1. **The change.** S50 fits run with `--eliminate-ambiguities` (`EliminatingAccumulator`, commits `09aa63e` and
   `c40ce9c`).
   - Each ambiguity is folded out of the streaming square-root solve when its arc has ended, and recovered by
     back-substitution after the solve.
   - This is exact for a full-rank system; the final solve's pivoted QR and rank rule are unchanged.
   - **Unchanged:** stations, data, weights, models, the 512 MiB workspace preflight, the 4 GiB cap and every other
     limit. No arc is discarded.
2. **Real-data parity before any S50 fit.**
   - **The check fit:** `E-check-0620` repeats `V-op-0620` (Jun 20, 25 stations, default + GRAD op, the same settings)
     with the flag on.
   - **Pass rule** (`parity_check.py`): every saved position differs by at most **1 mm**, with the same parameter
     layout and the same model binding. The gradient input list and module hash are normalized, since `V-op-0620`
     predates the arc-only binding `d281a93`, whose values were shown identical.
   - **On failure** the chain stops before S50, and the failure is reported.
3. **New campaigns.** S50 runs as `S50e-op-MMDD`; the failed `S50-op-0606` campaign is preserved unchanged. Scoring
   uses the S50e campaigns under the arm name `S50-op`. The station lists, dates, readings and controls of §6 are
   unchanged.
4. **Comparability.** V-op and S17 used the original accumulator. Because elimination is exact, the S50 contrast stays
   matched up to the rounding difference that the parity check measures, and that difference is reported with the
   S50 result.

### A3 — acceptance repairs before scoring (8 Oct 2026, before any network score)

**Outcome state when written:**
- All ten network campaigns are complete (S17-op and S50e-op on all five dates), and the A2 parity check passed:
  maximum position difference 1.02e-5 m (`runs/20261007T215551Z-1e19cd4c/parity.json`).
- SP3 files were exported from the network solutions (`deliverables/make_sp3.sh`). The exporter checks each file
  against its own solution only.
- The chain logs show how many linearizations each fit needed.
- **No network arm has been evaluated.** No network score, comparison with IGS final or NGA, or time share has been
  computed or opened.

**Source:** Astra's pre-outcome review N1–N4 (`research/final_documentation_review_20261006/NETWORK_PROTOCOL_REVIEW.md`).
The user asked on 8 Oct to fix these and score. Astra has not reviewed the repairs.

**Original sources, replaced and kept in git:**
- `analyze_networks.py`: sha256 `f71a76b2975d241754f6376bc12aa320043a7fb85ba804ef27c11911a4bb2153`, commit `8ced1e5`.
- `finish_networks.sh`: sha256 `da86432e79e83f2c7d71e089981148c27a1771c8671e870e1a712d1d8ce92a3f`, commit `a879eca`. It
  was never run.

The protocol body, the networks, the campaigns and their pins are unchanged. Nothing is refitted.

1. **Frozen scoring index (N2).**
   - `scoring_index.json` (`make_scoring_index.py`) names, for each date, the exact campaign folders of U, V-op, S17-op
     and S50-op (the S50e-op campaign, A2).
   - Each entry records the final step, the solution hash, and the fixture the solution is bound to.
   - It is committed before any evaluation. No campaign is chosen by its label.
   - U on Jun 23 is `U-elw13-0623r`, as in the earlier validation scoring.
2. **Wrapper (N2).** `score_networks.py` replaces `finish_networks.sh`.
   - **Preflight:** all 20 campaign and fixture pairs are checked against the index before any evaluation. These
     checks are: complete; converged; final step; solution hash; fixture hash; and the step's fixture binding. If one
     fails, nothing is evaluated.
   - **One guarded evaluation per date** (usage75, one thread). It is accepted only when all of these hold:
     - the guard exits 0;
     - the output is in that guard's new run folder;
     - the `Opus_Fork/results` copy is byte-identical to it;
     - its provenance names exactly the indexed solutions and fixtures, and the right day.
   - Logs are kept. Any failure stops the wrapper with a failing exit status.
   - **One guarded analysis** then reads the evaluations only through the wrapper's record, which includes their hashes.
3. **Controls (N1).** If any control fails, every reading is withheld and the analysis exits with a failing status.
   C1 and C2 keep their meaning. The others are added.
   - **C1 (extended):** the independent oracle reproduces, within 0.1 mm and on identical keys, each fitted arm's
     URE, 3D, each R/A/C component, and each satellite's 3D.
   - **C3 (NGA):** the same reproduction for NGA PE, scored by the oracle from the NGA file.
   - **C4 (provenance):**
     - the IGS final and NGA files match the hashes the evaluation recorded and the store's entry;
     - the Earth-orientation file matches the evaluation's recorded hash, and it is unchanged across the scoring run;
     - every arm's solution and fixture hashes match the index;
     - the day and the scored window (00:00–23:45) match.
     - **Force models:** every arm has variant `erp+thrust+iiia2600+sdeop+elw13` and the same sub-daily EOP model.
       - V-op, S17-op and S50-op use `grad_op`. S17-op's and S50-op's force models are identical to V-op's, with the
         gradient input list and module hash normalized, as in A2.
       - U has no gradients. Its model is identical to V-op's except for the gradients entry and `elev_sha256`.
       - **Why U's `elev_sha256` differs:** `Opus_Fork/elev.py` gained only the 1 Oct gradient hook and a `none`
         option after the U fits. Its `elw13` weighting code is unchanged, which a diff of the two campaigns'
         source copies shows. Checked on the configuration records before any score; the field is listed in the
         output.
   - **C5 (population):** the reconstructed key set has the evaluation's recorded population digest, not merely the
     same count, and the same satellite list. The digest is new in `Opus_Fork.evaluate` (commit `6dc8419`).
   - **Negative controls** are unit tests. Each must fail its control: a changed NGA score, a changed reference file,
     a changed force model, and the same count of different keys.
4. **Reporting (N3).**
   - **S17 wording:** S17 is described as "17 selected IGS stations near the publicly described NGA and USAF monitor
     sites". It is not NGA's data or estimator. The site distances, the over-1,000 km flags and the A1 BRUX
     substitution are reported with the result.
   - **Counts:** for each date and arm, the station, observation and satellite counts come from the fixtures and
     solutions. The experiment is not a uniform 17 versus 25 versus 50.
   - **Status of the dates:** they are exposed. All network arms are final latency (gradients), so no rapid-operation
     claim follows.
   - **S50:** the A2 parity difference is reported with the S50 result.
5. **S50 categories (N4).** The rules are evaluated in this order, on unrounded values; the first match wins.
   1. **improves:** the URE change is below 0 on at least 4 of 5 dates, and the mean is at most −1.0%.
   2. **no material change:** −1.0% < mean < +1.0%.
   3. **worse:** mean ≥ +1.0%.
   4. **mixed:** any other outcome, that is, mean ≤ −1.0% with fewer than four dates better.

   This restates the order and limits that the pre-outcome analysis already implemented (`s50_reading`); it does not
   change them. The mean and each date's change are reported beside the category.

### A4 — C1 with matching CIP methods, and three acceptance repairs (8 Oct 2026; results sealed)

**Outcome state when written:**
- The first scoring run (`Opus_Fork/runs/networks-scoring-20261009T003314Z`) exists.
  - Its five evaluations and its analysis output (`runs/20261009T003410Z-580a2c59`) contain network scores.
  - **Neither Opus nor Astra has opened any network score, ratio, contrast, time share or reading.**
- The analysis withheld its readings: the A3 extension of C1 failed on Jul 6 and Jul 23 (per-satellite 3D, 0.101 to
  0.115 mm against 0.1 mm). Every other control passed.
- This amendment follows only frame and synthetic evidence: Opus's diagnostic (`76d9f3b`) and Astra's review
  (`research/astra_network_review_20261008/REVIEW.md`). It was not chosen from any network outcome.
- The failed run, its diagnostic and the A3 body are preserved.

1. **C1 and C3 use matching CIP methods.**
   - **Cause.** Production composes GCRS→ITRS with ERFA's angles-based CIP X, Y (`xys06a`). The oracle uses the
     series-based `xy06`. Both are IAU 2006/2000A, and ERFA documents differences at the microarcsecond level between
     the two methods. Matching the method leaves 0.006 µas (Astra).
   - **New oracle path.** The oracle gains an opt-in angles-based path, `Frame(..., cip="angles")`, taking X, Y from
     `bpn2xy(pnm06a(TT))`. Everything else stays the oracle's own:
     - time conversion;
     - EOP reading and interpolation;
     - tidal corrections and dX/dY;
     - s06, the Earth rotation angle and polar motion.
   - **Default unchanged.** The default (series) path is unchanged, so earlier oracle results stand.
   - **The limit stays.** C1 and C3 use the angles path, with the **0.1 mm limit unchanged** for the aggregate and
     per-satellite quantities. The time shares use the same path.
   - **The series path stays as a diagnostic.** It is kept as a separately labelled cross-method frame diagnostic;
     its differences are reported, not gated.
2. **NR-01 (diagnostic grid).**
   - **The bug:** `diagnose_c1.py` built its epochs with a default-integer `np.arange`. That is int32 on this Windows
     NumPy and overflowed, so its frame maxima describe a span of about 4 s around midnight, not the full day.
   - **The fix:** int64, with a regression test.
   - **The record:** the correction is appended to the 8 Oct note, and the original run is preserved. Astra's
     full-day maxima are 0.59–1.50 µas.
3. **NR-02 (malformed metrics).** The score comparison refuses all of these, and a refusal fails the control:
   - non-finite or negative RMS values;
   - R/A/C lists that are not exactly three finite values;
   - mismatched satellite membership;
   - sample counts that are not positive.
4. **NR-03 (model identity).** These checks come before any normalization.
   - Each final `force_model.json` must match its campaign's artifact pin (`artifacts_sha256`) by bytes, and its
     decoded contents must match the campaign record's `force_model`.
   - The model hash is carried through the evaluation provenance (an additive evaluator field) and the scoring record.
     The analysis checks it again.
   - The analysis rehashes each indexed fixture when it uses it.
   - The expected hashes are in a new sidecar, `scoring_index_models.json`. `scoring_index.json` is untouched.
   - A2's normalization between campaigns stays. It never excuses a changed file within one campaign.
5. **Rerun.**
   - After the repairs and their regressions pass, run the complete wrapper: fresh evaluations and analysis, under the
     existing serial usage75 guards. No refit.
   - The results are unsealed only if C1–C5 all pass.
