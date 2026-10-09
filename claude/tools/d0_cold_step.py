"""Cold-start preparation for the station-only D0 case (guarded; no SP3 reads).

Astra's `d0_step prepare` only builds a *warm* checkpoint from the archived
fixed-D0 station solution. This module builds the control that the handoff asks
for: the same fixture and initial states, but a checkpoint whose entire x vector
is zero, i.e. broadcast orbit seeds, nominal D0 = -1e-7 m/s^2 and the original
internal clock/ambiguity initialisation, with no previous station-fit correction.

Nothing else changes: same priors, rows, sigmas, ambiguities, clock datum, six
hours and ten-minute cadence. The unchanged guarded `claude.tools.d0_iteration`
workers then run the identical linearisation, line search and stopping rule.
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
from claude.tools.d0_pilot import D0Pilot, SCALE
from claude.tools.d0_step import BASE

CAMPAIGN = ROOT/"claude/runs/20260912T145220Z-station-d0"
CASE = "station-d0-six-cold"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare",))
    parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])

    # Pin the warm campaign we are controlling against, and the six-hour baseline.
    manifest = json.loads((CAMPAIGN/"validation.json").read_text())
    if manifest["status"] != "station_d0_complete_not_accuracy_acceptance":
        raise ValueError("Warm campaign incomplete")
    for name, digest in manifest["source_sha256"].items():
        assert sha(ROOT/name) == digest, name
    for rel in ("prepare/fixture.json", "prepare/initial.npz", "prepare/step.json", "linear-1/solution.npz"):
        assert sha(CAMPAIGN/rel) == manifest["artifacts_sha256"][rel], rel
    warm_meta = json.loads((CAMPAIGN/"prepare/step.json").read_text())

    # Same fixture and initial states, copied and re-pinned.
    fixture = folder/"fixture.json"
    shutil.copyfile(CAMPAIGN/"prepare/fixture.json", fixture)
    shutil.copyfile(CAMPAIGN/"prepare/initial.npz", folder/"initial.npz")
    assert sha(fixture) == warm_meta["fixture_sha256"], "copied fixture differs from the warm preparation"

    pilot = D0Pilot(*restore(fixture))
    x = np.zeros(len(pilot.names))
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

    # A zero x must reproduce the broadcast-seed nominal start of the archived
    # six-hour fixed-D0 fit exactly: same seeds, same nominal D0, same everything.
    baseline_cost = json.loads((BASE/"six-0/step.json").read_text())["history"][0]["cost_before"]
    np.testing.assert_allclose(cost, baseline_cost, rtol=0, atol=1e-6)
    initial = np.load(folder/"initial.npz")
    np.testing.assert_array_equal(initial["satellites"], np.array(pilot.sats))
    seeded = np.array([[products.state(s, float(t))[:3] for t in initial["times_s"]] for s in pilot.sats])
    difference = seeded-initial["states"][:, :, :3]
    seed_error = float(np.max(np.abs(difference)))
    bitwise = bool(np.array_equal(seeded, initial["states"][:, :, :3]))
    assert seed_error < 1e-9, f"cold products differ from the archived seed trajectory by {seed_error} m"

    report = dict(status="prepared", case=CASE, cold_start=True, source_sha256=sources(),
                  fixture_sha256=sha(fixture), warm_campaign=str(CAMPAIGN),
                  warm_fixture_sha256=warm_meta["fixture_sha256"],
                  code_rows=code, phase_rows=phase, prior_rows=priors, retained_parameters=n,
                  local_clock_parameters=local, workspace_estimate_mib=workspace/2**20, budget_pass=True,
                  zero_start_cost=cost, archived_zero_start_cost=baseline_cost,
                  zero_start_cost_difference=cost-baseline_cost, zero_start_cost_matches_baseline=True,
                  seed_trajectory_max_difference_m=seed_error, seed_trajectory_bitwise=bitwise, force_prior_absent=True,
                  embedded_baseline_bitwise=True, precise_products_used=False,
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
    assert np.all(saved["x"][d0_columns] == 0.) and SCALE == 1e-7
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
