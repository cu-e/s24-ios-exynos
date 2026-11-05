#!/usr/bin/env python3
"""Independent exact-source/corpus/artifact and focused RSA host review; no QEMU."""
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,re,resource,subprocess,sys,time,zipfile,struct,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];IMPL=MAIN/'worktrees/krn-035-20261105'
CODE='a81876609fa33928f0c415f6a7d4b30013ed9ef6';META='3d84d9d4d3ac6927045f77d0a22eada97f71d726';XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1'}
RUN=os.environ.get('S24_REVRSA_RUN','20261105-session1');assert re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-rsa'/RUN;OUT.mkdir(parents=True,exist_ok=False);(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes());commands=[]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path

def source_run(argv,label):
 a=OUT/(label+'.stdout');b=OUT/(label+'.stderr')
 with a.open('xb') as f,b.open('xb') as g:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=f,stderr=g,env=ENV,timeout=20)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str(a.relative_to(MAIN)),stderr=str(b.relative_to(MAIN)),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE']}));assert r.returncode==0,label
 return a.read_bytes()
def git(repo,spec,label):return source_run(['git','-C',repo,'show',spec],label)
def path_for(name):
 p=Path(name);return p if p.is_absolute() else (MAIN if str(p).startswith('worktrees/') else IMPL)/p

def der(tag,payload):
 assert len(payload)<128
 return bytes([tag,len(payload)])+payload
def encoded(k,oid,hashed,parameters=True):
 info=hashed if oid is None else der(0x30,der(0x30,oid+(b'\x05\0' if parameters else b''))+der(4,hashed))
 if k<len(info)+11:return None
 return b'\0\1'+b'\xff'*(k-len(info)-3)+b'\0'+info

