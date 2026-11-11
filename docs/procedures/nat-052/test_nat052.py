#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-052 host tests: the image loader-diag-xnu-ckpt3-usb (the NAT-036 resumable C-checkpoint loader + the NAT-044 deadline/reset +
the NAT-047 USB log transport) and the glue between them. Evidence kind: host-test. Nothing here runs on, or is sent to, the phone.

    capvenv/bin/python -I docs/procedures/nat-052/test_nat052.py          (unicorn + capstone; zig, cc and the local NAT-020 artifacts)

Layers, each skips itself, and says why, when what it needs is missing:
  Decode     decode52.py against hand-made notes (nothing else needed).
  Patch      patch_ckpt52.py against the real loader source after the NAT-036 / NAT-044 / NAT-047 patches: every anchor exactly once,
             all-or-nothing, only the intended hunks, the order of the calls in nat036_ckpt_c, the frame kinds unique.
  Build      the image builds, twice identically; header; symbols; no SIMD and no misaligned access in the new code; the stub and the
             loader in one 2 MiB block at the three S-Boot bases seen; the engine, ladder and reset module are NAT-041/045/042's files.
  Chain      the patched ckpt3.c + the NAT-036 stub compiled for aarch64, run by the NAT-033/035 model on the payload kernel with the
             glue replaced by a recorder: one enter / note / pass / leave per arrival in that order, the hold without a leave, the
             token of every leave is the one its enter returned, and the end state still equals a run that was never stopped.
  Usb        the built loader.elf in unicorn with the NAT-041 DWC3 model behind the engine and the unmodified collector as the host:
             22 synthetic stops with kernel gaps in which nothing polls reach the archive complete and in order, the loader's
             vectors are installed while the stop is serviced and the kernel's are back afterwards, an early kernel exception is
             reported with ESR/ELR/FAR, the whole run ends before the reset deadline, the stack use is small.
