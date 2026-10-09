"""LongPilot.initial_state omits clock seeds for empty (epoch, station) pairs (checkpoint-A Q7 defect fix).

    C:\\anaconda\\python.exe -m unittest tests.test_empty_epoch_state -v

Synthetic stub only (the pattern of claude/reviews/opus_cross_date_observation_audit/check_empty_epoch_state.py): the
attributes initial_state reads, with a deterministic row-dependent link and no physics. The real-data parity (saved
campaign states) is docs/consolidation/evidence/empty_epoch_parity.py, run under the root guard.
"""
import json
import math
import unittest
import warnings

import numpy as np

from customkf.network_square_root import require_connected
from claude.roadmap.long_pilot import LongPilot


class Stub:
    stations = ["BRUX", "KIT3", "VACS"]
    epoch_count = 3
    names = []

    def __init__(self, gaps=()):
        self.rows = [dict(epoch=e, station=s, satellite=g, time_s=10+600*e+k, arc=f"{s}:{g}:0",
                          observation=np.array([2.+e+.1*k, 3.+e]))
                     for e in range(self.epoch_count) for s in self.stations for k, g in enumerate(("G01", "G02"))
                     if (e, s) not in gaps]
        self.by_epoch = [[i for i, r in enumerate(self.rows) if r["epoch"] == e] for e in range(self.epoch_count)]

    def products(self, x):
        return None

    def link(self, products, row, rc, sc, wet, amb, reference):
        base = 1.+.25*row["epoch"]+.5*self.stations.index(row["station"])+.0625*int(row["satellite"][1:])+rc/1e3
        return np.array([base, base+.125]), None, base/8.+(0. if reference is None else 1e-3), None


def former_initial_state(self):
    """LongPilot.initial_state before the fix, verbatim apart from the name."""
    products = self.products(np.zeros(len(self.names)))
    seeds = []
    for ei in range(self.epoch_count):
        for station in self.stations:
            selected = [self.rows[i] for i in self.by_epoch[ei] if self.rows[i]["station"] == station]
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


def former(stub):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # numpy: mean of an empty slice
        return former_initial_state(stub)


class Recorded:
    """state_record() on a stub state."""
    def __init__(self, state):
        self.clock_seeds = {tuple(k): v for k, v in state["clock_seeds"]}
        self.windup = list(state["windup"])
        self.amb_origins = dict(state["amb_origins"])


class EmptyEpochState(unittest.TestCase):
    def test_complete_data_is_unchanged(self):
        self.assertEqual(LongPilot.initial_state(Stub()), former(Stub()))

    def test_empty_pairs_are_omitted_and_used_values_are_bitwise_the_former_ones(self):
        gaps = {(1, "KIT3"), (2, "VACS")}
        old, new = former(Stub(gaps)), LongPilot.initial_state(Stub(gaps))
        nonfinite = [k for k, v in old["clock_seeds"] if not math.isfinite(v)]
        self.assertEqual(sorted(nonfinite), sorted(gaps))
        self.assertEqual(new["clock_seeds"], [(k, v) for k, v in old["clock_seeds"] if math.isfinite(v)])
        self.assertEqual(new["windup"], old["windup"])
        self.assertEqual(new["amb_origins"], old["amb_origins"])
        used = {(r["epoch"], r["station"]) for r in Stub(gaps).rows}
        self.assertEqual({k for k, _ in new["clock_seeds"]}, used)
        json.dumps(new, allow_nan=False)
        with self.assertRaises(ValueError):
            json.dumps(old, allow_nan=False)

    def test_state_record_refuses_non_finite_values(self):
        state = LongPilot.initial_state(Stub({(1, "KIT3")}))
        record = LongPilot.state_record(Recorded(state))
        json.dumps(record, allow_nan=False)
        for bad in (float("nan"), float("inf")):
            for part in ("clock_seeds", "windup", "amb_origins"):
                with self.subTest(part=part, value=bad):
                    broken = Recorded(state)
                    if part == "clock_seeds":
                        broken.clock_seeds[0, "BRUX"] = bad
                    elif part == "windup":
                        broken.windup[0] = bad
                    else:
                        broken.amb_origins[next(iter(broken.amb_origins))] = bad
                    with self.assertRaisesRegex(ValueError, "Non-finite"):
                        LongPilot.state_record(broken)
        broken = Recorded(state)
        broken.windup[0] = None
        with self.assertRaisesRegex(ValueError, "non-float"):
            LongPilot.state_record(broken)

    def test_former_nan_state_would_now_be_refused_on_write(self):
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            LongPilot.state_record(Recorded(former(Stub({(1, "KIT3")}))))

    def test_disconnected_or_reference_less_epochs_are_still_refused(self):
        """__init__ calls require_connected per epoch before initial_state; that refusal is unchanged."""
        for edges in ([("KIT3", "G01"), ("VACS", "G01")], [("BRUX", "G01"), ("KIT3", "G02")]):
            with self.assertRaises(ValueError):
                require_connected(edges, "BRUX")
        require_connected([("BRUX", "G01"), ("KIT3", "G01")], "BRUX")


if __name__ == "__main__":
    unittest.main()
