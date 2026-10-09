"""Shared pieces of the joint weighted transfer calculation (protocol: `PROTOCOL.md` in this folder).

Nothing here edits a file outside this experiment's own guard run folders. Pins and conventions:
- linearization point: SD-3 (Aug 3) final `lin2-solve`, rebuilt exactly as `experiments/residuals/replay.py` does;
- `MultiAccumulator`: `claude.roadmap.streaming.Accumulator` with a matrix of right-hand sides instead of one vector
  (same whitening, local elimination, streaming QR, constraint rows, final `_factor` column scale and rank rule);
- `helmert_scale`: the design of `Opus_Fork/score.py:helmert_residual` (unweighted, 7 parameters);
- `harm`: the hourly 12 h / 24 h harmonic fit of `experiments/sensitivity/analyze.py`.
"""
import copy
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy.linalg import qr_multiply

from Opus_Fork.paths import ROOT

HERE = Path(__file__).resolve().parent
SD3 = ROOT/"Opus_Fork/runs/20260925T215927Z-fit-SD-3-25st"
NOPCV = ROOT/"Opus_Fork/runs/20260926T173845Z-fit-S-nopcv-3"
FIXTURE = ROOT/"Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03/fixture.json"
CONFIG = ROOT/"claude/roadmap/configs/unit-ecom5.json"
PROTOCOL = HERE/"PROTOCOL.md"
PROTOCOL_SHA256 = "e4c39bff5349e3c843a3b6a82a52fdaac5ee263835189d1926b01528d246edc9"
# Appended amendments, each pinned before its effect was known (the body above stays pinned unchanged).
AMENDMENTS_SHA256 = {"A1": "35c35fbdf848282dcb515d95a1c3d73dfcf722019503eb5c8295a108b6c7fae8"}
SOLUTION_SHA256 = "c0311ba1249e85c23e538f7ef7f8069f3cbb200e2923efa189c11160ff63fb94"

TARGETS = ("y", "nopcv", "pcoz_p1cm", "solid_iers_minus_fixture", "otl_nodal_minus_fixture",
           "h_const_1mm", "h12_cos_1mm", "h12_sin_1mm", "h24_cos_1mm", "h24_sin_1mm",
           "sat_nadir_lin_1mm", "sat_nadir_quad_1mm", "rx_elev_cos_1mm")
K = len(TARGETS)
COL = {name: j for j, name in enumerate(TARGETS)}
GPS_EPOCH = datetime(1980, 1, 6)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_sha(x):
    return hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()


def run_dir():
    folder = os.environ.get("CUSTOMKF_RUN_DIR")
    if not folder:
        raise RuntimeError("Use the root guard: python -m customkf.guard --profile usage75 --timeout 300 -- MODULE")
    return Path(folder)


K1_TOLERANCE_M = 1e-6


def chunk_chain(last, epoch_count):
    """Walk the chunk chain back from `last` through `previous`: every chunk complete, epochs contiguous from 0 to
    `epoch_count`, and K1 (re-evaluated misclosure vs the fit's residual, PROTOCOL.md) aggregated over all chunks.

    Added 29 Sep 2026 (checkpoint-A review A05): K1 was recorded per chunk but never enforced. Raises on a gap, an
    overlap, a loop, a missing link or an incomplete chunk.
    """
    # Hardened 29 Sep 2026 (addendum review AA03): K1 values must be finite and non-negative (Python's max() can hide
    # a NaN), and every span must be a forward integer interval inside [0, epoch_count].
    if isinstance(epoch_count, bool) or not isinstance(epoch_count, int) or epoch_count <= 0:
        raise ValueError(f"Epoch count must be a positive integer, not {epoch_count!r}")
    chain, folder, seen = [], Path(last), set()
    while folder is not None:
        if str(folder) in seen or len(chain) > 1000:
            raise ValueError(f"Chunk chain loops at {folder}")
        seen.add(str(folder))
        step = json.loads((folder/"step.json").read_text())
        if step.get("status") != "transfer_chunk_complete":
            raise ValueError(f"Chunk {folder} is not complete: {step.get('status')}")
        start, stop, k1 = step["start"], step["stop"], step["checks"]["max_abs_vs_fit_residual_m"]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, stop)) \
                or not 0 <= start < stop <= epoch_count:
            raise ValueError(f"Chunk {folder} has an invalid span {start!r}..{stop!r} for {epoch_count} epochs")
        if isinstance(k1, bool) or not isinstance(k1, (int, float)) or not math.isfinite(k1) or k1 < 0:
            raise ValueError(f"Chunk {folder} has an invalid K1 value {k1!r}")
        chain.append(dict(folder=str(folder), start=start, stop=stop, k1_max_abs_m=float(k1)))
        folder = Path(step["previous"]) if step.get("previous") else None
    chain.reverse()
    expected = 0
    for c in chain:
        if c["start"] != expected:
            raise ValueError(f"Chunk chain gap or overlap at {c['folder']}: starts at {c['start']}, expected {expected}")
        expected = c["stop"]
    if expected != epoch_count:
        raise ValueError(f"Chunk chain ends at epoch {expected}, not {epoch_count}")
    k1 = max(c["k1_max_abs_m"] for c in chain)
    return dict(chunks=chain, K1_max_abs_m=k1, K1_pass=bool(k1 <= K1_TOLERANCE_M))


