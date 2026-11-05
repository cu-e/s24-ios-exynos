#!/usr/bin/env python3
"""An unreaped dead registered controller cannot make a live orphan invisible."""
import copy,importlib.util,json,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
here=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('zombie_fixture',here/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
path=Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py');s=importlib.util.spec_from_file_location('zombie_policy',path);e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=path
p=f.Project();worker=None;orphan=None;start=time.monotonic();r={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(path),'compiler_guest_common_started':False}
try:
 p.b.release();p.b.state_path.unlink();worker_args={k:str(v) if isinstance(v,Path) else v for k,v in vars(p.args).items()}
 observer_slot=dict(p.slot,task='OBSERVER',owner='observer',actual_output='artifacts/observer');p.grant['slots'].append(observer_slot);p.allocation.write_text(json.dumps(p.grant));p.approval['root_lease_sha256']=e.sha(p.allocation);p.queue.write_text(json.dumps({'heavy':{'id':p.grant['id'],'allocation_path':'artifacts/allocation.json','allocation_sha256':p.approval['root_lease_sha256'],'slots':p.grant['slots']}}))
 observer_args=SimpleNamespace(**vars(p.args));observer_args.task='OBSERVER';observer_args.owner='observer';observer_args.out=p.art/'observer';observer_approval=dict(p.approval,task='OBSERVER',owner='observer')
 p.b=e.project_approval(observer_args,observer_approval,executor_path=f.__file__);p.b.reserve()
 pidfile=p.art/'orphan.pid'
 code="import importlib.util,json,pathlib,subprocess,sys,types,os;s=importlib.util.spec_from_file_location('e',sys.argv[1]);e=importlib.util.module_from_spec(s);s.loader.exec_module(e);a=json.loads(sys.argv[2]);a['main']=pathlib.Path(a['main']);a['out']=pathlib.Path(a['out']);b=e.project_approval(types.SimpleNamespace(**a),json.loads(sys.argv[3]),executor_path=sys.argv[4]);b.reserve();p=subprocess.Popen(['sleep','8'],cwd='/tmp');pathlib.Path(sys.argv[5]).write_text(str(p.pid));os._exit(0)"
 worker=subprocess.Popen([sys.executable,'-c',code,str(path),json.dumps(worker_args),json.dumps(p.approval),f.__file__,str(pidfile)],cwd='/tmp',start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 until=time.monotonic()+3;root=None
 while time.monotonic()<until:
  root=f.identity(worker.pid)
  if root and root['state']=='Z' and pidfile.exists() and pidfile.read_text():break
  time.sleep(.01)
 if not root or root['state']!='Z':raise RuntimeError('Controlled worker did not become an unreaped zombie')
 orphan=f.identity(int(pidfile.read_text()));accepted=False;error=None;snapshot=None
 try:snapshot=p.b.sample();accepted=True
 except Exception as exc:error=repr(exc)
 r.update(controller_identity=root,orphan_identity=orphan,sample_accepted=accepted,orphan_accounted=bool(snapshot and orphan['pid'] in {x['pid'] for x in snapshot['project_processes']}),error=error,snapshot=snapshot)
 r['outcome']='pass' if not accepted else 'fail'
finally:
 if worker:
  f.stop_group(worker.pid,orphan);stdout,stderr=worker.communicate(timeout=2);r.update(worker_exit=worker.returncode,worker_stdout=stdout.decode(),worker_stderr=stderr.decode())
 p.close();r.update(elapsed_seconds=time.monotonic()-start,controller_memory=e.actual_controller_memory());(here/'zombie-controller-control.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='snapshot'}))
sys.exit(0 if r['outcome']=='pass' else 1)
