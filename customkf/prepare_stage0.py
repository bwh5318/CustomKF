"""Pin a tiny, local development fixture set. Run through customkf.guard."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

from .sp3 import read_sp3

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "IGS0OPSFIN_20262140000_01D_15M_ORB.SP3", "nga24300.sp3",
    "IGS0OPSFIN_20260630000_01D_15M_ORB.SP3", "nga24083.sp3",
    "IGS0OPSRAP_20260630000_01D_15M_ORB.SP3",
]
SOURCES = ["analysis/geometry.py", "analysis/extract.py", "analysis/out/harmonics.csv",
           "backend/services/sp3_parser.py", "backend/services/coordinate_transforms.py",
           "backend/services/ure_calculator.py", "backend/models/sp3_data.py", "backend/utils/constants.py"]


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(path):
    return {"source_path":str(path.resolve()), "bytes":path.stat().st_size, "sha256":digest(path)}


def pin(source, destination):
    info = fingerprint(source)
    if destination.exists() and digest(destination) != info["sha256"]:
        raise ValueError(f"Refusing to replace a different pinned fixture: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(source, destination)
    if digest(destination) != info["sha256"]:
        raise ValueError("Copy hash mismatch")
    return {**info, "local_path":destination.relative_to(ROOT).as_posix()}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use python -m customkf.guard -- customkf.prepare_stage0")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", type=Path, default=Path(r"E:\pythontests\autocomparesp3"))
    args = parser.parse_args()
    legacy, target = args.legacy_root.resolve(), ROOT/"data"/"stage0"
    if (target/"manifest.json").exists():
        raise RuntimeError("Fixtures already pinned; run customkf.audit_stage0 to verify them")
    cache = legacy/"data"/"sp3_cache"
    sizes = [(cache/name).stat().st_size for name in FILES]
    if max(sizes) > 8*2**20 or sum(sizes) > 16*2**20:
        raise ValueError("Fixture size exceeded the declared small-set budget")
    manifest = {"schema":1, "created_utc":datetime.now(timezone.utc).isoformat(),
                "legacy_root":str(legacy), "sp3":[], "support":[],
                "source_code_and_selection_evidence":[fingerprint(legacy/name) for name in SOURCES],
                "purpose":"Development comparator fixtures; not a holdout or observation-derived product",
                "arrival_time_evidence":"Unavailable: cache timestamps are not archive publication times",
                "rapid_replay_eligible_as_estimation_inputs":False}
    for name in FILES:
        entry = pin(cache/name, target/name)
        product = read_sp3(target/name, legacy_a_time_system="GPS" if name.startswith("nga") else None)
        entry.update({"version":product.version, "frame":product.frame, "time_system":product.time_system,
                      "time_basis":"Explicit legacy SP3-a GPS convention" if product.version == "a" else "SP3 %c header",
                      "position_origin":"COM", "origin_evidence":product.comments,
                      "product_role":"NGA final legacy comparator" if name.startswith("nga") else
                                     ("IGS rapid evaluation reference" if "RAP" in name else "IGS final evaluation reference"),
                      "gps_records":len(product.samples),
                      "position_records_valid":sum(s.xyz_m is not None for s in product.samples.values()),
                      "epochs":len({s.epoch_ns for s in product.samples.values()}),
                      "velocity_records_ignored":product.velocity_records_ignored})
        manifest["sp3"].append(entry)
    for name in ("analysis/out/event_days.csv", "analysis/paper/paper_numbers.json"):
        manifest["support"].append(pin(legacy/name, target/Path(name).name))
    selected = []
    with open(legacy/"analysis/out/harmonics.csv", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row["date"],row["sat"]) in {("2026-08-02","G08"),("2026-08-02","G01")}:
                selected.append({"date":row["date"], "satellite":row["sat"],
                                 "legacy_beta_deg":float(row["beta"]),
                                 "legacy_eclipse_fraction":float(row["ecl"]),
                                 "role":"quiet development arc" if row["sat"] == "G08" else "eclipse development arc"})
    if len(selected) != 2:
        raise ValueError("Missing quiet/eclipse selection evidence")
    selected.append({"date":"2026-03-04", "satellite":"G20", "role":"predeclared historical event exclusion",
                     "mission_event_cause":"Unverified; this is an existing study outlier label, not a confirmed maneuver"})
    manifest["development_cases"] = selected
    manifest["selection_warning"] = "Beta/eclipse labels use the old approximate geometry; recompute with the future force-model ephemerides. No PRN-to-block mapping is adopted."
    manifest["copied_bytes"] = sum(e["bytes"] for e in manifest["sp3"]+manifest["support"])
    (target/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({"manifest":str(target/"manifest.json"), "copied_bytes":manifest["copied_bytes"],
                      "cases":selected}, indent=2))


if __name__ == "__main__":
    main()
