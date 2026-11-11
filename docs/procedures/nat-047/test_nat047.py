#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-047 host tests: the images loader-diag-usbmon / loader-diag-usbmon-fault (the NAT-044 reset canary loader + the NAT-045
ladder + the NAT-041 usbmon engine, text and exceptions over USB). Evidence kind: host-test. Nothing here runs on, or is sent to,
the phone.

    python3 -I docs/procedures/nat-047/test_nat047.py
    capvenv/bin/python -I docs/procedures/nat-047/test_nat047.py     # an interpreter with unicorn + capstone adds the Aarch64 layers

Layers, each skips itself, and says why, when what it needs is missing:
  Patch      patch_loader5.py against the real run-006 loader source after the NAT-022 and NAT-044 patches: every anchor exactly
             once, only additions, all-or-nothing, not applicable twice, hooks where the design puts them.
  Constants  the decoder's status bits / frame kind / idx are the compiled source's.
  Build      both images build, twice identically; header, size; the engine, the ladder and the reset module are compiled from
             their own directories with the pinned hashes; no undefined symbol; the BRK exists only where it belongs; the x86
             test glue's struct sizes are the aarch64 compiler's.
  Aarch64    the built loader.elf executed instruction by instruction in unicorn, its usbmon engine driving the NAT-041 DWC3
             model through MMIO windows, the NAT-045 device model behind the ladder's registers, and the NAT-041 collector
             (s24_logd.py, unmodified) as the host: what the archive holds, when the reset comes, what a stopped ladder, a
             missing cable, a late cable, a controlled BRK and a fault inside the engine do.
