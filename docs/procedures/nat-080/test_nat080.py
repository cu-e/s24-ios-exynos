#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-080 host tests of the session-driver derivation (derive.py -> session_nat078.py). Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-080/test_nat080.py      (opens no device, sends no command)

session_nat078.py is the only launcher of the one native run. These tests pin what the derivation promises in its docstring:
  * the committed driver IS the derivation from NAT-075's driver and the pinned package (the --check of derive.py);
  * everything in NAT-075's driver that is not on the documented list of substitutions is still there, in order (the safety sequence:
    device checks, RECOVERY-only write, readback, restore on failure, watcher, collector, ONE reboot);
  * what the derivation adds is only a delivery companion started after the collector and before the reboot, two host-only preflight checks and
    constants: it adds no device access of its own, no second reboot, no retry;
  * the constants it carries are the package's (RECOVERY and Image.payload hashes, sizes), the padded root's and the loader's receive cap, and the
    companion's send time plus margin fits inside that cap;
  * a NAT-075 driver that has drifted from what the derivation expects is refused instead of half translated;
  * every option the driver passes to the companion is one the companion accepts.
The derived driver is not run here: its execution opens the phone."""
import contextlib
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V = load("nat080_derive", HERE / "derive.py")
DELIVER = load("nat080_deliver_for_derive", HERE / "deliver_nat080.py")
PACKAGE = ROOT / "artifacts/nat-079/package-002/package.json"
PADDED = ROOT / "artifacts/nat-077/padded.json"
HAVE_ARTIFACTS = PACKAGE.exists() and PADDED.exists()
TEXT75 = (PROC / "nat-075" / "session_nat075.py").read_text()
TEXT78 = (HERE / "session_nat078.py").read_text()
DOCSTRING = re.compile(r'(#!.*\n(?:#.*\n)*)("""(?:.|\n)*?""")')
FAKE = dict(new_sha="a" * 64, payload_sha="b" * 64, payload_len=1234, root_size=16384 * 5, root_sha="c" * 64, rx_cap_s=240)


def body(text):
    """The driver without its docstring: the docstring is the only text the derivation rewrites wholesale."""
    m = DOCSTRING.match(text)
    return text.replace(m.group(2), "", 1).splitlines()


# The lines of NAT-075's driver that the derivation replaces, by the first words of each line, in file order (the whole list: any other removed line is a defect).
REPLACED = ["'loader-diag-xnu-bigwin-md1':dict(", "NEW_SHA=", "CANARY_SHA=", "CANARY_LEN=", "PACKAGE=", "WATCH_S=", "COLLECT_S=", "REQUIRED_DONE=",
            "found=sorted(", "host_access();collector_selftest()", "marker=ROOT/", "report['outcome']='native-attempt-started'"]


def diff_parts(old, new):
    """-> (the lines of `old` that are not in `new`, the lines of `new` that are not in `old`), both in file order, from a line diff."""
    removed, added = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != "equal":
            removed += old[i1:i2]
            added += new[j1:j2]
    return removed, added


class Derivation(unittest.TestCase):
    @unittest.skipUnless(HAVE_ARTIFACTS, "artifacts/nat-079/package-002 or artifacts/nat-077/padded.json is not present")
    def test_the_committed_driver_is_the_derivation_from_the_packages_values(self):
        self.assertEqual(V.derive_session(TEXT75, *V.package_values()), TEXT78)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(V.main(["--check"]), 0)

    def test_check_fails_when_the_committed_driver_differs(self):
        derived = V.derive_session(TEXT75, *FAKE.values())
        self.assertNotEqual(derived, TEXT78, "the stand-in values must not reproduce the committed driver, or this test shows nothing")
        self.assertEqual(derived.count("'%s'" % ("a" * 64)), 1)
        # the same function with the real values and one changed character differs from the committed file: --check compares whole texts
        if HAVE_ARTIFACTS:
            real = V.derive_session(TEXT75, *V.package_values())
            self.assertNotEqual(real.replace("DELIVER_S=225", "DELIVER_S=226", 1), TEXT78)

    def test_only_the_documented_lines_of_the_nat075_driver_are_replaced(self):
        removed, added = diff_parts(body(TEXT75), body(TEXT78))
        got = [next((k for k in REPLACED if l.strip().startswith(k)), "<<%s>>" % l.strip()[:50]) for l in removed]
        self.assertEqual(got, REPLACED, "every other line of NAT-075's driver, including its comments, is kept and in order")
        # each replaced line has its counterpart with the same key
        for key in REPLACED[1:]:
            self.assertEqual(sum(1 for l in added if l.strip().startswith(key)), 1, key)
        self.assertEqual(sum(1 for l in added if l.strip().startswith("'loader-diag-xnu-rx-md1':dict(")), 1)

    def test_what_is_added_has_no_device_access_no_reboot_and_no_second_write(self):
        removed, added = diff_parts(body(TEXT75), body(TEXT78))
        extra = [l for l in added if not any(l.strip().startswith(k) for k in REPLACED + ["'loader-diag-xnu-rx-md1':dict("])]
        self.assertGreater(len(extra), 30)
        text = "\n".join(extra)
        for word in ("'adb'", "'reboot'", "'fastboot'", "'odin4'", "'heimdall'", "'dd'", "'su'", "'sh'", "'bash'", "/dev/", "sda", "ADB", "RECOVERY"):
            self.assertNotIn(word, text, word)
        self.assertEqual(len(re.findall(r"subprocess\.(?:run|Popen)", text)), 2, "the self-test and the companion: nothing else is started by the added code")
        # the added code starts two things, both the venv python on the companion, and the companion is detached with no stdin
        self.assertIn("'--selftest'", text)
        self.assertIn("start_new_session=True", text)
        self.assertIn("stdin=subprocess.DEVNULL", text)

    def test_the_sole_reboot_is_after_the_watcher_the_collector_and_the_companion(self):
        lines = TEXT78.splitlines()
        reboots = [i for i, l in enumerate(lines) if "'reboot'" in l]
        self.assertEqual(len(reboots), 1, "one adb reboot in the driver, as in NAT-075's")
        self.assertEqual(len([l for l in TEXT75.splitlines() if "'reboot'" in l]), 1)
        calls = {n: [i for i, l in enumerate(lines) if l.strip() == n + "()"] for n in ("watcher_start", "collector_start", "deliver_start")}
        for n, at in calls.items():
            self.assertEqual(len(at), 1, "%s() is called once" % n)
        w, c, d = (calls[n][0] for n in ("watcher_start", "collector_start", "deliver_start"))
        self.assertTrue(w < c < d < reboots[0], (w, c, d, reboots[0]))
        indents = {len(lines[i]) - len(lines[i].lstrip()) for i in (w, c, d)}
        self.assertEqual(len(indents), 1, "the three starts are in the same block, so a failure of any one stops the launch the same way")
        sent = next(i for i, l in enumerate(lines) if "report['reboot_sent']=True" in l)
        self.assertTrue(d < sent < reboots[0], "the reboot flag is set after the companion is confirmed and right before the reboot")
        self.assertEqual([i for i, l in enumerate(lines) if "raise RuntimeError('the delivery companion" in l] != [], True,
                         "a companion that does not report `loaded` stops the launch like the watcher and the collector")

    def test_the_companion_is_started_with_options_it_accepts(self):
        m = re.search(r"argv=\[(.*?)\]\n", TEXT78[TEXT78.index("def deliver_start"):])
        opts = re.findall(r"'(--[a-z0-9-]+)'", m.group(1))
        self.assertEqual(opts, ["--root", "--size", "--sha256", "--out", "--wait-s", "--deliver-s"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
            DELIVER.main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        for o in opts + ["--selftest"]:
            self.assertIn(o, buf.getvalue(), o)
        # the driver's constants are what it passes
        self.assertIn("'--wait-s',str(DELIVER_WAIT_S),'--deliver-s',str(DELIVER_S)", TEXT78)
        self.assertIn("'--selftest'", TEXT78)

    def test_the_derived_driver_is_valid_python_and_names_no_nat075_path(self):
        compile(TEXT78, "session_nat078.py", "exec")
        code = TEXT78.replace(DOCSTRING.match(TEXT78).group(2), "")
        for left in ("nat075", "artifacts/nat-075", "analyze_nat075", "bigwin"):
            self.assertNotIn(left, code, left)
        for need in ("artifacts/nat-078/native-attempt-", "*-nat078-%s-single-run-*.md", "artifacts/nat-079/package-002", "loader-diag-xnu-rx-md1"):
            self.assertIn(need, code, need)

    def test_the_registry_gate_needs_the_whole_delivery_chain(self):
        done = re.search(r"REQUIRED_DONE=\((.*?)\)", TEXT78).group(1)
        names = re.findall(r"'(NAT-\d+)'", done)
        old = re.findall(r"'(NAT-\d+)'", re.search(r"REQUIRED_DONE=\((.*?)\)", TEXT75).group(1))
        self.assertEqual(names[:len(old)], old, "NAT-075's gate is kept whole and first")
        self.assertEqual(names[len(old):], ["NAT-075", "NAT-076", "NAT-077", "NAT-079", "NAT-080"])
        self.assertNotIn("NAT-078", names, "the run itself is not a precondition of the run")

    def test_the_wait_for_the_loader_and_the_send_time_fit_in_the_receive_cap(self):
        c = {k: int(v) for k, v in re.findall(r"^(DELIVER_WAIT_S|DELIVER_S|DELIVER_MARGIN_S)=(\d+)", TEXT78, re.M)}
        self.assertEqual(c, dict(DELIVER_WAIT_S=V.DELIVER_WAIT_S, DELIVER_S=V.DELIVER_S, DELIVER_MARGIN_S=V.DELIVER_MARGIN_S))
        cap = int(re.search(r"RX_CAP_S=(\d+)\)", TEXT78).group(1))
        self.assertLessEqual(c["DELIVER_S"] + c["DELIVER_MARGIN_S"], cap)
        # the driver's own preflight asserts the same inequality against the cap recorded in the build record
        self.assertIn("assert DELIVER_S+DELIVER_MARGIN_S<=cfg['RX_CAP_S']", TEXT78)
        # the companion's wait covers the device's enumeration (+26.7 s in NAT-075) with a large margin and stays below the NAT-044 deadline (360 s)
        self.assertGreater(c["DELIVER_WAIT_S"], 4 * 27)
        self.assertLessEqual(c["DELIVER_WAIT_S"], 360)
        self.assertEqual(re.search(r"^WATCH_S=(\d+)", TEXT78, re.M).group(1), re.search(r"^COLLECT_S=(\d+)", TEXT78, re.M).group(1))
        self.assertGreaterEqual(int(re.search(r"^WATCH_S=(\d+)", TEXT78, re.M).group(1)), 360 + 30 + 120, "deadline + the return to Download Mode + the 120 s the analysis needs")

    @unittest.skipUnless(HAVE_ARTIFACTS, "artifacts/nat-079/package-002 or artifacts/nat-077/padded.json is not present")
    def test_the_constants_are_the_packages_the_padded_roots_and_the_builds(self):
        pkg = json.loads(PACKAGE.read_text())
        img = pkg["images"]["loader-diag-xnu-rx-md1"]
        build = json.loads((ROOT / pkg["build"] / "build.json").read_text())
        padded = json.loads(PADDED.read_text())
        const = lambda k: re.search(r"%s=['\"]?([0-9a-f]+)" % k, TEXT78).group(1)                        # noqa: E731
        self.assertEqual(const("NEW_SHA"), img["recovery_sha256"])
        self.assertEqual(const("CANARY_SHA"), img["payload_sha256"])
        self.assertEqual(int(const("CANARY_LEN")), img["payload_bytes"])
        self.assertEqual(int(const("ROOT_SIZE")), padded["padded_bytes"])
        self.assertEqual(const("ROOT_SHA"), padded["padded_sha256"])
        self.assertEqual(padded["padded_bytes"], build["nat079_params"]["reserve_bytes"], "the loader's reserve is exactly the root the companion sends")
        self.assertEqual(padded["padded_bytes"] % 16384, 0)
        self.assertEqual(int(re.search(r"RX_CAP_S=(\d+)\)", TEXT78).group(1)), build["nat079_params"]["rx_cap_s"])
        # the RECOVERY image the driver will write is the file that has that hash (100 MB: cheap to hash)
        files = [p for p in (ROOT / "artifacts/nat-079/package-002").rglob("*") if p.is_file() and p.stat().st_size == 100663296]
        self.assertTrue(files, "the packaged 96 MiB RECOVERY image is not in the package directory")
        self.assertIn(img["recovery_sha256"], {hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

    def test_a_nat075_driver_that_has_drifted_is_refused_not_half_translated(self):
        anchors = ["'loader-diag-xnu-bigwin-md1':dict(", "NEW_SHA='c76165fbe6457932e5c459b45a63a8510bf802e72b4278e0f9cb1186edbdbd14'",
                   "CANARY_SHA='5f39495505fd413671c6007a61ae7dab64b313014fa82a31e3302dcb89d1e25f'", "CANARY_LEN=21878752),", "artifacts/nat-075/package-001",
                   "*-nat075-%s-single-run-*.md", "artifacts/nat-075/native-attempt-%s-used.json", "WATCH_S=360", "COLLECT_S=360",
                   "VENV_PY=ROOT/'artifacts/recovery-rescue-20261110-01/venv/bin/python'", "'NAT-068','NAT-074')", "    def watcher_start():\n",
                   "        raise RuntimeError('the collector did not log a poll of the USB bus: no reboot')\n", "                host_access();collector_selftest()\n",
                   "            watcher_start()\n            collector_start()\n", "archive=report['collector']['archive'])));return 0"]
        for a in anchors:
            self.assertIn(a, TEXT75, "the anchor must exist in NAT-075's driver for this test to mean anything: " + a)
            gone = TEXT75.replace(a, "", 1)
            with self.assertRaises((AssertionError, ValueError), msg="missing: " + a):
                V.derive_session(gone, *FAKE.values())
        for a in anchors:
            if a.startswith("VENV_PY="):
                continue                                          # the derivation inserts after the first such line; a second one is not ambiguous for it
            with self.assertRaises((AssertionError, ValueError), msg="twice: " + a):             # a second copy of a single-use anchor is as wrong as none
                V.derive_session(TEXT75.replace(a, a + a, 1), *FAKE.values())

    def test_a_changed_docstring_or_a_leftover_nat075_name_is_refused(self):
        m = DOCSTRING.match(TEXT75)
        with self.assertRaises(AssertionError):
            V.derive_session(TEXT75.replace(m.group(2), m.group(2)[:-3] + "\nan added line\n" + '"' * 3, 1), *FAKE.values())     # one more line inside: the docstring has changed shape
        with self.assertRaises(AssertionError):
            V.derive_session(TEXT75.replace("NAT-075 session driver", "NAT-0xx session driver", 1), *FAKE.values())
        with self.assertRaises(AssertionError):
            V.derive_session(TEXT75 + "\nLEFT = 'loader-diag-xnu-bigwin-md1'\n", *FAKE.values())
        with self.assertRaises(AssertionError):
            V.derive_session(TEXT75 + "\nLEFT = 'analyze_nat075'\n", *FAKE.values())

    def test_the_values_of_the_package_go_into_the_driver_where_they_are_used(self):
        t = V.derive_session(TEXT75, *FAKE.values())
        self.assertIn("NEW_SHA='%s'" % FAKE["new_sha"], t)
        self.assertIn("CANARY_SHA='%s'" % FAKE["payload_sha"], t)
        self.assertIn("CANARY_LEN=%d," % FAKE["payload_len"], t)
        self.assertIn("ROOT_SIZE=%d\n" % FAKE["root_size"], t)
        self.assertIn("ROOT_SHA='%s'\n" % FAKE["root_sha"], t)
        self.assertIn("RX_CAP_S=%d)," % FAKE["rx_cap_s"], t)
        for h in FAKE["new_sha"], FAKE["payload_sha"], FAKE["root_sha"]:
            self.assertEqual(t.count(h), 1, "each pinned hash appears once, where it is checked")


    def test_a_second_copy_of_the_nat075_docstring_is_not_rewritten_silently(self):
        m = DOCSTRING.match(TEXT75)
        with self.assertRaises(AssertionError):
            V.derive_session(TEXT75 + "\n" + m.group(2) + "\n", *FAKE.values())			# only the first is replaced; the leftover is found


class Command(unittest.TestCase):
    """derive.py as a command: --check compares, no argument writes. The committed driver is never touched here."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nat080-derive-", dir=os.environ.get("TMPDIR")))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.derived = V.derive_session(TEXT75, *FAKE.values())
        self.out = self.tmp / "session_nat078.py"

    def run_main(self, argv):
        stdout = io.StringIO()
        with mock.patch.object(V, "HERE", self.tmp), mock.patch.object(V, "package_values", lambda: tuple(FAKE.values())), contextlib.redirect_stdout(stdout):
            code = V.main(argv)
        return code, stdout.getvalue()

    def test_check_passes_for_the_derived_text_and_changes_nothing(self):
        self.out.write_text(self.derived)
        self.assertEqual(self.run_main(["--check"]), (0, ""))
        self.assertEqual(self.out.read_text(), self.derived)

    def test_check_fails_with_status_1_for_any_other_text_and_changes_nothing(self):
        for text in (self.derived + " ", self.derived.replace("DELIVER_S=225", "DELIVER_S=226", 1), ""):
            self.out.write_text(text)
            self.assertEqual(self.run_main(["--check"]), (1, ""))
            self.assertEqual(self.out.read_text(), text)

    def test_without_an_argument_it_writes_the_derived_text_with_the_mode_of_nat075s_driver(self):
        self.out.write_text("old")
        self.out.chmod(0o600)
        code, stdout = self.run_main([])
        self.assertEqual((code, stdout), (0, "wrote %s\n" % self.out))
        self.assertEqual(self.out.read_text(), self.derived)
        self.assertEqual(self.out.stat().st_mode & 0o777, (PROC / "nat-075" / "session_nat075.py").stat().st_mode & 0o777)

    @unittest.skipUnless(HAVE_ARTIFACTS, "artifacts/nat-079/package-002 or artifacts/nat-077/padded.json is not present")
    def test_the_script_itself_exits_with_the_status_of_main(self):
        tree = self.tmp / "tree"
        here = tree / "docs/procedures/nat-080"
        here.mkdir(parents=True)
        shutil.copy(HERE / "derive.py", here / "derive.py")
        (tree / "docs/procedures/nat-075").symlink_to(PROC / "nat-075")
        (tree / "artifacts").symlink_to(ROOT / "artifacts")
        target = here / "session_nat078.py"

        def run(*args):
            r = subprocess.run([sys.executable, "-B", "-I", str(here / "derive.py"), *args], capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr

        target.write_text("something else")
        self.assertEqual(run("--check"), (1, "", ""))
        self.assertEqual(target.read_text(), "something else")
        code, stdout, stderr = run()
        self.assertEqual((code, stdout, stderr), (0, "wrote %s\n" % target, ""))
        self.assertEqual(target.read_text(), TEXT78, "with the real package the derivation is the committed driver")
        self.assertEqual(run("--check"), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
