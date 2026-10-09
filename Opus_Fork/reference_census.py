"""T1: the model's representation floor, fitted directly to IGS final for every satellite.

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 3000 --label ref-census \
        -- Opus_Fork.reference_census --day 2026-08-02 --workers 4

Reference-only diagnostic. Each satellite's IGS final positions (00:00-23:45, native 15-minute
samples, maneuver/predicted records excluded) are fitted with a 24 h dynamic arc. No station
observation is used, and nothing here becomes an estimator input: fitted coefficients,
including the radial accelerations of E5R, are diagnostics that decide which *physical* model
is worth implementing, never values to adopt (`results/URE_REVIEW_AND_TEST_PLAN.md` §7, §9).

Variants, all on the unchanged `customkf.orbit_forces.OrbitForceModel`:

- **E5**  - state + ECOM5 (the POD's own parameterization);
- **E5R** - E5 + one estimated constant radial acceleration (diagnostic for a missing radial force);
- **E5T** - E5 with antenna thrust P/(m·c) added as a fixed radial force, from the IGS satellite
  metadata only (`Opus_Fork.satmeta`); nothing fitted;
- **E7**  - state + ECOM-7 (adds Dc2, Ds2; `count==7` in the existing model).
- **E5P** - E5 with the fixed physical ERP + antenna thrust of `Opus_Fork.nongrav` (T1.5);
  nothing fitted to IGS.
- **E5PR** - E5P + one estimated constant radial acceleration. It measures what the physics
  leaves unexplained.

Predictions for E5P/E5PR, written after the first census (E5/E5R/E5T/E7) and before either ran.
The absorption-only area×flux estimate gives about 6e-10 m/s² of ERP for IIR and IIF, against
the 1.2–1.4e-9 that E5R minus thrust implies, and about 5e-10 for IIIA against about 5e-10
implied. So:

5. E5P lowers the pooled mean radial from +1.75 cm to about +0.8..+1.1 cm and lowers the
   radial RMS on most satellites; it removes nearly all of IIIA's offset and about half of
   IIF's and IIR's.
6. E5PR's residual radial acceleration is positive, about 0.5–0.9 nm/s² for IIR/IIR-M/IIF
   and near zero for IIIA.

- **E5B** – E5 + fixed a-priori box-wing SRP (`Opus_Fork.boxwing`), D0 starting at 0.
- **E5PB** – E5P + the same box-wing.

Predictions for E5B/E5PB, written 24 Sep 2026 after the ECOM-7 station test failed and before
either variant ran. The 12 h harmonic amplitude of the pooled hourly radial residual is 1.33 cm
for E5, 1.22 for E5P and 0.57 for E7.

7. If the box-wing captures the Sun-direction 2/rev physics, E5PB's 12 h amplitude is at most
   0.85 cm (at least 30% below E5P), and its pooled radial RMS is below E5P's 1.56 cm, without
   estimating any extra parameter.
8. E5B against E5 behaves the same way. The box-wing does not act on the mean radius, which is
   ERP's job, so E5B's pooled mean radial stays near E5's +1.75 cm.

A miss on 7 means the published box-wing is not the missing piece, and the swing needs another
explanation.

**Numerical-floor acceptance, added 25 Sep 2026 after two box-wing runs failed on 10–20
satellites.** A one-satellite trace (G02, `Opus_Fork/experiments/boxwing_debug.py`) showed the
fit reaching 4.89 cm RMS in two iterations and then staying flat. Every trial changed the cost by
a random ±1e-4 relative amount, whatever α: the box-wing's surface switching leaves
integration-level noise that swamps the 0.1 mm stopping rule. Such fits now end as
`numerical_floor` when there has been at least one accepted update and the step bound is under
1 cm. The label is kept in the output. It applies to every variant, and the E5/E5P results do not
reach it.

**Predictions, written before running** (from T0.1 and the physics in the plan):

1. E5R's radial acceleration is positive (outward) on most satellites, of order 1e-9 m/s²,
   and E5R lowers the radial misfit relative to E5.
2. E5T moves the fitted radius down by about the thrust shift (0.3-0.8 cm) and lowers the
   radial misfit on most satellites. It cannot remove all of it: thrust is 0.3-0.8 cm of an
   offset of about 1.7 cm.
3. E7 changes the floor little for GPS.
4. The cross-track floor (2.7-4.7 cm on G21/G27/G01) is not touched by any radial or SRP
   variant. If it stays, the frame/EOP explanation (T1.3) remains the candidate.

**Method.** A stage-1 fit estimates the state only, with nominal D0 = -1e-7 m/s², starting from
the reference position and velocity at 00:00. E5 starts from it. E5R, E5T and E7 then start
from E5's converged solution when it exists (E7 inherits D0/Y0/B0 only). This continuation
was added after a two-satellite smoke test, where G21's E5R direct start exhausted its line
search. It changes starting points, not the model or the stopping rule. Both stages use the same Gauss-Newton, column-scaled pivoted QR, rank check and
four-fraction line search as `claude.tools.force_parameter_fit.solve_force`. They stop at a
step bound < 0.1 mm with a predicted update RMS < 0.01 mm. A failure is recorded, never
retried with other settings. Formal sigmas are the unit-weight covariance scaled by the
posterior variance of the position residuals; they are conditional on this model.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import numpy as np
from scipy.linalg import qr, solve_triangular

GM = 3.986004415e14
VARIANTS = ("E5", "E5R", "E5T", "E7")
_W = {}


class Extended:
    """The unchanged OrbitForceModel plus an optional estimated and/or fixed radial acceleration."""

    def __init__(self, base, estimate_radial=False, fixed_radial_mps2=0.0):
        self.base, self.k = base, len(base.parameter_scales)
        self.estimate_radial, self.fixed = estimate_radial, float(fixed_radial_mps2)
        self.mu_m3ps2 = base.mu_m3ps2
        self.parameter_scales = np.r_[base.parameter_scales, [1e-9] if estimate_radial else []]
        self.parameter_names = tuple(base.parameter_names)+(("R0",) if estimate_radial else ())

    def evaluate(self, t, state, parameters, *, partials=True):
        p = np.asarray(parameters, dtype=float)
        a, jr, jv, dp = self.base.evaluate(t, state, p[:self.k], partials=partials)
        r = np.asarray(state[:3], dtype=float)
        distance = np.linalg.norm(r)
        rh = r/distance
        radial = self.fixed+(p[self.k] if self.estimate_radial else 0.)
        a = a+radial*rh
        if not partials:
            return a, None, None, None
        jr = jr+radial*(np.eye(3)-np.outer(rh, rh))/distance
        if self.estimate_radial:
            dp = np.column_stack([dp, rh])
        return a, jr, jv, dp


def _init(midnight, duration):
    from customkf.ephemeris import DE440
    from customkf.frames import EarthOrientation, FrameEpoch, Environment
    from customkf.orbit_forces import OrbitForceModel
    from .paths import STAGE2
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    environment = Environment(FrameEpoch(midnight, eop), DE440(STAGE2/"de440s.bsp"), duration)
    gravity = STAGE2/"EGM2008_degree12.gfc"
    _W.update(e5=OrbitForceModel(environment, gravity, 5), e7=OrbitForceModel(environment, gravity, 7),
              duration=duration)


def gauss_newton(state, p, active, model, times, positions, duration, max_iterations=8):
    """solve_force's loop, generalized to any active parameter set; returns state, p, trajectory,
    history and the unit-weight covariance of [state, p[active]]."""
    from claude.tools.force_parameter_fit import ForceTrajectory, design_at
    state, p = np.array(state, float), np.array(p, float)
    active = list(active)  # an empty tuple would index the whole array
    scales = np.r_[[100.]*3, [.01]*3, np.asarray(model.parameter_scales)[active]]
    history, trajectory = [], ForceTrajectory(state, model, duration, p)
    for iteration in range(max_iterations):
        residual = positions-np.array([trajectory.state(t)[:3] for t in times])
        design = design_at(trajectory, times, list(active))*scales
        singular = np.linalg.svd(design, compute_uv=False)
        rank = int(np.sum(singular > singular[0]*1e-11))
        if rank != len(scales):
            raise ValueError(f"Rank deficient: {rank}/{len(scales)}")
        q, r, pivot = qr(design, mode="economic", pivoting=True)
        scaled = np.zeros(len(scales))
        scaled[pivot] = solve_triangular(r, q.T@residual.ravel())
        delta = scaled*scales
        direction = (design@scaled).reshape(-1, 3)
        bound = float(max(np.linalg.norm(delta[:3])+duration*np.linalg.norm(delta[3:6]),
                          np.max(np.linalg.norm(direction, axis=1))))
        predicted = float(np.sqrt(np.mean(np.sum(direction**2, axis=1))))
        cost = float(np.sum(residual**2))
        record = dict(iteration=iteration, rank=rank, scaled_condition=float(singular[0]/singular[-1]),
                      rms_before_m=float(np.sqrt(cost/len(times))), predicted_update_rms_m=predicted, step_bound_m=bound)
        if bound < 1e-4 and predicted < 1e-5:
            record.update(termination="stationary")
            history.append(record)
            inv = solve_triangular(r, np.eye(len(scales)))
            cp = inv@inv.T
            covariance = np.zeros_like(cp)
            covariance[np.ix_(pivot, pivot)] = cp
            return state, p, trajectory, history, covariance*scales[:, None]*scales[None, :]
        for alpha in (1., .5, .25, .125):
            trial_p = p.copy()
            trial_p[list(active)] += alpha*delta[6:]
            trial = ForceTrajectory(state+alpha*delta[:6], model, duration, trial_p)
            cost2 = float(np.sum((positions-np.array([trial.state(t)[:3] for t in times]))**2))
            if cost2 <= cost:
                state, p, trajectory = state+alpha*delta[:6], trial_p, trial
                record.update(termination="line_search", step_fraction=alpha, rms_after_m=float(np.sqrt(cost2/len(times))))
                history.append(record)
                break
        else:
            accepted = [h for h in history if h.get("termination") == "line_search"]
            if accepted and bound < 0.01:
                # Numerical-floor acceptance (added 25 Sep 2026, applies to every variant). When the cost is
                # flat to its integration noise, no trial decreases it; after at least one accepted update, with a
                # step bound under 1 cm, the current iterate is reported as converged-at-floor, never hidden.
                record.update(termination="numerical_floor")
                history.append(record)
                inv = solve_triangular(r, np.eye(len(scales)))
                cp = inv@inv.T
                covariance = np.zeros_like(cp)
                covariance[np.ix_(pivot, pivot)] = cp
                return state, p, trajectory, history, covariance*scales[:, None]*scales[None, :]
            record.update(termination="line_search_exhausted")
            history.append(record)
            raise RuntimeError("No decreasing step")
    raise RuntimeError("Iteration cap")


def summarize(times, residual_inertial, axes, u):
    rac = np.einsum("nij,nj->ni", axes, residual_inertial)
    out = dict(rms_rac_cm=(np.sqrt(np.mean(rac**2, axis=0))*100).tolist(),
               mean_rac_cm=(rac.mean(axis=0)*100).tolist(),
               rms_3d_cm=float(np.sqrt(np.mean(np.sum(rac**2, axis=1))))*100)
    uu = np.unwrap(u)
    a = np.column_stack([np.ones_like(uu), np.cos(uu), np.sin(uu)])
    for c, name in ((0, "radial"), (2, "cross")):
        coef, *_ = np.linalg.lstsq(a, rac[:, c], rcond=None)
        rest = rac[:, c]-a@coef
        out[name+"_harmonics_cm"] = dict(constant=float(coef[0])*100, amp_1rev=float(np.hypot(*coef[1:]))*100,
                                         remainder_rms=float(np.sqrt(np.mean(rest**2)))*100)
    out["series_cm"] = [[round(float(t)/3600, 3)]+[round(float(x)*100, 3) for x in row] for t, row in zip(times, rac)]
    return out


def fit_satellite(task):
    from .nongrav import PhysicalRadiation
    sat, times, positions, axes, u, initial, satellite, variants = task
    thrust = satellite.thrust_mps2
    duration = _W["duration"]
    result = dict(satellite=sat, samples=len(times), thrust_mps2=thrust, variants={})
    try:
        base5 = Extended(_W["e5"])
        state0, _, _, h0, _ = gauss_newton(initial, [-1e-7, 0, 0, 0, 0], (), base5, times, positions, duration)
        result["stage1_iterations"] = len(h0)
    except (ValueError, RuntimeError) as error:
        result["stage1_error"] = str(error)[:200]
        return result
    start_state, e5 = state0, [-1e-7, 0, 0, 0, 0]
    for variant in variants:
        # Continuation: E5 starts from the state-only fit; the others start from E5's converged
        # solution when it exists (E7 inherits only D0/Y0/B0: its B-term phase origin differs).
        if variant == "E7":
            model, p0, active = Extended(_W["e7"]), [*e5[:3], 0, 0, 0, 0], tuple(range(7))
        elif variant == "E5R":
            model, p0, active = Extended(_W["e5"], estimate_radial=True), [*e5, 0], tuple(range(6))
        elif variant == "E5T":
            model, p0, active = Extended(_W["e5"], fixed_radial_mps2=thrust), list(e5), tuple(range(5))
        elif variant == "E5P":
            model, p0, active = PhysicalRadiation(_W["e5"], satellite), list(e5), tuple(range(5))
        elif variant == "E5PR":
            model, p0, active = Extended(PhysicalRadiation(_W["e5"], satellite), estimate_radial=True), [*e5, 0], tuple(range(6))
        elif variant in ("E5B", "E5PB"):
            from .boxwing import BoxWing
            inner = _W["e5"] if variant == "E5B" else PhysicalRadiation(_W["e5"], satellite)
            # The box-wing carries the panels' constant Sun push, so ECOM starts at 0 (a correction).
            # Model-consistent continuation (added after the first box-wing run, where starting from
            # E5's state, fitted under a different force model, exhausted the line search on 10–12
            # satellites): a state-only stage under the box-wing model itself, as E5 has under its own.
            model, p0, active = BoxWing(inner, satellite.block), [0.]*5, tuple(range(5))
            try:
                own_start, _, _, _, _ = gauss_newton(initial, p0, (), model, times, positions, duration)
            except (ValueError, RuntimeError) as error:
                result["variants"][variant] = dict(error="stage-1: "+str(error)[:180])
                continue
            try:
                state, p, trajectory, history, covariance = gauss_newton(own_start, p0, active, model, times, positions, duration)
            except (ValueError, RuntimeError) as error:
                result["variants"][variant] = dict(error=str(error)[:200])
                continue
            residual = np.array([trajectory.state(t)[:3] for t in times])-positions
            dof = 3*len(times)-len(covariance)
            variance = float(np.sum(residual**2))/dof
            sigma = np.sqrt(np.diag(covariance)*variance)
            entry = summarize(times, residual, axes, u)
            entry.update(parameters=dict(zip(model.parameter_names, (np.asarray(p)*1e9).tolist())),
                         parameter_sigma=dict(zip(model.parameter_names, (sigma[6:]*1e9).tolist())),
                         units="parameters in nm/s^2", initial_state=state.tolist(), state_sigma=sigma[:6].tolist(),
                         iterations=len(history), termination=history[-1]["termination"],
                         posterior_rms_m=float(np.sqrt(variance)), start="own state-only stage under the box-wing model")
            result["variants"][variant] = entry
            continue
        else:
            model, p0, active = Extended(_W["e5"]), list(e5), tuple(range(5))
        try:
            state, p, trajectory, history, covariance = gauss_newton(start_state, p0, active, model, times, positions, duration)
            if variant == "E5":
                start_state, e5 = state, list(p)
            residual = np.array([trajectory.state(t)[:3] for t in times])-positions
            dof = 3*len(times)-len(covariance)
            variance = float(np.sum(residual**2))/dof
            sigma = np.sqrt(np.diag(covariance)*variance)
            entry = summarize(times, residual, axes, u)
            entry.update(parameters=dict(zip(model.parameter_names, (np.asarray(p)*1e9).tolist())),
                         parameter_sigma=dict(zip(model.parameter_names, (sigma[6:]*1e9).tolist())),
                         units="parameters in nm/s^2", initial_state=state.tolist(),
                         state_sigma=sigma[:6].tolist(), iterations=len(history),
                         termination=history[-1]["termination"], posterior_rms_m=float(np.sqrt(variance)))
            result["variants"][variant] = entry
        except (ValueError, RuntimeError) as error:
            result["variants"][variant] = dict(error=str(error)[:200])
    return result


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    from customkf.frames import EarthOrientation
    from customkf.sp3 import epoch_tag
    from .blocks import satellite_blocks, group
    from .paths import STAGE2, RESULTS
    from .score import Declared, Product
    from .store import find
    from . import satmeta
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--satellites", default=None)
    parser.add_argument("--end-hour", type=float, default=23.75)
    parser.add_argument("--variants", default=",".join(VARIANTS), help="E5 must come first; others: E5R E5T E7 E5P E5PR")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    run = Path(os.environ["CUSTOMKF_RUN_DIR"])
    y, m, d = args.day.split("-")
    midnight = epoch_tag(f"* {y} {m} {d} 00 00 00")
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    path, entry = find("reference_igs_final", args.day)
    reference = Product(path, Declared(f"IGS final ({entry['name']})", "IGc20", "COM"), midnight, eop)
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(args.day).items()}
    meta = satmeta.load(args.day)
    duration = args.end_hour*3600.
    variants = tuple(args.variants.split(","))
    assert variants[0] == "E5", "E5 must come first: the other variants start from it"
    wanted = args.satellites.split(",") if args.satellites else sorted({s for s, _ in reference.keys() if s.startswith("G")})
    tasks = []
    for sat in wanted:
        times = np.array(sorted(t for s, ns in reference.keys() if s == sat for t in [(ns-midnight)/1e9] if 0 <= t <= duration))
        if len(times) < 80 or times[0] != 0. or sat not in meta:
            print(f"{sat}: skipped ({len(times)} samples, starts {times[0] if len(times) else None}, metadata {sat in meta})", flush=True)
            continue
        positions = np.array([reference.position(sat, t) for t in times])
        axes, u = [], []
        for t, r in zip(times, positions):
            v = reference.velocity(sat, t)
            radial = r/np.linalg.norm(r)
            normal = np.cross(r, v)/np.linalg.norm(np.cross(r, v))
            axes.append([radial, np.cross(normal, radial), normal])
            node = np.cross([0., 0., 1.], normal)
            node /= np.linalg.norm(node)
            u.append(np.arctan2(r@np.cross(normal, node), r@node))
        initial = np.r_[positions[0], reference.velocity(sat, 0.)]
        tasks.append((sat, times, positions, np.array(axes), np.array(u), initial, meta[sat], variants))
    report = dict(status="reference_dynamics_diagnostic_not_accuracy_acceptance", test="T1 reference ceiling census",
                  day=args.day, reference=dict(path=str(path), sha256=entry["sha256"]),
                  satellite_metadata=satmeta.provenance(), variants=variants, end_hour=args.end_hour, satellites={})
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init, initargs=(midnight, duration)) as pool:
        for result in pool.map(fit_satellite, tasks):
            sat = result["satellite"]
            result.update(block=blocks.get(sat), svn=meta[sat].svn)
            report["satellites"][sat] = result
            line = [f"{sat} {str(blocks.get(sat)):5s}"]
            for v in variants:
                e = result["variants"].get(v, {})
                if "rms_rac_cm" in e:
                    rr = e["rms_rac_cm"]
                    line.append(f"{v} R {rr[0]:.2f} ({e['mean_rac_cm'][0]:+.2f}) A {rr[1]:.2f} C {rr[2]:.2f}")
                else:
                    line.append(f"{v} FAIL")
            r0 = (result["variants"].get("E5R") or result["variants"].get("E5PR") or {}).get("parameters", {}).get("R0")
            print(" | ".join(line)+(f" | R0 {r0:+.3f} nm/s2" if r0 is not None else ""), flush=True)
    pooled = {}
    for v in variants:
        good = [s for s in report["satellites"].values() if "rms_rac_cm" in s["variants"].get(v, {})]
        if good:
            ms = np.mean([np.array(s["variants"][v]["rms_rac_cm"])**2 for s in good], axis=0)
            pooled[v] = dict(satellites=len(good), rms_rac_cm=np.sqrt(ms).tolist(),
                             mean_radial_cm=float(np.mean([s["variants"][v]["mean_rac_cm"][0] for s in good])),
                             failed=[s["satellite"] for s in report["satellites"].values() if "rms_rac_cm" not in s["variants"].get(v, {})])
    report["pooled"] = pooled
    r0 = {}
    for s in report["satellites"].values():
        e = s["variants"].get("E5R") or s["variants"].get("E5PR") or {}
        if "parameters" in e:
            r0.setdefault(s["block"], []).append(e["parameters"]["R0"])
    report["E5R_radial_acceleration_by_block_nm_s2"] = {b: dict(n=len(v), mean=float(np.mean(v)), std=float(np.std(v)))
                                                        for b, v in sorted(r0.items(), key=lambda kv: str(kv[0]))}
    for v, p in pooled.items():
        print(f"POOLED {v}: {p['satellites']} sats, RAC rms {[round(x, 2) for x in p['rms_rac_cm']]} cm, "
              f"mean radial {p['mean_radial_cm']:+.2f} cm, failed {p['failed']}", flush=True)
    print("E5R R0 by block (nm/s^2):", json.dumps(report["E5R_radial_acceleration_by_block_nm_s2"]), flush=True)
    text = json.dumps(report, indent=1, default=float)+"\n"
    (run/"reference_census.json").write_text(text)
    (RESULTS/f"reference_census_{args.day}{args.tag}.json").write_text(text)
    print("Wrote", run/"reference_census.json")


if __name__ == "__main__":
    main()
