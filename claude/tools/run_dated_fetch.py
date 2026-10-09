"""Direct controller: serial guarded header-first acquisition, no nested guards."""
from datetime import datetime,timezone
import json
import os
import shutil
from customkf.guard import ROOT,Limits,run
from customkf.prepare_stage2 import sha
from claude.tools.dated_fetch import MARKERS,DEST


def main():
    if os.environ.get('CUSTOMKF_RUN_DIR'):raise RuntimeError('Run controller directly')
    folder=ROOT/'claude/runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-day215-inputs')
    folder.mkdir(parents=True)
    report=dict(status='running',controller_pid=os.getpid(),runs={},active_worker=None)
    def save():(folder/'campaign.json').write_text(json.dumps(report,indent=2)+'\n')
    print(str(folder),flush=True)
    try:
        for marker in MARKERS:
            report['active_worker']=marker;save();print('Starting '+marker,flush=True)
            result,path=run(['claude.tools.dated_fetch','--marker',marker],Limits(timeout_s=120))
            shutil.move(str(path),str(folder/marker));report['runs'][marker]=result;report['active_worker']=None;save()
            print(marker,result['status'],round(result.get('elapsed_s',0),1),flush=True)
            if result['status']!='ok':raise RuntimeError('Acquisition stopped at '+marker)
        files=[]
        for marker in MARKERS:
            files.extend(e for e in json.loads((DEST/(marker+'.json')).read_text())['files'] if e['path'].endswith('.rnx.gz'))
        manifest=DEST/'inputs.json';manifest.write_text(json.dumps(dict(files=files),indent=2)+'\n')
        report.update(status='header_acquisition_complete_not_fixture_acceptance',input_manifest_sha256=sha(manifest))
    except Exception as e:
        report.update(status='failed',error=str(e));raise
    finally:save()


if __name__=='__main__':main()
