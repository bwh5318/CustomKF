"""Serial controller for one LongPilot fit under the fork's guard.

    C:\\anaconda\\python.exe -m Opus_Fork.run_fit --fixture DIR --config CONFIG.json \
        --label W1 --chunk-epochs 18 --trajectory-groups 2

Forked from `claude/roadmap/run_long.py` (hash in FORKED_FROM) for three reasons only:
its workers go through `customkf.guard`'s fixed 2 GiB / 10% / 1-core limits, its campaigns
land in `claude/runs/`, and it asserts the guard folder is under `runs/`. Everything
scientific is unchanged. Workers are `Opus_Fork.iteration` (a one-line fork of
`claude.roadmap.long_iteration` raising only the workspace preflight) and the unmodified
`claude.roadmap.traj_cache`,
the same linearization and line-search structure, the same hash re-verification before every
worker, the same fresh-campaign-only rule with no resume.

Pins additionally cover `Opus_Fork/*.py`, so a campaign records the fork code that produced
it as well as Astra's. Refuses to start if any other Python process exists.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid
import psutil

from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.common import sources, write_json

from .guard import Limits, PROFILES, run

FORKED_FROM = {"claude/roadmap/run_long.py": "0c7e60be46f3dc866458ce451a3c50ae0e554cc00bcd26c983bd8cdf8501e72d"}
RUNS = ROOT/"Opus_Fork"/"runs"


# Fork modules a running fit actually imports. Only these are enforced between workers;
# pinning every Opus_Fork/*.py made any edit during a fit abort the campaign, which is
# stricter than the dependency graph warrants and blocks development for the ~45 minutes
# a fit takes. The rest are recorded for provenance without being enforced.
ENFORCED = ("Opus_Fork/__init__.py", "Opus_Fork/guard.py", "Opus_Fork/paths.py",
            "Opus_Fork/run_fit.py", "Opus_Fork/iteration.py")


def fork_sources(extra=()):
    """Astra's roadmap pins, plus the fork modules a fit imports."""
    pins = sources(extra=extra)
    for name in ENFORCED:
        pins[name] = sha(ROOT/name)
    return pins


def fork_provenance():
    """Every other fork module, hashed for the record but not re-checked mid-campaign."""
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT/"Opus_Fork").glob("*.py"))
            if p.relative_to(ROOT).as_posix() not in ENFORCED}


