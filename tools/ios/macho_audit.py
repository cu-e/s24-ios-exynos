#!/usr/bin/env python3
"""IOS-012: static Mach-O / dyld shared cache audit of the unpacked iOS 16.5 userland (host, read-only).

Why own code: no ready tool was usable for this specific question.  The cctools `otool` of the project reads the programs but not the
split dyld shared cache; LIEF from PyPI has no dyld-shared-cache module in its public wheel; a downloaded `ipsw` binary was refused by
the auto-mode classifier (2026-11-12T00:36Z) and was not run.  So this file reads only what the questions need, from the public
layouts: <mach-o/loader.h>, <mach-o/fat.h>, dyld's dyld_cache_format.h (header, mapping info, image info), the export trie and the arm64
instruction encodings of `movz`/`movn`/`svc`.  It is read-only and prints facts, never file contents.

  audit PROGRAM... [--cache FILE]
                          header, platform/minos, load commands, fixups kind, linked libraries, which are in the cache
  closure PROGRAM... --cache FILE
                          transitive library closure of the programs through the images of the cache; names that are missing
                          (and whether the referring load command was weak)
  syscalls --cache FILE [--image PATH] --master syscalls.master --traps syscall_sw.c --config-dir config/
                          the system-call numbers issued by `mov x16,#N; svc #0x80` pairs in one cache image (default
                          libsystem_kernel), compared with the project kernel's tables: syscalls.master with its #if guards
                          resolved against the option tags of one configuration (default DEVELOPMENT of MASTER.arm64.e1s), and
                          the Mach trap table of osfmk/kern/syscall_sw.c
  program-syscalls PROGRAM... --master ... --traps ... --config-dir ...
                          the same for the `svc` instructions inside programs themselves (only dyld has any)
  cstrings PROGRAM --match REGEX...
                          the __TEXT,__cstring strings of a program that match (names of sysctls, environment variables, paths)

Everything is a static comparison, not a runtime test: a number or name that exists in the kernel tables says nothing about the
behaviour behind it, and an option the configuration files do not define stays "unresolved" and is reported as such.
"""
import argparse
import json
import mmap
import os
import re
import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xCAFEBABE
CPU_TYPE_ARM64 = 0x0100000C
LC = {
    "SEGMENT_64": 0x19, "SYMTAB": 0x2, "UNIXTHREAD": 0x5, "LOAD_DYLIB": 0xC, "ID_DYLIB": 0xD, "LOAD_DYLINKER": 0xE,
    "UUID": 0x1B, "CODE_SIGNATURE": 0x1D, "LAZY_LOAD_DYLIB": 0x20, "DYLD_INFO": 0x22, "VERSION_MIN_IPHONEOS": 0x25,
    "FUNCTION_STARTS": 0x26, "BUILD_VERSION": 0x32,
    "LOAD_WEAK_DYLIB": 0x80000018, "RPATH": 0x8000001C, "REEXPORT_DYLIB": 0x8000001F, "DYLD_INFO_ONLY": 0x80000022,
    "LOAD_UPWARD_DYLIB": 0x80000023, "MAIN": 0x80000028, "DYLD_EXPORTS_TRIE": 0x80000033, "DYLD_CHAINED_FIXUPS": 0x80000034,
}
LC_NAME = {v: k for k, v in LC.items()}
DYLIB_CMDS = {LC["LOAD_DYLIB"], LC["LOAD_WEAK_DYLIB"], LC["REEXPORT_DYLIB"], LC["LAZY_LOAD_DYLIB"], LC["LOAD_UPWARD_DYLIB"]}
PLATFORM = {1: "macOS", 2: "iOS", 3: "tvOS", 4: "watchOS", 5: "bridgeOS", 6: "macCatalyst", 7: "iOSSimulator",
            8: "tvOSSimulator", 9: "watchOSSimulator", 10: "driverKit"}
FILETYPE = {1: "OBJECT", 2: "EXECUTE", 6: "DYLIB", 7: "DYLINKER", 8: "BUNDLE"}
SVC_80 = 0xD4001001


class AuditError(Exception):
    pass


def version(v):
    return "%d.%d.%d" % (v >> 16, (v >> 8) & 0xFF, v & 0xFF)


def cstr(data, off, limit=4096):
    end = data.find(b"\0", off, off + limit)
    if end < 0:
        raise AuditError("unterminated string at %#x" % off)
    return bytes(data[off:end]).decode("utf-8", "replace")


def uleb(data, off):
    result = shift = 0
    while True:
        if off >= len(data) or shift > 63:
            raise AuditError("bad ULEB128")
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, off
        shift += 7


# --- Mach-O ---------------------------------------------------------------------------------------------------

