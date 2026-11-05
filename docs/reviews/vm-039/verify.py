#!/usr/bin/env python3
"""Independent bounded profile/transition/guard and existing-plan byte controls."""
import ast,copy,hashlib,importlib.util,itertools,json,os,resource,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');WT=MAIN/'worktrees/vm-039-ej-20261106'
TOOL=WT/'tools/build/avf_kernel_objects.py';PARENT=HERE.parents[2]/'tools/build/avf_kernel_objects.py'
START=time.monotonic();r={'kind':'host-test','origin':'local-host','outcome':'fail','argv':[sys.executable,*sys.argv],'controls':[],'bindings':{},'compiler_export_guest_common_started':False,'actual_new_profile_objects':0}
def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def bound(path,expected):
 actual=sha(path);r['bindings'][str(path)]=actual
 if actual!=expected:raise ValueError('Changed frozen bytes: '+str(path))
def check(name,value,**details):
 r['controls'].append({'name':name,'pass':bool(value),**details})
 if not value:raise AssertionError(name)
 if time.monotonic()-START>180:raise TimeoutError('180-second bound')
 hwm=next(int(s.split()[1])*1024 for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:'))
 if hwm>256*1024**2:raise MemoryError('Reviewer current-image VmHWM exceeds256MiB')
def rejects(name,callback):
 try:callback()
 except (ValueError,KeyError,TypeError,OSError) as error:check(name,True,rejection=repr(error))
 else:check(name,False)
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
try:
 bound(TOOL,'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0');bound(PARENT,'efe908ff5b6321ea1e456306a3094f9188cc501d066bcc78b435b500d56783e6')
 e=module('profile_review',TOOL);old=module('profile_accepted_parent',PARENT)
 oldtree=ast.parse(PARENT.read_text());newtree=ast.parse(TOOL.read_text())
 for name in ['ProjectBudget','project_approval','approval','run_child','stable_memory','load_project','process_table','owned_processes','landlock','namespace','expand','reusable','validate_graph','owned_out','canonical_output_path','normalized_index','Digests','dependencies','macho']:
  select=lambda tree:next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
  check('accepted parent AST unchanged '+name,ast.dump(select(oldtree))==ast.dump(select(newtree)))
 for name in ['PIN','TREE','CONFIG','COMPILER','GIB','GUARDS','SHARDS','PROJECT_PROFILE','RESOURCE_QUEUE','EXECUTOR_RSS']:
  check('accepted global guard constant unchanged '+name,getattr(e,name)==getattr(old,name))
 oldtuple=(e.PIN,e.LEGACY_QUALIFICATION,e.LEGACY_SELECTORS);newtuple=(e.FIREHOSE_MANIFEST,e.FIREHOSE_QUALIFICATION,e.FIREHOSE_SELECTORS)
 def args(identity):return SimpleNamespace(manifest_sha256=identity[0],qualification_sha256=identity[1],selectors_sha256=identity[2])
 for bits in itertools.product([0,1],repeat=3):
  value=tuple((newtuple if bit else oldtuple)[i] for i,bit in enumerate(bits))
  if len(set(bits))==1:check('exact accepted profile '+str(bits),e.accepted_profile(args(value))['manifest_sha256']==value[0])
  else:rejects('mixed tuple rejects '+str(bits),lambda v=value:e.accepted_profile(args(v)))
 for i in range(3):
  value=list(newtuple);value[i]='f'*64;rejects('arbitrary tuple override rejects field'+str(i),lambda v=value:e.accepted_profile(args(v)))
 task={'id':'VM-039','paths':['tools/build/avf_kernel_objects.py','fixtures/public/avf-guest-profile','docs/procedures/avf-guest-profile']}
 check('literal VM039 plan-only exception',e.task_shards(task,'plan','security')['source_only_tooling_exception'] is True)
 rejects('VM039 never gains execute authority',lambda:e.task_shards(task,'execute','security'))
 rejects('VM039 incomplete literal scope rejects',lambda:e.task_shards(dict(task,paths=task['paths'][:-1]),'plan','security'))
 rejects('VM039 extra shard paths still reject execute',lambda:e.task_shards(dict(task,paths=task['paths']+['fixtures/public/avf-object-shards/security','docs/procedures/avf-object-shards/security']),'execute','security'))
 for name in e.SHARDS:
  caller={'id':'SYNTHETIC-SHARD','paths':['fixtures/public/avf-object-shards/'+name,'docs/procedures/avf-object-shards/'+name]}
  check('original shard authority unchanged '+name,e.task_shards(caller,'execute',name)==old.task_shards(caller,'execute',name))
 base=MAIN/'worktrees/vm-038-20261106/docs/procedures/avf-firehose-namespace/qualification-session1'
 descriptor_path=base/'qualified-component.json';bound(descriptor_path,e.FIREHOSE_QUALIFICATION);descriptor=json.loads(descriptor_path.read_text())
 newpath=base/'next-full-object-manifest.json';bound(newpath,e.FIREHOSE_MANIFEST);newrows=json.loads(newpath.read_text())
 a=args(newtuple);a.main=MAIN;a.manifest=newpath;a.selectors=base/'object-shards.json'
 qualified,keymap,receipt=e.firehose_profile(a,newrows,descriptor)
 check('actual pinned full transition/export/context/key proof admits',len(keymap)==1080 and receipt['sha256']==e.FIREHOSE_NAMESPACE and qualified['artifact_index_sha256']==descriptor['artifact_index']['sha256'])
 oldpath=Path(descriptor['parents']['parent_manifest']['path']);bound(oldpath,e.PIN);oldrows=json.loads(oldpath.read_text());rules=e.profile_rules(MAIN)
 check('complete IDs and55 generated preserved',[x['id'] for x in oldrows]==[x['id'] for x in newrows] and sum(x['generated_input'] is True for x in newrows)==55)
 oldroot=Path(descriptor['old_root']['path']);newroot=Path(descriptor['new_root']['path'])
 for field in ['bound_source_sha256','configuration_sha256','generated_input','cwd']:
  changed=newrows.copy();changed[0]=copy.deepcopy(newrows[0]);changed[0][field]=not changed[0][field] if field=='generated_input' else 'changed'
  rejects('actual transition rejects changed '+field,lambda c=changed:rules.validate_transition(oldrows,c,oldroot,newroot))
 for label,change in [('extra flag',lambda row:row['next_owned_compile_argv_template'].append('-DXNU_NO_TYPE_BUILTINS=1')),('missing substitution',lambda row:row.update(next_owned_compile_argv_template=oldrows[0]['next_owned_compile_argv_template']))]:
  changed=newrows.copy();changed[0]=copy.deepcopy(newrows[0]);change(changed[0]);rejects('actual transition rejects '+label,lambda c=changed:rules.validate_transition(oldrows,c,oldroot,newroot))
 changed=newrows.copy();changed[0],changed[1]=changed[1],changed[0];rejects('actual transition rejects reordered IDs',lambda:rules.validate_transition(oldrows,changed,oldroot,newroot))
 changed=newrows.copy();changed[0]=copy.deepcopy(newrows[0]);v=changed[0]['next_owned_compile_argv_template'];index=next(i for i,arg in enumerate(v) if str(newroot) in arg);v[index],v[index+1]=v[index+1],v[index]
 rejects('same root at another argv position rejects',lambda:rules.validate_transition(oldrows,changed,oldroot,newroot))
 frozenkeys=json.loads((base/'object-input-keys.json').read_text())['keys'];manual=[]
 canonical=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 for before,after in zip(oldrows,newrows):
  checkfields={k:v for k,v in before.items() if k!='next_owned_compile_argv_template'}
  if checkfields!={k:v for k,v in after.items() if k!='next_owned_compile_argv_template'}:raise AssertionError('Non-template row changed')
  data={'schema':e.FIREHOSE_SCHEMA,'id':after['id'],'manifest_sha256':e.FIREHOSE_MANIFEST,'namespace_sha256':e.FIREHOSE_NAMESPACE,'source':after['bound_source'],'source_sha256':after['bound_source_sha256'],'configuration':after['configuration'],'configuration_sha256':after['configuration_sha256'],'compiler':after['next_owned_compile_argv_template'][0],'cwd':after['cwd'],'argv_template_sha256':canonical(after['next_owned_compile_argv_template'])}
  manual.append({'id':after['id'],'input_key':canonical(data),'binding':data})
 check('independent full1080 new-key formula matches frozen51af',manual==frozenkeys)
 output=WT/'artifacts/avf-guest-profile/frozen-001';legacy_plan=json.loads((output/'legacy-plan/execution-plan.json').read_text());new_plan=json.loads((output/'firehose-plan/execution-plan.json').read_text())
 prior=MAIN/'worktrees/vm-009-20261106/artifacts/avf-kernel-objects/controls-session2/real-plan'
 check('complete actual old-plan bytes unchanged except output prefix',(output/'legacy-plan/execution-plan.json').read_bytes()==(prior/'execution-plan.json').read_bytes().replace(str(prior).encode(),str(output/'legacy-plan').encode()))
 check('complete actual old input-binding bytes unchanged',(output/'legacy-plan/input-bindings.json').read_bytes()==(prior/'input-bindings.json').read_bytes())
 check('new actual security23 plan has exact frozen keys',len(new_plan['selected'])==23 and all(row['input_key']==keymap[row['id']]['input_key'] for row in new_plan['selected']))
 check('actual selected new keys differ from genuine legacy',all(x['id']==y['id'] and x['input_key']!=y['input_key'] for x,y in zip(legacy_plan['selected'],new_plan['selected'])))
 e.resume_profile({'provenance':new_plan['provenance']},new_plan);check('same new profile identity can resume structurally',True)
 rejects('legacy capsule cannot resume new namespace',lambda:e.resume_profile({'provenance':legacy_plan['provenance']},new_plan))
 rejects('new capsule cannot resume legacy namespace',lambda:e.resume_profile({'provenance':new_plan['provenance']},legacy_plan))
 rejects('missing namespace provenance cannot resume',lambda:e.resume_profile({'provenance':{'manifest_sha256':e.FIREHOSE_MANIFEST}},new_plan))
 negative=dict(legacy_plan['selected'][0],outcome='pass');rejects('real old plan key rejects before any object credit',lambda:e.reusable(negative,new_plan['selected'][0],{},e.Digests()))
 with tempfile.TemporaryDirectory(prefix='profile-negative-',dir=HERE) as directory:
  root=Path(directory);installed=root/'kernel';(installed/'os').mkdir(parents=True);header=installed/'os/firehose_buffer_private.h';original=(newroot/'os/firehose_buffer_private.h').read_bytes();digest=hashlib.sha256(original).hexdigest();header.write_bytes(original)
  rules.verify_overlay(installed,digest);check('own exact real-header overlay admits structurally',True)
  header.write_bytes(original+b'\nchanged');rejects('actual changed header bytes reject',lambda:rules.verify_overlay(installed,digest));header.unlink()
  rejects('missing new header rejects',lambda:rules.verify_overlay(installed,digest));header.symlink_to(newroot/'os/firehose_buffer_private.h');rejects('new header symlink rejects',lambda:rules.verify_overlay(installed,digest));header.unlink();header.write_bytes(original)
  alias=root/'alias';alias.symlink_to(installed,target_is_directory=True);rejects('new root symlink rejects',lambda:rules.verify_overlay(alias,digest))
  (installed/'shadow.h').write_text('own negative');rejects('extra shadow file rejects',lambda:rules.verify_overlay(installed,digest));(installed/'shadow.h').unlink()
  changedfile=root/'changed-descriptor.json';changedfile.write_text(json.dumps(dict(descriptor,namespace_digest=e.LEGACY_NAMESPACE)))
  rejects('real changed descriptor cannot retain accepted hash',lambda:e.load_project(changedfile,e.FIREHOSE_QUALIFICATION))
  rejects('source/context bytes cannot masquerade under old hash',lambda:e.bound_profile_file({'path':str(changedfile),'sha256':e.FIREHOSE_QUALIFICATION}))
  fake=copy.deepcopy(newrows[0]);fake.update(cwd=str(installed),bound_source=str(header),next_owned_compile_argv_template=['-I',str(installed),'-c',str(header)])
  e.namespace([fake],{str(header):digest},e.Digests());check('synthetic tiny namespace positive, no compile authority',True)
  (installed/'unbound.h').write_text('own negative');rejects('new unbound namespace addition rejects',lambda:e.namespace([fake],{str(header):digest},e.Digests()))
 rejects('conflicting main-relative/absolute index aliases reject',lambda:e.normalized_index({'x':'0'*64,str(MAIN/'x'):'1'*64},MAIN))
 check('retired old root still physically absent',not os.path.lexists(oldroot))
 r.update(outcome='pass',manual_key_rows=1080,actual_new_profile_objects=0,full_parent_namespace_scan_repeated=False)
except Exception as error:r['error']=repr(error)
finally:
 usage={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:','VmRSS:'))};r.update(elapsed_seconds=round(time.monotonic()-START,3),current_image_peak_rss_bytes=usage['VmHWM'],current_rss_bytes=usage['VmRSS'],raw_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
 (HERE/'verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ('controls','bindings')}|{'control_count':len(r['controls'])}))
sys.exit(0 if r['outcome']=='pass' else 1)
