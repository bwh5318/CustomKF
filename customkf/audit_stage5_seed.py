"""Separate evaluator: distinguish old broadcast record, COM offset and propagation."""
import json
import os
from pathlib import Path
import numpy as np
from .prepare_stage2 import ROOT, DATA as DYN, sha
from .prepare_stage3 import DATA
from .stage5_pilot import ORIGIN, DURATION
from .frames import FrameEpoch, EarthOrientation, Environment
from .ephemeris import DE440
from .orbit_forces import OrbitForceModel
from .dynamic_observation import Trajectory
from .broadcast import select_record, position, state_inertial
from .rinex import read_gps_navigation
from .precise import PreciseProducts
from .antenna import load_calibrations
from .diagnose_stage5 import offset_inertial, ARCHIVE


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    epoch=FrameEpoch(ORIGIN,EarthOrientation(DYN/"finals2000A.all"))
    ephemeris=DE440(DYN/"de440s.bsp")
    model=OrbitForceModel(Environment(epoch,ephemeris,DURATION),DYN/"EGM2008_degree12.gfc")
    nav=read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    cal,_=load_calibrations(DATA/"igs20.atx",[],ORIGIN)
    reference=DATA/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"
    precise=PreciseProducts([reference],[],ORIGIN,epoch.eop)
    baseline=np.load(ARCHIVE/"real/pilot.npz")
    report={"scope":"Initialization/propagation diagnostic; ANTEX nominal-yaw COM conversion, not certified broadcast antenna metadata", "satellites":[]}
    for sat in baseline["satellites"]:
        sat=str(sat);rec=select_record(nav[sat],ORIGIN)
        def old_apc(t):return epoch.celestial_to_terrestrial(t).T@position(rec,ORIGIN+int(round(t*1e9)))
        def com(t):
            apc=old_apc(t)
            sun,_=ephemeris.sun_moon_m(epoch.tdb_seconds(t))
            r=apc.copy()
            for _ in range(3):r=apc-offset_inertial(r,sun,cal[sat])
            return r
        initial=state_inertial(rec,epoch,ORIGIN)
        corrected=np.r_[com(0),(com(.5)-com(-.5))]
        coarse_velocity=(old_apc(5)-old_apc(-5))/10
        trajectory=Trajectory(initial,model,DURATION)
        corrected_trajectory=Trajectory(corrected,model,DURATION)
        rows=[]
        for t in (10.,910.,1810.,2710.):
            ref=precise.state(sat,t)[:3]
            # Preserve the age gate: expired old-record diagnostics are missing,
            # not a reason to extrapolate navigation beyond the declared bound.
            try:
                old_error=float(np.linalg.norm(com(t)-ref))
                drift=float(np.linalg.norm(trajectory.state(t)[:3]-old_apc(t)))
            except ValueError as error:
                if "extrapolation refused" not in str(error):raise
                old_error=drift=None
            rows.append({"time_s":t,"old_record_com_error_m":old_error,
                "integrated_seed_error_m":float(np.linalg.norm(trajectory.state(t)[:3]-ref)),
                "integrated_com_seed_error_m":float(np.linalg.norm(corrected_trajectory.state(t)[:3]-ref)),
                "dynamic_minus_old_broadcast_apc_m":drift})
        report["satellites"].append({"satellite":sat,"toc_age_at_start_s":(ORIGIN-rec["gps_ns"])/1e9,
            "toe_age_at_start_s":ORIGIN/1e9-(rec["week"]*604800+rec["toe"]),
            "broadcast_fit_interval_hours":rec["fit_interval"],"transmission_time_sow":rec["transmission_time"],
            "velocity_half_second_vs_five_second_mps":float(np.linalg.norm(initial[3:]-coarse_velocity)),"rows":rows})
    for name,key in (("old_broadcast_com","old_record_com_error_m"),("original_integrated","integrated_seed_error_m"),("com_integrated","integrated_com_seed_error_m")):
        values=[r[key] for s in report["satellites"] for r in s["rows"] if r[key] is not None]
        report[name+"_rms_m"]=float(np.sqrt(np.mean(np.array(values)**2)))
        report[name+"_sample_count"]=len(values)
    report["reference_sha256"]=sha(reference)
    report["source_sha256"]={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"seed.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("satellites","source_sha256")},indent=2),flush=True)


if __name__=="__main__":main()
