#!/usr/bin/env python3
"""NAT-077: turn a linked arm64 Mach-O (lld -flavor darwin) into a static, ad-hoc signed executable the payload kernel accepts as PID 1.

  mkstatic.py LINKED OUT [ENTITLEMENTS.plist]

Why this exists. The pinned wrapper (NAT-020 build-003 tools/e1s/mkinit.py) takes one position-independent `__text` out of an *object*
file and refuses relocations and other sections. A probe written in C needs a linker (BRANCH26/PAGE21/PAGEOFF12 relocations, read-only
tables in `__const`/`__cstring`). The only linker on this host that targets Mach-O is LLD's darwin flavour, which ignores `-static`:
its output is a dynamic executable (LC_MAIN, LC_LOAD_DYLINKER, `__TEXT` starting at the second 16 KiB page, an export trie in
`__LINKEDIT`). So the linker resolves everything and this script re-lays the result out the way mkinit.py does:

  __PAGEZERO  0 .. 4G
  __TEXT      0x100000000, r-x, file 0..16K: header, load commands, the linked sections (same relative layout)
  __LINKEDIT  0x100004000, r--: the code signature
  LC_UNIXTHREAD pc = _start, sp = 0 (the kernel provides the default user stack)
  LC_CODE_SIGNATURE ad-hoc SHA-256 CodeDirectory (4K pages), produced by mkinit.code_signature()

The linked bytes are moved by a multiple of 4 KiB, so every ADRP/ADD pair keeps its page distance and nothing needs relocating. That is
only valid when there is nothing to relocate or bind, so this script *refuses* the input unless:
  - it is an MH_EXECUTE arm64 file with only __PAGEZERO, __TEXT and __LINKEDIT segments (any __DATA/__DATA_CONST segment is refused:
    a writable global in the C source would otherwise be silently dropped),
  - dyld_info has no rebase, bind, weak-bind or lazy-bind data, there are no chained fixups, no dylib is loaded and no symbol is undefined,
  - the __TEXT sections are in address order and `_start` lies in the first one.
mkinit.py is imported from the pinned NAT-020 build-003 source after its SHA-256 is checked; its signature code is reused as it is.
"""
import hashlib
import importlib.util
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MKINIT = ROOT / "artifacts/nat-020/build-003/source/tools/e1s/mkinit.py"
MKINIT_SHA256 = "2200a8b3225ffc42cbec33747d74fc3562012fb5a2882b8ab5795d453a90ce03"

MH_MAGIC_64, CPU_TYPE_ARM64, MH_EXECUTE = 0xfeedfacf, 0x0100000c, 2
LC_SEGMENT_64, LC_SYMTAB, LC_DYSYMTAB, LC_LOAD_DYLIB = 0x19, 0x2, 0xb, 0xc
LC_DYLD_INFO_ONLY, LC_DYLD_CHAINED_FIXUPS = 0x80000022, 0x80000034
LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB, LC_LAZY_LOAD_DYLIB = 0x80000018, 0x8000001f, 0x80000023, 0x20
ALLOWED_SEGMENTS = ("__PAGEZERO", "__TEXT", "__LINKEDIT")
N_EXT, N_TYPE, N_SECT = 0x01, 0x0e, 0x0e
DYLIB_COMMANDS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB, LC_LAZY_LOAD_DYLIB)


