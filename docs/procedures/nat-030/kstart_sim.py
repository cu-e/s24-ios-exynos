#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-030: run the payload kernel's real start code (`_start_first_cpu`) on the host.

Host-test / simulation only. This executes the bytes of the payload kernel (the file the loader copies,
artifacts/nat-020/build-003/payload.bin) with a small AArch64 interpreter: capstone decodes, the code
below executes. Memory is a flat RAM window; once SCTLR_EL1.M is set, a 4 KiB-granule table walker reads
the page tables the kernel itself wrote and translates every fetch, load and store.

What it models: X registers, SP_EL0/SP_EL1, NZCV, the system registers the start code writes, address
translation (TTBR0/TTBR1, TCR T0SZ/T1SZ/TG/EPD/IPS, block and page descriptors, AF and AP/XN checks).
What it does not model: caches, the TLB (tables are re-read on every access, so a missing barrier or
a stale TLB entry cannot show up), the exception model (a fault raises SimFault: it says "hardware would
take an exception here", not what the vector does), timing, any device, and every instruction the start
code does not use (an unknown one raises). A pass says only that the loader's boot_args and RAM window
are consistent with what this code does with them. It is not evidence about the S24.
"""
import argparse
import collections
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nat-029"))
import analyze_payload as ap  # noqa: E402

try:
    import capstone
except ImportError:  # pragma: no cover - the tests skip without capstone
    capstone = None

M64 = (1 << 64) - 1
PAGE = 4096
BOOT_ARGS_SIZE = 736
# Offsets in the loader's struct boot_args (loader.c asserts Video at 40 and CommandLine at 108).
BA_OFF = dict(Revision=0, Version=2, virtBase=8, physBase=16, memSize=24, topOfKernelData=32,
              deviceTreeP=96, deviceTreeLength=104, memSizeActual=728)
SCTLR_RESET = 0x30d00800


class SimFault(Exception):
    """The hardware would take an exception here (the simulator does not model what happens next)."""

    def __init__(self, kind, va, pc, detail=""):
        super().__init__("%s va=%#x pc=%#x %s" % (kind, va, pc, detail))
        self.kind, self.va, self.pc, self.detail = kind, va, pc, detail


class Sim:
    def __init__(self, payload_path, window_base, window_size, ba_overrides=None, x0=None):
        if capstone is None:
            raise RuntimeError("capstone is required")
        self.p = ap.Payload(payload_path)
        self.base, self.size = window_base, window_size
        self.pages = {}
        self.md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        self.md.detail = True
        self.x = [0] * 31
        self.sp_el = [0, 0]
        self.spsel = 0
        self.n = self.z = self.c = self.v = 0
        self.sr = {"sctlr_el1": SCTLR_RESET, "midr_el1": 0x412fd070, "dczid_el0": 4}
        self.sctlr_hist = [SCTLR_RESET]
        self.daif_masked = False
        self.events = []
        self.steps = 0
        self.executed = collections.Counter()   # mnemonic -> times executed
        self.taint = {}        # register number -> set of poisoned 16-bit lanes
        self.violations = []   # (pc, register, instruction): reads of a poisoned register
        # Kernel segments at PA = window base + (vmaddr - virt_base); the rest of a segment is the zero fill.
        for vm, vs, fo, fs in self.p.segs:
            self.write_pa(self.base + (vm - self.p.virt_base), self.p.b[fo:fo + fs])
        # boot_args exactly as the loader (loader.c, NAT-022) fills it: ADT right after the kernel image,
        # boot_args at the next 16 KiB boundary after the ADT (measured in run 007: base + 0x4978000).
        self.adt_pa = self.base + (self.p.kernel_end - self.p.virt_base)
        self.ba_pa = self.base + 0x4978000
        ba = dict(Revision=2, Version=2, virtBase=self.p.virt_base, physBase=self.base, memSize=self.size,
                  topOfKernelData=self.ba_pa + 0x4000, deviceTreeP=self.p.virt_base + (self.adt_pa - self.base),
                  deviceTreeLength=0x4000, memSizeActual=self.size)
        ba.update(ba_overrides or {})
        blob = bytearray(BOOT_ARGS_SIZE)
        for k, off in BA_OFF.items():
            struct.pack_into({"Revision": "<H", "Version": "<H", "deviceTreeLength": "<I"}.get(k, "<Q"), blob, off, ba[k])
        self.write_pa(self.ba_pa, bytes(blob))
        self.boot_args = ba
        # Entry state of the kernel copy: x0 = boot_args PA, EL1, MMU off, PC = entry address.
        self.x[0] = self.ba_pa if x0 is None else x0
        self.entry_pc = self.pc = self.base + (self.p.entry_va - self.p.virt_base)

    # --- physical memory ------------------------------------------------------------------------
    def _page(self, pa):
        k = pa & ~(PAGE - 1)
        if k not in self.pages:
            if not (self.base <= k < self.base + self.size):
                raise SimFault("external-abort", pa, self.pc, "PA outside the RAM window")
            self.pages[k] = bytearray(PAGE)
        return self.pages[k]

    def write_pa(self, pa, data):
        i = 0
        while i < len(data):
            pg = self._page(pa + i)
            o = (pa + i) & (PAGE - 1)
            n = min(PAGE - o, len(data) - i)
            pg[o:o + n] = data[i:i + n]
            i += n

    def read_pa(self, pa, n):
        out = bytearray()
        while len(out) < n:
            pg = self._page(pa + len(out))
            o = (pa + len(out)) & (PAGE - 1)
            out += pg[o:o + min(PAGE - o, n - len(out))]
        return bytes(out)

    def u64_pa(self, pa):
        return struct.unpack("<Q", self.read_pa(pa, 8))[0]

    # --- address translation --------------------------------------------------------------------
    def mmu_on(self):
        return self.sr["sctlr_el1"] & 1

    def walk(self, va, access):
        """VA -> PA through TTBR0/TTBR1, 4 KiB granule, start level 1 (TxSZ 25..33)."""
        tcr = self.sr.get("tcr_el1", 0)
        t0sz, t1sz = tcr & 63, (tcr >> 16) & 63
        if (va >> (64 - t0sz)) == 0:
            region, ttbr, sz, tg, epd = 0, self.sr.get("ttbr0_el1", 0), t0sz, (tcr >> 14) & 3, (tcr >> 7) & 1
        elif (va >> (64 - t1sz)) == (1 << t1sz) - 1:
            region, ttbr, sz, tg, epd = 1, self.sr.get("ttbr1_el1", 0), t1sz, (tcr >> 30) & 3, (tcr >> 23) & 1
        else:
            raise SimFault("translation-fault", va, self.pc, "VA in neither TTBR range")
        if epd:
            raise SimFault("translation-fault", va, self.pc, "TTBR%d walks disabled" % region)
        if (region == 0 and tg != 0) or (region == 1 and tg != 2):
            raise SimFault("unsupported", va, self.pc, "granule other than 4 KiB")
        if not 25 <= sz <= 33:
            raise SimFault("unsupported", va, self.pc, "T%dSZ %d" % (region, sz))
        ips_bits = {0: 32, 1: 36, 2: 40, 3: 42, 4: 44, 5: 48}.get((tcr >> 32) & 7, 48)
        table = ttbr & 0xFFFFFFFFF000
        for level, shift in ((1, 30), (2, 21), (3, 12)):
            nbits = (64 - sz - 30) if level == 1 else 9
            d = self.u64_pa(table + ((va >> shift) & ((1 << nbits) - 1)) * 8)
            if not d & 1:
                raise SimFault("translation-fault", va, self.pc, "level %d descriptor invalid" % level)
            if level == 3 and not d & 2:
                raise SimFault("translation-fault", va, self.pc, "reserved level 3 descriptor")
            if level < 3 and d & 2:           # table descriptor
                table = d & 0xFFFFFFFFF000
                continue
            if not d & (1 << 10):
                raise SimFault("access-flag-fault", va, self.pc, "level %d" % level)
            if access == "x" and d & ((1 << 53) | (1 << 54)):
                raise SimFault("permission-fault", va, self.pc, "XN")
            if access == "w" and d & (1 << 7):
                raise SimFault("permission-fault", va, self.pc, "read-only")
            pa = (d & 0xFFFFFFFFF000 & ~((1 << shift) - 1)) | (va & ((1 << shift) - 1))
            if pa >> ips_bits:
                raise SimFault("address-size-fault", va, self.pc, "PA %#x beyond IPS %d bits" % (pa, ips_bits))
            return pa
        raise SimFault("translation-fault", va, self.pc, "no leaf")

    def translate(self, va, access="r"):
        return self.walk(va, access) if self.mmu_on() else va

    def bootstrap_map(self, ttbr):
        """Scan a bootstrap L1->L2 table pair by reading the descriptors directly (no walker).
        Returns merged runs (offset_start, offset_end, pa_start, attr); offsets are relative to the base of
        the translation region (TTBR0: VA 0; TTBR1: the first VA of the high region)."""
        runs = []
        for i in range(256):
            d = self.u64_pa((ttbr & 0xFFFFFFFFF000) + i * 8)
            if not d:
                continue
            if d & 3 != 3:
                raise SimFault("unsupported", 0, self.pc, "L1[%d] is not a table descriptor" % i)
            l2 = d & 0xFFFFFFFFF000
            for j in range(512):
                e = self.u64_pa(l2 + j * 8)
                if not e:
                    continue
                if e & 3 != 1:
                    raise SimFault("unsupported", 0, self.pc, "L2[%d][%d] is not a block descriptor" % (i, j))
                off = (i << 30) | (j << 21)
                pa, attr = e & 0xFFFFFFFFF000 & ~0x1FFFFF, e & ~0xFFFFFFFFF000
                if runs and runs[-1][1] == off and runs[-1][2] + (runs[-1][1] - runs[-1][0]) == pa and runs[-1][3] == attr:
                    runs[-1][1] = off + 0x200000
                else:
                    runs.append([off, off + 0x200000, pa, attr])
        return [tuple(r) for r in runs]

    # --- virtual memory access --------------------------------------------------------------------
    def read(self, va, n):
        if va % n:
            raise SimFault("alignment-fault", va, self.pc)
        return int.from_bytes(self.read_pa(self.translate(va, "r"), n), "little")

    def write(self, va, n, val):
        if va % n:
            raise SimFault("alignment-fault", va, self.pc)
        self.write_pa(self.translate(va, "w"), (val & ((1 << 8 * n) - 1)).to_bytes(n, "little"))

    # --- registers --------------------------------------------------------------------------------
    @staticmethod
    def _reg(name):
        name = name.strip()
        if name in ("sp", "wsp"):
            return "sp", 64 if name == "sp" else 32
        if name in ("xzr", "wzr"):
            return "zr", 64 if name == "xzr" else 32
        return int(name[1:]), 64 if name[0] == "x" else 32

    def get(self, name):
        r, w = self._reg(name)
        v = 0 if r == "zr" else self.sp_el[self.spsel] if r == "sp" else self.x[r]
        return v & ((1 << w) - 1)

    def set(self, name, val):
        r, w = self._reg(name)
        val &= (1 << w) - 1
        if r == "sp":
            self.sp_el[self.spsel] = val
        elif r != "zr":
            self.x[r] = val

    def width(self, name):
        return self._reg(name)[1]

    @staticmethod
    def reg_width_or_64(tok):
        tok = tok.strip()
        if tok in ("sp", "xzr") or (tok[:1] == "x" and tok[1:].isdigit()):
            return 64
        if tok in ("wsp", "wzr") or (tok[:1] == "w" and tok[1:].isdigit()):
            return 32
        return 64

    def val(self, tok, width=64):
        tok = tok.strip()
        return int(tok[1:], 0) & ((1 << width) - 1) if tok.startswith("#") else self.get(tok)

    EXTENDS = {"uxtb": (8, False), "uxth": (16, False), "uxtw": (32, False), "uxtx": (64, False),
               "sxtb": (8, True), "sxth": (16, True), "sxtw": (32, True), "sxtx": (64, True)}

    def shifted(self, ops, i, width):
        """Operand i with its optional modifier operand: a shift (`lsl`/`lsr`/`asr`/`ror #n`) or a register
        extend (`uxtb`..`sxtx`, optional `#n` left shift), as the shifted/extended-register forms use it."""
        m = (1 << width) - 1
        v = self.val(ops[i], width)
        if i + 1 < len(ops) and ops[i + 1].strip().split()[0] in ("lsl", "lsr", "asr", "ror") + tuple(self.EXTENDS):
            parts = ops[i + 1].split()
            kind = parts[0]
            amt = int(parts[1].lstrip("#"), 0) if len(parts) > 1 else 0
            if kind in self.EXTENDS:
                bits, signed = self.EXTENDS[kind]
                v &= (1 << bits) - 1
                if signed and v >> (bits - 1):
                    v -= 1 << bits
                v = (v << amt) & m
            elif kind == "lsl":
                v = (v << amt) & m
            elif kind == "lsr":
                v >>= amt
            elif kind == "asr":
                v = ((v - (1 << width) if v >> (width - 1) else v) >> amt) & m
            else:                                     # ror
                amt %= width
                v = ((v >> amt) | (v << (width - amt))) & m
        return v

    def sub_flags(self, a, b, width):
        m = (1 << width) - 1
        res = (a - b) & m
        sb = 1 << (width - 1)
        self.n, self.z, self.c = (1 if res & sb else 0), (1 if res == 0 else 0), (1 if a >= b else 0)
        self.v = 1 if (a ^ b) & (a ^ res) & sb else 0
        return res

    def cond(self, cc):
        n, z, c, v = self.n, self.z, self.c, self.v
        return bool({"eq": z, "ne": not z, "cs": c, "hs": c, "cc": not c, "lo": not c, "mi": n, "pl": not n,
                     "vs": v, "vc": not v, "hi": c and not z, "ls": not c or z, "ge": n == v, "lt": n != v,
                     "gt": not z and n == v, "le": z or n != v, "al": 1, "nv": 1}[cc])

    def msr(self, name, val):
        name = name.strip()
        if name == "oslar_el1":
            return
        if name == "spsel":
            self.spsel = val & 1
            return
        self.sr[name] = val
        if name == "sctlr_el1":
            self.sctlr_hist.append(val)
        self.events.append(("msr", name, val, self.pc))

    def mrs(self, name):
        name = name.strip()
        if name not in self.sr:
            raise SimFault("unsupported", 0, self.pc, "mrs %s" % name)
        return self.sr[name]

    # --- operand parsing ----------------------------------------------------------------------------
    @staticmethod
    def split_ops(s):
        out, depth, cur = [], 0, ""
        for ch in s:
            depth += (ch == "[") - (ch == "]")
            if ch == "," and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        if cur.strip():
            out.append(cur)
        return out

    def mem_access(self, ops, i):
        """Effective address of the memory operand at ops[i] -> (address, finish), where finish() applies
        pre/post-index writeback. Forms: [x], [x, #n], [x, #n]!, [x], #n, [x, xm], [x, xm, lsl #n],
        [x, wm, uxtw|sxtw #n]; or a literal (`#address`)."""
        m = ops[i].strip()
        if m.startswith("#"):
            return int(m[1:], 0), lambda: None
        pre = m.endswith("!")
        m = m.rstrip("!")
        parts = [t.strip() for t in m[1:m.index("]")].split(",")]
        base = parts[0]
        if len(ops) > i + 1:                                # post-index: [x], #n
            wb = int(ops[i + 1].strip()[1:], 0)
            return self.get(base), (lambda: self.set(base, self.get(base) + wb))
        off = 0
        if len(parts) > 1 and parts[1].startswith("#"):
            off = int(parts[1][1:], 0)
        elif len(parts) > 1:                                # register offset
            r = self.get(parts[1])
            ext = parts[2].split() if len(parts) > 2 else []
            if ext and ext[0] == "sxtw":
                r = (r & 0xFFFFFFFF) - (1 << 32) if r & 0x80000000 else r & 0xFFFFFFFF
            elif ext and ext[0] == "uxtw":
                r &= 0xFFFFFFFF
            elif ext and ext[0] not in ("lsl", "sxtx", "uxtx"):
                raise SimFault("unsupported", 0, self.pc, "register-offset extend " + ext[0])
            amt = int(ext[1].lstrip("#"), 0) if len(ext) > 1 else 0
            off = r << amt                                  # every form (lsl/uxtx/sxtx/uxtw/sxtw) scales by #amt
        addr = (self.get(base) + off) & M64
        return addr, ((lambda: self.set(base, addr)) if pre else (lambda: None))

    # --- execution ------------------------------------------------------------------------------------
    def fetch(self):
        w = self.read_pa(self.translate(self.pc, "x"), 4)
        ins = list(self.md.disasm(w, self.pc))
        if not ins:
            raise SimFault("undefined", self.pc, self.pc, w.hex())
        return ins[0]

    def run(self, stop_pcs=(), limit=50000):
        stops = set(stop_pcs)
        while self.pc not in stops:
            self.steps += 1
            if self.steps > limit:
                raise SimFault("step-limit", self.pc, self.pc)
            self.step()
        return self.pc

    def run_until_high_pc(self, limit=50000):
        """Run until the PC is a high (TTBR1) address with the MMU on: the first instruction of the
        kernel's virtual-address code. Returns that PC."""
        while not (self.mmu_on() and self.pc >> 63):
            self.steps += 1
            if self.steps > limit:
                raise SimFault("step-limit", self.pc, self.pc)
            self.step()
        return self.pc

    def _taint_reads(self, i):
        regs_read, _ = i.regs_access()
        for r in regs_read:
            name = i.reg_name(r)
            if name[0] not in "xw" or name in ("xzr", "wzr"):
                continue
            n = int(name[1:])
            lanes = self.taint.get(n)
            if not lanes:
                continue
            if i.mnemonic == "movk" and n == int(i.op_str.split(",")[0].strip()[1:]):
                continue                       # movk keeps the other lanes; tracked per lane in _taint_writes
            if name[0] == "w":
                lanes = {l for l in lanes if l < 2}
            if lanes:
                self.violations.append((self.pc, name, i.mnemonic + " " + i.op_str))

    def _taint_writes(self, i):
        if i.mnemonic == "movk":
            ops = self.split_ops(i.op_str)
            lane = (int(ops[2].split("#")[1], 0) // 16) if len(ops) > 2 else 0
            self.taint.get(int(ops[0].strip()[1:]), set()).discard(lane)
            return
        _, regs_write = i.regs_access()
        for r in regs_write:
            name = i.reg_name(r)
            if name[0] in "xw" and name not in ("xzr", "wzr"):
                self.taint.pop(int(name[1:]), None)

    def step(self):
        i = self.fetch()
        mn, text = i.mnemonic, i.op_str
        self.executed[mn] += 1
        ops = self.split_ops(text)
        if self.taint:
            self._taint_reads(i)
        nxt = self.pc + 4
        g, s, v = self.get, self.set, self.val
        if mn in ("isb", "dsb", "dmb", "tlbi", "ic", "nop"):
            pass
        elif mn == "msr":
            tgt = ops[0].strip()
            if tgt in ("daifset", "daifclr"):
                imm = int(ops[1].strip()[1:], 0)
                self.daif_masked = tgt == "daifset" and imm & 0xF == 0xF
                self.events.append(("msr", tgt, imm, self.pc))
            elif ops[1].strip().startswith("#"):
                self.msr(tgt, int(ops[1].strip()[1:], 0))
            else:
                self.msr(tgt, g(ops[1]))
        elif mn == "mrs":
            s(ops[0], self.mrs(ops[1]))
        elif mn == "mov":
            s(ops[0], v(ops[1], self.width(ops[0])))
        elif mn == "movk":
            imm = int(ops[1].strip()[1:], 0)
            sh = int(ops[2].split("#")[1], 0) if len(ops) > 2 else 0
            s(ops[0], (g(ops[0]) & ~(0xFFFF << sh)) | (imm << sh))
        elif mn == "adrp":
            s(ops[0], int(ops[1].strip()[1:], 0))      # capstone resolves the page address against self.pc
        elif mn in ("add", "sub", "and", "orr", "subs", "cmp"):
            if mn == "cmp":
                ops, mn = [("xzr" if self.width(ops[0]) == 64 else "wzr")] + ops, "subs"
            w = self.width(ops[0])
            a = g(ops[1])
            if mn in ("add", "sub") and len(ops) > 3 and ops[2].strip().startswith("#") and ops[3].strip().startswith("lsl"):
                b = (int(ops[2].strip()[1:], 0) << int(ops[3].split("#")[1], 0)) & ((1 << w) - 1)
            else:
                b = self.shifted(ops, 2, w)
            s(ops[0], {"add": lambda: a + b, "sub": lambda: a - b, "and": lambda: a & b, "orr": lambda: a | b,
                       "subs": lambda: self.sub_flags(a, b, w)}[mn]())
        elif mn in ("lsl", "lsr"):
            wd = self.width(ops[0])
            a = g(ops[1])
            amt = int(ops[2].strip()[1:], 0) if ops[2].strip().startswith("#") else g(ops[2]) % wd
            s(ops[0], (a << amt) if mn == "lsl" else (a >> amt))
        elif mn == "csel":
            s(ops[0], g(ops[1]) if self.cond(ops[3].strip()) else g(ops[2]))
        elif mn in ("ldr", "str", "ldur", "stur", "ldrb", "strb", "ldrh", "strh", "ldurb", "sturb", "ldurh",
                    "sturh", "ldrsb", "ldrsh", "ldrsw", "ldursw", "ldursb", "ldursh"):
            size = {"b": 1, "h": 2}.get(mn[-1] if mn[-1] in "bh" else "", 0)
            signed = mn.startswith(("ldrs", "ldurs"))
            if mn.endswith("sw"):
                size = 4
            elif mn[-2:] in ("sb", "sh"):
                size = 1 if mn[-1] == "b" else 2
            nbytes = size or self.width(ops[0]) // 8
            addr, finish = self.mem_access(ops, 1)
            if mn.startswith("ld"):
                val = self.read(addr, nbytes)
                if signed and val & (1 << (8 * nbytes - 1)):
                    val -= 1 << (8 * nbytes)
                s(ops[0], val)
            else:
                self.write(addr, nbytes, g(ops[0]))
            finish()
        elif mn == "b":
            nxt = int(text.strip()[1:], 0)
        elif mn == "bl":
            self.x[30] = nxt
            nxt = int(text.strip()[1:], 0)
        elif mn == "br":
            nxt = g(ops[0])
        elif mn == "ret":
            nxt = self.x[30] if not text.strip() else g(ops[0])
        elif mn.startswith("b."):
            if self.cond(mn[2:]):
                nxt = int(text.strip()[1:], 0)
        elif mn in ("cbz", "cbnz"):
            if (g(ops[0]) == 0) == (mn == "cbz"):
                nxt = int(ops[1].strip()[1:], 0)
        elif mn in ("tbz", "tbnz"):
            if (((g(ops[0]) >> int(ops[1].strip()[1:], 0)) & 1) == 0) == (mn == "tbz"):
                nxt = int(ops[2].strip()[1:], 0)
        else:
            nxt = self._ext(mn, ops, text, nxt)
        if self.taint:
            self._taint_writes(i)
        self.pc = nxt & M64


    # --- instructions beyond the start code (needed by the C code that follows) -------------------------
    def _ext(self, mn, ops, text, nxt):
        g, s, v = self.get, self.set, self.val
        w = self.reg_width_or_64(ops[0]) if ops else 64
        mask = (1 << w) - 1
        if mn in ("stp", "ldp", "stnp", "ldnp"):
            mn = {"stnp": "stp", "ldnp": "ldp"}.get(mn, mn)
            n = self.width(ops[0]) // 8
            addr, finish = self.mem_access(ops, 2)
            if mn == "stp":
                self.write(addr, n, g(ops[0]))
                self.write(addr + n, n, g(ops[1]))
            else:
                a, b = self.read(addr, n), self.read(addr + n, n)
                s(ops[0], a)
                s(ops[1], b)
            finish()
        elif mn == "ldpsw":
            addr, finish = self.mem_access(ops, 2)
            for k, r in enumerate(ops[:2]):
                x = self.read(addr + 4 * k, 4)
                s(r, x - (1 << 32) if x & 0x80000000 else x)
            finish()
        elif mn in ("cset", "csetm"):
            s(ops[0], (mask if mn == "csetm" else 1) if self.cond(ops[1].strip()) else 0)
        elif mn in ("cinc", "cinv", "cneg"):
            a = g(ops[1])
            if self.cond(ops[2].strip()):
                a = {"cinc": a + 1, "cinv": ~a, "cneg": -a}[mn]
            s(ops[0], a)
        elif mn in ("csinc", "csinv", "csneg"):
            if self.cond(ops[3].strip()):
                s(ops[0], g(ops[1]))
            else:
                b = g(ops[2])
                s(ops[0], {"csinc": b + 1, "csinv": ~b, "csneg": -b}[mn])
        elif mn in ("ccmp", "ccmn"):
            a = g(ops[0])
            b = self.val(ops[1], w)
            nzcv = int(ops[2].strip()[1:], 0)
            if self.cond(ops[3].strip()):
                if mn == "ccmp":
                    self.sub_flags(a, b, w)
                else:
                    self.add_flags(a, b, w)
            else:
                self.n, self.z, self.c, self.v = (nzcv >> 3) & 1, (nzcv >> 2) & 1, (nzcv >> 1) & 1, nzcv & 1
        elif mn in ("tst", "ands", "bics"):
            if mn == "tst":
                ops = [("xzr" if w == 64 else "wzr")] + ops
            a = g(ops[1])
            b = self.shifted(ops, 2, w)
            if mn == "bics":
                b = ~b & mask
            r = a & b
            self.n, self.z, self.c, self.v = (r >> (w - 1)) & 1, int(r == 0), 0, 0
            s(ops[0], r)
        elif mn in ("cmn", "adds", "negs", "subs"):
            if mn == "cmn":
                ops = [("xzr" if w == 64 else "wzr")] + ops
            if mn == "negs":
                ops = [ops[0], "xzr" if w == 64 else "wzr"] + ops[1:]
                mn = "subs"
            a = g(ops[1])
            b = self.shifted(ops, 2, w)
            s(ops[0], self.add_flags(a, b, w) if mn in ("cmn", "adds") else self.sub_flags(a, b, w))
        elif mn in ("eor", "bic", "orn", "eon", "mvn", "neg", "mul", "mneg", "madd", "msub", "udiv", "sdiv",
                    "umulh", "smulh", "umull", "smull", "umaddl", "smaddl", "asr", "ror", "lslv", "lsrv", "asrv",
                    "rorv", "rev", "clz", "rbit", "extr"):
            self._alu(mn, ops, w, mask)
        elif mn in ("sxtw", "uxtw", "sxtb", "uxtb", "sxth", "uxth"):
            bits = {"w": 32, "b": 8, "h": 16}[mn[-1]]
            x = g(ops[1]) & ((1 << bits) - 1)
            if mn[0] == "s" and x & (1 << (bits - 1)):
                x -= 1 << bits
            s(ops[0], x)
        elif mn in ("ubfx", "sbfx", "ubfiz", "sbfiz", "bfi", "bfxil", "bfc", "ubfm", "sbfm", "bfm"):
            self._bitfield(mn, ops, w, mask)
        elif mn == "adr":
            s(ops[0], int(ops[1].strip()[1:], 0))
        elif mn == "blr":
            self.x[30] = nxt
            nxt = g(ops[0])
        elif mn in ("ldxr", "ldaxr", "ldar", "ldapr", "ldaprb", "ldarb", "ldxrb", "ldaxrb"):
            nb = 1 if mn.endswith("b") else self.width(ops[0]) // 8
            addr, _ = self.mem_access(ops, 1)
            s(ops[0], self.read(addr, nb))
        elif mn in ("stxr", "stlxr", "stxrb", "stlxrb"):
            nb = 1 if mn.endswith("b") else self.width(ops[1]) // 8
            addr, _ = self.mem_access(ops, 2)
            self.write(addr, nb, g(ops[1]))
            s(ops[0], 0)                                    # exclusives always succeed (one core)
        elif mn in ("stlr", "stlrb", "stlrh"):
            nb = 1 if mn.endswith("b") else 2 if mn.endswith("h") else self.width(ops[0]) // 8
            addr, _ = self.mem_access(ops, 1)
            self.write(addr, nb, g(ops[0]))
        elif mn == "dc" and ops[0].strip() == "zva":
            a = g(ops[1]) & ~63                               # DCZID_EL0 = 4: 64-byte blocks
            for k in range(0, 64, 8):
                self.write(a + k, 8, 0)
        elif mn in ("dc", "dmb", "wfe", "sev", "sevl", "yield", "hint", "prfm", "prfum", "clrex", "pacibsp",
                    "autibsp", "paciasp", "autiasp", "bti"):
            pass
        else:
            raise SimFault("unsupported", self.pc, self.pc, "%s %s" % (mn, text))
        return nxt

    def add_flags(self, a, b, width):
        m = (1 << width) - 1
        res = (a + b) & m
        sb = 1 << (width - 1)
        self.n, self.z, self.c = (1 if res & sb else 0), (1 if res == 0 else 0), (1 if a + b > m else 0)
        self.v = 1 if (~(a ^ b)) & (a ^ res) & sb else 0
        return res

    def _alu(self, mn, ops, w, mask):
        g, s = self.get, self.set
        a = g(ops[1]) if len(ops) > 1 else 0
        signed = lambda x, bits=w: x - (1 << bits) if x & (1 << (bits - 1)) else x
        if mn in ("eor", "bic", "orn", "eon"):
            b = self.shifted(ops, 2, w)
            r = {"eor": a ^ b, "bic": a & ~b, "orn": a | ~b, "eon": a ^ ~b}[mn]
        elif mn == "mvn":
            r = ~self.shifted(ops, 1, w)
        elif mn == "neg":
            r = -self.shifted(ops, 1, w)
        elif mn in ("mul", "mneg"):
            r = a * g(ops[2])
            r = -r if mn == "mneg" else r
        elif mn in ("madd", "msub"):
            r = (g(ops[3]) + a * g(ops[2])) if mn == "madd" else (g(ops[3]) - a * g(ops[2]))
        elif mn in ("umull", "smull"):
            x, y = a & 0xFFFFFFFF, g(ops[2]) & 0xFFFFFFFF
            r = (signed(x, 32) * signed(y, 32)) if mn == "smull" else x * y
        elif mn in ("umaddl", "smaddl"):
            x, y = a & 0xFFFFFFFF, g(ops[2]) & 0xFFFFFFFF
            r = g(ops[3]) + ((signed(x, 32) * signed(y, 32)) if mn == "smaddl" else x * y)
        elif mn == "umulh":
            r = (a * g(ops[2])) >> 64
        elif mn == "smulh":
            r = (signed(a, 64) * signed(g(ops[2]), 64)) >> 64
        elif mn in ("udiv", "sdiv"):
            b = g(ops[2])
            if b == 0:
                r = 0
            elif mn == "udiv":
                r = a // b
            else:
                q = abs(signed(a)) // abs(signed(b))
                r = q if (signed(a) < 0) == (signed(b) < 0) else -q
        elif mn in ("asr", "ror", "lslv", "lsrv", "asrv", "rorv"):
            b = (int(ops[2].strip()[1:], 0) if ops[2].strip().startswith("#") else g(ops[2])) % w
            if mn in ("asr", "asrv"):
                r = signed(a) >> b
            elif mn in ("ror", "rorv"):
                r = (a >> b) | (a << (w - b))
            elif mn == "lslv":
                r = a << b
            else:
                r = a >> b
        elif mn == "rev":
            r = int.from_bytes(a.to_bytes(w // 8, "little"), "big")
        elif mn == "clz":
            r = w - a.bit_length()
        elif mn == "rbit":
            r = int(format(a, "0%db" % w)[::-1], 2)
        elif mn == "extr":
            lsb = int(ops[3].strip()[1:], 0)
            r = (((a << w) | g(ops[2])) >> lsb) & mask
        s(ops[0], r)

    def _bitfield(self, mn, ops, w, mask):
        g, s = self.get, self.set
        if mn in ("ubfx", "sbfx"):
            lsb, width = int(ops[2].strip()[1:], 0), int(ops[3].strip()[1:], 0)
            x = (g(ops[1]) >> lsb) & ((1 << width) - 1)
            if mn == "sbfx" and x & (1 << (width - 1)):
                x -= 1 << width
            s(ops[0], x)
        elif mn in ("ubfiz", "sbfiz"):
            lsb, width = int(ops[2].strip()[1:], 0), int(ops[3].strip()[1:], 0)
            x = g(ops[1]) & ((1 << width) - 1)
            if mn == "sbfiz" and x & (1 << (width - 1)):
                x -= 1 << width
            s(ops[0], x << lsb)
        elif mn in ("bfi", "bfxil", "bfc"):
            if mn == "bfc":
                lsb, width = int(ops[1].strip()[1:], 0), int(ops[2].strip()[1:], 0)
                s(ops[0], g(ops[0]) & ~(((1 << width) - 1) << lsb))
            else:
                lsb, width = int(ops[2].strip()[1:], 0), int(ops[3].strip()[1:], 0)
                src, dst = g(ops[1]), g(ops[0])
                if mn == "bfi":
                    s(ops[0], (dst & ~(((1 << width) - 1) << lsb)) | ((src & ((1 << width) - 1)) << lsb))
                else:
                    s(ops[0], (dst & ~((1 << width) - 1)) | ((src >> lsb) & ((1 << width) - 1)))
        else:
            raise SimFault("unsupported", self.pc, self.pc, "%s %s" % (mn, ", ".join(ops)))

    # --- what a loader / return stub does -------------------------------------------------------------
    def pa_of_kva(self, va):
        """Physical address of a static kernel-image VA for this window (what the loader computes)."""
        return self.base + (va - self.p.virt_base)

    def fill_slot(self, slot_va, stub_pa, ckpt, pa_minus_va):
        """The loader's stores into _loader_stub_slot (MMU off, physical): [1] stub PA, [2] checkpoint,
        [3] PA minus VA. [0] keeps the kernel's own magic."""
        self.write_pa(self.pa_of_kva(slot_va) + 8, struct.pack("<QQQ", stub_pa, ckpt, pa_minus_va & M64))

    def stop_state(self):
        return dict(pc=self.pc, x0=self.x[0], x1=self.x[1], x2=self.x[2], x3=self.x[3],
                    sctlr=self.sr["sctlr_el1"], mmu_on=bool(self.mmu_on()), daif_masked=self.daif_masked,
                    steps=self.steps)

    def resume_asm(self, site_va, slot_va, next_ckpt, junk):
        """What a resuming return stub would do after an assembly-checkpoint stop at `site_va`: clobber
        (and taint) the registers the stop path used, restore the SCTLR_EL1 value the kernel had before the
        stop path's write, set the next checkpoint number in slot[2], continue at the not-taken target of
        the site's `b.ne` (site + 15 instructions). Nothing here is read back from the stub's own state."""
        for r in (0, 1, 2, 3, 9, 10, 11):
            self.x[r] = junk
            self.taint[r] = {0, 1, 2, 3}
        self.sr["sctlr_el1"] = self.sctlr_hist[-2]
        self.write_pa(self.pa_of_kva(slot_va) + 16, struct.pack("<Q", next_ckpt))
        self.pc = self.pa_of_kva(site_va) + 15 * 4


def load_analysis(path):
    with open(path) as f:
        d = json.load(f)
    return dict(slot_va=int(d["slot"]["va"], 16), sites={c["checkpoint"]: int(c["va"], 16) for c in d["asm_checkpoints"]})


def main():
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--payload", default="artifacts/nat-020/build-003/payload.bin")
    ap_.add_argument("--kernel", default="artifacts/nat-020/build-003/kernel.no-storage")
    ap_.add_argument("--window-base", type=lambda s: int(s, 0), default=0x9de400000)
    ap_.add_argument("--window-size", type=lambda s: int(s, 0), default=0x20000000)
    a = ap_.parse_args()
    arm_init = ap.macho_symbols(a.kernel)["_arm_init"]
    sim = Sim(a.payload, a.window_base, a.window_size)
    sim.run(stop_pcs=[arm_init])
    print(json.dumps({k: hex(v) if isinstance(v, int) and not isinstance(v, bool) else v
                      for k, v in sim.stop_state().items()}, indent=1))


if __name__ == "__main__":
    main()
