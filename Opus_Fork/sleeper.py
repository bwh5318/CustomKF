"""Occupy the guard for a fixed time, to test mutual exclusion. Does nothing else."""
import os, sys, time
from pathlib import Path

def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20.
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    print(f"holding the guard for {seconds} s", flush=True)
    time.sleep(seconds)
    (out/"sleeper.json").write_text('{"held_s": %r}\n' % seconds)
    print("done", flush=True)

if __name__ == "__main__":
    main()
