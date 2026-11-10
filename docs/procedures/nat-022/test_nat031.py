#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-031 host tests: the loader side of the payload kernel's XNULDRST hook (ckpt.c, ckpt_stub.S, the CKPT markers
and the loader-diag-xnu-ckpt image). Evidence kind: host-test. Nothing here runs on the phone.

Three layers, each runs only what it can:
  * ckpt.c built for the host (gcc, alignment sanitizer) against the real payload bytes: the slot/site checks, the
    fill, the decision table. Needs the NAT-020 build-003 payload.
  * markerlib.c's CKPT drawing against the fake DECON0, read back with the independent decoder (decode.py).
  * the aarch64 code (zig): ckpt.c + ckpt_stub.S linked with test doubles for the marker routines and run by the
    NAT-030 interpreter on the kernel's real start code; plus a build/regression test of the loader images.
    Needs zig, capstone and the payload (the interpreter test also needs capstone in the Python running it).
The interpreter has no caches, exception model or SIMD: what it shows is the register/memory contract of the stub,
not the behaviour of the phone."""
import ctypes, importlib.util, json, os, re, shutil, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = Path(os.environ["NAT031_SRC"]) if os.environ.get("NAT031_SRC") else HERE / "src"      # a mutated copy of src/ for the mutation checks
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
sys.path.insert(0, str(ROOT / "docs/procedures/nat-029"))
sys.path.insert(0, str(ROOT / "docs/procedures/nat-030"))
import analyze_payload as ap  # noqa: E402

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

dec = _load("decode", HERE / "decode.py")
bld = _load("build", HERE / "build.py")
try:
    import capstone
except ImportError:
    capstone = None

VIRT = 0xfffffff004000000
SLOT_VA = 0xfffffff00743c7f0
SITES = [0xfffffff00743e068, 0xfffffff00743e0c4, 0xfffffff00743e304, 0xfffffff00743e408, 0xfffffff00743e470]
M64 = (1 << 64) - 1
NEEDS_PAYLOAD = unittest.skipUnless(PAYLOAD.exists(), "NAT-020 build-003 payload is missing")


def window_prefix(payload, upto):
    """The first `upto` bytes of the loader's copy of the kernel image: segments at PA = base + (vmaddr - virt_base)."""
    buf = bytearray(upto)
    for vm, vs, fo, fs in payload.segs:
        off = vm - payload.virt_base
        if off < upto:
            n = min(fs, upto - off)
            buf[off:off + n] = payload.b[fo:fo + n]
    return buf


