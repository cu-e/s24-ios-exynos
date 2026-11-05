#!/usr/bin/env python3
"""Independent frozen CTS3 review, bounded focused host probe; never builds a guest."""
import argparse,collections,datetime,hashlib,importlib.util,json,os,re,struct,subprocess,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent
WT=ROOT/'worktrees/krn-036-20261105';SOURCE=WT/'src/platform/crypto/cts3'
OWNER='codex-team-review-cts3-20261105-ck';XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def rfc(text):
 text=text.split('AES 128-bit key:',1)[1];key=bytearray();rows=[];field='key';target=key
 for line in text.splitlines():
  label=line.strip()
  if label in ['IV:','Input:','Output:','Next IV:']:
   field={'IV:':'iv','Input:':'pt','Output:':'ct','Next IV:':'next_iv'}[label]
   if field=='iv':rows.append({})
   target=bytearray();rows[-1][field]=target;continue
  match=re.fullmatch(r'\s*([0-9a-f]{4}):\s*((?:[0-9a-f]{2}(?:\s+|$))+)\s*',line)
  if match:
   if int(match[1],16)!=len(target):raise ValueError('RFC offset mismatch')
   target.extend(bytes.fromhex(match[2]))
 return [dict(key=bytes(key).hex(),**{k:bytes(v).hex()for k,v in row.items()})for row in rows]
def nist_field(section,label):
 lines=section.splitlines();start=next(i for i,s in enumerate(lines)if s.strip()==label)+1;result=[]
 for line in lines[start:]:
  if re.fullmatch(r'\s*[A-F0-9]{8}(?:\s+[A-F0-9]{8})*\s*',line):result.append(line)
  elif result:break
 return bytes.fromhex(' '.join(result)).hex()
def xnup(data):
 magic,size=struct.unpack_from('<II',data);assert magic==0x50554e58 and size==len(data)-8
 at=8;result={}
 while at+24<=len(data):
  name,n,flags=struct.unpack_from('<16sII',data,at);at+=24
  if not any(name):assert n==flags==0 and at==len(data);return result
  assert flags==0 and at+n<=len(data);label=name.rstrip(b'\0').decode();assert label not in result
  result[label]=data[at:at+n];at+=(n+15)//16*16
 raise ValueError('XNUP terminator missing')
