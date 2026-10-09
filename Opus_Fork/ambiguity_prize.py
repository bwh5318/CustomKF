"""If every ambiguity were resolved exactly, how much would the orbits tighten?

    python -m Opus_Fork.guard --profile fork8t --timeout 900 --label amb-prize -- Opus_Fork.ambiguity_prize \
        --solution DIR [--solution DIR ...]

Five hypotheses have been tested (`results/WEIGHTS_W2_AND_CAUSE.md`). Dynamics and force
parameters are exonerated: the reference orbit fits our own model to 0.78 cm along-track and we
recover D0 to under 1 nm/s². So the residual 39.6 cm on G21 sits in the estimated initial state,
which means observation strength and nuisance coupling.

Ambiguity resolution is the standard fix and the largest remaining build, so it is worth knowing
the size of the prize before paying for it. That is answerable exactly, with no fit, from the
saved retained covariance.

With C the retained covariance and J = C^-1 the information matrix, partition the parameters
into orbit/force/troposphere (o) and ambiguities (a):

    J = [[J_oo, J_oa], [J_ao, J_aa]]

Leaving ambiguities free gives the orbit block C[o,o]. **Fixing them exactly** gives inv(J_oo) —
the Schur complement removed. The ratio of those two is precisely what perfect ambiguity
resolution would be worth to orbit determination, in formal terms.

An earlier diagnostic (`ambiguity_health.json`) measured the leverage of each ambiguity
*individually* and found it uncorrelated with the measured along-track error. That rejected a
specific mechanism — that late, short arcs are individually weak — and it does **not** settle
this question. Individually weak and collectively absorbing are different things: 1172 float
constants, one per station-satellite arc, can jointly soak up an along-track signature that no
single one of them explains.

**Formal, not actual.** W2's formal sigmas are demonstrably over-confident, so these ratios
bound relative information gain and must not be read as a predicted centimetre improvement.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np

from customkf.prepare_stage2 import sha

from .blocks import satellite_blocks, group
from .paths import RESULTS
from .store import resolve


def rac_axes(position, velocity):
    radial = position/np.linalg.norm(position)
    normal = np.cross(position, velocity)
    normal = normal/np.linalg.norm(normal)
    return np.vstack([radial, np.cross(normal, radial), normal])


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution", action="append", required=True)
    parser.add_argument("--day", default="2026-08-02")
    args = parser.parse_args()
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(args.day).items()}

    report = dict(status="ambiguity_prize_diagnostic_not_accuracy_acceptance", day=args.day,
                  note="Formal information only. Ratios are free-ambiguity sigma divided by "
                       "exactly-fixed-ambiguity sigma, from the Schur complement of the saved "
                       "covariance. Formal sigmas here are known to be over-confident.",
                  arms={})

    for spec in args.solution:
        path = resolve(spec)
        solution = path/"solution.npz" if path.is_dir() else path
        label = solution.parent.parent.name
        with np.load(solution) as f:
            names = [str(n) for n in f["names"]]
            cov = np.array(f["retained_covariance"], dtype=float)
            satellites = [str(s) for s in f["satellites"]]
            states0 = np.array(f["states"][:, 0, :], dtype=float)
        retained = [n for n in names if not n.startswith("clock")]
        if cov.shape != (len(retained), len(retained)):
            raise ValueError("Covariance does not match the non-clock parameter list")
        index = {n: i for i, n in enumerate(retained)}
        ambiguity = np.array([n.startswith("amb:") for n in retained])
        other = ~ambiguity

        # J = C^-1, then invert only the non-ambiguity block: that is the covariance with
        # every ambiguity held exactly. Cholesky both ways so a loss of positive-definiteness
        # is an error rather than a silently wrong answer.
        chol = np.linalg.cholesky(cov)
        identity = np.eye(len(retained))
        information = np.linalg.solve(chol.T, np.linalg.solve(chol, identity))
        information = 0.5*(information+information.T)
        block = information[np.ix_(other, other)]
        fixed = np.linalg.inv(np.linalg.cholesky(block).T)
        fixed = fixed@fixed.T
        free_map = {n: k for k, n in enumerate([retained[i] for i in np.flatnonzero(other)])}

        arm = dict(solution=str(solution), sha256=sha(solution),
                   ambiguities=int(ambiguity.sum()), other_parameters=int(other.sum()),
                   satellites={})
        for si, sat in enumerate(satellites):
            keys = [f"orbit:{sat}:{k}" for k in range(6)]
            if not all(k in index for k in keys):
                continue
            free_idx = [index[k] for k in keys]
            fix_idx = [free_map[k] for k in keys]
            axes = rac_axes(states0[si, :3], states0[si, 3:])
            free6 = cov[np.ix_(free_idx, free_idx)]
            fix6 = fixed[np.ix_(fix_idx, fix_idx)]
            entry = dict(block=blocks.get(sat))
            for name, sub in (("free", free6), ("fixed", fix6)):
                position = axes@sub[:3, :3]@axes.T
                velocity = axes@sub[3:, 3:]@axes.T
                entry[name] = dict(
                    position_rac_sigma_mm=(np.sqrt(np.diag(position))*1000).tolist(),
                    velocity_rac_sigma_um_s=(np.sqrt(np.diag(velocity))*1e6).tolist())
            entry["position_ratio_rac"] = [a/b for a, b in zip(entry["free"]["position_rac_sigma_mm"],
                                                               entry["fixed"]["position_rac_sigma_mm"])]
            entry["velocity_ratio_rac"] = [a/b for a, b in zip(entry["free"]["velocity_rac_sigma_um_s"],
                                                               entry["fixed"]["velocity_rac_sigma_um_s"])]
            # Along-track drift over 24 h is driven mainly by the along-track velocity error.
            entry["along_velocity_ratio"] = entry["velocity_ratio_rac"][1]
            entry["information_gain_6d"] = float(np.exp(
                (np.linalg.slogdet(free6)[1]-np.linalg.slogdet(fix6)[1])/6))
            arm["satellites"][sat] = entry
        ratios = [d["along_velocity_ratio"] for d in arm["satellites"].values()]
        arm["median_along_velocity_ratio"] = float(np.median(ratios))
        arm["median_information_gain_6d"] = float(np.median(
            [d["information_gain_6d"] for d in arm["satellites"].values()]))
        report["arms"][label] = arm

        print(f"\n=== {label} : {arm['ambiguities']} ambiguities, {arm['other_parameters']} other ===")
        print(f"{'sat':5s} {'blk':6s} {'free A-vel':>11s} {'fixed A-vel':>12s} {'ratio':>7s} "
              f"{'free A-pos':>11s} {'fixed A-pos':>12s} {'6D gain':>8s}")
        print("-"*80)
        for sat, d in sorted(arm["satellites"].items(), key=lambda kv: -kv[1]["along_velocity_ratio"]):
            print(f"{sat:5s} {str(d['block']):6s} {d['free']['velocity_rac_sigma_um_s'][1]:11.3f} "
                  f"{d['fixed']['velocity_rac_sigma_um_s'][1]:12.3f} {d['along_velocity_ratio']:7.2f} "
                  f"{d['free']['position_rac_sigma_mm'][1]:11.2f} {d['fixed']['position_rac_sigma_mm'][1]:12.2f} "
                  f"{d['information_gain_6d']:8.2f}")
        print(f"median along-track velocity sigma ratio {arm['median_along_velocity_ratio']:.2f}, "
              f"median 6-D information gain {arm['median_information_gain_6d']:.2f}")

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"ambiguity_prize.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"ambiguity_prize.json").write_text(text)
    print("\nWrote "+str(out/"ambiguity_prize.json"))


if __name__ == "__main__":
    main()