@NEEDS_PAYLOAD
class CkptHost(unittest.TestCase):
    """The real ckpt.c (NAT031_HOST) on the real payload bytes. gcc's alignment sanitizer traps any misaligned access."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        so = Path(cls.tmp.name) / "ckpt.so"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DNAT031_HOST", "-fsanitize=alignment", "-fsanitize-undefined-trap-on-error",
                        "-shared", "-fPIC", f"-I{SRC}", str(SRC / "ckpt.c"), "-o", str(so)], check=True)
        lib = cls.lib = ctypes.CDLL(str(so))
        u64, u32, p = ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p
        lib.nat031_site_va.argtypes = [u32]; lib.nat031_site_va.restype = u64
        lib.nat031_check.argtypes = [ctypes.c_size_t, u64, ctypes.POINTER(u32)]; lib.nat031_check.restype = ctypes.c_int
        lib.nat031_prepare.argtypes = [p, ctypes.c_size_t, u64, u64, ctypes.POINTER(u32)]; lib.nat031_prepare.restype = ctypes.c_int
        lib.nat031_decide.argtypes = [p, u64, u64, p]
        lib.nat031_set_next.argtypes = [p, u32]
        cls.payload = ap.Payload(str(PAYLOAD))
        cls.image = window_prefix(cls.payload, 0x3500000)            # up to and past the last site

    def fresh(self):
        buf = (ctypes.c_char * len(self.image)).from_buffer_copy(bytes(self.image))
        return buf, ctypes.addressof(buf)

    class State(ctypes.Structure):
        _fields_ = [("slot_pa", ctypes.c_uint64), ("pa_minus_va", ctypes.c_uint64), ("expect", ctypes.c_uint32),
                    ("mask", ctypes.c_uint32), ("arrivals", ctypes.c_uint32), ("pad", ctypes.c_uint32)]

    class Decision(ctypes.Structure):
        _fields_ = [("action", ctypes.c_uint32), ("next", ctypes.c_uint32), ("resume_pa", ctypes.c_uint64)]

    def check(self, base):
        bad = ctypes.c_uint32(99)
        rc = self.lib.nat031_check(base, VIRT, ctypes.byref(bad))
        return rc, bad.value

    def test_site_table_is_exactly_the_sites_in_the_payload(self):
        self.assertEqual([self.lib.nat031_site_va(n) for n in range(1, 6)], SITES)
        self.assertEqual((self.lib.nat031_site_va(0), self.lib.nat031_site_va(6)), (0, 0))
        # Independent of ckpt.c: every place in the payload that forms the slot's address (adrp x9 + add x9, x9) and then loads
        # slot[2] and compares it with an immediate.
        found = []
        for vm, vs, fo, fs in self.payload.segs:
            for i in range(0, fs - 16, 4):
                w = [struct.unpack_from("<I", self.payload.b, fo + i + 4 * k)[0] for k in range(4)]
                if (w[0] & 0x9f00001f) != 0x90000009 or (w[1] & 0xffc003ff) != 0x91000129:      # adrp x9, P; add x9, x9, #lo12
                    continue
                imm = ((w[0] >> 5) & 0x7ffff) << 2 | (w[0] >> 29) & 3
                imm -= (1 << 21) if imm >> 20 else 0
                target = ((vm + i) & ~0xfff) + (imm << 12) + ((w[1] >> 10) & 0xfff)
                if target == SLOT_VA and w[2] == 0xf940092a and (w[3] & 0xffc003ff) == 0xf100015f:   # ldr x10,[x9,#16]; cmp x10,#imm
                    found.append((vm + i, (w[3] >> 10) & 0xfff))
        self.assertEqual(found, [(v, n) for n, v in enumerate(SITES, 1)])     # exactly five, numbered 1..5, in address order

    def test_the_real_payload_passes_and_the_fill_writes_exactly_three_words(self):
        buf, base = self.fresh()
        self.assertEqual(self.check(base), (0, 0))
        st = self.State()
        bad = ctypes.c_uint32(0)
        before = bytes(buf)
        self.assertEqual(self.lib.nat031_prepare(ctypes.byref(st), base, VIRT, 0x9e2d80000, ctypes.byref(bad)), 0)
        after = bytes(buf)
        slot = SLOT_VA - VIRT
        changed = [o for o in range(0, len(before), 8) if before[o:o + 8] != after[o:o + 8]]
        self.assertEqual(changed, [slot + 8, slot + 16, slot + 24])               # nothing but slot[1], [2], [3]
        self.assertEqual(struct.unpack_from("<4Q", after, slot), (0x545352444c554e58, 0x9e2d80000, 1, (base - VIRT) & M64))
        self.assertEqual((st.slot_pa, st.pa_minus_va, st.expect, st.mask, st.arrivals), (base + slot, (base - VIRT) & M64, 1, 0, 0))

    def test_every_single_bit_flip_in_a_site_is_refused_and_nothing_is_written(self):
        buf, base = self.fresh()
        self.assertEqual(self.check(base), (0, 0))
        for n, va in enumerate(SITES, 1):
            for w in range(15):
                off = va - VIRT + 4 * w
                orig = struct.unpack_from("<I", buf, off)[0]
                for bit in range(32):
                    struct.pack_into("<I", buf, off, orig ^ (1 << bit))
                    self.assertEqual(self.check(base), (2, n), (n, w, bit))
                struct.pack_into("<I", buf, off, orig)
        self.assertEqual(self.check(base), (0, 0))                                   # the loop left the image as it found it
        buf, base = self.fresh()
        off = SITES[2] - VIRT + 4 * 7
        struct.pack_into("<I", buf, off, struct.unpack_from("<I", buf, off)[0] ^ 1)
        st = self.State(); bad = ctypes.c_uint32(0); before = bytes(buf)
        self.assertEqual(self.lib.nat031_prepare(ctypes.byref(st), base, VIRT, 0x9e2d80000, ctypes.byref(bad)), 2)
        self.assertEqual((bad.value, bytes(buf)), (3, before))                      # refused: the slot is untouched

    def test_slot_conditions(self):
        slot = SLOT_VA - VIRT
        buf, base = self.fresh()
        magic = struct.unpack_from("<Q", buf, slot)[0]
        for bit in range(64):                                                      # a damaged magic
            struct.pack_into("<Q", buf, slot, magic ^ (1 << bit))
            self.assertEqual(self.check(base), (1, 0), bit)
        struct.pack_into("<Q", buf, slot, magic)
        for word in (1, 2, 3):                                                     # a slot that is not three zero words
            for val in (1, 1 << 63):
                struct.pack_into("<Q", buf, slot + 8 * word, val)
                self.assertEqual(self.check(base), (1, 0), (word, val))
            struct.pack_into("<Q", buf, slot + 8 * word, 0)
        self.assertEqual(self.check(base), (0, 0))
        self.assertEqual(self.check(base + 4)[0], 1)                               # a window base that makes the slot misaligned
        # A site that loads some other slot: the adrp/add pair is decoded, not compared with fixed bits.
        buf, base = self.fresh()
        off = SITES[0] - VIRT + 4
        w = struct.unpack_from("<I", buf, off)[0]
        struct.pack_into("<I", buf, off, (w & ~(0xfff << 10)) | ((((w >> 10) & 0xfff) + 8) << 10))
        self.assertEqual(self.check(base), (2, 1))

    def decide(self, st, x2, x3):
        d = self.Decision()
        self.lib.nat031_decide(ctypes.byref(st), x2, x3, ctypes.byref(d))
        return d.action, d.next, d.resume_pa

    def new_state(self):
        st = self.State(); st.expect = 1; st.pa_minus_va = 0x19da400000
        return st

    def test_decide_resumes_only_the_expected_checkpoint_and_holds_at_five(self):
        st = self.new_state()
        for n in range(1, 5):
            act, nxt, pa = self.decide(st, 2, n)
            self.assertEqual((act, nxt, pa), (1, n + 1, (SITES[n - 1] + 60 + 0x19da400000) & M64), n)    # RESUME, next number, site + 15 instructions
            self.assertEqual((st.expect, st.mask, st.arrivals), (n + 1, (1 << (n + 1)) - 2, n))
        self.assertEqual(self.decide(st, 2, 5), (2, 0, 0))                                      # HOLD at the last site
        self.assertEqual((st.mask, st.arrivals), (0x3e, 5))

    def test_decide_holds_on_everything_else(self):
        cases = [((2, 3), 1 << 10), ((2, 2), 1 << 10), ((2, 0), 1 << 10), ((2, 6), 1 << 10), ((2, 1 << 40), 1 << 10), ((3, 1), 1 << 10),
                 ((1, 0x96000045), 1 << 8), ((1, 1), 1 << 8), ((0, 0), 1 << 9), ((0, 1), 1 << 9), ((M64, 1), 1 << 10)]
        for (x2, x3), bit in cases:
            st = self.new_state()
            self.assertEqual(self.decide(st, x2, x3), (2, 0, 0), (x2, x3))
            self.assertEqual((st.mask, st.arrivals, st.expect), (bit, 1, 1), (x2, x3))            # held, and the expectation is unchanged
        st = self.new_state()                                                                     # the same checkpoint twice
        self.assertEqual(self.decide(st, 2, 1)[0], 1)
        self.assertEqual(self.decide(st, 2, 1), (2, 0, 0))
        self.assertEqual(st.mask, 0x2 | 1 << 10)
        st = self.new_state()                                                                     # an exception after two good arrivals
        self.decide(st, 2, 1); self.decide(st, 2, 2)
        self.assertEqual(self.decide(st, 1, 0x96000045)[0], 2)
        self.assertEqual(st.mask, 0x6 | 1 << 8)

    def test_set_next_stores_one_aligned_word_in_slot_2(self):
        buf, base = self.fresh()
        st = self.State(); st.slot_pa = base + (SLOT_VA - VIRT)
        before = bytes(buf)
        self.lib.nat031_set_next(ctypes.byref(st), 3)
        after = bytes(buf)
        self.assertEqual([o for o in range(0, len(before), 8) if before[o:o + 8] != after[o:o + 8]], [SLOT_VA - VIRT + 16])
        self.assertEqual(struct.unpack_from("<Q", after, SLOT_VA - VIRT + 16)[0], 3)


class CkptMarker(unittest.TestCase):
    """What the return stub draws (markerlib.c with MK_XNU_CKPT=1 against the fake DECON0), decoded independently."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.exe = t / "host_mk_ckpt"
        cc = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DMK_HOST=1", "-DMK_TRIG=1", "-DMK_LOADER=1", f"-I{SRC}"]
        subprocess.run([*cc, "-DMK_XNU_CKPT=1", "-DNAT031_HOST", str(SRC / "markerlib.c"), str(SRC / "ckpt.c"), str(SRC / "host_mk.c"), "-o", str(cls.exe)], check=True)
        cls.plain = t / "host_mk_ld"
        subprocess.run([*cc, str(SRC / "markerlib.c"), str(SRC / "host_mk.c"), "-o", str(cls.plain)], check=True)

    def go(self, n, seq, full=False):
        out = Path(self.tmp.name) / "fb.bin"
        p = subprocess.run([str(self.exe), "ckpt", str(n), str(out), "0x113", "0x3063", seq, *(["full"] if full else [])], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-300:] + p.stderr)
        ev = [l.split() for l in p.stdout.splitlines()]
        frames = [dec.parse_frame(int(e[1], 16)) for e in ev if e[0] == "DRAW"]
        self.assertTrue(frames and all(frames))
        return ev, frames

    def ck(self, frames, idx=None):
        return [f for f in frames if f["kind"] == 11 and (idx is None or f["idx"] == idx)]

    def test_each_pass_draws_regs_then_mask_and_the_hold_report_repeats(self):
        ev, frames = self.go(400, "2:1,2:2,2:3,2:4,2:5")
        ck = [(f["idx"], f["data"]) for f in frames if f["kind"] == 11]
        self.assertEqual(ck[:8], [(0, 0x0201), (1, 0x2), (0, 0x0202), (1, 0x6), (0, 0x0203), (1, 0xe), (0, 0x0204), (1, 0x1e)])
        self.assertEqual(ck[8:11], [(0, 0x0205), (1, 0x3e), (10, 5)])                 # the hold: REGS, MASK, ARRIVALS first
        later = {(f["kind"], f["idx"]) for f in frames[-40:]}
        self.assertTrue({(3, 0), (11, 0), (11, 1), (11, 2), (11, 3), (11, 4), (11, 5), (11, 6), (11, 7), (11, 8), (11, 9), (11, 10), (2, 0), (2, 1)} <= later, later)
        d = dec.describe(frames)["ckpt"]
        self.assertEqual((d["x2"], d["x3"], d["arrival_mask"], d["arrivals"]), (2, 5, 0x3e, 5))
        self.assertEqual(d["arrivals_seen"], ["checkpoint %d" % n for n in range(1, 6)])
        self.assertEqual((d["sctlr_el1_lo32"], d["ttbr1_el1_lo48"], d["vbar_el1_lo16"], d["tcr_el1_lo32"]),
                         ("0x3454593c", "0x0009e15af000", "0x7000", "0xa51a251a"))

    def test_the_pass_frames_come_after_the_loader_stages_and_use_stage_0x51_only_in_the_stub(self):
        ev, frames = self.go(400, "2:1,2:2,2:3,2:4,2:5", full=True)
        stages = [dec.STAGES[f["data"]] for f in frames if f["kind"] == 3 and f["idx"] == 0]
        self.assertEqual(stages[7], "pre-jump (NOT proof of kernel entry)")
        self.assertNotIn("inside NAT-031 return stub", stages[:8])
        first = next(i for i, f in enumerate(frames) if f["kind"] == 11)
        last_loader = max(i for i, f in enumerate(frames[:first]) if f["kind"] == 3)
        self.assertLess(last_loader, first)
        self.assertEqual(dec.describe(frames)["stages_reached"][-2:], ["pre-jump", "ckpt return stub (NAT-031)"])
        syms = subprocess.run(["nm", str(self.plain)], capture_output=True, text=True, check=True).stdout
        self.assertNotIn("mk_ckpt", syms)                                             # the plain loader markers cannot draw a CKPT frame
        src = (SRC / "markerlib.c").read_text()
        self.assertEqual(src.count("MK_ST_CKPT"), 5)                                   # the ld_bit case, the pass' mask, the hold's mask and its two stage frames
        self.assertIn("#if MK_XNU_CKPT\n\tcase MK_ST_CKPT", src[:src.index("#if MK_LOADER && MK_XNU_CKPT")])

    def test_arrival_order_and_unexpected_arrivals_show_in_the_mask(self):
        for seq, mask, regs in (("2:1,2:3", 0x2 | 1 << 10, 0x0203), ("2:2", 1 << 10, 0x0202), ("2:1,1:0x96000045", 0x2 | 1 << 8, 0x0145),
                                ("0:0", 1 << 9, 0x0000), ("2:1,2:2,2:3,2:4,2:5", 0x3e, 0x0205)):
            ev, frames = self.go(300, seq)
            d = dec.describe(frames)["ckpt"]
            self.assertEqual(d["arrival_mask"], mask, seq)
            self.assertEqual(self.ck(frames, 0)[-1]["data"], regs, seq)

    def test_exception_report_carries_esr_elr_far_and_no_sctlr_block(self):
        ev, frames = self.go(300, "1:0x96000045")
        d = dec.describe(frames)
        self.assertEqual((d["ckpt"]["x2"], d["ckpt"]["x3"]), (1, 0x45))               # data field is 8 bits of the code; ESR itself is below
        loop = {(f["kind"], f["idx"]) for f in frames[-60:]}
        self.assertTrue({(4, 0), (4, 1), (4, 2), (4, 3), (5, 0), (5, 3), (6, 0), (6, 3)} <= loop, loop)
        self.assertNotIn((11, 2), loop)
        self.assertEqual(d["esr"], "0x0000000096000045"); self.assertEqual(d["elr"], "0xfffffff00743e0b0"); self.assertEqual(d["far"], "0x00000000deadbeef")

    def test_every_draw_is_followed_by_a_decon_kick(self):
        ev, frames = self.go(200, "2:1,2:2,2:3,2:4,2:5")
        draws = [i for i, e in enumerate(ev) if e[0] == "DRAW"]
        for a, b in zip(draws, draws[1:]):
            seg = ev[a + 1:b]
            self.assertTrue(seg and seg[0][:2] == ["RD", "20"], seg)
            self.assertTrue({e[1] for e in seg if e[0] == "WR"} <= {"30", "50"})

    def test_display_budget(self):
        """Frames are shown for 1.2 s each and the display ends about 83 s after the first frame (runs 004-007: watchdog reset). The loader's
        stages take real time: PRE_JUMP was drawn 19.5 s after the first frame in runs 006 and 007. From there the budget is frames x 1.2 s."""
        ev, frames = self.go(400, "2:1,2:2,2:3,2:4,2:5", full=True)
        pre_jump = next(i for i, f in enumerate(frames) if f["kind"] == 3 and f["idx"] == 0 and f["data"] == 0x40)
        regs = [i for i, f in enumerate(frames) if f["kind"] == 11 and f["idx"] == 0]
        self.assertGreaterEqual(len(regs), 7)                                          # four passes, then the held report repeating
        held = regs[4]
        values_done = next(i for i, f in enumerate(frames[held:], held) if f["kind"] == 11 and f["idx"] == 9)       # TCR high: the last checkpoint value
        t_values = 19.5 + (values_done - pre_jump + 1) * 1.2
        t_report = 19.5 + (regs[5] - pre_jump) * 1.2
        self.assertLess(t_values, 50)                                                  # every checkpoint value is on screen once by ~46 s
        self.assertLess(t_report, 70)                                                  # the first complete held report, DECON block included
        self.assertGreater(83 - t_report, 10)
        self.assertGreater(regs[5] - regs[4], 20)                                      # a held report is a long loop (25 frames): the owner has time to film it twice

