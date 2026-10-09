"""Guarded public-data acquisition for any day (roadmap step 4); generalizes claude.tools.dated_fetch.

    station: python -m customkf.guard --timeout 120 -- claude.roadmap.fetch_day station --day 2026-08-04 --marker BRUX00BEL
    product: python -m customkf.guard --timeout 120 -- claude.roadmap.fetch_day product --day 2026-08-04 --kind brdc|sp3|clk

Writes only claude/data/day<DOY>/ (same place as Astra's day-215 inputs) plus the guard log. Station files are
header-screened before and after decoding with the existing pinned RNXCMP (no software installation).
Cached artifacts are hash-verified instead of re-downloaded. Each artifact gets a <name>.json record.
"""
import argparse
from datetime import datetime, timezone, timedelta
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
from customkf.prepare_stage2 import ROOT, CURL, sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import header, text_stream
from customkf.preprocess import choose_signals
from customkf.antenna import load_calibrations
from customkf.sp3 import epoch_tag
from claude.tools.station_extra_fetch import DECODER, DECODER_SHA256

BKG = "https://igs.bkg.bund.de/root_ftp/IGS"
GPS_START = datetime(1980, 1, 6)


def fetch(url, path, limit, range_sample=False):
    args = [CURL, "--fail", "--location", "--silent", "--show-error", "--max-time", "90", "--max-filesize", str(limit)]
    if range_sample:
        args += ["--range", "0-32767"]
    done = subprocess.run(args+[url, "-o", str(path)], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if done.returncode:
        raise RuntimeError("Public data fetch failed: "+done.stderr.strip())
    if path.stat().st_size > limit:
        raise ValueError("Byte limit exceeded")


def screen(lines, day):
    meta = header(io.StringIO("".join(lines)), allow_declared_phase_shifts=True)
    pair = choose_signals(meta.types["G"])
    date = datetime.strptime(day, "%Y-%m-%d")
    load_calibrations(DATA/"igs20.atx", [meta.antenna], epoch_tag(date.strftime("* %Y %m %d 11 59 50")))
    if meta.interval_s not in (0, 30) or meta.time_system != "GPS":
        raise ValueError("Unexpected cadence/time system")
    return dict(marker=meta.marker, antenna=meta.antenna, receiver=meta.receiver, interval_s=meta.interval_s,
                time_system=meta.time_system, signal_pair=pair.__dict__)


def destination(day):
    date = datetime.strptime(day, "%Y-%m-%d")
    dest = ROOT/"claude/data"/("day"+date.strftime("%j"))
    dest.mkdir(parents=True, exist_ok=True)
    return date, dest


def cached(record_path, folder):
    record = json.loads(record_path.read_text())
    for e in record["files"]:
        assert sha(ROOT/e["path"]) == e["sha256"], e["path"]
    (folder/"acquisition.json").write_text(json.dumps(record, indent=2)+"\n")
    print("Verified cached", record_path.name, flush=True)


def station(args, folder):
    date, dest = destination(args.day)
    record_path = dest/(args.marker+".json")
    if record_path.exists():
        return cached(record_path, folder)
    assert sha(DECODER) == DECODER_SHA256
    stamp, doy = date.strftime("%Y%j"), date.strftime("%j")
    name = f"{args.marker}_R_{stamp}0000_01D_30S_MO.crx.gz"
    url = f"{BKG}/obs/{date.year}/{doy}/{name}"
    sample = folder/"header.gz"
    fetch(url, sample, 2**20, True)
    if sample.stat().st_size > 32768:
        raise ValueError("Server ignored header range")
    lines, started = [], False
    with gzip.open(sample, "rt") as f:
        try:
            for line in f:
                if "RINEX VERSION / TYPE" in line:
                    started = True
                if started:
                    lines.append(line)
                if "END OF HEADER" in line:
                    break
        except EOFError:
            pass
    if not lines or "END OF HEADER" not in lines[-1]:
        raise ValueError("Incomplete header")
    before = screen(lines, args.day)
    compressed, part = dest/name, dest/(name+".part")
    fetch(url, part, 12*2**20)
    part.replace(compressed)
    compact = folder/"input.crx"
    with gzip.open(compressed, "rb") as src, compact.open("wb") as out:
        size = 0
        while block := src.read(65536):
            size += len(block)
            if size > 40*2**20:
                raise ValueError("Compact size exceeded")
            out.write(block)
    output = dest/name.replace(".crx.gz", ".rnx.gz")
    part = output.with_suffix(".part")
    with compact.open("rb") as src, (folder/"decoder.log").open("wb") as log:
        child = subprocess.Popen([str(DECODER)], stdin=src, stdout=subprocess.PIPE, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            size = 0
            with gzip.open(part, "wb", compresslevel=1) as out:
                while block := child.stdout.read(65536):
                    size += len(block)
                    if size > 160*2**20:
                        raise ValueError("Decoded size exceeded")
                    out.write(block)
            if child.wait(timeout=5):
                raise ValueError("Decoder failed")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
    compact.unlink()
    part.replace(output)
    with text_stream(output) as f:
        lines = []
        for line in f:
            lines.append(line)
            if "END OF HEADER" in line:
                break
    after = screen(lines, args.day)
    assert after == before
    record = dict(status="header_compatible_not_observation_acceptance", date=args.day, retrieved_utc=datetime.now(timezone.utc).isoformat(),
                  url=url, header=after, decoder_sha256=DECODER_SHA256, decoded_bytes=size,
                  files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p), bytes=p.stat().st_size) for p in (compressed, output)])
    record_path.write_text(json.dumps(record, indent=2)+"\n")
    (folder/"acquisition.json").write_text(json.dumps(record, indent=2)+"\n")
    print(args.marker, after, flush=True)


