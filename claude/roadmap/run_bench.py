"""Direct serial orchestrator for the multi-day bench (BENCH_PROTOCOL.md).

    C:\\anaconda\\python.exe -m claude.roadmap.run_bench --step2 DIR --step3 DIR [--days 2026-08-02,...]

Runs no numerics itself. L* is chosen mechanically by the frozen rule (a guarded long_evaluate on August 2).
Existing August-2/3 A0 and FB6 archives are reused; other days get fresh guarded preparations and run_long fits.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from customkf.prepare_stage2 import ROOT
from claude.roadmap.run_roadmap import Stage, check_idle, chunk_for, CONFIGS, latest_converged
from claude.roadmap.long_prepare import STATIONS

PROTOCOL = "claude/roadmap/BENCH_PROTOCOL.md"
BLOCK = ROOT/"claude/runs/20260913T015012Z-block-d0"
ARCHIVE = {
    "2026-08-02": dict(fixture=ROOT/"runs/20260912T161029Z-0ddb71b3/fixture.json",
                       A0=ROOT/"claude/runs/20260912T021739Z-arc/six-1", FB6=BLOCK/"B-02-linear-1"),
    "2026-08-03": dict(fixture=ROOT/"claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json",
                       A0=ROOT/"claude/runs/20260912T193417Z-day215-pod/fixed-linear-2", FB6=BLOCK/"B-03-linear-2"),
}
ARM_CONFIG = {"12h-FB": ("block-fixed.json", 0), "12h-D0": ("unit-d0.json", 1), "12h-FU": ("unit-fixed.json", 0), "12h-E5": ("unit-ecom5.json", 5),
              "24h-FB": ("block-fixed.json", 0), "24h-D0": ("unit-d0.json", 1), "24h-E5": ("unit-ecom5.json", 5)}


def final_of(campaign):
    manifest = json.loads((Path(campaign)/"validation.json").read_text())
    if manifest.get("status") != "long_fit_complete_not_accuracy_acceptance" or not manifest.get("final"):
        return None
    return Path(campaign)/manifest["final"], ROOT/manifest["fixture"]


def reusable(label, config_name, fixture_day):
    """A previously converged bench campaign for the same label, force config and day (completed archives only)."""
    found = latest_converged(label)
    if found is None:
        return None
    solution, fixture = found
    manifest = json.loads((solution.parent/"validation.json").read_text())
    context = json.loads(Path(fixture).read_text())["context"]
    if Path(manifest["config"]).name != config_name or context["day"] != fixture_day:
        return None
    return found


def inputs_for(day):
    doy = datetime.strptime(day, "%Y-%m-%d").strftime("%j")
    path = ROOT/"claude/data"/f"day{doy}"/"inputs.json"
    return ["--inputs", str(path)] if day != "2026-08-02" else []


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run directly"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2", required=True)
    parser.add_argument("--step3", help="unused; kept for command compatibility")
    parser.add_argument("--allow-missing-arms", action="store_true",
                        help="choose L* among converged arms even if some step 3 arms never converged (disclosed)")
    parser.add_argument("--days", default="2026-08-02,2026-08-03,2026-08-04,2026-08-05,2026-08-06")
    args = parser.parse_args()
    check_idle()
    g2d = json.loads((Path(args.step2)/"stage.json").read_text())["gates"]["G2d"]
    stage = Stage("bench")
    from customkf.prepare_stage2 import sha
    stage.report.update(protocol=PROTOCOL, protocol_sha256=sha(ROOT/PROTOCOL),
                        note="run_long children pin STREAMING_AND_ARCS_PROTOCOL.md through run_roadmap.Stage; this stage pins BENCH_PROTOCOL.md")
    try:
        # Step 3 arms span several stages (a sleep-interrupted 24 h run was repeated); take the newest completed campaign per arm.
        converged = {label: latest_converged(label) for label in ARM_CONFIG}
        converged = {k: v for k, v in converged.items() if v is not None}
        missing = sorted(set(ARM_CONFIG)-set(converged))
        if missing and not args.allow_missing_arms:
            raise RuntimeError("Step 3 arms not yet converged: "+",".join(missing)+" (rerun them, or pass --allow-missing-arms)")
        stage.report["step3_missing_arms"] = missing
        stage.report["step3_converged"] = sorted(converged)
        if not converged:
            raise RuntimeError("No converged step 3 arm; L* undefined")
        selection = ["claude.roadmap.long_evaluate", "--day", "2026-08-02", "--out-name", "lstar_selection", "--baseline", sorted(converged)[0],
                     "--domain", "S12", "12:00", "23:45"]
        for label, (solution, fixture) in converged.items():
            selection += ["--arm", label, str(solution), str(fixture)]
        chosen = stage.guard("lstar-selection", selection)
        scores = json.loads((chosen/"lstar_selection.json").read_text())["domains"]["S12"]["arms"]
        lstar = min(scores, key=lambda a: scores[a]["all"]["rms_3d_m"])
        stage.report["lstar"] = dict(label=lstar, S12_rms_3d_m={a: v["all"]["rms_3d_m"] for a, v in scores.items()})
        stage.save()
        config, count = ARM_CONFIG[lstar]
        long_start, long_epochs = ("00:00", 144) if lstar.startswith("24h") else ("12:00", 72)
        reports = []
        for day in args.days.split(","):
            tag = day[-2:]
            arms = {}
            if day in ARCHIVE:
                a = ARCHIVE[day]
                arms["A0"] = (a["A0"], a["fixture"])
                arms["FB6"] = (a["FB6"], a["fixture"])
            station_args = []
            if day not in ARCHIVE:
                # Frozen-parser readability screen; unreadable stations are excluded for every arm that day (disclosed).
                events = stage.guard(f"rinex-events-{tag}", ["claude.roadmap.bench_rinex_events", "--day", day, "--markers", ",".join(STATIONS.values())])
                unavailable = json.loads((events/"rinex_events.json").read_text())["unavailable"]
                names = [s for s, m in STATIONS.items() if m not in unavailable]
                station_args = ["--stations", ",".join(names)]
                stage.report.setdefault("excluded_stations", {})[day] = unavailable
                stage.save()
            if day not in ARCHIVE:
                six = None
                for arm, cfg, n in (("A0", "unit-fixed.json", 0), ("FB6", "block-fixed.json", 0)):
                    result = reusable(f"bench-{tag}-{arm}", cfg, day)
                    if result is None:
                        if six is None:
                            six = stage.guard(f"prepare-{tag}-6h", ["claude.roadmap.long_prepare", "--day", day, "--start", "12:00", "--epochs", "37",
                                                                   *station_args, *inputs_for(day)])
                        result = final_of(stage.long(f"bench-{tag}-{arm}", six, f"{CONFIGS}/{cfg}", chunk_for(g2d, n, 37, cached=True), 4, 1))
                        if result is None:
                            raise RuntimeError(f"{arm} did not converge on {day}")
                    else:
                        stage.report.setdefault("reused", {})[f"{day}:{arm}"] = str(result[0])
                    arms[arm] = result
            if day == "2026-08-02":
                arms["L*"] = converged[lstar]
            else:
                result = reusable(f"bench-{tag}-Lstar", config, day)
                if result is None:
                    longprep = stage.guard(f"prepare-{tag}-long", ["claude.roadmap.long_prepare", "--day", day, "--start", long_start,
                                                                   "--epochs", str(long_epochs), *station_args, *inputs_for(day)])
                    result = final_of(stage.long(f"bench-{tag}-Lstar", longprep, f"{CONFIGS}/{config}", chunk_for(g2d, count, long_epochs, cached=True),
                                                 6 if long_epochs == 144 else 4, 2 if long_epochs == 144 else 1))
                    if result is None:
                        raise RuntimeError(f"L* did not converge on {day}")
                else:
                    stage.report.setdefault("reused", {})[f"{day}:L*"] = str(result[0])
                arms["L*"] = result
            beta = stage.guard(f"beta-{tag}", ["claude.roadmap.bench_beta", "--day", day, "--start", "00:00", "--end", "23:45"])
            evaluate = ["claude.roadmap.bench_evaluate", "--day", day, "--out-name", f"bench_{tag}", "--baseline", "A0",
                        "--domain", "common", "12:00", "18:00"]
            for arm, (solution, fixture) in arms.items():
                evaluate += ["--arm", arm, str(solution), str(fixture)]
            out = stage.guard(f"evaluate-{tag}", evaluate)
            arc = stage.guard(f"evaluate-{tag}-arc", ["claude.roadmap.bench_evaluate", "--day", day, "--out-name", f"bench_{tag}_arc",
                                                     "--baseline", "L*", "--domain", "arc", long_start, "23:45",
                                                     "--arm", "L*", str(arms["L*"][0]), str(arms["L*"][1])])
            reports += ["--day-report", day, str(out/f"bench_{tag}.json")]
            stage.report.setdefault("days", {})[day] = dict(arms={k: str(v[0]) for k, v in arms.items()}, evaluation=str(out),
                                                            arc_evaluation=str(arc), beta=str(beta))
            stage.save()
        stage.guard("summary", ["claude.roadmap.bench_summary", *reports, "--window", "common"])
        stage.report["status"] = "bench_complete_not_accuracy_acceptance"
    except BaseException as error:
        stage.report.update(status="failed", error=repr(error))
        raise
    finally:
        stage.save()


if __name__ == "__main__":
    main()
