#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-092 host tests: the build wrapper of the Stage A image, the built payload against NAT-087's, the Stage A small root (every plist in it against the donor set and NAT-089's table) and the derived
session driver. Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-092/test_nat092.py      (opens no device)

What the tests stand on (so that they do not merely mirror the code under test):

  * the built payload is compared byte for byte with NAT-087's: the only differences are the command-line tag and the 4 MiB md0 region (which must equal the Stage A root file, and the
    NAT-087 payload's md0 region must equal NAT-087's root file); the loader differs only in the words that encode the image name;
  * the small root's source tree (the directory the container was packed from) holds exactly the 19 Apple plists of NAT-089's table plus the heartbeat, each with the recorded sha256, its label and its program
    (and the three `Disabled` keys the stock plists carry, listed); the container itself is tied to the tree by the recorded hash only (a byte search does not find the plists inside it);
  * the driver is the derivation's output, and names this image's hashes and not NAT-087's.
Nothing here runs on a phone."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
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


D = load("nat092_test_derive", HERE / "derive92.py")
PKG = ROOT / "artifacts/nat-092/package-001/package.json"
BUILD92 = ROOT / "artifacts/nat-092/build-001/loader-diag-xnu-sb-md1/Image.payload"
BUILD87 = ROOT / "artifacts/nat-087/build-001/loader-diag-xnu-rm-md1/Image.payload"
BUILD90 = ROOT / "artifacts/nat-090/build-001/loader-diag-xnu-sa-md1/Image.payload"
BUILD90_JSON = ROOT / "artifacts/nat-090/build-001/build.json"
BUILD_JSON = ROOT / "artifacts/nat-092/build-001/build.json"
MD0_92 = ROOT / "artifacts/nat-089/pid1-stageA/root.apfs"
MD0_87 = ROOT / "artifacts/nat-085/pid1/root.apfs"
JOBS_JSON = ROOT / "docs/procedures/nat-089/stage-a-jobs.json"
CMDLINE_OFF, CMDLINE_LEN = 0x48, 608                    # the SWEETXNU header's command line field (NAT-065's build.py)
LOADER_BYTES = 385024                                   # the loader Image in front of the XNU payload
MD0_BYTES = 4194304
TAG87, TAG92 = "NAT087-rm1", "NAT092-sb1"
TAG90 = "NAT090-sa1"


