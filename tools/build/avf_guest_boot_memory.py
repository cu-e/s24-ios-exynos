#!/usr/bin/env python3
"""Source-bound AVF memory preflight. Does not compile or execute a guest."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone

U64 = (1 << 64) - 1
FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/public/avf-guest-boot-memory'
PREPARED = 'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('Address/size must be an integer or integer string')
    result = int(value, 0) if isinstance(value, str) else int(value)
    if not 0 <= result <= U64:
        raise ValueError('Address/size outside uint64 range')
    return result


def add(a, b):
    return number(a + b)


def up(value, alignment):
    return add(value, alignment - 1) & ~(alignment - 1)


def span(base, size):
    return [base, add(base, size)]


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_at(stream, offset, length, bound):
    require(offset >= 0 and length >= 0 and offset + length <= bound, 'Truncated input extent')
    stream.seek(offset)
    data = stream.read(length)
    require(len(data) == length, 'Short input read')
    return data


def boot_args_abi(text):
    """Calculate the pinned declaration's ARM64 LP64 field layout without C."""
    source = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    body = re.search(r'struct boot_args\s*\{(.*?)\}', source, re.S)
    require(body is not None, 'boot_args declaration absent')
    kinds = {'uint16_t': (2, 2), 'uint32_t': (4, 4), 'uint64_t': (8, 8), 'void *': (8, 8),
             'Boot_Video': (48, 8), 'struct boot_video': (48, 8), 'char': (1, 1)}
    fields, offset = {}, 0
    for declaration in body[1].split(';'):
        declaration = ' '.join(declaration.split())
        if not declaration:
            continue
        match = re.fullmatch(r'(uint16_t|uint32_t|uint64_t|void\s*\*|Boot_Video|struct boot_video|char)\s*(.+)', declaration)
        require(match is not None, 'Unrecognized boot_args declaration')
        kind = 'void *' if match[1].startswith('void') else match[1]
        size, alignment = kinds[kind]
        for name in match[2].split(','):
            field = re.fullmatch(r'\s*(\w+)(?:\[(BOOT_LINE_LENGTH)\])?\s*', name)
            require(field is not None, 'Unrecognized boot_args field')
            count = 608 if field[2] else 1
            offset = up(offset, alignment)
            fields[field[1].lower()] = {'offset': offset, 'size': size * count}
            offset += size * count
    return {'fields': fields, 'size': up(offset, 8), 'abi': 'ARM64 LP64 declaration calculation; not a compiler measurement'}


