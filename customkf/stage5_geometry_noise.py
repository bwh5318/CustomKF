"""Controlled linearized noise/geometry experiments within the 900-state cap.

Twelve solve epochs are retained for both 55- and 165-minute arcs. This isolates
time span at approximately fixed equation count, not the effect of adding all
intermediate measurements. Orbit/wet prior centres equal synthetic truth.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from .stage5_pilot import prepare, Pilot, STATIONS, forbid_precise_product_reads
from .network_square_root import assemble, _factor, dense_qr
from .prepare_stage2 import ROOT, sha


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=("baseline","without-koug","without-djig","longer"),required=True)
    args=parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    stations=list(STATIONS)
    if args.case=="without-koug":stations.remove("KOUG")
    if args.case=="without-djig":stations.remove("DJIG")
    context,rows,seeds=prepare(step_s=900 if args.case=="longer" else 300,station_subset=stations)
    disconnected=[]
    for ei in range(12):
        adjacency={}
        for row in rows:
            if row["epoch"]!=ei:continue
            r,s="R:"+row["station"],"S:"+row["satellite"]
            adjacency.setdefault(r,set()).add(s);adjacency.setdefault(s,set()).add(r)
        remaining=set(adjacency);components=[]
        while remaining:
            found=set();queue=[min(remaining)]
            while queue:
                node=queue.pop()
                if node in found:continue
                found.add(node);queue.extend(adjacency[node]-found)
            remaining-=found
            components.append(sorted(found))
        if len(components)>1:disconnected.append({"epoch":ei,"components":components})
    if disconnected:
        report={"case":args.case,"status":"disconnected_epoch_graph","disconnected_epochs":disconnected,
            "station_count":len(stations),"satellite_count":len(seeds),"linear_solve_performed":False,
            "interpretation":"Current single-datum local-clock solver is inapplicable; not a claim that all possible estimators fail",
            "inputs":context["inputs"],"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}}
        (Path(os.environ["CUSTOMKF_RUN_DIR"])/"geometry.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps({k:v for k,v in report.items() if k not in ("inputs","source_sha256")},indent=2),flush=True)
        return
    pilot=Pilot(context,rows,seeds)
    blocks,constraints,residual,sigma,modeled,_,products=pilot.evaluate(np.zeros(len(pilot.names)))
    a,y,weights=assemble(blocks,constraints)
    q,mapping=_factor(a/weights[:,None])
    response=mapping@q[:len(residual)].T
    rng=np.random.default_rng(98231)
    z=rng.standard_normal((len(residual),128))
    if args.case=="baseline":
        original=np.load(ROOT/"runs/20260909T204417Z-9880aa32/noise.npz")
        np.testing.assert_array_equal(original["names"],pilot.names)
        np.testing.assert_array_equal(original["observations"],modeled+sigma*z[:,0])
        np.testing.assert_allclose(original["linear_step"],response@z[:,0],rtol=0,atol=1e-7)
    errors=response@z
    rhs=np.r_[sigma*z[:,0],np.zeros(len(y)-len(residual))]
    independent=dense_qr(a,rhs,weights).estimate
    np.testing.assert_allclose(errors[:,0],independent,rtol=0,atol=1e-7)
    times=np.linspace(10,context["duration_s"]-10,12)
    per_sat=[];all_d=[];partials=[]
    for sat in pilot.sats:
        k=pilot.index[f"orbit:{sat}:0"]
        sampled=[];expected=[];posterior=[];phi_grid=[]
        for t in times:
            phi=products.trajectories[sat].partial(t)[:3]
            sampled.append(phi@errors[k:k+6])
            b=phi@response[k:k+6]
            expected.append(float(np.sum(b*b)))
            posterior.append(float(np.sum((phi@mapping[k:k+6])**2)))
            phi_grid.append(phi)
        sampled=np.array(sampled)
        per_sat.append({"satellite":sat,"expected_3d_rms_m":float(np.sqrt(np.mean(expected))),
            "formal_posterior_3d_sigma_m":float(np.sqrt(np.mean(posterior))),
            "monte_carlo_3d_rms_m":float(np.sqrt(np.mean(np.sum(sampled**2,axis=1)))),
            "stations":sorted({r["station"] for r in rows if r["satellite"]==sat})})
        all_d.append(sampled)
        partials.append(phi_grid)
    rms=np.sqrt(np.mean(np.sum(np.array(all_d)**2,axis=2),axis=(0,1)))
    report={"case":args.case,"status":"passed_linear_noise_experiment","station_count":len(stations),"satellite_count":len(seeds),
        "arc_minutes":(context["duration_s"]-20)/60,"solve_epochs":12,"links":len(rows),"parameters":len(pilot.names),
        "assigned_zenith_code_phase_sigma_m":[.9,.009],"noise_seed":98231,"draws":128,
        "expected_network_3d_rms_m":float(np.sqrt(np.mean([s["expected_3d_rms_m"]**2 for s in per_sat]))),
        "formal_posterior_network_3d_sigma_m":float(np.sqrt(np.mean([s["formal_posterior_3d_sigma_m"]**2 for s in per_sat]))),
        "monte_carlo_median_network_3d_rms_m":float(np.median(rms)),"monte_carlo_5_95_m":np.percentile(rms,[5,95]).tolist(),
        "per_satellite":per_sat,"inputs":context["inputs"],"source_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")},
        "limitation":"Noise-only error assumes correct prior centres and cannot rank networks by itself; reduced data may increase shrinkage toward correct priors. Formal posterior includes assumed prior uncertainty, not calibrated physical errors. Longer case changes spacing, not epoch count."}
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"geometry.json").write_text(json.dumps(report,indent=2)+"\n")
    np.savez_compressed(folder/"linear_model.npz",design_whitened=a/weights[:,None],observation_count=len(residual),
        response=response,mapping=mapping,partials=np.array(partials),satellites=np.array(pilot.sats),names=np.array(pilot.names),times_s=times)
    print(json.dumps({k:v for k,v in report.items() if k not in ("per_satellite","inputs","source_sha256")},indent=2),flush=True)


if __name__=="__main__":main()
