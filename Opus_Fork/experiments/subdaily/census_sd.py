"""Dynamics-only census with a sub-daily ocean-tidal EOP model applied (results/SWING_ORIGIN_NOTES.md).

    ... -- Opus_Fork.experiments.subdaily.census_sd --day 2026-08-02 --workers 6 --variants E5 --tag _sdEOP

Runs `Opus_Fork.reference_census` unchanged, except that the model's `install()` adds its terms to
`customkf.frames.EarthOrientation.at`. That happens in the parent process (the IGS reference positions) and in every pool
worker (the dynamics' Earth rotation), through a replacement pool initializer defined here. Nothing is edited on disk.

Model: environment `OPUSFORK_SUBDAILY_MODEL`, inherited by the pool workers.
- `ortho` (default): IERS 2010 ORTHO_EOP, `Opus_Fork.subdaily_eop`. Sources hash-verified; IERS test case asserted.
- `ds`: Desai & Sibois (2016), `Opus_Fork.hfeop_ds`. Coefficient file hash-verified. Added 26 Sep 2026.
"""
import json
import os
from pathlib import Path

from Opus_Fork import reference_census as rc

MODEL = os.environ.get("OPUSFORK_SUBDAILY_MODEL", "ortho")
if MODEL == "ortho":
    from Opus_Fork import subdaily_eop as _model
elif MODEL == "ds":
    from Opus_Fork import hfeop_ds as _model
else:
    raise RuntimeError(f"OPUSFORK_SUBDAILY_MODEL must be 'ortho' or 'ds', got {MODEL!r}")

_model.install()
_original_init = rc._init


def _init_sd(midnight, duration):
    _model.install()
    return _original_init(midnight, duration)


rc._init = _init_sd


def main():
    run = Path(os.environ["CUSTOMKF_RUN_DIR"])
    if MODEL == "ortho":
        _model.verify_sources()
        _model.self_test()
        record = dict(applied="IERS 2010 ORTHO_EOP ocean-tidal diurnal/semidiurnal x, y, UT1 (no libration)",
                      module="Opus_Fork/subdaily_eop.py", iers_sources=_model.IERS_SOURCES)
    else:
        _model._table()
        record = dict(applied="Desai & Sibois (2016) ocean-tidal diurnal/semidiurnal x, y, UT1 (no libration)",
                      module="Opus_Fork/hfeop_ds.py", source=dict([_model.SOURCE]))
    (run/"subdaily_eop.json").write_text(json.dumps(dict(record, model=MODEL), indent=1)+"\n")
    rc.main()


if __name__ == "__main__":
    main()