def source_rules(main, report):
    pin_path = FIXTURES / 'source-pins.json'
    pins = json.loads(pin_path.read_text())
    component_path = main / PREPARED / 'prepared-component.json'
    require(digest(component_path) == pins['prepared_component_sha256'], 'Prepared component identity mismatch')
    component = json.loads(component_path.read_text())
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
    texts, bindings = {}, []
    for name, expected in pins['scion'].items():
        argv = ['git', '-C', str(main / 'references/scion-avf'), 'show', pins['scion_commit'] + ':' + name]
        start = time.monotonic()
        proc = subprocess.run(argv, env=env, capture_output=True, timeout=15)
        data = proc.stdout
        row = {'argv': argv, 'exit_code': proc.returncode, 'seconds': time.monotonic() - start,
               'stdout_sha256': hashlib.sha256(data).hexdigest(), 'stderr_sha256': hashlib.sha256(proc.stderr).hexdigest()}
        report['commands'].append(row)
        require(proc.returncode == 0, 'Pinned public source unavailable; lazy fetch is disabled')
        require(len(data) <= 2 * 1024 * 1024, 'Unexpected source size')
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(row['stdout_sha256'] == expected['sha256'] and blob == expected['git_blob_sha1'], 'Scion source identity mismatch: ' + name)
        texts[name] = data.decode()
        bindings.append({'role': 'scion', 'path': name, **expected})
    root = main / PREPARED / 'source/xnu'
    for name, expected in pins['prepared_xnu'].items():
        actual = digest(root / name)
        require(actual == expected['sha256'] == component['prepared_source_files'][name], 'Prepared source identity mismatch: ' + name)
        bindings.append({'role': 'prepared_xnu', 'path': name, 'sha256': actual})
    shim_root = main / 'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105'
    shim_path = shim_root / 'Image'
    require(digest(shim_path) == pins['qualified_shim']['sha256'], 'Qualified source-built shim Image mismatch')
    require(digest(shim_root / 'report.json') == pins['qualified_shim']['build_report_sha256'], 'Shim build report mismatch')
    build = json.loads((shim_root / 'report.json').read_text())
    require(build['donor_commit'] == pins['scion_commit'] and build['outcome'] == 'pass', 'Shim build lineage mismatch')
    built_sources = {row['path']: row['sha256'] for row in build['sources']}
    require(all(built_sources[name] == pins['scion'][name]['sha256'] for name in ('avf/shim/avfboot.c', 'avf/shim/start.S', 'avf/shim/avfboot.ld')), 'Shim build source mismatch')
    with shim_path.open('rb') as stream:
        image_header = read_at(stream, 0, 64, shim_path.stat().st_size)
    require(image_header[56:60] == b'ARMd', 'Shim Linux Image magic mismatch')
    text_offset, shim_image_size = struct.unpack_from('<QQ', image_header, 8)
    require(text_offset == 0 and shim_image_size >= shim_path.stat().st_size, 'Shim Image extent invalid')
    report['qualified_shim'] = {'path': str(shim_path), **pins['qualified_shim'], 'image_size_including_bss_stack': shim_image_size}
    source = texts['avf/shim/avfboot.c']
    shim_abi = boot_args_abi(source)
    kernel_abi = boot_args_abi((root / 'pexpert/pexpert/arm64/boot.h').read_text())
    require(shim_abi == kernel_abi and shim_abi['size'] == 736 and shim_abi['fields']['commandline']['offset'] == 108, 'Shim/selected ARM64 boot_args ABI differs')
    report['boot_args_abi'] = shim_abi
    constants = {}
    for name in ['KERNEL_VIRT_BASE', 'KERNEL_LINK_OFFSET', 'BASE_ALIGN', 'MAX_MEM_SIZE', 'PAGE_SIZE_MAX', 'PANIC_LOG_SIZE', 'DT_MAX', 'BOOT_LINE_LENGTH']:
        match = re.search(r'^#define\s+' + name + r'\s+(0x[0-9a-fA-F]+|[0-9]+)', source, re.M)
        require(match is not None, 'Source constant absent: ' + name)
        constants[name] = int(match[1], 0)
    require('top + 0x4000000ULL' in source, 'Source spare rule changed')
    constants['MIN_SPARE'] = 0x4000000
    constants['BOOT_ARGS_SIZE'] = 736
    constants['COMMAND_LINE_OFFSET'] = 108
    report['source_bindings'] = bindings
    report['source_pins_sha256'] = digest(pin_path)
    report['prepared_component_sha256'] = digest(component_path)
    report['rules'] = constants
    return constants


def payload(path):
    """Inspect XNUP structure without loading kernel or ramdisk into memory."""
    total = path.stat().st_size
    with path.open('rb') as stream:
        magic, size = struct.unpack('<II', read_at(stream, 0, 8, total))
        require(magic == 0x50554e58 and size + 8 == total, 'Invalid XNUP header or declared length')
        offset, entries, seen = 8, {}, set()
        for _ in range(4096):
            header = read_at(stream, offset, 24, total)
            raw_name, size, reserved = struct.unpack('<16sII', header)
            offset += 24
            name = raw_name.split(b'\0')[0].decode('ascii')
            if not name:
                require(offset == total, 'Trailing XNUP bytes')
                break
            require(name not in seen and reserved == 0, 'Duplicate/reserved XNUP entry')
            seen.add(name)
            require(offset + size <= total, 'XNUP entry out of range')
            entries[name] = {'offset': offset, 'size': size}
            offset += up(size, 16)
        else:
            raise ValueError('Too many XNUP entries')
        command = ''
        if 'cmdline' in entries:
            item = entries['cmdline']
            require(0 < item['size'] <= 608, 'Unbounded XNUP command line')
            raw = read_at(stream, item['offset'], item['size'], total)
            require(raw.endswith(b'\0') and b'\0' not in raw[:-1], 'Invalid XNUP command line termination')
            command = raw[:-1].decode('ascii')
    require('kernel' in entries, 'XNUP kernel missing')
    return {'size': total, 'entries': entries, 'sha256': digest(path), 'command_line': command}


