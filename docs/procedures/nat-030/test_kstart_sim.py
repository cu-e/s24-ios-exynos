#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-030 host checks for kstart_sim.py and for what the payload kernel's start code does with the
loader's boot_args and RAM window.

Run with a python that has capstone: `python3 -I docs/procedures/nat-030/test_kstart_sim.py`. Without
capstone every case skips (and says so). One extra case cross-checks the interpreter against Unicorn
(an independent CPU emulator) and skips without it. Needs the local artifacts/nat-020/build-003 payload
and Mach-O and artifacts/nat-029/payload-analysis.json (analyze_payload.py writes it).

These are host tests of a model: they show what the kernel's start bytes do to a faithfully built
boot_args and window, not that the S24 behaves the same.
"""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kstart_sim as ks  # noqa: E402

ap = ks.ap
PAYLOAD = str(ROOT / "artifacts/nat-020/build-003/payload.bin")
KERNEL = str(ROOT / "artifacts/nat-020/build-003/kernel.no-storage")
ANALYSIS = ROOT / "artifacts/nat-029/payload-analysis.json"
LOADER_C = ROOT / "artifacts/e1s-build/nat006-loader-001/source/shim/e1s-xnu/loader.c"
BASE = 0x9de400000           # measured window base, native run 007 (decision 0015)
SIZE = 0x20000000
HI = 0xffffffc000000000      # first address of the TTBR1 region for T1SZ 26
HAVE = ks.capstone is not None
try:
    import unicorn
except ImportError:  # pragma: no cover
    unicorn = None

needs_capstone = unittest.skipUnless(HAVE, "capstone not installed")


def cfg():
    return ks.load_analysis(str(ANALYSIS))


def arm_init_va():
    return ap.macho_symbols(KERNEL)["_arm_init"]


def new_sim(**kw):
    return ks.Sim(PAYLOAD, kw.pop("base", BASE), kw.pop("size", SIZE), **kw)


def mapping_errors(sim):
    """Loader truth: kernel VA -> PA = window base + (VA - virt_base); the low map is the identity over
    the same physical range. Checked on the descriptors (bootstrap_map) and through the walker."""
    errs = []
    t1 = sim.bootstrap_map(sim.sr["ttbr1_el1"])
    t0 = sim.bootstrap_map(sim.sr["ttbr0_el1"])
    for a, b, pa, _ in t1:
        want = sim.base + (HI + a - sim.p.virt_base)
        if pa != want:
            errs.append("TTBR1 run %#x..%#x -> %#x, loader truth %#x" % (HI + a, HI + b, pa, want))
    for a, b, pa, _ in t0:
        if pa != a:
            errs.append("TTBR0 run %#x..%#x -> %#x is not the identity" % (a, b, pa))
    return errs


class Instructions(unittest.TestCase):
    """Single instructions, hand-encoded (ARM ARM) and checked against capstone's text so a wrong
    encoding cannot hide, executed on the interpreter and compared with hand-computed results."""

    def setUp(self):
        if not HAVE:
            self.skipTest("capstone not installed")
        self.s = new_sim()
        self.code = BASE + 0x4a00000

    def run1(self, word, text, **regs):
        got = list(self.s.md.disasm(struct.pack("<I", word), self.code))[0]
        self.assertEqual("%s %s" % (got.mnemonic, got.op_str), text)
        self.s.write_pa(self.code, struct.pack("<I", word))
        self.s.pc = self.code
        for k, v in regs.items():
            self.s.x[int(k[1:])] = v
        self.s.step()

    def test_mov_movk_add_sub(self):
        self.run1(0xD28000A0, "mov x0, #5")
        self.assertEqual(self.s.x[0], 5)
        self.run1(0xF2A24680, "movk x0, #0x1234, lsl #16")
        self.assertEqual(self.s.x[0], 0x12340005)
        self.run1(0x91000401, "add x1, x0, #1", x0=0xFFFFFFFFFFFFFFFF)
        self.assertEqual(self.s.x[1], 0)                      # 64-bit wrap
        self.run1(0xD1000841, "sub x1, x2, #2", x2=1)
        self.assertEqual(self.s.x[1], 0xFFFFFFFFFFFFFFFF)

    def test_compare_and_flags(self):
        self.run1(0xF100141F, "cmp x0, #5", x0=5)
        self.assertEqual((self.s.n, self.s.z, self.s.c, self.s.v), (0, 1, 1, 0))
        self.run1(0xF100141F, "cmp x0, #5", x0=4)
        self.assertEqual((self.s.n, self.s.z, self.s.c, self.s.v), (1, 0, 0, 0))
        self.run1(0xF100141F, "cmp x0, #5", x0=6)
        self.assertEqual((self.s.n, self.s.z, self.s.c, self.s.v), (0, 0, 1, 0))
        self.run1(0xF100141F, "cmp x0, #5", x0=0x8000000000000000)   # signed overflow
        self.assertEqual((self.s.n, self.s.z, self.s.c, self.s.v), (0, 0, 1, 1))

    def test_branches(self):
        self.s.n, self.s.z, self.s.c, self.s.v = 0, 0, 1, 0          # ne
        self.run1(0x54000041, "b.ne #0x%x" % (self.code + 8))
        self.assertEqual(self.s.pc, self.code + 8)
        self.s.z = 1
        self.run1(0x54000041, "b.ne #0x%x" % (self.code + 8))
        self.assertEqual(self.s.pc, self.code + 4)
        self.run1(0xB4000040, "cbz x0, #0x%x" % (self.code + 8), x0=0)
        self.assertEqual(self.s.pc, self.code + 8)
        self.run1(0xB4000040, "cbz x0, #0x%x" % (self.code + 8), x0=7)
        self.assertEqual(self.s.pc, self.code + 4)
        self.run1(0x36180040, "tbz w0, #3, #0x%x" % (self.code + 8), x0=0b0111)
        self.assertEqual(self.s.pc, self.code + 8)
        self.run1(0x36180040, "tbz w0, #3, #0x%x" % (self.code + 8), x0=0b1000)
        self.assertEqual(self.s.pc, self.code + 4)

    def test_memory_and_shifts(self):
        buf = BASE + 0x4a10000
        self.s.write_pa(buf + 16, struct.pack("<Q", 0x1122334455667788))
        self.run1(0xF9400843, "ldr x3, [x2, #0x10]", x2=buf)
        self.assertEqual(self.s.x[3], 0x1122334455667788)
        self.run1(0xF8008441, "str x1, [x2], #8", x1=0xA5A5, x2=buf + 32)
        self.assertEqual(self.s.u64_pa(buf + 32), 0xA5A5)
        self.assertEqual(self.s.x[2], buf + 40)                # post-index writeback
        self.run1(0xD37CEC01, "lsl x1, x0, #4", x0=0x10)
        self.assertEqual(self.s.x[1], 0x100)
        self.run1(0xD344FC01, "lsr x1, x0, #4", x0=0x100)
        self.assertEqual(self.s.x[1], 0x10)
        self.s.n, self.s.v = 1, 0                               # lt is true when N != V
        self.run1(0x9A82B020, "csel x0, x1, x2, lt", x1=11, x2=22)
        self.assertEqual(self.s.x[0], 11)
        self.s.n, self.s.v = 1, 1                               # lt is false
        self.run1(0x9A82B020, "csel x0, x1, x2, lt", x1=11, x2=22)
        self.assertEqual(self.s.x[0], 22)

    def test_unaligned_and_unknown(self):
        with self.assertRaises(ks.SimFault) as c:
            self.run1(0xF9400843, "ldr x3, [x2, #0x10]", x2=BASE + 0x4a10004)
        self.assertEqual(c.exception.kind, "alignment-fault")
        self.s.write_pa(self.code, struct.pack("<I", 0xD4000001))       # svc #0: not modelled, must not pass silently
        self.s.pc = self.code
        with self.assertRaises(ks.SimFault) as c:
            self.s.step()
        self.assertEqual(c.exception.kind, "unsupported")


class Walker(unittest.TestCase):
    """The table walker on hand-built tables, with hand-computed results."""

    def setUp(self):
        if not HAVE:
            self.skipTest("capstone not installed")
        self.s = new_sim()
        s = self.s
        self.t1 = BASE + 0x4a20000            # L1 (2 KiB used)
        self.l2 = BASE + 0x4a21000
        self.l3 = BASE + 0x4a22000
        s.sr.update(tcr_el1=26 | (26 << 16) | (2 << 30) | (2 << 32), ttbr0_el1=self.t1, ttbr1_el1=self.t1)
        s.sr["sctlr_el1"] |= 1
        s.write_pa(self.t1 + 5 * 8, struct.pack("<Q", self.l2 | 3))            # VA 0x140000000.. -> L2
        s.write_pa(self.l2 + 3 * 8, struct.pack("<Q", self.l3 | 3))            # 2 MiB window at +6 MiB -> L3
        s.write_pa(self.l3 + 7 * 8, struct.pack("<Q", (BASE + 0x4a30000) | 0x703))     # page, AF, SH
        s.write_pa(self.l2 + 4 * 8, struct.pack("<Q", (BASE + 0x400000) | 0x601))      # 2 MiB block at +8 MiB
        s.write_pa(self.l2 + 5 * 8, struct.pack("<Q", (BASE + 0x400000) | 0x681))      # block, read-only
        s.write_pa(self.l2 + 6 * 8, struct.pack("<Q", (BASE + 0x400000) | 0x201))      # block without AF

    def test_page_block_and_faults(self):
        s, v = self.s, 0x140000000
        self.assertEqual(s.translate(v + 0x600000 + 7 * 0x1000 + 0x123), BASE + 0x4a30123)   # level 3 page
        self.assertEqual(s.translate(v + 0x800000 + 0x1ABCDE), BASE + 0x400000 + 0x1ABCDE)   # level 2 block
        with self.assertRaises(ks.SimFault) as c:
            s.translate(v + 0xC00000 + 0x10)
        self.assertEqual(c.exception.kind, "access-flag-fault")
        with self.assertRaises(ks.SimFault) as c:
            s.translate(v + 0xA00000, "w")
        self.assertEqual(c.exception.kind, "permission-fault")
        self.assertEqual(s.translate(v + 0xA00000, "r"), BASE + 0x400000)
        with self.assertRaises(ks.SimFault) as c:
            s.translate(v + 0x1400000)
        self.assertEqual(c.exception.kind, "translation-fault")       # invalid descriptor
        with self.assertRaises(ks.SimFault) as c:
            s.translate(0x0000800000000000)                           # neither TTBR0 nor TTBR1 range
        self.assertEqual(c.exception.kind, "translation-fault")

    def test_ttbr1_region_and_ips(self):
        s = self.s
        va = HI + (5 << 30) + 0x800000 + 0x42
        self.assertEqual(s.translate(va), BASE + 0x400000 + 0x42)
        s.sr["tcr_el1"] = 26 | (26 << 16) | (2 << 30) | (0 << 32)         # IPS 32 bits: PA >= 4 GiB cannot be output
        with self.assertRaises(ks.SimFault) as c:
            s.translate(va)
        self.assertEqual(c.exception.kind, "address-size-fault")

    def test_mmu_off_is_identity(self):
        self.s.sr["sctlr_el1"] &= ~1
        self.assertEqual(self.s.translate(0x123456789), 0x123456789)


@needs_capstone
class Entry(unittest.TestCase):
    def test_boot_args_layout(self):
        s = new_sim()
        raw = s.read_pa(s.ba_pa, ks.BOOT_ARGS_SIZE)
        rev, ver = struct.unpack_from("<HH", raw, 0)
        virt, phys, mem, top = struct.unpack_from("<QQQQ", raw, 8)
        dt, dtlen = struct.unpack_from("<QI", raw, 96)
        (actual,) = struct.unpack_from("<Q", raw, 728)
        self.assertEqual((rev, ver, virt, phys, mem), (2, 2, s.p.virt_base, BASE, SIZE))
        self.assertEqual(top, s.ba_pa + 0x4000)
        self.assertEqual(dt, s.p.virt_base + (s.adt_pa - BASE))
        self.assertEqual(actual, SIZE)
        self.assertEqual(s.ba_pa, BASE + 0x4978000)            # measured in run 007 (boot_args PA)
        self.assertEqual(s.pc, BASE + 0x343b4a8)               # measured in run 007 (kernel copy entry)
        self.assertEqual(s.x[0], s.ba_pa)

    @unittest.skipUnless(LOADER_C.exists(), "loader.c source not in artifacts/")
    def test_layout_matches_loader_source(self):
        src = LOADER_C.read_text()
        for frag in ('offsetof(struct boot_args, Video) == 40', 'offsetof(struct boot_args, CommandLine) == 108',
                     'sizeof(struct boot_args) == 736', "ba->topOfKernelData = ba_pa + PAGE_16K",
                     "ba->deviceTreeP = p->virt_base + (adt_pa - win_base)",
                     "uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1)"):
            self.assertIn(frag, src)
        # The loader aligns every window it picks to 2 MiB (base and size); the kernel needs that.
        gap = src[src.index("consider_gap(uint64_t start"):src.index("/* Preserve the existing payload reserve")]
        self.assertGreaterEqual(gap.count("0x1fffffUL"), 3)


@needs_capstone
class FallThrough(unittest.TestCase):
    """Slot never filled: the start code runs to `ret` into arm_init with the MMU on."""

    @classmethod
    def setUpClass(cls):
        cls.s = new_sim()
        cls.arm_init = arm_init_va()
        cls.s.run(stop_pcs=[cls.arm_init])

    def test_arrives_in_arm_init_with_boot_args_va(self):
        s = self.s
        self.assertEqual(s.pc, self.arm_init)
        self.assertEqual(s.x[0], s.p.virt_base + (s.ba_pa - BASE))      # arm_init's argument: boot_args VA
        self.assertTrue(s.mmu_on())
        sctlr = s.sr["sctlr_el1"]
        self.assertEqual(sctlr & (1 | 4 | 4096), 1 | 4 | 4096)          # M, C, I
        self.assertTrue(s.daif_masked)
        self.assertEqual(s.steps, 8202)

    def test_translation_control(self):
        s = self.s
        tcr = s.sr["tcr_el1"]
        self.assertEqual((tcr & 63, (tcr >> 16) & 63), (26, 26))
        self.assertEqual(((tcr >> 14) & 3, (tcr >> 30) & 3), (0, 2))      # 4 KiB granules
        self.assertEqual((tcr >> 32) & 7, 2)                              # IPS 40 bits: covers PA 0x9e1...
        self.assertLess(s.base + s.size, 1 << 40)
        self.assertEqual(s.sr["ttbr1_el1"], s.sr["ttbr0_el1"] + 0x1000)

    def test_bootstrap_map_matches_loader_truth(self):
        s = self.s
        self.assertEqual(mapping_errors(s), [])
        (a, b, pa, _), = s.bootstrap_map(s.sr["ttbr1_el1"])
        self.assertEqual((HI + a, HI + b, pa), (0xfffffff007000000, 0xfffffff023e00000, BASE + 0x3000000))
        (a0, b0, pa0, _), = s.bootstrap_map(s.sr["ttbr0_el1"])
        self.assertEqual((a0, b0, pa0), (BASE + 0x3000000, BASE + 0x1fe00000, BASE + 0x3000000))

    def test_everything_the_loader_placed_is_reachable_through_the_kernel_tables(self):
        s = self.s
        want = lambda va: BASE + (va - s.p.virt_base)
        for vm, vs, fo, fs in s.p.segs:
            for va in (vm, vm + vs - 1):
                self.assertEqual(s.translate(va), want(va), hex(va))
        ba_va = s.p.virt_base + (s.ba_pa - BASE)
        for va in (s.p.kernel_end, ba_va, ba_va + 0x3fff, s.boot_args["topOfKernelData"] - s.ba_pa + ba_va):
            self.assertEqual(s.translate(va), want(va), hex(va))
        for pa in (s.entry_pc, s.entry_pc + 0x1000, s.ba_pa):
            self.assertEqual(s.translate(pa), pa)                      # the low identity map covers the start code
        # the boot_args the kernel was handed reads back through the virtual address
        self.assertEqual(s.read(ba_va + 16, 8), BASE)
        self.assertEqual(s.read(ba_va + 8, 8), s.p.virt_base)

    def test_only_modelled_instructions_ran(self):
        self.assertEqual(self.s.violations, [])
        self.assertIn("msr", self.s.executed)
        self.assertGreater(sum(self.s.executed.values()), 8000)


@needs_capstone
class AsmCheckpoints(unittest.TestCase):
    """Slot filled by the loader: the start code stops at exactly checkpoint N and says so."""

    STUB = BASE + 0x4980000
    # System registers written (in order) before each checkpoint, read from the start code's order:
    # VBAR at 0x...e0bc (after 1, before 2), TPIDR*_EL0 at e124/e128, TCR/TTBR/MAIR/VBAR at e360-e400 (before 4).
    WRITTEN_BEFORE = {
        1: [],
        2: ["vbar_el1"],
        3: ["vbar_el1", "tpidrro_el0", "tpidr_el0"],
        4: ["vbar_el1", "tpidrro_el0", "tpidr_el0", "tcr_el1", "ttbr0_el1", "ttbr1_el1", "mair_el1", "vbar_el1"],
        5: ["vbar_el1", "tpidrro_el0", "tpidr_el0", "tcr_el1", "ttbr0_el1", "ttbr1_el1", "mair_el1", "vbar_el1"],
    }

    def stopped(self, n):
        c = cfg()
        s = new_sim()
        s.fill_slot(c["slot_va"], self.STUB, n, (BASE - s.p.virt_base) & ks.M64)
        s.run(stop_pcs=[self.STUB])
        return s, c

    def test_each_site_stops_with_the_documented_registers(self):
        for n in range(1, 6):
            with self.subTest(checkpoint=n):
                s, c = self.stopped(n)
                st = s.stop_state()
                self.assertEqual((st["x0"], st["x1"], st["x2"], st["x3"]), (0, 0, 2, n))
                self.assertFalse(st["mmu_on"])                     # the stop path leaves the MMU off
                self.assertTrue(st["daif_masked"])
                self.assertEqual(s.sr["sctlr_el1"] & 1, 0)
                # Reaching N proves the earlier straight-line code ran and the later code has not.
                written = [e[1] for e in s.events if e[1] not in ("sctlr_el1", "daifset")]
                self.assertEqual(written, self.WRITTEN_BEFORE[n])
                self.assertEqual(any(e[1] == "sctlr_el1" and e[2] & 1 for e in s.events), n == 5)
                l1_entry = s.u64_pa(BASE + 0x31ae000 + 39 * 8)          # bootstrap TTBR0 table (x25 area), L1[39]
                self.assertEqual(l1_entry != 0, n >= 3)                  # tables exist from checkpoint 3 on

    def test_stop_steps_increase_through_the_start_code(self):
        steps = [self.stopped(n)[0].steps for n in range(1, 6)]
        self.assertEqual(steps, sorted(steps))
        self.assertEqual(len(set(steps)), 5)
        self.assertLess(steps[0], 40)                              # checkpoint 1 is near the entry
        self.assertGreater(steps[2], 5000)                         # 3 is after the table zeroing/filling loops

    def test_stop_at_site_5_has_translation_state_of_the_mmu_enable(self):
        s, _ = self.stopped(5)
        self.assertEqual(s.sr["sctlr_el1"] | 1, 0x3454593d)
        self.assertEqual(mapping_errors(s), [])

    def test_slot_untouched_by_the_kernel(self):
        c = cfg()
        for n in range(1, 6):
            s, _ = self.stopped(n)
            slot = s.read_pa(s.pa_of_kva(c["slot_va"]), 32)
            self.assertEqual(slot[:8], b"XNULDRST")
            self.assertEqual(struct.unpack_from("<QQQ", slot, 8), (self.STUB, n, (BASE - s.p.virt_base) & ks.M64))


@needs_capstone
class ResumeChain(unittest.TestCase):
    """The idea from NAT-029: stop at 1..5 in one run, resume each time. The model shows it is possible
    in the executed path (nothing after a site reads x0-x3/x9-x11 before writing them)."""

    STUB = BASE + 0x4980000

    @classmethod
    def setUpClass(cls):
        c = cfg()
        cls.arm = arm_init_va()
        s = new_sim()
        s.fill_slot(c["slot_va"], cls.STUB, 1, (BASE - s.p.virt_base) & ks.M64)
        cls.records = []
        for n in range(1, 6):
            s.run(stop_pcs=[cls.STUB])
            cls.records.append(s.stop_state())
            s.resume_asm(c["sites"][n], c["slot_va"], n + 1 if n < 5 else 0, 0xDEAD0000BEEF0000 + n)
        s.run(stop_pcs=[cls.arm])
        cls.s = s
        cls.ref = new_sim()
        cls.ref.run(stop_pcs=[cls.arm])

    def test_five_stops_in_order(self):
        self.assertEqual([r["x3"] for r in self.records], [1, 2, 3, 4, 5])
        self.assertEqual([r["mmu_on"] for r in self.records], [False] * 5)

    def test_no_read_of_a_clobbered_register_before_it_is_rewritten(self):
        self.assertEqual(self.s.violations, [])

    def test_same_kernel_state_as_the_uninterrupted_run(self):
        s, r = self.s, self.ref
        self.assertEqual(s.pc, r.pc)
        for i in (0, *range(4, 9), *range(12, 31)):                    # the rest are scratch for arm_init
            self.assertEqual(s.x[i], r.x[i], "x%d" % i)
        self.assertEqual((s.sp_el, s.spsel, s.sr), (r.sp_el, r.spsel, r.sr))
        self.assertEqual(self.snapshot(s), self.snapshot(r))

    @staticmethod
    def snapshot(s):
        slot_pa = s.pa_of_kva(cfg()["slot_va"])
        out = {}
        for pa, pg in s.pages.items():
            b = bytes(pg)
            if pa == slot_pa & ~(ks.PAGE - 1):    # slot words [1]-[3] are the loader's, not the kernel's
                o = slot_pa & (ks.PAGE - 1)
                b = b[:o + 8] + b"\0" * 24 + b[o + 32:]
            if any(b):
                out[pa] = b
        return out


@needs_capstone
class NegativeControls(unittest.TestCase):
    """The checks must be able to fail: wrong inputs are detected, not silently accepted."""

    arm = None

    @classmethod
    def setUpClass(cls):
        cls.arm = arm_init_va()

    def test_wrong_x0_faults(self):
        for x0 in (0, 0xfffffff008978000):                 # NULL, and the boot_args VA (the MMU is off at entry)
            with self.subTest(x0=hex(x0)):
                with self.assertRaises(ks.SimFault):
                    new_sim(x0=x0).run(stop_pcs=[self.arm])

    def test_wrong_phys_base_in_boot_args_never_reaches_arm_init(self):
        s = new_sim(ba_overrides=dict(physBase=BASE + 0x200000))
        self.assertNotEqual(s.run_until_high_pc(), self.arm)    # the `ret` goes to a wrong VA
        ok = new_sim()
        self.assertEqual(ok.run_until_high_pc(), self.arm)      # and the control: the right boot_args arrive

    def test_wrong_virt_base_never_reaches_arm_init(self):
        s = new_sim(ba_overrides=dict(virtBase=0xfffffff005000000))
        self.assertNotEqual(s.run_until_high_pc(), self.arm)

    def test_misaligned_window_base_is_detected_by_the_mapping_check(self):
        """A base that is not 2 MiB aligned: the bootstrap rounds the 2 MiB blocks, so every kernel VA
        resolves 16 KiB away from where the loader put its bytes. The loader aligns (consider_gap)."""
        s = new_sim(base=0x9dd3fc000)
        s.run(stop_pcs=[self.arm])
        errs = mapping_errors(s)
        self.assertTrue(errs)
        self.assertIn("loader truth", errs[0])
        # and the same check is clean for the aligned base the loader would pick
        ok = new_sim(base=0x9dd400000)
        ok.run(stop_pcs=[self.arm])
        self.assertEqual(mapping_errors(ok), [])

    def test_pc_stop_guard_catches_wrong_slot_stub(self):
        """A slot whose stub PA lies outside RAM would fetch from nowhere: the model raises."""
        s = new_sim()
        s.fill_slot(cfg()["slot_va"], BASE + SIZE + 0x1000, 1, (BASE - s.p.virt_base) & ks.M64)
        with self.assertRaises(ks.SimFault) as c:
            s.run(stop_pcs=[0])
        self.assertEqual(c.exception.kind, "external-abort")

    def test_slot_not_used_when_ckpt_is_zero(self):
        s = new_sim()
        s.fill_slot(cfg()["slot_va"], BASE + 0x4980000, 0, (BASE - s.p.virt_base) & ks.M64)
        s.run(stop_pcs=[self.arm])
        self.assertEqual(s.pc, self.arm)


@needs_capstone
class WindowVariants(unittest.TestCase):
    """The start code works for the windows the loader can choose (2 MiB-aligned base and size)."""

    def test_variants(self):
        arm = arm_init_va()
        for base, size in ((0x9de400000, 0x20000000), (0x9dd400000, 0x20000000), (0x9de400000, 0x10000000),
                           (0x80000000, 0x20000000)):
            with self.subTest(base=hex(base), size=hex(size)):
                s = new_sim(base=base, size=size)
                s.run(stop_pcs=[arm])
                self.assertEqual(s.x[0], s.p.virt_base + (s.ba_pa - base))
                self.assertEqual(mapping_errors(s), [])


@unittest.skipUnless(HAVE and unicorn is not None, "capstone and unicorn are both needed")
class UnicornCrossCheck(unittest.TestCase):
    """Run the same bytes in Unicorn (an independent CPU model) up to, not including, the instruction
    that turns the MMU on. Registers, flags and the whole window must match the interpreter's. (Unicorn
    takes a prefetch abort right after the MMU enable on this setup, so the post-MMU part is not compared;
    the walker is tested above instead.)"""

    def test_state_identical_before_mmu_enable(self):
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
        from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X29, UC_ARM64_REG_X30, UC_ARM64_REG_SP, UC_ARM64_REG_NZCV
        probe = new_sim()
        probe.run(stop_pcs=[arm_init_va()])
        stop = next(e[3] for e in probe.events if e[1] == "sctlr_el1" and e[2] & 1)
        s = new_sim()
        s.run(stop_pcs=[stop])
        ref = new_sim()
        uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.mem_map(BASE, SIZE)
        for vm, vs, fo, fs in ref.p.segs:
            uc.mem_write(BASE + (vm - ref.p.virt_base), ref.p.b[fo:fo + fs])
        uc.mem_write(ref.ba_pa, ref.read_pa(ref.ba_pa, ks.BOOT_ARGS_SIZE))
        uc.reg_write(UC_ARM64_REG_X0, ref.ba_pa)
        count = [0]
        uc.hook_add(UC_HOOK_CODE, lambda *a: count.__setitem__(0, count[0] + 1))
        uc.emu_start(ref.pc, stop, count=100000)
        self.assertEqual(count[0], s.steps)
        regs = [uc.reg_read(UC_ARM64_REG_X0 + i) for i in range(29)] + [uc.reg_read(UC_ARM64_REG_X29),
                                                                       uc.reg_read(UC_ARM64_REG_X30)]
        self.assertEqual(regs, s.x)
        self.assertEqual(uc.reg_read(UC_ARM64_REG_SP), s.sp_el[s.spsel])
        self.assertEqual(uc.reg_read(UC_ARM64_REG_NZCV) >> 28, s.n << 3 | s.z << 2 | s.c << 1 | s.v)
        for off in range(0, SIZE, 0x100000):
            want = b"".join(bytes(s.pages.get(BASE + off + j, bytes(ks.PAGE))) for j in range(0, 0x100000, ks.PAGE))
            self.assertEqual(bytes(uc.mem_read(BASE + off, 0x100000)), want, "window +%#x" % off)


@needs_capstone
class ArmInitEdge(unittest.TestCase):
    """How far the real bytes go past the start code, and what an early C checkpoint stop does.

    Findings recorded here (model, not hardware): the boot CPU gets from the entry to `loader_checkpoint(10)`
    in `arm_init` with an empty slot; a stop at checkpoint 10 enters `loader_jump`, which calls
    `PE_parse_boot_argn("bootcpu")` before `PE_init_platform` has stored `PE_state.bootArgs`, so the very
    first dereference is NULL + offsetof(CommandLine) = 0x6c."""

    STUB = BASE + 0x4980000

    @classmethod
    def setUpClass(cls):
        cls.sym = ap.macho_symbols(KERNEL)

    def test_reaches_checkpoint_10_with_empty_slot(self):
        ck = self.sym["_loader_checkpoint"]
        s = new_sim()
        s.run(stop_pcs=[ck])
        self.assertEqual(s.x[0], 10)
        self.assertEqual(s.x[30], self.sym["_arm_init"] + 0x468 + 4)       # the call site that loads x0 = 10
        self.assertTrue(s.mmu_on())
        self.assertGreater(s.steps, 8000)
        self.assertLess(s.steps, 9000)
        self.assertEqual(mapping_errors(s), [])

    def test_stop_at_checkpoint_10_faults_on_null_boot_args(self):
        c = cfg()
        s = new_sim()
        s.fill_slot(c["slot_va"], self.STUB, 10, (BASE - s.p.virt_base) & ks.M64)
        pe_state = self.sym["_PE_state"]
        self.assertEqual(s.u64_pa(s.pa_of_kva(pe_state + 0xa0)), 0)         # PE_state.bootArgs not yet stored
        with self.assertRaises(ks.SimFault) as cm:
            s.run(stop_pcs=[self.STUB])
        f = cm.exception
        self.assertEqual(f.kind, "translation-fault")
        self.assertEqual(f.va, 0x6c)                                         # NULL + offsetof(boot_args, CommandLine)
        internal = self.sym["_PE_parse_boot_argn_internal"]
        self.assertLess(internal, f.pc)
        self.assertLess(f.pc, internal + 0x100)
        # It happened inside loader_jump's call, i.e. after the stub was selected but before it was entered.
        self.assertEqual(s.pc, f.pc)
        self.assertNotEqual(s.pc, self.STUB)

    def test_boot_args_stored_between_checkpoint_10_and_11(self):
        """Static order from the real bytes: arm_init calls loader_checkpoint(10), cpu_data_init,
        PE_init_platform, loader_checkpoint(11); PE_init_platform's first-call path stores x19 (its second
        argument, the boot_args pointer) at PE_state+0xa0."""
        s = new_sim()
        md = ks.capstone.Cs(ks.capstone.CS_ARCH_ARM64, ks.capstone.CS_MODE_ARM)
        a0 = self.sym["_arm_init"]
        code = s.read_pa(s.pa_of_kva(a0), 0x520)
        seq = []
        prev = None
        for i in md.disasm(code, a0):
            if i.mnemonic == "bl":
                tgt = int(i.op_str[1:], 16)
                n = None
                if tgt == self.sym["_loader_checkpoint"] and prev is not None and prev.mnemonic == "mov":
                    n = int(prev.op_str.split("#")[1], 0)
                seq.append((i.address - a0, tgt, n))
            prev = i
        ck = self.sym["_loader_checkpoint"]
        order = [(off, n if tgt == ck else tgt) for off, tgt, n in seq if tgt in (ck, self.sym["_cpu_data_init"],
                                                                                self.sym["_PE_init_platform"])]
        self.assertEqual([o[1] for o in order][:4], [10, self.sym["_cpu_data_init"], self.sym["_PE_init_platform"], 11])
        self.assertEqual([o[0] for o in order][:4], [0x468, 0x478, 0x484, 0x48c])
        pip = self.sym["_PE_init_platform"]
        text = [(i.mnemonic, i.op_str) for i in md.disasm(s.read_pa(s.pa_of_kva(pip), 0x100), pip)]
        self.assertIn(("str", "x19, [x8, #0xa0]"), text)
        self.assertIn(("add", "x8, x8, #0xe88"), text)
        self.assertEqual(self.sym["_PE_state"] & 0xfff, 0xe88)


class Differ:
    """One instruction word at a time, run in the interpreter and in Unicorn from the same random state
    (MMU off, identity); registers, SP, NZCV, PC and a 64 KiB data buffer are compared."""

    CODE = BASE + 0x1100000
    BUF = BASE + 0x1000000
    BUFLEN = 0x10000
    SKIP = ("msr", "mrs", "isb", "dsb", "dmb", "dc", "ic", "tlbi", "at", "eret", "svc", "hvc", "smc", "brk", "hlt",
            "wfe", "wfi", "sev", "sevl", "yield", "nop", "hint", "clrex", "prfm", "prfum", "sys", "sysl", "udf")
    SKIP_PREFIX = ("ldx", "stx", "ldax", "stlx", "ldar", "stlr", "ldapr", "ldlar", "stllr", "cas", "swp", "ldadd",
                   "ldclr", "ldeor", "ldset", "ldsmax", "ldsmin", "ldumax", "ldumin", "pac", "aut", "xpac", "bra",
                   "bla", "retaa", "retab", "eretaa", "eretab")

    def __init__(self, seed):
        import random
        from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
        from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X29, UC_ARM64_REG_X30
        cs = ks.capstone
        self.cs = cs
        self.md = cs.Cs(cs.CS_ARCH_ARM64, cs.CS_MODE_ARM)
        self.md.detail = True
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(BASE, SIZE)
        self.rng = random.Random(seed)
        self.s = new_sim()
        self.xregs = [UC_ARM64_REG_X0 + i for i in range(29)] + [UC_ARM64_REG_X29, UC_ARM64_REG_X30]
        self.n = 0                                           # distinct addresses (Unicorn caches blocks by address)

    @staticmethod
    def regnum(name):
        """Register number of a capstone register name (x5, w5, fp, lr); None for SP/WSP and ZR."""
        name = {"fp": "x29", "lr": "x30"}.get(name, name)
        if name in ("sp", "wsp", "xzr", "wzr"):
            return None
        if name[0] in "xw" and name[1:].isdigit():
            return int(name[1:])
        raise AssertionError("unexpected register %r" % name)

    def skipped(self, ins):
        mn = ins.mnemonic
        return mn in self.SKIP or mn.startswith(self.SKIP_PREFIX)

    def compare(self, w, trials=8):
        """Returns (status, detail): status in ok / mismatch / unsupported / skipped / unicorn-fault; detail is
        the text of the first mismatch. Interpreter faults other than 'unsupported' and alignment are a
        mismatch."""
        from unicorn import UcError
        from unicorn.unicorn_const import UC_ERR_FETCH_UNMAPPED
        from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_NZCV, UC_ARM64_REG_PC
        cs, s, uc, rng = self.cs, self.s, self.uc, self.rng
        self.n += 1
        code = self.CODE + 0x10 * (self.n % 0x10000)
        decoded = list(self.md.disasm(w, code))
        if not decoded:
            return "skipped", "undecodable"
        ins = decoded[0]
        if self.skipped(ins):
            return "skipped", ins.mnemonic
        memops = [o for o in ins.operands if o.type == cs.arm64.ARM64_OP_MEM]
        if ins.writeback and memops:
            base = self.regnum(ins.reg_name(memops[0].mem.base))
            regs_used = [self.regnum(ins.reg_name(o.reg)) for o in ins.operands if o.type == cs.arm64.ARM64_OP_REG
                         and ins.reg_name(o.reg) not in ("xzr", "wzr")]
            if base is not None and base in regs_used:
                return "skipped", "writeback base is also a transfer register (UNPREDICTABLE)"
        label = "%s %s" % (ins.mnemonic, ins.op_str)
        ran = 0
        for _ in range(trials):
            regs = [rng.getrandbits(64) for _ in range(31)]
            sp = self.BUF + 0x8000
            for o in memops:
                base = self.regnum(ins.reg_name(o.mem.base))
                if base is not None:
                    regs[base] = self.BUF + 0x8000
                if o.mem.index:
                    idx_reg = self.regnum(ins.reg_name(o.mem.index))
                    if idx_reg is not None and idx_reg == base:
                        return "skipped", "index register is the base register: " + label
                    if idx_reg is not None:
                        # A W index is zero- or sign-extended from 32 bits: keep it small and non-negative.
                        lo = 0 if ins.reg_name(o.mem.index).startswith("w") else -0x100
                        regs[idx_reg] = rng.randrange(lo, 0x100) & ks.M64
            nzcv = rng.getrandbits(4)
            data = bytes(rng.getrandbits(8) for _ in range(self.BUFLEN))
            s.write_pa(code, w)
            s.write_pa(self.BUF, data)
            s.x[:] = regs
            s.sp_el[s.spsel] = sp
            s.n, s.z, s.c, s.v = [(nzcv >> k) & 1 for k in (3, 2, 1, 0)]
            s.pc = code
            uc.mem_write(code, w)
            uc.mem_write(self.BUF, data)
            for r, v in zip(self.xregs, regs):
                uc.reg_write(r, v)
            uc.reg_write(UC_ARM64_REG_SP, sp)
            uc.reg_write(UC_ARM64_REG_NZCV, nzcv << 28)
            try:
                s.step()
            except ks.SimFault as e:
                if e.kind in ("unsupported", "undefined"):
                    return "unsupported", label
                if e.kind.startswith("alignment"):
                    continue                      # the interpreter models alignment faults, Unicorn does not
                return "mismatch", "%s: interpreter fault %s" % (label, e)
            # Unicorn translates the block at the next PC before it honours count=1; for a branch that block
            # sits on zeroed memory and is cached as invalid, then replayed when a later word is written there.
            uc.ctl_flush_tb()
            try:
                uc.emu_start(code, 0, count=1)
            except UcError as e:
                # FETCH_UNMAPPED after the instruction ran (a register branch to a random target) is a
                # completed step; anything else (UNDEF, data abort) leaves no oracle for this word.
                if not (e.errno == UC_ERR_FETCH_UNMAPPED and uc.reg_read(UC_ARM64_REG_PC) != code):
                    return "unicorn-fault", label
            got = s.x[:] + [s.sp_el[s.spsel], s.n << 3 | s.z << 2 | s.c << 1 | s.v, s.pc]
            want = [uc.reg_read(r) for r in self.xregs] + [uc.reg_read(UC_ARM64_REG_SP),
                                                            uc.reg_read(UC_ARM64_REG_NZCV) >> 28,
                                                            uc.reg_read(UC_ARM64_REG_PC)]
            if got != want:
                bad = [("x%d" % k if k < 31 else ("sp", "nzcv", "pc")[k - 31], hex(a), hex(b))
                       for k, (a, b) in enumerate(zip(got, want)) if a != b]
                return "mismatch", "%s (word %s, nzcv %x): %s" % (label, w.hex(), nzcv, bad[:3])
            if bytes(s.read_pa(self.BUF, self.BUFLEN)) != bytes(uc.mem_read(self.BUF, self.BUFLEN)):
                return "mismatch", "%s (word %s): data buffer differs" % (label, w.hex())
            ran += 1
        return ("ok", label) if ran else ("skipped", "no aligned trial: " + label)


@needs_capstone
class SemanticsVsUnicorn(unittest.TestCase):
    """Differential test of the interpreter's instruction semantics against Unicorn (an independent CPU
    model). The model's value rests on these semantics, so they are checked twice:

    * the instruction words the interpreter really executes between the kernel entry and
      `loader_checkpoint(10)` (8 random register/flag/memory states each; system, barrier and exclusive words
      are skipped and covered by the dedicated tests above);
    * a fixed-seed fuzz over valid encodings of the data-processing, load/store and branch classes: every
      word the interpreter accepts must agree with Unicorn (words it does not implement are counted, not
      compared; UNPREDICTABLE writeback forms are skipped)."""

    def test_each_executed_word_agrees_with_unicorn(self):
        words = {}

        class Rec(ks.Sim):
            def fetch(self_inner):
                ins = ks.Sim.fetch(self_inner)
                words.setdefault(bytes(ins.bytes), (ins.mnemonic, ins.op_str))
                return ins

        Rec(PAYLOAD, BASE, SIZE).run(stop_pcs=[ap.macho_symbols(KERNEL)["_loader_checkpoint"]])
        self.assertGreater(len(words), 120)
        d = Differ(0x5EED)
        res = {}
        for w, (mn, ops) in sorted(words.items()):
            st, detail = d.compare(w)
            res.setdefault(st, []).append((mn, detail))
        self.assertEqual(res.get("mismatch", []), [])
        self.assertEqual(res.get("unsupported", []), [])             # the stream's own words are all implemented
        self.assertEqual(res.get("unicorn-fault", []), [])
        ok = res.get("ok", [])
        classes = {m for m, _ in ok}
        # Measured on this payload: 208 words executed, 20 skipped (system registers, barriers, hints), 34
        # mnemonics (add adrp and b b.cond bl cbnz cbz ccmp cmp csel cset ldnp ldp ldr lsl lsr mov movk orr ret
        # stnp stp str strb stur sub subs tbnz tbz).
        self.assertGreater(len(ok), 150)
        self.assertGreaterEqual(len(classes), 30)
        self.assertLess(len(res.get("skipped", [])), len(ok) // 5)

    def fuzz_words(self, rng, count):
        """Random words in the base-ISA classes (not SIMD/FP, not system)."""
        out = []
        while len(out) < count:
            w = rng.getrandbits(32)
            if (w >> 26) & 7 == 0b100:                      # data processing, immediate
                pass
            elif (w >> 25) & 7 == 0b101:                    # data processing, register
                pass
            elif (w >> 25) & 5 == 4:                        # loads and stores
                if (w >> 26) & 1:                           # V=1: SIMD/FP loads and stores
                    continue
            elif (w >> 26) & 7 == 0b101:                    # branches, exception generation, system
                if (w >> 24) & 0xFF in (0xD4, 0xD5, 0xD6, 0xD7):   # exception gen, system, register branch
                    continue
            else:
                continue
            out.append(struct.pack("<I", w))
        return out

    def test_fuzz_agrees_with_unicorn(self):
        import random
        rng = random.Random(0xF022)
        d = Differ(0xF023)
        res = {}
        for w in self.fuzz_words(rng, 5000):
            st, detail = d.compare(w, trials=3)
            res.setdefault(st, []).append(detail)
        summary = {k: len(v) for k, v in res.items()}
        self.assertEqual(res.get("mismatch", []), [], summary)
        # Measured with this seed over 5000 words: 2194 compared (72 distinct mnemonics), 78 not implemented by
        # the interpreter (counted, not compared), 2728 skipped (2589 of them unallocated encodings capstone
        # cannot decode; the rest exclusive/atomic/prefetch or UNPREDICTABLE forms). The mnemonics compared
        # include add/sub/adds/subs/and/orr/eor/bic/orn/eon with shifted and extended operands, bitfields,
        # mul/div, load/store (all addressing modes), pairs, branches.
        self.assertGreater(len(res.get("ok", [])), 1500, summary)
        compared = {x.split()[0] for x in res["ok"]}
        # Only classes that uniform sampling reaches reliably are asserted here. Conditional compare, csel and
        # b.cond are rare under uniform sampling (this seed drew three ccmn words and no ccmp), so they are
        # generated per class in test_targeted_classes_agree_with_unicorn instead of hoped for.
        for mn in ("add", "subs", "eor", "orn", "ubfx", "ldp", "ldr", "str", "stp", "madd", "cbz", "tbnz"):
            self.assertIn(mn, compared)

    # (name, fixed-bit mask, fixed-bit value): every other bit is random. Mnemonics each class must reach.
    TARGETED = [
        ("ccmp/ccmn register", 0x3FE00000 | 0xC10, 0x3A400000, {"ccmp", "ccmn"}),
        ("ccmp/ccmn immediate", 0x3FE00000 | 0xC10, 0x3A400800, {"ccmp", "ccmn"}),
        ("csel family", 0x3FE00000 | 0x800, 0x1A800000, {"csel", "csinc", "csinv", "csneg"}),
        ("b.cond", 0xFF000010, 0x54000000, {"b.eq", "b.ne", "b.lt", "b.hi"}),
        ("cbz/cbnz", 0x7E000000, 0x34000000, {"cbz", "cbnz"}),
        ("tbz/tbnz", 0x7E000000, 0x36000000, {"tbz", "tbnz"}),
        ("udiv/sdiv", 0x7FE0F800, 0x1AC00800, {"udiv", "sdiv"}),
        ("multiply-add", 0x7FE00000, 0x1B000000, {"madd", "msub"}),
        ("multiply-add long (64-bit)", 0xFF000000, 0x9B000000, {"smaddl", "umaddl"}),
    ]

    def test_targeted_classes_agree_with_unicorn(self):
        import random
        rng = random.Random(0x7A46)
        d = Differ(0x7A47)
        for name, mask, value, must in self.TARGETED:
            words = []
            while len(words) < 160:
                w = (rng.getrandbits(32) & ~mask) | value
                words.append(struct.pack("<I", w))
            res = {}
            for w in words:
                st, detail = d.compare(w, trials=3)
                res.setdefault(st, []).append(detail)
            summary = (name, {k: len(v) for k, v in res.items()})
            self.assertEqual(res.get("mismatch", []), [], summary)
            self.assertEqual(res.get("unicorn-fault", []), [], summary)
            self.assertGreater(len(res.get("ok", [])), 40, summary)
            compared = {x.split()[0] for x in res.get("ok", [])}
            self.assertTrue(must <= compared, (name, sorted(must - compared), summary))


if __name__ == "__main__":
    unittest.main(verbosity=2)
