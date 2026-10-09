"""Elevation handling variants of the sub-daily-EOP fit (`Opus_Fork.sdeop`), installed per worker process.

Test: `results/ELEVATION_PROTOCOL.md`. Motivation (`results/SENSITIVITY_RESULTS.md`): on Aug 3 a 15° cutoff improved URE
by 5.0% in every component. The SD-3 phase residuals grow as 1/sin(e)^1.27, while the fixtures weight phase as 1/sin(e).
Low-elevation phase is therefore over-weighted.

Every fixture weights rows as sigma = (0.9 m, 9 mm)/sin(e), from `Opus_Fork/prepare.py:334` and
`claude/roadmap/long_prepare.py:146`, so sin(e) = 0.9/sigma_code is recovered exactly per row. Variants, one change each:

- `cut15s`: drop rows with e < 15° (sin(e) from sigma), on any day.
- `elw13`: phase sigma = 9 mm/sin(e)^1.3 instead of /sin(e); code unchanged. The zenith sigma is unchanged, so the
  weight relative to constraints and priors at high elevation is the same. p = 1.3 is frozen from the Aug 3 residual
  calibration (fitted 1.27).
- `none` (added 1 Oct 2026, experiments/gradients/PROTOCOL.md): rows unchanged after the sigma-rule check, i.e. the
  base sub-daily-EOP model and weights, so that SD-3's configuration can run through `run_fit_elev`.

A-priori tropospheric gradients (added 1 Oct 2026; `Opus_Fork/gradients.py`): `OPUSFORK_GRADIENTS` = `none` (default)
| `grad_op` | `gpt3`. When not `none`, `install()` sets the observation hook `claude.tools.dated_observation.GRADIENT`
and `binding()` gains a `gradients` entry (source, convention, module and input hashes); with `none` neither
changes.

Bases: `erp+thrust+sdeop` (Aug 2, 7) and `erp+thrust+iiia2600+sdeop` (Aug 3, 4, 5), each matching its SD comparator.
`install()` = `sdeop.install()` for the base, then `restore` is wrapped in `claude.tools.dated_fixture`,
`claude.roadmap.long_iteration` and `Opus_Fork.iteration`, so every worker sees the same rows and sigmas.
`binding()` = `sdeop.binding()` + the change, p, and this file's hash.
"""
import hashlib
import os
from pathlib import Path
import numpy as np

from . import gradients

HERE = Path(__file__).resolve().parent
BASES = ("erp+thrust+sdeop", "erp+thrust+iiia2600+sdeop")
CHANGES = ("cut15s", "elw13", "none")
VARIANTS = {f"{b}+{c}": (b, c) for b in BASES for c in CHANGES}
ENVIRONMENT = "OPUSFORK_ELEV_VARIANT"
CUTOFF_DEG = 15.0
PHASE_POWER = 1.3
SIGMA0 = (0.9, 0.009)


def current():
    name = os.environ.get(ENVIRONMENT)
    if name not in VARIANTS:
        raise RuntimeError(f"{ENVIRONMENT} must name a declared elevation variant, got {name!r}")
    return name


def binding():
    from . import sdeop
    name = current()
    base, change = VARIANTS[name]
    os.environ[sdeop.ENVIRONMENT] = base
    return dict(sdeop.binding(), variant=name, elevation=change,
                cutoff_deg=CUTOFF_DEG if change == "cut15s" else None,
                phase_power=PHASE_POWER if change == "elw13" else None,
                elev_sha256=hashlib.sha256((HERE/"elev.py").read_bytes()).hexdigest(),
                **({} if gradients.current() == "none" else dict(gradients=gradients.binding())))


def transform(rows, change):
    """Return the rows the variant uses (new list; input rows untouched)."""
    out = []
    smin = np.sin(np.deg2rad(CUTOFF_DEG))
    for r in rows:
        sin_e = SIGMA0[0]/float(r["sigma"][0])
        if not np.isclose(float(r["sigma"][1]), SIGMA0[1]/sin_e, rtol=1e-9, atol=0):
            raise ValueError("Row sigma does not follow (0.9, 0.009)/sin(e)")
        if change == "cut15s":
            if sin_e >= smin:
                out.append(r)
        elif change == "none":
            out.append(r)
        else:
            r = dict(r)
            r["sigma"] = np.array([SIGMA0[0]/sin_e, SIGMA0[1]/sin_e**PHASE_POWER])
            out.append(r)
    return out


def install():
    """Patch the running worker; returns `Opus_Fork.iteration` bound to the ERP pilot."""
    from . import sdeop
    name = current()
    base, change = VARIANTS[name]
    os.environ[sdeop.ENVIRONMENT] = base
    iteration = sdeop.install()
    from . import ngv_pilot, ngv_traj_cache
    ngv_pilot.model_binding = binding
    ngv_traj_cache.model_binding = binding
    from claude.tools import dated_fixture
    from claude.roadmap import long_iteration
    # Wrap the unmodified loader, never an earlier wrapper: a repeated or changed install in one interpreter then
    # applies exactly one transform, the current one (Astra PI-10, 8 Oct 2026).
    original = getattr(dated_fixture.restore, "unwrapped", dated_fixture.restore)

    def restore(path):
        context, rows, seeds = original(path)
        return context, transform(rows, change), seeds
    restore.unwrapped = original
    dated_fixture.restore = restore
    long_iteration.restore = restore
    iteration.restore = restore
    # Every install sets the hook from the current source, so `none` after an earlier source clears it; the hook and
    # binding() then always agree within one interpreter (Astra C02).
    from claude.tools import dated_observation
    source = gradients.current()
    dated_observation.GRADIENT = None if source == "none" else gradients.hook(source)
    return iteration
