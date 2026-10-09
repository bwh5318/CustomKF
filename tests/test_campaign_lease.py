"""Campaign lease v2 (review M14; checkpoint-A finding A02): serialized transitions, reserved admission, three-valued
owner identity, one coordination identity per machine user.

    C:\\anaconda\\python.exe -m unittest tests.test_campaign_lease -v

Uses temporary coordination directories (each has its own mutex), never the real one. No guard needed: the only child
processes are tiny controller/worker stand-ins (no numerical work).
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from customkf.runtime import lease as L

ROOT = str(Path(__file__).resolve().parents[1])

CONTROLLER = r'''
import os, subprocess, sys, time
from pathlib import Path
from customkf.runtime import lease as L
directory, signals = Path(sys.argv[1]), Path(sys.argv[2])
def mark(name): (signals/name).write_text("1")
def wait(name):
    while not (signals/name).exists(): time.sleep(0.02)
held = L.acquire("test-campaign", "stand-in controller", directory=directory, ttl_s=60)
worker = ("from customkf.runtime import lease as L\n"
          "with L.admit_worker('w') as a: print(a.kind)")
for step in ("worker1", "worker2"):
    out = subprocess.run([sys.executable, "-c", worker], env=held.child_environment(),
                         capture_output=True, text=True, check=True).stdout.strip()
    (signals/(step+".out")).write_text(out)
    mark(step+".done")
    if step == "worker1":
        wait("probe_gap.done")          # gap between two serial workers: no Python child alive
        held.heartbeat()
        mark("backoff")
        wait("probe_backoff.done")      # resource back-off: the controller sleeps, heartbeat renewed
        held.heartbeat()
held.release()
mark("released")
'''


class Clock:
    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="lease-"))
        self.clock = Clock()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def acquire(self, **kw):
        return L.acquire("c", "test", directory=self.dir, clock=self.clock, **kw)

    def admit(self, environ=None, **kw):
        return L.admit_worker("worker", environ={} if environ is None else environ, directory=self.dir,
                              clock=self.clock, **kw)

    def exited_pid(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        return child.pid

    def sleeper(self):
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.readline()"], stdin=subprocess.PIPE,
                                 text=True)
        self.addCleanup(lambda: child.poll() is None and (child.kill(), child.wait(10)))
        return child

    def write_record(self, **fields):
        _, created = L.process_identity(os.getpid())
        record = dict(version=2, kind="campaign", lease_id="old", campaign="old campaign", owner="old controller",
                      owner_pid=os.getpid(), owner_created=created, host="h", created=self.clock(),
                      heartbeat=self.clock(), ttl_s=60., children=[])
        record.update(fields)
        (self.dir/L.NAME).write_text(json.dumps(record))
        return record


class Basics(Case):
    def test_acquire_is_exclusive(self):
        held = self.acquire()
        with self.assertRaisesRegex(L.LeaseHeld, r"\[live\]"):
            self.acquire()
        self.assertTrue(held.release())
        self.acquire().release()

    def test_release_only_by_holder(self):
        held = self.acquire()
        impostor = L.Lease(self.dir, dict(held.record, lease_id="someone else"), self.clock)
        self.assertFalse(impostor.release())
        self.assertEqual(L.read(self.dir)["lease_id"], held.id)

    def test_overdue_live_owner_is_not_broken(self):
        self.write_record()
        self.clock.now += 3600
        self.assertEqual(L.check(self.dir, self.clock)[0], "overdue")
        with self.assertRaisesRegex(L.LeaseHeld, r"\[overdue\]"):
            self.acquire()
        with self.assertRaises(L.LeaseHeld):
            self.admit()

    def test_dead_owner_with_fresh_heartbeat_still_held(self):
        self.write_record(owner_pid=self.exited_pid())
        with self.assertRaises(L.LeaseHeld):
            self.acquire()

    def test_stale_lease_recovered_and_kept(self):
        self.write_record(owner_pid=self.exited_pid())
        self.clock.now += 61
        self.assertEqual(L.check(self.dir, self.clock)[0], "stale")
        held = self.acquire()
        self.assertEqual(L.read(self.dir)["lease_id"], held.id)
        self.assertEqual(json.loads((self.dir/"campaign_lease.stale-old.json").read_text())["lease_id"], "old")

    def test_pid_reuse_is_dead(self):
        self.assertEqual(L.liveness(os.getpid(), 12345), "dead")
        self.assertEqual(L.liveness(os.getpid(), L.process_identity(os.getpid())[1]), "alive")

    def test_unreadable_lease_is_held(self):
        (self.dir/L.NAME).write_text("")
        with self.assertRaisesRegex(L.LeaseHeld, "cannot be read"):
            self.acquire()
        with self.assertRaises(L.LeaseHeld):
            self.admit()

    def test_heartbeat_after_loss(self):
        held = self.acquire()
        held.heartbeat()
        (self.dir/L.NAME).unlink()
        self.write_record(lease_id="replacement")
        with self.assertRaises(L.LeaseLost):
            held.heartbeat()
        self.assertEqual(L.read(self.dir)["lease_id"], "replacement")

    def test_owner_must_be_inspectable_and_running(self):
        with self.assertRaisesRegex(ValueError, "not an inspectable running process"):
            self.acquire(owner_pid=self.exited_pid())

    def test_nested_transition_refused(self):
        with L.transition(self.dir):
            with self.assertRaisesRegex(RuntimeError, "Nested lease transition"):
                with L.transition(self.dir):
                    pass


class Admission(Case):
    """A02 item 1: admission is a reservation held for the worker's life, and campaigns account for bare workers."""

    def test_bare_worker_blocks_a_campaign_until_it_ends(self):
        with self.admit() as admission:
            self.assertEqual(admission.kind, "bare")
            with self.assertRaisesRegex(L.LeaseHeld, "bare"):
                self.acquire()
            with self.assertRaises(L.LeaseHeld):
                self.admit()                                  # a second bare worker too
        self.acquire().release()

    def test_campaign_admits_only_its_own_workers_and_registers_them(self):
        held = self.acquire()
        with self.assertRaises(L.LeaseHeld):
            self.admit()
        with self.assertRaisesRegex(L.LeaseHeld, "not the machine's live campaign lease"):
            self.admit({L.ENV: "wrong"})
        with self.admit(held.child_environment({})) as child:
            self.assertEqual(child.kind, "child")
            self.assertEqual([c["pid"] for c in L.read(self.dir)["children"]], [os.getpid()])
        self.assertEqual(L.read(self.dir)["children"], [])

    def test_one_worker_at_a_time_per_campaign(self):
        """Astra Part B, B02: a second authorized worker is refused while the first is registered and alive."""
        held = self.acquire()
        with self.admit(held.child_environment({})):
            with self.assertRaisesRegex(L.LeaseHeld, "one worker at a time"):
                self.admit(held.child_environment({}))
        with self.admit(held.child_environment({})) as second:           # after the first leaves, the next may start
            self.assertEqual(second.kind, "child")

    def test_worker_of_a_released_campaign_is_refused(self):
        held = self.acquire()
        env = held.child_environment({})
        held.release()
        with self.assertRaisesRegex(L.LeaseHeld, "no lease"):
            self.admit(env)

    def test_second_controller_between_workers_and_during_backoff(self):
        signals = self.dir/"signals"
        signals.mkdir()
        controller = subprocess.Popen([sys.executable, "-c", CONTROLLER, str(self.dir), str(signals)], cwd=ROOT,
                                      env={**os.environ, "PYTHONPATH": ROOT})
        try:
            def wait(name, timeout=60):
                end = time.time()+timeout
                while not (signals/name).exists():
                    self.assertIsNone(controller.poll(), "controller exited early")
                    self.assertLess(time.time(), end, "timed out waiting for "+name)
                    time.sleep(0.02)
            for probe, after in (("probe_gap", "worker1.done"), ("probe_backoff", "backoff")):
                wait(after)
                with self.assertRaises(L.LeaseHeld):
                    L.acquire("intruder", "second controller", directory=self.dir)
                with self.assertRaises(L.LeaseHeld):
                    L.admit_worker("bare job in the gap", environ={}, directory=self.dir)
                (signals/(probe+".done")).write_text("1")
            wait("released")
            self.assertEqual(controller.wait(30), 0)
        finally:
            if controller.poll() is None:
                controller.kill()
        self.assertEqual((signals/"worker1.out").read_text(), "child")
        self.assertEqual((signals/"worker2.out").read_text(), "child")
        self.assertEqual(L.check(self.dir)[0], "free")


