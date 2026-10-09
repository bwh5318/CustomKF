"""Opus_Fork.run_fit_elev: lease before any campaign write (Astra Part B, B01), the immutable campaign specification
on resume (Sol SOL-02), and semantic worker acceptance before `ok` and on reuse (Sol SOL-06).

    C:\\anaconda\\python.exe -m unittest tests.test_run_fit_elev_lease -v

Synthetic resume targets under Opus_Fork/runs (removed afterwards), a temporary coordination directory, mocked
workers. No worker is launched; no historical campaign is touched.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from customkf.runtime import lease as L
from Opus_Fork import elev
from Opus_Fork import run_fit_elev as C
from claude.roadmap.streaming import Accumulator


def write_valid(path):
    """A minimal valid output array/record of the kind named by `path` (Astra E-01 positive controls)."""
    rng = np.random.default_rng(5)
    if path.name == "trajectories.npz":
        np.savez(path, times=np.arange(3.), G01_states=rng.normal(size=(3, 6)), G01_stm=rng.normal(size=(3, 6, 6)),
                 G01_sensitivity=rng.normal(size=(3, 6, 5)))
    elif path.name == "checkpoint.npz":
        acc = Accumulator(2)
        for _ in range(2):
            acc.add_block(rng.normal(size=(4, 2)), rng.normal(size=(4, 1)), rng.normal(size=4), np.ones(4))
        np.savez(path, **acc.state(), residual=rng.normal(size=8), sigma=np.ones(8))
    elif path.name == "solution.npz":
        np.savez(path, x=rng.normal(size=5), names=np.array([f"p{i}" for i in range(5)]), states=rng.normal(size=(2, 3, 6)),
                 satellites=np.array(["G01", "G02"]), times_s=np.arange(3.), residual_m=rng.normal(size=4),
                 sigma_m=np.ones(4), retained_covariance=np.eye(2))
    elif path.name == "direction.npz":
        np.savez(path, x=rng.normal(size=5), step=rng.normal(size=5), names=np.array([f"p{i}" for i in range(5)]),
                 retained_covariance=np.eye(2))
    elif path.name == "state.json":
        path.write_text(json.dumps(dict(clock_seeds=[[[0, "AAAA"], 1.5]], windup=[0.25], amb_origins={"a": 2.0})))
    else:
        raise ValueError(path.name)

FIXTURE_DIR = "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03"
CONFIG = "claude/roadmap/configs/unit-ecom5.json"
OTHER_CONFIG = "claude/experiments/cross_date_preparation/config.json"
PROTOCOL = "Opus_Fork/experiments/untouched_dates/PROTOCOL.md"
VARIANT = "erp+thrust+iiia2600+sdeop+elw13"
LABEL = "contract-test"


def binding():
    with mock.patch.dict(os.environ, {elev.ENVIRONMENT: VARIANT}):
        return elev.binding()


class Target(unittest.TestCase):
    def setUp(self):
        self.coord = Path(tempfile.mkdtemp(prefix="elev-lease-")).resolve()
        self.target = C.RUNS/"_test_resume_contract_synthetic"
        shutil.rmtree(self.target, ignore_errors=True)
        (self.target/"lin0-traj-0").mkdir(parents=True)
        (self.target/"lin0-traj-0"/"partial.txt").write_text("interrupted worker output")
        os.chdir(ROOT)

    def tearDown(self):
        shutil.rmtree(self.target, ignore_errors=True)
        shutil.rmtree(self.coord, ignore_errors=True)

    def legacy_report(self):
        return dict(status="failed", fixture=f"{FIXTURE_DIR}/fixture.json", label=LABEL, force_model=binding(),
                    config=CONFIG, chunk_epochs=12, trajectory_groups=2, profile="fork8",
                    limits=dict(timeout_s=900.0), source_sha256={PROTOCOL: sha(ROOT/PROTOCOL)},
                    runs={"lin0-traj-0": {"status": "failed"}},
                    active_worker=None)

    def spec_report(self, **changes):
        meta = json.loads((ROOT/FIXTURE_DIR/"step.json").read_text())
        args = NS(label=LABEL, variant=VARIANT, protocol=PROTOCOL, chunk_epochs=12, trajectory_groups=2,
                  max_linearizations=6, profile="fork8")
        spec = C.specification(args, (ROOT/FIXTURE_DIR/"fixture.json").resolve(), meta, (ROOT/CONFIG).resolve(),
                               CONFIG, binding())
        spec.update(changes)
        return dict(self.legacy_report(), spec=spec)

    def write(self, report):
        self.manifest = self.target/"validation.json"
        self.manifest.write_text(json.dumps(report))
        self.before = self.manifest.read_bytes()

    def argv(self, *extra, config=CONFIG, max_lin="6", timeout="900", protocol=PROTOCOL):
        return ["run_fit_elev", "--fixture", FIXTURE_DIR, "--config", config, "--label", LABEL,
                "--chunk-epochs", "12", "--trajectory-groups", "2", "--max-linearizations", max_lin,
                "--worker-timeout", timeout, "--protocol", protocol, "--variant", VARIANT,
                "--resume", str(self.target), *extra]

    def run_main(self, argv, drive=None):
        with mock.patch.dict(os.environ, {L.DIR_ENV: str(self.coord)}), mock.patch.object(sys, "argv", argv), \
                mock.patch.object(C.process_check, "campaign_processes", return_value=[]), \
                mock.patch.object(C, "_drive", side_effect=drive or AssertionError("must not drive")) as driven, \
                mock.patch.object(C, "run") as worker:
            try:
                return C.main()
            finally:
                worker.assert_not_called()

    def assert_untouched(self):
        self.assertEqual(self.manifest.read_bytes(), self.before)
        self.assertEqual(sorted(p.name for p in self.target.iterdir()), ["lin0-traj-0", "validation.json"])


NEEDS_FIXTURE = unittest.skipUnless((ROOT/FIXTURE_DIR/"step.json").is_file(),
                                    f"needs the local prepare record {FIXTURE_DIR} (not in the public tree)")


class LeaseFirst(Target):
    @NEEDS_FIXTURE
    def test_refused_resume_leaves_the_target_untouched(self):
        """B01: with another campaign's lease held, the resume is refused before any write."""
        self.write(self.legacy_report())
        with L.acquire("another controller", "test", directory=self.coord):
            with self.assertRaises(L.LeaseHeld):
                self.run_main(self.argv("--legacy-resume"))
        self.assert_untouched()


