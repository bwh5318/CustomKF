"""Guarded long-arc fixture preparation (roadmap step 3); no precise products.

    python -m customkf.guard -- claude.roadmap.long_prepare --day 2026-08-02 --start 12:00 --epochs 72 [--inputs M]

A parameterized copy of Astra's claude.tools.dated_stage5.prepare: same observation selection,
arc tracking, 10-degree cutoff, sigmas, station models, navigation eligibility and broadcast seeds,
but with an explicit start time of day and epoch count at the frozen 600 s cadence. The whole arc
must lie within the observation day's files (so 12:00 start -> at most 72 epochs, 00:00 -> 144).
The navigation cutoff is the end of the observation day, as in the dated noon profile.
--check-six reproduces the dated August-2 six-hour fixture exactly (start 12:00, 37 epochs).
"""
from datetime import datetime, timedelta
from dataclasses import asdict
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT, DATA as DYN, sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import header, text_stream, epochs, read_gps_navigation
from customkf.preprocess import ArcTracker, combinations, choose_signals
from customkf.sp3 import epoch_tag
from customkf.frames import EarthOrientation, FrameEpoch, Environment
from customkf.ephemeris import DE440
from customkf.orbit_forces import OrbitForceModel
from customkf.station_models import station_displacement, reference_coordinate, read_loading
from customkf.measurement import enu_matrix, geometry
from customkf.antenna import load_calibrations
from customkf.nominal_navigation import corrected_state, NominalProducts
from customkf.broadcast import select_fit_record
from customkf.stage5_pilot import forbid_precise_product_reads
from claude.tools.dated_observation import Trajectory
from claude.tools.dated_fixture import freeze
from claude.roadmap.common import write_json

STATIONS = {"BRUX": "BRUX00BEL", "HOB2": "HOB200AUS", "KOUR": "KOUR00GUF", "ABMF": "ABMF00GLP", "KOUG": "KOUG00GUF",
            "DJIG": "DJIG00DJI", "NNOR": "NNOR00AUS", "MAS1": "MAS100ESP", "DAV1": "DAV100ATA", "FALK": "FALK00FLK",
            "FAA1": "FAA100PYF", "GLPS": "GLPS00ECU", "YELL": "YELL00CAN", "GUAM": "GUAM00GUM"}
STEP = 600


