"""Exact trajectory cache for long arcs (roadmap step 3).

Step 2's profile showed trajectory re-integration dominating each worker (63 s of 74 s for six hours;
roughly four times that for 24 h), which cannot fit a 300 s worker once repeated in every chunk.
A dedicated guarded worker integrates a group of satellites at one linearization point with the
unchanged propagate() call, and saves the raw arrays that ForceTrajectory interpolates:

    times, states_m_mps (N,6), state_transition (N,6,6), parameter_sensitivity (N,6,5)

Loaded trajectories rebuild the identical CubicHermiteSpline objects from identical float64 arrays, so
every state, partial and force partial evaluates bitwise as a fresh integration would. Each file
records, per satellite, the SHA-256 of the initial state and force-parameter bytes; a loader refuses
any mismatch with the requesting linearization point.

Cache contract (review finding M10, 28 Sep 2026). The per-satellite key alone does not define a
trajectory, so `cached_products` also refuses a file whose recorded fixture/config differ from the
caller's, whose time grid is not exactly the 15 s integration grid over [0, pilot.duration] (checked on
the stored `times`, so older caches are checked too), and, when recorded, whose origin, duration or
integration settings differ. The caller's identity is the `fixture_sha256`/`config_sha256` keyword
arguments, else the same keys in the pilot context, which `long_iteration.build`/`mode_state` (and the
fork's `Opus_Fork.iteration`/`iteration7` copies) set from the paths they restored; a pilot restored
directly (reviews, experiments) carries no identity and keeps its own checks. The fixture hash binds the
origin, duration and dynamic-model input files (restore verifies them); model code is bound by the
controllers' source pins and, for fork variants, by their `force_model` record.

    python -m customkf.guard -- claude.roadmap.traj_cache integrate --fixture F --config C --state S \
        [--solution DIR | --linear DIR --alpha A] --group i --groups g
"""
import argparse
import dataclasses
import hashlib
import json
import math
import numbers
import os
from pathlib import Path
import sys
import time
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from customkf.prepare_stage2 import ROOT, sha
from customkf.propagation import propagate
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.dynamic_observation import SETTINGS
from customkf.nominal_navigation import NominalProducts
from claude.tools.force_parameter_fit import ForceTrajectory, INITIAL_P
from claude.tools.dated_d0 import SCALE
from claude.roadmap.long_pilot import FORCE_NAMES
from claude.roadmap.common import write_json


ACCEPTED_POINT = ("iteration_complete", "converged")


def accepted_point(folder, names, binding, *, force_model, alpha=None):
    """x (and history) of an accepted solution, or x + alpha*step of a linearized direction (Sol review SOL-05).

    Matching names alone are not enough: identical parameter names occur on other dates, seeds and states, where the
    same vector means something else. Required: an accepted status (iteration_complete/converged; `linearized` for a
    direction), the recorded file hash, the caller's fixture/config/state binding, the exact parameter names in
    order, and finite arrays of the right length. A rejected trial, a foreign point or a malformed file is refused.

    Completed 1 Oct 2026 (Astra AR-01):
    - every caller states the force-model identity it runs (`force_model`, keyword-only, no default). The folder's
      `force_model.json` must equal it; `None` declares the bare roadmap model, whose points carry no declaration;
    - the fixture/config/state identities must be non-empty strings on both sides;
    - a direction's alpha must be a finite real number and the combined point finite.
    """
    folder = Path(folder)
    if not all(isinstance(binding.get(k), str) and binding.get(k) for k in ("fixture", "config", "state")):
        raise ValueError(f"{folder.name}: the caller's fixture/config/state identity is incomplete")
    step = json.loads((folder/"step.json").read_text())
    direction = alpha is not None
    name, digest = ("direction.npz", "direction_sha256") if direction else ("solution.npz", "solution_sha256")
    if step.get("status") not in (("linearized",) if direction else ACCEPTED_POINT):
        raise ValueError(f"{folder.name}: status {step.get('status')!r} is not an accepted "
                         + ("direction" if direction else "point"))
    if sha(folder/name) != step.get(digest):
        raise ValueError(f"{folder.name}: {name} does not match its recorded hash")
    recorded = step.get("binding") or {}
    differs = [k for k in ("fixture", "config", "state") if recorded.get(k) != binding.get(k)]
    if differs:
        raise ValueError(f"{folder.name}: bound to a different {', '.join(differs)}")
    declared = folder/"force_model.json"
    if force_model is None:
        if declared.exists():
            raise ValueError(f"{folder.name}: declares a force model, but the caller runs the bare roadmap model")
    elif not declared.is_file():
        raise ValueError(f"{folder.name}: no force-model declaration")
    elif json.loads(declared.read_text()) != force_model:
        raise ValueError(f"{folder.name}: computed with a different force model")
    if direction and (isinstance(alpha, bool) or not isinstance(alpha, numbers.Real) or not math.isfinite(alpha)):
        raise ValueError(f"{folder.name}: step fraction {alpha!r} is not a finite number")
    with np.load(folder/name) as saved:
        if [str(n) for n in saved["names"]] != [str(n) for n in names]:
            raise ValueError(f"{folder.name}: parameter names or order differ")
        x = saved["x"].astype(float)
        step_vector = saved["step"].astype(float) if direction else None
    for label, vector in (("x", x), ("step", step_vector)):
        if vector is not None and (vector.shape != (len(names),) or not np.all(np.isfinite(vector))):
            raise ValueError(f"{folder.name}: {label} is not a finite vector of {len(names)} parameters")
    if direction:
        x = x+alpha*step_vector
        if not np.all(np.isfinite(x)):
            raise ValueError(f"{folder.name}: x + alpha*step is not finite")
    return x, step.get("history", [])


