#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-036 host tests: the resumable C-checkpoint stub of loader-diag-xnu-ckpt3 (ckpt3.c, ckpt3_stub.S, the CKPT3 report, the
loader patch and the image). Evidence kind: host-test. Nothing here runs on, or is sent to, the phone. `make check` does not run
this file; run it with an interpreter that has capstone and unicorn (the NAT-033/035 scratch virtualenv) and zig and cc on PATH:

    python3 -I docs/procedures/nat-036/test_nat036.py            (NAT036_LONG=1 adds the 17-stop run to checkpoint 16, about 2 min)

Layers, each skips itself, and says why, when what it needs is missing:
  Words        the constants hard-coded in ckpt3.h/ckpt3.c against the payload bytes and against the payload's own symbols.
  Ckpt3Host    ckpt.c + ckpt3.c built for the host (alignment sanitizer) on the real payload bytes: the list check, the install
               checks (each refuses and writes nothing), the decision table, the slot / flag writes.
  C3Chain      the aarch64 stub + ckpt.c + ckpt3.c compiled as the loader build compiles them, run by the NAT-033/035 model on
               the payload kernel from its entry: assembly stops 1..5, the NAT-032/034 resume, then every C stop of the list
               resumed by the compiled stub itself. The end state is compared with a run that was never stopped.
  C3Controls   the same run with every restore instruction of the C tail removed in turn, and with every register the tail does
               not restore filled with junk (and tainted, so that a read of one is a recorded violation).
  AdtMask      the loader patch's expression, compiled and evaluated, fed to the kernel's own ml_get_cpu_number_local in the model.
  Ckpt3Marker  the report routines against the fake DECON0, decoded independently; the display budget against the 83 s watchdog.
  Build        the image builds, twice identically; the loader source differs from the checkpoint-2 loader in three hunks only;
               no SIMD, no misaligned access, the stub fits one 2 MiB block at the three S-Boot bases seen.
The model has no caches, no TLB, no exceptions and no real memory attributes. What it shows is the register/memory contract of the
stub and what the kernel does with it in the model; it is not a measurement of the S24 (README, hazards)."""
import ctypes, difflib, importlib.util, itertools, json, os, re, shutil, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = Path(os.environ["NAT036_SRC"]) if os.environ.get("NAT036_SRC") else HERE / "src"      # a mutated copy of src/ for the mutation checks
N22, N35 = ROOT / "docs/procedures/nat-022", ROOT / "docs/procedures/nat-035"
SRC22 = N22 / "src"
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


t31 = _load("test_nat031", N22 / "test_nat031.py")          # helpers only (its own tests are not run from here)
dec, bld, ap, capstone = t31.dec, t31.bld, t31.ap, t31.capstone
dec3 = _load("nat036_decode3", HERE / "decode3.py")
VIRT, SLOT_VA, SITES, M64 = t31.VIRT, t31.SLOT_VA, t31.SITES, t31.M64
NEEDS_PAYLOAD, zig_ok, NM_SIZES = t31.NEEDS_PAYLOAD, t31.zig_ok, t31.nm_sizes
try:
    sys.path.insert(0, str(N35))
    import cresume as cr
    HAVE_MODEL = capstone is not None and PAYLOAD.exists() and all(p.exists() for p in (cr.a5.PAYLOAD, cr.a5.KERNEL, cr.a5.ANALYSIS, cr.li.FIXED_PAYLOAD))
    WHY = "the NAT-033/035 model inputs are missing"
except Exception as e:          # capstone / unicorn / local artifacts
    cr, HAVE_MODEL, WHY = None, False, repr(e)
model = unittest.skipUnless(HAVE_MODEL and zig_ok(), "model, zig or the local NAT-020/034 artifacts missing: %s" % (WHY,))

ORDER = (10, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16)
DEFAULT_STOPS = (11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16)
SHORT_STOPS = (11, 30, 35, 12, 44, 13, 14, 15, 16)
MASK = {"BAD_TTBR0": 1 << 12, "FINAL": 1 << 13, "BAD_STATE": 1 << 14}
RC = {"LIST_BAD": 3, "BLOCK_BAD": 4, "JUMP_BAD": 5, "SETTTB_BAD": 6, "FLAG_BAD": 7}
RESUME_ASM, RESUME_C, HOLD = 1, 2, 3
JUMP_VA, SETTTB_VA, FLAG_VA = 0xfffffff00744f1cc, 0xfffffff0074428bc, 0xfffffff007d77009
NOP = 0xd503201f
UPTO = 0x3e00000                                           # the window prefix that holds loader_jump, _set_mmu_ttb and the flag byte

STOP_ASM = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


# ------------------------------------------------------------------------------------------------------------------ Words
@NEEDS_PAYLOAD
class Words(unittest.TestCase):
    """The constants of ckpt3.h / ckpt3.c are the payload's bytes. They fail if the payload kernel is rebuilt."""
    @classmethod
    def setUpClass(cls):
        cls.payload = ap.Payload(str(PAYLOAD))
        cls.image = t31.window_prefix(cls.payload, UPTO)
        cls.c = (SRC / "ckpt3.c").read_text()
        cls.h = (SRC / "ckpt3.h").read_text()

    def table(self, name):
        m = re.search(r"%s\[\w+\] = \{(.*?)\};" % name, self.c, re.S)
        return [int(x, 16) for x in re.findall(r"0x[0-9a-f]{8}", m.group(1))]

    def macro(self, name):
        return int(re.search(r"#define %s\s+(0x[0-9a-fA-F]+|\d+)[uU]?" % name, self.h).group(1), 0)

    def words(self, va, n):
        return list(struct.unpack_from("<%dI" % n, bytes(self.image), va - VIRT))

    def test_the_jump_and_set_ttb_tables_equal_the_payload(self):
        self.assertEqual(len(self.table("nat036_jump_words")), 27)
        self.assertEqual(self.table("nat036_jump_words"), self.words(JUMP_VA, 27))
        self.assertEqual(self.table("nat036_setttb_words"), self.words(SETTTB_VA, 4))
        self.assertEqual((self.macro("NAT036_JUMP_VA"), self.macro("NAT036_SETTTB_VA"), self.macro("NAT036_FLAG_VA")), (JUMP_VA, SETTTB_VA, FLAG_VA))
        self.assertEqual((self.macro("NAT036_JUMP_EPILOGUE"), self.macro("NAT036_JUMP_WORDS"), self.macro("NAT036_SETTTB_WORDS")), (0x4c, 27, 4))

    @unittest.skipUnless(HAVE_MODEL, "needs the payload's symbol table (NAT-035 model inputs)")
    def test_the_addresses_are_the_payloads_own_symbols(self):
        v = cr.a5.Image().vals
        self.assertEqual((v["_loader_jump"], v["_set_mmu_ttb"], v["_loader_return_entered"]), (JUMP_VA, SETTTB_VA, FLAG_VA))

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_epilogue_the_stub_returns_through_is_the_early_return_epilogue(self):
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        ep = JUMP_VA + 0x4c
        ins = [(i.mnemonic, i.op_str) for i in md.disasm(bytes(self.image[ep - VIRT:ep - VIRT + 12]), ep)]
        self.assertEqual(ins, [("ldp", "x29, x30, [sp, #0x30]"), ("add", "sp, sp, #0x40"), ("ret", "")])
        gad = [(i.mnemonic, i.op_str) for i in md.disasm(bytes(self.image[SETTTB_VA - VIRT:SETTTB_VA - VIRT + 16]), SETTTB_VA)]
        self.assertEqual(gad, [("dsb", "ish"), ("msr", "ttbr0_el1, x0"), ("isb", ""), ("ret", "")])
        # the early return is taken on the flag: ldrb (flag) ... tbnz, i.e. the 11th and 12th instruction
        ins = [(i.mnemonic, i.op_str) for i in md.disasm(bytes(self.image[JUMP_VA - VIRT + 36:JUMP_VA - VIRT + 48]), JUMP_VA + 36)]
        self.assertEqual([m for m, _ in ins], ["ldrb", "tbnz", "mrs"])
        self.assertEqual(ins[1][1].split(", ")[-1], "#" + hex(JUMP_VA + 0x4c), ins)

    def test_the_flag_byte_is_zero_in_the_copied_image_and_in_the_file(self):
        self.assertEqual(self.image[FLAG_VA - VIRT], 0)
        for vm, vs, fo, fs in self.payload.segs:
            if vm <= FLAG_VA < vm + vs:
                self.assertTrue(FLAG_VA - vm >= fs or self.payload.b[fo + FLAG_VA - vm] == 0)


