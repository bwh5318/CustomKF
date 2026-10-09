"""Bounded batch square-root network audit, with epoch-local elimination.

For independent, whitened observation blocks [G_i L_i], orthogonal QR of L_i
leaves projected equations for the retained parameters. Back-substitution
recovers local estimates and *all* covariance blocks, including correlations
between different epochs through the retained parameters. No normal equations
are formed. Covariance is conditional on the supplied sigmas and exact datum;
it is not multiplied by a residual variance estimate.

This deliberately small reference implementation materializes full Q and full
covariance. It is not the eventual streaming large-network implementation.
"""
from dataclasses import dataclass
import numpy as np
from scipy.linalg import qr, solve_triangular

MAX_ROWS = 12000
MAX_PARAMETERS = 900
RANK_RTOL = 1e-10


@dataclass
class Block:
    retained: np.ndarray
    local: np.ndarray
    target: np.ndarray
    sigma: np.ndarray


@dataclass
class Solution:
    estimate: np.ndarray
    covariance: np.ndarray
    rank: int
    reduced_rows: int


def _checked(a, y, sigma):
    a = np.asarray(a, dtype=float)
    y = np.asarray(y, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    if (a.ndim != 2 or not 0 < a.shape[1] <= MAX_PARAMETERS or
            not a.shape[1] <= len(a) <= MAX_ROWS or y.shape != (len(a),) or sigma.shape != y.shape or
            not np.isfinite(a).all() or not np.isfinite(y).all() or
            not np.isfinite(sigma).all() or np.any(sigma <= 0)):
        raise ValueError("Invalid square-root inputs or matrix budget exceeded")
    return a, y, sigma


def _factor(a, *, full=False, column_scale=None):
    scale = 1 / np.maximum(np.linalg.norm(a, axis=0), 1e-30) if column_scale is None else column_scale
    q, r, pivot = qr(a * scale, mode="full" if full else "economic", pivoting=True)
    n = a.shape[1]
    r = r[:n]
    diagonal = np.abs(np.diag(r))
    rank = int(np.sum(diagonal > max(diagonal[0], 1.) * RANK_RTOL))
    if rank != n:
        raise ValueError(f"Rank deficient square-root system: {rank}/{n}")
    # M maps rotated whitened right-hand sides to original physical parameters.
    inverse_r = solve_triangular(r, np.eye(n))
    mapping = np.empty_like(inverse_r)
    mapping[pivot] = scale[pivot, None] * inverse_r
    return q, mapping


def dense_qr(design, target, sigma):
    a, y, sigma = _checked(design, target, sigma)
    q, mapping = _factor(a / sigma[:, None])
    estimate = mapping @ (q.T @ (y / sigma))
    return Solution(estimate, mapping @ mapping.T, a.shape[1], len(a))


def _validate(blocks, constraints):
    c, z, sigma = constraints
    c = np.asarray(c, dtype=float)
    if c.ndim != 2 or not 0 < c.shape[1] <= MAX_PARAMETERS or not blocks:
        raise ValueError("Require retained parameters and at least one block")
    n = c.shape[1]
    total_rows, total_parameters = len(c), n
    # Constraints may have fewer rows than columns, or no rows at all.
    for g, l, y, s in [(c, np.zeros((len(c), 0)), z, sigma)] + [
            (b.retained, b.local, b.target, b.sigma) for b in blocks]:
        if (not all(isinstance(v, np.ndarray) for v in (g, l, y, s)) or
                g.ndim != 2 or l.ndim != 2 or g.shape != (len(l), n) or
                y.shape != (len(g),) or s.shape != y.shape or
                not all(np.isfinite(v).all() for v in (g, l, y, s)) or np.any(s <= 0)):
            raise ValueError("Invalid block or constraint dimensions/values")
    for b in blocks:
        if not 0 < b.local.shape[1] <= len(b.local):
            raise ValueError("Require nonempty, potentially full-rank local blocks")
        total_rows += len(b.target)
        total_parameters += b.local.shape[1]
    if total_rows > MAX_ROWS or total_parameters > MAX_PARAMETERS or total_rows < total_parameters:
        raise ValueError("Network development matrix budget exceeded or too few rows")
    return n, total_rows, total_parameters


def assemble(blocks, constraints):
    """Dense audit oracle; parameter order is retained, block-0 local, block-1 local..."""
    n, m, p = _validate(blocks, constraints)
    a = np.zeros((m, p))
    y = np.empty(m)
    sigma = np.empty(m)
    row = 0
    column = n
    for b in blocks:
        end = row + len(b.target)
        width = b.local.shape[1]
        a[row:end, :n] = b.retained
        a[row:end, column:column + width] = b.local
        y[row:end], sigma[row:end] = b.target, b.sigma
        row, column = end, column + width
    a[row:, :n], y[row:], sigma[row:] = constraints
    return a, y, sigma


def eliminated_qr(blocks, constraints):
    n, _, p = _validate(blocks, constraints)
    projected, targets = [], []
    recovery = []
    original_norm_squared = np.zeros(n)
    for b in blocks:
        l, g, y = b.local / b.sigma[:, None], b.retained / b.sigma[:, None], b.target / b.sigma
        original_norm_squared += np.sum(g*g, axis=0)
        q, mapping = _factor(l, full=True)
        k = l.shape[1]
        q1, q2 = q[:, :k], q[:, k:]
        projected.append(q2.T @ g)
        targets.append(q2.T @ y)
        recovery.append((mapping @ (q1.T @ y), -mapping @ (q1.T @ g), mapping @ mapping.T))
    c, z, sigma = constraints
    projected.append(c / sigma[:, None])
    targets.append(z / sigma)
    a, y = np.vstack(projected), np.concatenate(targets)
    original_norm_squared += np.sum((c/sigma[:, None])**2, axis=0)
    # Keep the pre-projection column scale. Rescaling a projected null column
    # would amplify floating-point roundoff and could hide rank deficiency.
    _checked(a, y, np.ones(len(y)))
    q, mapping = _factor(a, column_scale=1/np.maximum(np.sqrt(original_norm_squared), 1e-30))
    global_solution = Solution(mapping@(q.T@y), mapping@mapping.T, n, len(y))
    transform = np.vstack([np.eye(n), *[b for _, b, _ in recovery]])
    estimate = transform @ global_solution.estimate
    covariance = transform @ global_solution.covariance @ transform.T
    column = n
    for d, b, conditional in recovery:
        end = column + len(d)
        estimate[column:end] += d
        covariance[column:end, column:end] += conditional
        column = end
    return Solution(estimate, covariance, p, len(y))


def require_connected(edges, reference):
    """One exact receiver-clock datum is valid only for one connected graph."""
    adjacency = {}
    for receiver, satellite in edges:
        r, s = "R:" + receiver, "S:" + satellite
        adjacency.setdefault(r, set()).add(s)
        adjacency.setdefault(s, set()).add(r)
    start = "R:" + reference
    if start not in adjacency:
        raise ValueError("Reference receiver absent from epoch")
    visited, queue = {start}, [start]
    while queue:
        for other in adjacency[queue.pop()]:
            if other not in visited:
                visited.add(other)
                queue.append(other)
    if len(visited) != len(adjacency):
        raise ValueError("Disconnected epoch: one clock datum is insufficient")
    return len(adjacency)
