#!/usr/bin/env python3
"""Compose one immutable native consumer context from typed actual products.
No Make, generator, compiler, linker or shell is invoked.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import time


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(p, expected):
    p = Path(p)
    if p.is_symlink() or not p.is_file() or sha(p) != expected:
        raise ValueError('Input identity mismatch: ' + str(p))
    return json.loads(p.read_text())


def destination(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('Invalid placement: ' + str(relative))
    target = root / p
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Physical output escape')
    return target


def memory():
    data = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:', 'VmPeak:', 'VmSize:')):
            key, value, _ = line.split(); data[key.rstrip(':')] = int(value)*1024
    if max(data['VmRSS'], data['VmHWM']) > 256*1024**2:
        raise ValueError('Source composition RSS exceeded256MiB')
    return data


class Composition:
    def __init__(self, root):
        self.root = root
        self.files = {}
        self.inputs = {}

    def copy(self, source, digest, relative, kind, mode=None):
        memory()
        source = Path(source)
        if source.is_symlink() or not source.is_file() or sha(source) != digest:
            raise ValueError('Producer bytes differ: ' + str(source))
        target = destination(self.root, relative)
        key = str(target.relative_to(self.root))
        if key in self.files or target.exists():
            raise ValueError('Duplicate/colliding typed placement: ' + key)
        self.inputs[str(source)] = digest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != digest:
            raise ValueError('Copied bytes differ')
        target.chmod(0o444)
        self.files[key] = {'path': str(target), 'sha256': digest, 'producer_path': str(source),
                           'kind': kind, 'mode': mode}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--main', type=Path, required=True)
    ap.add_argument('--graph', type=Path, required=True)
    ap.add_argument('--graph-sha256', required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    started = time.monotonic()
    if int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024 < 4*1024**3:
        raise ValueError('Require4GiB MemAvailable')
    owned = Path(__file__).resolve().parents[3] / 'artifacts/e1s-development-body-graph'
    if a.out != a.out.resolve() or a.out.exists() or not a.out.is_relative_to(owned):
        raise ValueError('Fresh canonical owned output required')
    g = read(a.graph, a.graph_sha256)
    if g['machine'] != 'E1S' or g['kernel'] != 'DEVELOPMENT' or g['selected_component_objects'] != len(g['objects']):
        raise ValueError('Unqualified native graph')
    old = Path(g['component_context_root'])
    a.out.mkdir(parents=True)
    c = Composition(a.out / 'context')
    m = a.main
    descriptor_pins = {
        'mig': (m/'worktrees/str-015-e1s-development-mig-20261106/fixtures/public/e1s-development-mig/generated-development.json',
                'fe67b7906d50bfcb62cd5c5ced1dac7b98a20aaaf823f73f8999f36d18791111'),
        'iig': (m/'worktrees/str-017-e1s-development-iig-20261106/fixtures/public/e1s-development-iig/generated-development.json',
                '76484e5e560521e05ebb5624a5fa750f5981d4f11eb97c293122172a2098310c'),
    }
    d = {k: read(*v) for k, v in descriptor_pins.items()}
    for v in d.values():
        if v['outcome'] != 'pass':
            raise ValueError('Actual producer did not pass')
    config = read(m/'fixtures/public/e1s-development-configs/generated-development.json',
                  '6b0ac2c8e82b2837a94f628ee5c291105559a0607e3febac56fc7e7b6527cf9a')
    n = read(m/'fixtures/public/e1s-development-exports/qualified-namespace.json',
             '96694dccbb3723199ea0f27893ee7e40b33373a916c4a500a91af5e89e87d5a5')
    raw = read(n['raw_namespace_descriptor']['path'], n['raw_namespace_descriptor']['sha256'])
    pm = read(n['producer_map']['path'], n['producer_map']['sha256'])
    for component, data in config['components'].items():
        for relative, digest in data['generated_files'].items():
            name = 'configuration/' + component + '/DEVELOPMENT/' + relative
            c.copy(old/name, digest, name, 'actual-native-configuration')
    for name, digest in raw['raw_export_files'].items():
        c.copy(old/name, digest, name, 'raw-source-export')
    for row in pm['rows']:
        name = row['destination']
        if 'product' in row:
            c.copy(row['product']['path'], row['product']['sha256'], name, row['producer_kind'])
        elif row['producer_kind'] == 'MIG':
            matches = [r for r in d['mig']['typed_export_rows'] if r['destination'] == name]
            if len(matches) != 1 or matches[0]['producer_mode'] != row['producer_mode']:
                raise ValueError('MIG mode/typed destination differs')
            p = matches[0]['actual_product']
            c.copy(p['path'], p['sha256'], name, 'MIG-header', p['mode'])
        elif row['producer_kind'] == 'IIG':
            matches = [r['header'] for r in d['iig']['pairs'] if r['name'] + '.h' == row['name']]
            if len(matches) != 1:
                raise ValueError('Missing/ambiguous IIG header')
            p = matches[0]
            c.copy(p['path'], p['sha256'], name, 'IIG-header')
        elif row['producer_kind'] == 'other-DriverKit-generated-or-staged-header':
            matches = [r for r in d['iig']['source_header_placements'] if r['destination'] == name]
            if len(matches) != 1 or not matches[0]['not_generated_by_IIG']:
                raise ValueError('Missing DriverKit source placement')
            p = matches[0]
            c.copy(p['actual_output'], p['sha256'], name, 'DriverKit-OTHER_HEADERS-source')
        elif row['producer_kind'] == 'source-VPATH-staged-export':
            # Explicit source-VPATH copy; never claim these bytes were generated.
            p = row['source_candidate']
            c.copy(p['path'], p['sha256'], name, 'source-VPATH-staged-export', row['mode'])
        else:
            raise ValueError('Unresolved generated header producer')
    # Internal modes are private configuration inputs, not export replacements.
    for logical, p in d['mig']['products'].items():
        if not logical.startswith('internal/osfmk/'):
            continue
        relative = logical.removeprefix('internal/osfmk/')
        if p['mode'] != 'internal':
            raise ValueError('Internal MIG mode mismatch')
        c.copy(p['path'], p['sha256'], 'configuration/osfmk/DEVELOPMENT/' + relative, 'MIG-internal', 'internal')
    for p in d['iig']['pairs']:
        v = p['implementation']
        c.copy(v['path'], v['sha256'], 'configuration/iokit/DEVELOPMENT/DriverKit/' + p['name'] + '.iig.cpp', 'IIG-implementation')
    for p in pm['separate_generated_TUs']['syscalls']:
        c.copy(p['path'], p['sha256'], 'configuration/bsd/DEVELOPMENT/' + Path(p['path']).name, 'BSD-generated-C')
    p = pm['separate_generated_TUs']['version']
    c.copy(p['path'], p['sha256'], 'configuration/version.c', 'newvers-generated-C')
    assym_path = m/'worktrees/str-013-e1s-development-assym-20261106/fixtures/public/e1s-development-assym/generated-development.json'
    # Accepted descriptor exact digest is bound in the composition, not guessed.
    assym = read(assym_path, '71b557ef6b6c57c5cccf9fa19c3a73aeb6cc57db01d0bd426901e14e3782a862')
    if assym['BOUND_CHECKS'] != g['feature_decision']['BOUND_CHECKS'] or assym['machine'] != 'E1S':
        raise ValueError('Assym native context differs')
    p = assym['assym']
    c.copy(p['path'], p['sha256'], 'configuration/osfmk/DEVELOPMENT/assym.s', 'native-DEVELOPMENT-assym')
    p = g['mandatory_sanitizer_rule']
    c.copy(p['path'], p['sha256'], 'san/kasan-blacklist-arm64', 'genuine-derived-source-san-ignorelist')
    # One public source contribution at the already selected canonical search slot.
    public = m/'artifacts/open-kernel-inputs/typed-pthread-session1/header-tree/src/Libraries/AvailabilityVersions/include/TargetConditionals.h'
    c.copy(public, '17dc82833b1eb8ec946e660fe371d9a64bee669cdfa9226cffc1026d13ee2d9d',
           'unavailable-sdk/usr/local/include/kernel/TargetConditionals.h', 'public-TargetConditionals-only-not-SDK')
    source_bindings = {}
    for row in g['objects']:
        source = Path(row['source'])
        if source.is_relative_to(old):
            source = c.root/source.relative_to(old)
        if not source.is_file() or source.is_symlink():
            raise ValueError('Missing selected source: ' + row['id'])
        digest = sha(source)
        if row.get('source_sha256') and digest != row['source_sha256']:
            raise ValueError('Selected source differs: ' + row['id'])
        source_bindings[row['id']] = {'path': str(source), 'sha256': digest}
    for name, digest in c.inputs.items():
        if sha(name) != digest:
            raise ValueError('Producer changed during composition')
    index = {'schema': 'e1s-native-shared-consumer-context-v1', 'outcome': 'pass',
             'graph': {'path': str(a.graph), 'sha256': a.graph_sha256},
             'context_root': str(c.root), 'component_query_context': str(old),
             'mechanical_prefix_map': {str(old): str(c.root)},
             'typed_producers': {k: {'path': str(v[0]), 'sha256': v[1]} for k, v in descriptor_pins.items()},
             'assym_descriptor': {'path': str(assym_path), 'sha256': sha(assym_path)},
             'files': c.files, 'selected_source_bindings': source_bindings,
             'status_counts': dict(Counter(v['kind'] for v in c.files.values())),
             'producer_inputs': c.inputs, 'generated_sources_materialized': True,
             'source_VPATH_asm_are_copies_not_generated': True,
             'private_CWD_projection': 'Exact component configuration subtree; preserve all relative input paths and byte identities. Redirect object/MD/TMP outputs only.',
             'flags_or_include_order_changed': False, 'compiler_or_generator_executed': False,
             'full_header_or_compiler_input_closure_qualified': False,
             'SDK_or_private_ABI_or_link_or_runtime_or_hardware_qualified': False,
             'wall_seconds': time.monotonic()-started, 'actual_controller_memory': memory(),
             'controller_RSS_cap_bytes': 256*1024**2, 'controller_AS_cap': None, 'child_processes_started': 0}
    (a.out/'consumer-context.json').write_text(json.dumps(index, indent=2)+'\n')
    for directory in sorted(c.root.rglob('*'), reverse=True):
        if directory.is_dir(): directory.chmod(0o555)
    c.root.chmod(0o555)
    print(json.dumps({'outcome': 'pass', 'files': len(c.files), 'selected_sources': len(source_bindings), 'wall_seconds': index['wall_seconds']}))


if __name__ == '__main__':
    main()
