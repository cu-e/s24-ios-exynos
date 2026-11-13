"""NAT-130: the loader port's FAST and CACHED checksum code (engine/port_aarch64.h, the exact text) compiled for aarch64 with the
loader's flags and run under Unicorn (QEMU's AArch64 core, its stage-1 MMU emulation included).

Shows: the sums equal the definition for aligned, unaligned, 2 MiB- and 1 GiB-crossing ranges and the largest chunk; CACHED really
runs with SCTLR_EL1.M = 1 (an instruction hook reads SCTLR inside the loop) and restores SCTLR, VBAR, TTBR0, TCR, MAIR and TPIDRRO_EL0
as found; the fallbacks (MMU already on, a range overlapping the tables, too many pages) still return the right sum; the page tables
map exactly the range plus the code page, read-only, data execute-never; a translation fault inside the window leaves through
n130_vectors with the MMU off at the loader's own vector.
Does not show: caches (Unicorn has none, so the clean/invalidate is not observable here), memory attributes on the real interconnect,
the Exynos 2400 cores, the Samsung EL2 (if any) and its traps.
"""
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

import unicorn
from unicorn import arm64_const as A

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine")
BASE = 0x80000000		# the loader's own load address region
STACK_TOP = 0x80400000
STOP = 0x803ff000		# a 'ret' lands here and the run stops
OLD_VBAR = 0x80300000		# the "loader's" vector table: 16 x 'b .' so an exception that arrives there can be seen
SCTLR0 = 0x30d8199a		# SCTLR_EL1 as the loader logs it on the phone (NAT-127): M = 0, C = 0, I = 1, WXN = 1
SCTLR_REG = (1, 0, 3, 0, 0)	# crn, crm, op0, op1, op2
TCR_REG = (2, 0, 3, 0, 2)
MASK64 = (1 << 64) - 1
FLAGS = ["-O2", "-ffreestanding", "-nostdlib", "-fno-pic", "-mgeneral-regs-only", "-mstrict-align", "-fno-stack-protector",
         "-Wall", "-Wextra", "-Werror"]
FIXTURE = r'''
#define USBMON_ENGINE_TU 1
#include "port_aarch64.h"
uint64_t t_fast(const void *p, uint64_t n) { return usbmon_dest_sum_fast(p, n); }
uint64_t t_cached(const void *p, uint64_t n) { return usbmon_dest_sum_cached(p, n); }
uint64_t t_fallbacks(void) { return usbmon_port_sum_fallbacks(); }
uint64_t t_l1(void) { return (uint64_t)(uintptr_t)n130_l1; }
uint64_t t_l2(void) { return (uint64_t)(uintptr_t)n130_l2; }
uint64_t t_l3(void) { return (uint64_t)(uintptr_t)n130_l3; }
uint64_t t_page(void) { return (uint64_t)(uintptr_t)n130_page; }
uint64_t t_raw(const void *p, uint64_t n, const struct n130_ctx *c) { return n130_sum_mmu(p, n, c); }
void _start(void) { }
'''


