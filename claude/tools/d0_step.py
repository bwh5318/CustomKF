"""Guarded D0 checks/preparation and one inherited batch iteration; no SP3 reads."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import numpy as np
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore
from customkf.prepare_stage2 import ROOT,sha
from customkf.reduced_network import MAX_ROWS,MAX_PARAMETERS,WORKSPACE_BYTES
from claude.tools.d0_pilot import D0Pilot,SCALE
from claude.tools.force_parameter_fit import ForceTrajectory,INITIAL_P
from claude.tools import ablation_step as engine

BASE=ROOT/"claude/runs/20260912T021739Z-arc"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("prepare","iterate"))
    parser.add_argument("--fixture",type=Path);parser.add_argument("--previous",type=Path);args=parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads);folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    if args.mode=="iterate":
        engine.build_pilot=lambda path:D0Pilot(*restore(path));engine.iterate(args,folder);return
    manifest=json.loads((BASE/"validation.json").read_text())
    for name,digest in manifest["source_sha256"].items():assert sha(ROOT/name)==digest,name
    for name in ("six-prepare/fixture.json","six-prepare/initial.npz","six-1/solution.npz","six-1/step.json"):
        assert sha(BASE/name)==manifest["artifacts_sha256"][name],name
    fixture=folder/"fixture.json";shutil.copyfile(BASE/"six-prepare/fixture.json",fixture)
    shutil.copyfile(BASE/"six-prepare/initial.npz",folder/"initial.npz")
    pilot=D0Pilot(*restore(fixture));old=np.load(BASE/"six-1/solution.npz");x=pilot.embed(old)
    rows=pilot.rows;code=len(rows);phase=sum(r["arc"] in pilot.arcs for r in rows)
    priors=len(pilot.prior_sigma)+2*len(pilot.stations);m=code+phase+priors;n=pilot.n;local=sum(map(len,pilot.local_names))
    largest=max(sum(2 if r["arc"] in pilot.arcs else 1 for r in rows if r["epoch"]==ei) for ei in range(pilot.epoch_count))
    workspace=8*(5*m*n+4*largest**2+3*local*n+6*n*n)
    assert m<=MAX_ROWS and n<=MAX_PARAMETERS and workspace<=WORKSPACE_BYTES,(m,n,workspace/2**20)
    _,constraints,residual,sigma,_,cost,products=pilot.evaluate(x,jacobian=False)
    np.testing.assert_array_equal(residual,old["residual_m"]);np.testing.assert_array_equal(sigma,old["sigma_m"])
    original_cost=json.loads((BASE/"six-1/step.json").read_text())["history"][-1]["cost_after"]
    np.testing.assert_allclose(cost,original_cost,rtol=0,atol=1e-10)
    for si,sat in enumerate(pilot.sats):
        np.testing.assert_array_equal(np.array([products.state(sat,t) for t in old["times_s"]]),old["states"][si])
    assert not np.any(constraints[0][:,[pilot.index[f"srpD0:{s}"] for s in pilot.sats]])
    maximum=0.;checked=0
    for sat in ("G04","G19","G23","G27"):
        k=pilot.index[f"orbit:{sat}:0"];initial=pilot.seeds[sat]+x[k:k+6];h=.001
        original=products.trajectories[sat];plus=INITIAL_P.copy();minus=INITIAL_P.copy();plus[0]+=h*SCALE;minus[0]-=h*SCALE
        tp=ForceTrajectory(initial,pilot.context["model"],pilot.duration,plus)
        tm=ForceTrajectory(initial,pilot.context["model"],pilot.duration,minus)
        available=[r for r in rows if r["satellite"]==sat]
        for row in [available[i] for i in np.linspace(0,len(available)-1,6,dtype=int)]:
            analytic=pilot.force_partial_for(products,row,x)
            products.trajectories[sat]=tp;yp=pilot.link(products,row,*pilot.state_for(x,row),pilot.windup[id(row)])[0]
            products.trajectories[sat]=tm;ym=pilot.link(products,row,*pilot.state_for(x,row),pilot.windup[id(row)])[0]
            products.trajectories[sat]=original
            finite=(yp-ym)/(2*h);maximum=max(maximum,float(np.max(abs(finite-analytic))));checked+=2
            np.testing.assert_allclose(finite,analytic,rtol=0,atol=5e-5)
    report=dict(status="prepared",case="station-d0-six",source_sha256=engine.sources(),fixture_sha256=sha(fixture),
        code_rows=code,phase_rows=phase,prior_rows=priors,retained_parameters=n,local_clock_parameters=local,
        workspace_estimate_mib=workspace/2**20,budget_pass=True,embedded_baseline_bitwise=True,embedded_cost_difference=cost-original_cost,
        force_prior_absent=True,force_derivative_entries=checked,max_force_derivative_error_m_per_scaled_D0=maximum,
        precise_products_used=False,protocol_sha256=sha(ROOT/"D0_POD_PROTOCOL.md"))
    (folder/"step.json").write_text(json.dumps(report,indent=2)+"\n")
    warm=folder/"warm";warm.mkdir();np.savez_compressed(warm/"solution.npz",x=x,names=np.array(pilot.names))
    (warm/"step.json").write_text(json.dumps(dict(fixture_sha256=sha(fixture),solution_sha256=sha(warm/"solution.npz"),history=[]),indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="source_sha256"},indent=2),flush=True)


if __name__=="__main__":main()
