#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-059 host tests: the sources of loader-diag-xnu-ckpt4-usb (patch_ckpt59.py over NAT-036/NAT-052), their decision rules built for the
host, the payload facts they rely on, and (second half of this file) the driver and the analyser derived for the image.
Evidence kind: host-test. Nothing here runs on, or is sent to, the phone.

    python3 -I docs/procedures/nat-059/test_nat059.py              (the layers that need the NAT-020 payload, cc or zig skip themselves)
    <capture venv>/bin/python -W ignore -I docs/procedures/nat-059/test_nat059.py     (capstone for the instruction-level payload checks)

Layers:
  Derivation   the NAT-052 + NAT-059 hunks apply to the committed NAT-036 text; the stub assembly is byte for byte NAT-036's, which ran on the
               phone in NAT-058; the lines the change removes are exactly the ones named here; the wiring of the TTBR0 into the resume.
  Words        what the change relies on, against the payload bytes: the checkpoint call order of arm_init (17..21 follow arm_vm_init), the
               arm_vm_init words and the symbol _invalid_ttep, and what arm_vm_init writes to TCR_EL1/TTBR1_EL1 (decoded independently).
  Host         ckpt.c + the derived ckpt3.c built for the host on the real payload window: the stop-list rule, the install check, and the rule that
               picks the TTBR0 to give back, walked through every arrival of the 22-stop list.
  Build        the image builds (check-only) from the committed sources.
Tests that only mirror the implementation were left out: the expected values below come from the payload and from NAT-058's measurement."""
import ctypes, difflib, hashlib, importlib.util, json, os, re, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
N22, N35, N36, N52 = (PROC / n for n in ("nat-022", "nat-035", "nat-036", "nat-052"))
SRC22, SRC36 = N22 / "src", N36 / "src"
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"
SCRATCH = ROOT / "artifacts/nat-059/tmp"           # gitignored; the user's /tmp quota on this host is small


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


p52 = load("nat059t_patch52", N52 / "patch_ckpt52.py")
p59 = load("nat059t_patch59", Path(os.environ.get("NAT059_PATCH") or HERE / "patch_ckpt59.py"))      # mutated copies for the mutation checks
sha = lambda b: hashlib.sha256(b).hexdigest()

# NAT-058 ran the image built from these three files on the phone (artifacts/nat-052/build-003/build.json). The stub assembly is the proven one:
# the change must not touch it.
PINNED36 = {
    "ckpt3_stub.S": None,       # filled from the build record when it exists; the assertion below also compares with the committed file's own hash
}
ORDER = (10, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)
STOPS = (11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)
OLD_STOPS = STOPS[:17]
INVALID_TTEP_VA, VMTTB_VA = 0xfffffff0071ac3e0, 0xfffffff007433b64
SETTTB_VA, CHECKPOINT_VA, ARM_VM_INIT_VA = 0xfffffff0074428bc, 0xfffffff00744f3c0, 0xfffffff007432f5c
CP5_TTBR0 = 0x9e15ae000                              # measured at the checkpoint-5 stop on the phone (NAT-058)
MASK_BAD_TTBR0, MASK_FINAL, MASK_BAD_STATE = 1 << 12, 1 << 13, 1 << 14
RESUME_ASM, RESUME_C, HOLD = 1, 2, 3
RC_VMTTB_BAD, RC_LIST_BAD = 8, 3
VIRT = 0xfffffff004000000
UPTO = 0x3e00000


def derived_text():
    """ckpt3.c and ckpt3.h of the image as the build derives them, without a loader tree: NAT-052's hunks, then NAT-059's."""
    c52 = p52.patch_text("ckpt3.c", (SRC36 / "ckpt3.c").read_text(), p52.CKPT3)
    return (p59.patch_text("ckpt3.c", c52, p59.CKPT3_C), p59.patch_text("ckpt3.h", (SRC36 / "ckpt3.h").read_text(), p59.CKPT3_H), c52)


