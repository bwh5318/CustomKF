"""Write a solution out as an SP3 orbit product, and prove the file says what we meant.

    self-test: python -m Opus_Fork.guard --profile fork8 --timeout 300 --label export-selftest \
                   -- Opus_Fork.export selftest
    export:    ... -- Opus_Fork.export write --solution DIR --fixture FIXTURE --day 2026-08-02 \
                   --out Opus_Fork/datastore/products/OPUS_20262140000.SP3 [--cadence 900]

Until now a "result" was a `.npz` array of inertial states. That is not a product: nothing
downstream can read it, no convention is declared in it, and there is no check that what was
written is what was computed. `claude/reviews/opus_support_20260919/PRODUCT_READINESS.md` names
this gap directly.

What this writes, and what it deliberately refuses to write:

- **Positions only.** The fit's per-epoch satellite clocks are nuisance parameters, not a
  calibrated clock product, so every clock field is the SP3 missing sentinel 999999.999999.
  Writing them as if they were a product would be the single easiest way to mislead someone.
- **Centre of mass, IGc20, GPS time**, all declared in the header, because the comparison
  contract requires the origin and frame to be stated rather than inferred.
- **No orbit is flagged predicted or manoeuvred** unless the caller says so, and the caller
  has no way to say so yet, so the flag columns stay blank rather than claiming a screening
  that has not happened.
- **Accuracy exponents** come from the solution's own formal position sigma when the retained
  covariance is present, and are left 0 ("unknown") otherwise. They are formal, and the header
  comment says so.

The QA gate re-reads the file with `customkf.sp3.read_sp3` — the same strict reader used for
IGS and NGA products — and compares every position against the source state. SP3 stores
kilometres to six decimals, so the tolerance is half a millimetre of quantization and nothing
more. A file that does not pass is not left on disk.

**Corrected 27 Sep 2026 (Astra review C01, N03; `results/CORRECTIONS.md`).**
- The Earth-fixed rotation is now chosen from the solution's own `force_model.json`. Solutions fitted with the IERS 2010
  sub-daily EOP (`subdaily_eop` in the binding) are rotated with it. Before this fix they were silently rotated with
  the plain daily EOP: 4.9 cm RMS wrong, and QA passed because it only checked the writer against itself. An
  unrecognized model identifier is refused. The model used is written into the header comments and the result.
- The supplied fixture must be the one bound in the solution's `step.json`.
- The header start epoch, epoch count and interval are derived from the emitted epochs. `verify` checks them against
  the file's body. A noon-start file had been labelled midnight.
- Accuracy codes are written 0 (unknown). A formal initial-state sigma is not a calibrated orbit accuracy. The formal
  values are kept in the JSON result as a diagnostic.
- New mode `roundtrip`: export each given solution, then rebuild every position independently through the scoring
  path (`experiments/subdaily/sd_scoring`) and compare. A forced plain-EOP export of a sub-daily solution must fail
  that comparison (negative control).
"""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import numpy as np

from customkf.frames import EarthOrientation, FrameEpoch
from customkf.prepare_stage2 import sha
from customkf.sp3 import epoch_tag, read_sp3, GPS_START

from .paths import STAGE2, STORE, RESULTS
from .store import resolve

QUANTUM_M = 1e-3                 # SP3 position resolution: 1e-6 km
TOLERANCE_M = 5.1e-4             # half a quantum, plus a rounding hair
MISSING_CLOCK = 999999.999999
COMMENT_WIDTH = 57               # SP3 "/* " comment text


def accuracy_exponent(sigma_m):
    """SP3 accuracy code: the exponent b such that 2**b millimetres bounds the sigma."""
    if sigma_m is None or not np.isfinite(sigma_m) or sigma_m <= 0:
        return 0
    return int(min(99, max(1, np.ceil(np.log2(max(sigma_m*1000.0, 1.0))))))


