"""Run DIRECTLY, never nested: six-hour fixed-force reference diagnostic for every arc-fixture satellite.

    C:\\anaconda\\python.exe -m claude.tools.run_dynamics_six

Phase 1 reproduces three archived three-hour diagnostics with the new case-parameterized worker and
requires bitwise agreement with claude/runs/20260911T211901Z-dynamics-ceiling; that validates the
adaptation before any six-hour number is produced. Phase 2 fits the five satellites Astra named
first, then the remaining twenty-six serially, stopping at the first failed guard, rank,
convergence or input check. Phase 3 is a separate guarded review. Default guard limits, <=300 s per
worker, no nesting and no raised caps. Writes a new campaign under claude/runs; Astra's completed
arc campaign is read-only here. Guard folders are moved out of runs/ so Astra's newest-run
inspection keeps seeing Astra's own work.
"""
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import Limits, run
from claude.tools.dynamics_six_step import ARC, CASES, HELPERS
from claude.tools.pinned_sources import DYNAMICS, GUAM, ROOT, sha, verify

OWN = ("claude/tools/pinned_sources.py", "claude/tools/dynamics_six_step.py",
       "claude/tools/dynamics_six_review.py", "claude/tools/run_dynamics_six.py")
REPRODUCE = ("G18", "G03", "G22")
PRIORITY = ("G23", "G19", "G04", "G26", "G03")
# Pre-campaign guard folders that validated the adaptation, including the one failed attempt
# (an over-strict archive field comparison in dynamics_six_step.compare_with_archive).
DEV_RUNS = ("20260912T024836Z-a9d3f22c", "20260912T024900Z-230d2036", "20260912T025021Z-e7224a47")


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    policy = verify(HELPERS)
    arc = json.loads((ARC / "validation.json").read_text())
    assert arc["status"] == "arc_experiment_complete_not_accuracy_acceptance" and arc["active_worker"] is None
    for name, digest in arc["artifacts_sha256"].items():
        assert sha(ARC / name) == digest, name
    for name, digest in arc["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    archived = json.loads((DYNAMICS / "validation.json").read_text())
    assert archived["status"] == "fixed_force_reference_diagnostic_complete_not_independent_POD"
    for name, digest in archived["artifacts_sha256"].items():
        assert sha(DYNAMICS / name) == digest, name
    guam = json.loads((GUAM / "validation.json").read_text())

    satellites = sorted(json.loads((ARC / CASES["six"]["fixture"]).read_text())["seeds"])
    assert len(satellites) == 31 and set(PRIORITY) <= set(satellites) and set(REPRODUCE) <= set(satellites)
    ordered = list(PRIORITY) + [s for s in satellites if s not in PRIORITY]
    assert sorted(ordered) == satellites

    folder = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-dynamics-six")
    folder.mkdir()
    sources = {name: sha(ROOT / name) for name in (*arc["source_sha256"], *HELPERS, *OWN, *policy["new_files_sha256"])}
    for name in sources:
        target = folder / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for name in DEV_RUNS:
        source = ROOT / "runs" / name
        if source.exists():
            shutil.move(str(source), str(folder / "development" / name))

    report = {
        "status": "running",
        "operator": "Claude (Opus) while Astra is idle; assignment from claude/ASTRA_VERIFICATION_HANDOFF.md",
        "question": "Does the fixed-force representation still reach centimetres on withheld native IGS positions "
                    "over a six-hour arc, or has the force model itself become comparable to the 0.5437 m station fit?",
        "source_policy": policy, "source_sha256": sources, "report_sha256": arc["report_sha256"],
        "arc_campaign": ARC.relative_to(ROOT).as_posix(), "arc_manifest_sha256": sha(ARC / "validation.json"),
        "archived_campaign": DYNAMICS.relative_to(ROOT).as_posix(),
        "archived_manifest_sha256": sha(DYNAMICS / "validation.json"),
        "guam_manifest_sha256": sha(GUAM / "validation.json"), "guam_final": guam["final"],
        "satellites": satellites, "order": ordered, "priority": list(PRIORITY), "reproduce": list(REPRODUCE),
        "development_runs": list(DEV_RUNS), "completed": {}, "reproduced": {}, "active_worker": None, "runs": {},
        "predeclared_protocol":
            "Extend the reference-only fixed-force diagnostic to the exact six-hour station-fit fixture "
            "(claude/runs/20260912T021739Z-arc/six-prepare/fixture.json, duration 21620 s, 37 ten-minute epochs; "
            "comparison orbit six-1/solution.npz). Take the saved five-minute output grid at [::3] to obtain 25 "
            "native IGS samples; train on indices 0,2,...,24 and withhold 1,3,...,23. Six initial-state parameters "
            "only, broadcast start, ECOM5 [-1e-7,0,0,0,0] fixed, original Trajectory and integration, no priors, no "
            "force estimation, no alignment, <=4 iterations, rank 6 required. Reproduce archived three-hour "
            "G18/G03/G22 bitwise first, else stop. Then G23/G19/G04/G26/G03, then all 31 serially. Report per-SV "
            "train/held/all and common-first-three-hour RMS against the six-hour station fit on identical epochs, "
            "keeping every satellite including regressions. A 0.1 m withheld flag is diagnostic only; no reference "
            "state ever enters station-based POD and no station or weight is changed to improve this day's score."}

    def save():
        pending = folder / "pending.json"
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.replace(folder / "validation.json")

    def worker(name, args, timeout=300):
        report["active_worker"] = {"name": name, "module_args": args, "started_utc": datetime.now(timezone.utc).isoformat()}
        save()
        print("Starting " + name, flush=True)
        result, path = run(args, Limits(timeout_s=timeout))
        shutil.move(str(path), str(folder / name))
        report["runs"][name] = {**result, "original_directory": str(path), "moved_from_runs": True}
        report["active_worker"] = None
        save()
        print(f"{name}: {result['status']}, {result.get('elapsed_s', 0):.1f}s, "
              f"{result.get('peak_sampled_rss_mib', 0):.1f} MiB RSS", flush=True)
        if result["status"] != "ok":
            raise RuntimeError("Failed worker: " + name)
        return folder / name

    save()
    try:
        for sat in REPRODUCE:
            name = f"reproduce-three-{sat}"
            worker(name, ["claude.tools.dynamics_six_step", "--case", "three", "--satellite", sat, "--compare-archive"])
            assert json.loads((folder / name / "diagnostic.json").read_text())["archived_reproduction"]["arrays"] == "bitwise equal"
            report["reproduced"][sat] = name
            save()
        for sat in ordered:
            path = worker(name := f"six-{sat}", ["claude.tools.dynamics_six_step", "--case", "six", "--satellite", sat])
            diagnostic = json.loads((path / "diagnostic.json").read_text())
            assert diagnostic["case"] == "six" and diagnostic["satellite"] == sat
            assert all(entry["rank"] == 6 for entry in diagnostic["history"])
            report["completed"][sat] = name
            if sat == PRIORITY[-1]:
                report["priority_gate"] = {first: report["completed"][first] for first in PRIORITY}
            save()
        worker("review", ["claude.tools.dynamics_six_review", str(folder)], 240)
        if verify(HELPERS) != policy:
            raise RuntimeError("Source state changed during the campaign")
        for name, digest in sources.items():
            assert sha(ROOT / name) == digest, name
        assert sha(ARC / "validation.json") == report["arc_manifest_sha256"]
        report["status"] = "six_hour_fixed_force_reference_complete_not_accuracy_acceptance"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        values = list(report["runs"].values())
        if values:
            report.update(total_guarded_seconds=sum(v.get("elapsed_s", 0) for v in values),
                          peak_sampled_rss_mib=max(v.get("peak_sampled_rss_mib", 0) for v in values),
                          peak_job_memory_mib=max(v.get("windows_peak_job_memory_mib", 0) for v in values),
                          minimum_system_available_gib=min(v.get("minimum_system_available_gib", float("inf")) for v in values),
                          longest_worker_s=max(v.get("elapsed_s", 0) for v in values))
        report["artifacts_sha256"] = {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*"))
                                      if p.is_file() and p.name not in ("validation.json", "pending.json")}
        save()
    print("Archived: " + str(folder), flush=True)


if __name__ == "__main__":
    main()
