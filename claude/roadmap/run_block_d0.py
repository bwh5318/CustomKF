"""Direct serial controller for roadmap step 1 (claude/roadmap/BLOCK_D0_PROTOCOL.md).

    C:\\anaconda\\python.exe -m claude.roadmap.run_block_d0

Fresh campaign only; no resume flag. Each numerical stage is its own customkf.guard worker with the
unchanged default limits. Refuses to start if any other Python process exists.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import psutil
from customkf.guard import Limits, run
from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.common import sources, write_json

PROTOCOL = "claude/roadmap/BLOCK_D0_PROTOCOL.md"
DAYS = {
    "2026-08-03": dict(fixture="claude/runs/20260912T193417Z-day215-pod/prepare/fixture.json"),
    "2026-08-02": dict(fixture="runs/20260912T161029Z-0ddb71b3/fixture.json"),
}
PARITY_ARCHIVE = "claude/runs/20260912T193417Z-day215-pod/fixed-linear-2"
CALIBRATION_DAY = "2026-08-01"


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run the controller directly, never inside a guard"
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["pid"] != os.getpid() and "python" in (p.info["name"] or "").lower():
            raise RuntimeError("Another Python process exists; inspect before running: "+str(p.info["pid"]))
    for day, spec in DAYS.items():
        meta = json.loads((ROOT/spec["fixture"]).parent.joinpath("step.json").read_text())
        assert meta["status"] == "prepared" and meta["day"] == day and sha(ROOT/spec["fixture"]) == meta["fixture_sha256"]
        spec["fixture_sha256"] = meta["fixture_sha256"]
    satellites = sorted(json.loads((ROOT/DAYS["2026-08-02"]["fixture"]).read_text())["seeds"])
    assert len(satellites) == 31
    folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-block-d0")
    folder.mkdir(parents=True)
    pins = sources(extra=[PROTOCOL])
    for name in pins:
        target = folder/"source"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    report = dict(status="running", controller_pid=os.getpid(), protocol=PROTOCOL, active_worker=None,
                  source_sha256=pins, calibration=None, runs={},
                  days={d: dict(fixture=s["fixture"], fixture_sha256=s["fixture_sha256"], finals={}, accepted_trials={}) for d, s in DAYS.items()})

    def save():
        write_json(folder/"pending.json", report)
        (folder/"pending.json").replace(folder/"validation.json")

    def worker(name, args, timeout=300):
        for path, digest in report["source_sha256"].items():
            assert sha(ROOT/path) == digest, "Source changed during campaign: "+path
        report["active_worker"] = dict(name=name, args=args)
        save()
        print("Starting "+name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        assert path.resolve().is_relative_to(ROOT/"runs")
        shutil.move(str(path), str(folder/name))
        report["runs"][name] = result
        report["active_worker"] = None
        save()
        print(name, result["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Stopped at "+name)
        return folder/name

    print("Campaign "+str(folder), flush=True)
    save()
    try:
        worker("parity", ["claude.roadmap.block_iteration", "parity", "--fixture", str(ROOT/DAYS["2026-08-03"]["fixture"]),
                          "--archive", str(ROOT/PARITY_ARCHIVE)])
        half = len(satellites)//2
        fits = [worker(f"calibration-fit-{i}", ["claude.roadmap.block_calibrate", "fit", "--day", CALIBRATION_DAY,
                                                 "--satellites", ",".join(group)])
                for i, group in enumerate((satellites[:half], satellites[half:]))]
        combined = worker("calibration", ["claude.roadmap.block_calibrate", "combine", "--day", CALIBRATION_DAY,
                                          "--inputs", *map(str, fits)])
        calibration = combined/"calibration.json"
        report["calibration"] = dict(path=calibration.relative_to(folder).as_posix(), sha256=sha(calibration))
        save()
        for variant, label in (("block-fixed", "B"), ("block-prior", "C")):
            for day, spec in DAYS.items():
                common = ["--fixture", str(ROOT/spec["fixture"]), "--fixture-sha256", spec["fixture_sha256"], "--variant", variant,
                          "--calibration", str(calibration), "--calibration-sha256", report["calibration"]["sha256"]]
                tag = f"{label}-{day[-2:]}"
                previous, accepted_trials = None, []
                for i in range(4):
                    args = ["claude.roadmap.block_iteration", "linear", *common]
                    if previous:
                        args += ["--previous", str(previous)]
                    lin = worker(f"{tag}-linear-{i}", args)
                    if json.loads((lin/"step.json").read_text())["status"] == "converged":
                        report["days"][day]["finals"][label] = lin.name
                        save()
                        break
                    if i == 3:
                        raise RuntimeError("Stationarity not reached before the four-linearization cap: "+tag)
                    accepted = False
                    for ai, alpha in enumerate((1., .5, .25, .125)):
                        tri = worker(f"{tag}-trial-{i}-{ai}", ["claude.roadmap.block_iteration", "trial", *common,
                                                               "--linear", str(lin), "--alpha", str(alpha)])
                        if json.loads((tri/"step.json").read_text())["status"] == "iteration_complete":
                            previous = tri
                            accepted_trials.append(tri.name)
                            report["days"][day]["accepted_trials"][label] = accepted_trials
                            save()
                            accepted = True
                            break
                    if not accepted:
                        raise RuntimeError("Line search exhausted: "+tag)
        worker("evaluation", ["claude.roadmap.block_evaluate", str(folder)])
        report["status"] = "block_d0_campaign_complete_not_accuracy_acceptance"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        values = list(report["runs"].values())
        report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                      peak_job_memory_mib=max([v.get("windows_peak_job_memory_mib", 0) for v in values] or [0]),
                      minimum_system_available_gib=min([v.get("minimum_system_available_gib", float("inf")) for v in values] or [float("inf")]))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*")
                                      if p.is_file() and p.name not in ("validation.json", "pending.json")}
        save()


if __name__ == "__main__":
    main()
