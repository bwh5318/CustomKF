"""Bounded Stage 3 ingestion audit, without estimating station coordinates."""
from dataclasses import asdict
import gzip
import json
import os
from pathlib import Path
from .prepare_stage3 import DATA,ROOT,sha
from .rinex import text_stream,header,epochs,read_gps_navigation


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    report={"stations":{}}
    for entry in json.loads((DATA/"manifest.json").read_text())["files"]:
        if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Pinned input changed")
    for name in ("gode","wes2","guug"):
        with text_stream(DATA/f"{name}2140.26o.gz") as stream:
            meta=header(stream);count=0;records=0;complete=0;loss=0;intervals={};last=None;first=None;events={}
            available={};lli_bits={"loss_of_lock":0,"wavelength_or_half_cycle":0,"antispoofing":0}
            for epoch in epochs(stream,meta):
                if first is None:first=epoch.gps_ns
                if last is not None:
                    dt=(epoch.gps_ns-last)/1e9;intervals[str(dt)]=intervals.get(str(dt),0)+1
                last=epoch.gps_ns;count+=1;records+=len(epoch.satellites)
                events[str(epoch.flag)]=events.get(str(epoch.flag),0)+1
                for obs in epoch.satellites.values():
                    for code,sample in obs.items():
                        if sample.value is not None:available[code]=available.get(code,0)+1
                    flags=obs.get("L1").lli|obs.get("L2").lli
                    for bit,key in ((1,"loss_of_lock"),(2,"wavelength_or_half_cycle"),(4,"antispoofing")):
                        if flags&bit:lli_bits[key]+=1
                    if all(k in obs and obs[k].value is not None for k in ("P1","P2","L1","L2")):complete+=1
                    if any(obs.get(k) and obs[k].lli for k in ("L1","L2")):loss+=1
            report["stations"][name]={"header":asdict(meta),"epochs":count,"gps_records":records,
                "dual_frequency_p1p2_l1l2":complete,"phase_lli_records":loss,"intervals_s":intervals,
                "first_gps_ns":first,"last_gps_ns":last,"epoch_flags":events}
            report["stations"][name].update(nonempty_gps_observables=available,lli_bit_records=lli_bits)
            print(json.dumps({"station":name,**{k:v for k,v in report["stations"][name].items() if k!="header"}}),flush=True)
    path=DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz"
    with gzip.open(path,"rt") as stream:print("NAV: "+stream.readline().rstrip(),flush=True)
    nav=read_gps_navigation(path)
    report["navigation"]={"satellites":len(nav),"records":sum(map(len,nav.values()))}
    report["status"]="pass"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"inputs.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":main()
