#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-044 host tests: the reset canary image `loader-diag-reset` (the run-006 loader + a deadline that ends the run with the
unmodified NAT-042 reset module). Evidence kind: host-test. Nothing here runs on, or is sent to, the phone.

    python3 -I docs/procedures/nat-044/test_nat044.py
    capvenv/bin/python -I docs/procedures/nat-044/test_nat044.py     # an interpreter with unicorn + capstone adds the Aarch64 layers

Layers, each skips itself, and says why, when what it needs is missing:
  Patch      patch_loader4.py against the real run-006 loader source: every anchor exactly once, all-or-nothing, the diff is the hunks.
  HostReset  the real markerlib.c (patched) + markerlib4.c + the NAT-042 module on x86 with a PMU register model: deadline,
             once-only, the RESET marker before the trigger, the register order, refusal/read-back failure, no arming without arm.
  Build      both images build, twice identically; header, size, no SIMD; the deadline is well inside the watchdog.
  Aarch64    the built loader.elf run by unicorn: the real mk_hold loop with the real aarch64 module, the framebuffer decoded at
             the instant of the trigger store, simulated time from the counter; and the real recovery_guard for the call order
             (snapshot first, deadline armed only after the watchdog armed).
The unicorn model has no caches, no MMU and no real memory attributes. It shows the register/memory contract of the new code in
the compiled loader; it is not a measurement of the S24."""
import importlib.util
import math
import os
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
N22, N42 = HERE.parent / "nat-022", HERE.parent / "nat-042"
SRC22, SRC42, SRC44 = N22 / "src", N42 / "module", HERE / "src"
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


dec44 = _load("nat044_decode", HERE / "decode44.py")
p4 = _load("nat044_patch", HERE / "patch_loader4.py")
dec = dec44.base
try:
    import unicorn
    from unicorn import arm64_const as A
    HAVE_UNICORN = True
except ImportError:
    HAVE_UNICORN = False
try:
    import capstone
except ImportError:
    capstone = None

have_cc = shutil.which("cc") is not None
have_zig = shutil.which("zig") is not None
have_loader = LOADER_SRC.exists() and PAYLOAD.exists()
needs_loader = unittest.skipUnless(have_loader, "the local NAT-020 build-003 loader source/payload are missing")
needs_build = unittest.skipUnless(have_loader and have_zig, "zig or the local NAT-020 build-003 artifacts are missing")
needs_cc = unittest.skipUnless(have_cc, "cc is missing")
needs_sim = unittest.skipUnless(have_loader and have_zig and HAVE_UNICORN, "unicorn, zig or the local NAT-020 artifacts are missing")

NORMAL, DOWNLOAD, BOOTLOADER, RECOVERY = 0x12345600, 0x12345601, 0x1234560D, 0x12345604
INFORM2, INFORM3, CMD, REBOOT = 0xB8, 0xBC, 0x190, 0x3C00
DEADLINE_S = 45
WDT_S = 83
DWELL_S = 1.2


# ---------------------------------------------------------------------------------------------------------------- build cache
_build_dir = None
_build_tmp = None


def built():
    """Build both images once per run (the real build.py, from a copy of the run-006 loader source)."""
    global _build_dir, _build_tmp
    if _build_dir is None:
        _build_tmp = tempfile.TemporaryDirectory()
        out = Path(_build_tmp.name) / "out"
        subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--out", str(out), "--loader-source", str(LOADER_SRC)],
                       check=True, capture_output=True, text=True)
        _build_dir = out
    return _build_dir


def tearDownModule():
    if _build_tmp is not None:
        _build_tmp.cleanup()


def patched_tree(dst):
    """The run-006 loader source, patched the way build.py patches it (NAT-022 patch_loader.py, NAT-022 markerlib, NAT-044 patch)."""
    src = Path(dst) / "source"
    shutil.copytree(LOADER_SRC, src, ignore=shutil.ignore_patterns("out", ".git"))
    subprocess.run([sys.executable, "-I", str(N22 / "patch_loader.py"), str(src), "--trig-hold", "--adt-aligned"], check=True, capture_output=True)
    e = src / "shim/e1s-xnu"
    for f in ("marker.h", "markerlib.c"):
        shutil.copy(SRC22 / f, e)
    return src


def sh(argv, **kw):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True, **kw)


# ---------------------------------------------------------------------------------------------------------------------- Patch
@needs_loader
class Patch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = patched_tree(Path(cls.tmp.name) / "base")
        cls.e0 = cls.base / "shim/e1s-xnu"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fresh(self, name):
        d = Path(self.tmp.name) / name
        shutil.copytree(self.base, d / "source")
        return d / "source"

    def test_every_anchor_occurs_exactly_once_in_the_real_sources(self):
        for name, hunks in p4.HUNKS.items():
            text = (self.e0 / name).read_text()
            for key, old, _ in hunks:
                self.assertEqual(text.count(old), 1, "%s: %s" % (name, key))

    def test_the_patch_adds_the_hunks_and_changes_nothing_else(self):
        import difflib
        src = self.fresh("applied")
        r = sh([sys.executable, "-I", HERE / "patch_loader4.py", src])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WDT 83 s", r.stdout)
        e = src / "shim/e1s-xnu"
        touched = sorted(p.name for p in e.iterdir() if p.is_file() and (self.e0 / p.name).read_bytes() != p.read_bytes())
        self.assertEqual(touched, sorted(p4.HUNKS))
        for name, hunks in p4.HUNKS.items():
            a = (self.e0 / name).read_text().splitlines(keepends=True)
            b = (e / name).read_text().splitlines(keepends=True)
            removed = [l[2:] for l in difflib.ndiff(a, b) if l.startswith("- ")]
            added = [l[2:] for l in difflib.ndiff(a, b) if l.startswith("+ ")]
            want_removed = [l for _, old, _ in hunks for l in old.splitlines(keepends=True)]
            want_added = [l for _, _, new in hunks for l in new.splitlines(keepends=True)]
            # every line of a hunk's old text is either kept in the new text or replaced by its edited form; nothing else moves
            self.assertTrue(set(removed) <= set(want_removed), name)
            self.assertTrue(set(added) <= set(want_added), name)
            self.assertEqual(len(added) - len(removed), len(want_added) - len(want_removed), name)

    def test_a_missing_or_duplicated_anchor_fails_before_anything_is_written(self):
        for case in ("missing", "duplicated"):
            src = self.fresh(case)
            g = src / "shim/e1s-xnu/guard.c"
            t = g.read_text()
            anchor = p4.HUNKS["guard.c"][2][1]
            g.write_text(t.replace(anchor, "") if case == "missing" else t + anchor)
            before = {n: (src / "shim/e1s-xnu" / n).read_bytes() for n in p4.HUNKS}
            r = sh([sys.executable, "-I", HERE / "patch_loader4.py", src])
            self.assertNotEqual(r.returncode, 0, case)
            self.assertIn("anchor", r.stderr + r.stdout)
            for n, b in before.items():
                self.assertEqual((src / "shim/e1s-xnu" / n).read_bytes(), b, "%s: %s was written" % (case, n))

    def test_the_hooks_sit_where_the_design_needs_them(self):
        src = self.fresh("order")
        sh([sys.executable, "-I", HERE / "patch_loader4.py", src])
        g = (src / "shim/e1s-xnu/guard.c").read_text()
        i_snap, i_before = g.index("nat044_snapshot(pmu);"), g.index('diagnostic_value("panic_inform_before"')
        i_arm_wdt, i_arm = g.index("s5e_wdt_arm(&w,83)"), g.index("nat044_arm();")
        self.assertLess(i_snap, i_before)           # the snapshot reads the words S-Boot left, before anything touches them
        self.assertLess(i_arm_wdt, i_arm)           # the deadline is measured from after the watchdog armed
        self.assertEqual(g.count("nat044_arm();"), 1)
        m = (src / "shim/e1s-xnu/markerlib.c").read_text()
        self.assertEqual(m.count("nat044_tick();"), 2)      # the busy wait and the host/skip-wait branch
        self.assertEqual(m.count("nat044_show(&prev, &ld_k);"), 1)

    def test_wdt_seconds_parses_the_guard(self):
        self.assertEqual(p4.wdt_seconds((self.e0 / "guard.c").read_text()), WDT_S)
        with self.assertRaises(SystemExit):
            p4.wdt_seconds("int x;")


# ------------------------------------------------------------------------------------------------------------------ HostReset
@needs_cc
class HostReset(unittest.TestCase):
    """markerlib.c (patched) + markerlib4.c + the unmodified NAT-042 module + a PMU model, on x86, driving the real mk_hold."""
    deadline = DEADLINE_S

    @classmethod
    def build(cls, deadline, reason, tag):
        t = Path(cls.tmp.name) / tag
        shutil.copytree(SRC22, t)
        for f in ("marker.h", "markerlib.c"):
            (t / f).write_text(p4.patch_text(f, (SRC22 / f).read_text()))
        for f in ("reset44.h", "markerlib4.c"):
            shutil.copy(SRC44 / f, t)
        for f in ("s5e9945_reset.h", "s5e9945_reset.c"):
            shutil.copy(SRC42 / f, t)
        for f in ("host_mk4.c", "reset_host.c"):
            shutil.copy(HERE / "test_support" / f, t)
        exe = t / "host_mk4"
        r = sh(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-DMK_HOST=1", "-DMK_TRIG=1", "-DMK_LOADER=1",
                f"-DNAT044_DEADLINE_S={deadline}", f"-DNAT044_REASON={reason}", f"-I{t}", t / "host_mk4.c", t / "markerlib4.c",
                t / "reset_host.c", "-o", exe])
        assert r.returncode == 0, r.stderr
        return exe

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = cls.build(DEADLINE_S, "S5E_REASON_DOWNLOAD", "dl")
        cls.exe_bl = cls.build(DEADLINE_S, "S5E_REASON_BOOTLOADER", "bl")
        cls.exe_short = cls.build(10, "S5E_REASON_DOWNLOAD", "short")
        cls.exe_off = cls.build(0, "S5E_REASON_DOWNLOAD", "off")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def go(self, draws, i3=NORMAL, i2=0x0AA50011, cmd=0xD, flags=(), exe=None):
        out = Path(self.tmp.name) / "fb.bin"
        p = subprocess.run([str(exe or self.exe), "reset44", str(draws), str(out), hex(i3), hex(i2), hex(cmd), *flags], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-300:] + p.stderr)
        ev = [l.split() for l in p.stdout.splitlines()]
        n = 0
        evs = []
        for e in ev:
            if e[0] == "DRAW":
                n += 1
                evs.append(("DRAW", dec.parse_frame(int(e[1], 16)), n))
            elif e[0] in ("PMUR", "PMUW", "SNAPSHOT"):
                evs.append((e[0], *[int(x, 16) for x in e[1:]]))
            else:
                evs.append((e[0],))
        return evs

    @staticmethod
    def after_snapshot(evs):
        return next(e[1] for e in evs if e[0] == "SNAPSHOT")

    @staticmethod
    def writes(evs):
        return [(e[1], e[2]) for e in evs if e[0] == "PMUW"]

    @staticmethod
    def frames(evs):
        return [e[1] for e in evs if e[0] == "DRAW"]

    def test_every_drawn_frame_is_a_valid_frame(self):
        evs = self.go(80)
        self.assertTrue(all(f is not None for f in self.frames(evs)))

    def test_the_trigger_comes_at_the_deadline_not_before_and_the_marker_is_drawn_first(self):
        evs = self.go(200)
        self.assertEqual(evs[-1], ("WAIT",))                                 # the module's wait after the trigger = the reset
        trig = max(i for i, e in enumerate(evs) if e[0] == "PMUW")
        self.assertEqual(evs[trig][1:], (REBOOT, 2))
        last_draw = max(i for i, e in enumerate(evs[:trig]) if e[0] == "DRAW")
        f = evs[last_draw][1]
        self.assertEqual((f["kind"], f["idx"], f["data"]), (3, 0, 0x41))     # the RESET stage frame is the last thing drawn
        self.assertEqual([e[0] for e in evs[last_draw + 1:trig]].count("DRAW"), 0)
        self.assertEqual(evs[last_draw + 1][:2], ("PMUR", INFORM2))          # ... and the module's first access follows it directly
        snap = next(i for i, e in enumerate(evs) if e[0] == "SNAPSHOT")
        self.assertEqual([e[0] for e in evs[snap + 1:last_draw] if e[0] in ("PMUR", "PMUW")], [])   # no PMU access between the snapshot and the marker
        hold_draws = sum(1 for e in evs[:last_draw] if e[0] == "DRAW")
        self.assertEqual(hold_draws, math.ceil(DEADLINE_S / DWELL_S))        # each draw costs one dwell: not before the deadline, at the first wait after it

    def test_the_vendor_register_order_with_exact_values(self):
        evs = self.go(200, i3=NORMAL, i2=0x0AA50011, cmd=0xD)
        self.assertEqual(self.writes(evs), [(INFORM2, 0x0A4E0011), (INFORM3, DOWNLOAD), (CMD, 0x8), (REBOOT, 2)])

    def test_the_bootloader_variant_writes_its_reason_and_the_fastboot_mode(self):
        evs = self.go(200, exe=self.exe_bl)
        self.assertEqual(self.writes(evs), [(INFORM2, 0x0A4E0011), (INFORM3, BOOTLOADER), (CMD, 0xB), (REBOOT, 2)])

    def test_the_deadline_scales_with_the_macro(self):
        evs = self.go(200, exe=self.exe_short)
        trig = max(i for i, e in enumerate(evs) if e[0] == "PMUW")
        self.assertEqual(sum(1 for e in evs[:trig] if e[0] == "DRAW") - 1, math.ceil(10 / DWELL_S))     # - 1: the RESET frame itself

    def test_a_zero_deadline_never_arms_and_never_touches_the_pmu_after_the_snapshot(self):
        evs = self.go(120, exe=self.exe_off)
        self.assertEqual(self.writes(evs), [])
        self.assertNotIn(("WAIT",), evs)
        self.assertEqual(sum(1 for e in evs if e[0] == "PMUR"), 3)                    # only the entry snapshot

    def test_without_the_arm_call_nothing_is_ever_written(self):
        evs = self.go(120, flags=("noarm",))
        self.assertEqual(self.writes(evs), [])
        self.assertNotIn(("WAIT",), evs)
        self.assertEqual(sum(1 for e in evs if e[0] == "PMUR"), 3)

    def test_arming_without_the_snapshot_never_arms_because_the_pmu_window_is_unknown(self):
        evs = self.go(120, flags=("nosnap",))
        self.assertNotIn(("WAIT",), evs)
        self.assertEqual(self.writes(evs), [])
        self.assertEqual([e for e in evs if e[0] == "PMUR"], [])

    def test_a_leftover_download_request_is_cleared_once_and_remembered(self):
        evs = self.go(10, i3=DOWNLOAD)
        self.assertEqual(self.after_snapshot(evs), NORMAL)
        self.assertEqual(self.writes(evs), [])                                        # the clearing store is the only write, and it is not a module access
        d = dec44.describe44(self.frames(evs))
        self.assertEqual(d["reset"]["inform3_at_entry"], "0x%08x" % DOWNLOAD)          # the original, not the cleared word
        st = d["reset"]["status"]
        self.assertTrue(st["leftover_request_cleared"] and st["armed"] and not st["fired"])

    def test_a_leftover_bootloader_request_is_cleared_too(self):
        evs = self.go(10, i3=BOOTLOADER)
        self.assertEqual(self.after_snapshot(evs), NORMAL)

    def test_other_leftover_words_are_not_touched_by_the_snapshot(self):
        for w in (NORMAL, RECOVERY, 0, 0xDEADBEEF):
            evs = self.go(10, i3=w)
            self.assertEqual(self.after_snapshot(evs), w, hex(w))
            d = dec44.describe44(self.frames(evs))
            self.assertEqual(d["reset"]["inform3_at_entry"], "0x%08x" % w)
            self.assertFalse(d["reset"]["status"]["leftover_request_cleared"])

    def test_the_hold_round_reports_the_entry_words(self):
        evs = self.go(14, i3=0x12345604, i2=0x0AA50011, cmd=0x0000000D)
        d = dec44.describe44(self.frames(evs))
        self.assertEqual(d["reset"]["inform3_at_entry"], "0x12345604")
        self.assertEqual(d["reset"]["inform2_at_entry"], "0x0aa50011")
        self.assertEqual(d["reset"]["reboot_cmd_at_entry"], "0x0000000d")
        self.assertEqual(d["reset"]["status"], dict(rc=0, rc_meaning=dec44.RC_NAMES[0], fired=False, armed=True,
                                                    leftover_request_cleared=False, leftover_request_clear_failed=False))

    def test_a_failed_readback_triggers_nothing_reports_the_result_and_is_not_retried(self):
        for flag, rc, writes in (("fail2", 2, [(INFORM2, 0x0A4E0011)]), ("fail3", 3, [(INFORM2, 0x0A4E0011), (INFORM3, DOWNLOAD)]),
                                 ("failc", 4, [(INFORM2, 0x0A4E0011), (INFORM3, DOWNLOAD), (CMD, 0x8)])):
            evs = self.go(120, flags=(flag,))
            self.assertEqual(self.writes(evs), writes, flag)                         # prepare stops at the register that did not read back
            self.assertNotIn(("WAIT",), evs, flag)
            fr = self.frames(evs)
            self.assertEqual(dec44.reset_attempts(fr), (1, [rc]), flag)              # one RESET frame, one result frame, ever
            i = next(i for i, f in enumerate(fr) if (f["kind"], f["idx"], f["data"]) == (3, 0, 0x41))
            self.assertEqual((fr[i + 1]["kind"], fr[i + 1]["idx"]), (14, 7), flag)   # the result frame follows at once
            self.assertEqual(dec44.status(fr[i + 1]["data"])["rc"], rc)
            self.assertTrue(dec44.status(fr[i + 1]["data"])["fired"])
            self.assertGreater(len(fr) - i, 40, flag)                                # the hold loop went on afterwards (no retry, no hang)

    def test_the_report_frames_are_exactly_the_documented_ones(self):
        fr = self.frames(self.go(40))
        rst = [f["idx"] for f in fr if f["kind"] == 14]
        self.assertEqual(rst[:14], list(range(7)) * 2)                               # idx 0..6 once per hold round, nothing else of kind 14
        self.assertTrue(all(i <= 6 for i in rst))                                    # idx 7 only after a failed attempt


# ------------------------------------------------------------------------------------------------------------------------ Build
@needs_build
class Build(unittest.TestCase):
    def test_both_images_exist_with_a_valid_header_and_fit_one_mebibyte(self):
        out = built()
        for name in ("loader-diag-reset", "loader-diag-reset-bl"):
            img = (out / name / "Image").read_bytes()
            self.assertEqual(img[56:60], b"ARM\x64")
            self.assertEqual(struct.unpack_from("<Q", img, 8)[0], 0x80000)
            self.assertEqual(len(img), struct.unpack_from("<Q", img, 16)[0])
            self.assertLess(len(img), 1 << 20)
            self.assertGreater((out / name / "Image.payload").stat().st_size, len(img))

    def test_the_two_images_differ_only_in_the_reason_word_and_the_mode(self):
        out = built()
        a = (out / "loader-diag-reset/Image").read_bytes()
        b = (out / "loader-diag-reset-bl/Image").read_bytes()
        self.assertEqual(len(a), len(b))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertTrue(diff)
        self.assertLess(len(diff), 24)                                         # a few constants, not a different program

    def test_the_build_is_reproducible(self):
        out2 = Path(tempfile.mkdtemp())
        try:
            r = sh([sys.executable, "-I", HERE / "build.py", "--out", out2 / "o", "--loader-source", LOADER_SRC])
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("loader-diag-reset", "loader-diag-reset-bl"):
                for f in ("Image", "Image.payload"):
                    self.assertEqual((out2 / "o" / name / f).read_bytes(), (built() / name / f).read_bytes(), "%s/%s" % (name, f))
        finally:
            shutil.rmtree(out2, ignore_errors=True)

    def test_the_deadline_is_well_inside_the_watchdog_and_the_build_refuses_a_late_one(self):
        self.assertLessEqual(DEADLINE_S, WDT_S - 20)
        out = Path(tempfile.mkdtemp())
        try:
            for secs in (WDT_S - 19, WDT_S, 0, 200):
                r = sh([sys.executable, "-I", HERE / "build.py", "--out", out / ("o%d" % secs), "--loader-source", LOADER_SRC, "--deadline-s", secs])
                self.assertNotEqual(r.returncode, 0, secs)
                self.assertIn("deadline", r.stderr + r.stdout)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_the_build_record_states_the_reason_and_deadline_each_image_was_built_with(self):
        import json
        out = built()
        h = header_defines(SRC42 / "s5e9945_reset.h")
        meta = json.loads((out / "build.json").read_text())["image_meta"]
        self.assertEqual(meta["loader-diag-reset"], dict(reason="0x%08x" % h["S5E_REASON_DOWNLOAD"], deadline_s=DEADLINE_S, wdt_s=WDT_S))
        self.assertEqual(meta["loader-diag-reset-bl"], dict(reason="0x%08x" % h["S5E_REASON_BOOTLOADER"], deadline_s=DEADLINE_S, wdt_s=WDT_S))

    def test_the_module_is_the_nat042_module_unmodified(self):
        out = built()
        import hashlib
        for f in ("s5e9945_reset.h", "s5e9945_reset.c"):
            got = hashlib.sha256((out / "loader-diag-reset/source/shim/e1s-xnu" / f).read_bytes()).hexdigest()
            self.assertEqual(got, hashlib.sha256((SRC42 / f).read_bytes()).hexdigest(), f)

    def test_the_new_code_is_compiled_without_simd_and_the_flags_are_the_loader_flags(self):
        import importlib
        b22 = _load("nat022_build_t", N22 / "build.py")
        self.assertIn("-mgeneral-regs-only", b22.FLAGS)
        self.assertIn("-ffreestanding", b22.FLAGS)

    def test_the_loader_enables_fp_simd_before_any_c_code_runs(self):
        # zig cc emits SIMD/FP registers even with -mgeneral-regs-only (NAT-022 build.py note; the NAT-044 code has q/d-register
        # copies too, e.g. in nat044_snapshot). That is safe only because start.S sets CPACR_EL1.FPEN and clears CPTR_EL2 before
        # the first call into C. (An earlier "no SIMD in the text" check here was vacuous: capstone's disasm() stopped after the
        # two instructions of the Image header, and the premise was wrong, so it was replaced by this property.)
        start = (built() / "loader-diag-reset/source/shim/e1s-xnu/start.S").read_text()
        for needle in ("msr\tcptr_el2, xzr", "mov\tx1, #(3 << 20)\t\t/* CPACR_EL1.FPEN */", "msr\tcpacr_el1, x2", "bl\tdiagnostic_begin"):
            self.assertEqual(start.count(needle), 1, needle)
        self.assertLess(start.index("msr\tcptr_el2, xzr"), start.index("msr\tcpacr_el1, x2"))
        self.assertLess(start.index("msr\tcpacr_el1, x2"), start.index("bl\tdiagnostic_begin"))
        self.assertLess(start.index("msr\tcpacr_el1, x2"), start.index("bl\trecovery_guard"))

    @unittest.skipUnless(capstone is not None, "capstone is missing")
    def test_the_clearing_store_is_ordered_before_its_read_back_in_the_compiled_snapshot(self):
        for name in ("loader-diag-reset", "loader-diag-reset-bl"):
            elf = ElfImage(built() / name / "loader.elf")
            a, code = elf.code("nat044_snapshot")
            cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
            seq = [(i.mnemonic, i.op_str) for i in cs.disasm(code, a)]
            self.assertEqual(len(seq) * 4, len(code), name)                 # the whole function decoded: no data inside it
            hits = [k for k in range(len(seq) - 2) if seq[k][0] == "str" and seq[k][1].endswith("#0xbc]")
                    and seq[k + 1] == ("dsb", "sy") and seq[k + 2][0] == "ldr" and seq[k + 2][1].endswith("#0xbc]")]
            self.assertEqual(len(hits), 1, "%s: INFORM3 store; dsb sy; INFORM3 load not found once in %r" % (name, seq))


# --------------------------------------------------------------------------------------------------------------------- aarch64
class ElfImage:
    """Just enough ELF64 to load a freestanding loader into the simulator: PT_LOAD segments and the symbol table via nm."""
    def __init__(self, path):
        b = Path(path).read_bytes()
        phoff, phentsize, phnum = struct.unpack_from("<Q", b, 32)[0], struct.unpack_from("<H", b, 54)[0], struct.unpack_from("<H", b, 56)[0]
        self.entry = struct.unpack_from("<Q", b, 24)[0]
        self.segments = []
        for i in range(phnum):
            t, flags, off, vaddr, paddr, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", b, phoff + i * phentsize)
            if t == 1:
                self.segments.append(dict(vaddr=vaddr, memsz=memsz, data=b[off:off + filesz], exec=bool(flags & 1)))
        out = sh(["nm", "-S", path]).stdout
        self.sym, self.size = {}, {}
        for line in out.splitlines():
            p = line.split()
            if len(p) == 4:
                self.sym[p[3]], self.size[p[3]] = int(p[0], 16), int(p[1], 16)
            elif len(p) == 3:
                self.sym[p[2]] = int(p[0], 16)

    def code(self, name):
        """(address, bytes) of a sized function symbol."""
        a, n = self.sym[name], self.size[name]
        for seg in self.segments:
            if seg["exec"] and seg["vaddr"] <= a and a + n <= seg["vaddr"] + len(seg["data"]):
                return a, seg["data"][a - seg["vaddr"]:a - seg["vaddr"] + n]
        raise AssertionError("no executable segment holds %s" % name)


def u32(b):
    return struct.unpack("<I", bytes(b))[0]


# Layout of struct nat044 (reset44.h), checked against the compiler in LayoutOffsets below
OFF = dict(pmu=0, t0=8, deadline_ticks=16, armed=24, fired=28, rc=32, cleared=36, inform2_0=40, inform3_0=44, cmd_0=48)


def header_defines(path):
    out = {}
    for m in re.finditer(r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)u?\b", Path(path).read_text(), re.M):
        out[m.group(1)] = int(m.group(2), 0)
    return out


class Constants(unittest.TestCase):
    def test_the_decoder_s_status_bits_are_the_header_s(self):
        h = header_defines(SRC44 / "reset44.h")
        self.assertEqual((dec44.ST_RC_MASK, dec44.ST_FIRED, dec44.ST_ARMED, dec44.ST_CLEARED, dec44.ST_CLEARFAIL),
                         tuple(h[k] for k in ("NAT044_ST_RC_MASK", "NAT044_ST_FIRED", "NAT044_ST_ARMED", "NAT044_ST_CLEARED", "NAT044_ST_CLEARFAIL")))

    def test_the_decoder_s_frame_kind_and_stage_are_what_the_patch_adds(self):
        text = "".join(new for hunks in p4.HUNKS.values() for _, _, new in hunks)
        self.assertEqual(int(re.search(r"MK_RST = (\d+)", text).group(1)), dec44.KIND_RST)
        self.assertEqual(int(re.search(r"MK_ST_RESET = (0x[0-9a-f]+)", text).group(1), 16), dec44.ST_RESET)
        self.assertNotIn(dec44.KIND_RST, dec.KINDS)                      # no kind of NAT-022's decoder is shadowed

    def test_the_module_reasons_are_the_vendor_words(self):
        h = header_defines(SRC42 / "s5e9945_reset.h")
        self.assertEqual((h["S5E_REASON_NORMAL"], h["S5E_REASON_DOWNLOAD"], h["S5E_REASON_BOOTLOADER"]), (NORMAL, DOWNLOAD, BOOTLOADER))
        self.assertEqual((h["S5E_PMU_INFORM2"], h["S5E_PMU_INFORM3"], h["S5E_PMU_REBOOT_CMD"], h["S5E_PMU_REBOOT"]), (INFORM2, INFORM3, CMD, REBOOT))
        self.assertEqual(h["S5E_PMU_BASE"], PMU)


@needs_cc
class LayoutOffsets(unittest.TestCase):
    def test_the_offsets_used_to_read_g_nat044_in_the_simulator_are_the_compiler_s(self):
        with tempfile.TemporaryDirectory() as t:
            c = Path(t) / "o.c"
            c.write_text('#include <stddef.h>\n#include <stdio.h>\n#include "reset44.h"\nint main(void){\n' +
                         "".join('printf("%s %%zu\\n", offsetof(struct nat044, %s));\n' % (k, k) for k in OFF) + "return 0;}\n")
            r = sh(["cc", f"-I{SRC44}", f"-I{SRC42}", "-DNAT044_DEADLINE_S=45", "-DNAT044_REASON=S5E_REASON_DOWNLOAD", c, "-o", Path(t) / "o"])
            self.assertEqual(r.returncode, 0, r.stderr)
            got = {l.split()[0]: int(l.split()[1]) for l in sh([Path(t) / "o"]).stdout.splitlines()}
            # the host struct has 8-byte pointers like the target, so the layout is the same
            self.assertEqual(got, OFF)


PMU, WDT, DECON, FB, STACK, STOPPAGE = 0x12860000, 0x10040000, 0x19100000, 0xFA200000, 0x7F000000, 0x7E000000
FREQ = 24_000_000
STEP = 24_000        # 1 ms of simulated time per counter read


class Stop(Exception):
    pass


class Sim:
    """The built loader.elf in unicorn, with a PMU/WDT/DECON0 register model, a framebuffer and a counter the test controls."""
    def __init__(self, elf, init=None):
        self.elf = elf
        self.mu = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
        self.clk0 = 5_000_000
        self.clk = self.clk0
        self.limit_s = 120.0
        self.pmu_events = []       # (kind, offset, value, clk)
        self.wdt_events = []
        self.calls = []            # code-hook hits: (name, clk)
        self.diag = []
        self.frames = []           # frames sampled at the start of the next draw
        self.fb_at_trigger = None
        self.trigger_clk = None
        self.fault_off = None      # the first read of this PMU offset after a store to it returns a different value
        self._written = set()
        self.wdt_fault = False
        self.stop_on_trigger = True
        mu = self.mu
        mapped = set()
        for seg in elf.segments:
            for page in range(seg["vaddr"] & ~0xFFF, (seg["vaddr"] + seg["memsz"] + 0xFFF) & ~0xFFF, 0x1000):
                if page not in mapped:                 # neighbouring segments share a page
                    mu.mem_map(page, 0x1000)
                    mapped.add(page)
            mu.mem_write(seg["vaddr"], seg["data"])
        mu.mem_map(PMU, 0x10000)
        mu.mem_map(WDT, 0x1000)
        mu.mem_map(DECON, 0x10000)
        mu.mem_map(FB, 0x900000)
        mu.mem_map(STACK, 0x10000)
        mu.mem_map(STOPPAGE, 0x1000)
        mu.mem_write(STOPPAGE, b"\x1f\x20\x03\xd5" * 16)        # nops: the stop address of a call
        mu.mem_write(DECON + 0x20, struct.pack("<I", 0x113))   # GLOBAL_CON: not video mode, DECON enabled
        mu.mem_write(DECON + 0x30, struct.pack("<I", 0x3063))
        for off, v in (init or {}).items():
            mu.mem_write(PMU + off, struct.pack("<I", v))
        mu.hook_add(unicorn.UC_HOOK_INSN, self._mrs, None, 1, 0, A.UC_ARM64_INS_MRS)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._pmu_w, None, PMU, PMU + 0xFFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_READ, self._pmu_r, None, PMU, PMU + 0xFFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._wdt_w, None, WDT, WDT + 0xFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_READ, self._wdt_r, None, WDT, WDT + 0xFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._draw_start, None, FB, FB + 7)

    # -- time
    def _mrs(self, uc, reg, cp, ud):
        if (cp.crn, cp.crm, cp.op0, cp.op1) == (14, 0, 3, 3):
            if cp.op2 == 2:                                     # CNTVCT_EL0
                self.clk += STEP
                if (self.clk - self.clk0) / FREQ > self.limit_s:
                    uc.emu_stop()
                uc.reg_write(reg, self.clk)
                return True
            if cp.op2 == 0:                                     # CNTFRQ_EL0
                uc.reg_write(reg, FREQ)
                return True
        return False

    def t(self, clk=None):
        return ((self.clk if clk is None else clk) - self.clk0) / FREQ

    # -- registers
    def _pmu_w(self, uc, access, addr, size, value, ud):
        off = addr - PMU
        self.pmu_events.append(("W", off, value & 0xFFFFFFFF, self.clk))
        self._written.add(off)
        if off == REBOOT and (value & 0xFFFFFFFF) == 2:
            self.trigger_clk = self.clk
            self.fb_at_trigger = self.sample_fb()
            if self.stop_on_trigger:
                uc.emu_stop()

    def _pmu_r(self, uc, access, addr, size, value, ud):
        off = addr - PMU
        cur = u32(uc.mem_read(addr, 4))
        if off == self.fault_off and off in self._written:
            cur ^= 1
            uc.mem_write(addr, struct.pack("<I", cur))
        self.pmu_events.append(("R", off, cur, self.clk))

    def _wdt_w(self, uc, access, addr, size, value, ud):
        self.wdt_events.append(("W", addr - WDT, value & 0xFFFFFFFF, self.clk))

    def _wdt_r(self, uc, access, addr, size, value, ud):
        off = addr - WDT
        if off == 8:                                            # WTCNT: counts down
            uc.mem_write(addr, struct.pack("<I", max(1, u32(uc.mem_read(addr, 4)) - 1000)))
        if off == 0 and self.wdt_fault:                         # WTCON reads back without the enable bits
            uc.mem_write(addr, struct.pack("<I", 0))
        self.wdt_events.append(("R", off, u32(uc.mem_read(addr, 4)), self.clk))

    # -- framebuffer
    def sample_fb(self):
        levels = [1.0 if self.mu.mem_read(FB + b * 0x40000, 8) != b"\0" * 8 else 0.0 for b in range(dec.BANDS)]
        return dec.decode_bands(levels)

    def _draw_start(self, uc, access, addr, size, value, ud):
        f = self.sample_fb()                                    # the previous draw is complete: band 0 is the first thing a draw writes
        if f:
            self.frames.append((f, self.clk))

    # -- running
    def hook_symbol(self, name, cb):
        self.mu.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, s, ud: cb(uc), None, self.elf.sym[name], self.elf.sym[name])

    def call(self, name, *args, max_insn=400_000_000):
        mu = self.mu
        mu.reg_write(A.UC_ARM64_REG_SP, STACK + 0xF000)
        for i, a in enumerate(args):
            mu.reg_write(A.UC_ARM64_REG_X0 + i, a)
        mu.reg_write(A.UC_ARM64_REG_X30, STOPPAGE)
        try:
            mu.emu_start(self.elf.sym[name], STOPPAGE, count=max_insn)
        except unicorn.UcError as e:
            raise AssertionError("%s: %s at pc=%#x" % (name, e, mu.reg_read(A.UC_ARM64_REG_PC)))
        return mu.reg_read(A.UC_ARM64_REG_X0)

    def g(self, field):
        base = self.elf.sym["g_nat044"] + OFF[field]
        return struct.unpack("<Q" if field in ("pmu", "t0", "deadline_ticks") else "<I", bytes(self.mu.mem_read(base, 8 if field in ("pmu", "t0", "deadline_ticks") else 4)))[0]

    def pmu_word(self, off):
        return u32(self.mu.mem_read(PMU + off, 4))

    def final_frames(self):
        f = self.sample_fb()
        return [x for x, _ in self.frames] + ([f] if f else [])


@needs_sim
class Aarch64Hold(unittest.TestCase):
    """The real aarch64 mk_hold loop, nat044_* and the NAT-042 module from the built loader.elf."""
    @classmethod
    def setUpClass(cls):
        out = built()
        cls.elf = {n: ElfImage(out / n / "loader.elf") for n in ("loader-diag-reset", "loader-diag-reset-bl")}

    def sim(self, image="loader-diag-reset", i3=NORMAL, i2=0x0AA50011, cmd=0xD, arm=True):
        s = Sim(self.elf[image], {INFORM3: i3, INFORM2: i2, CMD: cmd})
        s.call("nat044_snapshot", PMU)
        if arm:
            s.call("nat044_arm")
        return s

    def hold(self, s, limit=None):
        if limit:
            s.limit_s = limit
        s.mu.reg_write(A.UC_ARM64_REG_SP, STACK + 0xF000)
        s.mu.reg_write(A.UC_ARM64_REG_X0, 0x40)
        s.mu.reg_write(A.UC_ARM64_REG_X1, 0)
        s.mu.reg_write(A.UC_ARM64_REG_X30, STOPPAGE)
        s.mu.emu_start(s.elf.sym["mk_hold"], 0, count=2_000_000_000)

    def writes(self, s):
        return [(o, v) for k, o, v, _ in s.pmu_events if k == "W"]

    def test_the_trigger_store_comes_at_the_deadline_after_the_reset_marker_with_the_vendor_values(self):
        s = self.sim()
        arm_clk = s.g("t0")
        self.hold(s)
        self.assertIsNotNone(s.trigger_clk, "no PMU trigger store was made")
        dt = (s.trigger_clk - arm_clk) / FREQ
        self.assertGreaterEqual(dt, DEADLINE_S)
        self.assertLess(dt, DEADLINE_S + 0.05)                      # the busy wait polls the deadline: no dwell is waited out
        self.assertEqual(self.writes(s), [(INFORM2, 0x0A4E0011), (INFORM3, DOWNLOAD), (CMD, 0x8), (REBOOT, 2)])
        f = s.fb_at_trigger
        self.assertIsNotNone(f, "the framebuffer did not decode as a frame at the trigger store")
        self.assertEqual((f["kind"], f["idx"], f["data"]), (3, 0, 0x41))     # decoded from the framebuffer bytes, not from a log

    def test_the_whole_run_before_the_trigger_shows_the_loader_hold_and_the_rst_frames_with_the_entry_words(self):
        s = self.sim(i3=RECOVERY, i2=0x0AA50011, cmd=0xD)
        self.hold(s)
        fr = [f for f, _ in s.frames]
        d = dec44.describe44(fr)
        self.assertEqual(d["reset"]["inform3_at_entry"], "0x%08x" % RECOVERY)
        self.assertEqual(d["reset"]["inform2_at_entry"], "0x0aa50011")
        self.assertEqual(d["reset"]["reboot_cmd_at_entry"], "0x0000000d")
        self.assertEqual(d["reset"]["status"]["rc"], 0)
        self.assertTrue(d["reset"]["status"]["armed"])
        self.assertEqual(dec44.reset_attempts(fr), (0, []))                # the RESET frame is not in the sampled sequence (it is the instant before the trigger)

    def test_the_bootloader_image_writes_its_own_reason_and_mode(self):
        s = self.sim("loader-diag-reset-bl")
        self.hold(s)
        self.assertEqual(self.writes(s), [(INFORM2, 0x0A4E0011), (INFORM3, BOOTLOADER), (CMD, 0xB), (REBOOT, 2)])

    def test_a_readback_failure_triggers_nothing_and_the_run_goes_on_to_the_watchdog_time(self):
        for off, rc in ((INFORM2, 2), (INFORM3, 3), (CMD, 4)):
            s = self.sim()
            s.fault_off = off
            self.hold(s, limit=WDT_S + 5)
            self.assertIsNone(s.trigger_clk, hex(off))
            self.assertNotIn(REBOOT, [o for o, _ in self.writes(s)])
            fr = s.final_frames()
            n, res = dec44.reset_attempts(fr)
            self.assertEqual(n, 1, hex(off))                           # attempted once, never again
            self.assertEqual(res, [rc], hex(off))
            self.assertGreaterEqual(s.t(), WDT_S + 5 - 0.1)

    def test_an_unarmed_loader_never_writes_the_pmu_in_a_full_watchdog_period(self):
        s = self.sim(arm=False)
        s.pmu_events.clear()
        self.hold(s, limit=WDT_S + 5)
        self.assertEqual(s.pmu_events, [])
        self.assertIsNone(s.trigger_clk)

    def test_a_leftover_download_request_is_cleared_at_entry(self):
        s = Sim(self.elf["loader-diag-reset"], {INFORM3: DOWNLOAD})
        s.call("nat044_snapshot", PMU)
        self.assertEqual(s.pmu_word(INFORM3), NORMAL)
        self.assertEqual((s.g("cleared"), s.g("inform3_0")), (1, DOWNLOAD))
        self.assertEqual([(o, v) for k, o, v, _ in s.pmu_events if k == "W"], [(INFORM3, NORMAL)])

    def test_a_leftover_request_that_cannot_be_cleared_is_reported_not_hidden(self):
        s = Sim(self.elf["loader-diag-reset"], {INFORM3: BOOTLOADER})
        s.fault_off = INFORM3                              # the read-back of the clearing store does not match
        s.call("nat044_snapshot", PMU)
        s.fault_off = None                                 # the later reset call is not the subject here
        self.assertEqual((s.g("cleared"), s.g("inform3_0")), (2, BOOTLOADER))
        s.call("nat044_arm")
        self.hold(s)
        r = dec44.describe44([f for f, _ in s.frames])["reset"]          # what the loader drew, decoded from the framebuffer
        self.assertEqual(r["inform3_at_entry"], "0x%08x" % BOOTLOADER)
        self.assertEqual({k: r["status"][k] for k in ("leftover_request_clear_failed", "leftover_request_cleared", "armed", "rc")},
                         dict(leftover_request_clear_failed=True, leftover_request_cleared=False, armed=True, rc=0))

    def test_a_cleared_leftover_request_is_reported_in_the_status_frame(self):
        for word in (DOWNLOAD, BOOTLOADER):
            s = self.sim(i3=word)
            self.hold(s)
            r = dec44.describe44([f for f, _ in s.frames])["reset"]
            self.assertEqual(r["inform3_at_entry"], "0x%08x" % word)
            self.assertEqual({k: r["status"][k] for k in ("leftover_request_clear_failed", "leftover_request_cleared", "armed")},
                             dict(leftover_request_clear_failed=False, leftover_request_cleared=True, armed=True), hex(word))

    def test_arming_before_the_snapshot_does_not_arm(self):
        s = Sim(self.elf["loader-diag-reset"], {})
        s.call("nat044_arm")
        self.assertEqual((s.g("armed"), s.g("pmu")), (0, 0))
        s.pmu_events.clear()
        self.hold(s, limit=WDT_S)
        self.assertEqual(s.pmu_events, [])

    def test_the_snapshot_leaves_every_other_word_alone(self):
        for w in (NORMAL, RECOVERY, 0):
            s = Sim(self.elf["loader-diag-reset"], {INFORM3: w, INFORM2: 0x11223344, CMD: 0x55})
            s.call("nat044_snapshot", PMU)
            self.assertEqual([e for e in s.pmu_events if e[0] == "W"], [], hex(w))
            self.assertEqual((s.g("inform3_0"), s.g("inform2_0"), s.g("cmd_0"), s.g("cleared")), (w, 0x11223344, 0x55, 0))


@needs_sim
class Aarch64Guard(unittest.TestCase):
    """The real recovery_guard: the order of snapshot, watchdog arm and deadline arm in the compiled loader."""
    @classmethod
    def setUpClass(cls):
        cls.elf = ElfImage(built() / "loader-diag-reset/loader.elf")

    def run_guard(self, i3=NORMAL, wdt_fault=False):
        s = Sim(self.elf, {INFORM3: i3})
        s.wdt_fault = wdt_fault
        s.mu.mem_write(self.elf.sym["diagnostic_value"], struct.pack("<I", 0xD65F03C0))    # `ret`: no UI in this model
        order = []

        def hit(name):
            def cb(uc):
                order.append(name)
                if name == "diagnostic_value":
                    p = uc.reg_read(A.UC_ARM64_REG_X0)
                    label = bytes(uc.mem_read(p, 40)).split(b"\0")[0].decode()
                    s.diag.append((label, uc.reg_read(A.UC_ARM64_REG_X1)))
                    order.append("diag:" + label)
            return cb
        for n in ("nat044_snapshot", "nat044_arm", "s5e_wdt_arm", "diagnostic_value"):
            s.hook_symbol(n, hit(n))
        rc = s.call("recovery_guard")
        return s, order, rc

    def test_snapshot_first_deadline_armed_only_after_the_watchdog(self):
        s, order, rc = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertEqual([o for o in order if not o.startswith("diag:")][:4], ["nat044_snapshot", "diagnostic_value", "diagnostic_value", "s5e_wdt_arm"])
        self.assertLess(order.index("s5e_wdt_arm"), order.index("nat044_arm"))
        self.assertEqual(s.g("armed"), 1)
        self.assertEqual(s.g("pmu"), PMU)
        self.assertEqual(s.g("deadline_ticks"), FREQ * DEADLINE_S)
        first_wdt_write = next(c for k, _, _, c in s.wdt_events if k == "W")
        self.assertGreaterEqual(s.g("t0"), first_wdt_write)         # the deadline starts after the watchdog's first store

    def test_a_watchdog_that_did_not_arm_means_no_deadline(self):
        s, order, rc = self.run_guard(wdt_fault=True)
        self.assertEqual(rc & 0xFFFFFFFF, 0xFFFFFFFF)                # recovery_guard() returned -1: the loader stops before XNU
        self.assertNotIn("nat044_arm", order)
        self.assertEqual(s.g("armed"), 0)

    def test_a_recovery_leftover_is_still_cleared_by_the_existing_guard_logic(self):
        s, order, rc = self.run_guard(i3=RECOVERY)
        self.assertEqual(s.pmu_word(INFORM3), NORMAL)
        self.assertEqual(s.g("inform3_0"), RECOVERY)                # the snapshot kept the word S-Boot left
        self.assertEqual(s.g("cleared"), 0)                         # and did not clear it itself (the guard did, as before)

    def test_a_download_leftover_is_cleared_by_the_snapshot_and_the_guard_sees_a_normal_word(self):
        s, order, rc = self.run_guard(i3=DOWNLOAD)
        self.assertEqual(s.pmu_word(INFORM3), NORMAL)
        self.assertEqual((s.g("cleared"), s.g("inform3_0")), (1, DOWNLOAD))
        self.assertEqual(dict(s.diag)["panic_inform_before"], NORMAL)


if __name__ == "__main__":
    unittest.main(verbosity=1)
