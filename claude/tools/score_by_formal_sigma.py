"""Exploratory: pool Stage 5b expanded-long IGS scores by the estimator's own formal sigma.

Read-only JSON arithmetic (no guard needed). Thresholds here are EXPLORATORY and were
chosen after seeing the IGS comparison, so they must not be quoted as a predeclared
screening rule. Usage (from E:\\pythontests\\customKF):
    C:\\anaconda\\python.exe claude\\tools\\score_by_formal_sigma.py claude\\diagnostics\\g18_diagnostic.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "validation/stage5b/20260910T203254Z/completion-20260910T205844Z/evaluation/evaluation.json"


def pooled(items, kind):
    n = sum(v[kind]["samples"] for _, v in items)
    if not n:
        return 0, float("nan"), [float("nan")] * 3
    d3 = (sum(v[kind]["rms_3d_m"] ** 2 * v[kind]["samples"] for _, v in items) / n) ** 0.5
    rac = [(sum(v[kind]["rms_rac_m"][i] ** 2 * v[kind]["samples"] for _, v in items) / n) ** 0.5 for i in range(3)]
    return n, d3, rac


def main():
    diag = json.loads(Path(sys.argv[1]).read_text())
    ev = json.loads(EV.read_text())
    for case in ("eight-long", "expanded-long"):
        sig = diag["cases"][case]["formal_position_sigma_m"]
        per = ev["per_satellite"][case]
        print(f"== {case}")
        print("  sat  formal_sigma_m  initial_3D  fit_3D  fit/sigma")
        for s in sorted(per, key=lambda s: sig.get(s, 0)):
            print(f"  {s}  {sig.get(s, float('nan')):12.2f}  {per[s]['initial']['rms_3d_m']:9.2f}  {per[s]['fit']['rms_3d_m']:7.2f}  {per[s]['fit']['rms_3d_m'] / sig[s]:.2f}")
        for lo, hi in ((0, 5), (5, 100), (100, 1e9)):
            items = [(s, v) for s, v in per.items() if lo <= sig.get(s, float("nan")) < hi]
            for kind in ("initial", "fit"):
                n, d3, rac = pooled(items, kind)
                print(f"  formal sigma [{lo},{hi}) m: {len(items):2d} sats, {kind:7s} 3D={d3:8.3f} RAC={'/'.join(f'{x:.2f}' for x in rac)} n={n}")


if __name__ == "__main__":
    main()
