#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-075 host tests: the packaged image loader-diag-xnu-bigwin-md1 (NAT-074's build), its derived driver and its analyser. Evidence kind: host-test.
Nothing here talks to a phone, and nothing shows what the S24 does with a 4096 MiB window, 16 KiB pages or a 2.3 GiB reserved RAMDisk1.

    <venv with pyusb>/bin/python -W ignore -I docs/procedures/nat-075/test_nat075.py        (seconds; the artifact layers skip themselves without their artifacts)

Layers:
  Package   the RECOVERY candidate carries NAT-074's Image.payload at offset 2048, differs from the stock image in the first 2048 bytes only at the header fields the packager rewrites, and its pins are the driver's.
  Cmdline   the command line inside the payload is NAT-067's with the NAT-075 tag (the touch and battery drivers off: the flaw NAT-074's first build had).
  Driver    session_nat075.py is what derive.py makes from session_nat067.py (a drifted source is refused); its gates behave as the NAT-067 driver's on a temporary tree.
  Reading   the analyser's readings on the delivered text: md devices, page size from vm_page_bootstrap, the return class and the pre-registered pass rule.
  Analyser  NAT-065's analyser under the new image name; the NAT-068 run (another image) is not accepted and does not satisfy the NAT-075 rule."""
import hashlib, importlib.util, io, json, os, struct, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
IMAGE = "loader-diag-xnu-bigwin-md1"
IMAGE67 = "loader-diag-xnu-ne1-usb"
BUILD = Path(os.environ.get("NAT075_BUILD") or ROOT / "artifacts/nat-074/build-002")
PACKAGE = ROOT / "artifacts/nat-075/package-001"
NAT68_LOG = PROC / "nat-068" / "run-001-kernel-log.txt"
NAT68_RUN = ROOT / "artifacts/nat-068/run-001"
LOADER_IMAGE_BYTES = 307200
CMD_OFF, CMD_LEN = 0x48, 608
EXPECTED_CMDLINE = ("rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT075-md1 debug=0xc serial=3 cpus=1 keepsyms=1 -v "
                    "loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0")
RESERVE = 2475720704
STOCK_SHA = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
DERIVE_PY = Path(os.environ.get("NAT075_DERIVE") or HERE / "derive.py")
DRIVER_PY = Path(os.environ.get("NAT075_DRIVER") or HERE / "session_nat075.py")
ANALYZE_PY = Path(os.environ.get("NAT075_ANALYZE") or HERE / "analyze_nat075.py")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def md_line(n, size):
    return "Added memory device md%d/rmd%d (01000000/0D000000) at FFFFFFF008974000 for %016X\n" % (n, n, size)


def vm_line(total, wired=4000):
    return "vm_page_bootstrap: %d free pages, %d wired pages\n" % (total - wired, wired)


