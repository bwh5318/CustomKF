"""Read the IGS satellite metadata SINEX: PRN -> SVN, block, mass and transmit power on a date.

Static estimation-side input acquired by `Opus_Fork.fetch_metadata` into
`datastore/static/igs_satellite_metadata.snx`; its sidecar hash is re-checked on every load.
File description: Steigenberger & Montenbruck, IGS Satellite Metadata File Description 1.10
(doi:10.57677/metadata-sinex). No orbit information; nothing here comes from an IGS orbit.
"""
from dataclasses import dataclass
from datetime import date as Date
import json

from customkf.prepare_stage2 import sha

from .paths import STORE

PATH = STORE/"static"/"igs_satellite_metadata.snx"
C_LIGHT = 299792458.


@dataclass(frozen=True)
class Satellite:
    prn: str
    svn: str
    block: str
    mass_kg: float
    tx_power_w: float

    @property
    def thrust_mps2(self):
        """Antenna thrust: radiated power / (mass * c), directed away from the Earth."""
        return self.tx_power_w/(self.mass_kg*C_LIGHT)


def _blocks(lines):
    out, name = {}, None
    for line in lines:
        if line.startswith("+"):
            name = line[1:].split()[0]
            out[name] = []
        elif line.startswith("-"):
            name = None
        elif name and line.strip() and not line.startswith("*"):
            out[name].append(line)
    return out


def _stamp(text):
    y, d, s = (int(v) for v in text.split(":"))
    return (y, d, s)


def _valid(start, stop, when):
    return _stamp(start) <= when and (stop.startswith("0000") or when < _stamp(stop))


def load(day):
    """{PRN: Satellite} for GPS satellites assigned on `day` (ISO date string), at 12:00."""
    record = json.loads((PATH.parent/(PATH.name+".json")).read_text())
    if sha(PATH) != record["sha256"]:
        raise ValueError("Satellite metadata no longer matches its acquisition hash")
    blocks = _blocks(PATH.read_text(encoding="ascii").splitlines())
    d = Date.fromisoformat(day)
    when = (d.year, d.timetuple().tm_yday, 43200)
    prn = {}
    for line in blocks["SATELLITE/PRN"]:
        f = line.split()
        if f[0].startswith("G") and _valid(f[1], f[2], when):
            if f[3] in prn:
                raise ValueError("Two SVNs for "+f[3])
            prn[f[3]] = f[0]
    block = {line.split()[0]: line.split()[3] for line in blocks["SATELLITE/IDENTIFIER"]
             if line.startswith(" G")}

    def dated(name):
        values = {}
        for line in blocks[name]:
            f = line.split()
            if f[0].startswith("G") and _valid(f[1], f[2], when):
                if f[0] in values:
                    raise ValueError(f"Two {name} records for {f[0]}")
                values[f[0]] = float(f[3])
        return values
    mass, power = dated("SATELLITE/MASS"), dated("SATELLITE/TX_POWER")
    return {p: Satellite(p, s, block.get(s, "?"), mass[s], power[s]) for p, s in sorted(prn.items())
            if s in mass and s in power}


def provenance():
    record = json.loads((PATH.parent/(PATH.name+".json")).read_text())
    return dict(path=str(PATH), sha256=record["sha256"], source_url=record["source_url"],
                retrieved_utc=record["retrieved_utc"], header=record["header"])
