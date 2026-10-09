"""Frozen constants and helpers for the August-6 native-gap validation (Opus, isolated).

Assignment: claude/reviews/OPUS_AUG6_NATIVE_GAP_VALIDATION_HANDOFF.md.
Frozen contrast: claude/experiments/native_gap_aug6_validation/PROTOCOL.md.
Nothing here writes outside Opus_Fork/ or guard-created runs/ folders.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from customkf.prepare_stage2 import ROOT, sha

HERE = Path(__file__).resolve().parent
RESULTS = ROOT/'Opus_Fork/results/native_gap_aug6_validation'
RUNS = ROOT/'Opus_Fork/runs'
DAY = '2026-08-06'

BASE = 'claude/runs/20260913T190407Z-roadmap-bench/prepare-06-long/fixture.json'
CAND = 'runs/20260921T231420Z-a41ef8ce/candidate_fixture.json'
CONFIG = 'claude/experiments/cross_date_preparation/config.json'
PROTOCOL = 'claude/experiments/native_gap_aug6_validation/PROTOCOL.md'
CHAIN = 'claude/reviews/NATIVE_GAP_CLASSIFICATION_AND_AUG6.manifest.json'
HANDOFF = 'claude/reviews/OPUS_AUG6_NATIVE_GAP_VALIDATION_HANDOFF.md'
PREFLIGHT = 'runs/20260921T231420Z-a41ef8ce'
REFERENCE = 'claude/data/day218/IGS0OPSRAP_20262180000_01D_15M_ORB.SP3.gz'
REPRO_FIXTURE = 'runs/20260912T161029Z-0ddb71b3/fixture.json'
REPRO_EXAMPLE = 'runs/20260920T155236Z-7cdcd2c2/reproduction.json'

# Supplied by the handoff; asserted before anything launches.
PINS = {
    BASE: '20776401ffe20f18ccdd5be58da0c7d42e4a3f11179d44380c9fbc632f68eee8',
    CAND: 'b751f77aac3f8c7125d9fb9aa8f95a5b5b3d02fe450369bb368c052c79866b15',
    CONFIG: '6b851bee09afe0d52aea85ab2a812c95243f4879574a4fc1c3725628b28af828',
    PROTOCOL: '2cfb1e478569cd473831965ab72b6932e6e190e09fdc9f5623448814a01f9ade',
    CHAIN: 'fda4132b3a25b66480118e59da07516166b5505764610a91ffe04133215f0e2b',
    REFERENCE: '41b2a2dac5c8fddefae0cfb81df10eabcfc4fd7f33bbf7c9a12027a6aba2f359',
}
CONFIG_VALUE = dict(nominal='unit', estimate=[0, 1, 2, 3, 4], prior_sigma_mps2={})

BASELINE, CANDIDATE = '2026-08-06-baseline14', '2026-08-06-nativegap14'
ARMS = {BASELINE: dict(phase='baseline', fixture=BASE), CANDIDATE: dict(phase='candidate', fixture=CAND)}
ORDER = [BASELINE, CANDIDATE]

# Cumulative (guarded, active-wall) seconds, never reset or pooled.
PHASES = {'readiness': (900, 1200), 'baseline': (5400, 7200), 'candidate': (5400, 7200), 'audit': (1200, 1800)}
TOTAL = (12900, 17400)

EXPECT = dict(code_rows=15635, phase_rows={BASE: 15523, CAND: 15521}, eligible_arcs=601,
              residuals={BASE: 31158, CAND: 31156}, retained=1013, local=5616, satellites=26, epochs=144)
LOST = [('NNOR', 'G18', 67), ('GLPS', 'G24', 108)]
SPLITS = {'NNOR:G18:24', 'GLPS:G24:37', 'GUAM:G28:34'}
CONTROLS = ['G18', 'G24', 'G28', 'G07', 'G21', 'G16']


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def write(p, value):
    Path(p).write_text(json.dumps(value, indent=2, allow_nan=False, default=lambda x: x.tolist() if hasattr(x, 'tolist') else str(x))+'\n')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def pins(folder):
    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def rel(p):
    return Path(p).resolve().relative_to(ROOT.resolve()).as_posix()
