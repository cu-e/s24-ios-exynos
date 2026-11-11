#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-049 host tests: the udev access check (host_access.py), the collector launcher (collector_launch.py), the NAT-043 verdict
analyzer (analyze_usblog.py) and the gated session driver (session_usblog.py). Evidence kind: host-test. Nothing here talks to a
phone: `adb` is a fake that records its calls, the USB bus is a directory tree of fake sysfs attributes or a fake `usb.core`, and the
"phone" behind the collector is the NAT-041 DWC3 model (or, in the optional simulator layer, the NAT-047 loader run in unicorn).

Layers:
  * HostAccess: the udev-rule reading (what grants access to 1209:0001 and what does not), the shipped rule, no side effects.
  * Launcher: the heartbeat wrapper around the collector's pyusb backend (cadence, found-count changes, errors, exclusive create,
    fsync per record), the self-test with a fake pyusb, and the real collector end to end with a fake `usb.core` (only 1209:0001
    is looked for, provenance unqualified-live, nothing written when no device appears).
  * Analyzer: archives made by the real NAT-041 collector from the NAT-041 DWC3 model, with the NAT-047 loader's text formats
    scripted into the model's ring; a table of scenarios whose verdicts are fixed by nat-047/decision-template.md (the provenance
    label is forced to unqualified-live inside the fixtures only to exercise the PASS path: it is not hardware evidence), refusal
    of synthetic provenance, corrupted archives, time ordering, disagreement between archive and USB log. The optional simulator
    layer judges the archives of the real NAT-047 loader built and run in unicorn.
  * RealTreeGate: in the real tree, without the agent-written decision file, the driver stops before the first adb call in every
    mode and for both images; its pinned hashes are those of NAT-047 package-001; its safety lines are those of the NAT-048
    driver; it never creates the decision file; the collector starts before the reboot.
  * OpenGateFlow: the driver in a scratch tree with a fake decision file, a fake registry, a fake adb that models the RECOVERY
    block in a file, the real watcher on a fake sysfs and a stand-in collector launcher: the read-only preflight writes nothing;
    --execute writes, reads back in full, starts the watcher AND the collector BEFORE the single reboot (the fake adb checks both
    logs at the moment of the reboot), leaves both detached; every gate and every failure path never reboots.
The fakes are not the phone: what these tests establish is control flow and the verdict rules, not device behaviour."""
import copy, datetime, difflib, fcntl, hashlib, importlib.util, json, os, re, shutil, signal, subprocess, sys, tempfile, time, types, unittest, warnings
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
DRIVER = Path(os.environ.get("NAT049_DRIVER") or HERE / "session_usblog.py")          # mutated copies for the mutation checks
ANALYZE = Path(os.environ.get("NAT049_ANALYZE") or HERE / "analyze_usblog.py")
LAUNCH = Path(os.environ.get("NAT049_LAUNCH") or HERE / "collector_launch.py")
ACCESS = Path(os.environ.get("NAT049_ACCESS") or HERE / "host_access.py")
RULE = HERE / "70-s24-usbmon.rules"
NAT048_DRIVER = PROC / "nat-048/session_reset_canary.py"
NAT048_WATCH = PROC / "nat-048/usb_watch.py"
PACKAGE = ROOT / "artifacts/nat-047/package-001"
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
STOCK_SHA = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
PLAIN, FAULT = "loader-diag-usbmon", "loader-diag-usbmon-fault"
IMAGES = (PLAIN, FAULT)
FAULT_ESR = 0xF2001234


# Tests that read the driver's SOURCE TEXT (pinned lines, ordering of statements, diff against the NAT-048 driver). The mutation runner
# runs the driver mutants once without them (NAT049_BEHAVIOUR_ONLY=1) to show which mutants only the text pins can see.
source_pin = unittest.skipIf(os.environ.get("NAT049_BEHAVIOUR_ONLY") == "1", "source-text pin (skipped in the behavioural mutation pass)")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


# ------------------------------------------------------------------------------------------------------------------ host access
class HostAccess(unittest.TestCase):
    USER, GROUPS = "egor", {"egor", "adbusers", "wheel"}

    @classmethod
    def setUpClass(cls):
        cls.m = load(ACCESS, "nat049_host_access_under_test")

    def grants(self, line, user=None, groups=None):
        return self.m.grants(line, user or self.USER, self.GROUPS if groups is None else groups)

    def rules_dir(self, **files):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for name, text in files.items():
            (Path(d.name) / (name + ".rules")).write_text(text)
        return d.name

    def test_the_shipped_rule_gives_a_member_of_adbusers_access_and_nobody_else(self):
        line = [l for l in self.m.logical_lines(RULE.read_text())]
        self.assertEqual(len(line), 1, "exactly one active rule")
        self.assertIsNotNone(self.grants(line[0]))
        self.assertIsNone(self.grants(line[0], groups={"egor", "wheel"}), "a user outside adbusers gets nothing")
        self.assertIn('ATTR{idVendor}=="1209"', line[0])
        self.assertIn('ATTR{idProduct}=="0001"', line[0])
        self.assertNotRegex(line[0], r"04e8|18d1", "the phone's own identities are not opened to the monitor tools")

    def test_a_world_writable_mode_grants_every_user(self):
        self.assertIsNotNone(self.grants('ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"', groups=set()))

    def test_the_group_bit_needs_write_and_a_group_the_user_is_in(self):
        base = 'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="%s", GROUP="%s"'
        self.assertIsNotNone(self.grants(base % ("0660", "adbusers")))
        self.assertIsNone(self.grants(base % ("0640", "adbusers")), "read-only for the group is not enough for control transfers")
        self.assertIsNone(self.grants(base % ("0660", "plugdev")), "the user is not in plugdev")
        self.assertIsNone(self.grants('ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0660"'), "a group mode with no GROUP names nobody")

    def test_owner_write_needs_owner_to_be_the_user(self):
        base = 'ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0600", OWNER="%s"'
        self.assertIsNotNone(self.grants(base % "egor"))
        self.assertIsNone(self.grants(base % "root"))

    def test_uaccess_grants(self):
        self.assertEqual(self.grants('SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", TAG+="uaccess"'), "uaccess")

    def test_other_identities_and_negated_matches_grant_nothing(self):
        for line in ('ATTR{idVendor}=="1209", ATTR{idProduct}=="0002", MODE="0666"',
                     'ATTR{idVendor}=="1208", ATTR{idProduct}=="0001", MODE="0666"',
                     'ATTR{idVendor}!="1209", ATTR{idProduct}=="0001", MODE="0666"',
                     'ATTR{idVendor}=="1209", MODE="0666"',
                     'ATTR{idProduct}=="0001", MODE="0666"',
                     'SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666", GROUP="adbusers", TAG+="uaccess"',
                     'SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666"',
                     'ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0444"'):
            self.assertIsNone(self.grants(line), line)

    def test_attribute_spelling_and_case(self):
        self.assertIsNotNone(self.grants('ATTRS{idVendor}=="1209", ATTRS{idProduct}=="0001", MODE="0666"'))
        self.assertIsNotNone(self.grants('ATTR{IDVENDOR}=="1209", ATTR{idproduct}=="0001", MODE="0666"'))
        self.assertIsNotNone(self.grants('ENV{ID_VENDOR_ID}=="x", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"'))

    def test_comments_and_continuations(self):
        text = '# SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"\n' \
               'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", \\\n   ATTR{idProduct}=="0001", MODE="0666"\n\n'
        lines = self.m.logical_lines(text)
        self.assertEqual(len(lines), 1)
        self.assertIsNotNone(self.grants(lines[0]))
        self.assertEqual(self.m.logical_lines('# only a comment\n   \n'), [])

    def test_find_rule_reads_files_in_the_given_directories_in_order(self):
        good = 'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0660", GROUP="adbusers"\n'
        d1 = self.rules_dir(**{"51-android": 'SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666"\n'})
        d2 = self.rules_dir(**{"70-s24-usbmon": good, "99-other": 'ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"\n'})
        found = self.m.find_rule((d1, d2), self.USER, self.GROUPS)
        self.assertTrue(found["file"].endswith("70-s24-usbmon.rules"))
        self.assertEqual(found["grant"], 'MODE=0660 GROUP="adbusers"')
        self.assertIsNone(self.m.find_rule((d1,), self.USER, self.GROUPS))
        self.assertIsNone(self.m.find_rule((d1, "/nonexistent-rules-dir"), self.USER, self.GROUPS))
        self.assertIsNone(self.m.find_rule((), self.USER, self.GROUPS))

    def test_an_unreadable_rule_file_is_skipped(self):
        d = self.rules_dir(a='ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"\n')
        (Path(d) / "a.rules").chmod(0)
        if os.access(Path(d) / "a.rules", os.R_OK):
            self.skipTest("running as a user that can read mode 000 files")
        self.assertIsNone(self.m.find_rule((d,), self.USER, self.GROUPS))

    def test_the_cli_exit_status_and_output(self):
        d = self.rules_dir(a='ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"\n')
        empty = self.rules_dir(b="# nothing\n")
        ok = subprocess.run([sys.executable, "-I", str(ACCESS), "--check", "--rules-dir", d], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["found"]["file"].endswith("a.rules"))
        no = subprocess.run([sys.executable, "-I", str(ACCESS), "--check", "--rules-dir", empty], capture_output=True, text=True)
        self.assertEqual(no.returncode, 2, no.stderr)
        self.assertIsNone(json.loads(no.stdout)["found"])
        self.assertEqual(json.loads(no.stdout)["vid_pid"], "1209:0001")

    def test_it_only_reads_rule_text(self):
        src = ACCESS.read_text()
        self.assertNotIn("subprocess", src)
        self.assertNotIn("/dev/bus", src)
        self.assertNotRegex(src, r"\bsudo\b(?!.*#)", "no privilege escalation in code")
        self.assertEqual(len(re.findall(r"\.read_text\(", src)), 1)
        self.assertNotRegex(src, r"\.write_|open\(")

    def test_the_shipped_rule_text_says_how_to_install_and_remove_it(self):
        text = RULE.read_text()
        for needle in ("sudo install", "udevadm control --reload", "70-s24-usbmon.rules", "host_access.py --check", "sudo rm"):
            self.assertIn(needle, text)

    def test_owner_read_only_mode_grants_nothing(self):
        base = 'ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="%s", OWNER="egor"'
        self.assertIsNone(self.grants(base % "0400"), "the owner's read bit is not write access")
        self.assertIsNotNone(self.grants(base % "0200"))

    def test_the_udev_directories_are_those_of_udev_7(self):
        # udev(7): rules come from /usr/lib, /usr/local/lib, /run and /etc (and /lib where it is not a link to /usr/lib)
        seen = []
        with mock.patch.object(self.m, "find_rule", side_effect=lambda dirs, user, groups: seen.append(tuple(dirs))), mock.patch("builtins.print"):
            self.m.main([])
        self.assertEqual(len(seen), 1)
        self.assertEqual(set(seen[0]), {"/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d"})

    def test_the_primary_group_counts_even_when_getgroups_omits_it(self):
        names = {5: "five", 77: "primary"}
        with mock.patch.object(self.m.os, "getuid", return_value=4242), mock.patch.object(self.m.os, "getgroups", return_value=[5]), \
                mock.patch.object(self.m.pwd, "getpwuid", return_value=types.SimpleNamespace(pw_name="u", pw_gid=77)), \
                mock.patch.object(self.m.grp, "getgrgid", side_effect=lambda g: types.SimpleNamespace(gr_name=names[g])):
            self.assertEqual(self.m.current_user(), ("u", {"five", "primary"}))

    def test_only_files_ending_in_dot_rules_are_rules(self):
        line = 'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"\n'
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for name in ("70-x.rules.disabled", "70-x.rules.bak", "README", "70-x.rules~", "rules"):
            (Path(d.name) / name).write_text(line)
        self.assertIsNone(self.m.find_rule((d.name,), self.USER, self.GROUPS))
        (Path(d.name) / "70-x.rules").write_text(line)
        self.assertTrue(self.m.find_rule((d.name,), self.USER, self.GROUPS)["file"].endswith("70-x.rules"))

    def test_a_missing_or_unreadable_directory_is_no_rule_and_no_error(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        locked = Path(d.name) / "locked"
        locked.mkdir()
        (locked / "a.rules").write_text('ATTR{idVendor}=="1209", ATTR{idProduct}=="0001", MODE="0666"\n')
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o700)
        if os.access(locked, os.R_OK):
            self.skipTest("running as a user that can read mode 000 directories")
        (Path(d.name) / "plain-file").write_text("x")
        for path in ("missing", "locked", "plain-file"):
            self.assertIsNone(self.m.find_rule((str(Path(d.name) / path),), self.USER, self.GROUPS), path)


# ------------------------------------------------------------------------------------------------------------------- launcher
def fake_usb(devices=(), backend=True, find_raises=None):
    """A stand-in for the pyusb modules the collector imports. Returns (modules for sys.modules, list of find() keyword calls)."""
    calls = []
    usb, core, back, lib1, util = (types.ModuleType(n) for n in ("usb", "usb.core", "usb.backend", "usb.backend.libusb1", "usb.util"))
    usb.__version__ = "1.2.4"

    class NoBackendError(Exception):
        pass

    def find(**kw):
        calls.append(kw)
        if find_raises:
            raise find_raises
        return iter(list(devices))
    core.find, core.NoBackendError = find, NoBackendError
    lib1.get_backend = lambda: object() if backend else None
    util.dispose_resources = lambda dev: None
    usb.core, usb.backend, usb.util, back.libusb1 = core, back, util, lib1
    return {"usb": usb, "usb.core": core, "usb.backend": back, "usb.backend.libusb1": lib1, "usb.util": util}, calls


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Launcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load(LAUNCH, "nat049_collector_launch_under_test")

    def tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)

    def rows(self, path):
        return [json.loads(l) for l in Path(path).read_text().splitlines()]

    def backend(self, *args, **kw):
        hb = self.m.HeartbeatBackend(*args, **kw)
        self.addCleanup(hb.f.close)
        return hb

    class Inner:
        def __init__(self, results):
            self.results, self.calls = list(results), []

        def find(self, vid, pid):
            self.calls.append((vid, pid))
            r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
            if isinstance(r, Exception):
                raise r
            return r

    def test_the_first_find_logs_start_poll_and_found_and_passes_the_result_through(self):
        t = self.tmp() / "hb.jsonl"
        clk, mono = Clock(1700000000.0), Clock(50.0)
        devs = []
        hb = self.backend(self.Inner([devs]), t, clock=clk, mono=mono)
        self.assertIs(hb.find(0x1209, 1), devs, "the collector gets exactly what the backend returned")
        rows = self.rows(t)
        self.assertEqual([r["event"] for r in rows], ["start", "poll", "found"])
        self.assertEqual(rows[0]["pid"], os.getpid())
        self.assertEqual((rows[1]["polls"], rows[1]["found"]), (1, 0))
        self.assertEqual((rows[2]["found"], rows[2]["vid"], rows[2]["pid"]), (0, "1209", "0001"))
        self.assertEqual(rows[1]["t_unix"], 1700000000.0)
        self.assertEqual(rows[1]["t_mono"], 50.0)

    def test_polls_are_logged_every_two_seconds_not_every_call(self):
        t = self.tmp() / "hb.jsonl"
        mono = Clock(10.0)
        hb = self.backend(self.Inner([[]]), t, clock=Clock(), mono=mono)
        for dt in (0, 0.5, 1.9, 2.0, 2.5, 3.9, 4.0):
            mono.t = 10.0 + dt
            hb.find(0x1209, 1)
        polls = [r for r in self.rows(t) if r["event"] == "poll"]
        self.assertEqual([r["polls"] for r in polls], [1, 4, 7], "at the first call, then each time 2 s have passed")
        self.assertEqual(hb.polls, 7)

    def test_a_change_in_the_number_of_devices_is_logged(self):
        t = self.tmp() / "hb.jsonl"
        a, b = [object()], [object(), object()]
        inner = self.Inner([[], a, a, b, []])
        hb = self.backend(inner, t, clock=Clock(), mono=Clock())
        for _ in range(5):
            hb.find(0x1209, 1)
        self.assertEqual([r["found"] for r in self.rows(t) if r["event"] == "found"], [0, 1, 2, 0])

    def test_a_backend_error_is_logged_and_raised_unchanged(self):
        t = self.tmp() / "hb.jsonl"
        boom = RuntimeError("no libusb")
        hb = self.backend(self.Inner([boom]), t, clock=Clock(), mono=Clock())
        with self.assertRaises(RuntimeError) as cm:
            hb.find(0x1209, 1)
        self.assertIs(cm.exception, boom)
        rows = self.rows(t)
        self.assertEqual([r["event"] for r in rows], ["start", "error"])
        self.assertEqual((rows[1]["error"], rows[1]["detail"], rows[1]["polls"]), ("RuntimeError", "no libusb", 1))

    def test_the_heartbeat_file_is_created_exclusively_and_fsynced_per_record(self):
        t = self.tmp() / "hb.jsonl"
        t.write_text("old\n")
        with self.assertRaises(FileExistsError):
            self.m.HeartbeatBackend(self.Inner([[]]), t)
        self.assertEqual(t.read_text(), "old\n")
        t.unlink()
        with mock.patch.object(self.m.os, "fsync", wraps=os.fsync) as fs:
            hb = self.backend(self.Inner([[]]), t, clock=Clock(), mono=Clock())
            self.assertEqual(fs.call_count, 1, "start")
            hb.find(0x1209, 1)
            self.assertEqual(fs.call_count, 3, "poll and found")
        self.assertEqual(len(t.read_text().splitlines()), 3, "flushed to the file, not only to a buffer")

    def test_other_attributes_are_not_hidden(self):
        t = self.tmp() / "hb.jsonl"
        inner = self.Inner([[]])
        hb = self.backend(inner, t)
        self.assertIs(hb.inner, inner)
        hb.find(0x1209, 1)
        self.assertEqual(inner.calls, [(0x1209, 1)])

    def test_selftest_with_a_working_fake_pyusb(self):
        mods, calls = fake_usb()
        with mock.patch.dict(sys.modules, mods), mock.patch("builtins.print") as pr:
            rc = self.m.main(["--selftest"])
        res = json.loads(pr.call_args[0][0])
        self.assertEqual(rc, 0)
        self.assertTrue(res["ok"] and res["libusb_backend"] and res["find_returns_list"])
        self.assertEqual((res["monitor_devices_now"], res["vid_pid"]), (0, "1209:0001"))
        self.assertEqual(calls, [dict(find_all=True, idVendor=0x1209, idProduct=0x0001)], "only the monitor identity is looked for")

    def test_selftest_reports_a_device_already_on_the_bus(self):
        mods, _ = fake_usb(devices=[types.SimpleNamespace(idVendor=0x1209, idProduct=1)])
        with mock.patch.dict(sys.modules, mods), mock.patch("builtins.print") as pr:
            rc = self.m.main(["--selftest"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(pr.call_args[0][0])["monitor_devices_now"], 1)

    def test_selftest_fails_without_pyusb_without_libusb_or_when_find_fails(self):
        cases = [("no pyusb", {"usb": None, "usb.core": None, "usb.backend": None, "usb.backend.libusb1": None, "usb.util": None}),
                 ("no libusb", fake_usb(backend=False)[0]),
                 ("find raises", fake_usb(find_raises=OSError("bus gone"))[0])]
        for name, mods in cases:
            with mock.patch.dict(sys.modules, mods), mock.patch("builtins.print") as pr:
                rc = self.m.main(["--selftest"])
            res = json.loads(pr.call_args[0][0])
            self.assertEqual(rc, 2, name)
            self.assertFalse(res["ok"], name)

    def test_the_real_collector_end_to_end_with_a_fake_usb_core(self):
        mods, calls = fake_usb()
        t = self.tmp()
        out, hb = t / "archive", t / "hb.jsonl"
        with mock.patch.dict(sys.modules, mods), mock.patch("builtins.print"), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)           # the production process keeps the heartbeat file open until it exits
            rc = self.m.main(["--out", str(out), "--heartbeat", str(hb), "--seconds", "0.5"])
        self.assertIn(rc, (0, 2))
        attempt = json.loads((out / "attempt.json").read_text())
        self.assertEqual((attempt["schema"], attempt["provenance"]), ("early-log-archive-v1", "unqualified-live"))
        self.assertTrue(calls and all(c == dict(find_all=True, idVendor=0x1209, idProduct=0x0001) for c in calls), "1209:0001 and nothing else")
        events = [r["event"] for r in self.rows(hb)]
        self.assertEqual(events[:3], ["start", "poll", "found"])
        self.assertEqual(self.rows(hb)[1]["found"], 0)
        self.assertFalse((out / "boots").exists() and any((out / "boots").iterdir()), "nothing is archived while no device appears")
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["outcome"], "incomplete", "a run that saw no device is not a complete stream")

    def test_an_existing_output_directory_is_refused(self):
        mods, _ = fake_usb()
        t = self.tmp()
        (t / "archive").mkdir()
        with mock.patch.dict(sys.modules, mods), mock.patch("builtins.print"), mock.patch("sys.stderr"), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            rc = self.m.main(["--out", str(t / "archive"), "--heartbeat", str(t / "hb.jsonl"), "--seconds", "0.2"])
        self.assertEqual(rc, 2)

    def test_the_arguments_are_checked(self):
        with self.assertRaises(SystemExit) as cm, mock.patch("sys.stderr"):
            self.m.main([])
        self.assertEqual(cm.exception.code, 2)
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.m.main(["--out", "x"])

    def test_the_launcher_has_no_provenance_or_identity_option_of_its_own(self):
        src = LAUNCH.read_text()
        self.assertEqual(src.count('"--provenance", "unqualified-live"'), 1, "the one place the label is set, in the argv given to the collector")
        self.assertNotIn("add_argument(\"--provenance\"", src)
        self.assertNotIn("add_argument(\"--vid\"", src)
        self.assertNotRegex(src, r"synthetic\"?\)?\s*\]")
        self.assertIn('"--provenance", "unqualified-live"', src)


    def test_a_poll_record_carries_the_number_of_devices_found(self):
        t = self.tmp() / "hb.jsonl"
        hb = self.backend(self.Inner([["dev-a", "dev-b"]]), t, clock=Clock(1.0), mono=Clock(2.0))
        hb.find(0x1209, 1)
        poll = [r for r in self.rows(t) if r["event"] == "poll"][0]
        self.assertEqual((poll["polls"], poll["found"]), (1, 2))

    def stub_logd(self, effect=None):
        calls = []
        stub = types.SimpleNamespace(PyUsbBackend=lambda *a, **k: object())

        def main():
            calls.append(list(sys.argv))
            if effect is not None:
                raise effect
            return 0
        stub.main = main
        return stub, calls

    def test_the_collector_gets_exactly_the_arguments_the_launcher_builds(self):
        t = self.tmp()
        for extra, seconds in (([], "180.0"), (["--seconds", "7.5"], "7.5")):
            stub, calls = self.stub_logd()
            with mock.patch.object(self.m, "load_logd", return_value=stub), mock.patch.object(sys, "argv", ["x"]):
                rc = self.m.main(["--out", str(t / "a"), "--heartbeat", str(t / ("hb" + seconds))] + extra)
            self.assertEqual(rc, 0)
            self.assertEqual(calls, [["s24_logd", "--out", str(t / "a"), "--provenance", "unqualified-live", "--seconds", seconds]])
            wrapped = stub.PyUsbBackend()                                   # the launcher put its wrapper in place of the collector's backend
            self.addCleanup(wrapped.f.close)
            self.assertIsInstance(wrapped, self.m.HeartbeatBackend)

    def test_launch_errors_are_status_two_and_a_bug_is_not_hidden(self):
        t = self.tmp()
        for i, exc in enumerate((OSError("disk"), ValueError("refusing to open vendor id 0x04e8"))):
            stub, _ = self.stub_logd(exc)
            with mock.patch.object(self.m, "load_logd", return_value=stub), mock.patch.object(sys, "argv", ["x"]), mock.patch("sys.stderr") as err:
                rc = self.m.main(["--out", str(t / "a"), "--heartbeat", str(t / ("hb%d" % i)), "--seconds", "1"])
            self.assertEqual(rc, 2, repr(exc))
            self.assertIn(str(exc), "".join(c.args[0] for c in err.write.call_args_list))
        stub, _ = self.stub_logd(RuntimeError("bug"))
        with mock.patch.object(self.m, "load_logd", return_value=stub), mock.patch.object(sys, "argv", ["x"]), self.assertRaises(RuntimeError):
            self.m.main(["--out", str(t / "a"), "--heartbeat", str(t / "hb9"), "--seconds", "1"])

    def test_selftest_requires_the_backend_to_return_a_list(self):
        mods, _ = fake_usb()
        stub = types.SimpleNamespace(P=types.SimpleNamespace(VID=0x1209, PID=1), PyUsbBackend=lambda: types.SimpleNamespace(find=lambda vid, pid: ()))
        with mock.patch.dict(sys.modules, mods), mock.patch.object(self.m, "load_logd", return_value=stub), mock.patch("builtins.print") as pr:
            rc = self.m.main(["--selftest"])
        res = json.loads(pr.call_args[0][0])
        self.assertEqual(rc, 2)
        self.assertFalse(res["find_returns_list"])
        self.assertFalse(res["ok"])


# ----------------------------------------------------------------------------------------------------------------- archives
LOGD_TESTS = PROC / "nat-041/test_logd.py"
BASE = 1_800_000_000.0           # wall clock of the fixtures: the collector's archive is created here ...
T0 = BASE + 10.0                 # ... the reboot is requested ten seconds later ...
FIRST = BASE + 30.0              # ... and the first record of the boot arrives twenty seconds after that
STAGES = [(0x20, "loader_main"), (0x21, "fb"), (0x30, "mem"), (0x31, "zero"), (0x32, "copy"), (0x33, "adt"), (0x34, "clean"), (0x40, "pre_jump")]


def fnv1a64(s):
    h = 0xCBF29CE484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def boot_id_of(image, counter=1):
    """The device boot id of NAT-047: first 8 bytes little-endian counter, last 8 bytes little-endian FNV-1a-64 of the image name."""
    return counter.to_bytes(8, "little") + fnv1a64(image).to_bytes(8, "little")


class Stamp:
    """NAT-016's stamp() with a controlled wall clock; every call advances it by one millisecond."""

    def __init__(self, t):
        self.t = t

    def __call__(self):
        self.t += 0.001
        return dict(utc=iso(self.t), monotonic_ns=int(self.t * 1e9))


