"""Run DIRECTLY, never nested: the two claude-side fixture variants of the 14-station case.

    C:\\anaconda\\python.exe -m claude.tools.run_fixture_variants [--variants holdout-2h,phase-weight]

holdout-2h fits only the first two hours and scores the withheld third hour, testing short-arc
information from the opposite side to Astra's longer-arc experiment. phase-weight replaces the
phase sigma model with one fitted to this arc's own residuals, as the error-model diagnostic
indicated. Both are fixture surgery on a copy of the archived GUAM fixture; no root source, data,
validation archive or baseline is modified, and neither replaces the baseline.

Serial guarded workers with default limits: <=300 s per preparation and iteration, at most five
iterations per variant, <=120 s for the evaluator. Stops at the first failure.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import Limits, run
from claude.tools.pinned_sources import GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/evaluate_ablation.py",)
OWN = ("claude/tools/fixture_variant_step.py", "claude/tools/evaluate_variant.py",
       "claude/tools/run_fixture_variants.py", "claude/tools/pinned_sources.py",
       "claude/tools/ablation_step.py", "claude/tools/yell_continuation_review.py")
STABILITY = ROOT / "claude/runs/20260911T162036Z-stability"
MAX_ITERATIONS = 5


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default="holdout-2h,phase-weight")
    names = parser.parse_args().variants.split(",")
    assert len(set(names)) == len(names) and set(names) <= {"holdout-2h", "phase-weight"}
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    for name, digest in base["artifacts_sha256"].items():
        assert sha(GUAM / name) == digest, name
    # The iteration engine is reused unchanged from the passed stability campaign.
    engine_pin = json.loads((STABILITY / "validation.json").read_text())["source_sha256"]["claude/tools/ablation_step.py"]
    assert sha(ROOT / "claude/tools/ablation_step.py") == engine_pin, "ablation_step.py changed since the stability campaign"
    folder = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-fixture-variants")
    folder.mkdir()
    sources = {name: sha(ROOT / name) for name in (*base["source_sha256"], *HELPERS, *OWN, *policy["new_files_sha256"])}
    for name in sources:
        target = folder / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    report = {
        "status": "running", "operator": "Claude (Opus) while Astra is idle; diagnostic variants, not a new baseline",
        "source_policy": policy, "source_sha256": sources, "report_sha256": base["report_sha256"],
        "baseline": GUAM.relative_to(ROOT).as_posix(), "baseline_manifest_sha256": sha(GUAM / "validation.json"),
        "iteration_engine_sha256": engine_pin, "cases": {}, "active_worker": None, "runs": {},
        "predeclared_protocol": "Two fixture variants of the archived 14-station case, estimator and model unchanged. "
                                "holdout-2h: keep solve epochs 0-23, keep the three-hour trajectory, and score the withheld "
                                "third hour separately; the wet basis necessarily shrinks with the arc. phase-weight: phase "
                                "sigma sqrt(a^2+b^2/sin^2 elevation) with a,b least squares on this arc's baseline phase "
                                "residuals, recorded before any IGS scoring, code sigma unchanged. At most five 300 s "
                                "iterations per variant and one 120 s evaluator. Frozen sigma<=10 m split; score all 31 "
                                "satellites plus determined and determined-in-both; keep every satellite visible. Neither "
                                "variant replaces the GUAM baseline."}

    def save():
        pending = folder / "pending.json"
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(folder / "validation.json")

    def worker(name, args, timeout=300):
        report["active_worker"] = {"name": name, "module_args": args, "started_utc": datetime.now(timezone.utc).isoformat()}
        save()
        print("Starting " + name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        shutil.copytree(path, folder / name)
        report["runs"][name] = {**result, "original_directory": str(path)}
        report["active_worker"] = None
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s', 0):.1f}s, {result.get('peak_sampled_rss_mib', 0):.1f} MiB RSS", flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Failed worker: " + name)
        return folder / name

    save()
    try:
        for variant in names:
            case = report["cases"][variant] = {"prepare": f"{variant}-prepare", "iterations": [], "final": None}
            save()
            worker(case["prepare"], ["claude.tools.fixture_variant_step", "prepare", "--variant", variant])
            previous = None
            for index in range(MAX_ITERATIONS):
                name = f"{variant}-iteration-{index}"
                args = ["claude.tools.fixture_variant_step", "iterate", "--fixture", str(folder / case["prepare"] / "fixture.json")]
                if previous:
                    args.extend(["--previous", str(previous)])
                previous = worker(name, args)
                case["iterations"].append(name)
                save()
                if json.loads((previous / "step.json").read_text())["status"] == "converged":
                    case["final"] = name
                    save()
                    break
            if not case["final"]:
                raise RuntimeError("Not converged within the iteration cap: " + variant)
        worker("evaluation", ["claude.tools.evaluate_variant", str(folder)], 120)
        if verify(HELPERS) != policy:
            raise RuntimeError("Source state changed during the campaign")
        for name, digest in sources.items():
            assert sha(ROOT / name) == digest, name
        report["status"] = "fixture_variants_complete_diagnostic_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        values = list(report["runs"].values())
        if values:
            report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                          peak_sampled_rss_mib=max(v.get("peak_sampled_rss_mib", 0) for v in values),
                          minimum_system_available_gib=min(v.get("minimum_system_available_gib", float("inf")) for v in values))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*"))
                                      if p.is_file() and p.name not in ("validation.json", "pending.json")}
        save()
    print("Archived: " + str(folder), flush=True)


if __name__ == "__main__":
    main()
