"""Guarded eclipse inventory for bench days: claude.roadmap.beta_angles with BenchReference.

    python -m customkf.guard -- claude.roadmap.bench_beta --day 2026-08-04 --start 00:00 --end 23:45
"""
import claude.roadmap.beta_angles as beta_angles
from claude.roadmap.bench_data import BenchReference

beta_angles.DatedReference = BenchReference

if __name__ == "__main__":
    beta_angles.main()
