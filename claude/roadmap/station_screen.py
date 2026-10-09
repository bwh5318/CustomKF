"""Guarded station screening for network expansion (roadmap step 5). No SP3/CLK input.

    listing:  python -m customkf.guard -- claude.roadmap.station_screen listing --day 2026-08-02
    headers:  python -m customkf.guard -- claude.roadmap.station_screen headers --day 2026-08-02 --batch 0 --batches 8
    geometry: python -m customkf.guard -- claude.roadmap.station_screen geometry --day 2026-08-02 --add 11 [--allow-c1c]

listing  : public BKG daily observation listing -> candidate 30 s MO markers (claude/data/screen<DOY>/listing.html).
headers  : 32 KB header range per candidate; records signal compatibility (C1W pair, or C1C-only needing
           C1C-C1W satellite biases), exact type-mean antenna calibration, IGc20 coordinate interval, PSD, BLQ.
geometry : generalization of Astra's customkf.plan_stage5b screen (clock-centred line-of-sight information,
           10 deg mask, sin^2 weights) over a 24 h broadcast grid; greedy additions to the frozen 14 stations.
Screening only: it predicts neither orbit error nor observation quality.
"""
import argparse
from datetime import datetime, timedelta
import gzip
import io
import json
import os
from pathlib import Path
import re
import subprocess
import numpy as np
from customkf.prepare_stage2 import ROOT, CURL, sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import header, read_gps_navigation
from customkf.preprocess import choose_signals
from customkf.antenna import load_calibrations
from customkf.sp3 import epoch_tag
from customkf.station_models import reference_coordinate, read_loading
from customkf.measurement import enu_matrix
from customkf.broadcast import select_fit_record, position
from claude.roadmap.common import write_json
from claude.roadmap.long_prepare import STATIONS

BKG = "https://igs.bkg.bund.de/root_ftp/IGS/obs"


def folder_for(day):
    date = datetime.strptime(day, "%Y-%m-%d")
    out = ROOT/"claude/data"/("screen"+date.strftime("%j"))
    out.mkdir(parents=True, exist_ok=True)
    return date, out


