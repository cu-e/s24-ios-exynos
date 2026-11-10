#!/usr/bin/env python3
"""Read-only ld64 runtime map facts; execution/product authority belongs to CU.

All inputs are borrowed CoherentFile snapshots. No file, subprocess, temporary
index, compiler, or linker is opened here. See the pinned source descriptor and
procedure for the precise supported grammar and intentionally incomplete scope.
"""
import hashlib
import json
import re


class LinkMapError(ValueError):
    pass


LINE_LIMIT = 65536
MAP_LIMIT = 256 * 1024**2
JSON_LIMIT = 4 * 1024**2
FILE_LIMIT = 16384
U64 = 2**64 - 1
SOURCE_DESCRIPTOR_SHA256 = '25cff42f8e30836e8f36430775731068d634f548890b30806d4ea6ffdf90ee70'
DRIVER_SOURCE_SHA256 = '609c5e1b81a399d4612940818e6737ef59ae9901603bdf3431e4fdda69831e3d'
LINEAGE = {
    'linker_revision': '904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb',
    'linker_sha256': 'f3cab070fef2c3fb39687e31bab86193f34ab95215fc4dbc8783f2a4f741563e',
    'compiler_sha256': '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82',
    'runtime_revision': '6009708b4367171ccdbf4b5905cb6a803753fe18',
    'runtime_archive_sha256': '67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5',
    'runtime_members_sha256': 'f966a18209553d257d3cc0be093258dc0be5b61aa168fed6baa5b365e8ac6e70',
    'producer_implementation': '0e44b04827b4c3258ed0f7bd724d03acc728bf26',
    'producer_evidence_sha256': 'feaf78a5050c239f144a1ab56e5bfd481c660a3d2e0347a5c33a3088ab48ce18',
    'review_evidence_sha256': '94c4c997585794832515dc085a249c8905feefed750612f12014fb9c392f6693',
}
SHA = re.compile(r'[0-9a-f]{64}\Z')
OBJECT = re.compile(r'\[ *([0-9]{1,5})\] (.+)\Z')
SECTION = re.compile(r'0x([0-9A-F]{8,16})\t0x([0-9A-F]{8,16})\t([^\t]+)\t([^\t]+)\Z')
LIVE = re.compile(r'0x([0-9A-F]{8,16})\t0x([0-9A-F]{8,16})\t\[ *([0-9]{1,5})\] (.+)\Z')
DEAD = re.compile(r'<<dead>> \t0x([0-9A-F]{8,16})\t\[ *([0-9]{1,5})\] (.+)\Z')


def require(condition, message):
    if not condition:
        raise LinkMapError(message)


def text(value):
    require(isinstance(value, str) and 0 < len(value) <= 8192 and
            not any(c in value for c in '\r\n\x00'), 'Invalid bounded text')
    return value


def hash_string(value):
    require(isinstance(value, str) and SHA.fullmatch(value), 'Invalid SHA256')
    return value


def integer(value, maximum=U64):
    require(type(value) is int and 0 <= value <= maximum, 'Invalid unsigned integer')
    return value


def bounded_json(snapshot):
    snapshot.check()
    require(snapshot.length <= JSON_LIMIT, 'JSON exceeds bounded input limit')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    try:
        result = json.loads(b''.join(snapshot.iter_range(0, snapshot.length)),
                            object_pairs_hook=pairs,
                            parse_constant=lambda _: require(False, 'Nonfinite JSON'))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LinkMapError('Malformed bounded JSON') from exc
    snapshot.check()
    return result


def binding(snapshot, expected):
    require(isinstance(expected, dict), 'Missing snapshot binding')
    require(str(snapshot.path) == text(expected.get('path')), 'Snapshot path mismatch')
    digest = snapshot.digest()
    require(digest == hash_string(expected.get('sha256')), 'Snapshot SHA256 mismatch')
    return {'path': str(snapshot.path), 'sha256': digest, 'size': snapshot.length}


