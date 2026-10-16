# Known limitations and open items

8 October 2026. This file collects what a reader or re-user of this repository should know before relying on it.
It summarizes Astra's principal-investigator review (findings PI-01 to PI-12), the documentation review (F1 to
F11) and the project's own backlog, all kept in the private working repository. The report (`GPS_POD_PROGRESS_REPORT.pdf`, pages 22-23) gives the same
scope in brief.

## What the results are, and are not

- **A retrospective proof of concept.** The adopted default was closer to IGS final than NGA PE on five untouched
  summer dates (repaired baseline; the original as-registered result was not established), with the qualifications
  in the report.
- **Not general superiority.** Five June-July dates and fixed networks do not establish performance across seasons,
  networks or satellite conditions. Those dates were later reused for the gradient and station tests, so they are now
  exposed.
- **Not absolute accuracy.** About 3 cm is orbit-only URE relative to IGS final (3D RMS about 9 cm). IGS final is a
  reference, not truth, and shared geodetic inputs (coordinates, calibrations, Earth orientation) can correlate
  errors with it. Clocks are nuisance parameters, so nothing here is a positioning or full signal-in-space result.
- **Not rapid operation.** Every input was downloaded after the fact. No as-of replay with a fixed cut-off, predicted
  Earth orientation or dated coordinate and metadata versions has been run (PI-07). "RAP" and "FIN" in file names are
  local labels, not IGS product classes or delivery evidence.
- **Self-written is not input-independent.** The estimator is the project's own code, but it uses external
  coordinates, calibrations, Earth orientation and model data, and model choices were selected using IGS-scored
  outcomes. See the input-role table in the report (page 22).

## Statistical and numerical scope

- **Small effects and spread (PI-04).** The gradient gain averages 0.59 mm URE (smallest daily gain 0.12 mm); epochs
  and satellites are correlated, not independent replicates. Aggregate gains coexist with local losses (worst
  satellite: +1.98 cm with gradients; +4.2 cm with 50 stations). SP3 files round positions to 1 mm.
- **Numerical assurance (PI-05).** Integration and derivative checks cover synthetic and short cases. The full
  adopted model has not been reintegration-checked at its real boundaries. The Earth-radiation variational
  derivative omits the radial force-magnitude gradient (`Opus_Fork/nongrav.py`), a recorded approximation that has
  not been bounded. The convergence rule is local; the covariance is conditional on fixed coordinates and supplied
  sigmas.
- **Physical models (PI-06).** Nominal yaw attitude through eclipses; fixed Earth-radiation and thrust parameters and
  satellite masses; diagonal observation weighting; libration omitted from the sub-daily EOP. Diagnostic
  improvements narrow hypotheses but do not identify unique causes.

## Code and release integrity

| Item | Status |
|---|---|
| PI-08 strict product identity | **Open.** Evaluation and export check solution hashes and fixture bindings, and the network scoring checks force-model identity against campaign pins. A general fail-closed check of the full model, fixture and EOP identity for new exports and evaluations is not yet enforced; historical artifacts go through labelled legacy paths |
| PI-09 export overwrite | **Fixed 8 Oct** (`107b614`): default names carry the solution hash; a verified temporary file is moved into place; an existing product is never replaced |
| PI-10 repeated elevation install | **Fixed 8 Oct** (`ac5fbd5`): repeated or changed installs apply exactly one transform |
| PI-11 oracle acceptance boundary | **Fixed 8 Oct** (`727b541`): the checker exits non-zero unless it passed; the oracle SP3 reader refuses duplicates, non-GPS time systems and non-finite values |
| PI-12 isolated reproduction | **Open.** No end-to-end rehearsal of the public tree on another machine yet. Several real-data tests skip when local data or archived campaigns are absent, so a green test run on a clean checkout does not exercise them |
| B16 guard drain | **Open.** The fork guard can release its admission and mutex before terminated child processes have exited |
| Windows only | The resource guards use Windows Job Objects. The science code is plain Python, but the campaign tooling assumes Windows and a Bash shell (Git Bash) |

## Data and inputs needed to run

The repository does not include observation files, navigation files, reference orbits or large model files; see
`docs/DATA_SOURCES.md` and `SETUP.md`. Some historical experiment scripts point at caches that existed only on the
original workstation (for example `Opus_Fork/experiments/gradients/analyze.py` and the `claude/roadmap/run_*.sh`
drivers). They are kept as a record of what was run.

## Where the details are

- Report: `GPS_POD_PROGRESS_REPORT.pdf` (final report, Revision 7), sections 21-22 (pages 22-23).
- Corrections to earlier claims: the correction index at the end of `docs/RESULTS_PHASE2.md`.
- Result write-ups: `docs/RESULTS_PHASE1.md`, `docs/RESULTS_PHASE2.md` and `Opus_Fork/experiments/*/`.
- Reviews and the backlog: kept in the private working repository.
