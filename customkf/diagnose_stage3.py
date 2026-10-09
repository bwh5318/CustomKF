"""Bounded, unedited phase diagnostics and published tide-model comparison."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tests.test_stage3_models import tide_reference_cases


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("folders",nargs=3)
    args=parser.parse_args();output=Path(os.environ["CUSTOMKF_RUN_DIR"])
    summary={"stations":{},"iers_reduced_tide_checks":tide_reference_cases(),
             "time_scale":"Hours since 2026-08-02 00:00:00 GPST",
             "note":"Residual diagnostics do not identify physical causes. No postfit observations removed."}
    fig,axes=plt.subplots(3,2,figsize=(12,9),constrained_layout=True)
    kour=None
    for index,folder in enumerate(args.folders):
        folder=Path(folder);report=json.loads((folder/"ppp.json").read_text())
        with np.load(folder/"ppp.npz") as data:
            phase=data["phase"];r=data["residual_m"][phase];el=np.rad2deg(data["elevation_rad"][phase])
            t=data["time_s"][phase]/3600;sat=data["satellite"][phase];arc=data["arc"][phase]
        scaled=r*np.sin(np.deg2rad(el))/.009
        stats={"scaled_phase_rms":float(np.sqrt(np.mean(scaled**2))),
               "max_abs_scaled_phase":float(np.max(np.abs(scaled))),"rows_over_4_sigma":int(sum(np.abs(scaled)>4)),
               "elevation_bins":{},"largest_within_arc_adjacent_changes":[]}
        for lo,hi in ((10,20),(20,30),(30,90.01)):
            mask=(el>=lo)&(el<hi)
            stats["elevation_bins"][f"{lo}-{hi:g}deg"]={"count":int(sum(mask)),
                "rms_m":float(np.sqrt(np.mean(r[mask]**2))) if mask.any() else None,
                "max_abs_m":float(np.max(abs(r[mask]))) if mask.any() else None}
        changes=[]
        for satellite in sorted(set(sat)):
            indices=np.flatnonzero(sat==satellite)
            for before,after in zip(indices[:-1],indices[1:]):
                if arc[before]==arc[after] and abs(t[after]-t[before]-1/12)<1e-8:
                    changes.append({"satellite":str(satellite),"end_hour_gpst":float(t[after]),
                        "change_m":float(r[after]-r[before]),"before_m":float(r[before]),"after_m":float(r[after]),
                        "elevation_deg":float(el[after])})
        stats["largest_within_arc_adjacent_changes"]=sorted(changes,key=lambda x:abs(x["change_m"]),reverse=True)[:10]
        summary["stations"][report["station"]]=stats
        axes[index,0].scatter(t,1000*r,s=4,alpha=.55,c=el,vmin=10,vmax=90,cmap="viridis")
        axes[index,0].set(xlabel="Hour of GPST day",ylabel="IF phase residual (mm)",title=report["station"]+" — all retained phases",xlim=(0,24))
        axes[index,1].scatter(el,1000*r,s=4,alpha=.5)
        axes[index,1].set(xlabel="Elevation (degrees)",ylabel="IF phase residual (mm)",xlim=(10,90))
        for ax in axes[index]:ax.axhline(0,color="black",lw=.7);ax.grid(alpha=.2)
        if report["station"]=="KOUR":kour=(r.copy(),t.copy(),sat.copy(),arc.copy())
    fig.suptitle("Fixed IGS-rapid orbit/clock PPP · 2 August 2026 · no postfit clipping",fontsize=14)
    fig.savefig(output/"phase_residuals.png",dpi=150);plt.close(fig)
    if kour is not None:
        r,t,sat,arc=kour;fig,ax=plt.subplots(figsize=(11,4),constrained_layout=True)
        for satellite in ("G12","G24","G29"):
            mask=(sat==satellite)&(t>=12)&(t<=16)
            ax.plot(t[mask],1000*r[mask],".-",label=satellite,lw=1,ms=4)
        ax.axhline(0,color="black",lw=.7);ax.grid(alpha=.2);ax.legend()
        ax.set(xlabel="Hour of GPST day",ylabel="IF phase residual (mm)",
               title="KOUR: localized residual structure (unedited; cause unassigned)")
        fig.savefig(output/"kour_detail.png",dpi=150);plt.close(fig)
    (output/"diagnostics.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2),flush=True)


if __name__=="__main__":main()
