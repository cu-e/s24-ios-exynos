#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-059 host tests, second half: the session driver (session_nat059.py) and the verdict analyser (analyze_nat059.py) for the image
loader-diag-xnu-ckpt4-usb. Evidence kind: host-test. Nothing here talks to a phone: `adb` is the NAT-049 fake that models the RECOVERY block
in a file, the collector launcher and the udev check are stand-ins, and the "phone" behind the real NAT-041 collector is the NAT-041 DWC3 model
whose ring is seeded with the text formats of the image (decode52's contract). The archives are NOT hardware evidence.

    python3 -I docs/procedures/nat-059/test_nat059_run.py

Layers:
  Derivation   the driver and the analyser differ from NAT-057's files only by the lines listed here; the pinned hashes are those of package-002
               and the build record (and of the second, identical build).
  RealTreeGate in the real tree the driver stops before any adb call in every mode while there is no agent-written decision file.
  Flow         the driver in a scratch tree: preflight is read-only; the registry needs NAT-058 and NAT-059 done as well; a launch writes RECOVERY
               only, reads it back, starts the watcher and the collector before the single reboot; the marker makes it one-shot.
  Verdicts     the analyser on archives written by the real collector: PASS needs all 27 notes, the stub's TTBR0 evidence and the hold; every way
               the run can end short (silence after a stop, the loader's refusal, the old table given back, an exception note) has its own verdict.
NAT-057 holds the tests of everything this file inherits (the driver's gates and flows, the NAT-049 integrity, T0, boot-id and provenance rules)."""
import difflib, hashlib, importlib.util, json, os, re, shutil, signal, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
DRIVER = Path(os.environ.get("NAT059_DRIVER") or HERE / "session_nat059.py")
ANALYZE = Path(os.environ.get("NAT059_ANALYZE") or HERE / "analyze_nat059.py")
IMAGE = "loader-diag-xnu-ckpt4-usb"
PACKAGE = ROOT / "artifacts/nat-059/package-002"
BUILD = ROOT / "artifacts/nat-059/build-002"
BUILD2 = ROOT / "artifacts/nat-059/build-003"
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
STOCK_SHA = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
SCRATCH = ROOT / "artifacts/nat-059/tmp"
MASK_FINAL, MASK_BAD_TTBR0, MASK_BAD_STATE = 1 << 13, 1 << 12, 1 << 14
CP5_TTBR0, TTEP = 0x9e15ae000, 0x9e15a8000        # the value measured at checkpoint 5 (NAT-058) and an _invalid_ttep-like table base
source_pin = unittest.skipIf(os.environ.get("NAT059_BEHAVIOUR_ONLY") == "1", "source-text pin (skipped in the behavioural mutation pass)")


def scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T57 = load(PROC / "nat-057/test_nat057.py", "nat059_test_nat057")        # fixtures only (and, through it, NAT-049's): never its test classes
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
@unittest.skipUnless((PACKAGE / "package.json").exists(), "NAT-059 package-002 is not present")
class Derivation(unittest.TestCase):
    @source_pin
    def test_pinned_hashes_are_those_of_package_002_and_the_build_records_and_the_second_build(self):
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        p = pkg["images"][IMAGE]
        self.assertEqual(sorted(pkg["images"]), [IMAGE])
        self.assertTrue(pkg["flashed"] is False and pkg["kind"] == "host-test" and pkg["device_used"] is False)
        self.assertEqual(pkg["stock_sha256"], STOCK_SHA)
        self.assertRegex(src, r"(?m)^PACKAGE=ROOT/'artifacts/nat-059/package-002'")
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
        m = load(DRIVER, "nat059_driver_pins")
        self.assertEqual(sorted(m.IMAGES), [IMAGE])
        self.assertEqual((m.IMAGES[IMAGE]["NEW_SHA"], m.IMAGES[IMAGE]["CANARY_SHA"], m.IMAGES[IMAGE]["CANARY_LEN"]),
                         (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))
        self.assertEqual(m.STOCK_SHA, STOCK_SHA)
        self.assertEqual(m.PACKAGE.relative_to(m.ROOT), PACKAGE.relative_to(ROOT))

    @source_pin
    def test_the_driver_differs_from_the_nat057_driver_only_where_the_task_says(self):
        removed, added = diff_lines(PROC / "nat-057/session_nat052.py", DRIVER)
        self.assertEqual(removed, [
            "'loader-diag-xnu-ckpt3-usb':dict(",
            "NEW_SHA='a8161cccddb4282796a848b2c5b464d5457dcc0bb9bc2e0c1fa9cb1014967d97',",
            "CANARY_SHA='9d9cb972496807177771febf819d783f0823ecd2fb44fad2f9fadbfc3027440e',  # Image.payload (loader + XNU payload + ADT)",
            "PACKAGE=ROOT/'artifacts/nat-052/package-002'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052')   # NAT-043: the log channel is proven on hardware; NAT-052: the image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat052-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-057/native-attempt-%s-used.json'%a.image)"])
        p = pinned()
        self.assertEqual(added, [
            "'loader-diag-xnu-ckpt4-usb':dict(",
            "NEW_SHA='%s'," % p["recovery_sha256"],
            "CANARY_SHA='%s',  # Image.payload (loader + XNU payload + ADT)" % p["payload_sha256"],
            "PACKAGE=ROOT/'artifacts/nat-059/package-002'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059')   # NAT-043/NAT-058: the log channel and the NAT-052 image ran on hardware; NAT-059: this image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat059-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-059/native-attempt-%s-used.json'%a.image)"])

    @source_pin
    def test_the_analyser_differs_from_the_nat057_analyser_only_where_the_task_says(self):
        removed, added = diff_lines(PROC / "nat-057/analyze_nat052.py", ANALYZE)
        self.assertEqual(removed, [
            'A49 = _load("nat057_nat049_analyze_usblog", PROC / "nat-049" / "analyze_usblog.py")',
            'D52 = _load("nat057_nat052_decode52", PROC / "nat-052" / "decode52.py")',
            'IMAGE = "loader-diag-xnu-ckpt3-usb"',
            "STOP_LIST = (1, 2, 3, 4, 5, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16)   # `last` of each arrival: 5 assembly stops + NAT-036's 17 C stops",
            'stops=[dict(n=s["n"], arr=s["arr"], last=s["last"], mask=hex(s["mask"]), mmu_on=s["mmu_on"], setups=s["setups"]) for s in prog["stops"]])'])
        self.assertEqual(sorted(l for l in added if l.startswith(("A49 =", "D52 =", "IMAGE =", "STOP_LIST ="))), sorted([
            'A49 = _load("nat059_nat049_analyze_usblog", PROC / "nat-049" / "analyze_usblog.py")',
            'D52 = _load("nat059_nat052_decode52", PROC / "nat-052" / "decode52.py")',
            'IMAGE = "loader-diag-xnu-ckpt4-usb"',
            "STOP_LIST = (1, 2, 3, 4, 5, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)   # `last` of each arrival: 5 assembly stops + 22 C stops"]))
        # everything else that was added is the TTBR0 rule (ttbr0_problems and its call) and the two fields of the stop summary
        rest = [l for l in added if not l.startswith(("A49 =", "D52 =", "IMAGE =", "STOP_LIST ="))]
        self.assertEqual(rest[0], "PRE_VM_N = STOP_LIST.index(16) + 1        # the notes n=5..22 are before arm_vm_init (the stub gives back the checkpoint-5 TTBR0); n=23..27 are checkpoints 17..21")
        self.assertIn("why += ttbr0_problems(stops)", rest)
        self.assertIn("def ttbr0_problems(stops):", rest)
        self.assertEqual(len(rest), 26, rest)

    def test_the_analyser_list_is_the_build_lists_with_the_five_assembly_stops_before_it(self):
        an = load(ANALYZE, "nat059_analyze_list")
        build = json.loads((BUILD / "build.json").read_text()) if (BUILD / "build.json").exists() else None
        if build is None:
            self.skipTest("no build record")
        self.assertEqual(an.STOP_LIST, (1, 2, 3, 4, 5) + tuple(build["stops"]))
        self.assertEqual((len(an.STOP_LIST), an.STOP_LIST[-1], an.PRE_VM_N, an.STOP_LIST[an.PRE_VM_N - 1], an.STOP_LIST[an.PRE_VM_N]), (27, 21, 22, 16, 17))
        self.assertEqual(an.IMAGE, IMAGE)
        self.assertEqual(load(DRIVER, "nat059_driver_name").IMAGES[IMAGE]["NEW_SHA"], pinned()["recovery_sha256"])


# ------------------------------------------------------------------------------------------------------------------ RealTreeGate
class RealTreeGate(unittest.TestCase):
    def decisions(self):
        return sorted((ROOT / "docs/decisions").glob("*-nat059-%s-single-run-*.md" % IMAGE))

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
        marker = ROOT / ("artifacts/nat-059/native-attempt-%s-used.json" % IMAGE)
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
            blocker = load(DRIVER, "nat059_driver_real_registry").registry_blocker(found[0])
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
                      "0023-nat059-loader-diag-xnu-ckpt3-usb-single-run-2026-11-12.md"):
                (d / n).write_text("x")
            self.assertEqual(sorted(d.glob("*-nat059-%s-single-run-*.md" % IMAGE)), [])
            (d / ("0025-nat059-%s-single-run-2026-11-12.md" % IMAGE)).write_text("x")
            self.assertEqual(len(sorted(d.glob("*-nat059-%s-single-run-*.md" % IMAGE))), 1)


# ------------------------------------------------------------------------------------------------------------------ Flow
@unittest.skipUnless((PACKAGE / "package.json").exists() and STOCK.exists(), "NAT-059 package-002 or the stock RECOVERY backup is not present")
class Flow(unittest.TestCase):
    """The driver in a scratch tree: fake decision file and registry, the NAT-049 fake adb, the real NAT-048 watcher on a fake sysfs through its
    one-file wrapper, stand-ins for the collector launcher and the udev check (NAT-049 tests their real behaviour)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = scratch("flow-")
        drv = t / "docs/procedures/nat-059"
        drv.mkdir(parents=True)
        shutil.copy(DRIVER, drv / "session_nat059.py")
        (t / "docs/procedures/nat-049").mkdir(parents=True)
        (t / "docs/procedures/nat-049/collector_launch.py").write_text(T49.STUB_COLLECTOR)
        (t / "docs/procedures/nat-049/host_access.py").write_text(T49.STUB_ACCESS)
        (t / "docs/procedures/nat-048").mkdir(parents=True)
        (t / "docs/procedures/nat-048/usb_watch.py").write_text(T49.WRAPPER)
        (t / "docs/decisions").mkdir(parents=True)
        (t / "state").mkdir()
        for rel in ("package.json", "%s/recovery.img" % IMAGE):
            dst = t / "artifacts/nat-059/package-002" / rel
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
        cls.driver = drv / "session_nat059.py"
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
        for p in (self.tmp / "artifacts/nat-059").glob("native-attempt-*"):
            p.unlink()
        if self.venv.is_symlink() or self.venv.exists():
            self.venv.unlink()
        os.symlink(sys.executable, self.venv)
        self.n = 0
        self.decision = "0099-nat059-%s-single-run-2026-11-12.md" % IMAGE
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

    def registry(self, done=("NAT-039", "NAT-046", "NAT-043", "NAT-052", "NAT-058", "NAT-059"), value=True):
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
        return self.tmp / ("artifacts/nat-059/native-attempt-%s-used.json" % IMAGE)

    def test_preflight_is_read_only(self):
        r, rep, out = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((rep["outcome"], rep["registry_blocker"]), ("ready-read-only", None))
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual([c for c in self.lines("adb-calls") if c.startswith("reboot")], [])
        self.assertFalse(self.marker().exists())
        self.assertEqual(sha256(self.base / "recovery.bin"), STOCK_SHA)

    def test_the_registry_needs_nat_058_and_nat_059_done_too_and_the_native_decision_to_cite_this_file(self):
        base = ("NAT-039", "NAT-046", "NAT-043", "NAT-052", "NAT-058", "NAT-059")
        for missing in ("NAT-058", "NAT-059", "NAT-052", "NAT-043"):
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


def script59(m, P, *, stops=27, skip=(), edit=None, exception_at=None, final=True, hold=True, wrong=None, banner=None):
    """The text the image writes: loader banner and ladder as NAT-047/NAT-057, then one `CK` note per stop (27 of them), then HOLD.
    `edit` = {n: dict(note_line keyword overrides)}."""
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
    for i in range(stops):
        n = i + 1
        if n in skip:
            continue
        kw = dict(mask=MASK_FINAL if (final and i == stops - 1) else 0, kttbr0=kttbr0_of(n), sctlr=0x3454599c if n <= 5 else 0x3454599d,
                  sp=0x800aa080 if n <= 2 else 0xfffffff008060000 if n <= 5 else 0xfffffff00805fef0)
        if exception_at == n:
            kw.update(x2=1, x3=0, exc=(0x96000045, 0xfffffff007441234, 0xdeadbeef000))
        kw.update((edit or {}).get(n, {}))
        m.text(T57.note_line(n, i + 1, (wrong or {}).get(n, order[i]), **kw))
    if hold:
        m.text("HOLD stage=0x51 code=0x2000")


def an_stop_list():
    return (1, 2, 3, 4, 5, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)


def make_archive(tc, *, boot_image=None, create_t=BASE, first_t=FIRST, live=True, plug=True, ring_size=32768, go_s=1.0, max_bytes=1 << 24, **kw):
    from unittest import mock
    T = T49.t41()
    clock = T49.Stamp(create_t)
    real_archive = T.L.A.Archive
    with mock.patch.object(T.L.A, "stamp", clock), \
            mock.patch.object(T.L.A, "Archive", (lambda out, ch, prov: real_archive(out, ch, "unqualified-live")) if live else real_archive):
        r = T.Rig(tc, ring_size=ring_size, boot_id=T49.boot_id_of(boot_image or IMAGE), plugged=plug)
        if plug:
            script59(r.m, T.P, **kw)
        clock.t = first_t
        r.go(go_s, max_bytes)
    return r


class Verdicts(unittest.TestCase):
    cache = {}

    @classmethod
    def setUpClass(cls):
        T49.t41()
        cls.an = load(ANALYZE, "nat059_analyze_under_test")
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

    def test_a_complete_run_is_a_pass_naming_27_notes_the_two_tables_and_the_hold(self):
        out = self.judge("full")
        self.assertEqual(out["verdict"], "PASS", (out.get("why"), out["reasons"]))
        p = out["progress"]
        self.assertEqual((p["notes"], p["last_checkpoint"], p["held"], p["reached_final"], p["gaps"]), (27, 21, True, True, []))
        self.assertEqual([s["kttbr0"] for s in p["stops"][4:22]], [hex(CP5_TTBR0)] * 18)
        self.assertEqual([s["kttbr0"] for s in p["stops"][22:]], [hex(TTEP)] * 5)
        self.assertEqual(p["hold"], {"stage": 0x51, "code": 0x2000})
        self.assertIn("27 stop notes (n=1..27, final checkpoint 21)", out["why"])

    def test_a_synthetic_archive_never_passes(self):
        d = self.arch("synthetic", live=False)
        self.assertEqual(self.an.analyze(d, usb_log(), report())["verdict"], "undetermined")
        self.assertEqual(self.an.analyze(d, usb_log(), report(), allow_synthetic=True)["verdict"], "simulated-PASS")

    def test_the_old_image_boot_is_not_evidence_about_this_image(self):
        out = self.judge("old-image", arch=dict(boot_image="loader-diag-xnu-ckpt3-usb"))
        self.assertEqual(out["verdict"], "undetermined", out.get("why"))
        self.assertIn("none has the boot id of %s" % IMAGE, out["why"])

    def test_the_run_of_the_previous_image_ends_where_it_did_and_is_partial_naming_checkpoint_16(self):
        # what NAT-058's image would look like here: 22 notes, the final bit at n=22 (checkpoint 16), HOLD: not the final stop of this image
        out = self.judge("old-like", arch=dict(stops=22))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the final-stop bit is set at n=22 (checkpoint 16) but this image's list has 27 stops ending at checkpoint 21", self.reasons(out))

    def test_silence_after_a_post_arm_vm_init_stop_is_partial_and_names_the_last_stop(self):
        out = self.judge("silent25", arch=dict(stops=25, final=False, hold=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the last note is n=25 (arrival 25, checkpoint 19)", out["why"])
        self.assertTrue(any("before the final stop" in r for r in out["reasons"]) and any("no HOLD" in r for r in out["reasons"]))

    def test_the_loaders_refusal_to_resume_is_partial_and_says_which_stop_and_why(self):
        out = self.judge("refused", arch=dict(stops=23, final=False, edit={23: dict(mask=MASK_BAD_TTBR0 | 0x3e, kttbr0=CP5_TTBR0)}))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the loader refused to resume at n=23 (checkpoint 17, mask 0x103e): the TTBR0 to give back was not a plausible table base", self.reasons(out))
        out = self.judge("badstate", arch=dict(stops=24, final=False, edit={24: dict(mask=MASK_BAD_STATE | 0x3e)}))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the loader refused to resume at n=24 (checkpoint 18, mask 0x403e): the C stop arrived in a state the stub does not understand", self.reasons(out))

    def test_giving_back_the_old_table_after_arm_vm_init_is_not_a_pass_even_with_every_note_present(self):
        out = self.judge("oldtable", arch=dict(edit={n: dict(kttbr0=CP5_TTBR0) for n in range(23, 28)}))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("from checkpoint 17 the stub gave back the checkpoint-5 table (0x9e15ae000), not the one arm_vm_init installed", self.reasons(out))

    def test_a_table_that_changes_between_stops_or_is_not_a_table_base_is_not_a_pass(self):
        out = self.judge("pre-changes", arch=dict(edit={9: dict(kttbr0=0x9e15ad000)}))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("kttbr0 differs between the stops up to checkpoint 16: ", self.reasons(out))
        out = self.judge("post-changes", arch=dict(edit={25: dict(kttbr0=TTEP + 0x1000)}))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("kttbr0 differs between the stops after arm_vm_init: ", self.reasons(out))
        for label, bad in (("zero", 0), ("unaligned", TTEP + 0x10), ("high", 0xab00000000000000 | TTEP)):
            out = self.judge("post-" + label, arch=dict(edit={n: dict(kttbr0=bad) for n in range(23, 28)}))
            self.assertEqual(out["verdict"], "PARTIAL", label)
            self.assertIn("kttbr0 after arm_vm_init is not a table base: %s" % hex(bad), self.reasons(out), label)

    def test_a_kernel_exception_note_after_arm_vm_init_is_an_exception_verdict_with_esr_elr_far(self):
        out = self.judge("exc25", arch=dict(stops=25, exception_at=25, final=False, hold=False))
        self.assertEqual(out["verdict"], "EXCEPTION", out.get("why"))
        self.assertEqual((out["exception"]["n"], out["exception"]["last"], out["exception"]["esr"], out["exception"]["elr"], out["exception"]["far"]),
                         (25, 19, "0x96000045", "0xfffffff007441234", "0xdeadbeef000"))

    def test_a_gap_a_wrong_checkpoint_or_a_missing_hold_is_not_a_pass(self):
        out = self.judge("gap", arch=dict(skip=(24,)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the notes skip numbers: 23->25", self.reasons(out))
        out = self.judge("wrong", arch=dict(wrong={26: 19}))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("notes whose checkpoint is not the one this image has at that position: n=26", self.reasons(out))
        out = self.judge("nohold", arch=dict(hold=False))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("no HOLD record", self.reasons(out))

    def test_a_pass_cites_only_the_notes_the_kernel_reported(self):
        # the TTBR0 rule reads the notes' own field; a note list whose n=5 note is missing cannot show the pre-VM table
        out = self.judge("no5", arch=dict(skip=(5,)))
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertIn("the notes skip numbers: 4->6", self.reasons(out))


if __name__ == "__main__":
    unittest.main()
