"""Write deliverables/sp3/README.md from the exported SP3 files and their export records (no computation).

    C:\\anaconda\\python.exe -m deliverables.manifest
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = {
    "default_25st": "Best rapid-candidate configuration: the adopted default (ECOM5, Earth radiation and antenna thrust, "
                    "IERS 2010 sub-daily EOP, elevation weighting), 25 stations, no tropospheric gradients. Inputs are "
                    "plausibly rapid, but these files were made retrospectively.",
    "S17_nga_like": "17 stations placed like NGA's monitor network (network test S17), default + TU Wien GRAD "
                    "operational gradients. Final latency.",
    "S50_doubled": "50 stations (network test S50, ambiguity elimination), default + TU Wien GRAD operational "
                   "gradients. Final latency.",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    (HERE/"sp3").mkdir(parents=True, exist_ok=True)
    lines = ["# SP3 orbit files", "",
             "Exported with `Opus_Fork.export write` (model-aware frame, QA re-read of every position; "
             "`deliverables/make_sp3.sh`). GPS satellite centre of mass, IGc20, GPS time, 15-minute cadence, positions "
             "only (clocks are the missing value 999999.999999), accuracy codes 0 (unknown). `RAP`/`FIN` in a name is "
             "this project's local category, not an IGS product class. The SP3 files are not in git.", ""]
    for name, text in SETS.items():
        files = sorted((HERE/"sp3"/name).glob("*.SP3"))
        lines += [f"## {name}", "", text, ""]
        if not files:
            lines += ["Not exported yet.", ""]
            continue
        lines += ["| File | SHA-256 | Source solution | QA |", "|---|---|---|---|"]
        for f in files:
            record = json.loads(f.with_suffix(".export.json").read_text()) if f.with_suffix(".export.json").exists() else {}
            source = Path(record.get("source_solution", "?"))
            lines.append(f"| `{f.name}` | `{sha(f)[:16]}…` | `{source.parent.parent.name}/{source.parent.name}` | "
                         f"{'passed' if record.get('passed') else '?'} |")
        lines.append("")
    (HERE/"sp3"/"README.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("wrote", HERE/"sp3"/"README.md")


if __name__ == "__main__":
    main()
