"""Stage 5a: bounded nonlinear observation/dynamics integration checkpoint.

Eight stations and 55 minutes test closure before daily constellation POD.
No precise orbit or clock is opened by the estimator. Broadcast states/clock
polynomials seed the solve; constant empirical force coefficients are fixed.
The weak orbit priors regularize this short arc and preclude accuracy claims.
"""
from datetime import datetime
from dataclasses import asdict
import argparse
import json
import os
from pathlib import Path
import time
import sys
import numpy as np
from .prepare_stage2 import ROOT, DATA as DYN, sha
from .prepare_stage3 import DATA
from .rinex import header, text_stream, epochs, read_gps_navigation
from .preprocess import ArcTracker, combinations, choose_signals
from .sp3 import epoch_tag
from .frames import EarthOrientation, FrameEpoch, Environment
from .ephemeris import DE440
from .orbit_forces import OrbitForceModel
from .station_models import station_displacement, reference_coordinate, read_loading
from .measurement import enu_matrix, geometry
from .antenna import load_calibrations
from .broadcast import select_record, state_inertial
from .dynamic_observation import Trajectory, DynamicProducts, modeled_link, link_jacobian
from .network_square_root import Block, eliminated_qr, require_connected

STATIONS = {"BRUX":"BRUX00BEL", "HOB2":"HOB200AUS", "KOUR":"KOUR00GUF", "ABMF":"ABMF00GLP",
            "KOUG":"KOUG00GUF", "DJIG":"DJIG00DJI", "NNOR":"NNOR00AUS", "MAS1":"MAS100ESP"}
ORIGIN = epoch_tag("* 2026 8 2 11 59 50")
DURATION = 3320.


def forbid_precise_product_reads(event, args):
    """Worker audit hook: accidental named SP3/CLK access is a hard failure."""
    if event == "open" and isinstance(args[0], (str, bytes)):
        name = os.fsdecode(args[0]).lower()
        if ".sp3" in name or ".clk" in name:
            raise RuntimeError("Precise-product access forbidden inside Stage 5 estimator: "+name)


