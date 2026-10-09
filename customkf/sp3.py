"""Small strict GPS position reader for Stage 0 fixtures (SP3-a/c/d).

Not a general SP3 library. Velocity/covariance records are counted but not used.
Keep nanosecond GPS epoch tags, invalid values and event flags explicit.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import gzip
import math
from pathlib import Path
import re

GPS_START = datetime(1980, 1, 6)


@dataclass(frozen=True)
class Sample:
    epoch_ns: int
    sat: str
    xyz_m: tuple | None
    clock_s: float | None
    clock_event: bool = False
    clock_predicted: bool = False
    maneuver: bool = False
    orbit_predicted: bool = False


@dataclass
class Product:
    version: str
    frame: str
    time_system: str
    samples: dict
    comments: list
    velocity_records_ignored: int


def epoch_tag(text):
    fields = text.split()
    if len(fields) != 7 or fields[0] != "*":
        raise ValueError("Malformed SP3 epoch")
    y, mo, d, h, mi = map(int, fields[1:6])
    sec = Decimal(fields[6])
    ns = sec*10**9
    if not sec.is_finite() or not 0 <= sec < 60 or ns != ns.to_integral_value():
        raise ValueError("Invalid GPS seconds or precision finer than nanoseconds")
    delta = datetime(y, mo, d, h, mi)-GPS_START
    if delta.days < 0:
        raise ValueError("Epoch precedes GPS epoch")
    return (delta.days*86400+delta.seconds)*10**9+int(ns)


def gps_id(text):
    token = text.strip()
    if token.isdigit():
        token = "G"+token.zfill(2)
    if not re.fullmatch(r"[A-Z]\d{2}", token):
        raise ValueError(f"Malformed satellite ID: {text!r}")
    if token.startswith("G") and not 1 <= int(token[1:]) <= 32:
        raise ValueError("GPS PRN outside 01..32")
    return token


def read_sp3(path, *, legacy_a_time_system=None):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    samples, comments = {}, []
    epoch = None
    epochs = []
    time_system = None
    velocities = 0
    eof = False
    with opener(path, "rt", encoding="ascii") as stream:
        first = stream.readline()
        if len(first) < 51 or first[:2] not in ("#a", "#c", "#d") or first[2] not in "PV":
            raise ValueError("Unsupported or malformed SP3 header")
        version, frame = first[1], first[46:51].strip()
        expected = int(first[32:39])
        if not frame:
            raise ValueError("SP3 frame is missing")
        for number, line in enumerate(stream, 2):
            if line.startswith("%c") and time_system is None:
                time_system = line[9:12].strip()
            elif line.startswith("/*"):
                comments.append(line[2:].strip())
            elif line.startswith("*"):
                epoch = epoch_tag(line)
                if epochs and epoch <= epochs[-1]:
                    raise ValueError("Epochs must be strictly increasing")
                epochs.append(epoch)
            elif line.startswith("P"):
                if epoch is None or len(line.rstrip("\r\n")) < 60:
                    raise ValueError(f"Malformed position record at line {number}")
                sat = gps_id(line[1:4])
                if not sat.startswith("G"):
                    continue
                key = (epoch, sat)
                if key in samples:
                    raise ValueError(f"Duplicate GPS sample {key}")
                values = [float(line[i:i+14]) for i in (4, 18, 32, 46)]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError(f"Nonfinite SP3 value at line {number}")
                xyz = values[:3]
                invalid = all(v == 0 for v in xyz) or any(abs(v) >= 999999 for v in xyz)
                flags = line.rstrip("\r\n").ljust(80)
                samples[key] = Sample(epoch, sat, None if invalid else tuple(v*1000 for v in xyz),
                                      None if abs(values[3]) >= 999999 else values[3]*1e-6,
                                      flags[74] == "E", flags[75] == "P", flags[78] == "M", flags[79] == "P")
            elif line.startswith("V"):
                velocities += 1
            elif line.startswith("EOF"):
                eof = True
                break
        if not eof or len(epochs) != expected:
            raise ValueError(f"Truncated/inconsistent SP3: {len(epochs)} epochs, expected {expected}, EOF={eof}")
    if version == "a" and time_system in (None, "ccc"):
        if legacy_a_time_system != "GPS":
            raise ValueError("SP3-a requires explicit legacy_a_time_system='GPS' provenance")
        time_system = "GPS"
    if time_system != "GPS":
        raise ValueError(f"Unsupported time system {time_system!r}; no implicit conversion")
    return Product(version, frame, time_system, samples, comments, velocities)


def matched_samples(reference, candidate, *, position_origin, exclude_satellite_days=frozenset()):
    """Strict same-frame exact-epoch matching. No residual-dependent editing.

    position_origin is a required (reference, candidate) pair of declarations.
    SP3 headers alone do not establish centre-of-mass convention.
    """
    if position_origin != ("COM", "COM"):
        raise ValueError("Both product origins must explicitly be declared COM")
    if reference.frame != candidate.frame or reference.time_system != candidate.time_system:
        raise ValueError("Frame/time mismatch: no silent alignment or relabelling")
    counts = {"reference_only":len(reference.samples.keys()-candidate.samples.keys()),
              "candidate_only":len(candidate.samples.keys()-reference.samples.keys()),
              "invalid_position":0, "orbit_event_or_prediction":0, "declared_exclusion":0}
    selected = []
    for key in sorted(reference.samples.keys() & candidate.samples.keys()):
        a, b = reference.samples[key], candidate.samples[key]
        if a.xyz_m is None or b.xyz_m is None:
            counts["invalid_position"] += 1
        elif a.maneuver or b.maneuver or a.orbit_predicted or b.orbit_predicted:
            counts["orbit_event_or_prediction"] += 1
        elif (key[0]//(86400*10**9), key[1]) in exclude_satellite_days:
            counts["declared_exclusion"] += 1
        else:
            selected.append((a, b))
    counts["matched"] = len(selected)
    return selected, counts
