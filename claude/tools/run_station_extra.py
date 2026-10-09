"""Run DIRECTLY, never nested: a 15-station diagnostic fit adding one screened station.

    C:\\anaconda\\python.exe -m claude.tools.run_station_extra --station PIMO

Tests whether simultaneous-viewing geometry still limits the 14-station 0.8211 m result, which is
the obvious question after 56.39 -> 11.18 -> 0.82 m from adding YELL and then GUAM. PIMO's header,
signals and antenna calibration already passed Claude's earlier screen.

Everything stays on Claude's side: acquisition writes to claude/data/acquired, preparation mirrors
the pinned Stage 3 inputs into claude/data/stage3-mirror and patches the station map and data path
at runtime only, and the existing 14 stations' rows, seeds and metadata must match the archived GUAM
fixture exactly. No root source, data/, validation/ archive or baseline is modified, and this does
not replace Astra's baseline.

Serial guarded workers, default limits: 120 s acquisition, <=300 s preparation and iterations, at
most five iterations, 120 s evaluator. Stops at the first failure.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import Limits, run
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)
OWN = ("claude/tools/station_extra_fetch.py", "claude/tools/station_extra_step.py",
       "claude/tools/evaluate_station_extra.py", "claude/tools/run_station_extra.py",
       "claude/tools/pinned_sources.py", "claude/tools/ablation_step.py")
STABILITY = ROOT / "claude/runs/20260911T162036Z-stability"
MARKERS = {"PIMO": "PIMO00PHL", "POHN": "POHN00FSM"}
MAX_ITERATIONS = 5


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    parser = argparse.ArgumentParser()
    parser.add_argument("--station", default="PIMO", choices=sorted(MARKERS))
    station = parser.parse_args().station
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    for name, digest in base["artifacts_sha256"].items():
        assert sha(GUAM / name) == digest, name
    engine_pin = json.loads((STABILITY / "validation.json").read_text())["source_sha256"]["claude/tools/ablation_step.py"]
    assert sha(ROOT / "claude/tools/ablation_step.py") == engine_pin, "ablation_step.py changed since the stability campaign"
    folder = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-station-{station.lower()}")
    folder.mkdir()
    sources = {name: sha(ROOT / name) for name in (*base["source_sha256"], *HELPERS, *OWN, *policy["new_files_sha256"])}
    for name in sources:
        target = folder / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    report = {
        "status": "running", "operator": "Claude (Opus) while Astra is idle; diagnostic, not a new baseline",
        "station": station, "marker": MARKERS[station], "source_policy": policy, "source_sha256": sources,
        "report_sha256": base["report_sha256"], "baseline": GUAM.relative_to(ROOT).as_posix(),
        "baseline_manifest_sha256": sha(GUAM / "validation.json"), "iteration_engine_sha256": engine_pin,
        "prepare": None, "iterations": [], "final": None, "active_worker": None, "runs": {},
        "predeclared_protocol": f"Add {station} ({MARKERS[station]}) to the archived 14-station case with the identical arc, "
                               "cadence, model, weights, priors, clock datum and ambiguity handling. Acquire and decode with the "
                               "pinned decoder into claude/data; mirror the pinned Stage 3 inputs into claude/data/stage3-mirror "
                               "with hash checks; patch the station map and data path at runtime only. Require the existing 14 "
                               "stations' rows, seeds, station metadata, input contents and arc context to match the GUAM fixture "
                               "exactly. Preflight rows/retained/workspace against the unchanged 12000/900/256 MiB limits. At most "
                               "five 300 s iterations, then a 120 s evaluator. Score all 31 satellites on the same native IGS "
                               "samples with the frozen sigma<=10 m split, plus determined and determined-in-both, and report the "
                               "actual change in simultaneous-site epochs. Diagnostic only; Astra's baseline is unchanged."}

    def save():
        pending = folder / "pending.json"
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(folder / "validation.json")

    def worker(name, args, timeout=300):
        report["active_worker"] = {"name": name, "module_args": args, "started_utc": datetime.now(timezone.utc).isoformat()}
        save()
        print("Starting " + name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        shutil.copytree(path, folder / name)
        report["runs"][name] = {**result, "original_directory": str(path)}
        report["active_worker"] = None
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s', 0):.1f}s, {result.get('peak_sampled_rss_mib', 0):.1f} MiB RSS", flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Failed worker: " + name)
        return folder / name

    save()
    try:
        acquired = worker("acquisition", ["claude.tools.station_extra_fetch", "--marker", MARKERS[station]], 120)
        report["acquisition"] = json.loads((acquired / "acquisition.json").read_text())
        save()
        report["prepare"] = "prepare"
        worker("prepare", ["claude.tools.station_extra_step", "prepare", "--station", station])
        save()
        previous = None
        for index in range(MAX_ITERATIONS):
            name = f"iteration-{index}"
            args = ["claude.tools.station_extra_step", "iterate", "--fixture", str(folder / "prepare/fixture.json")]
            if previous:
                args.extend(["--previous", str(previous)])
            previous = worker(name, args)
            report["iterations"].append(name)
            save()
            if json.loads((previous / "step.json").read_text())["status"] == "converged":
                report["final"] = name
                save()
                break
        if not report["final"]:
            raise RuntimeError("Not converged within the iteration cap")
        worker("evaluation", ["claude.tools.evaluate_station_extra", str(folder)], 120)
        if verify(HELPERS) != policy:
            raise RuntimeError("Source state changed during the campaign")
        for name, digest in sources.items():
            assert sha(ROOT / name) == digest, name
        report["status"] = "station_extension_complete_diagnostic_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        values = list(report["runs"].values())
        if values:
            report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                          peak_sampled_rss_mib=max(v.get("peak_sampled_rss_mib", 0) for v in values),
                          minimum_system_available_gib=min(v.get("minimum_system_available_gib", float("inf")) for v in values))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*"))
                                      if p.is_file() and p.name not in ("validation.json", "pending.json")}
        save()
    print("Archived: " + str(folder), flush=True)


if __name__ == "__main__":
    main()
