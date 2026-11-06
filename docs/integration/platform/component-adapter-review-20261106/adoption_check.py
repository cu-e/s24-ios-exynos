#!/usr/bin/env python3
"""Review the narrow final policy change, with no reservation or component run."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from types import ModuleType, SimpleNamespace

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
NEW=MAIN/'worktrees/vm-036-dz-af193-20261106'
OLD=MAIN/'worktrees/vm-036-dz-fix2-20261106'
HERE=Path(__file__).resolve().parent
OUT=HERE/'runs/adoption1'
EXPECTED='e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa'
CHECKS=[];FILES={}

def read(p,expected=None):
    data=p.read_bytes();s=hashlib.sha256(data).hexdigest()
    if expected and s!=expected:raise ValueError('Frozen input changed: '+str(p))
    FILES[str(p.relative_to(MAIN))]=s
    return data

def check(ok,name):
    if not ok:raise AssertionError(name)
    CHECKS.append({'name':name,'outcome':'pass'})

def reject(fn,message,name):
    try:fn()
    except ValueError as error:
        check(message in str(error),name)
        CHECKS[-1]['actual_rejection']=str(error)
        return
    raise AssertionError('Unexpected admission: '+name)

def funcs(data):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(data).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}

def main():
    OUT.mkdir(parents=True,exist_ok=False);samples=[]
    for n in range(3):
        available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        check(available>=4*1024**3,'stable4GiB-'+str(n));samples.append(available)
        if n<2:time.sleep(1)
    start=time.monotonic()
    raw=read(NEW/'tools/build/avf_guest_components.py',EXPECTED)
    old=read(OLD/'tools/build/avf_guest_components.py','3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f')
    m=ModuleType('independent_adoption');m.__file__=str(NEW/'tools/build/avf_guest_components.py')
    exec(compile(raw,m.__file__,'exec'),m.__dict__)
    policy=json.loads(read(m.POLICY,'748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348'))
    prior=json.loads(read(OLD/'fixtures/public/avf-guest-components/policy.json'))
    oldf,newf=funcs(old),funcs(raw)
    check(set(oldf)==set(newf) and [n for n in oldf if oldf[n]!=newf[n]]==['prepare'],'all old authority/product/runtime/resource functions unchanged except added prepare receipt binding')
    required=['process_root_acceptance','process_publication','process_source_review','adapter_source_review']
    check({k:policy['pins'][k] for k in prior['pins']}==prior['pins'],'all historical recipe/tool/namespace pins unchanged')
    check(set(policy['pins'])-set(prior['pins'])==set(required),'only four accepted receipt pins added')
    check({k:v for k,v in policy.items() if k not in ['pins','prospective_process']}=={k:v for k,v in prior.items() if k not in ['pins','prospective_process']},'all original component owners/scopes/tool digests unchanged')
    process=policy['prospective_process']
    check(process['path']=='worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py' and process['sha256']=='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0' and process['independently_accepted'] is True,'exact once-only accepted AF193 process')
    engine_bytes=read(MAIN/process['path'],process['sha256'])
    engine=m.module(MAIN/process['path'],process['sha256'],'independent_final_engine')
    for name in required:read(MAIN/policy['pins'][name]['path'],policy['pins'][name]['sha256'])
    marker=json.loads(read(MAIN/policy['pins']['process_root_acceptance']['path']))
    check(marker['published_head']==process['published_head']=='75fe3857c443c7e631bbd8cf838f7e48cc315844' and marker['common_tests']==170 and marker['common_exit']==0 and marker['owned_after']==[] and marker['lease_released'] is True,'actual root acceptance binds published common and cleanup')
    for kind,pin in [('firehose','5221e312a27f3a73eb808148c19f8b05ad9a3d06ad747096dca59f976b3bbd7b'),('pthread','288b255bfb5d38798a6889a7569596e5f04401752f3230e60c470017cbaa94bc')]:
        folder=NEW/'artifacts/avf-guest-components/af193-plans-001'/kind
        p=json.loads(read(folder/'execution-plan.json',pin))
        historical=json.loads(read(MAIN/policy['pins'][kind+'_unit']['path'],policy['pins'][kind+'_unit']['sha256']))
        check(p['executor_sha256']==EXPECTED and p['policy_sha256']==m.POLICY_SHA256 and p['process_policy']==process and p['compiled'] is False,'actual new '+kind+' plan binds final code and policy, not products')
        check([c['argv'] for c in p['commands']]==[c['argv'] for c in historical['commands']] and [c['cwd'] for c in p['commands']]==[c['cwd'] for c in historical['commands']],'actual '+kind+' commands and CWDs unchanged')
        previous=MAIN/'worktrees/vm-036-dz-20261106/artifacts/avf-guest-components/plans-001'/kind/'input-bindings.json'
        check(read(folder/'input-bindings.json')==read(previous),'complete '+kind+' namespace binding bytes unchanged, physical matrix not repeated')
    # This real API call intentionally uses the actual old reviewed adapter SHA.
    # It must reject before reading an absent negative lease, constructing a
    # broker, reserving any slot or touching an original-owner output.
    args=SimpleNamespace(main=MAIN,task='INT-003',owner='codex-integrator-platform-20261106-cn',experiment='PLATCOMP-003',shard='firehose',out=OUT/'never-output')
    approval={'schema':'project-budget-v1','reviewed_executor_sha256':'3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f','runner_reviewed':True,'root_lease':'negative-only-never-allocated','root_lease_path':'artifacts/negative-adoption-review-no-lease.json','root_lease_sha256':'0'*64,'resource_queue_path':'artifacts/team-coordination/20261106-team/resource-queue.json','max_jobs_per_executor':1,'task':args.task,'owner':args.owner,'experiment':args.experiment,'shard':args.shard,'source_plan_sha256':'0'*64,'qemu_allowed':False}
    reject(lambda:engine.project_approval(args,approval,executor_path=Path(m.__file__)),'Approval must bind exact reviewed serial executor','actual old adapter authority cannot approve final new caller before any allocation')
    reject(lambda:m.module(MAIN/process['path'],'42f84aff5febfe4800cb0f84f4052bc98ac539766f8d4ecd7739a63d2fb7dd0d','negative_old_engine'),'Changed pinned Python boundary','quarantined old process digest cannot load final physical engine')
    wrong=OUT/'modified-root-receipt.json';wrong.write_bytes(read(MAIN/policy['pins']['process_root_acceptance']['path'])+b'\n')
    changed=json.loads(json.dumps(policy));changed['pins']['process_root_acceptance']['path']=str(wrong)
    reject(lambda:m.pinned(changed,MAIN,'process_root_acceptance'),'Changed frozen process_root_acceptance','real changed accepted receipt rejected')
    check(not args.out.exists(),'no component output or allocation created')
    check(read(NEW/'tools/build/avf_guest_components.py',EXPECTED)==raw,'frozen adapter source remains unchanged')
    r={'kind':'host-test','origin':'local-host','task':'INT-003','owner':args.owner,'experiment':args.experiment,'outcome':'pass','recorded_at':datetime.now(timezone.utc).isoformat(),'summary':'Final AF193 component policy adoption source/plan receipt review and actual stale-authority rejection pass; no component execution.',
       'source_commit':'c931581ef7cb0bb2dc9e0874c98226443b2d1113','adapter_sha256':EXPECTED,'policy_sha256':m.POLICY_SHA256,'checks':CHECKS,'admission_MemAvailable_bytes':samples,'elapsed_seconds':time.monotonic()-start,'proc_status':[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))],
       'artifacts':list(FILES),'artifact_sha256':FILES,'control_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'compiler_archiver_loader_guest_executed':False,'actual_budget_reserved':False,'original_owner_output_written':False,'namespace_matrix_repeated':False}
    (OUT/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'checks':len(CHECKS),'files':len(FILES),'proc_status':r['proc_status'],'elapsed_seconds':r['elapsed_seconds'],'evidence_sha256':hashlib.sha256((OUT/'evidence.json').read_bytes()).hexdigest()}))

if __name__=='__main__':main()
