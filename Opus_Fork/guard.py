"""Opus_Fork guard: Astra's guard with a higher, user-authorized resource profile.

    python -m Opus_Fork.guard --profile fork8 --timeout 600 -- Opus_Fork.MODULE ARGS

Forked from `customkf/guard.py` (SHA-256 recorded in `FORKED_FROM` below) because
`customkf.guard.Limits.validate()` refuses anything above 4 GiB / 15% / 2 threads, and on
19 September 2026 the user authorized ~8 threads / 50% for this fork. Astra's guard and
both of its profiles are untouched, so her runs keep the tested policy exactly.

What is deliberately preserved from the original:

- **The same named mutex.** It is derived from the repository root, so this guard and
  Astra's still refuse to run at the same time. One guarded job per workspace, always.
- The 75% total-machine CPU/GPU/RAM stop threshold and its fail-closed telemetry (GPU
  readings and GPU telemetry gaps count after `GPU_SUSTAIN_S` since items 6-7 below).
- The rule that the full job cap is reserved *in addition* to machine headroom. The reserve
  and emergency thresholds were 8 and 6 GiB until 2 Oct 2026, when the user lowered them to
  2 and 1 GiB and took RAM out of the 75% usage ceiling (CPU and GPU keep it): a job now
  needs its cap + 2 GiB free to start (6 GiB at the 4 GiB cap).
- Windows Job Object enforcement: kill-on-close, aggregate private commit, below-normal
  priority, CPU affinity and rate control, verified by read-back.
- `CUSTOMKF_RUN_DIR` / `CUSTOMKF_STOP_FILE`, so workers written for either guard run
  under both, and the scratch-size and timeout watchdogs.

What changed, and why:

1. `Limits.validate()` admits up to 6 GiB, 60%, 12 threads and 12 processes. The legacy
   and usage75 profiles keep their original numbers, so selecting them here behaves as
   before.
2. New `fork8` profile: **4 GiB, 50% machine CPU, 1 numerical thread per process, 8 processes, 512 MiB scratch**
   (`fork8t` is the 8-thread variant; the ~8 threads authorized are used as eight single-threaded processes — corrected
   28 Sep 2026, Astra review N06; `Limits.validate`'s wider bounds are a validator range, not an authorization).
   Memory stays at Astra's 4 GiB because it was never the binding constraint (the
   25-station 24 h fit peaked at 503 MiB) and because raising it would break admission:
   the 75% ceiling already reserves 7.9 GiB on this 31.8 GiB machine, so a larger cap
   would be refused for lack of headroom rather than enforced.
3. `processes` is now a limit in its own right. The original hardcoded a 4-process job so
   a worker could not leave descendants running. The streaming solve folds independent
   epoch chunks into `R, z` by Householder updates, and that fold is associative, so
   chunks can be computed in parallel and combined. Fanning out inside one job is the
   only way to use more cores here: the dominant cost is per-row Python in
   `dynamic_observation.link_jacobian`, not BLAS, so extra *threads* alone buy little
   (`RESOURCE_POLICY_20260917.md` measured 1 thread beating 2 by 12x on the real-Jacobian
   workload). The job-wide affinity mask still caps total consumption either way.
4. Run folders are created under `Opus_Fork/runs/` instead of `runs/`, so nothing this
   fork does changes which folder is newest in Astra's `runs/`.
5. (25 September 2026, user-approved.) CPUs are spread over physical cores. Windows numbers
   the two hyperthreads of a P-core next to each other (0+1, 2+3 ... on this i7-13700F), so
   taking the first N logical CPUs put fork8's eight workers on four physical cores.
   `spread_cpus` now takes one logical CPU per physical core, fastest cores first, before any
   second hyperthread: fork8 gets CPUs 0,2,...,14. The CPU count, rate cap, memory and
   process limits are unchanged, so the budget is the same.
6. (25 September 2026, user-approved.) The GPU stop needs `GPU_SUSTAIN_S` of continuous
   readings at or above the ceiling instead of one 0.5 s reading, at launch and while
   running. The estimator puts no load on the GPU, so a brief spike from another program is
   no reason to kill a worker; sustained load (a game) still stops it within that time. CPU
   and RAM still act on a single reading, because this job adds to both.
7. (25 September 2026, user-approved.) A GPU telemetry error is treated like a high GPU
   reading: it stops the worker only if GPU telemetry stays unavailable for `GPU_SUSTAIN_S`.
   Transient PDH errors (0xc0000bba, seen three times from 23 to 25 September while other
   programs started or stopped) each killed a worker. During a gap CPU and RAM are read
   directly from psutil and still stop the job on a single reading. Telemetry that stays
   lost still fails closed, with the same error text as before, so chain scripts that
   recognize telemetry stops behave as before.

Not changed to make a run proceed: the 75% ceiling, the memory reserves, the mutex, or
the read-back verification. A refusal is a refusal.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import uuid

import psutil

# Astra's OS plumbing and telemetry are imported unchanged, not copied: they carry no
# policy, only Windows Job Object and PDH access.
from customkf.winjob import Job, Worker, create_mutex, close_handle, check, C
from customkf.guard import GIB, THREAD_ENV, pressure_action, scratch_bytes
from customkf.system_usage import usage_reason
from customkf.runtime import processes

# Exact state of Astra's originals when this fork was taken, 19 September 2026.
# `customkf/guard.py` was copied and edited; the other two are imported unchanged.
FORKED_FROM = {
    "customkf/guard.py": "157dbca8aaab380b45e6d96fd9ee38bbc1314bc1fcfafc5862bb4d38a2f5235a",
    "customkf/winjob.py": "5cd23fdae77e115dd2cf96ea1ba83878ab6b61f7e52f2d1730534861fcf8c6fd",
    "customkf/system_usage.py": "a8c22adf8a9d7198eb602fcfa36fee9816395f54ffb1cea5d58626cf6dc11ea2",
}

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT/"Opus_Fork"/"runs"

# GPU readings must stay at or above the ceiling, or unavailable, this long before they stop a
# worker (items 6 and 7).
GPU_SUSTAIN_S = 10
USAGE_KEYS = ("cpu_percent", "gpu_percent", "ram_percent")

PROFILES = {
    # name: (memory_mib, cpu_percent, threads, processes, scratch_mib)
    "legacy": (2048, 10, 1, 4, 128),
    "usage75": (4096, 15, 2, 4, 128),
    # fork8 keeps numerical threads at 1 on purpose: the estimator's cost is per-row Python
    # in `dynamic_observation.link_jacobian`, and threading it measurably hurts. The eight
    # cores are for eight single-threaded worker processes (eight physical cores since item 5).
    "fork8": (4096, 50, 1, 8, 512),
    "fork8t": (4096, 50, 8, 8, 512),   # BLAS-bound work (dense QR, covariance) instead
}


@dataclass(frozen=True)
class Limits:
    memory_mib: int = 4096
    cpu_percent: float = 50
    threads: int = 8
    processes: int = 8
    timeout_s: float = 600
    reserve_gib: float = 2      # user decision 2 Oct 2026 (was 8)
    emergency_gib: float = 1    # user decision 2 Oct 2026 (was 6)
    grace_s: float = 3
    scratch_mib: int = 512

    def validate(self):
        if (not all(math.isfinite(float(x)) for x in asdict(self).values())
                or not 64 <= self.memory_mib <= 6144
                or not 0 < self.cpu_percent <= 60
                or not 1 <= self.threads <= 12
                or not 1 <= self.processes <= 12
                or not 0 < self.timeout_s <= 7200
                or self.reserve_gib < 2 or self.emergency_gib < 1
                or self.emergency_gib >= self.reserve_gib
                or not 0 <= self.grace_s <= 5 or not 1 <= self.scratch_mib <= 2048):
            raise ValueError("Limits outside the authorized fork policy (max 6 GiB /60% /12 threads)")


class ForkJob(Job):
    """Astra's Job with the process count taken from the limits instead of hardcoded 4."""

    def __init__(self, memory_bytes, cpu_percent, cpus, processes):
        from customkf.winjob import ExtendedLimits, CpuLimits, create_job, set_info
        self.handle = check(create_job(None, None))
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000 | 0x200 | 0x20 | 0x10 | 0x8
            limits.basic.priority = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS
            limits.basic.affinity = sum(1 << cpu for cpu in cpus)
            limits.basic.active_limit = processes
            limits.job_memory = memory_bytes
            check(set_info(self.handle, 9, C.byref(limits), C.sizeof(limits)))
            cpu = CpuLimits(0x1 | 0x4, round(cpu_percent*100))
            check(set_info(self.handle, 15, C.byref(cpu), C.sizeof(cpu)))
            actual, actual_cpu = self.limits(), self.cpu_limits()
            if (actual.basic.flags & limits.basic.flags != limits.basic.flags
                    or actual.job_memory != memory_bytes
                    or actual.basic.affinity != limits.basic.affinity
                    or actual.basic.priority != limits.basic.priority
                    or actual.basic.active_limit != processes
                    or actual_cpu.flags != cpu.flags or actual_cpu.rate != cpu.rate):
                raise RuntimeError("Windows did not retain the requested resource limits")
        except BaseException:
            self.close()
            raise


