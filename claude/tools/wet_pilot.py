"""Support-local hourly wet-delay extension of the pinned physical Pilot.

Keep original endpoint names/priors; append two interior retained parameters.
The inherited observation model is evaluated with the new wet interpolant.
Replace only its wet Jacobian columns and wet increment constraints afterwards.
No observation, clock, ambiguity, force or orbit-prior changes.
"""
import numpy as np
from customkf.stage5_pilot import Pilot


class WetPilot(Pilot):
    def __init__(self, context, rows, seeds, nodes=4):
        if nodes not in (2, 4):
            raise ValueError("Only predeclared two-node and hourly experiments")
        self.nodes = nodes
        super().__init__(context, rows, seeds)
        self.base_n = self.n
        if nodes == 4:
            extra = [f"wet:{s}:hour{k}" for s in self.stations for k in (1, 2)]
            self.names[self.n:self.n] = extra
            self.n += len(extra)
            self.index = {name: k for k, name in enumerate(self.names)}

    def wet_indices(self, station):
        suffixes = ("0", "1") if self.nodes == 2 else ("0", "hour1", "hour2", "1")
        return [self.index[f"wet:{station}:{k}"] for k in suffixes]

    def weights(self, epoch):
        q = epoch / (self.epoch_count - 1) * (self.nodes - 1)
        if not 0 <= q <= self.nodes - 1:
            raise ValueError("Wet interpolation outside arc")
        left = min(int(q), self.nodes - 2)
        weights = np.zeros(self.nodes)
        weights[left], weights[left + 1] = 1 - (q - left), q - left
        return weights

    def embed(self, saved):
        old_index = {str(name): i for i, name in enumerate(saved["names"])}
        x = np.zeros(len(self.names))
        for name, i in self.index.items():
            if name in old_index:
                x[i] = saved["x"][old_index[name]]
        if self.nodes == 4:
            for station in self.stations:
                indices = self.wet_indices(station)
                for k in (1, 2):
                    x[indices[k]] = (1 - k / 3) * x[indices[0]] + k / 3 * x[indices[-1]]
        return x

    def state_for(self, x, row):
        rc, sc, wet, amb = super().state_for(x, row)
        if self.nodes == 4:
            wet = self.weights(row["epoch"]) @ x[self.wet_indices(row["station"])]
        return rc, sc, wet, amb

    def evaluate(self, x, jacobian=True, observations=None):
        result = super().evaluate(x, jacobian, observations)
        if self.nodes == 2:
            return result
        blocks, old_constraints, residual, sigma, modeled, _, products = result
        for ei, block in enumerate(blocks):
            weights = self.weights(ei)
            for station in self.stations:
                indices = self.wet_indices(station)
                mapping = block.retained[:, indices[0]] + block.retained[:, indices[-1]]
                block.retained[:, indices] = mapping[:, None] * weights
        # Preserve the original independent endpoint-level and orbit priors.
        # Replace each old end-to-end difference by three independent increments.
        c, _, old_sigma = old_constraints
        count = len(self.stations)
        levels = c[:-count]
        differences = []
        for station in self.stations:
            indices = self.wet_indices(station)
            for a, b in zip(indices[:-1], indices[1:]):
                row = np.zeros(self.n)
                row[a], row[b] = -1., 1.
                differences.append(row)
        c = np.vstack([levels, differences])
        prior_sigma = np.r_[old_sigma[:-count], np.full(len(differences), .03 / np.sqrt(3))]
        target = -c @ x[:self.n]
        cost = float(np.sum((residual / sigma) ** 2) + np.sum((target / prior_sigma) ** 2))
        return blocks, (c, target, prior_sigma), residual, sigma, modeled, cost, products