def header_lines(day, epochs_out, satellites, accuracy, *, agency, frame, comments):
    """epochs_out: emitted epochs in GPS seconds since GPS_START. The header describes *those* epochs (N03)."""
    first = GPS_START+timedelta(seconds=epochs_out[0])
    week, seconds = divmod(epochs_out[0], 604800.0)
    day_start = datetime(first.year, first.month, first.day)
    mjd = (day_start-datetime(1858, 11, 17)).days
    fraction = (first-day_start).total_seconds()/86400.0
    interval = epochs_out[1]-epochs_out[0] if len(epochs_out) > 1 else 900.0
    lines = [f"#dP{first.year:4d} {first.month:2d} {first.day:2d} {first.hour:2d} {first.minute:2d} "
             f"{first.second+first.microsecond/1e6:11.8f} {len(epochs_out):7d} ORBIT {frame:5s} FIT {agency:4s}",
             f"## {int(week):4d} {seconds:15.8f} {interval:14.8f} {mjd:5d} {fraction:15.13f}"]
    ids = list(satellites)
    rows = [ids[i:i+17] for i in range(0, max(len(ids), 1), 17)] or [[]]
    while len(rows) < 5:
        rows.append([])
    for i, row in enumerate(rows):
        prefix = f"+  {len(ids):3d}   " if i == 0 else "+        "
        lines.append(prefix+"".join(f"{s:>3s}" for s in row)+"  0"*(17-len(row)))
    for i, row in enumerate(rows):
        lines.append("++       "+"".join(f"{accuracy.get(s, 0):3d}" for s in row)+"  0"*(17-len(row)))
    lines += ["%c G  cc GPS ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
              "%c cc cc ccc ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
              "%f  0.0000000  0.000000000  0.00000000000  0.000000000000000",
              "%f  0.0000000  0.000000000  0.00000000000  0.000000000000000",
              "%i    0    0    0    0      0      0      0      0         0",
              "%i    0    0    0    0      0      0      0      0         0"]
    for text in comments:
        if len(text) > COMMENT_WIDTH:       # truncation once cut every product's latency label (3 Oct 2026)
            raise ValueError(f"SP3 comment longer than {COMMENT_WIDTH} characters: {text!r}")
        lines.append("/* "+text.ljust(COMMENT_WIDTH))
    while len(lines) < 22:
        lines.append("/* "+" "*57)
    return lines


def standard_comments(subdaily):
    return ["SATELLITE CENTRE OF MASS (SATCOM)",
            "GPS ONLY, STATION OBS/NAV FIT, NO EXTERNAL ORBIT USED",
            "CLOCKS NOT PROVIDED: FIT CLOCKS ARE NUISANCE PARAMETERS",
            "ACCURACY CODES 0 = UNKNOWN (NOT CALIBRATED)",
            "EOP: "+("DAILY FINALS + IERS2010 ORTHO_EOP SUBDAILY" if subdaily else "DAILY FINALS ONLY"),
            # Until 3 Oct 2026 "...LATENCY-CERTIFIED RAPID PRODUCT" (59 characters), written cut to "...RAPID PRODU".
            "RETROSPECTIVE INPUTS: NOT A LATENCY-CERTIFIED PRODUCT"]


def write_sp3(path, day, times_ns, states_ecef, accuracy, *, agency="OPUS", frame="IGc20", comments=()):
    """states_ecef: {(sat, gps_ns): xyz metres}. Clocks are written missing, deliberately."""
    satellites = sorted({s for s, _ in states_ecef})
    epochs_out = sorted(times_ns)
    out = header_lines(day, [t/1e9 for t in epochs_out], satellites, accuracy,
                       agency=agency, frame=frame, comments=comments)
    for ns in epochs_out:
        moment = GPS_START+timedelta(seconds=ns/1e9)
        out.append(f"*  {moment.year:4d} {moment.month:2d} {moment.day:2d} {moment.hour:2d} "
                   f"{moment.minute:2d} {moment.second+moment.microsecond/1e6:11.8f}")
        for sat in satellites:
            xyz = states_ecef.get((sat, ns))
            if xyz is None:
                continue
            km = np.asarray(xyz, dtype=float)/1000.0
            if not np.isfinite(km).all() or np.any(np.abs(km) >= 999999):
                raise ValueError(f"Refusing to write a nonfinite or out-of-range position: {sat} {ns}")
            out.append(f"P{sat}{km[0]:14.6f}{km[1]:14.6f}{km[2]:14.6f}{MISSING_CLOCK:14.6f}")
    out.append("EOF")
    Path(path).write_text("\n".join(out)+"\n", encoding="ascii", newline="\n")
    return len(epochs_out), len(satellites)


