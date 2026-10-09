"""Guarded hourly-basis prior equivalence, embedded-model and wet-partial checks."""
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore
from customkf.reduced_network import budget
from claude.tools.wet_pilot import WetPilot
from claude.tools.wet_step import BASE


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    # Endpoint marginal covariance via square-root factorization, no normal equations.
    a = np.vstack([np.eye(4)[[0, 3]] / .3, np.diff(np.eye(4), axis=0) / (.03 / np.sqrt(3))])
    q, r = np.linalg.qr(a, mode="reduced")
    inverse = np.linalg.solve(r, np.eye(4))
    cov = inverse @ inverse.T
    old = np.vstack([np.eye(2) / .3, np.array([[-1., 1.]]) / .03])
    _, ro = np.linalg.qr(old, mode="reduced")
    io = np.linalg.solve(ro, np.eye(2))
    np.testing.assert_allclose(cov[np.ix_([0, 3], [0, 3])], io @ io.T, rtol=1e-12, atol=1e-14)
    for endpoints in ((.12, -.09), (.3, .3), (0., .01)):
        linear = np.linspace(*endpoints, 4)
        np.testing.assert_allclose(np.linalg.norm(a @ linear)**2, np.linalg.norm(old @ endpoints)**2, rtol=1e-13)
    context, rows, seeds = restore(BASE / "prepare/fixture.json")
    assert context["epoch_count"] == 37 and context["step_s"] == 300
    pilot = WetPilot(context, rows, seeds, nodes=4)
    baseline = np.load(BASE / "iteration-1/solution.npz")
    x = pilot.embed(baseline)
    for ei in range(37):
        w = pilot.weights(ei)
        assert np.all(w >= 0) and abs(sum(w) - 1) < 1e-14
        np.testing.assert_allclose(w @ np.linspace(-.2, .1, 4), -.2 + .3 * ei / 36, atol=1e-15)
    blocks, constraints, residual, sigma, _, cost, products = pilot.evaluate(x)
    dimensions = budget(blocks, constraints)
    np.testing.assert_array_equal(sigma, baseline["sigma_m"])
    np.testing.assert_allclose(residual, baseline["residual_m"], rtol=0, atol=5e-8)
    original_cost = json.loads((BASE / "iteration-1/step.json").read_text())["history"][-1]["cost_after"]
    np.testing.assert_allclose(cost, original_cost, rtol=0, atol=2e-5)
    maximum = 0.
    checked = 0
    # Finite differences of the actual link model, checking assembled Jacobian
    # columns at all knots and intervening half-hours, for every viewing station.
    for ei in (0, 6, 12, 18, 24, 30, 36):
        seen = set()
        offset = 0
        for row in (r for r in rows if r["epoch"] == ei):
            count = 2 if row["arc"] in pilot.arcs else 1
            if row["station"] not in seen:
                seen.add(row["station"])
                for index in pilot.wet_indices(row["station"]):
                    plus, minus = x.copy(), x.copy()
                    plus[index] += .001
                    minus[index] -= .001
                    yp = pilot.link(products, row, *pilot.state_for(plus, row), pilot.windup[id(row)])[0]
                    ym = pilot.link(products, row, *pilot.state_for(minus, row), pilot.windup[id(row)])[0]
                    finite = (np.asarray(yp)[:count] - np.asarray(ym)[:count]) / .002
                    analytic = blocks[ei].retained[offset:offset + count, index]
                    maximum = max(maximum, float(np.max(abs(finite - analytic))))
                    np.testing.assert_allclose(finite, analytic, rtol=0, atol=2e-5)
                    checked += count
            offset += count
        assert offset == len(blocks[ei].target)
    report = {"status": "wet_basis_checks_pass", "endpoint_prior_marginal_covariance_pass": True,
              "linear_embedding_prior_energy_pass": True, "partition_and_linear_reproduction_pass": True,
              "embedded_model_max_residual_difference_m": float(np.max(abs(residual - baseline["residual_m"]))),
              "embedded_cost_difference": cost - original_cost, "finite_difference_entries": checked,
              "finite_difference_max_error": maximum, "retained_parameters": dimensions[0],
              "rows_with_constraints": dimensions[1], "local_parameters": dimensions[2],
              "workspace_mib": dimensions[3] / 2**20, "baseline_sha256": sha(BASE / "iteration-1/solution.npz")}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
