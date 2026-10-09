#!/usr/bin/env bash
# New-date test (NEW_DATE_PROTOCOL.md), after the newdate chain completes: the product, the production score, then
# the analysis. One root-guarded job at a time (usage75). Written before the fit completed.
cd "$(dirname "$0")/../../.." || exit 1   # the repository root
PY=C:/anaconda/python.exe
c=$(ls -d Opus_Fork/runs/*-fit-N-op-0627 | tail -1)
grep -q '"status": "long_fit_complete' $c/validation.json || { echo "N-op-0627 is not complete"; exit 1; }
final=$c/$(grep -o '"final": "[^"]*"' $c/validation.json | cut -d'"' -f4)
fx=runs/20261004T151035Z-0225f559/fixture.json
$PY -m customkf.guard --profile usage75 --threads 1 --timeout 900 -- Opus_Fork.export write --solution $final \
    --fixture $fx --day 2026-06-27 > /dev/null 2>&1 && echo "product written" || { echo "export FAILED"; exit 1; }
$PY -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- Opus_Fork.evaluate --day 2026-06-27 \
    --out-name newdate_20260627 --arm N-op $final $fx --domain full 00:00 23:45 > /dev/null 2>&1
[ -f Opus_Fork/results/newdate_20260627.json ] && echo "scored" || { echo "evaluation FAILED"; exit 1; }   # written by evaluate
$PY -m customkf.guard --profile usage75 --threads 1 --timeout 1800 -- Opus_Fork.experiments.gradients.analyze_newdate \
    2>&1 | grep -E "^\{|Logs:|REFUSED"
