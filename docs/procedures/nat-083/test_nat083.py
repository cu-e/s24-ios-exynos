#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-083 host tests of the session-driver derivation (derive83.py -> session_nat083.py). Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-083/test_nat083.py      (opens no device, sends no command)

session_nat083.py is the only launcher of the one native run. The tests pin what the derivation promises:
  * the committed driver IS the derivation from NAT-080's session_nat078.py (the --check of derive83.py);
  * every line that differs from session_nat078.py carries one of the documented substitutions: no device access, no reboot, no retry is added or removed;
  * the constants it carries are those of package-002 (RECOVERY and Image.payload hashes, payload length), the padded root's size and hash as recorded by the build, the
    decision glob and the one-shot marker of NAT-083, and the registry gate also needs NAT-070 done;
  * the package's recovery image is the size the driver writes and carries the NAT-083 command line (`rd=md1`, no `rd=md0`);
  * a NAT-080 driver that has drifted is refused instead of half translated.
The derived driver is not run here: its execution opens the phone."""
import contextlib
import difflib
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


D = load("nat083_derive_mod", HERE / "derive83.py")
SESSION = HERE / "session_nat083.py"
OLD = ROOT / "docs/procedures/nat-080/session_nat078.py"
PKG = D.PACKAGE / "package.json"
HAVE_PKG = PKG.is_file()


class Derivation(unittest.TestCase):
    def test_the_committed_driver_is_the_derivation(self):
        text, done = D.build()
        self.assertEqual(SESSION.read_text(), text)
        self.assertEqual(len(done), 12)
        self.assertTrue(all(n == 1 for _, n in done))

    def test_a_drifted_source_is_refused_not_half_translated(self):
        with tempfile.TemporaryDirectory(dir=None) as t:
            drifted = Path(t) / "session_nat078.py"
            drifted.write_text(OLD.read_text() + "\n# drift\n")
            with mock.patch.object(D, "SRC", drifted):
                with self.assertRaises(ValueError) as cm:
                    D.build()
            self.assertIn("not the file this derivation was written for", str(cm.exception))

    def test_a_substitution_whose_target_is_missing_is_refused(self):
        text = OLD.read_text().replace("analysis is analyze_nat080.py (run separately)", "analysis is elsewhere")
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "session_nat078.py"
            f.write_text(text)
            with mock.patch.object(D, "SRC", f), mock.patch.object(D, "SRC_SHA256", hashlib.sha256(text.encode()).hexdigest()):
                with self.assertRaises(ValueError) as cm:
                    D.build()
            self.assertIn("analyser name", str(cm.exception))

    def test_the_source_is_the_pinned_nat080_driver(self):
        self.assertEqual(hashlib.sha256(OLD.read_bytes()).hexdigest(), D.SRC_SHA256)

    def test_the_main_flag_check_succeeds_and_a_changed_driver_fails_it(self):
        self.assertEqual(D.main(["--check"]), 0)
        with tempfile.TemporaryDirectory() as t:
            other = Path(t) / "session_nat083.py"
            other.write_text(SESSION.read_text() + "\n")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(D.main(["--check"]), 1)


class Command(unittest.TestCase):
    """The command line of derive83.py: what it prints, what it writes, what it returns."""

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = D.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_check_says_ok_with_the_substitution_count_and_prints_nothing_else(self):
        self.assertEqual(self.call(["--check"]), (0, "ok: session_nat083.py equals the derivation (12 substitutions)\n", ""))

    def test_check_names_the_difference_on_stderr(self):
        with tempfile.TemporaryDirectory() as t:
            other = Path(t) / "session_nat083.py"
            other.write_text("x")
            with mock.patch.object(D, "OUT", other):
                rc, out, err = self.call(["--check"])
            self.assertEqual((rc, out, err), (1, "", "session_nat083.py differs from the derivation\n"))
            self.assertEqual(other.read_text(), "x")                          # --check never writes
            self.assertEqual(self.call(["--check"])[0], 0)

    def test_without_check_it_writes_the_driver_and_reports_its_hash(self):
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t)
            (fake / "docs/procedures/nat-083").mkdir(parents=True)
            target = fake / "docs/procedures/nat-083/session_nat083.py"
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
            self.assertEqual((rc, err), (0, ""))
            text, done = D.build()
            self.assertEqual(target.read_text(), text)
            self.assertTrue(out.startswith('{\n "out"'), out[:20])             # indent 1
            rep = json.loads(out)
            self.assertEqual(rep["out"], "docs/procedures/nat-083/session_nat083.py")
            self.assertEqual(rep["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(len(rep["substitutions"]), 12)
            self.assertTrue(all(s["count"] == 1 for s in rep["substitutions"]))

    def test_a_drifted_source_is_refused_with_status_2_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as t:
            drifted = Path(t) / "session_nat078.py"
            drifted.write_text(OLD.read_text() + "\n# drift\n")
            target = Path(t) / "session_nat083.py"
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
                rc2, out2, err2 = self.call(["--check"])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: session_nat078.py is not the file this derivation was written for"), err)
            self.assertEqual((rc2, out2), (2, ""))
            self.assertFalse(target.exists())

    def test_run_as_a_script_the_flag_reaches_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive83.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ok: session_nat083.py equals the derivation (12 substitutions)\n", ""))


class Diff(unittest.TestCase):
    """The driver differs from NAT-080's in the documented places only: undoing the documented substitutions gives NAT-080's driver back, byte for byte."""

    def undone(self):
        pkg = json.loads(PKG.read_text())["images"][D.IMAGE_NEW]
        t = SESSION.read_text()
        pairs = [(D.DOC_NEW, D.DOC_OLD),
                 ("analysis is analyze_nat083.py (run separately)", "analysis is analyze_nat080.py (run separately)"),
                 ("PACKAGE=ROOT/'artifacts/nat-083/%s'" % D.PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-079/package-002'"),
                 ("'%s':dict(" % D.IMAGE_NEW, "'%s':dict(" % D.IMAGE_OLD),
                 (pkg["recovery_sha256"], D.NEW_SHA_OLD), (pkg["payload_sha256"], D.CANARY_OLD),
                 ("CANARY_LEN=%d" % pkg["payload_bytes"], "CANARY_LEN=" + D.LEN_OLD),
                 ("ROOT_IMAGE=ROOT/'artifacts/nat-083/system-padded.apfs'", "ROOT_IMAGE=ROOT/'artifacts/nat-077/system-padded.apfs'"),
                 (D.ROOT_SHA_NEW, D.ROOT_SHA_OLD),
                 ("*-nat083-%s-single-run-*.md", "*-nat078-%s-single-run-*.md"),
                 ("artifacts/nat-083/native-attempt-%s-used.json", "artifacts/nat-078/native-attempt-%s-used.json"),
                 ("'NAT-079','NAT-080','NAT-070')", "'NAT-079','NAT-080')")]
        for new, old in pairs:
            self.assertEqual(t.count(new), 1, new)
            t = t.replace(new, old)
        return t

    @unittest.skipUnless(HAVE_PKG, "artifacts/nat-083/package-002 not present")
    def test_undoing_the_documented_substitutions_gives_the_nat080_driver_back(self):
        self.assertEqual(self.undone(), OLD.read_text())

    def test_the_diff_has_the_documented_size(self):
        a, b = OLD.read_text().splitlines(), SESSION.read_text().splitlines()
        changed = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if not l.startswith(("+++", "---", "@@"))]
        minus = [l for l in changed if l.startswith("-")]
        plus = [l for l in changed if l.startswith("+")]
        self.assertLessEqual(len(minus), 12)
        self.assertLessEqual(len(plus), 14)
        self.assertGreaterEqual(len(minus), 9)

    def test_no_device_facing_statement_is_added_or_removed(self):
        for word in ("adb", "su -c", "sda18", "Popen", "dd of=", "restore_stock", "sleep(", "subprocess", "STOCK_SHA", "WATCH_S", "COLLECT_S", "DELIVER_S", "'reboot'", "recovery"):
            self.assertEqual(SESSION.read_text().count(word), OLD.read_text().count(word), word)


@unittest.skipUnless(HAVE_PKG, "artifacts/nat-083/package-002 not present")
class Constants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = json.loads(PKG.read_text())["images"][D.IMAGE_NEW]
        cls.sess = load("nat083_session_mod", SESSION)

    def test_the_hashes_and_length_are_the_packages(self):
        cfg = self.sess.IMAGES[D.IMAGE_NEW]
        self.assertEqual(cfg["NEW_SHA"], self.pkg["recovery_sha256"])
        self.assertEqual(cfg["CANARY_SHA"], self.pkg["payload_sha256"])
        self.assertEqual(cfg["CANARY_LEN"], self.pkg["payload_bytes"])
        self.assertEqual(cfg["RX_CAP_S"], 240)
        self.assertEqual(set(self.sess.IMAGES), {D.IMAGE_NEW})

    def test_the_recovery_image_of_the_package_is_the_written_size_and_hash(self):
        data = (D.PACKAGE / D.IMAGE_NEW / "recovery.img").read_bytes()
        self.assertEqual(len(data), self.sess.SIZE)
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.sess.IMAGES[D.IMAGE_NEW]["NEW_SHA"])
        off = self.sess.PAYLOAD_OFFSET
        payload = data[off:off + self.sess.IMAGES[D.IMAGE_NEW]["CANARY_LEN"]]
        self.assertEqual(hashlib.sha256(payload).hexdigest(), self.sess.IMAGES[D.IMAGE_NEW]["CANARY_SHA"])

    def test_the_command_line_in_the_payload_boots_md1_and_not_md0(self):
        data = (D.PACKAGE / D.IMAGE_NEW / "recovery.img").read_bytes()
        m = re.search(rb"rd=md\d [ -~]{20,250}", data)
        self.assertIsNotNone(m)
        cmd = m.group(0).decode()
        self.assertTrue(cmd.startswith("rd=md1 "), cmd)
        self.assertEqual(cmd.count("rd="), 1)
        for need in ("nat_attempt=NAT083-rt1", "loader_return_after=60", "e1stouch=0", "e1sbattery=0", "serial=3", "debug=0xc"):
            self.assertIn(need, cmd)

    def test_the_root_image_constants(self):
        self.assertEqual((self.sess.ROOT_SIZE, self.sess.ROOT_SHA), (D.ROOT_SIZE, D.ROOT_SHA_NEW))
        self.assertEqual(self.sess.ROOT_IMAGE, ROOT / "artifacts/nat-083/system-padded.apfs")
        p = self.sess.ROOT_IMAGE
        if p.is_file():
            self.assertEqual(p.stat().st_size, D.ROOT_SIZE)

    def test_gate_names_nat083_and_the_registry_needs_nat070(self):
        self.assertIn("NAT-070", self.sess.REQUIRED_DONE)
        self.assertEqual(self.sess.PACKAGE, D.PACKAGE)
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t)
            (fake / "docs/decisions").mkdir(parents=True)
            with mock.patch.object(self.sess, "ROOT", fake):
                with self.assertRaises(AssertionError) as cm:
                    self.sess.gate(D.IMAGE_NEW, self.sess.IMAGES[D.IMAGE_NEW])
                self.assertIn("missing or ambiguous", str(cm.exception))
                (fake / ("docs/decisions/0032-nat083-%s-single-run-2026-11-12.md" % D.IMAGE_NEW)).write_text("decision 0019 " + self.sess.IMAGES[D.IMAGE_NEW]["NEW_SHA"])
                with self.assertRaises(AssertionError) as cm:
                    self.sess.gate(D.IMAGE_NEW, self.sess.IMAGES[D.IMAGE_NEW])
                self.assertIn(self.sess.IMAGES[D.IMAGE_NEW]["CANARY_SHA"], str(cm.exception))
                (fake / ("docs/decisions/0032-nat083-%s-single-run-2026-11-12.md" % D.IMAGE_NEW)).write_text(
                    "decision 0019 %s %s" % (self.sess.IMAGES[D.IMAGE_NEW]["NEW_SHA"], self.sess.IMAGES[D.IMAGE_NEW]["CANARY_SHA"]))
                self.assertEqual(self.sess.gate(D.IMAGE_NEW, self.sess.IMAGES[D.IMAGE_NEW]).name, "0032-nat083-%s-single-run-2026-11-12.md" % D.IMAGE_NEW)

    def test_a_decision_file_of_another_task_does_not_open_the_gate(self):
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t)
            (fake / "docs/decisions").mkdir(parents=True)
            (fake / ("docs/decisions/0030-nat078-%s-single-run-2026-11-12.md" % D.IMAGE_NEW)).write_text(
                "decision 0019 %s %s" % (self.sess.IMAGES[D.IMAGE_NEW]["NEW_SHA"], self.sess.IMAGES[D.IMAGE_NEW]["CANARY_SHA"]))
            with mock.patch.object(self.sess, "ROOT", fake):
                with self.assertRaises(AssertionError):
                    self.sess.gate(D.IMAGE_NEW, self.sess.IMAGES[D.IMAGE_NEW])


if __name__ == "__main__":
    unittest.main(verbosity=1)
