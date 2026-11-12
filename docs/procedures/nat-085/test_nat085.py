#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-085 host tests: the ephemeral-storage ADT, the build wrapper, the derived session driver, the job plist and the launchd-stage analyser. Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-085/test_nat085.py      (opens no device)

What the tests stand on (so that they do not merely mirror the code under test):

  * the ADT test parses the pinned e1s.adt and the derived one with the project's own adt.py and compares every node and property, not only the added one;
  * the launchd console text of the stage reader is the REAL one of NAT-084 (docs/procedures/nat-084/launchd-console.txt, 7.9 KB printed by Apple's launchd on the S24) and the
    process-list format is the real `ps -A` block of that run; the keybagd lines are checked against the strings of Apple's keybagd in the local IPSW unpack when it is present;
  * the whole analyze() path is run over the REAL archive of NAT-084 (it contains the NAT-084 kernel text, i.e. the run WITHOUT the ephemeral-storage property): the stage ladder
    must give S5 there (keybagd did not skip), the control that shows the analyser can tell the two cases apart;
  * the built payload (when artifacts/nat-085 is present) is parsed: its ADT must equal NAT-083's ADT plus the one property.
What stays hand-written: the console text of a launchd that skips keybag (nothing has produced it yet) and the stage-ladder cases. Nothing here measures the phone."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import plistlib
import struct
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


M = load("nat085_test_make_adt", HERE / "make_adt85.py")
A = load("nat085_test_analyze", HERE / "analyze_nat085.py")
D = load("nat085_test_derive", HERE / "derive85.py")
T83 = load("nat085_test_t83", ROOT / "docs/procedures/nat-083/test_analyze83.py")
ADT = M._adt()
B3 = ROOT / "artifacts/nat-020/build-003"
PINNED_ADT = B3 / "e1s.adt"
REAL_LAUNCHD = (ROOT / "docs/procedures/nat-084/launchd-console.txt").read_text()
KEYBAGD = ROOT / "artifacts/nat-083/recipe/sysimage/rootfs/usr/libexec/keybagd"
NAT84 = ROOT / "artifacts/nat-083/run-001"
ROOT_IMAGE = ROOT / "artifacts/nat-083/system-padded.apfs"
SIZE = T83.SIZE
PS_BLOCK = "  PID TTY           TIME CMD\n    1 ??         0:00.11 /redwood/sbin/init\n    6 ??         0:00.01 /bin/ps -A\n"      # the rc's ps -A of the NAT-084 run, verbatim
HAVE_ADT = PINNED_ADT.is_file() and M.ADT_PY.is_file()


def tree(node, path=""):
    """-> {path: [(prop name, flags, value)...]} for the node and its children (names repeated by /name#n)."""
    out = {}
    seen = {}
    p = path + "/" + node.name
    out[p] = [tuple(x) for x in node.props]
    for c in node.children:
        n = seen.get(c.name, 0)
        seen[c.name] = n + 1
        out.update(tree(c, p if n == 0 else p))
    return out


@unittest.skipUnless(HAVE_ADT, "artifacts/nat-020/build-003 not present")
class AdtDerivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = PINNED_ADT.read_bytes()
        cls.out, cls.rec = M.derive(cls.blob, ADT)

    def test_the_pinned_input_has_the_pinned_hash(self):
        self.assertEqual(hashlib.sha256(self.blob).hexdigest(), M.PIN_ADT)

    def test_exactly_one_property_is_added_to_chosen_and_nothing_else_changes(self):
        a, _ = ADT.parse(self.blob)
        b, end = ADT.parse(self.out)
        self.assertEqual(end, len(self.out))
        ta, tb = tree(a), tree(b)
        self.assertEqual(sorted(ta), sorted(tb))                                           # the same nodes
        changed = [p for p in ta if ta[p] != tb[p]]
        self.assertEqual(len(changed), 1, changed)
        added = [x for x in tb[changed[0]] if x not in ta[changed[0]]]
        self.assertEqual(added, [(M.PROP, 0, struct.pack("<I", 1))])
        self.assertEqual([x for x in tb[changed[0]] if x != added[0]], ta[changed[0]])    # the others, in their order
        self.assertTrue(changed[0].endswith("/chosen"), changed)

    def test_the_value_is_a_little_endian_u32_one_and_the_property_is_four_bytes(self):
        root, _ = ADT.parse(self.out)
        chosen = [c for c in root.children if c.name == "chosen"][0]
        self.assertEqual(chosen.prop("ephemeral-storage"), b"\x01\x00\x00\x00")

    def test_the_serialised_size_grows_by_the_property_and_stays_four_byte_aligned(self):
        self.assertEqual(len(self.out) - len(self.blob), self.rec["added"]["bytes_added"])
        self.assertEqual(self.rec["added"]["bytes_added"], 32 + 4 + 4)                      # name[32] + length word + 4 value bytes (no padding needed)
        self.assertEqual(len(self.out) % 4, 0)

    def test_the_record_names_both_hashes(self):
        self.assertEqual(self.rec["input_sha256"], M.PIN_ADT)
        self.assertEqual(self.rec["output_sha256"], hashlib.sha256(self.out).hexdigest())

    def test_the_input_is_left_alone(self):
        self.assertEqual(PINNED_ADT.read_bytes(), self.blob)

    def other_adt(self):
        """A valid, round-tripping ADT that is not the pinned one: the pinned tree with one property value changed."""
        root, _ = ADT.parse(self.blob)
        for node in [root] + list(root.children):
            for i, (name, flags, value) in enumerate(node.props):
                if len(value) >= 1 and name != "name":
                    node.props[i] = (name, flags, bytes([value[0] ^ 1]) + value[1:])
                    out = ADT.serialize(root)
                    self.assertNotEqual(out, self.blob)
                    return out
        self.fail("no property to change")

    def test_an_adt_that_is_not_the_pinned_one_is_refused_by_the_pin_alone(self):
        other = self.other_adt()
        with self.assertRaisesRegex(ValueError, r"^the input is not the pinned e1s\.adt \(sha256 %s\)$" % hashlib.sha256(other).hexdigest()):
            M.derive(other, ADT)
        out, rec = M.derive(other, ADT, check_pin=False)                                    # without the pin it is a perfectly good input: the refusal above is the pin's
        self.assertEqual(rec["input_sha256"], hashlib.sha256(other).hexdigest())
        self.assertEqual(len(out) - len(other), 40)

    def test_an_adt_that_already_has_the_property_is_refused(self):
        with self.assertRaisesRegex(ValueError, r"^/chosen already has ephemeral-storage$"):
            M.derive(self.out, ADT, check_pin=False)

    def test_a_lossy_parse_is_refused(self):
        with mock.patch.object(ADT, "serialize", lambda root: b"x"):
            with self.assertRaisesRegex(ValueError, "^re-serialising the input does not reproduce it; refusing to derive from a lossy parse$"):
                M.derive(self.blob, ADT)

    def test_trailing_bytes_are_refused_before_anything_else(self):
        with self.assertRaisesRegex(ValueError, r"^trailing bytes after the ADT root \(%d of %d parsed\)$" % (len(self.blob), len(self.blob) + 4)):
            M.derive(self.blob + b"\0" * 4, ADT, check_pin=False)

    def chosen_variants(self, n):
        """derive() on an ADT whose root has `n` nodes called chosen (the parse is patched; serialize returns the input so the round trip holds)."""
        real_parse = ADT.parse

        def parse(blob, off=0):                                                              # adt.parse recurses through the module attribute: only the root call (off 0) is changed
            root, end = real_parse(blob, off)
            if off == 0:
                kids = [c for c in root.children if c.name != "chosen"]
                ch = [c for c in root.children if c.name == "chosen"][0]
                root.children[:] = kids + [ch] * n
            return root, end
        with mock.patch.object(ADT, "parse", parse), mock.patch.object(ADT, "serialize", lambda root: self.blob):
            return M.derive(self.blob, ADT)

    def test_zero_or_two_chosen_nodes_are_refused_with_their_count(self):
        for n in (0, 2):
            with self.assertRaisesRegex(ValueError, r"^expected exactly one /chosen node, found %d$" % n):
                self.chosen_variants(n)
        out, rec = self.chosen_variants(1)                                                  # one is accepted: the refusals above are the count's
        self.assertEqual(rec["added"]["property"], "ephemeral-storage")

    def test_a_refusal_in_main_is_a_status_2_message_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "e1s-eph.adt"
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(M, "derive", side_effect=ValueError("boom 5")), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = M.main(["--out", str(o)])
            self.assertEqual((rc, out.getvalue(), err.getvalue()), (2, "", "refused: boom 5\n"))
            self.assertFalse(o.exists())

    def test_the_command_line_prints_the_record_with_indent_1(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(M.main(["--out", str(Path(d) / "x.adt")]), 0)
            self.assertEqual(buf.getvalue(), json.dumps(self.rec, indent=1) + "\n")

    def test_run_as_a_script_the_arguments_reach_main(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "script.adt"
            r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "make_adt85.py"), "--out", str(o)], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            self.assertEqual(o.read_bytes(), self.out)
            self.assertEqual(json.loads(r.stdout)["output_sha256"], self.rec["output_sha256"])
            r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "make_adt85.py"), "--out", str(o)], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "", "refused: %s exists\n" % o))

    def test_the_command_line_writes_the_file_and_refuses_to_overwrite_it(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "e1s-eph.adt"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(M.main(["--out", str(o)]), 0)
            self.assertEqual(o.read_bytes(), self.out)
            self.assertEqual(json.loads(buf.getvalue())["output_sha256"], self.rec["output_sha256"])
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(M.main(["--out", str(o)]), 2)
            self.assertIn("exists", err.getvalue())


class SessionDriver(unittest.TestCase):
    @unittest.skipUnless((ROOT / "artifacts/nat-085/package-001/package.json").is_file(), "artifacts/nat-085/package-001 not present")
    def test_the_committed_driver_equals_its_derivation(self):
        text, done = D.build()
        self.assertEqual((HERE / "session_nat085.py").read_text(), text)
        self.assertEqual(len(done), 10)
        self.assertTrue(all(n == 1 for _, n in done))

    @unittest.skipUnless((ROOT / "artifacts/nat-085/package-001/package.json").is_file(), "artifacts/nat-085/package-001 not present")
    def test_the_driver_names_this_images_hashes_and_not_nat083s(self):
        pkg = json.loads((D.PACKAGE / "package.json").read_text())["images"][D.IMAGE_NEW]
        t = (HERE / "session_nat085.py").read_text()
        for h in (pkg["recovery_sha256"], pkg["payload_sha256"]):
            self.assertEqual(t.count(h), 1)
        self.assertIn("CANARY_LEN=%d" % pkg["payload_bytes"], t)
        for old in (D.NEW_SHA_OLD, D.CANARY_OLD, "artifacts/nat-083/package-002", "nat083-%s-single-run", "artifacts/nat-083/native-attempt"):
            self.assertNotIn(old, t)
        self.assertIn("artifacts/nat-083/system-padded.apfs", t)                           # the big root is deliberately NAT-083's
        self.assertIn("'NAT-083','NAT-084','NAT-085'", t)

    def test_a_drifted_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session_nat083.py"
            p.write_bytes(D.SRC.read_bytes() + b"# drift\n")
            with mock.patch.object(D, "SRC", p):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("not the file this derivation was written for", str(cm.exception))

    def test_a_missing_substitution_target_is_refused_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.py"
            p.write_text(D.SRC.read_text().replace("'NAT-080','NAT-070')", "'NAT-080')"))
            with mock.patch.object(D, "SRC", p), mock.patch.object(D, "SRC_SHA256", hashlib.sha256(p.read_bytes()).hexdigest()):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("required tasks: expected 1 occurrence(s)", str(cm.exception))


class DeriveCommand(unittest.TestCase):
    """The command line of derive85.py: what it prints, writes and returns."""
    NAME = "session_nat085.py"

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = D.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_check_says_ok_with_the_substitution_count_and_prints_nothing_else(self):
        self.assertEqual(self.call(["--check"]), (0, "ok: session_nat085.py equals the derivation (10 substitutions)\n", ""))

    def test_check_names_the_difference_on_stderr_and_never_writes(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / self.NAME
            other.write_text("x")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat085.py differs from the derivation\n"))
            self.assertEqual(other.read_text(), "x")
            with mock.patch.object(D, "OUT", Path(d) / "missing.py"):                      # a missing driver is a difference too
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat085.py differs from the derivation\n"))
            self.assertFalse((Path(d) / "missing.py").exists())

    def test_without_check_it_writes_the_driver_and_reports_its_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)
            (fake / "docs/procedures/nat-085").mkdir(parents=True)
            target = fake / "docs/procedures/nat-085" / self.NAME
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
            self.assertEqual((rc, err), (0, ""))
            text, done = D.build()
            self.assertEqual(target.read_text(), text)
            self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")            # indent 1, trailing newline
            rep = json.loads(out)
            self.assertEqual(rep["out"], "docs/procedures/nat-085/session_nat085.py")
            self.assertEqual(rep["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(len(rep["substitutions"]), 10)
            self.assertTrue(all(s["count"] == 1 for s in rep["substitutions"]))

    def test_a_drifted_source_is_refused_with_status_2_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            drifted = Path(d) / "session_nat083.py"
            drifted.write_text(D.SRC.read_text() + "\n# drift\n")
            target = Path(d) / self.NAME
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
                rc2, out2, err2 = self.call(["--check"])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: session_nat083.py is not the file this derivation was written for"), err)
            self.assertEqual((rc2, out2), (2, ""))
            self.assertFalse(target.exists())

    def test_run_as_a_script_the_flag_reaches_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive85.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ok: session_nat085.py equals the derivation (10 substitutions)\n", ""))

    def test_the_output_path_is_the_committed_driver(self):
        self.assertEqual(D.OUT, HERE / "session_nat085.py")


class Plist(unittest.TestCase):
    P = HERE / "com.nat085.ps.plist"

    def test_the_job_is_ps_to_the_console_and_comes_back(self):
        d = plistlib.loads(self.P.read_bytes())
        self.assertEqual(d["Label"], "com.nat085.ps")
        self.assertEqual(d["ProgramArguments"], ["/bin/ps", "-A"])
        self.assertIs(d["RunAtLoad"], True)
        self.assertIs(d["KeepAlive"], True)
        self.assertEqual(d["ThrottleInterval"], 10)
        self.assertEqual((d["StandardOutPath"], d["StandardErrorPath"]), ("/dev/console", "/dev/console"))
        self.assertEqual(set(d), {"Label", "ProgramArguments", "RunAtLoad", "KeepAlive", "ThrottleInterval", "StandardOutPath", "StandardErrorPath"})

    def test_the_label_is_the_one_the_analyser_looks_for(self):
        self.assertIn("nat085", self.P.read_text())

    @unittest.skipUnless((HERE / "build-report-pid1.json").is_file(), "build report not present")
    def test_the_small_root_was_built_with_exactly_this_file_and_read_back_by_the_kernels_apfs_lib(self):
        rep = json.loads((HERE / "build-report-pid1.json").read_text())
        self.assertEqual(rep["own_jobs"], [{"file": "com.nat085.ps.plist", "bytes": self.P.stat().st_size, "sha256": hashlib.sha256(self.P.read_bytes()).hexdigest()}])
        self.assertTrue(rep["kernel_apfs_lib_readback"]["ok"])
        self.assertEqual(rep["kernel_apfs_lib_readback"]["files_compared"], 7)
        self.assertEqual(rep["rc"], "rc.nat083")

    @unittest.skipUnless((HERE / "build-report-pid1.json").is_file() and (ROOT / "docs/procedures/nat-083/build-report-pid1-b.json").is_file(), "reports not present")
    def test_the_three_programs_are_byte_identical_to_nat083s(self):
        a = json.loads((ROOT / "docs/procedures/nat-083/build-report-pid1-b.json").read_text())["programs"]
        b = json.loads((HERE / "build-report-pid1.json").read_text())["programs"]
        self.assertEqual({k: v["sha256"] for k, v in a.items()}, {k: v["sha256"] for k, v in b.items()})


class BuildWrapper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.B = load("nat085_test_build", HERE / "build.py")

    def test_names_have_the_lengths_of_nat083s(self):
        b83 = self.B.b83
        self.assertEqual((len(self.B.NAME), len(self.B.NEW_TAG)), (len(b83.NAME), len(b83.NEW_TAG)))
        self.assertNotEqual((self.B.NAME, self.B.NEW_TAG), (b83.NAME, b83.NEW_TAG))

    def test_only_the_pinned_adt_path_is_swapped_and_it_is_counted(self):
        pinned = self.B.b65.B3 / "e1s.adt"
        argv = ["python", Path("/x/mkpayload74.py"), self.B.b65.B3 / "kernel.no-storage", pinned, Path("/o/payload.bin"), "--cmdline", "rd=md1"]
        new, n = self.B.swap_adt(argv, Path("/d/e1s-eph.adt"))
        self.assertEqual(n, 1)
        self.assertEqual(new[3], Path("/d/e1s-eph.adt"))
        self.assertEqual([x for i, x in enumerate(new) if i != 3], [x for i, x in enumerate(argv) if i != 3])

    def test_a_string_with_the_same_text_or_another_adt_is_not_swapped(self):
        pinned = self.B.b65.B3 / "e1s.adt"
        new, n = self.B.swap_adt([str(pinned), self.B.b65.B3 / "other.adt", "e1s.adt"], Path("/d/x"))
        self.assertEqual(n, 0)
        self.assertEqual(new, [str(pinned), self.B.b65.B3 / "other.adt", "e1s.adt"])


BUILD = ROOT / "artifacts/nat-085/build-001/loader-diag-xnu-ep-md1/Image.payload"
BUILD83 = ROOT / "artifacts/nat-083/build-002/loader-diag-xnu-rt-md1/Image.payload"
CMDLINE_OFF, CMDLINE_LEN = 0x48, 608                    # the SWEETXNU header's command line field (NAT-065's build.py)
LOADER_BYTES = 385024                                   # the loader Image in front of the XNU payload (build.json: images.*.bytes)


@unittest.skipUnless(BUILD.is_file() and BUILD83.is_file() and HAVE_ADT, "built payloads not present")
class BuiltPayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p85 = BUILD.read_bytes()[LOADER_BYTES:]
        cls.p83 = BUILD83.read_bytes()[LOADER_BYTES:]

    @staticmethod
    def adt_of(p):
        off, size = struct.unpack_from("<QQ", p, 32)
        root, end = ADT.parse(p[off:off + size])
        return root, off, size, end

    def test_both_payloads_are_sweetxnu_images(self):
        self.assertEqual((self.p85[:8], self.p83[:8]), (b"SWEETXNU", b"SWEETXNU"))

    def test_the_payload_adt_is_nat083s_adt_plus_the_one_property(self):
        r85, o85, s85, e85 = self.adt_of(self.p85)
        r83, o83, s83, e83 = self.adt_of(self.p83)
        t85, t83 = tree(r85), tree(r83)
        self.assertEqual(sorted(t85), sorted(t83))
        changed = [p for p in t85 if t85[p] != t83[p]]
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual([x for x in t85[changed[0]] if x not in t83[changed[0]]], [("ephemeral-storage", 0, b"\x01\x00\x00\x00")])
        self.assertEqual([x for x in t83[changed[0]] if x not in t85[changed[0]]], [])
        self.assertEqual(o85, o83)                                                        # the ADT starts where it did
        self.assertEqual(s85 - s83, 40)
        self.assertEqual((s85 & 7, o85 & 7), (0, 0))                                     # the loader refuses an adt_size that is not a multiple of 8

    def test_everything_before_the_ramdisk_and_the_adt_is_the_same_except_header_and_command_line_tag(self):
        off = struct.unpack_from("<Q", self.p85, 32)[0]
        diff = [i for i in range(off) if self.p85[i] != self.p83[i]]
        diff_head = [i for i in diff if i < 0x300]
        self.assertTrue(set(diff_head) <= {40, 41} | set(range(CMDLINE_OFF, CMDLINE_OFF + CMDLINE_LEN)), diff_head)       # adt_size, and the command line field
        cmd85 = self.p85[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()
        cmd83 = self.p83[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()
        self.assertEqual(cmd85.replace("NAT085-ep1", "NAT083-rt1"), cmd83)
        # the rest of the difference lies in one contiguous region: the md0 ramdisk (the small root), 4 MiB at most
        rest = [i for i in diff if i >= 0x300]
        self.assertLess(rest[-1] - rest[0], 4 << 20)
        small = (ROOT / "artifacts/nat-085/pid1/root.apfs").read_bytes()
        at = self.p85.find(small[:4096])
        self.assertGreater(at, 0)
        self.assertEqual(self.p85[at:at + len(small)], small)                              # the md0 image in the payload is NAT-085's small root
        self.assertTrue(at <= rest[0] and rest[-1] < at + len(small), (at, rest[0], rest[-1]))

    def test_the_command_line_keeps_the_nat083_settings(self):
        cmd = self.p85[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()
        for tok in ("rd=md1", "nat_attempt=NAT085-ep1", "loader_return_after=60", "launchdsuffix=release", "cs_enforcement_disable=1", "e1stouch=0", "e1sbattery=0"):
            self.assertIn(tok, cmd.split())
        self.assertLessEqual(len(cmd), 255)


# ---------------------------------------------------------------------------------------------------------------- the stage reader and ladder
SKIP_TEXT = ("com.apple.xpc.launchd|1970-01-01 00:03:23.197788 (keybag) <Notice>: Doing boot task\n"
             "****** DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT ****\n")


def skip_variant(tail=""):
    """The real NAT-084 launchd text with its keybag block (from the `keybag` task line to the end) replaced by the skip line, then `tail`. HAND-WRITTEN: no run has printed this."""
    i = REAL_LAUNCHD.index("com.apple.xpc.launchd|1970-01-01 00:03:23.197788 (keybag)")
    return REAL_LAUNCHD[:i] + SKIP_TEXT + tail


def task_line(name, t="00:03:23.300000"):
    return "com.apple.xpc.launchd|1970-01-01 %s (%s) <Notice>: Doing boot task\n" % (t, name)


def whole(launchd_text, **kw):
    """A complete returned text of the NAT-083 chain (rows 1-4 as in the real run) with `launchd_text` as the output of the last exec."""
    cmds = list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", launchd_text, None)]
    return T83.text(cmds, **kw)


def stage(t, chain="PASS"):
    kern = A.A83.read_userland(t)
    d = A.A83.decide(chain, T83.DELIVERED, T83.loader(), SIZE, kern)
    return A.decide_stage(d, A.read_stage(A.after_exec_text(t)), kern), d


class Reader(unittest.TestCase):
    def test_the_real_nat084_text_is_read_task_by_task(self):
        st = A.read_stage(REAL_LAUNCHD)
        self.assertEqual(st["tasks"], ["fsck", "mount-phase-1", "data-protection", "finish-obliteration", "detect-installed-roots", "commit-boot-mode", "restore-datapartition",
                                       "mount-phase-2", "init-with-data-volume", "MSUEarlyBootTask", "fips", "keybag"])
        self.assertTrue(st["keybag_reached"])
        self.assertEqual(st["tasks_after_keybag"], [])
        self.assertTrue(st["fips_all_passed"])
        self.assertEqual(st["libignition_failed"], "libignition: 1: ignition boot failed: 25")
        self.assertTrue(st["mkb_init"] and st["keybag_fatal"] and st["reboot_request"])
        self.assertFalse(st["keybag_skip"])
        self.assertEqual(st["job_runs"], 0)
        self.assertEqual(st["last_task"], "keybag")
        self.assertEqual(st["bytes"], len(REAL_LAUNCHD))

    def test_the_real_nat084_notable_lines_after_keybag_are_the_failure_lines(self):
        st = A.read_stage(REAL_LAUNCHD)
        self.assertIn("MKB_INIT: Rebooting...", st["notable_after_keybag"])
        self.assertIn("REBOOTING INTO RECOVERY MODE.", st["notable_after_keybag"])
        self.assertEqual(st["notable_total"], len(st["notable_after_keybag"]))

    def test_notable_lines_are_bounded_and_counted(self):
        t = skip_variant("".join("com.apple.xpc.launchd|x <Error>: failed thing %d\n" % i for i in range(60)))
        st = A.read_stage(t)
        self.assertEqual((len(st["notable_after_keybag"]), st["notable_total"]), (A.NOTABLE_KEEP, 60))
        self.assertTrue(all(len(x) <= A.LINE_KEEP for x in st["notable_after_keybag"]))

    def test_the_ps_format_of_the_real_nat084_block_is_read_as_a_heartbeat(self):
        st = A.read_stage(skip_variant(PS_BLOCK))
        self.assertEqual((st["job_runs"], st["last_heartbeat"]), (1, ["/redwood/sbin/init", "/bin/ps -A"]))

    def test_each_header_is_one_run_and_the_last_list_is_kept(self):
        two = PS_BLOCK + "com.apple.xpc.launchd|x <Notice>: spawn\n" + "  PID TTY           TIME CMD\n    1 ??         0:00.30 /sbin/launchd.darwin\n   27 ??         0:00.01 /bin/ps -A\n"
        st = A.read_stage(skip_variant(two))
        self.assertEqual(st["job_runs"], 2)
        self.assertEqual(st["last_heartbeat"], ["/sbin/launchd.darwin", "/bin/ps -A"])

    def test_a_header_inside_other_text_is_not_a_run(self):
        st = A.read_stage(skip_variant("the PID TTY TIME CMD columns\n"))
        self.assertEqual(st["job_runs"], 0)

    def test_the_text_after_the_last_exec_echo_is_what_is_read(self):
        t = whole(REAL_LAUNCHD)
        self.assertEqual(A.after_exec_text(t).strip("\n"), REAL_LAUNCHD.strip("\n"))
        self.assertIsNone(A.after_exec_text(T83.text(list(T83.GOOD[:-1]))))
        self.assertIsNone(A.after_exec_text(""))
        self.assertIsNone(A.after_exec_text(None))

    def test_kernel_buffer_text_is_not_launchd_output(self):
        t = whole("", k="[   1.0]: com.apple.xpc.launchd|x (keybag) <Notice>: Doing boot task\n")
        self.assertEqual(A.read_stage(A.after_exec_text(t))["tasks"], [])

    def test_carriage_returns_do_not_break_the_reading(self):
        st = A.read_stage(skip_variant(PS_BLOCK).replace("\n", "\r\n"))
        self.assertEqual((st["job_runs"], st["keybag_skip"]), (1, True))

    @unittest.skipUnless(KEYBAGD.is_file(), "Apple's keybagd is not unpacked here")
    def test_the_keybagd_lines_the_ladder_looks_for_are_strings_of_apples_keybagd(self):
        data = KEYBAGD.read_bytes()
        for s in (A.SKIP_LINE, A.MKB_LINE, "FATAL KEYBAG ERROR", "REBOOTING INTO RECOVERY MODE"):
            self.assertIn(s.encode(), data, s)


class Ladder(unittest.TestCase):
    def check(self, t, row, chain="PASS"):
        s, d = stage(t, chain)
        self.assertEqual(s["row"], row, (s["name"], s["reasons"]))
        self.assertEqual(s["name"], A.STAGE_ROWS[row])
        self.assertEqual(s["pass"], row == 1)
        return s

    def test_s5_the_real_nat084_text_keybagd_did_not_skip(self):
        s = self.check(whole(REAL_LAUNCHD), 5)
        self.assertEqual(s["facts"]["chain_row"], 1)
        self.assertEqual(s["facts"]["tasks_after_keybag"], [])

    def test_s1_skip_and_two_process_lists(self):
        t = whole(skip_variant(task_line("some-later-task") + PS_BLOCK + "launchd noise\n" + PS_BLOCK))
        s = self.check(t, 1)
        self.assertEqual(s["facts"]["job_runs"], 2)
        self.assertEqual(s["facts"]["tasks_after_keybag"], ["some-later-task"])

    def test_s2_skip_and_one_process_list(self):
        self.check(whole(skip_variant(PS_BLOCK)), 2)

    def test_s3_skip_and_no_process_list(self):
        self.check(whole(skip_variant(task_line("some-later-task"))), 3)

    def test_s4_skip_and_a_reboot_request(self):
        self.check(whole(skip_variant(PS_BLOCK + "REBOOTING INTO RECOVERY MODE.\n")), 4)

    def test_s4_skip_and_a_pid1_exit_or_a_panic(self):
        k = T83.kernel(exit_line=T83.EXIT_PANIC)
        s = self.check(T83.text(list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", skip_variant(PS_BLOCK + PS_BLOCK), None)], k=k), 4)
        self.assertEqual(s["facts"]["pid1_exit"]["signal"], 11)
        s = self.check(T83.text(list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", skip_variant(PS_BLOCK), None)], k=T83.kernel(panic="bad thing")), 4)
        self.assertEqual(s["facts"]["panic"], "bad thing")

    def test_s5_an_mkb_init_line_wins_over_a_skip_line(self):
        self.check(whole(skip_variant("****** IN MKB_INIT ****\n" + PS_BLOCK + PS_BLOCK)), 5)

    def test_s5_keybag_task_with_no_skip_line_and_no_gap(self):
        self.check(whole(skip_variant("").replace(SKIP_TEXT.split("\n")[1] + "\n", "") + PS_BLOCK + PS_BLOCK), 5)

    def test_s6_launchd_never_started_keybag(self):
        i = REAL_LAUNCHD.index("com.apple.xpc.launchd|1970-01-01 00:03:23.197788 (keybag)")
        self.check(whole(REAL_LAUNCHD[:i]), 6)

    def test_s7_exec_reached_launchd_printed_nothing(self):
        s = self.check(whole("some stray text\n"), 7)
        self.assertEqual(s["facts"]["launchd_lines"], 0)

    def test_s9_the_chain_row_is_not_1(self):
        s = self.check(whole(skip_variant(PS_BLOCK + PS_BLOCK)), 9, chain="PARTIAL")
        self.assertEqual(s["facts"]["chain_row"], 9)
        s = self.check(T83.text(list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", "", None)], k=T83.kernel(root="md0")), 9)
        self.assertEqual(s["facts"]["chain_row"], 6)

    def test_s9_no_exec_line_at_all_is_chain_row_2_so_not_evaluated(self):
        self.check(T83.text(list(T83.GOOD[:-1])), 9)

    def test_chain_row_1b_is_still_evaluated(self):
        s, d = stage(whole(skip_variant(PS_BLOCK), k=T83.kernel(exit_line=T83.EXIT_PANIC)))
        self.assertEqual((d["row"], d["variant"]), (1, "b"))
        self.assertEqual(s["row"], 4)


class Closers(unittest.TestCase):
    """Boundaries and degenerate inputs of the reader and the ladder (found by the first mutation pass)."""

    def test_the_bounds_are_exact(self):
        for n in (A.NOTABLE_KEEP, A.NOTABLE_KEEP + 1):
            t = skip_variant("".join("com.apple.xpc.launchd|x <Error>: failed thing %d\n" % i for i in range(n)))
            st = A.read_stage(t)
            self.assertEqual((len(st["notable_after_keybag"]), st["notable_total"]), (A.NOTABLE_KEEP, n))
        long_line = "com.apple.xpc.launchd|x failed " + "y" * 400 + "\n"
        st = A.read_stage(skip_variant(long_line))
        self.assertEqual(max(len(x) for x in st["notable_after_keybag"]), A.LINE_KEEP)
        rows = "".join("%5d ??         0:00.01 /bin/proc%d\n" % (i + 10, i) for i in range(A.PS_KEEP + 1))
        st = A.read_stage(skip_variant("  PID TTY           TIME CMD\n" + rows))
        self.assertEqual(len(st["last_heartbeat"]), A.PS_KEEP)
        self.assertEqual(st["last_heartbeat"][0], "/bin/proc0")
        self.assertEqual(st["last_heartbeat"][-1], "/bin/proc%d" % (A.PS_KEEP - 1))
        self.assertEqual((A.NOTABLE_KEEP, A.LINE_KEEP, A.PS_KEEP), (25, 200, 40))

    def test_the_label_lines_are_the_job_lines_and_ten_at_most(self):
        t = skip_variant("".join("com.apple.xpc.launchd|x (com.nat085.ps) <Notice>: spawn %d\n" % i for i in range(11)) + "an unrelated line\n")
        st = A.read_stage(t)
        self.assertEqual(len(st["job_label_lines"]), 10)
        self.assertTrue(all("nat085" in x for x in st["job_label_lines"]))
        self.assertTrue(st["job_label_lines"][0].endswith("spawn 0") and st["job_label_lines"][-1].endswith("spawn 9"))
        self.assertEqual(A.read_stage(skip_variant("nothing of the job here\n"))["job_label_lines"], [])

    def test_a_process_row_before_any_header_is_not_a_run_and_does_not_crash(self):
        st = A.read_stage(skip_variant("    1 ??         0:00.11 /orphan/row\n"))
        self.assertEqual((st["job_runs"], st["last_heartbeat"]), (0, []))

    def test_a_block_ends_at_the_first_line_that_is_not_a_row(self):
        st = A.read_stage(skip_variant(PS_BLOCK + "launchd chatter\n   99 ??         0:00.01 /stray/after/the/block\n"))
        self.assertEqual((st["job_runs"], st["last_heartbeat"]), (1, ["/redwood/sbin/init", "/bin/ps -A"]))
        st = A.read_stage(skip_variant(PS_BLOCK + "\n   99 ??         0:00.01 /stray/after/a/blank\n"))
        self.assertEqual(st["last_heartbeat"], ["/redwood/sbin/init", "/bin/ps -A"])

    def test_the_last_exec_echo_wins_and_the_kernel_part_is_never_read(self):
        first = "$ exec /sbin/launchd.darwin\nfirst launchd text\n"
        second = "$ exec /sbin/launchd.darwin\nsecond launchd text\n"
        self.assertEqual(A.after_exec_text(first + second), "\nsecond launchd text\n")
        k = A.A83.KMARK
        self.assertIsNone(A.after_exec_text(k + "\n$ exec /sbin/launchd.darwin\nonly in the kernel buffer\n"))        # the mark at offset 0 still cuts
        self.assertEqual(A.after_exec_text(first + k + "\n$ exec /sbin/x\nkernel text\n"), "\nfirst launchd text\n")
        self.assertIsNone(A.after_exec_text("$ ls\nno exec here\n"))

    def test_the_stage_without_an_exec_line_is_9_even_for_a_row_1_chain(self):
        # unreachable through analyze() (chain row 1 needs the exec line), so the function is called directly
        chain = dict(row=1, variant="a", name="pass-a")
        kern = dict(gaps=[], gap_bytes=0, pid1_exit=None, pid1_exit_printf=None, panic=None, exec_seen=False)
        s = A.decide_stage(chain, A.read_stage(None), kern)
        self.assertEqual((s["row"], s["pass"]), (9, False))
        self.assertEqual(s["reasons"], ["no `$ exec` line in the console text"])

    def test_the_reasons_name_their_numbers(self):
        s, _ = stage(whole("stray\n"))
        self.assertEqual(s["reasons"], ["%d bytes of console text after the exec line, none of them from launchd" % s["facts"]["bytes"]])
        self.assertLess(len(s["reasons"][0]), 120)                                          # a number, not the text repeated that many times
        s, _ = stage(whole(skip_variant(PS_BLOCK + "REBOOTING INTO RECOVERY MODE.\n")))
        self.assertTrue(s["reasons"][0].endswith("; launchd stopped: a reboot request line; job runs seen: 1"), s["reasons"])
        s, _ = stage(whole(skip_variant(PS_BLOCK + PS_BLOCK)))
        self.assertTrue(s["reasons"][0].endswith("; no PID 1 exit, panic or reboot request in the text; the job printed 2 process lists"), s["reasons"])


class Gaps(unittest.TestCase):
    GAP = "\n[... 5000 bytes of the log were not sent ...]\n"

    def with_gap(self, launchd_text):
        return whole(launchd_text + self.GAP)

    def test_missing_keybag_with_a_gap_is_not_established(self):
        i = REAL_LAUNCHD.index("com.apple.xpc.launchd|1970-01-01 00:03:23.197788 (keybag)")
        s, _ = stage(self.with_gap(REAL_LAUNCHD[:i]))
        self.assertEqual((s["row"], s["name"]), (8, "not-established"))

    def test_missing_launchd_lines_with_a_gap_is_not_established(self):
        s, _ = stage(self.with_gap("stray\n"))
        self.assertEqual(s["row"], 8)

    def test_missing_skip_line_with_a_gap_is_not_established_but_a_present_mkb_line_is_not_hidden_by_it(self):
        no_skip = skip_variant("").replace(SKIP_TEXT.split("\n")[1] + "\n", "") + PS_BLOCK + PS_BLOCK
        self.assertEqual(stage(self.with_gap(no_skip))[0]["row"], 8)
        self.assertEqual(stage(self.with_gap(REAL_LAUNCHD))[0]["row"], 5)

    def test_missing_process_list_with_a_gap_is_not_established_and_a_present_one_is_judged(self):
        self.assertEqual(stage(self.with_gap(skip_variant("")))[0]["row"], 8)
        self.assertEqual(stage(self.with_gap(skip_variant(PS_BLOCK)))[0]["row"], 2)
        self.assertEqual(stage(self.with_gap(skip_variant(PS_BLOCK + PS_BLOCK)))[0]["row"], 1)

    def test_a_stop_is_a_finding_even_with_a_gap(self):
        self.assertEqual(stage(self.with_gap(skip_variant("REBOOTING INTO RECOVERY MODE.\n")))[0]["row"], 4)


@unittest.skipUnless(NAT84.is_dir() and ROOT_IMAGE.is_file() and HAVE_ADT, "artifacts/nat-083/run-001 (the NAT-084 archive) not present")
class RealArchive(unittest.TestCase):
    """analyze() over the archive of NAT-084 under NAT-083's image name: the control run (no ephemeral-storage property) must read S5."""
    SHA = "4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6"
    NAME = "loader-diag-xnu-rt-md1"

    @classmethod
    def setUpClass(cls):
        events, _ = A.A65.A49.read_jsonl(str(NAT84 / "usb-events.jsonl"))
        report = A.A65.A49.read_json(str(NAT84 / "report.json")) or {}
        cls.image_before = A.A83.IMAGE
        cls.res = A.analyze(NAT84 / "archive", events, report, NAT84 / "delivery", ROOT_IMAGE, SIZE, cls.SHA, image=cls.NAME)
        cls.image_after = A.A83.IMAGE

    def test_the_chain_reads_row_1a_as_in_the_committed_nat084_analysis(self):
        n = self.res["nat085"]
        self.assertEqual((n["chain_row"], n["chain_pass"]), (1, True))
        self.assertEqual(self.res["nat083"]["decision"]["variant"], "a")

    def test_the_stage_ladder_reads_s5_and_the_facts_of_the_real_launchd_text(self):
        s = self.res["nat085"]["stage"]
        self.assertEqual((s["row"], s["name"], s["pass"]), (5, "keybag-not-skipped", False), s["reasons"])
        f = self.res["nat085"]["launchd"]
        self.assertEqual(len(f["tasks"]), 12)
        self.assertEqual((f["keybag_skip"], f["mkb_init"], f["job_runs"], f["fips_all_passed"]), (False, True, 0, True))

    def test_the_text_launchd_printed_in_the_archive_is_the_committed_one(self):
        launchd = self.res["nat085"]["launchd"]
        self.assertAlmostEqual(launchd["bytes"], len(REAL_LAUNCHD), delta=8)                # the same text, give or take the newlines around it
        self.assertEqual(launchd["tasks"], A.read_stage(REAL_LAUNCHD)["tasks"])

    def test_the_default_image_name_is_the_new_image_and_the_old_run_is_refused_under_it(self):
        events, _ = A.A65.A49.read_jsonl(str(NAT84 / "usb-events.jsonl"))
        report = A.A65.A49.read_json(str(NAT84 / "report.json")) or {}
        res = A.analyze(NAT84 / "archive", events, report, NAT84 / "delivery", ROOT_IMAGE, SIZE, self.SHA)
        self.assertEqual(res["nat085"]["chain_row"], 9)                                    # the NAT-084 text is not this image's own boot
        self.assertEqual(res["nat085"]["stage"]["row"], 9)

    def test_the_module_global_image_name_is_restored(self):
        # NAT-083's default name equals NAT-085's run name here, so the setUpClass pair proves nothing: use a sentinel the analysis cannot confuse with either
        events, _ = A.A65.A49.read_jsonl(str(NAT84 / "usb-events.jsonl"))
        report = A.A65.A49.read_json(str(NAT84 / "report.json")) or {}
        with mock.patch.object(A.A83, "IMAGE", "sentinel-image-name"):
            res = A.analyze(NAT84 / "archive", events, report, NAT84 / "delivery", ROOT_IMAGE, SIZE, self.SHA, image=self.NAME)
            self.assertEqual(A.A83.IMAGE, "sentinel-image-name")
        self.assertEqual(res["nat085"]["chain_row"], 1)                                    # it was judged under the run's image name while the call ran

    def test_the_wrong_root_file_is_refused(self):
        events, _ = A.A65.A49.read_jsonl(str(NAT84 / "usb-events.jsonl"))
        with mock.patch.object(A.A83, "IMAGE", "sentinel-image-name"):
            with self.assertRaises(ValueError):
                A.analyze(NAT84 / "archive", events, {}, NAT84 / "delivery", ROOT_IMAGE, SIZE, "0" * 64, image=self.NAME)
            self.assertEqual(A.A83.IMAGE, "sentinel-image-name")                              # restored on the error path too

    def run_main(self, extra=()):
        argv = ["--archive", str(NAT84 / "archive"), "--events", str(NAT84 / "usb-events.jsonl"), "--report", str(NAT84 / "report.json"), "--delivery", str(NAT84 / "delivery"),
                "--root", str(ROOT_IMAGE), "--size", str(SIZE), "--sha256", self.SHA, "--image", self.NAME] + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(A.A80, "host_prefix_digests", lambda p, sizes: {SIZE: self.SHA}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = A.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_main_prints_the_record_and_writes_out_and_log_once(self):
        with tempfile.TemporaryDirectory() as d:
            o, lg = Path(d) / "analysis.json", Path(d) / "kernel.log"
            rc, out, err = self.run_main(["--out", str(o), "--log-out", str(lg)])
            self.assertEqual((rc, err), (0, ""))
            self.assertEqual(o.read_text(), out)
            self.assertEqual(json.loads(out)["nat085"]["stage"]["row"], 5)
            self.assertGreater(lg.stat().st_size, 1000)
            rc, out2, err2 = self.run_main(["--out", str(o)])
            self.assertEqual((rc, out2), (2, ""))
            self.assertEqual(err2, "refused: %s already exists\n" % o)

    def test_main_without_out_options_only_prints_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(A, "write_log", side_effect=AssertionError("no log was asked for")):
            cwd = os.getcwd()
            os.chdir(d)
            try:
                rc, out, err = self.run_main()
                self.assertEqual(os.listdir(d), [])
            finally:
                os.chdir(cwd)
        self.assertEqual((rc, err), (0, ""))
        self.assertTrue(out.endswith("}\n"))
        self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")                  # indent 1, one trailing newline, nothing else on stdout

    def test_main_writes_the_log_without_out_and_out_without_the_log(self):
        with tempfile.TemporaryDirectory() as d:
            lg = Path(d) / "kernel.log"
            rc, out, err = self.run_main(["--log-out", str(lg)])
            self.assertEqual((rc, err), (0, ""))
            self.assertGreater(lg.stat().st_size, 1000)
            o = Path(d) / "only-out.json"
            with mock.patch.object(A, "write_log", side_effect=AssertionError("no log was asked for")):
                rc, out, err = self.run_main(["--out", str(o)])
            self.assertEqual((rc, err), (0, ""))
            self.assertEqual(o.read_text(), out)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["kernel.log", "only-out.json"])

    def test_main_refuses_a_root_file_that_is_not_the_judged_image(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "a.json"
            argv = ["--archive", str(NAT84 / "archive"), "--events", str(NAT84 / "usb-events.jsonl"), "--report", str(NAT84 / "report.json"), "--root", str(ROOT_IMAGE),
                    "--size", str(SIZE), "--sha256", "0" * 64, "--image", self.NAME, "--out", str(o)]
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = A.main(argv)
            self.assertEqual((rc, out.getvalue()), (2, ""))
            self.assertTrue(err.getvalue().startswith("refused: the root file is not the image"), err.getvalue())
            self.assertFalse(o.exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