def product(args, folder):
    date, dest = destination(args.day)
    stamp, doy = date.strftime("%Y%j"), date.strftime("%j")
    week = (date-GPS_START).days//7
    name, url, limit = {
        "brdc": (f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz", f"{BKG}/BRDC/{date.year}/{doy}/", 4*2**20),
        "sp3": (f"IGS0OPSRAP_{stamp}0000_01D_15M_ORB.SP3.gz", f"{BKG}/products/{week}/", 2**20),
        "clk": (f"IGS0OPSRAP_{stamp}0000_01D_05M_CLK.CLK.gz", f"{BKG}/products/{week}/", 4*2**20),
    }[args.kind]
    record_path = dest/(name+".json")
    if record_path.exists():
        return cached(record_path, folder)
    if (DATA/name).exists():
        raise ValueError("Already present in data/stage3; use the pinned original instead: "+name)
    target, part = dest/name, dest/(name+".part")
    fetch(url+name, part, limit)
    with gzip.open(part, "rb") as f:
        head = f.read(4096)
    if args.kind == "sp3" and not (head.startswith(b"#c") or head.startswith(b"#d")):
        raise ValueError("Not an SP3-c/d file")  # IGS rapid orbits are SP3-c (#cP), like the pinned day-215 product
    if args.kind != "sp3" and b"RINEX VERSION / TYPE" not in head:
        raise ValueError("Not a RINEX file")
    part.replace(target)
    record = dict(status="product_acquired_not_validated", date=args.day, kind=args.kind, retrieved_utc=datetime.now(timezone.utc).isoformat(),
                  url=url+name, files=[dict(path=target.relative_to(ROOT).as_posix(), sha256=sha(target), bytes=target.stat().st_size)])
    record_path.write_text(json.dumps(record, indent=2)+"\n")
    (folder/"acquisition.json").write_text(json.dumps(record, indent=2)+"\n")
    print(name, record["files"][0], flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("station", "product"))
    parser.add_argument("--day", required=True)
    parser.add_argument("--marker")
    parser.add_argument("--kind", choices=("brdc", "sp3", "clk"))
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (station if args.mode == "station" else product)(args, folder)


if __name__ == "__main__":
    main()
