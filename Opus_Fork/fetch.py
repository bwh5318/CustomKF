"""Public-data acquisition into the single store, with a no-download availability screen.

    availability: python -m Opus_Fork.guard --profile fork8 --timeout 900 --label screen \
                      -- Opus_Fork.fetch availability --day 2026-08-01 --markers 25
    station:      ... -- Opus_Fork.fetch station --day 2026-08-01 --marker BRUX00BEL
    product:      ... -- Opus_Fork.fetch product --day 2026-08-01 --kind brdc|sp3rap|sp3fin|clk

Forked from `claude/roadmap/fetch_day.py` (hash in FORKED_FROM) for two reasons: it writes to
`claude/data/day<DOY>/`, and it has no way to ask whether a day is available before committing
to downloads. The decoding, header screening and hash-record logic is unchanged, including the
pinned RNXCMP decoder and the rule that a cached artifact is hash-verified rather than
re-fetched.

Changes:

1. **Destination is `Opus_Fork/datastore/<YYYYDOY>/`**, so every acquisition this fork makes
   lands in the one store and nowhere else.
2. **`availability` mode** range-samples each marker's header (32 KiB) and reports existence,
   antenna calibration, coordinate solution and selected signal pair *without* downloading
   any observation data. A day can therefore be accepted or rejected before spending
   bandwidth, and a station whose signal pair changed between dates is caught up front, which
   the cross-date preflight identified as a real risk.
3. **IGS final orbits** are fetchable (`sp3fin`), not just rapid. Final is the reference the
   objective names.

The 25-station set is the frozen network from `claude/roadmap/STATIONS_RESULTS.md`: the
original 14 plus the 11 added by the greedy geometry screen.
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

from .paths import STORE, RESULTS

FORKED_FROM = {"claude/roadmap/fetch_day.py": "9b4497bcfd76aa1bf53d748ac1b2617a364367e8aea80357b567e4a597a9047f"}
BKG = "https://igs.bkg.bund.de/root_ftp/IGS"
GPS_START = datetime(1980, 1, 6)

CORE_14 = ("BRUX00BEL", "HOB200AUS", "KOUR00GUF", "ABMF00GLP", "KOUG00GUF", "DJIG00DJI",
           "NNOR00AUS", "MAS100ESP", "DAV100ATA", "FALK00FLK", "FAA100PYF", "GLPS00ECU",
           "YELL00CAN", "GUAM00GUM")
ADDED_11 = ("SGOC00LKA", "KOKB00USA", "SUTH00ZAF", "KIT300UZB", "KIRI00KIR", "NKLG00GAB",
            "MDO100USA", "EUR200CAN", "VACS00MUS", "PIMO00PHL", "CHPI00BRA")
NETWORK_25 = CORE_14+ADDED_11

PRODUCTS = {
    "brdc": ("BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz", "{base}/BRDC/{year}/{doy}/", 4*2**20),
    "sp3rap": ("IGS0OPSRAP_{stamp}0000_01D_15M_ORB.SP3.gz", "{base}/products/{week}/", 2**20),
    "sp3fin": ("IGS0OPSFIN_{stamp}0000_01D_15M_ORB.SP3.gz", "{base}/products/{week}/", 2**20),
    "clk": ("IGS0OPSRAP_{stamp}0000_01D_05M_CLK.CLK.gz", "{base}/products/{week}/", 4*2**20),
}


def fetch(url, path, limit, range_sample=False):
    args = [CURL, "--fail", "--location", "--silent", "--show-error", "--max-time", "90",
            "--max-filesize", str(limit)]
    if range_sample:
        args += ["--range", "0-32767"]
    done = subprocess.run(args+[url, "-o", str(path)], capture_output=True, text=True,
                          creationflags=subprocess.CREATE_NO_WINDOW)
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
    return dict(marker=meta.marker, antenna=meta.antenna, receiver=meta.receiver,
                interval_s=meta.interval_s, time_system=meta.time_system,
                signal_pair=pair.__dict__, antenna_hen=list(meta.antenna_hen))


def destination(day):
    date = datetime.strptime(day, "%Y-%m-%d")
    dest = STORE/date.strftime("%Y%j")
    dest.mkdir(parents=True, exist_ok=True)
    return date, dest


def cached(record_path, folder):
    record = json.loads(record_path.read_text())
    for e in record["files"]:
        assert sha(ROOT/e["path"]) == e["sha256"], e["path"]
    (folder/"acquisition.json").write_text(json.dumps(record, indent=2)+"\n")
    print("Verified cached "+record_path.name, flush=True)
    return record


def sample_header(marker, day, scratch):
    """Range-sample a marker's RINEX header only. Returns the screen or the failure reason."""
    date = datetime.strptime(day, "%Y-%m-%d")
    stamp, doy = date.strftime("%Y%j"), date.strftime("%j")
    name = f"{marker}_R_{stamp}0000_01D_30S_MO.crx.gz"
    url = f"{BKG}/obs/{date.year}/{doy}/{name}"
    path = scratch/(marker+".gz")
    try:
        fetch(url, path, 2**20, True)
    except RuntimeError as error:
        return dict(marker=marker, available=False, reason="fetch: "+str(error)[:160], url=url)
    if path.stat().st_size > 32768:
        return dict(marker=marker, available=False, reason="server ignored header range", url=url)
    lines, started = [], False
    try:
        with gzip.open(path, "rt") as f:
            for line in f:
                if "RINEX VERSION / TYPE" in line:
                    started = True
                if started:
                    lines.append(line)
                if "END OF HEADER" in line:
                    break
    except (EOFError, OSError) as error:
        return dict(marker=marker, available=True, compatible=False, reason="decompress: "+str(error)[:120], url=url)
    if not lines or "END OF HEADER" not in lines[-1]:
        return dict(marker=marker, available=True, compatible=False, reason="incomplete header", url=url)
    try:
        return dict(marker=marker, available=True, compatible=True, header=screen(lines, day), url=url)
    except (ValueError, KeyError) as error:
        return dict(marker=marker, available=True, compatible=False, reason=str(error)[:160], url=url)


