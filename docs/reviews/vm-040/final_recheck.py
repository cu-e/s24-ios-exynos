#!/usr/bin/env python3
"""Independent narrowly scoped correction regression; Python controls only."""
import copy,datetime,hashlib,importlib.util,json,os,resource,struct,sys,time
from pathlib import Path
from types import SimpleNamespace
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');OLD=MAIN/'worktrees/vm-040-eh-20261106';NEW=MAIN/'worktrees/vm-040-consumer-20261106';HERE=Path(__file__).resolve().parent

def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
 out=HERE/'runs/correction-c8bd677-1';out.mkdir(parents=True,exist_ok=False)
 r={'kind':'independent-correction-host-controls','checks':[],'findings':[],'lease_cases':[],'FDT_cases':[],'QEMU_executed':False,'compiler_executed':False,'guest_executed':False,'outcome':'fail'}
 def check(n,ok):
  r['checks'].append({'name':n,'passed':bool(ok)})
  if not ok:raise ValueError(n)
 try:
  check('correction-frozen-tool',sha(NEW/'tools/run/avf_kernel_boot.py')=='233da39b23ea8986e83db6bfdceb8f23c52b0c6ac044f7f1d5f30d451e145c06')
  check('original-tool-unchanged',sha(OLD/'tools/run/avf_kernel_boot.py')=='82dc4f31e0a43431e49741bc26368ff81c3820a21985a97fef82c11f6f9e6589')
  for scenario in ['late-expiry','late-revocation','memory-drop','Stop','valid']:
   c=module('fixed_'+scenario,NEW/'tools/run/avf_kernel_boot.py');pins=c.read_json(c.FIXTURE);sup=c.helper(MAIN,pins,'process');saved_sample=sup.sample
   area=out/scenario;area.mkdir();c.ROOT=area;base=area/'artifacts/avf-kernel-boot';base.mkdir(parents=True)
   plan_path=base/'control-plan.json';run=base/'control-run';stop=c.Stop()
   plan={'main':str(area),'image_id':'EXPLICIT-PYTHON-CONTROL-NOT-AN-IMAGE','cwd':str(run),'admission':{'descriptor':{'sha256':'a'*64}},'descriptor':{},'collector_sha256':c.digest(c.__file__),'fixture_sha256':c.digest(c.FIXTURE),'argv':[sys.executable,'-s','-c','print("owned Python admission regression")'],'layout':{},'package':{},'checked_layout':{},'combined_boot_args':''};save(plan_path,plan)
   epoch=datetime.datetime.now(datetime.timezone.utc);clock={'offset':0.,'phase':'admission'};case={'name':scenario,'real_Popen_calls':[],'lease_checks':[],'sleeps':[],'admission':[],'dependency_seams':'prepare/ROOT/protocol factory and virtual lease clock; actual lease, collect loop, own_process, Popen and cleanup unchanged'}
   r['lease_cases'].append(case)
   grant={'id':'REVIEW-NOT-A-ROOT-GUEST-LEASE','owner':c.OWNER,'task':'VM-040','protocol':c.PROTOCOL,'plan_sha256':c.digest(plan_path),'collector_sha256':c.digest(c.__file__),'image_descriptor_sha256':'a'*64,'guest_memory_mib':256,'owned_rss_limit_bytes':c.RSS_LIMIT,'deadline_seconds':c.DEADLINE,'output':str(run),'issued_at':epoch.isoformat(),'expires_at':(epoch+datetime.timedelta(seconds=2.5 if scenario=='late-expiry'else 120)).isoformat()}
   queue=area/'artifacts/team-coordination/20261106-team/resource-queue.json';queue.parent.mkdir(parents=True);save(queue,{'qemu':grant})
   for i in range(3):
    if i:time.sleep(1)
    snap=saved_sample();case['admission'].append({'monotonic':time.monotonic(),'MemAvailable_bytes':snap['MemAvailable_bytes'],'pressure':snap['pressure']});check('external-floor:'+scenario+str(i),snap['MemAvailable_bytes']>=4*1024**3 and not sup.pressured(snap))
   original_lease=c.lease;original_own=c.own_process;original_popen=c.subprocess.Popen
   def fake_sleep(seconds):case['sleeps'].append(seconds);clock['offset']+=seconds
   def checked_lease(main,lease_id,path,p):
    row={'virtual_seconds':clock['offset']};case['lease_checks'].append(row)
    try:
     a=original_lease(main,lease_id,path,p,current=epoch+datetime.timedelta(seconds=clock['offset']));row['accepted']=True
     if scenario=='Stop' and clock['phase']=='before_spawn':stop.request('Reviewer Stop during final lease validation')
     return a
    except Exception as e:row.update(accepted=False,error=str(e));raise
   def late_phase(*args):
    clock['phase']='before_spawn'
    if scenario=='late-expiry':clock['offset']=3
    if scenario=='late-revocation':save(queue,{'qemu':{**grant,'id':'REVOKED'}})
    return None
   def sample(session=None):
    snap=saved_sample(session)
    if scenario=='memory-drop'and clock['phase']=='before_spawn'and session is None:snap['MemAvailable_bytes']=0
    return snap
   def traced_popen(argv,*args,**kwargs):
    check('only-owned-python-argv:'+scenario,argv==plan['argv']);case['real_Popen_calls'].append({'argv':argv,'virtual_seconds':clock['offset']});return original_popen(argv,*args,**kwargs)
   class Captured(Exception):pass
   def observed_own(*args,**kwargs):
    kwargs['seconds']=2;kwargs['rss_limit']=256<<20
    rec=original_own(*args,**kwargs);save(area/'process-record.json',rec);case['process_record']=rec;raise Captured()
   c.prepare=lambda *args,**kwargs:copy.deepcopy(plan);c.helper=lambda *args:sup;c.protocol_operation=late_phase;c.lease=checked_lease;c.own_process=observed_own;c.time=SimpleNamespace(monotonic=time.monotonic,sleep=fake_sleep);sup.sample=sample;c.subprocess.Popen=traced_popen
   try:c.collect(plan_path,grant['id'],stop)
   except Captured:pass
   except Exception as e:case['refusal']={'type':type(e).__name__,'message':str(e)}
   finally:c.subprocess.Popen=original_popen;sup.sample=saved_sample
   check('exactly-two-admission-sleeps:'+scenario,case['sleeps'][:2]==[1,1]and len([s for s in case['sleeps']if s==1])==2)
   if scenario=='valid':
    rec=case.get('process_record',{});check('valid-one-natural-python',len(case['real_Popen_calls'])==1 and rec.get('exit_code')==0 and rec.get('live_owned_pids')==[]and rec.get('host_signals')==[])
   else:check('zero-Popen:'+scenario,len(case['real_Popen_calls'])==0)
  c=module('fixed_fdt',NEW/'tools/run/avf_kernel_boot.py');old=(OLD/'artifacts/avf-kernel-boot/controls-9efba94-1/fdt/authored-input.dtb').read_bytes();props=c.fdt(old);layout={'payload_base':0x48000000};package={'size':64}
  def predicate(name,p,expected):
   try:value=c.fdt_contract(p,layout,package);accepted=True;error=None
   except Exception as e:accepted=False;error=str(e)
   row={'name':name,'accepted':accepted,'expected_acceptance':expected,'error':error};r['FDT_cases'].append(row)
   if accepted!=expected:r['findings'].append(row)
  predicate('original-invalid-memory-fixture',props,False)
  good=copy.deepcopy(props);good[('/memory@40000000','device_type')]=b'memory\0';predicate('corrected-memory-positive',good,True)
  for name,key,value in [('prefixed-PL011',('/pl011@9000000','compatible'),b'xarm,pl011\0'),('unterminated-PL011',('/pl011@9000000','compatible'),b'arm,pl011'),('prefixed-GIC',('/intc@8000000','compatible'),b'xarm,gic-v3\0'),('zero-GIC',('/intc@8000000','reg'),struct.pack('>4Q',0x08000000,0,0x080a0000,0)),('offbyone-GIC',('/intc@8000000','reg'),struct.pack('>4Q',0x08000000,0x10001,0x080a0000,0xf60000)),('wrong-memory-type',('/memory@40000000','device_type'),b'xmemory\0'),('PL011-and-8250-ambiguity',('/pl011@9000000','compatible'),b'arm,pl011\0ns16550a\0')]:
   p=copy.deepcopy(good);p[key]=value;predicate(name,p,False)
  root_only=copy.deepcopy(props);root_only[('/', 'device_type')]=b'memory\0';root_only[('/', 'reg')]=struct.pack('>QQ',0x40000000,256<<20);predicate('root-is-not-a-memory-child',root_only,False)
  p=copy.deepcopy(good);p[('/pl011@9000000','compatible')]=b'vendor,model\0arm,pl011\0';predicate('exact-later-token-positive',p,True)
  p=copy.deepcopy(good);p[('/other-uart','compatible')]=b'ns16550a\0';predicate('other-node-8250-priority',p,False)
  p=copy.deepcopy(good);p[('/other-uart','compatible')]=b'arm,pl011\0';predicate('competing-PL011-consumer',p,False)
  p=copy.deepcopy(good);p[('/other-gic','compatible')]=b'arm,gic-v3\0';predicate('competing-GIC-consumer',p,False)
  check('closed-image-allowlist',c.read_json(c.FIXTURE)['image_admissions']==[])
  r['outcome']='pass'if not r['findings']else'fail'
 except Exception as e:r['error']={'type':type(e).__name__,'message':str(e)}
 r['proc_self_VmHWM_bytes']=int(next(x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmHWM:')).split()[1])*1024;r['reviewer_sha256']=sha(__file__)
 save(out/'report.json',r);print(json.dumps({'outcome':r['outcome'],'checks':len(r['checks']),'findings':r['findings'],'error':r.get('error')}));return 0 if r['outcome']=='pass'else 1
if __name__=='__main__':raise SystemExit(main())
