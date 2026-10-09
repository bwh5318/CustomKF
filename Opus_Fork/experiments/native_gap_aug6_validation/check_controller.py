"""Bounded fault-injection checks of the August-6 controller's bookkeeping. No numerical work.

    C:\\anaconda\\python.exe -m customkf.guard --profile usage75 --threads 1 --timeout 120 -- \\
        Opus_Fork.experiments.native_gap_aug6_validation.check_controller

A fake guard stands in for customkf.guard.run: it asserts the usage75 limits it
is handed and creates artifact folders under this worker's own run directory.
"""
import os
from pathlib import Path
from customkf.prepare_stage2 import sha
from Opus_Fork.experiments.native_gap_aug6_validation.controller import Runner
from Opus_Fork.experiments.native_gap_aug6_validation.common import BASELINE, CANDIDATE, PHASES, rel, write


def expect(error, fn, text=None):
    try:
        fn()
    except error as e:
        assert text is None or text in str(e), (text, str(e))
        return
    raise AssertionError(f'{error.__name__} not raised')


def main():
    out = Path(os.environ['CUSTOMKF_RUN_DIR'])
    folder = out/'controller'
    folder.mkdir()
    pin = out/'input.txt'
    pin.write_text('fixed')
    calls = []
    m = dict(source_sha256={rel(pin): sha(pin)}, workers=[], precampaign_workers=[], phase='readiness',
             phases={k: dict(guarded_cap=g, wall_cap=w, guarded_seconds=0., active_wall_s=0.) for k, (g, w) in PHASES.items()},
             guarded_seconds=0., active_wall_s=0., active_worker=None, active_arm='-', unrecorded_attempts=[])

    def fake(args, limits, **kw):
        assert limits.memory_mib == 4096 and limits.cpu_percent == 15 and limits.threads == 1
        assert limits.timeout_s <= 300 and kw['usage_ceiling'] == 75
        p = out/f'worker{len(calls)}'
        p.mkdir()
        (p/'artifact').write_text('fixed')
        calls.append(list(args))
        return dict(status='worker_failed' if args == ['fail'] else 'ok', elapsed_s=2.), p

    r = Runner(folder, m, guard=fake)
    checks = []

    m['active_arm'] = BASELINE
    pb = r.worker('init-state', ['a'])
    m['active_arm'] = CANDIDATE
    pc = r.worker('init-state', ['b'])
    assert pb != pc and len(calls) == 2
    checks.append('identical label under two arms launches two separate workers')

    m['active_arm'] = BASELINE
    assert r.worker('init-state', ['a']) == pb
    m['active_arm'] = CANDIDATE
    assert r.worker('init-state', ['b']) == pc and len(calls) == 2
    checks.append('completed workers replay per (phase, arm, label) without relaunch')

    expect(AssertionError, lambda: r.worker('init-state', ['different']), 'Replay arguments differ')
    checks.append('replay with different arguments rejected')

    m['phase'], m['active_arm'] = 'baseline', BASELINE
    pz = r.worker('init-state', ['a'])
    assert pz not in (pb, pc) and len(calls) == 3
    m['phase'] = 'readiness'
    checks.append('same arm and label in another phase is a distinct worker')

    (pb/'artifact').write_text('tamper')
    expect(AssertionError, r.verify, 'Changed recorded worker')
    m['active_arm'] = BASELINE
    expect(AssertionError, lambda: r.worker('init-state', ['a']), 'Replayed artifact changed')
    (pb/'artifact').write_text('fixed')
    r.verify()
    checks.append('tampered artifact rejected by verify and by replay')

    before = m['phases']['readiness']['guarded_seconds']
    expect(RuntimeError, lambda: r.worker('bad', ['fail']), 'Guard failed')
    assert m['phases']['readiness']['guarded_seconds'] == before+2 and m['workers'][-1]['result']['status'] == 'worker_failed'
    checks.append('failed worker is recorded, charged its elapsed time, and stops the controller')

    cand_before = m['phases']['candidate']['guarded_seconds']
    wall_before = m['phases']['candidate']['active_wall_s']
    m['active_worker'] = dict(phase='candidate', arm=CANDIDATE, label='lost', args=['x'], timeout_s=300, started_utc='t')
    r.recover()
    assert m['phases']['candidate']['guarded_seconds'] == cand_before+300
    assert m['phases']['candidate']['active_wall_s'] >= wall_before+300
    assert m['unrecorded_attempts'][-1]['charged_seconds'] == 300 and m['active_worker'] is None
    checks.append('unrecorded attempt charged its full timeout to its own phase, guarded and wall')

    m['phases']['readiness']['guarded_seconds'] = 900
    m['phase'], m['active_arm'] = 'readiness', '-'
    expect(RuntimeError, lambda: r.worker('late', ['c']), 'readiness budget exhausted')
    checks.append('readiness 900 s cap enforced')

    m['phase'], m['active_arm'] = 'baseline', BASELINE
    r.worker('fit-one', ['d'])
    m['phases']['baseline']['guarded_seconds'] = 5400
    expect(RuntimeError, lambda: r.worker('fit-two', ['e']), 'baseline budget exhausted')
    m['phase'], m['active_arm'] = 'candidate', CANDIDATE
    r.worker('fit-one', ['d'])
    checks.append('baseline 5400 s cap enforced while the candidate phase stays independent')

    m['phases']['candidate']['active_wall_s'] = 7200
    expect(RuntimeError, lambda: r.worker('fit-three', ['f']), 'candidate budget exhausted')
    checks.append('active-wall cap enforced independently of guarded seconds')

    m['phase'], m['active_arm'] = 'audit', '-'
    m['phases']['audit']['guarded_seconds'] = 1199.5
    expect(RuntimeError, lambda: r.worker('audit-late', ['g']), 'audit budget exhausted')
    assert abs(m['guarded_seconds']-sum(p['guarded_seconds'] for p in m['phases'].values())) < 1e-9
    checks.append('audit cap enforced; total equals the sum of phase counters (no pooling)')

    pin.write_text('changed')
    expect(AssertionError, r.verify, 'Changed pin')
    expect(AssertionError, lambda: r.worker('any', ['h']), 'Changed pin')
    checks.append('changed source/input pin rejected before any launch')

    write(out/'controller_checks.json', dict(status='aug6_controller_fault_injection_pass', checks=checks, fake_launches=len(calls)))
    print(len(checks), 'checks pass', flush=True)


if __name__ == '__main__':
    main()
