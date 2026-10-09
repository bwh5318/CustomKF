"""Guarded Stage 4 audit: dense vs eliminated QR, events, covariance and datum.

Run: python -m customkf.guard --timeout 300 -- customkf.run_stage4
Uses local pinned inputs only. Writes an audit report, not an SP3 product.
"""
import json
import os
from pathlib import Path
import time
import numpy as np
from .network_fixture import make_rows, build_system, EPOCHS, START, INTERVAL
from .network_square_root import assemble, dense_qr, eliminated_qr, Block
from .square_root import weighted_qr
from .preprocess import ALPHA, LAMBDA1, LAMBDA2, ArcTracker, combinations, SignalPair
from .rinex import Observable


def timed(function, *args):
    start = time.perf_counter()
    result = function(*args)
    return result, time.perf_counter()-start


def agreement(direct, reduced, a, sigma, observation_rows):
    scale = np.sqrt(np.diag(direct.covariance))
    cov_error = (direct.covariance-reduced.covariance)/scale[:, None]/scale
    result = {"max_estimate_difference_in_formal_sigma": float(np.max(np.abs(direct.estimate-reduced.estimate)/scale)),
              "max_covariance_difference_normalized": float(np.max(np.abs(cov_error))),
              "covariance_relative_frobenius": float(np.linalg.norm(direct.covariance-reduced.covariance)/np.linalg.norm(direct.covariance)),
              # Prior equations include velocities in m/s; only measurement
              # rows can be reported as an observation difference in metres.
              "max_prediction_difference_m": float(np.max(np.abs(a[:observation_rows]@(direct.estimate-reduced.estimate)))),
              "max_whitened_prediction_difference": float(np.max(np.abs((a@(direct.estimate-reduced.estimate))/sigma)))}
    if result["max_estimate_difference_in_formal_sigma"] > 1e-7 or result["max_covariance_difference_normalized"] > 1e-7 or result["max_prediction_difference_m"] > 1e-6:
        raise AssertionError("Dense/eliminated equivalence gate failed: "+str(result))
    return result


def re_datum(old_names, new_names, old_reference, new_reference):
    lookup = {name: i for i, name in enumerate(old_names)}
    transform = np.zeros((len(new_names), len(old_names)))
    for row, name in enumerate(new_names):
        if not name.startswith("clock:"):
            transform[row, lookup[name]] = 1.
            continue
        _, epoch, kind, object_name = name.split(":")
        if kind != "R" or object_name != old_reference:
            transform[row, lookup[name]] = 1.
        transform[row, lookup[f"clock:{epoch}:R:{new_reference}"]] -= 1.
    return transform


