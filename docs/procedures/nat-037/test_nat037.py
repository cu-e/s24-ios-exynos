#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-037 host tests: the gated session driver of the loader-diag-xnu-ckpt3 image (session_xnu_ckpt3.py, decision 0018).
Evidence kind: host-test. Nothing here talks to a phone: `adb` is a fake that records its calls.

Two layers:
  * the real tree: with no owner decision file the driver stops before the first adb call in every mode, after checking
    its pinned hashes; its pinned hashes are those of the NAT-036 package; it differs from the run-009 driver (NAT-034)
    only in the pinned names and the docstring; it never creates the decision file.
  * a scratch tree that holds the driver, the real (read-only symlinked) candidate and stock images, a fake decision file
    and a fake `adb` that models a device's RECOVERY block in a file. It checks the open-gate flow: the read-only
    preflight writes nothing; --execute writes the candidate, reads it back in full, sends exactly one `reboot recovery`
    and leaves the one-shot marker (a second --execute refuses before any write); a readback mismatch restores the stock
    image and never reboots; --restore writes stock and never reboots; a device whose RECOVERY is not stock is refused.
The fake is not the phone: what these tests establish is the driver's own control flow, not any device behaviour."""
import json, os, re, shutil, stat, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DRIVER = Path(os.environ["NAT037_DRIVER"]) if os.environ.get("NAT037_DRIVER") else HERE / "session_xnu_ckpt3.py"     # a mutated copy for the mutation checks
PREVIOUS = ROOT / "docs/procedures/nat-022/session_xnu_ckpt2.py"
DECISION_NAME = "0018-nat036-loader-diag-xnu-ckpt3-single-run-2026-11-11.md"
DECISION = ROOT / "docs/decisions" / DECISION_NAME
PACKAGE = ROOT / "artifacts/nat-036/package-001"
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
PAYLOAD = ROOT / "artifacts/nat-036/build-001/loader-diag-xnu-ckpt3/Image.payload"
MARKER = ROOT / "artifacts/nat-022/native-attempt-xnuckpt3-used.json"

FAKE_ADB = r'''#!{python}
import hashlib, os, sys
from pathlib import Path
base = Path(os.environ["FAKE_DEVICE_DIR"])
dev = base / "recovery.bin"
with (base / "adb-calls").open("a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args == ["get-state"]:
    print("device")
elif args == ["reboot", "recovery"]:
    pass
elif args[:2] == ["shell", "-T"]:
    cmd = args[2]
    props = {"ro.product.model": "SM-S921B", "ro.product.device": "e1s", "ro.build.PDA": "S921BXXS9BYH3", "sys.boot_completed": "1"}
    if cmd.startswith("getprop "):
        print(props[cmd.split()[1]])
    elif "readlink -f" in cmd:
        print("/dev/block/sda18\n100663296\nblock_device")
    elif "pidof dd" in cmd:
        print("busy" if (base / "dd-busy").exists() else "idle")
    elif "sha256sum /dev/block/sda18" in cmd:
        print(hashlib.sha256(dev.read_bytes()).hexdigest() + "  /dev/block/sda18")
    elif cmd.startswith("dumpsys battery"):
        print("level=%s\ntemperature=300" % (base / "battery").read_text().strip() if (base / "battery").exists() else "level=80\ntemperature=300")
    elif "dd of=/dev/block/sda18" in cmd:
        data = sys.stdin.buffer.read()
        n = (base / "writes").read_text().count("\n") if (base / "writes").exists() else 0
        with (base / "writes").open("a") as w:
            w.write("%d\n" % len(data))
        if (base / "corrupt-first-write").exists() and n == 0:
            data = bytes([data[0] ^ 1]) + data[1:]
        dev.write_bytes(data)
    else:
        sys.stderr.write("fake adb: unexpected shell command: %s\n" % cmd)
        sys.exit(1)
else:
    sys.stderr.write("fake adb: unexpected arguments: %s\n" % args)
    sys.exit(1)
'''


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def docstring_split(text):
    """(docstring, the rest) of a script whose docstring is the first triple-quoted string."""
    m = re.search(r'"""(.*?)"""', text, re.S)
    return m.group(1), text[:m.start()] + text[m.end():]


