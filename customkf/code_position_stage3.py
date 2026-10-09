"""Guarded code-only diagnostic to test Stage 3 ingestion and geometry.

This deliberately does not claim carrier-phase PPP or its centimetre gate.
"""
import json
import os
from pathlib import Path
import numpy as np
from scipy.linalg import lstsq
from .prepare_stage3 import DATA
from .prepare_stage2 import DATA as DYNAMICS_DATA
from .frames import EarthOrientation
from .precise import PreciseProducts
from .preprocess import choose_signals,combinations,ArcTracker
from .rinex import text_stream,header,epochs,read_gps_navigation
from .measurement import geometry,enu_matrix,hydrostatic_baseline


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    with text_stream(DATA/"gode2140.26o.gz") as stream:
        meta=header(stream);pair=choose_signals(meta.types["G"]);tracker=ArcTracker();selected=[]
        for epoch in epochs(stream,meta):
            tracker.observe_epoch_event(epoch.gps_ns,epoch.satellites,epoch.flag)
            if epoch.flag==6:continue  # Slip-count records are not measurements.
            rows=[]
            for sat,obs in epoch.satellites.items():
                data=combinations(obs,pair)
                if data is None:continue
                arc=tracker.update(epoch.gps_ns,sat,data,epoch.flag)
                rows.append((sat,data,arc))
            if epoch.gps_ns%(1800*10**9)==0:selected.append((epoch.gps_ns,rows))
    origin=selected[0][0]
    navigation=read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    products=PreciseProducts(sorted(DATA.glob("*15M_ORB.SP3.gz")),sorted(DATA.glob("*05M_CLK.CLK.gz")),
                             origin,EarthOrientation(DYNAMICS_DATA/"finals2000A.all"),missing_clock_time_system="GPS")
    results=[];health_rejections=0;geometry_rejections={}
    for tag,observations in selected:
        state=np.r_[meta.approximate_xyz,0.];last=None
        for iteration in range(6):
            design=[];residual=[];sats=[];weights=[]
            for sat,data,arc in observations:
                messages=[r for r in navigation.get(sat,[]) if 0<=tag-r["gps_ns"]<=4*3600*10**9]
                if not messages or messages[-1]["health"]!=0:
                    if iteration==0:health_rejections+=1
                    continue
                try:g=geometry(products,sat,(tag-origin)/1e9,state[:3],state[3])
                except (KeyError,ValueError) as error:
                    if iteration==0:
                        reason=str(error);geometry_rejections[reason]=geometry_rejections.get(reason,0)+1
                    continue
                if g["elevation_rad"]<np.deg2rad(10):continue
                hydro,wet_map=hydrostatic_baseline(state[:3],g["elevation_rad"])
                prediction=g["modeled_code_without_trop_m"]+hydro+.1*wet_map
                design.append(np.r_[-g["los_ecef"],1.]);residual.append(data["code_if_m"]-prediction)
                sats.append(sat);weights.append(np.sin(g["elevation_rad"]))
            if len(residual)<5:break
            a=np.array(design)*np.array(weights)[:,None];b=np.array(residual)*weights
            correction,_,rank,_=lstsq(a,b,lapack_driver="gelsy")
            if rank!=4:break
            state+=correction;last=(sats,residual)
            if np.linalg.norm(correction)<1e-4:break
        if last is not None:
            results.append({"gps_ns":int(tag),"xyz_m":state[:3].tolist(),"receiver_clock_m":float(state[3]),
                "satellites":last[0],"prefinal_code_rms_m":float(np.sqrt(np.mean(np.array(last[1])**2)))})
    if len(results)<40:raise ValueError("Insufficient code diagnostic coverage")
    positions=np.array([r["xyz_m"] for r in results]);center=np.median(positions,axis=0)
    scatter=(enu_matrix(center)@(positions-center).T).T
    report={"status":"diagnostic_complete","station":"GODE","sample_epochs":len(results),
        "signal_pair":pair.__dict__,"native_arc_count":tracker.next_arc,"arc_events":tracker.events,
        "navigation_health_or_age_rejections":health_rejections,"geometry_rejections":geometry_rejections,
        "clock_time_basis":"Explicit GPST declaration for pinned IGS rapid CLK files with GPS/IGST header comments; TIME SYSTEM ID absent",
        "median_xyz_m":center.tolist(),"scatter_enu_rms_m":np.sqrt(np.mean(scatter**2,axis=0)).tolist(),
        "median_minus_header_xyz_m":(center-np.array(meta.approximate_xyz)).tolist(),"epochs":results,
        "limitations":["code-only; no carrier-phase estimation","header coordinate is not an accuracy reference",
            "no antenna corrections","no station tides/loading","simple hydrostatic and fixed wet baseline",
            "rapid products from neighbouring days used retrospectively; no latency certification"]}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"code_position.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("epochs","arc_events")},indent=2),flush=True)


if __name__=="__main__":main()
