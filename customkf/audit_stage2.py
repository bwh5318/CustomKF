"""Independent full-arc variational checks using the real Stage 2 force model."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from .prepare_stage2 import DATA
from .ephemeris import DE440
from .frames import EarthOrientation, FrameEpoch, Environment
from .orbit_forces import OrbitForceModel
from .propagation import IntegrationSettings, propagate


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fits",nargs=2,type=Path)
    args=parser.parse_args()
    report={"checks":[],"horizons_de441_difference_m":{}}
    ephemeris=DE440(DATA/"de440s.bsp")
    for name,position in zip(("sun","moon"),ephemeris.sun_moon_m((2461254.5-2451545.)*86400)):
        row=(DATA/f"horizons_{name}.txt").read_text().split("$$SOE\n")[1].splitlines()[0].split(",")
        report["horizons_de441_difference_m"][name]=float(np.linalg.norm(position-np.array(row[2:5],dtype=float)*1000))
    for folder in args.fits:
        fit=json.loads((folder/"fit.json").read_text())
        data=np.load(folder/"orbit.npz")
        times=(data["gps_epoch_ns"]-data["gps_epoch_ns"][0])/1e9
        epoch=FrameEpoch(int(data["gps_epoch_ns"][0]),EarthOrientation(DATA/"finals2000A.all"))
        environment=Environment(epoch,ephemeris,float(times[-1]))
        model=OrbitForceModel(environment,DATA/"EGM2008_degree12.gfc",fit["ecom_parameters"])
        state=np.array(fit["iterations"][-1]["initial_state"])
        p=np.array([fit["parameters"][name] for name in model.parameter_names])
        settings=IntegrationSettings(max_step_s=30,rtol=1e-13,position_atol_m=1e-8,
                                     velocity_atol_mps=1e-12,scaled_partial_atol=1e-14)
        base=propagate(state,times,model,p,settings=settings)
        dx=np.array([10.,-7.,4.,.001,-.0006,.0003])
        dp=np.array([1.,-2.,3.,-1.,2.])*1e-10
        linear=np.einsum("nij,j->ni",base.state_transition,dx)+np.einsum("nij,j->ni",base.parameter_sensitivity,dp)
        rows=[]
        for factor in (1.,.1):
            plus=propagate(state+factor*dx,times,model,p+factor*dp,settings=settings,partials=False)
            minus=propagate(state-factor*dx,times,model,p-factor*dp,settings=settings,partials=False)
            discrepancy=((plus.states_m_mps-minus.states_m_mps)/2-factor*linear)[:,:3]
            norms=np.linalg.norm(discrepancy,axis=1)
            rows.append({"factor":factor,"rms_m":float(np.sqrt(np.mean(norms**2))),"max_m":float(max(norms))})
        check={"satellite":fit["satellite"],"combined_direction_trials":rows,
               "pass":all(r["rms_m"]<.001 and r["max_m"]<.003 for r in rows)}
        report["checks"].append(check)
        print(json.dumps(check),flush=True)
    report["status"]="pass" if all(c["pass"] for c in report["checks"]) else "fail"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"audit.json").write_text(json.dumps(report,indent=2)+"\n")
    if report["status"]!="pass":raise RuntimeError("Full-arc derivative gate failed")


if __name__=="__main__":main()
