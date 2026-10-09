"""Per-date station lists for the network fixtures (PROTOCOL.md §5): each network's stations whose daily observation
file was acquired intact for that date. A station missing on a date is dropped for that date and reported.

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.networks.station_lists

Prints one line per network and date: `<network> <date> <comma-separated nine-character markers>`, then the
dropped stations on stderr. File existence only; nothing numerical.

Amendment A1: the estimator fixes BRUX's receiver clock as the datum, so S17's Hermitage site takes BRUX instead of
HERS (`networks.json` keeps the original selection record).
"""
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DATES = ("2026-06-06", "2026-06-20", "2026-06-23", "2026-07-06", "2026-07-23")
MINIMUM = {"S17": 15, "S50": 45}


def networks():
    selection = json.loads((HERE/"networks.json").read_text())
    from Opus_Fork.fetch import NETWORK_25
    markers25 = {m[:4]: m for m in NETWORK_25}
    s17 = [("BRUX", "BRUX00BEL") if e["station"] == "HERS" else (e["station"], e["marker"]) for e in selection["S17"]]
    assert ("BRUX", "BRUX00BEL") in s17 and len(s17) == 17
    s50 = [(s, markers25[s]) for s in selection["S50"]["base"]] + \
          [(e["station"], e["marker"]) for e in selection["S50"]["added"]]
    return {"S17": s17, "S50": s50}


def main():
    sys.stdout.reconfigure(newline=chr(10))      # plain LF on Windows, for the bash driver
    for name, stations in networks().items():
        for day in DATES:
            stamp = datetime.strptime(day, "%Y-%m-%d").strftime("%Y%j")
            folder = ROOT/"Opus_Fork/datastore"/stamp
            present = [s for s, m in stations if (folder/f"{m}_R_{stamp}0000_01D_30S_MO.rnx.gz").is_file()]
            missing = [s for s, _ in stations if s not in present]
            if len(present) < MINIMUM[name]:
                raise SystemExit(f"{name} {day}: only {len(present)} stations (need {MINIMUM[name]})")
            # Alphabetical by station, as every comparator fixture was prepared (row order follows the list).
            print(name, day, ",".join(m for s, m in sorted(stations) if s in present))
            if missing:
                print(f"{name} {day}: dropped (not acquired) {', '.join(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()
