"""score_networks.py (PROTOCOL.md amendments A3 and A4, Astra N2 and NR-03): preflight of the frozen index and the
force-model sidecar, and acceptance of fresh, provenance-bound evaluations only. Synthetic campaign trees in
temporary folders.

    C:\\anaconda\\python.exe -m unittest tests.test_networks_scoring_wrapper -v
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from Opus_Fork.experiments.networks import score_networks as S


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model(arm):
    out = dict(variant="v", nongrav_sha256="n")
    if arm != "U":
        out["gradients"] = dict(source="grad_op", module_sha256="m", inputs={"a.grad_g": "1"})
    return out


class Wrapper(unittest.TestCase):
    """score_networks preflight and output acceptance, on a fake campaign tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = dict(dates={"2026-06-06": {arm: self.campaign(arm) for arm in S.ARMS}})
        self.models = dict(dates={"2026-06-06": {arm: dict(sha256=self.pin(arm)) for arm in S.ARMS}})

    def tearDown(self):
        self.tmp.cleanup()

    def folder(self, arm):
        return self.root/self.index["dates"]["2026-06-06"][arm]["campaign"]

    def pin(self, arm):
        return json.loads((self.folder(arm)/"validation.json").read_text())["artifacts_sha256"]["lin2-solve/force_model.json"]

    def campaign(self, arm, name=None):
        name = name or f"20261001T000000Z-fit-{arm}-0606"
        folder = self.root/"runs"/name
        (folder/"lin2-solve").mkdir(parents=True)
        fixture = self.root/"fx"/arm/"fixture.json"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(json.dumps(dict(arm=arm)))
        solution = folder/"lin2-solve/solution.npz"
        solution.write_bytes(arm.encode())
        (folder/"lin2-solve/force_model.json").write_text(json.dumps(model(arm)))
        (folder/"lin2-solve/step.json").write_text(json.dumps(dict(status="converged", solution_sha256=digest(solution),
                                                                   binding=dict(fixture=digest(fixture)))))
        (folder/"validation.json").write_text(json.dumps(dict(
            status="long_fit_complete_not_accuracy_acceptance", label=f"{arm}-0606", final="lin2-solve",
            force_model=model(arm), artifacts_sha256={"lin2-solve/force_model.json":
                                                      digest(folder/"lin2-solve/force_model.json")})))
        return dict(campaign=f"runs/{name}", label=f"{arm}-0606", final="lin2-solve", solution_sha256=digest(solution),
                    fixture=f"fx/{arm}/fixture.json", fixture_sha256=digest(fixture))

    def preflight(self):
        return S.preflight(self.index, self.models, self.root)

    def test_complete_index_passes(self):
        self.assertEqual(self.preflight(), ([], {}))

    def test_missing_final_refused(self):
        os.remove(self.folder("S17-op")/"lin2-solve/solution.npz")
        problems, _ = self.preflight()
        self.assertTrue(any("S17-op" in p and "missing" in p for p in problems))

    def test_incomplete_or_changed_campaign_refused(self):
        record = self.folder("U")/"validation.json"
        record.write_text(json.dumps(dict(json.loads(record.read_text()), status="failed")))
        (self.folder("V-op")/"lin2-solve/solution.npz").write_bytes(b"other")
        problems, _ = self.preflight()
        self.assertTrue(any(p.startswith("2026-06-06 U") for p in problems))
        self.assertTrue(any(p.startswith("2026-06-06 V-op") for p in problems))

    def test_newer_duplicate_label_is_recorded_not_used(self):
        self.campaign("S50-op", name="20261009T000000Z-fit-S50-op-0606")             # sorts after the indexed one
        problems, duplicates = self.preflight()
        self.assertEqual(problems, [])
        self.assertEqual(duplicates, {"2026-06-06 S50-op": ["20261009T000000Z-fit-S50-op-0606"]})

    def test_single_model_file_changed_in_a_normalized_field_refused(self):
        """NR-03: a gradient input list differs only in a field A2 normalizes between campaigns; the campaign's own
        record and pin are unchanged, so the file is refused."""
        path = self.folder("S17-op")/"lin2-solve/force_model.json"
        changed = model("S17-op")
        changed["gradients"]["inputs"] = {"foreign.grad_g": "0"*64}
        path.write_text(json.dumps(changed))
        problems, _ = self.preflight()
        self.assertTrue(any(p.startswith("2026-06-06 S17-op") and "force model" in p for p in problems))
        self.assertFalse(any(p.startswith("2026-06-06 V-op") for p in problems))

    def test_coherent_all_arm_model_change_refused(self):
        """NR-03: every arm's model changed identically still differs from each unchanged campaign record."""
        for arm in S.ARMS:
            path = self.folder(arm)/"lin2-solve/force_model.json"
            path.write_text(json.dumps(dict(model(arm), nongrav_sha256="changed")))
        problems, _ = self.preflight()
        for arm in S.ARMS:
            self.assertTrue(any(p.startswith(f"2026-06-06 {arm}:") and "force model" in p for p in problems), arm)

    def test_sidecar_disagreement_refused(self):
        self.models["dates"]["2026-06-06"]["U"]["sha256"] = "0"*64
        problems, _ = self.preflight()
        self.assertTrue(any(p.startswith("2026-06-06 U") and "sidecar" in p for p in problems))

    def evaluation_files(self, results, guard, provenance_arms=None, model_sha=None):
        arms = self.index["dates"]["2026-06-06"]
        provenance = {a: dict(sha256=arms[a]["solution_sha256"], fixture_sha256=arms[a]["fixture_sha256"],
                              force_model_sha256=model_sha or self.pin(a))
                      for a in (provenance_arms or S.ARMS)}
        provenance["NGA"] = {}
        text = json.dumps(dict(day="2026-06-06", status="evaluation_not_accuracy_acceptance", provenance=provenance,
                               common_key_digest="d"))
        guard.mkdir(parents=True, exist_ok=True)
        results.mkdir(parents=True, exist_ok=True)
        (guard/"networks_20260606.json").write_text(text)
        (results/"networks_20260606.json").write_text(text)

    def accept(self, code, guard, started, results):
        return S.accept_evaluation(code, guard, "2026-06-06", self.index["dates"]["2026-06-06"], started,
                                   self.models["dates"]["2026-06-06"], results)

    def test_fresh_bound_output_accepted(self):
        results, guard = self.root/"results", self.root/"guard"
        self.evaluation_files(results, guard)
        self.assertEqual(self.accept(0, guard, time.time()-5, results)[1], [])

    def test_refusal_and_missing_run_folder_refused(self):
        results, guard = self.root/"results", self.root/"guard"
        self.evaluation_files(results, guard)
        self.assertIn("guard exit status 126", self.accept(126, guard, 0, results)[1])
        self.assertTrue(self.accept(0, None, 0, results)[1])

    def test_stale_output_refused(self):
        results, guard = self.root/"results", self.root/"guard"
        results.mkdir()
        (results/"networks_20260606.json").write_text("{}")                          # an older evaluation only
        self.assertTrue(self.accept(0, guard, 0, results)[1])
        self.evaluation_files(results, guard)
        self.assertIn("output predates this run", self.accept(0, guard, time.time()+60, results)[1])
        (results/"networks_20260606.json").write_text("{}")                          # results copy not this run's
        self.assertIn("the results copy is not this run's output", self.accept(0, guard, 0, results)[1])

    def test_unbound_provenance_refused(self):
        results, guard = self.root/"results", self.root/"guard"
        self.evaluation_files(results, guard, provenance_arms=("U", "V-op", "S17-op"))
        self.assertTrue(any(p.startswith("S50-op") for p in self.accept(0, guard, 0, results)[1]))

    def test_evaluated_force_model_mismatch_refused(self):
        results, guard = self.root/"results", self.root/"guard"
        self.evaluation_files(results, guard, model_sha="0"*64)
        problems = self.accept(0, guard, 0, results)[1]
        self.assertEqual(sum("force model" in p for p in problems), len(S.ARMS))


if __name__ == "__main__":
    unittest.main()