def candidates_allowed(checks, calibration):
    """The protocol gate: K1, K2 and K3 must all pass (a missing check counts as a failure), and the calibration too."""
    return all(bool(checks.get(k)) for k in ("K1_pass", "K2_pass", "K3_pass")) and bool(calibration.get("pass"))


def check_protocol():
    """The pre-registered body (everything before the first "## Amendment" heading) must hash to its original pin, and
    each appended amendment to its own pin. Returns the body hash, which the chunk outputs recorded."""
    text = PROTOCOL.read_bytes()
    parts = text.split(b"\n## Amendment ")
    body = parts[0].rstrip(b"\n")+b"\n"
    got = hashlib.sha256(body).hexdigest()
    if got != PROTOCOL_SHA256:
        raise RuntimeError(f"PROTOCOL.md body changed after it was pinned: {got}")
    amendments = [b"## Amendment "+part for part in parts[1:]]
    names = [a[len(b"## Amendment "):].split(b" ", 1)[0].decode() for a in amendments]
    if names != list(AMENDMENTS_SHA256):
        raise RuntimeError(f"PROTOCOL.md amendments {names} differ from the pinned set {list(AMENDMENTS_SHA256)}")
    for name, amendment in zip(names, amendments):
        if hashlib.sha256(amendment).hexdigest() != AMENDMENTS_SHA256[name]:
            raise RuntimeError(f"PROTOCOL.md amendment {name} changed after it was pinned")
    return got


def midnight_ns(context):
    """GPS ns of 00:00 of the fixture day; the fixture origin is 10 s before it (checked, not assumed)."""
    ns = int(context["origin_ns"])+10*10**9
    t = GPS_EPOCH+timedelta(seconds=ns/1e9)
    assert (t.hour, t.minute, t.second, t.microsecond) == (0, 0, 0, 0) and t.date().isoformat() == context["day"], t
    return ns


def ut_hours(context, time_s):
    offset_s = (midnight_ns(context)-int(context["origin_ns"]))/1e9   # exact integer difference (10 s)
    return (np.asarray(time_s, dtype=float)-offset_s)/3600.