The simulation has no caches, no MMU, no memory attributes, no interrupts, no second CPU, no real controller and no real USB
stack. It shows what the compiled code does against NAT-041's reading of the databook; it is not a measurement of the S24."""
import base64
import hashlib
import importlib.util
import json
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
PROC = HERE.parent
N22, N41, N42, N44, N45 = (PROC / n for n in ("nat-022", "nat-041", "nat-042", "nat-044", "nat-045"))
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
sys.path.insert(0, str(HERE / "test_support"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


p4 = _load("nat044_patch", N44 / "patch_loader4.py")
p5 = _load("nat047_patch", HERE / "patch_loader5.py")
d47 = _load("nat047_decode", HERE / "decode47.py")
try:
    import unicorn  # noqa: F401
    import sim47 as S
    import rig47 as R
    import plathost as H
    import usbmon_proto as P
    HAVE_SIM = True
except ImportError:
    HAVE_SIM = False
try:
    import capstone
except ImportError:
    capstone = None

have_cc = shutil.which("cc") is not None
have_zig = shutil.which("zig") is not None
have_loader = LOADER_SRC.exists() and PAYLOAD.exists()
needs_loader = unittest.skipUnless(have_loader, "the local NAT-020 build-003 loader source/payload are missing")
needs_build = unittest.skipUnless(have_loader and have_zig, "zig or the local NAT-020 build-003 artifacts are missing")
needs_sim = unittest.skipUnless(have_loader and have_zig and have_cc and HAVE_SIM, "unicorn, cc, zig or the local NAT-020 artifacts are missing")

PLAIN, FAULT = "loader-diag-usbmon", "loader-diag-usbmon-fault"
DEADLINE_S, WDT_S = 45, 83
NORMAL, DOWNLOAD = 0x12345600, 0x12345601
INFORM2, INFORM3, CMD, REBOOT = 0xB8, 0xBC, 0x190, 0x3C00
BRK_1234 = 0xD4224680
LAD_LAST = 5
# every PMU store of a whole run: the guard's watchdog arm (s5e9945.c: cluster 0 reset-enable, word 0x1244), then NAT-042's vendor reset order
PMU_WRITES = [(0x1244, 4), (INFORM2, 0x0A4E0011), (INFORM3, DOWNLOAD), (CMD, 0x8), (REBOOT, 2)]


def sh(argv, **kw):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True, **kw)


# ---------------------------------------------------------------------------------------------------------------- build cache
_build_dirs = {}
_build_tmp = None


def built(deadline_s=45):
    """Build both images once per run and deadline (the real build.py, from a copy of the run-006 loader source)."""
    global _build_tmp
    if deadline_s not in _build_dirs:
        if _build_tmp is None:
            _build_tmp = tempfile.TemporaryDirectory()
        out = Path(_build_tmp.name) / ("out" if deadline_s == 45 else "out%d" % deadline_s)
        r = sh([sys.executable, "-I", HERE / "build.py", "--out", out, "--loader-source", LOADER_SRC, "--deadline-s", deadline_s])
        assert r.returncode == 0, r.stderr + r.stdout
        _build_dirs[deadline_s] = out
    return _build_dirs[deadline_s]


def tearDownModule():
    if _build_tmp is not None:
        _build_tmp.cleanup()
    for t in _scenario_tmp:
        t.cleanup()


def patched_tree(dst):
    """The run-006 loader source after NAT-022 patch_loader.py (--trig-hold --adt-aligned), NAT-022's marker files and NAT-044's patch."""
    src = Path(dst) / "source"
    shutil.copytree(LOADER_SRC, src, ignore=shutil.ignore_patterns("out", ".git"))
    assert sh([sys.executable, "-I", N22 / "patch_loader.py", src, "--trig-hold", "--adt-aligned"]).returncode == 0
    e = src / "shim/e1s-xnu"
    for f in ("marker.h", "markerlib.c"):
        shutil.copy(N22 / "src" / f, e)
    assert sh([sys.executable, "-I", N44 / "patch_loader4.py", src]).returncode == 0
    return src


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

    def apply(self, src):
        return sh([sys.executable, "-I", HERE / "patch_loader5.py", src])

    def test_every_anchor_occurs_exactly_once_in_the_real_sources(self):
        for name, hunks in p5.HUNKS.items():
            text = (self.e0 / name).read_text()
            for key, old, _ in hunks:
                self.assertEqual(text.count(old), 1, "%s: %s" % (name, key))

    def test_the_patch_only_adds_lines_and_touches_only_its_three_files(self):
        import difflib
        src = self.fresh("applied")
        r = self.apply(src)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = src / "shim/e1s-xnu"
        touched = sorted(p.name for p in e.iterdir() if p.is_file() and (self.e0 / p.name).read_bytes() != p.read_bytes())
        self.assertEqual(touched, sorted(p5.HUNKS))
        for name, hunks in p5.HUNKS.items():
            a = (self.e0 / name).read_text().splitlines(keepends=True)
            b = (e / name).read_text().splitlines(keepends=True)
            removed = [l[2:] for l in difflib.ndiff(a, b) if l.startswith("- ")]
            added = [l[2:] for l in difflib.ndiff(a, b) if l.startswith("+ ")]
            # a hunk's new text is its old text with lines inserted before/after/inside; no existing line may disappear. The one
            # exception is a line the hunk extends in place (a replaced `while` or `mk_stage` line), which then reappears whole.
            want_removed = {l for _, old, _ in hunks for l in old.splitlines(keepends=True)}
            self.assertTrue(set(removed) <= want_removed, "%s removed %r" % (name, set(removed) - want_removed))
            self.assertEqual(len(added) - len(removed), sum(len(n.splitlines()) - len(o.splitlines()) for _, o, n in hunks), name)
            for _, _, new in hunks:
                for line in new.splitlines(keepends=True):
                    self.assertIn(line, (e / name).read_text())

    def test_a_missing_or_duplicated_anchor_fails_before_anything_is_written(self):
        for case in ("missing", "duplicated"):
            src = self.fresh(case)
            loader = src / "shim/e1s-xnu/loader.c"                  # the last file of the patch: the others are ready when it fails
            t = loader.read_text()
            anchor = next(old for k, old, _ in p5.HUNKS["loader.c"] if k == "bringup")
            loader.write_text(t.replace(anchor, "") if case == "missing" else t + anchor)
            before = {n: (src / "shim/e1s-xnu" / n).read_bytes() for n in p5.HUNKS}
            r = self.apply(src)
            self.assertNotEqual(r.returncode, 0, case)
            self.assertIn("anchor", r.stderr + r.stdout)
            for n, b in before.items():
                self.assertEqual((src / "shim/e1s-xnu" / n).read_bytes(), b, "%s: %s was written" % (case, n))

    def test_the_patch_cannot_be_applied_twice(self):
        src = self.fresh("twice")
        self.assertEqual(self.apply(src).returncode, 0)
        after = {n: (src / "shim/e1s-xnu" / n).read_bytes() for n in p5.HUNKS}
        self.assertNotEqual(self.apply(src).returncode, 0)
        for n, b in after.items():
            self.assertEqual((src / "shim/e1s-xnu" / n).read_bytes(), b, n)

    def test_the_hooks_sit_where_the_design_needs_them(self):
        src = self.fresh("order")
        self.assertEqual(self.apply(src).returncode, 0)
        e = src / "shim/e1s-xnu"
        m, ld, mh = (e / "markerlib.c").read_text(), (e / "loader.c").read_text(), (e / "marker.h").read_text()
        # every band of a drawn frame and every wait loop gives the engine a poll; the poll is the first thing in the band loop
        self.assertEqual(m.count("nat047_poll();"), 3)
        self.assertIn("for (uint32_t b = 0; b < MK_BANDS; b++) {\n\t\tnat047_poll();\n", m)
        self.assertEqual(m.count("nat047_stage(stage);"), 1)
        self.assertIn("void mk_stage(uint32_t stage)\n{\n\tnat047_stage(stage);\n", m)
        # the hold: the HOLD note (and the fault image's BRK) comes after the first dwell and before the report loop; the report
        # frame sits in the loop right after the NAT-044 one
        self.assertEqual(m.count("nat047_hold(stage, code);"), 1)
        self.assertLess(m.index("nat047_hold(stage, code);"), m.index("show(&prev, mk_frame(MK_STAGE, 1, ld_mask), &ld_k);"))
        self.assertEqual(m.count("nat047_show(&prev, &ld_k);"), 1)
        self.assertEqual(m.index("nat044_show(&prev, &ld_k);\n\t\tnat047_show(&prev, &ld_k);") > 0, True)
        # the exception: the record is made before anything is drawn, and the loop reports
        self.assertEqual(m.count("nat047_fault(slot, esr, elr, far);"), 1)
        self.assertLess(m.index("nat047_fault(slot, esr, elr, far);"), m.index("mk_draw(mk_frame(MK_STAGE, 0, MK_ST_EXC), 0, 1);"))
        self.assertEqual(m.count("nat047_show(&prev, &k);"), 1)
        # the loader: every character, and the bring-up right after the LOADER_MAIN stage and before any other stage
        self.assertEqual(ld.count("nat047_log_char(c);"), 1)
        self.assertEqual(ld.count("nat047_bringup("), 1)
        self.assertEqual(ld.count("nat047_bringup((const char *)loader_log.text, loader_log.length);"), 1)    # the RAM log so far, all of it
        i = ld.index("nat047_bringup(")
        self.assertEqual(ld.rindex("NAT022_STAGE(", 0, i), ld.index("NAT022_STAGE(MK_ST_LOADER_MAIN);"))
        self.assertLess(i, ld.index("NAT022_STAGE(MK_ST_LOADER_FB)") if "NAT022_STAGE(MK_ST_LOADER_FB)" in ld else len(ld))
        self.assertIn("MK_USB = 13", mh)


# ---------------------------------------------------------------------------------------------------------------------- Package
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"


@needs_build
@unittest.skipUnless(STOCK.exists(), "the pinned stock RECOVERY (local, not committed) is missing")
class Package(unittest.TestCase):
    """package.py: the RECOVERY candidate carries Image.payload (loader + XNU payload), not the loader-only Image (decision 0020)."""
    def test_the_recovery_candidate_carries_the_payload_image_verbatim_and_not_the_loader_alone(self):
        out = built()
        with tempfile.TemporaryDirectory() as tmp:
            r = sh([sys.executable, "-I", HERE / "package.py", "--build", out, "--out", Path(tmp) / "pkg", "--only", PLAIN])
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            rec = json.loads((Path(tmp) / "pkg/package.json").read_text())
            self.assertEqual(list(rec["images"]), [PLAIN])
            self.assertEqual((rec["kind"], rec["device_used"], rec["flashed"]), ("host-test", False, False))
            s = rec["images"][PLAIN]
            img = (Path(tmp) / "pkg" / PLAIN / "recovery.img").read_bytes()
            payload = (out / PLAIN / "Image.payload").read_bytes()
            loader = (out / PLAIN / "Image").read_bytes()
            self.assertGreater(len(payload), 10 * len(loader))                        # the XNU payload and ADT are the bulk of it
            self.assertEqual((payload[:16], payload[20:len(loader)]), (loader[:16], loader[20:]))     # only the image-size field differs
            self.assertEqual(struct.unpack_from("<Q", payload, 16)[0], len(payload))
            off = s["payload_offset"]
            self.assertEqual(img[off:off + len(payload)], payload)                    # verbatim, from the loader to the end of the ADT
            tail = img[off + len(loader):off + len(loader) + 65536]
            self.assertEqual(tail, payload[len(loader):len(loader) + 65536])
            self.assertNotEqual(tail, b"\0" * len(tail))
            self.assertEqual((s["recovery_sha256"], s["payload_sha256"], s["loader_image_sha256"], s["recovery_bytes"], s["payload_bytes"]),
                             (hashlib.sha256(img).hexdigest(), hashlib.sha256(payload).hexdigest(), hashlib.sha256(loader).hexdigest(),
                              len(img), len(payload)))
            self.assertEqual(len(img), 100663296)
            self.assertEqual(rec["stock_sha256"], "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")

    def test_a_build_record_that_does_not_match_its_payload_is_refused_and_nothing_is_packaged(self):
        out = built()
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(tmp) / "b"
            b.mkdir()
            os.symlink(out / PLAIN, b / PLAIN)
            rec = json.loads((out / "build.json").read_text())
            sha0 = rec["image_payloads"][PLAIN]["sha256"]
            rec["image_payloads"][PLAIN]["sha256"] = ("0" if sha0[0] != "0" else "1") + sha0[1:]
            (b / "build.json").write_text(json.dumps(rec))
            r = sh([sys.executable, "-I", HERE / "package.py", "--build", b, "--out", Path(tmp) / "pkg", "--only", PLAIN])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("does not match the build record", r.stderr + r.stdout)
            self.assertFalse((Path(tmp) / "pkg" / PLAIN / "recovery.img").exists())
            r = sh([sys.executable, "-I", HERE / "package.py", "--build", out, "--out", Path(tmp) / "pkg2", "--only", "no-such-image"])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("is not an image of the build record", r.stderr + r.stdout)


# ---------------------------------------------------------------------------------------------------------------- Constants
class Constants(unittest.TestCase):
    def test_the_decoder_s_status_bits_idx_and_phases_are_the_compiled_source_s(self):
        text = (HERE / "src/markerlib47.c").read_text()
        names = {"UP": "up", "CONNECTED": "connected", "CONFIGURED": "configured", "NONCE": "nonce", "FAULTED": "faulted",
                 "POLLFAULT": "poll_faulted", "PDWASON": "pd_was_on"}
        bits = {int(v, 16): names[n] for n, v in re.findall(r"#define N47_S_(\w+)\s+(0x[0-9a-f]+)u", text)}
        self.assertEqual(len(bits), len(names))
        self.assertEqual(bits, d47.BITS)
        enum = text.split("enum { N47_IDLE = 0")[1].split("};")[0]
        phases = {0: "IDLE"} | {int(v): n for n, v in re.findall(r"N47_(\w+) = (\d+)", enum)}
        self.assertEqual(phases, {0: "IDLE", 1: "LAD_RO", 2: "LAD_W", 3: "START", 4: "CONNECT", 5: "UP", 6: "STOP"})
        self.assertEqual(sorted(d47.PHASES), sorted(phases))
        self.assertEqual(re.findall(r"N47_I_(\w+) = (\d+)", text), [("STATUS", "0"), ("ERR", "1"), ("ERROP", "2"), ("NREC", "3"), ("WRITTEN", "5")])
        self.assertEqual((d47.I_STATUS, d47.I_ERR, d47.I_ERROP, d47.I_NREC, d47.I_WRITTEN), (0, 1, 2, 3, 5))
        self.assertIn("MK_USB = 13", p5.HUNKS["marker.h"][0][2])
        self.assertEqual(d47.KIND_USB, 13)
        self.assertIn("MK_USB", (HERE / "patch_loader5.py").read_text())

    def test_the_decoder_names_every_phase_after_the_loader_s_enumerator(self):
        text = (HERE / "src/markerlib47.c").read_text()
        enum = text.split("enum { N47_IDLE = 0")[1].split("};")[0]
        by_ident = {"IDLE": 0} | {n: int(v) for n, v in re.findall(r"N47_(\w+) = (\d+)", enum)}
        words = {"IDLE": "idle", "LAD_RO": "ladder-ro", "LAD_W": "ladder-write", "START": "engine-start", "CONNECT": "connect-wait",
                 "UP": "up", "STOP": "stopped"}                                       # what README.md and the decoder's docstring call them
        self.assertEqual(sorted(by_ident), sorted(words))
        for ident, num in by_ident.items():
            self.assertEqual(d47.status(num << 8)["phase"], words[ident], ident)
        self.assertEqual(d47.status(7 << 8)["phase"], "phase7")                       # a value the loader never writes is shown, not hidden

    def test_the_decoder_reads_a_status_word_and_a_stop_code(self):
        s = d47.status(0x5000 | 0x500 | 0x1 | 0x2 | 0x4 | 0x8 | 0x40)
        self.assertEqual((s["phase"], s["rung_done"]), ("up", 5))
        self.assertTrue(all(s[k] for k in ("up", "connected", "configured", "nonce", "pd_was_on")))
        self.assertFalse(s["faulted"] or s["poll_faulted"])
        self.assertEqual(d47.stop_code(0), (0, "none"))
        self.assertEqual(d47.stop_code(50), (3, "timeout"))
        self.assertEqual(d47.stop_code(114), (7, "timeout"))
        self.assertEqual(d47.describe47([]), {})

    def test_the_last_frame_of_each_idx_wins(self):
        fr = [dict(kind=13, idx=0, data=1), dict(kind=3, idx=0, data=0x40), dict(kind=13, idx=0, data=0x503), dict(kind=13, idx=3, data=79),
              dict(kind=13, idx=2, data=0xFFFF)]
        d = d47.describe47(fr)["usb"]
        self.assertEqual(d["status"]["phase"], "up")
        self.assertTrue(d["status"]["connected"])
        self.assertEqual((d["ladder_records"], d["stop_op"]), (79, None))


# ------------------------------------------------------------------------------------------------------------------------ Build
def nm_sizes(path):
    out = sh(["nm", "-S", path]).stdout
    res = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) == 4:
            res[p[3]] = (int(p[0], 16), int(p[1], 16))
        elif len(p) == 3:
            res[p[2]] = (int(p[0], 16), 0)
    return res


