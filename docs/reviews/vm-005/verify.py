#!/usr/bin/env python3
"""Independent exact-artifact/source audit and two small owned CPU replays."""
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,re,resource,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];LAB=ROOT.parents[1]
RUN=os.environ.get('S24_REVAVF_RUN','20261105-session1');assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-avf'/RUN;OUT.mkdir(parents=True,exist_ok=False)
(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
C='221923b2a7ee28bd2bb4c5f56a73a777a9d29476';ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
commands=[]
def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def run(argv,label):
 with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=ENV,timeout=10)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(LAB)),stderr=str((OUT/(label+'.stderr')).relative_to(LAB)),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']}))
 (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');assert r.returncode==0,(label,r.returncode)
 return (OUT/(label+'.stdout')).read_bytes()
def inspect_macho(p):
 data=p.read_bytes();magic,cpu,subtype,kind,count,cmdbytes,flags,reserved=struct.unpack_from('<8I',data)
 assert (magic,cpu,kind)==(0xfeedfacf,0x100000c,2) and 32+cmdbytes<=len(data)
 pos=32;segments=[];entry=None
 for _ in range(count):
  assert pos+8<=32+cmdbytes;cmd,n=struct.unpack_from('<II',data,pos);assert n>=8 and n%8==0 and pos+n<=32+cmdbytes
  assert cmd not in [0xc,0xe,0x80000018,0x8000001f]
  if cmd==0x19:
   assert n>=72;name,va,vm,off,size,maxprot,initprot,nsects,sflags=struct.unpack_from('<16s4Q4I',data,pos+8)
   assert size<=vm and off+size<=len(data) and n>=72+80*nsects
   if vm:segments.append(dict(name=name.split(b'\0')[0].decode(),va=va,vm=vm,off=off,size=size,initprot=initprot))
  if cmd==5:
   assert n==288 and struct.unpack_from('<II',data,pos+8)==(6,68)
   registers=struct.unpack_from('<34Q',data,pos+16);entry=registers[32]
  pos+=n
 assert pos==32+cmdbytes and entry and min(x['va'] for x in segments)==0xfffffff007000000
 ordered=sorted(segments,key=lambda x:x['va'])
 for a,b in zip(ordered,ordered[1:]):assert a['va']+a['vm']<=b['va']
 assert any(x['va']<=entry<x['va']+x['vm'] and x['initprot']&4 for x in segments)
 entry_pa=0x40000000+(entry-0xfffffff004000000);high=max(0x40000000+x['va']-0xfffffff004000000+x['vm'] for x in segments)
 dt=(high+16383)//16384*16384
 return dict(entry_va=entry,entry_pa=entry_pa,dt_pa=dt,bootargs_pa=dt+65536,top=dt+65536+16384,segments=segments,sha256=sha(p))
def inspect_dtb(p):
 d=p.read_bytes();h=struct.unpack_from('>10I',d);assert h[0]==0xd00dfeed and h[1]==len(d)
 start,strings=h[2],h[3];limit=start+h[9];assert limit<=len(d) and strings+h[8]<=len(d)
 s=d[strings:strings+h[8]];pos=start;stack=[];props={};ended=False
 while pos<limit:
  t=struct.unpack_from('>I',d,pos)[0];pos+=4
  if t==1:
   end=d.index(0,pos,limit);stack.append(d[pos:end].decode());pos=(end+4)&~3
  elif t==2:assert stack;stack.pop()
  elif t==3:
   assert stack and pos+8<=limit;length,key=struct.unpack_from('>II',d,pos);pos+=8;assert key<len(s) and pos+length<=limit
   end=s.index(0,key);props[('/'+'/'.join(stack[1:]),s[key:end].decode())]=d[pos:pos+length];pos+=(length+3)&~3
  elif t==4:pass
  elif t==9:assert not stack;ended=True;break
  else:raise ValueError(t)
 assert ended
 assert struct.unpack('>QQ',props[('/memory@40000000','reg')])==(0x40000000,0x10000000)
 assert struct.unpack('>QQ',props[('/pl011@9000000','reg')])[0]==0x9000000
 assert struct.unpack('>4Q',props[('/intc@8000000','reg')])[::2]==(0x8000000,0x80a0000)
 assert props[('/psci','method')]==b'hvc\0'
 return dict(sha256=sha(p),properties=len(props),initrd_start=int.from_bytes(props[('/chosen','linux,initrd-start')],'big'),initrd_end=int.from_bytes(props[('/chosen','linux,initrd-end')],'big'))
def payload(image,command,destination):
 entries=[]
 for name,data in [(b'kernel',image),(b'cmdline',command.encode()+b'\0')]:
  entries.append(name.ljust(16,b'\0')+struct.pack('<II',len(data),0)+data+bytes((-len(data))%16))
 body=b''.join(entries)+bytes(24);destination.write_bytes(struct.pack('<II',0x50554e58,len(body))+body)
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(),summary='Independent VM-005 source/address/provenance review and bounded actual synthetic CPU reproduction',commit=C,commands=commands,xnu_executed=False,pid1_executed=False,ios_executed=False,native_phone_executed=False)
try:
 candidate={}
 for i,f in enumerate(['tools/verify/avf_handoff.py','fixtures/public/avf-handoff/synthetic.c','fixtures/public/avf-handoff/inputs.json','docs/procedures/avf-handoff/README.md','docs/procedures/avf-handoff/experiment.md','docs/procedures/avf-handoff/binding-controls.md']):
  data=run(['git','show',C+':'+f],'candidate-'+str(i));p=OUT/'candidate'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);candidate[f]=sha(p)
 metadata=run(['git','rev-parse','bcc6437'],'metadata-commit').decode().strip();capsules=[]
 for i,name in enumerate(['evidence.json','evidence-bindings.json']):
  p=LAB/'docs/procedures/avf-handoff'/name;assert run(['git','show',metadata+':docs/procedures/avf-handoff/'+name],'capsule-'+str(i))==p.read_bytes()
  e=json.loads(p.read_text());assert e['commit']==C and e['outcome']=='pass';idx=e['artifact_sha256_index'];assert sha(LAB/idx['path'])==idx['sha256']
  index=json.loads((LAB/idx['path']).read_text())
  for path,h in index.items():assert sha(LAB/path)==h,path
  capsules.append(dict(path=str(p.relative_to(LAB)),sha256=sha(p),artifact_index_count=len(index)))
 evidence=json.loads((LAB/'docs/procedures/avf-handoff/evidence.json').read_text());pro=evidence['provenance'];pin=pro['pin']
 qemu=Path(pro['qemu']);shim=Path(pro['shim']);assert sha(qemu)==pin['qemu_sha256'] and sha(shim)==pin['shim_sha256']
 for path,h in pro['build_reports_and_source_manifest'].items():assert sha(path)==h
 builds=[json.loads(Path(x).read_text()) for x in pro['build_reports_and_source_manifest']]
 shim_build=next(x for x in builds if 'donor_commit' in x);qemu_build=next(x for x in builds if 'binary_sha256' in x)
 assert shim_build['donor_commit']==pin['scion_commit'] and qemu_build['pin']['commit']==pin['qemu_commit'] and qemu_build['binary_sha256']==sha(qemu)
 sources={}
 for i,(f,h) in enumerate(pro['source_sha256'].items()):
  if f.startswith('qemu/'):
   source=LAB/'worktrees/vm-004-20261105/artifacts/qemu-host/release-10.2.0/source/qemu-10.2.0'/f[5:];assert sha(source)==h;data=source.read_bytes()
  else:
   data=run(['git','-C',LAB/'references/scion-avf','show',pin['scion_commit']+':'+f],'scion-'+str(i));assert hashlib.sha256(data).hexdigest()==h
  p=OUT/'sources'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);sources[f]=sha(p)
 final=LAB/'worktrees/vm-005-20261105/artifacts/avf-handoff/run-final-221923b';r=json.loads((final/'report.json').read_text());assert r['commit']==C and r['outcome']=='pass'
 assert pro['fixture_source_sha256']==candidate['fixtures/public/avf-handoff/synthetic.c']
 for case in r['cases']:
  assert case['outcome']=='pass' and not any(x['state']!='Z' for x in case['run']['after']['owned_processes'])
  assert sha(final/(case['name']+'.log'))==case['console_sha256']
  assert case['run']['timeout_seconds']<=5 and case['run']['peak_total_owned_rss_bytes']<=512*1024**2
 normal=final/'normal.macho';spin=final/'spin.macho';m=inspect_macho(normal);ms=inspect_macho(spin)
 assert m['entry_pa']==r['synthetic_macho']['normal']['entry_pa'] and m['sha256']==r['synthetic_macho']['normal']['sha256']
 assert ms['sha256']==r['synthetic_macho']['spin']['sha256'];dtb=inspect_dtb(final/'qemu.dtb')
 llvm=Path('/home/egor/.local/bin/clang').resolve().parent/'llvm-readobj';run([llvm,'--file-headers','--sections','--symbols',normal],'independent-macho-tool')
 supervisor_path=ROOT/'tools/build/qemu_host.py';assert sha(supervisor_path)==pro['supervisor_sha256']
 spec=importlib.util.spec_from_file_location('review_qualified_cleanup',supervisor_path);supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
 cases=[]
 for name,cookie in [('positive',pin['command_cookie']),('cookie-suffix',pin['command_cookie']+'evil')]:
  image=OUT/(name+'.xnup');payload(normal.read_bytes(),'cpus=1 console_quiet=0 '+cookie,image)
  argv=[str(qemu),'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',str(shim),'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot','-initrd',str(image)]
  started=time.monotonic();record=dict(argv=argv,cwd=str(ROOT),timeout_seconds=5,guest_ram_mib=256,environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']});peak=0
  def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  with (OUT/(name+'.console')).open('xb') as log,(OUT/(name+'.samples.jsonl')).open('x') as samples:
   proc=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits,env=ENV);record['owned_session']=proc.pid
   try:
    while proc.poll() is None:
     snap=supervisor.sample(proc.pid);own=int(Path('/proc/self/statm').read_text().split()[1])*resource.getpagesize();snap['reviewer_rss_bytes']=own;snap['total_owned_rss_bytes']=own+snap['owned_tree_rss_bytes'];peak=max(peak,snap['total_owned_rss_bytes']);samples.write(json.dumps(snap)+'\n');samples.flush()
     if peak>512*1024**2:raise RuntimeError('512MiB RSS exceeded')
     if time.monotonic()-started>=5:raise TimeoutError('5s guest deadline')
     time.sleep(.02)
    record['exit_code']=proc.wait(timeout=2)
   finally:
    if proc.poll() is None or any(x['state']!='Z' for x in supervisor.sample(proc.pid)['owned_processes']):supervisor.terminate(proc)
    until=time.monotonic()+2;after=supervisor.sample(proc.pid)
    while any(x['state']!='Z' for x in after['owned_processes']) and time.monotonic()<until:time.sleep(.02);after=supervisor.sample(proc.pid)
    record.update(elapsed_seconds=time.monotonic()-started,peak_total_owned_rss_bytes=peak,after=after);(OUT/(name+'.run.json')).write_text(json.dumps(record,indent=2)+'\n')
    assert not any(x['state']!='Z' for x in after['owned_processes'])
  console=(OUT/(name+'.console')).read_text();assert record['exit_code']==0 and 'VM005 SYNTHETIC ENTER' in console and 'VM005 SYNTHETIC PSCI_SYSTEM_OFF' in console
  if name=='positive':
   found=re.search(r'VM005 SYNTHETIC PASS entry=(0x\w+) ba=(0x\w+) dt=(0x\w+) mem=(0x\w+) psci=(0x\w+)',console);assert found
   assert tuple(int(found[i],16) for i in range(1,6))==(m['entry_pa'],m['bootargs_pa'],m['dt_pa'],0xe000000,0x10001)
  else:assert 'VM005 SYNTHETIC PASS' not in console and 'VM005 SYNTHETIC REJECT command-cookie' in console
  record['console_sha256']=sha(OUT/(name+'.console'));record['payload_sha256']=sha(image);record['outcome']='pass';cases.append(record)
  commands.append(record);(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 assert sha(qemu)==pin['qemu_sha256'] and sha(shim)==pin['shim_sha256']
 report.update(outcome='pass',summary='Independent source/artifact/MachO/DTB audit and actual positive plus cookie-suffix rejection CPU replays passed; no actionable finding within synthetic fixture scope',metadata_commit=metadata,source_inputs=candidate,primary_inputs=sources,implementation_capsules=capsules,independent_macho=m,independent_dtb=dtb,cases=cases,tools={str(llvm):sha(llvm),str(qemu):sha(qemu),str(shim):sha(shim),str(supervisor_path):sha(supervisor_path)},checks=[dict(name=x,pass_check=True) for x in ['exact-code-and-final-metadata-bindings','143-artifact-index-hashes','pinned-source-and-qualified-build-identities','independent-MachO-thread-state-segment-entry-addresses','independent-real-QEMU-DTB-properties','actual-positive-CPU-PSCI-natural-exit','actual-cookie-prefix-collision-rejection','bounded-resources-and-no-live-owned-survivors']])
except Exception as error:report['error']=repr(error)
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(LAB)))))
raise SystemExit(report['outcome']!='pass')
