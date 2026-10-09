"""Guarded independent sample/mapping/score and SVD stationarity audit."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5b_step import restore
from customkf.dynamic_observation import Trajectory
from claude.tools.dynamics_ceiling_step import BASE
from claude.tools.evaluate_ablation import Reference
from customkf.stage5_pilot import ORIGIN


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    folder = parser.parse_args().campaign
    manifest = json.loads((folder / "validation.json").read_text())
    for group in ("source_sha256", "report_sha256"):
        for name, digest in manifest[group].items():
            assert sha(ROOT / name) == digest, name
    context, _, _ = restore(BASE / "prepare/fixture.json")
    reference = Reference()
    results = {}
    for sat, name in manifest["completed"].items():
        path = folder / name
        report = json.loads((path / "diagnostic.json").read_text())
        assert manifest["runs"][name]["status"] == "ok"
        assert sha(path / "diagnostic_fit.npz") == report["solution_sha256"]
        assert reference.sha256 == report["reference_sha256"]
        fit = np.load(path / "diagnostic_fit.npz")
        np.testing.assert_array_equal(fit["train_indices"], np.arange(0, 13, 2))
        np.testing.assert_array_equal(fit["held_indices"], np.arange(1, 13, 2))
        np.testing.assert_array_equal(fit["times_s"], 10. + np.arange(13) * 900.)
        trajectory = Trajectory(fit["initial_state"], context["model"], context["duration_s"])
        np.testing.assert_array_equal(np.array([trajectory.state(t) for t in fit["times_s"]]), fit["states"])
        for i, t in enumerate(fit["times_s"]):
            raw = reference.raw.samples[(ORIGIN + int(round(float(t) * 1e9)), sat)]
            np.testing.assert_array_equal(fit["reference_ecef_m"][i], raw.xyz_m)
            rotation = reference.epoch.celestial_to_terrestrial(float(t))
            np.testing.assert_array_equal(fit["rotations"][i], rotation)
            np.testing.assert_allclose(fit["reference_inertial_m"][i], rotation.T @ raw.xyz_m, rtol=0, atol=1e-8)
        delta = fit["states"][:, :3] - fit["reference_inertial_m"]
        scores = {}
        for label, indices in (("train", fit["train_indices"]), ("held", fit["held_indices"]), ("all", np.arange(13))):
            rms = float(np.sqrt(np.sum(delta[indices]**2) / len(indices)))
            np.testing.assert_allclose(rms, report["fit"][label]["rms_3d_m"], rtol=0, atol=2e-8)
            scores[label] = rms
        train = fit["train_indices"]
        scales = np.array([100.] * 3 + [.01] * 3)
        design = np.array([trajectory.partial(t)[:3] for t in fit["times_s"][train]]).reshape(-1, 6) * scales
        step, _, rank, singular = np.linalg.lstsq(design, -delta[train].ravel(), rcond=1e-11)
        correction = step * scales
        bound = float(np.linalg.norm(correction[:3]) + context["duration_s"] * np.linalg.norm(correction[3:]))
        assert rank == 6 and bound < 1e-4
        results[sat] = {"independent_inertial_rms_m": scores, "svd_rank": int(rank),
                        "svd_condition": float(singular[0] / singular[-1]), "svd_step_bound_m": bound,
                        "reintegrated_states_bitwise_equal": True}
    result = {"status": "independent_fixed_force_fit_checks_pass_not_POD_accuracy_acceptance", "satellites": results,
              "review_source_sha256": sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"]) / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
