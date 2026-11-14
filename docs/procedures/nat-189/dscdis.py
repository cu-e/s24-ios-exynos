#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Disassemble functions of the local 20F66 dyld shared cache on the host (NAT-192 follow-up): the bytes are read through the cache
mappings (dscsym.Cache), wrapped into an ELF object with the NDK clang (.inst words, never written into the repository) and shown by the
NDK llvm-objdump; branch targets are annotated with dscsym's table (image + symbol).

  dscdis.py --cache DIR --extra DIR --table PICKLE 0x1884471ec [0x... ...]
"""
import argparse, bisect, os, re, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dscsym  # noqa: E402
NDK = Path.home() / 'Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', required=True)
    ap.add_argument('--extra')
    ap.add_argument('--table', required=True)
    ap.add_argument('addrs', nargs='+')
    a = ap.parse_args(argv)
    cache = dscsym.Cache(a.cache, a.extra)
    t = dscsym.load_table(a.table)
    A = t.t['addrs']
    for s in a.addrs:
        start = int(s, 16)
        i = bisect.bisect_left(A, start)
        size = A[i + 1] - start if i + 1 < len(A) else 0x100
        data = cache.read(start, size)
        with tempfile.TemporaryDirectory() as d:
            words = [int.from_bytes(data[k:k + 4], 'little') for k in range(0, len(data) - 3, 4)]
            Path(d, 'f.s').write_text('.text\n.globl f\nf:\n' + ''.join('.inst %#x\n' % w for w in words))
            subprocess.run([str(NDK / 'clang'), '--target=aarch64-linux-android34', '-c', str(Path(d, 'f.s')), '-o', str(Path(d, 'f.o'))], check=True)
            out = subprocess.run([str(NDK / 'llvm-objdump'), '-d', '--no-show-raw-insn', '--adjust-vma=%#x' % start, str(Path(d, 'f.o'))],
                                 capture_output=True, text=True, check=True).stdout
        print('== %s %s size %#x' % (s, t.lookup(start)[:2], size))
        for line in out.splitlines():
            m = re.match(r'\s*([0-9a-f]+):\s+(.*)', line)
            if not m:
                continue
            ins = m[2]
            b = re.search(r'\b(bl?|b\.\w+|cbn?z|tbn?z)\b.*?0x([0-9a-f]+)', ins)
            note = ''
            if b and ins.split()[0] in ('bl', 'b'):
                tgt = int(b[2], 16)
                if not (start <= tgt < start + size):
                    img, sym, off = t.lookup(tgt)
                    note = '   ; %s %s+%#x' % (img, sym, off)
            print('  %s: %s%s' % (m[1], ins, note))
    return 0


if __name__ == '__main__':
    sys.exit(main())
