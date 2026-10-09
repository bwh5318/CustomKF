"""Guarded arc/cadence preparation, invariance gates and single fit iteration."""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT,sha
from customkf.stage5_pilot import prepare,forbid_precise_product_reads
from customkf.stage5b_step import freeze,restore
from customkf.reduced_network import MAX_ROWS,MAX_PARAMETERS,WORKSPACE_BYTES
from claude.tools.arc_pilot import ArcPilot
from claude.tools import ablation_step as engine

BASE=ROOT/"validation/guam/20260911T155927Z"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("prepare","iterate"))
    parser.add_argument("--case",choices=("oracle","three","six"),required=True)
    parser.add_argument("--fixture",type=Path);parser.add_argument("--previous",type=Path)
    args=parser.parse_args();folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    sys.addaudithook(forbid_precise_product_reads)
    if args.mode=="iterate":
        engine.build_pilot=lambda path:ArcPilot(*restore(path))
        engine.iterate(argparse.Namespace(fixture=args.fixture,previous=args.previous),folder)
        return
    original=json.loads((BASE/"prepare/fixture.json").read_text())
    context,rows,seeds=prepare(step_s=300 if args.case=="oracle" else 600,
        epoch_count=19 if args.case=="three" else 37,station_subset=list(original["context"]["stations"]),
        profile="nominal-multihour" if args.case=="oracle" else "nominal-cadence")
    fixture=folder/"fixture.json";freeze(context,rows,seeds,fixture,args.case)
    fresh=json.loads(fixture.read_text())
    assert fresh["seeds"]==original["seeds"],"Satellite eligibility or original broadcast seeds changed"
    assert fresh["context"]["stations"]==original["context"]["stations"]
    assert fresh["context"]["inputs"]==original["context"]["inputs"]
    old_rows=[r for r in original["rows"] if args.case=="oracle" or r["epoch"]%2==0]
    prefix=[r for r in fresh["rows"] if r["time_s"]<=10810]
    assert len(prefix)==len(old_rows),"Common-interval selection changed"
    max_sigma=0.
    for old,new in zip(old_rows,prefix):
        for key in old:
            if key=="epoch":assert new[key]==old[key]//(1 if args.case=="oracle" else 2)
            elif key=="sigma":
                np.testing.assert_allclose(new[key],old[key],rtol=0,atol=1e-9)
                max_sigma=max(max_sigma,float(np.max(abs(np.array(new[key])-old[key]))))
            else:assert new[key]==old[key],key
    if args.case=="oracle":assert fresh==original|{"case":"oracle"}
    pilot=ArcPilot(context,rows,seeds)
    code=len(rows);phase=sum(1 for r in rows if r["arc"] in pilot.arcs)
    prior_rows=len(pilot.prior_sigma)+len(pilot.stations)*(2 if pilot.extended else 1)
    m=code+phase+prior_rows;n=pilot.n;local=sum(map(len,pilot.local_names))
    largest=max(sum(2 if r["arc"] in pilot.arcs else 1 for r in rows if r["epoch"]==ei) for ei in range(pilot.epoch_count))
    workspace=8*(5*m*n+4*largest**2+3*local*n+6*n*n)
    report={"status":"prepared","case":args.case,"source_sha256":engine.sources(),"fixture_sha256":sha(fixture),
            "code_rows":code,"phase_rows":phase,"prior_rows":prior_rows,"retained_parameters":n,"local_clock_parameters":local,
            "workspace_estimate_mib":workspace/2**20,"common_prefix_rows":len(prefix),"max_prefix_sigma_difference_m":max_sigma,
            "native_slip_tracking_retained":True,"satellites":pilot.sats,"rejected_satellites":context["rejected_satellites"],
            "wet_node_hours":[0,3,6] if pilot.extended else [0,3],"precise_products_used":False,
            "budget_pass":m<=MAX_ROWS and n<=MAX_PARAMETERS and workspace<=WORKSPACE_BYTES}
    (folder/"step.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="source_sha256"},indent=2),flush=True)
    if not report["budget_pass"]:raise RuntimeError("Preflight budget failed; do not raise limits")
    product=pilot.products(np.zeros(len(pilot.names)));times=np.arange(10.,pilot.duration-9.,300.)
    states=np.array([[product.state(s,t) for t in times] for s in pilot.sats])
    if args.case in ("oracle","three"):
        old=np.load(BASE/"prepare/initial.npz")
        np.testing.assert_array_equal(states,old["states"])
    np.savez_compressed(folder/"initial.npz",states=states,times_s=times,satellites=np.array(pilot.sats))


if __name__=="__main__":main()
