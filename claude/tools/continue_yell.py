"""Claude's continuation of Astra's interrupted YELL campaign. Run DIRECTLY, never under the guard:

    C:\\anaconda\\python.exe -m claude.tools.continue_yell

Astra's controller for validation/yell/20260911T020943Z was killed from outside during
iteration-1 (11 Sep 2026, about 02:17 UTC): that worker wrote no guard result and the
manifest was left "running". That archive and manifest are not edited. Following
claude/ASTRA_VERIFICATION_HANDOFF.md, download/PPP/prepare are not rerun. This verifies the
pinned sources, report, inputs, fixture and iteration-0 checkpoint, then runs the remaining
customkf.stage5b_step iterations serially (300 s each; five iterations in total counting
iteration-0) and customkf.evaluate_yell (120 s), all with default guard limits. Each guard
folder is moved from runs/ into this campaign. Stops on any refusal, worker failure, timeout,
checkpoint/fixture/source change or non-convergence; never retries.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha

ORIGINAL = ROOT / "validation/yell/20260911T020943Z"
RESUME_FROM = "iteration-0"
INTERRUPTED_WORKER = ROOT / "runs/20260911T021441Z-23d4bb2d"
TOTAL_ITERATIONS = 5
HELPERS = ("claude/tools/continue_yell.py", "claude/tools/yell_result_review.py")


def rel(path):
    return Path(path).relative_to(ROOT).as_posix()


def tracked_sources():
    # Same set validate_yell pinned at launch.
    paths = [*sorted((ROOT / "customkf").glob("*.py")), *sorted((ROOT / "tests").glob("*.py")),
             ROOT / "claude/tools/evaluate_ablation.py", ROOT / "claude/SCORING_RULE.md"]
    return {rel(p): sha(p) for p in paths}


def inventory(folder):
    return {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    original = json.loads((ORIGINAL / "validation.json").read_text())
    # Continue only the exact interrupted state found on 11 Sep, never a finished or failed campaign.
    iterations = sorted(n for n in original["runs"] if n.startswith("iteration-"))
    if (original["status"] != "running" or original["final"] is not None or "artifacts_sha256" in original
            or iterations != [RESUME_FROM] or original["runs"][RESUME_FROM]["status"] != "ok"):
        raise ValueError("Original campaign is not in the expected interrupted state")
    if (ORIGINAL / "iteration-1").exists() or (INTERRUPTED_WORKER / "result.json").exists():
        raise ValueError("Interrupted iteration-1 left a result; inspect it before continuing")
    current = tracked_sources()
    if current != original["source_sha256"]:
        changed = sorted(k for k in current.keys() | original["source_sha256"].keys()
                         if current.get(k) != original["source_sha256"].get(k))
        raise ValueError("Source changed since the original launch: " + ", ".join(changed))
    for name, digest in original["report_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Report file changed: " + name)
    fixture = ORIGINAL / "prepare/fixture.json"
    fixture_sha = sha(fixture)
    prepare = json.loads((ORIGINAL / "prepare/step.json").read_text())
    if prepare["case"] != "yell-long" or prepare["fixture_sha256"] != fixture_sha:
        raise ValueError("Changed/wrong fixture")
    for name, digest in prepare["source_sha256"].items():
        if current.get(name) != digest:
            raise ValueError("Source changed since fixture: " + name)
    for name, digest in json.loads(fixture.read_text())["context"]["inputs"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Input hash changed: " + name)
    start = json.loads((ORIGINAL / RESUME_FROM / "step.json").read_text())
    if (start["status"] != "iteration_complete" or start["case"] != "yell-long" or start["fixture_sha256"] != fixture_sha
            or len(start["history"]) != 1 or sha(ORIGINAL / RESUME_FROM / "solution.npz") != start["solution_sha256"]):
        raise ValueError("Resume checkpoint is not a successful pinned iteration")

    launched = datetime.now(timezone.utc)
    campaign = ROOT / "claude/runs" / (launched.strftime("%Y%m%dT%H%M%SZ") + "-yell-continuation")
    (campaign / "prepare").mkdir(parents=True)
    # customkf.evaluate_yell reads prepare/ from the campaign it is given.
    for name in ("fixture.json", "initial.npz", "step.json"):
        shutil.copyfile(ORIGINAL / "prepare" / name, campaign / "prepare" / name)
        if sha(campaign / "prepare" / name) != sha(ORIGINAL / "prepare" / name):
            raise ValueError("Prepare copy mismatch: " + name)
    sources = {**current, **{h: sha(ROOT / h) for h in HELPERS}}
    for name in sources:
        target = campaign / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    report = {
        "status": "running", "kind": "continuation_of_externally_interrupted_campaign",
        "launched_utc": launched.isoformat(), "operator": "Claude (support role; Astra usage exhausted)",
        "original_campaign": rel(ORIGINAL), "original_manifest_sha256": sha(ORIGINAL / "validation.json"),
        "original_state_found": {
            "status": original["status"], "final": original["final"], "recorded_runs": list(original["runs"]),
            "note": "validate_yell and its iteration-1 stage5b_step worker were no longer running at 2026-09-11T02:18Z; "
                    "iteration-1 wrote no guard result and empty logs; manifest never finalized. Left unedited."},
        "interrupted_original_worker": {"directory": rel(INTERRUPTED_WORKER),
                                        "file_sizes": {p.name: p.stat().st_size for p in sorted(INTERRUPTED_WORKER.iterdir())}},
        "original_inventory_sha256": inventory(ORIGINAL),
        "fixture": {"path": rel(fixture), "sha256": fixture_sha},
        "prepare_copy_sha256": {n: sha(campaign / "prepare" / n) for n in ("fixture.json", "initial.npz", "step.json")},
        "resume_from": {"path": rel(ORIGINAL / RESUME_FROM), "step_sha256": sha(ORIGINAL / RESUME_FROM / "step.json"),
                        "solution_sha256": start["solution_sha256"], "history": start["history"]},
        "source_sha256": sources, "report_sha256": original["report_sha256"],
        "predeclared_case": original["predeclared_case"], "PPP_coordinate_gate": original["PPP_coordinate_gate"],
        "stopping_rule": "customkf.stage5b_step unchanged; at most five iterations in total counting original iteration-0; "
                         "300 s per iteration, 120 s evaluator; default guard limits",
        "checkpoints": {RESUME_FROM: rel(ORIGINAL / RESUME_FROM)}, "runs": {}, "final": None}

    def save():
        (campaign / "validation.json").write_text(json.dumps(report, indent=2) + "\n")

    def launch(name, args, timeout):
        print("Starting " + name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        shutil.move(str(path), str(campaign / name))
        report["runs"][name] = {**result, "original_directory": str(path)}
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s', 0):.1f} s, {result.get('peak_sampled_rss_mib', 0):.1f} MiB RSS, "
              f"min available {result.get('minimum_system_available_gib', 0):.2f} GiB", flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Worker failed: " + name)
        if tracked_sources() != current:
            raise RuntimeError("Unexpected source change during " + name)
        return campaign / name

    save()
    try:
        previous = ORIGINAL / RESUME_FROM
        for i in range(len(start["history"]), TOTAL_ITERATIONS):
            name = f"iteration-{i}"
            folder = launch(name, ["customkf.stage5b_step", "--case", "yell-long", "--fixture", str(fixture),
                                   "--previous", str(previous)], 300)
            step = json.loads((folder / "step.json").read_text())
            before = json.loads((previous / "step.json").read_text())["history"]
            if (step["fixture_sha256"] != fixture_sha or sha(folder / "solution.npz") != step["solution_sha256"]
                    or step["history"][:-1] != before or len(step["history"]) != i + 1):
                raise RuntimeError("Checkpoint chain mismatch at " + name)
            report["checkpoints"][name] = rel(folder)
            previous = folder
            if step["status"] == "converged":
                report["final"] = name
                save()
                break
        if not report["final"]:
            raise RuntimeError("Not converged within five bounded iterations in total")
        launch("evaluation", ["customkf.evaluate_yell", str(campaign)], 120)
        for name, digest in report["report_sha256"].items():
            if sha(ROOT / name) != digest:
                raise RuntimeError("Report file changed: " + name)
        if inventory(ORIGINAL) != report["original_inventory_sha256"]:
            raise RuntimeError("Original campaign archive changed during continuation")
        report["original_archive_unchanged"] = True
        report["status"] = "YELL_continuation_complete_not_accuracy_acceptance"
    except BaseException as error:
        busy = "Another customKF guarded experiment is running" in str(error)
        report.update(status="yielded_to_other_guarded_job" if busy else "failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        values = list(report["runs"].values())
        if values:
            report.update(total_guarded_seconds=sum(r.get("elapsed_s", 0) for r in values),
                          peak_sampled_rss_mib=max(r.get("peak_sampled_rss_mib", 0) for r in values),
                          minimum_system_available_gib=min(r.get("minimum_system_available_gib", float("inf")) for r in values))
        report["artifacts_sha256"] = {p.relative_to(campaign).as_posix(): sha(p) for p in sorted(campaign.rglob("*"))
                                      if p.is_file() and p != campaign / "validation.json"}
        save()
        print("Archived: " + str(campaign), flush=True)


if __name__ == "__main__":
    main()
