"""New-date test (NEW_DATE_PROTOCOL.md): readings P1-P4 and the descriptive scores, written before the fit completed.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.gradients.analyze_newdate

Run after `finish_newdate.sh` has exported the product and written `Opus_Fork/results/newdate_20260627.json`.
- P1: the GRAD input support, from `acquisition_record.tsv`;
- P2: the campaign status and its converged final solution;
- P3: the product's QA record (`export_write.json`), a fresh `export.roundtrip` with its plain-EOP negative control,
  and the product header's labels;
- P4: independent-oracle scores (validation.oracle, sub-daily frame) against the production scores, on identical
  samples.

It also writes the descriptive scores: URE, 3D and RAC, the ratios to NGA PE, and the satellites beating NGA.
Writes `newdate_analysis.json` in the run folder. No fit, no integration.
"""
import argparse
import json

from Opus_Fork import export
from Opus_Fork.experiments.gradients.analyze_validation import (R, ROOT, HERE, SCORE_TOL_M, campaign, final_solution,
                                                                input_support)
from Opus_Fork.experiments.transfer.common import run_dir, sha
from validation.oracle import frame as O2, metrics as O1

DAY, TAG, FIXTURE_DIR = "2026-06-27", "0627", "runs/20261004T151035Z-0225f559"
PRODUCT = ROOT/"Opus_Fork/datastore/products/OPUS0OPSFIN_20260627.SP3"
LABELS = export.GRADIENT_LABELS["grad_op"][0]+["RETROSPECTIVE INPUTS: NOT A LATENCY-CERTIFIED PRODUCT"]


def main():
    folder = run_dir()
    report = dict(protocol_sha256=sha(HERE/"NEW_DATE_PROTOCOL.md"), day=DAY)

    support = input_support(DAY)
    report["P1_input_support"] = support
    p1 = all(f["sha256"] for f in support["files"])

    arm = campaign(f"N-op-{TAG}")
    status = json.loads((arm/"validation.json").read_text())["status"]
    fit = final_solution(arm)                                           # raises unless complete and converged
    assert fit["force_model"]["gradients"]["source"] == "grad_op"
    report["P2_fit"] = dict(campaign=arm.name, status=status, final=fit["final"],
                            gradient_inputs=sorted(fit["force_model"]["gradients"]["inputs"]))
    p2 = status.startswith("long_fit_complete")

    written = json.loads((ROOT/"Opus_Fork/results/export_write.json").read_text())
    comments = [line[3:].rstrip() for line in PRODUCT.read_text().splitlines() if line.startswith("/* ")]
    fixture = ROOT/FIXTURE_DIR/"fixture.json"
    trip = export.roundtrip(argparse.Namespace(pairs=[f"{arm/fit['final']}::{fixture}::{DAY}"]), folder)["cases"][0]
    report["P3_product"] = dict(path=str(PRODUCT), sha256=sha(PRODUCT), qa_passed=written["passed"],
                                written_sha256=written["sha256"], product_type=written.get("product_type"),
                                header_comments=comments, labels_present=all(t in comments for t in LABELS),
                                roundtrip=trip)
    p3 = bool(written["passed"] and written["sha256"] == sha(PRODUCT) and trip["passed"]
              and report["P3_product"]["labels_present"])

    evaluation_path = ROOT/"Opus_Fork/results/newdate_20260627.json"
    evaluation = json.loads(evaluation_path.read_text())
    arms = evaluation["domains"]["full"]["arms"]
    origin = int(json.loads(fixture.read_text())["context"]["origin_ns"])
    frame = O2.Frame(O2.Finals(ROOT/"data/stage2/finals2000A.all"), subdaily=True)
    reference = O1.read_sp3(evaluation["provenance"]["igs_final"]["path"])
    ecef = O1.solution_ecef(fit["states"], fit["sats"], fit["times"], origin, frame)
    start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
    keys = {k for k in set(reference) & set(ecef) if start <= k[1] <= stop}
    oracle = O1.summarize(reference, ecef, frame, keys)
    ours, nga = arms["N-op"], arms["NGA"]
    difference = max(abs(oracle["orbit_ure_m"]-ours["raw"]["rms_orbit_ure_m"]), abs(oracle["rms_3d_m"]-ours["raw"]["rms_3d_m"]))
    report["P4_oracle"] = dict(evaluation_sha256=sha(evaluation_path), oracle_ure_m=oracle["orbit_ure_m"],
                               oracle_3d_m=oracle["rms_3d_m"], max_difference_m=difference,
                               samples_equal=oracle["samples"] == ours["raw"]["samples"])
    p4 = difference <= SCORE_TOL_M and report["P4_oracle"]["samples_equal"]

    sats = [s for s in ours["per_satellite"] if s in nga["per_satellite"]]
    report["scores"] = dict(
        ure_cm=ours["raw"]["rms_orbit_ure_m"]*100, d3_cm=ours["raw"]["rms_3d_m"]*100,
        rac_cm=[x*100 for x in ours["raw"]["rms_rac_m"]], samples=ours["raw"]["samples"],
        nga_ure_cm=nga["raw"]["rms_orbit_ure_m"]*100, nga_3d_cm=nga["raw"]["rms_3d_m"]*100,
        ure_ratio_to_nga=ours["raw"]["rms_orbit_ure_m"]/nga["raw"]["rms_orbit_ure_m"],
        d3_ratio_to_nga=ours["raw"]["rms_3d_m"]/nga["raw"]["rms_3d_m"],
        satellites_beating_nga_ure=sum(ours["per_satellite"][s]["rms_orbit_ure_m"] < nga["per_satellite"][s]["rms_orbit_ure_m"]
                                       for s in sats),
        satellites_compared=len(sats))
    report["readings"] = dict(P1=p1, P2=p2, P3=p3, P4=p4, operational_path_passes=bool(p1 and p2 and p3 and p4))
    (folder/"newdate_analysis.json").write_text(json.dumps(report, indent=1, default=float)+"\n")
    print(json.dumps(dict(report["readings"], **{k: report["scores"][k] for k in ("ure_cm", "nga_ure_cm", "ure_ratio_to_nga",
                                                                               "d3_ratio_to_nga")}), default=float))


if __name__ == "__main__":
    main()
