"""Claude ablation worker for Stage 5b (guarded; launched by claude.tools.run_ablation).

prepare: copy an archived Astra Stage 5b fixture, remove rows matching explicit
         STATION[:FIRST-LAST epoch] rules, and check that the Pilot builds.
iterate: one nonlinear iteration, identical in logic to customkf.stage5b_step
         (same model, weights, reduced QR, line search and stationary stop).
Reads Astra's archive and code read-only; writes only into the guard's run folder.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import warnings

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5b_step import restore, write_json
from customkf.stage5_pilot import Pilot, forbid_precise_product_reads
from customkf.reduced_network import reduced_qr
from customkf.nonlinear_stop import model_reduction, stationary

ARCHIVE = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"


def sources():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT / "customkf").glob("*.py"))}


def parse_rule(text):
    station, _, span = text.partition(":")
    if not station.isalnum():
        raise ValueError("Bad exclusion rule: " + text)
    if not span:
        return {"station": station, "epochs": None}
    lo, hi = (int(v) for v in span.split("-"))
    return {"station": station, "epochs": [lo, hi]}


def matches(row, rule):
    return row["station"] == rule["station"] and (
        rule["epochs"] is None or rule["epochs"][0] <= row["epoch"] <= rule["epochs"][1])


def build_pilot(path):
    context, rows, seeds = restore(path)
    with warnings.catch_warnings():
        # Pilot seeds a receiver clock for every station/epoch. An excluded window
        # leaves empty slices; their NaN seeds are never used by a retained row
        # (checked below).
        warnings.simplefilter("ignore", RuntimeWarning)
        pilot = Pilot(context, rows, seeds)
    for row in rows:
        if not np.isfinite(pilot.clock_seeds[row["epoch"], row["station"]]):
            raise ValueError("Non-finite clock seed used by a retained row")
    return pilot


def prepare(args, folder):
    source = ARCHIVE / f"{args.case}-prepare" / "fixture.json"
    obj = json.loads(source.read_text())
    if obj["case"] != args.case:
        raise ValueError("Archived fixture case mismatch")
    rules = [parse_rule(t) for t in args.exclude]
    kept, removed = [], {}
    for row in obj["rows"]:
        if any(matches(row, r) for r in rules):
            removed[row["station"]] = removed.get(row["station"], 0) + 1
        else:
            kept.append(row)
    if not removed:
        raise ValueError("Exclusion rules removed nothing")
    dropped = sorted(set(obj["context"]["stations"]) - {r["station"] for r in kept})
    if "BRUX" in dropped:
        raise ValueError("Cannot remove the BRUX clock datum")
    for station in dropped:
        obj["context"]["stations"].pop(station)
    obj["rows"] = kept
    obj["case"] = args.name
    obj["ablation"] = {"base_case": args.case, "rules": rules, "removed_links_by_station": removed,
                       "dropped_stations": dropped, "source_fixture": source.relative_to(ROOT).as_posix(),
                       "source_fixture_sha256": sha(source)}
    fixture = folder / "fixture.json"
    fixture.write_text(json.dumps(obj) + "\n")
    pilot = build_pilot(fixture)
    counts = {}
    for row in pilot.rows:
        counts[row["arc"]] = counts.get(row["arc"], 0) + 1
    report = {"status": "prepared", "case": args.name, "base_case": args.case, **obj["ablation"],
              "code_rows": len(pilot.rows), "phase_rows": sum(n for n in counts.values() if n >= 3),
              "retained_parameters": pilot.n, "local_clock_parameters": sum(map(len, pilot.local_names)),
              "satellites": pilot.sats, "fixture_sha256": sha(fixture), "source_sha256": sources()}
    write_json(folder / "step.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, indent=2), flush=True)


def iterate(args, folder):
    meta = json.loads((args.fixture.parent / "step.json").read_text())
    if meta["status"] != "prepared" or sha(args.fixture) != meta["fixture_sha256"]:
        raise ValueError("Changed or wrong fixture")
    if sources() != meta["source_sha256"]:
        raise ValueError("customkf source changed since preparation; stop rather than mix model versions")
    pilot = build_pilot(args.fixture)
    x = np.zeros(len(pilot.names))
    history = []
    if args.previous:
        prior = json.loads((args.previous / "step.json").read_text())
        if prior["fixture_sha256"] != meta["fixture_sha256"] or sha(args.previous / "solution.npz") != prior["solution_sha256"]:
            raise ValueError("Changed previous checkpoint")
        saved = np.load(args.previous / "solution.npz")
        np.testing.assert_array_equal(saved["names"], pilot.names)
        x = saved["x"].copy()
        history = prior["history"]
    begin = time.perf_counter()
    blocks, constraints, residual, sigma, _, cost, products = pilot.evaluate(x)
    print(f"Jacobian: {len(residual)} observations, retained {pilot.n}, total {len(pilot.names)}", flush=True)
    solution = reduced_qr(blocks, constraints)
    step = solution.estimate
    bound = max(np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]:pilot.index[f"orbit:{s}:0"] + 3])
                + pilot.duration * np.linalg.norm(step[pilot.index[f"orbit:{s}:0"] + 3:pilot.index[f"orbit:{s}:0"] + 6])
                for s in pilot.sats)
    reduction, dnorm = model_reduction(blocks, constraints, step)
    stopped = stationary(bound, cost, reduction, dnorm)
    accepted = False
    if stopped:
        alpha = 0.
        cost2 = cost
        r2 = residual
        accepted = True
    else:
        for alpha in (1., .5, .25, .125):
            trial = x + alpha * step
            _, _, r2, sigma, _, cost2, products = pilot.evaluate(trial, jacobian=False)
            if cost2 <= cost + max(1e-6, 1e-9 * cost):
                accepted = True
                x = trial
                break
    converged = stopped or (accepted and bound < .001 and abs(cost2 - cost) < max(1e-5, 1e-8 * cost))
    history.append({"iteration": len(history), "cost_before": cost, "cost_after": cost2, "accepted": accepted,
                    "update_applied": accepted and not stopped,
                    "termination": "small_step_and_linearized_progress" if stopped else "line_search",
                    "predicted_reduction": reduction, "whitened_direction_norm_squared": dnorm,
                    "step_fraction": alpha, "trajectory_step_bound_m": bound, "seconds": time.perf_counter() - begin})
    if not accepted:
        write_json(folder / "step.json", {"status": "no_accepted_step", "history": history})
        raise RuntimeError("No accepted nonlinear step; no solution checkpoint written")
    times = np.arange(10., pilot.duration - 9., 300.)
    np.savez_compressed(folder / "solution.npz", x=x, names=np.array(pilot.names),
                        states=np.array([[products.state(s, t) for t in times] for s in pilot.sats]),
                        satellites=np.array(pilot.sats), times_s=times, residual_m=r2, sigma_m=sigma,
                        retained_covariance=solution.retained_covariance)
    report = {"status": "converged" if converged else "iteration_complete", "case": meta["case"], "history": history,
              "fixture_sha256": meta["fixture_sha256"], "solution_sha256": sha(folder / "solution.npz"),
              "workspace_estimate_mib": solution.workspace_estimate_bytes / 2**20, "precise_products_used": False,
              "retained_covariance_at": "pre-step linearization; diagnostic only"}
    write_json(folder / "step.json", report)
    print(json.dumps(report, indent=2), flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard (via claude.tools.run_ablation)")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--case", choices=("eight-short", "eight-long", "expanded-long"), required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--exclude", action="append", required=True, help="STATION or STATION:FIRST-LAST (solve epochs)")
    i = sub.add_parser("iterate")
    i.add_argument("--fixture", type=Path, required=True)
    i.add_argument("--previous", type=Path)
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (prepare if args.mode == "prepare" else iterate)(args, folder)


if __name__ == "__main__":
    main()
