#!/usr/bin/env python3
"""Require new historical_paths field to have its documented JSON array type."""
import importlib.util,json,sys
from pathlib import Path
here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('history_controls',here/'controls.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
g=c.load(Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/int-history-gate-20261106/tools/integration_gate.py'),'frozen_schema_gate')
results=[]
for kind,name,value in [('object','transient.py',{'transient.py':{'unrecognized':'ignored'}}),('string','a','a')]:
 f=c.Fixture(transient=name)
 try:
  p=dict(f.plan,historical_paths=value);r=c.audit(g,f,p);r.update(name='reject malformed historical_paths '+kind,expected_acceptance=False,pass_control=not r['accepted']);results.append(r)
 finally:f.close()
report={'kind':'host-test','outcome':'pass' if all(r['pass_control'] for r in results) else 'fail','cases':results,'publication_common_compiler_guest_started':False,'fixture_git_commands':c.COMMANDS}
(here/'schema-control.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'outcome':report['outcome'],'actual_acceptance':[r['accepted'] for r in results]}))
sys.exit(0 if report['outcome']=='pass' else 1)