def zig_ok():
    return bool(shutil.which("zig"))


@unittest.skipUnless(capstone and zig_ok() and PAYLOAD.exists(), "capstone, zig or the NAT-020 build-003 payload is missing")
class KernelChain(unittest.TestCase):
    """The aarch64 stub + ckpt.c, compiled as the loader build does, run by the NAT-030 interpreter on the kernel's real
    start code with test doubles for mk_ckpt_pass / mk_ckpt_hold. The interpreter has no SIMD: the SIMD check is in Build."""
    BASE, SIZE = 0x9de400000, 0x20000000
    RET = BASE + 0x4a00000
    BAD = BASE + 0x4a10000
    KSP = 0xfffffff008060000

    @classmethod
    def setUpClass(cls):
        global ks
        ks = _load("kstart_sim", ROOT / "docs/procedures/nat-030/kstart_sim.py")
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        objs = []
        for name, src, extra in (("ckpt.c", SRC / "ckpt.c", bld.NO_SIMD), ("mock.c", HERE / "test_support/nat031_mock.c", bld.NO_SIMD),
                                 ("stub.S", SRC / "ckpt_stub.S", []), ("mockbss.S", HERE / "test_support/nat031_mock.S", [])):
            o = t / (name + ".o")
            subprocess.run(["zig", "cc", *[f for f in bld.FLAGS if f != "-mgeneral-regs-only"], *extra, f"-I{SRC}", "-c", str(src), "-o", str(o)], check=True)
            objs.append(o)
        cls.elf = t / "stub.elf"
        subprocess.run(["zig", "cc", "-target", "aarch64-freestanding", "-static", "-nostdlib", "-Wl,--build-id=none", "-Wl,-e,nat031_stub",
                        f"-Wl,-T,{HERE / 'test_support/nat031_mock.ld'}", *objs, "-o", str(cls.elf)], check=True)
        cls.secdata, cls.syms = cls.read_elf(cls.elf)
        cls.stack = cls.syms["_stack_top"]
        cls.stub = cls.syms["nat031_stub"]

    @staticmethod
    def read_elf(path):
        d = Path(path).read_bytes()
        shoff = struct.unpack_from("<Q", d, 0x28)[0]
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x3a)
        secs = [struct.unpack_from("<IIQQQQIIQQ", d, shoff + i * shentsize) for i in range(shnum)]
        names = d[secs[shstrndx][4]:]
        out = {names[s[0]:names.index(b"\0", s[0])].decode(): s for s in secs}
        sy, st = out[".symtab"], out[".strtab"]
        syms = {}
        for i in range(sy[5] // 24):
            nm, info, oth, shn, val, sz = struct.unpack_from("<IBBHQQ", d, sy[4] + 24 * i)
            name = d[st[4] + nm:d.index(b"\0", st[4] + nm)].decode()
            if name:
                syms[name] = val
        return [(s[3], d[s[4]:s[4] + s[5]]) for n, s in out.items() if n in (".text", ".rodata", ".data")], syms

    # --- harness ---------------------------------------------------------------------------------
    def mk(self, install=True, text_patch=None):
        sim = ks.Sim(str(PAYLOAD), self.BASE, self.SIZE)
        for a, d in self.secdata:
            sim.write_pa(a, d)
        for pa, word in (text_patch or {}).items():
            sim.write_pa(pa, struct.pack("<I", word))
        sim.write_pa(self.BAD, b"\xff" * 8)
        if install:
            rc = self.call(sim, "nat031_install", [self.BASE, VIRT, self.BAD])
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
        sim.sr.update({"ttbr1_el1": 0xdead0001000, "tcr_el1": 0x1234, "vbar_el1": 0xbeef000})   # whatever S-Boot left: the model has no value

    def log(self, sim):
        n = struct.unpack("<I", sim.read_pa(self.syms["mock_n"], 4))[0]
        return [struct.unpack("<10Q", sim.read_pa(self.syms["mock_log"] + 80 * i, 80)) for i in range(n)]

    def held(self, sim):
        return struct.unpack("<I", sim.read_pa(self.syms["mock_held"], 4))[0]

    def run_to_hold(self, sim):
        sim.run(stop_pcs={self.syms["mk_ckpt_hold"]}, limit=200000)
        try:                                                    # let the mock hold record, then it spins
            sim.run(limit=sim.steps + 60)
        except ks.SimFault as e:
            self.assertEqual(e.kind, "step-limit")

    def slot_words(self, sim):
        pa = sim.pa_of_kva(SLOT_VA)
        return struct.unpack("<4Q", sim.read_pa(pa, 32))

    def frame(self, sim):
        return struct.unpack("<32Q", sim.read_pa(self.stack - 0x100, 256))

    # --- tests -----------------------------------------------------------------------------------
    def test_compiled_install_fills_the_slot_and_the_chain_stops_at_five_in_order(self):
        sim = self.mk()
        self.assertEqual(self.slot_words(sim), (0x545352444c554e58, self.stub, 1, (self.BASE - VIRT) & M64))
        self.run_to_hold(sim)
        recs = self.log(sim)
        self.assertEqual(self.held(sim), 1)
        self.assertEqual([(r[0], r[1]) for r in recs], [(2, n) for n in range(1, 6)])
        self.assertEqual([(r[9] & 0xffffffff, r[9] >> 32) for r in recs], [(0x2, 1), (0x6, 2), (0xe, 3), (0x1e, 4), (0x3e, 5)])
        self.assertEqual([r[2] & 1 for r in recs], [0] * 5)                                       # SCTLR_EL1.M is clear at every stop
        # the system registers the kernel has written by checkpoint 4 (model values, NAT-030): TTBR1/TCR/VBAR
        self.assertEqual((recs[3][3], recs[3][4], recs[3][5]), (0x9e15af000, 0x22a51a251a, 0xfffffff007437000))
        self.assertEqual(self.slot_words(sim)[2], 5)                                              # the loader wrote 2, 3, 4, 5 and the kernel never changed it
        self.assertFalse(sim.violations)

    def test_resumed_chain_reaches_five_in_the_state_of_a_direct_run(self):
        a = self.mk(); self.run_to_hold(a)
        b = self.mk()
        b.write_pa(b.pa_of_kva(SLOT_VA) + 16, struct.pack("<Q", 5)); self.run_to_hold(b)
        self.assertEqual(len(self.log(b)), 1)
        fa, fb = self.frame(a), self.frame(b)
        self.assertEqual(fa, fb)                                                                  # x0..x30 and the SP the kernel had at checkpoint 5
        self.assertEqual(fa[31], self.KSP)
        self.assertEqual({k: v for k, v in a.sr.items() if v != b.sr.get(k)}, {})
        loader = range(0x9e2d80000, 0x9e2e20000)
        diff = [k + o for k in sorted(set(a.pages) | set(b.pages)) if a.pages.get(k, bytes(4096)) != b.pages.get(k, bytes(4096))
                for o in range(0, 4096, 8) if a.pages.get(k, bytes(4096))[o:o + 8] != b.pages.get(k, bytes(4096))[o:o + 8]]
        self.assertTrue(diff)                                                                     # the loader's own log differs ...
        self.assertTrue(all(x in loader for x in diff), [hex(x) for x in diff if x not in loader])  # ... and no kernel word does

    def arrive(self, sim, regs, sp, fn_stop=None):
        """Enter nat031_stub as the kernel's checkpoint macro would, with `regs` = {n: value}."""
        sim.x = [0] * 31
        for n, v in regs.items():
            sim.x[n] = v
        sim.spsel = 0; sim.sp_el = [sp, 0]
        sim.pc = self.stub
        sim.steps = 0

    def crafted_regs(self, x2, x3):
        r = {n: 0x1111111111111111 * (n % 15 + 1) ^ n for n in range(4, 31) if n not in (9, 10, 11)}
        r.update({0: 0, 1: 0, 2: x2, 3: x3, 9: 0xaaaa, 10: 0xbbbb, 11: 0xcccc})
        return r

    def resume_pc(self, sim, n):
        return sim.pa_of_kva(SITES[n - 1]) + 60

    def after_bl(self, sim):
        """Address of the instruction after the stub's `bl nat031_ckpt_c`."""
        for i in range(60):
            w = struct.unpack("<I", sim.read_pa(self.stub + 4 * i, 4))[0]
            if w >> 26 == 0b100101:
                return self.stub + 4 * (i + 1)
        raise AssertionError("no bl in the stub")

    def resume(self, sim, n, hostile=True):
        """Run an arrival that resumes to the continuation. `hostile`: when the C code has returned, every register it may
        legally have changed (all but x0, the return value) is poisoned, so only the stub's own restores can bring the kernel's values back."""
        if hostile:
            sim.run(stop_pcs={self.after_bl(sim)}, limit=100000)
            for r in [*range(1, 29), 29, 30]:
                sim.x[r] = 0xbad0bad0bad0bad0 + r
        sim.run(stop_pcs={self.resume_pc(sim, n)}, limit=100000)

    def test_the_stub_restores_every_live_register_and_the_sp_and_lands_on_the_continuation(self):
        for n in range(1, 5):
            sim = self.mk()
            for k in range(1, n):                       # the loader's expectation must be n: walk it there with real arrivals
                self.arrive(sim, self.crafted_regs(2, k), self.KSP)
                self.resume(sim, k, hostile=False)
            regs = self.crafted_regs(2, n)
            self.arrive(sim, regs, self.KSP + 0x40 * n)
            self.resume(sim, n)
            live = [r for r in range(4, 31) if r not in (9, 10, 11)]
            self.assertEqual({r: sim.x[r] for r in live}, {r: regs[r] for r in live}, n)
            self.assertEqual(sim.sp_el[sim.spsel], self.KSP + 0x40 * n)
            self.assertEqual(self.slot_words(sim)[2], n + 1)
            self.assertEqual(self.held(sim), 0)

    def test_every_restore_instruction_matters(self):
        """Mutation check of the test above: replacing any one of the restore loads by a nop must make it fail."""
        sim0 = self.mk()
        ret = self.syms["nat031_stub"]
        words = [struct.unpack("<I", sim0.read_pa(ret + 4 * i, 4))[0] for i in range(60)]
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        # x0..x3 and x9..x11 are overwritten by the kernel's macro / by the stub itself: removing their reloads is not observable.
        free = {"x0, x1", "x2, x3", "x10, x11"}
        restores = []
        end = words.index(0xd61f0120)                    # the stub ends with `br x9`
        for i in range(25, end):
            ins = next(md.disasm(struct.pack("<I", words[i]), 0))
            if ins.mnemonic in ("ldp", "ldr") and ins.op_str.split(", [")[0] not in free:
                restores.append(ret + 4 * i)
        self.assertEqual(len(restores), 11 + 3)          # eleven ldp pairs (x4..x29 without x8-x11), plus the loads of x30, x8 and the SP
        # The unmutated stub passes the same check (it is what the previous test shows; here it is the control).
        sim = self.mk(); regs = self.crafted_regs(2, 1); self.arrive(sim, regs, self.KSP); self.resume(sim, 1)
        self.assertEqual({r: sim.x[r] for r in range(4, 31) if r not in (9, 10, 11)}, {r: regs[r] for r in range(4, 31) if r not in (9, 10, 11)})
        for pa in restores:
            sim = self.mk(text_patch={pa: 0xd503201f})
            regs = self.crafted_regs(2, 1)
            self.arrive(sim, regs, self.KSP)
            self.resume(sim, 1)
            live = [r for r in range(4, 31) if r not in (9, 10, 11)]
            ok = {r: sim.x[r] for r in live} == {r: regs[r] for r in live} and sim.sp_el[sim.spsel] == self.KSP
            self.assertFalse(ok, "removing the instruction at %#x changed nothing the test can see" % pa)

    def test_unexpected_arrivals_hold_and_report_what_they_were_given(self):
        for regs, mask, name in (({2: 1, 3: 0x96000045, 4: 0xfffffff00743e0b0, 5: 0xdeadbeef}, 1 << 8, "exception"),
                                 ({2: 0}, 1 << 9, "orderly"), ({2: 2, 3: 3}, 1 << 10, "checkpoint 3 first"),
                                 ({2: 2, 3: 5}, 1 << 10, "checkpoint 5 first"), ({2: 2, 3: 6}, 1 << 10, "unknown checkpoint"), ({2: 7, 3: 1}, 1 << 10, "unknown reason")):
            sim = self.mk()
            merged = {**self.crafted_regs(2, 1), **regs}
            self.arrive(sim, merged, self.KSP)
            self.run_to_hold(sim)
            (rec,) = self.log(sim)
            self.assertEqual((rec[0], rec[1]), (merged[2], merged[3]), name)
            self.assertEqual((rec[6], rec[7], rec[8]), (merged[3], merged[4], merged[5]), name)    # ESR, ELR, FAR = x3, x4, x5
            self.assertEqual((rec[9] & 0xffffffff, rec[9] >> 32), (mask, 1), name)
            self.assertEqual(self.held(sim), 1)
            self.assertEqual(self.slot_words(sim)[2], 1, name)                                    # a hold never advances the slot

    def test_repeating_a_checkpoint_holds(self):
        sim = self.mk()
        self.arrive(sim, self.crafted_regs(2, 1), self.KSP)
        self.resume(sim, 1, hostile=False)
        self.arrive(sim, self.crafted_regs(2, 1), self.KSP)
        self.run_to_hold(sim)
        last = self.log(sim)[-1]
        self.assertEqual((last[9] & 0xffffffff, last[9] >> 32), (0x2 | 1 << 10, 2))
        self.assertEqual(self.held(sim), 1)

    def test_compiled_install_refuses_a_changed_site_and_writes_nothing(self):
        sim = ks.Sim(str(PAYLOAD), self.BASE, self.SIZE)
        for a, d in self.secdata:
            sim.write_pa(a, d)
        site = sim.pa_of_kva(SITES[2]) + 4 * 8                                                    # `mov x3, #3` of site 3
        w = struct.unpack("<I", sim.read_pa(site, 4))[0]
        sim.write_pa(site, struct.pack("<I", w ^ (1 << 5)))
        before = self.slot_words(sim)
        sim.write_pa(self.BAD, b"\xff" * 8)
        self.assertEqual(self.call(sim, "nat031_install", [self.BASE, VIRT, self.BAD]), 2)
        self.assertEqual(struct.unpack("<I", sim.read_pa(self.BAD, 4))[0], 3)
        self.assertEqual(self.slot_words(sim), before)


def nm_sizes(elf):
    out = subprocess.run(["nm", "-S", "--defined-only", str(elf)], capture_output=True, text=True, check=True).stdout
    res = {}
    for l in out.splitlines():
        f = l.split()
        if len(f) == 4:
            res[f[3]] = (int(f[0], 16), int(f[1], 16))
        elif len(f) == 3:
            res[f[2]] = (int(f[0], 16), 0)
    return res


@unittest.skipUnless(zig_ok() and (ROOT / "artifacts/nat-020/build-003/source").exists() and (ROOT / "artifacts/nat-022/build-003/build.json").exists(),
                     "zig, the NAT-020 build-003 source or the build-003 record is missing")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "o"
        r = subprocess.run([sys.executable, str(HERE / "build.py"), "--out", str(cls.out), "--loader-source", str(ROOT / "artifacts/nat-020/build-003/source")],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.rec = json.loads((cls.out / "build.json").read_text())

    def test_every_earlier_image_is_byte_identical(self):
        old = json.loads((ROOT / "artifacts/nat-022/build-003/build.json").read_text())["images"]
        for n, v in old.items():
            self.assertEqual(self.rec["images"][n]["sha256"], v["sha256"], n)
        b8 = ROOT / "artifacts/nat-022/build-008/build.json"
        if b8.exists():                                                      # the image that ran in native run 007
            ref = json.loads(b8.read_text())
            for n, v in ref["images"].items():
                self.assertEqual(self.rec["images"][n]["sha256"], v["sha256"], n)
            for n, v in ref["image_payloads"].items():
                self.assertEqual(self.rec["image_payloads"][n]["sha256"], v["sha256"], n)
        self.assertNotIn("loader-diag-xnu-ckpt", old)

    def test_the_ckpt_loader_differs_from_the_last_run_loader_in_the_documented_places_only(self):
        import difflib
        o = self.out
        a = (o / "loader-diag-trig-hold-adt8-aln/source/shim/e1s-xnu/loader.c").read_text().splitlines()
        c = (o / "loader-diag-xnu-ckpt/source/shim/e1s-xnu/loader.c").read_text()
        diff = [l for l in difflib.unified_diff(a, c.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        self.assertEqual([l for l in diff if l[0] == "-"], ["-\tNAT022_HOLD(MK_ST_PRE_JUMP, 0); /* loader-diag-trig: never jump */"])
        self.assertEqual(c.count("nat031_install("), 1)
        self.assertEqual(c.count("NAT022_HOLD(MK_ST_PRE_JUMP"), 0)
        self.assertNotIn("nat028_install_stub", c)                                           # no entry stub: the kernel's own first word runs
        i_inst, i_clean_stage, i_clean, i_ret = (c.index(x) for x in ("nat031_install(", "NAT022_STAGE(MK_ST_LOADER_CLEAN)", "clean(win_base, mem_end);", "return entry_pa;"))
        self.assertLess(i_inst, i_clean_stage); self.assertLess(i_clean_stage, i_clean); self.assertLess(i_clean, i_ret)      # the fill is cleaned with the window
        self.assertLess(c.index("uintptr_t entry_pa ="), i_inst)
        for f in ("adt_patch.c", "ui.c", "fdt.c", "gic.c", "guard.c", "s5e9945.c"):
            self.assertEqual((o / "loader-diag-xnu-ckpt/source/shim/e1s-xnu" / f).read_bytes(), (o / "loader-diag-trig-hold-adt8-aln/source/shim/e1s-xnu" / f).read_bytes(), f)
        ip = self.rec["image_payloads"]
        img = o / "loader-diag-xnu-ckpt/Image"
        newp = (o / ip["loader-diag-xnu-ckpt"]["path"]).read_bytes()
        refp = (o / ip["loader-diag-xnu-entry"]["path"]).read_bytes()
        oldimg = (o / "loader-diag-xnu-entry/Image").stat().st_size
        self.assertEqual(newp[img.stat().st_size:], refp[oldimg:])                           # the SWEETXNU payload is the bytes of run 007

    def test_the_stub_and_checkpoint_code_has_no_simd_and_no_misaligned_access(self):
        if capstone is None:
            self.skipTest("capstone missing")
        d = self.out / "loader-diag-xnu-ckpt"
        sizes = nm_sizes(d / "loader.elf")
        img = (d / "Image").read_bytes()
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM); md.detail = True
        simd = re.compile(r"^[vqdsbh]\d+$")
        def regs_of(fn):
            a, n = sizes[fn]
            self.assertGreater(n, 0, fn)
            out = []
            for ins in md.disasm(img[a:a + n], a):
                names = {md.reg_name(r) for r in list(ins.regs_read) + list(ins.regs_write)}
                names |= {md.reg_name(op.reg) for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG and op.reg}
                if any(simd.match(x or "") for x in names):
                    out.append((hex(ins.address), ins.mnemonic, ins.op_str))
            return out
        for fn in ("nat031_check", "nat031_prepare", "nat031_decide", "nat031_set_next", "nat031_install", "nat031_ckpt_c", "nat031_site_va"):
            self.assertEqual(regs_of(fn), [], fn)
        stub = sizes["nat031_stub"][0]
        for ins in md.disasm(img[stub:stub + 0x100], stub):
            if ins.mnemonic == "br":
                break
            self.assertFalse(any(simd.match(md.reg_name(op.reg) or "") for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG), (ins.mnemonic, ins.op_str))
        r = subprocess.run([sys.executable, "-I", str(HERE / "scan_unaligned.py"), str(d / "Image"), "--elf", str(d / "loader.elf")], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.splitlines()), (0, ["total 0"]))

    def test_the_stub_symbol_is_16_byte_aligned_and_the_frame_fits_the_stack_contract(self):
        sizes = nm_sizes(self.out / "loader-diag-xnu-ckpt/loader.elf")
        self.assertEqual(sizes["nat031_stub"][0] % 16, 0)
        self.assertEqual(sizes["_stack_top"][0] % 16, 0)
        stub = (SRC / "ckpt_stub.S").read_text()
        self.assertIn("sub\tx10, x10, #0x100", stub)
        pre = stub[stub.index("nat031_stub:"):stub.index("bl\tnat031_ckpt_c")]
        self.assertEqual(pre.count("\tstp\t") * 2 + pre.count("\tstr\t") - 1, 31)           # x0..x30 saved, plus the kernel's SP: 32 words = 0x100

    def test_the_ckpt_image_is_the_only_one_that_references_the_hook(self):
        for n in self.rec["images"]:
            elf = self.out / n / "loader.elf"
            if not elf.exists():
                continue
            syms = subprocess.run(["nm", str(elf)], capture_output=True, text=True, check=True).stdout
            self.assertEqual("nat031_stub" in syms, n == "loader-diag-xnu-ckpt", n)
            self.assertEqual("mk_ckpt_hold" in syms, n == "loader-diag-xnu-ckpt", n)


DECISION = ROOT / "docs/decisions/0016-nat031-loader-diag-xnu-ckpt-single-run-2026-11-11.md"


@unittest.skipUnless((ROOT / "artifacts/nat-031/package-001/recovery.img").exists() and (ROOT / "devices/recovery/backups/2026-11-10/recovery.img").exists(),
                     "the NAT-031 package or the stock RECOVERY backup is missing")
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
            r = subprocess.run([sys.executable, str(HERE / "session_xnu_ckpt.py"), "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def test_no_decision_no_adb_in_any_mode(self):
        if DECISION.exists():
            self.skipTest("the owner decision exists: the gate is open")
        for mode in ((), ("--execute",), ("--restore",)):
            r, calls, rep = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(calls, "", mode)                                                  # not a single adb invocation
            self.assertEqual(rep["outcome"], "stopped")
            self.assertIn("owner decision 0016 is missing", rep["error"])                       # the hash and package assertions before it passed
            self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))

    def test_pinned_hashes_are_those_of_the_package(self):
        src = (HERE / "session_xnu_ckpt.py").read_text()
        pkg = json.loads((ROOT / "artifacts/nat-031/package-001/package.json").read_text())
        for h in (pkg["recovery_sha256"], pkg["source_image_sha256"], pkg["stock_sha256"]):
            self.assertIn(h, src)
        payload = ROOT / "artifacts/nat-031/build-002/loader-diag-xnu-ckpt/Image.payload"
        if payload.exists():
            self.assertIn("CANARY_LEN=%d" % payload.stat().st_size, src)
        self.assertEqual(src.count("reboot','recovery'"), 1)                                    # the only reboot of the session
        self.assertNotIn("fastboot", src.lower())


if __name__ == "__main__":
    unittest.main()
