#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-034 host tests: the loader side of the first run past assembly checkpoint 5 (ckpt2.c, ckpt2_stub.S, the CKPT2
marker frames and the loader-diag-xnu-ckpt2 image). Evidence kind: host-test. Nothing here runs on the phone.

Layers, each runs only what it can:
  * ckpt.c + ckpt2.c built for the host (gcc, alignment sanitizer) against the real payload bytes: the decision table
    (resume 1..4 as before, resume 5 at site 5 - 28 with slot[2] = 11, final hold at C checkpoint 11), the slot write.
  * markerlib.c's CKPT2 report against the fake DECON0, read back with the independent decoder (decode.py).
  * the aarch64 code (zig): ckpt.c + ckpt2.c + ckpt2_stub.S linked with test doubles for the marker routines and run by
    the NAT-033 model (the NAT-030 interpreter plus the SIMD forms) on the real payload kernel from its entry: the chain
    1..5, the NAT-032 resume, the kernel's own run to loader_checkpoint(11) and the arrival there, MMU on, through
    loader_jump's private TTBR0. Needs zig, capstone and the NAT-020 build-003 payload.
  * a build/regression test of the images.
The model has no caches, no exceptions and no real memory attributes: what it shows is the register/memory contract of
the stub and what the kernel does in the model, not the behaviour of the S24."""
import ctypes, importlib.util, json, os, re, shutil, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = Path(os.environ["NAT034_SRC"]) if os.environ.get("NAT034_SRC") else HERE / "src"     # a mutated copy of src/ for the mutation checks
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


t31 = _load("test_nat031", HERE / "test_nat031.py")       # the NAT-031 helpers (its own tests are not run from here)
dec, bld, ap = t31.dec, t31.bld, t31.ap
capstone = t31.capstone
VIRT, SLOT_VA, SITES, M64 = t31.VIRT, t31.SLOT_VA, t31.SITES, t31.M64
NEEDS_PAYLOAD = t31.NEEDS_PAYLOAD
zig_ok = t31.zig_ok
try:
    c11 = _load("nat033_c11", ROOT / "docs/procedures/nat-033/c11.py")
except Exception as e:           # capstone/unicorn missing: the model-based classes skip themselves
    c11 = None
    _c11_error = e

DELTA = (0x9de400000 - VIRT) & M64
C11 = 11


@NEEDS_PAYLOAD
class Ckpt2Host(unittest.TestCase):
    """ckpt.c + ckpt2.c (NAT031_HOST) on the real payload bytes. gcc's alignment sanitizer traps any misaligned access."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        so = Path(cls.tmp.name) / "ckpt2.so"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DNAT031_HOST", "-fsanitize=alignment", "-fsanitize-undefined-trap-on-error",
                        "-shared", "-fPIC", f"-I{SRC}", str(SRC / "ckpt.c"), str(SRC / "ckpt2.c"), "-o", str(so)], check=True)
        lib = cls.lib = ctypes.CDLL(str(so))
        u64, u32, p = ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p
        lib.nat031_prepare.argtypes = [p, ctypes.c_size_t, u64, u64, ctypes.POINTER(u32)]; lib.nat031_prepare.restype = ctypes.c_int
        lib.nat034_decide.argtypes = [p, u64, u64, p]
        lib.nat034_set_next.argtypes = [p, u32]
        cls.payload = ap.Payload(str(PAYLOAD))
        cls.image = t31.window_prefix(cls.payload, 0x3500000)

    State, Decision = t31.CkptHost.State, t31.CkptHost.Decision

    def new_state(self):
        buf = (ctypes.c_char * len(self.image)).from_buffer_copy(bytes(self.image))
        base = ctypes.addressof(buf)
        st = self.State()
        bad = ctypes.c_uint32(0)
        self.assertEqual(self.lib.nat031_prepare(ctypes.byref(st), base, VIRT, 0x9e2d80000, ctypes.byref(bad)), 0)
        self._keep = buf
        return st

    def decide(self, st, x2, x3):
        d = self.Decision()
        self.lib.nat034_decide(ctypes.byref(st), x2, x3, ctypes.byref(d))
        return d.action, d.next, d.resume_pa

    def walk(self, st, upto):
        for n in range(1, upto + 1):
            self.assertEqual(self.decide(st, 2, n)[0], 1, n)

    def test_checkpoints_1_to_4_decide_exactly_as_in_nat031(self):
        st = self.new_state()
        base = st.pa_minus_va
        for n in range(1, 5):
            act, nxt, pa = self.decide(st, 2, n)
            self.assertEqual((act, nxt, pa), (1, n + 1, (SITES[n - 1] + 60 + base) & M64), n)
            self.assertEqual((st.expect, st.mask, st.arrivals), (n + 1, (1 << (n + 1)) - 2, n))

    def test_checkpoint_5_resumes_at_the_mmu_enable_block_with_slot_2_set_to_11(self):
        st = self.new_state()
        self.walk(st, 4)
        act, nxt, pa = self.decide(st, 2, 5)
        self.assertEqual((act, nxt), (1, C11))                                         # RESUME, next stop = the C checkpoint 11
        self.assertEqual(pa, (SITES[4] - 28 + st.pa_minus_va) & M64)                   # the block that turns the MMU on, 7 instructions before the macro
        self.assertEqual((st.expect, st.mask, st.arrivals), (C11, 0x3e, 5))

    def test_the_c_checkpoint_is_a_final_hold_and_only_when_it_is_expected(self):
        st = self.new_state()
        self.walk(st, 5)
        self.assertEqual(self.decide(st, 2, C11), (2, C11, 0))                         # HOLD, marked as the C stop
        self.assertEqual((st.mask, st.arrivals, st.expect), (0x3e | 1 << 11, 6, C11))
        for first in (0, 1, 2, 3, 4):                                                  # 11 before 5 has been passed: an unexpected arrival
            st = self.new_state()
            self.walk(st, first)
            self.assertEqual(self.decide(st, 2, C11), (2, 0, 0), first)
            self.assertEqual(st.mask & (1 << 11), 0, first)
            self.assertTrue(st.mask & (1 << 10), first)

    def test_everything_else_holds_with_the_nat031_masks(self):
        cases = [((2, 3), 1 << 10), ((2, 2), 1 << 10), ((2, 0), 1 << 10), ((2, 6), 1 << 10), ((2, 12), 1 << 10), ((2, 1 << 40), 1 << 10),
                 ((3, 1), 1 << 10), ((1, 0x96000045), 1 << 8), ((0, 0), 1 << 9), ((M64, 1), 1 << 10), ((2, 5), 1 << 10), ((2, C11), 1 << 10)]
        for (x2, x3), bit in cases:
            st = self.new_state()
            self.assertEqual(self.decide(st, x2, x3), (2, 0, 0), (x2, x3))
            self.assertEqual((st.mask, st.arrivals, st.expect), (bit, 1, 1), (x2, x3))
        for x2, x3, bit in ((2, 5, 1 << 10), (2, 4, 1 << 10), (1, 0x96000045, 1 << 8), (0, 0, 1 << 9), (2, 6, 1 << 10)):
            st2 = self.new_state()
            self.walk(st2, 5)
            before = st2.mask
            self.assertEqual(self.decide(st2, x2, x3), (2, 0, 0), (x2, x3))
            self.assertEqual((st2.mask, st2.expect), (before | bit, C11), (x2, x3))

    def test_the_reason_is_compared_at_5_and_at_11(self):
        """x3 alone must not decide: with x2 = 1 the kernel's x3 is an ESR value, with x2 = 0 it is not a checkpoint number."""
        for walked, x3 in ((4, 5), (5, C11)):
            for x2, bit in ((1, 1 << 8), (0, 1 << 9), (3, 1 << 10), (M64, 1 << 10)):
                st = self.new_state()
                self.walk(st, walked)
                before = st.mask
                self.assertEqual(self.decide(st, x2, x3), (2, 0, 0), (walked, x2))              # an ordinary hold, never the resume and never the C stop
                self.assertEqual((st.mask, st.expect), (before | bit, walked + 1 if walked < 5 else C11), (walked, x2))

    def test_set_next_stores_one_aligned_word_in_slot_2(self):
        buf = (ctypes.c_char * len(self.image)).from_buffer_copy(bytes(self.image))
        st = self.State(); st.slot_pa = ctypes.addressof(buf) + (SLOT_VA - VIRT)
        before = bytes(buf)
        self.lib.nat034_set_next(ctypes.byref(st), C11)
        after = bytes(buf)
        self.assertEqual([o for o in range(0, len(before), 8) if before[o:o + 8] != after[o:o + 8]], [SLOT_VA - VIRT + 16])
        self.assertEqual(struct.unpack_from("<Q", after, SLOT_VA - VIRT + 16)[0], C11)

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_resume_address_is_the_kernels_own_mmu_enable_block(self):
        """Independent of ckpt2.c: what the payload has at site 5 - 28 is the movk sequence building SCTLR_EL1 with M set, then
        msr/isb, then cbnz x21 (the primary-CPU test) falling into the checkpoint macro of site 5."""
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        off = SITES[4] - 28 - VIRT
        ins = list(md.disasm(bytes(self.image[off:off + 28]), SITES[4] - 28))
        self.assertEqual([i.mnemonic for i in ins], ["movk"] * 4 + ["msr", "isb", "cbnz"])
        self.assertEqual(ins[4].op_str, "sctlr_el1, x0")
        self.assertTrue(ins[6].op_str.startswith("x21, "))
        sctlr = 0
        for i in ins[:4]:                                                              # movk x0, #imm, lsl #sh: the value the kernel writes
            m = re.match(r"x0, #(\w+)(?:, lsl #(\d+))?$", i.op_str)
            sctlr |= int(m.group(1), 0) << int(m.group(2) or 0)
        self.assertEqual(sctlr & 1, 1)                                                 # the write turns the MMU on, which is why the resume is made MMU-off
        self.assertEqual(sctlr, 0x3454593d)
        self.assertEqual(ins[6].address + 4, SITES[4])                                 # and the cbnz is the last instruction before the macro of site 5


