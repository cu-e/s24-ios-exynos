#!/usr/bin/env python3
"""Package an owned static ARM64 executable as a raw mockfs memory root.

This performs bounded structural checks, never executable, ABI or boot qualification.
The selected source implements no on-disk mockfs header or directory table.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

ALIGNMENT = 0x4000  # Selected avfboot.c PAGE_SIZE_MAX; memdev units are 4 KiB.
MAX_BYTES = 16 * 1024 * 1024  # Owned minimal PID1 policy, not a kernel limit.
MAX_COMMAND_BYTES = 1024 * 1024
MAX_COMMANDS = 1024
CHUNK = 64 * 1024
UINT64 = 1 << 64


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def extent(offset, length, limit, name):
    require(0 <= offset <= limit and 0 <= length <= limit - offset,
            name + ' exceeds bounds')


def parse(stream, length):
    """Read only a bounded command table; all file extents use actual input size."""
    require(32 <= length <= MAX_BYTES, 'executable size outside owned policy')
    stream.seek(0)
    header = stream.read(32)
    require(len(header) == 32, 'truncated Mach-O header')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack('<8I', header)
    require((magic, cpu, subtype, kind) == (0xFEEDFACF, 0x0100000C, 0, 2),
            'need thin little-endian ARM64_ALL MH_EXECUTE')
    require(reserved == 0, 'nonzero reserved Mach-O header')
    require(0 < count <= MAX_COMMANDS and count * 8 <= size <= MAX_COMMAND_BYTES,
            'invalid Mach-O command count/size')
    extent(32, size, length, 'load commands')
    table = stream.read(size)
    require(len(table) == size, 'truncated load commands')
    segments, entry, offset = [], None, 0
    for _ in range(count):
        extent(offset, 8, size, 'load command header')
        cmd, n = struct.unpack_from('<II', table, offset)
        require(n >= 8 and n % 8 == 0, 'invalid load command size/alignment')
        extent(offset, n, size, 'load command')
        if cmd == 0x19:  # LC_SEGMENT_64
            require(n >= 72, 'short LC_SEGMENT_64')
            _, _, name, va, vs, fo, fs, maximum, initial, sections, sf = struct.unpack_from(
                '<II16sQQQQiiII', table, offset)
            require(n == 72 + sections * 80, 'segment section count mismatch')
            extent(va, vs, UINT64, 'segment virtual range')
            extent(fo, fs, length, 'segment file range')
            require(fs <= vs and initial >= 0 and maximum >= 0 and
                    initial & ~maximum == 0 and maximum & ~7 == 0,
                    'invalid segment size/protections')
            for i in range(sections):
                s = offset + 72 + i * 80
                addr, ssize, soff, salign, roff, nr, sflags = struct.unpack_from('<QQ5I', table, s + 32)
                extent(addr - va, ssize, vs, 'section virtual range')
                require(salign <= 31, 'section alignment outside policy')
                if sflags & 0xFF not in (1, 0xC, 0x12):
                    extent(soff - fo, ssize, fs, 'section file range')
                extent(roff, nr * 8, length, 'section relocation range')
            segments.append({'name': name.rstrip(b'\0').decode('ascii', errors='strict'),
                             'vmaddr': va, 'vmsize': vs, 'fileoff': fo,
                             'filesize': fs, 'initprot': initial})
        elif cmd == 5:  # LC_UNIXTHREAD / ARM_THREAD_STATE64
            require(entry is None and n == 288 and
                    struct.unpack_from('<II', table, offset + 8) == (6, 68),
                    'need one ARM_THREAD_STATE64 LC_UNIXTHREAD')
            entry = struct.unpack_from('<Q', table, offset + 272)[0]
        elif cmd == 2:  # LC_SYMTAB
            require(n == 24, 'invalid LC_SYMTAB')
            so, ns, st, ss = struct.unpack_from('<4I', table, offset + 8)
            extent(so, ns * 16, length, 'symbol table')
            extent(st, ss, length, 'string table')
        elif cmd == 0xB:  # LC_DYSYMTAB: table extents in the 64-bit format.
            require(n == 80, 'invalid LC_DYSYMTAB')
            values = struct.unpack_from('<18I', table, offset + 8)
            for a, width in ((6, 8), (8, 56), (10, 4), (12, 4), (14, 8), (16, 8)):
                extent(values[a], values[a + 1] * width, length, 'dynamic symbol auxiliary table')
        elif cmd in (0x1D, 0x26, 0x29):  # Code signature, function starts, data in code.
            require(n == 16, 'invalid linkedit data command')
            extent(*struct.unpack_from('<II', table, offset + 8), length, 'linkedit data')
        elif cmd == 0x32:  # LC_BUILD_VERSION, each build_tool_version is 8 bytes.
            require(n >= 24 and n == 24 + struct.unpack_from('<I', table, offset + 20)[0] * 8,
                    'invalid LC_BUILD_VERSION')
        elif cmd in (0x1B, 0x25, 0x2A):  # UUID, iPhoneOS version, source version.
            require(n == (24 if cmd == 0x1B else 16), 'invalid metadata command')
        else:
            raise ValueError(f'unsupported or dynamic load command 0x{cmd:x}')
        offset += n
    require(offset == size, 'unconsumed load command bytes')
    require(entry is not None and 0 < entry < (1 << 47), 'missing or non-user ARM64 entry')
    require(any(s['fileoff'] == 0 and s['filesize'] >= 32 + size for s in segments),
            'Mach-O header/commands absent from file-backed segment')
    require(any(s['initprot'] & 4 and s['vmaddr'] <= entry < s['vmaddr'] + s['filesize']
                for s in segments), 'entry outside file-backed executable segment')
    for i, a in enumerate(segments):
        for b in segments[i + 1:]:
            for base, size_key in (('vmaddr', 'vmsize'), ('fileoff', 'filesize')):
                require(not (a[size_key] and b[size_key] and
                             a[base] < b[base] + b[size_key] and
                             b[base] < a[base] + a[size_key]), 'overlapping segment ranges')
    return {'format': 'thin-arm64-static-unixthread', 'entry': hex(entry),
            'commands': count, 'segments': segments, 'executable_bytes': length}


def open_input(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, 'rb')
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        stream.close()
        raise ValueError('input must be a regular file, without symlinks')
    return stream, st


def pack(source, expected, provenance, out):
    require(len(expected) == 64 and all(c in '0123456789abcdef' for c in expected),
            'need lowercase SHA256 input binding')
    require(Path(provenance).stat().st_size <= CHUNK, 'provenance descriptor too large')
    origin = json.loads(Path(provenance).read_text())
    require(isinstance(origin, dict), 'provenance must be an object')
    require(origin.get('origin') in ('owned-source-built', 'synthetic-structural-control') and
            origin.get('input_sha256') == expected, 'provenance origin/hash mismatch')
    require(bool(origin.get('sources')) and bool(origin.get('build_evidence')),
            'provenance must identify sources and build evidence')
    stream, before = open_input(source)
    with stream:
        parsed = parse(stream, before.st_size)
        # Destination must be new. A failed attempt remains available for inspection.
        out.mkdir(parents=True, exist_ok=False)
        h = hashlib.sha256()
        with (out / 'root.ramdisk').open('xb') as dest:
            stream.seek(0)
            remaining = before.st_size
            while remaining:
                block = stream.read(min(CHUNK, remaining))
                require(bool(block), 'input truncated while copying')
                dest.write(block)
                h.update(block)
                remaining -= len(block)
            require(not stream.read(1), 'input grew while copying')
            after = os.fstat(stream.fileno())
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'input changed while copying')
            require(h.hexdigest() == expected, 'input SHA256 mismatch')
            dest.write(bytes(-before.st_size % ALIGNMENT))
    report = {'schema_version': 1, 'kind': 'host-test', 'format': 'mockfs-raw-executable-v1',
              'mount_argument': 'rd=md0', 'executable_path': '/sbin/launchd',
              'alignment': ALIGNMENT, 'input_sha256': expected, 'provenance': origin,
              'provenance_descriptor_sha256': digest(Path(provenance)),
              'packager_sha256': digest(Path(__file__)),
              'source_bindings_sha256': digest(Path(__file__).resolve().parents[2] /
                                               'fixtures/public/avf-guest-mockfs/sources.json'),
              'image_bytes': (out / 'root.ramdisk').stat().st_size,
              'image_sha256': digest(out / 'root.ramdisk'), 'mach_o': parsed,
              'executable_qualified': False, 'guest_executed': False}
    (out / 'package.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return verify(out)


def verify(out):
    require((out / 'package.json').stat().st_size <= MAX_COMMAND_BYTES, 'package metadata too large')
    report = json.loads((out / 'package.json').read_text())
    require(report['schema_version'] == 1 and report['format'] == 'mockfs-raw-executable-v1',
            'invalid package schema')
    n = report['mach_o']['executable_bytes']
    require(isinstance(n, int) and 32 <= n <= MAX_BYTES, 'invalid executable length')
    image, st = open_input(out / 'root.ramdisk')
    with image:
        require(st.st_size == report['image_bytes'] == n + (-n % ALIGNMENT),
                'image length/alignment mismatch')
        require(report['alignment'] == ALIGNMENT and report['mount_argument'] == 'rd=md0' and
                report['executable_path'] == '/sbin/launchd', 'invalid mockfs mapping')
        require(parse(image, n) == report['mach_o'], 'Mach-O description mismatch')
        image.seek(0)
        h = hashlib.sha256()
        remaining = n
        while remaining:
            block = image.read(min(CHUNK, remaining))
            require(bool(block), 'truncated executable')
            h.update(block)
            remaining -= len(block)
        require(h.hexdigest() == report['input_sha256'] == report['provenance']['input_sha256'],
                'executable hash mismatch')
        require(not any(image.read(ALIGNMENT)), 'nonzero image padding')
    require(digest(out / 'root.ramdisk') == report['image_sha256'], 'image hash mismatch')
    require(report['guest_executed'] is False and report['executable_qualified'] is False,
            'structural package cannot claim execution qualification')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pack')
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--input-sha256', required=True)
    p.add_argument('--provenance', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('verify')
    p.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    def memory():
        for row in Path('/proc/self/status').read_text().splitlines():
            if row.startswith('VmHWM:'):
                return int(row.split()[1]) * 1024
        return None
    try:
        result = pack(args.input, args.input_sha256, args.provenance, args.out) if args.command == 'pack' else verify(args.package)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, struct.error) as error:
        print(json.dumps({'outcome': 'fail', 'error': str(error),
                          'proc_self_VmHWM_bytes': memory()}), file=sys.stderr)
        return 1
    result['proc_self_VmHWM_bytes'] = memory()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