def text_words(elf_path):
    """(address, 32-bit words) of every executable PT_LOAD segment of a little-endian ELF64."""
    b = Path(elf_path).read_bytes()
    phoff, phentsize, phnum = struct.unpack_from("<Q", b, 32)[0], struct.unpack_from("<H", b, 54)[0], struct.unpack_from("<H", b, 56)[0]
    out = []
    for i in range(phnum):
        t, flags, off, vaddr, _, filesz, _, _ = struct.unpack_from("<IIQQQQQQ", b, phoff + i * phentsize)
        if t == 1 and flags & 1:
            out.append((vaddr, struct.unpack_from("<%dI" % (filesz // 4), b, off)))
    return out


@needs_build
class Build(unittest.TestCase):
    def test_both_images_exist_with_a_valid_header_and_fit_one_mebibyte(self):
        out = built()
        for name in (PLAIN, FAULT):
            img = (out / name / "Image").read_bytes()
            self.assertEqual(img[56:60], b"ARM\x64")
            self.assertEqual(struct.unpack_from("<Q", img, 8)[0], 0x80000)
            self.assertEqual(len(img), struct.unpack_from("<Q", img, 16)[0])
            self.assertLess(len(img), 1 << 20)
            self.assertGreater((out / name / "Image.payload").stat().st_size, len(img))

    def test_the_build_is_reproducible(self):
        out2 = Path(tempfile.mkdtemp())
        try:
            r = sh([sys.executable, "-I", HERE / "build.py", "--out", out2 / "o", "--loader-source", LOADER_SRC])
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in (PLAIN, FAULT):
                for f in ("Image", "Image.payload", "loader.elf"):
                    self.assertEqual((out2 / "o" / name / f).read_bytes(), (built() / name / f).read_bytes(), "%s/%s" % (name, f))
        finally:
            shutil.rmtree(out2, ignore_errors=True)

    def test_the_deadline_is_well_inside_the_watchdog_and_the_build_refuses_a_late_one(self):
        self.assertLessEqual(DEADLINE_S, WDT_S - 20)
        out = Path(tempfile.mkdtemp())
        try:
            for secs in (WDT_S - 19, WDT_S, 0, 200):
                r = sh([sys.executable, "-I", HERE / "build.py", "--out", out / ("o%d" % secs), "--loader-source", LOADER_SRC,
                        "--deadline-s", secs])
                self.assertNotEqual(r.returncode, 0, secs)
                self.assertIn("deadline", r.stderr + r.stdout)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_the_build_refuses_an_existing_output_directory(self):
        out = Path(tempfile.mkdtemp())
        try:
            r = sh([sys.executable, "-I", HERE / "build.py", "--out", out, "--loader-source", LOADER_SRC])
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("existing", r.stderr + r.stdout)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_the_build_record_states_what_each_image_was_built_with(self):
        bj = json.loads((built() / "build.json").read_text())
        self.assertEqual(bj["image_meta"][PLAIN], dict(reason="0x12345601", deadline_s=DEADLINE_S, wdt_s=WDT_S, fault=0))
        self.assertEqual(bj["image_meta"][FAULT], dict(reason="0x12345601", deadline_s=DEADLINE_S, wdt_s=WDT_S, fault=1))
        self.assertEqual((bj["kind"], bj["device_used"], bj["flashed"]), ("host-test", False, False))
        for name in (PLAIN, FAULT):
            for k, f in (("images", "Image"), ("image_payloads", "Image.payload")):
                self.assertEqual(bj[k][name]["sha256"], hashlib.sha256((built() / name / f).read_bytes()).hexdigest())

    def test_the_engine_the_ladder_and_the_reset_module_are_the_pinned_files_compiled_from_their_own_directories(self):
        bj = json.loads((built() / "build.json").read_text())
        pins = {}
        for n in ("nat-041", "nat-042", "nat-045"):
            pins.update(json.loads((PROC / n / "evidence.json").read_text())["sha256"])
        for group, base, files in (("nat041_engine", "docs/procedures/nat-041/engine/", None), ("nat045_ladder", "docs/procedures/nat-045/src/", None),
                                   ("nat042_module", "docs/procedures/nat-042/module/", None)):
            self.assertTrue(bj[group], group)
            for f, h in bj[group].items():
                self.assertEqual(pins[base + f], h, base + f)                       # the pinned hash of the reviewed file
                self.assertEqual(hashlib.sha256((ROOT / base / f).read_bytes()).hexdigest(), h, base + f)
        for c in bj["commands"]:
            self.assertEqual(c["exit_code"], 0, c["argv"])
            if c["stderr"]:                  # only the run-006 loader's own warning (loader.c:67, not compiled with -Werror) is tolerated
                self.assertTrue(c["argv"][-3].endswith("shim/e1s-xnu/loader.c") and "loader.c:67:" in c["stderr"] and c["stderr"].count("warning:") == 1,
                                "%s: %s" % (c["argv"][-3], c["stderr"][:200]))
        cmds = [" ".join(map(str, c["argv"])) for c in bj["commands"]]
        for src, need in (("nat-041/engine/usbmon.c", ["-Werror"]), ("nat-045/src/ladder.c", ["-Werror", "-DLAD_WRITING_RUNGS"]),
                          ("nat-045/src/ladder_usb.c", ["-Werror", "-DLAD_WRITING_RUNGS"])):
            hits = [c for c in cmds if src in c]
            self.assertEqual(len(hits), 2, src)                                     # once per image
            for c in hits:
                for flag in need:
                    self.assertIn(flag, c, src)
        resets = [c for c in cmds if "shim/e1s-xnu/s5e9945_reset.c" in c and " -c " in c]
        self.assertEqual(len(resets), 2)                                            # the NAT-042 module, once per image, with the same strictness
        for c in resets:
            self.assertIn("-Werror", c)
        marker = [c for c in cmds if "markerlib47.c" in c and " -c " in c]
        self.assertEqual(len(marker), 2)
        for c in marker:
            self.assertIn("-DNAT044_REASON=S5E_REASON_DOWNLOAD", c)
            self.assertIn("-DNAT044_DEADLINE_S=%d" % DEADLINE_S, c)
            self.assertIn("-DLAD_WRITING_RUNGS", c)
            self.assertIn("-Werror", c)
        self.assertEqual(sum("-DNAT047_FAULT=1" in c for c in marker), 1)
        self.assertEqual(sum("-DNAT047_FAULT=0" in c for c in marker), 1)
        for name in (PLAIN, FAULT):                                                  # and no copy of them sits in the patched loader tree
            e = built() / name / "source/shim/e1s-xnu"
            for f in ("usbmon.c", "ladder.c", "ladder_usb.c"):
                self.assertFalse((e / f).exists(), "%s/%s" % (name, f))
            for f in ("s5e9945_reset.h", "s5e9945_reset.c"):
                self.assertEqual((e / f).read_bytes(), (N42 / "module" / f).read_bytes(), f)

    def test_the_sources_the_nat047_code_hangs_on_are_those_of_the_build_record(self):
        bj = json.loads((built() / "build.json").read_text())
        for f, h in bj["nat047_sources"].items():
            p = HERE / "src" / f if f != "patch_loader5.py" else HERE / f
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), h, f)
        for f, h in bj["nat044_sources"].items():
            p = N44 / "src" / f if f != "patch_loader4.py" else N44 / f
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), h, f)

    def test_each_image_is_self_contained_and_has_the_symbols_the_run_needs(self):
        for name in (PLAIN, FAULT):
            elf = built() / name / "loader.elf"
            self.assertEqual(sh(["nm", "-u", elf]).stdout.strip(), "", name)
            syms = nm_sizes(elf)
            for s in ("usbmon_poll", "usbmon_init", "usbmon_log", "usbmon_stage", "usbmon_fault_record", "lad_run", "lad_usb_start",
                      "g_nat047", "nat047_bringup", "nat047_poll", "nat047_hold", "nat047_fault", "nat047_show", "nat047_stage",
                      "nat047_log_char", "recovery_guard", "mk_hold", "mk_stage", "g_nat044", "vectors", "_stack_top"):
                self.assertIn(s, syms, "%s: %s" % (name, s))

    def test_the_controlled_brk_exists_only_in_the_fault_image_and_only_in_the_hold_routine(self):
        """The one other BRK #0x1234 in the loader is NAT-022's canary variant inside mk_canary_loop: dead code here, nothing calls it."""
        for name, want in ((PLAIN, ["mk_canary_loop"]), (FAULT, ["mk_canary_loop", "nat047_hold"])):
            elf = built() / name / "loader.elf"
            syms = nm_sizes(elf)
            owners = []
            for vaddr, words in text_words(elf):
                for i, w in enumerate(words):
                    if w == BRK_1234:
                        a = vaddr + 4 * i
                        owners.append(next(n for n, (lo, size) in syms.items() if size and lo <= a < lo + size))
            self.assertEqual(sorted(owners), sorted(want), name)
            dead = syms["mk_canary_loop"][0]
            for vaddr, words in text_words(elf):
                for i, w in enumerate(words):
                    if w >> 26 in (0b100101, 0b000101):                      # BL / B imm26
                        imm = w & 0x3FFFFFF
                        imm -= (1 << 26) if imm >> 25 else 0
                        self.assertNotEqual(vaddr + 4 * i + 4 * imm, dead, "%s: a branch targets mk_canary_loop at %#x" % (name, vaddr + 4 * i))

    def test_the_x86_test_glue_sees_the_struct_sizes_the_aarch64_compiler_uses(self):
        if not HAVE_SIM:
            self.skipTest("unicorn is missing (the glue is part of the simulator)")
        tmp = Path(tempfile.mkdtemp())
        try:
            lib = S.load_lib(S.build_glue(str(tmp)))
            probe = tmp / "probe.c"
            probe.write_text('#include <stddef.h>\n#include "usbmon.h"\n#include "ladder.h"\n'
                             '_Static_assert(sizeof(struct usbmon) == %d, "usbmon");\n'
                             '_Static_assert(offsetof(struct usbmon, dma) == 0, "the DMA block is first");\n'
                             '_Static_assert(sizeof(((struct usbmon *)0)->dma) == %d, "dma");\n'
                             '_Static_assert(sizeof(struct lad_state) == %d, "lad_state");\n'
                             % (lib.h_sizeof_usbmon(), lib.h_sizeof_dma(), LAD_STATE_BYTES))
            b22 = _load("nat022_build_t", N22 / "build.py")
            r = sh(["zig", "cc", *b22.FLAGS, "-I" + str(N41 / "engine"), "-I" + str(N45 / "src"), "-c", probe, "-o", tmp / "probe.o"])
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_g_nat047_is_as_large_as_the_simulator_s_layout_says(self):
        if not HAVE_SIM:
            self.skipTest("unicorn is missing")
        tmp = Path(tempfile.mkdtemp())
        try:
            lib = S.load_lib(S.build_glue(str(tmp)))
            l0 = field_base(lib)
            for name in (PLAIN, FAULT):
                self.assertEqual(nm_sizes(built() / name / "loader.elf")["g_nat047"][1], (l0 + 52 + 63) & ~63, name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


LAD_STATE_BYTES = 1348


def field_base(lib):
    """Offset of struct nat047's line_len in g_nat047: the engine, two ladder states, the 32 KiB ring, the 200-byte line, 4-aligned."""
    return (lib.h_sizeof_usbmon() + 2 * LAD_STATE_BYTES + 32768 + 200 + 3) & ~3


# ------------------------------------------------------------------------------------------------------------------- scenarios
_glue = {}
_scenario_tmp = []
_cache = {}
TC = unittest.TestCase()
LOGBUF = None
LOG = "".join("loader: line %03d ..................................................\n" % i for i in range(26)).encode()    # > 2 chunks of 512
STAGES_AFTER = (0x21, 0x30, 0x31, 0x32, 0x33, 0x34, 0x40)
STAGE_NAMES = [(0x20, "loader_main"), (0x21, "fb"), (0x30, "mem"), (0x31, "zero"), (0x32, "copy"), (0x33, "adt"), (0x34, "clean"), (0x40, "pre_jump")]
INIT = lambda: {S.INFORM3: NORMAL, S.INFORM2: 0x0AA50011, S.CMD: 0xD}      # noqa: E731


def tmp_dir():
    t = tempfile.TemporaryDirectory()
    _scenario_tmp.append(t)
    return t.name


def glue_lib():
    if "lib" not in _glue:
        _glue["lib"] = S.load_lib(S.build_glue(tmp_dir()))
        _glue["table"] = H.ops()
    return _glue["lib"], _glue["table"]


class Res:
    pass


class Run:
    """One simulated phone: the loader's own thread is a queue of the calls loader_main makes, in its order."""
    def __init__(self, image, *, guard=True, pd_on=False, dev_kw=None, log=LOG, stages=STAGES_AFTER, hold_stage=0x40, pre=(), post=(),
                 tail=None, deadline_s=45):
        """pre / post: extra calls of the loader's thread right before / after nat047_bringup; tail: replaces the stage calls and the hold."""
        self.image = image
        self.lib, table = glue_lib()
        self.sim = S.Sim47(S.load_elf(built(deadline_s) / image / "loader.elf"), self.lib, table, pd_on=pd_on, init=INIT(), dev_kw=dev_kw)
        self.l0 = field_base(self.lib)
        self.log = log
        self.timeline = []
        self.rig = None
        self.stop = None
        self.sim.watch("nat047_hold")
        logbuf = S.LOAD + 0x60000
        self.sim.write(logbuf, log)
        if guard:
            self.sim.queue_call("recovery_guard")
        self.sim.queue_call("mk_stage", 0x20)
        for c in pre:
            self.sim.queue_call(*c)
        self.sim.queue_call("nat047_bringup", logbuf, len(log))
        for c in post:
            self.sim.queue_call(*c)
        if tail is not None:
            for c in tail:
                self.sim.queue_call(*c)
            return
        for st in stages:
            self.sim.queue_call("mk_stage", st)
        self.sim.queue_call("mk_hold", hold_stage, 0)

    OFF = dict(line_len=0, phase=4, up=8, polling=12, log_on=16, faulted=20, poll_faulted=24, in_fault=28, err=32, err_op=36, nrec=40,
               connect_err=44, holds=48)

    def f(self, name):
        signed = name in ("err", "connect_err")
        return self.sim.g("g_nat047", self.l0 + self.OFF[name], "<i" if signed else "<I")

    def until_done(self, n_calls, limit_s=60.0):
        """Run until the loader's thread has completed n_calls queued calls (the hold loop never completes)."""
        while len(self.sim.done_calls) < n_calls and not self.sim.stopped and self.sim.seconds() < limit_s:
            self.sim.advance(target_t=self.sim.t + 5 * S.STEP_V)
        return len(self.sim.done_calls) >= n_calls

    def until_up(self, limit_s=10.0):
        while not self.f("up") and not self.sim.stopped and self.sim.seconds() < limit_s:
            self.sim.advance(target_t=self.sim.t + 5 * S.STEP_V)
        return bool(self.f("up"))

    def record_until(self, t_s, dt=0.1):
        while self.sim.seconds() < t_s and not self.sim.stopped:
            self.sim.advance(target_t=min(self.sim.t0 + int(t_s * S.FREQ), self.sim.t + int(dt * S.FREQ)))
            self.timeline.append(dict(t=self.sim.seconds(), phase=self.f("phase"), up=self.f("up"), holds=self.f("holds"),
                                      connect_err=self.f("connect_err"), faulted=self.f("faulted"), poll_faulted=self.f("poll_faulted"),
                                      polls=self.sim.polls, nmmio=self.sim.nmmio, nexc=len(self.sim.excs)))

    def host(self):
        self.rig = R.Rig47(TC, self.sim, tmp_dir())
        return self.rig

    def collect(self, limit_s=70.0):
        self.stop = self.rig.go(limit_s)
        return self.stop

    def finish(self):
        s, r = self.sim, Res()
        r.image, r.log, r.timeline = self.image, self.log, self.timeline
        r.stop = self.stop
        r.g = {k: self.f(k) for k in self.OFF}
        r.g044 = {k: s.g("g_nat044", o) for k, o in dict(pmu=0, t0=8, deadline_ticks=16, armed=24, fired=28, rc=32, cleared=36).items()}
        r.pmu_w = [(o, v) for k, o, v, _ in s.pmu_events if k == "W"]
        r.wdt = list(s.wdt_events)
        r.seconds, r.reset_s = s.seconds(), (s.seconds(s.reset_t) if s.reset_t is not None else None)
        r.fb_at_reset = s.fb_at_reset
        r.frames = s.final_frames()
        r.excs, r.exc_t, r.polls, r.nmmio = list(s.excs), [s.seconds(t) for t in s.exc_t], s.polls, s.nmmio
        r.hold_t = [s.seconds(t) for t in s.watched["nat047_hold"]]
        r.dev_viol, r.mmio_viol, r.model_viol = list(s.dev.viol), list(s.mmio_viol), self.lib.model_nviol()
        r.done = list(s.done_calls)
        r.wtrace = s.machine.write_trace()
        r.done_polls = list(s.done_polls)
        r.sym = {n: s.sym(n) for n in ("nat047_hold", "usbmon_poll", "vectors")}
        nm, base = self.lib.h_sizeof_usbmon(), s.sym("g_nat047")                    # the engine, the ring and the line buffer as the loader left them
        r.mem_engine = s.read(base, nm)
        r.mem_ring = s.read(base + nm + 2 * LAD_STATE_BYTES, 32768)
        r.mem_line = s.read(base + nm + 2 * LAD_STATE_BYTES + 32768, 200)
        r.stopped = s.stopped
        if self.rig:
            r.errors = self.rig.errors()
            r.manifest = self.rig.manifest
            r.boots = [dict(name=d.name, frames=self.rig.frames(d), payload=self.rig.payload(d)) for d in self.rig.boot_dirs()]
            r.events = self.rig.events()
        else:
            r.errors, r.manifest, r.boots, r.events = [], None, [], []
        return r

    def close(self):
        self.sim.close()


def scenario(key, build):
    """Run a scenario once per test run; the simulator (one per process: it owns a fixed mapping) is closed right after."""
    if key not in _cache:
        run = None
        try:
            run = build()
            _cache[key] = run.finish()
        except S.RegionUnavailable as e:
            raise unittest.SkipTest(str(e))
        finally:
            if run is not None:
                run.close()
    return _cache[key]


def sc_plain(image):
    def b():
        run = Run(image)
        assert run.until_up(), "the engine did not come up"
        run.t_up = run.sim.seconds()
        run.host().plug()
        run.collect()
        return run
    return scenario(("plain", image), b)


def sc_nocable(image=PLAIN):
    def b():
        run = Run(image)
        assert run.until_up()
        run.record_until(60.0)
        return run
    return scenario(("nocable", image), b)


def sc_fault_nocable():
    def b():
        run = Run(FAULT)
        assert run.until_up()
        run.record_until(60.0)
        return run
    return scenario(("fault-nocable",), b)


def sc_late(plug_s=20.0):
    def b():
        run = Run(PLAIN)
        assert run.until_up()
        run.record_until(plug_s)
        run.host().plug()
        run.collect()
        return run
    return scenario(("late", plug_s), b)


def sc_stopped():
    def b():
        run = Run(PLAIN, dev_kw=dict(follow=False))
        run.record_until(60.0)
        return run
    return scenario(("stopped",), b)


def sc_pollfault():
    def b():
        run = Run(PLAIN)
        assert run.until_up()
        brk = S.LOAD + 0x70000
        run.sim.write(brk, struct.pack("<I", BRK_1234))
        run.sim.poll_inject = (run.sim.polls + 40, brk)
        run.record_until(60.0)
        return run
    return scenario(("pollfault",), b)


def sc_start_fail():
    """The ladder passes, then the engine's own identity check fails (the device model answers a foreign GSNPSID from the moment the loader
    is in the engine-start phase): the engine must not be reported up and the loader must go on to the reset."""
    def b():
        run = Run(PLAIN)
        orig = run.sim.dev.rd

        def rd(a):
            v = orig(a)
            if a == S.devmodel.GSNPSID_ADDR and run.f("phase") == 3:
                return 0x12345678
            return v
        run.sim.dev.rd = rd
        run.record_until(60.0)
        return run
    return scenario(("start-fail",), b)


BIG_LINES = 312
BIGLOG = "".join("loader: line %04d ..............................................\n" % i for i in range(BIG_LINES)).encode()      # 64 bytes a line


def sc_biglog():
    """A loader log of about 20 KB, written to the ring before any host is there: more than half of the 32 KiB ring."""
    def b():
        run = Run(PLAIN, log=BIGLOG)
        assert run.until_up()
        run.host().plug()
        run.collect()
        return run
    return scenario(("biglog",), b)


HOOK_STRS = [b"early-before-bringup", b"alpha beta\n", b"tail-without-newline", b"key", b"x" * 250 + b"\n", b"\n\n"]
HOOK_LINES = ["alpha beta", "tail-without-newlinekey=0x1234 ", "x" * 200, "x" * 50, "0x0"]


def sc_hooks():
    """The loader's own log routines and status drawing, called on the engine after bringup, with the collector on the bus."""
    def b():
        addrs, a = [], S.LOAD + 0x68000
        for x in HOOK_STRS:
            addrs.append(a)
            a += (len(x) + 16) & ~15
        pre = [("log_str", addrs[0])]                                      # the engine is not up yet: this partial line must go nowhere (not into the next one)
        post = [("n47_draw_status",), ("n47_draw_status",), ("log_str", addrs[1]), ("log_str", addrs[2]), ("log_kv", addrs[3], 0x1234),
                ("log_char", 10), ("log_str", addrs[4]), ("log_str", addrs[5]), ("log_hex", 0), ("log_char", 10),
                ("mk_stage", 0x01), ("mk_stage", 0x3f), ("mk_stage", 0x41), ("mk_stage", 0x77)]
        run = Run(PLAIN, pre=pre, post=post)
        for ad, x in zip(addrs, HOOK_STRS):
            run.sim.write(ad, x + b"\0")
        assert run.until_up()
        run.host().plug()
        run.collect()
        return run
    return scenario(("hooks",), b)


def sc_down_exc():
    """The ladder stopped (the engine never starts) and then a CPU exception: the loader's exception loop must not touch the engine."""
    def b():
        brk = S.LOAD + 0x70000
        run = Run(PLAIN, dev_kw=dict(follow=False), tail=[("mk_stage", 0x40), (brk,)])
        run.sim.write(brk, struct.pack("<I", BRK_1234))
        run.record_until(60.0)
        return run
    return scenario(("down-exc",), b)


def sc_pdon():
    def b():
        run = Run(PLAIN, pd_on=True)
        assert run.until_up()
        run.host().plug()
        run.collect()
        return run
    return scenario(("pdon",), b)


def sc_attach():
    """A host that resets the bus and then does nothing: the device is connected but never configured."""
    def b():
        run = Run(PLAIN)
        assert run.until_up()
        run.host().m.attach()
        run.record_until(20.0)
        return run
    return scenario(("attach",), b)


def sc_exc_screen():
    """The 63 s build (the report loops need more than the 45 s deadline allows): a BRK in the loader's thread with the engine up."""
    def b():
        brk = S.LOAD + 0x70000
        run = Run(PLAIN, tail=[(brk,)], deadline_s=63)
        run.sim.write(brk, struct.pack("<I", BRK_1234))
        run.record_until(62.0, dt=1.0)
        return run
    return scenario(("exc-screen",), b)


def sc_pollfault_screen():
    def b():
        run = Run(PLAIN, deadline_s=63)
        assert run.until_up()
        run.host().m.attach()
        brk = S.LOAD + 0x70000
        run.sim.write(brk, struct.pack("<I", BRK_1234))
        run.sim.poll_inject = (run.sim.polls + 40, brk)
        run.record_until(62.0, dt=1.0)
        return run
    return scenario(("pollfault-screen",), b)


def phases(res):
    """The phase field of every distinct status frame the screen showed, in order, consecutive repeats removed."""
    out = []
    for f in res.frames:
        if f["kind"] == 13 and f["idx"] == 0 and (not out or out[-1] != f["data"] >> 8 & 0xF):
            out.append(f["data"] >> 8 & 0xF)
    return out


def texts(boot, kind=None):
    return [f["text"] for f in boot["frames"] if f["kind"] in ("log", "stage", "fault") and "text" in f and (kind is None or f["dev_kind"] == kind)]


def records(boot):
    return [f for f in boot["frames"] if f["kind"] not in ("end",)]


def usb(res):
    return d47.describe47(res.frames).get("usb", {})


def fnv1a64(s):
    h = 0xcbf29ce484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h


# ------------------------------------------------------------------------------------------------------------------- Aarch64
@needs_sim
class Aarch64Plain(unittest.TestCase):
    """loader-diag-usbmon with the collector on the bus from the moment the engine is up, until the 45 s reset."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_plain(PLAIN)
        cls.boot = cls.r.boots[0] if cls.r.boots else None

    def test_one_boot_one_clean_capture_no_violation_anywhere(self):
        r = self.r
        self.assertEqual(len(r.boots), 1)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.dev_viol, [])
        self.assertEqual(r.mmio_viol, [])
        self.assertEqual(r.model_viol, 0)

    def test_the_boot_id_ends_with_the_hash_of_the_image_name(self):
        name = self.boot["name"]
        want = struct.pack("<Q", fnv1a64(PLAIN)).hex()
        self.assertTrue(name.endswith(want), "%s does not end with %s" % (name, want))
        self.assertNotEqual(struct.pack("<Q", fnv1a64(FAULT)).hex(), want)

    def test_the_head_of_the_boot_id_is_the_loader_s_counter_when_the_bringup_started(self):
        head = int.from_bytes(bytes.fromhex(self.boot["name"][-32:-16]), "little")
        self.assertGreater(head, S.T0)
        self.assertLess(head, S.T0 + 10 * S.FREQ)

    def test_the_controller_is_given_the_vendor_frame_length_adjustment(self):
        writes = [v for o, v in self.r.wtrace if o == 0xC630]                 # GFLADJ
        self.assertEqual(writes, [0x80 | 0x20])                                # SDBND_SEL | the vendor DT's quirk-frame-length-adjustment

    def test_the_first_record_names_the_image_the_deadline_and_the_fault_setting(self):
        first = records(self.boot)[1]
        self.assertEqual((first["dev_kind"], first["text"]), ("boot", "NAT047 loader-diag-usbmon deadline_s=45 fault=0"))

    def test_the_stages_arrive_in_the_loader_s_order_including_the_one_current_when_the_engine_came_up(self):
        got = [(f["stage"], f["text"]) for f in records(self.boot) if f["kind"] == "stage"]
        self.assertEqual(got, STAGE_NAMES)

    def test_the_ladder_report_gives_both_summaries_and_one_line_per_hardware_access(self):
        lines = texts(self.boot)
        lad = [l for l in lines if l.startswith("LAD ")]
        self.assertEqual(len(lad), 2)
        ro, w = (re.match(r"LAD (\w) err=(-?\d+) err_op=(-?\d+) rung=(\d+) pd_was_on=(-?\d+) nrec=(\d+) soft=(\d+) gsnpsid=(0x[0-9a-f]+)", l) for l in lad)
        self.assertEqual((ro.group(1), int(ro.group(2)), int(ro.group(4))), ("R", 0, 2))
        self.assertEqual((w.group(1), int(w.group(2)), int(w.group(4))), ("W", 0, LAD_LAST))
        self.assertEqual(w.group(5), "0")                                       # the model's domain starts off
        for tag, m in (("R", ro), ("W", w)):
            lr = [l for l in lines if l.startswith("LR %s " % tag)]
            self.assertEqual(len(lr), int(m.group(6)), tag)
            ops = [int(re.match(r"LR \w (\d+) ", l).group(1)) for l in lr]
            self.assertEqual(ops, sorted(ops), tag)
        self.assertGreater(int(w.group(6)), int(ro.group(6)))
        self.assertEqual(int(w.group(8), 16), 0x5533330A)                       # the NAT-041 model's GSNPSID: the ladder read it back

    def test_the_loader_ram_log_arrives_byte_exact_in_order_after_the_ladder_report(self):
        recs = records(self.boot)
        i_last_lr = max(i for i, f in enumerate(recs) if f.get("text", "").startswith("LR "))
        i_next_stage = next(i for i, f in enumerate(recs) if f["kind"] == "stage" and f["stage"] == 0x21)
        chunks = [base64.b64decode(f["data_b64"]) for f in recs[i_last_lr + 1:i_next_stage]]
        self.assertEqual(b"".join(chunks), LOG)
        self.assertEqual([len(c) for c in chunks], [512] * (len(LOG) // 512) + [len(LOG) % 512])        # 512 bytes per record, the rest in the last
        self.assertGreater(i_next_stage - i_last_lr - 1, 2)                     # chunked: the log is larger than one record

    def test_the_hold_note_is_the_last_record_and_names_the_stage(self):
        self.assertEqual(texts(self.boot)[-1], "HOLD stage=0x40 code=0x0")

    def test_every_byte_the_engine_wrote_was_read_parsed_into_records_and_nothing_was_dropped(self):
        end = [f for f in self.boot["frames"] if f["kind"] == "end"][0]
        info = json.loads(base64.b64decode(end["data_b64"]))
        li = info["last_info"]
        self.assertEqual((li["dropped"], li["faults"], li["last_err"], li["stalls"]), (0, 0, 0, 0))
        self.assertEqual((info["unread_bytes"], info["next_offset"]), (0, li["written"]))
        dev = [f for f in self.boot["frames"] if "dev_seq" in f]
        self.assertEqual([f["dev_seq"] for f in dev], list(range(len(dev))))      # no gap in the engine's record numbers
        self.assertEqual(sum(P.REC_HDR + len(base64.b64decode(f["data_b64"])) for f in dev), li["written"])    # and no byte outside a record
        self.assertEqual(end["reason"], "disconnect")                           # the SoC reset took the device off the bus

    def test_the_reset_comes_at_the_deadline_with_the_vendor_values_and_the_watchdog_armed_before_it(self):
        r = self.r
        self.assertIsNotNone(r.reset_s)
        self.assertGreaterEqual(r.reset_s - 0.0, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertEqual((r.g044["fired"], r.g044["rc"]), (1, 0))               # the deadline fired once and the reset module returned nothing before the store
        self.assertEqual(r.g044["deadline_ticks"], S.FREQ * DEADLINE_S)
        self.assertEqual(r.done[0], ("recovery_guard", 0))
        first_wdt_write = next(t for k, _, _, t in r.wdt if k == "W")
        self.assertGreaterEqual(r.g044["t0"], first_wdt_write)                  # the deadline is measured from after the watchdog's first store
        self.assertEqual((r.fb_at_reset["kind"], r.fb_at_reset["idx"], r.fb_at_reset["data"]), (3, 0, 0x41))     # the RESET marker is on the screen

    def test_the_screen_carries_the_status_of_the_channel(self):
        u = usb(self.r)
        s = u["status"]
        for k in ("up", "connected", "configured", "nonce"):
            self.assertTrue(s[k], k)
        self.assertEqual((s["phase"], s["rung_done"]), ("up", LAD_LAST))
        self.assertFalse(s["faulted"] or s["poll_faulted"])
        self.assertEqual(u["stop"], (0, "none"))
        self.assertEqual(u["stop_op"], None)
        self.assertGreater(u["ladder_records"], 70)
        self.assertGreater(u["engine_bytes_written_low16"], 0)

    def test_the_screen_showed_every_phase_of_the_bringup_in_order(self):
        self.assertEqual(phases(self.r), [1, 2, 3, 4, 5])

    def test_the_status_on_the_screen_is_the_status_in_the_loader_s_memory(self):
        r = self.r
        shown = [f["data"] for f in r.frames if f["kind"] == 13 and f["idx"] == 0][-1]
        self.assertEqual(shown, 0x1 | 0x2 | 0x4 | 0x8 | (r.g["phase"] << 8) | (LAD_LAST << 12))      # up, connected, configured, nonce, phase, rung
        self.assertEqual(r.g["phase"], 5)
        self.assertEqual(r.g["err"], 0)
        self.assertEqual(r.g["connect_err"], 0)


@needs_sim
class Aarch64Fault(unittest.TestCase):
    """loader-diag-usbmon-fault: a controlled BRK #0x1234 once the host configured the device."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_plain(FAULT)
        cls.boot = cls.r.boots[0]

    def test_the_exception_arrives_as_a_fault_record_with_the_values_the_loader_s_vector_saw(self):
        rec = [f for f in self.boot["frames"] if f["kind"] == "fault" and f.get("dev_kind") == "fault"]
        exc = [f for f in self.boot["frames"] if f["kind"] == "fault" and f.get("source") == "get_exc"]
        self.assertEqual((len(rec), len(exc), len(self.r.excs)), (1, 1, 1))
        _, pc, insn = self.r.excs[0]
        self.assertEqual(insn, BRK_1234)
        off, size = nm_sizes(built() / FAULT / "loader.elf")["nat047_hold"]
        self.assertTrue(S.LOAD + off <= pc < S.LOAD + off + size, "the BRK is not inside nat047_hold")
        e = exc[0]
        self.assertEqual((e["esr"], e["elr"], e["far"], e["spsr"], e["stage"], e["valid"], e["count"]),
                         (0xF2001234, pc, S.EXC_FAR, 0x3C5, 0x1F, 1, 1))
        self.assertEqual((rec[0]["esr"], rec[0]["elr"], rec[0]["far"], rec[0]["stage"]), (0xF2001234, pc, S.EXC_FAR, 0x1F))
        self.assertTrue(S.LOAD <= e["sp"] < S.LOAD + 0x400000 and e["sp"] % 16 == 0, hex(e["sp"]))      # the loader's exception stack
        want = "EXCEPTION slot=4 esr=0xf2001234 elr=%#x far=%#x spsr=0x3c5" % (pc, S.EXC_FAR)
        self.assertIn(want, texts(self.boot))
        self.assertEqual(e["x"], [0] * 31)                                       # documented: x0..x30 are not captured by the loader's vectors

    def test_the_first_record_names_the_fault_image_and_the_fault_setting(self):
        first = records(self.boot)[1]
        self.assertEqual((first["dev_kind"], first["text"]), ("boot", "NAT047 loader-diag-usbmon-fault deadline_s=45 fault=1"))

    def test_the_text_around_the_fault_is_in_order_and_names_the_exception(self):
        t = texts(self.boot)
        i_hold, i_note, i_exc = t.index("HOLD stage=0x40 code=0x0"), t.index("controlled BRK #0x1234 follows"), \
            next(i for i, x in enumerate(t) if x.startswith("EXCEPTION slot=4 esr=0xf2001234"))
        self.assertLess(i_hold, i_note)
        self.assertLess(i_note, i_exc)
        self.assertEqual(len(self.r.excs), 1)
        stages = [(f["stage"], f["text"]) for f in records(self.boot) if f["kind"] == "stage"]
        self.assertEqual(stages[-1], (0x1F, "exception"))

    def test_with_a_host_that_already_configured_the_device_the_brk_follows_the_hold_note_at_once(self):
        self.assertEqual(len(self.r.hold_t), 1)
        self.assertLess(self.r.exc_t[0] - self.r.hold_t[0], 1.0)

    def test_the_reset_still_comes_at_the_deadline_and_the_screen_reports_the_fault(self):
        r = self.r
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual((r.errors, r.dev_viol, r.mmio_viol, r.model_viol), ([], [], [], 0))
        self.assertTrue(usb(r)["status"]["faulted"])
        self.assertFalse(usb(r)["status"]["poll_faulted"])


@needs_sim
class Aarch64NoCable(unittest.TestCase):
    """No host at all: the bounded wait times out and the run continues to the reset exactly as the NAT-044 image would."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_nocable()

    def test_the_connect_wait_times_out_with_the_documented_code_and_the_loader_goes_on(self):
        r = self.r
        self.assertEqual(d47.stop_code(-r.g["connect_err"]), (7, "timeout"))
        self.assertEqual(r.g["phase"], 5)
        self.assertEqual(r.g["holds"], 1)
        t_wait = next(x["t"] for x in r.timeline if x["phase"] == 4)
        t_done = next(x["t"] for x in r.timeline if x["phase"] == 5)
        self.assertGreaterEqual(t_done - t_wait, 3.0 - 0.15)                      # bounded by time (3 s), not by a number of polls
        self.assertLess(t_done - t_wait, 3.0 + 1.0)
        t20 = next(x for x in r.timeline if x["t"] >= 20.0)
        self.assertEqual(t20["holds"], 1)                                         # eight stage dwells and the 3 s wait later: in the hold loop, 25 s before the deadline

    def test_the_reset_comes_at_the_deadline_with_nothing_changed(self):
        r = self.r
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))

    def test_an_idle_poll_costs_a_small_bounded_number_of_register_accesses(self):
        tl = [x for x in self.r.timeline if 15.0 <= x["t"] <= 40.0]
        d_poll, d_mmio = tl[-1]["polls"] - tl[0]["polls"], tl[-1]["nmmio"] - tl[0]["nmmio"]
        self.assertGreater(d_poll, 1000)
        self.assertLessEqual(d_mmio / d_poll, 3.0, "%d register accesses in %d idle polls" % (d_mmio, d_poll))

    def test_the_loader_polls_the_engine_in_every_tenth_of_a_second_of_the_hold_loop(self):
        tl = [x for x in self.r.timeline if 15.0 <= x["t"] <= 40.0]
        self.assertGreater(len(tl), 200)
        for a, b in zip(tl, tl[1:]):
            self.assertGreaterEqual(b["polls"] - a["polls"], 20, "%.1f s" % b["t"])

    def test_the_screen_showed_every_phase_of_the_bringup_in_order(self):
        self.assertEqual(phases(self.r), [1, 2, 3, 4, 5])

    def test_the_screen_says_up_but_never_connected(self):
        s = usb(self.r)["status"]
        self.assertTrue(s["up"])
        self.assertFalse(s["connected"] or s["configured"])
        self.assertEqual(s["phase"], "up")


@needs_sim
class Aarch64FaultNoCable(unittest.TestCase):
    """The fault image with no host: the BRK waits its bounded time for the host to configure the device, then fires anyway."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_fault_nocable()

    def test_the_brk_fires_after_the_bounded_eight_second_wait(self):
        r = self.r
        self.assertEqual((len(r.hold_t), len(r.exc_t)), (1, 1))
        self.assertGreaterEqual(r.exc_t[0] - r.hold_t[0], 8.0)
        self.assertLess(r.exc_t[0] - r.hold_t[0], 9.5)

    def test_the_loader_survives_the_fault_and_resets_at_the_deadline(self):
        r = self.r
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual(r.g["faulted"], 1)                                      # in memory; the screen's exception loop reaches its USB frames only after the long kick report
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))


