#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-096 host tests: the build wrapper of the quiet Stage A image, the built payload against NAT-092's, the small root (file for file against NAT-089's Stage A root: the same except the
com.apple.lsd plist) and the derived session driver. Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-096/test_nat096.py      (opens no device)

What the tests stand on (so that they do not merely mirror the code under test):

  * the built payload is compared byte for byte with NAT-092's: the only differences are the two bytes of the command-line tag and the 4 MiB md0 region (which must equal the quiet root
    file, and NAT-092's md0 region must equal NAT-089's root file); the loader differs only in the words that encode the image name;
  * the quiet small root's source tree is compared file by file (sha256) with NAT-089's: the same 25 files, none changed, plus the one NAT-089 file that is missing here (LaunchDaemons/com.apple.lsd.plist),
    and the job table is NAT-089's minus that one entry; the container itself is tied to the tree by the recorded and pinned hash only (a byte search does not find the plists inside it);
  * the driver is the derivation's output, and names this image's hashes and not NAT-092's.
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


D = load("nat096_test_derive", HERE / "derive96.py")
PKG = ROOT / "artifacts/nat-096/package-001/package.json"
BUILD96 = ROOT / "artifacts/nat-096/build-001/loader-diag-xnu-sq-md1/Image.payload"
BUILD92 = ROOT / "artifacts/nat-092/build-001/loader-diag-xnu-sb-md1/Image.payload"
BUILD92_JSON = ROOT / "artifacts/nat-092/build-001/build.json"
BUILD_JSON = ROOT / "artifacts/nat-096/build-001/build.json"
MD0_96 = ROOT / "artifacts/nat-096/pid1-sq/root.apfs"
MD0_92 = ROOT / "artifacts/nat-089/pid1-stageA/root.apfs"
TREE_96 = ROOT / "artifacts/nat-096/pid1-sq/root"
TREE_89 = ROOT / "artifacts/nat-089/pid1-stageA/root"
JOBS_89 = ROOT / "docs/procedures/nat-089/stage-a-jobs.json"
JOBS_96 = HERE / "stage-a-nolsd-jobs.json"
CMDLINE_OFF, CMDLINE_LEN = 0x48, 608                    # the SWEETXNU header's command line field (NAT-065's build.py)
LOADER_BYTES = 385024                                   # the loader Image in front of the XNU payload
MD0_BYTES = 4194304
TAG92, TAG96 = "NAT092-sb1", "NAT096-sq1"
LSD_PLIST = "LaunchDaemons/com.apple.lsd.plist"


