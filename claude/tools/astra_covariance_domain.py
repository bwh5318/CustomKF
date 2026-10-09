"""Guarded, reference-free audit of the archived expanded orbit covariance.

Run from the project root:
    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.astra_covariance_domain

Checks named covariance indices, PSD, initial STM identity, trajectory agreement,
and full-arc propagation including velocity/cross terms. No reclassification,
IGS score, new orbit solve or calibrated confidence-interval claim is made.
"""
import json
import os
from pathlib import Path
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT,sha
from customkf.stage5b_step import restore
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.dynamic_observation import Trajectory

ARCHIVE=ROOT/"validation/stage5b/20260910T203254Z/completion-20260910T205844Z"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    manifest=json.loads((ARCHIVE/"validation.json").read_text())
    # The sole pre-existing source changed for the new PPP station profile is
    # outside this dynamic/covariance audit's calculation path. Preserve evidence.
    changed={}
    for name,digest in manifest["source_sha256"].items():
        current=sha(ROOT/name)
        if current!=digest:
            if name!="customkf/run_stage3.py":raise ValueError("Unexpected archived-model source change: "+name)
            changed[name]={"archive":digest,"current":current,"reason":"New PPP station input profile; not called by this audit"}
    solution_path=ARCHIVE/"expanded-long-final/solution.npz"
    fixture_path=ARCHIVE/"expanded-long-prepare/fixture.json"
    for path in (solution_path,fixture_path):
        assert sha(path)==manifest["artifacts_sha256"][path.relative_to(ARCHIVE).as_posix()]
    saved=np.load(solution_path);cov=saved["retained_covariance"]
    names=list(saved["names"]);n=len(cov)
    assert cov.shape==(n,n) and all(not name.startswith("clock:") for name in names[:n])
    assert all(name.startswith("clock:") for name in names[n:]) and len(set(names))==len(names)
    np.testing.assert_allclose(cov,cov.T,rtol=0,atol=1e-9)
    assert np.isfinite(cov).all() and np.all(np.diag(cov)>0)
    scales=np.sqrt(np.diag(cov));correlation=cov/scales[:,None]/scales[None,:]
    eigen=np.linalg.eigvalsh((correlation+correlation.T)/2)
    assert eigen[0]>=-1e-10
    context,rows,seeds=restore(fixture_path)
    result={}
    for si,sat in enumerate(saved["satellites"]):
        indices=[names.index(f"orbit:{sat}:{k}") for k in range(6)]
        assert max(indices)<n and indices==list(range(indices[0],indices[0]+6))
        c0=cov[np.ix_(indices,indices)]
        lower=np.linalg.cholesky((c0+c0.T)/2)
        trajectory=Trajectory(seeds[str(sat)]+saved["x"][indices],context["model"],context["duration_s"])
        np.testing.assert_allclose(trajectory.partial(0),np.eye(6),rtol=0,atol=1e-12)
        sigma0=float(np.sqrt(np.trace(c0[:3,:3])))
        times=saved["times_s"];values=[];maximum_difference=0.
        for ti,t in enumerate(times):
            state=trajectory.state(float(t))
            difference=float(np.max(abs(state-saved["states"][si,ti])))
            maximum_difference=max(maximum_difference,difference)
            np.testing.assert_allclose(state,saved["states"][si,ti],rtol=0,atol=1e-7)
            phi=trajectory.partial(float(t))[:3]
            propagated=phi@c0@phi.T
            root=phi@lower
            sigma=float(np.sqrt(np.trace(propagated)))
            np.testing.assert_allclose(sigma,np.linalg.norm(root),rtol=2e-10,atol=1e-9)
            values.append(sigma)
        observed={r["epoch"] for r in rows if r["satellite"]==sat}
        by_epoch={e:{r["station"] for r in rows if r["satellite"]==sat and r["epoch"]==e} for e in observed}
        scored_indices=[i for i,t in enumerate(times) if abs((float(t)-10)%900)<1e-8]
        result[str(sat)]={"initial_position_root_trace_m":sigma0,
            "frozen_initial_sigma_class":"determined" if sigma0<=10 else "poorly_determined",
            "all_solve_epochs_position_root_trace_m":values,
            "scored_epochs_position_root_trace_m":[values[i] for i in scored_indices],
            "score_epoch_indices":scored_indices,
            "full_arc_root_trace_min_max_m":[min(values),max(values)],
            "score_epochs_outside_observation_span":[i for i in scored_indices if not observed or i<min(observed) or i>max(observed)],
            "two_receiver_epochs":sum(len(stations)>=2 for stations in by_epoch.values()),
            "max_recomputed_state_component_difference_SI":maximum_difference}
        print(f"{sat}: initial sigma {sigma0:.3f} m; arc {min(values):.3f}..{max(values):.3f} m",flush=True)
    report={"status":"covariance_mapping_and_propagation_verified_not_uncertainty_calibrated",
            "retained_covariance_shape":list(cov.shape),"scaled_correlation_min_eigenvalue":float(eigen[0]),
            "satellites":result,"times_s":saved["times_s"].tolist(),"allowed_source_changes":changed,
            "input_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (solution_path,fixture_path)},
            "tool_sha256":sha(Path(__file__)),"precise_products_read":False,
            "note":"Marginal covariance includes orbit priors and assumed weights, with velocity/cross terms propagated. Fixed empirical-force and external model uncertainties are absent. Frozen classifier unchanged."}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"covariance.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":main()
