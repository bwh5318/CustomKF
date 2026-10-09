"""Guarded split iteration for the block-D0 arms (mirrors claude.tools.dated_iteration).

    parity: python -m customkf.guard -- claude.roadmap.block_iteration parity --fixture F --archive DIR
    linear: ... linear --fixture F --variant block-fixed|block-prior --calibration C [--previous DIR]
    trial:  ... trial  --fixture F --variant ... --calibration C --linear DIR --alpha 1.0

Same objective, reduced QR, stationarity rule and line search as Astra's dated iteration.
No precise product may be opened (audit hook).
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.reduced_network import reduced_qr
from customkf.nonlinear_stop import model_reduction, stationary
from claude.tools.dated_fixture import restore
from claude.roadmap.block_pilots import BlockFixedPilot, BlockPriorPilot
from claude.roadmap.common import write_json


def build(args):
    context, rows, seeds = restore(args.fixture)
    calibration = json.loads(args.calibration.read_text())
    assert sha(args.calibration) == args.calibration_sha256 and calibration["status"] == "frozen_block_d0_calibration"
    nominal = calibration["nominal_d0_mps2"]
    if args.variant == "block-fixed":
        return BlockFixedPilot(context, rows, seeds, nominal)
    return BlockPriorPilot(context, rows, seeds, nominal, calibration["prior_sigma_mps2"])


def save_solution(folder, pilot, x, products, residual, sigma, cov, history, status, fixture_sha):
    times = np.arange(10., pilot.duration-9., 300.)
    np.savez_compressed(folder/"solution.npz", x=x, names=np.array(pilot.names),
                        states=np.array([[products.state(s, t) for t in times] for s in pilot.sats]),
                        satellites=np.array(pilot.sats), times_s=times, residual_m=residual, sigma_m=sigma,
                        retained_covariance=cov)
    report = dict(status=status, history=history, fixture_sha256=fixture_sha, solution_sha256=sha(folder/"solution.npz"),
                  precise_products_used=False, retained_covariance_at="pre-step linearization; diagnostic only")
    write_json(folder/"step.json", report)
    print(json.dumps(report, indent=2), flush=True)


def parity(args, folder):
    """Nominal -1e-7 everywhere must reproduce the archived fixed arm's forward model exactly."""
    context, rows, seeds = restore(args.fixture)
    pilot = BlockFixedPilot(context, rows, seeds, {s: -1e-7 for s in seeds})
    step = json.loads((args.archive/"step.json").read_text())
    assert sha(args.archive/"solution.npz") == step["solution_sha256"]
    with np.load(args.archive/"solution.npz") as z:
        np.testing.assert_array_equal(pilot.names, z["names"])
        _, _, residual, sigma, _, cost, products = pilot.evaluate(z["x"], jacobian=False)
        np.testing.assert_array_equal(residual, z["residual_m"])
        np.testing.assert_array_equal(sigma, z["sigma_m"])
        states = np.array([[products.state(s, t) for t in z["times_s"]] for s in pilot.sats])
        np.testing.assert_array_equal(states, z["states"])
    expected = step["history"][-1]["cost_after"]
    assert cost == expected, (cost, expected)
    write_json(folder/"parity.json", dict(status="block_fixed_forward_parity_bitwise_pass", residuals=len(residual),
        sampled_states=list(states.shape), cost=cost, archive=str(args.archive), fixture_sha256=sha(args.fixture)))
    print("Block-fixed pilot at nominal -1e-7 reproduces the archived fixed arm bitwise", flush=True)