def initial_and_parameters(pilot, sat, x):
    """Exactly LongPilot.products' per-satellite inputs."""
    k = pilot.index[f"orbit:{sat}:0"]
    p = INITIAL_P.copy()
    p[0] = pilot.nominal[sat]
    for column in pilot.estimate:
        j = pilot.index.get(f"srp{FORCE_NAMES[column]}:{sat}")
        if j is not None:
            p[column] += SCALE*x[j]
    return pilot.seeds[sat]+x[k:k+6], p


def key(initial, p):
    return hashlib.sha256(np.ascontiguousarray(initial).tobytes()+np.ascontiguousarray(p).tobytes()).hexdigest()


GRID_STEP_S = 15.


def trajectory_grid(duration):
    """ForceTrajectory's output grid: every 15 s from 0, plus the arc end."""
    return np.r_[np.arange(0., duration, GRID_STEP_S), duration]


def integration(settings, model):
    """What propagate() receives besides the initial state and parameters: settings, model type/columns, grid step."""
    record = dict(settings=type(settings).__qualname__, **dataclasses.asdict(settings),
                  model=f"{type(model).__module__}.{type(model).__qualname__}",
                  parameters=list(getattr(model, "parameter_names", ())), grid_step_s=GRID_STEP_S)
    return dict(record, sha256=hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest())


def contract(pilot, times, settings):
    """Arc and integration identity recorded by the writer and checked by the loader (M10)."""
    return dict(origin_ns=int(pilot.context["origin_ns"]), duration_s=pilot.duration,
                grid=dict(start_s=float(times[0]), stop_s=float(times[-1]), count=len(times), step_s=GRID_STEP_S),
                integration=integration(settings, pilot.context["model"]))


class LoadedTrajectory(ForceTrajectory):
    def __init__(self, times, states, stm, sensitivity, duration):
        self.position = CubicHermiteSpline(times, states[:, :3], states[:, 3:], extrapolate=False)
        self.phi = CubicHermiteSpline(times, stm[:, :3], stm[:, 3:], extrapolate=False)
        self.sensitivity = CubicHermiteSpline(times, sensitivity[:, :3], sensitivity[:, 3:], extrapolate=False)
        self.duration = duration


