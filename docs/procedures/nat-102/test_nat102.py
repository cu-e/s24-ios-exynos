#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102 host tests: the build wrapper of the heartbeat image, the built payload against NAT-096's, the small root (file for file against NAT-096's quiet Stage A root: the same except `bin/hb` and the
`/etc/rc` line that starts it) and the derived session driver. Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-102/test_nat102.py      (opens no device)

What the tests stand on (so that they do not merely mirror the code under test):

  * the built payload is compared byte for byte with NAT-096's: the only differences are the five bytes of the command-line tag and the 4 MiB md0 region (which must equal the heartbeat root
    file, and NAT-096's md0 region must equal NAT-096's root file); the loader differs only in the words that encode the image name;
  * the heartbeat small root's source tree is compared file by file (sha256) with NAT-096's: the same 25 files, none changed except `etc/rc`, plus the one new file `bin/hb`; the rc differs by exactly the
    four added lines; the hb file is the NAT-101 build; the container itself is tied to the tree by the recorded and pinned hash only (a byte search does not find the files inside it);
  * the driver is the derivation's output, and names this image's hashes and not NAT-096's.
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


D = load("nat102_test_derive", HERE / "derive102.py")
PKG = ROOT / "artifacts/nat-102/package-001/package.json"
BUILD102 = ROOT / "artifacts/nat-102/build-001/loader-diag-xnu-hb-md1/Image.payload"
BUILD96 = ROOT / "artifacts/nat-096/build-001/loader-diag-xnu-sq-md1/Image.payload"
BUILD_JSON = ROOT / "artifacts/nat-102/build-001/build.json"
MD0_102 = ROOT / "artifacts/nat-101/pid1-hb/root.apfs"
MD0_96 = ROOT / "artifacts/nat-096/pid1-sq/root.apfs"
TREE_102 = ROOT / "artifacts/nat-101/pid1-hb/root"
TREE_96 = ROOT / "artifacts/nat-096/pid1-sq/root"
HB_ROOT_JSON = ROOT / "artifacts/nat-101/pid1-hb/build.json"
JOBS_96 = ROOT / "docs/procedures/nat-096/stage-a-nolsd-jobs.json"
HB_SHA256 = "1819a4a89ec06403fa21df2facd73ff9723c2debd03c2ec6df9d7f6717103163"
CMDLINE_OFF, CMDLINE_LEN = 0x48, 608                    # the SWEETXNU header's command line field (NAT-065's build.py)
LOADER_BYTES = 385024                                   # the loader Image in front of the XNU payload
MD0_BYTES = 4194304
TAG96, TAG102 = "NAT096-sq1", "NAT102-hb1"


