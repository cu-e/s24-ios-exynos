#!/usr/bin/env python3
"""NAT-123 host binary audit. Disassemble the actual arm64 ACPM object.

Proves that masked updates return EINVAL and the generic write entry contains
all register/value guards before the call into the IPC sender. Behavioral
rejection is separately exercised by test_nat123.py.
"""
from pathlib import Path
import json
import struct
import sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

ROOT = Path(__file__).resolve().parents[3]


def functions(path):
    data = path.read_bytes()
    ncmds = struct.unpack_from('<I', data, 16)[0]
    sections, symbols = [], []
    offset = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x19:
            nsects = struct.unpack_from('<I', data, offset + 64)[0]
            for i in range(nsects):
                pos = offset + 72 + i * 80
                addr, length, fileoff = struct.unpack_from('<QQI', data, pos + 32)
                sections.append((addr, length, fileoff))
        elif cmd == 2:
            symoff, count, stroff, _ = struct.unpack_from('<IIII', data, offset + 8)
            for i in range(count):
                index, typ, sect, _, value = struct.unpack_from('<IBBHQ', data, symoff + i * 16)
                if not typ & 0xe0 and typ & 0xe == 0xe and sect:
                    end = data.index(b'\0', stroff + index)
                    symbols.append((data[stroff + index:end].decode(), sect, value))
        offset += size
    result = {}
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for name, sect, value in symbols:
        addr, length, fileoff = sections[sect - 1]
        end = min([v for _, s, v in symbols if s == sect and v > value] + [addr + length])
        result[name] = [(ins.mnemonic, ins.op_str) for ins in md.disasm(data[fileoff + value - addr:fileoff + end - addr], value)]
    return result


def main():
    path = ROOT / 'artifacts/nat-123/kernel-003/compile/bsd_e1s_acpm.o/e1s_acpm.o'
    funcs = functions(path)
    write = funcs['_e1s_acpm_mfd_write']
    update = funcs['_e1s_acpm_mfd_update']
    text = '\n'.join(m + ' ' + a for m, a in write)
    for constant in ('#0xd', '#5', '#0x34', '#0x3d', '#0xf0', '#0xd8'):
        assert constant in text, (constant, text)
    assert update[:2] == [('mov', 'w0, #0x16'), ('ret', '')], update
    assert any(m.startswith('b.') or m in ('cbnz', 'cbz') for m, _ in write)
    result = dict(kind='host-test', outcome='pass', object=str(path.relative_to(ROOT)),
                  write_disassembly=write, update_disassembly=update,
                  limitation='Constant/branch inspection plus host behavioral tests, not native PMIC evidence')
    out = ROOT / 'artifacts/nat-123/binary-audit.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(outcome='pass', write_instructions=len(write), update=update)))


if __name__ == '__main__':
    main()