def cached_products(pilot, x, files, *, fixture_sha256=None, config_sha256=None, settings=None):
    """NominalProducts at x from cache files; every file must meet the contract (module docstring, M10).

    fixture_sha256/config_sha256 default to the pilot context's (set by the builders); settings to SETTINGS.
    """
    c = pilot.context
    caller = dict(fixture_sha256=fixture_sha256 or c.get("fixture_sha256"), config_sha256=config_sha256 or c.get("config_sha256"))
    grid = trajectory_grid(pilot.duration)
    trajectories = {}
    for path in files:
        meta = json.loads((Path(path).parent/"trajectories.json").read_text())
        for name, value in caller.items():
            if value is not None and meta.get(name) != value:
                raise ValueError(f"Trajectory cache {path} records {name} {meta.get(name)}, not the caller's {value}")
        if "origin_ns" in meta and (int(meta["origin_ns"]) != int(c["origin_ns"]) or float(meta["duration_s"]) != float(pilot.duration)):
            raise ValueError(f"Trajectory cache {path} is for origin {meta['origin_ns']} ns / {meta['duration_s']} s, "
                             f"not {c['origin_ns']} ns / {pilot.duration} s")
        if "integration" in meta and meta["integration"] != integration(SETTINGS if settings is None else settings, c["model"]):
            raise ValueError(f"Trajectory cache {path} was integrated with different settings or model: {meta['integration']}")
        if sha(path) != meta["cache_sha256"]:
            raise ValueError(f"Trajectory cache {path} does not match its recorded content hash")
        with np.load(path) as data:
            times = data["times"]
            if times.ndim != 1 or not len(times) or not times[0] <= 0 or not times[-1] >= pilot.duration:
                raise ValueError(f"Trajectory cache {path} covers {times[:1]}..{times[-1:]} s, not [0, {pilot.duration}] s")
            if not np.array_equal(times, grid):
                raise ValueError(f"Trajectory cache {path} time grid is not the {GRID_STEP_S:g} s integration grid of this arc")
            for sat in meta["satellites"]:
                if sat not in pilot.sats:
                    raise ValueError(f"Trajectory cache {path} holds {sat}, which the pilot does not estimate")
                initial, p = initial_and_parameters(pilot, sat, x)
                if meta["keys"][sat] != key(initial, p):
                    raise ValueError("Trajectory cache does not match the linearization point: "+sat)
                arrays = data[f"{sat}_states"], data[f"{sat}_stm"], data[f"{sat}_sensitivity"]
                if any(len(a) != len(times) for a in arrays):
                    raise ValueError(f"Trajectory cache {path} arrays for {sat} do not match its time grid")
                trajectories[sat] = LoadedTrajectory(times, *arrays, pilot.duration)
    if set(trajectories) != set(pilot.sats):
        raise ValueError("Trajectory cache is incomplete")
    return NominalProducts(c["epoch"], c["origin_ns"], c["records"], {s: trajectories[s] for s in pilot.sats},
                           available_before_ns=c["navigation_cutoff_ns"])


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("integrate",))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, help="omit for the x=0 point before the pilot state exists")
    parser.add_argument("--solution", type=Path)
    parser.add_argument("--linear", type=Path)
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--group", type=int, required=True)
    parser.add_argument("--groups", type=int, required=True)
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    from claude.roadmap.long_iteration import build, load_config
    from claude.tools.dated_fixture import restore
    from claude.roadmap.long_pilot import LongPilot
    args.previous = args.solution
    if args.state is None:
        # Integration needs only names, seeds and force configuration, not clock seeds or wind-up branches.
        assert args.solution is None and args.linear is None, "Only the x=0 point may be integrated without a state"
        context, rows, seeds = restore(args.fixture)
        _, nominal, estimate, prior = load_config(args)
        pilot = LongPilot(context, rows, seeds, nominal=nominal, estimate=estimate, prior_sigma=prior,
                          state=dict(clock_seeds=[], windup=[], amb_origins={}))
    else:
        pilot, _ = build(args)
    if args.linear is not None or args.solution is not None:
        identity = dict(fixture=sha(args.fixture), config=sha(args.config), state=sha(args.state))
        if args.linear is not None:
            x, _ = accepted_point(args.linear, pilot.names, identity, force_model=None, alpha=args.alpha)
        else:
            x, _ = accepted_point(args.solution, pilot.names, identity, force_model=None)
    else:
        x = np.zeros(len(pilot.names))
    group = pilot.sats[args.group::args.groups]
    times = trajectory_grid(pilot.duration)
    arrays, keys = dict(times=times), {}
    start = time.perf_counter()
    for sat in group:
        initial, p = initial_and_parameters(pilot, sat, x)
        result = propagate(initial, times, pilot.context["model"], p, settings=SETTINGS)
        arrays[f"{sat}_states"] = result.states_m_mps
        arrays[f"{sat}_stm"] = result.state_transition
        arrays[f"{sat}_sensitivity"] = result.parameter_sensitivity
        keys[sat] = key(initial, p)
        print(sat, round(time.perf_counter()-start, 1), flush=True)
    np.savez_compressed(folder/"trajectories.npz", **arrays)
    write_json(folder/"trajectories.json", dict(status="trajectory_cache", satellites=group, keys=keys, group=args.group, groups=args.groups,
               x_sha256=hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest(), seconds=time.perf_counter()-start,
               cache_sha256=sha(folder/"trajectories.npz"), fixture_sha256=sha(args.fixture), config_sha256=sha(args.config),
               **contract(pilot, times, SETTINGS)))


if __name__ == "__main__":
    main()
