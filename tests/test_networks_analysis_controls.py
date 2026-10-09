"""analyze_networks.py controls (PROTOCOL.md amendment A3, Astra N1, N4): force-model, reference, population and
oracle-reproduction checks with their negative controls, and the S50 category boundaries. Synthetic inputs only.

    C:\\anaconda\\python.exe -m unittest tests.test_networks_analysis_controls -v
"""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from Opus_Fork.experiments.gradients.analyze_validation import SCORE_TOL_M, key_digest
from Opus_Fork.experiments.networks import analyze_networks as A


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def models():
    base = dict(variant=A.VARIANT, subdaily_eop="IERS 2010", elev_sha256="e2", nongrav_sha256="n")
    gradients = dict(source="grad_op", convention="c", module_sha256="m", inputs={"a": "1"})
    out = {"U": dict(base, elev_sha256="e1")}
    for arm in A.GRADIENT_ARMS:
        out[arm] = dict(base, gradients=dict(gradients))
    out["S17-op"]["gradients"].update(module_sha256="m2", inputs={"b": "2"})       # normalized, as in A2
    return out


class ForceModels(unittest.TestCase):
    def test_designed_differences_pass(self):
        self.assertEqual(A.check_force_models(models()), [])

    def test_changed_force_model_fails(self):
        for arm, field, value in (("S50-op", "nongrav_sha256", "x"), ("V-op", "variant", "other"),
                                  ("U", "nongrav_sha256", "x"), ("S17-op", "subdaily_eop", None)):
            m = models()
            m[arm][field] = value
            self.assertTrue(A.check_force_models(m), (arm, field))

    def test_gradient_source_and_u_gradients_fail(self):
        m = models()
        m["S17-op"]["gradients"]["source"] = "gpt3"
        self.assertTrue(A.check_force_models(m))
        m = models()
        m["U"]["gradients"] = m["V-op"]["gradients"]
        self.assertTrue(A.check_force_models(m))


class Scores(unittest.TestCase):
    production = dict(raw=dict(samples=4, rms_orbit_ure_m=0.05, rms_3d_m=0.1, rms_rac_m=[0.03, 0.08, 0.05]),
                      per_satellite={"G01": dict(samples=2, rms_3d_m=0.09), "G02": dict(samples=2, rms_3d_m=0.11)})
    oracle = dict(samples=4, orbit_ure_m=0.05, rms_3d_m=0.1, rms_rac_m=[0.03, 0.08, 0.05])
    each = {"G01": dict(samples=2, rms_3d_m=0.09), "G02": dict(samples=2, rms_3d_m=0.11)}

    def test_reproduction_passes(self):
        self.assertEqual(A.score_difference(self.production, self.oracle, self.each), (0.0, True, []))

    def test_changed_nga_score_fails(self):
        changed = copy.deepcopy(self.production)
        changed["raw"]["rms_orbit_ure_m"] += 1e-3
        diff, _, _ = A.score_difference(changed, self.oracle, self.each)
        self.assertGreater(diff, SCORE_TOL_M)

    def assert_refused(self, production, oracle, each):
        diff, equal, problems = A.score_difference(production, oracle, each)
        self.assertTrue(problems)
        self.assertFalse(diff <= SCORE_TOL_M and equal)

    def test_malformed_metrics_refused_on_either_side(self):
        """Astra NR-02: NaN, Infinity, negative, missing or extra R/A/C entries, bad counts and membership."""
        cases = []
        for bad in (float("nan"), float("inf"), -0.01, None, True):
            cases.append(lambda p, o, e, bad=bad: p["raw"]["rms_rac_m"].__setitem__(2, bad))
            cases.append(lambda p, o, e, bad=bad: o["rms_rac_m"].__setitem__(0, bad))
            cases.append(lambda p, o, e, bad=bad: p["per_satellite"]["G02"].__setitem__("rms_3d_m", bad))
            cases.append(lambda p, o, e, bad=bad: e["G01"].__setitem__("rms_3d_m", bad))
            cases.append(lambda p, o, e, bad=bad: p["raw"].__setitem__("rms_orbit_ure_m", bad))
            cases.append(lambda p, o, e, bad=bad: o.__setitem__("rms_3d_m", bad))
        cases += [lambda p, o, e: p["raw"].__setitem__("rms_rac_m", [0.03]),
                  lambda p, o, e: o.__setitem__("rms_rac_m", [0.03, 0.08, 0.05, 0.0]),
                  lambda p, o, e: p["raw"].pop("rms_rac_m"),
                  lambda p, o, e: p["raw"].__setitem__("samples", 0),
                  lambda p, o, e: o.__setitem__("samples", 4.0),
                  lambda p, o, e: e["G02"].__setitem__("samples", -2),
                  lambda p, o, e: e.pop("G02"),
                  lambda p, o, e: p["per_satellite"].__setitem__("G03", dict(samples=2, rms_3d_m=0.1))]
        for k, modify in enumerate(cases):
            p, o, e = copy.deepcopy(self.production), copy.deepcopy(self.oracle), copy.deepcopy(self.each)
            modify(p, o, e)
            with self.subTest(case=k):
                self.assert_refused(p, o, e)

    def test_changed_component_or_satellite_fails(self):
        changed = copy.deepcopy(self.production)
        changed["raw"]["rms_rac_m"][2] += 1e-3
        self.assertGreater(A.score_difference(changed, self.oracle, self.each)[0], SCORE_TOL_M)
        changed = copy.deepcopy(self.production)
        changed["per_satellite"]["G02"]["rms_3d_m"] += 1e-3
        self.assertGreater(A.score_difference(changed, self.oracle, self.each)[0], SCORE_TOL_M)

    def test_sample_mismatch_fails(self):
        changed = copy.deepcopy(self.production)
        changed["per_satellite"]["G02"]["samples"] = 3
        self.assertFalse(A.score_difference(changed, self.oracle, self.each)[1])


