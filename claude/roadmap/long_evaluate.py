"""Guarded evaluation of any set of station fits on one day (roadmap steps 2-4).

    python -m customkf.guard -- claude.roadmap.long_evaluate --day 2026-08-02 --out-name NAME \
        --arm A0 SOLUTION_DIR FIXTURE_JSON --arm B SOLUTION_DIR FIXTURE_JSON ... \
        --baseline A0 --domain first6h 12:00 18:00 --domain full12h 12:00 23:45 [--expect A0 first6h 0.543656441]

Raw IGS rapid comparison (contract formulas), no alignment. Samples are keyed by absolute GPST so fits
with different origins/arc lengths compare on identical native epochs; a domain is scored on the
keys common to *all* arms and any key present for some arms only is counted and reported.
Per-satellite, per-block (ANTEX groups) and pooled 3D/RAC/URE; paired median log ratio vs baseline.
"""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.sp3 import epoch_tag
from customkf.comparison import rac_difference, orbit_ure_m
from claude.roadmap.common import DatedReference, satellite_blocks, block_group, write_json


def pooled(values):
    rac = np.array(values)
    return dict(samples=len(rac), rms_3d_m=float(np.sqrt(np.mean(np.sum(rac**2, axis=1)))),
                rms_rac_m=np.sqrt(np.mean(rac**2, axis=0)).tolist(), rms_orbit_ure_m=float(np.sqrt(np.mean(orbit_ure_m(rac)**2))),
                mean_rac_m=np.mean(rac, axis=0).tolist())


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--out-name", required=True)
    parser.add_argument("--arm", nargs=3, action="append", required=True, metavar=("LABEL", "SOLUTION_DIR", "FIXTURE"))
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--domain", nargs=3, action="append", required=True, metavar=("NAME", "START", "END"))
    parser.add_argument("--expect", nargs=3, action="append", default=[], metavar=("LABEL", "DOMAIN", "RMS"))
    args = parser.parse_args()
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    date = datetime.strptime(args.day, "%Y-%m-%d")
    midnight = epoch_tag(date.strftime("* %Y %m %d 00 00 00"))
    reference = DatedReference(args.day, midnight)
    blocks = {s: block_group(t) for s, (t, _) in satellite_blocks(args.day).items()}
    errors, provenance = {}, {}
    for label, solution_dir, fixture_path in args.arm:
        solution_dir, fixture_path = Path(solution_dir), Path(fixture_path)
        step = json.loads((solution_dir/"step.json").read_text())
        assert step["status"] in ("converged", "iteration_complete") and sha(solution_dir/"solution.npz") == step["solution_sha256"], label
        origin = json.loads(fixture_path.read_text())["context"]["origin_ns"]
        f = np.load(solution_dir/"solution.npz")
        provenance[label] = dict(solution=str(solution_dir), solution_sha256=step["solution_sha256"], fixture_sha256=sha(fixture_path),
                                 status=step["status"], origin_ns=origin)
        table = {}
        for si, sat in enumerate(map(str, f["satellites"])):
            for ti, t in enumerate(map(float, f["times_s"])):
                absolute = origin+int(round(t*1e9))
                rt = (absolute-midnight)/1e9
                s = reference.sample(sat, rt)
                if s is None:
                    continue
                rotation = reference.epoch.celestial_to_terrestrial(rt)
                estimate = f["states"][si, ti, :3]
                d = rac_difference(rotation.T@s.xyz_m, estimate, reference.precise.state(sat, rt)[3:])
                cartesian = rotation@estimate-s.xyz_m
                assert abs(np.linalg.norm(d)-np.linalg.norm(cartesian)) < 2e-8
                table[sat, absolute] = d
        errors[label] = table
    report = dict(status="long_evaluation_not_accuracy_acceptance", day=args.day, reference_sha256=reference.sha256,
                  arms=provenance, domains={})
    for name, start, end in args.domain:
        h0, m0 = map(int, start.split(":"))
        h1, m1 = map(int, end.split(":"))
        lo = midnight+int((h0*3600+m0*60)*1e9)
        hi = midnight+int((h1*3600+m1*60)*1e9)
        keysets = {label: {k for k in table if lo <= k[1] <= hi} for label, table in errors.items()}
        common = set.intersection(*keysets.values())
        dropped = {label: len(keys-common) for label, keys in keysets.items()}
        out = dict(window=[start, end], common_samples=len(common), keys_outside_common=dropped, arms={})
        sats = sorted({k[0] for k in common})
        for label, table in errors.items():
            per = {s: pooled([table[k] for k in sorted(common) if k[0] == s]) | {"block": blocks[s]} for s in sats}
            by_block = {g: pooled([table[k] for k in sorted(common) if blocks[k[0]] == g]) for g in sorted({blocks[s] for s in sats})}
            out["arms"][label] = dict(all=pooled([table[k] for k in sorted(common)]), by_block=by_block, per_satellite=per)
        base = out["arms"][args.baseline]
        for label, arm in out["arms"].items():
            if label == args.baseline:
                continue
            ratios = np.array([np.log(arm["per_satellite"][s]["rms_3d_m"]/base["per_satellite"][s]["rms_3d_m"]) for s in sats])
            arm["versus_baseline"] = dict(baseline=args.baseline,
                pooled_3d_change_percent=100*(arm["all"]["rms_3d_m"]/base["all"]["rms_3d_m"]-1),
                by_block_3d_change_percent={g: 100*(v["rms_3d_m"]/base["by_block"][g]["rms_3d_m"]-1) for g, v in arm["by_block"].items()},
                median_ratio=float(np.exp(np.median(ratios))), improved=int(np.sum(ratios < 0)), worsened=int(np.sum(ratios > 0)),
                regressions_over_10_cm={s: arm["per_satellite"][s]["rms_3d_m"]-base["per_satellite"][s]["rms_3d_m"] for s in sats
                                        if arm["per_satellite"][s]["rms_3d_m"]-base["per_satellite"][s]["rms_3d_m"] > .1})
        report["domains"][name] = out
    for label, domain, value in args.expect:
        got = report["domains"][domain]["arms"][label]["all"]["rms_3d_m"]
        assert abs(got-float(value)) < 2e-8, (label, domain, got, value)
    report["expectations_checked"] = args.expect
    write_json(output/f"{args.out_name}.json", report)
    summary = {name: {label: dict(rms_3d_m=round(a["all"]["rms_3d_m"], 6), by_block={g: round(b["rms_3d_m"], 4) for g, b in a["by_block"].items()})
                      for label, a in d["arms"].items()} | dict(samples=d["common_samples"]) for name, d in report["domains"].items()}
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
