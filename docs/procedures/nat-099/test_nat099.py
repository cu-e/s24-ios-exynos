#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-099: tests of the Stage B small-root builder. Synthetic cases check the refusals with exact messages; the real-artifact cases (skipped when the local
artifacts are absent) compare the built tree with NAT-096's file by file and cross-check inject.conf against the dylib's install name and the job plists' programs."""
import importlib.util
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


B = _load("nat099_build", HERE / "build_stage_b_root.py")
MA = _load("nat099_macho_audit", ROOT / "tools/ios/macho_audit.py")
BASE = ROOT / "artifacts/nat-096/pid1-sq"
OUT = ROOT / "artifacts/nat-099/pid1-sb2"
DYLIB = ROOT / "references/hakios/prebuilt/userland/libhakios.dylib"
APPLE = ROOT / "artifacts/ios-root/recipe/sysimage/rootfs/System/Library/LaunchDaemons/com.apple.backboardd.plist"
HAVE = BASE.is_dir() and OUT.is_dir() and DYLIB.is_file() and APPLE.is_file()


def plist(**kw):
    return plistlib.dumps(kw)


class TreeDiff(unittest.TestCase):
    def test_added_removed_changed_and_mode_change(self):
        a = {"x": ("file", 0o644, "h1"), "y": ("file", 0o644, "h2"), "d": ("dir",)}
        b = {"x": ("file", 0o755, "h1"), "z": ("file", 0o644, "h3"), "d": ("dir",)}
        self.assertEqual(B.tree_diff(a, b), (["z"], ["y"], ["x"]))

    def test_tree_reads_files_modes_symlinks_and_dirs(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "d").mkdir()
            (r / "d/f").write_bytes(b"abc")
            (r / "d/f").chmod(0o750)
            (r / "l").symlink_to("d/f")
            got = B.tree(r)
            self.assertEqual(got["d"], ("dir",))
            self.assertEqual(got["d/f"], ("file", 0o750, B.sha256_bytes(b"abc")))
            self.assertEqual(got["l"], ("symlink", "d/f"))


class PlistCheck(unittest.TestCase):
    def pins(self, apple, made):
        return mock.patch.multiple(B, APPLE_BACKBOARDD_PLIST_SHA256=B.sha256_bytes(apple), MKJOBS_BACKBOARDD_PLIST_SHA256=B.sha256_bytes(made))

    def test_apple_plus_one_key_passes(self):
        a = plist(Label="l", KeepAlive=True)
        m = plist(Label="l", KeepAlive=True, StandardErrorPath="/dev/console")
        with self.pins(a, m):
            B.check_backboardd_plist(a, m)

    def test_unpinned_apple_plist_is_refused(self):
        a = plist(Label="l")
        with self.assertRaisesRegex(B.BuildError, "Apple's backboardd plist is sha256 .* not the pinned"):
            B.check_backboardd_plist(a, plist(Label="l", StandardErrorPath="/dev/console"))

    def test_wrong_error_path_is_refused(self):
        a = plist(Label="l")
        m = plist(Label="l", StandardErrorPath="/dev/null")
        with self.pins(a, m), self.assertRaisesRegex(B.BuildError, "StandardErrorPath '/dev/null', not /dev/console"):
            B.check_backboardd_plist(a, m)

    def test_a_second_changed_key_is_refused_and_named(self):
        a = plist(Label="l", KeepAlive=True)
        m = plist(Label="l", KeepAlive=False, StandardErrorPath="/dev/console")
        with self.pins(a, m), self.assertRaisesRegex(B.BuildError, r"more than the StandardErrorPath key: \['KeepAlive'\]"):
            B.check_backboardd_plist(a, m)

    def test_an_added_key_besides_the_error_path_is_refused(self):
        a = plist(Label="l")
        m = plist(Label="l", StandardErrorPath="/dev/console", StandardOutPath="/dev/console")
        with self.pins(a, m), self.assertRaisesRegex(B.BuildError, r"\['StandardOutPath'\]"):
            B.check_backboardd_plist(a, m)

    def test_unpinned_mkjobs_result_is_refused(self):
        a = plist(Label="l")
        m = plist(Label="l", StandardErrorPath="/dev/console")
        with mock.patch.object(B, "APPLE_BACKBOARDD_PLIST_SHA256", B.sha256_bytes(a)), self.assertRaisesRegex(B.BuildError, "mkjobs.py wrote is sha256 .* not the pinned"):
            B.check_backboardd_plist(a, m)


