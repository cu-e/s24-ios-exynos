#!/usr/bin/env python3
"""Independent canonical-vendor, corpus and focused host review; never QEMU."""
from datetime import datetime,timezone
import gzip,hashlib,importlib.util,json,os,re,resource,subprocess,tarfile,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];IMPL=MAIN/'worktrees/krn-032-20261105';FINAL=IMPL/'artifacts/crypto-des/cpu-final3'
C='6aa53a7df5cec5d4e11884751d79a1d2641dd316';CORE='e13dcd37f633c795856b16978aaae39f8bdc4ec9';XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'};RUN=os.environ.get('S24_REVDES_RUN','20261105-session1');assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-des'/RUN;OUT.mkdir(parents=True,exist_ok=False);(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes());commands=[]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
def source_run(argv,label):
 with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=ENV,timeout=20)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(MAIN)),stderr=str((OUT/(label+'.stderr')).relative_to(MAIN)),environment_overrides={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}));(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');assert r.returncode==0,(label,r.returncode)
 return (OUT/(label+'.stdout')).read_bytes()
def primary_parse(data,name):
 rows=[];fields={};direction=None
 def flush():
  if not fields:return
  assert direction in ['ENCRYPT','DECRYPT']
  k=bytes.fromhex(fields['KEYs'])*3 if 'KEYs'in fields else b''.join(bytes.fromhex(fields[x]) for x in ['KEY1','KEY2','KEY3'])
  pt=bytes.fromhex(fields['PLAINTEXT']);ct=bytes.fromhex(fields['CIPHERTEXT']);iv=bytes.fromhex(fields['IV']) if Path(name).name.startswith('TCBC') else b''
  assert len(k)==24 and len(pt)==len(ct) and len(pt)>0 and len(pt)%8==0 and len(iv) in [0,8]
  rows.append(dict(source='NIST',file=name,count=int(fields['COUNT']),direction=direction,key=k.hex(),iv=iv.hex(),pt=pt.hex(),ct=ct.hex()))
 for raw in data.decode().splitlines():
  line=raw.strip()
  if not line or line.startswith('#'):continue
  if line.startswith('['):flush();fields={};direction=line[1:-1];continue
  key,value=map(str.strip,line.split('=',1))
  if key=='COUNT' and fields:flush();fields={}
  assert key not in fields;fields[key]=value
 flush();return rows
report=dict(kind='source-review',origin='local-host',outcome='fail',summary='Independent canonical DES vendor/source/corpus/host review; actual final CPU evidence audit only, no reviewer guest',recorded_at=datetime.now(timezone.utc).isoformat(),commit=C,core_commit=CORE,commands=commands,QEMU_executed_by_reviewer=False,provider_registered=False,native_device=False,FIPS_qualified=False,private_ABI_qualified=False)
try:
 names=source_run(['git','ls-tree','-r','--name-only',C,'--','src/platform/crypto/des','docs/procedures/crypto-des'],'candidate-files').decode().splitlines();inputs={}
 for i,name in enumerate(names):
  p=OUT/'candidate'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source_run(['git','show',C+':'+name],'candidate-'+str(i)));inputs[name]=sha(p)
 src=OUT/'candidate/src/platform/crypto/des';assert source_run(['git','show',CORE+':src/platform/crypto/des/des.c'],'core-source')==(src/'des.c').read_bytes()
 vendor=src/'vendor';prov=json.loads((vendor/'provenance.json').read_text());archive=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/inputs/mbedtls.tar.gz';assert sha(archive)==prov['archive_sha256']
 # Read through gzip EOF/CRC and compare complete official members, independently of old catalog.
 total=0
 with gzip.open(archive,'rb') as f:
  while block:=f.read(1048576):total+=len(block)
 canonical={}
 with tarfile.open(archive,'r:gz') as tar:
  for name,expected in prov['files'].items():
   members=[m for m in tar.getmembers() if m.name=='mbedtls-'+prov['commit']+'/'+name];assert len(members)==1,name
   data=tar.extractfile(members[0]).read();local=(vendor/name).read_bytes();assert sha(vendor/name)==expected
   rawhash=hashlib.sha256(data).hexdigest()
   if name=='library/common.h':
    assert rawhash==prov['patches'][name]['upstream_sha256'] and data.count(b'#include <assert.h>\n')==1
    adapted=data.replace(b'#include <assert.h>\n',b'/* DES software unit has no runtime assert; omit unused libc header. */\n#if !defined(S24_DES_FREESTANDING)\n#include <assert.h>\n#endif\n',1);assert adapted==local and hashlib.sha256(adapted).hexdigest()==prov['patches'][name]['local_sha256']
   else:assert data==local,name
   canonical[name]=dict(upstream_bytes=len(data),upstream_sha256=rawhash,local_bytes=len(local),local_sha256=sha(vendor/name),exact_unmodified=name!='library/common.h')
 assert canonical['include/mbedtls/check_config.h']['upstream_bytes']==48196
 epath=FINAL/'evidence.json';assert sha(epath)=='077f56b1469d961ec5d5f5af695e85e0037ca698fd60a984b62efcae7006447d';e=json.loads(epath.read_text());assert e['outcome']=='pass' and e['commit']==C and e['experiment']=='DES004'
 for name,h in e['artifact_hashes'].items():assert sha(MAIN/name)==h,name
 for name,h in e['owned_source_hashes'].items():
  p=Path(name);p=p if p.is_absolute() else IMPL/name;assert sha(p)==h,name
 for name,h in e['selected_sources'].items():
  data=source_run(['git','-C',MAIN/'references/apple-xnu','show',XNU+':'+name],'xnu-'+Path(name).name);assert hashlib.sha256(data).hexdigest()==h
  p=OUT/'selected-xnu'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 for c in e['commands']:assert not any(p['state']!='Z' for p in c['after']['owned_processes'])
 assert e['host_vectors']==2936 and e['host_checks']==167606 and e['arm_checks']==167606 and all(x['accepted'] for x in e['guest_cases'])
 corpus=json.loads((FINAL/'regenerated/vectors.json').read_text());primary=[];derived=[];archive_facts={}
 for archive_name,h in corpus['archive_sha256'].items():
  path=MAIN/'worktrees/krn-028-20261105/tools/research/crypto-candidates/local/vectors'/archive_name;assert sha(path)==h
  with zipfile.ZipFile(path) as z:
   for name in sorted(z.namelist()):
    if not name.lower().endswith('.rsp'):continue
    raw=z.read(name);assert hashlib.sha256(raw).hexdigest()==corpus['files'][archive_name+'/'+name]
    if not Path(name).name.startswith(('TECB','TCBC')) or Path(name).name.startswith('TCBCI'):continue
    parsed=primary_parse(raw,archive_name+'/'+name);primary.extend(parsed);archive_facts[archive_name+'/'+name]=len(parsed)
    for row in parsed:
     k=bytes.fromhex(row['key'])
     if k[:8]==k[8:16]==k[16:]:derived.append(row|dict(source='NIST-derived repeated-key DES reduction',key=k[:8].hex()))
     if k[:8]==k[16:]:derived.append(row|dict(source='NIST-derived EDE2 local key form',key=k[:16].hex()))
 assert primary==[v for v in corpus['vectors'] if v['source']=='NIST'] and derived==[v for v in corpus['vectors'] if v['source'].startswith('NIST-derived')]
 extras=[v for v in corpus['vectors'] if v['source']=='OpenSSL EVP'];assert (len(primary),len(derived),len(extras))==(1000,1900,36)
 for v in extras:
  n=len(bytes.fromhex(v['key']));cbc=bool(v['iv']);blocks=len(bytes.fromhex(v['pt']))//8;stream=hashlib.shake_256(f's24-des-oracle-v1/{n}/{int(cbc)}/{blocks}'.encode()).digest(n+8+blocks*8)
  assert v['key']==stream[:n].hex() and v['iv']==(stream[n:n+8].hex() if cbc else '') and v['pt']==stream[n+8:].hex()
 helpers=corpus['helpers'];assert len(helpers)==352
 table=(vendor/'library/des.c').read_text().split('static const unsigned char weak_key_table',1)[1].split('};',1)[0];weak_bytes=bytes(int(x,16) for x in re.findall(r'0x[0-9A-Fa-f]{2}',table));assert len(weak_bytes)==128;weak={weak_bytes[i:i+8] for i in range(0,128,8)}
 for helper in helpers:
  key=bytes.fromhex(helper['key']);normal=bytes((b&254)|int((b&254).bit_count()%2==0) for b in key);assert normal.hex()==helper['parity'] and helper['weak']==int(normal in weak)
 # Six source-labeled pairs exercise every key form/mode without repeating the full matrix.
 selected=[]
 for cbc in [False,True]:
  row=next(v for v in primary if bool(v['iv'])==cbc and v['key'][:16]*3==v['key']);selected.append(row|dict(key=row['key'][:16]))
  row=next(v for v in primary if bool(v['iv'])==cbc and 16<=len(bytes.fromhex(v['pt']))<=128);selected.append(row)
  selected.append(next(v for v in extras if bool(v['iv'])==cbc and len(v['key'])==32 and len(v['pt'])==32))
 (OUT/'selected-cases.json').write_text(json.dumps(selected,indent=2)+'\n');arr=lambda h:'{'+','.join(str(b) for b in bytes.fromhex(h))+'}' if h else '{0}'
 header='struct review_case { unsigned n,len,cbc; unsigned char key[24],iv[8],pt[128],ct[128]; };\nstatic const struct review_case review_cases[]={\n'
 for v in selected:header+='{'+','.join([str(len(v['key'])//2),str(len(v['pt'])//2),str(int(bool(v['iv']))),*[arr(v[k]) for k in ['key','iv','pt','ct']]])+'},\n'
 (OUT/'review_cases.h').write_text(header+'};\n');(OUT/'host.c').write_bytes((ROOT/'docs/reviews/krn-032/host.c').read_bytes())
 shared=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2';sr=json.loads((shared/'evidence.json').read_text());assert sha(shared/'evidence.json')=='c5064a512ba295d1cd447af1e73ac6fc4f9c0ffeaf5b78f09ca0f80fc1f6216c'
 for f in ['host-adapter.o','host-aes.o']:assert sha(shared/f)==sr['artifact_hashes'][str((shared/f).relative_to(MAIN/'worktrees/krn-029-20261105'))]
 # Only host subprocesses below are run; each gets an immediate 4GiB admission guard.
 spec=importlib.util.spec_from_file_location('des_review_cleanup',ROOT/'tools/build/qemu_host.py');sup=importlib.util.module_from_spec(spec);spec.loader.exec_module(sup)
 def bounded(argv,label):
  before=memory()
  if before<4*1024**2:raise RuntimeError('RESOURCE_DEFERRED before '+label+': '+str(before)+' KiB; no compiler/test started')
  start=time.monotonic();record=dict(argv=list(map(str,argv)),cwd=str(ROOT),MemAvailable_before_KiB=before,timeout_seconds=20,rss_budget_mib=256,environment_overrides={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'});peak=0
  def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  env={**ENV,'ASAN_OPTIONS':'halt_on_error=1:detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'}
  with (OUT/(label+'.log')).open('xb') as log,(OUT/(label+'.samples.jsonl')).open('x') as samples:
   p=subprocess.Popen(record['argv'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,start_new_session=True,preexec_fn=limits);record['owned_session']=p.pid
   try:
    while p.poll() is None:
     snap=sup.sample(p.pid);own=int(Path('/proc/self/statm').read_text().split()[1])*resource.getpagesize();snap['total_owned_rss_bytes']=snap['owned_tree_rss_bytes']+own;peak=max(peak,snap['total_owned_rss_bytes']);samples.write(json.dumps(snap)+'\n');samples.flush()
     if peak>256*1024**2 or time.monotonic()-start>20:raise RuntimeError('bounded host resource/deadline limit')
     time.sleep(.02)
    record['exit_code']=p.wait(timeout=2)
   finally:
    if p.poll() is None or any(x['state']!='Z' for x in sup.sample(p.pid)['owned_processes']):sup.terminate(p)
    record.update(elapsed_seconds=time.monotonic()-start,peak_total_owned_rss_bytes=peak,after=sup.sample(p.pid));(OUT/(label+'.run.json')).write_text(json.dumps(record,indent=2)+'\n');assert not any(x['state']!='Z' for x in record['after']['owned_processes'])
  commands.append(record);assert record['exit_code']==0,label;return record
 cc=Path('/home/egor/.local/bin/clang').resolve();flags=['--target=x86_64-unknown-linux-gnu','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DMBEDTLS_CONFIG_FILE="s24_des_profile.h"','-DS24_DES_FREESTANDING','-I'+str(src),'-I'+str(vendor/'include'),'-I'+str(vendor/'library'),'-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-I'+str(OUT)]
 bounded([cc,*flags,OUT/'host.c',src/'des.c',vendor/'library/des.c',shared/'host-adapter.o',shared/'host-aes.o','-Wl,--threads=1','-o',OUT/'host'],'compile')
 bounded([OUT/'host'],'focused-host');result=json.loads((OUT/'focused-host.log').read_text())
 report.update(outcome='pass',summary='Canonical complete DES vendor/archive, independently parsed primary/derived/helper accounting and focused host IV/context/error checks passed; final registered DES004 host/ARM/control evidence audited, no reviewer QEMU',source_inputs=inputs,canonical_archive=dict(path=str(archive.relative_to(MAIN)),sha256=sha(archive),decompressed_bytes_read=total,members=canonical),corpus_counts=dict(primary=len(primary),derived=len(derived),independent_extras=len(extras),helpers=len(helpers),files=archive_facts),result=result,compiler=dict(path=str(cc),sha256=sha(cc)),final_owner_evidence=dict(path=str(epath.relative_to(MAIN)),sha256=sha(epath),experiment=e['experiment'],host_checks=e['host_checks'],arm_checks=e['arm_checks'],guest_cases=e['guest_cases']),checks=[dict(name=n,pass_check=True) for n in ['complete-canonical-archive-members-and-adaptation','genuine-selected-XNU-headers-and-consumers','independent-primary-derived-extras-helper-classification','final-DES004-source-artifact-controls-and-no-survivors','focused-host-ASan-UBSan-IV-context-alias-helper-boundaries','fresh-4GiB-admission-and-256MiB-owned-RSS']])
except Exception as error:
 report['error']=repr(error)
 if 'RESOURCE_DEFERRED'in str(error):report['outcome']='inconclusive'
report['artifacts']=[str(p.relative_to(MAIN)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(MAIN)))))
raise SystemExit(report['outcome']!='pass')