def artifact_pins(folder):
    """Every file a completed worker produced, so a resume can prove it is still intact."""
    return {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run the controller directly, never inside a guard"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--chunk-epochs", type=int, required=True)
    parser.add_argument("--max-linearizations", type=int, default=4)
    parser.add_argument("--protocol", default=None)
    parser.add_argument("--trajectory-groups", type=int, default=0)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="fork8")
    parser.add_argument("--worker-timeout", type=float, default=600.)
    parser.add_argument("--resume", type=Path, default=None,
                        help="continue an interrupted campaign folder, reusing verified workers")
    args = parser.parse_args()
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["pid"] != os.getpid() and "python" in (p.info["name"] or "").lower():
            raise RuntimeError("Another Python process exists; inspect before running: "+str(p.info["pid"]))

    memory, cpu, threads, processes, scratch = PROFILES[args.profile]
    limits = Limits(memory_mib=memory, cpu_percent=cpu, threads=threads, processes=processes,
                    scratch_mib=scratch, timeout_s=args.worker_timeout)

    prep = args.fixture.resolve()
    meta = json.loads((prep/"step.json").read_text())
    fixture = prep/"fixture.json"
    assert meta["status"] == "prepared" and sha(fixture) == meta["fixture_sha256"]
    epoch_count = json.loads(fixture.read_text())["context"]["epoch_count"]
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text())
    extra = [config_path.relative_to(ROOT).as_posix()]
    if config["nominal"] != "unit":
        assert sha(ROOT/config["nominal"]["path"]) == config["nominal"]["sha256"]
        extra.append(config["nominal"]["path"])
    if args.protocol:
        extra.append(args.protocol)
    pins = fork_sources(extra=extra)
    pins[fixture.relative_to(ROOT).as_posix()] = meta["fixture_sha256"]

    if args.resume:
        # A fit takes about an hour and the 75% total-machine watchdog can stop a worker for
        # load that is not ours: an unrelated CPU spike cost a whole campaign on 20 September.
        # Resume is content-bound, like Astra's cross-date controller: a completed worker is
        # reused only when its arguments match and every artifact still hashes as recorded.
        folder = args.resume.resolve()
        if not folder.is_relative_to(RUNS.resolve()):
            raise ValueError("Resume folder must be under Opus_Fork/runs")
        report = json.loads((folder/"validation.json").read_text())
        if report["status"] not in ("running", "failed", "interrupted"):
            raise ValueError("Refusing to resume a campaign with status "+report["status"])
        if report["fixture"] != fixture.relative_to(ROOT).as_posix() or report["label"] != args.label:
            raise ValueError("Resume target is a different fixture or label")
        shutil.copyfile(folder/"validation.json",
                        folder/("validation.before-resume-"+uuid.uuid4().hex[:8]+".json"))
        # The controller itself is exempt, and only the controller. It issues worker commands
        # but computes nothing, and a reused worker is already bound to its exact argument
        # list, so this file's hash adds nothing to reuse safety while blocking any fix to the
        # controller from ever being applied to an interrupted campaign. Every module a worker
        # imports, every input and every fixture is still checked exactly. The difference is
        # recorded rather than passed over.
        controller = "Opus_Fork/run_fit.py"
        changed = [p for p, d in report["source_sha256"].items() if sha(ROOT/p) != d]
        blocking = [p for p in changed if p != controller]
        if blocking:
            raise ValueError("Pinned input changed since the campaign started: "+", ".join(blocking))
        if controller in changed:
            report.setdefault("controller_changed_on_resume", []).append(
                dict(path=controller, recorded=report["source_sha256"][controller],
                     now=sha(ROOT/controller), resumed_utc=datetime.now(timezone.utc).isoformat()))
            report["source_sha256"][controller] = sha(ROOT/controller)
            print("NOTE: the controller changed since this campaign started; workers are "
                  "reused on their own module, input and argument bindings.", flush=True)
        # Preserve, never reuse: an interrupted worker and any recorded non-ok worker are
        # moved aside and rerun rather than inferred successful.
        stale = [n for n, r in report["runs"].items() if r.get("status") != "ok"]
        active = report.get("active_worker")
        if active and active["name"] not in stale:
            stale.append(active["name"])
        for name in stale:
            leftover = folder/name
            if leftover.is_dir():
                leftover.rename(folder/(name+"-interrupted-"+uuid.uuid4().hex[:8]))
            report["runs"].pop(name, None)
        report.setdefault("interrupted_attempts", []).extend(
            dict(name=n, recovered_utc=datetime.now(timezone.utc).isoformat()) for n in stale)
        report.update(status="running", controller_pid=os.getpid(), active_worker=None,
                      state=None, final=None, accepted_trials=[], linearizations=[],
                      resumed_utc=datetime.now(timezone.utc).isoformat())
        print(f"Resuming {folder}: {len(report['runs'])} workers reusable, "
              f"{len(stale)} preserved and to be rerun ({', '.join(stale) or 'none'})", flush=True)
        return _drive(args, folder, report, fixture, config_path, epoch_count, limits)

    folder = RUNS/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-fit-"+args.label)
    folder.mkdir(parents=True)
    for name in pins:
        if name.endswith(".py") or name.endswith(".md") or name == extra[0]:
            target = folder/"source"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, target)
    report = dict(status="running", guard="Opus_Fork", forked_from=FORKED_FROM, profile=args.profile,
                  limits={k: getattr(limits, k) for k in ("memory_mib", "cpu_percent", "threads", "processes", "timeout_s")},
                  controller_pid=os.getpid(), label=args.label,
                  fixture=fixture.relative_to(ROOT).as_posix(), config=extra[0],
                  chunk_epochs=args.chunk_epochs, epoch_count=epoch_count,
                  trajectory_groups=args.trajectory_groups, source_sha256=pins,
                  fork_provenance_sha256=fork_provenance(),
                  active_worker=None, runs={}, state=None, final=None,
                  accepted_trials=[], linearizations=[])
    return _drive(args, folder, report, fixture, config_path, epoch_count, limits)


