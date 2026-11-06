#!/usr/bin/env python3
"""Seal four native tail commands; no compiler, Make or postprocessor runs."""
import hashlib
import json
from pathlib import Path
import shlex

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[3]
PLAN_ROOT = WT/'artifacts/e1s-native-tails/plan-1'
OUT = WT/'artifacts/e1s-native-tails/execute-1'
OWNER = 'codex-e1s-native-tails-20261106-sr21'
EXPECTED = ('nonlto.o','version.o','lastkerneldataconst.o','lastkernelconstructor.o')
inputs = {}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def pin(path, expected=None):
    path = Path(path)
    actual = sha(path)
    if expected is not None:
        assert actual==expected, str(path)
    assert inputs.setdefault(str(path), actual)==actual
    return {'path':str(path),'sha256':actual}


def load(bound):
    pin(bound['path'],bound['sha256'])
    return json.loads(Path(bound['path']).read_text())


def dump(path, data):
    path.write_text(json.dumps(data,indent=2)+'\n')


assert not OUT.exists() and not (PLAN_ROOT/'execution-plan.json').exists()
interface_path = MAIN/'fixtures/public/e1s-development-body-graph/qualified-graph.json'
pin(interface_path,'c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579')
pin(Path(__file__))
pin(WT/'docs/procedures/e1s-native-tails/procedure.md')
interface = json.loads(interface_path.read_text())
context = load(interface['consumer_context'])
tails = load(interface['direct_tails'])
profile = load(interface['portable_compiler_profile_selection'])
pin(interface['graph']['path'],interface['graph']['sha256'])
pin(interface['contract']['path'],interface['contract']['sha256'])
assert tuple(r['target'] for r in tails)==EXPECTED
assert profile['selected_external_SEED_DEFINES']=='-DXNU_NO_TYPE_BUILTINS=0'
assert profile['generated_DEVELOPMENT_default'] is False
old_prefix,new_prefix = next(iter(context['mechanical_prefix_map'].items()))
assert len(context['mechanical_prefix_map'])==1
root = Path(context['context_root'])
assert str(root)==new_prefix
for row in context['files'].values():
    pin(row['path'],row['sha256'])
source_context = MAIN/'fixtures/public/e1s-native-source-ports/source-context.json'
pin(source_context,'3b87fdab0a2953438c7fd78f420e138604c258b5d09b97c444187737347df8dc')
sc = json.loads(source_context.read_text())
pin(sc['source_manifest'],sc['source_manifest_sha256'])
source_root = Path(sc['source_root'])
source_files = json.loads(Path(sc['source_manifest']).read_text())
feature = MAIN/'worktrees/str-013-e1s-development-assym-20261106/artifacts/e1s-development-assym/generate-1/compiler-feature-probe.json'
pin(feature,'01d70064392c72114d1ee10a9a5c55ceaa2b7bd3ce1a735a9b4fc06fe47f8332')
fd = json.loads(feature.read_text())
assert fd['BOUND_CHECKS']==0 and fd['normal_exit'] and fd['measured'] and not fd['stop_reason']
pin(fd['compiler']['path'],fd['compiler']['sha256'])
pin(fd['source_rule']['path'],fd['source_rule']['sha256'])
for stream in ['stdout','stderr']:
    pin(fd[stream]['path'],fd[stream]['sha256'])
projection = [v for k,v in context['files'].items() if k.startswith('configuration/kernel/DEVELOPMENT/')]
assert not projection, 'Pinned native top-level projection changed'
cwd = OUT/'objects'


def map_operand(token):
    if old_prefix not in token:
        return token
    if token.startswith(('-I'+old_prefix,'-fsanitize-ignorelist='+old_prefix,old_prefix+'/')):
        return token.replace(old_prefix,new_prefix,1)
    raise ValueError('Unrecognized context operand:'+token)