@NEEDS_FIXTURE
class ResumeSpecification(Target):
    """SOL-02: a resume must match the campaign's specification, checked before any mutation."""

    def test_different_config_refused(self):
        self.write(self.spec_report())
        with self.assertRaisesRegex(ValueError, "differs from the campaign specification.*config"):
            self.run_main(self.argv(config=OTHER_CONFIG))
        self.assert_untouched()

    def test_different_linearization_cap_refused(self):
        self.write(self.spec_report())
        with self.assertRaisesRegex(ValueError, "max_linearizations"):
            self.run_main(self.argv(max_lin="99"))
        self.assert_untouched()

    def test_different_protocol_refused(self):
        self.write(self.spec_report())
        with self.assertRaisesRegex(ValueError, "protocol"):
            self.run_main(self.argv(protocol="Opus_Fork/results/ELEVATION_PROTOCOL.md"))
        self.assert_untouched()

    def test_matching_request_proceeds_and_a_timeout_change_is_recorded(self):
        self.write(self.spec_report())
        seen = {}

        def drive(args, folder, report, *rest, **kw):
            seen["continuations"] = report.get("continuations")
        self.run_main(self.argv(timeout="1200"), drive=drive)
        self.assertEqual(seen["continuations"][-1]["worker_timeout_s"], dict(recorded=900.0, requested=1200.0))

    def test_legacy_record_needs_explicit_acknowledgement(self):
        self.write(self.legacy_report())
        with self.assertRaisesRegex(ValueError, "--legacy-resume"):
            self.run_main(self.argv())
        self.assert_untouched()
        seen = {}

        def drive(args, folder, report, *rest, **kw):
            seen["continuations"] = report.get("continuations")
            seen["spec"] = report.get("spec")
        self.run_main(self.argv("--legacy-resume"), drive=drive)
        assumed = seen["continuations"][-1]["legacy_assumed"]
        self.assertEqual(assumed["max_linearizations"], 6)
        self.assertEqual(assumed["protocol"], PROTOCOL)
        self.assertIsNone(seen["spec"])                    # the original record is never back-filled

    def legacy_with_continuation(self, **assumed):
        report = self.legacy_report()
        first = {}

        def drive(args, folder, rep, *rest, **kw):
            first.update(rep["continuations"][-1])
        self.write(report)
        self.run_main(self.argv("--legacy-resume"), drive=drive)       # the first acknowledgement
        shutil.rmtree(self.target)                                      # a fresh target that records it
        (self.target/"lin0-traj-0").mkdir(parents=True)
        (self.target/"lin0-traj-0"/"partial.txt").write_text("interrupted worker output")
        first["legacy_assumed"].update(assumed)
        report["continuations"] = [first]
        self.write(report)
        return report

    def test_matching_later_legacy_continuation_proceeds(self):
        """Astra AR-04: a later resume that repeats the earlier assumptions proceeds."""
        self.legacy_with_continuation()
        seen = {}

        def drive(args, folder, report, *rest, **kw):
            seen["continuations"] = report["continuations"]
        self.run_main(self.argv("--legacy-resume"), drive=drive)
        self.assertEqual(len(seen["continuations"]), 2)
        self.assertEqual(seen["continuations"][0]["legacy_assumed"], seen["continuations"][1]["legacy_assumed"])

    def test_conflicting_later_legacy_continuation_refused_before_any_write(self):
        """Astra AR-04: cap 6 / original protocol assumed earlier; cap 99 or another protocol is now refused."""
        self.legacy_with_continuation()
        with self.assertRaisesRegex(ValueError, "already records.*max_linearizations"):
            self.run_main(self.argv("--legacy-resume", max_lin="99"))
        self.assert_untouched()
        with self.assertRaisesRegex(ValueError, "already records.*protocol"):
            self.run_main(self.argv("--legacy-resume", protocol="Opus_Fork/results/ELEVATION_PROTOCOL.md"))
        self.assert_untouched()

    def test_legacy_protocol_recovered_from_the_source_pins(self):
        """No earlier continuation: the pinned protocol is still not replaceable by the request."""
        self.write(self.legacy_report())
        with self.assertRaisesRegex(ValueError, "pinned protocol"):
            self.run_main(self.argv("--legacy-resume", protocol="Opus_Fork/results/ELEVATION_PROTOCOL.md"))
        self.assert_untouched()
        unpinned = dict(self.legacy_report(), source_sha256={})
        self.write(unpinned)
        with self.assertRaisesRegex(ValueError, "pinned protocol"):        # started without a protocol: None is known
            self.run_main(self.argv("--legacy-resume"))
        self.assert_untouched()

    def test_legacy_record_still_checks_the_fields_it_has(self):
        self.write(self.legacy_report())
        with self.assertRaisesRegex(ValueError, "legacy campaign record.*config"):
            self.run_main(self.argv("--legacy-resume", config=OTHER_CONFIG))
        self.assert_untouched()


