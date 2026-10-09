"""Guarded evaluator; common native IGS epochs are selected before pooling.

Reference products are opened only here, after station-only fits are complete.
Also verifies Cartesian RMS independently of the shared RAC scoring routine.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.stage5_pilot import ORIGIN
from claude.tools.arc_step import BASE
from claude.tools.evaluate_ablation import Reference, score, pooled, strip, summary


def diagnostics(fixture, fit):
    counts = Counter(r["arc"] for r in fixture["rows"])
    values = defaultdict(list); flags = []; k = 0
    for ei in range(fixture["context"]["epoch_count"]):
        for row in (r for r in fixture["rows"] if r["epoch"] == ei):
            for kind in range(2 if counts[row["arc"]] >= 3 else 1):
                r = float(fit["residual_m"][k]); z = r/float(fit["sigma_m"][k]); k += 1
                label = "phase" if kind else "code"
                values[f"{row['station']}:{label}"].append(r)
                if row["station"] == "GUAM" and 19210 <= row["time_s"] <= 20410 and kind:
                    flags.append(dict(satellite=row["satellite"],time_s=row["time_s"],residual_mm=r*1000,normalized=z))
    assert k == len(fit["residual_m"])
    return {"station_residuals": {key:dict(count=len(v),rms_m=float(np.sqrt(np.mean(np.square(v))))) for key,v in values.items()},
            "guam_known_episode_1720_to_1740":flags,
            "phase_eligible_arcs":sum(n>=3 for n in counts.values()),
            "retained_links":len(fixture["rows"])}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"): raise RuntimeError("Use customkf.guard")
    folder = Path(sys.argv[1]); manifest = json.loads((folder/"validation.json").read_text())
    reference = Reference(); full = {}; common = {}; diagnostic = {}; keys = {}
    cases = {"baseline":(BASE/"iteration-1",BASE/"prepare")}
    for name, case in manifest["cases"].items():
        cases[name] = (folder/case["final"],folder/case["prepare"])
    for name,(solution,prepare) in cases.items():
        step = json.loads((solution/"step.json").read_text())
        assert step["status"] == "converged" and sha(solution/"solution.npz") == step["solution_sha256"]
        fit = np.load(solution/"solution.npz")
        full[name] = score(reference,solution,prepare/"fixture.json",prepare/"initial.npz")
        common[name] = deepcopy(full[name]); squares = []; keys[name] = []; allsq = []
        for si,sat in enumerate(map(str,fit["satellites"])):
            native = []; local = []; all_local = []
            for ti,t in enumerate(map(float,fit["times_s"])):
                sample = reference.raw.samples.get((ORIGIN+int(round(t*1e9)),sat))
                if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted: continue
                d = reference.epoch.celestial_to_terrestrial(t)@fit["states"][si,ti,:3]-sample.xyz_m
                sq = float(d@d); all_local.append(sq)
                native.append(t <= 10810)
                if t <= 10810: local.append(sq); keys[name].append([sat,t])
            p = common[name]["per_satellite"][sat]
            for kind in ("fit","initial"):
                p["_racs"][kind] = [v for v,keep in zip(p["_racs"][kind],native) if keep]
                p[kind] = summary(p["_racs"][kind])
            np.testing.assert_allclose(np.sqrt(np.mean(local)),p["fit"]["rms_3d_m"],rtol=0,atol=2e-8)
            np.testing.assert_allclose(np.sqrt(np.mean(all_local)),full[name]["per_satellite"][sat]["fit"]["rms_3d_m"],rtol=0,atol=2e-8)
            squares.extend(local); allsq.extend(all_local)
        common[name]["groups"] = {g:pooled(common[name],sats) for g,sats in (
            ("all",list(common[name]["per_satellite"])),
            ("determined",[s for s,p in common[name]["per_satellite"].items() if p["class"]=="determined"]),
            ("poorly_determined",[s for s,p in common[name]["per_satellite"].items() if p["class"]!="determined"]))}
        assert len(squares)==403 and len(allsq)==(775 if name=="six" else 403)
        np.testing.assert_allclose(np.sqrt(np.mean(squares)),common[name]["groups"]["all"]["fit"]["rms_3d_m"],rtol=0,atol=2e-8)
        diagnostic[name] = diagnostics(json.loads((prepare/"fixture.json").read_text()),fit)
        diagnostic[name].update(independent_common_cartesian_rms_m=float(np.sqrt(np.mean(squares))),
                                independent_full_cartesian_rms_m=float(np.sqrt(np.mean(allsq))))
        assert keys[name] == keys["baseline"]
    comparisons = {}
    for label,before,after in (("density","baseline","three"),("duration","three","six"),("overall","baseline","six")):
        a,b = common[before],common[after]
        both = [s for s in a["per_satellite"] if a["per_satellite"][s]["class"]==b["per_satellite"][s]["class"]=="determined"]
        per = {s:{"before_m":p["fit"]["rms_3d_m"],"after_m":b["per_satellite"][s]["fit"]["rms_3d_m"],
                  "change_m":b["per_satellite"][s]["fit"]["rms_3d_m"]-p["fit"]["rms_3d_m"]} for s,p in a["per_satellite"].items()}
        ar = a["groups"]["all"]["fit"]["rms_3d_m"]; br = b["groups"]["all"]["fit"]["rms_3d_m"]
        comparisons[label] = dict(before=before,after=after,before_rms_m=ar,after_rms_m=br,
            relative_reduction_percent=100*(1-br/ar),five_percent_improvement=br<=.95*ar,
            regressions_over_10_cm=[s for s,p in per.items() if p["change_m"]>.1],per_satellite=per,
            determined_in_both={before:pooled(a,both),after:pooled(b,both)})
    report = dict(status="arc_experiment_evaluated_not_accuracy_acceptance",reference_sha256=reference.sha256,
                  common_sample_keys=keys["baseline"],comparisons=comparisons,
                  full={k:strip(v) for k,v in full.items()},common={k:strip(v) for k,v in common.items()},diagnostics=diagnostic)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:{n:v for n,v in p.items() if n not in ("per_satellite","determined_in_both")} for k,p in comparisons.items()},indent=2),flush=True)


if __name__ == "__main__": main()
