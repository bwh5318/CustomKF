"""Freeze the exact campaigns the network scoring uses (PROTOCOL.md amendment A3, Astra N2), before any evaluation.

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.networks.make_scoring_index

Writes `scoring_index.json`: for each date and arm, the campaign folder named below (never the latest folder with a
label), its final step, the solution hash, and the fixture the solution is bound to (its step.json binding),
cross-checked with the campaign record and, for the network arms, with fixtures.tsv. Refuses to overwrite an existing
index. Reads records and hashes only; no solution array or reference product is opened.
"""
import csv
import json
import sys

from Opus_Fork.experiments.transfer.common import sha
from Opus_Fork.paths import ROOT

HERE = ROOT/"Opus_Fork/experiments/networks"
INDEX = HERE/"scoring_index.json"
RUNS = "Opus_Fork/runs"
# date -> arm -> campaign folder. U on Jun 23 is the U-elw13-0623r rerun, as in the earlier validation scoring.
CAMPAIGNS = {
    "2026-06-06": {"U": "20260930T012728Z-fit-U-elw13-0606", "V-op": "20261002T200402Z-fit-V-op-0606",
                   "S17-op": "20261005T220139Z-fit-S17-op-0606", "S50-op": "20261007T215554Z-fit-S50e-op-0606"},
    "2026-06-20": {"U": "20260929T233503Z-fit-U-elw13-0620", "V-op": "20261002T221652Z-fit-V-op-0620",
                   "S17-op": "20261005T230105Z-fit-S17-op-0620", "S50-op": "20261008T005002Z-fit-S50e-op-0620"},
    "2026-06-23": {"U": "20261001T012217Z-fit-U-elw13-0623r", "V-op": "20261003T000959Z-fit-V-op-0623",
                   "S17-op": "20261006T002221Z-fit-S17-op-0623", "S50-op": "20261008T171242Z-fit-S50e-op-0623"},
    "2026-07-06": {"U": "20260930T234445Z-fit-U-elw13-0706", "V-op": "20261003T010331Z-fit-V-op-0706",
                   "S17-op": "20261006T010650Z-fit-S17-op-0706", "S50-op": "20261008T194751Z-fit-S50e-op-0706"},
    "2026-07-23": {"U": "20260930T220757Z-fit-U-elw13-0723", "V-op": "20261003T025119Z-fit-V-op-0723",
                   "S17-op": "20261006T220323Z-fit-S17-op-0723", "S50-op": "20261008T222335Z-fit-S50e-op-0723"},
}
NETWORK = {"S17-op": "S17", "S50-op": "S50"}


def entry(day, arm, name):
    folder = ROOT/RUNS/name
    record = json.loads((folder/"validation.json").read_text())
    assert record["status"].startswith("long_fit_complete"), (name, record["status"])
    solution = folder/record["final"]/"solution.npz"
    step = json.loads((solution.parent/"step.json").read_text())
    assert step["status"] == "converged" and sha(solution) == step["solution_sha256"], name
    fixture = record["fixture"]
    assert sha(ROOT/fixture) == step["binding"]["fixture"], (name, "fixture binding")
    if arm in NETWORK:
        prepared = [r["run"] for r in csv.DictReader(open(HERE/"fixtures.tsv"), delimiter="\t")
                    if r["network"] == NETWORK[arm] and r["date"] == day and r["status"] == "prepared"]
        assert fixture.startswith(tuple(p+"/" for p in prepared)), (name, fixture, prepared)
    return dict(campaign=f"{RUNS}/{name}", label=record["label"], final=record["final"],
                solution_sha256=step["solution_sha256"], fixture=fixture, fixture_sha256=step["binding"]["fixture"],
                eliminate_ambiguities=bool(record.get("spec", {}).get("eliminate_ambiguities")))


def main():
    if INDEX.exists():
        sys.exit(f"{INDEX} exists; the index is frozen")
    index = dict(note="Frozen before any network evaluation (PROTOCOL.md amendment A3). Arm S50-op is the S50e-op "
                      "campaign (amendment A2).",
                 dates={day: {arm: entry(day, arm, name) for arm, name in arms.items()} for day, arms in CAMPAIGNS.items()})
    INDEX.write_text(json.dumps(index, indent=1)+"\n")
    print("wrote", INDEX)


if __name__ == "__main__":
    main()
