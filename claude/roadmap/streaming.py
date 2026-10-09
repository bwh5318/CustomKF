"""Streaming square-root accumulation of the batch least-squares solve (roadmap step 2).

The existing reduced_qr stacks every clock-eliminated row into one dense (rows x retained)
matrix, capped at 12,000 rows / 900 retained columns / 256 MiB. Here each epoch block is
whitened, its epoch-local clocks are eliminated by the same pivoted local QR, and the projected
rows are folded into an upper-triangular R and right-hand side z:  QR([R; A_k]) -> R'.
Because orthogonal transformations preserve the least-squares problem, the final solve (a
pivoted QR of R with the same pre-projection column scale and rank rule) gives the same
estimate, retained covariance and local-clock recovery as reduced_qr, up to rounding.

Memory is O(n^2 + block * n), where n (the retained global parameters: wet-delay nodes, ambiguities,
orbits, forces) grows with arc length, and the stored recovery blocks grow with epochs. It never materializes
the full observation design (corrected 28 Sep 2026, Astra review N07; it had said "independent of arc length").
The state is a small checkpoint, so a long linearization can be split across several guarded workers.

The predicted linear-model reduction at the exact LS step equals ||P y||^2 =
sum(||Q1^T y||^2 over local blocks) + ||z||^2, which is how the existing stationarity rule's
predicted_reduction and whitened_direction_norm_squared are reported (they coincide at the LS
optimum; the archives show identical values).
"""
import numpy as np
from scipy.linalg import qr_multiply, solve_triangular
from customkf.network_square_root import RANK_RTOL, _factor


class CachedEpoch:
    """Exact memoization of FrameEpoch rotations/TDB by float time. Outputs are bitwise those of
    the wrapped epoch; returned matrices are read-only so any in-place use would fail loudly."""
    def __init__(self, epoch, limit=400000):
        self.base, self.limit = epoch, limit
        self._rotation, self._tdb = {}, {}
        for name in ("tt1", "tt2", "eop"):
            setattr(self, name, getattr(epoch, name))

    def times(self, elapsed_s):
        return self.base.times(elapsed_s)

    def celestial_to_terrestrial(self, elapsed_s):
        key = float(elapsed_s)
        value = self._rotation.get(key)
        if value is None:
            if len(self._rotation) >= self.limit:
                self._rotation.clear()
            value = self.base.celestial_to_terrestrial(key)
            value.setflags(write=False)
            self._rotation[key] = value
        return value

    def tdb_seconds(self, elapsed_s):
        key = float(elapsed_s)
        value = self._tdb.get(key)
        if value is None:
            if len(self._tdb) >= self.limit:
                self._tdb.clear()
            value = self._tdb[key] = self.base.tdb_seconds(key)
        return value


def _check_rows(design, target, sigma, columns, what):
    """Raw input contract before whitening (Sol review SOL-08). A positive infinite sigma would otherwise turn finite
    rows into zeros that pass the post-division finiteness test, silently dropping observations or constraints."""
    if sigma.ndim != 1 or target.shape != sigma.shape or design.ndim != 2 or design.shape[0] != len(sigma) \
            or (columns is not None and design.shape[1] != columns):
        raise ValueError(f"Invalid {what} dimensions")
    if not (np.isfinite(sigma).all() and np.all(sigma > 0)):
        raise ValueError(f"Invalid {what} sigma: every sigma must be finite and positive")
    if not (np.isfinite(design).all() and np.isfinite(target).all()):
        raise ValueError(f"Invalid {what} values")


