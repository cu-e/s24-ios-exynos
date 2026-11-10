#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-035 host checks: the loader-equal model inputs and the resume of the payload kernel from a C-checkpoint stop
(README.md). Needs capstone, gcc and the local NAT-020/034 artifacts (a scratch virtualenv); every case skips and says
so without them. `make check` does not run this file.

What is checked, and what each check can fail on:
  (1) the model's ADT is the loader's patched ADT, not zeros, and the kernel's own PE_init_platform/pe_identify_machine
      code read the timebase frequency out of it (the NAT-030/033 model never did; this is the gap NAT-035 found);
  (2) the model's checkpoint-11 arrival still equals what run 009 measured on the phone (values read from the run-009
      evidence record, not retyped), so the new inputs did not move the anchor NAT-033 had;
  (3) the bytes the resume relies on are what the design says (`_set_mmu_ttb`, the `_loader_jump` early-return
      epilogue, the complete list of TTBR0 writers) -- these fail if the payload kernel changes;
  (4) a resume chain cp5 -> 11 -> 30 -> ... -> 14 ends in the kernel's own state of an uninterrupted run (entry state,
      registers, RAM), with no read of a clobbered register;
  (5) every resume primitive is needed: removing it is detected (negative controls).
They are host checks of a model; they do not show that the phone behaves the same."""
import json
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]

try:
    import cresume as cr
    import capstone
    HAVE = all(p.exists() for p in (cr.a5.PAYLOAD, cr.a5.KERNEL, cr.a5.ANALYSIS, cr.li.FIXED_PAYLOAD,
                                    cr.li.LOADER_SRC / "adt_patch.c"))
    WHY = "local artifacts missing"
except Exception as e:   # capstone or the artifacts are missing
    cr, HAVE, WHY = None, False, repr(e)

ready = unittest.skipUnless(HAVE, "capstone or local artifacts not available: %s" % (WHY,))
EVIDENCE_009 = ROOT / "docs/procedures/nat-022/native-attempt-009-evidence.json"
CHAIN = [11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14]   # program order of the checkpoints reachable in the model


@ready
class Inputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = cr.a5.Image()
        cls.sim, cls.a = cr.new(cls.img)
        cls.d = cr.li.describe(cls.sim)

    def test_adt_is_the_patched_payload_adt(self):
        s = self.sim
        self.assertEqual(len(s.adt_bytes), s.p.adt_size)
        self.assertTrue(any(s.adt_bytes), "zero ADT")
        self.assertEqual(s.read_pa(s.adt_pa, len(s.adt_bytes)), s.adt_bytes)      # really written into RAM
        # the loader's own patch changed the payload ADT (dram / pram / ramdisk), so it must differ from the raw payload
        raw = s.p.b[s.p.adt_off:s.p.adt_off + s.p.adt_size]
        self.assertNotEqual(raw, s.adt_bytes)
        self.assertEqual(len(raw), len(s.adt_bytes))

    def test_boot_args_fields(self):
        s = self.sim
        ba = s.read_pa(s.ba_pa, 760)
        BA = cr.li.BA
        self.assertEqual(struct.unpack_from("<I", ba, BA["deviceTreeLength"])[0], s.p.adt_size)
        self.assertEqual(struct.unpack_from("<Q", ba, BA["deviceTreeP"])[0], s.p.virt_base + (s.adt_pa - s.base))
        self.assertEqual(struct.unpack_from("<Q", ba, BA["physBase"])[0], s.base)
        self.assertEqual(struct.unpack_from("<Q", ba, BA["memSize"])[0], s.size)
        cl = bytes(ba[BA["CommandLine"]:BA["CommandLine"] + 608]).split(b"\0")[0]
        self.assertEqual(cl, s.cmdline)
        self.assertNotIn(b"e1s.hold=", cl)             # loader.c cmdline_xnu() drops it

    def test_cmdline_filter_cases(self):
        f = cr.li.cmdline_xnu
        self.assertEqual(f(b"a e1s.hold=5 b"), b"a b")
        self.assertEqual(f(b"e1s.hold=12  x"), b"x")
        self.assertEqual(f(b"a b  "), b"a b")
        self.assertEqual(f(b"xe1s.hold=5"), b"xe1s.hold=5")   # only at a word start

    def test_kernel_reads_the_timebase_from_the_adt(self):
        """The ADT carries cpu0 timebase-frequency 25600000; the kernel code (pe_identify_machine) must store it into
        gPEClockFrequencyInfo.timebase_frequency_hz (offset 0x48). In the NAT-030 model (zero ADT) it stayed 0."""
        # the value is looked up in the ADT bytes themselves, independent of the kernel
        adt = self.sim.adt_bytes
        i = adt.index(b"timebase-frequency")                    # ADT property: name[32], length u32, value
        self.assertEqual(struct.unpack_from("<II", adt, i + 32), (4, 25600000))
        sim = cr.reference(self.img, 30)
        g = self.img.vals["_gPEClockFrequencyInfo"]
        self.assertEqual(sim.read(g + 0x48, 4) & 0xFFFFFFFF, 25600000)


@ready
class AdtBootCpuReg(unittest.TestCase):
    """loader.c passes the whole 32-bit MPIDR_EL1 to adt_set_boot_cpu_mpidr(); the kernel's ml_get_cpu_number_local()
    compares the cpu topology's phys_id with MPIDR_EL1 & 0xffff. Bit 31 of MPIDR_EL1 is RES1 (Arm ARM; the model's
    own value 0x80000000 has it), so the two can never match. The kernel's own code is run on both variants."""
    TOPO = 0xfffffff0071c2000      # topology_info: +0x76c num_cpus, +0x780 cpu table (0x78 bytes each, phys_id at +4)

    def lookup(self, **kw):
        img = cr.a5.Image()
        sim = cr.reference(img, 14, **kw)          # the topology is parsed before checkpoint 14
        self.assertEqual(sim.read(self.TOPO + 0x76c, 4) & 0xFFFFFFFF, 1)
        phys = sim.read(sim.read(self.TOPO + 0x780, 8) + 4, 4) & 0xFFFFFFFF
        fn = img.vals["_ml_get_cpu_number_local"]
        sim.x[30] = cr.a5.STUB
        sim.pc = fn
        sim.run(stop_pcs={cr.a5.STUB, img.vals["_Assert"]}, limit=sim.steps + 5000)
        return phys, sim.sr["mpidr_el1"] & 0xFFFF, sim.pc == img.vals["_Assert"], sim.x[0] & 0xFFFFFFFF

    def test_as_built_the_lookup_fails_into_the_assertion(self):
        phys, mp16, asserted, _ = self.lookup()
        self.assertEqual(phys, 0x80000000)          # the kernel stored the reg the loader wrote, unmasked
        self.assertNotEqual(phys, mp16)
        self.assertTrue(asserted)

    def test_masked_reg_the_lookup_finds_cpu_0(self):
        phys, mp16, asserted, x0 = self.lookup(adt_reg=0)
        self.assertEqual(phys, mp16)
        self.assertFalse(asserted)
        self.assertEqual(x0, 0)