def detected_injection_epoch():
    """Inject one L1 cycle into native 30 s observables, without setting LLI."""
    tracker = ArcTracker()
    pair = SignalPair("P1", "P2", "L1", "L2")
    origin_arc = None
    detected = []
    for t in range(0, (EPOCHS-1)*INTERVAL+1, 30):
        jump = 1 if t >= 6*INTERVAL else 0
        obs = {"P1": Observable(22000000., 0, 0), "P2": Observable(22000000., 0, 0),
               "L1": Observable(22000000./LAMBDA1+jump, 0, 0),
               "L2": Observable(22000000./LAMBDA2, 0, 0)}
        arc = tracker.update(t*10**9, "G01", combinations(obs, pair))
        if origin_arc is None:
            origin_arc = arc
        if arc != origin_arc and not detected:
            detected.append(t//INTERVAL)
    if detected != [6] or len(tracker.events) != 2:
        raise AssertionError("Native unflagged one-cycle injection was not isolated")
    return detected[0], tracker.events


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    started = time.perf_counter()
    (rows, metadata), row_seconds = timed(make_rows)
    report = {"status": "running", "date": "2026-08-02", "span_gpst": ["12:00:00", "12:55:00"],
              "epochs": EPOCHS, "interval_s": INTERVAL, "station_count": len(metadata["stations"]),
              "link_count": len(rows), "metadata": metadata, "row_and_variational_seconds": row_seconds,
              "gate_scope": "Linear estimator algebra only; not independent POD, orbit accuracy, or rapid-vintage certification",
              "satellite_station_counts": {sat: len({r["station"] for r in rows if r["satellite"] == sat})
                                           for sat in metadata["satellites"]},
              "tolerances": {"estimate_formal_sigma": 1e-7, "normalized_covariance": 1e-7,
                             "prediction_m": 1e-6, "noise_free_event_m": 1e-6}}

    def save():
        (folder/"stage4.json").write_text(json.dumps(report, indent=2)+"\n")

    save()
    blocks, constraints, names, labels, layout = build_system(rows)
    a, y, sigma = assemble(blocks, constraints)
    ndata = len(labels)
    direct, direct_s = timed(dense_qr, a, y, sigma)
    reduced, reduced_s = timed(eliminated_qr, blocks, constraints)
    legacy, legacy_s = timed(weighted_qr, a, y, sigma)
    legacy_prediction = float(np.max(np.abs(a@(direct.estimate-legacy[0]))))
    if legacy_prediction > 1e-6:
        raise AssertionError("Existing Stage 3 QR oracle disagrees")
    report["real"] = {"rows_with_priors": len(y), "parameters": len(names),
        "retained_parameters": layout["retained_parameters"], "local_parameters": len(names)-layout["retained_parameters"],
        "reduced_rows": reduced.reduced_rows, "rank": direct.rank, "agreement": agreement(direct, reduced, a, sigma, ndata),
        "dense_seconds": direct_s, "eliminated_seconds": reduced_s, "legacy_qr_seconds": legacy_s,
        "legacy_qr_max_prediction_difference_m": legacy_prediction,
        "dense_design_mib": a.nbytes/2**20, "full_covariance_mib": direct.covariance.nbytes/2**20,
        "layout": layout}
    residual = y[:ndata]-a[:ndata]@reduced.estimate
    residual_stats = {}
    for station in sorted(metadata["stations"]):
        residual_stats[station] = {}
        for kind in ("code", "phase"):
            mask = np.array([label["station"] == station and label["kind"] == kind for label in labels])
            r = residual[mask]
            residual_stats[station][kind] = {"count": len(r), "rms_m": float(np.sqrt(np.mean(r*r))),
                "max_abs_m": float(np.max(np.abs(r))), "over_4_sigma": int(np.sum(np.abs(r/sigma[:ndata][mask]) > 4))}
    report["real"]["residuals_diagnostic_only"] = residual_stats
    np.savez_compressed(folder/"real_network.npz", estimate=reduced.estimate, covariance=reduced.covariance,
        names=np.array(names), residual_m=residual, sigma_m=sigma[:ndata], station=np.array([l["station"] for l in labels]),
        satellite=np.array([l["satellite"] for l in labels]), epoch=np.array([l["epoch"] for l in labels]),
        phase=np.array([l["kind"] == "phase" for l in labels]))
    print("Real network dense/eliminated agreement passed", report["real"]["agreement"], flush=True)
    save()

    # Change the exact datum; compare parameters AND covariance after the known
    # linear gauge transform. Identical raw numbers are not expected for clocks.
    b2, c2, names2, labels2, layout2 = build_system(rows, reference="HOB2")
    a2, y2, s2 = assemble(b2, c2)
    second, second_s = timed(eliminated_qr, b2, c2)
    transform = re_datum(names, names2, "BRUX", "HOB2")
    transformed = type(direct)(transform@direct.estimate, transform@direct.covariance@transform.T, direct.rank, 0)
    report["datum"] = {"from": "BRUX receiver correction = 0 each epoch", "to": "HOB2 receiver correction = 0 each epoch",
                       "agreement_after_transform": agreement(transformed, second, a2, s2, ndata), "seconds": second_s,
                       "design_transform_max_abs": float(np.max(np.abs(a2@transform-a)))}
    if report["datum"]["design_transform_max_abs"] > 1e-12 or not np.array_equal(y, y2):
        raise AssertionError("Datum change altered physical equations")
    del b2, c2, a2, second, transformed, transform

    # Weak-prior sensitivity is reported, not treated as a scientific accuracy
    # gate. A short network must not claim independent orbits from prior-dependent estimates.
    bweak, cweak, nweak, _, _ = build_system(rows, orbit_prior_factor=10.)
    weak, weak_s = timed(eliminated_qr, bweak, cweak)
    orbit_positions = np.array([name.startswith("orbit:") and name.split(":")[-1] in ("x", "y", "z") for name in names])
    delta = weak.estimate[orbit_positions]-reduced.estimate[orbit_positions]
    report["prior_sensitivity"] = {"position_prior_sigma_m": [100., 1000.], "velocity_prior_sigma_mps": [.1, 1.],
        "initial_position_component_change_rms_m": float(np.sqrt(np.mean(delta*delta))),
        "initial_position_component_change_max_m": float(np.max(np.abs(delta))), "seconds": weak_s}
    del bweak, cweak, weak

    # Recover deterministic events on the real network geometry. Native slip
    # detector identifies the breakpoint first; this is not a noisy detection-rate study.
    split_epoch, detector_events = detected_injection_epoch()
    candidates = sorted({r["arc"] for r in rows if r["station"] == "HOB2"})
    candidates = [arc for arc in candidates if {r["epoch"] for r in rows if r["arc"] == arc} == set(range(EPOCHS))]
    if not candidates:
        raise ValueError("No continuous HOB2 ambiguity arc for declared injection")
    arc = candidates[0]
    bs, cs, ns, ls, layout_s = build_system(rows, split=(arc, split_epoch))
    sa, _, ss = assemble(bs, cs)
    lookup = {name: i for i, name in enumerate(ns)}
    truth = np.zeros(len(ns))
    slip_m = ALPHA*LAMBDA1
    truth[lookup["ambiguity:"+arc+":injected"]] = slip_m
    for ei in range(split_epoch, EPOCHS):
        truth[lookup[f"clock:{ei}:R:HOB2"]] = 37.
        # A satellite clock step gives the opposite sign in the observations.
        truth[lookup[f"clock:{ei}:S:"+arc.split(":")[1]]]= -12.
    sy = sa@truth
    start_row = 0
    for b in bs:
        b.target = sy[start_row:start_row+len(b.target)]
        start_row += len(b.target)
    cs = (cs[0], sy[start_row:], cs[2])
    sd, sd_s = timed(dense_qr, sa, sy, ss)
    sr, sr_s = timed(eliminated_qr, bs, cs)
    err = sr.estimate-truth
    event_indices = [i for i, name in enumerate(ns) if name.startswith(("clock:", "ambiguity:"))]
    event_error = float(np.max(np.abs(err[event_indices])))
    if event_error > 1e-6:
        raise AssertionError(f"Noise-free event recovery failed: {event_error}")
    report["synthetic"] = {"arc": arc, "split_epoch": split_epoch,
        "event_gpst": "12:30:00", "unflagged_native_detector_events": detector_events,
        "receiver_clock_step_m": 37., "satellite_clock_step_m": -12., "l1_cycle_slip": 1,
        "if_ambiguity_step_m": slip_m, "max_clock_or_ambiguity_error_m": event_error,
        "max_formal_sigma_parameter_error": float(np.max(np.abs(err)/np.sqrt(np.diag(sr.covariance)))),
        "agreement": agreement(sd, sr, sa, ss, len(ls)), "dense_seconds": sd_s, "eliminated_seconds": sr_s,
        "limitation": "Noise-free injected linear observations on real geometry; no noisy detector completeness or orbit-accuracy claim"}
    report["status"] = "passed_stage4_linear_algebra_gate"
    report["elapsed_s"] = time.perf_counter()-started
    save()
    print(json.dumps({"status": report["status"], "parameters": len(names), "retained_parameters": layout["retained_parameters"],
        "real_agreement": report["real"]["agreement"], "datum": report["datum"],
        "prior_sensitivity": report["prior_sensitivity"], "synthetic": report["synthetic"],
        "elapsed_s": report["elapsed_s"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
