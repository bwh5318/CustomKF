"""Paired correction audit with frozen original rows, weights and 29 satellites.

New nominal-fit navigation selection and ANTEX/yaw COM initialization replace
the legacy orbit seeds. Original clock polynomials are retained to isolate the
initial-state/prior-centre correction. Estimator never reads precise products.
Prior sigmas, force model and observations are unchanged. Run under guard.
"""
import json
import os
from pathlib import Path
import sys
import numpy as np
from .stage5_pilot import prepare, Pilot, ORIGIN, forbid_precise_product_reads
from .broadcast import select_fit_record, position
from .diagnose_stage5 import offset_inertial
from .prepare_stage2 import ROOT, sha


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    context,rows,old_seeds=prepare()
    seeds={};selection=[]
    for sat in old_seeds:
        record=select_fit_record(context["records"][sat],ORIGIN,available_before_ns=ORIGIN+int(3320e9))
        def com(t):
            epoch=context["epoch"]
            apc=epoch.celestial_to_terrestrial(t).T@position(record,ORIGIN+int(round(t*1e9)))
            sun,_=context["ephemeris"].sun_moon_m(epoch.tdb_seconds(t))
            r=apc.copy()
            for _ in range(3):r=apc-offset_inertial(r,sun,context["sat_cal"][sat])
            return r
        seeds[sat]=np.r_[com(0),(com(.5)-com(-.5))]
        selection.append({"satellite":sat,"toc_minus_start_s":(record["gps_ns"]-ORIGIN)/1e9,
            "toe_sow":record["toe"],"fit_hours":record["fit_interval"],"transmission_time_sow":record["transmission_time"]})
    pilot=Pilot(context,rows,seeds)
    initial=pilot.products(np.zeros(len(pilot.names)))
    grid=np.arange(10.,3311.,300.)
    initial_states=np.array([[initial.state(s,t) for t in grid] for s in pilot.sats])
    x,history,converged=pilot.solve(max_iterations=5)
    _,_,residual,sigma,_,cost,products=pilot.evaluate(x,jacobian=False)
    report={"converged":converged,"history":history,"cost_with_priors":cost,"selection":selection,
        "scope":"Paired orbit-seed convention correction; original 29 satellites, rows, weights, clock polynomials and 1000 m /1 m/s prior sigmas preserved; prior centres follow corrected seeds",
        "clock_profile":"Legacy epoch clock polynomials intentionally unchanged; this is not a full navigation applicability repair",
        "availability":"Retrospective same-day navigation allowed through arc end; zero transmission tags do not prove receipt; rapid vintage still uncertified",
        "inputs":context["inputs"],"precise_products_used":False,
        "source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}}
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"fix.json").write_text(json.dumps(report,indent=2)+"\n")
    np.savez_compressed(folder/"fix.npz",x=x,names=np.array(pilot.names),satellites=np.array(pilot.sats),times_s=grid,
        initial_states=initial_states,states=np.array([[products.state(s,t) for t in grid] for s in pilot.sats]),residual_m=residual,sigma_m=sigma)
    print(json.dumps({k:v for k,v in report.items() if k not in ("inputs","source_sha256","selection")},indent=2),flush=True)


if __name__=="__main__":main()
