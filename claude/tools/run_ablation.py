"""Controller for Claude's Stage 5b KOUR ablations. Run DIRECTLY (never under the guard):

    C:\\anaconda\\python.exe -m claude.tools.run_ablation [--cases name,name]

Every numerical step runs serially in its own customkf.guard worker with the unchanged
default limits (2 GiB, 1 CPU/thread, 10% CPU, 300 s, 8 GiB reserve). Each finished run
folder is MOVED from runs/ into claude/runs/<campaign>/ so Astra's runs/ stays clean.
If another guarded job (e.g. Astra's) holds the workspace lock, the controller stops and
records that instead of retrying.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import ROOT, Limits, run
from customkf.prepare_stage2 import sha

CASES = {
    # Stage 3 KOUR_INVESTIGATION flagged ~13:30-14:30 GPST (solve epochs 18-30).
    "expanded-long-no-kour-window": {"base": "expanded-long", "exclude": ["KOUR:18-30"]},
    "eight-long-no-kour-window": {"base": "eight-long", "exclude": ["KOUR:18-30"]},
    "expanded-long-no-kour": {"base": "expanded-long", "exclude": ["KOUR"]},
}
MAX_ITERATIONS = 6


def tracked_sources():
    return {p.relative_to(ROOT).as_posix(): sha(p) for folder in ("customkf", "tests") for p in sorted((ROOT / folder).glob("*.py"))}


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=",".join(CASES))
    names = parser.parse_args().cases.split(",")
    campaign = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-kour-ablation")
    campaign.mkdir(parents=True)
    report = {"status": "running", "scoring_rule": "claude/SCORING_RULE.md",
              "limits": "customkf.guard defaults, unchanged", "cases": {}, "workers": {},
              "astra_sources_at_start": tracked_sources()}

    def save():
        (campaign / "campaign.json").write_text(json.dumps(report, indent=2) + "\n")

    def worker(name, args):
        print("Starting " + name, flush=True)
        result, path = run(args, Limits(timeout_s=300))
        shutil.move(str(path), str(campaign / name))
        report["workers"][name] = {**result, "original_directory": str(path)}
        save()
        print(f"  {name}: {result['status']}, {result.get('elapsed_s', 0):.1f} s, "
              f"{result.get('peak_sampled_rss_mib', 0):.0f} MiB RSS, min avail {result.get('minimum_system_available_gib', 0):.2f} GiB", flush=True)
        return result["status"] == "ok"

    save()
    try:
        for name in names:
            spec = CASES[name]
            case = report["cases"][name] = {**spec, "prepare": name + "-prepare", "iterations": [], "final": None, "status": "running"}
            args = ["claude.tools.ablation_step", "prepare", "--case", spec["base"], "--name", name]
            for rule in spec["exclude"]:
                args += ["--exclude", rule]
            if not worker(case["prepare"], args):
                case["status"] = "prepare_failed"
                save()
                continue
            previous = None
            for i in range(MAX_ITERATIONS):
                label = f"{name}-iteration-{i}"
                args = ["claude.tools.ablation_step", "iterate", "--fixture", str(campaign / case["prepare"] / "fixture.json")]
                if previous:
                    args += ["--previous", str(campaign / previous)]
                ok = worker(label, args)
                case["iterations"].append(label)
                if not ok:
                    case["status"] = "iteration_failed"
                    break
                step = json.loads((campaign / label / "step.json").read_text())
                previous = label
                if step["status"] == "converged":
                    case.update(status="converged", final=label)
                    break
            else:
                case["status"] = "not_converged_within_limit"
            save()
        if any(c.get("final") for c in report["cases"].values()):
            worker("evaluation", ["claude.tools.evaluate_ablation", str(campaign)])
        report["astra_sources_unchanged"] = tracked_sources() == report["astra_sources_at_start"]
        report["status"] = "completed_ablation_diagnostic_not_accuracy_acceptance"
    except RuntimeError as error:
        report.update(status="stopped", error=str(error))
        if "Another customKF guarded experiment is running" in str(error):
            report["status"] = "yielded_to_other_guarded_job"
        raise
    finally:
        workers = list(report["workers"].values())
        if workers:
            report.update(total_guarded_seconds=sum(w.get("elapsed_s", 0) for w in workers),
                          peak_sampled_rss_mib=max(w.get("peak_sampled_rss_mib", 0) for w in workers),
                          minimum_system_available_gib=min(w.get("minimum_system_available_gib", float("inf")) for w in workers))
        save()
        print("Campaign archived: " + str(campaign), flush=True)


if __name__ == "__main__":
    main()
