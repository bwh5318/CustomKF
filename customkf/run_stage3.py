"""Bounded static GPS float PPP development experiment with fixed rapid products.

The initial reduced loading/atmosphere/attitude profile remains explicitly
experimental. Coordinate gates and phase diagnostics are reported separately.
"""
import argparse
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import time
import numpy as np
from .square_root import weighted_qr
from .prepare_stage3 import DATA
from .prepare_stage2 import DATA as DYN_DATA,ROOT,sha
from .rinex import text_stream,header,epochs,read_gps_navigation
from .preprocess import choose_signals,combinations,ArcTracker,ALPHA,BETA,LAMBDA1,LAMBDA2
from .precise import PreciseProducts
from .frames import EarthOrientation
from .ephemeris import DE440
from .measurement import geometry,enu_matrix
from .antenna import load_calibrations,corrections
from .station_models import troposphere,station_displacement,read_loading,reference_coordinate
from .sp3 import epoch_tag

LEGACY_MARKERS={"BRUX":"BRUX00BEL","KOUR":"KOUR00GUF","HOB2":"HOB200AUS","SALU":"SALU00BRA","ABMF":"ABMF00GLP","KOUG":"KOUG00GUF"}
STAGE5B_MARKERS={"DAV1":"DAV100ATA","FALK":"FALK00FLK","FAA1":"FAA100PYF","GLPS":"GLPS00ECU","YELL":"YELL00CAN","GUAM":"GUAM00GUM"}


