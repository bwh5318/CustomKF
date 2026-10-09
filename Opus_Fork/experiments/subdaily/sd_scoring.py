"""Score fits made with the IERS 2010 sub-daily EOP (`Opus_Fork.sdeop`) beside ordinary fits, IGS final and NGA.

`Opus_Fork.evaluate` and `Opus_Fork.dip_nga` compare in inertial axes: IGS and NGA (Earth-fixed products) are
rotated with the plain daily EOP, and a fit's inertial states are used as they are. That is right for a fit made
with the plain EOP: its Earth-fixed product is R_plain(t)·r. A fit made with sub-daily EOP publishes
R_sd(t)·r. To score that product on the same footing, this hook presents such a fit's positions as
R_plain(t)ᵀ·R_sd(t)·r. The comparison is then exactly "our Earth-fixed product against IGS final", for every arm.

A fit is treated as sub-daily only if its solution folder's `force_model.json` declares `subdaily_eop`; every
other arm (and IGS, NGA) is untouched. `install()` patches the `Fit` name in `Opus_Fork.evaluate` and
`Opus_Fork.dip_nga` in this process only.
"""
import json
from pathlib import Path
import numpy as np

from customkf.frames import FrameEpoch
from customkf.prepare_stage2 import DATA as DYN

from Opus_Fork import subdaily_eop
from Opus_Fork.baseline import Fit


class SubdailyFit:
    """A sub-daily-EOP fit presented in the plain-EOP inertial frame the evaluators use."""

    def __init__(self, inner, eop_plain):
        self.inner, self.declared, self.origin_ns = inner, inner.declared, inner.origin_ns
        self.plain = FrameEpoch(inner.origin_ns, eop_plain)
        self.subdaily = FrameEpoch(inner.origin_ns, subdaily_eop.earth_orientation_class()(DYN/"finals2000A.all"))
        self._maps = {}

    def keys(self):
        return self.inner.keys()

    def _map(self, t):
        if t not in self._maps:
            self._maps[t] = self.plain.celestial_to_terrestrial(t).T@self.subdaily.celestial_to_terrestrial(t)
        return self._maps[t]

    def position(self, sat, t):
        return self._map(t)@self.inner.position(sat, t)

    def rotation(self, t):
        return self.plain.celestial_to_terrestrial(t)


def fit_for(npz_path, fixture_path, eop):
    inner = Fit(npz_path, fixture_path, eop)
    model = Path(npz_path).parent/"force_model.json"
    if model.exists() and json.loads(model.read_text()).get("subdaily_eop"):
        return SubdailyFit(inner, eop)
    return inner


def install():
    subdaily_eop.verify_sources()
    subdaily_eop.self_test()
    from Opus_Fork import evaluate, dip_nga
    evaluate.Fit = fit_for
    dip_nga.Fit = fit_for
