"""Smoke check of one `Opus_Fork.sens` variant in a fresh worker-like process (no fit).

    ... -- Opus_Fork.experiments.sensitivity.check_sens VARIANT
"""
import os
import sys
import numpy as np

FIXTURE = "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03/fixture.json"


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    variant = sys.argv[1]
    os.environ["OPUSFORK_SENS_VARIANT"] = variant
    from Opus_Fork import sens
    from Opus_Fork.paths import ROOT
    perturbation = sens.VARIANTS[variant]
    iteration = sens.install()
    from claude.tools import dated_fixture
    from claude.roadmap import long_iteration, long_pilot
    assert dated_fixture.restore is long_iteration.restore is iteration.restore
    from customkf.frames import EarthOrientation
    assert EarthOrientation.subdaily is not None, "sub-daily EOP not installed"
    b = sens.binding()
    assert b["sensitivity"] == perturbation and b["subdaily_eop"] and b["variant"] == variant, b
    context, rows, seeds = iteration.restore(ROOT/FIXTURE)
    print("rows", len(rows), "stations", len(context["stations"]), "satellites", len(seeds), flush=True)
    sat, cal = next(iter(context["sat_cal"].items()))
    rx = next(iter(context["rx_cal"].values()))
    sat_pcv = [cal.variation(f, a) for f in ("G01", "G02") for a in (0., 7., 13.)]
    rx_pcv = [rx.variation(f, z, 40.) for f in ("G01", "G02") for z in (5., 45., 80.)]
    print("satellite PCV samples (mm):", np.round(np.array(sat_pcv)*1000, 2), "| receiver PCV samples (mm):", np.round(np.array(rx_pcv)*1000, 2), flush=True)
    if perturbation == "nopcv":
        assert all(v == 0. for s in context["sat_cal"].values() for f in ("G01", "G02") for v in (s.variation(f, 0.), s.variation(f, 10.)))
        assert any(abs(v) > 0 for v in rx_pcv), "receiver PCV must be untouched"
    else:
        assert any(abs(v) > 0 for v in sat_pcv), "satellite PCV should be present"
    if perturbation == "cut15":
        assert len(rows) == 32885-3579, len(rows)
    else:
        assert len(rows) == 32885, len(rows)
    pilot = iteration.LongPilot(context, rows, seeds, estimate=(0, 1, 2, 3, 4),
                                state=dict(clock_seeds=[], windup=[], amb_origins={}))
    c, z, s = pilot.constraints(np.zeros(len(pilot.names)))
    start = len(pilot.level_sigma)
    wet = s[start:start+pilot.nodes*len(pilot.stations)]
    print("nodes", pilot.nodes, "NODE_EPOCHS", long_pilot.NODE_EPOCHS, "wet increment sigma", np.unique(np.round(wet, 5)),
          "arcs", len(pilot.arcs), "retained", len(pilot.names), flush=True)
    if perturbation == "wet1h":
        assert pilot.nodes == 24 and np.allclose(wet, .03*np.sqrt(6/18))
    else:
        assert pilot.nodes == 8 and np.allclose(wet, .03)
    print("SMOKE OK", variant, flush=True)


if __name__ == "__main__":
    main()
