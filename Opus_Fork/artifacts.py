"""Bounded-memory validation of the arrays a fork worker produced (Astra E-01, check-in C01; AR-02 follow-up).

`run_fit_elev.worker_rejection` calls `rejection(kind, path)` before a worker is recorded `ok` and again before it is
reused. A matching hash proves only that the bytes did not change after they were recorded, not that they are usable.
Here every array file is opened as an NPZ archive without unpickling, and:
- each member's `.npy` header is read: version, dtype (never object; at most MAX_ITEM_BYTES per item), shape;
- the kind's required members, shapes, dtypes and cross-member layout are checked; for a checkpoint these are the
  same rules `claude.roadmap.streaming.Accumulator.restore` applies;
- every member's payload, whatever its dtype, is streamed once in bounded chunks:
  - the byte count must equal the header's (sizes computed with Python integers, so no overflow);
  - the archive's CRC is verified and no trailing bytes are allowed;
  - floating members must be finite;
  - a checkpoint's recovery indices are checked in range and strictly increasing per block as they stream;
- small members are read only after their header shows a bounded size: scalars must have shape (), and the per-block
  lengths are limited to MAX_BLOCKS elements.

No array is held in memory whole: the controller runs outside any guard. No orbit is integrated and nothing is
fitted.
"""
import json
import math
import zipfile

import numpy as np
from numpy.lib import format as npformat

CHUNK_BYTES = 1 << 22
MAX_BLOCKS = 1 << 20
# A partial item is carried between chunks, so the read buffer is bounded only if items are (Astra peek, 2 Oct 2026:
# a wide fixed-width string dtype would grow the carry to its item size). Worker outputs use numbers and short names.
MAX_ITEM_BYTES = 1 << 12


def _header(stream):
    version = npformat.read_magic(stream)
    if version == (1, 0):
        shape, fortran, dtype = npformat.read_array_header_1_0(stream)
    elif version == (2, 0):
        shape, fortran, dtype = npformat.read_array_header_2_0(stream)
    else:
        raise ValueError(f"unsupported .npy version {version}")
    if dtype.hasobject:
        raise ValueError("object (pickled) array")
    if dtype.itemsize > MAX_ITEM_BYTES:
        raise ValueError(f"dtype {dtype} has {dtype.itemsize}-byte items (at most {MAX_ITEM_BYTES})")
    return dtype, tuple(int(d) for d in shape), bool(fortran)


def _archive(path):
    try:
        return zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError(f"not an NPZ archive ({error.__class__.__name__})") from None


def members(path):
    """{name: (dtype, shape)} from the NPZ members' headers; refuses non-NPZ bytes and object arrays."""
    out = {}
    with _archive(path) as archive:
        for info in archive.infolist():
            if not info.filename.endswith(".npy"):
                raise ValueError(f"unexpected archive member {info.filename!r}")
            try:
                with archive.open(info) as stream:
                    dtype, shape, _ = _header(stream)
            except zipfile.BadZipFile as error:
                raise ValueError(f"{info.filename}: archive member is corrupt ({str(error)[:80]})") from None
            out[info.filename[:-4]] = (dtype, shape)
    return out


def payload_bytes(dtype, shape):
    return math.prod(shape)*dtype.itemsize          # Python integers: no overflow


def stream_payloads(path, visitors=None):
    """Read every member's payload once, in bounded chunks; returns the names whose floating values are not finite.

    Checks: exact byte count against the header, archive CRC (zipfile verifies it at the end of each member) and no
    trailing bytes. `visitors[name](values)` receives each aligned chunk of that member as a 1-D array. A buffer never
    exceeds CHUNK_BYTES + MAX_ITEM_BYTES.
    """
    visitors = visitors or {}
    nonfinite = []
    with _archive(path) as archive:
        for info in archive.infolist():
            name = info.filename[:-4]
            try:
                with archive.open(info) as stream:
                    dtype, shape, fortran = _header(stream)
                    remaining, carry, bad = payload_bytes(dtype, shape), b"", False
                    while remaining > 0:
                        data = stream.read(min(CHUNK_BYTES, remaining))
                        if not data:
                            raise ValueError(f"{name}: payload truncated ({remaining} bytes missing)")
                        remaining -= len(data)
                        data = carry+data
                        usable = len(data)-len(data) % dtype.itemsize
                        carry = data[usable:]
                        values = np.frombuffer(data[:usable], dtype=dtype)
                        if dtype.kind in "fc" and not bad and not np.all(np.isfinite(values)):
                            bad = True
                        if name in visitors:
                            visitors[name](values)
                    if carry or stream.read(1):
                        raise ValueError(f"{name}: payload length does not match its header")
            except zipfile.BadZipFile as error:
                raise ValueError(f"{name}: archive member is corrupt ({str(error)[:80]})") from None
            if bad:
                nonfinite.append(name)
    return nonfinite


