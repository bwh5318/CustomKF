#!/usr/bin/env bash
# Network fixtures (PROTOCOL.md §5): one root-guarded Opus_Fork.prepare per network and date, serially, with the
# station list of station_lists.py (acquired stations, alphabetical, LF line endings). Appends to fixtures.tsv
# (network, date, run folder, status, stations) and skips any network/date already prepared, so it can be rerun.
cd "$(dirname "$0")/../../.." || exit 1   # the repository root
PY=C:/anaconda/python.exe
OUT=Opus_Fork/experiments/networks/fixtures.tsv
LISTS=$($PY -m Opus_Fork.experiments.networks.station_lists 2> Opus_Fork/experiments/networks/dropped.txt) \
  || { cat Opus_Fork/experiments/networks/dropped.txt; exit 1; }
[ -f $OUT ] || printf "network\tdate\trun\tstatus\tstations\n" > $OUT
echo "$LISTS" | while read net day stations; do
  if awk -F'\t' -v n="$net" -v d="$day" '$1==n && $2==d && $4=="prepared" {found=1} END {exit !found}' $OUT; then
    echo "$net $day already prepared"; continue
  fi
  log=$($PY -m customkf.guard --profile usage75 --timeout 1800 -- Opus_Fork.prepare --day $day --start 00:00 --epochs 144 \
        --network 25 --stations $stations --previous-day-nav --per-epoch-nav 2>&1)
  run=$(echo "$log" | grep -o 'Logs: .*' | sed 's/Logs: //; s/\\/\//g; s/.*customKF\///; s/[[:space:]]*$//')
  status=$(grep -o '"status": "[a-z_]*"' "$run/step.json" 2>/dev/null | head -1 | cut -d'"' -f4)
  printf "%s\t%s\t%s\t%s\t%s\n" "$net" "$day" "$run" "${status:-FAILED}" "$stations" >> $OUT
  echo "$net $day -> $run ${status:-FAILED}"
done
