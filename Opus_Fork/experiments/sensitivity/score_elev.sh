#!/usr/bin/env bash
# Score the ELEVATION_PROTOCOL arms: per day, evaluate_sd with SD comparator, cut15s, elw13 (if complete) and NGA,
# then summarize against the frozen predictions. Run from any directory after the elev chain has finished.
cd "$(dirname "$0")/../../.." || exit 1   # the repository root
R=Opus_Fork/runs
D="--domain full 00:00 23:45 --domain early 00:00 16:00 --domain late 18:00 23:45 --domain noon 12:00 18:00"
final() { c=$(ls -d $R/*fit-$1 2>/dev/null | tail -1); [ -n "$c" ] || return 1; python -c "import json,sys;v=json.load(open('$c/validation.json'));sys.exit(0 if v['status'].startswith('long_fit_complete') else 1)" || return 1; echo $c/$(python -c "import json;print(json.load(open('$c/validation.json'))['final'])"); }
declare -A FIX=( [2]=$R/20260920T200910Z-prepare-31sat/fixture.json [3]=$R/20260922T225652Z-prepare-2026-08-03/fixture.json [4]=$R/20260922T230119Z-prepare-2026-08-04/fixture.json [5]=$R/20260922T230410Z-prepare-2026-08-05/fixture.json [7]=runs/20260920T155655Z-7b703635/fixture.json )
for d in 4 7 2 5 3; do
  args="--arm SD $(final SD-$d-25st) ${FIX[$d]}"
  for ch in cut15s elw13; do f=$(final E-$ch-$d) && args="$args --arm $ch $f ${FIX[$d]}"; done
  [ $d = 3 ] && f=$(final S-cut15-3) && args="$args --arm cut15s $f ${FIX[$d]}"
  python -m Opus_Fork.guard --profile fork8 --label eval-elev-$d -- Opus_Fork.experiments.subdaily.evaluate_sd --day 2026-08-0$d --out-name arm_elev_aug$d $args $D > /dev/null 2>&1
  cp $(ls -td $R/*eval-elev-$d | head -1)/arm_elev_aug$d.json Opus_Fork/results/ 2>/dev/null
done
python - <<'EOF'
import json, os
print("day  arm     URE cm (change)   R/A/C cm              3D cm   worst sat 3D change   NGA URE")
summary = {}
for d in (4, 7, 2, 5, 3):
    p = f"Opus_Fork/results/arm_elev_aug{d}.json"
    if not os.path.exists(p):
        continue
    a = json.load(open(p))["domains"]["full"]["arms"]
    sd = a["SD"]["raw"]["rms_orbit_ure_m"]
    for arm in ("SD", "cut15s", "elw13"):
        if arm not in a:
            continue
        r = a[arm]["raw"]
        worst = max(((a[arm]["per_satellite"][s]["rms_3d_m"]-a["SD"]["per_satellite"][s]["rms_3d_m"])*100, s) for s in a["SD"]["per_satellite"])
        ch = 100*(r["rms_orbit_ure_m"]/sd-1)
        summary.setdefault(arm, {})[d] = dict(ure=r["rms_orbit_ure_m"]*100, change=ch, radial=r["rms_rac_m"][0]*100,
                                            radial_sd=a["SD"]["raw"]["rms_rac_m"][0]*100, worst=worst)
        print(f"Aug {d} {arm:6s} {r['rms_orbit_ure_m']*100:6.3f} ({ch:+5.1f}%)  {[round(x*100,2) for x in r['rms_rac_m']]}  {r['rms_3d_m']*100:6.2f}  {worst[0]:+5.1f} ({worst[1]})   {a['NGA']['raw']['rms_orbit_ure_m']*100:.3f}")
for arm in ("cut15s", "elw13"):
    s = summary.get(arm, {})
    held = {d: v for d, v in s.items() if d != 3}
    if not held:
        continue
    better = sum(v["change"] < 0 for v in held.values())
    worse = sum(v["change"] > 0 for v in held.values())
    mean = sum(v["change"] for v in held.values())/len(held)
    radial_ok = all(v["radial"] <= 1.03*v["radial_sd"] for v in held.values())
    worst = max(v["worst"][0] for v in held.values())
    print(f"{arm}: held-out days {sorted(held)} better {better}/{len(held)}, worse {worse}, mean change {mean:+.2f}%, radial within +3%: {radial_ok}, worst sat 3D {worst:+.1f} cm")
json.dump(summary, open("Opus_Fork/results/elevation_summary.json", "w"), indent=1, default=str)
EOF
