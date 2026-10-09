#!/usr/bin/env bash
# Production scoring of the option-A validation (VALIDATION_PROTOCOL.md): per date, Opus_Fork.evaluate with the
# comparator (U), V-op and V-gpt3 (NGA PE added by the evaluator), one fork-guarded evaluation at a time.
# Writes Opus_Fork/results/gradval_YYYYMMDD.json. Run after the gradval chain has completed.
cd "$(dirname "$0")/../../.." || exit 1   # the repository root
PY=C:/anaconda/python.exe
R=Opus_Fork/runs
final() { c=$(ls -d $R/*-fit-$1 2>/dev/null | tail -1); [ -n "$c" ] || return 1
          f=$(grep -o '"final": "[^"]*"' $c/validation.json | cut -d'"' -f4); echo "$c/$f"; }
for spec in 0606:2026-06-06:runs/20260929T202245Z-21f63ba3:U-elw13-0606 \
            0620:2026-06-20:runs/20260929T203924Z-224f1e22:U-elw13-0620 \
            0623:2026-06-23:runs/20260929T201929Z-5b2b3e42:U-elw13-0623r \
            0706:2026-07-06:runs/20260929T204645Z-ba94e895:U-elw13-0706 \
            0723:2026-07-23:runs/20260929T203059Z-40b5a8d7:U-elw13-0723; do
  IFS=: read tag day fx comp <<< "$spec"
  out=gradval_${day//-/}
  $PY -m Opus_Fork.guard --profile fork8 --label eval-gradval-$tag -- Opus_Fork.evaluate --day $day --out-name $out \
      --baseline U --arm U $(final $comp) $fx/fixture.json --arm V-op $(final V-op-$tag) $fx/fixture.json \
      --arm V-gpt3 $(final V-gpt3-$tag) $fx/fixture.json --domain full 00:00 23:45 > /dev/null 2>&1
  src=$(ls -td $R/*eval-gradval-$tag | head -1)/$out.json
  if [ -f "$src" ]; then cp "$src" Opus_Fork/results/; echo "$tag scored"; else echo "$tag FAILED ($(ls -td $R/*eval-gradval-$tag | head -1))"; fi
done
