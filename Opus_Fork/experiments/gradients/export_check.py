"""Export check for the adopted optional gradient model (user decision, 3 Oct 2026).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.gradients.export_check

For each option-A date the converged V-op (GRAD operational) solution goes through `Opus_Fork.export.roundtrip`:
- a model-aware export, rebuilt independently through the scoring path;
- the forced plain-EOP negative control, which must not match.

The model-aware file's header must also name the gradient model and the final latency class. Writes
`export_check.json` and the SP3 files in the run folder only: nothing goes to the product store or Opus_Fork/results.
"""
import argparse
import json

from Opus_Fork import export
from Opus_Fork.experiments.gradients.analyze_validation import DATES, ROOT, campaign
from Opus_Fork.experiments.transfer.common import run_dir

REQUIRED = export.GRADIENT_LABELS["grad_op"][0]+["RETROSPECTIVE INPUTS: NOT A LATENCY-CERTIFIED PRODUCT"]


def main():
    folder = run_dir()
    pairs = []
    for tag, (day, fixture_dir, _) in DATES.items():
        arm = campaign(f"V-op-{tag}")
        final = json.loads((arm/"validation.json").read_text())["final"]
        pairs.append(f"{arm/final}::{ROOT/fixture_dir/'fixture.json'}::{day}")
    result = export.roundtrip(argparse.Namespace(pairs=pairs), folder)
    for case in result["cases"]:
        day = case["day"].replace("-", "")
        files = sorted(folder.glob(f"roundtrip_{day}_*.SP3"))
        comments = [line[3:].rstrip() for line in files[0].read_text().splitlines() if line.startswith("/* ")] if files else []
        case["header_comments"] = comments
        case["labels_present"] = all(text in comments for text in REQUIRED)
        print(day, "labels present", case["labels_present"], flush=True)
    result["labels_present"] = all(c["labels_present"] for c in result["cases"])
    result["passed"] = bool(result["passed"] and result["labels_present"])
    (folder/"export_check.json").write_text(json.dumps(result, indent=1, default=float)+"\n")
    if not result["passed"]:
        raise SystemExit("export check failed")


if __name__ == "__main__":
    main()
