"""Restricted single-GPS-satellite SP3-c export of Stage 2 fitted COM positions.

No clock estimates or accuracy estimates are manufactured. SP3-c records have
millimetre coordinate precision; retain orbit.npz for submillimetre auditing.
"""
from datetime import timedelta
from pathlib import Path
import numpy as np
from .sp3 import GPS_START, gps_id


def write_fit_sp3(path, satellite, epochs_ns, positions_m, *, frame, predicted=None):
    satellite=gps_id(satellite)
    epochs=np.asarray(epochs_ns)
    positions=np.asarray(positions_m,dtype=float)
    if (not satellite.startswith("G") or epochs.ndim!=1 or len(epochs)<2
        or not np.issubdtype(epochs.dtype,np.integer) or np.any(epochs<0)
        or np.any(epochs%10) or np.any(np.diff(epochs)<=0)
        or np.any(np.diff(epochs)!=epochs[1]-epochs[0])
        or positions.shape!=(len(epochs),3) or not np.isfinite(positions).all()
        or np.max(np.abs(positions))>=999999000 or not 1<=len(frame)<=5
        or not frame.isalnum()):
        raise ValueError("Require regular finite GPS positions and SP3-c-compatible epochs/frame")
    flags=np.zeros(len(epochs),dtype=bool) if predicted is None else np.asarray(predicted,dtype=bool)
    if flags.shape!=(len(epochs),):raise ValueError("Prediction mask length mismatch")
    def calendar(tag):
        whole,ns=divmod(int(tag),10**9)
        dt=GPS_START+timedelta(seconds=whole)
        return f"{dt.year:4d} {dt.month:2d} {dt.day:2d} {dt.hour:2d} {dt.minute:2d} {dt.second+ns/1e9:11.8f}"
    first=int(epochs[0]);day,day_ns=divmod(first,86400*10**9)
    week,week_ns=divmod(first,604800*10**9)
    lines=[f"#cP{calendar(first)} {len(epochs):7d} ORBIT {frame:5s} FIT  CKF",
           f"## {week:4d} {week_ns/1e9:15.8f} {(epochs[1]-epochs[0])/1e9:14.8f} {44244+day:5d} {day_ns/(86400*1e9):15.13f}",
           "+    1   "+satellite+"  0"*16]
    lines.extend(["+        "+"  0"*17]*4)
    lines.extend(["++       "+"  0"*17]*5)
    lines.extend(["%c G  cc GPS ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
                  "%c cc cc ccc ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
                  "%f  1.2500000  1.025000000  0.00000000000  0.000000000000000",
                  "%f  0.0000000  0.000000000  0.00000000000  0.000000000000000",
                  "%i    0    0    0    0      0      0      0      0         0",
                  "%i    0    0    0    0      0      0      0      0         0",
                  "/* DYNAMIC FIT TO IGS FINAL; NOT OBSERVATION-DERIVED POD",
                  "/* CENTER OF MASS; GPST; CLOCKS AND ACCURACIES UNKNOWN",
                  "/* FRAME INHERITED FROM FIT REFERENCE; NO HELMERT ALIGNMENT",
                  "/* ORBIT P FLAGS MARK EPOCHS AFTER THE LAST TRAINING EPOCH"])
    for tag,xyz,flag in zip(epochs,positions,flags):
        lines.append("*  "+calendar(tag))
        lines.append((f"P{satellite}"+"".join(f"{x/1000:14.6f}" for x in xyz)+f"{999999.999999:14.6f}").ljust(79)+("P" if flag else " "))
    Path(path).write_text("\n".join(lines+["EOF"])+"\n",encoding="ascii")