class Accumulator:
    def __init__(self, n):
        self.n = int(n)
        self.R = np.zeros((0, self.n))
        self.z = np.zeros(0)
        self.norm2 = np.zeros(self.n)
        self.local_explained = 0.
        self.lost = 0.
        self.rows = 0
        self.local_total = 0
        self.recovery = []  # per block: (active retained columns, d, B restricted to those columns)
        self.largest_update_rows = 0

    def _update(self, a, t):
        if not len(t):
            return
        m = np.vstack([self.R, a])
        rhs = np.r_[self.z, t]
        self.largest_update_rows = max(self.largest_update_rows, len(rhs))
        qt, r = qr_multiply(m, rhs, mode="right")
        self.R, self.z = r, qt
        self.lost += float(rhs@rhs-qt@qt)

    def add_block(self, retained, local, target, sigma):
        _check_rows(retained, target, sigma, self.n, "block")
        _check_rows(local, target, sigma, None, "block")
        g = retained/sigma[:, None]
        l = local/sigma[:, None]
        y = target/sigma
        if not (np.isfinite(g).all() and np.isfinite(l).all() and np.isfinite(y).all()) or np.any(sigma <= 0):
            raise ValueError("Invalid block values")
        if g.shape[1] != self.n or not 0 < l.shape[1] <= len(l):
            raise ValueError("Invalid block dimensions")
        self.norm2 += np.sum(g*g, axis=0)
        q, mapping = _factor(l, full=True)
        k = l.shape[1]
        q1, q2 = q[:, :k], q[:, k:]
        qy = q1.T@y
        self.local_explained += float(qy@qy)
        active = np.flatnonzero(np.any(g != 0, axis=0))
        self.recovery.append((active, mapping@qy, -mapping@(q1.T@g[:, active])))
        self._update(q2.T@g, q2.T@y)
        self.rows += len(y)
        self.local_total += k

    def add_constraints(self, c, z, s):
        _check_rows(c, z, s, self.n, "constraint")
        c = c/s[:, None]
        z = z/s
        self.norm2 += np.sum(c*c, axis=0)
        self._update(c, z)
        self.rows += len(z)

    def solve(self):
        if self.R.shape != (self.n, self.n):
            raise ValueError("Underdetermined accumulated system")
        if self.rows < self.n+self.local_total:
            raise ValueError("Fewer rows than parameters")
        # Same pre-projection column scale and rank rule as reduced_qr.
        q, mapping = _factor(self.R, column_scale=1/np.maximum(np.sqrt(self.norm2), 1e-30))
        retained = mapping@(q.T@self.z)
        local = [d+b@retained[active] for active, d, b in self.recovery]
        estimate = np.concatenate([retained, *local])
        reduction = self.local_explained+float(self.z@self.z)
        return estimate, mapping@mapping.T, reduction

    def workspace_bytes(self, largest_block_rows):
        n = self.n
        recovery = sum(d.nbytes+b.nbytes+a.nbytes for a, d, b in self.recovery)
        return int(8*(4*(n+largest_block_rows)*n+3*n*n+4*largest_block_rows**2)+recovery)

    # Checkpointing: a compact npz between guarded workers.
    def state(self):
        actives = [a for a, _, _ in self.recovery]
        ds = [d for _, d, _ in self.recovery]
        bs = [b for _, _, b in self.recovery]
        return dict(n=self.n, R=self.R, z=self.z, norm2=self.norm2, local_explained=self.local_explained, lost=self.lost,
                    rows=self.rows, local_total=self.local_total, largest_update_rows=self.largest_update_rows,
                    active_lengths=np.array([len(a) for a in actives], dtype=np.int64),
                    local_lengths=np.array([len(d) for d in ds], dtype=np.int64),
                    active=np.concatenate(actives) if actives else np.zeros(0, np.int64),
                    d=np.concatenate(ds) if ds else np.zeros(0),
                    B=np.concatenate([b.ravel() for b in bs]) if bs else np.zeros(0))

    @classmethod
    def restore(cls, data):
        self = cls(int(data["n"]))
        self.R, self.z, self.norm2 = data["R"].copy(), data["z"].copy(), data["norm2"].copy()
        self.local_explained, self.lost = float(data["local_explained"]), float(data["lost"])
        self.rows, self.local_total = int(data["rows"]), int(data["local_total"])
        self.largest_update_rows = int(data["largest_update_rows"])
        # Read each npz member exactly once: NpzFile.__getitem__ re-reads the whole array on every access,
        # and slices of those temporaries would each keep a full copy alive (24 h: ~2 GiB over 144 blocks).
        active_lengths, local_lengths = data["active_lengths"], data["local_lengths"]
        all_active, all_d, all_b = data["active"], data["d"], data["B"]
        a_off = np.r_[0, np.cumsum(active_lengths)]
        d_off = np.r_[0, np.cumsum(local_lengths)]
        b_off = np.r_[0, np.cumsum(active_lengths*local_lengths)]
        # Semantic shape checks before use (Sol review SOL-08): a hash-valid checkpoint can still be malformed.
        n = self.n
        if self.R.ndim != 2 or self.R.shape[1] != n or self.R.shape[0] > n or self.z.shape != (self.R.shape[0],) \
                or self.norm2.shape != (n,) or active_lengths.shape != local_lengths.shape \
                or a_off[-1] != len(all_active) or d_off[-1] != len(all_d) or b_off[-1] != len(all_b) \
                or (len(all_active) and (all_active.min() < 0 or all_active.max() >= n)):
            raise ValueError("Checkpoint arrays are inconsistent with their recorded layout")
        if not all(np.isfinite(a).all() for a in (self.R, self.z, self.norm2, all_d, all_b)) \
                or not all(np.isfinite(v) for v in (self.local_explained, self.lost)) or self.rows < 0 or self.local_total < 0:
            raise ValueError("Checkpoint contains non-finite or negative values")
        # Recovery layout as the writer produces it (Astra AR-03): integral index and count arrays, at least one local
        # parameter per block, each block's active columns strictly increasing (np.flatnonzero), and the recorded local
        # total equal to the recovery blocks' parameters. A duplicate index would otherwise change recovered estimates.
        if any(a.dtype.kind not in "iu" for a in (active_lengths, local_lengths, all_active)) \
                or active_lengths.ndim != 1 or (len(active_lengths) and (active_lengths.min() < 0 or local_lengths.min() < 1)) \
                or self.local_total != int(local_lengths.sum()):
            raise ValueError("Checkpoint recovery counts are inconsistent with their recorded layout")
        for i in range(len(active_lengths)):
            # Adjacent elements are compared directly: np.diff of an unsigned array wraps a decrease into a large
            # positive step (Astra E-02).
            block = all_active[a_off[i]:a_off[i+1]]
            if np.any(block[1:] <= block[:-1]):
                raise ValueError("Checkpoint recovery indices are not unique and increasing in a block")
        for i in range(len(active_lengths)):
            active = all_active[a_off[i]:a_off[i+1]]
            d = all_d[d_off[i]:d_off[i+1]]
            b = all_b[b_off[i]:b_off[i+1]].reshape(len(d), len(active))
            self.recovery.append((active, d, b))
        return self


