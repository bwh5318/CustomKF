"""T0.1: where our orbit-only URE lives, by component and by harmonic, against IGS final.

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 1800 --label radial-budget \
        -- Opus_Fork.radial_budget

Evaluation only. Archived, converged solutions are re-scored epoch by epoch against IGS final,
with NGA PE scored alongside on the same satellite-epochs. No fit, no estimator input; the
reference products are read only here.

**Question** (`results/URE_REVIEW_AND_TEST_PLAN.md` T0.1). Radial error is 81-83% of URE² in every
case scored so far, and its pooled mean is +1.2..+1.7 cm. How much of the radial (and
cross-track) mean square is a per-satellite constant, a once-per-revolution term, a
twice-per-revolution term, or the rest? A constant is what an unmodelled radial force (Earth
radiation pressure, antenna thrust) leaves; 1/rev is the SRP-type signature a box-wing or
ECOM change would target.

**Method, fixed before any output was read.** Per satellite and component, nested
least-squares fits on the common native 15-minute epochs, in argument of latitude u from the
reference's own inertial position and velocity:

- radial and cross-track: [1] -> [1, cos u, sin u] -> [+ cos 2u, sin 2u];
- along-track: [1] -> [1, t] -> [+ cos u, sin u] -> [+ cos 2u, sin 2u].

The reductions in sum of squares are exactly additive and sum to the total. Pooled over
satellites they are converted to URE² with the contract weights 0.98² (radial) and 1/49
(along, cross). The per-satellite constant is compared against the antenna-thrust radial shift
predicted from the IGS metadata alone, f/(3n²) with f = P/(m·c).

**Declared expectation** (from the plan, before running): the radial constant is ≥20% of radial
mean square in every case; the per-satellite radial mean is positive on ≥80% of satellites;
the sign and the block ordering (IIR/IIF/IIR-M above IIIA) repeat on every day. NGA is the
control: its constant term should be much smaller.

**Cases.** Aug 2: P0, W1, W2 (27 satellites) and N0 (31); Aug 7 and Aug 8: the archived core
and expanded cross-date arms; Aug 8: the native-gap candidate. Aug 6 is deliberately absent:
its paired test stopped unscored and its baseline score is not read here.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.frames import EarthOrientation
from customkf.prepare_stage2 import ROOT, sha

from .baseline import Fit, OnOrigin
from .blocks import satellite_blocks, group
from .evaluate import load_reference, midnight_of
from .paths import STAGE2, RESULTS
from . import satmeta

GM = 3.986004415e14
CASES = {
    "2026-08-02": {
        "P0": ("claude/runs/20260913T220409Z-long-NL-25st-24h/lin2-solve/solution.npz",
               "claude/runs/20260913T214809Z-roadmap-stations/prepare-25-24h/fixture.json"),
        "W1": ("Opus_Fork/runs/20260920T030309Z-fit-W1-25st-24h/lin2-solve/solution.npz",
               "Opus_Fork/runs/fixtures/W1-25st-24h/fixture.json"),
        "W2": ("Opus_Fork/runs/20260920T035014Z-fit-W2-25st-24h/lin2-solve/solution.npz",
               "Opus_Fork/runs/fixtures/W2-25st-24h/fixture.json"),
        "N0": ("Opus_Fork/runs/20260920T203126Z-fit-N0-31sat/lin2-solve/solution.npz",
               "Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json"),
    },
    "2026-08-07": {
        "core14": ("runs/20260920T170926Z-0887a179/solution.npz", "runs/20260920T155421Z-a935f80c/fixture.json"),
        "expanded25": ("runs/20260920T180129Z-38cb5d57/solution.npz", "runs/20260920T155655Z-7b703635/fixture.json"),
    },
    "2026-08-08": {
        "core14": ("runs/20260920T183806Z-03ec5196/solution.npz", "runs/20260920T160347Z-59671675/fixture.json"),
        "expanded25": ("runs/20260920T193048Z-97d546ab/solution.npz", "runs/20260920T160634Z-40ed23ee/fixture.json"),
        "nativegap24": ("runs/20260921T224158Z-dc785352/solution.npz",
                        "runs/20260921T021034Z-9cb93a03/expanded25_candidate_fixture.json"),
    },
}
WEIGHT = np.array([0.98**2, 1/49, 1/49])
TERMS = {0: ("mean", "1/rev", "2/rev"), 1: ("mean", "trend", "1/rev", "2/rev"), 2: ("mean", "1/rev", "2/rev")}


def design(component, u, t):
    one = np.ones_like(u)
    rev1, rev2 = [np.cos(u), np.sin(u)], [np.cos(2*u), np.sin(2*u)]
    if component == 1:
        tn = (t-t.mean())/86400.
        return [[one], [tn], rev1, rev2]
    return [[one], rev1, rev2]


def nested(y, blocks):
    """Sum-of-squares reduction for each successive block, plus the remainder and coefficients."""
    total = float(y@y)
    left, columns, parts, coef = total, [], [], None
    for block in blocks:
        columns += block
        a = np.array(columns).T
        coef, *_ = np.linalg.lstsq(a, y, rcond=None)
        r = y-a@coef
        now = float(r@r)
        parts.append(left-now)
        left = now
    return total, parts, left, coef


def geometry(reference, sat, t):
    r = reference.position(sat, t)
    v = reference.velocity(sat, t)
    radial = r/np.linalg.norm(r)
    normal = np.cross(r, v)/np.linalg.norm(np.cross(r, v))
    along = np.cross(normal, radial)
    node = np.cross([0., 0., 1.], normal)
    node /= np.linalg.norm(node)
    u = np.arctan2(r@np.cross(normal, node), r@node)
    return r, np.array([radial, along, normal]), u, float(np.linalg.norm(r))


def budget(reference, candidate, keys, blocks, meta):
    by_sat = {}
    for sat, ns in sorted(keys):
        t = (ns-reference.origin_ns)/1e9
        r, axes, u, radius = geometry(reference, sat, t)
        d = candidate.position(sat, t)-r
        by_sat.setdefault(sat, []).append((t, u, radius, *(axes@d)))
    pooled = {c: dict(total=0., parts=None, remainder=0.) for c in range(3)}
    per_sat, n_all = {}, 0
    for sat, rows in by_sat.items():
        a = np.array(rows)
        t, u, radius, rac = a[:, 0], np.unwrap(a[:, 1]), a[:, 2], a[:, 3:]
        n_all += len(a)
        entry = dict(samples=len(a), block=blocks.get(sat), rms_rac_cm=(np.sqrt(np.mean(rac**2, axis=0))*100).tolist(),
                     mean_rac_cm=(rac.mean(axis=0)*100).tolist())
        for c in range(3):
            total, parts, left, coef = nested(rac[:, c], design(c, u, t))
            p = pooled[c]
            p["total"] += total
            p["remainder"] += left
            p["parts"] = parts if p["parts"] is None else [x+y for x, y in zip(p["parts"], parts)]
            name = "RAC"[c]
            entry[name+"_fit_cm"] = dict(constant=float(coef[0])*100,
                                         amp_1rev=float(np.hypot(*coef[-4:-2]))*100 if c != 1 else float(np.hypot(*coef[2:4]))*100,
                                         amp_2rev=float(np.hypot(*coef[-2:]))*100,
                                         remainder_rms=float(np.sqrt(left/len(a)))*100)
        if sat in meta:
            m = meta[sat]
            n2 = GM/np.mean(radius)**3
            entry.update(svn=m.svn, metadata_block=m.block, mass_kg=m.mass_kg, tx_power_w=m.tx_power_w,
                         thrust_mps2=m.thrust_mps2, predicted_thrust_radial_shift_cm=m.thrust_mps2/(3*n2)*100)
        per_sat[sat] = entry
    out = dict(samples=n_all, satellites=len(per_sat), components={})
    ure_total = 0.
    for c in range(3):
        p = pooled[c]
        ms = {k: v/n_all for k, v in zip(TERMS[c], p["parts"])}
        ms["remainder"] = p["remainder"]/n_all
        ure = {k: float(WEIGHT[c]*v*1e4) for k, v in ms.items()}
        ure_total += sum(ure.values())
        out["components"]["RAC"[c]] = dict(mean_square_cm2={k: float(v*1e4) for k, v in ms.items()},
                                           rms_cm=float(np.sqrt(p["total"]/n_all))*100, ure2_cm2=ure)
    out["ure_cm"] = float(np.sqrt(ure_total))
    out["ure2_total_cm2"] = float(ure_total)
    means = np.array([e["mean_rac_cm"][0] for e in per_sat.values()])
    out["radial_mean_positive"] = f"{int(np.sum(means > 0))}/{len(means)}"
    out["radial_constant_share_of_radial_ms"] = out["components"]["R"]["mean_square_cm2"]["mean"] / \
        sum(out["components"]["R"]["mean_square_cm2"].values())
    groups = {}
    for e in per_sat.values():
        groups.setdefault(e["block"], []).append(e)
    out["by_block"] = {g: dict(satellites=len(v), mean_of_radial_constants_cm=float(np.mean([e["R_fit_cm"]["constant"] for e in v])),
                               mean_1rev_radial_amp_cm=float(np.mean([e["R_fit_cm"]["amp_1rev"] for e in v])),
                               mean_predicted_thrust_shift_cm=float(np.mean([e.get("predicted_thrust_radial_shift_cm", np.nan) for e in v])))
                       for g, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}
    have = [e for e in per_sat.values() if "predicted_thrust_radial_shift_cm" in e]
    if len(have) > 3:
        x = np.array([e["predicted_thrust_radial_shift_cm"] for e in have])
        y = np.array([e["R_fit_cm"]["constant"] for e in have])
        out["radial_constant_vs_thrust_pearson"] = float(np.corrcoef(x, y)[0, 1])
    out["per_satellite"] = per_sat
    return out


def main():
    import argparse
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", nargs=4, action="append", metavar=("DAY", "LABEL", "SOLUTION", "FIXTURE"),
                        help="score these solutions instead of the frozen T0.1 case list")
    parser.add_argument("--out-name", default="radial_budget")
    args = parser.parse_args()
    cases = CASES
    if args.case:
        cases = {}
        for day, label, solution, fixture in args.case:
            cases.setdefault(day, {})[label] = (solution, fixture)
    run = Path(os.environ["CUSTOMKF_RUN_DIR"])
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    report = dict(status="evaluation_only_not_accuracy_acceptance", test="T0.1 radial budget",
                  reference="IGS final", note="Raw unaligned; nested per-satellite harmonic fits; NGA PE control on the same keys.",
                  satellite_metadata=satmeta.provenance(), days={})
    for day, arms in cases.items():
        midnight = midnight_of(day)
        blocks = {s: group(t) for s, (t, _) in satellite_blocks(day).items()}
        meta = satmeta.load(day)
        reference, ref_prov = load_reference("reference_igs_final", day, midnight, eop, "IGS final", "IGc20")
        nga, nga_prov = load_reference("reference_nga_pe", day, midnight, eop, "NGA PE", "WGS84", legacy="GPS")
        candidates, prov = {}, dict(igs_final=ref_prov, NGA=nga_prov)
        for label, (solution, fixture) in arms.items():
            solution, fixture = ROOT/solution, ROOT/fixture
            step = json.loads((solution.parent/"step.json").read_text())
            if step["status"] != "converged" or sha(solution) != step["solution_sha256"]:
                raise ValueError(f"{day} {label}: not a verified converged solution")
            candidates[label] = OnOrigin(Fit(solution, fixture, eop), midnight)
            prov[label] = dict(solution=str(solution), sha256=step["solution_sha256"], fixture=str(fixture),
                               fixture_sha256=sha(fixture))
        candidates["NGA"] = nga
        common = set(reference.keys())
        for c in candidates.values():
            common &= c.keys()
        entry = dict(provenance=prov, common_samples=len(common), satellites=sorted({s for s, _ in common}), arms={})
        for label, c in candidates.items():
            entry["arms"][label] = budget(reference, c, common, blocks, meta)
            b = entry["arms"][label]
            r = b["components"]["R"]["mean_square_cm2"]
            print(f"{day} {label:12s} URE {b['ure_cm']:.3f} | radial MS {sum(r.values()):.2f}: const {r['mean']:.2f} "
                  f"1/rev {r['1/rev']:.2f} 2/rev {r['2/rev']:.2f} rest {r['remainder']:.2f} | "
                  f"R>0 {b['radial_mean_positive']} | r(thrust) {b.get('radial_constant_vs_thrust_pearson', float('nan')):.2f}", flush=True)
        report["days"][day] = entry
    text = json.dumps(report, indent=2, default=float)+"\n"
    (run/f"{args.out_name}.json").write_text(text)
    (RESULTS/f"{args.out_name}.json").write_text(text)
    print("Wrote", run/f"{args.out_name}.json")


if __name__ == "__main__":
    main()
