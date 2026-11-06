"""Bound the source-only namespace qualifier with the frozen accepted process API."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
BASE = ROOT / 'docs/procedures/avf-resource-namespace'
ENGINE = MAIN / 'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
ENGINE_SHA = 'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=int,required=True)
    parser.add_argument('--experiment',required=True)
    args=parser.parse_args()
    if args.attempt < 2:raise ValueError('Attempt1 is preserved; use a fresh attempt')
    if sha(ENGINE) != ENGINE_SHA:
        raise ValueError('Frozen accepted AF193 source guard changed')
    ledger = json.loads((MAIN/'state/lab.json').read_text())
    experiment = next(e for e in ledger['experiments'] if e['id']==args.experiment)
    if (experiment['task'],experiment['owner'],experiment['status']) != ('VM-045','codex-guest-resource-namespace-20261106-es','planned'):
        raise ValueError('Original-owner prospectively planned source experiment required')
    guard = BASE/('guard-session'+str(args.attempt))
    guard.mkdir(parents=True,exist_ok=False)
    engine = ModuleType('frozen_af193_resource_source_guard')
    engine.__file__ = str(ENGINE)
    data = ENGINE.read_bytes()
    if hashlib.sha256(data).hexdigest() != ENGINE_SHA:
        raise ValueError('Engine source changed during capture')
    exec(compile(data,str(ENGINE),'exec'),engine.__dict__)
    helper=ROOT/'tools/build/avf_resource_namespace.py'
    helper_sha=sha(helper)
    argv=[sys.executable,'-B','-s',str(helper),'--main',str(MAIN),'--output',str(guard/'qualification')]
    result=engine.run_child(argv,ROOT,guard,'source-qualification',engine.supervisor(MAIN),timeout=120,admit=True,budget=None)
    (guard/'process.json').write_text(json.dumps(result,indent=2)+'\n')
    if sha(helper)!=helper_sha:
        raise ValueError('Source qualifier changed while running')
    passed=result.get('outcome')=='pass' and result.get('exit_code')==0 and result.get('after',{}).get('owned_processes')==[]
    report=guard/'qualification/evidence.json'
    if passed:
        passed=json.loads(report.read_text()).get('outcome')=='pass'
    paths=[p for p in sorted(guard.rglob('*')) if p.is_file()]
    if report.is_file():paths.append(report)
    if passed:paths.append(guard/'qualification/qualified-component.json')
    record=dict(kind='host-test',origin='local-host',task='VM-045',owner='codex-guest-resource-namespace-20261106-es',
        experiment=args.experiment,recorded_at=datetime.now(timezone.utc).isoformat(),outcome='pass' if passed else 'fail',
        summary='Bounded source-only matching resource namespace derivation and actual helper/filesystem controls' if passed else 'Source qualification failed; retain exact child evidence',
        commands=[result],accepted_process=dict(path=str(ENGINE),sha256=ENGINE_SHA),
        builder=dict(path=str(helper),sha256=helper_sha),source_child_report=str(report),
        artifacts=[str(p.relative_to(MAIN))for p in paths],sha256={str(p.relative_to(MAIN)):sha(p)for p in paths},
        compiler_executed=False,generator_executed=False,archiver_executed=False,loader_executed=False,
        common_checks_executed=False,guest_executed=False,consumer_admitted=False,old_objects_reused=False)
    (BASE/('evidence-session'+str(args.attempt)+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(outcome=record['outcome'],child_exit=result.get('exit_code'),peak_total_owned_rss_bytes=result.get('peak_total_owned_rss_bytes'),owned_after=result.get('after',{}).get('owned_processes'),evidence_sha256=sha(BASE/('evidence-session'+str(args.attempt)+'.json'))),indent=2))
    return 0 if passed else 1


if __name__=='__main__':sys.exit(main())
