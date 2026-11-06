#!/usr/bin/env python3
"""Stream-bind exact producer receipts, runtime artifacts and disclosed archives."""
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent;MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
ROOT='artifacts/avf-project-budget-contention/'
DOC='docs/procedures/avf-project-budget-contention/'
ITEMS=[
 ('vm-044-ep-20261106',ROOT+'baseline-001/evidence.json','80d4c92225e4cb138f40bb5a6a441922e58d02837d0236eee9f75ee94cce0155'),
 ('vm-044-ep-20261106',ROOT+'corrected-001/evidence.json','ebc8c6d2f9b5fec44abbab940528d2653d19a7a0803563e39e6a5235ab4b7fde'),
 ('vm-044-ep-fix1-20261106',ROOT+'final-001/evidence.json','0d783fa081cae4c18b4f368eb266d2acde1b4808878a9694293522856850ccc9'),
 ('vm-044-ep-fix2-20261106',DOC+'focused-evidence.json',None),
 ('vm-044-ep-fix3-20261106',DOC+'kernel-prototype-evidence.json',None),
 ('vm-044-ep-fix4-20261106',DOC+'kernel-final-evidence.json','a4ffb2061c1b7aa91cd8cdd283dd7722a5ec08c756961b3e9eca53ad9e49eaaa'),
 ('vm-044-ep-fix5-20261106',DOC+'restoration-final-evidence.json','94b7e1a2bb8376c3b6685ee8f0bf70da881cc4335539e7e67688f2ae533bb937'),
 ('vm-044-ep-fix5-20261106',DOC+'historical-boundaries.json',None)]
report={'kind':'source-review','outcome':'fail','argv':[sys.executable,*sys.argv],'bindings':[],'receipts':[],'historical_path_changes':[]};started=time.monotonic();seen={};pending=[]


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def resolved(name):
    path=Path(name);return path if path.is_absolute() else MAIN/path


def bind(path,expected=None,source=False):
    actual=digest(path);key=(str(path),expected)
    if key in seen:return
    if expected is not None and actual!=expected:
        archive=None
        if '/vm-044-ep-fix2-20261106/' in str(path) and expected in ['d6579e67cdfa87f251cf02692caf10be9beb362ec7049bc9e7f8c86b59b0c154','e74e373223c8d621dc2a5e9fce3712489916886764441b1194792df29322bf4c']:
            archive=MAIN/'worktrees/vm-044-ep-fix2-20261106'/DOC/'archived-focused-001'/path.name
        if archive is None or digest(archive)!=expected:raise ValueError('Unexpected changed binding: '+str(path))
        report['historical_path_changes'].append({'original_path':str(path),'recorded_sha256':expected,'current_sha256':actual,'retrospective_archive':str(archive),'archive_sha256':digest(archive),'limitation':'Archive created after failed focused-001 entrypoint changed. Hash-identical bytes retained, original physical source path is not unchanged.'})
        bind(archive,expected)
    else:report['bindings'].append({'path':str(path),'sha256':actual,'bytes':path.stat().st_size})
    seen[key]=actual


try:
    for worktree,name,expected in ITEMS:
        path=MAIN/'worktrees'/worktree/name;bind(path,expected);pending.append(path)
    scanned=set()
    while pending:
        path=pending.pop()
        if str(path) in scanned:continue
        scanned.add(str(path));data=json.loads(path.read_text())
        report['receipts'].append({'path':str(path),'outcome_as_recorded':data.get('outcome'),'timeouts':data.get('timeout_count'),'transactions':data.get('transaction_count'),'compiler_started':data.get('compiler_started'),'owned_after':data.get('owned_after')})
        for label in ['sha256','artifact_hashes','source_hashes']:
            mapping=data.get(label,{})
            if not isinstance(mapping,dict):continue
            for name,expected in mapping.items():
                if not isinstance(expected,str) or len(expected)!=64:continue
                target=resolved(name);bind(target,expected,source=label=='source_hashes')
                if target.name.endswith('evidence.json') and str(target) not in scanned:pending.append(target)
        for item in data.get('historical_capsules',[]):
            if isinstance(item,dict):
                name=item.get('path',item.get('evidence'))
                if name:bind(resolved(name),item.get('sha256'))
    if len(report['historical_path_changes'])!=2:raise AssertionError('Expected two explicitly archived old source/control entrypoint bindings')
    report.update(outcome='pass',verdict='Final current bindings pass; two disclosed historical source-path changes are matched to retrospective exact-byte archives, not relabeled unchanged.',elapsed_seconds=time.monotonic()-started)
except Exception as error:report.update(error=repr(error),elapsed_seconds=time.monotonic()-started)
(HERE/'producer-bindings.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['bindings','receipts']}|{'binding_count':len(report['bindings']),'receipt_count':len(report['receipts'])}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
