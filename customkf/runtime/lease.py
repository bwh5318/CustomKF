"""Campaign lease, version 2: one serial campaign owns the machine across worker gaps and back-off (review M14).

Version 1 (commit 961c414) was reviewed at checkpoint A (Astra, A02) and had four defects. This version repairs them:

1. **Every transition is serialized.** acquire, renew, release, stale recovery and worker admission all run under one
   Windows named mutex. The OS hands an abandoned mutex to the next waiter if its holder dies, so there is no stale
   lock file to clean up, and a check can never be separated from the write it justifies. Transitions are not
   re-entrant: a nested transition in the same thread raises rather than silently interleaving.
2. **Admission is a reservation, not a pre-check.** A guard calls `admit_worker()` once and holds the returned
   `Admission` for the worker's whole life.
   - With no lease on the machine, it takes a *bare* lease itself, so a campaign cannot start under it.
   - With a live campaign lease, only a worker carrying that lease's id (`CUSTOMKF_CAMPAIGN_LEASE`) is admitted, and
     it is registered as a child of the campaign.
   - Otherwise it is refused.
3. **An owner that cannot be inspected is not dead.** Process identity is three-valued: alive, dead or unknown. Only
   "no such process", an exit code, or a different creation time (pid reuse) means dead. Access denied and failed
   queries mean unknown, and such a lease stays held.
4. **One coordination identity per machine, not per checkout.**
   - The lease directory defaults to `%ProgramData%/customKF/coordination`, overridable with an absolute
     `CUSTOMKF_COORDINATION_DIR`. Not AppData: packaged apps virtualize it (29 Sep 2026).
   - The mutex name derives from that directory.
   - The main workspace and any replay root therefore share one lease.

A lease is recoverable (`stale`) only if all three hold:
- its heartbeat is older than its ttl;
- its owner is dead;
- every registered child is dead.

A dead owner with surviving workers is `orphaned` and held. Recovery keeps the old record beside the new one as
`campaign_lease.stale-<id>.json`. A lease file that cannot be read is held; inspect it, then remove it by hand.

Not wired into customkf.guard / Opus_Fork.guard. Integration is a separate, reviewed behaviour change
(docs/consolidation/M10_M14_FIXES.md).
"""
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time
import uuid

ENV = "CUSTOMKF_CAMPAIGN_LEASE"
DIR_ENV = "CUSTOMKF_COORDINATION_DIR"
NAME = "campaign_lease.json"
DEFAULT_TTL_S = 900.
LOCK_TIMEOUT_S = 10.
STILL_ACTIVE, ERROR_INVALID_PARAMETER = 259, 87


class LeaseHeld(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    pass


def canonical(directory):
    """The one accepted form of a coordination directory: absolute and resolved (addendum review AA02).

    A relative path would resolve against each process's working directory, so a workspace and a replay root, or a
    controller and a child started elsewhere, would each get their own lease and mutex.
    """
    path = Path(directory)
    if not path.is_absolute():
        raise ValueError(f"Coordination directory must be an absolute path, not {str(directory)!r}")
    resolved = path.resolve()
    appdata = [Path(os.environ[k]).resolve() for k in ("LOCALAPPDATA", "APPDATA") if os.environ.get(k)]
    temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or resolved).resolve()   # not virtualized (measured)
    parts = [p.lower() for p in resolved.parts]
    under_appdata = any(resolved == a or a in resolved.parents for a in appdata)
    if (under_appdata and not (resolved == temp or temp in resolved.parents)) or ("packages" in parts and "localcache" in parts):
        # Packaged (MSIX) apps silently redirect AppData writes to a per-package copy: a lease written from one app
        # would be invisible to processes started from another (measured 29 Sep 2026 from the Claude desktop app).
        raise ValueError(f"Coordination directory must not be under AppData (virtualized per packaged app): {resolved}")
    return resolved


