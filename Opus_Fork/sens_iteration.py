"""Worker: `Opus_Fork.iteration` for a one-change sensitivity variant of the sub-daily-EOP fit (`Opus_Fork.sens`).

    ... -- Opus_Fork.sens_iteration state|chunk|solve|trial <Opus_Fork.iteration arguments>

`sens.install()` first, then the unchanged `Opus_Fork.iteration.main`; writes `force_model.json` with `sens.binding()`.
"""
import json
import os
from pathlib import Path

from . import sens


def main():
    iteration = sens.install()
    iteration.main()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"force_model.json").write_text(json.dumps(sens.binding(), indent=2)+"\n")


if __name__ == "__main__":
    main()
