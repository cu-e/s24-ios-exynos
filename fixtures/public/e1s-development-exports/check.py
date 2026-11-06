#!/usr/bin/env python3
"""Check stored actual native export traversal, namespace and finite rejections."""
import argparse
from collections import deque
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def verify(out, descriptor=None, rows=None, visits=None, queries=None, physical=True):
    read = lambda name: json.loads((out / name).read_text())
    d = descriptor if descriptor is not None else read('generated-development.json')
    rows = rows if rows is not None else read('source-export-manifest.json')
    visits = visits if visits is not None else read('traversal.json')
    queries = queries if queries is not None else read('query-inventory.json')
    if tuple(d[k] for k in ['machine', 'architecture', 'kernel', 'platform']) != ('E1S', 'ARM64', 'DEVELOPMENT', 'iPhoneOS'):
        raise ValueError('Wrong native context')
    source = Path(d['source_root'])
    source_manifest = json.loads((source.parent / 'prepared-source-manifest.json').read_text())
    if sha(source.parent / 'prepared-source-manifest.json') != d['source_manifest_sha256']:
        raise ValueError('Wrong source witness')
    qmap = {(q['component'], q['directory']): q for q in queries if not q['configured']}
    expected_visits = {}
    expected_rows = []
    for mode, variable in [('MI', 'EXPINC_SUBDIRS'), ('MD', 'EXPINC_SUBDIRS_ARM64')]:
        queue = deque((c, c) for c in d['configuration_roots'])
        while queue:
            component, directory = queue.popleft()
            key = (component, directory, mode)
            if key in expected_visits:
                continue
            q = qmap[(component, directory)]
            values = q['values']
            if values['COMPONENT'] != component or values['EXPDIR'] != 'EXPORT_HDRS/' + component:
                raise ValueError('Bad component export destination')
            expected_visits[key] = {'component': component, 'mode': mode, 'directory': directory,
                                    'recursion_variable': variable, 'children': values[variable].split()}
            queue.extend((component, str(Path(directory) / n)) for n in values[variable].split())
            for generated in [False, True]:
                variable_name = 'EXPORT_' + mode + ('_GEN_LIST' if generated else '_LIST')
                for name in values[variable_name].split():
                    destination = str(Path('EXPORT_HDRS') / component / values['EXPORT_' + mode + '_DIR'] / name)
                    if Path(destination).is_absolute() or '..' in Path(destination).parts:
                        raise ValueError('Invalid namespace destination')
                    expected_rows.append((component, mode, directory, name, destination, generated))
    actual_visits = {(r['component'], r['directory'], r['mode']): r for r in visits}
    if len(actual_visits) != len(visits) or actual_visits != expected_visits:
        raise ValueError('Traversal differs from actual MI/MD source selection')
    actual_rows = [(r['component'], r['mode'], r['directory'], r['name'], r['destination'], r['generated']) for r in rows]
    if sorted(actual_rows) != sorted(expected_rows):
        raise ValueError('Export rows differ from selected real declarations')
    raw = {}
    generated = []
    for row in rows:
        if row['declaration'] != row['directory'] + '/Makefile' or row['query_makefile'] != str(source / row['declaration']):
            raise ValueError('Wrong declaration provenance')
        if row['generated']:
            if row['status'] != 'requires_actual_generated_producer' or 'sha256' in row:
                raise ValueError('Generated output misrepresented as source')
            generated.append(row)
            continue
        if row['status'] != 'raw_source_exported' or row['source'] != str(Path(row['directory']) / row['name']):
            raise ValueError('Wrong physical source mapping')
        if source_manifest[row['source']] != row['sha256']:
            raise ValueError('Raw source not in exact prepared witness')
        if raw.setdefault(row['destination'], row['sha256']) != row['sha256']:
            raise ValueError('Conflicting export ownership')
        if physical and (sha(source / row['source']) != row['sha256'] or sha(out / row['destination']) != row['sha256']):
            raise ValueError('Physical export body differs')
    if not raw or raw != d['raw_export_files'] or len(raw) != d['raw_export_count'] or generated != d['generated_required']:
        raise ValueError('Descriptor does not exactly bind the raw/generated namespace')
    if physical:
        actual_files = {str(p.relative_to(out)) for p in (out / 'EXPORT_HDRS').rglob('*') if p.is_file()}
        if actual_files != set(raw) or any(p.is_symlink() for p in (out / 'EXPORT_HDRS').rglob('*')):
            raise ValueError('Unindexed or symlinked physical exports')
        inputs = read('input-bindings.json')
        if any(sha(path) != digest for path, digest in inputs.items()):
            raise ValueError('Physical producer input changed')
    return len(raw), len(generated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    if a.out.exists():
        raise ValueError('Use fresh control output')
    a.out.mkdir(parents=True)
    d = json.loads((a.prepared / 'generated-development.json').read_text())
    rows = json.loads((a.prepared / 'source-export-manifest.json').read_text())
    visits = json.loads((a.prepared / 'traversal.json').read_text())
    queries = json.loads((a.prepared / 'query-inventory.json').read_text())
    raw_count, generated_count = verify(a.prepared)
    controls = []

    def reject(label, callback):
        try:
            callback()
        except (ValueError, KeyError, FileNotFoundError):
            controls.append({'name': label, 'rejected': True})
        else:
            raise AssertionError('Accepted mutation: ' + label)

    altered = copy.deepcopy(d); altered['machine'] = 'BCM2837'
    reject('wrong-machine-context', lambda: verify(a.prepared, descriptor=altered, physical=False))
    altered = copy.deepcopy(d); altered['source_manifest_sha256'] = '0' * 64
    reject('wrong-source-revision', lambda: verify(a.prepared, descriptor=altered, physical=False))
    changed = copy.deepcopy(visits); changed.pop()
    reject('dropped-real-traversal-directory', lambda: verify(a.prepared, visits=changed, physical=False))
    changed = copy.deepcopy(visits)
    selected = next(v for v in changed if v['children'])
    selected['recursion_variable'] = 'EXPINC_SUBDIRS_ARM64' if selected['mode'] == 'MI' else 'EXPINC_SUBDIRS'
    reject('crossed-MI-MD-recursion', lambda: verify(a.prepared, visits=changed, physical=False))
    changed = copy.deepcopy(rows); changed.pop()
    reject('omitted-selected-export', lambda: verify(a.prepared, rows=changed, physical=False))
    changed = copy.deepcopy(rows); next(r for r in changed if not r['generated'])['sha256'] = '0' * 64
    reject('wrong-real-source-body', lambda: verify(a.prepared, rows=changed, physical=False))
    changed = copy.deepcopy(rows); changed[0]['destination'] = '../../outside.h'
    reject('escaped-output-destination', lambda: verify(a.prepared, rows=changed, physical=False))
    changed = copy.deepcopy(rows); changed[0]['declaration'] = 'osfmk/Makefile'
    if changed[0]['declaration'] == rows[0]['declaration']:
        changed[0]['declaration'] = 'bsd/Makefile'
    reject('wrong-source-export-declaration', lambda: verify(a.prepared, rows=changed, physical=False))
    changed = copy.deepcopy(rows)
    pending = next(r for r in changed if r['generated'])
    pending['status'] = 'raw_source_exported'; pending['sha256'] = '0' * 64
    reject('generated-producer-claimed-as-raw', lambda: verify(a.prepared, rows=changed, physical=False))
    changed = copy.deepcopy(rows); changed.append(copy.deepcopy(next(r for r in rows if not r['generated'])))
    reject('duplicate-foreign-export-row', lambda: verify(a.prepared, rows=changed, physical=False))
    spec = importlib.util.spec_from_file_location('native_export_preparation', Path(__file__).with_name('prepare.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(dir=a.out) as temp:
        root = Path(temp)
        reject('absolute-copy-path', lambda: module.below(root, '/etc/passwd'))
        reject('relative-parent-copy-path', lambda: module.below(root, '../outside'))
        (root / 'link').symlink_to('/tmp', target_is_directory=True)
        reject('physical-symlink-copy-escape', lambda: module.below(root, 'link/outside'))
        ordinary = root / 'ordinary'; ordinary.write_text('real file\n')
        preparation = object.__new__(module.Preparation); preparation.inputs = {}
        reject('modified-producer-input', lambda: preparation.pin(ordinary, '0' * 64))
        (root / 'alias').symlink_to(ordinary)
        reject('symlinked-producer-input', lambda: preparation.pin(root / 'alias'))
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'pass',
              'raw_files_physically_verified': raw_count, 'generated_rows_preserved': generated_count,
              'finite_negative_controls': controls, 'compiler_or_generator_execution': False}
    (a.out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'outcome': 'pass', 'raw_files': raw_count, 'rejected_controls': len(controls)}))


if __name__ == '__main__':
    main()
