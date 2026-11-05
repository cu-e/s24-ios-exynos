#!/usr/bin/env python3
"""Complete only missing controls after immutable actual positive CPU evidence."""
import argparse,copy,datetime,hashlib,importlib.util,json,os,re,sys,time,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
os.environ.update(GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
spec=importlib.util.spec_from_file_location('accepted_xts',MAIN/'src/platform/crypto/xts/check.py');xts=importlib.util.module_from_spec(spec);spec.loader.exec_module(xts);avf=xts.avf
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',required=True,type=Path);p.add_argument('--run',required=True);p.add_argument('--lease',required=True);args=p.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('plain fresh run required')
 out=ROOT/'artifacts/crypto-gcm'/args.run;out.mkdir(parents=True,exist_ok=False);(out/'executed-cpu_controls.py').write_bytes(Path(__file__).read_bytes())
 prior=args.parent.resolve();old=json.loads(prior.read_text());report=copy.deepcopy(old);report.update(outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],lease=args.lease,stage_parent={'path':str(prior),'sha256':sha(prior)},prior_commands=old['commands'],original_deferral=old.get('deferred'))
 report.pop('error',None);report.pop('deferred',None)
 report['admission_policy']={'required_consecutive_samples':3,'minimum_MemAvailable_kib':4*1024*1024,'sample_interval_seconds':1,'per_command_wait_seconds':45,'total_wait_budget_seconds':180}
 report['admission_waits']=[];total_wait=0.0
 def command(argv,name,timeout=60):
  nonlocal total_wait
  started=time.monotonic();samples=[];consecutive=0;admitted=False;available=None
  while True:
   elapsed=time.monotonic()-started
   if elapsed>45 or total_wait+elapsed>180:break
   available=int(re.search(r'^MemAvailable:\s+(\d+) kB',Path('/proc/meminfo').read_text(),re.M)[1]);elapsed=time.monotonic()-started
   samples.append({'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':elapsed,'mem_available_kib':available,'children_launched':False})
   consecutive=consecutive+1 if available>=4*1024*1024 else 0
   if consecutive>=3:admitted=True;break
   remaining=min(45-elapsed,180-total_wait-elapsed)
   if remaining<1:break
   time.sleep(1)
  waited=time.monotonic()-started;total_wait+=waited
  report['admission_waits'].append({'name':name,'samples':samples,'wait_seconds':waited,'total_wait_seconds':total_wait,'admitted':admitted});report['total_admission_wait_seconds']=total_wait
  if not admitted:
   report['resource_outcome']='resource-deferred';report['deferred']={'name':name,'mem_available_kib':available,'reason':'Stable three-sample4GiB admission unavailable within finite budget; no child launched'};raise RuntimeError('Resource-deferred stable4GiB admission')
  r=xts.run(argv,out,name,timeout,512);r['mem_available_kib']=available;report['commands'].append(r);return r
 try:
  git_argv=['git','-C',str(ROOT),'rev-parse','HEAD'];result=subprocess.run(git_argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ,timeout=10);report['source_control']={'argv':git_argv,'exit_code':result.returncode,'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest(),'environment_overrides':{'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}}
  if result.returncode:raise ValueError('Exact source commit unavailable')
  report['commit']=result.stdout.decode().strip()
  if len(old.get('guest_cases',[]))!=1 or old.get('deferred',{}).get('name')!='wrong-cookie' or old.get('arm_checks')!=old.get('host_checks') or not old.get('arm_checks') or old.get('guest_cases')!=[x for x in old.get('guest_cases',[]) if x['name']=='positive' and x['accepted']]:raise ValueError('Exact positive CPU plus pre-control memory deferral required')
  for name,digest in old['artifact_hashes'].items():
   if sha(MAIN/name)!=digest:raise ValueError('Actual positive CPU evidence changed:'+name)
  for name,digest in old['owned_source_hashes'].items():
   if sha(ROOT/name)!=digest:
    # Only this exact report-label repair is permitted in the earlier CPU driver;
    # it cannot change the already linked, hash-verified implementation/image.
    before=(prior.parent/'executed-cpu.py').read_bytes()
    after=before.decode().replace(" finally:\n  report['owned_source_hashes']", " finally:\n  report.setdefault('summary','Actual GCM CPU qualification failed or memory-deferred; retain commands and conditional markers, no complete qualification claim')\n  report['owned_source_hashes']").encode()
    if name!='src/platform/crypto/gcm/cpu.py' or hashlib.sha256(before).hexdigest()!=digest or (ROOT/name).read_bytes()!=after:raise ValueError('Positively CPU-tested implementation changed:'+name)
    report['qualification_metadata_patch']={'path':name,'before_sha256':digest,'after_sha256':sha(ROOT/name),'scope':'Exact setdefault summary repair in CPU evidence driver only; unchanged compiled suite/source/images and positive execution'}
  parent=Path(old['parent']['path'])
  if sha(parent)!=old['parent']['sha256']:raise ValueError('Combined host/ARM evidence changed')
  arm=json.loads(parent.read_text());build=parent.parent
  for name,digest in arm['artifact_hashes'].items():
   if sha(MAIN/name)!=digest:raise ValueError('Source-qualified host/ARM image input changed:'+name)
  for name,digest in arm['dependencies'].items():
   if sha(name)!=digest:raise ValueError('Actual dependency changed:'+name)
  for category in ['reused_arm_objects','reused_stage_objects','shared_owned_source_checks']:
   for name,digest in arm[category].items():
    if sha(name)!=digest:raise ValueError('Accepted read-only source/object changed:'+name)
  xtspath=Path(arm['parent']['path'])
  if sha(xtspath)!=arm['parent']['sha256']:raise ValueError('Accepted AES/runtime qualification changed')
  binding=old['avf_inputs']
  for name,digest in binding['reports'].items():
   if sha(name)!=digest:raise ValueError('AVF source report changed')
  if binding['pin']!=avf.PIN or sha(MAIN/'tools/build/qemu_host.py')!=binding['supervisor_sha256'] or sha(MAIN/'tools/verify/avf_handoff.py')!=binding['qualified_helpers_sha256']:raise ValueError('Accepted CPU/helper identity changed')
  qemu=Path(binding['qemu']);shim=Path(binding['shim'])
  if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('CPU/shim changed')
  images={mode:avf.macho(build/(mode+'.macho')) for mode in ['normal','spin']}
  if images!=old['images']:raise ValueError('Actual image inspection changed')
  base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot'];corpus=json.loads((build/'vectors.json').read_text())
  for name,mode,cookie in [('wrong-cookie','normal','gcm_cookie=wrong'),('corrupt-vector','normal','gcm_cookie=owned-adapter-v1'),('spin-timeout','spin','gcm_cookie=owned-adapter-v1')]:
   kernel=bytearray((build/(mode+'.macho')).read_bytes())
   if name=='corrupt-vector':
    blob=(build/'vectors.bin').read_bytes();vector=next(v for v in corpus['vectors'] if len(v['ct'])>=32 and not v['bad']);wanted=bytes.fromhex(vector['ct'])
    if kernel.count(blob)!=1 or blob.count(wanted)!=1:raise ValueError('Unique actual expected ciphertext in owned corpus required')
    offset=kernel.index(blob)+blob.index(wanted);kernel[offset]^=1;report['corrupt_vector_control']={'offset':offset,'original_expected':wanted.hex(),'mutation':'xor1 first byte of unique owned expected ciphertext; inputs/tag/code unchanged'}
   payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie);r=command([*base,'-initrd',payload],name,3 if mode=='spin' else 60);console=(out/(name+'.log')).read_text(errors='replace');passed='GCM ARM PASS' in console
   if name=='wrong-cookie':ok=not passed and 'GCM SYNTHETIC REJECT command-cookie' in console and r['outcome']=='pass'
   elif name=='corrupt-vector':ok=not passed and 'GCM ARM FAIL' in console and 'GCM SYNTHETIC PSCI_SYSTEM_OFF' in console and r['outcome']=='pass'
   else:ok=not passed and 'GCM SYNTHETIC SPIN-CONTROL' in console and r['outcome']=='timeout'
   report['guest_cases'].append({'name':name,'accepted':ok,'payload_sha256':sha(payload),'console_sha256':sha(out/(name+'.log'))})
   if not ok:raise ValueError('Actual CPU control failed:'+name)
  if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Immutable CPU input changed')
  report['outcome']='pass';report['summary']='Combined actual same-suite ARM positive25948370 checks and three real CPU negative controls, all immutable host/source/ARM identities verified. Earlier memory-deferred report retained. No provider/XNU/native/FIPS/side-channel qualification.'
 except Exception as error:report['error']=repr(error)
 finally:
  report['owned_source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
  report['artifact_hashes'].update({str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()});report['artifact_hashes'][str(prior.relative_to(MAIN))]=sha(prior);report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','host_checks','arm_checks','guest_cases']},indent=2));return report['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
