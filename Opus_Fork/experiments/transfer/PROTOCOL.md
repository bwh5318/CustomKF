# Joint weighted transfer calculation — protocol (written before any transfer output exists)

Opus, 28 September 2026 UTC. Review follow-up #2 (`research/opus_work_review_20260926/findings.md`, M08, M15;
`Opus_Fork/results/CORRECTIONS.md`, "Cross-check discipline" item 4). **No fit.** Bounded, linearized, diagnostic only.
At the time this file was written no code of this experiment had run and no transfer number existed.

## Question

How does an observation-model perturbation δy propagate, through the actual weighted station POD (per-epoch clock
elimination, wet-delay nodes, float ambiguities, ECOM5, orbit and wet priors, the real observing geometry), into the
estimated orbits? Can plausible station-tide model differences, satellite-antenna perturbations or a network height
error produce the remaining constellation-scale breathing (SD-3, Aug 3: per-epoch Helmert scale against the IGS-final
reference, 0.311 ppb 12 h amplitude peaking at 4.5 h UT)?

## Linearization point (pinned)

- Campaign `Opus_Fork/runs/20260925T215927Z-fit-SD-3-25st`, final `lin2-solve` (status converged),
  `solution.npz` SHA-256 `c0311ba1249e85c23e538f7ef7f8069f3cbb200e2923efa189c11160ff63fb94`; x binding
  `89b1c90ccadd74a8df9562bf70615819cc6a385fe0fdc443677fbf43cbceb04b`.
- Fixture `Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03/fixture.json` (`b5b5cfc8…39d0`), config
  `claude/roadmap/configs/unit-ecom5.json` (`91aeadac…4ff4fc`), state `state/state.json` (`c37fc923…b2ab`).
- Pilot rebuilt as `experiments/residuals/replay.py` does: `sdeop.install()` with
  `OPUSFORK_SD_VARIANT=erp+thrust+iiia2600+sdeop`, `iteration.build`, products from `lin2-traj-*` via
  `claude.roadmap.traj_cache.cached_products` after checking every binding field except the two sub-daily-EOP source
  hashes (hook switch, verified bit-identical beforehand; `RESIDUAL_BINNING.md`).

## Method

For every epoch, `pilot.epoch_block(x, ei, products, jacobian=True)` gives the retained/local Jacobian, the misclosure
y and σ. A multi-right-hand-side copy of `claude.roadmap.streaming.Accumulator` (identical whitening, local-clock
elimination by `_factor(full=True)`, streaming QR, constraint rows, final `_factor` with the same column scale and
rank rule) solves the same weighted least squares for several targets at once. Constraint targets are the fit's own
(−C·x) for the y column and **0 for every perturbation column** (at convergence the gradient of the full objective
is zero, so the Gauss–Newton response to a model change is the LS solution for δy with zero constraint targets).
δx maps to orbit position through the trajectory partials: δr(t) = Φ(t)[:3]·δx_orbit + Σ_k S(t)[:3,k]·1e-7·δx_ECOMk
(`LongPilot.products`, `traj_cache.initial_and_parameters`). The per-epoch Helmert scale uses the 7-parameter design
of `Opus_Fork/score.py:helmert_residual` (unweighted, all 31 satellites, 96 epochs at 00:00–23:45 UT every 15 min),
hourly means of the four epochs in each hour, and the 12 h/24 h harmonic fit of `experiments/sensitivity/analyze.py`.
Positions are inertial; the scale parameter is invariant to a common rotation of positions and differences.

## Targets (sign conventions)

y = observation − model. A model change δm gives δy = −δm. A modeled station displacement δd changes the modeled range
by −los·δd (los: unit vector station→satellite, ECEF), so δy = +los·δd. Code and phase rows get the same δy.

