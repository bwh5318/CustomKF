"""What shape is the G21 along-track error, and is anything flagged or eclipsing?

    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.g21_signature

G21 carries 46% of our total squared error against IGS final on 2026-08-02, as a
+38.8 cm along-track bias on a 50.6 cm along-track RMS. The time structure separates
the candidate causes, which imply completely different fixes:

  step or ramp from one instant  -> a manoeuvre or momentum dump inside our 24 h arc
  quadratic growth from the ends -> an unmodelled constant along-track acceleration
  once-per-revolution            -> an empirical/SRP parameterization deficiency
  error local to one time span   -> a station/data problem (the line already pursued)

It also reports the sun-elevation-above-orbit-plane angle (beta) and the umbra/penumbra
fraction per epoch, because nominal yaw is the estimator's only attitude law, and every
SP3 event flag for the satellite in all three products. Evaluation products only; no fit.
"""
import json
import os
from pathlib import Path
import numpy as np

from customkf.ephemeris import DE440
from customkf.frames import EarthOrientation
from customkf.orbit_forces import shadow_fraction
from customkf.prepare_stage2 import sha
from customkf.sp3 import epoch_tag, read_sp3

from .baseline import BEST_FIXTURE, BEST_SOLUTION, DAY, MIDNIGHT, Fit, OnOrigin
from .blocks import satellite_blocks
from .paths import ROOT, STAGE0, STAGE2, STAGE3, RESULTS
from .score import Declared, Product, rac

WATCH = ("G21", "G27", "G23", "G14", "G01")


