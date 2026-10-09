"""Guarded bench evaluation: claude.roadmap.long_evaluate with references from data/stage3 or claude/data/day<DOY>.

    python -m customkf.guard -- claude.roadmap.bench_evaluate (same arguments as long_evaluate)

The scoring code is long_evaluate's, unchanged; only the reference loader is swapped for BenchReference,
which falls back to the original pinned data/stage3 product whenever it exists.
"""
import claude.roadmap.long_evaluate as long_evaluate
from claude.roadmap.bench_data import BenchReference

long_evaluate.DatedReference = BenchReference

if __name__ == "__main__":
    long_evaluate.main()
