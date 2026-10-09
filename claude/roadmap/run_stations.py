"""Direct serial controller for network expansion (roadmap step 5, STATION_EXPANSION_PROTOCOL.md).

    C:\\anaconda\\python.exe -m claude.roadmap.run_stations --step2 DIR --bench DIR

Screen (listing, 8 header batches, geometry) -> download the 11 added stations for 2 August -> 25-station input
manifest -> 6 h block-fixed fit (N6) and the bench's L* configuration (NL) -> evaluation against the 14-station arms.
Runs no numerics itself. A failed station download is replaced by the next-ranked alternative from the same greedy
step (the protocol's only allowed substitution, disclosed). L* at 24 h falls back to 12 h if the unchanged 256 MiB
streaming preflight refuses the 25-station system.
"""
import argparse
import json
import os
from pathlib import Path
from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.run_roadmap import Stage, check_idle, chunk_for, CONFIGS, latest_converged, AUG2_DATED, BLOCK_CAMPAIGN
from claude.roadmap.long_prepare import STATIONS

DAY = "2026-08-02"
PROTOCOL = "claude/roadmap/STATION_EXPANSION_PROTOCOL.md"
BASE_LINKS_6H = 4731
ARM_CONFIG = {"12h-FB": ("block-fixed.json", 0), "12h-D0": ("unit-d0.json", 1), "12h-FU": ("unit-fixed.json", 0), "12h-E5": ("unit-ecom5.json", 5),
              "24h-FB": ("block-fixed.json", 0), "24h-D0": ("unit-d0.json", 1), "24h-E5": ("unit-ecom5.json", 5)}


def scaled(g2d, count, epochs, links_ratio):
    """chunk_for with per-epoch cost scaled by the link ratio (plus 20% for the larger retained dimension)."""
    scaled_g2d = dict(g2d, max_chunk_seconds_per_epoch=g2d["max_chunk_seconds_per_epoch"]*links_ratio*1.2)
    return chunk_for(scaled_g2d, count, epochs, cached=True)


def final_of(campaign):
    manifest = json.loads((Path(campaign)/"validation.json").read_text())
    if manifest.get("status") != "long_fit_complete_not_accuracy_acceptance" or not manifest.get("final"):
        return None
    return Path(campaign)/manifest["final"], ROOT/manifest["fixture"]


