"""Guarded August-3 station acquisition, header first, using existing RNXCMP.

One station per worker; at most 8 MiB compressed and 128 MiB decoded. No software
installation. Cached successful artifacts are hash-verified on restart. Writes
only claude/data/day215 and its guard log, preserving original inputs.
"""
import argparse
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import subprocess

from customkf.prepare_stage2 import ROOT, CURL, sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import header, text_stream
from customkf.preprocess import choose_signals
from customkf.antenna import load_calibrations
from customkf.sp3 import epoch_tag
from claude.tools.station_extra_fetch import DECODER, DECODER_SHA256

DEST=ROOT/'claude/data/day215'
MARKERS=('BRUX00BEL','HOB200AUS','ABMF00GLP','KOUG00GUF','DJIG00DJI','NNOR00AUS',
         'MAS100ESP','DAV100ATA','FALK00FLK','FAA100PYF','GLPS00ECU','YELL00CAN','GUAM00GUM')
URL='https://igs.bkg.bund.de/root_ftp/IGS/obs/2026/215/'


def fetch(url,path,limit,range_sample=False):
    args=[CURL,'--fail','--location','--silent','--show-error','--max-time','45',
          '--max-filesize',str(limit)]
    if range_sample:args+=['--range','0-32767']
    done=subprocess.run(args+[url,'-o',str(path)],capture_output=True,text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    if done.returncode:raise RuntimeError('Public data fetch failed: '+done.stderr.strip())
    if path.stat().st_size>limit:raise ValueError('Byte limit exceeded')


def screen(lines):
    meta=header(io.StringIO(''.join(lines)),allow_declared_phase_shifts=True)
    pair=choose_signals(meta.types['G'])
    load_calibrations(DATA/'igs20.atx',[meta.antenna],epoch_tag('* 2026 8 3 11 59 50'))
    # INTERVAL is optional (HOB2 omits it on both days). An absent declaration
    # remains unknown here; native epoch spacing is checked at fixture preflight.
    if meta.interval_s not in (0,30) or meta.time_system!='GPS':raise ValueError('Unexpected cadence/time system')
    return dict(marker=meta.marker,antenna=meta.antenna,receiver=meta.receiver,
                interval_s=meta.interval_s,time_system=meta.time_system,signal_pair=pair.__dict__)


def main():
    folder=Path(os.environ['CUSTOMKF_RUN_DIR'])
    p=argparse.ArgumentParser();p.add_argument('--marker',choices=MARKERS,required=True);marker=p.parse_args().marker
    DEST.mkdir(parents=True,exist_ok=True);record_path=DEST/(marker+'.json')
    if record_path.exists():
        record=json.loads(record_path.read_text())
        for e in record['files']:assert sha(ROOT/e['path'])==e['sha256']
        (folder/'acquisition.json').write_text(json.dumps(record,indent=2)+'\n');print('Verified cached '+marker);return
    assert sha(DECODER)==DECODER_SHA256
    name=f'{marker}_R_20262150000_01D_30S_MO.crx.gz'
    sample=folder/'header.gz';fetch(URL+name,sample,2**20,True)
    if sample.stat().st_size>32768:raise ValueError('Server ignored header range')
    lines=[];started=False
    with gzip.open(sample,'rt') as f:
        for line in f:
            if 'RINEX VERSION / TYPE' in line:started=True
            if started:lines.append(line)
            if 'END OF HEADER' in line:break
    if not lines or 'END OF HEADER' not in lines[-1]:raise ValueError('Incomplete header')
    before=screen(lines)
    (folder/'header.json').write_text(json.dumps(before,indent=2)+'\n')
    compressed=DEST/name;part=DEST/(name+'.part')
    fetch(URL+name,part,8*2**20);part.replace(compressed)
    compact=folder/'input.crx'
    with gzip.open(compressed,'rb') as src,compact.open('wb') as out:
        size=0
        while block:=src.read(65536):
            size+=len(block)
            if size>32*2**20:raise ValueError('Compact size exceeded')
            out.write(block)
    output=DEST/name.replace('.crx.gz','.rnx.gz');part=output.with_suffix('.part')
    with compact.open('rb') as src,(folder/'decoder.log').open('wb') as log:
        child=subprocess.Popen([str(DECODER)],stdin=src,stdout=subprocess.PIPE,stderr=log,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            size=0
            with gzip.open(part,'wb',compresslevel=1) as out:
                while block:=child.stdout.read(65536):
                    size+=len(block)
                    if size>128*2**20:raise ValueError('Decoded size exceeded')
                    out.write(block)
            if child.wait(timeout=5):raise ValueError('Decoder failed')
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
    compact.unlink();part.replace(output)
    with text_stream(output) as f:
        lines=[]
        for line in f:
            lines.append(line)
            if 'END OF HEADER' in line:break
    after=screen(lines);assert after==before
    record=dict(status='header_compatible_not_observation_acceptance',date='2026-08-03',
        retrieved_utc=datetime.now(timezone.utc).isoformat(),url=URL+name,
        header=after,decoder_sha256=DECODER_SHA256,decoded_bytes=size,
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in (compressed,output)])
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    (folder/'acquisition.json').write_text(json.dumps(record,indent=2)+'\n')
    print(marker,after,flush=True)


if __name__=='__main__':main()
