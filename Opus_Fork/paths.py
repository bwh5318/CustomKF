"""Filesystem layout for the fork. One consolidated data store, plus read-only pins.

The existing `data/` and `claude/data/` trees stay exactly where they are: every
Astra manifest and source-map pin resolves against those paths, and moving a byte
would break `dated_fixture.sources()` parity and every scientific manifest. The
consolidated store therefore *indexes* them by hash instead of relocating them.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORK = ROOT/"Opus_Fork"
STORE = FORK/"datastore"
RUNS = FORK/"runs"
RESULTS = FORK/"results"

# Read-only inherited inputs (Astra's pinned trees).
ASTRA_DATA = ROOT/"data"
ASTRA_CLAUDE_DATA = ROOT/"claude/data"
STAGE0 = ASTRA_DATA/"stage0"
STAGE2 = ASTRA_DATA/"stage2"
STAGE3 = ASTRA_DATA/"stage3"

# The historical autocomparesp3 project's SP3 cache, outside this repository and treated as
# strictly read-only (README.md: "remains a read-only comparison reference"). It holds IGS
# final and NGA precise ephemerides for 359 common days, 2025-01-15 to 2026-08-08, which is
# every reference product a multi-day head-to-head needs. Indexed in place, never copied or
# modified; `Opus_Fork.store --verify` fails loudly if anything there changes under us.
SP3_CACHE = ROOT.parent/"autocomparesp3"/"data"/"sp3_cache"


def store_day(doy, year=2026):
    """Per-date folder inside the single store: datastore/<year><doy>/."""
    return STORE/f"{int(year)}{int(doy):03d}"


def reference_dir():
    """Evaluation references (IGS final/rapid, NGA) live in one place, never mixed
    into the estimator's input folders."""
    return STORE/"reference"
