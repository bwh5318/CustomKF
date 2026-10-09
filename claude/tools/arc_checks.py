"""Guarded arc-model checks: original oracle, wet priors and actual link partials."""
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore
from customkf.reduced_network import budget
from claude.tools.arc_pilot import ArcPilot
from claude.tools.arc_step import BASE


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    fixture = Path(sys.argv[1])
    pilot = ArcPilot(*restore(fixture))
    report = {}
    if not pilot.extended:
        baseline = np.load(BASE / "iteration-1/solution.npz")
        np.testing.assert_array_equal(pilot.names, baseline["names"])
        blocks, constraints, residual, sigma, _, cost, products = pilot.evaluate(baseline["x"])
        np.testing.assert_array_equal(residual, baseline["residual_m"])
        np.testing.assert_array_equal(sigma, baseline["sigma_m"])
        oldcost = json.loads((BASE / "iteration-1/step.json").read_text())["history"][-1]["cost_after"]
        np.testing.assert_allclose(cost, oldcost, rtol=0, atol=1e-10)
        states = np.array([[products.state(str(s), float(t)) for t in baseline["times_s"]] for s in baseline["satellites"]])
        np.testing.assert_array_equal(states, baseline["states"])
        report.update(oracle_residuals_sigmas_states_bitwise_identical=True, cost_difference=cost-oldcost)
    else:
        x = np.zeros(len(pilot.names))
        for station in pilot.stations:
            x[pilot.wet_indices(station)] = [.1, -.05, .07]
        blocks, constraints, residual, sigma, _, cost, products = pilot.evaluate(x)
        c, z, s = constraints
        old = np.vstack([np.eye(2)/.3, np.array([[-1., 1.]])/.03])
        _, r = np.linalg.qr(old, mode="reduced")
        inv = np.linalg.solve(r, np.eye(2)); oldcov = inv@inv.T
        for station in pilot.stations:
            a = c[:, pilot.wet_indices(station)]/s[:, None]
            a = a[np.any(a != 0, axis=1)]
            _, r = np.linalg.qr(a, mode="reduced")
            inv = np.linalg.solve(r, np.eye(3)); cov = inv@inv.T
            np.testing.assert_allclose(cov[:2, :2], oldcov, rtol=1e-12, atol=1e-14)
            for endpoints in ((.1, -.05), (.3, .3), (0., .01)):
                np.testing.assert_allclose(np.linalg.norm(a@[*endpoints, endpoints[-1]])**2,
                                           np.linalg.norm(old@endpoints)**2, rtol=1e-12)
        for ei in range(37):
            w = pilot.weights(ei)
            assert np.all(w >= 0) and abs(w.sum()-1) < 1e-14
            if ei <= 18:
                np.testing.assert_array_equal(w, [1-ei/18, ei/18, 0])
        maximum = 0.; checked = 0
        for ei in (0, 6, 12, 18, 24, 30, 36):
            seen = set(); offset = 0
            for row in (r for r in pilot.rows if r["epoch"] == ei):
                count = 2 if row["arc"] in pilot.arcs else 1
                if row["station"] not in seen:
                    seen.add(row["station"])
                    for index in pilot.wet_indices(row["station"]):
                        plus, minus = x.copy(), x.copy(); plus[index] += .001; minus[index] -= .001
                        yp = pilot.link(products, row, *pilot.state_for(plus,row), pilot.windup[id(row)])[0]
                        ym = pilot.link(products, row, *pilot.state_for(minus,row), pilot.windup[id(row)])[0]
                        finite = (np.asarray(yp)[:count]-np.asarray(ym)[:count])/.002
                        analytic = blocks[ei].retained[offset:offset+count,index]
                        maximum = max(maximum,float(np.max(abs(finite-analytic))))
                        np.testing.assert_allclose(finite,analytic,rtol=0,atol=2e-5); checked += count
                offset += count
            assert offset == len(blocks[ei].target)
        report.update(original_prior_marginal_pass=True, original_prefix_basis_pass=True,
                      finite_difference_entries=checked, finite_difference_max_error=maximum)
    dimensions = budget(blocks, constraints)
    report.update(status="arc_model_checks_pass", extended=pilot.extended,
                  retained_parameters=dimensions[0], rows_with_constraints=dimensions[1], workspace_mib=dimensions[3]/2**20)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"checks.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


if __name__ == "__main__": main()
