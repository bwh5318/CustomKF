"""Evidence for the M12 GPS navigation-conflict classification (results/CORRECTIONS.md, M12 status row).

    python -m customkf.guard --profile usage75 --timeout 600 -- Opus_Fork.experiments.review_fixes.nav_conflicts

`prepare.merge_navigation` keeps the first record per (satellite, epoch field) key and, since 28 Sep 2026, reports keys
whose two records differ. For every campaign day pair this re-reads both daily files, and for each GPS duplicate
whose records differ lists the fields that differ. Where orbit or clock parameters differ it also evaluates both
records with `customkf.broadcast`, every 300 s over toe +/- 2 h. The first-wins policy is not changed here.
Writes nav_conflicts.json in the run folder and results/nav_conflicts_gps.json.
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from customkf import broadcast
from customkf.rinex import number, text_stream
from customkf.sp3 import epoch_tag

NAMES = ("iode", "crs", "delta_n", "m0", "cuc", "e", "cus", "sqrt_a", "toe", "cic", "omega0", "cis",
         "i0", "crc", "omega", "omega_dot", "idot", "codes_l2", "week", "l2p_flag", "ura", "health",
         "tgd", "iodc", "transmission_time", "fit_interval", "spare1", "spare2")
ORBIT = {"crs", "delta_n", "m0", "cuc", "e", "cus", "sqrt_a", "toe", "cic", "omega0", "cis", "i0", "crc", "omega",
         "omega_dot", "idot", "week"}
CLOCK = {"af0", "af1", "af2", "tgd"}
DAYS = ("2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-07")


def gps_blocks(path):
    with text_stream(path) as stream:
        first = stream.readline()
        version = float(first[:9])
        for _ in range(2000):
            if "END OF HEADER" in stream.readline():
                break
        else:
            raise ValueError("Missing header end: "+str(path))
        blocks = []
        for line in stream:
            if not line.strip():
                continue
            system = line[0]
            count = (5 if version >= 3.05 else 4) if system == "R" else (4 if system == "S" else 8)
            block = [line]+[stream.readline() for _ in range(count-1)]
            if system == "G":
                blocks.append((line[:23], block))
        return blocks


def record(block):
    line = block[0]
    values = [number(row[i:i+19]) for row in block[1:] for i in (4, 23, 42, 61)]
    clocks = [number(line[i:i+19]) for i in (23, 42, 61)]
    return {"gps_ns": epoch_tag("* "+line[4:23].strip()), "af0": clocks[0], "af1": clocks[1], "af2": clocks[2],
            **dict(zip(NAMES, values))}


def impact(first, second):
    """Largest ECEF position and clock (as range) difference between two records, every 300 s over the kept toe +/- 2 h."""
    toe_ns = int(round((first["week"]*broadcast.WEEK+first["toe"])*1e9))
    grid = toe_ns+np.arange(-7200, 7201, 300, dtype=np.int64)*10**9
    try:
        dr = max(float(np.linalg.norm(broadcast.position(first, int(t))-broadcast.position(second, int(t)))) for t in grid)
        dc = max(abs(float(broadcast.clock(first, int(t))-broadcast.clock(second, int(t))))*299792458. for t in grid)
    except ValueError as error:          # the dropped record cannot be evaluated over the kept record's window
        return None, None, str(error)
    return dr, dc, None


def pair(day):
    from Opus_Fork import prepare
    previous = (date.fromisoformat(day)-timedelta(days=1)).isoformat()
    available = prepare.input_map(day, previous)

    def stamp(d):
        d = date.fromisoformat(d)
        return f"{d.year}{d.timetuple().tm_yday:03d}"
    names = [f"BRDC00WRD_R_{stamp(d)}0000_01D_MN.rnx.gz" for d in (previous, day)]
    missing = [n for n in names if n not in available]
    if missing:
        return dict(day=day, skipped="daily navigation file not in the store: "+", ".join(missing))
    earlier, later = (gps_blocks(Path(available[n][0])) for n in names)
    seen = dict(earlier)
    cases = []
    for key, block in later:
        if key not in seen or [l.rstrip("\r\n") for l in block] == [l.rstrip("\r\n") for l in seen[key]]:
            continue
        kept, dropped = record(seen[key]), record(block)
        fields = sorted(k for k in kept if k != "gps_ns" and kept[k] != dropped[k])
        case = dict(key=key.strip(), differing_fields=fields,
                    kept={k: kept[k] for k in fields}, dropped={k: dropped[k] for k in fields})
        if set(fields) & (ORBIT | CLOCK | {"af0", "af1", "af2"}):
            dr, dc, error = impact(kept, dropped)
            case.update(max_position_difference_m=dr, max_clock_difference_m=dc)
            if error:
                case["evaluation_error"] = error
        if not fields:
            case["note"] = "text differs, parsed values identical (formatting)"
        cases.append(case)
    kinds = {}
    for c in cases:
        kind = ",".join(c["differing_fields"]) or "formatting only"
        kinds[kind] = kinds.get(kind, 0)+1
    return dict(day=day, files=names, gps_duplicate_keys=sum(1 for k, _ in later if k in seen),
                gps_conflicts=len(cases), by_differing_fields=kinds,
                orbit_or_clock_conflicts=sum(1 for c in cases if "max_position_difference_m" in c),
                worst_position_difference_m=max((c.get("max_position_difference_m") or 0. for c in cases), default=0.),
                worst_clock_difference_m=max((c.get("max_clock_difference_m") or 0. for c in cases), default=0.),
                unevaluated=sum(1 for c in cases if "evaluation_error" in c),
                cases=cases)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    from Opus_Fork.paths import RESULTS
    report = dict(policy="first wins (earlier day's record kept); unchanged", days=[pair(d) for d in DAYS])
    for d in report["days"]:
        print(d["day"], d.get("skipped") or f"{d['gps_conflicts']} GPS conflicts, by fields {d['by_differing_fields']}, "
              f"orbit/clock {d['orbit_or_clock_conflicts']}, worst {d['worst_position_difference_m']:.3g} m / "
              f"{d['worst_clock_difference_m']:.3g} m", flush=True)
    text = json.dumps(report, indent=1, default=float)+"\n"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"nav_conflicts.json").write_text(text)
    (RESULTS/"nav_conflicts_gps.json").write_text(text)


if __name__ == "__main__":
    main()