# ------------------------------------------------------------------------------------------------------------------ Package
@unittest.skipUnless((PACKAGE / "package.json").exists() and (BUILD / "build.json").exists(), "artifacts/nat-075/package-001 or artifacts/nat-074/build-002 is not present")
class Package(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = json.loads((PACKAGE / "package.json").read_text())
        cls.p = cls.pkg["images"][IMAGE]
        cls.rec = (PACKAGE / IMAGE / "recovery.img").read_bytes()
        cls.pl = (BUILD / IMAGE / "Image.payload").read_bytes()

    def test_the_candidate_carries_the_nat074_payload_at_2048_and_the_pins_are_the_package_record(self):
        p = self.p
        self.assertEqual(sorted(self.pkg["images"]), [IMAGE])
        self.assertTrue(self.pkg["flashed"] is False and self.pkg["device_used"] is False and self.pkg["kind"] == "host-test")
        self.assertEqual((len(self.rec), p["recovery_bytes"]), (100663296, 100663296))
        self.assertEqual(sha(self.rec), p["recovery_sha256"])
        self.assertEqual(self.rec[2048:2048 + len(self.pl)], self.pl)
        self.assertEqual((sha(self.pl), len(self.pl), p["payload_offset"]), (p["payload_sha256"], p["payload_bytes"], 2048))
        self.assertEqual(p["loader_image_sha256"], sha((BUILD / IMAGE / "Image").read_bytes()))
        head, image = bytearray(self.pl[:LOADER_IMAGE_BYTES]), (BUILD / IMAGE / "Image").read_bytes()
        self.assertEqual(struct.unpack_from("<Q", head, 16)[0], len(self.pl), "the loader's header word 16 holds the payload length")
        head[16:24] = image[16:24]
        self.assertEqual(bytes(head), image, "the payload starts with the loader image, apart from that length word")
        self.assertEqual(self.pkg["stock_sha256"], STOCK_SHA)

    def test_only_the_boot_image_header_differs_from_the_stock_image(self):
        stock = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
        if not stock.exists():
            self.skipTest("the stock backup is not present")
        st = stock.read_bytes()
        self.assertEqual(sha(st), STOCK_SHA)
        self.assertEqual(len(st), len(self.rec))
        diff = [i for i in range(2048) if self.rec[i] != st[i]]
        allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(576, 596)) | set(range(1636, 1644))
        self.assertTrue(diff and set(diff) <= allowed, [i for i in diff if i not in allowed])
        self.assertEqual(struct.unpack_from("<I", self.rec, 8)[0], len(self.pl))

    def test_the_payload_is_a_different_image_from_the_nat067_one(self):
        old = ROOT / "artifacts/nat-075/../nat-067/package-001/package.json"
        if not old.exists():
            self.skipTest("NAT-067's package record is not present")
        o = json.loads(old.read_text())["images"][IMAGE67]
        self.assertNotEqual(self.p["recovery_sha256"], o["recovery_sha256"])
        self.assertNotEqual(self.p["payload_sha256"], o["payload_sha256"])


# ------------------------------------------------------------------------------------------------------------------ Cmdline
@unittest.skipUnless((BUILD / IMAGE / "Image.payload").exists(), "artifacts/nat-074/build-002 is not present")
class Cmdline(unittest.TestCase):
    def test_the_payload_command_line_is_nat067s_with_the_nat075_tag(self):
        pl = (BUILD / IMAGE / "Image.payload").read_bytes()[LOADER_IMAGE_BYTES:]
        field = pl[CMD_OFF:CMD_OFF + CMD_LEN]
        text = field.split(b"\0", 1)[0].decode()
        self.assertEqual(text, EXPECTED_CMDLINE)
        self.assertTrue(set(field.split(b"\0", 1)[1]) <= {0}, "the field is NUL-padded")
        self.assertIn(" e1stouch=0 e1sbattery=0", text)
        self.assertNotIn("NAT065", text)
        self.assertNotIn("NAT067", text)

    def test_the_boot_record_tag_is_the_new_image_name(self):
        b = json.loads((BUILD.parent / "build-002" / "build.json").read_text())
        flags = [c for c in b["commands"] if "NAT047_TAG" in json.dumps(c)]
        self.assertTrue(flags)
        for c in flags:
            s = json.dumps(c)
            self.assertIn('NAT047_TAG=\\"%s\\"' % IMAGE, s)
            self.assertNotIn(IMAGE67, s)


