"""One guarded preparation or nonlinear iteration, with pinned JSON checkpoints.

Each iteration is a separate serial guarded job. No SP3/CLK reads, long-lived
background process, raised OS limits or full clock covariance are needed.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from .stage5_pilot import prepare,Pilot,STATIONS,ORIGIN,forbid_precise_product_reads
from .prepare_stage2 import ROOT,DATA as DYN,sha
from .prepare_stage3 import DATA
from .frames import FrameEpoch,EarthOrientation,Environment
from .ephemeris import DE440
from .orbit_forces import OrbitForceModel
from .antenna import load_calibrations
from .rinex import read_gps_navigation
from .reduced_network import reduced_qr,budget
from .nonlinear_stop import model_reduction,stationary


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item())+"\n")


def freeze(context,rows,seeds,path,case):
    simple={k:context[k] for k in ("stations","inputs","rejected_satellites","duration_s","epoch_count","step_s","profile","navigation_cutoff_ns")}
    write_json(path,{"case":case,"context":simple,"rows":rows,"seeds":seeds})


def restore(path):
    obj=json.loads(path.read_text());context=obj["context"]
    for name,digest in context["inputs"].items():
        if sha(ROOT/name)!=digest:raise ValueError("Input hash changed: "+name)
    epoch=FrameEpoch(ORIGIN,EarthOrientation(DYN/"finals2000A.all"));ephemeris=DE440(DYN/"de440s.bsp")
    context.update(epoch=epoch,ephemeris=ephemeris,model=OrbitForceModel(Environment(epoch,ephemeris,context["duration_s"]),DYN/"EGM2008_degree12.gfc"))
    context["records"]=read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    context["sat_cal"],context["rx_cal"]=load_calibrations(DATA/"igs20.atx",[m["header"]["antenna"] for m in context["stations"].values()],ORIGIN)
    rows=obj["rows"]
    for row in rows:
        for key in ("receiver_xyz","observation","sigma"):row[key]=np.array(row[key])
    return context,rows,{s:np.array(x) for s,x in obj["seeds"].items()}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=("eight-short","eight-long","expanded-long","yell-long","guam-long"),required=True)
    parser.add_argument("--fixture",type=Path)
    parser.add_argument("--previous",type=Path)
    args=parser.parse_args();folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    sys.addaudithook(forbid_precise_product_reads)
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}
    if args.fixture is None:
        stations=list(STATIONS)+(["DAV1","FALK","FAA1","GLPS"] if args.case in ("expanded-long","yell-long","guam-long") else [])
        if args.case in ("yell-long","guam-long"):stations.append("YELL")
        if args.case=="guam-long":stations.append("GUAM")
        context,rows,seeds=prepare(epoch_count=12 if args.case=="eight-short" else 37,station_subset=stations,profile="nominal-multihour")
        freeze(context,rows,seeds,folder/"fixture.json",args.case)
        pilot=Pilot(context,rows,seeds)
        counts={};phase=0
        for row in rows:counts[row["arc"]]=counts.get(row["arc"],0)+1
        phase=sum(v for v in counts.values() if v>=3)
        # Preflight dimensions before allocating all observation Jacobian blocks.
        # Empty/fake linear blocks are unnecessary: use actual counts and the
        # same conservative allocation formula as reduced_network.budget.
        m=len(rows)+phase+len(pilot.prior_sigma)+len(stations)
        n=pilot.n;local=sum(map(len,pilot.local_names));largest=max(sum((2 if r["arc"] in pilot.arcs else 1) for r in rows if r["epoch"]==ei) for ei in range(pilot.epoch_count))
        workspace=8*(5*m*n+4*largest**2+3*local*n+6*n*n)
        from .reduced_network import WORKSPACE_BYTES,MAX_ROWS,MAX_PARAMETERS
        if m>MAX_ROWS or n>MAX_PARAMETERS or workspace>WORKSPACE_BYTES:raise ValueError("Preflight workspace/row/retained-column budget exceeded")
        product=pilot.products(np.zeros(len(pilot.names)));times=np.arange(10.,context["duration_s"]-9.,300.)
        np.savez_compressed(folder/"initial.npz",states=np.array([[product.state(s,t) for t in times] for s in pilot.sats]),satellites=np.array(pilot.sats),times_s=times)
        used_nav=[]
        for sat in pilot.sats:
            for t in times:
                record=product.record(sat,t-.1)
                used_nav.append((sat,record["gps_ns"],record.get("transmission_time")))
        used_nav=sorted(set(used_nav))
        report={"status":"prepared","case":args.case,"stations":stations,"satellites":pilot.sats,"code_rows":len(rows),"phase_rows":phase,"retained_parameters":n,"local_clock_parameters":local,"workspace_estimate_mib":workspace/2**20,"fixture_sha256":sha(folder/"fixture.json"),"source_sha256":sources,"navigation_records_used":used_nav,"unknown_navigation_receipt_records":sum(v[2] in (None,0.) for v in used_nav),"rapid_vintage_certified":False,"station_signal_pairs":{s:m["header"]["types"]["G"] for s,m in context["stations"].items()}}
        write_json(folder/"step.json",report)
        print(json.dumps({k:v for k,v in report.items() if k not in ("source_sha256","station_signal_pairs","navigation_records_used")},indent=2),flush=True)
        return
    fixture_report=json.loads((args.fixture.parent/"step.json").read_text())
    if fixture_report["case"]!=args.case or sha(args.fixture)!=fixture_report["fixture_sha256"]:raise ValueError("Changed/wrong fixture")
    for name,digest in fixture_report["source_sha256"].items():
        if sha(ROOT/name)!=digest:raise ValueError("Source changed since fixture: "+name)
    context,rows,seeds=restore(args.fixture);pilot=Pilot(context,rows,seeds)
    x=np.zeros(len(pilot.names));history=[]
    if args.previous:
        prior=json.loads((args.previous/"step.json").read_text())
        if prior["fixture_sha256"]!=sha(args.fixture) or sha(args.previous/"solution.npz")!=prior["solution_sha256"]:raise ValueError("Changed previous checkpoint")
        saved=np.load(args.previous/"solution.npz");np.testing.assert_array_equal(saved["names"],pilot.names)
        x=saved["x"].copy();history=prior["history"]
    begin=time.perf_counter()
    blocks,constraints,residual,sigma,_,cost,products=pilot.evaluate(x)
    print(f"Jacobian: {len(residual)} observations, retained {pilot.n}, total {len(pilot.names)}",flush=True)
    solution=reduced_qr(blocks,constraints);step=solution.estimate
    bound=max(np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]:pilot.index[f"orbit:{s}:0"]+3])+pilot.duration*np.linalg.norm(step[pilot.index[f"orbit:{s}:0"]+3:pilot.index[f"orbit:{s}:0"]+6]) for s in pilot.sats)
    reduction,dnorm=model_reduction(blocks,constraints,step)
    stopped=stationary(bound,cost,reduction,dnorm)
    accepted=False
    if stopped:
        # Keep the last accepted iterate. Do not accept a worse trial simply
        # because nonlinear residual evaluation has reached its precision floor.
        alpha=0.;cost2=cost;r2=residual;accepted=True
    else:
        for alpha in (1.,.5,.25,.125):
            trial=x+alpha*step
            _,_,r2,sigma,_,cost2,products=pilot.evaluate(trial,jacobian=False)
            if cost2<=cost+max(1e-6,1e-9*cost):accepted=True;x=trial;break
    converged=stopped or (accepted and bound<.001 and abs(cost2-cost)<max(1e-5,1e-8*cost))
    history.append({"iteration":len(history),"cost_before":cost,"cost_after":cost2,"accepted":accepted,"update_applied":accepted and not stopped,"termination":"small_step_and_linearized_progress" if stopped else "line_search","predicted_reduction":reduction,"whitened_direction_norm_squared":dnorm,"step_fraction":alpha,"trajectory_step_bound_m":bound,"seconds":time.perf_counter()-begin})
    if not accepted:raise RuntimeError("No accepted nonlinear step; no solution checkpoint written")
    times=np.arange(10.,context["duration_s"]-9.,300.)
    np.savez_compressed(folder/"solution.npz",x=x,names=np.array(pilot.names),states=np.array([[products.state(s,t) for t in times] for s in pilot.sats]),satellites=np.array(pilot.sats),times_s=times,residual_m=r2,sigma_m=sigma,retained_covariance=solution.retained_covariance)
    report={"status":"converged" if converged else "iteration_complete","case":args.case,"history":history,"fixture_sha256":sha(args.fixture),"solution_sha256":sha(folder/"solution.npz"),"workspace_estimate_mib":solution.workspace_estimate_bytes/2**20,"source_sha256":sources,"precise_products_used":False,"retained_covariance_at":"pre-step linearization; diagnostic only"}
    write_json(folder/"step.json",report)
    print(json.dumps({k:v for k,v in report.items() if k!="source_sha256"},indent=2),flush=True)


if __name__=="__main__":main()
