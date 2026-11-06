#!/usr/bin/env python3
"""Bounded independent GPU source intake; no target tools or shared mutations."""
import ast,copy,datetime,hashlib,json,os,resource,signal,sys,time
from pathlib import Path
from types import ModuleType
R=Path('/home/egor/dev/pet/s24-ios-exynos'); W=Path(__file__).resolve().parents[5]
D=Path(__file__).parent; O=D/'runs'/'source2'; O.mkdir(parents=True,exist_ok=False)
G=R/'worktrees/gpu-012-admission-20261106'; C=R/'worktrees/gpu-012-current-20261106'
resource.setrlimit(resource.RLIMIT_AS,(1024*1024**2,1024*1024**2)); checks=[]; inputs={}; start=time.monotonic()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
 p=Path(p);raw=p.read_bytes();inputs[str(p)]=hashlib.sha256(raw).hexdigest();return raw
def js(p):return json.loads(read(p))
def check(name,ok,**extra):
 rss=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
 if rss>256*1024**2:raise RuntimeError('Review RSS above256MiB')
 checks.append(dict(case=name,pass_=bool(ok),**extra))
 if not ok:raise AssertionError(name)
def refuses(name,callback,phrase):
 try:callback()
 except (ValueError,OSError,KeyError,StopIteration) as e:check(name,phrase in str(e),error=str(e))
 else:check(name,False)
def module(p,name):
 m=ModuleType(name);m.__file__=str(p);exec(compile(read(p),str(p),'exec'),m.__dict__);return m
admit=[]
for i in range(3):
 row={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()) if k=='MemAvailable'}
 if row['MemAvailable']<4*1024**3:raise RuntimeError('Admission below4GiB')
 admit.append(row)
 if i<2:time.sleep(1)
