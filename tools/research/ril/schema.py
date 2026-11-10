#!/usr/bin/env python3
"""CELL-009: offline static schema inventory of the BYH3 Samsung vendor RIL.

Reads only the two CELL-011 copies, checked against their recorded SHA-256, with
the pinned NDK 28.2.13676358 llvm-nm/llvm-objdump. The libraries are never loaded
or executed, and nothing is sent to a device. It writes:

  artifacts/ril-schema/RUN/symbols.txt        full demangled export list (local only)
  artifacts/ril-schema/RUN/report.json        everything below plus counts
  fixtures/public/ril/schema-byh3.json        (with --publish) the domain schema only

What is established is the name and C++ parameter types of each IPC 4.1 request
builder (IpcTx*) and the name of each response/notification parser (IpcRx*), per
protocol group. The frame header layout is read from the formatter that prints it.
Numeric main/sub command IDs and payload layouts are not recovered and are
reported as unknown.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
CAPTURE = ROOT/'artifacts/ril-root-capture/session-001'
LIBS = {
    'libsec-ril.so': (5459848, 'fa4c0b63dfb37f91af77710bc8ba4cea064a00adc3707ca2d2ab0e51df4c04ae'),
    'libsecril-client.so': (134368, '458cb6bec12d340d6576a13bf5e5f499fd86061b08087c0cef91642309d8adfb'),
}
NDK = '28.2.13676358'
BIN = Path('/home/egor/Android/Sdk/ndk')/NDK/'toolchains/llvm/prebuilt/linux-x86_64/bin'
DOMAINS = {
    'sim': ['Sim', 'Sap', 'Pb', 'Stk'],
    'registration': ['Net', 'JsonNet', 'IilNet'],
    'pdp': ['Data', 'JsonData', 'IilData'],
    'sms': ['Sms', 'IilSms', 'Mms'],
    'ims': ['Ims', 'Qmiims', 'IilIil'],
}
APDU = re.compile(r'Apdu|Transmit|Exchange|Channel|Pcsc|Atr|UiccAuth|ImsAuth|Gsim|RSIM', re.I)
HEADER_FORMAT = '%s %3s (M)%s (S)%s (T)%s l:%x m:%02x a:%02x [ '
COMMANDS = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv):
    x = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=300)
    COMMANDS.append(dict(argv=[str(a) for a in argv], exit_code=x.returncode, stdout_bytes=len(x.stdout)))
    if x.returncode:
        raise RuntimeError(f'{argv[0]} exit {x.returncode}: {x.stderr[-400:]}')
    return x.stdout


def cstring(data, vaddr):
    phoff = struct.unpack_from('<Q', data, 0x20)[0]
    size, count = struct.unpack_from('<HH', data, 0x36)
    for i in range(count):
        kind, _flags, off, va, _pa, filesz, _memsz, _align = struct.unpack_from('<IIQQQQQQ', data, phoff+i*size)
        if kind == 1 and va <= vaddr < va+filesz:
            start = off+vaddr-va
            return data[start:data.index(b'\0', start)].decode(errors='replace')
    return None


def header_layout(lib, data):
    """Read IpcProtocol::MakeHeader: which header bytes feed which printed field."""
    asm = run([BIN/'llvm-objdump', '-d', '--no-show-raw-insn', '--disassemble-symbols=_ZN11IpcProtocol10MakeHeaderEPcbPKc', lib])
    loads = re.findall(r'ldr(b|h)\s+w\d+, \[x19(?:, #(0x[0-9a-f]+))?\]', asm)
    offsets = sorted({(kind, int(off, 16) if off else 0) for kind, off in loads}, key=lambda x: x[1])
    pages = re.findall(r'adrp\s+x3, (0x[0-9a-f]+)\n.*?add\s+x3, x3, #(0x[0-9a-f]+)', asm)
    fmt = cstring(data, int(pages[0][0], 16)+int(pages[0][1], 16)) if pages else None
    return dict(function='IpcProtocol::MakeHeader(char*, bool, char const*)', loads=[dict(width='u16' if k == 'h' else 'u8', offset=o) for k, o in offsets],
                format_string=fmt, format_matches_expected=fmt == HEADER_FORMAT)


def tx_ids(lib):
    """Header constants that each IpcTx* function stores: strh IMM at base+4 and strb IMM at base+6.

    IMM16 = sub << 8 | main (little endian bytes 4 and 5), the strb is the type byte.
    Only constants loaded by mov into the stored register in the same function count.
    """
    mangled = [l.split()[-1] for l in run([BIN/'llvm-nm', '-D', '--defined-only', lib]).splitlines()
               if re.search(r'IpcProtocol41[A-Za-z]+\d+IpcTx', l.split()[-1])]
    names = run_input([BIN/'llvm-cxxfilt'], '\n'.join(mangled)+'\n').splitlines()
    asm = run([BIN/'llvm-objdump', '-d', '--no-show-raw-insn', '--disassemble-symbols='+','.join(mangled), lib])
    found, current, regs, h16, b8 = {}, None, {}, [], []

    def close():
        if current is not None:
            cands = sorted({(v & 0xff, v >> 8, t) for base, off, v in h16 for base2, off2, t in b8 if base2 == base and off2 == off+2})
            found[current] = cands
    by_mangled = dict(zip(mangled, names))
    for line in asm.splitlines():
        m = re.match(r'^[0-9a-f]+ <(.+)>:$', line)
        if m:
            close()
            current, regs, h16, b8 = by_mangled.get(m.group(1), m.group(1)), {}, [], []
            continue
        m = re.search(r'\tmov\tw(\d+), #(0x[0-9a-f]+)', line)
        if m:
            regs[m.group(1)] = int(m.group(2), 16)
            continue
        m = re.search(r'\tstr(h|b)\tw(\d+), \[(sp|x\d+), #(0x[0-9a-f]+)\]', line)
        if m and m.group(2) in regs:
            kind, reg, base, off = m.group(1), m.group(2), m.group(3), int(m.group(4), 16)
            if kind == 'h' and regs[reg] <= 0xffff:
                h16.append((base, off, regs[reg]))
            elif kind == 'b' and regs[reg] <= 0xff:
                b8.append((base, off, regs[reg]))
    close()
    return found


def run_input(argv, text):
    x = subprocess.run([str(a) for a in argv], input=text, capture_output=True, text=True, timeout=300)
    COMMANDS.append(dict(argv=[str(a) for a in argv], exit_code=x.returncode, stdout_bytes=len(x.stdout)))
    if x.returncode:
        raise RuntimeError(f'{argv[0]} exit {x.returncode}')
    return x.stdout


def parse(symbols):
    groups = {}
    for line in symbols:
        m = re.match(r'^IpcProtocol41([A-Za-z]+)::(IpcTx|IpcRx)([A-Za-z0-9_]+)\((.*)\)$', line)
        if not m:
            continue
        group, kind, name, params = m.groups()
        entry = groups.setdefault(group, dict(requests={}, parsers={}))
        bucket = entry['requests' if kind == 'IpcTx' else 'parsers']
        bucket.setdefault(name, set()).add(params)
    return {g: dict(requests={n: sorted(p) for n, p in sorted(v['requests'].items())}, parsers=sorted(v['parsers'])) for g, v in sorted(groups.items())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--publish', action='store_true')
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise SystemExit('Invalid run name')
    out = ROOT/'artifacts/ril-schema'/args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, task='CELL-009', kind='host-test', origin='local-host', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  analyzer=dict(path='tools/research/ril/schema.py', sha256=sha(__file__), ndk=NDK), inputs={}, executed_inputs=False, device_used=False)
    for name, (size, digest) in LIBS.items():
        f = CAPTURE/name
        actual = (f.stat().st_size, sha(f))
        if actual != (size, digest):
            raise SystemExit(f'{name}: {actual} is not the recorded {(size, digest)}')
        report['inputs'][name] = dict(bytes=size, sha256=digest, source='CELL-011 read-only su copy of /vendor/lib64/'+name)
    lib = CAPTURE/'libsec-ril.so'
    data = lib.read_bytes()
    report['tools'] = {t: run([BIN/t, '--version']).splitlines()[0:2] for t in ('llvm-nm', 'llvm-objdump')}
    needed = re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', run([BIN/'llvm-readelf', '-d', lib]))
    symbols = sorted({' '.join(l.split()[2:]) for l in run([BIN/'llvm-nm', '-D', '--defined-only', '-C', lib]).splitlines() if len(l.split()) > 2})
    (out/'symbols.txt').write_text('\n'.join(symbols)+'\n')
    strings = set(re.findall(rb'[\x20-\x7e]{6,}', data))
    groups = parse(symbols)
    transport = dict(
        device_nodes=sorted(s.decode() for s in strings if re.fullmatch(rb'/dev/(umts|nr)_[a-z]+[0-9]', s)),
        io_classes=sorted({l.split('::')[0] for l in symbols if re.match(r'^[A-Za-z]*IoChannel[A-Za-z]*::', l)}),
        io_entry_points=sorted(l for l in symbols if re.match(r'^IpcModem::(SendMessage|SendMessageSync|ReceiveMessage|SendRawIpc)\(', l)),
        frame_header=header_layout(lib, data),
        interpretation='u16 length @0, u8 main-sequence @2, u8 ack-sequence @3, u8 main command @4, u8 sub command @5, u8 type @6 '
                       '(the formatter prints l/m/a from bytes 0-3 and resolves M, S and T names from bytes 4, 5 and 6).')
    ids = tx_ids(lib)
    def id_of(group, name, params):
        cands = sorted({c for p in params for c in ids.get(f'IpcProtocol41{group}::IpcTx{name}({p})', [])})
        if len(cands) == 1:
            main_, sub_, type_ = cands[0]
            return dict(status='recovered', main=main_, sub=sub_, type=type_)
        return dict(status='ambiguous', candidates=[list(c) for c in cands]) if cands else dict(status='unknown')
    for g, v in groups.items():
        v['request_ids'] = {n: id_of(g, n, p) for n, p in v['requests'].items()}
    id_status = {}
    for v in groups.values():
        for r in v['request_ids'].values():
            id_status[r['status']] = id_status.get(r['status'], 0)+1
    schema = {}
    for domain, members in DOMAINS.items():
        sel = {g: groups[g] for g in members if g in groups}
        d = dict(groups=sorted(sel), requests={f'{g}.{n}': dict(params=p, header=v['request_ids'][n]) for g, v in sel.items() for n, p in v['requests'].items()},
                 parsers=[f'{g}.{n}' for g, v in sel.items() for n in v['parsers']])
        if domain == 'sim':
            d['apdu_related'] = sorted(['request '+k for k in d['requests'] if APDU.search(k.split('.', 1)[1])] +
                                       ['parser '+k for k in d['parsers'] if APDU.search(k.split('.', 1)[1])])
        schema[domain] = d
    other = sorted(set(groups) - {g for m in DOMAINS.values() for g in m})
    report.update(needed=needed, exported_symbols=len(symbols),
                  counts=dict(groups=len(groups), requests=sum(len(v['requests']) for v in groups.values()), parsers=sum(len(v['parsers']) for v in groups.values()),
                              per_group={g: [len(v['requests']), len(v['parsers'])] for g, v in groups.items()}),
                  transport=transport, schema=schema, other_groups=other,
                  request_id_status=id_status,
                  unknown=['main/sub/type for requests marked unknown or ambiguous, and for every parser (dispatch not traced)', 'payload field layouts and lengths',
                           'which requests the BYH3 modem firmware actually accepts', 'behaviour of any command on hardware'],
                  checks=dict(header_format_found=transport['frame_header']['format_matches_expected'],
                              header_bytes_read=[l['offset'] for l in transport['frame_header']['loads']] == [0, 2, 3, 4, 5, 6],
                              domains_non_empty=all(schema[d]['requests'] for d in DOMAINS),
                              control_GetAtr_is_main5_sub0x0a_type2=groups['Sim']['request_ids'].get('GetAtr') == dict(status='recovered', main=5, sub=10, type=2)))
    report['outcome'] = 'pass' if all(report['checks'].values()) else 'fail'
    report['commands'] = COMMANDS
    (out/'report.json').write_text(json.dumps(report, indent=1)+'\n')
    if args.publish and report['outcome'] == 'pass':
        public = dict(schema='byh3-ril-ipc41-static-v1', task='CELL-009', inputs=report['inputs'], analyzer=report['analyzer'], transport=transport,
                      domains=schema, other_groups=other, counts=report['counts'], unknown=report['unknown'], request_id_status=id_status,
                      note='Names and C++ parameter types from the export table of the proprietary library; no code or binary is included. Static inference only, not a hardware result.')
        target = ROOT/'fixtures/public/ril/schema-byh3.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(public, indent=1)+'\n')
        report['published'] = dict(path=str(target.relative_to(ROOT)), sha256=sha(target))
        (out/'report.json').write_text(json.dumps(report, indent=1)+'\n')
    print(json.dumps(dict(outcome=report['outcome'], checks=report['checks'], counts={k: v for k, v in report['counts'].items() if k != 'per_group'},
                          published=report.get('published')), indent=1))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
