"""Score the station-network tests (PROTOCOL.md §6 with amendments A3 and A4); replaces finish_networks.sh (Astra N2).

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.networks.score_networks

Run directly, never inside a guard: it launches its own serial root guards (usage75, one thread), one at a time.
1. Preflight all 20 campaign/fixture pairs of the frozen `scoring_index.json`, and each final force model against its
   campaign pin and the `scoring_index_models.json` sidecar (A4, NR-03). Any problem: nothing is evaluated.
2. Per date, one guarded `Opus_Fork.evaluate` of U, V-op, S17-op and S50-op (V-op the baseline, NGA PE added). It is
   accepted only when the guard exits 0, the output is in that guard's new run folder, the `Opus_Fork/results` copy
   is byte-identical, and its provenance names exactly the indexed solutions, fixtures and force models on the right
   day.
3. One guarded `analyze_networks`, which reads the evaluations only through this run's record.
Writes `Opus_Fork/runs/networks-scoring-<UTC>/scoring.json` and every log there; exits 1 on any failure.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from Opus_Fork.experiments.transfer.common import sha
from Opus_Fork.paths import RESULTS, ROOT, STAGE2

HERE = ROOT/"Opus_Fork/experiments/networks"
INDEX = HERE/"scoring_index.json"
MODELS = HERE/"scoring_index_models.json"
EOP = STAGE2/"finals2000A.all"
ARMS = ("U", "V-op", "S17-op", "S50-op")
PY = r"C:\anaconda\python.exe"


def check_model_identity(entry, expected_sha256, root=ROOT):
    """A4 §4 (Astra NR-03), before any normalization between arms: the final force_model.json is byte-identical to
    its campaign's artifact pin and to the sidecar's expected hash, and decodes to the campaign record's force_model."""
    folder = root/entry["campaign"]
    path = folder/entry["final"]/"force_model.json"
    if not path.exists():
        return ["final force model missing"]
    record = json.loads((folder/"validation.json").read_text())
    pin = (record.get("artifacts_sha256") or {}).get(f"{entry['final']}/force_model.json")
    actual, problems = sha(path), []
    if pin is None or actual != pin:
        problems.append("final force model is not the campaign's pinned artifact")
    if actual != expected_sha256:
        problems.append("final force model is not the one the sidecar expects")
    if json.loads(path.read_text()) != record.get("force_model"):
        problems.append("final force model differs from the campaign record")
    return problems


def preflight(index, models, root=ROOT):
    """(problems, duplicates): every indexed campaign must be the complete, converged, bound fit the index names, with
    the force model its campaign pinned (`models`: the scoring_index_models.json sidecar). Other folders carrying the
    same label are recorded, never used."""
    problems, duplicates = [], {}
    for day, arms in index["dates"].items():
        if sorted(arms) != sorted(ARMS):
            problems.append(f"{day}: arms {sorted(arms)}")
            continue
        for arm, e in arms.items():
            tag, folder = f"{day} {arm}", root/e["campaign"]
            if not folder.is_dir():
                problems.append(f"{tag}: campaign folder missing ({e['campaign']})")
                continue
            others = sorted(p.name for p in folder.parent.glob(f"*-fit-{e['label']}") if p.resolve() != folder.resolve())
            if others:
                duplicates[tag] = others
            try:
                record = json.loads((folder/"validation.json").read_text())
            except (OSError, ValueError) as exc:
                problems.append(f"{tag}: campaign record unreadable ({exc})")
                continue
            if not str(record.get("status", "")).startswith("long_fit_complete"):
                problems.append(f"{tag}: campaign not complete ({record.get('status')})")
            if record.get("label") != e["label"] or record.get("final") != e["final"]:
                problems.append(f"{tag}: label/final step {record.get('label')}/{record.get('final')} is not the indexed one")
            solution = folder/e["final"]/"solution.npz"
            if not solution.exists():
                problems.append(f"{tag}: final solution missing")
                continue
            step = json.loads((solution.parent/"step.json").read_text())
            if step.get("status") != "converged" or step.get("solution_sha256") != e["solution_sha256"] \
                    or sha(solution) != e["solution_sha256"]:
                problems.append(f"{tag}: solution is not the indexed converged solution")
            if (step.get("binding") or {}).get("fixture") != e["fixture_sha256"]:
                problems.append(f"{tag}: solution is not bound to the indexed fixture")
            fixture = root/e["fixture"]
            if not fixture.exists() or sha(fixture) != e["fixture_sha256"]:
                problems.append(f"{tag}: fixture missing or changed")
            expected = ((models.get("dates") or {}).get(day) or {}).get(arm, {}).get("sha256")
            problems += [f"{tag}: {p}" for p in check_model_identity(e, expected, root)]
    return problems, duplicates


def evaluate_command(day, arms):
    command = [PY, "-m", "customkf.guard", "--profile", "usage75", "--threads", "1", "--timeout", "1800", "--",
               "Opus_Fork.evaluate", "--day", day, "--out-name", out_name(day), "--baseline", "V-op"]
    for arm in ARMS:
        command += ["--arm", arm, f"{arms[arm]['campaign']}/{arms[arm]['final']}", arms[arm]["fixture"]]
    return command+["--domain", "full", "00:00", "23:45"]