def prepare(day, start, epoch_count, station_subset, input_manifest=None, extra_stations=None):
    date = datetime.strptime(day, "%Y-%m-%d")
    hour, minute = map(int, start.split(":"))
    first = date+timedelta(hours=hour, minutes=minute)
    origin_dt = first-timedelta(seconds=10)
    if first+timedelta(seconds=(epoch_count-1)*STEP) >= date+timedelta(days=1):
        raise ValueError("Arc must end inside the observation day's files")
    origin = epoch_tag(origin_dt.strftime("* %Y %m %d %H %M %S"))
    origin_doy = int(origin_dt.strftime("%j"))
    origin_second = float(origin_dt.hour*3600+origin_dt.minute*60+origin_dt.second)
    stamp = date.strftime("%Y%j")
    last_time = 10+(epoch_count-1)*STEP
    duration = last_time+10
    available = {**STATIONS, **(extra_stations or {})}
    stations = {s: available[s] for s in station_subset}
    if "BRUX" not in stations or len(stations) < 6:
        raise ValueError("Require reference BRUX and at least six stations")
    names = ["igs20.atx", "IGc20.ssc", "soln_IGc20.snx", "psd_IGc20.snx", "FES2014b.BLQ", f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"]
    names += [f"{m}_R_{stamp}0000_01D_30S_MO.rnx.gz" for m in stations.values()]
    pinned = {}
    for path in DATA.glob("*manifest.json"):
        for entry in json.loads(path.read_text()).get("files", []):
            pinned[entry["path"]] = entry["sha256"]
    for entry in json.loads((DYN/"manifest.json").read_text())["files"]:
        pinned[entry["path"]] = entry["sha256"]
    overrides = {}
    for manifest in (input_manifest or []):
        for entry in json.loads(Path(manifest).read_text())["files"]:
            p = ROOT/entry["path"]
            if p.name in overrides and overrides[p.name] != p:
                raise ValueError("Duplicate input basename")
            overrides[p.name] = p
            pinned[entry["path"]] = entry["sha256"]
    def path_for(name):
        return overrides.get(name, DATA/name)
    inputs = [path_for(name) for name in names]+[DYN/name for name in ("finals2000A.all", "de440s.bsp", "EGM2008_degree12.gfc")]
    used = {}
    for path in inputs:
        relative = path.relative_to(ROOT).as_posix()
        digest = sha(path)
        if pinned.get(relative) != digest:
            raise ValueError("Changed or unpinned input: "+relative)
        used[relative] = digest
    epoch = FrameEpoch(origin, EarthOrientation(DYN/"finals2000A.all"))
    ephemeris = DE440(DYN/"de440s.bsp")
    model = OrbitForceModel(Environment(epoch, ephemeris, duration), DYN/"EGM2008_degree12.gfc")
    navigation = read_gps_navigation(path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"))
    raw, station_meta = [], {}
    for station, marker in stations.items():
        tracker = ArcTracker()
        with text_stream(path_for(f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz")) as stream:
            meta = header(stream, allow_declared_phase_shifts=True)
            pair = choose_signals(meta.types["G"])
            selected = []
            for obs in epochs(stream, meta):
                t = (obs.gps_ns-origin)/1e9
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
                    if 10 <= t and (t-10) % STEP == 0 and not data["half_cycle"]:
                        selected.append({"station": station, "satellite": sat, "time_s": t, "epoch": int((t-10)/STEP),
                                         "arc": f"{station}:{sat}:{arc}", "origin_doy": origin_doy, "origin_second_of_day": origin_second,
                                         "observation": np.array([data["code_if_m"], data["phase_if_m"]])})
        if station in (DATA/"psd_IGc20.snx").read_text():
            raise ValueError("Unsupported station PSD")
        xyz, solution = reference_coordinate(DATA/"IGc20.ssc", DATA/"soln_IGc20.snx", station, date+timedelta(hours=12))
        loading = read_loading(DATA/"FES2014b.BLQ", station)
        eccentricity = enu_matrix(xyz).T@np.array(meta.antenna_hen)[[1, 2, 0]]
        displaced = {t: xyz+eccentricity+station_displacement(xyz, t, epoch, ephemeris, loading) for t in sorted({r["time_s"] for r in selected})}
        for row in selected:
            row["receiver_xyz"] = displaced[row["time_s"]]
        raw.extend(selected)
        station_meta[station] = {"header": asdict(meta), "reference_solution": solution, "fixed_xyz": xyz.tolist()}
    sat_cal, rx_cal = load_calibrations(DATA/"igs20.atx", [m["header"]["antenna"] for m in station_meta.values()], origin)
    records, seeds, rejected = {}, {}, {}
    cutoff_ns = epoch_tag((date+timedelta(days=1)).strftime("* %Y %m %d %H %M %S"))
    for sat in sorted({r["satellite"] for r in raw}):
        try:
            for t in np.arange(10., last_time+.1, STEP):
                for offset in (-.2, 0.):
                    select_fit_record(navigation.get(sat, []), origin+int((t+offset)*1e9), available_before_ns=cutoff_ns)
            if sat not in sat_cal:
                raise ValueError("Missing antenna")
            records[sat] = navigation[sat]
            seeds[sat] = corrected_state(navigation[sat], epoch, ephemeris, sat_cal[sat], origin, cutoff_ns)
        except ValueError as error:
            rejected[sat] = str(error)
    trajectories = {s: Trajectory(x, model, duration) for s, x in seeds.items()}
    products = NominalProducts(epoch, origin, records, trajectories, available_before_ns=cutoff_ns)
    rows = []
    for row in raw:
        if row["satellite"] not in records:
            continue
        g = geometry(products, row["satellite"], row["time_s"], row["receiver_xyz"])
        if g["elevation_rad"] >= np.deg2rad(10):
            row["sigma"] = np.array([.9, .009])/np.sin(g["elevation_rad"])
            rows.append(row)
    sats = sorted({r["satellite"] for r in rows})
    seeds = {s: seeds[s] for s in sats}
    context = {"epoch": epoch, "ephemeris": ephemeris, "model": model, "records": records, "sat_cal": sat_cal, "rx_cal": rx_cal,
               "stations": station_meta, "inputs": used, "rejected_satellites": rejected, "duration_s": duration,
               "epoch_count": epoch_count, "step_s": STEP, "profile": "nominal-cadence", "navigation_cutoff_ns": cutoff_ns,
               "origin_ns": origin, "day": day, "navigation_path": path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz").relative_to(ROOT).as_posix()}
    return context, rows, seeds


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--start", default="12:00")
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--stations", default=",".join(STATIONS))
    parser.add_argument("--inputs", type=Path, nargs="*")
    parser.add_argument("--extra-stations", default="", help="NAME=MARKER,... for stations beyond the frozen 14")
    parser.add_argument("--check-six", type=Path, help="dated six-hour fixture to reproduce exactly")
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    extra = dict(item.split("=") for item in args.extra_stations.split(",") if item)
    subset = args.stations.split(",")
    context, rows, seeds = prepare(args.day, args.start, args.epochs, subset, args.inputs, extra)
    freeze(context, rows, seeds, folder/"fixture.json")
    report = dict(status="prepared", case="claude-long-arc", day=args.day, start=args.start, epoch_count=args.epochs,
                  duration_s=context["duration_s"], fixture_sha256=sha(folder/"fixture.json"), satellites=sorted(seeds),
                  rejected_satellites=context["rejected_satellites"], stations=sorted(context["stations"]),
                  links=len(rows), precise_products_used=False)
    if args.check_six:
        old = json.loads(args.check_six.read_text())
        new = json.loads((folder/"fixture.json").read_text())
        assert new["seeds"] == old["seeds"], "Seeds differ"
        for key, value in old["context"].items():
            assert new["context"][key] == value, key
        assert new["rows"] == old["rows"], "Rows differ"
        report["dated_six_hour_fixture_reproduced_exactly"] = True
    write_json(folder/"step.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
