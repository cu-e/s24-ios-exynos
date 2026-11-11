#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-065 host tests, second half: the session driver (session_nat065.py) and the verdict analyser (analyze_nat065.py) for the image
loader-diag-xnu-md0-usb. Evidence kind: host-test. Nothing here talks to a phone (see docs/procedures/nat-062/test_nat062_run.py: `adb` is the NAT-049 fake,
the "phone" behind the real NAT-041 collector is the NAT-041 DWC3 model; the archives are NOT hardware evidence).

    <capture venv>/bin/python -W ignore -I docs/procedures/nat-065/test_nat065_run.py

The driver and the chain verdict of this image are NAT-062's with the image name, the pinned hashes, the decision-file glob, the marker path and the registry
list changed. So the Flow, RealTreeGate and Verdicts layers are NOT copied: they are NAT-062's own test source (test_nat062_run.py), read at import time and
re-targeted by the explicit, count-asserted substitutions in SUBSTITUTIONS below (a changed NAT-062 test file makes this module refuse to load instead of
testing something else). NAT-062's Derivation layer is replaced by this file's own (the driver differs from session_nat062.py only by the listed lines).

  Derivation   pins = package-001 and the build records; the driver's diff against session_nat062.py; the analyser reuses NAT-062's and restores its hooks.
  RealTreeGate (derived) in the real tree the driver stops before any adb call in every mode while there is no decision file / the registry is closed.
  Flow         (derived) preflight read-only; the registry needs NAT-043..065 as listed; one launch writes RECOVERY only; the marker makes it one-shot.
  Verdicts     (derived) the chain verdicts of NAT-062's analyser under this image's name.
  Root         what this image adds: the `root` reading of the kernel's own text: every outcome, the boundaries of the exit status, the real NAT-063 panic, the stamp
               normalisation, and the whole path through analyze() on archives written by the real collector."""
import json, os, re, shutil, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
SRC62 = PROC / "nat-062" / "test_nat062_run.py"
IMAGE62 = "loader-diag-xnu-run-usb"
REQUIRED = ('"NAT-039", "NAT-046", "NAT-043", "NAT-052", "NAT-058", "NAT-059", "NAT-060", "NAT-062", "NAT-063", "NAT-064", "NAT-065"')
# (old, new, expected count in NAT-062's text after its Derivation layer is cut); applied in this order
SUBSTITUTIONS = [
    ("nat-062", "nat-065", 10), ("nat062", "nat065", 16), ("NAT062", "NAT065", 3), ("NAT-062", "NAT-065", 6), ("nat_062", "nat_065", 1),
    ("loader-diag-xnu-run-usb", "loader-diag-xnu-md0-usb", 2),
    ('("NAT-039", "NAT-046", "NAT-043", "NAT-052", "NAT-058", "NAT-059", "NAT-060", "NAT-065")', "(" + REQUIRED + ")", 2),
    ('for missing in ("NAT-060", "NAT-065", "NAT-059", "NAT-058", "NAT-052", "NAT-043"):',
     'for missing in ("NAT-065", "NAT-064", "NAT-063", "NAT-062", "NAT-060", "NAT-059", "NAT-058", "NAT-052", "NAT-043"):', 1),
    ("test_the_registry_needs_nat_060_and_nat_065_done_too_and_the_native_decision_to_cite_this_file",
     "test_the_registry_needs_nat_043_to_065_done_and_the_native_decision_to_cite_this_file", 1),
]


def derive():
    text = SRC62.read_text()
    m1 = re.search(r"^# -+ Derivation\n", text, re.M)
    m2 = re.search(r"^# -+ RealTreeGate\n", text, re.M)
    if not (m1 and m2 and m1.start() < m2.start()):
        raise ImportError("the Derivation/RealTreeGate section markers of test_nat062_run.py moved")
    text = text[:m1.start()] + text[m2.start():]
    for old, new, count in SUBSTITUTIONS:
        if text.count(old) != count:
            raise ImportError("test_nat062_run.py changed: %r occurs %d times, expected %d" % (old, text.count(old), count))
        text = text.replace(old, new)
    for left in ("nat-062", "nat062", "NAT062", "run-usb"):
        if left in text:
            raise ImportError("%r is left in the derived test text" % left)
    if text.count("NAT-062") != 3:          # only the task id NAT-062 in the two registry tuples and the loop of missing tasks, put there by SUBSTITUTIONS
        raise ImportError("NAT-062 occurs %d times in the derived test text, expected 3 (registry lists)" % text.count("NAT-062"))
    ns = {"__name__": "nat065_run_derived", "__file__": str(HERE / "test_nat065_run.py"), "__builtins__": __builtins__}
    exec(compile(text, "<test_nat062_run.py re-targeted to NAT-065>", "exec"), ns)
    return ns


NS = derive()
for _k, _v in list(NS.items()):
    if isinstance(_v, type) and issubclass(_v, unittest.TestCase) and _v.__module__ == NS["__name__"]:
        _v.__module__ = __name__            # one module for every class: unittest runs a module's tearDownModule whenever it switches module (it would run it mid-way)
        globals()[_k] = _v
tearDownModule = NS["tearDownModule"]
IMAGE, PACKAGE, BUILD, BUILD2, STOCK_SHA = NS["IMAGE"], NS["PACKAGE"], NS["BUILD"], NS["BUILD2"], NS["STOCK_SHA"]
DRIVER, ANALYZE, load, scratch, pinned, T49 = NS["DRIVER"], NS["ANALYZE"], NS["load"], NS["scratch"], NS["pinned"], NS["T49"]
diff_lines, sha256 = NS["diff_lines"], NS["sha256"]
source_pin = NS["source_pin"]
assert IMAGE == "loader-diag-xnu-md0-usb"
assert DRIVER.name == "session_nat065.py" and ANALYZE.name == "analyze_nat065.py", (DRIVER, ANALYZE)


# ------------------------------------------------------------------------------------------------------------------ Derivation
@unittest.skipUnless((PACKAGE / "package.json").exists(), "NAT-065 package-001 is not present")
class Derivation(unittest.TestCase):
    @source_pin
    def test_pinned_hashes_are_those_of_package_001_and_the_build_records_and_the_second_build(self):
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        p = pkg["images"][IMAGE]
        self.assertEqual(sorted(pkg["images"]), [IMAGE])
        self.assertTrue(pkg["flashed"] is False and pkg["kind"] == "host-test" and pkg["device_used"] is False)
        self.assertEqual(pkg["stock_sha256"], STOCK_SHA)
        self.assertRegex(src, r"(?m)^PACKAGE=ROOT/'artifacts/nat-065/package-001'")
        self.assertRegex(src, r"(?m)^STOCK_SHA='%s'" % STOCK_SHA)
        for value in (p["recovery_sha256"], p["payload_sha256"]):
            self.assertEqual(src.count(value), 1, value)
        self.assertIn("CANARY_LEN=%d" % p["payload_bytes"], src)
        self.assertEqual(p["payload_offset"], 2048)
        self.assertNotEqual(p["payload_sha256"], p["loader_image_sha256"], "the payload, not the loader-only Image, is pinned")
        self.assertNotIn(p["loader_image_sha256"], src)
        rec = PACKAGE / IMAGE / "recovery.img"
        if rec.exists():
            self.assertEqual(sha256(rec), p["recovery_sha256"])
        for b in (BUILD, BUILD2):
            if (b / "build.json").exists():
                build = json.loads((b / "build.json").read_text())
                self.assertEqual(build["image_payloads"][IMAGE]["sha256"], p["payload_sha256"], b.name)
                self.assertEqual(build["image_payloads"][IMAGE]["bytes"], p["payload_bytes"])
                self.assertEqual(build["images"][IMAGE]["sha256"], p["loader_image_sha256"], "%s reproduces the same loader Image" % b.name)
        m = load(DRIVER, "nat065_driver_pins")
        self.assertEqual(sorted(m.IMAGES), [IMAGE])
        self.assertEqual((m.IMAGES[IMAGE]["NEW_SHA"], m.IMAGES[IMAGE]["CANARY_SHA"], m.IMAGES[IMAGE]["CANARY_LEN"]),
                         (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))
        self.assertEqual(m.STOCK_SHA, STOCK_SHA)
        self.assertEqual(m.PACKAGE.relative_to(m.ROOT), PACKAGE.relative_to(ROOT))
        for other, label in (("nat-062/session_nat062.py", "NAT-062"), ("nat-059/session_nat059.py", "NAT-059")):
            d = load(PROC / other, "nat065_driver_other_%s" % label)
            for img, rec_ in d.IMAGES.items():
                self.assertNotEqual(p["recovery_sha256"], rec_["NEW_SHA"], "this is not %s's image %s" % (label, img))
                self.assertNotEqual(p["payload_sha256"], rec_["CANARY_SHA"])

    @source_pin
    def test_the_driver_differs_from_the_nat062_driver_only_where_the_task_says(self):
        removed, added = diff_lines(PROC / "nat-062/session_nat062.py", DRIVER)       # code_lines leaves out the docstring
        old = load(PROC / "nat-062/session_nat062.py", "nat065_driver62_for_diff").IMAGES[IMAGE62]
        self.assertEqual(removed, [
            "'loader-diag-xnu-run-usb':dict(",
            "NEW_SHA='%s'," % old["NEW_SHA"],
            "CANARY_SHA='%s',  # Image.payload (loader + XNU payload + ADT)" % old["CANARY_SHA"],
            "CANARY_LEN=%d)," % old["CANARY_LEN"],
            "PACKAGE=ROOT/'artifacts/nat-062/package-001'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062')   # NAT-043/058/060: the log channel and the NAT-052/059 images ran on hardware; NAT-062: this image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat062-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-062/native-attempt-%s-used.json'%a.image)"])
        p = pinned()
        self.assertEqual(added, [
            "'loader-diag-xnu-md0-usb':dict(",
            "NEW_SHA='%s'," % p["recovery_sha256"],
            "CANARY_SHA='%s',  # Image.payload (loader + XNU payload + ADT)" % p["payload_sha256"],
            "CANARY_LEN=%d)," % p["payload_bytes"],
            "PACKAGE=ROOT/'artifacts/nat-065/package-001'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062','NAT-063','NAT-064','NAT-065')   # NAT-043/058/060/063: the log channel and the NAT-052/059/062 images ran on hardware; NAT-064: the ramdisk review; NAT-065: this image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat065-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-065/native-attempt-%s-used.json'%a.image)"])

    def test_the_analyser_reuses_nat062s_and_adds_only_the_root_reading(self):
        an = load(ANALYZE, "nat065_analyze_list")
        a62 = load(PROC / "nat-062/analyze_nat062.py", "nat065_analyze62")
        self.assertEqual(an.STOP_LIST, a62.STOP_LIST)
        self.assertEqual((len(an.STOP_LIST), an.STOP_LIST[-1]), (27, 21))
        self.assertEqual(an.IMAGE, IMAGE)
        self.assertEqual(a62.IMAGE, IMAGE62, "importing the NAT-065 analyser leaves NAT-062's module as it was")
        self.assertEqual(an.A62.analyze.__code__.co_filename, a62.analyze.__code__.co_filename)
        self.assertIs(an.write_log, an.A62.write_log)
        build = json.loads((BUILD / "build.json").read_text()) if (BUILD / "build.json").exists() else None
        if build is not None:
            self.assertEqual(an.STOP_LIST, (1, 2, 3, 4, 5) + tuple(build["stops"]))
        self.assertEqual(load(DRIVER, "nat065_driver_name").IMAGES[IMAGE]["NEW_SHA"], pinned()["recovery_sha256"])
        self.assertEqual(IMAGE, "loader-diag-xnu-md0-usb")
        # the boot id the collector must see is the FNV-1a-64 of THIS name (the analyser swaps NAT-062's name for the duration of one analysis)
        self.assertNotEqual(T49.boot_id_of(IMAGE), T49.boot_id_of(IMAGE62))

    def test_the_analyser_restores_nat062s_and_nat059s_hooks_after_each_analysis_even_when_it_fails(self):
        an = load(ANALYZE, "nat065_analyze_hooks")
        before = (an.A59.note_problems, an.D52.progress, an.A59.IMAGE, an.A62.IMAGE)
        for args in ((Path("/nonexistent"), [], {}), (Path("/nonexistent"), None, None)):
            try:
                an.analyze(*args)
            except Exception:
                pass
            self.assertEqual((an.A59.note_problems, an.D52.progress, an.A59.IMAGE, an.A62.IMAGE), before)
        self.assertEqual(an.A62.IMAGE, IMAGE62)


# ------------------------------------------------------------------------------------------------------------------ Root
REAL_LOG = ROOT / "docs/procedures/nat-063/run-001-kernel-log.txt"
DEC_NOT_OTHERS = ("0026-nat062-loader-diag-xnu-run-usb-single-run-2026-11-12.md", "0026-nat063-loader-diag-xnu-run-usb-single-run-2026-11-12.md",
                  "0027-nat066-loader-diag-xnu-md0-usb-single-run-2026-11-12.md", "0027-nat065-loader-diag-xnu-run-usb-single-run-2026-11-12.md")


def stamped(t, text):
    sec = int(t)
    return "[%9d.%06d]: %s\n" % (sec, round((t - sec) * 1024000), text)


def probe_text(status, *, pid=1, sig=0, banner=True, done=True, t_root=40.2, t_banner=41.5, sleep=1.0, console_line=True, extra=""):
    """What the kernel's log shows when the root device is mounted and the init runs: stamped lines in the format of the real log (microsecond field normalised by
    1,024,000), then the panic block."""
    out = stamped(t_root - 0.1, "!BSD") + stamped(t_root, "BSD root: md0, major 2, minor 0")
    if banner:
        out += stamped(t_banner, "SWEET userspace: init running as PID %d ***" % pid)
    if done:
        out += stamped(t_banner + sleep, "SWEET probe: done, exiting")
    out += stamped(t_banner + sleep + 0.01, "pid %d exited -- no exit reason available -- (signal %d, exit %d)" % (pid, sig, status))
    out += extra
    out += "--- panic buffer ---\npanic(cpu 0 caller 0xfffffff0079f74a0): initproc failed to start -- no exit reason available -- (signal %d, exit status %d ??? ) @bsd_init.c:1\n" % (sig, status)
    out += "Debugger message: panic\n"
    return out


class Root(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.an = load(ANALYZE, "nat065_analyze_root")

    def classify(self, text, key="2"):
        return self.an.classify_root({key: text})

    def test_the_real_nat063_panic_is_root_device_missing_and_nothing_else_is_invented(self):
        if not REAL_LOG.exists():
            self.skipTest("docs/procedures/nat-063/run-001-kernel-log.txt is not present")
        r = self.classify(REAL_LOG.read_bytes().decode("utf-8", "replace"))
        self.assertEqual(r["outcome"], "root-device-missing")
        self.assertTrue(r["panic"].startswith("IOFindBSDRoot: specified root memory device, md0, has not been configured"), r["panic"])
        self.assertTrue(r["bang_bsd"])
        self.assertEqual((r["bsd_root"], r["pid"], r["exit_status"], r["signal"], r["banner_seen"], r["done_seen"], r["init_run_s"], r["sleep_s"]),
                         (None, None, None, None, False, False, None, None))

    def test_a_probe_that_ran_to_its_exit_is_probe_ran_to_exit_with_the_pid_from_the_status(self):
        for pid in (1, 2, 9):
            r = self.classify(probe_text(0x50 + pid, pid=pid))
            self.assertEqual(r["outcome"], "probe-ran-to-exit", pid)
            self.assertEqual((r["pid"], r["exit_status"], r["signal"]), (pid, 0x50 + pid, 0))
            self.assertEqual(r["bsd_root"], dict(device="md0", major=2, minor=0))
            self.assertTrue(r["banner_seen"] and r["done_seen"] and r["bang_bsd"])
        r = self.classify(probe_text(81))
        self.assertAlmostEqual(r["sleep_s"], 1.0, places=5, msg="the 1 s select as the kernel's own stamps show it (field/1,024,000 per second)")
        self.assertAlmostEqual(r["init_run_s"], (41.5 + 1.0 + 0.01) - 40.2, places=5)

    def test_the_stamp_is_normalised_by_1_024_000_not_read_as_a_decimal_fraction(self):
        # the kernel's microsecond field runs to 1,024,000 per real second (NAT-064): a 1 s select moves the field by 1,024,000 = one whole second
        text = ("[   40.512000]: BSD root: md0, major 2, minor 0\n[   40.600000]: SWEET userspace: init running as PID 1 ***\n"
                "[   41.600000]: SWEET probe: done, exiting\n[   41.1000000]: pid 1 exited -- no exit reason available -- (signal 0, exit 81)\n"
                "panic(cpu 0 caller 0xfffffff0079f74a0): initproc failed to start -- no exit reason available -- (signal 0, exit status 81 x)\n")
        r = self.classify(text)
        self.assertAlmostEqual(r["sleep_s"], 1.0, places=6)
        self.assertAlmostEqual(r["init_run_s"], 41 + 1000000 / 1024000 - 40.5, places=5)      # a 7-digit field is read as 1,000,000/1,024,000, not as 0.1000000
        self.assertEqual(self.an.kernel_seconds(41, 512000), 41.5)
        self.assertEqual(self.an.kernel_seconds(0, 1024000), 1.0)
        self.assertEqual(self.an.kernel_seconds("12", "256000"), 12.25)
        # stamps that go backwards give no duration instead of a negative one
        r = self.classify(text.replace("[   41.600000]", "[   40.100000]"))
        self.assertIsNone(r["sleep_s"])
        r = self.classify(text.replace("[   41.1000000]", "[   40.100000]"))
        self.assertIsNone(r["init_run_s"])
        self.assertAlmostEqual(r["sleep_s"], 1.0, places=6)

    def test_the_other_outcomes_each_have_their_own_name_and_numbers(self):
        r = self.classify(probe_text(96, banner=False, done=False))
        self.assertEqual((r["outcome"], r["exit_status"], r["pid"], r["banner_seen"]), ("probe-no-console", 96, None, False))
        for status in (0, 1, 3, 80, 90, 95, 97, 255):
            r = self.classify(probe_text(status))
            self.assertEqual((r["outcome"], r["exit_status"]), ("init-exited-other", status), status)
        for status in (0x51, 0x59):
            self.assertEqual(self.classify(probe_text(status))["outcome"], "probe-ran-to-exit", status)
        for sig in (6, 9, 11):
            r = self.classify(probe_text(0, sig=sig))
            self.assertEqual((r["outcome"], r["signal"], r["exit_status"]), ("init-killed", sig, 0), sig)
        r = self.classify(probe_text(81, sig=11))
        self.assertEqual(r["outcome"], "init-killed", "a signal wins over the status")

    def test_another_panic_and_no_panic_text_are_reported_as_such(self):
        text = stamped(40.0, "!BSD") + "panic(cpu 0 caller 0xfffffff007123456): Kernel data abort. at pc 0xfffffff00712 ... @trap.c:1\n"
        r = self.classify(text)
        self.assertEqual(r["outcome"], "other-panic")
        self.assertTrue(r["panic"].startswith("Kernel data abort"))
        for texts in ({}, {"1": ""}, {"1": stamped(10.0, "arm_init: done") * 3}, {"1": probe_text(81).split("--- panic buffer ---")[0]}):
            r = self.an.classify_root(texts)
            self.assertEqual((r["outcome"], r["panic"]), ("no-panic-text", None), texts)
        r = self.an.classify_root({})
        self.assertEqual((r["text_bytes"], r["bsd_root"], r["banner_seen"], r["done_seen"], r["bang_bsd"]), (0, None, False, False, False))

    def test_the_text_of_all_dumps_is_read_in_key_order_and_a_truncated_dump_still_counts(self):
        r = self.an.classify_root({"1": stamped(30.0, "arm_init: done"), "2-truncated": probe_text(81)})
        self.assertEqual(r["outcome"], "probe-ran-to-exit")
        r = self.an.classify_root({"2": probe_text(81), "1": "no panic here\n"})
        self.assertEqual(r["outcome"], "probe-ran-to-exit")
        self.assertGreater(r["text_bytes"], len(probe_text(81)))

    def test_a_status_text_in_the_log_that_is_not_the_panic_does_not_decide_the_outcome(self):
        """The printf line of the init's exit and the panic line say the same thing; only the panic decides (the printf could be a user program's output)."""
        text = stamped(40.0, "pid 1 exited -- no exit reason available -- (signal 0, exit 81)")
        r = self.classify(text)
        self.assertEqual(r["outcome"], "no-panic-text")
        r = self.classify(stamped(40.0, "SWEET probe: done, exiting") + stamped(40.0, "initproc failed to start -- no exit reason available -- (signal 0, exit status 81 x)"))
        self.assertEqual(r["outcome"], "no-panic-text", "the panic must be a `panic(cpu N caller 0x...)` line")
        r = self.classify(stamped(40.0, "saw panic(cpu 0 caller 0xfffffff0079f74a0): initproc failed to start -- no exit reason available -- (signal 0, exit status 81 x)"))
        self.assertEqual(r["outcome"], "no-panic-text", "a panic( inside another line is not a panic")
        r = self.classify(probe_text(81).replace("initproc failed to start", "initproc exited"))
        self.assertEqual((r["outcome"], r["exit_status"]), ("probe-ran-to-exit", 81), "both spellings of the init's end are read")

    def test_decision_files_of_other_images_and_tasks_do_not_open_this_gate(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            for n in DEC_NOT_OTHERS:
                (d / n).write_text("x")
            self.assertEqual(sorted(d.glob("*-nat065-%s-single-run-*.md" % IMAGE)), [])
            (d / ("0027-nat065-%s-single-run-2026-11-12.md" % IMAGE)).write_text("x")
            self.assertEqual(len(sorted(d.glob("*-nat065-%s-single-run-*.md" % IMAGE))), 1)
        src = DRIVER.read_text()
        self.assertIn("*-nat065-%s-single-run-*.md", src)
        self.assertNotIn("nat062-%s", src)


class RootThroughTheAnalyser(unittest.TestCase):
    """analyze() on archives written by the real NAT-041 collector from the NAT-041 DWC3 model, with the dump text replaced by text that carries the root-device
    story: the chain verdict stays NAT-062's (a PASS of the chain is a delivered log), and `root` reads the delivered text."""

    cache = {}

    @classmethod
    def setUpClass(cls):
        T49.t41()
        cls.an = load(ANALYZE, "nat065_analyze_through")
        cls.tmp = scratch("root-")
        cls.make_archive, cls.usb_log, cls.report, cls.kernel_log = (staticmethod(NS[k]) for k in ("make_archive", "usb_log", "report", "kernel_log"))
        cls.saved = (NS["LOG1"], NS["LOG2"])

    @classmethod
    def tearDownClass(cls):
        NS["LOG1"], NS["LOG2"] = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls.cache.clear()

    def archive(self, key, log2, **kw):
        if key not in self.cache:
            NS["LOG2"] = log2
            try:
                r = NS["make_archive"](self, **kw)
            finally:
                NS["LOG2"] = self.saved[1]
            dest = self.tmp / ("cache-%s" % key)
            shutil.copytree(r.out, dest)
            self.cache[key] = dest
        dst = Path(tempfile.mkdtemp(dir=self.tmp)) / "archive"
        shutil.copytree(self.cache[key], dst)
        return dst

    def judge(self, key, log2, **kw):
        return self.an.analyze(self.archive(key, log2, **kw), self.usb_log(), self.report())

    def log2(self, tail_text):
        return self.kernel_log(60000, 2) + tail_text.encode()

    def test_a_probe_that_ran_is_a_pass_of_the_chain_and_probe_ran_to_exit(self):
        out = self.judge("probe", self.log2(probe_text(81)))
        self.assertEqual(out["verdict"], "PASS", (out.get("why"), out["reasons"]))
        self.assertEqual(out["image"], IMAGE)
        self.assertEqual(self.an.A62.IMAGE, IMAGE62, "the swap of NAT-062's image name is undone")
        r = out["root"]
        self.assertEqual((r["outcome"], r["pid"], r["exit_status"], r["bsd_root"]), ("probe-ran-to-exit", 1, 81, dict(device="md0", major=2, minor=0)))
        self.assertTrue(r["banner_seen"] and r["done_seen"])
        self.assertAlmostEqual(r["sleep_s"], 1.0, places=5)

    def test_the_old_panic_is_a_pass_of_the_chain_and_root_device_missing(self):
        real = REAL_LOG.read_bytes().decode("utf-8", "replace").split("\n", 4)[-1] if REAL_LOG.exists() else None
        if real is None:
            self.skipTest("the real NAT-063 log is not present")
        out = self.judge("old-panic", self.log2(real[-4000:]))
        self.assertEqual(out["verdict"], "PASS", (out.get("why"), out["reasons"]))
        self.assertEqual(out["root"]["outcome"], "root-device-missing")

    def test_no_panic_text_in_a_complete_chain_is_reported_not_guessed(self):
        out = self.judge("quiet", self.log2(stamped(50.0, "nothing to see")))
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(out["root"]["outcome"], "no-panic-text")

    def test_a_run_without_a_second_dump_still_carries_a_root_reading_of_the_first(self):
        out = self.judge("no-return", self.log2(""), ret=False)
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertEqual(out["root"]["outcome"], "no-panic-text")
        self.assertEqual(sorted(out["kernel_log"]["texts"]), ["1"])

    def test_the_log_file_keeps_the_panic_text_and_the_root_reading_does_not_change_it(self):
        out = self.judge("probe", self.log2(probe_text(81)))
        p = self.tmp / "kernel-log.txt"
        self.an.write_log(out, p)
        text = p.read_bytes().decode("utf-8")
        self.assertIn("initproc failed to start -- no exit reason available -- (signal 0, exit status 81", text)
        self.assertIn("SWEET probe: done, exiting", text)

    def test_a_synthetic_archive_never_passes_and_the_root_reading_is_still_there(self):
        d = self.archive("synthetic", self.log2(probe_text(81)), live=False)
        r = self.an.analyze(d, self.usb_log(), self.report())
        self.assertEqual(r["verdict"], "undetermined")
        self.assertIn("root", r)
        self.assertEqual(self.an.analyze(d, self.usb_log(), self.report(), allow_synthetic=True)["verdict"], "simulated-PASS")


if __name__ == "__main__":
    unittest.main()
