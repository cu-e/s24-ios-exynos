#!/usr/bin/env python3
"""Own a tiny child while a separate real process holds the broker lock."""
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('budget_controls',HERE/'focused-controls.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
spec=importlib.util.spec_from_file_location('archived_budget',HERE/'original-helper-39f68b5.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
f.e=e;f.TOOL=Path(e.__file__)
report={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(e.__file__),'argv':[sys.executable,*sys.argv],'compiler_guest_common_started':False}
p=f.Project();holder=None;started=time.monotonic()
try:
 ready=p.out/'ready';lockproof=p.out/'lock-proof.json'
 code="import fcntl,json,os,pathlib,sys,time;ready=pathlib.Path(sys.argv[1]);deadline=time.monotonic()+5\nwhile not ready.exists() and time.monotonic()<deadline:time.sleep(.002)\nif not ready.exists():sys.exit(3)\nchild=int(ready.read_text());handle=open(sys.argv[2],'a+');fcntl.flock(handle,fcntl.LOCK_EX);start=time.monotonic();time.sleep(.8)\ntry:os.kill(child,0);alive=True\nexcept ProcessLookupError:alive=False\npathlib.Path(sys.argv[3]).write_text(json.dumps({'lock_started':start,'sampled_after_lock_seconds':time.monotonic()-start,'child_alive':alive}));time.sleep(.7)"
 holder=subprocess.Popen([sys.executable,'-c',code,str(ready),str(p.b.lock_path),str(lockproof)],cwd=p.root,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 child_code="import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(8)"
 supervise=e.supervisor(Path('/home/egor/dev/pet/s24-ios-exynos'))
 result=e.run_child([sys.executable,'-c',child_code,str(ready)],p.root,p.out,'lock-deadline',supervise,timeout=.15,admit=False,budget=p.b)
 stdout,stderr=holder.communicate(timeout=3)
 proof=json.loads(lockproof.read_text())
 report.update(requested_child_deadline_seconds=.15,holder_exit=holder.returncode,holder_stdout=stdout.decode(),holder_stderr=stderr.decode(),lock_observation=proof,command=result)
 report['outcome']='pass' if not proof['child_alive'] else 'fail'
finally:
 if holder and holder.poll() is None:f.stop_group(holder.pid,f.identity(holder.pid));holder.communicate(timeout=2)
 p.close();report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
 (HERE/'initial-lock-control.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='command'}))
sys.exit(0 if report['outcome']=='pass' else 1)
