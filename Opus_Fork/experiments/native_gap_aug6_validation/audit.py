"""Guarded worker modes: independent audit, fresh forward, frozen scoring (August-6 pair).

    audit provenance SNAPSHOT
    audit algebra SNAPSHOT ARM
    audit forward SNAPSHOT ARM GROUP
    audit score SNAPSHOT DOMAINS --provenance DIR --algebra DIR DIR --forward DIR x8

SNAPSHOT is the campaign manifest frozen when both fits converged. Fit, algebra
and forward modes install forbid_precise_product_reads; only score reads SP3.
Adapted from claude/experiments/cross_date_review/check.py with this campaign's
(phase, arm, label) worker identity, date and domains made explicit.
"""
import argparse
from collections import Counter
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from claude.reviews.roadmap_review import load, array_sha, audit_fit
from Opus_Fork.experiments.native_gap_aug6_validation.common import (
    DAY, CONFIG, CONFIG_VALUE, ORDER, BASELINE, CANDIDATE, PHASES, TOTAL, EXPECT, ARMS, LOST, CONTROLS,
    read, write, pins)


def arm_workers(m, arm, prefix):
    return [w for w in m['workers'] if w['phase'] == ARMS[arm]['phase'] and w['arm'] == arm and w['label'].startswith(prefix)]


def provenance(out, snapshot):
    m = read(snapshot)
    assert m['status'] == 'both_fits_converged_pending_independent_audit_and_scoring'
    assert m['active_worker'] is None and not m['scoring_performed']
    for p, h in m['source_sha256'].items():
        assert sha(ROOT/p) == h, p
    peaks = {k: 0. for k in ('cpu_percent', 'gpu_percent', 'ram_percent')}
    memory, available, seen = 0., 1e9, set()
    for w in m['precampaign_workers']+m['workers']:
        key = (w['phase'], w['arm'], w['label'])
        assert key not in seen, key
        seen.add(key)
        assert pins(ROOT/w['path']) == w['files_sha256'], w['path']
        r = w['result']
        assert read(ROOT/w['path']/'result.json') == r
        assert r['module_args'] == w['args'] and r['status'] == 'ok' and r['enforced']
        lim = r['limits']
        assert lim['memory_mib'] == 4096 and lim['cpu_percent'] == 15 and lim['threads'] == 1
        assert lim['timeout_s'] <= 300 and lim['reserve_gib'] >= 8 and lim['scratch_mib'] <= 128
        assert r['system_usage']['ceiling_percent'] == 75
        for k in peaks:
            v = r['system_usage']['peak'][k]
            assert v < 75, (w['label'], k, v)
            peaks[k] = max(peaks[k], v)
        memory = max(memory, r['windows_peak_job_memory_mib'])
        available = min(available, r['minimum_system_available_gib'])
    assert memory < 4096 and available >= 8
    accounting = {}
    for phase, (gcap, wcap) in PHASES.items():
        elapsed = sum(w['result']['elapsed_s'] for w in m['workers'] if w['phase'] == phase)
        elapsed += sum(w['charged_seconds'] for w in m['precampaign_workers'] if w['phase'] == phase)
        lost = [w for w in m['unrecorded_attempts'] if w['phase'] == phase]
        assert all(w['charged_seconds'] == w['timeout_s'] for w in lost)
        elapsed += sum(w['charged_seconds'] for w in lost)
        ph = m['phases'][phase]
        assert abs(elapsed-ph['guarded_seconds']) < 1e-6, (phase, elapsed, ph['guarded_seconds'])
        assert elapsed <= gcap and ph['active_wall_s'] <= wcap and ph['guarded_cap'] == gcap and ph['wall_cap'] == wcap
        accounting[phase] = dict(guarded_seconds=elapsed, active_wall_s=ph['active_wall_s'], unrecorded_attempts=len(lost))
    assert abs(sum(a['guarded_seconds'] for a in accounting.values())-m['guarded_seconds']) < 1e-6
    assert m['guarded_seconds'] <= TOTAL[0] and m['active_wall_s'] <= TOTAL[1]
    lineage = {}
    for arm in ORDER:
        a = m['arms'][arm]
        assert a['status'] == 'converged' and pins(ROOT/a['final']) == a['final_sha256']
        state = read(ROOT/a['prepared_state'])
        assert state['fixture_sha256'] == sha(ROOT/a['fixture']) and state['config_sha256'] == sha(ROOT/CONFIG)
        assert a['state']['sha256'] == sha(ROOT/a['prepared_state'])
        assert not arm_workers(m, arm, 'lin0-traj-'), 'x=0 caches must come from readiness, not a warm start'
        lineage[arm] = dict(final=a['final'], linearizations=len(a['linearizations']), accepted_updates=len(a['accepted_trials']),
                            state=a['prepared_state'], caches=a['prepared_caches'])
    write(out/'provenance.json', dict(status='aug6_source_artifact_resource_accounting_pass', snapshot_sha256=sha(snapshot),
          source_pins=len(m['source_sha256']), workers=len(m['workers']), precampaign_workers=len(m['precampaign_workers']),
          phase_accounting=accounting, guarded_seconds=m['guarded_seconds'], active_wall_s=m['active_wall_s'],
          unrecorded_attempts=m['unrecorded_attempts'], resume_history=m['resume_history'], lineage=lineage,
          machine_peaks=peaks, peak_job_mib=memory, minimum_available_gib=available))
    print('provenance pass', {k: round(v['guarded_seconds'], 1) for k, v in accounting.items()}, peaks, flush=True)


