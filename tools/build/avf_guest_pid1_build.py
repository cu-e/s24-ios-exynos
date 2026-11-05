#!/usr/bin/env python3
"""Owned minimal static PID1 producer; plan is source-only, build requires root admission."""
import argparse,datetime,hashlib,importlib.util,json,os,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
TASK='VM-034';OWNER='codex-guest-pid1-20261106-dr';MIB=1024**2
GUARDS={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','LC_ALL':'C','LANG':'C','PYTHONUTF8':'1','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
ENV={'PATH':'/usr/bin:/bin',**GUARDS}
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
 d=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(65536),b''):d.update(b)
 return d.hexdigest()
def load(path,limit=16*MIB):
 p=Path(path)
 if not p.is_file()or p.stat().st_size>limit:raise ValueError('Missing/oversize metadata: '+str(p))
 with p.open()as f:return json.load(f)
def write(path,data):Path(path).write_text(json.dumps(data,indent=2)+'\n')
def memory():
 d={}
 for line in Path('/proc/self/status').read_text().splitlines():
  if line.startswith(('VmRSS:','VmHWM:')):d[line.split(':')[0]+'_bytes']=int(line.split()[1])*1024
 return d

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def bind(main,experiment,out_arg):
 main=main.resolve()
 if main!=MAIN:raise ValueError('Sole canonical MAIN required')
 if '..'in out_arg.parts:raise ValueError('Parent-component output denied')
 state=load(main/'state/lab.json');task=next(t for t in state['tasks']if t['id']==TASK)
 if task['status']!='in_progress'or task['owner']!=OWNER:raise ValueError('Original active VM034 owner required')
 required={'src/guest/avf-pid1','tools/build/avf_guest_pid1_build.py','docs/procedures/avf-guest-pid1-build'}
 if set(task['paths'])!=required:raise ValueError('Exact acquired producer boundaries required')
 if any(next(t for t in state['tasks']if t['id']==d)['status']!='done'for d in task['depends_on']):raise ValueError('Task prerequisites incomplete')
 wt=main/task['worktree']
 if task['worktree']!='worktrees/vm-034-20261106'or wt.resolve()!=ROOT or wt.parent.resolve()!=main/'worktrees'or wt.is_symlink():raise ValueError('Canonical assigned worktree required')
 plans=[p for p in state['experiments']if p['id']==experiment]
 if len(plans)!=1 or plans[0]['status']!='planned'or plans[0]['task']!=TASK or plans[0]['owner']!=OWNER:raise ValueError('Actual prospective MAIN experiment required')
 out=out_arg if out_arg.is_absolute()else ROOT/out_arg
 # Check every extant lexical ancestor before resolution and creation.
 for p in [out,*out.parents]:
  if p.is_symlink():raise ValueError('Symlink output ancestry denied')
 if out.exists()or out.resolve()!=out.absolute()or out==ROOT/'artifacts'or not out.is_relative_to(ROOT/'artifacts'):raise ValueError('Fresh strict owned artifacts child required')
 out.mkdir(parents=True)
 return out,task,plans[0]