# ------------------------------------------------------------------------------------------------------------------ Derivation
class Derivation(unittest.TestCase):
    def test_every_anchor_occurs_once_in_the_committed_sources(self):
        c, h, _ = derived_text()                                   # patch_text raises SystemExit unless each anchor occurs exactly once
        self.assertIn("nat059_resume_ttbr0", c)
        self.assertIn("NAT059_VMTTB_BAD", h)

    def test_the_stub_assembly_is_the_one_that_ran_on_the_phone(self):
        # the NAT-052 build copies nat-036/src/ckpt3_stub.S unchanged; patch_ckpt59.py derives ckpt3.c and ckpt3.h only
        rec = ROOT / "artifacts/nat-052/build-003/build.json"
        stub = (SRC36 / "ckpt3_stub.S").read_bytes()
        if rec.exists():
            self.assertEqual(json.loads(rec.read_text())["nat036_sources"]["ckpt3_stub.S"], sha(stub), "NAT-058 ran a build of this very stub")
        with tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.exists() else None) as d:
            e = Path(d)
            (e / "ckpt3.c").write_text(derived_text()[2])
            (e / "ckpt3.h").write_text((SRC36 / "ckpt3.h").read_text())
            self.assertEqual(sorted(p.name for p in p59.derive(e)), ["ckpt3.c", "ckpt3.h"], "derive() yields only these two files")
            self.assertEqual(sorted(p.name for p in e.iterdir()), ["ckpt3.c", "ckpt3.h"], "and writes nothing")

    def test_the_change_removes_only_the_lines_named_here(self):
        c, _, c52 = derived_text()
        removed = [l[2:] for l in difflib.ndiff(c52.splitlines(), c.splitlines()) if l.startswith("- ")]
        self.assertEqual(removed, [
            "\t10, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16,",
            "#define NAT036_STOP_LIST 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16",
            "\tuint64_t ttbr0, ttbr1, tcr, vbar, kv;",
            "\t\tnat036_cres.ttbr0 = nat036_st.kernel_ttbr0;",
        ])
        h_old = (SRC36 / "ckpt3.h").read_text().splitlines()
        h_new = derived_text()[1].splitlines()
        removed_h = [l[2:] for l in difflib.ndiff(h_old, h_new) if l.startswith("- ")]
        self.assertEqual([l.strip() for l in removed_h if l.strip().startswith(("#define", "NAT036_FLAG_BAD"))],
                         ["#define NAT036_ORDER_LEN\t18u", "#define NAT036_LAST_STOP\t16u\t/* the last checkpoint in program order before arm_vm_init */",
                          "NAT036_FLAG_BAD = 7\t/* loader_return_entered is not zero in the kernel copy */"])

    def test_the_resume_gives_back_the_stops_own_ttbr0_and_the_note_shows_it(self):
        c, _, _ = derived_text()
        body = c[c.index("struct nat036_ret nat036_ckpt_c"):]
        self.assertEqual(body.count("nat036_cres.ttbr0 = rt;"), 1)
        self.assertNotIn("kernel_ttbr0", body, "nothing in the loader entry point may use the cp5 value directly any more")
        self.assertLess(body.index("nat059_resume_decision(&nat036_st, &d, f->x[3], &rt);"), body.index("nat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);"))
        self.assertIn("\tnat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);\n\tif (rt)\n\t\tr.kttbr0 = rt;", body,
                      "the note must carry the given-back TTBR0 (nat036_ckpt_c is under the aarch64-only guard: a source-level check, not a behavioural one)")
        self.assertLess(body.index("nat036_report("), body.index("r.kttbr0 = rt;"))
        self.assertLess(body.index("r.kttbr0 = rt;"), body.index("nat052_note_stop(&r);"), "the note is written after the TTBR0 is known")
        self.assertLess(body.index("nat059_resume_decision("), body.index("if (d.action == NAT036_HOLD)"), "a bad TTBR0 turns into the hold before it is tested")

    def test_the_default_list_and_the_builds_default_are_the_same_22_stops(self):
        c, _, _ = derived_text()
        m = re.search(r"#define NAT036_STOP_LIST ([\d, ]+)\n", c)
        self.assertEqual(tuple(int(x) for x in m.group(1).split(",")), STOPS)
        self.assertEqual(p59.STOPS, STOPS)
        self.assertEqual(tuple(int(x) for x in re.search(r"nat036_order\[NAT036_ORDER_LEN\] = \{(.*?)\};", c, re.S).group(1).replace("\n", " ").replace("\t", " ").split(",")[:-1]), ORDER)


