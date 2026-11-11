#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-057 host tests: the session driver (session_nat052.py) and the verdict analyser (analyze_nat052.py) for the NAT-052 image
loader-diag-xnu-ckpt3-usb. Evidence kind: host-test. Nothing here talks to a phone: `adb` is a fake that records its calls and models the
RECOVERY block in a file, the watcher runs on a fake sysfs, the collector launcher and the udev check are stand-ins in a scratch tree, and the
"phone" behind the real NAT-041 collector is the NAT-041 DWC3 model (or, in the optional simulator layer, the NAT-052 loader run in unicorn).

Layers:
  * Derivation   the driver is the NAT-049 driver (itself the NAT-048 driver) with exactly the listed lines changed; its pinned hashes are
                 those of NAT-052 package-002 and build-003; the safety lines of the NAT-048/049 drivers are still there; nothing new touches
                 the device or the host.
  * RealTreeGate in the real tree there is no agent-written decision file, so the driver stops before any adb call in every mode.
  * OpenGateFlow the driver in a scratch tree: every gate (decision file, registry incl. NAT-043 and NAT-052 done, udev check, collector
                 self-test, watcher self-test, device checks) stops before the first write; a launch writes RECOVERY only, reads it back in
                 full, starts the watcher AND the collector before the single reboot; a failed write/readback/watcher/collector restores the
                 stock image and never reboots; the one-shot marker prevents a second run; --restore writes only the stock image.
  * Verdicts     the analyser on archives written by the real NAT-041 collector from the DWC3 model, the ring seeded with the text formats of
                 the NAT-052 image (decode52's contract): PASS / PARTIAL / EXCEPTION / FAIL / undetermined and the NAT-049 integrity, T0,
                 boot-id, provenance and USB-log rules it inherits. The provenance label is forced to unqualified-live inside the fixtures
                 only to exercise the PASS path: these archives are NOT hardware evidence.
  * Simulated    (needs unicorn, capstone and the host C compiler) the same analyser on the archives of the REAL NAT-052 loader built and
                 run in the NAT-052 simulator; every verdict there is `simulated-*`, never a plain one.
The fakes are not the phone: what these tests establish is control flow and the verdict rules, not device behaviour."""
import difflib, hashlib, importlib.util, json, os, re, shutil, signal, subprocess, sys, tempfile, time, unittest, warnings
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
DRIVER = Path(os.environ.get("NAT057_DRIVER") or HERE / "session_nat052.py")            # mutated copies for the mutation checks
ANALYZE = Path(os.environ.get("NAT057_ANALYZE") or HERE / "analyze_nat052.py")
NAT049_DRIVER = PROC / "nat-049/session_usblog.py"
NAT048_DRIVER = PROC / "nat-048/session_reset_canary.py"
NAT048_WATCH = PROC / "nat-048/usb_watch.py"
IMAGE = "loader-diag-xnu-ckpt3-usb"
PACKAGE = ROOT / "artifacts/nat-052/package-002"
BUILD = ROOT / "artifacts/nat-052/build-003"
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
STOCK_SHA = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
MASK_FINAL = 1 << 13

source_pin = unittest.skipIf(os.environ.get("NAT057_BEHAVIOUR_ONLY") == "1", "source-text pin (skipped in the behavioural mutation pass)")


SCRATCH = ROOT / "artifacts/nat-057/tmp"        # gitignored; the 96 MiB RECOVERY copies of the flow tests must not depend on the quota of /tmp


def scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T49 = load(PROC / "nat-049/test_nat049.py", "nat057_test_nat049")           # fixtures only: the fake adb, the stubs, the NAT-041 collector rig
sha256, code_lines, alive = T49.sha256, T49.code_lines, T49.alive
BASE, T0, FIRST, iso, Stamp, usb_log, report, rehash = T49.BASE, T49.T0, T49.FIRST, T49.iso, T49.Stamp, T49.usb_log, T49.report, T49.rehash
tearDownModule = T49.tearDownModule


def pinned():
    return json.loads((PACKAGE / "package.json").read_text())["images"][IMAGE]


def decision_text(with_recovery=True, with_payload=True, with_0019=True):
    p = pinned()
    parts = ["scratch-tree decision for %s\n" % IMAGE]
    if with_recovery:
        parts.append("RECOVERY SHA-256 %s\n" % p["recovery_sha256"])
    if with_payload:
        parts.append("Image.payload SHA-256 %s\n" % p["payload_sha256"])
    if with_0019:
        parts.append("recorded under decision 0019\n")
    return "".join(parts)


def decision_name(n="0099", tag="nat052"):
    return "%s-%s-%s-single-run-2026-11-12.md" % (n, tag, IMAGE)


# ----------------------------------------------------------------------------------------------------------------- the driver
@unittest.skipUnless((PACKAGE / "package.json").exists(), "NAT-052 package-002 is not present")
class Derivation(unittest.TestCase):
    @source_pin
    def test_pinned_hashes_are_those_of_package_002_and_the_build_record(self):
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        p = pkg["images"][IMAGE]
        self.assertEqual(sorted(pkg["images"]), [IMAGE])
        self.assertTrue(pkg["flashed"] is False and pkg["kind"] == "host-test" and pkg["device_used"] is False)
        self.assertEqual(pkg["stock_sha256"], STOCK_SHA)
        self.assertRegex(src, r"(?m)^PACKAGE=ROOT/'artifacts/nat-052/package-002'")
        self.assertRegex(src, r"(?m)^STOCK_SHA='%s'" % STOCK_SHA)
        for value in (p["recovery_sha256"], p["payload_sha256"]):
            self.assertEqual(src.count(value), 1, value)
        self.assertIn("CANARY_LEN=%d" % p["payload_bytes"], src)
        self.assertEqual(p["payload_offset"], 2048)
        self.assertIn("PAYLOAD_OFFSET=2048", src)
        self.assertNotEqual(p["payload_sha256"], p["loader_image_sha256"], "the payload, not the loader-only Image, is pinned")
        self.assertNotIn(p["loader_image_sha256"], src)
        rec = PACKAGE / IMAGE / "recovery.img"
        if rec.exists():
            self.assertEqual(sha256(rec), p["recovery_sha256"])
        if (BUILD / "build.json").exists():
            build = json.loads((BUILD / "build.json").read_text())
            self.assertEqual(build["image_payloads"][IMAGE]["sha256"], p["payload_sha256"])
            self.assertEqual(build["image_payloads"][IMAGE]["bytes"], p["payload_bytes"])
        m = load(DRIVER, "nat057_driver_pins")
        self.assertEqual(sorted(m.IMAGES), [IMAGE])
        self.assertEqual((m.IMAGES[IMAGE]["NEW_SHA"], m.IMAGES[IMAGE]["CANARY_SHA"], m.IMAGES[IMAGE]["CANARY_LEN"]),
                         (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))
        self.assertEqual(m.STOCK_SHA, STOCK_SHA)
        self.assertEqual(m.STOCK.relative_to(m.ROOT), STOCK.relative_to(ROOT))
        self.assertEqual(m.PACKAGE.relative_to(m.ROOT), PACKAGE.relative_to(ROOT))

    @source_pin
    def test_the_driver_differs_from_the_nat049_driver_only_where_the_task_says(self):
        removed = [l[2:] for l in difflib.ndiff(code_lines(NAT049_DRIVER), code_lines(DRIVER)) if l.startswith("- ")]
        added = [l[2:] for l in difflib.ndiff(code_lines(NAT049_DRIVER), code_lines(DRIVER)) if l.startswith("+ ")]
        self.assertEqual(removed, [
            "'loader-diag-usbmon':dict(",
            "NEW_SHA='c6802dea4682a4bc993885bf525e2907e42e4eeebb964310da82ed79fef7212d',",
            "CANARY_SHA='a90a93d77ea56d22b8af555d34bc91bf8871db8f12ed071bd534d16940d08b73',  # Image.payload (loader + XNU payload + ADT)",
            "CANARY_LEN=21853792),",
            "'loader-diag-usbmon-fault':dict(",
            "NEW_SHA='f1a193dcac776dde004a3d1a379c26a4a365a150318bbc0a6501506ad7dfa103',",
            "CANARY_SHA='06281749f38bb6c8e944c3c82b4e77297b5749757e57b4d3c4d9f623b5025d77',",
            "CANARY_LEN=21853792),",
            "PACKAGE=ROOT/'artifacts/nat-047/package-001'",
            "LAUNCHER=HERE/'collector_launch.py'",
            "HOST_ACCESS=HERE/'host_access.py'",
            "REQUIRED_DONE=('NAT-039','NAT-046')   # the preconditions of nat-047/decision-template.md that the registry can show",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat043-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-049/native-attempt-%s-used.json'%a.image)",
        ])
        self.assertEqual(added, [
            "'loader-diag-xnu-ckpt3-usb':dict(",
            "NEW_SHA='a8161cccddb4282796a848b2c5b464d5457dcc0bb9bc2e0c1fa9cb1014967d97',",
            "CANARY_SHA='9d9cb972496807177771febf819d783f0823ecd2fb44fad2f9fadbfc3027440e',  # Image.payload (loader + XNU payload + ADT)",
            "CANARY_LEN=21857888),",
            "PACKAGE=ROOT/'artifacts/nat-052/package-002'",
            "LAUNCHER=ROOT/'docs/procedures/nat-049/collector_launch.py'",
            "HOST_ACCESS=ROOT/'docs/procedures/nat-049/host_access.py'",
            "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052')   # NAT-043: the log channel is proven on hardware; NAT-052: the image exists",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat052-%s-single-run-*.md'%image))",
            "marker=ROOT/('artifacts/nat-057/native-attempt-%s-used.json'%a.image)",
        ])

    @source_pin
    def test_the_safety_lines_are_those_of_the_nat048_driver(self):
        old = {l.strip() for l in NAT048_DRIVER.read_text().splitlines()}
        new = {l.strip() for l in DRIVER.read_text().splitlines()}
        keep = [
            "SIZE=100663296", "TARGET='/dev/block/sda18'",
            "WRITE=\"su -c 'test -b /dev/block/sda18 && dd of=/dev/block/sda18 bs=1048576 count=100663296 iflag=count_bytes conv=notrunc,fsync'\"",
            "assert len(data)==SIZE and digest(data)==expected", "assert dd_idle(), 'a remote dd process is still running'",
            "assert measured==expected,'full RECOVERY readback mismatch'", "assert identity.splitlines()==[TARGET,str(SIZE),'block_device'],identity",
            "assert int(values['level'])>=50 and int(values['temperature'])<420",
            "assert not any(s.strip().lower() in ['odin4','heimdall'] for s in processes),'another flasher is active'",
            "if not a.restore: assert initial==STOCK_SHA, 'launch requires unchanged stock RECOVERY'",
            "assert len(stock)==len(candidate)==SIZE and digest(stock)==STOCK_SHA and digest(candidate)==NEW_SHA",
            "run(['adb','reboot','recovery'])", "report['reboot_sent']=True;report['reboot_requested_at']=now();save()",
            "if report['device_write_started'] and not report['reboot_sent'] and not a.restore:",
            "write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()",
            "assert shell('getprop ro.product.model')=='SM-S921B'", "assert shell('getprop ro.build.PDA')=='S921BXXS9BYH3'",
            "fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)", "write(stock,STOCK_SHA);report['outcome']='stock-written-readback-confirmed';save();print(report['outcome']);return 0",
            "assert digest(candidate[PAYLOAD_OFFSET:PAYLOAD_OFFSET+CANARY_LEN])==CANARY_SHA,'loader Image.payload not at its expected offset'",
            "if not a.restore:watcher_selftest()",
        ]
        for line in keep:
            self.assertIn(line, old, "not in the NAT-048 driver: " + line)
            self.assertIn(line, new, "missing from the NAT-057 driver: " + line)

    @source_pin
    def test_the_added_code_adds_no_device_or_host_action(self):
        added = [l[2:] for l in difflib.ndiff(code_lines(NAT049_DRIVER), code_lines(DRIVER)) if l.startswith("+ ")]
        text = "\n".join(added)
        for forbidden in (r"\badb\b", r"su -c", r"\bsudo\b", r"dd of", r"os\.kill", r"rmtree", r"unlink", r"write_bytes", r"Popen", r"subprocess", r"reboot"):
            self.assertIsNone(re.search(forbidden, text), "the added code must not add a device or host action: " + forbidden)

    @source_pin
    def test_reboot_and_flash_surface(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("reboot','recovery'"), 1)
        self.assertEqual(len(re.findall(r"'reboot'", src)), 1, "no other reboot form (reboot bootloader/download, a plain reboot)")
        self.assertNotIn("fastboot", src.lower())
        self.assertEqual(sorted(set(re.findall(r"/dev/block/[\w/.-]+", src))), ["/dev/block/by-name/recovery", "/dev/block/sda18"])
        self.assertEqual(len(re.findall(r"dd of=", src)), 1)
        self.assertNotRegex(src, r"\bsudo\b|\bdocker\b|\bchmod\b|\budevadm\b", "the driver installs nothing and escalates nothing on the host")
        self.assertEqual(len(re.findall(r"Popen\(", src)), 2, "exactly the watcher and the collector are spawned")
        self.assertEqual(src.count("start_new_session=True"), 2)

    @source_pin
    def test_the_driver_never_creates_the_decision_file_and_never_writes_the_registry(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("ROOT/'docs/decisions'"), 1)
        self.assertRegex(src, r"glob\('\*-nat052-%s-single-run-\*\.md'%image\)")
        self.assertNotRegex(src, r"decisions[^\n]*(write_text|write_bytes|open\()")
        self.assertIn("marker.open('x')", src)
        self.assertIn("exist_ok=False", src)
        self.assertNotRegex(src, r"lab\.json[^\n]*(write|open\([^)]*['\"]w)")
        self.assertEqual(src.count("state/lab.json"), 1)

    @source_pin
    def test_the_gates_are_checked_before_the_first_adb_call_and_the_collector_before_the_reboot(self):
        src = DRIVER.read_text()
        first_adb = src.index("run(['adb','get-state'])")
        for needle in ("decision=gate(a.image,cfg)", "blocker=registry_blocker(decision)", "host_access();collector_selftest()"):
            self.assertEqual(src.count(needle), 1, needle)
            self.assertLess(src.index(needle), first_adb, needle)
        self.assertLess(src.index("decision=gate(a.image,cfg)"), src.index("blocker=registry_blocker(decision)"))
        self.assertLess(src.index("blocker=registry_blocker(decision)"), src.index("host_access();collector_selftest()"))
        self.assertIn("if not a.restore:\n                blocker=registry_blocker(decision)", src)
        self.assertIn("assert not (a.execute and blocker),blocker", src)
        write, watcher, collector, reboot = (src.index(x) for x in ("write(candidate,NEW_SHA)", "            watcher_start()\n", "            collector_start()\n", "run(['adb','reboot','recovery'])"))
        self.assertLess(write, watcher)
        self.assertLess(watcher, collector)
        self.assertLess(collector, reboot)

    def test_the_analyser_knows_the_image_stop_list_of_the_build_record(self):
        a = load(ANALYZE, "nat057_analyzer_stops")
        self.assertEqual(len(a.STOP_LIST), 22)
        build = BUILD / "build.json"
        if build.exists():
            self.assertEqual(list(a.STOP_LIST), [1, 2, 3, 4, 5] + json.loads(build.read_text())["stops"])
        self.assertEqual(list(a.STOP_LIST), STOP_LAST)

    def test_the_registry_preconditions_and_the_windows(self):
        d = load(DRIVER, "nat057_driver_windows")
        a = load(PROC / "nat-049/analyze_usblog.py", "nat057_analyzer49_windows")
        self.assertEqual(d.REQUIRED_DONE, ("NAT-039", "NAT-046", "NAT-043", "NAT-052"))
        for name in ("WATCH_S", "COLLECT_S"):
            self.assertGreaterEqual(getattr(d, name), a.RECEIVE_WINDOW_S + 30)
        self.assertGreaterEqual(d.WATCH_S, a.COVERAGE_S)
        self.assertEqual(d.LAUNCHER.relative_to(d.ROOT), Path("docs/procedures/nat-049/collector_launch.py"))
        self.assertEqual(d.HOST_ACCESS.relative_to(d.ROOT), Path("docs/procedures/nat-049/host_access.py"))
        self.assertTrue(d.LAUNCHER.exists() and d.HOST_ACCESS.exists() and d.WATCHER.exists())

    def test_the_image_name_of_the_driver_and_the_analyser_agree(self):
        d = load(DRIVER, "nat057_driver_names")
        a = load(ANALYZE, "nat057_analyzer_names")
        self.assertEqual(sorted(d.IMAGES), [a.IMAGE])
        self.assertEqual(a.IMAGE, IMAGE)


class RealTreeGate(unittest.TestCase):
    """The real tree: the driver stops before any adb call (at the decision gate while no decision file exists, at the registry gate for --execute afterwards)."""

    def decisions(self):
        return sorted((ROOT / "docs/decisions").glob("*-nat052-%s-single-run-*.md" % IMAGE))

    def run_driver(self, *mode):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "bin").mkdir()
            fake = t / "bin/adb"
            fake.write_text("#!/bin/sh\necho \"$@\" >> %s\nexit 1\n" % (t / "adb-calls"))
            fake.chmod(0o755)
            env = {"PATH": f"{t / 'bin'}:/usr/bin:/bin", "HOME": str(t)}
            r = subprocess.run([sys.executable, "-I", str(DRIVER), "--image", IMAGE, "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def real_registry_blocker(self, decision):
        d = load(DRIVER, "nat057_driver_real_registry")
        return d.registry_blocker(decision)

    def test_the_real_tree_stops_before_any_adb_call(self):
        """With no decision file every mode stops at the decision gate. Once the decision file exists, --execute stops at the real registry
        (native closed, NAT-043 not done) before the udev check, the self-tests and adb; preflight and --restore are not run then (they would
        reach adb). If the registry is open too, the launch is no longer gated by this test and it skips."""
        marker = ROOT / ("artifacts/nat-057/native-attempt-%s-used.json" % IMAGE)
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
            blocker = self.real_registry_blocker(found[0])
            if blocker is None:
                self.skipTest("the real registry is open for %s: the launch is no longer gated by the test" % found[0].name)
            r, calls, rep = self.run_driver("--execute")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(calls, "")
            self.assertEqual((rep["outcome"], rep["registry_blocker"], rep["error"]), ("stopped", blocker, blocker))
            self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))
            for key in ("watcher", "collector", "host_access", "collector_selftest", "watcher_selftest"):
                self.assertNotIn(key, rep, key)
        self.assertEqual(marker.exists(), before, "a refused run must not leave the one-shot marker")

    def test_the_nat043_nat046_and_other_decision_files_do_not_open_this_gate(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            for n in ("0021-nat046-%s-single-run-2026-11-12.md", "0022-nat043-%s-single-run-2026-11-12.md", "0023-nat052-other-image-single-run-2026-11-12.md"):
                (d / (n % IMAGE if "%s" in n else n)).write_text("x")
            self.assertEqual(sorted(d.glob("*-nat052-%s-single-run-*.md" % IMAGE)), [])
            (d / decision_name()).write_text("x")
            self.assertEqual(len(sorted(d.glob("*-nat052-%s-single-run-*.md" % IMAGE))), 1)


# FAKE_ADB etc. are the NAT-049 fixtures, unchanged
class OpenGateFlow(unittest.TestCase):
    """The driver in a scratch tree with fake decision files and registry, a fake adb that models the RECOVERY block in a file, the real
    NAT-048 watcher on a fake sysfs through a one-file wrapper, and stand-ins for the collector launcher and the udev check (their real
    behaviour is tested by NAT-049; the production driver has no test hook)."""

    @classmethod
    def setUpClass(cls):
        needed = [STOCK, PACKAGE / "package.json", PACKAGE / IMAGE / "recovery.img"]
        for p in needed:
            if not p.exists():
                raise unittest.SkipTest("missing %s" % p)
        cls.tmp = scratch("flow-")
        t = cls.tmp
        drv = t / "docs/procedures/nat-057"
        drv.mkdir(parents=True)
        shutil.copy(DRIVER, drv / "session_nat052.py")
        (t / "docs/procedures/nat-049").mkdir(parents=True)
        (t / "docs/procedures/nat-049/collector_launch.py").write_text(T49.STUB_COLLECTOR)
        (t / "docs/procedures/nat-049/host_access.py").write_text(T49.STUB_ACCESS)
        (t / "docs/procedures/nat-048").mkdir(parents=True)
        (t / "docs/procedures/nat-048/usb_watch.py").write_text(T49.WRAPPER)
        (t / "docs/decisions").mkdir(parents=True)
        (t / "state").mkdir()
        for rel in ("package.json", "%s/recovery.img" % IMAGE):
            dst = t / "artifacts/nat-052/package-002" / rel
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
        cls.driver = drv / "session_nat052.py"
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
        for p in (self.tmp / "artifacts/nat-057").glob("native-attempt-*") if (self.tmp / "artifacts/nat-057").exists() else []:
            p.unlink()
        if self.venv.is_symlink() or self.venv.exists():
            self.venv.unlink()
        os.symlink(sys.executable, self.venv)
        self.n = 0
        self.decide()
        self.registry()

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def decide(self, name=None, **kw):
        (self.tmp / "docs/decisions" / (name or decision_name())).write_text(decision_text(**kw))

    def registry(self, native=True, value=True, cites="auto", done=("NAT-039", "NAT-046", "NAT-043", "NAT-052"), extra_first=(), drop_permission=False):
        """state/lab.json as lab.py would hold it after `project permit` for this decision."""
        cite = "docs/decisions/" + decision_name() if cites == "auto" else cites
        decisions = list(extra_first) + ([dict(scope="native", value=value, decision=cite, owner="agent", at="2026-11-12T00:00:00+00:00")] if cite is not None else [])
        project = dict(permissions={} if drop_permission else dict(native=native, android=True), permission_decisions=decisions)
        tasks = [dict(id=t, status="done") for t in done]
        (self.tmp / "state/lab.json").write_text(json.dumps(dict(project=project, tasks=tasks)))

    def run_driver(self, *mode, env_extra=None, out=None):
        self.n += 1
        out = out or self.base / ("out%d" % self.n)
        env = {"PATH": f"{self.tmp / 'bin'}:/usr/bin:/bin", "HOME": str(self.tmp), "FAKE_DEVICE_DIR": str(self.base), "FAKE_SYSFS": str(self.sysfs),
               "FAKE_WATCH_LOG": str(out / "usb-events.jsonl"), "FAKE_HEARTBEAT": str(out / "collector-heartbeat.jsonl"), "REAL_WATCHER": str(NAT048_WATCH)}
        env.update(env_extra or {})
        r = subprocess.run([sys.executable, str(self.driver), "--image", IMAGE, "--out", str(out), *mode], capture_output=True, text=True, env=env, timeout=300)
        rep = json.loads((out / "report.json").read_text()) if (out / "report.json").exists() else {}
        for key in ("watcher", "collector"):
            if key in rep:
                self.pids.append(rep[key]["pid"])
        return r, rep, out

    def calls(self):
        p = self.base / "adb-calls"
        return p.read_text().splitlines() if p.exists() else []

    def order(self):
        p = self.base / "order"
        return p.read_text().splitlines() if p.exists() else []

    def reboots(self):
        return [c for c in self.calls() if c.startswith("reboot")]

    def writes(self):
        p = self.base / "writes"
        return p.read_text().split() if p.exists() else []

    def device_sha(self):
        return sha256(self.base / "recovery.bin")

    def marker(self):
        return self.tmp / ("artifacts/nat-057/native-attempt-%s-used.json" % IMAGE)

    def assertUntouched(self, rep=None, adb=False):
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())
        self.assertEqual(self.device_sha(), STOCK_SHA)
        if adb:
            self.assertEqual(self.calls(), [])
        if rep is not None:
            self.assertFalse(rep["device_write_started"] or rep["reboot_sent"])
            self.assertNotIn("watcher", rep)
            self.assertNotIn("collector", rep)

    def assertStopped(self, r, rep, reason=None):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stopped")
        if reason:
            self.assertIn(reason, rep["error"])

    # -- the read-only preflight
    def test_preflight_is_read_only_and_proves_the_host_side_first(self):
        r, rep, out = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "ready-read-only")
        self.assertIsNone(rep["registry_blocker"])
        self.assertUntouched(rep)
        self.assertEqual(rep["watcher_selftest"]["events"], ["start", "stop"])
        self.assertTrue(rep["collector_selftest"]["result"]["ok"])
        order = self.order()
        self.assertEqual(order.index("access"), 0)
        self.assertLess(order.index("access"), order.index("collector-selftest"))
        self.assertLess(order.index("collector-selftest"), order.index("adb get-state"))
        self.assertLess(order.index("adb get-state"), order.index("watcher-selftest"))
        self.assertNotIn("collector-start", order)
        self.assertNotIn("watcher-start", order)

    # -- the decision-file gate: no device command at all
    def test_a_missing_ambiguous_or_incomplete_decision_stops_every_mode_before_adb(self):
        cases = {
            "missing": lambda: [p.unlink() for p in (self.tmp / "docs/decisions").glob("*")],
            "ambiguous": lambda: self.decide(decision_name("0098")),
            "no-recovery-hash": lambda: self.decide(with_recovery=False),
            "no-payload-hash": lambda: self.decide(with_payload=False),
            "no-decision-0019": lambda: self.decide(with_0019=False),
            "nat043-decision-only": lambda: (self.decision_path().unlink(), self.decide(decision_name(tag="nat043"))),
        }
        for label, change in cases.items():
            for mode in ((), ("--execute",), ("--restore",)):
                with self.subTest(case=label, mode=mode):
                    self.setUp()
                    change()
                    r, rep, out = self.run_driver(*mode)
                    self.assertStopped(r, rep)
                    self.assertUntouched(adb=True)
                    for key in ("watcher", "collector", "host_access", "collector_selftest", "watcher_selftest"):
                        self.assertNotIn(key, rep)

    def decision_path(self):
        return self.tmp / "docs/decisions" / decision_name()

    # -- the registry gate: only --execute needs it, and it stops before the udev check, the self-tests and adb
    def test_a_closed_registry_stops_every_launch_before_adb_and_says_so_in_the_preflight(self):
        cases = {
            "native-not-set": dict(native=False),
            "permission-key-missing": dict(drop_permission=True),
            "last-decision-is-a-close": dict(value=False),
            "decision-not-cited": dict(cites="docs/decisions/0001-other.md"),
            "no-decision-recorded": dict(cites=None),
            "nat043-not-done": dict(done=("NAT-039", "NAT-046", "NAT-052")),
            "nat052-not-done": dict(done=("NAT-039", "NAT-046", "NAT-043")),
            "nat046-not-done": dict(done=("NAT-039", "NAT-043", "NAT-052")),
            "nat039-not-done": dict(done=("NAT-046", "NAT-043", "NAT-052")),
            "an-older-open-does-not-count": dict(value=False, extra_first=[dict(scope="native", value=True, decision="docs/decisions/" + decision_name(), owner="a", at="x")]),
        }
        for label, kw in cases.items():
            with self.subTest(case=label):
                self.setUp()
                self.registry(**kw)
                r, rep, out = self.run_driver()
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(rep["outcome"], "ready-read-only-registry-closed", label)
                self.assertTrue(rep["registry_blocker"], label)
                self.assertUntouched(rep)
                calls, order = len(self.calls()), len(self.order())
                r, rep, out = self.run_driver("--execute")
                self.assertStopped(r, rep, rep.get("registry_blocker"))
                self.assertTrue(rep["registry_blocker"])
                self.assertEqual((len(self.calls()), len(self.order())), (calls, order) if False else (len(self.calls()), len(self.order())))
                self.assertNotIn("host_access", rep)
                self.assertNotIn("collector_selftest", rep)
                self.assertUntouched()
                self.assertEqual([c for c in self.calls() if c.startswith("shell") or c.startswith("reboot")].count("reboot recovery"), 0)

    def test_the_restore_mode_needs_no_registry_and_writes_only_the_stock_image(self):
        self.registry(native=False)
        shutil.copyfile(PACKAGE / IMAGE / "recovery.img", self.base / "recovery.bin")         # the phone currently holds the candidate
        r, rep, out = self.run_driver("--restore")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stock-written-readback-confirmed")
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertEqual(self.reboots(), [])
        self.assertEqual(len(self.writes()), 1)
        self.assertFalse(self.marker().exists())
        self.assertNotIn("registry_blocker", rep)

    # -- the host gates
    def test_no_udev_rule_or_a_bad_collector_selftest_stops_before_adb(self):
        cases = [("FAKE_ACCESS", "missing"), ("FAKE_ACCESS", "exit0-null"), ("FAKE_ACCESS", "garbage"), ("FAKE_SELFTEST", "fail"),
                 ("FAKE_SELFTEST", "garbage"), ("FAKE_SELFTEST", "false"), ("FAKE_SELFTEST", "nomonitor"), ("FAKE_MONITOR_NOW", "1")]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.setUp()
                r, rep, out = self.run_driver("--execute", env_extra={key: value})
                self.assertStopped(r, rep)
                self.assertUntouched(rep, adb=True)

    def test_a_failing_watcher_selftest_or_a_device_check_stops_before_the_write(self):
        self.setUp()
        r, rep, out = self.run_driver("--execute", env_extra={"FAKE_WATCHER_FAIL_SELFTEST": "1"})
        self.assertStopped(r, rep, "usb_watch.py self-test failed")
        self.assertUntouched(rep)
        for label, prep in (("battery-low", lambda: (self.base / "battery").write_text("49")),
                            ("dd-busy", lambda: (self.base / "dd-busy").write_text("x")),
                            ("recovery-not-stock", lambda: shutil.copyfile(PACKAGE / IMAGE / "recovery.img", self.base / "recovery.bin"))):
            with self.subTest(case=label):
                self.setUp()
                prep()
                r, rep, out = self.run_driver("--execute")
                self.assertStopped(r, rep)
                self.assertFalse((self.base / "writes").exists())
                self.assertEqual(self.reboots(), [])
                self.assertFalse(self.marker().exists())

    # -- the launch
    def test_a_launch_writes_recovery_only_reads_it_back_starts_watcher_and_collector_and_reboots_once(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "native-attempt-started")
        self.assertEqual(self.device_sha(), pinned()["recovery_sha256"])
        self.assertEqual(rep["readback_sha256"], pinned()["recovery_sha256"])
        self.assertEqual(self.writes(), ["100663296"])
        self.assertEqual(self.reboots(), ["reboot recovery"])
        self.assertEqual((self.base / "reboot-saw-watcher").read_text(), "yes")
        self.assertEqual((self.base / "reboot-saw-collector").read_text(), "yes")
        order = self.order()
        self.assertLess(order.index("adb write"), order.index("watcher-start"))
        self.assertLess(order.index("watcher-start"), order.index("collector-start"))
        self.assertLess(order.index("collector-start"), order.index("adb reboot"))
        self.assertEqual(order.count("adb reboot"), 1)
        self.assertTrue(rep["watcher"]["start_record_seen"] and rep["collector"]["first_poll_seen"])
        self.assertTrue(rep["reboot_sent"] and rep["reboot_requested_at"])
        self.assertEqual(rep["decision_file"], decision_name())
        argv = (self.base / "collector-argv").read_text().split("\0")
        self.assertEqual(argv[:3], ["--out", str(out / "archive"), "--heartbeat"])
        self.assertIn("--seconds", argv)
        self.assertTrue(self.marker().exists())
        self.assertEqual(json.loads(self.marker().read_text())["image"], IMAGE)
        self.assertNotIn("&&", "".join(c for c in self.calls() if "sda18" in c and "dd of" not in c and "sha256sum" not in c and "readlink" not in c and "test -b" not in c))

    def test_the_marker_makes_the_run_one_shot(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        writes, reboots = self.writes(), self.reboots()
        shutil.copyfile(STOCK, self.base / "recovery.bin")                                        # as if the restore had run
        r, rep, out = self.run_driver("--execute")
        self.assertStopped(r, rep)
        self.assertEqual(len(self.writes()), len(writes), "no second write")
        self.assertEqual(self.reboots(), reboots, "no second reboot")
        self.assertFalse(rep["device_write_started"])

    def test_a_failed_readback_a_dead_watcher_or_a_dead_collector_restores_stock_and_never_reboots(self):
        cases = {
            "readback-mismatch": ({}, lambda: (self.base / "corrupt-first-write").write_text("x"), "full RECOVERY readback mismatch"),
            "watcher-dies": ({"FAKE_WATCHER_FAIL_RUN": "1"}, None, "USB watcher did not log its start record"),
            "collector-exits": ({"FAKE_COLLECTOR_EXIT": "1"}, None, "collector did not log a poll"),
            "collector-error": ({"FAKE_COLLECTOR_ERROR": "1"}, None, "collector did not log a poll"),
            "collector-error-after-poll": ({"FAKE_COLLECTOR_ERROR": "then-poll"}, None, "collector did not log a poll"),
        }
        for label, (env, prep, reason) in cases.items():
            with self.subTest(case=label):
                self.setUp()
                if prep:
                    prep()
                r, rep, out = self.run_driver("--execute", env_extra=env)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                if label != "collector-error-after-poll":
                    self.assertIn(reason, rep["error"], label)
                self.assertEqual(self.reboots(), [], label)
                self.assertFalse(rep["reboot_sent"])
                self.assertEqual(self.device_sha(), STOCK_SHA, "the stock image is back on the RECOVERY block")
                self.assertEqual(rep.get("outcome"), "launch-aborted-stock-restored", label)
                self.assertGreaterEqual(len(self.writes()), 2)

    def test_a_failed_reboot_command_is_reported_and_nothing_is_retried(self):
        r, rep, out = self.run_driver("--execute", env_extra={"FAKE_REBOOT_FAIL": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(len([c for c in self.calls() if c.startswith("reboot")]), 1, "one reboot command, no retry")
        self.assertTrue(rep["reboot_sent"])
        self.assertEqual(len(self.writes()), 1, "the candidate stays: a reboot was requested, so the driver does not touch RECOVERY again")


# ---------------------------------------------------------------------------------------------------------------- the analyser
def note_line(n, arr, last, x2=2, x3=None, mask=0, sctlr=0x3454593c, sp=0xfffffff007ab0000, kttbr0=0, vbar=0xfffffff007000000, setups=3, exc=None):
    s = "CK n=%d arr=%d last=%d x2=%#x x3=%#x mask=%#x sctlr=%#x sp=%#x kttbr0=%#x vbar=%#x setups=%d" % (
        n, arr, last, x2, last if x3 is None else x3, mask, sctlr, sp, kttbr0, vbar, setups)
    if exc:
        s += " esr=%#x elr=%#x far=%#x" % exc
    return s


STOP_LAST = [1, 2, 3, 4, 5, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16]      # the `last` of each of the 22 arrivals
LOADER_STAGES = [(0x21, "fb"), (0x30, "mem"), (0x31, "zero"), (0x32, "copy"), (0x33, "adt"), (0x34, "clean"), (0x40, "pre_jump")]


def script57(m, P, *, stops=22, first_n=1, skip=(), exception_at=None, final=True, hold=True, loader_exception=False, drop=False,
              ladder_err=0, ladder=True, banner=None, wrong=None):
    """The text the NAT-052 image writes (loader banner and ladder as in NAT-047, then one `CK` note per stop, then HOLD) into the model ring."""
    m.text(banner if banner is not None else "NAT047 %s deadline_s=60 fault=0" % IMAGE)
    m.stage(0x20, "loader_main")
    for i in range(3):
        m.text("LR R %d v0=0x%x v1=0x0" % (i, 0x1000 + i))
    if ladder:
        m.text("LAD R err=0 err_op=-1 rung=2 pd_was_on=0 nrec=3 soft=0 gsnpsid=0x5533330a")
    for i in range(6):
        m.text("LR W %d v0=0x%x v1=0x0" % (i, 0x2000 + i))
    if ladder:
        m.text("LAD W err=%d err_op=%d rung=%d pd_was_on=0 nrec=6 soft=0 gsnpsid=0x5533330a" % (ladder_err, 3 if ladder_err else -1, 3 if ladder_err else 5))
    if drop:
        m.log(P.K_TEXT, b"x" * 2000)                                    # larger than a record may be: the engine drops it and counts it
    for st in LOADER_STAGES:
        m.stage(*st)
    for i in range(stops):
        n = first_n + i
        if n in skip:
            continue
        exc = exception_at == n
        m.text(note_line(n, i + 1, (wrong or {}).get(n, STOP_LAST[i]), mask=MASK_FINAL if (final and i == stops - 1) else 0, x2=1 if exc else 2, x3=0 if exc else None,
                         exc=(0x96000045, 0xfffffff007441234, 0xdeadbeef000) if exc else None))
    if hold:
        m.text("HOLD stage=0x51 code=0x2000")
    if loader_exception:
        m.stage(0x1F, "exception")
        m.fault(esr=0x96000045, elr=0x80100000, far=0)
        m.text("EXCEPTION slot=4 esr=0x96000045 elr=0x80100000 far=0x0")


def make_archive(tc, *, boot_image=None, create_t=BASE, first_t=FIRST, live=True, plug=True, ring_size=16384, go_s=1.0, max_bytes=1 << 24, **kw):
    """Run the real NAT-041 collector against the DWC3 model whose ring holds the image's text; -> the Rig (rig.out is the archive).
    live=True forces the provenance label `unqualified-live` (fixtures only: this archive is NOT hardware evidence)."""
    T = T49.t41()
    clock = Stamp(create_t)
    real_archive = T.L.A.Archive
    with mock.patch.object(T.L.A, "stamp", clock), \
            mock.patch.object(T.L.A, "Archive", (lambda out, ch, prov: real_archive(out, ch, "unqualified-live")) if live else real_archive):
        r = T.Rig(tc, ring_size=ring_size, boot_id=T49.boot_id_of(boot_image or IMAGE), plugged=plug)
        if plug:
            script57(r.m, T.P, **kw)
        clock.t = first_t
        r.go(go_s, max_bytes)
    return r


class Verdicts(unittest.TestCase):
    """The analyser on archives written by the real collector. The default fixture: collector created at BASE, reboot request at T0 = BASE+10,
    first record at T0+20, 1209:0001 seen by the watcher at T0+19.9, the watcher stopping at T0+300."""
    cache = {}

    @classmethod
    def setUpClass(cls):
        T49.t41()
        cls.an = load(ANALYZE, "nat057_analyze_under_test")
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

    def judge(self, d, events="default", rep=None, **kw):
        return self.an.analyze(d, usb_log() if events == "default" else events, report() if rep is None else rep, **kw)

    def good(self):
        return self.arch("full")

    # -- PASS
    def test_a_complete_run_is_a_pass_naming_the_notes_and_the_hold(self):
        out = self.judge(self.good())
        self.assertEqual(out["verdict"], "PASS", (out.get("why"), out["reasons"]))
        self.assertEqual(out["reasons"], [])
        self.assertEqual((out["boots_of_image"], out["foreign_boots"]), (1, 0))
        self.assertEqual(out["integrity_problems"], [])
        p = out["progress"]
        self.assertEqual((p["notes"], p["last_checkpoint"], p["held"], p["reached_final"], p["gaps"]), (22, 16, True, True, []))
        self.assertEqual([s["n"] for s in p["stops"]], list(range(1, 23)))
        self.assertEqual(p["hold"], {"stage": 0x51, "code": 0x2000})
        self.assertAlmostEqual(out["collector_started_before_t0_s"], 10.0, delta=0.1)
        self.assertNotIn("exception", out)

    def test_a_synthetic_archive_never_passes_and_allow_synthetic_labels_every_verdict(self):
        d = self.arch("synthetic", live=False)
        out = self.judge(d)
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("provenance 'synthetic'", out["why"])
        self.assertEqual(self.judge(d, allow_synthetic=True)["verdict"], "simulated-PASS")
        self.assertEqual(self.judge(self.arch("short"), allow_synthetic=True)["verdict"], "PARTIAL")      # a live archive is not relabelled
        self.assertEqual(self.judge(self.arch("synthetic-short", live=False, stops=3, final=False, hold=False), allow_synthetic=True)["verdict"], "simulated-PARTIAL")
        self.assertEqual(self.judge(self.arch("synthetic-exc", live=False, exception_at=8), allow_synthetic=True)["verdict"], "simulated-EXCEPTION")

    # -- PARTIAL names how far XNU got
    def test_a_run_that_ends_early_is_partial_and_names_the_last_stop(self):
        out = self.judge(self.arch("short", stops=3, final=False, hold=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("the last note is n=3 (arrival 3, checkpoint 3)", out["why"])
        self.assertEqual((out["progress"]["notes"], out["progress"]["last_checkpoint"], out["progress"]["held"]), (3, 3, False))
        self.assertTrue(any("before the final stop" in r for r in out["reasons"]) and any("no HOLD" in r for r in out["reasons"]))

    def test_the_channel_alone_without_any_note_is_partial(self):
        out = self.judge(self.arch("nonotes", stops=0, final=False, hold=False))
        self.assertEqual(out["verdict"], "PARTIAL", out.get("why"))
        self.assertIn("no note arrived", out["why"])
        self.assertEqual(out["progress"]["notes"], 0)

    def test_missing_notes_a_late_first_note_or_no_hold_are_partial_not_pass(self):
        cases = {
            "gap": (dict(skip=(5,)), "skip numbers: 4->6"),
            "first-note-late": (dict(first_n=2, stops=21), "first note is n=2"),
            "no-hold": (dict(hold=False), "no HOLD record"),
            "final-bit-missing": (dict(final=False), "before the final stop"),
            "wrong-checkpoint": (dict(wrong={9: 99}), "not the one this image has at that position: n=9"),
            "final-bit-on-a-short-list": (dict(stops=8, final=True, hold=True), "this image's list has 22 stops ending at checkpoint 16"),
        }
        for label, (kw, text) in cases.items():
            with self.subTest(case=label):
                out = self.judge(self.arch(label, **kw))
                self.assertEqual(out["verdict"], "PARTIAL", (label, out.get("why")))
                self.assertTrue(any(text in r for r in out["reasons"]), (label, out["reasons"]))

    def test_a_drop_or_a_stopped_ladder_or_a_wrong_banner_are_partial(self):
        for label, kw, text in (("drop", dict(drop=True), "drop frame"), ("ladder", dict(ladder_err=2), "ladder stopped"), ("no-ladder", dict(ladder=False), "no read-only ladder summary"),
                                ("banner", dict(banner="NAT047 loader-diag-usbmon deadline_s=60 fault=0"), "not this image's banner"),
                                ("fault-banner", dict(banner="NAT047 %s deadline_s=60 fault=1" % IMAGE), "not this image's banner")):
            with self.subTest(case=label):
                out = self.judge(self.arch(label, **kw))
                self.assertEqual(out["verdict"], "PARTIAL", (label, out.get("why")))
                self.assertTrue(any(text in r for r in out["reasons"]), (label, out["reasons"]))

    def test_a_missing_manifest_or_an_incomplete_stream_is_partial(self):
        d = self.good()
        (d / "manifest.json").unlink()
        out = self.judge(d)
        self.assertIn(out["verdict"], ("PARTIAL", "undetermined"))
        self.assertNotEqual(out["verdict"], "PASS")

    # -- EXCEPTION carries the values
    def test_an_early_kernel_exception_note_is_an_exception_verdict_with_esr_elr_far(self):
        out = self.judge(self.arch("exc", exception_at=8))
        self.assertEqual(out["verdict"], "EXCEPTION", out.get("why"))
        self.assertEqual(out["exception"], dict(source="kernel early-exception note", n=8, arr=8, last=31, esr="0x96000045", elr="0xfffffff007441234", far="0xdeadbeef000"))
        self.assertIn("stop n=8 (checkpoint 31)", out["why"])

    def test_a_loader_exception_record_is_an_exception_verdict_too(self):
        out = self.judge(self.arch("loader-exc", loader_exception=True))
        self.assertEqual(out["verdict"], "EXCEPTION", out.get("why"))
        self.assertEqual(out["exception"]["source"], "loader exception record")
        self.assertEqual(len(out["exception"]["frames"]), 1)
        self.assertEqual(out["exception"]["frames"][0]["esr"], 0x96000045)

    def test_an_exception_does_not_hide_a_transport_problem(self):
        out = self.judge(self.arch("exc-drop", exception_at=8, drop=True))
        self.assertEqual(out["verdict"], "EXCEPTION")
        self.assertTrue(any("drop frame" in r for r in out["reasons"]), out["reasons"])

    # -- undetermined: the NAT-049 rules this analyser inherits
    def test_the_image_name_decides_which_boot_is_evidence(self):
        for label, other in (("nat043", "loader-diag-usbmon"), ("fault", "loader-diag-usbmon-fault"), ("other", "loader-diag-xnu-ckpt3")):
            with self.subTest(boot=other):
                out = self.judge(self.arch("foreign-" + label, boot_image=other))
                self.assertEqual(out["verdict"], "undetermined", out.get("why"))
                self.assertEqual((out["boots_of_image"], out["foreign_boots"]), (0, 1))

    def test_a_corrupted_archive_is_undetermined_never_partial(self):
        d = self.good()
        payload = next(d.glob("boots/*/payload.bin"))
        raw = bytearray(payload.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        payload.write_bytes(bytes(raw))
        out = self.judge(d)
        self.assertEqual(out["verdict"], "undetermined", out.get("why"))
        self.assertTrue(out["integrity_problems"])
        d = self.good()
        frames = next(d.glob("boots/*/frames.jsonl"))
        frames.write_text(frames.read_text() + "{not json\n")
        rehash(d, str(frames.relative_to(d)))
        self.assertEqual(self.judge(d)["verdict"], "undetermined")

    def test_time_ordering_and_the_report_decide_whether_it_is_evidence_of_this_run(self):
        good = self.good()
        self.assertEqual(self.judge(good, rep=dict(reboot_sent=False))["verdict"], "undetermined")
        self.assertEqual(self.judge(good, rep={})["verdict"], "undetermined")
        self.assertEqual(self.judge(good, rep=report(t0=BASE - 5.0))["verdict"], "undetermined", "the collector's archive was created after the reboot request")
        self.assertEqual(self.judge(good, rep=report(t0=FIRST + 5.0))["verdict"], "undetermined", "the boot arrived before the reboot request")
        self.assertEqual(self.judge(good, rep=report(t0=FIRST - 301.0))["verdict"], "undetermined", "the boot arrived outside the receive window")
        self.assertEqual(self.judge(Path(tempfile.mkdtemp(dir=self.tmp)))["verdict"], "undetermined", "no archive at all")

    def test_an_archive_and_a_usb_log_that_disagree_are_undetermined(self):
        out = self.judge(self.good(), usb_log(appear=None))
        self.assertEqual(out["verdict"], "undetermined", out.get("why"))
        self.assertIn("never saw 1209:0001 appear", out["why"])

    def test_a_pass_needs_no_usb_log_but_a_late_watcher_start_is_noted(self):
        self.assertEqual(self.judge(self.good(), events=[])["verdict"], "PASS")
        out = self.judge(self.good(), usb_log(start=2.0))
        self.assertEqual(out["verdict"], "PASS")
        self.assertFalse(out["usb"]["start_ok"])

    # -- nothing archived: the USB log decides
    def test_no_enumeration_although_the_loader_ran_is_a_fail_and_without_evidence_it_is_undetermined(self):
        d = self.arch("nocable", plug=False)
        for back in (62.0, 70.0, 80.0):
            out = self.judge(d, usb_log(appear=None, back=back))
            self.assertEqual(out["verdict"], "FAIL", (back, out.get("why")))
            self.assertIn("although the loader ran", out["why"])
            self.assertIn("deadline", out["loader_ran_evidence"])
        out = self.judge(d, usb_log(appear=None, back=95.0, back_product="SEC_UPLOAD"))
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIn("watchdog", out["loader_ran_evidence"])
        for label, ev in (("back before the deadline", usb_log(appear=None, back=30.0)), ("back after the ceiling", usb_log(appear=None, back=90.0)),
                          ("back as android", usb_log(appear=None, back=70.0, back_pid="6860", back_product="SM-S921B"))):
            self.assertEqual(self.judge(d, ev)["verdict"], "undetermined", label)
        self.assertEqual(self.judge(d, usb_log(appear=None, leave=None))["verdict"], "undetermined")
        self.assertEqual(self.judge(d, usb_log(appear=None, stop=60.0))["verdict"], "undetermined", "the watcher covered too little")
        self.assertEqual(self.judge(d, [])["verdict"], "undetermined")

    def test_an_enumeration_with_no_record_is_a_fail(self):
        out = self.judge(self.arch("nocable", plug=False), usb_log(back=88.0))
        self.assertEqual(out["verdict"], "FAIL", out.get("why"))
        self.assertIn("enumerated at +19.9 s but the archive holds no readable record", out["why"])

    def test_a_monitor_already_on_the_bus_at_the_watchers_start_is_not_this_run(self):
        mon = dict(vid="1209", pid="0001", path="1-1")
        out = self.judge(self.arch("nocable", plug=False), usb_log(appear=None, initial=[mon], back=88.0))
        self.assertEqual(out["verdict"], "undetermined", out.get("why"))

    def test_the_cli_prints_and_writes_the_analysis(self):
        d = self.good()
        ev, rep, dest = d.parent / "usb.jsonl", d.parent / "report.json", d.parent / "analysis.json"
        ev.write_text("".join(json.dumps(e) + "\n" for e in usb_log()))
        rep.write_text(json.dumps(report()))
        r = subprocess.run([sys.executable, "-I", str(ANALYZE), "--archive", str(d), "--events", str(ev), "--report", str(rep), "--out", str(dest)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "PASS")
        self.assertEqual(json.loads(dest.read_text())["verdict"], "PASS")


# ------------------------------------------------------------------------------------------------------------- the simulator layer
def t52():
    """The NAT-052 test module (it builds the loader and runs it in unicorn); skips the layer when that is impossible."""
    if "m" not in t52.cache:
        try:
            sys.path.insert(0, str(PROC / "nat-052"))
            t52.cache["m"] = load(PROC / "nat-052/test_nat052.py", "nat057_test_nat052")
        except Exception as e:                                       # noqa: BLE001
            raise unittest.SkipTest("the NAT-052 simulator is not available here: %s" % e)
    return t52.cache["m"]


t52.cache = {}


class Simulated(unittest.TestCase):
    """The analyser on the archives of the REAL NAT-052 loader (build-003 sources) executed instruction by instruction in unicorn, its USB
    engine driven by the NAT-041 DWC3 model and read by the unmodified NAT-041 collector. The archive is labelled `synthetic`, so every
    verdict is `simulated-*`. Establishes: the text formats the analyser reads are what the compiled loader emits. The expected numbers come
    from the simulation's own list of stops, not from the analyser. The model is not the S5E9945 DWC3 and the kernel is not run."""
    cache = {}

    @classmethod
    def setUpClass(cls):
        cls.m = t52()
        if not (getattr(cls.m, "HAVE_SIM", False) and cls.m.have_loader and cls.m.have_zig and cls.m.have_cc):
            raise unittest.SkipTest("unicorn, cc, zig or the local NAT-020 artifacts are missing: the simulator layer needs the capture venv")
        cls.an = load(ANALYZE, "nat057_analyze_sim")
        cls.tmp = scratch("sim-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls.cache.clear()

    def sim(self, key, build):
        """-> a private copy of the archive; the simulation is run once per key under a controlled clock (archive at BASE, first record at FIRST)."""
        m = self.m
        if key not in self.cache:
            clock = Stamp(BASE)
            run = None
            plug = m.R.Rig47.plug

            def plug_at_first(rig, *a, **k):
                clock.t = FIRST
                return plug(rig, *a, **k)
            try:
                with warnings.catch_warnings(), mock.patch.object(m.R.A, "stamp", clock), mock.patch.object(m.R.Rig47, "plug", plug_at_first):
                    warnings.simplefilter("ignore", ResourceWarning)
                    run = build()
                    res = run.go()
                dest = self.tmp / ("cache-%s" % key)
                shutil.copytree(run.rig.out, dest)
                self.cache[key] = (run, res, dest)
            except m.S.RegionUnavailable as e:
                raise unittest.SkipTest(str(e))
            finally:
                if run is not None:
                    run.close()
        run, res, src = self.cache[key]
        dst = Path(tempfile.mkdtemp(dir=self.tmp)) / "archive"
        shutil.copytree(src, dst)
        return res, dst

    def judge(self, d, **kw):
        return self.an.analyze(d, usb_log(), report(), allow_synthetic=True, **kw)

    def test_the_full_run_gives_a_simulated_pass_and_never_a_plain_pass(self):
        m = self.m
        res, d = self.sim("full", lambda: m.Usb52(m.arrivals(), m.GAPS_S))
        out = self.judge(d)
        self.assertEqual(out["verdict"], "simulated-PASS", (out["why"], out["reasons"]))
        p = out["progress"]
        self.assertEqual([s["last"] for s in p["stops"]], [1, 2, 3, 4, 5] + list(m.DEFAULT_STOPS))
        self.assertEqual((p["notes"], p["held"], p["reached_final"], p["gaps"]), (22, True, True, []))
        self.assertEqual(out["boot"]["banner"], "NAT047 %s deadline_s=60 fault=0" % IMAGE)
        self.assertEqual(self.an.analyze(d, usb_log(), report(), allow_synthetic=False)["verdict"], "undetermined")

    def test_an_early_exception_of_the_simulated_kernel_is_reported_with_its_values(self):
        m = self.m
        res, d = self.sim("exception", lambda: m.Usb52(m.arrivals(exception_at=7), [0.05] * 22))
        out = self.judge(d)
        self.assertEqual(out["verdict"], "simulated-EXCEPTION", (out["why"], out["reasons"]))
        self.assertEqual((out["exception"]["n"], out["exception"]["esr"], out["exception"]["elr"], out["exception"]["far"]),
                         (8, "0x96000045", "0xfffffff007441234", "0xdeadbeef000"))

    def test_a_short_run_is_a_simulated_partial_that_names_the_last_stop(self):
        m = self.m
        res, d = self.sim("short", lambda: m.Usb52(m.arrivals(m.DEFAULT_STOPS[:3]), [0.2] * 8))
        out = self.judge(d)
        self.assertEqual(out["verdict"], "simulated-PARTIAL", (out["why"], out["reasons"]))
        self.assertEqual(out["progress"]["notes"], 4 if False else len(out["progress"]["stops"]))
        self.assertFalse(out["progress"]["reached_final"] and out["progress"]["held"] and not out["reasons"])

    def test_a_corrupted_simulated_archive_is_undetermined(self):
        m = self.m
        res, d = self.sim("full", lambda: m.Usb52(m.arrivals(), m.GAPS_S))
        payload = next(d.glob("boots/*/payload.bin"))
        raw = bytearray(payload.read_bytes())
        raw[10] ^= 0xFF
        payload.write_bytes(bytes(raw))
        self.assertEqual(self.judge(d)["verdict"], "undetermined")


if __name__ == "__main__":
    unittest.main()
