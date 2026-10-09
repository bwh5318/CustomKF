"""Real-data parity of the eliminating solve (PROTOCOL.md amendment A2), run by the networks chain before any S50 fit.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 900 -- \
        Opus_Fork.experiments.networks.parity_check

The pass rule was fixed in A2 before the check fit ran. `E-check-0620` repeats `V-op-0620`: the same fixture,
configuration, gradients and settings, with `--eliminate-ambiguities`. Ambiguity elimination is algebraically exact,
so the two final orbits must agree to rounding. **Pass** if every saved position, all satellites on the 300 s grid,
differs by at most 1 mm. Exits 1 on a failure, which stops the chain before S50.

Writes `parity.json` in the run folder. Solution arrays only; no reference product is read.
"""
import json
import sys

import numpy as np

from Opus_Fork.experiments.gradients.analyze_validation import campaign, final_solution
from Opus_Fork.experiments.transfer.common import run_dir, sha
from Opus_Fork.paths import ROOT

REFERENCE, CHECK, LIMIT_M = "V-op-0620", "E-check-0620", 1e-3


def model_core(force_model):
    """The force-model binding without the gradient input list and module hash. V-op-0620 predates the arc-only
    gradient binding (d281a93), whose values were shown bitwise identical; the differences are reported, not hidden."""
    core = dict(force_model)
    if "gradients" in core:
        core["gradients"] = {k: v for k, v in core["gradients"].items() if k not in ("inputs", "module_sha256")}
    return core


def solution(label):
    folder = campaign(label)
    fit = final_solution(folder)                          # refuses an incomplete or unconverged campaign
    with np.load(fit["path"]) as f:
        x, names = f["x"].copy(), [str(n) for n in f["names"]]
    spec = json.loads((folder/"validation.json").read_text()).get("spec", {})
    return dict(folder=folder.name, final=fit["final"], states=fit["states"], sats=fit["sats"], times=fit["times"],
                x=x, names=names, path=fit["path"], sha256=sha(fit["path"]),
                eliminate=bool(spec.get("eliminate_ambiguities")), force_model=fit["force_model"])


def main():
    folder = run_dir()
    ref, chk = solution(REFERENCE), solution(CHECK)
    report = dict(reference=dict((k, ref[k]) for k in ("folder", "final", "path", "sha256", "eliminate")),
                  check=dict((k, chk[k]) for k in ("folder", "final", "path", "sha256", "eliminate")),
                  limit_m=LIMIT_M)
    same = (ref["sats"] == chk["sats"] and np.array_equal(ref["times"], chk["times"]) and ref["names"] == chk["names"]
            and model_core(ref["force_model"]) == model_core(chk["force_model"]) and not ref["eliminate"] and chk["eliminate"])
    report["same_layout_and_model"] = bool(same)
    report["force_model_fields_differing"] = sorted(k for k in set(ref["force_model"]) | set(chk["force_model"])
                                                    if ref["force_model"].get(k) != chk["force_model"].get(k))
    if same:
        diff = np.linalg.norm(chk["states"]-ref["states"], axis=2)
        index = {n: i for i, n in enumerate(ref["names"])}
        orbit = [index[n] for n in ref["names"] if n.startswith("orbit:")]
        force = [index[n] for n in ref["names"] if n.startswith("srp")]
        report.update(max_position_difference_m=float(diff.max()), rms_position_difference_m=float(np.sqrt(np.mean(diff**2))),
                      worst_satellite=ref["sats"][int(np.unravel_index(diff.argmax(), diff.shape)[0])],
                      max_orbit_parameter_difference=float(np.max(np.abs(chk["x"][orbit]-ref["x"][orbit]))),
                      max_force_parameter_difference=float(np.max(np.abs(chk["x"][force]-ref["x"][force]))) if force else 0.)
    report["passed"] = bool(same and report["max_position_difference_m"] <= LIMIT_M)
    (folder/"parity.json").write_text(json.dumps(report, indent=1, default=float)+"\n")
    print(json.dumps({k: report.get(k) for k in ("same_layout_and_model", "max_position_difference_m",
                                                 "rms_position_difference_m", "passed")}), flush=True)
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
