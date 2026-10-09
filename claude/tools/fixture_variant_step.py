"""Guarded fixture variants of the 14-station GUAM case, plus one nonlinear iteration each.

    customkf.guard --timeout 300 -- claude.tools.fixture_variant_step prepare --variant holdout-2h
    customkf.guard --timeout 300 -- claude.tools.fixture_variant_step iterate --fixture PREPARE/fixture.json [--previous ITERATION]

Variants, both pure fixture surgery on a copy of the archived GUAM fixture. The estimator, force
model, priors, clock datum, ambiguity handling and root sources are untouched.

holdout-2h  Keep only the first 24 of 37 solve epochs (12:00-13:55). The trajectory still spans the
            full three hours, so the withheld hour is scored as prediction. Caveat: the two wet
            endpoints then span two hours instead of three, so this is not a pure data-volume change.
phase-weight Replace the phase sigma model 9 mm / sin(elevation) by sqrt(a^2 + b^2/sin^2 elevation),
            with a and b fitted by least squares to THIS arc's baseline phase residuals. That is
            in-sample and disclosed; the constants never see an IGS score. Code sigmas unchanged.

Iteration reuses the already tested engine in claude/tools/ablation_step.py, identical in logic to
customkf.stage5b_step. Writes only into the guarded run directory.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.stage5_pilot import forbid_precise_product_reads
from claude.tools import ablation_step as engine
from claude.tools.pinned_sources import GUAM, sha, verify
from claude.tools.yell_continuation_review import labelled

HELPERS = ("claude/tools/evaluate_ablation.py",)
KEPT_EPOCHS = 24
SIGMA_FLOOR_M = .001


def baseline_fixture():
    manifest = json.loads((GUAM / "validation.json").read_text())
    path = GUAM / "prepare/fixture.json"
    solution = GUAM / manifest["final"] / "solution.npz"
    for item in (path, solution):
        assert sha(item) == manifest["artifacts_sha256"][item.relative_to(GUAM).as_posix()], item
    return json.loads(path.read_text()), np.load(solution), sha(path)


def phase_weight_constants(fixture, fit):
    """Least squares of squared baseline phase residuals on [1, 1/sin^2 elevation]."""
    labels = labelled(fixture)
    residual, sigma = fit["residual_m"], fit["sigma_m"]
    assert len(labels) == len(residual)
    np.testing.assert_allclose(sigma, [row["sigma"][kind] for row, kind in labels], rtol=1e-12, atol=0)
    rows = [(row, index) for index, (row, kind) in enumerate(labels) if kind == 1]
    inverse_sine_squared = np.array([(row["sigma"][0] / .9) ** 2 for row, _ in rows])
    squared = np.array([residual[index] ** 2 for _, index in rows])
    design = np.column_stack([np.ones(len(rows)), inverse_sine_squared])
    (level, slope), *_ = np.linalg.lstsq(design, squared, rcond=None)
    record = {"rows": len(rows), "unconstrained_level_m2": float(level), "unconstrained_slope_m2": float(slope)}
    if level < 0:
        slope = float(inverse_sine_squared @ squared / (inverse_sine_squared @ inverse_sine_squared))
        level = 0.
        record["fallback"] = "negative level; refitted through the origin"
    record.update(level_m2=float(level), slope_m2=float(slope),
                  zenith_sigma_mm=float(1e3 * np.sqrt(level + slope)), constant_sigma_mm=float(1e3 * np.sqrt(level)),
                  elevation_sigma_mm=float(1e3 * np.sqrt(slope)),
                  previous_model="0.009 m / sin(elevation)", new_model="sqrt(level + slope / sin^2(elevation))")
    return float(level), float(slope), record


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "iterate"))
    parser.add_argument("--variant", choices=("holdout-2h", "phase-weight"))
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    if args.mode == "iterate":
        engine.iterate(argparse.Namespace(fixture=args.fixture, previous=args.previous), folder)
        return
    policy = verify(HELPERS)
    fixture, fit, fixture_sha256 = baseline_fixture()
    detail = {"variant": args.variant, "baseline_fixture_sha256": fixture_sha256,
              "baseline_solution_sha256": sha(GUAM / json.loads((GUAM / "validation.json").read_text())["final"] / "solution.npz")}
    new = {"case": args.variant, "context": dict(fixture["context"]), "rows": fixture["rows"], "seeds": fixture["seeds"]}
    if args.variant == "holdout-2h":
        new["rows"] = [row for row in fixture["rows"] if row["epoch"] < KEPT_EPOCHS]
        new["context"]["epoch_count"] = KEPT_EPOCHS
        detail.update(kept_epochs=KEPT_EPOCHS, withheld_epochs=list(range(KEPT_EPOCHS, fixture["context"]["epoch_count"])),
                      kept_rows=len(new["rows"]), removed_rows=len(fixture["rows"]) - len(new["rows"]),
                      duration_s_unchanged=new["context"]["duration_s"],
                      wet_basis_note="two wet endpoints now span two hours instead of three")
    else:
        level, slope, record = phase_weight_constants(fixture, fit)
        floored = 0
        rows = []
        for row in fixture["rows"]:
            copy = dict(row)
            inverse_sine_squared = (row["sigma"][0] / .9) ** 2
            value = float(np.sqrt(level + slope * inverse_sine_squared))
            if value < SIGMA_FLOOR_M:
                value = SIGMA_FLOOR_M
                floored += 1
            copy["sigma"] = [row["sigma"][0], value]
            rows.append(copy)
        new["rows"] = rows
        ratios = [row["sigma"][1] / original["sigma"][1] for row, original in zip(rows, fixture["rows"])]
        detail.update(predeclared_constants=record, rows_at_sigma_floor=floored,
                      phase_sigma_ratio={"min": float(min(ratios)), "median": float(np.median(ratios)), "max": float(max(ratios))},
                      code_sigma_unchanged=True)
    target = folder / "fixture.json"
    target.write_text(json.dumps(new) + "\n")
    pilot = engine.build_pilot(target)
    counts = {}
    for row in pilot.rows:
        counts[row["arc"]] = counts.get(row["arc"], 0) + 1
    report = {"status": "prepared", "case": args.variant, "variant_detail": detail, "source_policy": policy,
              "code_rows": len(pilot.rows), "phase_rows": sum(1 for n in counts.values() if n >= 3),
              "retained_parameters": pilot.n, "local_clock_parameters": sum(map(len, pilot.local_names)),
              "satellites": pilot.sats, "epoch_count": pilot.epoch_count, "duration_s": pilot.duration,
              "fixture_sha256": sha(target), "source_sha256": engine.sources(), "worker_sha256": sha(Path(__file__))}
    engine.write_json(folder / "step.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_sha256", "satellites", "source_policy")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
