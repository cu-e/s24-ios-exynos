#!/usr/bin/env python3
"""Prepare the missing genuine san input, without running any generator."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[3]
OLD = WT/'artifacts/e1s-development-assym/plan-1/execution-plan.json'
OUT = WT/'artifacts/e1s-development-assym/plan-2'
DEST = WT/'artifacts/e1s-development-assym/generate-2'


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def dump(p, d):
    p.write_text(json.dumps(d, indent=2)+'\n')


assert sha(OLD)=='f75f4adb26f9545139c9dd52ac760e36f7f4bb3128ae6c7ca733be6f41a80c59'
assert not DEST.exists()
OUT.mkdir(exist_ok=False)
plan = json.loads(OLD.read_text())
bindings = dict(plan['input_bindings'])


def pin(p, expected=None):
    digest = sha(p)
    if expected is not None:
        assert digest==expected, str(p)
    bindings[str(p)] = digest
    return {'path':str(p), 'sha256':digest}


source = Path(plan['source_root'])
probe = WT/'artifacts/e1s-development-assym/generate-1/compiler-feature-probe.json'
pin(probe, '01d70064392c72114d1ee10a9a5c55ceaa2b7bd3ce1a735a9b4fc06fe47f8332')
feature = json.loads(probe.read_text())
assert feature['normal_exit'] and feature['measured'] and feature['exit_code']==1
assert feature['BOUND_CHECKS']==0 and feature['CFLAGS_BOUND_CHECKS']==[]
assert feature['stop_reason'] is None
for stream in ['stdout','stderr']:
    pin(feature[stream]['path'], feature[stream]['sha256'])
pin(OLD)
pin(Path(__file__))
san_make = source/'san/memory/Makefile'
rule = san_make.read_text()
assert '$(OBJROOT)/san/kasan-blacklist-%: $(SOURCE)/kasan-blacklist $(SOURCE)/ubsan-blacklist $(SOURCE)/kasan-blacklist-%' in rule
assert '''sed -e 's,^src:\\./,src:'"$(SRCROOT)/," $^ > $@''' in rule
pin(san_make)
lists = [source/'san/memory'/n for n in ['kasan-blacklist','ubsan-blacklist','kasan-blacklist-arm64']]
validator = source/'san/tools/validate_blacklist.sh'
for p in [*lists, validator, Path('/usr/bin/sed'), Path('/bin/bash')]:
    pin(p)
blacklist = DEST/'san/kasan-blacklist-arm64'
query = OUT/'query.mk'
query.write_text((OLD.parent/'query.mk').read_text())
pin(query)
oldquery = plan['queries'][0]
argv = [str(query) if a==str(OLD.parent/'query.mk') else a for a in oldquery['argv']]
argv = [a.replace(str(Path(plan['actual_output'])), str(DEST)) for a in argv]
argv.insert(-1, 'UBSAN_BLACKLIST='+str(blacklist))
started = time.monotonic()
p = subprocess.run(argv, cwd=OUT, env=oldquery['env'], capture_output=True, text=True, timeout=20)
stdout, stderr = OUT/'query.stdout.txt', OUT/'query.stderr.txt'
stdout.write_text(p.stdout)
stderr.write_text(p.stderr)
actual = {'argv':argv,'cwd':str(OUT),'env':oldquery['env'],'exit_code':p.returncode,
          'wall_seconds':time.monotonic()-started,'stdout':pin(stdout),'stderr':pin(stderr)}
dump(OUT/'query-result.json', actual)
assert p.returncode==0 and not p.stderr.strip()
values = {r[1]:r[2] for line in p.stdout.splitlines() if line.startswith('E1SASSYM|') and len(r:=line.split('|',2))==3}
assert values['BOUND_CHECKS']=='0' and not values['SEED_DEFINES']
cc = shlex.split(values['COMPILE'])
cc[cc.index('-o')+1] = str(DEST/'genassym.o')
external = plan['variants']['0']['compile_argv'][-1]
cc += ['-MF', str(DEST/'genassym.d'), '-I', external]
oldcc = plan['variants']['0']['compile_argv']
expected = [a.replace(plan['actual_output'],str(DEST)) for a in oldcc]
ignore_index = next(i for i,a in enumerate(expected) if a.startswith('-fsanitize-ignorelist='))
expected[ignore_index] = '-fsanitize-ignorelist='+str(blacklist)
assert cc==expected, 'Non-path compiler flag drift'
sed = shlex.split(values['EXTRACT'])
assert sed[0]=='sed' and sed[-2:]==['>','assym.s']
sed[0]='/usr/bin/sed'
assert sed[:-2]==plan['variants']['0']['extract_argv']
staging = [{**s,'destination':s['destination'].replace(plan['actual_output'],str(DEST))} for s in plan['staging_exact_config_copies']]
path_flags = []
skip = set()
for i, token in enumerate(cc):
    if i in skip:
        continue
    role = None
    value = None
    if token in ['-o','-MF','-include','-I','-isystem','-idirafter','-resource-dir','-isysroot']:
        role, value = token, cc[i+1]
        skip.add(i+1)
    elif token.startswith('-I'):
        role, value = '-I', token[2:]
    elif token.startswith(('-fsanitize-ignorelist=','-resource-dir=')):
        role, value = token.split('=',1)
    elif i==0 or token==str(source/'osfmk/arm64/genassym.c'):
        role, value = 'input-file', token
    if role is None:
        continue
    path = Path(value) if Path(value).is_absolute() else DEST/value
    row = {'argv_index':i,'flag':role,'value':value,'path':str(path)}
    if role in ['-o','-MF']:
        assert not path.exists()
        row['status']='fresh-output'
    elif path==blacklist:
        row['status']='generated-by-bound-san-rule-before-compile'
    elif role=='-include':
        match = next(s for s in staging if Path(s['destination'])==path)
        row.update(status='exact-native-config-stage',source=match['source'],sha256=match['sha256'])
    elif path==DEST:
        row['status']='fresh-native-config-cwd'
    elif role=='input-file':
        row.update(status='bound-file',**pin(path))
    elif path.exists():
        assert path.is_dir()
        row['status']='existing-search-directory'
    else:
        row['status']='absent-search-directory-no-SDK-credit'
    path_flags.append(row)
assert '-nostdinc' in cc and not any(a.startswith('-resource-dir') for a in cc)
driver = MAIN/'artifacts/xnu-compiler-types/frontend-session1/compiler-source/src/clang/lib/Driver/ToolChains/Clang.cpp'
assert 'CmdArgs.push_back("-nostdsysteminc");\n    CmdArgs.push_back("-nobuiltininc");' in driver.read_text()
pin(driver)
new = {**plan,'experiment':'STR013ASSYM-002','actual_output':str(DEST),'cwd':str(DEST),
       'staging_exact_config_copies':staging,'variants':{'0':{'make_values':values,'compile_argv':cc,
          'extract_argv':sed[:-2],'extract_stdout':str(DEST/'assym.s')}}, 'queries':[actual],
       'probe_receipt':{'path':str(probe),'sha256':sha(probe)},'probe_reexecution':False,
       'input_bindings':bindings,'path_operand_preflight':path_flags,
       'resource_header_route':{'explicit_resource_dir':None,'nostdinc':True,
          'builtin_and_standard_system_includes_disabled_by_source':pin(driver),
          'source_lines':[6058,6067],'no_added_resource_flags':True},
       'precommands':[{'id':'san-generate','argv':['/usr/bin/sed','-e','s,^src:\\./,src:'+str(source)+'/,',*[str(p) for p in lists]],
          'stdout_destination':str(blacklist)}, {'id':'san-validate','argv':['/bin/bash',str(validator),str(blacklist)]}],
       'san_recipe':{'source':pin(san_make),'lines':[38,41],'selected_path_variable':'UBSAN_BLACKLIST',
          'definition_source':pin(source/'makedefs/MakeInc.def'),'definition_lines':[524,527]},
       'expected_outputs':{n:str(DEST/n) for n in ['genassym.o','genassym.d','assym.s']},
       'compiler_argv_delta':[{'index':i,'old':a,'new':b} for i,(a,b) in enumerate(zip(oldcc,cc)) if a!=b]}
new.pop('probe')
dump(OUT/'execution-plan.json', new)
dump(WT/'fixtures/public/e1s-development-assym/planned-retry-002.json', {
    'schema':'e1s-development-assym-source-plan-v1','task':'STR-013','owner':plan['owner'],
    'experiment':'STR013ASSYM-002','plan':pin(OUT/'execution-plan.json'),'source_only':True,
    'generator_started':False,'compiler_started':False,'offsets_qualified':False})
print(json.dumps({'plan':str(OUT/'execution-plan.json'),'sha256':sha(OUT/'execution-plan.json'),
                  'delta':new['compiler_argv_delta'],'path_flags':len(path_flags)}))