def linear(args, folder, fixture_sha):
    pilot = build(args)
    x = np.zeros(len(pilot.names))
    history = []
    if args.previous:
        previous = json.loads((args.previous/"step.json").read_text())
        assert previous["fixture_sha256"] == fixture_sha and sha(args.previous/"solution.npz") == previous["solution_sha256"]
        saved = np.load(args.previous/"solution.npz")
        np.testing.assert_array_equal(saved["names"], pilot.names)
        x = saved["x"].copy()
        history = previous["history"]
    blocks, constraints, residual, sigma, _, cost, products = pilot.evaluate(x)
    print("Jacobian complete", flush=True)
    solution = reduced_qr(blocks, constraints)
    step = solution.estimate
    index = pilot.index
    bound = max(np.linalg.norm(step[index[f"orbit:{s}:0"]:index[f"orbit:{s}:0"]+3]) +
                pilot.duration*np.linalg.norm(step[index[f"orbit:{s}:0"]+3:index[f"orbit:{s}:0"]+6]) for s in pilot.sats)
    force_bound = 0.
    if args.variant == "block-prior":
        force_bound = max(np.linalg.norm(products.trajectories[s].partial(t)[:3]@step[index[f"orbit:{s}:0"]:index[f"orbit:{s}:0"]+6] +
                          products.trajectories[s].force_partial(t)[:3, 0]*1e-7*step[index[f"srpD0:{s}"]])
                          for s in pilot.sats for t in np.arange(10., pilot.duration-9., 300.))
    bound = max(float(bound), float(force_bound))
    reduction, dnorm = model_reduction(blocks, constraints, step)
    record = dict(iteration=len(history), cost_before=cost, predicted_reduction=reduction, whitened_direction_norm_squared=dnorm,
                  trajectory_step_bound_m=bound, force_inclusive_sampled_step_bound_m=float(force_bound))
    if stationary(bound, cost, reduction, dnorm):
        record.update(cost_after=cost, accepted=True, update_applied=False, termination="small_step_and_linearized_progress", step_fraction=0.)
        save_solution(folder, pilot, x, products, residual, sigma, solution.retained_covariance, history+[record], "converged", fixture_sha)
    else:
        np.savez_compressed(folder/"direction.npz", x=x, step=step, names=np.array(pilot.names), retained_covariance=solution.retained_covariance)
        report = dict(status="linearized", fixture_sha256=fixture_sha, direction_sha256=sha(folder/"direction.npz"),
                      history=history, record=record, workspace_estimate_mib=solution.workspace_estimate_bytes/2**20)
        write_json(folder/"step.json", report)
        print(json.dumps(report, indent=2), flush=True)


def trial(args, folder, fixture_sha):
    pilot = build(args)
    lin = json.loads((args.linear/"step.json").read_text())
    assert lin["status"] == "linearized" and lin["fixture_sha256"] == fixture_sha
    assert sha(args.linear/"direction.npz") == lin["direction_sha256"]
    saved = np.load(args.linear/"direction.npz")
    np.testing.assert_array_equal(saved["names"], pilot.names)
    x = saved["x"]+args.alpha*saved["step"]
    _, _, residual, sigma, _, cost, products = pilot.evaluate(x, jacobian=False)
    before = lin["record"]["cost_before"]
    accepted = cost <= before+max(1e-6, 1e-9*before)
    record = lin["record"] | dict(cost_after=cost, accepted=accepted, update_applied=accepted, termination="line_search", step_fraction=args.alpha)
    if accepted:
        save_solution(folder, pilot, x, products, residual, sigma, saved["retained_covariance"], lin["history"]+[record], "iteration_complete", fixture_sha)
    else:
        write_json(folder/"step.json", dict(status="trial_rejected", record=record))
        print("Trial rejected", flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("parity", "linear", "trial"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--fixture-sha256")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--variant", choices=("block-fixed", "block-prior"))
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--calibration-sha256")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--linear", type=Path)
    parser.add_argument("--alpha", type=float, choices=(1., .5, .25, .125))
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    sys.addaudithook(forbid_precise_product_reads)
    if args.mode == "parity":
        return parity(args, folder)
    fixture_sha = sha(args.fixture)
    assert fixture_sha == args.fixture_sha256, "Fixture changed"
    (linear if args.mode == "linear" else trial)(args, folder, fixture_sha)


if __name__ == "__main__":
    main()
