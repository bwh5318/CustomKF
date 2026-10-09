#!/usr/bin/env bash
# GRAD operational gradient files for the optional gradient model (user adoption, 3 Oct 2026), for any day:
#     bash Opus_Fork/experiments/gradients/acquire_day.sh 2026-09-14 [2026-09-15 ...]
# For each day D, the files a standard 24 h arc needs (gradients.arc_days: D-1, D and D+1). Network and files only,
# no Python. A file already present is never downloaded again, so its first row in the acquisition record (server
# Last-Modified, retrieval time, SHA-256) stays its as-of evidence; a file that is not yet published (HTTP 404) is
# recorded and left absent, and the fit refuses until it exists.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/Opus_Fork/datastore/gradients/GRAD_OP"
LOG="$(dirname "$0")/acquisition_record.tsv"
BASE=https://vmf.geo.tuwien.ac.at/trop_products/GNSS/GRAD/GRAD_OP/daily
mkdir -p "$OUT"
[ $# -gt 0 ] || { echo "usage: $0 YYYY-MM-DD [...]" >&2; exit 2; }

get() {   # url, local path (as acquire.sh)
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

for day in "$@"; do
  date -u -d "$day" +%Y%j > /dev/null 2>&1 || { echo "not a date: $day" >&2; exit 2; }
  for offset in -1 0 1; do
    name=$(date -u -d "$day $offset day" +%Y%j)
    file="$OUT/$name.grad_g"
    if [ -f "$file" ]; then echo "present $name.grad_g"; continue; fi
    get "$BASE/${name:0:4}/$name.grad_g" "$file"
  done
done
