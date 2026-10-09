"""Five-day URE distributions against NGA PE: plain-EOP ERP arms (B) and sub-daily-EOP arms (ERP slot), IGS final truth.

    ... -- Opus_Fork.experiments.subdaily.nga_dist_sd

Reuses `Opus_Fork.dip_nga.build` / `part_a` / `part_b` unchanged, with the sub-daily arms scored as their Earth-fixed
products (`sd_scoring`). Writes `nga_dist_sd.json` to the run folder and `results/nga_dist_sd.json`; the original
`results/dip_nga.json` is not touched. The SD campaign for each day is the newest complete `*-fit-SD-<d>-25st`.
"""
import json
import os
from pathlib import Path

from Opus_Fork.experiments.subdaily import sd_scoring

R = "Opus_Fork/runs/"
PLAIN = {  # day: (fixture, plain-EOP ERP arm, variant)
    "2026-08-02": (R+"20260920T200910Z-prepare-31sat/fixture.json", R+"20260922T205445Z-fit-P1-erp-31sat/lin2-solve", "erp+thrust"),
    "2026-08-03": (R+"20260922T225652Z-prepare-2026-08-03/fixture.json", R+"20260923T000354Z-fit-P2-3-25st/lin2-solve", "erp+thrust+iiia2600"),
    "2026-08-04": (R+"20260922T230119Z-prepare-2026-08-04/fixture.json", R+"20260923T200747Z-fit-P2-4-25st/lin2-solve", "erp+thrust+iiia2600"),
    "2026-08-05": (R+"20260922T230410Z-prepare-2026-08-05/fixture.json", R+"20260923T230743Z-fit-P2-5-25st/lin3-solve", "erp+thrust+iiia2600"),
    "2026-08-07": ("runs/20260920T155655Z-7b703635/fixture.json", R+"20260922T215245Z-fit-R7-erp-aug7-25st/lin2-solve", "erp+thrust"),
}


def sd_arm(day):
    from Opus_Fork.paths import ROOT
    d = day[-1]
    runs = sorted((ROOT/"Opus_Fork"/"runs").glob(f"*-fit-SD-{d}-25st"), reverse=True)
    for folder in runs:
        v = json.loads((folder/"validation.json").read_text())
        if v["status"].startswith("long_fit_complete"):
            return (folder/v["final"]).relative_to(ROOT).as_posix()
    raise FileNotFoundError(f"No complete SD campaign for {day}")


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    sd_scoring.install()
    from customkf.ephemeris import DE440
    from customkf.frames import EarthOrientation
    from Opus_Fork import dip_nga
    from Opus_Fork.paths import STAGE2, RESULTS
    eop, ephemeris = EarthOrientation(STAGE2/"finals2000A.all"), DE440(STAGE2/"de440s.bsp")
    all_rows, helmert, resid, provenance = {}, {}, {}, {}
    for day, (fixture, plain, variant) in PLAIN.items():
        sd = sd_arm(day)
        rows, h, prov, r = dip_nga.build(day, fixture, [("B", plain), ("ERP", sd)], eop, ephemeris)
        all_rows[day], helmert[day], resid[day] = rows, h, r
        provenance[day] = dict(prov, plain_variant=variant, sd_arm=sd, fixture=fixture, common_samples=len(rows))
        print(day, len(rows), "samples", flush=True)
    census = json.loads((RESULTS/"reference_census_2026-08-02_physics.json").read_text())
    a = dip_nga.part_a(all_rows, helmert, census)
    b = dip_nga.part_b(all_rows, resid)
    report = dict(status="evaluation_only_not_accuracy_acceptance", reference="IGS final",
                  arms={"B": "plain-EOP ERP arm (P1/P2/R7)", "ERP": "sub-daily-EOP arm (SD)"},
                  provenance=provenance, part_a_midday_dip=a, part_b_nga_distributions=b)
    text = json.dumps(report, indent=1, default=float)+"\n"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"nga_dist_sd.json").write_text(text)
    (RESULTS/"nga_dist_sd.json").write_text(text)
    pooled = b["pooled_all_days"]
    for arm in ("B", "ERP"):
        print(arm, json.dumps(pooled.get(arm, pooled))[:900], flush=True)


if __name__ == "__main__":
    main()
