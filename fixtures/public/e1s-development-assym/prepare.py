#!/usr/bin/env python3
"""Prepare two genuine Make-derived genassym vectors; never run a compiler."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[3]
OUT = WT / 'artifacts/e1s-development-assym/plan-1'
DEST = WT / 'artifacts/e1s-development-assym/generate-1'
if (OUT / 'execution-plan.json').exists():
    raise ValueError('Preserve the existing plan; use a separately reviewed correction')


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def dump(p, data):
    p.write_text(json.dumps(data, indent=2) + '\n')


inputs = {}


def pin(p, expected=None):
    p = Path(p)
    digest = sha(p)
    if expected is not None and digest != expected:
        raise ValueError('Changed input: ' + str(p))
    if inputs.setdefault(str(p), digest) != digest:
        raise ValueError('Input mutated: ' + str(p))
    return {'path': str(p), 'sha256': digest}


namespace = MAIN / 'fixtures/public/e1s-development-exports/qualified-namespace.json'
pin(namespace, '96694dccbb3723199ea0f27893ee7e40b33373a916c4a500a91af5e89e87d5a5')
consumer = json.loads(namespace.read_text())
raw_binding = consumer['raw_namespace_descriptor']
pin(raw_binding['path'], raw_binding['sha256'])
raw = json.loads(Path(raw_binding['path']).read_text())
source = Path(raw['source_root'])
configs = MAIN / 'fixtures/public/e1s-development-configs/generated-development.json'
pin(configs, '6b0ac2c8e82b2837a94f628ee5c291105559a0607e3febac56fc7e7b6527cf9a')
config = json.loads(configs.read_text())['components']['osfmk']
makefile = Path(config['root']) / 'Makefile'
pin(makefile, config['makefile_sha256'])
text = makefile.read_text()
compile_rule = next(s.strip() for s in text.splitlines() if '${GENASSYM_KCC}' in s)
extract_rule = next(s.strip() for s in text.splitlines() if s.strip().startswith('$(_v)sed ') and 'DEFINITION__define__' in s)
commands_binding = raw['actual_Make_commands']
pin(commands_binding['path'], commands_binding['sha256'])
reference = json.loads(Path(commands_binding['path']).read_text())[0]
args = reference['argv'][5:-1]
args = [a for a in args if not a.startswith(('TARGET=', 'BOUND_CHECKS=', 'SEED_DEFINES='))]
args += ['TARGET=' + str(DEST)]
compiler = Path(next(a.split('=', 1)[1] for a in args if a.startswith('CC=')))
pin(compiler, '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82')
external = consumer['external_public_header_contribution']
pin(external['TargetConditionals']['path'], external['TargetConditionals']['sha256'])
for name in ['makedefs/MakeInc.def', 'makedefs/MakeInc.rule', 'makedefs/MakeInc.dir',
             'osfmk/conf/Makefile.template', 'osfmk/arm64/genassym.c',
             'pexpert/pexpert/arm64/board_config.h', 'pexpert/pexpert/arm64/E1S.h']:
    pin(source / name)
for a in args:
    if a.startswith('MakeInc_cmd='):
        pin(a.split('=', 1)[1])
for tool in ['/usr/bin/make', '/usr/bin/sed', '/bin/bash', '/usr/bin/tr']:
    pin(tool)
staging = []
for relative, digest in config['generated_files'].items():
    original = Path(config['root']) / relative
    pin(original, digest)
    staging.append({'source': str(original), 'sha256': digest, 'destination': str(DEST / relative)})
if DEST.exists():
    raise ValueError('Actual output must remain absent')
query = OUT / 'query.mk'
keys = ['GENASSYM_KCC', 'GENASSYM_LOCATION', 'CFLAGS', 'INCFLAGS', 'CFLAGS_NOLTO_FLAG',
        'SEED_DEFINES', 'BOUND_CHECKS', 'CFLAGS_BOUND_CHECKS']
query.write_text('include ' + str(makefile) + '\n' +
    ''.join('$(info E1SASSYM|' + k + '|$(' + k + '))\n' for k in keys) +
    '$(eval @ := genassym.o)\n$(eval < := $(SOURCE_DIR)/$(COMPONENT)/$(GENASSYM_LOCATION)/genassym.c)\n' +
    '$(info E1SASSYM|COMPILE|' + compile_rule + ')\n$(eval @ := assym.s)\n' +
    '$(info E1SASSYM|EXTRACT|' + extract_rule + ')\n$(info E1SFILES|$(MAKEFILE_LIST))\n' +
    '.PHONY: e1s_assym_query\ne1s_assym_query: ;\n')
pin(query)
env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
queries = []
variants = {}
for bounds in [0, 1]:
    argv = ['/usr/bin/make', '--no-print-directory', '-rR', '-f', str(query), *args,
            'BOUND_CHECKS=' + str(bounds), 'e1s_assym_query']
    started = time.monotonic()
    p = subprocess.run(argv, cwd=OUT, env=env, capture_output=True, text=True, timeout=20)
    stdout, stderr = OUT / f'query-{bounds}.stdout.txt', OUT / f'query-{bounds}.stderr.txt'
    stdout.write_text(p.stdout)
    stderr.write_text(p.stderr)
    queries.append({'argv': argv, 'cwd': str(OUT), 'env': env, 'exit_code': p.returncode,
                    'wall_seconds': time.monotonic() - started, 'stdout': pin(stdout), 'stderr': pin(stderr)})
    if p.returncode or p.stderr.strip():
        dump(OUT / 'failed-query.json', queries)
        raise ValueError('Read-only query failed; preserved output')
    values = {r[1]: r[2] for line in p.stdout.splitlines() if line.startswith('E1SASSYM|') and len(r := line.split('|', 2)) == 3}
    if set(values) != set(keys + ['COMPILE', 'EXTRACT']) or values['SEED_DEFINES']:
        raise ValueError('Incomplete or changed native Make selection')
    for line in p.stdout.splitlines():
        if line.startswith('E1SFILES|'):
            for name in line.split('|', 1)[1].split():
                pin(name)
    cc = shlex.split(values['COMPILE'])
    if cc[0] != str(compiler) or cc[-1] != str(source / 'osfmk/arm64/genassym.c'):
        raise ValueError('Wrong genuine compiler/source')
    assert all(x in cc for x in ['-S', '-MD', '-fno-integrated-as', '-DDEVELOPMENT', '-DARM64_BOARD_CONFIG_E1S'])
    cc[cc.index('-o') + 1] = str(DEST / 'genassym.o')
    # Original -I. receives exact accepted native config copies; the one public
    # contribution was genuinely present in the historical native MD closure.
    cc += ['-MF', str(DEST / 'genassym.d'), '-I', external['include_root']]
    sed = shlex.split(values['EXTRACT'])
    assert sed[0] == 'sed' and sed[-2:] == ['>', 'assym.s']
    sed[0] = '/usr/bin/sed'
    variants[str(bounds)] = {'make_values': values, 'compile_argv': cc,
                            'extract_argv': sed[:-2], 'extract_stdout': str(DEST / 'assym.s')}
assert [x for x in variants['1']['compile_argv'] if x != '-fbounds-attributes'] == variants['0']['compile_argv']
assert variants['0']['extract_argv'] == variants['1']['extract_argv']
plan = {'schema': 'e1s-development-assym-plan-v1', 'task': 'STR-013',
    'owner': 'codex-e1s-development-assym-20261106-sr13', 'experiment': 'STR013ASSYM-001',
    'source_only': True, 'execution_authority': False, 'source_root': str(source),
    'context': {'kernel': 'DEVELOPMENT', 'machine': 'E1S', 'architecture': 'ARM64', 'platform': 'iPhoneOS',
                'MAX_CPUS': 10, 'MAX_CPU_CLUSTERS': 4, 'SEED_DEFINES': ''},
    'actual_output': str(DEST), 'cwd': str(DEST), 'env': env, 'staging_exact_config_copies': staging,
    'probe': {'argv': [str(compiler), '-E', '-fbounds-attributes', '/dev/null'],
              'cwd': str(DEST), 'env': env,
              'source_rule': pin(source / 'makedefs/MakeInc.def'), 'source_lines': [372, 383],
              'selection': 'normal exit0 selects1; normal nonzero selects0; timeout/resource/abnormal stop selects nothing'},
    'variants': variants, 'queries': queries, 'input_bindings': inputs,
    'limits': {'max_jobs': 1, 'whole_seconds': 300, 'compiler_seconds': 120, 'max_owned_rss_bytes': 2147483648},
    'expected_outputs': {n: str(DEST / n) for n in ['genassym.o', 'genassym.d', 'assym.s']},
    'fresh_MD_required': True, 'old_RELEASE_offsets_reused': False, 'full_kernel_qualified': False}
dump(OUT / 'execution-plan.json', plan)
dump(WT / 'fixtures/public/e1s-development-assym/planned-generation.json', {
    'schema': 'e1s-development-assym-source-plan-v1', 'task': plan['task'], 'owner': plan['owner'],
    'experiment': plan['experiment'], 'plan': pin(OUT / 'execution-plan.json'), 'source_only': True,
    'compiler_started': False, 'offsets_qualified': False})
print(json.dumps({'plan': str(OUT / 'execution-plan.json'), 'sha256': sha(OUT / 'execution-plan.json'),
                  'compile_argc': len(variants['0']['compile_argv']), 'queries': len(queries)}))