_t41 = {}


def t41():
    """The NAT-041 test module (it compiles the DWC3 model with the host C compiler); skips the layer when that is impossible."""
    if "m" not in _t41:
        if shutil.which("cc") is None:
            raise unittest.SkipTest("no host C compiler for the NAT-041 DWC3 model")
        try:
            m = load(LOGD_TESTS, "nat049_nat041_test_logd")
            m.lib()
        except Exception as e:                                       # noqa: BLE001  (a missing toolchain is a skip, not a failure)
            raise unittest.SkipTest("the NAT-041 model does not build here: %s" % e)
        _t41["m"] = m
    return _t41["m"]


def tearDownModule():
    m = _t41.get("m")
    if m is not None:
        shutil.rmtree(m._TMP, ignore_errors=True)
    m47 = _t47.get("m")
    if m47 is not None:
        m47.tearDownModule()                                       # the NAT-047 build cache and scenario scratch directories


def script(m, image, *, nr=3, nw=6, r_lines=None, w_lines=None, r_err=0, w_err=0, w_op=7, lad_r=True, lad_w=True, stages=STAGES, banner=None,
           exception=None, exc_text=True, hold=True, drop=False, P=None):
    """The loader's text formats (docs/procedures/nat-047/README.md) written into the model engine's ring, in the order the loader writes them.
    exception: None = what the image does (the fault image raises its controlled BRK, the plain one nothing), False = none, dict = custom."""
    fault = 1 if image == FAULT else 0
    m.text(banner if banner is not None else "NAT047 %s deadline_s=45 fault=%d" % (image, fault))
    m.stage(*stages[0])
    for i in range(nr if r_lines is None else r_lines):
        m.text("LR R %d v0=0x%x v1=0x0" % (i, 0x1000 + i))
    if lad_r:
        m.text("LAD R err=%d err_op=%d rung=2 pd_was_on=0 nrec=%d soft=0 gsnpsid=0x5533330a" % (r_err, w_op if r_err else -1, nr))
    if drop:
        m.log(P.K_TEXT, b"x" * 2000)                                    # larger than a record may be: the engine drops it and counts it
    for i in range(nw if w_lines is None else w_lines):
        m.text("LW W %d v0=0x%x v1=0x0" % (i, 0x2000 + i) if False else "LR W %d v0=0x%x v1=0x0" % (i, 0x2000 + i))
    if lad_w:
        m.text("LAD W err=%d err_op=%d rung=%d pd_was_on=0 nrec=%d soft=0 gsnpsid=0x5533330a" % (w_err, w_op if w_err else -1, 3 if w_err else 5, nw))
    for st in stages[1:]:
        m.stage(*st)
    if hold:
        m.text("HOLD stage=0x40 code=0x0")
    if exception is None:
        exception = {} if image == FAULT else False
    if exception is not False:
        esr, elr, far = exception.get("esr", FAULT_ESR), exception.get("elr", 0x80100000), exception.get("far", 0)
        m.stage(0x1F, "exception")
        m.fault(esr=esr, elr=elr, far=far)
        if exc_text:
            m.text("EXCEPTION slot=4 esr=0x%x elr=0x%x far=0x%x" % (esr, elr, far))


def make_archive(tc, *, image=PLAIN, boot_image=None, create_t=BASE, first_t=FIRST, live=True, plug=True, ring_size=16384, go_s=1.0,
                 max_bytes=1 << 24, hook=None, **kw):
    """Run the real NAT-041 collector against the DWC3 model whose ring holds the loader's text; -> the Rig (rig.out is the archive).
    live=True forces the provenance label `unqualified-live` (fixtures only: this archive is NOT hardware evidence)."""
    T = t41()
    clock = Stamp(create_t)
    real_archive = T.L.A.Archive
    with mock.patch.object(T.L.A, "stamp", clock), \
            mock.patch.object(T.L.A, "Archive", (lambda out, ch, prov: real_archive(out, ch, "unqualified-live")) if live else real_archive):
        r = T.Rig(tc, ring_size=ring_size, boot_id=boot_id_of(boot_image or image), plugged=plug)
        if plug:
            script(r.m, image, P=T.P, **kw)
        r.hook = hook
        clock.t = first_t
        r.go(go_s, max_bytes)
    return r


def rec(event, t, vid="04e8", pid="685d", product="SAMSUNG USB", path="1-1"):
    return dict(seq=0, event=event, t_unix=t, t_mono=0.0, path=path, vid=vid, pid=pid, product=product, manufacturer=None, busnum="1", devnum="2")


def usb_log(*, t0=T0, start=-3.0, stop=300.0, leave=4.0, appear=19.9, back=None, back_pid="685d", back_product="SAMSUNG USB", initial=()):
    ev = []
    if start is not None:
        ev.append(dict(seq=1, event="start", t_unix=t0 + start, t_mono=0.0, initial=list(initial)))
    if leave is not None:
        ev.append(rec("disappear", t0 + leave, pid="6860", product="SM-S921B"))
    if appear is not None:
        ev.append(rec("appear", t0 + appear, vid="1209", pid="0001", product=None))
    if back is not None:
        ev.append(rec("appear", t0 + back, pid=back_pid, product=back_product))
    if stop is not None:
        ev.append(dict(seq=99, event="stop", t_unix=t0 + stop, t_mono=0.0))
    return sorted(ev, key=lambda e: e["t_unix"])