@needs_sim
class Aarch64LatePlug(unittest.TestCase):
    """The cable arrives 20 s after the engine came up: everything written before is still in the ring and arrives complete."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_late(20.0)
        cls.base = sc_plain(PLAIN)

    def test_the_records_written_long_before_the_cable_arrive_the_same_as_with_an_early_cable(self):
        pick = lambda b: [(f.get("dev_kind"), f.get("text")) for f in records(b)]   # noqa: E731
        self.assertEqual(pick(self.r.boots[0]), pick(self.base.boots[0]))
        self.assertGreater(len(pick(self.r.boots[0])), 100)
        self.assertEqual(self.r.errors, [])

    def test_the_connect_timeout_is_still_reported_and_the_reset_is_not_late(self):
        r = self.r
        self.assertEqual(d47.stop_code(-r.g["connect_err"]), (7, "timeout"))
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))

    def test_the_host_connects_to_the_hold_loop_and_sees_the_connected_status_from_then_on(self):
        s = usb(self.r)["status"]
        self.assertTrue(s["connected"] and s["configured"])


@needs_sim
class Aarch64LadderStop(unittest.TestCase):
    """The platform ladder cannot power the domain (the model ignores the PMU request): the loader behaves like the NAT-044 image."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_stopped()

    def test_the_ladder_stops_in_rung_three_with_a_timeout_and_the_engine_never_starts(self):
        r = self.r
        self.assertEqual(H.decode_err(r.g["err"]), (3, "timeout"))
        self.assertEqual(r.g["phase"], 6)
        self.assertEqual(r.g["up"], 0)
        self.assertEqual(r.g["connect_err"], 0)

    def test_the_screen_reports_the_stop_code_and_the_op(self):
        u = usb(self.r)
        self.assertEqual(u["stop"], (3, "timeout"))
        self.assertEqual(u["status"]["phase"], "stopped")
        self.assertFalse(u["status"]["up"])
        self.assertNotEqual(self.r.g["err_op"], self.r.g["nrec"])
        op = H.ops()[self.r.g["err_op"]]                                          # the op that timed out: the power-domain wait of rung 3
        self.assertEqual((op["kind"], op["rung"]), ("WAIT", 3))
        self.assertGreater(self.r.g["nrec"], 0)
        self.assertEqual((u["stop_op"], u["ladder_records"], u["engine_bytes_written_low16"]), (self.r.g["err_op"], self.r.g["nrec"], 0))
        self.assertEqual(phases(self.r), [1, 2, 6])

    def test_after_the_stop_no_register_is_touched_again_and_every_nat047_hook_is_a_no_op(self):
        tl = self.r.timeline
        i = next(i for i, x in enumerate(tl) if x["phase"] == 6)
        self.assertEqual(tl[-1]["nmmio"], tl[i]["nmmio"])
        self.assertEqual(self.r.polls, 0)
        self.assertEqual(self.r.dev_viol, [])

    def test_the_engine_that_never_started_is_never_written_by_the_stage_log_and_hold_hooks(self):
        r = self.r
        done = [n for n, _ in r.done]
        self.assertEqual(done.count("mk_stage"), 1 + len(STAGES_AFTER))                # every stage hook ran after the stop
        self.assertEqual(r.g["holds"], 1)                                              # and so did the hold hook
        self.assertEqual(r.mem_engine, bytes(len(r.mem_engine)))
        self.assertEqual(r.mem_ring, bytes(len(r.mem_ring)))
        self.assertEqual(r.mem_line, bytes(len(r.mem_line)))
        self.assertEqual((r.g["line_len"], r.g["log_on"]), (0, 0))

    def test_the_run_still_ends_with_the_reset_at_the_deadline(self):
        r = self.r
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual(len(r.excs), 0)


