#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-062 host tests, second half: the session driver (session_nat062.py) and the verdict analyser (analyze_nat062.py) for the image
loader-diag-xnu-run-usb. Evidence kind: host-test. Nothing here talks to a phone: `adb` is the NAT-049 fake that models the RECOVERY block
in a file, the collector launcher and the udev check are stand-ins, and the "phone" behind the real NAT-041 collector is the NAT-041 DWC3 model
whose ring is seeded with the text formats of the image (decode52's contract and glue62_impl.h's `KL` records). The archives are NOT hardware evidence.

    <capture venv>/bin/python -W ignore -I docs/procedures/nat-062/test_nat062_run.py

Layers:
  Derivation   the driver differs from NAT-059's only by the lines listed here; the analyser reuses NAT-059's modules; the pinned hashes are those of package-001
               and the build records (and of the second, identical build).
  RealTreeGate in the real tree the driver stops before any adb call in every mode while there is no agent-written decision file.
  Flow         the driver in a scratch tree: preflight is read-only; the registry needs NAT-060 and NAT-062 done as well; a launch writes RECOVERY
               only, reads it back, starts the watcher and the collector before the single reboot; the marker makes it one-shot.
  Verdicts     the analyser on archives written by the real collector: PASS needs the 27 notes, the log dump at the last stop, the kernel's own return
               note, the second dump and the hold; every way the run can end short has its own verdict and names the step.
