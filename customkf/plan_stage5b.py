"""Guarded station geometry screen from public listing and pinned local metadata.

Screen only: clock-centred line-of-sight information is not a dynamic POD
covariance and assumes coordinates/receiver clocks known. No SP3 input.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import argparse
import numpy as np
from .prepare_stage2 import ROOT, CURL, sha
from .prepare_stage3 import DATA
from .stage5_pilot import ORIGIN, STATIONS
from .rinex import read_gps_navigation
from .broadcast import select_fit_record, position
from .station_models import reference_coordinate, read_loading
from .measurement import enu_matrix

OUT=ROOT/"data/stage5b"
URL="https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/214/"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("--header-screen",type=Path);args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    listing=OUT/"bkg-2026214-listing.html"
    if not listing.exists():
        subprocess.run([CURL,"--fail","--location","--silent","--show-error","--max-time","45","--max-filesize",str(4*2**20),URL,"-o",str(listing)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    markers=sorted(set(re.findall(r'([A-Z0-9]{9})_R_20262140000_01D_30S_MO\.crx\.gz',listing.read_text())))
    psd=(DATA/"psd_IGc20.snx").read_text();candidates={};rejected={}
    compatible=None
    if args.header_screen:
        screen=json.loads(args.header_screen.read_text())
        compatible=set(STATIONS)|{"REUN"}|{marker[:4] for marker,value in screen.items() if value["status"]=="compatible_header"}
    for marker in markers:
        station=marker[:4]
        if compatible is not None and station not in compatible:continue
        try:
            if station in psd:raise ValueError("Unsupported station PSD")
            xyz,_=reference_coordinate(DATA/"IGc20.ssc",DATA/"soln_IGc20.snx",station,datetime(2026,8,2,12))
            read_loading(DATA/"FES2014b.BLQ",station)
            candidates[station]=(marker,xyz)
        except ValueError as error:rejected[station]=str(error)
    nav=read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    times=np.arange(10.,10811.,300.);cutoff=ORIGIN+int((12*3600+10)*1e9)
    sats=[];states=[];nav_rejected={}
    for sat,records in sorted(nav.items()):
        try:
            states.append([position(select_fit_record(records,ORIGIN+int(t*1e9),available_before_ns=cutoff),ORIGIN+int(t*1e9)) for t in times])
            sats.append(sat)
        except ValueError as error:nav_rejected[sat]=str(error)
    states=np.array(states)
    design={}
    for station,(_,xyz) in candidates.items():
        delta=states-xyz;u=delta/np.linalg.norm(delta,axis=2)[:,:,None]
        sine=u@enu_matrix(xyz)[2]
        w=np.where(sine>=np.sin(np.deg2rad(10)),sine**2,0.)
        design[station]=(w,u)
    def information(stations):
        w=np.array([design[s][0] for s in stations]);u=np.array([design[s][1] for s in stations])
        mean=np.sum(w[:,:,:,None]*u,axis=0)/np.maximum(w.sum(axis=0)[:,:,None],1e-30)
        d=u-mean
        return np.einsum('nse,nsei,nsej->seij',w,d,d)
    def score(stations):
        info=information(stations)
        weights=np.array([2. if s in ("G05","G12","G20","G22") else 1. for s in sats])
        return float(np.sum(weights[:,None]*np.linalg.slogdet(info+np.eye(3)*1e-6)[1]))
    selected=list(STATIONS)
    if not set(selected)<=set(candidates):raise ValueError("Base station metadata unavailable")
    baseline=score(selected);steps=[]
    for _ in range(4):
        ranked=sorted(((score(selected+[s]),s) for s in candidates if s not in selected),reverse=True)
        best,station=ranked[0];selected.append(station)
        steps.append({"selected":station,"marker":candidates[station][0],"score":best,"alternatives":[{"station":s,"score":v} for v,s in ranked[:8]]})
    def diagnostics(stations):
        info=information(stations);out=[]
        for si,sat in enumerate(sats):
            counts=np.sum([design[s][0][si]>0 for s in stations],axis=0)
            out.append({"satellite":sat,"minimum_receivers":int(counts.min()),"median_receivers":float(np.median(counts)),"median_minimum_information_eigenvalue":float(np.median(np.linalg.eigvalsh(info[si])[:,0]))})
        return out
    report={"scope":"Prospective geometric screening, not orbit-error prediction or station observation-quality acceptance", "header_screen_sha256":sha(args.header_screen) if args.header_screen else None,"listing_url":URL,"listing_sha256":sha(listing),"eligible_candidates":len(candidates),"rejected":rejected,"navigation_rejected":nav_rejected,"baseline_score":baseline,"steps":steps,"selected_markers":[candidates[s][0] for s in selected],"baseline":diagnostics(list(STATIONS)),"expanded":diagnostics(selected),"time_grid_s":times.tolist(),"sources_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/"customkf").glob("*.py")}}
    target=Path(os.environ["CUSTOMKF_RUN_DIR"])/"plan.json"
    target.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k in ("eligible_candidates","steps","selected_markers","navigation_rejected")},indent=2),flush=True)


if __name__=="__main__":main()
