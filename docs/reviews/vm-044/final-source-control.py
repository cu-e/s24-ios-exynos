#!/usr/bin/env python3
"""Bind final helper and prove unchanged guard/class/legacy code."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent;MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
paths={
 'AF193':('vm-039-ej-20261106','af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0'),
 'FE093':('vm-044-ep-20261106','fe093f7c62affab911f96b3243eef28c419ddcb8180fbd74d58fc9a7420c70df'),
 '2bb':('vm-044-ep-fix1-20261106','2bb96f520791fb5dd5e05090fcffeabccc1a9e2d9e37dd0911221dce494a4f83'),
 'e97':('vm-044-ep-fix2-20261106','e97a5c9e6edf4daae4924bafb9f50f9bbacf90f1257012da54401feebdb2f4f6'),
 'f2023':('vm-044-ep-fix4-20261106','f2023bd02bab4400e6a4ca19033c5b78baeb8b57485258afeda9e46891585796'),
 'bfa8':('vm-044-ep-fix5-20261106','bfa8a7ddc2d0d9fa42158c24d9d3906a26348666e82b2fcae181e72763911dc3')}
report={'kind':'source-review','outcome':'fail','argv':[sys.executable,*sys.argv],'checks':[],'sources':[]};started=time.monotonic()


def check(name,value):
    report['checks'].append({'name':name,'pass':bool(value)})
    if not value:raise AssertionError(name)


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def functions(tree):return {node.name:node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}


try:
    trees={}
    for name,(worktree,expected) in paths.items():
        path=MAIN/'worktrees'/worktree/'tools/build/avf_kernel_objects.py';actual=digest(path)
        check('exact preserved physical helper '+name,actual==expected);report['sources'].append({'name':name,'path':str(path),'sha256':actual});trees[name]=ast.parse(path.read_text())
    before=functions(trees['e97']);after=functions(trees['bfa8']);poll=functions(trees['f2023'])
    check('only bounded helper added',set(after)==set(before)|{'bounded_flock'})
    for name,node in before.items():
        if name!='ProjectBudget':check('e97 full AST preserved '+name,ast.dump(node)==ast.dump(after[name]))
    members=lambda node:{n.name:n for n in node.body if isinstance(n,ast.FunctionDef)}
    old_members=members(before['ProjectBudget']);new_members=members(after['ProjectBudget'])
    check('same ProjectBudget method set',set(old_members)==set(new_members))
    for name,node in old_members.items():
        if name!='transaction':check('full budget method preserved '+name,ast.dump(node)==ast.dump(new_members[name]))
    old_tx=copy.deepcopy(old_members['transaction']);new_tx=copy.deepcopy(new_members['transaction'])
    old_with=next(n for n in old_tx.body if isinstance(n,ast.With));new_with=next(n for n in new_tx.body if isinstance(n,ast.With))
    check('transaction pre-lock canonical/open statements preserved',[ast.dump(n) for n in old_tx.body if not isinstance(n,ast.With)]==[ast.dump(n) for n in new_tx.body if not isinstance(n,ast.With)])
    check('same lock descriptor context',ast.dump(old_with.items[0])==ast.dump(new_with.items[0]))
    check('all acquired-lock live/inode/state/operation/atomic-write checks preserved',[ast.dump(n) for n in old_with.body[2:]]==[ast.dump(n) for n in new_with.body[1:]])
    call=new_with.body[0].value
    check('one operative bounded helper call with original lock and timeout',isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='bounded_flock' and [ast.unparse(n) for n in call.args]==['lock','lock_timeout'])
    check('finite transaction default unchanged',ast.literal_eval(new_tx.args.defaults[-1])==.5)
    check('sample preserves finite default',ast.literal_eval(new_members['sample'].args.kw_defaults[-1])==.5)
    fixed=copy.deepcopy(after['bounded_flock']);original=poll['bounded_flock'];final_try=next(n for n in fixed.body if isinstance(n,ast.Try))
    mask=final_try.finalbody[0].value.args[1]
    check('restoration masks exactly ALRM TERM INT',isinstance(mask,ast.Set) and {ast.unparse(n) for n in mask.elts}=={'signal.SIGALRM','signal.SIGTERM','signal.SIGINT'})
    mask.elts=[next(n for n in mask.elts if ast.unparse(n)=='signal.SIGALRM')]
    check('only restoration mask differs from actually timed f2023 helper',ast.dump(fixed)==ast.dump(original))
    af=functions(trees['AF193'])
    for name in ['bind','accepted_profile','firehose_profile','load_project','project_approval','approval','owned_out','task_shards','resume_profile','reusable','Digests','macho','dependencies','landlock','namespace']:
        check('accepted AF193 legacy/profile/byte/scope guard unchanged '+name,ast.dump(af[name])==ast.dump(after[name]))
    old_non=[ast.dump(n) for n in trees['e97'].body if not isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Import))]
    new_non=[ast.dump(n) for n in trees['bfa8'].body if not isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Import))]
    check('all prior constants/other module AST unchanged',old_non==new_non)
    report['outcome']='pass'
except Exception as error:report['error']=repr(error)
finally:
    report['elapsed_seconds']=time.monotonic()-started;(HERE/'final-source-control.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['checks','sources']}|{'check_count':len(report['checks'])}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
