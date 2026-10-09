"""Guarded native epoch/date/cadence preflight for the full day-215 network.

Header compatibility is not data acceptance. Count actual GPS epoch spacing,
events and data span, require the requested day, and report gaps without changing
the frozen row rules or dropping stations. No reference products are opened.
"""
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from customkf.prepare_stage2 import ROOT,sha
from customkf.prepare_stage3 import DATA
from customkf.rinex import text_stream,header,epochs
from customkf.sp3 import epoch_tag
from customkf.stage5_pilot import forbid_precise_product_reads
from claude.tools.dated_fetch import MARKERS,DEST


def main():
    output=Path(os.environ['CUSTOMKF_RUN_DIR']);sys.addaudithook(forbid_precise_product_reads)
    midnight=epoch_tag('* 2026 8 3 0 0 0');report={}
    markers=(*MARKERS,'KOUR00GUF')
    for marker in markers:
        name=f'{marker}_R_20262150000_01D_30S_MO.rnx.gz'
        path=(DATA if marker.startswith('KOUR') else DEST)/name
        times=[];flags=Counter()
        with text_stream(path) as f:
            h=header(f,allow_declared_phase_shifts=True)
            if h.marker[:4]!=marker[:4]:raise ValueError('Wrong station marker')
            for obs in epochs(f,h):
                if not midnight<=obs.gps_ns<midnight+86400*10**9:raise ValueError('Epoch outside requested day')
                flags[obs.flag]+=1
                if obs.flag in (0,1):times.append(obs.gps_ns)
        if not times or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Missing or unordered native epochs')
        intervals=Counter((b-a)/1e9 for a,b in zip(times,times[1:]))
        if 30. not in intervals or any(t%30 for t in intervals):raise ValueError('Unexpected native cadence')
        if any((t-midnight)%(30*10**9) for t in times):raise ValueError('Epochs off nominal 30-second grid')
        first=(times[0]-midnight)/1e9;last=(times[-1]-midnight)/1e9
        if first>12*3600 or last<18*3600:raise ValueError('Daily file does not span the requested arc')
        report[marker]=dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path),native_epochs=len(times),
            declared_interval_s=h.interval_s,first_second=first,last_second=last,
            intervals_s={str(k):v for k,v in sorted(intervals.items())},events=dict(flags),
            gaps=[dict(previous_second=(a-midnight)/1e9,next_second=(b-midnight)/1e9,
                       spacing_s=(b-a)/1e9) for a,b in zip(times,times[1:]) if b-a>30*10**9])
        print(marker,len(times),'epochs; spacing',dict(intervals),flush=True)
    (output/'input_check.json').write_text(json.dumps(dict(status='day215_native_input_preflight_pass',stations=report),indent=2)+'\n')


if __name__=='__main__':main()