def small(path, name, kinds, max_elements=1, shape=None):
    """Read a member only after its header shows at most `max_elements` elements (and `shape`, if given)."""
    try:
        with _archive(path) as archive, archive.open(name+".npy") as stream:
            dtype, got, _ = _header(stream)
            if dtype.kind not in kinds or math.prod(got) > max_elements or (shape is not None and got != shape):
                raise ValueError(f"member {name!r} has dtype {dtype} and shape {got}")
        with _archive(path) as archive, archive.open(name+".npy") as stream:
            return npformat.read_array(stream, allow_pickle=False)
    except zipfile.BadZipFile as error:
        raise ValueError(f"{name}: archive member is corrupt ({str(error)[:80]})") from None


def _require(m, name, kinds, ndim=None):
    if name not in m:
        raise ValueError(f"required member {name!r} missing")
    dtype, shape = m[name]
    if dtype.kind not in kinds or (ndim is not None and len(shape) != ndim):
        raise ValueError(f"member {name!r} has dtype {dtype} and shape {shape}")
    return shape


def check_trajectories(path, satellites):
    m = members(path)
    expected = {"times"} | {f"{s}_{k}" for s in satellites for k in ("states", "stm", "sensitivity")}
    if set(m) != expected:
        raise ValueError(f"members differ from the recorded satellites: missing {sorted(expected-set(m))[:4]}, "
                         f"extra {sorted(set(m)-expected)[:4]}")
    (n,) = _require(m, "times", "f", 1)
    sensitivity = None
    for s in satellites:
        if _require(m, f"{s}_states", "f") != (n, 6) or _require(m, f"{s}_stm", "f") != (n, 6, 6):
            raise ValueError(f"{s} state or STM shape inconsistent with {n} times")
        shape = _require(m, f"{s}_sensitivity", "f", 3)
        if shape[:2] != (n, 6) or (sensitivity is not None and shape != sensitivity):
            raise ValueError(f"{s} sensitivity shape {shape}")
        sensitivity = shape
    return m, {}


class _ActiveOrder:
    """Streams the recovery indices: in [0, n) and strictly increasing inside each block (Accumulator.restore)."""

    def __init__(self, lengths, n):
        self.lengths, self.n, self.block, self.left, self.last = [int(v) for v in lengths], int(n), 0, None, None

    def __call__(self, values):
        for v in values.tolist():
            while self.left is None or self.left == 0:
                if self.left == 0:
                    self.block += 1
                if self.block >= len(self.lengths):
                    raise ValueError("checkpoint recovery indices exceed their recorded block lengths")
                self.left, self.last = self.lengths[self.block], None
            if not 0 <= v < self.n or (self.last is not None and v <= self.last):
                raise ValueError("checkpoint recovery indices are not unique, increasing and in range in a block")
            self.last, self.left = v, self.left-1


def check_checkpoint(path):
    m = members(path)
    for name in ("R", "z", "norm2", "d", "B", "residual", "sigma", "local_explained", "lost"):
        _require(m, name, "f")
    for name in ("n", "rows", "local_total", "largest_update_rows", "active_lengths", "local_lengths", "active"):
        _require(m, name, "iu")
    for name in ("n", "rows", "local_total", "largest_update_rows", "local_explained", "lost"):
        if m[name][1] != ():
            raise ValueError(f"member {name!r} must be a scalar, has shape {m[name][1]}")
    n = int(small(path, "n", "iu", shape=()))
    k, columns = _require(m, "R", "f", 2)
    width = _check_elimination(path, m, n) if "kind" in m else n
    if columns != width or k > width or m["z"][1] != (k,) or m["norm2"][1] != (n,):
        raise ValueError("checkpoint R/z/norm2 shapes are inconsistent")
    blocks = _require(m, "active_lengths", "iu", 1)
    if _require(m, "local_lengths", "iu", 1) != blocks or blocks[0] > MAX_BLOCKS:
        raise ValueError("checkpoint recovery length arrays are inconsistent")
    active_lengths = small(path, "active_lengths", "iu", MAX_BLOCKS).astype(object)     # Python ints: no overflow
    local_lengths = small(path, "local_lengths", "iu", MAX_BLOCKS).astype(object)
    if any(v < 0 for v in active_lengths) or any(v < 1 for v in local_lengths) \
            or int(small(path, "local_total", "iu", shape=())) != sum(local_lengths) \
            or int(small(path, "rows", "iu", shape=())) < 0:
        raise ValueError("checkpoint recovery counts are inconsistent with their recorded layout")
    if _require(m, "active", "iu", 1) != (sum(active_lengths),) or _require(m, "d", "f", 1) != (sum(local_lengths),) \
            or _require(m, "B", "f", 1) != (sum(a*b for a, b in zip(active_lengths, local_lengths)),):
        raise ValueError("checkpoint recovery arrays are inconsistent with their recorded layout")
    if _require(m, "residual", "f", 1) != _require(m, "sigma", "f", 1):
        raise ValueError("checkpoint residual and sigma lengths differ")
    return m, {"active": _ActiveOrder(active_lengths, n)}


