"""Station-only pilots with a per-satellite (block) nominal D0; no reference products.

BlockFixedPilot: Astra's dated ArcPilot with the fixed nominal D0 replaced by a per-satellite
value. With every value at -1e-7 its trajectories are produced by the same propagate() call as
the archived fixed arm, so the forward model must reproduce that archive exactly (parity gate).

BlockPriorPilot: Astra's dated D0Pilot (one D0 correction per satellite, scale 1e-7) centred on the
block nominal, plus one explicit prior equation per coefficient with a frozen sigma.
"""
import numpy as np
from customkf.nominal_navigation import NominalProducts
from claude.tools.dated_arc import ArcPilot
from claude.tools.dated_d0 import D0Pilot, SCALE
from claude.tools.force_parameter_fit import ForceTrajectory, INITIAL_P


def _products(pilot, x, estimated):
    trajectories = {}
    for sat in pilot.sats:
        k = pilot.index[f"orbit:{sat}:0"]
        p = INITIAL_P.copy()
        p[0] = pilot.nominal[sat]
        j = pilot.index.get(f"srpD0:{sat}") if estimated else None
        if j is not None:
            p[0] += SCALE*x[j]
        trajectories[sat] = ForceTrajectory(pilot.seeds[sat]+x[k:k+6], pilot.context["model"], pilot.duration, p)
    c = pilot.context
    return NominalProducts(c["epoch"], c["origin_ns"], c["records"], trajectories, available_before_ns=c["navigation_cutoff_ns"])


class BlockFixedPilot(ArcPilot):
    def __init__(self, context, rows, seeds, nominal):
        self.nominal = {str(s): float(v) for s, v in nominal.items()}
        missing = set(seeds)-set(self.nominal)
        if missing:
            raise ValueError("No nominal D0 for "+",".join(sorted(missing)))
        super().__init__(context, rows, seeds)
        assert self.extended and context["step_s"] == 600

    def products(self, x):
        return _products(self, x, False)


class BlockPriorPilot(D0Pilot):
    def __init__(self, context, rows, seeds, nominal, prior_sigma_mps2):
        self.nominal = {str(s): float(v) for s, v in nominal.items()}
        missing = set(seeds)-set(self.nominal)
        if missing:
            raise ValueError("No nominal D0 for "+",".join(sorted(missing)))
        if not 0 < prior_sigma_mps2 < 1e-7:
            raise ValueError("Implausible D0 prior sigma")
        self.prior_scaled = float(prior_sigma_mps2)/SCALE
        super().__init__(context, rows, seeds)

    def products(self, x):
        return _products(self, x, True)

    def evaluate(self, x, jacobian=True, observations=None):
        blocks, (c, z, s), residual, sigma, modeled, _, products = super().evaluate(x, jacobian, observations)
        rows = np.zeros((len(self.sats), self.n))
        for i, sat in enumerate(self.sats):
            rows[i, self.index[f"srpD0:{sat}"]] = 1.
        c = np.vstack([c, rows])
        z = np.r_[z, -rows@x[:self.n]]
        s = np.r_[s, np.full(len(self.sats), self.prior_scaled)]
        cost = float(np.sum((residual/sigma)**2)+np.sum((z/s)**2))
        return blocks, (c, z, s), residual, sigma, modeled, cost, products