# ------------------------------------------------------------------------------------------------------------------ host
class S31(ctypes.Structure):
    _fields_ = [("slot_pa", ctypes.c_uint64), ("pa_minus_va", ctypes.c_uint64), ("expect", ctypes.c_uint32), ("mask", ctypes.c_uint32),
                ("arrivals", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


class S36(ctypes.Structure):
    _fields_ = [("s", S31), ("stops", ctypes.c_void_p), ("nstops", ctypes.c_uint32), ("idx", ctypes.c_uint32), ("last", ctypes.c_uint32),
                ("pad", ctypes.c_uint32), ("kernel_ttbr0", ctypes.c_uint64), ("flag_pa", ctypes.c_uint64)]


class D36(ctypes.Structure):
    _fields_ = [("action", ctypes.c_uint32), ("next", ctypes.c_uint32), ("final", ctypes.c_uint32), ("resume_pa", ctypes.c_uint64)]


def ref_list_ok(stops):
    """Independent statement of the rule: 1..24 entries, each in ORDER, strictly increasing in program order."""
    if not 1 <= len(stops) <= 24 or any(s not in ORDER for s in stops):
        return False
    return all(ORDER.index(a) < ORDER.index(b) for a, b in zip(stops, stops[1:]))


@NEEDS_PAYLOAD
class Ckpt3Host(unittest.TestCase):
    """ckpt.c + ckpt3.c (NAT031_HOST) on the real payload bytes. gcc's alignment sanitizer traps any misaligned access."""
    STUB, STUB_END = 0x9e2d80000, 0x9e2d80140

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        so = Path(cls.tmp.name) / "ckpt3.so"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DNAT031_HOST", "-fsanitize=alignment", "-fsanitize-undefined-trap-on-error",
                        "-shared", "-fPIC", f"-I{SRC}", f"-I{SRC22}", str(SRC22 / "ckpt.c"), str(SRC / "ckpt3.c"), "-o", str(so)], check=True)
        lib = cls.lib = ctypes.CDLL(str(so))
        u64, u32, p = ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p
        lib.nat036_list_ok.argtypes = [p, u32]; lib.nat036_list_ok.restype = ctypes.c_int
        lib.nat036_check.argtypes = [ctypes.c_size_t, u64, u64, u64, p, u32, ctypes.POINTER(u32)]; lib.nat036_check.restype = ctypes.c_int
        lib.nat036_prepare.argtypes = [p, ctypes.c_size_t, u64, u64, u64, p, u32, ctypes.POINTER(u32)]; lib.nat036_prepare.restype = ctypes.c_int
        lib.nat036_decide.argtypes = [p, u64, u64, u64, u64, p]
        lib.nat036_set_next.argtypes = [p, u32]
        lib.nat036_clear_flag.argtypes = [u64]
        cls.payload = ap.Payload(str(PAYLOAD))
        cls.image = t31.window_prefix(cls.payload, UPTO)

    def setUp(self):
        self.buf = (ctypes.c_char * len(self.image)).from_buffer_copy(bytes(self.image))
        self.base = ctypes.addressof(self.buf)

    def arr(self, stops):
        a = (ctypes.c_uint8 * max(len(stops), 1))(*stops)
        self._keep = getattr(self, "_keep", []) + [a]
        return a

    def list_ok(self, stops):
        a = self.arr(stops)
        return self.lib.nat036_list_ok(ctypes.addressof(a) if stops else None, len(stops))

    def check(self, stops=DEFAULT_STOPS, stub=STUB, end=STUB_END):
        a, bad = self.arr(stops), ctypes.c_uint32(99)
        return self.lib.nat036_check(self.base, VIRT, stub, end, ctypes.addressof(a), len(stops), ctypes.byref(bad)), bad.value

    def prepare(self, stops):
        self.setUp()                                                               # a fresh image: prepare writes the slot, and nat031_check wants the original
        st, bad = S36(), ctypes.c_uint32(99)
        a = self.arr(stops)
        rc = self.lib.nat036_prepare(ctypes.byref(st), self.base, VIRT, self.STUB, self.STUB_END, ctypes.addressof(a), len(stops), ctypes.byref(bad))
        self.assertEqual(rc, 0)
        return st

    def decide(self, st, x2, x3, sctlr=0x3454593c, ttbr0=0x9e15ae000):
        d = D36()
        self.lib.nat036_decide(ctypes.byref(st), x2, x3, sctlr, ttbr0, ctypes.byref(d))
        return d.action, d.next, d.final, d.resume_pa

    def asm_walk(self, st, upto, ttbr0=0x9e15ae000):
        for n in range(1, upto + 1):
            act = self.decide(st, 2, n, ttbr0=ttbr0)
            self.assertEqual(act[0], RESUME_ASM, n)

    # --- the list ------------------------------------------------------------------------------------
    def test_list_rule_against_an_independent_statement_exhaustively_up_to_three_entries(self):
        alphabet = list(ORDER) + [0, 1, 5, 17, 21, 36, 255]
        for n in (1, 2, 3):
            for stops in itertools.product(alphabet, repeat=n):
                self.assertEqual(bool(self.list_ok(list(stops))), ref_list_ok(list(stops)), stops)

    def test_list_rule_special_cases(self):
        self.assertFalse(self.list_ok([]))
        self.assertFalse(self.lib.nat036_list_ok(None, 3))
        self.assertTrue(self.list_ok(list(DEFAULT_STOPS)) and self.list_ok(list(SHORT_STOPS)) and self.list_ok(list(ORDER)))
        self.assertFalse(self.list_ok(list(ORDER) + [16] * 7))                   # more than 24
        self.assertFalse(self.list_ok(list(DEFAULT_STOPS) + [17]))               # a checkpoint after arm_vm_init's TTBR0 change
        self.assertFalse(self.list_ok([11, 11]))                                  # a stop twice
        self.assertFalse(self.list_ok([30, 11]))                                  # out of program order
        self.assertFalse(self.list_ok([12, 40, 30]))
        self.assertFalse(self.list_ok([5, 11]))                                   # 5 is the assembly checkpoint, not a C stop

    # --- install checks ------------------------------------------------------------------------------
    def test_a_good_image_passes_and_prepare_fills_the_slot_like_nat031(self):
        self.assertEqual(self.check()[0], 0)
        st = self.prepare(DEFAULT_STOPS)
        self.assertEqual((st.nstops, st.idx, st.last, st.kernel_ttbr0, st.s.expect, st.s.mask, st.s.arrivals), (17, 0, 0, 0, 1, 0, 0))
        self.assertEqual(st.flag_pa, self.base + FLAG_VA - VIRT)
        w = struct.unpack_from("<4Q", bytes(self.buf), SLOT_VA - VIRT)
        self.assertEqual((w[1], w[2]), (self.STUB, 1))                              # slot[1] = the stub, slot[2] = the first checkpoint
        self.assertEqual((w[0], w[3]), (0x545352444c554e58, (self.base - VIRT) & M64))   # the "XNULDRST" tag stays; slot[3] = pa_minus_va

    def refuses(self, expect_rc, mutate, **kw):
        before = bytes(self.buf)
        mutate()
        mid = bytes(self.buf)
        st, bad = S36(), ctypes.c_uint32(99)
        a = self.arr(kw.get("stops", DEFAULT_STOPS))
        rc = self.lib.nat036_prepare(ctypes.byref(st), self.base, VIRT, kw.get("stub", self.STUB), kw.get("end", self.STUB_END), ctypes.addressof(a),
                                     len(kw.get("stops", DEFAULT_STOPS)), ctypes.byref(bad))
        self.assertEqual(rc, expect_rc)
        self.assertEqual(bytes(self.buf), mid, "a refused install wrote to the image")
        return before

    def test_every_refusal_writes_nothing(self):
        j, t, f = JUMP_VA - VIRT, SETTTB_VA - VIRT, FLAG_VA - VIRT
        for name, rc, mut, kw in (
                ("empty list", RC["LIST_BAD"], lambda: None, {"stops": []}),
                ("out of order", RC["LIST_BAD"], lambda: None, {"stops": [12, 11]}),
                ("after 16", RC["LIST_BAD"], lambda: None, {"stops": [11, 17]}),
                ("straddling stub", RC["BLOCK_BAD"], lambda: None, {"stub": 0x9e2dfff00, "end": 0x9e2e00100}),      # 0x9e2e00000: a 2 MiB boundary that is not a 4 MiB one
                ("stub one byte over", RC["BLOCK_BAD"], lambda: None, {"stub": 0x9e2dfff00, "end": 0x9e2e00001}),
                ("empty stub", RC["BLOCK_BAD"], lambda: None, {"stub": 0x9e2d80000, "end": 0x9e2d80000}),
                ("first jump word", RC["JUMP_BAD"], lambda: self.flip(j), {}),
                ("last jump word", RC["JUMP_BAD"], lambda: self.flip(j + 4 * 26), {}),
                ("epilogue word", RC["JUMP_BAD"], lambda: self.flip(j + 0x4c), {}),
                ("set_ttb first", RC["SETTTB_BAD"], lambda: self.flip(t), {}),
                ("set_ttb ret", RC["SETTTB_BAD"], lambda: self.flip(t + 12), {}),
                ("flag set", RC["FLAG_BAD"], lambda: self.set_byte(f, 1), {})):
            self.setUp()
            self.refuses(rc, mut, **kw)

    def flip(self, off):
        w = struct.unpack_from("<I", self.buf, off)[0]
        struct.pack_into("<I", self.buf, off, w ^ 0x10)

    def set_byte(self, off, v):
        self.buf[off] = bytes([v])

    def test_a_stub_ending_exactly_at_a_block_boundary_is_inside_the_block(self):
        self.assertEqual(self.check(stub=0x9e2dfff00, end=0x9e2e00000)[0], 0)
        self.assertEqual(self.check(stub=0x9e2e00000, end=0x9e2e00100)[0], 0)
        self.assertEqual(self.check(stub=0x9e2dfff00, end=0x9e2e00001)[0], RC["BLOCK_BAD"])

    def test_the_nat031_checks_still_come_first(self):
        for site in range(5):
            self.setUp()
            off = SITES[site] - VIRT + 4 * 8
            w = struct.unpack_from("<I", self.buf, off)[0]
            struct.pack_into("<I", self.buf, off, w ^ 0x20)
            rc, bad = self.check()
            self.assertEqual((rc, bad), (2, site + 1), site)
        self.setUp()
        struct.pack_into("<Q", self.buf, SLOT_VA - VIRT + 8, 7)                    # slot[1] is not what the kernel's image starts with
        self.assertEqual(self.check()[0], 1)

    # --- decisions ----------------------------------------------------------------------------------
    def test_the_walk_through_the_assembly_stops_the_cp5_resume_and_every_c_stop(self):
        st = self.prepare(SHORT_STOPS)
        base = st.s.pa_minus_va
        for n in range(1, 5):
            self.assertEqual(self.decide(st, 2, n), (RESUME_ASM, n + 1, 0, (SITES[n - 1] + 60 + base) & M64), n)
        act = self.decide(st, 2, 5, ttbr0=0x9e15ae000)
        self.assertEqual(act, (RESUME_ASM, 11, 0, (SITES[4] - 28 + base) & M64))
        self.assertEqual((st.kernel_ttbr0, st.s.expect, st.s.mask, st.s.arrivals, st.last, st.idx), (0x9e15ae000, 11, 0x3e, 5, 5, 0))
        for i, s in enumerate(SHORT_STOPS[:-1]):
            self.assertEqual(self.decide(st, 2, s, sctlr=0x3454593d, ttbr0=0x9e2279000), (RESUME_C, SHORT_STOPS[i + 1], 0, 0), s)
            self.assertEqual((st.last, st.idx, st.s.expect, st.kernel_ttbr0), (s, i + 1, SHORT_STOPS[i + 1], 0x9e15ae000), s)
        self.assertEqual(self.decide(st, 2, 16, sctlr=0x3454593d), (HOLD, 0, 1, 0))
        self.assertEqual((st.s.mask, st.s.arrivals, st.last), (0x3e | MASK["FINAL"], 5 + len(SHORT_STOPS), 16))
        self.assertEqual(self.decide(st, 2, 16, sctlr=0x3454593d)[0], HOLD)        # a second arrival at the last stop is a hold again, never a resume

    def test_the_cp5_ttbr0_is_validated_before_it_is_used(self):
        for bad in (0, 0x1, 0x2, 0xffe, 0x9e15ae800, 0x9e15ae004, 0x0000000000000fff, 0xffff000000000000):
            st = self.prepare(SHORT_STOPS)
            self.asm_walk(st, 4)
            act = self.decide(st, 2, 5, ttbr0=bad)
            self.assertEqual(act[0], HOLD, hex(bad))
            self.assertEqual((st.kernel_ttbr0, st.s.mask & MASK["BAD_TTBR0"], st.s.expect), (0, MASK["BAD_TTBR0"], 5), hex(bad))
            # with nothing captured, a C stop is not resumed either
            self.assertEqual(self.decide(st, 2, 11, sctlr=0x3454593d)[0], HOLD)
            self.assertTrue(st.s.mask & (1 << 10))
        for ok in (0x9e15ae000, 0x1000, 0x9e15ae001 & ~1 | 0, 0x00a09e15ae000 & ~0xfff, (7 << 48) | 0x9e15ae000):
            st = self.prepare(SHORT_STOPS)
            self.asm_walk(st, 4)
            self.assertEqual(self.decide(st, 2, 5, ttbr0=ok)[0], RESUME_ASM, hex(ok))
            self.assertEqual(st.kernel_ttbr0, ok)

    def test_checkpoint_5_arriving_with_the_mmu_on_holds_without_a_resume(self):
        st = self.prepare(SHORT_STOPS)
        self.asm_walk(st, 4)
        act = self.decide(st, 2, 5, sctlr=0x3454593d)                              # the MMU is on: not the arrival the capture is valid for
        self.assertEqual(act[0], HOLD)
        self.assertEqual((st.kernel_ttbr0, st.s.expect, st.s.mask & MASK["FINAL"]), (0, 5, 0))
        self.assertEqual(self.decide(st, 2, 11, sctlr=0x3454593d)[0], HOLD)         # and no C stop is resumed after it

    def test_a_c_stop_in_a_state_the_resume_does_not_understand_holds_and_says_so(self):
        st = self.prepare(SHORT_STOPS)
        self.asm_walk(st, 5)
        self.assertEqual(self.decide(st, 2, 11, sctlr=0x3454593c)[0], HOLD)        # MMU off at a C stop: not loader_jump's private-table arrival
        self.assertEqual((st.s.mask & MASK["BAD_STATE"], st.s.mask & MASK["FINAL"], st.idx, st.last), (MASK["BAD_STATE"], 0, 0, 11))

    def test_everything_unexpected_holds_with_the_nat031_masks_and_never_resumes(self):
        for walked in (0, 3, 5):
            for x2, x3, bit in ((1, 0x96000045, 1 << 8), (0, 0, 1 << 9), (3, 1, 1 << 10), (M64, 11, 1 << 10), (2, 99, 1 << 10), (2, 17, 1 << 10), (2, 0, 1 << 10)):
                st = self.prepare(SHORT_STOPS)
                self.asm_walk(st, walked)
                before = st.s.mask
                self.assertEqual(self.decide(st, x2, x3, sctlr=0x3454593d)[0], HOLD, (walked, x2, x3))
                self.assertEqual(st.s.mask, before | bit, (walked, x2, x3))
        # the right x3 with the wrong reason must not be taken for the stop (x3 is an ESR when x2 = 1)
        st = self.prepare(SHORT_STOPS)
        self.asm_walk(st, 5)
        for x2 in (1, 0, 3):
            self.assertEqual(self.decide(st, x2, 11, sctlr=0x3454593d)[0], HOLD, x2)
        self.assertEqual((st.idx, st.s.expect, st.s.mask & MASK["FINAL"]), (0, 11, 0))

    def test_stops_out_of_order_or_before_cp5_are_holds(self):
        for first in (12, 30, 16, 11):
            st = self.prepare(SHORT_STOPS)
            self.asm_walk(st, 4)
            self.assertEqual(self.decide(st, 2, first, sctlr=0x3454593d)[0], HOLD)  # a C stop before checkpoint 5
            self.assertEqual(st.kernel_ttbr0, 0)
        st = self.prepare(SHORT_STOPS)
        self.asm_walk(st, 5)
        for skip in (12, 44, 16):                                                  # the next expected is 11
            self.assertEqual(self.decide(st, 2, skip, sctlr=0x3454593d)[0], HOLD, skip)
        self.assertEqual(self.decide(st, 2, 11, sctlr=0x3454593d)[0], RESUME_C)    # and the expected one is still accepted after those holds
        self.assertEqual(self.decide(st, 2, 11, sctlr=0x3454593d)[0], HOLD)        # a repeat of a stop already passed

    def test_a_one_stop_list_resumes_5_then_holds_at_that_stop(self):
        st = self.prepare([12])
        self.asm_walk(st, 4)
        self.assertEqual(self.decide(st, 2, 5)[:2], (RESUME_ASM, 12))
        self.assertEqual(self.decide(st, 2, 12, sctlr=0x3454593d), (HOLD, 0, 1, 0))

    # --- the two memory writes ------------------------------------------------------------------------
    def test_set_next_writes_one_aligned_word_in_slot_2(self):
        st = self.prepare(SHORT_STOPS)
        before = bytes(self.buf)
        self.lib.nat036_set_next(ctypes.byref(st.s), 30)
        after = bytes(self.buf)
        self.assertEqual([o for o in range(0, len(before), 8) if before[o:o + 8] != after[o:o + 8]], [SLOT_VA - VIRT + 16])
        self.assertEqual(struct.unpack_from("<Q", after, SLOT_VA - VIRT + 16)[0], 30)

    def test_clear_flag_writes_exactly_the_flag_byte(self):
        self.buf[FLAG_VA - VIRT] = b"\x01"
        before = bytes(self.buf)
        self.lib.nat036_clear_flag(self.base + FLAG_VA - VIRT)
        after = bytes(self.buf)
        self.assertEqual([o for o in range(len(before)) if before[o] != after[o]], [FLAG_VA - VIRT])
        self.assertEqual(after[FLAG_VA - VIRT], 0)


