# Setting up customKF

This guide takes a fresh machine to a scored GPS orbit for one day.

- Every command below was used in this project.
- Run commands from the repository root.
- Where the project's own machine differs from yours (paths, drive letters), the difference is called out.

**Contents**
1. [What you need](#1-what-you-need)
2. [Install](#2-install)
3. [Repository layout](#3-repository-layout)
4. [Resource guards (read before running anything numerical)](#4-resource-guards)
5. [Static inputs (once)](#5-static-inputs-once)
6. [One day, end to end](#6-one-day-end-to-end)
7. [Optional: a-priori tropospheric gradients (final latency only)](#7-optional-a-priori-gradients)
8. [Long runs: resumable chains](#8-long-runs-resumable-chains)
9. [Tests](#9-tests)
10. [Station requirements and known limitations](#10-station-requirements-and-known-limitations)
11. [The report PDF](#11-the-report-pdf)

See also:
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md): every external input, with its source and citation;
- [docs/REPRODUCING_WITH_AN_LLM.md](docs/REPRODUCING_WITH_AN_LLM.md): the complete technical specification;
- [GPS_POD_PROGRESS_REPORT.pdf](GPS_POD_PROGRESS_REPORT.pdf): the narrative and the results.

---

## 1. What you need

| Requirement | Tested version | Why |
|---|---|---|
| **Windows 10 or 11, 64-bit** | Windows 11 Home | The resource guards use Windows Job Objects and PDH performance counters through `ctypes`, and the long-run chains are PowerShell scripts. The estimator code is plain Python, but the entry points refuse to run outside a guard (section 4). |
| **Python 3.12** (Anaconda distribution) | 3.12.7 | All code |
| NumPy | 1.26.4 | Arrays, linear algebra |
| SciPy | 1.13.1 | DOP853 integration, interpolation, QR |
| PyERFA | 2.0.1.4 | IAU 2006/2000A precession-nutation, Earth rotation (ERFA, from SOFA) |
| Numba | 0.60.0 | JIT for the gravity field and force kernels |
| psutil | 5.9.0 | Process and memory monitoring in the guards |
| threadpoolctl | 3.5.0 | Pins BLAS threads inside guarded workers |
| matplotlib | 3.9.2 | Figures (diagnostics and the report) |
| ReportLab, pypdf, Pillow | 5.0.1, 6.14.2, 10.4.0 (as installed on the project's machine) | Report PDF only |
| **Git for Windows (Git Bash)** | Bash with GNU tools | The `.sh` wrappers (scoring, deliverables, gradient acquisition). PowerShell runs the `.ps1` chains |
| **curl** | `C:\Windows\System32\curl.exe` (built into Windows 10/11) | All downloads (`customkf/prepare_stage2.py:CURL`) |
| **CRX2RNX** (RNXCMP 4.2.0, GSI) | vendored at `vendor/rnxcmp-4.2.0/CRX2RNX.exe`, hash-pinned | Decodes Hatanaka-compressed RINEX observation files |
| Disk | about 0.5 GB per processed day (25 stations), plus run folders | Observation files are about 17 MB each |
| Memory | 16 GB or more recommended | A guarded job needs its 4 GiB cap plus 2 GiB free to start |

No GNSS processing package (RTKLIB, Bernese, GROOPS, …) is used. The estimator is self-written. Attributions are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 2. Install

1. Install Anaconda (Python 3.12) for Windows. The project always calls it by full path: `C:\anaconda\python.exe`.
   If yours is elsewhere, substitute your path, and edit the `$py` line at the top of any chain script you use
   (section 8).
2. Check the packages (the project's machine had them through its Anaconda install; versions in section 1):

   ```bash
   C:/anaconda/python.exe -c "import numpy, scipy, erfa, numba, psutil, threadpoolctl; print('ok')"
   ```

   If anything is missing, install the tested versions from [requirements.txt](requirements.txt).
3. Clone the repository anywhere. Scripts locate everything relative to the repository root (the chain and wrapper
   scripts find it from their own location). Exceptions, kept as a historical record:
   - the optional external reference cache, `..\autocomparesp3\data\sp3_cache` (section 6.3), and two old analysis
     scripts that read it directly (`Opus_Fork/experiments/gradients/analyze.py`, `transfer_grad.py`);

**Shells.** Commands in `bash` blocks are for Git Bash; `powershell` blocks are for Windows PowerShell. Quote any
path with spaces or placeholders, and use forward slashes in Bash.

## 3. Repository layout

| Path | Contents |
|---|---|
| `customkf/` | Core library: time and frames, gravity and forces, the DOP853 integrator with variational equations, RINEX/SP3/ANTEX readers, observation model, square-root network solve, the root resource guard (`guard.py`), the campaign lease (`runtime/`) |
| `claude/roadmap/`, `claude/tools/` | The 24-hour streaming estimator (`long_pilot.py`, `streaming.py`, `traj_cache.py`) and the dated observation model (`dated_observation.py`) |
| `Opus_Fork/` | The production pipeline used for every current result: data store and fetch, preparation, the fit controller (`run_fit_elev.py`) and its workers, the model variants (`elev.py`, `sdeop.py`, `nongrav*.py`, `gradients.py`), evaluator, exporter, fork guard |
| `Opus_Fork/experiments/` | One folder per experiment: frozen protocol, scripts, results |
| `Opus_Fork/results/` | Created by the evaluator for its scored output (`*.json`); not tracked |
| `validation/oracle/` | The independent scorer: its own frame, EOP and sub-daily model, and SP3 metrics. It shares no code with production |
| `tests/` | Unit and regression tests |
| `data/`, `claude/data/`, `Opus_Fork/datastore/` | Inputs (git-ignored except small tables). `Opus_Fork/datastore/index.json` indexes all of them by hash |
| `runs/`, `Opus_Fork/runs/`, `claude/runs/` | One folder per guarded job or campaign, created at run time (not tracked) |
| `docs/` | Data sources, reproduction specification, known limitations, how it was built, combined result write-ups |

## 4. Resource guards

Every numerical job runs inside a **guard**: a supervisor process that starts the job as a Windows Job Object with
hard limits, and stops it if the machine gets busy.

- **What a guard enforces.** It refuses to start without enough free memory, and caps private memory, CPU rate,
  threads, processes, scratch space and wall time. It stops the job if total machine CPU or GPU use passes 75%.
- **What the entry points require.** Workers check for `CUSTOMKF_RUN_DIR` and refuse to run outside a guard.
- **Where output goes.** Each guarded job gets its own folder under `runs/` (root guard) or `Opus_Fork/runs/`
  (fork guard), holding `result.json`, `stdout.log` and `stderr.log`.

| Profile | Command | Limits | Use |
|---|---|---|---|
| `usage75` | `C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout SECONDS -- MODULE ARGS` | 4 GiB, 15% CPU, 2 threads; needs 6 GiB free to start | Downloads, preparation, scoring, export, analysis |
| `fork8` | `C:/anaconda/python.exe -m Opus_Fork.guard --profile fork8 --timeout SECONDS -- MODULE ARGS` | 4 GiB, 50% CPU, 1 thread × 8 processes | Fit workers, launched by the fit controller |

**Rules:**
- **One guarded job at a time.** A machine-wide campaign lease (`C:\ProgramData\customKF\coordination`) enforces
  this. A second job is refused, not queued.
- **Controllers run directly; never put a guard inside a guard.** The fit controller `Opus_Fork.run_fit_elev`
  launches its own guarded workers and holds the lease across them.
- **For QR-heavy jobs under usage75, pass `--threads 1`.** Two BLAS threads under the 15% CPU-rate cap were more
  than ten times slower.
- **A refusal is information, not an obstacle.** Wait for the machine to be quiet; do not raise limits to make a
  run proceed.
- **Inspect the lease:**

  ```bash
  C:/anaconda/python.exe -m customkf.runtime.lease status
  ```

  A lease is recovered only when it has gone without a heartbeat for its time-to-live (900 s by default,
  `customkf/runtime/lease.py`) **and** its owner and registered workers are known to be dead. If their state cannot
  be determined, the lease is treated as held. Do not delete the lease by hand while anything may still be running.

## 5. Static inputs (once)

These downloads fetch the models and calibrations into `data/stage2` and `data/stage3`, and record their hashes.
`prepare_stage3` is not static-only: it also fetches the August 2026 development files it was written for (three
NOAA CORS observation files, IGS rapid orbit and clock files, and one broadcast file for day 214). The current
pipeline does not need those; they are a historical dependency of that script.

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- customkf.prepare_stage2
```

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- customkf.prepare_stage3
```

| File | Content | Source |
|---|---|---|
| `finals2000A.all` | IERS daily EOP (polar motion, UT1−UTC, nutation corrections) | USNO / IERS Rapid Service |
| `de440s.bsp` | JPL planetary ephemeris (Sun, Moon) | JPL NAIF |
| `EGM2008_degree12.gfc` | Gravity field, truncated to degree/order 12 | ICGEM (GFZ) |
| `igs20.atx` | Satellite and receiver antenna phase-centre offsets and variations | IGS |
| `IGc20.ssc`, `soln_IGc20.snx`, `psd_IGc20.snx` | IGS20 station coordinates, velocities, solution intervals, post-seismic list | IGS |
| `FES2014b.BLQ` | Ocean-tide loading coefficients (1,294 stations) | AIUB Bernese user area |
| `Opus_Fork/datastore/static/igs_satellite_metadata.snx` | Satellite mass, transmit power, block (tracked) | IGS |
| `Opus_Fork/datastore/static/iers_ch8/*.F` | IERS Conventions ORTHO_EOP/CNMTX source (tracked; ported in `Opus_Fork/subdaily_eop.py`) | IERS Conventions Centre |

Full citations: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## 6. One day, end to end

Example day `D = 2026-06-27`. Replace it, and the marker list, with your own.

### 6.1 Check availability (headers only, no downloads)

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- Opus_Fork.fetch availability --day 2026-06-27 --markers 25
```

- **What it checks:** each station's header (signal pair, cadence, time system, antenna calibration) and the
  products for the day.
- **Network choice:** `--markers 25` is the frozen network (`Opus_Fork/fetch.py:NETWORK_25`). You can also pass a
  comma-separated list of nine-character markers.

### 6.2 Download observations and navigation

Run one guarded fetch per station, then the broadcast navigation for the day and the previous day:

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- Opus_Fork.fetch station --day 2026-06-27 --marker BRUX00BEL
```

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- Opus_Fork.fetch product --kind brdc --day 2026-06-27
```

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- Opus_Fork.fetch product --kind brdc --day 2026-06-26
```

Files land in `Opus_Fork/datastore/<YYYYDOY>/`, decoded and hash-recorded. Observations are 30 s daily RINEX 3 files
from the BKG IGS data centre.

### 6.3 Reference products (scoring only, never read by the fit)

- **IGS final orbits:**

  ```bash
  C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- Opus_Fork.fetch product --kind sp3fin --day 2026-06-27
  ```

- **NGA precise ephemeris.** Download the day's file from NGA's GNSS products page
  (`https://earth-info.nga.mil/index.php?action=gnss&dir=gnss`). Use the centre-of-mass product
  `nga<GPS week><day of week>.sp3`, not the `_apc` antenna-phase-centre variant, and place it in
  `Opus_Fork/datastore/reference/`.

  On the project's machine both products also come from an older read-only cache, `..\autocomparesp3\data\sp3_cache`.
  It is optional.

### 6.4 Index the store

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 600 -- Opus_Fork.store --rebuild
```

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 600 -- Opus_Fork.store --verify
```

### 6.5 Prepare the fixture (about 3–6 minutes)

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 1800 -- Opus_Fork.prepare --day 2026-06-27 --start 00:00 --epochs 144 --network 25 --previous-day-nav --per-epoch-nav
```

- **What it does:**
  - selects ionosphere-free code and phase at 600 s solve epochs over 24 h, with a 10° cutoff;
  - screens arcs and cycle slips;
  - applies station coordinates, tides, ocean loading and antenna calibrations;
  - merges the previous day's navigation;
  - freezes everything into `runs/<timestamp>/fixture.json`, with `step.json` recording its hash.
- **A station is missing on the day?** Pass `--stations` with the four-character list instead of `--network 25`.

### 6.6 Fit (about 1 hour of guarded time for 25 stations)

Run the controller **directly**, not inside a guard. Replace `PREPARE_FOLDER` with the folder from step 6.5:

```bash
C:/anaconda/python.exe -m Opus_Fork.run_fit_elev --variant erp+thrust+iiia2600+sdeop+elw13 --fixture "runs/PREPARE_FOLDER" --label MYFIT-0627 --config claude/roadmap/configs/unit-ecom5.json --chunk-epochs 12 --trajectory-groups 2 --worker-timeout 900 --max-linearizations 6
```

This is a reproduction run, so it has no `--protocol`. A test meant to decide an adoption needs its own protocol,
written and pinned with `--protocol PATH` before the fit (as in `Opus_Fork/experiments/*/PROTOCOL.md`).

- **Configuration:** the variant above is the current default (section 2 of the report).
- **Where it runs:** the campaign appears as `Opus_Fork/runs/<timestamp>-fit-MYFIT-0627/`.
- **Each iteration's workers:** integrate trajectories and variational equations, fold the observation chunks into a
  square-root information system, solve, and line-search.
- **When it is done:** `validation.json` reaches `long_fit_complete_not_accuracy_acceptance` and names the final
  solve folder (for example `lin2-solve`).
- **Resuming:** add `--resume <campaign folder>` after an interruption. Completed workers are reused after their
  hashes are re-verified.

### 6.7 Score against IGS final, with NGA beside it

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- Opus_Fork.evaluate --day 2026-06-27 --out-name myfit_0627 --arm MINE "Opus_Fork/runs/CAMPAIGN_FOLDER/FINAL_SOLVE_FOLDER" "runs/PREPARE_FOLDER/fixture.json" --domain full 00:00 23:45
```

- **Output:** `Opus_Fork/results/myfit_0627.json`, with raw, unaligned RMS 3D, radial/along/cross and orbit-only
  URE, per satellite and pooled.
- **NGA beside it:** the evaluator always adds NGA PE on the same satellite-epoch keys.
- **URE definition:** `sqrt(mean(0.98² R² + (A² + C²)/49))`.

### 6.8 Export an SP3 product

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 900 -- Opus_Fork.export write --solution "Opus_Fork/runs/CAMPAIGN_FOLDER/FINAL_SOLVE_FOLDER" --fixture "runs/PREPARE_FOLDER/fixture.json" --day 2026-06-27
```

- **Output:** `Opus_Fork/datastore/products/OPUS0OPSRAP_20260627_<first 12 hex of the solution hash>.SP3` (or `--out
  PATH`), at a 15-minute cadence, centre of mass, IGc20.
- **What it omits:** clocks are left out deliberately, and accuracy codes are 0 (unknown).
- **QA gate:** the file is written to a temporary sibling, re-read and compared with the solution, and moved into
  place only if it passes. An existing product is never overwritten.

## 7. Optional: a-priori gradients

The optional model adds TU Wien GRAD operational tropospheric gradients. Its products are **retrospective (final
latency)**; do not use it for anything that claims rapid latency.

```bash
bash Opus_Fork/experiments/gradients/acquire_day.sh 2026-06-27
```

That fetches the three daily files the arc needs (D−1, D, D+1) and records each file's server time. Then run the fit
with the variable set; the controller binds the arc's files automatically:

```powershell
$env:OPUSFORK_GRADIENTS = "grad_op"; C:\anaconda\python.exe -m Opus_Fork.run_fit_elev --variant erp+thrust+iiia2600+sdeop+elw13 ...
```

Exported products name the model in the header and are written as `OPUS0OPSFIN_YYYYMMDD_<hash>.SP3`. `FIN` and `RAP`
are this project's local labels, not IGS product classes or delivery evidence.

## 8. Long runs: resumable chains

- **Why chains:** a fit takes about an hour, and a campaign of several fits many hours. The project's PC is switched
  off overnight, so long work runs as a PowerShell chain that skips completed fits and resumes an interrupted one.
- **Restart:** `Opus_Fork/resume_chain.ps1` restarts a named chain (from PowerShell, in the repository root):

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File ".\Opus_Fork\resume_chain.ps1" -Chain newdate
  ```

- **What a chain does:**
  - waits for a quiet machine (GPU < 50%, ≥ 6.5 GiB free, no other guard or controller of this project);
  - resumes automatically after external stops such as machine-load stops or sleep;
  - writes progress to `Opus_Fork/runs/<chain>-chain.status`.
- **Templates:** `Opus_Fork/experiments/gradients/run_chain_newdate.ps1` and
  `Opus_Fork/experiments/networks/run_chain_networks.ps1`. They find the repository root themselves; set `$py` at the
  top if your Python is not `C:\anaconda\python.exe`.
- **What the chain's quiet check does not cover:** it waits on GPU, memory and this project's processes, not on
  total CPU. Another program's sustained CPU load makes the guard refuse each start, and the chain stops after 20
  automatic resumes. Wait for the machine to be quiet, then resume.

## 9. Tests

Most tests run directly:

```bash
C:/anaconda/python.exe -m unittest discover -s tests -t .
```

Two modules check thread limits and must run under the guard. Outside it they fail by design:

```bash
C:/anaconda/python.exe -m customkf.guard --profile usage75 --timeout 900 -- unittest tests.test_comparison tests.test_propagation
```

On the project's machine (8 Oct 2026), 427 tests are discovered; 425 pass directly, and the other two pass under the
guard. Do not run the whole suite inside a guard: tests that launch guards or take the campaign lease refuse to run
nested, by design. Some tests need the downloaded inputs and the validation fixtures, and **skip** when those are
absent, so a green run on a fresh clone does not exercise the real-data checks (docs/KNOWN_LIMITATIONS.md).

## 10. Station requirements and known limitations

**A station can be processed only if every one of these holds:**
- a daily 30 s RINEX 3 file at BKG;
- a P(Y)-code-compatible GPS signal pair (C1W/C2W with L1/L2); receivers without one would need code-bias
  corrections, which are not implemented;
- a recognised phase-shift header;
- an exact antenna and radome calibration in `igs20.atx`;
- an IGS20 coordinate solution valid on the date;
- no post-seismic deformation model in `psd_IGc20.snx` (not implemented);
- an ocean-loading entry;
- for the gradient option, coverage in the GRAD files.

On 5 Oct 2026, 149 of 293 stations listed at BKG on five summer dates met the file-level rules. The suitability
screen considered 70 of them: 13 were rejected for expired coordinate solutions before any header check, and 37 of the
remaining 57 passed the header checks (the selection record is kept in the private working repository).

**Other limitations:**
- Windows only (section 1).
- **Retrospective inputs.** The EOP file and metadata were downloaded after the dates. No real-time or rapid-deadline
  replay has been done.
- Clocks are estimated as nuisance parameters and are not a product.
- Ambiguities are float. There is no integer ambiguity resolution.
- GPS only.
- The full list of known limitations and open integrity items is in [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## 11. The report PDF

`GPS_POD_PROGRESS_REPORT.pdf` (Revision 5) is the published report. Its Markdown source, figure scripts and builder
(ReportLab, with a visual check of every page) are kept in the private working repository.
