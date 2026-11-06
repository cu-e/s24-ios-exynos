"""Run the frozen accepted adapter's source-plan CLI through its accepted process boundary."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
BASE=ROOT/'docs/procedures/avf-guest-firehose'
OUT=BASE/'accepted-adapter-plan-session1'
ADAPTER=MAIN/'worktrees/vm-036-dz-af193-20261106/tools/build/avf_guest_components.py'
POLICY=MAIN/'worktrees/vm-036-dz-af193-20261106/fixtures/public/avf-guest-components/policy.json'
ENGINE=MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
PINS={str(ADAPTER):'e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa',
      str(POLICY):'748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348',
      str(ENGINE):'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0',
      str(BASE/'bounded-plan-session1/plan.json'):'1243849185135bb9ab7f861faf4d8fe2fed0c9dcae1e57165a2e9ff7a86008dc',
      str(BASE/'preparation-session3/compile-plan.json'):'f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def bound(path):
    return dict(path=str(path),sha256=sha(path),size_bytes=Path(path).stat().st_size)


def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    for path,expected in PINS.items():
        if sha(path)!=expected:raise ValueError('Accepted frozen input changed: '+path)
    unit=json.loads((BASE/'bounded-plan-session1/plan.json').read_text())
    filelist=Path(unit['commands'][3]['filelist']['path'])
    if sha(filelist)!=unit['commands'][3]['filelist']['sha256']:raise ValueError('Original provider-only filelist changed')
    old={**PINS,str(filelist):sha(filelist)}
    target=Path(unit['owned_output_directory'])
    if os.path.lexists(target):raise ValueError('Future component output must remain absent during source planning')
    ledger=json.loads((MAIN/'state/lab.json').read_text())
    exp=next(e for e in ledger['experiments'] if e['id']=='AVFFH-002')
    if (exp['task'],exp['owner'],exp['status'])!=('VM-020','codex-guest-exec-20261106-cx','planned'):
        raise ValueError('Original owner actual experiment must remain planned')
    OUT.mkdir(parents=True,exist_ok=False)
    engine=ModuleType('accepted_af193_source_guard');engine.__file__=str(ENGINE)
    data=ENGINE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=PINS[str(ENGINE)]:raise ValueError('Engine source changed during capture')
    exec(compile(data,str(ENGINE),'exec'),engine.__dict__)
    supervise=engine.supervisor(MAIN)
    argv=[sys.executable,'-B','-s',str(ADAPTER),'--mode','plan','--main',str(MAIN),
          '--component','firehose','--task','VM-020','--owner','codex-guest-exec-20261106-cx',
          '--experiment','AVFFH-002','--out',str(OUT/'plan')]
    record=engine.run_child(argv,ROOT,OUT,'source-plan',supervise,timeout=120,admit=True,budget=None)
    dump(OUT/'guard-record.json',record)
    success=record.get('outcome')=='pass' and record.get('exit_code')==0
    if any(p.get('state')!='Z' for p in record.get('after',{}).get('owned_processes',[])):
        raise ValueError('Source-plan child survived cleanup')
    for path,expected in old.items():
        if sha(path)!=expected:raise ValueError('Preserved frozen input changed after source planning: '+path)
    if os.path.lexists(target):raise ValueError('Source plan materialized future component execution directory')
    artifact_paths=[OUT/'guard-record.json',OUT/'source-plan.stdout.txt',OUT/'source-plan.stderr.txt',OUT/'source-plan.samples.jsonl']
    planned=None
    if success:
        planned=json.loads((OUT/'plan/execution-plan.json').read_text())
        if planned.get('compiled') is not False or planned.get('executor_sha256')!=PINS[str(ADAPTER)] or planned.get('policy_sha256')!=PINS[str(POLICY)] or planned['process_policy']['path']!='worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py' or planned['process_policy']['sha256']!=PINS[str(ENGINE)]:
            raise ValueError('Derived plan did not bind exact accepted adapter/process or source-only state')
        artifact_paths.extend([OUT/'plan/execution-plan.json',OUT/'plan/input-bindings.json'])
    execute=[sys.executable,'-B','-s',str(ADAPTER),'--mode','execute','--main',str(MAIN),
             '--component','firehose','--task','VM-020','--owner','codex-guest-exec-20261106-cx',
             '--experiment','AVFFH-002','--out',str(target),'--approval','@ROOT_APPROVAL_PATH@',
             '--approval-sha256','@ROOT_APPROVAL_SHA256@']
    receipt=dict(kind='host-test',origin='local-host',task='VM-020',owner='codex-guest-exec-20261106-cx',
        recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        outcome='pass' if success else 'inconclusive',
        summary='Original-owner source plan derived through exact root-accepted adapter/AF193 process; no component commands executed' if success else 'Source-plan child failed or was resource-deferred; no component execution granted',
        builder=bound(__file__),argv=sys.orig_argv,experiment=dict(id='AVFFH-002',status='planned',recorded_as_actual_build_result=False),
        root_acceptance=bound(MAIN/'artifacts/team-coordination/20261106-team/components-root-acceptance.json'),
        accepted_adapter=bound(ADAPTER),accepted_policy=bound(POLICY),accepted_process=bound(ENGINE),
        commands=[record],preserved_inputs=[dict(path=p,sha256=h) for p,h in old.items()],
        artifacts=[str(p.relative_to(MAIN)) for p in artifact_paths if p.exists()],
        sha256={str(p.relative_to(MAIN)):sha(p) for p in artifact_paths if p.is_file()},
        new_plan=bound(OUT/'plan/execution-plan.json') if success else None,
        new_input_bindings=bound(OUT/'plan/input-bindings.json') if success else None,
        future_execute_argv_template=execute,approval_template_is_authorization=False,
        proposed_product_directory=str(target),proposed_product_names=['provider.o','provider-layout.o','interface.o','libfirehose_kernel.a'],
        future_product_directory_still_absent=True,compiler_executed=False,archiver_executed=False,
        loader_executed=False,qemu_executed=False,common_checks_executed=False,
        project_budget_or_execution_approval_supplied=False,budget044_repinned=False,
        limitations=['Actualbuild experiment remains planned for future owner_authority checks',
                    'Root must bind final plan/approval/broker lease and one serial compiler after both component plan intakes',
                    'Source plan is not a measured ABI/provider/archive or runtime component result'])
    dump(OUT/'evidence.json',receipt)
    print(json.dumps(dict(outcome=receipt['outcome'],guard_exit=record.get('exit_code'),new_plan=receipt['new_plan'],
        peak_total_owned_rss_bytes=record.get('peak_total_owned_rss_bytes'),owned_after=record.get('after',{}).get('owned_processes',[])),indent=2))
    return 0 if success else 1


if __name__=='__main__':sys.exit(main())