def source_bindings(main):
 fixture_path=main/'worktrees/vm-025-20261106/fixtures/public/avf-guest-pid1/inputs.json';fixture=load(fixture_path)
 selected=main/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2/source/xnu'
 prepared_path=selected.parents[1]/'prepared-component.json';prepared=load(prepared_path)
 records={}
 for row in fixture['inputs']:
  p=main/row['path']
  if sha(p)!=row['sha256']:raise ValueError('Changed immutable VM025/selected/legacy input: '+row['path'])
  records[row['path']]={'sha256':row['sha256'],'role':row['role']}
 additional=['osfmk/mach/arm/vm_param.h','osfmk/mach/arm/syscall_sw.h','libsyscall/custom/SYS.h','bsd/sys/fcntl.h','APPLE_LICENSE']
 frozen=prepared['prepared_source_files']
 for name in additional:
  p=selected/name;digest=sha(p)
  if frozen.get(name)!=digest:raise ValueError('Additional selected source not in immutable prepared map: '+name)
  records[str(p.relative_to(main))]={'sha256':digest,'role':'Selected genuine syscall/flag/interface/license source'}
 master=(selected/'bsd/kern/syscalls.master').read_text();reg=(selected/'osfmk/arm64/proc_reg.h').read_text();ret=(selected/'bsd/dev/arm/systemcalls.c').read_text();vm=(selected/'osfmk/mach/arm/vm_param.h').read_text();stub=(selected/'libsyscall/custom/SYS.h').read_text();fcntl=(selected/'bsd/sys/fcntl.h').read_text()
 for number,name in [(1,'exit'),(4,'write'),(5,'open'),(20,'getpid'),(274,'sys_sysctlbyname')]:
  if not re.search(r'^'+str(number)+r'\s+[^\n]*\b'+name+r'\(',master,re.M):raise ValueError('Selected syscall number/signature changed')
 if not re.search(r'#define\s+ARM64_SYSCALL_CODE_REG_NUM\s+\(16\)',reg)or not re.search(r'#define\s+SWI_SYSCALL\s+0x80',vm)or'svc   #SWI_SYSCALL'not in stub:raise ValueError('Selected trap register/immediate source changed')
 if 'ss64->x[1] = 0;'not in ret or'ss64->x[1] = uthread->uu_rval[1];'not in ret or'ss64->cpsr |= PSR64_CF;'not in ret:raise ValueError('Selected x1/carry return path changed')
 if not re.search(r'#define\s+O_RDWR\s+0x0*2\b',fcntl):raise ValueError('Selected console open flag changed')
 source=ROOT/'src/guest/avf-pid1/pid1.c';text=source.read_text()
 source_contract(text)
 return {'selected_source_pins':fixture['source_pins'],'selected_kernel_root':str(selected.relative_to(main)),'immutable_inputs':records,'VM025_fixture':{'path':str(fixture_path.relative_to(main)),'sha256':sha(fixture_path)},'owned_source':{'path':str(source.relative_to(main)),'sha256':sha(source)},'legacy':fixture['legacy'],'legacy_rejection':fixture['legacy_rejection'],'namespace_accepted_by_this_task':False}

def source_contract(text):
 for needle in ['"+r"(x0)','"+r"(x1)','"+r"(x16)','"=&r"(error)','"memory", "cc"','svc #0x80','cset %3, cs','pid.value==1','!os.error && darwin','size==7','ostype[6]==0','VM002: pid=1 ostype=Darwin owned-entry=v1']:
  if needle not in text:raise ValueError('Owned reviewed source contract missing: '+needle)
 if 'Darwin Kernel Version'in text or 'Apple launchd'in text.replace('or Apple launchd',''):raise ValueError('Fake kernel/userland banner denied')
 return True

def tools(main):
 base=main/'artifacts/xnu-compiler-cxx-storage/source-build-session2';cr=load(base/'report.json');lp=main/'artifacts/xnu-macho-tools/macho-session4';lr=load(lp/'report.json')
 if cr['outcome']!='pass'or cr['source_revision']!='fa9443738c1a18accef4244732ec6d6ee97a8133'or lr['outcome']!='pass'or lr['source_pins']['xnu-cctools']!='904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb':raise ValueError('Applicable source-built tool provenance required')
 result={'compiler':{'path':str(base/'clang'),'sha256':cr['compiler_sha256'],'source_commit':cr['source_revision'],'report':str((base/'report.json').relative_to(main)),'report_sha256':sha(base/'report.json')}}
 for key,name in [('linker','aarch64-apple-darwin-ld'),('nm','aarch64-apple-darwin-nm')]:result[key]={'path':str(lp/'prefix/bin'/name),'sha256':lr['prefix_files_sha256']['bin/'+name],'source_commit':lr['source_pins']['xnu-cctools'],'report':str((lp/'report.json').relative_to(main)),'report_sha256':sha(lp/'report.json')}
 for row in result.values():
  if sha(row['path'])!=row['sha256']:raise ValueError('Exact source-built tool bytes changed')
 runner=main/'worktrees/vm-009-20261106/tools/build/avf_kernel_objects.py';result['runner']={'path':str(runner),'sha256':sha(runner),'review_admission_required':True}
 parser=main/'worktrees/vm-025-20261106/tools/build/avf_guest_pid1.py';result['preflight']={'path':str(parser),'sha256':sha(parser),'independent_candidate_admission_required':True}
 return result