def command_line(package, fdt_args, ramdisk, rules):
    require(isinstance(fdt_args, str) and fdt_args.isascii() and '\0' not in fdt_args, 'Invalid declared FDT bootargs')
    args = package['command_line']
    require(len(fdt_args) < rules['BOOT_LINE_LENGTH'], 'FDT bootargs would truncate')
    # This task supports the console-only layout. Refuse memory carveouts rather
    # than reporting the uncarved window for them.
    require(not any(word in fdt_args for word in ('scfb.', 'sccam.', 'scgpu.', 'scsnd.')), 'Shared-memory carveouts need a separate qualified plan')
    def has(word):
        return any(part.startswith(word) for value in (args, fdt_args) for part in value.split(' '))
    command = 'debug=0x8 ' if has('serial=') else 'debug=0x8 serial=3 '
    if not has('cpus=') and not has('cpumask='):
        command += 'cpus=1 '
    if not has('console_quiet='):
        command += 'console_quiet=1 '
    if ramdisk and not has('rd='):
        command += 'rd=md0 '
    command += args
    if fdt_args:
        command += ' ' + fdt_args
    require(len(command) < rules['BOOT_LINE_LENGTH'], 'Combined boot_args commandLine would truncate')
    return command


def macho(path, entry):
    base, length = entry['offset'], entry['size']
    with path.open('rb') as stream:
        def read(offset, size):
            require(offset >= 0 and offset + size <= length, 'Mach-O command outside kernel entry')
            return read_at(stream, base + offset, size, path.stat().st_size)
        header = struct.unpack('<8I', read(0, 32))
        magic, cpu, _, filetype, ncmds, cmd_bytes, _, _ = header
        require(magic == 0xfeedfacf and cpu == 0x100000c and filetype == 2, 'Expected little-endian ARM64 executable Mach-O')
        require(0 < ncmds <= 16384 and cmd_bytes <= 16 * 1024 * 1024 and 32 + cmd_bytes <= length, 'Invalid Mach-O command budget')
        offset, segments, sections, pc = 32, [], [], None
        for _ in range(ncmds):
            cmd, size = struct.unpack('<II', read(offset, 8))
            require(size >= 8 and size % 8 == 0 and offset + size <= 32 + cmd_bytes, 'Invalid Mach-O load command extent')
            if cmd == 0x19:
                require(size >= 72, 'Short segment command')
                fields = struct.unpack('<II16sQQQQIIII', read(offset, 72))
                _, _, name, va, vs, fo, fs, _, prot, count, _ = fields
                require(size == 72 + count * 80 and count <= 65536, 'Invalid section table')
                require(fs <= vs and fo + fs <= length, 'Segment file/BSS bounds invalid')
                add(va, vs)
                name = name.split(b'\0')[0].decode('ascii')
                segment = {'name': name, 'va': va, 'size': vs, 'fileoff': fo, 'filesize': fs, 'initprot': prot, 'zero_tail_bytes': vs - fs}
                if vs:
                    require(not any(overlap(span(va, vs), span(s['va'], s['size'])) for s in segments), 'Overlapping Mach-O segments')
                    segments.append(segment)
                for i in range(count):
                    fields = struct.unpack('<16s16sQQ8I', read(offset + 72 + i * 80, 80))
                    sn, owner, addr, extent, fileoff, align, _, _, flags, _, _, _ = fields
                    sn = sn.split(b'\0')[0].decode('ascii'); owner = owner.split(b'\0')[0].decode('ascii')
                    require(owner == name and va <= addr and add(addr, extent) <= add(va, vs), 'Section outside owning segment')
                    require(align <= 31 and addr % (1 << align) == 0, 'Invalid section alignment')
                    zero = (flags & 0xff) in (1, 0xc, 0x12)
                    if not zero and extent:
                        require(fo <= fileoff and fileoff + extent <= fo + fs, 'Section outside segment file bytes')
                        require(addr - va == fileoff - fo, 'Section file/VA displacement mismatch')
                    sections.append({'name': sn, 'segment': owner, 'va': addr, 'size': extent, 'zerofill': zero})
            elif cmd == 5:
                require(pc is None and size == 288, 'Expected one complete ARM64 LC_UNIXTHREAD')
                flavor, count = struct.unpack('<II', read(offset + 8, 8))
                require(flavor == 6 and count == 68, 'Invalid ARM64 thread state')
                pc = struct.unpack('<Q', read(offset + 16 + 32 * 8, 8))[0]
            offset += size
        require(offset == 32 + cmd_bytes and segments and pc is not None, 'Missing Mach-O segments/thread entry')
        require(any(s['va'] <= pc < s['va'] + s['filesize'] and s['initprot'] & 4 for s in segments), 'Entry is not in file-backed executable bytes')
        metadata = [s for s in sections if s['name'] in ('__kalloc_type', '__kalloc_var')]
        require(any(s['name'] == '__kalloc_type' and s['size'] for s in metadata), 'Required kalloc type section absent')
        require(all(not s['zerofill'] for s in metadata), 'kalloc metadata cannot be zero-fill')
        return {'segments': segments, 'sections': sections, 'entry_va': pc, 'kalloc_sections': metadata}