def pilot_for(a):
    from claude.tools.dated_fixture import restore
    from claude.roadmap.long_pilot import LongPilot
    c, rows, seeds = restore(ROOT/a['fixture'])
    state = read(ROOT/a['prepared_state'])
    assert state['fixture_sha256'] == sha(ROOT/a['fixture']) and state['config_sha256'] == sha(ROOT/CONFIG)
    assert read(ROOT/CONFIG) == CONFIG_VALUE
    return LongPilot(c, rows, seeds, estimate=tuple(CONFIG_VALUE['estimate']), state=state)


def caches(m, arm, i):
    w = next(w for w in arm_workers(m, arm, f'lin{i}-solve') if w['label'] == f'lin{i}-solve')
    args = w['args']
    start = args.index('--trajectories')+1
    files = []
    for s in args[start:]:
        if s.startswith('--'):
            break
        files.append(Path(s))
    assert len(files) == 4
    return files


def algebra(out, snapshot, arm):
    from claude.roadmap.traj_cache import cached_products
    from customkf.stage5_pilot import forbid_precise_product_reads
    sys.addaudithook(forbid_precise_product_reads)
    m = read(snapshot)
    a = m['arms'][arm]
    fixture = read(ROOT/a['fixture'])
    entry = audit_fit(ROOT, a['final'], fixture, a['accepted_trials'], a['linearizations'][:-1])
    f = load(ROOT/a['final']/'solution.npz')
    p = pilot_for(a)
    np.testing.assert_array_equal(f['names'], p.names)
    previous, chunks_checked, maxworkspace = None, 0, 0.
    for i, linear in enumerate(a['linearizations']):
        x = np.zeros_like(f['x']) if previous is None else previous
        binding = dict(fixture=sha(ROOT/a['fixture']), config=sha(ROOT/CONFIG), state=a['state']['sha256'], x=array_sha(x))
        products = cached_products(p, x, caches(m, arm, i))
        assert set(products.trajectories) == set(map(str, f['satellites']))
        workers = sorted(arm_workers(m, arm, f'lin{i}-chunk-'), key=lambda w: w['label'])
        stop, previous_chunk = 0, None
        for w in workers:
            meta = read(ROOT/w['path']/'step.json')
            assert meta['binding'] == binding and meta['start'] == stop
            assert meta['checkpoint_sha256'] == sha(ROOT/w['path']/'checkpoint.npz')
            assert meta['workspace_estimate_mib'] <= 256
            if previous_chunk:
                assert Path(w['args'][w['args'].index('--checkpoint')+1]) == ROOT/previous_chunk
            else:
                assert '--checkpoint' not in w['args']
            previous_chunk, stop = w['path'], meta['stop']
            chunks_checked += 1
            maxworkspace = max(maxworkspace, meta['workspace_estimate_mib'])
        assert stop == fixture['context']['epoch_count'] == 144
        assert read(ROOT/linear/'step.json')['binding'] == binding
        if i < len(a['accepted_trials']):
            previous = load(ROOT/a['accepted_trials'][i]/'solution.npz')['x']
    cov = f['retained_covariance']
    assert np.array_equal(cov, cov.T), 'covariance not symmetric'
    min_eig = float(np.linalg.eigvalsh(cov).min())
    assert min_eig > 0, 'covariance not positive definite'
    final_step = read(ROOT/a['final']/'step.json')
    names = list(map(str, f['names']))
    force = {}
    for n in names:
        if not n.startswith('srp'):
            continue
        j = names.index(n)
        sat = n.split(':')[1]
        k = names.index(f'orbit:{sat}:0')
        force[n] = dict(correction_mps2=float(f['x'][j]*1e-7), formal_sigma_mps2=float(np.sqrt(cov[j, j])*1e-7),
                        state_correlations=(cov[k:k+6, j]/np.sqrt(np.diag(cov)[k:k+6]*cov[j, j])).tolist())
    assert len(f['residual_m']) == EXPECT['residuals'][ARMS[arm]['fixture']]
    entry.update(status='independent_algebra_and_stream_bindings_pass', arm=arm, solution_sha256=sha(ROOT/a['final']/'solution.npz'),
                 fixture_sha256=sha(ROOT/a['fixture']), satellites=list(map(str, f['satellites'])),
                 residual_count=len(f['residual_m']), chunks_checked=chunks_checked, max_stream_workspace_mib=maxworkspace,
                 covariance=dict(symmetric=True, minimum_eigenvalue=min_eig, dimension=int(cov.shape[0]),
                                 interpreted_at=final_step.get('retained_covariance_at'),
                                 note='Converged final applies no update, so the retained covariance is at the final '
                                      'linearization point; it is formal and conditional on the model and weights.'),
                 force_parameters=force)
    write(out/'algebra.json', entry)
    print(arm, 'algebra pass;', chunks_checked, 'chunks; next fresh forward', flush=True)


