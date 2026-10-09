"""Worker: `Opus_Fork.iteration` with fixed physical ERP + antenna thrust (test T2.1).

    ... -- Opus_Fork.nongrav_iteration state|chunk|solve|trial <Opus_Fork.iteration arguments>

Identical to `Opus_Fork.iteration` (objective, local elimination, rank rule, stationarity,
line search, checkpoint bindings, precise-product audit hook) except that the pilot integrates
each satellite with `Opus_Fork.nongrav.PhysicalRadiation`, and every trajectory cache it reads
must carry the same force-model binding. Each run writes `force_model.json` beside its outputs
so any artifact can be traced to the model that produced it.
"""
import json
import os
from pathlib import Path

from .nongrav_pilot import install, model_binding


def main():
    iteration = install()
    iteration.main()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder/"force_model.json").write_text(json.dumps(model_binding(), indent=2)+"\n")


if __name__ == "__main__":
    main()