def other_python_processes(allowed=()):
    """Other guard or campaign-controller Python processes of this project (narrowed 3 Oct 2026, user decision).

    Until then any Python process counted. See customkf/runtime/processes.py for what is and is not counted.
    """
    return processes.campaign_processes(exclude=allowed)


def physical_cores():
    """[(efficiency_class, logical CPUs)] per physical core, from GetLogicalProcessorInformationEx.

    Only processor group 0 is read; psutil affinity lists cover the same group.
    """
    query = C.WinDLL("kernel32", use_last_error=True).GetLogicalProcessorInformationEx
    query.argtypes, query.restype = [C.c_int, C.c_void_p, C.POINTER(C.c_uint32)], C.c_int
    size = C.c_uint32(0)
    query(0, None, C.byref(size))  # RelationProcessorCore; this call only reports the size
    if not size.value:
        raise C.WinError(C.get_last_error())
    buffer = C.create_string_buffer(size.value)
    check(query(0, buffer, C.byref(size)))
    raw, cores, offset = buffer.raw[:size.value], [], 0
    while offset < len(raw):
        # SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX + PROCESSOR_RELATIONSHIP (x64 layout)
        kind, length = struct.unpack_from("<II", raw, offset)
        efficiency, groups = raw[offset+9], struct.unpack_from("<H", raw, offset+30)[0]
        if kind != 0 or length < 32+16*groups or offset+length > len(raw):
            raise RuntimeError("Unexpected processor topology record")
        cpus = []
        for g in range(groups):
            mask, group = struct.unpack_from("<QH", raw, offset+32+16*g)
            if group == 0:
                cpus += [i for i in range(64) if mask >> i & 1]
        if cpus:
            cores.append((efficiency, cpus))
        offset += length
    return cores


