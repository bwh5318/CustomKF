"""Acquire three public station files, using the already authorized pinned decoder.

Run through customkf.guard. No installation or new executable is downloaded.
"""
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import subprocess
from .prepare_stage2 import ROOT, sha
from .prepare_stage3 import DATA, fetch

MARKERS = ("DJIG00DJI", "NNOR00AUS", "MAS100ESP")


def main(*, markers=MARKERS, manifest_name="stage4_manifest.json", allow_phase_shift_metadata=False):
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    if manifest_name not in ("stage4_manifest.json","stage5b_manifest.json"):
        raise ValueError("Unsupported input-manifest destination")
    manifest = DATA / manifest_name
    entries = json.loads(manifest.read_text())["files"] if manifest.exists() else []
    for entry in entries:
        if sha(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError("Changed Stage 4 input")
    exe = ROOT / "vendor/rnxcmp-4.2.0/CRX2RNX.exe"
    if sha(exe) != "bd8f57ce6a314764305a038816e643d9b7d8759f702197108e65fb732e7f1cca":
        raise ValueError("Decoder changed")

    def save():
        manifest.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": ("Stage 5b station screening and multi-hour network diagnostics; retrospective inputs, not a rapid-vintage replay"
                        if manifest_name=="stage5b_manifest.json" else "Eight-station short-arc algebra audit; retrospective inputs, not a rapid-vintage replay"),
            "files": entries}, indent=2) + "\n")

    for marker in markers:
        name = f"{marker}_R_20262140000_01D_30S_MO.crx.gz"
        if not any(e["path"] == f"data/stage3/{name}" for e in entries):
            entries.append(fetch("https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/214/" + name, name))
            save()
        output = DATA / name.replace(".crx.gz", ".rnx.gz")
        if any(e["path"] == output.relative_to(ROOT).as_posix() for e in entries):
            continue
        compact = folder / "input.crx"
        with gzip.open(DATA / name, "rb") as source, compact.open("wb") as target:
            count = 0
            while block := source.read(65536):
                count += len(block)
                if count > 32 * 2**20:
                    raise ValueError("Compact byte budget exceeded")
                target.write(block)
        with compact.open("rb") as source, (folder / f"{marker}_decoder.log").open("wb") as err:
            child = subprocess.Popen([str(exe)], stdin=source, stdout=subprocess.PIPE, stderr=err,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                count = 0
                with gzip.open(output.with_suffix(".part"), "wb", compresslevel=1) as target:
                    while block := child.stdout.read(65536):
                        count += len(block)
                        if count > 128 * 2**20:
                            raise ValueError("Decoded byte budget exceeded")
                        target.write(block)
                if child.wait(timeout=5) != 0:
                    raise ValueError("Decoder failed")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        compact.unlink()
        output.with_suffix(".part").replace(output)
        entries.append({"path": output.relative_to(ROOT).as_posix(), "bytes": output.stat().st_size,
                        "decoded_bytes": count, "sha256": sha(output), "source": name,
                        "decoder_sha256": sha(exe)})
        save()
        # The strict parser checks date-specific phase-shift and signal compatibility.
        from .rinex import text_stream, header
        from .preprocess import choose_signals
        with text_stream(output) as source:
            meta = header(source,allow_declared_phase_shifts=allow_phase_shift_metadata)
        print(marker, meta.receiver, meta.antenna, choose_signals(meta.types["G"]), flush=True)


if __name__ == "__main__":
    main()
