"""Bench data helpers (roadmap step 4): reference products and input manifests for any day.

Products for days already in data/stage3 are read from there (pinned in data/stage3/manifest.json);
days acquired by claude.roadmap.fetch_day live in claude/data/day<DOY>/ with a per-file JSON record.

    manifest: python -m customkf.guard -- claude.roadmap.bench_data manifest --day 2026-08-04 --markers M1,M2,...
              writes claude/data/day<DOY>/inputs.json (station RINEX + BRDC) for long_prepare --inputs.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from customkf.prepare_stage2 import ROOT, sha
from customkf.prepare_stage3 import DATA
from claude.roadmap.common import DatedReference, write_json


def day_folder(day):
    return ROOT/"claude/data"/("day"+datetime.strptime(day, "%Y-%m-%d").strftime("%j"))


def verified(path):
    """Return path if pinned either in data/stage3 manifests or by a fetch_day record."""
    path = Path(path)
    relative = path.relative_to(ROOT).as_posix()
    for manifest in DATA.glob("*manifest.json"):
        for entry in json.loads(manifest.read_text()).get("files", []):
            if entry["path"] == relative:
                if sha(path) != entry["sha256"]:
                    raise ValueError("Changed pinned input: "+relative)
                return path
    for record in path.parent.glob("*.json"):
        data = json.loads(record.read_text())
        for entry in data.get("files", []) if isinstance(data, dict) else []:
            if entry.get("path") == relative:
                if sha(path) != entry["sha256"]:
                    raise ValueError("Changed acquired input: "+relative)
                return path
    raise ValueError("Unpinned input: "+relative)


class BenchReference(DatedReference):
    """DatedReference that also accepts an IGS rapid SP3 acquired into claude/data/day<DOY>/."""
    def __init__(self, day, origin_ns):
        stamp = datetime.strptime(day, "%Y-%m-%d").strftime("%Y%j")
        name = f"IGS0OPSRAP_{stamp}0000_01D_15M_ORB.SP3.gz"
        if (DATA/name).exists():
            return super().__init__(day, origin_ns)
        from customkf.frames import FrameEpoch, EarthOrientation
        from customkf.precise import PreciseProducts
        from customkf.sp3 import read_sp3
        from customkf.prepare_stage2 import DATA as DYN
        path = verified(day_folder(day)/name)
        self.path, self.sha256, self.origin = path, sha(path), int(origin_ns)
        self.epoch = FrameEpoch(self.origin, EarthOrientation(DYN/"finals2000A.all"))
        self.precise = PreciseProducts([path], [], self.origin, self.epoch.eop)
        self.raw = read_sp3(path)
        if self.raw.frame != "IGc20":
            raise ValueError("Unexpected reference frame")


def manifest(args, run):
    folder = day_folder(args.day)
    stamp = datetime.strptime(args.day, "%Y-%m-%d").strftime("%Y%j")
    files = []
    for marker in args.markers.split(","):
        name = f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz"
        path = DATA/name if (DATA/name).exists() else folder/name
        verified(path)
        files.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), bytes=path.stat().st_size))
    brdc = f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"
    path = DATA/brdc if (DATA/brdc).exists() else folder/brdc
    verified(path)
    files.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), bytes=path.stat().st_size))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/"inputs.json"
    if target.exists():
        old = json.loads(target.read_text())
        if old["files"] != files:
            raise ValueError("Existing inputs.json differs; refusing to overwrite: "+str(target))
    else:
        write_json(target, dict(files=files))
    write_json(Path(os.environ["CUSTOMKF_RUN_DIR"])/"inputs.json", dict(path=target.relative_to(ROOT).as_posix(), sha256=sha(target), files=files))
    print(target, len(files), "files", flush=True)


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("manifest",))
    parser.add_argument("--day", required=True)
    parser.add_argument("--markers", required=True)
    args = parser.parse_args()
    manifest(args, None)


if __name__ == "__main__":
    main()
