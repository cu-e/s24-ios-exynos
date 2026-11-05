#!/usr/bin/env python3
"""Bounded real host/ARM DES qualification; never registers a crypto provider."""
import argparse,datetime,hashlib,importlib.util,json,os,re,resource,subprocess,sys,time,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
GIT_GUARDS={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
ENV_OVERRIDES=GIT_GUARDS|{'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1','PYTHONOPTIMIZE':'0'}
CHILD_ENV=dict(os.environ)|ENV_OVERRIDES
spec=importlib.util.spec_from_file_location('qualified_avf',ROOT/'tools/verify/avf_handoff.py')
avf=importlib.util.module_from_spec(spec);spec.loader.exec_module(avf)
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
# Process-session monitoring/cleanup derives from accepted VM-005. This owner
# deliberately uses RSS only: lld and ASan reserve large sparse virtual regions.
def run(argv, out, name, seconds=5, limit_mib=256):
    available=int(next(x.split()[1] for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))
    if available<4*1024**2:raise RuntimeError("MemAvailable floor: "+str(available)+" KiB")
    start = time.monotonic()
    record = {"argv": [str(x) for x in argv], "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "timeout_seconds": seconds, "rss_budget_mib": limit_mib, "outcome": "fail",
              "environment_overrides": ENV_OVERRIDES,"MemAvailable_before_KiB":available}

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with (out / (name + ".log")).open("xb") as log, (out / (name + ".samples.jsonl")).open("x") as samples:
        proc = subprocess.Popen(record["argv"], cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=limits, env=CHILD_ENV)
        record["owned_session"] = proc.pid
        peak = 0
        try:
            while proc.poll() is None:
                snap = avf.supervisor.sample(proc.pid)
                own_rss = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
                snap["memory_pressure"] = Path("/proc/pressure/memory").read_text()
                snap["supervisor_rss_bytes"] = own_rss
                snap["total_owned_rss_bytes"] = own_rss + snap["owned_tree_rss_bytes"]
                peak = max(peak, snap["total_owned_rss_bytes"])
                samples.write(json.dumps(snap) + "\n"); samples.flush()
                if peak > limit_mib * 1024**2:
                    record["outcome"] = "rss-limit"
                    avf.supervisor.terminate(proc)
                    break
                if time.monotonic() - start >= seconds:
                    record["outcome"] = "timeout"
                    avf.supervisor.terminate(proc)
                    break
                time.sleep(0.05)
            record["exit_code"] = proc.wait(timeout=2)
            if record["outcome"] == "fail" and record["exit_code"] == 0:
                record["outcome"] = "pass"
        finally:
            if any(p["state"] != "Z" for p in avf.supervisor.sample(proc.pid)["owned_processes"]):
                avf.supervisor.terminate(proc)
            until = time.monotonic() + 2
            after = avf.supervisor.sample(proc.pid)
            while any(p["state"] != "Z" for p in after["owned_processes"]) and time.monotonic() < until:
                time.sleep(0.02); after = avf.supervisor.sample(proc.pid)
            record.update(elapsed_seconds=round(time.monotonic() - start, 3),
                          peak_total_owned_rss_bytes=peak, cumulative_children_ru_maxrss_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, after=after)
            (out / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
            if any(p["state"] != "Z" for p in after["owned_processes"]):
                raise RuntimeError("Live owned fixture child survived cleanup")
    return record


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('--experiment',required=True,help='Existing planned MAIN experiment for this task/owner');ap.add_argument('--guest',action='store_true',help='Requires exclusive coordinator lease before invocation');a=ap.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh simple name required')
 out=ROOT/'artifacts/crypto-des'/a.run;out.mkdir(parents=True,exist_ok=False)
 report={'experiment':a.experiment,'prior_host_planning_deviation':'DES001 plan rejected for prose procedure instead of existing file; host-arm1..4 not preregistered; retained honestly. Fresh runs require an actual planned MAIN experiment before any child execution.', 'task':'KRN-032','kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':sys.argv,'commands':[],'source_reads':[],'source_pins':{'xnu':'c54f35ca767986246321eb901baf8f5ff7923f6a','mbedtls':'068ff080b369adfac81509f9b57b2afabaf82dc5'},'native_device':False,'xnu_executed':False,'provider_registered':False,'general_mode_api_qualified':False,'roundkey':'NULL, no selected caller demand, unsupported','helper_policy':'exactly8bytes; weak invalid nonzero, void parity invalid no-op','guest_requested':a.guest}
 def command(argv,name,seconds=30,expected=0,budget=256):
  r=run(argv,out,name,seconds,budget);report['commands'].append(r)
  if expected is not None and (r['exit_code']!=expected or r['outcome']!='pass'):raise ValueError(name+' '+r['outcome']+' exit '+str(r['exit_code']))
  return r
 def git(repo,spec):
  p=subprocess.run(['git','-C',str(repo),'show',spec],env=CHILD_ENV,capture_output=True,timeout=10)
  report['source_reads'].append({'argv':['git','-C',str(repo),'show',spec],'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr':p.stderr.decode(errors='replace')})
  if p.returncode:raise ValueError('pinned Git object unavailable without lazy fetch')
  return p.stdout
 try:
  (out/'preflight.json').write_text(json.dumps({'recorded_at':report['recorded_at'],'argv':sys.argv,'meminfo':Path('/proc/meminfo').read_text(),'memory_pressure':Path('/proc/pressure/memory').read_text()},indent=2)+'\n')
  ledger=(MAIN/'state/lab.json').read_bytes();state=json.loads(ledger)
  plans=[x for x in state['experiments'] if x['id']==a.experiment]
  if len(plans)!=1 or plans[0]['status']!='planned' or plans[0]['task']!='KRN-032' or plans[0]['owner']!='codex-team-crypto-des-20261105-bs':raise ValueError('actual MAIN planned experiment for this task/owner required')
  report['planning_record']=plans[0];report['planning_snapshot_sha256']=hashlib.sha256(ledger).hexdigest()
  report['commit']=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],env=CHILD_ENV,text=True).strip()
  report['owned_dirty_at_start']=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=all','--','src/platform/crypto/des','docs/procedures/crypto-des'],env=CHILD_ENV,text=True)
  sys.path.insert(0,str(HERE));from verify_vendor import verify
  report['canonical_vendor']=verify()
  vendor=HERE/'vendor';prov=json.loads((vendor/'provenance.json').read_text())
  for name,wanted in prov['files'].items():
   if digest(vendor/name)!=wanted:raise ValueError('vendor hash '+name)
  report['vendor_provenance_sha256']=digest(vendor/'provenance.json')
  # The installed oracle is independent, not a rebuilt copy of the Mbed primitive.
  cache=MAIN/'worktrees/krn-028-20261105/tools/research/crypto-candidates/local/vectors'
  command([sys.executable,HERE/'vectors.py',cache,out/'regenerated'],'vectors-replay',60)
  corpus=json.loads((out/'regenerated/vectors.json').read_text());report['corpus']={k:corpus[k] for k in ['primary_count','derived_count','oracle_extra_count','archive_sha256','files','excluded','parser','oracle']}
  # Bind actual selected caller declarations as well as all consumed headers.
  sourcefiles=['EXTERNAL_HEADERS/corecrypto/ccmode_impl.h','EXTERNAL_HEADERS/corecrypto/ccmode.h','libkern/libkern/crypto/des.h','libkern/libkern/crypto/register_crypto.h','libkern/crypto/corecrypto_des.c','bsd/netinet6/esp_core.c','bsd/nfs/gss/ccrypto.c','bsd/nfs/gss/gss_krb5_mech.c']
  report['selected_sources']={}
  for name in sourcefiles:
   raw=git(MAIN/'references/apple-xnu',report['source_pins']['xnu']+':'+name);path=MAIN/'references/apple-xnu'/name
   if raw!=path.read_bytes():raise ValueError('selected caller bytes changed '+name)
   report['selected_sources'][name]=hashlib.sha256(raw).hexdigest()
  # Audit absence of selected roundkey consumers, preserving actual command/output.
  r=command(['rg','-n','roundkey',*[MAIN/'references/apple-xnu'/p for p in ['bsd','libkern','osfmk','EXTERNAL_HEADERS/corecrypto']]],'roundkey-demand')
  lines=(out/'roundkey-demand.log').read_text().splitlines()
  if len(lines)!=1 or 'ccmode_impl.h:' not in lines[0]:raise ValueError('new roundkey consumer requires review')
  report['roundkey_source_audit']=lines
  # Exact accepted immutable XTS artifacts supply the only global zeroizer.
  shared=MAIN/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2';shared_report=shared/'evidence.json';sr=json.loads(shared_report.read_text())
  if digest(shared_report)!='c5064a512ba295d1cd447af1e73ac6fc4f9c0ffeaf5b78f09ca0f80fc1f6216c' or sr['outcome']!='pass':raise ValueError('accepted XTS evidence changed')
  runtime=MAIN/'fixtures/public/avf-handoff/runtime.h'
  if digest(runtime)!=sr['owned_source_hashes']['fixtures/public/avf-handoff/runtime.h']:raise ValueError('accepted unchanged runtime header differs')
  report['shared_runtime']={'path':str(runtime),'sha256':digest(runtime),'unchanged_against_accepted_XTS':True}
  report['zeroizer_dependency']={'accepted_report':str(shared_report),'sha256':digest(shared_report),'objects':{}}
  for name in ['host-adapter.o','host-aes.o','arm-adapter.o','arm-aes.o','arm-memory.o']:
   p=shared/name;key=str(p.relative_to(MAIN/'worktrees/krn-029-20261105'))
   if digest(p)!=sr['artifact_hashes'][key]:raise ValueError('accepted XTS object hash '+name)
   report['zeroizer_dependency']['objects'][str(p)]=digest(p)
  host=Path('/home/egor/.local/bin/clang').resolve();original_path=MAIN/'artifacts/xnu-kernel-declarations/controls-session1/report.json';original=json.loads(original_path.read_text())
  source=MAIN/original['source_ports']['osfmk/mc_provider.o']['source'];recipe=next(r for r in original['commands'] if str(source)in r['argv'] and '-c'in r['argv']);arm=Path(recipe['argv'][0]);ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
  if digest(arm)!=original['compiler_sha256']:raise ValueError('qualified ARM compiler changed')
  for name,argv in [('host-version',[host,'--version']),('host-resource',[host,'-print-resource-dir']),('arm-version',[arm,'--version']),('arm-resource',[arm,'-print-resource-dir']),('linker-version',[ld,'-v'])]:command(argv,name)
  rd=Path((out/'host-resource.log').read_text().strip());runtimes={str(p):digest(p) for p in sorted((rd/'lib/x86_64-unknown-linux-gnu').glob('*')) if p.is_file() and ('asan'in p.name or 'ubsan'in p.name)}
  if not any(p.endswith('/libclang_rt.asan.a') for p in runtimes):raise ValueError('native host sanitizer runtime absent')
  report['tools']={'host':{'path':str(host),'sha256':digest(host),'resource_dir':str(rd),'runtime_hashes':runtimes},'arm':{'path':str(arm),'sha256':digest(arm),'recipe_report':str(original_path),'recipe_report_sha256':digest(original_path)},'ld':{'path':str(ld),'sha256':digest(ld)}}
  command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-###',HERE/'sanitizer_control.c','-o',out/'dry-run'],'host-sanitizer-expanded-link')
  common=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-I'+str(HERE),'-I'+str(vendor/'include'),'-I'+str(vendor/'library'),'-I'+str(out/'regenerated'),'-DMBEDTLS_CONFIG_FILE="s24_des_profile.h"']
  hf=[*common,'--target=x86_64-unknown-linux-gnu','-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-DDES_HOST']
  for name,src in [('adapter',HERE/'des.c'),('des',vendor/'library/des.c'),('suite',HERE/'suite.c')]:command([host,*hf,'-MMD','-MF',out/('host-'+name+'.d'),'-c',src,'-o',out/('host-'+name+'.o')],'host-'+name)
  command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',*[out/('host-'+n+'.o') for n in ['adapter','des','suite']],shared/'host-adapter.o',shared/'host-aes.o','-o',out/'host'],'host-link')
  command([out/'host'],'host-tests',60);console=(out/'host-tests.log').read_text();match=re.search(r'DES HOST PASS vectors=(\d+) checks=(\d+) failure_line=0',console)
  if not match or int(match[1])!=len(corpus['vectors']):raise ValueError('host algorithm marker mismatch')
  report['host_checks']=int(match[2]);report['host_vectors']=int(match[1]);report['profile_rejections']=[]
  for option in ['MBEDTLS_DES_ALT','MBEDTLS_DES_SETKEY_ALT','MBEDTLS_DES_CRYPT_ECB_ALT','MBEDTLS_DES3_CRYPT_ECB_ALT','MBEDTLS_HAVE_ASM']:
   r=command([host,*hf,'-D'+option,'-c',HERE/'des.c','-o',out/('reject-'+option+'.o')],'reject-'+option,expected=None)
   ok=r['exit_code']!=0 and 'Unqualified DES profile'in(out/('reject-'+option+'.log')).read_text();report['profile_rejections'].append({'macro':option,'rejected':ok})
   if not ok:raise ValueError('unqualified profile accepted')
  command([host,'--target=x86_64-unknown-linux-gnu','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',HERE/'sanitizer_control.c','-o',out/'sanitizer-control'],'sanitizer-control-compile')
  report['sanitizer_controls']=[]
  for name,extra,marker in [('asan-heap',['heap'],'AddressSanitizer: heap-buffer-overflow'),('ubsan-overflow',[],'runtime error: signed integer overflow')]:
   r=command([out/'sanitizer-control',*extra],name,expected=None);ok=r['exit_code']!=0 and r['outcome']=='fail' and marker in(out/(name+'.log')).read_text();report['sanitizer_controls'].append({'name':name,'detected':ok})
   if not ok:raise ValueError('real sanitizer negative missing '+name)
  flags=list(recipe['argv'][1:])
  for key in ['-o','-MF']:
   i=flags.index(key);del flags[i:i+2]
  flags=[x for x in flags if not x.startswith('-W') and x not in ['-c','-MD','-MP','-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang'] and x!=str(source)]
  flags=['-I'+recipe['cwd'] if x=='-I.' else x for x in flags]
  flags += [*common,'-isystem',str(MAIN/'references/xnu-tapi/src/clang/lib/Headers'),'-I'+str(MAIN/'fixtures/public/avf-handoff'),'-DS24_DES_FREESTANDING','-ffreestanding','-fno-pic','-fno-pie','-fno-stack-protector','-fno-jump-tables','-mstrict-align','-mgeneral-regs-only','-mno-outline-atomics']
  for name,src in [('adapter',HERE/'des.c'),('des',vendor/'library/des.c'),('suite',HERE/'suite.c'),('typed',HERE/'typed.c'),('guest',HERE/'guest.c'),('spin',HERE/'guest.c')]:
   command([arm,*flags,*(['-DDES_SPIN'] if name=='spin' else []),'-MMD','-MF',out/('arm-'+name+'.d'),'-c',src,'-o',out/('arm-'+name+'.o')],'arm-'+name)
  report['dependency_hashes']={}
  for dep in sorted(out.glob('*.d')):
   for name in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():
    p=Path(name).resolve();report['dependency_hashes'][str(p)]=digest(p)
  report['selected_header_checks']={}
  for name,sha in report['dependency_hashes'].items():
   p=Path(name);root=MAIN/'references/apple-xnu';clangroot=MAIN/'references/xnu-tapi'
   if p.is_relative_to(root) and 'EXTERNAL_HEADERS/corecrypto/'in name:
    rel=str(p.relative_to(root));raw=git(root,report['source_pins']['xnu']+':'+rel)
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('actual selected XNU header differs')
    report['selected_header_checks'][rel]=sha
   if p.is_relative_to(clangroot/'src/clang/lib/Headers'):
    raw=git(clangroot,'fa9443738c1a18accef4244732ec6d6ee97a8133:'+str(p.relative_to(clangroot)))
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('genuine Clang resource header differs')
  sys.path.insert(0,str(ROOT/'tools/build'));from xnu_kernel_syscalls import ObjectData
  layout=ObjectData(out/'arm-adapter.o').value('_s24_des_layout','<7Q');storage=ObjectData(out/'arm-typed.o').value('_s24_des_storage','<4Q')
  report['native_symbols']={}
  zeroizers=0
  for path in [out/'arm-adapter.o',out/'arm-des.o',shared/'arm-adapter.o',shared/'arm-aes.o',shared/'arm-memory.o']:
   obj=ObjectData(path);imports=sorted(x['name'] for x in obj.symbols if not x['kind']&0x0e and x['kind']&1)
   definitions=sorted(obj.named)
   report['native_symbols'][str(path)]={'imports':imports,'definitions':definitions}
   zeroizers+=int('_mbedtls_platform_zeroize'in definitions)
   if path==out/'arm-des.o' and imports!=['_bzero','_mbedtls_platform_zeroize','_memcmp','_memcpy']:raise ValueError('unqualified primitive OS/heap imports')
  if zeroizers!=1 or '_mbedtls_platform_zeroize'in ObjectData(out/'arm-adapter.o').named:raise ValueError('global zeroizer ownership')
  report['target_layout']=dict(zip(['des_bytes','tdes_bytes','alignment','mbed_des_bytes','mbed_tdes_bytes','ecb_descriptor_bytes','cbc_descriptor_bytes'],layout));report['selected_storage']=list(storage)
  if layout!=(144,400,16,128,384,48,40) or storage!=(256,768,8,8):raise ValueError('genuine typed target layout mismatch')
  for mode,last in [('normal','guest'),('spin','spin')]:
   command([ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[out/('arm-'+n+'.o') for n in ['adapter','des','suite','typed',last]],*[shared/n for n in ['arm-adapter.o','arm-aes.o','arm-memory.o']],'-o',out/(mode+'.macho')],mode+'-link')
  images={mode:avf.macho(out/(mode+'.macho')) for mode in ['normal','spin']};report['images']=images
  if a.guest:
   report['guest_resource_allowance']='Exclusive coordinator grant:256MiB guest RAM,512MiB total owned RSS including process/device/supervisor overhead; host/compiler runs retain256MiB. Floor4GiB and aggregate2GiB preserved.'
   guest(command,out,corpus,report,images,git)
  report['outcome']='pass';report['summary']='Genuine typed DES/TDES ECB/CBC/helper component: primary NIST and independent OpenSSL, sanitized host and typed ARM; actual CPU only if guest_cases present; no provider/general roundkey/privateApple/native/FIPS/sidechannel claim'
 except Exception as error:
  report['error']=repr(error);report['summary']='Qualification failed/stopped without a pass claim: '+repr(error)
 finally:
  report['owned_source_hashes']={str(p.relative_to(ROOT)):digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__'not in str(p)}
  for p in [MAIN/'fixtures/public/avf-handoff/runtime.h',ROOT/'tools/build/qemu_host.py',ROOT/'tools/verify/avf_handoff.py']:report['owned_source_hashes'][str(p)]=digest(p)
  report['artifact_hashes']={str(p.relative_to(MAIN)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()};report['artifacts']=list(report['artifact_hashes']);report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','commit','host_vectors','host_checks','arm_checks','target_layout','guest_cases']},indent=2));return 0 if report['outcome']=='pass' else 1

def guest(command,out,corpus,report,images,git):
 # Same accepted synthetic runtime/QEMU/loader; no replacement fake kernel.
 vm2=MAIN/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105';vm4=MAIN/'worktrees/vm-004-20261105/artifacts/qemu-host';qemu=vm4/'build-6/build/qemu-system-aarch64';shim=vm2/'Image'
 if digest(qemu)!=avf.PIN['qemu_sha256'] or digest(shim)!=avf.PIN['shim_sha256']:raise ValueError('qualified unchanged QEMU/shim hashes')
 sbpath=vm2/'report.json';qbpath=vm4/'build-6/build-report.json';qmpath=vm4/'release-10.2.0/source-manifest.json';sb=json.loads(sbpath.read_text());qb=json.loads(qbpath.read_text());qm=json.loads(qmpath.read_text())
 if sb['donor_commit']!=avf.PIN['scion_commit'] or qb['pin']['commit']!=avf.PIN['qemu_commit'] or qb['binary_sha256']!=avf.PIN['qemu_sha256'] or not any(x['sha256']==avf.PIN['shim_sha256'] for x in sb['artifacts']):raise ValueError('build report bindings')
 source_hashes={}
 for row in sb['sources']:
  raw=git(MAIN/'references/scion-avf',avf.PIN['scion_commit']+':'+row['path']);sha=hashlib.sha256(raw).hexdigest()
  if sha!=row['sha256']:raise ValueError('shim source differs')
  source_hashes[row['path']]=sha
 for name in ['hw/arm/virt.c','hw/arm/boot.c','target/arm/tcg/psci.c']:
  sha=digest(vm4/'release-10.2.0/source/qemu-10.2.0'/name)
  if sha!=qm[name]['sha256']:raise ValueError('QEMU source differs')
  source_hashes['qemu/'+name]=sha
 report['avf_inputs']={'pin':avf.PIN,'qemu':str(qemu),'shim':str(shim),'source_hashes':source_hashes,'reports':{str(p):digest(p) for p in [sbpath,qbpath,qmpath]}}
 base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot'];report['guest_cases']=[]
 for name,mode,cookie in [('positive','normal','xts_cookie=owned-adapter-v1'),('wrong-cookie','normal','xts_cookie=wrong'),('corrupt-vector','normal','xts_cookie=owned-adapter-v1'),('spin-timeout','spin','xts_cookie=owned-adapter-v1')]:
  kernel=bytearray((out/(mode+'.macho')).read_bytes())
  if name=='corrupt-vector':
   # Locate complete actual generated vector blob, then mutate first expected CT.
   blob=bytearray();offset=None
   for v in corpus['vectors']:
    for field in ['key','iv','pt','ct']:
     if offset is None and field=='ct':offset=len(blob)
     blob.extend(bytes.fromhex(v[field]))
   if kernel.count(blob)!=1:raise ValueError('actual guest vector blob must be unique')
   position=kernel.index(blob)+offset;kernel[position]^=1
   report['corrupt_vector_control']={'offset':position,'original_byte':blob[offset],'mutation':'xor1 first expected ciphertext byte in full actual generated vector blob'}
  payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie)
  r=command([*base,'-initrd',payload],name,3 if mode=='spin' else 60,expected=None,budget=512);console=(out/(name+'.log')).read_text(errors='replace');passed='DES ARM PASS'in console
  if name=='positive':
   m=re.search(r'DES ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0',console);entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
   ok=bool(m and entry) and int(entry[1],16)==images[mode]['entry_pa'] and int(entry[2],16)==images[mode]['bootargs_pa'] and r['outcome']=='pass' and 'XTS SYNTHETIC HANDOFF VERIFIED'in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF'in console
   if m:report['arm_checks']=int(m[1],16);ok=ok and report['arm_checks']==report['host_checks']
  elif name=='wrong-cookie':ok=not passed and 'XTS SYNTHETIC REJECT command-cookie'in console and r['outcome']=='pass'
  elif name=='corrupt-vector':ok=not passed and 'DES ARM FAIL'in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF'in console and r['outcome']=='pass'
  else:ok=not passed and 'DES SYNTHETIC SPIN-CONTROL'in console and r['outcome']=='timeout'
  report['guest_cases'].append({'name':name,'accepted':ok,'payload_sha256':digest(payload),'console_sha256':digest(out/(name+'.log'))})
  if not ok:raise ValueError('guest control failure '+name)
 if digest(qemu)!=avf.PIN['qemu_sha256'] or digest(shim)!=avf.PIN['shim_sha256']:raise ValueError('shared immutable input changed')

if __name__=='__main__':raise SystemExit(main())