def prepare(*, step_s=300, epoch_count=12, station_subset=None, profile="legacy"):
    """Bounded fixture; defaults exactly reproduce the original Stage 5a case."""
    if profile not in ("legacy","nominal-multihour","nominal-cadence"):raise ValueError("Unknown fixture profile")
    if profile=="legacy" and (step_s not in (300,900) or epoch_count != 12):
        raise ValueError("Diagnostic fixture allows twelve epochs at 300 or 900 seconds")
    if profile=="nominal-multihour" and (step_s!=300 or epoch_count not in (12,37)):
        raise ValueError("New fixture allows 12 or 37 continuous five-minute epochs")
    if profile=="nominal-cadence" and (step_s!=600 or epoch_count not in (19,37)):
        raise ValueError("Cadence experiment allows only 19 or 37 ten-minute epochs")
    available_stations=STATIONS if profile=="legacy" else {**STATIONS,"DAV1":"DAV100ATA","FALK":"FALK00FLK","FAA1":"FAA100PYF","GLPS":"GLPS00ECU","YELL":"YELL00CAN","GUAM":"GUAM00GUM"}
    stations = STATIONS if station_subset is None else {s:available_stations[s] for s in station_subset}
    if "BRUX" not in stations or len(stations)<6:
        raise ValueError("Require reference BRUX and at least six stations")
    last_time=10+(epoch_count-1)*step_s
    duration=last_time+10
    # Only record inputs actually used here, never hash/read precise products as
    # an incidental side effect of a broad Stage 3 manifest verification loop.
    names = ["igs20.atx", "IGc20.ssc", "soln_IGc20.snx", "psd_IGc20.snx", "FES2014b.BLQ",
             "BRDC00WRD_R_20262140000_01D_MN.rnx.gz"]
    names += [f"{m}_R_20262140000_01D_30S_MO.rnx.gz" for m in stations.values()]
    pinned = {}
    for path in DATA.glob("*manifest.json"):
        for entry in json.loads(path.read_text()).get("files", []):
            pinned[entry["path"]] = entry["sha256"]
    for entry in json.loads((DYN/"manifest.json").read_text())["files"]:
        pinned[entry["path"]] = entry["sha256"]
    inputs = [DATA/name for name in names]+[DYN/name for name in ("finals2000A.all", "de440s.bsp", "EGM2008_degree12.gfc")]
    used = {}
    for path in inputs:
        relative = path.relative_to(ROOT).as_posix()
        digest = sha(path)
        if pinned.get(relative) != digest:
            raise ValueError("Changed or unpinned Stage 5 input: "+relative)
        used[relative] = digest
    epoch = FrameEpoch(ORIGIN, EarthOrientation(DYN/"finals2000A.all"))
    ephemeris = DE440(DYN/"de440s.bsp")
    model = OrbitForceModel(Environment(epoch, ephemeris, duration), DYN/"EGM2008_degree12.gfc")
    navigation = read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    raw, station_meta = [], {}
    for station, marker in stations.items():
        tracker = ArcTracker()
        with text_stream(DATA/f"{marker}_R_20262140000_01D_30S_MO.rnx.gz") as stream:
            meta = header(stream,allow_declared_phase_shifts=profile!="legacy")
            pair = choose_signals(meta.types["G"])
            selected = []
            for obs in epochs(stream, meta):
                t = (obs.gps_ns-ORIGIN)/1e9
                if t > last_time:
                    break
                tracker.observe_epoch_event(obs.gps_ns, obs.satellites, obs.flag)
                if obs.flag == 6:
                    continue
                for sat, values in obs.satellites.items():
                    data = combinations(values, pair)
                    if data is None:
                        continue
                    arc = tracker.update(obs.gps_ns, sat, data, obs.flag)
                    if 10 <= t and (t-10)%step_s == 0 and not data["half_cycle"]:
                        selected.append({"station":station, "satellite":sat, "time_s":t,
                            "epoch":int((t-10)/step_s), "arc":f"{station}:{sat}:{arc}",
                            "observation":np.array([data["code_if_m"],data["phase_if_m"]])})
        if station in (DATA/"psd_IGc20.snx").read_text():
            raise ValueError("Unsupported station PSD")
        xyz, solution = reference_coordinate(DATA/"IGc20.ssc", DATA/"soln_IGc20.snx", station, datetime(2026,8,2,12))
        loading = read_loading(DATA/"FES2014b.BLQ", station)
        eccentricity = enu_matrix(xyz).T@np.array(meta.antenna_hen)[[1,2,0]]
        displaced = {t:xyz+eccentricity+station_displacement(xyz,t,epoch,ephemeris,loading) for t in sorted({r["time_s"] for r in selected})}
        for row in selected:
            row["receiver_xyz"] = displaced[row["time_s"]]
        raw.extend(selected)
        station_meta[station] = {"header":asdict(meta), "reference_solution":solution, "fixed_xyz":xyz.tolist()}
    sat_cal, rx_cal = load_calibrations(DATA/"igs20.atx", [m["header"]["antenna"] for m in station_meta.values()], ORIGIN)
    records, seeds, rejected = {}, {}, {}
    cutoff_ns=ORIGIN+int((12*3600+10)*1e9) # End of the observed day; retrospective file-vintage scope.
    if profile!="legacy":
        from .nominal_navigation import corrected_state, NominalProducts
        from .broadcast import select_fit_record
    for sat in sorted({r["satellite"] for r in raw}):
        try:
            if profile=="legacy":rec = select_record(navigation.get(sat, []), ORIGIN)
            else:
                # Check the full receive/transmit grid; never extrapolate an
                # expired fit or silently change the satellite set mid-solve.
                for t in np.arange(10.,last_time+.1,step_s):
                    for offset in (-.2,0.):select_fit_record(navigation.get(sat,[]),ORIGIN+int((t+offset)*1e9),available_before_ns=cutoff_ns)
            if sat not in sat_cal:
                raise ValueError("Missing antenna")
            records[sat] = navigation[sat]
            seeds[sat] = (state_inertial(rec, epoch, ORIGIN) if profile=="legacy" else
                          corrected_state(navigation[sat],epoch,ephemeris,sat_cal[sat],ORIGIN,cutoff_ns))
        except ValueError as error:
            rejected[sat] = str(error)
    trajectories={s:Trajectory(x,model,duration) for s,x in seeds.items()}
    products = (DynamicProducts(epoch, ORIGIN, records, trajectories) if profile=="legacy" else
                NominalProducts(epoch,ORIGIN,records,trajectories,available_before_ns=cutoff_ns))
    rows = []
    for row in raw:
        sat = row["satellite"]
        if sat not in records:
            continue
        g = geometry(products,sat,row["time_s"],row["receiver_xyz"])
        if g["elevation_rad"] >= np.deg2rad(10):
            row["sigma"] = np.array([.9,.009])/np.sin(g["elevation_rad"])
            rows.append(row)
    sats = sorted({r["satellite"] for r in rows})
    seeds = {s:seeds[s] for s in sats}
    context = {"epoch":epoch, "ephemeris":ephemeris, "model":model, "records":records,
               "sat_cal":sat_cal, "rx_cal":rx_cal, "stations":station_meta, "inputs":used,
               "rejected_satellites":rejected,"duration_s":duration,"epoch_count":epoch_count,"step_s":step_s,
               "profile":profile,"navigation_cutoff_ns":cutoff_ns}
    return context, rows, seeds