The simulation has no caches, no MMU, no interrupts, no second CPU, no real controller and no real USB stack. It shows what the compiled
code does against NAT-041's reading of the databook; it is not a measurement of the S24 (README, risks)."""
import difflib
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
N22, N36, N41, N42, N44, N45, N47 = (PROC / n for n in ("nat-022", "nat-036", "nat-041", "nat-042", "nat-044", "nat-045", "nat-047"))
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
sys.path.insert(0, str(HERE / "test_support"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


d52 = _load("nat052_decode", HERE / "decode52.py")
p52 = _load("nat052_patch", HERE / "patch_ckpt52.py")
b52 = _load("nat052_build", HERE / "build.py")
t36 = _load("test_nat036", N36 / "test_nat036.py")
t47 = _load("test_nat047", N47 / "test_nat047.py")
try:
    import sim52 as S52
    import sim47 as S
    import rig47 as R
    from unicorn import arm64_const as A
    import unicorn
    HAVE_SIM = t47.HAVE_SIM
except ImportError:
    HAVE_SIM = False
try:
    import capstone
except ImportError:
    capstone = None

have_cc, have_zig = shutil.which("cc") is not None, shutil.which("zig") is not None
have_loader = LOADER_SRC.exists() and PAYLOAD.exists()
needs_loader = unittest.skipUnless(have_loader, "the local NAT-020 build-003 loader source/payload are missing")
needs_build = unittest.skipUnless(have_loader and have_zig, "zig or the local NAT-020 build-003 artifacts are missing")
needs_sim = unittest.skipUnless(have_loader and have_zig and have_cc and HAVE_SIM, "unicorn, cc, zig or the local NAT-020 artifacts are missing")

NAME = b52.NAME
SRC36, SRC52 = N36 / "src", HERE / "src"
DEFAULT_STOPS = tuple(t36.DEFAULT_STOPS)
MASK_FINAL = 1 << 13


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


_off = {}


def setups_offset():
    """offsetof(struct usbmon, setups): struct usbmon is the first member of g_nat047 (its size and the position of `up` after it are
    pinned by NAT-047's own tests, which take the same host compiler's layout)."""
    if "setups" not in _off:
        t = tempfile.TemporaryDirectory()
        c = Path(t.name) / "o.c"
        c.write_text('#include <stdio.h>\n#include <stddef.h>\n#include "usbmon.h"\n'
                     'int main(void){printf("%zu\\n", offsetof(struct usbmon, setups));return 0;}\n')
        r = subprocess.run(["cc", "-DUSBMON_TESTING", '-DUSBMON_PORT_HEADER="host_port.h"', "-I", str(N41 / "engine"), "-I", str(N41 / "model"),
                            str(c), "-o", str(Path(t.name) / "o")], capture_output=True, text=True)
        assert r.returncode == 0 and not r.stderr.strip(), r.stderr
        _off["setups"] = int(subprocess.run([str(Path(t.name) / "o")], capture_output=True, text=True, check=True).stdout)
        t.cleanup()
    return _off["setups"]


def changed(old, new):
    d = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return [l for l in d if l[0] == "-"], [l for l in d if l[0] == "+"]


# ------------------------------------------------------------------------------------------------------------------- build cache
_tmp = tempfile.TemporaryDirectory()
_built = {}


def built(deadline_s=60, service_tenths=3, stops=None, tag=""):
    key = (deadline_s, service_tenths, tuple(stops) if stops else None, tag)
    if key not in _built:
        out = Path(_tmp.name) / ("b%d" % len(_built))
        argv = [sys.executable, "-I", HERE / "build.py", "--out", out, "--loader-source", LOADER_SRC, "--deadline-s", deadline_s,
                "--service-tenths", service_tenths]
        if stops:
            argv += ["--stops", ",".join(map(str, stops))]
        r = subprocess.run([str(a) for a in argv], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-1500:] + r.stdout[-500:]
        _built[key] = out
    return _built[key]


def tearDownModule():
    _tmp.cleanup()
    for t in t47._scenario_tmp:
        t.cleanup()


def note_line(n, arr, last, x2=2, x3=None, mask=0, sctlr=0x3454593c, sp=0xfffffff007ab0000, kttbr0=0, vbar=0xfffffff007000000, setups=3, exc=None):
    s = "CK n=%d arr=%d last=%d x2=%#x x3=%#x mask=%#x sctlr=%#x sp=%#x kttbr0=%#x vbar=%#x setups=%d" % (
        n, arr, last, x2, last if x3 is None else x3, mask, sctlr, sp, kttbr0, vbar, setups)
    if exc:
        s += " esr=%#x elr=%#x far=%#x" % exc
    return s


# ------------------------------------------------------------------------------------------------------------------------ Decode
class Decode(unittest.TestCase):
    def test_a_note_round_trips_and_the_flags_come_from_the_values(self):
        n = d52.parse_note(note_line(7, 7, 33, sctlr=0x3454593d, kttbr0=0x9e15ae000, setups=14))
        self.assertEqual((n["n"], n["arr"], n["last"], n["x2"], n["x3"], n["setups"]), (7, 7, 33, 2, 33, 14))
        self.assertEqual((n["mmu_on"], n["exception"], n["kttbr0"]), (True, False, 0x9e15ae000))
        self.assertNotIn("esr", n)

    def test_an_exception_note_carries_esr_elr_far(self):
        n = d52.parse_note(note_line(3, 3, 5, x2=1, x3=0, exc=(0x96000045, 0xfffffff007441234, 0xdeadbeef000)))
        self.assertTrue(n["exception"])
        self.assertEqual((n["esr"], n["elr"], n["far"]), (0x96000045, 0xfffffff007441234, 0xdeadbeef000))

    def test_lines_that_are_not_notes_are_not_parsed(self):
        for line in ("", "loader: line 001", "CK n=1", note_line(1, 1, 1).replace("setups=3", "setups=x"), note_line(1, 1, 1) + " junk",
                     note_line(1, 1, 1).replace("x2=0x2", "x2=2")):
            self.assertIsNone(d52.parse_note(line), line)

    def test_progress_orders_gaps_the_hold_and_the_final_bit(self):
        lines = [note_line(1, 1, 1), "loader: noise", note_line(2, 2, 2), note_line(4, 4, 4, mask=MASK_FINAL), "HOLD stage=0x51 code=0x2000"]
        p = d52.progress(lines)
        self.assertEqual([s["n"] for s in p["stops"]], [1, 2, 4])
        self.assertEqual(p["gaps"], [(2, 4)])
        self.assertEqual((p["last"], p["held"], p["reached_final"]), (4, True, True))
        self.assertEqual(p["hold"], {"stage": 0x51, "code": 0x2000})
        self.assertIsNone(p["exception"])

    def test_progress_of_nothing_is_nothing(self):
        p = d52.progress([])
        self.assertEqual((p["stops"], p["last"], p["held"], p["reached_final"], p["gaps"]), ([], None, False, False, []))


# ------------------------------------------------------------------------------------------------------------------------- Patch
@needs_loader
class Patch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = Path(cls.tmp.name) / "src"
        shutil.copytree(LOADER_SRC, cls.src, ignore=shutil.ignore_patterns("out", ".git"))
        cls.wdt = b52.prepare_tree(cls.src, 60, final=False)
        cls.e = cls.src / "shim/e1s-xnu"
        cls.before = {n: (cls.e / n).read_text() for n in ("marker.h", "loader.c")}
        cls.out = {p.name: t for p, t in p52.derive(cls.e).items()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_markerlib52_is_markerlib3_with_the_four_intended_hunks(self):
        minus, plus = changed((SRC36 / "markerlib3.c").read_text(), self.out["markerlib52.c"])
        self.assertEqual(minus, ['-#include "markerlib.c"', "-\tld_after_draw();"])
        self.assertEqual(plus, ['+#include "markerlib47.c"', '+#include "glue52.h"', '+#include "glue52_impl.h"', "+\tnat052_service();",
                                "+\tnat047_hold(MK_ST_CKPT, r->mask);", "+\t\tnat047_show(&prev, &ld_k);"])

    def test_the_second_ld_after_draw_of_markerlib3_is_the_holds_and_stays(self):
        old = (SRC36 / "markerlib3.c").read_text()
        self.assertEqual(old.count("ld_after_draw();"), 2)
        self.assertEqual(self.out["markerlib52.c"].count("ld_after_draw();"), 1)
        hold = self.out["markerlib52.c"].split("mk_ckpt3_hold")[1]
        self.assertIn("ld_after_draw();", hold)
        self.assertLess(hold.index("ld_after_draw();"), hold.index("nat047_hold(MK_ST_CKPT"))

    def test_ckpt3_c_is_nat036s_with_the_vbar_swap_and_the_note_only(self):
        minus, plus = changed((SRC36 / "ckpt3.c").read_text(), self.out["ckpt3.c"])
        self.assertEqual(minus, ["-\tuint64_t ttbr0, ttbr1, tcr, vbar;"])
        self.assertEqual(plus, ['+#include "glue52.h"', "+\tuint64_t ttbr0, ttbr1, tcr, vbar, kv;", "+\tkv = nat052_vbar_enter();",
                                "+\tnat052_note_stop(&r);", "+\tnat052_vbar_leave(kv);"])

    def test_the_calls_in_nat036_ckpt_c_are_in_the_order_the_design_needs(self):
        body = self.out["ckpt3.c"].split("struct nat036_ret nat036_ckpt_c")[1]
        order = ["nat036_decide(", "nat036_report(", "kv = nat052_vbar_enter();", "nat052_note_stop(&r);", "mk_ckpt3_hold(&r);",
                 "mk_ckpt3_pass(&r);", "nat036_clear_flag(", "nat036_set_next(", "nat052_vbar_leave(kv);", "return ret;"]
        pos = [body.index(x) for x in order]
        self.assertEqual(pos, sorted(pos), dict(zip(order, pos)))
        self.assertEqual(body.count("return ret;"), 1)
        self.assertEqual(body.count("nat052_vbar_enter"), 1)
        self.assertEqual(body.count("nat052_vbar_leave"), 1)
        # the loader's vectors are in place for everything the loader does with the engine and the display, the set-next writes included
        self.assertLess(body.index("nat052_vbar_enter"), body.index("mk_ckpt3_hold"))
        self.assertLess(body.index("nat036_set_next(&nat036_st.s, d.next)"), body.index("nat052_vbar_leave"))

    def test_marker_h_moves_only_the_usb_kind_and_the_kinds_are_then_unique(self):
        minus, plus = changed(self.before["marker.h"], self.out["marker.h"])
        self.assertEqual(len(minus), len(plus), 1)
        self.assertIn("MK_USB = 13", minus[0])
        self.assertIn("MK_USB = 15", plus[0])
        kinds = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\s*(MK_[A-Z0-9]+) = (\d+),?\s", self.out["marker.h"], re.M)
                 if m.group(1) in ("MK_ENTRY", "MK_BOOTID", "MK_STAGE", "MK_ESR", "MK_ELR", "MK_FAR", "MK_SLOT", "MK_CHECK", "MK_REG", "MK_XNU",
                                   "MK_CKPT", "MK_CKPT2", "MK_USB", "MK_RST")}
        kinds["MK_CKPT3"] = int(re.search(r"#define MK_CKPT3 (\d+)", (SRC36 / "marker3.h").read_text()).group(1))
        self.assertEqual(len(kinds), 15, kinds)
        self.assertEqual(len(set(kinds.values())), len(kinds), "two report families share a frame kind: %s" % kinds)
        self.assertTrue(all(0 <= v < 16 for v in kinds.values()), kinds)
        self.assertEqual((kinds["MK_USB"], kinds["MK_CKPT3"], kinds["MK_RST"]), (15, 13, 14))

    def test_nat047s_decoder_still_says_13_and_this_image_is_why_it_must_not_be_used_on_its_frames(self):
        self.assertEqual(t47.d47.KIND_USB, 13)          # the NAT-047 image keeps 13; only this image uses 15 for the same family

    def test_loader_c_gets_the_declaration_and_the_one_call_right_after_the_bringup(self):
        minus, plus = changed(self.before["loader.c"], self.out["loader.c"])
        self.assertEqual(minus, [])
        self.assertEqual(plus, ["+void nat052_capture_vbar(void);", "+\tnat052_capture_vbar();"])
        t = self.out["loader.c"]
        self.assertEqual(t.count("nat052_capture_vbar();"), 1)
        i = t.index("nat047_bringup(")
        self.assertEqual(t[i:].split("\n")[1].strip(), "nat052_capture_vbar();")

    def test_nat047s_hunks_are_used_unchanged_except_the_one_loader_c_include_anchor(self):
        h, orig = p52.nat047_hunks()
        self.assertEqual(sorted(h), sorted(orig))
        for name in orig:
            self.assertEqual(len(h[name]), len(orig[name]), name)
            for mine, theirs in zip(h[name], orig[name]):
                if (name, mine[0]) == ("loader.c", "include"):
                    self.assertNotEqual(mine, theirs)
                else:
                    self.assertEqual(mine, theirs, (name, mine[0]))
        include = dict((k, (o, n)) for k, o, n in h["loader.c"])["include"]
        self.assertEqual(include[1].replace('#include "usb47.h"\n', ""), include[0])       # the replacement only adds the include

    def test_every_anchor_occurs_exactly_once_in_the_real_sources(self):
        srcs = {"markerlib52.c": (SRC36 / "markerlib3.c").read_text(), "ckpt3.c": (SRC36 / "ckpt3.c").read_text(),
                "marker.h": self.before["marker.h"], "loader.c": self.before["loader.c"]}
        for name, hunks in (("markerlib52.c", p52.MARKERLIB52), ("ckpt3.c", p52.CKPT3), ("marker.h", p52.MARKER_H), ("loader.c", p52.LOADER_C)):
            for key, old, _ in hunks:
                self.assertEqual(srcs[name].count(old), 1, (name, key))

    def test_a_missing_or_a_doubled_anchor_refuses_and_a_second_application_is_refused(self):
        hunks = p52.CKPT3
        text = (SRC36 / "ckpt3.c").read_text()
        with self.assertRaises(SystemExit):
            p52.patch_text("t", text.replace(hunks[0][1], "x"), hunks)
        with self.assertRaises(SystemExit):
            p52.patch_text("t", text + "\n" + hunks[0][1], hunks)
        once = p52.patch_text("t", text, hunks)
        with self.assertRaises(SystemExit):
            p52.patch_text("t", once, hunks)
        # all-or-nothing: derive() writes nothing, and main() writes all four or none
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "s"
            shutil.copytree(self.src, root)
            e = root / "shim/e1s-xnu"
            (e / "loader.c").write_text((e / "loader.c").read_text().replace("nat047_bringup(", "nat047_bringup_(", 1))
            snap = {p.name: p.read_bytes() for p in e.iterdir() if p.is_file()}
            with self.assertRaises(SystemExit):
                p52.main(["x", str(root)])
            self.assertEqual({p.name: p.read_bytes() for p in e.iterdir() if p.is_file()}, snap)

    def test_the_stop_note_buffer_is_big_enough_for_its_widest_line(self):
        impl = (SRC52 / "glue52_impl.h").read_text()
        self.assertIn("_Static_assert(N52_LABELS + N52_VALUES < NAT052_NOTE_MAX", impl)
        widest = note_line(-2147483648, -2147483648, -2147483648, x2=2 ** 64 - 1, x3=2 ** 64 - 1, mask=2 ** 64 - 1, sctlr=2 ** 64 - 1,
                           sp=2 ** 64 - 1, kttbr0=2 ** 64 - 1, vbar=2 ** 64 - 1, setups=-2147483648, exc=(2 ** 64 - 1,) * 3)
        self.assertLess(len(widest), int(re.search(r"#define NAT052_NOTE_MAX\s+(\d+)", impl).group(1)))
        self.assertIsNotNone(d52.parse_note(widest))

    def test_the_note_fields_are_written_in_the_order_the_decoder_reads(self):
        impl = (SRC52 / "glue52_impl.h").read_text()
        labels = re.findall(r'n47_s\(p, "([^"]+)"\)', impl.split("void nat052_note_stop")[1])
        written = [l.strip().rstrip("=").split()[-1] for l in labels]
        read = re.findall(r"([A-Za-z0-9]+)=\(\?P<", d52.NOTE.pattern)
        self.assertEqual(written, read)
        self.assertEqual(read, ["n", "arr", "last", "x2", "x3", "mask", "sctlr", "sp", "kttbr0", "vbar", "setups", "esr", "elr", "far"])


# ------------------------------------------------------------------------------------------------------------------------- Build
@needs_build
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = built()
        cls.out2 = Path(_tmp.name) / "again"
        r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--out", str(cls.out2), "--loader-source", str(LOADER_SRC),
                            "--deadline-s", "60", "--service-tenths", "3"], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]
        cls.rec = json.loads((cls.out / "build.json").read_text())
        cls.d = cls.out / NAME
        cls.elf = cls.d / "loader.elf"

    def test_the_image_is_reproducible(self):
        b = json.loads((self.out2 / "build.json").read_text())
        self.assertEqual((self.rec["images"], self.rec["image_payloads"]), (b["images"], b["image_payloads"]))

    def test_the_image_header_and_the_payload(self):
        img = (self.d / "Image").read_bytes()
        self.assertEqual(img[56:60], b"ARM\x64")
        self.assertEqual(struct.unpack_from("<Q", img, 8)[0], 0x80000)
        self.assertEqual(struct.unpack_from("<Q", img, 16)[0], len(img))
        pl = (self.d / "Image.payload").read_bytes()
        self.assertEqual(pl[len(img):], (self.d / "payload.adt8.bin").read_bytes())
        self.assertEqual(pl[:16] + pl[24:len(img)], img[:16] + img[24:])
        self.assertEqual((self.rec["device_used"], self.rec["flashed"], self.rec["kind"]), (False, False, "host-test"))
        self.assertEqual(self.rec["stops"], list(DEFAULT_STOPS))
        self.assertEqual(self.rec["image_meta"][NAME], {"reason": "0x12345601", "deadline_s": 60, "wdt_s": 83, "service_tenths": 3})

    def test_the_symbols_of_every_family_are_in_and_the_older_checkpoint_families_are_not(self):
        syms = subprocess.run(["nm", str(self.elf)], capture_output=True, text=True, check=True).stdout
        for s in ("nat036_stub", "nat036_ckpt_c", "mk_ckpt3_pass", "mk_ckpt3_hold", "nat052_vbar_enter", "nat052_vbar_leave", "nat052_note_stop",
                  "nat052_service", "nat052_capture_vbar", "nat047_bringup", "nat047_hold", "usbmon_poll", "nat044_tick", "s5e_reset_to"):
            self.assertRegex(syms, r"\b%s\n" % s)
        for s in ("nat034_stub", "nat031_stub", "mk_ckpt2_hold"):
            self.assertNotIn(s, syms)

    def test_the_sources_the_image_reuses_are_the_original_files(self):
        e = self.d / "source/shim/e1s-xnu"
        for f in ("marker3.h", "ckpt3_stub.S", "ckpt3.h"):
            self.assertEqual(sha(e / f), sha(SRC36 / f), f)
        for f in ("usb47.h", "markerlib47.c"):
            self.assertEqual(sha(e / f), sha(N47 / "src" / f), f)
        for f in ("glue52.h", "glue52_impl.h"):
            self.assertEqual(sha(e / f), sha(SRC52 / f), f)
        for f in ("s5e9945_reset.c", "s5e9945_reset.h"):
            self.assertEqual(sha(e / f), sha(N42 / "module" / f), f)
        for f, h in self.rec["nat041_engine"].items():
            self.assertEqual(sha(N41 / "engine" / f), h, f)
        for f, h in self.rec["nat045_ladder"].items():
            self.assertEqual(sha(N45 / "src" / f), h, f)

    @unittest.skipUnless(capstone, "capstone missing")
    def test_the_new_code_has_no_simd_and_no_misaligned_access(self):
        sizes = t36.NM_SIZES(self.elf)
        img = (self.d / "Image").read_bytes()
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        md.detail = True
        simd = re.compile(r"^[vqdsbh]\d+$")
        for fn in ("nat052_vbar_enter", "nat052_vbar_leave", "nat052_capture_vbar", "nat052_note_stop", "nat052_service", "nat036_ckpt_c",
                   "mk_ckpt3_pass", "mk_ckpt3_hold"):
            a, n = sizes[fn]
            self.assertGreater(n, 0, fn)
            for ins in md.disasm(img[a:a + n], a):
                names = {md.reg_name(r) for r in list(ins.regs_read) + list(ins.regs_write)}
                names |= {md.reg_name(op.reg) for op in ins.operands if op.type == capstone.arm64.ARM64_OP_REG and op.reg}
                self.assertFalse(any(simd.match(x or "") for x in names), (fn, hex(ins.address), ins.mnemonic))
        r = subprocess.run([sys.executable, "-I", str(N22 / "scan_unaligned.py"), str(self.d / "Image"), "--elf", str(self.elf)], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.splitlines()), (0, ["total 0"]))

    def test_the_stub_the_stack_the_log_and_the_end_of_the_loader_lie_in_one_2_mib_block_at_each_base_seen(self):
        s = t36.NM_SIZES(self.elf)
        offs = {n: s[n][0] for n in ("nat036_stub", "nat036_stub_end", "_stack_top", "loader_log", "_end")}
        self.assertEqual(s["_stack_top"][0] % 16, 0)
        self.assertLess(offs["_end"], 0x60000, offs)
        for base in (0x800a0000, 0x80180000, 0x801a0000):
            blocks = {n: (base + o - (1 if n.endswith("_end") else 0)) >> 21 for n, o in offs.items()}
            self.assertEqual(len(set(blocks.values())), 1, (hex(base), {n: hex(base + o) for n, o in offs.items()}))

    def test_no_compiler_warning_in_the_build(self):
        self.assertGreater(len(self.rec["commands"]), 15)
        warnings = []
        for c in self.rec["commands"]:
            self.assertEqual(c["exit_code"], 0, c["argv"])
            warnings += [l for l in c["stderr"].splitlines() if "warning:" in l]
        # the one warning the run-006 loader.c has always had (LOG_MAGIC is 8 characters in an 8-byte array); nothing of NAT-036/044/047/052 warns
        self.assertEqual(len(warnings), 1, warnings)
        self.assertRegex(warnings[0], r"/shim/e1s-xnu/loader\.c:67:\d+: warning: .*\[-Wunterminated-string-initialization\]$")

    def test_the_deadline_has_to_leave_the_nat044_margin_and_a_stop_list_changes_the_image(self):
        r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--check-only", "--loader-source", str(LOADER_SRC), "--deadline-s", "64"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("must be in (0, 63]", r.stderr + r.stdout)
        short = built(stops=(11, 30, 35))
        self.assertEqual(json.loads((short / "build.json").read_text())["stops"], [11, 30, 35])
        self.assertNotEqual(json.loads((short / "build.json").read_text())["images"][NAME]["sha256"], self.rec["images"][NAME]["sha256"])


