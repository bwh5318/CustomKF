"""General-arc station pilot with a per-epoch (streaming) Jacobian (roadmap steps 2-3).

For the six-hour case this reproduces, term by term, Astra's dated Pilot -> ArcPilot -> D0Pilot
objective: the same rows, sigmas, state mapping, wet basis (nodes every 18 ten-minute epochs, level
priors on the first two nodes, .03 m increments), orbit priors, clock elimination and D0 tangent
partials. Differences are structural only:
  * epochs are linearized one at a time into claude.roadmap.streaming.Accumulator, so there is no
    12,000-row / 900-column dense matrix and a long arc can be split across guarded workers;
  * the pilot's initial clock seeds, wind-up branches and ambiguity origins can be cached;
  * rotations/TDB are exactly memoized (CachedEpoch);
  * arcs of any length (step 600 s) and optional per-satellite nominal D0, unrestricted or
    prior-constrained force coefficients (D0 or all five ECOM terms).
No precise product is opened here.
"""
import math
import numpy as np
from customkf.nominal_navigation import NominalProducts
from customkf.network_square_root import Block, require_connected
from customkf.preprocess import C
from claude.tools.dated_observation import correction_difference, modeled_link, link_jacobian
from claude.tools.dated_d0 import d0_link_partial, SCALE
from claude.tools.force_parameter_fit import ForceTrajectory, INITIAL_P
from claude.roadmap.streaming import CachedEpoch

NODE_EPOCHS = 18
FORCE_NAMES = ("D0", "Y0", "B0", "Bc1", "Bs1")


class ColumnTangent:
    def __init__(self, base, satellite, column, delta):
        self.base, self.satellite, self.column, self.delta, self.epoch = base, satellite, column, delta, base.epoch

    def state(self, sat, t):
        state = self.base.state(sat, t)
        if sat == self.satellite:
            state = state+self.base.trajectories[sat].force_partial(t)[:, self.column]*SCALE*self.delta
        return state

    def clock(self, sat, t):
        return self.base.clock(sat, t)


def force_link_partial(products, row, receiver_cal, satellite_cal, ephemeris, rc, sc, wet, amb, windup, column):
    """Same construction as Astra's d0_link_partial, for any ECOM column."""
    if column == 0:
        return d0_link_partial(products, row, receiver_cal, satellite_cal, ephemeris, rc, sc, wet, amb, windup)
    def evaluate(p):
        return modeled_link(p, row, receiver_cal, satellite_cal, ephemeris, rc, sc, wet, amb, windup, details=True)
    g, base = evaluate(products)
    sat = row["satellite"]
    u = products.epoch.celestial_to_terrestrial(g["receive_s"]).T@g["los_ecef"]
    velocity = g["satellite_inertial"][3:]
    rate = products.clock_rate(sat, g["transmit_s"])
    sensitivity = products.trajectories[sat].force_partial(g["transmit_s"])[:3, column]*SCALE
    principal = (1+rate)*(u@sensitivity)/(1+u@velocity/C)
    h = .001
    # Domain-aware correction difference (Sol SOL-01 / Astra AF-02); bitwise as before wherever the step is valid.
    return principal+correction_difference(lambda delta: evaluate(ColumnTangent(products, sat, column, delta))[1],
                                           1., h, h/64, base)


def node_label(k):
    return {0: "0", 1: "1", 2: "6h"}.get(k, f"{3*k}h")