def header_consistency(path, epochs_ns):
    """N03: the header's start epoch, epoch count and interval must describe the body's epochs."""
    lines = Path(path).read_text(encoding="ascii").splitlines()
    issues = []
    f = lines[0][3:].split()
    y, mo, d, h, mi = (int(v) for v in f[:5])
    sec, count = float(f[5]), int(f[6])
    start = GPS_START+timedelta(seconds=epochs_ns[0]/1e9)
    head = datetime(y, mo, d, h, mi)+timedelta(seconds=sec)
    if abs((head-start).total_seconds()) > 1e-6:
        issues.append(f"header start {head.isoformat()} != first epoch {start.isoformat()}")
    if count != len(epochs_ns):
        issues.append(f"header count {count} != {len(epochs_ns)} epochs")
    g = lines[1][2:].split()
    week, sow, interval = int(g[0]), float(g[1]), float(g[2])
    if abs(week*604800.0+sow-epochs_ns[0]/1e9) > 1e-6:
        issues.append("header GPS week/seconds do not match the first epoch")
    steps = np.diff(np.array(epochs_ns, dtype=np.int64))/1e9
    if len(steps) and (np.any(np.abs(steps-interval) > 1e-6)):
        issues.append(f"epochs are not uniformly spaced at the header interval {interval} s")
    return issues


def verify(path, states_ecef, *, frame="IGc20"):
    """Re-read with the strict reader and compare every position against the source; check the header too."""
    product = read_sp3(path)
    issues, worst = [], 0.0
    issues += header_consistency(path, sorted({t for _, t in states_ecef}))
    if product.frame != frame:
        issues.append(f"frame read back as {product.frame!r}")
    if product.time_system != "GPS":
        issues.append(f"time system read back as {product.time_system!r}")
    written = {(s.sat, s.epoch_ns) for s in product.samples.values() if s.xyz_m is not None}
    if written != set(states_ecef):
        issues.append(f"sample set differs: wrote {len(states_ecef)}, read {len(written)}")
    for key, source in states_ecef.items():
        sample = product.samples.get((key[1], key[0]))
        if sample is None or sample.xyz_m is None:
            issues.append(f"missing on read back: {key[0]} {key[1]}")
            continue
        error = float(np.max(np.abs(np.asarray(sample.xyz_m)-np.asarray(source))))
        worst = max(worst, error)
        if sample.clock_s is not None:
            issues.append(f"clock unexpectedly present for {key[0]}")
    if worst > TOLERANCE_M:
        issues.append(f"round-trip position error {worst*1000:.4f} mm exceeds {TOLERANCE_M*1000:.2f} mm")
    return dict(passed=not issues, issues=issues, worst_round_trip_mm=worst*1000,
                epochs=len({e for _, e in written}), satellites=len({s for s, _ in written}),
                samples=len(written), frame=product.frame, time_system=product.time_system,
                velocity_records=product.velocity_records_ignored)


