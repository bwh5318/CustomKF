"""Final guarded GUAM checkpoint, residual and coverage audit; no fitting.

    customkf.guard --timeout 120 -- claude.tools.guam_result_review CAMPAIGN

Retains all satellites and the fixed prior scoring split. Does not diagnose
physical causes solely from postfit residuals. Uses no new station files.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from customkf.prepare_stage2 import ROOT,sha
from claude.tools.yell_continuation_review import residual_structure
from claude.tools.evaluate_ablation import coverage


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("campaign",type=Path);args=parser.parse_args()
    folder=args.campaign;manifest=json.loads((folder/"validation.json").read_text())
    assert manifest["status"]=="GUAM_experiment_complete_not_accuracy_acceptance"
    for name,digest in manifest["artifacts_sha256"].items():assert sha(folder/name)==digest,name
    for group in ("source_sha256","report_sha256"):
        for name,digest in manifest[group].items():assert sha(ROOT/name)==digest,name
    fixture=json.loads((folder/"prepare/fixture.json").read_text())
    for name,digest in fixture["context"]["inputs"].items():assert sha(ROOT/name)==digest,name
    final=folder/manifest["final"];fit=np.load(final/"solution.npz")
    step=json.loads((final/"step.json").read_text());identity=False
    if not step["history"][-1]["update_applied"]:
        prior=np.load(folder/f"iteration-{int(manifest['final'].split('-')[-1])-1}"/"solution.npz")
        for key in ("x","states","times_s","satellites","residual_m","sigma_m"):
            np.testing.assert_array_equal(prior[key],fit[key],err_msg=key)
        identity=True
    stations,labels,residual,z=residual_structure(fixture,fit)
    ppp=np.load(folder/"GUAM_PPP/ppp.npz");mask=ppp["phase"]
    r=ppp["residual_m"][mask];t=ppp["time_s"][mask]/3600;normalized=r*np.sin(ppp["elevation_rad"][mask])/.009
    def stats(select):
        return {"count":int(sum(select)),"rms_mm":float(1000*np.sqrt(np.mean(r[select]**2))),
                "max_abs_mm":float(1000*np.max(abs(r[select]))),"above_4_sigma":int(sum(abs(normalized[select])>4))}
    ppp_summary={"daily":stats(np.ones(len(r),dtype=bool)),"network_interval":stats((t>=12)&(t<=15)),
                 "flagged":[{"hour_gpst":float(t[i]),"satellite":str(ppp["satellite"][mask][i]),"residual_mm":float(r[i]*1000),"normalized":float(normalized[i])} for i in np.flatnonzero(abs(normalized)>4)]}
    baseline=ROOT/"claude/runs/20260911T022428Z-yell-continuation"
    old_fixture=json.loads((baseline/"prepare/fixture.json").read_text())
    cov,_=coverage(fixture);old_cov,_=coverage(old_fixture)
    added={s:{"baseline_multi_site_epochs":old_cov[s]["multi_site_epochs"],"GUAM_multi_site_epochs":cov[s]["multi_site_epochs"]} for s in ("G16","G18","G26","G29","G31")}
    evaluated=json.loads((folder/"evaluation/evaluation.json").read_text())
    per={s:{"before_m":evaluated["baseline"]["per_satellite"][s]["fit"]["rms_3d_m"],
            "after_m":v["fit"]["rms_3d_m"],"formal_sigma_m":v["formal_position_sigma_m"],"class":v["class"]}
         for s,v in evaluated["GUAM"]["per_satellite"].items()}
    common=evaluated["determined_in_both"]
    report={"status":"GUAM_results_and_residuals_reviewed_not_accuracy_acceptance","stationary_identity":identity,
            "PPP":ppp_summary,"network_station_residuals":stations,
            "GUAM_flagged_network_rows":[{"epoch":r["epoch"],"satellite":r["satellite"],"kind":kind,"residual_m":float(residual[i]),"normalized":float(z[i])} for i,(r,kind) in enumerate(labels) if r["station"]=="GUAM" and abs(z[i])>4],
            "actual_multi_site_coverage":added,"per_satellite":per,"determined_in_both":common,
            "all_common":evaluated["all_common"],"new_groups":evaluated["GUAM"]["groups"],
            "history":step["history"],"manifest_sha256":sha(folder/"validation.json"),
            "review_sources_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),ROOT/"claude/tools/yell_continuation_review.py",ROOT/"claude/tools/evaluate_ablation.py")}}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"review.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"PPP":ppp_summary,"GUAM_network":stations["GUAM"],"coverage":added,
                      "focus":{s:per[s] for s in ("G16","G18","G26","G29","G31")}},indent=2))


if __name__=="__main__":main()
