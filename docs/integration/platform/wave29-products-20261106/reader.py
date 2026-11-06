#!/usr/bin/env python3
"""Independent actual wave product reader. No compiler/helper/process execution."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shlex,subprocess,struct,sys,tempfile,time
from pathlib import Path
R=Path('/home/egor/dev/pet/s24-ios-exynos');HERE=Path(__file__).parent
EXPECTED={'manifest_sha256':'80cc9fe56c584e77f183b7bdfe442cb9aeb66c06d616660474ac0b940f120da4','qualification_sha256':'eb2ca4400478800b4d72f5d231eb73f6d13c2ba41ffb477c28a07f5e6baff5a4','selectors_sha256':'a2379193252975a5dac47dd27a41703ae5497e64f93591612670695e46c58d8e','namespace_sha256':'fdfc50d351c6c175422de7ce2c75f8a14c0228997ef8de921c9cdec3e97b1172'}
ENGINE='9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755';INPUTS='295e6edab63199b6ee1bcd245d43ede66dcb1c1429edc599389bc53f10307406';ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',LC_ALL='C')
CACHE={};OBS={};COUNT=0;NAMES=[];START=0
canonical=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def identity(s):return(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def req(label,ok):
 global COUNT
 COUNT+=1
 if not ok:raise ValueError(label)
 if len(NAMES)<10000:NAMES.append(label)
def sha(p,expected=None):
 p=Path(p);st=identity(p.stat());key=(str(p),st)
 if key not in CACHE:
  with p.open('rb') as f:
   before=identity(os.fstat(f.fileno()));digest=hashlib.file_digest(f,'sha256').hexdigest();req('Stable streamed physical input '+p.name,before==identity(os.fstat(f.fileno()))==identity(p.stat()))
  CACHE[key]=digest
 digest=CACHE[key];req('Exact hash '+p.name,expected is None or digest==expected);OBS[str(p)]=digest;return digest
def data(p,expected=None):
 p=Path(p);req('Bounded regular read '+p.name,p.is_file() and p.stat().st_size<=64*1024**2)
 with p.open('rb') as f:
  before=identity(os.fstat(f.fileno()));raw=f.read();req('Stable snapshot '+p.name,before==identity(os.fstat(f.fileno()))==identity(p.stat()))
 digest=hashlib.sha256(raw).hexdigest();req('Exact read hash '+p.name,expected is None or digest==expected);CACHE[(str(p),before)]=digest;OBS[str(p)]=digest;return raw
def load(p,h=None):return json.loads(data(p,h))
def errors(v):
 bad=[]
 if isinstance(v,dict):
  for k,x in v.items():
   if (k.endswith('_error') or k in ['error','violations','stop_reason']) and x:bad.append((k,x))
   bad.extend(errors(x))
 elif isinstance(v,list):
  for x in v:bad.extend(errors(x))
 return bad
def git(*args):
 p=subprocess.run(['git',*args],cwd=R,env=ENV,capture_output=True,timeout=15);req('Git '+args[0],p.returncode==0);return p.stdout.decode()
def patch(c):
 with tempfile.TemporaryFile() as out:
  argv=['git','show','--format=','--binary','--full-index','--no-ext-diff','--no-textconv','--no-renames',c];p=subprocess.run(argv,cwd=R,env=ENV,stdout=out,stderr=subprocess.PIPE,timeout=15);req('Source patch stream '+c,p.returncode==0);out.seek(0);return hashlib.file_digest(out,'sha256').hexdigest()
def main():
 global START,COUNT,NAMES
 a=argparse.ArgumentParser();a.add_argument('--config',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args();cfg=json.loads(args.config.read_text());O=args.output;O.mkdir(parents=True,exist_ok=False);samples=[]
 report={'kind':'host-test','origin':'local-host','task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATWAVE29-001','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'review_task':cfg['task'],'check_names':NAMES,'observed_input_output_hashes':OBS,'no_compiler_target_linker_QEMU_common_or_queue_mutation':True,'global_wave_release_or_taskclose_performed':False};products=[]
 try:
  for i in range(3):
   v=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;req('Stable4GiB-'+str(i),v>=4*1024**3);samples.append(v)
   if i<2:time.sleep(1)
  START=time.monotonic();W=R/cfg['worktree'];A=R/cfg['raw'];e=load(A,cfg['raw_sha256']);A=A.parent;conventional=load(W/cfg['capsule'],cfg['capsule_sha256'])
  own=e['ownership_binding'];req('Exact original task/owner/shard/output',own['task']==cfg['task'] and own['owner']==cfg['owner'] and e['shard']==cfg['shard'] and own['output']==str(A))
  req('Actual terminal complete resource-qualified fresh records',e['outcome']=='pass' and e['resource_qualification']=='pass' and len(e['objects'])==len(e['commands'])==cfg['count'] and not e.get('resume'))
  req('Honest no kernel/link/runtime/private SDK claims',all(e[k] is False for k in ['full_kernel_build_or_link','guest_executed','device_executed','sdk_qualified','private_apple_abi_qualified']))
  req('Exact actual copied engine',e['executor_sha256']==sha(A/'executor.py',ENGINE))
  plan=load(A/'execution-plan.json');inputs=load(A/'input-bindings.json',INPUTS);prov=plan['provenance'];req('Actual source profile identity',all(prov[k]==v for k,v in EXPECTED.items()) and plan['resource_profile']==e['resource_profile']=='project-budget-v1' and e['provenance']==prov)
  req('Canonical complete recorded namespace receipt',inputs['sha256']==EXPECTED['namespace_sha256']==canonical({k:inputs[k] for k in ['roots','absent_search_roots','files']}))
  rows=load(prov['manifest'],EXPECTED['manifest_sha256']);selectedids=load(prov['selectors'],EXPECTED['selectors_sha256'])['shards'][cfg['shard']];q=load(prov['qualification'],EXPECTED['qualification_sha256']);keymap={k['id']:k for k in load(q['object_input_keys']['path'],q['object_input_keys']['sha256'])['keys']};parent=load(q['namespace_receipt']['path'],q['namespace_receipt']['sha256']);req('Accepted namespace mapping reused without full body scan',inputs==parent)
  manifest={row['id']:row for row in rows};selected=[r for r in rows if r['id'] in set(selectedids)];req('Exact unchanged selected IDs and order',e['selected_ids']==[r['id'] for r in selected]==[r['id'] for r in plan['selected']] and len(selected)==len(set(selectedids))==cfg['count'])
  approval=e['execution_approval'];allocation=load(R/approval['root_lease_path'],approval['root_lease_sha256']);slot=next(s for s in allocation['slots'] if s['task']==cfg['task']);source=load(R/slot['source_plan'],slot['source_plan_sha256']);req('Exact root source-plan/profile authority',source['provenance']==prov and source['shard']==plan['shard']==cfg['shard'] and source['resource_profile']=='project-budget-v1' and slot['source_plan_sha256']==approval['source_plan_sha256'] and slot['owner']==cfg['owner'] and slot['reviewed_executor_sha256']==ENGINE and slot['max_jobs']==1 and slot['max_owned_rss_bytes']==512*1024**2)
  sha(prov['compiler']['path'],prov['compiler']['sha256']);req('Exact canonical compiler',prov['compiler']['sha256']=='7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82')
  spec=importlib.util.spec_from_file_location('cn_independent_macho',HERE.parent/'component-integration-20261106/inspect-actual.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  def bounded_parser_req(ok,label):req('Mach-O '+label,ok)
  m.req=bounded_parser_req;alldeps=set();peak=0;metadata_count=0;nonempty_stderr=0
  for n,(row,entry,command,sourcerow) in enumerate(zip(plan['selected'],e['objects'],e['commands'],source['selected'])):
   req('Finite reader deadline',time.monotonic()-START<120)
   rid=row['id'];g=manifest[rid];key=keymap[rid];rec=load(entry['record'],entry['record_sha256']);req('Actual row/record/source-plan key '+rid,entry['outcome']==rec['outcome']=='pass' and rec['id']==rid and row['input_key']==rec['input_key']==sourcerow['input_key']==key['input_key']==canonical(key['binding']))
   template=g['next_owned_compile_argv_template'];recipe=canonical(template);req('Genuine selected recipe/config/source '+rid,row['recipe_sha256']==sourcerow['recipe_sha256']==recipe==key['binding']['argv_template_sha256'] and row['source']==rec['source']==g['bound_source'] and row['source_sha256']==rec['source_sha256']==g['bound_source_sha256'] and row['configuration']==g['configuration'] and row['configuration_sha256']==g['configuration_sha256'] and row['cwd']==rec['cwd']==g['cwd'])
   expected=[x.replace('@NEXT_OBJECT_DIR@',str(A/'objects')).replace('@NEXT_DEPENDENCY_DIR@',str(A/'dependencies')) for x in template];req('Exact output-only expansion and actual command '+rid,row['argv']==command['argv']==rec['command']['argv']==expected and command==rec['command'] and command['cwd']==row['cwd'])
   sourceexpected=[x.replace('@NEXT_OBJECT_DIR@',str((R/slot['source_plan']).parent/'objects')).replace('@NEXT_DEPENDENCY_DIR@',str((R/slot['source_plan']).parent/'dependencies')) for x in template];req('Exact frozen source-plan argv '+rid,sourcerow['argv']==sourceexpected)
   sha(row['source'],row['source_sha256']);sha(row['configuration'],row['configuration_sha256'])
   req('Actual child resource and owned cleanup '+rid,command['exit_code']==0 and command['outcome']==command['execution_outcome']==command['resource_qualification']=='pass' and command['child_started'] is True and command['after']['owned_processes']==[] and command['after']['owned_tree_rss_bytes']==0 and not errors(command) and command['rss_budget_bytes']==512*1024**2 and command['peak_total_owned_rss_bytes']<=512*1024**2 and command['peak_project_rss_bytes']<=6*1024**3)
   peak=max(peak,command['peak_total_owned_rss_bytes']);label=rid.replace('/','_');sha(A/(label+'.stdout.txt'),command['stdout_sha256']);sha(A/(label+'.stderr.txt'),command['stderr_sha256']);nonempty_stderr+=bool((A/(label+'.stderr.txt')).stat().st_size)
   raw=data(rec['object'],rec['object_sha256']);obj=m.obj(raw);req('Physical object output rooted exact owner '+rid,Path(rec['object'])==A/'objects'/rid and rec['object_validation']['sha256']==rec['object_sha256'] and rec['object_validation']['arm64_macho_object'] is True)
   alloc=[]
   for s in obj['sections']:
    if s['name'].startswith('__kalloc'):
     req('Actual allocator extent '+rid,s['offset']+s['size']<=len(raw));alloc.append({'segment':s['segment'],'section':s['name'],'size':s['size'],'sha256':hashlib.sha256(raw[s['offset']:s['offset']+s['size']]).hexdigest()})
   req('Actual allocator section bytes '+rid,alloc==rec['object_validation']['allocator_metadata_sections']);metadata_count+=bool(alloc)
   dep=data(rec['dependency_file'],rec['dependency_file_sha256']).decode();line=re.sub(r'\\\r?\n','',dep).splitlines()[0];lhs,rhs=line.split(':',1);req('Actual MD target '+rid,shlex.split(lhs)==[rec['object']]);names={str((Path(row['cwd'])/x).resolve()) for x in shlex.split(rhs)}
   req('Independent actual MD source/header list '+rid,names==set(rec['dependencies']) and rec['source'] in names)
   for f,digest in rec['dependencies'].items():req('Selected actual input index '+Path(f).name,inputs['files'].get(f)==digest);sha(f,digest);alldeps.add(f)
   products.append({'id':rid,'input_key':row['input_key'],'object_sha256':rec['object_sha256'],'record_sha256':entry['record_sha256'],'actual_dependency_count':len(names),'strong_definitions':obj['strong'],'imports_retained':obj['imports'],'allocator_sections':alloc})
   rss=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024;req('Reader RSS256MiB',rss<=256*1024**2)
  req('Source owner frozen final commit',git('-C',str(W),'rev-parse','HEAD').strip()==cfg['head'] and git('-C',str(W),'status','--porcelain=v1','--untracked-files=no')=='')
  commits=git('rev-list','--reverse',cfg['base']+'..'+cfg['head']).splitlines();req('Exact scoped source ancestry',commits==cfg['commits']);patchmap=[]
  for c in commits:
   paths=git('diff-tree','--no-commit-id','--name-only','-r',c).splitlines();req('Literal producer scope '+c,bool(paths) and all(any(x==s or x.startswith(s+'/') for s in cfg['scopes']) for x in paths));patchmap.append({'source':c,'paths':paths,'patch_sha256':patch(c)})
  report.update(outcome='pass',actual_object_count=len(products),unique_actual_MD_inputs=len(alldeps),actual_peak_owned_rss_bytes=peak,actual_controller_memory=e['controller_memory'],inherited_rusage_not_fresh_footprint=True,actual_metadata_object_count=metadata_count,nonempty_stderr_files=nonempty_stderr,source_patch_map=patchmap,producer_head=cfg['head'],original_owner=cfg['owner'],raw_evidence_sha256=cfg['raw_sha256'],conventional_evidence_sha256=cfg['capsule_sha256'],full_kernel_link_provider_private_ABI_runtime_qualified=False,global_wave_release_not_inferred=True)
 except BaseException as error:report.update(outcome='fail',error=repr(error));raise
 finally:
  report.update(check_count=COUNT,admission_MemAvailable_bytes=samples,elapsed_seconds=time.monotonic()-START if START else None,proc_status=[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))],source_sha256=sha(__file__))
  (O/'objects.json').write_text(json.dumps(products,indent=2)+'\n');report['object_summary_sha256']=sha(O/'objects.json');(O/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'task':cfg['task'],'outcome':report.get('outcome'),'error':report.get('error'),'objects':len(products),'checks':COUNT,'memory':report['proc_status'],'evidence':str(O/'evidence.json'),'sha256':sha(O/'evidence.json')}))
if __name__=='__main__':main()
