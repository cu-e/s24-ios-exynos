#!/usr/bin/env python3
"""Bounded source-qualified native XTS provider/caller integration; no full link."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,struct,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[2]
OWNER='codex-team-kernel-xts-20261105-br'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
XNU='c54f35ca767986246321eb901baf8f5ff7923f6a';DONOR='c8860decc62c6d6180e609036d027a2997972420'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,r):Path(p).write_text(json.dumps(r,indent=2)+'\n')
def memory_available():return int(re.search(r'MemAvailable:\s*(\d+)',Path('/proc/meminfo').read_text())[1])*1024

def admit_memory(report,label):
 """Coordinator-approved stable launch admission; never lowers4GiB floor."""
 floor=4*1024**3;remaining=max(0,180-report.get('admission_total_wait_seconds',0));budget=min(45,remaining,max(0,report.get('_whole_deadline',float('inf'))-time.monotonic()));start=time.monotonic();deadline=start+budget;consecutive=0
 record={'command':label,'required_bytes':floor,'required_consecutive_samples':3,'sample_interval_seconds':1,'max_wait_seconds':budget,'samples':[],'child_started_below_floor':False,'admitted':False}
 report.setdefault('admission_waits',[]).append(record)
 while True:
  available=memory_available();consecutive=consecutive+1 if available>=floor else 0
  record['samples'].append({'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'available_bytes':available,'consecutive':consecutive})
  if consecutive>=3:
   final=memory_available();record['launch_available_bytes']=final
   if final>=floor:
    record['admitted']=True;break
   consecutive=0
  if time.monotonic()>=deadline:break
  time.sleep(min(1,max(0,deadline-time.monotonic())))
 record['actual_wait_seconds']=time.monotonic()-start;report['admission_total_wait_seconds']=report.get('admission_total_wait_seconds',0)+record['actual_wait_seconds']
 if not record['admitted']:
  report['resource_deferred']=True;raise ValueError('resource-deferred stable4GiB admission '+label)

def image_proof(path,require_table=True):
 data=path.read_bytes();at=32;symbols=None;segments=[]
 for _ in range(struct.unpack_from('<I',data,16)[0]):
  cmd,n=struct.unpack_from('<II',data,at)
  if cmd==0x19:
   name,va,vm,off,size=struct.unpack_from('<16s4Q',data,at+8);segments.append((va,vm,off,size))
  if cmd==2:symbols=struct.unpack_from('<4I',data,at+8)
  at+=n
 off,count,strings,size=symbols;names={}
 for i in range(count):
  name,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,off+16*i)
  if kind&0x0e!=0x0e:continue
  end=data.index(0,strings+name,strings+size);label=data[strings+name:end].decode();names.setdefault(label,[]).append(value)
 def symbol(name):
  values=names[name]
  if len(values)!=1:raise ValueError('Unique final linked public symbol required '+name)
  return values[0]
 def read(va,fmt):
  n=struct.calcsize(fmt)
  for base,vm,off,sz in segments:
   if base<=va and va+n<=base+sz:return struct.unpack_from(fmt,data,off+va-base)
  raise ValueError('Linked descriptor pointer outside file bytes')
 public={}
 for name in ['_s24_kernel_xts_encrypt','_s24_kernel_xts_decrypt']:
  va=symbol(name);metadata=read(va,'<3Q');callbacks=read(va+24,'<4Q')
  if metadata!=(608,48,16) or not all(0xfffffff007000000<=x<0xfffffff008000000 for x in callbacks):raise ValueError('Final immutable descriptor metadata/pointer identity')
  public[name]={'va':va,'pa':va-0xfffffff004000000+0x40000000,'metadata':metadata,'callback_VAs':callbacks}
 table=symbol('_test_table') if '_test_table' in names else None
 if require_table and (table is None or read(table+144,'<2Q')!=(public['_s24_kernel_xts_encrypt']['va'],public['_s24_kernel_xts_decrypt']['va'])):raise ValueError('Actual linked caller table must reference immutable descriptors')
 return {'public_descriptors':public,'actual_test_table_va':table,'mapped_entry_va':symbol('_mapped_entry'),'tt0_va':symbol('_tt0'),'tt1_va':symbol('_tt1'),'l2_va':symbol('_high_l2'),'VA_minus_PA':0xffffffefc4000000,'TTBR1_L1_index':448,'TTBR1_L2_first_index':32,'L2_blocks':128,'L2_block_bytes':2*1024*1024,'mapped_VA_start':0xfffffff004000000,'mapped_PA_start':0x40000000,'mapped_bytes':256*1024*1024,'kernel_MMU_qualified':False}

def shifted_mapping_result(console,run,proof,segments):
 """Exact observed pinned-shim fault path, not a relaxed positive marker."""
 fault=re.search(r'avfboot: exception slot=(0x[0-9a-f]+) during xnu\s+esr=(0x[0-9a-f]+) elr=(0x[0-9a-f]+) far=(0x[0-9a-f]+)',console)
 expected_pc=proof['mapped_entry_va'];delta=proof['VA_minus_PA'];wrong_pa=(expected_pc-delta-0x200000)&((1<<64)-1)
 loaded=[(x['vmaddr']-delta,(x['vmaddr']-delta)+x['vmsize']) for x in segments]
 outside=not any(start<=wrong_pa<end for start,end in loaded)
 accepted=bool(fault) and tuple(int(fault[i],16) for i in [1,2,3,4])==(4,0x02000000,expected_pc,0) and outside and run['exit_code']==0 and run['outcome']=='pass' and 'KXTS MAPPING START' in console and 'KXTS MAPPED' not in console and 'KXTS CALLER PASS' not in console and 'avfboot: FATAL: unexpected exception' in console and 'avfboot: powering off' in console
 return {'accepted':bool(accepted),'classification':'controlled shifted mapping causes pinned shim exception handler and natural PSCI shutdown','expected_ELR':expected_pc,'shifted_physical_target':wrong_pa,'outside_loaded_image':outside,'actual_exception':{'slot':int(fault[1],16),'ESR':int(fault[2],16),'ELR':int(fault[3],16),'FAR':int(fault[4],16)} if fault else None,'normal_L2_first_index':32,'control_L2_first_index':33,'watchdog_timeout_required':False}

def guest_main(a,m):
 if not a.native_artifacts or not a.lease_grant:raise ValueError('Existing component artifacts and explicit coordinator lease message required')
 out=WT/'artifacts/kernel-xts'/a.run;out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,out/'builder.py');native=a.native_artifacts.resolve();parent=load(native/'evidence.json')
 spec=importlib.util.spec_from_file_location('accepted_xts_supervisor',WT/'src/platform/crypto/xts/check.py');bounded=importlib.util.module_from_spec(spec);spec.loader.exec_module(bounded);avf=bounded.avf
 r=dict(kind='host-test',origin='local-host',outcome='fail',task='KRN-031',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],source_reads=[],lease_grant=a.lease_grant,full_kernel_qualified=False,full_crypto_qualified=False,native_device_qualified=False,genuine_selected_caller_executed=False)
 r['_whole_deadline']=time.monotonic()+300;r['whole_timeout_seconds']=300
 try:
  revision=subprocess.run(['git','-C',str(WT),'rev-parse','HEAD'],env=ENV,capture_output=True,text=True,check=True,timeout=10);r['commit']=revision.stdout.strip();r['builder_sha256']=sha(__file__)
  tasks={t['id']:t for t in load(m/'state/lab.json')['tasks']}
  if tasks['KRN-031']['owner']!=OWNER or tasks['KRN-031']['status']!='in_progress':raise ValueError('Require current owner')
  if parent['outcome']!='pass' or not parent.get('guest_image_ready'):raise ValueError('Require source-qualified component image')
  image=m/parent['guest_images']['positive']['path'] if parent.get('guest_images') else native/'caller.macho';r['mapping_proof']=image_proof(image);r['component_parent']={'path':str((native/'evidence.json').relative_to(m)),'sha256':sha(native/'evidence.json')};r['image']={'path':str(image.relative_to(m)),'sha256':sha(image)}
  vm2=m/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105';vm4=m/'worktrees/vm-004-20261105/artifacts/qemu-host';qemu=vm4/'build-6/build/qemu-system-aarch64';shim=vm2/'Image'
  if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Qualified unchanged shim/QEMU')
  sb=load(vm2/'report.json');qb=load(vm4/'build-6/build-report.json');qm=load(vm4/'release-10.2.0/source-manifest.json')
  if sb['donor_commit']!=avf.PIN['scion_commit'] or qb['pin']['commit']!=avf.PIN['qemu_commit'] or qb['binary_sha256']!=avf.PIN['qemu_sha256']:raise ValueError('Immutable build report bindings')
  for row in sb['sources']:
   argv=['git','-C',str(m/'references/scion-avf'),'show',avf.PIN['scion_commit']+':'+row['path']];p=subprocess.run(argv,env=ENV,capture_output=True,timeout=10);actual=hashlib.sha256(p.stdout).hexdigest();r['source_reads'].append({'argv':argv,'exit_code':p.returncode,'sha256':actual})
   if p.returncode or actual!=row['sha256']:raise ValueError('Genuine shim source changed')
  for name in ['hw/arm/virt.c','hw/arm/boot.c','target/arm/tcg/psci.c']:
   if sha(vm4/'release-10.2.0/source/qemu-10.2.0'/name)!=qm[name]['sha256']:raise ValueError('Genuine QEMU board source changed')
  r['qualified_inputs']={'pins':avf.PIN,'qemu':str(qemu),'shim':str(shim),'reports':{str(p.relative_to(m)):sha(p) for p in [vm2/'report.json',vm4/'build-6/build-report.json',vm4/'release-10.2.0/source-manifest.json']},'helper_sha256':sha(WT/'src/platform/crypto/xts/check.py'),'fixture_sha256':sha(WT/'fixtures/public/xnu-kernel-xts/guest.c'),'runtime_sha256':sha(WT/'fixtures/public/avf-handoff/runtime.h')}
  images=parent.get('guest_images',{'positive':{'path':str(image.relative_to(m)),'sha256':sha(image)}})
  cases=['positive','wrong-cookie','bad-mapping','corrupt-vector','original-caller','factory-mismatch','panic','spin'] if a.all_controls else ['positive']
  if a.guest_cases:
   cases=a.guest_cases.split(',')
   if not cases or len(cases)!=len(set(cases)) or any(x not in ['positive','wrong-cookie','bad-mapping','corrupt-vector','original-caller','factory-mismatch','panic','spin'] for x in cases):raise ValueError('Explicit unique valid guest cases required')
  r['requested_cases']=cases
  r['guest_cases']=[]
  for case in cases:
   label=case if case in images else 'positive';image=m/images[label]['path']
   if sha(image)!=images[label]['sha256']:raise ValueError('Qualified component image changed '+case)
   kernel=bytearray(image.read_bytes());proof=({'scope':'unmapped spin-timeout control; no TTBR/caller execution claim','image':avf.macho(image)} if case=='spin' else image_proof(image,case!='factory-mismatch'))
   if case=='corrupt-vector':
    corpus=load(WT/'src/platform/crypto/xts/testdata/vectors.json');pattern=bytes.fromhex(corpus['vectors'][0]['ct'])
    if kernel.count(pattern)!=1:raise ValueError('Unique actual expected-ciphertext mutation point required')
    offset=kernel.index(pattern);kernel[offset]^=1;r['algorithm_control']={'offset':offset,'original_expected':pattern.hex(),'mutation':'xor1 in actual owned expected vector blob; real AES/caller unchanged'}
   payload=out/(case+'.xnup');cookie='xts_cookie=wrong' if case=='wrong-cookie' else 'xts_cookie=owned-adapter-v1';avf.xnup(payload,kernel,'cpus=1 '+cookie)
   command=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot','-initrd',payload]
   admit_memory(r,case)
   case_timeout=3 if case in ['bad-mapping','spin'] else 30
   if time.monotonic()+case_timeout+5>r['_whole_deadline']:raise ValueError('whole-batch deadline defers child '+case)
   result=bounded.run(command,out,case,case_timeout,512);r['commands'].append(result);console=(out/(case+'.log')).read_text(errors='replace')
   mapped=re.search(r'KXTS MAPPED pc=(0x[0-9a-f]+) mode=(0x[0-9a-f]+) init=(0x[0-9a-f]+) tt0=(0x[0-9a-f]+) tt1=(0x[0-9a-f]+) tcr=(0x[0-9a-f]+)',console);passed=re.search(r'KXTS CALLER PASS vectors=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=0x0',console)
   if mapped:
    enc=proof['public_descriptors']['_s24_kernel_xts_encrypt'];delta=proof['VA_minus_PA']
    if tuple(int(mapped[i],16) for i in [1,2,3])!=(proof['mapped_entry_va'],enc['va'],enc['callback_VAs'][0]):raise ValueError('Actual high-VA code/const descriptor/callback reference differs '+case)
    if int(mapped[4],16)!=((proof['tt0_va']-delta)&((1<<64)-1)) or int(mapped[5],16)!=((proof['tt1_va']-delta)&((1<<64)-1)):raise ValueError('Actual TTBR roots differ '+case)
   if case=='positive':
    ok=bool(mapped and passed) and result['outcome']=='pass' and 'KXTS CALLER FAIL' not in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
    if ok:
     r['vectors']=int(passed[1],16);r['checks']=int(passed[2],16);ok=r['vectors']==1220 and r['checks']==7350;r['genuine_selected_caller_executed']=bool(ok)
   elif case=='wrong-cookie':ok=not passed and not mapped and 'XTS SYNTHETIC REJECT command-cookie' in console and result['outcome']=='pass'
   elif case=='bad-mapping':
    diagnosis=shifted_mapping_result(console,result,proof,avf.macho(image)['segments']);r['mapping_control_diagnosis']=diagnosis;ok=diagnosis['accepted']
   elif case in ['corrupt-vector','original-caller']:
    failed=re.search(r'KXTS CALLER FAIL vectors=0x4c4 checks=(0x[0-9a-f]+) line=(0x[0-9a-f]+)',console);expected=(18,44) if case=='corrupt-vector' else (7338,53)
    ok=not passed and bool(mapped) and bool(failed) and tuple(int(failed[i],16) for i in [1,2])==expected and result['outcome']=='pass' and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
   elif case=='factory-mismatch':ok=not passed and bool(mapped) and 'KXTS FACTORY PASS vectors=0x0 checks=0xb line=0x0' in console and 'KXTS FACTORY MISMATCH REJECTED' in console and result['outcome']=='pass'
   elif case=='panic':ok=not passed and bool(mapped) and 'KXTS SYNTHETIC PANIC' in console and result['outcome']=='pass'
   else:ok=not passed and not mapped and 'KXTS SPIN CONTROL' in console and result['outcome']=='timeout'
   r['guest_cases'].append({'case':case,'accepted':bool(ok),'image':str(image.relative_to(m)),'image_sha256':sha(image),'payload_sha256':sha(payload),'console_sha256':sha(out/(case+'.log')),'mapping_proof':proof,'vectors':0 if case=='factory-mismatch' else r.get('vectors') if case=='positive' else None})
   if not ok:raise ValueError('Actual caller/control case failed '+case)
  if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Shared immutable guest input changed')
  r['outcome']='pass';r['summary']='Genuine selected caller/registration plus real XTS execute through actual immutable high-VA descriptor references; bounded original-caller/algorithm/mapping/publication/runtime controls, not full mc_provider or XNU startup/MMU/native qualification'
 except Exception as error:r['error']=repr(error)
 finally:
  r['whole_elapsed_seconds']=300-max(0,r.pop('_whole_deadline',time.monotonic())-time.monotonic())
  r['artifacts']=[str(p.relative_to(m)) for p in sorted(out.rglob('*')) if p.is_file()];r['sha256']={str(p.relative_to(m)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()};dump(out/'evidence.json',r)
 print(json.dumps({k:r.get(k) for k in ['outcome','error','vectors','checks','genuine_selected_caller_executed']},indent=2));return 0 if r['outcome']=='pass' else 1

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);p.add_argument('--prepare-guest',action='store_true');p.add_argument('--host-controls',action='store_true');p.add_argument('--prepare-controls',action='store_true');p.add_argument('--execute-guest',action='store_true');p.add_argument('--all-controls',action='store_true');p.add_argument('--guest-cases');p.add_argument('--native-artifacts',type=Path);p.add_argument('--lease-grant');a=p.parse_args();m=a.root.resolve()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',a.run) or WT==m:raise ValueError('Fresh isolated worktree run required')
 if a.execute_guest:return guest_main(a,m)
 out=WT/'artifacts/kernel-xts'/a.run;out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,out/'builder.py')
 spec=importlib.util.spec_from_file_location('accepted_xts_supervisor',WT/'src/platform/crypto/xts/check.py');bounded=importlib.util.module_from_spec(spec);spec.loader.exec_module(bounded)
 sys.path.insert(0,str(WT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),task='KRN-031',commands=[],checks=[],parents={},source_reads=[],source_inputs={},full_kernel_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,native_device_qualified=False,guest_executed=False)
 def check(name,ok,**extra):
  report['checks'].append(dict(name=name,passed=bool(ok),**extra))
  if not ok:raise ValueError(name)
 def run(argv,name,cwd=None,expected=0):
  check('memory-floor-'+name,memory_available()>=4*1024**3)
  # Existing owned supervisor uses WT as cwd. Native -I. is made absolute below.
  r=bounded.run(argv,out,name,30,256);report['commands'].append(r)
  if expected is not None:check('command-'+name,r['exit_code']==expected and r['outcome']=='pass')
  return r
 def git(repo,pin,file):
  argv=['git','-C',str(m/repo),'show',pin+':'+file];r=subprocess.run(argv,env=ENV,capture_output=True,timeout=10);report['source_reads'].append(dict(argv=argv,exit_code=r.returncode,sha256=hashlib.sha256(r.stdout).hexdigest(),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']}))
  check('pinned-object-'+file,r.returncode==0);return r.stdout
 try:
  ledger=load(m/'state/lab.json');tasks={t['id']:t for t in ledger['tasks']};t=tasks['KRN-031'];check('owned-task',t['status']=='in_progress' and t['owner']==OWNER);check('accepted-parents',all(tasks[n]['status']=='done' for n in ['KRN-029','KRN-030']))
  e=next(e for e in ledger['experiments'] if e['id']==a.experiment);check('registered-before-run',e['owner']==OWNER and e['task']=='KRN-031' and e['status']=='planned')
  r=subprocess.run(['git','-C',str(WT),'rev-parse','HEAD'],env=ENV,capture_output=True,text=True,check=True,timeout=10);report['commit']=r.stdout.strip()
  r=subprocess.run(['git','-C',str(WT),'status','--porcelain','--untracked-files=all'],env=ENV,capture_output=True,text=True,check=True,timeout=10);report['dirty_at_start']=r.stdout
  for name,path in [('xts',m/'docs/procedures/crypto-xts/qualified-evidence.json'),('runtime-link',m/'worktrees/krn-030-20261105/artifacts/kernel-runtime-link/native-session1/evidence.json')]:
   parent=load(path);check('parent-pass-'+name,parent['outcome']=='pass');report['parents'][name]=dict(path=str(path.relative_to(m)),sha256=sha(path))
  accepted=load(m/'docs/procedures/crypto-xts/qualified-evidence.json')
  runtime_path=m/'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/qualified-component.json';runtime=load(runtime_path)
  check('accepted-genuine-link-only-runtime',runtime['archive_sha256']=='67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5' and sha(m/runtime['archive'])==runtime['archive_sha256'] and runtime['archive_members']==287 and runtime['corecrypto_provider'] is False)
  report['qualified_link_runtime']={'descriptor':str(runtime_path.relative_to(m)),'descriptor_sha256':sha(runtime_path),'archive':runtime['archive'],'sha256':runtime['archive_sha256'],'resource_dir':runtime['resource_dir'],'scope':'Link-only; never substituted into native compile recipes; compiler support, not crypto'}
  remaining_path=m/'worktrees/krn-024-20261105/artifacts/kernel-provider-link/acceptance-session1/remaining-export-inputs.json';remaining=load(remaining_path);check('37-unchanged-private-export-demands',len(remaining)==37)
  for row in remaining.values():
   if sha(m/row['path'])!=row['sha256']:raise ValueError('Changed genuine private export list')
  report['remaining_exports']={'path':str(remaining_path.relative_to(m)),'sha256':sha(remaining_path),'entries':remaining}

  for name,digest in accepted['owned_source_hashes'].items():
   if name.startswith('src/platform/crypto/xts/') or name=='fixtures/public/avf-handoff/runtime.h':check('accepted-component-'+name,sha(WT/name)==digest)
  prior=m/'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3';rows=load(prior/'current-compiled-objects.json');deps=load(prior/'current-dependency-files.json');previous=load(prior/'report.json')
  check('exact-original-982-graph',len(rows)==len({x['id'] for x in rows})==982)
  for row in rows:
   for key in ['source','output']:
    if sha(m/row[key])!=row[key+'_sha256']:raise ValueError('Changed accepted graph '+row['id'])
  for name,digest in deps.items():
   if sha(m/name)!=digest:raise ValueError('Changed accepted dependency '+name)
  check('all3156-dependencies-unchanged',len(deps)==3156)
  report['original_graph']=dict(path=str((prior/'current-compiled-objects.json').relative_to(m)),sha256=sha(prior/'current-compiled-objects.json'),objects=len(rows),dependencies=len(deps),metadata=previous['metadata'],link_variables=previous['link_variables'])
  for name,digest in previous['metadata']['outputs'].items():check('metadata-'+name,sha(m/name)==digest)
  native_report_path=m/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json';native=load(native_report_path);report['parents']['native-recipes']=dict(path=str(native_report_path.relative_to(m)),sha256=sha(native_report_path))
  selected={row['id']:row for row in rows};srcbase=out/'source';(srcbase/'osfmk/minicrypto').mkdir(parents=True);(srcbase/'libkern/crypto').mkdir(parents=True)
  donor=git('references/s24-port',DONOR,'xnu/hackios/files/osfmk/minicrypto/mc_provider.c').decode();ported=donor.replace('extern int printf(const char *format, ...) __printflike(1, 2);\n','',1)
  row=selected['osfmk/mc_provider.o'];check('exact-retained-declaration-port',(m/row['source']).read_text()==ported)
  caller=git('references/apple-xnu',XNU,'libkern/crypto/corecrypto_aesxts.c');row2=selected['libkern/corecrypto_aesxts.o'];check('actual-caller-pin',caller==(m/row2['source']).read_bytes())
  files={'osfmk/mc_provider.o':('osfmk/minicrypto/mc_provider.c','0001-prepare-real-xts-modes-before-provider-publication.patch',ported.encode()),'libkern/corecrypto_aesxts.o':('libkern/crypto/corecrypto_aesxts.c','0002-propagate-rejected-xts-block-operations.patch',caller)}
  for ident,(rel,patch,raw) in files.items():
   dest=srcbase/rel;dest.write_bytes(raw)
   argv=['git','apply','--unsafe-paths','--check','--directory='+str(srcbase),str(WT/'patches/kernel-xts-provider'/patch)]
   # Absolute --directory avoids repository-prefix ambiguity, and the paths are owned.
   run(argv,'check-'+ident.replace('/','-'));argv.remove('--check');run(argv,'apply-'+ident.replace('/','-'))
   report['source_inputs'][str(dest.relative_to(m))]=sha(dest);report['source_inputs'][str((WT/'patches/kernel-xts-provider'/patch).relative_to(m))]=sha(WT/'patches/kernel-xts-provider'/patch)
  mini=git('references/s24-port',DONOR,'xnu/hackios/files/osfmk/minicrypto/minicrypto.h');(srcbase/'osfmk/minicrypto/minicrypto.h').write_bytes(mini)
  xts=WT/'src/platform/crypto/xts';objects=out/'objects';objects.mkdir();results=[]
  def recipe(ident):
   source=str(m/selected[ident]['source']);c=next(c for c in native['commands'] if '-c'in c['argv'] and source in c['argv']);return c,source
  def compile(ident,source,template,extra=()):
   c,original_source=recipe(template);argv=list(c['argv']);compiler=Path(argv[0]);check('actual-native-compiler-'+ident,sha(compiler)==native['compiler_sha256']);argv[argv.index(original_source)]=str(source);dest=objects/(ident.replace('/','-')+'.o');argv[argv.index('-o')+1]=str(dest);argv[argv.index('-MF')+1]=str(dest.with_suffix('.d'));argv=['-I'+c['cwd'] if x=='-I.' else x for x in argv];argv += ['-I'+str(xts),'-Werror=incompatible-function-pointer-types',*extra]
   run(argv,'compile-'+ident.replace('/','-'));header=struct.unpack('<4I',dest.read_bytes()[:16]);check('real-arm64-object-'+ident,(header[0],header[1],header[3])==(0xfeedfacf,0x100000c,1));obj=None if ident.startswith('fixture/') else ObjectData(dest);results.append(dict(id=ident,source=str(source.relative_to(m)),source_sha256=sha(source),output=str(dest.relative_to(m)),output_sha256=sha(dest),template=template,original_recipe_sha256=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()));return obj,dest
  provider,pobj=compile('osfmk/mc_provider.o',srcbase/'osfmk/minicrypto/mc_provider.c','osfmk/mc_provider.o')
  caller_obj,cobj=compile('libkern/corecrypto_aesxts.o',srcbase/'libkern/crypto/corecrypto_aesxts.c','libkern/corecrypto_aesxts.o')
  helper,hobj=compile('component/kernel_provider',xts/'kernel_provider.c','osfmk/mc_provider.o')
  profile=['-mgeneral-regs-only','-mstrict-align','-mno-outline-atomics','-I'+str(xts/'vendor/include'),'-I'+str(xts/'vendor/library'),'-isystem',str(m/'references/xnu-tapi/src/clang/lib/Headers'),'-DMBEDTLS_CONFIG_FILE="s24_xts_profile.h"','-DS24_XTS_FREESTANDING']
  adapter,aobj=compile('component/xts',xts/'xts.c','osfmk/mc_provider.o',profile)
  aes,aesobj=compile('component/aes',xts/'vendor/library/aes.c','osfmk/mc_provider.o',profile)
  report['components']=results
  # Static table inspection covers every real448-byte selected field.
  abi=load(WT/'fixtures/public/corecrypto-provider/registration-abi.json');fields=abi['table']['fields']
  baseline=ObjectData(m/selected['osfmk/mc_provider.o']['output']);observations=[]
  replacements={'ccaes_xts_encrypt':'_s24_kernel_xts_encrypt','ccaes_xts_decrypt':'_s24_kernel_xts_decrypt'}
  for field in fields:
   name=field['field'];offset=field['offset']
   if field['state']=='relocated' or name in replacements:
    r=provider.relocation('_mc_funcs',offset);expected=replacements.get(name,field.get('target'))
    check('actual-slot-'+name,r['name']==expected)
    if name not in replacements:check('original-relocation-'+name,baseline.relocation('_mc_funcs',offset)['name']==r['name'])
    observations.append(dict(field=name,offset=offset,state='relocated',target=r['name']))
   else:
    check('actual-zero-'+name,provider.value('_mc_funcs','<Q',offset)==(0,))
    observations.append(dict(field=name,offset=offset,state='deferred' if name=='ccsha256_di' else 'unsupported'))
  check('36-relocations-one-deferred-19-unsupported',sum(x['state']=='relocated' for x in observations)==36 and sum(x['state']=='deferred' for x in observations)==1 and sum(x['state']=='unsupported' for x in observations)==19)
  report['table_observation']=observations
  # Inspect actual native branch relocations, not only source statement order.
  init_symbol=provider.named['_minicrypto_init'];section=provider.sections[init_symbol['section']-1];calls=[]
  start=init_symbol['value']-section['address'];later=[x['value']-section['address'] for x in provider.named.values() if x['section']==init_symbol['section'] and x['name'].startswith('_') and x['value']>init_symbol['value']];end=min(later) if later else section['size']
  for i in range(section['nreloc']):
   at,info=struct.unpack_from('<iI',provider.data,section['reloc']+8*i)
   if not(start<=at<end) or info>>28!=2 or not(info>>27)&1:continue
   symbol=provider.symbols[info&0xffffff]['name'];insn=struct.unpack_from('<I',provider.data,section['offset']+at)[0]
   if symbol in ['_s24_kernel_xts_prepare','_s24_kernel_xts_encrypt_mode','_s24_kernel_xts_decrypt_mode','_ccsha256_di','_register_crypto_functions']:
    check('actual-native-BL-'+symbol,(insn&0xfc000000)==0x94000000);calls.append({'offset':at,'target':symbol})
  calls.sort(key=lambda x:x['offset']);report['startup_call_relocations']=calls
  expected_calls=['_s24_kernel_xts_prepare','_s24_kernel_xts_encrypt_mode','_s24_kernel_xts_decrypt_mode','_ccsha256_di','_register_crypto_functions'];check('native-prepare-SHA-register-call-order',[x['target'] for x in calls]==expected_calls)
  report['public_mode_objects']={}
  for name,prefix in [('_s24_kernel_xts_encrypt','enc'),('_s24_kernel_xts_decrypt','dec')]:
   metadata=helper.value(name,'<3Q');check('actual-public-mode-metadata-'+name,metadata==(608,48,16));relocations=[helper.relocation(name,offset) for offset in [24,32,40,48]]
   check('actual-typed-mode-relocations-'+name,[x['name'] for x in relocations]==['_'+prefix+'_init','_'+prefix+'_sched','_'+prefix+'_tweak','_'+prefix+'_blocks'])
   report['public_mode_objects'][name]={'metadata':metadata,'callbacks':relocations,'const_definition':True,'physical_write_protection_qualified':False}

  definitions=set();original_imports={s['name'] for s in baseline.symbols if s['kind']&0x0e==0 and s['name']}
  original_definitions=set()
  report['component_symbols']={}
  for label,obj in [('provider',provider),('caller',caller_obj),('publication',helper),('adapter',adapter),('aes',aes)]:
   defined={x['name'] for x in obj.symbols if x['kind']&0x0e==0x0e and x['kind']&1};imports={x['name'] for x in obj.symbols if x['kind']&0x0e==0 and x['name']};definitions |=defined
   report['component_symbols'][label]={'definitions':sorted(defined),'imports':sorted(imports)}
  report['native_compiler']=dict(path=str(Path(recipe('osfmk/mc_provider.o')[0]['argv'][0]).relative_to(m)),sha256=native['compiler_sha256'])
  report['helper_layout']=helper.value('_s24_kernel_xts_layout','<11Q');report['private_layout']=adapter.value('_s24_xts_layout','<6Q')
  check('public-private-and-selected-layout',report['helper_layout'][:7]==(80,8,1072,1072,16,608,48) and report['private_layout'][:4]==(608,16,48,16))
  providers_path=m/previous['graph']['symbol-providers']['path'];check('accepted-provider-map',sha(providers_path)==previous['graph']['symbol-providers']['sha256']);known=load(providers_path)
  if isinstance(known,list):raise ValueError('Expected accepted named provider map')
  extra_definitions=set().union(*(set(v['definitions']) for v in report['component_symbols'].values()))
  all_imports=set().union(*(set(v['imports']) for v in report['component_symbols'].values()))
  check('new-component-import-provider-closure',not (all_imports-set(known)-extra_definitions),unresolved=sorted(all_imports-set(known)-extra_definitions))
  check('no-new-component-duplicates',not(set(report['component_symbols']['publication']['definitions']+report['component_symbols']['adapter']['definitions']+report['component_symbols']['aes']['definitions'])&set(known)))
  report['import_provider_map']={name:('new-component' if name in extra_definitions else known[name]) for name in sorted(all_imports)}
  check('exact-five-new-native-provider-imports',set(report['component_symbols']['provider']['imports'])-original_imports=={'_s24_kernel_xts_prepare','_s24_kernel_xts_encrypt_mode','_s24_kernel_xts_decrypt_mode','_s24_kernel_xts_encrypt','_s24_kernel_xts_decrypt'})
  provider_text=(srcbase/'osfmk/minicrypto/mc_provider.c').read_text();check('prepare-and-deferred-sha-before-registration',provider_text.index('s24_kernel_xts_prepare()')<provider_text.index('mc_funcs.ccsha256_di = ccsha256_di();')<provider_text.index('register_crypto_functions(&mc_funcs)'))
  unchanged=[row for row in rows if row['id'] not in files];check('exact980-other-object-identities',len(unchanged)==980)
  dump(out/'replacement-components.json',{'replacements':results[:2],'additional_kernel_components':results[2:5],'unchanged_originals':unchanged,'original_dependency_hashes':deps,'no_full_link':True,'remaining_unsupported_crypto_fields':[x for x in observations if x['state']=='unsupported'],'remaining_private_ARM_exports':37})
  if a.host_controls:
   host=Path('/home/egor/.local/bin/clang');host_pin=accepted['tools']['host'];check('accepted-host-compiler',sha(host)==host_pin['sha256'])
   for path,digest in host_pin['runtime_hashes'].items():check('accepted-sanitizer-runtime-'+Path(path).name,sha(path)==digest)
   hostflags=['--target=x86_64-unknown-linux-gnu','-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(xts),'-I'+str(xts/'vendor/include'),'-I'+str(xts/'vendor/library'),'-I'+str(xts/'testdata'),'-I'+str(m/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu/libkern'),'-I'+str(m/'references/apple-xnu/EXTERNAL_HEADERS'),'-DMBEDTLS_CONFIG_FILE="s24_xts_profile.h"']
   adapter_text=(xts/'xts.c').read_text();gated=out/'gated-factory.c';mismatch=out/'mismatch-factory.c'
   start='int s24_xts_descriptor(struct ccmode_xts *mode, int decrypt)\n{'
   if adapter_text.count(start)!=1:raise ValueError('Exact accepted real factory injection point required')
   gated.write_text(adapter_text.replace(start,'extern void kxts_factory_gate(void);\n'+start+'\n    kxts_factory_gate();'))
   end='m->custom = NULL; m->custom1 = NULL; m->impl = CC_IMPL_AES_XTS_GENERIC;'
   mismatch.write_text(adapter_text.replace(end,end+'\n    m->size += 16; /* owned negative metadata control, real algorithm unchanged */'))
   report['publication_controls']={'instrumentation':'A fresh accepted real factory copy gates entry while other threads observe actual preparing state; metadata mismatch is a fresh size-only factory copy. Helper and AES unmodified.','source_hashes':{str(x.relative_to(m)):sha(x) for x in [gated,mismatch,WT/'fixtures/public/xnu-kernel-xts/host_publication.c']},'host_compiler':str(host),'host_sha256':sha(host)}
   for label,source in [('helper',xts/'kernel_provider.c'),('aes',xts/'vendor/library/aes.c'),('factory-gated',gated),('factory-mismatch',mismatch)]:
    run([host,*hostflags,'-MD','-MF',objects/('host-'+label+'.d'),'-c',source,'-o',objects/('host-'+label+'.o')],'host-compile-'+label)
   for label,extra in [('publication',[]),('mismatch',['-DKXTS_FACTORY_MISMATCH'])]:
    run([host,*hostflags,*extra,'-MD','-MF',objects/('host-'+label+'.d'),'-c',WT/'fixtures/public/xnu-kernel-xts/host_publication.c','-o',objects/('host-'+label+'.o')],'host-compile-'+label)
    run([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread','-Wl,--threads=1',objects/'host-helper.o',objects/'host-aes.o',objects/('host-'+('factory-gated' if label=='publication' else 'factory-mismatch')+'.o'),objects/('host-'+label+'.o'),'-o',out/('host-'+label)],'host-link-'+label)
    result=bounded.run([out/('host-'+label)],out,'host-run-'+label,10,256);report['commands'].append(result);check('real-'+label+'-control',result['outcome']=='pass' and 'KXTS PUBLICATION PASS' in (out/('host-run-'+label+'.log')).read_text())
  if a.prepare_guest:
   fixture=WT/'fixtures/public/xnu-kernel-xts/guest.c';guestflags=profile+['-I'+str(WT/'fixtures/public/avf-handoff'),'-I'+str(xts/'testdata')]
   register=m/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu/libkern/crypto/register_crypto.c';check('actual-registration-source-pin',register.read_bytes()==git('references/apple-xnu',XNU,'libkern/crypto/register_crypto.c'))
   reg,regobj=compile('fixture/register',register,'libkern/corecrypto_aesxts.o')
   mem,memobj=compile('fixture/memory',xts/'memory.c','libkern/corecrypto_aesxts.o')
   guest,gobj=compile('fixture/guest',fixture,'libkern/corecrypto_aesxts.o',guestflags)
   ld=m/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
   command=[ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',cobj,hobj,aobj,aesobj,regobj,memobj,gobj,'-o',out/'caller.macho']
   run(command,'caller-component-link');report['synthetic_image']=bounded.avf.macho(out/'caller.macho');report['mapping_proof']=image_proof(out/'caller.macho');report['guest_image_ready']=True;report['guest_linker']={'path':str(ld),'sha256':sha(ld)}
   if a.prepare_controls:
    guest_images={'positive':out/'caller.macho'}
    # Existing genuine original caller object is the actual propagation counterexample.
    original_cmd=list(command);original_cmd[original_cmd.index(cobj)]=m/selected['libkern/corecrypto_aesxts.o']['output'];original_cmd[-1]=out/'original-caller.macho'
    run(original_cmd,'original-caller-component-link');guest_images['original-caller']=out/'original-caller.macho'
    for label,macro in [('bad-mapping','KXTS_BAD_MAPPING'),('spin','KXTS_SPIN_CONTROL'),('factory-mismatch','KXTS_FACTORY_MISMATCH'),('panic','KXTS_PANIC_CONTROL')]:
     obj,dest=compile('fixture/'+label,fixture,'libkern/corecrypto_aesxts.o',guestflags+['-D'+macro]);link=list(command);link[link.index(gobj)]=dest;link[-1]=out/(label+'.macho')
     if label=='factory-mismatch':
      # Real accepted factory copy with wrong reported size; helper must refuse publication.
      mismatch=out/'mismatch-factory.c'
      if not mismatch.exists():mismatch.write_text((xts/'xts.c').read_text().replace('m->custom = NULL; m->custom1 = NULL; m->impl = CC_IMPL_AES_XTS_GENERIC;','m->custom = NULL; m->custom1 = NULL; m->impl = CC_IMPL_AES_XTS_GENERIC; m->size += 16;'))
      _,badobj=compile('fixture/mismatch-adapter',mismatch,'osfmk/mc_provider.o',profile);link[link.index(aobj)]=badobj
     run(link,label+'-component-link');guest_images[label]=out/(label+'.macho')
    report['guest_images']={label:{'path':str(path.relative_to(m)),'sha256':sha(path),'mapping_proof':({'scope':'unmapped spin-timeout control; no TTBR/caller execution claim','image':bounded.avf.macho(path)} if label=='spin' else image_proof(path,label!='factory-mismatch'))} for label,path in guest_images.items()}

  c,oldsource=recipe('osfmk/mc_provider.o');bad_argv=list(c['argv']);bad_argv[bad_argv.index(oldsource)]=str(WT/'fixtures/public/xnu-kernel-xts/reject_wrong_callback.c');bad_argv[bad_argv.index('-o')+1]=str(out/'rejected.o');bad_argv[bad_argv.index('-MF')+1]=str(out/'rejected.d');bad_argv=['-I'+c['cwd'] if x=='-I.' else x for x in bad_argv];bad_argv += ['-I'+str(xts),'-Werror=incompatible-function-pointer-types','-Werror=incompatible-function-pointer-types-strict']
  bad=run(bad_argv,'reject-incompatible-actual-callback',expected=None);check('real-genuine-header-callback-rejection',bad['exit_code']!=0 and 'incompatible function pointer types' in (out/'reject-incompatible-actual-callback.log').read_text())
  report['component_dependency_hashes']={}
  for dep in sorted(objects.glob('*.d')):
   first=dep.read_text().replace('\\\n',' ').splitlines()[0]
   if ':' not in first:continue
   for name in first.split(':',1)[1].split():
    if name=='\\':continue
    path=Path(name)
    if not path.is_absolute():raise ValueError('Native dependency must bind absolute header input '+name)
    report['component_dependency_hashes'][str(path.relative_to(m)) if path.is_relative_to(m) else str(path)]=sha(path)
  report['owned_source_hashes']={str(path.relative_to(WT)):sha(path) for base in [WT/'src/platform/crypto/xts/kernel_provider.c',WT/'src/platform/crypto/xts/kernel_provider.h',WT/'tools/build/xnu_kernel_xts.py',WT/'fixtures/public/xnu-kernel-xts',WT/'patches/kernel-xts-provider'] for path in ([base] if base.is_file() else sorted(base.rglob('*'))) if path.is_file()}
  report['outcome']='pass';report['summary']='Actual native two-slot provider/caller replacement and real backend components; no full kernel link or native-device result' 
 except Exception as error:report['error']=repr(error)
 finally:
  report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();report['artifacts']=[str(p.relative_to(m)) for p in sorted(out.rglob('*')) if p.is_file()];report['sha256']={str(p.relative_to(m)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()};dump(out/'evidence.json',report)
 print(json.dumps({k:report.get(k) for k in ['outcome','error','helper_layout','private_layout','guest_image_ready']},indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