| Column | Perturbation of the model | δy evaluation |
|---|---|---|
| y | none (fit's own misclosure) | consistency column |
| nopcv | satellite PCV removed (exactly `Opus_Fork/sens.py` nopcv: NOAZI and azimuth tables zeroed) | exact re-evaluation of `modeled_link`; expected +(α·PCV_G01(nadir)+β·PCV_G02(nadir)) |
| pcoz_p1cm | satellite PCO z +10 mm on G01 and G02 | exact re-evaluation |
| solid_iers_minus_fixture | station displacement + (DEHANT − fixture solid) | exact re-evaluation with displaced `receiver_xyz` |
| otl_nodal_minus_fixture | station displacement + (OTL nodal − fixture OTL) | exact re-evaluation |
| h_const_1mm, h12_cos/sin_1mm, h24_cos/sin_1mm | every station up (geodetic) by 1 mm × {1, cos, sin of 2πt/12 h, 2πt/24 h}, t = UT hours | +(los·up)·δh |
| sat_nadir_lin_1mm, sat_nadir_quad_1mm | satellite antenna term +1 mm × (nadir/14°), × (nadir/14°)² | −δm |
| rx_elev_cos_1mm | receiver antenna term +1 mm × cos(elevation) | −δm |

Tide differences use the plain daily EOP exactly as the fixture and `experiments/stationtides/screen.py` do, at each
row's `time_s`. For "ours − IGS" the tide candidates are read as −response(IERS − fixture), i.e. under the assumption
that the reference uses IERS-type models.

## Prerequisite consistency checks (implementation trusted only if K1–K3 pass)

- K1: re-evaluated misclosures equal the fit's `residual_m` (max |Δ| ≤ 1e-6 m).
- K2: the accumulated R equals the fit's final lin2 checkpoint R (max |ΔR| ≤ 1e-6·max|R|).
- K3: the y column reproduces the fit's lin2 predicted reduction (6.289e-06) within 10%, and a trajectory step bound
  below 1 mm.
- K4 (reported): nopcv exact vs analytic α·PCV1+β·PCV2; solid tide exact vs los·δd; fixture `receiver_xyz`
  reproduced by `station_displacement` with the plain EOP; my Helmert of the actual state difference vs the hourly
  (arm − SD-3) difference in `results/sensitivity_analysis.json`.

## Calibration (decides whether the method is used at all)

Actual = S-nopcv-3 `lin2-solve` states − SD-3 `lin2-solve` states (inertial, same 5-min grid, 31 satellites).
Predicted = the nopcv column's δr. **All three must hold:**

- C1 mean scale: |mean_pred − mean_act| ≤ 0.20·|mean_act| (per-epoch Helmert scale, 96 epochs).
- C2 time pattern: Pearson r(pred, act) ≥ 0.80 over the 96 per-epoch scale values.
- C3 orbit level: RMS₃D(act − pred) ≤ 0.30·RMS₃D(act), pooled over 31 satellites × 287 samples.

Reported descriptively: per-satellite RMS ratio, R/A/C split, hourly 12 h/24 h harmonics of both responses, the
implied S-nopcv series (SD-3 hourly + predicted hourly response) against the known 0.245 ppb 12 h / +0.260 ppb mean.
**If any of C1–C3 fails, stop: candidate responses are not analysed or reported** (the solve worker enforces this).

## Candidate measures and reading categories (fixed now)

For each column: per-epoch scale response, hourly means, mean, 12 h and 24 h amplitude/peak UT, the projection of its
12 h vector on the observed SD-3 12 h vector (fraction explained, in phase), correlation of its hourly series with
the observed SD-3 series, and orbit RMS (3D, radial). For the tide candidates the implied "ours − IGS" contribution is
the negative response. Reading of the implied 12 h amplitude against 0.311 ppb:

- **capable of the magnitude**: ≥ 50% (≥ 0.156 ppb) **and** peak within ±1.5 h of 4.5 h (mod 12);
- **minor contributor**: 10–50%, or ≥ 50% at the wrong phase;
- **negligible**: < 10% (< 0.031 ppb).

Height kernel: 12 h (and 24 h) network-height amplitude and phase that would reproduce the observed SD-3 harmonic,
from the cos/sin responses (2×2 linear inversion); the constant-height response in ppb/mm.

## Level of inference

Linear response at one converged point on one day (Aug 3), one network and one weighting. It predicts what a refit
with the changed model would do to first order; it does not measure truth. A candidate that is negligible here is
disfavoured as the main cause of the breathing **for this configuration**; a capable candidate is a hypothesis worth
a controlled refit, not an identification. The IGS-final comparison remains agreement with a reference.

## Resources

Root guard `--profile usage75 --timeout 300`; serial workers (tides, 12 chunks of 12 epochs, solve), each < 300 s;
a direct serial driver launches them one at a time and retries only on guard refusal/external-load stops.

## Amendment A1 (appended 28 Sep 2026, 21:13 local = 01:13 UTC 29 Sep, per file time; no candidate had been analysed)

The first solve (`runs/20260928T223004Z-856d8a18`) passed the calibration by a wide margin: mean scale predicted
0.290288 ppb against 0.290289 ppb actual, per-epoch correlation 0.99999999999, 3D residual 1.4e-5 of the change. K3
(the fit's own linearized step reproduced) also passed, to 2e-13. **K2 failed on a check defect**: it compared the
accumulated triangular factor R with the fit's R **including the sign of each row**. QR factors are unique only up to
row signs (Householder), and |R| matched to 2.3e-15. As the protocol required, the candidates were withheld.

Amendment: K2 compares R and the y column of Z after aligning each row's sign to the fit's. The tolerance is unchanged
(1e-6 relative), and z is now held to the same relative tolerance. The raw sign-sensitive difference and the number of
flipped rows are kept in the output. Only the 9 s solve step is re-run, from the unchanged saved chunk accumulator;
nothing else changes. The candidate results were not known when this amendment was written.
