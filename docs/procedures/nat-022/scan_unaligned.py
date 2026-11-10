#!/usr/bin/env python3
"""List AArch64 unscaled loads/stores whose immediate is not a multiple of the access size (NAT-027). Host only.

usage: scan_unaligned.py IMAGE [--elf LOADER_ELF] [--end N]

Why: the NAT-020 loader runs with the MMU off, so every data access is Device memory and must be
naturally aligned. Native run 005 stopped on `stur x19, [x11, #0x24]` (adt_patch.c writing a 64-bit
ADT property value that is only 4-byte aligned): the compiler emits the *unscaled* LDUR/STUR form
exactly when the offset is not a multiple of the access size, so such an instruction in the image is a
compile-time-visible misaligned access whenever the base register is aligned.

What this does and does not see:
  * it decodes the general-register LDUR/STUR/LDURS* family (V=0) and reports imm9 % size != 0;
  * with --elf only the .text range is scanned and bytes covered by `$d` mapping symbols are skipped;
    without it, --end limits the scan (default: the whole file; data words may then decode by accident);
  * it does NOT see addresses computed at run time (e.g. `ldr x9, [x8]` after `add x8, x0, #36`);
    check_payload.py runs adt_patch.c under gcc's alignment trap for the ADT code.
Output: one line per finding, then `total N`. Exit status 1 if N > 0. This is a static host check,
not evidence about the phone.
"""
import argparse, bisect, re, struct, subprocess, sys

MASK, VALUE = 0x3f200c00, 0x38000000   # size[31:30] 111 V=0 00 opc[23:22] 0 imm9 00 Rn Rt

def access_size(size, opc):
    """Bytes accessed by an unscaled general-register load/store, or 0 when it is not an access."""
    if opc in (0, 1):
        return 1 << size
    if opc == 2:
        return {0: 1, 1: 2, 2: 4}.get(size, 0)     # LDURSB/LDURSH/LDURSW; size 3 is PRFUM (no access)
    return {0: 1, 1: 2}.get(size, 0)               # opc 3: LDURSB/LDURSH to a W register

def scan_words(data, base=0, skip=lambda a: False):
    """Yield (address, word, imm9, size) for each misaligned unscaled access in data."""
    for o in range(0, len(data) - 3, 4):
        a = base + o
        if skip(a):
            continue
        w = struct.unpack_from('<I', data, o)[0]
        if w & MASK != VALUE:
            continue
        sz = access_size(w >> 30, (w >> 22) & 3)
        imm = (w >> 12) & 0x1ff
        imm -= 0x200 if imm & 0x100 else 0
        if sz > 1 and imm % sz:
            yield a, w, imm, sz

def elf_layout(elf):
    """(text_start, text_end, data_ranges, symbols) from readelf/nm; only what the scan needs."""
    sec = subprocess.check_output(['readelf', '-SW', elf], text=True)
    m = re.search(r'\]\s+\.text\s+\S+\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)', sec)
    if not m:
        sys.exit('no .text section in ' + elf)
    start = int(m.group(1), 16); end = start + int(m.group(2), 16)
    marks, syms = [], []
    for line in subprocess.check_output(['nm', '-n', elf], text=True).splitlines():
        f = line.split()
        if len(f) != 3:
            continue
        addr = int(f[0], 16)
        if f[2] in ('$d', '$x'):
            marks.append((addr, f[2]))
        elif f[1] in 'tT':
            syms.append((addr, f[2]))
    return start, end, marks, syms

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image'); ap.add_argument('--elf')
    ap.add_argument('--end', type=lambda s: int(s, 0))
    a = ap.parse_args()
    data = open(a.image, 'rb').read()
    skip, name = (lambda addr: False), (lambda addr: '')
    if a.elf:
        start, end, marks, syms = elf_layout(a.elf)
        data = data[start:end]
        mk = sorted(set(marks))
        addrs = [m[0] for m in mk]
        def in_data(addr):
            i = bisect.bisect_right(addrs, addr) - 1
            return i >= 0 and mk[i][1] == '$d'
        skip = in_data
        sa = [s[0] for s in syms]
        def name(addr):
            i = bisect.bisect_right(sa, addr) - 1
            return f'{syms[i][1]}+0x{addr - syms[i][0]:x}' if i >= 0 else ''
        base = start
    else:
        base = 0
        if a.end is not None:
            data = data[:a.end]
    n = 0
    for addr, w, imm, sz in scan_words(data, base, skip):
        n += 1
        print(f'{addr:06x} {w:08x} {name(addr):28s} access {sz} B, imm {imm} (imm % {sz} = {imm % sz})')
    print('total', n)
    return 1 if n else 0

if __name__ == '__main__':
    sys.exit(main())
