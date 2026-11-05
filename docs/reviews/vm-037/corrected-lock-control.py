#!/usr/bin/env python3
"""Corrected live-child deadline under a detached, bounded broker-lock holder."""
import importlib.util,json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('fixtures_lock_fix',HERE/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
s=importlib.util.spec_from_file_location('budget_lock_fix','/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=Path(e.__file__)
p=f.Project();holder_pid=None;holder_identity=None;started=time.monotonic();report={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(e.__file__),'argv':[sys.executable,*sys.argv],'compiler_guest_common_started':False}
try:
 ready=p.out/'ready';lockproof=p.out/'proof.json';pidfile=p.out/'holder.pid'
 code="import fcntl,json,os,pathlib,sys,time\nif os.fork():sys.exit(0)\nos.setsid();pathlib.Path(sys.argv[4]).write_text(str(os.getpid()));ready=pathlib.Path(sys.argv[1]);deadline=time.monotonic()+5\nwhile not ready.exists() and time.monotonic()<deadline:time.sleep(.002)\nif not ready.exists():sys.exit(3)\nchild=int(ready.read_text());handle=open(sys.argv[2],'a+');fcntl.flock(handle,fcntl.LOCK_EX);start=time.monotonic();time.sleep(.8)\ntry:os.kill(child,0);alive=True\nexcept ProcessLookupError:alive=False\npathlib.Path(sys.argv[3]).write_text(json.dumps({'lock_started':start,'sampled_after_lock_seconds':time.monotonic()-start,'child_alive':alive}));time.sleep(.7)"
 launcher=subprocess.Popen([sys.executable,'-c',code,str(ready),str(p.b.lock_path),str(lockproof),str(pidfile)],cwd=p.root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);launcher.wait(timeout=2)
 until=time.monotonic()+2
 while (not pidfile.exists() or not pidfile.read_text()) and time.monotonic()<until:time.sleep(.005)
 holder_pid=int(pidfile.read_text());holder_identity=f.identity(holder_pid)
 child="import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(8)"
 result=e.run_child([sys.executable,'-c',child,str(ready)],p.root,p.out,'bounded-lock',e.supervisor(Path('/home/egor/dev/pet/s24-ios-exynos')),timeout=.15,admit=False,budget=p.b)
 until=time.monotonic()+3
 while (not lockproof.exists() or any(r['session']==holder_pid and r['state']!='Z' for r in e.process_table().values())) and time.monotonic()<until:time.sleep(.02)
 proof=json.loads(lockproof.read_text());report.update(command=result,lock_observation=proof,holder_identity=holder_identity)
 report['outcome']='pass' if not proof['child_alive'] and result['child_started'] and not result['after']['owned_processes'] and result.get('project_budget_error') else 'fail'
finally:
 if holder_pid:f.stop_group(holder_pid,holder_identity)
 p.close();report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
 (HERE/'corrected-lock-control.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='command'}))
sys.exit(0 if report['outcome']=='pass' else 1)
