#!/usr/bin/env python3
"""Read-only validation of the one actual native assembly-offset measurement."""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import resource
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[3]
OUT = WT/'artifacts/e1s-development-assym/generate-2'
CHECK = WT/'artifacts/e1s-development-assym/validation-3'
CHECK.mkdir(exist_ok=False)


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def binding(p):
    return {'path':str(p),'sha256':sha(p),'bytes':Path(p).stat().st_size}


checks = []


def require(label, condition):
    checks.append({'name':label,'passed':bool(condition)})
    if not condition:
        raise ValueError(label)


raw_path = OUT/'evidence.json'
require('exact-root75-raw', sha(raw_path)=='8dda1d1ee22392adf59abe1726944a6579fe39b56d497ac7e36f74e6a45e62c3')
raw = json.loads(raw_path.read_text())
plan_path = WT/'artifacts/e1s-development-assym/plan-2/execution-plan.json'
require('exact-source-plan', sha(plan_path)=='9a0d5728fc07ccfbd33b2b12fe6c33232f19084ec663a2147a9f39cfb9ca3e20')
plan = json.loads(plan_path.read_text())
require('exact-root-artifact-runner', raw['runner_sha256']=='7be8e9b248adf32d69c60d351c5cef073032dad0529fd9d6fd9efd55ed622cda')
require('actual-serial-four-commands', len(raw['commands'])==4)
expected = [(c['id'],c['argv']) for c in plan['precommands']]+[
    ('genassym-compile',plan['variants']['0']['compile_argv']),
    ('assym-extract',plan['variants']['0']['extract_argv'])]
for row, (name, argv) in zip(raw['commands'], expected):
    require('actual-argv-'+name, row['id']==name and row['argv']==argv and row['cwd']==str(OUT))
    require('actual-exit-'+name, row['exit_code']==0 and row.get('outcome')=='pass' and not row.get('stop_reason'))
    require('actual-cleanup-'+name, not [p for p in row['after']['owned_processes'] if p['state']!='Z'])
require('terminal-cleanup', raw['outcome']=='pass' and not raw.get('error') and not raw['owned_survivors'])
for p,digest in plan['input_bindings'].items():
    require('unchanged-input:'+p, sha(p)==digest)
for p,digest in raw['output_sha256'].items():
    require('actual-output:'+p, sha(p)==digest)
namespace_path = MAIN/'fixtures/public/e1s-development-exports/qualified-namespace.json'
require('accepted-native-namespace', sha(namespace_path)=='96694dccbb3723199ea0f27893ee7e40b33373a916c4a500a91af5e89e87d5a5')
namespace = json.loads(namespace_path.read_text())
rd = namespace['raw_namespace_descriptor']
require('accepted-raw-descriptor', sha(rd['path'])==rd['sha256'])
exports = json.loads(Path(rd['path']).read_text())
source = Path(plan['source_root'])
manifest_path = source.parent/'prepared-source-manifest.json'
require('accepted-native-source-manifest', sha(manifest_path)=='f884bf7fa08afdffd2f4ba0840ae44d666f1b9848700aaa8f5f88e4dcbe42ba2')
manifest = json.loads(manifest_path.read_text())
common_path = MAIN/'tools/build/avf_kernel_objects.py'
require('existing-MD-parser', sha(common_path)=='9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755')
spec = importlib.util.spec_from_file_location('native_assym_md',common_path)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
paths = common.dependencies(OUT/'genassym.d',OUT,OUT/'genassym.o')
config_files = {s['destination']:s['sha256'] for s in plan['staging_exact_config_copies']}
raw_root = Path(exports['raw_export_root']).parent
external = namespace['external_public_header_contribution']['TargetConditionals']
deps = []
counts = collections.Counter()
for name in paths:
    p = Path(name)
    if p.is_relative_to(source):
        expected_sha = manifest[str(p.relative_to(source))]
        kind = 'native-source'
    elif name in config_files:
        expected_sha = config_files[name]
        kind = 'native-DEVELOPMENT-config'
    elif p.is_relative_to(raw_root/'EXPORT_HDRS'):
        expected_sha = exports['raw_export_files'][str(p.relative_to(raw_root))]
        kind = 'accepted-native-raw'
    elif name==external['path']:
        expected_sha = external['sha256']
        kind = 'qualified-public-TargetConditionals'
    elif p==OUT/'san/kasan-blacklist-arm64':
        expected_sha = raw['generated_ignorelist_sha256']
        kind = 'actual-source-generated-san'
    else:
        raise ValueError('Unqualified actual MD dependency:'+name)
    require('actual-MD-byte:'+name, sha(p)==expected_sha)
    counts[kind] += 1
    deps.append({'path':name,'sha256':expected_sha,'kind':kind})