def spread_cpus(available, cores):
    """Order `available` so the first N logical CPUs sit on N different physical cores (item 5).

    Highest efficiency class first (P-cores on a hybrid Intel chip), then lowest CPU number;
    second hyperthreads only after every core has one. Fails closed on incomplete topology.
    """
    allowed = set(available)
    ranked = sorted((-efficiency, min(cpus), [c for c in sorted(cpus) if c in allowed])
                    for efficiency, cpus in cores)
    lists = [cpus for _, _, cpus in ranked if cpus]
    order = [cpus[i] for i in range(max(map(len, lists), default=0)) for cpus in lists if i < len(cpus)]
    if len(order) != len(allowed) or set(order) != allowed:
        raise RuntimeError("Processor topology does not match the allowed CPUs")
    return order


def read_usage(monitor):
    """`monitor.sample()`; on a GPU telemetry error, CPU and RAM alone with `gpu_percent` None (item 7)."""
    try:
        return monitor.sample()
    except (OSError, RuntimeError) as exc:  # every error UsageMonitor.sample raises comes from GPU telemetry
        memory = psutil.virtual_memory()
        return dict(cpu_percent=psutil.cpu_percent(None), gpu_percent=None, gpu_error=f"{type(exc).__name__}: {exc}",
                    ram_percent=100*(1-memory.available/memory.total), available_bytes=memory.available,
                    total_bytes=memory.total)


def usage_check(sample, ceiling, gpu_high_since, now):
    """`usage_reason`, except GPU only counts after GPU_SUSTAIN_S of continuous readings at or
    above the ceiling or without telemetry (items 6 and 7).

    Returns (reason, gpu_high_since). Readings are still validated; telemetry that stays lost
    raises, failing closed.
    """
    gpu = sample["gpu_percent"]
    reason = usage_reason(dict(sample, gpu_percent=0.), ceiling)  # CPU: one reading (RAM: reserve only)
    if gpu is not None and usage_reason(dict(sample, cpu_percent=0., ram_percent=0.), ceiling) is None:
        return reason, None
    since = now if gpu_high_since is None else gpu_high_since
    if reason is None and now-since >= GPU_SUSTAIN_S:
        if gpu is None:
            raise RuntimeError(f"GPU telemetry unavailable for {now-since:.1f} s: {sample['gpu_error']}")
        reason = "gpu_usage_limit"
    return reason, since


def record(usage, sample):
    usage["last"] = sample
    usage["samples"] += 1
    usage["gpu_telemetry_gaps"] += sample["gpu_percent"] is None
    for key in USAGE_KEYS:
        if sample[key] is not None:
            usage["peak"][key] = max(usage["peak"].get(key, sample[key]), sample[key])