def load_linearization_point():
    """SD-3's pilot, x and final-linearization products, rebuilt as its workers built them (replay.py)."""
    v = json.loads((SD3/"validation.json").read_text())
    assert v["status"].startswith("long_fit_complete") and v["final"] == "lin2-solve", v["status"]
    assert (ROOT/v["fixture"]).resolve() == FIXTURE.resolve() and (ROOT/v["config"]).resolve() == CONFIG.resolve()
    os.environ["OPUSFORK_SD_VARIANT"] = v["force_model"]["variant"]
    from Opus_Fork import sdeop
    iteration = sdeop.install()
    from claude.roadmap.traj_cache import cached_products
    state = SD3/v["state"]["path"]
    assert sha(state) == v["state"]["sha256"]
    pilot, _ = iteration.build(SimpleNamespace(fixture=FIXTURE, config=CONFIG, state=state))
    step = json.loads((SD3/"lin2-solve"/"step.json").read_text())
    solution = SD3/"lin2-solve"/"solution.npz"
    assert step["status"] == "converged" and sha(solution) == step["solution_sha256"] == SOLUTION_SHA256
    with np.load(solution) as f:
        names, x, residual = f["names"], f["x"].copy(), f["residual_m"].copy()
    np.testing.assert_array_equal(names, pilot.names)
    assert array_sha(x) == step["binding"]["x"]
    files = sorted(str(p) for p in SD3.glob("lin2-traj-*/trajectories.npz"))
    expected = sdeop.binding()
    skipped = set()
    for f in files:
        got = json.loads((Path(f).parent/"trajectories.json").read_text())["force_model"]
        diff = {k for k in set(got) | set(expected) if got.get(k) != expected.get(k)}
        assert diff <= {"subdaily_eop_sha256", "sdeop_sha256"}, diff
        skipped |= diff
    products = cached_products(pilot, x, files)
    binding = dict(fixture=sha(FIXTURE), config=sha(CONFIG), state=sha(state), x=array_sha(x), solution=SOLUTION_SHA256,
                   protocol=check_protocol())
    return SimpleNamespace(pilot=pilot, x=x, products=products, residual=residual, step=step, files=files,
                           binding=binding, binding_fields_not_checked=sorted(skipped), validation=v)


def zero_pcv(cal):
    """Identical to `Opus_Fork/sens.py` (nopcv): NOAZI and azimuth PCV tables zeroed, PCOs kept."""
    cal = copy.deepcopy(cal)
    for data in cal.frequencies.values():
        if data.get("noazi") is not None:
            data["noazi"] = np.zeros_like(data["noazi"])
        for az in list(data.get("azimuth") or {}):
            data["azimuth"][az] = np.zeros_like(data["azimuth"][az])
    return cal


def shift_pco_z(cal, dz):
    cal = copy.deepcopy(cal)
    for freq in ("G01", "G02"):
        pco = np.array(cal.frequencies[freq]["pco"], dtype=float)
        pco[2] += dz
        cal.frequencies[freq]["pco"] = pco
    return cal


