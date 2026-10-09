"""Gradient experiment, Stage 2 analysis (PROTOCOL.md: lin0 control, calibration C3/C2', oracle scoring).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 900 -- \
        Opus_Fork.experiments.gradients.analyze

Reads the completed campaigns, the Stage 1 result and the production evaluation (`arm_gradients_aug3.json`); writes
`gradients_analysis.json` in the run folder. No fit, no integration.
"""
import json
from pathlib import Path

import numpy as np

from Opus_Fork.experiments.transfer.common import run_dir, sha
from Opus_Fork.paths import ROOT
from validation.oracle import frame as O2, metrics as O1

R = ROOT/"Opus_Fork/runs"
ARMS = {"G-op-e13": ("20261001T210829Z-fit-G-op-e13", "20260927T163208Z-fit-E-elw13-3", "elw13", "grad_op"),
        "G-gpt3-e13": ("20261001T231310Z-fit-G-gpt3-e13", "20260927T163208Z-fit-E-elw13-3", "elw13", "gpt3"),
        "G-op-sd3": ("20261001T220848Z-fit-G-op-sd3", "20260925T215927Z-fit-SD-3-25st", "sd3", "grad_op")}
STAGE1 = ROOT/"runs/20261001T210618Z-e1848ce0"
EVALUATION = R/"20261002T133540Z-eval-grad-3/arm_gradients_aug3.json"
IGS_FINAL = Path(r"E:\pythontests\autocomparesp3\data\sp3_cache\IGS0OPSFIN_20262150000_01D_15M_ORB.SP3")
FIXTURE = R/"20260922T225652Z-prepare-2026-08-03/fixture.json"


def solution(campaign):
    v = json.loads((R/campaign/"validation.json").read_text())
    path = R/campaign/v["final"]/"solution.npz"
    step = json.loads((path.parent/"step.json").read_text())
    assert step["status"] == "converged" and sha(path) == step["solution_sha256"]
    with np.load(path) as f:
        return dict(states=f["states"].copy(), sats=[str(s) for s in f["satellites"]], times=f["times_s"].copy(),
                    path=str(path), sha256=sha(path), force_model=json.loads((path.parent/"force_model.json").read_text()))


def lin0_control(arm, comparator):
    out = {}
    for g in (0, 1):
        with np.load(R/arm/f"lin0-traj-{g}/trajectories.npz") as a, np.load(R/comparator/f"lin0-traj-{g}/trajectories.npz") as b:
            names = sorted(a.files)
            out[f"group{g}"] = dict(members=len(names), same_members=names == sorted(b.files),
                                    bitwise=bool(names == sorted(b.files) and all(np.array_equal(a[k], b[k]) for k in names)))
    return out


def rac_components(states, delta):
    r, v = states[..., :3], states[..., 3:6]
    radial = r/np.linalg.norm(r, axis=-1, keepdims=True)
    normal = np.cross(r, v)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    along = np.cross(normal, radial)
    return [np.einsum("stj,stj->st", ax, delta) for ax in (radial, along, normal)]