class BuildMain(unittest.TestCase):
    """main() with NAT-087's main() replaced by a stand-in that records what the globals look like while it runs and writes a build.json like NAT-083's and NAT-087's."""

    @classmethod
    def setUpClass(cls):
        cls.B = load("nat092_test_build_main", HERE / "build.py")

    def md0(self, d, size=MD0_BYTES, fill=b"\x5a"):
        p = Path(d) / "root.apfs"
        p.write_bytes(fill * size)
        return p, hashlib.sha256(fill * size).hexdigest()

    def go(self, argv, record_md0=None, change=None, raises=None, write=True):
        B, seen = self.B, {}

        def b87_main():
            seen["name"], seen["tag"] = B.b87.NAME, B.b87.NEW_TAG
            if raises:
                raise raises
            if "--out" in argv and write:
                rec = {"nat083_changes": {"md0_image": record_md0}, "nat087_changes": change if change is not None else {"image_name": B.NAME, "cmdline_tag": B.NEW_TAG,
                                                                                                                         "cmdline": "rd=md1 x xrd=md0"}, "other": 1}
                (Path(argv[argv.index("--out") + 1]) / "build.json").write_text(json.dumps(rec))

        before = (B.b87.NAME, B.b87.NEW_TAG)
        with mock.patch.object(B.b87, "main", b87_main), mock.patch.object(sys, "argv", ["build.py"] + argv):
            try:
                B.main()
            finally:
                seen["after"] = (B.b87.NAME, B.b87.NEW_TAG)
        seen["before"] = before
        return seen

    def test_names_have_the_lengths_of_nat087s(self):
        self.assertEqual((self.B.NAME, self.B.NEW_TAG), ("loader-diag-xnu-sb-md1", "nat_attempt=NAT092-sb1"))
        self.assertEqual(len(self.B.NAME), len(self.B.b87.NAME))
        self.assertEqual(len(self.B.NEW_TAG), len(self.B.b87.NEW_TAG))
        self.assertEqual(self.B.MD0_BYTES, MD0_BYTES)

    def test_the_names_are_in_place_while_nat087_runs_and_back_after(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            seen = self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h))
        self.assertEqual((seen["name"], seen["tag"]), (self.B.NAME, self.B.NEW_TAG))
        self.assertEqual(seen["after"], seen["before"])
        self.assertNotEqual(seen["before"], (self.B.NAME, self.B.NEW_TAG))

    def test_they_are_restored_when_nat087_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = self.md0(d)
            with self.assertRaises(RuntimeError):
                self.go(["--ramdisk", str(p)], raises=RuntimeError("boom"))
        self.assertNotEqual(self.B.b87.NAME, self.B.NAME)
        self.assertNotEqual(self.B.b87.NEW_TAG, self.B.NEW_TAG)

    def test_a_missing_ramdisk_argument_is_refused_before_anything_runs(self):
        with self.assertRaises(SystemExit) as cm:
            self.go(["--out", "x"])
        self.assertEqual(str(cm.exception), "--ramdisk is required: the Stage A small root")

    def test_a_ramdisk_of_another_size_is_refused_before_anything_runs(self):
        for size in (MD0_BYTES - 1, MD0_BYTES + 1, 0):
            with tempfile.TemporaryDirectory() as d:
                p, _ = self.md0(d, size=size)
                ran = []
                with mock.patch.object(self.B.b87, "main", lambda: ran.append(1)), mock.patch.object(sys, "argv", ["build.py", "--ramdisk", str(p)]):
                    with self.assertRaises(SystemExit) as cm:
                        self.B.main()
                self.assertEqual(str(cm.exception), "the small root is %d bytes, not %d" % (size, MD0_BYTES))
                self.assertEqual(ran, [])

    def test_check_only_needs_no_ramdisk_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(self.B.b87, "main", lambda: None), mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", d]):
            self.assertIsNone(self.B.main())
            self.assertEqual(os.listdir(d), [])

    def test_build_json_gets_the_nat092_record_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h))
            rec = json.loads((Path(d) / "build.json").read_text())
        self.assertEqual(rec["other"], 1)
        self.assertEqual(rec["nat092_changes"], {"image_name": self.B.NAME, "cmdline_tag": self.B.NEW_TAG, "md0_sha256": h, "md0_bytes": MD0_BYTES, "cmdline": "rd=md1 x xrd=md0"})
        self.assertEqual(rec["nat092_sources"], {"build.py": hashlib.sha256((HERE / "build.py").read_bytes()).hexdigest()})
        self.assertIn("Stage A small root", rec["nat092_note"])
        self.assertIn("nothing here ran on a phone", rec["nat092_note"])

    def test_a_build_json_with_another_md0_hash_or_size_is_refused(self):
        for bad in (dict(bytes=MD0_BYTES, sha256="0" * 64), dict(bytes=MD0_BYTES - 1, sha256=None), None):
            with tempfile.TemporaryDirectory() as d:
                p, h = self.md0(d)
                if bad is not None and bad["sha256"] is None:
                    bad = dict(bytes=bad["bytes"], sha256=h)
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p), "--out", d], record_md0=bad)
                self.assertTrue(str(cm.exception).startswith("build.json records md0 "), str(cm.exception))
                self.assertNotIn("nat092_changes", json.loads((Path(d) / "build.json").read_text()))

    def test_a_build_json_with_another_name_or_tag_is_refused(self):
        for bad in ({"image_name": "loader-diag-xnu-rm-md1", "cmdline_tag": self.B.NEW_TAG}, {"image_name": self.B.NAME, "cmdline_tag": "nat_attempt=NAT087-rm1"}, {}):
            with tempfile.TemporaryDirectory() as d:
                p, h = self.md0(d)
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h), change=bad)
                self.assertTrue(str(cm.exception).startswith("build.json does not carry this image's name and tag"), str(cm.exception))

    def test_without_a_build_json_it_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = self.md0(d)
            with self.assertRaises(SystemExit) as cm:
                self.go(["--ramdisk", str(p), "--out", d], write=False)
        self.assertEqual(str(cm.exception), "no build.json was written")

    def test_without_an_out_argument_nothing_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = self.md0(d)
            seen = self.go(["--ramdisk", str(p)])
        self.assertEqual((seen["name"], seen["tag"]), (self.B.NAME, self.B.NEW_TAG))

    def test_argv_value(self):
        f = self.B.argv_value
        self.assertEqual(f(["a", "--x", "1", "--y"], "--x"), "1")
        self.assertIsNone(f(["a", "--x", "1", "--y"], "--y"))       # a flag with no value after it
        self.assertIsNone(f(["a"], "--x"))

    def test_running_the_file_calls_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build.py")], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (1, "", "--ramdisk is required: the Stage A small root\n"))