@unittest.skipUnless(zig_ok() and capstone and c11 is not None and PAYLOAD.exists(), "zig, capstone, unicorn or the NAT-020 build-003 payload is missing")
class C11Chain(unittest.TestCase):
    """The aarch64 stub + ckpt.c + ckpt2.c, compiled as the loader build does, run by the NAT-033 model on the payload kernel's
    real code from its entry to the final stop at loader_checkpoint(11), with test doubles for the marker routines."""
    BASE, SIZE = 0x9de400000, 0x20000000
    RET = BASE + 0x4a00000
    BAD = BASE + 0x4a10000
    KSP = 0xfffffff008060000
    LOADER = range(0x9e2d80000, 0x9e2e20000)

    @classmethod
    def setUpClass(cls):
        global ks, sd
        sd, ks = c11.sd, c11.ks
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        objs = []
        for name, src, extra in (("ckpt.c", SRC / "ckpt.c", bld.NO_SIMD + ["-DNAT034_IMAGE=1"]), ("ckpt2.c", SRC / "ckpt2.c", bld.NO_SIMD),
                                 ("mock.c", HERE / "test_support/nat034_mock.c", bld.NO_SIMD),
                                 ("ckpt2_stub.S", SRC / "ckpt2_stub.S", []), ("mockbss.S", HERE / "test_support/nat031_mock.S", [])):
            o = t / (name + ".o")
            subprocess.run(["zig", "cc", *[f for f in bld.FLAGS if f != "-mgeneral-regs-only"], *extra, f"-I{SRC}", "-c", str(src), "-o", str(o)], check=True)
            objs.append(o)
        cls.elf = t / "stub.elf"
        subprocess.run(["zig", "cc", "-target", "aarch64-freestanding", "-static", "-nostdlib", "-Wl,--build-id=none", "-Wl,-e,nat034_stub",
                        f"-Wl,-T,{HERE / 'test_support/nat034_mock.ld'}", *objs, "-o", str(cls.elf)], check=True)
        cls.secdata, cls.syms = t31.KernelChain.read_elf(cls.elf)
        cls.stack = cls.syms["_stack_top"]
        cls.stub = cls.syms["nat034_stub"]
        img = c11.a5.Image()
        ref, a = c11.reference(img)                                     # the NAT-033 reference run: its own stand-in stub, no loader code
        cls.ref = c11.arrival(ref, img, a)

    # --- harness ---------------------------------------------------------------------------------
    def mk(self, install=True, text_patch=None):
        sim = sd.SimdSim(str(PAYLOAD), self.BASE, self.SIZE)
        for a, d in self.secdata:
            sim.write_pa(a, d)
        for pa, word in (text_patch or {}).items():
            sim.write_pa(pa, struct.pack("<I", word))
        sim.write_pa(self.BAD, b"\xff" * 8)
        if install:
            rc = self.call(sim, "nat034_install", [self.BASE, VIRT, self.BAD])
            self.assertEqual((rc, struct.unpack("<I", sim.read_pa(self.BAD, 4))[0]), (0, 0))
        self.entry_state(sim)
        return sim

    def call(self, sim, fn, args, limit=20000):
        for i, a in enumerate(args):
            sim.x[i] = a
        sim.sp_el[1] = self.stack; sim.spsel = 1
        sim.x[30] = self.RET
        sim.pc = self.syms[fn]
        sim.run(stop_pcs={self.RET}, limit=sim.steps + limit)
        return sim.x[0]

    def entry_state(self, sim):
        sim.x = [0] * 31; sim.x[0] = sim.ba_pa
        sim.sp_el = [0, 0]; sim.spsel = 0
        sim.n = sim.z = sim.c = sim.v = 0
        sim.pc = sim.entry_pc; sim.steps = 0
        # whatever S-Boot left in the registers the stub reads (the model has no reset value; the kernel writes them all later, TTBR0 only after
        # the assembly checkpoints 1..4)
        sim.sr.update({"ttbr1_el1": 0xdead0001000, "tcr_el1": 0x1234, "vbar_el1": 0xbeef000, "ttbr0_el1": 0xdead0002000})

    def log(self, sim):
        n = struct.unpack("<I", sim.read_pa(self.syms["mock_n"], 4))[0]
        return [struct.unpack("<10Q", sim.read_pa(self.syms["mock_log"] + 80 * i, 80)) for i in range(n)]

    def c2(self, sim):
        return struct.unpack("<4Q", sim.read_pa(self.syms["mock_c2"], 32))

    def held(self, sim):
        return struct.unpack("<I", sim.read_pa(self.syms["mock_held"], 4))[0]

    def run_to_hold(self, sim, limit=300000):
        sim.run(stop_pcs={self.syms["mk_ckpt_hold"], self.syms["mk_ckpt2_hold"]}, limit=limit)
        try:                                                    # let the mock record, then it spins
            sim.run(limit=sim.steps + 80)
        except ks.SimFault as e:
            self.assertEqual(e.kind, "step-limit")

    def slot_words(self, sim):
        return struct.unpack("<4Q", sim.read_pa(sim.pa_of_kva(SLOT_VA), 32))

    def frame(self, sim):
        return struct.unpack("<32Q", sim.read_pa(self.stack - 0x100, 256))

    _chain = {}

    def chain(self):
        """The full run from the kernel entry to the final stop (cached: the model is slow)."""
        if "sim" not in self._chain:
            sim = self.mk()
            self.run_to_hold(sim)
            self._chain["sim"] = sim
        return self._chain["sim"]

    def direct(self):
        """The same loader code, slot[2] = 11 from the start: nothing stops the kernel before the C checkpoint."""
        if "direct" not in self._chain:
            sim = self.mk()
            sim.write_pa(sim.pa_of_kva(SLOT_VA) + 16, struct.pack("<Q", C11))
            self.run_to_hold(sim)
            self._chain["direct"] = sim
        return self._chain["direct"]

    # --- the whole chain ---------------------------------------------------------------------------
    def test_the_chain_stops_at_1_to_5_then_resumes_and_holds_at_the_c_checkpoint(self):
        sim = self.chain()
        recs = self.log(sim)
        self.assertEqual(self.held(sim), 2)
        self.assertEqual([(r[0], r[1]) for r in recs], [(2, n) for n in range(1, 6)] + [(2, C11)])
        self.assertEqual([(r[9] & 0xffffffff, r[9] >> 32) for r in recs], [(0x2, 1), (0x6, 2), (0xe, 3), (0x1e, 4), (0x3e, 5), (0x3e | 1 << 11, 6)])
        self.assertEqual([r[2] & 1 for r in recs], [0] * 5 + [1])                         # M clear at the assembly stops, set (as the kernel left it) at the C stop
        self.assertEqual(self.slot_words(sim)[2], C11)                                    # never changed by the kernel
        self.assertFalse(sim.violations)

    def test_the_arrival_equals_the_independent_nat033_reference_run(self):
        sim = self.chain()
        r = self.log(sim)[-1]
        x0, x1, x5, ttbr0 = self.c2(sim)
        ref = self.ref
        self.assertEqual((x0, x1), (ref["x0"], ref["x1"]))                               # the loader_log PA and its length (0: the kernel logged nothing)
        self.assertEqual(x5, self.stub)                                                  # the kernel branched to the slot's stub
        self.assertEqual(ttbr0, ref["ttbr0"])                                            # loader_jump's private table
        self.assertEqual((r[2], r[3], r[4], r[5]), (ref["sctlr"], ref["ttbr1"], ref["tcr"], ref["vbar"]))
        self.assertEqual((ref["sctlr"], ref["x0"], ref["x1"], ref["ttbr0"]), (0x3454593d, 0x9e1f90a00, 0, 0x9e2279000))

    def test_the_resumed_kernel_state_equals_a_run_that_was_never_stopped(self):
        a, b = self.direct(), self.chain()
        self.assertEqual(len(self.log(a)), 1)
        fa, fb = self.frame(a), self.frame(b)
        self.assertEqual(fa, fb)                                                         # every register the kernel had at the C stop, and its SP
        self.assertEqual({k: v for k, v in a.sr.items() if v != b.sr.get(k)}, {})
        diff = [k + o for k in sorted(set(a.pages) | set(b.pages)) if a.pages.get(k, bytes(4096)) != b.pages.get(k, bytes(4096))
                for o in range(0, 4096, 8) if a.pages.get(k, bytes(4096))[o:o + 8] != b.pages.get(k, bytes(4096))[o:o + 8]]
        self.assertTrue(diff)                                                            # the loader's own log differs ...
        self.assertTrue(all(x in self.LOADER for x in diff), [hex(x) for x in diff if x not in self.LOADER])     # ... and no kernel word does

    def test_the_prologue_turns_the_mmu_off_before_the_first_memory_access(self):
        sim = self.chain()
        arrival = self.log(sim)[-1][2]
        self.assertEqual(sim.sr["sctlr_el1"], arrival & ~5)                              # M and C cleared, nothing else changed
        self.assertEqual(self.frame(sim)[11], arrival)                                   # the arrival value is kept in the x11 slot
        self.assertEqual(self.frame(sim)[10], self.stack - 0x100)
        # In the model the stack (and every other loader data page) is outside loader_jump's 2 MiB block: with the MMU on the
        # stub's first store would take a translation fault. The unmodified stub runs; each mutation of the prologue must fail.
        words = [struct.unpack("<I", self.mk().read_pa(self.stub + 4 * i, 4))[0] for i in range(6)]
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        text = [(i.mnemonic, i.op_str) for w in words for i in md.disasm(struct.pack("<I", w), 0)]
        self.assertEqual(text[0], ("mrs", "x11, sctlr_el1"))
        self.assertEqual(text[1][0], "tbz")
        self.assertEqual(text[4], ("msr", "sctlr_el1, x10"))
        self.assertEqual(text[5][0], "isb")
        # (the isb after the msr cannot be tested here: the model has no pipeline, so removing it changes nothing it can see)
        for what, idx, word in (("no msr", 4, 0xd503201f), ("the clearing is a copy", 3, 0xaa0b03ea)):
            sim = self.mk(text_patch={self.stub + 4 * idx: word})
            with self.assertRaises(ks.SimFault) as cm:
                self.run_to_hold(sim)
            self.assertEqual(cm.exception.kind, "translation-fault", what)

    # --- crafted arrivals ---------------------------------------------------------------------------
    def arrive(self, sim, regs, sp, sctlr=0x3454593c):
        sim.x = [0] * 31
        for n, v in regs.items():
            sim.x[n] = v
        sim.spsel = 0; sim.sp_el = [sp, 0]
        sim.sr["sctlr_el1"] = sctlr
        sim.pc = self.stub
        sim.steps = 0

    def crafted_regs(self, x2, x3):
        r = {n: 0x1111111111111111 * (n % 15 + 1) ^ n for n in range(4, 31) if n not in (9, 10, 11)}
        r.update({0: 0, 1: 0, 2: x2, 3: x3, 9: 0xaaaa, 10: 0xbbbb, 11: 0xcccc})
        return r

    def resume_pc(self, sim, n):
        return sim.pa_of_kva(SITES[n - 1]) + (60 if n < 5 else -28)

    def after_bl(self, sim):
        for i in range(80):
            w = struct.unpack("<I", sim.read_pa(self.stub + 4 * i, 4))[0]
            if w >> 26 == 0b100101:
                return self.stub + 4 * (i + 1)
        raise AssertionError("no bl in the stub")

    def resume(self, sim, n, hostile=True):
        if hostile:
            sim.run(stop_pcs={self.after_bl(sim)}, limit=sim.steps + 100000)
            for r in [*range(1, 29), 29, 30]:
                sim.x[r] = 0xbad0bad0bad0bad0 + r
        sim.run(stop_pcs={self.resume_pc(sim, n)}, limit=sim.steps + 100000)

    def walk(self, sim, upto):
        for k in range(1, upto + 1):
            self.arrive(sim, self.crafted_regs(2, k), self.KSP)
            self.resume(sim, k, hostile=False)

    def test_the_stub_restores_every_live_register_and_lands_on_the_continuation_at_each_resume(self):
        for n in range(1, 6):
            sim = self.mk()
            self.walk(sim, n - 1)
            regs = self.crafted_regs(2, n)
            self.arrive(sim, regs, self.KSP + 0x40 * n)
            self.resume(sim, n)
            live = [r for r in range(4, 31) if r not in (9, 10, 11)]
            self.assertEqual({r: sim.x[r] for r in live}, {r: regs[r] for r in live}, n)
            self.assertEqual(sim.sp_el[sim.spsel], self.KSP + 0x40 * n)
            self.assertEqual(self.slot_words(sim)[2], n + 1 if n < 5 else C11, n)
            self.assertEqual(self.held(sim), 0)
            self.assertEqual(sim.sr["sctlr_el1"], 0x3454593c)                            # an assembly arrival: the prologue writes nothing
        # the resume from 5 lands on the kernel's `movk x0` block, the instruction word at that address is the one NAT-032 names
        self.assertEqual(struct.unpack("<I", sim.read_pa(self.resume_pc(sim, 5), 4))[0] & 0xffe00000, 0xf2e00000)

    def test_every_restore_instruction_matters_at_the_resume_from_5(self):
        sim0 = self.mk()
        words = [struct.unpack("<I", sim0.read_pa(self.stub + 4 * i, 4))[0] for i in range(80)]
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        free = {"x0, x1", "x2, x3", "x10, x11"}
        bl = next(i for i, w in enumerate(words) if w >> 26 == 0b100101)
        end = words.index(0xd61f0120)
        restores = [self.stub + 4 * i for i in range(bl + 1, end)
                    for ins in md.disasm(struct.pack("<I", words[i]), 0)
                    if ins.mnemonic in ("ldp", "ldr") and ins.op_str.split(", [")[0] not in free]
        self.assertEqual(len(restores), 11 + 3)
        live = [r for r in range(4, 31) if r not in (9, 10, 11)]

        def result(text_patch):
            sim = self.mk(text_patch=text_patch)
            self.walk(sim, 4)
            regs = self.crafted_regs(2, 5)
            self.arrive(sim, regs, self.KSP)
            self.resume(sim, 5)
            return {r: sim.x[r] for r in live} == {r: regs[r] for r in live} and sim.sp_el[sim.spsel] == self.KSP
        self.assertTrue(result({}))
        for pa in restores:
            self.assertFalse(result({pa: 0xd503201f}), "removing the instruction at %#x changed nothing the test can see" % pa)

    def test_unexpected_arrivals_hold_and_report_what_they_were_given(self):
        for walked, regs, mask, held, name in (
                (0, {2: 1, 3: 0x96000045, 4: 0xfffffff00743e0b0, 5: 0xdeadbeef}, 1 << 8, 1, "exception first"),
                (0, {2: 0}, 1 << 9, 1, "orderly first"), (0, {2: 2, 3: 5}, 1 << 10, 1, "checkpoint 5 first"),
                (0, {2: 2, 3: C11}, 1 << 10, 1, "the C checkpoint first"), (4, {2: 2, 3: C11}, 0x1e | 1 << 10, 1, "the C checkpoint before 5"),
                (5, {2: 2, 3: 5}, 0x3e | 1 << 10, 1, "checkpoint 5 twice"), (5, {2: 2, 3: 4}, 0x3e | 1 << 10, 1, "checkpoint 4 after 5"),
                (5, {2: 1, 3: 0x96000045, 4: 0xfffffff0074401f0, 5: 0xdeadbeef}, 0x3e | 1 << 8, 1, "exception after 5"),
                (5, {2: 0}, 0x3e | 1 << 9, 1, "orderly after 5"), (5, {2: 7, 3: 1}, 0x3e | 1 << 10, 1, "unknown reason after 5")):
            sim = self.mk()
            self.walk(sim, walked)
            merged = {**self.crafted_regs(2, 1), **regs}
            self.arrive(sim, merged, self.KSP)
            self.run_to_hold(sim)
            rec = self.log(sim)[-1]
            self.assertEqual((rec[0], rec[1]), (merged[2], merged[3]), name)
            self.assertEqual((rec[6], rec[7], rec[8]), (merged[3], merged[4], merged[5]), name)
            self.assertEqual((rec[9] & 0xffffffff, rec[9] >> 32), (mask, walked + 1), name)
            self.assertEqual(self.held(sim), held, name)                                  # the ordinary hold (1), never the C-stop report
            self.assertEqual(self.slot_words(sim)[2], walked + 1 if walked < 5 else C11, name)    # a hold never advances the slot

    def test_the_c_stop_is_reported_with_the_registers_it_was_given_and_is_final(self):
        sim = self.mk()
        self.walk(sim, 5)
        regs = {**self.crafted_regs(2, C11), 0: 0x9e1f90a00, 1: 0x1234, 5: self.stub}
        sim.sr["ttbr0_el1"] = 0x9e2279000
        self.arrive(sim, regs, self.KSP, sctlr=0x3454593c)                               # M clear: the model cannot place the crafted arrival under the private table
        self.run_to_hold(sim)
        self.assertEqual(self.held(sim), 2)
        self.assertEqual(self.c2(sim), (0x9e1f90a00, 0x1234, self.stub, 0x9e2279000))
        rec = self.log(sim)[-1]
        self.assertEqual((rec[0], rec[1], rec[9] >> 32, rec[9] & 0xffffffff), (2, C11, 6, 0x3e | 1 << 11))
        self.assertEqual(self.slot_words(sim)[2], C11)
        self.assertEqual(len(self.log(sim)), 6)                                          # five passes and the one hold: nothing is resumed from a C checkpoint

    def test_a_changed_site_makes_the_compiled_installer_refuse_and_write_nothing(self):
        sim = sd.SimdSim(str(PAYLOAD), self.BASE, self.SIZE)
        for a, d in self.secdata:
            sim.write_pa(a, d)
        site = sim.pa_of_kva(SITES[4]) + 4 * 8                                           # `mov x3, #5` of site 5
        w = struct.unpack("<I", sim.read_pa(site, 4))[0]
        sim.write_pa(site, struct.pack("<I", w ^ (1 << 5)))
        before = self.slot_words(sim)
        sim.write_pa(self.BAD, b"\xff" * 8)
        self.assertEqual(self.call(sim, "nat034_install", [self.BASE, VIRT, self.BAD]), 2)
        self.assertEqual(struct.unpack("<I", sim.read_pa(self.BAD, 4))[0], 5)
        self.assertEqual(self.slot_words(sim), before)