def load_mkinit():
    """Import the pinned mkinit.py (refusing any other file)."""
    have = hashlib.sha256(MKINIT.read_bytes()).hexdigest()
    if have != MKINIT_SHA256:
        raise SystemExit("mkinit.py is not the pinned one (%s)" % have)
    spec = importlib.util.spec_from_file_location("nat077_mkinit", MKINIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cstr(raw):
    return raw.split(b"\0")[0].decode()


def parse(data):
    """-> dict(sections=[...], blob=(file offset, size), entry=VA of _start, text_va=VA of the __TEXT segment). Raises SystemExit when the
    file cannot be moved without relocation."""
    if len(data) < 32:
        raise SystemExit("not a Mach-O file")
    magic, cpu, _, ftype, ncmds, sizeofcmds, _, _ = struct.unpack_from("<8I", data, 0)
    if magic != MH_MAGIC_64 or cpu != CPU_TYPE_ARM64 or ftype != MH_EXECUTE:
        raise SystemExit("not an arm64 MH_EXECUTE file")
    if 32 + sizeofcmds > len(data):
        raise SystemExit("load commands run past the end of the file")
    segments, sections, symtab, dysym, dyld_info = {}, [], None, None, None
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if size < 8 or off + size > 32 + sizeofcmds:
            raise SystemExit("malformed load command")
        if cmd == LC_SEGMENT_64:
            name = _cstr(data[off + 8:off + 24])
            vmaddr, vmsize, fileoff, filesize, _, _, nsects, _ = struct.unpack_from("<4Q2i2I", data, off + 24)
            if name not in ALLOWED_SEGMENTS:
                raise SystemExit("segment %s: only %s can be carried by the static wrapper (a writable global or a "
                                 "relocated pointer in the C source?)" % (name, ", ".join(ALLOWED_SEGMENTS)))
            segments[name] = (vmaddr, vmsize, fileoff, filesize)
            for i in range(nsects):
                s = off + 72 + 80 * i
                sect, seg = _cstr(data[s:s + 16]), _cstr(data[s + 16:s + 32])
                addr, ssize, soff, align, reloff, nreloc, flags, r1, r2, r3 = struct.unpack_from("<2Q8I", data, s + 32)
                if nreloc or reloff:
                    raise SystemExit("section %s,%s has relocations" % (seg, sect))
                if seg == "__TEXT":
                    sections.append(dict(name=sect, addr=addr, size=ssize, off=soff, align=align, flags=flags))
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from("<4I", data, off + 8)
        elif cmd == LC_DYSYMTAB:
            dysym = struct.unpack_from("<18I", data, off + 8)
        elif cmd == LC_DYLD_INFO_ONLY:
            dyld_info = struct.unpack_from("<10I", data, off + 8)
        elif cmd == LC_DYLD_CHAINED_FIXUPS:
            raise SystemExit("chained fixups present: the file needs dyld to run")
        elif cmd in DYLIB_COMMANDS:
            raise SystemExit("the file loads a dylib: it was linked against something")
        off += size
    if "__TEXT" not in segments or not sections:
        raise SystemExit("no __TEXT sections")
    if dyld_info is not None:
        rebase, bind, weak, lazy = dyld_info[1], dyld_info[3], dyld_info[5], dyld_info[7]
        if rebase or bind or weak or lazy:
            raise SystemExit("dyld_info has rebase/bind data (rebase %d, bind %d, weak %d, lazy %d bytes)" % (rebase, bind, weak, lazy))
    if dysym is None or symtab is None:
        raise SystemExit("no symbol table: cannot find _start or prove there are no undefined symbols")
    nundef = dysym[5]		# dysymtab_command.nundefsym
    if nundef:
        raise SystemExit("%d undefined symbols" % nundef)
    vmaddr, _, fileoff, _ = segments["__TEXT"]
    if fileoff != 0:
        raise SystemExit("__TEXT does not start at file offset 0")
    prev_end = None
    for s in sections:
        if s["addr"] - vmaddr != s["off"]:
            raise SystemExit("section %s is not at segment offset == file offset" % s["name"])
        if prev_end is not None and s["off"] < prev_end:
            raise SystemExit("__TEXT sections overlap or are out of order")
        prev_end = s["off"] + s["size"]
    if sections[0]["name"] != "__text":
        raise SystemExit("the first __TEXT section is %s, not __text" % sections[0]["name"])
    if prev_end > len(data):
        raise SystemExit("a section runs past the end of the file")
    symoff, nsyms, stroff, _ = symtab
    entry = None
    for i in range(nsyms):
        strx, ntype, nsect, _, value = struct.unpack_from("<IBBHQ", data, symoff + 16 * i)
        if ntype & N_EXT and (ntype & N_TYPE) == N_SECT and _cstr(data[stroff + strx:stroff + strx + 64]) == "_start":
            entry = value
    if entry is None:
        raise SystemExit("no global _start")
    t = sections[0]
    if not t["addr"] <= entry < t["addr"] + t["size"]:
        raise SystemExit("_start is not inside __text")
    first = sections[0]["off"]
    return dict(sections=sections, blob=(first, prev_end - first), entry=entry, text_va=vmaddr)


def wrap(data, entitlements=None):
    mk = load_mkinit()
    info = parse(data)
    first, size = info["blob"]
    blob = data[first:first + size]
    secs = info["sections"]
    sect_cmds = []
    # the new place for the blob: the same offset modulo 4 KiB (so ADRP distances survive), after the load commands
    sig_size = len(mk.code_signature(bytes(mk.SEG), mk.SEG, mk.SEG, entitlements))
    thread_len = 16 + 4 * mk.ARM_THREAD_STATE64_COUNT
    lc_len = 72 + (72 + 80 * len(secs)) + 72 + thread_len + 16
    new_off = first & 0xfff
    while new_off < 32 + lc_len:
        new_off += 0x1000
    if new_off + size > mk.SEG:
        raise SystemExit("the linked sections (%d bytes at offset %#x) do not fit in one %d byte __TEXT page" % (size, new_off, mk.SEG))
    shift = new_off - first
    assert shift % 0x1000 == 0
    for s in secs:
        sect_cmds.append(struct.pack("<16s16sQQIIIIIIII", s["name"].encode(), b"__TEXT", mk.BASE + new_off + (s["off"] - first), s["size"],
                                     new_off + (s["off"] - first), s["align"], 0, 0, s["flags"], 0, 0, 0))
    thread = struct.pack("<IIII", mk.LC_UNIXTHREAD, thread_len, mk.ARM_THREAD_STATE64, mk.ARM_THREAD_STATE64_COUNT)
    state = [0] * 33
    state[32] = info["entry"] - info["text_va"] + mk.BASE + shift
    thread += struct.pack("<33QII", *state, 0, 0)
    cmds = [
        mk.segment("__PAGEZERO", 0, mk.BASE, 0, 0, 0),
        mk.segment("__TEXT", mk.BASE, mk.SEG, 0, mk.SEG, mk.VM_PROT_R | mk.VM_PROT_X, sect_cmds),
        mk.segment("__LINKEDIT", mk.BASE + mk.SEG, mk.SEG, mk.SEG, sig_size, mk.VM_PROT_R),
        thread,
        struct.pack("<4I", mk.LC_CODE_SIGNATURE, 16, mk.SEG, sig_size),
    ]
    lc = b"".join(cmds)
    assert len(lc) == lc_len, (len(lc), lc_len)
    header = struct.pack("<8I", mk.MH_MAGIC_64, mk.CPU_TYPE_ARM64, 0, mk.MH_EXECUTE, len(cmds), len(lc), mk.MH_NOUNDEFS, 0)
    image = bytearray(mk.SEG)
    image[:32 + len(lc)] = header + lc
    image[new_off:new_off + size] = blob
    sig = mk.code_signature(bytes(image), mk.SEG, mk.SEG, entitlements)
    assert len(sig) == sig_size
    return bytes(image) + sig


def main(argv):
    if len(argv) not in (3, 4):
        raise SystemExit(__doc__)
    ents = Path(argv[3]).read_bytes() if len(argv) == 4 else None
    out = wrap(Path(argv[1]).read_bytes(), ents)
    Path(argv[2]).write_bytes(out)
    print("%s: %d bytes" % (argv[2], len(out)))


if __name__ == "__main__":
    main(sys.argv)
