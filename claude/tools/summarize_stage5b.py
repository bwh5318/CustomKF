"""Read-only JSON summary of the Stage 5b completion archive (no numerics, no guard needed).

Usage (from E:\\pythontests\\customKF):
    C:\\anaconda\\python.exe claude\\tools\\summarize_stage5b.py
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z"
ev = json.loads((C / "evaluation/evaluation.json").read_text())


def fmt(s):
    return f"n={s['samples']:4d} 3D={s['rms_3d_m']:9.3f}  RAC=" + "/".join(f"{v:.2f}" for v in s["rms_rac_m"]) + f"  URE={s['rms_orbit_ure_m']:.3f}"


def pooled(items, kind="fit"):
    n = sum(v[kind]["samples"] for _, v in items)
    d3 = (sum(v[kind]["rms_3d_m"] ** 2 * v[kind]["samples"] for _, v in items) / n) ** 0.5
    rac = [(sum(v[kind]["rms_rac_m"][i] ** 2 * v[kind]["samples"] for _, v in items) / n) ** 0.5 for i in range(3)]
    return n, d3, rac


for block in ("common_scores", "long_common_scores", "full_scores"):
    print("==", block)
    for case, sc in ev[block].items():
        print(f"  {case:14s} initial {fmt(sc['initial'])}")
        print(f"  {case:14s} fit     {fmt(sc['fit'])}")

print("== per-satellite fit 3D RMS (m), full sample sets")
cases = list(ev["per_satellite"])
sats = sorted(set().union(*[set(ev["per_satellite"][c]) for c in cases]))
print("  sat   " + "  ".join(f"{c:>14s}" for c in cases) + "   expanded-init")
for s in sats:
    vals = []
    for c in cases:
        v = ev["per_satellite"][c].get(s)
        vals.append(f"{v['fit']['rms_3d_m']:14.2f}" if v else f"{'-':>14s}")
    ini = ev["per_satellite"]["expanded-long"].get(s)
    print(f"  {s}  " + "  ".join(vals) + (f"   {ini['initial']['rms_3d_m']:.2f}" if ini else ""))

pe = ev["per_satellite"]["expanded-long"]
tot = sum(v["fit"]["rms_3d_m"] ** 2 * v["fit"]["samples"] for v in pe.values())
print("== expanded-long squared-error share (top 5)")
for s, v in sorted(pe.items(), key=lambda kv: -kv[1]["fit"]["rms_3d_m"] ** 2 * kv[1]["fit"]["samples"])[:5]:
    print(f"  {s}: {100 * v['fit']['rms_3d_m'] ** 2 * v['fit']['samples'] / tot:.2f}%  rms={v['fit']['rms_3d_m']:.2f}")
ex = [(s, v) for s, v in pe.items() if s != "G18"]
for kind in ("initial", "fit"):
    n, d3, rac = pooled(ex, kind)
    print(f"  expanded-long excluding G18, {kind:7s}: 3D={d3:.3f} m RAC={'/'.join(f'{x:.2f}' for x in rac)} over {n} samples")
better = sum(v["fit"]["rms_3d_m"] < v["initial"]["rms_3d_m"] for _, v in pe.items())
print(f"  satellites where fit beats broadcast seed: {better} of {len(pe)}")

print("== station residual RMS")
for case, st in ev["station_residuals"].items():
    print(" ", case)
    for s, k in sorted(st.items()):
        print(f"    {s}: code n={k['code']['count']} rms={k['code']['rms_m']:.3f} m  phase n={k['phase']['count']} rms={k['phase']['rms_m'] * 1000:.2f} mm")

print("== coverage per satellite (stations; epochs with >=2 receivers)")
for case in ("eight-short", "eight-long", "expanded-long"):
    f = json.loads((C / f"{case}-prepare/fixture.json").read_text())
    satst, ep = defaultdict(set), defaultdict(lambda: defaultdict(set))
    for r in f["rows"]:
        satst[r["satellite"]].add(r["station"])
        ep[r["satellite"]][r["epoch"]].add(r["station"])
    print(" ", case, "epochs:", f["context"]["epoch_count"])
    print("   ", " ".join(f"{s}:{len(satst[s])}/{sum(len(v) >= 2 for v in ep[s].values())}" for s in sorted(satst)))

cv = json.loads((C / "validation.json").read_text())
print("== completion:", cv["status"], "| total guarded s:", round(cv["total_guarded_seconds"], 1),
      "| peak RSS MiB:", round(cv["peak_sampled_rss_mib"], 1), "| min avail GiB:", round(cv["minimum_system_available_gib"], 2))
