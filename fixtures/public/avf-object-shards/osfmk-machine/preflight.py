#!/usr/bin/env python3
"""Audit the VM-015 source allocation without executing any build tool."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import resource
import sys
import time

sys.dont_write_bytecode = True
MANIFEST = 'afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd'
ALLOCATION = '855246471cd69fc7b0e482b5247b1e249adc1453018c922698435bbc88972853'
QUALIFICATION = '058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7'
COMPILER = '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'
TREE = '6a955269a8f4e17d21239f75cef9fbe66cffc56c'
CONFIG = '1571c785ae12ed79858fb9c81ebfce4ecd5414e4ce6af906820f6b9d61f68394'
FLOOR = 4 * 1024**3
LIMIT = 256 * 1024**2


def memory():
    values = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            key, value = line.split(':', 1)
            values[key] = int(value.split()[0]) * 1024
    values['inherited_ru_maxrss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    return values


def available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable is unavailable')


class Audit:
    def __init__(self):
        self.started = time.monotonic()
        self.files = {}
        self.checks = 0

    def require(self, condition, message):
        self.checks += 1
        if not condition:
            raise ValueError(message)

    def guard(self):
        if time.monotonic() - self.started > 180 or memory()['VmHWM'] > LIMIT or available() < FLOOR:
            raise RuntimeError('Source audit resource/deadline guard rejected continuation')

    def sha(self, name, expected=None):
        self.guard()
        path = Path(name)
        before = path.stat()
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = path.stat()
        self.require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                     (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                     'Input changed while hashing: ' + str(path))
        if expected is not None:
            self.require(digest == expected, 'SHA256 mismatch: ' + str(path))
        self.files[str(path)] = digest
        return digest

    def load(self, path, expected=None):
        self.sha(path, expected)
        self.require(Path(path).stat().st_size <= 64 * 1024**2, 'Oversized JSON input')
        with Path(path).open() as stream:
            return json.load(stream)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rows_admit(audit, rows, wanted):
    audit.require(len(wanted) == 77 and len(set(wanted)) == 77, 'Allocation must contain exactly77 distinct IDs')
    audit.require([row['id'] for row in rows] == wanted, 'Selected rows differ from exact allocated order')
    for row in rows:
        argv = row['next_owned_compile_argv_template']
        identity = row['id']
        audit.require(row['component'] == 'osfmk' and identity == 'osfmk/' + row['target'], 'Foreign object identity')
        audit.require(row['status'] == 'genuine_source_and_recipe_bound_not_compiled' and
                      row['execution_requires_new_plan_and_resource_lease'] is True, 'Missing build admission boundary')
        audit.require(row['source'] == row['bound_source'] and row['source_sha256'] == row['bound_source_sha256'], 'Source binding differs')
        audit.require(argv.count(row['bound_source']) == 1 and argv.count('-c') == 1, 'Source compile argument differs')
        for option, expected in [('-o', '@NEXT_OBJECT_DIR@/' + identity), ('-MF', '@NEXT_DEPENDENCY_DIR@/' + identity + '.d')]:
            audit.require(argv.count(option) == 1 and argv[argv.index(option) + 1] == expected, 'Output escapes its exact object identity')
        audit.require([arg for arg in argv if '@' in arg] == ['@NEXT_DEPENDENCY_DIR@/' + identity + '.d', '@NEXT_OBJECT_DIR@/' + identity], 'Unknown placeholder/response file')
        audit.require('-DARM64_BOARD_CONFIG_BCM2837' in argv and argv[argv.index('-target') + 1] == 'arm64-apple-ios16.5', 'Guest board/target differs')
        if row['language'] != 'asm':
            audit.require('-DDEVELOPMENT' in argv and '-DXNU_NO_TYPE_BUILTINS=0' in argv and '-DXNU_NO_TYPE_BUILTINS=1' not in argv, 'Guest config or allocator metadata was weakened')


def includes(row):
    argv = row['next_owned_compile_argv_template']
    cwd = Path(row['cwd'])
    roots, forced, auxiliary = [], [], []
    for i, arg in enumerate(argv):
        if arg in ['-I', '-isystem', '-iquote', '-idirafter']:
            roots.append(str((cwd / argv[i + 1]).absolute()))
        elif arg.startswith('-I') and len(arg) > 2:
            roots.append(str((cwd / arg[2:]).absolute()))
        elif arg == '-include':
            forced.append(argv[i + 1])
        elif arg.startswith('-fsanitize-ignorelist='):
            auxiliary.append(arg.split('=', 1)[1])
    return roots, forced, auxiliary


def source_audit(audit, main, selection):
    allocation = audit.load(main / selection['allocation'], ALLOCATION)
    graph = audit.load(main / selection['source_manifest'], MANIFEST)
    wanted = allocation['shards']['osfmk-machine']
    audit.require(selection['task'] == 'VM-015' and selection['selector'] == 'osfmk-machine' and selection['expected_count'] == 77, 'Wrong task/selector')
    audit.require(selection['object_ids'] == wanted, 'Selector has missing, duplicate or foreign IDs')
    all_ids = [row['id'] for row in graph]
    allocated = [identity for shard in allocation['shards'].values() for identity in shard]
    audit.require(len(graph) == len(allocated) == len(set(allocated)) == len(set(all_ids)) == 1080 and set(allocated) == set(all_ids), 'Graph allocation is not a disjoint1080-object partition')
    rows = [row for row in graph if row['id'] in set(wanted)]
    rows_admit(audit, rows, wanted)
    qualification = audit.load(main / selection['qualification'], QUALIFICATION)
    audit.require(qualification['next_object_manifest'] == selection['source_manifest'], 'Qualification binds another manifest')
    index = audit.load(main / qualification['artifact_index'], qualification['artifact_index_sha256'])['files']
    index = {str((main / name).absolute()): digest for name, digest in index.items()}
    prepared_path = main / qualification['prepared_component']
    prepared = audit.load(prepared_path, index[str(prepared_path)])
    context = prepared['parent_source']
    audit.require(context['source_tree'] == TREE and context['config_sha256'] == CONFIG, 'Source composition/config differs')
    for key in ['descriptor', 'composition_manifest']:
        audit.sha(context[key], context[key + '_sha256'])
    compiler = prepared['compiler']
    audit.require(compiler['sha256'] == COMPILER, 'Compiler descriptor differs')
    audit.sha(compiler['path'], COMPILER)
    declarations, unresolved = [], []
    for row in rows:
        audit.require(row['next_owned_compile_argv_template'][0] == compiler['path'], 'Recipe compiler differs')
        for key in ['bound_source', 'configuration']:
            name, expected = row[key], row[key + '_sha256']
            audit.require(index.get(name) == expected, 'Direct source/config absent from qualified index')
            audit.sha(name, expected)
        roots, forced, auxiliary = includes(row)
        entry = {'id': row['id'], 'recipe_sha256': canonical(row['next_owned_compile_argv_template']),
                 'include_roots_in_order': [{'path': root, 'exists': Path(root).is_dir()} for root in roots],
                 'forced_includes': [], 'literal_direct_includes': []}
        for name in auxiliary:
            audit.require(name in index, 'Auxiliary input is unindexed')
            audit.sha(name, index[name])
        for name in forced:
            candidates = [Path(row['cwd']) / name] + [Path(root) / name for root in roots]
            resolved = next((p for p in candidates if p.is_file()), None)
            audit.require(resolved is not None, 'Forced include is missing: ' + name)
            audit.require(str(resolved) in index, 'Forced include is unindexed')
            entry['forced_includes'].append({'name': name, 'path': str(resolved), 'sha256': audit.sha(resolved, index[str(resolved)])})
        for line_number, line in enumerate(Path(row['bound_source']).read_text().splitlines(), 1):
            match = re.match(r'\s*#\s*include\s*([<"])([^>"]+)[>"]', line)
            if not match:
                continue
            delimiter, name = match.groups()
            candidates = ([Path(row['bound_source']).parent / name] if delimiter == '"' else []) + [Path(root) / name for root in roots]
            resolved = next((p for p in candidates if p.is_file()), None)
            record = {'name': name, 'line': line_number, 'resolved': str(resolved) if resolved else None}
            if resolved:
                # Canonicalize '..' without following directory aliases in the published index.
                path = str(resolved.resolve())
                audit.require(path in index, 'Literal include is not qualified: ' + path)
                record['sha256'] = audit.sha(path, index[path])
            else:
                unresolved.append({'id': row['id'], **record})
            entry['literal_direct_includes'].append(record)
        declarations.append(entry)
    return rows, declarations, unresolved


def controls(audit, rows):
    wanted = [row['id'] for row in rows]
    results = []
    def reject(label, mutate):
        candidate, ids = copy.deepcopy(rows), list(wanted)
        mutate(candidate, ids)
        try:
            rows_admit(audit, candidate, ids)
        except ValueError as error:
            results.append({'name': label, 'outcome': 'expected_rejection', 'error': str(error)})
        else:
            raise ValueError('Negative control was accepted: ' + label)
    reject('duplicate_allocation', lambda rows, ids: ids.__setitem__(1, ids[0]))
    reject('foreign_object', lambda rows, ids: rows[0].__setitem__('id', 'bsd/netboot.o'))
    reject('changed_source_binding', lambda rows, ids: rows[0].__setitem__('bound_source_sha256', '0' * 64))
    reject('output_path_escape', lambda rows, ids: rows[0]['next_owned_compile_argv_template'].__setitem__(-1, '@NEXT_OBJECT_DIR@/../foreign.o'))
    def weaken(rows, ids):
        argv = rows[0]['next_owned_compile_argv_template']
        argv[argv.index('-DXNU_NO_TYPE_BUILTINS=0')] = '-DXNU_NO_TYPE_BUILTINS=1'
    reject('disabled_allocator_metadata', weaken)
    return results


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    wt = Path(__file__).resolve().parents[4]
    output = args.out.absolute()
    if not output.is_relative_to(wt / 'artifacts') or output.exists():
        parser.error('Output must be a new owned worktree artifacts directory')
    output.mkdir(parents=True)
    audit = Audit()
    report = {'task': 'VM-015', 'owner': 'codex-guest-exec-20261106-cz', 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'argv': sys.argv, 'memory_initial': memory(), 'outcome': 'inconclusive', 'objects_produced': 0,
              'compiler_or_generator_invocations': 0, 'actual_dependency_closure_verified': False, 'guest_executed': False}
    code = 2
    try:
        samples = []
        for _ in range(3):
            samples.append(available())
            if samples[-1] < FLOOR:
                raise RuntimeError('Admission requires three MemAvailable samples >=4GiB')
            time.sleep(1)
        report['memory_admission_bytes'] = samples
        selection = audit.load(Path(__file__).with_name('selection.json'))
        audit.sha(__file__)
        audit.sha(sys.executable)
        rows, declarations, unresolved = source_audit(audit, args.main.absolute(), selection)
        report['negative_controls'] = controls(audit, rows)
        write(output / 'selected-manifest.json', rows)
        write(output / 'declared-inputs.json', declarations)
        report.update({'outcome': 'pass', 'scope': 'source preparation only', 'selected_count': len(rows),
                       'language_counts': {language: sum(row['language'] == language for row in rows) for language in sorted({row['language'] for row in rows})},
                       'generated_sources': sum(row['generated_input'] for row in rows), 'unresolved_literal_includes': unresolved,
                       'selected_manifest_sha256': audit.sha(output / 'selected-manifest.json'), 'declared_inputs_sha256': audit.sha(output / 'declared-inputs.json')})
        code = 0
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        report['error'] = repr(error)
        report['outcome'] = 'inconclusive' if isinstance(error, RuntimeError) else 'fail'
    report.update({'exit_code': code, 'checks': audit.checks, 'elapsed_seconds': time.monotonic() - audit.started,
                   'memory_final': memory(), 'files': audit.files, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    write(output / 'report.json', report)
    print(json.dumps({key: report.get(key) for key in ['outcome', 'exit_code', 'checks', 'error', 'selected_count', 'memory_final']}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
