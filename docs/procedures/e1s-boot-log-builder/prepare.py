#!/usr/bin/env python3
"""Freeze source/command/layout inputs only. No builder/compiler/control execution."""
import ast
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
MAIN=ROOT.parent.parent
OUT=ROOT/'artifacts/e1s-boot-log-builder/prepare-001'
OUT.mkdir(parents=True,exist_ok=False)
commands=[]
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bind(path):return {'path':str(path),'sha256':sha(path),'size':Path(path).stat().st_size}
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def git(*args):
    argv=['git','-C',str(MAIN/'references/s24-port'),*args]
    result=subprocess.run(argv,capture_output=True,timeout=15,env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'})
    commands.append({'argv':argv,'exit_code':result.returncode,'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr':result.stderr.decode(errors='replace')})
    dump(OUT/'source-commands.json',commands)
    if result.returncode:raise RuntimeError('Pinned source query failed; preserve source-commands.json')
    return result.stdout
candidate=ROOT/'tools/build/e1s.py';parent=MAIN/'tools/build/e1s.py'
assert sha(parent)=='18225ebae9b90a73b2d08387e6ab5fcdb74f594feb4f05a72914c9f0392bbcde'
tree=ast.parse(candidate.read_text());base=ast.parse(parent.read_text());normalized=copy.deepcopy(tree)
fn=next(n for n in normalized.body if isinstance(n,ast.FunctionDef) and n.name=='build')
report=next(n.value for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='report' for t in n.targets))
keep=[(k,v) for k,v in zip(report.keys,report.values) if not(isinstance(k,ast.Constant) and k.value=='boot_log_source_patch')]
report.keys=[p[0] for p in keep];report.values=[p[1] for p in keep]
trial=next(n for n in fn.body if isinstance(n,ast.Try))
begin=next(i for i,n in enumerate(trial.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='log_patch' for t in n.targets))
end=next(i for i,n in enumerate(trial.body[begin:],begin) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='products' for t in n.targets))
removed=trial.body[begin:end];trial.body[begin:end]=[]
assert ast.dump(normalized,include_attributes=False)==ast.dump(base,include_attributes=False),'Parent pipeline changed beyond third hook'
proof={'candidate':bind(candidate),'parent':bind(parent),'only_new_report_key':'boot_log_source_patch',
       'removed_hook_statements':len(removed),'all_other_parent_AST_identical':True,
       'target_compiler_or_builder_executed':False,'recorded_builder_commands_expected':23,
       'unchanged_parent_recorded_commands':21,'new_check_apply_commands':2}
dump(OUT/'parent-preservation.json',proof)
old_path=MAIN/'artifacts/e1s-build/str008-framebuffer-20261106-001/report.json'
assert sha(old_path)=='4419e266533ca37194923a896eb406213e0340000bf627ac4aa785b243817d9e'
old=json.loads(old_path.read_text());assert len(old['commands'])==21 and old['outcome']=='pass'
run='str031-loader-log-20261106-001';build_root=MAIN/'artifacts/e1s-build'/run
assert not build_root.exists()
old_relative='artifacts/e1s-build/str008-framebuffer-20261106-001'
new_relative=str(build_root.relative_to(MAIN))
def rebase(value):
    return value.replace(str(MAIN/old_relative),str(build_root)).replace(old_relative,new_relative)
expected=[[rebase(v) for v in row['argv']] for row in old['commands']]
snapshot=build_root/'loader-owned-diagnostics.patch'
expected[5:5]=[['git','apply','--check',str(snapshot)],['git','apply',str(snapshot)]]
assert len(expected)==23
source_config=MAIN/'fixtures/public/e1s-boot-log/source-bindings.json'
source=json.loads(source_config.read_text())
revision=source['upstream']['revision'];assert revision=='c8860decc62c6d6180e609036d027a2997972420'
files=['shim/e1s/start.S','shim/e1s/probe.c','shim/e1s/loader.ld','shim/e1s/font.h',
       *['shim/e1s-xnu/'+name for name in ['start.S','loader.c','ui.c','adt_patch.c','gic.c','fdt.c','loader.ld','ui.h','adt_patch.h','gic.h','fdt.h']],
       'tools/e1s/fix_image.py','tools/e1s/mkboot.py']
post={};donor={}
for relative in files:
    body=git('show',revision+':'+relative)
    assert body==(MAIN/'references/s24-port'/relative).read_bytes(),'Source working bytes differ from exact Git blob'
    row={'sha256':hashlib.sha256(body).hexdigest(),'git_blob_sha1':git('rev-parse',revision+':'+relative).decode().strip()}
    donor[relative]=row
    post[relative]=source['proposal']['files'].get(relative,{}).get('proposal_sha256',row['sha256'])
dump(OUT/'source-inputs.json',{'revision':revision,'donor':donor,'expected_post_source_sha256':post,
    'dependency_scope':'All source-local C/ASM/header/linker/packager inputs; existing pipeline emits no MD. Bundled stdint is separately pinned, no actual target MD asserted.'})
prior_plan=MAIN/'docs/procedures/e1s-framebuffer-builder/build-plan-001.json'
prior=json.loads(prior_plan.read_text())
for name in ['zig','git','python']:
    assert sha(prior['tools'][name]['path'])==prior['tools'][name]['sha256'],'Accepted tool changed: '+name