def curl(url, path, limit, sample=False):
    args = [CURL, "--fail", "--location", "--silent", "--show-error", "--max-time", "30", "--max-filesize", str(limit)]
    if sample:
        args += ["--range", "0-32767"]
    done = subprocess.run(args+[url, "-o", str(path)], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if done.returncode:
        raise RuntimeError(done.stderr.strip())


def listing(args, run):
    date, out = folder_for(args.day)
    path = out/"listing.html"
    if not path.exists():
        curl(f"{BKG}/{date.year}/{date.strftime('%j')}/", path, 4*2**20)
    stamp = date.strftime("%Y%j")
    markers = sorted(set(re.findall(r"([A-Z0-9]{9})_R_"+stamp+r"0000_01D_30S_MO\.crx\.gz", path.read_text(errors="replace"))))
    write_json(out/"candidates.json", dict(day=args.day, listing_sha256=sha(path), markers=markers))
    print(len(markers), "candidate markers", flush=True)


def check_header(marker, date, out):
    stamp = date.strftime("%Y%j")
    sample = out/"headers"/(marker+".gz")
    sample.parent.mkdir(exist_ok=True)
    if not sample.exists():
        curl(f"{BKG}/{date.year}/{date.strftime('%j')}/{marker}_R_{stamp}0000_01D_30S_MO.crx.gz", sample, 2**20, True)
    lines, started = [], False
    with gzip.open(sample, "rt", errors="replace") as f:
        try:
            for line in f:
                if "RINEX VERSION / TYPE" in line:
                    started = True
                if started:
                    lines.append(line)
                if "END OF HEADER" in line:
                    break
        except (EOFError, OSError):
            pass
    record = dict(marker=marker, header_sha256=sha(sample))
    if not lines or "END OF HEADER" not in lines[-1]:
        return record | dict(status="rejected", reason="incomplete header sample")
    try:
        meta = header(io.StringIO("".join(lines)), allow_declared_phase_shifts=True)
    except ValueError as error:
        return record | dict(status="rejected", reason="header: "+str(error))
    types = set(meta.types.get("G", []))
    record.update(antenna=meta.antenna, receiver=meta.receiver, interval_s=meta.interval_s, gps_types=sorted(types))
    try:
        choose_signals(sorted(types))
        record["signals"] = "c1w_pair"
    except ValueError:
        if {"C1C", "C2W", "L1C", "L2W"} <= types:
            record["signals"] = "c1c_only_needs_code_bias"
        else:
            return record | dict(status="rejected", reason="no supported GPS dual-frequency signal pair")
    station = marker[:4]
    try:
        load_calibrations(DATA/"igs20.atx", [meta.antenna], epoch_tag(date.strftime("* %Y %m %d 11 59 50")))
        if station in (DATA/"psd_IGc20.snx").read_text():
            raise ValueError("station has a post-seismic deformation model")
        xyz, _ = reference_coordinate(DATA/"IGc20.ssc", DATA/"soln_IGc20.snx", station, date+timedelta(hours=12))
        read_loading(DATA/"FES2014b.BLQ", station)
    except ValueError as error:
        return record | dict(status="rejected", reason=str(error))
    if meta.time_system not in ("GPS", ""):
        return record | dict(status="rejected", reason="time system "+str(meta.time_system))
    return record | dict(status="compatible" if record["signals"] == "c1w_pair" else "compatible_with_code_biases",
                         xyz=xyz.tolist(), approximate_position_offset_m=float(np.linalg.norm(np.array(meta.approximate_xyz)-xyz)) if len(meta.approximate_xyz) == 3 else None)


def headers(args, run):
    date, out = folder_for(args.day)
    markers = json.loads((out/"candidates.json").read_text())["markers"]
    chosen = markers[args.batch::args.batches]
    results = {}
    for marker in chosen:
        try:
            results[marker] = check_header(marker, date, out)
        except RuntimeError as error:
            results[marker] = dict(marker=marker, status="fetch_failed", reason=str(error))
        print(marker, results[marker]["status"], results[marker].get("reason", results[marker].get("signals")), flush=True)
    write_json(out/f"headers_{args.batch:02d}_of_{args.batches:02d}.json", results)


def geometry(args, run):
    date, out = folder_for(args.day)
    screened = {}
    for path in sorted(out.glob("headers_*_of_*.json")):
        screened.update(json.loads(path.read_text()))
    allowed = ("compatible", "compatible_with_code_biases") if args.allow_c1c else ("compatible",)
    base = list(STATIONS)
    candidates = {m[:4]: (m, np.array(v["xyz"])) for m, v in screened.items() if v["status"] in allowed and m[:4] not in base}
    for s in base:
        xyz, _ = reference_coordinate(DATA/"IGc20.ssc", DATA/"soln_IGc20.snx", s, date+timedelta(hours=12))
        candidates.setdefault(s, (STATIONS[s], xyz))
    stamp = date.strftime("%Y%j")
    nav_path = DATA/f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"
    if not nav_path.exists():
        nav_path = ROOT/"claude/data"/("day"+date.strftime("%j"))/nav_path.name
    nav = read_gps_navigation(nav_path)
    origin = epoch_tag((date-timedelta(seconds=10)).strftime("* %Y %m %d %H %M %S"))
    cutoff = epoch_tag((date+timedelta(days=1)).strftime("* %Y %m %d 00 00 00"))
    times = np.arange(10., 86400., 900.)
    sats, states = [], []
    for sat, records in sorted(nav.items()):
        try:
            states.append([position(select_fit_record(records, origin+int(t*1e9), available_before_ns=cutoff), origin+int(t*1e9)) for t in times])
            sats.append(sat)
        except ValueError:
            pass
    states = np.array(states)
    design = {}
    for station, (_, xyz) in candidates.items():
        delta = states-xyz
        u = delta/np.linalg.norm(delta, axis=2)[:, :, None]
        sine = u@enu_matrix(xyz)[2]
        design[station] = (np.where(sine >= np.sin(np.deg2rad(10)), sine**2, 0.), u)

    def information(stations):
        w = np.array([design[s][0] for s in stations])
        u = np.array([design[s][1] for s in stations])
        mean = np.sum(w[:, :, :, None]*u, axis=0)/np.maximum(w.sum(axis=0)[:, :, None], 1e-30)
        d = u-mean
        return np.einsum("nse,nsei,nsej->seij", w, d, d)

    def score(stations):
        return float(np.sum(np.linalg.slogdet(information(stations)+np.eye(3)*1e-6)[1]))

    def coverage(stations):
        counts = np.sum([design[s][0] > 0 for s in stations], axis=0)
        return dict(median_sites=float(np.median(counts)), fraction_epochs_below_3_sites=float(np.mean(counts < 3)),
                    worst_satellite_fraction_below_3=float(np.max(np.mean(counts < 3, axis=1))))

    selected = list(base)
    steps = [dict(selected=None, score=score(selected), coverage=coverage(selected))]
    for _ in range(args.add):
        ranked = sorted(((score(selected+[s]), s) for s in candidates if s not in selected), reverse=True)
        best, station = ranked[0]
        selected.append(station)
        steps.append(dict(selected=station, marker=candidates[station][0], signals=screened.get(candidates[station][0], {}).get("signals"),
                          score=best, coverage=coverage(selected), alternatives=[dict(station=s, score=v) for v, s in ranked[:6]]))
        print(station, round(best, 2), steps[-1]["coverage"], flush=True)
    write_json(Path(os.environ["CUSTOMKF_RUN_DIR"])/"geometry.json", dict(scope="prospective geometric screen, not an orbit-error prediction",
               day=args.day, allow_c1c=args.allow_c1c, candidates=len(candidates)-len(base), steps=steps,
               selected=selected, selected_markers=[candidates[s][0] for s in selected]))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("listing", "headers", "geometry"))
    parser.add_argument("--day", required=True)
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--batches", type=int, default=1)
    parser.add_argument("--add", type=int, default=11)
    parser.add_argument("--allow-c1c", action="store_true")
    args = parser.parse_args()
    dict(listing=listing, headers=headers, geometry=geometry)[args.mode](args, Path(os.environ["CUSTOMKF_RUN_DIR"]))


if __name__ == "__main__":
    main()
