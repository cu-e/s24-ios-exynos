#!/usr/bin/env python3
"""Read original-owner plan/authority proofs; never allocate or execute products."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

ROOT=Path('/home/egor/dev/pet/s24-ios-exynos')
HERE=Path(__file__).resolve().parent
CHECKS=[];HASHES={}

def read(p,expected=None):
    p=Path(p);raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
    if expected and h!=expected:raise ValueError('Changed frozen bytes: '+str(p))
    HASHES[str(p.relative_to(ROOT))]=h
    return raw

def require(ok,name):
    if not ok:raise ValueError(name)
    CHECKS.append(name)

def main():
    p=argparse.ArgumentParser();p.add_argument('--firehose',required=True,type=Path);p.add_argument('--pthread',required=True,type=Path);a=p.parse_args()
    out=HERE/'runs/original-plans1';out.mkdir(parents=True,exist_ok=False)
    samples=[]
    for n in range(3):
        m=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        require(m>=4*1024**3,'stable4GiB-'+str(n));samples.append(m)
        if n<2:time.sleep(1)
    start=time.monotonic()
    ledger=json.loads((ROOT/'state/lab.json').read_bytes())
    adapter=ROOT/'worktrees/vm-036-dz-af193-20261106/tools/build/avf_guest_components.py'
    read(adapter,'e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa')
    policy=json.loads(read(adapter.parents[2]/'fixtures/public/avf-guest-components/policy.json','748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348'))
    acceptance=json.loads(read(ROOT/'artifacts/team-coordination/20261106-team/components-root-acceptance.json','39103617435178361af6c2c4b7a989a1630b3da5fb91b7e23b0e39bb4d49f36b'))
    require(acceptance['fresh_original_owner_source_plans_allowed'] is True and acceptance['actual_component_compile_granted'] is False,'actual root acceptance allows planning, grants no compiler')
    launcher=ROOT/'artifacts/team-coordination/20261106-team/in-process-component-launcher-e62d7592-600.py'
    read(launcher,'abb67ea94a25dfb1da7ff1a49c1c65162516b082408bf72918875b3531cfe872')
    launcher_provenance=json.loads(read(ROOT/'artifacts/team-coordination/20261106-team/component-launcher-e62d7592-provenance.json'))
    require(launcher_provenance['adapter_sha256']==acceptance['adapter_sha256'] and launcher_provenance['whole_timeout_seconds']==600 and launcher_provenance['actual_compile_authorized'] is False,'exact root launcher metadata, no compile grant')
    items=[]
    for kind,path,exp,expected in [('firehose',a.firehose,'AVFFH-002','5221e312a27f3a73eb808148c19f8b05ad9a3d06ad747096dca59f976b3bbd7b'),('pthread',a.pthread,'AVFPTH-004','288b255bfb5d38798a6889a7569596e5f04401752f3230e60c470017cbaa94bc')]:
        raw=read(path,expected);plan=json.loads(raw);c=policy['components'][kind]
        task=next(t for t in ledger['tasks'] if t['id']==c['task']);experiment=next(e for e in ledger['experiments'] if e['id']==exp)
        require(task['owner']==c['owner'] and task['status']=='in_progress' and task['worktree']==c['worktree'],'original active owner/worktree '+kind)
        require(all(experiment[k]==v for k,v in [('task',c['task']),('owner',c['owner']),('status','planned')]),'new actual experiment stays planned '+kind)
        require(path.is_relative_to(ROOT/c['worktree']) and not any(x.is_symlink() for x in [path,*path.parents]),'original nonsymlink source-plan scope '+kind)
        require(plan['owner']==c['owner'] and plan['task']==c['task'] and plan['executor_sha256']==acceptance['adapter_sha256'] and plan['policy_sha256']==acceptance['policy_sha256'] and plan['process_policy']==policy['prospective_process'],'exact accepted adapter/policy/process/original identity '+kind)
        require(plan['resource_profile']=='project-budget-v1' and plan['qualification']=='source-plan-only' and plan['compiled'] is False,'source-only planned profile '+kind)
        unit=json.loads(read(ROOT/policy['pins'][kind+'_unit']['path'],policy['pins'][kind+'_unit']['sha256']))
        require(len(plan['commands'])==4 and [x['argv'] for x in plan['commands']]==[x['argv'] for x in unit['commands']] and [x['cwd'] for x in plan['commands']]==[x['cwd'] for x in unit['commands']],'four immutable historical argv and cwd '+kind)
        source_inputs=read(path.parent/'input-bindings.json');old_inputs=read(ROOT/'worktrees/vm-036-dz-af193-20261106/artifacts/avf-guest-components/af193-plans-001'/kind/'input-bindings.json')
        require(source_inputs==old_inputs,'accepted complete input-binding bytes reused '+kind)
        execution=Path(plan['output']);owned=ROOT/c['worktree'];allowed=[owned/'artifacts'/c['scope'],owned/'docs/procedures'/c['scope']]
        require(not execution.exists() and not any(x.is_symlink() for x in [execution,*execution.parents]) and any(execution.is_relative_to(x) and execution!=x for x in allowed),'fresh original canonical execution output '+kind)
        filelist=Path(plan['commands'][-1]['filelist']);read(filelist,plan['commands'][-1]['filelist_sha256'])
        future=['/usr/bin/python3','-B','-s',str(launcher),str(adapter),'--mode','execute','--main',str(ROOT),'--component',kind,'--task',c['task'],'--owner',c['owner'],'--experiment',exp,'--out',str(execution),'--approval','@ROOT_APPROVAL@','--approval-sha256','@ROOT_APPROVAL_SHA256@']
        items.append({'component':kind,'task':c['task'],'owner':c['owner'],'experiment':exp,'experiment_status':'planned','experiment_timeout_seconds':experiment.get('timeout_seconds'),'plan':str(path.relative_to(ROOT)),'plan_sha256':expected,'canonical_plan_sha256':hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'input_bindings_sha256':hashlib.sha256(source_inputs).hexdigest(),'execution_output':str(execution),'future_execute_argv_template_NOT_AUTHORIZED':future,'required_controller_plus_tree_rss_bytes':256*1024**2,'max_jobs':1,'whole_timeout_seconds':600,'child_timeout_seconds':120,'archive':plan['commands'][-1]['archive'],'archive_members':plan['commands'][-1]['members']})
    report={'kind':'host-test','origin':'local-host','outcome':'pass','recorded_at':datetime.now(timezone.utc).isoformat(),'task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATCOMPPLAN-001','summary':'Both original-owner exact finalAF193 derivedplans and newplanned actualexperiments qualify for root serialallocation intake; no execution granted.','components':items,'checks':CHECKS,'admission_MemAvailable_bytes':samples,'elapsed_seconds':time.monotonic()-start,'proc_status':[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))],'artifacts':list(HASHES),'artifact_sha256':HASHES,'control_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'actual_component_compile_or_broker_granted':False,'original_task_or_experiment_mutated':False,'physical_source_matrix_repeated':False}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'checks':len(CHECKS),'components':items,'evidence_sha256':hashlib.sha256((out/'evidence.json').read_bytes()).hexdigest(),'current_image_memory':report['proc_status']}))

if __name__=='__main__':main()
