#!/usr/bin/env python3
"""A declared outside-project root exits while its owned session survives."""
import importlib.util,json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
here=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('fixtures_existing',here/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
s=importlib.util.spec_from_file_location('archived_existing',Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py'));e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=Path(e.__file__)
p=f.Project();leader=None;orphan=None;report={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(e.__file__),'compiler_guest_common_started':False};started=time.monotonic()
try:
 p.b.release();p.b.state_path.unlink();pidfile=p.art/'pid';go=p.art/'go'
 code="import pathlib,subprocess,sys,time;child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(9)'],cwd='/tmp');pathlib.Path(sys.argv[1]).write_text(str(child.pid));until=time.monotonic()+5\nwhile not pathlib.Path(sys.argv[2]).exists() and time.monotonic()<until:time.sleep(.005)"
 leader=subprocess.Popen([sys.executable,'-c',code,str(pidfile),str(go)],cwd='/tmp',start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 until=time.monotonic()+2
 while not pidfile.exists() and time.monotonic()<until:time.sleep(.005)
 root=f.identity(leader.pid);orphan=f.identity(int(pidfile.read_text()))
 p.grant['existing_work']=[{'pid':root['pid'],'start_ticks':root['start_ticks'],'max_owned_rss_bytes':128*1024**2,'compiler_jobs':0,'label':'owned outside-cwd control'}]
 p.allocation.write_text(json.dumps(p.grant));p.approval['root_lease_sha256']=e.sha(p.allocation)
 p.queue.write_text(json.dumps({'heavy':{'id':p.grant['id'],'allocation_path':'artifacts/allocation.json','allocation_sha256':p.approval['root_lease_sha256'],'slots':[p.slot]}}))
 p.b=e.project_approval(p.args,p.approval,executor_path=f.__file__);p.b.reserve();before=p.b.sample()
 go.write_text('exit');leader.wait(timeout=2);time.sleep(.04)
 accepted=False;error=None;after=None
 try:after=p.b.sample();accepted=True
 except Exception as exc:error=repr(exc)
 alive=f.identity(orphan['pid']);alive=bool(alive and alive['state']!='Z' and alive['start_ticks']==orphan['start_ticks'])
 report.update(declared_root=root,orphan_identity=orphan,orphan_alive=alive,tracked_before=orphan['pid'] in {r['pid'] for r in before['project_processes']},sample_accepted_after_known_root_disappeared=accepted,tracked_after=bool(after and orphan['pid'] in {r['pid'] for r in after['project_processes']}),error=error,before=before,after=after)
 report['outcome']='pass' if not accepted else 'fail'
finally:
 if leader:f.stop_group(leader.pid,orphan);leader.wait(timeout=2)
 p.close();report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
 (here/'corrected-existing-root-control.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('before','after')}))
sys.exit(0 if report['outcome']=='pass' else 1)
