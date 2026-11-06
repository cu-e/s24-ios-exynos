#!/usr/bin/env python3
"""Independent bounded VM-033 byte review; no compiler or external section tool."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import struct
import sys
import time

sys.dont_write_bytecode = True
START = time.monotonic()
ROOT = Path(__file__).resolve().parents[3]
PINS = {
    'tools/build/avf_guest_allocator_metadata.py': '892db7f0f0764d2ab021a0468f498bd19a53455333e40259bd859007639b43a5',
    'fixtures/public/avf-guest-allocator-metadata/inputs.json': '7af5bd9dd17a39f7267331f3b058a8fec3ce2fa3fff5c41fc452a9dfb2d2e207',
    'fixtures/public/avf-guest-allocator-metadata/evidence.json': 'd1a03f41f51d5af24739b5782be3b03fd9dca74638badcee13fc3d7a2ef8ce33',
    'fixtures/public/avf-guest-allocator-metadata/boundary-relocations-evidence.json': 'dedddab57b8e5f568bf807badbba8d56bc2f4700409276e8e8dbf2aecb521dae',
}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def require(value, text):
    if not value:
        raise ValueError(text)


def available():
    return next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))


def guard():
    require(time.monotonic()-START < 90, 'Review deadline exceeded')
    require(available() >= 4*1024**3, 'Review deferred below4GiB available memory')


def sha(path):
    guard()
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024*1024):
            guard()
            digest.update(block)
    return digest.hexdigest()


def load(path, digest=None):
    if digest:
        require(sha(path) == digest, 'Pinned input changed: '+str(path))
    with Path(path).open() as stream:
        return json.load(stream)


def decode(path):
    """Independent raw reader, without producer parser or binary utility calls."""
    require(path.stat().st_size <= 1024*1024, 'Review witness exceeds1MiB')
    with path.open('rb') as stream:
        data = stream.read()
    def extent(offset, size):
        require(0 <= offset <= len(data) and 0 <= size <= len(data)-offset, 'Independent extent failure')
        return data[offset:offset+size]
    extent(0, 32)
    magic, cpu, subtype, kind, ncmd, commands, flags, reserved = struct.unpack_from('<8I', data)
    require((magic, cpu, kind) == (0xfeedfacf, 0x100000c, 1), 'Independent ARM64 MH_OBJECT identity failure')
    extent(32, commands)
    cursor, sections, symbol_table = 32, [], None
    for _ in range(ncmd):
        extent(cursor, 8)
        command, size = struct.unpack_from('<II', data, cursor)
        require(size >= 8 and cursor+size <= 32+commands, 'Independent command extent failure')
        if command == 0x19:
            require(size >= 72, 'Independent segment truncated')
            count = struct.unpack_from('<I', data, cursor+64)[0]
            require(72+count*80 <= size, 'Independent section table extent failure')
            for index in range(count):
                at = cursor+72+index*80
                name, segment, address, length, offset, align, reloff, reloc_count, attrs, r1, r2, r3 = struct.unpack_from('<16s16sQQ8I', data, at)
                section = dict(name=name.split(b'\0')[0].decode(), segment=segment.split(b'\0')[0].decode(), address=address, size=length, offset=offset, align=align, relocation_offset=reloff, relocation_count=reloc_count, flags=attrs, header_offset=at)
                if attrs & 255 not in [1, 12, 18]:
                    extent(offset, length)
                extent(reloff, reloc_count*8)
                sections.append(section)
        elif command == 2:
            require(size == 24 and symbol_table is None, 'Independent symbol table identity failure')
            symbol_table = struct.unpack_from('<4I', data, cursor+8)
        cursor += size
    require(cursor == 32+commands and symbol_table, 'Independent incomplete command table')
    symoff, count, stroff, strsize = symbol_table
    extent(symoff, count*16)
    strings = extent(stroff, strsize)
    symbols = []
    for i in range(count):
        at = symoff+i*16
        name, typ, section, desc, value = struct.unpack_from('<IBBHQ', data, at)
        end = strings.find(b'\0', name)
        require(name < len(strings) and end >= name, 'Independent symbol string extent failure')
        symbols.append(dict(name=strings[name:end].decode(), type=typ, section=section, value=value, at=at))
    for section in sections:
        section['relocations'] = []
        for i in range(section['relocation_count']):
            at = section['relocation_offset']+i*8
            address, bits = struct.unpack_from('<II', data, at)
            kind = bits >> 28
            row = dict(address=address, type=kind, length=1 << ((bits >> 25) & 3), pcrel=bool(bits & (1 << 24)), external=bool(bits & (1 << 27)), index=bits & 0xffffff, at=at, bits=bits)
            require(address < 0x80000000 and address+row['length'] <= section['size'], 'Independent relocation extent failure')
            if kind == 10:
                row['addend'] = row['index'] if row['index'] < 0x800000 else row['index']-0x1000000
            elif row['external']:
                require(row['index'] < len(symbols), 'Independent symbol target failure')
                row['target'] = symbols[row['index']]['name']
            else:
                require(0 < row['index'] <= len(sections), 'Independent section target failure')
                row['target'] = sections[row['index']-1]['name']
            section['relocations'].append(row)
    return data, sections, symbols


def allocator(path):
    data, sections, symbols = decode(path)
    rows = [s for s in sections if s['name'] == '__kalloc_type']
    require(len(rows) == 1, 'Independent metadata section identity failure')
    row = rows[0]
    require((row['segment'], row['size'], row['align'], row['flags']) == ('__DATA_CONST', 192, 3, 0x08000000), 'Independent metadata extent/attributes failure')
    relocs = row['relocations']
    require(len(relocs) == 6 and {r['address'] for r in relocs} == {16, 32, 80, 96, 144, 160}, 'Independent six-pointer positions failure')
    resolved = []
    for r in relocs:
        require((r['type'], r['length'], r['pcrel'], r['external']) == (0, 8, False, True), 'Independent unsigned64 pointer failure')
        symbol = symbols[r['index']]
        require(symbol['type'] & 14 == 14 and 0 < symbol['section'] <= len(sections), 'Independent pointer target definition failure')
        target = sections[symbol['section']-1]
        addend = struct.unpack_from('<q', data, row['offset']+r['address'])[0]
        delta = symbol['value']+addend-target['address']
        require(target['name'] == '__cstring' and 0 <= delta < target['size'], 'Independent string target/addend failure')
        text = data[target['offset']+delta:target['offset']+min(delta+1024, target['size'])]
        require(b'\0' in text, 'Independent bounded string terminator failure')
        value = text.split(b'\0')[0].decode('ascii')
        expected = 'site.ExpansionData' if r['address'] in [16, 80, 144] else '12'
        require(value == expected, 'Independent observed allocator name/signature changed')
        resolved.append(dict(address=r['address'], symbol=symbol['name'], target_section=target['name'], inline_addend=addend, string=value))
    return row, resolved


BOUNDARIES = {'section$'+edge+'$__DATA_CONST$__kalloc_'+kind for edge in ['start', 'end'] for kind in ['type', 'var']}


def consumer(path):
    data, sections, symbols = decode(path)
    undefined = [s for s in symbols if s['name'] in BOUNDARIES]
    require({s['name'] for s in undefined} == BOUNDARIES and all(s['type'] == 1 for s in undefined), 'Independent consumer boundary definitions failure')
    refs = [dict(section=s['name'], **r) for s in sections for r in s['relocations'] if r.get('target') in BOUNDARIES]
    require(len(refs) == 16 and Counter(r['target'] for r in refs) == Counter({name: 4 for name in BOUNDARIES}), 'Independent actual16 boundary references failure')
    require(all(r['external'] and r['length'] == 4 and (r['type'], r['pcrel']) in [(5, True), (6, False)] for r in refs), 'Independent consumer relocation contract failure')
    return refs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(); main_root = args.main.resolve(); out = args.out.resolve()
    require(out.is_relative_to(ROOT/'docs/reviews/vm-033') and not out.exists(), 'Fresh review-only output required')
    out.mkdir(parents=True)
    report = dict(kind='host-test', origin='local-host', outcome='fail', recorded_at=stamp(), task='REV-046', owner='codex-review-guest-allocator-20261106-fa', experiment='REV046ALLOC-001', argv=[sys.executable, *sys.argv], checks=[], findings=[], compiler_executed=False, linker_executed=False, external_section_tool_executed=False, guest_executed=False, full_link_retention_qualified=False)
    def check(name, value):
        require(value, 'Review check failed: '+name)
        report['checks'].append(dict(name=name, pass_result=True))
    def rejects(name, action):
        try:
            action()
        except (ValueError, IndexError, struct.error) as error:
            report['checks'].append(dict(name=name, pass_result=True, actual_rejection=repr(error)))
        else:
            raise ValueError('Corrupted copy accepted: '+name)
    try:
        samples = []
        for i in range(3):
            guard(); samples.append(available())
            if i < 2: time.sleep(1)
        report['mem_available_admission_bytes'] = samples
        producer = main_root/'worktrees/vm-033-20261106'
        frozen = {name: load(producer/name, expected) for name, expected in PINS.items() if name.endswith('.json')}
        helper = producer/'tools/build/avf_guest_allocator_metadata.py'
        check('exact final producer helper', sha(helper) == PINS['tools/build/avf_guest_allocator_metadata.py'])
        spec = importlib.util.spec_from_file_location('reviewed_producer_parser', helper)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        inputs = frozen['fixtures/public/avf-guest-allocator-metadata/inputs.json']
        original_evidence = frozen['fixtures/public/avf-guest-allocator-metadata/evidence.json']
        supplement = frozen['fixtures/public/avf-guest-allocator-metadata/boundary-relocations-evidence.json']
        def input_file(key):
            row = inputs['files'][key]; path = main_root/row['path']; load(path, row['sha256']) if path.suffix == '.json' else check('pinned primary '+key, sha(path) == row['sha256']); return path
        osreport = load(input_file('osdata_report')); kreport = load(input_file('kalloc_report'))
        osrow = next(r for r in osreport['representative_compiles'] if r['id'] == 'libkern/OSData.cpo')
        krow = next(r for r in kreport['representative_compiles'] if r['id'] == 'osfmk/kalloc.o')
        osobj, kobj = Path(osrow['object']), Path(krow['object'])
        for label, row, path in [('OSData', osrow, osobj), ('kalloc', krow, kobj)]:
            check('actual frozen object '+label, sha(path) == row['object_sha256'])
            check('actual frozen source '+label, sha(row['source']) == row['source_sha256'])
        metadata, strings = allocator(osobj); refs = consumer(kobj)
        expected = module.metadata(osobj)
        check('independent192-byte payload digest', hashlib.sha256(osobj.read_bytes()[metadata['offset']:metadata['offset']+192]).hexdigest() == expected['sha256'])
        check('six real pointer strings agree with producer', sorted((r['address'], r['string']) for r in strings) == sorted((r['address'], r['string']) for r in expected['resolved_metadata_strings']))
        check('all six actual inline addends are zero', all(r['inline_addend'] == 0 for r in strings))
        convert = lambda r: (r['section'], r['address'], r['length'], r['pcrel'], r['type'], r['target'])
        check('independent16 relocations match exact supplement', sorted(map(convert, refs)) == sorted(map(convert, supplement['boundary_reference_relocations'])))
        report['actual_metadata'] = dict(size=metadata['size'], flags=metadata['flags'], alignment_bytes=1 << metadata['align'], relocations=metadata['relocations'], resolved=strings)
        report['actual_consumer_references'] = refs
        report['object_pins'] = {str(osobj): osrow['object_sha256'], str(kobj): krow['object_sha256']}
        # Mutate only bounded copies of the genuine object bytes.
        data = osobj.read_bytes()
        def mutated(name, edits, test=module.metadata, original=data):
            copy = bytearray(original)
            for offset, value in edits: copy[offset:offset+len(value)] = value
            path = out/(name+'.o'); path.write_bytes(copy); rejects(name, lambda: test(path)); return path
        h = metadata['header_offset']; first = metadata['relocations'][0]; bits = first['bits']; rpos = first['at']
        mutated('missing-metadata-section', [(h, b'__removed_type'.ljust(16, b'\0'))])
        mutated('cleared-live-support', [(h+64, struct.pack('<I', 0))])
        mutated('missing-metadata-relocation', [(h+60, struct.pack('<I', 5))])
        mutated('pointer-pcrel', [(rpos+4, struct.pack('<I', bits | (1 << 24)))])
        mutated('pointer32', [(rpos+4, struct.pack('<I', (bits & ~(3 << 25)) | (2 << 25)))])
        mutated('pointer-subtractor', [(rpos+4, struct.pack('<I', (bits & 0x0fffffff) | (1 << 28)))])
        mutated('pointer-address-outside-section', [(rpos, struct.pack('<I', 192))])
        _, sec, symbols = decode(osobj); symbol = symbols[first['index']]
        mutated('undefined-string-target', [(symbol['at']+4, bytes([1]))])
        target = sec[symbol['section']-1]
        mutated('string-value-outside-section', [(symbol['at']+8, struct.pack('<Q', target['address']+target['size']))])
        kd, ks, ksymbols = decode(kobj)
        addend_data = data
        addends = [r for s in sec for r in s['relocations'] if r['type'] == 10]
        if not addends:
            addend_data = kd
            addends = [r for s in ks for r in s['relocations'] if r['type'] == 10]
        require(addends, 'Actual witness has no addend to test historical correction')
        addend = addends[0]
        mutated('broken-real-addend-pair', [(addend['at']+8, struct.pack('<I', addend['address']+4))], test=module.macho, original=addend_data)
        target_name = next(iter(sorted(BOUNDARIES))); replacement = next(r['index'] for r in refs if r['target'] != target_name)
        edits = [(r['at']+4, struct.pack('<I', (r['bits'] & ~0xffffff) | replacement)) for r in refs if r['target'] == target_name]
        mutated('missing-consumer-boundary-references', edits, test=consumer, original=kd)
        # The frozen hash gate protects a zero-addend witness; record resolver scope.
        changed = bytearray(data); struct.pack_into('<q', changed, metadata['offset']+16, 1)
        changed_path = out/'nonzero-inline-pointer-addend.o'; changed_path.write_bytes(changed)
        rejects('independent-inline-addend-consumer', lambda: allocator(changed_path))
        producer_resolution = module.metadata(changed_path)
        rejects('production-object-hash-gate-on-inline-change', lambda: module.require(module.digest(changed_path) == osrow['object_sha256'], 'object changed'))
        report['findings'].append(dict(severity='nonblocking-for-frozen-witness', subject='symbolic string resolver ignores inline unsigned-pointer addends', actual=producer_resolution['resolved_metadata_strings'], limitation='All six real pinned pointer addends are zero and the production object hash gate rejects the changed copy. Any future generalization must add inline addends or explicitly reject nonzero ones.'))
        controls = load(input_file('controls_report')); historical = next(r for r in controls['negative_controls'] if r['name'] == 'stock-compiler-real-metadata')
        diagnostic = input_file('wrongcompiler_stderr').read_text()
        check('historical real metadata builtin failure retained', historical['actual_exit_code'] == 1 and historical['no_output_or_fallback'] and '__builtin_xnu_type' in diagnostic and 'error:' in diagnostic)
        failed_command = next(c for c in controls['commands'] if c['argv'][0] == historical['compiler'])
        check('actual wrongcompiler command retains target metadata and no output', failed_command['exit_code'] == 1 and '-DXNU_NO_TYPE_BUILTINS=0' in failed_command['argv'] and '-ftrivial-auto-var-init=zero' in failed_command['argv'] and not Path(failed_command['argv'][failed_command['argv'].index('-o')+1]).exists())
        check('actual distinct stock compiler identity retained', sha(historical['compiler']) == historical['compiler_sha256'])
        rejects('actual wrong compiler identity gate', lambda: module.check_compiler(Path(historical['compiler']), osreport['compiler']['sha256']))
        first_run = original_evidence['runs'][0]; first_evidence = load(first_run['path'], first_run['sha256'])
        check('initial addend-parser failed history preserved', first_evidence['outcome'] == 'fail' and 'relocation target out of range' in first_evidence.get('error', ''))
        header = input_file('kalloc_header').read_text(); loader = input_file('loader_header').read_text(); recipe = input_file('link_recipe').read_text(); relhead = input_file('relocation_header').read_text()
        check('source requests live_support regular placement', '"regular, live_support"' in header and '#define KALLOC_TYPE_SEGMENT "__DATA_CONST"' in header)
        check('public flag and addend definitions match actual bytes', '0x08000000' in loader and 'ARM64_RELOC_ADDEND' in relhead)
        check('actual source still enables LTO dead stripping', 'LDFLAGS_KERNEL_STRIP_LTO = -Wl,-dead_strip,-no_dead_strip_inits_and_terms' in recipe)
        report.update(outcome='pass', summary='Independent real-object byte review confirms192B live-support metadata/six unsigned64 pointers/strings and16 kalloc boundary references; owned corruption and wrongcompiler gates reject. Bounded zero-inline-addend resolver limitation recorded. Final LTO retention/runtime remain unmeasured.')
    except Exception as error:
        report['error'] = repr(error)
    finally:
        status = {line.split(':', 1)[0]: int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:', 'VmRSS:'))}
        report['memory'] = dict(status, inherited_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
        if status['VmHWM'] > 256*1024**2: report.update(outcome='fail', error='Review current-image VmHWM exceeded256MiB')
        report['elapsed_seconds'] = time.monotonic()-START; report['finished_at'] = stamp()
        def finish_sha(path):
            with Path(path).open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest()
        report['source_sha256'] = finish_sha(__file__)
        report['artifact_hashes'] = {str(p): finish_sha(p) for p in out.iterdir() if p.is_file()}; report['artifacts'] = list(report['artifact_hashes']) or [str(Path(__file__))]
        (out/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'], error=report.get('error'), checks=len(report['checks']), findings=report['findings'], memory=report['memory']), indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
