"""New-date test, amendment A1: the matched gradient contrast on 2026-06-27 (N-op against U), written before U existed.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.gradients.analyze_newdate_matched

Run after `finish_newdate_matched.sh` has written `Opus_Fork/results/newdate_matched_20260627.json`.
- C1: the lin0 trajectory arrays of both arms are bitwise equal;
- C2: oracle scores (validation.oracle, sub-daily frame) for both arms within 0.1 mm of production, on identical
  samples;
- the A1 reading: URE change, the worst satellite 3D increase and the radial change;
- descriptive scores of both arms against NGA PE.

Writes `newdate_matched_analysis.json` in the run folder. No fit, no integration.
"""
import json

import numpy as np

from Opus_Fork.experiments.gradients.analyze_validation import (HERE, ROOT, SCORE_TOL_M, campaign, final_solution,
                                                                lin0_control)
from Opus_Fork.experiments.transfer.common import run_dir, sha
from validation.oracle import frame as O2, metrics as O1

DAY, TAG, FIXTURE_DIR = "2026-06-27", "0627", "runs/20261004T151035Z-0225f559"
ARMS = {"U": f"U-elw13-{TAG}", "N-op": f"N-op-{TAG}"}


def main():
    folder = run_dir()
    evaluation_path = ROOT/"Opus_Fork/results/newdate_matched_20260627.json"
    evaluation = json.loads(evaluation_path.read_text())
    arms = evaluation["domains"]["full"]["arms"]
    origin = int(json.loads((ROOT/FIXTURE_DIR/"fixture.json").read_text())["context"]["origin_ns"])
    frame = O2.Frame(O2.Finals(ROOT/"data/stage2/finals2000A.all"), subdaily=True)
    reference = O1.read_sp3(evaluation["provenance"]["igs_final"]["path"])
    start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
    report = dict(protocol_sha256=sha(HERE/"NEW_DATE_PROTOCOL.md"), day=DAY, evaluation_sha256=sha(evaluation_path),
                  arms={})
    folders, oracle, keys = {}, {}, None
    for name, label in ARMS.items():
        folders[name] = campaign(label)
        fit = final_solution(folders[name])
        source = (fit["force_model"].get("gradients") or {}).get("source", "none")
        assert source == ("grad_op" if name == "N-op" else "none"), (name, source)
        ecef = O1.solution_ecef(fit["states"], fit["sats"], fit["times"], origin, frame)
        keys = {k for k in set(reference) & set(ecef) if start <= k[1] <= stop} if keys is None else keys
        oracle[name] = O1.summarize(reference, ecef, frame, keys)
        raw = arms[name]["raw"]
        report["arms"][name] = dict(campaign=folders[name].name, final=fit["final"], gradients=source,
                                    ure_cm=raw["rms_orbit_ure_m"]*100, d3_cm=raw["rms_3d_m"]*100,
                                    rac_cm=[x*100 for x in raw["rms_rac_m"]],
                                    ure_ratio_to_nga=raw["rms_orbit_ure_m"]/arms["NGA"]["raw"]["rms_orbit_ure_m"],
                                    d3_ratio_to_nga=raw["rms_3d_m"]/arms["NGA"]["raw"]["rms_3d_m"],
                                    oracle_difference_m=max(abs(oracle[name]["orbit_ure_m"]-raw["rms_orbit_ure_m"]),
                                                            abs(oracle[name]["rms_3d_m"]-raw["rms_3d_m"])),
                                    oracle_samples_equal=oracle[name]["samples"] == raw["samples"])
    report["NGA"] = dict(ure_cm=arms["NGA"]["raw"]["rms_orbit_ure_m"]*100, d3_cm=arms["NGA"]["raw"]["rms_3d_m"]*100)

    c1 = lin0_control(folders["N-op"], folders["U"])
    c2 = all(a["oracle_difference_m"] <= SCORE_TOL_M and a["oracle_samples_equal"] for a in report["arms"].values())
    report["controls"] = dict(C1_lin0_bitwise=c1, C2_oracle_within_tolerance=c2)

    a, u = arms["N-op"], arms["U"]
    per_n, per_u = a["per_satellite"], u["per_satellite"]
    increases = sorted(((per_n[s]["rms_3d_m"]-per_u[s]["rms_3d_m"]), s) for s in per_u if s in per_n)
    contrast = dict(ure_change_pct=100*(a["raw"]["rms_orbit_ure_m"]/u["raw"]["rms_orbit_ure_m"]-1),
                    d3_change_pct=100*(a["raw"]["rms_3d_m"]/u["raw"]["rms_3d_m"]-1),
                    radial_change_pct=100*(a["raw"]["rms_rac_m"][0]/u["raw"]["rms_rac_m"][0]-1),
                    along_change_pct=100*(a["raw"]["rms_rac_m"][1]/u["raw"]["rms_rac_m"][1]-1),
                    cross_change_pct=100*(a["raw"]["rms_rac_m"][2]/u["raw"]["rms_rac_m"][2]-1),
                    worst_satellite_3d_increase_m=increases[-1][0], worst_satellite=increases[-1][1],
                    satellites_better_3d=sum(d < 0 for d, _ in increases), satellites=len(increases),
                    median_satellite_3d_change_m=float(np.median([d for d, _ in increases])))
    limits = contrast["worst_satellite_3d_increase_m"] <= 0.1 and contrast["radial_change_pct"] <= 3.0
    if not (all(c1.values()) and c2):
        reading = "not read (a control failed)"
    elif contrast["ure_change_pct"] <= -1.0 and limits:
        reading = "gain reproduced"
    elif contrast["ure_change_pct"] < 0 and limits:
        reading = "smaller gain"
    else:
        reading = "not reproduced"
    report["contrast"], report["reading"] = contrast, reading
    (folder/"newdate_matched_analysis.json").write_text(json.dumps(report, indent=1, default=float)+"\n")
    print(json.dumps(dict(reading=reading, controls=report["controls"], **{k: contrast[k] for k in
          ("ure_change_pct", "d3_change_pct", "radial_change_pct", "worst_satellite_3d_increase_m")},
          U_ratio=report["arms"]["U"]["ure_ratio_to_nga"], N_ratio=report["arms"]["N-op"]["ure_ratio_to_nga"]), default=float))


if __name__ == "__main__":
    main()