# ------------------------------------------------------------------------------------------------------------------ chain
_TMP = tempfile.TemporaryDirectory()
_ELF = {}
LOADER = range(0x9e2d80000, 0x9e2e20000)


def compile36(stops, tag=""):
    """The loader-side objects of the image, compiled as nat-022/build.py compiles them, linked at the model's stub address with the
    test double for the marker routines. Cached by stop list."""
    key = (tuple(stops), tag)
    if key in _ELF:
        return _ELF[key]
    t = Path(_TMP.name) / ("s" + "_".join(map(str, stops)) + tag)
    t.mkdir()
    objs = []
    flags = [f for f in bld.FLAGS if f != "-mgeneral-regs-only"]
    for name, src, extra in (("ckpt.c", SRC22 / "ckpt.c", bld.NO_SIMD + ["-DNAT034_IMAGE=1"]),
                             ("ckpt3.c", SRC / "ckpt3.c", bld.NO_SIMD + ["-DNAT036_STOP_LIST=" + ",".join(map(str, stops))]),
                             ("mock.c", HERE / "test_support/nat036_mock.c", bld.NO_SIMD),
                             ("ckpt3_stub.S", SRC / "ckpt3_stub.S", []), ("mockbss.S", N22 / "test_support/nat031_mock.S", [])):
        o = t / (name + ".o")
        subprocess.run(["zig", "cc", *flags, *extra, f"-I{SRC}", f"-I{SRC22}", "-c", str(src), "-o", str(o)], check=True)
        objs.append(o)
    elf = t / "stub.elf"
    subprocess.run(["zig", "cc", "-target", "aarch64-freestanding", "-static", "-nostdlib", "-Wl,--build-id=none", "-Wl,-e,nat036_stub",
                    f"-Wl,-T,{HERE / 'test_support/nat036_mock.ld'}", *objs, "-o", str(elf)], check=True)
    secdata, syms = t31.KernelChain.read_elf(elf)
    _ELF[key] = (elf, secdata, syms)
    return _ELF[key]


