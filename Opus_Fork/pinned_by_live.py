"""List every file pinned by a campaign that is currently running. Check before editing.

    python -m Opus_Fork.pinned_by_live [--all] [PATH ...]

Needs no guard: it reads JSON and hashes files, starts nothing and writes nothing.

**Why this exists.** On 21 September 2026 a correction added to
`Opus_Fork/results/ARC_CENSUS.md` aborted Astra's live `native_gap_fit` campaign after 24
workers and 1,542 guarded seconds. Her controller pins eight files in `Opus_Fork/` as evidence
inputs and re-verifies every pin before each worker, so editing one of my own documents broke
her run. That was the second time I interrupted a campaign of hers; the first was starting a
guarded job in the mutex gap between her workers, now prevented in `Opus_Fork/guard.py`.

A file in this fork can be immutable evidence for someone else's live campaign. Nothing in the
filesystem says so, so this reports it:

- every campaign under `claude/runs/` or `Opus_Fork/runs/` whose `validation.json` status is
  `running`, together with the paths it pins;
- whether each pinned file currently matches its recorded hash, so an already-broken pin is
  visible before a resume is attempted;
- with paths given as arguments, whether editing those specific files is safe right now.

A campaign between workers still counts as live. Absence of a running campaign is not
permission to edit a pinned artifact either: a stopped campaign may be resumed and will
re-verify.
"""
import argparse
import json
from pathlib import Path
import sys

from customkf.prepare_stage2 import ROOT, sha


def campaigns(include_all=False):
    for folder in sorted(list((ROOT/"claude/runs").glob("*")) +
                         list((ROOT/"Opus_Fork/runs").glob("*"))):
        manifest = folder/"validation.json"
        if not manifest.is_file():
            continue
        try:
            report = json.loads(manifest.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        status = report.get("status")
        if include_all or status == "running":
            pins = report.get("source_sha256") or {}
            if pins:
                yield folder, status, pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files you intend to edit")
    parser.add_argument("--all", action="store_true",
                        help="include stopped campaigns, which may still be resumed")
    args = parser.parse_args()

    wanted = {Path(p).as_posix().replace("\\", "/") for p in args.paths}
    live, unsafe = 0, []
    for folder, status, pins in campaigns(args.all):
        live += 1
        mine = sorted(p for p in pins if p.startswith("Opus_Fork/"))
        broken = [p for p, h in pins.items() if not (ROOT/p).is_file() or sha(ROOT/p) != h]
        print(f"\n{folder.relative_to(ROOT).as_posix()}  [{status}]")
        print(f"  {len(pins)} pinned paths, {len(mine)} of them under Opus_Fork/")
        for p in mine:
            state = "BROKEN" if p in broken else "ok"
            print(f"    {state:6s} {p}")
        if broken:
            print(f"  {len(broken)} pin(s) do not match; a resume will refuse until restored:")
            for p in broken[:10]:
                print(f"    BROKEN {p}")
        for p in wanted:
            if p in pins:
                unsafe.append((p, folder.relative_to(ROOT).as_posix(), status))

    if not live:
        print("No campaign with recorded pins is running." if not args.all
              else "No campaign with recorded pins found.")
    if wanted:
        print()
        for p in sorted(wanted):
            hits = [(f, s) for q, f, s in unsafe if q == p]
            if hits:
                print(f"DO NOT EDIT  {p}  — pinned by {', '.join(f'{f} [{s}]' for f, s in hits)}")
            else:
                print(f"safe to edit {p}  (no running campaign pins it)")
    return 1 if unsafe else 0


if __name__ == "__main__":
    sys.exit(main())