def _check_elimination(path, m, n):
    """EliminatingAccumulator checkpoint layout (7 Oct 2026), the rules of EliminatingAccumulator.restore; returns the
    active width of R. Every index array here has at most n elements, so it is read whole."""
    if int(small(path, "kind", "iu", shape=())) != 1:
        raise ValueError("unknown checkpoint kind")
    for name in ("eliminated_explained",):
        if _require(m, name, "f") != ():
            raise ValueError(f"member {name!r} must be a scalar")
    for name in ("elim_R", "elim_Rrest", "elim_z"):
        _require(m, name, "f", 1)
    last = small(path, "last_epoch", "iu", n, shape=(n,)).astype(np.int64)
    state = small(path, "column_state", "iu", n, shape=(n,)).astype(np.int64)
    columns = small(path, "columns", "iu", n).astype(np.int64)
    prefix = int(small(path, "covariance_prefix", "iu", shape=()))
    widest = int(small(path, "max_active", "iu", shape=()))
    e_len = small(path, "elim_lengths", "iu", n).astype(object)          # Python ints: no overflow
    r_len = small(path, "rest_lengths", "iu", n).astype(object)
    e_all = small(path, "elim_columns", "iu", n).astype(np.int64)
    if np.any(last < -1) or not 0 < prefix <= n or np.any(last[:prefix] != -1) \
            or not set(np.unique(state).tolist()) <= {0, 1, 2} or np.any(state[last == -1] != 1) \
            or len(np.unique(columns)) != len(columns) or not np.array_equal(np.sort(columns), np.flatnonzero(state == 1)) \
            or widest < len(columns):
        raise ValueError("checkpoint column states are inconsistent")
    if len(e_len) != len(r_len) or any(v < 1 for v in e_len) or any(v < 0 for v in r_len) \
            or len(e_all) != sum(e_len) or len(np.unique(e_all)) != len(e_all) \
            or (len(e_all) and np.any(state[e_all] != 2)) or int(np.sum(state == 2)) != len(e_all) \
            or _require(m, "rest_columns", "iu", 1) != (sum(r_len),) or m["elim_z"][1] != (sum(e_len),) \
            or m["elim_R"][1] != (sum(e*e for e in e_len),) or m["elim_Rrest"][1] != (sum(e*r for e, r in zip(e_len, r_len)),):
        raise ValueError("checkpoint elimination record is inconsistent with its layout")
    return len(columns)


def check_solution(path):
    m = members(path)
    (n,) = _require(m, "x", "f", 1)
    if _require(m, "names", "U", 1) != (n,):
        raise ValueError("names and x lengths differ")
    s, t, six = _require(m, "states", "f", 3)
    if six != 6 or _require(m, "satellites", "U", 1) != (s,) or _require(m, "times_s", "f", 1) != (t,):
        raise ValueError("states, satellites and times are inconsistent")
    if _require(m, "residual_m", "f", 1) != _require(m, "sigma_m", "f", 1):
        raise ValueError("residual and sigma lengths differ")
    r, r2 = _require(m, "retained_covariance", "f", 2)
    if r != r2 or r > n:
        raise ValueError("retained covariance shape")
    return m, {}


def check_direction(path):
    m = members(path)
    (n,) = _require(m, "x", "f", 1)
    if _require(m, "step", "f", 1) != (n,) or _require(m, "names", "U", 1) != (n,):
        raise ValueError("x, step and names lengths differ")
    r, r2 = _require(m, "retained_covariance", "f", 2)
    if r != r2 or r > n:
        raise ValueError("retained covariance shape")
    return m, {}


def check_state(path):
    def refuse(token):
        raise ValueError(f"non-finite JSON constant {token}")
    record = json.loads(path.read_text(), parse_constant=refuse)
    values = [v for _, v in record["clock_seeds"]]+list(record["windup"])+list(record["amb_origins"].values())
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        raise ValueError("non-finite or non-numeric state value")


def rejection(kind, path, satellites=None):
    """None, or why the array/record file at `path` is not a usable output of a worker of this kind."""
    checks = {"trajectories": lambda: check_trajectories(path, satellites), "checkpoint": lambda: check_checkpoint(path),
              "solution": lambda: check_solution(path), "direction": lambda: check_direction(path)}
    try:
        if kind == "state":
            check_state(path)
            return None
        _, visitors = checks[kind]()
        nonfinite = stream_payloads(path, visitors)
        if nonfinite:
            return f"{path.name} contains non-finite values in {', '.join(nonfinite[:3])}"
    except (ValueError, KeyError, TypeError) as error:
        return f"{path.name} is not a usable {kind} output: {error}"
    return None
