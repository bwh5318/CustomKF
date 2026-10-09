"""Serial controller for one fit with a named ERP + thrust variant (`Opus_Fork.nongrav_variants`).

Copy of `Opus_Fork.run_fit_nongrav` (pinned by P1/R7, unchanged); invoke as `-m Opus_Fork.run_fit_ngv --variant NAME ...`.
`--variant` is required, is set as `OPUSFORK_NONGRAV_VARIANT` for every worker, is pinned in the manifest,
and every worker must echo it back.

    C:\\anaconda\\python.exe -m Opus_Fork.run_fit_nongrav --fixture DIR --config CONFIG.json \
        --label LABEL --chunk-epochs 12 --trajectory-groups 2 --worker-timeout 900

Ancestry: `Opus_Fork/run_fit.py` -> `Opus_Fork/run_fit_nongrav.py` -> this file (hash in FORKED_FROM below).

A copy of `Opus_Fork.run_fit` with the scientific differences confined to the workers:
`Opus_Fork.nongrav_traj_cache` replaces `claude.roadmap.traj_cache`, and
`Opus_Fork.nongrav_iteration` replaces `Opus_Fork.iteration`. Linearization, chunking, line
search, caps, content-bound resume and the one-job-at-a-time checks are unchanged.

Additions:

- the force-model binding (variant, `nongrav.py` hash, satellite-metadata hash) is pinned in the
  manifest;
- every iteration worker must leave a matching `force_model.json`;
- every trajectory cache must carry the same binding, which the workers enforce.

The ERP/thrust source files and the metadata SINEX are pinned inputs.
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
from claude.roadmap.common import write_json

from .guard import Limits, PROFILES, run
from .run_fit import fork_sources, fork_provenance, artifact_pins, RUNS
from .ngv_pilot import model_binding
from . import nongrav_variants as nv
from . import satmeta

FORKED_FROM = {"Opus_Fork/run_fit_nongrav.py": "1a566762d4c4698a222c5a5768555d46b28115d08c732d485a028f7d6295a441"}
EXTRA_PINS = ("Opus_Fork/nongrav.py", "Opus_Fork/nongrav_variants.py", "Opus_Fork/ngv_pilot.py", "Opus_Fork/ngv_iteration.py",
              "Opus_Fork/ngv_traj_cache.py", "Opus_Fork/satmeta.py", "Opus_Fork/run_fit_ngv.py",
              "Opus_Fork/datastore/static/igs_satellite_metadata.snx")
TRAJ, ITER = "Opus_Fork.ngv_traj_cache", "Opus_Fork.ngv_iteration"


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run the controller directly, never inside a guard"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--chunk-epochs", type=int, required=True)
    parser.add_argument("--max-linearizations", type=int, default=4)
    parser.add_argument("--protocol", default=None)
    parser.add_argument("--trajectory-groups", type=int, required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="fork8")
    parser.add_argument("--worker-timeout", type=float, default=900.)
    parser.add_argument("--resume", type=Path, default=None)
    parser.add_argument("--variant", choices=tuple(nv.VARIANTS), required=True)
    args = parser.parse_args()
    os.environ[nv.ENVIRONMENT] = args.variant  # inherited by every guarded worker
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["pid"] != os.getpid() and "python" in (p.info["name"] or "").lower():
            raise RuntimeError("Another Python process exists; inspect before running: "+str(p.info["pid"]))
    if args.trajectory_groups < 1:
        raise ValueError("This controller integrates every trajectory in the nongrav cache worker")

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
    pins = fork_sources(extra=extra+list(EXTRA_PINS))
    pins[fixture.relative_to(ROOT).as_posix()] = meta["fixture_sha256"]
    binding = model_binding()

    if args.resume:
        folder = args.resume.resolve()
        if not folder.is_relative_to(RUNS.resolve()):
            raise ValueError("Resume folder must be under Opus_Fork/runs")
        report = json.loads((folder/"validation.json").read_text())
        if report["status"] not in ("running", "failed", "interrupted"):
            raise ValueError("Refusing to resume a campaign with status "+report["status"])
        if report["fixture"] != fixture.relative_to(ROOT).as_posix() or report["label"] != args.label \
                or report["force_model"] != binding:
            raise ValueError("Resume target is a different fixture, label or force model")
        shutil.copyfile(folder/"validation.json", folder/("validation.before-resume-"+uuid.uuid4().hex[:8]+".json"))
        changed = [p for p, d in report["source_sha256"].items() if sha(ROOT/p) != d]
        if changed:
            raise ValueError("Pinned input changed since the campaign started: "+", ".join(changed))
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
        report.update(status="running", controller_pid=os.getpid(), active_worker=None, state=None, final=None,
                      accepted_trials=[], linearizations=[], resumed_utc=datetime.now(timezone.utc).isoformat())
        print(f"Resuming {folder}: {len(report['runs'])} workers reusable, {len(stale)} to rerun", flush=True)
        return _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding)

    folder = RUNS/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-fit-"+args.label)
    folder.mkdir(parents=True)
    for name in pins:
        if name.endswith(".py") or name.endswith(".md") or name == extra[0]:
            target = folder/"source"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, target)
    report = dict(status="running", guard="Opus_Fork", forked_from=FORKED_FROM, profile=args.profile,
                  limits={k: getattr(limits, k) for k in ("memory_mib", "cpu_percent", "threads", "processes", "timeout_s")},
                  controller_pid=os.getpid(), label=args.label, force_model=binding,
                  satellite_metadata=satmeta.provenance(),
                  fixture=fixture.relative_to(ROOT).as_posix(), config=extra[0],
                  chunk_epochs=args.chunk_epochs, epoch_count=epoch_count,
                  trajectory_groups=args.trajectory_groups, source_sha256=pins,
                  fork_provenance_sha256=fork_provenance(),
                  active_worker=None, runs={}, state=None, final=None, accepted_trials=[], linearizations=[])
    return _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding)


def _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding):
    def save():
        write_json(folder/"pending.json", report)
        (folder/"pending.json").replace(folder/"validation.json")

    def worker(name, module_args, timeout=None):
        for path, digest in report["source_sha256"].items():
            assert sha(ROOT/path) == digest, "Pinned input changed: "+path
        done = report["runs"].get(name)
        if done and done.get("status") == "ok" and (folder/name).is_dir():
            if done.get("args") == module_args and artifact_pins(folder/name) == done.get("files_sha256"):
                print(name+" reused", flush=True)
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
        report["runs"][name] = dict(result, args=module_args, files_sha256=artifact_pins(folder/name))
        report["active_worker"] = None
        save()
        print(name, result["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Stopped at "+name)
        produced = folder/name/("force_model.json" if module_args[0] == ITER else "trajectories.json")
        recorded = json.loads(produced.read_text())
        if (recorded if module_args[0] == ITER else recorded.get("force_model")) != binding:
            raise RuntimeError("Worker did not use the pinned force model: "+name)
        return folder/name

    print("Campaign "+str(folder), flush=True)
    save()
    base = ["--fixture", str(fixture), "--config", str(config_path)]
    common = base
    try:
        def integrate(tag, point_args, with_state=True):
            files = []
            for g in range(args.trajectory_groups):
                d = worker(f"{tag}-traj-{g}", [TRAJ, "integrate", *(common if with_state else base), *point_args,
                                               "--group", str(g), "--groups", str(args.trajectory_groups)])
                files.append(str(d/"trajectories.npz"))
            return ["--trajectories", *files]

        zero_cache = integrate("lin0", [], with_state=False)
        state_dir = worker("state", [ITER, "state", *base, *zero_cache])
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
                chunk_args = [ITER, "chunk", *common, "--start", str(start), "--stop", str(stop), *cache]
                if previous:
                    chunk_args += ["--previous", str(previous)]
                if checkpoint:
                    chunk_args += ["--checkpoint", str(checkpoint)]
                checkpoint = worker(f"lin{i}-chunk-{start:03d}-{stop:03d}", chunk_args)
            solve_args = [ITER, "solve", *common, "--checkpoint", str(checkpoint), *cache]
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
                tri = worker(f"lin{i}-trial-{ai}", [ITER, "trial", *common, "--linear", str(lin),
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
        print("Campaign status:", report["status"], flush=True)


if __name__ == "__main__":
    main()
