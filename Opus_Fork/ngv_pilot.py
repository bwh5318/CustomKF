"""LongPilot with a named ERP + thrust variant (`Opus_Fork.nongrav_variants`).

Same design as `Opus_Fork.nongrav_pilot`, which P1/R7 pin and which stays unchanged. The
variant comes from `OPUSFORK_NONGRAV_VARIANT`, is required, and is written into every worker's
output. Trajectory caches must carry the identical binding or are refused.
"""
from datetime import datetime, timedelta
import json
from pathlib import Path

from claude.roadmap import long_pilot as _lp
from claude.roadmap.long_pilot import LongPilot

from . import nongrav_variants as nv

GPS_EPOCH = datetime(1980, 1, 6)


def _date_at(ns):
    return (GPS_EPOCH+timedelta(seconds=int(ns)/1e9)).date().isoformat()


def day_of(context):
    """Calendar day of the arc midpoint, used for the satellite-metadata lookup.

    Corrected 27 Sep 2026 (Astra review N05; results/CORRECTIONS.md). This used the fixture origin, which for midnight
    fixtures is 10 s before midnight, so it selected the *previous* day's metadata. The metadata were identical for
    both days on every campaign day (Aug 1→2, 2→3, 3→4, 4→5, 6→7 checked), so no existing result changes.
    """
    return _date_at(int(context["origin_ns"])+int(float(context["duration_s"])*1e9/2))


def model_binding():
    return nv.binding(nv.current())


def satellite_models(context, sats):
    # Refuse an arc across which a satellite's metadata (PRN->SVN, block, mass, power) changes: one model per
    # satellite per arc would then be wrong for part of it.
    from . import satmeta
    start, end = int(context["origin_ns"]), int(context["origin_ns"])+int(float(context["duration_s"])*1e9)
    first, last = satmeta.load(_date_at(start)), satmeta.load(_date_at(end))
    changed = [s for s in sats if first.get(s) != last.get(s)]
    if changed:
        raise ValueError(f"Satellite metadata change within the arc for {changed}; split the arc")
    return nv.satellite_models(context, sats, nv.current(), day_of(context))


class VariantPilot(LongPilot):
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
    from . import iteration
    original = iteration.cached_products

    def bound(pilot, x, files):
        check_cache_binding(files)
        return original(pilot, x, files)
    iteration.LongPilot = VariantPilot
    iteration.cached_products = bound
    # Resolved at call time, so a later patch of model_binding (sdeop, elev, e7) is the identity used (Astra AR-01).
    iteration.MODEL_IDENTITY = lambda: model_binding()
    return iteration
