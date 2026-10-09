"""ECOM-7 (D0, Y0, B0, Bc1, Bs1, Dc2, Ds2) with a named ERP + thrust variant, installed per worker process.

Test: `results/ECOM7_PROTOCOL.md`. The existing `customkf.orbit_forces.OrbitForceModel(count=7)` already
implements ECOM-7; the T1 census used it as variant E7. `LongPilot` and the trajectory-cache worker name
only the five ECOM5 terms, through the module constants `FORCE_NAMES` / `INITIAL_P`, and
`claude.tools.dated_fixture.restore` builds a count-5 model. `install()` changes, **in the running worker
process only** and with no file edited:

- `FORCE_NAMES` → + ("Dc2", "Ds2") and `INITIAL_P` → length 7 (nominal D0 −1e-7, the rest zero), in
  `claude.roadmap.long_pilot` and `claude.roadmap.traj_cache`;
- `restore` (in `claude.tools.dated_fixture`, `claude.roadmap.long_iteration` if loaded, and
  `Opus_Fork.iteration7`) → the same context with `OrbitForceModel(..., count=7)` on the same Environment;
- the ERP + thrust variant through `Opus_Fork.ngv_pilot` (P2 machinery), bound into every output.

`binding()` = the ngv binding + ECOM count + hashes of this file and `iteration7.py`. Caches and iteration
outputs carry it; anything without the identical binding is refused.
"""
import hashlib
import os
from pathlib import Path
import numpy as np

VARIANTS = {"erp+thrust+ecom7": "erp+thrust", "erp+thrust+iiia2600+ecom7": "erp+thrust+iiia2600"}
ENVIRONMENT = "OPUSFORK_E7_VARIANT"
NAMES7 = ("D0", "Y0", "B0", "Bc1", "Bs1", "Dc2", "Ds2")


def current():
    name = os.environ.get(ENVIRONMENT)
    if name not in VARIANTS:
        raise RuntimeError(f"{ENVIRONMENT} must name a declared ECOM-7 variant, got {name!r}")
    return name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding():
    from . import nongrav_variants as nv
    name = current()
    here = Path(__file__).parent
    return dict(nv.binding(VARIANTS[name]), variant=name, ecom=7,
                e7_sha256=_sha(here/"e7.py"), iteration7_sha256=_sha(here/"iteration7.py"))


def install():
    """Patch the running worker for ECOM-7 + ERP; returns the iteration7 module."""
    from . import nongrav_variants as nv
    name = current()
    os.environ[nv.ENVIRONMENT] = VARIANTS[name]      # ngv_pilot reads the ERP variant from here
    from claude.roadmap import long_pilot, traj_cache
    from claude.tools import dated_fixture
    from customkf.orbit_forces import OrbitForceModel
    from customkf.prepare_stage2 import DATA as DYN
    initial = np.array([-1e-7, 0., 0., 0., 0., 0., 0.])
    for module in (long_pilot, traj_cache):
        module.FORCE_NAMES = NAMES7
        module.INITIAL_P = initial.copy()
    original = dated_fixture.restore

    def restore7(path):
        context, rows, seeds = original(path)
        context["model"] = OrbitForceModel(context["model"].environment, DYN/"EGM2008_degree12.gfc", 7)
        return context, rows, seeds
    dated_fixture.restore = restore7
    import sys
    if "claude.roadmap.long_iteration" in sys.modules:
        sys.modules["claude.roadmap.long_iteration"].restore = restore7
    from . import iteration7, ngv_pilot, ngv_traj_cache
    iteration7.restore = restore7
    ngv_pilot.model_binding = binding
    ngv_traj_cache.model_binding = binding
    original_cached = iteration7.cached_products

    def bound(pilot, x, files):
        ngv_pilot.check_cache_binding(files)
        return original_cached(pilot, x, files)
    iteration7.LongPilot = ngv_pilot.VariantPilot
    iteration7.cached_products = bound
    return iteration7
