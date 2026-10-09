"""One bounded real-data dynamic-fit experiment; launch with customkf.guard."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import time


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    import numpy as np
    from scipy.interpolate import BarycentricInterpolator
    from .prepare_stage2 import DATA,ROOT,sha
    from .sp3 import read_sp3
    from .ephemeris import DE440
    from .frames import EarthOrientation,FrameEpoch,Environment
    from .orbit_forces import OrbitForceModel,shadow_fraction
    from .fitting import fit_orbit
    from .propagation import propagate,IntegrationSettings
    from .comparison import rac_difference,summarize
    from .export_stage2 import write_fit_sp3
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sat",choices=["G08","G01"],default="G08")
    parser.add_argument("--ecom",type=int,choices=[5,7],default=5)
    parser.add_argument("--max-iterations",type=int,default=6)
    parser.add_argument("--no-tides",action="store_true")
    args=parser.parse_args()
    if not 1<=args.max_iterations<=8:raise ValueError("Iteration cap is 8")
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    source=ROOT/"data/stage0/IGS0OPSFIN_20262140000_01D_15M_ORB.SP3"
    reference_entry=next(e for e in json.loads((ROOT/"data/stage0/manifest.json").read_text())["sp3"]
                         if e["local_path"]==source.relative_to(ROOT).as_posix())
    if sha(source)!=reference_entry["sha256"]:raise ValueError("Changed reference SP3")
    for entry in json.loads((DATA/"manifest.json").read_text())["files"]:
        if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Changed model data")
    product=read_sp3(source)
    records=sorted([s for s in product.samples.values() if s.sat==args.sat],key=lambda s:s.epoch_ns)
    if len(records)!=96 or any(s.xyz_m is None or s.maneuver or s.orbit_predicted for s in records):
        raise ValueError("Development arc changed or has flagged/missing orbit records")
    times=np.array([(s.epoch_ns-records[0].epoch_ns)/1e9 for s in records])
    terrestrial=np.array([s.xyz_m for s in records])
    epoch=FrameEpoch(records[0].epoch_ns,EarthOrientation(DATA/"finals2000A.all"))
    ephemeris=DE440(DATA/"de440s.bsp")
    rotations=np.array([epoch.celestial_to_terrestrial(t) for t in times])
    positions=np.einsum("nji,nj->ni",rotations,terrestrial)
    started=time.perf_counter()
    environment=Environment(epoch,ephemeris,times[-1])
    model=OrbitForceModel(environment,DATA/"EGM2008_degree12.gfc",args.ecom,solid_earth=not args.no_tides)
    train=(np.arange(96)<88)&(np.arange(96)%5!=2)
    validation=(np.arange(96)<88)&~train
    forecast=np.arange(96)>=88
    report={"status":"running","satellite":args.sat,"date_gpst":"2026-08-02","ecom_parameters":args.ecom,
        "solid_earth_nominal":not args.no_tides,"reference_sha256":sha(source),"frame":product.frame,
        "training_indices":np.where(train)[0].tolist(),"withheld_interior_indices":np.where(validation)[0].tolist(),
        "withheld_end_indices":np.where(forecast)[0].tolist(),"iterations":[],
        "omissions":["solid tide frequency corrections","ocean and pole tides","subdaily EOP tides",
                     "Earth radiation and antenna thrust","SVN-specific physical attitude/box-wing","planetary third bodies beyond Sun/Moon"]}
    def checkpoint(row):
        report["iterations"].append(row)
        (folder/"fit.json").write_text(json.dumps(report,indent=2)+"\n")
        print(f"{args.sat} ECOM{args.ecom} iteration {row['iteration']}: {row['training_rms_before_m']:.6f} -> {row['training_rms_after_m']:.6f} m",flush=True)
    print(f"Environment ready; fitting {sum(train)} epochs, withholding {sum(validation)} interior + {sum(forecast)} endpoint epochs",flush=True)
    settings=IntegrationSettings(rtol=1e-12,position_atol_m=1e-7,velocity_atol_mps=1e-11,scaled_partial_atol=1e-13)
    fitted=fit_orbit(times[train],positions[train],model,max_iterations=args.max_iterations,callback=checkpoint,settings=settings)
    solution=propagate(fitted.initial_state,times,model,fitted.parameters,settings=settings)
    tighter=propagate(fitted.initial_state,times,model,fitted.parameters,settings=replace(settings,max_step_s=60,rtol=3e-13),partials=False)
    refinement=np.linalg.norm(solution.states_m_mps[:,:3]-tighter.states_m_mps[:,:3],axis=1)
    velocity=[]
    for i,t in enumerate(times):
        first=min(max(i-4,0),len(times)-9);x=(times[first:first+9]-t)/1000.
        w=np.array([1/np.prod(x[k]-np.delete(x,k)) for k in range(len(x))])
        velocity.append(BarycentricInterpolator(x,positions[first:first+9],wi=w,axis=0).derivative(0.)/1000.)
    rac=rac_difference(positions,solution.states_m_mps[:,:3],np.array(velocity))
    for name,mask in (("training",train),("withheld_interior",validation),("withheld_end",forecast),("all",np.ones(96,dtype=bool))):
        report[name]=summarize(rac[mask])
    shadows=np.array([shadow_fraction(x,environment.at(t)[1]) for t,x in zip(times,solution.states_m_mps[:,:3])])
    error_3d=np.linalg.norm(solution.states_m_mps[:,:3]-positions,axis=1)
    report.update(converged=fitted.converged,rank=fitted.rank,parameters=dict(zip(model.parameter_names,fitted.parameters)),
        refinement_rms_m=float(np.sqrt(np.mean(refinement**2))),refinement_max_m=float(max(refinement)),
        eclipse_epoch_count=int(sum(shadows<.999999)),max_3d_m=float(max(error_3d)),
        elapsed_s=time.perf_counter()-started,
        status="pass" if fitted.converged and max(refinement)<.003 and np.sqrt(np.mean(refinement**2))<.001
        and report["training"]["rms_3d_m"]<.1 and report["withheld_interior"]["rms_3d_m"]<.1 else "gate_not_met")
    report["status_note"]="Fit/interior gate only; end-of-arc prediction and eclipse limitations reported separately; not observation-derived POD"
    (folder/"fit.json").write_text(json.dumps(report,indent=2)+"\n")
    fitted_terrestrial=np.einsum("nij,nj->ni",rotations,solution.states_m_mps[:,:3])
    np.savez(folder/"orbit.npz",gps_epoch_ns=np.array([s.epoch_ns for s in records],dtype=np.int64),
             states_inertial_m_mps=solution.states_m_mps,positions_terrestrial_m=fitted_terrestrial,
             reference_terrestrial_m=terrestrial,rac_m=rac,training_mask=train,shadow_fraction=shadows)
    write_fit_sp3(folder/f"CKF_{args.sat}_ECOM{args.ecom}.sp3",args.sat,
                  np.array([s.epoch_ns for s in records],dtype=np.int64),fitted_terrestrial,
                  frame=product.frame,predicted=forecast)
    print(json.dumps({key:report[key] for key in ("status","converged","training","withheld_interior","withheld_end","parameters","refinement_max_m","elapsed_s")},indent=2),flush=True)


if __name__=="__main__":main()
