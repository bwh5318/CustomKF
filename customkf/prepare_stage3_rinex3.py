"""Project-local official Hatanaka decoder and original station RINEX 3 data.

The decoder was discussed with the user before their instruction to continue.
No PATH, package-manager, registry or system installation changes are made.
"""
from datetime import datetime,timezone
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from .prepare_stage3 import DATA,fetch
from .prepare_stage2 import ROOT,sha


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    run=Path(os.environ["CUSTOMKF_RUN_DIR"])
    vendor=ROOT/"vendor/rnxcmp-4.2.0";vendor.mkdir(parents=True,exist_ok=True)
    archive=DATA/"RNXCMP_4.2.0_Windows_mingw_64bit.zip"
    if not archive.exists():
        fetch("https://terras.gsi.go.jp/ja/crx2rnx/"+archive.name,archive.name,2**20)
    if sha(archive)!="58080794cda5a14d7088b921fd75728257e70182d242573e6926d7f8efaa3eae":
        raise ValueError("Official decoder package differs from approved pinned version")
    exe=vendor/"CRX2RNX.exe"
    with zipfile.ZipFile(archive) as z:
        member="RNXCMP_4.2.0_Windows_mingw_64bit/CRX2RNX.exe"
        if z.getinfo(member).file_size>2**20:raise ValueError("Unexpected decoder executable size")
        payload=z.read(member)
        if exe.exists() and exe.read_bytes()!=payload:raise ValueError("Existing decoder differs from pinned package")
        if not exe.exists():exe.write_bytes(payload)
    metadata={"name":"GSI RNXCMP 4.2.0 Windows 64-bit CRX2RNX","retrieved_utc":datetime.now(timezone.utc).isoformat(),
        "source":"https://terras.gsi.go.jp/ja/crx2rnx/RNXCMP_4.2.0_Windows_mingw_64bit.zip",
        "package_sha256":sha(archive),"exe_sha256":sha(exe),"exe_bytes":exe.stat().st_size,
        "scope":"Project-local file decompression only; never estimates orbits or station coordinates"}
    for name in ("LICENSE.txt","README.txt"):
        entry=fetch("https://terras.gsi.go.jp/ja/crx2rnx/"+name,"RNXCMP_"+name,2**20)
        shutil.copyfile(ROOT/entry["path"],vendor/name)
    (vendor/"provenance.json").write_text(json.dumps(metadata,indent=2)+"\n")
    manifest=DATA/"rinex3_manifest.json"
    entries=json.loads(manifest.read_text())["files"] if manifest.exists() else []
    for entry in entries:
        if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Pinned RINEX 3 input changed")
    for station in ("BRUX00BEL","KOUR00GUF","HOB200AUS"):
        name=f"{station}_R_20262140000_01D_30S_MO.crx.gz"
        if not any(e["path"].endswith(name) for e in entries):
            entries.append(fetch("https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/214/"+name,name))
        output=DATA/name.replace(".crx.gz",".rnx.gz")
        if not any(e["path"].endswith(output.name) for e in entries):
            compact=run/"input.crx"
            with gzip.open(DATA/name,"rb") as source,compact.open("wb") as target:
                total=0
                while block:=source.read(65536):
                    total+=len(block)
                    if total>32*2**20:raise ValueError("Compact text exceeds 32 MiB")
                    target.write(block)
            with compact.open("rb") as source,(run/"decoder_stderr.log").open("wb") as errors:
                worker=subprocess.Popen([str(exe)],stdin=source,stdout=subprocess.PIPE,stderr=errors,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    total=0
                    with gzip.open(output.with_suffix(".part"),"wb",compresslevel=1) as target:
                        while block:=worker.stdout.read(65536):
                            total+=len(block)
                            if total>128*2**20:raise ValueError("Decoded RINEX exceeds 128 MiB")
                            target.write(block)
                    if worker.wait(timeout=5)!=0:raise RuntimeError("CRX2RNX failed; inspect decoder_stderr.log")
                finally:
                    if worker.poll() is None:worker.kill();worker.wait(timeout=5)
            compact.unlink()
            output.with_suffix(".part").replace(output)
            with gzip.open(output,"rt") as stream:
                first=stream.readline()
                if "RINEX VERSION / TYPE" not in first:raise ValueError("Decoder did not produce RINEX")
                print(station+": "+first.rstrip(),flush=True)
            entries.append({"path":output.relative_to(ROOT).as_posix(),"sha256":sha(output),"bytes":output.stat().st_size,
                            "decoded_bytes":total,"source":name,"decoder_sha256":sha(exe),
                            "transformation":"gzip decode; official CRX2RNX; recompress ordinary RINEX with gzip level 1"})
        manifest.write_text(json.dumps({"decoder":metadata,"files":entries},indent=2)+"\n")


if __name__=="__main__":main()