def recipe(tool,out):
 clang=tool['compiler']['path'];ld=tool['linker']['path'];source=ROOT/'src/guest/avf-pid1/pid1.c'
 target=['--target=arm64-apple-ios16.5','-O2','-mgeneral-regs-only','-fno-stack-protector','-fno-pic','-fno-pie']
 return [
 {'name':'source-to-ir','argv':[clang,*target,'-std=c11','-ffreestanding','-nostdinc','-fno-builtin','-Wall','-Wextra','-Werror','-S','-emit-llvm',str(source),'-o',str(out/'pid1.ll')]},
 {'name':'ir-to-assembly','argv':[clang,*target,'-x','ir','-S',str(out/'pid1.ll'),'-o',str(out/'pid1.s')]},
 {'name':'assembly-to-object','argv':[clang,'--target=arm64-apple-ios16.5','-x','assembler','-c',str(out/'pid1.s'),'-o',str(out/'pid1.o')]},
 {'name':'static-link','argv':[ld,'-arch','arm64','-static','-e','_start','-iphoneos_version_min','16.5','-pagezero_size','0x100000000','-no_uuid',str(out/'pid1.o'),'-o',str(out/'pid1')]},
 {'name':'undefined-symbols','argv':[tool['nm']['path'],'-u',str(out/'pid1')]}
 ]

