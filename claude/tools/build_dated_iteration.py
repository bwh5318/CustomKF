"""One-time isolated adaptation of the verified split iteration for two arms."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
text=(ROOT/'claude/tools/d0_iteration.py').read_text()
text=text.replace('from customkf.stage5b_step import restore','from claude.tools.dated_fixture import restore')
text=text.replace('from claude.tools.d0_pilot import D0Pilot',
                  'from claude.tools.dated_d0 import D0Pilot\nfrom claude.tools.dated_arc import ArcPilot')
text=text.replace('from claude.tools.ablation_step import sources','from claude.tools.dated_fixture import sources')
text=text.replace('    args=parser.parse_args();',
                  '    parser.add_argument("--variant",choices=("fixed","d0"),required=True)\n    args=parser.parse_args();')
text=text.replace('    pilot=D0Pilot(*restore(args.fixture))',
                  '    pilot=(D0Pilot if args.variant=="d0" else ArcPilot)(*restore(args.fixture))')
start=text.index('        previous=json.loads(')
end=text.index('        blocks,constraints,',start)
text=text[:start]+'''        x=np.zeros(len(pilot.names));history=[]
        if args.previous:
            previous=json.loads((args.previous/"step.json").read_text())
            assert previous["fixture_sha256"]==meta["fixture_sha256"] and sha(args.previous/"solution.npz")==previous["solution_sha256"]
            saved=np.load(args.previous/"solution.npz");np.testing.assert_array_equal(saved["names"],pilot.names)
            x=saved["x"].copy();history=previous["history"]
'''+text[end:]
old='for s in pilot.sats for t in np.arange(10.,pilot.duration-9.,300.))'
assert old in text
text=text.replace(old,old+' if args.variant=="d0" else 0.')
text='# Isolated dated adaptation of d0_iteration.py; original module preserved.\n'+text
ast.parse(text)
path=ROOT/'claude/tools/dated_iteration.py'
assert not path.exists()
path.write_text(text)