class EliminatingAccumulator:
    """Streaming accumulation that folds out each ambiguity once its arc has ended (7 Oct 2026, network test S50).

    `Accumulator` keeps every retained parameter in R from the first epoch. Its n x n factor and the solve workspace
    therefore grow with all the ambiguity arcs of the day: about 3,450 parameters for 49 stations, beyond the 512 MiB
    workspace preflight. Here the factor covers only the **active** parameters:
    - the permanent ones (orbits, forces, wet-delay nodes);
    - the ambiguities whose arc has started and not yet ended.

    A new parameter joins R (as a zero column) when its first nonzero row arrives. When an arc has ended (its last
    epoch is known from the fixture rows), its ambiguity is eliminated: the columns are permuted to put it first, QR
    re-triangularizes, and the leading rows (R_EE, R_E,rest, z_E) are kept for back-substitution. This is the standard
    square-root-information marginalization.
    - **Exact for a full-rank system.** The trailing block is the factor of the remaining parameters' marginal
      information, and x_E = R_EE^-1 (z_E - R_E,rest x_rest) recovers the eliminated ones.
    - **What does not change:** the predicted reduction is ||z||^2 summed over the retained and eliminated parts, and
      the final solve uses the same pivoted QR, column scale and rank rule as `Accumulator` on the remaining
      parameters.
    - **Fails closed.** Every eliminated block is checked against the same relative rank tolerance. A nonzero entry
      in an already eliminated column is refused.
    - **Covariance:** returned only for a leading block of permanent parameters (orbit states and the first wet-delay
      levels in `LongPilot`'s order). It is diagnostic, as before.
    """
    KIND = 1

    def __init__(self, n, last_epoch, covariance_prefix):
        """`last_epoch`: length-n integer array, -1 for permanent parameters, else the last epoch with a nonzero row."""
        self.n = int(n)
        self.last_epoch = np.asarray(last_epoch, dtype=np.int64)
        if self.last_epoch.shape != (self.n,) or np.any(self.last_epoch < -1):
            raise ValueError("Invalid elimination schedule")
        self.covariance_prefix = int(covariance_prefix)
        if not 0 < self.covariance_prefix <= self.n or np.any(self.last_epoch[:self.covariance_prefix] != -1):
            raise ValueError("The covariance prefix must consist of permanent parameters")
        self.state_of = np.where(self.last_epoch == -1, 1, 0).astype(np.int8)    # 0 not yet, 1 active, 2 eliminated
        self.columns = np.flatnonzero(self.state_of == 1)                       # global index of each R column
        self.R = np.zeros((0, len(self.columns)))
        self.z = np.zeros(0)
        self.norm2 = np.zeros(self.n)
        self.local_explained = self.eliminated_explained = self.lost = 0.
        self.rows = self.local_total = self.largest_update_rows = 0
        self.max_active = len(self.columns)
        self.recovery = []    # per block: (nonzero retained columns, d, B), global indices as in Accumulator
        self.eliminated = []  # per elimination: (E, rest, R_EE, R_E,rest, z_E), global indices

    def _activate(self, needed):
        if np.any(self.state_of[needed] == 2):
            raise ValueError("A row refers to an ambiguity that was already eliminated")
        new = needed[self.state_of[needed] == 0]
        if len(new):
            self.state_of[new] = 1
            self.columns = np.r_[self.columns, new]
            self.R = np.hstack([self.R, np.zeros((self.R.shape[0], len(new)))])
            self.max_active = max(self.max_active, len(self.columns))

    def _update(self, a, t):
        if not len(t):
            return
        m = np.vstack([self.R, a])
        rhs = np.r_[self.z, t]
        self.largest_update_rows = max(self.largest_update_rows, len(rhs))
        qt, r = qr_multiply(m, rhs, mode="right")
        self.R, self.z = r, qt
        self.lost += float(rhs@rhs-qt@qt)

    def add_block(self, retained, local, target, sigma):
        _check_rows(retained, target, sigma, self.n, "block")
        _check_rows(local, target, sigma, None, "block")
        g = retained/sigma[:, None]
        l = local/sigma[:, None]
        y = target/sigma
        if not (np.isfinite(g).all() and np.isfinite(l).all() and np.isfinite(y).all()) or np.any(sigma <= 0):
            raise ValueError("Invalid block values")
        if not 0 < l.shape[1] <= len(l):
            raise ValueError("Invalid block dimensions")
        active = np.flatnonzero(np.any(g != 0, axis=0))
        self._activate(active)
        self.norm2 += np.sum(g*g, axis=0)
        q, mapping = _factor(l, full=True)
        k = l.shape[1]
        q1, q2 = q[:, :k], q[:, k:]
        qy = q1.T@y
        self.local_explained += float(qy@qy)
        self.recovery.append((active, mapping@qy, -mapping@(q1.T@g[:, active])))
        self._update(q2.T@g[:, self.columns], q2.T@y)
        self.rows += len(y)
        self.local_total += k

    def add_constraints(self, c, z, s):
        _check_rows(c, z, s, self.n, "constraint")
        c = c/s[:, None]
        z = z/s
        self._activate(np.flatnonzero(np.any(c != 0, axis=0)))
        self.norm2 += np.sum(c*c, axis=0)
        self._update(c[:, self.columns], z)
        self.rows += len(z)

    def eliminate_through(self, epoch):
        """Fold out every active parameter whose last observation epoch is at or before `epoch`."""
        last = self.last_epoch[self.columns]
        position = np.flatnonzero((last >= 0) & (last <= epoch))
        e = len(position)
        if not e:
            return 0
        if self.R.shape[0] < e:
            raise ValueError("Underdetermined ambiguities at elimination")
        keep = np.setdiff1d(np.arange(len(self.columns)), position)
        qt, r = qr_multiply(self.R[:, np.r_[position, keep]], self.z, mode="right")
        r_ee, r_er, z_e = r[:e, :e], r[:e, e:], qt[:e]
        E, rest = self.columns[position], self.columns[keep]
        scaled = np.abs(np.diag(r_ee))/np.maximum(np.sqrt(self.norm2[E]), 1e-30)
        if np.any(scaled <= RANK_RTOL):
            raise ValueError(f"Rank deficient ambiguity elimination at epoch {epoch}")
        self.eliminated.append((E, rest, r_ee.copy(), r_er.copy(), z_e.copy()))
        self.eliminated_explained += float(z_e@z_e)
        self.R, self.z = r[e:, e:].copy(), qt[e:].copy()
        self.columns = rest
        self.state_of[E] = 2
        return e

    def solve(self):
        k = len(self.columns)
        if self.R.shape != (k, k):
            raise ValueError("Underdetermined accumulated system")
        if self.rows < self.n+self.local_total:
            raise ValueError("Fewer rows than parameters")
        if np.any(self.state_of == 0):
            raise ValueError("Parameters without any observation or constraint")
        q, mapping = _factor(self.R, column_scale=1/np.maximum(np.sqrt(self.norm2[self.columns]), 1e-30))
        retained = np.zeros(self.n)
        retained[self.columns] = mapping@(q.T@self.z)
        for E, rest, r_ee, r_er, z_e in reversed(self.eliminated):
            retained[E] = solve_triangular(r_ee, z_e-r_er@retained[rest])
        local = [d+b@retained[active] for active, d, b in self.recovery]
        estimate = np.concatenate([retained, *local])
        position = {int(c): i for i, c in enumerate(self.columns)}
        prefix = [position[i] for i in range(self.covariance_prefix)]
        covariance = (mapping@mapping.T)[np.ix_(prefix, prefix)]
        reduction = self.local_explained+self.eliminated_explained+float(self.z@self.z)
        return estimate, covariance, reduction

    def workspace_bytes(self, largest_block_rows):
        k = self.max_active
        recovery = sum(d.nbytes+b.nbytes+a.nbytes for a, d, b in self.recovery)
        eliminated = sum(sum(v.nbytes for v in block) for block in self.eliminated)
        return int(8*(4*(k+largest_block_rows)*k+3*k*k+4*largest_block_rows**2)+recovery+eliminated)

    # Checkpointing: the Accumulator members (R over the active columns) plus the elimination record.
    def state(self):
        actives = [a for a, _, _ in self.recovery]
        ds = [d for _, d, _ in self.recovery]
        bs = [b for _, _, b in self.recovery]
        el = self.eliminated
        return dict(kind=np.int64(self.KIND), n=self.n, R=self.R, z=self.z, norm2=self.norm2,
                    local_explained=self.local_explained, lost=self.lost, rows=self.rows, local_total=self.local_total,
                    largest_update_rows=self.largest_update_rows,
                    active_lengths=np.array([len(a) for a in actives], dtype=np.int64),
                    local_lengths=np.array([len(d) for d in ds], dtype=np.int64),
                    active=np.concatenate(actives) if actives else np.zeros(0, np.int64),
                    d=np.concatenate(ds) if ds else np.zeros(0),
                    B=np.concatenate([b.ravel() for b in bs]) if bs else np.zeros(0),
                    last_epoch=self.last_epoch, covariance_prefix=np.int64(self.covariance_prefix),
                    column_state=self.state_of.astype(np.int64), columns=self.columns.astype(np.int64),
                    max_active=np.int64(self.max_active), eliminated_explained=self.eliminated_explained,
                    elim_lengths=np.array([len(b[0]) for b in el], dtype=np.int64),
                    rest_lengths=np.array([len(b[1]) for b in el], dtype=np.int64),
                    elim_columns=np.concatenate([b[0] for b in el]).astype(np.int64) if el else np.zeros(0, np.int64),
                    rest_columns=np.concatenate([b[1] for b in el]).astype(np.int64) if el else np.zeros(0, np.int64),
                    elim_R=np.concatenate([b[2].ravel() for b in el]) if el else np.zeros(0),
                    elim_Rrest=np.concatenate([b[3].ravel() for b in el]) if el else np.zeros(0),
                    elim_z=np.concatenate([b[4] for b in el]) if el else np.zeros(0))

    @classmethod
    def restore(cls, data):
        if "kind" not in getattr(data, "files", data) or int(data["kind"]) != cls.KIND:
            raise ValueError("Not an eliminating checkpoint")
        self = cls(int(data["n"]), data["last_epoch"], int(data["covariance_prefix"]))
        n = self.n
        self.R, self.z, self.norm2 = data["R"].copy(), data["z"].copy(), data["norm2"].copy()
        self.local_explained, self.lost = float(data["local_explained"]), float(data["lost"])
        self.eliminated_explained = float(data["eliminated_explained"])
        self.rows, self.local_total = int(data["rows"]), int(data["local_total"])
        self.largest_update_rows, self.max_active = int(data["largest_update_rows"]), int(data["max_active"])
        state_of, columns = data["column_state"], data["columns"]
        if state_of.shape != (n,) or not set(np.unique(state_of).tolist()) <= {0, 1, 2} \
                or len(np.unique(columns)) != len(columns) \
                or not np.array_equal(np.sort(columns), np.flatnonzero(state_of == 1)) \
                or np.any(state_of[self.last_epoch == -1] != 1):
            raise ValueError("Checkpoint column states are inconsistent")
        self.state_of, self.columns = state_of.astype(np.int8), columns.copy()
        k = len(columns)
        if self.R.ndim != 2 or self.R.shape[1] != k or self.R.shape[0] > k or self.z.shape != (self.R.shape[0],) \
                or self.norm2.shape != (n,) or self.max_active < k:
            raise ValueError("Checkpoint arrays are inconsistent with their recorded layout")
        e_len, r_len = data["elim_lengths"], data["rest_lengths"]
        e_all, r_all = data["elim_columns"], data["rest_columns"]
        ree, rer, ze = data["elim_R"], data["elim_Rrest"], data["elim_z"]
        if e_len.shape != r_len.shape or (len(e_len) and (e_len.min() < 1 or r_len.min() < 0)) \
                or len(e_all) != e_len.sum() or len(r_all) != r_len.sum() or len(ze) != e_len.sum() \
                or len(ree) != int((e_len*e_len).sum()) or len(rer) != int((e_len*r_len).sum()) \
                or len(np.unique(e_all)) != len(e_all) \
                or (len(e_all) and (e_all.min() < 0 or e_all.max() >= n or np.any(state_of[e_all] != 2))) \
                or (len(r_all) and (r_all.min() < 0 or r_all.max() >= n)) \
                or int(np.sum(state_of == 2)) != len(e_all):
            raise ValueError("Checkpoint elimination record is inconsistent with its layout")
        if not all(np.isfinite(a).all() for a in (self.R, self.z, self.norm2, ree, rer, ze)) \
                or not np.isfinite(self.eliminated_explained):
            raise ValueError("Checkpoint contains non-finite values")
        eo, ro, qo, so = 0, 0, 0, 0
        for e, r in zip(e_len.tolist(), r_len.tolist()):
            E, rest = e_all[eo:eo+e].copy(), r_all[ro:ro+r].copy()
            self.eliminated.append((E, rest, ree[qo:qo+e*e].reshape(e, e).copy(), rer[so:so+e*r].reshape(e, r).copy(),
                                    ze[eo:eo+e].copy()))
            eo, ro, qo, so = eo+e, ro+r, qo+e*e, so+e*r
        # The recovery layout is validated exactly as Accumulator.restore does it (shared code, empty factor).
        base = Accumulator.restore(dict({key: data[key] for key in ("n", "norm2", "local_explained", "lost", "rows",
                                                                    "local_total", "largest_update_rows", "active_lengths",
                                                                    "local_lengths", "active", "d", "B")},
                                        R=np.zeros((0, n)), z=np.zeros(0)))
        self.recovery = base.recovery
        return self
