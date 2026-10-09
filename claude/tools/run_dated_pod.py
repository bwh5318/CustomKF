"""Direct serial controller for the frozen August-3 paired POD experiment.

Preparation is imported only after its dimension gate passes. Each linearization
or individual trial gets its own unchanged guard (300s); reference scoring is a
separate 120s job. No resume mode: inspect the saved manifest/checkpoints first
after interruption. No numerical worker may run concurrently with this controller.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
from customkf.guard import ROOT,Limits,run
from customkf.prepare_stage2 import sha
from claude.tools.dated_fixture import sources


def main():
    if os.environ.get('CUSTOMKF_RUN_DIR'):raise RuntimeError('Run controller directly')
    p=argparse.ArgumentParser();p.add_argument('--prepare',required=True,type=Path);a=p.parse_args()
    prep=a.prepare.resolve();meta=json.loads((prep/'step.json').read_text())
    assert meta['status']=='prepared' and meta['budget_pass'] and meta['day']=='2026-08-03'
    assert sha(prep/'fixture.json')==meta['fixture_sha256'] and sources()==meta['source_sha256']
    protocol=ROOT/'D0_DAY215_PROTOCOL.md'
    assert protocol.exists()
    folder=ROOT/'claude/runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-day215-pod')
    folder.mkdir(parents=True);shutil.copytree(prep,folder/'prepare')
    pins=sources()|{'claude/tools/run_dated_pod.py':sha(Path(__file__)),'D0_DAY215_PROTOCOL.md':sha(protocol)}
    report=dict(status='running',controller_pid=os.getpid(),active_worker=None,source_sha256=pins,
        report_sha256={n:sha(ROOT/n) for n in ('GPS_POD_PROGRESS_REPORT.md','GPS_POD_PROGRESS_REPORT.pdf','GPS_POD_PROGRESS_REPORT.manifest.json')},
        preparation_original=str(prep),runs={},arms={a:dict(final=None,accepted_trials=[]) for a in ('fixed','d0')})
    for name in pins:
        target=folder/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    def save():
        pending=folder/'pending.json';pending.write_text(json.dumps(report,indent=2)+'\n');pending.replace(folder/'validation.json')
    def worker(name,args,timeout=300):
        for group in ('source_sha256','report_sha256'):
            for path,digest in report[group].items():assert sha(ROOT/path)==digest,path
        report['active_worker']=dict(name=name,args=args,controller_pid=os.getpid());save()
        print('Starting '+name,flush=True)
        result,path=run(args,Limits(timeout_s=timeout));shutil.move(str(path),str(folder/name))
        report['runs'][name]=result;report['active_worker']=None;save()
        print(name,result['status'],round(result.get('elapsed_s',0),1),flush=True)
        if result['status']!='ok':raise RuntimeError('Stopped at '+name)
        return folder/name
    print('Campaign '+str(folder),flush=True);save()
    try:
        fixture=folder/'prepare/fixture.json'
        for arm in ('fixed','d0'):
            previous=None
            for i in range(4):
                args=['claude.tools.dated_iteration','linear','--fixture',str(fixture),'--variant',arm]
                if previous:args+=['--previous',str(previous)]
                linear=worker(f'{arm}-linear-{i}',args)
                if json.loads((linear/'step.json').read_text())['status']=='converged':
                    report['arms'][arm]['final']=linear.name;save();break
                accepted=False
                for ai,alpha in enumerate((1.,.5,.25,.125)):
                    trial=worker(f'{arm}-trial-{i}-{ai}',['claude.tools.dated_iteration','trial','--fixture',str(fixture),
                        '--variant',arm,'--linear',str(linear),'--alpha',str(alpha)])
                    if json.loads((trial/'step.json').read_text())['status']=='iteration_complete':
                        previous=trial;report['arms'][arm]['accepted_trials'].append(trial.name);save();accepted=True;break
                if not accepted:raise RuntimeError('Line search failed')
            if report['arms'][arm]['final'] is None:raise RuntimeError('Stationarity not reached before iteration cap')
        worker('evaluation',['claude.tools.dated_evaluate',str(folder)],120)
        report['status']='day215_paired_pod_complete_not_accuracy_acceptance'
    except Exception as e:report.update(status='failed',error=str(e));raise
    finally:
        values=list(report['runs'].values())
        report.update(total_guarded_seconds=sum(v.get('elapsed_s',0) for v in values),
            peak_job_memory_mib=max([v.get('windows_peak_job_memory_mib',0) for v in values] or [0]),
            minimum_system_available_gib=min([v.get('minimum_system_available_gib',float('inf')) for v in values] or [float('inf')]))
        report['artifacts_sha256']={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*')
                                    if p.is_file() and p.name not in ('validation.json','pending.json')}
        save()


if __name__=='__main__':main()