def default_directory():
    """%ProgramData%/customKF/coordination unless CUSTOMKF_COORDINATION_DIR names another absolute directory.

    Not %LOCALAPPDATA%: from a packaged app such as the Claude desktop app, writes there are redirected to the app's
    private copy (a marker written there was invisible to a process started outside the app, 29 Sep 2026).
    ProgramData, and named kernel mutexes, are shared across that boundary.
    """
    configured = os.environ.get(DIR_ENV)
    if configured:
        return canonical(configured)
    return canonical(Path(os.environ.get("PROGRAMDATA") or "C:/ProgramData")/"customKF"/"coordination")


def _kernel():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    return k


def process_identity(pid):
    """("alive", creation FILETIME) | ("dead", None) | ("unknown", None) for a Windows pid.

    A process that exited with code 259 (STILL_ACTIVE) would read as alive; that exit code is reserved by convention.
    """
    k = _kernel()
    handle = k.OpenProcess(0x1000, False, int(pid))    # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ("dead", None) if ctypes.get_last_error() == ERROR_INVALID_PARAMETER else ("unknown", None)
    try:
        code = ctypes.c_ulong()
        if not k.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
            return "unknown", None
        if code.value != STILL_ACTIVE:
            return "dead", None
        times = [ctypes.c_ulonglong() for _ in range(4)]
        if not k.GetProcessTimes(ctypes.c_void_p(handle), *map(ctypes.byref, times)):
            return "unknown", None
        return "alive", times[0].value
    finally:
        k.CloseHandle(ctypes.c_void_p(handle))


def liveness(pid, created):
    """alive / dead / unknown for a recorded (pid, creation time); a different creation time means pid reuse: dead."""
    status, now_created = process_identity(pid)
    if status == "alive" and now_created != created:
        return "dead"
    return status


_local = threading.local()


@contextlib.contextmanager
def transition(directory):
    """Serialize a lease transition machine-wide (per coordination directory). Not re-entrant."""
    if getattr(_local, "depth", 0):
        raise RuntimeError("Nested lease transition refused (a check must not be separated from its write)")
    k = _kernel()
    name = "Local\\customKF-coordination-"+hashlib.sha256(str(canonical(directory)).lower().encode()).hexdigest()[:24]
    handle = k.CreateMutexW(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    try:
        result = k.WaitForSingleObject(ctypes.c_void_p(handle), int(LOCK_TIMEOUT_S*1000)) & 0xFFFFFFFF
        if result not in (0, 0x80):                    # WAIT_OBJECT_0, WAIT_ABANDONED (a holder died: the OS hands it on)
            raise LeaseHeld(f"Coordination lock busy for {LOCK_TIMEOUT_S:.0f} s (wait result {result:#x})")
        _local.depth = 1
        try:
            yield canonical(directory)
        finally:
            _local.depth = 0
            k.ReleaseMutex(ctypes.c_void_p(handle))
    finally:
        k.CloseHandle(ctypes.c_void_p(handle))


def _patient(operation, *args, seconds=2.):
    """Retry through transient Windows sharing violations (a concurrent reader holding the file open)."""
    end = time.monotonic()+seconds
    while True:
        try:
            return operation(*args)
        except PermissionError:
            if time.monotonic() > end:
                raise
            time.sleep(0.005)


def _read_shared(path):
    """Read a file opened with FILE_SHARE_READ|WRITE|DELETE, so a reader never blocks the owner's atomic replace.

    Python's open() omits FILE_SHARE_DELETE, and then a tight loop of readers can starve os.replace indefinitely.
    """
    import msvcrt
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                              ctypes.c_uint32, ctypes.c_void_p)
    handle = k.CreateFileW(str(path), 0x80000000, 0x7, None, 3, 0x80, None)   # GENERIC_READ, share all, OPEN_EXISTING
    if handle is None or handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        if error in (2, 3):                                # file / path not found
            raise FileNotFoundError(error, "No lease file", str(path))
        raise PermissionError(error, "Lease file not readable", str(path))
    with os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY), "r") as stream:
        return stream.read()


