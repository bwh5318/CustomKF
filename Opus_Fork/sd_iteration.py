"""Worker: `Opus_Fork.iteration` with an ERP + thrust variant and the IERS 2010 sub-daily EOP (`Opus_Fork.sdeop`).

    ... -- Opus_Fork.sd_iteration state|chunk|solve|trial <Opus_Fork.iteration arguments>

Same as `Opus_Fork.ngv_iteration` (pinned by the IIIA campaigns, unchanged) after `sdeop.install()`; writes
`force_model.json` with `sdeop.binding()`.
"""
import json
import os
from pathlib import Path

from . import sdeop


def main():
    iteration = sdeop.install()
    iteration.main()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"force_model.json").write_text(json.dumps(sdeop.binding(), indent=2)+"\n")


if __name__ == "__main__":
    main()
