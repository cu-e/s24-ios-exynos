#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""IOS-014: static inspection of the donor's prebuilt libhakios.dylib against the donor's inject.c (host, read-only, nothing is executed).

The dylib is a binary built by the donor on its own machine; this host cannot rebuild it (no iPhoneOS SDK, no ld64).  What can be compared is
what both sides state in the open:
  * strings: every C string literal of inject.c (adjacent literals concatenated, escapes decoded) is searched as a byte string in the
    dylib's __TEXT,__cstring; every dylib cstring is searched in the literals of inject.c.  A string of the dylib that no literal of
    inject.c contains is reported as UNEXPLAINED, never as a match;
  * imports: the undefined symbols of the dylib's symbol table, and whether each name occurs as a token in inject.c;
  * constants: every 32/64-bit hex constant of inject.c with at least 7 hex digits is searched in the values that `movz`/`movk`/`movn` sequences and
    `orr Rd, xzr, #bitmask` of __TEXT,__text materialise (value equality only) and as 8-byte little-endian words anywhere in the file; a
    constant that is only added to (`VSLOT(vtable, offset)`) can be folded by the compiler, so a value just above it is reported as a weak hint;
  * `svc` instructions in __TEXT,__text (a raw system call would bypass the imports; expected none);
  * structure: install name, platform/minos/sdk, dependent libraries, section list, __mod_init_func entries (inject.c has one constructor).
