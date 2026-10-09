"""Real eight-station, 55-minute linearized network fixture for Stage 4.

The nominal trajectory and clocks remain IGS rapid. Orbit corrections use
six-state variational bases from the Stage 2 force model. This is a *linear
algebra fixture*, not an independently propagated POD solution: the nominal
SP3 trajectory need not satisfy that force model, and antenna/relativistic/
light-time corrections are frozen during the solve. No orbit product is emitted.
"""
from dataclasses import asdict
from datetime import datetime
import json
import numpy as np
from scipy.interpolate import CubicSpline
from .prepare_stage2 import ROOT, DATA as DYN_DATA, sha
from .prepare_stage3 import DATA
from .rinex import text_stream, header, epochs, read_gps_navigation
from .preprocess import choose_signals, combinations, ArcTracker, ALPHA, BETA, LAMBDA1, LAMBDA2
from .precise import PreciseProducts
from .frames import EarthOrientation, FrameEpoch, Environment
from .ephemeris import DE440
from .measurement import geometry, enu_matrix
from .antenna import load_calibrations, corrections
from .station_models import troposphere, station_displacement, read_loading, reference_coordinate
from .sp3 import epoch_tag
from .orbit_forces import OrbitForceModel
from .propagation import propagate
from .network_square_root import Block, require_connected

STATIONS = {"BRUX": "BRUX00BEL", "HOB2": "HOB200AUS", "KOUR": "KOUR00GUF",
            "ABMF": "ABMF00GLP", "KOUG": "KOUG00GUF", "DJIG": "DJIG00DJI",
            "NNOR": "NNOR00AUS", "MAS1": "MAS100ESP"}
START = 43200
INTERVAL = 300
EPOCHS = 12
MANIFESTS = ("manifest.json", "rinex3_manifest.json", "support_manifest.json",
             "kour_campaign_manifest.json", "stage4_manifest.json")