def selftest(args, folder):
    """Round-trip synthetic states: format, quantization and the strict reader, end to end."""
    day = "2026-08-02"
    midnight = epoch_tag("* 2026 08 02 00 00 00")
    rng = np.random.default_rng(20260920)
    states, accuracy = {}, {}
    satellites = [f"G{i:02d}" for i in (1, 5, 13, 21, 32)]
    for sat in satellites:
        accuracy[sat] = accuracy_exponent(0.05)
        base = rng.normal(0, 1, 3)
        base = base/np.linalg.norm(base)*26_560_000.0
        for k in range(96):
            angle = 2*np.pi*k/96
            xyz = base*np.cos(angle)+np.cross([0, 0, 1.0], base)*np.sin(angle)
            states[sat, midnight+int(k*900*1e9)] = xyz
    path = folder/"selftest.SP3"
    epochs, sats = write_sp3(path, day, sorted({t for _, t in states}), states, accuracy,
                             comments=["SELF TEST, SYNTHETIC POSITIONS, NOT A PRODUCT"])
    result = verify(path, states)
    result.update(wrote_epochs=epochs, wrote_satellites=sats, bytes=path.stat().st_size)

    # An out-of-range position must be refused rather than silently truncated.
    try:
        write_sp3(folder/"bad.SP3", day, [midnight], {("G01", midnight): (1e12, 0, 0)}, {})
        result["refuses_out_of_range"] = False
    except ValueError:
        result["refuses_out_of_range"] = True
    # A nonfinite position likewise.
    try:
        write_sp3(folder/"bad.SP3", day, [midnight], {("G01", midnight): (np.nan, 0, 0)}, {})
        result["refuses_nonfinite"] = False
    except ValueError:
        result["refuses_nonfinite"] = True
    # N03: a partial-day (noon-start) file must describe itself correctly and pass.
    noon = midnight+int(12*3600*1e9)
    part = {k: v for k, v in states.items() if k[1] >= noon}
    write_sp3(folder/"noon.SP3", day, sorted({t for _, t in part}), part, {}, comments=["SELF TEST, NOON START"])
    noon_check = verify(folder/"noon.SP3", part)
    result["partial_day_passes"] = noon_check["passed"]
    # ... and the old bug, a midnight header over noon data, must now be caught.
    text = (folder/"noon.SP3").read_text(encoding="ascii").splitlines()
    text[0] = text[0][:3]+"2026  8  2  0  0  0.00000000"+text[0][31:]
    (folder/"noon_badheader.SP3").write_text("\n".join(text)+"\n", encoding="ascii", newline="\n")
    result["mislabelled_header_caught"] = not verify(folder/"noon_badheader.SP3", part)["passed"]
    result["passed"] = bool(result["passed"] and result["refuses_out_of_range"] and result["refuses_nonfinite"]
                            and result["partial_day_passes"] and result["mislabelled_header_caught"])
    return result


# C01: the Earth-orientation model a solution was fitted with, read from its own provenance.
KNOWN_SUBDAILY = {
    "IERS 2010 ORTHO_EOP ocean-tidal diurnal/semidiurnal x, y, UT1 (no libration)": "subdaily_eop",
}


def earth_orientation_for(solution_path, *, force_plain=False, assume_plain=False):
    """Return (EarthOrientation instance, description, provenance dict) for the model the solution was fitted with.

    A solution without `force_model.json` carries no frame provenance. Since 28 Sep 2026 (review ledger follow-up to
    C01) that is refused unless the caller declares `assume_plain` (older fits made before provenance was recorded).
    """
    model_file = Path(solution_path).parent/"force_model.json"
    binding = json.loads(model_file.read_text()) if model_file.exists() else None
    plain = EarthOrientation(STAGE2/"finals2000A.all")
    plain.subdaily = None
    info = dict(force_model_json=str(model_file) if binding is not None else None,
                subdaily_eop=(binding or {}).get("subdaily_eop"))
    if force_plain:
        return plain, "NEGATIVE CONTROL: daily finals only, forced", dict(info, negative_control=True)
    if binding is None:
        if not assume_plain:
            raise ValueError(f"No force_model.json beside {solution_path}: frame model unknown "
                             "(pass --assume-plain-eop only for a fit known to predate sub-daily EOP)")
        return plain, "daily IERS finals (ASSUMED: the solution records no frame provenance)", dict(info, assumed_plain=True)
    if not binding.get("subdaily_eop"):
        return plain, "daily IERS finals (no sub-daily model in the solution's provenance)", info
    module = KNOWN_SUBDAILY.get(binding["subdaily_eop"])
    if module is None:
        raise ValueError(f"Unsupported Earth-orientation model in {model_file}: {binding['subdaily_eop']!r}")
    from . import subdaily_eop
    subdaily_eop.verify_sources()
    subdaily_eop.self_test()
    eop = subdaily_eop.earth_orientation_class()(STAGE2/"finals2000A.all")
    info.update(recorded_subdaily_eop_sha256=binding.get("subdaily_eop_sha256"),
                current_subdaily_eop_sha256=sha(Path(subdaily_eop.__file__)))
    return eop, "daily IERS finals + IERS 2010 ORTHO_EOP sub-daily (ocean tides)", info