# ------------------------------------------------------------------------------------------------------------------------- Chain
_ELF = {}


def compile52(stops, tag=""):
    """nat-036's compile36 with this image's ckpt3.c (derived from NAT-036's by patch_ckpt52) and the recording double of the glue."""
    key = (tuple(stops), tag)
    if key in _ELF:
        return _ELF[key]
    t = Path(_tmp.name) / ("m" + "_".join(map(str, stops)) + tag)
    t.mkdir()
    (t / "ckpt3.c").write_text(p52.patch_text("ckpt3.c", (SRC36 / "ckpt3.c").read_text(), p52.CKPT3))
    objs = []
    flags = [f for f in t36.bld.FLAGS if f != "-mgeneral-regs-only"]
    for name, src, extra in (("ckpt.c", t36.SRC22 / "ckpt.c", t36.bld.NO_SIMD + ["-DNAT034_IMAGE=1"]),
                             ("ckpt3.c", t / "ckpt3.c", t36.bld.NO_SIMD + ["-DNAT036_STOP_LIST=" + ",".join(map(str, stops))]),
                             ("mock.c", HERE / "test_support/nat052_mock.c", t36.bld.NO_SIMD),
                             ("ckpt3_stub.S", SRC36 / "ckpt3_stub.S", []), ("mockbss.S", N22 / "test_support/nat031_mock.S", [])):
        o = t / (name + ".o")
        subprocess.run(["zig", "cc", *flags, *extra, f"-I{SRC36}", f"-I{SRC52}", f"-I{t36.SRC22}", "-c", str(src), "-o", str(o)], check=True)
        objs.append(o)
    elf = t / "stub.elf"
    subprocess.run(["zig", "cc", "-target", "aarch64-freestanding", "-static", "-nostdlib", "-Wl,--build-id=none", "-Wl,-e,nat036_stub",
                    f"-Wl,-T,{N36 / 'test_support/nat036_mock.ld'}", *objs, "-o", str(elf)], check=True)
    secdata, syms = t36.t31.KernelChain.read_elf(elf)
    _ELF[key] = (elf, secdata, syms)
    return _ELF[key]


