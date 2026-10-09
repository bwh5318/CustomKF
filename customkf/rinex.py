"""Streaming, bounded GPS extraction from RINEX 2.11, 3.x and 4.01 observations.

Values retain their original identifiers, cycles/metres, LLI and signal strength.
Hatanaka is deliberately rejected. Unsupported corrections/events fail closed.
"""
from dataclasses import dataclass, field
import gzip
from pathlib import Path
import math
from .sp3 import epoch_tag, gps_id


def text_stream(path):
    path=Path(path)
    return gzip.open(path,"rt",encoding="ascii") if path.suffix==".gz" else path.open(encoding="ascii")


@dataclass(frozen=True)
class Observable:
    value: float | None
    lli: int
    strength: int


@dataclass
class Header:
    version: float
    marker: str=""
    receiver: str=""
    antenna: str=""
    antenna_serial: str=""
    approximate_xyz: tuple=()
    antenna_hen: tuple=()
    interval_s: float=0.
    clock_offsets_applied: int=0
    time_system: str=""
    types: dict=field(default_factory=dict)
    comments: list=field(default_factory=list)
    comment_events: list=field(default_factory=list)
    phase_shift_metadata: list=field(default_factory=list)


@dataclass
class ObservationEpoch:
    gps_ns: int
    flag: int
    receiver_clock_s: float | None
    satellites: dict


def number(value):
    value=value.strip()
    if not value:return None
    x=float(value.replace("D","E"))
    if not math.isfinite(x):raise ValueError("Nonfinite RINEX value")
    return x


def header(stream, *, allow_declared_phase_shifts=False):
    first=stream.readline()
    if "CRINEX" in first:raise ValueError("Hatanaka requires an explicit decoder; gzip alone is insufficient")
    if len(first)<60 or first[20]!="O" or "RINEX VERSION / TYPE" not in first:
        raise ValueError("Not an observation RINEX file")
    version=float(first[:9])
    if version!=2.11 and not 3.<=version<=3.05 and version!=4.01:
        raise ValueError("Supported observation versions: 2.11, 3.00–3.05 and 4.01")
    result=Header(version);counts={};system=None
    for _ in range(2000):
        line=stream.readline()
        if not line:raise ValueError("Truncated RINEX header")
        label=line[60:].strip();body=line[:60]
        if label=="END OF HEADER":break
        if label=="MARKER NAME":result.marker=body.strip()
        elif label=="REC # / TYPE / VERS":result.receiver=body.rstrip()
        elif label=="ANT # / TYPE":result.antenna=body[20:40].rstrip();result.antenna_serial=body[:20].strip()
        elif label=="APPROX POSITION XYZ":result.approximate_xyz=tuple(map(float,body.split()))
        elif label=="ANTENNA: DELTA H/E/N":result.antenna_hen=tuple(map(float,body.split()))
        elif label=="INTERVAL":result.interval_s=float(body)
        elif label=="RCV CLOCK OFFS APPL":result.clock_offsets_applied=int(body)
        elif label=="TIME OF FIRST OBS":result.time_system=body[48:51].strip()
        elif label=="# / TYPES OF OBSERV":
            if body[:6].strip():counts["G"]=int(body[:6]);result.types["G"]=[]
            result.types["G"].extend(body[i:i+6].strip() for i in range(6,60,6) if body[i:i+6].strip())
        elif label=="SYS / # / OBS TYPES":
            if body[0]!=" ":system=body[0];counts[system]=int(body[3:6]);result.types[system]=[]
            if system is None:raise ValueError("Orphan observation-type continuation")
            result.types[system].extend(body[i:i+4].strip() for i in range(7,60,4) if body[i:i+4].strip())
        elif label=="COMMENT":result.comments.append(body.rstrip())
        elif label in ("SYS / SCALE FACTOR","WAVELENGTH FACT L1/2","SYS / PHASE SHIFT"):
            if label=="SYS / PHASE SHIFT" and allow_declared_phase_shifts:
                # RINEX 3.05 section 5.2.12/Table 9: these corrections were
                # applied before writing phi_RINEX. Record, never add again.
                system,code=body[0],body[2:5].strip()
                shift=number(body[6:14]);count=int(body[16:18]) if body[16:18].strip() else 0
                satellites=body[18:].split()
                if (version<3.01 or system not in "GRECJIS" or (code and (len(code)!=3 or code[0]!="L")) or
                    count!=len(satellites) or count>10 or any(s[0]!=system for s in satellites) or
                    (not code and shift is not None)):
                    raise ValueError("Unsupported or malformed phase-shift metadata profile")
                result.phase_shift_metadata.append({"system":system,"signal":code,"applied_cycles":shift,"satellites":satellites})
                continue
            if label=="WAVELENGTH FACT L1/2" and body[:12].split()==["1","1"]:continue
            if label=="SYS / PHASE SHIFT" and (not body[6:14].strip() or float(body[6:14])==0.):continue
            raise ValueError(f"Explicit handling required for {label}: cannot ignore a data correction")
    else:raise ValueError("Header line budget exceeded")
    if any(len(result.types[s])!=n or len(set(result.types[s]))!=n for s,n in counts.items()):
        raise ValueError("Inconsistent observation type counts")
    if "G" not in result.types:raise ValueError("GPS observation types missing")
    if not result.time_system and first[40:41] in ("G"," "):result.time_system="GPS"
    if result.time_system!="GPS":raise ValueError("Explicit GPS epoch tags required")
    if result.clock_offsets_applied not in (0,1):raise ValueError("Invalid receiver clock flag")
    if len(result.approximate_xyz)!=3 or len(result.antenna_hen)!=3:raise ValueError("Station position/eccentricity missing")
    return result