@ready
class Anchor(unittest.TestCase):
    """Model arrival at C checkpoint 11 against the run-009 hardware record."""

    @classmethod
    def setUpClass(cls):
        cls.img = cr.a5.Image()
        cls.ref = cr.reference(cls.img, 11)
        cls.ev = EVIDENCE_009.read_text()

    def test_arrival_equals_hardware(self):
        s = self.ref
        self.assertEqual((s.x[2], s.x[3], s.x[1]), (2, 11, 0))
        self.assertEqual(s.x[0] & ((1 << 48) - 1), 0x9e1f90a00)
        self.assertEqual(s.sr["ttbr0_el1"] & ((1 << 48) - 1), 0x9e2279000)
        self.assertEqual(s.sr["ttbr1_el1"] & ((1 << 48) - 1), 0x9e15af000)
        self.assertEqual(s.sr["tcr_el1"] & 0xFFFFFFFF, 0xa51a251a)
        self.assertEqual(s.sr["vbar_el1"] & 0xFFFF, 0x7000)
        # every anchor above is the value the run-009 record says the phone showed
        for text in ("0x9e1f90a00", "0x9e2279000", "0x9e15af000", "0xa51a251a", "0x7000"):
            self.assertIn(text, self.ev)

    def test_sctlr_differs_only_in_bits_5_and_7(self):
        hw, model = 0x3454599d, self.ref.sr["sctlr_el1"]
        self.assertEqual(model, 0x3454593d)
        self.assertEqual(hw ^ model, (1 << 5) | (1 << 7))