@t36.model
class Chain(t36.Harness):
    STOPS = (11, 30, 31, 32, 33, 34, 35, 12)
    _run = {}

    def new_sim(self, stops, **kw):
        old = t36.compile36
        t36.compile36 = compile52
        try:
            return super().new_sim(stops, **kw)
        finally:
            t36.compile36 = old

    @classmethod
    def runs(cls):
        if not cls._run:
            h = cls("run_marker")
            h.setUpClass.__func__(cls)
            chain, syms = h.new_sim(cls.STOPS)
            h.drive(chain, syms)
            direct, dsyms = h.new_sim([cls.STOPS[-1]], tag="direct")
            h.drive(direct, dsyms)
            cls._run = dict(chain=chain, syms=syms, direct=direct, dsyms=dsyms, h=h, ref=t36.cr.reference(cls.img, cls.STOPS[-1], adt_reg=0))
        return cls._run

    def run_marker(self):
        pass

    @staticmethod
    def events(sim, syms):
        n = struct.unpack("<I", sim.read_pa(syms["m52_n"], 4))[0]
        return [struct.unpack("<2Q", sim.read_pa(syms["m52_ev"] + 16 * i, 16)) for i in range(n)]

    def test_every_arrival_is_enter_note_pass_leave_in_that_order_and_the_hold_has_no_leave(self):
        r = self.runs()
        ev = self.events(r["chain"], r["syms"])
        n_arr = 5 + len(self.STOPS)
        self.assertEqual(r["h"].held(r["chain"], r["syms"]), 1)
        self.assertEqual(len(ev), 4 * (n_arr - 1) + 3)
        lasts = [1, 2, 3, 4, 5] + list(self.STOPS)
        for i in range(n_arr):
            if i < n_arr - 1:
                (k0, tok), (k1, note), (k2, passed), (k3, back) = ev[4 * i:4 * i + 4]
                self.assertEqual((k0, k1, k2, k3), (1, 3, 4, 2), i)
                self.assertEqual(back, tok, "arrival %d: the leave got a different token than its enter returned" % i)
            else:
                (k0, tok), (k1, note), (k2, passed) = ev[4 * i:4 * i + 3]
                self.assertEqual((k0, k1, k2), (1, 3, 5))
            self.assertEqual(note, lasts[i] | (i + 1) << 32, i)
            self.assertEqual(passed, lasts[i], i)
        toks = [e[1] for e in ev if e[0] == 1]
        self.assertEqual(len(set(toks)), len(toks))
        self.assertEqual(len([e for e in ev if e[0] == 2]), n_arr - 1)

    def test_the_kernel_state_after_the_last_stop_equals_an_uninterrupted_run(self):
        r = self.runs()
        c = t36.cr.compare_entry(r["ref"], r["chain"])
        self.assertEqual(c["strict"], {}, c)
        a, b = r["direct"], r["chain"]
        self.assertEqual(self.ram_outside_loader(a, b), [], "the resumed kernel's RAM differs from the unstopped run")
        self.assertEqual({k: (a.sr.get(k), b.sr.get(k)) for k in set(a.sr) | set(b.sr) if a.sr.get(k) != b.sr.get(k)}, {})
        self.assertEqual(r["chain"].violations, [])

    def test_the_direct_run_is_a_real_comparison(self):
        r = self.runs()
        self.assertEqual(len(self.events(r["direct"], r["dsyms"])), 4 * 5 + 3)                  # five assembly stops with a leave; the one C stop is the hold
        self.assertEqual(len(self.events(r["chain"], r["syms"])), 4 * (5 + len(self.STOPS) - 1) + 3)
        self.assertGreater(r["chain"].steps, r["direct"].steps)