def independent_primary(z,name):
 state={};rows=[];excluded=[];ordinal=0;odd_signatures=[]
 # State intentionally persists key parameters across records, as original RSP does.
 for text in z.read(name).decode('ascii').splitlines():
  line=text.strip()
  if not line or line.startswith('#'):continue
  if line.startswith('[mod = '):state={};continue
  if '=' not in line:continue
  field,value=map(str.strip,line.split('=',1));state[field]=value
  if field!=('Result' if name.startswith('SigVer') else 'S'):continue
  ordinal+=1;expect=state.get('Result','P').startswith('P')
  if len(state['Msg'])%2:
   assert not expect;excluded.append(dict(source=name,record=ordinal,expected=False,reason='Odd hex digit count in octet field;no invented nibble/bit hashing semantics',fields=['Msg']));continue
  algorithm={'SHA512224':'SHA512/224','SHA512256':'SHA512/256'}.get(state['SHAAlg'],state['SHAAlg'])
  digest_name={'SHA1':'sha1','SHA224':'sha224','SHA256':'sha256','SHA384':'sha384','SHA512':'sha512','SHA512/224':'sha512_224','SHA512/256':'sha512_256'}[algorithm]
  oid={'SHA1':'06052b0e03021a','SHA224':'0609608648016503040204','SHA256':'0609608648016503040201','SHA384':'0609608648016503040202','SHA512':'0609608648016503040203','SHA512/224':'0609608648016503040205','SHA512/256':'0609608648016503040206'}[algorithm]
  n=int(state['n'],16);e=int(state['e'],16);s=int(state['S'],16);k=(n.bit_length()+7)//8
  sb=s.to_bytes(max(k,(s.bit_length()+7)//8),'big');message=bytes.fromhex(state['Msg']);h=hashlib.new(digest_name,message).digest()
  # Integer-to-octet serialization is modulus width, not a guessed message nibble.
  row=dict(source=name,algorithm=algorithm,n=state['n'],e=state['e'],signature=sb.hex(),oid=oid,hash=h.hex(),expected=expect,message_sha256=digest(message))
  for f in ['n','e']:
   if len(row[f])%2:row[f]='0'+row[f]
  if len(state['S'])%2:odd_signatures.append(dict(source=name,record=ordinal,published_hex_digits=len(state['S']),octets=len(sb),expected=expect,signature_sha256=digest(sb)))
  rows.append(row)
 return rows,excluded,odd_signatures

def public_oracle(row):
 n=int(row['n'],16);e=int(row['e'],16);s=int(row['signature'],16);k=(n.bit_length()+7)//8
 if len(bytes.fromhex(row['signature']))!=k or s>=n:return False
 raw=pow(s,e,n).to_bytes(k,'big');oid=bytes.fromhex(row['oid']) if row['oid'] else None;h=bytes.fromhex(row['hash'])
 return raw in [encoded(k,oid,h,True),encoded(k,oid,h,False)]

report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(),commit=CODE,metadata_commit=META,experiment='REVRSA-001',commands=commands,QEMU_executed_by_reviewer=False,provider_registered=False,native_device=False,FIPS_qualified=False,private_ABI_qualified=False,summary='Independent RSA canonical-source/corpus/artifact and focused sanitized host review')
try:
 ledger=json.loads((MAIN/'state/lab.json').read_text());experiments=ledger['experiments'];experiments=experiments.values() if isinstance(experiments,dict) else experiments
 plan=next(x for x in experiments if x['id']=='REVRSA-001');assert plan['task']=='REV-019' and plan['owner']=='codex-team-review-rsa-20261105-cf' and plan['status']=='planned';save(OUT/'actual-plan.json',json.dumps(plan,indent=2).encode()+b'\n')
 names=source_run(['git','ls-tree','-r','--name-only',CODE,'--','src/platform/crypto/rsa'],'owned-files').decode().splitlines();inputs={}
 for i,name in enumerate(names):
  p=save(OUT/'candidate'/name,git(ROOT,CODE+':'+name,'owned-'+str(i)));inputs[name]=sha(p)
 src=OUT/'candidate/src/platform/crypto/rsa';vendor=src/'vendor';prov=json.loads((vendor/'provenance.json').read_text());canonical={}
 bear_repo=MAIN/'worktrees/krn-028-20261105/tools/research/crypto-candidates/local/bearssl.git'
 for i,(name,row) in enumerate(prov['files'].items()):
  data=git(bear_repo,prov['revision']+':'+name,'bear-'+str(i));assert digest(data)==row['sha256']==sha(vendor/name) and len(data)==row['bytes'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['git_blob'];canonical[name]=dict(bytes=len(data),sha256=digest(data),git_blob=row['git_blob'])
 assert len(canonical)==33
 qraw=git(ROOT,META+':docs/procedures/crypto-rsa/qualified-evidence.json','qualified-capsule');q=json.loads(qraw);assert q['commit']==CODE and q['outcome']=='pass' and len(q['compiled_git_bindings'])==41
 assert qraw==(IMPL/'docs/procedures/crypto-rsa/qualified-evidence.json').read_bytes()
 for name,h in q['compiled_git_bindings'].items():assert inputs[name]==h,name
 stages={};artifact_count=0;stage_facts=[]
 for name,h in q['prior_actual_stage_capsules'].items():
  p=MAIN/name;assert sha(p)==h;stage=json.loads(p.read_text());stages[p.parent.name]=stage
  for f,expected in stage['artifact_hashes'].items():assert sha(path_for(f))==expected,f;artifact_count+=1
  for c in stage['commands']:
   if 'after' in c:assert not any(x['state']!='Z' for x in c['after']['owned_processes'])
   else:assert c['argv'][0]=='git' and c['exit_code']==0
  stage_facts.append(dict(path=name,sha256=h,outcome=stage['outcome'],commands=len(stage['commands']),artifacts=len(stage['artifact_hashes']),error=stage.get('error')))
 host=stages['host-build-session3'];build=stages['finish-session2'];cpu=stages['cpu-session1']
 owner_plans=[]
 owner_experiments=ledger['experiments'];owner_experiments=owner_experiments.values() if isinstance(owner_experiments,dict) else owner_experiments
 owner_experiments={x['id']:x for x in owner_experiments if x['id'].startswith('RSACOMP-')}
 for stage_name,experiment in [('host-build-session3','RSACOMP-003'),('finish-session2','RSACOMP-005'),('cpu-session1','RSACOMP-006')]:
  planned=owner_experiments[experiment];assert planned['task']=='KRN-035' and planned['owner']=='codex-team-crypto-rsa-20261105-bv'
  started=min(c['started_at'] for c in stages[stage_name]['commands'] if 'started_at' in c);assert datetime.fromisoformat(planned['created_at'])<datetime.fromisoformat(started)
  owner_plans.append(dict(id=experiment,created_at=planned['created_at'],first_bounded_command=started,evidence=planned['evidence']))
 save(OUT/'owner-plans.json',json.dumps(owner_plans,indent=2).encode()+b'\n')
 assert host['host_vectors']==491 and host['host_checks']==782365 and host['outcome']=='fail' and 'link' in host['error'].lower()
 assert build['outcome']=='pass' and cpu['outcome']=='pass' and cpu['arm_checks']==782365 and cpu['observed_stack_bytes']==10604
 assert all(x['detected'] for x in host['sanitizer_controls']) and all(x['accepted'] for x in cpu['guest_cases'])
 for name,h in cpu['owned_source_hashes'].items():
  if Path(name).suffix in ['.c','.h']:assert inputs[name]==h
 selected={};xnu=MAIN/'references/apple-xnu'
 for i,(name,h) in enumerate(build['canonical_selected_headers'].items()):
  raw=git(xnu,XNU+':'+name,'header-'+str(i));assert digest(raw)==h==sha(xnu/name);save(OUT/'selected-xnu'/name,raw);selected[name]=h
 for i,name in enumerate(['libkern/crypto/corecrypto_rsa.c','bsd/kern/chunklist.c','libkern/libkern/crypto/rsa.h','libkern/libkern/crypto/crypto_internal.h','bsd/sys/cdefs.h']):
  raw=git(xnu,XNU+':'+name,'consumer-'+str(i));assert sha(xnu/name)==digest(raw);save(OUT/'selected-xnu'/name,raw);selected[name]=digest(raw)
 cdefs=(OUT/'selected-xnu/bsd/sys/cdefs.h').read_text();start=cdefs.index('#if __has_attribute(enum_extensibility)');end=cdefs.index('\n#if XNU_KERNEL_PRIVATE',start)
 macros=save(OUT/'host-compiler-macros.h',('/* Exact selected BSD compiler enum macros, host only. */\n'+cdefs[start:end]+'\n').encode())
 corpus=json.loads((src/'testdata/vectors.json').read_text());archive=Path(corpus['archive']);assert sha(archive)==corpus['archive_sha256']=='8405aeb3572a4f98ed4b1a3ccb3f2f49e725462dd28ec4759d6a15d88855d19c'
 primary=[];excluded=[];odd_signatures=[];member_facts={}
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for name,row in corpus['members'].items():
   raw=z.read(name);assert digest(raw)==row['sha256'] and len(raw)==row['bytes'];member_facts[name]=dict(bytes=len(raw),sha256=digest(raw));r,e,o=independent_primary(z,name);primary+=r;excluded+=e;odd_signatures+=o
  # Read transient published TEST exponent; serialize only newly derived public cases.
  key={}
  for line in z.read('SigGen15_186-3.txt').decode('ascii').splitlines():
   if '=' in line and not line.startswith('#'):
    a,b=map(str.strip,line.split('=',1));key[a]=b
   if all(x in key for x in ['n','e','d']):break
 assert len(primary)==481 and primary==corpus['rows'][:481] and excluded==corpus['excluded'] and len(excluded)==17
 assert all(public_oracle(row)==row['expected'] for row in corpus['rows'])
 assert len(corpus['rows'])==491 and all(row['source'].startswith('independent-') for row in corpus['rows'][481:])
 assert any(x['expected'] and x['published_hex_digits']==511 for x in odd_signatures)
 # Small selected source cases plus independently encoded OID/digest boundaries.
 chosen=[next(x for x in primary if x['expected'] and x['algorithm']=='SHA256')]
 odd=next(x for x in odd_signatures if x['expected'] and x['published_hex_digits']==511)
 # Ordinal is in the original source, including any excluded records.
 original_positive=next(x for x in primary if digest(bytes.fromhex(x['signature']))==odd['signature_sha256'])
 chosen.append(original_positive)
 chosen.extend(x for x in corpus['rows'][481:] if x['case'] in ['valid-raw36','max-public-exponent','wrong-type'])
 cases=[dict(x,status='CCERR_OK',valid=x['expected']) for x in chosen]
 n,e,d=(int(key[k],16) for k in ['n','e','d']);k=(n.bit_length()+7)//8
 for label,oid,h,params in [('oid32-digest64',bytes([6,32])+bytes([43])*32,bytes(range(64)),True),('oid1-no-parameters',bytes([6,1,43]),bytes(range(64)),False),('oid-multibyte-subidentifier',bytes([6,4,43,129,128,1]),bytes(range(32)),True),('raw64',None,bytes(range(64)),True)]:
  em=encoded(k,oid,h,params);s=pow(int.from_bytes(em,'big'),d,n);assert pow(s,e,n).to_bytes(k,'big')==em
  row=dict(case=label,source='independent-review-RFC8017-integer-control',n=n.to_bytes(k,'big').hex(),e=e.to_bytes((e.bit_length()+7)//8,'big').hex(),signature=s.to_bytes(k,'big').hex(),oid=oid.hex() if oid else None,hash=h.hex(),expected=True,status='CCERR_OK',valid=True);cases.append(row)
 # Contract-invalid DER never reaches arithmetic, distinct from invalid signatures.
 for label,oid in [('OID33',bytes([6,33])+bytes([43])*33),('OID-empty',bytes([6,0])),('OID-long-length',bytes([6,128])+bytes(128)),('OID-leading-zero-group',bytes([6,2,128,1])),('OID-unfinished',bytes([6,2,43,129])),('OID-wrong-tag',bytes([5,1,43]))]:
  cases.append(dict(cases[0],case=label,oid=oid.hex(),expected=False,status='CCERR_PARAMETER',valid=False))
 save(OUT/'public-focused-cases.json',json.dumps(cases,indent=2).encode()+b'\n')
 arr=lambda h:'{'+','.join(map(str,bytes.fromhex(h)))+'}' if h else '{0}'
 header='struct review_case {unsigned n_len,e_len,sig_len,oid_len,hash_len; int status,valid; unsigned char n[512],e[512],sig[512],oid[130],hash[64];};\nstatic const struct review_case review_cases[]={\n'
 for row in cases:
  fields=['n','e','signature','oid','hash'];values=[row[f] for f in fields];header+='{'+','.join([*[str(len(bytes.fromhex(v))) if v else '0' for v in values],row['status'],str(int(row['valid'])),*[arr(v) for v in values]])+'},\n'
 save(OUT/'review_cases.h',(header+'};\n').encode());save(OUT/'host.c',(ROOT/'docs/reviews/krn-035/host.c').read_bytes())
 # Inspect genuine native objects, not published string claims, and exclude CPU helper.
 sys.path.insert(0,str(ROOT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 native_defined=set();native_undefined=set()
 for row in q['native_component_objects']:
  p=path_for(row['path']);assert sha(p)==row['sha256'] and 'synthetic_mem' not in row['source']
  for symbol in ObjectData(p).symbols:
   if symbol['kind']&1:
    if symbol['kind']&0x0e==0x0e:native_defined.add(symbol['name'])
    elif symbol['kind']&0x0e==0:native_undefined.add(symbol['name'])
 imports=sorted(native_undefined-native_defined);assert imports==q['native_unresolved_imports'] and len(q['native_component_objects'])==19
 assert not any(any(bad in s for bad in ['malloc','calloc','realloc','_free','_alloc']) for s in imports)
 layout=ObjectData(path_for(q['native_component_objects'][0]['path'])).value('_s24_rsa_layout','<8Q');assert list(layout)==q['target_layout']==[1584,8,64,8,24,24,1568,24]
 for path,h in cpu['avf_inputs']['reports'].items():assert sha(path)==h
 for field in ['qemu','shim']:assert sha(cpu['avf_inputs'][field])==cpu['avf_inputs']['pin'][field+'_sha256']
 consoles={}
 for case in cpu['guest_cases']:
  p=IMPL/'artifacts/crypto-rsa/cpu-session1'/(case['name']+'.log');assert sha(p)==case['console_sha256'];consoles[case['name']]=p.read_text()
 assert 'RSA ARM PASS checks=0xbf01d failure_line=0x0 stack_used=0x296c' in consoles['positive']
 assert f"entry={hex(build['images']['normal']['entry_pa'])} ba={hex(build['images']['normal']['bootargs_pa'])}" in consoles['positive']
 assert 'RSA ARM FAIL' in consoles['corrupt-signature'] and 'RSA ARM PASS' not in consoles['corrupt-signature']
 assert 'RSA ARM PASS' not in consoles['wrong-cookie'] and 'SPIN' in consoles['spin-timeout']
 assert cpu['commands'][0]['outcome']=='pass' and cpu['commands'][0]['exit_code']==0 and 'PSCI_SYSTEM_OFF' in consoles['positive']
 assert cpu['commands'][1]['outcome']=='pass' and 'REJECT command-cookie' in consoles['wrong-cookie']
 assert cpu['commands'][2]['outcome']=='pass' and 'PSCI_SYSTEM_OFF' in consoles['corrupt-signature']
 assert cpu['commands'][3]['outcome']=='timeout' and 'terminating on signal 15' in consoles['spin-timeout']
 # Independently parse the actual XNUP records, not just owner JSON acceptance.
 payload_facts={}
 for case in cpu['guest_cases']:
  raw=(IMPL/'artifacts/crypto-rsa/cpu-session1'/(case['name']+'.xnup')).read_bytes();magic,length=struct.unpack_from('<II',raw);assert magic==0x50554e58 and length==len(raw)-8;at=8;parts={}
  while at<len(raw):
   name,size,reserved=struct.unpack_from('<16sII',raw,at);at+=24;assert reserved==0 and size<=len(raw)-at;name=name.rstrip(b'\0').decode()
   if not name:assert size==0 and at==len(raw);break
   assert name not in parts;parts[name]=raw[at:at+size];at+=size+(-size%16)
  assert at==len(raw) and set(parts)=={'kernel','cmdline'}
  mode='spin' if case['name']=='spin-timeout' else 'normal';original=(IMPL/'artifacts/crypto-rsa/finish-session2'/(mode+'.macho')).read_bytes();assert digest(original)==build['images'][mode]['sha256']
  if case['name']=='corrupt-signature':
   first=next(x for x in corpus['rows'] if x['expected']);pattern=bytes.fromhex(first['signature']);assert original.count(pattern)==1;offset=original.index(pattern);mutated=bytearray(original);mutated[offset]^=1;assert parts['kernel']==bytes(mutated) and offset==cpu['corrupt_control']['offset']
  else:assert parts['kernel']==original
  expected_cookie=b'cpus=1 xts_cookie='+ (b'wrong' if case['name']=='wrong-cookie' else b'owned-adapter-v1');assert parts['cmdline'].rstrip(b'\0')==expected_cookie
  payload_facts[case['name']]=dict(sha256=digest(raw),kernel_sha256=digest(parts['kernel']),cmdline=parts['cmdline'].rstrip(b'\0').decode())
 shared=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2';xr=json.loads((shared/'evidence.json').read_text());assert sha(shared/'evidence.json')=='c5064a512ba295d1cd447af1e73ac6fc4f9c0ffeaf5b78f09ca0f80fc1f6216c'
 for f in ['host-adapter.o','host-aes.o']:assert sha(shared/f)==xr['artifact_hashes']['artifacts/crypto-xts/final-commit2/'+f]
 for name,h in build['dependency_hashes'].items():
  if '/src/platform/crypto/xts/' in name:assert sha(name)==h
 report.update(source_audit_passed_before_compile=True,source_inputs=inputs,canonical_bearssl=dict(repository=prov['repository'],revision=prov['revision'],members=canonical),selected_xnu=selected,qualified_capsule=dict(commit=CODE,metadata_commit=META,sha256=digest(qraw),stage_capsules=stage_facts,artifact_hash_records=artifact_count),corpus=dict(primary=len(primary),independent=10,unresolved_odd_nibble_messages=excluded,odd_integer_signatures=odd_signatures,archive_sha256=sha(archive),members=member_facts),native=dict(layout=list(layout),objects=19,imports=imports,allocating_imports=False,synthetic_memset_in_production=False),owner_plans=owner_plans,final_cpu=dict(arm_checks=cpu['arm_checks'],observed_stack_bytes=cpu['observed_stack_bytes'],guest_cases=cpu['guest_cases'],commands=cpu['commands'],payload_facts=payload_facts))
 report['prior_review_attempts']=[dict(path=str(p.relative_to(MAIN)),sha256=sha(p),outcome=json.loads(p.read_text())['outcome'],error=json.loads(p.read_text()).get('error')) for p in sorted((ROOT/'artifacts/rev-rsa').glob('*/evidence.json')) if p.parent!=OUT]
 save(OUT/'source-audit-before-host.json',json.dumps({k:v for k,v in report.items() if k not in ['commands']},indent=2).encode()+b'\n')
 # Only the bounded host compiler/fixture below execute; never launch a guest.
 spec=importlib.util.spec_from_file_location('rsa_review_cleanup',ROOT/'tools/build/qemu_host.py');sup=importlib.util.module_from_spec(spec);spec.loader.exec_module(sup)
 def bounded(argv,label):
  before=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
  if before<4*1024**2:raise RuntimeError('RESOURCE_DEFERRED before '+label+': '+str(before)+' KiB; no compiler/test started')
  start=time.monotonic();record=dict(argv=list(map(str,argv)),cwd=str(ROOT),MemAvailable_before_KiB=before,timeout_seconds=45,rss_budget_mib=256);peak=0
  def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  env={**ENV,'ASAN_OPTIONS':'halt_on_error=1:detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'}
  with (OUT/(label+'.log')).open('xb') as log,(OUT/(label+'.samples.jsonl')).open('x') as samples:
   p=subprocess.Popen(record['argv'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,start_new_session=True,preexec_fn=limits);record['owned_session']=p.pid
   try:
    while p.poll() is None:
     snap=sup.sample(p.pid);own=int(Path('/proc/self/statm').read_text().split()[1])*resource.getpagesize();snap['total_owned_rss_bytes']=snap['owned_tree_rss_bytes']+own;peak=max(peak,snap['total_owned_rss_bytes']);samples.write(json.dumps(snap)+'\n');samples.flush()
     if peak>256*1024**2 or time.monotonic()-start>45:raise RuntimeError('bounded host deadline/RSS limit')
     time.sleep(.02)
    record['exit_code']=p.wait(timeout=2)
   finally:
    if p.poll() is None or any(x['state']!='Z' for x in sup.sample(p.pid)['owned_processes']):sup.terminate(p)
    record.update(elapsed_seconds=time.monotonic()-start,peak_total_owned_rss_bytes=peak,after=sup.sample(p.pid));save(OUT/(label+'.run.json'),json.dumps(record,indent=2).encode()+b'\n');assert not any(x['state']!='Z' for x in record['after']['owned_processes'])
  commands.append(record);assert record['exit_code']==0,label;return record
 cc=Path('/home/egor/.local/bin/clang').resolve();xts=IMPL/'src/platform/crypto/xts'
 flags=['--target=x86_64-unknown-linux-gnu','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fno-strict-aliasing','-fsanitize=address,undefined','-fno-sanitize-recover=all','-include',macros,'-DMBEDTLS_CONFIG_FILE="s24_xts_profile.h"','-I'+str(src),'-I'+str(vendor/'inc'),'-I'+str(vendor/'src'),'-I'+str(xts),'-I'+str(xts/'vendor/include'),'-I'+str(xts/'vendor/library'),'-I'+str(xnu/'EXTERNAL_HEADERS'),'-I'+str(xnu/'libkern'),'-I'+str(OUT)]
 bounded([cc,*flags,OUT/'host.c',src/'rsa.c',src/'typed.c',*[vendor/p for p in prov['compiled_sources']],shared/'host-adapter.o',shared/'host-aes.o','-Wl,--threads=1','-o',OUT/'host'],'compile')
 bounded([OUT/'host'],'focused-host');result=json.loads((OUT/'focused-host.log').read_text())
 report.update(outcome='pass',summary='Canonical 33 BearSSL members, actual selected headers/compiled source/native imports, independent primary/exclusion/integer-oracle accounting and focused real sanitized host controls passed; existing ARM evidence inspected without reviewer guest',source_inputs=inputs,canonical_bearssl=dict(repository=prov['repository'],revision=prov['revision'],members=canonical),selected_xnu=selected,qualified_capsule=dict(commit=CODE,metadata_commit=META,sha256=digest(qraw),stage_capsules=stage_facts,artifact_hash_records=artifact_count),corpus=dict(primary=len(primary),independent=10,unresolved_odd_nibble_messages=excluded,odd_integer_signatures=odd_signatures,archive_sha256=sha(archive),members=member_facts),native=dict(layout=list(layout),objects=19,imports=imports,allocating_imports=False,synthetic_memset_in_production=False),focused_result=result,compiler=dict(path=str(cc),sha256=sha(cc)),final_cpu=dict(arm_checks=cpu['arm_checks'],observed_stack_bytes=cpu['observed_stack_bytes'],guest_cases=cpu['guest_cases'],commands=cpu['commands'],payload_facts=payload_facts),checks=[dict(name=n,pass_check=True) for n in ['actual-plan-verified-before-execution','complete-canonical-BearSSL-and-selected-XNU','all-compiled-owned-C-header-Git-bindings','independent-primary-exclusions-I2OSP-and-public-integer-oracle','native-layout-noheap-runtime-import-boundaries','actual-host-ARM-control-artifact-cleanup-evidence','focused-sanitized-OID-lifetime-const-error-alias-controls','fresh-4GiB-admission-256MiB-owned-RSS-no-guest']])
except Exception as error:
 report['error']=repr(error);report['traceback']=traceback.format_exc()
 if 'RESOURCE_DEFERRED' in str(error):report['outcome']='inconclusive'
report['commands']=commands;report['artifacts']=[str(p.relative_to(MAIN)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
save(OUT/'evidence.json',json.dumps(report,indent=2).encode()+b'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(MAIN)))))
raise SystemExit(report['outcome']!='pass')