@needs_sim
class Aarch64Hooks(unittest.TestCase):
    """The hooks the patch puts into the loader's own routines, called on a running engine."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_hooks()
        cls.boot = cls.r.boots[0]

    def test_one_status_draw_polls_the_engine_once_per_band(self):
        r = self.r
        idx = [i for i, (n, _) in enumerate(r.done) if n == "n47_draw_status"]
        self.assertEqual(len(idx), 2)
        for i in idx:
            self.assertEqual(r.done_polls[i] - r.done_polls[i - 1], d47.base.BANDS)

    def test_what_the_loader_logs_reaches_the_host_one_line_at_a_time(self):
        t = texts(self.boot, "text")
        i = t.index(HOOK_LINES[0])
        self.assertEqual(t[i:i + len(HOOK_LINES)], HOOK_LINES)      # a line ends at the newline, or at 200 characters; an empty line is not a record
        self.assertNotIn("", t)

    def test_what_the_loader_logs_before_the_engine_is_up_goes_nowhere(self):
        self.assertNotIn(b"early-before-bringup", self.boot["payload"])
        self.assertEqual([x for x in self.r.done if x[0] == "log_str"][0][0], "log_str")          # the call ran
        self.assertEqual(self.r.errors, [])

    def test_the_stage_records_carry_the_names_of_the_loader_s_stages(self):
        got = [(f["stage"], f["text"]) for f in records(self.boot) if f["kind"] == "stage"][:5]
        self.assertEqual(got, [(0x20, "loader_main"), (0x01, "entry"), (0x3F, "fail"), (0x41, "reset"), (0x77, "stage")])


@needs_sim
class Aarch64EngineDownException(unittest.TestCase):
    """A CPU exception when the engine never came up: the exception loop reports on the screen only, touches no register of the
    engine and the reset still comes."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_down_exc()

    def test_the_exception_is_counted_and_the_engine_is_left_alone(self):
        r = self.r
        self.assertEqual(len(r.excs), 1)
        self.assertEqual((r.g["up"], r.g["poll_faulted"], r.g["faulted"], r.g["phase"]), (0, 0, 1, 6))
        i = next(i for i, x in enumerate(r.timeline) if x["nexc"])
        self.assertEqual(r.timeline[-1]["nmmio"], r.timeline[i]["nmmio"])
        self.assertEqual(r.polls, 0)
        self.assertEqual(r.mem_engine, bytes(len(r.mem_engine)))                   # not even a record or a counter of the engine was written
        self.assertEqual(r.mem_ring, bytes(len(r.mem_ring)))

    def test_the_reset_still_comes_at_the_deadline(self):
        r = self.r
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))


