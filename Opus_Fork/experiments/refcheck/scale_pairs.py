"""Pairwise per-epoch Helmert-scale breathing between ours, IGS final, IGS rapid and NGA PE (protocol: PROTOCOL.md here).

    python -m customkf.guard --profile usage75 --timeout 600 -- Opus_Fork.experiments.refcheck.scale_pairs

Evaluation only. Writes scale_pairs.json in the run folder and results/refcheck_scale_pairs.json.
"""
import json
import os
from pathlib import Path

import numpy as np

from Opus_Fork.experiments.review_fixes.check_fixes import SD
from Opus_Fork.experiments.sensitivity.analyze import harm

PAIRS = (("ours", "final"), ("ours", "rapid"), ("ours", "NGA"), ("NGA", "final"), ("rapid", "final"), ("NGA", "rapid"))


def hourly(scale_by_ns, midnight):
    ns = np.array(sorted(scale_by_ns))
    s = np.array([scale_by_ns[k] for k in ns])
    hours = (ns-midnight)/3600e9
    return [float(s[(hours >= h) & (hours < h+1)].mean()) for h in range(24)]


def day_series(day, solution, fixture, eop):
    from Opus_Fork import dip_nga
    from Opus_Fork.evaluate import load_reference, midnight_of
    from Opus_Fork.score import helmert_residual
    midnight = midnight_of(day)
    products, prov = {}, {}
    products["final"], prov["final"] = load_reference("reference_igs_final", day, midnight, eop, "IGS final", "IGc20")
    products["rapid"], prov["rapid"] = load_reference("reference_igs_rapid", day, midnight, eop, "IGS rapid", "IGc20")
    products["NGA"], prov["NGA"] = load_reference("reference_nga_pe", day, midnight, eop, "NGA PE", "WGS84", legacy="GPS")
    products["ours"], prov["ours"] = dip_nga.load_solution(solution, fixture, eop, midnight)
    common = set(products["final"].keys())
    for p in products.values():
        common &= p.keys()
    scales = {}
    for a, b in PAIRS:
        _, params = helmert_residual(products[b], products[a], common)
        scales[f"{a}-{b}"] = {ns: q["scale"]*1e9 for ns, q in params.items()}
    epochs = sorted(set.intersection(*(set(s) for s in scales.values())))
    def closure(x, y, z):
        c = np.array([scales[x][e]-scales[y][e]-scales[z][e] for e in epochs])
        return dict(max_abs_ppb=float(np.max(np.abs(c))), rms_ppb=float(np.sqrt(np.mean(c**2))))
    out = dict(samples=len(common), epochs=len(epochs), satellites=len({s for s, _ in common}), provenance=prov,
               closure=dict(via_NGA=closure("ours-final", "ours-NGA", "NGA-final"),
                            via_rapid=closure("ours-final", "ours-rapid", "rapid-final")), pairs={})
    for name, s in scales.items():
        series = hourly(s, midnight)
        out["pairs"][name] = dict(hourly_scale_ppb=series, harmonics=harm(series))
    return out


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    from Opus_Fork.experiments.subdaily import sd_scoring
    from customkf.frames import EarthOrientation
    from Opus_Fork.paths import STAGE2, RESULTS
    sd_scoring.install()
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    report = dict(status="diagnostic_consistency_check_not_attribution", protocol_sha256=None, days={})
    import hashlib
    report["protocol_sha256"] = hashlib.sha256((Path(__file__).parent/"PROTOCOL.md").read_bytes()).hexdigest()
    for solution, fixture, day in SD:
        report["days"][day] = day_series(day, solution, fixture, eop)
        d = report["days"][day]
        print(f"{day}: {d['samples']} samples, {d['epochs']} epochs; closure via NGA max {d['closure']['via_NGA']['max_abs_ppb']:.2e}"
              f", via rapid max {d['closure']['via_rapid']['max_abs_ppb']:.2e} ppb", flush=True)
        for name, p in d["pairs"].items():
            h = p["harmonics"]
            print(f"   {name:12s} mean {h['mean']:+.3f}  12h {h['amp12']:.3f}@{h['peak12_ut']:4.1f}h  24h {h['amp24']:.3f}@{h['peak24_ut']:4.1f}h",
                  flush=True)
    days = list(report["days"])
    repetition = {}
    for name in report["days"][days[0]]["pairs"]:
        series = {d: np.array(report["days"][d]["pairs"][name]["hourly_scale_ppb"]) for d in days}
        repetition[name] = {d: float(np.corrcoef(series[d], np.mean([series[o] for o in days if o != d], axis=0))[0, 1])
                            for d in days}
        print(f"day repetition {name:12s} " + " ".join(f"{d[5:]}:{r:+.2f}" for d, r in repetition[name].items()), flush=True)
    report["day_repetition_corr_with_other_days_mean"] = repetition
    text = json.dumps(report, indent=1, default=float)+"\n"
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"scale_pairs.json").write_text(text)
    (RESULTS/"refcheck_scale_pairs.json").write_text(text)


if __name__ == "__main__":
    main()
