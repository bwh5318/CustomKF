"""Guarded single iteration of the fixed-data wet-basis experiment."""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore
from claude.tools import ablation_step as engine
from claude.tools.wet_pilot import WetPilot

BASE = ROOT / "validation/guam/20260911T155927Z"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, choices=(2, 4), required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    manifest = json.loads((BASE / "validation.json").read_text())
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    fixture = BASE / "prepare/fixture.json"
    baseline = BASE / manifest["final"] / "solution.npz"
    for path in (fixture, baseline):
        assert sha(path) == manifest["artifacts_sha256"][path.relative_to(BASE).as_posix()]
    spec = {"nodes": args.nodes, "orbit_prior_factor": 1., "level_priors": "original endpoints only, sigma 0.3 m",
            "increment_sigma_m": .03 / np.sqrt(args.nodes - 1), "fixture_sha256": sha(fixture),
            "baseline_sha256": sha(baseline), "sources": {f"claude/tools/{n}.py": sha(ROOT / f"claude/tools/{n}.py") for n in ("wet_step", "wet_pilot", "ablation_step")}}
    context, rows, seeds = restore(fixture)
    pilot = WetPilot(context, rows, seeds, nodes=args.nodes)
    if args.previous:
        assert json.loads((args.previous / "step.json").read_text())["experiment"] == spec
    else:
        args.previous = folder / "initial_parameters"
        args.previous.mkdir()
        initial = np.load(baseline)
        np.savez_compressed(args.previous / "solution.npz", x=pilot.embed(initial), names=np.array(pilot.names))
        (args.previous / "step.json").write_text(json.dumps({"status": "parameter_initialization_not_orbit_product", "history": [],
            "fixture_sha256": sha(fixture), "solution_sha256": sha(args.previous / "solution.npz")}) + "\n")
    engine.build_pilot = lambda path: pilot
    engine.iterate(argparse.Namespace(fixture=fixture, previous=args.previous), folder)
    step = json.loads((folder / "step.json").read_text())
    step["experiment"] = spec
    if args.nodes == 2:
        actual, expected = np.load(folder / "solution.npz"), np.load(baseline)
        for key in ("x", "names", "states", "times_s", "satellites", "residual_m", "sigma_m"):
            np.testing.assert_array_equal(actual[key], expected[key])
        np.testing.assert_allclose(actual["retained_covariance"], expected["retained_covariance"], rtol=1e-12, atol=1e-12)
        assert step["status"] == "converged" and not step["history"][-1]["update_applied"]
        step["baseline_reproduction"] = "bitwise arrays; covariance 1e-12"
    (folder / "step.json").write_text(json.dumps(step, indent=2) + "\n")


if __name__ == "__main__":
    main()
