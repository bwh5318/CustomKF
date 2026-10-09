# customKF: GPS orbits from station data, benchmarked against IGS final and NGA's precise ephemeris

A self-written precise-orbit estimator for the GPS constellation, built as a resource-bounded research project on one
Windows PC.
- **Inputs:** raw observations from about 25 public IGS tracking stations, the broadcast navigation message, and
  published models and calibrations (station coordinates, antenna calibrations, Earth orientation).
- **Output:** 24-hour orbits for the eligible healthy GPS satellites, exportable as SP3.
- **Software:** Python. No external GNSS processing package is used.

**The bar** is to be closer to the IGS final orbits than the U.S. National Geospatial-Intelligence Agency's precise
ephemeris (NGA PE) is. IGS final is a reference, not truth.

**What this is:** a retrospective proof of concept with a carefully recorded development and validation process. It
is **not** a demonstration of general superiority to NGA, of absolute orbit accuracy, or of rapid (within-a-day)
operation. See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## Where it stands (8 October 2026)

Scored against IGS final on the same satellite-epochs as NGA PE, on five summer dates (Jun 6, 20, 23, Jul 6, 23)
first drawn untouched by a pre-registered seeded stream:

| Configuration | Mean orbit-only URE | Mean daily URE ratio to NGA PE | Dates below NGA |
|---|---:|---:|---:|
| **Default** (rapid-candidate inputs, 25 stations) | 3.06 cm | **0.766** | 5 of 5 |
| Default + TU Wien gradients (final latency only) | 3.00 cm | 0.752 | 5 of 5 |
| Default + gradients, up to 50 stations | 2.55 cm | 0.638 | 5 of 5 |
| Default + gradients, 17 stations near NGA's public monitor sites | 4.83 cm | 1.215 | 1 of 5 |
| NGA PE | 4.01 cm | 1 | - |

- **Validation of the default:** below NGA in URE and 3D RMS on all five dates. One date needed a documented code
  repair, so this is the repaired-baseline result; the original as-registered result was not established. Over six
  fresh dates (including Jun 27), our constellation URE is below NGA's at 92.0% of 15-minute epochs.
- **Station tests:** doubling the network lowered URE by 15% on every date; with 17 stations the orbit no longer beat
  NGA. Both are descriptive final-latency contrasts on dates already used, not adopted configurations.
- **Relative, not absolute:** about 3 cm is orbit-only URE relative to IGS final; the 3D RMS is about 9 cm. Clocks are
  nuisance parameters, not a product.
- **Retrospective:** every input was downloaded after the fact; no rapid-deadline replay has been done.
- **Where NGA is still better:** the along-track component, on several dates.

The full account, with every improvement, every failure and the scope of each claim, is the report:
[GPS_POD_PROGRESS_REPORT.pdf](GPS_POD_PROGRESS_REPORT.pdf) (Revision 5).

## Start here

| If you want to … | Read |
|---|---|
| Run it | [SETUP.md](SETUP.md): requirements, install, guards, one day end to end |
| Know what the results do and do not show | [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) |
| Know where every input comes from | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) |
| Rebuild it from scratch, for example with an LLM | [docs/REPRODUCING_WITH_AN_LLM.md](docs/REPRODUCING_WITH_AN_LLM.md): the technical specification, models, constants, pitfalls and expected numbers |
| Read every result write-up, in order | [docs/RESULTS_PHASE1.md](docs/RESULTS_PHASE1.md) (6-19 Sep) and [docs/RESULTS_PHASE2.md](docs/RESULTS_PHASE2.md) (19-29 Sep) |
| See every correction to an earlier claim | The correction index, the last section of [docs/RESULTS_PHASE2.md](docs/RESULTS_PHASE2.md) (append-only) |
| Follow a specific experiment | `Opus_Fork/experiments/<name>/`: frozen protocol, amendments, scripts, results |
| Download example orbit files | [deliverables/sp3/](deliverables/sp3/README.md): 15 SP3 files (three networks, five dates) |
| Learn how the work was organized | [docs/HOW_THIS_WAS_BUILT.md](docs/HOW_THIS_WAS_BUILT.md) |

## How it was built

The project owner worked with two AI agents: Claude (Anthropic) wrote most of the code and ran the experiments, and
Codex (OpenAI) reviewed it at checkpoints and reproduced key results independently. The discipline that came out of
that collaboration is part of the project:
- **Protocols first.** Every adoption decision was pinned in a protocol before its fit ran; amendments are appended
  and say whether any outcome existed.
- **Untouched dates.** Claims of transfer use dates drawn by a seeded stream.
- **An independent scorer.** `validation/oracle/` reproduces the production scores with its own frame and metric code.
- **Corrections are appended, never rewritten.**

[docs/HOW_THIS_WAS_BUILT.md](docs/HOW_THIS_WAS_BUILT.md) summarizes the roles, the review process and the rules.

**This repository is a curated snapshot.** It holds the code, the tests, the report and the combined result
write-ups. The full working record (reviews, run records, evidence files, agent notes) stays in the private working repository;
paths cited in the report that are not here belong to that record.

## Repository map

| Path | Contents |
|---|---|
| `customkf/` | Core library: time and frames, forces, integration with variational equations, RINEX/SP3/ANTEX, observation model, square-root solve, resource guard, campaign lease |
| `claude/roadmap/`, `claude/tools/` | The 24 h streaming estimator and the dated observation model |
| `Opus_Fork/` | The production pipeline: fetch, store, prepare, fit controller and workers, model variants, evaluator, exporter; experiments and results |
| `validation/oracle/` | Independent scorer |
| `tests/` | Unit and regression tests |
| `deliverables/` | Example SP3 products and the script that made them |
| `docs/` | Data sources, the reproduction specification, known limitations, how it was built, and the combined result write-ups of both project phases |

## Licence, data and acknowledgements

- **Licence:** the project's own code is under the [MIT licence](LICENSE). Third-party code, vendored tools and
  routines ported from other sources keep their own terms: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- **Data:** large data files are not included. The scripts download them from their providers, listed with citations
  in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).
- **Acknowledgements:** observation data and orbit products of the International GNSS Service (IGS), through the BKG
  data centre; Earth orientation and the IERS Conventions (2010) software of the International Earth Rotation and
  Reference Systems Service (IERS), used under its licence (derived modules are identified in
  THIRD_PARTY_NOTICES.md); NGA GNSS products; JPL ephemerides; ICGEM gravity models; AIUB ocean-loading files; TU Wien
  troposphere products; the ERFA library (derived from IAU SOFA); and RNXCMP by Y. Hatanaka, GSI (Hatanaka 2008).