def fat_slice(data):
    """Return (offset, size) of the arm64 slice of a universal file, or (0, len) for a thin one."""
    if len(data) >= 8 and struct.unpack_from(">I", data, 0)[0] == FAT_MAGIC:
        n = struct.unpack_from(">I", data, 4)[0]
        if n > 16 or 8 + 20 * n > len(data):
            raise AuditError("bad fat header")
        for i in range(n):
            cpu, sub, off, size, _al = struct.unpack_from(">IIIII", data, 8 + 20 * i)
            if cpu == CPU_TYPE_ARM64:
                return off, size
        raise AuditError("no arm64 slice")
    return 0, len(data)


def parse_macho(data, base=0, size=None):
    """Parse one thin 64-bit Mach-O at data[base:].  Addresses stay as written; nothing is relocated."""
    if len(data) < base + 32 or struct.unpack_from("<I", data, base)[0] != MH_MAGIC_64:
        raise AuditError("not a thin 64-bit little-endian Mach-O")
    _m, cpu, sub, ftype, ncmds, sizeofcmds, flags, _res = struct.unpack_from("<IiiIIIII", data, base)
    if ncmds > 4096 or 32 + sizeofcmds > (size if size is not None else len(data) - base):
        raise AuditError("implausible load command area")
    m = {"cputype": cpu & 0xFFFFFFFF, "cpusubtype": sub & 0xFFFFFFFF, "filetype": FILETYPE.get(ftype, str(ftype)),
         "flags": flags, "ncmds": ncmds, "commands": [], "libraries": [], "rpaths": [], "segments": [], "sections": [],
         "dyld_fixups": "none", "dyld_linker": None, "entry": None, "install_name": None, "build_version": None,
         "exports_trie": None, "uuid": None}
    off = base + 32
    end = off + sizeofcmds
    for _ in range(ncmds):
        if off + 8 > end:
            raise AuditError("load command runs past the command area")
        cmd, csize = struct.unpack_from("<II", data, off)
        if csize < 8 or csize % 4 or off + csize > end:
            raise AuditError("bad load command size")
        name = LC_NAME.get(cmd, "%#x" % cmd)
        m["commands"].append(name)
        if cmd in DYLIB_CMDS or cmd == LC["ID_DYLIB"]:
            noff, _ts, cur, compat = struct.unpack_from("<IIII", data, off + 8)
            lib = cstr(data, off + noff)
            if cmd == LC["ID_DYLIB"]:
                m["install_name"] = lib
            else:
                m["libraries"].append({"name": lib, "kind": name, "current": version(cur), "compat": version(compat)})
        elif cmd == LC["LOAD_DYLINKER"]:
            noff = struct.unpack_from("<I", data, off + 8)[0]
            m["dyld_linker"] = cstr(data, off + noff)
        elif cmd == LC["RPATH"]:
            noff = struct.unpack_from("<I", data, off + 8)[0]
            m["rpaths"].append(cstr(data, off + noff))
        elif cmd == LC["BUILD_VERSION"]:
            plat, minos, sdk, _nt = struct.unpack_from("<IIII", data, off + 8)
            m["build_version"] = {"platform": PLATFORM.get(plat, str(plat)), "minos": version(minos), "sdk": version(sdk)}
        elif cmd == LC["VERSION_MIN_IPHONEOS"]:
            minos, sdk = struct.unpack_from("<II", data, off + 8)
            m["build_version"] = {"platform": "iOS (LC_VERSION_MIN)", "minos": version(minos), "sdk": version(sdk)}
        elif cmd == LC["MAIN"]:
            m["entry"] = {"kind": "LC_MAIN", "entryoff": struct.unpack_from("<Q", data, off + 8)[0]}
        elif cmd == LC["UNIXTHREAD"]:
            m["entry"] = {"kind": "LC_UNIXTHREAD"}
        elif cmd in (LC["DYLD_INFO"], LC["DYLD_INFO_ONLY"]) and m["dyld_fixups"] == "none":
            m["dyld_fixups"] = "dyld_info (rebase/bind opcodes)"
        elif cmd == LC["DYLD_CHAINED_FIXUPS"]:
            m["dyld_fixups"] = "chained fixups"
        elif cmd == LC["DYLD_EXPORTS_TRIE"]:
            m["exports_trie"] = struct.unpack_from("<II", data, off + 8)
        elif cmd == LC["UUID"]:
            m["uuid"] = bytes(data[off + 8:off + 24]).hex()
        elif cmd == LC["SEGMENT_64"]:
            segname = bytes(data[off + 8:off + 24]).split(b"\0")[0].decode()
            vmaddr, vmsize, fileoff, filesize, _mp, _ip, nsects, _fl = struct.unpack_from("<QQQQiiII", data, off + 24)
            m["segments"].append({"name": segname, "vmaddr": vmaddr, "vmsize": vmsize, "fileoff": fileoff, "filesize": filesize})
            so = off + 72
            for _s in range(nsects):
                if so + 80 > off + csize:
                    raise AuditError("section table runs past its segment command")
                sect = bytes(data[so:so + 16]).split(b"\0")[0].decode()
                saddr, ssize, soffset = struct.unpack_from("<QQI", data, so + 32)
                m["sections"].append({"segment": segname, "name": sect, "addr": saddr, "size": ssize, "offset": soffset})
                so += 80
        off += csize
    return m


