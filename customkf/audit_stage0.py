"""Bounded read-only parity audit of the pinned Stage 0 data and legacy source."""
import csv
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import sys

from .prepare_stage0 import ROOT, digest
from .sp3 import GPS_START, read_sp3, matched_samples


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use python -m customkf.guard -- customkf.audit_stage0")
    import numpy as np
    from threadpoolctl import threadpool_info
    from .comparison import rac_basis, rac_difference, summarize, orbit_ure_m

    target = ROOT/"data"/"stage0"
    manifest = json.loads((target/"manifest.json").read_text())
    checked = 0
    for entry in manifest["sp3"]+manifest["support"]+manifest["source_code_and_selection_evidence"]:
        path = ROOT/entry["local_path"] if "local_path" in entry else Path(entry["source_path"])
        if digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Pinned input/source changed: {path}")
        checked += 1
    # Reuse only the verified pure parser/math helpers; no backend server or downloader.
    legacy = Path(manifest["legacy_root"])
    sys.path.insert(0, str(legacy))
    from backend.services.sp3_parser import parse_sp3
    from backend.services.coordinate_transforms import ecef_to_rac
    from backend.services.ure_calculator import compute_ure
    geometry = load_module("legacy_geometry_stage0", legacy/"analysis/geometry.py")
    products, parser_checks = {}, []
    for entry in manifest["sp3"]:
        path = ROOT/entry["local_path"]
        product = read_sp3(path, legacy_a_time_system="GPS" if entry["version"] == "a" else None)
        old = parse_sp3(str(path))
        old_rows = {}
        for epoch in old.epochs:
            delta = epoch.datetime-GPS_START
            ns = (delta.days*86400+delta.seconds)*10**9+delta.microseconds*1000
            for sat,p in epoch.positions.items():
                if sat.startswith("G"):
                    old_rows[ns,sat] = np.array([p.x_km,p.y_km,p.z_km])*1000
        valid = {key:s for key,s in product.samples.items() if s.xyz_m is not None}
        if valid.keys() != old_rows.keys():
            raise AssertionError(f"Parser key parity failed: {path.name}")
        error = max(float(np.max(np.abs(np.asarray(s.xyz_m)-old_rows[key]))) for key,s in valid.items())
        if error != 0:
            raise AssertionError("Position parser parity was not exact")
        products[path.name] = product
        parser_checks.append({"file":path.name, "valid_gps_rows":len(valid), "max_position_difference_m":error,
                              "frame":product.frame, "invalid_gps_rows":len(product.samples)-len(valid)})

    with open(target/"event_days.csv", newline="") as stream:
        event_rows = list(csv.DictReader(stream))
    exclusions = {(row["date"],row["sat"]) for row in event_rows}
    result = {"status":"pass", "verified_fingerprints":checked, "parser_parity":parser_checks,
              "legacy_mode":"paper_compatibility: original approximate GMST, naive GPS calendar tags, np.gradient(edge_order=2), no frame alignment",
              "legacy_frame_warning":"Raw WGS84/G2296 versus IGc20/IGS20 coordinates. This reproduces the old study, not a verified realization transformation.",
              "days":[], "numerical_threadpools":threadpool_info()}
    for day, code, nga_name in (("2026-08-02","2026214","nga24300.sp3"),
                                 ("2026-03-04","2026063","nga24083.sp3")):
        ref = products[f"IGS0OPSFIN_{code}0000_01D_15M_ORB.SP3"]
        candidate = products[nga_name]
        try:
            matched_samples(ref,candidate,position_origin=("COM","COM"))
        except ValueError as exc:
            strict_message = str(exc)
        else:
            raise AssertionError("Expected different frame labels to be rejected")
        rows, clean, satellite_metrics = [], [], {}
        max_parity = max_3d = 0.
        flagged = excluded = 0
        for sat in sorted({s.sat for s in ref.samples.values()}):
            series = sorted((s for s in ref.samples.values() if s.sat == sat and s.xyz_m is not None),
                            key=lambda s:s.epoch_ns)
            if len(series) < 3:
                continue
            ts = [GPS_START+timedelta(microseconds=s.epoch_ns//1000) for s in series]
            pe = np.array([geometry.ecef_to_eci(s.xyz_m,t) for s,t in zip(series,ts)])
            seconds = np.array([(s.epoch_ns-series[0].epoch_ns)/1e9 for s in series])
            velocity = np.gradient(pe,seconds,axis=0,edge_order=2)
            sat_rows = []
            for k,s in enumerate(series):
                other = candidate.samples.get((s.epoch_ns,s.sat))
                if other is None or other.xyz_m is None:
                    continue
                delta = np.asarray(other.xyz_m)-s.xyz_m
                delta_eci = geometry.ecef_to_eci(delta,ts[k])
                old_rac = np.array([delta_eci@axis for axis in geometry.rac_frame(pe[k],velocity[k])])
                new_rac = rac_basis(pe[k],velocity[k])@delta_eci
                # Separately exercise the public candidate/reference interface.
                direct = rac_difference(pe[k],pe[k]+delta_eci,velocity[k])
                np.testing.assert_allclose(new_rac,old_rac,rtol=0,atol=1e-8)
                np.testing.assert_allclose(direct,old_rac,rtol=0,atol=1e-8)
                helper = ecef_to_rac(pe[k],pe[k]+delta_eci,velocity[k])
                np.testing.assert_allclose(direct,helper,rtol=0,atol=1e-8)
                max_parity = max(max_parity,float(np.max(np.abs(direct-old_rac))))
                max_3d = max(max_3d,float(np.linalg.norm(delta)))
                rows.append(new_rac)
                sat_rows.append(new_rac)
                flagged += int(s.maneuver or other.maneuver or s.orbit_predicted or other.orbit_predicted)
                if (day,sat) in exclusions:
                    excluded += 1
                else:
                    clean.append(new_rac)
            if sat_rows:
                satellite_metrics[sat] = summarize(sat_rows)
        result["days"].append({"date":day, "reference_frame":ref.frame, "candidate_frame":candidate.frame,
                               "strict_match_rejection":strict_message, "raw":summarize(rows),
                               "legacy_clean":summarize(clean), "predeclared_excluded_rows":excluded,
                               "orbit_flagged_rows_in_legacy_raw":flagged, "max_3d_m":max_3d,
                               "max_legacy_rac_parity_error_m":max_parity,
                               "development_satellites":{sat:satellite_metrics[sat] for sat in
                                                         (["G01","G08"] if day == "2026-08-02" else ["G20"])}})

    # Check against persisted outputs, not only against the same live geometry helper.
    harmonic_errors = []
    with open(legacy/"analysis/out/harmonics.csv", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["date"] == "2026-08-02" and row["sat"] in ("G01","G08"):
                expected = np.array([float(row[f"d{axis}_total"]) for axis in "RAC"])
                measured = np.array(result["days"][0]["development_satellites"][row["sat"]]["rms_rac_m"])
                np.testing.assert_allclose(measured,expected,rtol=0,atol=1e-7)
                harmonic_errors.append(float(np.max(np.abs(measured-expected))))
    if len(harmonic_errors) != 2:
        raise AssertionError("Missing stored RMS references")
    event = next(row for row in event_rows if row["date"] == "2026-03-04" and row["sat"] == "G20")
    event_error = abs(result["days"][1]["max_3d_m"]-float(event["max_3d_m"]))
    if event_error > 1e-6:
        raise AssertionError("Historical event magnitude not reproduced")
    result["stored_study_parity"] = {"max_component_rms_error_m":max(harmonic_errors), "event_max_3d_error_m":event_error}
    result["one_metre_radial_ure"] = {"canonical_m":float(orbit_ure_m([1,0,0])),
                                       "legacy_web_m":compute_ure(1,0,0,"G01")}
    fin = products["IGS0OPSFIN_20260630000_01D_15M_ORB.SP3"]
    rapid = products["IGS0OPSRAP_20260630000_01D_15M_ORB.SP3"]
    pairs, counts = matched_samples(fin,rapid,position_origin=("COM","COM"))
    differences = np.array([np.asarray(b.xyz_m)-a.xyz_m for a,b in pairs])
    result["same_frame_igs_rapid_minus_final"] = {"date":"2026-03-04", "frame":fin.frame, "counts":counts,
        "rms_3d_m":float(np.sqrt(np.mean(np.sum(differences**2,axis=1)))),
        "note":"Evaluation comparator check only; no own orbit has been estimated"}
    if not all(p["num_threads"] <= int(os.environ["MKL_NUM_THREADS"]) for p in result["numerical_threadpools"]):
        raise AssertionError("Numerical library thread limit exceeded")
    output = Path(os.environ["CUSTOMKF_RUN_DIR"])/"audit.json"
    output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
