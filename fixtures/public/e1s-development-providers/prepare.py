#!/usr/bin/env python3
"""Freeze STR018's narrow source plan; never execute target tools."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def checked(binding):
    path = Path(binding['path'])
    if not path.is_file() or sha(path) != binding['sha256']:
        raise ValueError('Changed source-plan input: ' + str(path))
    return path


def substitute(value, mappings):
    if isinstance(value, str):
        for old, new in mappings.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [substitute(x, mappings) for x in value]
    if isinstance(value, dict):
        return {k: substitute(v, mappings) for k, v in value.items()}
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--actual-out', type=Path, required=True)
    args = ap.parse_args()
    out, actual = args.out.absolute(), args.actual_out.absolute()
    owned = WT / 'artifacts/e1s-development-providers'
    for path in [out, actual]:
        if not path.is_relative_to(owned) or path.resolve() != path or path.exists():
            raise ValueError('Require a fresh canonical owned path: ' + str(path))
    inputs = read(HERE / 'inputs.json')
    if Path(inputs['worktree']) != WT:
        raise ValueError('Plan belongs to another worktree')
    pins = {}

    def bind(binding):
        path = checked(binding)
        pins[str(path)] = binding['sha256']
        return path

    for value in inputs.values():
        if isinstance(value, dict) and {'path', 'sha256'} <= value.keys():
            bind(value)
    for path in [HERE / 'inputs.json', HERE / 'header-route.json',
                 HERE / 'pthread-recipes.json', Path(__file__)]:
        pins[str(path)] = sha(path)
    source = read(inputs['source_context']['path'])
    source_root = Path(source['source_root'])
    derived = read(bind({'path': source['source_manifest'],
                         'sha256': source['source_manifest_sha256']}))
    stage = read(inputs['source_stage']['path'])
    pthread_source = Path(stage['stage_root'])
    if stage['target_tools_executed'] or not stage['typed_source_postimages_match_public_witness']:
        raise ValueError('Require genuine source-only typed pthread staging')
    for relative, digest in stage['files'].items():
        bind({'path': str(pthread_source / relative), 'sha256': digest})

    graph = read(inputs['native_graph']['path'])
    context = read(inputs['native_consumer_context']['path'])
    context_root = Path(context['context_root'])
    if inputs['native_consumer_context']['sha256'] != '00a9d47cb973d0a3bb32426d8218f01bfe1b51038bcef39829e6a65c3780f638':
        raise ValueError('Unexpected native shared context')
    recipe = read(inputs['native_BSD_recipe']['path'])
    if recipe['id'] != 'bsd/subr_log.o' or not recipe['compiler_feature_decision_qualified']:
        raise ValueError('Require the selected current native BSD recipe')
    native = substitute(recipe['selected_compiler_argv'], context['mechanical_prefix_map'])
    for flag in ['-DDEVELOPMENT', '-DCONFIG_PMAP_PPL', '-DXNU_NO_TYPE_BUILTINS=0',
                 '-Wxnu-typed-allocators', '-nostdinc']:
        if flag not in native:
            raise ValueError('Missing genuine native flag: ' + flag)
    if '-w' in native or '-fbounds-attributes' in native:
        raise ValueError('Unexpected compiler diagnostic/feature context')

    mig = read(inputs['MIG']['path'])
    if mig['product_count'] != 127 or mig['typed_export_count'] != 36:
        raise ValueError('Require the genuine composed native MIG descriptor')
    route = read(HERE / 'header-route.json')
    mappings = {'${FRESH_PROVIDER_OUT}': str(actual),
                '${FRESH_PTHREAD_SOURCE}': str(pthread_source)}
    route = substitute(route, mappings)
    copies, commands = [], []
    for row in route['header_rows']:
        origin = row['source']
        if origin['kind'] == 'fresh-prepared-source':
            if derived[origin['relative_to_source']] != origin['sha256']:
                raise ValueError('Header outside exact STR014 source identity')
            bind(origin)
        else:
            product = mig['products'][origin['logical_product']]
            if any(product[k] != origin[k] for k in ['path', 'sha256', 'mode']):
                raise ValueError('Wrong actual MIG header mode or product')
            bind(product)
            copies.append({'source': product['path'], 'sha256': product['sha256'],
                           'destination': origin['staged_native_prerequisite'],
                           'kind': 'actual-MIG-export-prerequisite',
                           'producer': inputs['MIG'], 'original_product': product})
    if len(route['header_rows']) != 315:
        raise ValueError('Unexpected scoped header selection')
    for pin in route['declaration_pins'].values():
        bind(pin)
    for pin in route['tools']:
        bind(pin)
    for index, row in enumerate(route['prospective_genuine_Make_commands']):
        commands.append({'id': 'install-headers-' + str(index).zfill(3),
                         'phase': 'headers', 'argv': row['argv_template'],
                         'cwd': row['cwd_template'], 'timeout_seconds': 120,
                         'header_rows': row['header_rows'], 'root_grant_required': True})

    # Project the exact BSD configuration subtree into a private compiler cwd.
    bsd_prefix = 'configuration/bsd/DEVELOPMENT/'
    for relative, entry in context['files'].items():
        if relative.startswith(bsd_prefix):
            bind(entry)
            copies.append({'source': entry['path'], 'sha256': entry['sha256'],
                           'destination': str(actual / 'native-bsd' / relative.removeprefix(bsd_prefix)),
                           'kind': entry['kind'], 'producer_path': entry['producer_path']})

    firehose_config = Path(inputs['firehose_config']['path']).read_text()
    export_flags = re.search(r'^COPY_HEADERS_UNIFDEF_FLAGS = (.+)$', firehose_config, re.M).group(1).split()
    exported_header = actual / 'firehose-export/include/kernel/os/firehose_buffer_private.h'
    commands.append({'id': 'export-firehose-header', 'phase': 'headers',
                     'argv': [inputs['unifdef']['path'], *export_flags, '-o',
                              str(exported_header), inputs['firehose_header']['path']],
                     'cwd': str(actual), 'accepted_exit_codes': [0, 1],
                     'timeout_seconds': 120, 'root_grant_required': True})
    firehose_root = Path(inputs['firehose_source']['path']).parents[2]
    extra = ['-I', str(exported_header.parents[1]), '-I', str(firehose_root),
             '-I', str(firehose_root / 'src/firehose'), '-I', str(source_root / 'libkern/firehose'),
             '-DKERNEL=1', '-DDISPATCH_USE_DTRACE=0',
             '-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1',
             '-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1',
             '-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0', '-mkernel', '-nostdinc', '-Wno-packed']
    firehose = native.copy()
    firehose[firehose.index(recipe['source'])] = inputs['firehose_source']['path']
    firehose[firehose.index('-MF') + 1] = str(actual / 'objects/firehose_buffer.d')
    firehose[1:1] = extra
    firehose += ['-o', str(actual / 'objects/firehose_buffer.o')]
    commands.append({'id': 'compile-firehose', 'phase': 'objects', 'argv': firehose,
                     'cwd': str(actual / 'native-bsd'), 'timeout_seconds': 120,
                     'root_grant_required': True})
    pt = read(HERE / 'pthread-recipes.json')
    for index, row in enumerate(pt['commands']):
        row = substitute(row, mappings)
        commands.append({'id': row['id'], 'phase': 'objects', 'argv': row['argv_template'],
                         'cwd': row['cwd'], 'timeout_seconds': 120, 'root_grant_required': True})
    for name in ['Availability.h', 'AvailabilityInternal.h', 'AvailabilityMacros.h']:
        path = source_root / 'EXTERNAL_HEADERS' / name
        pins[str(path)] = sha(path)
        copies.append({'source': str(path), 'sha256': pins[str(path)],
                       'destination': str(actual / 'public-availability' / name),
                       'kind': 'exact-public-source-contribution-not-SDK'})
    for label, objects in [('firehose_kernel', ['firehose_buffer']),
                           ('pthread_kext', ['kern_init', 'kern_support', 'kern_synch'])]:
        commands.append({'id': 'archive-' + label, 'phase': 'archives',
                         'argv': [inputs['libtool']['path'], '-static', '-o',
                                  str(actual / ('lib' + label + '.a')),
                                  *[str(actual / 'objects' / (x + '.o')) for x in objects]],
                         'cwd': str(actual), 'timeout_seconds': 120, 'root_grant_required': True,
                         'expected_members': [x + '.o' for x in objects]})
    assert len([c for c in commands if c['phase'] == 'objects']) == 4
    assert len([c for c in commands if c['phase'] == 'archives']) == 2
    directories = {str(actual), str(actual / 'objects'), str(exported_header.parent)}
    directories.update(c['cwd'] for c in commands)
    directories.update(str(Path(c['destination']).parent) for c in copies)
    for path in directories:
        if not Path(path).is_relative_to(actual) or '/unavailable-sdk/' in path:
            raise ValueError('Escaped or fabricated setup directory: ' + path)
    plan = {'schema': 'e1s-development-four-provider-plan-v1',
            'task': inputs['task'], 'owner': inputs['owner'], 'source_only': True,
            'actual_output': str(actual), 'target_tools_executed': False,
            'execution_authority': 'None; exact independent review and separate root budget required',
            'source_context': inputs['source_context'], 'source_stage': inputs['source_stage'],
            'native_consumer_context': inputs['native_consumer_context'],
            'native_BSD_recipe': inputs['native_BSD_recipe'],
            'MIG': inputs['MIG'], 'MIG_mode_order': mig['mode_include_roots_in_order'],
            'setup_owned_directories': sorted(directories),
            'setup_exact_copies': copies, 'commands': commands, 'input_sha256': pins,
            'header_expected_rows': route['header_rows'],
            'native_recipe_adaptation': {
                'source_and_MD_and_output_redirected': True,
                'native_prefix_mechanically_maps_to_exact_consumer005': True,
                'native_CWD_is_exact_BSD_subtree_projection': True,
                'original_BSD_flags_and_perfile_warning_additions_retained': True,
                'foreign_TU_adaptation_requires_independent_review': True,
                'genuine_Firehose_settings_and_header_roots_added': extra},
            'phase_gates': [
                'Freeze actual filtered-header products/hash/nonempty decisions before admitting four compiles',
                'New actual MD must qualify all resolved native/header/source inputs; 315 guide alone is not closure',
                'Same-context native macro/Firehose/pthread layout commands need separately frozen admitted auxiliary plans',
                'Only the four provider objects enter the archives; compare actual member bytes',
                'No execution until reviewed root resource APIs/caller/limits and exact lease are bound'],
            'resource_profile': 'project-budget-v1', 'max_compiler_jobs': 1,
            'new_executor_implemented': False, 'SDK_or_private_ABI_or_link_or_runtime_qualified': False}
    out.mkdir(parents=True, exist_ok=False)
    path = out / 'execution-plan.json'
    path.write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps({'plan': str(path), 'sha256': sha(path), 'commands': len(commands),
                      'headers': len(route['header_rows']), 'input_files': len(pins),
                      'actual_output_absent': not actual.exists(), 'target_tools_executed': False}))


if __name__ == '__main__':
    main()