class BuildMain(unittest.TestCase):
    """main() with NAT-087's main() replaced by a stand-in that records what the globals look like while it runs and writes a build.json like NAT-083's and NAT-087's."""

    @classmethod
    def setUpClass(cls):
        cls.B = load("nat102_test_build_main", HERE / "build.py")

    def md0(self, d, size=MD0_BYTES, fill=b"\x5a"):
        p = Path(d) / "root.apfs"
        p.write_bytes(fill * size)
        return p, hashlib.sha256(fill * size).hexdigest()

    def go(self, argv, record_md0=None, change=None, raises=None, write=True, pin="file"):
        """pin: "file" = the pinned hash is made the hash of the --ramdisk file (the real pin is tested on its own), None = the real pin, else a hash string."""
        B, seen = self.B, {}
        if pin == "file" and "--ramdisk" in argv:
            pin = hashlib.sha256(Path(argv[argv.index("--ramdisk") + 1]).read_bytes()).hexdigest()

        def b87_main():
            seen["name"], seen["tag"] = B.b87.NAME, B.b87.NEW_TAG
            if raises:
                raise raises
            if "--out" in argv and write:
                rec = {"nat083_changes": {"md0_image": record_md0}, "nat087_changes": change if change is not None else {"image_name": B.NAME, "cmdline_tag": B.NEW_TAG,
                                                                                                                         "cmdline": "rd=md1 x xrd=md0"}, "other": 1}
                (Path(argv[argv.index("--out") + 1]) / "build.json").write_text(json.dumps(rec))

        before = (B.b87.NAME, B.b87.NEW_TAG)
        with mock.patch.object(B.b87, "main", b87_main), mock.patch.object(sys, "argv", ["build.py"] + argv), mock.patch.object(B, "MD0_SHA256", pin if pin not in (None, "file") else B.MD0_SHA256):
            try:
                B.main()
            finally:
                seen["after"] = (B.b87.NAME, B.b87.NEW_TAG)
        seen["before"] = before
        return seen

    def test_names_have_the_lengths_of_nat087s(self):
        self.assertEqual((self.B.NAME, self.B.NEW_TAG), ("loader-diag-xnu-hb-md1", "nat_attempt=NAT102-hb1"))
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
        self.assertEqual(str(cm.exception), "--ramdisk is required: the NAT-101 small root (NAT-096's plus the heartbeat)")

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

    def test_a_ramdisk_of_the_right_size_and_another_hash_is_refused_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            ran = []
            with mock.patch.object(self.B.b87, "main", lambda: ran.append(1)), mock.patch.object(sys, "argv", ["build.py", "--ramdisk", str(p)]):
                with self.assertRaises(SystemExit) as cm:
                    self.B.main()
            self.assertEqual(str(cm.exception), "the small root is sha256 %s, not the pinned %s" % (h, self.B.MD0_SHA256))
            self.assertEqual(ran, [])

    def test_the_pin_is_a_sha256_and_the_pinned_file_when_present_has_it(self):
        self.assertRegex(self.B.MD0_SHA256, "^[0-9a-f]{64}$")
        self.assertNotEqual(self.B.MD0_SHA256, "62801cecc5cdf1e2bfaff8c056bd02e2539295e516fe2011b82fa3d2a5a37057")     # not NAT-096's root (the one without the heartbeat)
        if MD0_102.is_file():
            self.assertEqual(hashlib.sha256(MD0_102.read_bytes()).hexdigest(), self.B.MD0_SHA256)
            self.assertEqual(MD0_102.stat().st_size, self.B.MD0_BYTES)

    def test_a_build_with_the_pinned_hash_passes_the_pin(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            seen = self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h), pin=h)
        self.assertEqual((seen["name"], seen["tag"]), (self.B.NAME, self.B.NEW_TAG))

    def test_check_only_needs_no_ramdisk_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(self.B.b87, "main", lambda: None), mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", d]):
            self.assertIsNone(self.B.main())
            self.assertEqual(os.listdir(d), [])

    def test_build_json_gets_the_nat102_record_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h))
            rec = json.loads((Path(d) / "build.json").read_text())
        self.assertEqual(rec["other"], 1)
        self.assertEqual(rec["nat102_changes"], {"image_name": self.B.NAME, "cmdline_tag": self.B.NEW_TAG, "md0_sha256": h, "md0_bytes": MD0_BYTES, "cmdline": "rd=md1 x xrd=md0"})
        self.assertEqual(rec["nat102_sources"], {"build.py": hashlib.sha256((HERE / "build.py").read_bytes()).hexdigest()})
        self.assertIn("NAT-101 small root as md0", rec["nat102_note"])
        self.assertIn("18 Apple job plists plus the ps heartbeat job, plus the hb program started from /etc/rc", rec["nat102_note"])
        self.assertIn("nothing here ran on a phone", rec["nat102_note"])

    def test_a_build_json_with_another_md0_hash_or_size_is_refused(self):
        for bad in (dict(bytes=MD0_BYTES, sha256="0" * 64), dict(bytes=MD0_BYTES - 1, sha256=None), None):
            with tempfile.TemporaryDirectory() as d:
                p, h = self.md0(d)
                if bad is not None and bad["sha256"] is None:
                    bad = dict(bytes=bad["bytes"], sha256=h)
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p), "--out", d], record_md0=bad)
                self.assertTrue(str(cm.exception).startswith("build.json records md0 "), str(cm.exception))
                self.assertNotIn("nat102_changes", json.loads((Path(d) / "build.json").read_text()))

    def test_a_build_json_with_another_name_or_tag_is_refused(self):
        for bad in ({"image_name": "loader-diag-xnu-sq-md1", "cmdline_tag": self.B.NEW_TAG}, {"image_name": self.B.NAME, "cmdline_tag": "nat_attempt=NAT096-sq1"}, {}):
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
        self.assertEqual((r.returncode, r.stdout, r.stderr), (1, "", "--ramdisk is required: the NAT-101 small root (NAT-096's plus the heartbeat)\n"))