@unittest.skipUnless(zig_ok() and PAYLOAD.exists(), "zig or the payload is missing")
class Ckpt2Marker(unittest.TestCase):
    """What the stub draws (markerlib.c with MK_XNU_CKPT2=1 against the fake DECON0), decoded independently."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cc = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DMK_HOST=1", "-DMK_TRIG=1", "-DMK_LOADER=1", f"-I{SRC}"]
        cls.exe = t / "host_mk_ckpt2"
        subprocess.run([*cc, "-DMK_XNU_CKPT=1", "-DMK_XNU_CKPT2=1", "-DNAT031_HOST", str(SRC / "markerlib.c"), str(SRC / "ckpt.c"), str(SRC / "ckpt2.c"),
                        str(SRC / "host_mk.c"), "-o", str(cls.exe)], check=True)
        cls.old = t / "host_mk_ckpt"
        subprocess.run([*cc, "-DMK_XNU_CKPT=1", "-DNAT031_HOST", str(SRC / "markerlib.c"), str(SRC / "ckpt.c"), str(SRC / "host_mk.c"), "-o", str(cls.old)], check=True)

    def go(self, n, seq, full=False):
        out = Path(self.tmp.name) / "fb.bin"
        p = subprocess.run([str(self.exe), "ckpt2", str(n), str(out), "0x113", "0x3063", seq, *(["full"] if full else [])], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-300:] + p.stderr)
        ev = [l.split() for l in p.stdout.splitlines()]
        frames = [dec.parse_frame(int(e[1], 16)) for e in ev if e[0] == "DRAW"]
        self.assertTrue(frames and all(frames))
        return ev, frames

    SEQ = "2:1,2:2,2:3,2:4,2:5,2:11"

    def test_the_c_stop_report_carries_x0_x1_x5_ttbr0_then_the_system_registers(self):
        ev, frames = self.go(500, self.SEQ)
        d = dec.describe(frames)
        self.assertEqual((d["ckpt"]["x2"], d["ckpt"]["x3"], d["ckpt"]["arrival_mask"], d["ckpt"]["arrivals"]), (2, 11, 0x3e | 1 << 11, 6))
        self.assertEqual(d["ckpt"]["arrivals_seen"], ["checkpoint %d" % n for n in range(1, 6)] + ["C checkpoint 11 (NAT-034)"])
        self.assertEqual(d["ckpt2"], {"x0_lo48": "0x0009e1f90a00", "x1_lo32": "0x00a1b2c3", "x5_lo48": "0x0009e2d80000", "ttbr0_el1_lo48": "0x0009e2279000"})
        self.assertEqual((d["ckpt"]["sctlr_el1_lo32"], d["ckpt"]["ttbr1_el1_lo48"], d["ckpt"]["vbar_el1_lo16"], d["ckpt"]["tcr_el1_lo32"]),
                         ("0x3454593d", "0x0009e15af000", "0x7000", "0xa51a251a"))
        # order: REGS, MASK, ARRIVALS, then the eleven CKPT2 frames, then the old SCTLR/TTBR1/VBAR/TCR block
        hold = frames[next(i for i, f in enumerate(frames) if f["kind"] == 11 and f["idx"] == 10) - 2:]
        order = [(f["kind"], f["idx"]) for f in hold[:3 + 11 + 8]]
        self.assertEqual(order, [(11, 0), (11, 1), (11, 10)] + [(12, i) for i in range(11)] + [(11, 2), (11, 3), (11, 4), (11, 5), (11, 6), (11, 7), (11, 8), (11, 9)])

    def test_five_passes_then_the_hold_repeats_and_nothing_follows_it(self):
        ev, frames = self.go(500, self.SEQ)
        ck = [(f["idx"], f["data"]) for f in frames if f["kind"] == 11]
        self.assertEqual(ck[:10], [(0, 0x0201), (1, 0x2), (0, 0x0202), (1, 0x6), (0, 0x0203), (1, 0xe), (0, 0x0204), (1, 0x1e), (0, 0x0205), (1, 0x3e)])
        self.assertEqual(ck[10:13], [(0, 0x020b), (1, 0x83e), (10, 6)])
        regs = [i for i, f in enumerate(frames) if f["kind"] == 11 and f["idx"] == 0]
        self.assertGreaterEqual(len(regs), 8)                                                # five passes, then the held report repeats
        self.assertTrue(all(frames[i]["data"] == 0x020b for i in regs[5:]))

    def test_a_walk_that_does_not_reach_the_c_stop_holds_with_the_old_report(self):
        for seq in ("2:1,2:2,2:3,2:4,2:6", "2:1,2:2,2:3,2:4,2:5,2:5", "2:1,2:2,2:3,2:4,2:5,1:0x96000045", "2:11"):
            ev, frames = self.go(300, seq)
            d = dec.describe(frames)
            self.assertNotIn("ckpt2", d, seq)
            self.assertNotIn(1 << 11, [d["ckpt"]["arrival_mask"] & (1 << 11)], seq)

    def test_the_c_stop_is_drawn_only_by_the_ckpt2_markers(self):
        for exe in (self.old,):
            p = subprocess.run(["nm", str(exe)], capture_output=True, text=True, check=True).stdout
            self.assertNotIn("mk_ckpt2_hold", p)
        p = subprocess.run(["nm", str(self.exe)], capture_output=True, text=True, check=True).stdout
        self.assertIn("mk_ckpt2_hold", p)

    def test_the_ckpt2_hold_uses_the_nat031_stage_the_same_three_ways_as_the_nat031_hold(self):
        """test_nat031.py counts MK_ST_CKPT in the NAT-031 part of markerlib.c (5: ld_bit case, pass mask, hold mask, two stage frames). The NAT-034
        hold after `#if MK_XNU_CKPT2` has the hold's own three: the opening stage frame, the mask bit, the closing stage frame."""
        src = (SRC / "markerlib.c").read_text()
        part = src[src.index("#if MK_XNU_CKPT2"):]
        self.assertEqual(part.count("MK_ST_CKPT"), 3)
        self.assertEqual(part.count("ld_bit(MK_ST_CKPT)"), 1)

    def test_every_draw_is_followed_by_a_decon_kick(self):
        ev, frames = self.go(300, self.SEQ)
        draws = [i for i, e in enumerate(ev) if e[0] == "DRAW"]
        for a, b in zip(draws, draws[1:]):
            seg = ev[a + 1:b]
            self.assertTrue(seg and seg[0][:2] == ["RD", "20"], seg)
            self.assertTrue({e[1] for e in seg if e[0] == "WR"} <= {"30", "50"})

    def test_display_budget(self):
        """PRE_JUMP was drawn 19.5 s after the first frame in runs 006-008; each frame is shown for 1.2 s; the display ends about 83 s after the
        first frame. The CKPT2 values are the point of the run: they must be on screen once before the cut-off, with room to repeat."""
        ev, frames = self.go(600, self.SEQ, full=True)
        pre_jump = next(i for i, f in enumerate(frames) if f["kind"] == 3 and f["idx"] == 0 and f["data"] == 0x40)
        regs = [i for i, f in enumerate(frames) if f["kind"] == 11 and f["idx"] == 0]
        held = regs[5]
        c2_last = next(i for i, f in enumerate(frames[held:], held) if f["kind"] == 12 and f["idx"] == 10)
        tcr_last = next(i for i, f in enumerate(frames[held:], held) if f["kind"] == 11 and f["idx"] == 9)
        t_passes = 19.5 + (held - pre_jump) * 1.2
        t_c2 = 19.5 + (c2_last - pre_jump + 1) * 1.2
        t_tcr = 19.5 + (tcr_last - pre_jump + 1) * 1.2
        t_round = 19.5 + (regs[6] - pre_jump) * 1.2
        self.assertLess(t_passes, 40)                                                        # the five passes end by ~36 s
        self.assertLess(t_c2, 62)                                                            # x0, x1, x5, TTBR0 are on screen once by ~55 s
        self.assertLess(t_tcr, 70)                                                           # and the system registers by ~64 s
        self.assertLess(t_round, 83)                                                         # one complete held report fits before the display ends
        self.assertGreater(t_c2 - t_passes, 10)


