#!/usr/bin/env python3
"""Focused corrective trust-path/snapshot controls and immutable recipe equality."""
import ast,copy,importlib.util,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
s=importlib.util.spec_from_file_location('review_fixtures_ext',HERE/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
s=importlib.util.spec_from_file_location('corrected_extended',MAIN/'worktrees/vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=Path(e.__file__)
started=time.monotonic();r={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(e.__file__),'argv':[sys.executable,*sys.argv],'controls':[],'compiler_guest_common_started':False}
def check(name,condition,**details):
 r['controls'].append({'name':name,'pass':bool(condition),**details})
 if not condition:raise AssertionError(name)
def rejected(name,call):
 try:call()
 except (ValueError,OSError,KeyError,TypeError) as error:check(name,True,rejection=repr(error))
 else:check(name,False)
def loadmod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
try:
 check('exact corrected helper freeze',r['helper_sha256']=='6caa0872750874937c1343b26a168c0d016fa4c98677f54303546e7d194f915a')
 for label in ['state_path','lock_path','temporary']:
  p=f.Project();path=p.b.state_path.with_suffix('.tmp') if label=='temporary' else getattr(p.b,label)
  existed=path.exists();saved=path.with_name(path.name+'.original');saved.write_bytes(path.read_bytes() if existed else b'untouched sentinel')
  if existed:path.unlink()
  path.symlink_to(saved.name)
  try:rejected('live canonical '+label+' symlink rejected',p.b.sample)
  finally:
   path.unlink()
   if existed:saved.rename(path)
   else:saved.unlink()
   p.close()
 p=f.Project()
 try:
  before=p.queue.read_bytes();d=json.loads(before);d['heavy']['allocation_sha256']='0'*64;p.queue.write_text(json.dumps(d))
  rejected('live queue revocation rejects admission',p.b.sample);p.queue.write_bytes(before)
  d=json.loads(before);d['heavy']['slots'][0]['owner']='changed';p.queue.write_text(json.dumps(d))
  rejected('live queue copied-slot mismatch rejects',p.b.sample);p.queue.write_bytes(before)
  first=p.b.sample();check('controller PID RSS deduplicated',sum(row['pid']==os.getpid() for row in first['project_processes'])==1)
  check('process VmSwap and host swap counters separate',all(type(first[k]) is int for k in ['project_swap_bytes','pswpin','pswpout']) and all(type(row['swap_bytes']) is int for row in first['project_processes']))
  real=Path.read_text
  def unreadable(path,*a,**kw):
   if path==Path('/proc')/str(os.getpid())/'status':raise PermissionError('controlled known-owned status read error')
   return real(path,*a,**kw)
  with patch.object(Path,'read_text',unreadable):rejected('known-owned status read error fails closed',p.b.sample)
 finally:p.close()
 with tempfile.TemporaryDirectory(prefix='snapshot-',dir=HERE) as directory:
  root=Path(directory);plan=root/'plan.json';replacement=root/'replacement.json';original={'resource_profile':e.PROJECT_PROFILE,'identity':'approved'};changed={'resource_profile':e.PROJECT_PROFILE,'identity':'replacement'}
  plan.write_text(json.dumps(original));replacement.write_text(json.dumps(changed));expected=e.sha(plan);real_open=os.open
  def opened_snapshot(path,*a,**kw):
   descriptor=real_open(path,*a,**kw)
   if Path(path)==plan:os.replace(replacement,plan)
   return descriptor
  with patch.object(e.os,'open',side_effect=opened_snapshot):body=e.load_project(plan,expected)
  check('actual atomic rename after FD open keeps approved snapshot',body==original,expected_sha256=expected,parsed_body=body)
  rejected('replacement bytes fail the old approved snapshot hash',lambda:e.load_project(plan,expected))
 legacy_path=MAIN/'tools/build/avf_kernel_objects.py';legacy_sha=e.sha(legacy_path)
 check('original physical accepted5c witness unchanged',legacy_sha=='5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8',legacy_sha256=legacy_sha)
 old=loadmod('immutable_legacy',legacy_path);old_tree=ast.parse(legacy_path.read_text());new_tree=ast.parse(Path(e.__file__).read_text())
 names=['expand','canonical','select','validate_graph','reusable','namespace','landlock','owned_out','task_shards','load']
 for name in names:
  first=next(x for x in old_tree.body if isinstance(x,ast.FunctionDef) and x.name==name);second=next(x for x in new_tree.body if isinstance(x,ast.FunctionDef) and x.name==name)
  check('legacy AST unchanged '+name,ast.dump(first)==ast.dump(second))
 def expr(tree,variable):
  function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='bind')
  return next(x for x in ast.walk(function) if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id==variable for t in x.targets))
 for variable in ['provenance','recipe','identity']:
  check('complete legacy key operand AST unchanged '+variable,ast.dump(expr(old_tree,variable))==ast.dump(expr(new_tree,variable)))
 manifest=MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json';check('exact immutable1080 graph pin',e.sha(manifest)==e.PIN)
 rows=json.loads(manifest.read_text());check('genuine1080 graph IDs match',len(rows)==1080 and e.validate_graph(rows)==old.validate_graph(rows))
 output=HERE/'synthetic-never-executed'
 check('all1080 recipe expansion and digest bytes identical',all(e.expand(row,output)==old.expand(row,output) and e.canonical(row['next_owned_compile_argv_template'])==old.canonical(row['next_owned_compile_argv_template']) for row in rows))
 r.update(outcome='pass',legacy_sha256=legacy_sha,recipe_rows=1080)
except Exception as error:r['error']=repr(error)
finally:
 r.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory());(HERE/'extended-controls.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='controls'}|{'control_count':len(r['controls'])}))
sys.exit(0 if r['outcome']=='pass' else 1)