def forward(out, snapshot, arm, group):
    from customkf.stage5_pilot import forbid_precise_product_reads
    sys.addaudithook(forbid_precise_product_reads)
    from claude.tools.force_parameter_fit import ForceTrajectory, INITIAL_P
    from claude.roadmap.traj_cache import cached_products
    from customkf.nominal_navigation import NominalProducts
    m = read(snapshot)
    a = m['arms'][arm]
    p = pilot_for(a)
    c = p.context
    f = load(ROOT/a['final']/'solution.npz')
    x = f['x']
    fresh = {}
    for sat in p.sats[group::4]:
        k = p.index[f'orbit:{sat}:0']
        coeff = INITIAL_P.copy()
        for j, term in enumerate(('D0', 'Y0', 'B0', 'Bc1', 'Bs1')):
            coeff[j] += 1e-7*x[p.index[f'srp{term}:{sat}']]
        fresh[sat] = ForceTrajectory(np.asarray(p.seeds[sat])+x[k:k+6], c['model'], c['duration_s'], coeff)
        si = list(f['satellites']).index(sat)
        np.testing.assert_array_equal([fresh[sat].state(t) for t in f['times_s']], f['states'][si])
    cached = cached_products(p, x, caches(m, arm, len(a['linearizations'])-1))
    for sat in fresh:
        for t in f['times_s']:
            np.testing.assert_array_equal(fresh[sat].partial(t), cached.trajectories[sat].partial(t))
            np.testing.assert_array_equal(fresh[sat].force_partial(t), cached.trajectories[sat].force_partial(t))
    products = NominalProducts(c['epoch'], c['origin_ns'], c['records'], fresh, available_before_ns=c['navigation_cutoff_ns'])
    offset = checked = 0
    for ei in range(p.epoch_count):
        for i in p.by_epoch[ei]:
            r = p.rows[i]
            count = 2 if r['arc'] in p.arcset else 1
            if r['satellite'] in fresh:
                value = p.link(products, r, *p.state_for(x, r), p.windup[i])[0]
                np.testing.assert_array_equal(r['observation'][:count]-value[:count], f['residual_m'][offset:offset+count])
                checked += count
            offset += count
    assert offset == len(f['residual_m'])
    write(out/'forward.json', dict(status='fresh_forward_bitwise_pass', arm=arm, group=group, satellites=list(fresh),
          states_per_satellite=len(f['times_s']), residuals_checked=checked,
          solution_sha256=sha(ROOT/a['final']/'solution.npz'), precise_products_used=False))
    print(arm, group, 'fresh states, partials and', checked, 'residuals bitwise pass', flush=True)


def residual_table(fixture, f):
    """(epoch, station, satellite, kind) -> (residual, sigma), bound by epoch/row order and eligibility."""
    counts = Counter(r['arc'] for r in fixture['rows'])
    table, off = {}, 0
    for ei in range(fixture['context']['epoch_count']):
        for r in fixture['rows']:
            if r['epoch'] != ei:
                continue
            n = 2 if counts[r['arc']] >= 3 else 1
            for k in range(n):
                assert f['sigma_m'][off] == r['sigma'][k]
                table[(ei, r['station'], r['satellite'], k)] = (float(f['residual_m'][off]), float(f['sigma_m'][off]))
                off += 1
    assert off == len(f['residual_m'])
    return table