@needs_sim
class Aarch64PowerDomainWasOn(unittest.TestCase):
    """The HSI0 power domain was already on when the loader got there: the ladders report it, the screen carries it."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_pdon()
        cls.boot = cls.r.boots[0]

    def test_both_ladder_summaries_say_the_domain_was_on_and_the_run_is_otherwise_the_same(self):
        lad = [l for l in texts(self.boot) if l.startswith("LAD ")]
        self.assertEqual(len(lad), 2)
        for l in lad:
            self.assertIn(" err=0 ", l)
            self.assertIn(" pd_was_on=1 ", l)
        self.assertEqual(self.r.errors, [])
        self.assertEqual((self.r.dev_viol, self.r.mmio_viol, self.r.model_viol), ([], [], 0))

    def test_the_screen_carries_the_bit(self):
        s = usb(self.r)["status"]
        self.assertTrue(s["pd_was_on"] and s["up"] and s["configured"])


@needs_sim
class Aarch64ConnectedNotConfigured(unittest.TestCase):
    """The host resets the bus and goes away before configuring the device."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_attach()

    def test_the_status_says_connected_and_nothing_more(self):
        s = usb(self.r)["status"]
        self.assertEqual((s["up"], s["connected"], s["configured"], s["nonce"]), (True, True, False, False))

    def test_the_connect_wait_ends_at_once_with_no_error(self):
        r = self.r
        self.assertEqual(r.g["connect_err"], 0)
        t_done = next(x["t"] for x in r.timeline if x["phase"] == 5)
        t_done_no_cable = next(x["t"] for x in sc_nocable().timeline if x["phase"] == 5)      # the same start, 3 s of waiting
        self.assertLess(t_done, t_done_no_cable - 2.5)


