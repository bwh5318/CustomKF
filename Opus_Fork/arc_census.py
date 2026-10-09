"""Network-wide arc-integrity census: every within-arc step longer than the sampling interval.

    python -m Opus_Fork.guard --profile fork8 --timeout 1800 --label census -- Opus_Fork.arc_census \
        --day 2026-08-08 --network 25 --expect SGOC G07 12:38:00

PROTOCOL, FROZEN BEFORE ANY OUTPUT WAS READ. `results/sgoc_g07_native_audit/REVIEW.md` found a
phase discontinuity at SGOC:G07 12:38:00 on 2026-08-08 that the frozen tracker did not split,
and that one unsplit arc carried **50.4% of the whole network's phase cost**. Until the network
is censused for the same signature, residual-scatter weighting and arc handling are confounded:
a weight would down-weight such an arc and hide the defect (`w2_interpretation_review/REVIEW.md`
section 4). This census is the declared prerequisite for any further weighting or ambiguity
fixing, so it is run first and its criterion is fixed here rather than chosen after seeing hits.

**The mechanism, from `customkf/preprocess.py:47-52`.** The split rule reads

    elif (tag - old[0])/1e9 > 60:  reason.append("gap")
    else:                          <geometry-free and Melbourne-Wubbena jump tests>

so a step of **exactly 60 s** — one missed epoch in 30 s data — misses the gap test (strict
`>`) and falls through to jump tests carrying a 60 s allowance, `0.08 + 0.002*dt = 0.20 m` of
geometry-free change. SGOC's jump was 0.054 m with LLI 0, comfortably inside it. The rule
behaved exactly as written; the rule is what admits the discontinuity.

**Declared candidate criterion, applied uniformly.** Every pair of consecutive selected samples
of one satellite at one station that the tracker kept in the **same arc** while the time step
exceeded the file's nominal interval. Motivation, fixed in advance: a step longer than the
interval means the receiver stopped reporting usable phase, which is precisely when an
undetected cycle slip can occur, whatever the jump magnitude. No margin fraction and no
jump threshold enters the definition, so the census cannot be tuned by its own output.

Reported per candidate, for ranking only and never for inclusion: the step, the geometry-free
and Melbourne-Wubbena changes, each against the threshold that was actually applied, and the
loss-of-lock and half-cycle flags. `--expect STATION SAT HH:MM:SS` asserts a known case is
found, so a census that silently detects nothing fails loudly instead of reading as clean.

Read-only over native RINEX with the unchanged parser, `choose_signals`, `combinations` and
`ArcTracker`. No fixture, fit, weight, mask, arc-rule change or download.
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path

from customkf.prepare_stage2 import ROOT, sha
from customkf.rinex import header, text_stream, epochs
from customkf.preprocess import ArcTracker, combinations, choose_signals

from .fetch import CORE_14, NETWORK_25
from .paths import RESULTS
from .prepare import input_map


def census_station(path, day):
    """Replay the frozen tracker over a whole day and record every within-arc long step."""
    with text_stream(path) as stream:
        meta = header(stream, allow_declared_phase_shifts=True)
        pair = choose_signals(meta.types["G"])
        interval = meta.interval_s or 30.0
        tracker = ArcTracker()
        previous = {}
        candidates, arcs, samples = [], defaultdict(int), 0
        for obs in epochs(stream, meta):
            tracker.observe_epoch_event(obs.gps_ns, obs.satellites, obs.flag)
            if obs.flag == 6:
                continue
            for sat, values in obs.satellites.items():
                data = combinations(values, pair)
                if data is None:
                    continue
                before = previous.get(sat)
                arc = tracker.update(obs.gps_ns, sat, data, obs.flag)
                samples += 1
                arcs[sat, arc] += 1
                if before is not None:
                    step = (obs.gps_ns-before["gps_ns"])/1e9
                    if arc == before["arc"] and step > interval+1e-6:
                        gf = data["geometry_free_m"]-before["data"]["geometry_free_m"]
                        mw = data["mw_m"]-before["data"]["mw_m"]
                        limit = .08+.002*step
                        candidates.append(dict(
                            satellite=sat, arc=arc, gps_ns=int(obs.gps_ns),
                            step_s=step, missed_epochs=int(round(step/interval))-1,
                            d_geometry_free_m=gf, geometry_free_limit_m=limit,
                            geometry_free_margin=abs(gf)/limit,
                            d_melbourne_wubbena_m=mw, melbourne_wubbena_margin=abs(mw)/5.0,
                            loss_of_lock=bool(data["loss_of_lock"]),
                            half_cycle=bool(data["half_cycle"]),
                            exactly_at_gap_boundary=abs(step-60.) < 1e-6))
                previous[sat] = dict(gps_ns=obs.gps_ns, data=data, arc=arc)
    return dict(marker=path.name, interval_s=interval,
                signal_pair=pair.__dict__, samples=samples, arcs=len(arcs),
                candidates=candidates), tracker


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--network", choices=("14", "25"), default="25")
    parser.add_argument("--expect", nargs=3, action="append", default=[],
                        metavar=("STATION", "SAT", "HHMMSS"),
                        help="assert a known discontinuity is detected; the census fails if not")
    args = parser.parse_args()
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    markers = NETWORK_25 if args.network == "25" else CORE_14
    available = input_map(args.day)
    stamp = args.day.replace("-", "")
    stamp = f"{args.day[:4]}{__import__('datetime').datetime.strptime(args.day, '%Y-%m-%d').strftime('%j')}"

    report = dict(status="arc_census_not_an_arc_rule_change", day=args.day,
                  criterion="within-arc consecutive selected samples whose step exceeds the "
                            "file's nominal sampling interval",
                  mechanism="customkf/preprocess.py:48 uses a strict > 60 s gap test, so a "
                            "60 s step (one missed 30 s epoch) is judged by jump thresholds "
                            "carrying a 60 s allowance of 0.20 m geometry-free",
                  stations={}, inputs={})
    total, boundary = 0, 0
    for marker in markers:
        name = f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz"
        if name not in available:
            report["stations"][marker] = dict(error="absent from the store")
            continue
        path, digest, relative = available[name]
        if sha(path) != digest:
            raise ValueError("Input changed since it was indexed: "+relative)
        report["inputs"][relative] = digest
        try:
            entry, _ = census_station(path, args.day)
        except (ValueError, KeyError) as error:
            # One unreadable station must not abort a network census. The parser refuses
            # mid-day metadata events (rinex.py:143-150), which is why YELL is excluded on
            # some dates; that is recorded per station, not allowed to hide the other 24.
            report["stations"][marker[:4]] = dict(error=str(error)[:200], unreadable=True)
            print(f"  {marker[:4]}  UNREADABLE: {str(error)[:90]}", flush=True)
            continue
        entry["candidate_count"] = len(entry["candidates"])
        entry["boundary_count"] = sum(c["exactly_at_gap_boundary"] for c in entry["candidates"])
        total += entry["candidate_count"]
        boundary += entry["boundary_count"]
        report["stations"][marker[:4]] = entry
        print(f"  {marker[:4]}  {entry['samples']:6d} samples  {entry['arcs']:4d} arcs  "
              f"{entry['candidate_count']:4d} candidates ({entry['boundary_count']} at the 60 s boundary)",
              flush=True)

    every = [dict(c, station=s) for s, e in report["stations"].items()
             for c in e.get("candidates", [])]
    report["totals"] = dict(candidates=total, at_gap_boundary=boundary,
                            stations=len([s for s, e in report["stations"].items() if "candidates" in e]),
                            with_loss_of_lock=sum(c["loss_of_lock"] for c in every))
    report["worst_by_geometry_free"] = sorted(every, key=lambda c: -c["geometry_free_margin"])[:30]
    report["worst_by_melbourne_wubbena"] = sorted(every, key=lambda c: -c["melbourne_wubbena_margin"])[:30]

    # Positive control: a census that detects nothing must fail, not read as clean.
    from customkf.sp3 import epoch_tag
    checks = []
    for station, sat, hhmmss in args.expect:
        y, m, d = args.day.split("-")
        want = epoch_tag(f"* {y} {m} {d} {hhmmss[:2]} {hhmmss[3:5]} {hhmmss[6:8]}")
        hit = [c for c in every if c["station"] == station[:4] and c["satellite"] == sat
               and c["gps_ns"] == want]
        checks.append(dict(station=station, satellite=sat, time=hhmmss, found=bool(hit),
                           candidate=hit[0] if hit else None))
    report["positive_controls"] = checks

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"arc_census.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/f"arc_census_{args.day}.json").write_text(text)

    print(f"\n{total} candidates across {report['totals']['stations']} stations; "
          f"{boundary} sit exactly on the 60 s gap boundary; "
          f"{report['totals']['with_loss_of_lock']} carry loss-of-lock")
    print("\nworst 12 by geometry-free margin (fraction of the threshold actually applied):")
    for c in report["worst_by_geometry_free"][:12]:
        print(f"  {c['station']:5s} {c['satellite']} step {c['step_s']:5.0f}s  "
              f"dGF {c['d_geometry_free_m']*100:+8.2f} cm of {c['geometry_free_limit_m']*100:6.2f} cm "
              f"({c['geometry_free_margin']:.2f})  dMW {c['d_melbourne_wubbena_m']:+7.2f} m "
              f"({c['melbourne_wubbena_margin']:.2f})  LLI {int(c['loss_of_lock'])}")
    for check in checks:
        state = "FOUND" if check["found"] else "NOT FOUND"
        print(f"\npositive control {check['station']} {check['satellite']} {check['time']}: {state}")
        if check["found"]:
            c = check["candidate"]
            print(f"  step {c['step_s']:.0f} s, dGF {c['d_geometry_free_m']*100:+.2f} cm of "
                  f"{c['geometry_free_limit_m']*100:.2f} cm, dMW {c['d_melbourne_wubbena_m']:+.2f} m, "
                  f"boundary {c['exactly_at_gap_boundary']}")
    print("\nWrote "+str(out/"arc_census.json"))
    if checks and not all(c["found"] for c in checks):
        raise SystemExit("A declared positive control was not detected; the census is not trustworthy")


if __name__ == "__main__":
    main()