# --------------------------------------------------------------------------------------------------------------------------- Usb
KV = 0xfffffff007000000                 # a kernel VBAR (a virtual address), different from the loader's

def arrivals(stops=DEFAULT_STOPS, exception_at=None):
    """The 5 assembly stops and the C stops of a list as the stub would hand them over: (x2, x3, sctlr, mask, kttbr0, esr/elr/far)."""
    out, mask = [], 0
    for i, last in enumerate([1, 2, 3, 4, 5] + list(stops)):
        mask |= 1 << min(last, 12)
        c = i >= 5
        a = dict(x2=2, x3=last, sctlr=0x3454593d if c else 0x3454593c, mask=mask, arr=i + 1, last=last, nstops=len(stops),
                 kttbr0=0x9e15ae000 if c else 0, sp=0xfffffff007ab0000 + 0x40 * i, vbar=KV)
        if exception_at is not None and i == exception_at:
            a.update(x2=1, x3=0, esr=0x96000045, elr=0xfffffff007441234, far=0xdeadbeef000)
        out.append(a)
    out[-1]["mask"] |= MASK_FINAL
    return out


def pack(a):
    return struct.pack("<13Q4I", a["x2"], a["x3"], a["sctlr"], 0x1111, 0x2222, a["vbar"], a.get("esr", 0), a.get("elr", 0), a.get("far", 0),
                       a["sp"], 0, 0, a["kttbr0"], a["mask"], a["arr"], a["last"], a["nstops"])


