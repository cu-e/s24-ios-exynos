#!/usr/bin/env python3
"""Read-only validation of the one root91 four-tail measurement; no children."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
CALLER=WT/'fixtures/public/e1s-native-tails/run_tails.py'
OUT=WT/'artifacts/e1s-native-tails/execute-2'
DEST=WT/'artifacts/e1s-native-tails/validation-1'
def pin(path):
 path=Path(path)
 with path.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
 return dict(path=str(path),sha256=sha,bytes=path.stat().st_size)
def bound(path,sha):
 assert pin(path)['sha256']==sha,str(path)
 return json.loads(Path(path).read_text())
assert pin(CALLER)['sha256']=='51606d77bd3dfbc106ac8c6d95d990e3239717f8507622399bd76df705e26c8f'
spec=importlib.util.spec_from_file_location('actual_native_tail_caller',CALLER)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
native,common=c.helpers()
plan=bound(WT/'artifacts/e1s-native-tails/plan-2/source-plan-final.json','0e35588be01a8b0f0aca29739f05ecfb72af729a231e5e8272405e58f476d1bc')
raw=bound(OUT/'evidence.json','01dec0f40beff57046607671028f93e1a53c628e450fcfc58c45f09335a032de')
assert json.loads((OUT/'execution-plan.json').read_text())==plan
assert raw['outcome']=='pass' and not raw['owned_survivors']
assert not any(k in raw for k in ['failure','release_error','cancellation_signals'])
c.verify(native,common,plan);native.private_inputs(plan)
core=native.module(*native.PINS[1],'actual_tail_core')
supervise=native.module(*native.PINS[2],'actual_tail_supervisor')
cwd=plan['commands'][0]['cwd']
expected=[plan['loader_commands'][cwd],*[row['argv'] for row in plan['commands']],plan['transform_loader_command'],plan['postprocess']['argv']]
assert [row['process']['argv'] for row in raw['commands']]==expected
assert len(raw['commands'])==7
for row in raw['commands']:
 p=row['process']
 assert p['exit_code']==0 and p['child_started'] and p['outcome']=='pass' and p['resource_qualification']=='pass'
 assert p['rss_budget_bytes']==512*1024**2
 label={'compiler-loader':'compiler-loader','section-tool-loader':'section-tool-loader','constructor-transform':'constructor-transform'}.get(row['role'])
 if label is None:label='compile-'+str([r['id'] for r in plan['commands']].index(row['role']))
 for stream in ['stdout','stderr']:
  assert pin(OUT/(label+'.'+stream+'.txt'))['sha256']==p[stream+'_sha256']
 assert not p['after']['owned_processes']
native.loader_mapping((OUT/'compiler-loader.stdout.txt').read_text(),plan['runtime'])
native.loader_mapping((OUT/'section-tool-loader.stdout.txt').read_text(),plan['transform_runtime'])
objects=[];all_deps=set()
for row,actual in zip(plan['commands'],raw['objects'],strict=True):
 assert row['id']==actual['id']
 assert pin(row['object'])['sha256']==actual['object_sha256']
 assert pin(row['depfile'])['sha256']==actual['depfile_sha256']
 assert common.macho(row['object'])==actual['object_validation']
 assert c.object_facts(core,row['object'])==actual['inspection']
 deps=common.dependencies(row['depfile'],row['cwd'],row['object'])
 assert row['source'] in deps
 assert {p:plan['inputs'][p] for p in deps}==actual['dependencies']
 assert all(pin(p)['sha256']==actual['dependencies'][p] for p in deps)
 all_deps.update(deps)
 symbols=actual['inspection']['external_symbols']
 objects.append(dict(id=row['id'],object=pin(row['object']),depfile=pin(row['depfile']),source=dict(path=row['source'],sha256=row['source_sha256']),actual_dependency_count=len(deps),definitions={k:v for k,v in symbols.items() if not v['undefined']},imports={k:v for k,v in symbols.items() if v['undefined']}))
t=raw['constructor_transform'];before=Path(t['raw']);after=Path(t['final'])
assert core.verify_constructor_transform(before,after)==['__mod_init_func']==t['changed_sections']
assert pin(before)['sha256']==t['raw_sha256'] and pin(after)['sha256']==t['final_sha256']
assert not Path(plan['postprocess']['rename_only_after_exit0']['source']).exists()
assert c.object_facts(core,before)==raw['objects'][-1]['raw_inspection']
assert raw['objects'][-1]['raw_inspection']['external_symbols']==raw['objects'][-1]['inspection']['external_symbols']
sessions=[supervise.sample(row['process']['owned_session']) for row in raw['commands']]
assert all(not [p for p in s['owned_processes'] if p['state']!='Z'] for s in sessions)
allocation=MAIN/'artifacts/team-coordination/20261106-team/native-tails91/allocation.json'
assert pin(allocation)['sha256']=='faf70f4de4d135af1933c36e5a3a1de5f84e8e469ad6e8a1ca2b55183d2ec9c5'
reservation=allocation.with_suffix('.reservations.json');r=json.loads(reservation.read_text())
assert r['allocation_sha256']==pin(allocation)['sha256'] and r['entries']['STR-021']['status']=='complete'
root=MAIN/'artifacts/team-coordination/20261106-team/native-tails91/evidence.json';rootdata=json.loads(root.read_text())
assert rootdata['outcome']=='pass' and rootdata['released'] and not rootdata['owned_survivors'] and not rootdata['stop_reason']
report=dict(kind='host-test',origin='local-host',outcome='pass',recorded_at=common.stamp(),summary='Read-only validation of actual root91 four-tail object/MD/runtime/transform and cleanup measurement; no target replay.',raw=pin(OUT/'evidence.json'),source_plan=pin(WT/'artifacts/e1s-native-tails/plan-2/source-plan-final.json'),caller=pin(CALLER),validation_source=pin(__file__),input_count_current=len(plan['inputs']),include_namespace_sha256=plan['namespace']['sha256'],objects=objects,dependency_entries=sum(o['actual_dependency_count'] for o in objects),unique_dependencies=len(all_deps),constructor_transform=t,temporary_output_semantics='Tool temporary output was validated before successful rename; actual final bytes revalidated, temporary path now absent, raw pre-transform copy retained.',runtime_loaders='Both actual loader stdout maps match exact accepted runtimes',root_execution=pin(root),allocation=pin(allocation),reservation=pin(reservation),reservation_status='complete',current_sessions=sessions,owned_survivors=[],child_peak_rss_bytes=max(row['process']['peak_total_owned_rss_bytes'] for row in raw['commands']),controller_status=raw['controller_status'],validation_controller_status=core.proc_status(),new_target_children=0,full_native_image=False,native_boot=False,hardware_execution=False)
DEST.mkdir(exist_ok=False)
(DEST/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(evidence=pin(DEST/'evidence.json'),objects=objects,dependency_entries=report['dependency_entries'],unique_dependencies=len(all_deps)),indent=2))
