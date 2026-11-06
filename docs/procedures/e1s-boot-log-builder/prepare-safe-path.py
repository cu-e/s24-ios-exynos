#!/usr/bin/env python3
"""Source-only ROOT99 import failure correction; never launch corrected stages."""
import ast
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
MAIN=ROOT.parent.parent
OLD=ROOT/'artifacts/e1s-boot-log-builder/prepare-002/plan.json'
OUT=ROOT/'artifacts/e1s-boot-log-builder/prepare-003'
OUT.mkdir(parents=True,exist_ok=False)
def bind(path):
    digest=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024**2):digest.update(block);size+=len(block)
    return dict(path=str(path),sha256=digest.hexdigest(),size=size)
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
old_body=OLD.read_bytes();assert hashlib.sha256(old_body).hexdigest()=='1df5078c0420dc71b63cd1d0f4c7711c1991ea2a4ebc122b7432a21c2d6b6760'
plan=json.loads(old_body)
for name,row in plan['input_bindings'].items():assert bind(row['path'])==row,name
manual=Path('/usr/share/man/man1/python3.14.1.gz');manual_body=gzip.decompress(manual.read_bytes()).decode()
assert 'PYTHONSAFEPATH' in manual_body and 'unsafe' in manual_body and r'\-P' in manual_body
witnesses=[]
for token in ['PYTHONSAFEPATH',r'\-P']:
    at=manual_body.index(token);witnesses.append(dict(token=token,context=manual_body[max(0,at-160):at+650]))
paths=[ROOT/'fixtures/public/e1s-boot-log-builder/source-controls.py',ROOT/'fixtures/public/e1s-boot-log-builder/inspect.py',ROOT/'tools/build/e1s.py',ROOT/'tools/sources.py',MAIN/'references/s24-port/tools/e1s/fix_image.py',MAIN/'references/s24-port/tools/e1s/mkboot.py']
rows=[]
for path in paths:
    tree=ast.parse(path.read_bytes());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(a.name for a in node.names)
        if isinstance(node,ast.ImportFrom):
            assert node.level==0,'Unexpected relative import'
            imports.append(node.module)
    rows.append(dict(input=bind(path),imports=imports))
root99=MAIN/'artifacts/team-coordination/20261106-team/loader99'
receipt=json.loads((root99/'receipt.json').read_bytes())
assert receipt['exit_code']==1 and receipt['evidence'] is None and receipt['owned_survivors']==[]
assert 'partially initialized module' in (root99/'stderr.txt').read_text()
audit=dict(kind='source-review',imports=rows,manual=bind(manual),manual_context=witnesses,
    root99={p.name:bind(p) for p in root99.iterdir() if p.is_file()},
    qualification='Static source import audit and preserved preflight failure only; no corrected runtime test or stage execution.')
dump(OUT/'python-import-source-audit.json',audit)
plan['environment_overrides']['PYTHONSAFEPATH']='1'
plan['source_revision']='python-safe-path-v3';plan['recorded_at']=datetime.now(timezone.utc).isoformat()
plan['supersedes_source_plan']=bind(OLD)
plan['input_bindings']['safe_path_preparer']=bind(Path(__file__))
plan['input_bindings']['safe_path_procedure']=bind(ROOT/'docs/procedures/e1s-boot-log-builder/root101-python-safe-path.md')
plan['input_bindings']['Python314_manual']=bind(manual)
plan['python_import_source_audit']=bind(OUT/'python-import-source-audit.json')
argv=plan['inspector_template']['argv'];argv[argv.index('--plan')+1]=str(OUT/'plan.json')
assert plan['expected_recorded_run_argv']==json.loads(old_body)['expected_recorded_run_argv']
assert not Path(plan['output']['root']).exists()
assert not Path(plan['commands'][0]['argv'][-1]).exists()
assert not Path(argv[argv.index('--out')+1]).parent.exists()
dump(OUT/'plan.json',plan)
print(json.dumps(dict(source_preparation='pass',plan=bind(OUT/'plan.json'),input_bindings=len(plan['input_bindings']),
    unchanged_builder_vectors=len(plan['expected_recorded_run_argv']),source_import_audit=bind(OUT/'python-import-source-audit.json'),actual_execution=False)))
