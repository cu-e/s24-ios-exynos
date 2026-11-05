#!/usr/bin/env python3
"""Prepare bounded genuine selected DES/ESP caller CPU images; never runs QEMU."""
import argparse,datetime,hashlib,importlib.util,json,os,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',LC_ALL='C',PYTHONUTF8='1')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
class Image:
 def __init__(self,path):
  self.path=Path(path);self.data=self.path.read_bytes();self.segments=[];self.sections=[];self.symbols={};at=32;st=None
  if struct.unpack_from('<I',self.data)[0]!=0xfeedfacf:raise ValueError('thin MachO64 required')
  for _ in range(struct.unpack_from('<I',self.data,16)[0]):
   cmd,n=struct.unpack_from('<II',self.data,at)
   if n<8 or at+n>len(self.data):raise ValueError('load command bounds')
   if cmd==0x19:
    name,va,vm,off,size=struct.unpack_from('<16s4Q',self.data,at+8);self.segments.append(dict(name=name.rstrip(b'\0').decode(),va=va,vm=vm,off=off,size=size))
    for i in range(struct.unpack_from('<I',self.data,at+64)[0]):
     name,seg,addr,sz,offset,align,rel,nr,flags,_,_,_=struct.unpack_from('<16s16sQQ8I',self.data,at+72+i*80);self.sections.append(dict(name=name.rstrip(b'\0').decode(),segment=seg.rstrip(b'\0').decode(),va=addr,size=sz,off=offset,flags=flags))
   if cmd==2:st=struct.unpack_from('<4I',self.data,at+8)
   at+=n
  if not st:raise ValueError('symbol table required')
  off,count,strings,size=st
  for i in range(count):
   name,kind,section,desc,value=struct.unpack_from('<IBBHQ',self.data,off+i*16)
   if kind&0x0e!=0x0e:continue
   end=self.data.index(0,strings+name,strings+size);label=self.data[strings+name:end].decode();self.symbols.setdefault(label,[]).append(dict(va=value,section=section,kind=kind,desc=desc))
 def symbol(self,name):
  vals=self.symbols[name]
  if len(vals)!=1:raise ValueError('unique linked symbol '+name)
  return vals[0]
 def offset(self,va,n):
  for s in self.sections:
   if s['flags']&0xff not in [1,12] and s['va']<=va and va+n<=s['va']+s['size']:
    at=s['off']+va-s['va']
    if at+n>len(self.data):raise ValueError('section outside bytes')
    return at
  raise ValueError('address not file-backed')
 def read(self,name,fmt,delta=0):return struct.unpack_from(fmt,self.data,self.offset(self.symbol(name)['va']+delta,struct.calcsize(fmt)))
 def proof(self):
  public={};names={}
  for t in ['des','tdes']:
   for mode in ['ecb','cbc']:
    for d in ['encrypt','decrypt']:
     name='_s24_kernel_'+t+'_'+mode+'_'+d;v=self.symbol(name)['va'];meta=self.read(name,'<2Q');cbs=self.read(name,'<2Q',16)
     if meta!=(400 if t=='tdes' else 144,8) or not all(0xfffffff007000000<=x<0xfffffff008000000 for x in [v,*cbs]):raise ValueError('linked mode metadata/high pointers')
     for cb in cbs:
      if not any(s['segment']=='__TEXT' and s['name']=='__text' and s['va']<=cb<s['va']+s['size'] for s in self.sections):raise ValueError('callback not real linked text')
     public[name]={'va':v,'metadata':meta,'callbacks':cbs};names[t+'_'+mode+'_'+d]=v
  offsets={'des_ecb_encrypt':200,'des_ecb_decrypt':208,'des_cbc_encrypt':216,'des_cbc_decrypt':224,'tdes_ecb_encrypt':232,'tdes_ecb_decrypt':240,'tdes_cbc_encrypt':248,'tdes_cbc_decrypt':256}
  for name,offset in offsets.items():
   if self.read('_test_table','<Q',offset)!=(names[name],):raise ValueError('actual owned partial table immutable mode pointer')
  for offset,name in [(264,'_s24_kernel_des_key_is_weak'),(272,'_s24_kernel_des_key_set_odd_parity')]:
   if self.read('_test_table','<Q',offset)!=(self.symbol(name)['va'],):raise ValueError('actual partial table typed helper pointer')
  return {'public_modes':public,'test_table_va':self.symbol('_test_table')['va'],'mapped_entry_va':self.symbol('_mapped_entry')['va'],'control_word_va':self.symbol('_kdes_control')['va'],'control_word_offset':self.offset(self.symbol('_kdes_control')['va'],4),'tt0_va':self.symbol('_tt0')['va'],'tt1_va':self.symbol('_tt1')['va'],'l2_va':self.symbol('_high_l2')['va'],'VA_minus_PA':0xffffffefc4000000,'TTBR1_L1_index':448,'TTBR1_L2_first_index':32,'L2_blocks':128,'L2_block_bytes':2*1024*1024,'kernel_MMU_qualified':False,'full_provider_startup_executed':False}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--verified',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);p.add_argument('--reuse-esp',type=Path,help='Retain exact instrumented ESP and unchanged fortify objects after a fixture-only guest/link repair');a=p.parse_args();m=a.root.resolve()
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh run required')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'builder.py').write_bytes(Path(__file__).read_bytes())
 runner=module('des_runner',WT/'src/platform/crypto/des/check.py');runner.ENV_OVERRIDES|={'LC_ALL':'C','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};runner.CHILD_ENV=dict(os.environ)|runner.ENV_OVERRIDES
 r={'outcome':'fail','task':'KRN-039','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'checks':[],'parents':{},'guest_executed':False,'full_provider_startup_executed':False,'full_kernel_qualified':False,'full_crypto_qualified':False,'native_device_qualified':False}
 def check(n,ok,**d):
  r['checks'].append(dict(name=n,passed=bool(ok),**d))
  if not ok:raise ValueError(n)
 def run(argv,label):
  v=runner.run(argv,out,label,30,256);r['commands'].append(v);check('command-'+label,v['outcome']=='pass' and v['exit_code']==0);return v
 try:
  state=load(m/'state/lab.json');t=next(x for x in state['tasks'] if x['id']=='KRN-039');e=next(x for x in state['experiments'] if x['id']==a.experiment);check('owned-active-prospective-plan',t['owner']==e['owner']=='codex-team-kernel-des-20261105-ci' and t['status']=='in_progress' and e['task']=='KRN-039' and e['status']=='planned');r['planning_record']=e
  native=load(a.native);verified=load(a.verified);check('passed-native-controls',native['outcome']==verified['outcome']=='pass');r['parents']={name:{'path':str(path.relative_to(m)),'sha256':sha(path)} for name,path in [('native',a.native),('verified',a.verified)]}
  graph=load(m/verified['coherent_component_manifest']['path']);check('actual988-graph-bound',sha(m/verified['coherent_component_manifest']['path'])==verified['coherent_component_manifest']['sha256']);rows={x['id']:x for x in graph['objects']}
  for row in graph['objects']:
   check('unchanged-native-object-'+row['id'],sha(m/row['output'])==row['output_sha256'])
  des=WT/'src/platform/crypto/des';fixture=WT/'fixtures/public/xnu-kernel-des';vectors=m/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/regenerated';r['source_inputs']={str(p.relative_to(WT)):sha(p) for p in sorted(fixture.rglob('*')) if p.is_file()};r['source_inputs'][str(Path(__file__).relative_to(WT))]=sha(__file__);r['vectors']={str(p.relative_to(m)):sha(p) for p in [vectors/'vectors.h',vectors/'vectors.json']}
  r['accepted_runtime']={'path':'fixtures/public/avf-handoff/runtime.h','sha256':sha(WT/'fixtures/public/avf-handoff/runtime.h')};cap=load(m/'docs/procedures/crypto-xts/qualified-evidence.json');check('unchanged-qualified-runtime',r['accepted_runtime']['sha256']==cap['owned_source_hashes']['fixtures/public/avf-handoff/runtime.h'])
  objects=out/'objects';objects.mkdir()
  retained_esp=None
  if a.reuse_esp:
   retained_esp=load(a.reuse_esp);check('retained-ESP-parent-qualified-source-stage',(retained_esp.get('error')=="ValueError('command-link-patched')" or (retained_esp.get('outcome')=='pass' and retained_esp.get('guest_images_ready'))) and len(retained_esp.get('fixture_components',[]))==4);r['parents']['retained-ESP']={'path':str(a.reuse_esp.relative_to(m)),'sha256':sha(a.reuse_esp)}
  def compile(source,template,label,extra=()):
   if retained_esp and label in ['esp-patched','esp-original','fortify']:
    row=next(x for x in retained_esp['fixture_components'] if x['output'].endswith('/'+label+'.o'));check('unchanged-exact-ESP-'+label,sha(source)==row['source_sha256'] and sha(m/row['output'])==row['output_sha256']);r.setdefault('fixture_components',[]).append(dict(row,reused_from=r['parents']['retained-ESP']));return m/row['output']
   argv=list(rows[template]['argv']) if 'argv' in rows[template] else None
   if argv is None:
    report=load(m/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json');argv=list(next(c['argv'] for c in report['commands'] if str(m/rows[template]['source']) in c['argv'] and '-c' in c['argv']));original=str(m/rows[template]['source']);cwd=next(c['cwd'] for c in report['commands'] if c['argv']==argv);argv=['-I'+cwd if x=='-I.' else x for x in argv]
   else:original=str(m/rows[template]['source'])
   argv[argv.index(original)]=str(source);dest=objects/(label+'.o');argv[argv.index('-o')+1]=str(dest);argv[argv.index('-MF')+1]=str(dest.with_suffix('.d'));argv+=['-I'+str(des),'-I'+str(fixture),'-I'+str(des/'vendor/include'),'-I'+str(des/'vendor/library'),'-isystem',str(m/'references/xnu-tapi/src/clang/lib/Headers'),'-I'+str(vectors),'-I'+str(WT/'fixtures/public/avf-handoff'),'-DMBEDTLS_CONFIG_FILE="s24_des_profile.h"','-Werror=incompatible-function-pointer-types','-Werror=incompatible-function-pointer-types-strict','-fstack-usage',*extra]
   run(argv,'compile-'+label);r.setdefault('fixture_components',[]).append({'source':str(source.relative_to(m)),'source_sha256':sha(source),'output':str(dest.relative_to(m)),'output_sha256':sha(dest),'template':template,'argv':argv});return dest
  body=(m/rows['bsd/esp_core.o']['source']).read_text();original_git=['git','-C',str(m/'references/apple-xnu'),'show','c54f35ca767986246321eb901baf8f5ff7923f6a:bsd/netinet6/esp_core.c'];v=subprocess.run(original_git,env=ENV,capture_output=True,timeout=10);check('exact-original-selected-ESP-source',v.returncode==0);r['original_source_read']={'argv':original_git,'exit_code':v.returncode,'sha256':hashlib.sha256(v.stdout).hexdigest()}
  proto='\nextern __attribute__((noreturn)) void kdes_fixture_fail(unsigned);\n/* Owned fixture boundary: unavailable logging fails if debug is enabled. No opaque SDK record is fabricated. Production source/object are unchanged. */\n#undef ipseclog\n#define ipseclog(x) do { if (ipsec_debug != 0) kdes_fixture_fail(__LINE__); } while (0)\nvoid kdes_before_block(struct secasvar *,struct mbuf *,struct mbuf *,struct mbuf *,struct mbuf *,unsigned char *,unsigned char *);\n'
  appended=(fixture/'esp_fixture.c').read_text();espobjects={}
  for label,text in [('patched',body),('original',v.stdout.decode())]:
   needle='static int esp_null_mature(struct secasvar *);';check('unique-accessor-prototype-point-'+label,text.count(needle)==1);text=text.replace(needle,proto+needle)
   hook='\t\t// no need to check output pointer alignment';check('two-real-block-hook-points-'+label,text.count(hook)==2);text=text.replace(hook,'\t\tkdes_before_block(sav,m,scut,d0,d,sp,sbuf);\n'+hook)
   path=out/('esp-'+label+'.c');path.write_text(text+'\n/* BEGIN OWNED FOCUSED FIXTURE */\n'+appended);espobjects[label]=compile(path,'bsd/esp_core.o','esp-'+label,['-DKDES_ORIGINAL_CALLER'] if label=='original' else [])
  guest=compile(fixture/'guest.c','libkern/corecrypto_des.o','guest',['-mgeneral-regs-only','-mstrict-align','-mno-outline-atomics']);memory=compile(fixture/'memory.c','libkern/corecrypto_des.o','fortify')
  old=load(m/'docs/procedures/kernel-xts/qualified-evidence.json');strict=load(m/old['reports']['strict_native']['path']);prior=load(m/strict['parents']['retained-native']['path']);memrow=next(x for x in prior['components'] if x['id']=='fixture/memory');check('unchanged-qualified-byte-runtime',sha(m/memrow['output'])==memrow['output_sha256'] and sha(m/memrow['source'])==memrow['source_sha256']);r['byte_runtime']=memrow
  ld=m/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld';check('qualified-linker',sha(ld)==cap['tools']['ld']['sha256']);r['linker']={'path':str(ld),'sha256':sha(ld)}
  retained=[rows[x] for x in ['libkern/corecrypto_des.o','component/des-kernel-provider','component/des','component/mbedtls-des','component/xts','component/aes','libkern/register_crypto.o']];r['retained_components']=retained
  images={}
  for label in ['patched','original']:
   dest=out/(label+'.macho');argv=[ld,'-arch','arm64','-static','-dead_strip','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[m/x['output'] for x in retained],m/memrow['output'],espobjects[label],guest,memory,'-o',dest];run(argv,'link-'+label);images[label]={'path':str(dest.relative_to(m)),'sha256':sha(dest),'mapping_proof':Image(dest).proof()}
  positive=out/'patched.macho';data=bytearray(positive.read_bytes());proof=images['patched']['mapping_proof'];check('real-linked-control-word',struct.unpack_from('<I',data,proof['control_word_offset'])==(0x4b444553,))
  for label,value in [('corrupt-answer',1),('panic',2),('spin',3)]:
   raw=bytearray(data);struct.pack_into('<I',raw,proof['control_word_offset'],value);dest=out/(label+'.macho');dest.write_bytes(raw);parsed=Image(dest);check('control-only-image-delta-'+label,sum(x!=y for x,y in zip(raw,data))<=4 and len(raw)==len(data));images[label]={'path':str(dest.relative_to(m)),'sha256':sha(dest),'mapping_proof':parsed.proof(),'control_word':value}
  r['images']=images;r['guest_images_ready']=True;r['outcome']='pass'
 except Exception as error:r['error']=repr(error)
 finally:
  r['resource_admission_wait_seconds']=runner.RESOURCE_WAIT_USED;r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['sha256']={str(p.relative_to(m)):sha(p) for p in out.rglob('*') if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ['outcome','error','guest_images_ready']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
