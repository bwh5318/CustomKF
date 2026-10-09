"""Isolated two-arm controller for the August-6 native-gap validation (Opus).

    C:\\anaconda\\python.exe -m Opus_Fork.experiments.native_gap_aug6_validation.controller --controller-checks RUNDIR [RUNDIR ...]
    C:\\anaconda\\python.exe -m Opus_Fork.experiments.native_gap_aug6_validation.controller --resume Opus_Fork/runs/<campaign>

Phases, each with its own cumulative guarded / active-wall cap, never reset or
pooled: readiness, baseline, candidate, audit. Every worker is keyed by
(phase, arm, label), so the two arms' identical labels never alias. Fit mechanics
are `claude.experiments.cross_date_fits.run.fit`, imported unchanged; that
module's main() is never called. Only this controller launches guarded workers.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid
import psutil
from customkf.guard import Limits, run
from customkf.prepare_stage2 import ROOT, sha
from claude.roadmap.common import sources
from claude.experiments.cross_date_fits.run import fit
from Opus_Fork.experiments.native_gap_aug6_validation.common import (
    HERE, RUNS, BASE, CAND, CONFIG, PROTOCOL, CHAIN, HANDOFF, PREFLIGHT, REFERENCE, REPRO_FIXTURE, REPRO_EXAMPLE,
    PINS, ARMS, ORDER, BASELINE, CANDIDATE, PHASES, TOTAL, read, stamp, pins, rel)

MOD = 'Opus_Fork.experiments.native_gap_aug6_validation'


class Runner:
    def __init__(self, folder, m, guard=run):
        self.folder, self.m, self.guard = Path(folder), m, guard
        self.last = time.monotonic()

    def save(self):
        now = time.monotonic()
        dt, self.last = now-self.last, now
        m = self.m
        m['active_wall_s'] += dt
        m['phases'][m['phase']]['active_wall_s'] += dt
        m['guarded_seconds'] = sum(p['guarded_seconds'] for p in m['phases'].values())
        m['updated_utc'] = stamp()
        target = self.folder/'pending.json'
        target.write_text(json.dumps(m, indent=2, allow_nan=False)+'\n')
        target.replace(self.folder/'validation.json')

    def verify(self):
        for p, h in self.m['source_sha256'].items():
            assert sha(ROOT/p) == h, 'Changed pin: '+p
        for w in self.m['workers']+self.m['precampaign_workers']:
            assert pins(ROOT/w['path']) == w['files_sha256'], 'Changed recorded worker: '+w['label']

    def recover(self):
        a = self.m.get('active_worker')
        if a:
            ph = self.m['phases'][a['phase']]
            ph['guarded_seconds'] += a['timeout_s']
            ph['active_wall_s'] += a['timeout_s']
            self.m['active_wall_s'] += a['timeout_s']
            self.m['unrecorded_attempts'].append(dict(a, charged_seconds=a['timeout_s'], recovered_utc=stamp()))
            self.m['active_worker'] = None
            self.save()

    def worker(self, label, args, timeout=300):
        m = self.m
        phase, arm = m['phase'], m.get('active_arm') or '-'
        for p, h in m['source_sha256'].items():
            assert sha(ROOT/p) == h, 'Changed pin: '+p
        done = [w for w in m['workers'] if (w['phase'], w['arm'], w['label']) == (phase, arm, label) and w['result']['status'] == 'ok']
        if done:
            w = done[-1]
            assert w['args'] == args, ('Replay arguments differ', phase, arm, label)
            assert pins(ROOT/w['path']) == w['files_sha256'], ('Replayed artifact changed', phase, arm, label)
            return ROOT/w['path']
        self.save()
        ph = m['phases'][phase]
        left = min(ph['guarded_cap']-ph['guarded_seconds'], ph['wall_cap']-ph['active_wall_s'],
                   TOTAL[0]-m['guarded_seconds'], TOTAL[1]-m['active_wall_s'])
        if left < 1:
            raise RuntimeError(f'Frozen {phase} budget exhausted')
        timeout = min(timeout, 300, left)
        m['active_worker'] = dict(phase=phase, arm=arm, label=label, args=args, timeout_s=timeout, started_utc=stamp())
        self.save()
        print('Starting', phase, arm, label, flush=True)
        result, path = self.guard(args, Limits(memory_mib=4096, cpu_percent=15, threads=1, timeout_s=timeout), usage_ceiling=75)
        path = Path(path)
        assert path.resolve().is_relative_to((ROOT/'runs').resolve())
        ph['guarded_seconds'] += result.get('elapsed_s', timeout)
        m['workers'].append(dict(phase=phase, arm=arm, label=label, args=args, path=rel(path), result=result,
                                 files_sha256=pins(path)))
        m['active_worker'] = None
        self.save()
        print(phase, arm, label, result['status'], round(result.get('elapsed_s', 0), 2), flush=True)
        if result['status'] != 'ok':
            raise RuntimeError(f'Guard failed: {phase} {arm} {label} {result["status"]}')
        return path


def readiness(r):
    m = r.m
    m['phase'] = 'readiness'
    base = ['--fixture', str(ROOT/BASE), '--config', str(ROOT/CONFIG)]
    m['active_arm'] = '-'
    d = r.worker('reproduce-aug2', ['claude.tools.dated_prepare', 'reproduce', '--fixture', str(ROOT/REPRO_FIXTURE)])
    rep, ex = read(d/'reproduction.json'), read(ROOT/REPRO_EXAMPLE)
    assert rep['status'] == 'dated_august2_forward_bitwise_pass', rep['status']
    assert rep['fixture_sha256'] == ex['fixture_sha256'] == sha(ROOT/REPRO_FIXTURE)
    assert rep['original_solution_sha256'] == ex['original_solution_sha256']
    assert rep['residuals'] == ex['residuals'] and rep['cost'] == ex['cost']
    m['gates']['reproduction'] = dict(path=rel(d), status=rep['status'], residuals=rep['residuals'], cost=rep['cost'],
                                      matches_archived_example=REPRO_EXAMPLE)
    r.save()
    print('GATE reproduction PASS; next x=0 dynamics caches', flush=True)

    m['active_arm'] = BASELINE
    caches = []
    for g in range(4):
        d = r.worker(f'x0-cache-{g}', ['claude.roadmap.traj_cache', 'integrate', *base, '--group', str(g), '--groups', '4'])
        caches.append(d/'trajectories.npz')
    cache_args = [str(p) for p in caches]
    d = r.worker('init-state', [f'{MOD}.initialize', 'state', BASELINE, '--trajectories', *cache_args])
    init_b = read(d/'initialization.json')
    assert init_b['status'] == 'aug6_physical_initialization_pass'
    state_b = d/'state.json'
    m['active_arm'] = CANDIDATE
    d = r.worker('init-state', [f'{MOD}.initialize', 'state', CANDIDATE, '--trajectories', *cache_args,
                                '--baseline-state', str(state_b)])
    init_c = read(d/'initialization.json')
    assert init_c['status'] == 'aug6_physical_initialization_pass'
    state_c = d/'state.json'
    for arm, st, init in ((BASELINE, state_b, init_b), (CANDIDATE, state_c, init_c)):
        m['arms'][arm].update(prepared_state=rel(st), prepared_caches=[rel(p) for p in caches])
        m['gates']['initialization_'+arm] = dict(path=rel(st.parent), state_sha256=sha(st), counts=init['counts'],
                                                x0_objective=init['x0_full_objective'], residuals=init['x0_forward_residuals'])
    r.save()
    print('GATE initialization PASS both arms; next frozen domains', flush=True)

    m['active_arm'] = '-'
    d = r.worker('domains', [f'{MOD}.domains'])
    dom = read(d/'domains.json')
    assert dom['status'] == 'aug6_domains_frozen_before_any_score'
    m['domains'] = dict(path=rel(d/'domains.json'), sha256=sha(d/'domains.json'),
                        valid_samples_total=dom['valid_samples_total'], omission_reasons=dom['omission_reasons'])
    m['gates']['readiness'] = 'passed'
    r.save()
    print('READINESS PASSED; next baseline cold-start fit', flush=True)


def fits(r):
    m = r.m
    for arm in ORDER:
        m['phase'] = ARMS[arm]['phase']
        fit(r, arm)
        assert m['arms'][arm]['status'] == 'converged', arm
    m.update(status='both_fits_converged_pending_independent_audit_and_scoring', active_arm=None, phase='audit')
    r.save()
    snap = r.folder/'fits_complete_snapshot.json'
    if 'fit_snapshot' not in m:
        shutil.copyfile(r.folder/'validation.json', snap)
        m['fit_snapshot'] = dict(path=rel(snap), sha256=sha(snap))
        r.save()
    assert sha(ROOT/m['fit_snapshot']['path']) == m['fit_snapshot']['sha256']


def audit(r):
    m = r.m
    m['phase'] = 'audit'
    snap = str(ROOT/m['fit_snapshot']['path'])
    m['active_arm'] = '-'
    prov = r.worker('provenance', [f'{MOD}.audit', 'provenance', snap])
    alg, fw = {}, {}
    for arm in ORDER:
        m['active_arm'] = arm
        alg[arm] = r.worker('algebra', [f'{MOD}.audit', 'algebra', snap, arm])
        for g in range(4):
            fw[arm, g] = r.worker(f'forward-{g}', [f'{MOD}.audit', 'forward', snap, arm, str(g)])
    m['active_arm'] = '-'
    args = [f'{MOD}.audit', 'score', snap, str(ROOT/m['domains']['path']), '--provenance', str(prov),
            '--algebra', *[str(alg[a]) for a in ORDER], '--forward', *[str(fw[a, g]) for a in ORDER for g in range(4)]]
    e = r.worker('score', args)
    ev = read(e/'evaluation.json')
    m.update(scoring_performed=True, evaluation=dict(path=rel(e/'evaluation.json'), sha256=sha(e/'evaluation.json')),
             transfer_gate=ev['transfer_gate'],
             status='complete_audited_and_scored_descriptive_not_operational_acceptance')
    r.save()
    print('COMPLETE transfer gate:', ev['transfer_gate'], flush=True)


def create(check_dirs):
    for p, h in PINS.items():
        assert sha(ROOT/p) == h, 'Supplied pin mismatch: '+p
    chain = read(ROOT/CHAIN)
    assert chain['status'] == 'classification_and_aug6_preflight_complete_not_fit_or_accuracy_acceptance'
    assert not chain['aug6_fit_started']
    for e in chain['files']:
        assert sha(ROOT/e['path']) == e['sha256'], 'Chain output changed: '+e['path']
    for p, h in chain['source_input_sha256'].items():
        assert sha(ROOT/p) == h, 'Chain source/input changed: '+p
    pre = read(ROOT/PREFLIGHT/'result.json')
    assert pre['status'] == 'ok' and read(ROOT/PREFLIGHT/'preflight.json')['candidate_fixture_sha256'] == PINS[CAND]
    extra = [rel(p) for p in HERE.glob('*.py')]
    extra += ['Opus_Fork/results/native_gap_aug6_validation/PROTOCOL.md']
    extra += ['claude/experiments/cross_date_fits/run.py', 'claude/reviews/roadmap_review.py',
              'claude/reviews/roadmap_latest_review.py', 'claude/reviews/opus_cross_date_observation_audit/empty_epoch_state.py',
              'RESOURCE_POLICY_20260917.md', PROTOCOL, CHAIN, HANDOFF, CONFIG, BASE, CAND, REFERENCE,
              REFERENCE+'.json', REPRO_FIXTURE, REPRO_EXAMPLE, PREFLIGHT+'/preflight.json', PREFLIGHT+'/result.json',
              'claude/runs/20260913T190407Z-roadmap-bench/prepare-06-long/step.json',
              'claude/runs/20260913T190407Z-roadmap-bench/prepare-06-long/result.json',
              'claude/runs/20260913T190407Z-roadmap-bench/stage.json']
    bound = sources(extra)
    bound.update(read(ROOT/BASE)['context']['inputs'])
    phases = {k: dict(guarded_cap=g, wall_cap=w, guarded_seconds=0., active_wall_s=0.) for k, (g, w) in PHASES.items()}
    precampaign = []
    for i, d in enumerate(check_dirs):
        d = (ROOT/d).resolve()
        result = read(d/'result.json')
        charge = result.get('elapsed_s', result['limits']['timeout_s'])
        precampaign.append(dict(phase='readiness', arm='-', label=f'controller-check-{i}', args=result['module_args'],
                                path=rel(d), result=result, files_sha256=pins(d), charged_seconds=charge))
        phases['readiness']['guarded_seconds'] += charge
        phases['readiness']['active_wall_s'] += charge
    last = precampaign[-1]
    assert last['result']['status'] == 'ok' and last['result']['enforced']
    assert read(ROOT/last['path']/'controller_checks.json')['status'] == 'aug6_controller_fault_injection_pass'
    wall = sum(p['active_wall_s'] for p in phases.values())
    folder = RUNS/(time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())+'-native-gap-aug6-validation')
    folder.mkdir(parents=True)
    arms = {arm: dict(status='pending', phase=ARMS[arm]['phase'], fixture=ARMS[arm]['fixture'], prepared_state=None,
                      prepared_caches=[], state=None, final=None) for arm in ORDER}
    # Recorded once, not re-verified per worker: documents other agents may legitimately edit.
    ledger = {p: sha(ROOT/p) for p in ('AGENTS.md', 'CONTINUE_HERE.md')}
    ledger['chain_source_input_entries_verified'] = len(chain['source_input_sha256'])
    ledger['chain_output_files_verified'] = len(chain['files'])
    m = dict(status='running', created_utc=stamp(), assignment=HANDOFF, protocol=PROTOCOL, source_sha256=bound, ledger=ledger,
             phases=phases, phase='readiness', active_arm=None, active_worker=None, guarded_seconds=sum(
                 p['guarded_seconds'] for p in phases.values()), active_wall_s=wall, total_caps=dict(guarded=TOTAL[0], wall=TOTAL[1]),
             arms=arms, order=ORDER, gates={}, workers=[], precampaign_workers=precampaign, unrecorded_attempts=[],
             resume_history=[], scoring_performed=False)
    for p in bound:
        if p.endswith(('.py', '.md')):
            target = folder/'source'/p
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/p, target)
    return folder, m


def main():
    assert not os.environ.get('CUSTOMKF_RUN_DIR'), 'Controller must not be nested in a guard'
    ap = argparse.ArgumentParser()
    ap.add_argument('--resume', type=Path)
    ap.add_argument('--controller-checks', nargs='+', default=[])
    a = ap.parse_args()
    others = [p.pid for p in psutil.process_iter(['pid', 'name'])
              if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower()]
    assert not others, ('Other Python process', others)
    if a.resume:
        folder = (ROOT/a.resume).resolve()
        assert folder.is_relative_to(RUNS.resolve())
        m = read(folder/'validation.json')
        assert m['status'] in ('running', 'failed', 'interrupted'), m['status']
        snapshot = folder/('validation.before-resume-'+uuid.uuid4().hex[:8]+'.json')
        shutil.copyfile(folder/'validation.json', snapshot)
        m['resume_history'].append(dict(resumed_utc=stamp(), pre_resume_manifest=rel(snapshot),
                                        pre_resume_sha256=sha(snapshot), previous_status=m['status'], error=m.get('error')))
    else:
        assert a.controller_checks, 'Run the fault-injection check first and pass its run folder(s)'
        folder, m = create(a.controller_checks)
    r = Runner(folder, m)
    r.verify()
    r.recover()
    m.update(status='running', controller_pid=os.getpid(), controller_command=sys.argv, error=None)
    r.save()
    print('Campaign', folder, 'pid', os.getpid(), flush=True)
    try:
        if m['gates'].get('readiness') != 'passed':
            readiness(r)
        fits(r)
        audit(r)
    except BaseException as error:
        m.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=repr(error))
        raise
    finally:
        r.save()


if __name__ == '__main__':
    main()