@model
class Harness(unittest.TestCase):
    """Shared plumbing for the model runs."""
    BASE = 0x9de400000
    RET, BAD = BASE + 0x4a00000, BASE + 0x4a10000
    JUNK = 0xbad0bad0bad0bad0

    @classmethod
    def setUpClass(cls):
        cls.img = cr.a5.Image()

    def new_sim(self, stops, text_patch=None, adt_reg=0, tag="", id_zero=False):
        elf, secdata, syms = compile36(stops, tag)
        sim = cr.Assumed(names=self.img, adt_reg=adt_reg, id_zero=id_zero)
        for a, d in secdata:
            sim.write_pa(a, d)
        for pa, word in (text_patch or {}).items():
            sim.write_pa(pa, struct.pack("<I", word))
        sim.write_pa(self.BAD, b"\xff" * 8)
        for i, a in enumerate([self.BASE, VIRT, self.BAD]):
            sim.x[i] = a
        sim.sp_el[1] = syms["_stack_top"]; sim.spsel = 1; sim.x[30] = self.RET
        sim.pc = syms["nat036_install"]
        sim.run(stop_pcs={self.RET}, limit=200000)
        self.assertEqual((sim.x[0], struct.unpack("<I", sim.read_pa(self.BAD, 4))[0]), (0, 0), "the compiled installer refused the real payload")
        sim.x = [0] * 31; sim.x[0] = sim.ba_pa
        sim.sp_el = [0, 0]; sim.spsel = 0
        sim.n = sim.z = sim.c = sim.v = 0
        sim.pc = sim.entry_pc; sim.steps = 0
        # what S-Boot left in the registers the stub reads (the model has no reset value; the kernel writes them all before the C stops)
        sim.sr.update({"ttbr1_el1": 0xdead0001000, "tcr_el1": 0x1234, "vbar_el1": 0xbeef000, "ttbr0_el1": 0xdead0002000})
        return sim, syms

    @staticmethod
    def after_bl(sim, syms):
        for i in range(80):
            w = struct.unpack("<I", sim.read_pa(syms["nat036_stub"] + 4 * i, 4))[0]
            if w >> 26 == 0b100101:
                return syms["nat036_stub"] + 4 * (i + 1)
        raise AssertionError("no bl in the stub")

    def drive(self, sim, syms, hostile=False, taint=True, limit=3000000):
        """Run to the hold. With hostile=True every arrival, right after nat036_ckpt_c returns (x0, x1 are its result), has all other
        registers x2..x30 overwritten with junk, and (taint=True) marked as clobbered: the model records a violation for any read of
        one before it is written. A resume that depended on a register the stub does not restore is then a failure, not a coincidence."""
        hold, after = syms["mk_ckpt3_hold"], self.after_bl(sim, syms)
        while True:
            sim.run(stop_pcs={after, hold}, limit=limit)
            if sim.pc == hold:
                break
            if hostile:
                for r in range(2, 31):
                    sim.x[r] = self.JUNK + r
                    if taint:
                        sim.taint[r] = {0, 1, 2, 3}
                sim.steps += 1
                sim.step()                                                  # the cbnz that tests x1 (the mode) runs with the real x1
                if taint and sim.x[1]:
                    sim.taint[1] = {0, 1, 2, 3}                              # C resume: x1 is not restored either
            else:
                sim.steps += 1
                sim.step()
        try:                                                                # let the double record the hold, then it spins
            sim.run(limit=sim.steps + 80)
        except Exception as e:
            self.assertIn("step-limit", str(e))
        return sim

    def real_violations(self, sim, syms):
        """sim.violations without the reads that are only the stub's own frame save: `stp`/`str` between the stub's first instruction and its
        `bl`, which store whatever the 31 registers hold (junk included) and use none of it. Any other read of a clobbered register,
        in particular every instruction of the C tail and of the kernel, stays."""
        lo, hi = syms["nat036_stub"], self.after_bl(sim, syms)
        return [v for v in sim.violations if not (lo <= v[0] < hi and v[2].split()[0] in ("stp", "str"))]

    def log(self, sim, syms):
        n = struct.unpack("<I", sim.read_pa(syms["mock_n"], 4))[0]
        return [struct.unpack("<16Q", sim.read_pa(syms["mock_log"] + 128 * i, 128)) for i in range(n)]

    def held(self, sim, syms):
        return struct.unpack("<I", sim.read_pa(syms["mock_held"], 4))[0]

    @staticmethod
    def summary(rec):
        return dict(x2=rec[0], x3=rec[1], sctlr=rec[2], ttbr1=rec[3], tcr=rec[4], vbar=rec[5], sp=rec[9], x0=rec[10], x1=rec[11], kttbr0=rec[12],
                    mask=rec[13] & 0xffffffff, arrivals=rec[13] >> 32, last=rec[14] & 0xffffffff, nstops=rec[14] >> 32, kind=rec[15])

    def ram_outside_loader(self, a, b):
        return [(hex(k + o), ) for k in sorted(set(a.pages) | set(b.pages)) if k not in LOADER
                for o in range(0, 4096, 8) if a.pages.get(k, bytes(4096))[o:o + 8] != b.pages.get(k, bytes(4096))[o:o + 8]]


@model
class C3Chain(Harness):
    """The compiled stub resumes the payload kernel stop after stop. The model is the NAT-033/035 one: no TLB, no caches."""
    STOPS = (11, 30, 31, 32, 33, 34, 35, 12)
    _run = {}

    @classmethod
    def runs(cls):
        if not cls._run:
            h = cls("run_marker")
            h.setUpClass.__func__(cls)
            chain, syms = h.new_sim(cls.STOPS)
            h.drive(chain, syms)
            direct, dsyms = h.new_sim([cls.STOPS[-1]], tag="direct")
            h.drive(direct, dsyms)
            cls._run = dict(chain=chain, syms=syms, direct=direct, dsyms=dsyms, h=h,
                            ref=cr.reference(cls.img if hasattr(cls, "img") else cr.a5.Image(), cls.STOPS[-1], adt_reg=0))
        return cls._run

    def run_marker(self):          # a no-op test method name so that the harness instance can be built outside unittest
        pass

    def test_the_chain_stops_at_1_to_5_then_at_every_c_stop_of_the_list_and_holds_at_the_last(self):
        r = self.runs()
        recs = [self.summary(x) for x in self.log(r["chain"], r["syms"])]
        self.assertEqual(self.held(r["chain"], r["syms"]), 1)
        self.assertEqual([(x["x2"], x["x3"]) for x in recs], [(2, n) for n in (1, 2, 3, 4, 5) + self.STOPS])
        self.assertEqual([x["kind"] for x in recs], [1] * (len(recs) - 1) + [2])                       # every arrival but the last is a pass; the last is the hold
        self.assertEqual([x["arrivals"] for x in recs], list(range(1, len(recs) + 1)))
        self.assertEqual([x["last"] for x in recs], [1, 2, 3, 4, 5] + list(self.STOPS))
        self.assertEqual([x["sctlr"] & 1 for x in recs], [0] * 5 + [1] * len(self.STOPS))             # M clear at assembly stops, set at C stops
        self.assertEqual(recs[-1]["mask"], 0x3e | MASK["FINAL"])
        self.assertTrue(all(x["nstops"] == len(self.STOPS) for x in recs))
        self.assertEqual(recs[0]["kttbr0"], 0)                                                         # not captured before checkpoint 5 ...
        self.assertEqual({x["kttbr0"] for x in recs[5:]}, {0x9e15ae000})                              # ... the kernel's own table afterwards, the model's value
        self.assertEqual({x["ttbr1"] for x in recs[5:]}, {r["ref"].sr["ttbr1_el1"]})
        self.assertEqual(r["chain"].violations, [])

    def test_every_c_arrival_is_through_loader_jumps_private_table_with_the_mmu_on(self):
        r = self.runs()
        recs = [self.summary(x) for x in self.log(r["chain"], r["syms"])][5:]
        self.assertEqual({x["sctlr"] for x in recs}, {0x3454593d})                                     # the arrival value, as run 009 measured it (bit 5/7 aside)
        self.assertEqual(len({x["sp"] for x in recs}), 1)                                              # loader_jump's frame is at the same place at every stop

    def test_the_entry_state_at_the_last_stop_equals_an_uninterrupted_run(self):
        r = self.runs()
        c = cr.compare_entry(r["ref"], r["chain"])
        self.assertEqual(c["strict"], {}, c)
        self.assertEqual(len(r["chain"].jump_entries), 5 * 0 + len(self.STOPS))                         # one loader_jump entry per C stop
        self.assertTrue(all(e["daif_masked"] for e in r["chain"].jump_entries))

    def test_the_end_state_equals_a_run_of_the_same_loader_that_was_never_stopped(self):
        r = self.runs()
        a, b = r["direct"], r["chain"]
        self.assertEqual(len(a.jump_entries), 1)
        self.assertEqual(cr.compare_entry(a, b)["strict"], {})
        self.assertEqual({k: (a.sr.get(k), b.sr.get(k)) for k in set(a.sr) | set(b.sr) if a.sr.get(k) != b.sr.get(k)}, {})
        self.assertEqual(self.ram_outside_loader(a, b), [], "the resumed kernel's RAM differs from the unstopped run")
        la, lb = self.summary(self.log(a, r["dsyms"])[-1]), self.summary(self.log(b, r["syms"])[-1])
        for k in ("x2", "x3", "sctlr", "ttbr1", "tcr", "vbar", "sp", "x0", "x1", "kttbr0"):
            self.assertEqual(la[k], lb[k], k)

    def test_the_direct_run_is_a_real_comparison_not_the_same_run_twice(self):
        r = self.runs()
        self.assertEqual(len(self.log(r["direct"], r["dsyms"])), 6)                                    # 1..5 and the one C stop
        self.assertEqual(len(self.log(r["chain"], r["syms"])), 5 + len(self.STOPS))
        self.assertGreater(r["chain"].steps, r["direct"].steps)                                        # the chain ran the stub's resumes in between

    def test_the_flag_and_the_slot_are_what_the_resume_left(self):
        r = self.runs()
        sim = r["chain"]
        self.assertEqual(sim.read_pa(sim.pa_of_kva(FLAG_VA), 1), b"\x01")                              # set by the last loader_jump entry, as in any run
        slot = struct.unpack("<4Q", sim.read_pa(sim.pa_of_kva(SLOT_VA), 32))
        self.assertEqual(slot[2], self.STOPS[-1])                                                      # the last next-stop value stored; the kernel never writes it

    def test_the_log_the_double_recorded_names_the_hold_once(self):
        r = self.runs()
        self.assertEqual(sum(1 for x in self.log(r["chain"], r["syms"]) if x[15] == 2), 1)


