#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-087 host tests: the `xrd=md0` command-line token (XNU's real boot-arg parser compiled on the host), the build wrapper, the built payload, the derived session driver and the
launchd restore-mode analyser. Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-087/test_nat087.py      (opens no device)

What the tests stand on (so that they do not merely mirror the code under test):

  * the claim "the kernel still roots on rd=md1" is checked by compiling the REAL references/apple-xnu/pexpert/gen/bootargs.c (pinned SHA, only two shim headers for the types)
    and asking it for `rd` and `xrd` on the real NAT-087 command line; the control is the same program on a line whose last token is `rd=md0`;
  * the claim "launchd finds rd=md0 in the line" is checked on Apple's launchd binary of the local IPSW unpack when present: the string, the strstr import and the Boot dictionary
    (which tasks are PerformAlways / PerformInRestore) are read from the file, and the analyser's allowed-task list is compared with it;
  * the launchd console text of the reader is the REAL one of NAT-084 (keybagd fatal) and of NAT-086 (keybagd skipped, cache loader abort), both printed by Apple's launchd on the S24;
    both must read as "boot tasks not skipped" (the controls that show the analyser can tell restore mode from its absence); the whole analyze() path is run over both real archives;
  * the built payload is compared byte for byte with NAT-085's: the only differences are the tag, the token and the loader's name immediates.
What stays hand-written: the console text of a launchd in restore mode (nothing has produced it yet) and the ladder cases. Nothing here measures the phone."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import plistlib
import shutil
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


A = load("nat087_test_analyze", HERE / "analyze_nat087.py")
D = load("nat087_test_derive", HERE / "derive87.py")
T83 = load("nat087_test_t83", ROOT / "docs/procedures/nat-083/test_analyze83.py")
NAT84_LAUNCHD = (ROOT / "docs/procedures/nat-084/launchd-console.txt").read_text()
NAT86_LAUNCHD = (ROOT / "docs/procedures/nat-086/launchd-console.txt").read_text()
LAUNCHD_BIN = ROOT / "artifacts/nat-083/recipe/sysimage/rootfs/sbin/launchd"
BOOTARGS_C = ROOT / "references/apple-xnu/pexpert/gen/bootargs.c"
SYSCTL_C = ROOT / "references/apple-xnu/bsd/kern/kern_sysctl.c"
NAT84 = ROOT / "artifacts/nat-083/run-001"
NAT86 = ROOT / "artifacts/nat-085/run-001"
ROOT_IMAGE = ROOT / "artifacts/nat-083/system-padded.apfs"
SIZE = T83.SIZE
ROOT_SHA = "4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6"
PS_BLOCK = "  PID TTY           TIME CMD\n    1 ??         0:00.11 /redwood/sbin/init\n    6 ??         0:00.01 /bin/ps -A\n"      # the rc's ps -A of the NAT-084 run, verbatim
CMDLINE87 = ("rd=md1 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT087-rm1 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=60 "
             "launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 xrd=md0")                    # build.json nat087_changes.cmdline
CMDLINE86 = CMDLINE87.replace("NAT087-rm1", "NAT085-ep1").replace(" xrd=md0", "")


# ---------------------------------------------------------------------------------------------------------------- the real kernel parser
HARNESS = r'''
#include <stdio.h>
#include <string.h>
typedef int boolean_t;
boolean_t PE_parse_boot_arg_str(const char *arg_string, char *arg_ptr, int strlen);
static char line[512];
char *PE_boot_args(void) { return line; }
int IODTGetDefault(const char *key, void *infoAddr, unsigned int infoSize) { return -1; }
int SecureDTLookupEntry(void *a, const char *b, void **c) { return -1; }
int SecureDTGetProperty(void *e, const char *n, const void **d, unsigned *s) { return -1; }
int main(int argc, char **argv) {
    strncpy(line, argv[1], sizeof line - 1);
    char out[256] = "";
    boolean_t f = PE_parse_boot_arg_str(argv[2], out, sizeof out);
    printf("%d|%s\n", f, out);
    return 0;
}
'''
PEXPERT_H = '''#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef int boolean_t;
#define TRUE 1
#define FALSE 0
typedef int kern_return_t;
#define KERN_SUCCESS 0
char *PE_boot_args(void);
#define int64_t long long
'''
DEVICE_TREE_H = '''typedef void *DTEntry;
#define kSuccess 0
int SecureDTLookupEntry(void *a, const char *b, DTEntry *c);
int SecureDTGetProperty(DTEntry e, const char *n, const void **d, unsigned *s);
'''