A row says `found`, `not found` or `not comparable`; `found` means equal bytes or an equal value, not that the code does what inject.c does.
"""
import argparse
import importlib.util
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


MA = _load("ios014_macho_audit", ROOT / "tools" / "ios" / "macho_audit.py")

ESC = {"n": 10, "t": 9, "r": 13, "a": 7, "b": 8, "f": 12, "v": 11, "\\": 92, "'": 39, '"': 34, "?": 63}


def strip_comments(src, blank_literals=False):
    """C source -> same source with comments blanked (newlines kept); string and char literals are respected and, with blank_literals, emptied."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:j]))
            i = j
        elif c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(c + c if blank_literals else src[i:j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def decode_literal(body):
    """The text between the quotes of a C string literal -> bytes (simple, octal and \\x escapes)."""
    out, i = bytearray(), 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out += c.encode()
            i += 1
            continue
        i += 1
        d = body[i]
        if d in ESC:
            out.append(ESC[d])
            i += 1
        elif d == "x":
            j = i + 1
            while j < len(body) and body[j] in "0123456789abcdefABCDEF":
                j += 1
            out.append(int(body[i + 1:j], 16) & 0xFF)
            i = j
        elif d in "01234567":
            j = i
            while j < len(body) and j < i + 3 and body[j] in "01234567":
                j += 1
            out.append(int(body[i:j], 8) & 0xFF)
            i = j
        else:
            raise ValueError("unsupported escape \\%s" % d)
    return bytes(out)


LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
INCLUDE = re.compile(r"[ \t]*#[ \t]*include\b[^\n]*")


def string_literals(src):
    """Strings of a C file, in file order: one scanner over comments, character literals, `#include` lines and string literals; adjacent
    string literals (only whitespace or comments between them) are one string."""
    res, i, n, cur = [], 0, len(src), None
    at_line_start = True
    while i < n:
        c = src[i]
        if c == "\n":
            at_line_start = True
            i += 1
            continue
        if c in " \t\r\f\v":
            i += 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if at_line_start and c == "#":
            m = INCLUDE.match(src, i)
            if m:
                i = m.end()
                continue
        at_line_start = False
        if c == '"':
            m = LIT.match(src, i)
            if not m:
                raise ValueError("unterminated string literal near offset %d" % i)
            cur = (cur or b"") + decode_literal(m.group(1))
            i = m.end()
            continue
        if cur is not None:
            res.append(cur)
            cur = None
        if c == "'":
            j = i + 1
            while j < n and src[j] != "'":
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        else:
            i += 1
    if cur is not None:
        res.append(cur)
    return res


def hex_constants(src):
    code = strip_comments(src, blank_literals=True)
    vals = {}
    for m in re.finditer(r"\b0[xX]([0-9a-fA-F]{7,16})(?:[uUlL]*)\b", code):
        v = int(m.group(1), 16)
        vals.setdefault(v, code.count("\n", 0, m.start()) + 1)
    return vals


def bitmask_immediate(sf, n, immr, imms):
    """DecodeBitMasks of the A64 logical-immediate encoding (Arm ARM, `orr`): the value, or None for a reserved encoding."""
    x = (n << 6) | (~imms & 63)
    if x == 0:
        return None
    length = x.bit_length() - 1
    if length == 0 or (not sf and n):
        return None
    esize = 1 << length
    levels = esize - 1
    s_, r_ = imms & levels, immr & levels
    if s_ == levels:
        return None
    elem = (1 << (s_ + 1)) - 1
    elem = ((elem >> r_) | (elem << (esize - r_))) & ((1 << esize) - 1)
    size = 64 if sf else 32
    v = 0
    for i in range(0, size, esize):
        v |= elem << i
    return v


def decode_movs(text, base):
    """Values built by movz/movk (64- and 32-bit forms) in `text` (bytes at address `base`).  Every value reached after a movz or a movk of a
    register's running value is a candidate: {value: first address}.  Value equality only, with no data-flow."""
    regs, out = {}, {}
    for k in range(0, len(text) - 3, 4):
        w = struct.unpack_from("<I", text, k)[0]
        opc, hw, imm, rd = (w >> 29) & 3, (w >> 21) & 3, (w >> 5) & 0xFFFF, w & 31
        if (w >> 23) & 0x3F == 0x24 and opc == 1 and (w >> 5) & 31 == 31:  # orr Rd, xzr, #bitmask (MOV alias): sf 01 100100 N immr imms Rn Rd
            v = bitmask_immediate(w >> 31, (w >> 22) & 1, (w >> 16) & 63, (w >> 10) & 63)
            if v is not None:
                regs[(w >> 31, rd)] = v
                out.setdefault(v, base + k)
            continue
        if (w >> 23) & 0x3F != 0x25 or opc == 1:  # MOV wide immediate: sf opc 100101 hw imm16 rd (opc 0 movn, 2 movz, 3 movk)
            continue
        sf = w >> 31
        if not sf and hw > 1:
            continue
        shift = hw * 16
        if opc == 0:  # movn
            regs[(sf, rd)] = ~(imm << shift) & ((1 << (64 if sf else 32)) - 1)
        elif opc == 2:  # movz
            regs[(sf, rd)] = imm << shift
        elif (sf, rd) in regs:  # movk
            r = regs[(sf, rd)]
            regs[(sf, rd)] = (r & ~(0xFFFF << shift) & ((1 << (64 if sf else 32)) - 1)) | (imm << shift)
        else:
            continue
        out.setdefault(regs[(sf, rd)], base + k)
    return out


def symtab(data, base=0):
    """(undefined names, defined names, {defined name: address}) from LC_SYMTAB of a thin Mach-O."""
    ncmds, sizeofcmds = struct.unpack_from("<II", data, base + 16)
    off = base + 32
    und, dfn, values = [], [], {}
    for _ in range(ncmds):
        cmd, csize = struct.unpack_from("<II", data, off)
        if cmd == 2:
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", data, off + 8)
            for i in range(nsyms):
                n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from("<IBBHQ", data, symoff + 16 * i)
                if n_type & 0xE0:  # debug stab
                    continue
                name = MA.cstr(data, stroff + n_strx)
                if (n_type & 0x0E) == 0 and n_type & 1:
                    und.append(name)
                else:
                    dfn.append(name)
                    values[name] = n_value
        off += csize
    return und, dfn, values


def tokens(src):
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", strip_comments(src)))


def mod_inits(data, m, values):
    """Initialisers of the image: raw 8-byte words of every __mod_init_func section (chained-fixup pointers are not resolved: the low 36 bits are
    the target for DYLD_CHAINED_PTR_64) and the 4-byte offsets of __TEXT,__init_offsets (from the image base, the vmaddr of the first segment);
    each is matched with the defined symbol at that address."""
    res = []
    by_addr = {}
    for name, addr in values.items():
        by_addr.setdefault(addr, []).append(name)
    base = min((g["vmaddr"] for g in m["segments"] if g["name"] == "__TEXT"), default=0)
    for s in m["sections"]:
        if s["name"] == "__init_offsets":
            for k in range(s["size"] // 4):
                off = struct.unpack_from("<I", data, s["offset"] + 4 * k)[0]
                res.append({"section": s["segment"] + "," + s["name"], "offset": "%#x" % off, "address": "%#x" % (base + off),
                            "symbols_at_address": sorted(by_addr.get(base + off, []))})
        if s["name"] == "__mod_init_func":
            for k in range(s["size"] // 8):
                w = struct.unpack_from("<Q", data, s["offset"] + 8 * k)[0]
                res.append({"section": s["segment"] + "," + s["name"], "word": "%#x" % w, "target_low36": "%#x" % (w & ((1 << 36) - 1))})
    return res


def cstrings(data, m):
    out = []
    for s in m["sections"]:
        if s["name"] in ("__cstring",):
            blob = bytes(data[s["offset"]:s["offset"] + s["size"]])
            out += [x for x in blob.split(b"\0") if x]
    return out


def inspect(dylib, source, extra=()):
    data = Path(dylib).read_bytes()
    src = Path(source).read_text(encoding="utf-8", errors="replace")
    for e in extra:  # headers of the same program: their string macros end up in the binary too
        src += "\n" + Path(e).read_text(encoding="utf-8", errors="replace")
    m = MA.parse_macho(data)
    lits = [x for x in string_literals(src) if len(x) >= 3]
    cs = cstrings(data, m)
    lit_all = b"\n".join(lits)
    rows = []
    for x in sorted(set(lits)):
        at = data.find(x)
        if at < 0:
            res = "not found"
        else:  # a `static const char names[]` lands in __TEXT,__const, not in __cstring: name the section of the first hit
            sec = [t["segment"] + "," + t["name"] for t in m["sections"] if t["offset"] <= at < t["offset"] + t["size"]]
            res = "found" + (" in " + sec[0] if sec else " outside every section")
        rows.append({"literal": x.decode("latin-1"), "result": res})
    unexplained = [c.decode("latin-1") for c in cs if c not in lit_all and not any(c in l for l in lits)]
    und, dfn, values = symtab(data)
    toks = tokens(src)
    imports = [{"symbol": s, "named_in_inject_c": s.lstrip("_") in toks} for s in sorted(und)]
    text = [s for s in m["sections"] if s["segment"] == "__TEXT" and s["name"] == "__text"]
    movs = decode_movs(bytes(data[text[0]["offset"]:text[0]["offset"] + text[0]["size"]]), text[0]["addr"]) if text else {}
    svcs = []
    if text:
        raw = bytes(data[text[0]["offset"]:text[0]["offset"] + text[0]["size"]])
        svcs = ["%#x" % (text[0]["addr"] + k) for k in range(0, len(raw) - 3, 4) if struct.unpack_from("<I", raw, k)[0] & 0xFFE0001F == 0xD4000001]
    consts = []
    for v, line in sorted(hex_constants(src).items()):
        if v in movs:
            res = "found as a movz/movk value at %#x" % movs[v]
        elif struct.pack("<Q", v) in data:
            res = "found as an 8-byte word in the file"
        elif v < 1 << 32 and struct.pack("<I", v) in data:
            res = "found as a 4-byte word in the file (weak: any data equal to it)"
        else:
            near = sorted(x for x in movs if v < x < v + 0x800)
            res = ("not found exactly; the compiler may have folded it into a sum: a movz/movk/orr value inside (%#x, %#x) exists: %s"
                   % (v, v + 0x800, ", ".join("%#x at %#x" % (x, movs[x]) for x in near[:4]))) if near else "not found"
        consts.append({"value": "%#x" % v, "inject_c_line": line, "result": res})
    return {
        "file": str(dylib), "size": len(data),
        "header": MA.summarize(m), "install_name": m["install_name"], "uuid": m["uuid"],
        "segments": m["segments"], "sections": [s["segment"] + "," + s["name"] + " size=%d" % s["size"] for s in m["sections"]],
        "initialisers": mod_inits(data, m, values),
        "defined_symbols": sorted(dfn), "undefined_symbols": imports,
        "string_rows": rows, "dylib_strings_not_in_inject_c": unexplained, "dylib_cstring_count": len(cs),
        "constant_rows": consts, "svc_instructions_in_text": svcs,
        "summary": {
            "inject_c_literals": len(rows), "literals_found": sum(r["result"].startswith("found") for r in rows),
            "literals_not_found": sum(r["result"] == "not found" for r in rows),
            "dylib_strings_unexplained": len(unexplained),
            "imports": len(imports), "imports_not_named_in_inject_c": sum(not i["named_in_inject_c"] for i in imports),
            "constants": len(consts), "constants_not_found": sum(c["result"] == "not found" for c in consts),
            "constants_found_exactly": sum(c["result"].startswith("found") for c in consts),
            "constants_found_only_as_a_nearby_sum": sum(c["result"].startswith("not found exactly") for c in consts),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dylib", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--extra-source", action="append", default=[], help="header of the same program (repeatable)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = inspect(a.dylib, a.source, a.extra_source)
    Path(a.out).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    print(json.dumps(r["summary"], indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