@model
@unittest.skipUnless(os.environ.get("NAT036_LONG"), "NAT036_LONG=1: the 17-stop run to checkpoint 16 takes about two minutes")
class C3LongChain(Harness):
    def long_run(self, stops):
        sim, syms = self.new_sim(stops, id_zero=True)                          # cpu_init's three ID-register reads (ccsidr/clidr/id_aa64dfr0) read 0, as in NAT-035
        self.drive(sim, syms, hostile=True)
        recs = [self.summary(x) for x in self.log(sim, syms)]
        self.assertEqual([x["x3"] for x in recs], [1, 2, 3, 4, 5] + list(stops))
        self.assertEqual(recs[-1]["kind"], 2)
        self.assertEqual(recs[-1]["mask"], 0x3e | MASK["FINAL"])
        self.assertEqual(self.real_violations(sim, syms), [])
        ref = cr.reference(self.img, stops[-1], adt_reg=0, id_zero=True)
        self.assertEqual(cr.compare_entry(ref, sim)["strict"], {})
        direct, dsyms = self.new_sim([stops[-1]], tag="direct", id_zero=True)
        self.drive(direct, dsyms)
        self.assertEqual(self.ram_outside_loader(direct, sim), [])
        self.assertTrue(all(e["daif_masked"] for e in sim.jump_entries))
        self.assertEqual(len(sim.jump_entries), len(stops))
        return recs

    def test_all_17_stops_to_checkpoint_16_with_the_hostile_registers(self):
        self.long_run(DEFAULT_STOPS)

    def test_the_9_stop_candidate_list_to_checkpoint_16_with_the_hostile_registers(self):
        """The list the first image is built with: the kernel passes checkpoints 31-34, 40-43 without stopping (the slot holds the next stop), so
        this is a different run of the kernel from the 17-stop one, not a prefix of it."""
        recs = self.long_run(SHORT_STOPS)
        k = recs[-1]
        print("NAT036-9STOP final record: x0=%#x x1=%#x sp=%#x kttbr0=%#x sctlr=%#x ttbr1=%#x tcr=%#x vbar=%#x arrivals=%d" % (
            k["x0"], k["x1"], k["sp"], k["kttbr0"], k["sctlr"], k["ttbr1"], k["tcr"], k["vbar"], k["arrivals"]))