def qualify_sources(descriptor_snapshot, source_snapshots, linker_snapshot):
    """Hash borrowed actual/reference source pairs and the pinned linker, no exec."""
    require(descriptor_snapshot.digest() == SOURCE_DESCRIPTOR_SHA256,
            'Unqualified source descriptor')
    descriptor = bounded_json(descriptor_snapshot)
    require(descriptor.get('schema') == 'avf-runtime-linkmap-source-v1', 'Wrong source schema')
    require(all(descriptor.get(key) == value for key, value in LINEAGE.items()),
            'Source descriptor lineage mismatch')
    required = {row[key]: row['sha256'] for row in descriptor['files']
                for key in ('path', 'reference_path')}
    require(set(source_snapshots) == set(required), 'Missing/extra pinned source snapshots')
    for path, digest in required.items():
        require(source_snapshots[path].digest() == digest, 'Pinned actual/reference source changed')
    require(linker_snapshot.digest() == LINEAGE['linker_sha256'], 'Pinned linker changed')
    return {'schema': 'avf-runtime-linkmap-source-witness-v1',
            'source_descriptor_sha256': SOURCE_DESCRIPTOR_SHA256,
            'source_file_count': len(required), 'linker_sha256': LINEAGE['linker_sha256'],
            'execution_started': False, 'product_authority': False}


def qualify_driver_sources(descriptor_snapshot, source_snapshots, compiler_snapshot):
    """Qualify pinned driver forwarding text; this never runs the compiler."""
    require(descriptor_snapshot.digest() == DRIVER_SOURCE_SHA256,
            'Unqualified driver forwarding source descriptor')
    descriptor = bounded_json(descriptor_snapshot)
    require(descriptor.get('schema') == 'avf-runtime-driver-forwarding-source-v1' and
            descriptor.get('compiler_revision') == 'fa9443738c1a18accef4244732ec6d6ee97a8133' and
            descriptor.get('compiler_sha256') == LINEAGE['compiler_sha256'],
            'Driver forwarding source lineage mismatch')
    required = {row[key]: row['sha256'] for row in descriptor['files']
                for key in ('path', 'reference_path')}
    require(set(source_snapshots) == set(required), 'Missing/extra driver source snapshots')
    for path, digest in required.items():
        require(source_snapshots[path].digest() == digest, 'Actual/reference driver source changed')
    require(compiler_snapshot.digest() == LINEAGE['compiler_sha256'], 'Driver compiler bytes changed')
    return {'schema': 'avf-runtime-driver-source-witness-v1',
            'source_descriptor_sha256': DRIVER_SOURCE_SHA256,
            'source_file_count': len(required), 'compiler_sha256': LINEAGE['compiler_sha256'],
            'execution_started': False, 'product_authority': False}


def driver_diagnostic_operands(argv, map_path):
    """Closed canonical diagnostic forwarding subset, not complete/observed ld argv.

    Options.td, LLVM Option/Arg and Darwin AddLinkerInputs are pinned in the
    driver source descriptor. Only adjacent canonical forms are admitted, so a
    filename between separately forwarded tokens cannot become a guessed value.
    """
    require(isinstance(argv, list) and 0 < len(argv) <= FILE_LIMIT, 'Invalid driver argv')
    for value in argv:
        text(value)
        require(not value.startswith('@'), 'Response-file driver argv remains unqualified')
        require(value not in ('--', '-Xclang', '-Xassembler', '-Xpreprocessor'),
                'End-of-options/non-linker forwarding remains outside the qualified recipe')
    result, index = [], 1
    while index < len(argv):
        value = argv[index]
        if value.startswith('-Wl,'):
            operands = [item for item in value[4:].split(',') if item]
            if '-map' in operands or '-why_load' in operands:
                require(operands in (['-map', map_path], ['-why_load']),
                        'Noncanonical/ambiguous diagnostic forwarding')
                result.extend(operands)
        elif value == '-Xlinker':
            require(index + 1 < len(argv), 'Missing separate Xlinker operand')
            operand = argv[index + 1]
            if operand == '-map':
                require(index + 3 < len(argv) and argv[index + 2] == '-Xlinker' and
                        argv[index + 3] == map_path, 'Nonadjacent/incorrect Xlinker map operand')
                result.extend(['-map', map_path])
                index += 2
            elif operand == '-why_load':
                result.append('-why_load')
            index += 1
        elif value in ('-map', '-why_load', '-whyload'):
            raise LinkMapError('Unqualified native driver diagnostic spelling')
        index += 1
    require(result == diagnostic_options(map_path), 'Missing/duplicate/reordered driver diagnostics')
    return result