class Population(unittest.TestCase):
    keys = {("G01", 0), ("G01", 900), ("G02", 0)}

    def evaluation(self, keys):
        return dict(satellites=sorted({s for s, _ in keys}),
                    domains=dict(full=dict(samples=len(keys), key_digest=key_digest(keys))))

    def test_same_population_passes(self):
        self.assertEqual(A.check_population(self.keys, self.evaluation(self.keys)), [])

    def test_same_count_different_keys_fail(self):
        other = {("G01", 0), ("G01", 1800), ("G02", 0)}
        self.assertTrue(A.check_population(other, self.evaluation(self.keys)))


class References(unittest.TestCase):
    def test_changed_reference_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            igs, nga = Path(tmp)/"igs.sp3", Path(tmp)/"nga.sp3"
            igs.write_text("igs")
            nga.write_text("nga")
            evaluation = dict(day="2026-06-06", provenance=dict(igs_final=dict(path=str(igs), sha256=digest(igs)),
                                                                NGA=dict(path=str(nga), sha256=digest(nga))))
            store = {"reference_igs_final": digest(igs), "reference_nga_pe": digest(nga)}
            find = lambda role, day: (None, dict(sha256=store[role]))
            self.assertEqual(A.check_references(evaluation, find), [])
            igs.write_text("changed")
            self.assertTrue(A.check_references(evaluation, find))
            igs.write_text("igs")
            store["reference_nga_pe"] = "0"*64                                    # store holds another NGA file
            self.assertTrue(A.check_references(evaluation, find))


class S50Categories(unittest.TestCase):
    def test_boundaries_follow_a3(self):
        self.assertEqual(A.s50_reading([-1.0]*5), "improves")
        self.assertEqual(A.s50_reading([-2.0, -2.0, -2.0, -2.0, 3.0]), "improves")           # mean -1.0, 4 better
        self.assertEqual(A.s50_reading([-3.0, -3.0, -3.0, 2.0, 2.0]), "mixed")             # mean -1.0, 3 better
        self.assertEqual(A.s50_reading([-0.999]*5), "no material change")
        self.assertEqual(A.s50_reading([0.999]*5), "no material change")
        self.assertEqual(A.s50_reading([1.0]*5), "worse")


if __name__ == "__main__":
    unittest.main()
