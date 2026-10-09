"""Smoke check of one `Opus_Fork.elev` variant on one fixture (no fit).

    ... -- Opus_Fork.experiments.sensitivity.check_elev VARIANT FIXTURE_JSON
"""
import json
import os
import sys
import numpy as np


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    variant, fixture = sys.argv[1], sys.argv[2]
    os.environ["OPUSFORK_ELEV_VARIANT"] = variant
    from Opus_Fork import elev
    from Opus_Fork.paths import ROOT
    base, change = elev.VARIANTS[variant]
    iteration = elev.install()
    from claude.tools import dated_fixture
    from claude.roadmap import long_iteration
    from customkf.frames import EarthOrientation
    assert dated_fixture.restore is long_iteration.restore is iteration.restore
    assert EarthOrientation.subdaily is not None
    b = elev.binding()
    assert b["elevation"] == change and b["subdaily_eop"] and b["variant"] == variant
    raw = json.loads((ROOT/fixture).read_text())["rows"]
    context, rows, seeds = iteration.restore(ROOT/fixture)
    sin_raw = np.array([0.9/r["sigma"][0] for r in raw])
    print(variant, "rows", len(raw), "->", len(rows), "| below 15 deg in raw:", int((sin_raw < np.sin(np.deg2rad(15))).sum()), flush=True)
    if change == "cut15s":
        assert len(rows) == int((sin_raw >= np.sin(np.deg2rad(15))).sum())
        if "2026-08-03" in fixture:
            frozen = {tuple(r) for r in json.loads((ROOT/"Opus_Fork/experiments/sensitivity/drop_below15_aug03.json").read_text())["rows"]}
            here = {(int(r["epoch"]), r["station"], r["satellite"]) for r, s in zip(raw, sin_raw) if s < np.sin(np.deg2rad(15))}
            print("  Aug 3: sigma-based drop set vs frozen orbit-based list: common", len(frozen & here),
                  "only-sigma", len(here-frozen), "only-frozen", len(frozen-here), flush=True)
    else:
        assert len(rows) == len(raw)
        s = np.array([r["sigma"] for r in rows])
        e = np.degrees(np.arcsin(sin_raw))
        for lo in (10, 30, 89):
            k = int(np.argmin(abs(e-lo)))
            print(f"  e={e[k]:5.1f}: phase sigma {raw[k]['sigma'][1]*1000:.2f} -> {s[k, 1]*1000:.2f} mm, code {raw[k]['sigma'][0]:.3f} -> {s[k, 0]:.3f} m", flush=True)
        assert np.allclose(s[:, 0], [r["sigma"][0] for r in raw])
    print("SMOKE OK", variant, flush=True)


if __name__ == "__main__":
    main()
