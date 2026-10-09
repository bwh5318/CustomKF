"""Explicit-date fixture IO and bounded dimension checks; no reference products."""
import json
from pathlib import Path
import numpy as np
from customkf.prepare_stage2 import ROOT, DATA as DYN, sha
from customkf.prepare_stage3 import DATA
from customkf.stage5b_step import write_json
from customkf.frames import FrameEpoch, EarthOrientation, Environment
from customkf.ephemeris import DE440
from customkf.orbit_forces import OrbitForceModel
from customkf.rinex import read_gps_navigation
from customkf.antenna import load_calibrations
from customkf.reduced_network import MAX_ROWS, MAX_PARAMETERS, WORKSPACE_BYTES


def sources():
    paths = list((ROOT/'customkf').glob('*.py'))
    # Include evaluator/support dependencies too, not just the new dated modules.
    paths += list((ROOT/'claude/tools').glob('*.py'))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def freeze(context, rows, seeds, path):
    keys = ('stations','inputs','rejected_satellites','duration_s','epoch_count','step_s',
            'profile','navigation_cutoff_ns','origin_ns','day','navigation_path')
    write_json(path, {'case':'dated-six', 'context':{k:context[k] for k in keys}, 'rows':rows, 'seeds':seeds})


# The model inputs restore() opens, by role (Sol review SOL-04).
ROLE_FILES = {'daily EOP': DYN/'finals2000A.all', 'ephemeris': DYN/'de440s.bsp',
              'gravity field': DYN/'EGM2008_degree12.gfc', 'antenna calibrations': DATA/'igs20.atx'}


def check_roles(inputs):
    """Every model file restore() opens must be a recorded input at exactly that path.

    The recorded hashes are verified separately, so the bytes used in estimation are the bytes whose identity the
    fixture records. Before 1 Oct 2026 a fixture recording an alternate copy (same name, other location) would have
    been verified there and then the canonical file opened instead.
    """
    for role, path in ROLE_FILES.items():
        name = path.relative_to(ROOT).as_posix()
        if name not in inputs:
            recorded = [k for k in inputs if Path(k).name == path.name]
            raise ValueError(f'{role}: restore opens {name}, which the fixture does not record'
                             + (f' (it records {recorded})' if recorded else ''))


def restore(path):
    obj = json.loads(Path(path).read_text()); c = obj['context']
    for name, digest in c['inputs'].items():
        if sha(ROOT/name) != digest: raise ValueError('Input changed: '+name)
    if c['navigation_path'] not in c['inputs']: raise ValueError('Unpinned navigation')
    check_roles(c['inputs'])
    epoch = FrameEpoch(c['origin_ns'], EarthOrientation(DYN/'finals2000A.all'))
    ephemeris = DE440(DYN/'de440s.bsp')
    c.update(epoch=epoch, ephemeris=ephemeris,
        model=OrbitForceModel(Environment(epoch,ephemeris,c['duration_s']),DYN/'EGM2008_degree12.gfc'),
        records=read_gps_navigation(ROOT/c['navigation_path']))
    c['sat_cal'],c['rx_cal'] = load_calibrations(DATA/'igs20.atx',
        [m['header']['antenna'] for m in c['stations'].values()],c['origin_ns'])
    for row in obj['rows']:
        for k in ('receiver_xyz','observation','sigma'): row[k]=np.array(row[k])
    return c, obj['rows'], {s:np.array(x) for s,x in obj['seeds'].items()}


def dimensions(pilot):
    code=len(pilot.rows); phase=sum(r['arc'] in pilot.arcs for r in pilot.rows)
    priors=len(pilot.prior_sigma)+2*len(pilot.stations)
    m=code+phase+priors; n=pilot.n; local=sum(map(len,pilot.local_names))
    largest=max(sum(2 if r['arc'] in pilot.arcs else 1 for r in pilot.rows if r['epoch']==ei)
                for ei in range(pilot.epoch_count))
    workspace=8*(5*m*n+4*largest**2+3*local*n+6*n*n)
    return dict(code_rows=code,phase_rows=phase,prior_rows=priors,total_rows=m,retained_parameters=n,
                local_clock_parameters=local,workspace_estimate_mib=workspace/2**20,
                budget_pass=m<=MAX_ROWS and n<=MAX_PARAMETERS and workspace<=WORKSPACE_BYTES)