class LongPilot:
    def __init__(self, context, rows, seeds, *, nominal=None, estimate=(), prior_sigma=None, state=None):
        c = dict(context)
        if not isinstance(c["epoch"], CachedEpoch):
            c["epoch"] = CachedEpoch(c["epoch"])
        if c["step_s"] != 600:
            raise ValueError("Ten-minute cadence only")
        self.context, self.rows, self.seeds = c, rows, seeds
        self.duration, self.epoch_count = c["duration_s"], c["epoch_count"]
        self.sats, self.stations = sorted(seeds), sorted(c["stations"])
        self.nominal = {s: -1e-7 for s in self.sats} if nominal is None else {str(k): float(v) for k, v in nominal.items()}
        if set(self.sats)-set(self.nominal):
            raise ValueError("Missing nominal D0")
        self.estimate = tuple(int(k) for k in estimate)
        self.prior = {int(k): float(v) for k, v in (prior_sigma or {}).items()}
        if set(self.prior)-set(self.estimate):
            raise ValueError("Prior for a coefficient that is not estimated")
        counts = {}
        for r in rows:
            counts[r["arc"]] = counts.get(r["arc"], 0)+1
        self.arcs = sorted(a for a, n in counts.items() if n >= 3)
        self.arcset = set(self.arcs)
        self.by_epoch = [[] for _ in range(self.epoch_count)]
        for i, r in enumerate(rows):
            self.by_epoch[r["epoch"]].append(i)
        self.nodes = max(2, math.ceil((self.epoch_count-1)/NODE_EPOCHS))
        names = [f"orbit:{s}:{k}" for s in self.sats for k in range(6)]
        names += [f"wet:{s}:{k}" for s in self.stations for k in range(2)]
        names += ["amb:"+a for a in self.arcs]
        names += [f"wet:{s}:{node_label(k)}" for k in range(2, self.nodes+1) for s in self.stations]
        names += [f"srp{FORCE_NAMES[k]}:{s}" for s in self.sats for k in self.estimate]
        self.n = len(names)
        self.local_names = []
        for ei in range(self.epoch_count):
            selected = [rows[i] for i in self.by_epoch[ei]]
            require_connected([(r["station"], r["satellite"]) for r in selected], "BRUX")
            local = [f"clock:{ei}:R:{s}" for s in sorted({r["station"] for r in selected}) if s != "BRUX"]
            local += [f"clock:{ei}:S:{s}" for s in sorted({r["satellite"] for r in selected})]
            self.local_names.append(local)
            names.extend(local)
        self.names = names
        self.index = {name: k for k, name in enumerate(names)}
        self.wet = {s: [self.index[f"wet:{s}:{node_label(k)}"] for k in range(self.nodes+1)] for s in self.stations}
        self.level_sigma = np.array([1000. if k < 3 else 1. for s in self.sats for k in range(6)]+[.3]*(2*len(self.stations)))
        if state is None:
            state = self.initial_state()
        self.clock_seeds = {tuple(k): v for k, v in state["clock_seeds"]}
        self.windup = list(state["windup"])
        self.amb_origins = dict(state["amb_origins"])

    # ----- construction -------------------------------------------------------------------------
    def products(self, x):
        trajectories = {}
        for sat in self.sats:
            k = self.index[f"orbit:{sat}:0"]
            p = INITIAL_P.copy()
            p[0] = self.nominal[sat]
            for column in self.estimate:
                j = self.index.get(f"srp{FORCE_NAMES[column]}:{sat}")
                if j is not None:
                    p[column] += SCALE*x[j]
            trajectories[sat] = ForceTrajectory(self.seeds[sat]+x[k:k+6], self.context["model"], self.duration, p)
        c = self.context
        return NominalProducts(c["epoch"], c["origin_ns"], c["records"], trajectories, available_before_ns=c["navigation_cutoff_ns"])

    def link(self, products, row, rc, sc, wet, ambiguity, reference):
        c = self.context
        antenna = c["stations"][row["station"]]["header"]["antenna"]
        return modeled_link(products, row, c["rx_cal"][antenna], c["sat_cal"][row["satellite"]], c["ephemeris"], rc, sc, wet, ambiguity, reference)

    def initial_state(self):
        """Pilot's clock seeds, wind-up branches and ambiguity origins at x=0 (same order and rules).

        A station with no rows at an epoch gets no clock seed (defect fix, 1 Oct 2026; checkpoint-A Q7). Before, the
        median of an empty list put a NaN seed in the state, which no measurement reads: parameters and `state_for`
        exist only for stations present at the epoch, and `__init__` still refuses an epoch whose network is not
        connected to BRUX. Every used seed, wind-up and origin is computed exactly as before.
        """
        products = self.products(np.zeros(len(self.names)))
        seeds = []
        for ei in range(self.epoch_count):
            for station in self.stations:
                selected = [self.rows[i] for i in self.by_epoch[ei] if self.rows[i]["station"] == station]
                if not selected:
                    continue
                value = float(np.median([r["observation"][0]-self.link(products, r, 0., 0., 0., 0., None)[0][0] for r in selected]))
                seeds.append(((ei, station), value))
        clock = dict(seeds)
        previous, windup, origins = {}, [None]*len(self.rows), {}
        for i in sorted(range(len(self.rows)), key=lambda i: self.rows[i]["time_s"]):
            row = self.rows[i]
            out, _, phase, _ = self.link(products, row, clock[row["epoch"], row["station"]], 0., 0., 0., previous.get(row["arc"]))
            previous[row["arc"]] = phase
            windup[i] = phase
            origins.setdefault(row["arc"], float((row["observation"][1]-row["observation"][0])-(out[1]-out[0])))
        return dict(clock_seeds=seeds, windup=windup, amb_origins=origins)

    def state_record(self):
        """The state as strict JSON values: a non-finite seed, wind-up or origin is refused (checkpoint-A Q7)."""
        values = [*self.clock_seeds.values(), *self.windup, *self.amb_origins.values()]
        if not all(isinstance(v, float) and math.isfinite(v) for v in values):
            raise ValueError("Non-finite or non-float value in the pilot state")
        return dict(clock_seeds=[[list(k), v] for k, v in self.clock_seeds.items()], windup=self.windup, amb_origins=self.amb_origins)

    # ----- model --------------------------------------------------------------------------------
    def wet_weights(self, epoch):
        q = epoch/NODE_EPOCHS
        left = min(int(q), self.nodes-1)
        if not 0 <= q <= self.nodes:
            raise ValueError("Outside wet-node span")
        if self.nodes == 2:
            w = np.zeros(3)
            w[left] = 1-(q-left)
            w[left+1] = q-left
            return [0, 1, 2], w
        return [left, left+1], np.array([1-(q-left), q-left])

    def state_for(self, x, row):
        ei, station, sat = row["epoch"], row["station"], row["satellite"]
        rc = self.clock_seeds[ei, station]+(x[self.index[f"clock:{ei}:R:{station}"]] if station != "BRUX" else 0.)
        sc = x[self.index[f"clock:{ei}:S:{sat}"]]
        nodes, w = self.wet_weights(ei)
        wet = w@x[[self.wet[station][k] for k in nodes]]
        amb = self.amb_origins[row["arc"]]+(x[self.index["amb:"+row["arc"]]] if row["arc"] in self.arcset else 0.)
        return rc, sc, wet, amb

    def epoch_block(self, x, ei, products, jacobian=True):
        c = self.context
        local_index = {name: k for k, name in enumerate(self.local_names[ei])}
        gs, ls, ys, ss = [], [], [], []
        nodes, weights = self.wet_weights(ei)
        f = ei/(self.epoch_count-1)
        for i in self.by_epoch[ei]:
            row = self.rows[i]
            rc, sc, wet, amb = self.state_for(x, row)
            out, mw, _, elevation = self.link(products, row, rc, sc, wet, amb, self.windup[i])
            if elevation <= 0:
                raise ValueError("Trial moved retained observation below horizon")
            if jacobian:
                antenna = c["stations"][row["station"]]["header"]["antenna"]
                cal = (c["rx_cal"][antenna], c["sat_cal"][row["satellite"]], c["ephemeris"])
                orbit_j, clock_j = link_jacobian(products, row, *cal, rc, sc, wet, amb, self.windup[i])
                forces = [force_link_partial(products, row, *cal, rc, sc, wet, amb, self.windup[i], k) for k in self.estimate]
                # Pilot splits mw over two endpoint columns, ArcPilot sums them back: keep that arithmetic.
                mw_effective = mw*(1-f)+mw*f
            for kind in range(2 if row["arc"] in self.arcset else 1):
                ys.append(row["observation"][kind]-out[kind])
                ss.append(row["sigma"][kind])
                if jacobian:
                    g, l = np.zeros(self.n), np.zeros(len(local_index))
                    k = self.index[f"orbit:{row['satellite']}:0"]
                    g[k:k+6] = orbit_j[kind]
                    for node, w in zip(nodes, weights):
                        g[self.wet[row["station"]][node]] = mw_effective*w
                    if kind:
                        g[self.index["amb:"+row["arc"]]] = 1.
                    if row["station"] != "BRUX":
                        l[local_index[f"clock:{ei}:R:{row['station']}"]] = clock_j[kind]
                    l[local_index[f"clock:{ei}:S:{row['satellite']}"]] = -1.
                    for column, partial in zip(self.estimate, forces):
                        g[self.index[f"srp{FORCE_NAMES[column]}:{row['satellite']}"]] = partial[kind]
                    gs.append(g)
                    ls.append(l)
        block = Block(np.array(gs), np.array(ls), np.array(ys), np.array(ss)) if jacobian else None
        return block, ys, ss

    def constraints(self, x):
        n = self.n
        c = [np.eye(n)[:len(self.level_sigma)]]
        s = [self.level_sigma]
        for k in range(1, self.nodes+1):
            rows = np.zeros((len(self.stations), n))
            for i, station in enumerate(self.stations):
                rows[i, self.wet[station][k-1]] = -1.
                rows[i, self.wet[station][k]] = 1.
            c.append(rows)
            s.append(np.full(len(self.stations), .03))
        if self.prior:
            rows, sig = [], []
            for sat in self.sats:
                for column in self.estimate:
                    if column in self.prior:
                        r = np.zeros(n)
                        r[self.index[f"srp{FORCE_NAMES[column]}:{sat}"]] = 1.
                        rows.append(r)
                        sig.append(self.prior[column]/SCALE)
            c.append(np.array(rows))
            s.append(np.array(sig))
        c = np.vstack(c)
        s = np.concatenate(s)
        return c, -c@x[:n], s

    def evaluate(self, x, jacobian=True):
        """Compatibility form (all blocks in memory) for parity tests against the dated pilots."""
        products = self.products(x)
        blocks, residual, sigma = [], [], []
        for ei in range(self.epoch_count):
            block, ys, ss = self.epoch_block(x, ei, products, jacobian)
            if jacobian:
                blocks.append(block)
            residual += ys
            sigma += ss
        residual, sigma = np.array(residual), np.array(sigma)
        c, z, s = self.constraints(x)
        cost = float(np.sum((residual/sigma)**2)+np.sum((z/s)**2))
        return blocks, (c, z, s), residual, sigma, cost, products

    def cost(self, residual, sigma, x):
        c, z, s = self.constraints(x)
        return float(np.sum((residual/sigma)**2)+np.sum((z/s)**2))