def read(directory=None):
    """The lease record, None when there is none, or {"unreadable": text}. Read-only; takes no lock."""
    path = (canonical(directory) if directory else default_directory())/NAME
    try:
        text = _patient(_read_shared, path)
    except FileNotFoundError:
        return None
    except PermissionError:
        return {"unreadable": "sharing violation persisted for 2 s"}
    try:
        record = json.loads(text)
        if not isinstance(record, dict) or "lease_id" not in record:
            raise ValueError
        return record
    except ValueError:
        return {"unreadable": text[:200]}


def _write(directory, record):
    """Atomic replace: readers see the old or the new record, never a partial one. Call only inside transition()."""
    path = Path(directory)/NAME
    temporary = path.with_name(f"{NAME}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(record, indent=1))
    _patient(os.replace, temporary, path)


def _live_children(record):
    """Registered workers that are alive or cannot be inspected (unknown counts as alive)."""
    return [c for c in record.get("children", []) if liveness(c["pid"], c.get("created")) != "dead"]


def state(record, clock=time.time):
    """free | live | closing | overdue | unverifiable | orphaned | stale | unreadable.

    Only `free` and `stale` admit a new owner. `closing`: the controller released the lease while registered workers
    were still alive or uninspectable (addendum review AA01); it is held until they have all exited.
    """
    if record is None:
        return "free"
    if "unreadable" in record:
        return "unreadable"
    if record.get("closing"):
        return "closing" if _live_children(record) else "stale"
    if clock()-float(record["heartbeat"]) <= float(record["ttl_s"]):
        return "live"
    owner = liveness(record["owner_pid"], record.get("owner_created"))
    if owner != "dead":
        return "overdue" if owner == "alive" else "unverifiable"
    return "orphaned" if _live_children(record) else "stale"


def describe(record, status, clock=time.time):
    if status == "unreadable":
        return f"A campaign lease file exists but cannot be read (inspect, then remove by hand): {record['unreadable']!r}"
    return (f"The machine is held [{status}] by {record.get('kind', 'campaign')} lease {record['campaign']!r} "
            f"({record['owner']}, pid {record['owner_pid']}, {len(record.get('children', []))} registered workers), "
            f"heartbeat {clock()-float(record['heartbeat']):.0f} s ago")


def check(directory=None, clock=time.time):
    """Status for display only. It reserves nothing; guards must use admit_worker()."""
    record = read(directory)
    return state(record, clock), record


def _new_record(kind, campaign, owner, pid, ttl_s, clock):
    status, created = process_identity(pid)
    if status != "alive":
        raise ValueError(f"Lease owner pid {pid} is not an inspectable running process ({status})")
    return dict(version=2, kind=kind, lease_id=uuid.uuid4().hex, campaign=str(campaign), owner=str(owner),
                owner_pid=int(pid), owner_created=created, host=socket.gethostname(), created=clock(),
                heartbeat=clock(), ttl_s=float(ttl_s), children=[])


def _take(directory, record, clock):
    """Inside transition(): install `record` if the machine is free, or recover a stale lease first; else LeaseHeld."""
    current = read(directory)
    status = state(current, clock)
    if status == "stale":
        _patient(os.replace, Path(directory)/NAME, Path(directory)/f"campaign_lease.stale-{current['lease_id']}.json")
    elif status != "free":
        raise LeaseHeld(describe(current, status, clock))
    _write(directory, record)


class Lease:
    def __init__(self, directory, record, clock):
        self.directory, self.record, self.clock = canonical(directory), record, clock

    @property
    def id(self):
        return self.record["lease_id"]

    def child_environment(self, environ=None):
        """Environment for an authorized worker of this campaign (the guard registers it via admit_worker)."""
        return {**(os.environ if environ is None else environ), ENV: self.id, DIR_ENV: str(self.directory)}

    def heartbeat(self):
        with transition(self.directory):
            current = read(self.directory)
            if not current or current.get("lease_id") != self.id:
                raise LeaseLost(f"Lease {self.id} is no longer held: {current}")
            current["heartbeat"] = self.clock()
            _write(self.directory, current)
            self.record = current

    def release(self):
        """Give the machine back: "released", "closing", or False when this lease is not held.

        With registered workers still alive or uninspectable the lease enters `closing` instead of disappearing
        (addendum review AA01): no new worker is admitted, nothing else can acquire, and the last departing worker
        removes the record. A controller's error or cancellation path should terminate its workers (the guard's job
        object does so when the guard exits) and then use drain().
        """
        with transition(self.directory):
            current = read(self.directory)
            if not current or current.get("lease_id") != self.id:
                return False
            if _live_children(current):
                current["closing"] = self.clock()
                _write(self.directory, current)
                return "closing"
            _patient((self.directory/NAME).unlink)
            return "released"

    def drain(self, timeout_s=600., poll_s=1.):
        """release(), then keep finishing it until every registered worker has exited or timeout_s passes."""
        end = time.monotonic()+timeout_s
        result = self.release()
        while result == "closing" and time.monotonic() < end:
            time.sleep(poll_s)
            result = self.release()
            if result is False:            # the last worker removed the record after our release: done
                return "released"
        return result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def acquire(campaign, owner, *, owner_pid=None, ttl_s=DEFAULT_TTL_S, directory=None, clock=time.time, kind="campaign"):
    """Take the machine for a campaign or raise LeaseHeld. owner_pid defaults to this process ($PID from PowerShell)."""
    directory = canonical(directory) if directory else default_directory()
    directory.mkdir(parents=True, exist_ok=True)
    record = _new_record(kind, campaign, owner, os.getpid() if owner_pid is None else owner_pid, ttl_s, clock)
    with transition(directory):
        _take(directory, record, clock)
    return Lease(directory, record, clock)


class Admission:
    """A guard's reservation for one worker: a bare lease of its own, or a child registration under a campaign."""

    def __init__(self, directory, lease_id, kind, pid, clock):
        self.directory, self.lease_id, self.kind, self.pid, self.clock = canonical(directory), lease_id, kind, pid, clock

    def heartbeat(self):
        """Bare leases are renewed by their guard; a child is covered by its campaign's heartbeat."""
        if self.kind == "bare":
            Lease(self.directory, dict(lease_id=self.lease_id), self.clock).heartbeat()

    def release(self):
        with transition(self.directory):
            current = read(self.directory)
            if not current or current.get("lease_id") != self.lease_id:
                return False
            if self.kind == "bare":
                _patient((self.directory/NAME).unlink)
            else:
                current["children"] = [c for c in current.get("children", []) if c["pid"] != self.pid]
                if current.get("closing") and not _live_children(current):
                    _patient((self.directory/NAME).unlink)     # the last worker of a released campaign closes it
                else:
                    _write(self.directory, current)
            return True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def admit_worker(label, *, environ=None, guard_pid=None, ttl_s=300., directory=None, clock=time.time):
    """Guard-side admission, held for the worker's whole life (pid = the supervising guard process).

    - `environ` carries a live campaign lease's id → registered as that campaign's child ("child").
    - No lease, or a stale one → a bare lease is taken for this worker ("bare"), which a campaign cannot start under.
    - Anything else → LeaseHeld.
    """
    environ = os.environ if environ is None else environ
    configured = directory or environ.get(DIR_ENV)
    directory = canonical(configured) if configured else default_directory()
    directory.mkdir(parents=True, exist_ok=True)
    pid = os.getpid() if guard_pid is None else int(guard_pid)
    with transition(directory):
        current = read(directory)
        status = state(current, clock)
        wanted = environ.get(ENV)
        if wanted and current and current.get("lease_id") == wanted and current.get("kind") == "campaign" \
                and status in ("live", "overdue", "unverifiable", "orphaned"):
            # One worker at a time per campaign, whatever root or guard it comes from (Astra Part B, B02): the
            # per-root worker mutex cannot see a replay root, so the lease itself refuses a second live child.
            running = _live_children(current)
            if running:
                raise LeaseHeld(f"Another worker of campaign {current['campaign']!r} is still running "
                                f"({running[0].get('label')}, pid {running[0]['pid']}); one worker at a time")
            alive, created = process_identity(pid)
            if alive != "alive":
                raise ValueError(f"Guard pid {pid} is not an inspectable running process ({alive})")
            current.setdefault("children", []).append(dict(pid=pid, created=created, label=str(label), since=clock()))
            _write(directory, current)
            return Admission(directory, wanted, "child", pid, clock)
        if wanted:
            raise LeaseHeld(f"Worker carries lease {wanted}, which is not the machine's live campaign lease: "
                            + (describe(current, status, clock) if current else "no lease"))
        record = _new_record("bare", label, "guarded worker", pid, ttl_s, clock)
        _take(directory, record, clock)
        return Admission(directory, record["lease_id"], "bare", pid, clock)


def guard_admission(label):
    """admit_worker() for the guards, reporting a refusal the way the guards report their other admission refusals.

    Integrated 29 Sep 2026 as its own behaviour change (M14; checkpoint-A A02, addendum AA01/AA02). The guard
    holds the admission for its worker's whole life, renews a bare lease from its monitor loop (every
    GUARD_HEARTBEAT_S) and releases it in `finally`.
    """
    try:
        return admit_worker(label)
    except LeaseHeld as exc:
        raise RuntimeError(f"Campaign lease refused admission: {exc}") from None


GUARD_HEARTBEAT_S = 60.


@contextlib.contextmanager
def campaign(label, owner, *, ttl_s=DEFAULT_TTL_S, directory=None, drain_timeout_s=600.):
    """For a serial controller: hold one campaign lease across all its workers, gaps and back-off waits.

    The lease id (and coordination directory) is exported into os.environ for the duration, so every guard the
    controller starts, whether in-process (guard.run) or as a subprocess, registers its worker as a child. On exit
    the environment is restored and the lease drained. The guard's job object has already ended each worker, so this
    is normally immediate. A controller killed outright (for example, the PC switched off) leaves a lease that
    becomes stale once its heartbeat lapses, and the next run recovers it.
    """
    held = acquire(label, owner, ttl_s=ttl_s, directory=directory)
    saved = {k: os.environ.get(k) for k in (ENV, DIR_ENV)}
    os.environ.update({ENV: held.id, DIR_ENV: str(held.directory)})
    try:
        yield held
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        held.drain(timeout_s=drain_timeout_s)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Campaign lease for a PowerShell controller.")
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("acquire")
    a.add_argument("--campaign", required=True)
    a.add_argument("--owner", required=True)
    a.add_argument("--owner-pid", type=int, required=True)
    a.add_argument("--ttl", type=float, default=DEFAULT_TTL_S)
    for name in ("heartbeat", "release"):
        sub.add_parser(name).add_argument("--lease-id", required=True)
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "acquire":
        print(acquire(args.campaign, args.owner, owner_pid=args.owner_pid, ttl_s=args.ttl).id)
        return
    if args.command == "status":
        status, record = check()
        print(json.dumps(dict(state=status, directory=str(default_directory()), record=record), indent=1))
        return
    lease = Lease(default_directory(), dict(lease_id=args.lease_id), time.time)
    if args.command == "heartbeat":
        lease.heartbeat()
    elif not lease.release():
        raise LeaseLost(f"Lease {args.lease_id} is not the current lease")


if __name__ == "__main__":
    main()