def stats(values):
    if not values:
        return dict(count=0)
    v = np.array(values)
    return dict(count=len(v), rms_m=float(np.sqrt(np.mean(v[:, 0]**2))), whitened_rms=float(np.sqrt(np.mean((v[:, 0]/v[:, 1])**2))))


def score(out, snapshot, domains_path, provenance_dir, algebra_dirs, forward_dirs):
    from claude.reviews.roadmap_latest_review import reference, pool
    m, domains = read(snapshot), read(domains_path)
    assert domains['status'] == 'aug6_domains_frozen_before_any_score'
    assert read(provenance_dir/'provenance.json')['status'] == 'aug6_source_artifact_resource_accounting_pass'
    audits = {}
    for d in algebra_dirs:
        e = read(d/'algebra.json')
        audits[e['arm']] = e
    assert set(audits) == set(ORDER)
    for arm in ORDER:
        fw = [read(d/'forward.json') for d in forward_dirs if read(d/'forward.json')['arm'] == arm]
        assert len(fw) == 4 and {v['group'] for v in fw} == set(range(4))
        counts = Counter(s for v in fw for s in v['satellites'])
        assert set(counts) == set(audits[arm]['satellites']) and set(counts.values()) == {1}
        assert sum(v['residuals_checked'] for v in fw) == audits[arm]['residual_count'] == EXPECT['residuals'][ARMS[arm]['fixture']]
        assert all(v['status'] == 'fresh_forward_bitwise_pass' and v['solution_sha256'] == audits[arm]['solution_sha256'] for v in fw)
    midnight, ep, raw, vel, ref = reference(DAY)
    assert ref['sha256'] == domains['reference']['sha256'] and raw.frame == domains['reference_frame'] == 'IGc20'
    tables, cache, finals, fixtures = {}, {}, {}, {}
    for arm in ORDER:
        a = m['arms'][arm]
        f = load(ROOT/a['final']/'solution.npz')
        fixture = read(ROOT/a['fixture'])
        finals[arm], fixtures[arm] = f, fixture
        table = {}
        for si, sat in enumerate(map(str, f['satellites'])):
            for ti, t in enumerate(f['times_s']):
                absolute = fixture['context']['origin_ns']+round(float(t)*1e9)
                key = (sat, absolute)
                sample = raw.samples.get((absolute, sat))
                if not sample or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:
                    continue
                if key not in cache:
                    rt = (absolute-midnight)/1e9
                    rot = ep.celestial_to_terrestrial(rt)
                    r = rot.T@sample.xyz_m
                    radial = r/np.linalg.norm(r)
                    cross = np.cross(r, vel.state(sat, rt)[3:])
                    cross /= np.linalg.norm(cross)
                    cache[key] = (rot, r, np.array([radial, np.cross(cross, radial), cross]), sample.xyz_m)
                rot, r, basis, xyz = cache[key]
                state = f['states'][si, ti, :3]
                cart = rot@state-xyz
                rac = basis@(state-r)
                assert abs(np.linalg.norm(cart)-np.linalg.norm(rac)) < 2e-8
                table[key] = [*rac, float(cart@cart)]
        frozen = {(s, int(t)) for s, ts in domains['native_keys_by_arm'][arm].items() for t in ts}
        assert set(table) == frozen, (arm, 'native key mismatch')
        tables[arm] = table
    common = {(s, int(t)) for s, ts in domains['common_native_gps_ns'].items() for t in ts}
    assert common == set(tables[BASELINE]) & set(tables[CANDIDATE])
    arms = {}
    for arm in ORDER:
        diag = audits[arm]['diagnostics']
        ordered = sorted(common)
        per = {s: pool([tables[arm][k] for k in ordered if k[0] == s]) for s in sorted({k[0] for k in ordered})}
        groups = {g: (pool([tables[arm][k] for k in ordered if diag[k[0]]['classification'] == g])
                      if any(diag[k[0]]['classification'] == g for k in ordered) else None)
                  for g in ('determined', 'poorly_determined')}
        arms[arm] = dict(all=pool([tables[arm][k] for k in ordered]), per_satellite=per, determination_groups=groups,
                         diagnostics=diag)
    b, c = arms[BASELINE], arms[CANDIDATE]
    change = {s: c['per_satellite'][s]['rms_3d_m']-b['per_satellite'][s]['rms_3d_m'] for s in b['per_satellite']}
    regressions = {s: v for s, v in change.items() if v > .1}
    pooled = dict(rms_3d_m=c['all']['rms_3d_m']-b['all']['rms_3d_m'],
                  rms_orbit_ure_m=c['all']['rms_orbit_ure_m']-b['all']['rms_orbit_ure_m'],
                  rms_rac_m=[x-y for x, y in zip(c['all']['rms_rac_m'], b['all']['rms_rac_m'])])
    gate = dict(lower_pooled_3d=pooled['rms_3d_m'] < 0, lower_pooled_orbit_ure=pooled['rms_orbit_ure_m'] < 0,
                no_regression_over_0p1m=not regressions)
    gate['passed'] = all(gate.values())
    controls = {s: dict(baseline=b['per_satellite'].get(s), candidate=c['per_satellite'].get(s), change_3d_m=change.get(s),
                        present=s in change) for s in CONTROLS}
    # Observation residuals on identical keys; the two lost phase keys are reported separately.
    rt = {arm: residual_table(fixtures[arm], finals[arm]) for arm in ORDER}
    shared = set(rt[BASELINE]) & set(rt[CANDIDATE])
    only_base, only_cand = sorted(set(rt[BASELINE])-shared), sorted(set(rt[CANDIDATE])-shared)
    lost_keys = sorted((e, s, t, 1) for s, t, e in LOST)
    assert only_base == lost_keys and not only_cand, (only_base, only_cand)
    residuals = {arm: {kind: stats([rt[arm][k] for k in sorted(shared) if k[3] == i]) for i, kind in enumerate(('code', 'phase'))}
                 for arm in ORDER}
    lost = [dict(epoch=e, station=s, satellite=t, residual_m=rt[BASELINE][(e, s, t, 1)][0],
                 whitened=rt[BASELINE][(e, s, t, 1)][0]/rt[BASELINE][(e, s, t, 1)][1]) for e, s, t, _ in lost_keys]
    objective = {arm: audits[arm]['objective'] for arm in ORDER}
    result = dict(status='aug6_frozen_native_comparison_complete_descriptive_not_operational_acceptance', day=DAY,
                  reference=ref, domains_sha256=sha(domains_path), snapshot_sha256=sha(snapshot), common_samples=len(common),
                  arms={arm: {k: v for k, v in arms[arm].items() if k != 'diagnostics'} for arm in ORDER},
                  determination={arm: dict(Counter(d['classification'] for d in arms[arm]['diagnostics'].values())) for arm in ORDER},
                  candidate_minus_baseline_3d_m=change, pooled_change=pooled, regressions_over_0p1m=regressions,
                  improved=sum(v < 0 for v in change.values()), worsened=sum(v > 0 for v in change.values()),
                  worsened_satellites={s: v for s, v in sorted(change.items(), key=lambda kv: -kv[1]) if v > 0},
                  controls=controls, transfer_gate=gate,
                  observation_residuals_on_identical_keys=dict(shared_keys=len(shared), by_arm=residuals, lost_phase_keys=lost),
                  objective=objective, force_parameters={arm: audits[arm]['force_parameters'] for arm in ORDER},
                  note='A smaller objective after removing observations does not by itself establish a better orbit. '
                       'Descriptive research gate, not statistical or operational acceptance.')
    write(out/'evaluation.json', result)
    print('pooled', {arm: {k: arms[arm]['all'][k] for k in ('rms_3d_m', 'rms_orbit_ure_m')} for arm in ORDER},
          'gate', gate, 'regressions', regressions, flush=True)


def main():
    out = Path(os.environ['CUSTOMKF_RUN_DIR'])
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['provenance', 'algebra', 'forward', 'score'])
    ap.add_argument('snapshot', type=Path)
    ap.add_argument('rest', nargs='*')
    ap.add_argument('--provenance', type=Path)
    ap.add_argument('--algebra', nargs='*', type=Path, default=[])
    ap.add_argument('--forward', nargs='*', type=Path, default=[])
    a = ap.parse_args()
    if a.mode == 'provenance':
        provenance(out, a.snapshot)
    elif a.mode == 'algebra':
        algebra(out, a.snapshot, a.rest[0])
    elif a.mode == 'forward':
        forward(out, a.snapshot, a.rest[0], int(a.rest[1]))
    else:
        score(out, a.snapshot, Path(a.rest[0]), a.provenance, a.algebra, a.forward)


if __name__ == '__main__':
    main()