@unittest.skipUnless(BUILD92.is_file() and BUILD87.is_file() and BUILD_JSON.is_file() and MD0_92.is_file() and MD0_87.is_file(), "built payloads / small roots not present")
class BuiltPayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw92, cls.raw87 = BUILD92.read_bytes(), BUILD87.read_bytes()
        cls.p92, cls.p87 = cls.raw92[LOADER_BYTES:], cls.raw87[LOADER_BYTES:]
        cls.rec = json.loads(BUILD_JSON.read_text())
        cls.m92, cls.m87 = MD0_92.read_bytes(), MD0_87.read_bytes()

    def cmd(self, p):
        return p[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()

    def test_the_command_line_is_nat087s_with_the_new_tag_and_still_ends_in_the_token(self):
        c = self.cmd(self.p92)
        self.assertEqual(c, self.cmd(self.p87).replace(TAG87, TAG92))
        self.assertEqual(c, self.rec["nat092_changes"]["cmdline"])
        self.assertTrue(c.endswith(" xrd=md0"))
        self.assertEqual([t for t in c.split() if t.startswith("rd=")], ["rd=md1"])
        self.assertEqual(c.count("xrd="), 1)
        self.assertEqual(c.count("nat_attempt=NAT092-sb1"), 1)

    def test_md0_of_each_payload_is_its_small_root_at_the_same_offset(self):
        o87, o92 = self.p87.find(self.m87), self.p92.find(self.m92)
        self.assertGreater(o87, 0)
        self.assertEqual((o87, len(self.m87), len(self.m92)), (o92, MD0_BYTES, MD0_BYTES))
        self.assertEqual(self.p87.count(self.m87), 1)
        self.assertEqual(self.p92.count(self.m92), 1)
        self.assertEqual(hashlib.sha256(self.m92).hexdigest(), self.rec["nat092_changes"]["md0_sha256"])

    def test_nothing_else_in_the_payload_differs_from_nat087s(self):
        o = self.p87.find(self.m87)
        want = bytearray(self.p87)
        want[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = self.cmd(self.p87).replace(TAG87, TAG92).encode().ljust(CMDLINE_LEN, b"\0")
        want[o:o + MD0_BYTES] = self.m92
        self.assertEqual(bytes(want), self.p92)                                            # ADT, kernel, delivery parameters are NAT-087's

    def test_the_loader_differs_only_in_its_name_immediates(self):
        a, b = self.raw87[:LOADER_BYTES], self.raw92[:LOADER_BYTES]
        diff = [i for i in range(LOADER_BYTES) if a[i] != b[i]]
        self.assertTrue(0 < len(diff) <= 40, len(diff))
        self.assertTrue(64000 <= diff[0] and diff[-1] <= 64500, (diff[0], diff[-1]))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_the_payload_has_the_packaged_size_and_nat087s(self):
        want = json.loads(PKG.read_text())["images"]["loader-diag-xnu-sb-md1"]["payload_bytes"]
        self.assertEqual((len(self.raw92), len(self.raw87)), (want, want))
        self.assertEqual(hashlib.sha256(self.raw92).hexdigest(), json.loads(PKG.read_text())["images"]["loader-diag-xnu-sb-md1"]["payload_sha256"])


@unittest.skipUnless(BUILD92.is_file() and BUILD90.is_file() and BUILD_JSON.is_file() and BUILD90_JSON.is_file(), "NAT-090 / NAT-092 built payloads not present")
class AgainstNat090(unittest.TestCase):
    """NAT-092 is a documented re-run of NAT-090's content: the payload must equal NAT-090's byte for byte except the command-line tag, and the loader except its name immediates."""

    @classmethod
    def setUpClass(cls):
        cls.raw90, cls.raw92 = BUILD90.read_bytes(), BUILD92.read_bytes()
        cls.rec90, cls.rec92 = json.loads(BUILD90_JSON.read_text()), json.loads(BUILD_JSON.read_text())

    def test_same_length_and_the_tag_is_the_only_difference_after_the_loader(self):
        self.assertEqual(len(self.raw90), len(self.raw92))
        p90, p92 = self.raw90[LOADER_BYTES:], self.raw92[LOADER_BYTES:]
        want = bytearray(p90)
        want[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = p90[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode().replace(TAG90, TAG92).encode().ljust(CMDLINE_LEN, b"\0")
        self.assertEqual(bytes(want), p92)
        self.assertNotEqual(p90, p92)
        start = p90.find(TAG90.encode())
        self.assertTrue(CMDLINE_OFF <= start < CMDLINE_OFF + CMDLINE_LEN, start)
        self.assertEqual([i for i in range(len(p90)) if p90[i] != p92[i]], [start + 5, start + 8])               # '0' -> '2' and 'a' -> 'b'

    def test_the_loader_differs_in_a_few_bytes_inside_the_name_immediates_only(self):
        a, b = self.raw90[:LOADER_BYTES], self.raw92[:LOADER_BYTES]
        diff = [i for i in range(LOADER_BYTES) if a[i] != b[i]]
        self.assertTrue(0 < len(diff) <= 20, len(diff))
        self.assertTrue(64000 <= diff[0] and diff[-1] <= 64500, (diff[0], diff[-1]))

    def test_the_small_root_is_the_same_file(self):
        self.assertEqual(self.rec90["nat090_changes"]["md0_sha256"], self.rec92["nat092_changes"]["md0_sha256"])
        self.assertEqual(self.rec90["nat090_changes"]["md0_bytes"], self.rec92["nat092_changes"]["md0_bytes"])

    def test_the_command_lines_differ_only_in_the_tag(self):
        c90, c92 = self.rec90["nat090_changes"]["cmdline"], self.rec92["nat092_changes"]["cmdline"]
        self.assertEqual(c92, c90.replace(TAG90, TAG92))
        self.assertNotEqual(c90, c92)
        self.assertEqual(self.rec92["nat092_changes"]["image_name"], "loader-diag-xnu-sb-md1")
        self.assertEqual(self.rec90["nat090_changes"]["image_name"], "loader-diag-xnu-sa-md1")
        self.assertEqual(len(self.rec92["nat092_changes"]["image_name"]), len(self.rec90["nat090_changes"]["image_name"]))


STAGE_TREE = ROOT / "artifacts/nat-089/pid1-stageA/root/LaunchDaemons"


@unittest.skipUnless(MD0_92.is_file() and JOBS_JSON.is_file() and STAGE_TREE.is_dir(), "Stage A small root not present")
class StageARoot(unittest.TestCase):
    """The tree the small root was packed from (the APFS container stores the plists in a form a byte search does not find, so the container itself is tied to the tree only by its recorded hash)."""

    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads(JOBS_JSON.read_text())
        cls.table = cls.rec["job_table"]

    def test_the_root_file_is_the_one_the_table_describes(self):
        self.assertEqual(hashlib.sha256(MD0_92.read_bytes()).hexdigest(), self.rec["small_root"]["sha256"])
        self.assertEqual(MD0_92.stat().st_size, self.rec["small_root"]["bytes"])

    def test_the_table_has_19_apple_jobs_and_the_heartbeat_and_none_of_the_skipped(self):
        labels = [t["label"] for t in self.table]
        self.assertEqual(len(labels), 20)
        self.assertEqual(len(set(labels)), 20)
        self.assertEqual(labels.count("com.nat085.ps"), 1)
        self.assertEqual(len([l for l in labels if l.startswith("com.apple.")]), 19)
        for skipped in ("com.apple.wifid", "com.apple.backboardd", "com.apple.SpringBoard"):
            self.assertNotIn(skipped, labels)

    def test_the_directory_holds_exactly_the_tables_plists_with_the_recorded_hashes(self):
        self.assertEqual(sorted(p.name for p in STAGE_TREE.iterdir()), sorted(t["label"] + ".plist" for t in self.table))
        for t in self.table:
            self.assertEqual(hashlib.sha256((STAGE_TREE / (t["label"] + ".plist")).read_bytes()).hexdigest(), t["plist_sha256"], t["label"])

    def test_every_plist_names_its_label_and_its_program_and_three_carry_a_disabled_key(self):
        import plistlib
        disabled = {}
        for t in self.table:
            d = plistlib.loads((STAGE_TREE / (t["label"] + ".plist")).read_bytes())
            self.assertEqual(d["Label"], t["label"])
            prog = d.get("Program") or d["ProgramArguments"][0]
            self.assertEqual(prog, t["program"], t["label"])
            if "Disabled" in d:
                disabled[t["label"]] = d["Disabled"]
        # read from the stock plists by hand: syslogd is plainly disabled, two jobs are disabled while a feature flag is off (the flag state of the phone's userland is not known here)
        self.assertEqual(disabled, {"com.apple.syslogd": True,
                                    "com.apple.cfprefsd.xpc.daemon.system": {"#IfFeatureFlagDisabled": "CoreFoundation/CFPreferencesSystemSession", "#Then": True},
                                    "com.apple.containermanagerd.system": {"#IfFeatureFlagDisabled": "containermanagerd/user_system_split", "#Then": True}})


class SessionDriver(unittest.TestCase):
    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_the_committed_driver_equals_its_derivation(self):
        text, done = D.build()
        self.assertEqual((HERE / "session_nat092.py").read_text(), text)
        self.assertEqual(len(done), 9)
        self.assertTrue(all(n == 1 for _, n in done))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_the_driver_names_this_images_hashes_and_not_nat087s(self):
        pkg = json.loads(PKG.read_text())["images"][D.IMAGE_NEW]
        t = (HERE / "session_nat092.py").read_text()
        for h in (pkg["recovery_sha256"], pkg["payload_sha256"]):
            self.assertEqual(t.count(h), 1)
        self.assertIn("CANARY_LEN=%d" % pkg["payload_bytes"], t)
        for old in (D.OLD_SHA, D.OLD_PAYLOAD_SHA, "artifacts/nat-087/package-001", "nat087-%s-single-run", "artifacts/nat-087/native-attempt", D.IMAGE_OLD):
            self.assertNotIn(old, t)
        self.assertIn("artifacts/nat-083/system-padded.apfs", t)                           # the big root is deliberately NAT-083's
        self.assertIn("'NAT-083','NAT-084','NAT-085','NAT-087','NAT-089','NAT-090','NAT-092')", t)
        self.assertIn("nat092-%s-single-run", t)
        self.assertIn("artifacts/nat-092/native-attempt-%s-used.json", t)
        self.assertIn("analyze_nat087.py (chain rows) and analyze_nat089.py (Stage A rows)", t)

    def test_a_drifted_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session_nat087.py"
            p.write_bytes(D.SRC.read_bytes() + b"# drift\n")
            with mock.patch.object(D, "SRC", p):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("not the file this derivation was written for", str(cm.exception))

    def test_a_missing_substitution_target_is_refused_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.py"
            p.write_text(D.SRC.read_text().replace("'NAT-085','NAT-087')", "'NAT-085')"))
            with mock.patch.object(D, "SRC", p), mock.patch.object(D, "SRC_SHA256", hashlib.sha256(p.read_bytes()).hexdigest()):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("required tasks: expected 1 occurrence(s)", str(cm.exception))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_a_payload_of_another_length_is_refused(self):
        pkg = json.loads(PKG.read_text())
        pkg["images"][D.IMAGE_NEW]["payload_bytes"] += 8
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text(json.dumps(pkg))
            with mock.patch.object(D, "PACKAGE", Path(d)):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("CANARY_LEN", str(cm.exception))

    def test_the_source_is_nat087s_driver_and_its_old_values_are_nat087s(self):
        self.assertEqual(D.SRC, ROOT / "docs/procedures/nat-087/session_nat087.py")
        self.assertEqual(hashlib.sha256(D.SRC.read_bytes()).hexdigest(), D.SRC_SHA256)
        t = D.SRC.read_text()
        self.assertEqual((t.count(D.OLD_SHA), t.count(D.OLD_PAYLOAD_SHA), t.count(D.IMAGE_OLD)), (1, 1, 1))


class DeriveCommand(unittest.TestCase):
    NAME = "session_nat092.py"

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = D.main(argv)
        return rc, out.getvalue(), err.getvalue()

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_check_says_ok_with_the_substitution_count_and_prints_nothing_else(self):
        self.assertEqual(self.call(["--check"]), (0, "ok: session_nat092.py equals the derivation (9 substitutions)\n", ""))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_check_names_the_difference_on_stderr_and_never_writes(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / self.NAME
            other.write_text("x")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat092.py differs from the derivation\n"))
            self.assertEqual(other.read_text(), "x")
            with mock.patch.object(D, "OUT", Path(d) / "missing.py"):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat092.py differs from the derivation\n"))
            self.assertFalse((Path(d) / "missing.py").exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_without_check_it_writes_the_driver_and_reports_its_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)
            (fake / "docs/procedures/nat-092").mkdir(parents=True)
            target = fake / "docs/procedures/nat-092" / self.NAME
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
            self.assertEqual((rc, err), (0, ""))
            text, done = D.build()
            self.assertEqual(target.read_text(), text)
            self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")
            rep = json.loads(out)
            self.assertEqual(rep["out"], "docs/procedures/nat-092/session_nat092.py")
            self.assertEqual(rep["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(len(rep["substitutions"]), 9)
            self.assertTrue(all(s["count"] == 1 for s in rep["substitutions"]))

    def test_a_drifted_source_is_refused_with_status_2_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            drifted = Path(d) / "session_nat087.py"
            drifted.write_text(D.SRC.read_text() + "\n# drift\n")
            target = Path(d) / self.NAME
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
                rc2, out2, err2 = self.call(["--check"])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: session_nat087.py is not the file this derivation was written for"), err)
            self.assertEqual((rc2, out2), (2, ""))
            self.assertFalse(target.exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-092/package-001 not present")
    def test_run_as_a_script_the_flag_reaches_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive92.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ok: session_nat092.py equals the derivation (9 substitutions)\n", ""))

    def test_the_output_path_is_the_committed_driver(self):
        self.assertEqual(D.OUT, HERE / "session_nat092.py")


if __name__ == "__main__":
    unittest.main()
