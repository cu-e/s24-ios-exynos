"""Single prospectively registered source/host-only review, frozen guard."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
ENGINE=MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
DIGEST='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0'


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    record=next(e for e in json.loads((MAIN/'state/lab.json').read_text())['experiments']if e['id']=='REVRESOURCE-001')
    if(record['task'],record['owner'],record['status'])!=('REV-040','codex-review-resource-namespace-20261106-et','planned'):raise ValueError('Planned original-owner experiment required')
    if sha(ENGINE)!=DIGEST:raise ValueError('Frozen AF193 guard changed')
    guard=ModuleType('frozen_af193_review');guard.__file__=str(ENGINE)
    data=ENGINE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=DIGEST:raise ValueError('Guard capture changed')
    exec(compile(data,str(ENGINE),'exec'),guard.__dict__)
    out=BASE/'run-1';out.mkdir(exist_ok=False)
    source=BASE/'review.py';source_sha=sha(source)
    argv=[sys.executable,'-B','-s',str(source)]
    result=guard.run_child(argv,ROOT,out,'independent-source-controls',guard.supervisor(MAIN),timeout=120,admit=True,budget=None)
    (out/'process.json').write_text(json.dumps(result,indent=2)+'\n')
    success=result.get('outcome')=='pass'and result.get('exit_code')==0 and result.get('after',{}).get('owned_processes')==[] and sha(source)==source_sha
    if success:success=json.loads((out/'report.json').read_text())['outcome']=='pass'
    capsule=dict(kind='host-test',origin='local-host',recorded_at=datetime.now(timezone.utc).isoformat(),
        outcome='pass'if success else'fail',summary='Independent frozen compiler-resource namespace/source/host controls; no compilation or consumer admission',
        commands=[result],guard=dict(path=str(ENGINE),sha256=DIGEST),reviewer_source=dict(path=str(source),sha256=source_sha),
        compiler_executed=False,generator_executed=False,guest_executed=False,common_checks_executed=False)
    (out/'capsule.json').write_text(json.dumps(capsule,indent=2)+'\n')
    print(json.dumps(dict(outcome=capsule['outcome'],exit_code=result.get('exit_code'),peak=result.get('peak_total_owned_rss_bytes'),after=result.get('after',{}).get('owned_processes')),indent=2))
    return 0 if success else 1


if __name__=='__main__':sys.exit(main())
