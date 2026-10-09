"""Guarded reference-only D0 calibration on a day before the evaluation days.

    fit:     python -m customkf.guard -- claude.roadmap.block_calibrate fit --day 2026-08-01 --satellites G01,G02
    combine: python -m customkf.guard -- claude.roadmap.block_calibrate combine --day 2026-08-01 --inputs DIR DIR

IGS positions are the *training data* here (a prior-day a priori model), never a station-POD seed
for an evaluation day. Uses Astra's claude.tools.force_parameter_fit.solve_force unchanged.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, DATA as DYN, sha
from customkf.sp3 import epoch_tag
from customkf.ephemeris import DE440
from customkf.frames import Environment
from customkf.orbit_forces import OrbitForceModel
from claude.tools.force_parameter_fit import solve_force
from claude.roadmap.common import DatedReference, satellite_blocks, block_group, write_json

DURATION = 21620.
TIMES = 10.+np.arange(25)*900.
TRAIN, HELD = np.arange(0, 25, 2), np.arange(1, 25, 2)
FLOOR = 3e-9


def rms(delta):
    return float(np.sqrt(np.mean(np.sum(np.asarray(delta)**2, axis=1))))


def fit(args, folder):
    date = datetime.strptime(args.day, "%Y-%m-%d")
    origin = epoch_tag(f"* {date.year} {date.month} {date.day} 11 59 50")
    reference = DatedReference(args.day, origin)
    ephemeris = DE440(DYN/"de440s.bsp")
    model = OrbitForceModel(Environment(reference.epoch, ephemeris, DURATION), DYN/"EGM2008_degree12.gfc")
    assert tuple(model.parameter_names) == ("D0", "Y0", "B0", "Bc1", "Bs1")
    rotations = np.array([reference.epoch.celestial_to_terrestrial(float(t)) for t in TIMES])
    results = {}
    for sat in args.satellites.split(","):
        samples = [reference.sample(sat, t) for t in TIMES]
        if any(s is None for s in samples):
            results[sat] = dict(status="invalid_reference_samples",
                                missing_times_s=[float(t) for t, s in zip(TIMES, samples) if s is None])
            print(sat, "invalid", flush=True)
            continue
        ecef = np.array([s.xyz_m for s in samples])
        inertial = np.einsum("tji,tj->ti", rotations, ecef)
        # The trajectory's initial state is at t=0 (origin 11:59:50 GPST), not at the first sample.
        initial = reference.precise.state(sat, 0.)
        entry = dict(status="ok", initial_state_source="IGS polynomial inertial state at t=0 s (origin)")
        for variant in ("fixed", "d0"):
            state, p, trajectory, history, cov = solve_force(initial, TIMES[TRAIN], inertial[TRAIN], model, DURATION, variant)
            states = np.array([trajectory.state(float(t))[:3] for t in TIMES])
            delta = states-inertial
            std = np.sqrt(np.diag(cov))
            corr = cov/std[:, None]/std[None, :]
            entry[variant] = dict(coefficients_mps2=p.tolist(), train_rms_3d_m=rms(delta[TRAIN]),
                                  held_rms_3d_m=rms(delta[HELD]), iterations=len(history),
                                  unit_weight_parameter_std=std.tolist(),
                                  max_abs_state_force_correlation=float(np.max(abs(corr[:6, 6:]))) if variant == "d0" else None)
        results[sat] = entry
        print(sat, "D0", entry["d0"]["coefficients_mps2"][0], "held", entry["d0"]["held_rms_3d_m"], flush=True)
    write_json(folder/"calibration_fits.json", dict(status="reference_d0_calibration_fits_not_POD", day=args.day,
        origin_ns=origin, times_s=TIMES, train_indices=TRAIN, held_indices=HELD, reference_sha256=reference.sha256,
        reference_path=reference.path.relative_to(ROOT).as_posix(), satellites=results))


def combine(args, folder):
    blocks = satellite_blocks(args.day)
    merged, inputs = {}, {}
    for directory in args.inputs:
        path = Path(directory)/"calibration_fits.json"
        data = json.loads(path.read_text())
        assert data["day"] == args.day
        inputs[path.relative_to(ROOT).as_posix()] = sha(path)
        for sat, entry in data["satellites"].items():
            assert sat not in merged, sat
            merged[sat] = entry
    groups = {}
    table = {}
    for sat in sorted(merged):
        block_type, svn = blocks[sat]
        group = block_group(block_type)
        entry = merged[sat]
        table[sat] = dict(block_type=block_type, svn=svn, group=group, status=entry["status"])
        if entry["status"] == "ok":
            d0 = entry["d0"]["coefficients_mps2"][0]
            table[sat].update(d0_mps2=d0, held_rms_fixed_m=entry["fixed"]["held_rms_3d_m"], held_rms_d0_m=entry["d0"]["held_rms_3d_m"])
            groups.setdefault(group, []).append(d0)
    stats = {g: dict(count=len(v), mean_mps2=float(np.mean(v)), sample_sd_mps2=float(np.std(v, ddof=1)) if len(v) > 1 else None)
             for g, v in sorted(groups.items())}
    dof = sum(len(v)-1 for v in groups.values())
    pooled = float(np.sqrt(sum(np.sum((np.array(v)-np.mean(v))**2) for v in groups.values())/dof))
    nominal = {}
    for sat, row in table.items():
        if row["group"] not in stats:
            raise ValueError("Block without a valid calibration satellite: "+row["group"])
        nominal[sat] = stats[row["group"]]["mean_mps2"]
    write_json(folder/"calibration.json", dict(status="frozen_block_d0_calibration", day=args.day,
        rule="block nominal = mean valid per-satellite reference D0; prior sigma = max(3e-9, pooled within-block sd)",
        blocks=stats, pooled_within_block_sd_mps2=pooled, prior_sigma_mps2=max(FLOOR, pooled),
        nominal_d0_mps2=nominal, satellites=table, input_fits_sha256=inputs))
    print(json.dumps(dict(blocks=stats, pooled=pooled, prior_sigma=max(FLOOR, pooled)), indent=2), flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fit", "combine"))
    parser.add_argument("--day", required=True)
    parser.add_argument("--satellites")
    parser.add_argument("--inputs", nargs="+")
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (fit if args.mode == "fit" else combine)(args, folder)


if __name__ == "__main__":
    main()
