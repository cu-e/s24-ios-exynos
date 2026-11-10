#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-032 host checks: resuming the payload kernel at its assembly checkpoint 5, and what it runs afterwards.

Run with a python that has capstone: `python3 -I docs/procedures/nat-032/test_nat032.py`. Every case skips
(and says so) without capstone or without the local artifacts (artifacts/nat-020/build-003/payload.bin,
kernel.no-storage and artifacts/nat-029/payload-analysis.json). `make check` does not run this file.

These are host checks on the real payload bytes and on the NAT-030 instruction-level model (no caches, TLB,
exceptions, timers or SIMD). They show what the kernel's own start code does when it is resumed the way
README.md proposes; they do not show that the S24 behaves the same.
"""
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]

try:
    import after5 as a5  # noqa: E402
    HAVE = all(p.exists() for p in (a5.PAYLOAD, a5.KERNEL, a5.ANALYSIS))
except Exception as e:  # capstone or the artifacts are missing
    a5, HAVE, WHY = None, False, repr(e)
else:
    WHY = "local artifacts missing"

ready = unittest.skipUnless(HAVE, "capstone or local artifacts not available: %s" % (WHY,))
M64 = (1 << 64) - 1


def snapshot(sim):
    return {pa: bytes(pg) for pa, pg in sim.pages.items() if any(pg)}


@ready
class ResumeAtFive(unittest.TestCase):
    """Stop at assembly checkpoint 5 (slot[2] = 5), then resume the way a stub that does not run under the kernel's
    MMU can: restore nothing about SCTLR_EL1, write slot[2] = 11, branch (MMU off) to the kernel's own MMU-enable
    block 28 bytes before the checkpoint macro. Reference: the same image run without any stop (slot[2] = 11)."""

    JUNKS = (0xDEADBEEFCAFEF00D, 0x0123456789ABCDEF)

    @classmethod
    def setUpClass(cls):
        cls.img = a5.Image()
        cls.lc = cls.img.vals["_loader_checkpoint"]
        cls.a = a5.analysis()
        ref = a5.Tracing(str(a5.PAYLOAD), a5.BASE, a5.SIZE)
        ref.fill_slot(cls.a["slot_va"], a5.STUB, 11, (a5.BASE - ref.p.virt_base) & M64)
        ref.run(stop_pcs={cls.lc}, limit=20000)
        cls.ref = ref
        cls.runs = []
        for junk in cls.JUNKS:
            sim, a = a5.stopped_at(5)
            cls.stop = sim.stop_state()
            n0, ev0 = sim.steps, len(sim.events)
            a5.resume_at_five(sim, a, 11, junk)
            sim.run(stop_pcs={cls.lc}, limit=sim.steps + 20000)
            cls.runs.append((junk, sim, sim.steps - n0, sim.events[ev0:]))

    def test_the_stop_is_the_documented_one(self):
        s = self.stop
        self.assertEqual((s["x2"], s["x3"], s["mmu_on"], s["daif_masked"]), (2, 5, False, True))
        self.assertEqual(s["sctlr"] | 1, 0x3454593d)      # the value the kernel wrote with M set

    def test_resumed_state_equals_the_uninterrupted_state(self):
        for junk, sim, _, _ in self.runs:
            with self.subTest(junk=hex(junk)):
                self.assertEqual(sim.pc, self.ref.pc)
                self.assertEqual(sim.x, self.ref.x)           # every register, clobbered ones included: they are rewritten
                self.assertEqual((sim.sp_el, sim.spsel, sim.sr), (self.ref.sp_el, self.ref.spsel, self.ref.sr))
                self.assertEqual((sim.n, sim.z, sim.c, sim.v, sim.daif_masked),
                                 (self.ref.n, self.ref.z, self.ref.c, self.ref.v, self.ref.daif_masked))
                self.assertEqual(snapshot(sim), snapshot(self.ref))

    def test_no_read_of_a_clobbered_register(self):
        for junk, sim, _, _ in self.runs:
            self.assertEqual(sim.violations, [], hex(junk))

    def test_resume_reenables_the_mmu_and_skips_the_stop(self):
        for junk, sim, steps, events in self.runs:
            w = [(n, v) for k, n, v, pc in events if k == "msr"]
            self.assertEqual(w[:3], [("sctlr_el1", 0x3454593d), ("cpacr_el1", 0x300000), ("tpidr_el1", 0)])
            self.assertTrue(sim.mmu_on())
            self.assertEqual(sim.x[0], 10)                  # loader_checkpoint(10), the next stop point
            self.assertTrue(250 < steps < 300, steps)       # 275 at the time of writing; a change here means new code ran

    def test_obvious_resume_at_site_plus_60_leaves_the_mmu_off_and_fails(self):
        """Negative control: the continuation NAT-031 uses for checkpoints 1..4 does not work for 5. With M clear
        the kernel's `ret` into arm_init (a high virtual address) executes as a physical address."""
        sim, a = a5.stopped_at(5)
        for r in (0, 1, 2, 3, 9, 10, 11):
            sim.x[r] = 0xBAD
        sim.write_pa(sim.pa_of_kva(a["slot_va"]) + 16, struct.pack("<Q", 11))
        sim.pc = sim.pa_of_kva(a["sites"][5]) + 15 * 4
        with self.assertRaises(a5.ks.SimFault) as cm:
            sim.run(stop_pcs={self.lc}, limit=sim.steps + 2000)
        self.assertEqual(cm.exception.kind, "external-abort")
        self.assertEqual(cm.exception.va, cm.exception.pc)
        self.assertGreater(cm.exception.pc, 0xFFFFFFF000000000)
        self.assertEqual(sim.mmu_on(), 0)

    def test_resume_with_slot_unchanged_stops_again(self):
        """Negative control: the slot word is what makes the kernel progress. With slot[2] still 5 the same
        site fires again."""
        sim, a = a5.stopped_at(5)
        a5.resume_at_five(sim, a, 5, 0x1234)
        sim.run(stop_pcs={a5.STUB, self.lc}, limit=sim.steps + 2000)
        self.assertEqual(sim.pc, a5.STUB)
        self.assertEqual((sim.x[2], sim.x[3]), (2, 5))

    def test_resume_needs_x21_preserved(self):
        """x21 decides primary/secondary in the kernel's start code (`cbnz x21` skips the checkpoint macro and the
        stop). A stub that loses it would turn the primary CPU into a 'secondary' one; the stub saves and restores it."""
        sim, a = a5.stopped_at(5)
        self.assertEqual(sim.x[21], 0)
        a5.resume_at_five(sim, a, 11, 0x1234)
        sim.x[21] = 1
        try:
            sim.run(stop_pcs={self.lc}, limit=sim.steps + 2000)
        except a5.ks.SimFault:
            return                                           # the run goes wrong: x21 is used as a pointer later
        self.assertNotEqual(sim.x, self.ref.x)               # or at least ends in a different state