def inspect_actual(out,parser):
 data=parser.bounded_bytes(out/'pid1');meta=parser.macho(data);text=next(s for s in meta['sections']if s['name']=='__text');code=data[text['offset']:text['offset']+text['size']]
 words=[x[0]for x in struct.iter_unpack('<I',code[:len(code)//4*4])];svc=[x for x in words if x&0xffe0001f==0xd4000001]
 if not svc or any(x!=0xd4001001 for x in svc):raise ValueError('Actual executable SVC immediate/convention differs')
 ir=(out/'pid1.ll').read_text();calls=[x for x in ir.splitlines()if 'asm sideeffect'in x and'svc'in x]
 if not calls:raise ValueError('No real emitted raw-syscall IR')
 for line in calls:
  for token in ['={x0}','={x1}','={x16}','=&r','~{memory}','~{cc}']:
   if token not in line:raise ValueError('Actual LLVM asm result/clobber constraint missing: '+token)
 assembly=(out/'pid1.s').read_text()
 if not re.search(r'\bcset\s+x\d+,\s*(cs|hs)\b',assembly):raise ValueError('Actual carry-result instruction missing')
 if any(x in assembly for x in ['_memcpy','_memset','_bzero','_stack_chk','_cerror']):raise ValueError('Unexpected libc/runtime dependency in actual assembly')
 controls=parser.controls(data)
 if not all(x.get('outcome')=='rejected'for x in controls):raise ValueError('Actual image corruption control unexpectedly admitted')
 for label,changed in [('ELF-magic',b'\x7fELF'+data[4:]),('arm64e-subtype',data[:8]+struct.pack('<I',2)+data[12:])]:
  try:parser.macho(changed)
  except (ValueError,UnicodeError,struct.error)as error:controls.append({'case':label,'outcome':'rejected','reason':str(error),'sha256':hashlib.sha256(changed).hexdigest()})
  else:raise ValueError('Actual bad ABI/ELF image accepted')
 return {'structure':meta,'actual_svc_count':len(svc),'actual_svc_word':'0xd4001001','real_llvm_asm_records':calls,'actual_image_controls':controls,'runtime_executed':False,'independently_ABI_admitted':False}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--mode',choices=['plan','build'],required=True);ap.add_argument('--main',type=Path,default=MAIN);ap.add_argument('--experiment',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--source-plan',type=Path);ap.add_argument('--source-plan-sha256');ap.add_argument('--approval',type=Path);ap.add_argument('--approval-sha256');a=ap.parse_args()
 out=None;report={'task':TASK,'owner':OWNER,'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':stamp(),'summary':'Owned PID1 source/build attempt; no boot or runtime identity acceptance','argv':sys.argv,'compiler_executed':False,'linker_executed':False,'guest_executed':False,'device_executed':False,'commands':[]}
 try:
  out,task,plan=bind(a.main,a.experiment,a.out);report['planned_experiment']=plan;report['mode']=a.mode;report['current_image_memory_start']=memory()
  rev=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],env=ENV,capture_output=True,text=True,timeout=10)
  if rev.returncode:raise ValueError('Owned source commit unavailable')
  report['commit']=rev.stdout.strip();report['implementation_sha256']=sha(__file__);report['bindings']=source_bindings(a.main);report['tools']=tools(a.main);report['commands_planned']=recipe(report['tools'],out)
  parser=module('owned_pid1_preflight',report['tools']['preflight']['path'])
  legacy=a.main/report['bindings']['legacy']['path'];report['legacy_structure']=parser.macho(parser.bounded_bytes(legacy));report['legacy_abi_accepted']=False
  try:source_contract((a.main/report['bindings']['legacy']['source_path']).read_text())
  except ValueError as error:report['actual_legacy_source_control']={'rejected':True,'reason':str(error)}
  else:raise ValueError('Actual legacy input-only x1 contract was not rejected')
  source_plan={k:report[k]for k in ['task','owner','commit','implementation_sha256','bindings','tools','commands_planned']};source_plan['output_root']=str(out);source_plan['canonical_recipe']=[{'name':row['name'],'argv':[x.replace(str(out)+'/', '@OUTPUT@/')for x in row['argv']]}for row in report['commands_planned']];write(out/'plan.json',source_plan)
  if a.mode=='plan':
   report['outcome']='pass';report['summary']='Source-only VM034 owned PID1/selected ABI/tool/finite recipe bindings prepared; zero compiler/linker/guest commands, no executable or runtime qualification'
  else:
   if not a.source_plan or not a.source_plan_sha256 or sha(a.source_plan)!=a.source_plan_sha256:raise ValueError('Exact prior source-plan hash required')
   old=load(a.source_plan)
   if old['canonical_recipe']!=source_plan['canonical_recipe']:raise ValueError('Build recipe changed beyond owned output substitution')
   for key in ['implementation_sha256','bindings','tools']:
    if old[key]!=report[key]:raise ValueError('Source/tool/producer changed after preparation: '+key)
   if not a.approval or not a.approval_sha256 or sha(a.approval)!=a.approval_sha256:raise ValueError('Explicit root small-build admission descriptor required')
   approval=load(a.approval)
   if approval.get('task')!=TASK or approval.get('owner')!=OWNER or approval.get('source_plan_sha256')!=a.source_plan_sha256 or approval.get('producer_sha256')!=sha(__file__)or approval.get('reviewed_runner_sha256')!=report['tools']['runner']['sha256']or approval.get('runner_reviewed')is not True or not approval.get('root_lease')or approval.get('max_jobs')!=1 or approval.get('max_project_jobs')!=2 or approval.get('max_owned_rss_bytes')!=256*MIB or approval.get('qemu_allowed')is not False:raise ValueError('Root admission does not bind exact reviewed producer/runner/resources')
   report['admission']={'path':str(a.approval),'sha256':a.approval_sha256,'data':approval};runner=module('reviewed_pid1_process_helper',report['tools']['runner']['path']);supervise=runner.supervisor(a.main)
   for row in report['commands_planned']:
    record=runner.run_child(row['argv'],ROOT,out,row['name'],supervise,timeout=60,admit=True);report['commands'].append(record)
    if record['child_started']and row['name']in ['source-to-ir','ir-to-assembly','assembly-to-object']:report['compiler_executed']=True
    if record['child_started']and row['name']=='static-link':report['linker_executed']=True
    if record['outcome']!='pass':
     if record['outcome']=='resource-deferred':report['outcome']='inconclusive'
     raise ValueError('Actual '+row['name']+' '+record['outcome'])
   if (out/'undefined-symbols.stdout.txt').read_text().strip():raise ValueError('Actual static PID1 has undefined symbols')
   report['inspection']=inspect_actual(out,parser);image=out/'pid1';source=ROOT/'src/guest/avf-pid1/pid1.c';candidate={'path':str(image.relative_to(a.main)),'sha256':sha(image),'source_path':str(source.relative_to(a.main)),'source_sha256':sha(source)};write(out/'candidate.json',candidate);report['candidate']=candidate
   report['outcome']='pass';report['summary']='Actually source-built owned ARM64 static MachO PID1, corrected x0/x1/carry constraints and structural controls; independently reviewed ABI/candidate admission, real kernel exec/console/syscalls/PID1/stop remain unmeasured'
 except Exception as error:
  report['error']=repr(error)
  print(json.dumps({'outcome':report['outcome'],'error':report['error']},indent=2))
 finally:
  report['current_image_memory_end']=memory();report['finished_at']=stamp()
  if out is not None:
   report['artifact_hashes']={str(p.relative_to(a.main)):sha(p)for p in sorted(out.rglob('*'))if p.is_file()};report['artifacts']=list(report['artifact_hashes'])
   if not report['artifacts']:write(out/'failure.json',{'error':report.get('error'),'recorded_at':stamp()});report['artifacts']=[str((out/'failure.json').relative_to(a.main))]
   write(out/'evidence.json',report)
 if report['outcome']=='pass'and a.mode=='build':
  evidence_path=out/'evidence.json';provenance={'origin':'owned-source-built','input_sha256':report['candidate']['sha256'],'sources':[{'repository':'owned:s24-ios-exynos','commit':report['commit']},{'repository':'https://github.com/apple-oss-distributions/xnu','commit':'c54f35ca767986246321eb901baf8f5ff7923f6a'},{'repository':'https://github.com/Scion-Project/hackios-xnu-kernel','commit':'a6f4bc38aa244359cd365c976244a88c9d6b3304'}],'build_evidence':{'path':str(evidence_path.relative_to(a.main)),'sha256':sha(evidence_path)}};write(out/'mockfs-provenance.json',provenance);write(out/'handoff-index.json',{'raw_evidence':provenance['build_evidence'],'candidate':{'path':str((out/'candidate.json').relative_to(a.main)),'sha256':sha(out/'candidate.json')},'mockfs_provenance':{'path':str((out/'mockfs-provenance.json').relative_to(a.main)),'sha256':sha(out/'mockfs-provenance.json')},'independently_ABI_admitted':False,'guest_executed':False})
 if report['outcome']=='pass':print(json.dumps({'outcome':'pass','mode':a.mode,'compiler_executed':report['compiler_executed'],'linker_executed':report['linker_executed'],'guest_executed':False,'out':str(out)},indent=2))
 return 0 if report['outcome']=='pass'else 2 if report['outcome']=='inconclusive'else 1
if __name__=='__main__':raise SystemExit(main())