def harmonic_fit(hours, values):
    """Split a series into bias, linear, quadratic and once/twice-per-rev parts.

    The GPS revolution is 11.967 h (half a sidereal day), so a 24 h arc spans
    almost exactly two revolutions.
    """
    period = 11.967058
    w = 2*np.pi/period
    design = np.column_stack([np.ones_like(hours), hours, hours**2,
                              np.cos(w*hours), np.sin(w*hours),
                              np.cos(2*w*hours), np.sin(2*w*hours)])
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    names = ("bias", "linear_per_h", "quadratic_per_h2", "cos1", "sin1", "cos2", "sin2")
    parts = {}
    for i, name in enumerate(names):
        contribution = design[:, i]*coefficients[i]
        parts[name] = dict(coefficient=float(coefficients[i]), rms_m=float(np.sqrt(np.mean(contribution**2))))
    left = values-design@coefficients
    total = float(np.sqrt(np.mean(values**2)))
    return dict(total_rms_m=total, terms=parts, residual_rms_m=float(np.sqrt(np.mean(left**2))),
                onerev_amplitude_m=float(np.hypot(coefficients[3], coefficients[4])),
                tworev_amplitude_m=float(np.hypot(coefficients[5], coefficients[6])))


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    ephemeris = DE440(STAGE2/"de440s.bsp")
    final_path = STAGE0/"IGS0OPSFIN_20262140000_01D_15M_ORB.SP3"
    reference = Product(final_path, Declared("IGS final", "IGc20", "COM"), MIDNIGHT, eop)
    nga = Product(STAGE0/"nga24300.sp3", Declared("NGA PE", "WGS84", "COM", legacy_a_time_system="GPS"), MIDNIGHT, eop)
    fit = OnOrigin(Fit(BEST_SOLUTION, BEST_FIXTURE, eop), MIDNIGHT)
    blocks = satellite_blocks(DAY)

    report = dict(status="g21_signature_diagnostic_not_accuracy_acceptance", day=DAY,
                  inputs={"igs_final": sha(final_path), "solution": sha(BEST_SOLUTION)},
                  satellites={})

    # Every SP3 event flag for the watched satellites, in all three products.
    flags = {}
    for name, path in (("igs_final", final_path),
                       ("igs_rapid", STAGE3/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz"),
                       ("nga_pe", STAGE0/"nga24300.sp3")):
        product = read_sp3(path, legacy_a_time_system="GPS" if "nga" in name else None)
        rows = []
        for (ns, sat), s in sorted(product.samples.items(), key=lambda kv: kv[0]):
            if sat in WATCH and (s.maneuver or s.orbit_predicted or s.clock_event or s.clock_predicted or s.xyz_m is None):
                rows.append(dict(satellite=sat, hour=(ns-MIDNIGHT)/3.6e12, maneuver=s.maneuver,
                                 orbit_predicted=s.orbit_predicted, clock_event=s.clock_event,
                                 clock_predicted=s.clock_predicted, position_invalid=s.xyz_m is None))
        flags[name] = rows
    report["sp3_event_flags_for_watched_satellites"] = flags

    for sat in WATCH:
        keys = sorted(ns for s, ns in reference.keys() & fit.keys() if s == sat)
        if not keys:
            continue
        hours = np.array([(ns-MIDNIGHT)/3.6e12 for ns in keys])
        ours = np.array([rac(reference, fit, sat, (ns-MIDNIGHT)/1e9) for ns in keys])
        theirs = np.array([rac(reference, nga, sat, (ns-MIDNIGHT)/1e9) for ns in keys])
        geometry = []
        for ns in keys:
            t = (ns-MIDNIGHT)/1e9
            position = reference.position(sat, t)
            velocity = reference.velocity(sat, t)
            sun, _ = ephemeris.sun_moon_m(reference.epoch.tdb_seconds(t))
            normal = np.cross(position, velocity)
            normal = normal/np.linalg.norm(normal)
            beta = np.rad2deg(np.arcsin(np.clip(-normal@(sun/np.linalg.norm(sun)), -1, 1)))
            geometry.append((beta, float(shadow_fraction(position, sun))))
        beta = np.array([g[0] for g in geometry])
        lit = np.array([g[1] for g in geometry])
        report["satellites"][sat] = dict(
            block=blocks.get(sat, ("?", "?"))[0], svn=blocks.get(sat, ("?", "?"))[1], samples=len(keys),
            beta_deg=dict(min=float(beta.min()), max=float(beta.max())),
            sunlit_fraction=dict(min=float(lit.min()), epochs_in_shadow=int((lit < 0.999999).sum())),
            ours=dict(radial=harmonic_fit(hours, ours[:, 0]), along=harmonic_fit(hours, ours[:, 1]),
                      cross=harmonic_fit(hours, ours[:, 2])),
            nga_along=harmonic_fit(hours, theirs[:, 1]),
            along_series_cm=[[round(float(h), 3), round(float(v)*100, 2)] for h, v in zip(hours, ours[:, 1])],
            nga_along_series_cm=[[round(float(h), 3), round(float(v)*100, 2)] for h, v in zip(hours, theirs[:, 1])])

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"g21_signature.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"g21_signature.json").write_text(text)

    for sat, d in report["satellites"].items():
        a = d["ours"]["along"]
        t = a["terms"]
        print(f"\n{sat} ({d['block']} {d['svn']}) beta {d['beta_deg']['min']:.2f}..{d['beta_deg']['max']:.2f} deg, "
              f"{d['sunlit_fraction']['epochs_in_shadow']} shadow epochs")
        print(f"  along-track total {a['total_rms_m']*100:7.2f} cm   NGA {d['nga_along']['total_rms_m']*100:6.2f} cm")
        print(f"    bias {t['bias']['coefficient']*100:+8.2f} cm | linear {t['linear_per_h']['coefficient']*100:+7.2f} cm/h"
              f" | quad {t['quadratic_per_h2']['coefficient']*100:+7.3f} cm/h2")
        print(f"    1/rev amp {a['onerev_amplitude_m']*100:6.2f} cm | 2/rev amp {a['tworev_amplitude_m']*100:6.2f} cm"
              f" | left {a['residual_rms_m']*100:6.2f} cm")
        print(f"    radial total {d['ours']['radial']['total_rms_m']*100:6.2f} cm, cross {d['ours']['cross']['total_rms_m']*100:6.2f} cm")
    print("\nSP3 event flags on watched satellites:",
          {k: len(v) for k, v in report["sp3_event_flags_for_watched_satellites"].items()})
    for name, rows in report["sp3_event_flags_for_watched_satellites"].items():
        for row in rows[:12]:
            print(f"  {name}: {row['satellite']} h={row['hour']:.2f} "
                  + " ".join(k for k, v in row.items() if v is True))
    print("\nWrote "+str(out/"g21_signature.json"))


if __name__ == "__main__":
    main()
