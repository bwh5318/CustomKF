"""Guarded PPP regression and unedited residual review for the four new sites."""
import argparse
import json
import os
from pathlib import Path

import numpy as np


def read(path):
    return json.loads(path.read_text())


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign",type=Path)
    parser.add_argument("--regression-only",action="store_true")
    args=parser.parse_args();folder=args.campaign
    before=np.load(folder/"BRUX_before/ppp.npz")
    after=np.load(folder/"BRUX/ppp.npz")
    assert set(before.files)==set(after.files)
    for name in before.files:
        np.testing.assert_array_equal(before[name],after[name],err_msg=name)
    old,new=(read(folder/name/"ppp.json") for name in ("BRUX_before","BRUX"))
    for key in old:
        if key not in ("elapsed_s","iterations"):
            assert old[key]==new[key],key
    report={"status":"legacy_numeric_regression_pass","stations":{}}
    if not args.regression_only:
        for station in ("DAV1","FALK","FAA1","GLPS"):
            ppp=read(folder/station/"ppp.json")
            saved=np.load(folder/station/"ppp.npz")
            mask=saved["phase"];r=saved["residual_m"][mask]
            t=saved["time_s"][mask]/3600
            el=np.rad2deg(saved["elevation_rad"][mask])
            sat=saved["satellite"][mask];arcs=saved["arc"][mask]
            normalized=r*np.sin(np.deg2rad(el))/.009
            def stats(select):
                values=r[select]
                return {"count":len(values),"rms_mm":float(1000*np.sqrt(np.mean(values**2))) if len(values) else None,
                        "max_abs_mm":float(1000*np.max(abs(values))) if len(values) else None}
            order=np.argsort(abs(normalized))[-8:][::-1]
            changes=[]
            for s in sorted(set(sat)):
                indices=np.flatnonzero(sat==s)
                for a,b in zip(indices[:-1],indices[1:]):
                    if arcs[a]==arcs[b] and abs(t[b]-t[a]-1/12)<1e-8:
                        changes.append({"satellite":str(s),"hour_gpst":float(t[b]),"change_mm":float(1000*(r[b]-r[a]))})
            report["stations"][station]={
                "coordinate_gate":ppp["status"],"converged":ppp["converged"],
                "horizontal_error_mm":1000*ppp["horizontal_error_m"],
                "vertical_error_mm":1000*ppp["error_enu_m"][2],
                "error_enu_mm":[1000*v for v in ppp["error_enu_m"]],
                "phase":stats(np.ones(len(r),dtype=bool)),
                "normalized_phase_rms":float(np.sqrt(np.mean(normalized**2))),
                "rows_above_4_sigma":int(sum(abs(normalized)>4)),
                "elevation_bins":{f"{lo}-{hi}":stats((el>=lo)&(el<hi)) for lo,hi in ((10,20),(20,30),(30,50),(50,91))},
                "hours":{str(hour):stats((t>=hour)&(t<hour+1)) for hour in range(24)},
                "network_arc":stats((t>=12)&(t<=15)),
                "largest_normalized_residuals":[{"hour_gpst":float(t[i]),"satellite":str(sat[i]),"phase_mm":float(r[i]*1000),"normalized":float(normalized[i]),"elevation_deg":float(el[i])} for i in order],
                "largest_same_arc_changes":sorted(changes,key=lambda v:abs(v["change_mm"]),reverse=True)[:8],
                "native_arcs":ppp["native_arc_count"],"fitted_ambiguities":ppp["fitted_ambiguities"],
                "excluded_short_arc_phase_rows":ppp["short_arc_phase_rows_excluded"],
                "modeled_epochs":ppp["modeled_epochs"],"signal_pair":ppp["signal_pair"],
                "receiver_header":ppp["receiver_header"]}
        report["status"]="station_diagnostics_completed_not_physical_acceptance"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"review.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"stations":{s:{k:v[k] for k in ("coordinate_gate","horizontal_error_mm","vertical_error_mm","phase","normalized_phase_rms","rows_above_4_sigma")} for s,v in report["stations"].items()}},indent=2))


if __name__=="__main__":main()
