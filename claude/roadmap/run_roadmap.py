"""Direct serial orchestrator for roadmap steps 2-3 (STREAMING_AND_ARCS_PROTOCOL.md).

    C:\\anaconda\\python.exe -m claude.roadmap.run_roadmap --stage step2
    C:\\anaconda\\python.exe -m claude.roadmap.run_roadmap --stage step3-prepare
    C:\\anaconda\\python.exe -m claude.roadmap.run_roadmap --stage step3-fits --step2 DIR
    C:\\anaconda\\python.exe -m claude.roadmap.run_roadmap --stage step3-eval --step3 DIR

Runs no numerics itself: every numerical stage is its own customkf.guard worker (default limits) or a
claude.roadmap.run_long controller child, strictly one at a time. Stops at the first failed gate/worker.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import psutil
from customkf.guard import Limits, run
from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.common import write_json

AUG3_PREP = "claude/runs/20260912T193417Z-day215-pod/prepare"
AUG3_D0 = "claude/runs/20260912T193417Z-day215-pod/d0-linear-3"
AUG2_DATED = "runs/20260912T161029Z-0ddb71b3"
BLOCK_CAMPAIGN = "claude/runs/20260913T015012Z-block-d0"
CONFIGS = "claude/roadmap/configs"
PROTOCOL = "claude/roadmap/STREAMING_AND_ARCS_PROTOCOL.md"


class Stage:
    def __init__(self, name):
        self.folder = ROOT/"claude/runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-roadmap-"+name)
        self.folder.mkdir(parents=True)
        self.report = dict(status="running", stage=name, orchestrator_pid=os.getpid(), protocol=PROTOCOL,
                           protocol_sha256=sha(ROOT/PROTOCOL), runs={}, campaigns={}, gates={})
        self.save()
        print("Stage folder", self.folder, flush=True)

    def save(self):
        write_json(self.folder/"pending.json", self.report)
        (self.folder/"pending.json").replace(self.folder/"stage.json")

    def guard(self, name, args, timeout=300):
        print("Starting", name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        shutil.move(str(path), str(self.folder/name))
        self.report["runs"][name] = result
        self.save()
        print(name, result["status"], round(result.get("elapsed_s", 0), 1), flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Stopped at "+name)
        return self.folder/name

    def long(self, label, fixture_dir, config, chunk_epochs, max_linearizations=4, trajectory_groups=0):
        env = dict(os.environ, CLAUDE_ROADMAP_ORCHESTRATOR_PID=str(os.getpid()))
        command = [sys.executable, "-u", "-m", "claude.roadmap.run_long", "--fixture", str(fixture_dir), "--config", str(ROOT/config),
                   "--label", label, "--chunk-epochs", str(chunk_epochs), "--max-linearizations", str(max_linearizations), "--protocol", PROTOCOL,
                   "--trajectory-groups", str(trajectory_groups)]
        print("Starting long fit", label, "chunk", chunk_epochs, flush=True)
        campaign = None
        with subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as child:
            for line in child.stdout:
                print("  ["+label+"]", line.rstrip(), flush=True)
                if line.startswith("Campaign "):
                    campaign = Path(line.split(" ", 1)[1].strip())
            code = child.wait()
        self.report["campaigns"][label] = dict(folder=str(campaign), exit_code=code)
        self.save()
        if code or campaign is None:
            raise RuntimeError("Long fit failed: "+label)
        return campaign


def check_idle():
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["pid"] != os.getpid() and "python" in (p.info["name"] or "").lower():
            raise RuntimeError("Another Python process exists; inspect before running: "+str(p.info["pid"]))


def step2(stage):
    stage.guard("profile", ["claude.roadmap.stream_checks", "profile", "--epochs", "3"])
    cold = stage.guard("parity-cold", ["claude.roadmap.stream_checks", "parity", "--x", "cold"])
    first = stage.guard("parity-first", ["claude.roadmap.stream_checks", "parity", "--x", "first"])
    stage.guard("gate-g2c", ["claude.roadmap.gate_checks", "g2c", "--parity", str(cold), str(first)], 120)
    stage.report["gates"]["G2c"] = True
    for arm in ("fixed", "d0"):
        dump = stage.guard(f"dump-{arm}", ["claude.roadmap.long_checks", "dump", "--arm", arm])
        stage.guard(f"compare-{arm}", ["claude.roadmap.long_checks", "compare", "--arm", arm, "--dump", str(dump)])
    stage.report["gates"]["G2a"] = json.loads((stage.folder/"profile/profile.json").read_text())["cached_bitwise_equal"]
    stage.report["gates"]["G2b"] = True
    stage.save()
    campaign = stage.long("g2d-aug3-d0", ROOT/AUG3_PREP, f"{CONFIGS}/unit-d0.json", 12)
    gate = stage.guard("gate-g2d", ["claude.roadmap.gate_checks", "g2d", "--campaign", str(campaign), "--archive", str(ROOT/AUG3_D0)], 120)
    stage.report["gates"]["G2d"] = json.loads((gate/"g2d.json").read_text())
    stage.report["status"] = "step2_gates_passed"


def step3_prepare(stage):
    check = stage.guard("traj-cache-check", ["claude.roadmap.traj_cache_check"])
    stage.report["gates"]["trajectory_cache_bitwise"] = json.loads((check/"traj_cache_check.json").read_text())["status"] == "trajectory_cache_bitwise_pass"
    stage.save()
    stations = ",".join(json.loads((ROOT/AUG2_DATED/"fixture.json").read_text())["context"]["stations"])
    stage.guard("prepare-six-check", ["claude.roadmap.long_prepare", "--day", "2026-08-02", "--start", "12:00", "--epochs", "37",
                                      "--stations", stations, "--check-six", str(ROOT/AUG2_DATED/"fixture.json")])
    stage.guard("prepare-12h", ["claude.roadmap.long_prepare", "--day", "2026-08-02", "--start", "12:00", "--epochs", "72", "--stations", stations])
    stage.guard("prepare-24h", ["claude.roadmap.long_prepare", "--day", "2026-08-02", "--start", "00:00", "--epochs", "144", "--stations", stations])
    stage.report["status"] = "step3_fixtures_prepared"


def chunk_for(g2d, estimate_count, epochs, cached=False):
    # Per-link work: 15 orbit/clock link evaluations + 3 per estimated force column; G2d measured the D0 arm.
    per_epoch = g2d["max_chunk_seconds_per_epoch"]*(16+3*estimate_count)/19
    # Integration and start-up (restore, environment, state) scale roughly with arc length; a trajectory
    # cache replaces integration by loading (declared allowance 20 s plus scaled start-up).
    integration = 20. if cached else g2d["max_chunk_integration_seconds"]*epochs/g2d["six_hour_epochs"]
    fixed = integration+g2d["max_chunk_startup_overhead_seconds"]*epochs/g2d["six_hour_epochs"]
    # Target 180 s per chunk worker including fixed costs (the first 24 h attempt measured 242 s at a 240 s target
    # because per-epoch cost grows with the retained dimension): 120 s margin under the unchanged 300 s cap.
    budget = 180-fixed
    if budget < 4*per_epoch:
        raise RuntimeError("A single chunk cannot fit the 300 s worker cap for this arc; replan, do not raise limits")
    return max(1, math.floor(budget/per_epoch))


def step3_fits(stage, step2_dir, prepare_dir, only=None):
    g2d = json.loads((Path(step2_dir)/"stage.json").read_text())["gates"]["G2d"]
    assert g2d["passed"]
    arms = [("12h-FB", "prepare-12h", "block-fixed.json", 0, 4), ("12h-D0", "prepare-12h", "unit-d0.json", 1, 4),
            ("12h-FU", "prepare-12h", "unit-fixed.json", 0, 4), ("12h-E5", "prepare-12h", "unit-ecom5.json", 5, 4),
            ("24h-FB", "prepare-24h", "block-fixed.json", 0, 6), ("24h-D0", "prepare-24h", "unit-d0.json", 1, 6),
            ("24h-E5", "prepare-24h", "unit-ecom5.json", 5, 6)]
    gate = json.loads((Path(prepare_dir)/"stage.json").read_text())["gates"]
    assert gate.get("trajectory_cache_bitwise") is True
    for label, prep, config, count, cap in arms:
        if only and label not in only:
            continue
        epochs = json.loads((Path(prepare_dir)/prep/"step.json").read_text())["epoch_count"]
        groups = 1 if epochs <= 72 else 2
        stage.long(label, Path(prepare_dir)/prep, f"{CONFIGS}/{config}", chunk_for(g2d, count, epochs, cached=True), cap, groups)
    stage.report["status"] = "step3_fits_complete"


def latest_converged(label):
    """Newest claude/runs/*-long-<label> campaign that completed, as (solution_dir, fixture)."""
    for campaign in sorted((ROOT/"claude/runs").glob(f"*-long-{label}"), reverse=True):
        manifest = json.loads((campaign/"validation.json").read_text())
        if manifest.get("status") == "long_fit_complete_not_accuracy_acceptance" and manifest.get("final"):
            return campaign/manifest["final"], ROOT/manifest["fixture"]
    return None


def step3_eval(stage):
    """Protocol comparisons over whichever step 3 arms have converged; missing arms are listed, not faked."""
    six = {"A0": (ROOT/"claude/runs/20260912T021739Z-arc/six-1", ROOT/AUG2_DATED/"fixture.json"),
           "FB6": (ROOT/BLOCK_CAMPAIGN/"B-02-linear-1", ROOT/AUG2_DATED/"fixture.json")}
    long = {label: latest_converged(label) for label in ("12h-FB", "12h-FU", "12h-D0", "12h-E5", "24h-FB", "24h-D0", "24h-E5")}
    stage.report["arms_available"] = {k: (str(v[0]) if v else None) for k, v in long.items()}
    stage.save()

    def evaluate(name, arms, baseline, domains, expect=()):
        args = ["claude.roadmap.long_evaluate", "--day", "2026-08-02", "--out-name", name, "--baseline", baseline]
        for label, (solution, fixture) in arms.items():
            args += ["--arm", label, str(solution), str(fixture)]
        for d in domains:
            args += ["--domain", *d]
        for e in expect:
            args += ["--expect", *e]
        stage.guard(name, args, 300)

    twelve = {k: v for k, v in long.items() if k.startswith("12h") and v}
    day = {k: v for k, v in long.items() if k.startswith("24h") and v}
    if twelve:
        # Self-check: the archived six-hour nominal arm must reproduce its full-domain score (775 samples).
        evaluate("S6-6h-12h", {**six, **twelve}, "FB6", [("S6", "12:00", "18:00")], [("A0", "S6", "0.547216206")])
        if "12h-FB" in twelve:
            evaluate("S12-12h", twelve, "12h-FB", [("S12", "12:00", "23:45")])
    if day and "24h-FB" in day:
        evaluate("S6-S12-with-24h", {**six, **twelve, **day}, "24h-FB", [("S6", "12:00", "18:00"), ("S12", "12:00", "23:45")])
        evaluate("S24-24h", day, "24h-FB", [("S24", "00:00", "23:45")])
    stage.report["status"] = "step3_evaluation_complete_for_available_arms"


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run directly, never inside a guard"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("step2", "step3-prepare", "step3-fits", "step3", "step3-eval"), required=True)
    parser.add_argument("--step2")
    parser.add_argument("--prepare")
    parser.add_argument("--arms", help="comma-separated subset of step 3 arm labels")
    parser.add_argument("--regression-gate", action="store_true",
                        help="before fits, rerun stream_checks parity --x cold (checkpoint split must stay bitwise)")
    args = parser.parse_args()
    check_idle()
    stage = Stage(args.stage)
    try:
        if args.stage == "step2":
            step2(stage)
        elif args.stage == "step3-prepare":
            step3_prepare(stage)
        elif args.stage == "step3-eval":
            step3_eval(stage)
        elif args.stage == "step3":
            step3_prepare(stage)
            stage.save()
            step3_fits(stage, args.step2, stage.folder)
        else:
            if args.regression_gate:
                cold = stage.guard("parity-cold-regression", ["claude.roadmap.stream_checks", "parity", "--x", "cold"])
                stage.guard("gate-g2c-regression", ["claude.roadmap.gate_checks", "g2c", "--parity", str(cold)], 120)
                stage.report["gates"]["G2c_after_restore_fix"] = True
                stage.save()
            step3_fits(stage, args.step2, args.prepare, set(args.arms.split(",")) if args.arms else None)
    except BaseException as error:
        stage.report.update(status="failed", error=repr(error))
        raise
    finally:
        stage.save()


if __name__ == "__main__":
    main()
