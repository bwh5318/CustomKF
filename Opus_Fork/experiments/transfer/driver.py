"""Serial driver for the transfer calculation. Run DIRECTLY (never inside a guard); it launches one root-guarded
worker at a time and never nests guards:

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.transfer.driver [--max-steps N]

Steps: `tides` → `chunk` × 12 (12 epochs each, each restoring the previous chunk's accumulator) → `solve`.
Each worker: `python -m customkf.guard --profile usage75 --timeout 300 -- MODULE ARGS` (the unchanged usage75 policy).
Resumable: `driver_status.json` in this folder records every completed step's guard run folder; a restart skips them.
Retries only on a guard refusal (another guarded job holds the mutex, machine already at the usage ceiling,
insufficient memory headroom: wait 45 s) or an external-load stop (wait 60 s, at most 4 per step). A timeout or
worker failure stops the driver. Limits are never raised.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from Opus_Fork.paths import ROOT

HERE = Path(__file__).resolve().parent
STATUS = HERE/"driver_status.json"
REFUSALS = ("Another customKF guarded experiment is running", "Machine already at usage ceiling",
            "Insufficient memory headroom")
CHUNK = 12
EPOCHS = 144


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_status():
    if STATUS.exists():
        return json.loads(STATUS.read_text())
    return dict(created_utc=now(), steps={}, launches=[])


def save(status):
    STATUS.write_text(json.dumps(status, indent=1)+"\n")


def done(status, name, expect):
    entry = status["steps"].get(name)
    if not entry:
        return None
    folder = Path(entry["folder"])
    step = folder/"step.json"
    if step.exists() and json.loads(step.read_text()).get("status") == expect:
        return folder
    return None


def launch(status, name, module, args, expect):
    cmd = [sys.executable, "-m", "customkf.guard", "--profile", "usage75", "--timeout", "300", "--", module, *args]
    refusals = stops = 0
    while True:
        start = time.monotonic()
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        text = p.stdout+p.stderr
        m = re.search(r"^Logs: (.+)$", p.stdout, re.M)
        folder = Path(m.group(1).strip()) if m else None
        result = json.loads((folder/"result.json").read_text()) if folder and (folder/"result.json").exists() else {}
        record = dict(step=name, utc=now(), returncode=p.returncode, folder=str(folder) if folder else None,
                      guard_status=result.get("status"), elapsed_s=result.get("elapsed_s", time.monotonic()-start),
                      cpu_seconds=result.get("cpu_seconds"), peak_private_mib=result.get("peak_sampled_private_commit_mib"),
                      peak_usage=result.get("system_usage", {}).get("peak"))
        status["launches"].append(record)
        save(status)
        if p.returncode == 0 and folder and (folder/"step.json").exists() and \
                json.loads((folder/"step.json").read_text()).get("status") == expect:
            status["steps"][name] = dict(folder=str(folder), elapsed_s=record["elapsed_s"], utc=record["utc"])
            save(status)
            print(f"{now()} {name}: ok in {record['elapsed_s']:.0f} s -> {folder}", flush=True)
            return folder
        if p.returncode == 126 and any(r in text for r in REFUSALS):
            refusals += 1
            if refusals > 80:
                raise SystemExit(f"{name}: guard refused {refusals} times; giving up")
            print(f"{now()} {name}: guard refused ({[r for r in REFUSALS if r in text][0]}); waiting 45 s", flush=True)
            time.sleep(45)
            continue
        if result.get("status") not in (None, "ok", "worker_failed", "orphan_children", "timeout", "setup_failed") \
                and p.returncode == 125:
            stops += 1
            if stops > 4:
                raise SystemExit(f"{name}: stopped {stops} times by external load; giving up")
            print(f"{now()} {name}: stopped ({result.get('status')}); waiting 60 s", flush=True)
            time.sleep(60)
            continue
        print(text[-6000:], flush=True)
        raise SystemExit(f"{name}: failed (returncode {p.returncode}, guard status {result.get('status')}); see {folder}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-steps", type=int, default=10**6)
    args = parser.parse_args()
    status = load_status()
    budget = args.max_steps
    base = "Opus_Fork.experiments.transfer."
    tides = done(status, "tides", "tides_ready")
    if tides is None:
        if budget <= 0:
            return
        tides = launch(status, "tides", base+"tides", [], "tides_ready")
        budget -= 1
    previous = None
    for start in range(0, EPOCHS, CHUNK):
        stop = min(start+CHUNK, EPOCHS)
        name = f"chunk-{start:03d}-{stop:03d}"
        folder = done(status, name, "transfer_chunk_complete")
        if folder is None:
            if budget <= 0:
                return
            extra = ["--previous", str(previous)] if previous is not None else []
            folder = launch(status, name, base+"chunk", ["--start", str(start), "--stop", str(stop), "--tides", str(tides), *extra],
                            "transfer_chunk_complete")
            budget -= 1
        previous = folder
    solved = done(status, "solve", "transfer_solved")
    if solved is None:
        if budget <= 0:
            return
        solved = launch(status, "solve", base+"solve", ["--last", str(previous)], "transfer_solved")
    (HERE/"transfer_result.json").write_text((solved/"transfer.json").read_text())
    status["finished_utc"] = now()
    save(status)
    print(f"{now()} finished; result copied to {HERE/'transfer_result.json'}", flush=True)


if __name__ == "__main__":
    main()
