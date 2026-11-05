#!/usr/bin/env python3
"""Continue a digest-verified memory-deferred positive host/ARM run, no rerun claim."""
import argparse,copy,datetime,hashlib,importlib.util,json,os,re,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
os.environ.update(GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
spec=importlib.util.spec_from_file_location('accepted_xts',MAIN/'src/platform/crypto/xts/check.py');xts=importlib.util.module_from_spec(spec);spec.loader.exec_module(xts)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',required=True,type=Path);p.add_argument('--run',required=True);args=p.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('plain fresh run required')
 out=ROOT/'artifacts/crypto-gcm'/args.run;out.mkdir(parents=True,exist_ok=False);(out/'executed-finish_arm.py').write_bytes(Path(__file__).read_bytes())
 prior=args.parent.resolve();old=json.loads(prior.read_text());report=copy.deepcopy(old);report.update(outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],stage_parent={'path':str(prior),'sha256':sha(prior)},prior_commands=old['commands'],original_deferral=old.get('deferred'))
 report.pop('error',None);report.pop('deferred',None)
 def command(argv,name,expected=0,seconds=30,budget=256):
  available=int(re.search(r'^MemAvailable:\s+(\d+) kB',Path('/proc/meminfo').read_text(),re.M)[1])
  if available<4*1024*1024:report['deferred']={'name':name,'mem_available_kib':available};raise RuntimeError('Deferred below4GiB MemAvailable')
  r=xts.run(argv,out,name,seconds,budget);r['mem_available_kib']=available;report['commands'].append(r)
  if r['exit_code']!=expected or r['outcome'] in ['rss-limit','timeout']:raise ValueError('Bounded stage failed:'+name)
  return r
 try:
  if not old.get('host_checks') or old.get('deferred',{}).get('name')!='arm-vectors' or len(old.get('profile_rejections',[]))!=4 or not all(x['rejected'] for x in old['profile_rejections']):raise ValueError('Exact positive host plus qualified memory-deferred ARM stage required')
  for name,digest in old['artifact_hashes'].items():
   if sha(MAIN/name)!=digest:raise ValueError('Prior artifact changed:'+name)
  for name,digest in old['owned_source_hashes'].items():
   if sha(ROOT/name)!=digest:raise ValueError('Tested source changed:'+name)
  for name,value in old['source_member_checks'].items():
   if sha(name)!=value['actual_sha256']:raise ValueError('Full-archive audited dependency changed')
  for tool in old['tools'].values():
   if sha(tool['path'])!=tool['sha256']:raise ValueError('Qualified compiler changed')
  accepted=json.loads(Path(old['parent']['path']).read_text())
  report['shared_owned_source_checks']={}
  for name,digest in accepted['owned_source_hashes'].items():
   if name.startswith('src/platform/crypto/xts/'):
    if sha(MAIN/name)!=digest:raise ValueError('Accepted shared AES/profile/zeroizer source changed:'+name)
    report['shared_owned_source_checks'][str(MAIN/name)]=digest
  arm=Path(old['tools']['arm']['path']);flags=old['actual_native_compile_profile']['derived_flags'];build=prior.parent
  for name in ['vectors.json','vectors.bin']:(out/name).write_bytes((build/name).read_bytes())
  sources=[('vectors',build/'vectors.S'),('typed',HERE/'typed.c'),('guest',HERE/'guest.c'),('spin',HERE/'guest.c')]
  for name,source in sources:command([arm,*flags,*(['-DGCM_SPIN'] if name=='spin' else []),'-MMD','-MF',out/('arm-'+name+'.d'),'-c',source,'-o',out/('arm-'+name+'.o')],'arm-'+name)
  sys.path.insert(0,str(MAIN/'tools/build'));from xnu_kernel_syscalls import ObjectData
  view=ObjectData(build/'arm-adapter.o').value('_s24_gcm_layout','<6Q');report['layout']=dict(zip(['owned_bytes','owned_alignment','backend_bytes','block_cipher_bytes','AES_bytes','ccmode_gcm_bytes'],view))
  if not(view[0]<=2048 and view[1]==16 and view[4]==288 and view[5]==80):raise ValueError('Actual native context layout failed')
  objects=[build/('arm-'+name+'.o') for name in ['adapter','backend','block','constant','probe']]+[out/'arm-vectors.o']
  nm=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm');report['symbol_tool']={'path':str(nm),'sha256':sha(nm)}
  command([nm,'--undefined-only',*objects],'arm-imports');text=(out/'arm-imports.log').read_text();report['no_heap_profile']=not any(re.search(r'\b_'+name+r'\b',text) for name in ['malloc','calloc','realloc','free','mbedtls_cipher_setup','psa_import_key','__assert_fail'])
  if not report['no_heap_profile']:raise ValueError('Forbidden allocating/generic/assert import')
  xtsbuild=Path(old['parent']['path']).parent;shared=[xtsbuild/('arm-'+name+'.o') for name in ['adapter','aes','memory']];report['reused_arm_objects']={str(p):sha(p) for p in shared};report['reused_stage_objects']={str(p):sha(p) for p in objects if p.parent==build}
  ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld';report['linker']={'path':str(ld),'sha256':sha(ld)};report['images']={}
  for mode,last in [('normal','guest'),('spin','spin')]:
   command([ld,'-arch','arm64','-static','-e','_gcm_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*objects,*shared,out/('arm-'+last+'.o'),'-o',out/(mode+'.macho')],mode+'-link')
   report['images'][mode]=xts.avf.macho(out/(mode+'.macho'))
  report['dependencies']={};report['selected_source_checks']={}
  for dep in [*build.glob('*.d'),*out.glob('*.d')]:
   for raw in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():
    path=Path(raw).resolve();digest=sha(path);report['dependencies'][str(path)]=digest
    if '/src/platform/crypto/' in str(path) and '/vendor/' in str(path) and str(path) not in report['source_member_checks']:raise ValueError('Consumed unaudited backend header:'+str(path))
    reference=None
    if '/EXTERNAL_HEADERS/corecrypto/' in str(path):reference=MAIN/'references/apple-xnu';relative='EXTERNAL_HEADERS/'+str(path).split('/EXTERNAL_HEADERS/',1)[1];revision='c54f35ca767986246321eb901baf8f5ff7923f6a'
    elif str(path).endswith('/libkern/libkern/crypto/register_crypto.h'):reference=MAIN/'references/apple-xnu';relative='libkern/libkern/crypto/register_crypto.h';revision='c54f35ca767986246321eb901baf8f5ff7923f6a'
    elif path.is_relative_to(MAIN/'references/xnu-tapi/src/clang/lib/Headers'):reference=MAIN/'references/xnu-tapi';relative=str(path.relative_to(reference));revision='fa9443738c1a18accef4244732ec6d6ee97a8133'
    if reference and str(path) not in report['selected_source_checks']:
     raw=subprocess.check_output(['git','-C',reference,'show',revision+':'+relative],env=os.environ)
     if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Genuine native header differs:'+relative)
     report['selected_source_checks'][str(path)]={'revision':revision,'sha256':digest}
  report['outcome']='pass';report['summary']='Combined immutable positive sanitized host corpus and actual genuine typed ARM layout/profile/images. Original host report retained memory-deferred; this continuation executes only missing ARM steps. CPU execution pending.'
 except Exception as error:report['error']=repr(error)
 finally:
  report['owned_source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
  report['artifact_hashes'].update({str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()});report['artifact_hashes'][str(prior.relative_to(MAIN))]=sha(prior);report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','host_checks','layout','no_heap_profile']},indent=2));return report['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
