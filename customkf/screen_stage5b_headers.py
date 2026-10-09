"""Read header-only HTTP range samples; no observation decompression required."""
import gzip
import io
import json
import os
from pathlib import Path
from .prepare_stage2 import ROOT,sha
from .prepare_stage3 import DATA
from .rinex import header
from .preprocess import choose_signals
from .antenna import load_calibrations
from .stage5_pilot import ORIGIN


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    report={}
    for p in sorted((ROOT/"data/stage5b/headers").glob("*.gz")):
        try:
            with gzip.open(p,"rt") as stream:
                lines=[];started=False
                for line in stream:
                    if "RINEX VERSION / TYPE" in line:started=True
                    if started:lines.append(line)
                    if "END OF HEADER" in line:break
            meta=header(io.StringIO("".join(lines)),allow_declared_phase_shifts=True)
            pair=choose_signals(meta.types["G"])
            load_calibrations(DATA/"igs20.atx",[meta.antenna],ORIGIN)
            report[p.stem]={"status":"compatible_header","antenna":meta.antenna,"pair":pair.__dict__,"range_sample_sha256":sha(p)}
        except (ValueError,EOFError,OSError) as error:report[p.stem]={"status":"rejected","reason":str(error),"range_sample_sha256":sha(p)}
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"headers.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":main()
