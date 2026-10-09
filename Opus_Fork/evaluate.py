"""Score any set of our fits against IGS final, with NGA PE always in the same table.

    python -m Opus_Fork.guard --profile fork8 --timeout 900 --label eval -- Opus_Fork.evaluate \
        --day 2026-08-02 --out-name arm1 \
        --arm P0 claude/runs/…/lin2-solve claude/runs/…/fixture.json \
        --arm W1 Opus_Fork/runs/…/lin2-solve Opus_Fork/runs/…/fixture.json \
        --domain full 00:00 23:45 --domain late 18:00 23:45

The objective is "closer to IGS final than NGA PE is", so this evaluator always adds NGA PE
as an arm and always scores on satellite-epochs common to every arm *and* NGA. A score
cannot be reported here without the bar beside it, and arms with different satellite sets
cannot be compared on different populations by accident.

References come from the single store by role and date, with their recorded hashes
re-verified, so the reference used is never ambiguous. Raw unaligned contract scores are
primary; the Helmert fit stays a separately labelled diagnostic. Evaluation only: the
estimator never reaches this module.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np

from customkf.frames import EarthOrientation
from customkf.prepare_stage2 import sha
from customkf.sp3 import epoch_tag

from .baseline import Fit, OnOrigin, compare
from .blocks import satellite_blocks, group
from .paths import ROOT, STAGE2, RESULTS
from .score import Declared, Product
from .store import find, resolve


def population_digest(keys):
    """SHA-256 of the sorted (satellite, GPS ns) population, so an analysis can show it scored exactly these samples,
    not merely as many (Astra N1, 6 Oct 2026). Equal to analyze_validation.key_digest for str/int keys."""
    return hashlib.sha256(repr(sorted((str(s), int(t)) for s, t in keys)).encode()).hexdigest()


def model_sha256(solution):
    """SHA-256 of the force_model.json beside a solution, or None for one that predates it. Recorded in each arm's
    provenance so an analysis can bind the scored model to its campaign's pin (Astra NR-03, 8 Oct 2026)."""
    model_file = Path(solution).parent/"force_model.json"
    return sha(model_file) if model_file.exists() else None


def midnight_of(day):
    y, m, d = day.split("-")
    return epoch_tag(f"* {y} {m} {d} 00 00 00")


def load_reference(role, day, midnight, eop, label, frame, legacy=None):
    path, entry = find(role, day)
    product = Product(path, Declared(f"{label} ({entry['name']})", frame, "COM", legacy_a_time_system=legacy),
                      midnight, eop)
    return product, dict(role=role, path=str(path), sha256=entry["sha256"], name=entry["name"],
                         frame=frame, declared_origin="COM", valid_samples=len(product.keys()))