paths={'candidate':candidate,'parent_builder':parent,'candidate_source_verifier':ROOT/'tools/sources.py',
 'main_source_verifier':MAIN/'tools/sources.py','source_registry':MAIN/'research/sources.json',
 'RAM_patch':MAIN/'patches/e1s-boot/0001-loader-memory-validation.patch',
 'FB_patch':MAIN/'patches/e1s-display/0001-loader-framebuffer-contract.patch',
 'log_patch':MAIN/'patches/e1s-boot-log/0001-loader-owned-diagnostics.patch',
 'accepted_source_inputs':source_config,'accepted_host_evidence':MAIN/'docs/procedures/e1s-boot-log-host/evidence.json',
 'parent_actual_report':old_path,'prior_tool_plan':prior_plan,
 'inspector':ROOT/'fixtures/public/e1s-boot-log-builder/inspect.py',
 'source_controls':ROOT/'fixtures/public/e1s-boot-log-builder/source-controls.py',
 'preparer':Path(__file__),'procedure':ROOT/'docs/procedures/e1s-boot-log-builder/procedure.md',
 'Zig_resource_stdint':Path('/usr/lib/zig/include/stdint.h'),'ELF_relocation_definitions':Path('/usr/include/elf.h')}
for name in ['zig','git','python']:paths[name]=Path(prior['tools'][name]['path'])
baseline=MAIN/'worktrees/str-019-e1s-boot-log-20261106/artifacts/e1s-boot-log/source-002/baseline'
donor_root=baseline.parent/'donor'
for rel in ['shim/e1s-xnu/loader.c','shim/e1s-xnu/ui.c']:
    paths['composed_baseline_'+Path(rel).name]=baseline/rel
paths['donor_UI']=donor_root/'shim/e1s-xnu/ui.c'
inputs={name:bind(path) for name,path in paths.items()}
assert inputs['log_patch']['sha256']=='569663074fb7de230b4760a613562841afe311352ed32e78275c55708aa21328'
assert inputs['accepted_host_evidence']['sha256']=='7a401ad85a2183bcfdec36233578c5d374b0d2db3714fc7c6d34055f8b00c836'
python=prior['tools']['python']['path'];control_out=ROOT/'artifacts/e1s-boot-log-builder/source-controls-001'
inspect_out=ROOT/'artifacts/e1s-boot-log-builder/inspection-001/result.json'
assert not control_out.exists() and not inspect_out.parent.exists()
plan={'schema':'e1s-boot-log-builder-plan-v1','phase':'planned-not-executed','task':'STR-031',
 'owner':'codex-e1s-boot-log-builder-20261106-sr31','experiment':'STR031BUILD-001',
 'recorded_at':datetime.now(timezone.utc).isoformat(),'main_source_base':'7189aa4f73582260d15351717eaabc7dd7d8e711',
 'input_bindings':inputs,'expected_recorded_run_argv':expected,'expected_product_paths':[rebase(p['path']) for p in old['products']],
 'expected_post_source_sha256':post,'expected_source':{k:old['source'][k] for k in ['id','origin','revision']},
 'parent_preservation':bind(OUT/'parent-preservation.json'),'source_dependencies':bind(OUT/'source-inputs.json'),
 'output':{'root':str(build_root),'report':str(build_root/'report.json'),'must_not_exist_before_execution':True},
 'commands':[
  {'id':'source-hook-controls','argv':[python,str(paths['source_controls']),'--candidate',str(candidate),'--baseline',str(baseline),
      '--donor',str(donor_root),'--patch',str(paths['log_patch']),'--out',str(control_out)],'cwd':str(MAIN),'timeout_seconds':120},
  {'id':'ordinary-builder','argv':[python,str(candidate),'--root',str(MAIN),'--run',run],'cwd':str(MAIN),'timeout_seconds':600},
 ],
 'inspector_template':{'argv':[python,str(paths['inspector']),'--build-root',str(build_root),'--main',str(MAIN),
     '--plan',str(OUT/'plan.json'),'--plan-sha256','@PLAN_SHA256@','--out',str(inspect_out),'--controls'],
     'cwd':str(MAIN),'timeout_seconds':120,'substitution':'Only @PLAN_SHA256@ is replaced by the actual frozen plan hash; no target flag/source/input substitution.'},
 'environment_overrides':{'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'},
 'resource_request':{'serial_builders':1,'max_combined_owned_rss_bytes':2*1024**3,'whole_seconds':600,
     'inner_builder_child_seconds':120,'source_control_seconds':120,'artifact_inspection_seconds':120,
     'root_grant':None,'native_kernel_wave_has_priority':True,'supervisor':'Existing root75/root83 qemu_host/core/work_guard APIs, no new generic executor'},
 'no_target_or_compiler_or_control_executed_by_preparation':True,
 'qualification':'Genuine freestanding probe/loader artifacts and numeric source/layout only; no XNU payload, target execution, physical mapping/persistence/retrieval/recovery or kernel0011/12 ownership.'}
dump(OUT/'plan.json',plan)
print(json.dumps({'source_preparation':'pass','plan':str(OUT/'plan.json'),'plan_sha256':sha(OUT/'plan.json'),
    'recorded_builder_commands':23,'preserved_parent_commands':21,'new_overlay_commands':2,
    'source_files':len(post),'input_bindings':len(inputs),'target_or_control_execution':False}))
