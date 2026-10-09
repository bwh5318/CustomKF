"""Serial controller for an elevation-handling variant of the sub-daily-EOP fit (`Opus_Fork.elev`).

Copy of `Opus_Fork.run_fit_sd` (pinned by the SD campaigns): workers `Opus_Fork.elev_traj_cache` /
`Opus_Fork.elev_iteration`, `--variant` from `elev.VARIANTS` exported as `OPUSFORK_ELEV_VARIANT`, binding
`elev.binding()`, and `elev.py` as a pinned input. Everything else is unchanged. Protocol: `results/ELEVATION_PROTOCOL.md`.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from customkf.prepare_stage2 import ROOT, sha
from customkf.runtime import lease, processes as process_check
from claude.roadmap.common import write_json

from .guard import Limits, PROFILES, run
from .run_fit import fork_sources, fork_provenance, artifact_pins, RUNS
from . import artifacts
from . import elev
from . import gradients
from . import satmeta

FORKED_FROM = {"Opus_Fork/run_fit_sd.py": "ba7385b04a855368ee6b3f374e6c3a11667661444e345b8b6521fc4fddf65915"}
EXTRA_PINS = ("Opus_Fork/nongrav.py", "Opus_Fork/nongrav_variants.py", "Opus_Fork/ngv_pilot.py", "Opus_Fork/ngv_traj_cache.py",
              "Opus_Fork/sdeop.py", "Opus_Fork/elev.py", "Opus_Fork/elev_iteration.py", "Opus_Fork/elev_traj_cache.py",
              "Opus_Fork/subdaily_eop.py",
              "Opus_Fork/datastore/static/iers_ch8/ORTHO_EOP.F", "Opus_Fork/datastore/static/iers_ch8/CNMTX.F",
              "Opus_Fork/satmeta.py", "Opus_Fork/run_fit_elev.py",
              "Opus_Fork/datastore/static/igs_satellite_metadata.snx",
              # Executed since 29 Sep 2026 (campaign lease); pinned and copied for new campaigns (Astra Part B, B04).
              "customkf/runtime/__init__.py", "customkf/runtime/lease.py",
              # Worker-array validation (Astra E-01, 2 Oct 2026); also the gradient fields (experiments/gradients).
              "Opus_Fork/artifacts.py", "Opus_Fork/gradients.py",
              # Which processes the guard and this controller wait for (user decision, 3 Oct 2026).
              "customkf/runtime/processes.py")
TRAJ, ITER = "Opus_Fork.elev_traj_cache", "Opus_Fork.elev_iteration"


def move_folder(source, target, attempts=32, delay_s=.25):
    """Move a finished guard folder into its campaign by rename only, retrying while Windows still holds a handle.

    `shutil.move` falls back to copy-and-delete when a rename fails. On 3 Oct 2026 (V-gpt3-0723, lin2-traj-1, after a
    CPU-limit stop) a worker descendant that was still exiting held stderr.log open: the copy completed, the delete did
    not, and the campaign stopped with both folders on disk. Both folders are under Opus_Fork/runs, so a rename always
    suffices; it never overwrites, and a failed one leaves the source intact. The retries span about a minute.
    """
    for attempt in range(attempts):
        try:
            os.rename(source, target)
            return
        except PermissionError:
            if attempt == attempts-1:
                raise
            time.sleep(min(delay_s*2**attempt, 2.))


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
    parser.add_argument("--variant", choices=tuple(elev.VARIANTS), required=True)
    parser.add_argument("--eliminate-ambiguities", action="store_true",
                        help="fold each ambiguity out of the streaming solve once its arc has ended "
                             "(EliminatingAccumulator; 7 Oct 2026, networks larger than 25 stations)")
    parser.add_argument("--legacy-resume", action="store_true",
                        help="resume a campaign recorded before the specification existed; the request's values for the "
                             "fields it lacks are recorded as assumed")
    args = parser.parse_args()
    os.environ[elev.ENVIRONMENT] = args.variant  # inherited by every guarded worker
    # This project's guard and campaign-controller processes only (user decision 3 Oct 2026; any Python until then).
    others = process_check.campaign_processes()
    if others:
        raise RuntimeError("Another guard or campaign-controller Python process of this project exists; inspect before "
                           "running: "+", ".join(map(str, others)))
    if args.trajectory_groups < 1:
        raise ValueError("This controller integrates every trajectory in the nongrav cache worker")

    memory, cpu, threads, processes, scratch = PROFILES[args.profile]
    limits = Limits(memory_mib=memory, cpu_percent=cpu, threads=threads, processes=processes,
                    scratch_mib=scratch, timeout_s=args.worker_timeout)
    prep = args.fixture.resolve()
    meta = json.loads((prep/"step.json").read_text())
    fixture = prep/"fixture.json"
    assert meta["status"] == "prepared" and sha(fixture) == meta["fixture_sha256"]
    context = json.loads(fixture.read_text())["context"]
    epoch_count = context["epoch_count"]
    # The arc's gradient input files, inherited by every worker (gradients.arc_days; defect fix 3 Oct 2026).
    os.environ[gradients.ARC_ENVIRONMENT] = ",".join(gradients.arc_days(int(context["origin_ns"]), context["duration_s"]))
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
    binding = elev.binding()
    spec = specification(args, fixture, meta, config_path, extra[0], binding)

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
        changed = [p for p, d in report["source_sha256"].items() if sha(ROOT/p) != d]
        if changed:
            raise ValueError("Pinned input changed since the campaign started: "+", ".join(changed))
        continuation = check_resume_request(report, spec, args)
        # The campaign lease is taken before the first mutation of the resume target (Astra Part B, B01): a refusal
        # leaves validation.json and every worker directory exactly as they were.
        with lease.campaign(args.label, "Opus_Fork.run_fit_elev") as held:
            return _resume(args, folder, report, fixture, config_path, epoch_count, limits, binding, held, continuation)

    with lease.campaign(args.label, "Opus_Fork.run_fit_elev") as held:
        return _start(args, pins, extra, fixture, meta, config_path, epoch_count, limits, binding, held, spec)


SPEC_VERSION = 1
LEGACY_FIELDS = ("fixture", "config", "label", "force_model", "chunk_epochs", "trajectory_groups", "profile")


def specification(args, fixture, meta, config_path, config_name, binding):
    """The immutable campaign specification (Sol review SOL-02): everything that defines the fit."""
    return dict(version=SPEC_VERSION, fixture=fixture.relative_to(ROOT).as_posix(), fixture_sha256=meta["fixture_sha256"],
                config=config_name, config_sha256=sha(config_path), label=args.label, variant=args.variant,
                force_model=binding, protocol=args.protocol,
                protocol_sha256=sha(ROOT/args.protocol) if args.protocol else None,
                chunk_epochs=args.chunk_epochs, trajectory_groups=args.trajectory_groups,
                max_linearizations=args.max_linearizations, profile=args.profile,
                # Recorded only when set, so campaigns from before 7 Oct 2026 keep an identical specification.
                **({"eliminate_ambiguities": True} if getattr(args, "eliminate_ambiguities", False) else {}))


def check_resume_request(report, spec, args):
    """Refuse, before any mutation, a resume request that differs from the campaign's recorded specification.

    The worker timeout is the one operational setting a continuation may change; the change is recorded. A campaign
    recorded before the specification existed is checked on the fields it does record, and needs --legacy-resume to
    proceed; the request's values for the fields it lacks are then recorded as assumed in a continuation entry,
    never written into the original record as if they had been there.
    """
    recorded = report.get("spec")
    timeout = report.get("limits", {}).get("timeout_s")
    continuation = dict(utc=datetime.now(timezone.utc).isoformat())
    if timeout is not None and float(timeout) != float(args.worker_timeout):
        continuation["worker_timeout_s"] = dict(recorded=timeout, requested=args.worker_timeout)
    if recorded is not None:
        differs = {k: dict(recorded=recorded.get(k), requested=v) for k, v in spec.items() if recorded.get(k) != v}
        if differs:
            raise ValueError("Resume request differs from the campaign specification: "+json.dumps(differs, default=str))
        return continuation
    differs = {k: dict(recorded=report.get(k), requested=spec[k]) for k in LEGACY_FIELDS if report.get(k) != spec[k]}
    if differs:
        raise ValueError("Resume request differs from the legacy campaign record: "+json.dumps(differs, default=str))
    if not args.legacy_resume:
        raise ValueError("Campaign predates the recorded specification; pass --legacy-resume to accept the request's "
                         "values for the fields it does not record")
    assumed = {k: v for k, v in spec.items() if k not in LEGACY_FIELDS}
    conflicts = {k: dict(recorded=v, requested=assumed.get(k), source="pinned protocol")
                 for k, v in legacy_protocol(report).items() if assumed.get(k) != v}
    # A value assumed by an earlier continuation is no longer absent (Astra AR-04): later resumes must match it.
    for earlier in report.get("continuations", []):
        for k, v in (earlier.get("legacy_assumed") or {}).items():
            if assumed.get(k) != v:
                conflicts.setdefault(k, dict(recorded=v, requested=assumed.get(k),
                                             source="continuation "+str(earlier.get("utc"))))
    if conflicts:
        raise ValueError("Legacy resume conflicts with values the campaign already records: "
                         +json.dumps(conflicts, default=str))
    continuation["legacy_assumed"] = assumed
    return continuation


def legacy_protocol(report):
    """The protocol a pre-specification campaign was started with, recovered from its source pins (Astra AR-04).

    A campaign pins Python sources, model tables and the declared extras (config, calibration, --protocol); the
    protocol is the only Markdown document among them, so it is recoverable exactly, with its hash.
    """
    documents = [p for p in report.get("source_sha256", {}) if p.endswith(".md")]
    if len(documents) > 1:
        raise ValueError(f"Legacy record pins several documents {documents}; its protocol is ambiguous")
    if not documents:
        return dict(protocol=None, protocol_sha256=None)
    return dict(protocol=documents[0], protocol_sha256=report["source_sha256"][documents[0]])


# Completed worker output sets (Sol SOL-06, Astra AR-02): for each iteration mode, the step statuses that complete the
# worker and the array each status must have produced, with the step key holding its hash. A rejected line-search
# trial is a completed worker (the controller records and inspects it), never an accepted point: accepted_point
# refuses its status.
WORKER_OUTPUTS = {"state": {"state_ready": ("state.json", "state_sha256")},
                  "chunk": {"chunk_complete": ("checkpoint.npz", "checkpoint_sha256")},
                  "solve": {"converged": ("solution.npz", "solution_sha256"),
                            "linearized": ("direction.npz", "direction_sha256")},
                  "trial": {"iteration_complete": ("solution.npz", "solution_sha256"), "trial_rejected": (None, None)}}
ARTIFACT_KINDS = {"state.json": "state", "checkpoint.npz": "checkpoint", "solution.npz": "solution",
                  "direction.npz": "direction", None: None}


def worker_rejection(path, module_args, binding, identity):
    """None, or why a worker's output set cannot be accepted, at first acceptance and again on reuse.

    Required: the force-model declaration equal to the pinned binding (SOL-06), and (Astra AR-02) the worker kind's
    complete artifact set: a permitted status, the produced array present and equal to its recorded hash, and the
    campaign's fixture/config (and state, once it exists) in the record. A declaration alone is not a completed
    worker.
    """
    def load(name):
        return json.loads((path/name).read_text())
    if module_args[0] == TRAJ:
        if not (path/"trajectories.json").is_file():
            return "required record missing: trajectories.json"
        meta = load("trajectories.json")
        if meta.get("force_model") != binding:
            return "worker did not use the pinned force model"
        if meta.get("status") != "trajectory_cache" or not isinstance(meta.get("satellites"), list) \
                or not meta["satellites"] or not isinstance(meta.get("keys"), dict) \
                or sorted(meta["keys"]) != sorted(meta["satellites"]):
            return "invalid trajectory-cache record"
        if not (path/"trajectories.npz").is_file():
            return "required output missing: trajectories.npz"
        if sha(path/"trajectories.npz") != meta.get("cache_sha256"):
            return "trajectories.npz does not match its recorded hash"
        if meta.get("fixture_sha256") != identity["fixture"] or meta.get("config_sha256") != identity["config"]:
            return "bound to a different fixture or config"
        # A matching hash does not make the array usable (Astra E-01): open it and check its layout and values.
        return artifacts.rejection("trajectories", path/"trajectories.npz", meta["satellites"])
    if not (path/"force_model.json").is_file():
        return "required record missing: force_model.json"
    if load("force_model.json") != binding:
        return "worker did not use the pinned force model"
    mode = module_args[1]
    if mode not in WORKER_OUTPUTS:
        return f"unknown worker mode {mode!r}"
    if not (path/"step.json").is_file():
        return "required record missing: step.json"
    step = load("step.json")
    status = step.get("status")
    if status not in WORKER_OUTPUTS[mode]:
        return f"status {status!r} does not complete a {mode} worker"
    output, key = WORKER_OUTPUTS[mode][status]
    if output is not None:
        if not (path/output).is_file():
            return f"required output missing: {output}"
        if sha(path/output) != step.get(key):
            return f"{output} does not match its recorded hash"
    if mode == "state":
        recorded = load("state.json")
        bound = dict(fixture=recorded.get("fixture_sha256"), config=recorded.get("config_sha256"))
    elif status == "trial_rejected":
        return None if isinstance(step.get("record"), dict) else "rejected trial without its record"
    else:
        bound = step.get("binding") or {}
    if bound.get("fixture") != identity["fixture"] or bound.get("config") != identity["config"]:
        return "bound to a different fixture or config"
    if mode != "state" and identity.get("state") and bound.get("state") != identity["state"]:
        return "bound to a different state"
    # Open the produced array/record and check its kind-specific layout and finite values (Astra E-01).
    return artifacts.rejection(ARTIFACT_KINDS[output], path/output)


def _resume(args, folder, report, fixture, config_path, epoch_count, limits, binding, held, continuation):
    shutil.copyfile(folder/"validation.json", folder/("validation.before-resume-"+uuid.uuid4().hex[:8]+".json"))
    report.setdefault("continuations", []).append(continuation)
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
    return _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding, held=held)


def _start(args, pins, extra, fixture, meta, config_path, epoch_count, limits, binding, held, spec):
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
                  trajectory_groups=args.trajectory_groups, source_sha256=pins, spec=spec,
                  fork_provenance_sha256=fork_provenance(),
                  active_worker=None, runs={}, state=None, final=None, accepted_trials=[], linearizations=[])
    return _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding, held=held)


def _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding, *, held=None):
    # Campaign lease (M14): held across worker gaps and back-off until the end. A direct caller without one gets it
    # here, before the first write (Astra Part B, B01); a real `with` boundary makes cleanup unconditional even when
    # the final report or artifact hashing fails (B03).
    if held is None:
        with lease.campaign(args.label, "Opus_Fork.run_fit_elev") as held:
            return _drive(args, folder, report, fixture, config_path, epoch_count, limits, binding, held=held)
    report["campaign_lease"] = held.id

    def save():
        write_json(folder/"pending.json", report)
        (folder/"pending.json").replace(folder/"validation.json")

    identity = dict(fixture=sha(fixture), config=sha(config_path))

    def rejection(name, module_args):
        """Semantic acceptance (Sol SOL-06, Astra AR-02): None, or why the worker's output set cannot be accepted."""
        return worker_rejection(folder/name, module_args, binding,
                                dict(identity, state=(report.get("state") or {}).get("sha256")))

    def worker(name, module_args, timeout=None):
        for path, digest in report["source_sha256"].items():
            assert sha(ROOT/path) == digest, "Pinned input changed: "+path
        done = report["runs"].get(name)
        if done and done.get("status") == "ok" and (folder/name).is_dir():
            if done.get("args") == module_args and artifact_pins(folder/name) == done.get("files_sha256"):
                reason = rejection(name, module_args)
                if reason:
                    raise RuntimeError(f"Recorded worker fails acceptance on reuse ({reason}); preserve and inspect: {name}")
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
        move_folder(path, folder/name)
        record = dict(result, args=module_args, files_sha256=artifact_pins(folder/name))
        reason = rejection(name, module_args) if result["status"] == "ok" else None
        if reason:      # guard success is not acceptance: record the rejection, never a reusable `ok`
            record.update(status="rejected", guard_status=result["status"], rejection=reason)
        report["runs"][name] = record
        report["active_worker"] = None
        save()
        print(name, record["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if record["status"] != "ok":
            raise RuntimeError("Stopped at "+name+(f": {reason}" if reason else ""))
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
        eliminate = ["--eliminate-ambiguities"] if getattr(args, "eliminate_ambiguities", False) else []
        previous = None
        for i in range(args.max_linearizations):
            cache = zero_cache if i == 0 else integrate(f"lin{i}", ["--solution", str(previous)])
            checkpoint = None
            for start in range(0, epoch_count, args.chunk_epochs):
                stop = min(epoch_count, start+args.chunk_epochs)
                chunk_args = [ITER, "chunk", *common, "--start", str(start), "--stop", str(stop), *cache, *eliminate]
                if previous:
                    chunk_args += ["--previous", str(previous)]
                if checkpoint:
                    chunk_args += ["--checkpoint", str(checkpoint)]
                checkpoint = worker(f"lin{i}-chunk-{start:03d}-{stop:03d}", chunk_args)
            solve_args = [ITER, "solve", *common, "--checkpoint", str(checkpoint), *cache, *eliminate]
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
