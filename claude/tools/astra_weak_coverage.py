"""Guarded, cached-data-only screen of extra views for the five flagged GPS SVs.

customkf.guard --timeout 120 -- claude.tools.astra_weak_coverage
Uses actual archived baseline observation masks and broadcast geometry for
candidate views. No IGS products, acquisition, new fit, or accuracy prediction.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

import numpy as np

from customkf.prepare_stage2 import ROOT,sha
from customkf.stage5_pilot import ORIGIN,forbid_precise_product_reads
from customkf.rinex import read_gps_navigation
from customkf.broadcast import position,select_fit_record
from customkf.station_models import reference_coordinate,read_loading
from customkf.measurement import enu_matrix

DATA=ROOT/"data/stage3"
ARCHIVE=ROOT/"validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
FOCUS=("G16","G18","G26","G29","G31")


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    sys.addaudithook(forbid_precise_product_reads)
    fixture_path=ARCHIVE/"expanded-long-prepare/fixture.json"
    fixture=json.loads(fixture_path.read_text());manifest=json.loads((ARCHIVE/"validation.json").read_text())
    assert sha(fixture_path)==manifest["artifacts_sha256"][fixture_path.relative_to(ARCHIVE).as_posix()]
    for name,digest in fixture["context"]["inputs"].items():assert sha(ROOT/name)==digest,name
    inputs=[fixture_path,ROOT/"data/stage5b/bkg-2026214-listing.html",ROOT/"runs/20260910T015027Z-4dc3d5cc/headers.json"]
    header_info=json.loads(inputs[-1].read_text())
    markers=sorted(set(re.findall(r'([A-Z0-9]{9})_R_20262140000_01D_30S_MO\.crx\.gz',inputs[1].read_text())))
    psd=(DATA/"psd_IGc20.snx").read_text();candidates={};rejected={}
    baseline={r["station"]:np.array(r["receiver_xyz"]) for r in fixture["rows"]}
    for marker in markers:
        station=marker[:4]
        if station in baseline:continue
        try:
            if station in psd:raise ValueError("Unsupported PSD")
            xyz,_=reference_coordinate(DATA/"IGc20.ssc",DATA/"soln_IGc20.snx",station,datetime(2026,8,2,12))
            read_loading(DATA/"FES2014b.BLQ",station)
            candidates[station]=(marker,xyz)
        except ValueError as error:rejected[station]=str(error)
    nav=read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    times=10+300*np.arange(37);cutoff=fixture["context"]["navigation_cutoff_ns"]
    states={s:np.array([position(select_fit_record(nav[s],ORIGIN+int(t*1e9),available_before_ns=cutoff),ORIGIN+int(t*1e9)) for t in times]) for s in FOCUS}
    def views(xyz,s):
        d=states[s]-xyz;u=d/np.linalg.norm(d,axis=1)[:,None];sine=u@enu_matrix(xyz)[2]
        return u,np.where(sine>=np.sin(np.deg2rad(10)),sine**2,0)
    existing={st:{s:views(xyz,s) for s in FOCUS} for st,xyz in baseline.items()}
    masks={s:[{r["station"] for r in fixture["rows"] if r["satellite"]==s and r["epoch"]==i} for i in range(37)] for s in FOCUS}
    results=[]
    for st,(marker,xyz) in candidates.items():
        per={};total=0.
        for sat in FOCUS:
            u,w=views(xyz,sat);gain=0.;potential=0;separation=[]
            for i,stations in enumerate(masks[sat]):
                if w[i]==0 or not stations:continue
                distinct=[s for s in stations if np.linalg.norm(xyz-baseline[s])>=50000]
                if distinct:potential+=1
                weights=np.array([existing[s][sat][1][i] for s in stations]);directions=np.array([existing[s][sat][0][i] for s in stations])
                weight=float(weights.sum())
                if weight<=0:continue
                mean=np.sum(weights[:,None]*directions,axis=0)/weight
                # Increment in trace of clock-centred LOS information; receiver
                # clocks assumed known. All five satellites have equal weight.
                gain+=float(weight*w[i]/(weight+w[i])*np.sum((u[i]-mean)**2))
                if distinct:separation.append(max(float(np.degrees(np.arccos(np.clip(u[i]@existing[s][sat][0][i],-1,1)))) for s in distinct))
            total+=gain
            per[sat]={"potential_distinct_co_visible_epochs":potential,
                "geometric_visible_epochs":np.flatnonzero(w>0).tolist(),"los_information_trace_gain":gain,
                "median_max_los_separation_deg":float(np.median(separation)) if separation else None}
        info=header_info.get(marker,{"status":"not_header_screened"})
        if st=="REUN":info={"status":"previous_full_file_compatible"}
        results.append({"station":st,"marker":marker,"score":total,"header_status":info["status"],"header_reason":info.get("reason"),
                        "full_local_rinex_present":(DATA/f"{marker}_R_20262140000_01D_30S_MO.rnx.gz").exists(),"per_satellite":per})
    results.sort(key=lambda v:(-v["score"],v["station"]))
    compatible=[r for r in results if r["header_status"] in ("compatible_header","previous_full_file_compatible")]
    report={"status":"candidate_geometry_screen_only","focus":FOCUS,
        "method":"Equal-weight sum of incremental clock-centred LOS information trace over five frozen weak-sigma satellites. Baseline actual masks; candidate broadcast elevation >=10 deg. Receiver clocks assumed known. No orbit-error inputs.",
        "limitation":"Potential candidate visibility is not verified observation availability. Header compatibility alone does not establish coordinate solution/calibration validity for the complete file.",
        "candidates":results,"compatible_candidates":compatible,"rejected_metadata":rejected,
        "input_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},"tool_sha256":sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"coverage.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"top_all":results[:8],"compatible":compatible},indent=2))


if __name__=="__main__":main()
