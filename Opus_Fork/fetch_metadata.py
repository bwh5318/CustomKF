"""Acquire the IGS satellite metadata SINEX into the store, with a sidecar provenance record.

    C:\\anaconda\\python.exe -m Opus_Fork.guard --profile fork8 --timeout 300 --label fetch-satmeta \
        -- Opus_Fork.fetch_metadata

The file (`igs_satellite_metadata.snx`) is the IGS-maintained table of GNSS satellite
identifiers, launch/decommission dates, masses, transmit powers, antenna offsets and
body/panel dimensions. It is a static, versioned public input, so it is rapid-legal: nothing
in it depends on the day being processed.

Its purpose here is test T2.1 in `results/URE_REVIEW_AND_TEST_PLAN.md`: physical Earth
radiation pressure and antenna thrust need per-satellite mass, transmit power and dimensions.
It is an estimation-side static input, not a reference product. Nothing in it is fitted to or
derived from an IGS orbit.

Written to `datastore/static/` with a `.json` sidecar (source URL, retrieval time, SHA-256,
bytes, header lines). An existing file is hash-verified against its sidecar and never
silently replaced. Mirrors are tried in a fixed declared order; which one answered is
recorded.
"""
from datetime import datetime, timezone
import json
import subprocess

from customkf.prepare_stage2 import CURL, sha

from .paths import STORE

NAME = "igs_satellite_metadata.snx"
MIRRORS = ("https://files.igs.org/pub/station/general/"+NAME,
           "https://igs.bkg.bund.de/root_ftp/IGS/station/general/"+NAME)
LIMIT = 16*2**20


def main():
    folder = STORE/"static"
    folder.mkdir(parents=True, exist_ok=True)
    target, record = folder/NAME, folder/(NAME+".json")
    if target.exists():
        meta = json.loads(record.read_text())
        if sha(target) != meta["sha256"]:
            raise ValueError("Stored metadata no longer matches its sidecar hash; not replacing it")
        print("Already acquired and verified:", target, meta["sha256"])
        return
    errors = []
    for url in MIRRORS:
        part = folder/(NAME+".part")
        done = subprocess.run([CURL, "--fail", "--location", "--silent", "--show-error",
                               "--max-time", "120", "--max-filesize", str(LIMIT), url, "-o", str(part)],
                              capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if done.returncode or not part.exists():
            errors.append(dict(url=url, error=done.stderr.strip()))
            part.unlink(missing_ok=True)
            continue
        text = part.read_text(encoding="ascii", errors="strict")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("%=SNX") or "+SATELLITE/IDENTIFIER" not in text:
            errors.append(dict(url=url, error="Not a satellite metadata SINEX"))
            part.unlink()
            continue
        part.replace(target)
        meta = dict(role="static_satellite_metadata", source_url=url,
                    retrieved_utc=datetime.now(timezone.utc).isoformat(),
                    sha256=sha(target), bytes=target.stat().st_size, header=lines[0],
                    blocks=sorted({l.split()[0] for l in lines if l.startswith("+")}),
                    failed_mirrors=errors,
                    use="Estimation-side static input for physical ERP/antenna-thrust modelling (T2.1). "
                        "Not a reference product; no orbit information.")
        record.write_text(json.dumps(meta, indent=2)+"\n")
        print(json.dumps(meta, indent=2))
        return
    raise RuntimeError("All mirrors failed: "+json.dumps(errors))


if __name__ == "__main__":
    main()
