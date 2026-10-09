#!/usr/bin/env bash
# SP3 deliverables (user request, 7 Oct 2026). Run after the networks chain has completed; one root-guarded export
# at a time (usage75). The files themselves are git-ignored.
#   default_25st : the best rapid-candidate configuration (default, no gradients, 25 stations) on the five untouched
#                  dates. Header: retrospective inputs, local product type RAP.
#   S17_nga_like : 17 stations near NGA's monitor sites, default + GRAD operational gradients. Final latency, local
#                  type FIN.
#   S50_doubled  : 50 stations (S50e, ambiguity elimination), default + GRAD operational gradients. Final latency,
#                  local type FIN.
# Every file gets an explicit unique name: the exporter's default name would let configurations replace each other
# (Astra PI-09). An existing file is never overwritten. Then: deliverables/manifest.py writes sp3/README.md.
cd "$(dirname "$0")/.." || exit 1   # the repository root
PY=C:/anaconda/python.exe
R=Opus_Fork/runs
OUT=deliverables/sp3
final() { c=$(ls -d $R/*-fit-$1 2>/dev/null | tail -1); [ -n "$c" ] || return 1
          grep -q '"status": "long_fit_complete' $c/validation.json || return 1
          echo "$c/$(grep -o '"final": "[^"]*"' $c/validation.json | cut -d'"' -f4)"; }
network_fixture() { awk -F'\t' -v n="$1" -v d="$2" '$1==n && $2==d && $4=="prepared" {f=$3} END {if (f) print f"/fixture.json"}' \
                    Opus_Fork/experiments/networks/fixtures.tsv; }
export_one() {   # set, campaign label, day, fixture, product code
  local set=$1 label=$2 day=$3 fixture=$4 code=$5 sol out log run
  sol=$(final $label) || { echo "SKIP $set $day: $label is not complete"; return 0; }
  mkdir -p $OUT/$set
  out=$OUT/$set/OPUS0OPS${code}_${day//-/}_${set}.SP3
  [ -f "$out" ] && { echo "exists $out"; return 0; }
  log=$($PY -m customkf.guard --profile usage75 --threads 1 --timeout 900 -- Opus_Fork.export write \
        --solution $sol --fixture $fixture --day $day --out $out 2>&1)
  run=$(echo "$log" | grep -o 'Logs: .*' | tr -d '\r' | sed 's/Logs: //; s/\\/\//g')
  if [ -f "$out" ] && [ -f "$run/export.json" ]; then
    cp "$run/export.json" "${out%.SP3}.export.json"; echo "wrote $out"
  else
    echo "FAILED $set $day ($run)"
  fi
}
for spec in 0606:2026-06-06:runs/20260929T202245Z-21f63ba3:U-elw13-0606 \
            0620:2026-06-20:runs/20260929T203924Z-224f1e22:U-elw13-0620 \
            0623:2026-06-23:runs/20260929T201929Z-5b2b3e42:U-elw13-0623r \
            0706:2026-07-06:runs/20260929T204645Z-ba94e895:U-elw13-0706 \
            0723:2026-07-23:runs/20260929T203059Z-40b5a8d7:U-elw13-0723; do
  IFS=: read tag day fx comp <<< "$spec"
  export_one default_25st $comp $day $fx/fixture.json RAP
  export_one S17_nga_like S17-op-$tag $day $(network_fixture S17 $day) FIN
  export_one S50_doubled S50e-op-$tag $day $(network_fixture S50 $day) FIN
done
# The exporter also records its latest run in Opus_Fork/results/export_write.json (tracked); keep the tracked one.
git checkout -- Opus_Fork/results/export_write.json 2>/dev/null
$PY -m deliverables.manifest
