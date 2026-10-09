"""Station selection for the network tests (PROTOCOL.md §3–§4), run once as one guarded job.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 3600 -- \
        Opus_Fork.experiments.networks.select_networks

1. Lists the BKG daily observation directories for the five dates.
2. Builds the pool:
   - listed on all five dates;
   - IGc20 solution valid at each date;
   - not in the PSD file;
   - present in FES2014b.BLQ;
   - four GRAD epochs in each needed file.
3. Chooses S17 (nearest pool station to each NGA/USAF monitor site) and S50 (the frozen 25 plus farthest-point
   additions). Each candidate is header-screened on all five dates when the rules first consider it.

Writes `networks.json` in the run folder. No observation data is downloaded; no orbit, residual or reference product
is read.
"""
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import re

import numpy as np

from customkf.station_models import reference_coordinate
from Opus_Fork import gradients
from Opus_Fork.fetch import BKG, NETWORK_25, fetch, sample_header
from Opus_Fork.experiments.transfer.common import run_dir, sha
from Opus_Fork.paths import ROOT

HERE = Path(__file__).resolve().parent
STAGE3 = ROOT/"data/stage3"
DATES = {"2026-06-06": "runs/20260929T202245Z-21f63ba3", "2026-06-20": "runs/20260929T203924Z-224f1e22",
         "2026-06-23": "runs/20260929T201929Z-5b2b3e42", "2026-07-06": "runs/20260929T204645Z-ba94e895",
         "2026-07-23": "runs/20260929T203059Z-40b5a8d7"}
NGA_SITES = [("Adelaide, Australia", -34.93, 138.60), ("Buenos Aires, Argentina", -34.60, -58.38),
             ("Hermitage, England", 51.45, -1.27), ("Manama, Bahrain", 26.23, 50.59),
             ("Quito, Ecuador", -0.18, -78.47), ("Washington DC (USNO), USA", 38.92, -77.07),
             ("Fairbanks, Alaska", 64.84, -147.72), ("Osan, South Korea", 37.09, 127.03),
             ("Papeete, Tahiti", -17.55, -149.56), ("Pretoria, South Africa", -25.75, 28.19),
             ("Wellington, New Zealand", -41.29, 174.78), ("Ascension Island (USAF)", -7.95, -14.36),
             ("Cape Canaveral, Florida (USAF)", 28.39, -80.60), ("Colorado Springs, Colorado (USAF)", 38.80, -104.53),
             ("Diego Garcia (USAF)", -7.31, 72.41), ("Hawaii, Oahu (USAF)", 21.57, -158.27),
             ("Kwajalein Atoll (USAF)", 8.72, 167.73)]
EARTH_KM = 6371.0
TARGET = 50


def unit_from_latlon(lat, lon):
    a, b = math.radians(lat), math.radians(lon)
    return np.array([math.cos(a)*math.cos(b), math.cos(a)*math.sin(b), math.sin(a)])


def km(u, v):
    return EARTH_KM*math.acos(max(-1.0, min(1.0, float(u@v))))


def listing(day, folder):
    date = datetime.strptime(day, "%Y-%m-%d")
    stamp, doy = date.strftime("%Y%j"), date.strftime("%j")
    path = folder/f"listing_{stamp}.html"
    fetch(f"{BKG}/obs/{date.year}/{doy}/", path, 8*2**20)
    names = set(re.findall(rf"([A-Z0-9]{{4}}\d\d[A-Z]{{3}})_R_{stamp}0000_01D_30S_MO\.crx\.gz", path.read_text(errors="replace")))
    return names, sha(path)


def ssc_positions():
    """{site: unit vector} from the first STAX/STAY/STAZ triple per site in IGc20.ssc (ranking only)."""
    seen = {}
    for line in open(STAGE3/"IGc20.ssc"):
        f = line.split()
        if len(f) >= 10 and f[1] in ("STAX", "STAY", "STAZ"):
            seen.setdefault((f[2], f[4]), {})[f[1]] = float(f[8])
    out = {}
    for (site, _), xyz in seen.items():
        if site not in out and len(xyz) == 3:
            v = np.array([xyz["STAX"], xyz["STAY"], xyz["STAZ"]])
            out[site] = v/np.linalg.norm(v)
    return out


def blq_sites():
    out = set()
    for line in open(STAGE3/"FES2014b.BLQ"):
        if line.startswith("  ") and len(line.strip()) == 4 and not line.startswith("$$"):
            out.add(line.strip())
    return out


