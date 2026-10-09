"""Station-only D0 pilot with tenfold weaker ORBIT priors and nothing else changed.

The handoff's step 4: 1000 m -> 10000 m position and 1 m/s -> 10 m/s velocity prior
sigmas, i.e. only the first 6*len(sats) entries of `prior_sigma`. Wet level and
increment priors, rows, sigmas, weights, ambiguities, clocks and the complete
absence of a D0 prior are untouched. The orbit prior centres stay the original
broadcast seeds (x = 0), exactly as in the earlier weak-prior stability work.

Root and pinned support scripts are unchanged; this subclass is the whole
adaptation, and `claude.tools.d0_weak_iteration` reuses Astra's iteration logic.
"""
import numpy as np

from claude.tools.d0_pilot import D0Pilot

ORBIT_FACTOR = 10.


class WeakD0Pilot(D0Pilot):
    def __init__(self, context, rows, seeds):
        super().__init__(context, rows, seeds)
        orbit = 6*len(self.sats)
        nominal = self.prior_sigma.copy()
        if len(nominal) != orbit+2*len(self.stations):
            raise ValueError("Unexpected prior block layout")
        weakened = nominal.copy()
        weakened[:orbit] *= ORBIT_FACTOR
        # Equivalent to the existing Pilot(prior_factor=10.) orbit sigmas, checked
        # rather than assumed, and with the wet block provably untouched.
        expected = np.array([ORBIT_FACTOR*(1000. if k < 3 else 1.) for _ in self.sats for k in range(6)])
        if not np.array_equal(weakened[:orbit], expected) or not np.array_equal(weakened[orbit:], nominal[orbit:]):
            raise ValueError("Weak prior construction changed something other than the orbit block")
        self.nominal_prior_sigma = nominal
        self.prior_sigma = weakened
