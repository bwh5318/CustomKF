"""Separate IGS evaluator for matched station/arc experiments, never estimator input."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from .prepare_stage2 import ROOT,DATA as DYN,sha
from .prepare_stage3 import DATA
from .stage5_pilot import ORIGIN
from .frames import FrameEpoch,EarthOrientation
from .precise import PreciseProducts
from .sp3 import read_sp3
from .comparison import rac_difference,summarize


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("campaign",type=Path);args=parser.parse_args()
    campaign=json.loads((args.campaign/"validation.json").read_text())
    epoch=FrameEpoch(ORIGIN,EarthOrientation(DYN/"finals2000A.all"))
    reference=DATA/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
    pin=next(f["sha256"] for f in json.loads((DATA/"manifest.json").read_text())["files"] if f["path"]==reference.relative_to(ROOT).as_posix())
    if sha(reference)!=pin:raise ValueError("Reference input changed")
    precise=PreciseProducts([reference],[],ORIGIN,epoch.eop);raw=read_sp3(reference)
    if raw.frame!="IGc20":raise ValueError("Unexpected reference frame")
    cases={};references={};residuals={};hashes={}
    for case,finished in campaign["final_steps"].items():
        folder=args.campaign/finished;step=json.loads((folder/"step.json").read_text())
        if step["status"]!="converged":raise ValueError("Cannot score unconverged case as completed")
        fit=np.load(folder/"solution.npz");initial=np.load(args.campaign/(case+"-prepare")/"initial.npz")
        np.testing.assert_array_equal(fit["satellites"],initial["satellites"])
        np.testing.assert_array_equal(fit["times_s"],initial["times_s"])
        cases[case]={}
        for si,sat in enumerate(fit["satellites"]):
            for ti,t in enumerate(fit["times_s"]):
                key=(str(sat),float(t));sample=raw.samples.get((ORIGIN+int(round(t*1e9)),str(sat)))
                if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:continue
                r=epoch.celestial_to_terrestrial(t).T@sample.xyz_m;v=precise.state(str(sat),t)[3:]
                cases[case][key]={"initial":rac_difference(r,initial["states"][si,ti,:3],v),"fit":rac_difference(r,fit["states"][si,ti,:3],v)}
        fixture=json.loads((args.campaign/(case+"-prepare")/"fixture.json").read_text())
        rows=fixture["rows"];counts={}
        for row in rows:counts[row["arc"]]=counts.get(row["arc"],0)+1
        by_station={};k=0
        for ei in range(fixture["context"]["epoch_count"]):
            for row in rows:
                if row["epoch"]!=ei:continue
                for kind in range(2 if counts[row["arc"]]>=3 else 1):
                    by_station.setdefault(row["station"],{"code":[],"phase":[]})["phase" if kind else "code"].append(float(fit["residual_m"][k]));k+=1
        if k!=len(fit["residual_m"]):raise ValueError("Residual label mismatch")
        residuals[case]={s:{kind:{"count":len(v),"rms_m":float(np.sqrt(np.mean(np.array(v)**2)))} for kind,v in kinds.items()} for s,kinds in by_station.items()}
        hashes[case]={"solution":sha(folder/"solution.npz"),"initial":sha(args.campaign/(case+"-prepare")/"initial.npz"),"fixture":sha(args.campaign/(case+"-prepare")/"fixture.json")}
    common=sorted(set.intersection(*(set(values) for values in cases.values())))
    long_common=sorted(set(cases["eight-long"])&set(cases["expanded-long"]))
    def score(values,keys):return {kind:summarize(np.array([values[k][kind] for k in keys])) for kind in ("initial","fit")}
    report={"status":"completed_comparison_not_accuracy_acceptance","reference_sha256":pin,"input_hashes":hashes,
        "common_samples":[list(k) for k in common],"common_scores":{name:score(values,common) for name,values in cases.items()},
        "long_common_samples":[list(k) for k in long_common],"long_common_scores":{name:score(cases[name],long_common) for name in ("eight-long","expanded-long")},
        "full_scores":{name:score(values,sorted(values)) for name,values in cases.items()},
        "per_satellite":{name:{s:score(values,[k for k in sorted(values) if k[0]==s]) for s in sorted({k[0] for k in values})} for name,values in cases.items()},
        "station_residuals":residuals,"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")},
        "limitations":["Fixed ECOM5; no empirical force estimation", "Float ambiguities and broad orbit priors", "Retrospective end-of-day navigation cutoff; receipt vintage not certified", "New stations have input/geometry checks, not independent coordinate validation"]}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ("common_scores","long_common_scores","full_scores")},indent=2),flush=True)


if __name__=="__main__":main()
