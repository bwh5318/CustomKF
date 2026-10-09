"""The single data store: one index over every input the fork may use.

    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.store --rebuild
    python -m customkf.guard --profile usage75 --timeout 300 -- Opus_Fork.store --verify

Rationale for indexing instead of moving. Astra's `data/` and `claude/data/` trees are
referenced by path inside frozen scientific manifests, and `claude/tools/dated_fixture.py`
hashes source trees for exact parity. Relocating a single byte would invalidate those
pins and every archived campaign that resolves against them. So the store is one
manifest, `datastore/index.json`, that records role, date, SHA-256 and the actual
location of every input, wherever it physically lives:

  inherited  - already on disk under data/ or claude/data/; indexed in place, read-only.
  acquired   - anything this fork downloads, written under datastore/<YYYYDOY>/ or
               datastore/static/ or datastore/reference/.

Every new acquisition lands in the store and nowhere else, so there is exactly one place
to look for an input and exactly one hash of record for it. `--verify` re-hashes
everything and reports drift; it never rewrites a hash to make a check pass.
"""
import argparse
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path

from customkf.prepare_stage2 import sha

from .paths import ASTRA_CLAUDE_DATA, ASTRA_DATA, ROOT, SP3_CACHE, STAGE0, STAGE2, STAGE3, STORE

INDEX = STORE/"index.json"
GPS_START = datetime(1980, 1, 6)

# Filename patterns -> (role, whether the name carries a YYYYDDD date stamp).
ROLES = (
    ("_01D_30S_MO.", "station_obs", True),
    ("_01D_MN.", "broadcast_nav", True),
    # Order matters: classify() takes the first match, so the clock pattern must precede
    # OPSRAP_, or IGS0OPSRAP_..._05M_CLK.CLK.gz is filed as a rapid *orbit*.
    ("_01D_05M_CLK.", "reference_igs_clock", True),
    ("OPSFIN_", "reference_igs_final", True),
    ("OPSRAP_", "reference_igs_rapid", True),
    ("nga_pred", "reference_nga_predicted", False),   # predicted, never a comparison candidate
    ("_apc.sp3", "reference_nga_apc", True),          # antenna phase centre; contract forbids COM use
    ("nga", "reference_nga_pe", True),
    (".atx", "static_antenna", False),
    (".ssc", "static_coordinates", False),
    (".snx", "static_coordinates", False),
    (".BLQ", "static_ocean_loading", False),
    (".gfc", "static_gravity", False),
    (".bsp", "static_ephemeris", False),
    ("finals2000A", "static_eop", False),
)


def classify(path):
    for token, role, dated in ROLES:
        if token in path.name:
            return role, dated
    return None, False


def stamp_to_date(name):
    """Date from either the IGS long filename (YYYYDDD) or NGA's GPS week/day (WWWWD)."""
    if name.startswith("nga") and name.endswith(".sp3"):
        stem = name[3:-4]
        # nga<week><dow>.sp3; an "_apc" suffix marks the antenna-phase-centre variant, which
        # the comparison contract forbids treating as centre of mass.
        digits = stem.split("_")[0]
        if digits.isdigit() and len(digits) == 5:
            return (GPS_START+timedelta(days=int(digits[:4])*7+int(digits[4]))).strftime("%Y-%m-%d")
        return None
    for i in range(len(name)-6):
        chunk = name[i:i+7]
        if chunk.isdigit() and 1980 <= int(chunk[:4]) <= 2100 and 1 <= int(chunk[4:]) <= 366:
            return (datetime(int(chunk[:4]), 1, 1)+timedelta(days=int(chunk[4:])-1)).strftime("%Y-%m-%d")
    return None


def load():
    if not INDEX.exists():
        raise FileNotFoundError("Build the store first: Opus_Fork.store --rebuild")
    return json.loads(INDEX.read_text())


def resolve(path_text):
    return Path(path_text) if Path(path_text).is_absolute() else ROOT/path_text


# Where a product is preferred from when several copies exist. Repository copies come first
# because Astra's manifests pin them; the external autocomparesp3 cache is the fallback.
REFERENCE_PRECEDENCE = ("data/stage0", "data/stage3", "Opus_Fork/datastore")


def _content_sha(path):
    """SHA-256 of the product content, decompressed when the file is gzip (a .gz and a plain copy of one product)."""
    data = Path(path).read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return hashlib.sha256(data).hexdigest()


def _reference_rank(entry):
    relative = str(entry["path"]).replace("\\", "/")
    for i, prefix in enumerate(REFERENCE_PRECEDENCE):
        if relative.startswith(prefix):
            return i
    return len(REFERENCE_PRECEDENCE)


def find(role, date=None, index=None):
    """The one input of this role for this date, with its recorded hash re-checked.

    Several copies of the same product exist: IGS final for 2026-08-02 sits both in
    `data/stage0` and in the external SP3 cache it was copied from. Identical content is
    resolved by declared precedence, because choosing between byte-identical files is not a
    scientific decision. Genuinely different files sharing a role and date are an error, so a
    campaign can never silently score against a product it did not mean to use.
    """
    index = index or load()
    hits = [e for e in index["entries"].values()
            if e["role"] == role and (date is None or e["date"] == date)]
    if not hits:
        raise KeyError(f"No {role} in the store for {date}")
    if len({h["sha256"] for h in hits}) > 1:
        # Different file bytes can still be one product: a gzip copy and its plain original (30 Sep 2026: the
        # untouched-date IGS finals were downloaded as .gz while the external cache holds plain .SP3). Compare the
        # decompressed content of every copy, each re-checked against its recorded file hash; refuse if it differs.
        for h in hits:
            if sha(resolve(h["path"])) != h["sha256"]:
                raise ValueError("Store entry changed on disk since it was indexed: "+h["path"])
        if len({_content_sha(resolve(h["path"])) for h in hits}) > 1:
            raise KeyError(f"{len(hits)} DIFFERENT files for {role} on {date}: " +
                           ", ".join(f"{h['path']} ({h['sha256'][:12]})" for h in hits))
    hits.sort(key=_reference_rank)
    entry = hits[0]
    path = resolve(entry["path"])
    if sha(path) != entry["sha256"]:
        raise ValueError("Store entry changed on disk since it was indexed: "+entry["path"])
    return path, entry


