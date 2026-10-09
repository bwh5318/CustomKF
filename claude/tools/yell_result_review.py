"""Guarded final YELL evidence/residual review; no fit or data editing.

customkf.guard --timeout 120 -- claude.tools.yell_result_review
Preserves full-domain orbit scores and separately reviews daily PPP versus the
three-hour network residuals. Writes only the guarded run directory.
"""
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT,sha

CAMPAIGN=ROOT/"validation/yell/20260911T020943Z"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    manifest=json.loads((CAMPAIGN/"validation.json").read_text())
    assert manifest["status"]=="YELL_experiment_complete_not_accuracy_acceptance"
    for name,digest in manifest["artifacts_sha256"].items():assert sha(CAMPAIGN/name)==digest,name
    for group in ("source_sha256","report_sha256"):
        for name,digest in manifest[group].items():assert sha(ROOT/name)==digest,name
    evaluation=json.loads((CAMPAIGN/"evaluation/evaluation.json").read_text())
    final=CAMPAIGN/manifest["final"];step=json.loads((final/"step.json").read_text())
    fit=np.load(final/"solution.npz")
    fixture=json.loads((CAMPAIGN/"prepare/fixture.json").read_text())
    for name,digest in fixture["context"]["inputs"].items():assert sha(ROOT/name)==digest,name
    if not step["history"][-1]["update_applied"]:
        previous=CAMPAIGN/f"iteration-{int(manifest['final'].split('-')[-1])-1}"
        before=np.load(previous/"solution.npz")
        for key in ("x","states","residual_m","sigma_m","times_s","satellites"):
            np.testing.assert_array_equal(before[key],fit[key],err_msg=key)
    ppp=np.load(CAMPAIGN/"YELL_PPP/ppp.npz");phase=ppp["phase"]
    residual=ppp["residual_m"][phase];t=ppp["time_s"][phase]/3600
    normalized=residual*np.sin(ppp["elevation_rad"][phase])/.009
    def stats(mask):
        r=residual[mask];z=normalized[mask]
        return {"count":len(r),"rms_mm":float(1000*np.sqrt(np.mean(r*r))),"max_abs_mm":float(1000*np.max(abs(r))),
                "normalized_rms":float(np.sqrt(np.mean(z*z))),"above_4_sigma":int(sum(abs(z)>4))}
    flagged=np.flatnonzero(abs(normalized)>4)
    ppp_review={"daily":stats(np.ones(len(t),dtype=bool)),"network_interval":stats((t>=12)&(t<=15)),
        "flagged_rows":[{"hour_gpst":float(t[i]),"satellite":str(ppp["satellite"][phase][i]),"phase_mm":float(1000*residual[i]),"normalized":float(normalized[i])} for i in flagged]}
    changes={s:{"baseline_rms_m":old["fit"]["rms_3d_m"],"YELL_rms_m":evaluation["YELL"]["per_satellite"][s]["fit"]["rms_3d_m"],
                "baseline_formal_sigma_m":old["formal_position_sigma_m"],
                "YELL_formal_sigma_m":evaluation["YELL"]["per_satellite"][s]["formal_position_sigma_m"],
                "YELL_class":evaluation["YELL"]["per_satellite"][s]["class"]}
             for s,old in evaluation["baseline"]["per_satellite"].items()}
    report={"status":"YELL_results_verified_not_accuracy_acceptance","PPP_residual_review":ppp_review,
        "full_common":evaluation["all_common"],"determined_in_both":evaluation["determined_in_both"],
        "new_groups":evaluation["YELL"]["groups"],"per_satellite_changes":changes,
        "network_phase_rms_mm":evaluation["YELL"]["phase_rms_mm"],
        "history":step["history"],"stationary_checkpoint_identity_checked":not step["history"][-1]["update_applied"],
        "manifest_sha256":sha(CAMPAIGN/"validation.json"),"tool_sha256":sha(Path(__file__))}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"review.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"PPP_residual_review":ppp_review,"focus_changes":{s:changes[s] for s in ("G16","G18","G26","G29","G31")},"groups":report["new_groups"]},indent=2))


if __name__=="__main__":main()