by_path = {r['path']:r for r in context['files'].values()}
commands = []
paths = []
for row in tails:
    target = row['target']
    original = row['selected_compiler_argv']
    argv = [map_operand(a) for a in original]
    assert len(argv)==106 and '-o' not in argv
    assert '-DXNU_NO_TYPE_BUILTINS=0' in argv and '-fbounds-attributes' not in argv
    assert argv[argv.index('-MF')+1]==target[:-2]+'.d'
    assert '-nostdinc' in argv and '-c' in argv
    source = Path(argv[-1])
    if target=='version.o':
        actual = row['actual_separate_producer']
        assert by_path[str(source)]['sha256']==actual['sha256']
        pin(actual['path'],actual['sha256'])
        pin(source,actual['sha256'])
    else:
        pin(source,source_files[str(source.relative_to(source_root))])
        assert inputs[str(source)]==row['source_sha256']
    pin(row['source_rule'],row['source_rule_sha256'])
    skip = set()
    path_rows = []
    for i,a in enumerate(argv):
        if i in skip:
            continue
        kind,value = None,None
        if a in ['-MF','-include','-I','-isystem','-idirafter','-resource-dir','-isysroot']:
            kind,value = a,argv[i+1]
            skip.add(i+1)
        elif a.startswith('-I'):
            kind,value = '-I',a[2:]
        elif a.startswith(('-fsanitize-ignorelist=','-resource-dir=')):
            kind,value = a.split('=',1)
        elif i==0 or i==len(argv)-1:
            kind,value = 'input-file',a
        if kind is None:
            continue
        path = Path(value) if Path(value).is_absolute() else cwd/value
        item = {'index':i,'flag':kind,'value':value,'path':str(path)}
        if kind=='-MF':
            assert not path.exists()
            item['status']='fresh-output'
        elif path==cwd:
            item['status']='fresh-empty-native-kernel-CWD'
        elif kind in ['input-file','-fsanitize-ignorelist']:
            item.update(status='bound-input',**pin(path))
        elif path.is_dir():
            item['status']='existing-search-directory'
        else:
            assert not path.exists()
            item['status']='explicit-absent-search-directory'
        path_rows.append(item)
    require_san = next(v for v in path_rows if v['flag']=='-fsanitize-ignorelist')
    assert require_san['path']==str(root/'san/kasan-blacklist-arm64')
    commands.append({'id':'kernel/'+target,'target':target,'argv':argv,'cwd':str(cwd),
        'original_compiler_argv':original,'source':pin(source),'implicit_object':str(cwd/target),
        'dependency_file':str(cwd/(target[:-2]+'.d')),'path_operands':path_rows,
        'argv_delta':[{'index':i,'original':a,'selected':b} for i,(a,b) in enumerate(zip(original,argv)) if a!=b],
        'original_recipe_lines':row['original_recipe_lines'],'selected_expanded_steps':row['selected_expanded_steps'],
        'compiler_timeout_seconds':120})
constructor = tails[-1]
tool = constructor['postprocess_tool_binding']
pin(tool['path'],tool['sha256'])
native_tool_source = source_root/'SETUP/setsegname/setsegname.c'
pin(native_tool_source,tool['source_sha256'])
tool_descriptor = MAIN/'fixtures/public/xnu-kernel-direct-tail/qualified-component.json'
pin(tool_descriptor)
td = json.loads(tool_descriptor.read_text())['tool']
for p,d in [(MAIN/td['source'],td['source_sha256']),
            (MAIN/td['compatibility_header'],td['compatibility_header_sha256'])]:
    pin(p,d)
