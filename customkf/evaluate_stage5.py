"""Post-fit evaluator only: exact common epochs against IGS rapid, no feedback.

Reads completed pilot arrays in a separate guarded process. It never alters
estimates or chooses priors using the score. This tiny sample is diagnostic.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from .prepare_stage2 import ROOT, DATA as DYN, sha
from .prepare_stage3 import DATA
from .precise import PreciseProducts
from .sp3 import read_sp3
from .frames import EarthOrientation
from .stage5_pilot import ORIGIN
from .comparison import rac_difference, summarize


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    archive=parser.parse_args().archive
    baseline=np.load(archive/"real/pilot.npz")
    perturbed=np.load(archive/"perturbed/pilot.npz")
    weak=np.load(archive/"weak-prior/pilot.npz")
    for other in (perturbed,weak):
        for key in ("names","times_s","satellites","seed_states"):
            np.testing.assert_array_equal(baseline[key],other[key])
    delta=perturbed["states"][:,:,:3]-baseline["states"][:,:,:3]
    sensitivity=weak["states"][:,:,:3]-baseline["states"][:,:,:3]
    report={"scope":"Post-fit diagnostic, all raw differences retained; not Stage 5 accuracy acceptance",
        "fitted_arrays_sha256":{str(p.relative_to(ROOT)):sha(p) for p in archive.glob("*/pilot.npz")},
        "perturbed_start_max_position_difference_m":float(np.max(np.linalg.norm(delta,axis=2))),
        "prior_change_trajectory_3d_rms_m":float(np.sqrt(np.mean(np.sum(sensitivity**2,axis=2)))),
        "prior_change_max_trajectory_difference_m":float(np.max(np.linalg.norm(sensitivity,axis=2)))}
    reference=DATA/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
    manifest=json.loads((DATA/"manifest.json").read_text())
    expected=next(f["sha256"] for f in manifest["files"] if f["path"]==reference.relative_to(ROOT).as_posix())
    if sha(reference)!=expected:raise ValueError("Changed evaluator reference")
    raw=read_sp3(reference)
    if raw.frame!="IGc20":raise ValueError("Unexpected reference frame")
    precise=PreciseProducts([reference],[],ORIGIN,EarthOrientation(DYN/"finals2000A.all"))
    weak_report=json.loads((archive/"weak-prior/pilot.json").read_text())
    report["weak_prior_converged"]=weak_report["converged"]
    report["prior_comparison_scope"]="Final stored iterates; weak-prior convergence status explicit, not necessarily two stationary solutions"
    differences={name:[] for name in ("fit","weak_prior_iterate")}
    excluded=[]
    for si,sat in enumerate(baseline["satellites"]):
        for ti,t in enumerate(baseline["times_s"]):
            tag=ORIGIN+int(round(t*1e9))
            row=raw.samples.get((tag,str(sat)))
            if row is None:continue  # exact common epochs only; no position interpolation
            if row.xyz_m is None or row.maneuver or row.orbit_predicted:
                excluded.append([str(sat),int(tag),"invalid or flagged reference"]);continue
            rotation=precise.epoch.celestial_to_terrestrial(t)
            ref=rotation.T@row.xyz_m
            velocity=precise.state(str(sat),t)[3:]
            for name,candidate in (("fit",baseline["states"][si,ti,:3]),("weak_prior_iterate",weak["states"][si,ti,:3])):
                differences[name].append(rac_difference(ref,candidate,velocity))
    report.update(reference=str(reference.relative_to(ROOT)),reference_sha256=expected,
        convention="COM; IGc20 reference and fixed station datum; exact GPS epochs; inertial RAC; no alignment, demeaning or residual clipping",
        reference_flag_exclusions=excluded,external_scores={name:summarize(np.array(v)) for name,v in differences.items()})
    report["passed_start_consistency_gate"]=report["perturbed_start_max_position_difference_m"]<.001
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    np.savez_compressed(folder/"comparison.npz",**{name:np.array(v) for name,v in differences.items()})
    print(json.dumps(report,indent=2),flush=True)
    if not report["passed_start_consistency_gate"]:raise AssertionError("Perturbed-start gate failed")


if __name__=="__main__":main()
