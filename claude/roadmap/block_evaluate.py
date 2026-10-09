"""Guarded evaluation of the block-D0 campaign: A0/A1 archives versus new arms B/C.

    python -m customkf.guard -- claude.roadmap.block_evaluate CAMPAIGN_DIR

Raw IGS rapid comparison on exact native keys; no alignment; all satellites; per-block pooling.
Independent of Astra's RAC scorer except for the Stage 0 rac_difference/orbit_ure formulas.
"""
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.comparison import rac_difference, orbit_ure_m
from claude.roadmap.common import DatedReference, satellite_blocks, block_group, write_json

ARCHIVES = {
    "2026-08-02": {"A0": "claude/runs/20260912T021739Z-arc/six-1", "A1": "claude/runs/20260912T145220Z-station-d0/linear-1"},
    "2026-08-03": {"A0": "claude/runs/20260912T193417Z-day215-pod/fixed-linear-2", "A1": "claude/runs/20260912T193417Z-day215-pod/d0-linear-3"},
}
EXPECTED_COMMON = {("2026-08-02", "A0"): .543656441, ("2026-08-02", "A1"): .441752106,
                   ("2026-08-03", "A0"): .620816744, ("2026-08-03", "A1"): .713457544}
COMMON_LIMIT = 10810.


def pooled(values):
    rac = np.array(values)
    return dict(samples=len(rac), rms_3d_m=float(np.sqrt(np.mean(np.sum(rac**2, axis=1)))),
                rms_rac_m=np.sqrt(np.mean(rac**2, axis=0)).tolist(),
                rms_orbit_ure_m=float(np.sqrt(np.mean(orbit_ure_m(rac)**2))), mean_rac_m=np.mean(rac, axis=0).tolist())


def load(path):
    step = json.loads((path/"step.json").read_text())
    assert sha(path/"solution.npz") == step["solution_sha256"], path
    assert step["status"] in ("converged", "iteration_complete"), (path, step["status"])
    return np.load(path/"solution.npz"), sha(path/"solution.npz")