def validate_filelists(document, argv, snapshots):
    """Check CU-sealed filelist bytes and declared ordered expansion, borrowing FDs."""
    rows = document.get('filelists')
    require(isinstance(rows, list) and 0 < len(rows) <= 16 and isinstance(snapshots, dict),
            'Missing bounded coherent filelists')
    declared, expanded, seen = [], [], set()
    bindings = []
    for row in rows:
        require(isinstance(row, dict), 'Invalid filelist binding')
        path = text(row.get('path'))
        require(path not in declared and path in snapshots, 'Missing/duplicate filelist snapshot')
        declared.append(path)
        bindings.append(binding(snapshots[path], row))
        paths = row.get('ordered_object_paths')
        require(isinstance(paths, list) and 0 < len(paths) <= FILE_LIMIT,
                'Missing bounded ordered filelist expansion')
        observed = []
        for line in lines(snapshots[path]):
            path_entry = text(line)
            require(path_entry not in seen and len(observed) < FILE_LIMIT,
                    'Duplicate/excess filelist object')
            seen.add(path_entry)
            observed.append(path_entry)
        require(paths == observed, 'Sealed filelist expansion differs from actual bytes')
        expanded.extend(observed)
        require(len(expanded) <= FILE_LIMIT, 'Excess total filelist objects')
    require(set(snapshots) == set(declared), 'Unexpected filelist snapshots')
    operands = []
    for index, arg in enumerate(argv):
        if arg == '-filelist':
            require(index + 1 < len(argv), 'Missing driver filelist operand')
            operands.append(argv[index + 1])
        if arg.startswith('-Wl,') and '-filelist' in arg[4:].split(','):
            raise LinkMapError('Use the source-qualified native driver filelist form')
    require(operands == declared, 'Actual driver filelist operands differ from sealed expansion')
    objects = document.get('objects')
    require(isinstance(objects, list), 'Missing objects for sealed filelist')
    paths = [text(row.get('path')) for row in objects if isinstance(row, dict)]
    require(len(paths) == len(objects) and paths[:len(expanded)] == expanded,
            'Object order differs from actual filelist expansion')
    require(all(path in argv for path in paths[len(expanded):]),
            'Additional staged object lacks explicit actual driver operand')
    return bindings


def lines(snapshot):
    require(snapshot.length <= MAP_LIMIT, 'Map/diagnostic exceeds byte budget')
    snapshot.check()
    snapshot.stream.seek(0)
    consumed = 0
    while consumed < snapshot.length:
        raw = snapshot.stream.readline(LINE_LIMIT + 1)
        require(raw and len(raw) <= LINE_LIMIT and raw.endswith(b'\n'),
                'Map/diagnostic line truncated or exceeds limit')
        consumed += len(raw)
        require(consumed <= snapshot.length and b'\x00' not in raw and b'\r' not in raw,
                'Invalid map/diagnostic bytes')
        try:
            yield raw[:-1].decode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise LinkMapError('Non-UTF8 map/diagnostic') from exc
    require(not snapshot.stream.read(1), 'Map/diagnostic grew')
    snapshot.check()