class RealTreeGate(unittest.TestCase):
    """The gated driver in the real tree: with no owner decision file it stops before any adb call, in every mode."""

    def run_driver(self, *mode):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "bin").mkdir()
            fake = t / "bin/adb"
            fake.write_text("#!/bin/sh\necho \"$@\" >> %s\nexit 1\n" % (t / "adb-calls"))
            fake.chmod(0o755)
            env = {"PATH": f"{t / 'bin'}:/usr/bin:/bin", "HOME": str(t)}
            r = subprocess.run([sys.executable, str(DRIVER), "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def test_no_decision_no_adb_in_any_mode(self):
        if DECISION.exists():
            self.skipTest("the owner decision exists: the gate is open")
        marker_before = MARKER.exists()
        for mode in ((), ("--execute",), ("--restore",)):
            r, calls, rep = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(calls, "", mode)
            self.assertEqual(rep["outcome"], "stopped")
            self.assertIn("owner decision 0018 is missing", rep["error"])
            self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))
        self.assertEqual(MARKER.exists(), marker_before, "a refused run must not leave the one-shot marker")

    def test_pinned_hashes_are_those_of_the_package(self):
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        for key, expected in (("recovery_sha256", "NEW_SHA"), ("source_image_sha256", "CANARY_SHA"), ("stock_sha256", "STOCK_SHA")):
            self.assertRegex(src, r"(?m)^%s='%s'" % (expected, pkg[key]))
        self.assertRegex(src, r"(?m)^CANDIDATE=ROOT/'artifacts/nat-036/package-001/recovery\.img'")
        self.assertTrue(pkg["flashed"] is False and pkg["size"] == 100663296)
        if PAYLOAD.exists():
            self.assertIn("CANARY_LEN=%d\n" % PAYLOAD.stat().st_size, src)
            self.assertEqual(sha256(PAYLOAD), pkg["source_image_sha256"])

    def test_the_package_image_is_the_pinned_one_and_carries_the_payload_verbatim(self):
        pkg = json.loads((PACKAGE / "package.json").read_text())
        if not (PACKAGE / "recovery.img").exists():
            self.skipTest("package-001 is not present")
        img = (PACKAGE / "recovery.img").read_bytes()
        import hashlib
        self.assertEqual(hashlib.sha256(img).hexdigest(), pkg["recovery_sha256"])
        if PAYLOAD.exists():
            payload = PAYLOAD.read_bytes()
            self.assertEqual(img[2048:2048 + len(payload)], payload)

    def test_reboot_and_flash_surface(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("reboot','recovery'"), 1)
        self.assertEqual(len(re.findall(r"'reboot'", src)), 1, "no other reboot form (reboot bootloader/download, a plain reboot)")
        self.assertNotIn("fastboot", src.lower())
        self.assertNotIn("bootloader", src)
        # odin4/heimdall appear only as process names in the "another flasher is active" guard, never as a command
        self.assertEqual(len(re.findall(r"odin|heimdall", src)), 2)
        self.assertIn("['odin4','heimdall']", src)
        # the only block device the driver names is RECOVERY
        self.assertEqual(sorted(set(re.findall(r"/dev/block/[\w/.-]+", src))), ["/dev/block/by-name/recovery", "/dev/block/sda18"])

    def test_the_driver_never_creates_the_decision_file(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("docs/decisions"), 1)
        self.assertRegex(src, r"assert \(ROOT/'docs/decisions/%s'\)\.exists\(\)" % re.escape(DECISION_NAME))
        self.assertNotRegex(src, r"decisions[^\n]*(write_text|write_bytes|open\()")
        self.assertIn("marker.open('x')", src)

    def test_the_driver_differs_from_the_run_009_driver_only_in_pinned_names_and_the_docstring(self):
        old_doc, old = docstring_split(PREVIOUS.read_text())
        new_doc, new = docstring_split(DRIVER.read_text())
        old_lines, new_lines = old.splitlines(), new.splitlines()
        self.assertEqual(len(old_lines), len(new_lines))
        differing = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
        allowed = ("CANDIDATE=", "NEW_SHA=", "CANARY_SHA=", "CANARY_LEN=", "            assert (ROOT/'docs/decisions/", "            marker=ROOT/'artifacts/nat-022/native-attempt-")
        for a, b in differing:
            self.assertTrue(a.startswith(allowed) and b.startswith(allowed), (a, b))
        self.assertEqual([a.split("=")[0].strip().split("(")[0] for a, b in differing][:3], ["CANDIDATE", "NEW_SHA", "CANARY_SHA"])
        # the three behavioural lines (CANARY_LEN may be unchanged between two images)
        self.assertGreaterEqual(len(differing), 5)
        # no run-009 name left in the live code of the new driver
        self.assertNotRegex(new, r"nat-034|ckpt2|0017")
        self.assertIn("0018", new_doc + new)
        self.assertIn("loader-diag-xnu-ckpt3", new_doc)


