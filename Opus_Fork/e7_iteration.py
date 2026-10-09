"""Worker: `Opus_Fork.iteration7` with ECOM-7 and a named ERP + thrust variant (`Opus_Fork.e7`).

    ... -- Opus_Fork.e7_iteration state|chunk|solve|trial <Opus_Fork.iteration arguments>

Writes `force_model.json` (the `e7.binding()`) beside its outputs; the controller refuses a mismatch.
"""
import json
import os
from pathlib import Path

from . import e7


def main():
    iteration7 = e7.install()
    iteration7.main()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"force_model.json").write_text(json.dumps(e7.binding(), indent=2)+"\n")


if __name__ == "__main__":
    main()
