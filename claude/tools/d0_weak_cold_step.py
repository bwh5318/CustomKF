"""Cold start under the weak orbit priors (guarded; no SP3 reads).

The warm weak-prior run stopped at its first linearisation without taking a step,
because the nominal-prior solution is already stationary to within the solver's own
tolerance under the weakened priors. That makes the warm test degenerate: it shows
the solution does not move, but never re-derives it.

This preparation removes that degeneracy the same way the earlier prior-stability
work did (handoff: "if warm-start stability passes, a cold-start factor-10
confirmation is useful"). It combines the two controls already run separately:
orbit prior sigmas x10 *and* an entirely zero starting x. Wet priors, rows, sigmas,
weights, ambiguities, clocks and the absent D0 prior are unchanged, and the prior
centres remain the broadcast seeds.

At x = 0 every prior residual is exactly zero, so the starting cost cannot depend
on the prior sigmas at all: it must equal the archived nominal start cost bitwise.
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
from claude.tools.d0_step import BASE

CAMPAIGN = ROOT/"claude/runs/20260912T145220Z-station-d0"
CASE = "station-d0-six-weak-cold"


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
    for rel in ("prepare/fixture.json", "prepare/initial.npz", "prepare/step.json"):
        assert sha(CAMPAIGN/rel) == manifest["artifacts_sha256"][rel], rel
    nominal_meta = json.loads((CAMPAIGN/"prepare/step.json").read_text())

    fixture = folder/"fixture.json"
    shutil.copyfile(CAMPAIGN/"prepare/fixture.json", fixture)
    shutil.copyfile(CAMPAIGN/"prepare/initial.npz", folder/"initial.npz")
    assert sha(fixture) == nominal_meta["fixture_sha256"], "copied fixture differs"

    pilot = WeakD0Pilot(*restore(fixture))
    x = np.zeros(len(pilot.names))
    orbit = 6*len(pilot.sats)
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

    _, constraints, residual, sigma, _, cost, products = pilot.evaluate(x, jacobian=False)
    assert not np.any(constraints[0][:, d0_columns]), "a prior row touches a D0 column"
    np.testing.assert_array_equal(constraints[1], np.zeros(priors))

    baseline_cost = json.loads((BASE/"six-0/step.json").read_text())["history"][0]["cost_before"]
    np.testing.assert_allclose(cost, baseline_cost, rtol=0, atol=1e-6)
    initial = np.load(folder/"initial.npz")
    np.testing.assert_array_equal(initial["satellites"], np.array(pilot.sats))
    seeded = np.array([[products.state(s, float(t))[:3] for t in initial["times_s"]] for s in pilot.sats])
    seed_error = float(np.max(np.abs(seeded-initial["states"][:, :, :3])))
    bitwise = bool(np.array_equal(seeded, initial["states"][:, :, :3]))
    assert seed_error < 1e-9, f"weak-cold products differ from the archived seed trajectory by {seed_error} m"

    report = dict(status="prepared", case=CASE, cold_start=True, weak_orbit_prior=True, source_sha256=sources(),
                  fixture_sha256=sha(fixture), nominal_campaign=str(CAMPAIGN),
                  nominal_fixture_sha256=nominal_meta["fixture_sha256"], warm_fixture_sha256=nominal_meta["fixture_sha256"],
                  orbit_prior_factor=ORBIT_FACTOR, declared_position_sigma_m=1000.*ORBIT_FACTOR,
                  declared_velocity_sigma_mps=1.*ORBIT_FACTOR, wet_priors_unchanged=True, d0_prior_absent=True,
                  orbit_prior_entries=orbit,
                  code_rows=code, phase_rows=phase, prior_rows=priors, retained_parameters=n,
                  local_clock_parameters=local, workspace_estimate_mib=workspace/2**20, budget_pass=True,
                  zero_start_cost=cost, archived_zero_start_cost=baseline_cost,
                  zero_start_cost_difference=cost-baseline_cost, zero_start_cost_matches_baseline=True,
                  zero_start_prior_residuals_all_zero=True,
                  seed_trajectory_max_difference_m=seed_error, seed_trajectory_bitwise=bitwise,
                  force_prior_absent=True, embedded_baseline_bitwise=True, precise_products_used=False,
                  residual_rows=int(len(residual)), protocol_sha256=sha(ROOT/"D0_POD_PROTOCOL.md"))
    (folder/"step.json").write_text(json.dumps(report, indent=2)+"\n")

    cold = folder/"cold"
    cold.mkdir()
    np.savez_compressed(cold/"solution.npz", x=x, names=np.array(pilot.names))
    (cold/"step.json").write_text(json.dumps(dict(fixture_sha256=sha(fixture),
                                                  solution_sha256=sha(cold/"solution.npz"),
                                                  history=[]), indent=2)+"\n")
    saved = np.load(cold/"solution.npz")
    assert np.all(saved["x"] == 0.) and len(saved["x"]) == len(pilot.names)
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
