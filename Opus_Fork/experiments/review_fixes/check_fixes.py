"""Checks for the 27 Sep review fixes (results/CORRECTIONS.md: C01, N03, M12). Run under the guard, no campaign running.

    ... -- Opus_Fork.experiments.review_fixes.check_fixes

1. C01/N03 export: `export.selftest` (now including a noon-start file that must pass and a mislabelled header that must
   be caught). Then `export.roundtrip` over the five SD solutions and one plain solution (P1). For SD, the model-aware
   export must match the scoring path to SP3 quantization, and the forced plain-EOP negative control must NOT. For P1
   both must match.
2. M12 prepare: merge the Aug 2 navigation pair into two fresh temporary paths at different wall times. The bytes
   must be identical. Merging into the existing store file must leave it byte-for-byte unchanged. A conflicting
   existing file must be refused.
Writes check_fixes.json in the run folder and results/review_fixes_check.json.
"""
import argparse
import gzip
import json
import os
import shutil
import time
from pathlib import Path

R = "Opus_Fork/runs/"
SD = [
    (R+"20260925T183701Z-fit-SD-2-25st/lin2-solve", R+"20260920T200910Z-prepare-31sat/fixture.json", "2026-08-02"),
    (R+"20260925T193347Z-fit-SD-7-25st/lin4-solve", "runs/20260920T155655Z-7b703635/fixture.json", "2026-08-07"),
    (R+"20260925T215927Z-fit-SD-3-25st/lin2-solve", R+"20260922T225652Z-prepare-2026-08-03/fixture.json", "2026-08-03"),
    (R+"20260925T225732Z-fit-SD-4-25st/lin2-solve", R+"20260922T230119Z-prepare-2026-08-04/fixture.json", "2026-08-04"),
    (R+"20260926T025926Z-fit-SD-5-25st/lin2-solve", R+"20260922T230410Z-prepare-2026-08-05/fixture.json", "2026-08-05"),
]
PLAIN = (R+"20260922T205445Z-fit-P1-erp-31sat/lin2-solve", R+"20260920T200910Z-prepare-31sat/fixture.json", "2026-08-02")


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    from Opus_Fork import export, prepare
    from Opus_Fork.paths import RESULTS, ROOT
    from customkf.prepare_stage2 import sha
    report = {}

    (folder/"selftest").mkdir()
    report["export_selftest"] = export.selftest(argparse.Namespace(), folder/"selftest")
    print("export selftest passed:", report["export_selftest"]["passed"],
          "| partial-day passes:", report["export_selftest"]["partial_day_passes"],
          "| mislabelled header caught:", report["export_selftest"]["mislabelled_header_caught"], flush=True)

    (folder/"roundtrip").mkdir()
    pairs = ["::".join(p) for p in SD+[PLAIN]]
    report["export_roundtrip"] = export.roundtrip(argparse.Namespace(pairs=pairs), folder/"roundtrip")

    # M12: navigation merge determinism and no-overwrite.
    fixture = json.loads((ROOT/R/"20260920T200910Z-prepare-31sat/fixture.json").read_text())
    store_merged = ROOT/fixture["context"]["navigation_path"]
    stamp_prev, stamp = "2026213", "2026214"
    available = prepare.input_map("2026-08-02", "2026-08-01")
    prev = Path(available[f"BRDC00WRD_R_{stamp_prev}0000_01D_MN.rnx.gz"][0])
    cur = Path(available[f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"][0])
    a, b = folder/"nav_a.rnx.gz", folder/"nav_b.rnx.gz"
    ca = prepare.merge_navigation(prev, cur, a)
    time.sleep(2)
    prepare.merge_navigation(prev, cur, b)
    m12 = dict(bytes_identical_across_runs=a.read_bytes() == b.read_bytes(), conflicts=ca[3], records_kept=ca[0])
    with gzip.open(a, "rb") as fa, gzip.open(store_merged, "rb") as fs:
        m12["store_file_content_equals_fresh_merge"] = fa.read() == fs.read()
    before = sha(store_merged)
    copy = folder/"store_copy.rnx.gz"
    shutil.copyfile(store_merged, copy)
    prepare.merge_navigation(prev, cur, copy)      # existing file with same content: must be kept as is
    m12["existing_same_content_kept_byte_for_byte"] = sha(copy) == before
    bad = folder/"conflict.rnx.gz"
    with gzip.open(bad, "wb") as g:
        g.write(b"not the same content\n")
    try:
        prepare.merge_navigation(prev, cur, bad)
        m12["conflicting_existing_refused"] = False
    except ValueError:
        m12["conflicting_existing_refused"] = True
    m12["store_file_untouched"] = sha(store_merged) == before
    report["prepare_nav"] = m12
    print("nav merge:", m12, flush=True)

    report["passed"] = bool(report["export_selftest"]["passed"] and report["export_roundtrip"]["passed"]
                            and m12["bytes_identical_across_runs"] and m12["existing_same_content_kept_byte_for_byte"]
                            and m12["conflicting_existing_refused"] and m12["store_file_untouched"])
    text = json.dumps(report, indent=1, default=str)+"\n"
    (folder/"check_fixes.json").write_text(text)
    (RESULTS/"review_fixes_check.json").write_text(text)
    print("ALL PASSED" if report["passed"] else "SOME CHECK FAILED", flush=True)


if __name__ == "__main__":
    main()