dep_set = set(paths)
require('native-source-is-actual-dependency', str(source/'osfmk/arm64/genassym.c') in dep_set)
require('actual-native-config', str(OUT/'mach_assert.h') in dep_set and (OUT/'mach_assert.h').read_text().strip()=='#define MACH_ASSERT 1')
board = Path(exports['raw_export_root'])/'pexpert/pexpert/arm64/board_config.h'
e1s = board.parent/'E1S.h'
require('actual-native-board-headers', str(board) in dep_set and str(e1s) in dep_set)
block = board.read_text().split('#ifdef ARM64_BOARD_CONFIG_E1S',1)[1].split('#endif',1)[0]
require('source-qualified-E1S-capacity', re.search(r'^#define\s+MAX_CPUS\s+10\s*$',block,re.M) and re.search(r'^#define\s+MAX_CPU_CLUSTERS\s+4\s*$',block,re.M))
argv = plan['variants']['0']['compile_argv']
require('exact-native-selected-defines', all(a in argv for a in ['-DARM64_BOARD_CONFIG_E1S','-DDEVELOPMENT','-DCONFIG_PMAP_PPL','-S','-MD','-nostdinc']))
require('no-legacy-seed-or-guest-config', not any('XNU_NO_TYPE_BUILTINS' in a or 'BCM2837' in a or a=='-DRELEASE' for a in argv))
assembly = (OUT/'genassym.o').read_text()
records = re.findall(r'^\s*DEFINITION__define__([A-Za-z0-9_]+):\s*\.ascii\s+"([#$]*-?[0-9]+)"\s*$',assembly,re.M)
require('actual-native-assembly-text', '.build_version ios, 16, 5' in assembly and bool(records))
require('unique-compiler-definition-names', len(records)==len(set(k for k,v in records)))
source_names = set(re.findall(r'DECLARE\("([A-Za-z0-9_]+)"', (source/'osfmk/arm64/genassym.c').read_text()))
require('emitted-names-from-real-source', set(k for k,v in records)<=source_names)
defines = re.findall(r'^#define ([A-Za-z0-9_]+) ([#$]*-?[0-9]+)$',(OUT/'assym.s').read_text(),re.M)
require('exact-emitted-and-numeric-pairs', defines==[pair for k,v in records for pair in [(k,v.lstrip('$')),(k+'_NUM',str(int(v.lstrip('$#'))))]])
require('only-extracted-definition-lines', len((OUT/'assym.s').read_text().splitlines())==len(defines))
require('authentic-sed-stream-materialization', sha(OUT/'assym.s')==sha(OUT/'assym-extract.stdout.txt'))
require('source-validated-san-input', sha(OUT/'san/kasan-blacklist-arm64')==sha(OUT/'san-generate.stdout.txt'))
require('no-probe-repeat', [r['id'] for r in raw['commands']]==[x[0] for x in expected] and raw['reused_feature_probe']==plan['probe_receipt'])
for stream in ['san-generate.stderr.txt','san-validate.stdout.txt','san-validate.stderr.txt','assym-extract.stderr.txt']:
    require('clean-stream:'+stream, (OUT/stream).stat().st_size==0)
warning = (OUT/'genassym-compile.log').read_text()
require('compiler-warning-retained', 'deprecated and will be ignored' in warning)
report = {'kind':'host-test','origin':'local-host','outcome':'pass','recorded_at':datetime.now(timezone.utc).isoformat(),
    'summary':'Read-only actual native genassym MD/source/config/raw/public/san closure and assembly/offset extraction validation; no replay',
    'task':'STR-013','owner':plan['owner'],'checks':checks,'raw':binding(raw_path),'plan':binding(plan_path),
    'validator':binding(Path(__file__)),'actual_MD':binding(OUT/'genassym.d'),'dependencies':deps,'dependency_count':len(deps),
    'dependency_classes':dict(counts),'assembly':binding(OUT/'genassym.o'),'assym':binding(OUT/'assym.s'),
    'emitted_records':len(records),'extracted_definitions':len(defines),'definitions':dict(defines),
    'native_context':{'MACH_ASSERT':1,'MAX_CPUS':10,'MAX_CPU_CLUSTERS':4,'CONFIG_PMAP_PPL_selected':True,
        'topology_evidence':'Actual MD includes accepted E1S board headers under exact -DARM64_BOARD_CONFIG_E1S; no runtime topology claim',
        'PPL_execution_or_monitor_runtime_qualified':False},
    'fresh_generated_prerequisites':[d for d in deps if d['kind']=='actual-source-generated-san'],
    'no_MIG_syscall_version_prerequisite_in_actual_MD':not any('/generated/include/libkern/version.h' in p or '/generated/bsd/' in p or '/MIG/' in p for p in paths),
    'controller_current_VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,
    'native_runtime_qualified':False,'full_ABI_qualified':False,'artifacts':[str(raw_path),str(OUT/'genassym.o'),str(OUT/'assym.s'),str(OUT/'genassym.d')]}
(CHECK/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'outcome':'pass','checks':len(checks),'dependencies':len(deps),'classes':dict(counts),
                  'records':len(records),'definitions':len(defines),'evidence_sha256':sha(CHECK/'evidence.json')}))
