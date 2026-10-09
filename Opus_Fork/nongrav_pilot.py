"""LongPilot with fixed physical Earth radiation pressure and antenna thrust (test T2.1).

The estimated parameter set, objective, priors, weights and stopping rules are exactly
LongPilot's. The only change is the force model each satellite's trajectory is integrated
with: the unchanged `OrbitForceModel` wrapped in `Opus_Fork.nongrav.PhysicalRadiation`, per
satellite, using that satellite's metadata (mass, transmit power, block geometry).

`install()` points the fork's iteration worker at this pilot, and refuses any trajectory cache
not integrated with the same force-model variant. Astra's cache key hashes only the initial
state and force parameters, so a cache integrated with the plain model would otherwise be
accepted silently. Nothing in `customkf/` or `claude/` is edited; patching happens in the
worker process only.
"""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

from claude.roadmap import long_pilot as _lp
from claude.roadmap.long_pilot import LongPilot

from . import nongrav, satmeta

VARIANT = "erp+thrust"
GPS_EPOCH = datetime(1980, 1, 6)


def model_binding():
    """What a trajectory produced by this pilot depends on, beyond initial state and parameters."""
    source = Path(nongrav.__file__).read_bytes()
    return dict(variant=VARIANT, nongrav_sha256=hashlib.sha256(source).hexdigest(),
                satellite_metadata_sha256=satmeta.provenance()["sha256"])


def day_of(context):
    """Calendar date (GPS time scale) of the fixture origin; metadata is evaluated at 12:00 of it."""
    return (GPS_EPOCH+timedelta(seconds=int(context["origin_ns"])/1e9)).date().isoformat()


def satellite_models(context, sats):
    meta = satmeta.load(day_of(context))
    missing = [s for s in sats if s not in meta or meta[s].block not in nongrav.GEOMETRY]
    if missing:
        raise ValueError("No metadata/geometry for "+", ".join(missing))
    return {s: nongrav.PhysicalRadiation(context["model"], meta[s]) for s in sats}


class NonGravPilot(LongPilot):
    def products(self, x):
        if not hasattr(self, "_models"):
            self._models = satellite_models(self.context, self.sats)
        trajectories = {}
        for sat in self.sats:
            k = self.index[f"orbit:{sat}:0"]
            p = _lp.INITIAL_P.copy()
            p[0] = self.nominal[sat]
            for column in self.estimate:
                j = self.index.get(f"srp{_lp.FORCE_NAMES[column]}:{sat}")
                if j is not None:
                    p[column] += _lp.SCALE*x[j]
            trajectories[sat] = _lp.ForceTrajectory(self.seeds[sat]+x[k:k+6], self._models[sat], self.duration, p)
        c = self.context
        return _lp.NominalProducts(c["epoch"], c["origin_ns"], c["records"], trajectories,
                                   available_before_ns=c["navigation_cutoff_ns"])


def check_cache_binding(files):
    expected = model_binding()
    for path in files:
        meta = json.loads((Path(path).parent/"trajectories.json").read_text())
        if meta.get("force_model") != expected:
            raise ValueError(f"Trajectory cache {path} was not integrated with force model {expected}")


def install():
    """Point Opus_Fork.iteration at NonGravPilot and bind its cache loader to this model."""
    from . import iteration
    original = iteration.cached_products

    def bound(pilot, x, files):
        check_cache_binding(files)
        return original(pilot, x, files)
    iteration.LongPilot = NonGravPilot
    iteration.cached_products = bound
    iteration.MODEL_IDENTITY = lambda: model_binding()     # previous points must carry this model (Astra AR-01)
    return iteration
