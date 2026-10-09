# Results, first phase (6-19 September 2026)

From the first station-fitted orbits (158 m) to 24-hour arcs with 25 stations. Each section is one original write-up, unchanged except that its headings are one level deeper.

This document is generated for the public release. Links inside the sections point to files of the private working repository, which may not be here.

## Contents

1. `STAGE0_RESULTS.md`
2. `STAGE1_RESULTS.md`
3. `STAGE2_RESULTS.md`
4. `STAGE3_RESULTS.md`
5. `KOUR_INVESTIGATION.md`
6. `STAGE4_RESULTS.md`
7. `STAGE5_RESULTS.md`
8. `STAGE5_ATTRIBUTION.md`
9. `STAGE5B_RESULTS.md`
10. `STAGE5B_STATION_CHECKS.md`
11. `YELL_GUAM_RESULTS.md`
12. `STABILITY_RESULTS.md`
13. `WET_DELAY_EXPERIMENT.md`
14. `DYNAMICS_CEILING_RESULTS.md`
15. `OBSERVATION_PROFILE_RESULTS.md`
16. `ARC_LENGTH_RESULTS.md`
17. `FORCE_PARAMETER_PROTOCOL.md`
18. `FORCE_PARAMETER_RESULTS.md`
19. `D0_POD_PROTOCOL.md`
20. `D0_POD_RESULTS.md`
21. `D0_DAY215_PROTOCOL.md`
22. `D0_DAY215_RESULTS.md`
23. `GUAM_GAP_PROTOCOL.md`
24. `GUAM_GAP_RESULTS.md`
25. `D0_REPLICATION_PLAN.md`
26. `claude/roadmap/STREAMING_AND_ARCS_PROTOCOL.md`
27. `claude/roadmap/STREAMING_RESULTS.md`
28. `claude/roadmap/STEP3_RESULTS.md`
29. `claude/roadmap/BENCH_PROTOCOL.md`
30. `claude/roadmap/BENCH_RESULTS.md`
31. `claude/roadmap/STATION_EXPANSION_PROTOCOL.md`
32. `claude/roadmap/STATIONS_RESULTS.md`
33. `claude/roadmap/BLOCK_D0_PROTOCOL.md`
34. `claude/roadmap/BLOCK_D0_RESULTS.md`
35. `COMPARISON_CONTRACT.md`

---

<!-- original: STAGE0_RESULTS.md -->

## Stage 0 results

**Stage 0 is complete: conventions, comparator, a small pinned development set and bounded Windows execution are implemented and validated.** This is a foundation for the orbit estimator; it does not yet generate an orbit from station observations. No software was installed, no remote data were downloaded, and the existing `autocomparesp3` source/data were not edited.

Final validation: **2026-09-06 15:02 UTC**, using the existing Anaconda Python 3.12.7 on the i7-13700F /31.77 GiB Windows machine. [Full machine-readable report](E:/pythontests/customKF/validation/stage0/20260906T150250Z.json) includes tested source/contract hashes, fixture-manifest hash, every safety-probe result, test logs, numerical-library settings and the real-data findings.

### What passed

**34 tests passed: 13 resource-control tests and 21 comparator/parser tests.** The real-data audit additionally verified 15 input/source fingerprints, compared **27,648 valid GPS position records** against the previous parser, and reproduced the old study calculation over **6,144 matched satellite-epochs** on two dates. All five real files had exactly matching valid GPS keys and coordinates in the new and old parsers.

The independent synthetic checks cover identity, signed centimetre RAC offsets, right-handed orthonormal axes, invariance under a common rotation, the distinction between inertial and Earth-fixed velocity, URE amplitude weighting, a 1 ns clock offset, clock-datum removal, missing records, flags, time systems and exact epoch matching. One test runs synthetic SP3 files through parsing, matching, RAC and clock-inclusive SISRE end to end.

The [comparison contract](E:/pythontests/customKF/COMPARISON_CONTRACT.md) freezes candidate-minus-IGS signs, COM positions, GPS time, SI units, exact common epochs, reference inertial RAC axes, the paper's URE formula, explicit screening and raw-coordinate scores without fitted frame alignment.

### Measured resource use

The final validation used the normal **2 GiB private-commit cap, one logical CPU, one MKL thread and a configured 10% CPU quota** for numerical work. Safety probes used deliberately smaller caps. The entire validation took **13.58 seconds**, including the five-second CPU probe and timeout/cleanup tests.

| Workload | Wall time | CPU time | Sampled peak RSS | Sampled peak private commit | Minimum available system RAM |
|---|---:|---:|---:|---:|---:|
| 21 numerical/parser tests, guarded process | 0.77 s | 0.27 s | 50.32 MiB | 37.98 MiB | 12.77 GiB |
| Five-file real-data audit | 3.13 s | 2.52 s | 68.22 MiB | 51.86 MiB | 12.76 GiB |

RSS and private-memory samples are collected at approximately 0.1-second intervals, so they are observed sample peaks, not continuous physical-memory maxima. The job's separate Windows peak accounting reported 56.18 MiB on the real-data audit. These numbers concern the local worker tree; they do not include the small controller or Codex itself. They validate the Stage 0 workload only and do not reduce the uncertainty of later POD runtime estimates.

Resource-control verification included:

- Reading back the native job's memory, affinity, priority, process-count and CPU limits before resuming computation; inspecting the actual MKL thread count afterward.
- Attempting a **256 MiB private allocation inside a 128 MiB job**. Windows denied it with error 1455; the worker's private memory remained exactly **10,805,248 bytes before and after**. The attempted block was never touched.
- Running a five-second one-core probe with a **1% CPU quota**: **1.28125 CPU-seconds over 5.172 wall-seconds**, about 0.248 logical CPUs on average. This is consistent with approximately 1% of 24 logical CPUs, within startup/scheduling effects. It is not a per-instant CPU calibration.
- Terminating parent and child on timeout, detecting and terminating orphan children, and proving kill-on-job-close cleanup after an injected controller exception.
- Refusing overlapping guarded jobs, insufficient memory headroom, invalid budgets and simulated OS setup failure. There is no unguarded fallback.
- Exercising low-memory stop/termination logic with **simulated system availability**, rather than consuming real RAM to create pressure.

Two useful issues emerged during validation. Windows can signal process exit before its job's active-process count settles; the controller now gives accounting **up to 0.2 seconds** to settle while retaining its watchdog checks, then treats remaining processes as orphans. A one-second CPU probe produced inconsistent averages, so the final check uses five seconds; the exact source of the short-window variability was not established, and no claim of instantaneous quota accuracy is made.

There is also an accounting caveat: the denied-allocation probe reported a raw Windows job-memory peak of **268.04 MiB**, even though allocation failed and private memory did not increase. On this machine that counter alone cannot establish whether a denied request actually consumed memory. The reports therefore preserve the raw Windows counter, sampled private/RSS values and the allocation outcome separately. The resource policy caps worker private commitment; it does not cap every use of physical RAM by the OS or other applications. See [operating limits](E:/pythontests/customKF/README.md) for scope and API references.

### Real-data reproduction

The [manifest](E:/pythontests/customKF/data/stage0/manifest.json) pins five SP3 files plus the historical event list and paper-number summary: **3,781,714 bytes (3.61 MiB)**, excluding the manifest. Each entry has an original path, SHA-256 hash, byte count, actual header frame/time metadata and intended role.

| Development case | Selection evidence | Purpose |
|---|---|---|
| 2026-08-02 G08 | Old study beta +48.22°, eclipse fraction 0 | Initial quiet arc |
| 2026-08-02 G01 | Old study beta −5.04°, eclipse fraction 8/96 epochs | Eclipse/low-beta arc |
| 2026-03-04 G20 | Existing study satellite-day exclusion; maximum discrepancy 272.37 km | Ensure raw events remain visible and exclusions are explicit |

Beta/eclipse values are inherited from the old approximate geometry. They are useful development labels, not independently verified attitude histories. The G20 discrepancy's physical cause remains unverified here. No static PRN-to-spacecraft-block mapping was adopted.

The following results are **existing products compared with existing products**, in the explicitly labelled historical paper-compatibility mode:

| Comparison | Rows retained | R RMS | A RMS | C RMS | 3D RMS | Orbit-only URE RMS |
|---|---:|---:|---:|---:|---:|---:|
| NGA − IGS final, 2026-08-02 | 3,072 | 4.25 cm | 6.79 cm | 7.78 cm | 11.17 cm | 4.42 cm |
| NGA − IGS final, 2026-03-04, historical G20 exclusion | 2,976 | 3.12 cm | 6.76 cm | 6.54 cm | 9.91 cm | 3.34 cm |

The March 4 raw result retains all 3,072 rows and has **17,726.64 m 3D RMS**, dominated by the large G20 discrepancy. The historical exclusion removes 96 rows; the raw maximum reproduces the stored **272,369.92318368173 m** exactly. The file flags mark only two matched orbit records on that day, illustrating why event flags alone do not reproduce the old satellite-day screening.

The stored G01/G08 component RMS values reproduce within **1.39 × 10⁻¹⁷ m**. The public comparator's RAC differences agree with the legacy calculation within **2.24 × 10⁻⁹ m** across both dates. These are floating-point reproducibility results, not estimates of real orbit accuracy.

Separately, same-frame **IGS rapid − IGS final on 2026-03-04** matches 3,072 records and gives **5.19036 cm 3D RMS**. This checks real strict matching without an unexplained frame mismatch. It does not represent an orbit generated by customKF.

### Findings that matter for the next stages

1. **The old web comparator and the paper use different conventions.** The web velocity calculation is Earth-fixed; the paper uses a rotated position series before differentiation. The web URE applies 0.98 to radial variance, while the paper applies it to radial amplitude. The new canonical comparator uses the paper's URE and requires inertial velocity for RAC.
2. **The paper's rotation is an approximation, not a validated full IERS transform.** Its exact reproduction remains a separately labelled compatibility path. Proper dated time/EOP/frame handling still needs to be implemented and verified for propagation and export.
3. **NGA files say WGS84/G2296; these IGS files say IGc20.** The strict matcher refuses silent equivalence. The old raw comparison can be reproduced with the mismatch disclosed; it is not evidence that a realization transformation has been proved unnecessary.
4. **The historical benchmark is a study-wide target.** The 359-day stored target remains 3.43 /6.28 /7.17 cm component RMS, 10.13 cm 3D and 3.62 cm orbit-only URE. Stage 0 does not rerun that full study or demonstrate that our estimator meets it.
5. **Rapid availability is not yet certified.** Cached precise products are evaluation/development references. Their cache dates cannot prove historical delivery times, and they are not approved target-period estimation inputs for observation-derived POD. Future OBS/NAV and auxiliary-product ingestion must track input vintages at the chosen rapid cutoff.

No additional input is needed to close Stage 0. The next implementation milestone is **Stage 1: propagation and partial derivatives**, beginning with analytic orbit checks, step refinement and derivative consistency under the same guard. The acceptance gate remains refined integration agreement below 0.1 cm RMS /0.3 cm maximum on the export interval. The full estimator, station ingestion, spacecraft force model and any optional SLR work remain later stages.

---

<!-- original: STAGE1_RESULTS.md -->

## Stage 1 — propagation and partial derivatives

**Stage 1's numerical acceptance gates pass.** There is now a scaled DOP853 propagator, analytic force derivatives, a 6×6 state-transition matrix and four force-parameter sensitivity columns. This validates the numerical foundation for Stage 2; it does not yet reproduce an IGS orbit or constitute a complete GPS force model.

Validation date: **2026-09-06 UTC**. [Archived audit](E:/pythontests/customKF/validation/stage1/20260906T152340Z/audit.json) and [run provenance, resource measurements and source hashes](E:/pythontests/customKF/validation/stage1/20260906T152340Z/provenance.json). No software was installed, no data were downloaded and no changes were made to `autocomparesp3`.

### Implemented scope and conventions

