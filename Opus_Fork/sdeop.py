"""ERP + thrust variants fitted with the IERS 2010 ocean-tidal sub-daily EOP (`Opus_Fork.subdaily_eop`), per worker.

Test: `results/SDEOP_PROTOCOL.md`. Diagnosis: `results/SWING_ORIGIN_NOTES.md`. `customkf.frames.EarthOrientation`
interpolates daily IERS values and omits the diurnal/semidiurnal ocean-tidal terms (IERS Conventions 2010
Ch. 8, Class 1), which IGS analysis centres apply. `install()`, **in the running worker process only**, with no file
edited:

- adds those terms to every `EarthOrientation.at` (so the dynamics' Earth rotation, the station geometry in
  `customkf.dynamic_observation`, and `LongPilot` all see them);
- selects the ECOM5 ERP + thrust variant through `Opus_Fork.ngv_pilot` (the machinery the IIIA campaigns pin);
- binds `binding()` into every trajectory cache and iteration output, so nothing fitted without sub-daily
  EOP can be mixed in.

Products of these fits are Earth-fixed through the same sub-daily rotation; score them with
`Opus_Fork.experiments.subdaily.evaluate_sd`.
"""
import hashlib
import os
from pathlib import Path

VARIANTS = {"erp+thrust+sdeop": "erp+thrust", "erp+thrust+iiia2600+sdeop": "erp+thrust+iiia2600"}
ENVIRONMENT = "OPUSFORK_SD_VARIANT"
MODEL = "IERS 2010 ORTHO_EOP ocean-tidal diurnal/semidiurnal x, y, UT1 (no libration)"


def current():
    name = os.environ.get(ENVIRONMENT)
    if name not in VARIANTS:
        raise RuntimeError(f"{ENVIRONMENT} must name a declared sub-daily-EOP variant, got {name!r}")
    return name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding():
    from . import nongrav_variants as nv
    name = current()
    here = Path(__file__).parent
    return dict(nv.binding(VARIANTS[name]), variant=name, subdaily_eop=MODEL,
                subdaily_eop_sha256=_sha(here/"subdaily_eop.py"), sdeop_sha256=_sha(here/"sdeop.py"))


def install():
    """Patch the running worker for sub-daily EOP + ERP; returns `Opus_Fork.iteration` bound to the ERP pilot."""
    from . import nongrav_variants as nv
    from . import subdaily_eop
    name = current()
    os.environ[nv.ENVIRONMENT] = VARIANTS[name]      # ngv_pilot reads the ERP variant from here
    subdaily_eop.verify_sources()
    subdaily_eop.self_test()
    subdaily_eop.install()
    from . import ngv_pilot, ngv_traj_cache
    ngv_pilot.model_binding = binding
    ngv_traj_cache.model_binding = binding
    return ngv_pilot.install()