def accept_arm(label, solution_dir, fixture, eop, *, allow_iterate=False):
    """Acceptance and frame binding for one arm; returns (fit presented in the plain-EOP inertial frame, provenance).

    Tightened 27-28 Sep 2026 (Astra review M11, C01; results/CORRECTIONS.md): converged only unless
    allow_iterate (then labelled a diagnostic); the supplied fixture must be the one bound to the solution; the
    Earth-fixed frame is chosen from the solution's own force_model.json (sub-daily EOP or plain), and an unknown model
    identifier is refused. A solution without force_model.json predates frame provenance: it is scored with the plain
    EOP and labelled "assumed". Plain arms score exactly as before.
    """
    from .experiments.subdaily.sd_scoring import fit_for
    from .export import KNOWN_SUBDAILY
    accepted = ("converged", "iteration_complete") if allow_iterate else ("converged",)
    solution = solution_dir/"solution.npz" if solution_dir.is_dir() else solution_dir
    step = json.loads((solution.parent/"step.json").read_text())
    if step["status"] not in accepted or sha(solution) != step["solution_sha256"]:
        raise ValueError(f"{label}: solution is not a verified converged checkpoint"
                         + ("" if allow_iterate else " (--diagnostic-allow-iterate scores an iterate as a diagnostic)"))
    bound = (step.get("binding") or {}).get("fixture")
    if bound is not None and bound != sha(fixture):
        raise ValueError(f"{label}: the supplied fixture is not the one bound to this solution")
    model_file = solution.parent/"force_model.json"
    subdaily = json.loads(model_file.read_text()).get("subdaily_eop") if model_file.exists() else None
    if subdaily and subdaily not in KNOWN_SUBDAILY:
        raise ValueError(f"{label}: unsupported Earth-orientation model {subdaily!r}")
    frame = subdaily or ("daily finals only" if model_file.exists() else "daily finals only (ASSUMED: no force_model.json)")
    return fit_for(solution, fixture, eop), dict(solution=str(solution), sha256=step["solution_sha256"],
                                                 fixture_sha256=sha(fixture), fixture_bound_in_step=bound is not None,
                                                 status=step["status"], earth_orientation=frame,
                                                 force_model_sha256=model_sha256(solution))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--out-name", required=True)
    parser.add_argument("--arm", nargs=3, action="append", required=True,
                        metavar=("LABEL", "SOLUTION_DIR", "FIXTURE"))
    parser.add_argument("--domain", nargs=3, action="append", required=True,
                        metavar=("NAME", "START", "END"))
    parser.add_argument("--baseline", default=None, help="arm to compare the others against; default the first")
    parser.add_argument("--no-nga", action="store_true", help="only if NGA PE is genuinely absent for this day")
    parser.add_argument("--diagnostic-allow-iterate", action="store_true",
                        help="also accept iteration_complete checkpoints; the output is then labelled a diagnostic")
    args = parser.parse_args()
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    midnight = midnight_of(args.day)
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(args.day).items()}

    reference, provenance = load_reference("reference_igs_final", args.day, midnight, eop, "IGS final", "IGc20")
    references = {"igs_final": provenance}

    candidates = {}
    for label, solution_dir, fixture in args.arm:
        fit, record = accept_arm(label, resolve(solution_dir), resolve(fixture), eop,
                                 allow_iterate=args.diagnostic_allow_iterate)
        candidates[label] = OnOrigin(fit, midnight)
        references[label] = record
    if not args.no_nga:
        nga, nga_provenance = load_reference("reference_nga_pe", args.day, midnight, eop,
                                             "NGA PE", "WGS84", legacy="GPS")
        candidates["NGA"] = nga
        references["NGA"] = nga_provenance

    # One common satellite-epoch set across the reference and every arm, so no arm is
    # scored on a population another arm does not have.
    common = set(reference.keys())
    for c in candidates.values():
        common &= c.keys()
    if not common:
        raise ValueError("No satellite-epochs common to the reference and every arm")

    report = dict(status=("DIAGNOSTIC_iterates_allowed_" if args.diagnostic_allow_iterate else "")+"evaluation_not_accuracy_acceptance",
                  day=args.day,
                  reference="IGS final", note="Raw unaligned contract scores on satellite-epochs "
                                              "common to every arm and to NGA PE.",
                  provenance=references, satellites=sorted({s for s, _ in common}),
                  common_samples=len(common), common_key_digest=population_digest(common),
                  earth_orientation_input=dict(path=str(STAGE2/"finals2000A.all"),
                                               sha256=sha(STAGE2/"finals2000A.all")),
                  domains={})

    class Restricted:
        def __init__(self, inner, keys):
            self.inner, self._keys, self.declared = inner, keys, inner.declared
        def keys(self):
            return self._keys
        def position(self, sat, t):
            return self.inner.position(sat, t)
        def velocity(self, sat, t):
            return self.inner.velocity(sat, t)
        def rotation(self, t):
            return self.inner.rotation(t)
        @property
        def origin_ns(self):
            return self.inner.origin_ns

    for name, start, end in args.domain:
        h0, m0 = map(int, start.split(":"))
        h1, m1 = map(int, end.split(":"))
        lo, hi = midnight+int((h0*3600+m0*60)*1e9), midnight+int((h1*3600+m1*60)*1e9)
        keys = {k for k in common if lo <= k[1] <= hi}
        if not keys:
            raise ValueError("Empty domain: "+name)
        window = dict(window=[start, end], samples=len(keys), key_digest=population_digest(keys), arms={})
        for label, candidate in candidates.items():
            window["arms"][label] = compare(Restricted(reference, keys), Restricted(candidate, keys),
                                            blocks, f"{label} vs IGS final, {name}")
        base = args.baseline or args.arm[0][0]
        for label, arm in window["arms"].items():
            if label != base:
                arm["vs_"+base] = dict(
                    ratio_3d=arm["raw"]["rms_3d_m"]/window["arms"][base]["raw"]["rms_3d_m"],
                    ratio_ure=arm["raw"]["rms_orbit_ure_m"]/window["arms"][base]["raw"]["rms_orbit_ure_m"])
            if "NGA" in window["arms"] and label != "NGA":
                arm["vs_NGA"] = dict(
                    ratio_3d=arm["raw"]["rms_3d_m"]/window["arms"]["NGA"]["raw"]["rms_3d_m"],
                    ratio_ure=arm["raw"]["rms_orbit_ure_m"]/window["arms"]["NGA"]["raw"]["rms_orbit_ure_m"],
                    satellites_we_beat=sorted(s for s in arm["per_satellite"]
                                              if arm["per_satellite"][s]["rms_3d_m"] <
                                              window["arms"]["NGA"]["per_satellite"][s]["rms_3d_m"]))
        report["domains"][name] = window

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/f"{args.out_name}.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/f"{args.out_name}.json").write_text(text)

    print(f"{args.day}: {len(report['satellites'])} satellites, {len(common)} common satellite-epochs\n")
    for name, window in report["domains"].items():
        print(f"--- {name} {window['window'][0]}-{window['window'][1]}, {window['samples']} samples ---")
        print(f"  {'arm':10s} {'3D cm':>8s} {'URE cm':>8s}  {'R/A/C cm':>22s} {'vs NGA 3D':>10s} {'beats NGA':>10s}")
        for label, arm in window["arms"].items():
            r = arm["raw"]
            rac = "/".join(f"{v*100:.2f}" for v in r["rms_rac_m"])
            ratio = arm.get("vs_NGA", {}).get("ratio_3d")
            beat = arm.get("vs_NGA", {}).get("satellites_we_beat")
            ratio_text = f"{ratio:.3f}" if ratio else "-"
            beat_text = f"{len(beat)}/{len(arm['per_satellite'])}" if beat is not None else "-"
            print(f"  {label:10s} {r['rms_3d_m']*100:8.3f} {r['rms_orbit_ure_m']*100:8.3f}  {rac:>22s} "
                  f"{ratio_text:>10s} {beat_text:>10s}")
        print()
    print("Wrote "+str(out/f"{args.out_name}.json"))


if __name__ == "__main__":
    main()
