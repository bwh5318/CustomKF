"""Why does the 24 h fixture drop five satellites at 00:00, and does the previous day fix it?

    python -m Opus_Fork.guard --profile fork8 --timeout 300 --label nav-coverage -- Opus_Fork.nav_coverage

`claude/roadmap/long_prepare.py` requires an eligible nominal four-hour LNAV fit record at
every solve epoch, including the -0.2 s light-time offset at the arc start. On 2026-08-02
G02, G05, G13, G18 and G29 fail, so the 24 h arc fits 27 of 32 satellites while NGA PE
carries all 32. That is not a deliverable product.

This walks the frozen rule in `customkf/broadcast.py:select_fit_record` epoch by epoch and
reports, per satellite, which epochs fail and which specific clause rejects every candidate
record. It then repeats the walk with the **previous day's** broadcast file merged in and
reports which satellites become eligible. Read-only: navigation files only, no fit, no
reference product, no download. The previous-day file is already on disk.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.broadcast import WEEK, select_fit_record
from customkf.prepare_stage2 import sha
from customkf.rinex import read_gps_navigation
from customkf.sp3 import epoch_tag

from .blocks import satellite_blocks
from .paths import ROOT, STAGE3, RESULTS

DAY = "2026-08-02"
STEP = 600.
EPOCHS = 144
ORIGIN = epoch_tag("* 2026 08 01 23 59 50")          # long_prepare: first epoch minus 10 s
CUTOFF = epoch_tag("* 2026 08 03 00 00 00")          # end of the observation day
CURRENT = STAGE3/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz"
PREVIOUS = STAGE3/"BRDC00WRD_R_20262130000_01D_MN.rnx.gz"


def rejection_reasons(records, gps_ns, available_before_ns):
    """Which clause of select_fit_record rejects each record, for the nearest candidates."""
    tally, nearest = {}, []
    for r in records:
        toe = r["week"]*WEEK+r["toe"]
        why = []
        if r["health"] != 0:
            why.append("unhealthy")
        if r.get("fit_interval") != 4.:
            why.append(f"fit_interval={r.get('fit_interval')}")
        if r["toe"] % 3600 != 0:
            why.append("toe_not_hour_aligned")
        if abs(r["gps_ns"]/1e9-toe) > 1e-6:
            why.append("toc_ne_toe")
        age = gps_ns/1e9-toe
        if abs(age) > 7200.:
            why.append(f"age={age/3600:+.2f}h_outside_2h")
        if r["gps_ns"] > available_before_ns:
            why.append("after_cutoff")
        tx = r.get("transmission_time")
        if tx not in (None, 0.):
            transmission = r["week"]*WEEK+tx
            transmission -= round((transmission-toe)/WEEK)*WEEK
            if transmission > available_before_ns/1e9:
                why.append("transmission_after_cutoff")
        key = ",".join(why) or "eligible"
        tally[key] = tally.get(key, 0)+1
        nearest.append((abs(age), age/3600, key))
    nearest.sort()
    return tally, [dict(age_h=round(a, 3), verdict=k) for _, a, k in nearest[:3]]


def walk(navigation, satellites):
    """First failing epoch and failure count per satellite under the frozen rule."""
    times = np.arange(10., 10.+(EPOCHS-1)*STEP+.1, STEP)
    out = {}
    for sat in satellites:
        records = navigation.get(sat, [])
        failures, first = 0, None
        for t in times:
            for offset in (-.2, 0.):
                tag = ORIGIN+int((t+offset)*1e9)
                try:
                    select_fit_record(records, tag, available_before_ns=CUTOFF)
                except ValueError:
                    failures += 1
                    if first is None:
                        tally, nearest = rejection_reasons(records, tag, CUTOFF)
                        first = dict(hour=round((tag-ORIGIN-10e9)/3.6e12, 4), offset_s=offset,
                                     candidate_verdicts=tally, nearest_records=nearest)
        out[sat] = dict(records=len(records), failing_checks=failures, eligible=failures == 0,
                        first_failure=first)
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    blocks = satellite_blocks(DAY)
    current = read_gps_navigation(CURRENT)
    previous = read_gps_navigation(PREVIOUS)

    merged = {}
    for sat in set(current) | set(previous):
        rows = list(previous.get(sat, []))+list(current.get(sat, []))
        seen, unique = set(), []
        for r in sorted(rows, key=lambda r: r["gps_ns"]):
            key = (r["gps_ns"], r["week"], r["toe"], r["iode"])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        merged[sat] = unique

    satellites = sorted(set(current) | set(previous))
    day_only = walk(current, satellites)
    with_previous = walk(merged, satellites)

    gained = [s for s in satellites if not day_only[s]["eligible"] and with_previous[s]["eligible"]]
    still = [s for s in satellites if not with_previous[s]["eligible"]]
    report = dict(status="nav_coverage_diagnostic", day=DAY,
                  inputs={"current": dict(path=CURRENT.relative_to(ROOT).as_posix(), sha256=sha(CURRENT)),
                          "previous": dict(path=PREVIOUS.relative_to(ROOT).as_posix(), sha256=sha(PREVIOUS))},
                  rule="customkf.broadcast.select_fit_record, unchanged",
                  epochs=EPOCHS, checks_per_satellite=EPOCHS*2,
                  eligible_day_only=sorted(s for s in satellites if day_only[s]["eligible"]),
                  eligible_with_previous=sorted(s for s in satellites if with_previous[s]["eligible"]),
                  gained_by_previous_day=gained, still_ineligible=still,
                  per_satellite={s: dict(block=blocks.get(s, ("?", "?"))[0],
                                         day_only=day_only[s], with_previous=with_previous[s])
                                 for s in satellites})
    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"nav_coverage.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"nav_coverage.json").write_text(text)

    print(f"day-file only:    {len(report['eligible_day_only'])}/{len(satellites)} eligible")
    print(f"+ previous day:   {len(report['eligible_with_previous'])}/{len(satellites)} eligible")
    print(f"gained:           {' '.join(gained) or 'none'}")
    print(f"still ineligible: {' '.join(still) or 'none'}")
    print()
    for sat in satellites:
        a, b = day_only[sat], with_previous[sat]
        if a["eligible"] and b["eligible"]:
            continue
        print(f"{sat} ({blocks.get(sat, ('?',))[0]}): {a['records']} records in the day file, "
              f"{a['failing_checks']} of {EPOCHS*2} checks fail -> {b['failing_checks']} with the previous day")
        if a["first_failure"]:
            f = a["first_failure"]
            print(f"    first failure at hour {f['hour']:.3f} (offset {f['offset_s']} s)")
            print(f"    nearest records: {f['nearest_records']}")
            top = sorted(f["candidate_verdicts"].items(), key=lambda kv: -kv[1])[:3]
            print(f"    verdict tally: {top}")
        if b["first_failure"]:
            print(f"    STILL fails with previous day at hour {b['first_failure']['hour']:.3f}: "
                  f"{b['first_failure']['nearest_records']}")
    print("\nWrote "+str(out/"nav_coverage.json"))


if __name__ == "__main__":
    main()
