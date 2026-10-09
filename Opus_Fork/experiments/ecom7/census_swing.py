"""12 h harmonic of the pooled hourly radial residual in dynamics-only census fits, by day and variant.

Follow-up to `results/ECOM7P_HOLDOUT_RESULTS.md`: is Aug 7's missing 12 h common-height swing a property of the
day (it would be missing from the census too) or of the station POD on Aug 7's fixture (the census would still
show it)? Same method as `Opus_Fork/dip_mechanism.py` (Aug 2 census: E5 1.33, E5P 1.22, E7 0.57 cm).

    ... -- Opus_Fork.experiments.ecom7.census_swing results/reference_census_2026-08-02.json [more census JSONs]

For every file and variant: all satellites, and the satellites common to every file given (so a day's
rejections cannot masquerade as a day effect). Also per block. No fit; reads census JSON only.
"""
import json
import os
import sys
from pathlib import Path
import numpy as np

from Opus_Fork.paths import ROOT


def harmonic_amplitudes(hourly):
    h = np.arange(24)+0.5
    y = np.array([np.nan if v is None else v for v in hourly])
    m = np.isfinite(y)
    w = 2*np.pi/24
    a = np.column_stack([np.ones(m.sum()), np.cos(w*h[m]), np.sin(w*h[m]), np.cos(2*w*h[m]), np.sin(2*w*h[m])])
    c, *_ = np.linalg.lstsq(a, y[m], rcond=None)
    # Phase: UT hour of the first 12 h maximum.
    peak12 = (np.degrees(np.arctan2(c[4], c[3])) % 360)/360*12
    return dict(mean=round(float(c[0]), 3), amp_24h=round(float(np.hypot(c[1], c[2])), 3),
                amp_12h=round(float(np.hypot(c[3], c[4])), 3), peak_12h_ut=round(float(peak12), 2))


def pooled(census, variant, keep):
    acc = {h: [] for h in range(24)}
    n = 0
    for s, v in census["satellites"].items():
        if not keep(s, v):
            continue
        series = v.get("variants", {}).get(variant, {}).get("series_cm", [])
        n += bool(series)
        for hour, rr, _, _ in series:
            if hour < 24:
                acc[int(hour)].append(rr)
    hourly = [float(np.mean(acc[h])) if acc[h] else None for h in range(24)]
    return harmonic_amplitudes(hourly) | dict(satellites=n, hourly=[None if x is None else round(x, 3) for x in hourly])


def per_satellite(census, variant, keep):
    """Each satellite's own 12 h UT harmonic of its radial residual (cm) and the coherence of their phases.

    coherence = |mean vector| / mean |vector|: 1 when every satellite peaks at the same UT, ~1/sqrt(N) when random.
    """
    h0, vec = {}, []
    w = 2*np.pi/24
    for s, v in sorted(census["satellites"].items()):
        if not keep(s, v):
            continue
        series = np.array(v.get("variants", {}).get(variant, {}).get("series_cm", []))
        if len(series) < 48:
            continue
        t, rr = series[:, 0], series[:, 1]
        a = np.column_stack([np.ones_like(t), np.cos(2*w*t), np.sin(2*w*t)])
        c, *_ = np.linalg.lstsq(a, rr, rcond=None)
        z = complex(c[1], c[2])
        vec.append(z)
        h0[s] = dict(amp_12h=round(abs(z), 3), peak_12h_ut=round((np.degrees(np.angle(z)) % 360)/360*12, 2),
                     block=v.get("block"))
    vec = np.array(vec)
    return dict(median_amp=round(float(np.median(abs(vec))), 3), coherence=round(float(abs(vec.mean())/abs(vec).mean()), 3),
                mean_vector_amp=round(float(abs(vec.mean())), 3), satellites=h0)


def fitted(census, variant):
    return {s for s, v in census["satellites"].items() if v.get("variants", {}).get(variant, {}).get("series_cm")}


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use a guard")
    files = [Path(p) if Path(p).is_absolute() else ROOT/"Opus_Fork"/p for p in sys.argv[1:]]
    data = {f.name: json.loads(f.read_text()) for f in files}
    variants = sorted(set.intersection(*(set(c["variants"]) for c in data.values())))
    common = set.intersection(*(fitted(c, v) for c in data.values() for v in variants))
    out = dict(status="diagnostic_not_accuracy_acceptance", common_satellites=sorted(common), files={})
    for name, c in data.items():
        entry = out["files"][name] = dict(day=c["day"], variants={})
        for v in variants:
            blocks = sorted({str(s.get("block")) for s in c["satellites"].values()})
            e = entry["variants"][v] = dict(all=pooled(c, v, lambda s, x: True),
                                            common=pooled(c, v, lambda s, x: s in common),
                                            by_block={b: pooled(c, v, lambda s, x, b=b: str(x.get("block")) == b) for b in blocks},
                                            per_satellite=per_satellite(c, v, lambda s, x: s in common))
            ps = e["per_satellite"]
            print(f"{c['day']} {v:4s} per-satellite 12h: median amp {ps['median_amp']:.2f}, coherence {ps['coherence']:.2f}, "
                  f"mean vector {ps['mean_vector_amp']:.2f}", flush=True)
            print(f"{c['day']} {v:4s} all: 12h {e['all']['amp_12h']:.2f} (peak {e['all']['peak_12h_ut']:4.1f} UT) "
                  f"24h {e['all']['amp_24h']:.2f} mean {e['all']['mean']:+.2f} n={e['all']['satellites']} | "
                  f"common: 12h {e['common']['amp_12h']:.2f} (peak {e['common']['peak_12h_ut']:4.1f}) n={e['common']['satellites']} | "
                  + " ".join(f"{b} {x['amp_12h']:.2f}" for b, x in e["by_block"].items() if x["satellites"]), flush=True)
    (Path(os.environ["CUSTOMKF_RUN_DIR"])/"census_swing.json").write_text(json.dumps(out, indent=1)+"\n")


if __name__ == "__main__":
    main()