def make_rows():
    manifests = {name: json.loads((DATA/name).read_text()) for name in MANIFESTS}
    for manifest in manifests.values():
        for entry in manifest["files"]:
            if sha(ROOT/entry["path"]) != entry["sha256"]:
                raise ValueError("Changed network fixture input")
    # Also verify the gravity coefficients used by the variational basis.
    dynamic_manifest = json.loads((DYN_DATA/"manifest.json").read_text())
    for entry in dynamic_manifest["files"]:
        if sha(ROOT/entry["path"]) != entry["sha256"]:
            raise ValueError("Changed dynamics input")
    origin = epoch_tag("* 2026 8 2 0 0 0")
    eop = EarthOrientation(DYN_DATA/"finals2000A.all")
    products = PreciseProducts(
        [DATA/f"IGS0OPSRAP_2026{day}0000_01D_15M_ORB.SP3.gz" for day in (213, 214)],
        [DATA/f"IGS0OPSRAP_2026{day}0000_01D_05M_CLK.CLK.gz" for day in (213, 214)],
        origin, eop, missing_clock_time_system="GPS")
    ephemeris = DE440(DYN_DATA/"de440s.bsp")
    navigation = read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    all_rows, metadata = [], {}
    for station, marker in STATIONS.items():
        tracker = ArcTracker()
        selected = []
        native = 0
        with text_stream(DATA/f"{marker}_R_20262140000_01D_30S_MO.rnx.gz") as stream:
            meta = header(stream)
            pair = choose_signals(meta.types["G"])
            for epoch in epochs(stream, meta):
                t = (epoch.gps_ns-origin)/1e9
                if t > START+(EPOCHS-1)*INTERVAL:
                    break
                native += 1
                tracker.observe_epoch_event(epoch.gps_ns, epoch.satellites, epoch.flag)
                if epoch.flag == 6:
                    continue
                records = []
                for sat, obs in epoch.satellites.items():
                    data = combinations(obs, pair)
                    if data is None:
                        continue
                    arc = tracker.update(epoch.gps_ns, sat, data, epoch.flag)
                    if not data["half_cycle"]:
                        records.append((sat, data, arc))
                if START <= t and (t-START) % INTERVAL == 0:
                    selected.append((epoch.gps_ns, records))
        if len(selected) != EPOCHS:
            raise ValueError(f"{station}: missing requested epochs")
        with (DATA/"psd_IGc20.snx").open() as stream:
            if any(station in line.split() for line in stream):
                raise ValueError("Unsupported station postseismic terms")
        reference, solution = reference_coordinate(DATA/"IGc20.ssc", DATA/"soln_IGc20.snx",
                                                    station, datetime(2026, 8, 2, 12))
        eccentricity = enu_matrix(reference).T @ np.array(meta.antenna_hen)[[1, 2, 0]]
        loading = read_loading(DATA/"FES2014b.BLQ", station)
        sat_cal, rx_cal = load_calibrations(DATA/"igs20.atx", [meta.antenna], origin)
        windup, rejections, initial_clocks = {}, {}, []

        def reject(reason):
            rejections[reason] = rejections.get(reason, 0)+1

        for ei, (tag, observations) in enumerate(selected):
            t = (tag-origin)/1e9
            receiver = reference+eccentricity+station_displacement(reference, t, products.epoch, ephemeris, loading)
            candidates, b = [], []
            for sat, data, arc in observations:
                nav = [r for r in navigation.get(sat, []) if 0 <= tag-r["gps_ns"] <= 4*3600*10**9]
                if not nav or nav[-1]["health"] != 0:
                    reject("navigation_health_or_age")
                    continue
                if sat not in sat_cal:
                    reject("satellite_antenna")
                    continue
                try:
                    g = geometry(products, sat, t, receiver)
                except (ValueError, KeyError) as error:
                    reject("geometry_"+str(error))
                    continue
                if g["elevation_rad"] < np.deg2rad(10):
                    reject("elevation_below_10deg")
                    continue
                hydro, _ = troposphere(receiver, g["elevation_rad"], 214+t/86400)
                candidates.append((sat, data, arc))
                b.append(data["code_if_m"]-g["modeled_code_without_trop_m"]-hydro)
            if len(candidates) < 5:
                raise ValueError(f"{station}: fewer than five satellites in epoch {ei}")
            clock = float(np.median(b))
            initial_clocks.append(clock)
            for sat, data, arc in candidates:
                g = geometry(products, sat, t, receiver, clock)
                hydro, mw = troposphere(receiver, g["elevation_rad"], 214+t/86400)
                sun, _ = ephemeris.sun_moon_m(products.epoch.tdb_seconds(g["transmit_s"]))
                rotation = products.epoch.celestial_to_terrestrial(g["receive_s"])
                antenna, phase = corrections(g, receiver, rx_cal[meta.antenna], sat_cal[sat], sun, rotation)
                key = (sat, arc)
                if key in windup:
                    phase += np.floor(windup[key]-phase+.5)
                windup[key] = phase
                base = g["modeled_code_without_trop_m"]+hydro+antenna
                all_rows.append({"station": station, "satellite": sat, "epoch": ei, "time_s": t,
                    "arc": f"{station}:{sat}:{arc}", "elevation": g["elevation_rad"],
                    "los_inertial": rotation.T@g["los_ecef"], "transmit_s": g["transmit_s"],
                    "wet_mapping": mw, "code": data["code_if_m"]-base,
                    "phase": data["phase_if_m"]-base-(ALPHA*LAMBDA1+BETA*LAMBDA2)*phase})
        metadata[station] = {"header": asdict(meta), "signals": asdict(pair), "reference_solution": solution,
            "fixed_xyz_m": reference.tolist(), "native_epochs_read": native, "rejections": rejections,
            "initial_receiver_clocks_m": initial_clocks,
            "arc_events_in_window": [e for e in tracker.events if origin+START*10**9 <= e["gps_ns"] <= origin+(START+(EPOCHS-1)*INTERVAL)*10**9]}
        print(f"{station}: {sum(r['station']==station for r in all_rows)} links", flush=True)
    # Stage 2 physical variational bases, starting one second before the first
    # receiver epoch so that all transmit times are bracketed.
    base_time = START-1
    environment = Environment(FrameEpoch(origin+base_time*10**9, eop), ephemeris, EPOCHS*INTERVAL)
    model = OrbitForceModel(environment, DYN_DATA/"EGM2008_degree12.gfc")
    grid = np.arange(0., EPOCHS*INTERVAL+1., 60.)
    satellites = sorted({r["satellite"] for r in all_rows})
    for sat in satellites:
        result = propagate(products.state(sat, base_time), grid, model)
        phi = CubicSpline(grid, result.state_transition, extrapolate=False)
        for row in all_rows:
            if row["satellite"] == sat:
                row["orbit_partial"] = row["los_inertial"]@phi(row["transmit_s"]-base_time)[:3]
    return all_rows, {"stations": metadata, "frame": products.frame,
        "variational_epoch_gpst": "2026-08-02T11:59:59", "input_manifests": manifests,
        "dynamic_manifest": dynamic_manifest, "satellites": satellites}


