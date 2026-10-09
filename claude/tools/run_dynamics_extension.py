"""Run DIRECTLY, never nested: fixed-force reference-fit extension to every GUAM-fixture satellite.

    C:\\anaconda\\python.exe -m claude.tools.run_dynamics_extension

Phase 1 reruns Astra's G18/G03/G22 fits and requires bitwise agreement with the completed
claude/runs/20260911T211901Z-dynamics-ceiling archive, under the documented source-drift policy
(claude/tools/pinned_sources.py). Phase 2 fits the other 28 satellites serially, stopping at the
first failed guard, rank, convergence or input check. Phase 3 is a separate <=120 s guarded
review. Default guard limits, <=300 s per fit worker. Writes a new campaign; the completed one is
untouched.
"""
from datetime import datetime, timezone
import json
import os
import shutil

from customkf.guard import Limits, run
from claude.tools.pinned_sources import DYNAMICS, GUAM, ROOT, sha, verify

HELPERS = ("claude/tools/fixed_force_fit.py", "claude/tools/dynamics_ceiling_step.py", "claude/tools/evaluate_ablation.py")
OWN = ("claude/tools/pinned_sources.py", "claude/tools/dynamics_extension_step.py",
       "claude/tools/run_dynamics_extension.py", "claude/tools/dynamics_extension_review.py")
REPRODUCE = ("G18", "G03", "G22")


def main():
    if os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Do not nest guards")
    policy = verify(HELPERS)
    base = json.loads((GUAM / "validation.json").read_text())
    for name, digest in base["artifacts_sha256"].items():
        assert sha(GUAM / name) == digest, name
    archived = json.loads((DYNAMICS / "validation.json").read_text())
    assert archived["status"] == "fixed_force_reference_diagnostic_complete_not_independent_POD" and archived["active_worker"] is None
    for name, digest in archived["artifacts_sha256"].items():
        assert sha(DYNAMICS / name) == digest, name
    satellites = sorted(json.loads((GUAM / "prepare/fixture.json").read_text())["seeds"])
    assert len(satellites) == 31 and set(REPRODUCE) <= set(satellites)
    remaining = [s for s in satellites if s not in REPRODUCE]
    folder = ROOT / "claude/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-dynamics-extension")
    folder.mkdir()
    sources = {name: sha(ROOT / name) for name in (*base["source_sha256"], *HELPERS, *OWN, *policy["new_files_sha256"])}
    for name in sources:
        target = folder / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    report = {
        "status": "running", "operator": "Claude (Opus) while Astra is idle; user authorized accepting the inconsequential drift",
        "source_policy": policy, "source_sha256": sources, "report_sha256": base["report_sha256"],
        "baseline_manifest_sha256": sha(GUAM / "validation.json"),
        "archived_campaign": DYNAMICS.relative_to(ROOT).as_posix(), "archived_manifest_sha256": sha(DYNAMICS / "validation.json"),
        "satellites": satellites, "reproduce": list(REPRODUCE), "extend": remaining,
        "completed": {}, "active_worker": None, "runs": {},
        "predeclared_protocol": "Extend the completed fixed-force reference diagnostic to every GUAM-fixture satellite with the identical "
                                "six-state fit: production Trajectory, ECOM5 [-1e-7,0,0,0,0], broadcast start, no priors, seven half-hour "
                                "native IGS positions train, six interleaved quarter-hours withheld, <=4 iterations, rank 6. First reproduce "
                                "archived G18/G03/G22 bitwise under the documented prepare()-only stage5_pilot.py drift, else stop. Then the "
                                "other 28 serially; stop at the first failed guard/rank/convergence/input check. Report per-SV train/held/all "
                                "RMS, observation-solution RMS on the same epochs, rank/condition and pooled values. Held-out <0.1 m stays a "
                                "diagnostic flag, not a POD gate. No reference-fitted state enters station-based POD."}

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
        for sat in REPRODUCE:
            worker(f"reproduce-{sat}", ["claude.tools.dynamics_extension_step", "--satellite", sat, "--compare-archive"])
            report["completed"][sat] = f"reproduce-{sat}"
            save()
        for sat in remaining:
            worker(sat, ["claude.tools.dynamics_extension_step", "--satellite", sat])
            report["completed"][sat] = sat
            save()
        worker("review", ["claude.tools.dynamics_extension_review", str(folder)], 120)
        if verify(HELPERS) != policy:
            raise RuntimeError("Source state changed during the campaign")
        for name, digest in sources.items():
            assert sha(ROOT / name) == digest, name
        report["status"] = "fixed_force_extension_complete_not_independent_POD"
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
