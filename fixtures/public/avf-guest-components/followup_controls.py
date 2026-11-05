#!/usr/bin/env python3
"""Focused quarantined-policy and same-read input race controls; no compiler."""
from pathlib import Path
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
import sys
import time
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--main',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
spec=importlib.util.spec_from_file_location('adapter_followup',ROOT/'tools/build/avf_guest_components.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
out=v.canonical_path(a.out)
if not out.is_relative_to(ROOT/'artifacts/avf-guest-components') or out.exists():raise ValueError('Fresh owned output required')
ledger=v.load(a.main/'state/lab.json')
if not any(e['id']=='AVFCOMP-001' and e['status']=='planned' and e['owner']=='codex-guest-next-executor-20261106-dz' for e in ledger['experiments']):raise ValueError('Original experiment registration required')
out.mkdir(parents=True);checks=[];report={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.now(timezone.utc).isoformat(),'task':'VM-036','argv':sys.argv,'checks':checks,'source_sha256':v.sha(Path(v.__file__)),'control_sha256':v.sha(Path(__file__)),'compiler_executed':False,'archiver_executed':False,'guest_executed':False};start=time.monotonic()
def check(name,fn,reject=False):
 try:result=fn()
 except ValueError as error:
  if not reject:raise
  checks.append({'name':name,'outcome':'pass','actual_rejection':str(error)});return
 if reject:raise AssertionError('Unexpected admission '+name)
 checks.append({'name':name,'outcome':'pass'});return result
try:
 for kind in ['firehose','pthread']:
  policy,helper,unit,commands,index,target=check(kind+' exact original recipe after input-reader change',lambda kind=kind:v.prepare(a.main,kind))
  args=SimpleNamespace(main=a.main,component=kind,out=target,task=policy['components'][kind]['task'],owner=policy['components'][kind]['owner'],experiment='AVFFH-001' if kind=='firehose' else 'AVFPTH-003',approval=None,approval_sha256=None)
  check(kind+' quarantined process policy cannot execute even with original authority',lambda:v.execute(args),True)
  if target.exists():raise AssertionError('Quarantine created original execution root')
  check(kind+' no execution root created',lambda:None)
 for kind in ['json','module']:
  victim=out/('race.'+kind);replacement=out/('replacement.'+kind)
  old=b'{"value":"original"}' if kind=='json' else b'value="original"\n'
  changed=b'{"value":"replacement"}' if kind=='json' else b'value="replacement"\n'
  victim.write_bytes(old);replacement.write_bytes(changed);digest=v.sha(victim);normal_open=Path.open;opens=[]
  def race_open(path,*args,**kwargs):
   stream=normal_open(path,*args,**kwargs)
   if path==victim:
    opens.append(str(path))
    if len(opens)==1:os.replace(replacement,victim)
   return stream
  Path.open=race_open
  try:result=v.load(victim,digest) if kind=='json' else v.module(victim,digest,'actual_replaced_module')
  finally:Path.open=normal_open
  value=result['value'] if kind=='json' else result.value
  if value!='original' or len(opens)!=1 or victim.read_bytes()!=changed:raise AssertionError('Did not parse/execute the one original captured byte snapshot')
  check(kind+' actual pathname replacement after open consumes original captured bytes once',lambda:None)
  check(kind+' subsequent changed pathname rejected',lambda:v.load(victim,digest) if kind=='json' else v.module(victim,digest,'changed_module'),True)
 original=a.main/'worktrees/vm-036-dz-20261106/tools/build/avf_guest_components.py'
 if v.sha(original)!='7f6b93bd852194ff65c8b81888b660f48b5f9ee4a710370ef0b3b0c6aa389a5a':raise ValueError('Historical physical source changed')
 check('original physical8b11/PASS88 source preserved',lambda:None)
 baseline=a.main/'worktrees/vm-036-dz-20261106/artifacts/avf-guest-components/handoff-001/evidence.json';previous=v.load(baseline,'37b88f5a3ec7800233b77d34b34e299968d245916ae5f3f0ec6c9f1275eee2d2')
 for path,digest in previous['artifact_hashes'].items():
  if v.sha(a.main/path)!=digest:raise ValueError('Historical artifact changed')
 for path,digest in previous['source_bindings'].items():
  if v.sha(a.main/path)!=digest:raise ValueError('Historical frozen source changed')
 check('historical117 artifact and8 source bindings unchanged',lambda:None)
 report.update(outcome='pass',summary={'checks_passed':len(checks),'historical_checks_reused':88,'compiler_or_archiver_commands':0,'actual_replacement_races':2},baseline_evidence=str(baseline),baseline_sha256=v.sha(baseline))
except BaseException as error:
 report['failure']={'type':type(error).__name__,'message':str(error)};raise
finally:
 report.update(elapsed_seconds=time.monotonic()-start,current_image_memory=helper.actual_controller_memory() if 'helper' in locals() else {})
 v.write(out/'evidence.json',report)
print(json.dumps(report['summary']))