def decode_fields(text,types):
    text=text.ljust(16*len(types));result={}
    for i,code in enumerate(types):
        field=text[i*16:(i+1)*16]
        result[code]=Observable(number(field[:14]),int(field[14]) if field[14].strip() else 0,
                                int(field[15]) if field[15].strip() else 0)
    return result


def _declares_no_phase_shift(row):
    if row[60:].strip()!="SYS / PHASE SHIFT":return False
    value=row[6:14].strip()
    try:return not value or float(value)==0.
    except ValueError:return False


def epochs(stream,meta,max_epochs=10000):
    previous=None;count=0
    for line in stream:
        if not line.strip():continue
        count+=1
        if count>max_epochs:raise ValueError("Observation epoch budget exceeded")
        if meta.version<3:
            if len(line)<32:raise ValueError("Truncated observation epoch")
            fields=line[:26].split()
            if len(fields)!=6:raise ValueError("Malformed RINEX 2 epoch")
            year=int(fields[0]);fields[0]=str(year+(1900 if year>=80 else 2000))
            tag=epoch_tag("* "+" ".join(fields));flag=int(line[28]);n=int(line[29:32])
            clock=number(line[68:80]);sats=line[32:68]
        else:
            if not line.startswith(">") or len(line)<35:raise ValueError("Malformed RINEX 3 epoch")
            fields=line[1:].split();tag=epoch_tag("* "+" ".join(fields[:6]));flag=int(fields[6]);n=int(fields[7])
            clock=number(fields[8]) if len(fields)>8 else None
        if not 0<=n<=200:raise ValueError("Satellite/event count exceeds budget")
        if flag in (2,3,4,5):
            event_rows=[stream.readline() for _ in range(n)]
            # Header-information events are accepted only when they change nothing: comments, or a SYS / PHASE SHIFT
            # declaring no correction (the same rule as the header). Added 29 Sep 2026: YELL00CAN inserts an
            # "E L6C 0.00000" phase-shift event on 2026-06-20 and 06-23. Anything else still refuses.
            if flag==4 and event_rows and all(row[58:].strip()=="COMMENT" or _declares_no_phase_shift(row) for row in event_rows):
                meta.comment_events.append({"gps_ns":tag,"flag":flag,"lines":[row.rstrip() for row in event_rows]})
                continue
            # Equipment, moving-site and header updates cannot cross static PPP arcs.
            raise ValueError(f"RINEX event {flag} at {tag}: split and explicitly process metadata")
        if flag not in (0,1,6):raise ValueError("Unsupported RINEX event flag")
        if previous is not None and tag<=previous:raise ValueError("Observation times must increase")
        previous=tag
        records={}
        if meta.version<3:
            for _ in range((n-1)//12):
                continuation=stream.readline()
                if len(continuation.rstrip())<32:raise ValueError("Truncated satellite continuation")
                sats+=continuation[32:68]
            satellites=[gps_id(sats[i*3:(i+1)*3]) for i in range(n)]
            types=meta.types["G"]
            for sat in satellites:
                parts=[]
                for _ in range((len(types)+4)//5):
                    row=stream.readline()
                    if not row:raise ValueError("Truncated observation record")
                    parts.append(row.rstrip("\r\n").ljust(80))
                if sat.startswith("G"):
                    if sat in records:raise ValueError("Duplicate GPS satellite")
                    records[sat]=decode_fields("".join(parts),types)
        else:
            for _ in range(n):
                row=stream.readline()
                if not row:raise ValueError("Truncated observation record")
                sat=gps_id(row[:3])
                if sat[0] not in meta.types:raise ValueError("Missing satellite-system observation types")
                if sat.startswith("G"):
                    if sat in records:raise ValueError("Duplicate GPS satellite")
                    records[sat]=decode_fields(row[3:].rstrip("\r\n"),meta.types["G"])
        if clock not in (None,0.) and meta.clock_offsets_applied==0:
            raise ValueError("Unapplied receiver epoch clock offset requires explicit normalization")
        yield ObservationEpoch(tag,flag,clock,records)


def read_gps_navigation(path):
    """GPS LNAV blocks from RINEX 3 navigation; retain all named raw parameters."""
    names=("iode","crs","delta_n","m0","cuc","e","cus","sqrt_a","toe","cic","omega0","cis",
           "i0","crc","omega","omega_dot","idot","codes_l2","week","l2p_flag","ura","health",
           "tgd","iodc","transmission_time","fit_interval","spare1","spare2")
    result={}
    with text_stream(path) as stream:
        first=stream.readline()
        if "NAVIGATION" not in first or not 3<=float(first[:9])<4:raise ValueError("Require RINEX 3 navigation")
        version=float(first[:9])
        for _ in range(2000):
            if "END OF HEADER" in stream.readline():break
        else:raise ValueError("Missing NAV header end")
        for count,line in enumerate(stream):
            if count>100000:raise ValueError("Navigation record budget exceeded")
            if not line.strip():continue
            sat=gps_id(line[:3]);system=sat[0]
            if system not in "GRECJIS":raise ValueError("Unknown navigation system")
            nlines=(5 if version>=3.05 else 4) if system=="R" else (4 if system=="S" else 8)
            rows=[line]+[stream.readline() for _ in range(nlines-1)]
            if any(not row for row in rows):raise ValueError("Truncated navigation block")
            if system!="G":continue
            tag=epoch_tag("* "+line[4:23].strip())
            clocks=[number(line[i:i+19]) for i in (23,42,61)]
            values=[number(row[i:i+19]) for row in rows[1:] for i in (4,23,42,61)]
            if any(v is None for v in clocks+values[:24]):raise ValueError("Missing GPS ephemeris parameter")
            record={"gps_ns":tag,"af0":clocks[0],"af1":clocks[1],"af2":clocks[2],**dict(zip(names,values))}
            result.setdefault(sat,[]).append(record)
    for rows in result.values():rows.sort(key=lambda r:r["gps_ns"])
    if not result:raise ValueError("No GPS navigation records")
    return result