# A-priori tropospheric gradients (Opus_Fork/gradients.py), named in the product (user adoption, 3 Oct 2026: GRAD
# operational as an optional, labelled model for final-latency products; experiments/gradients/VALIDATION_RESULTS.md).
# source -> (header comments, product-type code in the default file name or None for the default's).
# "FIN" is this project's local file-name category separating gradient products from the default's "RAP" path; it
# does not certify an IGS product class, a delivery deadline or operational latency. The latency comment read
# "LATENCY: FINAL CLASS (GRADIENT INPUT ~2 DAYS AFTER DAY)" until 5 Oct 2026 (Astra review R03: Last-Modified is not
# a verified issue time); products written before then keep their bytes.
GRADIENT_LABELS = {
    "grad_op": (["TROPO GRADIENTS: TU WIEN GRAD OPERATIONAL, A PRIORI",
                 "LATENCY: RETROSPECTIVE; ISSUE TIME NOT VERIFIED"], "FIN"),
    "gpt3": (["TROPO GRADIENTS: GPT3 EMPIRICAL, A PRIORI (NOT ADOPTED)"], None),
}


def gradients_for(solution_path):
    """(header comments, product-type code or None, provenance or None) for the solution's a-priori gradients."""
    model_file = Path(solution_path).parent/"force_model.json"
    binding = json.loads(model_file.read_text()) if model_file.exists() else {}
    recorded = binding.get("gradients")
    if not recorded:
        return [], None, None
    if recorded.get("source") not in GRADIENT_LABELS:
        raise ValueError(f"Unsupported gradient model in {model_file}: {recorded.get('source')!r}")
    comments, kind = GRADIENT_LABELS[recorded["source"]]
    return list(comments), kind, recorded


