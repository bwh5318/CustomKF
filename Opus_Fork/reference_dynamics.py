"""Can a single smooth 24 h arc represent IGS final's own G21 orbit?

    python -m Opus_Fork.guard --profile fork8 --timeout 2400 --label refdyn -- Opus_Fork.reference_dynamics \
        --day 2026-08-02 --satellites G21,G27,G23,G01 --split-hour 13

Three explanations for G21's along-track runaway have now been tested. Ambiguity leverage was
rejected (rank correlation 0.20). Gross outliers were rejected (12 rows of 28,393). Weighting
was **partly** confirmed: W1 took G21 from 51.83 to 43.14 cm 3D, a real 17% and concentrated
late as predicted, but nowhere near enough. Something else is acting on this satellite.

The remaining candidate that our station data cannot see is that **G21's true trajectory is not
a single smooth arc on this day** — a small manoeuvre or momentum dump, unflagged in every SP3.
That is testable without our observations at all: fit initial state plus ECOM5 directly to the
IGS final positions and look at what is left. A satellite whose true motion is smooth will fit
to a few centimetres; one that was manoeuvred will not, and the misfit will concentrate in time.

If G21's reference-only misfit is large and steps where our error takes off, while control
satellites fit cleanly, then no estimator change can fix this day for G21: the arc has to be
split, and the project's single-arc-per-day assumption is what needs revisiting. If instead
G21's reference orbit fits as cleanly as the controls, a manoeuvre is excluded and the cause is
still in our own modelling.

`--split-hour` repeats the fit on each side of a declared break, so a manoeuvre shows up as
both halves fitting far better than the whole.

**Reference-only, never an estimator input.** This reads IGS final deliberately, so the
precise-product audit hook is *not* installed here; nothing it produces feeds a fit, exactly as
`DYNAMICS_CEILING_RESULTS.md` and `FORCE_PARAMETER_RESULTS.md` treated their reference fits.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np

from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation, FrameEpoch, Environment
from customkf.orbit_forces import OrbitForceModel
from customkf.prepare_stage2 import sha
from customkf.sp3 import epoch_tag
from claude.tools.force_parameter_fit import solve_force

from .blocks import satellite_blocks
from .paths import STAGE2, RESULTS
from .score import Declared, Product
from .store import find

WINDOW_H = 3.0


def rac_of(position, velocity, difference):
    radial = position/np.linalg.norm(position)
    normal = np.cross(position, velocity)
    normal = normal/np.linalg.norm(normal)
    return np.array([difference@radial, difference@np.cross(normal, radial), difference@normal])


def fit_span(reference, sat, times, model, duration, offset):
    """Fit state + ECOM5 to reference positions over one span; return RAC residuals."""
    positions = np.array([reference.position(sat, t) for t in times])
    initial = np.r_[reference.position(sat, times[0]), reference.velocity(sat, times[0])]
    # solve_force returns (state, parameters, trajectory, history, covariance).
    _, parameters, trajectory, history, _ = solve_force(initial, times-offset, positions,
                                                        model, duration, "ecom5")
    fitted = dict(ecom5_nm_s2=(np.asarray(parameters)*1e9).tolist(),
                  iterations=len(history), termination=history[-1].get("termination"))
    rows = []
    for t in times:
        modelled = trajectory.state(t-offset)[:3]
        rows.append(rac_of(reference.position(sat, t), reference.velocity(sat, t),
                           modelled-reference.position(sat, t)))
    return np.array(rows), fitted


def summarize(times, rac, midnight_offset=0.0):
    hours = (times+midnight_offset)/3600.
    out = dict(samples=len(times),
               rms_3d_cm=float(np.sqrt(np.mean(np.sum(rac**2, axis=1))))*100,
               rms_rac_cm=(np.sqrt(np.mean(rac**2, axis=0))*100).tolist(),
               max_abs_along_cm=float(np.max(np.abs(rac[:, 1])))*100,
               by_window={})
    for lo in np.arange(0, 24, WINDOW_H):
        m = (hours >= lo) & (hours < lo+WINDOW_H)
        if m.any():
            out["by_window"][f"{int(lo):02d}-{int(lo+WINDOW_H):02d}"] = dict(
                samples=int(m.sum()),
                rms_3d_cm=float(np.sqrt(np.mean(np.sum(rac[m]**2, axis=1))))*100,
                rms_along_cm=float(np.sqrt(np.mean(rac[m, 1]**2)))*100)
    out["along_series_cm"] = [[round(float(h), 3), round(float(v)*100, 2)] for h, v in zip(hours, rac[:, 1])]
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--satellites", required=True)
    parser.add_argument("--split-hour", type=float, default=None)
    parser.add_argument("--end-hour", type=float, default=23.75)
    args = parser.parse_args()
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    y, m, d = args.day.split("-")
    midnight = epoch_tag(f"* {y} {m} {d} 00 00 00")
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    ephemeris = DE440(STAGE2/"de440s.bsp")
    path, entry = find("reference_igs_final", args.day)
    reference = Product(path, Declared(f"IGS final ({entry['name']})", "IGc20", "COM"), midnight, eop)
    blocks = satellite_blocks(args.day)

    duration = args.end_hour*3600.
    epoch = FrameEpoch(midnight, eop)
    model = OrbitForceModel(Environment(epoch, ephemeris, duration), STAGE2/"EGM2008_degree12.gfc")

    report = dict(status="reference_dynamics_diagnostic_not_accuracy_acceptance", day=args.day,
                  reference=dict(path=str(path), sha256=entry["sha256"]),
                  note="Initial state + ECOM5 fitted directly to IGS final positions. Reference-only; "
                       "no station observation and no estimator input. Large misfit means the reference "
                       "orbit itself is not a single smooth arc on this day.",
                  end_hour=args.end_hour, split_hour=args.split_hour, satellites={})

    for sat in args.satellites.split(","):
        available = sorted(t for s, ns in reference.keys() if s == sat
                           for t in [(ns-midnight)/1e9] if 0 <= t <= duration)
        if len(available) < 20:
            report["satellites"][sat] = dict(error=f"only {len(available)} reference samples")
            continue
        times = np.array(available)
        entry_out = dict(block=blocks.get(sat, ("?", "?"))[0], svn=blocks.get(sat, ("?", "?"))[1])
        try:
            rac, fitted = fit_span(reference, sat, times, model, duration, 0.0)
            entry_out["whole_arc"] = summarize(times, rac) | {"fit": fitted}
        except (ValueError, RuntimeError) as error:
            entry_out["whole_arc"] = dict(error=str(error)[:200])
        if args.split_hour:
            cut = args.split_hour*3600.
            for name, mask in (("first_half", times < cut), ("second_half", times >= cut)):
                sub = times[mask]
                if len(sub) < 20:
                    entry_out[name] = dict(error=f"only {len(sub)} samples")
                    continue
                span = float(sub[-1]-sub[0])
                sub_model = OrbitForceModel(Environment(FrameEpoch(midnight+int(sub[0]*1e9), eop),
                                                        ephemeris, span), STAGE2/"EGM2008_degree12.gfc")
                try:
                    rac, fitted = fit_span(reference, sat, sub, sub_model, span, float(sub[0]))
                    entry_out[name] = summarize(sub, rac) | {"fit": fitted}
                except (ValueError, RuntimeError) as error:
                    entry_out[name] = dict(error=str(error)[:200])
        report["satellites"][sat] = entry_out
        w = entry_out.get("whole_arc", {})
        print(f"\n{sat} ({entry_out['block']} {entry_out['svn']}):", flush=True)
        if "error" in w:
            print(f"  whole arc: FAILED {w['error']}", flush=True)
        else:
            print(f"  whole 24 h : 3D {w['rms_3d_cm']:8.2f} cm, along {w['rms_rac_cm'][1]:8.2f} cm, "
                  f"max|along| {w['max_abs_along_cm']:8.2f} cm", flush=True)
            worst = sorted(w["by_window"].items(), key=lambda kv: -kv[1]["rms_along_cm"])[:3]
            print("    worst windows: "+", ".join(f"{k} {v['rms_along_cm']:.2f} cm" for k, v in worst), flush=True)
        for name in ("first_half", "second_half"):
            h = entry_out.get(name)
            if h and "error" not in h:
                print(f"  {name:11s}: 3D {h['rms_3d_cm']:8.2f} cm, along {h['rms_rac_cm'][1]:8.2f} cm", flush=True)
            elif h:
                print(f"  {name:11s}: FAILED {h['error']}", flush=True)

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"reference_dynamics.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"reference_dynamics.json").write_text(text)
    print("\nWrote "+str(out/"reference_dynamics.json"))


if __name__ == "__main__":
    main()