def main(argv=None,_history=None):
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station",choices=[*LEGACY_MARKERS,*STAGE5B_MARKERS],default="BRUX")
    parser.add_argument("--date",choices=["2026-08-01","2026-08-02","2026-08-03"],default="2026-08-02")
    parser.add_argument("--interval",type=int,choices=[300,900],default=300)
    parser.add_argument("--initial-offset",type=float,nargs=3,default=[0.,0.,0.],metavar=("X","Y","Z"))
    parser.add_argument("--allow-next-day-products",action="store_true",help="Retrospective padding diagnostic only; violates target-day rapid availability")
    args=parser.parse_args(argv);started=time.perf_counter();folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    expanded=args.station in STAGE5B_MARKERS
    if expanded and args.date!="2026-08-02":raise ValueError("Expanded station profile is pinned to 2026-08-02")
    history=[] if _history is None else _history
    if not np.isfinite(args.initial_offset).all() or np.linalg.norm(args.initial_offset)>200:
        raise ValueError("Initial perturbation must be finite and at most 200 m")
    date=datetime.strptime(args.date,"%Y-%m-%d");day=date.timetuple().tm_yday
    manifests=["manifest.json","rinex3_manifest.json","support_manifest.json"]
    if (DATA/"kour_campaign_manifest.json").exists():manifests.append("kour_campaign_manifest.json")
    if expanded:manifests.append("stage5b_manifest.json")
    pinned_inputs={}
    for filename in manifests:
        for entry in json.loads((DATA/filename).read_text())["files"]:
            if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Changed PPP input")
            pinned_inputs[entry["path"]]=entry["sha256"]
    marker={**LEGACY_MARKERS,**STAGE5B_MARKERS}[args.station]
    source=DATA/f"{marker}_R_2026{day}0000_01D_30S_MO.rnx.gz"
    if source.relative_to(ROOT).as_posix() not in pinned_inputs:raise ValueError("Unpinned station observations")
    tracker=ArcTracker();selected=[];native=0;missing=0
    with text_stream(source) as stream:
        meta=header(stream,allow_declared_phase_shifts=expanded);pair=choose_signals(meta.types["G"])
        for epoch in epochs(stream,meta):
            native+=1;tracker.observe_epoch_event(epoch.gps_ns,epoch.satellites,epoch.flag)
            if epoch.flag==6:continue
            records=[]
            for sat,obs in epoch.satellites.items():
                data=combinations(obs,pair)
                if data is None:missing+=1;continue
                arc=tracker.update(epoch.gps_ns,sat,data,epoch.flag)
                if data["half_cycle"]:continue
                records.append((sat,data,arc))
            if epoch.gps_ns%(args.interval*10**9)==0:selected.append((epoch.gps_ns,records))
    origin=epoch_tag(date.strftime("* %Y %m %d 0 0 0"))
    if not selected or any(not origin<=tag<origin+86400*10**9 for tag,_ in selected):
        raise ValueError("Selected observations must belong to the declared GPST day")
    def product_paths(suffix):
        days=(day-1,day,day+1) if args.allow_next_day_products else (day-1,day)
        return [DATA/f"IGS0OPSRAP_2026{day}0000_01D_{suffix}" for day in days]
    orbit_paths=product_paths("15M_ORB.SP3.gz");clock_paths=product_paths("05M_CLK.CLK.gz")
    products=PreciseProducts(orbit_paths,clock_paths,
                            origin,EarthOrientation(DYN_DATA/"finals2000A.all"),missing_clock_time_system="GPS")
    ephemeris=DE440(DYN_DATA/"de440s.bsp")
    sat_cal,rx_cal=load_calibrations(DATA/"igs20.atx",[meta.antenna],origin)
    navigation=read_gps_navigation(DATA/f"BRDC00WRD_R_2026{day}0000_01D_MN.rnx.gz")
    reference,solution_number=reference_coordinate(DATA/"IGc20.ssc",DATA/"soln_IGc20.snx",args.station,date.replace(hour=12))
    with (DATA/"psd_IGc20.snx").open() as stream:
        if any(args.station in line.split() for line in stream):
            raise ValueError("Selected station has postseismic terms; evaluation model must be extended")
    loading=read_loading(DATA/"FES2014b.BLQ",args.station)
    approximate=np.array(meta.approximate_xyz)+args.initial_offset;enu=enu_matrix(approximate)
    eccentricity=enu.T@np.array(meta.antenna_hen)[[1,2,0]]
    rows=[];rejections={};windup={};clocks=[];times=[]
    def reject(reason):rejections[reason]=rejections.get(reason,0)+1
    for index,(tag,observations) in enumerate(selected):
        t=(tag-origin)/1e9
        receiver=approximate+eccentricity+station_displacement(approximate,t,products.epoch,ephemeris,loading)
        candidates=[];b=[]
        for sat,data,arc in observations:
            nav=[r for r in navigation.get(sat,[]) if 0<=tag-r["gps_ns"]<=4*3600*10**9]
            if not nav or nav[-1]["health"]!=0:reject("navigation_health_or_age");continue
            if sat not in sat_cal:reject("missing_satellite_antenna");continue
            try:g=geometry(products,sat,t,receiver)
            except (ValueError,KeyError) as error:reject("geometry_"+str(error));continue
            if g["elevation_rad"]<np.deg2rad(10):reject("elevation_below_10deg");continue
            candidates.append((sat,data,arc))
            hydro,_=troposphere(receiver,g["elevation_rad"],day+t/86400)
            b.append(data["code_if_m"]-g["modeled_code_without_trop_m"]-hydro)
        if len(candidates)<5:reject("epoch_fewer_than_5_satellites");continue
        clock=float(np.median(b));ei=len(clocks);clocks.append(clock);times.append(t)
        for sat,data,arc in candidates:
            g=geometry(products,sat,t,receiver,clock)
            hydro,mw=troposphere(receiver,g["elevation_rad"],day+t/86400)
            sun,_=ephemeris.sun_moon_m(products.epoch.tdb_seconds(g["transmit_s"]))
            antenna,phase=corrections(g,receiver,rx_cal[meta.antenna],sat_cal[sat],sun,
                                      products.epoch.celestial_to_terrestrial(g["receive_s"]))
            key=(sat,arc)
            if key in windup:phase+=np.floor(windup[key]-phase+.5)
            windup[key]=phase
            base=g["modeled_code_without_trop_m"]+hydro+antenna
            rows.append({"epoch":ei,"time_s":t,"satellite":sat,"arc":arc,"elevation":g["elevation_rad"],
                "azimuth":g["azimuth_rad"],"los":g["los_ecef"],"wet_mapping":mw,
                "code_residual":data["code_if_m"]-base,
                "phase_residual":data["phase_if_m"]-base-(ALPHA*LAMBDA1+BETA*LAMBDA2)*phase})
        if index%72==0:print(f"{args.station}: modeled {index+1}/{len(selected)} epochs",flush=True)
    # Retain all usable rows; no postfit clipping. Short phase arcs are counted
    # and excluded before solving to avoid singleton ambiguities masquerading as fit.
    counts={}
    for row in rows:counts[row["arc"]]=counts.get(row["arc"],0)+1
    arc_ids=sorted(k for k,n in counts.items() if n>=3);arc_index={a:i for i,a in enumerate(arc_ids)}
    nclock=len(clocks);nwet=25;nparam=3+nclock+nwet+2+len(arc_ids)
    if len(rows)>5000 or nparam>900:raise ValueError("PPP development matrix budget exceeded")
    design=[];target=[];sigma=[];labels=[];ambiguity_origin={}
    for row in rows:
        v=np.zeros(nparam);v[:3]=-row["los"];v[3+row["epoch"]]=1.
        hour=row["time_s"]/3600;k=min(int(hour),23);f=hour-k
        v[3+nclock+k]=row["wet_mapping"]*(1-f);v[3+nclock+k+1]=row["wet_mapping"]*f
        mg=1/(np.sin(row["elevation"])*np.tan(row["elevation"])+.0032)
        v[3+nclock+nwet:3+nclock+nwet+2]=mg*np.array([np.cos(row["azimuth"]),np.sin(row["azimuth"])])
        design.append(v.copy());target.append(row["code_residual"]);sigma.append(.9/np.sin(row["elevation"]));labels.append(("code",row))
        if row["arc"] in arc_index:
            ambiguity_origin.setdefault(row["arc"],row["phase_residual"]-row["code_residual"])
            v[3+nclock+nwet+2+arc_index[row["arc"]]]=1.
            design.append(v);target.append(row["phase_residual"]-ambiguity_origin[row["arc"]]);sigma.append(.009/np.sin(row["elevation"]));labels.append(("phase",row))
    ndata=len(target)
    # Weak wet-delay continuity, 3 cm/sqrt(hour). No coordinate priors.
    for k in range(nwet-1):
        v=np.zeros(nparam);v[3+nclock+k]=-1;v[3+nclock+k+1]=1
        design.append(v);target.append(0.);sigma.append(.03)
    a=np.array(design);y=np.array(target);sigma=np.array(sigma)
    estimate,rank=weighted_qr(a,y,sigma)
    residual=y[:ndata]-a[:ndata]@estimate
    delta_enu=enu@(approximate+estimate[:3]-reference)
    residual_stats={}
    for kind in ("code","phase"):
        mask=np.array([label[0]==kind for label in labels]);r=residual[mask]
        residual_stats[kind]={"count":int(sum(mask)),"rms_m":float(np.sqrt(np.mean(r*r))),"median_abs_m":float(np.median(np.abs(r))),"max_abs_m":float(np.max(np.abs(r)))}
    position_gate=np.linalg.norm(delta_enu[:2])<.02 and abs(delta_enu[2])<.05
    report={"status":"development_position_gate_pass" if position_gate else "development_position_gate_not_met",
        "station":args.station,"date":args.date,"frame":products.frame,"reference_solution":solution_number,"reference_xyz_m":reference.tolist(),
        "estimated_xyz_m":(approximate+estimate[:3]).tolist(),"error_enu_m":delta_enu.tolist(),
        "horizontal_error_m":float(np.linalg.norm(delta_enu[:2])),"native_epochs":native,"modeled_epochs":nclock,
        "observations_missing_pair":missing,"native_arc_count":tracker.next_arc,"fitted_ambiguities":len(arc_ids),
        "short_arc_phase_rows_excluded":sum(n for n in counts.values() if n<3),"rejections":rejections,
        "parameter_count":nparam,"rank":rank,"residuals":residual_stats,"receiver_header":asdict(meta),
        "signal_pair":asdict(pair),"wet_delays_m":estimate[3+nclock:3+nclock+nwet].tolist(),
        "gradients_m":estimate[3+nclock+nwet:3+nclock+nwet+2].tolist(),"elapsed_s":time.perf_counter()-started,
        "initial_offset_m":args.initial_offset,"coordinate_correction_m":estimate[:3].tolist(),
        "profile":"NMF + standard pressure; reduced solid tides and 11-line ocean loading (no CMC); secular-pole tide; nominal yaw; float IF; no postfit clipping",
        "product_paths":[p.relative_to(ROOT).as_posix() for p in orbit_paths+clock_paths],
        "next_day_product_padding":args.allow_next_day_products,
        "station_input_profile":"stage5b_declared_phase_metadata" if expanded else "legacy",
        "observation_sha256":pinned_inputs[source.relative_to(ROOT).as_posix()],
        "modeled_time_span_s":[min(times),max(times)],
        "stage3_gate_note":"Position threshold alone is insufficient: residual structure, independent tests and repeated station/date validation remain required"}
    history.append({"iteration":len(history),"initial_offset_m":args.initial_offset,"coordinate_correction_m":estimate[:3].tolist(),
                    "elapsed_s":report["elapsed_s"]})
    report["iterations"]=history
    report["converged"]=bool(np.linalg.norm(estimate[:3])<1e-4)
    if not report["converged"] and len(history)<4:
        (folder/f"ppp_iteration_{len(history)-1}.json").write_text(json.dumps(report,indent=2)+"\n")
        next_offset=approximate+estimate[:3]-np.array(meta.approximate_xyz)
        print(f"{args.station}: relinearizing after {np.linalg.norm(estimate[:3]):.6f} m coordinate correction",flush=True)
        del design,a,estimate,y,sigma,residual,rows,labels,products,selected
        return main(["--station",args.station,"--date",args.date,"--interval",str(args.interval),"--initial-offset",*[str(v) for v in next_offset],
                     *(["--allow-next-day-products"] if args.allow_next_day_products else [])],history)
    report["elapsed_s"]=sum(item["elapsed_s"] for item in history)
    if not report["converged"]:report["status"]="nonlinear_convergence_failed"
    (folder/"ppp.json").write_text(json.dumps(report,indent=2)+"\n")
    (folder/"arc_events.json").write_text(json.dumps(tracker.events,indent=2)+"\n")
    np.savez(folder/"ppp.npz",residual_m=residual,phase=np.array([kind=="phase" for kind,row in labels]),
        arc=np.array([row["arc"] for kind,row in labels]),
        time_s=np.array([row["time_s"] for kind,row in labels]),satellite=np.array([row["satellite"] for kind,row in labels]),
        elevation_rad=np.array([row["elevation"] for kind,row in labels]),azimuth_rad=np.array([row["azimuth"] for kind,row in labels]),estimate=estimate,clock_initial_m=np.array(clocks))
    print(json.dumps({k:report[k] for k in ("status","error_enu_m","residuals","fitted_ambiguities","elapsed_s")},indent=2),flush=True)


if __name__=="__main__":main()