The [propagator](E:/pythontests/customKF/customkf/propagation.py) uses the installed SciPy **1.13.1** DOP853 implementation. Its high-order method and dense interpolation are documented under `method`, while its local error controls are documented under `rtol, atol` in the [version-matched SciPy solve_ivp reference](https://docs.scipy.org/doc/scipy-1.13.1/reference/generated/scipy.integrate.solve_ivp.html). We validate global output error separately; specifying a small local tolerance alone is not an accuracy result.

The [test-force module](E:/pythontests/customKF/customkf/dynamics.py) implements central gravity, fixed-axis J2, prescribed fixed third bodies including the indirect acceleration of the origin, and three constant inertial acceleration parameters. It provides analytic position, velocity and parameter derivatives. The fixed third body has lunar-strength GM but a deliberately synthetic, stationary position. The J2 axis is the fixed inertial z axis. These choices give smooth, conservative, independently checkable problems without needing external ephemerides or Earth-orientation data.

The force parameters are absolute `[J2, ax, ay, az]`; the last three have units m/s². They are test parameters, **not an ECOM solar-radiation-pressure model**. Every augmented run integrates **66 equations**: 6 state components +36 transition elements +24 parameter-sensitivity elements. State-only propagation is available for independent finite differences.

| Convention | Stage 1 implementation |
|---|---|
| Public state | `[x, y, z, vx, vy, vz]` in metres and metres/second, in one inertial Cartesian frame |
| Time | Elapsed uniform coordinate seconds; forward and backward arcs supported. No UTC date arithmetic, GPST/TT conversion, EOP interpolation or terrestrial-frame transformation is implemented here. |
| State transition | `Phi[i,j] = ∂x_i(t)/∂x_j(t0)`, with identity initial condition |
| Parameter sensitivity | `S[i,k] = ∂x_i(t)/∂p_k`, holding the initial state fixed, with zero initial condition |
| Internal scaling | Position divided by 26,560,000 m; velocity divided by `sqrt(GM/26,560,000 m)`. Parameter scales are `[10^-3, 10^-7, 10^-7, 10^-7]`. Output states, transition and sensitivities are converted back to SI. |
| Output | Explicit strictly ordered epochs; DOP853 interpolates within integration steps. The acceptance grid contains 600 epochs over 24 h: 300-second export epochs plus off-grid interpolation probes, including both endpoints. |
| Supported arcs | Smooth dynamics, up to 48 h and 20,000 requested output epochs per call. Discontinuities or impulses must be split into separate arcs; automatic jump handling is not implemented. |
| Resource handling | Existing Windows guard; cooperative `STOP.json` checks during propagation; an additional right-hand-side evaluation budget. No partially completed solution is returned as success. |

Internally the variational equations are `Phi_dot = A Phi` and `S_dot = A S + B`, where `A` contains the acceleration derivatives and `B` contains its force-parameter derivatives. Both equations use the same scaled state and force evaluation as the physical orbit. There is no differentiation through the ODE solver and no autodiff dependency.

### Accuracy results

All values below are **numerical discrepancies on synthetic orbits**, not physical GPS orbit errors. The independent Kepler oracle solves the elliptic Kepler equation algebraically; the separate fixed-step RK4 oracle shares force expressions but uses independent integration code. The force expressions themselves also pass analytic equator/pole tests, potential-gradient checks and independent central differences.

| Check | Measured result | Gate |
|---|---:|---:|
| Circular orbit, 24 h, versus analytic Kepler | **0.479 µm RMS /1.264 µm max** position | <1 mm RMS /3 mm max |
| Eccentricity 0.1 orbit, 24 h, versus analytic Kepler | **0.139 µm RMS /0.414 µm max** | <1 mm RMS /3 mm max |
| Perturbed orbit, 120 s versus 30 s max step | **0.824 µm RMS /1.641 µm max** | <1 mm RMS /3 mm max |
| Perturbed orbit, 60 s versus 30 s max step | **1.200 µm RMS /2.632 µm max** | <1 mm RMS /3 mm max |
| Largest full-arc central-difference displacement discrepancy | **13.107 µm** | <100 µm |
| Largest derivative velocity-displacement discrepancy | **2.81 ×10⁻⁹ m/s** | <10⁻⁷ m/s |
| Independent RK4, 6 h, 5 s step, versus DOP853 | **0.388 µm** endpoint position | <3 mm |
| 24 h backward return from propagated endpoint | **0.153 µm** position | <3 mm |
| Scaled transition-matrix composition discrepancy | **2.06 ×10⁻¹²** | <10⁻⁸ |
| Scaled parameter-sensitivity composition discrepancy | **5.57 ×10⁻¹⁷** | <10⁻⁸ |
| Scaled symplectic identity discrepancy | **1.11 ×10⁻¹²** | <10⁻⁸ |

The two refined position differences are not monotonically smaller as the step shrinks: they are already at the micrometre numerical floor for these smooth cases. Their agreement passes the millimetre allocation; this is not evidence that arbitrary real force models can use those steps unchanged. The independent RK4 errors at 20/10/5-second steps were **221.68 /13.71 /0.388 µm**. The first reduction is a factor **16.17**, consistent with fourth-order convergence before the fine-step floor dominates.

Two-body energy and angular-momentum relative drift stayed below **5.6×10⁻¹⁵**; the synthetic perturbed model's energy drift was **5.7×10⁻¹⁵**. Conservation, reversibility and symplectic checks complement the independent comparisons; none alone establishes accuracy.

#### Derivative validation over the whole day

Each of the six initial-state columns and four force-parameter columns was checked by **positive and negative independent reintegration at three perturbation sizes**—60 full-day state-only integrations. The report stores the result of every column and size.

| Parameter type | Perturbations tested |
|---|---|
| Initial position | 100, 10, 1 m per component |
| Initial velocity | 0.01, 0.001, 0.0001 m/s per component |
| J2 | 10⁻⁶, 10⁻⁷, 10⁻⁸ |
| Constant acceleration | 10⁻⁸, 10⁻⁹, 10⁻¹⁰ m/s² per component |

The comparison is expressed as a **physical displacement residual**, `(x_plus − x_minus)/2 − derivative × perturbation`, avoiding a misleading norm mixing derivative units. The 13.107 µm maximum is across all columns, sizes and output epochs; it is not a uniform relative error bound on every derivative.

An additional combined one-sided perturbation test checks linearization itself. Reducing all initial-state and force perturbations by factors 1, 0.1 and 0.01 reduced position prediction RMS from **13.328 mm →0.131969 mm →0.000886 mm**. The approximate quadratic reduction is visible before the numerical floor. Independent half-arc integrations also reproduce the transition/sensitivity chain rule.

### Runtime and resource measurements

The complete scientific audit took **75.05 s wall time /71.00 CPU-seconds**, inside a 300-second guarded timeout. It ran on **one logical CPU, with one numerical-library thread**, the configured 10% CPU quota and a 2 GiB private-commit cap. Its peak sampled RSS was **66.33 MiB**, sampled private commit **49.08 MiB**, and minimum available system memory **12.69 GiB**. The guard and its policy were not changed in Stage 1.

One 24-hour augmented propagation took:

| Maximum step /settings | Right-hand-side evaluations | Measured runtime |
|---|---:|---:|
| 120 s /baseline | 10,112 | **0.71 s** |
| 60 s /fine | 18,950 | **1.31 s** |
| 30 s /finest | 36,320 | **2.53 s** |

The returned 600-epoch state/transition/sensitivity arrays occupy **321,600 bytes**. The many independent derivative runs explain why the audit takes longer than a single orbit. These timings cover simple test forces; they do not replace the planning estimates for an actual GPS force model, fitting iterations or network POD.

The final combined unit-test run passed **35 tests**: 21 existing Stage 0 numerical/parser tests and 14 new dynamics/propagation tests. It took **0.64 s** including worker startup, with peak sampled RSS **69.91 MiB**. Stage 0's native guard tests were not rerun because its code was unchanged; their successful archived verification remains linked from [Stage 0 results](E:/pythontests/customKF/STAGE0_RESULTS.md). RSS values are sampled peaks, not continuous physical-memory maxima; the guard's private-commit cap and memory-headroom checks retain their documented scope.

### Running and extending this stage

From `E:\pythontests\customKF`:

```powershell
python -m customkf.guard --timeout 60 -- unittest tests.test_comparison tests.test_sp3 tests.test_dynamics tests.test_propagation -v
python -m customkf.guard --timeout 300 -- customkf.audit_stage1
```

New runs write logs, resource accounting and the progressive `audit.json` under `runs/`. A failed scientific gate records its values with `status: fail` before raising. A guard timeout or worker exception is a failed/incomplete run even if an earlier individual check passed. The archived result above preserves the completed run and source hashes.

Baseline settings are `rtol=10^-11`, position absolute tolerance `10^-5 m`, velocity absolute tolerance `10^-9 m/s`, scaled partial tolerance `10^-12`, and maximum step 120 s. The audit tightens tolerances and reduces the maximum step to 60 and 30 s. Exact settings and synthetic force constants are recorded in the audit JSON. Small local tolerance is not a guarantee about exported coordinates.

**Next is Stage 2: dynamic fitting to IGS SP3.** Before interpreting a centimetre fit physically, that stage must add the dated time/frame/EOP path, a consistent Earth gravity model, real Sun/Moon ephemerides and radiation-pressure modelling. [IERS Conventions, Chapter 6, §6.1 and Table 6.1](https://iers-conventions.obspm.fr/content/chapter6/icc6.pdf) supplies the gravity modelling context; the full project choices remain in the [research report](E:/pythontests/customKF/GPS_POD_RESEARCH_REPORT.md). Reusing this numerical core does not remove those modelling requirements. No station OBS/NAV ingestion, SP3 fitting, ECOM, ambiguity estimation or optional SLR work was started in Stage 1.

---

<!-- original: STAGE2_RESULTS.md -->

## Stage 2 — dynamic fitting to GPS SP3

Validated 2026-09-06 on the existing Windows Python. **The Stage 2 development gate passes. Keep ECOM5 as the default.** The quiet G08 arc fits at 3.56 cm 3D RMS, with 3.64 cm on withheld interior epochs and 6.47 cm on the withheld end segment. G01 provides an eclipse diagnostic, with a materially worse endpoint.

This is a fit to IGS final positions. It establishes a working dynamic model and our own QR estimator; it does **not** establish independent observation-derived POD, rapid-latency operation, or equivalence to the 359-day NGA–IGS study. That study's 10.13 cm 3D baseline is an external-product comparison over far more data. Two fitted satellite-days are not comparable evidence.

### Measured results

All position metrics below are **3D RMS in cm**, with no Helmert transformation, mean subtraction, residual-dependent editing or clock adjustment. Runtime is guarded wall time, including interpreter startup, environment preparation and JIT compilation.

| Experiment | Training, 70 epochs | Withheld interior, 18 | Withheld end, 8 | Wall time (s) | Peak sampled RSS (MiB) |
|---|---:|---:|---:|---:|---:|
| G08_ECOM5 | 3.564 | 3.636 | 6.467 | 12.30 | 166.3 |
| G08_ECOM7 | 3.395 | 3.523 | 6.902 | 12.50 | 166.0 |
| G01_ECOM5 | 5.465 | 5.550 | 11.563 | 19.67 | 165.4 |
| G01_ECOM7 | 5.329 | 5.402 | 10.870 | 13.95 | 166.4 |
| G08_no_tides | 6.724 | 6.687 | 8.041 | 12.66 | 165.6 |

Seven parameters slightly improve the interior fit but worsen G08's endpoint. G01 improves modestly with seven parameters and still exceeds 10 cm at its endpoint. This one-day experiment does not justify making the larger model the default. Keep the seven-parameter option for subsequent multi-day tests.

The controlled tide ablation uses the same G08 positions, masks and fitting procedure. Adding nominal solid Earth tides reduces the withheld interior RMS from 6.687 to 3.636 cm (about 46%) and endpoint RMS from 8.041 to 6.467 cm. This is an empirical result for this arc and model; it neither isolates every physical tide effect nor substitutes for an independent implementation comparison.

![RAC residuals](E:/pythontests/customKF/validation/stage2/20260906T171235Z/residuals.png)

#### Component metrics for the default model

| Case / sample set | Radial RMS (cm) | Along-track RMS (cm) | Cross-track RMS (cm) | Orbit-only URE RMS (cm) |
|---|---:|---:|---:|---:|
| G08_ECOM5 / training | 1.997 | 0.918 | 2.806 | 2.002 |
| G08_ECOM5 / withheld_interior | 2.026 | 1.009 | 2.845 | 2.031 |
| G08_ECOM5 / withheld_end | 2.483 | 2.586 | 5.382 | 2.579 |
| G01_ECOM5 / training | 1.884 | 2.180 | 4.644 | 1.987 |
| G01_ECOM5 / withheld_interior | 1.825 | 2.498 | 4.607 | 1.939 |
| G01_ECOM5 / withheld_end | 1.392 | 11.260 | 2.231 | 2.133 |

URE follows the frozen amplitude convention: `sqrt((0.98 R)^2 + (A^2+C^2)/49)`. RAC uses the reference's inertial velocity, obtained for evaluation from a local nine-point derivative of its positions. The URE values contain no clock error and are not total SISRE.

### Exactly what was fitted and withheld

The pinned input is `IGS0OPSFIN_20262140000_01D_15M_ORB.SP3`: 2026-08-02, GPST, COM, IGc20. G08 and G01 each have 96 unflagged 15-minute positions from 00:00 through 23:45. The selection was inherited from Stage 0's quiet/eclipsing examples, before seeing these fitted residuals. G08 has no sampled shadow epochs; G01 has 8.

For indices 0–87, every fifth index congruent to 2 is withheld, leaving 70 training and 18 interior validation epochs. All eight indices 88–95 are withheld: 22:00–23:45. The last training epoch is 21:45, so the endpoint evaluation spans 15–120 minutes beyond the fitted interval. No neighbouring daily arc overlap was computed. The interior validation is a deterministic interpolation holdout on the same development day, not an unseen-day generalization test.

Only training positions enter the solve and its ten-point initial state interpolation. The six initial state components and five or seven constant SRP coefficients are estimated by unweighted Cartesian least squares. There are 210 scalar training measurements and 11 or 13 unknowns. No fitted accelerations per epoch, pseudo-observation priors, frame alignment or outlier removal are used. SP3 clock fields do not enter the fit.

### Estimator and numerical checks

`customkf/fitting.py` implements iterative, column-scaled, pivoted QR square-root batch least squares. It solves the rectangular design system without forming/inverting normal equations. SVD is used only to diagnose rank/conditioning; a deficient system is rejected. This is our own small batch estimator, not a sequential SRIF, EKF or UKF. No turnkey orbit-estimation software was installed or invoked.

The initial position/velocity scales are 100 m and 0.01 m/s; SRP columns use 1e-7 m/s². All four nominal fits are full rank. Trial steps use the same augmented integration/error norm as the objective, avoiding a state-only versus variational cost mismatch near penumbra. Ordinary stopping requires an RMS change below 10 µm. If line search cannot accept a step, convergence additionally requires a predicted full-step trajectory correction below 0.1 mm and RMS cost change below 10 µm. G01 ECOM5 stopped with a predicted correction of about 5.5 µm; the rejected trial changed its RMS by about 0.07 µm. A rejected material step is a failure.

Stage 2 uses DOP853 with a 120 s maximum step, rtol 1e-12, position atol 1e-7 m, velocity atol 1e-11 m/s and scaled-partial atol 1e-13. Refinement holds the fitted parameters fixed, halves the maximum step and tightens rtol to 3e-13; it independently uses state-only integration. These are observed numerical differences, not rigorous error bounds.

| Experiment | Refinement RMS (mm) | Refinement maximum (mm) |
|---|---:|---:|
| G08_ECOM5 | 0.000197 | 0.000338 |
| G01_ECOM5 | 0.273035 | 0.613103 |
| G08_ECOM7 | 0.000797 | 0.001633 |
| G01_ECOM7 | 0.176069 | 0.416713 |

The gate requires convergence, training and interior 3D RMS below 10 cm, refinement RMS below 1 mm and maximum below 3 mm. The endpoint is explicitly reported rather than silently folded into that gate. All four nominal fits pass; the larger eclipse endpoint remains a limitation.

**47 numerical/parser tests pass.** They include official ERFA rotation vectors, independent Horizons geometric Sun/Moon positions, synthetic Chebyshev records, GPST/TT/UTC and leap-offset checks, gravity normalization against analytic J2, force derivatives at independent perturbation sizes, algebraic trajectory recovery by the QR estimator, rank-deficiency rejection and SP3 export checks. The existing Stage 1 full-day audit also passes after generalizing the variational integrator to a variable number of force parameters.

For the real force model, a separate full-arc audit compares integrated variational predictions with independent plus/minus reintegrations for a combined perturbation in all six initial components and all five SRP coefficients, at two perturbation sizes, on both G08 and G01. The worst position discrepancy is **0.0428 mm**. This supplements, rather than replaces, individual force-column tests. The DE440 reader differs from the independent Horizons **DE441** vectors by 0.028 m for the Sun and 2.313 m for the Moon at the pinned check epoch; the test allows 10 m because the ephemerides differ.

### Force model, conventions and limits

| Component | Implemented scope / source |
|---|---|
| Static terrestrial gravity | Fully normalized, tide-free EGM2008 truncated at degree/order 12. Uses its own GM = 3.986004415e14 m³/s² and radius = 6,378,136.3 m. [ICGEM catalogue, EGM2008 row](https://icgem.gfz.de/tom_longtime). |
| Solid Earth tides | Nominal anelastic degree 2/3 response and induced degree 4 terms, full permanent component for tide-free input. Frequency-dependent corrections are omitted. [IERS Conventions 2010, Chapter 6, §6.2.1 equations 6.6–6.7/Table 6.3 and §6.2.2](https://iers-conventions.obspm.fr/content/chapter6/icc6.pdf). |
| Sun/Moon gravity | Direct-minus-indirect third-body acceleration, geometric positions from pinned DE440s. A restricted read-only DAF/SPK type-2 reader uses existing NumPy. [NAIF SPK specification, “Type 2: Chebyshev (position only)”](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/spk.html). |
| Time and orientation | Explicit GPST→TT/UTC/UT1, IAU 2006/2000A through installed ERFA, observed polar motion and dX/dY. EOP and body ephemerides are interpolated on bounded intervals; no network lookup or extrapolation during fitting. [ERFA official tests, `t_c2t06a`](https://raw.githubusercontent.com/liberfa/erfa/master/src/t_erfa_c.c). |
| Relativity | Earth Schwarzschild acceleration. No claim of complete relativistic frame/time-scale treatment. |
| SRP | ECOM5 and an ECOM2-style seven-parameter variant, inverse-square Sun-distance scaling, spherical-disc umbra/penumbra. D points satellite→Sun, Y is radial×D, B = D×Y. [Arnold et al. 2015, ECOM model development](https://doi.org/10.1007/s00190-015-0814-4). |

ECOM5 uses argument of latitude from the instantaneous ascending node. The seven-parameter variant uses argument relative to the Sun's projection in the orbital plane and adds twice-per-revolution D terms. Accordingly, B harmonic coefficient pairs are in different phase bases and should not be compared directly across those two options. A negative D0 points away from the Sun under our declared sign convention.

| Fit | D0 | Y0 | B0 | Bc1 | Bs1 | Dc2 | Ds2 | Scaled condition |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| G08_ECOM5 | -108.05303 | 0.00649 | -0.89298 | -1.83488 | -0.11509 | — | — | 1120.5 |
| G01_ECOM5 | -80.79584 | 0.78772 | 0.12746 | 0.89967 | -0.18809 | — | — | 3173.4 |
| G08_ECOM7 | -108.04064 | 0.00031 | -0.94238 | 1.85154 | -0.00814 | 0.18063 | 1.23799 | 2999.4 |
| G01_ECOM7 | -80.37019 | 0.78531 | 0.24156 | -0.71372 | -0.44201 | 1.79018 | -0.68771 | 4405.4 |

Acceleration coefficients are in **1e-9 m/s²**, normalized to 1 AU before eclipse attenuation. Condition numbers refer to the declared scaled design, not raw SI columns. Each archived `fit.json` also records the fitted initial state, every iteration and full residual statistics. We do not interpret these empirical coefficients as independently identified physical properties or report formal uncertainty from correlated SP3 pseudo-observations.

Omitted physics includes tide frequency corrections, ocean/pole tides, subdaily EOP tides, secular/seasonal gravity variation, Earth radiation, antenna thrust, satellite-specific yaw/box-wing and thermal behavior, and planetary third bodies beyond Sun/Moon. The force evaluator uses analytic central/third-body derivatives and centered differences of the much smaller remaining terms. This is a useful initial physical model with measured fit performance, not a full IGS analysis-centre implementation. In particular, an eclipse shadow factor does not validate GPS attitude transitions.

The frame is inherited from the IGc20 reference with no fitted realization transformation. The USNO EOP file is a snapshot downloaded in September; its August entries are observed values, not a certified record of what was available at the original rapid deadline. The use of IGS final training positions and this retrospective EOP snapshot is confined to Stage 2. It cannot certify the future rapid processing chain.

### Runtime, resources and artifacts

The four nominal fits take about 12–20 seconds each on this machine, at one logical CPU and one numerical-library thread. The five fit experiments peak at **166.4 MiB sampled RSS**, with at least **15.94 GiB system available memory** observed. The existing 2 GiB aggregate private-commit cap, 10% CPU quota, single-experiment lock, below-normal priority, timeout and memory-pressure watchdog remain enabled. All numerical validation runs are serial. These measurements describe tiny SP3 fits, not station-network POD runtime.

No software was installed. Reference data added about 34.8 MiB for DE440s, EOP and degree-12 gravity, plus small independent check transcripts. Sources and SHA-256 hashes are pinned in `data/stage2/manifest.json` and `check_vectors.json`.

The archive is [20260906T171235Z](E:/pythontests/customKF/validation/stage2/20260906T171235Z). It contains each fit's JSON, full-precision NPZ, SP3-c product, resource report, logs, source hashes, dependency versions, derivative audit, Stage 1 regression and artifact checks. Each SP3 is explicitly labelled as a dynamic fit, with **missing clocks and unknown accuracy**, COM positions and predicted-orbit flags for the eight withheld endpoint epochs. SP3 coordinates round to 1 mm; NPZ is authoritative for finer numerical checks. The maximum 3D export rounding across these products is 0.832 mm. Format reference: [IGS SP3-c, first header line and Position and Clock Record](https://files.igs.org/pub/data/format/sp3c.txt).

Reproduce all numerical checks and fits, without installing anything:

```powershell
python -m customkf.validate_stage2
```

This is a lightweight controller that launches guarded workers; do not put an outer guard around it. For one fit:

```powershell
python -m customkf.guard --timeout 180 -- customkf.run_stage2 --sat G08
python -m customkf.guard --timeout 180 -- customkf.run_stage2 --sat G01 --ecom 7
```

The next milestone is **Stage 3: fixed-orbit single-station PPP**, adding OBS/NAV ingestion and testing the observation model against known station coordinates. This Stage 2 implementation does not yet ingest station observations. No SLR dependency is introduced.

---

<!-- original: STAGE3_RESULTS.md -->

## Stage 3 — fixed-orbit GPS float PPP

**8 September follow-up:** [The KOUR investigation](E:/pythontests/customKF/KOUR_INVESTIGATION.md) compared three adjacent KOUR days, ABMF, and nearby KOUG. The particular 2 August burst is localized: at the same epoch G12 has +175.4 mm at KOUR and −6.0 mm at KOUG, 25.07 km away. KOUR's outside-window RMS is nearly unchanged across days. This favors a local episode, not a general satellite-product error or a blanket bad-station classification. The strict residual-quality gate remains open; I now recommend moving to Stage 4's numerical estimator audit with the quality exceptions explicitly retained. The remainder of this report records the original 7 September validation.

**Status: numerical validation and three-station coordinate gates passed; residual-quality gate remains open.** Updated 7 September 2026. The resumed validation passed all **69 tests**, all three station solves without next-day product padding, and the perturbed-start comparison. All numerical work ran serially under the unchanged RAM/CPU guard. KOUR retains a localized low-elevation phase-residual burst whose physical cause is unresolved; Stage 3 is not yet an unqualified observation-model acceptance.

The immediate recommendation is to investigate KOUR's localized structure and add a withheld date/another receiver manufacturer before claiming broad PPP robustness. We now have our own observation estimator, not an independent satellite-orbit product. Fixed IGS rapid satellite positions and clocks are inputs; estimating satellite dynamics from a network remains later work. Nothing here demonstrates the NGA–IGS orbit-comparison accuracy target. The frozen numerical evidence is in [validation.json](E:/pythontests/customKF/validation/stage3/20260907T165503Z/validation.json); the subsequent visual/native-record review is in [review.json](E:/pythontests/customKF/validation/stage3/20260907T165503Z/review.json).

### Recorded development results

Input day: **2 August 2026**, GPS day 2026/214. Each file contains 2,880 native 30-second epochs. The current solves retain **286 five-minute epochs, 00:00–23:45 GPST**, using only previous/current-day precise products. The last two five-minute observation epochs lack orbit bracketing and are excluded explicitly. No coordinate constraints or postfit residual clipping were used. Reference coordinates were propagated from the applicable IGc20 station solution to the observation date and used only for evaluation.

| Station | Receiver / antenna | East error | North error | Up error | IF phase RMS | Code RMS |
|---|---|---:|---:|---:|---:|---:|
| BRUX, Belgium | Septentrio POLARX5TR / JAVRINGANT_DM SCIS | −2.74 mm | −0.81 mm | +11.26 mm | 6.33 mm | 0.721 m |
| KOUR, French Guiana | Septentrio POLARX5TR / SEPCHOKE_B3E6 NONE | −0.40 mm | −1.04 mm | −4.60 mm | 14.52 mm | 0.781 m |
| HOB2, Australia | Septentrio POLARX5 / LEIAR25.R4 NONE | +1.79 mm | −1.43 mm | +3.67 mm | 10.65 mm | 0.911 m |

These are three physical receivers and three antenna/radome combinations, but **one receiver manufacturer and one development date**. They are not a withheld-date or receiver-manufacturer validation set. Agreement with IGc20 coordinates is also not independent of the broader IGS processing system supplying the fixed satellite products.

Current archived run reports:

- [BRUX](E:/pythontests/customKF/validation/stage3/20260907T165503Z/BRUX/ppp.json): 2,423 phase observations, 55 float ambiguities, one short-arc phase row excluded; maximum absolute phase residual 44.9 mm.
- [KOUR](E:/pythontests/customKF/validation/stage3/20260907T165503Z/KOUR/ppp.json): 2,875 phase observations, 40 ambiguities, no short-arc phase rows excluded; maximum residual 175.4 mm.
- [HOB2](E:/pythontests/customKF/validation/stage3/20260907T165503Z/HOB2/ppp.json): 2,522 phase observations, 65 ambiguities, no short-arc phase rows excluded; maximum residual 80.1 mm.
- [BRUX starting-position stress run](E:/pythontests/customKF/validation/stage3/20260907T165503Z/BRUX_perturbed/ppp.json): deliberately added **[+100, −70, +40] m** to the header XYZ. Three coordinate linearizations converged within **1 micrometre** of the nominal result (recorded numerical difference approximately 1 nanometre). This is a convergence-repeatability check, not nanometre physical accuracy.

The controller records dependencies, source hashes before and after its experiments, input manifests, guard measurements, logs, estimates, residual arrays and plots. The 6 September preliminary runs remain under `runs/`; the table above supersedes their numbers. No estimator source was changed during the resumed validation or the subsequent native-record review.

### Runtime and RAM

| Recorded experiment | Guarded wall time | Sampled peak worker RSS |
|---|---:|---:|
| BRUX, converged default | 15.64 s | 172.2 MiB |
| KOUR, converged default | 17.08 s | 184.8 MiB |
| HOB2, converged default | 16.39 s | 177.6 MiB |
| BRUX, three-pass perturbed start | 23.83 s | 176.7 MiB |

The eight controller workers used **102.78 seconds of summed elapsed run time**; the subsequent native-record audit took another **2.16 seconds**. Across the controller suite, sampled peak RSS was **184.8 MiB**, sampled private committed memory peaked at **188.0 MiB**, and available system memory stayed above **14.16 GiB**. These measurements describe the numerical workers, not all RAM consumed by Windows, disk cache, other applications or the desktop agent.

The policy remains **2 GiB aggregate worker private-commit limit, one logical CPU, one BLAS thread, 10% machine CPU quota, below-normal priority, one guarded experiment at a time**. Nothing in Stage 3 increases those limits. At validation launch, the guard requires its 2 GiB budget plus 8 GiB available headroom. [The recorded refusal](E:/pythontests/customKF/runs/20260907T011448Z-13115aa3/result.json) shows 8.12 GiB available versus 10.00 GiB required; no test worker was started. A later read-only check showed 7.90 GiB available. The limit was not relaxed to make the tests run.

The 7 September retry launched with sufficient memory and retained exactly the same policy. Use approximately **15–30 seconds per iterated station-day development solve** as the local pilot planning range; the serial suite requires about two minutes. These are not network-POD scaling measurements. Its default worker timeout is 180 seconds, with 120 seconds for unit tests and diagnostics. The downloaded Stage 3 data, decoded compressed copies, manifests and decoder archive occupy about **137.35 MiB on disk**, excluding the small project-local vendor directory and run archives.

### What the estimator now does

The experiment uses a small dense, column-scaled, pivoted **weighted QR batch least-squares solve**, with nonlinear coordinate relinearization. It does not form or invert a normal matrix. This is the numerical oracle intended for the later network implementation; it is not a sequential SRIF, EKF or UKF.

For each station, estimated parameters are:

- Three constant station coordinates, without an IGc20/header coordinate prior.
- One receiver clock per retained epoch; initial clocks come from the code data.
- Twenty-five hourly zenith-wet-delay knots, linearly interpolated, with a 3 cm constraint on each adjacent hourly difference.
- Two constant horizontal atmospheric-gradient coefficients.
- One float ionosphere-free carrier-phase ambiguity for each retained native tracking arc.

The ambiguity origin is shifted by the first phase-minus-code value for numerical scaling. This is not integer fixing or an ambiguity prior. Arcs with fewer than three retained phase samples are removed before the solve and counted; their code observations remain. No postfit observations are discarded.

The working observation model contains:

| Component | Implemented scope |
|---|---|
| Ingestion | Streaming GPS extraction from ordinary RINEX 2.11, supported 3.x, and 4.01 observations; GPS LNAV extraction from RINEX 3 mixed navigation |
| Signals | Explicit P(Y)-compatible ionosphere-free code pair; current stations use **C1W/C2W with L1C/L2W**. Unsupported code pairs fail rather than silently substituting C1C |
| Editing | Native 30-second loss-of-lock/half-cycle flags, event records, gaps, geometry-free jumps and Melbourne–Wübbena jumps; performed before five-minute decimation |
| Geometry | Iterated transmit time, inertial satellite interpolation and receiver rotation, geometric range and Shapiro delay; satellite eccentricity clock correction applied once |
| Antennas | Exact receiver antenna/radome type-mean absolute ANTEX calibration; valid GPS satellite calibration; L1/L2 offsets and angular variations; nominal IGS body axes and continuous phase wind-up |
| Atmosphere | First-order ionosphere-free combination; NMF dry/wet mapping, standard-pressure hydrostatic delay, estimated wet delay and gradients |
| Station motion | Header monument-to-antenna eccentricity, reduced solid-Earth tides, secular-pole tide, 11-constituent ocean loading |
| Reference evaluation | Active IGc20 coordinate solution plus velocity propagation; selected stations have no PSD entries in the pinned file. Unsupported PSD terms now cause an explicit failure |
| Numerical safeguards | Rank check, maximum 900 parameters, bounded design matrix, input hashes, finite values and no orbit/clock extrapolation |

Weights are engineering starting values: ionosphere-free code standard deviation **0.9 m /sin(elevation)** and phase **9 mm /sin(elevation)**, with a 10-degree elevation mask. They are not a fitted covariance model. No formal coordinate-accuracy claim is inferred from a small postfit residual or an inverse information matrix.

Relevant modules are [run_stage3.py](E:/pythontests/customKF/customkf/run_stage3.py), [square_root.py](E:/pythontests/customKF/customkf/square_root.py), [rinex.py](E:/pythontests/customKF/customkf/rinex.py), [preprocess.py](E:/pythontests/customKF/customkf/preprocess.py), [measurement.py](E:/pythontests/customKF/customkf/measurement.py), [antenna.py](E:/pythontests/customKF/customkf/antenna.py), and [station_models.py](E:/pythontests/customKF/customkf/station_models.py).

### Rapid-product timing correction

The initial development configuration supplied 1–3 August rapid orbits/clocks to the 2 August observation solve. This is convenient interpolation padding, but the **3 August daily rapid product would arrive after the intended 2 August rapid-product deadline**. It is therefore unsuitable as the default evidence for our latency goal.

The current default supplies only 1–2 August products. The 2 August SP3 has 96 epochs, from 00:00 to 23:45 GPST. The 23:50 and 23:55 observation epochs cannot be bracketed by that orbit file and are rejected explicitly. Near the end, interpolation uses the available one-sided local window. In the paired BRUX experiment, adding next-day padding changed the estimated coordinate by **0.202 mm in 3D**, including the effect of retaining the last two epochs. This does not isolate interpolation error alone. The start of the day uses preceding-day support for transmit times before midnight.

The following-day configuration remains available only as an explicit `--allow-next-day-products` diagnostic. Even the default is **not a certified historical rapid replay**: the EOP, coordinates, loading coefficients and antenna metadata are later snapshots. Product vintage/arrival manifests and full-day operational orbit delivery remain separate work.

### Residual diagnosis and model limits

KOUR requires particular attention. Its largest early residuals include G29 near 14.00 hours GPST at about 10 degrees elevation (−172 mm), G12 near 14.25 hours at about 14 degrees (+175 mm), and G24 around 13.83–14.17 hours at roughly 14–21 degrees (+97 to +130 mm). Several satellites have localized structure in the same time region. **The physical cause has not been established.** Calling it multipath, an ionospheric event, a cycle slip or a tropospheric event at this point would be speculation.

The completed diagnostics preserve all retained observations and report phase residuals against time/elevation, elevation-bin RMS, residuals scaled by the specified observation weights, and the largest changes between consecutive samples within a native arc. All three plots below were visually inspected. KOUR's largest departures are localized pulses rather than an obvious permanent offset in these sampled traces; that observation does not identify their physical cause or rule out an undetected slip.

| Station | Phase RMS, 10–20° elevation | Phase RMS, ≥30° elevation | Largest residual / assigned sigma | Rows above 4 sigma |
|---|---:|---:|---:|---:|
| BRUX | 11.36 mm | 2.56 mm | 1.07 | 0 |
| KOUR | 23.98 mm | 6.09 mm | 5.08 | 2 |
| HOB2 | 19.24 mm | 3.96 mm | 2.09 | 0 |

These are residuals divided by the assigned measurement sigma, without postfit-leverage normalization or a calibrated temporal-correlation model; they are diagnostics, not formal outlier probabilities. The two KOUR observations remain in the solution.

The additional native-record audit found no loss-of-lock, half-cycle flags or arc changes for G12/G24 during 13:30–14:30 GPST. G29 had two earlier gap/loss-of-lock events at 13:38:30 and 13:44:00, already handled by separate arcs. Maximum within-arc 30-second geometry-free changes were 32.9, 50.4 and 57.0 mm for G12/G24/G29 respectively. The native plots show substantial changing geometry-free phase, but those combinations contain effects that cancel in the ionosphere-free observable; they do not establish an ionospheric cause of the IF residual burst. **The native check narrows some hypotheses but does not close the residual-quality gate.**

![Retained phase residuals versus time and elevation](E:/pythontests/customKF/validation/stage3/20260907T165503Z/diagnostics/phase_residuals.png)

![KOUR localized residual structure](E:/pythontests/customKF/validation/stage3/20260907T165503Z/diagnostics/kour_detail.png)

![KOUR native tracking audit](E:/pythontests/customKF/validation/stage3/20260907T165503Z/native_tracking/kour_native_tracking.png)

The initial physical profile is intentionally limited:

- Solid-Earth tides use a reduced degree-2/3 model and an approximate frequency-dependent term, with geodetic local vertical. This is **not** the complete IERS displacement algorithm. The three published IERS test cases produced 3D differences of **2.045, 1.867 and 1.326 mm**. Their 20 mm test tolerance is an engineering bound, not IERS conformance; three vectors do not bound errors everywhere. The official routine describes its corrections under “Called” and provides the cases under “Test case.” [IERS DEHANTTIDEINEL](https://iers-conventions.obspm.fr/content/chapter7/software/dehanttideinel/DEHANTTIDEINEL.F).
- Ocean loading uses the 11 major constituents from the pinned FES2014b BLQ file, whose header states **CMC:NO**. It does not perform full minor-constituent/admittance expansion, nodal treatment or a centre-of-mass correction. The secular-pole model follows the revised convention rather than the older RTKLIB mean-pole expression. Full loading and pole-tide requirements are described in §§7.1.2 and 7.1.4 of [IERS Chapter 7](https://iers-conventions.obspm.fr/content/chapter7/icc7.pdf).
- Nominal attitude does not model satellite-block-specific eclipse or noon/midnight yaw turns. No claim of eclipse-season observation-model validation is made.
- Standard pressure/NMF and hourly wet delays can leave atmospheric structure. Higher-order ionosphere, atmospheric loading and subdaily Earth-orientation corrections are not part of this initial profile.
- Slip screening currently lacks Doppler consistency and a statistically calibrated robust Melbourne–Wübbena detector. Five-minute wind-up unwrapping also needs challenging-attitude validation.

The NMF/reduced-tide equations were checked against the primary [RTKLIB rtkcmn.c](https://raw.githubusercontent.com/tomojitakasu/RTKLIB/master/src/rtkcmn.c) functions `nmf`/`tropmapf` and [ppp.c](https://raw.githubusercontent.com/tomojitakasu/RTKLIB/master/src/ppp.c) functions `tide_pl`, `tide_solid` and `tide_oload`. Their license and attribution are retained in [THIRD_PARTY_NOTICES.md](E:/pythontests/customKF/THIRD_PARTY_NOTICES.md). RTKLIB's estimator is not used.

### Inputs and the decoder exception

The first ingestion audit used public NOAA ordinary RINEX 2 files for GODE, WES2 and GUUG. GODE supplied usable P1/P2/L1/L2 combinations; WES2 and GUUG lacked P1, and RINEX 2 obscures modern tracking-code identification. I did not substitute C1 into a precise P1/P2 clock convention without bias handling.

After discussing the software tradeoff and receiving the instruction to continue, the experiment acquired the official **GSI RNXCMP 4.2.0 Windows 64-bit decoder** in the project-local vendor directory. It only converts compact observation files to ordinary RINEX. No package, PATH, registry or system installation was changed; the estimator remains ours. [GSI RNXCMP distribution](https://terras.gsi.go.jp/ja/crx2rnx/RNXCMP_4.2.0_Windows_mingw_64bit.zip), [local license and provenance](E:/pythontests/customKF/vendor/rnxcmp-4.2.0/provenance.json).

The decoded BRUX/KOUR headers are RINEX **4.01**, HOB2 is **3.04**; this is why the reader was extended beyond the initially planned RINEX 3 scope. The original compact files and their decoded compressed copies are both retained with hashes. Observations, broadcast navigation and rapid products came from BKG's public IGS mirror. Coordinate/antenna files came from IGS; the loading table came from AIUB's BSWUSER54 reference-data directory. Sources and hashes are recorded in the [main manifest](E:/pythontests/customKF/data/stage3/manifest.json), [observation/decoder manifest](E:/pythontests/customKF/data/stage3/rinex3_manifest.json), and [support manifest](E:/pythontests/customKF/data/stage3/support_manifest.json). Existing Stage 2 DE440s and EOP files are reused and hash-checked.

The pinned IGS clock headers omit `TIME SYSTEM ID`; the experiment explicitly declares GPS time for this input profile rather than silently applying a generic UTC/GPS guess. This assumption must be revisited for another clock product. See the header record definition in [RINEX clock format 3.00, Table A16](https://files.igs.org/pub/data/format/rinex_clock300.txt).

### Acceptance checks and rerunning

The earlier [foundation archive](E:/pythontests/customKF/validation/stage3/20260906T175418Z/validation.json) passed 14 Stage 3 parsing/combination/geometry tests, the initial ingestion audit and a GODE code-only diagnostic. It predates the complete PPP estimator. The Stage 2 regression archive remains separate; it is not evidence that the new PPP corrections passed their tests.

The resumed suite passed **69 tests**: 47 earlier-stage numerical/parser tests, 14 Stage 3 foundation tests and eight additional model tests in [test_stage3_models.py](E:/pythontests/customKF/tests/test_stage3_models.py). The ingestion audit, three current-default PPP solutions, starting-position stress run, next-day comparison and diagnostics all completed successfully. To repeat them, with at least 10 GiB RAM available, launch the lightweight controller directly:

```powershell
C:\anaconda\python.exe -m customkf.validate_stage3
```

Every numerical worker is inside the native guard. Do not place this controller inside another guard. Logs, reports, residual arrays, plots, dependencies, source hashes and embedded input manifests are archived in a new `validation/stage3/` directory. The automated controller deliberately leaves `residual_review_pending`; the subsequent [review.json](E:/pythontests/customKF/validation/stage3/20260907T165503Z/review.json) now records completed visual/native inspection and **residual_gate_open**, preserving the original automated output. The native audit can be repeated with `customkf.guard --timeout 60 -- research.stage3_native_residual_audit <validation-directory>`.

For a single bounded current-default experiment:

```powershell
C:\anaconda\python.exe -m customkf.guard --timeout 180 -- customkf.run_stage3 --station BRUX
```

Remaining acceptance work: investigate KOUR's low-elevation transient without tuning to reference coordinates or silently clipping residuals. A bounded comparison of atmospheric temporal resolution is a reasonable next diagnostic, but a reduction in fitted residuals alone would not identify the cause; it should be checked on withheld epochs/date. Another receiver manufacturer should also follow before claiming broad PPP robustness. The tiny-network algebra can reuse this numerical oracle, but I recommend closing or quantitatively accepting the residual limitation before declaring Stage 3 complete and advancing the physical-model validation chain.

---

<!-- original: KOUR_INVESTIGATION.md -->

## KOUR adjacent-day and station-control investigation

8 September 2026. **The particular 2 August burst appears to be a KOUR-local episode in this three-day sample. Elevated low-elevation residuals are neither unique to KOUR nor confined to that day.** The controls argue against a dominant common satellite orbit/clock error, but do not identify an equipment fault or establish whether local atmosphere, multipath, tracking or our local observation model is responsible.

I would retain KOUR as a flagged stress case, not reject the station wholesale. I also would not change the estimator globally to make this one burst disappear. The numerical evidence is sufficient to proceed to the **Stage 4 tiny-network algebra audit**, while keeping explicit residual-quality exceptions open. That is a recommendation to advance a mathematical audit, not a declaration that the full observation-model quality gate or operational network QC is complete.

### Comparison design

The initial test set was KOUR on **1, 2 and 3 August 2026**, with ABMF in Guadeloupe as an additional low-latitude control on 2 August. The existing BRUX and HOB2 results supplied two more same-day controls. After inspecting those results, I added nearby **KOUG on 2 August**, a deliberately identified adaptive follow-up rather than a preselected independent confirmation set.

The physical model, signal pair, elevation mask, observation weights, wet-delay constraints and float-ambiguity estimator were unchanged. The only estimator changes parameterized the station/day, applied the selected day consistently to time origins/reference coordinates/troposphere seasonality, and saved azimuths for diagnostics. **The new KOUR 2 August run reproduced every retained baseline residual and the station coordinate exactly in the stored floating-point arrays.** All 69 existing numerical/parser/model tests passed after the date/station parameterization. KOUG was subsequently added to the station selection and exercised in its own guarded integration run.

All solves use previous/current-day IGS rapid orbits and clocks, without following-day product padding. The observation files contain 2,880 native 30-second epochs. Each solve retained 286 five-minute epochs through 23:45 GPST; two late epochs lack orbit bracketing. The already identified event window was frozen at **13:30–14:30 GPST** before examining the new days. Window statistics below are descriptive; this is not a randomized sample or a significance test. Five-minute sampling also limits exact day-to-day waveform comparisons.

No postfit clipping, station-coordinate prior, altered measurement weights, new software or external PPP solver was introduced. Short native tracking arcs and input-compatibility failures remain explicitly recorded.

### Results

| Station/date | Whole-day phase RMS | Maximum absolute phase residual | Phase RMS, 13:30–14:30 | Rows above 4 assigned sigmas | Horizontal error | Vertical error |
|---|---:|---:|---:|---:|---:|---:|
| KOUR, 1 Aug | 13.08 mm | 110.5 mm | 17.15 mm | 0 | 2.70 mm | −5.83 mm |
| **KOUR, 2 Aug** | **14.52 mm** | **175.4 mm** | **36.36 mm** | **2** | **1.12 mm** | **−4.60 mm** |
| KOUR, 3 Aug | 12.88 mm | 99.4 mm | 14.63 mm | 0 | 1.89 mm | −7.69 mm |
| ABMF, 2 Aug | 15.80 mm | 147.6 mm | 12.66 mm | 1 | 1.23 mm | +4.36 mm |
| KOUG, 2 Aug | 13.56 mm | 106.7 mm | 18.20 mm | 1 | 2.04 mm | −9.65 mm |
| BRUX, 2 Aug — previous control | 6.33 mm | 44.9 mm | 8.29 mm | 0 | 2.86 mm | +11.26 mm |
| HOB2, 2 Aug — previous control | 10.65 mm | 80.1 mm | 9.19 mm | 0 | 2.29 mm | +3.67 mm |

Every coordinate result meets the original 20 mm horizontal /50 mm vertical threshold against propagated IGc20 station coordinates. Those coordinates are used only for evaluation. Agreement with coordinates alone does not establish correct residual statistics or orbit-product accuracy.

Outside the fixed event window, KOUR's phase RMS was **12.85, 12.48 and 12.79 mm** across the three days. Thus the excess on 2 August is localized in time; outside that hour the day was comparable to its neighbours. Inside the hour, its 36.36 mm RMS was **2.12 times** the 1 August value and **2.49 times** the 3 August value. These comparisons keep all retained observations; the outside-window calculation is a diagnostic partition, not an edited solution.

KOUR's phase RMS above 30 degrees was particularly stable: **5.97, 6.09 and 6.15 mm**. Below 20 degrees it was **21.43, 23.98 and 21.88 mm**. ABMF and KOUG also showed larger low-elevation noise: **29.23 and 22.33 mm**, respectively. This is why calling KOUR generally unreliable would overstate the evidence. Our simple noise/atmosphere/attitude profile still has to accommodate a range of real station conditions.

The assigned-sigma ratios use the existing phase weight, 9 mm/sin(elevation). They are not studentized residuals or calibrated outlier probabilities. KOUG's largest ratio, **5.60**, occurred outside the KOUR event window and above 30 degrees; it must not disappear from the quality record simply because KOUG is useful as a control. ABMF's largest ratio was **4.06**. No such observations were removed.

![Adjacent days and added controls](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/comparison_final/station_day_residuals.png)

![Same KOUR satellites over three days](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/comparison_final/kour_three_days.png)

### The nearby station comparison

KOUG is **25.07 km** from KOUR by the pinned reference-coordinate separation. Both actual observation headers identify Septentrio POLARX5TR receivers with firmware 5.6.0, but their antennas differ: KOUR uses SEPCHOKE_B3E6 NONE, while KOUG uses LEIAR25.R3 LEIT. The current official station pages corroborate those identities under “Receiver - Firmware” and “Antenna - Radome.” [KOUR metadata](https://network.igs.org/KOUR00GUF), [KOUG metadata](https://network.igs.org/KOUG00GUF).

This gives a more useful common-satellite-product check than a distant station: the two sites have almost the same line of sight to a given GPS satellite, share the precise satellite products, and are estimated independently.

| Satellite / GPST | KOUR residual | KOUG residual at exactly the same epoch |
|---|---:|---:|
| G12, 14:15 | **+175.4 mm** | **−6.0 mm** |
| G24, 14:10 | **+130.3 mm** | **−4.3 mm** |
| G29, 14:05 — largest KOUR value with a retained KOUG match in the window | −88.9 mm | +46.2 mm |

The larger G29 KOUR departure at 14:00 lacks a retained KOUG counterpart; it is not used as an exact matched-epoch comparison. There were 13, 11 and 6 matching event-window samples for G12, G24 and G29 respectively.

**Inference:** the lack of matching G12/G24 excursions at KOUG weighs against a common satellite clock error, and against an orbit error dominating this localized burst. It favors an effect local to KOUR's observations or their modeling. This is not a proof: independent fitted receiver clocks, wet delays and ambiguities can redistribute errors, and two nearby receivers are not a clean external truth experiment. Receiver-family effects also remain possible because the controls did not successfully diversify manufacturers.

The earlier native KOUR audit already found no reported loss-of-lock/half-cycle flags for G12/G24 during the event. G29 had two prior gap/loss events that were already split into separate ambiguity arcs. The new controls do not justify retroactively declaring those flags the cause of the full burst.

![Same satellites at nearby stations](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/comparison_final/nearby_station_comparison.png)

### Selection, exclusions and latency limits

ABMF's actual file uses a Septentrio POLARX5 with TRM57971.00 NONE, consistent with the “Receiver - Firmware” and equipment-history sections of [IGS ABMF metadata](https://network.igs.org/ABMF00GLP). It adds an independent site and antenna, but not a new receiver manufacturer.

SALU was initially selected because its Trimble NETR9 would diversify the receiver family. Its GPS header supplies C1C/C2W but **no C1W**, and includes phase-shift metadata that our strict parser does not currently support. It was excluded for compatibility, not because its residuals were poor: **no SALU PPP solution was computed**. The original file remains pinned. Supporting that combination requires explicit bias/phase convention work; silently substituting C1C would change the experiment. The receiver identity is also documented in [IGS SALU metadata, equipment history](https://network.igs.org/SALU00BRA).

The public BKG directory listed the ABMF file with a **5 August 08:34** modification timestamp, later than the nominal target-day rapid deadline. A directory timestamp does not prove first availability—it may reflect replacement—but this archive cannot certify timely ABMF arrival. ABMF is a retrospective quality control here. KOUR/KOUG and all other inputs likewise lack a complete historical arrival/vintage audit. This study tests observation behavior, not operational rapid replay. [Saved BKG directory index](E:/pythontests/customKF/research/sources/stage3/bkg_2026214_index.html).

Only 26,185,534 bytes (**24.97 MiB**) of additional public reference/observation data were downloaded. Retaining original and decoded compressed copies brings the added input footprint to 91,513,034 bytes (**87.27 MiB**). Existing GSI CRX2RNX and the existing Windows Python environment were reused.

### Verification and reproducibility

The first comparison-report worker stopped while encountering SALU's unsupported phase-shift header. The station solutions had already completed successfully. The report code was fixed to record this input-compatibility failure explicitly, then rerun; the failed log and successful recovery are both retained. This changed no estimated station solution. KOUG was then added and solved independently, and the final comparison includes it.

Across downloads, decoding, tests, five station solves and diagnostic/recovery workers, summed guarded elapsed time was **157.58 seconds** and CPU time **90.56 seconds**. Peak sampled RSS was **185.5 MiB**, private committed memory **187.9 MiB**, and available system memory never fell below **11.08 GiB** during those workers. The **2 GiB cap, one logical CPU, one BLAS thread, 10% CPU quota and one-experiment concurrency policy remained unchanged**.

Evidence:

- [Final completion record](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/completion.json), including the retained reporting failure/recovery and adaptive KOUG extension.
- [Full numerical comparison](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/comparison_final/comparison.json), including exclusions, residual bins, peaks and exact baseline reproduction.
- [Initial campaign record and source hashes](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/campaign.json), whose failure status is deliberately preserved because its first report worker failed.
- [Final additional-data manifest](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/campaign_inputs_final.json) and [resource summary](E:/pythontests/customKF/validation/stage3/20260908T202847Z-kour/resource_summary.json).
- Source snapshots for the original parameterized solver, the KOUG extension and the final diagnostic are retained with their respective outputs. The earlier 7 September archive remains unchanged.

To repeat the current five-solve study, after the data are present:

```powershell
C:\anaconda\python.exe -m research.run_kour_campaign
```

This is a lightweight controller; it launches all numerical workers serially inside the guard. Do not wrap the controller in another guard. A single adjacent-day case can be repeated with:

```powershell
C:\anaconda\python.exe -m customkf.guard --timeout 180 -- customkf.run_stage3 --station KOUR --date 2026-08-03
```

### Recommendation

Treat **KOUR/2 August/approximately 13:30–14:30 GPST as a flagged station-time episode**, with the raw data and unedited solution retained. The three-day evidence supports localization, not a universal “bad station” label. Keep ABMF's and KOUG's other residual departures visible too.

I recommend proceeding to Stage 4's small-network estimator-equivalence work using the established controls, while making station-time quality flags an explicit requirement before a real network POD solve. Keep KOUR as a stress case. The strict residual-quality gate remains open, and the physical cause is still unresolved; I would not spend an unbounded investigation on naming the cause before doing the independent network algebra audit. Any later atmospheric-resolution or editing change should be evaluated on withheld data and raw orbit/overlap metrics, not accepted merely because it reduces these fitted residuals.

---

<!-- original: STAGE4_RESULTS.md -->

## Stage 4: eight-station square-root estimator audit

Completed 8 September 2026 local time; final archive 9 September UTC. **The linear-algebra gate passed.** Estimates, full formal covariance, clock-datum changes and deterministic event recovery agree. Independent satellite-orbit accuracy is not established, and Stage 3's residual-quality exceptions remain open.

Evidence: [validation summary](E:/pythontests/customKF/validation/stage4/20260909T012400Z/validation.json), [detailed network report](E:/pythontests/customKF/validation/stage4/20260909T012400Z/network/stage4.json), [77-test log](E:/pythontests/customKF/validation/stage4/20260909T012400Z/unit_tests/stderr.log), and [estimates, full covariance and residual arrays](E:/pythontests/customKF/validation/stage4/20260909T012400Z/network/real_network.npz). The archive includes source snapshots, dependency versions, input manifests, SHA-256 hashes and guard logs.

### Fixture and scope

Real GPS observations from **BRUX, HOB2, KOUR, ABMF, KOUG, DJIG, NNOR and MAS1**, on **2 August 2026, 12:00–12:55 GPST**, sampled at 300 seconds. Native 30-second observations feed ambiguity-arc bookkeeping before decimation. The window was selected before fitting and does not include the previously investigated 13:30–14:30 KOUR episode.
8
| Quantity | Count |
|---|---:|
| Epochs / satellites appearing in the window | 12 / 29 |
| Station–satellite links / code observations | 879 / 879 |
| Retained phase observations | 872 |
| Phase rows excluded before fitting: arcs shorter than 3 selected samples | 7 |
| Prior/continuity equations | 198 |
| Total equations / unknowns | 1,949 / 658 |
| Orbit initial-state corrections | 174: six per satellite |
| Wet delays / float ambiguities | 16 / 83 |
| Epoch clock corrections eliminated | 385 |
| Retained unknowns / projected equations | 273 / 1,564 |

Station coordinates are fixed to their propagated IGc20 reference solutions; EOP are fixed. Each epoch's receiver–satellite graph must be connected. One receiver clock correction is fixed exactly to zero per epoch: BRUX by default, HOB2 for the datum-change test. Corrections refer to nominal precise satellite clocks and code-derived receiver clock seeds; the physical reference receiver clock is not assumed to be zero.

The nominal trajectory and satellite clocks remain IGS rapid products. Six-state orbit-correction bases use the existing Stage 2 variational propagator, starting at 11:59:59 GPST, with zero empirical force coefficients. **The SP3 nominal trajectory need not equal the integrated orbit, and nonlinear observation corrections are frozen during fitting.** This is a linear estimator fixture, not a dynamically closed POD solution. No SP3 product is emitted.

The fixture reuses Stage 3 signal combinations, antenna/wind-up, reduced loading, troposphere and navigation-health checks. It fixes station coordinates, uses two wet-delay knots and omits gradient parameters. Weights remain 0.9/sin(elevation) metres for code and 0.009/sin(elevation) metres for phase, with a 10-degree mask. There is no postfit clipping. All eight selected receivers are Septentrio models; this does not add manufacturer diversity.

### Numerical evidence

| Check | Measured result | Gate |
|---|---:|---:|
| Real dense vs eliminated measurement predictions, maximum difference | 3.174 × 10⁻¹² m | <1 × 10⁻⁶ m |
| Estimates: maximum difference / formal parameter sigma | 1.418 × 10⁻¹¹ | <1 × 10⁻⁷ |
| Full covariance: maximum difference / corresponding sigma product | 3.979 × 10⁻¹² | <1 × 10⁻⁷ |
| Covariance relative Frobenius difference | 1.018 × 10⁻¹² | Diagnostic |
| BRUX→HOB2 datum: maximum measurement difference after transformation | 1.773 × 10⁻¹² m | <1 × 10⁻⁶ m |
| Datum change: normalized covariance difference | 3.985 × 10⁻¹² | <1 × 10⁻⁷ |
| Transformed design vs original design | Exactly zero difference | <1 × 10⁻¹² |
| Noise-free event recovery: maximum clock/ambiguity error | 3.241 × 10⁻¹¹ m | <1 × 10⁻⁶ m |

These tiny differences measure arithmetic equivalence of solutions to the same equations, not physical accuracy. The existing Stage 3 QR oracle also passes the agreement check. The first pilot reported a 1.328 × 10⁻⁹ maximum including prior equations; the final report separates measurement rows because velocity-prior equations have different units. Estimates and covariances did not change.

The event case injects a **+37 m receiver-clock step**, **−12 m satellite-clock step**, and **one L1 cycle**, equivalent to **+0.484435889 m** in the ionosphere-free ambiguity, at 12:30 GPST. The existing geometry-free detector first locates an unflagged one-cycle step on an ideal native 30-second observable sequence. That breakpoint splits the continuous HOB2–G08 network ambiguity. The solver then recovers the injected clock and ambiguity parameters from synthetic linear observations using the real geometry. This is not a noisy-field detection-probability or false-alarm study.

Eight new tests check independent SVD estimates/covariance, analytic cross-epoch covariance, mixed units, row/block ordering, missing clock datum, unobservable retained parameters, disconnected graphs and invalid inputs/dimensions. The prior 69 numerical/parser tests also pass. The rank test retains pre-projection column scales so that roundoff in a projected null direction cannot be rescaled into apparent observability.

### What elimination preserves

For whitened epoch equations `y_i = G_i g + L_i l_i + error`, QR of `L_i` leaves projected equations for retained parameters `g`. Back-substitution recovers `l_i = d_i + B_i g`. Then:

- `Cov(l_i,g) = B_i Cov(g)`.
- For different epochs, `Cov(l_i,l_j) = B_i Cov(g) B_jᵀ`.
- A local diagonal block also includes its conditional triangular-solve covariance.

The implementation recovers every block. Omitting cross terms would invalidate uncertainties for clock differences and datum changes even if estimates looked correct. Covariance is conditional on the supplied sigmas, priors and exact datum, without residual-variance rescaling.

This is batch square-root least squares with epoch-local elimination. It has no temporal prediction/update recursion; it is not an EKF, UKF or sequential SRIF. Ambiguities remain in the retained solve. Full epoch Q matrices and full covariance are deliberately materialized for this bounded audit; they are not the eventual large-network storage design.

Primary references checked 8 September 2026: [GROOPS network cookbook, “GNSS processing”](https://groops-devs.github.io/groops/html/cookbook.gnssNetwork.html) describes eliminating epoch parameters and reconstructing them after solving to reduce memory; “Preprocessing: Orbit integration” describes integration and variational equations. This supports the architecture, not an exact match to an analysis centre's estimator. [SciPy 1.13.1 QR documentation, “Parameters” and “Notes”](https://docs.scipy.org/doc/scipy-1.13.1/reference/generated/scipy.linalg.qr.html) documents the installed factorization interface. Elimination and covariance assembly are our code; SciPy supplies QR and triangular solves.

### Prior dependence prevents an orbit-accuracy claim

Zero-centred orbit-correction priors use **100 m position / 0.1 m/s velocity sigmas**. Wet delays use 0.3 m sigmas and a 0.03 m knot-difference constraint. Both solvers receive identical priors.

Loosening the orbit sigmas tenfold to **1,000 m / 1 m/s** changes initial-position components by **76.62 m RMS**, with a **518.85 m maximum**. Five satellites—G18, G24, G26, G28 and G31—appear at only one station over the window. The short arc, uneven network and flexible nuisance parameters leave dependencies that the priors resolve numerically.

Postfit phase RMS ranges from **2.70 to 10.05 mm**, with no retained residual exceeding four assigned sigmas. Small residuals do not overcome that measured prior dependence. These are formal, constrained uncertainties, not calibrated physical orbit uncertainties. The original KOUR quality exceptions remain relevant outside this short window.

### Resources and reproduction

| Final validation measurement | Result |
|---|---:|
| 77-test worker | 14.98 s |
| Network/event/datum/prior worker | 17.91 s |
| Total guarded worker elapsed time | **32.89 s** |
| Peak sampled RSS / Windows peak job private commit | **232.6 / 204.3 MiB** |
| Minimum system available memory | **9.90 GiB** |
| Dense estimate + covariance solve | 0.161 s |
| Eliminated estimate + covariance solve | 0.039 s |
| Dense design / full covariance arrays | 9.78 / 3.30 MiB |

An earlier complete run took 18.64 seconds with 227.4 MiB sampled RSS and 12.70 GiB minimum available memory. Other system activity and startup affect wall time. The final small-case factorization ratio is about 4.2×; the earlier run was about 3.1×. These timings include covariance formation, and the eliminated call includes projection; they exclude dense-design assembly. They do not establish full-day POD scaling.

Every worker retained the **2 GiB private-memory cap, one logical CPU, one library thread, 10% CPU hard quota and 8 GiB available-memory reserve**. The 10 GiB launch check and pressure watchdog were unchanged. Jobs run serially. No package, software installation or resource-policy change was made.

Three new public station files required **17,062,675 download bytes (16.27 MiB)**. Originals plus compressed decoded observations occupy **68,298,599 bytes (65.13 MiB)**. Acquisition/decoding took 39.25 seconds separately, using the previously authorized decoder. URLs and hashes are in the [input manifest](E:/pythontests/customKF/data/stage3/stage4_manifest.json). Other files were reused locally. Metadata/EOP and arrival histories remain retrospective, not certified rapid-deadline vintages. No next-day orbit/clock padding is used.

Run from the project directory with the existing Windows Python:

```powershell
C:\anaconda\python.exe -m customkf.validate_stage4
```

Run the controller directly, without an outer guard. It performs no downloads, preserves failed runs and archives source hashes. Acquisition is separate: `python -m customkf.guard --timeout 240 -- customkf.prepare_stage4`.

The next implementation boundary is a **dynamically consistent, iterated observation-based orbit solve**, starting with bounded integration tests before the planned 25–30-station daily float POD. An IGS orbit may initialize the iteration, but must cease to supply an independently corrected nominal trajectory or an accuracy-setting constraint. Check nonlinear derivative closure, convergence, datum and prior sensitivity before interpreting the SP3 comparison. Larger networks need blocked accumulation and selective covariance, not an increase of this audit's 900-parameter ceiling.

---

<!-- original: STAGE5_RESULTS.md -->

## Stage 5a: nonlinear dynamics and observation integration

**9 September 2026: the primary nonlinear integration checks passed; the weak-prior
convergence and physical accuracy gates did not.** The baseline is **158.36 m raw
3D RMS from IGS rapid**, not close to the planned 20 cm development target or
10.13 cm study benchmark. Small phase residuals must not be read as orbit quality.

This is a bounded checkpoint within Stage 5, not the planned daily 25-30-station
constellation POD acceptance. The eight-station fixture now estimates initial
orbital states from station observations while reintegrating its own nominal
trajectories and recomputing the corrected observation model. IGS precise orbit
and clock products are absent from the estimator inputs. Full Stage 5 accuracy,
prior independence, scaling and rapid-input-vintage gates remain open.

### Model and decisions

The fixture covers 2 August 2026, 12:00-12:55 GPST, at five-minute solve spacing:
BRUX, HOB2, KOUR, ABMF, KOUG, DJIG, NNOR and MAS1. Native 30-second observations
are tracked before decimation. There are 879 code observations and 872 retained
phase observations, 29 satellites, 658 parameters and 273 retained parameters
after eliminating epoch clocks. Seven short-arc phase observations are excluded
by the predeclared minimum length, with no postfit clipping. G13 is rejected
because no healthy, past initialization record meets the four-hour age bound.

- Six initial-state components per satellite; fixed ECOM5 coefficients
  `[-1e-7, 0, 0, 0, 0] m/s^2`. The 55-minute arc is intentionally not used to
  estimate additional weakly observed SRP parameters.
- Two wet-delay knots per station, float ambiguity per supported native arc,
  satellite and receiver clocks per solve epoch, exact BRUX clock datum.
- Station coordinates, EOP, station displacements at nominal observation tags,
  weights and observation selection are fixed. The Stage 3 reduced physical
  profile and its known quality limitations remain.
- Orbit priors have 1,000 m position /1 m/s velocity sigma; wet knots have 0.3 m
  sigma and 0.03 m difference sigma. Their centers remain fixed during nonlinear
  iteration and start perturbations. These are increment equations targeting
  the original prior, not new zero-step priors reset each iteration.
- Every trial integrates current states with the Stage 2 force model. Position
  and velocity are the value and derivative of one Hermite curve; state-transition
  interpolation uses the corresponding position and velocity partials.
- Corrected observation terms are recomputed: implicit transmit time, Earth
  rotation, relativistic satellite clock, Shapiro delay, antenna offsets/PCV,
  troposphere mapping, and wind-up aligned to the same continuous branch.
- Analytic implicit-light-time range and broadcast-clock derivatives avoid
  subtracting two ~20 Mm observables. Small correction terms are differenced on
  tangent trajectories. Independent plus/minus *reintegrations* audit that Jacobian.

GPS LNAV user equations initialize an approximate orbit and nominal clock
polynomial. Broadcast coordinates refer to the antenna phase centre, whereas
our dynamic observation model applies ANTEX corrections to an estimated centre
of mass. The unconverted navigation state is therefore only an approximate
seed/broad prior center, not a precise COM reference. Explicit conversion is
required before tighter broadcast priors or precise initialization comparisons.
See ESA Navipedia, [GPS and Galileo Satellite Coordinates Computation, coordinate
algorithm](https://gssc.esa.int/navipedia/index.php/GPS_and_Galileo_Satellite_Coordinates_Computation)
and [Satellite Antenna Phase Centre, opening reference-point definition](https://gssc.esa.int/navipedia/index.php/Satellite_Antenna_Phase_Centre),
checked 9 September 2026. These support conventions, not customKF performance.

### Verified numerical results

| Check | Result |
|---|---:|
| Cumulative unit suite | 85 passed |
| Real-force corrected-observation derivative displacement residual | 7.93 nm max across G01/G08/G12 and two perturbation scales |
| Receiver-clock derivative displacement residual, +/-100 m | 0.104 micrometre max |
| Hermite grid refinement, 15 to 7.5 s | 1.63 micrometres max position difference |
| Real-data objective, including priors | 241,304,511.395 to 223.573638 |
| Real-data iterations | 3, all full steps accepted |
| Final initial-state step indicator | 0.2776 mm |
| Code / phase RMS | 0.763293 m /7.162175 mm |
| Real versus perturbed-start trajectory difference | 0.1817 mm maximum over 348 stored satellite-epochs |
| Synthetic orbit recovery | 0.2277 mm maximum at three sampled times per satellite |
| Synthetic observation recovery | 0.1341 micrometre maximum |

The step indicator is `max_sat(norm(delta_r0) + 3320 norm(delta_v0))`.
It is expressed in metres but is not a mathematically proved maximum over the
integrated trajectory. Convergence also requires a small objective change and
an accepted trial; direct trajectory agreement from different starts is a
separate check. Numerical discrepancies are not physical GPS accuracy.

### External comparison and prior stress

The separate evaluator uses **116 exact common satellite-epochs**: 29 GPS
satellites at 12:00, 12:15, 12:30 and 12:45 GPST. Reference positions are native
IGS rapid SP3 samples; only the inertial reference velocity for RAC is derived
from interpolation of inertially rotated reference positions. Both station
datum and reference are IGc20. Comparison is COM, candidate minus reference,
without Helmert alignment, per-satellite demeaning or residual screening. No
reference samples in this common set were flagged/excluded. No SP3 quantization
is added to the candidate; its full-precision integrated NPZ states are used.

| Raw metric | Baseline converged fit | Last accepted weak-prior iterate (not converged) |
|---|---:|---:|
| Radial RMS | 100.898 m | 681.269 m |
| Along-track RMS | 96.223 m | 300.823 m |
| Cross-track RMS | 75.082 m | 523.102 m |
| 3D RMS | **158.356 m** | **910.086 m** |
| Orbit-only URE RMS, frozen amplitude convention | 100.406 m | 673.186 m |
| Phase residual RMS | 7.162 mm | 7.102 mm |
| Weighted objective with respective priors | 223.573638 | 221.719402 |

The tenfold weaker orbit prior changes the stored trajectories by **879.678 m
3D RMS and 5,136.070 m maximum** over 348 output samples. That comparison is
between final stored iterates, **not two proven stationary solutions**. The weak
case makes six accepted updates, then rejects all four line-search fractions
on its seventh attempt; its remaining step indicator is 23.57 mm. The scientific
convergence gate stays open, despite the worker exiting normally within 278.22 s.

This diagnoses severe sensitivity under the current short-arc model; it does
not isolate all causes of the 158 m error or establish that network expansion
alone will fix it. The operational force, observation, datum and bias conventions
still require validation. The weak-prior score was not used to tune the estimator.

The noise-free case uses the same physical model, real network geometry and
prior centers equal to truth. All satellite starting states are perturbed by
`[100,-70,40] m` and `[0.01,-0.02,0.015] m/s`. Known nuisance parameters include
a +37 m HOB2 clock at epoch 6, -12 m G08 clock at epoch 6 and +0.484435889 m on
one float ambiguity. This tests nonlinear recovery, not independent physical
model validity or noisy cycle-slip detection. Real-start perturbation uses the
same offsets without moving the prior centers.

### Development failures retained

- `runs/20260909T015550Z-7d9cd7f1`: expired frozen broadcast clock record rejected.
  The corrected code selects a healthy age-valid record at each transmit time;
  the age limit was not relaxed.
- `runs/20260909T015811Z-78e17f87`: finite differences of complete observables
  reduced the cost but stalled at centimetre-scale updates. It remains an open
  numerical gate in that original run. The analytic-range/small-correction
  Jacobian resolved this in subsequent runs without relaxing convergence.
- `runs/20260909T020529Z-9dcd97e9`: first converged hybrid-Jacobian pilot,
  105.11 s, 185.97 MiB sampled RSS. The later archived campaign adds start,
  synthetic, prior and independent comparison checks.
- `validation/stage5/20260909T200136Z/validation.json` retains `status: failed`
  because the original controller required the weak-prior stress to converge.
  The subsequent review separates primary integration acceptance from that
  still-open stress gate; it does not relabel the weak run as converged.
- `review-20260909T201326Z` within that campaign retains the first post-review
  evaluator's frame-check failure. Inspection verified the SP3 header is
  **IGc20**, matching the fixed station datum. The corrected evaluator enforces
  that exact label. It also omits a misleading raw APC-broadcast/COM comparison.

### Final evidence and resource measurements

Primary archive: `validation/stage5/20260909T200136Z/`. Final review:
`review-20260909T201401Z/review.json`; final external scores:
`review-20260909T201401Z/evaluation/evaluation.json` and `comparison.npz`.
The review verifies that numerical estimator/force/observation sources and input
manifests are unchanged from the original campaign. It archives updated evaluator,
controller and strengthened unit checks, then reruns the 85-test suite and
post-fit comparison. Original source snapshots, failures and fit arrays remain.

| Guarded workload | Elapsed seconds |
|---|---:|
| Baseline / perturbed-start solve | 101.70 /102.09 |
| Noise-free recovery | 113.30 |
| Weak-prior stress | 278.22 |
| Primary campaign plus successful review | 633.45 |

That 10.56-minute sum excludes earlier exploratory attempts and the first
review's frame-check failure. Peak sampled RSS was **190.63 MiB**, peak Windows
job private commitment **166.64 MiB**, and minimum observed system-available RAM
**12.67 GiB**. All numerical workers used one logical CPU/library thread, a 10%
machine CPU hard quota, 2 GiB private-memory limit and 8 GiB reserve. These are
small-case measurements, not a daily-network forecast.

### Reproduction and remaining scope

`customkf.validate_stage5` launches serial guarded workers and archives source
snapshots, input hashes, JSON/NPZ outputs, tests and resource records under
`validation/stage5/`. Run directly with `C:\anaconda\python.exe -m customkf.validate_stage5`;
do not wrap the controller in another guard. Individual pilot runs use
`C:\anaconda\python.exe -m customkf.guard --timeout 300 -- customkf.stage5_pilot --mode real`.
Other modes are `perturbed`, `synthetic`, and `weak-prior`.

The estimator's file-open audit hook rejects named SP3/CLK access. A separate
post-fit evaluator reads the completed immutable estimates and IGS rapid
reference; its score is never fed back into estimation. Dated EOP, coordinates,
antenna and loading inputs remain retrospective development snapshots. Past
navigation toe/toc checks do not certify actual historical dissemination times.

Next: implement bounded accumulation/selective covariance before increasing
matrix size, make broadcast-to-COM initialization explicit, expand arc length
and network geometry, estimate the warranted SRP terms, and demonstrate prior
independence and raw external agreement. The current full-Q/full-covariance
reference solver remains capped at 900 parameters; its limits must not simply
be raised to accommodate daily processing. No new software was installed and
the CPU, memory, reserve and scratch limits remain unchanged.

---

<!-- original: STAGE5_ATTRIBUTION.md -->

## Stage 5a error attribution — 9 September 2026

Completed 10 September UTC / 9 September local. These are bounded diagnostic
results, not an independent orbit-accuracy or rapid-production acceptance.
The shareable PDF and its source/manifest have deliberately not been updated.

### Decision

The 158.36 m result is chiefly evidence that this small, short-arc observation
problem permits large orbit errors while fitting phase closely. An actual
broadcast initialization mistake also existed, but correcting it barely changes
the final error. Do not attempt to reach the IGS target simply by tuning the
optimizer, tightening orbit priors, or adding nearby stations indiscriminately.
Next, improve geographic coverage and continuous time coverage, while preserving
the corrected seed convention and the resource limits. Full Stage 5 remains open.

### Same-data correction experiment

All scores below use the same 29 GPS satellites and 116 exact common samples
(12:00, 12:15, 12:30 and 12:45 GPST, 2 August 2026). They are raw inertial RAC
differences against IGS rapid, without Helmert alignment. The fitted observation
arc covers 12:00–12:55 at 300-second solve spacing, using eight stations,
879 code observations and 872 phase observations. The reference is evaluator
input only: the estimator's precise-product file-access prohibition remained on.

| Quantity | Original | Corrected orbit initialization |
|---|---:|---:|
| Integrated starting trajectory, 3D RMS | 27.401 m | **1.200 m** |
| Fitted trajectory, 3D RMS | 158.356 m | **156.809 m** |
| Fitted radial RMS | 100.898 m | 100.109 m |
| Fitted along-track RMS | 96.223 m | 96.494 m |
| Fitted cross-track RMS | 75.082 m | 72.500 m |
| Phase residual RMS | 7.162175 mm | 7.162061 mm |

The corrected fit converged in three iterations, with a final trajectory-step
bound of 0.194 mm and code residual RMS of 0.7633 m. Small postfit residuals and
successful numerical convergence plainly do not establish accurate orbits here.

The original selector required a past clock reference time and allowed four
hours of age. Five satellites (G07, G12, G14, G24 and G26) therefore started from
records with toe/toc 14,390 seconds old. Their starting position differences
were approximately 28–58 m. GPS reference time is a curve-fit reference, not a
record receipt time: nominal four-hour fits are centred on their reference
epoch, and negative reference-time offsets are normal. Offset reference times
and extended fit intervals need additional policies. See
[IS-GPS-200N, section 20.3.4.5 and Table 20-XIII, printed pages 135–138](https://archive.gps.gov/technical/icwg/IS-GPS-200N.pdf).

The new `select_fit_record` implements a deliberately narrow profile: healthy,
hour-aligned, matching toe/toc, explicit four-hour fit, within two hours of toe,
and a separately supplied data cutoff. Tests cover negative reference offsets,
fit boundaries, health/cutoff rejection and GPS-week continuity. Initial states
also now subtract the nominal ANTEX ionosphere-free satellite antenna offset,
including its effect on velocity. The axes and sign have an independent analytic
test. See [ESA Navipedia, Satellite Antenna Phase Centre, equations (1)–(6)](https://gssc.esa.int/navipedia/index.php/Satellite_Antenna_Phase_Centre).
This ANTEX/nominal-yaw conversion is not an independent certification of the
broadcast control segment's actual antenna reference or spacecraft attitude.

For this paired experiment, observation rows, weights, satellites, fixed force
coefficients, original clock polynomials and prior **sigmas** were unchanged.
Orbit prior **centres** follow the corrected initial states. Thus it measures
the combined initialization/prior-centre convention correction, not an isolated
optimizer starting-guess perturbation. ECOM5 remains fixed at
`[-1e-7, 0, 0, 0, 0]`; orbit prior sigmas remain 1000 m and 1 m/s.

Complete navigation applicability is still open. An attempted simultaneous
clock-policy replacement correctly stopped: G04 lacks a noon record, and its
14:00 reference record exceeds the deliberately conservative 12:55:10 cutoff.
The follow-up changes only orbit initialization to avoid changing the comparison
sample or silently extending a fit interval. Zero transmission-time fields do
not prove historical receipt. Neither this cutoff nor the retrospective EOP and
station products establish rapid-deadline input availability. The legacy
`select_record` remains explicitly labelled and retained for reproducing the
original pilot; the current work is not a full production navigation repair.

### Error concentration and controlled noise

Four satellites account for **83.02% of the original squared orbit error**:

| Satellite | Original 3D RMS | Corrected-fit 3D RMS | Observing stations |
|---|---:|---:|---|
| G05 | 526.253 m | 525.618 m | ABMF, KOUR, KOUG |
| G12 | 378.158 m | 372.226 m | ABMF, KOUR, KOUG |
| G22 | 341.231 m | 341.331 m | ABMF, KOUR, KOUG |
| G20 | 259.528 m | 259.756 m | ABMF, KOUR, KOUG |

These are three stations in a limited geographic region, not three widely
separated viewing directions. The estimated epoch satellite clocks and float
arc ambiguities can absorb much of the range information shared by nearby
receivers. A 55-minute arc provides limited independent information about six
initial-state parameters per satellite. Some satellites observed at only one
station remain close to their starting orbit because the priors retain it;
that apparent accuracy is not evidence of strong orbit determination.

At the original pilot linearization, 128 independent Gaussian observation-noise
draws at the assigned zenith sigmas (0.9 m code, 0.009 m phase, both divided by
sin(elevation)) gave median network 3D RMS **276.803 m**, with a 5–95 percentile
interval of **208.678–389.431 m** over the 12 output epochs. Orbit and wet-delay
prior centres were exactly correct. Scaling the noise to 0.3 times those values
scales the linearized median to 83.041 m.

One pinned realization was then solved nonlinearly, including fresh trajectory
integration on each trial:

| Check | 3D RMS |
|---|---:|
| Linearized noise prediction | 263.3567 m |
| Nonlinear recovered orbit minus synthetic truth | 263.3958 m |
| Nonlinear orbit minus reintegrated linear solution | 0.1392 m |

This demonstrates that the geometry, parameterization and assigned noise alone
can produce errors of this size, without a bad initial orbit or a physical
model discrepancy. It does **not** establish that real residuals are independent
Gaussian noise, calibrate the assigned sigmas, or allocate an exact percentage
of the real error to noise versus systematic observation/force errors.

### Coverage experiments

These use cached linear models, the original pilot linearization and the same
prior sigmas. The 165-minute experiment keeps twelve solve epochs, spaced at
900 seconds. It does not add all intermediate 300-second measurements.

The table scores **the same 29 satellites at the same four output epochs**:

| Case | Expected noise-only 3D RMS | Formal posterior 3D sigma |
|---|---:|---:|
| Eight stations, 55 minutes | 274.878 m | 1740.122 m |
| Remove KOUG, 55 minutes | 237.827 m | 1834.188 m |
| Eight stations, 165 minutes | 206.053 m | 1259.796 m |

Expected noise RMS is `sqrt(E[RMS^2])`, not the Monte Carlo median. Formal
posterior sigma includes the stated broad prior uncertainty; it is a conditional
model calculation, not calibrated physical orbit uncertainty.

Removing KOUG reduces noise-only motion partly because fewer measurements leave
the solution closer to the assumed perfectly correct prior centres. The
posterior uncertainty worsens. It would be wrong to conclude that removing KOUG
improves the network. Removing DJIG disconnects the receiver/satellite graph at
9 of 12 epochs, separating the Australian stations from the remaining network;
the current single-datum epoch-clock elimination correctly refuses that case.
This is a limitation of this solver formulation, not a proof that every possible
estimator must reject such data.

On matched output epochs, the longer arc reduces expected noise RMS by about
25% and formal posterior sigma by about 28%. Over its entire 165-minute output
span and 30-satellite set, its expected noise RMS is instead 478.510 m versus
289.436 m for the baseline's complete twelve-epoch span. The differing domains
and poorly supported endpoints explain why that aggregate alone gives a
misleading comparison. Longer arcs help here, but this test neither demonstrates
centimetre accuracy nor predicts the benefit of a continuously sampled multi-hour
network solution.

### Validation, resources and reproducibility

**90 numerical/parser/model tests pass**, including five new navigation/antenna
tests. The geometry experiments also compare a noise realization with the
independent dense QR solution. The default diagnostic fixture reproduces the
original observations and linear noise response before varying coverage.

The retained main campaign and completion workers consumed **570.49 guarded
seconds (9.51 minutes)**, including the preserved failed seed/clock attempts.
Peak sampled RSS was **253.91 MiB**; minimum observed available system memory was
**11.28 GiB**. The corrected-seed nonlinear fit took 137.77 seconds and peaked at
186.72 MiB RSS. These totals exclude the earlier exploratory campaign and focused
test runs; they are worker runtimes, not total investigation wall time.

Every numerical worker used the existing Windows Python and unchanged native
guard: 2 GiB private-commit cap, one logical CPU/library thread, 10% machine CPU
quota, 8 GiB available-memory reserve and 128 MiB scratch threshold. Workers ran
serially. No package installation or new data download was needed.

Evidence:

- [Original diagnostic and geometry campaign](E:/pythontests/customKF/validation/stage5/20260909-attribution/20260910T011512Z/validation.json).
  Its `failed` status is retained because the first old-record evaluator hit the
  broadcast extrapolation guard. The corrected evaluator records unavailable
  old-record comparisons rather than extending the allowed interval.
- [Completion manifest](E:/pythontests/customKF/validation/stage5/20260909-attribution/20260910T011512Z/completion-20260910T013128Z/completion.json)
  pins earlier evidence, source snapshots, successful follow-ups, tests, evaluator
  outputs, resource measurements and unchanged PDF/source/manifest hashes.
- [Separate IGS evaluation and matched coverage scores](E:/pythontests/customKF/validation/stage5/20260909-attribution/20260910T011512Z/completion-20260910T013128Z/evaluation/evaluation.json).
- The earlier aborted campaign under `20260909T204901Z` and the unsuccessful
  full clock-policy attempt remain available; neither is relabelled as passed.

To repeat the orbit-seed correction, then test/evaluate/archive it:

```powershell
C:\anaconda\python.exe -m customkf.guard --timeout 300 -- customkf.stage5_navigation_fix
# Replace RUN_DIRECTORY with the path printed by the guarded fit.
# Launch this controller directly; it starts its own serial guards.
C:\anaconda\python.exe -m customkf.complete_stage5_attribution --fit-run RUN_DIRECTORY
```

### Recommended next work and open gates

1. Carry the tested seed convention into the next fixture, and complete a
   separately tested navigation applicability/availability policy. Preserve the
   old pilot as the labelled regression baseline.
2. Select stations by additional viewing directions for poorly constrained
   satellites, with explicit graph-connectivity and formal information checks.
   A station count by itself is an inadequate network criterion.
3. Test a continuously sampled multi-hour arc with broader geography. First
   budget the retained QR problem and extend its structure within the existing
   resource limits; do not lift the current bounded-pilot state cap to force a
   larger run. Keep noise, prior sensitivity and real-data comparisons separate.
4. Reassess force/observation systematics and withheld-orbit behaviour once the
   network has enough information. Weak-prior robustness, independent orbit
   accuracy and rapid-vintage provenance remain unpassed.

The next milestone should demonstrate that observations improve upon the
approximately 1.2 m integrated corrected broadcast seed. That is an intermediate
diagnostic target, not a replacement for the original IGS-comparison ambition.

---

<!-- original: STAGE5B_RESULTS.md -->

## Stage 5b — continuous arcs and broader station coverage

10 September 2026 (final archive review 11 September UTC). Status: numerically
complete after a stationarity review; independent orbit-accuracy gate remains open.
This is a diagnostic step toward independent GPS POD, not a rapid-product
accuracy or operational acceptance.

### Results and interpretation

Adding four geographically spread stations substantially improves this experiment.
At identical 390 satellite/epoch samples over three hours, raw 3D RMS against IGS
rapid falls from **314.95 m to 57.32 m**. More observation time alone did not help:
on the original 116 common samples, extending the eight-station arc worsens the
fit from **156.81 m to 229.08 m**. The earlier linear noise-only geometry result
was not a prediction that the actual longer-arc observation fit would improve.

| Exact common scoring domain | eight-short | eight-long | expanded-long |
|---|---:|---:|---:|
| Original 116 samples, fitted 3D RMS (m) | 156.8087 | 229.0833 | 70.8281 |
| Original 116 samples, initial 3D RMS (m) | 1.2001 | 1.2001 | 1.2001 |
| Long-arc 390 samples, fitted 3D RMS (m) | — | 314.9515 | 57.3171 |
| Long-arc 390 samples, initial 3D RMS (m) | — | 1.4913 | 1.4913 |
| Each case's full sample count | 116 | 390 | 403 |
| Full sample set, fitted 3D RMS (m) | 156.8087 | 314.9515 | 56.3867 |

On the long common domain, the expanded fit has radial/along/cross RMS of
18.124/37.892/39.000 m. On the original common domain its corresponding values
are 5.467/39.214/58.728 m, with orbit-only amplitude-weighted URE 11.423 m.
The full expanded sample set includes G25; its 56.39 m must not replace the
matched 57.32 m in the eight-versus-twelve-station comparison.

#### Determinability and the remaining errors

Following the user decision documented in Claude's notes, use the frozen
[determinability split](claude/SCORING_RULE.md): initial-position formal sigma
`sqrt(trace(C_position)) <= 10 m`, with a 50 km site-clustering rule for coverage
descriptions. Keep all-satellite results and list the poorly determined satellites
separately. For comparisons also retain the set classified as determined in both
runs. The 10 m threshold was selected after seeing the Stage 5b baseline scores,
before Claude's ablations; baseline subset improvements are exploratory. Formal
covariance includes priors and assumed observation noise; it is not calibrated
real-world uncertainty or an accuracy certificate. Saved covariance is labelled
at the pre-step linearization (which equals the retained state for a stationary stop).

| Expanded network group | Satellites | Fit 3D RMS (m) | Seed 3D RMS (m) |
|---|---:|---:|---:|
| All | 31 | 56.3867 | 1.4759 |
| Formal sigma <= 10 m | 26 | 1.2253 | 1.4861 |
| Poorly determined | 5 | 140.3740 | 1.4217 |

| Poorly determined satellite | Formal initial-position sigma (m, rounded) | Full-arc fit RMS (m) | Coverage limitation |
|---|---:|---:|---|
| G18 | 1352 | 313.65 | HOB2 and FAA1 overlap for only 9 of 37 solve epochs; FAA1 alone afterwards, no retained observations after 14:35 |
| G16 | 56 | 8.47 | 16 multi-site epochs; unobserved after solve epoch 26 |
| G29 | 56 | 8.46 | First retained observation at epoch 16; early scored interval is extrapolation |
| G31 | 28.5 | 1.69 | Only 17 multi-site epochs |
| G26 | 1732 | 1.07 | DJIG and FAA1 observations never overlap; effectively prior-dominated despite having observations |

G18 contributes **99.8109% of total squared error**. Excluding it gives 2.4928 m,
but that is only an outlier-attribution diagnostic; it is not the headline or
the frozen classifier. Its 13.68 mm HOB2 phase residual coexists with hundreds of
metres of orbit displacement. That association and its huge formal covariance
support weak determination; the residual alone does not prove the causal size
of a particular measurement error. With a free satellite clock each epoch,
a genuinely single receiver cannot provide independent conventional line-of-sight
range information on the orbit at that epoch. Two receivers within 50 km are
not mathematically identical: clustering them is a conservative coverage label,
not exact proof that their differential information is zero.

#### Independent KOUR ablations

Claude completed these before Astra's final review. They remove either KOUR's
previously flagged 13:30–14:30 window (136 links) or all KOUR links (395), using
the archived fixtures and the same physical model, priors, QR and stopping rules.
Astra independently checked the exact retained rows and seeds, current estimator
hashes, convergence status, and recomputed the following RMS values directly in
Cartesian coordinates from native IGS samples.

| Case | All-satellite RMS (m) | Satellites determined in both: RMS (m) |
|---|---:|---:|
| Expanded baseline | 56.3867 | 1.2253 (26) |
| Expanded, KOUR flagged window removed | 56.4932 | 1.1984 (26) |
| Expanded, all KOUR removed | 55.7187 | 1.2142 (26) |
| Eight-station long baseline | 314.9515 | 1.5190 (11) |
| Eight-station long, KOUR flagged window removed | 226.5707 | 1.5272 (11) |

KOUR's expanded-network phase RMS falls from 20.5 to 12.3 mm when the window is
removed. Eight-long G24 improves from 960.3 to 61.6 m, but remains poorly
determined. This supports a local observation-quality episode amplifying weak
geometry. It does not identify the episode's physical cause. Removing KOUR does
not cure the expanded network's weak satellites. KOUG remains at about 14–15 mm
phase RMS, so its residual excess needs its own explanation. These diagnostic
edits have not become default data exclusions.

### Numerical stopping and preserved failure history

The first campaign failed at expanded-long iteration 2: no trial fraction met
the existing objective acceptance test. An isolated audit found a proposed
initial-position/velocity stopping measure `||dr0|| + T ||dv0||` of **0.07768 mm**,
predicted linearized objective reduction **7.07e-9**, and whitened direction
norm squared **7.07e-9**. The measure is a stopping proxy, not a rigorous bound
on the integrated orbit. Trial objective differences were approximately
6.3e-6 to 2.4e-5 for maximum residual changes of only 0.08–0.21 micrometres.
This supports effective numerical/Jacobian resolution as the immediate stopping
issue; it does not isolate its exact floating-point cause.

`nonlinear_stop.py` now permits retaining the last accepted iterate only when
the orbit-step measure is below 1 mm and both linearized reduction and whitened
direction norm squared are below `max(1e-5, 1e-8*cost)`, with finite/nonnegative
checks. The direction criterion also guards against significant nuisance-state
movement. It does not accept a worse trial or loosen line-search acceptance.
Five targeted tests cover these distinctions. All **102 tests pass**; the
original legacy-fixture regression also passed. Final review verified that the
retained state, sampled trajectory, residuals and sigmas are **bitwise identical**
to the last accepted pre-fix checkpoint. Numerical convergence is not accuracy.

The original campaign deliberately keeps `status: failed`. Its linked completion
is `completed_after_stationarity_review_not_accuracy_acceptance`; neither archive
has been rewritten to erase the failure.

### Experiment

The preceding attribution study found that correcting orbit initialization
improved the starting trajectory from 27.40 m to 1.20 m relative to IGS rapid,
while observation fitting still produced 156.81 m. The next experiment separates
additional observation time from additional geographic coverage:

| Case | Stations | Solve epochs | Arc | Code / phase observations | Retained / epoch-clock parameters |
|---|---:|---:|---:|---:|---:|
| eight-short | 8 | 12 | 55 minutes | 879 / 872 | 273 / 385 |
| eight-long | 8 | 37 | 180 minutes | 2702 / 2699 | 314 / 1189 |
| expanded-long | 12 | 37 | 180 minutes | 4052 / 3991 | 402 / 1467 |

All solve epochs are 300 seconds apart, beginning at 12:00 GPST on 2 August 2026.
RINEX parsing and slip detection still inspect the native 30-second observations;
"continuous" here means retaining every five-minute solve epoch, not fitting
every native observation. The three-hour cases end at 15:00 inclusive.

The eight original stations are BRUX, HOB2, KOUR, ABMF, KOUG, DJIG, NNOR and MAS1.
The additions are DAV1 (Davis), FALK (Falkland Islands), FAA1 (Faaa) and GLPS
(Galápagos). During the original 55-minute interval, the actual retained station
sets for the original four worst satellites become:

| Satellite | Observing stations in expanded fixture |
|---|---|
| G05, G12 | ABMF, FAA1, GLPS, KOUG, KOUR |
| G20 | ABMF, FALK, GLPS, KOUG, KOUR |
| G22 | ABMF, DAV1, FALK, GLPS, KOUG, KOUR |

The evaluator scores exact native IGS SP3 epochs, without Helmert alignment,
and reports both each case's complete sample set and intersections of satellites
and epochs. The intersection is essential: extending the arc adds G29 and later
epochs, which would otherwise change the scoring domain as well as the estimator.

### Why these stations

A public [BKG station-file listing for day 214](https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/214/)
was intersected with the pinned IGc20 coordinates, valid coordinate solution
intervals and ocean-loading table. Stations needing unsupported postseismic
deformation were excluded. This left 142 metadata-compatible candidates.

The geometric screening objective uses elevation-weighted line-of-sight vectors
with their weighted mean removed to represent an unknown satellite clock. A
greedy log-determinant score, regularized by `1e-6 I`, sums over GPS satellites
and the three-hour grid; G05/G12/G20/G22 receive twice the weight of other
satellites. This is a heuristic screen that assumes receiver clocks known. It
is neither the dynamic estimator's covariance nor a proven optimal network.

The first choices exposed actual input-model limitations. MCM4 and MAW1 lack
their exact antenna/radome combinations in the pinned calibration file. PARC,
GAMB, SYOG and CAS1 need unsupported code-bias/signal handling. These exclusions
are not findings of bad station data. Twelve 32 KiB compressed header samples
were then checked before acquiring additional complete files. SUTM's declared
phase-shift metadata exceeds the currently supported profile. Restricting the
screen to the compatible checked headers and baseline stations left 18 candidates;
the greedy selections became DAV1, FALK, FAA1 and GLPS. Réunion was compatible,
but these four gave a better marginal geometry score within that candidate set.

The selected stations passed full-file header, supported signal-pair and exact
antenna-calibration checks, and the actual epoch graphs passed the solver's
single-datum connectivity requirement. They have not yet had independent PPP
coordinate validation, so their observation-model quality remains a separate
gate. No station was removed based on postfit orbit error.

### Estimator and input changes

`reduced_network.reduced_qr` estimates the retained parameters and recovers epoch
clocks through QR elimination, while returning only the retained covariance.
It never builds the full clock covariance or a design matrix spanning all clock
columns. The old full-covariance implementation and its 900-total-parameter
limit are unchanged as the small-problem oracle. The new implementation keeps
900 retained columns and 12,000 rows as ceilings and adds a conservative
256 MiB matrix-workspace preflight. Its workspace estimates for these three cases
are 26.81, 80.90 and 149.16 MiB; those are allocation estimates, not measured RSS.
No normal equations are formed and no OS resource limit was raised.

Small independent tests compare both estimates and retained covariance against
the original full-covariance solver. Other tests check a system containing 1000
local clocks, rank deficiency and refusal of a matrix exceeding the workspace
budget. A real-fixture regression also exactly reproduces the archived legacy
observation/noise calculation after the preparation code was generalized.

Each nonlinear iteration runs in a separate serial guarded worker. A preparation
worker pins a JSON fixture; subsequent workers verify its hash, source hashes,
all used data hashes and the prior checkpoint before resuming. Each trial still
reintegrates the dynamic orbit. This avoids extending a worker timeout or leaving
an unbounded background solver. Retained covariance saved with a step belongs
to its pre-step linearization and is labelled diagnostic.

The new fixture consistently uses the corrected nominal four-hour LNAV selection
for both initial orbit states and satellite clock polynomials. It permits valid
negative offsets from toe/toc, checks applicability across the full epoch grid,
and rejects unsupported fit profiles. The data cutoff is the end of the same
observed day, independent of the observation epoch. See
[IS-GPS-200N, section 20.3.4.5 and Table 20-XIII](https://archive.gps.gov/technical/icwg/IS-GPS-200N.pdf).
This is a deliberately bounded navigation profile, not a complete implementation
of offset reference times and extended fits. Thirty distinct used records in
each long fixture have unknown receipt timing from zero transmission tags;
historical rapid availability is not certified.

Initial states use the ANTEX ionosphere-free antenna offset and nominal yaw to
convert broadcast APC to COM, including the velocity correction. All fits retain
the original broad 1000 m / 1 m/s orbit prior sigmas, float ambiguities, two wet
delay endpoints per station and fixed ECOM5 coefficients. The wet-delay endpoints
span different durations in the short and long cases; this is not a pure change
in equation count with every temporal basis held fixed. Empirical force
coefficients are not yet estimated in these observation fits.

RINEX phase-shift records now have an explicit opt-in metadata profile. The
reported corrections were applied before the observations were written and are
preserved as metadata, never added again. This was verified against
[RINEX 3.05, section 5.2.12 and Table 9](https://files.igs.org/pub/data/format/rinex305.pdf)
and a known-value parser test. Unsupported continuation/malformed metadata,
scale factors and unvalidated code-bias combinations still fail closed. The
legacy parser profile remains available for exact earlier reproductions.

### Resources and evidence

The campaign uses the existing Windows Python, the same pinned Hatanaka decoder
and the unchanged guard: 2 GiB aggregate private commit, one logical CPU/library
thread, 10% machine CPU quota, 8 GiB available-memory reserve, 300 seconds per
worker and 128 MiB scratch threshold. The new data includes 42.89 MiB of downloaded
compressed station files and 119.68 MiB of recompressed decoded files, including
screened candidates that were not selected; header samples and the listing are
additional small files. No software was installed.

The campaign is archived under
[validation/stage5b/20260910T203254Z](E:/pythontests/customKF/validation/stage5b/20260910T203254Z/validation.json).
It preserves source snapshots, input hashes, the then-current 97-test suite, the legacy
regression, prepared fixtures and each nonlinear iteration separately.

The [completion archive](validation/stage5b/20260910T203254Z/completion-20260910T205844Z/validation.json)
adds the stopping audit, 102-test suite, accepted-state confirmation and separate
IGS evaluator. Combined main/completion workers used **1410.924 s (23.52 min)**,
including the failed iteration and audit, with **320.48 MiB** peak sampled RSS
and at least **15.63 GiB** available memory. Acquisition/scouting is separate.
Claude's [KOUR campaign](claude/runs/20260910T222851Z-kour-ablation/campaign.json)
used another **1152.516 s (19.21 min)**, **315.0 MiB** peak RSS and minimum
**15.37 GiB** available. No guard limits changed.

Astra's [final verification](claude/runs/20260911T014145Z-astra-verification/verification.json)
checked **279 pinned archive artifacts**, report hashes, estimator/test source
continuity, stationary-state identity and all six Cartesian baseline/ablation
scores. It took **8.875 s**, peak **118.41 MiB** RSS, minimum **16.57 GiB** available.
The current Claude helper scripts are now hashed in that review; the earlier
Claude campaign did not archive historical hashes of its own helper scripts.
Thus this review verifies artifacts and current code but cannot certify the
historical helper revision independently of those outputs.

### Next work and open gates

Latest, 11 September: the controlled YELL and GUAM additions are complete.
All-satellite RMS on the same 403-sample domain fell 56.387→11.177→0.821 m.
See [YELL/GUAM results](YELL_GUAM_RESULTS.md); next work is prior sensitivity on
the 14-station case. Earlier next-step paragraphs below are historical rationale.

Update, 11 September UTC: the four station PPP coordinate gates and the covariance
mapping/propagation audit have now passed. DAV1 has a separate evening residual
exception; the weak-satellite screen identifies YELL as a useful next candidate.
See [the completed follow-up](STAGE5B_STATION_CHECKS.md). The paragraphs below
retain the original next-step rationale; the Opus handoff records current status.

First validate the four added stations independently with fixed-product PPP and
screen actual co-visibility for weak satellites. Preserve the frozen scoring
split and full-domain comparison. Do not immediately extend this dense retained
design to a day: 12 stations over six hours would exceed the current 12,000-row
ceiling. Scaling needs bounded QR accumulation and equivalence tests, not higher
limits. Test a finer wet-delay time basis only as a controlled hypothesis after
the station checks; the KOUR ablation is already complete.

Open gates include weak-prior stability, observation-quality exceptions,
empirical-force estimation, broader network/day generalization and rapid-vintage
input availability. In particular, a monthly bias product is not automatically
available at the historical rapid deadline simply because the bias is stable;
any future signal-bias input needs explicit validity and publication/receipt checks.
The [Opus verification handoff](claude/ASTRA_VERIFICATION_HANDOFF.md) separates
required next-stage checks from optional investigations with compute caps.

The PDF, report source and report manifest remain the prior dated snapshot.

---

<!-- original: STAGE5B_STATION_CHECKS.md -->

## Stage 5b follow-up: independent station PPP, covariance and coverage

10 September 2026 local / 11 September UTC. **Four new stations pass the
coordinate gates.** Covariance mapping and propagation checks pass. DAV1 has a
separate daily residual episode; physical observation-quality and orbit-accuracy
acceptance remain open. No new network orbit solution was fitted in this step.

### Independent fixed-product PPP

Each station was solved over 2 August using fixed IGS rapid orbit/clock products,
five-minute solve epochs and native 30-second slip detection. The coordinate
reference is the pinned IGc20 solution at noon. Gates retain Stage 3's <20 mm
horizontal and <50 mm absolute vertical limits; coordinates are estimated without
coordinate priors. No next-day rapid padding or postfit clipping was introduced.

| Station | Horizontal error (mm) | Vertical error (mm) | Daily phase RMS (mm) | Phase RMS during 12:00–15:00 (mm) | Daily phase rows >4 assumed sigma |
|---|---:|---:|---:|---:|---:|
| DAV1 | 5.368 | -16.190 | 13.774 | 8.466 | 13 |
| FALK | 6.382 | +0.999 | 9.536 | 8.405 | 0 |
| FAA1 | 2.715 | +1.780 | 9.132 | 9.330 | 0 |
| GLPS | 5.631 | -2.940 | 6.751 | 6.562 | 0 |

All four converged and had full-rank PPP designs. Their coordinate agreement makes
gross station coordinate/calibration mistakes less likely as the cause of the
Stage 5b orbit outliers. This is not a full independent validation of the shared
observation model: PPP and network reuse corrections and processing conventions,
and the PPP reference is fixed IGS rapid. The daily PPP wet basis also has hourly
knots and gradients, unlike the network's two wet endpoints. Do not treat its
12:00–15:00 residuals as the same experiment or exact link set as the network fit.

`run_stage3.py` now accepts DAV1/FALK/FAA1/GLPS on the pinned date, verifies the
Stage 5b input manifest and the selected observation file, and opts those stations
into the existing already-applied phase-shift metadata parser. Marker strings,
signal pairs and exact antenna/radome calibrations are preserved. Legacy stations
keep their previous parser behavior. The physical models, estimator, matrix
limits, clock treatment and arc rules were not changed.

A fresh pre-edit BRUX run was archived. After the extension, every saved BRUX
numerical array and non-timing legacy report field matched **bit-for-bit**.
All **25 targeted tests** passed (Stage 3 parsing/models and Stage 5b inputs).
The earlier full 102-test result remains historical; this step reran the affected
tests and the real-data regression rather than the entire suite.

### DAV1 residual exception

The 13 daily phase residuals above four assumed sigmas occur between **21:10 and
21:35 GPST**, involving G07/G15/G18/G20/G27/G30. The largest absolute residual is
**191.8 mm**; the largest normalized residual is **13.88**. The 12:00–15:00 orbit
experiment has **zero** such residuals at all four new stations. The separate
evening episode cannot directly contaminate observations that the earlier
three-hour network solve never ingested; however, full-day PPP nuisance estimates
can be influenced by measurements elsewhere in that day.

DAV1 has 634 native arcs and 134 fitted daily ambiguities; 144 short-arc phase
rows are excluded by the unchanged prefit arc rule. Its daily arc-event reason
counts are 533 geometry-free, 115 loss-of-lock, 23 Melbourne–Wübbena, 67 gap and
32 new-satellite events. Reasons can overlap within an event. The 21:00–22:00
review preserves 64 arc events and 726 native records for the six implicated
satellites. The evidence shows a residual episode and substantial tracking/arc
fragmentation, but does not distinguish receiver behavior, ionospheric effects,
multipath or shortcomings in the arc/model logic. No causal label, station
exclusion or extra clipping has been adopted.

The [residual plot](validation/stage5b_stations/20260911T015113Z/followup-review/residuals/station_residuals.png)
was visually inspected: all four daily series and the highlighted network interval
are legible; DAV1's evening episode is distinct. FALK/FAA1/GLPS show no comparable
episode under this screen. That is a passed limited screen, not full physical
acceptance or a calibrated residual-probability statement.

### Covariance mapping and full-arc propagation

A separate guarded audit used the archived expanded-network state and marginal
retained covariance, without reading precise orbit or clock files. It verified:

- Named orbit-index mapping within the 402×402 retained covariance; epoch clocks
  lie outside that matrix.
- Symmetry, finite positive diagonal entries and positive semidefiniteness of the
  scaled correlation matrix (minimum eigenvalue **3.26e-9**).
- Identity of the state transition matrix at the initial epoch and recomputed
  trajectories exactly matching all saved state components for all 31 satellites.
- Position covariance `Phi_position C_state Phi_position.T`, including velocity
  and position–velocity cross terms, against propagation of a Cholesky factor.

| Satellite | Initial position root-trace sigma (m) | Minimum / maximum on the three-hour solve grid (m) |
|---|---:|---:|
| G16 | 56.295 | 37.503 / 106.216 |
| G18 | 1352.468 | 1353.601 / 5826.572 |
| G26 | 1732.051 | 1732.137 / 22757.161 |
| G27 | 5.469 | 5.044 / 13.620 |
| G29 | 56.188 | 14.400 / 56.082 |
| G31 | 28.541 | 8.014 / 28.488 |

The initial epoch is 10 seconds before the first solve sample, so initial sigma
need not equal a grid endpoint. These results support the covariance bookkeeping
and demonstrate weak velocity/extrapolation constraints. They do **not** calibrate
formal uncertainty against reality. Priors and assumed noise are included;
uncertainty in fixed force coefficients and external corrections is not.

The frozen initial-sigma classifier remains unchanged: G27 still belongs to its
determined group even though its propagated position sigma later exceeds 10 m.
Future reporting should include time-dependent uncertainty alongside that frozen
grouping. Do not silently redefine the classifier to improve a score.

### Candidate coverage screen

A cached-data-only screen used the five frozen poorly determined satellites,
actual retained baseline station/epoch masks, broadcast positions and a 10°
candidate elevation cutoff. The ranking sums incremental trace of clock-centred
line-of-sight information, equally weighted across the five satellites. Receiver
clocks are assumed known for this heuristic; candidate observations are not yet
verified. It is neither a dynamic covariance calculation nor an error forecast.

**YELL is the strongest already-header-compatible candidate** in this screen.
Its potential G18 visibility begins at epoch 9, immediately after HOB2's last
retained epoch 8. It can overlap FAA1 for **23 epochs (12:45–14:35)**, with a median
maximum line-of-sight separation of **20.97°**. If actual observations support
that geometry, the existing nine multi-site epochs could become 32. YELL alone
over the final five epochs would still leave that tail weakly constrained.

| Header-compatible candidate | Potential co-visible epochs: G16 / G18 / G26 / G29 / G31 |
|---|---|
| YELL | 10 / 23 / 7 / 21 / 1 |
| ALGO | 0 / 12 / 0 / 21 / 0 |
| THTG | 0 / 9 / 0 / 5 / 17 |
| REUN | 9 / 0 / 0 / 0 / 0 |
| HRAO, SUTH | 0 / 0 / 0 / 0 / 0 |

These counts require a candidate at least 50 km from one currently observing
receiver; they are not all *newly gained* multi-site epochs. THTG is near FAA1 and
mostly duplicates its G18 view, whereas YELL fills the later gap. In contrast,
GAMB offers 25 potential G18 overlap epochs but only about **3.13°** median maximum
LOS separation, with unsupported code-bias handling still required. PARC has no
G18 visibility in this interval. This makes YELL a more direct next experiment
than implementing code-bias support solely to unlock those two stations.

Among metadata-compatible candidates whose headers remain unchecked, the top
ranked are MCIL, CCJ2, UTQI, GUAM and KOKB. MCIL/CCJ2/GUAM/KOKB geometrically overlap
all 32 baseline-observed G18 epochs. Small header checks should precede any full
data acquisition for these; the screen does not imply their signals, calibration
or daily observations are supported.

### Resources, archives and next step

All work used existing Windows Python, no new downloads or software, and unchanged
guard limits. Nine PPP/test/regression workers including the pre-edit baseline
used **131.844 s**. Covariance, residual/native-record and coverage reviews added
29.141, 3.406 and 3.609 s, for **168.000 s (2.8 min)** total guarded wall time.
Peak sampled RSS was **206.41 MiB**, minimum available system memory **16.265 GiB**.
Each worker used a 120 s timeout, below the usual 300 s default; none hit a limit.

[The primary archive](validation/stage5b_stations/20260911T015113Z/validation.json)
contains source snapshots, pinned inputs, BRUX before/after outputs, each station,
tests and numerical diagnostics. It retains its original residual-review-pending
status; the later review is attached in
[followup-review](validation/stage5b_stations/20260911T015113Z/followup-review/manifest.json)
without rewriting that history. Helper source snapshots and their guard results
are included there. The PDF, report source and manifest are unchanged.

Next: acquire and validate YELL's already-screened full observation file, then
preflight a controlled same-three-hour baseline-plus-YELL solve against the
unchanged row/retained/workspace caps. Check headers for one additional distinct
view if needed. Preserve all/common/determined-in-both scoring. Resolve DAV1's
evening exception before relying on full-day processing; it need not block this
earlier three-hour geometry experiment.

---

<!-- original: YELL_GUAM_RESULTS.md -->

## YELL and GUAM: controlled tests of the weak-orbit explanation

11 September 2026. **YELL and GUAM completed and verified. The 14-station
all-satellite orbit RMS is 0.821 m**, versus 11.177 m with YELL and 56.387 m
with twelve stations, on identical 31-satellite/403-sample domains.
The objective is to reduce the large orbit errors by adding missing simultaneous
views. Station qualification supports that orbit experiment; it is not a broad
station survey. All accuracy gates remain open until the actual scored results
justify otherwise. No PDF update in this step.

### YELL survived the interrupted session

The original controller at `validation/yell/20260911T020943Z` stopped externally
during iteration 1 after saving iteration 0. The unfinished worker has no guard
result; its exact termination cause and complete resource consumption are unknown.
Opus continued from the pinned iteration-0 state in
`claude/runs/20260911T022428Z-yell-continuation`, preserving the original archive.
Two further guarded iterations converged, including a stationary stop that kept
the preceding accepted state bit-for-bit. The original manifest's `running` status
is historical and must not be read as a request to restart it.

Astra reran the continuation review before any GUAM source edits: archive/source
hashes, accepted-state identity, actual coverage and residual checks passed in
5.438 s, with 111.63 MiB peak RSS and at least 15.469 GiB available memory.
Evidence is copied into the GUAM campaign as `YELL_verification/`.

| Identical native IGS comparison domain | 12 stations | +YELL, 13 stations |
|---|---:|---:|
| All 31 satellites, 403 samples: 3D RMS | 56.387 m | 11.177 m |
| Same 26 satellites determined in both runs | 1.225 m | 0.997 m |
| G18, full scored arc | 313.65 m | 1.76 m |
| G26, full scored arc | 1.07 m | 61.89 m |

YELL gave G18 exactly the predicted 23 extra simultaneous-site epochs, increasing
its multi-site coverage from nine to 32 epochs. Its formal initial-position sigma
fell from 1352 to 4.74 m. This is strong evidence that inadequate coverage caused
G18's enormous earlier error, though 1.76 m is not IGS-level reproduction.

G26 demonstrates the remaining problem: originally it had no simultaneous
receivers and stayed near its broadcast seed. YELL adds only seven two-site
epochs near the arc end. Its fitted error grows to 61.89 m while formal position
sigma remains about 1397 m; it contributes about 98.9% of squared error. A weakly
determined observation fit can be worse than the starting broadcast orbit. The
absence of >2-sigma G26 residuals does not prove perfect data or rule out model
errors; the geometry and covariance explain why a large orbit movement is allowed.

All 28 satellites below the frozen 10 m formal-sigma threshold in the YELL run
have 1.076 m RMS. The poorly determined group remains G16/G26/G31. All-satellite
results and fixed-set comparisons remain visible; no satellite was removed.

### Why GUAM is the next controlled test

Opus screened the 13-station masks using the same clock-centred LOS-information
heuristic, with focus satellites selected by the frozen sigma rule. GUAM is the
highest-ranked header-compatible candidate. It potentially adds new multi-site
epochs for G16/G26/G31 of 12/28/17, with G26 LOS separation about 21.7 degrees.
PIMO and POHN also passed header screening; no other site is being added now.
This is geometric ranking, not a covariance or accuracy forecast.

GUAM's full BKG observation file was acquired and decoded with the existing
pinned RNXCMP executable. It passed the C1W/C2W/L1C/L2W signal and exact
JAVRINGANT_DM SCIS calibration checks. The fourteen-station case retains the same
2 August 12:00–15:00 GPST interval, 300 s solve epochs, native slip checks, broad
1000 m /1 m/s priors, fixed empirical forces, float ambiguities and two wet-delay
endpoints. No KOUR exclusion is applied. Precise products remain evaluator-only
for network fitting; the separate station PPP uses fixed rapid products.

Campaign: `validation/guam/20260911T155927Z`. Before fitting, the evaluator
confirmed exact equality of all original thirteen stations' retained rows, seeds
and sampled starting states. The matrix and guard ceilings are unchanged.
The final comparison retains 12-, 13- and 14-station full scores and the
13-versus-14-station determined-in-both set. Final values follow.

### GUAM result: catastrophic coverage errors removed in this case

| Same scoring domain | 13 stations | +GUAM, 14 stations | Broadcast seed |
|---|---:|---:|---:|
| All 31 satellites, 403 samples, raw 3D RMS | 11.1768 m | **0.8211 m** | 1.4759 m |
| Same 28 satellites determined in both, 364 samples | 1.0760 m | **0.8139 m** | 1.5017 m |

The full 14-station R/A/C RMS is **0.4560 /0.4784 /0.4873 m**, and orbit-only
amplitude-weighted URE is **0.4574 m**. The Cartesian recomputation agrees with
the RAC-based score within the 20 nm assertion tolerance. No Helmert alignment,
postfit satellite removal, changed noise weights or tighter orbit priors are used.

| Satellite | 13-station 3D RMS (m) | 14-station 3D RMS (m) | New formal initial-position sigma (m) |
|---|---:|---:|---:|
| G16 | 2.780 | 0.920 | 1.851 |
| G18 | 1.762 | 2.403 | 1.690 |
| G26 | 61.893 | 1.044 | 3.640 |
| G29 | 1.863 | 0.371 | 1.353 |
| G31 | 1.302 | 0.645 | 4.315 |

All 31 now meet the frozen <=10 m formal-sigma classifier; the poorly determined
group is empty. That threshold is a diagnostic, not IGS-level accuracy acceptance.
G18 worsens modestly and is now the largest remaining error; do not describe
every satellite as improved. The next largest are G03 1.38 m, G22 1.33 m,
G24 1.15 m and G26 1.04 m. The fit now improves on the broadcast seed across the
**full** constellation in this three-hour case, but 0.82 m remains far from the
project's decimetre-scale reproduction objective.

GUAM's real data match the predicted new multi-site epoch gains: G16 25→37,
G26 7→35 and G31 18→35. G18 increases 32→33 and G29 21→31. The baseline thirteen
stations' rows, station metadata, seeds and sampled initial trajectories are
exactly unchanged. GUAM contributes 311 code and 309 phase rows. The retained
solve has 443 columns and 1628 local clock parameters, 9378 observation rows,
and **189.90 MiB** estimated matrix workspace, under the unchanged limits.

### Convergence, station quality and verification

All 102 tests passed. The first orbit iteration accepted a full step, reducing
the weighted objective from 24,797,533.65 to 1685.73525. At the next linearization,
the existing position/velocity stopping proxy was 0.0411 mm and the predicted
objective reduction 7.15e-7. The unchanged stationarity rule retained the accepted
state. Final review verified the state, trajectory, residual and sigma arrays
bit-for-bit against the preceding checkpoint. No stopping tolerance was changed.

GUAM's separate daily fixed-product PPP coordinate errors are **6.67 mm horizontal
and -10.52 mm vertical**, within the existing coordinate gates. Daily phase RMS
is 20.74 mm, with eleven >4-assumed-sigma observations outside 12:00–15:00. The
current interval has 13.88 mm PPP phase RMS and no such flags; in the network fit,
GUAM has **5.62 mm phase RMS**, 0.924 m code RMS and no >4-sigma code or phase rows.
PPP and network use different nuisance-state/temporal models and link sets;
their residual RMS values are not a like-for-like model improvement metric.
The daily residual causes remain open before relying on full-day processing.

The guarded final review verified the new archive, pinned current sources and
inputs, unchanged report files, stationary checkpoint identity, residual row
labels against stored sigmas, and actual site coverage. See
[the final review](validation/guam/20260911T155927Z/followup-review/review/review.json).
No extra fit or postfit exclusions were used in this review.

### Resource measurements

The GUAM campaign, including download, re-verification of YELL, tests, PPP,
preparation, invariance, two orbit workers and evaluation, used **403.187 s**.
Final review added **1.172 s**, for **404.359 s (6.74 min)**. Peak sampled RSS
was **364.48 MiB**, with at least **15.437 GiB** available system memory.
Orbit workers took 148.1 and 124.3 s. All memory/CPU/row/column/workspace limits
remain unchanged. Only one numerical worker ran at a time. No software installed.

The YELL interrupted-worker time is not included in this GUAM total; it lacks a
complete guard record. Opus's separate continuation resources are documented in
`claude/YELL_CONTINUATION.md`. All completed and interrupted archives remain
intact; the 13-station continuation is accepted as the comparison baseline without
rerunning it or moving its files out of `claude/`.

### Continuity and remaining investigations

The GUAM controller atomically saves its active worker and completed results.
Each orbit iteration is a separate <=300 s guarded job, at most five; station,
preparation and evaluator workers are <=120 s. If interrupted, recover the last
successful pinned checkpoint into a new continuation archive. Do not restart
completed acquisition/PPP or relax numerical thresholds to force convergence.

With the large weak-mode outliers removed here, the next experiment is prior
sensitivity on the fourteen-station network, not automatically another station addition.
Daily YELL 07:35 and DAV1 evening residual episodes are outside the current orbit
window and remain separate investigations before daily processing. Full-day
scaling, stochastic-model calibration, force estimation and rapid-vintage input
certification also remain open. The current Opus queue is maintained in
`claude/ASTRA_VERIFICATION_HANDOFF.md`.

---

<!-- original: STABILITY_RESULTS.md -->

## Fourteen-station prior/start stability — 11 September 2026

The current 0.821 m IGS disagreement is stable under 10x weaker orbit-prior
sigmas and a substantially different starting point. The largest sampled
trajectory difference is **0.03528 mm**, against the predeclared **10 mm**
diagnostic threshold. This passes the numerical stability experiment; it does
not pass the IGS reproduction or operational rapid-latency accuracy gates.

### Fixed scope and controlled changes

Same 2 August 2026, 12:00–15:00 GPST interval, fourteen stations, 31 GPS satellites,
37 five-minute solve epochs and 403 native IGS comparison samples. No station,
satellite or residual removal. Same physical forces, observations, weights,
clock datum, float ambiguities and two-endpoint wet-delay model as GUAM.

Nominal orbit-prior sigmas are 1000 m position and 1 m/s velocity. The weak
experiment uses 10,000 m and 10 m/s: 100x less prior information weight.
Prior centres remain the original broadcast seeds, never the warm solution.
Wet constraints and all other priors stay unchanged. The estimator's precise
SP3/CLK read prohibition remains active; IGS is read only by separate evaluators.

The perturbed start uses alternating-sign inertial RAC offsets [100, -70, 40] m
and [0.02, -0.01, 0.01] m/s for each satellite relative to its broadcast seed.
Estimated nuisance offsets are reset to zero; the existing deterministic
receiver-clock seeds and ambiguity origins are still constructed normally.
This tests a different start with weak priors. A pure broadcast cold start is
a separate optional confirmation assigned to Opus.

### Results

| Case | Applied updates / stationary checks | RMS trajectory change vs GUAM | Maximum change | All-31 IGS 3D RMS |
|---|---:|---:|---:|---:|
| Nominal-prior worker reproduction | 0 / 1 | exactly 0 | exactly 0 | 0.821140807 m |
| Weak prior, warm start | 0 / 1 | exactly 0 | exactly 0 | 0.821140807 m |
| Weak prior, perturbed start | 2 / 1 | 0.004920 mm | 0.035276 mm | 0.821140422 m |

The warm run retained its input checkpoint because its proposed displacement
metric was 0.108864 mm and its predicted objective reduction was 7.1544e-7,
meeting the unchanged stopping rule. Its exact zero change is therefore a
tolerance-limited result, not a claim of mathematical independence from priors.
The perturbed run supplies the independent-start check: two accepted full
updates, then a stationary check with displacement metric 0.002276 mm and
predicted reduction 6.5942e-9. Its maximum difference from the weak warm solution
is also 0.035276 mm. No convergence tolerances were loosened.

The roughly 0.4 micrometre change in pooled IGS RMS is numerical agreement,
not a meaningful accuracy improvement. All satellites remain included and meet
the frozen initial-position formal-sigma classifier. The remaining G18 and
other satellite errors from the GUAM result remain unresolved. Formal covariance
is diagnostic and has not been calibrated against multi-day errors.

### Verification and evidence

- Campaign: `claude/runs/20260911T162036Z-stability/validation.json`, status
  `stability_checks_pass_not_absolute_accuracy_acceptance`.
- Final checkpoints: `baseline-check-0`, `weak-warm-0`, `weak-perturbed-2`.
- `evaluation/evaluation.json`: frozen groups, per-satellite scores and stability
  comparisons. Checks all 31 x 37 sampled trajectory positions; the predeclared
  criterion is maximum 3D difference <=0.01 m, including same-prior start comparison.
- `followup-review/review/review.json`: independently recomputes Cartesian IGS
  RMS, both pooled and per satellite, agreeing with RAC scoring within 20 nm;
  records per-satellite/per-epoch trajectory differences, residual-label/sigma
  checks, histories and stationary checkpoint identity. All checks pass.
- Original review guard: `runs/20260911T163125Z-df0dea7a`.
- Baseline remains `validation/guam/20260911T155927Z/iteration-1`. Its source,
  fixture, input, checkpoint and artifact hashes were checked. The baseline
  reproduction has bitwise-equal solution/residual/trajectory arrays and
  covariance agreement at 1e-12 tolerance.

New helpers are support-local in `claude/tools/`: `stability_step.py`,
`run_stability.py`, `evaluate_stability.py`, `stability_review.py`. Root estimator
and test sources are unchanged. The previously passed 102-test suite was not
rerun for these support helpers; the guarded baseline oracle, stress campaign
and separate result audit are this change's validation. Snapshots and hashes
are archived. No production model change is claimed.

### Resources and next action

Campaign workers used **637.562 s**, and independent review **1.687 s**:
**639.249 s (10.65 min)** total guarded elapsed time. Peak sampled RSS was
**368.164 MiB** and minimum available system memory **15.585 GiB**.
The estimated QR workspace remains **189.902 MiB**. Guards retained the 2 GiB
private-memory limit, one CPU/library thread, 10% machine CPU quota, 8 GiB
available-memory reserve and 128 MiB scratch cap. All workers completed within
their original timeouts. No software installed; no numerical job remains active.

The next model experiment should compare the current wet-delay basis with an
hourly basis while controlling its stochastic constraints. The existing model
has 0.3 m endpoint level priors and a 0.03 m end-to-end difference constraint;
adding nodes must explicitly account for both. Improved in-sample phase RMS
alone will not demonstrate better orbits. Keep the same IGS sample set and
report per-satellite regressions, particularly G18. Force estimation, longer
arcs, streamed QR scaling, multi-day tests and rapid-vintage input certification
remain subsequent work.

Opus can perform the optional broadcast cold-start repeat while Astra is idle;
the exact command, expected runtime and stopping conditions are in
`claude/ASTRA_VERIFICATION_HANDOFF.md`. It is not a prerequisite for beginning
the controlled model work, but run it before model-source changes invalidate
the current fixture's source pins. PDF/source/report manifest remain unchanged.

---

<!-- original: WET_DELAY_EXPERIMENT.md -->

## Hourly wet-delay experiment — results and protocol, 11 September 2026

**Completed: hourly wet delay does not provide a material orbit improvement on
this arc. Retain the two-node GUAM solution as the working baseline.** All-31
IGS RMS changes 0.821140807 to 0.818327943 m, a 0.3426% reduction; the predeclared
5% candidate-benefit threshold is not met. Twelve satellites improve and nineteen
worsen. Six worsen by more than 0.1 m. This is a mixed model-sensitivity result,
not evidence that the remaining 0.82 m error has been solved.

### Completed results

| Quantity, identical sample domain | Two endpoints | Hourly nodes |
|---|---:|---:|
| All-31 IGS 3D RMS, 403 samples | 0.821141 m | 0.818328 m |
| Radial / along / cross RMS | 0.456039 / 0.478382 / 0.487290 m | 0.441649 / 0.471457 / 0.502330 m |
| Amplitude-weighted orbit-only URE RMS | 0.457441 m | 0.443865 m |
| Pooled phase residual RMS, 4652 rows | 10.6444 mm | 10.1986 mm |
| Pooled code residual RMS, 4726 rows | 887.400 mm | 887.246 mm |
| Weighted observation cost | 1667.888760 | 1619.048038 |
| Prior cost | 17.846489 | 25.461095 |

All 31 retain the frozen initial-position formal-sigma classification of
determined; none are removed. No Helmert fit or reference-epoch interpolation
was introduced. IGS comparisons use the same 403 native samples, while trajectory
change diagnostics cover all 31 x 37 solve-grid positions.

| Satellite | Baseline RMS | Hourly RMS | Change |
|---|---:|---:|---:|
| G18, largest baseline error | 2.402518 m | 2.274939 m | -0.127579 m |
| G03 | 1.382221 m | 1.121914 m | -0.260306 m |
| G22 | 1.331837 m | 1.414968 m | +0.083131 m |
| G10 | 0.753973 m | 0.925726 m | +0.171753 m |
| G20 | 0.233692 m | 0.384589 m | +0.150897 m |
| G23 | 0.651927 m | 0.848866 m | +0.196939 m |
| G25 | 0.398243 m | 0.575790 m | +0.177548 m |
| G27 | 0.581751 m | 0.770758 m | +0.189007 m |
| G29 | 0.370835 m | 0.573941 m | +0.203106 m |

The last six rows are the complete set of >0.1 m regressions. The machine-readable
evaluation preserves every satellite, station residual summary and wet-node value.
KOUR phase RMS changes 20.675 to 19.305 mm, and KOUG 17.537 to 16.569 mm. One KOUR
>4-assumed-sigma row drops below that threshold; the KOUG phase flag remains.
This neither diagnoses nor resolves the physical cause of their residual episodes.

The largest interior departures from each station's own fitted endpoint line
are KOUR 21.933 mm and KOUG 16.736 mm. These are fitted nuisance parameters,
not independently validated water-vapour measurements. DAV1's fitted wet term
remains negative (about -67 to -74 mm), already negative in the baseline; the
reduced hydrostatic/measurement model can confound these terms. Its cause is
unverified, and the sign was not clipped or used to remove observations.

### Numerical verification, resources and decision

The two-node oracle reproduced baseline arrays bitwise, with covariance agreement
at 1e-12. The hourly fit accepted one full correction and then stopped at the
unchanged stationarity rule: proposed displacement metric 0.019276 mm and predicted
reduction 9.1962e-7. The stationary checkpoint retains the preceding solution
arrays exactly. Existing 102 root tests were not rerun because root model/test
sources were unchanged; validation here comprises the baseline oracle, prior
equivalence and 764 derivative checks below, the controlled fit and separate audits.

The separate evaluator recomputed Cartesian IGS RMS, pooled and per satellite,
independently of RAC projection, agreeing within 20 nm. A subsequent archive audit
checked source/input/report/artifact hashes, checkpoint history and stationary
identity, and independently reconstructed the full objective from saved residuals
and parameter values. The hourly objective agrees within 2.3e-13.

Campaign `claude/runs/20260911T172336Z-wet` has status
`wet_experiment_complete_not_accuracy_acceptance`; final hourly checkpoint is
`hourly-1`. Core evaluation is `evaluation/evaluation.json`. Later independent
review and pooled reporting arithmetic are archived under `followup-review/`.
Original review/summary guards: `runs/20260911T210527Z-fa0abaa2` and
`runs/20260911T210637Z-6f8676de`. The difference between archive timestamps includes
idle time between user turns; it is not numerical runtime.

Core campaign including basis checks: **478.922 s**; review 1.062 s and summary
0.218 s: **480.202 s (8.00 min)** total guarded work. Independent verification of
Opus's completed cold start added 2.250 s. Peak sampled RAM was **376.332 MiB**;
minimum available memory **15.785 GiB**. All original limits were retained.
No numerical job remains active and no software was installed.

Keep the two-node model as the default baseline. Do not tune node spacing or
increment strength against this same day's IGS scores merely to seek a lower
number. The next recommended diagnostic is a reference-only dynamic-fit ceiling
test: for G18/G03/G22 first, fit the same native IGS positions with the current
fixed-force model and only six initial-state components. Check withheld interior
epochs as well as fit residuals and conditioning. If these fits are already much
better than the observation-based orbits, prioritize measurement-model/short-arc
limitations; if they are poor, investigate forces. Only then consider freeing
force parameters, with explicit conditioning and held-out checks. These fits
would be diagnostic uses of IGS, not station-derived products, and their states
must never enter the independent observation estimator. Longer arcs and memory
bounded QR scaling remain subsequent work.

### Original protocol (recorded before hourly IGS scoring)

Campaign: `claude/runs/20260911T172336Z-wet`. At protocol creation the two-node
oracle is running; no hourly-model IGS score has been read. This is a controlled
model experiment, not an accuracy acceptance or a new operational product.

### Hypothesis and controls

The fourteen-station three-hour fit is numerically stable but differs from IGS
rapid by 0.821140807 m RMS. Test whether allowing more within-arc wet-delay
variation improves the fitted GPS orbits. Keep the 2 August 12:00–15:00 GPST
fixture, 31 satellites, 37 solve epochs, observations/weights, force model,
orbit priors, clock datum and ambiguity handling fixed. Precise SP3/CLK products
remain forbidden estimator input. No station or satellite removal.

Each station's current two wet-delay endpoints become four nodes: endpoints
plus one and two hours into the arc. Fourteen stations add 28 retained parameters
(443 to 471); local clocks remain 1628. Endpoint names are unchanged; interior
names are `wet:STATION:hour1` and `wet:STATION:hour2`. All four remain retained
parameters in the owned square-root batch solve.

Keep the two original independent endpoint-level priors, sigma 0.3 m; do not add
independent level priors to the interior nodes. Replace the original end-to-end
difference sigma 0.03 m by three independent increment sigmas 0.03/sqrt(3) m
(17.3205 mm). The three-hour increment variance remains 0.03^2 m^2. Marginalizing
the interior nodes preserves the endpoint prior covariance; a straight-line
embedding preserves the original prior penalty. The added degrees of freedom
allow curvature between the endpoints under the stated increment constraints.
This is a controlled choice, not a calibrated or purportedly optimal noise model.

### Checks and predeclared evaluation

Before fitting, `claude.tools.wet_checks` passed:

- Endpoint marginal covariance equivalence, evaluated using square-root factors.
- Prior-energy equivalence for straight-line embeddings; interpolation partition
  of unity and linear reproduction at all 37 solve epochs.
- Exact reproduction of baseline residuals, sigmas and weighted objective when
  the old solution is embedded in the hourly basis.
- 764 finite differences of the actual code/phase link model against assembled
  wet Jacobian entries, at all knots and intermediate half-hours across stations.
  Maximum derivative discrepancy 1.5624e-6, below the predeclared 2e-5 tolerance.
- Actual matrix budget: 9634 rows including constraints, 471 retained parameters,
  1628 local parameters; estimated workspace 202.8806 MiB (limit 256 MiB).

Check guard: `runs/20260911T172113Z-8e1ba4f6`, 109.891 s, 221.516 MiB peak RSS,
15.986 GiB minimum available. Then reproduce the nominal two-node fit exactly
using the same experiment worker before running the hourly case.

Evaluate all 31 satellites on the same 403 native IGS samples, frozen formal-sigma
groups and determined-in-both intersection. Recompute Cartesian RMS independently
of the RAC scoring basis. Report every satellite's score change and trajectory
shift, station code/phase residuals, node estimates and departures from linear
wet delay. A >=5% pooled RMS reduction flags a candidate benefit; explicitly flag
every satellite worsening by >0.1 m. Neither criterion proves absolute accuracy
or robust multi-day improvement. Lower in-sample phase residuals alone are
insufficient. G18's baseline 2.403 m RMS remains a specific diagnostic target.

Stop on source/input mismatch, rejected line search, rank failure, timeout or
nonconvergence within four hourly iterations. Do not raise limits. Each numerical
worker uses the guard; the controller runs directly and launches workers serially.
The 2 GiB private-memory cap, one CPU/library thread, 10% CPU quota, 8 GiB available
reserve and 128 MiB scratch cap remain unchanged. No software installation.

### Implementation and method context

Support-local `claude/tools/wet_pilot.py` subclasses the pinned physical Pilot:
it changes wet interpolation, wet Jacobian columns and wet constraints. It reuses
the existing link model, dynamics, clock elimination, QR and nonlinear iteration
engine. Root estimator/test sources stay unchanged. Other helpers: `wet_step.py`,
`wet_checks.py`, `run_wet.py`, `evaluate_wet.py`. The archived baseline and source
hashes remain intact; no old fixture hashes are rewritten.

Piecewise-linear troposphere parameters are documented by the official
[Bernese features page, Modeling section](https://www.bernese.unibe.ch/features/features_fea.php).
The [TUG repro3 troposphere dataset description](https://repository.tugraz.at/records/gb7yh-px108)
documents two-hourly piecewise-linear nodes. These primary sources support the
parameterization family, not our particular one-hour spacing or constraint value.
Our test estimates parameters from the existing observations; it does not ingest
those external troposphere products or establish their rapid-latency suitability.

Opus's cold-start result was independently re-reviewed immediately before this
experiment: all-31 IGS RMS 0.821141679 m; maximum cold/warm trajectory difference
0.021678 mm and cold/perturbed 0.020064 mm. Review guards are
`runs/20260911T171827Z-d589f3c4` and `runs/20260911T171838Z-8ab5ff1d`, both passed.
The PDF, editable expert report and report manifest remain unchanged.

---

<!-- original: DYNAMICS_CEILING_RESULTS.md -->

## Fixed-force dynamic representation test — 11 September 2026

**The current force model can represent substantially better three-hour
trajectories than the observation-based solution for G18, G03 and G22.**
With only six initial-state components adjusted, withheld native IGS positions
are reproduced at 4.78, 3.03 and 0.95 cm RMS, respectively. The observation-based
solution differs by 2.32, 1.39 and 1.34 m on exactly those withheld epochs.

This is an IGS-dependent diagnostic, not a new independent POD product. It shows
attainable agreement in the existing dynamic trajectory family on this arc;
it does not establish a universal lower bound, prove a measurement-model bug,
or validate long-arc prediction. The two-node GUAM observation solution remains
the working baseline, and none of these reference-fitted states enters it.

### Frozen experiment

Same 2 August 2026 12:00–15:00 GPST interval and existing IGS rapid reference.
G18/G03/G22 were selected before fitting because of their observation-solution
errors; they are not a representative constellation-wide accuracy sample.

Use the exact production `Trajectory`, its 15-second Hermite grid, augmented
integration/settings, frames and physical force model. ECOM5 coefficients remain
fixed at [-1e-7, 0, 0, 0, 0] m/s^2. Estimate only the six initial-state components
at the existing reference epoch, starting from the original broadcast seed.
No orbit priors, force-parameter adjustments, fitted frame transformation,
residual removal or reference-state initialization.

For each satellite, use thirteen native 15-minute IGS positions. The fixed split
is seven training positions at half-hour intervals (including both endpoints),
and six interleaved quarter-hour positions withheld from fitting. At the existing
11:59:50 GPST reference epoch, these are elapsed times 10 + 900*k seconds,
k=0..12; even k train, odd k validate. No interpolated IGS positions are scored.
Only training positions enter `solve_fixed`; convergence and line search use
training residuals alone. The six withheld epochs assess interior representation,
not extrapolation beyond the fitted arc, and share the same correlated IGS product.

The 21 scalar training observations constrain six parameters. The solver uses
column-scaled pivoted QR, with 100 m position and 0.01 m/s velocity scales and a
relative singular-value rank threshold of 1e-11. It stops only when the proposed
initial-state displacement metric is below 0.1 mm and the predicted training
position-update RMS is below 0.01 mm. At most four iterations are permitted;
no rejected material update is accepted and no tolerance was relaxed.

### Results

| SV | Reference fit: train RMS | Reference fit: withheld RMS | Reference fit: all 13 RMS | Observation fit: same withheld RMS | Observation fit: all 13 RMS |
|---|---:|---:|---:|---:|---:|
| G18 | 0.062507 m | **0.047806 m** | 0.056202 m | 2.319450 m | 2.402518 m |
| G03 | 0.040555 m | **0.030289 m** | 0.036180 m | 1.391904 m | 1.382221 m |
| G22 | 0.011644 m | **0.009486 m** | 0.010702 m | 1.343961 m | 1.331837 m |

All three fits have rank six and converge in one accepted full update followed
by a stationary check. Scaled design condition numbers are 11.47, 11.61 and 11.90.
These are conditions of the direct-position diagnostic, not of the station
observation estimator. All meet the predeclared <0.1 m withheld RMS diagnostic
flag. It is not an independent POD acceptance threshold.

The same unmodified forces that accompany metre-level station-derived errors
support centimetre-level withheld position fits here. Therefore a gross inability
of these fixed-force trajectories to follow IGS is not the dominant explanation
for these three satellites' present errors. The station observations constrain
line-of-sight combinations with clocks, ambiguities and atmospheric terms;
direct three-coordinate IGS position fitting provides much stronger information.
Short-arc geometry, measurement noise, nuisance-parameter correlations and model
errors remain possible contributors. This experiment does not separate them.

### Independent checks

- Reintegrating the archived observation-derived initial state reproduces its
  trajectory states bitwise on all 37 solve epochs, separately for each satellite.
  This verifies the same trajectory family and numerical settings are used.
- Synthetic same-model closure uses seven training epochs from a deliberately
  offset orbit and begins from broadcast. All-epoch maximum recovery discrepancy
  is 8.51e-8 m; withheld RMS is 5.23e-8 m. This tests the implementation, not real
  orbit accuracy.
- 234 central finite-difference checks cover all six initial-state derivatives
  at all thirteen epochs. Maximum position discrepancy for the stated 1 m or
  1 mm/s perturbations is 1.70e-6 m, below the predeclared 1e-4 m tolerance.
- Cartesian/ECEF and inertial scoring agree within 20 nm. The independent review
  reopens the pinned native reference samples, checks the split and transformations,
  reintegrates the final states bitwise and reconstructs scores.
- A separate SVD least-squares stationarity check agrees on rank and conditioning;
  remaining initial-state displacement metrics are 0.163, 0.154 and 0.054 micrometres.
- Source/input/baseline/report hashes pass. Root estimator and tests are unchanged;
  validation is the focused synthetic/derivative/identity and independent audit
  suite above, rather than a rerun of the unchanged 102 root tests.

### Evidence and resources

Archive: `claude/runs/20260911T211901Z-dynamics-ceiling/`, status
`fixed_force_reference_diagnostic_complete_not_independent_POD`.

- `checks/diagnostic.json`: synthetic recovery and derivative checks.
- `G18/`, `G03/`, `G22/`: each contains `diagnostic.json`, `diagnostic_fit.npz`,
  guard result and logs. The NPZ name and status explicitly distinguish these
  reference-dependent diagnostic fits from observation-estimator checkpoints.
- `review/review.json`: independent reference, reintegration, score and SVD audit.
- `validation.json`: protocol declared before real fits, resource results,
  input baseline identity, pinned sources and artifact hashes; source snapshots
  under `source/`.

Original synthetic-check guard: `runs/20260911T211659Z-e424eb44`. Support-local
helpers are `fixed_force_fit.py`, `dynamics_ceiling_step.py`,
`dynamics_ceiling_review.py` and `run_dynamics_ceiling.py` in `claude/tools/`.
Do not use `customkf/fitting.py`'s default as an equivalent experiment: it also
fits force parameters, whereas this diagnostic does not.

Total guarded work **35.925 seconds**, including 14.110 seconds of synthetic and
derivative checks, three approximately 5–6 second real fits and the independent
review. Peak sampled RSS **171.152 MiB**; minimum available memory **16.120 GiB**.
Workers were serial under the unchanged guard: 2 GiB private-memory limit,
one CPU/library thread, 10% machine CPU quota, 8 GiB available-memory reserve,
128 MiB scratch. Fit/check workers had <=300 s caps, review <=120 s. Nothing
remains running. No installation or expert-report/PDF update.

### Recommended next experiment

Prioritize diagnosing the observation solution before adding force parameters.
Measure how strongly the network observations distinguish the accepted orbit
states from these much closer-to-IGS diagnostic states, after re-estimating the
same clock, ambiguity and wet-delay nuisance parameters. Use a controlled,
explicitly reference-dependent cost/residual diagnostic, with the original
observations and weights unchanged. Report the objective change, orbit-direction
uncertainty and which station/epoch/satellite groups contribute, rather than
treating a raw residual increase as evidence of bad stations. A weak cost penalty
would support limited short-arc information; a concentrated coherent penalty
would identify a modeling/data hypothesis to test. Neither alone proves cause.

An optional extension to the remaining satellites can map whether this finding
generalizes; it need not block the focused observation-information diagnostic.
Do not initiate a force-parameter sweep or feed any reference-fitted states into
the operational/independent estimator. Longer arcs, memory-bounded scaling and
rapid-vintage certification remain open.

---

<!-- original: OBSERVATION_PROFILE_RESULTS.md -->

## Observation information diagnostic — results, 11 September 2026

**Completed: the station observations prefer the accepted trajectories, but
orbit/clock/nuisance correlations substantially reduce their ability to distinguish
the closer-to-IGS trajectories on this three-hour arc.** Substituting the G18/G03/G22
reference-fitted trajectories raises the weighted objective by 63.2472 after
nuisance refitting. Allowing other satellite orbits to respond reduces the
linearized penalty to 22.4467. This is not a calibrated significance test and
does not prove either a station fault or a measurement-model bug.

### Main results

| Comparison | Weighted total cost | Increase |
|---|---:|---:|
| Accepted observation baseline | 1685.735249 | — |
| G18 substituted; nuisance refit, linearized | 1729.409799 | 43.674550 |
| G03 substituted; nuisance refit, linearized | 1694.684056 | 8.948807 |
| G22 substituted; nuisance refit, linearized | 1699.044095 | 13.308846 |
| All three substituted; nuisance refit, linearized | 1748.982250 | 63.247001 |
| All three substituted; nonlinear nuisance check | 1748.982461 | **63.247213** |
| All three substituted; other orbits also free, linearized | 1708.181900 | **22.446652** above unrestricted linear optimum |

The baseline's unrestricted remaining correction would reduce cost by only
7.15e-7. Its fixed-orbit nuisance profile reduces cost by 7.08e-7 with maximum
nuisance update 1.44 micrometres, verifying baseline stationarity. The individual
penalties are not additive because the parameters are coupled.

The joint eighteen-component covariance calculation independently gives
22.446652240376, agreeing with the other-orbits-free QR cost difference to about
5e-13. All correlations in that selected covariance submatrix are retained.
The latter case is linearized only; its other orbit corrections have not been
accepted as a nonlinear solution or scored as an orbit product.

### What absorbs the orbit substitution

The largest nuisance change is G18's satellite clock at the last epoch:
**+2.90049 m in range units**. These are estimated clock offsets, not a measured
hardware-clock event. The actual residual response is much smaller:

| Observation type | Rows | Baseline RMS | Substitution RMS | RMS residual shift | Weighted observation-cost increase |
|---|---:|---:|---:|---:|---:|
| Code | 4726 | 887.400 mm | 888.436 mm | 52.524 mm | 1.423028 |
| Phase | 4652 | 10.6444 mm | 11.2374 mm | **3.2353 mm** | **58.892891** |

The observation penalty is 60.315920. The remaining 2.931293 comes from priors,
mostly wet-delay continuity: wet-change cost rises from 5.408270 to 8.251733;
wet-level cost from 12.438156 to 12.525996. Orbit-prior cost is tiny and decreases
from 0.000062714 to 0.000053003. Strong orbit priors are not causing this preference.

This confirms a practical distinction: metre-level differences between fitted
orbits can coexist with small millimetre-scale phase-residual shifts once clocks,
wet delays and ambiguities readjust. The supplied data/model do prefer the
accepted orbits; the test does not show the alternatives are indistinguishable.
It shows why a small phase RMS by itself is insufficient evidence of accurate orbits.

### Where the cost difference appears

These are signed contributions to the **observation** objective change, after
the joint network nuisance adjustment; they are not causal station fault scores.

| Station | Weighted observation-cost change |
|---|---:|
| GUAM | +18.933711 |
| KOUG | +11.609183 |
| FAA1 | +9.325533 |
| HOB2 | +4.45 |
| NNOR | +4.31 |
| DJIG | +4.26 |
| YELL | +4.13 |
| KOUR | **-3.318379** |

Other stations and every satellite/epoch are retained in the machine-readable
review. Largest station-hour contributions include GUAM 14:00–15:00 (+10.72),
KOUG 12:00–13:00 (+10.23), GUAM 12:00–13:00 (+5.54), and FAA1 13:00–14:00 (+5.10).
Hour bins are half-open except the final one includes the 15:00 endpoint.
Other satellites' residuals also change because they share nuisance parameters.
Do not remove GUAM/KOUG/FAA1 on this evidence. KOUR is not driving the positive
cost penalty in this experiment; its historical residual issue remains separate.

### Verification and limitations

The nonlinear joint calculation retained the linear nuisance solution at the
unchanged stopping criterion. Its proposed remaining nuisance update was
1.64 micrometres, with predicted reduction and whitened direction norm squared
6.41e-7. The nonlinear cost exceeds the linear prediction by only **0.00021139**,
well below the predeclared 0.01 tolerance; the largest nonlinear-minus-linear
residual difference is **1.94 micrometres**.

Baseline residuals/sigmas were bitwise reproduced; retained covariance and its
profile-cost identity passed. Independent review reconstructed observation and
prior objectives, checked every residual label/sigma and group-cost sum, verified
replacement states against their archived reference fits, and confirmed the other
28 orbit states and trajectories remained bitwise unchanged. Root sources/tests
were unchanged; these focused checks validate the new support diagnostic. The
existing 102 root tests were not rerun.

No calibrated chi-square probabilities are reported. Measurement sigmas,
correlations and prior stochastic models have not been empirically calibrated.
The three substituted satellites were deliberately selected; this is not a
constellation-wide reference constraint. The reference-fit states share IGS
product errors and are themselves imperfect representations. The primary result
conditions on the other 28 accepted orbits; only the additional linear profile
relaxes that condition. No new independent POD product is produced.

### Evidence, resources and next action

Archive `claude/runs/20260911T213336Z-observation-profile`, status
`observation_profile_complete_reference_dependent_not_POD`:

- `prepare/profile.json` and `linear_profiles.npz`: all linear profiles and
  parameter/residual changes, covariance identity and baseline stationarity.
- `iteration-0/profile.json` and `diagnostic_nuisance.npz`: nonlinear joint check.
- `review/review.json`: objective decomposition, station/type/satellite/epoch/
  station-hour contributions, nuisance changes and invariance checks.
- `validation.json` and `source/`: frozen protocol, source hashes/snapshots,
  input identities, guard results and artifact hashes.

Successful campaign **254.812 s (4.25 min)**. Including the preserved export-failure
run, actual guarded work was **381.640 s (6.36 min)**. Peak RSS including that
attempt: **382.727 MiB**; minimum available memory **15.683 GiB**. No limits changed.
The nuisance-only reduced QR workspace is 108.854 MiB; the other-orbits-free
linear comparison 181.921 MiB, both below the original 256 MiB workspace limit.
All numerical jobs are finished. Baseline and expert report/PDF remain unchanged.

**Recommended next action: a bounded arc-length experiment.** Compare three-hour
and six-hour solutions at a common ten-minute solve cadence, alongside the existing
three-hour/five-minute baseline. This separates the effect of coarser sampling
from the effect of longer tracking, while targeting about 37 epochs for the
six-hour solve rather than doubling the observation-row count. Preflight actual
rows/ambiguities/workspace under the existing limits; do not assume they fit.
Retain native 30-second slip tracking and compare identical first-three-hour IGS
epochs, with full-arc and formal-uncertainty results reported separately.
Inspect the newly included station-time data using the existing quality rules.
The current fixture builder explicitly supports only five-minute 12/37-epoch
nominal cases; this experiment requires a validated new input profile, not an
existing CLI flag. No implementation or result for that extension is claimed here.

This is preferable to another station-removal loop or immediate extra force
parameters: longer tracking directly tests whether short-arc orbit/clock/nuisance
coupling is limiting the observation solution. It may fail to improve accuracy;
if so, the signed station/time residual evidence above provides specific model
hypotheses without identifying any station as faulty in advance.

### Original protocol and failed-attempt record

Status at protocol creation: preparation running after a result-export bug was
fixed; no numerical result is accepted yet. The failed guard is retained as
`runs/20260911T212853Z-f3dd81c9`, including its source snapshot. Its duplicate
NPZ keyword was a reporting error, not a QR or covariance failure. Limits and
numerical choices are unchanged on the retry.

### Question and fixed controls

The same force model can reproduce withheld IGS positions to centimetres for
G18/G03/G22, while the observation-derived orbits differ by metres. Test how
strongly the existing station observations distinguish these trajectories after
clock, ambiguity and wet-delay adjustments. This is an explicitly reference-
dependent diagnostic, not a new independent POD solution or an accuracy gate.

Use the exact fourteen-station GUAM fixture, two-node wet model, original rows,
weights, priors, clock datum, ambiguity origins, windup branches, physical model
and three-hour arc. The three replacement initial states come from the pinned
reference-only campaign `claude/runs/20260911T211901Z-dynamics-ceiling`.
Other 28 orbit states remain at their accepted observation-based values for the
primary experiment. No observations, stations or satellites are removed.

### Predeclared comparisons

1. Reproduce the baseline residuals and sigmas exactly and its retained covariance
   at the same linearization. Profile the baseline with all orbits fixed; any
   remaining nuisance correction must be <1 mm and reduce cost by <1e-5.
2. In that linearization, substitute each of G18/G03/G22 individually and all
   three jointly, solving anew for the 257 retained nuisance parameters and
   1628 epoch-local clocks. Fixed orbital displacement contributes to the
   right-hand side, including its original prior cost. Use the existing reduced
   QR; no normal equations or fitted reference orbit constraints are introduced.
3. Separately allow the other 28 orbits to adjust in a joint linearized profile.
   Check the cost above the unrestricted local optimum against the Mahalanobis
   distance from the selected eighteen-component covariance submatrix, accounting
   for the baseline's small remaining Newton step. This checks the algebra and
   distinguishes fixed-other-orbit and correlated-orbit profiles. It is not a
   nonlinear estimate of those other orbits.
4. Initialize a nonlinear joint substitution with the linear nuisance solution.
   Hold every orbit fixed and relinearize the full original observation model;
   re-estimate nuisance parameters only. Stop only when the maximum nuisance
   correction is <1 mm and both predicted reduction and squared whitened
   direction norm are <1e-5. At most three <=300 s iterations. Reject any
   material update that does not reduce the actual objective.
5. Independently reconstruct the objective, check reference-state substitution
   and bitwise identity of the other orbit trajectories, and compare nonlinear
   and linear joint objectives within a predeclared 0.01 tolerance. Report
   differences by observation kind, station, satellite, epoch and station-hour.

Cost means the sum of squared residuals divided by the unchanged assumed
variances, plus original prior penalties. Priors and observation contributions
are reported separately. Cost is not an orbit RMS. Group contributions may be
negative and do not identify causal bad stations. No chi-square probabilities
or sigma significance claims will be made: the assumed measurement variances
and correlations have not been empirically calibrated.

All numerical work is serial through `customkf.guard`, with the unchanged 2 GiB
private-memory cap, one CPU/library thread, 10% CPU quota, 8 GiB available reserve
and 128 MiB scratch cap. Review workers <=120 s. No software installation.
The worker does not open precise SP3/CLK files directly, but deliberately reads
IGS-dependent diagnostic NPZ states; absence of direct SP3 reads does NOT make
the calculation independent. Results stay under `claude/runs/` and never seed
the observation-estimator baseline. Expert report/PDF files remain unchanged.

---

<!-- original: ARC_LENGTH_RESULTS.md -->

## Matched cadence / arc-length experiment

Started 11 September 2026 local time (12 September UTC). Campaign:
`claude/runs/20260912T021739Z-arc`. Status: completed and independently audited;
diagnostic improvement, not accuracy acceptance. No numerical worker is active.

### Result

Longer tracking improves the station-derived solution substantially, even after
separating the loss from reduced observation density.

| Fit | RMS on identical first-three-hour IGS samples |
|---|---:|
| Original 3h / 5min | 0.821141 m |
| New 3h / 10min | 0.981968 m |
| New 6h / 10min | **0.543656 m** |

At fixed ten-minute cadence, extending tracking reduces RMS **44.636%**.
It improves on the original, denser three-hour baseline by **33.793%**, despite
the density control alone worsening RMS by 19.586%. All three retain 31 satellites
in the unchanged diagnostic determined group; the gain does not come from dropping
weak satellites. Common-domain radial/along/cross RMS is 0.261/0.294/0.376 m;
orbit-only URE under the existing convention is 0.264 m.

Full six-hour RMS is **0.547216 m** on 775 native samples, with radial/along/cross
0.269/0.295/0.374 m and orbit-only URE 0.272 m. This different domain is reported
separately. These results remain far above the desired centimetre-level agreement.

Relative to the original 3h/5min baseline, 23 satellites improve and 8 worsen.
The largest gains include G18 (2.403 -> 0.622 m), G22 (1.332 -> 0.130 m),
G24 (1.147 -> 0.409 m), G10 (0.754 -> 0.151 m), and G03 (1.382 -> 0.823 m).
G26 remains near one metre (1.044 -> 0.993 m). The six regressions above 0.1 m are:

| Satellite | Original 3h/5min | New 6h/10min | Increase |
|---|---:|---:|---:|
| G04 | 0.608 m | 0.873 m | 0.265 m |
| G08 | 0.294 m | 0.479 m | 0.185 m |
| G19 | 0.662 m | 0.975 m | 0.313 m |
| G20 | 0.234 m | 0.384 m | 0.151 m |
| G21 | 0.251 m | 0.516 m | 0.265 m |
| G23 | 0.652 m | 1.191 m | 0.539 m |

At fixed ten-minute cadence, >0.1 m regressions are G19, G21, G23 and G27.
Every per-satellite score, coverage reason and formal sigma for both domains is
in `evaluation/evaluation.json`; no alignment or exclusion was applied.

GUAM's retained 17:30 G27 phase residual is +51.8 mm (2.24 assumed sigma),
versus the earlier daily-PPP flag of +129.5 mm. G07 at 17:20 is +20.7 mm
(1.36 sigma). The sampled episode does not reproduce the large daily-PPP
normalized flags in this fit; it does not prove the station has no model error,
because orbit and nuisance estimates can absorb error. GUAM full-arc phase RMS
is 10.17 mm. No station removal is justified by this check alone.

### Verification and measured resources

- All **105 regression tests** passed.
- The original 3h/5min states, residuals and weights reproduce **bitwise**, with
  zero objective difference under the new source revision.
- All **579 wet derivative entries** passed finite differences; maximum error
  1.84e-6. The original two-node prior marginal and prefix basis were verified.
- Each fit accepted one full update and then passed stationarity. Final proposed
  trajectory bounds are 0.057 mm (3h) and 0.052 mm (6h); accepted states and
  residuals remain bitwise unchanged at the stationary check.
- Independent Cartesian scoring agrees with RAC scoring within 2e-8 m.
  Independently reconstructed objectives, sigma/row labels, positive-definite
  covariance, source hashes and report hashes all passed.
- The longer environment changes the common-prefix initial trajectory by only
  **7.45e-9 m**. Thirteen early phase rows become eligible when their ambiguity
  arcs acquire the required third retained sample after 15:00. This is a disclosed
  consequence of the unchanged minimum-arc rule, not a manual data-selection change.
- Total guarded time including both preparations, checks, solves, evaluation and
  independent audit: **1432.015 seconds (23.87 minutes)**. The longest worker was
  278.532 seconds, inside the unchanged 300-second cap.
- Peak job private memory **383.23 MiB**; sampled RSS **409.42 MiB**; minimum
  system available memory **12.840 GiB**, above the 8 GiB reserve. No limit raised.

Audit: `review-20260912T023747Z/manifest.json` and `review/review.json` beneath
that follow-up directory. Its separate manifest preserves the main campaign hash.
Full sources, inputs/checkpoint hashes, guard results and numerical histories
are in the main campaign. The expert PDF/source/manifest were left unchanged.

### Recommendation

Use the six-hour case as the working comparison for the next diagnostic, while
preserving the original GUAM baseline. Duration is now a demonstrated contributor;
neither station count alone nor numerical convergence explains the remaining error.

Next, extend the reference-only fixed-force representation test to this exact
six-hour interval, with native half-hour training and withheld quarter-hours.
The previous three-hour 5.01 cm result cannot establish the six-hour force floor.
Prioritize G23, G19, G04, G26 and G03, but retain all 31 in the pooled conclusion.
If six-hour representation remains much better than station-derived orbits,
return to measurement/nuisance coupling; if it grows materially, test physically
motivated force parameters before extending the arc again. No automatic station
exclusion or weight tuning against this day's IGS scores. The Opus handoff gives
the bounded protocol; no additional numerical job is running.

### Question and fixed protocol

Does extending station tracking from 12:00–15:00 to 12:00–18:00 GPST on
2 August 2026 improve GPS orbit agreement with IGS rapid? Compare both at
ten-minute solve cadence, retaining the three-hour/five-minute GUAM baseline
as a separate density control. All comparisons use raw, unaligned positions.
The primary domain is the identical first-three-hour set of 403 native IGS
samples (31 satellites, 13 epochs). The full six-hour domain, 775 samples,
is reported separately and is not compared directly with the old 403-sample RMS.

Both new cases start from broadcast seeds with zero fitted corrections.
IGS SP3 and clocks are prohibited from the estimation worker and opened only
by the evaluator. Fourteen stations, signals, native 30-second slip tracking,
fixed weights, force parameters, station models, BRUX clock datum and orbit
priors remain those of the GUAM baseline. G13 retains its nominal-navigation
rejection. Preparation verifies identical shared rows, station metadata and
seeds; shared sigmas agree within 4e-15 m in the longer environment.

The original wet nodes remain at 0h and 3h with their original level priors
(0.3 m each) and difference prior (0.03 m). The six-hour case appends a 6h
node with only a 0.03 m 3h-to-6h continuity equation. Marginalizing that node
preserves the original two-node prior exactly. This avoids stretching the
original atmospheric line across six hours. The same minimum of three retained
samples per phase ambiguity arc still applies; any early phase rows newly
enabled by longer tracking must be disclosed.

The predeclared candidate-benefit flag is a 5% pooled RMS reduction on common
samples, with all per-satellite regressions exceeding 0.1 m disclosed.
The unchanged 10 m formal initial-position sigma rule separates diagnostic
determined/poorly determined groups; it is not a measured accuracy bound.

The known GUAM daily-PPP residual episode at 17:20–17:35 enters the extended
interval. Retain its observations and inspect postfit residuals; a PPP flag is
not by itself proof of station hardware failure or permission to trim scores.

### Resource preflight

| Case | Code / phase rows | Retained parameters | Local clocks | Estimated workspace |
|---|---:|---:|---:|---:|
| Existing 3h / 5min | 4726 / 4652 | 443 | 1628 | 189.9 MiB |
| New 3h / 10min | 2426 / 2340 | 418 | 836 | 97.7 MiB |
| New 6h / 10min | 4731 / 4593 | 510 | 1628 | 219.1 MiB |

All remain below the unchanged 12,000-row / 900-retained-column / 256 MiB
workspace ceilings. Each numerical worker runs serially through `customkf.guard`:
2 GiB aggregate private-memory cap, one CPU/library thread, 10% CPU quota,
8 GiB available-memory reserve, 128 MiB scratch, and at most 300 seconds.
No software installation or limit increase. The direct controller must not be
nested inside a guard. Archived sources include the explicit, narrow
`nominal-cadence` preparation extension; historical source hashes are untouched.

### Reading the additional Opus experiments

Opus reports all-constellation three-hour reference-only fits at 5.01 cm
withheld RMS, the two-hour observation variant at 2.513 m over the original
three-hour scoring span, a uniform phase-sigma rescale at 0.962 m, and PIMO at
0.818584 m versus 0.821141 m. See the respective notes under `claude/`.
These support prioritizing arc length but do not exhaust alternative force,
weighting or network models. PIMO supplies little new simultaneous coverage,
so its small pooled gain cannot establish general geometry saturation.

The earlier Opus elevation interpretation is reversed: normalized residual
RMS grows toward low elevations, suggesting a steeper relative increase than
the assumed curve, if residual scatter is used as a noise proxy. Postfit
scatter also depends on leverage and nuisance fitting, so it is not a direct
measurement of observation noise. One correlated day's formal-error ratios
do not calibrate coverage probabilities, and a common Helmert fit cannot
exclude every station-frame or time-varying EOP mechanism. None of these
diagnostics changes this experiment's fixed weights or unaligned scoring.

The expert PDF/source/manifest remain unchanged under the agreed reporting cadence.

---

<!-- original: FORCE_PARAMETER_PROTOCOL.md -->

## Six-hour force-parameter diagnostic: frozen protocol

Declared 12 September 2026 UTC, before running either free-force variant.
This follows the independently reproduced Opus six-hour result (19.6806 cm
withheld fixed-force RMS, versus 53.6127 cm station-fit RMS on the same epochs).
Astra's repeat audit is `runs/20260912T030715Z-c90c6025` (46.547 s, 128.29 MiB
peak job memory, >=17.338 GiB available). Original archives remain unchanged.

### Interpretation correction

The fixed-force representation residual is material, but it is not a proven
physical-error floor. The fit minimizes training error, not withheld error;
it is conditioned on IGS and this parameterization. The squared RMS ratio
(13.5%) is not an additive variance attribution: the difference between the
station orbit and fitted reference orbit can correlate with the reference-fit
residual. Likewise, a ratio >=0.40 does not establish that forces dominate.
The satellite groups in Opus's note are exploratory priorities, not causal labels.
G19's small representation residual supports investigating observation/nuisance
coupling but does not prove force errors cannot bias a station-derived estimate.

### Fixed choices

Use the exact six-hour fixture, model and broadcast seeds from
`claude/runs/20260912T021739Z-arc/six-prepare/fixture.json`.
Reference and comparison orbits are the pinned Opus six-hour diagnostic and
the station fit `six-1/solution.npz`. The 25 native IGS epochs span 12–18 GPST
on 2 August 2026. Train on even indices (13 half-hours); withhold odd indices
(12 quarter-hours). Report both groups, all 25 and the first 13 separately.

Two variants, each also estimating the six initial-state components:

1. **D0 only:** estimate the constant Sun-direction coefficient; hold the other
   four at zero. Seven estimated parameters total.
2. **Full ECOM5:** estimate D0, Y0, B0, Bc1, Bs1. Eleven total.

This is the existing reduced ECOM basis, not newly chosen harmonics. Initial
coefficients remain [-1e-7,0,0,0,0] m/s². The implemented D axis points toward
the Sun, so the nominal direct coefficient is negative. B harmonics use the
existing ascending-node argument convention; no coefficient convention change.
Retain shadow, inverse-square scaling, gravity, tides, relativity, integration
tolerances and 15-second Hermite interpolation exactly. Fit by scaled pivoted
QR with reintegration, training-only line search, no priors and no regularization.

The five reduced ECOM terms are documented in Duan and Hugentobler (2021),
[Enhanced solar radiation pressure model for GPS satellites considering various physical effects](https://link.springer.com/article/10.1007/s10291-020-01073-z),
Introduction, paragraphs defining the DYB frame and reduced ECOM. Arnold et al. (2015),
[CODE's new solar radiation pressure model for GNSS orbit determination](https://link.springer.com/article/10.1007/s00190-015-0814-4),
Abstract, motivates structured harmonics and also documents limitations of the
older ECOM. These are established-model references, not a claim that our reduced
implementation matches a current analysis center's entire force/attitude model.

### Scope, checks and decision rules

First validate exact fixed-coefficient trajectory/STM equivalence, independently
reintegrated state and force partials, synthetic recovery of nonzero coefficients,
and reproduction of archived fixed-force fits. Then run both variants for
G04 (largest fixed-force residual), G19 (small fixed-force residual but large
station error) and G23 (largest station error/regression). These are deliberately
selected diagnostic cases; no three-satellite pooled claim is constellation-wide.
The same two variants and criteria extend unchanged to all 31 satellites for Opus.

Rank threshold: singular value > largest*1e-11 in declared parameter scaling.
Do not silently regularize a rank failure. Report scaled condition number and
flag >1e8, coefficient magnitudes >1e-6 m/s², and all withheld regressions >1 cm
relative to the fixed-force control. A >=50% withheld RMS reduction flags useful
representation improvement only; it does not authorize adding parameters to POD.
Report parameter/initial-state coupling and coefficient uncertainty scales as
unit-weight diagnostics, not calibrated physical uncertainties.

The same day's holdouts have already informed this research direction: they
remain withheld from each fit but are not a fresh, untouched model-selection
test. Another day/arc will be required before claiming generalization. Keep all
variants and failures; do not select coefficients per satellite to optimize scores.

No reference-fitted state or coefficient may seed station POD. No root estimator,
station set, weights, data or expert-report changes. New tools/results under
`claude/`. All numerical workers serial through the existing guard, <=300 s,
2 GiB job limit, one thread, 10% CPU quota, 8 GiB available reserve. No limit raised.
Each completed worker must have a manifest/checkpoint entry for safe continuation.

---

<!-- original: FORCE_PARAMETER_RESULTS.md -->

## Force-parameter diagnostics and transition to station estimation

12 September 2026. The three-satellite Astra pilot and Opus's all-31 extension
are complete. The unchanged fixed-force representation gives 0.196806 m
withheld RMS on 372 native IGS samples. Estimating D0 plus initial state reduces
that to **0.023621 m**; full ECOM5 plus initial state gives **0.008425 m**.
The station-derived six-hour orbit remains **0.536127 m** on those same withheld
epochs until the new station-only experiment is evaluated.

Evidence: `claude/runs/20260912T031407Z-force-parameters` (Astra pilot),
`claude/runs/20260912T032414Z-force-parameters` (all 31, unchanged controller),
and `claude/runs/20260912T033519Z-force-all-review` (Opus independent review).
Astra reran all 62 free-case checks in `runs/20260912T144615Z-03649cb6`:
raw Cartesian RMS, holdout indices, bitwise reintegration, independent SVD
stationarity/covariance and sources all pass. Rerun cost 93.985 s, 138.47 MiB
peak job memory, >=15.912 GiB available. The numerical wrapper checks also
passed 198 independently reintegrated derivative entries (maximum 1.32e-7 m
displacement discrepancy) and synthetic coefficient recovery to 3.31e-13 m/s².

This demonstrates that freeing existing force coefficients can represent this
six-hour IGS arc closely. It does not establish physical force truth or that
station observations can determine those coefficients. The fixed nominal D0
was too restrictive for this representation test; broader statements that all
remaining station error must come from measurement models are premature.
Strong state/force coupling in the reference fits reinforces the need to test
station estimation directly. The frozen choices and literature rationale are
in `FORCE_PARAMETER_PROTOCOL.md`; full per-satellite results are in
`claude/FORCE_PARAMETER_ALL31.md` and the machine archives.

### Next experiment, completed

The station-only D0 protocol is in `D0_POD_PROTOCOL.md`. No reference-fitted
coefficients or states seed it. Preparation passed at **541 retained parameters,
233.102 MiB estimated workspace**. Its zero-D0-correction embedding reproduces
the original station baseline bitwise and all 48 observation partial checks pass.
The completed campaign is `claude/runs/20260912T145220Z-station-d0` with separate
bounded linearization and trial workers. The actual station fit improved common
RMS **0.543656 -> 0.441752 m** (18.744%) and full-six-hour RMS
**0.547216 -> 0.440239 m** (19.549%), with six >0.1 m common-domain regressions.
See `D0_POD_RESULTS.md` for all caveats, validation and resources. No job is active.
The Opus handoff now prioritizes independent review and cold-start/orbit-prior
robustness. No root estimator, data or expert-report files were changed.

---

<!-- original: D0_POD_PROTOCOL.md -->

## Station-only D0 pilot: declared before fitting

12 September 2026 UTC. Fixed six-hour baseline:
`claude/runs/20260912T021739Z-arc/six-1` (0.543656 m common first-three-hour
IGS RMS; 0.547216 m full six-hour RMS). Opus's completed reference-only
force experiment demonstrates representability, not station observability.

Add exactly one estimated D0 correction per satellite, for all 31 satellites.
The correction is expressed in units of 1e-7 m/s²; total D0 starts at -1e-7.
Y0/B0/Bc1/Bs1 stay zero. No D0 prior; retain all original orbit/wet priors,
stations, observations, sigma values, slip/ambiguity rules, nominal-navigation
eligibility and BRUX clock datum. Keep six-hour tracking and ten-minute solve
cadence. No IGS-derived states or force coefficients enter initialization or fit.
Warm-start from the existing station-only solution with D0 corrections exactly
zero. Both the old solution and new outputs remain archived; no automatic
baseline replacement. New code is isolated under `claude/`.

First require bitwise nominal trajectory equivalence, embedded baseline
residual/cost agreement, independent force-column finite differences and an
actual matrix-size preflight. Expected retained count is 541 rather than 510.
Do not raise the 256 MiB workspace, 900-column, 12,000-row or OS guard limits.
Every numerical worker is serial, <=300 s, 2 GiB job memory, one thread,
10% CPU quota and 8 GiB available reserve. At most four nonlinear iterations.
If runtime does not fit, preserve the failure and split work; do not raise caps.

Score only after convergence, on the same 31 satellites / 403 first-three-hour
native IGS samples, and separately all 775 six-hour samples. Disclose every
>0.1 m per-satellite regression, coefficient magnitude and formal sigma, and
the unchanged 10 m initial-position determinability classes. A >=5% common-domain
RMS reduction is a candidate-benefit flag, not an operational or accuracy gate.
Stationary step/cost, residual labels, independent Cartesian scoring and archive
hashes must pass. Any apparent benefit still needs another day and start/prior
sensitivity checks before adoption. Do not tune priors to this day's IGS scores.

### Optional Opus supporting diagnostic

Review the all-satellite reference results and preserve the distinction between
representability and station estimability. A projection of station-orbit errors
onto *force columns alone* is not a POD benefit bound: initial states and nuisance
parameters change too. If doing a cheap evaluator-only projection, show the
initial-state span first, then the incremental force span after projecting out
initial states (rank-revealing QR/SVD), and the combined span. Use consistent
linearization, native epochs and units; verify the Pythagorean decomposition and
report rank/conditioning. Do not equate any span fraction with causal attribution
or achievable station-based improvement. This is optional and does not block
the direct, station-only D0 experiment.

No root estimator, data files or expert-report files are changed by this pilot.

---

<!-- original: D0_POD_RESULTS.md -->

## Station-only D0 experiment: completed 12 September 2026

**Subsequent replication:** August 3 failed the predeclared 3D benefit flag:
0.6208 -> 0.7135 m common and 0.6229 -> 0.6938 m full, while radial RMS and URE
improve. See `D0_DAY215_RESULTS.md`. The August-2 numbers below remain valid;
they do not justify adopting D0 as a generally better station estimator.

Estimating one direct solar-pressure coefficient per satellite improves the
station-derived six-hour orbit on this arc. The coefficients were estimated
from station observations, with no IGS-derived force coefficient or orbit seed.
This is a candidate improvement. Independent review and start/prior robustness
now pass; the subsequent separate-day result is recorded above.

| Domain, identical native IGS epochs | Fixed D0 | Estimated D0 | Reduction |
|---|---:|---:|---:|
| First three hours, 31 satellites / 403 samples | 0.543656 m | **0.441752 m** | **18.744%** |
| Full six hours, 31 satellites / 775 samples | 0.547216 m | **0.440239 m** | **19.549%** |

All 31 remain in the unchanged diagnostic determined group. No alignment,
station exclusion, residual deletion or per-satellite model selection.
Common-domain radial/along/cross RMS changes from 0.261/0.294/0.376 m to
**0.169/0.297/0.281 m**. Orbit-only URE under the existing convention changes
from 0.2643 m to **0.1753 m**. This remains above the desired centimetre agreement.

Twenty-one satellites improve on the common domain and ten worsen. Examples:
G23 1.191 -> 0.265 m; G14 0.842 -> 0.165 m; G03 0.823 -> 0.238 m;
G04 0.873 -> 0.400 m; G18 0.622 -> 0.358 m. G19 and G26 remain large at
0.836 m and 0.819 m. All six common-domain regressions exceeding 0.1 m:

| Satellite | Fixed D0 | Estimated D0 | Increase |
|---|---:|---:|---:|
| G01 | 0.448 m | 0.664 m | 0.215 m |
| G02 | 0.221 m | 0.357 m | 0.136 m |
| G07 | 0.362 m | 0.658 m | 0.297 m |
| G12 | 0.231 m | 0.368 m | 0.138 m |
| G22 | 0.130 m | 0.532 m | 0.402 m |
| G27 | 0.646 m | 1.099 m | 0.454 m |

Full-domain >0.1 m regressions are G07/G08/G10/G12/G22/G27. The machine
evaluation contains every per-satellite result, coverage reason, coefficient,
formal uncertainty and station residual summary; all cases are retained.

### Method and verification

The frozen design is `D0_POD_PROTOCOL.md`: six hours, ten-minute solve cadence,
same fourteen stations and inputs, same orbit/wet priors, unchanged float
ambiguities, fixed weights and BRUX clock datum. D0 corrections start at zero
around -1e-7 m/s² and have **no prior**. Other ECOM terms remain zero. The warm
start is the previous station-only solution. Reference fits are never read by
the estimator; precise-product open prevention remains active.

One full update was accepted; weighted cost decreased 1802.308728 ->
1701.367818. The linear prediction differs from the realized reduction by
0.00009796. The next linearization was stationary: combined stopping bound
7.35 micrometres, including a 2.58 micrometre sampled force-plus-state bound.
The accepted checkpoint remains bitwise unchanged at that check. The force
contribution is explicitly included because a six-state-only stopping bound
would miss movement from a D0 update.

Preparation reproduced all baseline states, residuals and sigmas bitwise with
zero cost difference. All 48 full observation force-partial entries passed
independent plus/minus propagation (max 3.73e-5 m per scaled D0 unit, equivalent
to 3.73e-8 m at the finite-difference perturbation). The adjustable trajectory
also passed the preceding 198 state/force partial checks and synthetic recovery.
Final evaluation verifies raw Cartesian versus RAC RMS, native sample counts,
independent objective and sigma/row labels, positive-definite covariance and
stationary checkpoint identity. Root sources, fixture and report hashes pass.
The subsequent independent review and cold-start controls are recorded below.

Estimated D0 values range from -1.2083e-7 to -7.4004e-8 m/s². Their formal
sigmas range from 3.75e-9 to 3.44e-8 m/s²; these are uncalibrated model-based
diagnostics. The coefficient's sign and plausible scale do not establish that
it estimates pure solar pressure rather than partly absorbing measurement error.

### Archive, resources and next work

Campaign: `claude/runs/20260912T145220Z-station-d0`, status
`station_d0_complete_not_accuracy_acceptance`. Final checkpoint:
`linear-1/solution.npz`; accepted update `trial-0-0/solution.npz`;
evaluation `evaluation/evaluation.json`. Source snapshots, input/output hashes,
guard results and original run paths are in `validation.json`. No job is active.

Total guarded experiment time **558.218 seconds (9.30 minutes)**. Peak job memory
**414.38 MiB**; minimum system available **15.454 GiB**. Longest worker 181.218 s.
Matrix workspace **233.102 MiB**, 541 retained parameters, 1628 local clocks,
9566 rows including priors. Linearization/QR and individual trial evaluation
were separate guarded workers; all original limits remain unchanged.
The preceding all-31 reference review took a separate 93.985 s / 138.47 MiB.

Keep this as a candidate station solution and preserve the fixed-D0 baseline.
The assigned Opus review and robustness controls are complete. Next: date handling
and a separately declared day, as detailed in `D0_REPLICATION_PLAN.md`. Do not tune
a D0 prior or select force terms by this day's per-satellite scores.

No root estimator, input data, expert-report source, PDF or report manifest changed.

### Independent review and robustness accepted, 12 September 2026

Opus's `claude/D0_REVIEW.md` records fresh final-state propagation reproducing
9324 residuals, sigmas and 31 x 73 sampled states bitwise, independent Cartesian
scoring, and 60 additional force-partial entries on five other satellites.
The independent scoring reproduces the common/full RMS to about 1e-10 m.

`claude/D0_START_AND_PRIOR_ROBUSTNESS.md` documents the three controls:

| Control versus nominal warm solution | Maximum position difference | Maximum D0 difference |
|---|---:|---:|
| Broadcast-seed cold start | 0.01658 mm | 1.473e-13 m/s² |
| Tenfold weaker orbit priors, warm start | 0 (no update taken) | 0 |
| Tenfold weaker orbit priors, cold start | 0.01849 mm | 1.682e-13 m/s² |

All pass the predeclared 1 mm / 1e-10 m/s² numerical gates. The warm-prior control
alone is limited by immediate stationarity; the paired cold runs supply the more
informative confirmation. They differ directly by **0.002432 mm** maximum and
**3.241e-14 m/s²** in D0. This is stability over the tested starts and prior
strengths, not proof of a unique global solution or accurate physical modelling.

Astra independently audited all four nominal/control archives in
`runs/20260912T155348Z-ae76ad8e/audit.json`, using
`claude/tools/audit_d0_robustness.py`. Source/report/artifact hashes all match;
full-step checkpoint algebra and final/accepted array identity pass. Separately
reconstructed objectives using each run's declared priors have zero recorded
difference. This audit recomputes saved-array quantities, not propagation again.

Opus's coefficient comparison gives station-versus-IGS-fit Pearson 0.848 and
Spearman 0.749. This supports correspondence between the two fitted coefficients
on the same arc. It does not establish pure solar pressure: the fits share force
modelling, state/force coupling remains, and formal sigmas are uncalibrated.
Likewise, the two finite-difference perturbations support derivative consistency
but do not uniquely identify the source of their small remaining discrepancy.

Opus review plus controls: 1402.3 guarded seconds, peak job memory 415.14 MiB,
minimum available 15.590 GiB. Astra's archive audit: 0.531 seconds, 47.47 MiB,
minimum available 16.278 GiB. No limits increased. The 0.4402 m IGS disagreement,
per-satellite regressions, separate-day and rapid-operation gates remain open.

---

<!-- original: D0_DAY215_PROTOCOL.md -->

## Frozen comparison: August 3 fixed versus estimated D0

Declared 12 September 2026 before either day-215 orbit fit or score. This document
is pinned and snapshotted by `claude.tools.run_dated_pod`. Do not edit it after
starting that campaign; record outcomes and deviations in a separate result note.

### Question and inputs

Does the August-2 benefit of estimating one D0 per satellite recur on the next
chronological day? Use 3 August 2026, 12:00–18:00 GPST, six-hour trajectories,
600-second solve cadence and the same fourteen stations: BRUX/HOB2/KOUR/ABMF/
KOUG/DJIG/NNOR/MAS1/DAV1/FALK/FAA1/GLPS/YELL/GUAM. The date and network were
selected before inspecting any day-215 IGS orbit errors.

The thirteen new daily RINEX files are pinned in `claude/data/day215/inputs.json`
(SHA256 eb79361e1e3596822061f51dcca6b45630afb9e9e67ab4284e796df2a8239fd5).
KOUR observations, BRDC navigation and static support are existing pinned inputs.
The preparation fixture records every actual input digest and source digest;
the controller verifies them before a fit. IGS rapid SP3 is evaluator-only and
must match its original `data/stage3/manifest.json` pin. No precise orbit/clock,
reference-fit coefficient or previous-day station fit seeds the estimator.

Header compatibility and native epoch checks are prerequisites. HOB2 lacks the
optional INTERVAL header; actual epochs, not that absent field, determine cadence.
GUAM's observed gaps are retained and disclosed. Do not replace or trim a station
because a later orbit score looks poor. Use the existing nominal-LNAV eligibility
rule; disclose rejected satellites and their reasons, without forcing yesterday's
31-satellite population.

### Paired estimator

Both arms start from this day's corrected broadcast initial states and zero
station-fit corrections. The fixed arm uses D0 = -1e-7 m/s². The estimated arm
adds exactly one scaled D0 correction per eligible satellite (unit 1e-7 m/s²),
initially zero and with **no D0 prior**. All other ECOM terms stay zero. Initial
orbit prior sigmas remain 1000 m / 1 m/s, centred on broadcast seeds. Preserve
the existing 0/3/6-hour wet basis and priors, BRUX clock datum, fixed weights,
float ambiguities, slip handling and minimum-three-observation phase-arc rule.

The isolated date-aware modules preserve the original observation algebra.
Before using them, require August-2 fixture/seed and final forward-model exact
reproduction, derivative regression and explicit-calendar checks. Native date
and calibration/EOP coverage must be checked on day 215 too.

Use the existing reduced square-root QR, four-linearization cap, trial fractions
1/.5/.25/.125, and original cost/stationarity gates. Include the D0 trajectory
contribution in the estimated-arm stopping bound. Each linearization and each
trial is a separate serial guarded worker; preserve every rejected/failed attempt.

### Budget and reporting

Preflight must pass 12000 rows, 900 retained columns, 256 MiB estimated workspace.
Never increase a limit or silently remove observations to fit. Keep 2 GiB Windows
job memory, one thread/core, 10% CPU quota, 8 GiB available reserve, 128 MiB scratch,
and at most 300 seconds per numerical worker. No nested or concurrent guards.
If preflight or convergence fails, stop that experiment and report the cause.

After both arms converge, score identical native IGS epochs and satellites in
two domains: first three hours and full six hours. Report raw 3D and RAC RMS,
orbit-only URE under the existing comparison convention, sample counts and all
per-satellite changes. Report all satellites, the unchanged <=10 m initial formal
position-sigma diagnostic groups, and the determined-in-both paired group with
coverage reasons. Disclose every >0.1 m regression and all estimated coefficients
with uncalibrated formal sigmas. No alignment or residual deletion.

A >=5% first-three-hour pooled improvement is the same candidate-benefit flag
used on August 2. Report the full-domain result even if it disagrees. Replication
does not itself pass the centimetre accuracy target, validate pure SRP, or certify
rapid-latency operation. Native Cartesian recomputation, named-prior objective,
checkpoint/array checks and archive pins are required before accepting the result.
No tuning based on either day's IGS scores during this comparison.

---

<!-- original: D0_DAY215_RESULTS.md -->

## August-3 D0 replication: complete, primary benefit flag failed

12 September local / 13 September 2026 UTC review. Frozen design:
`D0_DAY215_PROTOCOL.md`. Campaign `claude/runs/20260912T193417Z-day215-pod`
completed both fits and evaluation. Independent audit passed. The August-2
improvement in raw 3D agreement **did not replicate**; do not promote unrestricted
per-satellite D0 estimation to the accepted baseline. Original estimator files,
completed campaigns and expert PDF are preserved. No numerical job is active.

| Matched native IGS samples, all 31 satellites | Fixed D0 | Estimated D0 | Change |
|---|---:|---:|---:|
| First three hours, 403 samples, 3D RMS | 0.620817 m | 0.713458 m | **14.92% worse** |
| Full six hours, 775 samples, 3D RMS | 0.622874 m | 0.693766 m | **11.38% worse** |
| First three hours, radial RMS | 0.334274 m | 0.275175 m | improves |
| First three hours, along-track RMS | 0.381924 m | 0.479303 m | worsens |
| First three hours, cross-track RMS | 0.357503 m | 0.451186 m | worsens |
| First three hours, orbit-only URE | 0.336005 m | 0.285597 m | improves |
| Full six hours, orbit-only URE | 0.316730 m | 0.275895 m | improves |

The predeclared >=5% common-domain 3D benefit flag fails. The radial and URE
improvements remain useful evidence, but do not replace the primary metric after
seeing the result. Both fits keep all 31 satellites in the unchanged <=10 m
initial formal-position-sigma diagnostic class. The determined-in-both group
therefore equals the full population; this coarse classification is not accuracy
acceptance. No alignment, score-based satellite removal or station substitution.

### Satellite breakdown and interpretation

Sixteen satellites improve and fifteen worsen in each domain. G27 dominates the
pooled reversal: common RMS **0.151011 -> 2.458037 m**, full RMS
**0.253892 -> 2.234901 m**. In the common domain its squared-error sum increases
by 78.249 m², while all other satellites together decrease by 28.435 m², giving
the net 49.814 m² increase. Full-domain figures are +123.258, -50.919 and +72.339
m² respectively. These are descriptive contributions over the fixed samples;
G27 remains in every acceptance score.

All common-domain regressions exceeding 0.1 m:

| Satellite | Fixed D0 RMS (m) | Estimated D0 RMS (m) | Increase (m) |
|---|---:|---:|---:|
| G02 | 0.225258 | 0.384807 | 0.159548 |
| G07 | 0.249194 | 0.418735 | 0.169541 |
| G15 | 0.142635 | 0.305812 | 0.163176 |
| G16 | 0.808907 | 1.093124 | 0.284217 |
| G17 | 0.215876 | 0.377163 | 0.161287 |
| G25 | 0.466703 | 0.609507 | 0.142803 |
| G27 | 0.151011 | 2.458037 | 2.307027 |
| G28 | 0.888661 | 1.108689 | 0.220028 |
| G29 | 0.809608 | 1.096948 | 0.287340 |

Full-domain >0.1 m regressions are G02/G07/G08/G12/G15/G16/G17/G20/G27/G29.
Examples of common-domain gains: G04 0.97 -> 0.23 m, G14 1.19 -> 0.64 m,
G23 0.98 -> 0.46 m. The archive contains every satellite and coverage reason.

G27's station-estimated D0 changes from -9.4503e-8 m/s² on August 2 to
-1.37894e-7 m/s² on August 3, with day-3 uncalibrated formal sigma 1.53449e-8.
Its initial-state/D0 coordinate correlations reach |0.9248|, while its initial
formal position sigma is 1.182 m. It has at least two viewing sites in 36/37
epochs; at epochs 32–36 only FAA1 and YELL remain, after GUAM disappears.
This identifies coupling and a specific coverage change worth testing. It does
not establish that GUAM's outage caused the error, or that the estimated force
change represents real solar-pressure variation.

The observation objective falls **1931.751770 -> 1823.502251** when D0 is added,
despite poorer 3D IGS agreement. Thus convergence and improved observation fit
are insufficient to support model adoption. The second-day result is evidence
against assuming the first day's 3D gain generalizes, not evidence that D0 should
never be estimated in a better-constrained POD solution.

### Preparation and date validation

The isolated date-aware path reproduces the August-2 fixture and sampled seeds
exactly, and its converged forward model reproduces all 9324 residuals, sigmas,
31 x 73 sampled states and cost bitwise. Ninety-six tested measurement derivative
entries agree exactly; independent calendar arithmetic agrees within 5.4e-12 days.
The dated reference evaluator recovers the original 0.441752106 / 0.440239190 m
RMS and 403 / 775 native samples on August 2.

All thirteen missing station files were acquired from the public BKG archive,
header-screened, decoded with the existing pinned RNXCMP and stored separately
under `claude/data/day215`. Native data checks cover all fourteen stations:
thirteen have 2880 epochs at 30 seconds. GUAM has 2222, with a long gap between
17:14:30 and 22:41:30 GPST and a later three-minute spacing. The long gap removes
the last five GUAM solve epochs. All other station rows remain; no substitutions.
HOB2 omits the optional INTERVAL header, but its actual epochs verify 30 seconds.

Date-215 antenna calibrations and station coordinate solution intervals match
date 214; propagated daily coordinate changes are 0.017–0.203 mm. EOP/ephemeris
coverage is exercised by preparation; navigation and static input hashes pass.
Day-215 navigation was already pinned in `data/stage3/kour_campaign_manifest.json`.

Day-215 preflight: 31 eligible satellites, G13 rejected under the unchanged LNAV
rule; 4692 code rows, 4581 phase rows, 242 prior rows; 523 estimated-arm retained
parameters and 1622 local clocks; estimated workspace 223.865 MiB. This fits the
unchanged 256 MiB workspace and all OS guard limits. Preparation took 138.844 s,
peaked at 187.934 MiB job memory and retained >=14.765 GiB available memory.

### Completed fits, verification and resources

Fixed D0 converged at `fixed-linear-2/solution.npz` after two full accepted steps;
estimated D0 at `d0-linear-3/solution.npz` after three. Final trajectory-step bounds
are **1.847e-6 m** and **1.985e-6 m**; the estimated arm's sampled force-inclusive
bound is 4.399e-7 m. Neither arm used a rejected trial or a raised iteration cap.

`runs/20260913T002114Z-ccc3f76e/audit.json` independently verifies all 177 source,
3 report and 249 artifact pins; declared-prior objectives, residual/sigma labels,
positive-definite covariance, accepted checkpoint algebra and final array identity,
and independently recomputed native Cartesian scores. No fresh propagation was
repeated in this post-campaign audit. The descriptive contribution/coupling check
is `runs/20260913T002301Z-beafc0cd/breakdown.json`.

The inherited empty-median warning arises at GUAM epochs without rows, where an
unused clock seed is NaN. The independent breakdown verifies that **all actual
fitted parameters, states and residuals are finite**. No observation or receiver
clock parameter exists for those absent station/epochs; no warning was suppressed.

Paired fits plus evaluation: **1583.643 guarded seconds (26.39 minutes)** over 13
serial workers, peak job memory **409.32 MiB**, minimum available **14.728 GiB**;
longest worker **171.5 s**. The extra convergence steps explain the overrun of
the rough 15–20 minute planning estimate. Independent audit: 2.688 s / 72.82 MiB;
descriptive breakdown: 0.344 s / 42.23 MiB. Earlier preparation/check timings are
in their individual guard archives. All original limits remain unchanged.

### Next action

Keep both completed days and both model arms. Before adding more force parameters
or tuning D0 priors, run a controlled August-2 experiment removing only GUAM's
last five solve epochs to mimic the August-3 gap, with otherwise identical fixed
and estimated-D0 arms. Compare G27 and the entire population against their own
unmasked August-2 baselines. This can test sensitivity to that missing information;
it cannot by itself assign the August-3 discrepancy to GUAM or to station hardware.
The handoff specifies the bounded control and independent review priorities.
No additional orbit experiment was launched after accepting this replication result.

---

<!-- original: GUAM_GAP_PROTOCOL.md -->

## Frozen August-2 GUAM late-gap control

Declared 13 September 2026 UTC before preparation, fitting or masked scoring.
Question: how sensitive is the August-2 six-hour solution to removing GUAM's
last five solve epochs? This is a single information-loss experiment, not a
unique causal explanation of August 3 and not a station-quality diagnosis.

Copy `claude/runs/20260912T021739Z-arc/six-prepare/fixture.json` unchanged,
then remove only rows with station GUAM and epoch >=32 (epochs 32 through 36,
17:20 through 18:00 GPST). Keep every other row value and order, native arc ID,
sigma, station metadata, navigation/input pin, six-hour span and broadcast seed.
Recompute minimum-three-row phase eligibility without rebuilding native arcs.
Record exact original row indices and row objects removed, arc changes, phase
removals from retained rows, and promotions (including zero counts).

Use the original August-2 ArcPilot and D0Pilot through an isolated wrapper of
the existing split iteration engine. No root estimator or pinned tools edits.
Before any masked fit, require unmasked fixed and D0 forward reproduction of
names, residuals, sigmas, sampled states and cost against their own archives.
Masked preparation must pass 12000 total rows, 900 retained parameters and
256 MiB estimated workspace. Initial sampled states must match the original.

Fit fixed D0=-1e-7 m/s^2 and one unregularized D0 per satellite with scale
1e-7 m/s^2; other ECOM terms zero. Both start with x=0 against original broadcast
seeds. Keep 1000 m / 1 m/s orbit priors, 0/3/6-hour wet basis, .3 m first two
wet-node level sigmas and .03 m adjacent difference sigmas, BRUX clock datum,
weights, float ambiguities and navigation satellite eligibility unchanged.
Use existing reduced QR and nonlinear_stop rules, at most four linearizations
per arm, trial fractions 1/.5/.25/.125; include D0 sensitivity in stopping bound.
Reference products are read only by evaluation/audit workers.

Every worker is serial under customkf.guard with 2 GiB job private commit,
one core/library thread, 10% CPU quota, 8 GiB available reserve, 128 MiB scratch.
No nested guards. Preparation and each reproduction have 180 s caps, linear or
trial workers 300 s, evaluation/audit 120 s each. Plan 20-35 guarded minutes for
fits plus preparation/reproduction/audit. Hard fit envelope: 8 linearizations
and at most 24 trials (four line-search fractions after each of three possible
updates per arm); the fourth linearization must converge. Stop on guard failure,
pin mismatch, budget/rank failure, exhausted line search or nonconvergence;
never increase limits or restart an interrupted campaign in place.

Compare masked fixed against `20260912T021739Z-arc/six-1`, and masked D0 against
`20260912T145220Z-station-d0/linear-1`, under claude/runs. Score raw common
(first three hours) and full six-hour native IGS samples, keeping all satellites,
RAC/3D/orbit-only URE, signed means, <=10 m initial formal-position-sigma groups
and determined-in-both intersections. Publish exact keys and every >0.1 m RMS
regression for both own-baseline comparisons and the masked fixed/D0 comparison.
Report G27 coefficient, formal SI sigma, six state-force cross covariances and
correlations, and exact station tracking for all satellites at epochs 30-36.
The prior >=5% D0 common-domain benefit flag is descriptive; there is no new
accuracy/causality gate. No exclusions, alignment, tuning or extra masks.

Freeze this protocol, adapter/dependency sources, current report pins and
baseline pins before workers start. Historical report hashes resolve only to
matching Revision-2 files per REPORT_PIN_MIGRATION.md. Preserve all old manifests.
Independent post-fit audit reconstructs rows and phase labels, named prior cost,
zero starts, accepted chain, stationary finals, finite arrays, covariance units,
and native Cartesian RMS without the RAC scoring implementation. Stop after the
pair and review; update result note and Opus handoff, with no PDF rebuild.

---

<!-- original: GUAM_GAP_RESULTS.md -->

## August-2 GUAM-gap control: complete and independently reviewed

13 September 2026 UTC. Frozen design: [GUAM_GAP_PROTOCOL.md](GUAM_GAP_PROTOCOL.md).
The requested pair and review are complete. **The late GUAM gap does not reproduce
the August-3 unrestricted-D0 error increase.** Both pooled D0 scores and G27's
scores improve on August 2 despite increased formal uncertainty and coupling.
This is sensitivity evidence for this six-hour configuration, not a reason to
remove GUAM from a production solution or a unique explanation of August 3.

### Raw scores, all 31 eligible satellites

Common = first three hours (403 native satellite-epochs); full = six hours
(775). Exact native keys match across all four fits. No alignment or exclusions.
R/A/C and URE use the frozen inertial-reference comparison contract. Values in m.

| Domain | Arm | 3D RMS | R RMS | A RMS | C RMS | Orbit-only URE |
|---|---|---:|---:|---:|---:|---:|
| Common | Unmasked fixed | 0.543656 | 0.260548 | 0.294260 | 0.375617 | 0.264280 |
| Common | Masked fixed | 0.538511 | 0.248736 | 0.287623 | 0.381310 | 0.253131 |
| Common | Unmasked D0 | 0.441752 | 0.168647 | 0.296603 | 0.280589 | 0.175264 |
| Common | Masked D0 | 0.393667 | 0.171220 | 0.261783 | 0.239012 | 0.175271 |
| Full | Unmasked fixed | 0.547216 | 0.269118 | 0.294665 | 0.374424 | 0.272378 |
| Full | Masked fixed | 0.543522 | 0.262493 | 0.289024 | 0.378126 | 0.266076 |
| Full | Unmasked D0 | 0.440239 | 0.177934 | 0.281463 | 0.287973 | 0.183619 |
| Full | Masked D0 | 0.392419 | 0.169363 | 0.248774 | 0.251834 | 0.173508 |

Masking improves fixed-D0 pooled 3D by 0.946% / 0.675% and estimated-D0 by
10.885% / 10.862% (common/full). The masked D0 arm beats masked fixed by
26.897% / 27.801%, passing the inherited descriptive 5% common-domain flag.
Common-domain D0 radial RMS worsens slightly and URE is essentially unchanged
(+0.00000648 m), so its 3D improvement is not an across-metric improvement.

All satellites remain in the unchanged <=10 m initial formal-position-sigma
diagnostic class. The poorly determined groups are empty, and every paired
determined-in-both group contains all 31. This does not establish actual accuracy
or calibrated uncertainty. G13 retains its frozen LNAV eligibility rejection.
Every satellite's raw scores, signed RAC means, coverage reasons, class and
coefficient/formal sigma are in `evaluation/evaluation.json` below.

| Comparison | Common improved / worsened | Full improved / worsened |
|---|---:|---:|
| Masked fixed vs its unmasked baseline | 16 / 15 | 12 / 19 |
| Masked D0 vs its unmasked baseline | 20 / 11 | 18 / 13 |
| Masked D0 vs masked fixed | 21 / 10 | 21 / 10 |

### Every >0.1 m per-satellite regression

Against each arm's own unmasked baseline:

| Domain | Arm | Satellite | Before (m) | After (m) | Increase (m) |
|---|---|---|---:|---:|---:|
| Common | Fixed | G27 | 0.645581 | 0.803715 | 0.158134 |
| Common | D0 | G03 | 0.237804 | 0.346867 | 0.109063 |

Neither arm has a >0.1 m full-domain regression against its own baseline.
For completeness, adding D0 within the masked pair has these >0.1 m regressions:

| Domain | Satellite | Masked fixed (m) | Masked D0 (m) | Increase (m) |
|---|---|---:|---:|---:|
| Common | G01 | 0.444508 | 0.640387 | 0.195879 |
| Common | G07 | 0.424881 | 0.573819 | 0.148938 |
| Common | G08 | 0.345648 | 0.544231 | 0.198583 |
| Common | G12 | 0.221346 | 0.331369 | 0.110024 |
| Common | G22 | 0.155597 | 0.487294 | 0.331698 |
| Full | G07 | 0.393607 | 0.524223 | 0.130616 |
| Full | G08 | 0.290451 | 0.639680 | 0.349229 |
| Full | G12 | 0.226970 | 0.403554 | 0.176584 |
| Full | G22 | 0.187434 | 0.439347 | 0.251913 |

### G27: more uncertain, but smaller D0-fit error

| Quantity | Unmasked | Masked |
|---|---:|---:|
| Fixed common / full 3D RMS (m) | 0.645581 / 0.554071 | 0.803715 / 0.636563 |
| D0 common / full 3D RMS (m) | 1.099264 / 0.995553 | 0.584918 / 0.494887 |
| Estimated D0 (m/s²) | -9.4503447941e-8 | -1.0447666322e-7 |
| D0 uncalibrated formal sigma (m/s²) | 1.3166442620e-8 | 1.9811089141e-8 |
| Initial position root-trace formal sigma (m) | 1.093436 | 1.413770 |
| Largest absolute initial-state/D0 coordinate correlation | 0.909408 | 0.950211 |

State order is inertial x/y/z/vx/vy/vz. Masked state-D0 cross covariances are
`[-2.2511349965e-8, 1.0259964411e-8, 4.3205496893e-9,
-1.3806956041e-12, -2.6910869038e-12, 2.7638359217e-13]`.
Units are m²/s² for position-D0 and m²/s³ for velocity-D0. Correlations are
`[-0.950211, 0.754022, 0.700363, -0.733624, -0.850387, 0.307961]`.
Both complete covariance vectors and coefficient units were independently checked.
These are initial-state diagnostics; no full-arc covariance propagation is claimed.

| Solve epoch | Original G27 stations | Masked G27 stations |
|---|---|---|
| 30 | GUAM, YELL | GUAM, YELL |
| 31 | FAA1, GUAM, YELL | FAA1, GUAM, YELL |
| 32–36 (each epoch) | FAA1, GUAM, YELL | FAA1, YELL |

The machine-readable evaluation lists each station at each epoch 30–36 for
every satellite. The loss increases G27's formal sigma and state-force coupling,
as expected for weaker information, but does not yield the August-3 D0 error
(2.458037 m common / 2.234901 m full). Day-specific observations/model mismatch
and their interaction with geometry remain unresolved. Improved masked scores
do not identify a bad receiver or justify outcome-based station deletion.

### Fixture, convergence and audit

Only 40 GUAM row objects at epochs 32–36 were removed: 40 code observations and
38 eligible phase observations. GUAM:G30:83 had only two native rows and was
already phase-ineligible. No phase arc was promoted or demoted; no retained
phase row was disabled. All retained values/order, native arc IDs, metadata,
sigmas, seeds, navigation/input pins and priors are unchanged.

Preflight: 4691 code + 4555 phase + 242 prior rows; 541 retained parameters in
the D0 arm, 1622 local clock parameters, 231.418 MiB predicted workspace.
The fixed solve used 217.556 MiB predicted workspace. Both are below 256 MiB.
Unmasked fixed and D0 forward checks reproduced names, residuals, sigmas,
31 x 73 sampled states and objective bitwise; masked initial states also match.

Both arms start at x=0 and accept one full step, then converge on linearization
1. Final trajectory-step bounds: fixed 5.057572e-5 m, D0 4.914498e-5 m (sampled
force-inclusive bound 1.556377e-5 m). No rejected trial or extra iteration.
Fixed objective = 1717.245726 observation + 22.765133 prior = 1740.010860;
D0 objective = 1619.464851 observation + 22.597030 prior = 1642.061881.

The final independent review verifies 185 source, 3 current report and 234
campaign artifact pins, plus all three historical campaigns with exact Revision-2
report mappings. It verifies exact row selection, phase labels, clock semantics,
named prior objectives, cold starts, accepted checkpoint algebra, finite fitted
arrays, positive-definite covariance, native Cartesian RMS, independently coded
RAC/URE and signed means, diagnostic classes and every regression list.
Reference velocity interpolation is shared; the audit does not freshly propagate
the final orbits. The original unmasked forward checks did perform propagation.

The first audit's exact-row checks passed but its JSON `removed_rows` summary
incorrectly said 7 because a seven-element covariance index list reused that
variable. Its source and output are preserved. The final review executes a
snapshotted two-replacement correction, repeats all checks and reports 40. This
was an audit-summary defect, with no estimator, fixture, fit or score changes.
The expected empty-median warnings concern unused absent-epoch GUAM clock seeds;
all actual fitted parameters, states and residuals are finite.

### Archives and resources

- Campaign: `claude/runs/20260913T161703Z-guam-gap/validation.json`.
- Finals: `fixed-linear-1/solution.npz`, `d0-linear-1/solution.npz` in that campaign.
- Exact mask: `prepare/mask.json`; scores/keys: `evaluation/evaluation.json`.
- Final independent review: `claude/runs/20260913T163720Z-guam-gap-review/audit.json`.
- Superseded summary audit: `runs/20260913T163537Z-1549cd58/audit.json`.
- Result completion/evidence binding: `GUAM_GAP_RESULTS.manifest.json`.

The controller's immutable final status is `guam_gap_pair_complete_pending_audit`;
the separate final review and result manifest resolve that pending review. Do
not relabel the frozen campaign or rerun its no-resume controller.

Preparation, two reproductions, paired fits and evaluation: **1096.876 guarded s
(18.28 min)** across 10 workers; longest 161.890 s, peak job private memory
411.844 MiB, minimum available memory 13.817 GiB. Both audit runs add 18.845 s;
total **1115.721 s (18.60 min)**. All original resource limits were respected:
2 GiB job commit, one core/thread, 10% quota, 8 GiB reserve, 128 MiB scratch,
<=300 s ordinary workers. No software or data download. The root estimator,
pinned tools, completed numerical archives and Revision-3 PDF/source/manifest
remain unchanged. No numerical job remains active at completion.

### Opus follow-up and next recommendation

Read [claude/roadmap/ASTRA_HANDOFF.md](claude/roadmap/ASTRA_HANDOFF.md) alongside
this result. Its block-calibrated nominal, streaming parity and 12-hour D0
results are promising separate experiments. This task read their protocols,
notes and relevant code; it did not independently recompute those campaigns.
The GUAM-gap pair deliberately preserves the older unit-nominal six-hour
configuration to answer its original controlled question.

The next useful bounded task is an independent archive/numerical review of
Opus's block calibration and streaming/12-hour evidence, followed by a declared
August-3 12-hour D0 replication if those checks pass. Treat the existing two
evaluation dates as reused development data; a prior-day calibration timestamp
alone does not certify product availability at a rapid cutoff. Do not infer that
all remaining error is proven to be SRP or estimation noise.

Stop here as assigned. No additional masks, prior tuning, ECOM terms, station
substitutions, downloads, 24-hour restarts or PDF rebuilds were launched.

---

<!-- original: D0_REPLICATION_PLAN.md -->

## Next D0 experiment: separate-day replication preparation

**Completed, 12 September local / 13 September UTC:** date handling, acquisitions,
preflight, paired fits and independent audit are finished. The primary 3D benefit
did not replicate; see `D0_DAY215_RESULTS.md`. The preparation plan below is retained
as history. No job is active; the current next step is the controlled GUAM-gap test.

Decision recorded 12 September 2026 after the start/prior controls passed.
This is an implementation and input plan, not a completed experiment or frozen
execution manifest. Preserve all previous campaigns and their pinned sources.

### Recommended comparison

Use **3 August 2026, 12:00–18:00 GPST**, the next chronological day, with the
same fourteen-station network, ten-minute solve cadence and six-hour dynamics.
Choose this date before inspecting its orbit scores. Compare fixed nominal D0
against one estimated D0 per satellite, retaining the current weights, priors,
wet basis, ambiguity rules, navigation eligibility and clock datum. Start from
that day's broadcast seeds and nominal coefficients; do not carry fitted states,
ambiguities or D0 from August 2. Do not tune force priors or select satellites
using IGS discrepancies.

Report paired raw Cartesian/RAC RMS on identical native IGS epochs, sample counts,
every satellite, determined/poorly-determined groups, coverage reasons and every
regression above 0.1 m. The eligible satellite set can differ from August 2;
do not force 31 or drop a weak satellite to recreate the earlier population.
Reference data enter the evaluator only. A pooled improvement on day two is
replication evidence, not achievement of the centimetre or operational target.

### Local input inventory

Filename inventory on 12 September (existence only, not header/coverage approval):

| August 3 input | Cached under data/stage3 | Remaining work |
|---|---|---|
| BRDC navigation, day 215 | Yes | Hash and eligibility/coverage preflight |
| IGS rapid orbit and clock, day 215 | Yes | Evaluator-only hash/epoch checks |
| KOUR station observations, day 215 | Yes | Header and observation preflight |
| Other thirteen station observations, day 215 | No in data/ or claude/data/ inventory | Acquire and header-screen before fitting |

Missing station files: BRUX, HOB2, ABMF, KOUG, DJIG, NNOR, MAS1, DAV1, FALK,
FAA1, GLPS, YELL, GUAM. Existing calibration, coordinate, loading, ephemeris and
EOP files require date-validity checks; presence is not proof of suitability.
No files were downloaded during this review, and no new software is needed for
the preparation. A different six-hour interval on August 2 would save downloads
but would provide weaker independence, so it is not the preferred replication.

### Implementation gates before fitting

1. Parameterize the observation date and arc epoch explicitly. Known dependencies
   include `customkf/stage5_pilot.py` ORIGIN, day-214 filenames, coordinate epoch,
   calibration epoch and end-of-day navigation cutoff. In
   `customkf/dynamic_observation.py`, the troposphere day fraction is hardcoded
   as `214+(43190+receive_s)/86400`. Audit helper imports and evaluation epochs
   too; changing only ORIGIN is insufficient.
2. Retain an explicit legacy/default configuration and reproduce August 2
   fixtures, forward observables and sampled trajectories before using day 215.
   Archive changes separately; never repair old manifests to match new sources.
3. Header-screen all candidate files, then preflight day-215 rows, ambiguity arcs,
   common eligible satellites, navigation, calibration and simultaneous coverage.
   Stop for missing/unsupported inputs instead of silently changing the network.
4. Freeze the day-215 input hashes, eligibility, settings and paired comparison
   contract before either orbit fit or reference scoring.
5. Run serial fixed-D0 and estimated-D0 fits, separate evaluator, and an independent
   result audit. If the gain reverses, preserve that result and investigate before
   further force-model expansion.

### Resource and latency boundaries

Keep existing Windows Python and customkf.guard. No concurrent numerical jobs,
no nested guards, 2 GiB job cap, one thread/core, 10% CPU quota, 8 GiB available
reserve, 128 MiB scratch; each worker at most 300 seconds. Keep QR ceilings at
12000 rows, 900 retained columns and 256 MiB workspace. Current D0 workspace is
233.102 MiB, so day-dependent ambiguity growth may exceed the limit: preflight
must stop rather than raise limits or silently trim observations.

The measured August-2 D0 campaign took 9.3 guarded minutes and about 414 MiB peak
job memory; use that as a planning reference, not a guarantee for day two.
Date refactoring and input screening come before that runtime. Archived daily
files test retrospective reproduction. Record product vintages and issue-time
eligibility separately; this replication alone cannot establish rapid-latency
operational readiness.

---

<!-- original: claude/roadmap/STREAMING_AND_ARCS_PROTOCOL.md -->

## Frozen protocol: streaming solve (step 2) and 12 h / 24 h arcs (step 3)

Declared by Claude (Opus) on 13 September 2026 UTC. The step 2 gates and all step 3 choices below
were written before any streaming, long-arc fit or long-arc score ran. Step 1 (block D0) was still
running when this was written; its outcome does not alter anything here. All code is under
`claude/roadmap/`, and the root estimator and Astra's tools are unchanged.

### Step 2: gates for the streaming implementation (all must pass before step 3)

- **G2a, exact caching** (`stream_checks profile`, first 3 epochs of the August-3 fixture): Astra's
  dated `D0Pilot` with and without `CachedEpoch` gives bitwise-identical Jacobian blocks,
  residuals and sigmas. Speed-up and top profile entries are reported.
- **G2b, pilot parity** (`long_checks --arm fixed` and `--arm d0`, August-3 six-hour fixture,
  archived final x):
  - `LongPilot` forward residuals, sigmas, sampled states and cost equal the archive bitwise;
  - every Jacobian block and the constraint system equal the dated pilot's bitwise.
- **G2c, solve parity** (`stream_checks parity`, x = cold and x = first accepted iterate, the D0
  arm): versus `reduced_qr`, the maximum absolute difference in the estimate must be ≤ 1e-6 of the
  largest estimate magnitude, relative differences in the retained covariance diagonal ≤ 1e-6, and
  the checkpoint-split solve must be bitwise equal to the unsplit streaming solve.
- **G2d, end-to-end** (`run_long`, August-3 six-hour fixture, `configs/unit-d0.json`, cold start,
  12-epoch chunks):
  - convergence under the unchanged stationarity rule;
  - final sampled states within **1 mm** of the archived `d0-linear-3` states at every sample
    (the rule's own 1 mm scale);
  - final objective within 1e-6 relative of the archive.
- Resources, runtime per link and the largest worker are recorded. A failed gate stops step 3
  and is reported.

### Step 3: longer arcs on August 2 (day 214, the same 14 stations, 10-minute cadence)

- **Fixtures** (`long_prepare`): no new observations, only longer spans from the same daily files.
  - **12 h:** 12:00–23:50 GPST, 72 epochs.
  - **24 h:** 00:00–23:50, 144 epochs, origin 23:59:50 on 1 August.
  - **Six-hour sanity check:** `--check-six` must reproduce the dated August-2 six-hour fixture
    exactly.
  - Satellites failing the unchanged navigation-coverage rule over the longer span are reported,
    not replaced.
- **Arms:** all start at x = 0 from broadcast seeds, with 1000 m / 1 m/s orbit priors, the wet basis
  with nodes every 3 h (level priors on the first two nodes, .03 m increments), float ambiguities,
  and the unchanged 10° cutoff, sigmas and stationarity rule. At most 4 linearizations; at most 6
  on the 24 h arc because of its larger initial nonlinearity (declared here, not after the fact).
  - **FB, fixed block nominal:** `configs/block-fixed.json`, from the frozen August-1 calibration of
    step 1.
  - **FU, fixed unit nominal (-1e-7):** 12 h only, to separate block and arc effects.
  - **D0, unrestricted:** one D0 per satellite from the unit nominal (as Astra's arm).
  - **E5, unrestricted ECOM5:** D0, Y0, B0, Bc1, Bs1 per satellite from the unit nominal.
- **Order:** 12 h FB, 12 h D0, 12 h FU, 12 h E5, then 24 h FB, 24 h D0, 24 h E5. Stop early if
  a gate fails or a fit fails its cap; the reason is reported.

### Step 3 scoring (`long_evaluate`, evaluation-only)

- **Domains (August 2):**
  - **S6:** 12:00–18:00, the six-hour baseline window with 775 samples if all satellites are
    present;
  - **S12:** 12:00–23:45;
  - **S24:** 00:00–23:45.
  Each is scored on native keys common to all arms being compared.
- **Comparisons:**
  1. **S6:** the step 1 B arm (6 h FB) as baseline, against 12 h FB and 24 h FB. Also A0 (6 h unit) against 12 h FU.
  2. **S12:** 12 h FB baseline, against 12 h D0, 12 h E5 and 12 h FU; 24 h FB where it covers the window.
  3. **S24:** 24 h FB baseline, against 24 h D0 and 24 h E5.
- **Reported:** 3D/RAC/URE, per block and per satellite, median ratio, >0.1 m regressions,
  D0/ECOM formal sigmas and state-force correlations.
- **Predeclared descriptive flags** (≥5% pooled 3D benefit):
  - (a) 12 h FB beats 6 h FB on S6;
  - (b) D0 beats FB on the arc's own full domain, separately for 12 h and 24 h;
  - (c) E5 beats FB likewise.
  These are one-day diagnostics, not adoption. Adoption needs step 4's multi-day bench.

### Resources

- Unchanged guard limits on every worker: 300 s, 2 GiB job commit, one core/thread, 10% CPU,
  8 GiB reserve, 128 MiB scratch.
- **Chunk size** is chosen from the measured G2d per-link time, so a chunk's projected time is
  ≤ 200 s.
  - *Operational amendment, before any long-arc worker:* G2a's profile showed trajectory
    re-integration dominating (63 s of 74 s for three epochs), not rotations. Chunk sizing therefore
    budgets integration and start-up, scaled by arc length, within a 240 s projected total per
    worker (60 s under the cap).
  - Arcs whose fixed cost alone cannot fit are stopped for replanning, for example 24 h without a
    trajectory cache. No scientific choice changes.
- *Second operational amendment, after step 2 passed and before any step 3 worker:* all step 3 arms
  use the exact trajectory cache (`traj_cache.py`).
  - Each linearization or trial point is integrated once by guarded integrate workers: one group
    for 12 h, two for 24 h. Chunk, solve and trial workers load that point.
  - `traj_cache_check.py` is a gate before any long fit. It requires every state, state-transition
    partial and force partial on the output grid, plus two epochs' Jacobian blocks, to be bitwise
    identical to a fresh integration, and a mismatched point must be refused.
  - This changes runtime only, not the objective or any estimate.
- **Accumulator workspace** stays under the existing 256 MiB solve-preflight value: the chunk
  step records an estimate and stops if it is exceeded.
- Stop on any guard failure; never raise limits or resume a campaign in place.

---

<!-- original: claude/roadmap/STREAMING_RESULTS.md -->

## Result: streaming square-root solve (roadmap step 2) — all gates pass

Claude (Opus), 13 September 2026 UTC. Protocol: [STREAMING_AND_ARCS_PROTOCOL.md](STREAMING_AND_ARCS_PROTOCOL.md).
Stage archive: `claude/runs/20260913T023932Z-roadmap-step2` (`stage.json`). End-to-end fit:
`claude/runs/20260913T030114Z-long-g2d-aug3-d0`. No root estimator or Astra file changed.

### What was built

- **`streaming.Accumulator`:** per-epoch clock elimination (the same pivoted local QR), then
  Householder folding of the projected rows into `R, z`.
  - The final pivoted solve uses `reduced_qr`'s pre-projection column scale and rank rule.
  - The state checkpoints between guarded workers.
  - Memory is O(n² + block·n), independent of arc length.
- **`long_pilot.LongPilot`:** Astra's dated `Pilot → ArcPilot → D0Pilot` objective reproduced term by
  term, with an epoch-at-a-time Jacobian.
  - Generalized to any 10-minute arc (wet nodes every 3 h).
  - Supports per-satellite nominal D0, and unrestricted or prior-constrained D0/ECOM5.
- **`long_iteration` + `run_long`:** state / chunk / solve / trial guarded workers. The
  stationarity rule and line search are unchanged. Every checkpoint is hash-bound to the fixture,
  config, state and linearization point.

### Gates

| Gate | Test | Result |
|---|---|---|
| **G2a** exact caching | dated D0Pilot, 3 epochs, with and without `CachedEpoch` | **bitwise equal**; but speed-up only 1.04× (see profile) |
| **G2b** pilot parity | `LongPilot` at archived Aug-3 finals, fixed and D0 arms | forward residuals, sigmas, 31×73 states and cost **bitwise equal to the archives**; every Jacobian block and the constraint system **bitwise equal to the dated pilots** |
| **G2c** solve parity | streaming vs `reduced_qr` on the full 6 h D0 linearization, cold and near-converged x | max \|Δestimate\| 4.6e-13 (7e-14 relative), covariance diagonal 5.6e-14 relative, predicted reduction identical; checkpoint-split solve **bitwise equal** to unsplit |
| **G2d** end to end | `run_long`, Aug-3 6 h D0 arm, cold start, 12-epoch chunks | converged in 3 linearizations (the archive also took 3); final states within **5.8e-7 m** of the archive at every sample; objective 1823.50225151 vs 1823.50225123 (1.6e-10 relative) |

**Streaming solve time:** 0.6 s for the six-hour system (523 retained, 1622 local clocks, 9515
rows). The workspace estimate is 22–25 MiB, against the dense solver's 224 MiB.

### Profile: where the time actually goes

My review guessed that per-link ERFA nutation calls dominated. **That was wrong.**

- The 3-epoch cProfile attributes 63 s of 74 s to re-integrating the 31 trajectories with
  variational and force-sensitivity equations (about 172,000 force-model evaluations at about
  0.3 ms of Python each). `xys06a` totals only 0.8 s.
- Without the profiler, G2d measured:
  - **integration about 45–50 s** per six-hour linearization point;
  - **link Jacobians about 2.0–2.2 s per epoch** (about 17 ms per link for the D0 arm).
- **Implication:** integration cost scales with arc length and is repeated in every chunk worker. For
  24 h it alone is about 200 s, so an exact trajectory cache (`traj_cache.py`) is needed before 24 h
  arcs can fit the unchanged 300 s cap. Twelve-hour arcs fit without one.

### Resources

- **Step 2 total:** stage workers plus the G2d fit.
- **G2d fit:** 1117.8 guarded s (18.6 min) over 3 linearizations. Longest worker 79.9 s; peak job
  memory 382 MiB.
- **Parity workers:** 166–179 s each, all within the unchanged 300 s cap.
- No limit was changed.

---

<!-- original: claude/roadmap/STEP3_RESULTS.md -->

## Result: longer arcs on 2 August (roadmap step 3) — all 7 arms converged

Claude (Opus), 13 September 2026 UTC. Supersedes [STEP3_RESULTS_INTERIM.md](STEP3_RESULTS_INTERIM.md)
for the 24 h arms. Protocol: [STREAMING_AND_ARCS_PROTOCOL.md](STREAMING_AND_ARCS_PROTOCOL.md).
Operational log: [STEP3_RUN_LOG.md](STEP3_RUN_LOG.md). Final evaluation stage:
`claude/runs/20260913T181310Z-roadmap-step3-eval`.

All results are raw and unaligned, on one day (2 August). The 24 h fixture has **27 satellites**:
G02, G05, G13, G18 and G29 fail the frozen LNAV coverage rule at the 00:00 start.

### Convergence

| Arm | Campaign | Linearizations | Guarded s |
|---|---|---:|---:|
| 12h-FB | `claude/runs/20260913T033218Z-long-12h-FB` | 3 | 1054 |
| 12h-FU | `…T040754Z-long-12h-FU` | 2 | 709 |
| 12h-D0 | `…T034955Z-long-12h-D0` | 3 | 1075 |
| 12h-E5 | `…T041946Z-long-12h-E5` | 3 | 1668 |
| 24h-FB | `…T050802Z-long-24h-FB` | 2 | 1270 |
| 24h-D0 | `…T171214Z-long-24h-D0` | 3 | 1503 |
| 24h-E5 | `…T173721Z-long-24h-E5` | 3 | 2145 |

The failed or interrupted earlier attempts are preserved and documented in the run log.

### Full-day arcs (S24 = 00:00–23:45, 2592 samples, 27 satellites)

| Arm | 3D (m) | R / A / C (m) | URE (m) | IIF / IIIA / IIR / IIR-M |
|---|---:|---|---:|---|
| 24h-FB fixed block nominal | 0.9087 | 0.313 / 0.805 / 0.284 | 0.3299 | 0.577 / 1.389 / 0.657 / 0.619 |
| 24h-D0 | 0.3399 | 0.109 / 0.306 / 0.099 | 0.1167 | 0.181 / 0.465 / 0.229 / 0.417 |
| **24h-E5 (ECOM5)** | **0.1714** | **0.058 / 0.130 / 0.096** | **0.0609** | 0.155 / 0.187 / 0.191 / 0.167 |

- **24h-E5 against 24h-FB:** −81.1% pooled, median per-satellite ratio 0.273. All **27 of 27**
  satellites improve, with no regressions over 0.1 m.
- **24h-D0 against 24h-FB:** −62.6%; 26 improve.

### Common window, all arc lengths (12:00–18:00 on the 27 common satellites, 675 samples)

| Arm | 3D (m) | URE (m) |
|---|---:|---:|
| A0, 6 h nominal (the original baseline) | 0.5707 | 0.2782 |
| FB6, 6 h block fixed (step 1) | 0.3455 | 0.1367 |
| 12h-FB | 0.3903 | 0.1321 |
| 12h-FU | 1.6685 | 0.8483 |
| 12h-D0 | 0.2257 | 0.0759 |
| 12h-E5 | 0.3963 | 0.1487 |
| 24h-FB | 0.7529 | 0.1926 |
| 24h-D0 | 0.2556 | 0.0964 |
| **24h-E5** | **0.1532** | **0.0511** |

On all 31 satellites (12 h arms only, 12:00–23:45): 12h-D0 0.2207 m, 12h-FB 0.3901, 12h-E5 0.3690,
12h-FU 1.7114. See the interim note.

### Predeclared descriptive flags (one day)

| Flag | Result |
|---|---|
| (a) 12h-FB ≥5% better than 6 h FB on S6 | fails (+14.4%) |
| (b) D0 ≥5% better than FB, 12 h | passes (−43.4% on S12) |
| (b) D0 ≥5% better than FB, 24 h | passes (−62.6% on S24) |
| (c) ECOM5 ≥5% better than FB, 12 h | passes on pooled RMS (−5.4%), but more satellites worsen (18 vs 13) |
| (c) ECOM5 ≥5% better than FB, 24 h | **passes strongly (−81.1%, 27/27 improve)** |

### Reading

1. **24 h with ECOM5 is the best configuration so far.**
   - **Full day:** 17.1 cm 3D and 6.1 cm URE.
   - **Common afternoon window:** 15.3 cm and 5.1 cm.
   - **Against the 10.13 cm / 3.62 cm benchmark:** about 1.5–1.7×, down from about 5× at the start
     of the day.
   - **Consistent with practice:** IGS analysis centres estimate ECOM-type parameters on day-long
     arcs, where the once-per-revolution terms separate from the initial state.
2. **The best force model depends on arc length.**
   - With about 6 h, a well-calibrated fixed nominal wins.
   - With about 12 h, one D0 per satellite wins, and ECOM5 is over-flexible.
   - With 24 h, ECOM5 wins clearly.
   - Fixed forces degrade quickly with arc length (24h-FB is 0.91 m).
3. **Caveats:**
   - This is one day and 27 satellites.
   - Four satellites were lost at the 00:00 start. Adding the previous day's broadcast file is a
     declared input change still to make.
   - The step 4 bench tests repeatability across days. By its frozen rule it will select L\* among
     these arms on 2 August.

---

<!-- original: claude/roadmap/BENCH_PROTOCOL.md -->

## Frozen protocol: multi-day bench (roadmap step 4)

Declared by Claude (Opus) on 13 September 2026 UTC. Written while the step 3 long-arc fits were
running and **before any step 3 score existed**. No bench download, fit or score has run. The code
is under `claude/roadmap/`, and data goes to `claude/data/day<DOY>/` (see `README.md`).

### Question

Do the model improvements found on one or two days hold across a small set of consecutive days?
Specifically, do the block-calibrated nominal D0 and the best long-arc configuration beat the
original fixed nominal, consistently rather than on a pooled average driven by one day or satellite?

### Days and inputs

- **Evaluation days:** 2026-08-02, 03, 04, 05, 06 (DOY 214–218).
- **Calibration:** stays the frozen **1 August** block means from step 1. It is not re-fitted per day,
  which is conservative: the calibration ages by 1–5 days.
- **Network:** the frozen 14 stations and 10-minute cadence.
- **Downloads** (`run_fetch`, BKG public mirror, pinned RNXCMP): station RINEX and broadcast/IGS
  rapid SP3 for days not already on disk. Days 216–218 need everything; 214 and 215 exist.
- **Missing data:** a station missing on a day is recorded and that day runs without it. There are
  no substitutions. Satellites failing the frozen navigation-coverage rule are recorded, not
  replaced.
- **Eclipse inventory:** `bench_beta` records beta angles and shadow entries per day. It is
  descriptive only.

### Arms (all from broadcast seeds and x = 0, unchanged priors, rules and caps)

- **A0:** 6 h (12:00–18:00), fixed unit nominal D0 (-1e-7). For Aug 2 and Aug 3 the existing
  archives are used.
- **FB6:** 6 h, fixed block nominal. Aug 2 and Aug 3 use the step 1 B archives.
- **L\*:** the best step 3 long-arc arm, chosen by the rule below and run on every bench day.
  - **Selection rule** (declared now): among step 3 arms that converged, take the one with the lowest
    pooled 3D RMS on August 2, window 12:00–23:45, using the native keys common to all converged
    12 h and 24 h arms.
  - If only 12 h arms converged, choose among them on their common keys.
  - August 2 is then in-sample for L\*, which is disclosed; August 3–6 are out-of-sample.

### Scoring (`bench_evaluate`, raw IGS rapid, all satellites, no alignment)

- **Common window (all arms):** 12:00–18:00 GPST, on keys common to all arms on that day.
- **Arc windows:** L\* is also scored on its own full window, against FB6 where they overlap.
- **Per day:** pooled 3D, RAC and URE; per block; paired per-satellite median ratio against A0;
  satellites improving and worsening; >0.1 m regressions.
- **Bench level:**
  - mean over days of the pooled 3D RMS;
  - days with ≥5% improvement against A0 (and L\* against FB6);
  - a one-sided sign test over all satellite-days of log(RMS_arm / RMS_A0).

### Predeclared reading

- **FB6 consistent:** at least 4 of 5 days ≥5% better than A0 on the common window, *and* the
  sign-test p < 0.05.
- **L\* adds value:** L\* ≥5% better than FB6 on at least 4 of 5 days on the common window.
  - Otherwise L\* is recorded as not demonstrated.
- **Limits:** these flags describe consistency across five consecutive summer days with one
  network. They are not seasonal, eclipse-general or operational validation.
- **No exclusions or tuning:** no day or satellite exclusion, and no calibration or weighting tuning
  based on bench scores.

### Resources

- Unchanged guard limits; one job at a time.
- The trajectory cache and streaming solve are used as validated in steps 2–3.
- **Rough budget:** 6 h arms about 15 min per day per arm; 24 h arms up to about 1 h per day. Stop on
  any failure; never raise limits.

---

<!-- original: claude/roadmap/BENCH_RESULTS.md -->

## Result: multi-day bench, 2–6 August 2026 (roadmap step 4) — both predeclared flags pass

Claude (Opus), 13 September 2026 UTC. Frozen protocol: [BENCH_PROTOCOL.md](BENCH_PROTOCOL.md).
Operational log: [BENCH_RUN_LOG.md](BENCH_RUN_LOG.md). Stage:
`claude/runs/20260913T190407Z-roadmap-bench` (the failed first attempt,
`…T182500Z-roadmap-bench`, is preserved). Summary: `summary/bench_summary.json`.

All results are raw IGS rapid comparisons with no alignment, all satellites present in each arm,
and no score-based exclusion. The calibration is the frozen **1 August** block D0 for every day.

### Arms

- **A0:** 6 h (12:00–18:00), the original fixed nominal D0 (−1e-7).
- **FB6:** 6 h, fixed block-calibrated D0 (step 1).
- **L\*:** chosen by the frozen rule on 2 August: **24h-E5**, a 24 h arc (00:00–23:50) with
  unrestricted ECOM5 per satellite (selection-window RMS 0.193 m, lowest of seven).
  - 2 August is in-sample for L\*; 3–6 August are out-of-sample.
  - The 3 August L\* campaign was reused from the first stage (same label, config and day, converged).

### Common window, 12:00–18:00 (keys common to all three arms)

| Day | Samples | A0 3D | FB6 3D | **L\* 3D** | A0 URE | FB6 URE | **L\* URE** | Stations |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Aug 2 | 675 | 0.571 | 0.346 | **0.153** | 0.278 | 0.137 | **0.051** | 14 |
| Aug 3 | 700 | 0.635 | 0.452 | **0.152** | 0.330 | 0.232 | **0.048** | 14 (GUAM gap) |
| Aug 4 | 725 | 0.772 | 0.585 | **0.162** | 0.377 | 0.263 | **0.052** | 13 (no YELL) |
| Aug 5 | 775 | 1.470 | 1.076 | **0.183** | 0.859 | 0.618 | **0.053** | 13 (no YELL) |
| Aug 6 | 650 | 0.624 | 0.388 | **0.132** | 0.283 | 0.147 | **0.040** | 14 |
| **Mean of days** | | **0.815** | **0.569** | **0.156** | | | | |

Sample counts differ because the 24 h fixture drops satellites failing the frozen LNAV coverage rule
at 00:00. The common window uses only keys present in all three arms.

### L\* over its own full-day window (00:00–23:45)

| Day | Samples | 3D (m) | R / A / C (m) | URE (m) |
|---|---:|---:|---|---:|
| Aug 2 | 2592 | 0.171 | 0.058 / 0.130 / 0.096 | 0.061 |
| Aug 3 | 2688 | 0.156 | 0.050 / 0.112 / 0.097 | 0.054 |
| Aug 4 | 2784 | 0.212 | 0.070 / 0.165 / 0.114 | 0.074 |
| Aug 5 | 2976 | 0.214 | 0.064 / 0.149 / 0.139 | 0.069 |
| Aug 6 | 2496 | 0.154 | 0.050 / 0.110 / 0.095 | 0.053 |

### Predeclared flags

| Comparison (common window) | Days ≥5% better | Satellite-days improved / worsened | One-sided sign test | Median per-satellite ratio | Per-day pooled change |
|---|---:|---:|---:|---:|---|
| **FB6 vs A0** | **5 / 5** | 122 / 19 | p = 6.7e-20 | 0.687 | −39.5, −28.9, −24.3, −26.8, −37.8% |
| **L\* vs FB6** | **5 / 5** | 127 / 14 | p = 2.9e-24 | 0.394 | −55.7, −66.4, −72.3, −83.0, −66.0% |
| L\* vs A0 (descriptive) | 5 / 5 | 135 / 6 | p = 3.7e-33 | 0.247 | −73.2, −76.1, −79.0, −87.6, −78.9% |

- **`FB6_consistent: true`**: at least 4 of 5 days ≥5% better and p < 0.05. The block-calibrated
  nominal D0 generalizes across five days, with its calibration aged 1–5 days.
- **`Lstar_adds_value: true`**: the 24 h ECOM5 arc beats the 6 h block-fixed arm by 56–83% every
  day.

### Observations

- **L\* is stable day to day:** 13–18 cm 3D on the common window and 15–21 cm over the full day,
  while the 6 h arms swing by more than 2× across days (FB6 0.35–1.08 m). The short-arc fits are
  very sensitive to network coverage.
  - Losing YELL on 4–5 August roughly doubled the 6 h errors.
  - It raised L\*'s full-day error only from about 0.16 to 0.21 m.
- **Eclipse-season satellites** (|β| < 13.9°, entering shadow) were present on every bench day:
  G01, G02, G06, G11 and G18, plus G24 entering shadow on 6 August. The bench therefore includes
  eclipsing satellites every day, although G02 and G18 are among those the 24 h fixture drops at
  00:00.
- **Distance to the historical benchmark** (10.13 cm 3D, 3.62 cm URE): L\* averages about 1.5× in
  3D on the common window and 1.1–1.5× in URE.

### Limits

- Five consecutive summer days, one network, retrospective inputs.
- Satellite counts differ between 6 h and 24 h fixtures, handled by common-key scoring.
- The 24 h rule drops up to 5 satellites at 00:00. Including the previous day's broadcast file is a
  declared input change still to make.
- YELL is excluded on two days because Astra's frozen parser refuses a Galileo metadata event.
- This is not operational or seasonal validation.

### Resources

- **Guarded time:** 885 s of stage workers plus 8932 s of fits (about 2.7 h).
  - A0 and FB6 arms: 283–456 s each.
  - L\* 24 h arms: 2044–2424 s each.
- **Peak job memory:** 433 MiB. Longest worker 134 s.
- **Limits:** unchanged, and no guard nested.

---

<!-- original: claude/roadmap/STATION_EXPANSION_PROTOCOL.md -->

## Frozen protocol: network expansion toward ~25 stations (roadmap step 5)

Declared by Claude (Opus) on 13 September 2026 UTC, before any step 5 screen, download, fit or
score. It was written while the step 3 fits were running, so no step 3 or bench score had been
seen. The code is `claude/roadmap/station_screen.py`, `fetch_day.py`, `long_prepare.py` and
`run_long.py`.

### Question

Adding simultaneous tracking was the project's largest historical gain (12 → 14 stations: 56 m →
0.82 m). Does growing the frozen 14-station network to about 25 improve raw IGS agreement, with
everything else unchanged? And does it make results less sensitive to a single-station outage?

### Screening (no SP3/CLK)

1. **Listing:** BKG daily observation listing for **2026-08-02** (DOY 214), 30 s `MO` markers,
   stored in `claude/data/screen214/`.
2. **Header screen:** a 32 KB header range per candidate. Eligible stations need:
   - a supported C1W/C2W code pair with L1C|L1W/L2W phase;
   - an exact type-mean receiver antenna calibration in `igs20.atx`;
   - a valid IGc20 coordinate interval on the date;
   - no PSD model;
   - FES2014b ocean-loading coefficients;
   - GPS time system (or undeclared).

   C1C-only stations (`compatible_with_code_biases`) are **recorded but excluded** from this step.
   Including them needs a satellite C1C–C1W bias product and its own parity checks. That is a
   separately declared sub-step (5b), not done here.
3. **Geometry:** starting from the frozen 14 stations, **11 stations are added one at a time**, each
   time choosing the station that most increases the information score.
   - The score is Astra's clock-centred line-of-sight information: 10° mask, sin² weights, summed
     log-determinant over satellites.
   - It is computed on a 24 h broadcast grid at 15-minute steps for 2 August.
   - Ties or near-ties are broken by rank only; there is no manual choice.
4. **Acquisition:** each selected station's daily file for 2 August goes through `fetch_day`:
   - header-first download, pinned RNXCMP, before/after header equality;
   - the full file is written to `claude/data/day214/`.

   A station that fails download or decoding is replaced by the next-ranked eligible station. That
   is the only substitution allowed, and it must be disclosed.

### Fits (2 August, from broadcast seeds and x = 0; all other settings unchanged)

- **N6:** 6 h (12:00–18:00), fixed block nominal D0, 25 stations. Compared with **FB6** (step 1
  arm B, 14 stations).
- **NL:** the step 4 L\* arc configuration with 25 stations. Compared with L\* at 14 stations on
  2 August.
  - If the streaming workspace preflight (256 MiB, unchanged) refuses the 24 h / 25-station system,
    NL uses 12 h (12:00–23:50) with the same force configuration, and the fallback is disclosed.
  - The limit is never raised.
- **Preparation:** `long_prepare --stations` gets the 25-station list (the frozen 14 first, then the
  added stations in screen order), with `--extra-stations NAME=MARKER` and `--inputs` for the new
  files.

### Scoring (evaluation-only)

- **Windows:** 12:00–18:00 for N6 vs FB6, and the L\* window for NL vs L\*. Both use native keys
  common to the compared arms, with all satellites and no alignment.
- **Reported:** pooled 3D/RAC/URE; per block; per satellite; paired median ratio; >0.1 m
  regressions; the number of satellite-epochs below three viewing sites (from the fixture) before
  and after.
- **Predeclared descriptive flag:** N6 at least 5% better than FB6 on 2 August. Likewise NL vs L\*.
  A single day is a sensitivity result, not adoption. If time allows, the same 25-station N6 arm
  runs on the bench days with the bench protocol's consistency rule.
- **No tuning:** no station removal, weighting change or satellite exclusion based on scores.

### Resources

- Unchanged guard limits.
- A 25-station 6 h fit is expected at roughly 1.8× the 14-station links. Chunk sizing and the
  trajectory cache work as in steps 2–3.
- Downloads: about 11 stations at 10–20 MB each.

---

<!-- original: claude/roadmap/STATIONS_RESULTS.md -->

## Result: network expansion to 25 stations, 2 August (roadmap step 5) — both flags pass

Claude (Opus), 13 September 2026 UTC. Frozen protocol:
[STATION_EXPANSION_PROTOCOL.md](STATION_EXPANSION_PROTOCOL.md). Stage:
`claude/runs/20260913T214809Z-roadmap-stations` (`stage.json`). One day only (2 August). Results
are raw and unaligned, with no score-based choices.

### Screening (no SP3/CLK)

- **Candidates:** 334 daily 30 s MO markers from the BKG listing for day 214. Header screen results
  are in `claude/data/screen214/`:
  - **81 compatible:** C1W pair, exact antenna calibration, IGc20 coordinate, no PSD, BLQ available;
  - **43 C1C-only**, which need satellite code biases and are excluded from this step, as declared;
  - **210 rejected**, each with its reason recorded.
- **Selection:** a greedy 24 h clock-centred line-of-sight information screen from the frozen 14
  added the stations below in order. All 11 downloaded and decoded; no replacement was needed.

| Order | Station | Marker | Median sites/epoch after | Epoch fraction with <3 sites | Worst satellite fraction <3 |
|---:|---|---|---:|---:|---:|
| — | (frozen 14) | | 4 | 0.116 | 0.177 |
| 1 | SGOC (Sri Lanka) | SGOC00LKA | 4 | 0.074 | 0.115 |
| 2 | KOKB (Hawaii) | KOKB00USA | 5 | 0.023 | 0.063 |
| 3 | SUTH (South Africa) | SUTH00ZAF | 5 | 0.006 | 0.021 |
| 4 | KIT3 (Uzbekistan) | KIT300UZB | 5 | 0.005 | 0.021 |
| 5 | KIRI (Kiribati) | KIRI00KIR | 6 | 0.001 | 0.010 |
| 6 | NKLG (Gabon) | NKLG00GAB | 6 | 0.001 | 0.010 |
| 7 | MDO1 (Texas) | MDO100USA | 6 | 0.000 | 0.000 |
| 8 | EUR2 (Nunavut) | EUR200CAN | 6 | 0.000 | 0.000 |
| 9 | VACS (Mauritius) | VACS00MUS | 7 | 0.000 | 0.000 |
| 10 | PIMO (Philippines) | PIMO00PHL | 7 | 0.000 | 0.000 |
| 11 | CHPI (Brazil) | CHPI00BRA | 7 | 0.000 | 0.000 |

- **Data:** station files are in `claude/data/day214/` with per-file records. The 25-station input
  manifest is `claude/data/day214/inputs.json`.
- **Fixtures:**
  - 6 h: 31 satellites, 8508 links (1.80× the 14-station 4731).
  - 24 h: 27 satellites, 28,898 links. G02, G05, G13, G18 and G29 are rejected by the frozen LNAV
    rule, as with 14 stations.

### Fits and scores

**N6: 6 h, fixed block D0, 25 stations**, against FB6 (step 1 arm B, 14 stations). Window
12:00–18:00, 775 samples, 31 satellites.

| Arm | 3D (m) | R / A / C (m) | URE (m) | IIF / IIIA / IIR / IIR-M |
|---|---:|---|---:|---|
| FB6 (14 st.) | 0.3331 | 0.128 / 0.240 / 0.193 | 0.1329 | 0.303 / 0.320 / 0.507 / 0.263 |
| **N6 (25 st.)** | **0.1953** | 0.080 / 0.148 / 0.099 | **0.0823** | 0.195 / 0.242 / 0.125 / 0.160 |

- **N6 against FB6:** **−41.4%**, median per-satellite ratio 0.592.
- 25 satellites improve and 6 worsen, with **no regression over 0.1 m**.
- Converged in 2 linearizations, 391 guarded s.

**NL: the bench's L\* configuration (24 h + ECOM5) with 25 stations**, against 24h-E5 with 14
stations. The 25-station 24 h system passed the unchanged 256 MiB streaming preflight (chunk
estimates 183–211 MiB), so the 12 h fallback was not needed.

| Window | Samples | 14 st. 3D | **25 st. 3D** | 14 st. URE | **25 st. URE** | Change | Improve / worsen | >0.1 m regressions |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Full day 00:00–23:45 | 2592 | 0.1714 | **0.1464** | 0.0609 | **0.0464** | **−14.5%** | 23 / 4 | G21 +0.25 |
| 12:00–18:00 | 675 | 0.1532 | **0.1221** | 0.0511 | **0.0387** | **−20.3%** | 21 / 6 | G21 +0.19 |

- **NL full-day R / A / C:** 0.043 / 0.120 / 0.072 m.
- **By block (full day):** IIF 0.103, IIIA 0.215, IIR 0.093, IIR-M 0.116.
- Converged in 3 linearizations, 3374 guarded s, peak 503 MiB job memory, longest worker 107 s.

### Predeclared flags (one day, descriptive)

| Flag | Result |
|---|---|
| N6 ≥5% better than FB6 | **passes** (−41.4%) |
| NL ≥5% better than L\* at 14 stations | **passes** (−14.5% full day; −20.3% on 12:00–18:00) |

### Reading

- **Coverage, not only force modelling, still limited the fits.**
  - Going from 14 to 25 stations removes nearly all satellite-epochs with fewer than three viewing
    sites.
  - The 6 h block-fixed error drops 41%.
  - The best configuration (24 h + ECOM5) gains a further 15–20%.
- **Best result of the project:** **24 h + ECOM5 with 25 stations reaches 14.6 cm 3D / 4.6 cm URE
  over the full day** and **12.2 cm / 3.9 cm on 12:00–18:00**. That is 1.2–1.4× the 10.13 cm
  3D and 1.07–1.28× the 3.62 cm URE benchmark, though on one day and 27 satellites.
- **G21** (IIIA) is the one regression over 0.1 m in NL. Its 24 h error rises by about 0.2 m.
- **Limits:**
  - One day; the bench's multi-day consistency test has not been repeated with 25 stations.
  - The 43 C1C-only stations are still excluded; a code-bias product would open them.
  - The 24 h fixture still loses 5 satellites at 00:00.
  - Memory headroom is shrinking: the 24 h / 25-station workspace estimate reaches 211 of 256 MiB.
    More stations or longer arcs will need ambiguity elimination at arc end, or another memory
    measure, before the unchanged preflight refuses them.

### Resources

- **Guarded time:** stage workers 581 s (screen, downloads, prepares, evaluations), N6 391 s,
  NL 3374 s. Wall time about 72 minutes.
- **Downloads:** 11 station days of about 10–20 MB each, from BKG's public mirror with the pinned
  RNXCMP.
- **Limits:** unchanged.

---

<!-- original: claude/roadmap/BLOCK_D0_PROTOCOL.md -->

## Frozen protocol: block-specific nominal D0 (roadmap step 1)

Declared by Claude (Opus) on 13 September 2026 UTC, before any calibration, fit or scoring
in this experiment. The user approved the plan in `claude/PROJECT_REVIEW.md` §6. Motivation:
the review's post-hoc finding that the fixed nominal D0 (-1e-7 m/s²) is block-biased. This test
checks that finding with an out-of-sample calibration. It changes no root estimator, Astra
tool or archive; all code is under `claude/roadmap/`.

### Question

Does replacing the single nominal D0 with a **block-mean D0 calibrated on an earlier day**
improve raw station-only orbit agreement on August 2 and August 3? Is a block-centred
D0 prior better than both the fixed nominal and the unrestricted D0?

### Calibration (strictly before both evaluation days)

- **Day and window:** 2026-08-01, 12:00–18:00 GPST, origin 11:59:50 GPST, duration 21620 s.
  Same force model and integration settings as the station pilots (`OrbitForceModel`, EGM2008
  d/o 12, DE440s, `finals2000A.all`).
- **Data:** `data/stage3/IGS0OPSRAP_20262130000_01D_15M_ORB.SP3.gz`, pinned in
  `data/stage3/manifest.json`. Native epochs are t = 10 + 900k s, k = 0..24.
  - Training uses even k (13 samples); odd k (12 samples) are held out and reported only.
  - Samples that are missing, manoeuvring or predicted make that satellite's calibration
    invalid. Invalid satellites are reported and not replaced.
- **Satellites:** the 31 of the August-2 six-hour fixture.
- **Initial state:** the IGS polynomial inertial state at t = 0 (the origin). There are no priors.
  - *Pre-campaign amendment:* the first draft said t = 10 s. A guarded smoke run (G27, G04) showed
    that this puts a 39 km error into a t = 0 initial state. The fit converged regardless, but the
    code and protocol were corrected before the campaign.
  - The smoke run revealed only those two calibration values (G27 -1.0871e-7, G04 -7.360e-8). No
    station score was seen.
- **Fit:** `claude.tools.force_parameter_fit.solve_force`, used unchanged, variant `d0`
  (six states + D0). A `fixed` variant also runs for context.
- **Blocks:** from `data/stage3/igs20.atx` TYPE / SERIAL NO entries valid on the calibration
  date. IIR-A and IIR-B merge into **IIR** (same bus); IIR-M, IIF and IIIA stay separate.
- **Frozen values:**
  - Block nominal = arithmetic mean of the valid per-satellite D0 in that block.
  - Prior sigma for arm C = max(3e-9 m/s², pooled within-block sample standard deviation).
  - The 3e-9 floor was chosen knowing the August-2 reference scatter (pooled ~2.5e-9). It was
    never chosen from station scores.
- **Leakage rule:** calibration results are written once and hash-pinned before any station
  fit reads them. IGS products for 1 August are prior-day information, compatible with rapid
  latency.

### Station arms (each day uses its existing prepared fixture, unchanged)

- **Fixtures:**
  - August 2: `runs/20260912T161029Z-0ddb71b3/fixture.json`, the dated August-2 fixture.
  - August 3: `claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json`.
- **Existing arms, read from archives, not rerun:**
  - A0, nominal fixed D0: Aug 2 `claude/runs/20260912T021739Z-arc/six-1`; Aug 3 `.../day215-pod/fixed-linear-2`.
  - A1, unrestricted estimated D0: Aug 2 `claude/runs/20260912T145220Z-station-d0/linear-1`; Aug 3 `.../day215-pod/d0-linear-3`.
- **New arms:**
  - **B, block-fixed:** each satellite's fixed D0 is its block nominal; other ECOM terms zero; no
    new parameters.
  - **C, block-prior:** one D0 correction per satellite (scale 1e-7), prior centred on the block
    nominal with the frozen sigma.
- **Unchanged:** observations, sigmas, the 10° cutoff, native arcs and the minimum-three-row rule,
  broadcast seeds, 1000 m / 1 m/s orbit priors, the 0/3/6 h wet basis and priors, the BRUX clock
  datum, float ambiguities, `reduced_qr`, `nonlinear_stop`, and the line-search fractions
  1/.5/.25/.125.
- **Start:** x = 0 (broadcast seeds, zero corrections). At most four linearizations per arm/day;
  the fourth must converge.
- **Forward parity gate before any new fit:** B's pilot with every nominal set to -1e-7 must
  reproduce the archived August-3 fixed final residuals, sigmas and cost at its archived x. This
  must be exact, or the run stops.
- **Order:** B on Aug 3, then B on Aug 2, C on Aug 3, C on Aug 2, then evaluation.

### Scoring (evaluation-only; reference products are read only there)

- **Scope:** raw IGS rapid comparison, no alignment, all 31 satellites. Common domain is
  t ≤ 10810 s (403 samples); the full domain is 775 samples. The exact native keys must be
  identical across all four arms on a day.
- **Reported:**
  - 3D, RAC and orbit-only URE (contract formula);
  - per satellite and pooled per block (IIF, IIIA, IIR, IIR-M);
  - paired per-satellite median of log(RMS_arm / RMS_A0);
  - satellites improving and worsening;
  - every >0.1 m per-satellite regression against A0;
  - arm C coefficients and formal sigmas.
- **Self-check:** the evaluator must reproduce the archived A0/A1 pooled RMS (0.543656441 /
  0.441752106 / 0.620816744 / 0.713457544 m, common) within 2e-8 m. Otherwise it stops.

### Predeclared reading

- **Benefit flag for B:** common and full 3D RMS both ≥5% better than A0 on **both** days.
  - If the flag passes, B is recommended to Astra as the new *nominal* model for further work.
    It is a correction of a fixed input, not added freedom.
  - If it fails on either day, record the failure; no re-selection of blocks, calibration day or
    values.
- **Arm C:** descriptive. It is compared with B, A0 and A1 on the same flags, with no new gate.
- **Limits of the evidence:** two evaluation days support replication across two days, not
  generality. The per-block view is predeclared here, so it is no longer post hoc for this
  experiment. No satellite exclusion, alignment or sigma retuning.

### Resources

- **Guard:** every worker runs serially under the unchanged `customkf.guard`: 2 GiB job commit,
  one core/thread, 10% CPU, 8 GiB available reserve, 128 MiB scratch. No nesting.
- **Worker caps:** calibration and parity 300 s each; linearization and trial 300 s; evaluation
  300 s.
- **Budget:** roughly 50–70 guarded minutes.
- **Stop conditions:** guard failure, pin mismatch, parity failure, budget/rank failure,
  exhausted line search or nonconvergence. Never raise limits or resume in place.
- **Coordination:** the controller refuses to start if another Python process exists (for
  example Astra's GUAM-gap controller).

---

<!-- original: claude/roadmap/BLOCK_D0_RESULTS.md -->

## Result: block-specific nominal D0 (roadmap step 1) — benefit flag passes on both days

Claude (Opus), 13 September 2026 UTC. Frozen protocol: [BLOCK_D0_PROTOCOL.md](BLOCK_D0_PROTOCOL.md).
Campaign: `claude/runs/20260913T015012Z-block-d0` (status
`block_d0_campaign_complete_not_accuracy_acceptance`). All results are raw, unaligned and include
all 31 satellites. No root estimator or Astra file changed.

### Headline

Replacing the single fixed D0 (-1e-7 m/s²) with **block-mean D0 values calibrated on the previous
day (1 August)** cuts 3D RMS by 22–39% on both evaluation days. It beats both the nominal fixed
arm and Astra's unrestricted per-satellite D0.

| 3D RMS (m), all 31 satellites | A0 nominal fixed | A1 unrestricted D0 | **B block-fixed** | C block prior (3 nm/s²) |
|---|---:|---:|---:|---:|
| Aug 2, common (403) | 0.543656 | 0.441752 | **0.341886 (−37.1%)** | 0.334020 (−38.6%) |
| Aug 2, full (775) | 0.547216 | 0.440239 | **0.333137 (−39.1%)** | 0.325503 (−40.5%) |
| Aug 3, common (403) | 0.620817 | 0.713458 | **0.481354 (−22.5%)** | 0.480168 (−22.7%) |
| Aug 3, full (775) | 0.622874 | 0.693766 | **0.448801 (−28.0%)** | 0.448790 (−28.0%) |

**The predeclared flag for B passes:** at least 5% better than A0 in both domains on both days
(`arm_B_predeclared_flag_both_days_both_domains: true`). The evaluator reproduced all four archived
A0/A1 pooled RMS values within 2e-8 m before scoring the new arms.

| Orbit-only URE (m), full domain | A0 | A1 | B | C |
|---|---:|---:|---:|---:|
| Aug 2 | 0.2724 | 0.1836 | 0.1329 | 0.1271 |
| Aug 3 | 0.3167 | 0.2759 | 0.2224 | 0.2182 |

- **Radial, along and cross all improve.** Cross-track improves most: Aug 2 full 0.374 → 0.193 m;
  Aug 3 0.373 → 0.188 m.
- **Paired per-satellite medians** (B/A0, full domain): 0.738 on Aug 2 and 0.852 on Aug 3.
- **Satellites improving:** 28/31 on Aug 2 and 21/31 on Aug 3.

### Calibration (1 August, frozen before any station fit)

- **Source:** IGS rapid orbit for day 213, 12:00–18:00, reference-only fits of six initial states
  plus D0.
  - Training uses 13 native epochs; 12 held out. All 31 satellites are valid.
  - Held-out RMS: 0.8–3.9 cm with D0, against 1.4–46.8 cm with the fixed nominal.

| Block (ANTEX, 1 Aug) | n | Mean D0 (nm/s²) | Sample sd |
|---|---:|---:|---:|
| IIF | 11 | −108.16 | 0.85 |
| IIIA (GPS III) | 9 | −80.98 | 4.06 |
| IIR (A+B) | 4 | −102.11 | 2.60 |
| IIR-M | 7 | −99.36 | 1.49 |

- **Pooled within-block sd:** 2.53 nm/s², so arm C's prior sigma is 3 nm/s² (the declared floor).
- **Day-to-day stability:** these match the August-2 reference fits to within 0.2 nm/s² per block
  mean (review §2.1).
- **Smoke-test correction:** a pre-campaign guarded smoke test caught an initial-state time offset
  (t = 10 s used as t = 0). It was corrected in code and protocol before the campaign; see the
  protocol amendment.

### By block (full domain, 3D RMS m)

| Block | Aug 2 A0 → B | Aug 3 A0 → B |
|---|---|---|
| IIF | 0.494 → 0.303 | 0.636 → 0.519 |
| IIIA | 0.732 → 0.320 | 0.781 → 0.430 |
| IIR | 0.532 → 0.507 | 0.460 → 0.413 |
| IIR-M | 0.304 → 0.263 | 0.421 → 0.366 |

Every block improves on both days, not only GPS III. The IIF gain is the ~8 nm/s² correction; the
IIR and IIR-M gains are indirect, through shared clocks and ambiguities.

### Regressions and satellites to watch (>0.1 m versus A0)

- **August 2:** none in either domain for B or C.
- **August 3, B:**
  - common: G18 +0.409, G25 +0.135, G27 +0.167;
  - full: G18 +0.184 only.
- **August 3, C:** common G18 +0.317, G25 +0.147, G27 +0.271; full G18 +0.127, G27 +0.119.
- **G18 (IIIA, SVN75):** its own 1 August reference D0 is −87.8 nm/s², the furthest from the IIIA
  block mean of −81.0.
  - Per-satellite calibration, rather than block means, is a natural refinement.
  - It must be predeclared and tested on new days, not tuned on these two.
- **G27:** A1's 2.235 m full-domain error on August 3 becomes 0.280 m (B) and 0.373 m (C). Arm C's
  G27 estimate is −109.2 nm/s², within 0.35σ of its block mean. There is no runaway once the
  coefficient is anchored.

### Arm C (block-centred prior) versus B

- **Estimates:** C's D0 values stay within |z| ≤ 1.0 of their block means (prior sigma 3 nm/s²).
  Formal posterior sigmas are 2.3–3.0 nm/s², so six hours of station data barely update a
  3 nm/s² prior.
- **Scores:** C is marginally better than B on August 2 (0.326 vs 0.333 m, full) and equal on
  August 3.
- **Reading:** on six-hour arcs the gain comes from the *nominal*, not from estimation. That is
  consistent with the review's bias-versus-variance reading. Whether estimation adds value on
  longer arcs is step 3's question.

### Interpretation and limits

- **The review's post-hoc hypothesis now holds up.** The calibration came from a separate earlier
  day, and the test used two evaluation days with a predeclared flag.
- **The fixed nominal D0 was the largest single model error** identified in the project so far. The
  earlier "D0 helped on day 1, failed on day 2" story is explained by estimation noise around a
  block-biased nominal.
- **This is not accuracy acceptance.**
  - Two days, one six-hour window each, one network.
  - The 0.33–0.45 m level is still 3–4× the 10.13 cm benchmark.
  - Step 4's multi-day bench is needed before calling this general.
- **Recommendation to Astra:** treat block-calibrated nominal D0 (prior-day IGS reference fits,
  frozen) as the new fixed-force control for further experiments. This is a correction of a fixed
  input, not added freedom.
  - IGS products from a prior day are rapid-latency compatible.
  - The calibration must always predate the evaluation day.

### Resources

- **Guarded totals:** 2921.5 s (48.7 min) across 21 serial workers.
- **Peak job memory:** 414.3 MiB, with at least 15.63 GiB available.
- **Longest worker:** 208 s, within the unchanged 300 s cap.
- **Smoke runs:** evaluator and two-satellite calibration, kept in `claude/runs/roadmap-smoke/`.

### Archive map

- `calibration-fit-0/1/calibration_fits.json`: per-satellite fits.
- `calibration/calibration.json`: frozen block means and prior (sha256 `1a8c1d6e…`).
- `parity/parity.json`: the block pilot at nominal −1e-7 reproduces the archived August-3 fixed arm
  bitwise.
- `B-03-linear-2`, `B-02-linear-1`, `C-03-linear-2`, `C-02-linear-1`: final checkpoints.
- `evaluation/evaluation.json`: every per-satellite, per-block and per-domain number above.

---

<!-- original: COMPARISON_CONTRACT.md -->

## Comparison contract v1

Frozen for Stage 0 on 2026-09-05 local time (2026-09-06 UTC). Changes to a convention require a new contract version and fresh validation. This is the GPS-only contract; it does not claim a general GNSS parser or a completed orbit estimator.

### Canonical evaluation

| Item | Frozen rule |
|---|---|
| Reference and sign | IGS is reference; all differences are **candidate minus reference**. |
| Units | Float64 metres, metres/second and seconds internally. SP3 positions convert from kilometres; SP3 clocks from microseconds. |
| Epoch representation | Integer nanoseconds since 1980-01-06 00:00:00 GPS time. Match exact `(epoch, GPS PRN)` keys. No interpolation, nearest-neighbour matching or UTC relabelling. |
| Time support | SP3 `%c` must declare GPS. Old SP3-a without a time-system field requires an explicit GPS declaration in provenance. Other time systems are rejected until a tested conversion exists. |
| Position origin | Satellite centre of mass (COM). Both inputs require an explicit declaration. Never compare NGA antenna-phase-centre `.apc` as COM; the cache used here is the prior project's `.eph` comparison material, whose NGA headers also state `SATCOM`. |
| Terrestrial frame | Preserve the literal SP3 frame and dated realization evidence. The strict matcher requires the same frame/time labels. Equal labels are necessary, **not sufficient**, evidence of physically consistent realizations; the input manifest must establish the realization and antenna conventions. |
| Frame conversion | A future production path must use a dated ITRF/IGS realization and tested IERS/ERFA terrestrial/celestial transforms with explicit UTC, UT1, TT and EOP vintage. This is not implemented in Stage 0. The RAC API takes inertial velocity expressed in the same axes as reference position. |
| RAC | `R = r/|r|`, `C = (r × v_inertial)/|r × v_inertial|`, `A = C × R`. Project the candidate-minus-reference position difference on these reference axes. Earth-fixed finite-difference velocity alone is not the inertial velocity. |
| Alignment | Raw coordinates are the primary score. No fitted translation, rotation, scale, orbit bias or per-satellite demeaning. Any later Helmert diagnostic gets a separate label and never replaces the raw score. |
| Orbit-only URE | `sqrt((0.98 R)^2 + (A^2 + C^2)/49)` in metres. The radial amplitude, rather than its variance, is weighted by 0.98. This follows the existing paper's definition. |
| Clock-inclusive SISRE | `sqrt((0.98 R - c Δt)^2 + (A^2 + C^2)/49)`, `c = 299792458 m/s`, `Δt = candidate clock - reference clock` in seconds. This is a separate metric from orbit-only URE. |
| Clock datum | When comparing clocks, retain raw differences and separately subtract the arithmetic mean of eligible matched GPS clock differences at each epoch. Save offsets and satellite counts. No satellite-wise mean removal. A one-satellite epoch cannot establish a useful relative clock score. |
| Missing values | Retain missing positions/clocks explicitly. All-zero XYZ or missing-value sentinels invalidate an orbit row; one zero coordinate alone does not. Reject nonfinite values, duplicates, truncation and unsupported time systems. |
| Flags | Canonical orbit matching rejects rows flagged as maneuver or predicted orbit in either product. Missing/event/predicted clocks do not invalidate an otherwise valid orbit; clock evaluation must separately exclude those clocks. Full station/navigation health and maneuver-arc screening comes with later ingestion. |
| Exclusions and coverage | Report intersection counts, unmatched rows, invalid positions, orbit flags and predeclared exclusions. Never create exclusions from the candidate residuals to improve a score. Publish raw and screened results and retained coverage. |
| Statistics | Equal weight per retained satellite-epoch. Component RMS is `sqrt(mean(component^2))`; 3D RMS is `sqrt(mean(R^2+A^2+C^2))`; URE RMS is `sqrt(mean(URE^2))`. Also retain signed component means. This is not the mean 3D norm. |
| Endpoint handling | Do not silently discard endpoints. A later velocity interpolation/export method must report endpoint performance separately and demonstrate negligible numerical error. |

SP3 format authority: [IGS, *SP3-d*, header descriptions and Position and Clock Record](https://files.igs.org/pub/data/format/sp3d.pdf), including the `%c` time-system field, units, missing values and flags in columns 75, 76, 79 and 80. The Stage 0 reader ignores velocity/covariance records, counts velocity records, and does not interpret formal accuracy codes. No general SP3 compliance claim is made.

### Historical paper compatibility

`customkf.audit_stage0` has a deliberately named `paper_compatibility` path. It preserves the original study's approximate GMST rotation, naive calendar tags and NumPy central differences with second-order endpoints. It compares original NGA WGS84/G2296 coordinates with IGS IGc20 coordinates without relabelling or fitting them. **It is a reproduction of that study's calculation, not proof of an exact realization transformation or a validated IERS transform.** The canonical matcher rejects this unexplained frame mismatch.

The old web comparator and paper are not interchangeable. The web path differentiates Earth-fixed positions; the paper first rotates the reference positions. The web URE weights `R^2` by 0.98, producing 0.989949494 m for a 1 m purely radial error; the canonical/paper formula produces 0.980000000 m. Those differences are preserved in diagnostics, not silently carried into the new estimator.

The eight satellite-days in `data/stage0/event_days.csv` are frozen **only to reproduce the historical NGA-versus-IGS benchmark**. They are not a blanket excuse to exclude those days from our future orbit product. The March 4 G20 label is a historical discrepancy flag; its physical cause is unverified here. The compatibility report shows all raw rows and the old screened result separately, including counts of SP3 flags that the original parser discarded.

### Target and rapid-latency boundary

The stored 359-day paper benchmark is R/A/C RMS **3.43 / 6.28 / 7.17 cm**, 3D RMS **10.13 cm**, orbit-only URE RMS **3.62 cm**, over 1,090,304 retained rows. These are rounded stored study results, not values recomputed across the full study in Stage 0. Success requires comparable dates, samples, coverage and declared screening; passing a two-day comparator audit does not meet this orbit-quality target.

Precise SP3 files in this fixture set are evaluation references and later dynamic-fit development inputs. They must not become target-period pseudo-observations or tight priors in the observation-derived POD stages. Station OBS/NAV and permitted auxiliary products will require availability timestamps and vintages at the chosen rapid cutoff. Historical cache timestamps do not establish those arrival times. The development set has **no certified rapid-replay eligibility as estimation input**; even the file labelled IGS rapid is currently an evaluation reference. No station data have been downloaded, and no holdout set has been consumed.

The quiet and eclipse labels are development selections from the old approximate geometry, not verified attitude events or SVN/block histories. Recompute them with dated spacecraft metadata and the force-model ephemerides before using them as physical classifications.

### Stage 0 numerical gates

- Exact identity gives zero.
- Analytic ±1 cm RAC injections recover within 3 nanometres; common coordinate rotations preserve RAC within 6 nanometres. These tolerances reflect double-precision subtraction at GPS orbital radius.
- The file-to-comparator test recovers signed 1/2/3 cm displacements and a 1 ns clock offset. Real SP3 coordinates are quantized to 1 mm; arbitrary synthetic offsets would carry up to half a least-significant coordinate unit of rounding.
- Real parser positions and valid GPS keys match the old parser exactly on the pinned fixtures, while separate malformed-input tests cover known weaknesses of the old reader.
- Live legacy geometry parity is within 10 nanometres; stored quiet/eclipse component RMS values within 0.1 micrometre; stored event maximum within 1 micrometre. These are reproducibility gates, not claimed physical accuracies.
