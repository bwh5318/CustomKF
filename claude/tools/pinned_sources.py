"""Documented source-drift policy for Claude support workers pinned to the GUAM baseline.

validation/guam/20260911T155927Z pins 93 customkf/tests/scoring sources. While starting its
arc-length experiment on 11 Sep 2026, Astra (out of tokens mid-task) changed only the prepare()
validation in customkf/stage5_pilot.py, adding a "nominal-cadence" profile, and added
tests/test_arc_profile.py. The user judged such a change inconsequential and asked Claude to go
ahead. No pinned hash is rewritten: verify() accepts either no drift or exactly that diff,
checked line by line against the pinned GUAM source snapshot, and returns a record to archive.
"""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUAM = ROOT / "validation/guam/20260911T155927Z"
DYNAMICS = ROOT / "claude/runs/20260911T211901Z-dynamics-ceiling"
DRIFTED = "customkf/stage5_pilot.py"
ACCEPTED_CHANGES = [
    ("replace",
     ['    if profile not in ("legacy","nominal-multihour"):raise ValueError("Unknown fixture profile")'],
     ['    if profile not in ("legacy","nominal-multihour","nominal-cadence"):raise ValueError("Unknown fixture profile")']),
    ("insert", [],
     ['    if profile=="nominal-cadence" and (step_s!=600 or epoch_count not in (19,37)):',
      '        raise ValueError("Cadence experiment allows only 19 or 37 ten-minute epochs")']),
]
ALLOWED_NEW_FILES = ("tests/test_arc_profile.py",)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    return Path(path).read_bytes().decode("utf-8").splitlines()


def verify(helpers=()):
    """Raise unless the tree matches the GUAM pins up to the accepted diff; return the record to archive."""
    manifest = json.loads((GUAM / "validation.json").read_text())
    pins = manifest["source_sha256"]
    mismatched = sorted(name for name, digest in pins.items() if not (ROOT / name).exists() or sha(ROOT / name) != digest)
    if mismatched not in ([], [DRIFTED]):
        raise ValueError("Unaccepted source drift: " + ", ".join(mismatched))
    record = {"policy": "GUAM source pins, except the documented prepare()-only nominal-cadence diff in "
                        "customkf/stage5_pilot.py; no pinned hash rewritten",
              "guam_manifest_sha256": sha(GUAM / "validation.json"), "pinned_sources": len(pins), "drift": {}}
    if mismatched:
        snapshot = GUAM / "source" / DRIFTED
        if not sha(snapshot) == pins[DRIFTED] == manifest["artifacts_sha256"]["source/" + DRIFTED]:
            raise ValueError("Pinned GUAM snapshot does not match its manifest")
        old, new = lines(snapshot), lines(ROOT / DRIFTED)
        changes = [(tag, old[i1:i2], new[j1:j2]) for tag, i1, i2, j1, j2 in
                   difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if tag != "equal"]
        if changes != [(tag, list(a), list(b)) for tag, a, b in ACCEPTED_CHANGES]:
            raise ValueError(DRIFTED + " differs from the pinned GUAM snapshot beyond the accepted diff")
        record["drift"][DRIFTED] = {"pinned_sha256": pins[DRIFTED], "current_sha256": sha(ROOT / DRIFTED),
                                    "accepted_changes": [list(change) for change in ACCEPTED_CHANGES]}
    tracked = {p.relative_to(ROOT).as_posix() for folder in ("customkf", "tests") for p in (ROOT / folder).glob("*.py")}
    extra = sorted(tracked - set(pins))
    if not set(extra) <= set(ALLOWED_NEW_FILES):
        raise ValueError("Unaccepted new source files: " + ", ".join(extra))
    record["new_files_sha256"] = {name: sha(ROOT / name) for name in extra}
    for name, digest in manifest["report_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Report file changed: " + name)
    pinned_helpers = json.loads((DYNAMICS / "validation.json").read_text())["source_sha256"]
    for name in helpers:
        if sha(ROOT / name) != pinned_helpers[name]:
            raise ValueError("Helper changed since the fixed-force campaign: " + name)
    record["helpers_sha256"] = {name: pinned_helpers[name] for name in helpers}
    return record