@ready
class AfterCheckpointFive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = a5.Image()
        cls.a = a5.analysis()
        cls.t = a5.trace_to_c10()

    def test_call_sequence_from_the_resume_to_c_checkpoint_10(self):
        names = [self.img.sym_at(int(op[1:], 16))[1] for _, mn, op in self.t["calls"]]
        self.assertEqual(names, ["_arm_set_kernel_tbi", "_memmove", "_loader_checkpoint"])

    def test_model_stops_at_the_first_simd_instruction(self):
        """The model has no SIMD: the run past C checkpoint 10 ends in cpu_data_init+0x10 (`movi v0.16b, #0`). Anything
        after it is review-only in this project until a SIMD-capable emulator runs it."""
        sim = self.t["sim"]
        with self.assertRaises(a5.ks.SimFault) as cm:
            sim.run(stop_pcs=set(), limit=sim.steps + 3000)
        self.assertEqual(cm.exception.kind, "unsupported")
        self.assertEqual(cm.exception.pc, self.img.vals["_cpu_data_init"] + 0x10)
        self.assertIn("movi", str(cm.exception))

    def test_c_and_asm_checkpoint_numbers_are_disjoint(self):
        import json
        d = json.loads(a5.ANALYSIS.read_text())
        c = {x["checkpoint"] for x in d["c_checkpoints"]}
        s = {x["checkpoint"] for x in d["asm_checkpoints"]}
        self.assertEqual(s, {1, 2, 3, 4, 5})
        self.assertEqual(c, set(range(10, 22)) | set(range(30, 36)) | set(range(40, 45)))
        self.assertFalse(c & s)

    def test_loader_checkpoint_compares_slot_2_with_its_argument_and_tail_calls_loader_jump(self):
        img = self.img
        s = img.vals["_loader_checkpoint"]
        ins = [(i.mnemonic, i.op_str) for i in img.md.disasm(img.p.va(s, 36), s)]
        # nop, nop, ldr x8,[slot+0x10], cmp x8,x0, b.ne ret, mov x1,x0, mov w0,#2, b loader_jump, ret
        self.assertEqual([m for m, _ in ins], ["nop", "nop", "ldr", "cmp", "b.ne", "mov", "mov", "b", "ret"])
        self.assertEqual(int(ins[2][1].split("#")[-1], 16), self.a["slot_va"] + 16)
        self.assertEqual(ins[3][1], "x8, x0")
        self.assertEqual(int(ins[7][1][1:], 16), img.vals["_loader_jump"])

    def test_first_platform_call_is_the_vm_not_initialized_one(self):
        """arm_init calls PE_init_platform(0, boot_args) between C checkpoints 10 and 11. With w0 = 0 the function skips
        pe_arm_init_interrupts and pe_arm_init_debug (guarded by `cbz w20` / `cbnz w20`), so the code that maps ADT
        ranges with ml_io_map is not on this path."""
        img = self.img
        a = img.vals["_arm_init"]
        ins = list(img.md.disasm(img.p.va(a + 0x47C, 12), a + 0x47C))
        self.assertEqual([(i.mnemonic, i.op_str) for i in ins[:2]], [("mov", "w0, #0"), ("mov", "x1, x20")])
        self.assertEqual(int(ins[2].op_str[1:], 16), img.vals["_PE_init_platform"])
        p = img.vals["_PE_init_platform"]
        code = {i.address - p: (i.mnemonic, i.op_str) for i in img.md.disasm(img.p.va(p, 0x300), p)}
        self.assertEqual(code[0x14], ("mov", "x20, x0"))
        self.assertEqual(code[0x20][0], "cbz")                      # PE_state not initialized yet -> first-time init at +0x44
        self.assertEqual(code[0x20][1].split(",")[0], "w8")
        self.assertEqual(code[0x24][0], "cbz")                      # initialized and vm_initialized == 0 -> DT path at +0xc4
        self.assertEqual(code[0x24][1].split(",")[0], "w20")
        self.assertEqual(code[0x2C], ("bl", "#%#x" % img.vals["_pe_arm_init_interrupts"]))
        self.assertEqual(code[0xC0], ("cbnz", "w20, #%#x" % (p + 0x28)))   # after the first-time init, vm_initialized != 0 -> interrupts/debug
        self.assertEqual(code[0xC4][0], "str")

    def test_adt_has_what_the_first_platform_call_reads(self):
        """The payload's ADT (the loader copies it) contains the /cpus/cpu0 frequency properties that
        pe_identify_machine reads (a missing one leads to its cold panic path) and /chosen."""
        nodes = parse_adt(self.img.p)
        names = [n for n, _ in nodes]
        self.assertIn("/device-tree/chosen", names)
        cpu = dict(nodes)["/device-tree/cpus/cpu0"]
        for k in ("timebase-frequency", "bus-frequency", "memory-frequency", "peripheral-frequency",
                  "fixed-frequency", "clock-frequency"):
            self.assertIn(k, cpu)
            self.assertIn(len(cpu[k]), (4, 8), k)
        self.assertEqual(cpu["state"].split(b"\0")[0], b"running")
        root = dict(nodes)["/device-tree"]
        self.assertIn("target-type", root)
        self.assertIn("model", root)

    def test_gic_state_pointer_is_zero_and_nothing_on_the_path_sets_it(self):
        img = self.img
        va = img.vals["_gicd_base"]
        self.assertEqual(va, 0xFFFFFFF007E867B0)
        self.assertEqual(img.p.u64(va), 0)
        for fn in ("_gic_v3_irq_quiesce", "_gic_v3_irq_cpu_shutdown"):
            s = img.vals[fn]
            ins = [(i.mnemonic, i.op_str) for i in img.md.disasm(img.p.va(s, 0x24), s)]
            self.assertIn(("adrp", "x19, #0xfffffff007e86000"), ins)
            self.assertIn(("ldr", "x8, [x19, #0x7b0]"), ins)
            self.assertEqual(ins[5][0], "cbz")                      # a zero pointer branches to the epilogue
            self.assertEqual(ins[5][1].split(",")[0], "x8")
        # The pointer has one direct writer in the image. Everything arm_init runs between the resume and C checkpoint 11
        # is the three calls the model executed up to checkpoint 10 plus cpu_data_init and PE_init_platform; the writer is
        # in the direct-call closure of none of them (an over-approximation, so this is a sound "cannot be reached by a
        # direct call"; an indirect call through a function pointer is not followed).
        writers = img.stores_to(va & ~0xFFF, va & 0xFFF)
        self.assertEqual(writers, ["_gic_v3_irq_cpu_init"])
        for root in ("_arm_set_kernel_tbi", "_memmove", "_cpu_data_init", "_PE_init_platform"):
            self.assertNotIn(writers[0], img.closure(root, 12), root)

    def test_loader_jump_parses_the_bootcpu_boot_arg(self):
        img = self.img
        self.assertEqual(img.p.va(0xFFFFFFF0070A078B, 8).split(b"\0")[0], b"bootcpu")


def parse_adt(p):
    adt = p.b[p.adt_off:p.adt_off + p.adt_size]
    out = []

    def node(off, path):
        nprops, nchild = struct.unpack_from("<II", adt, off)
        off += 8
        props = {}
        for _ in range(nprops):
            name = adt[off:off + 32].split(b"\0")[0].decode("latin1")
            ln = struct.unpack_from("<I", adt, off + 32)[0] & 0x7FFFFFFF
            off += 36
            props[name] = adt[off:off + ln]
            off += (ln + 3) & ~3
        here = path + "/" + props.get("name", b"?").split(b"\0")[0].decode("latin1")
        out.append((here, props))
        for _ in range(nchild):
            off = node(off, here)
        return off

    end = node(0, "")
    assert end == len(adt), (end, len(adt))
    return out


if __name__ == "__main__":
    unittest.main()