@ready
class Bytes(unittest.TestCase):
    """What the resume design relies on, read from the payload bytes."""

    @classmethod
    def setUpClass(cls):
        cls.img = cr.a5.Image()
        cls.md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

    def dis(self, va, n):
        return [(i.mnemonic, i.op_str) for i in self.md.disasm(self.img.p.va(va, 4 * n), va)]

    def test_set_mmu_ttb_is_the_gadget(self):
        g = self.img.vals[cr.KERNEL_SET_TTB]
        self.assertEqual(self.dis(g, 4), [("dsb", "ish"), ("msr", "ttbr0_el1, x0"), ("isb", ""), ("ret", "")])

    def test_jump_early_return_epilogue(self):
        e = self.img.vals["_loader_jump"] + cr.KERNEL_JUMP_EPILOGUE
        self.assertEqual(self.dis(e, 3), [("ldp", "x29, x30, [sp, #0x30]"), ("add", "sp, sp, #0x40"), ("ret", "")])

    def test_jump_returns_early_when_the_flag_is_set(self):
        """loader_jump starts by loading loader_return_entered and branching to the epilogue when it is set."""
        lj = self.img.vals["_loader_jump"]
        text = self.dis(lj, 14)
        flag_page = self.img.vals[cr.FLAG] & ~0xfff
        adrps = [op for mn, op in text if mn == "adrp" and int(op.split("#")[1], 16) == flag_page]
        self.assertTrue(adrps, text)
        self.assertTrue(any(mn == "cbnz" and "0x%x" % (lj + cr.KERNEL_JUMP_EPILOGUE) in op for mn, op in text)
                        or any(mn == "tbnz" and "0x%x" % (lj + cr.KERNEL_JUMP_EPILOGUE) in op for mn, op in text), text)

    def test_ttbr0_writers(self):
        """Every `msr ttbr0_el1` in the kernel's high text lies in _set_mmu_ttb or _loader_jump, and the only call
        sites of _set_mmu_ttb are the six pmap/arm_vm_init/common_start ones; the start code's own (physical-address)
        write happens before checkpoint 5."""
        img = self.img
        writers = set()
        for i, (a, n) in enumerate(img.items):
            if not a >> 60 == 0xf:
                continue
            e = img.addrs[i + 1] if i + 1 < len(img.addrs) else a + 0x1000
            if e <= a or e - a > 0x4000:
                continue
            raw = img.p.va(a, e - a)
            if raw is None:
                continue
            for ins in self.md.disasm(raw, a):
                if ins.mnemonic == "msr" and ins.op_str.startswith("ttbr0_el1"):
                    writers.add(n)
        self.assertEqual(writers, {"_set_mmu_ttb", "_loader_jump"})
        G = img.vals[cr.KERNEL_SET_TTB]
        callers = set()
        for vm, vs, fo, fs in img.p.segs:
            if vm >> 60 != 0xf:
                continue
            data = img.p.b[fo:fo + fs]
            for off in range(0, len(data) - 3, 4):
                w = int.from_bytes(data[off:off + 4], "little")
                if w & 0x7c000000 == 0x14000000:
                    imm = w & 0x3ffffff
                    imm -= (1 << 26) if imm & 0x2000000 else 0
                    if vm + off + imm * 4 == G:
                        callers.add(img.name(vm + off).split("+")[0])
        self.assertEqual(callers, {"_pmap_switch_internal", "_pmap_clear_user_ttb_internal", "_pmap_clear_user_ttb",
                                   "_arm_vm_init", "common_start"})