def build_system(rows, reference="BRUX", split=None, orbit_prior_factor=1.):
    """Identical linear rows/priors for both solvers; receiver reference is exact.

    Split is (arc_name, first_new_epoch), supplied as a known synthetic event.
    Orbit priors are 100 m / 0.1 m/s; wet delay priors 0.3 m with 0.03 m
    knot difference. They regularize an underconstrained algebra fixture.
    """
    rows = [dict(r) for r in rows]
    for row in rows:
        if split and row["arc"] == split[0] and row["epoch"] >= split[1]:
            row["arc"] += ":injected"
    sats = sorted({r["satellite"] for r in rows})
    stations = sorted({r["station"] for r in rows})
    counts = {}
    for row in rows:
        counts[row["arc"]] = counts.get(row["arc"], 0)+1
    arcs = sorted(a for a, count in counts.items() if count >= 3)
    names = [f"orbit:{sat}:{axis}" for sat in sats for axis in ("x", "y", "z", "vx", "vy", "vz")]
    names += [f"wet:{s}:{k}" for s in stations for k in (0, 1)]
    names += ["ambiguity:"+a for a in arcs]
    index = {name: i for i, name in enumerate(names)}
    n = len(names)
    blocks, locals_by_epoch, labels, offsets = [], [], [], {}
    for ei in range(EPOCHS):
        selected = [r for r in rows if r["epoch"] == ei]
        require_connected([(r["station"], r["satellite"]) for r in selected], reference)
        local_names = [f"clock:{ei}:R:{s}" for s in sorted({r["station"] for r in selected}) if s != reference]
        local_names += [f"clock:{ei}:S:{s}" for s in sorted({r["satellite"] for r in selected})]
        local_index = {name: i for i, name in enumerate(local_names)}
        retained, local, target, sigma = [], [], [], []
        for row in selected:
            v, l = np.zeros(n), np.zeros(len(local_names))
            first = index[f"orbit:{row['satellite']}:x"]
            v[first:first+6] = row["orbit_partial"]
            f = ei/(EPOCHS-1)
            v[index[f"wet:{row['station']}:0"]] = (1-f)*row["wet_mapping"]
            v[index[f"wet:{row['station']}:1"]] = f*row["wet_mapping"]
            if row["station"] != reference:
                l[local_index[f"clock:{ei}:R:{row['station']}"]] = 1.
            l[local_index[f"clock:{ei}:S:{row['satellite']}"]] = -1.
            for kind, noise in (("code", .9), ("phase", .009)):
                if kind == "phase" and row["arc"] not in arcs:
                    continue
                vector = v.copy()
                y = row[kind]
                if kind == "phase":
                    offsets.setdefault(row["arc"], row["phase"]-row["code"])
                    y -= offsets[row["arc"]]
                    vector[index["ambiguity:"+row["arc"]]] = 1.
                retained.append(vector)
                local.append(l.copy())
                target.append(y)
                sigma.append(noise/np.sin(row["elevation"]))
                labels.append({k: row[k] for k in ("station", "satellite", "epoch", "arc", "elevation")}|{"kind": kind})
        blocks.append(Block(np.array(retained), np.array(local), np.array(target), np.array(sigma)))
        locals_by_epoch.append(local_names)
    c, z, s = [], [], []
    for name in names:
        if name.startswith("ambiguity:"):
            continue
        v = np.zeros(n)
        v[index[name]] = 1.
        c.append(v)
        z.append(0.)
        s.append((.1 if name.split(":")[-1].startswith("v") else 100.)*orbit_prior_factor
                 if name.startswith("orbit:") else .3)
    for station in stations:
        v = np.zeros(n)
        v[index[f"wet:{station}:0"]] = -1.
        v[index[f"wet:{station}:1"]] = 1.
        c.append(v)
        z.append(0.)
        s.append(.03)
    return blocks, (np.array(c), np.array(z), np.array(s)), names+sum(locals_by_epoch, []), labels, {
        "reference": reference, "retained_parameters": n, "phase_rows_excluded_short_arc": sum(count for count in counts.values() if count < 3),
        "ambiguity_origins_m": offsets, "local_names": locals_by_epoch, "orbit_prior_factor": orbit_prior_factor}
