"""Real-data regression for the domain-aware correction stencil (Sol SOL-01; untouched-date amendment A3).

    OPUSFORK_ELEV_VARIANT=erp+thrust+iiia2600+sdeop+elw13 C:\\anaconda\\python.exe -m customkf.guard --profile usage75 \
        --timeout 900 -- Opus_Fork.experiments.untouched_dates.check_stencil_fix

On the preserved Jun 23 campaign's zero point (fixture, state, lin0 trajectory caches; no integration, no fit):
1. every link of epochs 96-108 except the failing one gets a Jacobian bitwise equal to the former fixed-stencil formula;
2. the failing GLPS-G10 link (epoch 105), which the former formula refuses, now succeeds. Its x column equals the
   5 m central difference, and agrees with the 2.5 m and 1.25 m controls;
3. the unperturbed observation is unchanged.
Writes stencil_check.json in the run folder. Nothing in the campaign folder is written.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from customkf.prepare_stage2 import ROOT, sha

PREP = ROOT/"runs/20260929T201929Z-5b2b3e42"
CONFIG = ROOT/"claude/roadmap/configs/unit-ecom5.json"
CAMPAIGN = ROOT/"Opus_Fork/runs/20260930T183604Z-fit-U-elw13-0623"


def former_link_jacobian(D, products, row, receiver_cal, satellite_cal, ephemeris, receiver_clock,
                         satellite_clock, wet, ambiguity, windup_reference):
    """The fixed-stencil implementation before the fix, verbatim apart from the name."""
    def evaluate(p, rc=receiver_clock):
        return D.modeled_link(p, row, receiver_cal, satellite_cal, ephemeris, rc,
                              satellite_clock, wet, ambiguity, windup_reference, details=True)
    g, _ = evaluate(products)
    sat = row["satellite"]
    rotation = products.epoch.celestial_to_terrestrial(g["receive_s"])
    u = rotation.T@g["los_ecef"]
    velocity = g["satellite_inertial"][3:]
    rate = products.clock_rate(sat, g["transmit_s"])
    principal = (1+rate)*(u@products.trajectories[sat].partial(g["transmit_s"])[:3])/(1+u@velocity/D.C)
    jac = np.empty((2, 6))
    for k in range(6):
        h = 10. if k < 3 else .01
        d = np.eye(6)[k]*h
        jac[:, k] = principal[k]+(evaluate(D.PerturbedProducts(products, sat, d))[1]-
                     evaluate(D.PerturbedProducts(products, sat, -d))[1])/(2*h)
    t = g["receive_s"]
    receiver_velocity = (products.epoch.celestial_to_terrestrial(t+.5).T@row["receiver_xyz"]-
                         products.epoch.celestial_to_terrestrial(t-.5).T@row["receiver_xyz"])
    range_rate = -u@(velocity-receiver_velocity)/(D.C+u@velocity)
    clock_jac = (1+rate)*(1+range_rate)+(evaluate(products, receiver_clock+10.)[1]-evaluate(products, receiver_clock-10.)[1])/20.
    return jac, clock_jac


def former_force_partial(D, L, D0, products, row, receiver_cal, satellite_cal, ephemeris, rc, sc, wet, amb, windup, column):
    """The fixed-stencil force-column partials before AF-02 (long_pilot.force_link_partial / dated_d0.d0_link_partial)."""
    def evaluate(p):
        return D.modeled_link(p, row, receiver_cal, satellite_cal, ephemeris, rc, sc, wet, amb, windup, details=True)
    g, _ = evaluate(products)
    sat = row["satellite"]
    u = products.epoch.celestial_to_terrestrial(g["receive_s"]).T@g["los_ecef"]
    velocity = g["satellite_inertial"][3:]
    rate = products.clock_rate(sat, g["transmit_s"])
    sensitivity = products.trajectories[sat].force_partial(g["transmit_s"])[:3, column]*D0.SCALE
    principal = (1+rate)*(u@sensitivity)/(1+u@velocity/D.C)
    h = .001
    if column == 0:
        return principal+(evaluate(D0.ForceTangent(products, sat, h))[1]-evaluate(D0.ForceTangent(products, sat, -h))[1])/(2*h)
    return principal+(evaluate(L.ColumnTangent(products, sat, column, h))[1]-evaluate(L.ColumnTangent(products, sat, column, -h))[1])/(2*h)


def main():
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    from Opus_Fork import elev
    iteration = elev.install()
    from claude.tools import dated_observation as D
    from claude.tools import dated_d0 as D0
    from claude.roadmap import long_pilot as L
    args = NS(fixture=PREP/"fixture.json", config=CONFIG, state=CAMPAIGN/"state/state.json")
    pilot, _ = iteration.build(args)
    x = np.zeros(len(pilot.names))
    files = [CAMPAIGN/f"lin0-traj-{g}/trajectories.npz" for g in range(2)]
    products = iteration.cached_products(pilot, x, files)
    report = dict(fixture_sha256=sha(args.fixture), state_sha256=sha(args.state), cache_sha256=[sha(p) for p in files],
                  dated_observation_sha256=sha(ROOT/"claude/tools/dated_observation.py"), links=0, bitwise_equal=0,
                  former_refused=[], differing=[], force_partials=0, force_bitwise_equal=0, force_differing=[],
                  force_former_refused=[])
    for ei in range(96, 108):
        for i in pilot.by_epoch[ei]:
            row = pilot.rows[i]
            rc, sc, wet, amb = pilot.state_for(x, row)
            antenna = pilot.context["stations"][row["station"]]["header"]["antenna"]
            cal = (pilot.context["rx_cal"][antenna], pilot.context["sat_cal"][row["satellite"]], pilot.context["ephemeris"])
            new = D.link_jacobian(products, row, *cal, rc, sc, wet, amb, pilot.windup[i])
            report["links"] += 1
            for column in pilot.estimate:
                report["force_partials"] += 1
                fresh = L.force_link_partial(products, row, *cal, rc, sc, wet, amb, pilot.windup[i], column)
                try:
                    old_force = former_force_partial(D, L, D0, products, row, *cal, rc, sc, wet, amb, pilot.windup[i], column)
                except ValueError as error:
                    report["force_former_refused"].append(dict(epoch=ei, row=i, column=int(column), error=str(error)))
                    continue
                if np.array_equal(np.asarray(fresh), np.asarray(old_force)):
                    report["force_bitwise_equal"] += 1
                else:
                    report["force_differing"].append(dict(epoch=ei, row=i, column=int(column)))
            try:
                old = former_link_jacobian(D, products, row, *cal, rc, sc, wet, amb, pilot.windup[i])
            except ValueError as error:
                entry = dict(epoch=ei, row=i, station=row["station"], satellite=row["satellite"], error=str(error),
                             new_jacobian=new[0].tolist())
                # Controls: plain central differences at 5, 2.5 and 1.25 m on the x column (small corrections only).
                def small(delta):
                    return D.modeled_link(D.PerturbedProducts(products, row["satellite"], delta), row, *cal, rc, sc,
                                          wet, amb, pilot.windup[i], details=True)[1]
                g, base = D.modeled_link(products, row, *cal, rc, sc, wet, amb, pilot.windup[i], details=True)
                rotation = products.epoch.celestial_to_terrestrial(g["receive_s"])
                u = rotation.T@g["los_ecef"]
                rate = products.clock_rate(row["satellite"], g["transmit_s"])
                principal = (1+rate)*(u@products.trajectories[row["satellite"]].partial(g["transmit_s"])[:3])/\
                    (1+u@g["satellite_inertial"][3:]/D.C)
                controls = {}
                for step in (5., 2.5, 1.25):
                    d = np.eye(6)[0]*step
                    controls[step] = (principal[0]+(small(d)-small(-d))/(2*step)).tolist()
                entry.update(controls_x=controls,
                             x_equals_5m=bool(np.array_equal(new[0][:, 0], np.array(controls[5.]))),
                             x_close_to_smaller=bool(np.allclose(new[0][:, 0], controls[1.25], rtol=1e-9, atol=1e-12)))
                report["former_refused"].append(entry)
                continue
            if np.array_equal(old[0], new[0]) and np.array_equal(np.asarray(old[1]), np.asarray(new[1])):
                report["bitwise_equal"] += 1
            else:
                report["differing"].append(dict(epoch=ei, row=i, station=row["station"], satellite=row["satellite"]))
    report["passed"] = bool(report["former_refused"] and not report["differing"]
                            and report["bitwise_equal"] == report["links"]-len(report["former_refused"])
                            and all(e["x_equals_5m"] and e["x_close_to_smaller"] for e in report["former_refused"])
                            and not report["force_differing"]
                            and report["force_bitwise_equal"] == report["force_partials"]-len(report["force_former_refused"]))
    (folder/"stencil_check.json").write_text(json.dumps(report, indent=1)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("former_refused",)}, indent=1))
    print("former refused:", [(e["station"], e["satellite"], e["epoch"], e["x_equals_5m"], e["x_close_to_smaller"])
                              for e in report["former_refused"]])
    print("PASSED" if report["passed"] else "FAILED")


if __name__ == "__main__":
    main()
