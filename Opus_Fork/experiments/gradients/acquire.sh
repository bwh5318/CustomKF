#!/usr/bin/env bash
# Acquisition of external gradient inputs (BACKLOG B14; Astra GRADIENT_ADVICE.md). Network and files only, no Python.
# Writes into Opus_Fork/datastore/gradients/ (git-ignored data) and an acquisition record (tab-separated) beside this
# script: URL, local file, HTTP status, server Last-Modified, bytes, SHA-256, retrieval UTC.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/Opus_Fork/datastore/gradients"
LOG="$(dirname "$0")/acquisition_record.tsv"
BASE=https://vmf.geo.tuwien.ac.at
mkdir -p "$OUT/gpt3" "$OUT/GRAD_OP"
[ -f "$LOG" ] || printf "url\tfile\thttp_status\tlast_modified\tbytes\tsha256\tretrieved_utc\n" > "$LOG"

get() {   # url, local path
  local url="$1" file="$2" hdr status lm
  hdr="$(mktemp)"
  status=$(curl -s -m 300 -A "customKF research (GNSS orbit study)" -D "$hdr" -o "$file" -w "%{http_code}" "$url")
  lm=$(grep -i "^last-modified:" "$hdr" | sed 's/^[^:]*: *//; s/\r//')
  rm -f "$hdr"
  if [ "$status" != "200" ]; then rm -f "$file"; fi
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$url" "${file#$ROOT/}" "$status" "$lm" \
    "$( [ -f "$file" ] && stat -c %s "$file" || echo 0)" "$( [ -f "$file" ] && sha256sum "$file" | cut -d' ' -f1 || echo -)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
  echo "$status $url"
}

for f in gpt3_1.grd gpt3_5.grd gpt3_1.f90 gpt3_5.f90 gpt3_1.m gpt3_5.m; do
  get "$BASE/codes/$f" "$OUT/gpt3/$f"
done
# Operational site-wise gradients: Aug 1-8 (studied days), and each untouched date with its neighbours.
for d in 213 214 215 216 217 218 219 220 156 157 158 170 171 172 173 174 175 186 187 188 203 204 205; do
  get "$BASE/trop_products/GNSS/GRAD/GRAD_OP/daily/2026/2026$d.grad_g" "$OUT/GRAD_OP/2026$d.grad_g"
done
# Documentation: the GRAD paper (product definition, conventions) and the VMF3/GPT3 paper.
get "$BASE/documentation/Landskron%20and%20Boehm,%202018%20%20%20(GRAD).pdf" "$OUT/docs/Landskron_Boehm_2018_GRAD.pdf"
get "$BASE/documentation/Landskron%20and%20Boehm,%202018%20%20%20(VMF3+GPT3).pdf" "$OUT/docs/Landskron_Boehm_2018_VMF3_GPT3.pdf"