def main():
    folder = run_dir()
    stage1 = json.loads((STAGE1/"gradients_linear.json").read_text())
    evaluation = json.loads(EVALUATION.read_text())
    finals = O2.Finals(ROOT/"data/stage2/finals2000A.all")
    frame = O2.Frame(finals, subdaily=True)
    reference = O1.read_sp3(IGS_FINAL)
    origin = int(json.loads(FIXTURE.read_text())["context"]["origin_ns"])
    report = dict(stage1_json_sha256=sha(STAGE1/"gradients_linear.json"), evaluation_sha256=sha(EVALUATION),
                  igs_final_sha256=sha(IGS_FINAL), arms={})
    with np.load(STAGE1/"gradients_linear.npz") as f:
        predicted = {k: f[k].copy() for k in f.files if "_dr_" in k}
    keys = None
    scored = {}
    for name, (arm, comparator, weights, source) in ARMS.items():
        new, base = solution(arm), solution(comparator)
        assert new["sats"] == base["sats"] and np.array_equal(new["times"], base["times"])
        assert new["force_model"]["gradients"]["source"] == source and "gradients" not in base["force_model"]
        actual = new["states"][:, :, :3]-base["states"][:, :, :3]
        pred = predicted[f"{weights}_dr_{source}"]
        resid = actual-pred
        rms = lambda a: float(np.sqrt(np.mean(np.sum(a**2, axis=-1))))
        r_act, a_act, c_act = rac_components(base["states"], actual)
        r_pre, a_pre, c_pre = rac_components(base["states"], pred)
        corr = {lab: float(np.corrcoef(x.ravel(), y.ravel())[0, 1]) for lab, x, y in
                (("radial", r_act, r_pre), ("along", a_act, a_pre), ("cross", c_act, c_pre))}
        c3 = rms(resid)/rms(actual)
        entry = dict(campaign=arm, comparator=comparator, solution_sha256=new["sha256"],
                     lin0_control=lin0_control(arm, comparator),
                     actual_change_rms3d_cm=rms(actual)*100, predicted_change_rms3d_cm=rms(pred)*100,
                     residual_rms3d_cm=rms(resid)*100, C3_ratio=c3, component_correlation=corr,
                     role="calibration (primary, PROTOCOL Stage 2)" if name == "G-op-sd3" else "descriptive (elw13 weights)")
        if name == "G-op-sd3":
            entry.update(C3_pass=bool(c3 <= 0.30), C2_along_pass=bool(corr["along"] >= 0.80))
        for label, data in ((name, new), (comparator, base)):
            if label in scored:
                continue
            ecef = O1.solution_ecef(data["states"][:, :, :3], data["sats"], data["times"], origin, frame)
            if keys is None:
                start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
                keys = {k for k in set(reference) & set(ecef) if start <= k[1] <= stop}
            scored[label] = O1.summarize(reference, ecef, frame, keys)
        report["arms"][name] = entry
    full = evaluation["domains"]["full"]["arms"]
    production_names = {"G-op-e13": "G-op-e13", "G-gpt3-e13": "G-gpt3-e13", "G-op-sd3": "G-op-sd3",
                        "20260927T163208Z-fit-E-elw13-3": "elw13", "20260925T215927Z-fit-SD-3-25st": "SD"}
    report["oracle_vs_production"] = {
        label: dict(oracle_ure_m=v["orbit_ure_m"], production_ure_m=full[production_names[label]]["raw"]["rms_orbit_ure_m"],
                    oracle_3d_m=v["rms_3d_m"], production_3d_m=full[production_names[label]]["raw"]["rms_3d_m"],
                    samples=v["samples"], production_samples=full[production_names[label]]["raw"]["samples"])
        for label, v in scored.items()}
    for name, (arm, comparator, weights, source) in ARMS.items():
        o_new, o_base = scored[name], scored[comparator]
        report["arms"][name]["oracle_ure_change_pct"] = 100*(o_new["orbit_ure_m"]/o_base["orbit_ure_m"]-1)
        report["arms"][name]["oracle_3d_change_pct"] = 100*(o_new["rms_3d_m"]/o_base["rms_3d_m"]-1)
        report["arms"][name]["stage1_predicted_ure_change_pct"] = stage1["arms"][weights]["fields"][source]["predicted_ure_change_pct"]
    (folder/"gradients_analysis.json").write_text(json.dumps(report, indent=1)+"\n")
    print(json.dumps({n: {k: v for k, v in e.items() if k in ("lin0_control", "C3_ratio", "component_correlation",
                                                              "oracle_ure_change_pct", "stage1_predicted_ure_change_pct",
                                                              "actual_change_rms3d_cm", "residual_rms3d_cm")}
                      for n, e in report["arms"].items()}, indent=1))
    print(json.dumps(report["oracle_vs_production"], indent=1))


if __name__ == "__main__":
    main()