NM_SIZES = t31.nm_sizes


@unittest.skipUnless(zig_ok() and (ROOT / "artifacts/nat-020/build-003/source").exists() and (ROOT / "artifacts/nat-031/build-002/build.json").exists(),
                     "zig, the NAT-020 build-003 source or the NAT-031 build record is missing")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "o"
        r = subprocess.run([sys.executable, str(HERE / "build.py"), "--out", str(cls.out), "--loader-source", str(ROOT / "artifacts/nat-020/build-003/source")],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.rec = json.loads((cls.out / "build.json").read_text())

    def test_every_earlier_image_and_payload_is_byte_identical(self):
        old = json.loads((ROOT / "artifacts/nat-031/build-002/build.json").read_text())
        for n, v in old["images"].items():
            self.assertEqual(self.rec["images"][n]["sha256"], v["sha256"], n)
        for n, v in old["image_payloads"].items():
            self.assertEqual(self.rec["image_payloads"][n]["sha256"], v["sha256"], n)
        self.assertNotIn("loader-diag-xnu-ckpt2", old["images"])
        self.assertIn("loader-diag-xnu-ckpt2", self.rec["images"])

    def test_the_ckpt2_loader_differs_from_the_ckpt_loader_in_the_install_call_only(self):
        o = self.out
        a = (o / "loader-diag-xnu-ckpt/source/shim/e1s-xnu/loader.c").read_text().splitlines()
        c = (o / "loader-diag-xnu-ckpt2/source/shim/e1s-xnu/loader.c").read_text().splitlines()
        import difflib
        diff = [l for l in difflib.unified_diff(a, c, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        self.assertEqual(diff, ['-#include "ckpt.h"', '+#include "ckpt2.h"',
                                '-\t\tif (nat031_install(win_base, p->virt_base, &nat031_bad))', '+\t\tif (nat034_install(win_base, p->virt_base, &nat031_bad))'])
        for f in ("adt_patch.c", "ui.c", "fdt.c", "gic.c", "guard.c", "s5e9945.c", "start.S"):
            self.assertEqual((o / "loader-diag-xnu-ckpt2/source/shim/e1s-xnu" / f).read_bytes(), (o / "loader-diag-xnu-ckpt/source/shim/e1s-xnu" / f).read_bytes(), f)
        ip = self.rec["image_payloads"]
        n1 = (o / ip["loader-diag-xnu-ckpt2"]["path"]).read_bytes()
        n0 = (o / ip["loader-diag-xnu-ckpt"]["path"]).read_bytes()
        s1 = (o / "loader-diag-xnu-ckpt2/Image").stat().st_size
        s0 = (o / "loader-diag-xnu-ckpt/Image").stat().st_size
        self.assertEqual(n1[s1:], n0[s0:])                                                   # the SWEETXNU payload is the bytes of run 007 and 008

    def elf(self, name="loader-diag-xnu-ckpt2"):
        return self.out / name / "loader.elf"

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_nat034_code_has_no_simd_and_no_misaligned_access(self):
        d = self.out / "loader-diag-xnu-ckpt2"
        sizes = NM_SIZES(self.elf())
        img = (d / "Image").read_bytes()
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM); md.detail = True
        simd = re.compile(r"^[vqdsbh]\d+$")
        for fn in ("nat031_check", "nat031_prepare", "nat031_decide", "nat031_set_next", "nat031_site_va", "nat034_decide", "nat034_set_next", "nat034_install", "nat034_ckpt_c"):
            a, n = sizes[fn]
            self.assertGreater(n, 0, fn)
            for ins in md.disasm(img[a:a + n], a):
                names = {md.reg_name(r) for r in list(ins.regs_read) + list(ins.regs_write)}
                names |= {md.reg_name(op.reg) for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG and op.reg}
                self.assertFalse(any(simd.match(x or "") for x in names), (fn, hex(ins.address), ins.mnemonic))
        stub = sizes["nat034_stub"][0]
        for ins in md.disasm(img[stub:stub + 0x120], stub):
            if ins.mnemonic == "br":
                break
            self.assertFalse(any(simd.match(md.reg_name(op.reg) or "") for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG), (ins.mnemonic, ins.op_str))
        r = subprocess.run([sys.executable, "-I", str(HERE / "scan_unaligned.py"), str(d / "Image"), "--elf", str(self.elf())], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.splitlines()), (0, ["total 0"]))

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_prologue_in_the_image_is_registers_only_and_uses_only_x9_x10_x11(self):
        d = self.out / "loader-diag-xnu-ckpt2"
        sizes = NM_SIZES(self.elf())
        img = (d / "Image").read_bytes()
        a = sizes["nat034_stub"][0]
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM); md.detail = True
        ins = list(md.disasm(img[a:a + 4 * 7], a))
        self.assertEqual([(i.mnemonic, i.op_str.split(",")[0]) for i in ins[:6]], [("mrs", "x11"), ("tbz", "w11"), ("mov", "x10"), ("bic", "x10"), ("msr", "sctlr_el1"), ("isb", "")])
        self.assertEqual(ins[1].op_str.split(", ")[1], "#0")                                      # bit 0 = SCTLR_EL1.M
        self.assertEqual(int(ins[1].op_str.split(", ")[2].lstrip("#"), 0), a + 4 * 6)             # taken: over the clearing, to the first instruction of the body
        self.assertEqual(ins[2].op_str, "x10, #5")                                                # M (bit 0) and C (bit 2)
        self.assertEqual(ins[3].op_str, "x10, x11, x10")
        for i in ins[:6]:
            self.assertNotIn(i.mnemonic, ("ldr", "ldp", "str", "stp", "ldur", "stur"))
        self.assertEqual(sizes["nat034_stub"][0] % 16, 0)
        self.assertEqual(sizes["_stack_top"][0] % 16, 0)

    def test_only_the_ckpt2_image_has_the_nat034_hook_and_it_has_not_the_nat031_one(self):
        for n in self.rec["images"]:
            elf = self.out / n / "loader.elf"
            if not elf.exists():
                continue
            syms = subprocess.run(["nm", str(elf)], capture_output=True, text=True, check=True).stdout
            self.assertEqual("nat034_stub" in syms, n == "loader-diag-xnu-ckpt2", n)
            self.assertEqual("mk_ckpt2_hold" in syms, n == "loader-diag-xnu-ckpt2", n)
            self.assertEqual("nat031_stub" in syms, n == "loader-diag-xnu-ckpt", n)
            self.assertEqual("mk_ckpt_hold" in syms, n in ("loader-diag-xnu-ckpt", "loader-diag-xnu-ckpt2"), n)

    def test_the_stub_the_stack_and_the_log_fit_one_2_mib_block_at_both_measured_s_boot_bases(self):
        """A recorded fact about this link, not a proof about the phone: S-Boot started the earlier images at 0x800a0000 (the ADT images) and
        0x801a0000 (the canary of run 003); the base varies with the image. Native run 009 (decision 0017) then measured this very image at
        0x80180000 (the reported stub PA 0x80191d30 minus the stub's offset 0x11d30), so the three bases seen so far are tested. loader_jump maps one
        2 MiB block 1:1 around the stub; at either base the stub, the stack, loader_log and the end of the loader (the payload copy starts at
        _end) lie in one aligned 2 MiB block. The prologue clears SCTLR_EL1.M and C first anyway, so this is margin, not the mechanism."""
        s = NM_SIZES(self.elf())
        offs = {n: s[n][0] for n in ("nat034_stub", "_stack_top", "loader_log", "_end")}
        self.assertLess(offs["_end"], 0x40000, offs)
        for base in (0x800a0000, 0x80180000, 0x801a0000):
            blocks = {n: (base + o) >> 21 for n, o in offs.items()}
            self.assertEqual(len(set(blocks.values())), 1, (hex(base), {n: hex(base + o) for n, o in offs.items()}))
            self.assertEqual((base + offs["_end"] - 1) >> 21, blocks["nat034_stub"], hex(base))      # the last byte of the loader too