class MachO:
 def __init__(self,p):
  self.data=Path(p).read_bytes();magic,cpu,_,kind,count=struct.unpack_from('<5I',self.data);assert(magic,cpu)==(0xfeedfacf,0x100000c)
  self.sections=[];self.symbols=[];self.named={};self.segments=[];self.entry=None;at=32
  for _ in range(count):
   cmd,size=struct.unpack_from('<II',self.data,at);assert size>=8 and at+size<=len(self.data)
   if cmd==0x19:
    _,va,vm,off,files=struct.unpack_from('<16s4Q',self.data,at+8);self.segments.append((va,vm,off,files));assert off+files<=len(self.data)
    n=struct.unpack_from('<I',self.data,at+64)[0]
    for i in range(n):
     s=struct.unpack_from('<16s16sQQ8I',self.data,at+72+i*80);self.sections.append(dict(name=s[0].rstrip(b'\0').decode(),va=s[2],size=s[3],off=s[4],rel=s[6],nrel=s[7],flags=s[8]))
   if cmd==2:symbol_table=struct.unpack_from('<4I',self.data,at+8)
   if cmd==5:self.entry=struct.unpack_from('<Q',self.data,at+272)[0]
   at+=size
  off,n,strings,limit=symbol_table
  for i in range(n):
   k,t,section,_,value=struct.unpack_from('<IBBHQ',self.data,off+i*16);end=self.data.index(0,strings+k,strings+limit);name=self.data[strings+k:end].decode();row=dict(name=name,kind=t,section=section,value=value);self.symbols.append(row)
   if t&0xe==0xe:self.named.setdefault(name,row)
 def imports(self):return{s['name']for s in self.symbols if s['kind']&1 and s['kind']&0xe==0}
 def definitions(self):return{s['name']for s in self.symbols if s['kind']&0xe==0xe}
 def read(self,name,fmt):
  s=self.named[name];section=self.sections[s['section']-1];offset=s['value']-section['va'];assert section['flags']&255!=1 and offset+struct.calcsize(fmt)<=section['size'];return struct.unpack_from(fmt,self.data,section['off']+offset)
 def relocation(self,name):
  s=self.named[name];section=self.sections[s['section']-1];wanted=s['value']-section['va'];result=[]
  for i in range(section['nrel']):
   off,info=struct.unpack_from('<iI',self.data,section['rel']+8*i)
   if off==wanted and info>>27&1:result.append(self.symbols[info&0xffffff]['name'])
  return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);args=ap.parse_args();out=BASE/'runs'/args.run;out.mkdir(parents=True,exist_ok=False)
 report=dict(kind='source-review',origin='local-host',outcome='fail',task='REV-021',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=[],inputs={},source_commands=[],commands=[],reviewer_guest_runs=0)
 def check(name,ok):
  report['checks'].append({'name':name,'passed':bool(ok)})
  if not ok:raise AssertionError(name)
 def bind(p,digest=None):
  p=Path(p);actual=sha(p);report['inputs'][str(p)]=actual
  if digest is not None and actual!=digest:raise AssertionError('hash mismatch '+str(p))
  return p
 def prospective():
  state=load(ROOT/'state/lab.json');task=next(t for t in state['tasks']if t['id']=='REV-021');plan=next(e for e in state['experiments']if e['id']=='REVCTS3-001')
  check('prospective-owned-active-plan',task['owner']==OWNER and task['status']=='in_progress'and plan['owner']==OWNER and plan['task']=='REV-021'and plan['status']=='planned')
  return plan
 def git(repo,spec):
  prospective();argv=['git','-C',str(repo),'show',spec];p=subprocess.run(argv,env=ENV,capture_output=True,timeout=15);report['source_commands'].append(dict(argv=argv,exit_code=p.returncode,stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),stderr_sha256=hashlib.sha256(p.stderr).hexdigest(),environment_overrides={k:ENV[k]for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']}));check('pinned-git-read',p.returncode==0);return p.stdout
 def child(argv,name,seconds=15,expected=0):
  prospective();r=supervisor.run(argv,out,name,seconds,256);report['commands'].append(r);check('bounded-child-'+name,r['exit_code']==expected and r['outcome']in(['pass']if expected==0 else['fail'])and not r['after']['owned_processes']and r['peak_total_owned_rss_bytes']<=256*1024**2);return r
 try:
  plan=prospective();(out/'prospective-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
  raw=load(bind(WT/'artifacts/crypto-cts3/cpu-final1/evidence.json','a95b5c69a14519bc2cfc2da8dea025a684bda3a82647b27e66d93d90109afc57'));qualified=load(bind(WT/'docs/procedures/crypto-cts3/qualified-evidence.json'))
  check('qualified-actual-host-arm',raw['outcome']=='pass'and raw['host_checks']==raw['arm_checks']==28794 and raw['arm_cpu_executed']and not raw['owned_dirty_at_start'])
  for row in qualified['stage_capsules']:
   capsule=load(bind(ROOT/row['path'],row['sha256']));check('stage-outcome-'+row['experiment'],capsule['outcome']==row['outcome']and capsule.get('error')==row['error'])
  for name,digest in raw['artifact_hashes'].items():bind(ROOT/name,digest)
  for name,digest in raw['dependency_hashes'].items():bind(name,digest)
  for name,digest in raw['owned_source_hashes'].items():
   bind(WT/name,digest);check('frozen-source-'+name,hashlib.sha256(git(ROOT,'80ee7fde7b7a67310a8eecdb1a015aa6aa8081ad:'+name)).hexdigest()==digest)
  for name,digest in raw['audit_continuation']['unchanged_compiled_and_oracle_sources'].items():check('same-compiled-source-'+name,hashlib.sha256(git(ROOT,'89ff8f2a6f616c5a3662f8e91cb54396318eb405:'+name)).hexdigest()==digest)
  headers={}
  for name in ['EXTERNAL_HEADERS/corecrypto/ccpad.h','EXTERNAL_HEADERS/corecrypto/ccmode_impl.h','libkern/libkern/crypto/register_crypto.h','bsd/nfs/gss/ccrypto.c','bsd/nfs/gss/gss_krb5_mech.c','osfmk/libsa/string.h']:
   headers[name]=git(ROOT/'references/apple-xnu',XNU+':'+name).decode()
  check('selected-strict-size-contract','at least 1 block + 1 byte' in headers['EXTERNAL_HEADERS/corecrypto/ccpad.h'])
  nfs=headers['bsd/nfs/gss/gss_krb5_mech.c'];check('NFS-separate-short-and-ignored-return','if (len <= ccmode->block_size)'in nfs and '\n\t\tdo_ccpad(ccmode, wctx.crypt_ctx, wctx.iv, cts_len, cts_pad, cts_pad);'in nfs)
  production=load(SOURCE/'production.json');check('production-scope',production['sources']==['cts3.c']and production['headers']==['cts3.h']and not production['fixture_sources_are_production']and not production['provider_registered']and not production['selected_native_external_boundary']['native_kernel_provider_qualified'])
  canonical=raw['canonical_AES_inputs'];archive=bind(canonical['archive'],canonical['sha256']);vendor=ROOT/'src/platform/crypto/xts/vendor'
  with tarfile.open(archive)as tar:
   for name,row in canonical['files'].items():
    upstream=tar.extractfile('mbedtls-'+canonical['commit']+'/'+name).read();check('complete-canonical-'+name,hashlib.sha256(upstream).hexdigest()==row['canonical_sha256']);actual=upstream
    if name=='library/common.h':actual=upstream.replace(b'#include <assert.h>',b'/* Owned freestanding AES-only port: this unit uses no runtime assert. */\n#if !defined(S24_XTS_FREESTANDING)\n#include <assert.h>\n#endif')
    check('exact-accepted-AES-member-'+name,(vendor/name).read_bytes()==actual);bind(vendor/name,row['actual_sha256'])
  pins=load(bind(WT/'docs/procedures/crypto-cts3/source-pins.json',raw['primary_source_pins']['sha256']))
  for row in pins['documents']:
   if row['outcome']=='pass':bind(WT/row['path'],row['sha256'])
  check('source-acquisition-failure-preserved',any(row['outcome']=='fail'and'nist-38a.pdf'in row['path']for row in pins['documents']))
  corpus=load(bind(raw['corpus_path']));vectors=corpus['vectors'];cbc=corpus['cbc_fixture'];check('corpus-counts',len(vectors)==381 and len(cbc)==18 and corpus['primary']['count']==6 and corpus['derived_extra_count']==375)
  oracle=raw['corpus']['oracle'];bind(oracle['library'],oracle['sha256']);bind(oracle['libcrypto_path'],oracle['libcrypto_sha256'])
  for name,digest in oracle['provider_module_hashes'].items():bind(name,digest)
  for name,digest in raw['tools']['host']['runtime_hashes'].items():bind(name,digest)
  primary_text=(WT/'artifacts/crypto-cts3/inputs/rfc3962.txt').read_text();primary=rfc(primary_text);check('RFC-six-offset-checked-records',len(primary)==6 and [len(bytes.fromhex(v['pt']))for v in primary]==[17,31,32,47,48,64])
  for expected,actual in zip(primary,vectors):check('exact-primary-record',all(actual[k]==v for k,v in expected.items()))
  malformed=primary_text.replace('0010:  20\n','0011:  20\n',1)
  try:rfc(malformed);offset_rejected=False
  except ValueError:offset_rejected=True
  check('independent-primary-offset-control',malformed!=primary_text and offset_rejected)
  text=(WT/'artifacts/crypto-cts3/inputs/nist-AES-CBC.txt').read_text();iv=nist_field(text,'IV is')
  for index,bits in enumerate([128,192,256]):
   part=text.split('CBC-AES'+str(bits)+' (Encryption)',1)[1].split('CBC-AES'+str(bits)+' (Decryption)',1)[0]
   row={k:nist_field(part,label)for k,label in [('key','Key is'),('pt','Plaintext is'),('ct','Ciphertext is')]};row['iv']=iv;row['next_iv']=row['ct'][-32:]
   check('published-NIST-CBC-'+str(bits),all(cbc[index][k]==v for k,v in row.items()))
   swapped=row['ct'][:-64]+row['ct'][-32:]+row['ct'][-64:-32];check('explicitly-derived-NIST-CS3-'+str(bits),vectors[-3+index]['ct']==swapped and vectors[-3+index]['next_iv']==row['next_iv']and'derived'in vectors[-3+index]['source'])
  coverage=collections.defaultdict(set)
  for row in vectors:
   b=len(bytes.fromhex(row['iv']));n=len(bytes.fromhex(row['pt']));prefix=((n-1)//b-1)*b;coverage[(row['algorithm'],len(bytes.fromhex(row['key'])),b)].add((n,any(bytes.fromhex(row['iv']))))
   check('length-and-IVY',n>b and len(bytes.fromhex(row['ct']))==n and row['next_iv']==row['ct'][2*prefix:2*(prefix+b)]and len(row['chain_ct'])==2*n)
  for a,n,b in [(0,8,8),(1,16,8),(1,24,8),(2,16,16),(2,24,16),(2,32,16)]:
   wanted={(k,p)for k in list(range(b+1,3*b+1))+[4*b-1,4*b,4*b+1,7*b-1,7*b,7*b+1,16*b+1]for p in [False,True]};check('all-length-key-IV-boundaries-'+str((a,n,b)),wanted<=coverage[(a,n,b)])
  for name,row in raw['native_symbols'].items():
   obj=MachO(bind(name));check('independent-native-imports-'+Path(name).name,obj.imports()==set(row['imports']));check('independent-native-definitions-'+Path(name).name,obj.definitions()==set(row['definitions']))
  objects=WT/'artifacts/crypto-cts3/host-arm2';adapter=MachO(objects/'arm-adapter.o');fixture=MachO(objects/'arm-fixture.o');typed=MachO(objects/'arm-typed.o')
  check('actual-selected-layout',adapter.read('_s24_cts3_layout','<6Q')==(40,16,16,16,16,16)and fixture.read('_s24_cts3_fixture_layout','<4Q')==(304,16,288,40))
  check('production-only-generic-imports',adapter.imports()=={'___memcpy_chk','_memcpy','_mbedtls_platform_zeroize'})
  check('typed-real-callback-relocations',typed.relocation('_s24_cts3_typed_encrypt')==['_s24_cts3_encrypt']and typed.relocation('_s24_cts3_typed_decrypt')==['_s24_cts3_decrypt'])
  unique={}
  for name in raw['native_symbols']:
   for symbol in MachO(name).definitions():
    if symbol.startswith('_mbedtls_aes_')or symbol=='_mbedtls_platform_zeroize':unique.setdefault(symbol,[]).append(name)
  check('single-real-AES-and-zeroizer',unique==raw['single_AES_and_zeroizer_definitions']and all(len(v)==1 for v in unique.values()))
  guest=MachO(objects/'arm-guest.o');stack=guest.sections[guest.named['_cts3_stack']['section']-1];check('legitimate-zerofill-guest-only',stack['flags']&255==1 and stack['size']==65536)
  nm=raw['tools']['nm'];bind(nm['path'],nm['sha256']);bind(nm['build_report'],nm['build_report_sha256']);check('qualified-nm-consumer-only',nm['source_commit']=='904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb')
  boundary=raw['fortified_memory_boundary'];check('genuine-fortification-source',hashlib.sha256(headers['osfmk/libsa/string.h'].encode()).hexdigest()==boundary['canonical_header']['sha256']and'__builtin___memcpy_chk'in headers['osfmk/libsa/string.h']and not boundary['native_kernel_provider_qualified']);bind(boundary['canonical_header']['path'],boundary['canonical_header']['sha256']);bind(boundary['accepted_fixture_provider']['object'],boundary['accepted_fixture_provider']['sha256']);bind(boundary['accepted_fixture_provider']['source'],boundary['accepted_fixture_provider']['source_sha256'])
  for name,digest in raw['accepted_dependencies']['objects'].items():bind(name,digest)
  bind(raw['shared_runtime']['path'],raw['shared_runtime']['sha256'])
  allblob=bytearray()
  for table in [vectors,cbc]:
   for row in table:
    for field in ['key','iv','pt','ct','next_iv','chain_ct','chain_iv']:allblob.extend(bytes.fromhex(row.get(field,row['ct']if field=='chain_ct'else row['next_iv'])))
  phase=WT/'artifacts/crypto-cts3/cpu-final1';image_dir=WT/'artifacts/crypto-cts3/audit-link2'
  avf=raw['avf_inputs'];bind(avf['qemu'],avf['pin']['qemu_sha256']);bind(avf['shim'],avf['pin']['shim_sha256'])
  for name,digest in avf['reports'].items():bind(name,digest)
  for name,digest in avf['source_hashes'].items():
   if name.startswith('qemu/'):bind(ROOT/'worktrees/vm-004-20261105/artifacts/qemu-host/release-10.2.0/source/qemu-10.2.0'/name[5:],digest)
   else:check('genuine-loader-source-'+name,hashlib.sha256(git(ROOT/'references/scion-avf',avf['pin']['scion_commit']+':'+name)).hexdigest()==digest)
  for index,row in enumerate(raw['guest_cases']):
   name=row['name'];mode='spin'if name=='spin-timeout'else'normal';image=MachO(image_dir/(mode+'.macho'));check('linked-image-'+mode,sha(image_dir/(mode+'.macho'))==raw['images'][mode]['sha256']);payload=xnup(bind(phase/(name+'.xnup'),row['payload_sha256']).read_bytes());expected=bytearray(image.data)
   if name=='corrupt-vector':
    check('unique-actual-whole-vector-blob',image.data.count(allblob)==1);point=image.data.index(allblob)+sum(len(bytes.fromhex(vectors[0][f]))for f in ['key','iv','pt']);check('actual-RFC-ciphertext-mutation-point',point==raw['corrupt_vector_control']['offset']and expected[point]==bytes.fromhex(primary[0]['ct'])[0]);expected[point]^=1
   check('exact-actual-payload-'+name,payload['kernel']==expected and payload['cmdline']==('cpus=1 xts_cookie='+('wrong'if name=='wrong-cookie'else'owned-adapter-v1')).encode()+b'\0')
   console=bind(phase/(name+'.log'),row['console_sha256']).read_text();command=raw['commands'][index];check('bounded-CPU-cleanup-'+name,not command['after']['owned_processes']and command['rss_budget_mib']==512 and command['peak_total_owned_rss_bytes']<=512*1024**2 and command['MemAvailable_before_KiB']>=4*1024**2)
   if name=='positive':
    delta=0xffffffefc4000000;high=max(s[0]+s[1]for s in image.segments);dt=((high-delta)+16383)&~16383;entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console);check('real-CPU-entry-count-and-stop',entry and int(entry[1],16)==image.entry-delta and int(entry[2],16)==dt+65536 and'CTS3 ARM PASS checks=0x707a failure_line=0x0'in console and'XTS SYNTHETIC PSCI_SYSTEM_OFF'in console)
   elif name=='wrong-cookie':check('actual-cookie-rejection','XTS SYNTHETIC REJECT command-cookie'in console and'CTS3 ARM PASS'not in console)
   elif name=='corrupt-vector':check('actual-algorithm-counterexample','CTS3 ARM FAIL'in console and'CTS3 ARM PASS'not in console and'XTS SYNTHETIC PSCI_SYSTEM_OFF'in console)
   else:check('actual-spin-timeout','CTS3 SYNTHETIC SPIN-CONTROL'in console and command['outcome']=='timeout'and command['timeout_seconds']==3 and'CTS3 ARM PASS'not in console)
  helper=bind(raw['resource_supervisor']['path'],raw['resource_supervisor']['sha256']);spec=importlib.util.spec_from_file_location('qualified_resource_supervisor',helper);supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
  pdf=bind(raw['tools']['pdftotext']['path'],raw['tools']['pdftotext']['sha256']);child([pdf,'-layout',WT/'artifacts/crypto-cts3/inputs/nist-38a-addendum.pdf',out/'nist-addendum.txt'],'normative-extract')
  normative=(out/'nist-addendum.txt').read_text();check('normative-unconditional-swap',re.search(r'unconditionally\s+swaps',normative)and'CBC-CS3'in normative)
  chosen=vectors[:6]
  for algorithm,keybytes,block,size in [(0,8,8,9),(0,8,8,16),(1,16,8,17),(1,24,8,32),(2,24,16,33),(2,32,16,64)]:chosen.append(next(v for v in vectors if v['algorithm']==algorithm and len(v['key'])==keybytes*2 and len(v['iv'])==block*2 and len(v['pt'])==size*2 and any(bytes.fromhex(v['iv']))))
  def array(value):return'{'+','.join(str(x)for x in bytes.fromhex(value))+'}'
  header=['#define PROBE_RECORDS '+str(len(chosen)),'struct probe_record {unsigned algorithm,keybytes,block,bytes;unsigned char key[32],iv[16],pt[272],ct[272],next[16];};','static const struct probe_record probe_records[]={']
  for v in chosen:header.append('{'+','.join([str(v['algorithm']),str(len(v['key'])//2),str(len(v['iv'])//2),str(len(v['pt'])//2),*(array(v[f])for f in ['key','iv','pt','ct','next_iv'])])+'},')
  header.append('};');(out/'records.h').write_text('\n'.join(header)+'\n');(out/'focused-records.json').write_text(json.dumps(chosen,indent=2)+'\n')
  host=bind(raw['tools']['host']['path'],raw['tools']['host']['sha256']);link_objects=[objects/'host-adapter.o',objects/'host-fixture.o',objects/'host-aes.o',ROOT/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2/host-adapter.o',ROOT/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/host-adapter.o',ROOT/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/host-des.o']
  for p in link_objects:bind(p)
  child([host,'--target=x86_64-unknown-linux-gnu','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1','-I'+str(SOURCE),'-I'+str(out),'-I'+str(ROOT/'references/apple-xnu/EXTERNAL_HEADERS'),BASE/'focused.c',*link_objects,'-o',out/'focused'],'focused-compile',30)
  child([out/'focused'],'focused-positive',10);child([out/'focused','--wrong-expected'],'focused-wrong-expected',10,1)
  positive=(out/'focused-positive.log').read_text();check('focused-actual-postwrite-error-probe','REVIEW CTS3 PASS records=12'in positive and'post-real-CBC-error=all-stages'in positive and'AddressSanitizer'not in positive)
  check('focused-wrong-oracle-detected','REVIEW CTS3 FAIL'in(out/'focused-wrong-expected.log').read_text())
  report['focused_checks']=int(re.search(r'checks=(\d+)',positive)[1]);report['focused_records']=len(chosen);report['outcome']='pass';report['summary']='Independent CTS3 source/corpus/canonical/native/payload/cleanup audit and focused real post-CBC-error sanitized probe passed; no bounded blocking finding, native integration/private gates preserved'
 except Exception as error:
  report['error']=repr(error)
  if 'supervisor'in locals()and isinstance(error,supervisor.ResourceDeferred):report['outcome']='inconclusive';report['summary']='Focused review resource-deferred before child; no algorithm defect inferred'
 report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();report['reviewer_source_hashes']={str(p):sha(p)for p in [Path(__file__),BASE/'focused.c',BASE/'experiment.md']};report['artifacts']={str(p.relative_to(ROOT)):sha(p)for p in sorted(out.rglob('*'))if p.is_file()};(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['outcome','error','focused_checks','focused_records','summary']},indent=2));return report['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
