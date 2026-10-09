"""Decode individually screened public files using the existing pinned decoder."""
import json
import os
import argparse
from pathlib import Path
from .prepare_stage4 import main as decode


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    parser=argparse.ArgumentParser();parser.add_argument("--markers",nargs="+",default=["DAV100ATA","FALK00FLK","FAA100PYF","GLPS00ECU"]);args=parser.parse_args()
    report={}
    from .prepare_stage3 import DATA
    from .rinex import text_stream,header
    from .preprocess import choose_signals
    from .antenna import load_calibrations
    from .stage5_pilot import ORIGIN
    for marker in args.markers:
        try:
            decode(markers=(marker,),manifest_name="stage5b_manifest.json",allow_phase_shift_metadata=True)
            with text_stream(DATA/f"{marker}_R_20262140000_01D_30S_MO.rnx.gz") as stream:meta=header(stream,allow_declared_phase_shifts=True)
            pair=choose_signals(meta.types["G"])
            load_calibrations(DATA/"igs20.atx",[meta.antenna],ORIGIN)
            report[marker]={"status":"header_signals_and_calibration_passed","antenna":meta.antenna,"signals":pair.__dict__}
        except ValueError as error:
            report[marker]=str(error)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"decoding.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":main()
