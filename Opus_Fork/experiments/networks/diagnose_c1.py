"""Why did the extended C1 control fail on Jul 6 and Jul 23 (8 Oct 2026)? Production and oracle frames compared.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.networks.diagnose_c1 --scoring Opus_Fork/runs/networks-scoring-<UTC>/scoring.json

Production scores a sub-daily-EOP fit through `customkf.frames` + `Opus_Fork.subdaily_eop`; the oracle rotates the same
inertial states with its own `validation.oracle.frame`. NGA PE is Earth-fixed and needs neither, and it reproduced to
3e-10 m. For each date this records, on the scored 15-minute epochs:
- the small rotation between the two sub-daily GCRS->ITRS matrices (and between the two plain ones), in uas;
- the daily EOP values and the ocean-tidal sub-daily corrections of each side;
- for every fitted arm, oracle minus production for URE, 3D, R, A, C and the largest per-satellite 3D difference.
Differences only: no score, ratio or contrast is printed or saved. Writes `diagnose_c1.json` in the run folder.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from customkf.frames import EarthOrientation, FrameEpoch
from Opus_Fork import subdaily_eop
from Opus_Fork.experiments.networks.analyze_networks import ARMS, DATES, EOP, INDEX, ROOT, CachedFrame, solution
from Opus_Fork.experiments.transfer.common import run_dir, sha
from validation.oracle import frame as O2, metrics as O1

AS2UAS = 1e6
RAD2UAS = 180/np.pi*3600*1e6


def scored_epochs(origin):
    """The 96 scored 15-minute GPST tags (ns) from 00:00 to 23:45, as Python ints.

    Corrected 8 Oct 2026 (Astra NR-01): the first version used `np.arange(96)*900*10**9`, which is int32 on this
    Windows NumPy and overflowed, so run `runs/20261009T003655Z-18787b21` sampled about 4 s around midnight."""
    return [int(origin)+10*10**9+k*900*10**9 for k in range(96)]


def small_rotation(a, b):
    """Rotation vector (rad) of a @ b.T, valid for small angles."""
    d = a@b.T
    return np.array([d[2, 1]-d[1, 2], d[0, 2]-d[2, 0], d[1, 0]-d[0, 1]])/2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scoring", required=True)
    args = parser.parse_args()
    folder = run_dir()
    record = json.loads(open(args.scoring).read())          # the analysis stopped, so the record is no longer "analyzing"
    evaluations = {}
    for day in DATES:
        e = record["evaluations"][day]
        assert e["problems"] == [] and e["exit_code"] == 0 and sha(e["output"]) == e["output_sha256"], day
        evaluations[day] = Path(e["output"])
    index = json.loads(INDEX.read_text())["dates"]
    plain_p, sub_p = EarthOrientation(EOP), subdaily_eop.earth_orientation_class()(EOP)
    finals = O2.Finals(EOP)
    plain_o, sub_o = O2.Frame(finals), CachedFrame(O2.Frame(finals, subdaily=True))
    out = {}
    for day in DATES:
        evaluation = json.loads(evaluations[day].read_text())
        origin = int(json.loads((ROOT/index[day]["V-op"]["fixture"]).read_text())["context"]["origin_ns"])
        epochs = scored_epochs(origin)
        fp, fs = FrameEpoch(origin, plain_p), FrameEpoch(origin, sub_p)
        w_sub, w_plain, eop_diff, tide_diff = [], [], [], []
        for t in epochs:
            elapsed = (t-origin)/1e9
            w_sub.append(small_rotation(fs.celestial_to_terrestrial(elapsed), sub_o.rotation(t))*RAD2UAS)
            w_plain.append(small_rotation(fp.celestial_to_terrestrial(elapsed), plain_o.rotation(t))*RAD2UAS)
            _, _, mjd, _ = plain_o.times(t)
            p, o = plain_p.at(mjd), finals.at(mjd)
            eop_diff.append([(p[0]-o[0])*AS2UAS, (p[1]-o[1])*AS2UAS, (p[2]-o[2])*1e6, (p[3]-o[3])*1e3, (p[4]-o[4])*1e3])
            tide_diff.append(np.subtract(subdaily_eop.ocean_tidal_eop(mjd), O2.ocean_tidal_eop(mjd)))
        w_sub, w_plain, eop_diff, tide_diff = map(np.array, (w_sub, w_plain, eop_diff, tide_diff))
        entry = dict(subdaily_rotation_uas=dict(max_norm=float(np.linalg.norm(w_sub, axis=1).max()),
                                                mean_xyz=w_sub.mean(axis=0).tolist(), std_xyz=w_sub.std(axis=0).tolist()),
                     plain_rotation_uas=dict(max_norm=float(np.linalg.norm(w_plain, axis=1).max()),
                                             mean_xyz=w_plain.mean(axis=0).tolist()),
                     daily_eop_max_abs=dict(zip(("xp_uas", "yp_uas", "dut1_us", "dX_uas", "dY_uas"),
                                                np.abs(eop_diff).max(axis=0).tolist())),
                     tidal_max_abs=dict(zip(("x_uas", "y_uas", "ut1_us"), np.abs(tide_diff).max(axis=0).tolist())),
                     position_effect_at_gps_radius_mm=float(np.linalg.norm(w_sub, axis=1).max()/RAD2UAS*26.56e9),
                     arms={})
        reference = O1.read_sp3(evaluation["provenance"]["igs_final"]["path"])
        arms = evaluation["domains"]["full"]["arms"]
        keys = None
        ecefs = {}
        for arm in ARMS:
            s = solution(index[day][arm])
            ecefs[arm] = O1.solution_ecef(s["states"], s["sats"], s["times"], origin, sub_o)
            keys = set(ecefs[arm]) if keys is None else keys & set(ecefs[arm])
        nga = O1.read_sp3(evaluation["provenance"]["NGA"]["path"])
        lo, hi = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
        keys = {k for k in keys & set(reference) & set(nga) if lo <= k[1] <= hi}
        sats = sorted({s for s, _ in keys})
        for arm in ARMS:
            raw = arms[arm]["raw"]
            whole = O1.summarize(reference, ecefs[arm], sub_o, keys)
            per = {s: O1.summarize(reference, ecefs[arm], sub_o, {k for k in keys if k[0] == s})["rms_3d_m"]
                   -arms[arm]["per_satellite"][s]["rms_3d_m"] for s in sats}
            worst = max(per, key=lambda s: abs(per[s]))
            entry["arms"][arm] = dict(ure_mm=(whole["orbit_ure_m"]-raw["rms_orbit_ure_m"])*1e3,
                                      d3_mm=(whole["rms_3d_m"]-raw["rms_3d_m"])*1e3,
                                      rac_mm=[(a-b)*1e3 for a, b in zip(whole["rms_rac_m"], raw["rms_rac_m"])],
                                      worst_satellite=worst, worst_satellite_3d_mm=per[worst]*1e3,
                                      satellites_over_0p1mm=sorted(s for s in sats if abs(per[s]) > 1e-4))
        out[day] = entry
        print(day, json.dumps({k: entry[k] for k in ("subdaily_rotation_uas", "daily_eop_max_abs", "tidal_max_abs")}),
              flush=True)
        for arm, a in entry["arms"].items():
            print("  ", arm, json.dumps(a), flush=True)
    (folder/"diagnose_c1.json").write_text(json.dumps(out, indent=1)+"\n")


if __name__ == "__main__":
    main()
