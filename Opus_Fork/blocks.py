"""PRN -> GPS block mapping from the pinned ANTEX validity intervals.

Own implementation so the fork does not depend on another tree's helper; the
ANTEX file itself is read-only and shared.
"""
from datetime import datetime
from .paths import STAGE3

GROUPS = {"BLOCK IIF": "IIF", "BLOCK IIIA": "IIIA", "BLOCK IIR-M": "IIR-M",
          "BLOCK IIR-A": "IIR", "BLOCK IIR-B": "IIR"}


def satellite_blocks(day, path=None):
    """{PRN: (ANTEX type, SVN)} valid at 00:00 of `day` (YYYY-MM-DD), GPS only."""
    when = datetime.strptime(day, "%Y-%m-%d")
    found, current = {}, None
    with open(path or STAGE3/"igs20.atx") as stream:
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
                current[label] = datetime(*map(int, f[:5]))
            elif label == "END OF ANTENNA":
                prn = current.get("prn", "")
                if len(prn) == 3 and prn.startswith("G"):
                    if current.get("VALID FROM", datetime.min) <= when < current.get("VALID UNTIL", datetime.max):
                        if prn in found:
                            raise ValueError("Ambiguous ANTEX PRN mapping: "+prn)
                        found[prn] = (current["type"], current["svn"])
                current = None
    return found


def group(block_type):
    if block_type not in GROUPS:
        raise ValueError("Undeclared block type: "+block_type)
    return GROUPS[block_type]
