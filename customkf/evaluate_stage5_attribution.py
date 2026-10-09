"""Separate guarded IGS evaluator and matched-epoch geometry comparison.

Reads precise products only after the estimator has finished. Accepts an
explicit corrected-fit run directory. No reference data enters estimation.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from .prepare_stage2 import ROOT, DATA as DYN, sha
from .prepare_stage3 import DATA
from .stage5_pilot import ORIGIN
from .frames import FrameEpoch, EarthOrientation
from .precise import PreciseProducts
from .sp3 import read_sp3
from .comparison import rac_difference, summarize
from .diagnose_stage5 import ARCHIVE

CAMPAIGN=ROOT/"validation/stage5/20260909-attribution/20260910T011512Z"


def matched_geometry():
    cases={name:np.load(CAMPAIGN/name/"linear_model.npz") for name in ("baseline","without-koug","longer")}
    satellites=sorted(set.intersection(*(set(c["satellites"]) for c in cases.values())))
    times=sorted(set.intersection(*(set(c["times_s"]) for c in cases.values())))
    results={}
    for name,c in cases.items():
        names=list(c["names"]);sats=list(c["satellites"]);grid=list(c["times_s"])
        noise=[];posterior=[]
        for sat in satellites:
            k=names.index(f"orbit:{sat}:0")
            for t in times:
                phi=c["partials"][sats.index(sat),grid.index(t)]
                noise.append(float(np.sum((phi@c["response"][k:k+6])**2)))
                posterior.append(float(np.sum((phi@c["mapping"][k:k+6])**2)))
        results[name]={"expected_noise_3d_rms_m":float(np.sqrt(np.mean(noise))),
                       "formal_posterior_3d_sigma_m":float(np.sqrt(np.mean(posterior)))}
    return {"satellites":satellites,"times_s":times,"cases":results,
            "limitation":"Matched output epochs/PRNs remove scoring-domain changes; measurement cadence and ambiguity support still differ. Priors are broad assumed uncertainties, not calibrated physical errors.",
            "linear_model_sha256":{n:sha(CAMPAIGN/n/"linear_model.npz") for n in cases}}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-run",type=Path,required=True)
    args=parser.parse_args()
    fit=np.load(args.fit_run/"fix.npz")
    report_fit=json.loads((args.fit_run/"fix.json").read_text())
    if not report_fit["converged"]:raise ValueError("Correction fit did not converge")
    old=np.load(ARCHIVE/"real/pilot.npz")
    np.testing.assert_array_equal(old["satellites"],fit["satellites"])
    np.testing.assert_array_equal(old["times_s"],fit["times_s"])
    np.testing.assert_array_equal(old["names"],fit["names"])
    np.testing.assert_array_equal(old["sigma_m"],fit["sigma_m"])
    epoch=FrameEpoch(ORIGIN,EarthOrientation(DYN/"finals2000A.all"))
    reference=DATA/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
    expected=next(f["sha256"] for f in json.loads((DATA/"manifest.json").read_text())["files"] if f["path"]==reference.relative_to(ROOT).as_posix())
    if sha(reference)!=expected:raise ValueError("Reference hash mismatch")
    precise=PreciseProducts([reference],[],ORIGIN,epoch.eop)
    raw=read_sp3(reference)
    if raw.frame!="IGc20":raise ValueError("Unexpected SP3 frame")
    arrays={"old_fit":[],"corrected_seed":[],"corrected_fit":[]}
    per_sat=[]
    for si,sat in enumerate(fit["satellites"]):
        sub={k:[] for k in arrays}
        for ti,t in enumerate(fit["times_s"]):
            sample=raw.samples.get((ORIGIN+int(round(t*1e9)),str(sat)))
            if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:continue
            ref=epoch.celestial_to_terrestrial(t).T@sample.xyz_m
            vel=precise.state(str(sat),t)[3:]
            for name,state in (("old_fit",old["states"][si,ti]),("corrected_seed",fit["initial_states"][si,ti]),("corrected_fit",fit["states"][si,ti])):
                diff=rac_difference(ref,state[:3],vel)
                arrays[name].append(diff);sub[name].append(diff)
        per_sat.append({"satellite":str(sat),**{k:summarize(np.array(v)) for k,v in sub.items()}})
    aggregate={k:summarize(np.array(v)) for k,v in arrays.items()}
    if any(v["samples"]!=116 for v in aggregate.values()):raise ValueError("Changed common sample count")
    residual=fit["residual_m"];sigma=fit["sigma_m"]
    phase=sigma<.2
    report={"scope":"Attribution completed; orbit accuracy gate remains separate", "aggregate":aggregate,"per_satellite":per_sat,
        "corrected_fit_residual_rms_m":{"code":float(np.sqrt(np.mean(residual[~phase]**2))),"phase":float(np.sqrt(np.mean(residual[phase]**2)))},
        "fit_run":str(args.fit_run.resolve()),"fit_sha256":sha(args.fit_run/"fix.npz"),"fit_report_sha256":sha(args.fit_run/"fix.json"),
        "reference_sha256":expected,"old_fit_sha256":sha(ARCHIVE/"real/pilot.npz"),
        "matched_geometry":matched_geometry(),
        "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("per_satellite","source_sha256")},indent=2),flush=True)


if __name__=="__main__":main()
