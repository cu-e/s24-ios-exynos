#!/usr/bin/env python3
"""Independent bounded PID1 source/IR/ARM64/Mach-O review; no compiler/guest."""
import argparse,datetime,hashlib,json,os,re,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
BASE=MAIN/'worktrees/vm-034-20261106'
BUILD=BASE/'artifacts/avf-guest-pid1-build/build-1'
SELECTED=MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2/source/xnu'
GUARDS=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',PYTHONDONTWRITEBYTECODE='1')
EXPECTED_RAW='01488b5be195fe61a0e0880c60b51190a7cb38c33dd0ba7af3d68ac22bc266b2'
EXPECTED_IMAGE='fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3'
EXPECTED_CANDIDATE='0bdfc24445a1a213790546a79a62975691c9ff334cd6bedb6f954859cf41f63e'

def sha(path):
 with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(data):return hashlib.sha256(data).hexdigest()
def require(ok,why):
 if not ok:raise ValueError(why)
def text(data):return data.split(b'\0',1)[0].decode('ascii')
def bounded(data,at,size):
 require(0<=at<=len(data)and 0<=size<=len(data)-at,'out-of-file extent')
 return data[at:at+size]
def u32(data,at):return struct.unpack('<I',bounded(data,at,4))[0]
def sx(value,bits):return value-(1<<bits)if value&(1<<(bits-1))else value

def macho(data,executable=True):
 require(32<=len(data)<=1024**2,'bounded Mach-O header/file size')
 magic,cpu,subtype,kind,ncmds,size,flags,reserved=struct.unpack_from('<8I',data)
 require((magic,cpu,subtype,kind,reserved)==(0xfeedfacf,0x100000c,0,2 if executable else 1,0),'ARM64_ALL thin Mach-O type')
 require(1<=ncmds<=32 and size<=len(data)-32,'load command bounds')
 require(flags==(1 if executable else 0x2000),'static/object flags')
 allowed={0x19,2,0x2a,5}if executable else {0x19,0x32,0x2e,2,0xb}
 segments=[];sections=[];symtab=None;thread=None;commands=[];at=32
 for unused in range(ncmds):
  cmd,length=struct.unpack('<II',bounded(data,at,8))
  require(length>=8 and length%8==0 and at+length<=32+size,'load command extent/alignment')
  require(cmd in allowed,'dynamic/unsupported load command')
  commands.append({'offset':at,'kind':cmd,'size':length})
  if cmd==0x19:
   _,_,name,va,vmsize,foff,fsize,maxprot,initprot,nsects,segflags=struct.unpack('<II16sQQQQiiII',bounded(data,at,72))
   require(length==72+80*nsects and va+vmsize<=1<<64 and fsize<=vmsize,'segment size/overflow')
   bounded(data,foff,fsize)
   if executable:require(va%16384==vmsize%16384==foff%16384==0 and initprot&maxprot==initprot and not(initprot&2 and initprot&4),'16KiB/perms segment')
   seg={'name':text(name),'va':va,'vmsize':vmsize,'fileoff':foff,'filesize':fsize,'maxprot':maxprot,'initprot':initprot,'command_offset':at}
   segments.append(seg)
   for index in range(nsects):
    pos=at+72+80*index
    name,sg,addr,count,off,align,reloff,nreloc,sflags,r1,r2,r3=struct.unpack('<16s16sQQIIIIIIII',bounded(data,pos,80))
    require(va<=addr and count<=va+vmsize-addr and foff<=off and count<=foff+fsize-off,'section VM/file extent')
    bounded(data,reloff,nreloc*8)
    require(align<=31 and off%(1<<align)==0,'section alignment')
    sections.append({'name':text(name),'segment':text(sg),'address':addr,'size':count,'offset':off,'reloff':reloff,'nreloc':nreloc,'header_offset':pos})
  elif cmd==2:
   require(length==24 and symtab is None,'single symbol table')
   _,_,so,nsyms,stro,strsize=struct.unpack('<6I',bounded(data,at,24));bounded(data,so,nsyms*16);strings=bounded(data,stro,strsize)
   require(strsize>0,'string table extent')
   symbols=[]
   for index in range(nsyms):
    pos=so+16*index;idx,ntype,nsect,desc,value=struct.unpack('<IBBHQ',bounded(data,pos,16))
    require(idx<strsize and b'\0'in strings[idx:],'symbol name extent')
    require(ntype&0xe not in (0,0xc),'undefined/prebound import')
    symbols.append({'name':text(strings[idx:]),'type':ntype,'section':nsect,'value':value,'offset':pos})
   symtab={'symbols':symbols,'command_offset':at}
  elif cmd==5:
   require(executable and thread is None and length==288,'one complete UNIXTHREAD')
   flavor,count=struct.unpack('<II',bounded(data,at+8,8));require((flavor,count)==(6,68),'ARM_THREAD_STATE64 flavor/count')
   state=bounded(data,at+16,272);pc=struct.unpack_from('<Q',state,256)[0]
   require(not any(state[:256])and not any(state[264:]),'zero initial regs/SP/CPSR, kernel default stack only')
   thread={'pc':pc,'sp':0,'command_offset':at}
  elif cmd==0xb:
   require(length==80 and u32(data,at+28)==0 and symtab is not None and u32(data,at+24)<=len(symtab['symbols']),'object undefined range empty')
  at+=length
 require(at==32+size and symtab is not None,'complete commands/symbols')
 byname={row['name']:row for row in sections};require(len(byname)==len(sections)and set(byname)=={'__text','__cstring','__const'},'actual three sections')
 if executable:
  require([s['name']for s in segments]==['__PAGEZERO','__TEXT','__LINKEDIT'],'three static segments')
  z,t,l=segments
  require((z['va'],z['vmsize'],z['fileoff'],z['filesize'],z['initprot'],z['maxprot'])==(0,1<<32,0,0,0,0),'hard 4GiB PAGEZERO')
  require((t['va'],t['vmsize'],t['fileoff'],t['filesize'],t['initprot'],t['maxprot'])==(1<<32,16384,0,16384,5,5),'RX TEXT mapping')
  require(l['initprot']==l['maxprot']==1 and l['fileoff']+l['filesize']==len(data),'readonly final LINKEDIT')
  for left,right in zip(segments,segments[1:]):require(left['va']+left['vmsize']<=right['va'],'VM overlap')
  require(thread is not None,'UNIXTHREAD entry required')
  sec=byname['__text'];pc=thread['pc']
  require(pc%4==0 and sec['address']<=pc<sec['address']+sec['size'],'entry inside aligned file-backed code')
  require(pc==sec['address'] and any(s['name']=='_start'and s['value']==pc for s in symtab['symbols']),'entry matches actual _start')
  require(not any(row['nreloc']for row in sections),'no linked unresolved relocations')
 return {'header_flags':flags,'commands':commands,'segments':segments,'sections':sections,'symtab':symtab,'thread':thread}

