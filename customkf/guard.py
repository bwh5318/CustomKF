"""Run a Python module inside verified Windows limits: python -m customkf.guard -- MODULE ..."""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

import psutil
from .winjob import Job, Worker, create_mutex, close_handle, check, C

ROOT = Path(__file__).resolve().parents[1]
GIB = 2**30
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS", "BLIS_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS")


@dataclass(frozen=True)
class Limits:
    memory_mib: int = 2048
    cpu_percent: float = 10
    threads: int = 1
    timeout_s: float = 300
    reserve_gib: float = 2      # user decision 2 Oct 2026 (was 8): stop request below this much free memory
    emergency_gib: float = 1    # user decision 2 Oct 2026 (was 6): terminate below this
    grace_s: float = 3
    scratch_mib: int = 128

    def validate(self):
        if (not all(math.isfinite(float(x)) for x in asdict(self).values())
                or not 64 <= self.memory_mib <= 4096
                or not 0 < self.cpu_percent <= 15
                or self.threads not in (1, 2)
                or not 0 < self.timeout_s <= 3600
                or self.reserve_gib < 2 or self.emergency_gib < 1
                or self.emergency_gib >= self.reserve_gib
                or not 0 <= self.grace_s <= 5 or not 1 <= self.scratch_mib <= 1024):
            raise ValueError("Limits outside the Stage 0 policy (max 4 GiB /15% /2 threads)")


def pressure_action(available, limits, elapsed_under_pressure):
    if available < limits.emergency_gib * GIB:
        return "terminate"
    if available < limits.reserve_gib * GIB:
        return "terminate" if elapsed_under_pressure >= limits.grace_s else "request_stop"
    return "continue"


def scratch_bytes(folder):
    """Total size of the files under `folder` for the scratch ceiling.

    A worker may delete its own temporary files while the monitor walks the folder. A file or directory that
    disappears between enumeration and stat is skipped instead of aborting the job (Astra follow-up review AF-01:
    an actual reviewer job ended `controller_failed` on such a race). Any other error (permission, IO) propagates.
    The ceiling itself is unchanged.
    """
    total, pending = 0, [str(folder)]
    while pending:
        try:
            entries = list(os.scandir(pending.pop()))
        except FileNotFoundError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                elif entry.is_file():
                    total += entry.stat().st_size
            except FileNotFoundError:
                continue
    return total


