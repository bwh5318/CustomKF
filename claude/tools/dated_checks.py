"""Guarded regression of measurement derivatives and explicit seasonal date.

Uses the saved August-2 fixture, not IGS. Compare old/date-aware state, receiver
clock and D0 partials exactly on six spread-out links. Independently derive the
seasonal epoch from calendar arithmetic, including the receiver-clock correction.
"""
from datetime import datetime,timedelta
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import numpy as np
from customkf.prepare_stage2 import ROOT,sha
from customkf.stage5_pilot import forbid_precise_product_reads
from customkf.stage5b_step import restore as old_restore
from customkf.dynamic_observation import link_jacobian as old_jac
from claude.tools.d0_pilot import D0Pilot as OldPilot
from claude.tools.dated_d0 import D0Pilot
from claude.tools.dated_fixture import restore
from claude.tools import dated_observation as obs


def main():
    output=Path(os.environ['CUSTOMKF_RUN_DIR']);fixture=Path(sys.argv[1]);sys.addaudithook(forbid_precise_product_reads)
    base=ROOT/'claude/runs/20260912T145220Z-station-d0'
    old=OldPilot(*old_restore(base/'prepare/fixture.json'));new=D0Pilot(*restore(fixture))
    with np.load(base/'linear-1/solution.npz') as z:x=z['x'].copy()
    np.testing.assert_array_equal(old.names,new.names)
    op=old.products(x);np_=new.products(x);count=0;date_errors=[]
    for index in np.linspace(0,len(new.rows)-1,6,dtype=int):
        a,b=old.rows[index],new.rows[index];c=new.context
        antenna=c['stations'][b['station']]['header']['antenna']
        args=(c['rx_cal'][antenna],c['sat_cal'][b['satellite']],c['ephemeris'])
        state=new.state_for(x,b);wind=new.windup[id(b)]
        ja=old_jac(op,a,*args,*old.state_for(x,a),old.windup[id(a)])
        jb=obs.link_jacobian(np_,b,*args,*state,wind)
        for u,v in zip(ja,jb):np.testing.assert_array_equal(u,v);count+=np.size(u)
        np.testing.assert_array_equal(old.force_partial_for(op,a,x),new.force_partial_for(np_,b,x));count+=2
        real=obs.troposphere;seen=[]
        def spy(xyz,elevation,doy):seen.append(doy);return real(xyz,elevation,doy)
        shifted=b|{'origin_doy':215}
        with patch.object(obs,'troposphere',side_effect=spy):
            g,_=obs.modeled_link(np_,shifted,*args,*state,wind,details=True)
        # Calendar computation independent of the row's DOY expression.
        absolute=datetime(2026,8,3,11,59,50)+timedelta(seconds=g['receive_s'])
        expected=1+(absolute-datetime(2026,1,1)).total_seconds()/86400
        error=abs(seen[0]-expected);assert error<2e-11;date_errors.append(error)
    report=dict(status='dated_partial_and_calendar_regression_pass',exact_partial_entries=count,
                max_independent_calendar_error_days=max(date_errors),fixture_sha256=sha(fixture),source_sha256=sha(Path(__file__)))
    (output/'checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