class Interleavings(Case):
    """A02 item 2: a check and its write are never separated; renewal, release and recovery are serialized."""

    def paused_heartbeat(self, lease):
        """Run lease.heartbeat() in a thread that pauses inside its transition, after reading the record."""
        inside, go = threading.Event(), threading.Event()
        real_read, errors = L.read, []

        def read(directory=None):
            record = real_read(directory)
            if threading.current_thread() is worker:
                inside.set()
                go.wait(10)
            return record

        def run():
            try:
                lease.heartbeat()
            except Exception as error:              # noqa: BLE001 - reported to the test
                errors.append(error)
        worker = threading.Thread(target=run)
        patcher = mock.patch.object(L, "read", side_effect=read)
        patcher.start()
        self.addCleanup(patcher.stop)
        worker.start()
        self.assertTrue(inside.wait(10))
        return worker, go, errors

    def test_recovery_waits_for_an_in_flight_heartbeat(self):
        """Astra's probe: old owner exits and a new party recovers while a heartbeat is in flight."""
        owner = self.sleeper()
        old = self.acquire(owner_pid=owner.pid, ttl_s=1)
        self.clock.now += 10
        worker, go, errors = self.paused_heartbeat(old)
        owner.communicate(input="\n", timeout=5)     # the real owner process exits: the lease would now be stale
        result = []
        contender = threading.Thread(target=lambda: result.append(self._try_acquire()))
        contender.start()
        time.sleep(0.3)
        self.assertTrue(contender.is_alive(), "recovery must wait for the in-flight heartbeat's transition")
        go.set()
        worker.join(10)
        contender.join(15)
        self.assertEqual(errors, [])
        # The renewed heartbeat is fresh, so the contender sees a live lease and is refused; nothing is overwritten.
        self.assertIsInstance(result[0], L.LeaseHeld)
        self.assertEqual(L.read(self.dir)["lease_id"], old.id)

    def _try_acquire(self):
        try:
            return self.acquire()
        except L.LeaseHeld as error:
            return error

    def test_heartbeat_after_recovery_fails_and_never_overwrites(self):
        owner = self.sleeper()
        old = self.acquire(owner_pid=owner.pid, ttl_s=1)
        self.clock.now += 10
        owner.communicate(input="\n", timeout=5)
        new = self.acquire()                          # stale recovery by a new owner
        with self.assertRaises(L.LeaseLost):
            old.heartbeat()                           # the old helper's late renewal
        self.assertEqual(L.read(self.dir)["lease_id"], new.id)
        self.assertFalse(old.release())
        self.assertEqual(L.read(self.dir)["lease_id"], new.id)

    def test_same_thread_reentry_is_refused_not_interleaved(self):
        """The probe's in-thread variant (a transition triggered inside another) fails loudly instead of overwriting."""
        old = self.acquire()
        real_read = L.read

        def read(directory=None):
            L.acquire("inner", "reentrant", directory=self.dir, clock=self.clock)
            return real_read(directory)
        with mock.patch.object(L, "read", side_effect=read):
            with self.assertRaisesRegex(RuntimeError, "Nested lease transition"):
                old.heartbeat()
        self.assertEqual(L.read(self.dir)["lease_id"], old.id)

    def test_abandoned_coordination_lock_is_handed_on(self):
        """A holder that dies inside a transition does not wedge the machine."""
        code = ("import ctypes, os, sys; from customkf.runtime import lease as L\n"
                "cm = L.transition(sys.argv[1]); cm.__enter__(); os._exit(0)")
        subprocess.run([sys.executable, "-c", code, str(self.dir)], cwd=ROOT, env={**os.environ, "PYTHONPATH": ROOT},
                       check=True, timeout=30)
        start = time.monotonic()
        self.acquire().release()
        self.assertLess(time.monotonic()-start, 5)

    def test_concurrent_acquire_one_winner(self):
        for _ in range(5):
            won, lost = self.contend(self.acquire)
            self.assertEqual((len(won), len(lost)), (1, 7))
            self.assertEqual(L.read(self.dir)["lease_id"], won[0].id)
            won[0].release()

    def test_concurrent_recovery_one_winner(self):
        dead = self.exited_pid()
        for round_ in range(5):
            self.write_record(lease_id=f"old{round_}", owner_pid=dead)
            self.clock.now += 61
            won, lost = self.contend(self.acquire)
            self.assertEqual(len(won), 1)
            self.assertEqual(L.read(self.dir)["lease_id"], won[0].id)
            self.assertTrue((self.dir/f"campaign_lease.stale-old{round_}.json").exists())
            won[0].release()

    def test_concurrent_bare_admissions_one_winner(self):
        won, lost = self.contend(self.admit)
        self.assertEqual((len(won), len(lost)), (1, 7))
        won[0].release()

    def contend(self, action, count=8):
        barrier, won, lost = threading.Barrier(count), [], []

        def contender():
            barrier.wait()
            try:
                won.append(action())
            except L.LeaseHeld as error:
                lost.append(error)
        threads = [threading.Thread(target=contender) for _ in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        return won, lost

    def test_heartbeat_never_looks_free(self):
        held, seen, stop = self.acquire(), [], threading.Event()

        def guard():
            while not stop.is_set():
                seen.append(L.check(self.dir, self.clock)[0])
        readers = [threading.Thread(target=guard) for _ in range(4)]
        for t in readers:
            t.start()
        for _ in range(200):
            held.heartbeat()
        stop.set()
        for t in readers:
            t.join(30)
        self.assertGreater(len(seen), 100)
        self.assertEqual(set(seen), {"live"})


class OwnerIdentity(Case):
    """A02 item 3: an owner that cannot be inspected is unknown and held, never reclaimed as dead."""

    class Kernel:
        def __init__(self, open_result=0, exit_ok=True):
            self.open_result, self.exit_ok = open_result, exit_ok

        def OpenProcess(self, *args):
            return self.open_result

        def GetExitCodeProcess(self, handle, code):
            return 1 if self.exit_ok else 0

        def GetProcessTimes(self, *args):
            return 0

        def CloseHandle(self, handle):
            return 1

    def test_access_denied_owner_is_unverifiable_and_held(self):
        record = self.write_record()
        self.clock.now += 3600
        with mock.patch.object(L, "_kernel", return_value=self.Kernel()), \
                mock.patch.object(L.ctypes, "get_last_error", return_value=5):
            self.assertEqual(L.process_identity(os.getpid()), ("unknown", None))
            self.assertEqual(L.state(record, self.clock), "unverifiable")

    def test_no_such_process_is_dead(self):
        with mock.patch.object(L, "_kernel", return_value=self.Kernel()), \
                mock.patch.object(L.ctypes, "get_last_error", return_value=87):
            self.assertEqual(L.process_identity(123456), ("dead", None))

    def test_failed_exit_code_query_is_unknown(self):
        with mock.patch.object(L, "_kernel", return_value=self.Kernel(open_result=1, exit_ok=False)):
            self.assertEqual(L.process_identity(os.getpid()), ("unknown", None))

    def test_dead_controller_with_surviving_worker_is_orphaned(self):
        worker = self.sleeper()
        _, created = L.process_identity(worker.pid)
        self.write_record(owner_pid=self.exited_pid(), children=[dict(pid=worker.pid, created=created, label="w")])
        self.clock.now += 61
        self.assertEqual(L.check(self.dir, self.clock)[0], "orphaned")
        with self.assertRaisesRegex(L.LeaseHeld, r"\[orphaned\]"):
            self.acquire()
        worker.communicate(input="\n", timeout=5)
        self.assertEqual(L.check(self.dir, self.clock)[0], "stale")
        self.acquire().release()


class Closing(Case):
    """Addendum review AA01: releasing a campaign never forgets a live (or uninspectable) registered worker."""

    def campaign_with_worker(self):
        held, worker = self.acquire(), self.sleeper()
        child = L.admit_worker("w", environ=held.child_environment({}), guard_pid=worker.pid, directory=self.dir,
                               clock=self.clock)
        return held, worker, child

    def test_release_with_live_worker_keeps_the_machine_reserved(self):
        held, worker, child = self.campaign_with_worker()
        self.assertEqual(held.release(), "closing")
        self.assertEqual(L.check(self.dir, self.clock)[0], "closing")
        with self.assertRaisesRegex(L.LeaseHeld, r"\[closing\]"):
            self.acquire()                                    # the probe's second campaign
        with self.assertRaises(L.LeaseHeld):
            self.admit()                                      # a bare job
        with self.assertRaises(L.LeaseHeld):
            self.admit(held.child_environment({}))            # a new worker of the released campaign
        self.assertIsNone(worker.poll())
        self.assertTrue(child.release())                      # the last worker leaves and removes the record
        self.assertEqual(L.check(self.dir, self.clock)[0], "free")

    def test_worker_that_dies_without_releasing_makes_it_recoverable(self):
        held, worker, _ = self.campaign_with_worker()
        self.assertEqual(held.release(), "closing")
        worker.communicate(input="\n", timeout=5)
        self.assertEqual(L.check(self.dir, self.clock)[0], "stale")
        self.acquire().release()

    def test_unknown_worker_liveness_keeps_it_closing(self):
        held, worker, _ = self.campaign_with_worker()
        with mock.patch.object(L, "liveness", return_value="unknown"):
            self.assertEqual(held.release(), "closing")
            self.assertEqual(L.check(self.dir, self.clock)[0], "closing")
            with self.assertRaises(L.LeaseHeld):
                self.acquire()

    def test_drain_waits_for_the_last_worker(self):
        held, worker, child = self.campaign_with_worker()
        timer = threading.Timer(0.5, child.release)
        timer.start()
        self.assertEqual(held.drain(timeout_s=10, poll_s=0.05), "released")
        timer.join()
        self.assertEqual(L.check(self.dir, self.clock)[0], "free")

    def test_drain_times_out_while_a_worker_lives(self):
        held, worker, _ = self.campaign_with_worker()
        self.assertEqual(held.drain(timeout_s=0.2, poll_s=0.05), "closing")

    def test_release_without_workers_is_immediate(self):
        self.assertEqual(self.acquire().release(), "released")


class CanonicalDirectory(Case):
    """Addendum review AA02: the coordination directory is absolute and canonical everywhere."""

    def test_relative_override_is_refused(self):
        with mock.patch.dict(os.environ, {L.DIR_ENV: "coordination"}):
            with self.assertRaisesRegex(ValueError, "absolute"):
                L.default_directory()
            with self.assertRaisesRegex(ValueError, "absolute"):
                L.acquire("c", "t")
            with self.assertRaisesRegex(ValueError, "absolute"):
                L.admit_worker("w", environ={L.DIR_ENV: "coordination"})

    def test_relative_explicit_directory_is_refused(self):
        for call in (lambda: L.acquire("c", "t", directory="coordination"),
                     lambda: L.admit_worker("w", environ={}, directory="coordination"),
                     lambda: L.read("coordination")):
            with self.assertRaisesRegex(ValueError, "absolute"):
                call()

    def test_lease_survives_a_working_directory_change(self):
        held = self.acquire()
        cwd = os.getcwd()
        try:
            os.chdir(tempfile.gettempdir())
            held.heartbeat()
            self.assertEqual(Path(held.child_environment({})[L.DIR_ENV]), self.dir.resolve())
            self.assertEqual(held.release(), "released")
        finally:
            os.chdir(cwd)
        self.assertEqual(L.check(self.dir, self.clock)[0], "free")


class SharedIdentity(Case):
    """A02 item 4: one coordination identity per machine user, shared by the workspace and replay roots."""

    def test_default_directory_is_outside_any_checkout(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(L.DIR_ENV, None)
            default = L.default_directory()
        self.assertNotIn(Path(ROOT).resolve(), default.resolve().parents)
        self.assertEqual(default.name, "coordination")

    def test_default_is_programdata_not_appdata(self):
        """Packaged apps virtualize AppData (measured 29 Sep 2026); ProgramData is shared across app boundaries."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(L.DIR_ENV, None)
            default = L.default_directory()
        expected = (Path(os.environ.get("PROGRAMDATA") or "C:/ProgramData")/"customKF"/"coordination").resolve()
        self.assertEqual(default, expected)

    def test_appdata_locations_are_refused(self):
        for key in ("LOCALAPPDATA", "APPDATA"):
            with self.subTest(key), self.assertRaisesRegex(ValueError, "AppData"):
                L.canonical(Path(os.environ[key])/"customKF"/"coordination")
        with self.assertRaisesRegex(ValueError, "AppData"):
            L.canonical("C:/Users/x/AppData/Local/Packages/SomeApp_123/LocalCache/Local/customKF")

    def test_two_roots_share_one_lease(self):
        code = ("import sys; from customkf.runtime import lease as L\n"
                "try:\n    L.acquire('replay', 'root '+sys.argv[1]); print('acquired')\n"
                "except L.LeaseHeld:\n    print('held')")
        env = {**os.environ, L.DIR_ENV: str(self.dir)}
        held = L.acquire("workspace", "test", directory=self.dir)
        try:
            for root in (ROOT, str(self.dir)):          # a different working root; same coordination identity
                out = subprocess.run([sys.executable, "-c", code, root], cwd=root, capture_output=True, text=True,
                                     env={**env, "PYTHONPATH": ROOT}, timeout=60).stdout.strip()
                self.assertEqual(out, "held")
        finally:
            held.release()


if __name__ == "__main__":
    unittest.main()
