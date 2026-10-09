"""Shared helpers for Claude's roadmap experiments (claude/roadmap/).

Isolated from Astra's pinned trees: nothing here is imported by customkf/, claude/tools/ or
claude/checks/. Reference products are opened only by callers that are evaluation or
reference-calibration workers, never by a station estimator.
"""
from datetime import datetime
import json
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, DATA as DYN, sha
from customkf.prepare_stage3 import DATA

ROADMAP = ROOT/"claude/roadmap"
BLOCK_GROUPS = {"BLOCK IIF": "IIF", "BLOCK IIIA": "IIIA", "BLOCK IIR-M": "IIR-M",
                "BLOCK IIR-A": "IIR", "BLOCK IIR-B": "IIR"}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x.item())+"\n")


def sources(extra=()):
    """Hashes of every Python source a roadmap worker can import, plus declared documents."""
    paths = [p for d in ("customkf", "claude/tools", "claude/roadmap") for p in (ROOT/d).glob("*.py")]
    paths += [ROOT/p for p in extra]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def satellite_blocks(day, path=DATA/"igs20.atx"):
    """PRN -> (ANTEX block type, SVN) valid at 00:00 of the given date; GPS only."""
    when = datetime.strptime(day, "%Y-%m-%d")
    found, current = {}, None
    with open(path) as stream:
        for line in stream:
            label = line[60:].strip()
            if label == "START OF ANTENNA":
                current = {}
            elif current is None:
                continue
            elif label == "TYPE / SERIAL NO":
                current.update(type=line[:20].strip(), prn=line[20:40].strip(), svn=line[40:50].strip())
            elif label in ("VALID FROM", "VALID UNTIL"):
                f = line[:43].split()
                current[label] = datetime(int(f[0]), int(f[1]), int(f[2]), int(f[3]), int(f[4]))
            elif label == "END OF ANTENNA":
                prn = current.get("prn", "")
                if len(prn) == 3 and prn.startswith("G"):
                    start, end = current.get("VALID FROM", datetime.min), current.get("VALID UNTIL", datetime.max)
                    if start <= when < end:
                        if prn in found:
                            raise ValueError("Ambiguous ANTEX PRN mapping: "+prn)
                        found[prn] = (current["type"], current["svn"])
                current = None
    return found


def block_group(block_type):
    if block_type not in BLOCK_GROUPS:
        raise ValueError("Undeclared block type: "+block_type)
    return BLOCK_GROUPS[block_type]


class DatedReference:
    """IGS rapid SP3 for an explicit day; pinned in data/stage3/manifest.json. Evaluation only."""
    def __init__(self, day, origin_ns):
        from customkf.frames import FrameEpoch, EarthOrientation
        from customkf.precise import PreciseProducts
        from customkf.sp3 import read_sp3
        stamp = datetime.strptime(day, "%Y-%m-%d").strftime("%Y%j")
        path = DATA/f"IGS0OPSRAP_{stamp}0000_01D_15M_ORB.SP3.gz"
        pinned = {e["path"]: e["sha256"] for e in json.loads((DATA/"manifest.json").read_text())["files"]}
        relative = path.relative_to(ROOT).as_posix()
        if pinned.get(relative) != sha(path):
            raise ValueError("Unpinned or changed reference product: "+relative)
        self.path, self.sha256, self.origin = path, pinned[relative], int(origin_ns)
        self.epoch = FrameEpoch(self.origin, EarthOrientation(DYN/"finals2000A.all"))
        self.precise = PreciseProducts([path], [], self.origin, self.epoch.eop)
        self.raw = read_sp3(path)
        if self.raw.frame != "IGc20":
            raise ValueError("Unexpected reference frame")

    def sample(self, sat, t):
        s = self.raw.samples.get((self.origin+int(round(float(t)*1e9)), sat))
        return s if s and s.xyz_m is not None and not s.maneuver and not s.orbit_predicted else None