def write_from_solution(args, folder):
    solution_dir = resolve(args.solution)
    solution = solution_dir/"solution.npz" if solution_dir.is_dir() else solution_dir
    step = json.loads((solution.parent/"step.json").read_text())
    if step["status"] != "converged" or sha(solution) != step["solution_sha256"]:
        raise ValueError("Refusing to export anything but a verified converged solution")
    fixture = resolve(args.fixture)
    bound = (step.get("binding") or {}).get("fixture")
    if bound is not None and bound != sha(fixture):
        raise ValueError("The supplied fixture is not the one bound to this solution")
    origin = int(json.loads(fixture.read_text())["context"]["origin_ns"])
    gradient_comments, kind, gradient_info = gradients_for(solution)
    eop, eop_description, eop_info = earth_orientation_for(solution, force_plain=getattr(args, "force_plain_eop", False),
                                                           assume_plain=getattr(args, "assume_plain_eop", False))
    epoch = FrameEpoch(origin, eop)
    with np.load(solution) as f:          # read each member once; NpzFile re-reads on access
        satellites = [str(s) for s in f["satellites"]]
        times = [float(t) for t in f["times_s"]]
        inertial = np.array(f["states"][:, :, :3], dtype=float)
        names = [str(n) for n in f["names"]]
        covariance = np.array(f["retained_covariance"]) if "retained_covariance" in f.files else None

    # N03: accuracy codes are written 0 (unknown). The formal initial-state sigma is kept only as a diagnostic.
    accuracy, formal_sigma_m = {}, {}
    if covariance is not None:
        retained = [n for n in names if not n.startswith("clock")]
        index = {n: i for i, n in enumerate(retained)}
        diagonal = np.diag(covariance)
        for sat in satellites:
            keys = [f"orbit:{sat}:{k}" for k in range(3)]
            if all(k in index for k in keys):
                formal_sigma_m[sat] = float(np.sqrt(sum(diagonal[index[k]] for k in keys)))

    y, m, d = args.day.split("-")
    midnight = epoch_tag(f"* {y} {m} {d} 00 00 00")
    states, rotations, skipped = {}, {}, 0
    for si, sat in enumerate(satellites):
        for ti, t in enumerate(times):
            ns = origin+int(round(t*1e9))
            if (ns-midnight) % int(args.cadence*1e9) or not 0 <= ns-midnight < 86400*10**9:
                skipped += 1
                continue
            if t not in rotations:
                rotations[t] = epoch.celestial_to_terrestrial(t)
            states[sat, ns] = rotations[t]@inertial[si, ti]
    if not states:
        raise ValueError("No saved state lands on the requested output cadence")

    if eop_info.get("negative_control"):
        out = Path(folder)/f"NEGATIVE_CONTROL_{args.day.replace('-','')}_{solution.parent.parent.name[:40]}.SP3"   # never into the product store
    else:
        out = destination(args, kind, step["solution_sha256"])
    out.parent.mkdir(parents=True, exist_ok=True)
    comments = standard_comments(bool(eop_info.get("subdaily_eop") and not eop_info.get("negative_control")))+gradient_comments
    (epochs, sats), result, size, digest = write_verified(
        out, lambda path: write_sp3(path, args.day, sorted({t for _, t in states}), states, accuracy, comments=comments),
        lambda path: verify(path, states))
    result.update(output=str(out), wrote_epochs=epochs, wrote_satellites=sats,
                  cadence_s=args.cadence, states_skipped_off_cadence=skipped,
                  bytes=size, sha256=digest,
                  source_solution=str(solution), source_solution_sha256=step["solution_sha256"],
                  fixture=str(fixture), fixture_bound_in_step=bound is not None,
                  earth_orientation=eop_description, earth_orientation_provenance=eop_info,
                  gradients=gradient_info, product_type=kind or "RAP",
                  accuracy_codes="0 (unknown) for every satellite",
                  formal_initial_position_sigma_m_diagnostic=formal_sigma_m)
    if not result["passed"]:
        result["output"] = "not written: QA gate failed (the verified temporary file was discarded)"
    return result


def destination(args, kind, solution_sha256):
    """The output path: --out, or a store name that carries the solution's identity, so two configurations or
    solutions on one day never share a default destination (Astra PI-09, 8 Oct 2026)."""
    if args.out:
        return Path(args.out)
    return STORE/"products"/f"OPUS0OPS{kind or 'RAP'}_{args.day.replace('-', '')}_{solution_sha256[:12]}.SP3"