@ready
class Resume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = cr.a5.Image()
        cls.ref = cr.reference(cls.img, CHAIN[-1])
        cls.sim, cls.stops, cls.ttbr0 = cr.chain(cls.img, CHAIN)

    def test_every_stop_was_reached_in_order(self):
        self.assertEqual([s["n"] for s in self.stops], CHAIN)
        self.assertEqual([s["x3"] for s in self.stops], CHAIN)
        steps = [s["steps"] for s in self.stops]
        self.assertEqual(steps, sorted(steps))
        # the private table is installed at every stop, and the kernel's own one was captured at the checkpoint-5 stop
        self.assertEqual({s["ttbr0"] for s in self.stops}, {self.ref.sr["ttbr0_el1"]})
        self.assertEqual(self.ttbr0, 0x9e15ae000)

    def test_entry_state_equals_uninterrupted_run(self):
        c = cr.compare_entry(self.ref, self.sim)
        self.assertEqual(c["strict"], {}, c)
        self.assertEqual(len(self.sim.jump_entries), len(CHAIN))
        # DAIF is not restored by any primitive; it must be "all masked" at every stop the kernel reached
        self.assertTrue(all(e["daif_masked"] for e in self.sim.jump_entries))

    def test_stop_state_ram_and_registers(self):
        d = cr.compare(self.ref, self.sim, self.img)
        self.assertEqual(d["ram"], [])
        self.assertLessEqual(set(d["reg_diff"]), {"x%d" % r for r in cr.SCRATCH})

    def test_no_read_of_a_clobbered_register(self):
        self.assertEqual(self.sim.violations, [])


@ready
class NegativeControls(unittest.TestCase):
    """Each primitive is needed: without it the run either never stops again, faults, or ends in a different state."""
    ORDER = [11, 30]

    @classmethod
    def setUpClass(cls):
        cls.img = cr.a5.Image()
        cls.ref = cr.reference(cls.img, 30)

    def run_without(self, prim):
        return cr.chain(self.img, self.ORDER, omit=(prim,), limit=60000)

    def test_baseline_has_no_difference(self):
        sim, _, _ = cr.chain(self.img, self.ORDER)
        self.assertEqual(cr.compare_entry(self.ref, sim)["strict"], {})

    def test_without_clearing_the_flag_the_next_stop_never_comes(self):
        with self.assertRaises(cr.sd.a5.SimFault if hasattr(cr.sd.a5, "SimFault") else Exception) as cm:
            self.run_without("flag")
        self.assertIn("step-limit", str(cm.exception))

    def test_without_the_next_slot_value_the_next_stop_never_comes(self):
        with self.assertRaises(Exception) as cm:
            self.run_without("slot")
        self.assertIn("step-limit", str(cm.exception))

    def test_without_the_stack_pointer_the_run_faults(self):
        with self.assertRaises(Exception) as cm:
            self.run_without("sp")
        self.assertIn("translation-fault", str(cm.exception))

    def test_without_the_callee_saved_registers(self):
        sim, _, _ = self.run_without("callee")
        c = cr.compare_entry(self.ref, sim)
        self.assertTrue({"x%d" % r for r in range(19, 29)} <= set(c["strict"]), c)
        self.assertGreater(len(sim.violations), 0)        # the kernel read a clobbered register

    def test_without_x18(self):
        sim, _, _ = self.run_without("x18")
        self.assertEqual(set(cr.compare_entry(self.ref, sim)["strict"]), {"x18"})

    def test_without_the_kernel_ttbr0(self):
        for prim, in (("ttbr0",), ("ttbr0_private",)):
            sim, _, _ = self.run_without(prim)
            self.assertEqual(set(cr.compare_entry(self.ref, sim)["strict"]), {"ttbr0_el1"}, prim)


if __name__ == "__main__":
    unittest.main()
