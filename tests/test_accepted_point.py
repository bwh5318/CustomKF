"""Accepted, identity-bound previous points and directions (Sol review SOL-05; claude.roadmap.traj_cache.accepted_point).

    C:\\anaconda\\python.exe -m unittest tests.test_accepted_point -v

Uses one completed untouched-date campaign's saved trial/solve records read-only (copies are made for the
negative cases); no fixture is restored and no orbit is integrated.
"""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.traj_cache import accepted_point
from Opus_Fork import iteration

CAMPAIGN = ROOT/"Opus_Fork/runs/20260929T233503Z-fit-U-elw13-0620"
TRIAL, LINEAR = CAMPAIGN/"lin0-trial-0", CAMPAIGN/"lin0-solve"


@unittest.skipUnless(TRIAL.is_dir() and LINEAR.is_dir(), "the Jun 20 untouched campaign is not present")
class AcceptedPoint(unittest.TestCase):
    def setUp(self):
        self.step = json.loads((TRIAL/"step.json").read_text())
        self.binding = {k: self.step["binding"][k] for k in ("fixture", "config", "state")}
        with np.load(TRIAL/"solution.npz") as saved:
            self.names = [str(n) for n in saved["names"]]
            self.former_x = saved["x"].copy()
        self.model = json.loads((TRIAL/"force_model.json").read_text())
        self.tmp = Path(tempfile.mkdtemp(prefix="accepted-point-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def copy(self, source, mutate_step=None, mutate_arrays=None):
        target = self.tmp/source.name
        shutil.copytree(source, target, ignore=lambda d, names: [n for n in names if n not in ("step.json", "solution.npz", "direction.npz", "force_model.json")])
        npz = "solution.npz" if (target/"solution.npz").exists() else "direction.npz"
        if mutate_arrays:
            with np.load(target/npz) as saved:
                arrays = {k: saved[k] for k in saved.files}
            mutate_arrays(arrays)
            np.savez(target/npz, **arrays)
        step = json.loads((target/"step.json").read_text())
        step["solution_sha256" if npz == "solution.npz" else "direction_sha256"] = sha(target/npz)
        if mutate_step:
            mutate_step(step)
        (target/"step.json").write_text(json.dumps(step))
        return target

    def test_accepted_trial_loads_bitwise_as_before(self):
        x, history = accepted_point(TRIAL, self.names, self.binding, force_model=self.model)
        self.assertTrue(np.array_equal(x, self.former_x))
        self.assertEqual(history, self.step["history"])

    def test_direction_combines_exactly_as_before(self):
        lin = json.loads((LINEAR/"step.json").read_text())
        binding = {k: lin["binding"][k] for k in ("fixture", "config", "state")}
        with np.load(LINEAR/"direction.npz") as saved:
            former = saved["x"]+0.5*saved["step"]
        x, _ = accepted_point(LINEAR, self.names, binding, force_model=self.model, alpha=0.5)
        self.assertTrue(np.array_equal(x, former))

    def test_rejected_or_unaccepted_status_refused(self):
        rejected = self.copy(TRIAL, mutate_step=lambda s: s.update(status="trial_rejected"))
        with self.assertRaisesRegex(ValueError, "not an accepted point"):
            accepted_point(rejected, self.names, self.binding, force_model=self.model)

    def test_foreign_binding_refused(self):
        for key in ("fixture", "config", "state"):
            with self.subTest(key):
                with self.assertRaisesRegex(ValueError, f"different {key}"):
                    accepted_point(TRIAL, self.names, dict(self.binding, **{key: "0"*64}), force_model=self.model)

    def test_tampered_file_refused(self):
        target = self.copy(TRIAL)
        (target/"solution.npz").write_bytes((target/"solution.npz").read_bytes()+b"x")
        with self.assertRaisesRegex(ValueError, "recorded hash"):
            accepted_point(target, self.names, self.binding, force_model=self.model)

    def test_nonfinite_or_wrong_length_refused(self):
        def nan(arrays):
            arrays["x"] = arrays["x"].copy()
            arrays["x"][0] = np.nan
        target = self.copy(TRIAL, mutate_arrays=nan)
        with self.assertRaisesRegex(ValueError, "finite vector"):
            accepted_point(target, self.names, self.binding, force_model=self.model)

    def test_different_names_refused(self):
        with self.assertRaisesRegex(ValueError, "names or order"):
            accepted_point(TRIAL, list(reversed(self.names)), self.binding, force_model=self.model)


    # ----- Astra AR-01 ------------------------------------------------------------------------------------------
    def test_foreign_or_missing_force_model_refused(self):
        foreign = dict(self.model, variant="erp+thrust+iiia2600+sdeop+cut15s")
        with self.assertRaisesRegex(ValueError, "different force model"):
            accepted_point(TRIAL, self.names, self.binding, force_model=foreign)
        undeclared = self.copy(TRIAL)
        (undeclared/"force_model.json").unlink()
        with self.assertRaisesRegex(ValueError, "no force-model declaration"):
            accepted_point(undeclared, self.names, self.binding, force_model=self.model)
        with self.assertRaisesRegex(ValueError, "bare roadmap model"):
            accepted_point(TRIAL, self.names, self.binding, force_model=None)
        with self.assertRaises(TypeError):                  # the identity is keyword-only and has no default
            accepted_point(TRIAL, self.names, self.binding)

    def test_incomplete_identity_refused_even_when_both_sides_are_empty(self):
        empty = self.copy(TRIAL, mutate_step=lambda s: s.update(binding={}))
        for binding in ({}, dict(self.binding, state=None), dict(self.binding, config="")):
            with self.subTest(binding=binding), self.assertRaisesRegex(ValueError, "identity is incomplete"):
                accepted_point(empty, self.names, binding, force_model=self.model)

    def test_nonfinite_step_fraction_or_combination_refused(self):
        lin = json.loads((LINEAR/"step.json").read_text())
        binding = {k: lin["binding"][k] for k in ("fixture", "config", "state")}
        for alpha in (float("inf"), float("nan"), True, "0.5"):
            with self.subTest(alpha=alpha), self.assertRaisesRegex(ValueError, "not a finite number"):
                accepted_point(LINEAR, self.names, binding, force_model=self.model, alpha=alpha)

        def huge(arrays):
            arrays["step"] = np.full_like(arrays["step"], 1e308)
        target = self.copy(LINEAR, mutate_arrays=huge)
        with self.assertRaisesRegex(ValueError, "not finite"):
            accepted_point(target, self.names, binding, force_model=self.model, alpha=10.)

    def test_worker_point_uses_the_installed_model_identity(self):
        validation = json.loads((CAMPAIGN/"validation.json").read_text())
        args = NS(previous=TRIAL, fixture=ROOT/validation["fixture"], config=ROOT/validation["config"],
                  state=CAMPAIGN/"state/state.json")
        pilot = NS(names=self.names)
        with patch.object(iteration, "MODEL_IDENTITY", lambda: self.model):
            x, _ = iteration.point(args, pilot)
        self.assertTrue(np.array_equal(x, self.former_x))
        with patch.object(iteration, "MODEL_IDENTITY", lambda: dict(self.model, variant="other")):
            with self.assertRaisesRegex(ValueError, "different force model"):
                iteration.point(args, pilot)
        with patch.object(iteration, "MODEL_IDENTITY", None), self.assertRaisesRegex(ValueError, "bare roadmap"):
            iteration.point(args, pilot)

    def test_installer_binds_the_identity_resolved_at_call_time(self):
        from Opus_Fork import ngv_pilot
        with patch.multiple(iteration, LongPilot=iteration.LongPilot, cached_products=iteration.cached_products,
                            MODEL_IDENTITY=None), patch.object(ngv_pilot, "model_binding", lambda: {"first": 1}):
            ngv_pilot.install()
            with patch.object(ngv_pilot, "model_binding", lambda: {"later": 2}):
                self.assertEqual(iteration.MODEL_IDENTITY(), {"later": 2})


if __name__ == "__main__":
    unittest.main()
