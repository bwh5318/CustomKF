"""One-time, auditable creation of isolated date-aware research modules.

Preserves the pinned originals. Generated files are ordinary inspectable Python,
not runtime source rewriting. Refuses to overwrite a prior generated module.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'claude/tools'
provenance = {}


def source(name):
    p = ROOT / name
    provenance[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return p.read_text()


def replace(text, old, new):
    assert old in text, old
    return text.replace(old, new)


def write(name, text):
    p = OUT / name
    assert not p.exists(), p
    text = '# Isolated date-aware adaptation; see dated_module_origins.json.\n' + text
    ast.parse(text)
    p.write_text(text)


dynamic = source('customkf/dynamic_observation.py').replace('from .', 'from customkf.')
dynamic = replace(dynamic, '214+(43190+g["receive_s"])/86400',
    'row["origin_doy"]+(row["origin_second_of_day"]+g["receive_s"])/86400')
write('dated_observation.py', dynamic)

stage = source('customkf/stage5_pilot.py').split('\ndef main():')[0]
stage = stage.split('    def solve(self,')[0]  # Only the bounded split solver is used.
stage = stage.replace('from .', 'from customkf.')
stage = replace(stage, 'from customkf.dynamic_observation import', 'from claude.tools.dated_observation import')
stage = replace(stage, 'from datetime import datetime', 'from datetime import datetime, timedelta')
stage = replace(stage, 'station_subset=None, profile="legacy"):',
    'station_subset=None, profile="nominal-cadence", day="2026-08-02", input_manifest=None):')
stage = replace(stage, '    if profile not in', '''    date = datetime.strptime(day, "%Y-%m-%d")
    if profile != "nominal-cadence":
        raise ValueError("Dated replication supports only the frozen ten-minute profile")
    origin = epoch_tag(f"* {date.year} {date.month} {date.day} 11 59 50")
    stamp = date.strftime("%Y%j")
    doy = int(date.strftime("%j"))
    if profile not in''')
stage = stage.replace('"BRDC00WRD_R_20262140000_01D_MN.rnx.gz"', 'f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"')
stage = stage.replace('20262140000_01D_30S_MO', '{stamp}0000_01D_30S_MO')
stage = replace(stage, '    inputs = [DATA/name for name in names]', '''    overrides = {}
    if input_manifest is not None:
        for entry in json.loads(Path(input_manifest).read_text())["files"]:
            p = ROOT/entry["path"]
            if p.name in overrides: raise ValueError("Duplicate input basename")
            overrides[p.name] = p
            pinned[entry["path"]] = entry["sha256"]
    def path_for(name): return overrides.get(name, DATA/name)
    inputs = [path_for(name) for name in names]''')
stage = stage.replace('DATA/f"BRDC', 'path_for(f"BRDC').replace('DATA/f"{marker}', 'path_for(f"{marker}')
stage = replace(stage, 'navigation = read_gps_navigation(path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz")',
    'navigation = read_gps_navigation(path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz"))')
stage = replace(stage, 'with text_stream(path_for(f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz") as stream:',
    'with text_stream(path_for(f"{marker}_R_{stamp}0000_01D_30S_MO.rnx.gz")) as stream:')
# Replace epoch usage in prepare, leaving the legacy constant available solely as
# an August-2 compatibility symbol. Pilot.products uses context, never that symbol.
head, tail = stage.split('\nclass Pilot:', 1)
prefix, prep = head.split('\ndef prepare', 1)
prep = prep.replace('ORIGIN', 'origin').replace('datetime(2026,8,2,12)', 'date+timedelta(hours=12)')
prep = replace(prep, '"observation":np.array',
    '"origin_doy":doy,"origin_second_of_day":43190.,"observation":np.array')
prep = replace(prep, '"profile":profile,"navigation_cutoff_ns":cutoff_ns}',
    '"profile":profile,"navigation_cutoff_ns":cutoff_ns,"origin_ns":origin,"day":day,\n'
    '               "navigation_path":path_for(f"BRDC00WRD_R_{stamp}0000_01D_MN.rnx.gz").relative_to(ROOT).as_posix()}')
tail = tail.replace(',ORIGIN,', ',self.context["origin_ns"],')
stage = prefix+'\ndef prepare'+prep+'\nclass Pilot:'+tail
write('dated_stage5.py', stage)

arc = source('claude/tools/arc_pilot.py').replace('from customkf.stage5_pilot import Pilot',
    'from claude.tools.dated_stage5 import Pilot')
write('dated_arc.py', arc)
d0 = source('claude/tools/d0_pilot.py').replace('from customkf.dynamic_observation import modeled_link',
    'from claude.tools.dated_observation import modeled_link').replace('from customkf.stage5_pilot import ORIGIN\n', '')
d0 = d0.replace('from claude.tools.arc_pilot import ArcPilot', 'from claude.tools.dated_arc import ArcPilot')
d0 = d0.replace(',ORIGIN,', ',self.context["origin_ns"],')
write('dated_d0.py', d0)
(OUT/'dated_module_origins.json').write_text(json.dumps(provenance, indent=2)+'\n')
