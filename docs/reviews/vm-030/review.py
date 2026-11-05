#!/usr/bin/env python3
"""Independent bounded stop classifier review; never starts a VM/compiler."""
import argparse, copy, datetime, hashlib, importlib.util, json, math, os
from pathlib import Path
import resource, shutil, signal, subprocess, sys, time
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
P=MAIN/'worktrees/vm-030-20261106'
HERE=Path(__file__).resolve().parent
TOOL=P/'tools/build/avf_guest_stop.py'
TOOL_SHA='1c2dd72b2682b3ff8c45634626f4989d552f90eeafe04f5abe62aad3052582ee'
DESC_SHA='4e0119b5a19502d0dfdbba8ea94ec4023fd953df18030d8a3580e907e272661f'
EVIDENCE_SHA='30f97abcf05e9cd31c0b84048c0036fcaf33b361493ffa04a87afbe33609d912'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 out=a.out.resolve();out.relative_to(HERE);out.mkdir(parents=True,exist_ok=False)
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(100,100))
 r={'task':'REV-034','started_at':utc(),'outcome':'fail','checks':[],'controls':[],'inputs':[],'commands':[],'compiler_executed':False,'guest_executed':False}
 def check(name,ok,**detail):
  r['checks'].append(dict(name=name,passed=bool(ok),**detail))
  if not ok:raise ValueError(name)
 def bind(p,h=None,n=None):
  p=Path(p);s=p.stat();actual=sha(p)
  check('binding:'+str(p),(h is None or actual==h) and(n is None or s.st_size==n))
  row={'path':str(p),'sha256':actual,'bytes':s.st_size,'mode':s.st_mode&0o777};r['inputs'].append(row);return row
 def reject(name,fn,token=None):
  try:fn()
  except (ValueError,OSError,TypeError,KeyError) as e:row={'name':name,'passed':token is None or token in str(e),'type':type(e).__name__,'error':str(e)}
  else:row={'name':name,'passed':False,'error':'unexpected acceptance'}
  r['controls'].append(row)
  if not row['passed']:raise ValueError(name)
 def command(name,argv,expected=0):
  samples=[]
  for i in range(3):
   if i:time.sleep(1)
   value=int(next(x for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1])*1024
   samples.append({'utc':utc(),'monotonic':time.monotonic(),'MemAvailable_bytes':value})
  check('memory:'+name,all(s['MemAvailable_bytes']>=4*1024**3 for s in samples) and all(b['monotonic']-a['monotonic']>=1 for a,b in zip(samples,samples[1:])))
  start=time.monotonic();timed=False
  with(out/(name+'.stdout')).open('xb')as so,(out/(name+'.stderr')).open('xb')as se:
   env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',LC_ALL='C')
   child=subprocess.Popen(list(map(str,argv)),cwd=P,env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
   try:code=child.wait(timeout=10)
   except subprocess.TimeoutExpired:
    timed=True
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    code=child.wait(timeout=2)
  r['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':code,'expected_exit_code':expected,'timed_out':timed,'reaped':True,'elapsed_seconds':time.monotonic()-start,'admission':samples,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
  check('command:'+name,code==expected and not timed)
  return(out/(name+'.stdout')).read_bytes()
 try:
  bind(TOOL,TOOL_SHA);bind(P/'fixtures/public/avf-guest-stop/inputs.json',DESC_SHA)
  bind(P/'docs/procedures/avf-guest-stop/evidence-final.json',EVIDENCE_SHA)
  data=json.loads((P/'fixtures/public/avf-guest-stop/inputs.json').read_text())
  ev=json.loads((P/'docs/procedures/avf-guest-stop/evidence-final.json').read_text())
  for x in ev['implementation_hashes']:bind(MAIN/x['path'],x['sha256'],x['size'])
  for key,x in data['inputs'].items():bind(MAIN/x['path'],x['sha256'],x['size'])
  # The final producer148 artifact capsules are hashed, never re-executed.
  for x in ev['artifact_hashes']:bind(MAIN/x['path'],x['sha256'],x['size'])
  b=command('frozen-source',['git','show','925080513827cd32d5ea36db386baaad81d9f5b7:tools/build/avf_guest_stop.py'])
  check('actual-commit-tool-identity',hashlib.sha256(b).hexdigest()==TOOL_SHA)
  spec=importlib.util.spec_from_file_location('immutable_stop',TOOL);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  prepared=m.preflight(MAIN,P/'fixtures/public/avf-guest-stop/inputs.json');save(out/'source-preflight.json',prepared)
  check('source-preflight-pass',prepared['outcome']=='pass' and prepared['guest_executed'] is False and prepared['kernel_image_qualified'] is False)
  check('legacy-pid1-still-rejected',data['pid1_runtime_admissible'] is False and data['replacement_task']=='VM-034')
  wrong=copy.deepcopy(data);wrong['source_pins']['xnu']='0'*40;save(out/'wrong-source-pin.json',wrong)
  check('wrong-canonical-source-pin-rejected',m.preflight(MAIN,out/'wrong-source-pin.json')['outcome']=='fail')
  wrong=copy.deepcopy(data);wrong['inputs']['psci']['composition_member']['oid']='0'*40;save(out/'wrong-composed-member.json',wrong)
  check('wrong-composed-member-rejected',m.preflight(MAIN,out/'wrong-composed-member.json')['outcome']=='fail')
  # Genuine previously recorded VM027 capture, not a new guest run.
  cap=MAIN/'worktrees/vm-027-20261106/artifacts/avf-guest-device-tree/capture-1'
  bind(cap/'report.json','02319a8a9c7de8f1fe1f9a3c10b35b24d51c4f4d095b4fd34d9830f9bc34d41e',9944)
  bind(cap/'console.log','41632a0e31625f322f819031a013f59463399ff6def2c265efbdbb8a0755af33',909)
  captured=json.loads((cap/'report.json').read_text());console_actual=(cap/'console.log').read_bytes()
  qmp=[x['received'] for x in captured['qmp'] if 'received'in x and 'event'in x['received']]
  save(out/'actual-vm027-events.json',qmp)
  check('actual-host-quit-origin',any(x.get('sent',{}).get('execute')=='quit' for x in captured['qmp']) and any(e.get('event')=='SHUTDOWN' and e.get('data')=={'guest':False,'reason':'host-qmp-quit'} for e in qmp))
  # All other facts are explicitly AUTHORed contrast controls, never recovered observations.
  host={'guest_started':True,'argv':['qemu-system-aarch64','-no-reboot'],'boot_args':'cpus=1 -v console_quiet=0 avf_exit=1','termination':{'timed_out':False,'host_signals':[],'live_owned_pids':[],'exit_code':0,'elapsed_seconds':1.0,'deadline_seconds':10.0}}
  halt=b'Darwin Kernel Version SYNTHETIC\navf: halt (PSCI SYSTEM_OFF)\n'
  event=[{'event':'SHUTDOWN','data':{'guest':True,'reason':'guest-shutdown'}}]
  def classify(name,con=halt,events=event,sup=host,expected='halt',want='inconclusive'):
   result=m.classify(con,events,sup,expected);row={'name':name,'passed':result['classification']==want,'result':result,'synthetic_other_facts':True};r['controls'].append(row)
   if not row['passed']:raise ValueError(name)
   return result
  classify('actual-vm027-console-qmp-rejected',console_actual,qmp)
  classify('actual-hostquit-with-synthetic-favorable-console',halt,qmp)
  classify('synthetic-halt-positive',want='guest-stop')
  panic=b'Darwin Kernel Version SYNTHETIC\nVM002: pid=1 ostype=Darwin owned-entry=v1\navf: kernel panic: panic(cpu0): initproc failed to start\navf: powering off (PSCI SYSTEM_OFF)\n'
  classify('synthetic-pid1-classifier-only',panic,expected='pid1-panic',want='guest-stop')
  classify('synthetic-reset-positive',b'avf: reboot (PSCI SYSTEM_RESET)\n',[{'event':'SHUTDOWN','data':{'guest':True,'reason':'guest-reset'}}],expected='reset',want='guest-stop')
  for name,events in [('host-false',[{'event':'SHUTDOWN','data':{'guest':False,'reason':'guest-shutdown'}}]),('integer-guest',[{'event':'SHUTDOWN','data':{'guest':1,'reason':'guest-shutdown'}}]),('wrong-reason',[{'event':'SHUTDOWN','data':{'guest':True,'reason':'guest-reset'}}]),('duplicate',event+event),('reset-event',event+[{'event':'RESET','data':{}}]),('panic-event',event+[{'event':'GUEST_PANICKED','data':{}}]),('missing',[])]:classify(name,events=events)
  for name,con in [('no-intent',b'Darwin Kernel Version'),('duplicate-intent',halt+halt),('firmware-refusal',halt+m.REFUSED),('shim-fatal',halt+b'avfboot: FATAL:'),('conflicting-intent',halt+m.RESET),('truncated-intent',halt[:-7])]:classify(name,con)
  for name,key,val in [('timedout','timed_out',True),('host-signal','host_signals',['SIGTERM']),('live-child','live_owned_pids',[123]),('exit-bool','exit_code',False),('elapsed-bool','elapsed_seconds',True),('negative-time','elapsed_seconds',-1),('at-deadline','elapsed_seconds',10),('nan','elapsed_seconds',float('nan')),('infinite-deadline','deadline_seconds',float('inf'))]:
   h=copy.deepcopy(host);h['termination'][key]=val;classify(name,sup=h,want='host-cleanup' if key in ['timed_out','host_signals'] else 'inconclusive')
  for name,key,val in [('guest-int','guest_started',1),('paused','argv',['qemu','-no-reboot','-S']),('nonterminating','argv',['qemu','-no-reboot','-no-shutdown']),('wrong-args','boot_args','cpus=1 avf_exit=0')]:
   h=copy.deepcopy(host);h[key]=val;classify(name,sup=h)
  classify('pid1-ordering',panic.replace(b'Darwin Kernel Version SYNTHETIC\n',b'')+b'Darwin Kernel Version',expected='pid1-panic')
  reject('malformed-event-data',lambda:m.classify(halt,[{'event':'SHUTDOWN','data':[]}],host))
  record_dir=out/'records';record_dir.mkdir();(record_dir/'console').write_bytes(panic);save(record_dir/'qmp.json',event);save(record_dir/'preflight.json',prepared)
  h=copy.deepcopy(host);h.update(source_preflight_sha256=sha(record_dir/'preflight.json'),qemu_sha256=prepared['inputs']['qemu_binary']['sha256']);save(record_dir/'supervisor.json',h)
  record={'schema_version':1}
  for key,name in [('console','console'),('qmp','qmp.json'),('preflight','preflight.json'),('supervisor','supervisor.json')]:record[key]={'path':name,'sha256':sha(record_dir/name)}
  save(record_dir/'runtime.json',record)
  reject('full-assess-legacy-even-with-synthetic-pid1-positive',lambda:m.assess(record_dir/'runtime.json','pid1-panic'),'Legacy PID1 runtime admission is rejected')
  (record_dir/'escape').symlink_to(cap/'console.log');reject('escape-symlink',lambda:m.relative(record_dir,'escape'),'escapes')
  reject('path-traversal',lambda:m.relative(record_dir,'../source-preflight.json'),'relative')
  (record_dir/'nonfinite.json').write_text('{"elapsed_seconds": NaN}')
  reject('json-nonfinite',lambda:m.read_json(record_dir/'nonfinite.json'),'Nonfinite')
  bad=copy.deepcopy(record);bad['qmp']['sha256']='0'*64;save(record_dir/'wrong-hash.json',bad)
  reject('captured-data-hash',lambda:m.assess(record_dir/'wrong-hash.json','halt'),'hash mismatch')
  # Real offline CLI against owned record, exercising legacy rejection without running QEMU.
  command('actual-cli-legacy',[sys.executable,'-s',TOOL,'--out',out/'cli-assessment.json','assess','--record',record_dir/'runtime.json','--expected','pid1-panic'],2)
  for x in r['inputs']:check('immutable-after:'+x['path'],sha(x['path'])==x['sha256'] and Path(x['path']).stat().st_size==x['bytes'] and Path(x['path']).stat().st_mode&0o777==x['mode'])
  r['outcome']='pass'
 except Exception as e:r['error']={'type':type(e).__name__,'message':str(e)}
 r['finished_at']=utc();r['reviewer_sha256']=sha(__file__);r['proc_self_VmHWM_bytes']=int(next(x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmHWM:')).split()[1])*1024
 save(out/'report.json',r);print(json.dumps({'outcome':r['outcome'],'checks':len(r['checks']),'controls':len(r['controls']),'commands':len(r['commands']),'error':r.get('error'),'report':str(out/'report.json')}));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