def qualified_catalog(archive, catalog_snapshot):
    """Verify every physical member, including order, without an archive tool."""
    require(archive.length == 219448, 'Unqualified runtime archive size')
    require(archive.digest() == LINEAGE['runtime_archive_sha256'], 'Unqualified runtime archive')
    require(catalog_snapshot.digest() == LINEAGE['runtime_members_sha256'], 'Unqualified member catalog')
    catalog = bounded_json(catalog_snapshot)
    require(isinstance(catalog, list) and len(catalog) == 287, 'Expected qualified287 catalog')
    names = set()
    for row in catalog:
        require(isinstance(row, dict), 'Invalid catalog row')
        name = text(row.get('name'))
        require(name not in names and '/' not in name and '(' not in name and ')' not in name,
                'Duplicate/ambiguous runtime member')
        names.add(name)
        hash_string(row.get('sha256'))
        for field in ('defined', 'undefined'):
            symbols = row.get(field)
            require(isinstance(symbols, list) and len(symbols) <= 4096 and
                    len(set(map(text, symbols))) == len(symbols), 'Invalid catalog symbols')
    require(archive.read_range(0, 8) == b'!<arch>\n', 'Expected ordinary ar archive')
    offset, ordinal, index_seen = 8, 0, False
    while offset < archive.length:
        header = archive.read_range(offset, 60)
        require(len(header) == 60 and header[58:] == b'`\n', 'Malformed ar header')
        try:
            size_field = header[48:58].decode('ascii').strip()
            require(size_field.isdecimal(), 'Invalid ar member size')
            size = int(size_field)
            name_field = header[:16].decode('ascii').rstrip()
        except UnicodeError as exc:
            raise LinkMapError('Invalid ar ASCII header') from exc
        start, end = offset + 60, offset + 60 + size
        require(end <= archive.length, 'Truncated ar body')
        if name_field.startswith('#1/'):
            require(name_field[3:].isdecimal(), 'Invalid BSD name length')
            name_size = int(name_field[3:])
            require(0 < name_size <= 256 and name_size <= size, 'Invalid BSD member name')
            try:
                name = archive.read_range(start, name_size).rstrip(b'\x00').decode('ascii')
            except UnicodeError as exc:
                raise LinkMapError('Invalid ar member name') from exc
            start += name_size
        else:
            name = name_field.removesuffix('/')
        if name in ('__.SYMDEF', '__.SYMDEF SORTED'):
            require(offset == 8 and not index_seen, 'Unexpected ar symbol index')
            index_seen = True
        else:
            require(ordinal < len(catalog), 'Unexpected extra ar member')
            row = catalog[ordinal]
            require(name == row['name'], 'Physical runtime member order/name mismatch')
            digest = hashlib.sha256()
            for block in archive.iter_range(start, end - start):
                digest.update(block)
            require(digest.hexdigest() == row['sha256'], 'Runtime member bytes mismatch')
            ordinal += 1
        offset = end + size % 2
        require(offset <= archive.length, 'Missing ar padding')
        if size % 2:
            require(archive.read_range(end, 1) == b'\n', 'Invalid ar alignment padding')
    require(ordinal == 287 and offset == archive.length and index_seen,
            'Missing qualified runtime members/index')
    archive.check()
    return catalog


