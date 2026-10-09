"""Direct serial controller for one LongPilot fit (roadmap steps 2-3).

    C:\\anaconda\\python.exe -m claude.roadmap.run_long --fixture DIR --config CONFIG.json --label NAME --chunk-epochs 12

Fresh campaign only (claude/runs/<utc>-long-<label>); no resume. Every guarded worker uses the unchanged
default limits (300 s, 2 GiB, one core, 10% CPU, 8 GiB reserve, 128 MiB scratch). Refuses to start if any
other Python process exists. Sources, config, calibration and fixture are hash-pinned and re-verified
before each worker.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import psutil
from customkf.guard import Limits, run
from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.common import sources, write_json


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run the controller directly, never inside a guard"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True, help="prepared directory containing fixture.json/step.json")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--chunk-epochs", type=int, required=True)
    parser.add_argument("--max-linearizations", type=int, default=4)
    parser.add_argument("--protocol", default=None)
    parser.add_argument("--trajectory-groups", type=int, default=0,
                        help="integrate each linearization/trial point once, in this many guarded workers (claude.roadmap.traj_cache)")
    args = parser.parse_args()
    allowed = {os.getpid()}
    if os.environ.get("CLAUDE_ROADMAP_ORCHESTRATOR_PID") == str(os.getppid()):
        allowed.add(os.getppid())  # launched by claude.roadmap.run_roadmap, which runs no numerics itself
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["pid"] not in allowed and "python" in (p.info["name"] or "").lower():
            raise RuntimeError("Another Python process exists; inspect before running: "+str(p.info["pid"]))
    prep = args.fixture.resolve()
    meta = json.loads((prep/"step.json").read_text())
    fixture = prep/"fixture.json"
    assert meta["status"] == "prepared" and sha(fixture) == meta["fixture_sha256"]
    epoch_count = json.loads(fixture.read_text())["context"]["epoch_count"]
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text())
    folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-long-"+args.label)
    folder.mkdir(parents=True)
    extra = [config_path.relative_to(ROOT).as_posix()]
    if config["nominal"] != "unit":
        assert sha(ROOT/config["nominal"]["path"]) == config["nominal"]["sha256"]
        extra.append(config["nominal"]["path"])
    if args.protocol:
        extra.append(args.protocol)
    pins = sources(extra=extra)
    pins[fixture.relative_to(ROOT).as_posix()] = meta["fixture_sha256"]
    for name in pins:
        if name.endswith(".py") or name.endswith(".md") or name == extra[0]:
            target = folder/"source"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, target)
    report = dict(status="running", controller_pid=os.getpid(), label=args.label, fixture=fixture.relative_to(ROOT).as_posix(),
                  config=extra[0], chunk_epochs=args.chunk_epochs, epoch_count=epoch_count, trajectory_groups=args.trajectory_groups,
                  source_sha256=pins, active_worker=None,
                  runs={}, state=None, final=None, accepted_trials=[], linearizations=[])

    def save():
        write_json(folder/"pending.json", report)
        (folder/"pending.json").replace(folder/"validation.json")

    def worker(name, module_args, timeout=300):
        for path, digest in report["source_sha256"].items():
            assert sha(ROOT/path) == digest, "Pinned input changed: "+path
        report["active_worker"] = dict(name=name, args=module_args)
        save()
        print("Starting "+name, flush=True)
        result, path = run(module_args, Limits(timeout_s=timeout))
        assert path.resolve().is_relative_to(ROOT/"runs")
        shutil.move(str(path), str(folder/name))
        report["runs"][name] = result
        report["active_worker"] = None
        save()
        print(name, result["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Stopped at "+name)
        return folder/name

    print("Campaign "+str(folder), flush=True)
    save()
    base = ["--fixture", str(fixture), "--config", str(config_path)]
    try:
        def integrate(tag, point_args, with_state=True):
            if not args.trajectory_groups:
                return []
            files = []
            for g in range(args.trajectory_groups):
                d = worker(f"{tag}-traj-{g}", ["claude.roadmap.traj_cache", "integrate", *(common if with_state else base), *point_args,
                                              "--group", str(g), "--groups", str(args.trajectory_groups)])
                files.append(str(d/"trajectories.npz"))
            return ["--trajectories", *files]

        # The x=0 trajectories serve both the pilot state and the first linearization.
        zero_cache = integrate("lin0", [], with_state=False)
        state_dir = worker("state", ["claude.roadmap.long_iteration", "state", *base, *zero_cache])
        state = state_dir/"state.json"
        report["state"] = dict(path=state.relative_to(folder).as_posix(), sha256=sha(state))
        save()
        common = [*base, "--state", str(state)]

        previous = None
        for i in range(args.max_linearizations):
            cache = zero_cache if i == 0 else integrate(f"lin{i}", ["--solution", str(previous)])
            checkpoint = None
            for start in range(0, epoch_count, args.chunk_epochs):
                stop = min(epoch_count, start+args.chunk_epochs)
                chunk_args = ["claude.roadmap.long_iteration", "chunk", *common, "--start", str(start), "--stop", str(stop), *cache]
                if previous:
                    chunk_args += ["--previous", str(previous)]
                if checkpoint:
                    chunk_args += ["--checkpoint", str(checkpoint)]
                checkpoint = worker(f"lin{i}-chunk-{start:03d}-{stop:03d}", chunk_args)
            solve_args = ["claude.roadmap.long_iteration", "solve", *common, "--checkpoint", str(checkpoint), *cache]
            if previous:
                solve_args += ["--previous", str(previous)]
            lin = worker(f"lin{i}-solve", solve_args)
            status = json.loads((lin/"step.json").read_text())["status"]
            report["linearizations"].append(lin.name)
            if status == "converged":
                report["final"] = lin.name
                save()
                break
            if i == args.max_linearizations-1:
                raise RuntimeError("Stationarity not reached before the linearization cap")
            accepted = False
            for ai, alpha in enumerate((1., .5, .25, .125)):
                trial_cache = integrate(f"lin{i}-trial-{ai}", ["--linear", str(lin), "--alpha", str(alpha)])
                tri = worker(f"lin{i}-trial-{ai}", ["claude.roadmap.long_iteration", "trial", *common, "--linear", str(lin),
                                                    "--alpha", str(alpha), *trial_cache])
                if json.loads((tri/"step.json").read_text())["status"] == "iteration_complete":
                    previous = tri
                    report["accepted_trials"].append(tri.name)
                    save()
                    accepted = True
                    break
            if not accepted:
                raise RuntimeError("Line search exhausted")
        report["status"] = "long_fit_complete_not_accuracy_acceptance"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        values = list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                      peak_job_memory_mib=max([v.get("windows_peak_job_memory_mib", 0) for v in values] or [0]),
                      minimum_system_available_gib=min([v.get("minimum_system_available_gib", float("inf")) for v in values] or [float("inf")]),
                      longest_worker_s=max([v.get("elapsed_s", 0) for v in values] or [0]))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*")
                                      if p.is_file() and p.name not in ("validation.json", "pending.json")}
        save()


if __name__ == "__main__":
    main()
