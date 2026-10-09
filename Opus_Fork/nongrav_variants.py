"""Named, frozen variants of the physical ERP + antenna-thrust model (`Opus_Fork.nongrav`).

A variant is chosen by the controller through `OPUSFORK_NONGRAV_VARIANT`. Every worker records the
variant it actually used, and the controller refuses any mismatch. `nongrav.py` itself is never
edited: the P1/R7 campaigns pin it. A variant changes only declared per-block inputs.

| Variant | Change from `nongrav.py` | Source | Declared |
|---|---|---|---|
| `erp+thrust` | none (P1, R7) | — | 22 Sep 2026 |
| `erp+thrust+iiia2600` | GPS-IIIA mass 2161 → **2600 kg**, for both thrust and ERP | Steigenberger, Thoelert & Montenbruck (2020), Adv Space Res 66:2773: Table 3 caption, "A satellite mass of 2600 kg is adopted in both models", and Table 1 footnote b, "Solar radiation pressure estimates indicate a higher mass" | 22 Sep 2026, before any fit with it |

Why only the mass. The two published IIIA box-wing variants differ in +Z area (4.0 against 6.0 m²),
and choosing one after seeing IIIA over-corrected would be selection by score. The paper adopts
2600 kg in **both** of its models, so the mass is the single input it fixes unambiguously. The
+Z area stays at the midpoint declared originally.

Expected size, declared before running: IIIA's accelerations scale by 2161/2600 = 0.831, so
its POD radius shift falls from about 1.75 cm to about 1.46 cm. The 0.9–1.3 cm IIIA overshoot
seen on Aug 2 and Aug 7 should therefore shrink by about 0.3 cm, **not vanish**.
"""
from dataclasses import replace
import hashlib
import os
from pathlib import Path

from . import nongrav, satmeta

VARIANTS = {
    "erp+thrust": {},
    "erp+thrust+iiia2600": {"GPS-IIIA": 2600.},
}
ENVIRONMENT = "OPUSFORK_NONGRAV_VARIANT"


def current():
    name = os.environ.get(ENVIRONMENT)
    if name not in VARIANTS:
        raise RuntimeError(f"{ENVIRONMENT} must name a declared variant, got {name!r}")
    return name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(name):
    return dict(variant=name, mass_overrides_kg=VARIANTS[name],
                nongrav_sha256=_sha(nongrav.__file__), variants_sha256=_sha(__file__),
                satellite_metadata_sha256=satmeta.provenance()["sha256"])


def satellite_models(context, sats, name, day):
    meta = satmeta.load(day)
    missing = [s for s in sats if s not in meta or meta[s].block not in nongrav.GEOMETRY]
    if missing:
        raise ValueError("No metadata/geometry for "+", ".join(missing))
    overrides = VARIANTS[name]
    return {s: nongrav.PhysicalRadiation(context["model"],
                                         replace(meta[s], mass_kg=overrides.get(meta[s].block, meta[s].mass_kg)))
            for s in sats}