def pinned_hashes():
    """Every SHA-256 Astra's manifests already record, so the store can cite theirs."""
    found = {}
    for manifest in list(ASTRA_DATA.rglob("*manifest.json"))+list(ASTRA_CLAUDE_DATA.rglob("*manifest.json")):
        try:
            content = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for entry in content.get("files", []):
            if isinstance(entry, dict) and "path" in entry and "sha256" in entry:
                found[entry["path"]] = (entry["sha256"], manifest.relative_to(ROOT).as_posix())
    return found


def scan():
    """Index inherited inputs in place and anything already inside the store."""
    pins = pinned_hashes()
    entries, skipped = {}, []
    # The external SP3 cache is large and mostly individual analysis-centre finals we do not
    # use; only the two comparison products are indexed from it.
    wanted_from_cache = ("IGS0OPSFIN_", "nga")
    roots = [(STAGE0, "inherited"), (STAGE2, "inherited"), (STAGE3, "inherited"),
             (ASTRA_CLAUDE_DATA, "inherited"), (SP3_CACHE, "external_read_only"), (STORE, "acquired")]
    for root, origin in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix == ".json" and path.name != "inputs.json":
                continue
            if path.name in ("index.json",) or INDEX in path.parents:
                continue
            if origin == "external_read_only" and not path.name.startswith(wanted_from_cache):
                continue
            role, dated = classify(path)
            if role is None:
                skipped.append(str(path))
                continue
            relative = path.relative_to(ROOT).as_posix() if root != SP3_CACHE else str(path)
            digest = sha(path)
            pin = pins.get(relative)
            if pin and pin[0] != digest:
                raise ValueError("Inherited file no longer matches its pinned hash: "+relative)
            # Keyed by path, not by basename: the same basename can be two genuinely
            # different files (PIMO day 214 differs between claude/data/day214 and
            # claude/data/acquired), and collapsing them hid the copy an archived fixture
            # actually read. The index records what exists; consumers apply precedence.
            key = relative
            entries[key] = dict(role=role, date=stamp_to_date(path.name) if dated else None,
                                name=path.name, path=relative, sha256=digest,
                                bytes=path.stat().st_size, origin=origin,
                                pinned_by=pin[1] if pin else None)
    return entries, skipped


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    STORE.mkdir(parents=True, exist_ok=True)

    if args.verify and INDEX.exists():
        old = json.loads(INDEX.read_text())
        drift, missing = [], []
        for key, entry in old["entries"].items():
            # External cache entries are recorded as absolute paths; repository ones relative.
            path = Path(entry["path"]) if Path(entry["path"]).is_absolute() else ROOT/entry["path"]
            if not path.is_file():
                missing.append(entry["path"])
            elif sha(path) != entry["sha256"]:
                drift.append(entry["path"])
        report = dict(status="store_verified" if not drift and not missing else "store_drifted",
                      checked=len(old["entries"]), drifted=drift, missing=missing)
        (out/"verify.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report, indent=2))
        if drift or missing:
            raise SystemExit("Store drift; the index is not rewritten to hide it")
        return

    entries, skipped = scan()
    by_role, by_date = {}, {}
    for entry in entries.values():
        by_role[entry["role"]] = by_role.get(entry["role"], 0)+1
        if entry["date"]:
            by_date.setdefault(entry["date"], []).append(entry["role"])
    index = dict(
        status="single_consolidated_input_index",
        note="Inherited files are indexed where they already live: Astra's manifests pin those "
             "paths and moving one would break archived campaign parity. Everything this fork "
             "acquires is written under Opus_Fork/datastore/ and nowhere else.",
        built_utc=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        totals=dict(entries=len(entries), bytes=sum(e["bytes"] for e in entries.values()),
                    by_role=dict(sorted(by_role.items()))),
        dates={d: dict(sorted({r: sorted(rs).count(r) for r in rs}.items())) for d, rs in sorted(by_date.items())},
        unclassified=skipped, entries=dict(sorted(entries.items())))
    INDEX.write_text(json.dumps(index, indent=2)+"\n")
    (out/"index.json").write_text(json.dumps(index, indent=2)+"\n")
    print(f"{len(entries)} inputs, {sum(e['bytes'] for e in entries.values())/2**30:.2f} GiB")
    for role, count in sorted(by_role.items()):
        print(f"  {role:24s} {count:4d}")
    print("\nper date:")
    for date, counted in sorted(index["dates"].items()):
        print(f"  {date}  " + ", ".join(f"{r} x{n}" for r, n in sorted(counted.items())))
    if skipped:
        print(f"\n{len(skipped)} unclassified files (not inputs, or a role to add):")
        for path in skipped[:15]:
            print("  "+path)
    print("\nWrote "+str(INDEX))


if __name__ == "__main__":
    main()
