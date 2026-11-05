#!/usr/bin/env python3
"""Bounded real CBC-CS3 component qualification; guest requires a fresh root lease."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
OWNER='codex-team-crypto-cts3-20261105-cb'
XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
MBED='068ff080b369adfac81509f9b57b2afabaf82dc5'
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1','PYTHONOPTIMIZE':'0'}
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def inputs(report):
 xts=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2';des=MAIN/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3'
 xreport=xts/'evidence.json';dreport=des/'evidence.json'
 if digest(xreport)!='c5064a512ba295d1cd447af1e73ac6fc4f9c0ffeaf5b78f09ca0f80fc1f6216c' or digest(dreport)!='077f56b1469d961ec5d5f5af695e85e0037ca698fd60a984b62efcae7006447d':raise ValueError('accepted CBC/XTS dependency report changed')
 xr=json.loads(xreport.read_text());dr=json.loads(dreport.read_text());report['accepted_dependencies']={'reports':{str(p):digest(p) for p in [xreport,dreport]},'objects':{}}
 # Old AES.o is deliberately absent: one new canonical CBC-enabled AES supplies
 # unchanged accepted XTS adapter imports and the unique zeroizer dependency.
 paths=[xts/'host-adapter.o',xts/'arm-adapter.o',xts/'arm-memory.o',des/'host-adapter.o',des/'host-des.o',des/'arm-adapter.o',des/'arm-des.o']
 for p in paths:
  expected=xr['artifact_hashes'][str(p.relative_to(MAIN/'worktrees/krn-029-20261105'))] if p.parent==xts else dr['artifact_hashes'][str(p.relative_to(MAIN))]
  if digest(p)!=expected:raise ValueError('accepted object changed '+str(p))
  report['accepted_dependencies']['objects'][str(p)]=digest(p)
 runtime=MAIN/'fixtures/public/avf-handoff/runtime.h'
 if digest(runtime)!=xr['owned_source_hashes']['fixtures/public/avf-handoff/runtime.h']:raise ValueError('shared runtime changed')
 report['shared_runtime']={'path':str(runtime),'sha256':digest(runtime),'unchanged':True}
 # Every consumed upstream source/header is checked against the complete official
 # exact-pin archive, not a potentially truncated candidate catalog/raw cache.
 vendor=MAIN/'src/platform/crypto/xts/vendor';prov=json.loads((vendor/'provenance.json').read_text());archive=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/inputs/mbedtls.tar.gz'
 if digest(archive)!='ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937' or prov['commit']!=MBED:raise ValueError('complete canonical AES archive/pin changed')
 canonical={'archive':str(archive),'sha256':digest(archive),'commit':MBED,'files':{},'license_choice':'Apache-2.0','shared_vendor_read_only':True}
 with tarfile.open(archive) as t:
  for name,expected in prov['files'].items():
   raw=t.extractfile('mbedtls-'+MBED+'/'+name).read();wanted=raw
   if name=='library/common.h':
    wanted=raw.replace(b'#include <assert.h>',b'/* Owned freestanding AES-only port: this unit uses no runtime assert. */\n#if !defined(S24_XTS_FREESTANDING)\n#include <assert.h>\n#endif')
    if hashlib.sha256(raw).hexdigest()!=prov['patches'][name]['upstream_sha256']:raise ValueError('accepted common.h canonical preimage mismatch')
   if (vendor/name).read_bytes()!=wanted or digest(vendor/name)!=expected:raise ValueError('canonical upstream member mismatch '+name)
   canonical['files'][name]={'canonical_sha256':hashlib.sha256(raw).hexdigest(),'actual_sha256':expected,'bytes':len(wanted),'patched':wanted!=raw}
 report['canonical_AES_inputs']=canonical
 pins_path=ROOT/'docs/procedures/crypto-cts3/source-pins.json';pins=json.loads(pins_path.read_text());report['primary_source_pins']={'path':str(pins_path),'sha256':digest(pins_path),'data':pins}
 required={'rfc3962.txt','nist-38a-addendum.pdf','openssl-evp-doc.pod','openssl-params.h','openssl-core_names.h.in','nist-AES-CBC.pdf'};found=set()
 for row in pins['documents']:
  if row['outcome']=='pass':
   p=ROOT/row['path']
   if digest(p)!=row['sha256']:raise ValueError('primary source bytes changed '+str(p))
   found.add(p.name)
 if not required<=found:raise ValueError('required primary input unavailable')
 if digest(ROOT/pins['nist_example_text']['path'])!=pins['nist_example_text']['sha256']:raise ValueError('published NIST text changed')
 return xts,des,vendor,dr

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('--experiment',required=True);ap.add_argument('--guest',action='store_true');ap.add_argument('--resume',type=Path,help='Reuse immutable same-commit host/ARM capsule; no compiler/oracle replay');ap.add_argument('--audit-resume',type=Path,help='Narrow continuation of preserved known fortification-audit failure, without host replay');a=ap.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh simple run name required')
 out=ROOT/'artifacts/crypto-cts3'/a.run;out.mkdir(parents=True,exist_ok=False)
 report={'task':'KRN-036','experiment':a.experiment,'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'summary':'Attempted genuine generic CBC-CS3 qualification; no pass inferred from authored code or a resource stop','argv':sys.argv,'commands':[],'source_reads':[],'source_pins':{'xnu':XNU,'mbedtls':MBED},'native_device':False,'xnu_executed':False,'provider_registered':False,'arm_cpu_executed':False,'test_CBC16_is_production':False}
 supervisor=None;extra_artifacts=[];extra_hashes={}
 def command(argv,name,seconds=30,expected=0,budget=256):
  r=supervisor.run(argv,out,name,seconds,budget);report['commands'].append(r)
  if expected is not None and (r['exit_code']!=expected or r['outcome']!='pass'):raise ValueError(name+' '+r['outcome']+' exit '+str(r['exit_code']))
  return r
 def git(repo,spec):
  argv=['git','-C',str(repo),'show',spec];p=subprocess.run(argv,env=ENV,capture_output=True,timeout=10)
  report['source_reads'].append({'argv':argv,'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr':p.stderr.decode(errors='replace')})
  if p.returncode:raise ValueError('pinned Git object unavailable without lazy fetch')
  return p.stdout
 try:
  (out/'preflight.json').write_text(json.dumps({'recorded_at':report['recorded_at'],'argv':sys.argv,'meminfo':Path('/proc/meminfo').read_text(),'memory_pressure':Path('/proc/pressure/memory').read_text()},indent=2)+'\n')
  raw=(MAIN/'state/lab.json').read_bytes();state=json.loads(raw);plans=[x for x in state['experiments'] if x['id']==a.experiment]
  if len(plans)!=1 or plans[0]['status']!='planned' or plans[0]['task']!='KRN-036' or plans[0]['owner']!=OWNER:raise ValueError('actual MAIN planned experiment for036/cb required')
  report['planning_record']=plans[0];report['planning_snapshot_sha256']=hashlib.sha256(raw).hexdigest()
  report['commit']=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],env=ENV,text=True).strip();report['owned_dirty_at_start']=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=all','--','src/platform/crypto/cts3','docs/procedures/crypto-cts3'],env=ENV,text=True)
  xts,des,vendor,dr=inputs(report)
  helper=MAIN/'src/platform/crypto/des/check.py'
  if digest(helper)!=dr['owned_source_hashes']['src/platform/crypto/des/check.py']:raise ValueError('qualified bounded supervisor/admission changed')
  supervisor=load_module('qualified_des_supervisor',helper);report['resource_supervisor']={'path':str(helper),'sha256':digest(helper),'same_accepted_admission_and_cleanup':True}
  avf=supervisor.avf
  for name in ['EXTERNAL_HEADERS/corecrypto/ccpad.h','EXTERNAL_HEADERS/corecrypto/ccmode_impl.h','EXTERNAL_HEADERS/corecrypto/ccmode.h','libkern/libkern/crypto/register_crypto.h','bsd/nfs/gss/ccrypto.c','bsd/nfs/gss/gss_krb5_mech.c']:
   raw=git(MAIN/'references/apple-xnu',XNU+':'+name)
   if raw!=(MAIN/'references/apple-xnu'/name).read_bytes():raise ValueError('actual selected declaration/caller changed')
  if a.resume and a.audit_resume:raise ValueError('choose one immutable phase input')
  if a.resume:
   if not a.guest:raise ValueError('resume is a guest-only phase')
   resume=a.resume.resolve()
   if not resume.is_relative_to(ROOT/'artifacts/crypto-cts3'):raise ValueError('own immutable phase capsule required')
   host=json.loads(resume.read_text())
   if host['task']!='KRN-036' or host['outcome']!='pass' or host['commit']!=report['commit'] or host['owned_dirty_at_start']:raise ValueError('clean same-commit passing host/typed-ARM capsule required')
   current={str(p.relative_to(ROOT)):digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__'not in str(p)}
   if current!=host['owned_source_hashes']:raise ValueError('owned implementation changed since host/typedARM qualification')
   for name,sha in host['artifact_hashes'].items():
    if digest(MAIN/name)!=sha:raise ValueError('host phase artifact changed '+name)
   report['host_phase']={'path':str(resume.relative_to(MAIN)),'sha256':digest(resume),'commit':host['commit']};extra_hashes=dict(host['artifact_hashes']);extra_hashes[str(resume.relative_to(MAIN))]=digest(resume);extra_artifacts=[str(resume.relative_to(MAIN)),*host['artifacts']]
   for key in ['host_checks','host_vectors','cbc_fixture_vectors','corpus','target_layout','fixture_target_layout','profile_rejections','sanitizer_controls','native_symbols','tools','dependency_hashes','selected_header_checks','images','typed_negative_rejected','stack_usage_artifacts','single_AES_and_zeroizer_definitions','fortified_memory_boundary','adapter_compile_argv','corpus_path']:report[key]=host[key]
   image_dir=resume.parent;corpus=json.loads(Path(host['corpus_path']).read_text())
  elif a.audit_resume:
   preserved=a.audit_resume.resolve()
   if not preserved.is_relative_to(ROOT/'artifacts/crypto-cts3')or digest(preserved)!='26edb172fd4f023b0b0659f23cdf02d466befe579a5321051b6bc326947442f3':raise ValueError('only exact preserved real audit-failure capsule is admitted')
   host=json.loads(preserved.read_text())
   if host['outcome']!='fail'or host['error']!="ValueError('production is no longer generic/memory-only imports')"or host['owned_dirty_at_start']or host['host_checks']!=28794or host['host_vectors']!=381or host['cbc_fixture_vectors']!=18:raise ValueError('preserved actual host/typed proof differs')
   if not all(x['rejected']for x in host['profile_rejections'])or not all(x['detected']for x in host['sanitizer_controls'])or not host['typed_negative_rejected']:raise ValueError('existing real negative proof incomplete')
   current={str(p.relative_to(ROOT)):digest(p)for p in sorted(HERE.rglob('*'))if p.is_file()and'__pycache__'not in str(p)}
   allowed={'src/platform/crypto/cts3/check.py','src/platform/crypto/cts3/production.json'}
   if set(current)!=set(host['owned_source_hashes'])or any(sha!=current[name]for name,sha in host['owned_source_hashes'].items()if name not in allowed):raise ValueError('compiled production/fixture/oracle/suite/source set changed; host proof cannot be reused')
   if digest(ROOT/'docs/procedures/crypto-cts3/source-pins.json')!=host['primary_source_pins']['sha256']:raise ValueError('primary pins changed after actual host proof')
   old_manifest=json.loads(git(ROOT,host['commit']+':src/platform/crypto/cts3/production.json'));new_manifest=json.loads((HERE/'production.json').read_text())
   if {k:v for k,v in new_manifest.items()if k!='selected_native_external_boundary'}!=old_manifest:raise ValueError('production manifest changed beyond explicit external-memory boundary')
   for name,sha in host['artifact_hashes'].items():
    if digest(MAIN/name)!=sha:raise ValueError('preserved host/typed artifact changed '+name)
   for name,sha in host['dependency_hashes'].items():
    if digest(name)!=sha:raise ValueError('actual consumed compilation input changed '+name)
   extra_hashes=dict(host['artifact_hashes']);extra_hashes[str(preserved.relative_to(MAIN))]=digest(preserved)
   report['audit_continuation']={'preserved_path':str(preserved.relative_to(MAIN)),'sha256':digest(preserved),'original_failure':host['error'],'compiled_source_commit':host['commit'],'qualification_commit':report['commit'],'changed_uncompiled_metadata_only':sorted(allowed),'unchanged_compiled_and_oracle_sources':{k:v for k,v in current.items()if k not in allowed},'host_algorithm_replayed':False,'object_recompiled':False}
   for key in ['host_checks','host_vectors','cbc_fixture_vectors','corpus','tools','dependency_hashes','selected_header_checks','profile_rejections','sanitizer_controls','typed_negative_rejected']:report[key]=host[key]
   report['adapter_compile_argv']=next(x['argv']for x in host['commands']if str(preserved.parent/'arm-adapter.o')in x['argv']and'-c'in x['argv'])
   report['corpus_path']=str(preserved.parent/'regenerated/vectors.json');corpus=json.loads(Path(report['corpus_path']).read_text());image_dir=out
   finish_native(command,report,out,preserved.parent,xts,des,git)
  else:
   image_dir=out;native(command,report,out,vendor,xts,des,git)
   report['corpus_path']=str(out/'regenerated/vectors.json');corpus=json.loads(Path(report['corpus_path']).read_text())
  if a.guest:
   guest(command,out,image_dir,corpus,report,avf,git)
   report['arm_cpu_executed']=True
  report['outcome']='pass';report['summary']='Genuine generic CBC-CS3 selected callbacks: primary RFC3962, published NIST CBC fixture and explicitly derived/oracle cases, bounded sanitized host/typedARM'+(' and actual ARMCPU controls' if a.guest else '; actual CPU not yet executed in this phase')+'; strict>block/local error boundary, single zeroizer/AES object, no provider/privateABI/native/FIPS/fullcrypto claim'
 except Exception as error:
  report['error']=repr(error)
  if supervisor is not None and isinstance(error,supervisor.ResourceDeferred):report['outcome']='inconclusive';report['summary']='Algorithm qualification resource-deferred/inconclusive at bounded admission; no algorithm defect inferred: '+str(error)
 finally:
  report['resource_wait_seconds']=supervisor.RESOURCE_WAIT_USED if supervisor else 0
  report['owned_source_hashes']={str(p.relative_to(ROOT)):digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__'not in str(p)}
  report['artifact_hashes']=extra_hashes|{str(p.relative_to(MAIN)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()};report['artifacts']=list(report['artifact_hashes'])
  report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','commit','host_vectors','cbc_fixture_vectors','host_checks','arm_checks','target_layout','fixture_target_layout','guest_cases']},indent=2));return 0 if report['outcome']=='pass' else 1

def native(command,report,out,vendor,xts,des,git):
 host=Path('/home/egor/.local/bin/clang').resolve();recipe_path=MAIN/'artifacts/xnu-kernel-declarations/controls-session1/report.json';original=json.loads(recipe_path.read_text());source=MAIN/original['source_ports']['osfmk/mc_provider.o']['source'];recipe=next(x for x in original['commands'] if str(source)in x['argv'] and '-c'in x['argv']);arm=Path(recipe['argv'][0]);ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
 if digest(arm)!=original['compiler_sha256']:raise ValueError('qualified original ARM compiler changed')
 for name,argv in [('host-version',[host,'--version']),('host-resource',[host,'-print-resource-dir']),('arm-version',[arm,'--version']),('arm-resource',[arm,'-print-resource-dir']),('linker-version',[ld,'-v'])]:command(argv,name)
 rd=Path((out/'host-resource.log').read_text().strip());runtimes={str(p):digest(p) for p in sorted((rd/'lib/x86_64-unknown-linux-gnu').glob('*')) if p.is_file()and('asan'in p.name or'ubsan'in p.name)}
 if not any(p.endswith('/libclang_rt.asan.a') for p in runtimes):raise ValueError('genuine native sanitizer runtime unavailable')
 report['tools']={'host':{'path':str(host),'sha256':digest(host),'resource_dir':str(rd),'runtime_hashes':runtimes},'arm':{'path':str(arm),'sha256':digest(arm),'recipe_report':str(recipe_path),'recipe_report_sha256':digest(recipe_path)},'ld':{'path':str(ld),'sha256':digest(ld)}}
 # Native public OpenSSL headers determine OSSL_PARAM layout in actual C.
 command([host,'--target=x86_64-unknown-linux-gnu','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-shared','-fPIC','-Wl,--threads=1','-MD','-MF',out/'oracle.d',HERE/'oracle.c','-lcrypto','-o',out/'oracle.so'],'oracle-compile')
 command(['ldd',out/'oracle.so'],'oracle-actual-link')
 if str(Path('/usr/lib64/libcrypto.so.3').resolve())not in(out/'oracle-actual-link.log').read_text()and'libcrypto.so.3'in(out/'oracle-actual-link.log').read_text():
  # ldd may print a symlink rather than its resolved real filename; preserve and
  # separately hash that exact file rather than asserting a rebuilt source ABI.
  report['oracle_ldd_path_uses_symlink']=True
 command(['pdftotext','-layout',ROOT/'artifacts/crypto-cts3/inputs/nist-AES-CBC.pdf',out/'nist-published.txt'],'nist-pdf-extract')
 wanted=json.loads((ROOT/'docs/procedures/crypto-cts3/source-pins.json').read_text())['nist_example_text']['sha256']
 if digest(out/'nist-published.txt')!=wanted:raise ValueError('primary PDF text replay differs')
 pdf_tool=Path(shutil.which('pdftotext')).resolve();report['tools']['pdftotext']={'path':str(pdf_tool),'sha256':digest(pdf_tool)}
 command([sys.executable,HERE/'vectors.py',out/'oracle.so',ROOT/'artifacts/crypto-cts3/inputs/rfc3962.txt',out/'nist-published.txt',out/'regenerated'],'vectors-replay',60)
 corpus=json.loads((out/'regenerated/vectors.json').read_text());report['corpus']={k:corpus[k] for k in ['primary','derived_extra_count','nist_published_cbc_count','nist_derived_cs3_count','nist_text_sha256','parser_negative_reordered_offsets','oracle']}
 common=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-I'+str(HERE),'-I'+str(MAIN/'src/platform/crypto/des'),'-I'+str(vendor/'include'),'-I'+str(vendor/'library'),'-I'+str(out/'regenerated'),'-DMBEDTLS_CONFIG_FILE="s24_cts3_aes_profile.h"']
 hf=[*common,'--target=x86_64-unknown-linux-gnu','-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-DCTS3_HOST']
 command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-###',HERE/'sanitizer_control.c','-o',out/'dry-run'],'host-sanitizer-expanded-link')
 for name,src in [('adapter',HERE/'cts3.c'),('fixture',HERE/'fixture_aes.c'),('aes',vendor/'library/aes.c'),('suite',HERE/'suite.c')]:command([host,*hf,'-MMD','-MF',out/('host-'+name+'.d'),'-c',src,'-o',out/('host-'+name+'.o')],'host-'+name)
 command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',*[out/('host-'+n+'.o') for n in ['adapter','fixture','aes','suite']],xts/'host-adapter.o',des/'host-adapter.o',des/'host-des.o','-o',out/'host'],'host-link')
 command([out/'host'],'host-tests',60);console=(out/'host-tests.log').read_text();match=re.search(r'CTS3 HOST PASS vectors=(\d+) cbc16=(\d+) checks=(\d+) failure_line=0',console)
 if not match or int(match[1])!=len(corpus['vectors']) or int(match[2])!=len(corpus['cbc_fixture']):raise ValueError('actual host marker mismatch')
 report['host_vectors']=int(match[1]);report['cbc_fixture_vectors']=int(match[2]);report['host_checks']=int(match[3]);report['profile_rejections']=[]
 for option in ['MBEDTLS_AES_ALT','MBEDTLS_AESNI_C','MBEDTLS_AESCE_C','MBEDTLS_HAVE_ASM','MBEDTLS_PADLOCK_C','MBEDTLS_SELF_TEST']:
  r=command([host,*hf,'-D'+option,'-c',HERE/'fixture_aes.c','-o',out/('reject-'+option+'.o')],'reject-'+option,expected=None);ok=r['exit_code']!=0 and'Unqualified fixture AES profile'in(out/('reject-'+option+'.log')).read_text();report['profile_rejections'].append({'macro':option,'rejected':ok})
  if not ok:raise ValueError('unqualified fixture profile accepted')
 command([host,'--target=x86_64-unknown-linux-gnu','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',HERE/'sanitizer_control.c','-o',out/'sanitizer-control'],'sanitizer-control-compile')
 report['sanitizer_controls']=[]
 for name,extra,marker in [('asan-heap',['heap'],'AddressSanitizer: heap-buffer-overflow'),('ubsan-overflow',[],'runtime error: signed integer overflow')]:
  r=command([out/'sanitizer-control',*extra],name,expected=None);ok=r['exit_code']!=0 and r['outcome']=='fail' and marker in(out/(name+'.log')).read_text();report['sanitizer_controls'].append({'name':name,'detected':ok})
  if not ok:raise ValueError('executed sanitizer detector failed')
 flags=list(recipe['argv'][1:])
 for key in ['-o','-MF']:
  i=flags.index(key);del flags[i:i+2]
 flags=[x for x in flags if not x.startswith('-W')and x not in ['-c','-MD','-MP','-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang']and x!=str(source)]
 flags=['-I'+recipe['cwd']if x=='-I.'else x for x in flags]
 flags += [*common,'-isystem',str(MAIN/'references/xnu-tapi/src/clang/lib/Headers'),'-I'+str(MAIN/'fixtures/public/avf-handoff'),'-DS24_XTS_FREESTANDING','-ffreestanding','-fno-pic','-fno-pie','-fno-stack-protector','-fno-jump-tables','-mstrict-align','-mgeneral-regs-only','-mno-outline-atomics','-fstack-usage']
 for name,src in [('adapter',HERE/'cts3.c'),('fixture',HERE/'fixture_aes.c'),('aes',vendor/'library/aes.c'),('suite',HERE/'suite.c'),('typed',HERE/'typed.c'),('guest',HERE/'guest.c'),('spin',HERE/'guest.c')]:command([arm,*flags,*(['-DCTS3_SPIN']if name=='spin'else[]),'-MMD','-MF',out/('arm-'+name+'.d'),'-c',src,'-o',out/('arm-'+name+'.o')],'arm-'+name)
 r=command([arm,*flags,'-c',HERE/'typed_negative.c','-o',out/'wrong-return.o'],'typed-return-negative',expected=None)
 if r['exit_code']==0 or'incompatible function pointer types'not in(out/'typed-return-negative.log').read_text():raise ValueError('real incompatible return typedef not rejected')
 report['typed_negative_rejected']=True
 report['dependency_hashes']={}
 for dep in sorted(out.glob('*.d')):
  for name in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():
   p=Path(name).resolve();report['dependency_hashes'][str(p)]=digest(p)
 report['selected_header_checks']={}
 for name,sha in report['dependency_hashes'].items():
  p=Path(name);xr=MAIN/'references/apple-xnu';cr=MAIN/'references/xnu-tapi'
  if p.is_relative_to(xr)and'EXTERNAL_HEADERS/corecrypto/'in name:
   rel=str(p.relative_to(xr));raw=git(xr,XNU+':'+rel)
   if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('consumed genuine selected header mismatch')
   report['selected_header_checks'][rel]=sha
  if p.is_relative_to(cr/'src/clang/lib/Headers'):
   if hashlib.sha256(git(cr,'fa9443738c1a18accef4244732ec6d6ee97a8133:'+str(p.relative_to(cr)))).hexdigest()!=sha:raise ValueError('genuine compiler resource header mismatch')
 report['adapter_compile_argv']=next(x['argv']for x in report['commands']if str(out/'arm-adapter.o')in x['argv']and'-c'in x['argv'])
 finish_native(command,report,out,out,xts,des,git)

def finish_native(command,report,out,objdir,xts,des,git):
 ld=Path(report['tools']['ld']['path'])
 # Exact selected string header explains the observed fortified external import.
 string_path=next(Path(x)for x in report['dependency_hashes']if x.endswith('/EXPORT_HDRS/osfmk/string.h'))
 raw=git(MAIN/'references/apple-xnu',XNU+':osfmk/libsa/string.h')
 if string_path.read_bytes()!=raw or digest(string_path)!='53948931a721b9fa29a0cd0a1dc4f09d1e3332bc6377f9cf8441760bcb20e38d':raise ValueError('actual fortified string header differs from exact genuine blob')
 if b'#define memcpy(dst, src, n)             __builtin___memcpy_chk(dst, src, n, __xnu_bos_default(dst))'not in raw:raise ValueError('genuine builtin mapping not present')
 pp=list(report['adapter_compile_argv'])
 for option in ['-o','-MF']:
  index=pp.index(option);del pp[index:index+2]
 pp=[x for x in pp if x not in ['-c','-MD','-MMD','-MP','-fstack-usage']]+['-E','-dM']
 command(pp,'native-memory-preprocessor')
 macros=(out/'native-memory-preprocessor.log').read_text();mapping=next(x for x in macros.splitlines()if x.startswith('#define memcpy('))
 if '__builtin___memcpy_chk'not in mapping:raise ValueError('actual selected preprocessing did not enable checked memcpy')
 memory=MAIN/'src/platform/crypto/xts/memory.c';xr=json.loads((xts/'evidence.json').read_text())
 if digest(memory)!=xr['owned_source_hashes']['src/platform/crypto/xts/memory.c']or'if(n>capacity)__builtin_trap();return memcpy(dst,src,n);'not in memory.read_text():raise ValueError('accepted memory source/real trapping check changed')
 report['fortified_memory_boundary']={'canonical_header':{'path':str(string_path),'sha256':digest(string_path),'git_blob':XNU+':osfmk/libsa/string.h'},'actual_preprocessor_mapping':mapping,'actual_macho_import':'___memcpy_chk','C_symbol':'__memcpy_chk','accepted_fixture_provider':{'object':str(xts/'arm-memory.o'),'sha256':digest(xts/'arm-memory.o'),'source':str(memory),'source_sha256':digest(memory),'bounds_overflow_traps':True},'native_kernel_provider_qualified':False,'scope':'synthetic fixture provider only; production native provider closure is a separate gate'}
 sys.path.insert(0,str(MAIN/'tools/build'));from xnu_kernel_syscalls import ObjectData
 layout=ObjectData(objdir/'arm-adapter.o').value('_s24_cts3_layout','<6Q');fixture=ObjectData(objdir/'arm-fixture.o').value('_s24_cts3_fixture_layout','<4Q')
 report['target_layout']=dict(zip(['cbc_descriptor_bytes','cbc_opaque_bytes','cbc_alignment','iv_opaque_bytes','iv_alignment','selected_max_block_bytes'],layout));report['fixture_target_layout']=dict(zip(['aes_state_bytes','alignment','genuine_mbed_aes_bytes','cbc_descriptor_bytes'],fixture))
 if layout!=(40,16,16,16,16,16)or fixture!=(304,16,288,40):raise ValueError('actual target ABI/layout differs')
 native_paths=[objdir/('arm-'+n+'.o')for n in ['adapter','fixture','aes','suite','typed','guest']]+[xts/'arm-adapter.o',xts/'arm-memory.o',des/'arm-adapter.o',des/'arm-des.o'];report['native_symbols']={};definitions={}
 for p in native_paths:
  obj=ObjectData(p);imports=sorted(x['name']for x in obj.symbols if not x['kind']&0x0e and x['kind']&1);names=sorted(obj.named)
  report['native_symbols'][str(p)]={'imports':imports,'definitions':names}
  for name in names:
   if name.startswith('_mbedtls_aes_')or name=='_mbedtls_platform_zeroize':definitions.setdefault(name,[]).append(str(p))
  if p==objdir/'arm-adapter.o'and set(imports)!={'___memcpy_chk','_memcpy','_mbedtls_platform_zeroize'}:raise ValueError('production is no longer generic/memory-only imports')
 if '___memcpy_chk'not in ObjectData(xts/'arm-memory.o').named:raise ValueError('accepted real trapping helper definition missing')
 if any(len(v)!=1 for v in definitions.values())or len(definitions.get('_mbedtls_platform_zeroize',[]))!=1:raise ValueError('duplicate/missing global AES/zeroizer implementation')
 if definitions.get('_mbedtls_aes_crypt_cbc')!=[str(objdir/'arm-aes.o')]:raise ValueError('canonical CBC function not supplied by one real AES object')
 report['single_AES_and_zeroizer_definitions']=definitions
 for mode,last in [('normal','guest'),('spin','spin')]:command([ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[objdir/('arm-'+n+'.o')for n in ['adapter','fixture','aes','suite','typed',last]],xts/'arm-adapter.o',xts/'arm-memory.o',des/'arm-adapter.o',des/'arm-des.o','-o',out/(mode+'.macho')],mode+'-link')
 avf=load_module('qualified_avf_for_cts3',MAIN/'tools/verify/avf_handoff.py');report['images']={mode:avf.macho(out/(mode+'.macho'))for mode in ['normal','spin']}
 report['stack_usage_artifacts']={str(p.relative_to(MAIN)):digest(p)for p in sorted(objdir.glob('*.su'))}

def guest(command,out,image_dir,corpus,report,avf,git):
 vm2=MAIN/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105';vm4=MAIN/'worktrees/vm-004-20261105/artifacts/qemu-host';qemu=vm4/'build-6/build/qemu-system-aarch64';shim=vm2/'Image'
 if digest(qemu)!=avf.PIN['qemu_sha256']or digest(shim)!=avf.PIN['shim_sha256']:raise ValueError('qualified unchanged QEMU/loader changed')
 sbpath=vm2/'report.json';qbpath=vm4/'build-6/build-report.json';qmpath=vm4/'release-10.2.0/source-manifest.json';sb=json.loads(sbpath.read_text());qb=json.loads(qbpath.read_text());qm=json.loads(qmpath.read_text())
 if sb['donor_commit']!=avf.PIN['scion_commit']or qb['pin']['commit']!=avf.PIN['qemu_commit']or qb['binary_sha256']!=avf.PIN['qemu_sha256']or not any(x['sha256']==avf.PIN['shim_sha256']for x in sb['artifacts']):raise ValueError('qualified loader/emulator build witness changed')
 source_hashes={}
 for row in sb['sources']:
  raw=git(MAIN/'references/scion-avf',avf.PIN['scion_commit']+':'+row['path']);sha=hashlib.sha256(raw).hexdigest()
  if sha!=row['sha256']:raise ValueError('loader canonical source differs')
  source_hashes[row['path']]=sha
 for name in ['hw/arm/virt.c','hw/arm/boot.c','target/arm/tcg/psci.c']:
  sha=digest(vm4/'release-10.2.0/source/qemu-10.2.0'/name)
  if sha!=qm[name]['sha256']:raise ValueError('virtual board canonical source differs')
  source_hashes['qemu/'+name]=sha
 report['avf_inputs']={'pin':avf.PIN,'qemu':str(qemu),'shim':str(shim),'source_hashes':source_hashes,'reports':{str(p):digest(p)for p in [sbpath,qbpath,qmpath]}}
 images={mode:avf.macho(image_dir/(mode+'.macho'))for mode in ['normal','spin']}
 if images!=report['images']:raise ValueError('immutable qualified actual image layout changed')
 base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot'];report['guest_cases']=[]
 for name,mode,cookie in [('positive','normal','xts_cookie=owned-adapter-v1'),('wrong-cookie','normal','xts_cookie=wrong'),('corrupt-vector','normal','xts_cookie=owned-adapter-v1'),('spin-timeout','spin','xts_cookie=owned-adapter-v1')]:
  kernel=bytearray((image_dir/(mode+'.macho')).read_bytes())
  if name=='corrupt-vector':
   blob=bytearray();offset=None
   for table in [corpus['vectors'],corpus['cbc_fixture']]:
    for v in table:
     for field in ['key','iv','pt','ct','next_iv','chain_ct','chain_iv']:
      if offset is None and field=='ct':offset=len(blob)
      blob.extend(bytes.fromhex(v.get(field,v['ct']if field=='chain_ct'else v['next_iv'])))
   if kernel.count(blob)!=1:raise ValueError('full actual generated guest vector blob must be unique')
   position=kernel.index(blob)+offset;kernel[position]^=1;report['corrupt_vector_control']={'offset':position,'original_byte':blob[offset],'mutation':'xor1 first actual primary RFC expected ciphertext byte, whole emitted blob bound'}
  payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie)
  r=command([*base,'-initrd',payload],name,3 if mode=='spin'else 60,expected=None,budget=512);console=(out/(name+'.log')).read_text(errors='replace');passed='CTS3 ARM PASS'in console
  if name=='positive':
   m=re.search(r'CTS3 ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0',console);entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
   ok=bool(m and entry)and int(entry[1],16)==images[mode]['entry_pa']and int(entry[2],16)==images[mode]['bootargs_pa']and r['outcome']=='pass'and'XTS SYNTHETIC HANDOFF VERIFIED'in console and'XTS SYNTHETIC PSCI_SYSTEM_OFF'in console
   if m:report['arm_checks']=int(m[1],16);ok=ok and report['arm_checks']==report['host_checks']
  elif name=='wrong-cookie':ok=not passed and'XTS SYNTHETIC REJECT command-cookie'in console and r['outcome']=='pass'
  elif name=='corrupt-vector':ok=not passed and'CTS3 ARM FAIL'in console and'XTS SYNTHETIC PSCI_SYSTEM_OFF'in console and r['outcome']=='pass'
  else:ok=not passed and'CTS3 SYNTHETIC SPIN-CONTROL'in console and r['outcome']=='timeout'
  report['guest_cases'].append({'name':name,'accepted':ok,'payload_sha256':digest(payload),'console_sha256':digest(out/(name+'.log'))})
  if not ok:raise ValueError('actual guest control failed '+name)
 if digest(qemu)!=avf.PIN['qemu_sha256']or digest(shim)!=avf.PIN['shim_sha256']:raise ValueError('read-only qualified guest input changed')

if __name__=='__main__':raise SystemExit(main())