def layout_check(plan, image, package, rules):
    """Plan addresses are declared host inputs, not observations of a running guest."""
    r = rules
    required = {'ram_base', 'ram_size', 'shim_base', 'shim_image_size', 'fdt_base', 'fdt_size', 'payload_base', 'fdt_bootargs'}
    require(set(plan) == required, 'Layout fields must exactly name RAM, shim, FDT and payload extents')
    p = {key: number(value) for key, value in plan.items() if key != 'fdt_bootargs'}
    cl = command_line(package, plan['fdt_bootargs'], package['entries'].get('ramdisk', {}).get('size', 0), r)
    require(p['shim_base'] % 0x200000 == 0 and p['fdt_base'] % 8 == 0 and p['payload_base'] % 8 == 0, 'Initial Image/FDT/payload alignment invalid')
    ram = span(p['ram_base'], p['ram_size'])
    initial = {'shim': span(p['shim_base'], p['shim_image_size']), 'fdt': span(p['fdt_base'], p['fdt_size']), 'payload': span(p['payload_base'], package['size'])}
    require(p['ram_size'] and p['shim_image_size'] and 40 <= p['fdt_size'] <= 2 * 1024 * 1024, 'Empty/oversized initial layout')
    for name, extent in initial.items():
        require(ram[0] <= extent[0] < extent[1] <= ram[1], name + ' outside RAM')
    for left, right in [('shim', 'fdt'), ('shim', 'payload'), ('fdt', 'payload')]:
        require(not overlap(initial[left], initial[right]), 'Initial ' + left + '/' + right + ' overlap')
    base = up(ram[0], r['BASE_ALIGN'])
    require(ram[1] >= r['PANIC_LOG_SIZE'], 'Panic reserve underflow')
    panic = (ram[1] - r['PANIC_LOG_SIZE']) & ~(r['PAGE_SIZE_MAX'] - 1)
    end = panic & ~(r['BASE_ALIGN'] - 1)
    require(end > base, 'No aligned memory window')
    end = base + min(end - base, r['MAX_MEM_SIZE'])
    lo = min(s['va'] for s in image['segments'])
    hi = max(add(s['va'], s['size']) for s in image['segments'])
    require(lo >= r['KERNEL_VIRT_BASE'] + r['KERNEL_LINK_OFFSET'], 'Image below shim link offset')
    def physical(va):
        require(va >= r['KERNEL_VIRT_BASE'], 'VA below virtual base')
        return add(base, va - r['KERNEL_VIRT_BASE'])
    kern = [physical(lo), up(physical(hi), r['PAGE_SIZE_MAX'])]
    rdsize = up(package['entries'].get('ramdisk', {'size': 0})['size'], r['PAGE_SIZE_MAX'])
    rd = span(kern[1], rdsize)
    dt = span(rd[1], r['DT_MAX'])
    ba = span(dt[1], r['PAGE_SIZE_MAX'])
    require(add(ba[1], r['MIN_SPARE']) <= end, 'Kernel/data plus source-required 64 MiB spare do not fit')
    require(initial['shim'][1] <= kern[0], 'Shim/BSS/stack overlaps kernel destination')
    move = None
    if overlap(initial['payload'], [kern[0], ba[1]]):
        length = package['size']
        require(length <= end - base, 'Payload move subtraction underflow')
        target = (end - length) & ~(r['PAGE_SIZE_MAX'] - 1)
        require(target >= ba[1], 'No space to relocate overlapping payload')
        moved = span(target, up(length, 8))
        require(moved[1] <= end, 'Rounded payload move exceeds memory window')
        require(not overlap(moved, initial['payload']) or target >= initial['payload'][0], 'Shim backward copy cannot safely move payload downward')
        move = moved
    mapped = [{'name': s['name'], 'physical': span(physical(s['va']), s['size']), 'zero_tail_bytes': s['zero_tail_bytes']} for s in image['segments']]
    return {'input_origin': 'declared host address plan; not a runtime FDT observation', 'ram': ram, 'window': [base, end], 'panic': span(panic, r['PANIC_LOG_SIZE']),
            'kernel': kern, 'ramdisk': rd, 'apple_device_tree_capacity': dt, 'boot_args_page': ba, 'topOfKernelData': ba[1],
            'deviceTreeP_virtual': add(r['KERNEL_VIRT_BASE'], dt[0] - base), 'entry_physical': physical(image['entry_va']),
            'payload_relocation': move, 'spare_bytes': end - ba[1], 'mapped_segments': mapped,
            'boot_args': {'revision': 2, 'version': 2, 'virtBase': r['KERNEL_VIRT_BASE'], 'physBase': base, 'memSize': end - base,
                          'memSizeActual': end - base, 'size': r['BOOT_ARGS_SIZE'], 'commandLine_offset': r['COMMAND_LINE_OFFSET'], 'commandLine': cl},
            'fdt_read_before_kernel_copy': True}