class BuildMain(unittest.TestCase):
    """main() with NAT-087's main() replaced by a stand-in that records what the globals look like while it runs and writes a build.json like NAT-083's and NAT-087's."""

    @classmethod
    def setUpClass(cls):
        cls.B = load("nat096_test_build_main", HERE / "build.py")

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
        self.assertEqual((self.B.NAME, self.B.NEW_TAG), ("loader-diag-xnu-sq-md1", "nat_attempt=NAT096-sq1"))
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
        self.assertEqual(str(cm.exception), "--ramdisk is required: the Stage A small root without the lsd job")

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
        self.assertNotEqual(self.B.MD0_SHA256, "90c85ffb4e4a6857b3e7d46be3aff910b9b4ba7a9deadd75ad6fb942453a43f1")     # not NAT-089's root (the one with the lsd job)
        if MD0_96.is_file():
            self.assertEqual(hashlib.sha256(MD0_96.read_bytes()).hexdigest(), self.B.MD0_SHA256)
            self.assertEqual(MD0_96.stat().st_size, self.B.MD0_BYTES)

    def test_a_build_with_the_pinned_hash_passes_the_pin(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            seen = self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h), pin=h)
        self.assertEqual((seen["name"], seen["tag"]), (self.B.NAME, self.B.NEW_TAG))

    def test_check_only_needs_no_ramdisk_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(self.B.b87, "main", lambda: None), mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", d]):
            self.assertIsNone(self.B.main())
            self.assertEqual(os.listdir(d), [])

    def test_build_json_gets_the_nat096_record_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h))
            rec = json.loads((Path(d) / "build.json").read_text())
        self.assertEqual(rec["other"], 1)
        self.assertEqual(rec["nat096_changes"], {"image_name": self.B.NAME, "cmdline_tag": self.B.NEW_TAG, "md0_sha256": h, "md0_bytes": MD0_BYTES, "cmdline": "rd=md1 x xrd=md0"})
        self.assertEqual(rec["nat096_sources"], {"build.py": hashlib.sha256((HERE / "build.py").read_bytes()).hexdigest()})
        self.assertIn("minus the com.apple.lsd job", rec["nat096_note"])
        self.assertIn("18 Apple job plists plus the ps heartbeat", rec["nat096_note"])
        self.assertIn("nothing here ran on a phone", rec["nat096_note"])

    def test_a_build_json_with_another_md0_hash_or_size_is_refused(self):
        for bad in (dict(bytes=MD0_BYTES, sha256="0" * 64), dict(bytes=MD0_BYTES - 1, sha256=None), None):
            with tempfile.TemporaryDirectory() as d:
                p, h = self.md0(d)
                if bad is not None and bad["sha256"] is None:
                    bad = dict(bytes=bad["bytes"], sha256=h)
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p), "--out", d], record_md0=bad)
                self.assertTrue(str(cm.exception).startswith("build.json records md0 "), str(cm.exception))
                self.assertNotIn("nat096_changes", json.loads((Path(d) / "build.json").read_text()))

    def test_a_build_json_with_another_name_or_tag_is_refused(self):
        for bad in ({"image_name": "loader-diag-xnu-sb-md1", "cmdline_tag": self.B.NEW_TAG}, {"image_name": self.B.NAME, "cmdline_tag": "nat_attempt=NAT092-sb1"}, {}):
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
        self.assertEqual((r.returncode, r.stdout, r.stderr), (1, "", "--ramdisk is required: the Stage A small root without the lsd job\n"))