@needs_sim
class Aarch64ExceptionScreen(unittest.TestCase):
    """The exception loop's fallback report on the screen (reachable only past the 45 s deadline, hence the 63 s build)."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_exc_screen()

    def test_the_exception_loop_shows_the_usb_frames_with_the_fault_bit(self):
        r = self.r
        self.assertEqual(len(r.excs), 1)
        u = usb(r)
        self.assertTrue(u["status"]["up"] and u["status"]["faulted"])
        self.assertFalse(u["status"]["poll_faulted"])
        self.assertEqual(u["ladder_records"], r.g["nrec"])
        self.assertEqual(u["stop"], (0, "none"))

    def test_nothing_else_is_disturbed(self):
        r = self.r
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))
        self.assertIsNone(r.reset_s)                                             # the 63 s deadline had not come


@needs_sim
class Aarch64PollFaultScreen(unittest.TestCase):
    """A fault inside the engine's poll with a connected host: the dead engine reports as down, not as connected."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_pollfault_screen()

    def test_the_screen_says_poll_faulted_and_not_up_and_not_connected(self):
        s = usb(self.r)["status"]
        self.assertEqual((s["poll_faulted"], s["faulted"], s["up"], s["connected"], s["configured"]), (True, True, False, False, False))


@needs_sim
class Aarch64PollFault(unittest.TestCase):
    """A CPU exception inside the engine's poll takes the engine out of service; the loader's exception loop and the reset go on."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_pollfault()

    def test_the_fault_marks_the_engine_unusable_and_it_is_never_polled_again(self):
        r = self.r
        self.assertEqual(len(r.excs), 1)
        self.assertEqual((r.g["up"], r.g["poll_faulted"], r.g["faulted"]), (0, 1, 1))
        i = next(i for i, x in enumerate(r.timeline) if x["nexc"])
        self.assertEqual(r.timeline[-1]["polls"], r.timeline[i]["polls"])
        self.assertEqual(r.timeline[-1]["nmmio"], r.timeline[i]["nmmio"])
        self.assertTrue(usb(r)["status"]["poll_faulted"])
        self.assertFalse(usb(r)["status"]["up"])

    def test_the_exception_loop_keeps_reporting_and_the_reset_still_comes(self):
        r = self.r
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))


@needs_sim
class Aarch64EngineStartFails(unittest.TestCase):
    """The ladder is through and the engine refuses to start: stopped with the engine's own code, no op, nothing polled afterwards."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_start_fail()

    def test_the_loader_records_the_start_failure_and_does_not_report_the_engine_up(self):
        r = self.r
        self.assertEqual(H.decode_err(r.g["err"]), (6, "notalive"))
        self.assertEqual((r.g["up"], r.g["phase"], r.g["log_on"], r.g["connect_err"]), (0, 6, 0, 0))
        self.assertEqual(r.g["err_op"], 0xFFFF)                                      # the failure is the engine's, not one of the ladder's ops
        self.assertEqual(phases(r), [1, 2, 3, 6])
        u = usb(r)
        self.assertEqual((u["stop"], u["stop_op"], u["engine_bytes_written_low16"]), ((6, "notalive"), None, 0))
        self.assertEqual((u["status"]["phase"], u["status"]["up"], u["status"]["connected"]), ("stopped", False, False))

    def test_nothing_is_polled_or_written_to_the_controller_afterwards_and_the_reset_comes(self):
        r = self.r
        self.assertEqual(r.polls, 0)
        self.assertEqual(r.mem_ring, bytes(len(r.mem_ring)))                          # no record was ever written
        self.assertEqual(r.pmu_w, PMU_WRITES)
        self.assertGreaterEqual(r.reset_s, DEADLINE_S)
        self.assertLess(r.reset_s, DEADLINE_S + 3.0)
        self.assertEqual((r.dev_viol, r.mmio_viol, r.model_viol), ([], [], 0))


@needs_sim
class Aarch64BigLog(unittest.TestCase):
    """The ring is the size the build says: a loader log of more than half of it, collected before the host drains anything, is whole."""
    @classmethod
    def setUpClass(cls):
        cls.r = sc_biglog()
        cls.boot = cls.r.boots[0] if cls.r.boots else None

    def test_the_whole_log_arrives_with_no_drop_although_it_does_not_fit_in_half_the_ring(self):
        self.assertEqual(len(self.r.boots), 1)
        end = [f for f in self.boot["frames"] if f["kind"] == "end"][0]
        li = json.loads(base64.b64decode(end["data_b64"]))["last_info"]
        self.assertGreater(li["written"], 16384 + 4096)                                # more than half of the ring was in use at once
        self.assertLess(li["written"], 32768)
        self.assertEqual((li["dropped"], li["faults"], li["last_err"]), (0, 0, 0))
        payload = self.boot["payload"]
        self.assertIn(BIGLOG, payload)                                                 # byte exact, in one piece
        self.assertEqual(self.r.errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