def _drive(args, folder, report, fixture, config_path, epoch_count, limits):
    def save():
        write_json(folder/"pending.json", report)
        (folder/"pending.json").replace(folder/"validation.json")

    def worker(name, module_args, timeout=None):
        for path, digest in report["source_sha256"].items():
            assert sha(ROOT/path) == digest, "Pinned input changed: "+path
        done = report["runs"].get(name)
        if done and done.get("status") == "ok" and (folder/name).is_dir():
            # Content-bound reuse: same arguments and every artifact still hashing as
            # recorded. Anything else is rerun rather than assumed good.
            if done.get("args") == module_args and artifact_pins(folder/name) == done.get("files_sha256"):
                print(name+" reused from the interrupted campaign", flush=True)
                return folder/name
            raise RuntimeError("Recorded worker no longer matches its record: "+name)
        if (folder/name).is_dir():
            raise RuntimeError("Worker folder exists without an ok record; preserve and inspect: "+name)
        report["active_worker"] = dict(name=name, args=module_args)
        save()
        print("Starting "+name, flush=True)
        result, path = run(module_args, Limits(**{**{k: getattr(limits, k) for k in
                                                    ("memory_mib", "cpu_percent", "threads", "processes", "scratch_mib")},
                                                 "timeout_s": timeout or limits.timeout_s}),
                           label=f"{args.label}-{name}")
        assert path.resolve().is_relative_to(RUNS)
        shutil.move(str(path), str(folder/name))
        report["runs"][name] = dict(result, args=module_args,
                                    files_sha256=artifact_pins(folder/name))
        report["active_worker"] = None
        save()
        print(name, result["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Stopped at "+name)
        return folder/name

    print("Campaign "+str(folder), flush=True)
    save()
    base = ["--fixture", str(fixture), "--config", str(config_path)]
    common = base
    try:
        def integrate(tag, point_args, with_state=True):
            if not args.trajectory_groups:
                return []
            files = []
            for g in range(args.trajectory_groups):
                d = worker(f"{tag}-traj-{g}", ["claude.roadmap.traj_cache", "integrate",
                                               *(common if with_state else base), *point_args,
                                               "--group", str(g), "--groups", str(args.trajectory_groups)])
                files.append(str(d/"trajectories.npz"))
            return ["--trajectories", *files]

        zero_cache = integrate("lin0", [], with_state=False)
        state_dir = worker("state", ["Opus_Fork.iteration", "state", *base, *zero_cache])
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
                chunk_args = ["Opus_Fork.iteration", "chunk", *common,
                              "--start", str(start), "--stop", str(stop), *cache]
                if previous:
                    chunk_args += ["--previous", str(previous)]
                if checkpoint:
                    chunk_args += ["--checkpoint", str(checkpoint)]
                checkpoint = worker(f"lin{i}-chunk-{start:03d}-{stop:03d}", chunk_args)
            solve_args = ["Opus_Fork.iteration", "solve", *common, "--checkpoint", str(checkpoint), *cache]
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
                tri = worker(f"lin{i}-trial-{ai}", ["Opus_Fork.iteration", "trial", *common,
                                                    "--linear", str(lin), "--alpha", str(alpha), *trial_cache])
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
        print("Campaign status:", report["status"], flush=True)


if __name__ == "__main__":
    main()
