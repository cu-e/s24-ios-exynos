#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-033 host checks: the SIMD forms on the cp10 -> cp11 path of the payload kernel, and the model run to C
checkpoint 11 (README.md). Needs capstone and unicorn (a scratch virtualenv); every case skips and says so without
them or without the local artifacts. `make check` does not run this file.

What is checked: (1) the list of vector instruction forms is derived from the payload bytes, not typed in; (2) each
distinct instruction WORD that the closure of cpu_data_init and PE_init_platform contains is run in the extended
interpreter and in Unicorn on the same random registers and memory, and the vector registers, general registers, SP
and a 128 KiB buffer must agree; (3) the base class still refuses what is not implemented. These are host
checks of the model; they do not show that the phone behaves the same."""
import random
import re
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]

try:
    import simd as sd  # noqa: E402
    import unicorn
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X29, UC_ARM64_REG_X30, UC_ARM64_REG_SP,
                                     UC_ARM64_REG_Q0, UC_ARM64_REG_PC, UC_ARM64_REG_CPACR_EL1)
    XR = [UC_ARM64_REG_X0 + i for i in range(29)] + [UC_ARM64_REG_X29, UC_ARM64_REG_X30]   # X29/X30 are not contiguous
    HAVE = all(p.exists() for p in (sd.a5.PAYLOAD, sd.a5.KERNEL, sd.a5.ANALYSIS))
    WHY = "local artifacts missing"
except Exception as e:   # capstone, unicorn or the artifacts are missing
    sd, HAVE, WHY = None, False, repr(e)

ready = unittest.skipUnless(HAVE, "capstone/unicorn or local artifacts not available: %s" % (WHY,))
M64 = (1 << 64) - 1
BASE, SIZE = 0x9de400000, 0x20000000
BUF = BASE + 0x3000000
BUFLEN = 0x20000
MAPBASE, MAPLEN = BASE + 0x1000000, 0x4000000


def path_closure(img):
    cl = img.closure("_PE_init_platform", 4)
    cl.update(img.closure("_cpu_data_init", 0))
    return cl


def vector_words(img):
    """{word: (pc, mnemonic, op_str)} for every vector instruction in the closure (branches excluded)."""
    out = {}
    for n, (d, r) in path_closure(img).items():
        if not r["simd"]:
            continue
        s = r["start"]
        e = img.end_of(s)
        raw = img.p.va(s, e - s)
        for ins in img.md.disasm(raw, s):
            if ins.mnemonic in ("b", "bl"):
                continue
            if sd.is_simd(sd.SimdSim.split_ops(ins.op_str)):
                w = struct.unpack("<I", raw[ins.address - s:ins.address - s + 4])[0]
                out.setdefault(w, (ins.address, ins.mnemonic, ins.op_str))
    return out


@ready
class Forms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = sd.a5.Image()
        cls.words = vector_words(cls.img)

    def test_the_form_list_is_what_the_payload_contains(self):
        mns = {m for _, m, _ in self.words.values()}
        self.assertEqual(mns, {"add", "and", "cmeq", "cmhi", "dup", "eor", "fmov", "ldr", "ldur", "movi", "orr", "stp", "str",
                               "stur", "uminv", "ushl"})
        self.assertGreater(len(self.words), 60)

    def test_every_word_is_implemented_by_the_extended_interpreter(self):
        sim = sd.SimdSim(str(sd.a5.PAYLOAD), BASE, SIZE)
        base = BUF + 0x8000
        for w, (pc, mn, ops) in self.words.items():
            code, regs = place(w, pc, ops, random.Random(w), base)
            sim.write_pa(code, struct.pack("<I", w))
            sim.pc = code
            for i in range(31):
                sim.x[i] = regs[i]
            sim.sp_el[sim.spsel] = regs[31]
            sim.step()          # must not raise: an unimplemented form raises SimFault("unsupported")
            self.assertEqual(sim.pc, code + 4, (hex(pc), mn, ops))

    def test_not_implemented_forms_fail_loudly(self):
        """Vector forms outside the list raise SimFault("unsupported"); they are never silently skipped."""
        sim = sd.SimdSim(str(sd.a5.PAYLOAD), BASE, SIZE)
        code = BUF + 0x100
        for word, want in ((0x4EA0B800, "abs"), (0x0E200000, "saddl"), (0x4E040420, "dup")):   # dup v0.4s, v1.s[0]
            sim.write_pa(code, struct.pack("<I", word))
            sim.pc = code
            self.assertEqual(sim.fetch().mnemonic, want)
            with self.assertRaises(sd.SimFault) as cm:
                sim.step()
            self.assertEqual(cm.exception.kind, "unsupported", want)


def place(word, real_pc, ops, rng, base):
    """Where to put `word` and what to load into x0..x30, SP so that a memory form stays in the buffer. A literal
    load keeps its encoded offset, so the code goes at BUF + 0x10000 - offset (inside the mapped range)."""
    regs = [rng.getrandbits(64) for _ in range(31)] + [rng.getrandbits(64) & ~0xF]
    m = re.search(r"\[(x\d+|sp)", ops)
    if m:
        if m.group(1) == "sp":
            regs[31] = base
        else:
            regs[int(m.group(1)[1:])] = base
        code = BASE + 0x2000000
    elif re.match(r"^q\d+, #", ops):
        off = int(ops.split("#")[1], 16) - real_pc
        code = BUF + 0x10000 - off
    else:
        code = BASE + 0x2000000
    return code, regs


@ready
class AgainstUnicorn(unittest.TestCase):
    TRIALS = 3

    @classmethod
    def setUpClass(cls):
        cls.img = sd.a5.Image()
        cls.words = vector_words(cls.img)
        cls.sim = sd.SimdSim(str(sd.a5.PAYLOAD), BASE, SIZE)
        cls.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        cls.uc.mem_map(MAPBASE, MAPLEN)
        cls.uc.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)

    def run_one(self, word, pc, ops, seed):
        rng = random.Random(seed)
        base = BUF + 0x8000
        code, regs = place(word, pc, ops, rng, base)
        vregs = [rng.getrandbits(128) for _ in range(32)]
        data = bytes(rng.getrandbits(8) for _ in range(BUFLEN))
        sim, uc = self.sim, self.uc
        sim.write_pa(BUF, data)
        sim.write_pa(code, struct.pack("<I", word))
        sim.pc = code
        for i in range(31):
            sim.x[i] = regs[i]
        sim.sp_el[sim.spsel] = regs[31]
        sim.vr = list(vregs)
        sim.step()
        uc.mem_write(BUF, data)
        uc.mem_write(code, struct.pack("<I", word))
        uc.ctl_flush_tb()
        for i in range(31):
            uc.reg_write(XR[i], regs[i])
        uc.reg_write(UC_ARM64_REG_SP, regs[31])
        for i in range(32):
            uc.reg_write(UC_ARM64_REG_Q0 + i, vregs[i])
        uc.emu_start(code, code + 4, count=1)
        label = "%#x %s %s (word %#010x, seed %d)" % (pc, self.words[word][1], ops, word, seed)
        self.assertEqual([uc.reg_read(r) for r in XR], sim.x, "x regs: " + label)
        self.assertEqual(uc.reg_read(UC_ARM64_REG_SP), sim.sp_el[sim.spsel], "sp: " + label)
        self.assertEqual([uc.reg_read(UC_ARM64_REG_Q0 + i) for i in range(32)], sim.vr, "v regs: " + label)
        self.assertEqual(bytes(uc.mem_read(BUF, BUFLEN)), sim.read_pa(BUF, BUFLEN), "memory: " + label)
        self.assertEqual(uc.reg_read(UC_ARM64_REG_PC), sim.pc, "pc: " + label)

    def test_every_distinct_word_agrees_with_unicorn(self):
        n = 0
        for w, (pc, mn, ops) in sorted(self.words.items()):
            for seed in range(self.TRIALS):
                self.run_one(w, pc, ops, seed * 1000003 + w)
                n += 1
        self.assertGreater(n, 180)

    def test_edge_values_agree_with_unicorn(self):
        """Lane-edge inputs that random data rarely hits: all-zero and all-one vectors, equal vectors (cmeq), shift
        counts at and beyond the lane width, negative shifts (ushl)."""
        edge = [0, (1 << 128) - 1, 0x00FF00FF00FF00FF00FF00FF00FF00FF, 0x8000000080000000FFFFFFFF00000001,
                0x0000002000000020000000200000001F, 0xE0E0E0E0E0E0E0E0E0E0E0E0E0E0E0E0]
        sim, uc = self.sim, self.uc
        for w, (pc, mn, ops) in sorted(self.words.items()):
            if mn not in ("ushl", "cmeq", "cmhi", "add", "uminv", "orr", "and", "eor", "dup"):
                continue
            for a in edge:
                for b in edge:
                    code, regs = place(w, pc, ops, random.Random(w), BUF + 0x8000)
                    vregs = [a if i % 2 == 0 else b for i in range(32)]
                    sim.write_pa(code, struct.pack("<I", w))
                    sim.pc = code
                    for i in range(31):
                        sim.x[i] = regs[i]
                    sim.sp_el[sim.spsel] = regs[31]
                    sim.vr = list(vregs)
                    sim.step()
                    uc.mem_write(code, struct.pack("<I", w))
                    uc.ctl_flush_tb()
                    for i in range(31):
                        uc.reg_write(XR[i], regs[i])
                    uc.reg_write(UC_ARM64_REG_SP, regs[31])
                    for i in range(32):
                        uc.reg_write(UC_ARM64_REG_Q0 + i, vregs[i])
                    uc.emu_start(code, code + 4, count=1)
                    self.assertEqual([uc.reg_read(UC_ARM64_REG_Q0 + i) for i in range(32)], sim.vr,
                                     "%s %s a=%x b=%x" % (mn, ops, a, b))


@ready
class ToCheckpoint11(unittest.TestCase):
    """The real kernel, from the entry, to the C checkpoint 11 stop: with no stop before it (reference) and with the
    NAT-032 stop-and-resume at assembly checkpoint 5 (resumed). The model has no caches, TLB or exceptions."""

    @classmethod
    def setUpClass(cls):
        import c11
        cls.c11 = c11
        cls.img = sd.a5.Image()
        cls.ref, cls.a = c11.reference(cls.img)
        cls.res, _, cls.at5 = c11.resumed(cls.img)
        cls.ra = c11.arrival(cls.ref, cls.img, cls.a)
        cls.sa = c11.arrival(cls.res, cls.img, cls.a)

    def test_the_reference_run_arrives_at_the_stub_with_the_loader_jump_contract(self):
        r = self.ra
        self.assertEqual((r["x2"], r["x3"]), (2, 11))
        self.assertEqual(r["x0"], r["log_pa"])
        self.assertEqual(r["log_pa"], 0x9E1F90A00)                  # loader_log, NAT-029
        self.assertEqual(r["x1"], 0)                                 # the length passed is loader_log_len: nothing was logged
        self.assertEqual(r["log_len"], 0)
        self.assertTrue(r["mmu_on"])                                 # C arrival: MMU on, unlike the assembly checkpoints
        self.assertEqual(r["loader_return_entered"], 1)              # why the C path cannot be resumed
        self.assertEqual(r["x5"], sd.a5.STUB)
        self.assertEqual(r["sctlr"], 0x3454593D)
        self.assertEqual(r["ttbr1"], 0x9E15AF000)
        self.assertEqual(r["vbar"], 0xFFFFFFF007437000)
        self.assertEqual(r["cpacr"], 0x300000)

    def test_loader_jump_builds_its_private_table_inside_the_window(self):
        ttbr0 = self.ra["ttbr0"]
        self.assertNotEqual(ttbr0, 0x9E15AE000)                      # not the kernel's bootstrap TTBR0
        self.assertTrue(sd.a5.BASE <= ttbr0 < sd.a5.BASE + sd.a5.SIZE)

    def test_resume_at_five_arrives_in_the_same_state_as_the_uninterrupted_run(self):
        self.assertEqual(self.ref.x, self.res.x)
        self.assertEqual(self.ref.vr, self.res.vr)
        self.assertEqual(self.ref.sr, self.res.sr)
        self.assertEqual(self.ref.sp_el, self.res.sp_el)
        self.assertEqual(self.c11.snapshot(self.ref), self.c11.snapshot(self.res))
        self.assertEqual(self.res.violations, [])                    # no read of a register the stub clobbered
        self.assertGreater(self.res.steps, self.ref.steps)           # it re-executed the MMU-enable block and the macro
        self.assertEqual(self.at5, 8200)

    def test_the_executed_path_has_no_panic_no_mmio_mapping_and_no_log(self):
        fns = self.c11.functions(self.ref)
        self.assertEqual((len(fns), len(set(fns))), (67, 23))     # entries (repeats counted) and distinct functions
        for f in set(fns):
            self.assertNotIn("panic", f)
            self.assertFalse(f.startswith(("_ml_io", "_pmap_map", "_gic_v3_irq_cpu_init", "_psci", "_redwood")), f)
        self.assertIn("_cpu_data_init", fns)
        self.assertIn("_PE_init_platform", fns)
        self.assertEqual(fns[-1], "_loader_jump")
        self.assertEqual(self.ra["log_len"], 0)

    def test_the_gic_quiesce_call_on_the_path_does_nothing(self):
        fns = self.c11.functions(self.ref)
        self.assertIn("_gic_v3_irq_quiesce", fns)
        # between its entry and the next function it executes only the zero-pointer early return (see NAT-032)
        i = [k for k, (_, n) in enumerate(self.ref.fn_seq) if n == "_gic_v3_irq_quiesce"][0]
        self.assertLess(self.ref.fn_seq[i + 1][0] - self.ref.fn_seq[i][0], 12)

    def test_every_vector_instruction_that_ran_is_a_word_checked_against_unicorn(self):
        checked = set(vector_words(self.img))
        ran = {w for _, _, w in self.ref.simd_executed}
        self.assertEqual(len(self.ref.simd_executed), 39)
        self.assertTrue(ran <= checked, sorted(hex(w) for w in ran - checked))

    def test_the_resumed_run_differs_in_exactly_two_system_register_writes(self):
        """Reference: ... sctlr(0x..3d) cpacr tpidr daifset tcr ttbr0.  Resumed: the same with, after the first sctlr
        write, the checkpoint macro's MMU-off write (0x..3c, just before it branches to the stub) and the replay of the
        kernel's own MMU-on write (0x..3d) from the NAT-032 resume point."""
        def seq(sim):
            return [(n, v) for k, n, v, pc in sim.events if k == "msr"]
        ref, res = seq(self.ref), seq(self.res)
        self.assertEqual((len(ref), len(res)), (15, 17))
        k = ref.index(("sctlr_el1", 0x3454593D))
        self.assertEqual(res[:k + 1], ref[:k + 1])
        self.assertEqual(res[k + 1:k + 3], [("sctlr_el1", 0x3454593C), ("sctlr_el1", 0x3454593D)])
        self.assertEqual(res[k + 3:], ref[k + 1:])
        self.assertEqual([n for n, _ in ref[k + 1:]], ["cpacr_el1", "tpidr_el1", "daifset", "tcr_el1", "ttbr0_el1"])

    def test_unaligned_accesses_are_recorded_on_normal_memory_with_the_mmu_on(self):
        """A not naturally aligned access (two vector, three general-register) is legal on Normal memory
        (SCTLR_EL1.A = 0) and an alignment fault on Device memory: every one of the five on the path is to a kernel
        (TTBR1) page whose MAIR attribute is Normal."""
        self.assertEqual(len(self.ref.unaligned), 5)
        self.assertEqual(self.ref.sr["sctlr_el1"] & 2, 0)            # A clear
        for pc, va, size, mair in self.ref.unaligned:
            self.assertTrue(pc >> 63 and va >> 63)
            self.assertEqual(mair, 0xFF, hex(va))                    # Normal Inner/Outer Write-Back (MAIR byte 0 here)


@ready
class ControlSimd(unittest.TestCase):
    def test_a_wrong_cmhi_is_caught_by_the_unicorn_comparison(self):
        """Negative control: the comparison would fail if an implemented form were wrong."""
        case = AgainstUnicorn("test_every_distinct_word_agrees_with_unicorn")
        AgainstUnicorn.setUpClass()
        orig = sd.SimdSim._simd

        def broken(self, mn, ops, ins):
            if mn == "cmhi":
                la = sd.lanes_of(self.vr[sd.vtok(ops[1])[0]], 16, 8)
                lb = sd.lanes_of(self.vr[sd.vtok(ops[2])[0]], 16, 8)
                self.vr[sd.vtok(ops[0])[0]] = sd.join([255 if x >= y else 0 for x, y in zip(la, lb)], 8)
                return
            return orig(self, mn, ops, ins)

        sd.SimdSim._simd = broken
        try:
            with self.assertRaises(AssertionError):
                case.test_edge_values_agree_with_unicorn()
        finally:
            sd.SimdSim._simd = orig


if __name__ == "__main__":
    unittest.main()
