#!/usr/bin/env python3
"""Independent exact global-allocation/caller/queue admission controls."""
import copy,importlib.util,json,os,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
here=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('admission_fixture',here/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
s=importlib.util.spec_from_file_location('admission_corrected','/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=Path(e.__file__)
start=time.monotonic();r={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','helper_sha256':e.sha(e.__file__),'controls':[],'compiler_guest_common_started':False}
def rejected(name,callback):
 try:callback()
 except (ValueError,OSError,KeyError,TypeError) as error:r['controls'].append({'name':name,'pass':True,'rejection':repr(error)})
 else:raise AssertionError('Accepted '+name)
def install(p,grant):
 p.allocation.write_text(json.dumps(grant));approval=copy.deepcopy(p.approval);approval['root_lease_sha256']=e.sha(p.allocation)
 p.queue.write_text(json.dumps({'heavy':{'id':grant['id'],'allocation_path':'artifacts/allocation.json','allocation_sha256':approval['root_lease_sha256'],'slots':grant['slots']}}));return approval
def instantiate(p,a):return e.project_approval(p.args,a,executor_path=f.__file__)
p=f.Project()
try:
 rejected('same canonical slot cannot be reserved twice',lambda:instantiate(p,p.approval).reserve())
 p.b.release();rejected('completed slot cannot be silently recycled',lambda:instantiate(p,p.approval).reserve())
 p.b.state_path.unlink()
 def slots(n):return [dict(p.slot,task=p.slot['task'] if i==0 else 'OTHER-'+str(i),owner=p.slot['owner'] if i==0 else 'owner-'+str(i),actual_output='artifacts/execute' if i==0 else 'artifacts/out-'+str(i)) for i in range(n)]
 grant=copy.deepcopy(p.grant);grant['slots']=slots(6);a=install(p,grant);six=instantiate(p,a)
 r['controls'].append({'name':'six UNIQUE serial512MiB slots fit6GiB including2GiB light','pass':len(six.allocation['slots'])==6 and six.rss_limit==512*1024**2})
 grant['slots']=slots(7);a=install(p,grant);rejected('seven UNIQUE slots rejected by GLOBAL6 job bound',lambda:instantiate(p,a))
 grant['slots']=slots(8);grant['max_compiler_jobs_total']=8;a=install(p,grant);rejected('eight slots without actual prior six measurement rejected',lambda:instantiate(p,a))
 grant=copy.deepcopy(p.grant);grant['max_compiler_jobs_total']=True;a=install(p,grant);rejected('boolean cannot replace global job count',lambda:instantiate(p,a))
 grant=copy.deepcopy(p.grant);grant['slots'][0]['max_jobs']=2;a=install(p,grant);rejected('slot cannot become two compilers',lambda:instantiate(p,a))
 grant=copy.deepcopy(p.grant);grant['light_rss_budget_bytes']=0;a=install(p,grant);rejected('global light2GiB reservation cannot be removed',lambda:instantiate(p,a))
 a=install(p,p.grant)
 wrong=copy.deepcopy(a);wrong['reviewed_executor_sha256']=e.sha(e.__file__);rejected('helper policy hash cannot replace actual component caller hash',lambda:instantiate(p,wrong))
 wrong=copy.deepcopy(a);wrong['source_plan_sha256']='0'*64;rejected('approval cannot change signed source plan',lambda:instantiate(p,wrong))
 wrong=copy.deepcopy(a);wrong['owner']='other-owner';rejected('approval cannot change original owner',lambda:instantiate(p,wrong))
 copy_path=p.art/'copied-allocation.json';copy_path.write_bytes(p.allocation.read_bytes());wrong=copy.deepcopy(a);wrong['root_lease_path']='artifacts/copied-allocation.json';rejected('copied allocation cannot create separate global broker',lambda:instantiate(p,wrong))
 wrong=copy.deepcopy(a);wrong['resource_queue_path']='artifacts/alternate-queue.json';rejected('alternate queue path cannot bypass canonical root queue',lambda:instantiate(p,wrong))
 r['outcome']='pass' if all(c['pass'] for c in r['controls']) else 'fail'
except Exception as error:r['error']=repr(error)
finally:
 p.close();r.update(elapsed_seconds=time.monotonic()-start,controller_memory=e.actual_controller_memory());(here/'admission-controls.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='controls'}|{'control_count':len(r['controls'])}))
sys.exit(0 if r['outcome']=='pass' else 1)
