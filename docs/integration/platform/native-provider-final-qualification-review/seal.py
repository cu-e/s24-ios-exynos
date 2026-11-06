#!/usr/bin/env python3
"""Seal reviewed native provider facts and exact source patches; no decoder."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[4]
PRODUCER = MAIN / 'worktrees/str-018-e1s-development-providers-20261106'
OUT = WT / 'artifacts/native-provider-final-qualification-review/admission-001'
PINS = {}

def pin(path, expected=None):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), path
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    key = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    assert key(before) == key(after) == key(path.stat()), path
    assert expected is None or digest == expected, path
    PINS[str(path)] = digest
    return digest

def load(path, expected=None):
    pin(path, expected)
    assert Path(path).stat().st_size < 16 * 1024**2
    return json.loads(Path(path).read_bytes())

def refs(value):
    if isinstance(value, dict):
        if set(('path','sha256')) <= value.keys():
            pin(value['path'], value['sha256'])
        else:
            for child in value.values():
                refs(child)
    elif isinstance(value, list):
        for child in value:
            refs(child)

def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args], env={
        **os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'})

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    descriptor = load(PRODUCER / 'fixtures/public/e1s-development-providers/generated-development.json',
                      'ba75ab12068a14ccadf3c131d544852ce1e3bbb28a58e00ca61729437cb0ec0d')
    refs(descriptor)
    assert descriptor['outcome'] == 'pass' and descriptor['remaining_external_import_count'] == 70
    for key in ('task_closed','all_external_imports_or_alias_targets_resolved','auxiliary_objects_in_production_archives_or_kernel',
                'failed001_003_products_adopted','full_private_ABI_link_image_runtime_hardware_qualified'):
        assert descriptor[key] is False, key
    assessment = load(descriptor['assessment']['path'], descriptor['assessment']['sha256'])
    refs(assessment)
    layout = load(descriptor['actual_numeric_layout']['path'], descriptor['actual_numeric_layout']['sha256'])
    consumers = load(descriptor['actual_known_consumers']['path'], descriptor['actual_known_consumers']['sha256'])
    refs(layout); refs(consumers)
    prior = load(PRODUCER / 'artifacts/e1s-development-providers/qualification-pass-record-001/assessment.json',
                 '932263094b75ca321cb3b05974b7d8ba667e3178167325b992b35be71601b475')
    observed = load(consumers['observations']['path'], consumers['observations']['sha256'])
    join = load(consumers['source_join']['path'], consumers['source_join']['sha256']); refs(join)
    numeric = load(WT / 'artifacts/native-provider-final-qualification-review/numeric-002/evidence.json',
                   '3a7fc824bb0ced3f79c6a8eb70fe568e38745e0f192e560c7d60e4f4a7c6e1b6')
    assert numeric['outcome'].startswith('ACCEPT actual auxiliary')
    assert all(o['record'] == layout['record'] for o in numeric['numeric_records'])
    assert assessment['same_context_CPU10_cluster4_PHY9_and_listed_shared_FH_numeric_values'] is True
    assert assessment['actual_MACH_ASSERT_independent_observations'] == layout['MACH_ASSERT_observed_per_recipe'] == [1,1]
    inventories = prior['complete_nm_symbol_inventories']
    definitions = [v['name'] for inv in inventories.values() for v in inv['definitions']]
    imported = {v for inv in inventories.values() for v in inv['imports']}
    native_definitions = [v for obj in observed['products'] for v in obj['external_definitions']]
    assert len(definitions) == len(set(definitions)) == assessment['provider_external_definition_count'] == 47
    assert len(native_definitions) == len(set(native_definitions)) == assessment['native_known_consumer_definition_count'] == 57
    assert not set(definitions).intersection(native_definitions) and assessment['provider_native_duplicate_definitions'] == []
    provider_supplied = imported.intersection(definitions)
    native_supplied = (imported - provider_supplied).intersection(native_definitions)
    remaining = imported - provider_supplied - native_supplied
    assert len(imported) == assessment['provider_unique_import_count'] == 107
    assert provider_supplied == set(assessment['imports_satisfied_by_provider_union']) and len(provider_supplied) == 34
    assert native_supplied == set(assessment['imports_satisfied_by_known_native_consumers']) and len(native_supplied) == 3
    assert remaining == set(assessment['remaining_external_imports']) and len(remaining) == 70
    alias_lines = {tuple(line.split()) for line in Path(descriptor['source_selected_aliases']['path']).read_text().splitlines()
                   if len(line.split()) == 2 and not line.lstrip().startswith('#')}
    assert len(assessment['source_alias_correspondence']) == 3
    for alias in assessment['source_alias_correspondence']:
        assert alias['import_name'] in remaining
        assert (alias['actual_source_selected_target_name'],alias['import_name']) in alias_lines
        assert alias['actual_provider_import_observed'] and alias['actual_final_target_definition'] is None
        assert alias['final_link_alias_binding_qualified'] is False
    identity = join['actual_pthread_struct_declaration_identity']
    for name, ending in [('functions', '} * pthread_functions_t;'),('callbacks', '} *pthread_callbacks_t;')]:
        fragments = []
        for header in ('native_header','actual_provider_filtered_header'):
            raw = Path(identity[header]['path']).read_bytes()
            start = raw.index(('typedef const struct pthread_' + name + '_s {').encode())
            end = raw.index(ending.encode(),start) + len(ending)
            fragment = raw[start:end]; fragments.append(fragment)
            assert len(fragment) == identity['identical_struct_declaration_regions'][name]['bytes']
            assert hashlib.sha256(fragment).hexdigest() == identity['identical_struct_declaration_regions'][name]['sha256']
        assert fragments[0] == fragments[1]
    assert assessment['pthread_interface_boundary']['versions_are_same_table_or_equality_gate'] is False
    assert assessment['all_external_imports_or_alias_targets_resolved'] is False
    assert assessment['historical_111_unsupported_disassembly_remains_not_proof'] is True
    assert assessment['production_objects_or_archives_adopt_auxiliary_probe'] is False
    assert assessment['full_private_ABI_link_image_runtime_hardware_qualified'] is False
    commits = ['e11bf80437e26d0b13ea56b5a17a26de2b9af0c7','2e4123ae15a50c5a63a97475878e412a635aa339',
               '6b27384b0505da4fb2e7ada47dc3158d3d38169e','bf9bc4889ced64053adf95a53f932c60287751cc']
    previous = '1f238daebbeee16bd1d8a7c177da42b43988e584'; mapping = []
    for commit in commits:
        assert git(PRODUCER,'rev-parse',commit+'^').decode().strip() == previous
        paths = git(PRODUCER,'diff-tree','--no-commit-id','--name-only','-r',commit).decode().splitlines()
        assert paths and all(p.startswith(('fixtures/public/e1s-development-providers/','docs/procedures/e1s-development-providers/')) for p in paths)
        patch = git(PRODUCER,'diff','--binary','--full-index','--no-ext-diff','--no-textconv',previous,commit)
        mapping.append({'source':commit,'parent':previous,'paths':paths,'binary_fullindex_patch_sha256':hashlib.sha256(patch).hexdigest()})
        previous = commit
    assert git(PRODUCER,'rev-parse','HEAD').decode().strip() == previous
    assert not git(PRODUCER,'status','--porcelain').strip()
    base = git(MAIN,'rev-parse','HEAD').decode().strip()
    for name, ref in [('generated-headers.json',descriptor['actual_headers']),('generated-products.json',descriptor['actual_products']),
                      ('generated-qualification.json',descriptor['retained_partial111'])]:
        pin(MAIN / 'fixtures/public/e1s-development-providers' / name,ref['sha256'])
    pin(__file__)
    result = {'kind':'source-review','origin':'local-host','outcome':'pass','task':'INT-003','owner':'codex-integrator-platform-20261106-cn',
              'main_observed_base':base,'producer_tip':previous,'source_commit_map':mapping,
              'accepted_scope':'Literal native STR018 provider-build inputs, known consumers, measured shared tuple/layout, callback/source and alias facts',
              'descriptor_sha256':'ba75ab12068a14ccadf3c131d544852ce1e3bbb28a58e00ca61729437cb0ec0d',
              'provider_definitions':47,'known_native_definitions':57,'provider_import_partition':{'total':107,'provider':34,'known_native':3,'remaining':70},
              'remaining_external_imports':sorted(remaining),'source_alias_correspondence':assessment['source_alias_correspondence'],
              'numeric_independent_evidence_sha256':'3a7fc824bb0ced3f79c6a8eb70fe568e38745e0f192e560c7d60e4f4a7c6e1b6',
              'no_target_tools_old_decoder_corpus_or_common_repeated':True,'task_criteria_assessment':'Satisfied within literal provider-build scope; original-owner closure only after root publication/common acceptance.',
              'full_private_ABI_export37_link_image_runtime_hardware_qualified':False,'ledger_task_closed':False,
              'artifact_sha256':PINS}
    output = OUT / 'evidence.json'; output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'outcome':'pass','bindings':len(PINS),'source_commits':len(mapping),'main':base,'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))

if __name__ == '__main__':
    main()
