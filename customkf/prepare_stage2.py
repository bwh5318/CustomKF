"""Bounded public reference-data downloads; no package installation or credentials."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"/"stage2"
CURL=r"C:\Windows\System32\curl.exe"


def sha(path):
    with open(path,"rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def fetch(url,name,limit):
    dest=DATA/name
    if dest.exists():
        return {"url":url,"path":dest.relative_to(ROOT).as_posix(),"bytes":dest.stat().st_size,"sha256":sha(dest)}
    part=dest.with_suffix(dest.suffix+".part")
    subprocess.run([CURL,"--fail","--location","--silent","--show-error","--max-time","60",
                    "--max-filesize",str(limit),url,"-o",str(part)],check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    total=part.stat().st_size
    if total>limit:raise ValueError("Reference download exceeded its byte budget")
    part.replace(dest)
    return {"url":url,"path":dest.relative_to(ROOT).as_posix(),"bytes":total,"sha256":sha(dest)}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):raise RuntimeError("Use customkf.guard")
    DATA.mkdir(parents=True,exist_ok=True)
    manifest=DATA/"manifest.json"
    if manifest.exists():
        entries=json.loads(manifest.read_text())["files"]
        for entry in entries:
            if sha(ROOT/entry["path"])!=entry["sha256"]:raise ValueError("Pinned reference changed")
        print("Existing pinned Stage 2 reference files verified")
        return
    files=[]
    files.append(fetch("https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp","de440s.bsp",40*2**20))
    print("DE440s downloaded",flush=True)
    files.append(fetch("https://maia.usno.navy.mil/ser7/finals2000A.all","finals2000A.all",6*2**20))
    print("EOP table downloaded",flush=True)
    gravity=DATA/"EGM2008_degree12.gfc"
    fetch("https://icgem.gfz.de/tom_longtime","icgem_index.html",2**20)
    html=(DATA/"icgem_index.html").read_text(encoding="utf-8")
    links=re.findall(r'href=["\']([^"\']+)["\']',html)
    matches=[link for link in links if "EGM2008.gfc" in link]
    if len(matches)!=1:raise ValueError(f"Expected one official EGM2008 link, got {matches}")
    url=urllib.request.urljoin("https://icgem.gfz.de/",matches[0])
    if not gravity.exists():
        retained=[];total=0;ended=False
        process=subprocess.Popen([CURL,"--fail","--location","--silent","--show-error","--max-time","60",url],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for raw in process.stdout:
                total+=len(raw)
                if total>2**20:raise ValueError("Gravity prefix exceeded 1 MiB")
                line=raw.decode("ascii")
                fields=line.split()
                if fields and fields[0]=="gfc" and int(fields[1])>12:
                    ended=True;break
                retained.append(line)
        finally:
            if process.poll() is None:process.terminate()
            process.wait(timeout=5)
        if not ended:raise ValueError("Gravity prefix did not reach degree 13")
        gravity.write_text("".join(retained),encoding="ascii")
    files.append({"url":url,"path":gravity.relative_to(ROOT).as_posix(),"bytes":gravity.stat().st_size,"sha256":sha(gravity),
                  "transformation":"Original ASCII prefix through degree/order 12; original max_degree header deliberately preserved"})
    manifest.write_text(json.dumps({"created_utc":datetime.now(timezone.utc).isoformat(),"files":files,
        "purpose":"Retrospective Stage 2 dynamics development; this EOP snapshot is not a certified historical rapid input vintage"},indent=2)+"\n")
    print(json.dumps(files,indent=2))


if __name__=="__main__":main()
