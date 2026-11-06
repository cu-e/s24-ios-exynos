#!/usr/bin/env python3
"""Focused independent real-signal restoration regression, no children."""
import ast,copy,datetime,hashlib,json,os,signal,time
from pathlib import Path
from types import ModuleType
D=Path(__file__).parent;O=D/'runs/correction1';O.mkdir(parents=True,exist_ok=False)
R=Path('/home/egor/dev/pet/s24-ios-exynos');B=R/'worktrees/gpu-012-admission-20261106';F=R/'worktrees/gpu-012-signalfix-20261106';CANCEL={signal.SIGINT,signal.SIGTERM,signal.SIGALRM};checks=[];inputs={}
def sha(p):
 raw=Path(p).read_bytes();h=hashlib.sha256(raw).hexdigest();inputs[str(Path(p))]=h;return h
def check(name,ok):
 checks.append(name)
 if not ok:raise AssertionError(name)
def module(p):
 m=ModuleType('independent_fixed_launcher');m.__file__=str(p);raw=Path(p).read_bytes();sha(p);exec(compile(raw,str(p),'exec'),m.__dict__);return m
mem=[]
for i in range(3):
 v=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;check('Stable4GiB-'+str(i),v>=4*1024**3);mem.append(v)
 if i<2:time.sleep(1)
