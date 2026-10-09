"""Tiny worker for tests/test_guard_lease_integration.py: mark START, wait (max 60 s) for RELEASE, exit 0. No numerics.

    python -m tests.lease_guard_worker START_FILE RELEASE_FILE
"""
from pathlib import Path
import sys
import time

start, release = Path(sys.argv[1]), Path(sys.argv[2])
start.write_text("started")
end = time.monotonic()+60
while not release.exists() and time.monotonic() < end:
    time.sleep(0.05)
print("released" if release.exists() else "timed out", flush=True)