def admitted_paths(document, runtime_path, catalog, *, driver=False):
    require(isinstance(document, dict), 'Object list must be an object')
    require(document.get('schema') == ('avf-guest-link-object-list-v2' if driver else
                                     'avf-guest-link-object-list-v1') and
            document.get('source_only') is False, 'Unsealed/source-only object list')
    if driver:
        require(document.get('command_kind') == 'clang-driver' and
                'actual_link_argv' not in document, 'Driver projection must not claim actual ld argv')
    argv = document.get('actual_driver_argv' if driver else 'actual_link_argv')
    require(isinstance(argv, list) and 0 < len(argv) <= FILE_LIMIT,
            'Missing bounded actual linker argv')
    for arg in argv:
        text(arg)
    allowed, archive_rows, object_ids = {}, {}, set()
    path_bytes = 0
    objects = document.get('objects')
    archives = document.get('archives')
    require(isinstance(objects, list) and isinstance(archives, list) and
            len(objects) + len(archives) <= FILE_LIMIT, 'Invalid object/archive list')
    lto_objects = document.get('lto_objects', [])
    require(isinstance(lto_objects, list) and len(lto_objects) <= FILE_LIMIT,
            'Invalid LTO object list')
    for row in objects + lto_objects:
        require(isinstance(row, dict), 'Invalid object row')
        path = text(row.get('path'))
        require(path not in allowed and '(' not in path and ')' not in path,
                'Duplicate/ambiguous object path')
        hash_string(row.get('sha256'))
        if row in objects:
            identity = text(row.get('id'))
            require(identity not in object_ids, 'Duplicate object ID')
            object_ids.add(identity)
        else:
            require(text(row.get('source_argv_operand')) in argv,
                    'Unbound LTO input operand')
            # No current source-qualified LTO output derivation is admitted.
            raise LinkMapError('LTO intermediate output provenance remains unqualified')
        allowed[path] = None
        path_bytes += len(path.encode('utf-8'))
        require(path_bytes <= 8 * 1024**2, 'Admitted path byte budget exceeded')
    runtime_count = 0
    for row in archives:
        require(isinstance(row, dict), 'Invalid archive row')
        path = text(row.get('path'))
        require(path not in archive_rows and path not in allowed and
                '(' not in path and ')' not in path, 'Duplicate/ambiguous archive path')
        digest = hash_string(row.get('sha256'))
        if not driver:
            require(path in argv, 'Archive is absent from actual linker operands')
        members = row.get('members')
        require(isinstance(members, list) and 0 < len(members) <= FILE_LIMIT,
                'Missing bounded archive members')
        runtime = row.get('role') == 'runtime'
        if runtime:
            runtime_count += 1
            require(path == runtime_path and digest == LINEAGE['runtime_archive_sha256'] and
                    len(members) == len(catalog), 'Wrong runtime archive binding')
        seen = set()
        for ordinal, member in enumerate(members):
            require(isinstance(member, dict) and member.get('ordinal') == ordinal and
                    type(member.get('ordinal')) is int, 'Archive member ordinal mismatch')
            name = text(member.get('name'))
            require(name not in seen and not any(c in name for c in '/()'),
                    'Duplicate/ambiguous archive member name')
            seen.add(name)
            hash_string(member.get('sha256'))
            if runtime:
                require(name == catalog[ordinal]['name'] and
                        member['sha256'] == catalog[ordinal]['sha256'], 'Forged runtime member')
            rendered = path + '(' + name + ')'
            require(rendered not in allowed and len(allowed) < FILE_LIMIT,
                    'Duplicate/excess admitted paths')
            allowed[rendered] = (path, ordinal, runtime)
            path_bytes += len(rendered.encode('utf-8'))
            require(path_bytes <= 8 * 1024**2, 'Admitted path byte budget exceeded')
        archive_rows[path] = row
    require(runtime_count == 1, 'Expected exactly one qualified runtime archive')
    return allowed, argv


def diagnostic_options(map_path):
    """Source-derived proposal only; the controller reviews command additions."""
    return ['-map', text(map_path), '-why_load']


