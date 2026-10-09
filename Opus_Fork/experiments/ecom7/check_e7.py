"""Smoke test of the ECOM-7 install (no fit): model count, pilot names, cache parameters, sensitivities, binding.

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 600 --label e7-check -- Opus_Fork.experiments.ecom7.check_e7
"""
import json
import os
from pathlib import Path
import numpy as np


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    from Opus_Fork import e7
    os.environ[e7.ENVIRONMENT] = "erp+thrust+ecom7"
    iteration7 = e7.install()
    from claude.tools.dated_fixture import restore
    from claude.roadmap import long_pilot, traj_cache
    from customkf.propagation import propagate
    from customkf.dynamic_observation import SETTINGS
    from Opus_Fork.ngv_pilot import VariantPilot, satellite_models
    fixture = Path("Opus_Fork/runs/20260920T200910Z-prepare-31sat/fixture.json")
    context, rows, seeds = restore(fixture)
    model = context["model"]
    assert len(model.parameter_scales) == 7 and model.parameter_names[-2:] == ("Dc2", "Ds2"), model.parameter_names
    assert iteration7.restore is restore and iteration7.LongPilot is VariantPilot
    pilot = VariantPilot(context, rows, seeds, nominal=None, estimate=tuple(range(7)), prior_sigma={},
                         state=dict(clock_seeds=[], windup=[], amb_origins={}))
    names = [n for n in pilot.names if n.startswith("srp") and n.endswith(":G27")]
    assert names == [f"srp{k}:G27" for k in e7.NAMES7], names
    x = np.zeros(len(pilot.names))
    initial, p = traj_cache.initial_and_parameters(pilot, "G27", x)
    assert p.shape == (7,) and p[0] == -1e-7 and not p[1:].any(), p
    models = satellite_models(context, ["G27"])
    assert len(models["G27"].parameter_scales) == 7
    result = propagate(initial, np.arange(0., 3601., 900.), models["G27"], p, settings=SETTINGS)
    assert result.parameter_sensitivity.shape == (5, 6, 7), result.parameter_sensitivity.shape
    dc2 = np.abs(result.parameter_sensitivity[-1, :3, 5]).max()
    b = e7.binding()
    assert b["ecom"] == 7 and b["variant"] == "erp+thrust+ecom7"
    report = dict(status="ok", model_names=list(model.parameter_names), srp_names_G27=names, p0=p.tolist(),
                  dc2_position_sensitivity_after_1h_m_per_unit=float(dc2), binding=b,
                  retained_parameters=pilot.n, local_parameters=sum(map(len, pilot.local_names)))
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"check_e7.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
