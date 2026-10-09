"""Deterministic date stream for PROTOCOL.md section 2. No data is read.

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.untouched_dates.draw_dates

Writes date_stream.json beside this file (window, exclusions, seed, full shuffled stream).
"""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
WINDOW = (date(2026, 6, 1), date(2026, 8, 27))
EXCLUDED = (date(2026, 7, 30), date(2026, 8, 9))
SEED = 20260929


def main():
    days = [WINDOW[0]+timedelta(n) for n in range((WINDOW[1]-WINDOW[0]).days+1)]
    eligible = [d for d in days if not EXCLUDED[0] <= d <= EXCLUDED[1]]
    stream = [d.isoformat() for d in eligible]
    random.Random(SEED).shuffle(stream)
    record = dict(protocol_sha256=hashlib.sha256((HERE/"PROTOCOL.md").read_bytes()).hexdigest(),
                  window=[d.isoformat() for d in WINDOW], excluded=[d.isoformat() for d in EXCLUDED], seed=SEED,
                  eligible=len(eligible), stream=stream)
    (HERE/"date_stream.json").write_text(json.dumps(record, indent=1)+"\n")
    print("first ten:", stream[:10])


if __name__ == "__main__":
    main()
