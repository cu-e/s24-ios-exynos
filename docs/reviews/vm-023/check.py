#!/usr/bin/env python3
"""Bounded read-only byte/evidence review; never invokes a compiler or child."""
import argparse
import datetime
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import shlex
import signal
import struct
import sys
import time

sys.dont_write_bytecode = True
FREEZE = 'feaf78a5050c239f144a1ab56e5bfd481c660a3d2e0347a5c33a3088ab48ce18'
TOOL = '847ebaed1349b8139f0df55490b61afe4c966d017731314c61ade19a6e66a197'
PARSER = '7382b6a59df4d11fbf574997678c76fc7e9813989b76809f131270c1cc90e511'
GIB = 1024**3


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def memory():
    result = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            result[line.split(':')[0]] = int(line.split()[1])*1024
    result['inherited_ru_maxrss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    return result


def available():
    return next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                if line.startswith('MemAvailable:'))


class Review:
    def __init__(self, out):
        self.out = out
        self.count = 0
        self.files = {}
        self.controls = []

    def check(self, value, message):
        self.count += 1
        if not value:
            raise ValueError(message)

    def guard(self):
        if available() < 4*GIB or memory()['VmHWM'] > 256*1024**2:
            raise RuntimeError('Review stopped at MemAvailable/current-image memory boundary')

    def sha(self, path, expected=None):
        self.guard()
        path = Path(path)
        before = path.stat()
        with path.open('rb') as stream:
            value = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = path.stat()
        self.check((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                   (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                   'Input changed while hashing: '+str(path))
        if expected is not None:
            self.check(value == expected, 'Frozen hash differs: '+str(path))
        self.files[str(path)] = value
        return value

    def load(self, path, expected=None):
        self.sha(path, expected)
        self.check(Path(path).stat().st_size < 64*1024**2, 'Oversized review JSON')
        with Path(path).open() as stream:
            return json.load(stream)

    def reject(self, name, action, raw=None):
        item = {'name': name, 'expected': 'ValueError'}
        if raw is not None:
            path = self.out/'cases'/(name+'.bin')
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(raw)
            item.update(input=str(path), input_sha256=hashlib.sha256(raw).hexdigest(), input_bytes=len(raw))
        try:
            action()
        except ValueError as error:
            item.update(outcome='expected_rejection', error=str(error))
            self.controls.append(item)
            self.count += 1
        else:
            item['outcome'] = 'unexpected_acceptance'
            self.controls.append(item)
            raise ValueError('Negative control accepted: '+name)


def independent_members(data, review):
    """Walk ar framing independently of the production parser."""
    review.check(data.startswith(b'!<arch>\n'), 'Independent ar signature')
    position = 8
    result = []
    while position < len(data):
        header = data[position:position+60]
        review.check(len(header) == 60 and header[58:60] == b'`\n', 'Independent ar header extent')
        size_text = header[48:58].decode('ascii').strip()
        review.check(size_text.isdecimal(), 'Independent ar decimal size')
        size = int(size_text)
        end = position+60+size
        review.check(end <= len(data), 'Independent ar member extent')
        body = data[position+60:end]
        name = header[:16].decode('ascii').strip()
        if name.startswith('#1/'):
            extent = int(name[3:])
            review.check(extent <= size, 'Independent BSD name bound')
            name = body[:extent].rstrip(b'\0').decode('utf-8')
            body = body[extent:]
        else:
            name = name.removesuffix('/')
        if name and name != '/' and not name.startswith('__.SYMDEF'):
            result.append({'name': name, 'body': body, 'header_offset': position})
        position = end+(size & 1)
    review.check(position == len(data), 'Independent archive exact final extent')
    return result


def independent_object(body, review):
    review.check(len(body) >= 32, 'Independent Mach-O minimum header')
    magic, cpu, subtype, kind, count, extent, _, _ = struct.unpack_from('<8I', body)
    review.check((magic, cpu, subtype, kind) == (0xfeedfacf, 0x100000c, 0, 1), 'Independent ARM64 MH_OBJECT identity')
    cursor = 32
    platform = []
    table = None
    table_command = None
    platform_offset = None
    for _ in range(count):
        review.check(cursor+8 <= 32+extent <= len(body), 'Independent load command bound')
        command, size = struct.unpack_from('<II', body, cursor)
        review.check(size >= 8 and cursor+size <= 32+extent, 'Independent load command size')
        if command == 0x25:
            platform.append((2, struct.unpack_from('<I', body, cursor+8)[0]))
            platform_offset = cursor+8
        elif command == 0x32:
            platform.append(struct.unpack_from('<II', body, cursor+8))
            platform_offset = cursor+12
        elif command == 2:
            review.check(table is None, 'Independent unique symbol table')
            table = struct.unpack_from('<4I', body, cursor+8)
            table_command = cursor
        cursor += size
    review.check(cursor == 32+extent and platform == [(2, 0x100500)], 'Independent exact iOS16.5 platform')
    defined, undefined = set(), set()
    if table is not None:
        symoff, count, stroff, strsize = table
        review.check(symoff+16*count <= len(body) and stroff+strsize <= len(body), 'Independent symbol/string table extents')
        for index in range(count):
            name, flags, _, _, value = struct.unpack_from('<IBBHQ', body, symoff+index*16)
            if flags & 0xe0 or not flags & 1:
                continue
            review.check(name < strsize, 'Independent external name index')
            tail = body[stroff+name:stroff+strsize]
            review.check(b'\0' in tail, 'Independent terminated symbol name')
            symbol = tail.split(b'\0', 1)[0].decode('utf-8')
            (defined if flags & 0x0e or value else undefined).add(symbol)
    return defined, undefined, {'table': table, 'table_command': table_command, 'platform_offset': platform_offset}


def lookup(text, linker, archive, expected):
    commands = [shlex.split(line) for line in text.splitlines() if line.lstrip().startswith('"')]
    if len(commands) != 1:
        raise ValueError('Exactly one recorded backend command is required')
    argv = commands[0]
    if not argv or argv[0] != linker or '-cc1' in argv or '-lcc_kext' in argv or any(a.startswith('@') for a in argv):
        raise ValueError('Recorded backend is not the exact interpreted linker lookup')
    libraries = [a for a in argv if a.endswith('libclang_rt.cc_kext_ios.a')]
    if libraries != ([archive] if expected else []):
        raise ValueError('Exact pinned archive occurrence differs from requested admission')
    return argv


def inspect(review, main, producer):
    maintained = review.load(producer/'docs/procedures/avf-guest-compiler-runtime/evidence.json', FREEZE)
    review.sha(producer/'tools/build/avf_guest_compiler_runtime.py', TOOL)
    review.sha(producer/'fixtures/public/avf-guest-compiler-runtime/inputs.json', 'ef56568454f475ebafc77c9043b84f82237cb55bf80b4fc448b29186ddbee9cc')
    pins = maintained['source_and_tool_pins']
    paths = {}
    for key, pin in pins['inputs'].items():
        path = main/pin['path']
        review.check(path.stat().st_size == pin['size'], 'Pinned input size: '+key)
        review.sha(path, pin['sha256'])
        paths[key] = path
    index = review.load(main/maintained['artifact_index']['path'], maintained['artifact_index']['sha256'])
    # Producer index is inspected according to its actual recorded schema.
    indexed = index['files'] if 'files' in index else index
    for name, digest in indexed.items():
        review.sha(main/name, digest)
    final = producer/'artifacts/avf-guest-compiler-runtime/final-0e44b04'
    final_report = review.load(final/'report.json', maintained['sha256'][str((final/'report.json').relative_to(main))])
    expected_members = review.load(paths['members'])
    recipes = review.load(final/'runtime-recipes.json', '77cf712bf78bc9ee4c6df8db1bb81c2bd39173c2b39f368236b980468e2f8216')
    original = review.load(paths['original_report'])
    corrected = review.load(paths['corrected_report'])
    descriptor = review.load(paths['descriptor'])
    dependencies = review.load(paths['original_dependencies'])
    review.check(original['outcome'] == 'fail' and 'integer-semantics' in original['error'], 'Historical runtime semantics failure remains explicit')
    review.check(corrected['outcome'] == 'pass', 'Accepted unsigned-shift correction remains passing')
    parser_path = producer/'tools/build/xnu_cc_kext.py'
    review.sha(parser_path, PARSER)
    spec = importlib.util.spec_from_file_location('rev043_frozen_parser', parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    with paths['archive'].open('rb') as stream:
        archive = stream.read(1024*1024)
        review.check(not stream.read(1), 'Bounded actual archive input')
    frames = independent_members(archive, review)
    parsed = parser.archive_members(archive)
    review.check(len(frames) == len(parsed) == len(expected_members) == len(recipes) == 287, 'Exact287 member and recipe coverage')
    definitions, imports = set(), set()
    representative = None
    member_results = []
    for frame, pair, expected in zip(frames, parsed, expected_members):
        name, body = frame['name'], frame['body']
        review.check((name, body) == pair and name == expected['name'], 'Independent/production ordered member bytes agree')
        review.check(hashlib.sha256(body).hexdigest() == expected['sha256'], 'Genuine member SHA256: '+name)
        defined, undefined, metadata = independent_object(body, review)
        review.check((defined, undefined) == parser.object_symbols(body), 'Independent/production actual symbols agree: '+name)
        review.check(sorted(defined) == expected['defined'] and sorted(undefined) == expected['undefined'], 'Accepted member symbol boundary: '+name)
        definitions.update(defined); imports.update(undefined)
        if representative is None and metadata['table'] and metadata['table'][1] and defined:
            representative = (body, metadata)
        member_results.append({'name': name, 'sha256': expected['sha256'], 'defined': len(defined), 'undefined': len(undefined)})
    external = sorted(imports-definitions)
    review.check(len(external) == 47 and external == final_report['archive']['external_imports'], 'Exact47 unresolved external archive names')
    witnesses = {}
    for record in [original, corrected]:
        for command in record['commands']:
            argv = command['argv']
            if '-c' in argv and '-o' in argv:
                output = Path(argv[argv.index('-o')+1])
                if output.parent.name == 'objects':
                    witnesses[output.name] = command
    review.check(set(witnesses) == set(recipes) == {row['name'] for row in expected_members}, 'Exact287 original/corrected witness names')
    categories = {'canonical_source': 0, 'generated': 0, 'corrected': 0}
    for expected in expected_members:
        name = expected['name']; recipe = recipes[name]; witness = witnesses[name]; argv = recipe['argv']
        review.check(recipe['argv'] == witness['argv'] and recipe['cwd'] == witness['cwd'] and recipe['exit_code'] == witness['exit_code'] == 0,
                     'Exact existing compile command witness: '+name)
        review.check(argv[0] == str(paths['compiler']) and argv[argv.index('-target')+1] == pins['target'], 'Witness qualified compiler/target: '+name)
        source = Path(argv[argv.index('-c')+1]); output = Path(argv[argv.index('-o')+1])
        source_hash = review.sha(source, recipe['source_sha256'])
        review.sha(output, expected['sha256'])
        source_pin = recipe['source_pin']
        if 'derivative_of' in source_pin:
            categories['corrected'] += 1
            review.check(source_hash == descriptor['source_correction']['patched_sha256'] and source_pin['derivative_of'] == descriptor['source_correction']['base_sha256'], 'Exact accepted correction provenance')
        elif 'generated_by' in source_pin:
            categories['generated'] += 1
            review.check(source_hash == source_pin['sha256'] == dependencies[str(source.relative_to(main))], 'Generated wrapper dependency/source binding')
        else:
            categories['canonical_source'] += 1
            key = str(source).split('/source/', 1)[1]
            review.check(source_hash == source_pin['sha256'] == original['runtime_source_inputs'][key]['sha256'], 'Canonical runtime source binding')
            if 'git_blob_sha1' in source_pin:
                digest = hashlib.sha1(('blob '+str(source.stat().st_size)+'\0').encode())
                with source.open('rb') as stream:
                    for block in iter(lambda: stream.read(65536), b''):
                        digest.update(block)
                review.check(digest.hexdigest() == source_pin['git_blob_sha1'], 'Canonical runtime Git blob binding')
    review.check(categories == {'canonical_source': 161, 'generated': 125, 'corrected': 1}, 'Source witness categories remain exact')
    review.check(final_report['commands'] == maintained['final_driver_commands'], 'Existing final driver records agree with maintained freeze')
    linker, archive_path = str(paths['linker']), str(paths['archive'])
    lookup_results = []
    for index, command in enumerate(final_report['commands']):
        expected = index == 0
        review.check(command['exit_code'] == 0 and not command['stop_reason'] and not command['remaining_live_owned_children'], 'Actual recorded driver exit/cleanup')
        review.check('-###' in command['argv'] and '-x' in command['argv'] and command['argv'][command['argv'].index('-x')+1] == 'object' and '/dev/null' in command['argv'], 'Recorded dry-run-only nonprovider input')
        review.sha(command['stdout'], command['stdout_sha256']); review.sha(command['stderr'], command['stderr_sha256'])
        text = Path(command['stderr']).read_text()
        backend = lookup(text, linker, archive_path, expected)
        review.check(backend == command['emitted_backend_argv'], 'Independent recorded stderr parsing agrees')
        review.check(not Path(command['argv'][command['argv'].index('-o')+1]).exists(), 'Dry-run did not leave declared output')
        root = Path(command['argv'][command['argv'].index('-resource-dir')+1])
        review.check(root.exists() == expected, 'Existing versus absent resource root remains explicit')
        lookup_results.append({'expected_archive': expected, 'exit_code': 0, 'archive_occurrences': backend.count(archive_path), 'stderr_sha256': command['stderr_sha256']})
    positive, missing = [Path(command['stderr']).read_text() for command in final_report['commands']]
    review.reject('missing_root_exit_zero_is_not_positive', lambda: lookup(missing, linker, archive_path, True))
    review.reject('duplicate_archive_token', lambda: lookup(positive.rstrip()+' '+shlex.quote(archive_path)+'\n', linker, archive_path, True))
    review.reject('foreign_same_basename_archive', lambda: lookup(positive.replace(archive_path, '/owned/foreign/libclang_rt.cc_kext_ios.a'), linker, archive_path, True))
    bad = archive[:-1]
    review.reject('truncated_genuine_archive', lambda: parser.archive_members(bad), bad)
    bad = bytearray(archive); offset = frames[0]['header_offset']; bad[offset+48:offset+58] = b'-000000001'
    review.reject('negative_member_extent', lambda: parser.archive_members(bad), bad)
    bad = bytearray(archive); bad[offset:offset+16] = b'#1/999999       '
    review.reject('oversized_bsd_name_extent', lambda: parser.archive_members(bad), bad)
    body, metadata = representative
    for name, at, value in [('foreign_cpu', 4, 0x1000007), ('wrong_ios_version', metadata['platform_offset'], 0xe0000),
                            ('oversized_symbol_count', metadata['table_command']+12, 0xffffffff)]:
        bad = bytearray(body); struct.pack_into('<I', bad, at, value)
        review.reject(name, lambda bad=bad: parser.object_symbols(bad), bad)
    bad = bytearray(body); symoff, _, _, strsize = metadata['table']
    # Target a real external symbol; local/debug symbols are deliberately ignored.
    target = next(symoff+16*n for n in range(metadata['table'][1]) if not bad[symoff+16*n+4] & 0xe0 and bad[symoff+16*n+4] & 1)
    struct.pack_into('<I', bad, target, strsize)
    review.reject('external_name_outside_strings', lambda: parser.object_symbols(bad), bad)
    guest = review.load(paths['guest_manifest'])
    review.check(len(guest) == 1080 and final_report['guest_recipe_namespace']['count'] == 1080, 'Original immutable guest template profile identity')
    link_root = archive_path.split('/lib/darwin/', 1)[0]
    representatives = []
    for language in ['c', 'c++', 'asm']:
        row = next(row for row in guest if row['language'] == language)
        argv = row['next_owned_compile_argv_template']
        review.check(argv[argv.index('-target')+1] == pins['target'] and all(link_root not in token for token in argv), 'Representative compile header/runtime separation')
        representatives.append({'id': row['id'], 'language': language, 'link_resource_root_absent': True})
    del guest
    gc.collect()
    for path, digest in list(review.files.items()):
        review.sha(path, digest)
    return {'members': 287, 'member_results': member_results, 'source_witness_categories': categories,
            'external_imports': external, 'external_import_count': len(external), 'existing_lookup': lookup_results,
            'compile_namespace_representatives': representatives, 'original_guest_manifest_sha256': pins['inputs']['guest_manifest']['sha256'],
            'failed_producer_attempts_retained': [(command['report'], command['outcome']) for command in maintained['commands'] if command['outcome'] != 'pass'],
            'compiler_or_driver_invoked': False, 'archive_or_link_tool_invoked': False, 'child_processes_started': 0}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--main', type=Path, required=True)
    cli.add_argument('--producer', type=Path, required=True)
    cli.add_argument('--out', type=Path, required=True)
    args = cli.parse_args()
    scope = Path(__file__).resolve().parent
    out = args.out.resolve()
    if not out.is_relative_to(scope/'runs') or out.exists():
        cli.error('Fresh output beneath this owned review directory is required')
    out.mkdir(parents=True)
    review = Review(out)
    report = {'task': 'REV-043', 'owner': 'codex-review-guest-runtime-20261106-ex', 'kind': 'host-test', 'origin': 'local-host',
              'recorded_at': stamp(), 'argv': [sys.executable, *sys.argv], 'memory_initial': memory(), 'outcome': 'inconclusive'}
    def deadline(signum, frame):
        raise TimeoutError('Bounded 90-second review deadline')
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 90)
    started = time.monotonic()
    code = 1
    try:
        samples = []
        for n in range(3):
            samples.append(available())
            review.check(samples[-1] >= 4*GIB, 'Three stable >=4GiB samples required')
            if n < 2:
                time.sleep(1)
        report['admission_mem_available_bytes'] = samples
        review.sha(__file__)
        review.sha(sys.executable)
        report['results'] = inspect(review, args.main.resolve(), args.producer.resolve())
        review.guard()
        report['outcome'] = 'pass'
        code = 0
    except Exception as error:
        report.update(error=repr(error), outcome='inconclusive' if isinstance(error, (TimeoutError, RuntimeError)) else 'fail')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report.update(exit_code=code, checks=review.count, controls=review.controls, files=review.files,
                      memory_final=memory(), elapsed_seconds=time.monotonic()-started, finished_at=stamp())
        with (out/'report.json').open('x') as stream:
            json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps({key: report.get(key) for key in ['outcome', 'error', 'checks', 'elapsed_seconds', 'memory_final']}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
