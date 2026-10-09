"""Print receiver, antenna and GPS observation-type header lines (read-only text; no guard needed).

    C:\\anaconda\\python.exe claude\\tools\\show_obs_types.py
"""
import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKERS = ["GAMB00PYF", "PARC00CHL", "SYOG00ATA", "CAS100ATA", "SUTM00ZAF", "FAA100PYF", "KOUR00GUF", "BRUX00BEL"]
KEYS = ("REC # / TYPE / VERS", "ANT # / TYPE", "SYS / # / OBS TYPES", "SYS / PHASE SHIFT")


def header_lines(path):
    lines = []
    try:
        with gzip.open(path, "rt", errors="replace") as stream:
            for line in stream:
                lines.append(line.rstrip("\n"))
                if "END OF HEADER" in line:
                    break
    except (EOFError, OSError):
        pass  # truncated header samples end early
    return lines


for marker in MARKERS:
    candidates = sorted(ROOT.glob(f"data/**/{marker}_R_*_MO.rnx.gz")) + sorted(ROOT.glob(f"data/**/headers/{marker}.gz"))
    if not candidates:
        print(f"=== {marker}: no local file")
        continue
    print(f"=== {marker}: {candidates[0].relative_to(ROOT)}")
    system = None
    for line in header_lines(candidates[0]):
        label = line[60:].strip()
        if label not in KEYS:
            continue
        if label in ("SYS / # / OBS TYPES", "SYS / PHASE SHIFT"):
            if line[0] != " ":
                system = line[0]
            if system != "G":
                continue
        print("   " + line)
