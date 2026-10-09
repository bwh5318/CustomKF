"""Oracle acceptance run (O2 vs production frames, O4 negative controls, O1+O2 vs the saved untouched-date scores).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --timeout 1800 -- validation.oracle.check

Tolerances are declared here, before any comparison (`docs/consolidation/REPAIRED_BASELINE.md` §4):
- FRAME_TOL: 2e-11 per rotation element, about 4 uas, which is 0.53 mm at 26,560 km. That is half the 1 mm SP3
  quantization;
- SCORE_TOL_M: 1e-4 m (0.1 mm) on each pooled raw metric (RMS 3D and orbit-only URE), with an identical sample count;
- every negative control must disagree with production by more than 10x its tolerance.

Production code is imported only to be compared against; the oracle's own numbers come from
`validation.oracle.frame` (O2) and `validation.oracle.metrics` (O1). Reads only; writes to the guard's run folder.
"""
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from validation.oracle import frame as O2
from validation.oracle import metrics as O1

ROOT = O2.ROOT
FINALS = ROOT/"data/stage2/finals2000A.all"
FRAME_TOL = 2e-11
SCORE_TOL_M = 1e-4
NEGATIVE_FACTOR = 10.
GPS_RADIUS_M = 26.56e6
CAMPAIGN_DAYS = ["2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
UNTOUCHED = ["2026-06-06", "2026-06-20", "2026-06-23", "2026-07-06", "2026-07-23"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def origin_of(day):
    """GPST ns of 23:59:50 on the previous day (every 24 h fixture's origin, checked against fixtures below)."""
    when = datetime.strptime(day, "%Y-%m-%d")-timedelta(seconds=10)
    return int((when-O1.GPS0).total_seconds())*10**9


def production(subdaily):
    from customkf.frames import EarthOrientation
    if not subdaily:
        return EarthOrientation(FINALS)
    from Opus_Fork.subdaily_eop import earth_orientation_class
    return earth_orientation_class()(FINALS)


def frame_comparison(days, finals):
    from customkf.frames import FrameEpoch
    out = {}
    for subdaily in (False, True):
        eop = production(subdaily)
        oracle = O2.Frame(finals, subdaily=subdaily)
        for day in days:
            origin = origin_of(day)
            epoch = FrameEpoch(origin, eop)
            worst = worst_norm = 0.
            for k in range(288):
                elapsed = 10.+300.*k
                diff = epoch.celestial_to_terrestrial(elapsed)-oracle.rotation(origin+int(elapsed*1e9))
                worst = max(worst, float(np.max(np.abs(diff))))
                worst_norm = max(worst_norm, float(np.linalg.norm(diff, 2)))
            out[f"{day} {'SD' if subdaily else 'plain'}"] = dict(
                max_element=worst, max_position_mm_at_gps_radius=worst_norm*GPS_RADIUS_M*1e3,
                passed=bool(worst <= FRAME_TOL))
    return out


def negative_controls(day, finals):
    """O4: each corruption must make the oracle disagree with production SD by > 10x the frame tolerance."""
    from customkf.frames import FrameEpoch
    origin = origin_of(day)
    epoch = FrameEpoch(origin, production(True))
    shifted = O2.Finals.__new__(O2.Finals)
    shifted.rows, shifted.kinds = finals.rows.copy(), finals.kinds
    shifted.rows[:, 3] += 1e-4                                     # UT1-UTC +0.1 ms in the daily file
    cases = {"wrong daily EOP file (UT1-UTC +0.1 ms)": (O2.Frame(shifted, subdaily=True), 0),
             "sub-daily EOP dropped (plain frame for an SD solution)": (O2.Frame(finals, subdaily=False), 0),
             "epoch shifted by 1 s": (O2.Frame(finals, subdaily=True), 10**9),
             "wrong fixture (origin of the next day)": (O2.Frame(finals, subdaily=True), 86400*10**9)}
    out = {}
    for name, (oracle, offset) in cases.items():
        worst = max(float(np.max(np.abs(epoch.celestial_to_terrestrial(10.+300.*k)
                                        -oracle.rotation(origin+int((10.+300.*k)*1e9)+offset))))
                    for k in range(0, 288, 12))
        out[name] = dict(max_element=worst, exceeds=bool(worst > NEGATIVE_FACTOR*FRAME_TOL))
    return out


def untouched_scores(day, finals):
    saved = json.loads((ROOT/f"Opus_Fork/results/untouched_{day.replace('-', '')}.json").read_text())
    p = saved["provenance"]
    for role in ("igs_final", "NGA"):
        assert sha(p[role]["path"]) == p[role]["sha256"], role
    solution = Path(p["U"]["solution"])
    assert sha(solution) == p["U"]["sha256"]
    campaign = solution.parents[1]
    fixture = ROOT/json.loads((campaign/"validation.json").read_text())["fixture"]
    assert sha(fixture) == p["U"]["fixture_sha256"]
    origin = int(json.loads(fixture.read_text())["context"]["origin_ns"])
    assert origin == origin_of(day), (origin, origin_of(day))
    with np.load(solution) as z:
        states, satellites, times = z["states"].copy(), [str(s) for s in z["satellites"]], z["times_s"].copy()
    sd = O2.Frame(finals, subdaily=True)
    reference, nga = O1.read_sp3(p["igs_final"]["path"]), O1.read_sp3(p["NGA"]["path"])
    ours = O1.solution_ecef(states, satellites, times, origin, sd)
    start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
    keys = {k for k in set(reference) & set(nga) & set(ours) if start <= k[1] <= stop}
    result, verdict = {}, True
    arms = saved["domains"]["full"]["arms"]
    for name, candidate in (("U", ours), ("NGA", nga)):
        got = O1.summarize(reference, candidate, sd, keys)
        want = arms[name]["raw"]
        diff = dict(rms_3d_m=got["rms_3d_m"]-want["rms_3d_m"], orbit_ure_m=got["orbit_ure_m"]-want["rms_orbit_ure_m"])
        ok = got["samples"] == want["samples"] and all(abs(v) <= SCORE_TOL_M for v in diff.values())
        verdict &= ok
        result[name] = dict(oracle=got, saved=dict(samples=want["samples"], rms_3d_m=want["rms_3d_m"],
                                                   orbit_ure_m=want["rms_orbit_ure_m"]), difference=diff, passed=bool(ok))
    plain = O1.solution_ecef(states, satellites, times, origin, O2.Frame(finals, subdaily=False))
    dropped = O1.summarize(reference, plain, sd, keys)
    result["negative_control_sd_dropped"] = dict(
        orbit_ure_difference_m=dropped["orbit_ure_m"]-arms["U"]["raw"]["rms_orbit_ure_m"],
        rms_3d_difference_m=dropped["rms_3d_m"]-arms["U"]["raw"]["rms_3d_m"],
        exceeds=bool(max(abs(dropped["orbit_ure_m"]-arms["U"]["raw"]["rms_orbit_ure_m"]),
                         abs(dropped["rms_3d_m"]-arms["U"]["raw"]["rms_3d_m"])) > NEGATIVE_FACTOR*SCORE_TOL_M))
    result["ure_ratio"] = result["U"]["oracle"]["orbit_ure_m"]/result["NGA"]["oracle"]["orbit_ure_m"]
    result["d3_ratio"] = result["U"]["oracle"]["rms_3d_m"]/result["NGA"]["oracle"]["rms_3d_m"]
    result["passed"] = bool(verdict)
    return result


def main():
    folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
    finals = O2.Finals(FINALS)
    report = dict(tolerances=dict(frame_element=FRAME_TOL, score_m=SCORE_TOL_M, negative_factor=NEGATIVE_FACTOR),
                  finals_sha256=sha(FINALS), oracle_sha256={p.name: sha(p) for p in sorted(Path(O2.__file__).parent.glob("*.py"))})
    report["frames"] = frame_comparison(UNTOUCHED+CAMPAIGN_DAYS, finals)
    print("frames:", all(v["passed"] for v in report["frames"].values()), flush=True)
    report["negative_controls"] = negative_controls("2026-06-20", finals)
    report["scores"] = {day: untouched_scores(day, finals) for day in UNTOUCHED}
    for day, r in report["scores"].items():
        print(day, r["passed"], round(r["ure_ratio"], 6), round(r["d3_ratio"], 6), flush=True)
    ratios = [report["scores"][d]["ure_ratio"] for d in UNTOUCHED]
    report["untouched_claim"] = dict(ure_ratio_below_1=sum(r < 1 for r in ratios), mean_ure_ratio=float(np.mean(ratios)),
                                     mean_d3_ratio=float(np.mean([report["scores"][d]["d3_ratio"] for d in UNTOUCHED])))
    report["passed"] = bool(all(v["passed"] for v in report["frames"].values())
                            and all(v["exceeds"] for v in report["negative_controls"].values())
                            and all(r["passed"] and r["negative_control_sd_dropped"]["exceeds"]
                                    for r in report["scores"].values()))
    (folder/"oracle_check.json").write_text(json.dumps(report, indent=1)+"\n")
    print(json.dumps({k: report[k] for k in ("passed", "untouched_claim")}, indent=1), flush=True)
    return exit_status(report)


def exit_status(report):
    """0 only for an explicit pass, so the process status alone can gate acceptance (Astra PI-11, 8 Oct 2026)."""
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
