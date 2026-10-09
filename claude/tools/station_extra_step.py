"""Guarded 15-station fixture (GUAM network plus one extra station) and one nonlinear iteration.

    customkf.guard --timeout 300 -- claude.tools.station_extra_step prepare --station PIMO
    customkf.guard --timeout 300 -- claude.tools.station_extra_step iterate --fixture PREPARE/fixture.json [--previous ITERATION]

customkf/stage5_pilot.prepare accepts only its built-in marker map and verifies every station file
against a manifest inside data/stage3. Claude does not write to data/, so preparation instead:

1. Builds claude/data/stage3-mirror/: byte-identical copies of exactly the inputs prepare() reads,
   each verified against Astra's pinned hash first, plus the separately acquired extra station and a
   manifest of its own. Astra's data/ is untouched.
2. Patches the station map and data path on the imported module at runtime only, the same technique
   Astra's own wet_pilot and stability_step use. No root file is edited.
3. Calls the unchanged prepare() and then requires the 14 existing stations' rows, seeds, station
   metadata, input hashes, rejected satellites and arc context to be identical to the archived GUAM
   fixture. Any difference stops the run.

The estimator, force model, priors, weights, clock datum and ambiguity handling are unchanged, and
the result is a diagnostic, never a replacement baseline. Writes only into the guard directory and
the mirror.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np

import customkf.stage5_pilot as pilot_module
from customkf.stage5b_step import freeze
from customkf.reduced_network import MAX_ROWS, MAX_PARAMETERS, WORKSPACE_BYTES
from claude.tools import ablation_step as engine
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)
MIRROR = ROOT / "claude/data/stage3-mirror"
ACQUIRED = ROOT / "claude/data/acquired"
EXTRA_MARKERS = {"PIMO": "PIMO00PHL", "POHN": "POHN00FSM", "GUAM": "GUAM00GUM"}
REFERENCE_INPUTS = ("igs20.atx", "IGc20.ssc", "soln_IGc20.snx", "psd_IGc20.snx", "FES2014b.BLQ",
                    "BRDC00WRD_R_20262140000_01D_MN.rnx.gz")


def build_mirror(station, baseline_context):
    """Hash-verified copies of exactly the inputs prepare() reads, plus the extra station."""
    pinned = {}
    for path in (ROOT / "data/stage3").glob("*manifest.json"):
        for entry in json.loads(path.read_text()).get("files", []):
            pinned[entry["path"]] = entry["sha256"]
    # Take the names from the baseline fixture's own input list. A header MARKER NAME field is four
    # characters at some stations and nine at others, so it cannot be used to build file names.
    names = [Path(key).name for key in baseline_context["inputs"] if key.startswith("data/stage3/")]
    missing = [name for name in REFERENCE_INPUTS if name not in names]
    if missing:
        raise ValueError("Baseline inputs lack expected reference files: " + ", ".join(missing))
    if len(names) != len(REFERENCE_INPUTS) + len(baseline_context["stations"]):
        raise ValueError("Unexpected Stage 3 input count in the baseline fixture")
    extra_name = f"{EXTRA_MARKERS[station]}_R_20262140000_01D_30S_MO.rnx.gz"
    MIRROR.mkdir(parents=True, exist_ok=True)
    entries, record = [], {}
    for name in names + [extra_name]:
        extra = name == extra_name
        source = (ACQUIRED if extra else ROOT / "data/stage3") / name
        digest = sha(source)
        if not extra:
            relative = f"data/stage3/{name}"
            if pinned.get(relative) != digest:
                raise ValueError("Mirror source is not Astra's pinned input: " + relative)
        target = MIRROR / name
        if not target.exists() or sha(target) != digest:
            shutil.copyfile(source, target)
        if sha(target) != digest:
            raise ValueError("Mirror copy mismatch: " + name)
        entries.append({"path": target.relative_to(ROOT).as_posix(), "bytes": target.stat().st_size,
                        "sha256": digest, "origin": source.relative_to(ROOT).as_posix(),
                        "pinned_by_astra": not extra})
        record[name] = digest
    expected = set(names) | {extra_name, "claude_mirror_manifest.json"}
    for stale in sorted(MIRROR.iterdir()):
        if stale.is_file() and stale.name not in expected:
            stale.unlink()
    manifest = MIRROR / "claude_mirror_manifest.json"
    manifest.write_text(json.dumps({
        "purpose": "Claude-side byte-identical mirror of the Stage 3 inputs that stage5_pilot.prepare reads, plus one "
                   "separately acquired station, so a 15-station diagnostic fixture can be built without writing to data/.",
        "files": entries}, indent=2) + "\n")
    return record, sha(manifest), extra_name


def prepare(args, folder):
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    baseline_path = GUAM / "prepare/fixture.json"
    assert sha(baseline_path) == base["artifacts_sha256"]["prepare/fixture.json"]
    old = json.loads(baseline_path.read_text())
    mirror, mirror_manifest_sha256, extra_name = build_mirror(args.station, old["context"])
    # prepare() appends rows station by station in iteration order, and the baseline fixture's own
    # station dict preserves Astra's order, so reuse it and append the extra station last.
    stations = list(old["context"]["stations"]) + [args.station]
    # Runtime-only injection: the root module file is not modified.
    pilot_module.STATIONS = {**pilot_module.STATIONS, args.station: EXTRA_MARKERS[args.station]}
    pilot_module.DATA = MIRROR
    context, rows, seeds = pilot_module.prepare(step_s=old["context"]["step_s"], epoch_count=old["context"]["epoch_count"],
                                               station_subset=stations, profile=old["context"]["profile"])
    fixture = folder / "fixture.json"
    freeze(context, rows, seeds, fixture, f"guam-plus-{args.station.lower()}")
    fresh = json.loads(fixture.read_text())
    existing = [r for r in fresh["rows"] if r["station"] != args.station]
    if existing != old["rows"]:
        order_only = (sorted(json.dumps(r, sort_keys=True) for r in existing)
                      == sorted(json.dumps(r, sort_keys=True) for r in old["rows"]))
        raise ValueError(f"Existing stations' retained rows changed: {len(existing)} rows versus "
                         f"{len(old['rows'])}; identical content in a different order: {order_only}")
    if fresh["seeds"] != old["seeds"]:
        raise ValueError("Broadcast seeds or satellite eligibility changed")
    if {s: v for s, v in fresh["context"]["stations"].items() if s != args.station} != old["context"]["stations"]:
        raise ValueError("Existing station metadata changed")
    for key in ("rejected_satellites", "duration_s", "epoch_count", "step_s", "profile", "navigation_cutoff_ns"):
        if fresh["context"][key] != old["context"][key]:
            raise ValueError("Arc context changed: " + key)
    old_inputs = {Path(k).name: v for k, v in old["context"]["inputs"].items()}
    new_inputs = {Path(k).name: v for k, v in fresh["context"]["inputs"].items()}
    if any(new_inputs.get(name) != digest for name, digest in old_inputs.items()):
        raise ValueError("Mirrored inputs differ in content from the pinned originals")
    if sorted(set(new_inputs) - set(old_inputs)) != [extra_name]:
        raise ValueError("Unexpected extra inputs: " + ", ".join(sorted(set(new_inputs) - set(old_inputs))))
    pilot = engine.build_pilot(fixture)
    counts = {}
    for row in pilot.rows:
        counts[row["arc"]] = counts.get(row["arc"], 0) + 1
    phase = sum(n for n in counts.values() if n >= 3)
    local = sum(map(len, pilot.local_names))
    m = len(pilot.rows) + phase + len(pilot.prior_sigma) + len(pilot.stations)
    largest = max(sum(2 if r["arc"] in pilot.arcs else 1 for r in pilot.rows if r["epoch"] == ei)
                  for ei in range(pilot.epoch_count))
    workspace = 8 * (5 * m * pilot.n + 4 * largest**2 + 3 * local * pilot.n + 6 * pilot.n**2)
    if m > MAX_ROWS or pilot.n > MAX_PARAMETERS or workspace > WORKSPACE_BYTES:
        raise ValueError("Preflight row/retained/workspace budget exceeded")
    extra_rows = [r for r in fresh["rows"] if r["station"] == args.station]
    elevation = [float(np.degrees(np.arcsin(.9 / r["sigma"][0]))) for r in extra_rows]
    report = {"status": "prepared", "case": fresh["case"], "station": args.station, "source_policy": policy,
              "mirror": {"directory": MIRROR.relative_to(ROOT).as_posix(), "manifest_sha256": mirror_manifest_sha256,
                         "files_sha256": mirror, "astra_data_unmodified": True},
              "invariance": "existing rows, seeds, station metadata, input contents and arc context identical to the GUAM fixture",
              "extra_station": {"links": len(extra_rows), "satellites": sorted({r["satellite"] for r in extra_rows}),
                                "epochs": sorted({r["epoch"] for r in extra_rows}),
                                "elevation_deg": {"min": min(elevation), "median": float(np.median(elevation)), "max": max(elevation)}},
              "code_rows": len(pilot.rows), "phase_rows": phase, "prior_rows": len(pilot.prior_sigma) + len(pilot.stations),
              "retained_parameters": pilot.n, "local_clock_parameters": local, "design_rows": m,
              "workspace_estimate_mib": workspace / 2**20, "budget_pass": True,
              "satellites": pilot.sats, "fixture_sha256": sha(fixture), "source_sha256": engine.sources(),
              "worker_sha256": sha(Path(__file__))}
    engine.write_json(folder / "step.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_sha256", "satellites", "source_policy", "mirror")}, indent=2), flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "iterate"))
    parser.add_argument("--station", choices=sorted(EXTRA_MARKERS))
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    sys.addaudithook(pilot_module.forbid_precise_product_reads)
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    if args.mode == "iterate":
        engine.iterate(argparse.Namespace(fixture=args.fixture, previous=args.previous), folder)
        return
    prepare(args, folder)


if __name__ == "__main__":
    main()