GAPS_S = [0.01] * 5 + [0.05, 0.2, 0.4, 0.9, 0.05, 0.2, 8.0, 0.05, 0.3, 1.0, 0.05, 0.2, 0.4, 2.0, 0.05, 0.3, 0.1]
STACK_FILL = 0xA5


class Usb52:
    """One simulated phone running the stops, and the unmodified collector as the host."""
    def __init__(self, arr, gaps, deadline_s=60, hold=True, io_timeout_ms=1000, stages=t47.STAGES_AFTER, dev_kw=None):
        self.arr, self.hold = arr, hold
        self.img = built(deadline_s)
        self.lib, table = t47.glue_lib()
        self.sim = sim = S52.Sim52(S.load_elf(self.img / NAME / "loader.elf"), self.lib, table, init=t47.INIT(), dev_kw=dev_kw)
        self.l0 = t47.field_base(self.lib)
        self.vbar_seen = []          # (where, VBAR) at the entry of the functions that service the engine
        self.depth = []              # stack depth (bytes below _stack_top) reached by one note + pass
        self.tokens = []
        self.setups_at_note = []     # the engine's own count of SETUP packets served, read just before each note is written
        self.loader_vbar = sim.sym("vectors")
        logbuf = S.LOAD + 0x60000
        sim.write(logbuf, t47.LOG)
        sim.watch("mk_ckpt3_hold")
        sim.queue_call("recovery_guard")
        sim.queue_call("mk_stage", 0x20)
        sim.queue_call("nat047_bringup", logbuf, len(t47.LOG))
        sim.queue_py(lambda s: s.set_vbar(self.loader_vbar))              # what the loader's start.S installed
        sim.queue_call("nat052_capture_vbar")
        for st in stages:
            sim.queue_call("mk_stage", st)
        base = S.LOAD + 0x70000
        top = sim.sym("_stack_top")
        for i, a in enumerate(arr):
            ptr = base + 128 * i
            sim.write(ptr, pack(a))
            last = i == len(arr) - 1
            sim.queue_py(lambda s: s.set_vbar(KV))                         # the kernel's vectors while it runs
            sim.queue_call("nat052_vbar_enter")
            sim.queue_py(lambda s: (self.tokens.append(s.done_calls[-1][1]),
                                    s.write(top - 0x4000, bytes([STACK_FILL]) * 0x4000)))
            sim.queue_py(lambda s: self.setups_at_note.append(s.g("g_nat047", setups_offset())))
            sim.queue_call("nat052_note_stop", ptr)
            sim.queue_py(lambda s: self.vbar_seen.append(("note-done", s.vbar())))
            if last and hold:
                sim.queue_call("mk_ckpt3_hold", ptr)
                break
            sim.queue_call("mk_ckpt3_pass", ptr)
            sim.queue_py(lambda s: (self.vbar_seen.append(("pass-done", s.vbar())), self.depth.append(self.used(s))))
            sim.queue_call("nat052_vbar_leave", KV)
            sim.queue_py(lambda s: self.vbar_seen.append(("left", s.vbar())))
            if gaps[i]:
                sim.queue_gap(gaps[i])
        self.colkw = dict(io_timeout_ms=io_timeout_ms, dead_after=30.0, grace=10.0)

    def used(self, s):
        top = s.sym("_stack_top")
        mem = s.read(top - 0x4000, 0x4000)
        i = 0
        while i < len(mem) and mem[i] == STACK_FILL:
            i += 1
        return 0x4000 - i

    def go(self, limit_s=75.0):
        sim = self.sim
        while not sim.g("g_nat047", self.l0 + 8) and sim.seconds() < 20:
            sim.advance(target_t=sim.t + 5 * S.STEP_V)
        self.up_at = sim.seconds()
        self.rig = R.Rig47(t47.TC, sim, t47.tmp_dir(), **self.colkw)
        self.rig.plug()
        self.stop = self.rig.go(limit_s)
        return self.result(self.rig)

    def go_blind(self, limit_s=75.0):
        """No host at all (the engine never came up, so there is nothing to enumerate): run the loader's thread to the deadline reset."""
        sim = self.sim
        while not sim.stopped and sim.seconds() < limit_s:
            sim.advance(target_t=sim.t + 50 * S.STEP_V)
        return self.result(None)

    def result(self, rig):
        sim = self.sim
        self.res = Res()
        res = self.res
        res.up = sim.g("g_nat047", self.l0 + 8)
        res.boots = [dict(name=d.name, frames=rig.frames(d), payload=rig.payload(d)) for d in rig.boot_dirs()] if rig else []
        res.errors, res.events, res.manifest = (rig.errors(), rig.events(), rig.manifest) if rig else ([], [], None)
        res.reset_s = sim.seconds(sim.reset_t) if sim.reset_t is not None else None
        res.seconds, res.gaps, res.blocked = sim.seconds(), [(sim.seconds(a), sim.seconds(b)) for a, b in sim.gaps], sim.gap_polls_blocked
        res.dev_viol, res.mmio_viol, res.model_viol = list(sim.dev.viol), list(sim.mmio_viol), self.lib.model_nviol()
        res.excs = list(sim.excs)
        res.done = list(sim.done_calls)
        res.vbar_seen, res.depth, res.tokens = list(self.vbar_seen), list(self.depth), list(self.tokens)
        res.setups_at_note = list(self.setups_at_note)
        res.loader_vbar, res.hold_t = self.loader_vbar, [sim.seconds(t) for t in sim.watched["mk_ckpt3_hold"]]
        res.stack_size = 0x10000
        return res

    def close(self):
        self.sim.close()


