#!/usr/bin/env python3
"""NAT-189: map unslid addresses of the iOS 16.5 (20F66) arm64 dyld shared cache to image + symbol, on the host.

Reads the owner's extracted cache (gitignored artifacts/apple-inputs/...) and the three LZBITMAP files that 7z leaves compressed
(.symbols, .28.dyldlinkedit, .42.dyldlinkedit), expanded by the donor's unzbm into a separate directory (artifacts/nat-189/dsc-symbols).
Symbols come from two places: the local (stripped) symbols in the .symbols file, and every image's own LC_SYMTAB (exports and other
external definitions) read through the cache's VM mappings. Nothing Apple is written into the repository: the table is cached as a
pickle under artifacts/.

    dscsym.py --cache DIR --extra DIR --table OUT.pickle build
    dscsym.py --table OUT.pickle lookup 0x1a2b3c4d5 ...
"""
import argparse
import bisect
import os
import pickle
import struct
import sys

MAIN = 'dyld_shared_cache_arm64'
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
N_STAB = 0xe0
N_TYPE = 0x0e
N_SECT = 0x0e


class Cache:
    def __init__(self, cache_dir, extra_dir):
        self.files = []  # (path, [(vmaddr, size, fileoff)])
        self.handles = {}
        main = self._path(cache_dir, extra_dir, MAIN)
        with open(main, 'rb') as f:
            h = f.read()
        self.header = h
        self.base = struct.unpack_from('<Q', h, 0xe0)[0]
        self._add_file(main, h)
        sc_off, sc_count = struct.unpack_from('<II', h, 0x188)
        for k in range(sc_count):
            e = h[sc_off + 56 * k:sc_off + 56 * (k + 1)]
            suffix = e[24:56].split(b'\0')[0].decode()
            p = self._path(cache_dir, extra_dir, MAIN + suffix)
            with open(p, 'rb') as f:
                self._add_file(p, f.read(0x4000))
        self.symbols_path = self._path(cache_dir, extra_dir, MAIN + '.symbols')
        img_off, img_count = struct.unpack_from('<II', h, 0x1c0)
        self.images = []
        for k in range(img_count):
            addr, _mt, _ino, path_off, _pad = struct.unpack_from('<QQQII', h, img_off + 32 * k)
            self.images.append((addr, h[path_off:h.index(b'\0', path_off)].decode()))

    @staticmethod
    def _path(cache_dir, extra_dir, name):
        for d in (extra_dir, cache_dir):
            if d:
                p = os.path.join(d, name)
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    return p
        raise FileNotFoundError(name + ' (empty or missing; expand LZBITMAP files with unzbm into --extra)')

    def _add_file(self, path, h):
        mo, mc = struct.unpack_from('<II', h, 0x10)
        maps = []
        for k in range(mc):
            a, s, fo, _mx, _ip = struct.unpack_from('<QQQII', h, mo + 32 * k)
            maps.append((a, s, fo))
        self.files.append((path, maps))

    def read(self, vm, size):
        for path, maps in self.files:
            for a, s, fo in maps:
                if a <= vm and vm + size <= a + s:
                    f = self.handles.get(path)
                    if f is None:
                        f = self.handles[path] = open(path, 'rb')
                    f.seek(fo + vm - a)
                    return f.read(size)
        return None


def image_info(cache, addr):
    """(__TEXT vmsize, [(name, value)] of the image's own LC_SYMTAB definitions)"""
    mh = cache.read(addr, 32)
    if mh is None or struct.unpack_from('<I', mh)[0] != 0xfeedfacf:
        return 0, []
    ncmds, sizeofcmds = struct.unpack_from('<II', mh, 16)
    cmds = cache.read(addr + 32, sizeofcmds)
    text_size = 0
    linkedit = None
    symtab = None
    off = 0
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', cmds, off)
        if cmd == LC_SEGMENT_64:
            name = cmds[off + 8:off + 24].split(b'\0')[0]
            vmaddr, vmsize, fileoff = struct.unpack_from('<QQQ', cmds, off + 24)
            if name == b'__TEXT':
                text_size = vmsize
            elif name == b'__LINKEDIT':
                linkedit = (vmaddr, fileoff)
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from('<IIII', cmds, off + 8)
        off += size
    syms = []
    if symtab and linkedit and symtab[1]:
        symoff, nsyms, stroff, strsize = symtab
        nl = cache.read(linkedit[0] + symoff - linkedit[1], 16 * nsyms)
        st = cache.read(linkedit[0] + stroff - linkedit[1], strsize)
        if nl and st:
            for k in range(nsyms):
                strx, ntype, _sect, _desc, value = struct.unpack_from('<IBBHQ', nl, 16 * k)
                if ntype & N_STAB or (ntype & N_TYPE) != N_SECT or not value:
                    continue
                syms.append((st[strx:st.index(b'\0', strx)].decode('utf-8', 'replace'), value))
    return text_size, syms


