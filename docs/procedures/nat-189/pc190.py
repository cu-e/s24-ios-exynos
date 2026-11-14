#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-190 analyser: read the e1s-pc lines (NAT-189 sampler) from a kernel text and say where backboardd's time goes.

Without a symbol table it reports the raw buckets. With --table (dscsym.py's local pickle of the 20F66 dyld shared cache, never
committed) every bucket is mapped to image + symbol (local names are mostly '<redacted>' in Apple's .symbols file; those are reported
as the function's start address), and the samples are grouped by image and by group:

  copy    libsystem_platform (memmove, memset, ...)
  trap    libsystem_kernel (the saved pc of a thread that blocked in a trap: waiting, not computing)
  ca      QuartzCore
  raster  CoreGraphics, libRIP, ImageIO, vImage, libvDSP, Accelerate, CoreImage, libCGInterfaces, IOSurface
  runtime libobjc, CoreFoundation, libdispatch, libsystem_malloc, libsystem_pthread, Foundation, libc++
  other   any other cache image
  outside not in the cache (backboardd's own binary, dyld)

Verdict (pre-registered, NAT-190): P-none (no window line), P-thin (fewer than 2000 samples over the swipe windows 220-310 s), else P-ok
with the coarse-table coverage; the leading group over the swipe windows and in the last (Today-view) window is reported as a finding.

  pc190.py KERNEL_TEXT [--table artifacts/nat-189/dsc-table.pickle] [--json OUT]
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SWIPE_WINDOWS = (265, 310)
LAST_WINDOW = 375
THIN = 2000

GROUPS = (
    ('copy', ('libsystem_platform.dylib',)),
    ('trap', ('libsystem_kernel.dylib',)),
    ('ca', ('QuartzCore',)),
    ('raster', ('CoreGraphics', 'libRIP.A.dylib', 'ImageIO', 'vImage', 'libvDSP.dylib', 'Accelerate', 'CoreImage',
                'libCGInterfaces.dylib', 'IOSurface', 'libvMisc.dylib', 'libBLAS.dylib')),
    ('runtime', ('libobjc.A.dylib', 'CoreFoundation', 'libdispatch.dylib', 'libsystem_malloc.dylib', 'libsystem_pthread.dylib',
                 'Foundation', 'libc++.1.dylib', 'libc++abi.dylib', 'libsystem_c.dylib')),
)

HEAD = re.compile(r'e1s-pc: (\d+) window (\d+)-(\d+) s ticks (\d+) busy (\d+) samples (\d+) tlost (\d+) self (\d+) us pid (-?\d+) '
                  r'start (0x[0-9a-f]+|0)')
ENTRIES = re.compile(r'e1s-pc: (\d+) ([fgl])((?: [ca][0-9a-f]+:\d+)+)\s*$')
SHOWN = re.compile(r'e1s-pc: (\d+) ([fgl]) shown (\d+) lost (\d+)')


def group_of(image):
    if image is None:
        return 'outside'
    for g, names in GROUPS:
        if image in names:
            return g
    return 'other'


def parse(text):
    windows = {}
    for line in text.splitlines():
        m = HEAD.search(line)
        if m:
            end = int(m[1])
            windows[end] = dict(end=end, start_s=int(m[2]), ticks=int(m[4]), busy=int(m[5]), samples=int(m[6]), tlost=int(m[7]),
                                self_us=int(m[8]), pid=int(m[9]), cache_start=int(m[10], 16), f=[], g=[], l=[], shown={}, lost={})
            continue
        m = ENTRIES.search(line)
        if m and int(m[1]) in windows:
            for e in m[3].split():
                kind, rest = e[0], e[1:]
                addr, n = rest.split(':')
                windows[int(m[1])][m[2]].append((kind, int(addr, 16), int(n)))
            continue
        m = SHOWN.search(line)
        if m and int(m[1]) in windows:
            windows[int(m[1])]['shown'][m[2]] = int(m[3])
            windows[int(m[1])]['lost'][m[2]] = int(m[4])
    return windows


def _resolve(table, base, kind, addr):
    """(image, function key) for one bucket"""
    if table is None or kind == 'a':
        return (None, None)
    image, sym, off = table.lookup(base + addr)
    if image is None:
        return (None, None)
    if sym is None:
        return (image, '%s+%#x' % (image, off))
    if sym == '<redacted>':
        return (image, '%s:sub_%x' % (image, base + addr - off))
    return (image, sym)


def summarise(w, table, base):
    out = {}
    for kind_table in ('f', 'g', 'l'):
        entries = w[kind_table]
        total = w['samples']
        by_image, by_group, by_func = {}, {}, {}
        for kind, addr, n in entries:
            image, func = _resolve(table, base, kind, addr)
            by_image[image or 'outside'] = by_image.get(image or 'outside', 0) + n
            by_group[group_of(image)] = by_group.get(group_of(image), 0) + n
            if kind_table != 'g':
                key = func or ('%s%x' % (kind, addr))
                by_func[key] = by_func.get(key, 0) + n
        top = lambda d, k=12: [dict(name=a, samples=b, share=round(b / total, 4) if total else None)
                               for a, b in sorted(d.items(), key=lambda x: -x[1])[:k]]
        out[kind_table] = dict(coverage=round(sum(n for _, _, n in entries) / total, 4) if total else None,
                               groups=top(by_group, 10), images=top(by_image), functions=top(by_func, 20) if by_func else [])
    return out


def analyse(text, table=None):
    windows = parse(text)
    base = table.t['base'] if table is not None else 0
    r = dict(windows=[], verdict='P-none', symbolised=table is not None)
    if not windows:
        return r
    for end in sorted(windows):
        w = windows[end]
        s = dict({k: w[k] for k in ('end', 'start_s', 'ticks', 'busy', 'samples', 'tlost', 'self_us', 'pid', 'cache_start')},
                 slide=(w['cache_start'] - base) if (table is not None and w['cache_start']) else None,
                 sampler_share=round(w['self_us'] / ((w['end'] - w['start_s']) * 1e6), 4))
        s.update(summarise(w, table, base))
        r['windows'].append(s)
    swipe = [s for s in r['windows'] if s['end'] in SWIPE_WINDOWS]
    samples = sum(s['samples'] for s in swipe)
    r['swipe_samples'] = samples
    if samples < THIN:
        r['verdict'] = 'P-thin'
        return r
    r['verdict'] = 'P-ok'
    r['swipe_coarse_coverage'] = round(sum(s['g']['coverage'] * s['samples'] for s in swipe) / samples, 4)
    groups = {}
    for s in swipe:
        for g in s['g']['groups']:
            groups[g['name']] = groups.get(g['name'], 0) + g['samples']
    r['swipe_groups'] = {k: round(v / samples, 4) for k, v in sorted(groups.items(), key=lambda x: -x[1])}
    r['swipe_leader'] = next(iter(r['swipe_groups']), None)
    last = [s for s in r['windows'] if s['end'] == LAST_WINDOW]
    if last and last[0]['samples']:
        r['last_groups'] = {g['name']: g['share'] for g in last[0]['g']['groups']}
        r['last_leader'] = last[0]['g']['groups'][0]['name'] if last[0]['g']['groups'] else None
    return r


def _load_dscsym():
    spec = importlib.util.spec_from_file_location('nat189_dscsym', HERE / 'dscsym.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('text')
    ap.add_argument('--table')
    ap.add_argument('--json')
    a = ap.parse_args(argv)
    table = _load_dscsym().load_table(a.table) if a.table else None
    r = analyse(Path(a.text).read_text(errors='replace'), table)
    s = json.dumps(r, indent=2) + '\n'
    if a.json:
        Path(a.json).write_text(s)
    print(json.dumps({k: r.get(k) for k in ('verdict', 'swipe_samples', 'swipe_coarse_coverage', 'swipe_leader', 'swipe_groups',
                                            'last_leader', 'last_groups')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
