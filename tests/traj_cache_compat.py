"""Read-only M10 compatibility check: an archived campaign cache still loads through the stricter loader.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --timeout 300 -- tests.traj_cache_compat

Rebuilds the SD-3 (Aug 3, 25 stations) pilot as its workers and `Opus_Fork/experiments/residuals/replay.py` did
(`sdeop.install()` with the campaign's variant; `iteration.build` with its fixture, config and state), then loads
the final linearization's `lin2-traj-*` caches with `claude.roadmap.traj_cache.cached_products`. As in replay.py,
the fork's force-model binding is checked field by field and the unbound loader is used, because these caches
record the pre-26-Sep hashes of the two sub-daily-EOP source files (their hook switch was verified bit-identical).

Requires: accepted with the caller identity `build` now records; states equal, bitwise, to the states the fit
saved in `lin2-solve/solution.npz` from the same caches; refused for a different fixture or config hash.
Nothing under the campaign folder is written. Output: `traj_cache_compat.json` in the guard run folder.
"""
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import numpy as np

CAMPAIGN = "Opus_Fork/runs/20260925T215927Z-fit-SD-3-25st"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    from customkf.prepare_stage2 import ROOT, sha
    from customkf.stage5_pilot import forbid_precise_product_reads
    sys.addaudithook(forbid_precise_product_reads)
    start = time.perf_counter()
    camp = ROOT/CAMPAIGN
    v = json.loads((camp/"validation.json").read_text())
    assert v["status"].startswith("long_fit_complete") and v["final"] == "lin2-solve", v["status"]
    os.environ["OPUSFORK_SD_VARIANT"] = v["force_model"]["variant"]
    from Opus_Fork import sdeop
    iteration = sdeop.install()
    from claude.roadmap.traj_cache import cached_products
    fixture, config, state = ROOT/v["fixture"], ROOT/v["config"], camp/v["state"]["path"]
    assert sha(state) == v["state"]["sha256"]
    pilot, _ = iteration.build(SimpleNamespace(fixture=fixture, config=config, state=state))
    identity = dict(fixture_sha256=sha(fixture), config_sha256=sha(config))
    assert {k: pilot.context.get(k) for k in identity} == identity, "build did not record the caller identity"
    step = json.loads((camp/"lin2-solve"/"step.json").read_text())
    solution = camp/"lin2-solve"/"solution.npz"
    assert step["status"] == "converged" and sha(solution) == step["solution_sha256"]
    with np.load(solution) as f:
        names, x, saved_states, sats, times = f["names"], f["x"].copy(), f["states"].copy(), list(f["satellites"]), f["times_s"].copy()
    np.testing.assert_array_equal(names, pilot.names)
    files = sorted(str(p) for p in camp.glob("lin2-traj-*/trajectories.npz"))
    expected, skipped = sdeop.binding(), set()
    for path in files:
        got = json.loads((Path(path).parent/"trajectories.json").read_text())["force_model"]
        diff = {k for k in set(got) | set(expected) if got.get(k) != expected.get(k)}
        assert diff <= {"subdaily_eop_sha256", "sdeop_sha256"}, diff
        skipped |= diff
    load_start = time.perf_counter()
    products = cached_products(pilot, x, files)
    load_s = time.perf_counter()-load_start
    states = np.array([[products.state(s, t) for t in times] for s in sats])
    bitwise = bool(np.array_equal(states, saved_states))
    explicit = cached_products(pilot, x, files, **identity)
    explicit_bitwise = bool(np.array_equal(np.array([[explicit.state(s, t) for t in times] for s in sats]), saved_states))
    refusals = {}
    for name in identity:
        try:
            cached_products(pilot, x, files, **{name: "0"*64})
            refusals[name] = "ACCEPTED"
        except ValueError as exc:
            refusals[name] = str(exc)
    report = dict(status="traj_cache_compat_pass" if bitwise and explicit_bitwise and "ACCEPTED" not in refusals.values()
                  else "traj_cache_compat_FAIL",
                  campaign=CAMPAIGN, files=[Path(p).relative_to(ROOT).as_posix() for p in files],
                  cache_sha256=[sha(p) for p in files], fixture=v["fixture"], config=v["config"], caller_identity=identity,
                  accepted=True, satellites=len(sats), sampled_times=len(times), states_bitwise_equal_to_saved_solution=bitwise,
                  explicit_keyword_identity_bitwise=explicit_bitwise, wrong_identity_refusals=refusals,
                  force_model_fields_not_checked=sorted(skipped), load_seconds=load_s, total_seconds=time.perf_counter()-start)
    Path(os.environ["CUSTOMKF_RUN_DIR"], "traj_cache_compat.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)
    if report["status"] != "traj_cache_compat_pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
