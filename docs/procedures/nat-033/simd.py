#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-033: the SIMD/FP instruction forms the payload kernel executes between C checkpoints 10 and 11, as a subclass
of the NAT-030 interpreter (the NAT-030 files are unchanged).

Only the forms found in the direct-call closure of cpu_data_init and PE_init_platform (see test_nat033.py, which
re-derives the list from the payload bytes and checks every form against Unicorn on random inputs) are implemented.
Anything else with a vector/FP register operand raises SimFault("unsupported") exactly like the base class.
What this is not: a floating-point unit (no FP arithmetic is on the path), FPCR/FPSR, or a trap model for
CPACR_EL1.FPEN (the NAT-030 model does not model exceptions at all).

Vector registers are 128-bit Python ints. A write to a 64-bit arrangement or to a scalar b/h/s/d register zeroes
the rest of the register, as the architecture does.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


a5 = _load("nat032_after5", ROOT / "docs/procedures/nat-032/after5.py")
ks = a5.ks
SimFault = ks.SimFault
M128 = (1 << 128) - 1
ELEM = {"b": 8, "h": 16, "s": 32, "d": 64}
VTOK = re.compile(r"^([vqdsbh])(\d+)(?:\.(\d+)([bhsd]))?$")


def vtok(tok):
    """'v3.16b' -> (3, 16 lanes, 8 bits); 'q3' -> (3, None, 128); 'd3' -> (3, None, 64); None if not a vector token."""
    m = VTOK.match(tok.strip())
    if not m:
        return None
    kind, n, lanes, el = m.groups()
    if kind == "v":
        return int(n), int(lanes), ELEM[el]
    return int(n), None, 128 if kind == "q" else ELEM[kind]


def is_simd(ops):
    return any(vtok(o) is not None for o in ops if not o.strip().startswith(("[", "#")))


def lanes_of(val, nlanes, bits):
    m = (1 << bits) - 1
    return [(val >> (bits * i)) & m for i in range(nlanes)]


def join(lanes, bits):
    out = 0
    for i, x in enumerate(lanes):
        out |= (x & ((1 << bits) - 1)) << (bits * i)
    return out