def availability(args, folder):
    markers = NETWORK_25 if args.markers == "25" else (CORE_14 if args.markers == "14" else tuple(args.markers.split(",")))
    scratch = folder/"headers"
    scratch.mkdir(parents=True, exist_ok=True)
    rows = [sample_header(m, args.day, scratch) for m in markers]
    for row in rows:
        state = "OK " if row.get("compatible") else ("BAD" if row.get("available") else "ABS")
        pair = row.get("header", {}).get("signal_pair", {})
        detail = f"{pair.get('code1','')}+{pair.get('code2','')} {row.get('header',{}).get('antenna','')}" \
            if row.get("compatible") else row.get("reason", "")
        print(f"  {state} {row['marker']:10s} {detail}", flush=True)
    ok = [r for r in rows if r.get("compatible")]
    report = dict(status="availability_screen", day=args.day, markers=len(markers),
                  compatible=len(ok), unavailable=[r["marker"] for r in rows if not r.get("available")],
                  incompatible=[r["marker"] for r in rows if r.get("available") and not r.get("compatible")],
                  rows=rows, note="Header range-sample only; no observation data downloaded.")
    for name, (pattern, base, _) in PRODUCTS.items():
        date = datetime.strptime(args.day, "%Y-%m-%d")
        stamp = date.strftime("%Y%j")
        url = base.format(base=BKG, year=date.year, doy=date.strftime("%j"),
                          week=(date-GPS_START).days//7)+pattern.format(stamp=stamp)
        target = scratch/(name+".probe")
        try:
            fetch(url, target, 2**20, True)
            report.setdefault("products", {})[name] = dict(available=True, url=url, sampled_bytes=target.stat().st_size)
        except RuntimeError as error:
            report.setdefault("products", {})[name] = dict(available=False, url=url, reason=str(error)[:160])
        print(f"  {'OK ' if report['products'][name]['available'] else 'ABS'} product {name}", flush=True)
    for path in scratch.glob("*"):
        path.unlink()
    text = json.dumps(report, indent=2)+"\n"
    (folder/"availability.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/f"availability_{args.day}.json").write_text(text)
    print(f"\n{len(ok)} of {len(markers)} markers compatible on {args.day}", flush=True)
    pairs = {}
    for r in ok:
        key = r["header"]["signal_pair"]["code1"]+"+"+r["header"]["signal_pair"]["code2"]
        pairs[key] = pairs.get(key, 0)+1
    print("  signal pairs: "+", ".join(f"{k} x{v}" for k, v in sorted(pairs.items())), flush=True)


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
        child = subprocess.Popen([str(DECODER)], stdin=src, stdout=subprocess.PIPE, stderr=log,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
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
    record = dict(status="header_compatible_not_observation_acceptance", date=args.day,
                  retrieved_utc=datetime.now(timezone.utc).isoformat(), url=url, header=after,
                  decoder_sha256=DECODER_SHA256, decoded_bytes=size,
                  retrospective="Retrieved long after the observation day; this is not evidence "
                                "of availability at any rapid cutoff.",
                  files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
                         for p in (compressed, output)])
    record_path.write_text(json.dumps(record, indent=2)+"\n")
    (folder/"acquisition.json").write_text(json.dumps(record, indent=2)+"\n")
    print(f"{args.marker} {after['signal_pair']['code1']}+{after['signal_pair']['code2']} "
          f"{record['files'][1]['bytes']} bytes", flush=True)


def product(args, folder):
    date, dest = destination(args.day)
    stamp, doy = date.strftime("%Y%j"), date.strftime("%j")
    week = (date-GPS_START).days//7
    pattern, base, limit = PRODUCTS[args.kind]
    name = pattern.format(stamp=stamp)
    url = base.format(base=BKG, year=date.year, doy=doy, week=week)+name
    record_path = dest/(name+".json")
    if record_path.exists():
        return cached(record_path, folder)
    if (DATA/name).exists():
        raise ValueError("Already pinned in data/stage3; use the original instead: "+name)
    target, part = dest/name, dest/(name+".part")
    fetch(url, part, limit)
    with gzip.open(part, "rb") as f:
        head = f.read(4096)
    if args.kind.startswith("sp3") and not (head.startswith(b"#c") or head.startswith(b"#d")):
        raise ValueError("Not an SP3-c/d file")
    if not args.kind.startswith("sp3") and b"RINEX VERSION / TYPE" not in head:
        raise ValueError("Not a RINEX file")
    part.replace(target)
    record = dict(status="product_acquired_not_validated", date=args.day, kind=args.kind,
                  retrieved_utc=datetime.now(timezone.utc).isoformat(), url=url,
                  evaluation_only=args.kind.startswith("sp3") or args.kind == "clk",
                  files=[dict(path=target.relative_to(ROOT).as_posix(), sha256=sha(target),
                              bytes=target.stat().st_size)])
    record_path.write_text(json.dumps(record, indent=2)+"\n")
    (folder/"acquisition.json").write_text(json.dumps(record, indent=2)+"\n")
    print(f"{name} {record['files'][0]['bytes']} bytes", flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("availability", "station", "product"))
    parser.add_argument("--day", required=True)
    parser.add_argument("--marker")
    parser.add_argument("--markers", default="25", help="'25', '14', or a comma-separated marker list")
    parser.add_argument("--kind", choices=tuple(PRODUCTS))
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    {"availability": availability, "station": station, "product": product}[args.mode](args, folder)


if __name__ == "__main__":
    main()