def synthetic_payload():
    """Owned parser-control bytes; never an XNU kernel or reusable boot artifact."""
    va = 0xfffffff007000000
    section = struct.pack('<16s16sQQ8I', b'__kalloc_type', b'__DATA_CONST', va + 0x4000, 16, 0x4000, 3, 0, 0, 0, 0, 0, 0)
    text = struct.pack('<II16sQQQQIIII', 0x19, 72, b'__TEXT', va, 0x4000, 0, 0x4000, 7, 5, 0, 0)
    data = struct.pack('<II16sQQQQIIII', 0x19, 152, b'__DATA_CONST', va + 0x4000, 0x4000, 0x4000, 16, 3, 3, 1, 0) + section
    regs = [0] * 34; regs[32] = va + 0x800
    thread = struct.pack('<4I34Q', 5, 288, 6, 68, *regs)
    commands = text + data + thread
    header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, 3, len(commands), 0, 0)
    image = (header + commands).ljust(0x4010, b'\0')
    body = struct.pack('<16sII', b'kernel', len(image), 0) + image + b'\0' * (-len(image) % 16) + b'\0' * 24
    return struct.pack('<II', 0x50554e58, len(body)) + body


def controls(out, rules):
    path = out / 'owned-synthetic-parser-control.xnup'
    path.write_bytes(synthetic_payload())
    package = payload(path); image = macho(path, package['entries']['kernel'])
    plan = {'ram_base': 0x40000000, 'ram_size': 256 << 20, 'shim_base': 0x40200000, 'shim_image_size': 0x20000,
            'fdt_base': 0x48200000, 'fdt_size': 0x10000, 'payload_base': 0x48000000, 'fdt_bootargs': ''}
    positive = layout_check(plan, image, package, rules)
    require(positive['window'] == [0x40000000, 0x4e000000], 'Independent 256 MiB alignment oracle differs')
    require(positive['topOfKernelData'] == 0x4301c000, 'Independent boot_args placement oracle differs')
    results = [{'case': 'owned-synthetic-positive', 'outcome': 'pass', 'layout': positive}]
    def bad(name, p=None, i=None, pkg=None, mutate=None):
        try:
            if mutate:
                corrupt = out / (name + '.xnup'); corrupt.write_bytes(mutate(path.read_bytes()))
                x = payload(corrupt); macho(corrupt, x['entries']['kernel'])
            else:
                layout_check(p or plan, i or image, pkg or package, rules)
        except (ValueError, UnicodeError, struct.error) as error:
            results.append({'case': name, 'outcome': 'expected-rejection', 'reason': str(error)})
        else:
            raise ValueError('Negative control accepted: ' + name)
    bad('insufficient-ram', {**plan, 'ram_size': 128 << 20, 'payload_base': 0x41000000, 'fdt_base': 0x42000000})
    bad('ram-uint64-overflow', {**plan, 'ram_base': U64 - 4095})
    bad('initial-fdt-shim-overlap', {**plan, 'fdt_base': plan['shim_base']})
    bad('fdt-outside-ram', {**plan, 'fdt_base': 0x50000000})
    bad('unqualified-memory-carveout', {**plan, 'fdt_bootargs': 'scgpu.addr=0x45000000 scgpu.size=0x40000'})
    bad('bootargs-truncation', {**plan, 'fdt_bootargs': 'a' * 607})
    bad('shim-bss-kernel-overlap', {**plan, 'shim_image_size': 0x3000000})
    broken = copy.deepcopy(image); broken['segments'][0]['va'] -= 0x4000
    bad('below-link-offset', i=broken)
    broken = copy.deepcopy(image); broken['segments'][-1]['size'] = 1 << 30
    bad('large-image-not-assumed-to-fit', i=broken)
    bad('xnup-size-mismatch', mutate=lambda b: b[:4] + struct.pack('<I', len(b)) + b[8:])
    def patch_file_size(b):
        data = bytearray(b); struct.pack_into('<Q', data, package['entries']['kernel']['offset'] + 32 + 48, U64); return data
    bad('segment-file-extent', mutate=patch_file_size)
    def patch_entry(b):
        data = bytearray(b); struct.pack_into('<Q', data, package['entries']['kernel']['offset'] + 32 + 72 + 152 + 16 + 32 * 8, 1); return data
    bad('entry-outside-executable', mutate=patch_entry)
    def patch_metadata(b):
        data = bytearray(b); start = package['entries']['kernel']['offset'] + 32 + 72 + 72; data[start:start+16] = b'__missing'.ljust(16,b'\0'); return data
    bad('missing-kalloc-metadata', mutate=patch_metadata)
    relocation = layout_check({**plan, 'payload_base': 0x43000000}, image, package, rules)
    require(relocation['payload_relocation'] is not None, 'Required payload relocation not planned')
    results.append({'case': 'overlapping-payload-relocated', 'outcome': 'pass', 'layout': relocation})
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--main', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--controls', action='store_true')
    ap.add_argument('--payload', type=Path)
    ap.add_argument('--layout', type=Path)
    args = ap.parse_args()
    require(bool(args.payload) == bool(args.layout), '--payload and --layout must be provided together')
    output_root = Path(__file__).resolve().parents[2] / 'artifacts/avf-guest-boot-memory'
    require(args.out.resolve().is_relative_to(output_root.resolve()) and args.out.resolve() != output_root.resolve(), 'Output must be a fresh task-local artifacts/avf-guest-boot-memory child')
    cap = 256 * 1024 * 1024
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    report = {'task': 'VM-026', 'kind': 'source-derived-host-preflight', 'started_at': datetime.now(timezone.utc).isoformat(),
              'argv': sys.argv, 'commands': [], 'outcome': 'inconclusive', 'xnu_executed': False, 'compiler_executed': False,
              'qemu_executed': False, 'runtime_mmu_verified': False, 'genuine_final_image_measured': False,
              'tools': {'python': {'path': sys.executable, 'sha256': digest(sys.executable)}, 'script_sha256': digest(__file__),
                        'git': {'path': shutil.which('git'), 'sha256': digest(shutil.which('git'))}},
              'limits': {'address_space_bytes': cap, 'source_read_deadline_seconds': 15, 'git_lazy_fetch': False, 'git_optional_locks': False},
              'limitations': ['A passing layout is necessary, not sufficient, for boot.', 'No final genuine XNU kernel was available during source preparation.',
                              'Host address plan is not an observed runtime FDT. Excludes extra scfb/sccam/scgpu/scsnd carveouts.',
                              'Does not establish boot-time allocator demand, metadata ABI, actual page-table execution, or 256 MiB sufficiency.']}
    exit_code = 0
    try:
        rules = source_rules(args.main.resolve(), report)
        if args.controls:
            report['controls'] = controls(args.out, rules)
        if args.payload:
            pkg = payload(args.payload)
            image = macho(args.payload, pkg['entries']['kernel'])
            report['payload'] = pkg; report['image'] = image
            report['layout_sha256'] = digest(args.layout)
            plan = json.loads(args.layout.read_text())
            require(number(plan['shim_image_size']) == report['qualified_shim']['image_size_including_bss_stack'], 'Declared shim size excludes qualified Image/BSS/stack')
            report['layout'] = layout_check(plan, image, pkg, rules)
            report['layout_preflight'] = 'pass'
        report['source_preflight'] = 'pass'
        report['outcome'] = 'pass' if args.controls or args.payload else 'inconclusive'
    except (ValueError, OSError, subprocess.SubprocessError, UnicodeError, struct.error, KeyError) as error:
        report['outcome'] = 'fail'; report['error'] = str(error); exit_code = 2
    finally:
        report['seconds'] = time.monotonic() - start
        report['exit_code'] = exit_code
        status = Path('/proc/self/status').read_text()
        report['proc_status_memory_kib'] = {k: int(v) for k,v in re.findall(r'^(VmHWM|VmRSS):\s+(\d+) kB', status, re.M)}
        report['output_hashes'] = {p.name: digest(p) for p in args.out.iterdir() if p.is_file()}
        (args.out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'outcome': report['outcome'], 'evidence': str(args.out / 'evidence.json'), 'exit_code': exit_code}))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
