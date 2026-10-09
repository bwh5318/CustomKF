"""Weak-orbit-prior preparation for the station-only D0 case (guarded; no SP3 reads).

Copies the pinned fixture and initial states of the completed nominal-prior D0
campaign, builds `WeakD0Pilot` (orbit prior sigmas x10, nothing else changed) and
writes a warm checkpoint holding the converged nominal-prior D0 solution.

The observation part of the objective cannot change, so the preparation proves it:
residuals and sigmas must reproduce bitwise, and the cost must move by exactly the
analytic orbit-prior term, `-(1 - 1/100) * sum((x_orbit/sigma_nominal)^2)`.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np

from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore
from customkf.prepare_stage2 import ROOT, sha
from customkf.reduced_network import MAX_ROWS, MAX_PARAMETERS, WORKSPACE_BYTES
from claude.tools.ablation_step import sources
from claude.tools.d0_weak_pilot import WeakD0Pilot, ORBIT_FACTOR

CAMPAIGN = ROOT/"claude/runs/20260912T145220Z-station-d0"
CASE = "station-d0-six-weak-orbit-prior"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare",))
    parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])

    manifest = json.loads((CAMPAIGN/"validation.json").read_text())
    if manifest["status"] != "station_d0_complete_not_accuracy_acceptance":
        raise ValueError("Nominal-prior campaign incomplete")
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT/name) == digest, name
    for rel in ("prepare/fixture.json", "prepare/initial.npz", "prepare/step.json",
                f"{manifest['final']}/solution.npz"):
        assert sha(CAMPAIGN/rel) == manifest["artifacts_sha256"][rel], rel
    nominal_meta = json.loads((CAMPAIGN/"prepare/step.json").read_text())
    final_step = json.loads((CAMPAIGN/manifest["final"]/"step.json").read_text())
    assert final_step["status"] == "converged"

    fixture = folder/"fixture.json"
    shutil.copyfile(CAMPAIGN/"prepare/fixture.json", fixture)
    shutil.copyfile(CAMPAIGN/"prepare/initial.npz", folder/"initial.npz")
    assert sha(fixture) == nominal_meta["fixture_sha256"], "copied fixture differs"

    pilot = WeakD0Pilot(*restore(fixture))
    previous = np.load(CAMPAIGN/manifest["final"]/"solution.npz")
    np.testing.assert_array_equal(previous["names"], np.array(pilot.names))
    x = previous["x"].copy()
    d0_columns = [pilot.index[f"srpD0:{s}"] for s in pilot.sats]

    rows = pilot.rows
    code = len(rows)
    phase = sum(r["arc"] in pilot.arcs for r in rows)
    priors = len(pilot.prior_sigma)+2*len(pilot.stations)
    m = code+phase+priors
    n = pilot.n
    local = sum(map(len, pilot.local_names))
    largest = max(sum(2 if r["arc"] in pilot.arcs else 1 for r in rows if r["epoch"] == ei)
                  for ei in range(pilot.epoch_count))
    workspace = 8*(5*m*n+4*largest**2+3*local*n+6*n*n)
    assert m <= MAX_ROWS and n <= MAX_PARAMETERS and workspace <= WORKSPACE_BYTES, (m, n, workspace/2**20)

    _, constraints, residual, sigma, _, cost, _ = pilot.evaluate(x, jacobian=False)
    assert not np.any(constraints[0][:, d0_columns]), "a prior row touches a D0 column"
    np.testing.assert_array_equal(residual, previous["residual_m"])
    np.testing.assert_array_equal(sigma, previous["sigma_m"])

    orbit = 6*len(pilot.sats)
    nominal_terms = float(np.sum(np.square(x[:orbit]/pilot.nominal_prior_sigma[:orbit])))
    expected = final_step["history"][-1]["cost_after"]-nominal_terms*(1-1/ORBIT_FACTOR**2)
    np.testing.assert_allclose(cost, expected, rtol=0, atol=1e-8)

    report = dict(status="prepared", case=CASE, weak_orbit_prior=True, source_sha256=sources(),
                  fixture_sha256=sha(fixture), nominal_campaign=str(CAMPAIGN),
                  nominal_fixture_sha256=nominal_meta["fixture_sha256"],
                  orbit_prior_factor=ORBIT_FACTOR,
                  declared_position_sigma_m=1000.*ORBIT_FACTOR, declared_velocity_sigma_mps=1.*ORBIT_FACTOR,
                  wet_priors_unchanged=True, d0_prior_absent=True,
                  code_rows=code, phase_rows=phase, prior_rows=priors, retained_parameters=n,
                  local_clock_parameters=local, workspace_estimate_mib=workspace/2**20, budget_pass=True,
                  warm_start_from=f"{manifest['final']}/solution.npz",
                  nominal_cost=final_step["history"][-1]["cost_after"], weak_cost=cost,
                  nominal_orbit_prior_terms=nominal_terms, expected_weak_cost=expected,
                  cost_difference_from_analytic=cost-expected,
                  observation_residuals_bitwise=True, embedded_baseline_bitwise=True,
                  precise_products_used=False, residual_rows=int(len(residual)),
                  protocol_sha256=sha(ROOT/"D0_POD_PROTOCOL.md"))
    (folder/"step.json").write_text(json.dumps(report, indent=2)+"\n")

    warm = folder/"warm"
    warm.mkdir()
    np.savez_compressed(warm/"solution.npz", x=x, names=np.array(pilot.names))
    (warm/"step.json").write_text(json.dumps(dict(fixture_sha256=sha(fixture),
                                                  solution_sha256=sha(warm/"solution.npz"),
                                                  history=[]), indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