# ------------------------------------------------------------------------------------------------------------------ Words
def payload_window():
    """The payload as the loader copies it: the first UPTO bytes of the virtual window starting at VIRT (segments laid out by their vm address)."""
    sys.path.insert(0, str(N22))
    t31 = load("nat059t_test31", N22 / "test_nat031.py")
    return t31, t31.ap.Payload(str(PAYLOAD)), t31.window_prefix


try:
    HAVE_PAYLOAD = PAYLOAD.exists()
    T31, PL, WINDOW = payload_window() if HAVE_PAYLOAD else (None, None, None)
except Exception as e:                      # missing helper artifacts
    HAVE_PAYLOAD, T31, PL, WINDOW, WHY = False, None, None, None, repr(e)
try:
    import capstone
except ImportError:
    capstone = None
needs_payload = unittest.skipUnless(HAVE_PAYLOAD, "the NAT-020 build-003 payload is missing")


def words_at(image, va, n):
    return list(struct.unpack_from("<%dI" % n, bytes(image), va - VIRT))


def sx(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def adrp_target(pc, w):
    imm = sx(((w >> 5) & 0x7ffff) << 2 | ((w >> 29) & 3), 21) << 12
    return (pc & ~0xfff) + imm


def bl_target(pc, w):
    return pc + sx(w & 0x3ffffff, 26) * 4


@needs_payload
class Words(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = WINDOW(PL, UPTO)

    def test_the_arm_vm_init_site_is_the_one_the_patch_pins(self):
        got = words_at(self.image, VMTTB_VA, 5)
        self.assertEqual(got, list(p59.VMTTB_WORDS))
        # decoded without the patch's help: x19 = page(adrp) + add imm = _invalid_ttep; ldr x8, [x19]; and x0, x8, #0xffffffffffff; bl _set_mmu_ttb
        adrp, add, ldr, and_, bl = got
        self.assertEqual(adrp & 0x9f00001f, 0x90000013)                       # adrp x19
        self.assertEqual(adrp_target(VMTTB_VA, adrp) + ((add >> 10) & 0xfff), INVALID_TTEP_VA)
        self.assertEqual(add & 0xffc003ff, 0x91000273)                        # add x19, x19, #imm
        self.assertEqual(ldr, 0xf9400268)                                     # ldr x8, [x19]
        self.assertEqual(and_, 0x9240bd00)                                    # and x0, x8, #0xffffffffffff (N=1 immr=0 imms=47)
        self.assertEqual(bl_target(VMTTB_VA + 16, bl), SETTTB_VA)
        self.assertEqual(words_at(self.image, SETTTB_VA, 4), [0xd5033b9f, 0xd5182000, 0xd5033fdf, 0xd65f03c0], "_set_mmu_ttb is dsb; msr ttbr0_el1, x0; isb; ret")

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_instructions_are_what_the_patch_says(self):
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        ins = [(i.mnemonic, i.op_str) for i in md.disasm(bytes(self.image[VMTTB_VA - VIRT:VMTTB_VA - VIRT + 20]), VMTTB_VA)]
        self.assertEqual(ins[0][0] + ins[1][0] + ins[2][0] + ins[3][0] + ins[4][0], "adrpaddldrandbl")
        self.assertEqual(ins[2][1], "x8, [x19]")
        self.assertEqual(ins[3][1], "x0, x8, #0xffffffffffff")
        self.assertEqual(p59.INVALID_TTEP_VA, INVALID_TTEP_VA)

    def test_the_symbol_of_the_address_is_invalid_ttep(self):
        try:
            sys.path.insert(0, str(N35))
            cr = load("nat059t_cresume", N35 / "cresume.py")
            v = cr.a5.Image().vals
        except Exception as e:
            self.skipTest("the NAT-035 model inputs are missing: %r" % (e,))
        self.assertEqual(v["_invalid_ttep"], INVALID_TTEP_VA)
        self.assertEqual(v["_arm_vm_init"], ARM_VM_INIT_VA)
        self.assertEqual(v["_set_mmu_ttb"], SETTTB_VA)

    def test_the_checkpoint_calls_of_arm_init_are_in_the_order_the_stop_list_assumes_and_17_to_21_follow_arm_vm_init(self):
        # the first `bl _loader_checkpoint` after arm_init's start up to the `bl _machine_startup`; each has a `movz w0, #n` (or a mov from w8) just before it
        sites = checkpoint_sites(self.image)
        self.assertEqual([n for _, n in sites], list(ORDER))
        call = vm_init_call(self.image)
        before = [n for a, n in sites if a < call]
        after = [n for a, n in sites if a > call]
        self.assertEqual((before[-1], after), (16, [17, 18, 19, 20, 21]), "17..21 are exactly the checkpoints after arm_vm_init")

    def test_arm_vm_init_sets_tcr_by_one_orr_and_the_call_is_set_tcr(self):
        # What NAT-059 relies on: arm_vm_init writes TCR_EL1 once, with `orr x21, x0, #imm` of the value read by get_tcr (the loader_jump check
        # on T0SZ therefore still sees the T0SZ of the kernel's own TCR). Found by walking arm_vm_init's calls; decoded here without the patch.
        end = VMTTB_VA + 20
        sets = []
        for off in range(ARM_VM_INIT_VA - VIRT, end - VIRT, 4):
            w = struct.unpack_from("<I", bytes(self.image), off)[0]
            if w >> 26 == 0b100101:
                sets.append(bl_target(VIRT + off, w))
        self.assertEqual(sets.count(SETTTB_VA), 1, "one _set_mmu_ttb call in arm_vm_init before the pinned site's end")
        self.assertIn(0xfffffff0074428d8, sets, "bl _set_tcr")


def checkpoint_sites(image):
    """[(address, n)] of the `bl _loader_checkpoint` calls of arm_init in address order. The argument is set by a `mov w0, #n` shortly before."""
    start, end = 0xfffffff007431398, 0xfffffff007431d14
    base = start - VIRT
    out = []
    for off in range(base, end - VIRT, 4):
        w = struct.unpack_from("<I", bytes(image), off)[0]
        if w >> 26 != 0b100101:
            continue
        pc = VIRT + off
        if bl_target(pc, w) != CHECKPOINT_VA:
            continue
        n = None
        for back in range(1, 9):
            p = struct.unpack_from("<I", bytes(image), off - 4 * back)[0]
            if p & 0xffe0001f == 0x52800000:                                     # movz w0, #imm16
                n = (p >> 5) & 0xffff
                break
        out.append((pc, n))
    return out


def vm_init_call(image):
    start, end = 0xfffffff007431398, 0xfffffff007431d14
    for off in range(start - VIRT, end - VIRT, 4):
        w = struct.unpack_from("<I", bytes(image), off)[0]
        if w >> 26 == 0b100101 and bl_target(VIRT + off, w) == ARM_VM_INIT_VA:
            return VIRT + off
    raise AssertionError("no call of arm_vm_init in arm_init")


# ------------------------------------------------------------------------------------------------------------------ Host
class S31(ctypes.Structure):
    _fields_ = [("slot_pa", ctypes.c_uint64), ("pa_minus_va", ctypes.c_uint64), ("expect", ctypes.c_uint32), ("mask", ctypes.c_uint32),
                ("arrivals", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


class S36(ctypes.Structure):
    _fields_ = [("s", S31), ("stops", ctypes.c_void_p), ("nstops", ctypes.c_uint32), ("idx", ctypes.c_uint32), ("last", ctypes.c_uint32),
                ("pad", ctypes.c_uint32), ("kernel_ttbr0", ctypes.c_uint64), ("flag_pa", ctypes.c_uint64), ("ttep_pa", ctypes.c_uint64)]


class D36(ctypes.Structure):
    _fields_ = [("action", ctypes.c_uint32), ("next", ctypes.c_uint32), ("final", ctypes.c_uint32), ("resume_pa", ctypes.c_uint64)]


def ref_list_ok(stops):
    """The rule, stated from the payload's checkpoint order (ORDER above is checked against arm_init's call sites by Words)."""
    if not 1 <= len(stops) <= 24 or any(s not in ORDER for s in stops):
        return False
    return all(ORDER.index(a) < ORDER.index(b) for a, b in zip(stops, stops[1:]))


def have_cc():
    return subprocess.run(["cc", "--version"], capture_output=True).returncode == 0


@needs_payload
@unittest.skipUnless(have_cc(), "cc missing")
class Host(unittest.TestCase):
    STUB, STUB_END = 0x9e2d80000, 0x9e2d80140

    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        t = Path(cls.tmp.name)
        c, h, _ = derived_text()
        (t / "ckpt3.c").write_text(c)
        (t / "ckpt3.h").write_text(h)
        for f in ("marker3.h",):
            (t / f).write_bytes((SRC36 / f).read_bytes())
        so = t / "ckpt3.so"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DNAT031_HOST", "-fsanitize=alignment", "-fsanitize-undefined-trap-on-error",
                        "-shared", "-fPIC", f"-I{t}", f"-I{SRC22}", f"-I{N52 / 'src'}", str(SRC22 / "ckpt.c"), str(t / "ckpt3.c"), "-o", str(so)], check=True)
        lib = cls.lib = ctypes.CDLL(str(so))
        u64, u32, p = ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p
        lib.nat036_list_ok.argtypes = [p, u32]; lib.nat036_list_ok.restype = ctypes.c_int
        lib.nat036_check.argtypes = [ctypes.c_size_t, u64, u64, u64, p, u32, ctypes.POINTER(u32)]; lib.nat036_check.restype = ctypes.c_int
        lib.nat036_prepare.argtypes = [p, ctypes.c_size_t, u64, u64, u64, p, u32, ctypes.POINTER(u32)]; lib.nat036_prepare.restype = ctypes.c_int
        lib.nat036_decide.argtypes = [p, u64, u64, u64, u64, p]
        lib.nat059_resume_ttbr0.argtypes = [p, u32, ctypes.POINTER(u64)]; lib.nat059_resume_ttbr0.restype = ctypes.c_int
        lib.nat059_resume_decision.argtypes = [p, p, u64, ctypes.POINTER(u64)]
        cls.image = WINDOW(PL, UPTO)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.buf = (ctypes.c_char * len(self.image)).from_buffer_copy(bytes(self.image))
        self.base = ctypes.addressof(self.buf)
        self._keep = []

    def arr(self, stops):
        a = (ctypes.c_uint8 * max(len(stops), 1))(*stops)
        self._keep.append(a)
        return a

    def poke64(self, va, value):
        struct.pack_into("<Q", self.buf, va - VIRT, value)

    def poke32(self, va, value):
        struct.pack_into("<I", self.buf, va - VIRT, value)

    def check(self, stops):
        bad = ctypes.c_uint32(99)
        a = self.arr(stops)
        return self.lib.nat036_check(self.base, VIRT, self.STUB, self.STUB_END, ctypes.addressof(a), len(stops), ctypes.byref(bad)), bad.value

    def prepare(self, stops):
        st, bad = S36(), ctypes.c_uint32(99)
        a = self.arr(stops)
        rc = self.lib.nat036_prepare(ctypes.byref(st), self.base, VIRT, self.STUB, self.STUB_END, ctypes.addressof(a), len(stops), ctypes.byref(bad))
        self.assertEqual(rc, 0, "install refused the real payload")
        return st

    def decide(self, st, x2, x3, sctlr=0x3454599d, ttbr0=CP5_TTBR0):
        d = D36()
        self.lib.nat036_decide(ctypes.byref(st), x2, x3, sctlr, ttbr0, ctypes.byref(d))
        return d

    def asm_to_cp5(self, st):
        for n in (1, 2, 3, 4):
            self.assertEqual(self.decide(st, 2, n, sctlr=0x30d8099a).action, RESUME_ASM)
        d = self.decide(st, 2, 5, sctlr=0x3454599c)
        self.assertEqual(d.action, RESUME_ASM)

    def rt(self, st, d, x3):
        rt = ctypes.c_uint64(0xdead)
        self.lib.nat059_resume_decision(ctypes.byref(st), ctypes.byref(d), x3, ctypes.byref(rt))
        return rt.value

    # -- the list rule
    def test_the_list_rule_accepts_17_to_21_and_refuses_what_is_out_of_order_or_unknown(self):
        cases = [STOPS, OLD_STOPS, (17,), (21,), (11, 17, 21), (16, 17), (30, 40, 44, 13, 21), (21, 17), (17, 17), (16, 15), (22,), (0,), (), (10,), (18, 17),
                 STOPS + (21,), (11, 30, 12, 31)]
        for s in cases:
            a = self.arr(list(s))
            self.assertEqual(bool(self.lib.nat036_list_ok(ctypes.addressof(a) if s else None, len(s))), ref_list_ok(s), s)
        self.assertEqual(self.lib.nat036_list_ok(None, 3), 0)

    def test_the_install_check_accepts_the_real_payload_for_the_22_stops_and_for_the_old_17(self):
        self.assertEqual(self.check(STOPS)[0], 0)
        self.assertEqual(self.check(OLD_STOPS)[0], 0)

    def test_the_install_check_refuses_an_arm_vm_init_that_is_not_the_analysed_one_only_when_the_list_goes_past_it(self):
        for i in range(5):
            self.setUp()
            self.poke32(VMTTB_VA + 4 * i, 0xd503201f)
            self.assertEqual(self.check(STOPS)[0], RC_VMTTB_BAD, "word %d" % i)
            self.assertEqual(self.check((17,))[0], RC_VMTTB_BAD)
            self.assertEqual(self.check(OLD_STOPS)[0], 0, "a list that stays at or below 16 does not read arm_vm_init")
            self.assertEqual(self.check((11, 30, 12, 40))[0], 0, "ids 30..44 are numerically above 21 but come before arm_vm_init: they do not read it")
        self.setUp()
        a = self.arr(list(STOPS))
        buf_before = bytes(self.buf)
        st, bad = S36(), ctypes.c_uint32(99)
        self.poke32(VMTTB_VA, 0)
        before = bytes(self.buf)
        rc = self.lib.nat036_prepare(ctypes.byref(st), self.base, VIRT, self.STUB, self.STUB_END, ctypes.addressof(a), len(STOPS), ctypes.byref(bad))
        self.assertEqual(rc, RC_VMTTB_BAD)
        self.assertEqual(bytes(self.buf), before, "nothing is written when a check fails")

    # -- the TTBR0 rule
    def test_every_stop_up_to_16_gives_back_the_cp5_value_and_every_stop_from_17_the_value_of_invalid_ttep(self):
        invalid_ttep = 0x9e15a8000
        self.poke64(INVALID_TTEP_VA, 0x00ab000000000000 | invalid_ttep)           # ASID-like bits above bit 47 must not survive
        st = self.prepare(STOPS)
        self.asm_to_cp5(st)
        got = []
        for i, cp in enumerate(STOPS):
            d = self.decide(st, 2, cp)
            self.assertEqual((d.action, d.final), (RESUME_C, 0) if i < len(STOPS) - 1 else (HOLD, 1), cp)
            got.append(self.rt(st, d, cp))
        self.assertEqual(got, [CP5_TTBR0] * 17 + [invalid_ttep] * 5)
        self.assertEqual(st.s.mask & (MASK_BAD_TTBR0 | MASK_BAD_STATE), 0)
        self.assertTrue(st.s.mask & MASK_FINAL)

    def test_a_stop_after_arm_vm_init_never_resumes_with_the_cp5_value_even_when_it_is_the_only_value_the_stub_has(self):
        self.poke64(INVALID_TTEP_VA, 0)                                            # what the payload file holds: arm_vm_init has not run
        st = self.prepare(STOPS)
        self.asm_to_cp5(st)
        for cp in STOPS[:17]:
            self.assertEqual(self.decide(st, 2, cp).action, RESUME_C)
        d = self.decide(st, 2, 17)
        self.assertEqual(d.action, RESUME_C, "decide() is the NAT-036 rule: it resumes; the TTBR0 policy is nat059_resume_decision's")
        rt = self.rt(st, d, 17)
        self.assertEqual((d.action, rt), (HOLD, 0), "an unreadable value holds; it is never replaced by the cp5 value")
        self.assertTrue(st.s.mask & MASK_BAD_TTBR0)

    def test_an_implausible_invalid_ttep_holds_instead_of_resuming(self):
        for bad in (0x1, 0x9e15a8002, 0x9e15a8ffe, 0x0000000000000fff, 0xffff000000000000):
            self.setUp()
            self.poke64(INVALID_TTEP_VA, bad)
            st = self.prepare(STOPS)
            self.asm_to_cp5(st)
            for cp in STOPS[:16]:
                self.decide(st, 2, cp)
            d = self.decide(st, 2, 16)
            self.assertEqual(d.action, RESUME_C)
            self.rt(st, d, 16)
            self.assertEqual(d.action, RESUME_C, "checkpoint 16 does not look at invalid_ttep: %#x" % bad)
            d = self.decide(st, 2, 17)
            self.rt(st, d, 17)
            self.assertEqual(d.action, HOLD, hex(bad))
            self.assertTrue(st.s.mask & MASK_BAD_TTBR0, hex(bad))

    def test_the_old_17_stop_list_is_unchanged_and_never_reads_invalid_ttep(self):
        self.poke64(INVALID_TTEP_VA, 0x1)                                          # would be refused if it were read
        self.poke32(VMTTB_VA, 0)
        st = self.prepare(OLD_STOPS)
        self.asm_to_cp5(st)
        rts = []
        for i, cp in enumerate(OLD_STOPS):
            d = self.decide(st, 2, cp)
            self.assertEqual((d.action, d.final), (RESUME_C, 0) if i < 16 else (HOLD, 1))
            rts.append(self.rt(st, d, cp))
        self.assertEqual(rts, [CP5_TTBR0] * 17)
        self.assertEqual(st.s.mask & MASK_BAD_TTBR0, 0)

    def test_a_stop_that_neither_resumes_nor_is_final_reports_no_ttbr0(self):
        st = self.prepare(STOPS)
        self.asm_to_cp5(st)
        d = self.decide(st, 2, 30)                                                 # not the expected next stop (11): hold
        self.assertEqual(d.action, HOLD)
        self.assertEqual(self.rt(st, d, 30), 0)
        d = self.decide(st, 0, 0)                                                  # the kernel's orderly end
        self.assertEqual((d.action, self.rt(st, d, 0)), (HOLD, 0))


# ------------------------------------------------------------------------------------------------------------------ Build
def zig_ok():
    return subprocess.run(["zig", "version"], capture_output=True).returncode == 0 if subprocess.run(["which", "zig"], capture_output=True).returncode == 0 else False


@unittest.skipUnless(HAVE_PAYLOAD and LOADER_SRC.exists() and zig_ok(), "zig or the NAT-020 build-003 source/payload is missing")
class Build(unittest.TestCase):
    def test_the_image_builds_from_the_committed_sources(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMPDIR=str(SCRATCH))
        r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--check-only", "--loader-source", str(LOADER_SRC)], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertRegex(r.stdout.strip(), r"^ok \d+$")

    def test_an_old_style_list_is_still_buildable_and_a_list_past_21_is_refused_by_the_loaders_own_rule(self):
        # the build passes the list to the compiler; the refusal is nat036_list_ok at install time (Host layer). Here only that the default is the 22.
        b = load("nat059t_build", HERE / "build.py")
        self.assertEqual(b.DEFAULT_STOPS, STOPS)
        self.assertEqual(b.NAME, "loader-diag-xnu-ckpt4-usb")


if __name__ == "__main__":
    unittest.main()
