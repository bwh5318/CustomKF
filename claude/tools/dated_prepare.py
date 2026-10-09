"""Guarded dated fixture preparation and August-2 reproduction gates.

prepare: rebuild native observation fixture and check old day by exact values.
reproduce: rebuild final D0 forward model from dated fixture and archived x.
No reference SP3/CLK is read in either mode.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT, sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import write_json
from claude.tools.dated_stage5 import prepare
from claude.tools.dated_d0 import D0Pilot
from claude.tools.dated_fixture import freeze,restore,sources,dimensions

BASE=ROOT/'claude/runs/20260912T021739Z-arc'
D0=ROOT/'claude/runs/20260912T145220Z-station-d0'


def main():
    folder=Path(os.environ['CUSTOMKF_RUN_DIR'])
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','reproduce'))
    p.add_argument('--day',default='2026-08-02');p.add_argument('--inputs',type=Path)
    p.add_argument('--fixture',type=Path);a=p.parse_args()
    sys.addaudithook(forbid_precise_product_reads)
    if a.mode=='prepare':
        old=json.loads((BASE/'six-prepare/fixture.json').read_text())
        c,rows,seeds=prepare(step_s=600,epoch_count=37,station_subset=list(old['context']['stations']),
                              day=a.day,input_manifest=a.inputs)
        freeze(c,rows,seeds,folder/'fixture.json')
        fresh=json.loads((folder/'fixture.json').read_text())
        if a.day=='2026-08-02':
            assert fresh['seeds']==old['seeds']
            for k,v in old['context'].items(): assert fresh['context'][k]==v,k
            for r in fresh['rows']:
                del r['origin_doy'];del r['origin_second_of_day']
            assert fresh['rows']==old['rows'],'Native rows changed'
        pilot=D0Pilot(c,rows,seeds)
        report=dict(status='prepared',case='dated-six',day=a.day,source_sha256=sources(),
            fixture_sha256=sha(folder/'fixture.json'),satellites=pilot.sats,
            rejected_satellites=c['rejected_satellites'],stations=pilot.stations,
            legacy_fixture_values_equal=a.day=='2026-08-02',precise_products_used=False,**dimensions(pilot))
        write_json(folder/'step.json',report)
        print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2),flush=True)
        if not report['budget_pass']: raise ValueError('Preflight budget exceeded; limits unchanged')
        x=np.zeros(len(pilot.names));product=pilot.products(x);times=np.arange(10.,pilot.duration-9.,300.)
        states=np.array([[product.state(s,t) for t in times] for s in pilot.sats])
        if a.day=='2026-08-02':
            with np.load(BASE/'six-prepare/initial.npz') as z: np.testing.assert_array_equal(states,z['states'])
        np.savez_compressed(folder/'initial.npz',states=states,times_s=times,satellites=np.array(pilot.sats))
        cold=folder/'cold';cold.mkdir()
        np.savez_compressed(cold/'solution.npz',x=x,names=np.array(pilot.names))
        write_json(cold/'step.json',dict(fixture_sha256=report['fixture_sha256'],
            solution_sha256=sha(cold/'solution.npz'),history=[]))
        report['seed_states_bitwise_equal']=True if a.day=='2026-08-02' else None
        write_json(folder/'step.json',report)
    else:
        c,rows,seeds=restore(a.fixture)
        assert c['day']=='2026-08-02'
        pilot=D0Pilot(c,rows,seeds)
        with np.load(D0/'linear-1/solution.npz') as z:
            np.testing.assert_array_equal(pilot.names,z['names'])
            _,_,r,s,_,cost,products=pilot.evaluate(z['x'],jacobian=False)
            np.testing.assert_array_equal(r,z['residual_m']);np.testing.assert_array_equal(s,z['sigma_m'])
            states=np.array([[products.state(sat,t) for t in z['times_s']] for sat in pilot.sats])
            np.testing.assert_array_equal(states,z['states'])
            expected=json.loads((D0/'linear-1/step.json').read_text())['history'][-1]['cost_after']
            assert cost==expected
        write_json(folder/'reproduction.json',dict(status='dated_august2_forward_bitwise_pass',
            residuals=len(r),sampled_states=list(states.shape),cost=cost,source_sha256=sources(),
            fixture_sha256=sha(a.fixture),original_solution_sha256=sha(D0/'linear-1/solution.npz')))
        print('Dated August-2 final residuals, sigmas, states and cost reproduce bitwise',flush=True)


if __name__=='__main__':main()
