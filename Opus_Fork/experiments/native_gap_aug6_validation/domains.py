"""Guarded worker: freeze August-6 evaluation keys before any fit is scored.

Also checks the date-dependent constants independently: fixture origin and
cutoff, solve-epoch times, the saved-state grid and the 96 requested native
15-minute slots, with no day-214 constants. Reads the IGS Rapid SP3 for
evaluation only; this worker feeds nothing to a fit.
"""
from collections import Counter, defaultdict
import os
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.sp3 import epoch_tag
from claude.reviews.roadmap_latest_review import reference
from Opus_Fork.experiments.native_gap_aug6_validation.common import (
    DAY, BASE, CAND, REFERENCE, PINS, BASELINE, CANDIDATE, read, write)


def coverage(fx, sats):
    counts = defaultdict(Counter)
    for r in fx['rows']:
        counts[r['satellite']][r['epoch']] += 1
    out = {}
    for s in sats:
        per = np.array([counts[s][e] for e in range(fx['context']['epoch_count'])])
        out[s] = dict(minimum_stations=int(per.min()), median_stations=float(np.median(per)),
                      epochs_below_three=int((per < 3).sum()), epochs_zero=int((per == 0).sum()), total_links=int(per.sum()))
    return out


def main():
    out = Path(os.environ['CUSTOMKF_RUN_DIR'])
    base, cand = read(ROOT/BASE), read(ROOT/CAND)
    assert sha(ROOT/BASE) == PINS[BASE] and sha(ROOT/CAND) == PINS[CAND]
    c = base['context']
    assert cand['context'] == c
    origin = epoch_tag('* 2026 08 05 23 59 50')
    midnight_expected = epoch_tag('* 2026 08 06 00 00 00')
    constants = dict(day=c['day'], origin_ns=c['origin_ns'], expected_origin_ns=origin, epoch_count=c['epoch_count'],
                     step_s=c['step_s'], duration_s=c['duration_s'], navigation_cutoff_ns=c['navigation_cutoff_ns'],
                     expected_cutoff_ns=epoch_tag('* 2026 08 07 00 00 00'))
    assert c['day'] == DAY and c['origin_ns'] == origin and c['epoch_count'] == 144 and c['step_s'] == 600
    assert c['navigation_cutoff_ns'] == constants['expected_cutoff_ns']
    times = {r['time_s'] for r in base['rows']}
    assert all(r['time_s'] == 10+600*r['epoch'] and 0 <= r['epoch'] < 144 for r in base['rows'])
    assert max(times)+10 == c['duration_s'] == 85820
    # Saved-state grid of save_solution: arange(10, duration-9, 300) seconds after origin.
    grid = np.arange(10., c['duration_s']-9., 300.)
    grid_ns = {c['origin_ns']+round(float(t)*1e9) for t in grid}
    slots = [midnight_expected+k*900*10**9 for k in range(96)]
    assert c['origin_ns']+10*10**9 == midnight_expected and all(s in grid_ns for s in slots)
    constants.update(state_grid=dict(first_s=float(grid[0]), step_s=300., count=len(grid)),
                     native_slots=dict(first='00:00', last='23:45', count=len(slots), step_s=900))

    sats = sorted(base['seeds'])
    assert sats == sorted(cand['seeds']) and len(sats) == 26
    midnight, ep, raw, vel, ref = reference(DAY)
    assert midnight == midnight_expected and ref['path'] == REFERENCE and ref['sha256'] == PINS[REFERENCE]
    assert raw.frame == 'IGc20'
    keys, omissions = {}, []
    for s in sats:
        keys[s] = []
        for t in slots:
            sample = raw.samples.get((t, s))
            reason = ('absent' if not sample else 'no_position' if sample.xyz_m is None else
                      'maneuver' if sample.maneuver else 'orbit_predicted' if sample.orbit_predicted else None)
            if reason:
                omissions.append(dict(satellite=s, gps_ns=t, reason=reason))
            else:
                keys[s].append(t)
    counts = {s: len(v) for s, v in keys.items()}
    rejected = c['rejected_satellites']
    rejected_in_reference = {s: sum(1 for t in slots if raw.samples.get((t, s))) for s in sorted(rejected)}
    result = dict(status='aug6_domains_frozen_before_any_score', day=DAY, reference=ref, reference_frame='IGc20',
                  date_constants=constants, satellites=sats, rejected_satellites=rejected,
                  rejected_satellites_reference_samples=rejected_in_reference,
                  requested_slots_per_satellite=len(slots), valid_samples_per_satellite=counts,
                  valid_samples_total=sum(counts.values()), omissions=omissions,
                  omission_reasons=dict(Counter(o['reason'] for o in omissions)),
                  native_keys_by_arm={BASELINE: keys, CANDIDATE: keys}, common_native_gps_ns=keys,
                  full_equals_common=True,
                  coverage_by_arm={BASELINE: coverage(base, sats), CANDIDATE: coverage(cand, sats)},
                  note='Same 26 NAV-selected satellites and identical code rows in both arms, so full and common '
                       'domains coincide. No score was computed.')
    write(out/'domains.json', result)
    print(dict(status=result['status'], satellites=len(sats), valid_total=result['valid_samples_total'],
               omission_reasons=result['omission_reasons']), flush=True)


if __name__ == '__main__':
    main()
