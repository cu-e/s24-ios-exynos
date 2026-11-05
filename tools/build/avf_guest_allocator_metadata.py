#!/usr/bin/env python3
"""Read-only, bounded inspection of frozen guest allocator metadata witnesses."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_compiler(path, expected):
    require(digest(path) == expected, 'wrong compiler provenance')


def macho(path):
    """Parse a small real witness, rejecting malformed extents before slicing."""
    require(path.stat().st_size <= 32 * 1024 * 1024, 'object exceeds inspection bound')
    with path.open('rb') as stream:
        data = stream.read()
    def extent(offset, size):
        require(0 <= offset <= len(data) and 0 <= size <= len(data) - offset,
                'invalid Mach-O extent')
        return data[offset:offset + size]
    require(len(data) >= 32, 'short Mach-O header')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from('<8I', data)
    require((magic, cpu, kind) == (0xfeedfacf, 0x100000c, 1), 'not an ARM64 Mach-O object')
    extent(32, size)
    at, sections, symtab = 32, [], None
    for _ in range(count):
        require(at + 8 <= 32 + size, 'load command header exceeds table')
        cmd, width = struct.unpack_from('<II', data, at)
        require(width >= 8 and at + width <= 32 + size, 'invalid load command')
        if cmd == 25:
            require(width >= 72, 'short segment command')
            nsects = struct.unpack_from('<I', data, at + 64)[0]
            require(72 + 80 * nsects <= width, 'invalid section table')
            for i in range(nsects):
                pos = at + 72 + 80 * i
                name, segment, address, length, offset, align, reloff, nreloc, attrs, r1, r2, r3 = struct.unpack_from('<16s16sQQ8I', data, pos)
                name, segment = [x.split(b'\0', 1)[0].decode('ascii') for x in (name, segment)]
                # S_ZEROFILL and S_THREAD_LOCAL_ZEROFILL have no file payload.
                payload = b'' if attrs & 0xff in (1, 12, 18) else extent(offset, length)
                extent(reloff, nreloc * 8)
                sections.append(dict(section=name, segment=segment, address=address,
                                     size=length, offset=offset, align=align, flags=attrs,
                                     header_offset=pos, relocation_offset=reloff,
                                     relocation_count=nreloc, sha256=hashlib.sha256(payload).hexdigest()))
        if cmd == 2:
            require(width == 24 and symtab is None, 'invalid/duplicate symbol table')
            symtab = struct.unpack_from('<4I', data, at + 8)
        at += width
    require(at == 32 + size and symtab is not None, 'incomplete Mach-O command table')
    off, count, stroff, strsize = symtab
    symbols, strings = [], extent(stroff, strsize)
    extent(off, count * 16)
    for i in range(count):
        strx, typ, section, desc, value = struct.unpack_from('<IBBHQ', data, off + i * 16)
        require(strx < len(strings), 'symbol string index out of range')
        end = strings.find(b'\0', strx)
        require(end >= 0, 'unterminated symbol name')
        symbols.append(dict(name=strings[strx:end].decode('utf-8'), type=typ,
                            section=section, description=desc, value=value))
    for section in sections:
        relocations = []
        for i in range(section['relocation_count']):
            address, bits = struct.unpack_from('<iI', data, section['relocation_offset'] + i * 8)
            require(address >= 0, 'scattered/negative ARM64 relocation unsupported')
            number, external = bits & 0xffffff, bool(bits & (1 << 27))
            length = 1 << ((bits >> 25) & 3)
            require(address + length <= section['size'], 'relocation exceeds section')
            if bits >> 28 == 10:  # ARM64_RELOC_ADDEND stores an addend, not a target index.
                require(not external and i + 1 < section['relocation_count'], 'invalid addend relocation')
                next_address, next_bits = struct.unpack_from('<iI', data, section['relocation_offset'] + (i + 1) * 8)
                require(next_address == address and next_bits >> 28 in (3, 4), 'unpaired addend relocation')
                relocations.append(dict(address=address, type=10, addend=number if number < 0x800000 else number - 0x1000000))
                continue
            require(number < len(symbols) if external else 0 < number <= len(sections),
                    'relocation target out of range')
            relocations.append(dict(address=address, length=length, pcrel=bool(bits & (1 << 24)),
                                    type=bits >> 28, external=external, target_index=number,
                                    target=symbols[number]['name'] if external else sections[number - 1]['section']))
        section['relocations'] = relocations
    return dict(sections=sections, symbols=symbols)


def metadata(path):
    parsed = macho(path)
    rows = [s for s in parsed['sections'] if s['section'] == '__kalloc_type']
    require(len(rows) == 1, 'missing/duplicate allocator section')
    row = rows[0]
    require(row['segment'] == '__DATA_CONST' and row['size'] == 192, 'allocator extent/segment changed')
    require(row['flags'] == 0x08000000 and row['align'] == 3, 'allocator live_support/alignment changed')
    require(row['relocation_count'] == 6, 'allocator relocation table stripped/changed')
    require(all(r['type'] == 0 and r['length'] == 8 and not r['pcrel'] for r in row['relocations']),
            'allocator pointer relocation contract changed')
    require({r['address'] for r in row['relocations']} == {16, 32, 80, 96, 144, 160},
            'allocator name/signature relocation positions changed')
    targets = []
    with path.open('rb') as stream:
        for reloc in row['relocations']:
            require(reloc['external'], 'allocator symbol relocation changed')
            symbol = parsed['symbols'][reloc['target_index']]
            require(symbol['type'] & 0x0e == 0x0e and 0 < symbol['section'] <= len(parsed['sections']),
                    'allocator metadata pointer target is undefined')
            section = parsed['sections'][symbol['section'] - 1]
            delta = symbol['value'] - section['address']
            require(0 <= delta < section['size'], 'allocator string target out of range')
            stream.seek(section['offset'] + delta)
            raw = stream.read(min(1024, section['size'] - delta))
            require(b'\0' in raw, 'allocator name/signature has no bounded terminator')
            value = raw.split(b'\0', 1)[0].decode('ascii')
            targets.append(dict(address=reloc['address'], symbol=symbol['name'], section=section['section'], string=value))
    row['resolved_metadata_strings'] = targets
    return row


def run(args, report):
    main = args.main.resolve()
    descriptor = Path(__file__).resolve().parents[2] / 'fixtures/public/avf-guest-allocator-metadata/inputs.json'
    inputs = json.loads(descriptor.read_text())
    report['descriptor_sha256'] = digest(descriptor)
    report['inputs'] = []
    def bound(item):
        path = main / item['path']
        actual = digest(path)
        report['inputs'].append(dict(path=str(path), sha256=actual))
        require(actual == item['sha256'], 'input hash mismatch: ' + str(path))
        return path
    paths = {key: bound(item) for key, item in inputs['files'].items()}
    header = paths['kalloc_header'].read_text()
    loader = paths['loader_header'].read_text()
    require('"regular, live_support"' in header and '#define KALLOC_TYPE_SEGMENT "__DATA_CONST"' in header,
            'primary allocator section placement contract changed')
    require('S_ATTR_LIVE_SUPPORT' in loader and '0x08000000' in loader,
            'primary Mach-O live-support definition changed')
    require('ARM64_RELOC_ADDEND' in paths['relocation_header'].read_text(), 'primary addend relocation contract changed')
    require('LDFLAGS_KERNEL_STRIP_LTO = -Wl,-dead_strip,-no_dead_strip_inits_and_terms' in paths['link_recipe'].read_text(),
            'primary dead-strip recipe changed')
    manifest = json.loads(paths['manifest'].read_text())
    compiler = json.loads(paths['compiler_descriptor'].read_text())
    for key, item in inputs['compiler_source_files'].items():
        bound(item)
    check_compiler(main / compiler['compiler']['path'], compiler['compiler']['sha256'])
    report['witnesses'] = []
    for ident, key in [('osfmk/kalloc.o', 'kalloc_report'), ('libkern/OSData.cpo', 'osdata_report')]:
        recorded = json.loads(paths[key].read_text())
        row = next(r for r in recorded['representative_compiles'] if r['id'] == ident)
        recipe = next(r for r in manifest if r['id'] == ident)
        require(row['exit_code'] == 0 and row['actual_arm64_object'], 'recorded compile did not succeed')
        require(row['source_sha256'] == recipe['bound_source_sha256'], 'witness differs from frozen guest source')
        require(digest(Path(row['source'])) == row['source_sha256'], 'source changed')
        require(digest(Path(recipe['configuration'])) == recipe['configuration_sha256'], 'configuration changed')
        argv = recipe['next_owned_compile_argv_template']
        require(argv[0] == recorded['compiler']['path'] and recorded['compiler'] == dict(path=str(main / compiler['compiler']['path']), sha256=compiler['compiler']['sha256']), 'wrong compiler')
        require('-DXNU_NO_TYPE_BUILTINS=0' in argv and '-target' in argv and argv[argv.index('-target') + 1] == 'arm64-apple-ios16.5', 'guest recipe/builtins changed')
        commands = [c for c in recorded['commands'] if c['argv'][0] == argv[0] and row['source'] in c['argv'] and c.get('exit_code') == 0]
        require(len(commands) == 1, 'actual compile command unavailable/ambiguous')
        require('-DXNU_NO_TYPE_BUILTINS=0' in commands[0]['argv'], 'actual compile disabled metadata')
        for name, expected in row['dependencies'].items():
            require(digest(Path(name)) == expected, 'actual dependency changed: ' + name)
        obj = Path(row['object'])
        require(digest(obj) == row['object_sha256'], 'object changed')
        parsed = macho(obj)
        witness = dict(id=ident, source_sha256=row['source_sha256'], object=str(obj), object_sha256=row['object_sha256'], dependency_count=len(row['dependencies']), command=commands[0])
        if ident.startswith('libkern'):
            witness['metadata'] = metadata(obj)
            require(witness['metadata']['sha256'] == row['allocator_metadata_sections'][0]['sha256'], 'recorded metadata bytes differ')
            osdata = obj
        else:
            boundaries = [s for s in parsed['symbols'] if s['name'].startswith(('section$start$__DATA_CONST$__kalloc_', 'section$end$__DATA_CONST$__kalloc_'))]
            expected = {'section$' + edge + '$__DATA_CONST$__kalloc_' + kind for edge in ('start', 'end') for kind in ('type', 'var')}
            require({s['name'] for s in boundaries} == expected and all(s['type'] == 1 for s in boundaries), 'consumer boundary symbol contract changed')
            witness['undefined_section_boundaries'] = boundaries
            references = [dict(section=s['section'], **r) for s in parsed['sections']
                          for r in s['relocations'] if r.get('target') in expected]
            require({r['target'] for r in references} == expected, 'consumer boundary relocation references missing')
            witness['section_boundary_relocations'] = references
        report['witnesses'].append(witness)
    controls = json.loads(paths['controls_report'].read_text())
    historical = next(r for r in controls['negative_controls'] if r['name'] == 'stock-compiler-real-metadata')
    require(historical['pass'] and historical['actual_exit_code'] == 1 and historical['source_sha256'] == recipe['bound_source_sha256'], 'wrongcompiler historical control invalid')
    require(digest(Path(historical['compiler'])) == historical['compiler_sha256'], 'historical stock compiler changed')
    command = next(c for c in controls['commands'] if c['argv'][0] == historical['compiler'])
    require(command['exit_code'] == 1 and command['stderr_sha256'] == digest(paths['wrongcompiler_stderr']), 'wrongcompiler diagnostic changed')
    require('-DXNU_NO_TYPE_BUILTINS=0' in command['argv'] and historical['no_output_or_fallback'], 'wrongcompiler control weakens metadata contract')
    require(not Path(command['argv'][command['argv'].index('-o') + 1]).exists(), 'wrongcompiler control output unexpectedly exists')
    diagnostic = paths['wrongcompiler_stderr'].read_text()
    require('__builtin_xnu_type' in diagnostic and 'error:' in diagnostic, 'historical failure is not metadata related')
    report['historical_wrongcompiler'] = dict(control=historical, command=command)
    report['controls'] = []
    try:
        check_compiler(Path(historical['compiler']), compiler['compiler']['sha256'])
    except ValueError as error:
        report['controls'].append(dict(name='wrongcompiler-preflight', rejected=True, diagnostic=str(error), compiler_executed=False))
    else:
        raise ValueError('wrongcompiler control unexpectedly passed')
    original = metadata(osdata)
    with osdata.open('rb') as stream:
        data = stream.read()
    for label, offset, replacement in [('stripped-section', original['header_offset'], b'__removed_type'.ljust(16, b'\0')), ('stripped-live-support', original['header_offset'] + 64, struct.pack('<I', 0)), ('stripped-relocations', original['header_offset'] + 60, struct.pack('<I', 0))]:
        copy = bytearray(data)
        copy[offset:offset + len(replacement)] = replacement
        path = args.output / (label + '.cpo')
        with path.open('xb') as stream:
            stream.write(copy)
        try:
            metadata(path)
        except ValueError as error:
            report['controls'].append(dict(name=label, path=str(path.resolve()), sha256=digest(path), rejected=True, diagnostic=str(error), compiler_executed=False))
        else:
            raise ValueError('corrupted object unexpectedly accepted: ' + label)
    report['checks_passed'] = True
    report['outcome'] = 'pass'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(kind='host-test', origin='local-host', recorded_at=datetime.now(timezone.utc).isoformat(), argv=sys.argv,
                  script_sha256=digest(Path(__file__)), outcome='fail', compiler_executed=False, linker_executed=False,
                  full_kernel_link_retention_qualified=False, guest_executed=False, device_executed=False)
    code = 0
    try:
        run(args, report)
    except Exception as error:
        report['error'] = repr(error)
        code = 2
    status = Path('/proc/self/status').read_text().splitlines()
    report['process_status'] = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in status if line.startswith(('VmRSS:', 'VmHWM:'))}
    report['exit_code'] = code
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(outcome=report['outcome'], exit_code=code, process_status=report['process_status'], error=report.get('error'))))
    return code


if __name__ == '__main__':
    sys.exit(main())