def summarize(m):
    return {
        "cputype": "arm64" if m["cputype"] == CPU_TYPE_ARM64 else hex(m["cputype"]),
        "cpusubtype": {0: "arm64 (plain, no pointer authentication)", 2: "arm64e"}.get(m["cpusubtype"] & 0xFFFFFF, hex(m["cpusubtype"])),
        "filetype": m["filetype"], "ncmds": m["ncmds"], "build_version": m["build_version"], "dyld_fixups": m["dyld_fixups"],
        "entry": m["entry"], "dyld_linker": m["dyld_linker"], "rpaths": m["rpaths"],
        "load_command_counts": {k: m["commands"].count(k) for k in sorted(set(m["commands"]))},
        "libraries": m["libraries"]}


# --- dyld shared cache -----------------------------------------------------------------------------------------

class Dsc:
    """A split dyld shared cache: the main file and its numbered subcaches (dyld_cache_format.h layouts)."""

    def __init__(self, main_path):
        self.files = []
        try:
            self._load(Path(main_path))
        except BaseException:
            self.close()  # do not leak the files opened so far when the set is rejected
            raise

    def _load(self, main_path):
        self.dir = main_path.parent
        self.maps = []  # (address, size, file_index, file_offset, init_prot)
        names = sorted(p for p in self.dir.iterdir()
                       if re.fullmatch(re.escape(main_path.name) + r"(\.\d+(\.dylddata|\.dyldlinkedit)?)?", p.name))
        names.sort(key=lambda p: (p.name != main_path.name, p.name))
        if not names or names[0].name != main_path.name:
            raise AuditError("main cache file missing")
        for p in names:
            fh = open(p, "rb")
            try:
                mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)  # an empty file raises ValueError
            except BaseException:
                fh.close()
                raise
            idx = len(self.files)
            self.files.append((p.name, fh, mm))
            if mm[:6] != b"dyld_v":
                raise AuditError("%s is not a dyld cache file" % p.name)
            moff, mcount = struct.unpack_from("<II", mm, 0x10)
            if mcount > 64 or moff + 32 * mcount > len(mm):
                raise AuditError("%s: implausible mapping table" % p.name)
            for i in range(mcount):
                addr, size, foff, _maxp, initp = struct.unpack_from("<QQQII", mm, moff + 32 * i)
                if foff + size > len(mm):
                    raise AuditError("%s: mapping %d runs past its file" % (p.name, i))
                self.maps.append((addr, size, idx, foff, initp))
        main = self.files[0][2]
        self.magic = bytes(main[:16]).rstrip(b"\0 ").decode()
        self.platform, = struct.unpack_from("<I", main, 0xD8)
        self.os_version, = struct.unpack_from("<I", main, 0x16C)
        self.shared_region_start, self.shared_region_size = struct.unpack_from("<QQ", main, 0xE0)
        ioff, icount = struct.unpack_from("<II", main, 0x1C0)
        if ioff == 0:
            ioff, icount = struct.unpack_from("<II", main, 0x18)
        if icount > 20000 or ioff + 32 * icount > len(main):
            raise AuditError("implausible image table")
        self.images = []
        for i in range(icount):
            addr, _mt, _ino, poff, _pad = struct.unpack_from("<QQQII", main, ioff + 32 * i)
            self.images.append((addr, cstr(main, poff)))
        self.by_path = {p: a for a, p in self.images}

    def read(self, addr, n):
        for a, size, idx, foff, _prot in self.maps:
            if a <= addr and addr + n <= a + size:
                mm = self.files[idx][2]
                return mm[foff + addr - a: foff + addr - a + n]
        raise AuditError("address %#x..%#x is in no mapping" % (addr, addr + n))

    def macho(self, path):
        addr = self.by_path[path]
        head = self.read(addr, 32)
        sizeofcmds = struct.unpack_from("<I", head, 20)[0]
        return parse_macho(self.read(addr, 32 + sizeofcmds)), addr

    def close(self):
        for _n, fh, mm in self.files:
            mm.close()
            fh.close()


# --- exports, syscall stubs ---------------------------------------------------------------------------------------

