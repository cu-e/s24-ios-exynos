#!/usr/bin/env python3
"""Independent REV-028 focused review; no compiler or guest."""
import argparse, copy, datetime, hashlib, importlib.util, io, json, os
from pathlib import Path
import resource, shutil, signal, struct, subprocess, sys, time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
PRODUCER = MAIN / 'worktrees/vm-024-20261106'
TOOL = PRODUCER / 'tools/build/avf_guest_mockfs.py'
HERE = Path(__file__).resolve().parent
PINS = {
 'tools/build/avf_guest_mockfs.py': 'a850d42599874826deb512c36833557bfc90e2a2de905de74c19834f54e5bd0b',
 'fixtures/public/avf-guest-mockfs/package_candidate.py':'442016995020c45c07057e3c7644cd3d0111e732bc644f0150466f6c5aa9e426',
 'fixtures/public/avf-guest-mockfs/vm034-candidate.json':'43dcec6b0c0a817b8942c7fe0c484afb973853f098c5bd5c80999ea679f5194b',
 'docs/procedures/avf-guest-mockfs/candidate-output-manifest.json':'aa8c56bbdbad5190d3e2cb509a3ba62493d4fb56c0376ae4cf4cd219996fb0c7',
 'docs/procedures/avf-guest-mockfs/results/candidate-fac53e7-1-report.json':'26e65cec9ed1b22b6451a17184d29ce11c76d1e7d7872bbdea050a7805ca7c82',
 'docs/procedures/avf-guest-mockfs/results/candidate-fac53e7-1-artifacts.json':'fff2d1c681758a63884b589594dc73bf1f18d3f0ad73d6059ed5cad95990cc14',
}

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()

