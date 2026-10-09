"""Guarded evaluator for dated fixed-D0 versus estimated-D0 station fits.

References are isolated here; no estimator is instantiated. Native IGS sample
keys are identical in both arms. Cartesian RMS is recomputed independently of
RAC scoring; all satellites and covariance-based coverage classes are retained.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import numpy as np
from customkf.prepare_stage2 import ROOT,DATA as DYN,sha
from customkf.prepare_stage3 import DATA
from customkf.frames import FrameEpoch,EarthOrientation
from customkf.precise import PreciseProducts
from customkf.sp3 import read_sp3
from customkf.comparison import rac_difference
from claude.tools.evaluate_ablation import score,strip,pooled
from claude.tools.d0_weak_compare import declared_cost


class Reference:
    def __init__(self,context,limit=None):
        self.origin=context['origin_ns'];self.limit=limit
        stamp=datetime.strptime(context['day'],'%Y-%m-%d').strftime('%Y%j')
        path=DATA/f'IGS0OPSRAP_{stamp}0000_01D_15M_ORB.SP3.gz'
        pinned=next(e['sha256'] for e in json.loads((DATA/'manifest.json').read_text())['files']
                    if e['path']==path.relative_to(ROOT).as_posix())
        assert sha(path)==pinned
        self.sha256=pinned;self.epoch=FrameEpoch(self.origin,EarthOrientation(DYN/'finals2000A.all'))
        self.precise=PreciseProducts([path],[],self.origin,self.epoch.eop);self.raw=read_sp3(path)
        assert self.raw.frame=='IGc20'

    def sample(self,sat,t):
        if self.limit is not None and t>self.limit:return None
        s=self.raw.samples.get((self.origin+int(round(t*1e9)),sat))
        return s if s and s.xyz_m is not None and not s.maneuver and not s.orbit_predicted else None

    def rac(self,sat,t,xyz):
        s=self.sample(sat,t)
        if s is None:return None
        return rac_difference(self.epoch.celestial_to_terrestrial(t).T@s.xyz_m,xyz,self.precise.state(sat,t)[3:])


def main():
    output=Path(os.environ['CUSTOMKF_RUN_DIR']);folder=Path(sys.argv[1])
    manifest=json.loads((folder/'validation.json').read_text())
    prep=folder/'prepare';fixture=json.loads((prep/'fixture.json').read_text());c=fixture['context']
    fits={};audits={}
    for arm in ('fixed','d0'):
        path=folder/manifest['arms'][arm]['final'];step=json.loads((path/'step.json').read_text())
        assert step['status']=='converged' and sha(path/'solution.npz')==step['solution_sha256']
        fits[arm]=np.load(path/'solution.npz');f=fits[arm]
        names={str(n):i for i,n in enumerate(f['names'])}
        cost,_=declared_cost(f,names,list(map(str,f['satellites'])),sorted(c['stations']),1000.,1.)
        assert abs(cost-step['history'][-1]['cost_after'])<2e-8
        np.testing.assert_allclose(f['retained_covariance'],f['retained_covariance'].T,rtol=0,atol=1e-12)
        np.linalg.cholesky(f['retained_covariance'])
        audits[arm]=dict(objective=cost,solution_sha256=sha(path/'solution.npz'))
    for k in ('satellites','times_s','sigma_m'):np.testing.assert_array_equal(fits['fixed'][k],fits['d0'][k])
    domains={}
    for domain,limit in (('common',10810.),('full',None)):
        ref=Reference(c,limit);scores={};keys={};cart={}
        for arm,f in fits.items():
            scores[arm]=score(ref,folder/manifest['arms'][arm]['final'],prep/'fixture.json',prep/'initial.npz')
            keys[arm]=[];sq=[]
            for si,sat in enumerate(map(str,f['satellites'])):
                for ti,t in enumerate(map(float,f['times_s'])):
                    s=ref.sample(sat,t)
                    if s is None:continue
                    d=ref.epoch.celestial_to_terrestrial(t)@f['states'][si,ti,:3]-s.xyz_m
                    sq.append(float(d@d));keys[arm].append([sat,t])
            cart[arm]=float(np.sqrt(np.mean(sq)))
            np.testing.assert_allclose(cart[arm],scores[arm]['groups']['all']['fit']['rms_3d_m'],rtol=0,atol=2e-8)
        assert keys['fixed']==keys['d0'] and keys['fixed']
        per={s:dict(before_m=v['fit']['rms_3d_m'],after_m=scores['d0']['per_satellite'][s]['fit']['rms_3d_m'],
                    change_m=scores['d0']['per_satellite'][s]['fit']['rms_3d_m']-v['fit']['rms_3d_m'])
             for s,v in scores['fixed']['per_satellite'].items()}
        both=[s for s in per if all(scores[a]['per_satellite'][s]['class']=='determined' for a in scores)]
        domains[domain]=dict(samples=len(keys['fixed']),sample_keys=keys['fixed'],cartesian_rms_m=cart,
            reduction_percent=100*(1-cart['d0']/cart['fixed']),per_satellite=per,
            regressions_over_10_cm=[s for s,v in per.items() if v['change_m']>.1],
            determined_in_both={a:pooled(v,both) for a,v in scores.items()},
            scores={a:strip(v) for a,v in scores.items()})
    f=fits['d0'];names={str(n):i for i,n in enumerate(f['names'])}
    coefficients={str(s):dict(D0_mps2=-1e-7+1e-7*float(f['x'][names[f'srpD0:{s}']]),
        formal_sigma_mps2=1e-7*float(np.sqrt(f['retained_covariance'][names[f'srpD0:{s}'],names[f'srpD0:{s}']]))) for s in f['satellites']}
    report=dict(status='dated_paired_evaluation_complete_not_accuracy_acceptance',day=c['day'],
        reference_sha256=ref.sha256,fixture_sha256=sha(prep/'fixture.json'),audits=audits,domains=domains,coefficients=coefficients)
    (output/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:{n:v[n] for n in ('samples','cartesian_rms_m','reduction_percent','regressions_over_10_cm')} for k,v in domains.items()},indent=2),flush=True)


if __name__=='__main__':main()