class Res:
    pass


_usb = {}


def usb_scenario(key, build):
    if key not in _usb:
        run = None
        try:
            run = build()
            _usb[key] = run.go()
        except S.RegionUnavailable as e:
            raise unittest.SkipTest(str(e))
        finally:
            if run is not None:
                run.close()
    return _usb[key]


def texts(boot):
    """The lines of the device's TEXT records in archive order (a record can hold several lines, and a line of the loader log can be split over two)."""
    return [l for f in boot["frames"] if "text" in f and f.get("dev_kind") == "text" for l in f["text"].split("\n")]


def sc_full():
    return usb_scenario(("full",), lambda: Usb52(arrivals(), GAPS_S))


def sc_exception():
    return usb_scenario(("exception",), lambda: Usb52(arrivals(exception_at=7), [0.05] * 22))


def sc_down():
    def b():
        run = Usb52(arrivals(DEFAULT_STOPS[:3]), [0.2] * 8, dev_kw=dict(follow=False))
        run.go = run.go_blind
        return run
    return usb_scenario(("down",), b)


def sc_short():
    return usb_scenario(("short",), lambda: Usb52(arrivals(DEFAULT_STOPS[:3]), [0.2] * 8))


@needs_sim
class UsbFull(unittest.TestCase):
    """5 assembly + 17 C stops, kernel gaps of 10 ms to 8 s in which nothing polls, the host on the bus from the engine's first moment."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_full()
        cls.boot = cls.r.boots[0] if cls.r.boots else None
        cls.p = d52.progress(texts(cls.boot)) if cls.boot else None

    def test_one_boot_one_clean_capture_no_violation_anywhere(self):
        r = self.r
        self.assertEqual(len(r.boots), 1)
        self.assertEqual(r.errors, [])
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))
        self.assertEqual(r.excs, [])

    def test_all_22_stops_arrive_in_order_none_missing_and_the_numbers_are_the_loaders_own(self):
        p = self.p
        self.assertEqual([s["n"] for s in p["stops"]], list(range(1, 23)))
        self.assertEqual(p["gaps"], [])
        self.assertEqual([s["last"] for s in p["stops"]], [1, 2, 3, 4, 5] + list(DEFAULT_STOPS))
        self.assertEqual([s["arr"] for s in p["stops"]], list(range(1, 23)))

    def test_the_values_of_the_stop_are_what_the_stub_handed_over(self):
        for s, a in zip(self.p["stops"], arrivals()):
            self.assertEqual((s["x2"], s["x3"], s["sctlr"], s["mask"], s["kttbr0"], s["sp"], s["vbar"]),
                             (a["x2"], a["x3"], a["sctlr"], a["mask"], a["kttbr0"], a["sp"], a["vbar"]))
        self.assertEqual([s["mmu_on"] for s in self.p["stops"]], [False] * 5 + [True] * 17)

    def test_the_hold_is_announced_and_comes_after_the_last_note(self):
        p = self.p
        self.assertTrue(p["held"])
        self.assertEqual(p["hold"]["stage"], 0x51)                       # MK_ST_CKPT
        self.assertEqual(p["hold"]["code"], arrivals()[-1]["mask"])
        self.assertTrue(p["reached_final"])
        lines = texts(self.boot)
        last_note = max(i for i, l in enumerate(lines) if l.startswith("CK n="))
        self.assertLess(last_note, max(i for i, l in enumerate(lines) if l.startswith("HOLD")))

    def test_the_earlier_log_is_there_too_and_before_the_first_stop(self):
        lines = texts(self.boot)
        first = min(i for i, l in enumerate(lines) if l.startswith("CK n="))
        self.assertTrue(any(l.startswith("LAD ") for l in lines[:first]))
        self.assertTrue(any("loader: line 000" in l for l in lines[:first]))

    def test_every_pass_is_serviced_with_the_loaders_vectors_and_the_kernels_are_back_after_it(self):
        seen = self.r.vbar_seen
        self.assertEqual(len(seen), 3 * 21 + 1)
        notes = [v for k, v in seen if k == "note-done"]
        passes = [v for k, v in seen if k == "pass-done"]
        left = [v for k, v in seen if k == "left"]
        self.assertEqual(len(notes), 22)
        self.assertEqual(len(set(notes + passes)), 1, "the stop was not serviced under one vector table")
        self.assertEqual(set(notes + passes), {self.r.loader_vbar})
        self.assertNotEqual(self.r.loader_vbar, KV)
        self.assertEqual(set(left), {KV})
        self.assertEqual(len(left), 21)

    def test_the_enter_returns_the_kernels_vbar_each_time(self):
        self.assertEqual(self.r.tokens, [KV] * 22)

    def test_the_gaps_really_stopped_the_engine_and_nothing_was_lost(self):
        r = self.r
        self.assertEqual(len(r.gaps), 22 - 1)
        self.assertGreater(r.blocked, 100)
        notes = [e for e in r.events if e["kind"] == "capture-error"]
        self.assertEqual(notes, [])
        self.assertEqual(self.p["gaps"], [])
        self.assertGreater(sum(s["setups"] for s in self.p["stops"][1:]), 20)

    def test_setups_is_what_the_engine_served_since_the_previous_note_not_a_running_total(self):
        total = self.r.setups_at_note                                    # the engine's own counter, read just before each note
        self.assertEqual(len(total), 22)
        self.assertEqual(total, sorted(total))
        want = [b - a for a, b in zip([0] + total[:-1], total)]
        self.assertEqual([s["setups"] for s in self.p["stops"]], want)
        self.assertGreater(want[-1], 0)

    def test_the_whole_run_is_over_before_the_deadline_with_room_to_spare(self):
        r = self.r
        self.assertEqual(len(r.hold_t), 1)
        floor = 22 * 0.3 + sum(GAPS_S[:21])                       # service windows and gaps asked for: the least the run can take
        self.assertGreater(r.hold_t[0], floor)
        self.assertLess(r.hold_t[0], 60 - 20, "the hold was entered at %.1f s of a 60 s deadline (floor %.1f s)" % (r.hold_t[0], floor))
        self.assertIsNotNone(r.reset_s)
        self.assertAlmostEqual(r.reset_s, 60.0, delta=3.0)

    def test_the_stack_the_note_and_the_pass_use_is_a_small_part_of_the_loaders_stack(self):
        self.assertEqual(len(self.r.depth), 21)
        self.assertGreater(min(self.r.depth), 0)
        self.assertLess(max(self.r.depth), 0x2000, max(self.r.depth))
        self.assertLess(max(self.r.depth), self.r.stack_size // 4)


@needs_sim
class UsbException(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = sc_exception()
        cls.p = d52.progress(texts(cls.r.boots[0])) if cls.r.boots else None

    def test_the_early_exception_is_reported_with_esr_elr_far_and_only_that_stop(self):
        p = self.p
        self.assertEqual([s["n"] for s in p["stops"]], list(range(1, 23)))
        exc = [s for s in p["stops"] if s["exception"]]
        self.assertEqual(len(exc), 1)
        self.assertEqual((exc[0]["n"], exc[0]["esr"], exc[0]["elr"], exc[0]["far"]), (8, 0x96000045, 0xfffffff007441234, 0xdeadbeef000))
        self.assertIs(p["exception"], exc[0])
        self.assertEqual([s for s in p["stops"] if not s["exception"] and "esr" in s], [])

    def test_the_run_is_otherwise_clean(self):
        self.assertEqual((self.r.errors, self.r.dev_viol, self.r.mmio_viol, self.r.model_viol), ([], [], [], 0))


@needs_sim
class UsbEngineDown(unittest.TestCase):
    """The ladder stopped (the power domain never reports on), so the engine never comes up: the stops must behave as in the video-only image."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_down()

    def test_the_engine_is_down_and_every_call_of_the_thread_completed(self):
        r = self.r
        self.assertEqual(r.up, 0)
        self.assertEqual(r.boots, [])
        names = [c[0] for c in r.done]
        self.assertEqual(names.count("nat052_note_stop"), 8)
        self.assertEqual(names.count("mk_ckpt3_pass"), 7)
        self.assertEqual(names.count("nat052_vbar_leave"), 7)
        self.assertEqual(r.excs, [])

    def test_the_vector_swap_does_not_depend_on_the_engine(self):
        seen = self.r.vbar_seen
        self.assertEqual(set(v for k, v in seen if k in ("note-done", "pass-done")), {self.r.loader_vbar})
        self.assertEqual(set(v for k, v in seen if k == "left"), {KV})

    def test_the_hold_is_reached_and_the_reset_comes_at_the_deadline_with_no_log(self):
        r = self.r
        self.assertEqual(len(r.hold_t), 1)
        self.assertAlmostEqual(r.reset_s, 60.0, delta=3.0)
        self.assertEqual(r.dev_viol, [])


@needs_sim
class UsbShort(unittest.TestCase):
    """A short list: the same reporting, 8 arrivals, to make sure nothing depends on the number of stops."""
    def test_eight_arrivals_and_the_hold(self):
        r = sc_short()
        p = d52.progress(texts(r.boots[0]))
        self.assertEqual([s["n"] for s in p["stops"]], list(range(1, 9)))
        self.assertTrue(p["held"] and p["reached_final"])
        self.assertEqual(p["last"], DEFAULT_STOPS[2])


if __name__ == "__main__":
    unittest.main()
