"""Reference-only six-state dynamic fitting; never an observation-estimator input.

Uses the production Trajectory with unchanged force coefficients, integration
settings and interpolation. Only training positions enter solve_fixed(). No
priors, force-parameter fitting, Helmert alignment or residual editing.
"""
import numpy as np
from scipy.linalg import qr, solve_triangular
from customkf.dynamic_observation import Trajectory

SCALES = np.array([100.] * 3 + [.01] * 3)


def solve_fixed(initial, times, positions, model, duration, max_iterations=4):
    times, positions = np.asarray(times, float), np.asarray(positions, float)
    if times.ndim != 1 or len(times) < 4 or positions.shape != (len(times), 3):
        raise ValueError("Invalid training positions")
    if not np.isfinite(positions).all() or np.any(np.diff(times) <= 0):
        raise ValueError("Nonfinite or unordered training data")
    state = np.array(initial, float).copy()
    history = []
    trajectory = Trajectory(state, model, duration)
    for iteration in range(max_iterations):
        residual = positions - np.array([trajectory.state(t)[:3] for t in times])
        design = np.array([trajectory.partial(t)[:3] for t in times]).reshape(-1, 6) * SCALES
        singular = np.linalg.svd(design, compute_uv=False)
        rank = int(np.sum(singular > singular[0] * 1e-11))
        if rank != 6:
            raise ValueError("Rank-deficient six-state diagnostic")
        q, r, pivot = qr(design, mode="economic", pivoting=True)
        scaled_step = np.zeros(6)
        scaled_step[pivot] = solve_triangular(r, q.T @ residual.ravel())
        step = scaled_step * SCALES
        direction = (design @ scaled_step).reshape(-1, 3)
        predicted_rms = float(np.sqrt(np.mean(np.sum(direction**2, axis=1))))
        bound = float(np.linalg.norm(step[:3]) + duration * np.linalg.norm(step[3:]))
        cost = float(np.sum(residual**2))
        record = {"iteration": iteration, "rank": rank, "scaled_condition": float(singular[0] / singular[-1]),
                  "singular_values": singular.tolist(), "training_rms_before_m": float(np.sqrt(cost / len(times))),
                  "predicted_training_update_rms_m": predicted_rms, "step_bound_m": bound}
        # Retain the accepted state at a precision well below the cm diagnostic.
        if bound < 1e-4 and predicted_rms < 1e-5:
            record.update(termination="stationary", update_applied=False, step_fraction=0., training_rms_after_m=record["training_rms_before_m"])
            history.append(record)
            return state, trajectory, history
        accepted = False
        for alpha in (1., .5, .25, .125):
            proposed = state + alpha * step
            trial = Trajectory(proposed, model, duration)
            trial_residual = positions - np.array([trial.state(t)[:3] for t in times])
            trial_cost = float(np.sum(trial_residual**2))
            if trial_cost <= cost:
                state, trajectory, accepted = proposed, trial, True
                break
        record.update(termination="line_search", update_applied=accepted, step_fraction=alpha,
                      training_rms_after_m=float(np.sqrt(trial_cost / len(times))))
        history.append(record)
        if not accepted:
            raise RuntimeError("No decreasing training-only step; no accepted diagnostic product")
    raise RuntimeError("Six-state fit did not converge within iteration cap")