# ------------------------------------------------------------------------------------------------------------------ controls
@model
class C3Controls(Harness):
    """Every restore instruction of the C tail is needed, and the stub survives a hostile register file. A control that fails to detect a
    removal would mean the test cannot see what it claims to; the unmodified stub is run through the same harness first."""
    STOPS = (11, 30)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ref = cr.reference(cls.img, cls.STOPS[-1], adt_reg=0)

    def outcome(self, text_patch=None, hostile=True):
        """('ok'|'fault:KIND'|'diff'|'violation'|'wrong-log', detail)."""
        sim, syms = self.new_sim(self.STOPS, text_patch=text_patch)
        try:
            self.drive(sim, syms, hostile=hostile, limit=200000)
        except Exception as e:
            return "fault:" + (getattr(e, "kind", None) or str(e)[:40]), None
        recs = [self.summary(x) for x in self.log(sim, syms)]
        if [x["x3"] for x in recs] != [1, 2, 3, 4, 5, 11, 30] or self.held(sim, syms) != 1:
            return "wrong-log", [x["x3"] for x in recs]
        if self.real_violations(sim, syms):
            return "violation", self.real_violations(sim, syms)[:2]
        c = cr.compare_entry(self.ref, sim)
        return ("diff", c["strict"]) if c["strict"] else ("ok", None)

    def tail(self):
        """Address and text of every instruction of the C tail (after `br x9`, up to and including `br x12`)."""
        elf, secdata, syms = compile36(self.STOPS)
        sim = cr.Assumed(names=self.img, adt_reg=0)
        for a, d in secdata:
            sim.write_pa(a, d)
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        base = syms["nat036_stub"]
        words = [struct.unpack("<I", sim.read_pa(base + 4 * i, 4))[0] for i in range(120)]
        first = words.index(0xd61f0120) + 1                                    # br x9 ends the assembly tail
        last = words.index(0xd61f0180)                                         # br x12 ends the C tail
        return [(base + 4 * i, next(md.disasm(struct.pack("<I", words[i]), 0))) for i in range(first, last + 1)]

    def test_the_unmodified_stub_survives_the_hostile_registers_without_a_violation(self):
        self.assertEqual(self.outcome(), ("ok", None))
        self.assertEqual(self.outcome(hostile=False), ("ok", None))

    def test_every_restore_and_setup_instruction_of_the_c_tail_is_detected_when_removed(self):
        tail = self.tail()
        # what the tail must do, by instruction: the register restores, the SP, the two returns values, the SCTLR write, the branch
        must = {"ldp x18, x19": "x18/x19", "ldp x20, x21": "x20/x21", "ldp x22, x23": "x22/x23", "ldp x24, x25": "x24/x25", "ldp x26, x27": "x26/x27",
                "ldr x28": "x28", "ldr x11": "SCTLR value", "ldr x10": "kernel SP", "ldp x0, x30": "TTBR0 + return address", "ldr x12": "gadget",
                "mov sp, x10": "SP switch", "msr sctlr_el1, x11": "MMU back on", "mov x9, x0": "block pointer"}
        found = {}
        for pa, ins in tail:
            key = ins.mnemonic + " " + ins.op_str.split(", [")[0]
            for k in must:
                if key.startswith(k) and k not in found:
                    found[k] = pa
        self.assertEqual(set(found), set(must), "the tail changed: %s" % sorted(set(must) - set(found)))
        results = {}
        for k, pa in found.items():
            results[k] = self.outcome({pa: NOP})
            self.assertNotEqual(results[k][0], "ok", "removing `%s` (%s) was not detected" % (k, must[k]))
        self.assertEqual(len(results), 13)

    def test_every_register_the_c_tail_restores_comes_back_with_the_value_it_had_at_the_entry(self):
        """The kernel's own x18..x28 may be equal to each other at a stop (a slot swapped with its neighbour would then go unseen), so at the first
        C arrival x18..x28 are replaced by distinct values before the stub runs. At the gadget (the last instruction of the C tail, `br x12`) they
        must be those values again, the SP the entry SP and x0 the captured TTBR0."""
        sim, syms = self.new_sim(self.STOPS)
        entry, hold, after = syms["nat036_stub"], syms["mk_ckpt3_hold"], self.after_bl(sim, syms)
        gadget = self.tail()[-1][0]
        want = sp = None
        for _ in range(40):
            sim.run(stop_pcs={entry}, limit=400000)
            self.assertEqual(sim.pc, entry)
            if not sim.sr["sctlr_el1"] & 1:                                      # assembly stop: let the stub resume it, as in the chain
                sim.steps += 1
                sim.step()
                continue
            for r in range(18, 29):
                sim.x[r] = 0x5eed0000 + 0x101 * r
            want = {r: sim.x[r] for r in range(18, 29)}
            sp = sim.sp_el[sim.spsel]
            sim.steps += 1
            sim.step()
            sim.run(stop_pcs={after}, limit=400000)
            for r in range(2, 31):
                sim.x[r] = self.JUNK + r
                sim.taint[r] = {0, 1, 2, 3}
            sim.steps += 1
            sim.step()                                                            # cbnz x1, 2f: the C resume
            sim.run(stop_pcs={gadget, hold}, limit=400000)
            self.assertEqual(sim.pc, gadget, "the stub held instead of resuming at the first C stop")
            break
        self.assertTrue(want, "no C arrival in 40 stub entries")
        self.assertEqual({r: sim.x[r] for r in want}, want)
        self.assertEqual(sim.sp_el[sim.spsel], sp)
        self.assertEqual(sim.x[0], 0x9e15ae000)

    def test_the_stack_frame_is_exactly_the_registers_and_the_sp_and_the_stub_never_stores_outside_it(self):
        """The frame is `sub x10, x10, #N` below _stack_top; its stores are the 31 registers and the kernel SP. A frame one slot too small
        would put the last stores above _stack_top, into whatever follows the stack: invisible to the model (RAM is RAM there)."""
        lines = (SRC / "ckpt3_stub.S").read_text().splitlines()
        head = []
        for l in lines:
            l = re.sub(r"/\*.*?\*/", "", l).strip()
            if l.startswith("bl\t"):
                break
            head.append(l)
        size = [int(m.group(1), 0) for l in head for m in [re.match(r"sub\s+x10, x10, #(\w+)$", l)] if m]
        self.assertEqual(len(size), 1)
        stores = [(int(m.group(2), 0), 16 if m.group(1) == "stp" else 8) for l in head for m in [re.match(r"(stp|str)\s+.*\[sp, #(\w+)\]$", l)] if m]
        self.assertEqual(max(o + n for o, n in stores), size[0])
        self.assertEqual(sorted(o for o, _ in stores), sorted(list(range(0, 240, 16)) + [240, 248]))
        self.assertEqual(size[0], 8 * 32)

    def test_the_barriers_cannot_be_checked_in_the_model(self):
        """dsb / tlbi / isb have no effect the model can see: removing them changes nothing. That is the limit of this layer and it is
        listed in the README hazards (stale TLB entry, instruction synchronisation) instead of being claimed as tested."""
        tail = self.tail()
        barrier = [(pa, ins.mnemonic + " " + ins.op_str) for pa, ins in tail if ins.mnemonic in ("dsb", "isb", "tlbi")]
        self.assertEqual([t for _, t in barrier], ["dsb sy", "tlbi vmalle1", "dsb nsh", "isb ", "isb "])
        self.assertEqual({self.outcome({pa: NOP}) for pa, _ in barrier}, {("ok", None)})

    def test_the_prologue_and_the_assembly_tail_are_nat034s_text(self):
        def code(path, sym):
            out = []
            for l in Path(path).read_text().splitlines():
                l = re.sub(r"/\*.*?\*/", "", l).strip()
                if l and not l.startswith("/*") and not l.startswith("*"):
                    out.append(re.sub(r"\s+", " ", l.replace(sym, "natXXX")))
            return out
        a, b = code(N22 / "src/ckpt2_stub.S", "nat034"), code(SRC / "ckpt3_stub.S", "nat036")
        cut = b.index("2:")
        b = [l for l in b[:cut] if l != "cbnz x1, 2f" and l != ".globl natXXX_stub_end"]
        self.assertEqual(b, a)

    def test_the_c_tail_loads_everything_it_needs_before_the_mmu_comes_back_on(self):
        """After `msr sctlr_el1, x11` the MMU is on with loader_jump's private table, which maps only the stub's 2 MiB block: the stub's code
        and nothing else (README section 2). The only instructions after the msr are an isb and the branch."""
        tail = self.tail()
        names = [ins.mnemonic for _, ins in tail]
        i = max(k for k, (_, ins) in enumerate(tail) if ins.mnemonic == "msr")
        self.assertEqual(names[i + 1:], ["isb", "br"])
        loads = [k for k, m in enumerate(names) if m in ("ldr", "ldp")]
        self.assertTrue(loads and max(loads) < names.index("dsb") < i)               # every load is before the first barrier, hence before the msr
        self.assertFalse([m for m in names[i:] if m in ("ldr", "ldp", "str", "stp")])


# ------------------------------------------------------------------------------------------------------------------ ADT
@model
class AdtMask(Harness):
    """The loader patch's own expression, compiled and evaluated, fed to the kernel's ml_get_cpu_number_local() in the model."""
    TOPO = 0xfffffff0071c2000

    def patched_expression(self):
        if not LOADER_SRC.exists():
            self.skipTest("the NAT-020 build-003 source is missing")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "src"
            shutil.copytree(LOADER_SRC, root, ignore=shutil.ignore_patterns("out", ".git"))
            subprocess.run([sys.executable, "-I", str(HERE / "patch_loader3.py"), str(root)], check=True, capture_output=True)
            s = (root / "shim/e1s-xnu/loader.c").read_text()
        lines = [l for l in s.splitlines() if "adt_set_boot_cpu_mpidr(" in l]
        self.assertEqual(len(lines), 1, lines)
        rest = lines[0].split("p->adt_size, ", 1)[1]
        depth = 0
        for i, ch in enumerate(rest):                                              # the third argument: up to the parenthesis that closes the call
            depth += (ch == "(") - (ch == ")")
            if depth < 0:
                return rest[:i]
        self.fail(lines[0])

    @staticmethod
    def evaluate(expr, mpidr):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "e.c"
            src.write_text('#include <stdio.h>\n#include <stdint.h>\nstruct { uint64_t mpidr; } gi = { %s };\nint main(void) { printf("%%u\\n", (unsigned)(%s)); return 0; }\n' % (hex(mpidr) + "ULL", expr))
            subprocess.run(["cc", "-o", str(Path(t) / "e"), str(src)], check=True)
            return int(subprocess.run([str(Path(t) / "e")], capture_output=True, text=True, check=True).stdout)

    def lookup(self, adt_reg):
        sim = cr.reference(self.img, 14, adt_reg=adt_reg)
        phys = sim.read(sim.read(self.TOPO + 0x780, 8) + 4, 4) & 0xFFFFFFFF
        sim.x[30] = cr.a5.STUB
        sim.pc = self.img.vals["_ml_get_cpu_number_local"]
        sim.run(stop_pcs={cr.a5.STUB, self.img.vals["_Assert"]}, limit=sim.steps + 5000)
        return phys, sim.sr["mpidr_el1"] & 0xFFFF, sim.pc == self.img.vals["_Assert"], sim.x[0] & 0xFFFFFFFF

    def test_the_value_the_patched_loader_writes_makes_the_kernels_cpu_lookup_succeed(self):
        expr = self.patched_expression()
        self.assertIn("0xffff", expr)
        for mpidr in (0x80000000, 0x80000100, 0x81000203):                         # RES1 bit 31 alone, and values with affinity fields set
            self.assertEqual(self.evaluate(expr, mpidr), mpidr & 0xffff, hex(mpidr))
        value = self.evaluate(expr, cr.li.ASSUMED_MPIDR)
        phys, mp16, asserted, x0 = self.lookup(value)
        self.assertEqual((phys, asserted, x0), (mp16, False, 0))

    def test_the_old_expression_is_the_assertion(self):
        phys, mp16, asserted, _ = self.lookup(cr.li.ASSUMED_MPIDR & 0xFFFFFFFF)
        self.assertNotEqual(phys, mp16)
        self.assertTrue(asserted)


