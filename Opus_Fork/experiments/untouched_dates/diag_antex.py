"""Diagnostic only: rerun one failed chunk worker and record the context of an "ANTEX angular extrapolation" refusal.

    OPUSFORK_ELEV_VARIANT=... python -m customkf.guard --profile usage75 --timeout 900 -- \
        Opus_Fork.experiments.untouched_dates.diag_antex <the failed worker's elev_iteration arguments after the module>

Replicates `Opus_Fork.elev_iteration` (elev.install(), then iteration.main()) with the observation model wrapped so the
first refused calibration lookup records station, satellite, time, the evaluated angles and the table ranges.
Writes antex_diagnostic.json in the run folder. Outputs never go into the campaign folder; no model is changed.
"""
import json
import os
from pathlib import Path
import sys

import numpy as np


def main():
    from Opus_Fork import elev
    iteration = elev.install()
    from claude.tools import dated_observation as D
    from customkf.measurement import enu_matrix
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    original = D.modeled_link
    record = {}

    def wrapped(products, row, receiver_cal, satellite_cal, ephemeris, receiver_clock, *rest, **kw):
        try:
            return original(products, row, receiver_cal, satellite_cal, ephemeris, receiver_clock, *rest, **kw)
        except ValueError as error:
            if "ANTEX" in str(error) and not record:
                g = D.geometry(products, row["satellite"], row["time_s"], row["receiver_xyz"], receiver_clock)
                state = g["satellite_inertial"]
                z = -state[:3]/np.linalg.norm(state[:3])
                axis = products.epoch.celestial_to_terrestrial(g["receive_s"])@z
                nadir = float(np.degrees(np.arccos(np.clip((-g["los_ecef"])@axis, -1, 1))))
                record.update(error=str(error), station=row.get("station"), satellite=row["satellite"],
                              time_s=float(row["time_s"]), arc=row.get("arc"), perturbed=type(products).__name__,
                              elevation_deg=float(np.degrees(g["elevation_rad"])),
                              zenith_deg=float(90-np.degrees(g["elevation_rad"])), nadir_deg=nadir,
                              receiver_antenna=receiver_cal.name, receiver_zenith_table=[float(receiver_cal.zenith[0]),
                                                                                          float(receiver_cal.zenith[-1])],
                              satellite_antenna=f"{satellite_cal.name} {satellite_cal.svn}",
                              satellite_nadir_table=[float(satellite_cal.zenith[0]), float(satellite_cal.zenith[-1])])
                (folder/"antex_diagnostic.json").write_text(json.dumps(record, indent=1)+"\n")
                print("ANTEX refusal:", json.dumps(record), flush=True)
            raise
    D.modeled_link = wrapped
    sys.argv = ["elev_iteration", *sys.argv[1:]]
    try:
        iteration.main()
    except ValueError as error:
        print("worker stopped as expected:", error, flush=True)
    if not record:
        print("No ANTEX refusal reproduced", flush=True)


if __name__ == "__main__":
    main()