def main():
    assert not os.environ.get("CUSTOMKF_RUN_DIR"), "Run directly"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2", required=True)
    parser.add_argument("--bench", required=True, help="completed bench stage folder (for the chosen L*)")
    parser.add_argument("--add", type=int, default=11)
    args = parser.parse_args()
    check_idle()
    g2d = json.loads((Path(args.step2)/"stage.json").read_text())["gates"]["G2d"]
    bench = json.loads((Path(args.bench)/"stage.json").read_text())
    lstar = bench["lstar"]["label"]
    stage = Stage("stations")
    stage.report.update(protocol=PROTOCOL, protocol_sha256=sha(ROOT/PROTOCOL), lstar=lstar)
    try:
        stage.guard("screen-listing", ["claude.roadmap.station_screen", "listing", "--day", DAY], 120)
        for i in range(8):
            stage.guard(f"screen-headers-{i}", ["claude.roadmap.station_screen", "headers", "--day", DAY, "--batch", str(i), "--batches", "8"], 300)
        geometry_dir = stage.guard("screen-geometry", ["claude.roadmap.station_screen", "geometry", "--day", DAY, "--add", str(args.add)], 300)
        geometry = json.loads((geometry_dir/"geometry.json").read_text())
        added, replacements = [], []
        for step in geometry["steps"][1:]:
            options = [(step["selected"], step["marker"])] + [(a["station"], None) for a in step["alternatives"] if a["station"] != step["selected"]]
            chosen = None
            for station, marker in options:
                if station in STATIONS or any(station == s for s, _ in added):
                    continue
                if marker is None:
                    marker = next((m for m in json.loads((ROOT/"claude/data/screen214/candidates.json").read_text())["markers"] if m[:4] == station), None)
                    if marker is None:
                        continue
                try:
                    stage.guard(f"fetch-{marker}", ["claude.roadmap.fetch_day", "station", "--day", DAY, "--marker", marker], 180)
                    chosen = (station, marker)
                    break
                except RuntimeError as error:
                    replacements.append(dict(failed=station, marker=marker, error=str(error)))
            if chosen is None:
                raise RuntimeError("No downloadable station for greedy step "+str(step["selected"]))
            added.append(chosen)
        stage.report.update(added_stations=added, download_replacements=replacements)
        stage.save()
        names = list(STATIONS)+[s for s, _ in added]
        markers = [STATIONS[s] for s in STATIONS]+[m for _, m in added]
        extra = ",".join(f"{s}={m}" for s, m in added)
        stage.guard("manifest-day214", ["claude.roadmap.bench_data", "manifest", "--day", DAY, "--markers", ",".join(markers)], 120)
        inputs = str(ROOT/"claude/data/day214/inputs.json")
        common = ["claude.roadmap.long_prepare", "--day", DAY, "--stations", ",".join(names), "--extra-stations", extra, "--inputs", inputs]
        six = stage.guard("prepare-25-6h", [*common, "--start", "12:00", "--epochs", "37"], 300)
        ratio = json.loads((six/"step.json").read_text())["links"]/BASE_LINKS_6H
        stage.report["links_ratio_vs_14"] = ratio
        n6 = final_of(stage.long("N6-25st", six, f"{CONFIGS}/block-fixed.json", scaled(g2d, 0, 37, ratio), 4, 1))
        if n6 is None:
            raise RuntimeError("N6 did not converge")
        config, count = ARM_CONFIG[lstar]
        nl, used = None, lstar
        tries = [("24h", "00:00", 144, 6, 2), ("12h", "12:00", 72, 4, 1)] if lstar.startswith("24h") else [("12h", "12:00", 72, 4, 1)]
        for arc, start, epochs, cap, groups in tries:
            prep = stage.guard(f"prepare-25-{arc}", [*common, "--start", start, "--epochs", str(epochs)], 300)
            try:
                nl = final_of(stage.long(f"NL-25st-{arc}", prep, f"{CONFIGS}/{config}", scaled(g2d, count, epochs, ratio), cap, groups))
            except RuntimeError as error:
                stage.report.setdefault("nl_failures", []).append(dict(arc=arc, error=str(error)))
                stage.save()
                continue
            if nl is not None:
                used = arc+lstar[3:]
                break
        stage.report["nl_configuration_used"] = used
        stage.save()
        fb6 = (ROOT/BLOCK_CAMPAIGN/"B-02-linear-1", ROOT/AUG2_DATED/"fixture.json")
        stage.guard("evaluate-N6", ["claude.roadmap.long_evaluate", "--day", DAY, "--out-name", "N6_vs_FB6", "--baseline", "FB6",
                                    "--arm", "FB6", str(fb6[0]), str(fb6[1]), "--arm", "N6", str(n6[0]), str(n6[1]),
                                    "--domain", "S6", "12:00", "18:00"], 300)
        if nl is not None:
            base = latest_converged(used)
            window = ("00:00", "23:45") if used.startswith("24h") else ("12:00", "23:45")
            stage.guard("evaluate-NL", ["claude.roadmap.long_evaluate", "--day", DAY, "--out-name", "NL_vs_14", "--baseline", "L14",
                                        "--arm", "L14", str(base[0]), str(base[1]), "--arm", "NL", str(nl[0]), str(nl[1]),
                                        "--domain", "arc", *window, "--domain", "S6", "12:00", "18:00"], 300)
        stage.report["status"] = "station_expansion_complete_not_accuracy_acceptance"
    except BaseException as error:
        stage.report.update(status="failed", error=repr(error))
        raise
    finally:
        stage.save()


if __name__ == "__main__":
    main()
