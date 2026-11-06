#!/usr/bin/env python3
"""Bounded allocator byte witnesses; product/producer authority stays with CU.

Borrowed snapshots and views must be used inside CU's macho_snapshot context.
No compilation, binary utilities, dynamic CU import, or target execution here.
"""
import hashlib
import json
from pathlib import Path
import struct
import time

SOURCE_PINS = {
    'kalloc_header': 'ed1ede09dade21c6d20bd7494b263278b0adeddc4a356c849b9305a7931321d1',
    'zalloc_header': 'fa29ef19600c860cfa00b21c8f494b9439044c0d1efda276586c9c95c01aeccc',
    'loader_header': '8780a1e622375833b563f488bc820422c2fb5b8727bb8df8ceaa73ab6f0f88e3',
    'relocation_header': 'c190e13a45e54e4dd513e8465f521cb1ad0327fcce02405afc6958544eb53f2a',
    'link_recipe': '755d0fde3e8ddd46e235ed58c0664394014250e1dae7e7021bd07ad0ecae65b8',
    'kalloc_consumer': '05381b898a98188c271bc76f798a281d5eaaaee586acf4359001fba8a28df23c',
    'compiler_semantics': '6fe9f27461be647d14006558f4b79a9fad620170f33a22ce875b3aeb66b3b69d',
    'selected_link_contract': '125a7627c1178d3812f3e618c8f8bcc125cb77520be100013cbcc710b84c9d3a',
}
# ARM64 LP64: zone_view has four pointers. The selected uint16 zone_id and
# (log2(32768)-log2(32))*2+2 == 22 one-byte zones put var signatures at56/64.
LAYOUTS = {
    'fixed': dict(section='__kalloc_type', stride=64, strings={'name':16, 'signature':32},
                  integers={'flags':[40,4], 'size':[44,4]}, zero=[[0,16],[24,8],[48,16]]),
    'variable': dict(section='__kalloc_var', stride=80,
                     strings={'name':16, 'signature_header':56, 'signature_type':64},
                     integers={'version':[0,2], 'size_header':[2,2], 'size_type':[4,4], 'flags':[72,4]},
                     zero=[[8,8],[24,32],[76,4]]),
}
MAX_REQUIREMENTS = 4096
MAX_RECORDS = 1_000_000
MAX_RELOCATIONS = 2_000_000
MAX_STRING = 4096
BOUNDARIES = tuple('section$'+edge+'$__DATA_CONST$'+layout['section']
                   for layout in LAYOUTS.values() for edge in ('start','end'))


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha_value(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def tool_sha256():
    digest = hashlib.sha256()
    with Path(__file__).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def expected_source():
    return dict(schema=1, abi='arm64-lp64-little-endian', sources=SOURCE_PINS,
                layouts=LAYOUTS, segment='__DATA_CONST', alignment=8,
                variable_zones=22, pointer_encoding='unslid-u64', kc_format='static',
                live_support=0x08000000, selected_data_const_protection=[1,1],
                selected_use_lto=False, selected_dead_strip=False,
                lto_rule='USE_LTO=1 enables conditional dead_strip')


def source_contract(snapshots):
    """Verify exact source bytes through borrowed coherent FDs; no layout guess."""
    require(set(snapshots) == set(SOURCE_PINS), 'Exact selected source set required')
    for name, expected in SOURCE_PINS.items():
        require(snapshots[name].digest() == expected, 'Selected source changed: '+name)
    # Full digests above bind declarations, placement macros, ARM64 relocation
    # enum, compiler signature implementation and conditional linker recipe.
    result = expected_source()
    return json.loads(canonical(result))


def check_source(contract):
    require(contract == expected_source(), 'Source-qualified ARM64 layout contract changed')


def file_range(snapshot, offset, size):
    require(type(offset) is int and type(size) is int and 0 <= offset <= snapshot.length
            and 0 <= size <= snapshot.length-offset, 'Allocator file range outside retained FD')
    return snapshot.read_range(offset, size)


def section_range(snapshot, section):
    require(section['flags'] & 255 not in (1,12,18), 'Allocator/string section is not file-backed')
    require(section['address'] >= 0 and section['size'] >= 0 and
            section['address']+section['size'] < 2**64, 'Invalid allocator VM range')
    require(0 <= section['offset'] <= snapshot.length and
            section['size'] <= snapshot.length-section['offset'], 'Allocator section exceeds retained FD')


def read_string(snapshot, section, address):
    section_range(snapshot, section)
    delta = address-section['address']
    require(0 <= delta < section['size'], 'String/addend outside target section')
    raw = file_range(snapshot, section['offset']+delta, min(MAX_STRING,section['size']-delta))
    require(b'\0' in raw, 'No bounded allocator string terminator')
    try:
        return raw.split(b'\0',1)[0].decode('ascii')
    except UnicodeDecodeError as error:
        raise ValueError('Allocator string is not ASCII') from error


def relocations(snapshot, section):
    """Stream raw ARM64 records, including explicit signed24 ADDEND pairs.

    ADDEND is an instruction relocation payload, never a section/symbol index.
    Metadata pointers support UNSIGNED external defined-symbol relocations only.
    """
    count = section['relocation_count']
    require(type(count) is int and 0 <= count <= MAX_RELOCATIONS, 'Relocation inspection bound exceeded')
    require(0 <= section['relocation_offset'] <= snapshot.length and
            count*8 <= snapshot.length-section['relocation_offset'], 'Relocation table exceeds retained FD')
    pending = None
    for number in range(count):
        address,bits = struct.unpack('<iI',file_range(snapshot,section['relocation_offset']+number*8,8))
        row = dict(address=address, type=bits>>28, length=1<<((bits>>25)&3),
                   pcrel=bool(bits&(1<<24)), external=bool(bits&(1<<27)), index=bits&0xffffff)
        require(0 <= address and address+row['length'] <= section['size'], 'Relocation exceeds section')
        if pending is not None:
            require(row['address'] == pending['address'] and row['type'] in (3,4)
                    and row['length'] == 4 and row['pcrel'] == (row['type'] == 3),
                    'Invalid ARM64_RELOC_ADDEND follower')
            row['explicit_addend'] = pending['addend']
            pending = None
        if row['type'] == 10:
            require(not row['external'] and not row['pcrel'] and row['length'] == 4,
                    'Invalid ARM64_RELOC_ADDEND flags')
            row['addend'] = row['index'] if row['index'] < 0x800000 else row['index']-0x1000000
            pending = row
        yield row
    require(pending is None, 'Unpaired ARM64_RELOC_ADDEND')


def pointer_relocations(snapshot, view, section, layout, symbol_at):
    require(section['size']//layout['stride'] <= MAX_REQUIREMENTS, 'Object record inspection bound exceeded')
    expected = {base+offset for base in range(0,section['size'],layout['stride'])
                for offset in layout['strings'].values()}
    require(len(expected) <= MAX_REQUIREMENTS*3, 'Object pointer inspection bound exceeded')
    resolved = {}
    for row in relocations(snapshot,section):
        address = row['address']
        require(address in expected and address not in resolved, 'Unexpected/duplicate metadata relocation')
        require((row['type'],row['length'],row['pcrel'],row['external']) == (0,8,False,True)
                and 'explicit_addend' not in row, 'Unsupported allocator pointer relocation kind/flags')
        symbol = symbol_at(snapshot,view,row['index'])
        require(not symbol['type'] & 0xe0 and symbol['type'] & 14 == 14 and
                0 < symbol['section'] <= len(view['sections']), 'Allocator pointer symbol is undefined/unsupported')
        target = view['sections'][symbol['section']-1]
        require(target['name'] == '__cstring' and target['flags'] & 255 == 2,
                'Allocator object pointer does not target a cstring section')
        inline = struct.unpack('<q',file_range(snapshot,section['offset']+address,8))[0]
        actual = symbol['value']+inline
        require(0 <= actual < 2**64, 'Allocator symbol plus inline addend overflows')
        resolved[address] = dict(string=read_string(snapshot,target,actual), inline_addend=inline,
                                 symbol=symbol['name'], target_address=actual)
    # A null header signature is allowed for KALLOC_TYPE_VAR_DEFINE_3 only.
    for address in expected-resolved.keys():
        raw = file_range(snapshot,section['offset']+address,8)
        is_header = layout['section'] == '__kalloc_var' and address%layout['stride'] == 56
        require(is_header and raw == b'\0'*8, 'Missing required metadata pointer relocation')
        resolved[address] = dict(string=None, inline_addend=0, symbol=None, target_address=0)
    return resolved


def image_string(snapshot, view, pointer):
    require(pointer != 0, 'Null required allocator pointer')
    matches = [s for s in view['sections'] if s['address'] <= pointer < s['address']+s['size']]
    require(len(matches) == 1, 'Final pointer has ambiguous/missing section mapping')
    section = matches[0]
    require(section['name'] == '__cstring' and section['flags'] & 255 == 2,
            'Final allocator pointer is not a source-qualified cstring')
    parents = [s for s in view['segments'] if s['name'] == section['parent_segment']]
    require(len(parents) == 1, 'Final string parent segment is ambiguous')
    parent = parents[0]
    require(parent['initial'] & 1 and not parent['initial'] & 2 and
            section['offset']-parent['offset'] == section['address']-parent['address'] and
            parent['address'] <= pointer < parent['address']+parent['stored'],
            'Final string is not in read-only file-backed mapped bytes')
    return read_string(snapshot,section,pointer)


def semantic_record(snapshot, view, section, kind, base, pointer_values=None):
    layout = LAYOUTS[kind]
    raw = file_range(snapshot,section['offset']+base,layout['stride'])
    for offset,size in layout['zero']:
        require(raw[offset:offset+size] == b'\0'*size, 'Allocator runtime/reserved fields are not pristine')
    values = {key:int.from_bytes(raw[offset:offset+size],'little')
              for key,(offset,size) in layout['integers'].items()}
    require(values['flags'] & ~0xff == 0 and values['flags'] & 0x60 == 0x60,
            'Allocator flags are not selected compiler pre-initialization metadata')
    if kind == 'variable':
        require(values['version'] == 1 and values['size_type'] > 0, 'Unsupported allocator variable version/size')
    else:
        require(values['size'] > 0, 'Allocator fixed type size is zero')
    strings = {}
    for key,offset in layout['strings'].items():
        if pointer_values is not None:
            value = pointer_values[base+offset]['string']
        else:
            pointer = struct.unpack_from('<Q',raw,offset)[0]
            value = None if kind == 'variable' and key == 'signature_header' and pointer == 0 else image_string(snapshot,view,pointer)
        strings[key] = value
    require(strings['name'] is not None and strings['name'].startswith('site.') and len(strings['name']) > 5,
            'Allocator site name violates selected emission macro')
    if kind == 'variable':
        require((strings['signature_header'] is None) == (values['size_header'] == 0),
                'Variable header size/signature disagree')
    # Empty signature is legal for data-only/VM macros; absence is not empty.
    for key,value in strings.items():
        if key != 'name' and value is not None:
            require(all(ch in '0123456789abcdef' for ch in value), 'Allocator signature contains unsupported encoding')
    return dict(kind=kind, **values, **strings)


def metadata_sections(snapshot,view):
    result = {}
    for kind,layout in LAYOUTS.items():
        rows = [s for s in view['sections'] if s['name'] == layout['section']]
        require(len(rows) <= 1, 'Duplicate allocator metadata section')
        if not rows:
            continue
        row = rows[0]
        section_range(snapshot,row)
        require(row['segment'] == '__DATA_CONST' and row['flags'] & 255 == 0 and
                row['align'] >= 3 and row['address']%8 == row['offset']%8 == 0 and
                row['size']%layout['stride'] == 0 and row['size']//layout['stride'] <= MAX_RECORDS,
                'Allocator section placement/alignment/stride invalid')
        result[kind] = row
    for row in result.values():
        for other in view['sections']:
            if other is row or not row['size'] or not other['size']:
                continue
            require(row['address']+row['size'] <= other['address'] or
                    other['address']+other['size'] <= row['address'], 'Allocator section overlaps another VM section')
    return result


def inspect_object(snapshot,view,source,*,symbol_at):
    check_source(source)
    require(view['filetype'] == 1, 'Allocator emission witness requires MH_OBJECT')
    require(callable(symbol_at), 'Borrowed original nlist accessor required')
    records, pointers, sections = {}, [], metadata_sections(snapshot,view)
    deadline = time.monotonic()+60
    for kind,section in sections.items():
        require(section['flags'] & 0x08000000, 'Allocator object live_support attribute missing')
        require(section['size']//LAYOUTS[kind]['stride'] <= MAX_REQUIREMENTS, 'Object record inspection bound exceeded')
        resolved = pointer_relocations(snapshot,view,section,LAYOUTS[kind],symbol_at)
        pointers.extend(dict(kind=kind,address=k,**{key:value for key,value in v.items() if key != 'string'})
                        for k,v in resolved.items())
        for base in range(0,section['size'],LAYOUTS[kind]['stride']):
            require(time.monotonic() < deadline, 'Allocator object inspection deadline exceeded')
            record = semantic_record(snapshot,view,section,kind,base,resolved)
            fingerprint = sha_value(record)
            row = records.setdefault(fingerprint,dict(record=record,count=0))
            row['count'] += 1
    digest = snapshot.digest()
    require(digest == view['sha256'], 'Object view digest differs from retained bytes')
    snapshot.check()
    return dict(schema=1,source_contract_sha256=sha_value(source),tool_sha256=tool_sha256(),
                object_sha256=digest,metadata_records=records,pointers=pointers,
                qualification='historical-object-byte-witness-only')


def boundary_references(snapshot,view,*,symbol_at):
    require(view['filetype'] == 1, 'Boundary consumer witness requires MH_OBJECT')
    counts = dict.fromkeys(BOUNDARIES,0)
    explicit_addends = 0
    deadline = time.monotonic()+60
    for section in view['sections']:
        for row in relocations(snapshot,section):
            require(time.monotonic() < deadline, 'Boundary relocation inspection deadline exceeded')
            if row['type'] == 10:
                explicit_addends += 1
                continue
            if not row['external']:
                continue
            symbol = symbol_at(snapshot,view,row['index'])
            if symbol['name'] in counts:
                require(symbol['type'] == 1 and symbol['section'] == 0 and
                        row['length'] == 4 and (row['type'],row['pcrel']) in ((5,True),(6,False)),
                        'Unsupported allocator boundary consumer relocation')
                counts[symbol['name']] += 1
    require(all(counts.values()), 'Allocator consumer is missing boundary references')
    digest = snapshot.digest()
    require(digest == view['sha256'], 'Consumer changed after snapshot parsing')
    return dict(object_sha256=digest,counts=counts,arm64_explicit_addend_pairs=explicit_addends)


def check_image_encoding(snapshot):
    """Reject fixup encodings that cannot be read as unslid raw ARM64 VAs."""
    magic,cpu,subtype,kind,count,size,flags,reserved = struct.unpack('<8I',file_range(snapshot,0,32))
    require((magic,cpu,subtype,kind) == (0xfeedfacf,0x100000c,0,2), 'Unsupported final ARM64 image encoding')
    require(size <= 16*1024**2 and 32+size <= snapshot.length and count <= size//8,
            'Unsupported final load command extent')
    cursor = 32
    for _ in range(count):
        command,length = struct.unpack('<II',file_range(snapshot,cursor,8))
        require(length >= 8 and length%8 == 0 and cursor+length <= 32+size, 'Invalid final command extent')
        require(command != 0x80000034, 'Chained final pointer fixups are unsupported')
        if command in (0x22,0x80000022):
            require(length == 48, 'Invalid dyld info command')
            values = struct.unpack('<10I',file_range(snapshot,cursor+8,40))
            require(not any(values[i] for i in (1,3,5,7)), 'Dyld rebase/bind final pointer streams are unsupported')
        if command == 0xb:
            require(length == 80, 'Invalid dynamic symbol command')
            values = struct.unpack('<18I',file_range(snapshot,cursor+8,72))
            require(not values[15] and not values[17], 'Dynamic final relocation tables are unsupported')
        cursor += length
    require(cursor == 32+size, 'Incomplete final load command extent')


def validate(snapshot,view,contract,*,symbol_at):
    """Validate unslid static-image records and explicit required minima.

    CU must independently bind contract/witness/source/selection/producer pins.
    Requirements are proof *inputs*, never an authorization or liveness oracle.
    No boolean can grant product qualification; no lazy borrowed object escapes.
    """
    check_source(contract['source'])
    require(callable(symbol_at), 'Reviewed original nlist accessor required')
    require(view['filetype'] == 2, 'Final allocator parser requires ARM64 MH_EXECUTE')
    check_image_encoding(snapshot)
    selection = contract['selection']
    require(set(selection) == {'use_lto','dead_strip','pointer_encoding','kc_format'} and
            type(selection['use_lto']) is bool and type(selection['dead_strip']) is bool and
            selection['pointer_encoding'] == 'unslid-u64' and selection['kc_format'] == 'static',
            'Unsupported selected link/pointer/KC semantics')
    require(selection['use_lto'] is False and selection['dead_strip'] is False,
            'Different LTO/dead_strip selection requires a new independently qualified source contract')
    witnesses = contract['witnesses']
    require(type(witnesses) is list and 0 < len(witnesses) <= MAX_REQUIREMENTS, 'Bounded actual input witnesses required')
    observed = {}
    witness_rows = 0
    object_hashes = set()
    for witness in witnesses:
        require(witness['tool_sha256'] == tool_sha256() and
                witness['source_contract_sha256'] == sha_value(contract['source']), 'Witness tool/source binding mismatch')
        object_hash = witness['object_sha256']
        require(type(object_hash) is str and len(object_hash) == 64 and all(c in '0123456789abcdef' for c in object_hash)
                and object_hash not in object_hashes, 'Duplicate/invalid source-object witness digest')
        object_hashes.add(object_hash)
        require(len(witness['metadata_records']) <= MAX_REQUIREMENTS, 'Oversized witness record set')
        witness_rows += len(witness['metadata_records'])
        require(witness_rows <= MAX_REQUIREMENTS, 'Combined witness record bound exceeded')
        for fingerprint,row in witness['metadata_records'].items():
            require(fingerprint == sha_value(row['record']) and type(row['count']) is int and row['count'] > 0,
                    'Invalid witnessed semantic record')
            observed[(witness['object_sha256'],fingerprint)] = row
    requirements = contract['required']
    require(type(requirements) is list and len(requirements) <= MAX_REQUIREMENTS, 'Required-record bound exceeded')
    wanted = {}
    for req in requirements:
        objects = req['object_sha256']
        require(type(objects) is list and 0 < len(objects) <= MAX_REQUIREMENTS and
                len(objects) == len(set(objects)), 'Required identity needs distinct bounded source objects')
        rows = [observed.get((obj,req['fingerprint'])) for obj in objects]
        require(all(row is not None for row in rows) and type(req['minimum']) is int and
                0 < req['minimum'] <= sum(row['count'] for row in rows),
                'Required record lacks actual source-object witness/multiplicity')
        require(isinstance(req['liveness_proof_sha256'],str) and len(req['liveness_proof_sha256']) == 64 and
                all(c in '0123456789abcdef' for c in req['liveness_proof_sha256']), 'Required record lacks explicit liveness-proof digest')
        require(req['fingerprint'] not in wanted, 'Duplicate required identity must be aggregated explicitly')
        wanted[req['fingerprint']] = dict(minimum=req['minimum'],actual=0,object_sha256=list(objects),
                                         liveness_proof_sha256=req['liveness_proof_sha256'])
    deadline = time.monotonic()+120
    section_facts = []
    sections = metadata_sections(snapshot,view)
    for kind,layout in LAYOUTS.items():
        section = sections.get(kind)
        names = ['section$'+edge+'$__DATA_CONST$'+layout['section'] for edge in ('start','end')]
        symbols = [view['external_symbols'].get(name) for name in names]
        # Zero-length sections may legitimately disappear; explicit equal defined
        # boundaries still establish an empty range. Missing boundaries do not.
        require(all(symbols), 'Final allocator boundary symbols missing')
        require(all(s['type'] & 0xe0 == 0 and s['type'] & 14 in (2,14) and not s.get('undefined',False)
                    for s in symbols), 'Final allocator boundaries are undefined/unsupported')
        start,end = [s['value'] for s in symbols]
        require(0 <= start <= end < 2**64 and start%8 == end%8 == 0, 'Final allocator boundary range invalid')
        if section is None:
            require(start == end, 'Nonempty allocator range has no section')
            section_facts.append(dict(kind=kind,count=0,start=start,end=end,section_absent=True))
            continue
        require(start == section['address'] and end == start+section['size'], 'Final allocator boundaries do not delimit actual section')
        ordinal = view['sections'].index(section)+1
        require(all(s['type'] & 14 == 2 or s['section'] == ordinal for s in symbols), 'Boundary symbol section ordinal mismatch')
        parent = [s for s in view['segments'] if s['name'] == '__DATA_CONST']
        require(len(parent) == 1 and section['parent_segment'] == '__DATA_CONST', 'Allocator final segment missing/ambiguous')
        parent = parent[0]
        # Exact selected genuine link vector explicitly uses r--,r--. Runtime
        # pre-lockdown write arrangements are a separate unmeasured boot gate.
        require([parent['maximum'],parent['initial']] == [1,1] and
                parent['offset'] <= section['offset'] and section['offset']+section['size'] <= parent['offset']+parent['stored'] and
                section['offset']-parent['offset'] == start-parent['address'], 'Allocator mapped range/protection invalid')
        require(section['relocation_count'] == 0, 'Unresolved final allocator relocation table unsupported')
        aggregate = hashlib.sha256()
        for base in range(0,section['size'],layout['stride']):
            require(time.monotonic() < deadline, 'Final allocator inspection deadline exceeded')
            record = semantic_record(snapshot,view,section,kind,base)
            fingerprint = sha_value(record)
            aggregate.update(bytes.fromhex(fingerprint))
            if fingerprint in wanted:
                wanted[fingerprint]['actual'] += 1
        section_facts.append(dict(kind=kind,count=section['size']//layout['stride'],start=start,end=end,
                                  alignment_exponent=section['align'],flags=section['flags'],
                                  segment_protection=[parent['maximum'],parent['initial']],
                                  semantic_sequence_sha256=aggregate.hexdigest()))
    for fingerprint,row in wanted.items():
        require(row['actual'] >= row['minimum'], 'Required allocator metadata was not retained: '+fingerprint)
    digest = snapshot.digest()
    require(digest == view['sha256'], 'Image changed after coherent parsing')
    snapshot.check()
    return dict(schema=1,parser_result='pass',required_retention='pass' if wanted else 'incomplete-no-required-record-proof',
                product_qualification='not-granted-by-byte-validator',image_sha256=digest,
                tool_sha256=tool_sha256(),source_contract_sha256=sha_value(contract['source']),
                contract_sha256=sha_value(contract),selection=selection,sections=section_facts,required=wanted,
                input_object_sha256=[w['object_sha256'] for w in witnesses],
                limitations=['CU must validate actual producer lineage and required-record liveness proofs',
                             'No input/output record equality under dead_strip or LTO',
                             'No runtime, pointer authentication, dynamic relocations, chained fixups or fileset qualification'])
