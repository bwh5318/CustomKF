"""Real-force derivative/refinement gate before accepting Stage 5 nonlinear fits."""
import json
import os
from pathlib import Path
import numpy as np
from .stage5_pilot import prepare, Pilot, DURATION, ORIGIN
from .dynamic_observation import Trajectory, DynamicProducts, modeled_link, link_jacobian


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    context,rows,seeds=prepare()
    pilot=Pilot(context,rows,seeds)
    products=pilot.products(np.zeros(len(pilot.names)))
    report={"scope":"Stage 5a real-force corrected-observation derivative closure", "checks":[],"inputs":context["inputs"]}
    delta=np.array([100.,-70.,40.,.01,-.02,.015])
    for sat in ("G01","G08","G12"):
        choices=[r for r in rows if r["satellite"]==sat]
        row=choices[len(choices)//2]
        antenna=context["stations"][row["station"]]["header"]["antenna"]
        rx,satellite=context["rx_cal"][antenna],context["sat_cal"][sat]
        rc,sc,wet,amb=pilot.state_for(np.zeros(len(pilot.names)),row)
        wet=.12
        reference=pilot.windup[id(row)]
        jac,clock_j=link_jacobian(products,row,rx,satellite,context["ephemeris"],rc,sc,wet,amb,reference)
        clock_values=[modeled_link(products,row,rx,satellite,context["ephemeris"],rc+sign*100.,sc,wet,amb,reference)[0] for sign in (1,-1)]
        report.setdefault("receiver_clock_checks",[]).append({"satellite":sat,
            "max_displacement_error_m":float(np.max(np.abs((clock_values[0]-clock_values[1])/2-clock_j*100.)))})
        for scale in (1.,.1):
            values=[]
            for sign in (1,-1):
                trajectories=products.trajectories.copy()
                trajectories[sat]=Trajectory(seeds[sat]+sign*scale*delta,context["model"],DURATION)
                perturbed=DynamicProducts(context["epoch"],ORIGIN,context["records"],trajectories)
                values.append(modeled_link(perturbed,row,rx,satellite,context["ephemeris"],rc,sc,wet,amb,reference)[0])
            error=(values[0]-values[1])/2-jac@(scale*delta)
            report["checks"].append({"satellite":sat,"station":row["station"],"time_s":row["time_s"],
                "perturbation_scale":scale,"code_displacement_error_m":float(error[0]),"phase_displacement_error_m":float(error[1])})
        fine=Trajectory(seeds[sat],context["model"],DURATION,step=7.5)
        times=np.linspace(.125,DURATION-.125,83)
        difference=np.array([products.state(sat,t)[:3]-fine.state(t)[:3] for t in times])
        report.setdefault("interpolation_refinement",[]).append({"satellite":sat,"max_position_difference_m":float(np.max(np.linalg.norm(difference,axis=1)))})
    worst=max(abs(c[k]) for c in report["checks"] for k in ("code_displacement_error_m","phase_displacement_error_m"))
    refinement=max(c["max_position_difference_m"] for c in report["interpolation_refinement"])
    report.update(max_corrected_observation_displacement_error_m=worst,max_interpolation_difference_m=refinement,
                  passed=bool(worst<1e-4 and refinement<1e-4 and max(c["max_displacement_error_m"] for c in report["receiver_clock_checks"])<1e-4))
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"audit.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    if not report["passed"]:
        raise AssertionError("Stage 5 closure/refinement gate failed")


if __name__=="__main__":main()