NAT-057 and NAT-059 hold the tests of everything this file inherits (the driver's gates and flows, the NAT-049 integrity, T0, boot-id and provenance rules,
the TTBR0 rules of the notes)."""
import difflib, hashlib, importlib.util, json, os, re, shutil, signal, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
DRIVER = Path(os.environ.get("NAT062_DRIVER") or HERE / "session_nat062.py")
ANALYZE = Path(os.environ.get("NAT062_ANALYZE") or HERE / "analyze_nat062.py")
IMAGE = "loader-diag-xnu-run-usb"
PACKAGE = ROOT / "artifacts/nat-062/package-001"
BUILD = ROOT / "artifacts/nat-062/build-001"
BUILD2 = ROOT / "artifacts/nat-062/build-002"
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
STOCK_SHA = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
SCRATCH = ROOT / "artifacts/nat-062/tmp"
MASK_FINAL, MASK_BAD_TTBR0, MASK_BAD_STATE = 1 << 13, 1 << 12, 1 << 14
CP5_TTBR0, TTEP = 0x9e15ae000, 0x9e15a8000        # the value measured at checkpoint 5 (NAT-058) and an _invalid_ttep-like table base
source_pin = unittest.skipIf(os.environ.get("NAT062_BEHAVIOUR_ONLY") == "1", "source-text pin (skipped in the behavioural mutation pass)")


def scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T57 = load(PROC / "nat-057/test_nat057.py", "nat062_test_nat057")        # fixtures only (and, through it, NAT-049's): never its test classes
T49 = T57.T49
sha256, code_lines = T49.sha256, T49.code_lines
BASE, T0, FIRST, usb_log, report = T49.BASE, T49.T0, T49.FIRST, T49.usb_log, T49.report
tearDownModule = T49.tearDownModule


def pinned():
    return json.loads((PACKAGE / "package.json").read_text())["images"][IMAGE]


def diff_lines(a, b):
    ndiff = list(difflib.ndiff(code_lines(a), code_lines(b)))
    return [l[2:] for l in ndiff if l.startswith("- ")], [l[2:] for l in ndiff if l.startswith("+ ")]


# ------------------------------------------------------------------------------------------------------------------ Derivation
@unittest.skipUnless((PACKAGE / "package.json").exists(), "NAT-062 package-001 is not present")
class Derivation(unittest.TestCase):
    @source_pin
    def test_pinned_hashes_are_those_of_package_001_and_the_build_records_and_the_second_build(self):
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        p = pkg["images"][IMAGE]
        self.assertEqual(sorted(pkg["images"]), [IMAGE])
        self.assertTrue(pkg["flashed"] is False and pkg["kind"] == "host-test" and pkg["device_used"] is False)
        self.assertEqual(pkg["stock_sha256"], STOCK_SHA)
        self.assertRegex(src, r"(?m)^PACKAGE=ROOT/'artifacts/nat-062/package-001'")
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
        m = load(DRIVER, "nat062_driver_pins")
        self.assertEqual(sorted(m.IMAGES), [IMAGE])
        self.assertEqual((m.IMAGES[IMAGE]["NEW_SHA"], m.IMAGES[IMAGE]["CANARY_SHA"], m.IMAGES[IMAGE]["CANARY_LEN"]),
                         (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))
        self.assertEqual(m.STOCK_SHA, STOCK_SHA)
        self.assertEqual(m.PACKAGE.relative_to(m.ROOT), PACKAGE.relative_to(ROOT))
        self.assertNotEqual(p["recovery_sha256"], load(PROC / "nat-059/session_nat059.py", "nat062_driver59_pins").IMAGES["loader-diag-xnu-ckpt4-usb"]["NEW_SHA"],
                            "this is not NAT-059's image")

    @source_pin
    def test_the_driver_differs_from_the_nat059_driver_only_where_the_task_says(self):
        removed, added = diff_lines(PROC / "nat-059/session_nat059.py", DRIVER)       # code_lines leaves out the docstring
        self.assertEqual(removed, [
            "'loader-diag-xnu-ckpt4-usb':dict(",
            "NEW_SHA='60147f1f6190c688b89ea63ac1f56816e977db692eb3864bf2aaa404ea868dd1',",
            "CANARY_SHA='3bb6e5d14368ef3627288f44aeff9c00c1e510915395db5988de600402b0af20',  # Image.payload (loader + XNU payload + ADT)",
            "CANARY_LEN=21857888),",
            "PACKAGE=ROOT/'artifacts/nat-059/package-002'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059')   # NAT-043/NAT-058: the log channel and the NAT-052 image ran on hardware; NAT-059: this image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat059-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-059/native-attempt-%s-used.json'%a.image)"])
        p = pinned()
        self.assertEqual(added, [
            "'loader-diag-xnu-run-usb':dict(",
            "NEW_SHA='%s'," % p["recovery_sha256"],
            "CANARY_SHA='%s',  # Image.payload (loader + XNU payload + ADT)" % p["payload_sha256"],
            "CANARY_LEN=%d)," % p["payload_bytes"],
            "PACKAGE=ROOT/'artifacts/nat-062/package-001'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062')   # NAT-043/058/060: the log channel and the NAT-052/059 images ran on hardware; NAT-062: this image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat062-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-062/native-attempt-%s-used.json'%a.image)"])

    @source_pin
    def test_the_analyser_reuses_the_nat059_one_and_replaces_only_the_rule_for_what_follows_the_stop_notes(self):
        an = load(ANALYZE, "nat062_analyze_list")
        a59 = load(PROC / "nat-059/analyze_nat059.py", "nat062_analyze59")
        self.assertEqual(an.STOP_LIST, a59.STOP_LIST)
        self.assertEqual((len(an.STOP_LIST), an.STOP_LIST[-1]), (27, 21))
        self.assertEqual(an.IMAGE, IMAGE)
        self.assertEqual(a59.IMAGE, "loader-diag-xnu-ckpt4-usb", "importing the NAT-062 analyser leaves NAT-059's module as it was")
        build = json.loads((BUILD / "build.json").read_text()) if (BUILD / "build.json").exists() else None
        if build is not None:
            self.assertEqual(an.STOP_LIST, (1, 2, 3, 4, 5) + tuple(build["stops"]))
        self.assertEqual(load(DRIVER, "nat062_driver_name").IMAGES[IMAGE]["NEW_SHA"], pinned()["recovery_sha256"])

    def test_the_analyser_restores_nat059s_hooks_after_each_analysis(self):
        an = load(ANALYZE, "nat062_analyze_hooks")
        before = (an.A59.note_problems, an.D52.progress, an.A59.IMAGE)
        try:
            an.analyze(Path("/nonexistent"), [], {})
        except Exception:
            pass
        self.assertEqual((an.A59.note_problems, an.D52.progress, an.A59.IMAGE), before)


# ------------------------------------------------------------------------------------------------------------------ RealTreeGate
class RealTreeGate(unittest.TestCase):
    def decisions(self):
        return sorted((ROOT / "docs/decisions").glob("*-nat062-%s-single-run-*.md" % IMAGE))

    def run_driver(self, *mode):
        with tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.exists() else None) as t:
            t = Path(t)
            (t / "bin").mkdir()
            fake = t / "bin/adb"
            fake.write_text("#!/bin/sh\necho \"$@\" >> %s\nexit 1\n" % (t / "adb-calls"))
            fake.chmod(0o755)
            env = {"PATH": f"{t / 'bin'}:/usr/bin:/bin", "HOME": str(t)}
            r = subprocess.run([sys.executable, "-I", str(DRIVER), "--image", IMAGE, "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def test_the_real_tree_stops_before_any_adb_call(self):
        """No decision file: every mode stops at the decision gate. A decision file and a closed registry: --execute stops at the registry.
        An open registry: the launch is no longer gated by this test and it skips."""
        marker = ROOT / ("artifacts/nat-062/native-attempt-%s-used.json" % IMAGE)
        before = marker.exists()
        found = self.decisions()
        if not found:
            for mode in ((), ("--execute",), ("--restore",)):
                r, calls, rep = self.run_driver(*mode)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(calls, "", mode)
                self.assertEqual(rep["outcome"], "stopped")
                self.assertIn("decision file for %s is missing or ambiguous (0 found)" % IMAGE, rep["error"])
                self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))
                for key in ("watcher", "collector", "host_access", "collector_selftest", "registry_blocker", "watcher_selftest"):
                    self.assertNotIn(key, rep, (mode, key))
        else:
            self.assertEqual(len(found), 1)
            blocker = load(DRIVER, "nat062_driver_real_registry").registry_blocker(found[0])
            if blocker is None:
                self.skipTest("the real registry is open for %s: the launch is no longer gated by the test" % found[0].name)
            r, calls, rep = self.run_driver("--execute")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(calls, "")
            self.assertEqual((rep["outcome"], rep["registry_blocker"], rep["error"]), ("stopped", blocker, blocker))
            self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))
        self.assertEqual(marker.exists(), before, "a refused run must not leave the one-shot marker")

    def test_the_decision_files_of_other_tasks_and_images_do_not_open_this_gate(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.exists() else None) as t:
            d = Path(t)
            for n in ("0024-nat052-loader-diag-xnu-ckpt3-usb-single-run-2026-11-11.md", "0022-nat043-%s-single-run-2026-11-12.md" % IMAGE,
                      "0025-nat059-loader-diag-xnu-ckpt4-usb-single-run-2026-11-11.md", "0026-nat062-loader-diag-xnu-ckpt4-usb-single-run-2026-11-12.md",
                      "0026-nat059-%s-single-run-2026-11-12.md" % IMAGE):
                (d / n).write_text("x")
            self.assertEqual(sorted(d.glob("*-nat062-%s-single-run-*.md" % IMAGE)), [])
            (d / ("0026-nat062-%s-single-run-2026-11-12.md" % IMAGE)).write_text("x")
            self.assertEqual(len(sorted(d.glob("*-nat062-%s-single-run-*.md" % IMAGE))), 1)


# ------------------------------------------------------------------------------------------------------------------ Flow
@unittest.skipUnless((PACKAGE / "package.json").exists() and STOCK.exists(), "NAT-062 package-001 or the stock RECOVERY backup is not present")
class Flow(unittest.TestCase):
    """The driver in a scratch tree: fake decision file and registry, the NAT-049 fake adb, the real NAT-048 watcher on a fake sysfs through its
    one-file wrapper, stand-ins for the collector launcher and the udev check (NAT-049 tests their real behaviour)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = scratch("flow-")
        drv = t / "docs/procedures/nat-062"
        drv.mkdir(parents=True)
        shutil.copy(DRIVER, drv / "session_nat062.py")
        (t / "docs/procedures/nat-049").mkdir(parents=True)
        (t / "docs/procedures/nat-049/collector_launch.py").write_text(T49.STUB_COLLECTOR)
        (t / "docs/procedures/nat-049/host_access.py").write_text(T49.STUB_ACCESS)
        (t / "docs/procedures/nat-048").mkdir(parents=True)
        (t / "docs/procedures/nat-048/usb_watch.py").write_text(T49.WRAPPER)
        (t / "docs/decisions").mkdir(parents=True)
        (t / "state").mkdir()
        for rel in ("package.json", "%s/recovery.img" % IMAGE):
            dst = t / "artifacts/nat-062/package-001" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(PACKAGE / rel, dst)
        (t / "devices/recovery/backups/2026-11-10").mkdir(parents=True)
        os.symlink(STOCK, t / "devices/recovery/backups/2026-11-10/recovery.img")
        (t / "bin").mkdir()
        adb = t / "bin/adb"
        adb.write_text(T49.FAKE_ADB.replace("{python}", sys.executable))
        adb.chmod(0o755)
        cls.venv = t / "artifacts/recovery-rescue-20261110-01/venv/bin/python"
        cls.venv.parent.mkdir(parents=True)
        cls.driver = drv / "session_nat062.py"
        cls.pids = []

    @classmethod
    def tearDownClass(cls):
        for pid in cls.pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="dev-", dir=self.tmp))
        self.sysfs = self.base / "sys"
        self.sysfs.mkdir()
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        for p in (self.tmp / "docs/decisions").glob("*"):
            p.unlink()
        for p in (self.tmp / "artifacts/nat-062").glob("native-attempt-*"):
            p.unlink()
        if self.venv.is_symlink() or self.venv.exists():
            self.venv.unlink()
        os.symlink(sys.executable, self.venv)
        self.n = 0
        self.decision = "0099-nat062-%s-single-run-2026-11-12.md" % IMAGE
        p = pinned()
        (self.tmp / "docs/decisions" / self.decision).write_text("scratch-tree decision for %s\nRECOVERY SHA-256 %s\nImage.payload SHA-256 %s\nunder decision 0019\n" % (
            IMAGE, p["recovery_sha256"], p["payload_sha256"]))
        self.registry()

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def registry(self, done=("NAT-039", "NAT-046", "NAT-043", "NAT-052", "NAT-058", "NAT-059", "NAT-060", "NAT-062"), value=True):
        project = dict(permissions=dict(native=value, android=True),
                       permission_decisions=[dict(scope="native", value=value, decision="docs/decisions/" + self.decision, owner="agent", at="2026-11-12T00:00:00+00:00")])
        (self.tmp / "state/lab.json").write_text(json.dumps(dict(project=project, tasks=[dict(id=t, status="done") for t in done])))

    def run_driver(self, *mode):
        self.n += 1
        out = self.base / ("out%d" % self.n)
        env = {"PATH": f"{self.tmp / 'bin'}:/usr/bin:/bin", "HOME": str(self.tmp), "FAKE_DEVICE_DIR": str(self.base), "FAKE_SYSFS": str(self.sysfs),
               "FAKE_WATCH_LOG": str(out / "usb-events.jsonl"), "FAKE_HEARTBEAT": str(out / "collector-heartbeat.jsonl"), "REAL_WATCHER": str(T57.NAT048_WATCH)}
        r = subprocess.run([sys.executable, str(self.driver), "--image", IMAGE, "--out", str(out), *mode], capture_output=True, text=True, env=env, timeout=300)
        rep = json.loads((out / "report.json").read_text()) if (out / "report.json").exists() else {}
        for key in ("watcher", "collector"):
            if key in rep:
                self.pids.append(rep[key]["pid"])
        return r, rep, out

    def lines(self, name):
        p = self.base / name
        return p.read_text().splitlines() if p.exists() else []

    def marker(self):
        return self.tmp / ("artifacts/nat-062/native-attempt-%s-used.json" % IMAGE)

    def test_preflight_is_read_only(self):
        r, rep, out = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((rep["outcome"], rep["registry_blocker"]), ("ready-read-only", None))
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual([c for c in self.lines("adb-calls") if c.startswith("reboot")], [])
        self.assertFalse(self.marker().exists())
        self.assertEqual(sha256(self.base / "recovery.bin"), STOCK_SHA)

    def test_the_registry_needs_nat_060_and_nat_062_done_too_and_the_native_decision_to_cite_this_file(self):
        base = ("NAT-039", "NAT-046", "NAT-043", "NAT-052", "NAT-058", "NAT-059", "NAT-060", "NAT-062")
        for missing in ("NAT-060", "NAT-062", "NAT-059", "NAT-058", "NAT-052", "NAT-043"):
            with self.subTest(missing=missing):
                self.setUp()
                self.registry(done=tuple(t for t in base if t != missing))
                r, rep, out = self.run_driver("--execute")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(missing, rep["error"])
                self.assertFalse((self.base / "writes").exists())
                self.assertEqual(self.lines("adb-calls"), [])
                self.assertFalse(self.marker().exists())
        self.setUp()
        self.registry(value=False)
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.lines("adb-calls"), [])

    def test_a_launch_writes_recovery_only_reads_it_back_starts_watcher_and_collector_and_reboots_once(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "native-attempt-started")
        self.assertEqual(sha256(self.base / "recovery.bin"), pinned()["recovery_sha256"])
        self.assertEqual(rep["readback_sha256"], pinned()["recovery_sha256"])
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296"])
        self.assertEqual([c for c in self.lines("adb-calls") if c.startswith("reboot")], ["reboot recovery"])
        order = self.lines("order")
        self.assertLess(order.index("adb write"), order.index("watcher-start"))
        self.assertLess(order.index("watcher-start"), order.index("collector-start"))
        self.assertLess(order.index("collector-start"), order.index("adb reboot"))
        self.assertEqual(order.count("adb reboot"), 1)
        self.assertEqual(rep["decision_file"], self.decision)
        self.assertEqual(json.loads(self.marker().read_text())["image"], IMAGE)

    def test_the_marker_makes_the_run_one_shot(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        writes, reboots = (self.base / "writes").read_text().split(), [c for c in self.lines("adb-calls") if c.startswith("reboot")]
        shutil.copyfile(STOCK, self.base / "recovery.bin")                       # as if the restore had run
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual((self.base / "writes").read_text().split(), writes, "no second write")
        self.assertEqual([c for c in self.lines("adb-calls") if c.startswith("reboot")], reboots, "no second reboot")
        self.assertFalse(rep["device_write_started"])


# ------------------------------------------------------------------------------------------------------------------ Verdicts
def kttbr0_of(n, post=TTEP):
    """What the image's notes show: 0 before the checkpoint-5 stop, the checkpoint-5 table up to checkpoint 16 (n=22), the table of arm_vm_init after."""
    return 0 if n < 5 else CP5_TTBR0 if n <= 22 else post


def kernel_log(n, seed):
    """A made-up console log of n bytes: lines of text, a backslash, a carriage return and a few bytes that are not printable (every escape the dump has)."""
    out = bytearray()
    i = 0
    while len(out) < n:
        out += ("xnu[%d]: [%9.6f] cpu0: step %d \\ path\r\n" % (seed, i * 0.017, i)).encode()
        if i % 7 == 3:
            out += bytes([0x00, 0x1b, 0x7f, 0x80, 0xff])
        i += 1
    return bytes(out[:n])


def esc(raw):
    out = []
    for c in raw:
        out.append("\\\\" if c == 0x5c else "\\n" if c == 0x0a else "\\r" if c == 0x0d else chr(c) if 0x20 <= c < 0x7f else "\\x%02x" % c)
    return "".join(out)


HEAD_MAX, TAIL_MAX = {1: 8192, 2: 8192}, {1: 8192, 2: 32768}


def kl_lines(log, why, *, head=None, tail=None, drop=None, no_end=False, end_recs=None, damage=None, x0=0x9a2b0a00):
    """The `KL` records of one dump of `log` as the image sends them (the newest text first); the keywords break one thing."""
    n = len(log)
    h = min(n, HEAD_MAX[why]) if head is None else head
    t = min(n - h, TAIL_MAX[why]) if tail is None else tail
    lines = ["KL begin why=%d len=%d head=%d tail=%d gap=%d x0=0x%x" % (why, n, h, t, n - h - t, x0)]
    recs = []
    for lo, hi in ((n - t, n), (0, h)):
        for off in range(lo, hi, 96):
            recs.append("KL %06x %s" % (off, esc(log[off:min(off + 96, hi)])))
    if drop is not None:
        del recs[drop]
    if damage is not None:
        recs[damage] = recs[damage][:10] + "\\q" + recs[damage][12:]
    lines += recs
    if not no_end:
        lines.append("KL end why=%d recs=%d bytes=%d" % (why, len(recs) if end_recs is None else end_recs, h + t))
    return lines


LOG1, LOG2 = kernel_log(20000, 1), kernel_log(70000, 2)
RETURN_NOTE = "CK n=%d arr=27 last=21 x2=0x0 x3=0x0 mask=0x203e sctlr=0x3454599d sp=0xfffffff00805fef0 kttbr0=0x9e2d7c000 vbar=0xfffffff007437000 setups=0"


def script62(m, P, *, stops=27, skip=(), edit=None, exception_at=None, final=True, hold=True, wrong=None, banner=None,
             dump1=True, refused1=False, kl1=None, ret=True, ret_n=28, kl2=None, dump2=True, hold_at=None, before_last=False, ret_dump_first=False, stray=False, two_returns=False):
    """The text the image writes: loader banner and ladder as NAT-047/NAT-057, one `CK` note per stop (27), the log dump at the last stop (`KL`), then, if the kernel
    returns by itself, the reason-0 note, the second dump and HOLD. `edit` = {n: dict(note_line keyword overrides)}; the other keywords drop or break one step."""
    m.text(banner if banner is not None else "NAT047 %s deadline_s=60 fault=0" % IMAGE)
    m.stage(0x20, "loader_main")
    for i in range(3):
        m.text("LR R %d v0=0x%x v1=0x0" % (i, 0x1000 + i))
    m.text("LAD R err=0 err_op=-1 rung=2 pd_was_on=0 nrec=3 soft=0 gsnpsid=0x5533330a")
    for i in range(6):
        m.text("LR W %d v0=0x%x v1=0x0" % (i, 0x2000 + i))
    m.text("LAD W err=0 err_op=-1 rung=5 pd_was_on=0 nrec=6 soft=0 gsnpsid=0x5533330a")
    for st in T57.LOADER_STAGES:
        m.stage(*st)
    order = list(an_stop_list())
    d1 = (["KL refused why=1 x0=0x%x x1=0x%x" % (0x1234, 0x200)] if refused1 else kl_lines(LOG1, 1, **(kl1 or {}))) if dump1 else []
    for i in range(stops):
        n = i + 1
        if n in skip:
            continue
        if before_last and n == stops:
            for l in d1:
                m.text(l)
        kw = dict(mask=MASK_FINAL | 0x3e if (final and i == stops - 1) else 0, kttbr0=kttbr0_of(n), sctlr=0x3454599c if n <= 5 else 0x3454599d,
                  sp=0x800aa080 if n <= 2 else 0xfffffff008060000 if n <= 5 else 0xfffffff00805fef0)
        if exception_at == n:
            kw.update(x2=1, x3=0, exc=(0x96000045, 0xfffffff007441234, 0xdeadbeef000))
        kw.update((edit or {}).get(n, {}))
        m.text(T57.note_line(n, i + 1, (wrong or {}).get(n, order[i]), **kw))
    if not before_last:
        for l in d1:
            m.text(l)
    if stray:
        m.text("KL end why=1 recs=0 bytes=0")
    if ret:
        d2 = kl_lines(LOG2, 2, **(kl2 or {})) if dump2 else []
        if ret_dump_first:
            for l in d2:
                m.text(l)
        for _ in range(2 if two_returns else 1):
            m.text(RETURN_NOTE % ret_n)
        if not ret_dump_first:
            for k, l in enumerate(d2):
                if hold_at is not None and k == hold_at:
                    m.text("HOLD stage=0x51 code=0x203e")
                m.text(l)
        if hold:
            m.text("HOLD stage=0x51 code=0x203e")


def an_stop_list():
    return (1, 2, 3, 4, 5, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)


def make_archive(tc, *, boot_image=None, create_t=BASE, first_t=FIRST, live=True, plug=True, ring_size=1 << 19, go_s=2.0, max_bytes=1 << 25, **kw):
    from unittest import mock
    T = T49.t41()
    clock = T49.Stamp(create_t)
    real_archive = T.L.A.Archive
    with mock.patch.object(T.L.A, "stamp", clock), \
            mock.patch.object(T.L.A, "Archive", (lambda out, ch, prov: real_archive(out, ch, "unqualified-live")) if live else real_archive):
        r = T.Rig(tc, ring_size=ring_size, boot_id=T49.boot_id_of(boot_image or IMAGE), plugged=plug)
        if plug:
            script62(r.m, T.P, **kw)
        clock.t = first_t
        r.go(go_s, max_bytes)
    return r


class Verdicts(unittest.TestCase):
    cache = {}

    @classmethod
    def setUpClass(cls):
        T49.t41()
        cls.an = load(ANALYZE, "nat062_analyze_under_test")
        cls.tmp = scratch("arch-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls.cache.clear()

    def arch(self, key, **kw):
        if key not in self.cache:
            r = make_archive(self, **kw)
            dest = self.tmp / ("cache-%s" % key)
            shutil.copytree(r.out, dest)
            self.cache[key] = dest
        dst = Path(tempfile.mkdtemp(dir=self.tmp)) / "archive"
        shutil.copytree(self.cache[key], dst)
        return dst

    def judge(self, key, **kw):
        arch_kw = kw.pop("arch", {})
        return self.an.analyze(self.arch(key, **arch_kw), usb_log(), report(), **kw)

    def reasons(self, out):
        return " | ".join(out["reasons"])

    def expected_text(self, log, why):
        n = len(log)
        head = min(n, HEAD_MAX[why])
        tail = min(n - head, TAIL_MAX[why])
        gap = n - head - tail
        return log[:head].decode("utf-8", "replace") + ("\n[... %d bytes of the log were not sent ...]\n" % gap if gap else "") + log[n - tail:].decode("utf-8", "replace")

    def test_a_complete_run_is_a_pass_naming_the_notes_both_dumps_the_return_and_the_hold(self):
        out = self.judge("full")
        self.assertEqual(out["verdict"], "PASS", (out.get("why"), out["reasons"]))
        p = out["progress"]
        self.assertEqual((p["notes"], p["last_checkpoint"], p["held"], p["reached_final"], p["gaps"]), (27, 21, True, True, []))
        self.assertEqual([s["kttbr0"] for s in p["stops"][4:22]], [hex(CP5_TTBR0)] * 18)
        self.assertEqual([s["kttbr0"] for s in p["stops"][22:]], [hex(TTEP)] * 5)
        self.assertEqual(p["hold"], {"stage": 0x51, "code": 0x203e})
        for part in ("the 27 stop notes (n=1..27, final checkpoint 21)", "the kernel's log at the last stop (20000 bytes long: 8192 + 8192 sent in 172 records, 3616 not sent)",
                     "the kernel's own return (reason-0 note n=28, x3=0x0)", "its log (70000 bytes long: 8192 + 32768 sent in 428 records, 29040 not sent), then HOLD", "no drop, nothing unread, no exception"):
            self.assertIn(part, out["why"])
        self.assertNotIn("the hold announced", out["why"], "NAT-059's sentence is about a hold at the last stop")
        kl = out["kernel_log"]
        self.assertEqual(sorted(kl["texts"]), ["1", "2"])
        self.assertEqual(kl["texts"]["1"], self.expected_text(LOG1, 1))
        self.assertEqual(kl["texts"]["2"], self.expected_text(LOG2, 2))
        self.assertEqual((kl["return_notes"], kl["hold"]), ([28], {"stage": "0x51", "code": "0x203e"}))
        self.assertEqual([(d["why"], d["status"], d["len"], d["head"], d["tail"], d["gap"], d["recs"], d["bytes"]) for d in kl["dumps"]],
                         [(1, "complete", 20000, 8192, 8192, 3616, 172, 16384), (2, "complete", 70000, 8192, 32768, 29040, 428, 40960)])

    def test_the_text_is_written_to_the_log_file_and_nothing_is_invented(self):
        out = self.judge("full")
        p = self.tmp / "kernel-log.txt"
        self.an.write_log(out, p)
        text = p.read_bytes().decode("utf-8")          # not read_text(): universal newlines would turn the kernel's \r\n into \n
        self.assertIn("===== dump 1 ", text)
        self.assertIn("===== dump 2 ", text)
        self.assertIn(self.expected_text(LOG1, 1), text)
        self.assertIn("[... 29040 bytes of the log were not sent ...]", text)
        self.assertIn("xnu[2]: [ 0.000000] cpu0: step 0 \\ path\r\n", text)
        self.assertEqual(text.count("were not sent"), 2)

    def test_a_synthetic_archive_never_passes(self):
        d = self.arch("synthetic", live=False)
        r = self.an.analyze(d, usb_log(), report())
        self.assertEqual(r["verdict"], "undetermined")
        self.assertIn("the kernel's own return (reason-0 note n=28", r["why"], "even a refused verdict names this image's chain, not NAT-059's")
        self.assertEqual(self.an.analyze(d, usb_log(), report(), allow_synthetic=True)["verdict"], "simulated-PASS")

    def test_the_old_image_boot_is_not_evidence_about_this_image(self):
        out = self.judge("old-image", arch=dict(boot_image="loader-diag-xnu-ckpt4-usb"))
        self.assertEqual(out["verdict"], "undetermined", out.get("why"))
        self.assertIn("none has the boot id of %s" % IMAGE, out["why"])

    def test_a_kernel_that_never_hands_control_back_is_partial_and_the_first_dump_is_still_delivered(self):
        # the dump at checkpoint 21 arrived, the kernel ran on and nothing more came before the deadline reset or the watchdog
        out = self.judge("no-return", arch=dict(ret=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertEqual(len(out["reasons"]), 1, out["reasons"])
        self.assertIn("NO RETURN: the kernel did not hand control back after checkpoint 21", out["reasons"][0])
        self.assertEqual(out["kernel_log"]["texts"]["1"], self.expected_text(LOG1, 1), "what the kernel had written by checkpoint 21 is delivered all the same")
        self.assertEqual(out["kernel_log"]["return_notes"], [])
        self.assertIn("the last note is n=27 (arrival 27, checkpoint 21)", out["why"])

    def test_a_missing_final_dump_a_refusal_a_cut_dump_and_a_damaged_dump_are_each_named(self):
        out = self.judge("no-dump1", arch=dict(dump1=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("0 log dump(s) with why=1 (the final stop's), expected exactly one", self.reasons(out))
        out = self.judge("refused1", arch=dict(refused1=True, ret=False))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the dump at the final stop is refused (x0=0x1234 x1=0x200: the stop's registers were not the kernel's log)", self.reasons(out))
        out = self.judge("cut1", arch=dict(kl1=dict(no_end=True), ret=False))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the dump at the final stop is truncated: the dump has no `KL end` record", self.reasons(out))
        self.assertEqual(sorted(out["kernel_log"]["texts"]), ["1-truncated"], "what arrived is kept and labelled")
        out = self.judge("drop1", arch=dict(kl1=dict(drop=40)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the dump at the final stop is damaged: the records do not cover the announced ranges", self.reasons(out))
        out = self.judge("damage1", arch=dict(kl1=dict(damage=7)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("a record at offset ", self.reasons(out))
        out = self.judge("count1", arch=dict(kl1=dict(end_recs=170)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the end record says 170 records", self.reasons(out))

    def test_a_dump_that_does_not_send_the_head_and_tail_this_image_sends_is_not_a_pass(self):
        out = self.judge("small-head", arch=dict(kl1=dict(head=4000, tail=8192)))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the dump does not send the head and tail this image sends (len 20000: expected head 8192 tail 8192, announced 4000 and 8192)", self.reasons(out))
        out = self.judge("big-tail", arch=dict(kl2=dict(tail=40000, head=8192)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("expected head 8192 tail 32768, announced 8192 and 40000", self.reasons(out))

    def test_the_return_chain_has_a_reason_for_every_missing_step(self):
        out = self.judge("no-dump2", arch=dict(dump2=False, hold=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("0 dump(s) with why=2, 0 after the return note, expected exactly one", self.reasons(out))
        self.assertIn("no HOLD record after the kernel's return", self.reasons(out))
        out = self.judge("cut2", arch=dict(kl2=dict(no_end=True), hold=False))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the dump at the kernel's return is truncated", self.reasons(out))
        self.assertEqual(sorted(out["kernel_log"]["texts"]), ["1", "2-truncated"])
        out = self.judge("nohold", arch=dict(hold=False))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertEqual(out["reasons"], ["no HOLD record after the kernel's return"])
        out = self.judge("hold-early", arch=dict(hold_at=50, hold=False))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the HOLD record arrived before the end of the return dump", self.reasons(out))
        out = self.judge("two-returns", arch=dict(two_returns=True))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("2 reason-0 notes, expected one", self.reasons(out))
        out = self.judge("dump-first", arch=dict(ret_dump_first=True))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("1 dump(s) with why=2, 0 after the return note, expected exactly one", self.reasons(out))

    def test_the_dump_must_come_after_the_note_of_the_stop_it_belongs_to_and_inside_one_begin_end(self):
        out = self.judge("dump-before-note", arch=dict(before_last=True))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the final dump arrived before the n=27 note", self.reasons(out))
        out = self.judge("stray-end", arch=dict(stray=True))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("1 KL line(s) outside any dump", self.reasons(out))

    def test_silence_after_a_stop_is_partial_and_names_the_last_stop(self):
        out = self.judge("silent25", arch=dict(stops=25, final=False, hold=False, dump1=False, ret=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the last note is n=25 (arrival 25, checkpoint 19)", out["why"])
        self.assertTrue(any("before the final stop" in r for r in out["reasons"]))
        self.assertFalse(any("NO RETURN" in r for r in out["reasons"]), "the chain after the last stop is not judged while the stops themselves are incomplete")

    def test_a_return_note_before_the_first_stop_is_not_a_pass(self):
        out = self.judge("return-only", arch=dict(stops=0, dump1=False, final=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the only notes are reason-0 arrivals", self.reasons(out))

    def test_stop_note_failures_keep_their_nat059_reasons_and_mention_the_dumps_that_did_arrive(self):
        out = self.judge("gap", arch=dict(skip=(24,)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the notes skip numbers: 23->25", self.reasons(out))
        self.assertIn("2 complete log dump(s) did arrive (why=1,2)", self.reasons(out))
        out = self.judge("wrong", arch=dict(wrong={26: 19}))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("notes whose checkpoint is not the one this image has at that position: n=26", self.reasons(out))
        out = self.judge("oldtable", arch=dict(edit={n: dict(kttbr0=CP5_TTBR0) for n in range(23, 28)}))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("from checkpoint 17 the stub gave back the checkpoint-5 table (0x9e15ae000), not the one arm_vm_init installed", self.reasons(out))
        out = self.judge("refused", arch=dict(stops=23, final=False, dump1=False, ret=False, edit={23: dict(mask=MASK_BAD_TTBR0 | 0x3e, kttbr0=CP5_TTBR0)}))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the loader refused to resume at n=23 (checkpoint 17, mask 0x103e): the TTBR0 to give back was not a plausible table base", self.reasons(out))

    def test_a_kernel_exception_note_is_an_exception_verdict_with_esr_elr_far(self):
        out = self.judge("exc25", arch=dict(stops=25, exception_at=25, final=False, hold=False, dump1=False, ret=False))
        self.assertEqual(out["verdict"], "EXCEPTION", out.get("why"))
        self.assertEqual((out["exception"]["n"], out["exception"]["last"], out["exception"]["esr"], out["exception"]["elr"], out["exception"]["far"]),
                         (25, 19, "0x96000045", "0xfffffff007441234", "0xdeadbeef000"))

    def test_a_return_note_is_not_counted_as_a_stop_note_and_does_not_make_the_final_bit_vanish(self):
        out = self.judge("full")
        p = out["progress"]
        self.assertEqual(p["notes"], 27)
        self.assertEqual(p["stops"][-1]["last"], 21)
        self.assertTrue(p["reached_final"])


if __name__ == "__main__":
    unittest.main()
