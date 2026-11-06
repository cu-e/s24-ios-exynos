#!/usr/bin/env python3
"""Correct only the mocked closure boundary; rerun two resume gate cases."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
RAW=MAIN/'worktrees/vm-014-profile-v1-20261106/artifacts/avf-object-shards/libkern/profile-v1/build-001'
NEW=MAIN/'worktrees/vm-044-ep-fix2-20261106/tools/build/avf_kernel_objects.py'
RUNTIME=HERE/'runtime'/'focused-gate';RUNTIME.mkdir()
report={'kind':'host-test','outcome':'fail','argv':[sys.executable,*sys.argv],'orchestration_cases':[],'limitation':'Original focused-control mocked accepted_profile returned {}, causing unrelated KeyError after loop. Original result and all process controls preserved. This run corrects only that test boundary, uses genuine old bytes, and reruns no real child or timing control. Namespace and ledger remain mocked, no fresh compilation or namespace qualification.'}
started=time.monotonic()


def module(path):
    spec=importlib.util.spec_from_file_location('resume_gate_subject',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


e=module(NEW)
try:
    original=(HERE/'focused-control.py').read_text();tree=ast.parse(original)
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='orchestration')
    code=ast.get_source_segment(original,function)
    before="'accepted_profile':lambda args:{}";after="'accepted_profile':lambda args:{'manifest_sha256':'a'*64}"
    if code.count(before)!=1:raise ValueError('Exact fixture correction seam changed')
    code=code.replace(before,after)
    before="summary={'label':label";after="summary={'error':result.get('error'),'label':label"
    if code.count(before)!=1:raise ValueError('Exact report correction seam changed')
    code=code.replace(before,after)
    (RUNTIME/'corrected-orchestration.py').write_text(code+'\n')
    exec(compile(code,str(RUNTIME/'corrected-orchestration.py'),'exec'),globals())
    for scenario in ['resume','resume-single']:
        result=orchestration(NEW,scenario,scenario)
        if result['error'] is not None or result['dispatch_calls'] or result['popen_attempts'] or result['compiler_started'] or result['resource_qualification']!='inconclusive' or result['outcome']!='fail' or result['object_outcomes']!=['pass']:
            raise AssertionError('Unqualified genuine-byte resume must fail only the resource/count gate and never dispatch')
    report['outcome']='pass'
except Exception as error:report['error']=repr(error)
finally:
    report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
    (HERE/'focused-gate-control.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='orchestration_cases'}|{'case_count':len(report['orchestration_cases'])}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
