"""How often is our URE lower than NGA PE's? Time shares against IGS final on the fresh dates (user question, 4 Oct 2026).

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
        Opus_Fork.experiments.gradients.ure_time_share

For each scored date (the five untouched/validation dates and Jun 27), and for the default and the default plus GRAD
operational gradients:
- **epoch share:** the fraction of 15-minute epochs at which our constellation URE (the RMS over satellites at that
  epoch) is lower than NGA's;
- **sample share:** the fraction of satellite-epochs at which our instantaneous orbit URE,
  sqrt(0.98^2 R^2 + (A^2 + C^2)/49), is lower than NGA's.

Both use the independent oracle's frame and metric definitions, on the evaluator's population: keys common to IGS
final, NGA and every arm, over 00:00:10 to 23:45:10 of the arc. Each date's per-sample values are checked to reproduce
the production URE within 0.1 mm. Descriptive only, with IGS final as the reference, not truth. Writes
`ure_time_share.json` in the run folder.
"""
import json

import numpy as np

from Opus_Fork.experiments.gradients.analyze_validation import ROOT, SCORE_TOL_M
from Opus_Fork.experiments.transfer.common import run_dir, sha
from validation.oracle import frame as O2, metrics as O1

# evaluation file -> (our default arm, our gradient arm)
DATES = {"2026-06-06": ("gradval_20260606.json", "U", "V-op"), "2026-06-20": ("gradval_20260620.json", "U", "V-op"),
         "2026-06-23": ("gradval_20260623.json", "U", "V-op"), "2026-07-06": ("gradval_20260706.json", "U", "V-op"),
         "2026-07-23": ("gradval_20260723.json", "U", "V-op"),
         "2026-06-27": ("newdate_matched_20260627.json", "U", "N-op")}
FIXTURES = {"2026-06-06": "runs/20260929T202245Z-21f63ba3", "2026-06-20": "runs/20260929T203924Z-224f1e22",
            "2026-06-23": "runs/20260929T201929Z-5b2b3e42", "2026-07-06": "runs/20260929T204645Z-ba94e895",
            "2026-07-23": "runs/20260929T203059Z-40b5a8d7", "2026-06-27": "runs/20261004T151035Z-0225f559"}


def per_sample_ure(reference, candidate, frame, keys):
    """{key: instantaneous orbit URE (m)}, with the same geometry as validation.oracle.metrics.summarize."""
    rotations = {t: frame.rotation(t) for _, t in reference}
    per = {}
    for s, t in sorted(reference):
        per.setdefault(s, []).append(t)
    out = {}
    for s, t in sorted(keys):
        ts = np.array(per[s], dtype=np.int64)
        k = int(np.searchsorted(ts, t))
        lo = max(0, min(k-4, len(ts)-9))
        ix = ts[lo:lo+9]
        x = (ix-t)/1e9/900.
        positions = np.array([rotations[int(q)].T@reference[s, int(q)] for q in ix])
        velocity = np.linalg.solve(np.vander(x, N=9, increasing=True), positions)[1]/900.
        r = rotations[t].T@reference[s, t]
        delta = rotations[t].T@(candidate[s, t]-reference[s, t])
        radial = r/np.linalg.norm(r)
        cross = np.cross(r, velocity)
        cross /= np.linalg.norm(cross)
        along = np.cross(cross, radial)
        R, A, C = delta@radial, delta@along, delta@cross
        out[s, t] = float(np.sqrt(.98**2*R*R+(A*A+C*C)/49.))
    return out


def solution(path):
    with np.load(path) as f:
        return f["states"][:, :, :3].copy(), [str(s) for s in f["satellites"]], f["times_s"].copy()


def main():
    folder = run_dir()
    frame = O2.Frame(O2.Finals(ROOT/"data/stage2/finals2000A.all"), subdaily=True)
    report, pooled = dict(dates={}), {"default": [0, 0, 0, 0], "gradients": [0, 0, 0, 0]}
    for day, (name, default, gradient) in DATES.items():
        evaluation = json.loads((ROOT/"Opus_Fork/results"/name).read_text())
        provenance, arms = evaluation["provenance"], evaluation["domains"]["full"]["arms"]
        reference = O1.read_sp3(provenance["igs_final"]["path"])
        nga = O1.read_sp3(provenance["NGA"]["path"])
        fixture = ROOT/FIXTURES[day]/"fixture.json"
        origin = int(json.loads(fixture.read_text())["context"]["origin_ns"])
        ours = {}
        for label, arm in (("default", default), ("gradients", gradient)):
            assert provenance[arm]["fixture_sha256"] == sha(fixture), (day, arm)
            states, sats, times = solution(provenance[arm]["solution"])
            ours[label] = O1.solution_ecef(states, sats, times, origin, frame)
        start, stop = origin+10*10**9, origin+10*10**9+int((23*3600+45*60)*1e9)
        keys = {k for k in set(reference) & set(nga) & set(ours["default"]) & set(ours["gradients"]) if start <= k[1] <= stop}
        u_nga = per_sample_ure(reference, nga, frame, keys)
        entry = dict(samples=len(keys), epochs=len({t for _, t in keys}), production_samples=arms["NGA"]["raw"]["samples"])
        for label, arm in (("default", default), ("gradients", gradient)):
            u = per_sample_ure(reference, ours[label], frame, keys)
            rms = float(np.sqrt(np.mean([v*v for v in u.values()])))
            assert abs(rms-arms[arm]["raw"]["rms_orbit_ure_m"]) <= SCORE_TOL_M, (day, arm, rms)
            epochs = sorted({t for _, t in keys})
            at = {t: [k for k in keys if k[1] == t] for t in epochs}
            lower_epochs = sum(np.sqrt(np.mean([u[k]**2 for k in at[t]])) < np.sqrt(np.mean([u_nga[k]**2 for k in at[t]]))
                               for t in epochs)
            lower_samples = sum(u[k] < u_nga[k] for k in keys)
            entry[label] = dict(arm=arm, ure_cm=rms*100, epoch_share=lower_epochs/len(epochs),
                                sample_share=lower_samples/len(keys), epochs_lower=lower_epochs,
                                samples_lower=lower_samples)
            p = pooled[label]
            p[0] += lower_epochs; p[1] += len(epochs); p[2] += lower_samples; p[3] += len(keys)
        entry["nga_ure_cm"] = float(np.sqrt(np.mean([v*v for v in u_nga.values()])))*100
        assert abs(entry["nga_ure_cm"]/100-arms["NGA"]["raw"]["rms_orbit_ure_m"]) <= SCORE_TOL_M, (day, "NGA")
        report["dates"][day] = entry
        print(day, {lab: (round(entry[lab]["epoch_share"], 3), round(entry[lab]["sample_share"], 3))
                    for lab in ("default", "gradients")}, flush=True)
    report["pooled"] = {lab: dict(epoch_share=p[0]/p[1], epochs=p[1], sample_share=p[2]/p[3], samples=p[3])
                        for lab, p in pooled.items()}
    print("pooled", json.dumps(report["pooled"]), flush=True)
    (folder/"ure_time_share.json").write_text(json.dumps(report, indent=1, default=float)+"\n")


if __name__ == "__main__":
    main()
