#!/usr/bin/env python3
"""Independent actual four-tail object/transform/dependency intake, no tools."""
import datetime,hashlib,importlib.util,json,os,resource,shlex,struct,sys,time
from pathlib import Path
D=Path(__file__).parent;O=D/'runs/actual2';O.mkdir(parents=True,exist_ok=False)
R=Path('/home/egor/dev/pet/s24-ios-exynos');T=R/'worktrees/vm-022-tail-cancellation-20261106';A=T/'artifacts/avf-guest-link-inputs/tails-execute-1'
spec=importlib.util.spec_from_file_location('prior_independent_raw_reader',D.parent/'component-integration-20261106/inspect-actual.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
checks=p.CHECKS;req=p.req;sha=p.sha;data=p.data
canonical=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
samples=[]
for n in range(3):
 value=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;req(value>=4*1024**3,'stable4GiB-'+str(n));samples.append(value)
 if n<2:time.sleep(1)
start=time.monotonic();report={'kind':'host-test','origin':'local-host','task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATTAIL-001','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'artifacts':p.HASHES,'compiler_loader_archive_linker_generator_guest_or_queue_mutation':False}
try:
 e=json.loads(data(A/'evidence.json','3abed3cb6de1cbe0c9e493340ef9b8af4fa00330d89254b5bb3dadfb87f4a0f1'));plan=json.loads(data(A/'execution-plan.json'));inputs=json.loads(data(A/'input-bindings.json'))
 req(e['outcome']=='pass' and len(e['commands'])==5 and len(e['objects'])==4,'Actual four compiles and one real transform PASS')
 req(e['executor_sha256']==plan['executor_sha256']==sha(T/'tools/build/avf_guest_link_inputs.py')=='99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060','Exact reviewed actual tail caller and builder snapshot')
 req(sha(A/'builder.py')==e['executor_sha256'],'Actual builder captured exact source')
 req(e['source_plan_sha256']==sha(A/'execution-plan.json')=='6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569','Exact actual source plan file binding')
 req(e['recipe_namespace_sha256']==inputs['sha256']==canonical({k:inputs[k] for k in ['roots','absent_search_roots','files']}),'Actual complete selected namespace canonical digest')
 parent=json.loads(data(plan['namespace_receipt']['path'],plan['namespace_receipt']['sha256']))
 req(e['accepted_parent_namespace_sha256']==parent['sha256']==plan['namespace_digest']=='25f22291e314445a01a4030e7db74f8cebd9a935b604eefc7b1ad9f5ee033461','Actual accepted VM038 parent namespace identity')
 # Existing complete parent hashes reused: compare recorded mappings, not bodies.
 req(all(parent['files'].get(k)==v for k,v in inputs['files'].items() if k in parent['files']),'All actual selected inherited namespace member identities retained')
 extra={k:v for k,v in inputs['files'].items() if k not in parent['files']}
 req(extra=={str(A/'source-context/version.c'):plan['fresh_version_source']['sha256']},'Only fresh version source added to recorded namespace')
 for name,digest in plan['input_bindings'].items():req(sha(name)==digest,'Exact source/tool/proof input '+Path(name).name)
 req(plan['common_executor_sha256']==sha(R/'tools/build/avf_kernel_objects.py')=='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0','Current real shared process boundary remains exact AF193')
 req(data(A/'source-context/version.c')==data(plan['fresh_version_source']['path'],plan['fresh_version_source']['sha256']),'Actual version source exact qualified fresh generated text')
 warnings=[];parsed={};deps=set();peak=0
 def errors(value):
  result=[]
  if isinstance(value,dict):
   for k,v in value.items():
    if ('error' in k or k in ['violations','stop_reason']) and v:result.append((k,v))
    result+=errors(v)
  elif isinstance(value,list):
   for v in value:result+=errors(v)
  return result
 for n,r in enumerate(e['commands']):
  req(r['exit_code']==0 and r['outcome']=='pass' and r['child_started'] is True,'Actual child success '+str(n))
  req(r['after']['owned_processes']==[] and r['after']['owned_tree_rss_bytes']==0 and not errors(r),'Actual resource reports and owned cleanup clean '+str(n))
  req(r['rss_budget_bytes']==256*1024**2 and r['admission']['admitted'] is True,'Exact admitted256MiB command '+str(n))
  peak=max(peak,r['peak_total_owned_rss_bytes'])
  label=str(n)+'-'+(plan['commands'][n]['target'] if n<4 else 'constructor-segment')
  output=data(A/'commands'/(label+'.stdout.txt'),r['stdout_sha256']);stderr=data(A/'commands'/(label+'.stderr.txt'),r['stderr_sha256'])
  if stderr.strip():warnings.append({'command':n,'bytes':len(stderr),'sha256':hashlib.sha256(stderr).hexdigest(),'text':stderr.decode(errors='replace')})
  if n==4:
   req(r['argv']==plan['constructor_transform']['argv'] and r['cwd']==str(A/'source-context'),'Actual genuine transform argv and cwd');continue
  c=plan['commands'][n];name=c['target'];meta=e['objects'][name];obj=data(meta['object'],meta['sha256']);parsed[name]=p.obj(obj)
  req(r['argv']==c['argv'] and r['cwd']==c['cwd'] and r['timeout_seconds']==120,'Exact genuine selected compiler argv and cwd '+name)
  req(meta['source']==c['source'] and sha(meta['source'])==meta['source_sha256']==c['source_sha256'],'Actual source hash '+name)
  dep=data(meta['dependency_file'],meta['dependency_file_sha256']).decode().replace('\\\n','').splitlines()[0];lhs,rhs=dep.split(':',1)
  req(shlex.split(lhs)==[meta['object']],'Actual MD target '+name)
  names={str((Path(c['cwd'])/x).resolve()) for x in shlex.split(rhs)}
  req(names==set(meta['dependencies']) and c['source'] in names,'Independent actual MD source/header set '+name)
  for f,digest in meta['dependencies'].items():req((inputs['files'].get(f) if f in inputs['files'] else parent['files'].get(f))==digest==sha(f),'Actual selected qualified MD input '+Path(f).name);deps.add(f)
 raw=data(A/'raw/lastkernelconstructor.o',e['constructor_before_transform']);actual=data(A/'objects/lastkernelconstructor.o',e['objects']['lastkernelconstructor.o']['sha256'])
 expected=bytearray(raw);ncmd,size=struct.unpack_from('<II',raw,16);at=32;changed=[];diff=[]
 for _ in range(ncmd):
  cmd,length=struct.unpack_from('<II',raw,at);req(length>=8 and at+length<=32+size,'Bounded raw constructor command')
  if cmd==25:
   nsects=struct.unpack_from('<I',raw,at+64)[0];req(72+nsects*80<=length,'Bounded raw constructor sections')
   for n in range(nsects):
    q=at+72+n*80;section=raw[q:q+16].rstrip(b'\0').decode();segment=raw[q+16:q+32].rstrip(b'\0').decode();flags=struct.unpack_from('<I',raw,q+64)[0]
    if segment=='__DATA' and not flags&0x02000000:
     expected[q+16:q+32]=b'__LASTDATA_CONST'.ljust(16,b'\0');changed.append(section);diff.append([q+16,q+32])
  at+=length
 req(at==32+size and '__mod_init_func' in changed and changed==e['constructor_renamed_sections'] and bytes(expected)==actual,'Full raw/final byte equivalence except exact eligible section segment names')
 original=p.obj(raw);req(original['symbols']==parsed['lastkernelconstructor.o']['symbols'],'Raw/final constructor symbols values bindings and imports identical')
 req(not Path(plan['constructor_transform']['temporary']).exists(),'Temporary transform consumed into exact final path')
 req(e['budget_release'] is None and not e.get('budget_release_error'),'Normal shared reservation release returned without error; root independently verifies state')
 req(all(e[k] is False for k in ['archive_executed','link_executed','guest_executed']) and all(plan[k] is False for k in ['target_production_executed','archive_executed','link_executed','runtime_executed','private_apple_abi_qualified']),'No archive/link/runtime or private ABI credit')
 report['outcome']='pass';report['summary']={'objects':{k:{'sha256':e['objects'][k]['sha256'],'strong_definitions':v['strong'],'imports_retained':v['imports'],'sections':v['sections']} for k,v in parsed.items()},'constructor_raw_sha256':e['constructor_before_transform'],'constructor_changed_sections':changed,'constructor_allowed_byte_ranges':diff,'unique_actual_MD_dependencies':len(deps),'recorded_parent_namespace_files_reused':len(parent['files']),'selected_actual_namespace_files':len(inputs['files']),'parent_members_outside_selected_four_recipe_namespace':len(set(parent['files'])-set(inputs['files'])),'actual_peak_owned_rss_bytes':peak,'controller_current_image_HWM':e['final_process'],'inherited_raw_ru_maxrss_excluded':True,'stderr_retained':warnings,'full_kernel_link_runtime_native_and_VM022_completion':False}
except BaseException as error:report['outcome']='fail';report['error']=repr(error);raise
finally:
 report['check_count']=len(checks);report['admission_MemAvailable_bytes']=samples;report['elapsed_seconds']=time.monotonic()-start;report['proc_status']=[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))];report['review_source_sha256']=sha(__file__);report['argv']=sys.argv
 (O/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'outcome':report['outcome'],'checks':len(checks),'error':report.get('error'),'evidence':str(O/'evidence.json'),'memory':report['proc_status']}))
