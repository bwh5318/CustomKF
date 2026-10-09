"""Diagnose why box-wing census fits exhaust the line search: print the Gauss-Newton history for one satellite.

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 900 --label boxwing-debug -- Opus_Fork.experiments.boxwing_debug G02 E5PB
"""
import os
import sys
import numpy as np


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    sat, variant = sys.argv[1], sys.argv[2]
    from customkf.frames import EarthOrientation
    from customkf.sp3 import epoch_tag
    from Opus_Fork.paths import STAGE2
    from Opus_Fork.score import Declared, Product
    from Opus_Fork.store import find
    from Opus_Fork import satmeta, reference_census as rc
    from Opus_Fork.boxwing import BoxWing
    from Opus_Fork.nongrav import PhysicalRadiation
    from claude.tools.force_parameter_fit import ForceTrajectory, design_at
    midnight = epoch_tag("* 2026 08 02 00 00 00")
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    path, _ = find("reference_igs_final", "2026-08-02")
    reference = Product(path, Declared("IGS final", "IGc20", "COM"), midnight, eop)
    duration = 23.75*3600.
    rc._init(midnight, duration)
    meta = satmeta.load("2026-08-02")[sat]
    times = np.array(sorted(t for s, ns in reference.keys() if s == sat for t in [(ns-midnight)/1e9] if 0 <= t <= duration))
    positions = np.array([reference.position(sat, t) for t in times])
    initial = np.r_[positions[0], reference.velocity(sat, 0.)]
    inner = rc._W["e5"] if variant == "E5B" else PhysicalRadiation(rc._W["e5"], meta)
    model = BoxWing(inner, meta.block)
    state, p = np.array(initial, float), np.zeros(5)
    for stage, active in (("state-only", []), ("ecom5", [0, 1, 2, 3, 4])):
        scales = np.r_[[100.]*3, [.01]*3, np.asarray(model.parameter_scales)[active]]
        for it in range(8):
            traj = ForceTrajectory(state, model, duration, p)
            res = positions-np.array([traj.state(t)[:3] for t in times])
            cost = float(np.sum(res**2))
            design = design_at(traj, times, active)*scales
            scaled, *_ = np.linalg.lstsq(design, res.ravel(), rcond=None)
            delta = scaled*scales
            direction = (design@scaled).reshape(-1, 3)
            bound = float(max(np.linalg.norm(delta[:3])+duration*np.linalg.norm(delta[3:6]), np.max(np.linalg.norm(direction, axis=1))))
            trials = []
            for alpha in (1., .5, .25, .125, 1/16, 1/32):
                tp = p.copy()
                tp[active] += alpha*delta[6:]
                tt = ForceTrajectory(state+alpha*delta[:6], model, duration, tp)
                trials.append((alpha, float(np.sum((positions-np.array([tt.state(t)[:3] for t in times]))**2))))
            best = min(trials, key=lambda x: x[1])
            print(f"{stage} it{it}: rms {np.sqrt(cost/len(times))*100:.4f} cm  step bound {bound*1000:.3f} mm  "
                  f"trial costs/cost-1: " + " ".join(f"{a:g}:{c/cost-1:+.2e}" for a, c in trials), flush=True)
            if best[1] > cost:
                print(f"  -> no decreasing step (rms {np.sqrt(cost/len(times))*100:.4f} cm)", flush=True)
                break
            state = state+best[0]*delta[:6]
            p = p.copy()
            p[active] += best[0]*delta[6:]
            if bound < 1e-4:
                print("  -> stationary", flush=True)
                break
        print(f"{stage} done: p (nm/s2) {np.round(p*1e9, 3).tolist()}", flush=True)


if __name__ == "__main__":
    main()