start=time.monotonic();l=module(F/'src/platform/gpu/native/userclient/launcher.py');cases=[]
report={'kind':'host-test','origin':'local-host','task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATGPU-003','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'cases':cases,'inputs':inputs,'no_child_engine_or_target_command_or_allocation':True}
initial={s:signal.getsignal(s) for s in CANCEL};initialmask=signal.pthread_sigmask(signal.SIG_BLOCK,set());originalsignal=signal.signal;originaltimer=signal.setitimer
try:
 check('Exact corrected launcher',sha(F/'src/platform/gpu/native/userclient/launcher.py')=='ea82de7bb04578166bfec433bcbdaf1ed01194b3e02be8b3ca274f9b04ab1afc')
 for name in ['src/platform/gpu/native/userclient/admission.py','fixtures/public/gpu-userclient/admission-policy.json']:
  check('Executor/policy unchanged '+name,sha(F/name)==sha(B/name))
 parent=json.loads((F/'fixtures/public/gpu-userclient/current-policy.json').read_text())
 for name in parent['source_freeze']['files']:check('Native/ABI/fixture unchanged '+name,sha(F/name)==sha(B/name))
 policy=json.loads((F/'fixtures/public/gpu-userclient/admission-policy.json').read_text());check('Execution remains disabled null authority',policy['execution_enabled'] is False and policy['final_binding'] is None)
 old=ast.parse((B/'src/platform/gpu/native/userclient/launcher.py').read_text());new=ast.parse((F/'src/platform/gpu/native/userclient/launcher.py').read_text())
 for tree in [old,new]:
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='guarded');outer=next(n for n in fn.body if isinstance(n,ast.Try));outer.finalbody=[]
 check('Only guarded finally AST changes',ast.dump(old,include_attributes=False)==ast.dump(new,include_attributes=False))
 # A restoration API wrapper sends real signals only at the exact seam.
 # All original handlers are safe callables except the exact defaultINT repro.
 for name,inject,timerstage,blocked,default,callbackcancel in [
  ('exact-original-first-INT',(signal.SIGINT,),False,False,True,False),
  ('repeat-all-restoration',tuple([signal.SIGINT,signal.SIGTERM,signal.SIGALRM]*2),False,False,False,False),
  ('first-TERM-timer',(signal.SIGTERM,),True,False,False,False),
  ('caller-blocked-pending-INT',(signal.SIGINT,signal.SIGINT),False,True,False,False),
  ('callback-first-and-repeat',(),False,False,False,True)]:
  signal.pthread_sigmask(signal.SIG_BLOCK,CANCEL);delivered=[];before={}
  def caller(n,f):delivered.append({'signal':n,'handlers_complete':all(signal.getsignal(s)==before[s] for s in CANCEL),'mask':sorted(int(x) for x in signal.pthread_sigmask(signal.SIG_BLOCK,set()))})
  for s in CANCEL:before[s]=signal.default_int_handler if default and s==signal.SIGINT else caller;originalsignal(s,before[s])
  working=set(initialmask)|{signal.SIGUSR1}
  if blocked:working.add(signal.SIGINT)
  signal.pthread_sigmask(signal.SIG_SETMASK,working);fired=False
  def fire():
   global fired
   if not fired:
    fired=True
    for s in inject:os.kill(os.getpid(),s)
  def sig(n,h):
   if not timerstage and n==signal.SIGALRM and h==before[signal.SIGALRM]:fire()
   return originalsignal(n,h)
  def timer(which,seconds,*args):
   if timerstage and seconds==0:fire()
   return originaltimer(which,seconds,*args)
  signal.signal=sig;signal.setitimer=timer;escaped=None;result=None
  def callback():
   if callbackcancel:
    try:os.kill(os.getpid(),signal.SIGINT)
    finally:
     for s in [signal.SIGINT,signal.SIGTERM,signal.SIGALRM]:os.kill(os.getpid(),s)
   return 23
  try:result=l.guarded(callback,.5)
  except BaseException as e:escaped=type(e).__name__
  finally:signal.signal=originalsignal;signal.setitimer=originaltimer
  actualmask=set(signal.pthread_sigmask(signal.SIG_BLOCK,set()));pending=set(signal.sigpending())&CANCEL
  check(name+' all original handlers restored',all(signal.getsignal(s)==before[s] for s in CANCEL))
  check(name+' exact caller mask restored',actualmask==working)
  check(name+' timer disarmed',signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
  if default:check(name+' pending belongs to original default handler',escaped=='KeyboardInterrupt')
  elif blocked:
   check(name+' pending preserved undelivered',pending=={signal.SIGINT} and delivered==[])
   signal.pthread_sigmask(signal.SIG_SETMASK,working-{signal.SIGINT})
   check(name+' caller unblocks exact pending',len(delivered)==1 and delivered[0]['signal']==signal.SIGINT)
  elif callbackcancel:check(name+' callback cancellation cleanup unaffected',escaped is None and result['outcome']=='cancelled' and len(result['signals'])==4)
  else:check(name+' pending sent to originals after complete restoration',escaped is None and set(x['signal'] for x in delivered)==set(inject) and all(x['handlers_complete'] for x in delivered))
  cases.append({'case':name,'injected_signals':list(inject),'escaped':escaped,'result':result,'original_handler_deliveries':delivered,'mask_at_return':sorted(int(x) for x in actualmask),'pending_at_return':sorted(int(x) for x in pending)})
  signal.pthread_sigmask(signal.SIG_BLOCK,CANCEL)
  # No pending signal is consumed silently: deliver any remaining to the safe
  # original callable before changing back to the reviewing process handlers.
  for s in CANCEL:originalsignal(s,caller)
  signal.pthread_sigmask(signal.SIG_UNBLOCK,CANCEL);signal.pthread_sigmask(signal.SIG_BLOCK,CANCEL)
  for s,h in initial.items():originalsignal(s,h)
  signal.pthread_sigmask(signal.SIG_SETMASK,initialmask)
 report['outcome']='pass'
finally:
 signal.signal=originalsignal;signal.setitimer=originaltimer;originaltimer(signal.ITIMER_REAL,0)
 signal.pthread_sigmask(signal.SIG_BLOCK,CANCEL)
 for s,h in initial.items():originalsignal(s,h)
 signal.pthread_sigmask(signal.SIG_SETMASK,initialmask)
 report['check_count']=len(checks);report['admission_MemAvailable_bytes']=mem;report['elapsed_seconds']=time.monotonic()-start;report['proc_status']=[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))];report['source_sha256']=sha(__file__)
 (O/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'outcome':report.get('outcome','fail'),'checks':len(checks),'evidence':str(O/'evidence.json'),'memory':report['proc_status']}))