class OpenGateFlow(unittest.TestCase):
    """The driver in a scratch tree with a fake decision file and a fake adb that models the RECOVERY block in a file."""

    @classmethod
    def setUpClass(cls):
        for p in (PACKAGE / "recovery.img", PACKAGE / "package.json", STOCK):
            if not p.exists():
                raise unittest.SkipTest("missing %s" % p)
        cls.tmp = Path(tempfile.mkdtemp(prefix="nat037-"))
        t = cls.tmp
        drv = t / "docs/procedures/nat-037"
        drv.mkdir(parents=True)
        shutil.copy(DRIVER, drv / "session_xnu_ckpt3.py")
        (t / "docs/decisions").mkdir(parents=True)
        (t / "artifacts/nat-036/package-001").mkdir(parents=True)
        for name in ("recovery.img", "package.json"):
            os.symlink(PACKAGE / name, t / "artifacts/nat-036/package-001" / name)
        (t / "devices/recovery/backups/2026-11-10").mkdir(parents=True)
        os.symlink(STOCK, t / "devices/recovery/backups/2026-11-10/recovery.img")
        (t / "bin").mkdir()
        adb = t / "bin/adb"
        adb.write_text(FAKE_ADB.replace("{python}", sys.executable))
        adb.chmod(0o755)
        cls.driver = drv / "session_xnu_ckpt3.py"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="dev-", dir=self.tmp))
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        self.decision = self.tmp / "docs/decisions" / DECISION_NAME
        self.decision.write_text("test decision (scratch tree only)\n")
        for p in (self.tmp / "artifacts/nat-022").glob("native-attempt-*"):
            p.unlink()
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def run_driver(self, *mode):
        self.n += 1
        env = {"PATH": f"{self.tmp / 'bin'}:/usr/bin:/bin", "HOME": str(self.tmp), "FAKE_DEVICE_DIR": str(self.base)}
        out = self.base / ("out%d" % self.n)
        r = subprocess.run([sys.executable, str(self.driver), "--out", str(out), *mode], capture_output=True, text=True, env=env, timeout=300)
        return r, json.loads((out / "report.json").read_text())

    def calls(self):
        p = self.base / "adb-calls"
        return p.read_text().splitlines() if p.exists() else []

    def reboots(self):
        return [c for c in self.calls() if c.startswith("reboot")]

    def device_sha(self):
        return sha256(self.base / "recovery.bin")

    def marker(self):
        return self.tmp / "artifacts/nat-022/native-attempt-xnuckpt3-used.json"

    def test_preflight_is_read_only(self):
        r, rep = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "ready-read-only")
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["device_write_started"] or rep["reboot_sent"])
        self.assertFalse(self.marker().exists())
        self.assertEqual(self.device_sha(), "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")

    def test_execute_writes_the_candidate_reads_it_back_and_reboots_once(self):
        r, rep = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "native-attempt-started")
        self.assertEqual(self.device_sha(), "c61165cb0264388098705deea0421e12d77f612791c3b2d579e46bf40abd4f0b")
        self.assertEqual(rep["readback_sha256"], self.device_sha())
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296"])
        self.assertEqual(self.reboots(), ["reboot recovery"])
        calls = self.calls()
        # the order: the write, then its readback, then the reboot, last
        write = next(i for i, c in enumerate(calls) if c.startswith("shell -T") and "dd of=" in c)
        readback = max(i for i, c in enumerate(calls) if "sha256sum /dev/block/sda18" in c)
        self.assertLess(write, readback)
        self.assertLess(readback, calls.index("reboot recovery"))
        self.assertEqual(calls[-1], "reboot recovery")
        self.assertTrue(rep["reboot_sent"] and rep["device_write_started"])
        self.assertTrue(self.marker().exists())
        self.assertEqual(json.loads(self.marker().read_text())["image_sha256"], "c61165cb0264388098705deea0421e12d77f612791c3b2d579e46bf40abd4f0b")

    def test_a_second_execute_is_refused_by_the_marker_before_any_write(self):
        r, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # a second launch on a device that was restored to stock in the meantime
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        (self.base / "writes").unlink()
        r, rep = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stopped")
        self.assertFalse(rep["device_write_started"] or rep["reboot_sent"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), ["reboot recovery"], "exactly one reboot over both sessions")

    def test_a_readback_mismatch_restores_stock_and_never_reboots(self):
        (self.base / "corrupt-first-write").write_text("")
        r, rep = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("readback mismatch", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["reboot_sent"])
        self.assertEqual(self.device_sha(), "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296", "100663296"])

    def test_a_busy_remote_dd_blocks_every_write(self):
        (self.base / "dd-busy").write_text("")
        for mode in ((), ("--execute",), ("--restore",)):
            r, rep = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, (mode, r.stdout, r.stderr))
            self.assertFalse((self.base / "writes").exists(), mode)
            self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_restore_writes_stock_without_a_reboot(self):
        r, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.device_sha(), "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")
        r, rep = self.run_driver("--restore")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stock-written-readback-confirmed")
        self.assertEqual(self.device_sha(), "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")
        self.assertEqual(self.reboots(), ["reboot recovery"], "only the launch rebooted")
        self.assertFalse(rep["reboot_sent"])

    def test_launch_refuses_a_recovery_that_is_not_stock(self):
        data = bytearray((STOCK).read_bytes())
        data[100] ^= 0xFF
        (self.base / "recovery.bin").write_bytes(bytes(data))
        r, rep = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unchanged stock RECOVERY", rep["error"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_launch_refuses_a_low_battery(self):
        (self.base / "battery").write_text("49")
        r, rep = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())


if __name__ == "__main__":
    unittest.main()
