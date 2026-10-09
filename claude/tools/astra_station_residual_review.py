"""Bounded, unedited PPP residual plots and DAV1 native-record episode review.

Run via customkf.guard --timeout 120 -- claude.tools.astra_station_residual_review
No refit, data deletion, new download, or physical-cause attribution.
"""
from collections import Counter
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from customkf.prepare_stage2 import ROOT,sha
from customkf.rinex import text_stream,header,epochs
from customkf.preprocess import choose_signals,combinations
from customkf.sp3 import epoch_tag

CAMPAIGN=ROOT/"validation/stage5b_stations/20260911T015113Z"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    manifest=json.loads((CAMPAIGN/"validation.json").read_text())
    for name,digest in manifest["artifacts_sha256"].items():
        assert sha(CAMPAIGN/name)==digest,name
    fig,axes=plt.subplots(4,2,figsize=(11,9),constrained_layout=True)
    summary={"status":"residual_review_complete_DAV1_exception_open","stations":{}}
    for row,station in enumerate(("DAV1","FALK","FAA1","GLPS")):
        data=np.load(CAMPAIGN/station/"ppp.npz");mask=data["phase"]
        r=data["residual_m"][mask];t=data["time_s"][mask]/3600;el=data["elevation_rad"][mask]
        normalized=r*np.sin(el)/.009;sats=data["satellite"][mask]
        axes[row,0].scatter(t,r*1000,s=3,alpha=.65,color="#27649b")
        axes[row,0].axvspan(12,15,color="#45a56b",alpha=.15)
        axes[row,0].set(xlim=(0,24),ylabel=f"{station}\nPhase residual (mm)")
        axes[row,1].scatter(t,normalized,s=3,alpha=.65,color="#80509d")
        axes[row,1].axvspan(12,15,color="#45a56b",alpha=.15)
        axes[row,1].axhline(4,color="#b12a37",lw=.7);axes[row,1].axhline(-4,color="#b12a37",lw=.7)
        axes[row,1].set(xlim=(0,24),ylabel="Residual / assumed sigma")
        flags=abs(normalized)>4;arc=(t>=12)&(t<=15)
        summary["stations"][station]={"above_4_sigma":[{"hour_gpst":float(t[i]),"satellite":str(sats[i]),"phase_mm":float(1000*r[i]),"normalized":float(normalized[i])} for i in np.flatnonzero(flags)],
            "network_arc_above_4_sigma_count":int(sum(flags&arc))}
        for ax in axes[row]:ax.grid(alpha=.15)
    axes[0,0].set_title("Unedited fixed-IGS PPP residuals, 2 August 2026")
    axes[0,1].set_title("Green interval: Stage 5b orbit experiment")
    for ax in axes[-1]:ax.set_xlabel("Hour GPST")
    fig.savefig(folder/"station_residuals.png",dpi=140)
    plt.close(fig)
    origin=epoch_tag("* 2026 08 02 00 00 0")
    flags=summary["stations"]["DAV1"]["above_4_sigma"]
    involved={v["satellite"] for v in flags}
    events=json.loads((CAMPAIGN/"DAV1/arc_events.json").read_text())
    episode=[{**v,"hour_gpst":(v["gps_ns"]-origin)/3.6e12} for v in events if 21<=(v["gps_ns"]-origin)/3.6e12<=22]
    summary["DAV1_arc_events_21_to_22_GPST"]=episode
    summary["DAV1_daily_arc_reason_counts"]=dict(Counter(reason for event in events for reason in event["reasons"]))
    path=ROOT/"data/stage3/DAV100ATA_R_20262140000_01D_30S_MO.rnx.gz"
    assert sha(path)==manifest["input_sha256"][path.relative_to(ROOT).as_posix()]
    native=[]
    with text_stream(path) as stream:
        meta=header(stream,allow_declared_phase_shifts=True);pair=choose_signals(meta.types["G"])
        for epoch in epochs(stream,meta):
            hour=(epoch.gps_ns-origin)/3.6e12
            if hour>22:break
            if hour<21:continue
            for sat in sorted(involved&set(epoch.satellites)):
                obs=epoch.satellites[sat];data=combinations(obs,pair)
                native.append({"hour_gpst":hour,"satellite":sat,"epoch_flag":epoch.flag,
                    "lli":{k:v.lli for k,v in obs.items() if k.startswith("L")},
                    "combination":data})
    summary["DAV1_native_episode"]=native
    summary["input_sha256"]={p.relative_to(ROOT).as_posix():sha(p) for p in (path,CAMPAIGN/"validation.json")}
    summary["tool_sha256"]=sha(Path(__file__))
    (folder/"residual_review.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({"flagged":{s:len(v["above_4_sigma"]) for s,v in summary["stations"].items()},
        "DAV1_flagged_rows":flags,"DAV1_arc_event_count_21_to_22":len(episode),
        "DAV1_native_episode_rows":len(native),"DAV1_daily_arc_reason_counts":summary["DAV1_daily_arc_reason_counts"]},indent=2))


if __name__=="__main__":main()
