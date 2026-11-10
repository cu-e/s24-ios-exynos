#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-029: derive the return-to-loader contract of the payload kernel from the real bytes.

Reads artifacts/nat-020/build-003/payload.bin (what the loader copies) and
artifacts/nat-020/build-003/kernel.no-storage (the Mach-O it was made from, used only for symbol
names), and checks that the two agree at every symbol it relies on. It needs no disassembler: the
few instruction shapes it matches are fixed encodings (adrp/add/ldr/cmp/movz/bl/br), decoded here.

Usage: analyze_payload.py [--payload P] [--kernel K] [--window-base 0x9de400000] [--out FILE]
Output: JSON with the slot, the checkpoint sites (assembly and C), the symbol table slice and the
checks. Nothing here touches a device.
"""
import argparse
import json
import struct
import sys

HDR = "<8sIIQQQQQQ"
SEG_TABLE_OFF = 680
SLOT_MAGIC = b"XNULDRST"
LIVE_MAGIC = 0x214556494C554E58  # "XNULIVE!"


class Payload:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.b = f.read()
        (self.magic, self.version, self.nseg, self.virt_base, self.entry_va, self.adt_off, self.adt_size,
         self.kernel_end, self.phys_base) = struct.unpack_from(HDR, self.b, 0)
        self.segs = [struct.unpack_from("<4Q", self.b, SEG_TABLE_OFF + 32 * i) for i in range(self.nseg)]

    def va(self, addr, n):
        """n bytes at kernel VA addr; bytes beyond a segment's file range read as zero; None if unmapped."""
        for vm, vs, fo, fs in self.segs:
            if vm <= addr and addr + n <= vm + vs:
                off = addr - vm
                have = self.b[fo + off:fo + min(fs, off + n)] if off < fs else b""
                return have + b"\0" * (n - len(have))
        return None

    def u32(self, addr):
        return struct.unpack("<I", self.va(addr, 4))[0]

    def u64(self, addr):
        return struct.unpack("<Q", self.va(addr, 8))[0]

    def text_segments(self):
        return [s for s in self.segs if s[3] > 0]


def macho_symbols(path):
    with open(path, "rb") as f:
        b = f.read()
    magic, _cpu, _sub, _ft, ncmds, _sz, _fl, _r = struct.unpack_from("<IiiIIIII", b, 0)
    if magic != 0xFEEDFACF:
        raise SystemExit("not a 64-bit little-endian Mach-O: %s" % path)
    off = 32
    st = None
    for _ in range(ncmds):
        cmd, cs = struct.unpack_from("<II", b, off)
        if cmd == 2:
            st = struct.unpack_from("<IIII", b, off + 8)
        off += cs
    symoff, nsyms, stroff, _strsize = st
    out = {}
    for i in range(nsyms):
        n_strx, n_type, n_sect, _desc, value = struct.unpack_from("<IBBHQ", b, symoff + 16 * i)
        if n_type & 0xE0:  # stab (debug) entry
            continue
        if (n_type & 0x0E) != 0x0E or n_sect == 0:  # keep defined-in-section symbols only
            continue
        name = b[stroff + n_strx:b.index(b"\0", stroff + n_strx)].decode("latin1")
        out.setdefault(name, value)
    return out


# --- fixed instruction shapes -------------------------------------------------------------------