def report(t0=T0, sent=True):
    return dict(reboot_sent=sent, reboot_requested_at=iso(t0))


def rehash(root, *names):
    """Rewrite the manifest's recorded hash of the named files (so that only the archive's inner consistency checks can notice a change)."""
    mf = json.loads((root / "manifest.json").read_text())
    for n in names:
        mf["sha256"][n] = sha256(root / n)
    (root / "manifest.json").write_text(json.dumps(mf, indent=1) + "\n")


class Verdicts(unittest.TestCase):
    """The analyzer on archives written by the real collector. The default fixture: collector created at BASE, reboot request at T0 = BASE+10,
    first record at T0+20, 1209:0001 seen by the USB watcher at T0+19.9, the watcher stopping at T0+300."""
    cache = {}

    @classmethod
    def setUpClass(cls):
        t41()
        cls.an = load(ANALYZE, "nat049_analyze_under_test")
        cls.tmp = Path(tempfile.mkdtemp(prefix="nat049-arch-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls.cache.clear()

    def arch(self, key, **kw):
        """A private copy of the archive built for `key` (built once per class)."""
        if key not in self.cache:
            r = make_archive(self, **kw)
            dest = self.tmp / ("cache-%s" % key)
            shutil.copytree(r.out, dest)
            self.cache[key] = dest
        dst = Path(tempfile.mkdtemp(dir=self.tmp)) / "archive"
        shutil.copytree(self.cache[key], dst)
        return dst

    def judge(self, d, events="default", rep=None, image=PLAIN, **kw):
        return self.an.analyze(d, usb_log() if events == "default" else events, report() if rep is None else rep, image, **kw)

    def good(self):
        return self.arch("plain", image=PLAIN)

    def good_fault(self):
        return self.arch("fault", image=FAULT)

    # -- the verdicts of the decision template
    def test_a_clean_run_of_the_plain_image_is_a_pass(self):
        out = self.judge(self.good())
        self.assertEqual(out["verdict"], "PASS", out.get("why"))
        self.assertEqual(out["reasons"], [])
        self.assertEqual((out["boots_of_image"], out["foreign_boots"]), (1, 0))
        self.assertEqual(out["integrity_problems"], [])
        self.assertAlmostEqual(out["collector_started_before_t0_s"], 10.0, delta=0.1)
        b = out["boot"]
        self.assertEqual(b["banner"], "NAT047 %s deadline_s=45 fault=0" % PLAIN)
        self.assertEqual([s for s, _ in b["stages"]], [n for n, _ in STAGES])
        self.assertEqual(b["ladder"]["R"]["nrec"], 3)
        self.assertEqual(b["ladder"]["W"]["nrec"], 6)
        self.assertEqual((b["ladder_op_lines"]["R"], b["ladder_op_lines"]["W"]), (3, 6))
        self.assertEqual((b["exception_frames"], b["exception_page"]), ([], []))
        self.assertEqual(out["manifest"]["outcome"], "complete-received-stream")
        self.assertIn(PLAIN, out["why"])

    def test_a_clean_run_of_the_fault_image_is_a_pass_with_the_controlled_exception(self):
        out = self.judge(self.good_fault(), image=FAULT)
        self.assertEqual(out["verdict"], "PASS", (out.get("why"), out["reasons"]))
        b = out["boot"]
        self.assertEqual([f["esr"] for f in b["exception_frames"]], [FAULT_ESR])
        self.assertEqual(len(b["exception_page"]), 1)
        self.assertTrue(b["exception_page"][0]["valid"])
        self.assertEqual(b["stages"][-1][0], 0x1F)
        self.assertEqual(len(b["exception_texts"]), 1)
        self.assertIn("0xf2001234", out["why"])

    def test_a_synthetic_archive_never_passes(self):
        d = self.arch("synthetic", image=PLAIN, live=False)
        out = self.judge(d)
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("synthetic", out["why"])
        self.assertIn("no verdict of its own", out["why"])
        sim = self.judge(d, allow_synthetic=True)
        self.assertEqual(sim["verdict"], "simulated-PASS")
        self.assertNotEqual(sim["verdict"], "PASS")

    def test_synthetic_partial_and_fail_are_simulated_too(self):
        d = self.arch("synthetic-nocable", image=PLAIN, live=False, plug=False)
        out = self.judge(d, usb_log(appear=None, back=60.0), allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-FAIL")
        out = self.judge(self.arch("synthetic-ladder", image=PLAIN, live=False, w_err=-5), allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-PARTIAL")

    def test_the_verdict_words_are_those_of_the_decision_template(self):
        text = (PROC / "nat-047/decision-template.md").read_text()
        for word in ("PASS (transport)", "PARTIAL", "FAIL", "Undetermined"):
            self.assertIn("* " + word, text)
        self.assertEqual(self.an.VERDICTS, ("PASS", "PARTIAL", "FAIL"))
        seen = {self.judge(self.good())["verdict"], self.judge(self.arch("nocable", image=PLAIN, plug=False), usb_log(appear=None, back=60.0))["verdict"],
                self.judge(self.arch("ladder", image=PLAIN, w_err=-5))["verdict"], self.judge(self.good(), rep=report(sent=False))["verdict"]}
        self.assertEqual(seen, {"PASS", "FAIL", "PARTIAL", "undetermined"})

    def test_the_image_name_decides_which_boot_is_evidence(self):
        wrong = self.judge(self.good_fault(), image=PLAIN)
        self.assertEqual(wrong["verdict"], "undetermined")
        self.assertIn("none has the boot id of %s" % PLAIN, wrong["why"])
        wrong = self.judge(self.good(), image=FAULT)
        self.assertEqual(wrong["verdict"], "undetermined")
        self.assertEqual((wrong["boots_of_image"], wrong["foreign_boots"]), (0, 1))
        self.assertEqual(self.judge(self.good(), image="loader-diag-reset")["verdict"], "undetermined")
        self.assertIn("unknown image", self.judge(self.good(), image="loader-diag-reset")["why"])

    def test_fnv_tail_matches_the_standard_test_vectors(self):
        self.assertEqual(self.an.fnv1a64(""), 0xCBF29CE484222325)
        self.assertEqual(self.an.fnv1a64("a"), 0xAF63DC4C8601EC8C)
        self.assertEqual(self.an.fnv1a64("foobar"), 0x85944171F73967E8)
        self.assertEqual(self.an.expected_tail(PLAIN), fnv1a64(PLAIN).to_bytes(8, "little").hex())
        self.assertNotEqual(self.an.expected_tail(PLAIN), self.an.expected_tail(FAULT))
        d = self.good()
        names = [p.name for p in (d / "boots").iterdir()]
        self.assertEqual(len(names), 1)
        self.assertRegex(names[0], r"^000001-[0-9a-f]{32}-0100000000000000%s$" % self.an.expected_tail(PLAIN))

    # -- the boot is incomplete or wrong: PARTIAL
    def test_partial_cases(self):
        cases = [
            ("ladder-w-stop", dict(w_err=-5), PLAIN, "the writing ladder stopped: err=-5 at rung 3, op 7"),
            ("ladder-r-stop", dict(r_err=-3), PLAIN, "the read-only ladder stopped: err=-3 at rung 2, op 7"),
            ("no-lad-w", dict(lad_w=False), PLAIN, "no writing ladder summary"),
            ("no-lad-r", dict(lad_r=False), PLAIN, "no read-only ladder summary"),
            ("lines-short", dict(w_lines=5), PLAIN, "the writing ladder reports 6 accesses but 5 lines arrived"),
            ("lines-long", dict(r_lines=4), PLAIN, "the read-only ladder reports 3 accesses but 4 lines arrived"),
            ("device-drop", dict(drop=True), PLAIN, "drop frame(s)"),
            ("stage-order", dict(stages=[(0x20, "a"), (0x30, "b"), (0x21, "c"), (0x40, "d")]), PLAIN, "stage records out of order"),
            ("stage-first", dict(stages=[(0x21, "a"), (0x30, "b")]), PLAIN, "the first stage record is 0x21"),
            ("banner-of-the-other-image", dict(banner="NAT047 %s deadline_s=45 fault=1" % FAULT), PLAIN, "not this image's banner"),
            ("banner-fault-flag", dict(banner="NAT047 %s deadline_s=45 fault=1" % PLAIN), PLAIN, "not this image's banner"),
            ("exception-in-the-plain-image", dict(exception={}), PLAIN, "an exception was reported by the image that has no controlled fault"),
            ("fault-image-no-exception", dict(exception=False), FAULT, "0 exception records in the ring"),
            ("wrong-esr", dict(exception=dict(esr=0x96000045)), FAULT, "has ESR 0x96000045, expected 0xf2001234"),
            ("exception-without-text", dict(exc_text=False), FAULT, "no EXCEPTION text record"),
        ]
        for key, kw, image, why in cases:
            with self.subTest(key):
                out = self.judge(self.arch(key, image=image, **kw), image=image)
                self.assertEqual(out["verdict"], "PARTIAL", (out.get("why"), out["reasons"]))
                self.assertTrue(any(why in r or why in out["why"] for r in out["reasons"] + [out["why"]]), (why, out["reasons"]))

    def test_a_capped_run_with_unread_engine_bytes_is_partial(self):
        d = self.arch("capped", image=PLAIN, max_bytes=2500, nw=60, w_lines=60)
        out = self.judge(d)
        self.assertEqual(out["verdict"], "PARTIAL", (out.get("why"), out["reasons"]))
        self.assertTrue(any("never read" in r or "manifest says" in r or "no end record" in r for r in out["reasons"]), out["reasons"])

    def test_two_boots_of_the_image_are_partial(self):
        def hook(rig, n):
            if n == 40:
                rig.reset_device(boot_id_of(PLAIN, 2))
                T = t41()
                script(rig.m, PLAIN, P=T.P)
        d = self.arch("twice", image=PLAIN, hook=hook, go_s=3.0)
        names = sorted(p.name for p in (d / "boots").iterdir())
        self.assertEqual(len(names), 2, names)
        out = self.judge(d)
        self.assertEqual(out["verdict"], "PARTIAL", (out.get("why"), out["reasons"]))
        self.assertTrue(any("2 boots of this image" in r for r in out["reasons"]), out["reasons"])

    def test_a_foreign_boot_next_to_the_image_is_partial(self):
        def hook(rig, n):
            if n == 40:
                rig.reset_device(boot_id_of(FAULT, 2))
                script(rig.m, FAULT, P=t41().P)
        d = self.arch("plain-then-fault", image=PLAIN, hook=hook, go_s=3.0)
        out = self.judge(d)
        self.assertEqual(out["verdict"], "PARTIAL", (out.get("why"), out["reasons"]))
        self.assertEqual((out["boots_of_image"], out["foreign_boots"]), (1, 1))
        self.assertTrue(any("boot(s) of other images" in r for r in out["reasons"]))

    def test_a_missing_manifest_is_partial_not_a_pass(self):
        d = self.good()
        (d / "manifest.json").unlink()
        out = self.judge(d)
        self.assertEqual(out["verdict"], "PARTIAL")
        self.assertTrue(any("no manifest.json" in r for r in out["reasons"]))

    def test_a_pass_needs_no_usb_log_but_says_it_had_none(self):
        out = self.judge(self.good(), [])
        self.assertEqual(out["verdict"], "PASS")
        self.assertFalse(out["usb"]["has_log"])

    # -- no usable record: FAIL, or undetermined
    def nocable(self):
        return self.arch("nocable", image=PLAIN, plug=False)

    def test_no_enumeration_although_the_loader_ran_is_a_fail(self):
        for back in (50.0, 60.0, 76.0):
            out = self.judge(self.nocable(), usb_log(appear=None, back=back))
            self.assertEqual(out["verdict"], "FAIL", (back, out["why"]))
            self.assertIn("although the loader ran", out["why"])
            self.assertIn("deadline", out["loader_ran_evidence"])
        out = self.judge(self.nocable(), usb_log(appear=None, back=95.0, back_product="SEC_UPLOAD"))
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIn("watchdog", out["loader_ran_evidence"])

    def test_without_evidence_that_the_loader_ran_an_absence_is_undetermined(self):
        for name, ev in (("never left", usb_log(appear=None, leave=None)), ("left, never returned", usb_log(appear=None)),
                         ("back before the deadline", usb_log(appear=None, back=30.0)), ("back after the ceiling", usb_log(appear=None, back=90.0)),
                         ("back as android", usb_log(appear=None, back=60.0, back_pid="6860", back_product="SM-S921B")),
                         ("log too short", usb_log(appear=None, back=60.0, stop=100.0)), ("no log", []),
                         ("no stop record and a short log", [e for e in usb_log(appear=None, back=60.0, stop=None)][:1]),
                         ("watcher late", usb_log(appear=None, back=60.0, start=2.0)),
                         ("monitor was already there", usb_log(appear=None, back=60.0, initial=[dict(vid="1209", pid="0001")]))):
            with self.subTest(name):
                out = self.judge(self.nocable(), ev)
                self.assertEqual(out["verdict"], "undetermined", (name, out["why"]))

    def test_an_enumeration_with_no_record_is_a_fail_and_a_permission_error_is_named(self):
        out = self.judge(self.nocable(), usb_log(appear=19.9))
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIn("1209:0001 enumerated at +19.9 s but the archive holds no readable record", out["why"])
        self.assertIsNone(out["cause"])

        def deny(rig, n):
            raise t41().L.UsbAccess("[Errno 13] Access denied (insufficient permissions)")
        d = self.arch("denied", image=PLAIN, hook=deny)
        self.assertFalse(list((d / "boots").iterdir()) if (d / "boots").exists() else [])
        out = self.judge(d, usb_log(appear=19.9))
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(out["cause"], "host-access-denied")
        self.assertIn("permission", out["why"])
        self.assertIn("device-access-denied", out["capture_errors"])
        out = self.judge(d, usb_log(appear=None, back=60.0))
        self.assertEqual(out["verdict"], "FAIL", "the loader ran; whatever the cause, nothing was archived")
        out = self.judge(d, usb_log(appear=None, leave=None))
        self.assertEqual(out["verdict"], "undetermined")

    # -- the archive and the run do not fit together: undetermined
    def test_a_boot_that_arrived_before_the_reboot_request_is_not_this_run(self):
        out = self.judge(self.arch("early", image=PLAIN, first_t=T0 - 2.0))
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("BEFORE the reboot request", out["why"])

    def test_the_first_record_must_come_within_the_window(self):
        out = self.judge(self.arch("at-300", image=PLAIN, first_t=T0 + 299.0), usb_log(appear=298.9, stop=400.0))
        self.assertEqual(out["verdict"], "PASS")
        out = self.judge(self.arch("at-301", image=PLAIN, first_t=T0 + 301.0), usb_log(appear=300.9, stop=400.0))
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("outside the 300 s window", out["why"])

    def test_a_collector_started_after_the_reboot_request_did_not_follow_the_protocol(self):
        out = self.judge(self.arch("late-collector", image=PLAIN, create_t=T0 + 1.0, first_t=T0 + 20.0))
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("after the reboot request", out["why"])

    def test_archive_and_usb_log_must_agree_that_the_monitor_appeared(self):
        out = self.judge(self.good(), usb_log(appear=None))
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("never saw 1209:0001 appear", out["why"])

    def test_the_report_must_carry_a_sent_reboot(self):
        for rep in (report(sent=False), dict(reboot_sent=True), dict(), dict(reboot_sent=True, reboot_requested_at=None)):
            out = self.judge(self.good(), rep=rep)
            self.assertEqual(out["verdict"], "undetermined", rep)
            self.assertIn("no reboot request", out["why"])

    def test_the_t0_of_the_report_orders_everything(self):
        out = self.judge(self.good(), rep=report(t0=T0 + 25.0))
        self.assertEqual(out["verdict"], "undetermined", "the boot would have arrived before the request")
        out = self.judge(self.good(), usb_log(t0=T0 + 25.0), rep=report(t0=T0 + 25.0))
        self.assertEqual(out["verdict"], "undetermined")

    # -- damaged archives are never judged
    def assertRefused(self, d, fragment=None):
        out = self.judge(d)
        self.assertEqual(out["verdict"], "undetermined", (out.get("why"), out.get("reasons")))
        if fragment:
            self.assertIn(fragment, out["why"])
        return out

    def test_a_flipped_byte_in_received_bin(self):
        d = self.good()
        raw = bytearray((d / "received.bin").read_bytes())
        raw[len(raw) // 2] ^= 1
        (d / "received.bin").write_bytes(bytes(raw))
        out = self.assertRefused(d, "integrity")
        self.assertIn("hash mismatch: received.bin", out["integrity_problems"])

    def test_a_truncated_received_bin_with_a_matching_manifest(self):
        d = self.good()
        raw = (d / "received.bin").read_bytes()
        (d / "received.bin").write_bytes(raw[:-10])
        rehash(d, "received.bin")
        out = self.assertRefused(d)
        self.assertTrue(any("received.bin has" in p or "does not match received.bin" in p for p in out["integrity_problems"]), out["integrity_problems"])

    def test_a_changed_chunk_index_with_a_matching_manifest(self):
        d = self.good()
        lines = (d / "chunks.jsonl").read_text().splitlines()
        row = json.loads(lines[0])
        row["offset"] += 1
        lines[0] = json.dumps(row)
        (d / "chunks.jsonl").write_text("\n".join(lines) + "\n")
        rehash(d, "chunks.jsonl")
        out = self.assertRefused(d)
        self.assertTrue(any("chunk" in p for p in out["integrity_problems"]))

    def test_a_missing_payload_and_a_payload_that_is_not_the_frames_data(self):
        d = self.good()
        payload = next((d / "boots").glob("*/payload.bin"))
        rel = str(payload.relative_to(d))
        payload.write_bytes(payload.read_bytes()[:-1] + b"\x00" if payload.read_bytes()[-1] != 0 else payload.read_bytes()[:-1] + b"\x01")
        rehash(d, rel)
        out = self.assertRefused(d)
        self.assertTrue(any("payload.bin is not the concatenation" in p for p in out["integrity_problems"]), out["integrity_problems"])
        d = self.good()
        next((d / "boots").glob("*/payload.bin")).unlink()
        out = self.assertRefused(d)
        self.assertTrue(any("missing" in p for p in out["integrity_problems"]))

    def test_a_file_the_manifest_does_not_list_and_a_file_it_lists_but_is_gone(self):
        d = self.good()
        (d / "extra.txt").write_text("x")
        self.assertIn("file not in the manifest: extra.txt", self.assertRefused(d)["integrity_problems"])
        d = self.good()
        (d / "usb-transfers.jsonl").unlink()
        self.assertTrue(any("usb-transfers.jsonl but the file is missing" in p for p in self.assertRefused(d)["integrity_problems"]))

    def test_an_edited_frames_file_with_a_matching_manifest(self):
        d = self.good()
        f = next((d / "boots").glob("*/frames.jsonl"))
        lines = f.read_text().splitlines()
        f.write_text("\n".join(lines[:-1]) + "\n")                       # the end frame is gone; the payload still has its data
        rehash(d, str(f.relative_to(d)))
        out = self.assertRefused(d)
        self.assertTrue(any("payload.bin is not the concatenation" in p for p in out["integrity_problems"]))
        d = self.good()
        f = next((d / "boots").glob("*/frames.jsonl"))
        f.write_text(f.read_text() + "{not json\n")
        rehash(d, str(f.relative_to(d)))
        self.assertTrue(any("unreadable frame lines" in p for p in self.assertRefused(d)["integrity_problems"]))

    def test_unreadable_attempt_json_and_empty_or_missing_directories(self):
        d = self.good()
        (d / "attempt.json").write_text("{")
        self.assertRefused(d, "no readable attempt.json")
        d = self.good()
        (d / "attempt.json").unlink()
        self.assertRefused(d, "no readable attempt.json")
        e = self.tmp / "empty-dir"
        e.mkdir(exist_ok=True)
        self.assertRefused(e, "the collector never started")
        self.assertRefused(self.tmp / "no-such-dir", "the collector never started")
        d = self.good()
        (d / "attempt.json").write_text(json.dumps(dict(schema="something-else")))
        self.assertRefused(d, "no readable attempt.json")

    def test_a_damaged_archive_is_not_partial_it_is_not_judged_at_all(self):
        d = self.arch("ladder", image=PLAIN, w_err=-5)
        self.assertEqual(self.judge(d)["verdict"], "PARTIAL")
        raw = bytearray((d / "received.bin").read_bytes())
        raw[0] ^= 1
        (d / "received.bin").write_bytes(bytes(raw))
        self.assertEqual(self.judge(d)["verdict"], "undetermined")

    # -- the judgement one reason at a time (judge_boot on the summary of a real boot) and the parsing (summarize_boot on its frames)
    def boot_of(self, image):
        d = self.good() if image == PLAIN else self.good_fault()
        return copy.deepcopy(self.judge(d, image=image)["boot"])

    def frames_of(self, image):
        d = self.good() if image == PLAIN else self.good_fault()
        folder = next((d / "boots").iterdir())
        rows, problems = self.an.load_boot(folder)
        self.assertEqual(problems, [])
        return folder.name, copy.deepcopy(rows)

    def test_a_healthy_boot_of_either_image_has_no_reason(self):
        self.assertEqual(self.an.judge_boot(self.boot_of(PLAIN), PLAIN, 0), [])
        self.assertEqual(self.an.judge_boot(self.boot_of(FAULT), FAULT, 1), [])

    def test_each_judge_boot_reason_has_its_own_trigger(self):
        exc_frame = dict(esr=FAULT_ESR, elr=0x80100000, far=0, stage=0x1F)
        page = lambda b: b["exception_page"][0]          # noqa: E731
        boot_rec, monitor, banner, ring = "one boot record followed by a contiguous sequence", "does not name the monitor device 1209:0001", "not this image's banner", "not contiguous from 0"
        stage_last, page_bad, plain_exc = "the exception stage is not the single last stage record", "invalid or disagrees", "an exception was reported by the image that has no controlled fault"
        cases = [
            ("no boot record", PLAIN, lambda b: b["kinds"].update(boot=0), boot_rec),
            ("two boot records", PLAIN, lambda b: b["kinds"].update(boot=2), boot_rec),
            ("frame sequence gap", PLAIN, lambda b: b.update(frame_seq_contiguous=False), boot_rec),
            ("boot record names another vendor", PLAIN, lambda b: b.update(usb=dict(vid=0x04E8, pid=1)), monitor),
            ("boot record names another product", PLAIN, lambda b: b.update(usb=dict(vid=0x1209, pid=2)), monitor),
            ("boot record names nothing", PLAIN, lambda b: b.update(usb=None), monitor),
            ("banner of another name", PLAIN, lambda b: b.update(banner="NAT047 something-else deadline_s=45 fault=0"), banner),
            ("banner without the setting", PLAIN, lambda b: b.update(banner="NAT047 %s deadline_s=45" % PLAIN), banner),
            ("no banner", PLAIN, lambda b: b.update(banner=None), banner),
            ("ring starts at 1", PLAIN, lambda b: b.update(first_dev_seq=1), ring),
            ("ring has a gap", PLAIN, lambda b: b.update(dev_seq_contiguous=False), ring),
            ("drop frames", PLAIN, lambda b: b.update(drop_frames=2), "2 drop frame(s)"),
            ("no stage records", PLAIN, lambda b: b.update(stages=[]), "no stage record"),
            ("a stage after the exception", FAULT, lambda b: b["stages"].append((0x40, "late")), stage_last),
            ("two exception stages", FAULT, lambda b: b["stages"].append((0x1F, "exception")), stage_last),
            ("no end record", PLAIN, lambda b: b.update(end=None), "no end record"),
            ("unread engine bytes", PLAIN, lambda b: b["end"].update(unread_bytes=17), "17 engine bytes were written but never read"),
            ("two exception records", FAULT, lambda b: b.update(exception_frames=b["exception_frames"] * 2), "2 exception records in the ring"),
            ("exception page invalid", FAULT, lambda b: page(b).update(valid=0), page_bad),
            ("exception page: another pc", FAULT, lambda b: page(b).update(elr=page(b)["elr"] + 4), page_bad),
            ("exception page: another syndrome", FAULT, lambda b: page(b).update(esr=0x96000045), page_bad),
            ("exception page: another address", FAULT, lambda b: page(b).update(far=0x1000), page_bad),
            ("plain image: an exception record", PLAIN, lambda b: b.update(exception_frames=[exc_frame]), plain_exc),
            ("plain image: an EXCEPTION text", PLAIN, lambda b: b.update(exception_texts=["EXCEPTION slot=4 esr=0x0"]), plain_exc),
            ("plain image: an exception page", PLAIN, lambda b: b.update(exception_page=[dict(esr=0, elr=0, far=0, valid=1, spsr=0, sp=0)]), plain_exc),
            ("plain image: an exception stage", PLAIN, lambda b: b["stages"].append((0x1F, "exception")), plain_exc),
        ]
        for name, image, change, fragment in cases:
            with self.subTest(name):
                b = self.boot_of(image)
                change(b)
                reasons = self.an.judge_boot(b, image, 1 if image == FAULT else 0)
                self.assertTrue(any(fragment in r for r in reasons), (fragment, reasons))

    def test_summarize_boot_reads_the_sequence_numbers_from_the_frames(self):
        an = self.an
        name, rows = self.frames_of(PLAIN)
        s = an.summarize_boot(name, rows)
        self.assertTrue(s["frame_seq_contiguous"] and s["dev_seq_contiguous"])
        self.assertEqual(s["first_dev_seq"], 0)
        gap = copy.deepcopy(rows)
        gap[5]["frame"]["seq"] += 1
        self.assertFalse(an.summarize_boot(name, gap)["frame_seq_contiguous"])
        ring = [i for i, r in enumerate(rows) if r["frame"]["kind"] in ("log", "stage", "fault") and "dev_seq" in r["frame"]]
        hole = copy.deepcopy(rows)
        hole[ring[3]]["frame"]["dev_seq"] += 1
        s = an.summarize_boot(name, hole)
        self.assertFalse(s["dev_seq_contiguous"])
        self.assertEqual(s["first_dev_seq"], 0)
        shifted = copy.deepcopy(rows)
        for i in ring:
            shifted[i]["frame"]["dev_seq"] += 1
        s = an.summarize_boot(name, shifted)
        self.assertTrue(s["dev_seq_contiguous"])
        self.assertEqual(s["first_dev_seq"], 1)
        only_boot = an.summarize_boot(name, rows[:1])                       # no ring record at all
        self.assertEqual((only_boot["records"], only_boot["first_dev_seq"], only_boot["banner"]), (0, None, None))
        self.assertFalse(only_boot["dev_seq_contiguous"])

    def test_a_manifest_that_says_incomplete_or_counts_errors_is_partial(self):
        for key, change in (("outcome", dict(outcome="incomplete")), ("errors", dict(errors=2))):
            with self.subTest(key):
                d = self.good()
                mf = json.loads((d / "manifest.json").read_text())
                mf.update(change)
                (d / "manifest.json").write_text(json.dumps(mf, indent=1) + "\n")
                out = self.judge(d)
                self.assertEqual(out["verdict"], "PARTIAL", (out["why"], out["reasons"]))
                self.assertTrue(any("manifest says" in r for r in out["reasons"]), out["reasons"])

    def test_collector_drops_make_a_pass_partial(self):
        d = self.good()
        s = json.loads((d / "collector-summary.json").read_text())
        s["stats"]["drops"] = 3
        (d / "collector-summary.json").write_text(json.dumps(s, indent=1) + "\n")
        rehash(d, "collector-summary.json")
        out = self.judge(d)
        self.assertEqual(out["verdict"], "PARTIAL", (out["why"], out["reasons"]))
        self.assertTrue(any("the collector counted 3 drop(s)" in r for r in out["reasons"]), out["reasons"])

    # -- the host USB log: its edges
    def test_the_usb_log_must_cover_one_hundred_and_twenty_seconds(self):
        d = self.nocable()
        self.assertEqual(self.judge(d, usb_log(appear=None, back=60.0, stop=120.0))["verdict"], "FAIL", "120 s are enough")
        out = self.judge(d, usb_log(appear=None, back=60.0, stop=119.9))
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("covers only", out["why"])

    def test_a_monitor_seen_before_the_reboot_request_is_not_this_run(self):
        early = rec("appear", T0 - 1.0, vid="1209", pid="0001", product=None)
        out = self.judge(self.good(), sorted(usb_log(appear=None) + [early], key=lambda e: e["t_unix"]))
        self.assertEqual(out["verdict"], "undetermined", out["why"])
        self.assertIsNone(out["usb"]["monitor_appear_dt"])
        self.assertIn("never saw 1209:0001 appear", out["why"])

    def test_another_vendors_device_coming_and_going_is_not_the_phone(self):
        other = [rec("disappear", T0 + 4.0, vid="1d6b", pid="0002", product="xHCI Host Controller"),
                 rec("appear", T0 + 60.0, vid="1d6b", pid="0002", product="SAMSUNG USB")]
        out = self.judge(self.nocable(), sorted(usb_log(appear=None, leave=None) + other, key=lambda e: e["t_unix"]))
        self.assertEqual(out["verdict"], "undetermined", out["why"])
        self.assertIsNone(out["usb"]["phone_left_dt"])

    def test_only_a_return_after_the_phone_left_counts(self):
        ev = usb_log(appear=None, leave=None) + [rec("appear", T0 + 50.0, pid="685d"), rec("disappear", T0 + 55.0, pid="685d")]
        out = self.judge(self.nocable(), sorted(ev, key=lambda e: e["t_unix"]))
        self.assertEqual(out["usb"]["phone_left_dt"], 55.0)
        self.assertIsNone(out["usb"]["first_return"])
        self.assertEqual(out["verdict"], "undetermined", out["why"])

    # -- the archive's own consistency checks, one at a time
    def problems(self, d):
        return self.judge(d)["integrity_problems"]

    def test_a_chunk_index_that_skips_a_chunk_is_found_by_its_offsets_alone(self):
        d = self.good()
        lines = (d / "chunks.jsonl").read_text().splitlines()
        (d / "chunks.jsonl").write_text("\n".join(lines[1:]) + "\n")
        rehash(d, "chunks.jsonl")
        p = self.problems(d)
        self.assertTrue(any(x.startswith("chunk index: offset") and "where 0 was expected" in x for x in p), p)
        self.assertFalse(any("does not match" in x for x in p), p)

    def test_a_chunk_whose_hash_is_wrong_is_found_by_the_hash_alone(self):
        d = self.good()
        lines = (d / "chunks.jsonl").read_text().splitlines()
        row = json.loads(lines[0])
        row["sha256"] = "0" * 64
        lines[0] = json.dumps(row)
        (d / "chunks.jsonl").write_text("\n".join(lines) + "\n")
        rehash(d, "chunks.jsonl")
        p = self.problems(d)
        self.assertEqual([x for x in p if "does not match" in x], ["chunk at offset 0 does not match received.bin"], p)

    def test_a_chunk_whose_length_runs_past_the_end_is_found_by_the_length(self):
        d = self.good()
        lines = (d / "chunks.jsonl").read_text().splitlines()
        row = json.loads(lines[-1])
        row["length"] += 5                                                  # the slice is clipped at the end of the file, so its hash is still right
        lines[-1] = json.dumps(row)
        (d / "chunks.jsonl").write_text("\n".join(lines) + "\n")
        rehash(d, "chunks.jsonl")
        p = self.problems(d)
        self.assertTrue(any("does not match received.bin" in x for x in p), p)

    def test_bytes_after_the_last_chunk_are_found(self):
        d = self.good()
        with open(d / "received.bin", "ab") as f:
            f.write(b"\x00" * 10)
        rehash(d, "received.bin")
        p = self.problems(d)
        self.assertEqual(len(p), 1, p)
        self.assertIn("the chunk index covers", p[0])

    def test_a_frame_whose_data_is_not_strict_base64_is_not_the_payload(self):
        d = self.good()
        f = next((d / "boots").glob("*/frames.jsonl"))
        rows = [json.loads(l) for l in f.read_text().splitlines()]
        data = rows[1]["frame"]["data_b64"]
        rows[1]["frame"]["data_b64"] = data[:8] + "!" + data[8:]            # a lenient decoder drops the "!" and gets the same bytes
        f.write_text("".join(json.dumps(r) + "\n" for r in rows))
        rehash(d, str(f.relative_to(d)))
        self.assertTrue(any("payload.bin is not the concatenation" in x for x in self.problems(d)))

    def test_an_unreadable_events_line_is_an_integrity_problem(self):
        d = self.good()
        with open(d / "events.jsonl", "a") as f:
            f.write("{broken\n")
        rehash(d, "events.jsonl")
        self.assertIn("events.jsonl has 1 unreadable lines", self.problems(d))

    # -- the command line
    def test_the_cli_reads_the_files_prints_and_writes_the_analysis(self):
        d = self.good()
        t = d.parent
        (t / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in usb_log()))
        (t / "report.json").write_text(json.dumps(report()))
        base = [sys.executable, "-I", str(ANALYZE), "--archive", str(d), "--events", str(t / "events.jsonl"), "--report", str(t / "report.json"), "--image", PLAIN]
        r = subprocess.run(base + ["--out", str(t / "analysis.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "PASS", r.stdout)
        self.assertEqual(json.loads((t / "analysis.json").read_text())["image"], PLAIN)

    def test_the_cli_survives_missing_inputs(self):
        d = self.good()
        t = d.parent
        r = subprocess.run([sys.executable, "-I", str(ANALYZE), "--archive", str(d), "--events", str(t / "none.jsonl"), "--report", str(t / "none.json"),
                            "--image", PLAIN], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "undetermined")
        self.assertIn("no reboot request", json.loads(r.stdout)["why"])

    def test_the_cli_allow_synthetic_flag(self):
        d = self.arch("synthetic", image=PLAIN, live=False)
        t = d.parent
        (t / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in usb_log()))
        (t / "report.json").write_text(json.dumps(report()))
        base = [sys.executable, "-I", str(ANALYZE), "--archive", str(d), "--events", str(t / "events.jsonl"), "--report", str(t / "report.json"), "--image", PLAIN]
        self.assertEqual(json.loads(subprocess.run(base, capture_output=True, text=True).stdout)["verdict"], "undetermined")
        self.assertEqual(json.loads(subprocess.run(base + ["--allow-synthetic"], capture_output=True, text=True).stdout)["verdict"], "simulated-PASS")

    def test_the_analyzer_never_writes_into_the_archive(self):
        d = self.good()
        before = {str(p.relative_to(d)): sha256(p) for p in d.rglob("*") if p.is_file()}
        self.judge(d)
        after = {str(p.relative_to(d)): sha256(p) for p in d.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(sorted(p.name for p in d.iterdir()), sorted({p.parts[0] for p in map(Path, before)}))



def add_dev(root, name, vid="04e8", pid="685d", product="SAMSUNG USB", devnum="7", serial="SERIALSENTINEL0123", manufacturer="SAMSUNG", complete=True):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    files = dict(idVendor=vid, idProduct=pid, product=product, manufacturer=manufacturer, busnum="5", devnum=devnum, serial=serial)
    for k, v in files.items():
        if complete or k == "idVendor":
            (d / k).write_text(v + "\n")


def rm_dev(root, name):
    shutil.rmtree(Path(root) / name)


# ---------------------------------------------------------------------------------------------------------------- driver
FAKE_ADB = r'''#!{python}
import hashlib, os, sys
from pathlib import Path
base = Path(os.environ["FAKE_DEVICE_DIR"])
dev = base / "recovery.bin"
args = sys.argv[1:]
with (base / "adb-calls").open("a") as f:
    f.write(" ".join(args) + "\n")


def order(tag):
    with (base / "order").open("a") as f:
        f.write(tag + "\n")


def has(path, needle):
    return bool(path) and os.path.exists(path) and any(needle in l for l in open(path))


if args == ["get-state"]:
    order("adb get-state")
    print("device")
elif args == ["reboot", "recovery"]:
    order("adb reboot")
    (base / "reboot-saw-watcher").write_text("yes" if has(os.environ.get("FAKE_WATCH_LOG"), '"event": "start"') else "no")
    (base / "reboot-saw-collector").write_text("yes" if has(os.environ.get("FAKE_HEARTBEAT"), '"event": "poll"') else "no")
    if os.environ.get("FAKE_REBOOT_FAIL"):
        sys.stderr.write("error: closed\n")
        sys.exit(1)
elif args[:2] == ["shell", "-T"]:
    cmd = args[2]
    props = {"ro.product.model": "SM-S921B", "ro.product.device": "e1s", "ro.build.PDA": "S921BXXS9BYH3", "sys.boot_completed": "1"}
    if cmd.startswith("getprop "):
        order("adb getprop")
        print(props[cmd.split()[1]])
    elif "readlink -f" in cmd:
        order("adb identity")
        print("/dev/block/sda18\n100663296\nblock_device")
    elif "pidof dd" in cmd:
        order("adb pidof")
        print("busy" if (base / "dd-busy").exists() else "idle")
    elif "sha256sum /dev/block/sda18" in cmd:
        order("adb sha256sum")
        print(hashlib.sha256(dev.read_bytes()).hexdigest() + "  /dev/block/sda18")
    elif cmd.startswith("dumpsys battery"):
        order("adb battery")
        print("level=%s\ntemperature=300" % (base / "battery").read_text().strip() if (base / "battery").exists() else "level=80\ntemperature=300")
    elif "dd of=/dev/block/sda18" in cmd:
        order("adb write")
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

# usb_watch.py of the scratch tree: the real NAT-048 watcher on a fake sysfs, started through this one-file wrapper
WRAPPER = r'''import os, runpy, sys
real = os.environ["REAL_WATCHER"]
secs = sys.argv[sys.argv.index("--seconds") + 1]
with open(os.path.join(os.environ["FAKE_DEVICE_DIR"], "order"), "a") as f:
    f.write("watcher-selftest\n" if secs == "1" else "watcher-start\n")
if os.environ.get("FAKE_WATCHER_FAIL_SELFTEST") and secs == "1":
    sys.exit(1)
if os.environ.get("FAKE_WATCHER_FAIL_RUN") and secs != "1":
    sys.exit(1)
if os.environ.get("FAKE_WATCHER_DELAY") and secs != "1":
    import time
    time.sleep(float(os.environ["FAKE_WATCHER_DELAY"]))
sys.argv += ["--sysfs", os.environ["FAKE_SYSFS"]]
sys.argv[0] = real
runpy.run_path(real, run_name="__main__")
'''

# collector_launch.py of the scratch tree: same command line and the same heartbeat vocabulary (start/poll/error) as the real launcher
STUB_COLLECTOR = r'''import json, os, sys, time
base = os.environ["FAKE_DEVICE_DIR"]


def order(tag):
    with open(os.path.join(base, "order"), "a") as f:
        f.write(tag + "\n")


args = sys.argv[1:]
if args == ["--selftest"]:
    order("collector-selftest")
    mode = os.environ.get("FAKE_SELFTEST", "ok")
    if mode == "garbage":
        print("not json")
        sys.exit(0)
    res = dict(ok=mode not in ("fail", "false"), monitor_devices_now=int(os.environ.get("FAKE_MONITOR_NOW", "0")))
    if mode == "nomonitor":
        del res["monitor_devices_now"]
    print(json.dumps(res))
    sys.exit(2 if mode in ("fail", "exit2") else 0)


def opt(name):
    return args[args.index(name) + 1]


order("collector-start")
with open(os.path.join(base, "collector-argv"), "w") as f:
    f.write("\0".join(args))
if os.environ.get("FAKE_COLLECTOR_EXIT"):
    sys.exit(3)
hb = open(opt("--heartbeat"), "x")


def emit(event, **kw):
    hb.write(json.dumps(dict(event=event, t_unix=time.time(), **kw)) + "\n")
    hb.flush()
    os.fsync(hb.fileno())


emit("start", pid=os.getpid())
time.sleep(float(os.environ.get("FAKE_COLLECTOR_DELAY", "0")))
if os.environ.get("FAKE_COLLECTOR_ERROR"):
    emit("error", error="UsbAccess", detail="denied")
    if os.environ["FAKE_COLLECTOR_ERROR"] == "then-poll":
        emit("poll", polls=2, found=0)             # a poll AFTER the error: the driver must still stop on the error
else:
    emit("poll", polls=1, found=0)
time.sleep(float(opt("--seconds")))
'''

STUB_ACCESS = r'''import json, os, sys
base = os.environ["FAKE_DEVICE_DIR"]
with open(os.path.join(base, "order"), "a") as f:
    f.write("access\n")
mode = os.environ.get("FAKE_ACCESS", "ok")
if mode == "garbage":
    print("not json")
    sys.exit(0)
found = None if mode in ("missing", "exit0-null") else dict(file="/etc/udev/rules.d/70-s24-usbmon.rules", line="x", grant="MODE=0660")
print(json.dumps(dict(vid_pid="1209:0001", user="u", found=found, groups=[])))
sys.exit(2 if mode in ("missing", "exit2-found") else 0)
'''


def pinned(image):
    return json.loads((PACKAGE / "package.json").read_text())["images"][image]


def decision_text(image, with_recovery=True, with_payload=True, with_0019=True):
    p = pinned(image)
    parts = ["scratch-tree decision for %s\n" % image]
    if with_recovery:
        parts.append("RECOVERY SHA-256 %s\n" % p["recovery_sha256"])
    if with_payload:
        parts.append("Image.payload SHA-256 %s\n" % p["payload_sha256"])
    if with_0019:
        parts.append("recorded under decision 0019\n")
    return "".join(parts)


def decision_name(image, n="0099"):
    return "%s-nat043-%s-single-run-2026-11-12.md" % (n, image)


def alive(pid):
    try:
        state = Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False
    return state not in "ZX"


def code_lines(path):
    text = Path(path).read_text()
    m = re.search(r'"""(.*?)"""', text, re.S)
    return [l.strip() for l in (text[:m.start()] + text[m.end():]).splitlines() if l.strip()]


class RealTreeGate(unittest.TestCase):
    """The gated driver in the real tree: with no agent-written decision file it stops before any adb call, in every mode, and before
    the registry, the udev check or the collector self-test are consulted."""

    def decisions(self, image):
        return sorted((ROOT / "docs/decisions").glob("*-nat043-%s-single-run-*.md" % image))

    def run_driver(self, image, *mode):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "bin").mkdir()
            fake = t / "bin/adb"
            fake.write_text("#!/bin/sh\necho \"$@\" >> %s\nexit 1\n" % (t / "adb-calls"))
            fake.chmod(0o755)
            env = {"PATH": f"{t / 'bin'}:/usr/bin:/bin", "HOME": str(t)}
            r = subprocess.run([sys.executable, "-I", str(DRIVER), "--image", image, "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def test_no_decision_no_adb_in_any_mode_for_either_image(self):
        for image in IMAGES:
            if self.decisions(image):
                self.skipTest("a decision file for %s exists: its gate is open" % image)
            marker = ROOT / ("artifacts/nat-049/native-attempt-%s-used.json" % image)
            before = marker.exists()
            for mode in ((), ("--execute",), ("--restore",)):
                r, calls, rep = self.run_driver(image, *mode)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(calls, "", (image, mode))
                self.assertEqual(rep["outcome"], "stopped")
                self.assertIn("decision file for %s is missing or ambiguous (0 found)" % image, rep["error"])
                self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))
                for key in ("watcher", "collector", "host_access", "collector_selftest", "registry_blocker", "watcher_selftest"):
                    self.assertNotIn(key, rep, (image, mode, key))
            self.assertEqual(marker.exists(), before, "a refused run must not leave the one-shot marker")

    def test_one_images_decision_does_not_open_the_other(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / decision_name(FAULT, "0021")).write_text("x")
            self.assertEqual(sorted(d.glob("*-nat043-%s-single-run-*.md" % PLAIN)), [])
            self.assertEqual(len(sorted(d.glob("*-nat043-%s-single-run-*.md" % FAULT))), 1)
        # and the NAT-046/NAT-022 decision files are not NAT-043 decisions
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "0021-nat046-loader-diag-usbmon-single-run-2026-11-12.md").write_text("x")
            self.assertEqual(sorted(Path(t).glob("*-nat043-%s-single-run-*.md" % PLAIN)), [])

    @source_pin
    def test_pinned_hashes_are_those_of_package_001_and_the_build_record(self):
        if not (PACKAGE / "package.json").exists():
            self.skipTest("package-001 is not present")
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        build = json.loads((ROOT / pkg["build"] / "build.json").read_text())
        self.assertRegex(src, r"(?m)^PACKAGE=ROOT/'artifacts/nat-047/package-001'")
        self.assertRegex(src, r"(?m)^STOCK_SHA='%s'" % pkg["stock_sha256"])
        self.assertEqual(pkg["stock_sha256"], STOCK_SHA)
        self.assertTrue(pkg["flashed"] is False and pkg["kind"] == "host-test" and pkg["device_used"] is False)
        for image in IMAGES:
            p = pkg["images"][image]
            for value in (p["recovery_sha256"], p["payload_sha256"]):
                self.assertEqual(src.count(value), 1, (image, value))
            self.assertIn("CANARY_LEN=%d" % p["payload_bytes"], src)
            self.assertEqual(p["payload_offset"], 2048)
            self.assertIn("PAYLOAD_OFFSET=2048", src)
            self.assertEqual(build["image_payloads"][image]["sha256"], p["payload_sha256"])
            self.assertEqual(build["image_payloads"][image]["bytes"], p["payload_bytes"])
            self.assertNotEqual(p["payload_sha256"], p["loader_image_sha256"], "the payload, not the loader-only Image, is pinned")
            self.assertNotIn(p["loader_image_sha256"], src)
            rec = PACKAGE / image / "recovery.img"
            if rec.exists():
                self.assertEqual(sha256(rec), p["recovery_sha256"])
        m = load(DRIVER, "nat049_driver_pins")
        self.assertEqual(sorted(m.IMAGES), sorted(IMAGES))
        for image in IMAGES:
            self.assertEqual((m.IMAGES[image]["NEW_SHA"], m.IMAGES[image]["CANARY_SHA"], m.IMAGES[image]["CANARY_LEN"]),
                             (pkg["images"][image]["recovery_sha256"], pkg["images"][image]["payload_sha256"], pkg["images"][image]["payload_bytes"]))
        self.assertEqual(m.STOCK_SHA, STOCK_SHA)
        self.assertEqual(m.STOCK.relative_to(m.ROOT), STOCK.relative_to(ROOT))
        self.assertEqual(m.PACKAGE.relative_to(m.ROOT), PACKAGE.relative_to(ROOT))

    def test_the_image_names_of_the_driver_and_the_analyzer_agree(self):
        d = load(DRIVER, "nat049_driver_names")
        a = load(ANALYZE, "nat049_analyzer_names")
        self.assertEqual(sorted(d.IMAGES), sorted(a.IMAGES))
        self.assertEqual(sorted(d.IMAGES), sorted(IMAGES))

    def test_the_session_covers_the_analyzers_windows(self):
        d = load(DRIVER, "nat049_driver_windows")
        a = load(ANALYZE, "nat049_analyzer_windows")
        for name in ("WATCH_S", "COLLECT_S"):
            self.assertGreaterEqual(getattr(d, name), a.RECEIVE_WINDOW_S + 30, "%s must outlast the 300 s window for the first record by a margin" % name)
        self.assertGreaterEqual(d.WATCH_S, a.COVERAGE_S)
        self.assertEqual(d.REQUIRED_DONE, ("NAT-039", "NAT-046"))

    @source_pin
    def test_reboot_and_flash_surface(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("reboot','recovery'"), 1)
        self.assertEqual(len(re.findall(r"'reboot'", src)), 1, "no other reboot form (reboot bootloader/download, a plain reboot)")
        self.assertNotIn("fastboot", src.lower())
        self.assertEqual(len(re.findall(r"odin|heimdall", src)), 2)
        self.assertIn("['odin4','heimdall']", src)
        self.assertEqual(sorted(set(re.findall(r"/dev/block/[\w/.-]+", src))), ["/dev/block/by-name/recovery", "/dev/block/sda18"])
        self.assertEqual(len(re.findall(r"dd of=", src)), 1)
        self.assertNotRegex(src, r"\bsudo\b|\bdocker\b|\bchmod\b|\budevadm\b", "the driver installs nothing and escalates nothing on the host")
        self.assertEqual(len(re.findall(r"Popen\(", src)), 2, "exactly the watcher and the collector are spawned")
        self.assertEqual(src.count("start_new_session=True"), 2)

    @source_pin
    def test_the_driver_never_creates_the_decision_file(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("ROOT/'docs/decisions'"), 1)
        self.assertRegex(src, r"glob\('\*-nat043-%s-single-run-\*\.md'%image\)")
        self.assertNotRegex(src, r"decisions[^\n]*(write_text|write_bytes|open\()")
        self.assertIn("marker.open('x')", src)
        self.assertIn("exist_ok=False", src)
        self.assertNotRegex(src, r"lab\.json[^\n]*(write|open\([^)]*['\"]w)", "the registry is read, never written")
        self.assertEqual(src.count("state/lab.json"), 1)

    @source_pin
    def test_the_gates_are_checked_before_the_first_adb_call(self):
        src = DRIVER.read_text()
        first_adb = src.index("run(['adb','get-state'])")
        for needle in ("decision=gate(a.image,cfg)", "blocker=registry_blocker(decision)", "host_access();collector_selftest()"):
            self.assertEqual(src.count(needle), 1, needle)
            self.assertLess(src.index(needle), first_adb, needle)
        self.assertLess(src.index("decision=gate(a.image,cfg)"), src.index("blocker=registry_blocker(decision)"))
        self.assertLess(src.index("blocker=registry_blocker(decision)"), src.index("host_access();collector_selftest()"))
        # the registry, udev and collector self-test gates are skipped by --restore only, and the blocker stops --execute only
        self.assertIn("if not a.restore:\n                blocker=registry_blocker(decision)", src)
        self.assertIn("assert not (a.execute and blocker),blocker", src)
        self.assertLess(first_adb, src.index("if not a.restore:watcher_selftest()"))

    @source_pin
    def test_watcher_and_collector_are_started_after_the_readback_and_before_the_single_reboot(self):
        src = DRIVER.read_text()
        write = src.index("write(candidate,NEW_SHA)")
        watcher = src.index("            watcher_start()\n")
        collector = src.index("            collector_start()\n")
        reboot = src.index("run(['adb','reboot','recovery'])")
        sent = src.index("report['reboot_sent']=True;report['reboot_requested_at']=now();save()")
        self.assertTrue(write < watcher < collector < sent < reboot)
        self.assertLess(src.index("marker.open('x')"), write)
        self.assertEqual(src.count("watcher_start()"), 2)           # definition + call
        self.assertEqual(src.count("collector_start()"), 2)
        # a start that fails stops the launch (an exception) rather than carrying on
        self.assertIn("raise RuntimeError('the USB watcher did not log its start record: no reboot')", src)
        self.assertIn("raise RuntimeError('the collector did not log a poll of the USB bus: no reboot')", src)
        self.assertIn("if report['device_write_started'] and not report['reboot_sent'] and not a.restore:", src)

    @source_pin
    def test_the_heartbeat_vocabulary_is_the_one_the_real_launcher_writes(self):
        d, l = DRIVER.read_text(), LAUNCH.read_text()
        for event in ("poll", "error", "start"):
            self.assertIn('self.emit("%s"' % event, l)
        self.assertIn("'poll' in ev", d)
        self.assertIn("'error' in ev", d)
        self.assertIn("--out", l)
        self.assertIn("--heartbeat", l)
        self.assertIn("--seconds", l)
        self.assertIn("'--out',str(archive),'--heartbeat',str(log),'--seconds',str(COLLECT_S)", d)

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
            self.assertIn(line, new, "missing from the NAT-049 driver: " + line)

    @source_pin
    def test_the_driver_differs_from_the_nat048_driver_only_where_the_task_says(self):
        removed = [l[2:] for l in difflib.ndiff(code_lines(NAT048_DRIVER), code_lines(DRIVER)) if l.startswith("- ")]
        self.assertEqual(removed, [
            "'loader-diag-reset':dict(",
            "NEW_SHA='a3189ca7914b48b0b5d3a575c2936b6425bccdafde16e66c34fedf1f3d1ea34e',",
            "CANARY_SHA='b79aeecc689c02c7a95ee487fb4a4b808ef8915292e0888122de9be983acaa14',  # Image.payload (loader + XNU payload + ADT)",
            "CANARY_LEN=21771872),",
            "'loader-diag-reset-bl':dict(",
            "NEW_SHA='d4e1454c198379328c91fc63a5aaf26e58c1747e2b696ca1b92719211bedfebd',",
            "CANARY_SHA='b05349eb5bc048c3b78694c3f14b3e58def30a7f74b45bd0f3b6d229fb6ef936',",
            "CANARY_LEN=21771872),",
            "PACKAGE=ROOT/'artifacts/nat-044/package-002'",
            "WATCH_S=240      # the watcher outlives the reboot by about this long: SEC_UPLOAD came at about +95 s and left at about +118 s in runs 001-009",
            "WATCHER=HERE/'usb_watch.py'",
            "found=sorted((ROOT/'docs/decisions').glob('*-nat046-%s-single-run-*.md'%image))",
            "report['decision_file']=gate(a.image,cfg).name;save()",
            "report['outcome']='ready-read-only';save();print(report['outcome']);return 0",
            "marker=ROOT/('artifacts/nat-048/native-attempt-%s-used.json'%a.image)",
            "report['outcome']='native-attempt-started';save();print(json.dumps(dict(outcome=report['outcome'],image=a.image,image_sha256=NEW_SHA,"
            "reboot_requested_at=report['reboot_requested_at'],usb_log=report['watcher']['log'])));return 0",
        ])

    @source_pin
    def test_each_failed_launch_step_stops_its_own_process_and_the_abort_handler_stops_all(self):
        # watcher (inherited from NAT-048), collector (new here) and the abort handler: three places that stop a process before the reboot
        self.assertEqual(code_lines(DRIVER).count("if proc.poll() is None:proc.terminate()"), 3)

    @source_pin
    def test_the_driver_is_the_nat048_driver_plus_the_collector_gates_and_nothing_else_is_spawned(self):
        added = [l[2:] for l in difflib.ndiff(code_lines(NAT048_DRIVER), code_lines(DRIVER)) if l.startswith("+ ")]
        text = "\n".join(added)
        for forbidden in ("adb", "su -c", "sudo", "dd of", "os.kill", "rmtree", "unlink", "write_bytes"):
            self.assertNotIn(forbidden, text.replace("'adb','reboot','recovery'", ""), "the added code must not add a device or host action: " + forbidden)

    @source_pin
    def test_the_udev_rule_and_its_checker_are_shipped_and_named_by_the_driver(self):
        src = DRIVER.read_text()
        self.assertTrue(RULE.exists() and ACCESS.exists())
        self.assertIn("docs/procedures/nat-049/70-s24-usbmon.rules", src)
        self.assertIn("HOST_ACCESS=HERE/'host_access.py'", src)
        self.assertIn("VENV_PY=ROOT/'artifacts/recovery-rescue-20261110-01/venv/bin/python'", src)


class OpenGateFlow(unittest.TestCase):
    """The driver in a scratch tree with fake decision files and registry, a fake adb that models the RECOVERY block in a file, the
    real NAT-048 watcher pointed at a fake sysfs through a one-file wrapper, and stand-ins for the collector launcher and the udev
    check (their real behaviour is tested in the Launcher and HostAccess layers; the production driver has no test hook)."""

    @classmethod
    def setUpClass(cls):
        needed = [STOCK, PACKAGE / "package.json"] + [PACKAGE / i / "recovery.img" for i in IMAGES]
        for p in needed:
            if not p.exists():
                raise unittest.SkipTest("missing %s" % p)
        cls.tmp = Path(tempfile.mkdtemp(prefix="nat049-"))
        t = cls.tmp
        drv = t / "docs/procedures/nat-049"
        drv.mkdir(parents=True)
        shutil.copy(DRIVER, drv / "session_usblog.py")
        (drv / "collector_launch.py").write_text(STUB_COLLECTOR)
        (drv / "host_access.py").write_text(STUB_ACCESS)
        (t / "docs/procedures/nat-048").mkdir(parents=True)
        (t / "docs/procedures/nat-048/usb_watch.py").write_text(WRAPPER)
        (t / "docs/decisions").mkdir(parents=True)
        (t / "state").mkdir()
        for rel in ("package.json",) + tuple("%s/recovery.img" % i for i in IMAGES):
            dst = t / "artifacts/nat-047/package-001" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(PACKAGE / rel, dst)
        (t / "devices/recovery/backups/2026-11-10").mkdir(parents=True)
        os.symlink(STOCK, t / "devices/recovery/backups/2026-11-10/recovery.img")
        (t / "bin").mkdir()
        adb = t / "bin/adb"
        adb.write_text(FAKE_ADB.replace("{python}", sys.executable))
        adb.chmod(0o755)
        cls.venv = t / "artifacts/recovery-rescue-20261110-01/venv/bin/python"
        cls.venv.parent.mkdir(parents=True)
        cls.driver = drv / "session_usblog.py"
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
        for p in (self.tmp / "artifacts/nat-049").glob("native-attempt-*") if (self.tmp / "artifacts/nat-049").exists() else []:
            p.unlink()
        if self.venv.is_symlink() or self.venv.exists():
            self.venv.unlink()
        os.symlink(sys.executable, self.venv)
        self.n = 0
        self.decide(PLAIN)
        self.registry()

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def decide(self, image, **kw):
        (self.tmp / "docs/decisions" / decision_name(image)).write_text(decision_text(image, **kw))

    def registry(self, image=PLAIN, native=True, value=True, cites="auto", done=("NAT-039", "NAT-046"), extra_first=(), drop_permission=False, tasks=None):
        """state/lab.json as lab.py would hold it after `project permit` for this decision."""
        cite = "docs/decisions/" + decision_name(image) if cites == "auto" else cites
        decisions = list(extra_first) + ([dict(scope="native", value=value, decision=cite, owner="agent", at="2026-11-12T00:00:00+00:00")] if cite is not None else [])
        project = dict(permissions={} if drop_permission else dict(native=native, android=True), permission_decisions=decisions)
        if tasks is None:
            tasks = [dict(id=t, status="done") for t in done] + [dict(id="NAT-043", status="pending")]
        (self.tmp / "state/lab.json").write_text(json.dumps(dict(project=project, tasks=tasks)))

    def run_driver(self, *mode, image=PLAIN, env_extra=None, out=None):
        self.n += 1
        out = out or self.base / ("out%d" % self.n)
        env = {"PATH": f"{self.tmp / 'bin'}:/usr/bin:/bin", "HOME": str(self.tmp), "FAKE_DEVICE_DIR": str(self.base), "FAKE_SYSFS": str(self.sysfs),
               "FAKE_WATCH_LOG": str(out / "usb-events.jsonl"), "FAKE_HEARTBEAT": str(out / "collector-heartbeat.jsonl"), "REAL_WATCHER": str(NAT048_WATCH)}
        env.update(env_extra or {})
        r = subprocess.run([sys.executable, str(self.driver), "--image", image, "--out", str(out), *mode], capture_output=True, text=True, env=env, timeout=300)
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

    def device_sha(self):
        return sha256(self.base / "recovery.bin")

    def marker(self, image=PLAIN):
        return self.tmp / ("artifacts/nat-049/native-attempt-%s-used.json" % image)

    def assertUntouched(self, rep=None, adb=False):
        """Nothing was written, nothing rebooted, no marker, no detached process; with adb=True not even a call."""
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

    def wait_events(self, out, pred, timeout=15):
        end = time.time() + timeout
        log = out / "usb-events.jsonl"
        while time.time() < end:
            rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []
            if rows and pred(rows):
                return rows
            time.sleep(0.05)
        self.fail("timed out waiting for the watcher log: %s" % (log.read_text() if log.exists() else "<none>"))

    def wait_dead(self, pid, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if not alive(pid):
                return True
            time.sleep(0.05)
        return False

    # -- the read-only preflight
    def test_preflight_is_read_only_and_proves_the_host_side_first(self):
        r, rep, out = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "ready-read-only")
        self.assertIsNone(rep["registry_blocker"])
        self.assertUntouched(rep)
        self.assertEqual(rep["watcher_selftest"]["events"], ["start", "stop"])
        self.assertIn("grant", rep["host_access"])
        self.assertTrue(rep["collector_selftest"]["result"]["ok"])
        self.assertTrue((out / "usb-selftest.jsonl").exists())
        order = self.order()
        self.assertEqual(order.index("access"), 0)
        self.assertLess(order.index("access"), order.index("collector-selftest"))
        self.assertLess(order.index("collector-selftest"), order.index("adb get-state"))
        self.assertLess(order.index("adb get-state"), order.index("watcher-selftest"))
        self.assertNotIn("collector-start", order)
        self.assertNotIn("watcher-start", order)

    def test_a_closed_registry_makes_the_preflight_say_so_and_stops_every_launch_before_adb(self):
        self.registry(native=False)
        r, rep, out = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "ready-read-only-registry-closed")
        self.assertEqual(rep["registry_blocker"], "registry native permission is not set: no launch")
        self.assertUntouched(rep)
        calls, order = len(self.calls()), len(self.order())
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stopped")
        self.assertEqual(rep["error"], "registry native permission is not set: no launch")
        self.assertUntouched(rep)
        self.assertEqual((len(self.calls()), len(self.order())), (calls, order), "the launch stopped before any adb call and before the host checks")

    def test_every_registry_shortfall_closes_the_launch(self):
        name = decision_name(PLAIN)
        other = dict(scope="native", value=True, decision="docs/decisions/0001-something-else.md", owner="agent", at="x")
        cases = [
            ("native false", dict(native=False), "registry native permission is not set"),
            ("native missing", dict(drop_permission=True), "registry native permission is not set"),
            ("no decision recorded", dict(cites=None), "does not cite %s" % name),
            ("decision of another file", dict(cites="docs/decisions/0001-something-else.md"), "does not cite %s" % name),
            ("decision without the directory", dict(cites=name), "does not cite %s" % name),
            ("value false in the last decision", dict(value=False), "does not cite %s" % name),
            ("only a non-native decision cites it", dict(extra_first=[dict(scope="android", value=True, decision="docs/decisions/" + name, owner="a", at="x")], cites=None),
             "does not cite %s" % name),
            ("NAT-039 not done", dict(done=("NAT-046",)), "precondition tasks are not done: NAT-039"),
            ("NAT-046 not done", dict(done=("NAT-039",)), "precondition tasks are not done: NAT-046"),
            ("neither done", dict(done=()), "precondition tasks are not done: NAT-039, NAT-046"),
            ("task in progress", dict(tasks=[dict(id="NAT-039", status="in_progress"), dict(id="NAT-046", status="done")]), "NAT-039"),
            ("task blocked", dict(tasks=[dict(id="NAT-039", status="done"), dict(id="NAT-046", status="blocked")]), "NAT-046"),
        ]
        for label, kw, why in cases:
            with self.subTest(label):
                self.registry(**kw)
                r, rep, _ = self.run_driver("--execute")
                self.assertEqual(r.returncode, 2, (label, r.stdout, r.stderr))
                self.assertIn(why, rep["error"], label)
                self.assertUntouched(rep, adb=True)
        # an older decision for the same scope does not open it when a later one closed it, and a later one opens it again
        self.registry(extra_first=[dict(scope="native", value=True, decision="docs/decisions/" + name, owner="a", at="x")], value=False)
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2)
        self.registry(extra_first=[other])
        r, rep, out = self.run_driver()
        self.assertEqual(rep["outcome"], "ready-read-only", "the LAST native decision is the one that counts")

    # -- the host side: udev rule and collector self-test
    def test_each_host_check_failure_stops_before_any_adb_call_in_every_non_restore_mode(self):
        cases = [
            ("no udev rule", {"FAKE_ACCESS": "missing"}, "no udev rule gives this user write access"),
            ("exit 0 but nothing found", {"FAKE_ACCESS": "exit0-null"}, "no udev rule gives this user write access"),
            ("found but exit 2", {"FAKE_ACCESS": "exit2-found"}, "no udev rule gives this user write access"),
            ("collector self-test fails", {"FAKE_SELFTEST": "fail"}, "collector self-test failed"),
            ("self-test says ok=false with exit 0", {"FAKE_SELFTEST": "false"}, "collector self-test failed"),
            ("self-test exit 2 with ok=true", {"FAKE_SELFTEST": "exit2"}, "collector self-test failed"),
            ("monitor already on the bus", {"FAKE_MONITOR_NOW": "1"}, "already on the bus"),
            ("self-test does not report the monitor count", {"FAKE_SELFTEST": "nomonitor"}, "already on the bus"),
        ]
        for label, env, why in cases:
            for mode in ((), ("--execute",)):
                with self.subTest(label, mode=mode):
                    r, rep, _ = self.run_driver(*mode, env_extra=env)
                    self.assertEqual(r.returncode, 2, (label, mode, r.stdout, r.stderr))
                    self.assertEqual(rep["outcome"], "stopped")
                    self.assertIn(why, rep["error"])
                    self.assertUntouched(rep, adb=True)
        for label, env in (("access garbage", {"FAKE_ACCESS": "garbage"}), ("self-test garbage", {"FAKE_SELFTEST": "garbage"})):
            r, rep, _ = self.run_driver("--execute", env_extra=env)
            self.assertEqual(r.returncode, 2, label)
            self.assertEqual(rep["outcome"], "stopped")
            self.assertUntouched(rep, adb=True)

    def test_a_missing_pyusb_venv_stops_before_any_adb_call(self):
        self.venv.unlink()
        for mode in ((), ("--execute",)):
            r, rep, _ = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("the pyusb venv python is missing", rep["error"])
            self.assertUntouched(rep, adb=True)

    def test_restore_needs_none_of_the_launch_gates(self):
        r, _, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.device_sha(), STOCK_SHA)
        (self.tmp / "state/lab.json").unlink()                           # no registry at all
        self.venv.unlink()                                               # no venv
        before = len(self.order())
        r, rep, out = self.run_driver("--restore", env_extra={"FAKE_ACCESS": "missing", "FAKE_SELFTEST": "fail", "FAKE_MONITOR_NOW": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stock-written-readback-confirmed")
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertEqual(self.reboots(), ["reboot recovery"], "only the launch rebooted")
        self.assertFalse(rep["reboot_sent"])
        for key in ("watcher", "watcher_selftest", "collector", "collector_selftest", "host_access", "registry_blocker"):
            self.assertNotIn(key, rep, key)
        new = self.order()[before:]
        for tag in ("access", "collector-selftest", "collector-start", "watcher-start", "watcher-selftest"):
            self.assertNotIn(tag, new, tag)

    # -- the launch
    def test_execute_writes_reads_back_starts_watcher_then_collector_then_reboots_once(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "native-attempt-started")
        new_sha = pinned(PLAIN)["recovery_sha256"]
        self.assertEqual(self.device_sha(), new_sha)
        self.assertEqual(rep["readback_sha256"], new_sha)
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296"])
        self.assertEqual(self.reboots(), ["reboot recovery"])
        order = self.order()
        write = order.index("adb write")
        readback = max(i for i, c in enumerate(order) if c == "adb sha256sum")
        self.assertLess(write, readback)
        self.assertLess(readback, order.index("watcher-start"))
        self.assertLess(order.index("watcher-start"), order.index("collector-start"))
        self.assertLess(order.index("collector-start"), order.index("adb reboot"))
        self.assertEqual(order[-1], "adb reboot")
        self.assertEqual(order.count("adb reboot"), 1)
        self.assertLess(order.index("access"), order.index("adb get-state"))
        self.assertLess(order.index("collector-selftest"), order.index("adb get-state"))
        self.assertEqual((self.base / "reboot-saw-watcher").read_text(), "yes", "the watcher had logged its start record before the reboot was sent")
        self.assertEqual((self.base / "reboot-saw-collector").read_text(), "yes", "the collector had logged a poll of the bus before the reboot was sent")
        self.assertTrue(rep["watcher"]["start_record_seen"])
        self.assertTrue(rep["collector"]["first_poll_seen"])
        self.assertEqual(rep["decision_file"], decision_name(PLAIN))
        self.assertLess(rep["watcher"]["started_at"], rep["collector"]["started_at"])
        self.assertLess(rep["collector"]["started_at"], rep["reboot_requested_at"])
        self.assertEqual(json.loads(self.marker().read_text())["image_sha256"], new_sha)
        printed = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(printed["image"], PLAIN)
        self.assertEqual(printed["usb_log"], str(out / "usb-events.jsonl"))
        self.assertEqual(printed["archive"], str(out / "archive"))
        self.assertEqual(printed["reboot_requested_at"], rep["reboot_requested_at"])

    def test_the_collector_command_line_and_the_two_detached_sessions(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = (self.base / "collector-argv").read_text().split("\0")
        self.assertEqual(argv, ["--out", str(out / "archive"), "--heartbeat", str(out / "collector-heartbeat.jsonl"), "--seconds", "360"])
        self.assertEqual((rep["watcher"]["seconds"], rep["collector"]["seconds"]), (360, 360))
        me = os.getpid()
        for key in ("watcher", "collector"):
            pid = rep[key]["pid"]
            os.kill(pid, 0)                                              # still alive after the driver exited
            self.assertNotEqual(os.getpgid(pid), os.getpgid(me))
            self.assertEqual(os.getsid(pid), pid, "%s is a session leader of its own" % key)
            self.assertIn(b"\x00360\x00", Path("/proc/%d/cmdline" % pid).read_bytes() + b"\x00")
        cmd = Path("/proc/%d/cmdline" % rep["collector"]["pid"]).read_bytes().split(b"\0")
        self.assertEqual(cmd[0].decode(), str(self.venv), "the collector runs with the pyusb venv python")
        self.assertEqual(cmd[1], b"-I")
        self.assertEqual(Path(cmd[2].decode()).name, "collector_launch.py")

    def test_the_watcher_outlives_the_driver_and_sees_the_device_leave_and_return(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pid = rep["watcher"]["pid"]
        add_dev(self.sysfs, "1-2", pid="6860", product="SM-S921B")
        self.wait_events(out, lambda e: any(x["event"] == "appear" for x in e))
        rm_dev(self.sysfs, "1-2")
        add_dev(self.sysfs, "1-2", vid="1209", pid="0001", product="", devnum="9")
        rows = self.wait_events(out, lambda e: any(x["event"] == "appear" and x.get("vid") == "1209" for x in e))
        self.assertEqual([x["event"] for x in rows][:1], ["start"])
        os.kill(pid, signal.SIGTERM)
        self.wait_events(out, lambda e: e[-1]["event"] == "stop")

    def test_a_slow_watcher_or_collector_delays_the_reboot_instead_of_missing_its_window(self):
        r, rep, out = self.run_driver("--execute", env_extra={"FAKE_WATCHER_DELAY": "1.5", "FAKE_COLLECTOR_DELAY": "1.5"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.base / "reboot-saw-watcher").read_text(), "yes")
        self.assertEqual((self.base / "reboot-saw-collector").read_text(), "yes")
        self.assertTrue(rep["watcher"]["start_record_seen"] and rep["collector"]["first_poll_seen"])
        hb = [json.loads(l) for l in (out / "collector-heartbeat.jsonl").read_text().splitlines()]
        t0 = datetime.datetime.fromisoformat(rep["reboot_requested_at"]).timestamp()
        poll = next(e for e in hb if e["event"] == "poll")
        self.assertLessEqual(poll["t_unix"], t0, "the first poll precedes the reboot request: the collector covers T0")

    def test_the_report_fits_the_analyzer_and_the_logs_cover_t0(self):
        r, rep, out = self.run_driver("--execute")
        t0 = datetime.datetime.fromisoformat(rep["reboot_requested_at"]).timestamp()
        events = self.wait_events(out, lambda e: any(x["event"] == "start" for x in e))
        self.assertLessEqual(events[0]["t_unix"], t0)
        an = load(ANALYZE, "nat049_analyzer_for_report")
        empty = self.base / "no-archive"
        out_an = an.analyze(empty, events, rep, PLAIN)
        self.assertNotIn("no reboot request", out_an["why"], "the report carries what the analyzer needs from it")
        self.assertEqual(out_an["verdict"], "undetermined")

    def test_the_second_image_uses_its_own_pins_decision_registry_entry_and_marker(self):
        self.decide(FAULT)
        self.registry(image=FAULT)
        r, rep, out = self.run_driver("--execute", image=FAULT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.device_sha(), pinned(FAULT)["recovery_sha256"])
        self.assertTrue(self.marker(FAULT).exists())
        self.assertFalse(self.marker(PLAIN).exists())
        self.assertEqual(self.reboots(), ["reboot recovery"])
        self.assertEqual(rep["decision_file"], decision_name(FAULT))

    def test_the_registry_entry_of_one_image_does_not_open_the_other(self):
        self.decide(FAULT)                                               # the fault image has its decision file ...
        r, rep, _ = self.run_driver("--execute", image=FAULT)            # ... but the registry cites the plain image's
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("does not cite %s" % decision_name(FAULT), rep["error"])
        self.assertUntouched(rep, adb=True)

    def test_a_second_execute_is_refused_by_the_marker_before_any_write(self):
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        (self.base / "writes").unlink()
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stopped")
        self.assertFalse(rep["device_write_started"] or rep["reboot_sent"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), ["reboot recovery"], "exactly one reboot over both sessions")
        self.assertNotIn("watcher", rep)
        self.assertNotIn("collector", rep)

    def test_the_marker_of_one_image_does_not_block_the_other(self):
        self.decide(FAULT)
        self.registry(image=FAULT)
        self.marker(PLAIN).parent.mkdir(parents=True, exist_ok=True)
        self.marker(PLAIN).write_text("{}")
        r, rep, _ = self.run_driver("--execute", image=FAULT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # -- failures after the write
    def test_a_readback_mismatch_restores_stock_and_starts_nothing(self):
        (self.base / "corrupt-first-write").write_text("")
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("readback mismatch", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["reboot_sent"])
        self.assertNotIn("watcher", rep)
        self.assertNotIn("collector", rep)
        self.assertNotIn("watcher-start", self.order())
        self.assertNotIn("collector-start", self.order())
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296", "100663296"])

    def test_a_watcher_that_cannot_start_restores_stock_and_the_collector_is_never_started(self):
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_WATCHER_FAIL_RUN": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("watcher did not log its start record", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["reboot_sent"])
        self.assertFalse(rep["watcher"]["start_record_seen"])
        self.assertNotIn("collector", rep)
        self.assertNotIn("collector-start", self.order())
        self.assertEqual(self.device_sha(), STOCK_SHA)

    def test_a_collector_that_exits_restores_stock_never_reboots_and_stops_the_watcher(self):
        r, rep, out = self.run_driver("--execute", env_extra={"FAKE_COLLECTOR_EXIT": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("collector did not log a poll", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["reboot_sent"])
        self.assertFalse(rep["collector"]["first_poll_seen"])
        self.assertTrue(rep["watcher"]["start_record_seen"])
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertTrue(self.wait_dead(rep["watcher"]["pid"]), "the watcher of an aborted launch is stopped")

    def test_a_collector_error_is_final_even_if_a_poll_follows_it(self):
        for mode in ("error-only", "then-poll"):
            with self.subTest(mode):
                shutil.copyfile(STOCK, self.base / "recovery.bin")
                if self.marker().exists():
                    self.marker().unlink()
                r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_COLLECTOR_ERROR": mode})
                self.assertEqual(r.returncode, 2, (mode, r.stdout, r.stderr))
                self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
                self.assertIn("collector did not log a poll", rep["error"])
                self.assertEqual(self.reboots(), [])
                self.assertFalse(rep["collector"]["first_poll_seen"])
                self.assertTrue(self.wait_dead(rep["collector"]["pid"]), "a collector that hit an error is stopped")
                self.assertTrue(self.wait_dead(rep["watcher"]["pid"]))

    def test_a_collector_that_never_polls_is_given_fifteen_seconds_not_forever(self):
        t = time.time()
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_COLLECTOR_DELAY": "40"})
        took = time.time() - t
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("collector did not log a poll", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertLess(took, 120)
        self.assertTrue(self.wait_dead(rep["collector"]["pid"]))

    def gap_after(self, rep, key):
        """Seconds from the start of `key` (watcher/collector) to the next command the driver ran: how long it waited for the start proof."""
        t = datetime.datetime.fromisoformat(rep[key]["started_at"]).timestamp()
        nxt = [datetime.datetime.fromisoformat(c["started_at"]).timestamp() for c in rep["commands"] if datetime.datetime.fromisoformat(c["started_at"]).timestamp() > t]
        return nxt[0] - t

    def test_a_start_that_failed_outright_is_reported_at_once_not_after_the_timeout(self):
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_WATCHER_FAIL_RUN": "1"})
        self.assertLess(self.gap_after(rep, "watcher"), 5)
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        self.marker().unlink()
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_COLLECTOR_EXIT": "1"})
        self.assertLess(self.gap_after(rep, "collector"), 5)

    def test_a_watcher_that_is_too_slow_to_log_its_start_is_stopped_and_stock_restored(self):
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_WATCHER_DELAY": "60"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("watcher did not log its start record", rep["error"])
        self.assertTrue(self.wait_dead(rep["watcher"]["pid"]))
        self.assertNotIn("collector", rep)
        self.assertEqual(self.reboots(), [])
        self.assertEqual(self.device_sha(), STOCK_SHA)

    def test_a_reboot_command_that_fails_leaves_the_logging_running_and_recovery_alone(self):
        r, rep, out = self.run_driver("--execute", env_extra={"FAKE_REBOOT_FAIL": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stopped")
        self.assertTrue(rep["reboot_sent"], "the request was made; whether the phone obeyed is not known")
        self.assertEqual(self.device_sha(), pinned(PLAIN)["recovery_sha256"], "no write after the request: the stock restore is the separate --restore step")
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296"])
        for key in ("watcher", "collector"):
            self.assertTrue(alive(rep[key]["pid"]), "%s keeps logging after a reboot request" % key)

    def test_a_package_record_that_does_not_match_the_pins_opens_nothing(self):
        pj = self.tmp / "artifacts/nat-047/package-001/package.json"
        target = os.readlink(pj)
        good = json.loads(Path(target).read_text())

        def edit(fn):
            p = copy.deepcopy(good)
            fn(p)
            return p
        variants = [
            ("flashed", edit(lambda p: p.__setitem__("flashed", True)), "flashed"),
            ("stock", edit(lambda p: p.__setitem__("stock_sha256", "0" * 64)), "stock_sha256"),
            ("recovery", edit(lambda p: p["images"][PLAIN].__setitem__("recovery_sha256", "0" * 64)), "recovery_sha256"),
            ("payload", edit(lambda p: p["images"][PLAIN].__setitem__("payload_sha256", "0" * 64)), "payload_sha256"),
            ("length", edit(lambda p: p["images"][PLAIN].__setitem__("payload_bytes", p["images"][PLAIN]["payload_bytes"] + 1)), "payload_bytes"),
            ("offset", edit(lambda p: p["images"][PLAIN].__setitem__("payload_offset", 4096)), "payload_offset"),
        ]
        try:
            for label, rec, _ in variants:
                with self.subTest(label):
                    pj.unlink()
                    pj.write_text(json.dumps(rec))
                    for mode in ((), ("--execute",)):
                        r, rep, _ = self.run_driver(*mode)
                        self.assertEqual(r.returncode, 2, (label, mode, r.stdout))
                        self.assertEqual(rep["outcome"], "stopped")
                        self.assertUntouched(rep, adb=True)
        finally:
            if pj.is_symlink() or pj.exists():
                pj.unlink()
            os.symlink(target, pj)

    def test_a_failing_watcher_selftest_stops_before_any_write(self):
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_WATCHER_FAIL_SELFTEST": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("self-test failed", rep["error"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())
        self.assertNotIn("collector-start", self.order())
        r, rep, _ = self.run_driver(env_extra={"FAKE_WATCHER_FAIL_SELFTEST": "1"})
        self.assertEqual(r.returncode, 2, "the read-only preflight reports a broken watcher too")

    # -- the decision file
    def test_a_decision_that_does_not_name_the_hashes_or_decision_0019_opens_nothing(self):
        for kw in (dict(with_recovery=False), dict(with_payload=False), dict(with_0019=False)):
            self.decide(PLAIN, **kw)
            before = len(self.calls())
            for mode in ((), ("--execute",), ("--restore",)):
                r, rep, _ = self.run_driver(*mode)
                self.assertEqual(r.returncode, 2, (kw, mode, r.stdout))
                self.assertIn("does not name", rep["error"])
            self.assertEqual(len(self.calls()), before, "no adb call: %r" % (kw,))
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.order(), [], "not even the host checks ran")

    def test_two_decision_files_for_one_image_are_ambiguous(self):
        (self.tmp / "docs/decisions" / decision_name(PLAIN, "0098")).write_text(decision_text(PLAIN))
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ambiguous (2 found)", rep["error"])
        self.assertEqual(self.calls(), [])

    def test_a_decision_of_the_other_image_does_not_open_this_one(self):
        for p in (self.tmp / "docs/decisions").glob("*"):
            p.unlink()
        self.decide(FAULT)
        r, rep, _ = self.run_driver("--execute", image=PLAIN)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_the_decision_of_the_other_image_beside_this_ones_is_not_ambiguity(self):
        self.decide(FAULT)                       # both images have a decision file: the pattern of one must not match the file of the other
        r, rep, _ = self.run_driver()
        self.assertEqual((r.returncode, rep.get("outcome")), (0, "ready-read-only"), (r.stdout, rep.get("error")))
        self.assertEqual(rep["decision_file"], decision_name(PLAIN))

    def test_an_existing_output_directory_is_never_reused(self):
        out = self.base / "reused"
        out.mkdir()
        (out / "report.json").write_text('{"previous": "run"}\n')
        r, rep, _ = self.run_driver(out=out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FileExistsError", r.stderr)
        self.assertEqual(json.loads((out / "report.json").read_text()), {"previous": "run"}, "the earlier report is not overwritten")
        self.assertEqual(self.calls(), [])
        self.assertUntouched(adb=True)

    def test_a_second_session_cannot_run_while_the_recovery_write_lock_is_held(self):
        lock = self.tmp / "artifacts/nat-022/recovery-write.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r, _, _ = self.run_driver("--execute")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("BlockingIOError", r.stderr)
        self.assertUntouched(adb=True)

    # -- the phone-side gates inherited from NAT-048
    def test_a_busy_remote_dd_blocks_every_write(self):
        (self.base / "dd-busy").write_text("")
        for mode in ((), ("--execute",), ("--restore",)):
            r, rep, _ = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, (mode, r.stdout, r.stderr))
            self.assertFalse((self.base / "writes").exists(), mode)
            self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_launch_refuses_a_recovery_that_is_not_stock(self):
        data = bytearray(STOCK.read_bytes())
        data[100] ^= 0xFF
        (self.base / "recovery.bin").write_bytes(bytes(data))
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unchanged stock RECOVERY", rep["error"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())
        self.assertNotIn("watcher-start", self.order())

    def test_launch_refuses_a_low_battery(self):
        (self.base / "battery").write_text("49")
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_the_candidate_packages_the_payload_not_the_loader_only_image(self):
        pkg = json.loads((PACKAGE / "package.json").read_text())
        build = ROOT / pkg["build"]
        for image in IMAGES:
            p = pkg["images"][image]
            img = (PACKAGE / image / "recovery.img").read_bytes()
            payload = build / image / "Image.payload"
            if not payload.exists():
                self.skipTest("%s not present" % pkg["build"])
            self.assertEqual(hashlib.sha256(img[2048:2048 + p["payload_bytes"]]).hexdigest(), p["payload_sha256"])
            self.assertEqual(sha256(payload), p["payload_sha256"])


# ------------------------------------------------------------------------------------------------------------ simulated NAT-047 loader
_t47 = {}


def t47():
    """The NAT-047 test module: the real built loader.elf of both images executed in unicorn against the NAT-041 DWC3 model, with the
    NAT-041 collector on the other side. Skips the layer without unicorn, a C compiler, zig or the local NAT-020 build-003 artifacts."""
    if "m" not in _t47:
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("unicorn is missing (an interpreter with unicorn and capstone runs this layer)")
        try:
            m = load(PROC / "nat-047/test_nat047.py", "nat049_nat047")
        except Exception as e:                                       # noqa: BLE001  (a missing toolchain is a skip, not a failure)
            raise unittest.SkipTest("the NAT-047 simulator does not load here: %s" % e)
        if not (m.have_loader and m.have_zig and m.have_cc and m.HAVE_SIM):
            raise unittest.SkipTest("the NAT-047 simulator needs unicorn, cc, zig and the local NAT-020 build-003 artifacts")
        _t47["m"] = m
    return _t47["m"]


class Simulated(unittest.TestCase):
    """The analyzer on the archives of the REAL loader: loader.elf of loader-diag-usbmon / -fault (built by NAT-047's build.py from the
    pinned sources) is executed instruction by instruction in unicorn; its usbmon engine is driven by the NAT-041 DWC3 model, and the
    unmodified NAT-041 collector reads it. The archive is labelled `synthetic` by the rig, so every verdict here is `simulated-*` and
    the analyzer is called with allow_synthetic. What this layer establishes: the formats and numbers the analyzer expects are those the
    compiled loader emits (a host-test; the model is not the S5E9945 DWC3, and the loader's thread is a queue of calls, not S-Boot).
    The expected values come from the NAT-047 simulator's own view of the loader (its stage calls, the loader's memory, the exception
    the simulated CPU took), not from the analyzer."""
    cache = {}
    LOADER_START_S = 15.0       # assumption of the no-cable timelines: from the reboot request to the loader running (anything inside the window gives the same verdict)

    @classmethod
    def setUpClass(cls):
        cls.m = t47()
        cls.an = load(ANALYZE, "nat049_analyze_sim")
        cls.tmp = Path(tempfile.mkdtemp(prefix="nat049-sim-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls.cache.clear()

    def sim(self, key, image, *, plug=True, late_s=0.0, follow=True):
        """-> (the NAT-047 result record, a private copy of the archive). The run is made once per key; the simulator owns a fixed mapping, so it is closed at once."""
        m = self.m
        if key not in self.cache:
            clock = Stamp(BASE)
            run = None
            try:
                with warnings.catch_warnings(), mock.patch.object(m.R.A, "stamp", clock):
                    warnings.simplefilter("ignore", ResourceWarning)                 # NAT-045's a64sim reads the ELF with a bare open()
                    run = m.Run(image, dev_kw=None if follow else dict(follow=False))
                    if follow:
                        self.assertTrue(run.until_up(), "the engine did not come up")
                    if late_s:
                        run.record_until(late_s)
                    rig = run.host()
                    if plug:
                        rig.plug()
                    clock.t = FIRST
                    run.collect(70.0)
                res = run.finish()
                dest = self.tmp / ("cache-%s" % key)
                shutil.copytree(rig.out, dest)
                self.cache[key] = (res, dest)
            except m.S.RegionUnavailable as e:
                raise unittest.SkipTest(str(e))
            finally:
                if run is not None:
                    run.close()
        res, src = self.cache[key]
        dst = Path(tempfile.mkdtemp(dir=self.tmp)) / "archive"
        shutil.copytree(src, dst)
        return res, dst

    def judge(self, d, image, events=None, **kw):
        return self.an.analyze(d, usb_log() if events is None else events, report(), image, **kw)

    # -- the plain image
    def test_the_plain_loader_gives_a_simulated_pass_and_never_a_pass(self):
        res, d = self.sim("plain", PLAIN)
        out = self.judge(d, PLAIN, allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-PASS", (out["why"], out["reasons"]))
        self.assertEqual(out["reasons"], [])
        out = self.judge(d, PLAIN)
        self.assertEqual(out["verdict"], "undetermined")
        self.assertIn("provenance 'synthetic'", out["why"])

    def test_the_numbers_the_analyzer_reads_are_the_loaders_own(self):
        m = self.m
        res, d = self.sim("plain", PLAIN)
        b = self.judge(d, PLAIN, allow_synthetic=True)["boot"]
        self.assertEqual(len(res.boots), 1)
        self.assertEqual(b["device_id"][16:], m.fnv1a64(PLAIN).to_bytes(8, "little").hex())        # the tag the loader derives from its image name
        self.assertEqual(b["banner"], "NAT047 %s deadline_s=45 fault=0" % PLAIN)
        self.assertEqual([tuple(s) for s in b["stages"]], list(m.STAGE_NAMES))                           # the stage calls the simulated loader thread made
        self.assertEqual(b["ladder"]["R"]["nrec"], b["ladder_op_lines"]["R"])
        self.assertEqual(b["ladder"]["W"]["nrec"], res.g["nrec"])                                         # the count in the loader's memory at the end of the run
        self.assertEqual(b["ladder_op_lines"]["W"], res.g["nrec"])
        self.assertEqual((b["ladder"]["R"]["err"], b["ladder"]["W"]["err"]), (0, 0))
        frames = res.boots[0]["frames"]
        self.assertEqual(b["records"], len([f for f in frames if "dev_seq" in f]))
        self.assertEqual(b["first_dev_seq"], 0)
        self.assertEqual(b["drop_frames"], 0)
        self.assertEqual(res.g["up"], 1)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.manifest["outcome"], "complete-received-stream")

    # -- the fault image
    def test_the_fault_loader_gives_a_simulated_pass_with_the_exception_the_simulated_cpu_took(self):
        res, d = self.sim("fault", FAULT)
        out = self.judge(d, FAULT, allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-PASS", (out["why"], out["reasons"]))
        b = out["boot"]
        self.assertEqual(len(res.excs), 1)
        _, pc, insn = res.excs[0]
        self.assertEqual(insn, self.m.BRK_1234)
        self.assertEqual([(f["esr"], f["elr"], f["far"], f["stage"]) for f in b["exception_frames"]], [(FAULT_ESR, pc, self.m.S.EXC_FAR, 0x1F)])
        self.assertEqual([(f["esr"], f["elr"], f["far"], f["valid"]) for f in b["exception_page"]], [(FAULT_ESR, pc, self.m.S.EXC_FAR, 1)])
        self.assertEqual(b["stages"][-1][0], 0x1F)
        self.assertEqual(len(b["exception_texts"]), 1)
        self.assertEqual(b["banner"], "NAT047 %s deadline_s=45 fault=1" % FAULT)

    def test_the_plain_loader_raises_no_exception(self):
        res, d = self.sim("plain", PLAIN)
        b = self.judge(d, PLAIN, allow_synthetic=True)["boot"]
        self.assertEqual(res.excs, [])
        self.assertEqual((b["exception_frames"], b["exception_page"], b["exception_texts"]), ([], [], []))

    def test_the_archive_of_one_image_is_no_evidence_for_the_other(self):
        for key, have, want in (("plain", PLAIN, FAULT), ("fault", FAULT, PLAIN)):
            with self.subTest(have=have):
                res, d = self.sim(key, have)
                out = self.judge(d, want, allow_synthetic=True)
                self.assertEqual(out["verdict"], "undetermined", out["why"])
                self.assertEqual((out["boots_of_image"], out["foreign_boots"]), (0, 1))

    # -- a host that plugs late
    def test_a_host_that_plugs_twenty_seconds_late_still_gets_every_record(self):
        res, d = self.sim("late", PLAIN, late_s=20.0)
        out = self.judge(d, PLAIN, allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-PASS", (out["why"], out["reasons"]))
        _, dp = self.sim("plain", PLAIN)
        plain = self.judge(dp, PLAIN, allow_synthetic=True)["boot"]
        b = out["boot"]
        self.assertEqual(b["first_dev_seq"], 0)
        self.assertEqual([tuple(s) for s in b["stages"]], [tuple(s) for s in plain["stages"]])
        self.assertEqual((b["ladder"]["R"]["nrec"], b["ladder"]["W"]["nrec"]), (plain["ladder"]["R"]["nrec"], plain["ladder"]["W"]["nrec"]))
        self.assertEqual(b["drop_frames"], 0)

    # -- nothing enumerates: the loader ran, the host archived nothing
    def test_no_cable_leaves_an_empty_archive_and_the_usb_log_decides(self):
        res, d = self.sim("nocable", PLAIN, plug=False)
        self.assertEqual(res.boots, [])
        self.assertEqual(res.g["up"], 1)                                                                  # the engine was up; nobody was there
        self.assertGreaterEqual(res.reset_s, 45)
        back = self.LOADER_START_S + res.reset_s                                                          # the host sees the phone again when the loader resets
        out = self.judge(d, PLAIN, usb_log(appear=None, back=back), allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-FAIL", out["why"])
        self.assertIn("although the loader ran", out["why"])
        self.assertEqual(out["boots_in_archive"], [])
        out = self.judge(d, PLAIN, usb_log(appear=None, leave=None), allow_synthetic=True)
        self.assertEqual(out["verdict"], "undetermined", "the phone never left the bus: nothing shows the loader ran")

    def test_a_stopped_ladder_is_a_run_nothing_enumerates_in(self):
        res, d = self.sim("stopped", PLAIN, plug=False, follow=False)
        self.assertEqual(res.boots, [])
        self.assertEqual(res.g["up"], 0)                                                                  # the engine never started
        self.assertNotEqual(res.g["err"], 0)                                                              # the ladder stopped with an error
        self.assertGreaterEqual(res.reset_s, 45)                                                          # and the loader still reset at its deadline
        out = self.judge(d, PLAIN, usb_log(appear=None, back=self.LOADER_START_S + res.reset_s), allow_synthetic=True)
        self.assertEqual(out["verdict"], "simulated-FAIL", out["why"])
        self.assertEqual(out["boots_in_archive"], [])


if __name__ == "__main__":
    unittest.main()