class MultiAccumulator:
    """`claude.roadmap.streaming.Accumulator` with K right-hand sides (columns of `targets`).

    R is identical to the single-target accumulator's (QR of the same whitened, locally projected rows); Z holds
    Qᵀ·targets. Local-clock recovery blocks are not kept: only retained parameters are needed here.
    """

    def __init__(self, n, k):
        self.n, self.k = int(n), int(k)
        self.R = np.zeros((0, self.n))
        self.Z = np.zeros((0, self.k))
        self.norm2 = np.zeros(self.n)
        self.local_explained = np.zeros(self.k)
        self.lost = np.zeros(self.k)
        self.rows = 0
        self.local_total = 0
        self.largest_update_rows = 0

    def _update(self, a, t):
        if not len(t):
            return
        m = np.vstack([self.R, a])
        rhs = np.vstack([self.Z, t])
        self.largest_update_rows = max(self.largest_update_rows, len(rhs))
        qt, r = qr_multiply(m, rhs.T, mode="right")
        self.R, self.Z = r, np.ascontiguousarray(qt.T)
        self.lost += np.sum(rhs*rhs, axis=0)-np.sum(qt*qt, axis=1)

    def add_block(self, retained, local, targets, sigma):
        from customkf.network_square_root import _factor
        g = retained/sigma[:, None]
        l = local/sigma[:, None]
        y = targets/sigma[:, None]
        if not (np.isfinite(g).all() and np.isfinite(l).all() and np.isfinite(y).all()) or np.any(sigma <= 0):
            raise ValueError("Invalid block values")
        if g.shape[1] != self.n or not 0 < l.shape[1] <= len(l) or y.shape != (len(g), self.k):
            raise ValueError("Invalid block dimensions")
        self.norm2 += np.sum(g*g, axis=0)
        q, _ = _factor(l, full=True)
        k = l.shape[1]
        q1, q2 = q[:, :k], q[:, k:]
        qy = q1.T@y
        self.local_explained += np.sum(qy*qy, axis=0)
        self._update(q2.T@g, q2.T@y)
        self.rows += len(y)
        self.local_total += k

    def add_constraints(self, c, z, s):
        c = c/s[:, None]
        z = z/s[:, None]
        self.norm2 += np.sum(c*c, axis=0)
        self._update(c, z)
        self.rows += len(z)

    def solve(self):
        """Same pre-projection column scale and rank rule as `Accumulator.solve` (customkf.network_square_root._factor)."""
        from customkf.network_square_root import _factor
        if self.R.shape != (self.n, self.n):
            raise ValueError("Underdetermined accumulated system")
        if self.rows < self.n+self.local_total:
            raise ValueError("Fewer rows than parameters")
        q, mapping = _factor(self.R, column_scale=1/np.maximum(np.sqrt(self.norm2), 1e-30))
        estimate = mapping@(q.T@self.Z)
        reduction = self.local_explained+np.sum(self.Z*self.Z, axis=0)
        return estimate, mapping, reduction

    def state(self):
        return dict(n=self.n, k=self.k, R=self.R, Z=self.Z, norm2=self.norm2, local_explained=self.local_explained,
                    lost=self.lost, rows=self.rows, local_total=self.local_total,
                    largest_update_rows=self.largest_update_rows, targets=np.array(TARGETS))

    @classmethod
    def restore(cls, data):
        assert tuple(str(t) for t in data["targets"]) == TARGETS
        self = cls(int(data["n"]), int(data["k"]))
        self.R, self.Z, self.norm2 = data["R"].copy(), data["Z"].copy(), data["norm2"].copy()
        self.local_explained, self.lost = data["local_explained"].copy(), data["lost"].copy()
        self.rows, self.local_total = int(data["rows"]), int(data["local_total"])
        self.largest_update_rows = int(data["largest_update_rows"])
        return self


def helmert_design(p):
    """`Opus_Fork/score.py:helmert_residual` design: translation, rotation, scale on positions p (m, 3)."""
    design = np.zeros((3*len(p), 7))
    for i, q in enumerate(p):
        design[3*i:3*i+3, :3] = np.eye(3)
        design[3*i:3*i+3, 3:6] = np.array([[0, q[2], -q[1]], [-q[2], 0, q[0]], [q[1], -q[0], 0]])
        design[3*i:3*i+3, 6] = q
    return design


def helmert_scale(p, d):
    """Scale (ppb) of the unweighted 7-parameter fit of differences d (m, 3[, K]) on positions p (m, 3)."""
    design = helmert_design(p)
    rhs = d.reshape(3*len(p), -1)
    solution, *_ = np.linalg.lstsq(design, rhs, rcond=None)
    return solution[6]*1e9


def scale_operator(p):
    """Row vector h (3m) with scale_ppb = h·vec(d); the same least-squares solution as `helmert_scale`."""
    return np.linalg.pinv(helmert_design(p))[6]*1e9


def harm(y):
    """`experiments/sensitivity/analyze.py:harm` (24 hourly values at h+0.5)."""
    h = np.arange(24)+0.5
    w = 2*np.pi/24
    a = np.column_stack([np.ones(24), np.cos(w*h), np.sin(w*h), np.cos(2*w*h), np.sin(2*w*h)])
    c, *_ = np.linalg.lstsq(a, np.asarray(y, dtype=float), rcond=None)
    return dict(mean=float(c[0]), amp12=float(np.hypot(c[3], c[4])), peak12_ut=float((np.degrees(np.arctan2(c[4], c[3])) % 360)/30),
                amp24=float(np.hypot(c[1], c[2])), peak24_ut=float((np.degrees(np.arctan2(c[2], c[1])) % 360)/15),
                c12=[float(c[3]), float(c[4])], c24=[float(c[1]), float(c[2])])


def hourly(per_epoch):
    """Mean of the four 15-min epochs in each UT hour (96 → 24)."""
    return np.asarray(per_epoch, dtype=float).reshape(24, 4).mean(1)


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, default=float)+"\n")