class Refusals(unittest.TestCase):
    def test_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as t, self.assertRaisesRegex(B.BuildError, "must be new"):
            B.build(t, BASE, ROOT, DYLIB)

    def test_base_without_image(self):
        with tempfile.TemporaryDirectory() as t, self.assertRaisesRegex(B.BuildError, "has no root.apfs and root/"):
            B.build(Path(t) / "out", t, ROOT, DYLIB)

    def test_base_with_another_image(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "root").mkdir()
            (Path(t) / "root.apfs").write_bytes(b"not the pinned image")
            with self.assertRaisesRegex(B.BuildError, "the base root.apfs is sha256 .* not the pinned"):
                B.build(Path(t) / "out", t, ROOT, DYLIB)


@unittest.skipUnless(HAVE, "local artifacts absent")
class RealArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads((OUT / "build.json").read_text())
        cls.before = B.tree(BASE / "root")
        cls.after = B.tree(OUT / "root")

    def test_base_image_and_dylib_are_the_pinned_files(self):
        self.assertEqual(B.sha256_file(BASE / "root.apfs"), B.BASE_ROOT_APFS_SHA256)
        self.assertEqual(B.sha256_file(DYLIB), B.DYLIB_SHA256)
        self.assertEqual(B.sha256_file(OUT / "root/lib/libhakios.dylib"), B.DYLIB_SHA256)

    def test_the_tree_differs_from_nat096s_in_exactly_the_three_files_and_lib_dir(self):
        added, removed, changed = B.tree_diff(self.before, self.after)
        # tree_diff returns sorted paths (ASCII: the capital L of LaunchDaemons sorts before the lowercase names)
        self.assertEqual(added, ["LaunchDaemons/com.apple.backboardd.plist", "etc/inject.conf", "lib", "lib/libhakios.dylib"])
        self.assertEqual((removed, changed), ([], []))
        self.assertEqual(sum(1 for v in self.before.values() if v[0] == "file"), 25)
        self.assertEqual(sum(1 for v in self.after.values() if v[0] == "file"), 28)

    def test_inject_conf_bytes_and_modes(self):
        self.assertEqual((OUT / "root/etc/inject.conf").read_bytes(),
                         b"/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system\n")
        self.assertEqual(self.after["lib/libhakios.dylib"][1], 0o755)
        self.assertEqual(self.after["etc/inject.conf"][1], 0o644)

    def test_inject_conf_library_is_the_dylibs_install_name(self):
        data = (DYLIB).read_bytes()
        self.assertEqual(MA.parse_macho(data)["install_name"], (OUT / "root/etc/inject.conf").read_text().split()[0])
        self.assertEqual("/redwood/" + "lib/libhakios.dylib", MA.parse_macho(data)["install_name"])

    def test_every_injected_name_is_the_program_of_a_job_in_the_image(self):
        programs = set()
        for f in (OUT / "root/LaunchDaemons").glob("*.plist"):
            d = plistlib.loads(f.read_bytes())
            programs.add(Path((d.get("ProgramArguments") or [d.get("Program")])[0]).name)
        names = (OUT / "root/etc/inject.conf").read_text().split()[1:]
        self.assertEqual(names, ["backboardd", "containermanagerd", "containermanagerd_system"])
        self.assertEqual([n for n in names if n not in programs], [])

    def test_backboardd_plist_is_apples_plus_the_error_path(self):
        made = (OUT / "root/LaunchDaemons/com.apple.backboardd.plist").read_bytes()
        a, b = plistlib.loads(APPLE.read_bytes()), plistlib.loads(made)
        self.assertEqual(b.pop("StandardErrorPath"), "/dev/console")
        self.assertEqual(a, b)
        self.assertEqual(plistlib.loads(made)["ProgramArguments"], ["/usr/libexec/backboardd"])
        self.assertEqual(plistlib.loads(made)["UserName"], "mobile")

    def test_image_record_matches_the_files_and_the_readback_was_clean(self):
        img = OUT / "root.apfs"
        self.assertEqual(self.rec["root_apfs"]["sha256"], B.sha256_file(img))
        self.assertEqual(self.rec["root_apfs"]["bytes"], img.stat().st_size)
        self.assertEqual(img.stat().st_size, 4194304)  # the md0 region of the image is this size
        rb = self.rec["kernel_apfs_lib_readback"]
        self.assertEqual((rb["mismatches"], rb["files_compared"], rb["local_files"]), ([], 28, 28))
        self.assertEqual(self.rec["verify_content"]["exit"], 0)

    def test_the_donor_init_buffer_holds_the_list(self):
        self.assertLess(len((OUT / "root/etc/inject.conf").read_bytes()), 4096)  # init.c reads it into a 4096-byte buffer


if __name__ == "__main__":
    unittest.main()