# ------------------------------------------------------------------------------------------------------------------ marker
@unittest.skipUnless(zig_ok() and PAYLOAD.exists(), "zig or the payload is missing")
class Ckpt3Marker(unittest.TestCase):
    """What the stub draws (markerlib3.c against the fake DECON0), decoded independently by decode.py/decode3.py."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.exe = t / "host_mk3"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DMK_HOST=1", "-DMK_TRIG=1", "-DMK_LOADER=1", "-DMK_XNU_CKPT=1", "-DNAT031_HOST",
                        f"-I{SRC}", f"-I{SRC22}", str(SRC / "markerlib3.c"), str(SRC22 / "ckpt.c"), str(SRC / "ckpt3.c"), str(HERE / "test_support/host_mk3.c"),
                        "-o", str(cls.exe)], check=True)

    def go(self, n, stops, seq, full=False):
        out = Path(self.tmp.name) / "fb.bin"
        p = subprocess.run([str(self.exe), "ckpt3", str(n), str(out), "0x113", "0x3063", ",".join(map(str, stops)), seq, *(["full"] if full else [])],
                           capture_output=True, text=True)
        self.assertIn(p.returncode, (0, 6), p.stdout[-300:] + p.stderr)
        ev = [l.split() for l in p.stdout.splitlines()]
        frames = [dec.parse_frame(int(e[1], 16)) for e in ev if e[0] == "DRAW"]
        self.assertTrue(frames and all(frames))
        return ev, frames

    @staticmethod
    def seq(stops):
        return ",".join(["2:%d" % n for n in range(1, 6)] + ["2:%d" % s for s in stops])

    def test_the_framebuffer_after_every_draw_decodes_to_the_frame_that_was_drawn(self):
        """What the camera sees is the framebuffer, not the frame word the harness logs: after each draw the independent raw decoder must read
        exactly the frame just drawn. A pass that redrew only the bands that differ from a wrong `prev` would leave the previous frame's lit bands
        on screen and every DRAW event would still look right."""
        stops = (11, 30, 35, 12)
        _, frames = self.go(60, stops, self.seq(stops))
        out = Path(self.tmp.name) / "fb.bin"
        self.assertGreaterEqual(len(frames), 40)
        for n in range(1, 41):
            _, fr = self.go(n, stops, self.seq(stops))
            self.assertEqual(dec.decode_raw(out.read_bytes()), frames[n - 1], "after draw %d" % n)
            self.assertEqual(fr[n - 1], frames[n - 1])

    def test_one_frame_per_pass_and_the_pass_counts_arrivals_and_the_checkpoint(self):
        stops = DEFAULT_STOPS
        ev, frames = self.go(500, stops, self.seq(stops))
        passes = [(f["data"] >> 8, f["data"] & 0xff) for f in frames if f["kind"] == 13 and f["idx"] == 0]
        want = [(i + 1, n) for i, n in enumerate((1, 2, 3, 4, 5) + stops)]
        self.assertEqual(passes[:len(want) - 1], want[:-1])                      # every pass but the last: exactly one PASS frame each, nothing else drawn
        self.assertEqual(passes[len(want) - 1], want[-1])
        self.assertEqual(dec3.passes(frames)[:len(want)], want)
        first_hold = next(i for i, f in enumerate(frames) if f["kind"] == 3)     # the hold opens with the stage frame
        self.assertEqual(first_hold, len(want) - 1)                              # i.e. the passes drew len(want) - 1 frames and nothing but PASS frames
        self.assertTrue(all(f["kind"] == 13 and f["idx"] == 0 for f in frames[:first_hold]))

    def test_the_final_report_carries_every_value_the_run_is_about(self):
        stops = (11, 30, 31, 32, 33, 34, 35, 12)
        ev, frames = self.go(600, stops, self.seq(stops))
        d = dec3.describe3(frames)
        k = d["ckpt3"]
        self.assertEqual((k["arrivals"], k["last_checkpoint"], k["stops_in_list"]), (13, 12, 8))
        self.assertEqual((k["sp_lo48"], k["kernel_ttbr0_lo48"], k["x0_lo48"], k["x1_lo32"]), ("0xfff00a1b2c40", "0x0009e15ae000", "0x0009e1f90a00", "0x00a1b2c3"))
        self.assertEqual((d["ckpt"]["x2"], d["ckpt"]["x3"], d["ckpt"]["arrival_mask"]), (2, 12, 0x3e | MASK["FINAL"]))
        self.assertIn("final: the last stop of the list was reached (the intended hold)", d["ckpt"]["arrivals_seen"])
        self.assertEqual((d["ckpt"]["sctlr_el1_lo32"], d["ckpt"]["ttbr1_el1_lo48"], d["ckpt"]["vbar_el1_lo16"], d["ckpt"]["tcr_el1_lo32"]),
                         ("0x3454593d", "0x0009e2b6f000", "0x7000", "0xa51a251a"))
        self.assertEqual(dec3.stops_missed(dec3.passes(frames), stops), [])

    def test_the_values_come_first_so_that_a_cut_off_report_still_has_them(self):
        stops = (11, 12)
        ev, frames = self.go(80, stops, self.seq(stops))
        hold = frames[frames.index(next(f for f in frames if f["kind"] == 3)):]
        order = [(f["kind"], f["idx"]) for f in hold]
        head = order[:16]
        self.assertEqual(head, [(3, 0), (13, 0), (11, 0), (11, 1), (13, 1)] + [(13, i) for i in range(2, 13)])
        for i in range(0, 2 * 12):                                                # a second round is identical: the report repeats, nothing is added
            pass
        self.assertEqual(order[:len(order) // 2][:5], order[:5])

    def test_a_missed_frame_is_recovered_from_the_next_pass(self):
        stops = (11, 30, 31, 12)
        ev, frames = self.go(500, stops, self.seq(stops))
        seen = dec3.passes(frames)
        thinned = [p for p in seen if p[0] not in (7, 8)]                         # the camera missed the 7th and 8th arrival
        self.assertEqual(dec3.stops_missed(thinned, stops), [])                   # (arrivals, last) of a later pass accounts for them
        self.assertEqual(dec3.stops_missed([p for p in seen if p[0] <= 6], stops), [30, 31, 12])

    def test_an_exception_before_the_last_stop_reports_esr_elr_far(self):
        stops = (11, 30)
        seq = "2:1,2:2,2:3,2:4,2:5,2:11,1:0x96000045"
        ev, frames = self.go(500, stops, seq)
        d = dec3.describe3(frames)
        self.assertEqual((d["ckpt"]["x2"], d["ckpt"]["x3"]), (1, 0x45))             # x3 is the ESR: only its low byte is in the REGS frame
        self.assertEqual((d["esr"], d["elr"], d["far"]), ("0x0000000096000045", "0xfffffff00743e0b0", "0x00000000deadbeef"))
        self.assertTrue(d["ckpt"]["arrival_mask"] & (1 << 8))
        self.assertEqual(d["ckpt3"]["last_checkpoint"], 11)
        self.assertNotIn("sp_lo48", d["ckpt3"])

    def test_unexpected_arrivals_hold_with_the_report_and_no_final_bit(self):
        stops = (11, 30)
        for seq, bit in (("2:1,2:2,2:3,2:4,2:5,2:12", 1 << 10), ("2:1,2:2,2:3,2:4,2:5,2:11,2:11", 1 << 10), ("2:11", 1 << 10), ("0:0", 1 << 9)):
            ev, frames = self.go(300, stops, seq)
            d = dec3.describe3(frames)
            self.assertTrue(d["ckpt"]["arrival_mask"] & bit, seq)
            self.assertFalse(d["ckpt"]["arrival_mask"] & MASK["FINAL"], seq)

    def test_every_draw_is_followed_by_a_decon_kick(self):
        ev, frames = self.go(300, (11, 30), self.seq((11, 30)))
        draws = [i for i, e in enumerate(ev) if e[0] == "DRAW"]
        for a, b in zip(draws, draws[1:]):
            seg = ev[a + 1:b]
            self.assertTrue(seg and seg[0][:2] == ["RD", "20"], seg)
            self.assertTrue({e[1] for e in seg if e[0] == "WR"} <= {"30", "50"})

    # Timeline. Measured: PRE_JUMP is drawn 19.5 s after the first frame (runs 006-009); in run 009 the five assembly passes ended about
    # 41 s after the run started at 2.7 s per two-frame pass, so the first pass starts at 41 - 5 * 2.7 = 27.5 s; a frame shown for 1.2 s plus
    # its draw and kick is 1.35 s; the loader's display watchdog ends it at 83 s. The kernel's own time between stops is below 0.2 s per stop in
    # the model's step counts and is ignored: the figures are a budget, not a prediction.
    T_FIRST_PASS, FRAME, WATCHDOG = 27.5, 1.35, 83.0

    def timeline(self, stops):
        ev, frames = self.go(900, stops, self.seq(stops), full=True)
        pre = next(i for i, f in enumerate(frames) if f["kind"] == 3 and f["idx"] == 0 and f["data"] == 0x40)
        passes = [i for i, f in enumerate(frames) if f["kind"] == 13 and f["idx"] == 0]
        n_arrivals = 5 + len(stops)
        t = lambda i: self.T_FIRST_PASS + (i - passes[0] + 1) * self.FRAME
        first_hold = next(i for i, f in enumerate(frames[pre:], pre) if f["kind"] == 3 and f["idx"] == 0 and f["data"] == 0x51)
        x0_last = next(i for i, f in enumerate(frames[first_hold:], first_hold) if f["kind"] == 13 and f["idx"] == 12)
        sctlr_last = next(i for i, f in enumerate(frames[first_hold:], first_hold) if f["kind"] == 11 and f["idx"] == 3)
        return dict(passes_end=t(passes[n_arrivals - 2]), values_end=t(x0_last), sysregs_end=t(sctlr_last), frames_in_passes=n_arrivals - 1)

    def test_display_budget_default_list(self):
        r = self.timeline(DEFAULT_STOPS)
        self.assertLess(r["passes_end"], 60)                                        # the 22 passes are over by ~57 s
        self.assertLess(r["values_end"], 78)                                        # SP, kernel TTBR0, x1, x0, the mask and the list: all on screen once ...
        self.assertGreater(self.WATCHDOG - r["values_end"], 4)                      # ... with a margin; a second round would not fit (see the short list)
        self.assertLess(r["sysregs_end"], self.WATCHDOG)

    def test_display_budget_short_list_has_room_for_a_second_round(self):
        r = self.timeline(SHORT_STOPS)
        self.assertLess(r["passes_end"], 50)
        self.assertLess(r["values_end"], 70)
        self.assertGreater(self.WATCHDOG - r["values_end"], 12)


# ------------------------------------------------------------------------------------------------------------------ build
@unittest.skipUnless(zig_ok() and LOADER_SRC.exists() and PAYLOAD.exists(), "zig, the NAT-020 build-003 source or the payload is missing")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "o"
        cls.out2 = Path(cls.tmp.name) / "o2"
        for o in (cls.out, cls.out2):
            r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--out", str(o), "--loader-source", str(LOADER_SRC)], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr[-800:]
        cls.rec = json.loads((cls.out / "build.json").read_text())
        cls.name = "loader-diag-xnu-ckpt3"
        cls.d = cls.out / cls.name

    def test_the_image_is_reproducible(self):
        a, b = self.rec, json.loads((self.out2 / "build.json").read_text())
        self.assertEqual(a["images"], b["images"])
        self.assertEqual(a["image_payloads"], b["image_payloads"])

    def test_the_image_header_and_the_payload(self):
        img = (self.d / "Image").read_bytes()
        self.assertEqual(img[56:60], b"ARM\x64")
        self.assertEqual(struct.unpack_from("<Q", img, 8)[0], 0x80000)
        self.assertEqual(struct.unpack_from("<Q", img, 16)[0], len(img))               # image_size = where the payload starts
        pl = (self.d / "Image.payload").read_bytes()
        fixed = (self.d / "payload.adt8.bin").read_bytes()
        self.assertEqual(pl[len(img):], fixed)
        self.assertEqual(struct.unpack_from("<Q", pl, 16)[0], len(pl))
        self.assertEqual(pl[:16] + pl[24:len(img)], img[:16] + img[24:])                # the append changes image_size and nothing else
        self.assertEqual(fixed[:8], b"SWEETXNU")
        self.assertEqual(self.rec["stops"], list(DEFAULT_STOPS))
        self.assertEqual((self.rec["device_used"], self.rec["flashed"], self.rec["kind"]), (False, False, "host-test"))

    def test_the_loader_source_differs_from_the_checkpoint_2_loader_in_three_hunks_only(self):
        p22 = _load("nat022_patch_loader_t", N22 / "patch_loader.py")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "src"
            shutil.copytree(LOADER_SRC, root, ignore=shutil.ignore_patterns("out", ".git"))
            p22.main(root, trig_hold=True, adt_aligned=True, xnu_entry=False, ckpt=False, ckpt2=True)
            old = (root / "shim/e1s-xnu/loader.c").read_text().splitlines()
        new = (self.d / "source/shim/e1s-xnu/loader.c").read_text().splitlines()
        diff = [l for l in difflib.unified_diff(old, new, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        self.assertEqual([l for l in diff if l[0] == "-"], [
            '-#include "ckpt2.h"',
            "-\tif (adt_set_boot_cpu_mpidr(adt_pa, p->adt_size, (uint32_t)gi.mpidr)) {",
            "-\t\tstatic const char *const nat031_msg[] = {",
            '-\t\t\t"XNU checkpoint slot check failed", "XNU checkpoint site 1 check failed",',
            '-\t\t\t"XNU checkpoint site 2 check failed", "XNU checkpoint site 3 check failed",',
            '-\t\t\t"XNU checkpoint site 4 check failed", "XNU checkpoint site 5 check failed" };',
            "-",
            "-\t\tif (nat034_install(win_base, p->virt_base, &nat031_bad))",
            "-\t\t\treturn fail(nat031_msg[nat031_bad]);"])
        self.assertEqual([l for l in diff if l[0] == "+"], [
            '+#include "ckpt3.h"',
            "+\tif (adt_set_boot_cpu_mpidr(adt_pa, p->adt_size, (uint32_t)(gi.mpidr & 0xffff))) {",
            "+\t\tint nat036_rc = nat036_install(win_base, p->virt_base, &nat031_bad);",
            "+",
            "+\t\tif (nat036_rc)",
            "+\t\t\treturn fail(nat036_msg(nat036_rc, nat031_bad));"])
        # everything else of the loader tree is the checkpoint-2 tree's
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "src"
            shutil.copytree(LOADER_SRC, root, ignore=shutil.ignore_patterns("out", ".git"))
            p22.main(root, trig_hold=True, adt_aligned=True, xnu_entry=False, ckpt=False, ckpt2=True)
            for f in sorted((root / "shim/e1s-xnu").iterdir()):
                if f.is_file() and f.name != "loader.c":
                    self.assertEqual((self.d / "source/shim/e1s-xnu" / f.name).read_bytes(), f.read_bytes(), f.name)

    def test_the_earlier_sources_are_copied_unchanged(self):
        for f in ("marker.h", "markerlib.c", "ckpt.h", "ckpt.c", "ckpt2.h"):
            self.assertEqual((self.d / "source/shim/e1s-xnu" / f).read_bytes(), (SRC22 / f).read_bytes(), f)
        for f in ("marker3.h", "markerlib3.c", "ckpt3.h", "ckpt3.c", "ckpt3_stub.S"):
            self.assertEqual((self.d / "source/shim/e1s-xnu" / f).read_bytes(), (SRC / f).read_bytes(), f)

    def elf(self):
        return self.d / "loader.elf"

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_nat036_code_has_no_simd_and_no_misaligned_access(self):
        sizes = NM_SIZES(self.elf())
        img = (self.d / "Image").read_bytes()
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM); md.detail = True
        simd = re.compile(r"^[vqdsbh]\d+$")
        for fn in ("nat036_list_ok", "nat036_check", "nat036_prepare", "nat036_decide", "nat036_set_next", "nat036_clear_flag", "nat036_report",
                   "nat036_install", "nat036_msg", "nat036_ckpt_c", "mk_ckpt3_pass", "mk_ckpt3_hold"):
            a, n = sizes[fn]
            self.assertGreater(n, 0, fn)
            for ins in md.disasm(img[a:a + n], a):
                names = {md.reg_name(r) for r in list(ins.regs_read) + list(ins.regs_write)}
                names |= {md.reg_name(op.reg) for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG and op.reg}
                self.assertFalse(any(simd.match(x or "") for x in names), (fn, hex(ins.address), ins.mnemonic))
        stub, end = sizes["nat036_stub"][0], sizes["nat036_stub_end"][0]
        self.assertGreater(end - stub, 0x80)
        for ins in md.disasm(img[stub:end], stub):
            self.assertFalse(any(simd.match(md.reg_name(op.reg) or "") for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG), (ins.mnemonic, ins.op_str))
        r = subprocess.run([sys.executable, "-I", str(N22 / "scan_unaligned.py"), str(self.d / "Image"), "--elf", str(self.elf())], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.splitlines()), (0, ["total 0"]))

    def test_the_stub_is_sixteen_byte_aligned_and_the_stack_too(self):
        s = NM_SIZES(self.elf())
        self.assertEqual((s["nat036_stub"][0] % 16, s["_stack_top"][0] % 16), (0, 0))
        self.assertLess(s["nat036_stub_end"][0] - s["nat036_stub"][0], 0x200)

    def test_the_stub_and_the_loader_fit_one_2_mib_block_at_the_three_s_boot_bases_seen(self):
        """Recorded facts about this link: S-Boot started earlier images at 0x800a0000, 0x801a0000 and (run 009) 0x80180000. loader_jump maps ONE
        2 MiB block 1:1 around the stub; the installer also refuses a stub that straddles one. The stub's code and its end, the stack, the log
        and the end of the loader lie in one aligned block at each base. The prologue clears SCTLR_EL1.M/C first anyway; this is margin."""
        s = NM_SIZES(self.elf())
        offs = {n: s[n][0] for n in ("nat036_stub", "nat036_stub_end", "_stack_top", "loader_log", "_end")}
        self.assertLess(offs["_end"], 0x40000, offs)
        for base in (0x800a0000, 0x80180000, 0x801a0000):
            blocks = {n: (base + o - (1 if n.endswith("_end") else 0)) >> 21 for n, o in offs.items()}
            self.assertEqual(len(set(blocks.values())), 1, (hex(base), {n: hex(base + o) for n, o in offs.items()}))

    def test_only_this_image_has_the_nat036_symbols(self):
        syms = subprocess.run(["nm", str(self.elf())], capture_output=True, text=True, check=True).stdout
        for sym in ("nat036_stub", "nat036_ckpt_c", "mk_ckpt3_hold", "mk_ckpt3_pass"):
            self.assertIn(sym, syms)
        for sym in ("nat034_stub", "nat031_stub", "mk_ckpt2_hold"):
            self.assertNotIn(sym, syms)

    def test_a_list_that_is_not_in_program_order_does_not_build_into_an_image_that_installs(self):
        """build.py accepts any --stops; the loader's own nat036_list_ok refuses a bad one at run time, before the first write. The refusal is
        covered by Ckpt3Host; this pins that the compiled list is the one asked for."""
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--out", str(Path(t) / "o"), "--loader-source", str(LOADER_SRC), "--stops", "11,30,35"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertEqual(json.loads((Path(t) / "o/build.json").read_text())["stops"], [11, 30, 35])
            self.assertNotEqual(json.loads((Path(t) / "o/build.json").read_text())["images"][self.name]["sha256"], self.rec["images"][self.name]["sha256"])


if __name__ == "__main__":
    unittest.main()
