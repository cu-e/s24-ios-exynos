"""Single registered borrowed parser review under immutable BFA8 monitor."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
ENGINE=MAIN/'worktrees/vm-044-ep-fix5-20261106/tools/build/avf_kernel_objects.py'
PIN='bfa8a7ddc2d0d9fa42158c24d9d3906a26348666e82b2fcae181e72763911dc3'


def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    exp=next(x for x in json.loads((MAIN/'state/lab.json').read_text())['experiments']if x['id']=='REV047FD-001')
    if(exp['task'],exp['owner'],exp['status'])!=('REV-047','codex-review-runtime-linkmap-20261106-fd','planned'):raise ValueError('Original planned experiment required')
    if sha(ENGINE)!=PIN:raise ValueError('Immutable guard changed')
    b=ENGINE.read_bytes()
    if hashlib.sha256(b).hexdigest()!=PIN:raise ValueError('Guard capture changed')
    guard=ModuleType('accepted_guard');guard.__file__=str(ENGINE);exec(compile(b,str(ENGINE),'exec'),guard.__dict__)
    out=BASE/'run-1';out.mkdir(exist_ok=False);source=BASE/'review.py';h=sha(source)
    result=guard.run_child([sys.executable,'-B','-s',str(source)],ROOT,out,'independent-runtime-map',guard.supervisor(MAIN),timeout=120,admit=True,budget=None)
    (out/'process.json').write_text(json.dumps(result,indent=2)+'\n')
    passed=result.get('outcome')=='pass'and result.get('exit_code')==0 and result.get('after',{}).get('owned_processes')==[]and sha(source)==h
    if passed:passed=json.loads((out/'report.json').read_text())['outcome']=='pass'
    record=dict(kind='host-test',origin='local-host',recorded_at=datetime.now(timezone.utc).isoformat(),outcome='pass'if passed else'fail',summary='Independent runtime-map/source/archive/CU9f80 borrowed parser controls; synthetic facts receive zero actual selection credit',commands=[result],guard=dict(path=str(ENGINE),sha256=PIN),reviewer_source=dict(path=str(source),sha256=h),compiler_started=False,actual_allocation_granted=False,common_checks_executed=False)
    (out/'capsule.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(outcome=record['outcome'],exit_code=result.get('exit_code'),peak=result.get('peak_total_owned_rss_bytes'),after=result.get('after',{}).get('owned_processes')),indent=2));return 0 if passed else 1


if __name__=='__main__':sys.exit(main())
