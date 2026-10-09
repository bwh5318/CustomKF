"""Freeze the expected force model of every indexed campaign (PROTOCOL.md amendment A4 §4, Astra NR-03).

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.networks.make_scoring_index_models

Writes the sidecar `scoring_index_models.json`, bound to the frozen `scoring_index.json` by its hash, which stays
untouched. For each date and arm it records the final `force_model.json` and the hash its campaign pinned in
`artifacts_sha256`, after checking that the file matches that pin and decodes to the campaign record's `force_model`.
Refuses to overwrite an existing sidecar. Reads records and model files only.
"""
import json
import sys

from Opus_Fork.experiments.networks.score_networks import INDEX, MODELS, check_model_identity
from Opus_Fork.experiments.transfer.common import sha
from Opus_Fork.paths import ROOT


def main():
    if MODELS.exists():
        sys.exit(f"{MODELS} exists; the sidecar is frozen")
    index, dates = json.loads(INDEX.read_text()), {}
    for day, arms in index["dates"].items():
        for arm, e in arms.items():
            record = json.loads((ROOT/e["campaign"]/"validation.json").read_text())
            pin = record["artifacts_sha256"][f"{e['final']}/force_model.json"]
            problems = check_model_identity(e, pin)
            assert not problems, (day, arm, problems)
            dates.setdefault(day, {})[arm] = dict(force_model=f"{e['campaign']}/{e['final']}/force_model.json",
                                                  sha256=pin)
    MODELS.write_text(json.dumps(dict(note="Expected final force models (A4 §4), from each campaign's artifact pin.",
                                      index=INDEX.relative_to(ROOT).as_posix(), index_sha256=sha(INDEX),
                                      dates=dates), indent=1)+"\n")
    print("wrote", MODELS)


if __name__ == "__main__":
    main()
