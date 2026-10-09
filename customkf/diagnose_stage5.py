"""Bounded attribution of Stage 5a errors; no changes to the fitted estimator.

Run via customkf.guard. Reconstruct the original rows, score each satellite,
compare navigation with an explicitly ANTEX/nominal-yaw corrected reference,
and quantify linearized noise amplification with fixed seeds. Precise products
are evaluator inputs only. White noise is a controlled model, not a claim that
real residuals are independent. Source/input hashes accompany every result.
"""
import json
import os
from pathlib import Path
import numpy as np
from .stage5_pilot import prepare, Pilot, ORIGIN
from .prepare_stage2 import ROOT, sha
from .prepare_stage3 import DATA
from .precise import PreciseProducts
from .sp3 import read_sp3
from .broadcast import select_record, position
from .preprocess import ALPHA, BETA
from .antenna import unit
from .network_square_root import assemble, _factor
from .comparison import rac_difference, summarize

ARCHIVE=ROOT/"validation/stage5/20260909T200136Z"


def offset_inertial(r, sun, calibration):
    """COM -> IF APC under nominal yaw, Navipedia equations (1)-(6)."""
    z=-unit(r); y=unit(np.cross(z,unit(sun-r))); x=np.cross(y,z)
    pco=ALPHA*calibration.frequencies["G01"]["pco"]+BETA*calibration.frequencies["G02"]["pco"]
    return np.c_[x,y,z]@pco


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    context,rows,seeds=prepare()
    pilot=Pilot(context,rows,seeds)
    fitted=np.load(ARCHIVE/"real/pilot.npz")
    np.testing.assert_array_equal(fitted["names"],pilot.names)
    np.testing.assert_array_equal(fitted["seed_states"],np.array([seeds[s] for s in pilot.sats]))
    x0=np.zeros(len(pilot.names))
    blocks,constraints,residual,sigma,modeled,cost,products=pilot.evaluate(x0)
    print("Original rows and derivatives reconstructed",flush=True)
    ref_path=DATA/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
    pin=next(f["sha256"] for f in json.loads((DATA/"manifest.json").read_text())["files"] if f["path"]==ref_path.relative_to(ROOT).as_posix())
    if sha(ref_path)!=pin:raise ValueError("Reference hash mismatch")
    precise=PreciseProducts([ref_path],[],ORIGIN,context["epoch"].eop)
    raw=read_sp3(ref_path)
    if raw.frame!="IGc20":raise ValueError("Reference frame mismatch")
    report={"scope":"Stage 5a attribution; no accuracy acceptance", "inputs":context["inputs"],
        "reference_sha256":pin,"fitted_sha256":sha(ARCHIVE/"real/pilot.npz"),
        "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")},
        "navigation_reference_point":"ANTEX IF offset and nominal yaw applied to precise COM reference; broadcast APC metadata/attitude not independently certified", "satellites":[]}
    all_fit=[];all_nav=[];all_seed=[]
    for si,sat in enumerate(pilot.sats):
        links=[r for r in rows if r["satellite"]==sat]
        counts=[len({r["station"] for r in links if r["epoch"]==ei}) for ei in range(12)]
        rf=[];rn=[];rs=[];offsets=[]
        for ti,t in enumerate(fitted["times_s"]):
            tag=ORIGIN+int(round(t*1e9)); sample=raw.samples.get((tag,sat))
            if sample is None or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:continue
            rotation=context["epoch"].celestial_to_terrestrial(t)
            r=rotation.T@sample.xyz_m;v=precise.state(sat,t)[3:]
            sun,_=context["ephemeris"].sun_moon_m(context["epoch"].tdb_seconds(t))
            offset=offset_inertial(r,sun,context["sat_cal"][sat])
            nav=rotation.T@position(select_record(context["records"][sat],tag),tag)
            rf.append(rac_difference(r,fitted["states"][si,ti,:3],v))
            # Equivalently nav minus (IGS COM + nominal IF APC offset).
            rn.append(rac_difference(r,nav-offset,v))
            rs.append(rac_difference(r,products.state(sat,t)[:3],v))
            offsets.append(float(np.linalg.norm(offset)))
        all_fit.extend(rf);all_nav.extend(rn);all_seed.extend(rs)
        report["satellites"].append({"satellite":sat,"stations":sorted({r["station"] for r in links}),
            "links":len(links),"receiver_counts_per_epoch":counts,
            "fit":summarize(np.array(rf)),"navigation_apc_matched":summarize(np.array(rn)),
            "integrated_uncorrected_seed":summarize(np.array(rs)),"if_pco_norm_m":max(offsets)})
    report["aggregate"]={"fit":summarize(np.array(all_fit)),"navigation_apc_matched":summarize(np.array(all_nav)),"integrated_uncorrected_seed":summarize(np.array(all_seed))}
    total=sum(s["fit"]["samples"]*s["fit"]["rms_3d_m"]**2 for s in report["satellites"])
    for s in report["satellites"]:s["squared_error_share"]=s["fit"]["samples"]*s["fit"]["rms_3d_m"]**2/total
    report["satellites"].sort(key=lambda s:s["fit"]["rms_3d_m"],reverse=True)
    a,y,weights=assemble(blocks,constraints)
    q,mapping=_factor(a/weights[:,None])
    nobs=len(residual)
    response=mapping@q[:nobs].T # maps observation noise divided by sigma
    rng=np.random.default_rng(98231)
    draws=128
    z=rng.standard_normal((nobs,draws))
    error=response@z
    # Fixed truth/prior centres: perturb only observations, never prior rows.
    per_sat=[];all_displacements=[]
    for sat in pilot.sats:
        k=pilot.index[f"orbit:{sat}:0"]
        d=np.array([products.trajectories[sat].partial(t)[:3]@error[k:k+6] for t in fitted["times_s"]])
        per_sat.append({"satellite":sat,"rms_3d_m":float(np.sqrt(np.mean(np.sum(d*d,axis=1))))})
        all_displacements.append(d)
    displacements=np.array(all_displacements) # satellite,time,xyz,draw
    rms=np.sqrt(np.mean(np.sum(displacements**2,axis=2),axis=(0,1)))
    report["noise_experiment"]={"type":"Linearized Monte Carlo, fixed true orbit/wet prior centres, Gaussian independent observation noise only",
        "seed":98231,"draws":draws,"code_zenith_sigma_m":.9,"phase_zenith_sigma_m":.009,
        "elevation_weight":"1/sin(elevation)","network_3d_rms_median_m":float(np.median(rms)),
        "network_3d_rms_5_95_m":np.percentile(rms,[5,95]).tolist(),
        "three_tenths_noise_rms_median_m":float(.3*np.median(rms)),"per_satellite":per_sat}
    # Same seed realization is consumed by the independent nonlinear experiment.
    np.savez_compressed(folder/"noise.npz",observations=modeled+sigma*z[:,0],linear_step=error[:,0],names=np.array(pilot.names),
        truth_states=np.array([[products.state(s,t) for t in fitted["times_s"]] for s in pilot.sats]),times_s=fitted["times_s"],linear_network_rms_m=rms)
    (folder/"diagnosis.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"aggregate":report["aggregate"],"worst_satellites":report["satellites"][:6],"noise":{k:v for k,v in report["noise_experiment"].items() if k!="per_satellite"}},indent=2),flush=True)


if __name__=="__main__":main()
