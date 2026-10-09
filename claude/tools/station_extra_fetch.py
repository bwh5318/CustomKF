"""Guarded acquisition of one extra station file into Claude's own data folder.

    customkf.guard --timeout 120 -- claude.tools.station_extra_fetch --marker PIMO00PHL

Downloads the BKG day-214 observation file listed in the pinned directory listing, decodes it with
the existing pinned RNXCMP executable, and recompresses it under the project's usual name. Nothing
is written to data/, validation/ or any Astra archive: the raw and decoded files go to
claude/data/acquired/, and the guard directory keeps the decoder log and a provenance record.
The same header rules as customkf.screen_stage5b_headers are applied to the full file: RINEX
header with declared phase shifts allowed, a supported P(Y) signal pair, and an exact igs20.atx
antenna/radome match. A pass is a file-compatibility check, not data-quality acceptance.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import subprocess

from customkf.prepare_stage2 import CURL
from customkf.prepare_stage3 import DATA
from customkf.rinex import text_stream, header
from customkf.preprocess import choose_signals
from customkf.antenna import load_calibrations
from customkf.stage5_pilot import ORIGIN
from claude.tools.pinned_sources import ROOT, sha

URL = "https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/214/"
LISTING = ROOT / "data/stage5b/bkg-2026214-listing.html"
LISTING_SHA256 = "e9917ea1a76e432adedfeeb7e9431dd4db8546bfcdc95a1da316934fa7679f40"
DECODER = ROOT / "vendor/rnxcmp-4.2.0/CRX2RNX.exe"
DECODER_SHA256 = "bd8f57ce6a314764305a038816e643d9b7d8759f702197108e65fb732e7f1cca"
ACQUIRED = ROOT / "claude/data/acquired"
COMPRESSED_BUDGET = 8 * 2**20
COMPACT_BUDGET = 32 * 2**20
DECODED_BUDGET = 128 * 2**20


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", required=True)
    marker = parser.parse_args().marker
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    assert sha(LISTING) == LISTING_SHA256 and sha(DECODER) == DECODER_SHA256
    name = f"{marker}_R_20262140000_01D_30S_MO.crx.gz"
    row = re.search(re.escape(name) + r'</a>\s*</td><td align="right">([^<]*?)\s*</td><td align="right">([^<]*?)</td>',
                    LISTING.read_text())
    if not row:
        raise ValueError("Marker file not in the pinned listing: " + name)
    ACQUIRED.mkdir(parents=True, exist_ok=True)
    compressed = ACQUIRED / name
    output = ACQUIRED / name.replace(".crx.gz", ".rnx.gz")
    record = {"marker": marker, "url": URL + name, "listing_last_modified_server_time": row.group(1),
              "listing_size": row.group(2), "decoder_sha256": DECODER_SHA256,
              "already_present": compressed.exists() and output.exists()}
    if not compressed.exists():
        done = subprocess.run([CURL, "--fail", "--location", "--silent", "--show-error", "--max-time", "90",
                               "--max-filesize", str(COMPRESSED_BUDGET), "--write-out", "%{http_code} %{size_download}",
                               URL + name, "-o", str(compressed)], capture_output=True, text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        record["curl"] = {"exit_code": done.returncode, "http_code_and_bytes": done.stdout.strip(), "stderr": done.stderr.strip()}
        if done.returncode != 0 or not compressed.exists():
            raise RuntimeError("Download failed: " + done.stderr.strip())
    record.update(compressed_bytes=compressed.stat().st_size, compressed_sha256=sha(compressed))
    if not output.exists():
        compact = folder / "input.crx"
        with gzip.open(compressed, "rb") as source, compact.open("wb") as target:
            count = 0
            while block := source.read(65536):
                count += len(block)
                if count > COMPACT_BUDGET:
                    raise ValueError("Compact byte budget exceeded")
                target.write(block)
        record["compact_bytes"] = count
        with compact.open("rb") as source, (folder / f"{marker}_decoder.log").open("wb") as error:
            child = subprocess.Popen([str(DECODER)], stdin=source, stdout=subprocess.PIPE, stderr=error,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                count = 0
                with gzip.open(output.with_suffix(".part"), "wb", compresslevel=1) as target:
                    while block := child.stdout.read(65536):
                        count += len(block)
                        if count > DECODED_BUDGET:
                            raise ValueError("Decoded byte budget exceeded")
                        target.write(block)
                if child.wait(timeout=10) != 0:
                    raise ValueError("Decoder failed")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        compact.unlink()
        output.with_suffix(".part").replace(output)
        record["decoded_bytes"] = count
    record.update(decoded_path=output.relative_to(ROOT).as_posix(), decoded_bytes_on_disk=output.stat().st_size,
                  decoded_sha256=sha(output))
    with text_stream(output) as stream:
        meta = header(stream, allow_declared_phase_shifts=True)
    pair = choose_signals(meta.types["G"])
    load_calibrations(DATA / "igs20.atx", [meta.antenna], ORIGIN)
    record.update(status="full_file_header_signals_and_calibration_passed", rinex_version=meta.version,
                  marker_name=meta.marker, receiver=meta.receiver, antenna=meta.antenna,
                  antenna_hen_m=list(meta.antenna_hen), interval_s=meta.interval_s,
                  phase_shift_records=len(meta.phase_shift_metadata), signal_pair=pair.__dict__,
                  systems=sorted(meta.types), tool_sha256=sha(Path(__file__)))
    (folder / "acquisition.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "curl"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