def validate(image_snapshot, image_view, contract, *, map_snapshot,
             archive_snapshot, object_list_snapshot, catalog_snapshot,
             driver_source_snapshot=None, filelist_snapshots=None):
    """Return bounded observed facts. Even actual facts confer no product authority.

    CU must authenticate actual command, source contracts and these same open
    snapshots. A caller-written JSON contract never authenticates execution.
    """
    require(isinstance(contract, dict) and contract.get('schema') in
            ('avf-runtime-linkmap-contract-v1', 'avf-runtime-linkmap-contract-v2'),
            'Invalid runtime contract')
    driver = contract['schema'] == 'avf-runtime-linkmap-contract-v2'
    if driver:
        require(contract.get('command_kind') == 'clang-driver' and
                contract.get('selection_scope') == 'all-observed-live-runtime-members',
                'Driver contract requires complete observed runtime selection')
    origin = contract.get('measurement_origin')
    require(origin in ('actual-link', 'synthetic-control') and
            contract.get('source_only') is False, 'Unmeasured/source-only contract')
    require(contract.get('lineage') == LINEAGE, 'Compiler/source/producer lineage mismatch')
    require(contract.get('source_descriptor_sha256') == SOURCE_DESCRIPTOR_SHA256,
            'Unqualified map grammar/options descriptor')
    snapshots = {'image': image_snapshot, 'map': map_snapshot, 'archive': archive_snapshot,
                 'object_list': object_list_snapshot, 'catalog': catalog_snapshot}
    if driver:
        require(driver_source_snapshot is not None and
                driver_source_snapshot.digest() == DRIVER_SOURCE_SHA256,
                'Missing/unqualified driver forwarding source snapshot')
        snapshots['driver_source'] = driver_source_snapshot
    bindings = {key: binding(value, contract.get('bindings', {}).get(key))
                for key, value in snapshots.items()}
    require(image_view.get('sha256') == bindings['image']['sha256'] and
            image_view.get('file_size') == image_snapshot.length and
            image_view.get('filetype') == 2, 'Image view binding/type mismatch')
    catalog = qualified_catalog(archive_snapshot, catalog_snapshot)
    document = bounded_json(object_list_snapshot)
    allowed, argv = admitted_paths(document, str(archive_snapshot.path), catalog, driver=driver)
    atom_queries = contract.get('atom_queries', [])
    require(isinstance(atom_queries, list) and len(atom_queries) <= 512, 'Excess/invalid atom queries')
    query_index = {}
    for number, query in enumerate(atom_queries):
        require(isinstance(query, dict), 'Invalid atom query')
        key = (text(query.get('object_path')), text(query.get('name')))
        require(key[0] in allowed and key not in query_index, 'Unknown/duplicate atom query')
        query_index[key] = number
    queried_live_atoms = []
    proposed = diagnostic_options(str(map_snapshot.path))
    require(contract.get('diagnostic_argv') == proposed, 'Unqualified diagnostic options')
    filelist_bindings = []
    if driver:
        derived = document.get('derived_linker_operands')
        require(isinstance(derived, dict) and derived.get('kind') == 'forwarded-driver-operands-only',
                'Missing explicit source-derived diagnostic projection')
        require(derived.get('source_proof') == {
            'path': str(driver_source_snapshot.path), 'sha256': DRIVER_SOURCE_SHA256},
            'Driver projection source proof mismatch')
        require(derived.get('argv') == driver_diagnostic_operands(argv, str(map_snapshot.path)),
                'Declared projection differs from actual driver forwarding')
        filelist_bindings = validate_filelists(document, argv, filelist_snapshots)
    else:
        require(argv.count('-map') == 1 and argv.index('-map') + 1 < len(argv) and
                argv[argv.index('-map') + 1] == str(map_snapshot.path) and
                argv.count('-why_load') == 1, 'Actual argv lacks exact diagnostic operands')
    output = text(contract.get('output_path'))
    require(argv.count('-o') == 1 and argv.index('-o') + 1 < len(argv) and
            argv[argv.index('-o') + 1] == output and output == str(image_snapshot.path),
            'Output path/argv mismatch')
    required = contract.get('required_members', [] if driver else None)
    require(isinstance(required, list) and (0 if driver else 1) <= len(required) <= 287 and
            len(set(map(lambda n: integer(n, 286), required))) == len(required),
            'Missing/duplicate/out-of-range required runtime members')
    architecture = contract.get('architecture')
    require(architecture == 'arm64', 'Unqualified runtime architecture')
    section_view = image_view.get('sections')
    require(isinstance(section_view, list) and len(section_view) <= 4096, 'Invalid bounded sections')
    image_sections = set()
    for section in section_view:
        key = (text(section['segment']), text(section['name']),
               integer(section['address']), integer(section['size']))
        require(key[2] + key[3] <= U64 and key not in image_sections, 'Invalid duplicate image section')
        image_sections.add(key)
    iterator = iter(lines(map_snapshot))
    def take(expected):
        require(next(iterator, None) == expected, 'Missing/out-of-order ld64 header: ' + expected)
    take('# Path: ' + output)
    take('# Arch: ' + architecture)
    take('# Object files:')
    files, file_paths, observed_paths, previous = [], [], set(), {}
    runtime_ids = {}
    map_path_bytes = 0
    for line in iterator:
        if line == '# Sections:':
            break
        match = OBJECT.fullmatch(line)
        require(match and len(files) < FILE_LIMIT, 'Malformed/excess map file row')
        identity, path = int(match[1]), match[2]
        map_path_bytes += len(path.encode('utf-8'))
        require(map_path_bytes <= 8 * 1024**2, 'Map path byte budget exceeded')
        require(identity == len(files) and path not in observed_paths,
                'Duplicate/noncontiguous map file ID/path')
        observed_paths.add(path)
        file_paths.append(path)
        if identity == 0:
            require(path == 'linker synthesized', 'Missing synthesized file0')
            files.append(None)
            continue
        require(path in allowed, 'Map references unadmitted object/archive member')
        facts = allowed[path]
        files.append(facts)
        if facts:
            archive_path, ordinal, runtime = facts
            require(ordinal > previous.get(archive_path, -1), 'Map archive member order mismatch')
            previous[archive_path] = ordinal
            if runtime:
                runtime_ids[identity] = ordinal
    else:
        raise LinkMapError('Missing map sections')
    require(files, 'Missing object table')
    take('# Address\tSize    \tSegment\tSection')
    sections = []
    for line in iterator:
        if line == '# Symbols:':
            break
        match = SECTION.fullmatch(line)
        require(match, 'Malformed ld64 section row')
        address, size = int(match[1], 16), int(match[2], 16)
        key = (match[3], match[4], address, size)
        require(key in image_sections and key not in sections, 'Map/image section mismatch')
        sections.append(key)
    else:
        raise LinkMapError('Missing map symbols')
    require(sections, 'No mapped image section')
    take('# Address\tSize    \tFile  Name')
    live_counts, dead_counts, selected_symbols = {}, {}, {}
    live_rows = dead_rows = 0
    dead_phase = False
    for line in iterator:
        if line == '' and not dead_phase:
            take('# Dead Stripped Symbols:')
            take('#        \tSize    \tFile  Name')
            dead_phase = True
            continue
        match = (DEAD if dead_phase else LIVE).fullmatch(line)
        require(match, 'Malformed ld64 symbol/phase')
        if dead_phase:
            size, identity, name = int(match[1], 16), int(match[2]), match[3]
            dead_rows += 1
        else:
            address, size, identity, name = int(match[1], 16), int(match[2], 16), int(match[3]), match[4]
            require(address + size <= U64 and any(
                base <= address and address + size <= base + length
                for _, _, base, length in sections), 'Live atom outside mapped section')
            live_rows += 1
        require(identity < len(files), 'Unknown/out-of-range map symbol file ID')
        query_key = (file_paths[identity], name)
        if not dead_phase and query_key in query_index:
            require(len(queried_live_atoms) < 4096, 'Excess queried map atom matches')
            queried_live_atoms.append({'query_index':query_index[query_key],
                'object_path':query_key[0], 'file_id':identity, 'name':name,
                'address':address, 'size':size})
        if identity not in runtime_ids:
            continue
        ordinal = runtime_ids[identity]
        counts = dead_counts if dead_phase else live_counts
        counts[ordinal] = counts.get(ordinal, 0) + 1
        if dead_phase or name not in catalog[ordinal]['defined']:
            continue
        symbol = image_view['external_symbols'].get(name)
        require(symbol is not None and symbol.get('undefined') is False and
                symbol.get('value') == address and symbol.get('section', 0) > 0 and
                symbol.get('type', 0) & 0x0e == 0x0e, 'Runtime symbol map/image mismatch')
        section_number = integer(symbol['section'], len(section_view))
        own_section = section_view[section_number - 1]
        require(own_section['address'] <= address and
                address + size <= own_section['address'] + own_section['size'],
                'Runtime symbol outside its final nlist section')
        require(name not in selected_symbols, 'Duplicate runtime symbol attribution')
        require(len(selected_symbols) < 4096, 'Excess runtime symbol witnesses')
        selected_symbols[name] = {'name': name, 'member_ordinal': ordinal,
                                  'address': address, 'size': size}
    require(set(required) <= set(live_counts), 'Required runtime member lacks live atom')
    providers = {row['member_ordinal'] for row in selected_symbols.values()}
    require(set(required) <= providers, 'Required runtime member lacks final external provider')
    selected = sorted(live_counts)
    defined = {symbol for ordinal in selected for symbol in catalog[ordinal]['defined']}
    imports = sorted({symbol for ordinal in selected for symbol in catalog[ordinal]['undefined']} - defined)
    imported = []
    for name in imports:
        symbol = image_view['external_symbols'].get(name)
        imported.append({'name': name, 'present_defined': bool(symbol is not None and
                         symbol.get('undefined') is False),
                         'address': symbol.get('value') if symbol else None})
    for snapshot in snapshots.values():
        snapshot.check()
    if driver:
        for snapshot in filelist_snapshots.values():
            snapshot.check()
    return {'schema': 'avf-runtime-linkmap-witness-v2' if driver else 'avf-runtime-linkmap-witness-v1',
            'measurement_origin': origin,
            'source_only': False, 'product_authority': False,
            'actual_execution_authenticated': False,
            'qualified_for_actual_selection': False,
            'scope': 'actual-byte-facts-require-controller-authentication' if origin == 'actual-link'
                     else 'synthetic-control-no-actual-selection-credit',
            'lineage': dict(LINEAGE), 'bindings': bindings,
            'command_kind': 'clang-driver' if driver else 'direct-linker',
            'derived_linker_operands': document.get('derived_linker_operands') if driver else None,
            'observed_linker_child_argv_claimed': False,
            'driver_recipe_authentication_owned_by_controller': True,
            'filelist_bindings': filelist_bindings,
            'atom_queries': atom_queries, 'queried_live_atoms': queried_live_atoms,
            'queried_atom_qualification': False,
            'diagnostic_argv': proposed, 'map_file_count': len(files),
            'map_live_atom_count': live_rows, 'map_dead_atom_count': dead_rows,
            'members': [{'ordinal': ordinal, 'name': catalog[ordinal]['name'],
                         'sha256': catalog[ordinal]['sha256'],
                         'live_atom_count': live_counts.get(ordinal, 0),
                         'dead_atom_count': dead_counts.get(ordinal, 0)}
                        for ordinal in sorted(set(runtime_ids.values()))],
            'required_members': required,
            'selection_scope': 'all-observed-live-runtime-members' if driver else 'required-members-v1',
            'selected_live_member_ordinals': selected,
            'empty_runtime_selection': not selected,
            'selected_member_symbols': [dict(ordinal=ordinal, name=catalog[ordinal]['name'],
                sha256=catalog[ordinal]['sha256'], defined=list(catalog[ordinal]['defined']),
                undefined=list(catalog[ordinal]['undefined'])) for ordinal in selected],
            'selected_symbols': sorted(selected_symbols.values(), key=lambda row: row['name']),
            'selected_member_import_candidates': imported,
            'import_closure_measured': False, 'lto_retention_measured': False}


def parse_load_diagnostics(snapshot, runtime_path, catalog):
    """Optional stdout load reasons, never a proof of retained code or closure."""
    prefix = text(runtime_path) + '('
    names = {row['name']: ordinal for ordinal, row in enumerate(catalog)}
    result = []
    for line in lines(snapshot):
        if prefix not in line:
            continue
        reason, separator, rendered = line.partition('forced load of ')
        require(separator and rendered.startswith(prefix) and rendered.endswith(')'),
                'Unknown runtime archive diagnostic grammar')
        require(reason in ('', '-ObjC ') or (reason.endswith(' ') and
                ' ' not in reason[:-1] and reason[:-1]), 'Unknown forced-load reason')
        name = rendered[len(prefix):-1]
        require(name in names and len(result) < 287, 'Unknown/excess loaded runtime member')
        require(all(row['member_ordinal'] != names[name] for row in result),
                'Duplicate loaded runtime diagnostic')
        result.append({'member_ordinal': names[name], 'name': name,
                       'reason': reason.rstrip(), 'retention_credit': False})
    return {'schema': 'avf-runtime-load-diagnostic-v1', 'members': result,
            'product_authority': False, 'retention_credit': False}
