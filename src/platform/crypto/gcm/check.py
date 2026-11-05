#!/usr/bin/env python3
"""Own bounded GCM qualification; shared accepted AES/zeroizer/helpers are read-only."""
import argparse,datetime,hashlib,importlib.util,json,os,re,subprocess,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
GUARDS={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1'};os.environ.update(GUARDS)
spec=importlib.util.spec_from_file_location('accepted_xts_runner',MAIN/'src/platform/crypto/xts/check.py');xts=importlib.util.module_from_spec(spec);spec.loader.exec_module(xts)
def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def memory():return int(re.search(r'^MemAvailable:\s+(\d+) kB',Path('/proc/meminfo').read_text(),re.M)[1])
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--mode',choices=['abi','host'],default='abi');args=p.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('plain fresh run name required')
 out=ROOT/'artifacts/crypto-gcm'/args.run;out.mkdir(parents=True,exist_ok=False)
 (out/'executed-check.py').write_bytes(Path(__file__).read_bytes())
 report={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'inputs':{},'provider_registered':False,'xnu_executed':False,'native_device':False,'full_crypto_qualified':False,'fips_qualified':False,'side_channel_qualified':False}
 def command(argv,name,expected=0,seconds=30,budget=256):
  available=memory()
  if available<4*1024*1024:
   report['deferred']={'name':name,'mem_available_kib':available};raise RuntimeError('Deferred below4GiB MemAvailable')
  r=xts.run(argv,out,name,seconds,budget);r['mem_available_kib']=available;report['commands'].append(r)
  if expected is not None and (r['exit_code']!=expected or r['outcome'] in ['rss-limit','timeout']):raise ValueError(name+' failed: '+str(r['exit_code']))
  return r
 try:
  report['commit']=subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD'],text=True,env=os.environ).strip()
  parent=MAIN/'docs/procedures/crypto-xts/qualified-evidence.json';qualified=json.loads(parent.read_text());oldpath=MAIN/qualified['report']
  if sha(oldpath)!=qualified['report_sha256']:raise ValueError('Accepted XTS report changed')
  old=json.loads(oldpath.read_text());report['parent']={'path':str(oldpath),'sha256':sha(oldpath)}
  for name,digest in old['artifact_hashes'].items():
   if sha(Path(name) if Path(name).is_absolute() else oldpath.parents[3]/name)!=digest:raise ValueError('Accepted XTS artifact changed:'+name)
  for name,digest in json.loads((HERE/'vendor/provenance.json').read_text())['files'].items():
   if sha(HERE/'vendor'/name)!=digest:raise ValueError('Pinned GCM backend changed')
  shared=MAIN/'src/platform/crypto/xts/vendor';backend=HERE/'vendor'
  for name,digest in json.loads((shared/'provenance.json').read_text())['files'].items():
   if sha(shared/name)!=digest:raise ValueError('Accepted shared AES source changed')
  archive=ROOT/'artifacts/crypto-gcm/source-session1/mbedtls.tar.gz'
  if sha(archive)!='ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937':raise ValueError('Full upstream archive changed')
  report['source_archive']={'path':str(archive),'sha256':sha(archive)};report['source_member_checks']={}
  with tarfile.open(archive) as tar:
   prefix=tar.getmembers()[0].name+'/'
   for directory in [shared,backend]:
    prov=json.loads((directory/'provenance.json').read_text())
    for name,digest in prov['files'].items():
     raw=tar.extractfile(prefix+name).read();upstream=hashlib.sha256(raw).hexdigest();patch=prov.get('patches',{}).get(name)
     if patch:
      if upstream!=patch['upstream_sha256'] or digest!=patch['local_sha256']:raise ValueError('Shared patch pre/postimage mismatch')
     elif upstream!=digest:raise ValueError('Truncated or changed full-archive member:'+name)
     report['source_member_checks'][str(directory/name)]={'full_archive_sha256':upstream,'actual_sha256':sha(directory/name),'accepted_patch':patch}
  host=Path(old['tools']['host']['path']);arm=Path(old['tools']['arm']['path']);ndk=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin')
  for name,tool in [('host',host),('arm',arm)]:
   if sha(tool)!=old['tools'][name]['sha256']:raise ValueError('Accepted compiler changed')
  report['tools']=old['tools'];report['inputs'][str(MAIN/'src/platform/crypto/xts/check.py')]=sha(MAIN/'src/platform/crypto/xts/check.py')
  common=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-I'+str(HERE),'-I'+str(backend/'include'),'-I'+str(shared/'include'),'-I'+str(backend/'library'),'-I'+str(shared/'library'),'-DMBEDTLS_CONFIG_FILE="s24_gcm_profile.h"']
  hostflags=[*common,'--target=x86_64-unknown-linux-gnu','-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-DGCM_PROBE_HOST']
  if args.mode=='host':
   command([sys.executable,HERE/'vectors.py',ROOT/'artifacts/crypto-gcm/source-session2/nist-1.zip',out],'vector-oracle',seconds=90,budget=256)
   hostflags += ['-I'+str(out)]
   report['corpus']={k:v for k,v in json.loads((out/'vectors.json').read_text()).items() if k!='vectors'}
  sources=[('adapter',HERE/'gcm.c'),('backend',backend/'library/gcm.c'),('block',backend/'library/block_cipher.c'),('constant',backend/'library/constant_time.c'),('probe',HERE/('suite.c' if args.mode=='host' else 'probe.c'))]+([('vectors',out/'vectors.S')] if args.mode=='host' else [])
  for name,source in sources:command([host,*hostflags,'-MMD','-MF',out/('host-'+name+'.d'),'-c',source,'-o',out/('host-'+name+'.o')],'host-'+name)
  reused={name:oldpath.parent/('host-'+name+'.o') for name in ['adapter','aes']}
  report['reused_host_objects']={str(v):sha(v) for v in reused.values()}
  command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',*[out/('host-'+n+'.o') for n,_ in sources],*reused.values(),'-o',out/'host-probe'],'host-probe-link')
  command([out/'host-probe'],'host-probe-run',budget=512)
  text=(out/'host-probe-run.log').read_text()
  if args.mode=='abi':
   if 'GCM PROBE PASS failure=0' not in text:raise ValueError('Actual initial GCM algorithm marker absent')
  else:
   found=re.search(r'GCM HOST PASS vectors=(\d+) checks=(\d+) failure_line=0',text)
   if not found:raise ValueError('Actual full GCM host marker absent')
   report['host_vectors']=int(found[1]);report['host_checks']=int(found[2])
   report['profile_rejections']=[]
   for option in ['MBEDTLS_GCM_ALT','MBEDTLS_CIPHER_C','MBEDTLS_PSA_CRYPTO_C','MBEDTLS_AESNI_C']:
    r=command([host,*hostflags,'-D'+option,'-c',HERE/'gcm.c','-o',out/('reject-'+option+'.o')],'reject-'+option,expected=None)
    ok=r['exit_code']!=0 and 'Unqualified' in (out/('reject-'+option+'.log')).read_text();report['profile_rejections'].append({'macro':option,'rejected':ok})
    if not ok:raise ValueError('Unqualified profile admitted')
   control=MAIN/'src/platform/crypto/xts/sanitizer_control.c';report['inputs'][str(control)]=sha(control)
   command([host,'--target=x86_64-unknown-linux-gnu','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',control,'-o',out/'sanitizer-control'],'sanitizer-control-compile')
   for name,extra,marker in [('asan-heap',['heap'],'AddressSanitizer: heap-buffer-overflow'),('ubsan-overflow',[],'runtime error: signed integer overflow')]:
    r=command([out/'sanitizer-control',*extra],name,expected=None,budget=512);ok=r['exit_code']!=0 and marker in (out/(name+'.log')).read_text()
    if not ok:raise ValueError('Actual sanitizer control failed:'+name)
  native=MAIN/'artifacts/xnu-kernel-declarations/controls-session1/report.json';profile=json.loads(native.read_text());source=MAIN/profile['source_ports']['osfmk/mc_provider.o']['source'];recipe=next(c for c in profile['commands'] if str(source) in c['argv'] and '-c' in c['argv'])
  flags=list(recipe['argv'][1:])
  for option in ['-o','-MF']:
   index=flags.index(option);del flags[index:index+2]
  flags=[v for v in flags if not v.startswith('-W') and v not in ['-c','-MD','-MP','-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang'] and v!=str(source)]
  flags=['-I'+recipe['cwd'] if v=='-I.' else v for v in flags]
  flags += [*common,'-isystem',str(MAIN/'references/xnu-tapi/src/clang/lib/Headers'),'-DS24_XTS_FREESTANDING','-ffreestanding','-fno-pic','-fno-pie','-fno-stack-protector','-fno-jump-tables','-mstrict-align','-mgeneral-regs-only','-mno-outline-atomics']
  if args.mode=='host':flags += ['-I'+str(out)]
  report['actual_native_compile_profile']={'source_report':str(native),'sha256':sha(native),'original_recipe':recipe,'derived_flags':flags}
  for name,source in sources+[('typed',HERE/'typed.c')]:command([arm,*flags,'-MMD','-MF',out/('arm-'+name+'.d'),'-c',source,'-o',out/('arm-'+name+'.o')],'arm-'+name)
  sys.path.insert(0,str(MAIN/'tools/build'));from xnu_kernel_syscalls import ObjectData
  view=ObjectData(out/'arm-adapter.o').value('_s24_gcm_layout','<6Q');report['layout']=dict(zip(['owned_bytes','owned_alignment','backend_bytes','block_cipher_bytes','AES_bytes','ccmode_gcm_bytes'],view))
  if not(view[0]<=2048 and view[1]==16 and view[4]==288 and view[5]==80):raise ValueError('Actual target layout/profile mismatch')
  command([ndk/'llvm-nm','--undefined-only',*[out/('arm-'+name+'.o') for name,_ in sources]],'arm-imports')
  undefined=(out/'arm-imports.log').read_text();report['no_heap_profile']=not any(re.search(r'\b_'+name+r'\b',undefined) for name in ['malloc','calloc','realloc','free','mbedtls_cipher_setup','psa_import_key'])
  if not report['no_heap_profile']:raise ValueError('Forbidden allocating/generic cipher import')
  if args.mode=='host':
   ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld';report['linker']={'path':str(ld),'sha256':sha(ld)}
   for name,extra in [('guest',[]),('spin',['-DGCM_SPIN'])]:
    command([arm,*flags,*extra,'-MMD','-MF',out/('arm-'+name+'.d'),'-c',HERE/'guest.c','-o',out/('arm-'+name+'.o')],'arm-'+name)
   report['reused_arm_objects']={str(oldpath.parent/('arm-'+name+'.o')):sha(oldpath.parent/('arm-'+name+'.o')) for name in ['adapter','aes','memory']}
   sys.path.insert(0,str(MAIN/'tools/verify'));import avf_handoff as avf
   report['images']={}
   for mode,last in [('normal','guest'),('spin','spin')]:
    command([ld,'-arch','arm64','-static','-e','_gcm_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[out/('arm-'+name+'.o') for name,_ in sources],*[Path(x) for x in report['reused_arm_objects']],out/('arm-'+last+'.o'),'-o',out/(mode+'.macho')],mode+'-link')
    report['images'][mode]=avf.macho(out/(mode+'.macho'))
  report['dependencies']={}
  for dep in out.glob('*.d'):
   for raw in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():report['dependencies'][raw]=sha(raw)
  report['selected_source_checks']={}
  for name,digest in report['dependencies'].items():
   path=Path(name).resolve()
   if path.is_relative_to(shared) or path.is_relative_to(backend):
    if str(path) not in report['source_member_checks']:raise ValueError('Unaudited consumed Mbed file:'+str(path))
   reference=None;relative=None
   if '/EXTERNAL_HEADERS/corecrypto/' in str(path):reference=MAIN/'references/apple-xnu';relative='EXTERNAL_HEADERS/'+str(path).split('/EXTERNAL_HEADERS/',1)[1];revision='c54f35ca767986246321eb901baf8f5ff7923f6a'
   elif str(path).endswith('/libkern/libkern/crypto/register_crypto.h'):reference=MAIN/'references/apple-xnu';relative='libkern/libkern/crypto/register_crypto.h';revision='c54f35ca767986246321eb901baf8f5ff7923f6a'
   elif path.is_relative_to(MAIN/'references/xnu-tapi/src/clang/lib/Headers'):reference=MAIN/'references/xnu-tapi';relative=str(path.relative_to(reference));revision='fa9443738c1a18accef4244732ec6d6ee97a8133'
   if reference:
    raw=subprocess.check_output(['git','-C',reference,'show',revision+':'+relative],env=os.environ)
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Actual pinned header differs:'+relative)
    report['selected_source_checks'][str(path)]={'revision':revision,'sha256':digest}
  report['outcome']='pass';report['summary']='Actual sanitized host GCM vectors and typed ARM layout/profile plus real synthetic images; CPU execution not yet performed' if args.mode=='host' else 'Actual initial sanitized GCM result and genuine ARM callbacks/layout;not full vector/CPU qualification'
 except Exception as error:report['error']=repr(error)
 finally:
  report.setdefault('summary','Failed actual GCM profile/type/initial algorithm qualification;retained diagnostics')
  report['owned_source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
  report['artifact_hashes']={str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()};report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','layout','no_heap_profile']},indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
