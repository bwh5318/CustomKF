"""Small guarded navigation record inventory; no numerical fit."""
import json
import os
from .rinex import read_gps_navigation
from .prepare_stage3 import DATA
from .stage5_pilot import ORIGIN
from .broadcast import select_fit_record


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    nav=read_gps_navigation(DATA/"BRDC00WRD_R_20262140000_01D_MN.rnx.gz")
    for sat,records in nav.items():
        try:
            for t in (0.,10.,3310.):select_fit_record(records,ORIGIN+int(t*1e9),available_before_ns=ORIGIN+int(3320e9))
        except ValueError:
            print(json.dumps({"satellite":sat,"records":[{k:r.get(k) for k in ("gps_ns","toe","fit_interval","transmission_time","health")} | {"toc_minus_origin_s":(r["gps_ns"]-ORIGIN)/1e9} for r in records if -15000 < (r["gps_ns"]-ORIGIN)/1e9 < 15000]}),flush=True)


if __name__=="__main__":main()