def machine(data,meta):
 sec=next(s for s in meta['sections']if s['name']=='__text');code=bounded(data,sec['offset'],sec['size'])
 require(len(code)%4==0,'ARM64 instruction width')
 words=list(struct.unpack('<'+'I'*(len(code)//4),code));svc=[i for i,w in enumerate(words)if w&0xffe0001f==0xd4000001]
 require(len(svc)==6 and all(words[i]==0xd4001001 for i in svc),'six genuine SVC #0x80')
 calls=[]
 for i in svc:
  require(words[i+1]&~31==0x9a9f37e0,'immediate CSET HS carry capture')
  carryreg=words[i+1]&31;require(carryreg not in [0,1,2,3,4,5,16],'early carry output aliases an input')
  movs=[((w>>5)&0xffff)for w in words[max(0,i-9):i]if w&0xffe0001f==0x52800010]
  require(bool(movs),'x16 syscall literal missing')
  calls.append({'instruction_index':i,'file_offset':sec['offset']+4*i,'syscall_number':movs[-1],'carry_register':carryreg})
 require([r['syscall_number']for r in calls]==[5,20,274,4,4,1],'selected direct syscall numbers/order')
 require(words[svc[2]-2]==0x52800161,'sysctl namelen is eleven, without null')
 loops=[]
 for call in calls:
  if call['syscall_number']!=4:continue
  i=call['instruction_index']
  require(0xaa0803e0 in words[i-7:i]and 0xaa0a03e1 in words[i-7:i],'fd x8 and preserved pointer x10 reloaded into x0/x1')
  require(words[i+2:i+7]==[0x8b00014a,0xf100017f,0xfa410808,0xfa40a040,0xcb000042],'pointer advance/carry/positive/bounds/remaining-count instructions')
  branch=words[i+7];require(branch&0xff00001f==0x54000002,'loop only branches HS after valid write')
  target=i+7+sx((branch>>5)&0x7ffff,19)
  require(target==i-7 and words[target]&0xff00001f==0xb4000002,'loop has zero-remaining exit before each SVC')
  loops.append({'svc_index':i,'backedge_target_index':target,'remaining_register':2,'preserved_pointer_register':10,'positive_progress_only':True})
 # Actual linker ADR+NOP relaxation must point to the intended literals.
 literals=[]
 expected=[(10,0,b'/dev/console\0'),(17,10,b'kern.ostype\0'),(72,10,b'\nVM002: guest identity checks failed\n\0'),(92,10,b'\nVM002: pid=1 ostype=Darwin owned-entry=v1\n\0')]
 text_segment=next(s for s in meta['segments']if s['name']=='__TEXT')
 for index,reg,string in expected:
  word=words[index];require(word&0x9f00001f==0x10000000|reg and words[index+1]==0xd503201f,'actual ADR/NOP static relaxation')
  imm=sx((((word>>5)&0x7ffff)<<2)|((word>>29)&3),21);target=sec['address']+4*index+imm
  off=text_segment['fileoff']+target-text_segment['va'];require(bounded(data,off,len(string))==string,'actual literal target differs')
  literals.append({'instruction_index':index,'register':reg,'target':target,'literal_sha256':digest(string)})
 require(words[-2:]==[0xd503203f,0x17ffffff],'post-exit EL0 YIELD loop')
 return {'calls':calls,'write_loops':loops,'literal_relocations':literals,'instruction_count':len(words),'words':words}

def source_contract(source):
 s=re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S);compact=re.sub(r'\s+','',s)
 for name,value in [('EXIT',1),('WRITE',4),('OPEN',5),('GETPID',20),('SYSCTLBYNAME',274)]:require(re.search(r'PID1_SYS_'+name+r'\s*=\s*'+str(value)+r'\b',s) is not None,'wrong source syscall '+name)
 for token in ['"+r"(x0)','"+r"(x1)','"+r"(x16)','"=&r"(error)','"memory","cc"','svc#0x80','cset%3,cs','sizeof(word)==8','sizeof(usize)==8']:require(token in compact,'source asm/type contract '+token)
 condition='if(!console.error&&console.value>=0&&!pid.error&&pid.value==1&&!os.error&&darwin)'
 require(condition in compact,'identity marker not gated by actual syscall results')
 require('size==7&&ostype[0]'in compact and 'ostype[6]==0'in compact,'exact returned Darwin string/length gate')
 require('if(r.error||r.value<=0||(usize)r.value>count)return0;'in compact and 'text+=(usize)r.value;count-=(usize)r.value;'in compact,'finite successful write progress')
 require('Darwin Kernel Version'not in source,'fabricated kernel banner')
 return True

def ir_contract(ir):
 calls=[line for line in ir.splitlines()if 'asm sideeffect'in line and 'svc'in line]
 require(len(calls)==6,'six actual volatile IR syscalls')
 for line in calls:
  for token in ['={x0}','={x1}','={x16}','=&r','{x2},{x3},{x4},{x5},{x0},{x1},{x16}','~{memory}','~{cc}']:
   require(token in line,'actual IR asm constraint '+token)
 require(ir.index('%11 = call')<ir.index('%13 = load i64')and 'icmp eq i64 %7, 1'in ir and 'br i1 %53, label %54, label %70'in ir,'identity memory loads and conditional verified edge')
 for count,result in [('56','61'),('73','78')]:
  require('icmp ugt i64 %'+result+', %'+count in ir and 'sub i64 %'+count+', %'+result in ir,'real IR loop bounds/progress')
 return calls

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();out=args.out.resolve();require(out.is_relative_to(ROOT/'docs/reviews/vm-034'),'review-only output prefix');out.mkdir(parents=True,exist_ok=False)
 report={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'summary':'Independent compiled PID1 ABI/artifact assessment; no real kernel exec/PID1/runtime acceptance','checks':[],'controls':[],'git_commands':[],'compiler_executed':False,'guest_executed':False,'main_source_written':False,'reviewer_sha256':sha(Path(__file__))}
 def check(name,ok,**facts):
  report['checks'].append({'name':name,'pass':bool(ok),**facts});require(ok,name)
 def reject(name,fn,data):
  try:fn(data)
  except (ValueError,UnicodeError,struct.error,KeyError)as e:report['controls'].append({'name':name,'pass':True,'input_sha256':digest(data.encode()if isinstance(data,str)else data),'reason':str(e)})
  else:raise ValueError('Mutation admitted: '+name)
 def git(*argv):
  result=subprocess.run(['git','-C',str(MAIN),*argv],env=GUARDS,capture_output=True,timeout=10)
  report['git_commands'].append({'argv':['git','-C',str(MAIN),*argv],'exit_code':result.returncode,'stdout_sha256':digest(result.stdout),'stderr_sha256':digest(result.stderr),'git_no_lazy_fetch':'1','git_optional_locks':'0'})
  require(result.returncode==0,'read-only pinned Git command');return result.stdout
 try:
  ledger=json.loads((MAIN/'state/lab.json').read_text());plan=next(x for x in ledger['experiments']if x['id']=='REVPID1-001');require(plan['status']=='planned'and plan['task']=='REV-026'and plan['owner']=='codex-review-pid1-20261106-ds','actual MAIN prospective review plan');report['planned_experiment']=plan
  require(sha(BUILD/'evidence.json')==EXPECTED_RAW,'raw build capsule hash');e=json.loads((BUILD/'evidence.json').read_text())
  check('actual-five-command-build',len(e['commands'])==5 and all(c['exit_code']==0 and c['outcome']=='pass'for c in e['commands']))
  check('all-owned-children-retired',all(not c['after']['owned_processes']for c in e['commands']))

  check('exact-recorded-recipes-and-cwd',all(c['argv']==p['argv']and c['cwd']==str(BASE)for c,p in zip(e['commands'],e['commands_planned'])))
  admissions=[]
  for c in e['commands']:
   samples=c['admission']['samples'];times=[datetime.datetime.fromisoformat(x['recorded_at'])for x in samples]
   good=c['admission']['admitted']and len(samples)==3 and all(x['MemAvailable_bytes']>=4*1024**3 for x in samples)
   good=good and all((b-a).total_seconds()>=1 for a,b in zip(times,times[1:]))and c['peak_total_owned_rss_bytes']<=256*1024**2
   admissions.append(good)
  check('actual-three-sample-one-second-admission-and-rss',all(admissions),commands=len(admissions))
  approval=Path(e['admission']['path']);check('actual-root-build-approval-hash',sha(approval)==e['admission']['sha256'])
  grant=json.loads(approval.read_text());check('actual-root-build-scope',grant['task']=='VM-034'and grant['owner']=='codex-guest-pid1-20261106-dr'and grant['max_jobs']==1 and grant['max_owned_rss_bytes']==256*1024**2 and grant['qemu_allowed']is False)
  plan_path=BASE/'artifacts/avf-guest-pid1-build/plan-1/plan.json';check('exact-before-build-source-plan',sha(plan_path)=='ffe6f8cc47732a52d2eefd2cc18a51335df427ef6c6460b254e0f97296d0445a')
  source_plan=json.loads(plan_path.read_text());build_plan=json.loads((BUILD/'plan.json').read_text());check('source-plan-unchanged-except-owned-output',all(source_plan[k]==build_plan[k]for k in ['canonical_recipe','implementation_sha256','bindings','tools']))
  handoff=json.loads((BUILD/'handoff-index.json').read_text())
  check('acyclic-handoff-index-hashes',all(sha(MAIN/row['path'])==row['sha256']for row in [handoff['raw_evidence'],handoff['candidate'],handoff['mockfs_provenance']]))
  provenance=json.loads((BUILD/'mockfs-provenance.json').read_text());check('mockfs-provenance-matches-exact-image-and-build',provenance['input_sha256']==EXPECTED_IMAGE and provenance['build_evidence']==handoff['raw_evidence'])

  for name,h in e['artifact_hashes'].items():check('build-artifact:'+name,sha(MAIN/name)==h)
  for name,row in e['bindings']['immutable_inputs'].items():check('pinned-input:'+name,sha(MAIN/name)==row['sha256'])
  for name,row in e['tools'].items():
   check('public-tool:'+name,sha(Path(row['path']))==row['sha256'])
   if 'report'in row:check('public-tool-report:'+name,sha(MAIN/row['report'])==row['report_sha256'])
  source=(BASE/'src/guest/avf-pid1/pid1.c').read_text();owned=BASE/'src/guest/avf-pid1/pid1.c';require(sha(owned)==e['bindings']['owned_source']['sha256'],'source matches actual compile input')
  for commit in ['0a60389','60afd5d','2b278bfad93de50f084a34e7c8f5983bea988eb1']:
   full=git('rev-parse',commit+'^{commit}').decode().strip();data=git('show',full+':src/guest/avf-pid1/pid1.c');check('source-commit:'+full,digest(data)==sha(owned))
   producer=git('show',full+':tools/build/avf_guest_pid1_build.py');check('producer-commit:'+full,digest(producer)==e['implementation_sha256'])
  require(sha(BUILD/'candidate.json')==EXPECTED_CANDIDATE and sha(BUILD/'pid1')==EXPECTED_IMAGE,'exact candidate descriptor/image')
  candidate=json.loads((BUILD/'candidate.json').read_text());require(candidate==e['candidate']and candidate['sha256']==EXPECTED_IMAGE and candidate['source_sha256']==sha(owned),'candidate graph')
  source_contract(source);ir=(BUILD/'pid1.ll').read_text();calls=ir_contract(ir)
  image=(BUILD/'pid1').read_bytes();obj=(BUILD/'pid1.o').read_bytes();meta=macho(image);ometa=macho(obj,False);code=machine(image,meta)
  osec=next(s for s in ometa['sections']if s['name']=='__text');tsec=next(s for s in meta['sections']if s['name']=='__text');ow=list(struct.unpack('<126I',bounded(obj,osec['offset'],osec['size'])))
  relocs=[struct.unpack('<iI',bounded(obj,osec['reloff']+8*i,8))for i in range(osec['nreloc'])];changed=[i*4 for i,(a,b)in enumerate(zip(ow,code['words']))if a!=b]
  check('only-eight-genuine-static-relocations-change-instructions',len(relocs)==8 and set(changed)=={a for a,w in relocs} and all(w>>28 in [3,4]for a,w in relocs),changed_instruction_offsets=changed,relocations=relocs)
  report['structure']=meta;report['actual_arm64']={k:v for k,v in code.items()if k!='words'};report['ir_syscalls']=calls
  frozen=json.loads((SELECTED.parents[1]/'prepared-component.json').read_text())['prepared_source_files'];extra={}
  for name in ['bsd/kern/kern_newsysctl.c','config/version.c','osfmk/arm64/locore.s','bsd/kern/kern_exit.c','bsd/kern/kern_sysctl.c']:
   require(sha(SELECTED/name)==frozen[name],'additional genuine source '+name);extra[name]=sha(SELECTED/name)
  report['additional_selected_sources']=extra
  check('selected-syscall-returns',all(s in (SELECTED/'bsd/dev/arm/systemcalls.c').read_text()for s in ['ss64->x[1] = 0;','ss64->x[1] = uthread->uu_rval[1];','ss64->cpsr |= PSR64_CF;']))
  # Source/IR changes preserve the file's general shape but must lose admission.
  reject('source-x1-input-only',source_contract,source.replace('"+r"(x1)','"r"(x1)'))
  reject('actual-legacy-x1-defect',source_contract,(MAIN/'src/virtualization/pid1.c').read_text())
  for name,a,b in [('source-no-memory','"memory", "cc"','"cc"'),('source-no-cc','"memory", "cc"','"memory"'),('source-carry-not-early','"=&r"(error)','"=r"(error)'),('source-wrong-getpid','PID1_SYS_GETPID=20','PID1_SYS_GETPID=21'),('source-unconditional-identity','if(!console.error && console.value>=0 && !pid.error && pid.value==1 && !os.error && darwin)','if(1)'),('source-zero-progress-allowed','r.value<=0','r.value<0')]:
   require(a in source,'mutation target present '+name);reject(name,source_contract,source.replace(a,b,1))
  require(source_contract('/* harmless reviewer whitespace */\n'+source),'equivalent source formatting accepted')
  reject('IR-x1-output-lost',ir_contract,ir.replace('={x1},','',1));reject('IR-memory-barrier-lost',ir_contract,ir.replace('~{memory}','',1))
  reject('IR-forced-identity',ir_contract,ir.replace('icmp eq i64 %7, 1','icmp eq i64 %7, 2'))
  def patch32(data,at,value):
   b=bytearray(data);struct.pack_into('<I',b,at,value);return bytes(b)
  def patch64(data,at,value):
   b=bytearray(data);struct.pack_into('<Q',b,at,value);return bytes(b)
  textoff=tsec['offset'];first=code['calls'][0]['instruction_index'];write=code['write_loops'][0]['svc_index'];thread=meta['thread']['command_offset'];pagezero=meta['segments'][0]['command_offset'];textcmd=meta['segments'][1]['command_offset']
  for name,data in [('wrong-SVC-immediate',patch32(image,textoff+first*4,0xd4001021)),('wrong-carry-condition',patch32(image,textoff+(first+1)*4,0x9a9f07ec)),('write-pointer-clobbered',patch32(image,textoff+(write-5)*4,0xaa0103e1)),('write-count-grows',patch32(image,textoff+(write+6)*4,0x8b000042)),('write-invalid-retry',patch32(image,textoff+(write+7)*4,code['words'][write+7]^1))]:
   reject(name,lambda b:machine(b,macho(b)),data)
  for name,data in [('wrong-cpu',patch32(image,4,0x1000007)),('arm64e-subtype',patch32(image,8,2)),('ELF-disguise',b'\x7fELF'+image[4:]),('dynamic-flags',patch32(image,24,5)),('bad-command-extent',patch32(image,36,0)),('dyld-command',patch32(image,meta['commands'][4]['offset'],0xe)),('wrong-thread-flavor',patch32(image,thread+8,1)),('wrong-thread-count',patch32(image,thread+12,67)),('custom-stack',patch64(image,thread+16+248,0x200000000)),('entry-in-pagezero',patch64(image,thread+16+256,0)),('unaligned-entry',patch64(image,thread+16+256,meta['thread']['pc']+1)),('small-pagezero',patch64(image,pagezero+32,4096)),('write-execute',patch32(patch32(image,textcmd+56,7),textcmd+60,7)),('undefined-symbol-despite-flag',image[:meta['symtab']['symbols'][0]['offset']+4]+b'\x01'+image[meta['symtab']['symbols'][0]['offset']+5:]),('truncated-linkedit',image[:-1])]:reject(name,macho,data)
  report['candidate']=candidate;report['candidate_descriptor_sha256']=EXPECTED_CANDIDATE;report['raw_build_evidence_sha256']=EXPECTED_RAW
  report['boundaries']={'compiled_source_abi_and_static_layout_only':True,'VM025_candidate_list_admitted':False,'VM024_packaging_performed':False,'real_PID1_syscall_console_stack_signing_kernel_execution_qualified':False,'actual_kernel_panic_PSCI_or_host_stop_qualified':False}
  report['outcome']='pass';report['summary']='Independent exact PID1 source/IR/ARM64/MachO compiled-ABI review PASS; genuine x0/x1/carry/memory and optimized loop progress, static image/relocations and narrow controls verified. No real kernel/PID1/stack/signing/console/stop runtime claim.'
 except (ValueError,KeyError,UnicodeError,struct.error,OSError,subprocess.SubprocessError)as error:report['error']=repr(error)
 report['current_image_memory']={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines()if line.startswith(('VmHWM:','VmRSS:'))}
 if report['current_image_memory']['VmHWM']>256*1024**2:report['outcome']='fail';report['resource_error']='current-image RSS budget exceeded'
 report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'outcome':report['outcome'],'error':report.get('error'),'checks':len(report['checks']),'controls':len(report['controls']),'memory':report['current_image_memory']},indent=2));return 0 if report['outcome']=='pass'else 1
if __name__=='__main__':raise SystemExit(main())
