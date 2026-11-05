#!/usr/bin/env python3
"""A known live old session must occupy the executor's sole command slot."""
import importlib.util,json,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
here=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('prelaunch_fixtures',here/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
s=importlib.util.spec_from_file_location('prelaunch_fixed','/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=Path(e.__file__)
p=f.Project();leader=None;orphan=None;started=time.monotonic();r={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(e.__file__),'compiler_guest_common_started':False}
try:
 pidfile=p.art/'orphan.pid';code="import pathlib,subprocess,sys;p=subprocess.Popen(['sleep','7'],cwd='/tmp');pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
 leader=subprocess.Popen([sys.executable,'-c',code,str(pidfile)],cwd=p.root,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);leader.wait(timeout=2)
 orphan=f.identity(int(pidfile.read_text()));before=p.b.sample(leader.pid)
 result=e.run_child(['sleep','.01'],p.root,p.out,'must-not-launch',e.supervisor(Path('/home/egor/dev/pet/s24-ios-exynos')),timeout=1,admit=False,budget=p.b)
 r.update(orphan_identity=orphan,command=result,tracked_before=orphan['pid'] in {p['pid'] for p in before['project_processes']})
 r['outcome']='pass' if r['tracked_before'] and result['outcome']=='resource-deferred' and result['child_started'] is False and result['admission']['previous_owned_command_still_alive'] else 'fail'
finally:
 if leader:f.stop_group(leader.pid,orphan);leader.wait(timeout=2)
 p.close();r.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory());(here/'prelaunch-control.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
sys.exit(0 if r['outcome']=='pass' else 1)
