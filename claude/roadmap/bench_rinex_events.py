"""Guarded RINEX event screen for bench days (roadmap step 4). No SP3/CLK; no estimator.

    python -m customkf.guard -- claude.roadmap.bench_rinex_events --day 2026-08-04 --markers M1,M2,...

Astra's customkf.rinex.epochs refuses in-file metadata events (epoch flags 2-5) rather than guessing how to
apply them. This worker scans each station's daily file with that same parser. For any station whose file
cannot be read, it records the refusal and the raw event record lines, and writes
claude/data/day<DOY>/rinex_events.json. Under BENCH_PROTOCOL.md such a station counts as unavailable that
day, for every arm alike: excluded and disclosed, never substituted. Data-quality only; no scores are read.
"""
import argparse
from datetime import datetime
import gzip
import json
import os
from pathlib import Path
from customkf.prepare_stage2 import ROOT, sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import header, text_stream, epochs
from claude.roadmap.bench_data import day_folder, verified
from claude.roadmap.common import write_json


def raw_event_lines(path, limit=12):
    """Return the event line(s) with flags 2-5 and the records that follow them, from the raw text."""
    found = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", errors="replace") as f:
        in_header = True
        pending = 0
        for line in f:
            if in_header:
                in_header = "END OF HEADER" not in line
                continue
            if pending:
                found[-1]["records"].append(line.rstrip("\n"))
                pending -= 1
                continue
            if line.startswith(">") and len(line) > 31 and line[31] in "2345":
                count = int(line[32:35]) if line[32:35].strip().isdigit() else 0
                found.append(dict(event=line.rstrip("\n"), records=[]))
                pending = min(count, 40)
                if len(found) >= limit:
                    break
    return found


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--markers", required=True)
    args = parser.parse_args()
    stamp = datetime.strptime(args.day, "%Y-%m-%d").strftime("%Y%j")
    folder = day_folder(args.day)
    results = {}
    for marker in args.markers.split(","):
        name = f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz"
        path = DATA/name if (DATA/name).exists() else folder/name
        verified(path)
        try:
            with text_stream(path) as stream:
                meta = header(stream, allow_declared_phase_shifts=True)
                count = sum(1 for _ in epochs(stream, meta))
            results[marker] = dict(status="readable", epochs=count, sha256=sha(path))
        except ValueError as error:
            results[marker] = dict(status="unreadable_by_frozen_parser", error=str(error), sha256=sha(path),
                                   raw_events=raw_event_lines(path))
        print(marker, results[marker]["status"], results[marker].get("error", results[marker].get("epochs")), flush=True)
    report = dict(status="rinex_event_screen", day=args.day, stations=results,
                  unavailable=sorted(m for m, v in results.items() if v["status"] != "readable"),
                  rule="BENCH_PROTOCOL.md: a station unusable on a day is excluded for every arm that day and disclosed")
    write_json(folder/"rinex_events.json", report)
    write_json(Path(os.environ["CUSTOMKF_RUN_DIR"])/"rinex_events.json", report)


if __name__ == "__main__":
    main()
