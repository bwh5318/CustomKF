"""One-change sensitivity variants of the sub-daily-EOP fit (`Opus_Fork.sdeop`), installed per worker process.

Test: `results/SENSITIVITY_PROTOCOL.md`. Question: which observation-model channel drives the POD's remaining
day-repeating 0.16–0.37 ppb scale breathing (`STATION_TIDES_SCREEN.md`, `RESIDUAL_BINNING.md`)? Each variant is the
SD-3 fit, `erp+thrust+iiia2600+sdeop` on 2026-08-03, with exactly one change. Nothing on disk is edited.

- `nopcv`: satellite antenna phase-centre *variations* set to zero (the nadir-dependent satellite term). PCOs are kept.
  Done by zeroing each satellite `Calibration`'s NOAZI/azimuth tables in the restored context.
- `cut15`: elevation cutoff 15° instead of the fixture's 10°. Drops the rows listed in the pinned
  `experiments/sensitivity/drop_below15_aug03.json`, frozen from the converged SD-3 orbit before any sensitivity fit.
- `wet1h`: tropospheric wet-delay nodes every hour (`long_pilot.NODE_EPOCHS` 18 → 6). The node-to-node random-walk σ
  is scaled 0.03 m → 0.03·√(6/18) m, so the process noise per unit time is unchanged.

`install()` applies `sdeop.install()` (sub-daily EOP, ERP variant) and then the named change. It patches `restore`
in `claude.tools.dated_fixture`, `claude.roadmap.long_iteration` and `Opus_Fork.iteration`, so the trajectory-cache and
iteration workers see identical rows and parameter names. `binding()` = `sdeop.binding()` + the perturbation, this
file's hash and the drop list's hash.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
PERTURBATIONS = ("nopcv", "cut15", "wet1h")
VARIANTS = {f"erp+thrust+iiia2600+sdeop+{p}": p for p in PERTURBATIONS}
ENVIRONMENT = "OPUSFORK_SENS_VARIANT"
DROP_LIST = ("experiments/sensitivity/drop_below15_aug03.json",
             "6071005086d706fc5ee90fea8b672513f35f8da19f7cdf9ececa4f6e756cb77b")
WET_NODE_EPOCHS = 6
WET_SIGMA_FACTOR = float(np.sqrt(6/18))


def current():
    name = os.environ.get(ENVIRONMENT)
    if name not in VARIANTS:
        raise RuntimeError(f"{ENVIRONMENT} must name a declared sensitivity variant, got {name!r}")
    return name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding():
    from . import sdeop
    name = current()
    os.environ[sdeop.ENVIRONMENT] = "erp+thrust+iiia2600+sdeop"
    return dict(sdeop.binding(), variant=name, sensitivity=VARIANTS[name], sens_sha256=_sha(HERE/"sens.py"),
                drop_list_sha256=_sha(HERE/DROP_LIST[0]) if VARIANTS[name] == "cut15" else None)


def _drop_set():
    path = HERE/DROP_LIST[0]
    assert _sha(path) == DROP_LIST[1], "drop list changed"
    return {tuple(r) for r in json.loads(path.read_text())["rows"]}


def install():
    """Patch the running worker; returns `Opus_Fork.iteration` bound to the (possibly subclassed) ERP pilot."""
    from . import sdeop
    name = current()
    perturbation = VARIANTS[name]
    os.environ[sdeop.ENVIRONMENT] = "erp+thrust+iiia2600+sdeop"
    iteration = sdeop.install()
    from . import ngv_pilot, ngv_traj_cache
    ngv_pilot.model_binding = binding
    ngv_traj_cache.model_binding = binding
    from claude.tools import dated_fixture
    from claude.roadmap import long_iteration, long_pilot
    original = dated_fixture.restore

    if perturbation == "nopcv":
        def restore(path):
            context, rows, seeds = original(path)
            cals = {}
            for sat, cal in context["sat_cal"].items():
                cal = copy.deepcopy(cal)
                for data in cal.frequencies.values():
                    if data.get("noazi") is not None:
                        data["noazi"] = np.zeros_like(data["noazi"])
                    for az in list(data.get("azimuth") or {}):
                        data["azimuth"][az] = np.zeros_like(data["azimuth"][az])
                cals[sat] = cal
            context["sat_cal"] = cals
            return context, rows, seeds
    elif perturbation == "cut15":
        drop = _drop_set()

        def restore(path):
            context, rows, seeds = original(path)
            assert json.loads(Path(path).read_text())["context"]["day"] == "2026-08-03", "cut15 list is for Aug 3 only"
            kept = [r for r in rows if (int(r["epoch"]), r["station"], r["satellite"]) not in drop]
            assert len(rows)-len(kept) == len(drop), (len(rows), len(kept), len(drop))
            return context, kept, seeds
    else:  # wet1h
        restore = original
        long_pilot.NODE_EPOCHS = WET_NODE_EPOCHS

        class HourlyWetPilot(iteration.LongPilot):
            def constraints(self, x):
                c, z, s = super().constraints(x)
                s = np.array(s, dtype=float)
                start = len(self.level_sigma)
                s[start:start+self.nodes*len(self.stations)] *= WET_SIGMA_FACTOR
                return c, z, s
        iteration.LongPilot = HourlyWetPilot

    dated_fixture.restore = restore
    long_iteration.restore = restore
    iteration.restore = restore
    return iteration