def score_day(day, origin, arms, calibration):
    reference = DatedReference(day, origin)
    blocks = {s: block_group(t) for s, (t, _) in satellite_blocks(day).items()}
    out = {"reference_sha256": reference.sha256, "arms": {}, "solutions_sha256": {}}
    samples = {}
    for arm, path in arms.items():
        f, digest = load(path)
        out["solutions_sha256"][arm] = digest
        sats, times = list(map(str, f["satellites"])), list(map(float, f["times_s"]))
        rac, keys = {}, []
        for si, sat in enumerate(sats):
            for ti, t in enumerate(times):
                s = reference.sample(sat, t)
                if s is None:
                    continue
                rotation = reference.epoch.celestial_to_terrestrial(t)
                estimate = f["states"][si, ti, :3]
                cartesian = rotation@estimate-s.xyz_m
                d = rac_difference(rotation.T@s.xyz_m, estimate, reference.precise.state(sat, t)[3:])
                assert abs(np.linalg.norm(d)-np.linalg.norm(cartesian)) < 2e-8
                rac.setdefault(sat, []).append((t, d))
                keys.append((sat, t))
        samples[arm] = (rac, keys)
    key_sets = {arm: v[1] for arm, v in samples.items()}
    first = next(iter(key_sets.values()))
    assert all(k == first for k in key_sets.values()), "Native sample keys differ between arms"
    for domain in ("common", "full"):
        domain_out = {}
        for arm, (rac, _) in samples.items():
            per = {}
            for sat, rows in rac.items():
                chosen = [d for t, d in rows if domain == "full" or t <= COMMON_LIMIT]
                per[sat] = pooled(chosen)
                per[sat]["block"] = blocks[sat]
            everything = [d for sat, rows in rac.items() for t, d in rows if domain == "full" or t <= COMMON_LIMIT]
            by_block = {}
            for group in sorted(set(blocks[s] for s in rac)):
                by_block[group] = pooled([d for sat, rows in rac.items() if blocks[sat] == group
                                          for t, d in rows if domain == "full" or t <= COMMON_LIMIT])
            domain_out[arm] = dict(all=pooled(everything), by_block=by_block, per_satellite=per)
        for arm in domain_out:
            if arm == "A0":
                continue
            base, new = domain_out["A0"]["per_satellite"], domain_out[arm]["per_satellite"]
            ratios = np.array([np.log(new[s]["rms_3d_m"]/base[s]["rms_3d_m"]) for s in base])
            domain_out[arm]["versus_A0"] = dict(
                pooled_3d_change_percent=100*(domain_out[arm]["all"]["rms_3d_m"]/domain_out["A0"]["all"]["rms_3d_m"]-1),
                median_log_ratio=float(np.median(ratios)), median_ratio=float(np.exp(np.median(ratios))),
                improved=int(np.sum(ratios < 0)), worsened=int(np.sum(ratios > 0)),
                regressions_over_10_cm={s: new[s]["rms_3d_m"]-base[s]["rms_3d_m"] for s in base
                                        if new[s]["rms_3d_m"]-base[s]["rms_3d_m"] > .1})
        out["arms"][domain] = domain_out
    for arm in ("A0", "A1"):
        got = out["arms"]["common"][arm]["all"]["rms_3d_m"]
        assert abs(got-EXPECTED_COMMON[day, arm]) < 2e-8, (day, arm, got)
    out["archive_self_check"] = "A0/A1 common pooled 3D RMS reproduced within 2e-8 m"
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    if sys.argv[1] == "--smoke":
        fixtures = {"2026-08-02": "runs/20260912T161029Z-0ddb71b3/fixture.json",
                    "2026-08-03": "claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json"}
        smoke = {}
        for day, spec in ARCHIVES.items():
            origin = json.loads((ROOT/fixtures[day]).read_text())["context"]["origin_ns"]
            r = score_day(day, origin, {a: ROOT/p for a, p in spec.items()}, None)
            smoke[day] = {dom: {a: dict(all=v["all"], by_block={g: b["rms_3d_m"] for g, b in v["by_block"].items()})
                                for a, v in r["arms"][dom].items()} for dom in ("common", "full")}
        write_json(output/"smoke.json", dict(status="archive_only_smoke_not_campaign", days=smoke))
        print(json.dumps(smoke, indent=2), flush=True)
        return
    campaign = Path(sys.argv[1])
    manifest = json.loads((campaign/"validation.json").read_text())
    calibration_path = campaign/manifest["calibration"]["path"]
    assert sha(calibration_path) == manifest["calibration"]["sha256"]
    calibration = json.loads(calibration_path.read_text())
    report = dict(status="block_d0_evaluation_complete_not_accuracy_acceptance", calibration_sha256=sha(calibration_path),
                  days={})
    for day, spec in manifest["days"].items():
        fixture = json.loads((ROOT/spec["fixture"]).read_text())
        origin = fixture["context"]["origin_ns"]
        arms = {name: ROOT/path for name, path in ARCHIVES[day].items()}
        for arm, final in spec["finals"].items():
            arms[arm] = campaign/final
        day_report = score_day(day, origin, arms, calibration)
        if "C" in spec["finals"]:
            f, _ = load(campaign/spec["finals"]["C"])
            names = {str(n): i for i, n in enumerate(f["names"])}
            day_report["arm_C_coefficients"] = {str(s): dict(
                D0_mps2=calibration["nominal_d0_mps2"][str(s)]+1e-7*float(f["x"][names[f"srpD0:{s}"]]),
                formal_sigma_mps2=1e-7*float(np.sqrt(f["retained_covariance"][names[f"srpD0:{s}"], names[f"srpD0:{s}"]])))
                for s in f["satellites"]}
        benefit = {}
        for arm in spec["finals"]:
            benefit[arm] = {domain: day_report["arms"][domain][arm]["versus_A0"]["pooled_3d_change_percent"] <= -5.
                            for domain in ("common", "full")}
        day_report["five_percent_benefit_vs_A0"] = benefit
        report["days"][day] = day_report
    flag = all(report["days"][d]["five_percent_benefit_vs_A0"].get("B", {}).get(x, False)
               for d in report["days"] for x in ("common", "full"))
    report["arm_B_predeclared_flag_both_days_both_domains"] = flag
    write_json(output/"evaluation.json", report)
    summary = {d: {dom: {a: round(v["all"]["rms_3d_m"], 6) for a, v in r["arms"][dom].items()} for dom in ("common", "full")}
               for d, r in report["days"].items()}
    print(json.dumps(dict(summary=summary, flag_B=flag), indent=2), flush=True)


if __name__ == "__main__":
    main()
