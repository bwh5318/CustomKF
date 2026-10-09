"""Direct serial guard controller for the station-only D0 weak-prior COLD start.

Combines the two controls already run separately: tenfold weaker orbit prior
sigmas (10000 m / 10 m/s) *and* an entirely zero starting x. The warm weak-prior
run stopped without taking a step, so it never re-derived the solution; this one
does. Wet priors, data, weights, ambiguities, clocks, the absent D0 prior and the
broadcast-seed prior centres are unchanged.

Preparation is `claude.tools.d0_weak_cold_step`; the iterations use
`claude.tools.d0_weak_iteration`, which is Astra's unchanged `d0_iteration` logic
with the weak-prior pilot bound into it. Guard folders are moved out of `runs/`
into this campaign. No resume flag: after an interruption, verify the completed
guard results and hashes and adapt a separate continuation archive.
"""
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha
from claude.tools.d0_step import BASE

NOMINAL = ROOT/"claude/runs/20260912T145220Z-station-d0"
HELPERS = ("d0_pilot", "d0_step", "d0_iteration", "evaluate_d0", "run_d0", "force_parameter_fit",
           "yell_continuation_review", "arc_pilot", "ablation_step", "evaluate_ablation", "d0_review",
           "d0_weak_pilot", "d0_weak_step", "d0_weak_iteration", "d0_weak_compare", "run_d0_weak",
           "d0_weak_cold_step", "d0_weak_cold_compare", "run_d0_weak_cold")


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    nominal = json.loads((NOMINAL/"validation.json").read_text())
    if nominal["status"] != "station_d0_complete_not_accuracy_acceptance":
        raise RuntimeError("Nominal-prior campaign is not complete")
    sources = {**nominal["source_sha256"],
               **{f"claude/tools/{n}.py": sha(ROOT/f"claude/tools/{n}.py") for n in HELPERS},
               "D0_POD_PROTOCOL.md": sha(ROOT/"D0_POD_PROTOCOL.md")}
    for name, digest in sources.items():
        assert sha(ROOT/name) == digest, name

    folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-station-d0-weak-cold")
    folder.mkdir()
    for name in sources:
        target = folder/"source"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    report = dict(status="running", case="station-d0-six-weak-cold", source_sha256=sources,
                  report_sha256=nominal["report_sha256"], nominal_campaign=str(NOMINAL),
                  nominal_manifest_sha256=sha(NOMINAL/"validation.json"),
                  baseline_manifest_sha256=sha(BASE/"validation.json"),
                  runs={}, active_worker=None, final=None, accepted_trials=[], controller_pid=os.getpid(),
                  note="orbit prior sigmas x10 AND zero start; wet priors, data, weights and the absent D0 prior unchanged")

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
        prepare = worker("prepare", ["claude.tools.d0_weak_cold_step", "prepare"])
        meta = json.loads((prepare/"step.json").read_text())
        assert meta["weak_orbit_prior"] and meta["cold_start"] and meta["budget_pass"]
        assert meta["zero_start_cost_matches_baseline"] and meta["zero_start_prior_residuals_all_zero"]
        assert meta["d0_prior_absent"] and meta["fixture_sha256"] == meta["nominal_fixture_sha256"]
        assert meta["declared_position_sigma_m"] == 10000. and meta["declared_velocity_sigma_mps"] == 10.
        fixture = prepare/"fixture.json"
        previous = prepare/"cold"
        for i in range(4):
            linear = worker(f"linear-{i}", ["claude.tools.d0_weak_iteration", "linear", "--fixture", str(fixture),
                                            "--previous", str(previous)])
            if json.loads((linear/"step.json").read_text())["status"] == "converged":
                report["final"] = linear.name
                save()
                break
            accepted = False
            for ai, alpha in enumerate((1., .5, .25, .125)):
                trial = worker(f"trial-{i}-{ai}", ["claude.tools.d0_weak_iteration", "trial", "--fixture",
                                                   str(fixture), "--linear", str(linear), "--alpha", str(alpha)])
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
        worker("comparison", ["claude.tools.d0_weak_cold_compare", str(folder)], 120)
        report["status"] = "station_d0_weak_cold_complete_not_accuracy_acceptance"
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