class WorkerAcceptance(unittest.TestCase):
    """SOL-06: guard success is not acceptance; a rejected worker never becomes a reusable `ok`."""

    def setUp(self):
        self.scratch = C.RUNS/"_test_worker_acceptance_synthetic"
        shutil.rmtree(self.scratch, ignore_errors=True)
        self.scratch.mkdir(parents=True)
        self.folder = self.scratch/"campaign"
        self.folder.mkdir()
        self.args = NS(label="synthetic", trajectory_groups=1, max_linearizations=1, chunk_epochs=1)
        self.limits = C.Limits(memory_mib=4096, cpu_percent=15, threads=2, processes=1, timeout_s=300.)
        (self.scratch/"fixture").write_text("synthetic fixture")
        (self.scratch/"config").write_text("synthetic config")

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def produced(self, force_model, complete=True, **changes):
        """A trajectory worker's output set; complete=False is Astra's AR-02 metadata-only probe."""
        out = self.scratch/f"worker-{len(list(self.scratch.iterdir()))}"
        out.mkdir()
        meta = {"force_model": force_model}
        if complete:
            write_valid(out/"trajectories.npz")
            meta.update(status="trajectory_cache", satellites=["G01"], keys={"G01": "k"},
                        cache_sha256=sha(out/"trajectories.npz"), fixture_sha256=sha(self.scratch/"fixture"),
                        config_sha256=sha(self.scratch/"config"))
        meta.update(changes)
        (out/"trajectories.json").write_text(json.dumps(meta))
        return out

    def identity(self, **extra):
        return dict(fixture=sha(self.scratch/"fixture"), config=sha(self.scratch/"config"), **extra)

    def drive(self, report, run):
        with mock.patch.object(C, "run", side_effect=run):
            C._drive(self.args, self.folder, report, self.scratch/"fixture", self.scratch/"config", 1, self.limits,
                     {"expected": True}, held=NS(id="mock"))

    def report(self):
        return dict(source_sha256={}, runs={}, state=None, active_worker=None, final=None, accepted_trials=[],
                    linearizations=[])

    def test_wrong_binding_is_recorded_rejected_and_never_reused(self):
        report = self.report()
        with self.assertRaisesRegex(RuntimeError, "did not use the pinned force model"):
            self.drive(report, lambda *a, **k: ({"status": "ok", "exit_code": 0}, self.produced({"wrong": True})))
        record = report["runs"]["lin0-traj-0"]
        self.assertEqual((record["status"], record["guard_status"]), ("rejected", "ok"))
        reached = []

        def next_worker(module_args, *rest, **kw):
            reached.append(module_args[:2])
            raise RuntimeError("synthetic next worker")
        with self.assertRaisesRegex(RuntimeError, "without an ok record"):
            self.drive(report, next_worker)
        self.assertEqual(reached, [])                    # the rejected worker was not reused, nothing went on

    def test_missing_required_record_is_rejected(self):
        report = self.report()
        empty = self.scratch/"empty"
        empty.mkdir()
        with self.assertRaisesRegex(RuntimeError, "required record missing"):
            self.drive(report, lambda *a, **k: ({"status": "ok", "exit_code": 0}, empty))
        self.assertEqual(report["runs"]["lin0-traj-0"]["status"], "rejected")

    def test_an_old_ok_record_failing_acceptance_is_not_reused(self):
        report = self.report()
        out = self.folder/"lin0-traj-0"
        out.mkdir()
        (out/"trajectories.json").write_text(json.dumps({"force_model": {"wrong": True}}))
        module_args = [C.TRAJ, "integrate", "--fixture", str(self.scratch/"fixture"), "--config",
                       str(self.scratch/"config"), "--group", "0", "--groups", "1"]
        report["runs"]["lin0-traj-0"] = dict(status="ok", args=module_args, files_sha256=C.artifact_pins(out))
        with self.assertRaisesRegex(RuntimeError, "fails acceptance on reuse"):
            self.drive(report, AssertionError("must not launch"))

    def test_metadata_only_worker_is_rejected(self):
        """Astra AR-02: a matching declaration without trajectories.npz was recorded ok and reused."""
        report = self.report()
        with self.assertRaisesRegex(RuntimeError, "invalid trajectory-cache record"):
            self.drive(report, lambda *a, **k: ({"status": "ok", "exit_code": 0},
                                                self.produced({"expected": True}, complete=False)))
        self.assertEqual(report["runs"]["lin0-traj-0"]["status"], "rejected")
        meta_only = self.produced({"expected": True}, complete=False, status="trajectory_cache", satellites=["G01"],
                                  keys={"G01": "k"})
        self.assertEqual(C.worker_rejection(meta_only, [C.TRAJ, "integrate"], {"expected": True}, self.identity()),
                         "required output missing: trajectories.npz")

    def test_metadata_only_old_ok_record_is_not_reused(self):
        report = self.report()
        out = self.folder/"lin0-traj-0"
        out.mkdir()
        (out/"trajectories.json").write_text(json.dumps({"force_model": {"expected": True}}))
        module_args = [C.TRAJ, "integrate", "--fixture", str(self.scratch/"fixture"), "--config",
                       str(self.scratch/"config"), "--group", "0", "--groups", "1"]
        report["runs"]["lin0-traj-0"] = dict(status="ok", args=module_args, files_sha256=C.artifact_pins(out))
        with self.assertRaisesRegex(RuntimeError, "fails acceptance on reuse"):
            self.drive(report, AssertionError("must not launch"))

    def test_incomplete_or_foreign_trajectory_sets_are_rejected(self):
        cases = {"trajectories.npz does not match": dict(cache_sha256="0"*64),
                 "different fixture or config": dict(fixture_sha256="0"*64),
                 "invalid trajectory-cache record": dict(status="trajectory_partial")}
        for reason, change in cases.items():
            with self.subTest(reason):
                out = self.produced({"expected": True}, **change)
                self.assertIn(reason, C.worker_rejection(out, [C.TRAJ, "integrate"], {"expected": True}, self.identity()))
        self.assertIsNone(C.worker_rejection(self.produced({"expected": True}), [C.TRAJ, "integrate"],
                                             {"expected": True}, self.identity()))

    def iteration_worker(self, status, output=None, binding=None, **step):
        out = self.scratch/f"iter-{len(list(self.scratch.iterdir()))}"
        out.mkdir()
        (out/"force_model.json").write_text(json.dumps({"expected": True}))
        record = dict(status=status, binding=binding if binding is not None else self.identity(state="s"*64), **step)
        if output:
            name, key = output
            write_valid(out/name)
            record[key] = sha(out/name)
        (out/"step.json").write_text(json.dumps(record))
        return out

    def test_iteration_worker_kinds(self):
        identity = self.identity(state="s"*64)
        ok = {"chunk": ("chunk_complete", ("checkpoint.npz", "checkpoint_sha256")),
              "solve": ("linearized", ("direction.npz", "direction_sha256")),
              "trial": ("iteration_complete", ("solution.npz", "solution_sha256"))}
        for mode, (status, output) in ok.items():
            with self.subTest(mode=mode):
                args = [C.ITER, mode]
                self.assertIsNone(C.worker_rejection(self.iteration_worker(status, output), args, {"expected": True},
                                                     identity))
                missing = self.iteration_worker(status, output)
                (missing/output[0]).unlink()
                self.assertEqual(C.worker_rejection(missing, args, {"expected": True}, identity),
                                 f"required output missing: {output[0]}")
                self.assertIn("does not complete",
                              C.worker_rejection(self.iteration_worker("failed"), args, {"expected": True}, identity))
                other = self.iteration_worker(status, output, binding=self.identity(state="t"*64))
                self.assertEqual(C.worker_rejection(other, args, {"expected": True}, identity),
                                 "bound to a different state")
                metadata_only = self.scratch/f"declaration-{mode}"
                metadata_only.mkdir()
                (metadata_only/"force_model.json").write_text(json.dumps({"expected": True}))
                self.assertEqual(C.worker_rejection(metadata_only, args, {"expected": True}, identity),
                                 "required record missing: step.json")
        rejected = self.iteration_worker("trial_rejected", record={"cost_after": 2.})
        self.assertIsNone(C.worker_rejection(rejected, [C.ITER, "trial"], {"expected": True}, identity))
        converged = self.iteration_worker("converged", ("solution.npz", "solution_sha256"))
        self.assertIsNone(C.worker_rejection(converged, [C.ITER, "solve"], {"expected": True}, identity))
        wrong = self.iteration_worker("iteration_complete", ("solution.npz", "solution_sha256"))
        self.assertIn("does not complete", C.worker_rejection(wrong, [C.ITER, "solve"], {"expected": True}, identity))

    def rewrite(self, folder, name, writer, record="step.json", key=None):
        """Replace an output with `writer(path)` and refresh its recorded hash, as a malformed but consistent worker."""
        writer(folder/name)
        meta = json.loads((folder/record).read_text())
        meta[key] = sha(folder/name)
        (folder/record).write_text(json.dumps(meta))

    def test_unusable_arrays_with_matching_hashes_are_rejected(self):
        """Astra E-01: a hash-matching output must still open as the expected arrays with finite values."""
        rng = np.random.default_rng(9)
        good = dict(times=np.arange(3.), G01_states=rng.normal(size=(3, 6)), G01_stm=rng.normal(size=(3, 6, 6)),
                    G01_sensitivity=rng.normal(size=(3, 6, 5)))
        cases = {"plain text": lambda p: p.write_bytes(b"not an array archive"),
                 "object array": lambda p: np.savez(p, **dict(good, times=np.array([1., None, 2.], dtype=object))),
                 "missing member": lambda p: np.savez(p, **{k: v for k, v in good.items() if k != "G01_stm"}),
                 "incompatible shape": lambda p: np.savez(p, **dict(good, G01_states=rng.normal(size=(3, 5)))),
                 "non-finite values": lambda p: np.savez(p, **dict(good, G01_stm=np.full((3, 6, 6), np.nan)))}
        for label, writer in cases.items():
            with self.subTest(label):
                out = self.produced({"expected": True})
                self.rewrite(out, "trajectories.npz", writer, record="trajectories.json", key="cache_sha256")
                reason = C.worker_rejection(out, [C.TRAJ, "integrate"], {"expected": True}, self.identity())
                self.assertIsNotNone(reason)
                self.assertIn("trajectories.npz", reason)
        identity = self.identity(state="s"*64)
        solution = dict(x=rng.normal(size=5), names=np.array([f"p{i}" for i in range(5)]), states=rng.normal(size=(2, 3, 6)),
                        satellites=np.array(["G01", "G02"]), times_s=np.arange(3.), residual_m=rng.normal(size=4),
                        sigma_m=np.ones(4), retained_covariance=np.eye(2))
        bad_solutions = {"unrelated member only": lambda p: np.savez(p, unrelated=np.zeros(3)),
                         "names length": lambda p: np.savez(p, **dict(solution, names=np.array(["a"]))),
                         "non-finite x": lambda p: np.savez(p, **dict(solution, x=np.array([1., np.inf, 0., 0., 0.]))),
                         "plain text": lambda p: p.write_bytes(b"x")}
        for label, writer in bad_solutions.items():
            with self.subTest(label):
                out = self.iteration_worker("converged", ("solution.npz", "solution_sha256"))
                self.rewrite(out, "solution.npz", writer, key="solution_sha256")
                reason = C.worker_rejection(out, [C.ITER, "solve"], {"expected": True}, identity)
                self.assertIsNotNone(reason)
                self.assertIn("solution.npz", reason)
        state = self.iteration_worker("state_ready", ("state.json", "state_sha256"), binding={})
        (state/"state.json").write_text(json.dumps(dict(clock_seeds=[[[0, "A"], 1.]], windup=[0.], amb_origins={},
                                                        fixture_sha256=identity["fixture"], config_sha256=identity["config"])))
        self.rewrite(state, "state.json", lambda p: None, key="state_sha256")
        self.assertIsNone(C.worker_rejection(state, [C.ITER, "state"], {"expected": True}, identity))
        (state/"state.json").write_text('{"clock_seeds": [[[0, "A"], NaN]], "windup": [], "amb_origins": {}, '
                                        f'"fixture_sha256": "{identity["fixture"]}", "config_sha256": "{identity["config"]}"}}')
        self.rewrite(state, "state.json", lambda p: None, key="state_sha256")
        self.assertIn("not a usable state", C.worker_rejection(state, [C.ITER, "state"], {"expected": True}, identity))

    def test_every_worker_of_a_real_campaign_is_accepted(self):
        campaign = ROOT/"Opus_Fork/runs/20260929T233503Z-fit-U-elw13-0620"
        if not campaign.is_dir():
            self.skipTest("the Jun 20 untouched campaign is not present")
        report = json.loads((campaign/"validation.json").read_text())
        identity = dict(fixture=sha(ROOT/report["fixture"]), config=sha(ROOT/report["config"]))
        checked = 0
        for name, record in report["runs"].items():
            if record.get("status") != "ok":
                continue
            state = None if name == "state" or name.startswith("lin0-traj") else report["state"]["sha256"]
            with self.subTest(name):
                self.assertIsNone(C.worker_rejection(campaign/name, record["args"], report["force_model"],
                                                     dict(identity, state=state)))
                checked += 1
        self.assertGreater(checked, 10)

    def test_correct_binding_is_accepted(self):
        report = self.report()

        def runs(module_args, *rest, **kw):
            if module_args[0] == C.TRAJ:
                return {"status": "ok", "exit_code": 0}, self.produced({"expected": True})
            raise RuntimeError("synthetic stop at the state worker")
        with self.assertRaisesRegex(RuntimeError, "synthetic stop"):
            self.drive(report, runs)
        self.assertEqual(report["runs"]["lin0-traj-0"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
