"""Guarded worker: physical initialization of one August-6 arm. No precise products.

    initialize state <arm> --trajectories C0 C1 C2 C3 [--baseline-state STATE]

Baseline: clock seeds, wind-up branches and ambiguity origins from its own x=0
caches, with the unused-empty-clock adapter checked bitwise against the pinned
LongPilot.initial_state on every used seed.

Candidate: first proves context, seeds, case and every non-arc row field equal to
the baseline, builds the reverse arc map, and requires exactly the frozen splits
and the two lost phase rows. Only then does it reuse the baseline's x=0 dynamics
caches, whose metadata (baseline fixture, config, span, per-satellite keys) is
validated and left untouched. Its state is bound to its own fixture.

Both arms: finite strict-JSON state, the full x=0 forward residual/sigma vectors
at their expected lengths, a finite objective, and the frozen parameter counts.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
import warnings
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from claude.tools.dated_fixture import restore
from claude.roadmap.long_pilot import LongPilot
from claude.roadmap.traj_cache import cached_products
from claude.reviews.opus_cross_date_observation_audit.empty_epoch_state import initial_state_omitting_unused
from Opus_Fork.experiments.native_gap_aug6_validation.common import (
    BASE, CONFIG, CONFIG_VALUE, ARMS, CANDIDATE, EXPECT, LOST, SPLITS, read, write, rel)


class CachedPilot(LongPilot):
    def products(self, x):
        assert np.all(x == 0)
        return self.zero_products


def check_caches(files, duration, n_names):
    """Baseline-bound x=0 caches: metadata validated, never relabelled."""
    base_sha, config_sha = sha(ROOT/BASE), sha(ROOT/CONFIG)
    zero_sha = hashlib.sha256(np.ascontiguousarray(np.zeros(n_names)).tobytes()).hexdigest()
    provenance = []
    for f in files:
        meta_path = f.with_name('trajectories.json')
        meta = read(meta_path)
        assert meta['status'] == 'trajectory_cache' and meta['cache_sha256'] == sha(f), f
        assert meta['fixture_sha256'] == base_sha and meta['config_sha256'] == config_sha, f
        assert meta['x_sha256'] == zero_sha, ('cache is not the x=0 point', f)
        with np.load(f) as z:
            assert z['times'][0] == 0 and z['times'][-1] == duration, f
        provenance.append(dict(path=rel(f), sha256=sha(f), metadata_sha256=sha(meta_path), group=meta['group'],
                               groups=meta['groups'], satellites=meta['satellites'], original_fixture_sha256=base_sha))
    assert sorted(p['group'] for p in provenance) == [0, 1, 2, 3] and all(p['groups'] == 4 for p in provenance)
    return provenance


def compare_fixtures(base, cand):
    assert cand['context'] == base['context'] and cand['seeds'] == base['seeds'] and cand['case'] == base['case']
    groups, reverse = defaultdict(set), {}
    for i, (r, n) in enumerate(zip(base['rows'], cand['rows'], strict=True)):
        assert {k: v for k, v in r.items() if k != 'arc'} == {k: v for k, v in n.items() if k != 'arc'}, ('non-arc field changed', i)
        groups[r['arc']].add(n['arc'])
        assert reverse.get(n['arc'], r['arc']) == r['arc'], ('arc merging', n['arc'])
        reverse[n['arc']] = r['arc']
    splits = {k: sorted(v) for k, v in groups.items() if len(v) > 1}
    assert set(splits) == SPLITS, splits
    bc, nc = Counter(r['arc'] for r in base['rows']), Counter(r['arc'] for r in cand['rows'])
    lost = [(n['station'], n['satellite'], n['epoch'], r['arc'], n['arc'])
            for r, n in zip(base['rows'], cand['rows']) if bc[r['arc']] >= 3 and nc[n['arc']] < 3]
    gained = [(n['station'], n['satellite'], n['epoch']) for r, n in zip(base['rows'], cand['rows'])
              if bc[r['arc']] < 3 and nc[n['arc']] >= 3]
    assert sorted(x[:3] for x in lost) == sorted(LOST) and not gained, (lost, gained)
    renamed = sorted(n for n, o in reverse.items() if n != o and o not in splits)
    return dict(splits=splits, split_row_counts={k: {a: nc[a] for a in v} for k, v in splits.items()},
                lost_phase_rows=[dict(station=s, satellite=t, epoch=e, old_arc=o, new_arc=a) for s, t, e, o, a in lost],
                gained_phase_rows=gained, renamed_unchanged_arcs=len(renamed), renamed_examples=renamed[:12],
                reverse_map=reverse)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['state'])
    ap.add_argument('arm', choices=list(ARMS))
    ap.add_argument('--trajectories', nargs=4, type=Path, required=True)
    ap.add_argument('--baseline-state', type=Path)
    a = ap.parse_args()
    from customkf.stage5_pilot import forbid_precise_product_reads
    sys.addaudithook(forbid_precise_product_reads)
    out = Path(os.environ['CUSTOMKF_RUN_DIR'])
    fixture_path = ROOT/ARMS[a.arm]['fixture']
    assert read(ROOT/CONFIG) == CONFIG_VALUE
    fx = read(fixture_path)
    comparison = None
    if a.arm == CANDIDATE:
        assert a.baseline_state, 'candidate needs the baseline state'
        comparison = compare_fixtures(read(ROOT/BASE), fx)
    c, rows, seeds = restore(fixture_path)
    estimate = tuple(CONFIG_VALUE['estimate'])
    pilot = CachedPilot(c, rows, seeds, estimate=estimate, state=dict(clock_seeds=[], windup=[], amb_origins={}))
    caches = check_caches(a.trajectories, c['duration_s'], len(pilot.names))
    pilot.zero_products = cached_products(pilot, np.zeros(len(pilot.names)), a.trajectories)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        old = LongPilot.initial_state(pilot)
    new, omitted = initial_state_omitting_unused(pilot)
    used = {(r['epoch'], r['station']) for r in rows}
    oldseeds, newseeds = dict(old['clock_seeds']), dict(new['clock_seeds'])
    assert set(newseeds) == used and set(omitted) == set(oldseeds)-used
    np.testing.assert_array_equal([oldseeds[k] for k in sorted(used)], [newseeds[k] for k in sorted(used)])
    assert all(np.isfinite(v) for v in newseeds.values()) and all(not np.isfinite(oldseeds[k]) for k in omitted)
    np.testing.assert_array_equal(old['windup'], new['windup'])
    assert old['amb_origins'] == new['amb_origins']
    assert np.isfinite(new['windup']).all() and all(np.isfinite(list(new['amb_origins'].values())))
    new.update(fixture_sha256=sha(fixture_path), config_sha256=sha(ROOT/CONFIG))
    (out/'state.json').write_text(json.dumps(new, allow_nan=False)+'\n')
    state = read(out/'state.json')

    if comparison is not None:
        bs = read(a.baseline_state)
        assert bs['fixture_sha256'] == sha(ROOT/BASE) and bs['config_sha256'] == sha(ROOT/CONFIG)
        bclock = {tuple(k): v for k, v in bs['clock_seeds']}
        cclock = {tuple(k): v for k, v in state['clock_seeds']}
        assert cclock == bclock, 'clock seeds differ from the baseline'
        rev, splits = comparison['reverse_map'], comparison['splits']
        base_rows = read(ROOT/BASE)['rows']
        unchanged = [i for i, r in enumerate(base_rows) if r['arc'] not in splits]
        np.testing.assert_array_equal(np.array(state['windup'])[unchanged], np.array(bs['windup'])[unchanged])
        changed_windup = [dict(row=i, arc=rows[i]['arc'], baseline=bs['windup'][i], candidate=state['windup'][i])
                          for i, r in enumerate(base_rows) if r['arc'] in splits and bs['windup'][i] != state['windup'][i]]
        for n, o in rev.items():
            if o not in splits:
                assert state['amb_origins'][n] == bs['amb_origins'][o], ('origin changed for unchanged arc', n)
        split_origins = {o: dict(baseline=bs['amb_origins'][o],
                                 candidate={n: state['amb_origins'][n] for n in splits[o]}) for o in splits}
        comparison.update(clock_seeds_bitwise_equal_to_baseline=True, windup_equal_on_unchanged_rows=len(unchanged),
                          changed_windup_rows=changed_windup, origins_equal_for_unchanged_arcs=True,
                          split_arc_origins=split_origins, baseline_state_sha256=sha(a.baseline_state))

    p = LongPilot(c, rows, seeds, estimate=estimate, state=state)
    x = np.zeros(len(p.names))
    products = cached_products(p, x, a.trajectories)
    residual, sigma = [], []
    for ei in range(p.epoch_count):
        _, r, s = p.epoch_block(x, ei, products, jacobian=False)
        residual.extend(r)
        sigma.extend(s)
    residual, sigma = np.asarray(residual), np.asarray(sigma)
    expected_sigma = [v for ei in range(c['epoch_count']) for r in rows if r['epoch'] == ei
                      for v in r['sigma'][:2 if r['arc'] in p.arcset else 1]]
    np.testing.assert_array_equal(sigma, expected_sigma)
    assert np.isfinite(residual).all() and np.isfinite(sigma).all()
    assert len(residual) == EXPECT['residuals'][ARMS[a.arm]['fixture']], len(residual)
    cost = float(p.cost(residual, sigma, x))
    assert np.isfinite(cost)
    phase_rows = sum(1 for r in rows if r['arc'] in p.arcset)
    local = sum(len(v) for v in p.local_names)
    counts = dict(code_rows=len(rows), phase_rows=phase_rows, eligible_arcs=len(p.arcs), retained_parameters=p.n,
                  local_parameters=local, satellites=len(p.sats), epochs=p.epoch_count, stations=len(p.stations))
    assert counts['code_rows'] == EXPECT['code_rows'] and phase_rows == EXPECT['phase_rows'][ARMS[a.arm]['fixture']]
    assert len(p.arcs) == EXPECT['eligible_arcs'] and p.n == EXPECT['retained'] and local == EXPECT['local']
    assert len(p.sats) == EXPECT['satellites'] and p.epoch_count == EXPECT['epochs']
    report = dict(status='aug6_physical_initialization_pass', arm=a.arm, fixture=ARMS[a.arm]['fixture'],
                  fixture_sha256=sha(fixture_path), config_sha256=sha(ROOT/CONFIG), state_sha256=sha(out/'state.json'),
                  counts=counts, connected_epochs=p.epoch_count, x0_forward_residuals=len(residual), x0_full_objective=cost,
                  used_clock_seeds=len(used), omitted_unused_clock_keys=[list(k) for k in omitted],
                  pinned_method_warnings=sorted({str(w.message) for w in caught}),
                  pinned_vs_adapter_used_seeds_windup_origins_bitwise_equal=True, strict_json_and_all_finite=True,
                  x0_cache_provenance=caches, candidate_comparison=comparison, precise_products_used=False,
                  optimization_start='zero corrections', source_sha256=sha(Path(__file__)))
    write(out/'initialization.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('x0_cache_provenance', 'candidate_comparison')}, indent=1), flush=True)
    if comparison:
        print('splits', comparison['splits'], 'lost', comparison['lost_phase_rows'], 'renamed', comparison['renamed_unchanged_arcs'], flush=True)


if __name__ == '__main__':
    main()