def grad_sites(day, fixture_dir):
    context = json.loads((ROOT/fixture_dir/"fixture.json").read_text())["context"]
    names = gradients.arc_days(int(context["origin_ns"]), context["duration_s"])
    counts = []
    for name in names:
        c = {}
        for line in (gradients.DATA/"GRAD_OP"/f"{name}.grad_g").read_text().splitlines():
            p = line.split()
            if len(p) == 6 and not p[0].startswith(("!", "#", "%")):
                c[p[0]] = c.get(p[0], 0)+1
        counts.append(c)
    return {s for s in counts[0] if all(c.get(s) == 4 for c in counts)}, names


def main():
    folder = run_dir()
    scratch = folder/"headers"
    scratch.mkdir(exist_ok=True)
    report = dict(protocol_sha256=sha(HERE/"PROTOCOL.md"), dates=list(DATES), listings={}, pool_filters={})

    listed = None
    for day in DATES:
        names, digest = listing(day, folder)
        report["listings"][day] = dict(markers=len(names), sha256=digest)
        listed = names if listed is None else listed & names
    markers = {}
    for m in sorted(listed):
        markers.setdefault(m[:4], m)                                     # lexically first marker per site
    positions = ssc_positions()
    psd = (STAGE3/"psd_IGc20.snx").read_text()
    blq = blq_sites()
    grad = None
    for day, fixture_dir in DATES.items():
        sites, files = grad_sites(day, fixture_dir)
        report["pool_filters"][f"grad_{day}"] = files
        grad = sites if grad is None else grad & sites
    pool = sorted(s for s in markers if s in positions and s not in psd and s in blq and s in grad)
    report["pool_filters"].update(listed_all_dates=len(markers), with_ssc=sum(s in positions for s in markers),
                                  pool=len(pool))
    print(f"{len(markers)} sites listed on all dates; pool {len(pool)}", flush=True)

    screened = {}

    def eligible(site):
        if site in screened:
            return screened[site]["eligible"]
        entry = dict(marker=markers[site], dates={})
        ok = True
        for day in DATES:
            when = datetime.strptime(day, "%Y-%m-%d")+timedelta(hours=12)
            try:
                reference_coordinate(STAGE3/"IGc20.ssc", STAGE3/"soln_IGc20.snx", site, when)
            except ValueError as error:
                entry["dates"][day] = dict(coordinate=str(error))
                ok = False
                break
            row = sample_header(markers[site], day, scratch)
            entry["dates"][day] = {k: row.get(k) for k in ("available", "compatible", "reason")}
            if row.get("compatible"):
                entry["dates"][day]["signal_pair"] = row["header"]["signal_pair"]
                entry["dates"][day]["antenna"] = row["header"]["antenna"]
            else:
                ok = False
                break
        entry["eligible"] = ok
        screened[site] = entry
        print(f"  screen {markers[site]}: {'eligible' if ok else 'rejected'}", flush=True)
        return ok

    s17, taken = [], set()
    for name, lat, lon in NGA_SITES:
        target = unit_from_latlon(lat, lon)
        ranked = sorted(pool, key=lambda s: (km(positions[s], target), s))
        for site in ranked:
            if site not in taken and eligible(site):
                d = km(positions[site], target)
                s17.append(dict(site=name, station=site, marker=markers[site], distance_km=round(d, 1),
                                flagged_over_1000_km=d > 1000))
                taken.add(site)
                break
    report["S17"] = s17

    base = [m[:4] for m in NETWORK_25]
    chosen = list(base)
    added, rejected = [], set()
    while len(chosen) < TARGET:
        candidates = [s for s in pool if s not in chosen and s not in rejected]
        scored = sorted(((-min(km(positions[s], positions[c]) for c in chosen), s) for s in candidates))
        for negative, site in scored:
            if eligible(site):
                chosen.append(site)
                added.append(dict(station=site, marker=markers[site], min_distance_km=round(-negative, 1)))
                break
            rejected.add(site)
        else:
            raise RuntimeError("Pool exhausted before 50 stations")
    report["S50"] = dict(base=base, added=added, stations=chosen)
    report["screened"] = screened
    for path in scratch.glob("*"):
        path.unlink()
    (folder/"networks.json").write_text(json.dumps(report, indent=1)+"\n")
    print("S17:", ", ".join(f"{e['station']} ({e['distance_km']:.0f} km)" for e in s17), flush=True)
    print("S50 added:", ", ".join(f"{e['station']} ({e['min_distance_km']:.0f} km)" for e in added), flush=True)


if __name__ == "__main__":
    main()