report={'kind':'host-test','origin':'local-host','task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATGPU-002','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_freezes':['1f13443ed1f3a70dbf4a90199b809dfc51ae232c','372535dfe53b10b6350e7f9c2702062aac5b61c9'],'checks':checks,'inputs':inputs,'admission':admit,'compiler_sanitizer_loader_archive_guest_or_allocation':False,'prior_canonical_API_checks_reused':31}
try:
 a=module(G/'src/platform/gpu/native/userclient/admission.py','review_gpu_admission');l=module(G/'src/platform/gpu/native/userclient/launcher.py','review_gpu_launcher')
 parent=js(a.PARENT);check('Exact retained current plan hash',sha(a.PARENT)==a.PARENT_SHA)
 policy=js(G/'fixtures/public/gpu-userclient/admission-policy.json');check('Exact disabled policy hash',sha(G/'fixtures/public/gpu-userclient/admission-policy.json')==a.POLICY_SHA and policy['execution_enabled'] is False and policy['final_binding'] is None)
 for name,digest in parent['source_freeze']['files'].items():
  check('Unchanged native/portable/fixture source '+name,sha(G/name)==sha(C/name)==sha(Path(parent['source_freeze']['worktree'])/name)==digest)
 check('Exactly seven original source bodies',len(parent['source_freeze']['files'])==7)
 bind=js(G/'fixtures/public/gpu-userclient/admission-source-binding.json')
 plans={item['phase']:js(R/item['path']) for item in bind['phase_plans']}
 for item in bind['phase_plans']:check('Frozen '+item['phase']+' phase plan',sha(R/item['path'])==item['sha256'])
 for phase in ['native','host-sanitizer']:
  refuses(phase+' missing final policy refuses directly',lambda:a.accepted_interface(policy,phase),'Final accepted VM044/046')
  check(phase+' actual output remains absent',not Path(plans[phase]['output']).exists())
  check(phase+' exact retained command reconstruction',a.commands(parent,phase,Path(plans[phase]['output']))==plans[phase]['commands'])
  check(phase+' resource and no-execution flags',plans[phase]['execution_ready'] is False and plans[phase]['native_ABI_qualified'] is False and plans[phase]['hardware_result'] is False and plans[phase]['resource_contract']['max_owned_rss_bytes']==256*1024**2)
 host=copy.deepcopy(policy);host['execution_enabled']=True;host['final_binding']={'accepted':True,'resource_profile':'project-budget-v1','helper':policy['source_control_helper']}
 refuses('Actual accepted AF193 lacks RSS-only API with no fallback',lambda:a.accepted_interface(host,'host-sanitizer'),'run_child_rss_only interface; no fallback')
 refuses('Wrong phase refused',lambda:a.commands(parent,'combined',O/'absent'),'Explicit separate')
 for number,row in enumerate(plans['native']['commands']):
  selected=parent['target_commands'][number];genuine=next(r for r in parent['genuine_recipes'] if r['id']==selected['derived_from']);template=genuine['next_owned_compile_argv_template']
  changes={i for i,(x,y) in enumerate(zip(row['argv'],template)) if x!=y};expected={template.index(genuine['bound_source']),template.index('-o')+1,template.index('-MF')+1}
  check('Only source/object/dependency changes '+row['id'],len(row['argv'])==len(template) and changes==expected and row['cwd']==genuine['cwd'])
  check('Genuine flags preserve C language '+row['id'],not any(x.startswith('-std=') for x in row['argv']) if row['id']=='dispatcher' else '-target' in row['argv'])
 changed=copy.deepcopy(parent);changed['genuine_recipes'][0]['next_owned_compile_argv_template']=changed['genuine_recipes'][0]['next_owned_compile_argv_template']+['-DUNREVIEWED=1']
 refuses('Changed selected native recipe rejected',lambda:a.commands(changed,'native',O/'absent'),'Native recipe changed')
 # Safe actual launcher CLI refusal path: execute refuses inactive historical experiment
 # before all admission. Deeper disabled policy was tested directly above.
 for phase,p in plans.items():
  raw=O/(phase+'-plan.json');raw.write_text(json.dumps(p))
  refuses(phase+' actual full execute refuses historical unplanned experiment',lambda:a.execute(raw,sha(raw),O/'absent-approval'),'Original planned experiment')
  refuses(phase+' wrong serialized plan hash rejects before authority',lambda:a.execute(raw,'0'*64,O/'absent-approval'),'same-byte JSON')
 before={s:signal.getsignal(s) for s in [signal.SIGALRM,signal.SIGTERM,signal.SIGINT]};oldsignal=signal.signal
 check('Normal finite launcher restores handlers',l.guarded(lambda:19,.1)['result']==19 and before=={s:signal.getsignal(s) for s in before})
 # First cancellation exactly on restoration: wrapper intercepts only the actual
 # signal.signal call and sends a real SIGINT to this review process. Production
 # launcher bytes and handler implementation are unchanged; no fake backend.
 injected=False
 def restoration_interrupt(number,handler):
  global injected
  if number==signal.SIGALRM and handler==before[signal.SIGALRM] and not injected:
   injected=True;os.kill(os.getpid(),signal.SIGINT)
  return oldsignal(number,handler)
 signal.signal=restoration_interrupt
 escaped=None
 try:l.guarded(lambda:23,.1)
 except BaseException as error:escaped=type(error).__name__+': '+str(error)
 finally:
  left={s:signal.getsignal(s) for s in before};signal.signal=oldsignal;signal.setitimer(signal.ITIMER_REAL,0)
  for number,handler in before.items():oldsignal(number,handler)
 report['restoration_counterexample']={'injected_real_SIGINT':injected,'exception':escaped,'unrestored_handlers':[signal.Signals(s).name for s in before if left[s]!=before[s]],'review_process_handlers_repaired':before=={s:signal.getsignal(s) for s in before}}
 check('Restoration counterexample is actual and bounded',injected and escaped is not None and len(report['restoration_counterexample']['unrestored_handlers'])>0 and report['restoration_counterexample']['review_process_handlers_repaired'])
 author=js(G/'artifacts/gpu-userclient/admission-controls-2/controls.json');check('Retained author35 controls clean, reused not rerun',author['outcome']=='pass' and len(author['checks'])==35 and not author.get('watchdog_recovery'))
 report['outcome']='pass';report['review_verdict']='hold launcher restoration correction; narrow disabled source/recipe scope accepted'
except BaseException as error:
 report['outcome']='fail';report['error']=repr(error);raise
finally:
 report['elapsed_seconds']=time.monotonic()-start;report['proc_status']=[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))];report['source_sha256']=sha(__file__);report['argv']=sys.argv;report['commit']='d5c7d643e768c1e898f8d61feaa125754c3f689d'
 (O/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'outcome':report['outcome'],'checks':len(checks),'counterexample':report.get('restoration_counterexample'),'evidence':str(O/'evidence.json')}))