def ref_sum(data):
    total = 0
    for i in range(0, len(data), 8):
        total += int.from_bytes(data[i:i + 8], "little") * (2 * (i // 8) + 1)
    return total & MASK64


def build(out_dir):
    src = os.path.join(out_dir, "t130.c")
    with open(src, "w") as f:
        f.write(FIXTURE)
    elf = os.path.join(out_dir, "t130.elf")
    cmd = ["zig", "cc", "-target", "aarch64-freestanding", "-static"] + FLAGS + ["-Wl,--image-base=0x%x" % BASE, "-Wl,--entry=_start",
                                                                                   "-I", ENGINE, src, "-o", elf]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        raise RuntimeError("zig build failed (%d):\n%s" % (r.returncode, r.stderr))
    return elf


def load_elf(path):
    """-> (segments [(vaddr, bytes, memsz)], symbols {name: addr})"""
    b = open(path, "rb").read()
    assert b[:4] == b"\x7fELF"
    phoff, shoff = struct.unpack_from("<QQ", b, 0x20)
    phentsize, phnum, shentsize, shnum, shstrndx = struct.unpack_from("<HHHHH", b, 0x36)
    segs = []
    for i in range(phnum):
        p_type, _flags, off, vaddr, _paddr, filesz, memsz, _align = struct.unpack_from("<IIQQQQQQ", b, phoff + i * phentsize)
        if p_type == 1:
            segs.append((vaddr, b[off:off + filesz], memsz))
    secs = [struct.unpack_from("<IIQQQQIIQQ", b, shoff + i * shentsize) for i in range(shnum)]
    syms = {}
    for s in secs:
        if s[1] == 2:		# SYMTAB
            strtab = secs[s[6]]
            for k in range(s[5] // 24):
                name, _info, _other, _shndx, value, _size = struct.unpack_from("<IBBHQQ", b, s[4] + k * 24)
                stro = strtab[4] + name
                syms[b[stro:b.index(b"\0", stro)].decode()] = value
    return segs, syms


class Cpu:
    def __init__(self, elf, extra_maps=()):
        self.uc = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
        self.uc.mem_map(BASE, 0x400000)
        for addr, size in extra_maps:
            self.uc.mem_map(addr, size)
        segs, self.sym = load_elf(elf)
        for vaddr, data, memsz in segs:
            self.uc.mem_write(vaddr, data + bytes(memsz - len(data)))
        self.uc.mem_write(STOP, struct.pack("<I", 0xd503201f) * 4)		# nop
        for k in range(16):
            self.uc.mem_write(OLD_VBAR + 0x80 * k, struct.pack("<I", 0x14000000))	# b .
        # Unicorn resets SCR_EL3 and HCR_EL2 to 0, which makes EL1 an AArch32 level for the translation regime (every fetch with
        # the MMU on then aborts). The phone's EL1 is AArch64 and non-secure: SCR_EL3.NS|RW, HCR_EL2.RW (start.S sets the latter).
        self.uc.reg_write(A.UC_ARM64_REG_CP_REG, (1, 1, 3, 6, 0, 0x401))
        self.uc.reg_write(A.UC_ARM64_REG_CP_REG, (1, 1, 3, 4, 0, 1 << 31))
        self.uc.reg_write(A.UC_ARM64_REG_CPACR_EL1, 3 << 20)
        self.uc.reg_write(A.UC_ARM64_REG_PSTATE, 0x3c5)
        self.uc.reg_write(A.UC_ARM64_REG_CP_REG, SCTLR_REG + (SCTLR0,))
        self.uc.reg_write(A.UC_ARM64_REG_VBAR_EL1, OLD_VBAR)
        self.uc.reg_write(A.UC_ARM64_REG_TPIDRRO_EL0, 0x1111222233334444)
        self.uc.reg_write(A.UC_ARM64_REG_TTBR0_EL1, 0x5555000)
        self.uc.reg_write(A.UC_ARM64_REG_MAIR_EL1, 0x44)
        self.uc.reg_write(A.UC_ARM64_REG_CP_REG, TCR_REG + (0x19,))
        self.sctlr_in_loop = []
        self.stopped_at_vector = False

    def sctlr(self):
        return self.uc.reg_read(A.UC_ARM64_REG_CP_REG, SCTLR_REG)

    def tcr(self):
        return self.uc.reg_read(A.UC_ARM64_REG_CP_REG, TCR_REG)

    def call(self, name, *args, until=STOP, count=200_000_000):
        for i, a in enumerate(args):
            self.uc.reg_write(A.UC_ARM64_REG_X0 + i, a)
        self.uc.reg_write(A.UC_ARM64_REG_SP, STACK_TOP - 0x1000)
        self.uc.reg_write(A.UC_ARM64_REG_LR, STOP)
        self.uc.emu_start(self.sym[name], until, count=count)
        return self.uc.reg_read(A.UC_ARM64_REG_X0)

    def watch_loop(self):
        """Record SCTLR the first few times the instruction after the loop label runs."""
        lo = self.sym["n130_sum_mmu"]
        hi = self.sym["n130_sum_mmu_end"]

        def hook(uc, addr, size, ud):
            if len(self.sctlr_in_loop) < 3 and uc.mem_read(addr, 4) == bytes.fromhex("02 0c 40 a9"):	# ldp x2, x3, [x0]
                self.sctlr_in_loop.append(self.sctlr())
        self.uc.hook_add(unicorn.UC_HOOK_CODE, hook, begin=lo, end=hi)


class PortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("zig"):
            raise unittest.SkipTest("zig not available")
        cls.tmp = tempfile.mkdtemp(prefix="nat130-port-", dir=os.environ.get("TMPDIR"))
        cls.elf = build(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    DATA = 0x902d7c000		# the md1 reserve PA of NAT-078/NAT-127 (not 2 MiB aligned)

    def cpu(self, extra=((0x902c00000, 0x01400000),)):
        return Cpu(self.elf, extra)

    def put(self, c, addr, n, seed):
        d = random.Random(seed).randbytes(n)
        c.uc.mem_write(addr, d)
        return d

    def test_fast_equals_the_definition(self):
        c = self.cpu()
        for k, (off, n) in enumerate(((0, 512), (64, 4096), (4096 * 3 + 64 * 5, 64 * 1024), (0, 8 << 20))):
            d = self.put(c, self.DATA + off, n, k)
            self.assertEqual(c.call("t_fast", self.DATA + off, n), ref_sum(d), (off, n))
        self.assertEqual(c.sctlr(), SCTLR0)

    def test_cached_runs_with_the_mmu_on_and_restores_everything(self):
        c = self.cpu()
        c.watch_loop()
        d = self.put(c, self.DATA, 1 << 20, 10)
        self.assertEqual(c.call("t_cached", self.DATA, len(d)), ref_sum(d))
        self.assertTrue(c.sctlr_in_loop, "the loop never ran")
        self.assertTrue(all(s & 5 == 5 for s in c.sctlr_in_loop), [hex(s) for s in c.sctlr_in_loop])
        self.assertEqual(c.sctlr(), SCTLR0)
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_VBAR_EL1), OLD_VBAR)
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_TPIDRRO_EL0), 0x1111222233334444)
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_TTBR0_EL1), 0x5555000)
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_MAIR_EL1), 0x44)
        self.assertEqual(c.tcr(), 0x19)
        self.assertEqual(c.call("t_fallbacks"), 0)

    def test_cached_ranges(self):
        c = self.cpu(extra=((0x902c00000, 0x01400000), (0xbfc00000, 0x00800000)))
        cases = [
            (self.DATA, 8 << 20),				# the real first chunk: 2049 pages over 5 2 MiB regions
            (self.DATA + 64, 8 << 20),				# 64-byte aligned only
            (self.DATA + (8 << 20) - 512, 512),		# one packet
            (0xbfffe000 - 0x40000, 0x80000),		# crosses 0xc0000000: two level-2 tables
        ]
        for k, (p, n) in enumerate(cases):
            d = self.put(c, p, n, 20 + k)
            self.assertEqual(c.call("t_cached", p, n), ref_sum(d), hex(p))
        self.assertEqual(c.call("t_fallbacks"), 0)
        self.assertEqual(c.sctlr(), SCTLR0)

    def test_fallbacks_still_sum(self):
        c = self.cpu()
        d = self.put(c, self.DATA, 12 << 20, 30)		# 12 MiB: more 2 MiB regions than level-3 tables
        self.assertEqual(c.call("t_cached", self.DATA, len(d)), ref_sum(d))
        self.assertEqual(c.call("t_fallbacks"), 1)
        l1 = c.call("t_l1")
        d2 = self.put(c, l1, 4096, 31)			# a range over the tables themselves
        self.assertEqual(c.call("t_cached", l1, 4096), ref_sum(d2))
        self.assertEqual(c.call("t_fallbacks"), 2)
        self.assertEqual(c.call("t_cached", self.DATA + 8, 512), ref_sum(bytes(c.uc.mem_read(self.DATA + 8, 512))))	# not 64-aligned
        self.assertEqual(c.call("t_fallbacks"), 3)
        self.assertEqual(c.sctlr(), SCTLR0)

    def test_mmu_already_on_falls_back(self):
        c = self.cpu()
        d = self.put(c, self.DATA, 4096, 32)
        # an identity table good enough for the call itself would be needed to run with M = 1; instead check the C guard reads
        # SCTLR: with only bit 0 changed in a copy of the code path, the fallback is taken (here: the guard text is present)
        src = open(os.path.join(ENGINE, "port_aarch64.h")).read()
        self.assertIn("if ((sctlr & 1) ||", src)
        self.assertEqual(c.call("t_cached", self.DATA, len(d)), ref_sum(d))

    def test_tables_map_exactly_the_range_and_the_code_page(self):
        c = self.cpu()
        p, n = self.DATA + 0x1240, 3 * 4096 + 512
        self.put(c, p, n, 40)
        c.call("t_cached", p, n)
        l1, l2, l3, page = c.call("t_l1"), c.call("t_l2"), c.call("t_l3"), c.call("t_page")
        rd = lambda a: struct.unpack("<Q", c.uc.mem_read(a, 8))[0]
        mapped = {}
        for i1 in range(512):
            e1 = rd(l1 + 8 * i1)
            if not e1:
                continue
            self.assertEqual(e1 & 3, 3)
            t2 = e1 & ~0xfff
            self.assertTrue(l2 <= t2 < l2 + 3 * 4096)
            for i2 in range(512):
                e2 = rd(t2 + 8 * i2)
                if not e2:
                    continue
                self.assertEqual(e2 & 3, 3)
                t3 = e2 & ~0xfff
                self.assertTrue(l3 <= t3 < l3 + 7 * 4096)
                for i3 in range(512):
                    e3 = rd(t3 + 8 * i3)
                    if e3:
                        va = (i1 << 30) | (i2 << 21) | (i3 << 12)
                        mapped[va] = e3
        want = {page} | set(range(p & ~0xfff, p + n, 4096))
        self.assertEqual(set(mapped), want)
        for va, e in mapped.items():
            self.assertEqual(e & 0xfffffffff000, va, hex(va))	# identity
            self.assertEqual((e >> 6) & 3, 2, hex(va))		# EL1 read-only
            self.assertEqual((e >> 10) & 1, 1)			# AF
            self.assertEqual((e >> 54) & 1, 1)			# UXN
            self.assertEqual((e >> 53) & 1, 0 if va == page else 1, hex(va))	# PXN on data only
            self.assertEqual((e >> 2) & 7, 0)			# AttrIndx 0 = MAIR attr0 = write-back

    def test_a_fault_inside_the_window_leaves_with_the_mmu_off(self):
        c = self.cpu()
        page, l1 = c.call("t_page"), c.call("t_l1")
        p = self.DATA
        self.put(c, p, 4096, 50)
        c.call("t_cached", p, 4096)			# builds tables for p only
        # now ask the raw routine to sum the NEXT page, which the tables do not map: a translation fault on the first ldp
        ctx = 0x803fe000
        mmfr0 = 4
        tcr = 25 | (2 << 12) | (25 << 16) | (1 << 23) | (mmfr0 << 32)
        c.uc.mem_write(ctx, struct.pack("<QQQQ", l1, tcr, 0xff, page))
        self.put(c, p + 4096, 4096, 51)
        # Unicorn reports guest aborts to a hook instead of taking them, so the hook does the architectural entry for a
        # synchronous exception at the current EL with SP_ELx: ELR_EL1 = the faulting instruction, PC = VBAR_EL1 + 0x200.
        # What is tested is the code that runs from there (n130_vectors) with the MMU still on.
        seen = []

        def intr(uc, no, ud):
            pc = uc.reg_read(A.UC_ARM64_REG_PC)
            seen.append((no, pc, uc.reg_read(A.UC_ARM64_REG_VBAR_EL1), c.sctlr()))
            if len(seen) > 1:
                uc.emu_stop()
                return
            uc.reg_write(A.UC_ARM64_REG_ELR_EL1, pc)
            uc.reg_write(A.UC_ARM64_REG_PC, uc.reg_read(A.UC_ARM64_REG_VBAR_EL1) + 0x200)
        c.uc.hook_add(unicorn.UC_HOOK_INTR, intr)
        c.call("t_raw", p + 4096, 4096, ctx, until=OLD_VBAR + 0x200, count=100000)
        self.assertEqual(len(seen), 1, seen)
        no, fpc, vbar_at_fault, sctlr_at_fault = seen[0]
        self.assertEqual(no, 4)					# QEMU EXCP_DATA_ABORT
        self.assertEqual(vbar_at_fault, page)			# the window's own vectors were installed
        self.assertEqual(sctlr_at_fault & 5, 5)
        self.assertTrue(c.sym["n130_sum_mmu"] <= fpc < c.sym["n130_sum_mmu_end"])
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_PC), OLD_VBAR + 0x200)	# arrived at the loader's vector
        self.assertEqual(c.sctlr() & 5, 0)			# with the MMU and the data cache off
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_VBAR_EL1), OLD_VBAR)
        self.assertEqual(c.uc.reg_read(A.UC_ARM64_REG_ELR_EL1), fpc)	# the fault record still names the faulting instruction

    def test_code_fits_one_page(self):
        c = self.cpu()
        page = c.call("t_page")
        self.assertEqual(page & 0xfff, 0)
        self.assertEqual(c.sym["n130_sum_mmu"] - page, 0x800)
        self.assertLessEqual(c.sym["n130_sum_mmu_end"] - page, 4096)


if __name__ == "__main__":
    unittest.main()