def out_name(day):
    return "networks_"+day.replace("-", "")


def run_logged(command, log, cwd=ROOT):
    """(exit status, the guard's run folder or None), with all output kept in `log`."""
    with open(log, "w", encoding="utf-8") as f:
        code = subprocess.run(command, cwd=cwd, stdout=f, stderr=subprocess.STDOUT).returncode
    found = re.search(r"^Logs: (.+?)\s*$", Path(log).read_text(encoding="utf-8", errors="replace"), re.M)
    return code, (Path(found.group(1)) if found else None)


def accept_evaluation(code, guard_dir, day, arms, started, models, results=RESULTS):
    """(output path or None, problems): only this run's fresh, provenance-bound evaluation is accepted. `models`: the
    sidecar's entries for this day; each arm's evaluated force model must be the expected one (NR-03)."""
    problems = [] if code == 0 else [f"guard exit status {code}"]
    if guard_dir is None:
        return None, problems+["no guard run folder in the log"]
    out = guard_dir/f"{out_name(day)}.json"
    if not out.exists():
        return None, problems+["no output in the guard run folder"]
    if out.stat().st_mtime < started:
        problems.append("output predates this run")
    copy = results/f"{out_name(day)}.json"
    if not copy.exists() or copy.read_bytes() != out.read_bytes():
        problems.append("the results copy is not this run's output")
    evaluation = json.loads(out.read_text())
    if evaluation.get("day") != day or evaluation.get("status") != "evaluation_not_accuracy_acceptance":
        problems.append(f"day/status {evaluation.get('day')}/{evaluation.get('status')}")
    provenance = evaluation.get("provenance", {})
    for arm in ARMS:
        p = provenance.get(arm, {})
        if p.get("sha256") != arms[arm]["solution_sha256"] or p.get("fixture_sha256") != arms[arm]["fixture_sha256"]:
            problems.append(f"{arm}: evaluated solution or fixture is not the indexed one")
        if p.get("force_model_sha256") is None or p.get("force_model_sha256") != models.get(arm, {}).get("sha256"):
            problems.append(f"{arm}: evaluated force model is not the expected one")
    if "NGA" not in provenance or "common_key_digest" not in evaluation:
        problems.append("NGA PE or the population digest is missing")
    return out, problems


def main():
    folder = ROOT/"Opus_Fork/runs"/("networks-scoring-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir()
    record_path = folder/"scoring.json"
    index, models = json.loads(INDEX.read_text()), json.loads(MODELS.read_text())
    record = dict(status="preflight", index=INDEX.relative_to(ROOT).as_posix(), index_sha256=sha(INDEX),
                  models=MODELS.relative_to(ROOT).as_posix(), models_sha256=sha(MODELS),
                  eop=EOP.relative_to(ROOT).as_posix(), eop_sha256_before=sha(EOP),
                  started_utc=datetime.now(timezone.utc).isoformat(), evaluations={})

    def save(status=None):
        if status:
            record["status"] = status
        record_path.write_text(json.dumps(record, indent=1, default=str)+"\n")

    def stop(status, message):
        save(status)
        print(f"STOPPED ({status}): {message}; record {record_path}", flush=True)
        sys.exit(1)

    record["preflight_problems"], record["duplicate_labels"] = preflight(index, models)
    if models.get("index_sha256") != record["index_sha256"]:
        record["preflight_problems"].append("the models sidecar is not bound to this scoring index")
    save()
    if record["preflight_problems"]:
        stop("preflight_failed", "; ".join(record["preflight_problems"]))
    print("preflight passed: 20 campaigns", flush=True)
    for day, arms in index["dates"].items():
        save("evaluating "+day)
        started = time.time()-2
        code, guard_dir = run_logged(evaluate_command(day, arms), folder/f"evaluate_{day}.log")
        out, problems = accept_evaluation(code, guard_dir, day, arms, started, models["dates"][day])
        record["evaluations"][day] = dict(log=f"evaluate_{day}.log", exit_code=code, guard_dir=str(guard_dir),
                                          output=str(out) if out else None, output_sha256=sha(out) if out else None,
                                          problems=problems)
        save()
        if problems:
            stop("evaluation_failed", f"{day}: {'; '.join(problems)}")
        print(day, "evaluated", flush=True)
    record["eop_sha256_after"] = sha(EOP)
    if record["eop_sha256_after"] != record["eop_sha256_before"]:
        stop("eop_changed", "the Earth-orientation file changed during scoring")
    save("analyzing")
    code, guard_dir = run_logged([PY, "-m", "customkf.guard", "--profile", "usage75", "--threads", "1", "--timeout",
                                  "3600", "--", "Opus_Fork.experiments.networks.analyze_networks", "--scoring",
                                  str(record_path)], folder/"analysis.log")
    output = guard_dir/"networks_analysis.json" if guard_dir else None
    record["analysis"] = dict(log="analysis.log", exit_code=code, guard_dir=str(guard_dir),
                              output=str(output) if output and output.exists() else None)
    if code != 0 or not (output and output.exists()):
        stop("analysis_failed_or_controls_failed", f"analysis exit status {code}")
    save("complete")
    print("complete:", output, flush=True)


if __name__ == "__main__":
    main()
