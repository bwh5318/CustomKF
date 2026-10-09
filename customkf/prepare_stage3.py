"""Bounded Stage 3 public input acquisition; no package installation."""
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import subprocess
from .prepare_stage2 import ROOT, CURL, sha

DATA=ROOT/"data/stage3"


def fetch(url,name,limit=16*2**20):
    destination=DATA/name
    if not destination.exists():
        part=destination.with_suffix(destination.suffix+".part")
        subprocess.run([CURL,"--fail","--location","--silent","--show-error","--max-time","45",
                        "--max-filesize",str(limit),url,"-o",str(part)],check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        if part.stat().st_size>limit:raise ValueError("Input byte budget exceeded")
        part.replace(destination)
    if destination.stat().st_size>limit:raise ValueError("Existing input exceeds byte budget")
    return {"url":url,"path":destination.relative_to(ROOT).as_posix(),"bytes":destination.stat().st_size,"sha256":sha(destination)}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    DATA.mkdir(parents=True,exist_ok=True)
    manifest=DATA/"manifest.json"
    entries=json.loads(manifest.read_text())["files"] if manifest.exists() else []
    for entry in entries:
        if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Pinned Stage 3 input changed")
    requests=[("https://noaa-cors-pds.s3.amazonaws.com/rinex/2026/214/gode/gode2140.26o.gz","gode2140.26o.gz"),
              ("https://noaa-cors-pds.s3.amazonaws.com/rinex/2026/214/wes2/wes22140.26o.gz","wes22140.26o.gz"),
              ("https://noaa-cors-pds.s3.amazonaws.com/rinex/2026/214/guug/guug2140.26o.gz","guug2140.26o.gz"),
              ("https://files.igs.org/pub/station/coord/IGc20/IGc20.ssc","IGc20.ssc"),
              ("https://files.igs.org/pub/station/coord/IGc20/soln_IGc20.snx","soln_IGc20.snx"),
              ("https://files.igs.org/pub/station/coord/IGc20/psd_IGc20.snx","psd_IGc20.snx"),
              ("https://files.igs.org/pub/station/general/igs20.atx","igs20.atx")]
    for day in (213,214,215):
        week=2429 if day==213 else 2430
        for suffix in ("15M_ORB.SP3.gz","05M_CLK.CLK.gz"):
            name=f"IGS0OPSRAP_2026{day}0000_01D_{suffix}"
            requests.append((f"https://igs.bkg.bund.de/root_ftp/IGS/products/{week}/{name}",name))
    requests.append(("https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2026/214/BRDC00WRD_R_20262140000_01D_MN.rnx.gz",
                     "BRDC00WRD_R_20262140000_01D_MN.rnx.gz"))
    for url,name in requests:
        if any(e["path"]==f"data/stage3/{name}" for e in entries):continue
        entry=fetch(url,name,64*2**20 if name.endswith('.atx') else 16*2**20)
        entries.append(entry)
        manifest.write_text(json.dumps({"retrieved_utc":datetime.now(timezone.utc).isoformat(),"files":entries,
            "purpose":"Stage 3 fixed-orbit observation-model development; arrival-vintage certification is a later gate"},indent=2)+"\n")
        print(f"Pinned {name}: {entry['bytes']} bytes",flush=True)
        if name.endswith("o.gz"):
            with gzip.open(DATA/name,"rt") as stream:
                for line in stream:
                    if "END OF HEADER" in line:break
                    if any(label in line for label in ("RINEX VERSION","REC #","ANT #","APPROX POSITION","# / TYPES OF OBSERV","SYS / # / OBS TYPES")):
                        print(line.rstrip(),flush=True)
    support=DATA/"support_manifest.json"
    if support.exists():
        for entry in json.loads(support.read_text())["files"]:
            if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Pinned supporting input changed")
    else:
        entry=fetch("https://download.aiub.unibe.ch/BSWUSER54/REF/FES2014b.BLQ","FES2014b.BLQ")
        entry["interpretation"]="FES2014b; 11 major constituents; CMC:NO; radial/west/south; Greenwich phase lag"
        dynamic=json.loads((ROOT/"data/stage2/manifest.json").read_text())["files"]
        support.write_text(json.dumps({"created_utc":datetime.now(timezone.utc).isoformat(),
            "purpose":"Retrospective Stage 3 model inputs; not historical rapid-deadline vintages",
            "files":[entry,*[e for e in dynamic if Path(e["path"]).name in ("de440s.bsp","finals2000A.all")]]},indent=2)+"\n")


if __name__=="__main__":main()