@unittest.skipUnless(BUILD96.is_file() and BUILD92.is_file() and BUILD_JSON.is_file() and MD0_96.is_file() and MD0_92.is_file(), "built payloads / small roots not present")
class BuiltPayload(unittest.TestCase):
    """The quiet image against NAT-092's: the same payload except the command-line tag and the md0 region; the loader except its name immediates."""

    @classmethod
    def setUpClass(cls):
        cls.raw96, cls.raw92 = BUILD96.read_bytes(), BUILD92.read_bytes()
        cls.p96, cls.p92 = cls.raw96[LOADER_BYTES:], cls.raw92[LOADER_BYTES:]
        cls.rec = json.loads(BUILD_JSON.read_text())
        cls.m96, cls.m92 = MD0_96.read_bytes(), MD0_92.read_bytes()

    def cmd(self, p):
        return p[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()

    def test_the_command_line_is_nat092s_with_the_new_tag_and_still_ends_in_the_token(self):
        c = self.cmd(self.p96)
        self.assertEqual(c, self.cmd(self.p92).replace(TAG92, TAG96))
        self.assertEqual(c, self.rec["nat096_changes"]["cmdline"])
        self.assertTrue(c.endswith(" xrd=md0"))
        self.assertEqual([t for t in c.split() if t.startswith("rd=")], ["rd=md1"])
        self.assertEqual(c.count("xrd="), 1)
        self.assertEqual(c.count("nat_attempt=NAT096-sq1"), 1)
        self.assertNotIn("max_cpumon", c)                                              # no boot-arg changes: the only change is the job set

    def test_md0_of_each_payload_is_its_small_root_at_the_same_offset(self):
        o92, o96 = self.p92.find(self.m92), self.p96.find(self.m96)
        self.assertGreater(o92, 0)
        self.assertEqual((o92, len(self.m92), len(self.m96)), (o96, MD0_BYTES, MD0_BYTES))
        self.assertEqual(self.p92.count(self.m92), 1)
        self.assertEqual(self.p96.count(self.m96), 1)
        self.assertEqual(hashlib.sha256(self.m96).hexdigest(), self.rec["nat096_changes"]["md0_sha256"])
        self.assertNotEqual(self.m96, self.m92)

    def test_nothing_else_in_the_payload_differs_from_nat092s(self):
        o = self.p92.find(self.m92)
        want = bytearray(self.p92)
        want[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = self.cmd(self.p92).replace(TAG92, TAG96).encode().ljust(CMDLINE_LEN, b"\0")
        want[o:o + MD0_BYTES] = self.m96
        self.assertEqual(bytes(want), self.p96)                                            # ADT, kernel, delivery parameters are NAT-092's
        self.assertEqual(len(self.p96), len(self.p92))

    def test_outside_md0_only_the_two_tag_bytes_differ(self):
        o = self.p92.find(self.m92)
        diff = [i for i in range(len(self.p92)) if self.p92[i] != self.p96[i] and not (o <= i < o + MD0_BYTES)]
        start = self.p92.find(TAG92.encode())
        self.assertTrue(CMDLINE_OFF <= start < CMDLINE_OFF + CMDLINE_LEN, start)
        self.assertEqual(diff, [start + 5, start + 8])                                     # '2' -> '6' and 'b' -> 'q'

    def test_the_loader_differs_only_in_its_name_immediates(self):
        a, b = self.raw92[:LOADER_BYTES], self.raw96[:LOADER_BYTES]
        diff = [i for i in range(LOADER_BYTES) if a[i] != b[i]]
        self.assertTrue(0 < len(diff) <= 40, len(diff))
        self.assertTrue(64000 <= diff[0] and diff[-1] <= 64500, (diff[0], diff[-1]))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_the_payload_has_the_packaged_size_and_hash(self):
        want = json.loads(PKG.read_text())["images"]["loader-diag-xnu-sq-md1"]
        self.assertEqual((len(self.raw96), len(self.raw92)), (want["payload_bytes"], want["payload_bytes"]))
        self.assertEqual(hashlib.sha256(self.raw96).hexdigest(), want["payload_sha256"])


def tree_hashes(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_symlink():
            out[str(p.relative_to(root))] = "->" + os.readlink(p)
        elif p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@unittest.skipUnless(MD0_96.is_file() and JOBS_89.is_file() and TREE_96.is_dir() and TREE_89.is_dir(), "small root trees not present")
class QuietRoot(unittest.TestCase):
    """The tree the quiet small root was packed from, against NAT-089's Stage A tree and table (the APFS container stores the plists in a form a byte search does not find, so the container is tied to the tree by the pinned hash)."""

    @classmethod
    def setUpClass(cls):
        cls.t96, cls.t89 = tree_hashes(TREE_96), tree_hashes(TREE_89)
        cls.rec96 = json.loads(JOBS_96.read_text())
        cls.rec89 = json.loads(JOBS_89.read_text())

    def test_the_tree_is_nat089s_minus_exactly_the_lsd_plist(self):
        self.assertEqual(len(self.t89), 26)
        self.assertEqual(len(self.t96), 25)
        self.assertEqual(sorted(set(self.t89) - set(self.t96)), [LSD_PLIST])
        self.assertEqual(sorted(set(self.t96) - set(self.t89)), [])
        for k in self.t96:
            self.assertEqual(self.t96[k], self.t89[k], k)

    def test_the_removed_file_is_the_lsd_job_the_table_removed(self):
        removed = self.rec96["removed"]
        self.assertEqual([r["label"] for r in removed], ["com.apple.lsd"])
        self.assertEqual(removed[0]["plist_sha256"], self.t89[LSD_PLIST])
        self.assertEqual(removed[0]["program"], "/usr/libexec/lsd")
        self.assertFalse(removed[0]["self_start"])                                           # lsd is on demand: the seven self-starting jobs are untouched

    def test_the_table_is_nat089s_minus_the_lsd_entry_and_nothing_else(self):
        want = [t for t in self.rec89["job_table"] if t["label"] != "com.apple.lsd"]
        self.assertEqual(len(self.rec89["job_table"]), 20)
        self.assertEqual(self.rec96["job_table"], want)
        self.assertEqual(len(want), 19)
        labels = [t["label"] for t in want]
        self.assertEqual(labels.count("com.nat085.ps"), 1)
        self.assertEqual(len([l for l in labels if l.startswith("com.apple.")]), 18)
        for skipped in ("com.apple.wifid", "com.apple.backboardd", "com.apple.SpringBoard", "com.apple.lsd"):
            self.assertNotIn(skipped, labels)
            self.assertIn(skipped, self.rec96["skipped_jobs"])
        self.assertEqual(sorted(t["label"] for t in want if t["self_start"]), sorted(t["label"] for t in self.rec89["job_table"] if t["self_start"]))
        self.assertEqual(len([t for t in want if t["self_start"] and t["label"].startswith("com.apple.")]), 7)     # the seven self-starting Apple jobs (the heartbeat is the eighth self-starting job)

    def test_the_directory_holds_exactly_the_tables_plists_with_the_recorded_hashes(self):
        d = TREE_96 / "LaunchDaemons"
        self.assertEqual(sorted(p.name for p in d.iterdir()), sorted(t["label"] + ".plist" for t in self.rec96["job_table"]))
        for t in self.rec96["job_table"]:
            self.assertEqual(hashlib.sha256((d / (t["label"] + ".plist")).read_bytes()).hexdigest(), t["plist_sha256"], t["label"])

    def test_no_file_of_the_tree_is_named_lsd(self):
        self.assertEqual([k for k in self.t96 if "lsd" in k], [])

    def test_the_root_file_is_the_one_the_table_and_the_pin_describe(self):
        data = MD0_96.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.rec96["small_root"]["sha256"])
        self.assertEqual(len(data), self.rec96["small_root"]["bytes"])
        self.assertEqual(self.rec96["small_root"]["sha256"], load("nat096_test_build_pin", HERE / "build.py").MD0_SHA256)
        self.assertNotEqual(self.rec96["small_root"]["sha256"], self.rec89["small_root"]["sha256"])


class SessionDriver(unittest.TestCase):
    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_the_committed_driver_equals_its_derivation(self):
        text, done = D.build()
        self.assertEqual((HERE / "session_nat096.py").read_text(), text)
        self.assertEqual(len(done), 9)
        self.assertTrue(all(n == 1 for _, n in done))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_the_driver_names_this_images_hashes_and_not_nat092s(self):
        pkg = json.loads(PKG.read_text())["images"][D.IMAGE_NEW]
        t = (HERE / "session_nat096.py").read_text()
        for h in (pkg["recovery_sha256"], pkg["payload_sha256"]):
            self.assertEqual(t.count(h), 1)
        self.assertIn("CANARY_LEN=%d" % pkg["payload_bytes"], t)
        for old in (D.OLD_SHA, D.OLD_PAYLOAD_SHA, "artifacts/nat-092/package-001", "nat092-%s-single-run", "artifacts/nat-092/native-attempt", D.IMAGE_OLD):
            self.assertNotIn(old, t)
        self.assertIn("artifacts/nat-083/system-padded.apfs", t)                           # the big root is deliberately NAT-083's
        self.assertIn("'NAT-083','NAT-084','NAT-085','NAT-087','NAT-089','NAT-090','NAT-092','NAT-096','NAT-097')", t)
        self.assertIn("nat096-%s-single-run", t)
        self.assertIn("artifacts/nat-096/native-attempt-%s-used.json", t)
        self.assertIn("analyze_nat087.py (chain rows) and analyze_nat097.py (Stage A rows over NAT-097's reader", t)
        self.assertNotIn("analyze_nat089.py", t.split('"""')[1].split("(run separately)")[0].split("analyses are")[1])

    def test_a_drifted_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session_nat092.py"
            p.write_bytes(D.SRC.read_bytes() + b"# drift\n")
            with mock.patch.object(D, "SRC", p):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("not the file this derivation was written for", str(cm.exception))

    def test_a_missing_substitution_target_is_refused_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.py"
            p.write_text(D.SRC.read_text().replace("'NAT-090','NAT-092')", "'NAT-090')"))
            with mock.patch.object(D, "SRC", p), mock.patch.object(D, "SRC_SHA256", hashlib.sha256(p.read_bytes()).hexdigest()):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("required tasks: expected 1 occurrence(s)", str(cm.exception))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_a_payload_of_another_length_is_refused(self):
        pkg = json.loads(PKG.read_text())
        pkg["images"][D.IMAGE_NEW]["payload_bytes"] += 8
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text(json.dumps(pkg))
            with mock.patch.object(D, "PACKAGE", Path(d)):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("CANARY_LEN", str(cm.exception))

    def test_the_source_is_nat092s_driver_and_its_old_values_are_nat092s(self):
        self.assertEqual(D.SRC, ROOT / "docs/procedures/nat-092/session_nat092.py")
        self.assertEqual(hashlib.sha256(D.SRC.read_bytes()).hexdigest(), D.SRC_SHA256)
        t = D.SRC.read_text()
        self.assertEqual((t.count(D.OLD_SHA), t.count(D.OLD_PAYLOAD_SHA), t.count(D.IMAGE_OLD)), (1, 1, 1))


class DeriveCommand(unittest.TestCase):
    NAME = "session_nat096.py"

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = D.main(argv)
        return rc, out.getvalue(), err.getvalue()

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_check_says_ok_with_the_substitution_count_and_prints_nothing_else(self):
        self.assertEqual(self.call(["--check"]), (0, "ok: session_nat096.py equals the derivation (9 substitutions)\n", ""))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_check_names_the_difference_on_stderr_and_never_writes(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / self.NAME
            other.write_text("x")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat096.py differs from the derivation\n"))
            self.assertEqual(other.read_text(), "x")
            with mock.patch.object(D, "OUT", Path(d) / "missing.py"):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat096.py differs from the derivation\n"))
            self.assertFalse((Path(d) / "missing.py").exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_without_check_it_writes_the_driver_and_reports_its_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)
            (fake / "docs/procedures/nat-096").mkdir(parents=True)
            target = fake / "docs/procedures/nat-096" / self.NAME
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
            self.assertEqual((rc, err), (0, ""))
            text, done = D.build()
            self.assertEqual(target.read_text(), text)
            self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")
            rep = json.loads(out)
            self.assertEqual(rep["out"], "docs/procedures/nat-096/session_nat096.py")
            self.assertEqual(rep["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(len(rep["substitutions"]), 9)
            self.assertTrue(all(s["count"] == 1 for s in rep["substitutions"]))

    def test_a_drifted_source_is_refused_with_status_2_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            drifted = Path(d) / "session_nat092.py"
            drifted.write_text(D.SRC.read_text() + "\n# drift\n")
            target = Path(d) / self.NAME
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
                rc2, out2, err2 = self.call(["--check"])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: session_nat092.py is not the file this derivation was written for"), err)
            self.assertEqual((rc2, out2), (2, ""))
            self.assertFalse(target.exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-096/package-001 not present")
    def test_run_as_a_script_the_flag_reaches_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive96.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ok: session_nat096.py equals the derivation (9 substitutions)\n", ""))

    def test_the_output_path_is_the_committed_driver(self):
        self.assertEqual(D.OUT, HERE / "session_nat096.py")


if __name__ == "__main__":
    unittest.main()