def save(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 out=a.out.resolve();out.relative_to(HERE);out.mkdir(parents=True,exist_ok=False)
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(100,100))
 r={'task':'REV-028','kind':'host-test','origin':'local-host','started_at':utc(),'outcome':'fail',
    'checks':[],'controls':[],'commands':[],'inputs':[],'compiler_executed':False,'guest_executed':False}
 env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',LC_ALL='C')
 def check(name,ok,**detail):
  r['checks'].append(dict(name=name,passed=bool(ok),**detail))
  if not ok:raise ValueError(name)
 def bound(p,expected=None,size=None):
  p=Path(p);st=p.stat();actual=sha(p)
  check('binding:'+str(p), (expected is None or actual==expected) and (size is None or st.st_size==size))
  row={'path':str(p),'sha256':actual,'bytes':st.st_size,'mode':st.st_mode&0o777};r['inputs'].append(row);return row
 def admission():
  samples=[]
  for i in range(3):
   if i:time.sleep(1)
   value=int(next(x for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1])*1024
   samples.append({'utc':utc(),'monotonic':time.monotonic(),'MemAvailable_bytes':value})
  check('three-sample-admission',all(x['MemAvailable_bytes']>=4*1024**3 for x in samples) and all(b['monotonic']-a['monotonic']>=1 for a,b in zip(samples,samples[1:])))
  return samples
 def run(name,argv,expected=0,cwd=PRODUCER):
  samples=admission();start=time.monotonic();timed=False
  with (out/(name+'.stdout')).open('xb') as so,(out/(name+'.stderr')).open('xb') as se:
   p=subprocess.Popen(list(map(str,argv)),cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
   try:code=p.wait(timeout=10)
   except subprocess.TimeoutExpired:
    timed=True
    try:os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    code=p.wait(timeout=2)
  row={'name':name,'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':code,'expected_exit_code':expected,'timed_out':timed,'elapsed_seconds':time.monotonic()-start,'admission':samples,
       'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr')),'child_reaped':True}
  r['commands'].append(row);check('command:'+name,code==expected and not timed);return (out/(name+'.stdout')).read_bytes()
 def reject(name,fn,contains=None):
  try:fn()
  except (ValueError,OSError,KeyError,struct.error,UnicodeError) as e:
   row={'name':name,'passed':contains is None or contains in str(e),'type':type(e).__name__,'message':str(e)}
  else:row={'name':name,'passed':False,'error':'unexpected acceptance'}
  r['controls'].append(row)
  if not row['passed']:raise ValueError(name)
 try:
  for path,h in PINS.items():bound(PRODUCER/path,h)
  for n,commit in enumerate(['19965c7','7a71236','ff41a8e','b716bbd','2257b31']):
   b=run('git-source-'+str(n),['git','show',commit+':tools/build/avf_guest_mockfs.py'])
   check('frozen-tool-at:'+commit,hashlib.sha256(b).hexdigest()==PINS['tools/build/avf_guest_mockfs.py'])
  sources=json.loads((PRODUCER/'fixtures/public/avf-guest-mockfs/sources.json').read_text())
  for s in sources['sources']:
   p=MAIN/s['path'];bound(p,s['sha256']);b=p.read_bytes()
   check('canonical-blob:'+s['path'],hashlib.sha1(('blob '+str(len(b))+'\0').encode()+b).hexdigest()==s['git_blob_sha1'])
  for f in ['artifact-index.json','candidate-fac53e7-1-artifacts.json']:
   rows=json.loads((PRODUCER/'docs/procedures/avf-guest-mockfs/results'/f).read_text())
   for row in rows:
    p=Path(row['path']);bound(p if p.is_absolute() else PRODUCER/p,row['sha256'],row['bytes'])
  manifest=json.loads((PRODUCER/'docs/procedures/avf-guest-mockfs/candidate-output-manifest.json').read_text())
  for pin in manifest['candidate_inputs']:bound(MAIN/pin['path'],pin['sha256'])
  spec=json.loads((PRODUCER/'fixtures/public/avf-guest-mockfs/vm034-candidate.json').read_text())
  roles={p['role']:MAIN/p['path'] for p in spec['pins']}
  binary=roles['candidate_executable'].read_bytes();n=len(binary)
  artifact=PRODUCER/'artifacts/avf-guest-mockfs/candidate-fac53e7-1/package-one'
  meta=json.loads((artifact/'package.json').read_text());image=(artifact/'root.ramdisk').read_bytes()
  check('independent-exact-prefix-tail',n==16512 and len(image)==32768 and image[:n]==binary and image[n:]==bytes(16256))
  check('independent-image-identity',hashlib.sha256(image).hexdigest()=='b26710980746c0fbc48f4d40f9b43533784617c7332ba54055e44da2d0f12b59')
  check('independent-metadata-map',meta['alignment']==16384 and meta['mount_argument']=='rd=md0' and meta['executable_path']=='/sbin/launchd' and meta['executable_qualified'] is False and meta['guest_executed'] is False)
  check('independent-provenance-identity',meta['provenance']==json.loads(roles['mockfs_provenance'].read_text()) and meta['provenance_descriptor_sha256']==sha(roles['mockfs_provenance']))
  check('independent-real-entry',struct.unpack_from('<Q',binary,528+272)[0]==0x100003d9c)
  module=importlib.util.spec_from_file_location('immutable_mockfs',TOOL);m=importlib.util.module_from_spec(module);module.loader.exec_module(m)
  check('actual-package-verify',m.verify(artifact)==meta)
  local=out/'local';local.mkdir()
  def changed(name,mutate=None,metadata=None):
   d=local/name;shutil.copytree(artifact,d)
   if mutate:
    b=bytearray((d/'root.ramdisk').read_bytes());mutate(b);(d/'root.ramdisk').write_bytes(b)
   if metadata:
    o=json.loads((d/'package.json').read_text());metadata(o,d);save(d/'package.json',o)
   return d
  cases=[('prefix-flip',lambda b:b.__setitem__(16000,b[16000]^1),'executable hash mismatch'),
         ('truncate',lambda b:b.pop(),'length/alignment'),('extend',lambda b:b.extend(b'\0'),'length/alignment')]
  for name,mut,error in cases:
   d=changed(name,mut);reject(name,lambda:m.verify(d),error)
  d=changed('padding-self-consistent',lambda b:b.__setitem__(n,1),lambda o,d:o.update(image_sha256=sha(d/'root.ramdisk')))
  reject('nonzero-padding-despite-updated-image-hash',lambda:m.verify(d),'nonzero image padding')
  for field,value in [('guest_executed',True),('executable_qualified',True),('mount_argument','rd=md1'),('executable_path','/bin/sh'),('alignment',4096)]:
   d=changed('metadata-'+field,metadata=lambda o,d:o.update({field:value}));reject('metadata-'+field,lambda:m.verify(d))
  d=changed('provenance-input',metadata=lambda o,d:o['provenance'].update(input_sha256='0'*64));reject('provenance-input',lambda:m.verify(d),'executable hash mismatch')
  for name,offset,fmt,value in [('wrong-cpu',4,'I',0x1000007),('bad-table-extent',20,'I',0x100000),('wrong-entry',800,'Q',0),('dynamic-command',488,'I',0xe)]:
   b=bytearray(binary);struct.pack_into('<'+fmt,b,offset,value);reject(name,lambda:m.parse(io.BytesIO(b),len(b)))
  symlink=local/'symlink-pid1';symlink.symlink_to(roles['candidate_executable']);reject('symlink-final-input',lambda:m.open_input(symlink))
  fifo=local/'fifo';os.mkfifo(fifo);reject('nonblocking-fifo-input',lambda:m.open_input(fifo),'regular file')
  existing=local/'existing';existing.mkdir();(existing/'sentinel').write_bytes(b'preserve')
  reject('existing-output',lambda:m.pack(roles['candidate_executable'],sha(roles['candidate_executable']),roles['mockfs_provenance'],existing))
  check('existing-output-unchanged',list(p.name for p in existing.iterdir())==['sentinel'] and (existing/'sentinel').read_bytes()==b'preserve')
  reject('wrong-expected-content-hash',lambda:m.pack(roles['candidate_executable'],'0'*64,roles['mockfs_provenance'],local/'wrong-hash'),'provenance origin/hash mismatch')
  # Real on-disk mutation at deterministic seam after genuine parsing, before copy.
  mutable=local/'mutable';mutable.write_bytes(binary);original=m.parse
  def race(f,length):
   parsed=original(f,length)
   with mutable.open('r+b') as w:w.seek(16000);w.write(b'R');w.flush();os.fsync(w.fileno())
   return parsed
  m.parse=race
  try:reject('input-mutation-between-parse-copy',lambda:m.pack(mutable,sha(roles['candidate_executable']),roles['mockfs_provenance'],local/'raced'),'input changed while copying')
  finally:m.parse=original
  check('failed-copy-without-success-metadata',(local/'raced/root.ramdisk').exists() and not (local/'raced/package.json').exists())
  # Signature validation is intentionally outside structural policy. Carry opaque bytes.
  signed=bytearray(binary);struct.pack_into('<II',signed,16,7,800);struct.pack_into('<IIII',signed,816,0x1d,16,len(binary),8);signed.extend(b'NOTCSIG!')
  accepted=m.parse(io.BytesIO(signed),len(signed));check('signature-is-opaque-not-validated',accepted['commands']==7)
  r['explicit_boundary']='Opaque code-signature payload is accepted structurally; no cryptographic or real kernel signing admission.'
  # One real CLI read-only check, preserving originals and explicit exit/output hashes.
  run('actual-cli-verify',[sys.executable,'-s',TOOL,'verify','--package',artifact])
  for pin in list(r['inputs']):
   check('immutable-after:'+pin['path'],sha(pin['path'])==pin['sha256'] and Path(pin['path']).stat().st_size==pin['bytes'] and Path(pin['path']).stat().st_mode&0o777==pin['mode'])
  r['outcome']='pass'
 except Exception as e:r['error']={'type':type(e).__name__,'message':str(e)}
 r['finished_at']=utc();r['reviewer_sha256']=sha(__file__)
 r['proc_self_VmHWM_bytes']=int(next(s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')).split()[1])*1024
 save(out/'report.json',r)
 print(json.dumps({'outcome':r['outcome'],'checks':len(r['checks']),'controls':len(r['controls']),'commands':len(r['commands']),'error':r.get('error'),'report':str(out/'report.json')}))
 return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