def local_symbols(cache):
    out = {}
    with open(cache.symbols_path, 'rb') as f:
        h = f.read(0x100)
        lso = struct.unpack_from('<Q', h, 0x48)[0]
        f.seek(lso)
        no, nc, so, ss, eo, ec = struct.unpack('<6I', f.read(24))
        f.seek(lso + no)
        nlist = f.read(16 * nc)
        f.seek(lso + so)
        strings = f.read(ss)
        f.seek(lso + eo)
        entries = f.read(16 * ec)
    for k in range(ec):
        dylib_off, start, count = struct.unpack_from('<QII', entries, 16 * k)
        syms = []
        for j in range(start, start + count):
            strx, ntype, _sect, _desc, value = struct.unpack_from('<IBBHQ', nlist, 16 * j)
            if ntype & N_STAB or (ntype & N_TYPE) != N_SECT or not value:
                continue
            syms.append((strings[strx:strings.index(b'\0', strx)].decode('utf-8', 'replace'), value))
        out[cache.base + dylib_off] = syms
    return out


def build(cache_dir, extra_dir, table_path):
    cache = Cache(cache_dir, extra_dir)
    locals_by_image = local_symbols(cache)
    images = []
    syms = {}
    for addr, path in cache.images:
        text_size, own = image_info(cache, addr)
        images.append((addr, addr + text_size, path))
        for name, value in own + locals_by_image.get(addr, []):
            if addr <= value < addr + text_size:
                syms.setdefault(value, name)
    images.sort()
    table = {
        'base': cache.base,
        'images': images,
        'addrs': sorted(syms),
    }
    table['names'] = [syms[a] for a in table['addrs']]
    with open(table_path, 'wb') as f:
        pickle.dump(table, f)
    return table


class Table:
    def __init__(self, table):
        self.t = table
        self.starts = [i[0] for i in table['images']]

    def lookup(self, addr):
        """(image short name or None, symbol or None, offset)"""
        k = bisect.bisect_right(self.starts, addr) - 1
        if k < 0 or addr >= self.t['images'][k][1]:
            return None, None, 0
        lo, hi, path = self.t['images'][k]
        j = bisect.bisect_right(self.t['addrs'], addr) - 1
        image = os.path.basename(path)
        if j < 0 or self.t['addrs'][j] < lo:
            return image, None, addr - lo
        return image, self.t['names'][j], addr - self.t['addrs'][j]


def load_table(path):
    with open(path, 'rb') as f:
        return Table(pickle.load(f))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', help='directory with the extracted dyld_shared_cache_arm64*')
    ap.add_argument('--extra', help='directory with the unzbm-expanded .symbols/.dyldlinkedit files')
    ap.add_argument('--table', required=True)
    ap.add_argument('cmd', choices=['build', 'lookup'])
    ap.add_argument('addrs', nargs='*')
    a = ap.parse_args(argv)
    if a.cmd == 'build':
        t = build(a.cache, a.extra, a.table)
        print('images %d symbols %d base %#x' % (len(t['images']), len(t['addrs']), t['base']))
        return 0
    t = load_table(a.table)
    for s in a.addrs:
        image, sym, off = t.lookup(int(s, 16))
        print('%s %s %s+%#x' % (s, image, sym, off))
    return 0


if __name__ == '__main__':
    sys.exit(main())
