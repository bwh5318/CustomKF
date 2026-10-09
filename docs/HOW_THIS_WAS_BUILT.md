# How this project was built

8 October 2026. This document summarizes how the work was organized. The private working repository also holds the
day-to-day agent instructions, hand-off notes and session logs; those are not part of the public release and are
summarized here instead.

## Who did what

- **The project owner** set the objective, made every adoption and resource decision, and decided when to stop,
  continue or publish.
- **Claude (Anthropic)** worked as a support agent until 28 September 2026 and as the main coder afterwards. It wrote
  most of the code, designed and ran the experiments, wrote the protocols, results and this documentation, and built
  the report.
- **Codex (OpenAI), called Astra in the project records,** led the early work and then acted as adviser and reviewer:
  checkpoint reviews, independent reproductions of key results, a principal-investigator review before publication,
  and reviews of the station-test controls before any score was read.
- **A separate reviewer, Sol,** reviewed the estimator on 30 September and found the antenna-derivative defect that
  stopped one validation date, plus several contract gaps that were then repaired.

The reviews are kept in the private working repository; `docs/KNOWN_LIMITATIONS.md` summarizes what they found that a reader
needs to know.

## The rules the agents worked under

These came from the owner's standing instructions and from the reviews, and they shaped every result:
- **The objective.** An independent GPS-only orbit product from station observations and broadcast navigation, closer
  to IGS final than NGA PE is. IGS final is a reference, not truth.
- **Report each test.** After every test: the meaningful result, the recommended next step, and why it advances the
  objective.
- **Pin protocols first.** A test that can lead to an adoption has a written protocol, pinned into its campaign
  records before the fit runs. Amendments are appended, never edited in, and each says whether any outcome existed
  when it was written.
- **Do not loosen a failed control.** When a control failed (for example the 8 October per-satellite check), the
  results stayed sealed, the cause was diagnosed and reviewed, and the fix kept the original limit.
- **No causal overclaims.** A diagnostic that narrows a hypothesis is not an identification. Fit inputs and model
  selection are recorded separately; reference-derived priors are labelled "reference-informed".
- **Never raise a limit to make a run proceed.** Resource limits (memory, CPU, GPU, time) are enforced by guards; a
  refusal means wait or replan.
- **Preserve history.** Scientific manifests, fixtures, pins and earlier report revisions are never rewritten.
  Corrections go into an append-only index (the last section of `docs/RESULTS_PHASE2.md`).
- **Distinguish** a prepared hand-off from a dispatched one, a recorded result from an independently verified one,
  and a diagnostic gate from physical or operational validation.

## How the computing was organized

- **One Windows PC, switched off overnight.** Long work ran as resumable chains (`Opus_Fork/resume_chain.ps1`) that
  skip completed fits and resume an interrupted one from hash-verified saved workers.
- **Guards.** Numerical jobs ran inside resource guards (Windows Job Objects) with memory, CPU, thread and time caps,
  one guarded campaign at a time through a machine-wide lease (`customkf/guard.py`, `Opus_Fork/guard.py`,
  `customkf/runtime/lease.py`). The policies are summarized in `SETUP.md` section 4.
- **Local git only, until publication.** Commits separated three kinds of change: pure moves, one defect fix with a
  regression test, or one scientific change with a frozen protocol.

## Where the decisions are recorded

| Record | What it holds |
|---|---|
| `Opus_Fork/experiments/*/PROTOCOL.md` | Frozen protocols and their appended amendments |
| `Opus_Fork/experiments/*/RESULTS.md` | The result of each later experiment |
| `docs/RESULTS_PHASE1.md`, `docs/RESULTS_PHASE2.md` | Every earlier protocol and result write-up, combined in order |
| End of `docs/RESULTS_PHASE2.md` | The correction index: every correction to an earlier claim |

The configuration registry, the decision log, the backlog and the report archives stay in the private working repository.

## What is not in the public release

- The agent instruction files (`AGENTS.md`), the session hand-off file and the dated notes between agents: working
  records, summarized here.
- The independent reviews, the configuration registry, decision log and backlog, and the report source and
  builder.
- Run folders, downloaded data, evidence files, raw campaign manifests that carry local paths, and the
  per-session logs.
- The full history of the private repository. The public tree starts from a single snapshot.
