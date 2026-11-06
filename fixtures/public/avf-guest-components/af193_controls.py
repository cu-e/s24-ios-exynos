#!/usr/bin/env python3
"""Narrow accepted-policy/plan intake checks; no allocation or tool execution."""
import argparse
import ast
from datetime import datetime,timezone
import inspect
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--main',required=True,type=Path);p.add_argument('--plans',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
spec=importlib.util.spec_from_file_location('adapter',ROOT/'tools/build/avf_guest_components.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=m.canonical_path(a.out)
if not out.is_relative_to(ROOT/'artifacts/avf-guest-components') or out.exists():raise ValueError('Fresh owned source-check output required')
ledger=m.load(a.main/'state/lab.json')
if not any(e['id']=='AVFCOMP-003' and e['status']=='planned' and e['owner']=='codex-guest-next-executor-20261106-dz' for e in ledger['experiments']):raise ValueError('Register source experiment first')
out.mkdir(parents=True);checks=[];start=time.monotonic();report={'kind':'host-test','origin':'local-host','outcome':'fail','task':'VM-036','experiment':'AVFCOMP-003','recorded_at':datetime.now(timezone.utc).isoformat(),'argv':sys.orig_argv,'checks':checks,'source_sha256':m.sha(Path(m.__file__)),'control_sha256':m.sha(Path(__file__)),'compiler_archiver_loader_or_guest_executed':False,'actual_broker_reserved':False,'original_owner_plan_or_unit_written':False}
def check(name,fn,reject=False,message=None):
 try:r=fn()
 except ValueError as error:
  if not reject or (message and message not in str(error)):raise
  checks.append({'name':name,'outcome':'pass','actual_rejection':str(error)});return
 if reject:raise AssertionError('Unexpected admission '+name)
 checks.append({'name':name,'outcome':'pass'});return r
try:
 policy=m.load(m.POLICY,m.POLICY_SHA256);process=policy['prospective_process']
 if process['sha256']!='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0' or process['independently_accepted'] is not True:raise AssertionError('Wrong final process policy')
 check('one final accepted AF193 physical process pin',lambda:m.pinned({'pins':{'engine':process}},a.main,'engine'))
 for key in process['accepted_receipts']:check('exact accepted receipt '+key,lambda key=key:m.pinned(policy,a.main,key))
 marker=m.pinned_json(policy,a.main,'process_root_acceptance')
 if not(marker['published_head']==process['published_head']=='75fe3857c443c7e631bbd8cf838f7e48cc315844' and marker['common_tests']==170 and marker['common_exit']==0 and marker['owned_after']==[] and marker['lease_released'] is True):raise AssertionError('Invalid accepted root/common receipt')
 check('actual170-PASS root/common/release semantics',lambda:None)
 oldroot=a.main/'worktrees/vm-036-dz-fix2-20261106';oldsource=(oldroot/'tools/build/avf_guest_components.py').read_text();newsource=Path(m.__file__).read_text();oldpolicy=m.load(oldroot/'fixtures/public/avf-guest-components/policy.json')
 oldsha=oldsource.split("POLICY_SHA256 = '")[1].split("'")[0]
 expected=oldsource.replace(oldsha,m.POLICY_SHA256).replace("'archiver_descriptor', 'supervisor']","'archiver_descriptor', 'supervisor', 'process_root_acceptance', 'process_publication', 'process_source_review', 'adapter_source_review']")
 if newsource!=expected:raise AssertionError('Unexpected source change beyond policy constant/receipt names')
 def funcs(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 oldf,newf=funcs(oldsource),funcs(newsource);changed=[name for name in oldf if oldf[name]!=newf.get(name)]
 if changed!=['prepare']:raise AssertionError('Changed authority/parser/resource function')
 check('exact source delta and unchanged execution/parser/resource ASTs',lambda:None);report['changed_existing_functions']=changed
 if any(policy['pins'][key]!=value for key,value in oldpolicy['pins'].items()) or {k for k in policy['pins'] if k not in oldpolicy['pins']}!=set(process['accepted_receipts']):raise AssertionError('Unrelated source/unit/tool pin changed')
 if {k:v for k,v in policy.items() if k not in ['pins','prospective_process']}!={k:v for k,v in oldpolicy.items() if k not in ['pins','prospective_process']}:raise AssertionError('Unrelated policy changed')
 check('all original component/source/tool/namespace policy fields unchanged',lambda:None)
 engine=m.module(a.main/process['path'],process['sha256'],'accepted_process_api')
 report['API']={name:str(inspect.signature(getattr(engine,name))) for name in ['ProjectBudget','project_approval','load_project','run_child']}
 if 'budget' not in inspect.signature(engine.run_child).parameters or 'executor_path' not in inspect.signature(engine.project_approval).parameters:raise AssertionError('Actual accepted API differs')
 check('actual final typed process API surface',lambda:None)
 wrong=out/'wrong-policy.json';wrong.write_text(m.POLICY.read_text()+'\n');check('changed real policy bytes reject',lambda:m.load(wrong,m.POLICY_SHA256),True)
 wrong_receipt=out/'wrong-root-acceptance.json';wrong_receipt.write_text((a.main/policy['pins']['process_root_acceptance']['path']).read_text()+'\n')
 badpolicy=json.loads(json.dumps(policy));badpolicy['pins']['process_root_acceptance']['path']=str(wrong_receipt)
 check('changed real acceptance bytes reject',lambda:m.pinned(badpolicy,a.main,'process_root_acceptance'),True)
 check('wrong AF193 digest rejects before module execution',lambda:m.module(a.main/process['path'],'0'*64,'wrong_engine'),True)
 loaded={};report['plans']={}
 for kind in ['firehose','pthread']:
  file=a.plans/kind/'execution-plan.json';plan=m.load(file);inputs=m.load(a.plans/kind/'input-bindings.json');loaded[kind]=(plan,inputs)
  if not(plan['executor_sha256']==m.sha(Path(m.__file__)) and plan['policy_sha256']==m.POLICY_SHA256 and plan['process_policy']==process and plan['resource_profile']=='project-budget-v1' and plan['qualification']=='source-plan-only' and plan['compiled'] is False):raise AssertionError('New source plan does not bind final code/policy')
  check(kind+' new actual CLI plan binds final code/policy without products',lambda:None)
  unit=m.pinned_json(policy,a.main,kind+'_unit')
  if [c['argv'] for c in plan['commands']]!=[c['argv'] for c in unit['commands']] or [c['cwd'] for c in plan['commands']]!=[c['cwd'] for c in unit['commands']]:raise AssertionError('Historical recipe argv/cwd changed')
  check(kind+' all four historical argv/cwd arrays unchanged',lambda:None)
  if m.sha(plan['commands'][-1]['filelist'])!=plan['commands'][-1]['filelist_sha256']:raise AssertionError('Old filelist changed')
  check(kind+' exact original filelist remains unchanged',lambda:None)
  prior=a.main/'worktrees/vm-036-dz-20261106/artifacts/avf-guest-components/plans-001'/kind/'input-bindings.json'
  if (a.plans/kind/'input-bindings.json').read_bytes()!=prior.read_bytes():raise AssertionError('Unrelated source namespace bytes changed')
  check(kind+' actual complete source-input binding bytes equal historical',lambda:None)
  report['plans'][kind]={'path':str(file.relative_to(a.main)),'sha256':m.sha(file),'input_bindings_sha256':m.sha(a.plans/kind/'input-bindings.json'),'unit':policy['pins'][kind+'_unit'],'output_scope':'VM036-owned source-only review artifact, not original-owner execution plan'}
 args=SimpleNamespace(main=a.main,out=out/'never-created',task='VM-036',owner='codex-guest-next-executor-20261106-dz',experiment='AVFCOMP-003',shard='firehose')
 approval={'schema':'project-budget-v1','reviewed_executor_sha256':'0'*64,'runner_reviewed':True,'root_lease':'negative-only-no-live-lease','root_lease_path':'artifacts/negative-only-missing.json','root_lease_sha256':'0'*64,'resource_queue_path':'artifacts/team-coordination/20261106-team/resource-queue.json','max_jobs_per_executor':1,'task':args.task,'owner':args.owner,'experiment':args.experiment,'shard':args.shard,'source_plan_sha256':report['plans']['firehose']['sha256'],'qemu_allowed':False}
 check('actual accepted API rejects wrong caller before allocation',lambda:engine.project_approval(args,approval,executor_path=Path(m.__file__)),True,'Approval must bind')
 # Negative-only dependency substitution reaches the unchanged plan comparison
 # without impersonating a component owner or reserving any real broker slot.
 # Both compared plans are real retained CLI outputs, not fake hardware/input.
 oldplan=m.load(a.main/'worktrees/vm-036-dz-20261106/artifacts/avf-guest-components/plans-001/firehose/execution-plan.json')
 current,bindings=loaded['firehose'];sentinel=out/'negative-approval.json';sentinel.write_text('{}\n');calls=[]
 original_module,original_owner,original_plan=m.module,m.owner_authority,m.plan
 original_approval=engine.project_approval
 class NegativeBudget:
  source_plan=oldplan;rss_limit=256*1024**2
  def reserve(self):calls.append('reserve');raise AssertionError('Negative fixture reached reservation')
  def release(self):calls.append('release');raise AssertionError('Negative fixture reached release')
 def fixture_module(path,expected,name):
  if name=='component_budget_engine':
   if expected!=process['sha256'] or Path(path)!=a.main/process['path']:raise AssertionError('Wrong process source')
   return engine
  return original_module(path,expected,name)
 engine.project_approval=lambda *args,**kwargs:NegativeBudget()
 m.module=fixture_module;m.owner_authority=lambda *args,**kwargs:{'negative_only_fixture':True};m.plan=lambda *args,**kwargs:(current,bindings)
 probe=SimpleNamespace(main=a.main,out=Path(current['output']),component='firehose',task='VM-036',owner=args.owner,experiment=args.experiment,approval=sentinel,approval_sha256=m.sha(sentinel))
 try:check('existing gate rejects real old policy/source plan before reserve/mkdir',lambda:m.execute(probe),True,'Root allocation does not bind')
 finally:m.module=original_module;m.owner_authority=original_owner;m.plan=original_plan;engine.project_approval=original_approval
 if calls or Path(current['output']).exists():raise AssertionError('Negative fixture touched component output/allocation')
 check('negative plan fixture performs no allocation or original-owner output write',lambda:None)
 report['plan_mismatch_control']='Clearly labeled negative budget/authority dependency fixture; unchanged actual execute guard compares two real CLI plans and rejects before reserve/mkdir. No actual owner impersonation or shared queue mutation.'
 if m.sha(oldroot/'tools/build/avf_guest_components.py')!='3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f':raise AssertionError('Prior frozen source changed')
 check('prior accepted physical source remains frozen',lambda:None)
 report.update(outcome='pass',policy_sha256=m.POLICY_SHA256,process=process,summary={'checks_passed':len(checks),'actual_source_only_cli_plans':2,'compiler_archiver_loader_or_guest_commands':0,'real_broker_reservations':0,'new_component_products':0,'historical_matrices_repeated':False})
except BaseException as error:
 report['failure']={'type':type(error).__name__,'message':str(error)};raise
finally:
 report.update(elapsed_seconds=time.monotonic()-start,source_sha256_after=m.sha(Path(m.__file__)))
 m.write(out/'evidence.json',report)
print(json.dumps(report['summary']))
