# The data store

One place to look for any input this fork uses, and one hash of record for each.
Built and checked by `Opus_Fork/store.py`; the manifest is `index.json`.

```bash
C:\anaconda\python.exe -m customkf.guard --profile usage75 --timeout 180 -- Opus_Fork.store --rebuild
C:\anaconda\python.exe -m customkf.guard --profile usage75 --timeout 180 -- Opus_Fork.store --verify
```

## Why inherited files are indexed in place rather than moved

The obvious reading of "one big data store" is to move everything into it. That would
break the project. Astra's frozen scientific manifests record inputs **by path**, and
`claude/tools/dated_fixture.py:sources()` hashes whole source trees so that archived
campaigns can be reproduced bit for bit. Moving one byte under `data/` or `claude/data/`
would invalidate those pins and every campaign that resolves against them, and
`CONTINUE_HERE.md` lists exactly that as a trap.

So the store is a **manifest, not a relocation**:

- `inherited` — already on disk under `data/` or `claude/data/`. Indexed where it lives,
  read-only, and cross-checked against whichever of Astra's manifests already pins it.
  A mismatch is an error, never a silent re-pin.
- `acquired` — anything this fork downloads. Written here and nowhere else, so new data
  stops accumulating in per-experiment folders.

The effect the request was after — one index, one hash per input, no hunting through
`data/stage3` vs `claude/data/day214` vs `claude/data/stage3-mirror` — is delivered by
`index.json`. The effect that would have broken reproducibility is not attempted.

## Layout for newly acquired data

```
datastore/
  index.json          the manifest: role, date, sha256, bytes, path, origin, pinned_by
  <YYYYDOY>/          per-date inputs: station OBS, broadcast NAV     e.g. 2026214/
  reference/          evaluation references: IGS final, IGS rapid, NGA PE
  static/             ANTEX, SINEX coordinates, BLQ, gravity, DE440, EOP, code biases
```

`<YYYYDOY>` is the observation day, so 2026-08-02 is `2026214`. Each acquired file keeps
a sidecar record with source URL, retrieval time, SHA-256 and decoded byte count, the
same convention `claude/roadmap/fetch_day.py` already uses.

## Roles

| Role | Meaning |
|---|---|
| `station_obs` | Daily 30 s RINEX observation file. Estimation input. |
| `broadcast_nav` | Daily BRDC mixed navigation. Seeds and nominal clocks. Estimation input. |
| `reference_igs_final` | IGS final SP3. **Evaluation only.** The reference the objective names. |
| `reference_igs_rapid` | IGS rapid SP3. **Evaluation only.** |
| `reference_igs_clock` | IGS rapid clock. **Evaluation only.** |
| `reference_nga_pe` | NGA precise ephemeris. **Evaluation only.** The product to beat. |
| `static_*` | ANTEX, coordinates, ocean loading, gravity, planetary ephemeris, EOP. |

Estimation must never read a `reference_*` entry. `customkf/stage5_pilot.py`
`forbid_precise_product_reads` is installed on fitting paths and enforces that at runtime.

## What the first build found

210 inputs, 1.67 GiB, across 10 dates.

| Role | Count |
|---|---:|
| `station_obs` | 178 |
| `reference_igs_rapid` | 12 |
| `broadcast_nav` | 8 |
| `static_coordinates` | 3 |
| `reference_igs_final` | **2** |
| `reference_nga_pe` | **2** |
| other static | 5 |

Two coverage facts that shape the plan:

- **IGS final and NGA PE exist for only two days each**, 2026-08-02 and 2026-03-04. Both
  are needed for every head-to-head, so a multi-day claim requires acquiring both products
  per test day.
- **The 25-station network has observations for 2026-08-02 only.** The 11 added markers
  exist for no other date. Every cross-date 25-station arm needs new acquisition.

Dates currently held: 2026-03-04, 07-31, and 08-01 through 08-08. Of those, **08-07 and
08-08 hold broadcast navigation only** and are reserved for Astra's unexposed cross-date
comparison; this fork does not use them.
