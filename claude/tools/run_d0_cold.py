"""Direct serial guard controller for the station-only D0 cold-start control.

Same fixture, priors, data, weights and limits as Astra's warm campaign; the only
difference is the starting checkpoint, which is exactly zero (broadcast seeds and
nominal D0). Preparation is `claude.tools.d0_cold_step`; every iteration then uses
Astra's unchanged guarded `claude.tools.d0_iteration` linear/trial workers, with
the original 1/.5/.25/.125 trial order, at most four linearisations and unchanged
resource ceilings. Guard folders are moved out of `runs/` into this campaign so
Astra's newest-run inspection keeps showing Astra's own work.

There is no resume flag. After an interruption, verify the completed guard results
and checkpoint hashes and adapt a separate continuation; never relabel this archive.
"""
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha
from claude.tools.d0_step import BASE

WARM = ROOT/"claude/runs/20260912T145220Z-station-d0"
HELPERS = ("d0_pilot", "d0_step", "d0_iteration", "evaluate_d0", "run_d0", "force_parameter_fit",
           "yell_continuation_review", "arc_pilot", "ablation_step", "evaluate_ablation",
           "d0_cold_step", "d0_cold_compare", "run_d0_cold", "d0_review")


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    warm = json.loads((WARM/"validation.json").read_text())
    if warm["status"] != "station_d0_complete_not_accuracy_acceptance":
        raise RuntimeError("Warm campaign is not complete")
    sources = {**warm["source_sha256"],
               **{f"claude/tools/{n}.py": sha(ROOT/f"claude/tools/{n}.py") for n in HELPERS},
               "D0_POD_PROTOCOL.md": sha(ROOT/"D0_POD_PROTOCOL.md")}
    for name, digest in sources.items():
        assert sha(ROOT/name) == digest, name

    folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-station-d0-cold")
    folder.mkdir()
    for name in sources:
        target = folder/"source"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    report = dict(status="running", case="station-d0-six-cold", source_sha256=sources,
                  report_sha256=warm["report_sha256"], warm_campaign=str(WARM),
                  warm_manifest_sha256=sha(WARM/"validation.json"),
                  baseline_manifest_sha256=sha(BASE/"validation.json"),
                  runs={}, active_worker=None, final=None, accepted_trials=[], controller_pid=os.getpid(),
                  note="cold start: entire x vector zero; identical priors/rows/weights/limits")

    def save():
        pending = folder/"pending.json"
        pending.write_text(json.dumps(report, indent=2)+"\n")
        pending.replace(folder/"validation.json")

    def worker(name, arguments, timeout=300):
        for group in ("source_sha256", "report_sha256"):
            for path, digest in report[group].items():
                assert sha(ROOT/path) == digest, path
        report["active_worker"] = dict(name=name, module_args=arguments, controller_pid=os.getpid(),
                                       started_utc=datetime.now(timezone.utc).isoformat())
        save()
        print("Starting "+name, flush=True)
        result, path = run(arguments, Limits(timeout_s=timeout))
        shutil.move(str(path), str(folder/name))
        report["runs"][name] = {**result, "original_directory": str(path), "moved_from_runs": True}
        report["active_worker"] = None
        save()
        print(f"{name}: {result['status']} {result.get('elapsed_s',0):.1f}s "
              f"{result.get('windows_peak_job_memory_mib',0):.1f} MiB", flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Worker failed: "+name)
        return folder/name

    save()
    print("Campaign: "+str(folder), flush=True)
    try:
        prepare = worker("prepare", ["claude.tools.d0_cold_step", "prepare"])
        meta = json.loads((prepare/"step.json").read_text())
        assert meta["cold_start"] and meta["budget_pass"] and meta["zero_start_cost_matches_baseline"]
        assert meta["force_prior_absent"] and meta["fixture_sha256"] == meta["warm_fixture_sha256"]
        fixture = prepare/"fixture.json"
        previous = prepare/"cold"
        for i in range(4):
            linear = worker(f"linear-{i}", ["claude.tools.d0_iteration", "linear", "--fixture", str(fixture),
                                            "--previous", str(previous)])
            if json.loads((linear/"step.json").read_text())["status"] == "converged":
                report["final"] = linear.name
                save()
                break
            accepted = False
            for ai, alpha in enumerate((1., .5, .25, .125)):
                trial = worker(f"trial-{i}-{ai}", ["claude.tools.d0_iteration", "trial", "--fixture", str(fixture),
                                                   "--linear", str(linear), "--alpha", str(alpha)])
                if json.loads((trial/"step.json").read_text())["status"] == "iteration_complete":
                    previous = trial
                    report["accepted_trials"].append(trial.name)
                    save()
                    accepted = True
                    break
            if not accepted:
                raise RuntimeError("No accepted trial")
        if report["final"] is None:
            raise RuntimeError("Iteration cap reached without stationarity; preserved for inspection")
        worker("comparison", ["claude.tools.d0_cold_compare", str(folder)], 120)
        report["status"] = "station_d0_cold_start_complete_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        values = list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                      peak_job_memory_mib=max([v.get("windows_peak_job_memory_mib", 0) for v in values] or [0]),
                      minimum_system_available_gib=min([v.get("minimum_system_available_gib", float("inf"))
                                                        for v in values] or [float("inf")]))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*")
                                      if p.is_file() and p.name != "validation.json"}
        save()
    print("Archived: "+str(folder), flush=True)


if __name__ == "__main__":
    main()
