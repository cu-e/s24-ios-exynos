#!/usr/bin/env python3
"""Compare exact frozen production delta with accepted AF193."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
OLD = MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
NEW = MAIN/'worktrees/vm-044-ep-20261106/tools/build/avf_kernel_objects.py'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()


started = time.monotonic()
report = {'kind':'source-review', 'outcome':'fail', 'argv':[sys.executable, *sys.argv], 'checks':[], 'source_commit':'a132516078cd044251f568c86982d6104257f57b', 'old_tool':str(OLD), 'new_tool':str(NEW)}


def check(name, value):
    report['checks'].append({'name':name, 'pass':bool(value)})
    if not value:raise AssertionError(name)


try:
    check('original physical AF193 unchanged', sha(OLD)=='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0')
    check('exact corrected production freeze', sha(NEW)=='fe093f7c62affab911f96b3243eef28c419ddcb8180fbd74d58fc9a7420c70df')
    before = ast.parse(OLD.read_text()); after = ast.parse(NEW.read_text())
    first = {node.name:node for node in before.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    second = {node.name:node for node in after.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    check('same production top-level function and class names', set(first)==set(second))
    changed = []
    for name in first:
        same = ast.dump(first[name])==ast.dump(second[name])
        if name in ['process_table', 'run_child']:
            check('expected changed function '+name, not same); changed.append(name)
        else:check('accepted full AST preserved '+name, same)
    check('all nonfunction production AST nodes unchanged', [ast.dump(node) for node in before.body if not isinstance(node, (ast.FunctionDef, ast.ClassDef))]==[ast.dump(node) for node in after.body if not isinstance(node, (ast.FunctionDef, ast.ClassDef))])
    budget = second['ProjectBudget']
    tx = next(node for node in budget.body if isinstance(node, ast.FunctionDef) and node.name=='transaction')
    sample = next(node for node in budget.body if isinstance(node, ast.FunctionDef) and node.name=='sample')
    check('transaction finite wait defaults to 0.5s', ast.literal_eval(tx.args.defaults[-1])==.5)
    check('sample finite wait defaults to 0.5s', ast.literal_eval(sample.args.kw_defaults[-1])==.5)
    check('fresh process scan remains inside budget snapshot', any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id=='process_table' for node in ast.walk(next(node for node in budget.body if isinstance(node, ast.FunctionDef) and node.name=='snapshot'))))
    resolver = next(node for node in second['process_table'].body if isinstance(node, ast.FunctionDef) and node.name=='resolved')
    check('resolver calls libc on actual argument', any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id=='realpath' for node in ast.walk(resolver)))
    check('resolver always frees returned allocation in finally', any(isinstance(node, ast.Try) and node.finalbody and 'free' in ast.unparse(node.finalbody[0]) for node in ast.walk(resolver)))
    report.update(outcome='pass', old_sha256=sha(OLD), new_sha256=sha(NEW), changed_functions=changed)
except Exception as error:report['error']=repr(error)
finally:
    report['elapsed_seconds']=time.monotonic()-started
    (HERE/'source-control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}|{'checks':len(report['checks'])}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
