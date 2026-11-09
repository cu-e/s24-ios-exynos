#!/usr/bin/env python3
"""Check the linked kernel with a parser written here and with the Mach-O tools.

The link executor already ran the pinned bounded parser. This adds a separate
reading of the same bytes, so one parser's mistake cannot pass unnoticed. Runs
no compiler or linker and never executes the image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
TOOLS = MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-'
LINK_ADDRESS = 0xfffffff007004000
SEGMENTS = ['__TEXT', '__DATA_CONST', '__TEXT_EXEC', '__KLD', '__LASTDATA_CONST', '__LAST', '__KLDDATA', '__DATA', '__BOOTDATA', '__PRELINK_TEXT',
            '__PRELINK_INFO', '__PLK_TEXT_EXEC', '__PRELINK_DATA', '__PLK_DATA_CONST', '__PLK_LLVM_COV', '__PLK_LINKEDIT', '__LINKINFO', '__LINKEDIT']
LC_SEGMENT_64, LC_UNIXTHREAD, LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_MAIN = 0x19, 0x5, 0xc, 0x80000018, 0x80000028
ARM_THREAD_STATE64 = 6


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse(data):
    magic, cpu, _subtype, filetype, count, size, flags, _reserved = struct.unpack_from('<IiiIIIII', data, 0)
    require(magic == 0xfeedfacf and cpu == 0x0100000c and filetype == 2, 'Not an ARM64 MH_EXECUTE')
    segments, entry, dylibs, at = [], None, 0, 32
    require(32+size <= len(data), 'Load commands exceed the file')
    for _ in range(count):
        cmd, length = struct.unpack_from('<II', data, at)
        require(8 <= length and at+length <= 32+size and length % 8 == 0, 'Malformed load command')
        if cmd == LC_SEGMENT_64:
            name = data[at+8:at+24].rstrip(b'\0').decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, at+24)
            require(fileoff+filesize <= len(data), 'Segment exceeds the file: '+name)
            require(filesize <= vmsize, 'Segment stores more than it maps: '+name)
            segments.append(dict(name=name, vmaddr=vmaddr, vmsize=vmsize, fileoff=fileoff, filesize=filesize))
        elif cmd == LC_UNIXTHREAD:
            flavor, words = struct.unpack_from('<II', data, at+8)
            require(flavor == ARM_THREAD_STATE64 and words == 68, 'Unexpected thread state')
            entry = struct.unpack_from('<Q', data, at+16+32*8)[0]  # x0..x28, fp, lr, sp, then pc
        elif cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB):
            dylibs += 1
        elif cmd == LC_MAIN:
            raise ValueError('A kernel must not use LC_MAIN')
        at += length
    return dict(flags=flags, load_commands=count, segments=segments, entry=entry, dylibs=dylibs)


def tool(name, *args):
    done = subprocess.run([str(TOOLS)+name, *args], capture_output=True, text=True, timeout=120)
    require(done.returncode == 0, name+' failed: '+done.stderr[-500:])
    return done.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    evidence = json.loads(args.evidence.read_text())
    require(evidence['outcome'] == 'pass' and evidence['link_executed'] is True and not evidence['owned_survivors'], 'Link evidence is not a clean pass')
    image = args.evidence.parent/'kernel/kernel.unstripped'
    data = image.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    require(digest == evidence['image']['sha256'], 'Image differs from the link evidence')

    view = parse(data)
    names = [s['name'] for s in view['segments']]
    require(names == SEGMENTS, 'Segment order differs: '+repr(names))
    segments = {s['name']: s for s in view['segments']}
    require(segments['__TEXT']['vmaddr'] == LINK_ADDRESS, '__TEXT is not at the configured link address')
    require(segments['__TEXT']['fileoff'] == 0, '__TEXT must start the file')
    require(view['dylibs'] == 0, 'A kernel must load no dylibs')
    execute = segments['__TEXT_EXEC']
    require(view['entry'] is not None and execute['vmaddr'] <= view['entry'] < execute['vmaddr']+execute['vmsize'], 'Entry is outside __TEXT_EXEC')
    # Compare with what the executor's own parser reported from the same bytes.
    require(view['entry'] == evidence['image']['entry'], 'Parsers disagree on the entry')
    require([(s['name'], s['address'], s['size']) for s in evidence['image']['segments']] == [(s['name'], s['vmaddr'], s['vmsize']) for s in view['segments']], 'Parsers disagree on segments')

    undefined = tool('nm', '-u', str(image)).split()
    require(not undefined, 'Undefined symbols remain: '+repr(undefined[:20]))
    symbols = tool('nm', str(image)).splitlines()
    start = [line.split() for line in symbols if line.endswith(' __start')]
    require(len(start) == 1 and int(start[0][0], 16) == view['entry'], 'Entry is not the unique __start symbol')
    uuid_lines = [line.strip() for line in tool('otool', '-l', str(image)).splitlines() if line.strip().startswith('uuid ')]
    require(len(uuid_lines) == 1, 'Expected one LC_UUID')

    record = dict(schema='e1s-native-image-verification-v1', kind='host-test', origin='local-host', outcome='pass', image=str(image), sha256=digest, bytes=len(data),
                  architecture='arm64', filetype='MH_EXECUTE', segments=names, link_address=hex(LINK_ADDRESS), entry=hex(view['entry']), entry_symbol='__start',
                  undefined_symbols=0, dylib_load_commands=0, symbols_listed=len(symbols), independent_parser_agrees_with_executor=True, image_executed=False,
                  not_established=['That the image boots or that __start reaches any later code.', 'private37 ABI obligations; STR-037 stays open.', 'check_all_exports: the native DEVELOPMENT driver has no RELEASE export-list flag, so it was not run.', 'Any physical memory layout, Exynos or QEMU behaviour.'])
    (args.out/'verify.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({k: record[k] for k in ['outcome', 'sha256', 'bytes', 'entry', 'undefined_symbols', 'symbols_listed']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