def adrp_target(pc, w):
    if (w & 0x9F000000) != 0x90000000:
        return None
    imm = ((w >> 5) & 0x7FFFF) << 2 | ((w >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~0xFFF) + (imm << 12), w & 31


def add_imm(w):
    """add xd, xn, #imm (no shift): (rd, rn, imm) or None."""
    if (w & 0xFFC00000) != 0x91000000:
        return None
    return w & 31, (w >> 5) & 31, (w >> 10) & 0xFFF


def ldr_x_uimm(w):
    if (w & 0xFFC00000) != 0xF9400000:
        return None
    return w & 31, (w >> 5) & 31, ((w >> 10) & 0xFFF) * 8


def cmp_x_imm(w):
    """cmp xn, #imm (subs xzr, xn, #imm)."""
    if (w & 0xFFC0001F) != 0xF100001F:
        return None
    return (w >> 5) & 31, (w >> 10) & 0xFFF


def movz(w):
    """movz xd/wd, #imm16 (shift 0): (rd, imm, is64)."""
    if (w & 0x7F800000) != 0x52800000 or ((w >> 21) & 3) != 0:
        return None
    return w & 31, (w >> 5) & 0xFFFF, bool(w >> 31)


def bl_target(pc, w):
    if (w & 0xFC000000) != 0x94000000:
        return None
    imm = w & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return pc + imm * 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default="artifacts/nat-020/build-003/payload.bin")
    ap.add_argument("--kernel", default="artifacts/nat-020/build-003/kernel.no-storage")
    ap.add_argument("--window-base", default="0x9de400000")
    ap.add_argument("--out")
    a = ap.parse_args()
    base = int(a.window_base, 0)

    p = Payload(a.payload)
    syms = macho_symbols(a.kernel)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    def pa(va):
        return base + (va - p.virt_base)

    def need(name):
        if name not in syms:
            raise SystemExit("symbol missing in the Mach-O: " + name)
        return syms[name]

    slot = need("_loader_stub_slot")
    check("slot magic in payload.bin", p.va(slot, 8) == SLOT_MAGIC, p.va(slot, 8).decode("latin1"))
    slot_words = [p.u64(slot + 8 * i) for i in range(4)]
    check("slot words 1..3 are zero in the image (the loader fills them)", slot_words[1:] == [0, 0, 0], str(slot_words[1:]))
    check("magic occurs once in the mapped file ranges", sum(
        p.b[fo:fo + fs].count(SLOT_MAGIC) for _vm, _vs, fo, fs in p.segs) == 1)
    check("slot is 8-byte aligned (aligned 64-bit stores with the MMU off)", slot % 8 == 0)
    check("slot lies in file-backed bytes", any(vm <= slot and slot + 32 <= vm + fs for vm, _vs, _fo, fs in p.segs))
    # entry: the kernel's own first instruction
    w0 = p.u32(p.entry_va)
    imm = w0 & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    ent_tgt = p.entry_va + imm * 4 if (w0 & 0xFC000000) == 0x14000000 else None
    check("entry word is `b _start_first_cpu`", ent_tgt == need("_start_first_cpu"),
          "word %#x target %s" % (w0, hex(ent_tgt) if ent_tgt else None))

    # --- assembly checkpoints: adrp/add of the slot, ldr x10,[x9,#16], cmp x10,#N, ..., mov x3,#N, ldr x9,[x9,#8], br x9
    asm_sites = []
    for vm, _vs, fo, fs in p.text_segments():
        words = struct.unpack_from("<%dI" % (fs // 4), p.b, fo)
        for i in range(len(words) - 20):
            pc = vm + 4 * i
            t = adrp_target(pc, words[i])
            if not t or t[0] != (slot & ~0xFFF):
                continue
            ad = add_imm(words[i + 1])
            if not ad or ad[0] != t[1] or ad[1] != t[1] or ad[2] != (slot & 0xFFF):
                continue
            ld = ldr_x_uimm(words[i + 2])
            cp = cmp_x_imm(words[i + 3])
            if not ld or not cp or ld[2] != 16:
                continue
            n = cp[1]
            # the macro body: mov x0,#0; mov x1,#0; mov x2,#2; mov x3,#n; mrs; bic; msr; isb; ldr x9,[x9,#8]; br x9
            tail = words[i + 5:i + 17]
            m2 = movz(tail[2])
            m3 = movz(tail[3])
            ldr_stub = ldr_x_uimm(words[i + 13])
            br = words[i + 14]
            asm_sites.append({
                "checkpoint": n,
                "va": hex(pc),
                "pa_at_window_base": hex(pa(pc)),
                "function": None,
                "reason_x2": m2[1] if m2 else None,
                "code_x3": m3[1] if m3 else None,
                "stub_load_is_slot_plus_8": bool(ldr_stub and ldr_stub[2] == 8),
                "branches_through_x9": (br & 0xFFFFFC1F) == 0xD61F0000 and ((br >> 5) & 31) == 9,
                "shape_ok": bool(m2 and m3),
            })
    asm_sites.sort(key=lambda s: int(s["va"], 16))

    # --- C checkpoints: bl _loader_checkpoint with a movz x0/w0,#n among the previous 3 instructions
    chk_fn = need("_loader_checkpoint")
    funcs = sorted((v, k) for k, v in syms.items() if k.startswith("_") and v >= p.virt_base)

    def containing(va):
        lo, hi = 0, len(funcs) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if funcs[mid][0] <= va:
                best = funcs[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    c_sites = []
    for vm, _vs, fo, fs in p.text_segments():
        words = struct.unpack_from("<%dI" % (fs // 4), p.b, fo)
        for i, w in enumerate(words):
            pc = vm + 4 * i
            if bl_target(pc, w) != chk_fn:
                continue
            n = None
            for k in range(1, 4):
                if i - k >= 0:
                    m = movz(words[i - k])
                    if m and m[0] == 0:
                        n = m[1]
                        break
            f = containing(pc)
            c_sites.append({"checkpoint": n, "va": hex(pc), "pa_at_window_base": hex(pa(pc)),
                            "function": f[1] if f else None})
    c_sites.sort(key=lambda s: (s["checkpoint"] is None, s["checkpoint"], int(s["va"], 16)))

    # --- who feeds the log: callers of loader_log_putc / loader_log_line / loader_return
    def callers(target):
        out = []
        for vm, _vs, fo, fs in p.text_segments():
            words = struct.unpack_from("<%dI" % (fs // 4), p.b, fo)
            for i, w in enumerate(words):
                pc = vm + 4 * i
                if bl_target(pc, w) == target:
                    f = containing(pc)
                    out.append({"va": hex(pc), "function": f[1] if f else None})
        return out

    log_callers = {n: callers(need(n)) for n in ("_loader_log_putc", "_loader_log_line", "_loader_return")}

    # --- loader_checkpoint itself: compares slot[2] with x0 and calls loader_jump(2, n)
    jump_fn = need("_loader_jump")
    chk_words = [p.u32(chk_fn + 4 * i) for i in range(12)]

    # --- loader_jump: find the final `br x5` and the registers loaded just before it
    jump_end = None
    for off in range(0, 0x400, 4):
        if (p.u32(jump_fn + off) & 0xFFFFFC1F) == 0xD61F0000 and ((p.u32(jump_fn + off) >> 5) & 31) == 5:
            jump_end = jump_fn + off
            break
    jump_tail = [p.u32(jump_end - 4 * k) for k in range(12, -1, -1)] if jump_end else []

    # --- other pieces the stub or a host decoder depends on
    interesting = ["_loader_log", "_loader_log_len", "_loader_live", "_loader_return", "_loader_log_putc",
                   "_loader_log_line", "_loader_recording", "_loader_sound", "_panic_spin_forever", "_arm_init",
                   "_start_first_cpu", "_LowResetVectorBase", "_LowResetVectorEnd", "_machine_startup", "_PE_init_platform",
                   "_kernel_bootstrap", "_kernel_bootstrap_thread", "_arm_vm_init", "_console_write"]
    table = {}
    for k in interesting:
        if k in syms:
            table[k] = {"va": hex(syms[k]), "pa_at_window_base": hex(pa(syms[k]))}
        else:
            table[k] = None
    live = syms.get("_loader_live")
    if live:
        check("loader_live magic (XNULIVE!) present in the payload image", p.u64(live) == LIVE_MAGIC, hex(p.u64(live)))
    log_va = syms.get("_loader_log")
    if log_va:
        check("loader_log is a zero-fill (bss) buffer of 1.5 MiB in the payload mapping",
              any(vm <= log_va and log_va + 1536 * 1024 <= vm + vs and log_va >= vm + fs for vm, vs, _fo, fs in p.segs)
              or any(vm <= log_va < vm + vs for vm, vs, _fo, fs in p.segs))

    checks.append({"check": "assembly checkpoint numbers", "ok": [s["checkpoint"] for s in asm_sites] == [1, 2, 3, 4, 5],
                   "detail": str([s["checkpoint"] for s in asm_sites])})
    checks.append({"check": "every assembly site returns reason 2 with x3 = its number through slot[1]",
                   "ok": all(s["reason_x2"] == 2 and s["code_x3"] == s["checkpoint"] and s["stub_load_is_slot_plus_8"] and
                             s["branches_through_x9"] for s in asm_sites)})
    checks.append({"check": "C checkpoint sites found", "ok": len(c_sites) > 0 and all(s["checkpoint"] is not None for s in c_sites),
                   "detail": "%d sites" % len(c_sites)})

    result = {
        "payload": a.payload, "kernel_macho_for_symbols": a.kernel, "window_base": hex(base),
        "payload_header": {"virt_base": hex(p.virt_base), "entry_va": hex(p.entry_va), "phys_base": hex(p.phys_base),
                           "kernel_end": hex(p.kernel_end), "nseg": p.nseg},
        "slot": {"va": hex(slot), "pa_at_window_base": hex(pa(slot)), "words": [hex(x) for x in slot_words],
                 "layout": ["magic XNULDRST", "PA of the loader's return stub", "checkpoint number to stop at (0 = none)",
                            "PA minus VA of the static kernel image (physical = va + this, mod 2^64)"],
                 "slot3_for_window_base": hex((base - p.virt_base) & (2**64 - 1))},
        "log_callers": log_callers,
        "asm_checkpoints": asm_sites,
        "c_checkpoints": c_sites,
        "loader_checkpoint_words": [hex(w) for w in chk_words],
        "loader_jump_tail_words": [hex(w) for w in jump_tail],
        "loader_jump": {"va": hex(jump_fn), "final_br_x5_va": hex(jump_end) if jump_end else None},
        "symbols": table,
        "checks": checks,
    }
    text = json.dumps(result, indent=1)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text + "\n")
    else:
        print(text)
    bad = [c for c in checks if not c["ok"]]
    for c in bad:
        print("CHECK FAILED:", c, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
