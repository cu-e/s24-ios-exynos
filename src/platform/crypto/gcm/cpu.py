#!/usr/bin/env python3
"""Execute prequalified own real GCM MachO on accepted synthetic ARM CPU.
Requires coordinator's exclusive guest grant, supplied as recorded --lease text.
"""
import argparse,datetime,hashlib,importlib.util,json,os,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
os.environ.update(GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
spec=importlib.util.spec_from_file_location('accepted_xts',MAIN/'src/platform/crypto/xts/check.py');xts=importlib.util.module_from_spec(spec);spec.loader.exec_module(xts)
avf=xts.avf
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',required=True,type=Path);p.add_argument('--run',required=True);p.add_argument('--lease',required=True);args=p.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('plain fresh run required')
 out=ROOT/'artifacts/crypto-gcm'/args.run;out.mkdir(parents=True,exist_ok=False);(out/'executed-cpu.py').write_bytes(Path(__file__).read_bytes())
 report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],lease=args.lease,provider_registered=False,xnu_executed=False,native_device=False,full_crypto_qualified=False,fips_qualified=False,side_channel_qualified=False)
 def command(argv,name,timeout=45,budget=512):
  available=int(re.search(r'^MemAvailable:\s+(\d+) kB',Path('/proc/meminfo').read_text(),re.M)[1])
  if available<4*1024*1024:report['deferred']={'name':name,'mem_available_kib':available};raise RuntimeError('Deferred below4GiB MemAvailable')
  r=xts.run(argv,out,name,timeout,budget);r['mem_available_kib']=available;report['commands'].append(r);return r
 try:
  parent=args.parent.resolve();old=json.loads(parent.read_text());report['parent']={'path':str(parent),'sha256':sha(parent)}
  if old['outcome']!='pass' or not old.get('host_checks') or not old.get('no_heap_profile'):raise ValueError('Host/ARM qualification required')
  for name,digest in old['artifact_hashes'].items():
   if sha(MAIN/name)!=digest:raise ValueError('Host artifact changed:'+name)
  for name,digest in old['owned_source_hashes'].items():
   if sha(ROOT/name)!=digest:raise ValueError('Tested source changed:'+name)
  for name,digest in old['dependencies'].items():
   if sha(name)!=digest:raise ValueError('Consumed host/ARM dependency changed:'+name)
  images={mode:avf.macho(parent.parent/(mode+'.macho')) for mode in ['normal','spin']}
  report['images']=images;report['host_checks']=old['host_checks'];report['host_vectors']=old['host_vectors'];report['corpus']=old['corpus']
  qemu=MAIN/'worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build/qemu-system-aarch64';shim=MAIN/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/Image'
  if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Accepted CPU/shim changed')
  # Reverify the complete accepted AVF source/tool binding, rather than treating
  # a binary name as qualification. XTS evidence is immutable source for this reuse.
  parent_xts=Path(old['parent']['path']);qualified=json.loads(parent_xts.read_text());binding=qualified['avf_inputs'];report['avf_inputs']=binding
  for name,digest in binding['reports'].items():
   if sha(name)!=digest:raise ValueError('Accepted AVF source report changed')
  if binding['pin']!=avf.PIN:raise ValueError('AVF helper pin changed')
  if sha(MAIN/'tools/build/qemu_host.py')!=binding['supervisor_sha256'] or sha(MAIN/'tools/verify/avf_handoff.py')!=binding['qualified_helpers_sha256']:raise ValueError('Accepted CPU supervision helper changed')
  base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot']
  corpus=json.loads((parent.parent/'vectors.json').read_text());report['guest_cases']=[]
  for name,mode,cookie in [('positive','normal','gcm_cookie=owned-adapter-v1'),('wrong-cookie','normal','gcm_cookie=wrong'),('corrupt-vector','normal','gcm_cookie=owned-adapter-v1'),('spin-timeout','spin','gcm_cookie=owned-adapter-v1')]:
   kernel=bytearray((parent.parent/(mode+'.macho')).read_bytes())
   if name=='corrupt-vector':
    blob=(parent.parent/'vectors.bin').read_bytes()
    if kernel.count(blob)!=1:raise ValueError('Unique full corpus blob required')
    # Mutate a nonempty expected ciphertext without changing plaintext/IV/tag.
    vector=next(v for v in corpus['vectors'] if len(v['ct'])>=32 and not v['bad']);wanted=bytes.fromhex(vector['ct'])
    offset=kernel.index(blob)+blob.index(wanted);kernel[offset]^=1;report['corrupt_vector_control']={'offset':offset,'original_expected':wanted.hex(),'mutation':'xor1 owned expected ciphertext inside actual embedded vector blob'}
   payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie);argv=[*base,'-initrd',payload]
   if name=='positive':
    dtb=out/'qemu.dtb';dump=list(argv);dump[2]+=',dumpdtb='+str(dtb);r=command(dump,'dtb-dump',5)
    if r['outcome']!='pass':raise ValueError('Actual DTB dump failed')
    report['qemu_dtb']=avf.fdt(dtb)
   r=command(argv,name,3 if mode=='spin' else 60);console=(out/(name+'.log')).read_text(errors='replace');passed='GCM ARM PASS' in console
   if name=='positive':
    marker=re.search(r'GCM ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0',console);entry=re.search(r'GCM SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
    ok=bool(marker and entry) and int(entry[1],16)==images[mode]['entry_pa'] and int(entry[2],16)==images[mode]['bootargs_pa'] and r['outcome']=='pass' and 'GCM SYNTHETIC HANDOFF VERIFIED' in console and 'GCM SYNTHETIC PSCI_SYSTEM_OFF' in console
    if marker:report['arm_checks']=int(marker[1],16);ok=ok and report['arm_checks']==old['host_checks']
   elif name=='wrong-cookie':ok=not passed and 'GCM SYNTHETIC REJECT command-cookie' in console and r['outcome']=='pass'
   elif name=='corrupt-vector':ok=not passed and 'GCM ARM FAIL' in console and 'GCM SYNTHETIC PSCI_SYSTEM_OFF' in console and r['outcome']=='pass'
   else:ok=not passed and 'GCM SYNTHETIC SPIN-CONTROL' in console and r['outcome']=='timeout'
   report['guest_cases'].append({'name':name,'accepted':ok,'payload_sha256':sha(payload),'console_sha256':sha(out/(name+'.log'))})
   if not ok:raise ValueError('Actual guest control failed:'+name)
  if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Immutable CPU input changed')
  report['outcome']='pass';report['summary']='Genuine typed owned GCM adapter: qualified vectors/state checks actually execute on accepted synthetic ARM CPU; no provider/XNU/native-device/private ABI/FIPS/side-channel qualification'
 except Exception as error:report['error']=repr(error)
 finally:
  report.setdefault('summary','Actual GCM CPU qualification failed or memory-deferred; retain commands and conditional markers, no complete qualification claim')
  report['owned_source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
  report['artifact_hashes']={str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()};report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','host_checks','arm_checks','guest_cases']},indent=2));return report['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
