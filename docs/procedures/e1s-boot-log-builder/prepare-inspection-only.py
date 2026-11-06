#!/usr/bin/env python3
"""Freeze one inspection of retained ROOT101 products; never execute checker."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parent.parent
OLD=ROOT/'artifacts/e1s-boot-log-builder/prepare-003/plan.json'
OUT=ROOT/'artifacts/e1s-boot-log-builder/prepare-004';OUT.mkdir(parents=True,exist_ok=False)
def bind(path):
    digest=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024**2):digest.update(block);size+=len(block)
    return dict(path=str(path),sha256=digest.hexdigest(),size=size)
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
body=OLD.read_bytes();assert hashlib.sha256(body).hexdigest()=='3c94d5b33c2ca7d8ecc25f0d4064a7964adcc7e6c2cb58296b5238dd20bfe73c'
plan=json.loads(body)
for name,row in plan['input_bindings'].items():assert bind(row['path'])==row,name
raw_path=ROOT/'artifacts/e1s-boot-log-builder/measure-root101-001/evidence.json'
assert bind(raw_path)['sha256']=='9a2ea70ee6af0d58d782fa3f0f53581f40e45b141dff888ea124ffa1706ea081'
raw=json.loads(raw_path.read_bytes());assert raw['outcome']=='fail' and raw['owned_survivors']==[]
existing=raw['post_build_observed']
for row in existing.values():assert bind(row['path'])==row
report=json.loads(Path(existing['report']['path']).read_bytes())
assert report['outcome']=='pass' and [r['argv'] for r in report['commands']]==plan['expected_recorded_run_argv']
assert all(row['exit_code']==0 for row in report['commands']) and len(report['products'])==8
for row in report['products']:
    actual=bind(MAIN/row['path']);assert actual['sha256']==row['sha256'] and actual['size']==row['size']
inspector=ROOT/'fixtures/public/e1s-boot-log-builder/inspect-entry.py';ast.parse(inspector.read_bytes())
plan['input_bindings']['original_inspector']=plan['input_bindings']['inspector']
plan['input_bindings']['inspector']=bind(inspector)
for name,path in {'inspection_preparer':Path(__file__),'inspection_procedure':ROOT/'docs/procedures/e1s-boot-log-builder/inspection-only-procedure.md','actual_root101_measurement':raw_path,'actual_root101_receipt':MAIN/'artifacts/team-coordination/20261106-team/loader101/receipt.json','original_failure_capsule':ROOT/'docs/procedures/e1s-boot-log-builder/root101-failure-evidence.json','actual_entry_observation':ROOT/'artifacts/e1s-boot-log-builder/root101-diagnosis-001/entry-observation.json'}.items():plan['input_bindings'][name]=bind(path)
plan['experiment']='STR031INSPECT-002';plan['source_revision']='retained-products-entry-inspection-v4'
plan['phase']='planned-inspection-only-not-executed';plan['recorded_at']=datetime.now(timezone.utc).isoformat();plan['supersedes_source_plan']=bind(OLD)
plan['existing_build_bindings']=existing
plan['retained_product_bindings']=report['products']
inspect_out=ROOT/'artifacts/e1s-boot-log-builder/inspection-002/result.json';assert not inspect_out.parent.exists()
command=dict(id='artifact-inspection',argv=[plan['input_bindings']['python']['path'],'-P','-B','-s',str(inspector),'--build-root',plan['output']['root'],'--main',str(MAIN),'--plan',str(OUT/'plan.json'),'--plan-sha256','@PLAN_SHA256@','--out',str(inspect_out),'--controls'],cwd=str(MAIN),timeout_seconds=120)
plan['commands']=[command];plan['inspector_template']=dict(command,substitution='Only @PLAN_SHA256@ becomes actual frozen plan hash. All input artifacts are retained ROOT101 products; no build/source controls.')
plan['output']['must_not_exist_before_execution']=False
plan['output']['read_only_existing_build']=True
plan['new_inspection_output']=str(inspect_out)
plan['resource_request']=dict(serial_inspection_children=1,max_combined_owned_rss_bytes=2*1024**3,whole_seconds=600,inspection_child_seconds=120,external_seconds=690,root_grant=None,supervisor='Existing qemu_host/core/workguard; root alone owns queue')
plan['qualification']='Retained genuine ROOT101 products inspection only; no source-control/build replay, target execution or physical/native ownership qualification.'
dump(OUT/'plan.json',plan)
print(json.dumps(dict(source_preparation='pass',plan=bind(OUT/'plan.json'),inspector=bind(inspector),input_bindings=len(plan['input_bindings']),planned_children=1,unchanged_builder_vectors=len(plan['expected_recorded_run_argv']),execution=False)))