assert tool['sha256']=='aec52c72b8555f9c11707834566742f9683ca09e170084e83ff35f7031e5ff2f'
assert td['source_sha256']==tool['source_sha256']
assert constructor['original_profile_removal']=='lastkernelconstructor.o_CFLAGS_RM = -fprofile-instr-generate'
literal_shell = '\n'.join(s for i,s in constructor['selected_expanded_steps'].items() if int(i)>=5)
assert 'for last_file in lastkernelconstructor.o;' in literal_shell
assert str(tool['path'])+' -s __DATA -n __LASTDATA_CONST -o ${last_file}__ ${last_file} || exit 1;' in literal_shell
transform = {'id':'constructor-native-section-transform','argv':[tool['path'],'-s','__DATA','-n','__LASTDATA_CONST',
    '-o',str(cwd/'lastkernelconstructor.o__'),str(cwd/'lastkernelconstructor.o')],
    'cwd':str(cwd),'timeout_seconds':30,'original_literal_shell':literal_shell,
    'raw_snapshot_before':str(OUT/'raw/lastkernelconstructor.o'),
    'rename_only_after_exit0':{'source':str(cwd/'lastkernelconstructor.o__'),'destination':str(cwd/'lastkernelconstructor.o')},
    'single_LAST_FILES_equivalence':'One original LAST_FILES member; same tool/flags/order, canonical fresh output operands and mv after success',
    'tool_reuse_only_no_historical_object_credit':True}
helpers = {}
for label,path,digest in [('common',MAIN/'tools/build/avf_kernel_objects.py','9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'),
    ('supervisor',MAIN/'tools/build/qemu_host.py','faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99'),
    ('inspection_and_cancellation',MAIN/'tools/build/avf_guest_link_inputs.py','9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5')]:
    helpers[label]=pin(path,digest)
driver = MAIN/'artifacts/xnu-compiler-types/frontend-session1/compiler-source/src/clang/lib/Driver/ToolChains/Clang.cpp'
pin(driver)
assert 'CmdArgs.push_back("-nostdsysteminc");\n    CmdArgs.push_back("-nobuiltininc");' in driver.read_text()
plan = {'schema':'e1s-native-tails-plan-v1','resource_profile':'project-budget-v1','task':'STR-021','owner':OWNER,
    'experiment':'E1SNATIVETAILS-001','shard':'native-link-tails','main':str(MAIN),'out':str(OUT),
    'source_only':True,'execution_authority':False,'root_caller_and_allocation_binding':'Required before target execution; not provided by this preparation',
    'graph_interface':pin(interface_path),'accepted_graph':interface['graph'],'consumer_context':interface['consumer_context'],
    'portable_compiler_profile':interface['portable_compiler_profile_selection'],'shared_feature_receipt':pin(feature),
    'derived_source_context':pin(source_context),'original_context_prefix':old_prefix,'selected_context_prefix':new_prefix,
    'private_CWD_projection':projection,'compile_commands':commands,'postprocess':transform,'helpers':helpers,
    'limits':{'max_jobs':1,'max_owned_rss_bytes':512*1024**2,'whole_seconds':600,'compiler_seconds':120,
              'transform_seconds':30,'max_total_project_rss_bytes':6*1024**3,'light_reserved_rss_bytes':2*1024**3},
    'resource_header_rule':{'nostdinc':True,'explicit_resource_dir':None,'source':pin(driver),'source_lines':[6058,6067]},
    'native_context_boundary':'Actual top-level Make vector, not component CONFIG_DEFINES; no forced Mach/assert config absent from recipe',
    'input_bindings':inputs,'context_file_count':len(context['files']),
    'actual_MD_and_ARM64_MachO_required':True,'actual_MIG_or_IIG_dependency':'Not assumed; classify fresh actual MD against typed accepted context',
    'constructor_validation':'Existing verify_constructor_transform(raw,final), bounded_macho and exact final bytes/symbols/imports',
    'old_RELEASE_or_BCM_objects_reused':False,'archive_or_link_or_runtime_qualified':False}
dump(PLAN_ROOT/'execution-plan.json',plan)
dump(WT/'fixtures/public/e1s-native-tails/planned-tails.json',{'schema':'e1s-native-tails-source-plan-v1',
    'task':plan['task'],'owner':OWNER,'experiment':plan['experiment'],'plan':pin(PLAN_ROOT/'execution-plan.json'),
    'source_only':True,'compiler_or_postprocessor_executed':False})
print(json.dumps({'plan':str(PLAN_ROOT/'execution-plan.json'),'sha256':sha(PLAN_ROOT/'execution-plan.json'),
                  'commands':len(commands),'transform_tool_sha256':tool['sha256'],'context_files':len(context['files'])}))