# ------------------------------------------------------------------------------------------------------------------ Driver
class Driver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load(DERIVE_PY, "nat075_derive_under_test")
        cls.text67 = (PROC / "nat-067" / "session_nat067.py").read_text()
        cls.text75 = DRIVER_PY.read_text()
        cls.pins = ("e" * 64, "f" * 64, 21878704)

    def test_the_committed_driver_is_what_the_derivation_gives(self):
        if not (PACKAGE / "package.json").exists():
            self.skipTest("artifacts/nat-075/package-001 is not present")
        self.assertEqual(self.d.derive_session(self.text67, *self.d.package_values()), self.text75)

    def test_the_derivation_changes_only_the_listed_lines(self):
        t = self.d.derive_session(self.text67, *self.pins)
        end = "(run separately).\"\"\""
        a, b = self.text67.splitlines(), t.splitlines()
        ia = next(i for i, x in enumerate(a) if x.endswith(end))
        ib = next(i for i, x in enumerate(b) if x.endswith(end))
        code_a, code_b = a[ia + 1:], b[ib + 1:]
        self.assertEqual(len(code_a), len(code_b), "the code after the docstring has the same number of lines")
        changed = [(x, y) for x, y in zip(code_a, code_b) if x != y]
        keys = ("'%s':dict(" % IMAGE67, "NEW_SHA=", "CANARY_SHA=", "PACKAGE=", "REQUIRED_DONE=", "glob(", "marker=")
        self.assertEqual(len(changed), len(keys), [x for x, _ in changed])
        for (x, y), k in zip(changed, keys):
            self.assertIn(k, x)
            self.assertNotEqual(x, y)
        self.assertIn("'NAT-068','NAT-074')", [y for _, y in changed][4])
        for keep in ("def gate(", "def registry_blocker(", "WRITE=", "TARGET='/dev/block/sda18'", "assert len(data)==SIZE and digest(data)==expected"):
            self.assertIn(keep, t)
            self.assertEqual(t.count(keep), self.text67.count(keep), keep)
        self.assertNotIn("nat067", t.replace(self.d.DOC, ""))

    def test_the_derivation_uses_the_values_it_is_given(self):
        t = self.d.derive_session(self.text67, "a" * 64, "b" * 64, 12345)
        self.assertIn("NEW_SHA='%s'" % ("a" * 64), t)
        self.assertIn("CANARY_SHA='%s'" % ("b" * 64), t)
        self.assertIn("CANARY_LEN=12345", t)
        self.assertNotIn("21878704", t.split("CANARY_LEN=")[1].split("\n")[0])

    def test_a_drifted_nat067_driver_is_refused(self):
        for old, new in (("'loader-diag-xnu-ne1-usb':dict(", "'x':dict("),
                         ("CANARY_LEN=21878704", "CANARY_LEN=1"),
                         ("artifacts/nat-067/package-001", "artifacts/nat-099/package-001"),
                         ("*-nat067-%s-single-run-*.md", "*-nat067-%s-run-*.md"),
                         ("'NAT-066','NAT-067')", "'NAT-066')")):
            self.assertEqual(self.text67.count(old), 1, old)
            with self.assertRaises(AssertionError, msg=old):
                self.d.derive_session(self.text67.replace(old, new), *self.pins)

    def test_the_driver_pins_and_paths(self):
        mod = load(DRIVER_PY, "nat075_session_mod")
        self.assertEqual(sorted(mod.IMAGES), [IMAGE])
        self.assertTrue(str(mod.PACKAGE).endswith("artifacts/nat-075/package-001"))
        self.assertEqual(mod.STOCK_SHA, STOCK_SHA)
        self.assertEqual((mod.TARGET, mod.SIZE, mod.PAYLOAD_OFFSET), ("/dev/block/sda18", 100663296, 2048))
        for t in ("NAT-067", "NAT-068", "NAT-074", "NAT-065", "NAT-060", "NAT-043"):
            self.assertIn(t, mod.REQUIRED_DONE)
        self.assertNotIn("NAT-075", mod.REQUIRED_DONE, "the run's own task is not its own prerequisite")
        self.assertGreaterEqual(min(mod.WATCH_S, mod.COLLECT_S), 330, "both outlive the slowest expected return (+200 s) plus the analyser's 120 s reach")
        if (PACKAGE / "package.json").exists():
            p = json.loads((PACKAGE / "package.json").read_text())["images"][IMAGE]
            cfg = mod.IMAGES[IMAGE]
            self.assertEqual((cfg["NEW_SHA"], cfg["CANARY_SHA"], cfg["CANARY_LEN"]), (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))

    def test_the_gates_on_a_temporary_tree(self):
        mod = load(DRIVER_PY, "nat075_session_gates")
        cfg = mod.IMAGES[IMAGE]
        with tempfile.TemporaryDirectory(prefix="nat075-", dir=os.environ.get("TMPDIR")) as w:
            root = Path(w)
            (root / "docs/decisions").mkdir(parents=True)
            (root / "state").mkdir()
            mod.ROOT = root
            with self.assertRaises(AssertionError, msg="no decision file"):
                mod.gate(IMAGE, cfg)
            d = root / ("docs/decisions/0029-nat075-%s-single-run-2026-11-12.md" % IMAGE)
            d.write_text("decision 0019 %s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            self.assertEqual(mod.gate(IMAGE, cfg), d)
            for text in ("decision 0019 %s" % cfg["NEW_SHA"], "%s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]), "decision 0019 %s" % cfg["CANARY_SHA"]):
                d.write_text(text)
                with self.assertRaises(AssertionError, msg=text):
                    mod.gate(IMAGE, cfg)
            d.write_text("decision 0019 %s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            other = root / ("docs/decisions/0030-nat075-%s-single-run-2026-11-13.md" % IMAGE)
            other.write_text("x")
            with self.assertRaises(AssertionError, msg="two decision files"):
                mod.gate(IMAGE, cfg)
            other.unlink()
            (root / ("docs/decisions/0030-nat067-%s-single-run-2026-11-13.md" % IMAGE)).write_text("x")
            self.assertEqual(mod.gate(IMAGE, cfg), d, "a NAT-067 decision file is not a NAT-075 one")

            def write_state(native, decision, done):
                st = dict(project=dict(permissions=dict(native=native),
                                       permission_decisions=[dict(scope="native", value=native, decision=decision)] if decision else []),
                          tasks=[dict(id=t, status="done") for t in done])
                (root / "state/lab.json").write_text(json.dumps(st))
            allt = list(mod.REQUIRED_DONE)
            write_state(False, "docs/decisions/" + d.name, allt)
            self.assertIn("native permission is not set", mod.registry_blocker(d))
            write_state(True, "docs/decisions/other.md", allt)
            self.assertIn("does not cite", mod.registry_blocker(d))
            for need in ("NAT-068", "NAT-074", "NAT-067"):
                write_state(True, "docs/decisions/" + d.name, [t for t in allt if t != need])
                self.assertIn(need, mod.registry_blocker(d), need)
            write_state(True, "docs/decisions/" + d.name, allt)
            self.assertIsNone(mod.registry_blocker(d))


# ------------------------------------------------------------------------------------------------------------------ Reading
class Reading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = load(ANALYZE_PY, "nat075_analyze_under_test")

    def test_md_devices_are_listed_with_their_byte_sizes(self):
        text = "noise\n" + md_line(0, 0x8000) + "more\n" + md_line(1, RESERVE)
        md = self.a.read_md(text)
        self.assertEqual([(d["name"], d["size"]) for d in md], [("md0", 0x8000), ("md1", RESERVE)])
        self.assertEqual(self.a.read_md("nothing here"), [])

    def test_md1_ok_needs_the_reserve_size_exactly(self):
        ok = lambda t: self.a.readings(t, None, "PASS", "probe-ran-to-exit")["md1_ok"]
        self.assertTrue(ok(md_line(0, 0x8000) + md_line(1, RESERVE)))
        self.assertFalse(ok(md_line(0, 0x8000)), "md1 absent")
        self.assertFalse(ok(md_line(0, 0x8000) + md_line(1, RESERVE - 0x1000)), "one page short")
        self.assertFalse(ok(md_line(0, 0x8000) + md_line(1, RESERVE + 0x1000)), "one page long")
        self.assertFalse(ok(md_line(0, RESERVE)), "the size on md0 is not md1")
        self.assertFalse(ok(md_line(1, 0x8000)), "md1 with the probe's size")

    def test_page_size_follows_from_the_page_count_and_the_window(self):
        r16 = self.a.read_vm(vm_line(262144 - 3000))
        self.assertEqual((r16["total"], r16["page_size"]), (259144, 16384), "a 16 KiB-page kernel: 4096 MiB / 16 KiB = 262144 pages, a few thousand lost to boot structures")
        r4 = self.a.read_vm(vm_line(1048576 - 12000))
        self.assertEqual(r4["page_size"], 4096)
        r = self.a.read_vm(vm_line(131072))
        self.assertEqual((r["found"], r["page_size"]), (True, None), "131072 pages is the 512 MiB window of NAT-068, in neither reading of a 4096 MiB window")
        self.assertEqual(self.a.read_vm("no such line")["found"], False)
        self.assertEqual(self.a.read_vm(vm_line(262144 * 2))["page_size"], None)

    def test_the_loader_readings_for_the_expected_and_for_other_runs(self):
        lines = ["NAT047 x deadline_s=150 fault=0", "window from DTB=0x8fe400000 win=0x8fe400000 win size=0x100000000 ",
                 "ticks=0x1 zero_bytes=0x1000000 ", "ticks=0x2 zero_bytes=0x8b7c000 ", "ticks=0x3 clean_full_window_begin=0x8fe400000 ",
                 "ticks=0x4 clean_full_window_end=0x9fe400000 "]
        r = self.a.read_loader(lines)
        self.assertEqual((r["window_base"], r["window_size"], r["zero_bytes_final"], r["clean_span"]), (0x8fe400000, 1 << 32, 146259968, 1 << 32))
        self.assertTrue(r["window_ok"] and r["zero_ok"] and r["clean_ok"] and r["found"])
        self.assertEqual(r["refusals"], [])
        r = self.a.read_loader(lines[:2] + ["reserve layout does not fit the window", "bad payload header"])
        self.assertEqual((r["zero_bytes_final"], r["clean_span"], r["zero_ok"], r["clean_ok"]), (None, None, False, False))
        self.assertEqual(r["refusals"], ["does not fit", "bad payload header"])
        r = self.a.read_loader([l.replace("0x100000000", "0x20000000") for l in lines])
        self.assertFalse(r["window_ok"], "a 512 MiB window is not this image's")
        r = self.a.read_loader(lines[:3] + ["ticks=0x2 zero_bytes=0x8b7b000 "])
        self.assertEqual((r["zero_bytes_final"], r["zero_ok"]), (0x8b7b000, False), "the last value is the final one, and it must be exact")
        r = self.a.read_loader([])
        self.assertEqual((r["found"], r["window_ok"], r["zero_ok"], r["clean_ok"], r["refusals"]), (False, False, False, False, []))

    def test_the_return_is_classified_against_the_two_clocks(self):
        c = lambda dt, k="download": self.a.classify_return(dict(dt=dt, klass=k))["cls"]
        for dt in (165.0, 173.2, 177.7, 181.0, 195.0):
            self.assertEqual(c(dt), "cap-reset", dt)
        self.assertEqual(c(164.9), "download-other-early", "just before the window")
        self.assertEqual(c(195.1), "download-other-late")
        self.assertEqual(c(200.0), "download-other-late")
        self.assertEqual(c(150.0), "download-other-early")
        self.assertEqual(c(114.0), "download-other-early", "a Download Mode return at the old 83 s watchdog time is not a cap reset")
        self.assertEqual(c(87.72), "download-other-early", "the NAT-068 return (a 60 s loader deadline) is not a cap reset")
        for dt in (85.0, 95.0, 105.0):
            self.assertEqual(c(dt, "upload"), "watchdog-upload", dt)
        self.assertEqual(c(84.9, "upload"), "upload-other")
        self.assertEqual(c(105.1, "upload"), "upload-other")
        self.assertEqual(c(175.0, "upload"), "upload-other", "SEC_UPLOAD at the cap time is not the cap reset")
        self.assertEqual(c(181.0, "android"), "not-download-android")
        self.assertEqual(self.a.classify_return(None)["cls"], "no-return-seen")
        self.assertEqual(self.a.classify_return(dict(dt=None, klass=None))["cls"], "not-download-None")

    def test_the_windows_do_not_overlap_and_follow_from_the_measured_clocks(self):
        a = self.a
        lo, hi = a.upload_window()
        self.assertEqual((lo, hi), (85.0, 105.0), "NAT-048's baseline of runs 001-009: +95 s +- 10 s")
        self.assertLess(hi, a.CAP_RETURN[0])
        # NAT-068: Download Mode at +87.72 s for a 60 s deadline, loader seconds worth 0.95..1.0 host seconds -> the same path for a 150 s cap
        expected = [a.BASELINE_RETURN_S + (a.CAP_S - a.BASELINE_DEADLINE_S) * k for k in (0.95, 1.0)]
        self.assertAlmostEqual(expected[0], 173.2, delta=0.1)
        self.assertAlmostEqual(expected[1], 177.7, delta=0.1)
        self.assertLess(a.CAP_RETURN[0], expected[0])
        self.assertGreater(a.CAP_RETURN[1], expected[1])
        self.assertEqual((a.RESERVE, a.WINDOW, a.CAP_S, a.WDT_S), (RESERVE, 4096 * 1024 * 1024, 150, 83))

    def test_the_pass_rule_needs_all_four_conditions(self):
        text = md_line(0, 0x8000) + md_line(1, RESERVE) + vm_line(259144)
        good = dict(first_return=dict(dt=181.0, klass="download"))
        r = self.a.readings(text, good, "PASS", "probe-ran-to-exit")
        self.assertTrue(r["rule"]["pass"], r["rule"])
        for label, args in (("chain verdict", (text, good, "FAIL", "probe-ran-to-exit")),
                            ("probe", (text, good, "PASS", "probe-no-console")),
                            ("md1", (md_line(0, 0x8000) + vm_line(259144), good, "PASS", "probe-ran-to-exit")),
                            ("return", (text, dict(first_return=dict(dt=114.0, klass="download")), "PASS", "probe-ran-to-exit")),
                            ("return-upload", (text, dict(first_return=dict(dt=181.0, klass="upload")), "PASS", "probe-ran-to-exit")),
                            ("no usb", (text, None, "PASS", "probe-ran-to-exit"))):
            r = self.a.readings(*args)
            self.assertFalse(r["rule"]["pass"], label)
        r = self.a.readings(text, good, "PASS", "probe-ran-to-exit")
        self.assertEqual(r["vm"]["page_size"], 16384, "the page size is reported but is not part of the rule")
        r = self.a.readings(text.replace(vm_line(259144), vm_line(1048576 - 12000)), good, "PASS", "probe-ran-to-exit")
        self.assertTrue(r["rule"]["pass"])


# ------------------------------------------------------------------------------------------------------------------ Analyser
class Analyser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = load(ANALYZE_PY, "nat075_analyze_mod")

    def test_the_analyser_is_nat065s_under_the_new_image_name(self):
        self.assertEqual(self.a.IMAGE, IMAGE)
        self.assertIs(self.a.classify_root, self.a.A65.classify_root)
        self.assertEqual(self.a.A65.IMAGE, "loader-diag-xnu-md0-usb", "NAT-065's own name is restored after a call")

    def test_readings_are_taken_over_every_dump_of_the_kernel_log(self):
        """The chain hands over one text per dump; the md1 line and the page count can sit in different dumps. NAT-062's chain is stubbed: this tests the combination."""
        fake = dict(verdict="PASS", root=dict(outcome="probe-ran-to-exit"), usb=dict(first_return=dict(dt=181.0, klass="download")),
                    kernel_log=dict(texts={"1": md_line(0, 0x8000) + vm_line(259144), "2": md_line(1, RESERVE)}))
        old = self.a._ANALYZE65
        self.a._ANALYZE65 = lambda *args, **kw: dict(fake)
        try:
            out = self.a.analyze(Path("."), [], {})
        finally:
            self.a._ANALYZE65 = old
        b = out["bigwin"]
        self.assertTrue(b["md1_ok"] and b["rule"]["pass"], b)
        self.assertEqual((b["vm"]["page_size"], [d["name"] for d in b["md"]]), (16384, ["md0", "md1"]))
        fake["kernel_log"] = None
        self.a._ANALYZE65 = lambda *args, **kw: dict(fake)
        try:
            out = self.a.analyze(Path("."), [], {})
        finally:
            self.a._ANALYZE65 = old
        self.assertEqual((out["bigwin"]["md"], out["bigwin"]["rule"]["pass"]), ([], False), "no kernel log: no md reading, no pass")

    @unittest.skipUnless(NAT68_LOG.exists(), "the NAT-068 log is not present")
    def test_the_nat068_log_reads_as_the_512_mib_one_md_run(self):
        text = NAT68_LOG.read_text(errors="replace")
        self.assertEqual([d["name"] for d in self.a.read_md(text)], ["md0"])
        vm = self.a.read_vm(text)
        self.assertEqual((vm["free"], vm["wired"], vm["total"]), (110384, 20688, 131072))
        self.assertEqual(vm["bytes_if_4k"], 512 << 20)
        self.assertIsNone(vm["page_size"], "512 MiB is not the 4096 MiB window")
        r = self.a.readings(text, dict(first_return=dict(dt=87.72, klass="download")), "PASS", self.a.classify_root({"1": text})["outcome"])
        self.assertFalse(r["md1_ok"])
        self.assertFalse(r["rule"]["pass"], "the NAT-068 run is not a NAT-075 pass")

    @unittest.skipUnless((NAT68_RUN / "archive").exists(), "artifacts/nat-068/run-001 is not present")
    def test_a_boot_of_the_nat067_image_is_not_accepted_under_the_new_name(self):
        A49 = self.a.A65.A49
        events, _ = A49.read_jsonl(str(NAT68_RUN / "usb-events.jsonl"))
        report = A49.read_json(str(NAT68_RUN / "report.json")) or {}
        with redirect_stdout(io.StringIO()):
            r = self.a.analyze(NAT68_RUN / "archive", events, report)
        self.assertEqual(r["image"], IMAGE)
        self.assertNotEqual(r["verdict"], "PASS", "the NAT-068 boot has the NAT-067 image's boot id")
        self.assertFalse(r["bigwin"]["rule"]["pass"])
        self.assertEqual(self.a.A65.IMAGE, "loader-diag-xnu-md0-usb")

    @unittest.skipUnless((NAT68_RUN / "archive").exists(), "artifacts/nat-068/run-001 is not present")
    def test_the_loader_reading_of_the_nat068_archive_is_the_512_mib_window(self):
        A49 = self.a.A65.A49
        events, _ = A49.read_jsonl(str(NAT68_RUN / "usb-events.jsonl"))
        report = A49.read_json(str(NAT68_RUN / "report.json")) or {}
        old = self.a.IMAGE
        self.a.IMAGE = IMAGE67
        try:
            with redirect_stdout(io.StringIO()):
                r = self.a.analyze(NAT68_RUN / "archive", events, report)
        finally:
            self.a.IMAGE = old
        ld = r["bigwin"]["loader"]
        self.assertTrue(ld["found"])
        self.assertEqual((ld["window_base"], ld["window_size"]), (0x9de400000, 0x20000000))
        self.assertEqual((ld["clean_span"], ld["zero_bytes_final"]), (0x20000000, 0x20000000), "NAT-068 zeroed and cleaned the whole 512 MiB window")
        self.assertFalse(ld["window_ok"], "512 MiB is not the NAT-075 window")
        self.assertFalse(ld["zero_ok"])
        self.assertFalse(ld["clean_ok"])

    @unittest.skipUnless((NAT68_RUN / "archive").exists(), "artifacts/nat-068/run-001 is not present")
    def test_the_module_image_name_is_what_drives_the_analysis(self):
        """Positive control: with the module's name set to the NAT-067 image, the NAT-068 run (a boot of that image) is accepted, so the rejection above is the name."""
        A49 = self.a.A65.A49
        events, _ = A49.read_jsonl(str(NAT68_RUN / "usb-events.jsonl"))
        report = A49.read_json(str(NAT68_RUN / "report.json")) or {}
        old = self.a.IMAGE
        self.a.IMAGE = IMAGE67
        try:
            with redirect_stdout(io.StringIO()):
                r = self.a.analyze(NAT68_RUN / "archive", events, report)
        finally:
            self.a.IMAGE = old
        self.assertEqual(r["verdict"], "PASS", r.get("why"))
        self.assertEqual(r["root"]["outcome"], "probe-ran-to-exit")
        self.assertFalse(r["bigwin"]["md1_ok"])
        self.assertEqual(r["bigwin"]["return"]["cls"], "download-other-early")
        self.assertFalse(r["bigwin"]["rule"]["pass"], "a PASS chain verdict alone is not the NAT-075 rule")
        self.assertEqual(self.a.A65.IMAGE, "loader-diag-xnu-md0-usb")

    @unittest.skipUnless((NAT68_RUN / "archive").exists(), "artifacts/nat-068/run-001 is not present")
    def test_the_command_line_tool_writes_json_with_the_bigwin_reading(self):
        with tempfile.TemporaryDirectory(prefix="nat075-an-", dir=os.environ.get("TMPDIR")) as w:
            out = Path(w) / "analysis.json"
            r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(ANALYZE_PY), "--archive", str(NAT68_RUN / "archive"), "--events", str(NAT68_RUN / "usb-events.jsonl"),
                                "--report", str(NAT68_RUN / "report.json"), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-600:])
            doc = json.loads(out.read_text())
            self.assertEqual(doc["image"], IMAGE)
            self.assertIn("bigwin", doc)
            self.assertEqual(json.loads(r.stdout)["bigwin"], doc["bigwin"])


if __name__ == "__main__":
    unittest.main()