@unittest.skipUnless(BOOTARGS_C.is_file() and shutil.which("cc"), "references/apple-xnu or a C compiler not present")
class KernelBootArgParser(unittest.TestCase):
    """XNU's own PE_parse_boot_arg_str on the command line of the image: `rd` keeps its value, `xrd` is a key of its own."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        (d / "pexpert").mkdir()
        (d / "pexpert/pexpert.h").write_text(PEXPERT_H)
        (d / "pexpert/device_tree.h").write_text(DEVICE_TREE_H)
        (d / "harness.c").write_text(HARNESS)
        cls.exe = d / "harness"
        r = subprocess.run(["cc", "-Wno-unused", "-I", str(d), "-o", str(cls.exe), str(BOOTARGS_C), str(d / "harness.c")], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("the shimmed bootargs.c did not compile:\n" + r.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def get(self, line, key):
        out = subprocess.run([str(self.exe), line, key], capture_output=True, text=True, check=True).stdout.strip()
        found, _, value = out.partition("|")
        return found == "1", value

    def test_the_kernel_still_roots_on_md1_with_the_token_in_the_line(self):
        self.assertEqual(self.get(CMDLINE87, "rd"), (True, "md1"))

    def test_the_token_is_a_key_of_its_own(self):
        self.assertEqual(self.get(CMDLINE87, "xrd"), (True, "md0"))

    def test_the_harness_can_tell_a_real_rd_md0_token_from_the_x_prefixed_one(self):      # control: a plain `rd=md0` token as the last one wins (last duplicate wins)
        self.assertEqual(self.get(CMDLINE86 + " rd=md0", "rd"), (True, "md0"))
        self.assertEqual(self.get(CMDLINE86, "xrd"), (False, ""))

    def test_the_other_keys_are_unchanged_by_the_token(self):
        for key, want in (("nat_attempt", "NAT087-rm1"), ("loader_return_after", "60"), ("launchdsuffix", "release"), ("e1stouch", "0"), ("serial", "3")):
            self.assertEqual(self.get(CMDLINE87, key), (True, want), key)
            self.assertEqual(self.get(CMDLINE87, key)[1], self.get(CMDLINE86.replace("NAT085-ep1", "NAT087-rm1"), key)[1], key)

    def test_the_line_is_below_the_sysctl_buffer_size(self):
        self.assertLess(len(CMDLINE87), 256)


@unittest.skipUnless(SYSCTL_C.is_file(), "references/apple-xnu not present")
class KernBootargsSysctl(unittest.TestCase):
    def test_kern_bootargs_returns_the_whole_line_the_parser_reads(self):
        t = SYSCTL_C.read_text()
        i = t.index("sysctl_sysctl_bootargs\n(")
        body = t[i:t.index("SYSCTL_PROC(_kern, OID_AUTO, bootargs", i)]
        self.assertIn("strlcpy(buf, PE_boot_args(), BOOT_LINE_LENGTH)", body)
        self.assertIn("sysctl_io_string(req, buf, BOOT_LINE_LENGTH", body)
        p = BOOTARGS_C.read_text()
        self.assertIn("PE_parse_boot_argn_internal(PE_boot_args(),", p)                  # the parser reads the same string


# ---------------------------------------------------------------------------------------------------------------- Apple's launchd
@unittest.skipUnless(LAUNCHD_BIN.is_file(), "the launchd of the local IPSW unpack is not present")
class AppleLaunchd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = LAUNCHD_BIN.read_bytes()
        i = cls.data.find(b"<?xml")
        while i >= 0:
            j = cls.data.find(b"</plist>", i) + 8
            if b"<key>Boot</key>" in cls.data[i:j]:
                cls.cfg = plistlib.loads(cls.data[i:j])
                break
            i = cls.data.find(b"<?xml", j)
        cls.boot = cls.cfg["Boot"]

    def test_the_binary_contains_the_substring_it_searches_for(self):
        self.assertEqual(self.data.count(b"\0rd=md0\0"), 1)

    def test_the_binary_imports_strstr(self):
        self.assertIn(b"_strstr\0", self.data)

    def test_the_lines_the_analyser_looks_for_are_strings_of_launchd(self):
        for s in (A.RESTORE_LINE, A.NO_CACHE, A.CACHE_SEARCH, A.SKIPPING, "Doing boot task"):
            self.assertIn(s.encode() + b"\0", self.data, s)

    def test_the_allowed_tasks_are_exactly_the_ones_that_run_in_restore_mode(self):
        restore = {k for k, v in self.boot.items() if v.get("PerformAlways") or v.get("PerformInRestore")}
        self.assertEqual(restore, set(A.ALLOWED_TASKS))

    def test_every_task_nat086_ran_is_outside_the_allowed_set(self):
        ran = A.read_restore(NAT86_LAUNCHD)["tasks"]
        self.assertEqual(len(ran), 12)
        for t in ran:
            self.assertIn(t, self.boot)
            self.assertNotIn(t, A.ALLOWED_TASKS)
            self.assertFalse(self.boot[t].get("PerformAlways") or self.boot[t].get("PerformInRestore"), t)

    def test_the_cache_loader_is_a_required_task_that_restore_mode_skips(self):
        v = self.boot["launchd_cache_loader"]
        self.assertTrue(v.get("RequireRun") and v.get("RequireSuccess"))
        self.assertFalse(v.get("PerformAlways") or v.get("PerformInRestore"))


# ---------------------------------------------------------------------------------------------------------------- the build wrapper
class BuildWrapper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.B = load("nat087_test_build", HERE / "build.py")

    def test_names_have_the_lengths_of_nat085s(self):
        b85 = self.B.b85
        self.assertEqual((len(self.B.NAME), len(self.B.NEW_TAG)), (len(b85.NAME), len(b85.NEW_TAG)))
        self.assertNotEqual((self.B.NAME, self.B.NEW_TAG), (b85.NAME, b85.NEW_TAG))
        self.assertEqual(self.B.TOKEN, " xrd=md0")

    def test_the_token_is_appended_last(self):
        self.assertEqual(self.B.add_token("rd=md0 a=1"), "rd=md0 a=1 xrd=md0")

    def test_an_existing_xrd_token_is_refused(self):
        for line in ("rd=md0 xrd=md1", "xrd=md0 rd=md0", "a=1 xrd="):
            with self.assertRaises(SystemExit) as cm:
                self.B.add_token(line)
            self.assertIn("already has an xrd= token", str(cm.exception))

    def test_the_length_limit_is_255_bytes_including_the_token(self):
        ok = "a" * (255 - len(self.B.TOKEN))
        self.assertEqual(len(self.B.add_token(ok)), 255)
        with self.assertRaises(SystemExit) as cm:
            self.B.add_token(ok + "a")
        self.assertIn("256", str(cm.exception))

    def test_the_length_refusal_names_the_length(self):
        with self.assertRaises(SystemExit) as cm:
            self.B.add_token("a" * (256 - len(self.B.TOKEN)))
        self.assertIn("(256 bytes)", str(cm.exception))
        self.assertLess(len(str(cm.exception)), 200)

    def test_running_the_file_calls_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build.py")], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 1, (r.stdout, r.stderr))
        self.assertIn("--ramdisk", r.stdout + r.stderr)

    def test_a_key_that_merely_ends_in_xrd_is_not_refused(self):
        self.assertTrue(self.B.add_token("notxrdish=1").endswith(" xrd=md0"))


class BuildMain(unittest.TestCase):
    """main() with NAT-085's main() replaced by a stand-in that records what the hooks look like while it runs and writes a build.json like NAT-083's."""
    ORIG = "rd=md0 a=1 loader=2"

    @classmethod
    def setUpClass(cls):
        cls.B = load("nat087_test_build_main", HERE / "build.py")

    def setUp(self):
        self.B.STATE.clear()

    def go(self, argv, record=None, fake=None, raises=None):
        """-> (seen, state after). `record`: the cmdline NAT-083's build would store as nat083_changes.cmdline (default: the hook's result with rd=md0 -> rd=md1)."""
        B, seen = self.B, {}

        def b85_main():
            seen["name"], seen["tag"] = B.b85.NAME, B.b85.NEW_TAG
            seen["hooked"] = B.b65.make_cmdline(b"x")
            if raises:
                raise raises
            if "--out" in argv:
                final = record if record is not None else seen["hooked"].replace("rd=md0 ", "rd=md1 ", 1)
                (Path(argv[argv.index("--out") + 1]) / "build.json").write_text(json.dumps({"nat083_changes": {"cmdline": final}, "other": 1}))
            if fake:
                fake(seen)

        before = (B.b85.NAME, B.b85.NEW_TAG)
        with mock.patch.object(B.b65, "make_cmdline", lambda field: self.ORIG), mock.patch.object(B.b85, "main", b85_main), mock.patch.object(sys, "argv", ["build.py"] + argv):
            try:
                B.main()
            finally:
                seen["after"] = (B.b85.NAME, B.b85.NEW_TAG, B.b65.make_cmdline(b"x"))
        seen["before"] = before
        return seen

    def test_the_names_and_the_hook_are_in_place_while_nat085_runs_and_back_after(self):
        seen = self.go([])
        self.assertEqual((seen["name"], seen["tag"]), (self.B.NAME, self.B.NEW_TAG))
        self.assertEqual(seen["hooked"], self.ORIG + " xrd=md0")
        self.assertEqual(seen["after"], (seen["before"][0], seen["before"][1], self.ORIG))
        self.assertNotEqual(seen["before"], (self.B.NAME, self.B.NEW_TAG))
        self.assertEqual(self.B.STATE["cmdline_before_root_change"], self.ORIG + " xrd=md0")

    def test_they_are_restored_when_nat085_raises(self):
        with self.assertRaises(RuntimeError):
            self.go([], raises=RuntimeError("boom"))
        self.assertNotEqual(self.B.b85.NAME, self.B.NAME)
        self.assertNotEqual(self.B.b85.NEW_TAG, self.B.NEW_TAG)

    def test_without_the_hook_having_run_the_build_is_refused(self):
        with self.assertRaises(SystemExit) as cm, mock.patch.object(self.B.b85, "main", lambda: None), mock.patch.object(sys, "argv", ["build.py"]):
            self.B.main()
        self.assertIn("hook never ran", str(cm.exception))

    def test_check_only_does_not_need_the_hook_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(self.B.b85, "main", lambda: None), mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", d]):
            self.assertIsNone(self.B.main())
            self.assertEqual(os.listdir(d), [])

    def test_build_json_gets_the_nat087_record_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            self.go(["--out", d])
            rec = json.loads((Path(d) / "build.json").read_text())
        final = self.ORIG.replace("rd=md0 ", "rd=md1 ", 1) + " xrd=md0"
        self.assertEqual(rec["other"], 1)
        self.assertEqual(rec["nat083_changes"], {"cmdline": final})
        self.assertEqual(rec["nat087_changes"], {"image_name": self.B.NAME, "cmdline_tag": self.B.NEW_TAG, "token": "xrd=md0", "cmdline": final, "cmdline_bytes": len(final)})
        self.assertEqual(rec["nat087_sources"], {"build.py": hashlib.sha256((HERE / "build.py").read_bytes()).hexdigest()})
        self.assertIn("xrd=md0", rec["nat087_note"])
        self.assertIn("nothing here ran on a phone", rec["nat087_note"])

    def test_a_final_command_line_that_does_not_end_in_the_token_is_refused(self):
        for bad in ("rd=md1 a=1 xrd=md0 b=2", "rd=md1 a=1", "", "rd=md1 a=1 xrd=md0x"):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--out", d], record=bad)
                self.assertIn("the final command line is not", str(cm.exception), bad)
                self.assertNotIn("nat087_changes", json.loads((Path(d) / "build.json").read_text()))

    def test_a_second_or_other_rd_token_is_refused(self):
        for bad in ("rd=md1 a=1 rd=md1 xrd=md0", "rd=md1 rd=md0 xrd=md0", "rd=md0 a=1 xrd=md0", "a=1 xrd=md0"):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--out", d], record=bad)
                self.assertIn("the final command line is not", str(cm.exception), bad)

    def test_a_build_json_without_a_command_line_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                self.go(["--out", d], fake=lambda seen: (Path(d) / "build.json").write_text(json.dumps({"nat083_changes": None})))

    def test_without_a_build_json_nothing_is_checked_or_written(self):
        with tempfile.TemporaryDirectory() as d:
            self.go(["--out", d], fake=lambda seen: (Path(d) / "build.json").unlink())
            self.assertEqual(os.listdir(d), [])


# ---------------------------------------------------------------------------------------------------------------- the built payload
BUILD87 = ROOT / "artifacts/nat-087/build-001/loader-diag-xnu-rm-md1/Image.payload"
BUILD85 = ROOT / "artifacts/nat-085/build-001/loader-diag-xnu-ep-md1/Image.payload"
BUILD_JSON = ROOT / "artifacts/nat-087/build-001/build.json"
CMDLINE_OFF, CMDLINE_LEN = 0x48, 608                    # the SWEETXNU header's command line field (NAT-065's build.py)
LOADER_BYTES = 385024                                   # the loader Image in front of the XNU payload (build.json: images.*.bytes)


@unittest.skipUnless(BUILD87.is_file() and BUILD85.is_file() and BUILD_JSON.is_file(), "built payloads not present")
class BuiltPayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw87, cls.raw85 = BUILD87.read_bytes(), BUILD85.read_bytes()
        cls.p87, cls.p85 = cls.raw87[LOADER_BYTES:], cls.raw85[LOADER_BYTES:]
        cls.rec = json.loads(BUILD_JSON.read_text())

    def cmd(self, p):
        return p[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].split(b"\0")[0].decode()

    def test_the_command_line_in_the_payload_is_the_recorded_one_and_ends_in_the_token(self):
        c = self.cmd(self.p87)
        self.assertEqual(c, CMDLINE87)
        self.assertEqual(c, self.rec["nat087_changes"]["cmdline"])
        self.assertEqual(self.rec["nat087_changes"]["cmdline_bytes"], len(c))
        self.assertTrue(c.endswith(" xrd=md0"))
        self.assertEqual(c.count("xrd="), 1)

    def test_only_one_rd_token_is_in_the_line_and_it_is_the_kernels_root(self):
        toks = self.cmd(self.p87).split()
        self.assertEqual([t for t in toks if t.startswith("rd=")], ["rd=md1"])
        self.assertEqual(toks[0], "rd=md1")

    def test_the_kernel_text_is_nat085s_apart_from_the_command_line_field(self):
        want = bytearray(self.p85)
        new = self.cmd(self.p85).replace("NAT085-ep1", "NAT087-rm1") + " xrd=md0"
        want[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = new.encode().ljust(CMDLINE_LEN, b"\0")
        self.assertEqual(bytes(want), self.p87)                                            # nothing else differs: ADT, ramdisk, kernel are NAT-085's

    def test_the_loader_differs_only_in_its_name_immediates(self):
        a, b = self.raw85[:LOADER_BYTES], self.raw87[:LOADER_BYTES]
        diff = [i for i in range(LOADER_BYTES) if a[i] != b[i]]
        self.assertTrue(0 < len(diff) <= 40, len(diff))
        self.assertTrue(64000 <= diff[0] and diff[-1] <= 64500, (diff[0], diff[-1]))      # the words that encode the image name / tag (as for NAT-083 -> 085)

    @unittest.skipUnless((ROOT / "artifacts/nat-087/package-001/package.json").is_file(), "artifacts/nat-087/package-001 not present")
    def test_the_payload_has_the_packaged_size_and_nat085s(self):
        want = json.loads((ROOT / "artifacts/nat-087/package-001/package.json").read_text())["images"]["loader-diag-xnu-rm-md1"]["payload_bytes"]
        self.assertEqual((len(self.raw87), len(self.raw85)), (want, want))


# ---------------------------------------------------------------------------------------------------------------- the derived session driver
PKG = ROOT / "artifacts/nat-087/package-001/package.json"


class SessionDriver(unittest.TestCase):
    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_the_committed_driver_equals_its_derivation(self):
        text, done = D.build()
        self.assertEqual((HERE / "session_nat087.py").read_text(), text)
        self.assertEqual(len(done), 9)
        self.assertTrue(all(n == 1 for _, n in done))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_the_driver_names_this_images_hashes_and_not_nat085s(self):
        pkg = json.loads(PKG.read_text())["images"][D.IMAGE_NEW]
        t = (HERE / "session_nat087.py").read_text()
        for h in (pkg["recovery_sha256"], pkg["payload_sha256"]):
            self.assertEqual(t.count(h), 1)
        self.assertIn("CANARY_LEN=%d" % pkg["payload_bytes"], t)
        for old in (D.OLD_SHA, D.OLD_PAYLOAD_SHA, "artifacts/nat-085/package-001", "nat085-%s-single-run", "artifacts/nat-085/native-attempt", D.IMAGE_OLD):
            self.assertNotIn(old, t)
        self.assertIn("artifacts/nat-083/system-padded.apfs", t)                           # the big root is deliberately NAT-083's
        self.assertIn("'NAT-083','NAT-084','NAT-085','NAT-087'", t)
        self.assertIn("nat087-%s-single-run", t)
        self.assertIn("artifacts/nat-087/native-attempt-%s-used.json", t)
        self.assertIn("analyze_nat087.py", t)

    def test_a_drifted_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session_nat085.py"
            p.write_bytes(D.SRC.read_bytes() + b"# drift\n")
            with mock.patch.object(D, "SRC", p):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("not the file this derivation was written for", str(cm.exception))

    def test_a_missing_substitution_target_is_refused_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.py"
            p.write_text(D.SRC.read_text().replace("'NAT-084','NAT-085')", "'NAT-084')"))
            with mock.patch.object(D, "SRC", p), mock.patch.object(D, "SRC_SHA256", hashlib.sha256(p.read_bytes()).hexdigest()):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("required tasks: expected 1 occurrence(s)", str(cm.exception))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_a_payload_of_another_length_is_refused(self):
        pkg = json.loads(PKG.read_text())
        pkg["images"][D.IMAGE_NEW]["payload_bytes"] += 8
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text(json.dumps(pkg))
            with mock.patch.object(D, "PACKAGE", Path(d)):
                with self.assertRaises(ValueError) as cm:
                    D.build()
        self.assertIn("CANARY_LEN", str(cm.exception))


class DeriveCommand(unittest.TestCase):
    NAME = "session_nat087.py"

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = D.main(argv)
        return rc, out.getvalue(), err.getvalue()

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_check_says_ok_with_the_substitution_count_and_prints_nothing_else(self):
        self.assertEqual(self.call(["--check"]), (0, "ok: session_nat087.py equals the derivation (9 substitutions)\n", ""))

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_check_names_the_difference_on_stderr_and_never_writes(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / self.NAME
            other.write_text("x")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat087.py differs from the derivation\n"))
            self.assertEqual(other.read_text(), "x")
            with mock.patch.object(D, "OUT", Path(d) / "missing.py"):
                self.assertEqual(self.call(["--check"]), (1, "", "session_nat087.py differs from the derivation\n"))
            self.assertFalse((Path(d) / "missing.py").exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_without_check_it_writes_the_driver_and_reports_its_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)
            (fake / "docs/procedures/nat-087").mkdir(parents=True)
            target = fake / "docs/procedures/nat-087" / self.NAME
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
            self.assertEqual((rc, err), (0, ""))
            text, done = D.build()
            self.assertEqual(target.read_text(), text)
            self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")
            rep = json.loads(out)
            self.assertEqual(rep["out"], "docs/procedures/nat-087/session_nat087.py")
            self.assertEqual(rep["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(len(rep["substitutions"]), 9)
            self.assertTrue(all(s["count"] == 1 for s in rep["substitutions"]))

    def test_a_drifted_source_is_refused_with_status_2_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            drifted = Path(d) / "session_nat085.py"
            drifted.write_text(D.SRC.read_text() + "\n# drift\n")
            target = Path(d) / self.NAME
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", target):
                rc, out, err = self.call([])
                rc2, out2, err2 = self.call(["--check"])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: session_nat085.py is not the file this derivation was written for"), err)
            self.assertEqual((rc2, out2), (2, ""))
            self.assertFalse(target.exists())

    @unittest.skipUnless(PKG.is_file(), "artifacts/nat-087/package-001 not present")
    def test_run_as_a_script_the_flag_reaches_main(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive87.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ok: session_nat087.py equals the derivation (9 substitutions)\n", ""))

    def test_the_output_path_is_the_committed_driver(self):
        self.assertEqual(D.OUT, HERE / "session_nat087.py")


# ---------------------------------------------------------------------------------------------------------------- the restore reader and ladder
RESTORE_HEAD = ("com.apple.xpc.launchd|1970-01-01 00:03:04.600000 <Notice>: Restore environment starting.\n"
                "com.apple.xpc.launchd|1970-01-01 00:03:04.610000 <Error>: Unable to open /System/Library/xpc/launchd.plist [2:No such file or directory]\n")


def restore_variant(tail=""):
    """The head of the REAL NAT-086 launchd text (libignition, FIPS POST) followed by the restore line and `tail`. HAND-WRITTEN beyond the head: no run has printed this."""
    i = NAT86_LAUNCHD.index("com.apple.xpc.launchd|1970-01-01 00:03:04.687952 (keybag)")
    head = NAT86_LAUNCHD[:i]
    k = head.index("[... 5321 bytes")
    head = head[:k] + head[head.index("\n", k) + 1:]                                        # without the gap marker: the synthetic text is complete
    return head + RESTORE_HEAD + tail


def task_line(name, t="00:03:05.300000"):
    return "com.apple.xpc.launchd|1970-01-01 %s (%s) <Notice>: Doing boot task\n" % (t, name)


def whole(launchd_text, **kw):
    """A complete returned text of the NAT-083 chain (rows 1-4 as in the real run) with `launchd_text` as the output of the last exec."""
    cmds = list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", launchd_text, None)]
    return T83.text(cmds, **kw)


def verdict(t, chain="PASS"):
    kern = A.A83.read_userland(t)
    d = A.A83.decide(chain, T83.DELIVERED, T83.loader(), SIZE, kern)
    return A.decide_restore(d, A.read_restore(A.after_exec_text(t)), kern), d


class Reader(unittest.TestCase):
    def test_the_real_nat086_text_is_read_task_by_task(self):
        st = A.read_restore(NAT86_LAUNCHD)
        self.assertEqual(st["tasks"], ["keybag", "usermanagerd", "dirs_cleaner", "xpcroleaccountd", "init_featureflags", "auearlyboot", "tzinit", "finish-restore", "finish-demo-restore",
                                       "sysstatuscheck", "prng_seedctl", "launchd_cache_loader"])
        self.assertEqual(st["unexpected_tasks"], st["tasks"])
        self.assertEqual((st["restore_line"], st["keybag_ran"], st["cache_loader_ran"], st["no_cache"], st["plist_missing_line"]), (False, True, True, False, True))
        self.assertEqual((st["job_runs"], st["fips_all_passed"], st["reboot_request"]), (0, True, False))
        self.assertEqual(st["last_task"], "launchd_cache_loader")

    def test_the_real_nat084_text_is_read_too(self):
        st = A.read_restore(NAT84_LAUNCHD)
        self.assertEqual(len(st["tasks"]), 12)
        self.assertEqual((st["restore_line"], st["reboot_request"], st["keybag_ran"], st["cache_loader_ran"]), (False, True, True, False))

    def test_the_restore_line_is_found_anywhere_in_the_text(self):
        self.assertTrue(A.read_restore("x" + A.RESTORE_LINE + "y")["restore_line"])
        self.assertFalse(A.read_restore("Restore environment starting")["restore_line"])      # without the full stop it is not the line

    def test_allowed_tasks_are_not_unexpected_and_others_are(self):
        t = task_line("commit-boot-mode") + task_line("init-with-data-volume") + task_line("restore-datapartition") + task_line("fsck")
        st = A.read_restore(t)
        self.assertEqual(st["tasks"], ["commit-boot-mode", "init-with-data-volume", "restore-datapartition", "fsck"])
        self.assertEqual(st["unexpected_tasks"], ["fsck"])
        self.assertEqual(st["last_task"], "fsck")

    def test_the_cache_lines_and_the_skipping_lines_are_facts(self):
        st = A.read_restore("a\n%s\nb\n%s: x\n%s\n" % (A.CACHE_SEARCH, A.SKIPPING, A.SKIPPING))
        self.assertEqual((st["cache_search_line"], st["no_cache"], st["skipping_total"]), (True, False, 2))
        self.assertEqual(len(st["skipping_lines"]), 2)
        self.assertEqual(A.read_restore("No service cache\n")["no_cache"], True)

    def test_each_header_is_one_run_and_the_last_list_is_kept(self):
        st = A.read_restore("noise\n" + PS_BLOCK + "more\n" + PS_BLOCK.replace("/bin/ps -A", "/bin/other"))
        self.assertEqual(st["job_runs"], 2)
        self.assertEqual(st["last_heartbeat"], ["/redwood/sbin/init", "/bin/other"])

    def test_a_header_inside_other_text_is_not_a_run(self):
        self.assertEqual(A.read_restore("x  PID TTY TIME CMD\n")["job_runs"], 0)

    def test_the_text_after_the_last_exec_echo_is_what_is_read(self):
        t = whole("first\n")
        self.assertEqual(A.after_exec_text(t).strip().split("\n")[0], "first")
        self.assertIsNone(A.after_exec_text("no echo here"))
        self.assertIsNone(A.after_exec_text(None))

    def test_kernel_buffer_text_is_not_launchd_output(self):
        t = whole("launchd text\n")
        k = t.find(A.A83.KMARK)
        self.assertGreater(k, 0)
        self.assertNotIn("zzkernelzz", A.after_exec_text(t + "zzkernelzz"))

    def test_carriage_returns_do_not_break_the_reading(self):
        st = A.read_restore((RESTORE_HEAD + task_line("fsck") + PS_BLOCK).replace("\n", "\r\n"))
        self.assertEqual((st["restore_line"], st["tasks"], st["job_runs"]), (True, ["fsck"], 1))


class Ladder(unittest.TestCase):
    def check(self, t, row, chain="PASS"):
        s, d = verdict(t, chain)
        self.assertEqual(s["row"], row, (s["name"], s["reasons"]))
        self.assertEqual(s["name"], A.ROWS[row])
        self.assertEqual(s["pass"], row == 1)
        return s

    def test_r5_the_real_nat086_text_cache_loader_ran(self):                                # control: the run WITHOUT the token reads "boot tasks not skipped"
        s = self.check(whole(NAT86_LAUNCHD), 5)
        self.assertEqual(s["facts"]["chain_row"], 1)
        self.assertEqual(s["facts"]["restore_line"], False)
        self.assertIn("launchd_cache_loader", s["facts"]["unexpected_tasks"])
        self.assertIn("not seen", s["reasons"][0])

    def test_r5_the_real_nat084_text(self):
        self.assertEqual(self.check(whole(NAT84_LAUNCHD), 5)["facts"]["restore_line"], False)

    def test_r1_restore_line_and_two_process_lists(self):
        s = self.check(whole(restore_variant(task_line("commit-boot-mode") + PS_BLOCK + "launchd noise\n" + PS_BLOCK)), 1)
        self.assertEqual(s["facts"]["job_runs"], 2)
        self.assertEqual(s["facts"]["tasks"], ["commit-boot-mode"])
        self.assertEqual(s["facts"]["unexpected_tasks"], [])
        self.assertIn("2 process lists", s["reasons"][0])

    def test_r1_with_no_task_line_at_all(self):
        self.assertEqual(self.check(whole(restore_variant(PS_BLOCK + PS_BLOCK)), 1)["facts"]["tasks"], [])

    def test_r2_one_process_list(self):
        s = self.check(whole(restore_variant(PS_BLOCK)), 2)
        self.assertEqual(s["facts"]["job_runs"], 1)

    def test_r3_restore_line_and_no_process_list(self):
        self.check(whole(restore_variant("")), 3)

    def test_r4_a_reboot_request(self):
        s = self.check(whole(restore_variant("REBOOTING INTO RECOVERY MODE.\n" + PS_BLOCK + PS_BLOCK)), 4)
        self.assertEqual(s["facts"]["job_runs"], 2)
        self.assertIn("a reboot request line", s["reasons"][0])

    def test_r4_the_fatal_no_service_cache_line(self):
        s = self.check(whole(restore_variant("No service cache\n" + PS_BLOCK + PS_BLOCK)), 4)
        self.assertIn("No service cache", s["reasons"][0])

    def test_r4_a_pid1_exit_or_a_panic(self):
        for extra, key in (("\nPID 1 exited: sub-process /sbin/launchd.darwin ended\n", "pid1_exit"), ("\npanic(cpu 0 caller 0xfffffe0012345678): launchd[1] exited -- exit reason namespace 7 subcode 0x1\n", "panic")):
            t = whole(restore_variant(PS_BLOCK)) + extra
            s, d = verdict(t)
            self.assertEqual(d["row"], 1, d["name"])
            if s["row"] == 4:
                self.assertTrue(s["facts"][key], key)

    def test_r5_an_unexpected_task_wins_over_the_restore_line_and_the_heartbeats(self):
        s = self.check(whole(restore_variant(task_line("fsck") + PS_BLOCK + PS_BLOCK)), 5)
        self.assertEqual(s["facts"]["restore_line"], True)
        self.assertIn("seen", s["reasons"][0])
        self.assertNotIn("not seen", s["reasons"][0])
        self.assertEqual(s["facts"]["unexpected_tasks"], ["fsck"])

    def test_r5_an_unexpected_task_wins_over_a_stop(self):
        self.check(whole(restore_variant(task_line("launchd_cache_loader") + "REBOOTING INTO RECOVERY MODE.\n")), 5)

    def test_r6_launchd_printed_lines_but_no_restore_line_and_no_task(self):
        s = self.check(whole(restore_variant("").replace(RESTORE_HEAD, "") + PS_BLOCK + PS_BLOCK), 6)
        self.assertEqual(s["facts"]["tasks"], [])

    def test_r6_only_allowed_tasks_and_no_restore_line(self):
        self.check(whole(restore_variant(task_line("commit-boot-mode")).replace(RESTORE_HEAD, "")), 6)

    def test_r6_a_stop_without_the_restore_line_is_still_r6(self):
        self.check(whole(restore_variant("REBOOTING INTO RECOVERY MODE.\n").replace(RESTORE_HEAD, "")), 6)

    def test_r7_exec_reached_launchd_printed_nothing(self):
        s = self.check(whole("stray text\n"), 7)
        self.assertIn("none of them from launchd", s["reasons"][0])

    def test_r9_the_chain_row_is_not_1(self):
        t = whole(restore_variant(PS_BLOCK + PS_BLOCK))
        kern = A.A83.read_userland(t)
        d = dict(A.A83.decide("PASS", T83.DELIVERED, T83.loader(), SIZE, kern), row=2, name="x")
        s = A.decide_restore(d, A.read_restore(A.after_exec_text(t)), kern)
        self.assertEqual((s["row"], s["pass"]), (9, False))
        self.assertIn("not evaluated", s["reasons"][0])

    def test_r9_no_exec_line_at_all(self):
        t = T83.text(list(T83.GOOD[:-1]))
        s, d = verdict(t)
        self.assertEqual(s["row"], 9)

    def test_chain_row_1b_is_still_evaluated(self):
        t = whole(restore_variant(PS_BLOCK + PS_BLOCK))
        kern = A.A83.read_userland(t)
        d = dict(A.A83.decide("PASS", T83.DELIVERED, T83.loader(), SIZE, kern), variant="b")
        s = A.decide_restore(d, A.read_restore(A.after_exec_text(t)), kern)
        self.assertEqual((s["row"], s["facts"]["chain_variant"]), (1, "b"))


class Closers(unittest.TestCase):
    def test_the_bounds_are_exact(self):
        many = "".join("com.apple.xpc.launchd|x <Error>: failure %d\n" % i for i in range(A.NOTABLE_KEEP + 5))
        st = A.read_restore(A.RESTORE_LINE + "\n" + many)
        self.assertEqual((len(st["notable_after_restore"]), st["notable_total"]), (A.NOTABLE_KEEP, A.NOTABLE_KEEP + 5))
        long_line = A.RESTORE_LINE + "\nfailed " + "x" * 500 + "\n"
        self.assertEqual(len(A.read_restore(long_line)["notable_after_restore"][0]), A.LINE_KEEP)
        rows = "".join("%5d ?? 0:00.01 /bin/p%d\n" % (i + 1, i) for i in range(A.PS_KEEP + 5))
        st = A.read_restore("  PID TTY TIME CMD\n" + rows)
        self.assertEqual(len(st["last_heartbeat"]), A.PS_KEEP)
        skips = "".join("%s %d\n" % (A.SKIPPING, i) for i in range(A.KEEP_LINES + 3))
        st = A.read_restore(skips)
        self.assertEqual((len(st["skipping_lines"]), st["skipping_total"]), (A.KEEP_LINES, A.KEEP_LINES + 3))
        labels = "".join("com.nat085.ps line %d\n" % i for i in range(A.KEEP_LINES + 3))
        self.assertEqual(len(A.read_restore(labels)["job_label_lines"]), A.KEEP_LINES)

    def test_notable_lines_before_the_restore_line_are_not_counted(self):
        st = A.read_restore("failure before\n" + A.RESTORE_LINE + "\nfailure after\n")
        self.assertEqual(st["notable_after_restore"], ["failure after"])
        self.assertEqual(A.read_restore("failure alone\n")["notable_after_restore"], [])

    def test_a_process_row_before_any_header_is_not_a_run_and_does_not_crash(self):
        self.assertEqual(A.read_restore("    1 ??         0:00.11 /sbin/launchd\n")["job_runs"], 0)

    def test_a_block_ends_at_the_first_line_that_is_not_a_row(self):
        st = A.read_restore(PS_BLOCK + "not a row\n    9 ??         0:00.01 /late/row\n")
        self.assertEqual(st["last_heartbeat"], ["/redwood/sbin/init", "/bin/ps -A"])

    def test_the_last_exec_echo_wins(self):
        t = T83.text(list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", "first\n", None), ("exec /sbin/launchd.darwin", "second\n", None)])
        self.assertEqual(A.after_exec_text(t).strip().split("\n")[0], "second")

    def test_a_non_exec_echo_after_the_exec_is_not_the_cut(self):
        t = T83.text(list(T83.GOOD[:-1]) + [("exec /sbin/launchd.darwin", "launchd out\n", None), ("ls", "listing\n", None)])
        self.assertTrue(A.after_exec_text(t).strip().startswith("launchd out"))

    def test_the_reasons_name_their_numbers(self):
        s, _ = verdict(whole(restore_variant(task_line("fsck") + task_line("mount-phase-1"))))
        self.assertIn("2 unexpected of 2", s["reasons"][0])
        s, _ = verdict(whole(restore_variant(PS_BLOCK + PS_BLOCK + PS_BLOCK)))
        self.assertIn("3 process lists", s["reasons"][0])
        s, _ = verdict(whole(restore_variant("").replace(RESTORE_HEAD, "") + "\n" + GAP))
        self.assertIn("5000 bytes", s["reasons"][0])

    def test_the_facts_carry_the_chain_and_the_log_gap(self):
        s, d = verdict(whole(restore_variant(PS_BLOCK + PS_BLOCK)))
        f = s["facts"]
        self.assertEqual((f["chain_row"], f["chain_variant"], f["gap_bytes"]), (d["row"], d["variant"], 0))


GAP = "\n[... 5000 bytes of the log were not sent ...]\n"


class Gaps(unittest.TestCase):
    def with_gap(self, launchd_text):
        return whole(launchd_text + GAP)

    def test_missing_restore_line_with_a_gap_is_not_established(self):
        s, _ = verdict(self.with_gap(restore_variant(PS_BLOCK + PS_BLOCK).replace(RESTORE_HEAD, "")))
        self.assertEqual((s["row"], s["name"]), (8, "not-established"))
        self.assertIn("5000 bytes", s["reasons"][0])

    def test_missing_launchd_lines_with_a_gap_is_not_established(self):
        s, _ = verdict(self.with_gap("stray\n"))
        self.assertEqual(s["row"], 8)

    def test_missing_process_list_with_a_gap_is_not_established_and_a_present_one_is_judged(self):
        self.assertEqual(verdict(self.with_gap(restore_variant("")))[0]["row"], 8)
        self.assertEqual(verdict(self.with_gap(restore_variant(PS_BLOCK)))[0]["row"], 2)
        self.assertEqual(verdict(self.with_gap(restore_variant(PS_BLOCK + PS_BLOCK)))[0]["row"], 1)

    def test_a_stop_is_a_finding_even_with_a_gap(self):
        self.assertEqual(verdict(self.with_gap(restore_variant("REBOOTING INTO RECOVERY MODE.\n")))[0]["row"], 4)

    def test_an_unexpected_task_is_a_finding_even_with_a_gap(self):
        self.assertEqual(verdict(self.with_gap(NAT86_LAUNCHD))[0]["row"], 5)
        self.assertEqual(verdict(self.with_gap(restore_variant(task_line("fsck"))))[0]["row"], 5)

    def test_the_real_nat086_text_has_a_gap_and_still_reads_r5(self):
        s, _ = verdict(whole(NAT86_LAUNCHD))
        self.assertGreater(s["facts"]["gap_bytes"], 5000)
        self.assertEqual(s["row"], 5)



class Boundaries(unittest.TestCase):
    """Added after the first mutation pass: literal numbers (the older bounds test used the module's own constants, so changing a constant could not fail it), values at the edges of the
    text, and the stop signs of decide_restore built by hand because the text-level tests reach them only when the kernel text happens to match."""

    def good(self, tail):
        t = whole(restore_variant(tail))
        kern = A.A83.read_userland(t)
        d = A.A83.decide("PASS", T83.DELIVERED, T83.loader(), SIZE, kern)
        self.assertEqual(d["row"], 1)
        return d, A.read_restore(A.after_exec_text(t)), kern

    def test_report_bounds_are_the_literal_numbers(self):
        many = "".join("com.apple.xpc.launchd|x <Error>: failure %d\n" % i for i in range(30))
        st = A.read_restore(A.RESTORE_LINE + "\n" + many)
        self.assertEqual((len(st["notable_after_restore"]), st["notable_total"]), (25, 30))
        self.assertEqual(len(A.read_restore(A.RESTORE_LINE + "\nfailed " + "x" * 500 + "\n")["notable_after_restore"][0]), 200)
        rows = "".join("%5d ?? 0:00.01 /bin/p%d\n" % (i + 1, i) for i in range(50))
        self.assertEqual(len(A.read_restore("  PID TTY TIME CMD\n" + rows)["last_heartbeat"]), 40)
        st = A.read_restore("".join("%s %d\n" % (A.SKIPPING, i) for i in range(13)))
        self.assertEqual((len(st["skipping_lines"]), st["skipping_total"]), (10, 13))
        self.assertEqual(len(A.read_restore("".join("com.nat085.ps line %d\n" % i for i in range(13)))["job_label_lines"]), 10)
        self.assertEqual(len(A.read_restore(A.SKIPPING + " " + "z" * 500 + "\n")["skipping_lines"][0]), 200)

    def test_the_libignition_failure_line_is_the_first_such_line_and_is_cut(self):
        st = A.read_restore("a line\nlibignition: ignition boot failed (errno 25)\nlater ignition boot failed again\n")
        self.assertEqual(st["libignition_failed"], "libignition: ignition boot failed (errno 25)")
        self.assertIsNone(A.read_restore("a line\nignition boot ok\n")["libignition_failed"])
        self.assertEqual(len(A.read_restore("ignition boot failed " + "y" * 500 + "\n")["libignition_failed"]), 200)

    def test_a_restore_line_at_the_very_start_is_found(self):
        self.assertTrue(A.read_restore(A.RESTORE_LINE + "\n")["restore_line"])
        self.assertEqual(A.read_restore(A.RESTORE_LINE)["notable_after_restore"], [])

    def test_a_kernel_marker_at_the_very_start_leaves_no_launchd_text(self):
        self.assertIsNone(A.after_exec_text(A.A83.KMARK + "\n$ exec /sbin/launchd.darwin\nkernel text only\n"))
        self.assertEqual(A.after_exec_text("$ exec /sbin/launchd.darwin\nout\n" + A.A83.KMARK + "\n$ exec /x\nkernel\n"), "\nout\n")

    def test_no_exec_in_the_kernel_reading_is_row_9_with_its_reason(self):
        d, st, kern = self.good(PS_BLOCK + PS_BLOCK)
        s = A.decide_restore(d, st, dict(kern, exec_seen=False))
        self.assertEqual((s["row"], s["name"], s["pass"]), (9, "not-evaluated", False))
        self.assertEqual(s["reasons"], ["no `$ exec` line in the console text"])

    def test_launchd_silent_reason_carries_the_byte_count(self):
        s, _ = verdict(whole("stray text\n"))
        self.assertEqual(s["row"], 7)
        self.assertEqual(s["reasons"], ["%d bytes of console text after the exec line, none of them from launchd" % s["facts"]["bytes"]])
        self.assertGreater(s["facts"]["bytes"], 0)

    def test_the_unexpected_task_list_in_the_reason_is_cut_at_six(self):
        s, _ = verdict(whole(restore_variant("".join(task_line("t%d" % i) for i in range(8)))))
        self.assertEqual(s["row"], 5)
        self.assertIn("['t0', 't1', 't2', 't3', 't4', 't5']", s["reasons"][0])
        self.assertNotIn("t6", s["reasons"][0])
        self.assertIn("8 unexpected of 8", s["reasons"][0])

    def test_each_stop_sign_alone_makes_row_4_and_is_named(self):
        d, st, kern = self.good(PS_BLOCK + PS_BLOCK)
        exit_info = dict(pid=1, signal=6, status=0)
        for key in ("pid1_exit", "pid1_exit_printf"):
            other = "pid1_exit_printf" if key == "pid1_exit" else "pid1_exit"
            s = A.decide_restore(d, st, dict(kern, **{key: exit_info, other: None, "panic": None}))
            self.assertEqual(s["row"], 4, key)
            self.assertIn("PID 1 exit %s" % (exit_info,), s["reasons"][0])
            self.assertEqual(s["facts"]["pid1_exit"], exit_info)
        s = A.decide_restore(d, st, dict(kern, pid1_exit=None, pid1_exit_printf=None, panic="panic(cpu 0 caller 0x1): x"))
        self.assertEqual(s["row"], 4)
        self.assertIn("panic panic(cpu 0 caller 0x1): x", s["reasons"][0])
        self.assertNotIn("PID 1 exit", s["reasons"][0])
        s = A.decide_restore(d, st, dict(kern, pid1_exit=None, pid1_exit_printf=None, panic=None))
        self.assertEqual(s["row"], 1)                                   # the same inputs with no sign: the control

    def test_the_row_4_reason_names_the_tasks_and_the_job_runs(self):
        d, st, kern = self.good(PS_BLOCK + PS_BLOCK)
        stop = dict(kern, panic="p")
        s = A.decide_restore(d, st, stop)
        self.assertTrue(s["reasons"][0].startswith("restore mode entered; boot tasks started: none; launchd stopped: panic p"), s["reasons"][0])
        self.assertTrue(s["reasons"][0].endswith("; job runs seen: 2"), s["reasons"][0])
        d, st, kern = self.good(task_line("commit-boot-mode") + PS_BLOCK)
        s = A.decide_restore(d, st, dict(kern, panic="p"))
        self.assertIn("boot tasks started: ['commit-boot-mode']; launchd stopped", s["reasons"][0])
        self.assertTrue(s["reasons"][0].endswith("; job runs seen: 1"), s["reasons"][0])

# ---------------------------------------------------------------------------------------------------------------- the real archives
class RealArchiveBase:
    DIR = None
    NAME = None
    CHAIN_VARIANT = None

    @classmethod
    def setUpClass(cls):
        events, _ = A.A65.A49.read_jsonl(str(cls.DIR / "usb-events.jsonl"))
        report = A.A65.A49.read_json(str(cls.DIR / "report.json")) or {}
        cls.events, cls.report = events, report
        cls.res = A.analyze(cls.DIR / "archive", events, report, cls.DIR / "delivery", ROOT_IMAGE, SIZE, ROOT_SHA, image=cls.NAME)

    def test_the_chain_reads_row_1_as_in_the_committed_analysis(self):
        n = self.res["nat087"]
        self.assertEqual((n["chain_row"], n["chain_pass"]), (1, self.CHAIN_VARIANT == "a"))     # `pass` is the decision-0032 reading: row 1 variant a only
        self.assertEqual(self.res["nat083"]["decision"]["variant"], self.CHAIN_VARIANT)

    def test_the_restore_ladder_reads_r5_and_the_facts_of_the_real_launchd_text(self):
        s = self.res["nat087"]["restore"]
        self.assertEqual((s["row"], s["name"], s["pass"]), (5, "boot-tasks-not-skipped", False), s["reasons"])
        f = self.res["nat087"]["launchd"]
        self.assertEqual(len(f["tasks"]), 12)
        self.assertEqual((f["restore_line"], f["job_runs"], f["fips_all_passed"]), (False, 0, True))

    def test_the_default_image_name_is_the_new_image_and_the_old_run_is_refused_under_it(self):
        res = A.analyze(self.DIR / "archive", self.events, self.report, self.DIR / "delivery", ROOT_IMAGE, SIZE, ROOT_SHA)
        self.assertEqual(res["nat087"]["chain_row"], 9)                                    # the old run is not this image's own boot
        self.assertEqual(res["nat087"]["restore"]["row"], 9)

    def test_the_module_global_image_name_is_restored(self):
        with mock.patch.object(A.A83, "IMAGE", "sentinel-image-name"):
            res = A.analyze(self.DIR / "archive", self.events, self.report, self.DIR / "delivery", ROOT_IMAGE, SIZE, ROOT_SHA, image=self.NAME)
            self.assertEqual(A.A83.IMAGE, "sentinel-image-name")
        self.assertEqual(res["nat087"]["chain_row"], 1)

    def test_the_wrong_root_file_is_refused_and_the_global_restored(self):
        with mock.patch.object(A.A83, "IMAGE", "sentinel-image-name"):
            with self.assertRaises(ValueError):
                A.analyze(self.DIR / "archive", self.events, {}, self.DIR / "delivery", ROOT_IMAGE, SIZE, "0" * 64, image=self.NAME)
            self.assertEqual(A.A83.IMAGE, "sentinel-image-name")

    def argv(self, extra=()):
        return ["--archive", str(self.DIR / "archive"), "--events", str(self.DIR / "usb-events.jsonl"), "--report", str(self.DIR / "report.json"), "--delivery", str(self.DIR / "delivery"),
                "--root", str(ROOT_IMAGE), "--size", str(SIZE), "--sha256", ROOT_SHA, "--image", self.NAME] + list(extra)

    def run_main(self, extra=()):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(A.A80, "host_prefix_digests", lambda p, sizes: {SIZE: ROOT_SHA}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = A.main(self.argv(extra))
        return rc, out.getvalue(), err.getvalue()

    def test_main_prints_the_record_and_writes_out_and_log_once(self):
        with tempfile.TemporaryDirectory() as d:
            o, lg = Path(d) / "analysis.json", Path(d) / "kernel.log"
            rc, out, err = self.run_main(["--out", str(o), "--log-out", str(lg)])
            self.assertEqual((rc, err), (0, ""))
            self.assertEqual(o.read_text(), out)
            self.assertEqual(json.loads(out)["nat087"]["restore"]["row"], 5)
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
        self.assertEqual(out, json.dumps(json.loads(out), indent=1) + "\n")

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
            argv = self.argv(["--out", str(o)])
            argv[argv.index(ROOT_SHA)] = "0" * 64
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = A.main(argv)
            self.assertEqual((rc, out.getvalue()), (2, ""))
            self.assertTrue(err.getvalue().startswith("refused: the root file is not the image"), err.getvalue())
            self.assertFalse(o.exists())


@unittest.skipUnless(NAT86.is_dir() and ROOT_IMAGE.is_file(), "artifacts/nat-085/run-001 (the NAT-086 archive) not present")
class RealArchiveNat086(RealArchiveBase, unittest.TestCase):
    """analyze() over the archive of NAT-086 (loader-diag-xnu-ep-md1: no token): the control run must read R5, the cache loader ran."""
    DIR, NAME, CHAIN_VARIANT = NAT86, "loader-diag-xnu-ep-md1", "b"

    def test_the_cache_loader_ran_in_the_real_run(self):
        f = self.res["nat087"]["launchd"]
        self.assertTrue(f["cache_loader_ran"] and f["keybag_ran"])
        self.assertEqual(f["last_task"], "launchd_cache_loader")


@unittest.skipUnless(NAT84.is_dir() and ROOT_IMAGE.is_file(), "artifacts/nat-083/run-001 (the NAT-084 archive) not present")
class RealArchiveNat084(RealArchiveBase, unittest.TestCase):
    """analyze() over the archive of NAT-084 (loader-diag-xnu-rt-md1, before the ephemeral-storage property): also R5 (twelve tasks ran; the keybag one asked for a reboot)."""
    DIR, NAME, CHAIN_VARIANT = NAT84, "loader-diag-xnu-rt-md1", "a"

    def test_the_keybag_reboot_request_is_in_the_facts(self):
        self.assertTrue(self.res["nat087"]["launchd"]["reboot_request"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
