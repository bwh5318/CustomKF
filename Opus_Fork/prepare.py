"""Fixture preparation with previous-day navigation and per-epoch LNAV eligibility.

    python -m Opus_Fork.guard --profile fork8 --timeout 900 --label prepare -- Opus_Fork.prepare \
        --day 2026-08-02 --start 00:00 --epochs 144 --network 25 --previous-day-nav --per-epoch-nav

Forked from `claude/roadmap/long_prepare.py` (hash in FORKED_FROM). The observation selection,
arc tracking, 10-degree cutoff, station models, antenna calibration, broadcast screening and
fixture freezing are unchanged; `--check-parity` reproduces a reference fixture byte for byte
to prove it.

Two changes, both measured in `results/nav_coverage.json` before being written:

**`--previous-day-nav`.** The frozen rule needs an eligible four-hour LNAV fit at every solve
epoch including the -0.2 s light-time offset at the arc start. At a 00:00 start that offset
lands in the previous day, which the day's own file cannot cover, so G18 and G29 each fail
exactly **one** check of 288 and are dropped entirely. Merging the previous day's broadcast
file recovers G05, G18 and G29: **27 -> 30 satellites**. Records are de-duplicated on
(toc, week, toe, IODE) and the previous day's file is a declared extra input.

**`--per-epoch-nav`.** Eligibility was all-or-nothing: one missing ephemeris anywhere in 24 h
removed a satellite from the whole arc. G02 fails 23 of 288 checks because of a mid-day
ephemeris gap and loses all 144 epochs for it. With this flag a satellite needs an eligible
record only at the arc start, which its seed genuinely requires; elsewhere the rows at
uncovered epochs are dropped and the rest of the arc is kept. That takes G02 from 0 to 133
epochs and the eligible set to **31 of 32**.

G13 stays excluded either way: it is flagged unhealthy in the broadcast for the whole day, so
the rule is doing its job. A product should mark it, not silently omit it, and the fixture
records it under `rejected_satellites` with the reason.

Inputs resolve through the single store's index, hash-verified, then Astra's pinned manifests,
so a day acquired into `Opus_Fork/datastore/` works with no manifest edit anywhere.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta
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

from .fetch import CORE_14, NETWORK_25
from .paths import STORE
from .store import load as load_store, resolve

FORKED_FROM = {"claude/roadmap/long_prepare.py": "eb5ab8640a7fac214c782398bd30947d04f0a5c3f3f88bbef2ca37066bd020e6"}
STEP = 600
STATIONS = {m[:4]: m for m in NETWORK_25}


def station_markers(entries):
    """{station: marker} in the given order. A four-character entry names a frozen-network station; a nine-character
    entry is any RINEX 3 marker, whose first four characters name the station (5 Oct 2026, network tests)."""
    out = {}
    for entry in entries:
        if len(entry) == 9:
            out[entry[:4]] = entry
        else:
            out[entry] = STATIONS[entry]          # KeyError for an unknown four-character name, as before
    return out


# Directory precedence for resolving an input basename. Several genuinely different files
# share a basename on this machine: PIMO's day-214 observation file exists as two distinct
# byte streams, one under claude/data/day214 (the one Astra's fixture read) and another under
# claude/data/acquired and claude/data/stage3-mirror. They decode to identical observations,
# but a fixture must record exactly which file it read, so resolution is by declared
# precedence and a genuine tie is an error rather than whichever the scan saw last.
PRECEDENCE = ("data/stage3", "data/stage2", "data/stage0", "claude/data/day", "Opus_Fork/datastore")
EXCLUDED = ("claude/data/acquired", "claude/data/stage3-mirror", "claude/data/screen")


def _rank(relative):
    for i, prefix in enumerate(PRECEDENCE):
        if relative.startswith(prefix):
            return i
    return len(PRECEDENCE)


def input_map(day, previous_day=None):
    """{basename: (path, sha256)} resolved by declared precedence, never by scan order."""
    dates = {day} | ({previous_day} if previous_day else set())
    candidates = {}
    for entry in load_store()["entries"].values():
        if entry["date"] is not None and entry["date"] not in dates:
            continue
        if entry["role"].startswith("reference_"):
            continue                      # estimation never sees a reference product
        relative = entry["path"].replace("\\", "/")
        if not Path(entry["path"]).is_absolute():
            pass
        else:
            try:
                relative = Path(entry["path"]).relative_to(ROOT).as_posix()
            except ValueError:
                continue                  # outside the repository: references only
        if any(relative.startswith(x) for x in EXCLUDED):
            continue
        candidates.setdefault(entry["name"], []).append((_rank(relative), relative, entry["sha256"]))
    for manifest in list(DATA.glob("*manifest.json"))+[DYN/"manifest.json"]:
        for entry in json.loads(manifest.read_text()).get("files", []):
            relative = entry["path"].replace("\\", "/")
            if any(relative.startswith(x) for x in EXCLUDED):
                continue
            name = Path(relative).name
            if not any(c[1] == relative for c in candidates.get(name, [])):
                candidates.setdefault(name, []).append((_rank(relative), relative, entry["sha256"]))
    found = {}
    for name, rows in candidates.items():
        rows.sort()
        best = rows[0][0]
        tied = {r[2] for r in rows if r[0] == best}
        if len(tied) > 1:
            raise ValueError("Ambiguous input, several distinct files at equal precedence: "+name+
                             " -> "+", ".join(r[1] for r in rows if r[0] == best))
        found[name] = (ROOT/rows[0][1], rows[0][2], rows[0][1])
    return found


def merge_navigation(previous_path, current_path, out_path):
    """Write one RINEX navigation file holding both days' records, verbatim.

    `claude/tools/dated_fixture.py` freezes a fixed key list and `restore()` reads exactly
    one `navigation_path`, so a fixture cannot carry two navigation files. Merging in
    `prepare()` alone would be worse than useless: the fixture would still name one file and
    every downstream worker would silently re-read only that one, so the seeds and the fit
    would disagree about which ephemerides exist.

    Records are copied line for line rather than re-formatted, so no numeric field is ever
    rewritten. Duplicates are dropped on (satellite, epoch field), first wins; since 28 Sep 2026 a duplicate whose
    full record differs is reported in the returned conflict list (Astra review M12). The header comes from the
    current day's file. Record lengths follow `customkf.rinex.read_gps_navigation`: five or
    four lines for GLONASS depending on version, four for SBAS, eight otherwise.
    """
    def records_of(path):
        with text_stream(path) as stream:
            first = stream.readline()
            version = float(first[:9])
            head = [first]
            for _ in range(2000):
                line = stream.readline()
                head.append(line)
                if "END OF HEADER" in line:
                    break
            else:
                raise ValueError("Missing navigation header end: "+str(path))
            blocks = []
            for line in stream:
                if not line.strip():
                    continue
                system = line[0]
                count = (5 if version >= 3.05 else 4) if system == "R" else (4 if system == "S" else 8)
                block = [line]+[stream.readline() for _ in range(count-1)]
                if any(not row for row in block):
                    raise ValueError("Truncated navigation block in "+str(path))
                blocks.append((line[:23], block))
            return head, blocks

    _, earlier = records_of(previous_path)
    header, later = records_of(current_path)
    seen, out, conflicts = {}, [], []
    for key, block in earlier+later:
        if key in seen:
            # Same (satellite, epoch) key: first wins, as before. A differing full record (issue, health, transmission
            # time ...) is now reported instead of silently dropped (Astra review M12). The policy is unchanged.
            if [l.rstrip("\r\n") for l in block] != [l.rstrip("\r\n") for l in seen[key]]:
                conflicts.append(key.strip())
            continue
        seen[key] = block
        out.append(block)
    text = "".join(line if line.endswith("\n") else line+"\n" for line in header)
    text += "".join(line if line.endswith("\n") else line+"\n" for block in out for line in block)
    data = text.encode("ascii")
    # Byte-deterministic gzip (fixed mtime, no stored filename), so identical content gives identical bytes.
    # A pinned path is never rewritten: identical decoded content keeps the existing bytes, different content
    # is refused (Astra review M12).
    import gzip as _gzip
    import io as _io
    buffer = _io.BytesIO()
    with _gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=buffer, mtime=0) as sink:
        sink.write(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        with _gzip.open(out_path, "rb") as existing:
            if existing.read() != data:
                raise ValueError(f"Refusing to overwrite {out_path}: existing merged navigation has different content")
    else:
        out_path.write_bytes(buffer.getvalue())
    return len(out), len(earlier), len(later), conflicts


def eligible_epochs(records, origin, epoch_count, cutoff_ns):
    """Epoch indices where the frozen rule resolves at both the -0.2 s and 0 s offsets."""
    ok = set()
    for ei in range(epoch_count):
        t = 10.+ei*STEP
        try:
            for offset in (-.2, 0.):
                select_fit_record(records, origin+int((t+offset)*1e9), available_before_ns=cutoff_ns)
            ok.add(ei)
        except ValueError:
            pass
    return ok


def prepare(day, start, epoch_count, station_subset, *, previous_day_nav, per_epoch_nav,
            min_epoch_fraction=0.5):
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
    previous = (date-timedelta(days=1)).strftime("%Y-%m-%d")
    previous_stamp = (date-timedelta(days=1)).strftime("%Y%j")
    last_time = 10+(epoch_count-1)*STEP
    duration = last_time+10
    stations = station_markers(station_subset)
    if "BRUX" not in stations or len(stations) < 6:
        raise ValueError("Require reference BRUX and at least six stations")

    available = input_map(day, previous if previous_day_nav else None)
    names = ["igs20.atx", "IGc20.ssc", "soln_IGc20.snx", "psd_IGc20.snx", "FES2014b.BLQ",
             f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"]
    names += [f"{m}_R_{stamp}0000_01D_30S_MO.rnx.gz" for m in stations.values()]
    names += ["finals2000A.all", "de440s.bsp", "EGM2008_degree12.gfc"]
    if previous_day_nav:
        names.append(f"BRDC00WRD_R_{previous_stamp}0000_01D_MN.rnx.gz")
    used = {}
    for name in names:
        if name not in available:
            raise ValueError("Input absent from the store and from every pinned manifest: "+name)
        path, digest, relative = available[name]
        if sha(path) != digest:
            raise ValueError("Input changed since it was indexed: "+str(path))
        # Repository-relative POSIX keys, matching the convention every existing fixture uses,
        # so an `inputs` block can be compared directly against an archived one.
        used[relative] = digest

    def path_for(name):
        return available[name][0]

    epoch = FrameEpoch(origin, EarthOrientation(path_for("finals2000A.all")))
    ephemeris = DE440(path_for("de440s.bsp"))
    model = OrbitForceModel(Environment(epoch, ephemeris, duration), path_for("EGM2008_degree12.gfc"))
    navigation = read_gps_navigation(path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"))
    nav_relative = available[f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"][2]
    nav_sources = [nav_relative]
    merged_record = None
    if previous_day_nav:
        # Materialise the merged navigation as a real file in the store, because the frozen
        # fixture format carries exactly one navigation path and every downstream worker
        # re-reads it. Content is deterministic, and since 27 Sep so are the bytes (fixed gzip mtime); an existing
        # file with the same content is kept byte-for-byte, and a different one is refused, never overwritten.
        merged = STORE/date.strftime("%Y%j")/f"BRDCMERGED_{previous_stamp}_{stamp}_MN.rnx.gz"
        counts = merge_navigation(path_for(f"BRDC00WRD_R_{previous_stamp}0000_01D_MN.rnx.gz"),
                                  path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"), merged)
        nav_relative = merged.relative_to(ROOT).as_posix()
        used[nav_relative] = sha(merged)
        merged_record = dict(path=nav_relative, sha256=used[nav_relative],
                             records_kept=counts[0], from_previous_day=counts[1],
                             from_target_day=counts[2], duplicate_key_conflicts=counts[3],
                             sources=[available[f"BRDC00WRD_R_{previous_stamp}0000_01D_MN.rnx.gz"][2],
                                      available[f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"][2]])
        nav_sources = merged_record["sources"]
        navigation = read_gps_navigation(merged)

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
                        selected.append({"station": station, "satellite": sat, "time_s": t,
                                         "epoch": int((t-10)/STEP), "arc": f"{station}:{sat}:{arc}",
                                         "origin_doy": origin_doy, "origin_second_of_day": origin_second,
                                         "observation": np.array([data["code_if_m"], data["phase_if_m"]])})
        if station in path_for("psd_IGc20.snx").read_text():
            raise ValueError("Unsupported station PSD")
        xyz, solution = reference_coordinate(path_for("IGc20.ssc"), path_for("soln_IGc20.snx"),
                                             station, date+timedelta(hours=12))
        loading = read_loading(path_for("FES2014b.BLQ"), station)
        eccentricity = enu_matrix(xyz).T@np.array(meta.antenna_hen)[[1, 2, 0]]
        displaced = {t: xyz+eccentricity+station_displacement(xyz, t, epoch, ephemeris, loading)
                     for t in sorted({r["time_s"] for r in selected})}
        for row in selected:
            row["receiver_xyz"] = displaced[row["time_s"]]
        raw.extend(selected)
        station_meta[station] = {"header": asdict(meta), "reference_solution": solution, "fixed_xyz": xyz.tolist()}

    sat_cal, rx_cal = load_calibrations(path_for("igs20.atx"),
                                       [m["header"]["antenna"] for m in station_meta.values()], origin)
    cutoff_ns = epoch_tag((date+timedelta(days=1)).strftime("* %Y %m %d %H %M %S"))
    records, seeds, rejected, coverage = {}, {}, {}, {}
    for sat in sorted({r["satellite"] for r in raw}):
        rows_for_sat = navigation.get(sat, [])
        try:
            if sat not in sat_cal:
                raise ValueError("Missing antenna")
            ok = eligible_epochs(rows_for_sat, origin, epoch_count, cutoff_ns)
            if 0 not in ok:
                raise ValueError("No eligible nominal LNAV fit at the arc start; the seed needs one")
            if not per_epoch_nav and len(ok) != epoch_count:
                raise ValueError(f"No eligible nominal four-hour LNAV fit at {epoch_count-len(ok)} epochs")
            if len(ok) < min_epoch_fraction*epoch_count:
                raise ValueError(f"Eligible at only {len(ok)} of {epoch_count} epochs")
            seeds[sat] = corrected_state(rows_for_sat, epoch, ephemeris, sat_cal[sat], origin, cutoff_ns)
            records[sat] = rows_for_sat
            coverage[sat] = sorted(ok)
        except ValueError as error:
            rejected[sat] = str(error)

    trajectories = {s: Trajectory(x, model, duration) for s, x in seeds.items()}
    products = NominalProducts(epoch, origin, records, trajectories, available_before_ns=cutoff_ns)
    rows, dropped_epochs = [], 0
    for row in raw:
        sat = row["satellite"]
        if sat not in records:
            continue
        if row["epoch"] not in set(coverage[sat]):
            dropped_epochs += 1
            continue
        g = geometry(products, sat, row["time_s"], row["receiver_xyz"])
        if g["elevation_rad"] >= np.deg2rad(10):
            row["sigma"] = np.array([.9, .009])/np.sin(g["elevation_rad"])
            rows.append(row)
    sats = sorted({r["satellite"] for r in rows})
    seeds = {s: seeds[s] for s in sats}
    context = {"epoch": epoch, "ephemeris": ephemeris, "model": model, "records": records,
               "sat_cal": sat_cal, "rx_cal": rx_cal, "stations": station_meta, "inputs": used,
               "rejected_satellites": rejected, "duration_s": duration, "epoch_count": epoch_count,
               "step_s": STEP, "profile": "nominal-cadence", "navigation_cutoff_ns": cutoff_ns,
               "origin_ns": origin, "day": day,
               # One real file, and it is in `inputs`, so the frozen restore() reads exactly
               # the merged record set this preparation used.
               "navigation_path": nav_relative}
    extra = dict(previous_day_nav=previous_day_nav, per_epoch_nav=per_epoch_nav,
                 navigation_sources=nav_sources, merged_navigation=merged_record,
                 rows_dropped_for_navigation=dropped_epochs,
                 epoch_coverage={s: len(coverage[s]) for s in sats},
                 partial_coverage={s: len(coverage[s]) for s in sats if len(coverage[s]) != epoch_count})
    return context, rows, seeds, extra


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--start", default="00:00")
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--network", choices=("14", "25"), default="25")
    parser.add_argument("--stations", default=None,
                        help="comma-separated four-character names (frozen network) or nine-character markers")
    parser.add_argument("--previous-day-nav", action="store_true")
    parser.add_argument("--per-epoch-nav", action="store_true")
    parser.add_argument("--check-parity", type=Path, help="fixture.json this run must reproduce exactly")
    args = parser.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    subset = args.stations.split(",") if args.stations else \
        [m[:4] for m in (NETWORK_25 if args.network == "25" else CORE_14)]
    context, rows, seeds, extra = prepare(args.day, args.start, args.epochs, subset,
                                          previous_day_nav=args.previous_day_nav,
                                          per_epoch_nav=args.per_epoch_nav)
    freeze(context, rows, seeds, folder/"fixture.json")
    report = dict(status="prepared", case="opus-fork-long-arc", guard="Opus_Fork",
                  forked_from=FORKED_FROM, day=args.day, start=args.start, epoch_count=args.epochs,
                  duration_s=context["duration_s"], fixture_sha256=sha(folder/"fixture.json"),
                  satellites=sorted(seeds), rejected_satellites=context["rejected_satellites"],
                  stations=sorted(context["stations"]), links=len(rows),
                  precise_products_used=False, **extra)
    if args.check_parity:
        old = json.loads(args.check_parity.read_text())
        new = json.loads((folder/"fixture.json").read_text())
        # `navigation_path` and `rejected_satellites` differ by construction when the new
        # flags are on (extra source file, more specific rejection messages), so parity is
        # judged on the scientific content: seeds, rows, inputs and the rejected *set*.
        descriptive = ("navigation_path", "rejected_satellites")
        report["parity"] = dict(
            seeds_equal=new["seeds"] == old["seeds"], rows_equal=new["rows"] == old["rows"],
            context_equal=all(new["context"].get(k) == v for k, v in old["context"].items()
                              if k not in descriptive),
            rejected_set_equal=set(new["context"]["rejected_satellites"]) ==
                               set(old["context"]["rejected_satellites"]),
            differing_context_keys=[k for k, v in old["context"].items()
                                    if k not in descriptive and new["context"].get(k) != v],
            reference=str(args.check_parity))
    write_json(folder/"step.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "rejected_satellites"}, indent=2), flush=True)
    print("rejected:", json.dumps(report["rejected_satellites"], indent=2), flush=True)


if __name__ == "__main__":
    main()
