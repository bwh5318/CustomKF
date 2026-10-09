#!/usr/bin/env bash
# New-date test, amendment A1: score U-elw13-0627 and N-op-0627 together (U the baseline, NGA PE added by the
# evaluator), then the matched analysis. One root-guarded job at a time (usage75). Written before U completed.
cd "$(dirname "$0")/../../.." || exit 1   # the repository root
PY=C:/anaconda/python.exe
fx=runs/20261004T151035Z-0225f559/fixture.json
final() { c=$(ls -d Opus_Fork/runs/*-fit-$1 | tail -1)
          grep -q '"status": "long_fit_complete' $c/validation.json || return 1
          echo "$c/$(grep -o '"final": "[^"]*"' $c/validation.json | cut -d'"' -f4)"; }
u=$(final U-elw13-0627) || { echo "U-elw13-0627 is not complete"; exit 1; }
n=$(final N-op-0627) || { echo "N-op-0627 is not complete"; exit 1; }
$PY -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- Opus_Fork.evaluate --day 2026-06-27 \
    --out-name newdate_matched_20260627 --baseline U --arm U $u $fx --arm N-op $n $fx --domain full 00:00 23:45 \
    > /dev/null 2>&1
[ -f Opus_Fork/results/newdate_matched_20260627.json ] && echo "scored" || { echo "evaluation FAILED"; exit 1; }
$PY -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- \
    Opus_Fork.experiments.gradients.analyze_newdate_matched 2>&1 | grep -E "^\{|Logs:|REFUSED"