class Pilot:
    def __init__(self, context, rows, seeds, prior_factor=1.):
        self.context, self.rows, self.seeds = context, rows, seeds
        self.duration=context.get("duration_s",DURATION)
        self.epoch_count=context.get("epoch_count",12)
        self.sats = sorted(seeds)
        self.stations = sorted(context["stations"])
        counts = {}
        for row in rows:
            counts[row["arc"]] = counts.get(row["arc"],0)+1
        self.arcs = sorted(a for a,n in counts.items() if n>=3)
        self.names = [f"orbit:{s}:{k}" for s in self.sats for k in range(6)]
        self.names += [f"wet:{s}:{k}" for s in self.stations for k in range(2)]
        self.names += ["amb:"+a for a in self.arcs]
        self.n = len(self.names)
        self.local_names = []
        for ei in range(self.epoch_count):
            selected = [r for r in rows if r["epoch"] == ei]
            require_connected([(r["station"],r["satellite"]) for r in selected],"BRUX")
            local = [f"clock:{ei}:R:{s}" for s in sorted({r["station"] for r in selected}) if s != "BRUX"]
            local += [f"clock:{ei}:S:{s}" for s in sorted({r["satellite"] for r in selected})]
            self.local_names.append(local)
            self.names.extend(local)
        self.index = {name:k for k,name in enumerate(self.names)}
        self.prior_sigma = np.array([prior_factor*(1000. if k<3 else 1.) for s in self.sats for k in range(6)]+
                                    [.3]*(2*len(self.stations)))
        self.clock_seeds, self.amb_origins, self.windup = {}, {}, {}
        products = self.products(np.zeros(len(self.names)))
        for ei in range(self.epoch_count):
            for station in self.stations:
                selected = [r for r in rows if r["epoch"]==ei and r["station"]==station]
                self.clock_seeds[ei,station] = float(np.median([r["observation"][0]-self.link(products,r,0.,0.,0.,0.,None)[0][0] for r in selected]))
        # Use exactly one continuous windup branch and ambiguity origin per arc,
        # then align every nonlinear trial and derivative evaluation to it.
        previous = {}
        for row in sorted(rows,key=lambda r:r["time_s"]):
            arc = row["arc"]
            out,_,phase,_ = self.link(products,row,self.clock_seeds[row["epoch"],row["station"]],0.,0.,0.,previous.get(arc))
            previous[arc] = phase
            self.windup[id(row)] = phase
            self.amb_origins.setdefault(arc,float((row["observation"][1]-row["observation"][0])-(out[1]-out[0])))

    def products(self, x):
        trajectories = {sat:Trajectory(self.seeds[sat]+x[self.index[f"orbit:{sat}:0"]:self.index[f"orbit:{sat}:0"]+6],
                                       self.context["model"],self.duration) for sat in self.sats}
        if self.context.get("profile","legacy")!="legacy":
            from .nominal_navigation import NominalProducts
            return NominalProducts(self.context["epoch"],ORIGIN,self.context["records"],trajectories,
                                   available_before_ns=self.context["navigation_cutoff_ns"])
        return DynamicProducts(self.context["epoch"],ORIGIN,self.context["records"],trajectories)

    def link(self, products, row, rc, sc, wet, ambiguity, reference):
        c = self.context
        antenna = c["stations"][row["station"]]["header"]["antenna"]
        return modeled_link(products,row,c["rx_cal"][antenna],c["sat_cal"][row["satellite"]],c["ephemeris"],rc,sc,wet,ambiguity,reference)

    def state_for(self,x,row):
        ei, station, sat = row["epoch"],row["station"],row["satellite"]
        rc = self.clock_seeds[ei,station]+(x[self.index[f"clock:{ei}:R:{station}"]] if station!="BRUX" else 0.)
        sc = x[self.index[f"clock:{ei}:S:{sat}"]]
        f = ei/(self.epoch_count-1)
        wet = (1-f)*x[self.index[f"wet:{station}:0"]]+f*x[self.index[f"wet:{station}:1"]]
        amb = self.amb_origins[row["arc"]]+(x[self.index["amb:"+row["arc"]]] if row["arc"] in self.arcs else 0.)
        return rc,sc,wet,amb

    def evaluate(self,x,jacobian=True,observations=None):
        products = self.products(x)
        blocks, residuals, sigmas, modeled = [], [], [], []
        offset = 0
        for ei in range(self.epoch_count):
            local_index = {name:k for k,name in enumerate(self.local_names[ei])}
            gs,ls,ys,ss = [],[],[],[]
            for row in self.rows:
                if row["epoch"] != ei:
                    continue
                rc,sc,wet,amb = self.state_for(x,row)
                out,mw,_,elevation = self.link(products,row,rc,sc,wet,amb,self.windup[id(row)])
                # Retain the fixed prefit selection/weights; no trial-dependent
                # row removal is allowed to make line search improve its score.
                if elevation <= 0:
                    raise ValueError("Trial moved retained observation below horizon")
                if jacobian:
                    c = self.context
                    antenna = c["stations"][row["station"]]["header"]["antenna"]
                    orbit_j,clock_j = link_jacobian(products,row,c["rx_cal"][antenna],c["sat_cal"][row["satellite"]],
                                                   c["ephemeris"],rc,sc,wet,amb,self.windup[id(row)])
                for kind in range(2 if row["arc"] in self.arcs else 1):
                    observation = row["observation"][kind] if observations is None else observations[offset]
                    residuals.append(observation-out[kind]);sigmas.append(row["sigma"][kind]);modeled.append(out[kind]);offset+=1
                    if jacobian:
                        g,l = np.zeros(self.n),np.zeros(len(local_index))
                        k = self.index[f"orbit:{row['satellite']}:0"]
                        g[k:k+6] = orbit_j[kind]
                        f = ei/(self.epoch_count-1)
                        g[self.index[f"wet:{row['station']}:0"]] = mw*(1-f)
                        g[self.index[f"wet:{row['station']}:1"]] = mw*f
                        if kind:
                            g[self.index["amb:"+row["arc"]]] = 1.
                        if row["station"]!="BRUX":
                            l[local_index[f"clock:{ei}:R:{row['station']}"]] = clock_j[kind]
                        l[local_index[f"clock:{ei}:S:{row['satellite']}"]] = -1.
                        gs.append(g);ls.append(l);ys.append(residuals[-1]);ss.append(sigmas[-1])
            if jacobian:
                blocks.append(Block(np.array(gs),np.array(ls),np.array(ys),np.array(ss)))
        c = np.eye(self.n)[:len(self.prior_sigma)]
        prior_target = -(c@x[:self.n])
        prior_sigma = self.prior_sigma.copy()
        for station in self.stations:
            v = np.zeros(self.n)
            v[self.index[f"wet:{station}:0"]]=-1.
            v[self.index[f"wet:{station}:1"]]=1.
            c = np.vstack([c,v]);prior_target=np.r_[prior_target,-v@x[:self.n]];prior_sigma=np.r_[prior_sigma,.03]
        residuals,sigmas = np.array(residuals),np.array(sigmas)
        cost = float(np.sum((residuals/sigmas)**2)+np.sum((prior_target/prior_sigma)**2))
        return blocks,(c,prior_target,prior_sigma),residuals,sigmas,np.array(modeled),cost,products

    def solve(self,initial=None,observations=None,max_iterations=8):
        x = np.zeros(len(self.names)) if initial is None else initial.copy()
        history=[]
        for iteration in range(max_iterations):
            start=time.perf_counter()
            blocks,constraints,residual,sigma,_,cost,_=self.evaluate(x,observations=observations)
            solution=eliminated_qr(blocks,constraints)
            step=solution.estimate
            # Step size is a trajectory displacement, not mixed SI state norm.
            displacement=max(np.linalg.norm(step[self.index[f"orbit:{s}:0"]:self.index[f"orbit:{s}:0"]+3])+
                             self.duration*np.linalg.norm(step[self.index[f"orbit:{s}:0"]+3:self.index[f"orbit:{s}:0"]+6]) for s in self.sats)
            accepted=False
            for alpha in (1.,.5,.25,.125):
                trial=x+alpha*step
                _,_,r2,_,_,cost2,_=self.evaluate(trial,jacobian=False,observations=observations)
                if cost2<=cost+max(1e-6,1e-9*cost):
                    accepted=True;x=trial;break
            history.append({"iteration":iteration,"cost_before":cost,"cost_after":cost2,"accepted":accepted,
                            "step_fraction":alpha,"trajectory_step_bound_m":displacement,"seconds":time.perf_counter()-start})
            print("Iteration",history[-1],flush=True)
            if accepted and displacement<.001 and abs(cost2-cost)<max(1e-5,1e-8*cost):
                return x,history,True
            if not accepted:
                return x,history,False
        return x,history,False


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder=Path(os.environ["CUSTOMKF_RUN_DIR"])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("real","perturbed","synthetic","weak-prior"),default="real")
    args=parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    context,rows,seeds=prepare()
    print(f"Prepared {len(rows)} links, {len(seeds)} satellites",flush=True)
    prior_factor=10. if args.mode=="weak-prior" else 1.
    pilot=Pilot(context,rows,seeds,prior_factor=prior_factor)
    initial=np.zeros(len(pilot.names))
    observations=None
    truth=None
    if args.mode in ("perturbed","synthetic"):
        for sat in pilot.sats:
            k=pilot.index[f"orbit:{sat}:0"]
            initial[k:k+6]=np.array([100.,-70.,40.,.01,-.02,.015])
    if args.mode=="synthetic":
        truth=np.zeros(len(pilot.names))
        truth[pilot.index["clock:6:R:HOB2"]]=37.
        truth[pilot.index["clock:6:S:G08"]]=-12.
        truth[pilot.index["amb:"+pilot.arcs[0]]]=.484435889
        observations=pilot.evaluate(truth,jacobian=False)[4]
    x,history,converged=pilot.solve(initial,observations=observations)
    _,_,residual,sigma,_,cost,products=pilot.evaluate(x,jacobian=False,observations=observations)
    kinds=[]
    for ei in range(12):
        for row in rows:
            if row["epoch"]==ei:
                kinds.extend(range(2 if row["arc"] in pilot.arcs else 1))
    kinds=np.array(kinds)
    report={"status":"converged_short_arc_diagnostic" if converged else "nonlinear_gate_open",
        "scope":"Stage 5a integration pilot, not full Stage 5 constellation accuracy acceptance",
        "mode":args.mode,"converged":converged,
        "inputs":context["inputs"],"rejected_satellites":context["rejected_satellites"],"station_count":len(STATIONS),
        "satellites":pilot.sats,"link_count":len(rows),"parameter_count":len(x),"history":history,
        "observation_rms_m":float(np.sqrt(np.mean(residual**2))),"weighted_cost_with_priors":cost,
        "residuals_by_kind":{label:{"count":int(np.sum(kinds==kind)),"rms_m":float(np.sqrt(np.mean(residual[kinds==kind]**2)))} for kind,label in enumerate(("code","phase"))},
        "precise_products_used_by_estimator":False,"precise_product_open_hook_active":True,
        "orbit_prior_position_sigma_m":prior_factor*1000.,"orbit_prior_velocity_sigma_mps":prior_factor,
        "orbit_prior_center":"broadcast initial state; unchanged during nonlinear iteration and perturbed-start test",
        "fixed_force_parameters":"ECOM5 [-1e-7,0,0,0,0] m/s^2", "station_model":"Stage 3 reduced profile; fixed coordinates and EOP"}
    if truth is not None:
        truth_products=pilot.products(truth)
        report["synthetic_recovery"]={"scope":"Noise-free same-model closure; orbit/wet prior centers equal truth",
            "max_observation_error_m":float(np.max(np.abs(residual))),
            "max_orbit_position_error_m":float(max(np.linalg.norm(products.state(s,t)[:3]-truth_products.state(s,t)[:3]) for s in pilot.sats for t in (10.,1660.,3310.))),
            "receiver_clock_error_m":float(x[pilot.index["clock:6:R:HOB2"]]-37.),
            "satellite_clock_error_m":float(x[pilot.index["clock:6:S:G08"]]+12.)}
    (folder/"pilot.json").write_text(json.dumps(report,indent=2)+"\n")
    grid=np.arange(10.,3311.,300.)
    np.savez_compressed(folder/"pilot.npz",x=x,names=np.array(pilot.names),residual_m=residual,sigma_m=sigma,kinds=kinds,
        times_s=grid,satellites=np.array(pilot.sats),states=np.array([[products.state(s,t) for t in grid] for s in pilot.sats]),
        seed_states=np.array([seeds[s] for s in pilot.sats]))
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":
    main()