def write_verified(out, write, check):
    """Write through a temporary sibling, check it, and move it into place only if it passed (PI-09).

    An existing destination is never replaced or deleted: it is refused before anything is written. Returns
    (write's return value, check's result, size in bytes, SHA-256), the last two None when the check failed."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} exists; refusing to overwrite an earlier product")
    temporary = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    try:
        written = write(temporary)
        result = check(temporary)
        size = digest = None
        if result["passed"]:
            size, digest = temporary.stat().st_size, sha(temporary)
            if out.exists():
                raise FileExistsError(f"{out} appeared while exporting; refusing to overwrite it")
            os.replace(temporary, out)
        return written, result, size, digest
    finally:
        temporary.unlink(missing_ok=True)


def roundtrip(args, folder):
    """C01 check: export each solution, then rebuild every position through the scoring path and compare.

    The scoring path (`experiments/subdaily/sd_scoring.fit_for`) presents a solution in the plain-EOP inertial frame the
    evaluators use. Rotating that with the plain EOP gives the Earth-fixed product the scores describe. The exported
    file must match it to SP3 quantization. A forced plain-EOP export of a sub-daily solution is the negative control
    and must fail.
    """
    from .experiments.subdaily.sd_scoring import fit_for
    out = dict(cases=[])
    plain = EarthOrientation(STAGE2/"finals2000A.all")
    plain.subdaily = None
    for spec in args.pairs:
        solution_dir, fixture, day = spec.split("::")
        case = {"solution": solution_dir, "day": day}
        for control in (False, True):
            tag = Path(solution_dir).parent.name[:40]    # distinct file per solution (the Aug 2 SD file was overwritten by P1's)
            ns = argparse.Namespace(solution=solution_dir, fixture=fixture, day=day, cadence=900.0,
                                    out=str(Path(folder)/f"roundtrip_{day.replace('-','')}_{tag}.SP3"), force_plain_eop=control,
                                    assume_plain_eop=False)
            written = write_from_solution(ns, folder)
            path = Path(written["output"]) if not written["output"].startswith("deleted") else None
            sol = resolve(solution_dir)
            sol = sol/"solution.npz" if sol.is_dir() else sol
            fx = resolve(fixture)
            origin = int(json.loads(fx.read_text())["context"]["origin_ns"])
            scored = fit_for(sol, fx, plain)
            frame = FrameEpoch(origin, plain)
            product = read_sp3(path) if path else None
            worst, n = 0.0, 0
            if product is not None:
                for s in product.samples.values():
                    if s.xyz_m is None:
                        continue
                    t = (s.epoch_ns-origin)/1e9
                    expected = frame.celestial_to_terrestrial(t)@scored.position(s.sat, t)
                    worst = max(worst, float(np.max(np.abs(np.asarray(s.xyz_m)-expected))))
                    n += 1
            key = "negative_control" if control else "model_aware"
            case[key] = dict(qa_passed=written["passed"], earth_orientation=written["earth_orientation"],
                             samples_compared=n, worst_vs_scoring_path_mm=worst*1000,
                             matches_scoring_path=bool(n and worst <= TOLERANCE_M))
        sd = bool(case["model_aware"]["earth_orientation"].startswith("daily IERS finals + "))
        case["subdaily_solution"] = sd
        # Pass: the model-aware export matches the scored product. For a sub-daily solution the forced plain-EOP
        # control must NOT match; for a plain solution the two exports coincide, so the control must match too.
        case["passed"] = bool(case["model_aware"]["matches_scoring_path"] and
                              (not case["negative_control"]["matches_scoring_path"] if sd else
                               case["negative_control"]["matches_scoring_path"]))
        out["cases"].append(case)
        print(day, "model-aware worst %.4f mm, negative control worst %.1f mm, passed %s"
              % (case["model_aware"]["worst_vs_scoring_path_mm"], case["negative_control"]["worst_vs_scoring_path_mm"], case["passed"]), flush=True)
    out["passed"] = all(c["passed"] for c in out["cases"]) and bool(out["cases"])
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("selftest")
    w = sub.add_parser("write")
    w.add_argument("--solution", required=True)
    w.add_argument("--fixture", required=True)
    w.add_argument("--day", required=True)
    w.add_argument("--out", default=None)
    w.add_argument("--cadence", type=float, default=900.0)
    w.add_argument("--assume-plain-eop", action="store_true",
                   help="only for a solution that predates frame provenance (no force_model.json): declare plain EOP")
    w.add_argument("--force-plain-eop", action="store_true",
                   help="negative control only: writes into the run folder, never the product store")
    r = sub.add_parser("roundtrip")
    r.add_argument("pairs", nargs="+", help="SOLUTION_DIR::FIXTURE_JSON::YYYY-MM-DD")
    args = parser.parse_args()
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    result = {"selftest": selftest, "write": write_from_solution, "roundtrip": roundtrip}[args.mode](args, folder)
    text = json.dumps(result, indent=2, default=float)+"\n"
    (folder/"export.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/f"export_{args.mode}.json").write_text(text)
    print(json.dumps(result, indent=2, default=float), flush=True)
    if not result["passed"]:
        raise SystemExit("QA gate failed")


if __name__ == "__main__":
    main()
