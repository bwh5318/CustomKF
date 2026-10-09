"""Direct serial controller: acquire bench days (roadmap step 4). No nested guards.

    C:\\anaconda\\python.exe -m claude.roadmap.run_fetch --days 2026-08-04,2026-08-05,2026-08-06

For each day: BRDC and IGS rapid SP3 (products absent from data/stage3), the frozen 14 network stations
(header-first, pinned RNXCMP), then claude/data/day<DOY>/inputs.json. Each download is its own guarded
worker (120 s). Cached artifacts are hash-verified. Refuses to start if any other Python process exists.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import psutil
from customkf.guard import Limits, run
from customkf.prepare_stage2 import ROOT
from customkf.prepare_stage3 import DATA
from claude.roadmap.long_prepare import STATIONS
from claude.roadmap.common import write_json


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run directly"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", required=True)
    parser.add_argument("--markers", default=",".join(STATIONS.values()))
    args = parser.parse_args()
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["pid"] != os.getpid() and "python" in (p.info["name"] or "").lower():
            raise RuntimeError("Another Python process exists: "+str(p.info["pid"]))
    folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-fetch")
    folder.mkdir(parents=True)
    report = dict(status="running", days=args.days.split(","), runs={})

    def save():
        write_json(folder/"campaign.json", report)

    def worker(name, module_args, timeout=120):
        print("Starting", name, flush=True)
        result, path = run(module_args, Limits(timeout_s=timeout))
        shutil.move(str(path), str(folder/name))
        report["runs"][name] = result
        save()
        print(name, result["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Stopped at "+name)

    try:
        for day in report["days"]:
            stamp = datetime.strptime(day, "%Y-%m-%d").strftime("%Y%j")
            for kind, name in (("brdc", f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"), ("sp3", f"IGS0OPSRAP_{stamp}0000_01D_15M_ORB.SP3.gz")):
                if not (DATA/name).exists():
                    worker(f"{stamp}-{kind}", ["claude.roadmap.fetch_day", "product", "--day", day, "--kind", kind])
            for marker in args.markers.split(","):
                if not (DATA/f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz").exists():
                    worker(f"{stamp}-{marker}", ["claude.roadmap.fetch_day", "station", "--day", day, "--marker", marker])
            worker(f"{stamp}-manifest", ["claude.roadmap.bench_data", "manifest", "--day", day, "--markers", args.markers])
        report["status"] = "acquisition_complete_not_fixture_acceptance"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
