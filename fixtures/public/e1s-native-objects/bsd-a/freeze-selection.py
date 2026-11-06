"""Freeze only STR024 BSD selection/provenance; never prepare or execute commands."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[4]
FIXTURE = WT / 'fixtures/public/e1s-native-objects/bsd-a'
DOCS = WT / 'docs/procedures/e1s-native-objects/bsd-a'
PINS = {
    'interface': (MAIN/'fixtures/public/e1s-development-body-graph/qualified-graph.json',
        'c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579'),
    'source_context': (MAIN/'fixtures/public/e1s-native-source-ports/source-context.json',
        '3b87fdab0a2953438c7fd78f420e138604c258b5d09b97c444187737347df8dc'),
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bound(path):
    return dict(path=str(path), sha256=sha(path), size_bytes=Path(path).stat().st_size)


def dump(path, data):
    with path.open('x') as stream:
        stream.write(json.dumps(data, indent=2)+'\n')


def main():
    started = time.monotonic()
    witnesses = {}

    def read(path, expected):
        path = Path(path)
        if sha(path) != expected:
            raise ValueError('Accepted readonly witness changed: '+str(path))
        witnesses[str(path)] = expected
        return json.loads(path.read_text())

    def linked(entry):
        return read(entry['path'], entry['sha256'])

    interface = read(*PINS['interface'])
    source_context = read(*PINS['source_context'])
    graph = linked(interface['graph'])
    partitions = linked(interface['partitions'])
    context = linked(interface['consumer_context'])
    profile = linked(interface['portable_compiler_profile_selection'])
    for field, expected in [('machine','E1S'),('kernel','DEVELOPMENT'),('architecture','ARM64')]:
        if interface[field] != expected or graph[field] != expected:
            raise ValueError('Native graph profile differs: '+field)
    for field, expected in [('partitions','2519966081d650108e62e10734f8b23ac4bda51008930e7ec7dec8e53a98e31a'),
            ('consumer_context','00a9d47cb973d0a3bb32426d8218f01bfe1b51038bcef39829e6a65c3780f638'),
            ('portable_compiler_profile_selection','a65f70a1daf01c26399ca1034ff41dafbf790ef86bccc3caa8f84acd0df27581')]:
        if interface[field]['sha256'] != expected:
            raise ValueError('Root-selected exact interface version differs: '+field)
    if graph['source_root'] != source_context['source_root'] or graph['source_manifest_sha256'] != source_context['source_manifest_sha256']:
        raise ValueError('STR014 source derivative lineage differs')
    source_manifest = read(source_context['source_manifest'], source_context['source_manifest_sha256'])
    if profile['selected_external_SEED_DEFINES'] != '-DXNU_NO_TYPE_BUILTINS=0' or profile['generated_DEVELOPMENT_default']:
        raise ValueError('Explicit portable compiler profile input differs')
    feature = graph['feature_decision']
    if feature['BOUND_CHECKS'] != 0 or feature['status'] != 'consumed-shared-actual-SR13-receipt':
        raise ValueError('Measured native capability decision differs')
    linked(feature['receipt'])
    for field in ['typed_producers']:
        for entry in context[field].values():linked(entry)
    linked(context['assym_descriptor'])
    for field in ['contract','portable_compiler_profile_boundary']:
        entry=interface[field]
        if sha(entry['path']) != entry['sha256']:raise ValueError('Accepted boundary text differs')
        witnesses[entry['path']]=entry['sha256']
    bsd = graph['components']['bsd']
    if sha(bsd['makefile']) != bsd['makefile_sha256']:
        raise ValueError('Original BSD native configuration changed')
    witnesses[bsd['makefile']] = bsd['makefile_sha256']
    ordered = ['bsd/'+target for target in bsd['ordered_OBJS']]
    shard = next(p for p in partitions['partitions'] if p['id']=='bsd-a')
    ids = ordered[0:170]
    if len(ordered)!=508 or len(ids)!=170 or len(set(ids))!=170 or shard['ordered_object_ids']!=ids or shard['object_count']!=170 or shard['component_slices']!=[dict(component='bsd',start=0,end=170)]:
        raise ValueError('Exact accepted BSD[0:170] partition differs')
    by_id={row['id']:row for row in graph['objects']}
    rows=[]
    for position,identifier in enumerate(ids):
        original=by_id[identifier]
        recipe=linked(original['recipe'])
        if original['selection_index']!=position or recipe['id']!=identifier or recipe['selection_index']!=position:
            raise ValueError('Original selection/recipe ordering differs: '+identifier)
        argv=recipe['selected_compiler_argv']
        if argv[0]!=str(MAIN/profile['compiler_qualification']['compiler']['path']) or '-DXNU_NO_TYPE_BUILTINS=0' not in argv:
            raise ValueError('Frozen compiler/profile vector differs: '+identifier)
        binding=context['selected_source_bindings'][identifier]
        source=Path(binding['path'])
        if sha(source)!=binding['sha256']:
            raise ValueError('Selected readonly source changed: '+identifier)
        witnesses[str(source)]=binding['sha256']
        if original['source_kind']=='actual-native-derived-source':
            relative=str(source.relative_to(Path(source_context['source_root'])))
            if source_manifest[relative]!=binding['sha256'] or original['source_sha256']!=binding['sha256']:
                raise ValueError('Selected STR014 source manifest binding differs: '+identifier)
        else:
            producer=original['actual_producer']
            if producer['sha256']!=binding['sha256'] or sha(producer['path'])!=binding['sha256']:
                raise ValueError('Genuine generated source/placement differs: '+identifier)
            witnesses[producer['path']]=producer['sha256']
        rows.append(dict(id=identifier,selection_index=position,original_graph_row=original,
            selected_readonly_source=dict(binding),original_recipe=original['recipe'],
            original_selected_compiler_argv_sha256=canonical(argv),
            original_selected_expanded_steps_sha256=canonical(recipe['selected_expanded_steps']),
            recipe_or_flags_rewritten=False,caller_plan_or_private_projection_created=False))
    manifest=dict(schema='e1s-native-bsd-a-source-selection-v1',task='STR-024',owner='codex-e1s-native-objects-20261106-sr24',
        shard='bsd-a',component_slice=dict(component='bsd',start=0,end=170),object_count=170,ordered_object_ids=ids,
        accepted_interface=dict(path=str(PINS['interface'][0]),sha256=PINS['interface'][1]),
        graph=interface['graph'],partitions=interface['partitions'],consumer_context=interface['consumer_context'],
        portable_compiler_profile=interface['portable_compiler_profile_selection'],
        kernel='DEVELOPMENT',architecture='ARM64',machine='E1S',platform='iPhoneOS',
        selected_external_SEED_DEFINES=profile['selected_external_SEED_DEFINES'],measured_BOUND_CHECKS=0,
        objects=rows,object_compiled=False,compiler_input_closure_complete=False,old_objects_adopted=False,
        caller_execution_plan_created=False,private_CWD_projection_created=False)
    manifest_path=FIXTURE/'slice-manifest.json';dump(manifest_path,manifest)
    provenance=dict(schema='e1s-native-bsd-a-source-provenance-v1',task='STR-024',
        source_context=dict(path=str(PINS['source_context'][0]),sha256=PINS['source_context'][1]),
        source_root=source_context['source_root'],source_manifest=dict(path=source_context['source_manifest'],sha256=source_context['source_manifest_sha256']),
        compiler_identity_inherited_from_profile=profile['compiler_qualification']['compiler'],
        measured_feature_decision=feature,mandatory_sanitizer_rule=graph['mandatory_sanitizer_rule'],
        shared_context_file_count=len(context['files']),context_status_counts=context['status_counts'],
        typed_producers=context['typed_producers'],assym_descriptor=context['assym_descriptor'],
        selected_source_kinds=dict(Counter(r['original_graph_row']['source_kind']for r in rows)),
        source_and_recipe_witnesses=witnesses,
        pending_gate='STR030 independently reviewed exact native caller freeze plus root-selected source-plan/private-CWD interface and separate budget grant',
        immutable_shared_context_written=False,private_projection_created=False,target_tools_executed=False,
        source_graph_historical_status='Historical pending/placement fields remain unchanged; consumer005 binds actual generated source copies separately')
    provenance_path=FIXTURE/'source-provenance.json';dump(provenance_path,provenance)
    for path,expected in witnesses.items():
        if sha(path)!=expected:raise ValueError('Readonly input changed during selection freeze: '+path)
    artifacts=[manifest_path,provenance_path]
    evidence=dict(kind='source-review',origin='local-host',outcome='pass',recorded_at=datetime.now(timezone.utc).isoformat(),
        task='STR-024',owner='codex-e1s-native-objects-20261106-sr24',argv=sys.orig_argv,builder=bound(__file__),
        summary='Exact accepted native BSD[0:170]170-ID source/recipe selection and provenance only; no caller plan, projection or target tool',
        ordered_first=ids[0],ordered_last=ids[-1],readonly_witness_count=len(witnesses),
        artifacts=[str(p.relative_to(WT))for p in artifacts],sha256={str(p.relative_to(WT)):sha(p)for p in artifacts},
        wall_seconds=time.monotonic()-started,current_image_status=[s.strip()for s in Path('/proc/self/status').read_text().splitlines()if s.startswith(('VmRSS:','VmHWM:'))],
        target_tools_executed=False,caller_plan_created=False,private_projection_created=False,compiler_input_closure_complete=False,
        old_objects_adopted=False,native_runtime_or_ABI_or_hardware_qualified=False)
    dump(DOCS/'selection-evidence.json',evidence)
    print(json.dumps(dict(outcome='pass',object_count=170,first=ids[0],last=ids[-1],manifest=bound(manifest_path),provenance=bound(provenance_path))))


if __name__=='__main__':main()
