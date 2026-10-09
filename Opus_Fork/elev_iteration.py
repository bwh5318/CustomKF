"""Worker: `Opus_Fork.iteration` for an elevation-handling variant of the sub-daily-EOP fit (`Opus_Fork.elev`).

    ... -- Opus_Fork.elev_iteration state|chunk|solve|trial <Opus_Fork.iteration arguments>

`elev.install()` first, then the unchanged `Opus_Fork.iteration.main`; writes `force_model.json` with `elev.binding()`.
"""
import json
import os
from pathlib import Path

from . import elev


def main():
    iteration = elev.install()
    iteration.main()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"force_model.json").write_text(json.dumps(elev.binding(), indent=2)+"\n")


if __name__ == "__main__":
    main()
