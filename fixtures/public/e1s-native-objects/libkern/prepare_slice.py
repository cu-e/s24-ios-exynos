#!/usr/bin/env python3
"""Freeze only the original ordered native libkern metadata slice."""
import datetime
import hashlib
import json
from pathlib import Path
import resource
import signal
import sys
import time

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[4]
FIX = Path(__file__).parent
DOC = WT/'docs/procedures/e1s-native-objects/libkern'
QUALIFIED = MAIN/'fixtures/public/e1s-development-body-graph/qualified-graph.json'
EXPECTED = 'c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579'

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def pinned(pin):
    path = Path(pin['path'])
    if sha(path) != pin['sha256']:
        raise ValueError('Frozen input changed: '+str(path))
    return json.loads(path.read_text())

def require(value, message):
    if not value:
        raise ValueError(message)

def alarm(_signum, _frame):
    raise TimeoutError('Source metadata deadline120s')

resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
signal.signal(signal.SIGALRM, alarm)
signal.alarm(120)
started = time.monotonic()
report = {'kind':'source-review', 'origin':'local-host', 'task':'STR-028',
          'owner':'codex-e1s-native-objects-20261106-sr28', 'outcome':'fail',
          'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'actual_argv':[sys.executable, '-s', str(Path(__file__).resolve())],
          'actual_cwd':str(Path.cwd()), 'child_processes_started':0,
          'target_tools_executed':False, 'private_projection_created':False,
          'caller_execution_plan_created':False}
try:
    require(sha(QUALIFIED) == EXPECTED, 'Canonical qualified descriptor')
    q = json.loads(QUALIFIED.read_text())
    graph = pinned(q['graph'])
    context = pinned(q['consumer_context'])
    partitions = pinned(q['partitions'])
    profile = pinned(q['portable_compiler_profile_selection'])
    require(q['partitions']['sha256'] == '2519966081d650108e62e10734f8b23ac4bda51008930e7ec7dec8e53a98e31a', 'Partition freeze')
    require(q['consumer_context']['sha256'] == '00a9d47cb973d0a3bb32426d8218f01bfe1b51038bcef39829e6a65c3780f638', 'Context freeze')
    require(q['portable_compiler_profile_selection']['sha256'] == 'a65f70a1daf01c26399ca1034ff41dafbf790ef86bccc3caa8f84acd0df27581', 'Profile freeze')
    require(profile['selected_external_SEED_DEFINES'] == '-DXNU_NO_TYPE_BUILTINS=0', 'Genuine typecheck profile')
    require(not profile['typechecks_removed_or_disabled'] and not profile['compiler_or_typecheck_stubs_added'], 'No typecheck weakening')
    partition = next(p for p in partitions['partitions'] if p['id'] == 'libkern')
    rows = [row for row in graph['objects'] if row['component'] == 'libkern']
    require(len(rows) == partition['object_count'] == 77, 'Exact original77 rows')
    ids = [row['id'] for row in rows]
    require(len(set(ids)) == 77 and ids == partition['ordered_object_ids'], 'Original partition order')
    component = graph['components']['libkern']
    require([row['target'] for row in rows] == component['ordered_OBJS'], 'Original Make OBJS order')
    require([row['selection_index'] for row in rows] == list(range(77)), 'Original selection indices')
    require(sha(Path(component['makefile'])) == component['makefile_sha256'], 'Native Makefile bytes')
    sources = {}; recipes = {}; languages = {}
    for row in rows:
        binding = context['selected_source_bindings'][row['id']]
        require(sha(Path(binding['path'])) == binding['sha256'], 'Selected actual source '+row['id'])
        require(binding['path'] == row['source'] and binding['sha256'] == row['source_sha256'], 'Unchanged native source '+row['id'])
        recipe = pinned(row['recipe'])
        require(recipe['id'] == row['id'] and recipe['selection_index'] == row['selection_index'], 'Recipe identity '+row['id'])
        sources[row['id']] = binding
        recipes[row['id']] = row['recipe']
        languages[row['language']] = languages.get(row['language'], 0)+1
    pins = {'qualified_graph':{'path':str(QUALIFIED), 'sha256':EXPECTED}}
    for name in ['graph','consumer_context','partitions','portable_compiler_profile_selection','contract','portable_compiler_profile_boundary']:
        pins[name] = q[name]
        require(sha(Path(q[name]['path'])) == q[name]['sha256'], 'Provenance '+name)
    manifest = {
        'schema':'e1s-native-libkern-source-slice-v1', 'kind':'source-review',
        'task':'STR-028', 'owner':report['owner'], 'outcome':'pass',
        'base_commit':'415c9a1fcad73cb47affcedbb037520ce973f888',
        'machine':'E1S','kernel':'DEVELOPMENT','architecture':'ARM64','platform':'iPhoneOS',
        'pins':pins, 'partition':partition, 'objects':rows,
        'actual_selected_source_bindings':sources, 'original_recipe_pins':recipes,
        'component':{name:component[name] for name in ['makefile','makefile_sha256','ordered_OBJS','ordered_LIBOBJS']},
        'native_source_provenance':{name:graph[name] for name in ['source_root','source_manifest_sha256','base_source_manifest_sha256','base_source_profile_sha256']},
        'feature_decision':graph['feature_decision'],
        'portable_compiler_profile_selection':q['portable_compiler_profile_selection'],
        'selected_external_SEED_DEFINES':profile['selected_external_SEED_DEFINES'],
        'CXX_typechecks_enabled':True,
        'caller_freeze':'pending root-reviewed STR030 freeze and budget',
        'not_an_execution_plan':True, 'private_projection_materialized':False,
        'compiler_or_Make_or_generator_executed':False,'old_objects_or_MD_credited':False,
        'full_TU_closure_or_ABI_runtime_hardware_qualified':False}
    target = FIX/'source-slice.json'
    require(not target.exists(), 'Never overwrite a frozen slice')
    target.write_text(json.dumps(manifest, indent=2)+'\n')
    report.update(outcome='pass', actual_exit_code=0, ordered_object_count=77,
                  languages=languages, actual_sources_bound=len(sources), original_recipes_bound=len(recipes),
                  summary='Exact ordered native libkern77 source/recipe slice frozen; no caller plan/projection/target tool.',
                  provenance=pins, artifacts=[str(target.relative_to(MAIN)), str(Path(__file__).resolve().relative_to(MAIN))],
                  sha256={str(target.relative_to(MAIN)):sha(target), str(Path(__file__).resolve().relative_to(MAIN)):sha(Path(__file__).resolve())})
except BaseException as error:
    report.update(error=repr(error), actual_exit_code=1)
finally:
    report['elapsed_seconds'] = time.monotonic()-started
    report['current_image_memory'] = {line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:','VmRSS:'))}
    report['inherited_ru_maxrss_kib_not_current_image'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['limits'] = {'address_space_bytes':256*1024**2, 'deadline_seconds':120}
    (DOC/'source-slice-evidence.json').write_text(json.dumps(report, indent=2)+'\n')
    signal.alarm(0)
print(json.dumps({key:report.get(key) for key in ['outcome','error','ordered_object_count','elapsed_seconds','current_image_memory']}))
raise SystemExit(report['actual_exit_code'])