class SimdSim(a5.Tracing):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.vr = [0] * 32
        self.simd_executed = []            # (pc, mnemonic, word) in order: which vector instructions really ran
        # (pc, va, size, MAIR byte of the page or None with the MMU off): every access that is not naturally aligned
        self.unaligned = []

    # --- vector memory ------------------------------------------------------------------------------------
    def _vread(self, va, n):
        out = bytearray()
        while len(out) < n:
            k = min(n - len(out), 0x1000 - ((va + len(out)) & 0xFFF))
            out += self.read_pa(self.translate(va + len(out), "r"), k)
        return int.from_bytes(out, "little")

    def _vwrite(self, va, n, val):
        data = (val & ((1 << (8 * n)) - 1)).to_bytes(n, "little")
        i = 0
        while i < n:
            k = min(n - i, 0x1000 - ((va + i) & 0xFFF))
            self.write_pa(self.translate(va + i, "w"), data[i:i + k])
            i += k

    def read(self, va, n):
        """With the MMU on the kernel maps RAM as Normal memory (MAIR attribute 0 = 0xff, SCTLR_EL1.A = 0), where a
        non-element-aligned load or store is legal; the base class' strict check models the MMU-off Device accesses
        of the start code. Unaligned accesses are recorded, not hidden."""
        if self.mmu_on() and va % n:
            self.unaligned.append((self.pc, va, n, self.attr_of(va)[1]))
            return self._vread(va, n)
        return super().read(va, n)

    def write(self, va, n, val):
        if self.mmu_on() and va % n:
            self.unaligned.append((self.pc, va, n, self.attr_of(va)[1]))
            return self._vwrite(va, n, val)
        return super().write(va, n, val)

    def attr_of(self, va):
        """(AttrIndx, MAIR byte) of the leaf descriptor that maps `va` right now (diagnostic: the base class' walker
        returns only the PA). MAIR byte 0xff/0x44/0x4f... is Normal memory, 0x00/0x04/0x08/0x0c is Device."""
        tcr = self.sr.get("tcr_el1", 0)
        region = 1 if va >> 63 else 0
        sz = (tcr >> 16) & 63 if region else tcr & 63
        table = self.sr.get("ttbr1_el1" if region else "ttbr0_el1", 0) & 0xFFFFFFFFF000
        for level, shift in ((1, 30), (2, 21), (3, 12)):
            nbits = (64 - sz - 30) if level == 1 else 9
            d = self.u64_pa(table + ((va >> shift) & ((1 << nbits) - 1)) * 8)
            if level < 3 and d & 2:
                table = d & 0xFFFFFFFFF000
                continue
            idx = (d >> 2) & 7
            return idx, (self.sr.get("mair_el1", 0) >> (8 * idx)) & 0xFF
        raise SimFault("translation-fault", va, self.pc, "no leaf")

    def _note_unaligned(self, va, size):
        if va % min(size, 8):
            self.unaligned.append((self.pc, va, size, self.attr_of(va)[1] if self.mmu_on() else None))

    # --- execution ----------------------------------------------------------------------------------------
    def step(self):
        ins = self.fetch()
        ops = self.split_ops(ins.op_str)
        if ins.mnemonic in ("b", "bl", "br", "blr", "ret", "cbz", "cbnz", "tbz", "tbnz") or not is_simd(ops):
            return super().step()
        mn = ins.mnemonic
        self.executed[mn] += 1
        if self.taint:
            self._taint_reads(ins)
        self.simd_executed.append((self.pc, mn, int.from_bytes(bytes(ins.bytes), "little")))
        self._simd(mn, ops, ins)
        if self.taint:
            self._taint_writes(ins)
        self.pc = (self.pc + 4) & ((1 << 64) - 1)

    def setv(self, tok, val, bits=None):
        n, lanes, b = vtok(tok)
        self.vr[n] = val & M128                       # scalar and 64-bit writes have a zero upper part by construction

    def _simd(self, mn, ops, ins):
        t0 = vtok(ops[0])
        if mn in ("ldr", "ldur", "str", "stur", "ldp", "stp"):
            return self._mem(mn, ops)
        if mn == "fmov":                                   # only the general <-> vector register moves are implemented
            if ops[0].strip()[0] in "xw":
                self.set(ops[0], self.vr[vtok(ops[1])[0]] & ((1 << self.width(ops[0])) - 1))
            elif ops[1].strip()[0] in "xw" and t0[1] is None:
                self.vr[t0[0]] = self.get(ops[1])
            else:
                raise SimFault("unsupported", self.pc, self.pc, "fmov %s" % ", ".join(ops))
            return
        n, lanes, bits = t0
        if mn == "movi":
            return self._movi(ops, t0)
        if mn == "dup" and ops[1].strip()[0] in "xw":    # from a general register (the element form is not implemented)
            src = self.get(ops[1]) & ((1 << bits) - 1)
            self.vr[n] = join([src] * lanes, bits)
            return
        if mn in ("orr", "and", "eor"):
            a, b = self.vr[vtok(ops[1])[0]], self.vr[vtok(ops[2])[0]]
            r = {"orr": a | b, "and": a & b, "eor": a ^ b}[mn]
            self.vr[n] = r & ((1 << (lanes * bits)) - 1)
            return
        if mn in ("add", "cmeq", "cmhi", "ushl") and vtok(ops[1]) and vtok(ops[2]) and vtok(ops[2])[1]:
            la = lanes_of(self.vr[vtok(ops[1])[0]], lanes, bits)
            lb = lanes_of(self.vr[vtok(ops[2])[0]], lanes, bits)
            full = (1 << bits) - 1
            if mn == "add":
                r = [(x + y) & full for x, y in zip(la, lb)]
            elif mn == "cmeq":
                r = [full if x == y else 0 for x, y in zip(la, lb)]
            elif mn == "cmhi":
                r = [full if x > y else 0 for x, y in zip(la, lb)]
            else:                                         # ushl: the signed low byte of each lane of the second source
                r = []
                for x, y in zip(la, lb):
                    sh = y & 0xFF
                    sh = sh - 256 if sh & 0x80 else sh
                    r.append((x << sh) & full if 0 <= sh < bits else (x >> -sh if -bits < sh < 0 else 0))
            self.vr[n] = join(r, bits)
            return
        if mn == "uminv":
            src = vtok(ops[1])
            self.vr[n] = min(lanes_of(self.vr[src[0]], src[1], src[2]))
            return
        raise SimFault("unsupported", self.pc, self.pc, "%s %s" % (mn, ", ".join(ops)))

    def _movi(self, ops, t0):
        n, lanes, bits = t0
        imm = int(ops[1].strip()[1:], 0)
        if len(ops) > 2:
            kind, amt = ops[2].split()[0], int(ops[2].split("#")[1], 0)
            if kind != "lsl":
                raise SimFault("unsupported", self.pc, self.pc, "movi %s" % ", ".join(ops))
            imm <<= amt
        if lanes is None:                                  # movi dN, #imm64
            self.vr[n] = imm & ((1 << 64) - 1)
        else:
            self.vr[n] = join([imm] * lanes, bits)

    def _mem(self, mn, ops):
        pair = mn in ("ldp", "stp")
        regs = [vtok(ops[0])] + ([vtok(ops[1])] if pair else [])
        size = regs[0][2] // 8
        addr, finish = self.mem_access(ops, 2 if pair else 1)
        for k, (rn, _, _) in enumerate(regs):
            a = addr + k * size
            self._note_unaligned(a, size)
            if mn.startswith("ld"):
                self.vr[rn] = self._vread(a, size)
            else:
                self._vwrite(a, size, self.vr[rn])
        finish()