def parse_exports(trie):
    """Export trie -> {symbol: (flags, address-offset or None)}; reexports have no address here."""
    out = {}
    stack = [(0, "")]
    seen = 0
    while stack:
        off, prefix = stack.pop()
        seen += 1
        if seen > 2_000_000:
            raise AuditError("export trie too large")
        size, p = uleb(trie, off)
        if size:
            flags, q = uleb(trie, p)
            if flags & 0x8:
                out[prefix] = (flags, None)
            else:
                addr, _ = uleb(trie, q)
                out[prefix] = (flags, addr)
        p += size
        count = trie[p]
        p += 1
        for _ in range(count):
            end = trie.index(b"\0", p)
            edge = bytes(trie[p:end]).decode("utf-8", "replace")
            child, p = uleb(trie, end + 1)
            if child >= len(trie):
                raise AuditError("export trie edge points outside the trie")
            stack.append((child, prefix + edge))
    return out


def scan_svc(text, base):
    """Find `movz/movn x16,#imm ; svc #0x80`.  Returns (pairs [(address, number)], svc_total)."""
    pairs, total = [], 0
    words = struct.unpack("<%dI" % (len(text) // 4), bytes(text[:len(text) // 4 * 4]))
    for i, w in enumerate(words):
        if w == SVC_80:
            total += 1
            if i:
                p = words[i - 1]
                if (p & 0x1F) == 16 and ((p >> 21) & 3) == 0:
                    imm = (p >> 5) & 0xFFFF
                    if p & 0xFF800000 == 0xD2800000:
                        pairs.append((base + 4 * (i - 1), imm))
                    elif p & 0xFF800000 == 0x92800000:
                        pairs.append((base + 4 * (i - 1), ~imm))
    return pairs, total


COMMPAGE_RW = 0xFFFFFC000            # _COMM_PAGE64_BASE_ADDRESS of osfmk/arm/cpu_capabilities.h (the page the kernel writes)
COMMPAGE_RO = 0xFFFFF4000            # _COMM_PAGE64_RO_ADDRESS (the read-only page)
COMMPAGE_SPAN = 0x4000
_ORR_HIGH = 0xB2704FE0               # orr xN,xzr,#0xfffff0000  (xN in the low 5 bits): the high part of every commpage address
_MOVK32 = 0xF2C001E0                 # movk xN,#0xf,lsl #32
_MOVK16 = 0xF2BFFFE0                 # movk xN,#0xffff,lsl #16


def commpage_region(addr):
    """('rw'|'ro', offset in that page) for an address inside the 64-bit commpage, else None."""
    for name, start in (("rw", COMMPAGE_RW), ("ro", COMMPAGE_RO)):
        if start <= addr < start + COMMPAGE_SPAN:
            return name, addr - start
    return None


def _low_lane(x, rd):
    """imm16 of `movk/movz xRd,#imm16` (no shift), else None."""
    if (x & 0xFF800000) in (0xF2800000, 0xD2800000) and (x & 0x1F) == rd and ((x >> 21) & 3) == 0:
        return (x >> 5) & 0xFFFF
    return None


def scan_commpage(text, base):
    """References to the 64-bit commpage that are visible as constants in the instruction stream.  Two shapes, both with the
    same destination register xN:
      A. movk xN,#0xf,lsl #32 + movk xN,#0xffff,lsl #16 + a low-lane movk/movz (clang's four-movk sequence, any order, inside a
         window of eleven instructions centred on the lane-2 movk);
      B. orr xN,xzr,#0xfffff0000 followed within four instructions by a low-lane movk/movz.
    Returns [(address of the low-lane instruction, 'rw'|'ro', offset in that page)] for addresses inside either page.
    A heuristic: addresses formed any other way (adrp from a table, a literal pool, add after a bare orr of the page base) are
    not found, so a miss proves nothing about an image."""
    words = struct.unpack("<%dI" % (len(text) // 4), bytes(text[:len(text) // 4 * 4]))
    hits = []

    def add(j, imm):
        r = commpage_region(0xFFFFF0000 | imm)
        if r:
            hits.append((base + 4 * j, r[0], r[1]))

    for i, w in enumerate(words):
        if (w & ~0x1F) == _MOVK32:                                           # shape A
            rd = w & 0x1F
            window = range(max(0, i - 5), min(len(words), i + 6))
            if any(words[j] == _MOVK16 | rd for j in window):
                for j in window:
                    imm = _low_lane(words[j], rd)
                    if imm is not None:
                        add(j, imm)
        elif (w & ~0x1F) == _ORR_HIGH and (w & 0x1F) != 31:                  # shape B
            for j in range(i + 1, min(len(words), i + 5)):
                imm = _low_lane(words[j], w & 0x1F)
                if imm is not None:
                    add(j, imm)
                    break
    return sorted(set(hits))


def scan_sysregs(text, base):
    """MRS/MSR (register) instructions: [(address, 'mrs'|'msr', 'S<op0>_<op1>_C<CRn>_C<CRm>_<op2>')].  Encoding: bits 31..20 are
    0xd53 for mrs and 0xd51 for msr, bit 19 is op0-2, then op1 (3 bits), CRn, CRm (4 bits each), op2 (3 bits), Rt."""
    words = struct.unpack("<%dI" % (len(text) // 4), bytes(text[:len(text) // 4 * 4]))
    out = []
    for i, w in enumerate(words):
        if (w >> 20) in (0xD51, 0xD53):
            name = "S%d_%d_C%d_C%d_%d" % (2 + ((w >> 19) & 1), (w >> 16) & 7, (w >> 12) & 15, (w >> 8) & 15, (w >> 5) & 7)
            out.append((base + 4 * i, "mrs" if (w >> 20) == 0xD53 else "msr", name))
    return out


def implementation_defined(name):
    """Architecturally reserved for implementation-defined registers: op0 == 3 and CRn in {11, 15}."""
    op0, _op1, crn, _crm, _op2 = (int(x.lstrip("SC")) for x in name.split("_"))
    return op0 == 3 and crn in (11, 15)


def parse_commpage_names(header_text):
    """{('rw'|'ro', offset): [macro names]} from `#define _COMM_PAGE_NAME (_COMM_PAGE_START_ADDRESS+0x010)` and the
    `_COMM_PAGE_RO_ADDRESS` flavour of osfmk/arm/cpu_capabilities.h."""
    names = {}
    for m in re.finditer(r"^#define\s+(_COMM_PAGE_[A-Z0-9_]+)\s+\(_COMM_PAGE_(START|RO)_ADDRESS\s*\+\s*(0x[0-9A-Fa-f]+)\)", header_text, re.M):
        names.setdefault(("ro" if m.group(2) == "RO" else "rw", int(m.group(3), 16)), []).append(m.group(1))
    return names


def nearest_field(names, region, off):
    """{'fields': names defined at exactly this offset} or, when the project header defines none there,
    {'fields': [], 'unnamed_in_project_header': True, 'after_field': nearest lower-offset field of the page, 'distance': bytes}.
    The 'after' hint only says where a byte read could sit inside a wider field; it does not name the field."""
    if (region, off) in names:
        return {"fields": names[(region, off)]}
    lower = [o for (r, o) in names if r == region and o < off]
    out = {"fields": [], "unnamed_in_project_header": True}
    if lower:
        o = max(lower)
        out["after_field"] = names[(region, o)][0]
        out["distance"] = off - o
    return out


def text_of(macho, reader):
    for s in macho["sections"]:
        if s["segment"] == "__TEXT" and s["name"] == "__text":
            return s["addr"], reader(s["addr"], s["size"])
    raise AuditError("no __TEXT,__text")


# --- the project kernel's tables ---------------------------------------------------------------------------------------

_GUARD = re.compile(r"^#\s*(if|ifdef|ifndef)\s+(!?)\s*(\w+)\s*(?:/\*.*\*/|//.*)?\s*$")
_SYSCALL = re.compile(r"^(\d+)\s+\S+\s+\S+\s+\{\s*[^({}]*?\b(\w+)\s*\(")


def parse_master_alternatives(text):
    """{number: [(guards, name)]} from bsd/kern/syscalls.master (lines: NUMBER AUE_x FLAGS { ret name(args) ... }).
    guards = ((option, wanted_value), ...) of the enclosing #if/#ifdef/#ifndef/#else blocks, outermost first.  A #if whose
    condition is not a single (optionally negated) option name is kept as an opaque guard that no configuration resolves."""
    alts = {}
    stack = []
    for line in text.splitlines():
        s = line.strip()
        g = _GUARD.match(s)
        if g:
            kind, neg, name = g.groups()
            stack.append((name, (kind != "ifndef") != (neg == "!")))
            continue
        if s.startswith("#if"):
            stack.append((s, True))
            continue
        if s.startswith("#elif"):
            raise AuditError("#elif in syscalls.master is not handled")
        if s.startswith("#else"):
            if not stack:
                raise AuditError("#else without #if in syscalls.master")
            name, want = stack.pop()
            stack.append((name, not want))
            continue
        if s.startswith("#endif"):
            if not stack:
                raise AuditError("#endif without #if in syscalls.master")
            stack.pop()
            continue
        m = _SYSCALL.match(line)
        if m:
            alts.setdefault(int(m.group(1)), []).append((tuple(stack), m.group(2)))
    if stack:
        raise AuditError("unbalanced #if in syscalls.master")
    return alts


def parse_config_bundles(text):
    """`#  NAME = [ a b NAME2 ]` lines of a config/MASTER.* file -> {NAME: [tokens]}."""
    return {m.group(1): m.group(2).split()
            for m in re.finditer(r"^#\s+([A-Z][A-Z_0-9]*)\s*=\s*\[([^\]]*)\]", text, re.M)}


def enabled_tags(bundles, root):
    """The lower-case option tags reached from the bundle `root` (upper-case tokens are bundles)."""
    tags, todo, seen = set(), [root], set()
    while todo:
        t = todo.pop()
        if t in seen:
            continue
        seen.add(t)
        if t in bundles:
            todo.extend(bundles[t])
        elif not t.isupper():
            tags.add(t)
    return tags


def option_states(config_texts, tags):
    """{OPTION: bool} from `options NAME ... # <tag,tag>` lines: on when any tag in the last <...> list is enabled.
    Options without a <tag> list are always on.  Options that never appear are absent (unresolved)."""
    state = {}
    for text in config_texts:
        for line in text.splitlines():
            m = re.match(r"^\s*options\s+(\w+)", line)
            if not m:
                continue
            lists = re.findall(r"<([^>]*)>", line)
            state[m.group(1)] = True if not lists else any(t.strip() in tags for t in lists[-1].split(","))
    return state


def effective_syscalls(alts, states):
    """{number: (name, status)}.  status: "unconditional", "resolved" (the config decided every guard) or
    "unresolved:<options>" (a guard names an option the configuration files do not define)."""
    out = {}
    for num, lst in alts.items():
        unresolved, picked, fallback = set(), None, None
        for guards, name in lst:
            verdict = True
            for opt, want in guards:
                if opt not in states:
                    unresolved.add(opt)
                    verdict = None
                    break
                if states[opt] != want:
                    verdict = False
                    break
            if verdict:
                picked = (name, "resolved" if guards else "unconditional")
                break
            if verdict is None and fallback is None:
                fallback = name
        if picked:
            out[num] = picked
        elif fallback is not None:
            out[num] = (fallback, "unresolved:" + ",".join(sorted(unresolved)))
        else:
            out[num] = ("(no alternative enabled)", "resolved")
    return out


def parse_mach_traps(text):
    """{trap number: name} from osfmk/kern/syscall_sw.c (`/* 26 */ MACH_TRAP(mach_reply_port, 0, 0, NULL),`)."""
    table = {}
    for m in re.finditer(r"/\*\s*(\d+)\s*\*/\s*MACH_TRAP\(\s*(\w+)\s*,", text):
        if m.group(2) != "kern_invalid":
            table[int(m.group(1))] = m.group(2)
    return table


def norm(name):
    """Comparable form of a libsystem_kernel export or a kernel table name: drop `$VARIANT` suffixes, leading
    underscores, the kernel's `sys_`/`syscall_` prefixes and the Mach traps' `_trap` suffix."""
    n = name.split("$")[0].lstrip("_")
    for pre in ("sys_", "syscall_"):
        if n.startswith(pre):
            n = n[len(pre):]
    return n[:-5] if n.endswith("_trap") else n


def compare_numbers(pairs, names_at, bsd, mach):
    """pairs: [(address, number)] (BSD numbers >= 0, Mach traps as -N); names_at: {address: [export names]};
    bsd: {number: (name, status)} from effective_syscalls(); mach: {trap: name}."""
    exact, differs, no_name, absent, nosys, unresolved = 0, [], [], [], [], []
    all_names = {norm(n) for ns in names_at.values() for n in ns}
    for addr, num in sorted(set(pairs)):
        names = names_at.get(addr, [])
        if num >= 0:
            kname, status = bsd.get(num, (None, "absent"))
        else:
            kname, status = mach.get(-num), "mach trap table"
        row = {"number": num, "stub_names": names, "kernel": kname, "kernel_status": status}
        if kname is None:
            absent.append(row)
        elif status.startswith("unresolved"):
            unresolved.append(row)
        elif num > 0 and norm(kname) in ("nosys", "enosys"):
            nosys.append(row)
        elif num == 0:
            exact += 1  # the indirect syscall: the kernel table names slot 0 `nosys` by design
        elif not names:
            no_name.append(row)
        elif any(norm(n) == norm(kname) for n in names):
            exact += 1
        else:
            row["kernel_name_exported_by_the_library"] = norm(kname) in all_names
            differs.append(row)
    return {"name_match": exact, "no_export_name_at_stub": no_name, "name_differs": differs,
            "number_absent_in_kernel_table": absent, "kernel_entry_is_nosys": nosys,
            "kernel_entry_depends_on_unresolved_option": unresolved}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("audit")
    a1.add_argument("programs", nargs="+", type=Path)
    a1.add_argument("--cache", type=Path)
    a2 = sub.add_parser("closure")
    a2.add_argument("programs", nargs="+", type=Path)
    a2.add_argument("--cache", type=Path, required=True)
    a3 = sub.add_parser("syscalls")
    a3.add_argument("--cache", type=Path, required=True)
    a3.add_argument("--image", default="/usr/lib/system/libsystem_kernel.dylib")
    a3.add_argument("--master", type=Path, required=True)
    a3.add_argument("--traps", type=Path, required=True)
    a3.add_argument("--config-dir", type=Path, required=True, help="the kernel tree's config/ directory")
    a3.add_argument("--config-file", default="MASTER.arm64.e1s")
    a3.add_argument("--config", default="DEVELOPMENT")
    a4 = sub.add_parser("program-syscalls")
    a4.add_argument("programs", nargs="+", type=Path)
    a4.add_argument("--master", type=Path, required=True)
    a4.add_argument("--traps", type=Path, required=True)
    a4.add_argument("--config-dir", type=Path, required=True, help="the kernel tree's config/ directory")
    a4.add_argument("--config-file", default="MASTER.arm64.e1s")
    a4.add_argument("--config", default="DEVELOPMENT")
    a6 = sub.add_parser("commpage", help="commpage fields referenced by images of the cache and by programs (heuristic)")
    a6.add_argument("--cache", type=Path)
    a6.add_argument("--image", action="append", default=[], help="cache image path (repeatable)")
    a6.add_argument("--program", action="append", default=[], type=Path)
    a6.add_argument("--header", type=Path, required=True, help="osfmk/arm/cpu_capabilities.h of the kernel tree")
    a7 = sub.add_parser("sysregs", help="mrs/msr system-register accesses of images of the cache and of programs")
    a7.add_argument("--cache", type=Path)
    a7.add_argument("--image", action="append", default=[], help="cache image path (repeatable)")
    a7.add_argument("--program", action="append", default=[], type=Path)
    a5 = sub.add_parser("cstrings", help="list the __TEXT,__cstring strings of a program that match any of the regexes")
    a5.add_argument("program", type=Path)
    a5.add_argument("--match", action="append", required=True, help="regex (repeatable)")
    args = ap.parse_args(argv)
    out = {}
    if args.cmd in ("commpage", "sysregs"):
        if args.image and not args.cache:
            raise AuditError("--image needs --cache")
        sources = {}
        dsc = None
        try:
            if args.image:
                dsc = Dsc(args.cache)
                for img in args.image:
                    m, _addr = dsc.macho(img)
                    sources[img] = text_of(m, dsc.read)
            for prog in args.program:
                data = prog.read_bytes()
                off, size = fat_slice(data)
                m = parse_macho(data, off, size)
                sec = next((x for x in m["sections"] if x["segment"] == "__TEXT" and x["name"] == "__text"), None)
                if sec is None:
                    raise AuditError("%s: no __TEXT,__text" % prog)
                sources[str(prog)] = (sec["addr"], data[off + sec["offset"]: off + sec["offset"] + sec["size"]])
        finally:
            if dsc is not None:
                dsc.close()
        if args.cmd == "sysregs":
            out = {"images": {}}
            for label, (taddr, text) in sources.items():
                counts = {}
                for _a, kind, name in scan_sysregs(text, taddr):
                    counts[(name, kind)] = counts.get((name, kind), 0) + 1
                out["images"][label] = {"registers": [
                    {"register": name, "access": kind, "count": n, "implementation_defined": implementation_defined(name)}
                    for (name, kind), n in sorted(counts.items())]}
        else:
            names = parse_commpage_names(args.header.read_text())
            out = {"commpage_rw_base": hex(COMMPAGE_RW), "commpage_ro_base": hex(COMMPAGE_RO), "header_fields": len(names), "images": {}}
            for label, (taddr, text) in sources.items():
                hits = scan_commpage(text, taddr)
                seen = {}
                for _a, region, off in hits:
                    seen[(region, off)] = seen.get((region, off), 0) + 1
                out["images"][label] = {"references": len(hits), "offsets": [
                    dict({"page": region, "offset": hex(off), "references": n},
                         **nearest_field(names, region, off)) for (region, off), n in sorted(seen.items())]}
    elif args.cmd == "cstrings":
        data = args.program.read_bytes()
        off, size = fat_slice(data)
        m = parse_macho(data, off, size)
        sec = next((x for x in m["sections"] if x["segment"] == "__TEXT" and x["name"] == "__cstring"), None)
        if sec is None:
            raise AuditError("%s: no __TEXT,__cstring" % args.program)
        blob = data[off + sec["offset"]: off + sec["offset"] + sec["size"]]
        strings = [s.decode("utf-8", "replace") for s in blob.split(b"\0") if s]
        pats = [re.compile(p) for p in args.match]
        out = {"program": str(args.program), "cstring_count": len(strings),
               "matches": {p.pattern: sorted({s for s in strings if p.search(s)}) for p in pats}}
    elif args.cmd in ("audit", "closure"):
        dsc = Dsc(args.cache) if args.cache else None
        paths = {str(p): p for p in args.programs}
        out["programs"] = {}
        parsed = {}
        for label, p in paths.items():
            data = p.read_bytes()
            off, size = fat_slice(data)
            m = parse_macho(data, off, size)
            parsed[label] = m
            info = summarize(m)
            if dsc:
                info["libraries_in_cache"] = [l["name"] for l in m["libraries"] if l["name"] in dsc.by_path]
                info["libraries_not_in_cache"] = [l["name"] for l in m["libraries"] if l["name"] not in dsc.by_path]
            out["programs"][label] = info
        if args.cmd == "closure":
            for label, m in parsed.items():
                todo = [(l["name"], l["kind"], label.rsplit("/", 1)[-1]) for l in m["libraries"]]
                seen, missing = set(), {}
                while todo:
                    name, kind, via = todo.pop()
                    if name in seen:
                        continue
                    seen.add(name)
                    if name not in dsc.by_path:
                        missing[name] = {"kind": kind, "first_referrer": via, "required": kind != "LOAD_WEAK_DYLIB"}
                        continue
                    dm, _ = dsc.macho(name)
                    todo.extend((l["name"], l["kind"], name) for l in dm["libraries"])
                out["programs"][label]["closure"] = {"images": len(seen) - len(missing), "missing": missing,
                                                     "missing_required": sorted(n for n, v in missing.items() if v["required"])}
        if dsc:
            out["cache"] = {"files": len(dsc.files), "images": len(dsc.images), "magic": dsc.magic, "platform": dsc.platform,
                            "os_version": version(dsc.os_version), "shared_region_start": hex(dsc.shared_region_start),
                            "shared_region_size": hex(dsc.shared_region_size)}
            dsc.close()
    elif args.cmd == "syscalls":
        dsc = Dsc(args.cache)
        m, base = dsc.macho(args.image)
        taddr, text = text_of(m, dsc.read)
        pairs, total = scan_svc(text, taddr)
        names_at = {}
        if m["exports_trie"]:
            lk = next(s for s in m["segments"] if s["name"] == "__LINKEDIT")
            dataoff, datasize = m["exports_trie"]
            trie = dsc.read(lk["vmaddr"] + (dataoff - lk["fileoff"]), datasize)
            text_base = next(s for s in m["segments"] if s["name"] == "__TEXT")["vmaddr"]
            for sym, (_fl, off) in parse_exports(trie).items():
                if off is not None:
                    names_at.setdefault(text_base + off, []).append(sym)
        cfg = args.config_dir
        tags = enabled_tags(parse_config_bundles((cfg / args.config_file).read_text()), args.config)
        states = option_states([(cfg / n).read_text() for n in ("MASTER", "MASTER.arm64", args.config_file)], tags)
        alts = parse_master_alternatives(args.master.read_text())
        bsd = effective_syscalls(alts, states)
        guards = sorted({g for lst in alts.values() for gs, _n in lst for g, _w in gs})
        mach = parse_mach_traps(args.traps.read_text())
        cmp = compare_numbers([(a, n) for a, n in pairs], names_at, bsd, mach)
        out = {"image": args.image, "text_bytes": len(text), "svc_80_total": total, "svc_with_x16_immediate": len(pairs),
               "svc_without_x16_immediate": total - len(pairs),
               "distinct_bsd_numbers": len({n for _a, n in pairs if n >= 0}),
               "distinct_mach_traps": len({n for _a, n in pairs if n < 0}),
               "kernel_tables": {"bsd_entries": len(bsd), "mach_traps": len(mach),
                                 "config": "%s of %s" % (args.config, args.config_file),
                                 "guards_in_master": {g: states.get(g, "unresolved") for g in guards}},
               "comparison": cmp}
        dsc.close()
    else:
        cfg = args.config_dir
        tags = enabled_tags(parse_config_bundles((cfg / args.config_file).read_text()), args.config)
        states = option_states([(cfg / n).read_text() for n in ("MASTER", "MASTER.arm64", args.config_file)], tags)
        bsd = effective_syscalls(parse_master_alternatives(args.master.read_text()), states)
        mach = parse_mach_traps(args.traps.read_text())
        out["config"] = "%s of %s" % (args.config, args.config_file)
        out["programs"] = {}
        for p in args.programs:
            data = p.read_bytes()
            off, size = fat_slice(data)
            m = parse_macho(data, off, size)
            sec = next((x for x in m["sections"] if x["segment"] == "__TEXT" and x["name"] == "__text"), None)
            if sec is None:
                raise AuditError("%s: no __TEXT,__text" % p)
            taddr, text = sec["addr"], data[off + sec["offset"]: off + sec["offset"] + sec["size"]]
            pairs, total = scan_svc(text, taddr)
            nums = sorted({n for _a, n in pairs})
            out["programs"][str(p)] = {"svc_80_total": total, "numbers": [
                dict(zip(("kernel", "status"), bsd.get(n, ("(no entry)", "absent")) if n >= 0
                         else (mach.get(-n, "(no entry)"), "mach trap table")), number=n)
                for n in nums]}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