def run(module_args, limits=Limits(), *, usage_ceiling=75, label=None, ignore_other_python=False):
    limits.validate()
    if usage_ceiling is not None and (not math.isfinite(usage_ceiling) or not 0 < usage_ceiling <= 75):
        raise ValueError("Machine usage ceiling must be positive and at most 75 percent")
    if not module_args or module_args[0].startswith("-"):
        raise ValueError("Expected a Python module name after --")
    # The mutex alone is NOT enough, and on 20 September 2026 that cost Astra a campaign.
    # It is held only for the duration of one worker, so a serial controller releases it
    # between workers. A single guarded job started in that gap takes the mutex, the
    # controller's next worker is refused, and the whole campaign aborts. That is exactly
    # what happened to `claude.experiments.cross_date_fits.run` at lin2-chunk-054-072.
    # Astra's controllers protect themselves by refusing to start when any other Python
    # process exists; a bare guard invocation had no such check. It does now.
    # Narrowed on 3 Oct 2026 (user decision) to this project's guard and campaign-controller
    # processes; other Python is governed by the hardware rules. The message keeps its
    # opening words, which the chain scripts match as an external stop.
    if not ignore_other_python:
        others = other_python_processes()
        if others:
            raise RuntimeError(
                "Another Python process is running this project's guard or a campaign "
                "controller (pid "+", ".join(map(str, others))+"). "
                "It may be a controller between workers, whose next worker this job would "
                "refuse. Inspect it before running; pass ignore_other_python only when you "
                "have confirmed it is not a campaign.")
    # Identical mutex name to customkf.guard: the fork must never run beside Astra.
    mutex = check(create_mutex(None, False, "Local\\customKF-" +
                              hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:20]))
    if C.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        close_handle(mutex)
        raise RuntimeError("Another customKF guarded experiment is running")
    # Campaign lease (M14), taken after the per-worker mutex and held for the worker's life; see
    # customkf/runtime/lease.py:guard_admission. Integrated 29 Sep 2026 as its own behaviour change.
    from customkf.runtime.lease import GUARD_HEARTBEAT_S, guard_admission
    try:
        admission = guard_admission(module_args[0])
    except BaseException:
        close_handle(mutex)
        raise
    job = worker = monitor = gpu_high_since = None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = RUNS/(stamp+"-"+(label or uuid.uuid4().hex[:8]))
    result = {"guard": "Opus_Fork", "forked_from": FORKED_FROM, "limits": asdict(limits),
              "module_args": module_args, "status": "setup_failed",
              "lease": {"kind": admission.kind, "lease_id": admission.lease_id}}
    started = time.monotonic()
    try:
        if usage_ceiling is not None:
            from customkf.system_usage import UsageMonitor
            monitor = UsageMonitor()
            sample = read_usage(monitor)
            result["system_usage"] = dict(ceiling_percent=usage_ceiling, interval_s=.5,
                gpu_measure="busiest physical engine, summed across processes", gpu_sustain_s=GPU_SUSTAIN_S,
                start=sample, peak={}, samples=0, gpu_telemetry_gaps=0)
            record(result["system_usage"], sample)
            reason, gpu_high_since = usage_check(sample, usage_ceiling, None, time.monotonic())
            while reason is None and gpu_high_since is not None:
                # A GPU spike or telemetry gap at launch is waited out for up to GPU_SUSTAIN_S.
                time.sleep(.5)
                sample = read_usage(monitor)
                record(result["system_usage"], sample)
                reason, gpu_high_since = usage_check(sample, usage_ceiling, gpu_high_since, time.monotonic())
            if reason:
                raise RuntimeError("Machine already at usage ceiling: "+reason)
        # Job cap + machine reserve; the RAM part of the usage ceiling no longer adds (user decision, 2 Oct 2026).
        available = psutil.virtual_memory().available
        needed = limits.memory_mib*2**20 + limits.reserve_gib*GIB
        if available < needed:
            raise RuntimeError(f"Insufficient memory headroom: {available/GIB:.2f} GiB available; {needed/GIB:.2f} required")
        folder.mkdir(parents=True)
        stop = folder/"STOP.json"
        env = os.environ.copy()
        env.update({key: str(limits.threads) for key in THREAD_ENV})
        env.update({"MKL_DYNAMIC": "FALSE", "OMP_DYNAMIC": "FALSE", "PYTHONDONTWRITEBYTECODE": "1",
                    "CUSTOMKF_RUN_DIR": str(folder), "CUSTOMKF_STOP_FILE": str(stop),
                    "OPUSFORK_PROCESSES": str(limits.processes),
                    "OPUSFORK_THREADS": str(limits.threads)})
        if usage_ceiling is not None:
            env.update({"OMP_WAIT_POLICY": "PASSIVE", "KMP_BLOCKTIME": "0"})
        # Affinity is sized by whichever of threads/processes needs more cores. The original
        # tied it to `threads`, which is right when one process uses N library threads, but
        # this workload is per-row Python: `RESOURCE_POLICY_20260917.md` measured one thread
        # beating two by 12x on the real-Jacobian load. Parallelism here means several
        # single-threaded worker processes, so the job needs one core per process, and since
        # 25 September each of those is on a different physical core where possible (item 5).
        wanted = max(limits.threads, limits.processes)
        cpus = sorted(spread_cpus(psutil.Process().cpu_affinity(), physical_cores())[:wanted])
        if len(cpus) != wanted:
            raise RuntimeError("Requested CPU affinity unavailable")
        job = ForkJob(limits.memory_mib*2**20, limits.cpu_percent, cpus, limits.processes)
        result.update({"enforced": True, "cpu_affinity": cpus, "memory_at_start_gib": available/GIB,
                       "cpu_rate_readback": job.cpu_limits().rate, "pid": None})
        with open(folder/"stdout.log", "wb") as out, open(folder/"stderr.log", "wb") as err, open(os.devnull, "rb") as inp:
            worker = Worker(job, [sys.executable, "-m", *module_args], env, ROOT, out, err, inp)
            result["pid"] = int(worker.info.pid)
            peak_rss = peak_private = 0
            minimum_available = available
            pressure_started = None
            parent_exit_seen = None
            last_usage = time.monotonic()
            last_lease = time.monotonic()
            while True:
                now = time.monotonic()
                if admission.kind == "bare" and now-last_lease >= GUARD_HEARTBEAT_S:
                    admission.heartbeat()
                    last_lease = now
                available = psutil.virtual_memory().available
                minimum_available = min(minimum_available, available)
                if available < limits.reserve_gib*GIB and pressure_started is None:
                    pressure_started = now
                elif available >= limits.reserve_gib*GIB:
                    pressure_started = None
                action = pressure_action(available, limits, 0 if pressure_started is None else now-pressure_started)
                if action == "request_stop" and not stop.exists():
                    stop.write_text(json.dumps({"reason": "system_memory_pressure"}))
                code = worker.code()
                reason = None
                if monitor is not None and now-last_usage >= .5:
                    sample = read_usage(monitor)
                    last_usage = now
                    record(result["system_usage"], sample)
                    reason, gpu_high_since = usage_check(sample, usage_ceiling, gpu_high_since, now)
                    if reason:
                        stop.write_text(json.dumps({"reason": reason, "sample": sample}))
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
                    active = job.accounting().active
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
            job.close()
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
        (folder/"result.json").write_text(json.dumps(result, indent=2))
    return result, folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="fork8")
    parser.add_argument("--memory-mib", type=int)
    parser.add_argument("--cpu-percent", type=float)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--processes", type=int)
    parser.add_argument("--scratch-mib", type=int)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--label", help="folder suffix under Opus_Fork/runs/")
    parser.add_argument("--ignore-other-python", action="store_true",
                        help="only after confirming no controller is mid-campaign")
    parser.add_argument("module", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    module = args.module[1:] if args.module[:1] == ["--"] else args.module
    memory, cpu, threads, processes, scratch = PROFILES[args.profile]
    try:
        limits = Limits(memory_mib=args.memory_mib if args.memory_mib is not None else memory,
                        cpu_percent=args.cpu_percent if args.cpu_percent is not None else cpu,
                        threads=args.threads if args.threads is not None else threads,
                        processes=args.processes if args.processes is not None else processes,
                        scratch_mib=args.scratch_mib if args.scratch_mib is not None else scratch,
                        timeout_s=args.timeout)
        result, folder = run(module, limits, usage_ceiling=75, label=args.label,
                             ignore_other_python=args.ignore_other_python)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 126
    print(json.dumps(result, indent=2))
    print(f"Logs: {folder}")
    if (folder/"stdout.log").exists():
        print((folder/"stdout.log").read_text(errors="replace")[-16000:])
    if (folder/"stderr.log").exists():
        print((folder/"stderr.log").read_text(errors="replace")[-8000:], file=sys.stderr)
    return result["exit_code"] if result["exit_code"] <= 255 else 1


if __name__ == "__main__":
    sys.exit(main())
