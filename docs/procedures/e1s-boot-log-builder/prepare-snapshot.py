#!/usr/bin/env python3
"""Additive source-only STR031 snapshot correction freeze; never execute controls."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
MAIN=ROOT.parent.parent
OLD=ROOT/'artifacts/e1s-boot-log-builder/prepare-001/plan.json'
OUT=ROOT/'artifacts/e1s-boot-log-builder/prepare-002'
OUT.mkdir(parents=True,exist_ok=False)
def bind(path):
    with Path(path).open('rb') as stream:
        body=stream.read() if Path(path).stat().st_size<1024**2 else None
    if body is not None:return dict(path=str(path),sha256=hashlib.sha256(body).hexdigest(),size=len(body))
    digest=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024*1024):size+=len(block);digest.update(block)
    return dict(path=str(path),sha256=digest.hexdigest(),size=size)
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
old_body=OLD.read_bytes()
assert hashlib.sha256(old_body).hexdigest()=='5d329ff58a28a81bd116da592cdba32f431a14eab9fd0a66843e89c293639294'
plan=json.loads(old_body)
for name,binding in plan['input_bindings'].items():
    if name=='inspector':continue
    assert bind(binding['path'])==binding,'Changed non-inspector original input: '+name
inspector=ROOT/'fixtures/public/e1s-boot-log-builder/inspect.py'
ast.parse(inspector.read_bytes())
plan['input_bindings']['inspector']=bind(inspector)
plan['input_bindings']['snapshot_preparer']=bind(Path(__file__))
plan['input_bindings']['snapshot_correction_procedure']=bind(ROOT/'docs/procedures/e1s-boot-log-builder/snapshot-correction.md')
plan['source_revision']='snapshot-correction-v2'
plan['recorded_at']=datetime.now(timezone.utc).isoformat()
plan['supersedes_source_plan']=bind(OLD)
plan['superseded_source_commit']='0ff8705fa1a88304c193ceaf8cedb3a002696c72'
argv=plan['inspector_template']['argv'];argv[argv.index('--plan')+1]=str(OUT/'plan.json')
plan['inspector_template']['snapshot_semantics']='Digest, size, parsing and result hashes refer to identical bounded captured bytes; no current-path identity claim.'
assert not Path(plan['output']['root']).exists()
for command in plan['commands']:
    if command['id']=='source-hook-controls':assert not Path(command['argv'][command['argv'].index('--out')+1]).exists()
assert not Path(argv[argv.index('--out')+1]).parent.exists()
assert len(plan['expected_recorded_run_argv'])==23
assert plan['expected_recorded_run_argv']==json.loads(old_body)['expected_recorded_run_argv']
dump(OUT/'plan.json',plan)
print(json.dumps(dict(source_preparation='pass',plan=bind(OUT/'plan.json'),inspector=bind(inspector),
    unchanged_recorded_builder_commands=23,input_bindings=len(plan['input_bindings']),
    target_compiler_control_or_inspector_executed=False)))
