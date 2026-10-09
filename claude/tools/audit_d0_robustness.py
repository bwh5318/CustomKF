"""Astra's bounded archive audit of Opus's D0 robustness controls.

Run with existing Python through customkf.guard (120 second ceiling). Reads saved
arrays; does not repeat propagation or fit observations. Independently recomputes
the paired cold-start difference and each objective with its declared priors.
Historical campaigns are read-only. Output goes to CUSTOMKF_RUN_DIR.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "nominal": "20260912T145220Z-station-d0",
    "cold": "20260912T151932Z-station-d0-cold",
    "weak": "20260912T152819Z-station-d0-weak",
    "weak_cold": "20260912T153512Z-station-d0-weak-cold",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])
    results, arrays = {}, {}
    for label, name in CASES.items():
        folder = ROOT / "claude/runs" / name
        manifest_path = folder / "validation.json"
        m = json.loads(manifest_path.read_text())
        assert "complete_not_accuracy_acceptance" in m["status"]
        assert m["active_worker"] is None
        counts = {}
        for key, base in (("source_sha256", ROOT), ("report_sha256", ROOT),
                          ("artifacts_sha256", folder)):
            for path, expected in m[key].items():
                assert digest(base / path) == expected, (label, key, path)
            counts[key] = len(m[key])
        for run in m["runs"].values():
            assert run["status"] == "ok"
            assert run["minimum_system_available_gib"] >= 8
            assert run["windows_peak_job_memory_mib"] <= 2048
        final = folder / m["final"]
        step = json.loads((final / "step.json").read_text())
        assert step["status"] == "converged"
        assert digest(final / "solution.npz") == step["solution_sha256"]
        with np.load(final / "solution.npz") as z:
            a = {key: z[key].copy() for key in z.files}
        arrays[label] = a
        x = dict(zip(a["names"].astype(str), a["x"]))
        factor = 10 if label.startswith("weak") else 1
        prior_cost = 0.
        for n, v in x.items():
            if n.startswith("orbit:"):
                prior_cost += (v / (factor * (1000 if int(n.split(":")[-1]) < 3 else 1)))**2
        orbit_cost = prior_cost
        stations = sorted({n.split(":")[1] for n in x if n.startswith("wet:")})
        for s in stations:
            w0, w3, w6 = [x[f"wet:{s}:{t}"] for t in ("0", "1", "6h")]
            prior_cost += (w0/.3)**2 + (w3/.3)**2 + ((w3-w0)/.03)**2 + ((w6-w3)/.03)**2
        objective = float(np.sum((a["residual_m"] / a["sigma_m"])**2) + prior_cost)
        difference = objective - step["history"][-1]["cost_after"]
        assert abs(difference) < 2e-8
        for trial_name in m["accepted_trials"]:
            iteration = trial_name.split("-")[1]
            with np.load(folder / f"linear-{iteration}/direction.npz") as d:
                with np.load(folder / trial_name / "solution.npz") as t:
                    # All four archived campaigns used a single full step.
                    np.testing.assert_array_equal(t["x"], d["x"] + d["step"])
        if m["accepted_trials"]:
            with np.load(folder / m["accepted_trials"][-1] / "solution.npz") as t:
                for key in ("x", "states", "residual_m", "sigma_m"):
                    np.testing.assert_array_equal(a[key], t[key])
        results[label] = {"manifest_sha256": digest(manifest_path), "pins_verified": counts,
                          "objective": objective, "objective_difference": difference,
                          "orbit_prior_cost": orbit_cost, "accepted_trials": m["accepted_trials"],
                          "guarded_seconds": m["total_guarded_seconds"],
                          "peak_job_memory_mib": m["peak_job_memory_mib"],
                          "minimum_available_gib": m["minimum_system_available_gib"]}
    comparisons = {}
    for left, right in (("cold", "nominal"), ("weak", "nominal"),
                        ("weak_cold", "nominal"), ("weak_cold", "cold")):
        a, b = arrays[left], arrays[right]
        for key in ("names", "satellites", "times_s", "sigma_m"):
            np.testing.assert_array_equal(a[key], b[key])
        position = float(np.linalg.norm(a["states"][:, :, :3]-b["states"][:, :, :3], axis=2).max())
        mask = np.char.startswith(a["names"].astype(str), "srpD0:")
        coefficient = float(np.max(np.abs(a["x"][mask]-b["x"][mask])) * 1e-7)
        assert position < .001 and coefficient < 1e-10
        comparisons[f"{left}_vs_{right}"] = {"max_position_m": position, "max_D0_mps2": coefficient}
    report = {"status": "d0_robustness_archive_audit_pass_not_accuracy_acceptance",
              "scope": "hashes, saved arrays, full-step lineage, declared-prior objective; no fresh propagation",
              "source_sha256": digest(Path(__file__)), "cases": results, "comparisons": comparisons}
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