DECISION = ROOT / "docs/decisions/0017-nat034-loader-diag-xnu-ckpt2-single-run-2026-11-11.md"
DRIVER = HERE / "session_xnu_ckpt2.py"


@unittest.skipUnless(DRIVER.exists() and (ROOT / "artifacts/nat-034/package-001/recovery.img").exists() and (ROOT / "devices/recovery/backups/2026-11-10/recovery.img").exists(),
                     "the NAT-034 driver, its package or the stock RECOVERY backup is missing")
class SessionGate(unittest.TestCase):
    """The gated driver: with no owner decision file it stops before any adb call, in every mode, after checking its pinned hashes."""
    def run_driver(self, *mode):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "bin").mkdir()
            fake = t / "bin/adb"
            fake.write_text("#!/bin/sh\necho \"$@\" >> %s\nexit 1\n" % (t / "adb-calls"))
            fake.chmod(0o755)
            env = {"PATH": f"{t / 'bin'}:/usr/bin:/bin", "HOME": str(t)}
            r = subprocess.run([sys.executable, str(DRIVER), "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def test_no_decision_no_adb_in_any_mode(self):
        if DECISION.exists():
            self.skipTest("the owner decision exists: the gate is open")
        for mode in ((), ("--execute",), ("--restore",)):
            r, calls, rep = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(calls, "", mode)
            self.assertEqual(rep["outcome"], "stopped")
            self.assertIn("owner decision 0017 is missing", rep["error"])
            self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))

    def test_pinned_hashes_are_those_of_the_package(self):
        src = DRIVER.read_text()
        pkg = json.loads((ROOT / "artifacts/nat-034/package-001/package.json").read_text())
        for h in (pkg["recovery_sha256"], pkg["source_image_sha256"], pkg["stock_sha256"]):
            self.assertIn(h, src)
        payload = ROOT / "artifacts/nat-034/build-001/loader-diag-xnu-ckpt2/Image.payload"
        if payload.exists():
            self.assertIn("CANARY_LEN=%d" % payload.stat().st_size, src)
        self.assertEqual(src.count("reboot','recovery'"), 1)
        self.assertNotIn("fastboot", src.lower())


if __name__ == "__main__":
    unittest.main()