@unittest.skipUnless(BUILD102.is_file() and BUILD96.is_file() and BUILD_JSON.is_file() and MD0_102.is_file() and MD0_96.is_file(), "built payloads / small roots not present")
class BuiltPayload(unittest.TestCase):
    """The heartbeat image against NAT-096's: the same payload except the command-line tag and the md0 region; the loader except its name immediates."""

    @classmethod
    def setUpClass(cls):
        cls.raw102, cls.raw96 = BUILD102.read_bytes(), BUILD96.read_bytes()
        cls.p102, cls.p96 = cls.raw102[LOADER_BYTES:], cls.raw96[LOADER_BYTES:]
        cls.rec = json.loads(BUILD_JSON.read_text())
        cls.m102, cls.m96 = MD0_102.read_bytes(), MD0_96.read_bytes()

    def cmd(self, p):
        return p[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()

    def test_the_command_line_is_nat096s_with_the_new_tag_and_still_ends_in_the_token(self):
        c = self.cmd(self.p102)
        self.assertEqual(c, self.cmd(self.p96).replace(TAG96, TAG102))
        self.assertEqual(c, self.rec["nat102_changes"]["cmdline"])
        self.assertTrue(c.endswith(" xrd=md0"))
        self.assertEqual([t for t in c.split() if t.startswith("rd=")], ["rd=md1"])
        self.assertEqual(c.count("xrd="), 1)
        self.assertEqual(c.count("nat_attempt=NAT102-hb1"), 1)
        self.assertNotIn("max_cpumon", c)                                              # no boot-arg changes: the only change is the program started from /etc/rc

    def test_md0_of_each_payload_is_its_small_root_at_the_same_offset(self):
        o96, o102 = self.p96.find(self.m96), self.p102.find(self.m102)
        self.assertGreater(o96, 0)
        self.assertEqual((o96, len(self.m96), len(self.m102)), (o102, MD0_BYTES, MD0_BYTES))
        self.assertEqual(self.p96.count(self.m96), 1)
        self.assertEqual(self.p102.count(self.m102), 1)
        self.assertEqual(hashlib.sha256(self.m102).hexdigest(), self.rec["nat102_changes"]["md0_sha256"])
        self.assertNotEqual(self.m102, self.m96)

    def test_nothing_else_in_the_payload_differs_from_nat096s(self):
        o = self.p96.find(self.m96)
        want = bytearray(self.p96)
        want[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = self.cmd(self.p96).replace(TAG96, TAG102).encode().ljust(CMDLINE_LEN, b"\0")
        want[o:o + MD0_BYTES] = self.m102
        self.assertEqual(bytes(want), self.p102)                                           # ADT, kernel, delivery parameters are NAT-096's
        self.assertEqual(len(self.p102), len(self.p96))

    def test_outside_md0_only_the_five_tag_bytes_differ(self):
        o = self.p96.find(self.m96)
        diff = [i for i in range(len(self.p96)) if self.p96[i] != self.p102[i] and not (o <= i < o + MD0_BYTES)]
        start = self.p96.find(TAG96.encode())
        self.assertTrue(CMDLINE_OFF <= start < CMDLINE_OFF + CMDLINE_LEN, start)
        self.assertEqual(diff, [start + 3, start + 4, start + 5, start + 7, start + 8])    # 'NAT096-sq1' -> 'NAT102-hb1'

    def test_the_loader_differs_only_in_its_name_immediates(self):
        a, b = self.raw96[:LOADER_BYTES], self.raw102[:LOADER_BYTES]
        diff = [i for i in range(LOADER_BYTES) if a[i] != b[i]]
        self.assertTrue(0 < len(diff) <= 40, len(diff))
        self.assertTrue(64000 <= diff[0] and diff[-1] <= 64500, (diff[0], diff[-1]))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_the_payload_has_the_packaged_size_and_hash(self):
        want = json.loads(PKG.read_text())["images"]["loader-diag-xnu-hb-md1"]
        self.assertEqual((len(self.raw102), len(self.raw96)), (want["payload_bytes"], want["payload_bytes"]))
        self.assertEqual(hashlib.sha256(self.raw102).hexdigest(), want["payload_sha256"])


def tree_hashes(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_symlink():
            out[str(p.relative_to(root))] = "->" + os.readlink(p)
        elif p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@unittest.skipUnless(MD0_102.is_file() and JOBS_96.is_file() and TREE_102.is_dir() and TREE_96.is_dir(), "small root trees not present")
class HeartbeatRoot(unittest.TestCase):
    """The tree the heartbeat small root was packed from, against NAT-096's tree and table (the APFS container stores the files in a form a byte search does not find, so the container is tied to the tree by the pinned hash)."""

    @classmethod
    def setUpClass(cls):
        cls.t102, cls.t96 = tree_hashes(TREE_102), tree_hashes(TREE_96)
        cls.jobs = json.loads(JOBS_96.read_text())

    def test_the_tree_is_nat096s_plus_bin_hb_with_only_etc_rc_changed(self):
        self.assertEqual((len(self.t96), len(self.t102)), (25, 26))
        self.assertEqual(sorted(set(self.t102) - set(self.t96)), ["bin/hb"])
        self.assertEqual(sorted(set(self.t96) - set(self.t102)), [])
        self.assertEqual(sorted(k for k in self.t96 if self.t96[k] != self.t102[k]), ["etc/rc"])

    def test_the_launch_daemons_are_exactly_nat096s_and_match_its_job_table(self):
        d = TREE_102 / "LaunchDaemons"
        self.assertEqual(sorted(p.name for p in d.iterdir()), sorted(t["label"] + ".plist" for t in self.jobs["job_table"]))
        for t in self.jobs["job_table"]:
            self.assertEqual(hashlib.sha256((d / (t["label"] + ".plist")).read_bytes()).hexdigest(), t["plist_sha256"], t["label"])
        self.assertEqual(len(self.jobs["job_table"]), 19)
        self.assertEqual(self.t102["bin/child"], self.t96["bin/child"])

    def test_the_rc_differs_by_exactly_the_four_added_lines_before_the_exec_line(self):
        a = (TREE_96 / "etc/rc").read_text().splitlines()
        b = (TREE_102 / "etc/rc").read_text().splitlines()
        self.assertEqual(len(b), len(a) + 4)
        self.assertTrue(a[-1].startswith("exec /sbin/launchd.darwin"), a[-1])
        self.assertEqual(b[-1], a[-1])
        self.assertEqual(b[:len(a) - 1], a[:-1])
        added = b[len(a) - 1:-1]
        self.assertEqual(len(added), 4)
        self.assertTrue(all(l.startswith("#") for l in added[:3]), added)
        self.assertEqual(added[3], "/redwood/bin/hb &")
        self.assertEqual(sum(1 for l in b if l.strip() == "/redwood/bin/hb &"), 1)

    def test_hb_is_the_nat101_build_executable_and_static(self):
        data = (TREE_102 / "bin/hb").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), HB_SHA256)
        self.assertEqual((TREE_102 / "bin/hb").stat().st_mode & 0o777, 0o755)
        self.assertEqual(data[:4], bytes.fromhex("cffaedfe"))                                  # 64-bit Mach-O, little endian
        self.assertNotIn(b"/usr/lib/dyld", data)                                              # no dynamic loader: it is a static program
        self.assertNotIn(b"libSystem", data)

    def test_the_root_file_is_the_one_the_record_and_the_pin_describe(self):
        data = MD0_102.read_bytes()
        rec = json.loads(HB_ROOT_JSON.read_text())
        self.assertEqual(hashlib.sha256(data).hexdigest(), rec["root_apfs"]["sha256"])
        self.assertEqual(len(data), rec["root_apfs"]["bytes"])
        self.assertEqual(rec["root_apfs"]["sha256"], load("nat102_test_build_pin", HERE / "build.py").MD0_SHA256)
        self.assertEqual(rec["base"]["root_apfs_sha256"], hashlib.sha256(MD0_96.read_bytes()).hexdigest())
        self.assertEqual(rec["added"]["bin/hb"]["sha256"], HB_SHA256)
        self.assertEqual(rec["kernel_apfs_lib_readback"]["mismatches"], [])


class SessionDriver(unittest.TestCase):
    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_the_committed_driver_equals_its_derivation(self):
        text, done = D.build()
        self.assertEqual((HERE / "session_nat102.py").read_text(), text)
        self.assertEqual(len(done), 9)
        self.assertTrue(all(n == 1 for _, n in done))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_the_driver_names_this_images_hashes_and_not_nat096s(self):
        pkg = json.loads(PKG.read_text())["images"][D.IMAGE_NEW]
        t = (HERE / "session_nat102.py").read_text()
        for h in (pkg["recovery_sha256"], pkg["payload_sha256"]):
            self.assertEqual(t.count(h), 1)
        self.assertIn("CANARY_LEN=%d" % pkg["payload_bytes"], t)
        for old in (D.OLD_SHA, D.OLD_PAYLOAD_SHA, "artifacts/nat-096/package-001", "nat096-%s-single-run", "artifacts/nat-096/native-attempt", D.IMAGE_OLD):
            self.assertNotIn(old, t)
        self.assertIn("artifacts/nat-083/system-padded.apfs", t)                           # the big root is deliberately NAT-083's
        self.assertIn("'NAT-083','NAT-084','NAT-085','NAT-087','NAT-089','NAT-090','NAT-092','NAT-096','NAT-097','NAT-101','NAT-102')", t)
        self.assertIn("nat102-%s-single-run", t)
        self.assertIn("artifacts/nat-102/native-attempt-%s-used.json", t)
        self.assertIn("analyze_nat087.py (chain rows), analyze_nat097.py (Stage A rows over NAT-097's reader", t)
        self.assertIn("and analyze_nat102.py (heartbeat rows H1-H5 over the same text) (run separately)", t)
        self.assertNotIn("analyze_nat089.py", t.split('"""')[1].split("(run separately)")[0].split("analyses are")[1])

    def test_a_drifted_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session_nat096.py"
            p.write_bytes(D.SRC.read_bytes() + b"# drift\n")
            with mock.patch.object(D, "SRC", p):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("not the file this derivation was written for", str(cm.exception))

    def test_a_missing_substitution_target_is_refused_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.py"
            p.write_text(D.SRC.read_text().replace("'NAT-092','NAT-096','NAT-097')", "'NAT-092','NAT-096')"))
            with mock.patch.object(D, "SRC", p), mock.patch.object(D, "SRC_SHA256", hashlib.sha256(p.read_bytes()).hexdigest()):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("required tasks: expected 1 occurrence(s)", str(cm.exception))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_a_payload_of_another_length_is_refused(self):
        pkg = json.loads(PKG.read_text())
        pkg["images"][D.IMAGE_NEW]["payload_bytes"] += 8
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text(json.dumps(pkg))
            with mock.patch.object(D, "PACKAGE", Path(d)):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("CANARY_LEN", str(cm.exception))

    def test_the_source_is_nat096s_driver_and_its_old_values_are_nat096s(self):
        self.assertEqual(D.SRC, ROOT / "docs/procedures/nat-096/session_nat096.py")
        self.assertEqual(hashlib.sha256(D.SRC.read_bytes()).hexdigest(), D.SRC_SHA256)
        t = D.SRC.read_text()
        self.assertEqual((t.count(D.OLD_SHA), t.count(D.OLD_PAYLOAD_SHA), t.count(D.IMAGE_OLD)), (1, 1, 1))


class DeriveCommand(unittest.TestCase):
    NAME = "session_nat102.py"

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = D.main(argv)
        return rc, out.getvalue(), err.getvalue()

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_check_says_ok_with_the_substitution_count_and_prints_nothing_else(self):
        self.assertEqual(self.call(["--check"]), (0, "ok: session_nat102.py equals the derivation (9 substitutions)\n", ""))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_check_names_the_difference_on_stderr_and_never_writes(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / self.NAME
            other.write_text("x")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat102.py differs from the derivation\n"))
            self.assertEqual(other.read_text(), "x")
            with mock.patch.object(D, "OUT", Path(d) / "missing.py"):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat102.py differs from the derivation\n"))
            self.assertFalse((Path(d) / "missing.py").exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_without_check_it_writes_the_driver_and_reports_its_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)
            (fake / "docs/procedures/nat-102").mkdir(parents=True)
            target = fake / "docs/procedures/nat-102" / self.NAME
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
            self.assertEqual((rc, err), (0, ""))
            text, done = D.build()
            self.assertEqual(target.read_text(), text)
            self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")
            rep = json.loads(out)
            self.assertEqual(rep["out"], "docs/procedures/nat-102/session_nat102.py")
            self.assertEqual(rep["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(len(rep["substitutions"]), 9)
            self.assertTrue(all(s["count"] == 1 for s in rep["substitutions"]))

    def test_a_drifted_source_is_refused_with_status_2_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            drifted = Path(d) / "session_nat096.py"
            drifted.write_text(D.SRC.read_text() + "\n# drift\n")
            target = Path(d) / self.NAME
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
                rc2, out2, err2 = self.call(["--check"])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: session_nat096.py is not the file this derivation was written for"), err)
            self.assertEqual((rc2, out2), (2, ""))
            self.assertFalse(target.exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-102/package-001 not present")
    def test_run_as_a_script_the_flag_reaches_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive102.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ok: session_nat102.py equals the derivation (9 substitutions)\n", ""))

    def test_the_output_path_is_the_committed_driver(self):
        self.assertEqual(D.OUT, HERE / "session_nat102.py")


if __name__ == "__main__":
    unittest.main()
