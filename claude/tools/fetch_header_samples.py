"""Guarded 32 KiB header range samples for the West Pacific shortlist, checked with Astra's
unchanged header compatibility rules. The user approved these six downloads on 11 Sep 2026.

    C:\\anaconda\\python.exe -m customkf.guard --timeout 120 -- claude.tools.fetch_header_samples

Source is the BKG IGS day-214 observation directory behind the pinned
data/stage5b/bkg-2026214-listing.html. Each request asks only for bytes 0-32767, the size of
Astra's samples. curl refuses any response over 1 MiB, so an ignored range cannot pull a full
file. Samples and headers.json go only into the guarded run directory; data/ is not touched.
The check is the one in customkf.screen_stage5b_headers: RINEX header with declared phase shifts
allowed, a supported P(Y) signal pair and an exact igs20.atx antenna/radome calibration.
A pass is a header screen only, not data availability or quality.
"""
from datetime import datetime
import gzip
import io
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np

from customkf.prepare_stage2 import ROOT, CURL, sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import header
from customkf.preprocess import choose_signals
from customkf.antenna import load_calibrations
from customkf.stage5_pilot import ORIGIN
from customkf.station_models import reference_coordinate

URL = "https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/214/"
LISTING = ROOT / "data/stage5b/bkg-2026214-listing.html"
LISTING_SHA256 = "e9917ea1a76e432adedfeeb7e9431dd4db8546bfcdc95a1da316934fa7679f40"
SCREEN = ROOT / "claude/runs/20260911T024352Z-weak-coverage-screen/coverage.json"
SCREEN_SHA256 = "b59e36d1cd204e7c93f393ccca69c52e663a60203db764dd1bd0ca44fd889585"
SHORTLIST = ("GUAM", "CCJ2", "PIMO", "MCIL", "HKSL", "POHN")
SAMPLE_BYTES = 32768


def header_lines(path):
    lines, started = [], False
    with gzip.open(path, "rt") as stream:
        for line in stream:
            if "RINEX VERSION / TYPE" in line:
                started = True
            if started:
                lines.append(line)
            if "END OF HEADER" in line:
                return lines
    raise EOFError("Sample ended before END OF HEADER")


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    (folder / "headers").mkdir()
    assert sha(LISTING) == LISTING_SHA256 and sha(SCREEN) == SCREEN_SHA256
    listing = LISTING.read_text()
    screened = {c["station"]: c for c in json.loads(SCREEN.read_text())["candidates"]}
    report = {"status": "header_range_samples_screened_not_data_acceptance", "source": URL,
              "listing_sha256": LISTING_SHA256, "coverage_screen_sha256": SCREEN_SHA256, "sample_bytes": SAMPLE_BYTES,
              "rules": "customkf.rinex.header(allow_declared_phase_shifts=True), customkf.preprocess.choose_signals, "
                       "customkf.antenna.load_calibrations(igs20.atx) exact antenna/radome", "stations": {}}
    for station in SHORTLIST:
        marker = screened[station]["marker"]
        name = f"{marker}_R_20262140000_01D_30S_MO.crx.gz"
        row = re.search(re.escape(name) + r'</a>\s*</td><td align="right">([^<]*?)\s*</td><td align="right">([^<]*?)</td>', listing)
        if not row:
            raise ValueError("Marker file not in pinned listing: " + name)
        path = folder / "headers" / f"{marker}.gz"
        entry = {"marker": marker, "url": URL + name, "listing_last_modified_server_time": row.group(1), "listing_size": row.group(2)}
        done = subprocess.run([CURL, "--fail", "--location", "--silent", "--show-error", "--max-time", "45",
                               "--max-filesize", str(2**20), "--range", f"0-{SAMPLE_BYTES - 1}",
                               "--write-out", "%{http_code} %{size_download}", URL + name, "-o", str(path)],
                              capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        entry["curl"] = {"exit_code": done.returncode, "http_code_and_bytes": done.stdout.strip(), "stderr": done.stderr.strip()}
        report["stations"][station] = entry
        if done.returncode != 0 or not path.exists():
            entry["status"] = "download_failed"
            continue
        entry.update(bytes=path.stat().st_size, range_sample_sha256=sha(path))
        if entry["bytes"] > SAMPLE_BYTES:
            raise ValueError("Server ignored the byte range: " + name)
        try:
            lines = header_lines(path)
            meta = header(io.StringIO("".join(lines)), allow_declared_phase_shifts=True)
            xyz, _ = reference_coordinate(DATA / "IGc20.ssc", DATA / "soln_IGc20.snx", station, datetime(2026, 8, 2, 12))
            entry.update(rinex_version=meta.version, marker_name=meta.marker, receiver=meta.receiver, antenna=meta.antenna,
                         antenna_hen_m=list(meta.antenna_hen), interval_s=meta.interval_s, gps_types=meta.types["G"],
                         systems=sorted(meta.types), phase_shift_records=len(meta.phase_shift_metadata),
                         first_obs=next((l[:60].strip() for l in lines if l[60:].strip() == "TIME OF FIRST OBS"), None),
                         approx_minus_igc20_m=float(np.linalg.norm(np.array(meta.approximate_xyz) - xyz)))
            pair = choose_signals(meta.types["G"])
            load_calibrations(DATA / "igs20.atx", [meta.antenna], ORIGIN)
            entry.update(status="compatible_header", pair=pair.__dict__)
        except (ValueError, EOFError, OSError) as error:
            entry.update(status="rejected", reason=str(error))
    report["tool_sha256"] = sha(Path(__file__))
    (folder / "headers.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({s: {k: v for k, v in e.items() if k not in ("url", "gps_types")} for s, e in report["stations"].items()}, indent=1), flush=True)


if __name__ == "__main__":
    main()