def run(module_args, limits=Limits(), *, usage_ceiling=None):
    limits.validate()
    if usage_ceiling is not None and (not math.isfinite(usage_ceiling) or not 0 < usage_ceiling <= 75):
        raise ValueError('Machine usage ceiling must be positive and at most 75 percent')
    if not module_args or module_args[0].startswith("-"):
        raise ValueError("Expected a Python module name after --")
    mutex = check(create_mutex(None, False, "Local\\customKF-" +
                              hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:20]))
    if C.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        close_handle(mutex)
        raise RuntimeError("Another customKF guarded experiment is running")
    # Campaign lease (M14), taken after the per-worker mutex and held for the worker's life; see
    # customkf/runtime/lease.py:guard_admission. Integrated 29 Sep 2026 as its own behaviour change.
    from .runtime.lease import GUARD_HEARTBEAT_S, guard_admission
    try:
        admission = guard_admission(module_args[0])
    except BaseException:
        close_handle(mutex)
        raise
    job = worker = monitor = None
    folder = ROOT / "runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    result = {"limits": asdict(limits), "module_args": module_args, "status": "setup_failed",
              "lease": {"kind": admission.kind, "lease_id": admission.lease_id}}
    started = time.monotonic()
    try:
        if usage_ceiling is not None:
            from .system_usage import UsageMonitor, usage_reason
            monitor = UsageMonitor()
            sample = monitor.sample()
            result['system_usage'] = dict(ceiling_percent=usage_ceiling, interval_s=.5,
                gpu_measure='busiest physical engine, summed across processes', start=sample,
                peak={k: sample[k] for k in ('cpu_percent','gpu_percent','ram_percent')}, samples=1)
            reason = usage_reason(sample, usage_ceiling)
            if reason:
                raise RuntimeError('Machine already at usage ceiling: '+reason)
        # The entire job cap is reserved in addition to the machine reserve. Since 2 Oct 2026 (user decision) the RAM
        # part of the usage ceiling no longer adds to this: memory is governed by the reserve alone.
        available = psutil.virtual_memory().available
        needed = limits.memory_mib * 2**20 + limits.reserve_gib * GIB
        if available < needed:
            raise RuntimeError(f"Insufficient memory headroom: {available/GIB:.2f} GiB available; {needed/GIB:.2f} required")
        folder.mkdir(parents=True)
        stop = folder / "STOP.json"
        env = os.environ.copy()
        env.update({key: str(limits.threads) for key in THREAD_ENV})
        env.update({"MKL_DYNAMIC": "FALSE", "OMP_DYNAMIC": "FALSE", "PYTHONDONTWRITEBYTECODE": "1",
                    "CUSTOMKF_RUN_DIR": str(folder), "CUSTOMKF_STOP_FILE": str(stop)})
        if usage_ceiling is not None:
            # Avoid numerical thread spin-waits competing on a small affinity set.
            env.update({'OMP_WAIT_POLICY':'PASSIVE','KMP_BLOCKTIME':'0'})
        cpus = psutil.Process().cpu_affinity()[:limits.threads]
        if len(cpus) != limits.threads:
            raise RuntimeError("Requested CPU affinity unavailable")
        job = Job(limits.memory_mib * 2**20, limits.cpu_percent, cpus)
        result.update({"enforced": True, "cpu_affinity": cpus, "memory_at_start_gib": available/GIB,
                       "cpu_rate_readback": job.cpu_limits().rate, "pid": None})
        with open(folder / "stdout.log", "wb") as out, open(folder / "stderr.log", "wb") as err, open(os.devnull, "rb") as inp:
            worker = Worker(job, [sys.executable, "-m", *module_args], env, ROOT, out, err, inp)
            result["pid"] = int(worker.info.pid)
            peak_rss = peak_private = 0
            minimum_available = available
            pressure_started = None
            parent_exit_seen = None
            last_usage = last_lease = time.monotonic()
            while True:
                now = time.monotonic()
                if admission.kind == "bare" and now-last_lease >= GUARD_HEARTBEAT_S:
                    admission.heartbeat()
                    last_lease = now
                available = psutil.virtual_memory().available
                minimum_available = min(minimum_available, available)
                if available < limits.reserve_gib * GIB and pressure_started is None:
                    pressure_started = now
                elif available >= limits.reserve_gib * GIB:
                    pressure_started = None
                action = pressure_action(available, limits, 0 if pressure_started is None else now-pressure_started)
                if action == "request_stop" and not stop.exists():
                    stop.write_text(json.dumps({"reason": "system_memory_pressure"}))
                code = worker.code()
                reason = None
                if monitor is not None and now-last_usage >= .5:
                    sample = monitor.sample(); last_usage = now
                    result['system_usage']['last'] = sample
                    result['system_usage']['samples'] += 1
                    for key in result['system_usage']['peak']:
                        result['system_usage']['peak'][key] = max(result['system_usage']['peak'][key],sample[key])
                    reason = usage_reason(sample, usage_ceiling)
                    if reason:
                        stop.write_text(json.dumps({'reason':reason, 'sample':sample}))
                if reason is not None:
                    pass
                elif action == "terminate":
                    reason = "memory_pressure"
                elif now-started >= limits.timeout_s:
                    reason = "timeout"
                elif scratch_bytes(folder) > limits.scratch_mib*2**20:
                    reason = "scratch_limit"
                if reason:
                    job.terminate(124 if reason == "timeout" else 125)
                    result.update(status=reason, exit_code=124 if reason == "timeout" else 125)
                    break
                if code is not None:
                    # A completed parent is never allowed to leave running descendants.
                    active = job.accounting().active
                    # Process signalling can precede the job's active-count update.
                    # Allow a bounded accounting drain; the watchdog remains active.
                    if active and parent_exit_seen is None:
                        parent_exit_seen = now
                    if active and now-parent_exit_seen < .2:
                        time.sleep(.01)
                        continue
                    job.terminate(125)
                    result.update(status="ok" if code == 0 and active == 0 else
                                  ("orphan_children" if code == 0 else "worker_failed"),
                                  exit_code=code if code else (125 if active else 0))
                    break
                try:
                    parent = psutil.Process(worker.info.pid)
                    members = [parent, *parent.children(recursive=True)]
                    memories = [p.memory_info() for p in members]
                    peak_rss = max(peak_rss, sum(m.rss for m in memories))
                    peak_private = max(peak_private, sum(m.private for m in memories))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                time.sleep(0.1)
            acc, actual = job.accounting(), job.limits()
            result.update({"elapsed_s": time.monotonic()-started,
                           "cpu_seconds": (acc.user+acc.kernel)/1e7,
                           # Windows can count a denied allocation in this raw peak.
                           "windows_peak_job_memory_mib": actual.peak_job_memory/2**20,
                           "peak_sampled_private_commit_mib": peak_private/2**20,
                           "peak_sampled_rss_mib": peak_rss/2**20,
                           "minimum_system_available_gib": minimum_available/GIB})
    except BaseException as exc:
        result.update(error=f"{type(exc).__name__}: {exc}", exit_code=126,
                      status="controller_failed" if worker else "setup_failed")
        if isinstance(exc, KeyboardInterrupt):
            result["status"] = "interrupted"
    finally:
        if job:
            job.close()  # KILL_ON_JOB_CLOSE applies on every failure/interrupt path.
        if worker:
            worker.close()
        if monitor:
            monitor.close()
        try:
            released = admission.release()
            result["lease"]["released"] = released
            if released is False:      # documented meaning: the admission was already absent or replaced
                result["lease"]["release_note"] = "admission already absent at release; nothing was held"
        except BaseException as exc:
            # Never mask the worker's own result, but an unresolved cleanup is not a successful worker boundary
            # (Sol review SOL-07): keep the worker outcome separately and report the boundary as failed. The lease
            # stays held (fail closed); it is not force-removed.
            result["lease"]["release_error"] = f"{type(exc).__name__}: {exc}"
            result["worker_status"] = result.get("status")
            result["status"] = "cleanup_failed"
            if not result.get("exit_code"):
                result["exit_code"] = 126
        close_handle(mutex)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "result.json").write_text(json.dumps(result, indent=2))
    return result, folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('legacy','usage75'), default='legacy')
    parser.add_argument("--memory-mib", type=int)
    parser.add_argument("--cpu-percent", type=float)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("module", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    module = args.module[1:] if args.module[:1] == ["--"] else args.module
    try:
        defaults = (4096,15,2) if args.profile == 'usage75' else (2048,10,1)
        result, folder = run(module, Limits(memory_mib=args.memory_mib if args.memory_mib is not None else defaults[0],
                                           cpu_percent=args.cpu_percent if args.cpu_percent is not None else defaults[1],
                                           threads=args.threads if args.threads is not None else defaults[2], timeout_s=args.timeout),
                             usage_ceiling=75 if args.profile == 'usage75' else None)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 126
    print(json.dumps(result, indent=2))
    print(f"Logs: {folder}")
    if (folder / "stdout.log").exists():
        print((folder / "stdout.log").read_text(errors="replace")[-16000:])
    if (folder / "stderr.log").exists():
        print((folder / "stderr.log").read_text(errors="replace")[-8000:], file=sys.stderr)
    return result["exit_code"] if result["exit_code"] <= 255 else 1


if __name__ == "__main__":
    sys.exit(main())
