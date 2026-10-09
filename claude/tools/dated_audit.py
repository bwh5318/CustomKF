"""Guarded post-campaign audit of paired dated solutions and archive integrity.

Recomputes objective with named prior terms, validates retained covariance and
checkpoint algebra, and independently reads native SP3 for Cartesian scores.
Does not refit observations or adopt the reference as an estimator input.
"""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT,sha
from customkf.prepare_stage3 import DATA
from customkf.frames import FrameEpoch,EarthOrientation
from customkf.sp3 import read_sp3


def main():
    output=Path(os.environ['CUSTOMKF_RUN_DIR']);folder=Path(sys.argv[1]);m=json.loads((folder/'validation.json').read_text())
    assert m['status']=='day215_paired_pod_complete_not_accuracy_acceptance'
    pins={}
    for key,base in (('source_sha256',ROOT),('report_sha256',ROOT),('artifacts_sha256',folder)):
        for p,h in m[key].items():assert sha(base/p)==h,p
        pins[key]=len(m[key])
    fixture=json.loads((folder/'prepare/fixture.json').read_text());context=fixture['context'];counts=Counter(r['arc'] for r in fixture['rows'])
    epoch=FrameEpoch(context['origin_ns'],EarthOrientation(ROOT/'data/stage2/finals2000A.all'))
    path=DATA/'IGS0OPSRAP_20262150000_01D_15M_ORB.SP3.gz';reference=read_sp3(path)
    scored=json.loads((folder/'evaluation/evaluation.json').read_text());assert sha(path)==scored['reference_sha256']
    results={}
    for arm,a in m['arms'].items():
        f=np.load(folder/a['final']/'solution.npz');step=json.loads((folder/a['final']/'step.json').read_text())
        assert step['status']=='converged'
        x=dict(zip(map(str,f['names']),f['x']));prior=[]
        for name,value in x.items():
            if name.startswith('orbit:'):prior.append(value/(1000 if int(name.split(':')[-1])<3 else 1))
        for station in context['stations']:
            a0,a3,a6=[x[f'wet:{station}:{t}'] for t in ('0','1','6h')]
            prior.extend((a0/.3,a3/.3,(a3-a0)/.03,(a6-a3)/.03))
        expected_sigma=[]
        for ei in range(context['epoch_count']):
            for row in fixture['rows']:
                if row['epoch']==ei:expected_sigma.extend(row['sigma'][:2 if counts[row['arc']]>=3 else 1])
        np.testing.assert_array_equal(f['sigma_m'],expected_sigma)
        objective=float(np.sum((f['residual_m']/f['sigma_m'])**2)+np.sum(np.square(prior)))
        assert abs(objective-step['history'][-1]['cost_after'])<2e-8
        for trial in a['accepted_trials']:
            index=trial.split('-')[2]
            linear=folder/f'{arm}-linear-{index}';s=np.load(linear/'direction.npz');t=np.load(folder/trial/'solution.npz')
            tr=json.loads((folder/trial/'step.json').read_text())['history'][-1]
            np.testing.assert_array_equal(t['x'],s['x']+tr['step_fraction']*s['step'])
        with np.load(folder/a['accepted_trials'][-1]/'solution.npz') as accepted:
            for k in ('x','states','residual_m','sigma_m'):np.testing.assert_array_equal(accepted[k],f[k])
        covariance=f['retained_covariance'];np.linalg.cholesky(covariance)
        per={};domain={}
        for label,limit in (('common',10810.),('full',float('inf'))):
            sq=[];keys=[]
            for si,sat in enumerate(map(str,f['satellites'])):
                ss=[]
                for ti,t in enumerate(f['times_s']):
                    sample=reference.samples.get((context['origin_ns']+int(round(t*1e9)),sat))
                    if t>limit or not sample or sample.xyz_m is None or sample.maneuver or sample.orbit_predicted:continue
                    d=epoch.celestial_to_terrestrial(t)@f['states'][si,ti,:3]-sample.xyz_m
                    ss.append(float(d@d));keys.append([sat,float(t)])
                assert ss;sq.extend(ss);per[sat]=float(np.sqrt(np.mean(ss)))
                field='before_m' if arm=='fixed' else 'after_m'
                assert abs(per[sat]-scored['domains'][label]['per_satellite'][sat][field])<2e-8
            rms=float(np.sqrt(np.mean(sq)))
            assert keys==scored['domains'][label]['sample_keys']
            assert abs(rms-scored['domains'][label]['cartesian_rms_m'][arm])<2e-8
            domain[label]=dict(samples=len(sq),rms_m=rms)
        results[arm]=dict(objective=objective,domains=domain)
    report=dict(status='dated_archive_and_cartesian_audit_pass_not_accuracy_acceptance',
                campaign_manifest_sha256=sha(folder/'validation.json'),pins_verified=pins,results=results,source_sha256=sha(Path(__file__)))
    (output/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
