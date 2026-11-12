#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-110 host tests: Stage C2 root builder, build wrapper, payload verification,
analyze_nat110.py (SpringBoa + service spawned + quiet launchd), derive110.py,
and session_nat110.py gate/registry checks. Host-only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent

ROOT110 = ROOT / "artifacts/nat-110/pid1-sc2-hb/root.apfs"
ROOT110_JSON = ROOT / "artifacts/nat-110/pid1-sc2-hb/build.json"
JOBS108_DIR = ROOT / "artifacts/nat-108/pid1-sc1-hb/root/LaunchDaemons"
JOBS106_DIR = ROOT / "artifacts/nat-106/pid1-sb2-hb/root/LaunchDaemons"
PKG110_JSON = ROOT / "artifacts/nat-110/package-001/package.json"
BUILD110 = ROOT / "artifacts/nat-110/build-001/loader-diag-xnu-sc2-md1/Image.payload"
BUILD108 = ROOT / "artifacts/nat-108/build-001/loader-diag-xnu-sc1-md1/Image.payload"
BUILD110_JSON = ROOT / "artifacts/nat-110/build-001/build.json"
NAT105_ARCHIVE = ROOT / "artifacts/nat-105/run-001/archive"
NAT109_ARCHIVE = ROOT / "artifacts/nat-109/run-001/archive"
SCRATCH = ROOT / "artifacts/nat-110/tmp"

PAYLOAD_LEN = 26134288


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RB = load("nat110_test_root", HERE / "build_sc2_hb_root.py")
B = load("nat110_test_build", HERE / "build.py")
D = load("nat110_test_derive", HERE / "derive110.py")
AN = load("nat110_test_analyze", HERE / "analyze_nat110.py")
S110 = load("nat110_test_session", HERE / "session_nat110.py")


def make_scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


class TestStageC2RootBuilder(unittest.TestCase):
    def _make_fake_base(self, root_dir):
        base = root_dir / "base"
        b_root = base / "root"
        (b_root / "etc").mkdir(parents=True)
        (b_root / "LaunchDaemons").mkdir(parents=True)
        for rel in RB.KEEP_REQUIRED:
            p = b_root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"keep-" + rel.encode())
        for name in RB.PRUNE_PLISTS:
            (b_root / "LaunchDaemons" / name).write_bytes(b"prune-" + name.encode())
        b_root_files = sum(1 for v in RB.tree(b_root).values() if v[0] == "file")
        apfs = base / "root.apfs"
        apfs.write_bytes(b"FAKE-SC1-APFS")
        tools = root_dir / "tools"
        tools.mkdir()
        mkapfs = tools / "mkapfs.py"
        verify = tools / "verify.py"
        apfstool = tools / "apfs-tool"
        for t in (mkapfs, verify, apfstool):
            t.write_bytes(b"#!/bin/sh\n")
        return base, b_root_files, sha(apfs.read_bytes()), mkapfs, verify, apfstool

    def test_constants_and_cli_help(self):
        self.assertEqual(RB.SC1_HB_FILE_COUNT, 423)
        self.assertEqual(RB.MD0_BYTES, 4194304)
        r = subprocess.run(
            [sys.executable, "-B", str(HERE / "build_sc2_hb_root.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("Stage C2 + heartbeat 4 MiB md0", r.stdout)

    def test_synthetic_build_happy_and_refusals(self):
        d = make_scratch("rb110_")
        try:
            base, base_count, base_sha, mkapfs, verify, apfstool = self._make_fake_base(d)
            out = d / "out"
            out.mkdir()
            (out / "stale.txt").write_bytes(b"old")

            state = {
                "mkapfs_rc": 0,
                "mkapfs_bytes": 16,
                "verify_rc": 0,
                "cat_bad": False,
                "mode_bad": False,
                "skip_census": False,
            }

            def fake_run(argv, **kw):
                argv_s = [str(x) for x in argv]
                if "mkapfs.py" in argv_s[2]:
                    img_p = Path(argv_s[argv_s.index("-o") + 1])
                    img_p.write_bytes(b"Z" * state["mkapfs_bytes"])
                    return SimpleNamespace(
                        returncode=state["mkapfs_rc"],
                        stdout="line0\nmkapfs: built\n",
                        stderr="M" + ("N" * 600),
                    )
                if "verify.py" in argv_s[2]:
                    return SimpleNamespace(
                        returncode=state["verify_rc"],
                        stdout="V" + ("W" * 300),
                        stderr="X" + ("Y" * 600),
                    )
                if argv_s[0].endswith("apfs-tool") and argv_s[1] == "census":
                    cur_root = Path(argv_s[2]).parent / "root"
                    lines = [
                        "header",
                        "/bad_parts\t8\t644",
                        "relative\t8\t644\t0\t0\t0\t0",
                        "path\tkind\tmode\tuid\tgid\tsz\tino",
                    ]
                    for p in sorted(cur_root.rglob("*")):
                        rel = p.relative_to(cur_root).as_posix()
                        if p.is_dir():
                            lines.append("/%s\t4\t755\t0\t0\t0\t0" % rel)
                        elif p.is_file():
                            if state["skip_census"] and rel == "bin/hb":
                                continue
                            m = p.stat().st_mode & 0o7777
                            if state["mode_bad"] and rel == "bin/hb":
                                m = m ^ 0o011
                            lines.append("/%s\t8\t%o\t0\t0\t0\t0" % (rel, m))
                    return SimpleNamespace(returncode=0, stdout="\n".join(lines) + "\n", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_subproc_run(argv, **kw):
                argv_s = [str(x) for x in argv]
                self.assertEqual(kw.get("timeout"), 60)
                cur_root = Path(argv_s[2]).parent / "root"
                rel = argv_s[3].lstrip("/")
                data = (cur_root / rel).read_bytes()
                if state["cat_bad"] and rel == "bin/hb":
                    data = b"CORRUPT"
                return SimpleNamespace(returncode=0, stdout=data, stderr=b"")

            old_umask = os.umask(0o077)
            try:
                with mock.patch.object(RB, "ROOT", d), \
                     mock.patch.object(RB, "SC1_HB_ROOT_APFS_SHA256", base_sha), \
                     mock.patch.object(RB, "SC1_HB_FILE_COUNT", base_count), \
                     mock.patch.object(RB, "MD0_BYTES", 16), \
                     mock.patch.object(RB, "MKAPFS", mkapfs), \
                     mock.patch.object(RB, "VERIFY", verify), \
                     mock.patch.object(RB, "TOOL", apfstool), \
                     mock.patch.object(RB, "run", side_effect=fake_run), \
                     mock.patch.object(RB.subprocess, "run", side_effect=fake_subproc_run):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        RB.main(["--out", str(out), "--base", str(base)])
                    self.assertIn('\n "root_apfs":', buf.getvalue())
                    summary = json.loads(buf.getvalue())
                    self.assertTrue(summary["kernel_readback_ok"])
                    expected_files = base_count - len(RB.PRUNE_PLISTS) + 1
                    expected_entries = sum(1 for _ in (out / "root").rglob("*"))
                    self.assertEqual(summary["files"], expected_files)
                    self.assertEqual(summary["launchdaemons_plist_count"], 4)
                    self.assertFalse((out / "stale.txt").exists())
                    self.assertEqual((out / "root/etc/quiet").read_bytes(), b"")
                    self.assertEqual((out / "root/etc/quiet").stat().st_mode & 0o777, 0o644)

                    bjson_txt = (out / "build.json").read_text()
                    self.assertTrue(bjson_txt.endswith("\n"))
                    self.assertIn('\n "added":', bjson_txt)
                    self.assertNotIn(str(d) + "/", bjson_txt)
                    bjson = json.loads(bjson_txt)
                    self.assertEqual(bjson["added"], ["etc/quiet"])
                    self.assertEqual(bjson["pruned_plists"], list(RB.PRUNE_PLISTS))
                    self.assertEqual(bjson["root_apfs"]["mkapfs_last_line"], "mkapfs: built")
                    self.assertEqual(len(bjson["verify_content"]["tail"]), 300)
                    self.assertTrue(bjson["verify_content"]["tail"].endswith("Y" * 290))
                    self.assertEqual(bjson["kernel_apfs_lib_readback"]["entries"], expected_entries)
                    self.assertEqual(bjson["kernel_apfs_lib_readback"]["files_compared"], expected_files)
                    self.assertEqual(bjson["kernel_apfs_lib_readback"]["local_files"], expected_files)
                    self.assertEqual(bjson["script_sha256"], RB.sha256_file(HERE / "build_sc2_hb_root.py"))

                    # Missing recipe tool, missing base dir/apfs combinations, sha/count mismatches
                    with self.assertRaises(RB.BuildError):
                        RB.build(out, base, mkapfs=d / "missing", verify=verify, tool=apfstool)
                    with self.assertRaises(RB.BuildError):
                        RB.build(out, d / "no-base", mkapfs=mkapfs, verify=verify, tool=apfstool)
                    only_dir = d / "only_dir"
                    (only_dir / "root").mkdir(parents=True)
                    with self.assertRaises(RB.BuildError):
                        RB.build(out, only_dir, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    only_apfs = d / "only_apfs"
                    only_apfs.mkdir()
                    (only_apfs / "root.apfs").write_bytes(b"X")
                    with self.assertRaises(RB.BuildError):
                        RB.build(out, only_apfs, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    with mock.patch.object(RB, "SC1_HB_ROOT_APFS_SHA256", "0" * 64):
                        with self.assertRaises(RB.BuildError):
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    with mock.patch.object(RB, "SC1_HB_FILE_COUNT", base_count + 1):
                        with self.assertRaises(RB.BuildError):
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)

                    # Pre-existing etc/quiet triggers specific error
                    (base / "root/etc/quiet").write_bytes(b"")
                    with mock.patch.object(RB, "SC1_HB_FILE_COUNT", base_count + 1):
                        with self.assertRaises(RB.BuildError) as cm_q:
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    self.assertIn("unexpectedly contains etc/quiet", str(cm_q.exception))
                    (base / "root/etc/quiet").unlink()

                    # Missing pruned plist & missing KEEP_REQUIRED (keep base_files equal to reach post-count guards)
                    p0 = base / "root/LaunchDaemons" / RB.PRUNE_PLISTS[0]
                    p0_data = p0.read_bytes()
                    p0.unlink()
                    with mock.patch.object(RB, "SC1_HB_FILE_COUNT", base_count - 1):
                        with self.assertRaises(RB.BuildError) as cm_pr:
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    self.assertIn("expected pruned plist missing in base", str(cm_pr.exception))
                    p0.write_bytes(p0_data)

                    keep0 = base / "root" / RB.KEEP_REQUIRED[0]
                    keep0_data = keep0.read_bytes()
                    keep0.unlink()
                    with mock.patch.object(RB, "SC1_HB_FILE_COUNT", base_count - 1):
                        with self.assertRaises(RB.BuildError) as cm_kp:
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    self.assertIn("required file missing after prune", str(cm_kp.exception))
                    keep0.write_bytes(keep0_data)

                    # tree_diff guards (unexpected add / remove / change)
                    orig_tree = RB.tree
                    with mock.patch.object(RB, "tree", side_effect=[orig_tree(base / "root"), {"etc/quiet": ("file", 0o644, "0"), "rogue": ("file", 0o644, "0")}]):
                        with self.assertRaises(RB.BuildError) as cm_add:
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    self.assertIn("unexpected additions", str(cm_add.exception))

                    rem_tree = dict(orig_tree(base / "root"))
                    rem_tree["bin/hb"] = rem_tree["bin/hb"]
                    rem_after = dict(rem_tree)
                    rem_after["etc/quiet"] = ("file", 0o644, "e3b0")
                    for p in RB.PRUNE_PLISTS:
                        rem_after.pop("LaunchDaemons/" + p)
                    rem_after.pop("bin/hb")
                    with mock.patch.object(RB, "tree", side_effect=[rem_tree, rem_after]):
                        with self.assertRaises(RB.BuildError) as cm_rem:
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    self.assertIn("unexpected removals", str(cm_rem.exception))

                    chg_after = dict(rem_tree)
                    chg_after["etc/quiet"] = ("file", 0o644, "e3b0")
                    for p in RB.PRUNE_PLISTS:
                        chg_after.pop("LaunchDaemons/" + p)
                    chg_after["bin/hb"] = ("file", 0o755, "modified")
                    with mock.patch.object(RB, "tree", side_effect=[rem_tree, chg_after]):
                        with self.assertRaises(RB.BuildError) as cm_chg:
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    self.assertIn("unexpected modifications", str(cm_chg.exception))

                    # mkapfs & verify tail[-600:] exactness + size check
                    state["mkapfs_rc"] = 1
                    with self.assertRaises(RB.BuildError) as cm_mk:
                        RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    msg_mk = str(cm_mk.exception)
                    self.assertNotIn("M", msg_mk)
                    self.assertTrue(msg_mk.endswith("N" * 600))
                    state["mkapfs_rc"] = 0

                    state["mkapfs_bytes"] = 8
                    with self.assertRaises(RB.BuildError):
                        RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    state["mkapfs_bytes"] = 16

                    state["verify_rc"] = 1
                    with self.assertRaises(RB.BuildError) as cm_vf:
                        RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                    msg_vf = str(cm_vf.exception)
                    self.assertNotIn("X", msg_vf)
                    self.assertTrue(msg_vf.endswith("Y" * 600))
                    state["verify_rc"] = 0

                    for key in ("cat_bad", "mode_bad", "skip_census"):
                        state[key] = True
                        with self.assertRaises(RB.BuildError):
                            RB.build(out, base, mkapfs=mkapfs, verify=verify, tool=apfstool)
                        state[key] = False

                    # main() exits cleanly via SystemExit on BuildError
                    with mock.patch.object(RB, "SC1_HB_ROOT_APFS_SHA256", "bad"):
                        with self.assertRaises(SystemExit) as cm_exit:
                            RB.main(["--out", str(out), "--base", str(base)])
                    self.assertIn("build_sc2_hb_root:", str(cm_exit.exception))
            finally:
                os.umask(old_umask)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_real_sc2_root_apfs_and_contents(self):
        self.assertTrue(ROOT110.is_file(), "missing artifacts/nat-110/pid1-sc2-hb/root.apfs")
        rec = json.loads(ROOT110_JSON.read_text())
        self.assertEqual(rec["base"]["files"], 423)
        self.assertEqual(rec["files"], 396)
        self.assertEqual(rec["launchdaemons_plist_count"], 377)
        self.assertEqual(rec["added"], ["etc/quiet"])
        self.assertEqual(len(rec["pruned_plists"]), 28)
        self.assertEqual(rec["kernel_apfs_lib_readback"]["files_compared"], 396)
        self.assertEqual(rec["kernel_apfs_lib_readback"]["local_files"], 396)
        self.assertEqual(rec["kernel_apfs_lib_readback"]["mismatches"], [])
        self.assertEqual(sha(ROOT110.read_bytes()), B.MD0_SHA256)

        root = ROOT110.parent / "root"
        self.assertEqual((root / "etc/quiet").read_bytes(), b"")
        self.assertEqual((root / "etc/quiet").stat().st_mode & 0o777, 0o644)
        for name in RB.PRUNE_PLISTS:
            self.assertFalse((root / "LaunchDaemons" / name).exists(), name)
        for rel in RB.KEEP_REQUIRED:
            self.assertTrue((root / rel).is_file(), rel)
        self.assertTrue((root / "LaunchDaemons/com.apple.UserEventAgent-System.plist").is_file())


class TestBuild110(unittest.TestCase):
    def test_cli_help_cmdline_and_default_timings(self):
        r = subprocess.run(
            [
                sys.executable,
                "-B",
                str(HERE / "build.py"),
                "--check-only",
                "--loader-source",
                str(ROOT / "artifacts/nat-020/build-003/source"),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("--ramdisk", r.stderr)
        self.assertEqual(B.cmdline_with_fb_diff("a b"), "a b fb_diff=1")
        with self.assertRaises(SystemExit):
            B.cmdline_with_fb_diff("a fb_diff=1 b")

        src = ["build.py", "--out", "o"]
        got = B.with_default_timings(src)
        self.assertEqual(src, ["build.py", "--out", "o"])
        self.assertEqual(got, ["build.py", "--out", "o", "--return-after-s", "63", "--deadline-s", "365"])
        self.assertEqual(
            B.with_default_timings(["build.py", "--return-after-s", "60", "--deadline-s", "360"]),
            ["build.py", "--return-after-s", "60", "--deadline-s", "360"],
        )

    def test_main_out_check_only_and_refusals(self):
        self.assertEqual(B.MD0_BYTES, 4194304)
        self.assertEqual(B.BURST_NEW, 4096)
        self.assertEqual(B.TAIL_RETURN_NEW, 524288)
        self.assertEqual(B.RETURN_SETTLE_WAITS, 10)
        self.assertEqual(B.RETURN_AFTER_NEW, 63)
        self.assertEqual(B.DEADLINE_NEW, 365)

        d = make_scratch("b110_")
        try:
            saved_snap = (
                B.b106.NAME,
                B.b106.NEW_TAG,
                B.b106.MD0_SHA256,
                B.b106.MD0_BYTES,
                B.b106.BURST_NEW,
                B.b106.TAIL_RETURN_NEW,
                B.b106.RETURN_SETTLE_WAITS,
                B.b67.APPEND,
            )
            out = d / "b1"
            out.mkdir()
            valid_cmd = "rd=md1 nat_attempt=NAT110-sc2 loader_return_after=63 fb_diff=1 xrd=md0"

            def fake_b106_main():
                self.assertIn("--return-after-s", sys.argv)
                self.assertEqual(sys.argv[sys.argv.index("--return-after-s") + 1], "63")
                self.assertIn("--deadline-s", sys.argv)
                self.assertEqual(sys.argv[sys.argv.index("--deadline-s") + 1], "365")
                self.assertEqual(B.b67.APPEND, saved_snap[7] + " fb_diff=1")
                self.assertEqual(B.b106.NAME, B.NAME)
                self.assertEqual(B.b106.NEW_TAG, B.NEW_TAG)
                self.assertEqual(B.b106.MD0_SHA256, B.MD0_SHA256)
                self.assertEqual(B.b106.MD0_BYTES, B.MD0_BYTES)
                self.assertEqual(B.b106.BURST_NEW, B.BURST_NEW)
                self.assertEqual(B.b106.TAIL_RETURN_NEW, B.TAIL_RETURN_NEW)
                self.assertEqual(B.b106.RETURN_SETTLE_WAITS, B.RETURN_SETTLE_WAITS)
                (out / "build.json").write_text(
                    json.dumps(
                        {
                            "nat106_sources": {"build.py": "abc"},
                            "nat106_note": "old",
                            "nat106_changes": {
                                "cmdline": valid_cmd,
                                "md0_sha256": B.MD0_SHA256,
                                "md0_bytes": B.MD0_BYTES,
                                "glue62_impl_sha256": "gsha",
                            },
                        }
                    )
                )

            orig_argv = ["build.py", "--out", str(out), "--loader-source", "src", "--ramdisk", "r.apfs"]
            with mock.patch.object(sys, "argv", list(orig_argv)):
                with mock.patch.object(B.b106, "main", side_effect=fake_b106_main):
                    B.main()
                self.assertEqual(sys.argv, orig_argv)
            self.assertEqual(
                saved_snap,
                (
                    B.b106.NAME,
                    B.b106.NEW_TAG,
                    B.b106.MD0_SHA256,
                    B.b106.MD0_BYTES,
                    B.b106.BURST_NEW,
                    B.b106.TAIL_RETURN_NEW,
                    B.b106.RETURN_SETTLE_WAITS,
                    B.b67.APPEND,
                ),
            )
            bjson_txt = (out / "build.json").read_text()
            self.assertIn('\n "nat110_changes":', bjson_txt)
            bj = json.loads(bjson_txt)
            self.assertNotIn("nat106_sources", bj)
            self.assertNotIn("nat106_changes", bj)
            self.assertNotIn("nat106_note", bj)
            self.assertEqual(bj["nat110_changes"]["cmdline"], valid_cmd)
            self.assertEqual(bj["nat110_changes"]["cmdline_bytes"], len(valid_cmd))
            self.assertEqual(bj["nat110_changes"]["fb_diff"], 1)
            self.assertEqual(bj["nat110_changes"]["return_after_s"], 63)
            self.assertEqual(bj["nat110_changes"]["deadline_s"], 365)
            self.assertEqual(bj["nat110_changes"]["glue62_impl_sha256"], "gsha")
            self.assertEqual(bj["nat110_sources"]["build.py"], B.sha((HERE / "build.py").read_bytes()))

            # Check exception restoration
            with mock.patch.object(sys, "argv", list(orig_argv)):
                with mock.patch.object(B.b106, "main", side_effect=RuntimeError("boom")):
                    with self.assertRaises(RuntimeError):
                        B.main()
                self.assertEqual(sys.argv, orig_argv)
            self.assertEqual(B.b67.APPEND, saved_snap[7])

            # Early returns: --check-only and no --out
            with mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", str(out)]):
                with mock.patch.object(B.b106, "main"):
                    B.main()
            with mock.patch.object(sys, "argv", ["build.py", "--ramdisk", "r.apfs"]):
                with mock.patch.object(B.b106, "main"):
                    B.main()

            # Refusals + 255 byte boundary
            max255 = ("a" * (255 - len(" loader_return_after=63 fb_diff=1"))) + " loader_return_after=63 fb_diff=1"
            self.assertEqual(len(max255), 255)
            with mock.patch.object(sys, "argv", list(orig_argv)):
                def write_ok255():
                    (out / "build.json").write_text(json.dumps({"nat106_changes": {"cmdline": max255}}))
                with mock.patch.object(B.b106, "main", side_effect=write_ok255):
                    B.main()

            bad_cmds = [
                "rd=md1 loader_return_after=63",
                "rd=md1 fb_diff=1",
                ("a" * (256 - len(" loader_return_after=63 fb_diff=1"))) + " loader_return_after=63 fb_diff=1",
            ]
            for bad in bad_cmds:
                with mock.patch.object(sys, "argv", list(orig_argv)):
                    def write_bad(cmd=bad):
                        (out / "build.json").write_text(json.dumps({"nat106_changes": {"cmdline": cmd}}))
                    with mock.patch.object(B.b106, "main", side_effect=write_bad):
                        with self.assertRaises(SystemExit):
                            B.main()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_real_build_payload_and_package(self):
        self.assertTrue(BUILD110.is_file(), "missing Image.payload for NAT-110")
        p110 = BUILD110.read_bytes()
        p108 = BUILD108.read_bytes()
        self.assertEqual(len(p110), PAYLOAD_LEN)
        self.assertEqual(len(p108), PAYLOAD_LEN)

        bj = json.loads(BUILD110_JSON.read_text())
        ch = bj["nat110_changes"]
        self.assertEqual(ch["image_name"], "loader-diag-xnu-sc2-md1")
        self.assertEqual(ch["cmdline_tag"], "nat_attempt=NAT110-sc2")
        self.assertEqual(ch["fb_diff"], 1)
        self.assertEqual(ch["return_after_s"], 63)
        self.assertEqual(ch["deadline_s"], 365)
        self.assertEqual(ch["cmdline_bytes"], 246)
        self.assertEqual(ch["md0_sha256"], B.MD0_SHA256)
        self.assertIn("loader_return_after=63", ch["cmdline"].split())
        self.assertIn("fb_diff=1", ch["cmdline"].split())
        self.assertEqual(ch["glue62_impl_sha256"], "7fa35d764441bca2ce000408a2fea17672c149a45129047224c70880dcc71d60")

        self.assertIn(ch["cmdline"].encode() + b"\x00", p110)
        self.assertNotIn(b"NAT108-sc1", p110)
        self.assertNotIn(b"loader_return_after=60", p110)

        pkg = json.loads(PKG110_JSON.read_text())
        img_rec = pkg["images"]["loader-diag-xnu-sc2-md1"]
        self.assertEqual(img_rec["payload_sha256"], sha(p110))
        self.assertEqual(img_rec["payload_bytes"], PAYLOAD_LEN)
        self.assertEqual(img_rec["recovery_bytes"], 100663296)


class TestAnalyze110(unittest.TestCase):
    def test_constants_row_is_springboard_and_spawned_regex(self):
        self.assertEqual(AN.TAIL_RETURN_110, 524288)
        for yes in (
            {"cmd": "/System/Library/CoreServices/SpringBoard.app/SpringBoard"},
            {"cmd": "/System/Library/CoreServices/SpringBoard.app/SpringBoa"},
            {"cmd": "SpringBoar --arg"},
            {"cmd": "SpringBo"},
            {"cmd": "SpringBoard"},
        ):
            self.assertTrue(AN._row_is_springboard(yes), yes)
        for no in ({}, {"cmd": ""}, {"cmd": "   "}, {"cmd": "SpringB"}, {"cmd": "backboardd"}, {"cmd": "SpringBoardX"}):
            self.assertFalse(AN._row_is_springboard(no), no)

        m_xp = AN.SPAWNED_110.match("xpcproxy spawned with pid 18")
        m_sv = AN.SPAWNED_110.match("service spawned with pid 13")
        self.assertIsNotNone(m_xp)
        self.assertEqual(m_xp.group(1), "18")
        self.assertIsNotNone(m_sv)
        self.assertEqual(m_sv.group(1), "13")
        self.assertIsNone(AN.SPAWNED_110.match("other spawned with pid 9"))

    def test_patched_analyzers_restores_on_exception(self):
        orig_sb = AN.A108._row_is_springboard
        orig_sp = AN.A108.A89.SPAWNED
        self.assertIsNot(orig_sb, AN._row_is_springboard)
        self.assertIsNot(orig_sp, AN.SPAWNED_110)
        try:
            with AN.patched_analyzers():
                self.assertIs(AN.A108._row_is_springboard, AN._row_is_springboard)
                self.assertIs(AN.A108.A89.SPAWNED, AN.SPAWNED_110)
                raise RuntimeError("abort")
        except RuntimeError:
            pass
        self.assertIs(AN.A108._row_is_springboard, orig_sb)
        self.assertIs(AN.A108.A89.SPAWNED, orig_sp)

    def test_stage_c_quiet_and_non_quiet(self):
        jobs = [
            {"label": "com.apple.SpringBoard", "program": "/System/Library/CoreServices/SpringBoard.app/SpringBoard", "self_start": True, "heartbeat": False},
            {"label": "com.apple.backboardd", "program": "/usr/libexec/backboardd", "self_start": True, "heartbeat": False},
        ]
        # Default args keep hole_bytes=0, gap_bytes=0 and detect etc_quiet_active=True
        r_def = AN.analyze_stage_c_text(
            "  PID TTY TIME CMD\n   13 ?? 0:01.00 SpringBoa\n   18 ?? 0:01.00 backboardd\nhakios: hi\n",
            jobs,
        )
        self.assertEqual(r_def["row"], 5)
        self.assertTrue(r_def["facts"]["etc_quiet_active"])
        self.assertEqual(r_def["facts"]["hole_bytes"], 0)
        self.assertEqual(r_def["facts"]["gap_bytes"], 0)
        self.assertTrue(r_def["facts"]["springboard_alive_in_last_list"])

        r_hg = AN.analyze_stage_c_text(
            "  PID TTY TIME CMD\n   13 ?? 0:01.00 SpringBoa\n   18 ?? 0:01.00 backboardd\n",
            jobs,
            hole_bytes=12,
            gap_bytes=34,
        )
        self.assertEqual(r_hg["facts"]["hole_bytes"], 12)
        self.assertEqual(r_hg["facts"]["gap_bytes"], 34)

        non_quiet_c4 = (
            "com.apple.xpc.launchd|1970-01-01 00:03:11.000000 (system/com.apple.SpringBoard) <Notice>: service spawned with pid 13\n"
            "com.apple.xpc.launchd|1970-01-01 00:03:11.100000 (system/com.apple.backboardd) <Notice>: xpcproxy spawned with pid 18\n"
            "  PID TTY TIME CMD\n"
            "   18 ?? 0:01.00 backboardd\n"
        )
        r_c4 = AN.analyze_stage_c_text(non_quiet_c4, jobs)
        self.assertEqual(r_c4["row"], 4)
        self.assertFalse(r_c4["facts"]["etc_quiet_active"])
        self.assertEqual(r_c4["facts"]["springboard_spawns"], [{"clock": 191.0, "pid": 13}])

        if NAT109_ARCHIVE.is_dir():
            r109 = AN.analyze_stage_c(NAT109_ARCHIVE, JOBS108_DIR)
            self.assertEqual(r109["row"], 6)
            self.assertEqual(r109["name"], "fb-swaps-no-diff")
            self.assertTrue(r109["facts"]["springboard_alive_in_last_list"])
            self.assertEqual(len(r109["facts"]["springboard_spawns"]), 1)
            self.assertEqual(r109["facts"]["springboard_spawns"][0]["pid"], 13)
            self.assertFalse(r109["facts"]["etc_quiet_active"])

        d = make_scratch("empty_arch_")
        try:
            arch_dir = d / "arch"
            arch_dir.mkdir()
            r0 = AN.analyze_stage_c(arch_dir, JOBS108_DIR)
            self.assertEqual(r0["row"], 0)
            self.assertNotIn("etc_quiet_active", r0["facts"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_cli_and_chain_modes(self):
        d = make_scratch("ancli_")
        try:
            for mode, prefix, jdir in (
                ("stage-c", "row C2 ", JOBS106_DIR),
                ("stage-b", "row B2 ", JOBS106_DIR),
                ("hb", "row H", JOBS106_DIR),
                ("stage-a", "row A", JOBS106_DIR),
            ):
                out_f = d / ("%s.json" % mode)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = AN.main(["--mode", mode, "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(jdir), "--out", str(out_f)])
                self.assertEqual(rc, 0)
                self.assertTrue(buf.getvalue().startswith(prefix), (mode, buf.getvalue()))
                out_txt = out_f.read_text()
                self.assertIn('\n "row":', out_txt)
                self.assertNotIn('\n  "row":', out_txt)

            # Without --out runs cleanly without writing
            buf_no = io.StringIO()
            with contextlib.redirect_stdout(buf_no):
                self.assertEqual(AN.main(["--mode", "stage-c", "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(JOBS106_DIR)]), 0)
            self.assertTrue(buf_no.getvalue().startswith("row C2 "))

            # Subprocess execution of analyze_nat110.py exercises __main__ entrypoint
            cli_sub = subprocess.run(
                [sys.executable, "-B", str(HERE / "analyze_nat110.py"), "--mode", "stage-c", "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(JOBS106_DIR)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(cli_sub.returncode, 0)
            self.assertTrue(cli_sub.stdout.startswith("row C2 "))

            with mock.patch.object(AN.A108, "analyze_chain", return_value={"row": 1, "stage_c": {"facts": {"launchd_console_lines": 0}}, "_exit_code": 5}) as mc:
                buf2 = io.StringIO()
                with contextlib.redirect_stdout(buf2):
                    rc2 = AN.main(
                        [
                            "--mode", "chain",
                            "--archive", str(NAT105_ARCHIVE),
                            "--events", "e",
                            "--report", "r",
                            "--delivery", "del",
                            "--root", "root",
                            "--size", "1",
                            "--sha256", "ab",
                            "--log-out", "lg",
                            "--out", str(d / "co.json"),
                            "--allow-synthetic",
                        ]
                    )
            self.assertEqual(rc2, 5)
            self.assertEqual(mc.call_args.kwargs["image"], AN.IMAGE_110)
            self.assertTrue(mc.call_args.kwargs["allow_synthetic"])
            self.assertIn('\n "row": 1', buf2.getvalue())
            self.assertNotIn('\n  "row": 1', buf2.getvalue())
            parsed = json.loads(buf2.getvalue())
            self.assertTrue(parsed["stage_c"]["facts"]["etc_quiet_active"])

            # Chain result without stage_c dict must not crash
            with mock.patch.object(AN.A108, "analyze_chain", return_value={"row": 0, "_exit_code": 2}):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        AN.main(["--mode", "chain", "--archive", str(NAT105_ARCHIVE), "--events", "e", "--report", "r", "--delivery", "del", "--root", "root", "--size", "1", "--sha256", "ab"]),
                        2,
                    )

            # All 6 required chain options checked before invoking analyze_chain
            base_chain = ["--mode", "chain", "--archive", str(NAT105_ARCHIVE), "--events", "e", "--report", "r", "--delivery", "del", "--root", "root", "--size", "1", "--sha256", "ab"]
            with mock.patch.object(AN, "analyze_chain", side_effect=AssertionError("must not call analyze_chain")):
                for missing in ("--events", "--report", "--delivery", "--root", "--size", "--sha256"):
                    idx = base_chain.index(missing)
                    err_buf = io.StringIO()
                    with mock.patch.object(sys, "stderr", new=err_buf):
                        with self.assertRaises(SystemExit):
                            AN.main(base_chain[:idx] + base_chain[idx + 2:])
                    self.assertIn("--mode chain requires " + missing, err_buf.getvalue())

            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    AN.main(["--mode", "stage-c", "--archive", str(NAT105_ARCHIVE)])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDeriveAndSession110(unittest.TestCase):
    def test_derive_check_write_drift_and_refusals(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = D.main(["--check"])
        self.assertEqual(rc, 0)
        self.assertIn("9 substitutions", buf.getvalue())

        d = make_scratch("drv110_")
        try:
            out_py = d / "session_nat110.py"
            with mock.patch.object(D, "OUT", out_py):
                buf_w = io.StringIO()
                with contextlib.redirect_stdout(buf_w):
                    self.assertEqual(D.main([]), 0)
                wjson = json.loads(buf_w.getvalue())
                self.assertEqual(len(wjson["substitutions"]), 9)
                self.assertEqual(wjson["sha256"], sha(out_py.read_bytes()))
                out_py.write_text("# drifted\n")
                with mock.patch.object(sys, "stderr", new=io.StringIO()):
                    self.assertEqual(D.main(["--check"]), 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        saved = (D.SRC_SHA256, D.PAYLOAD_LEN, D.OLD_SHA)
        try:
            D.SRC_SHA256 = "0" * 64
            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                self.assertEqual(D.main(["--check"]), 2)
            D.SRC_SHA256 = saved[0]
            D.PAYLOAD_LEN = 123
            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                self.assertEqual(D.main(["--check"]), 2)
            D.PAYLOAD_LEN = saved[1]
            D.OLD_SHA = "badsha"
            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                self.assertEqual(D.main(["--check"]), 2)
        finally:
            D.SRC_SHA256, D.PAYLOAD_LEN, D.OLD_SHA = saved

    def test_session_gate_and_registry(self):
        cfg = S110.IMAGES["loader-diag-xnu-sc2-md1"]
        self.assertGreaterEqual(cfg["RX_CAP_S"], S110.DELIVER_S + S110.DELIVER_MARGIN_S)
        dec = S110.gate("loader-diag-xnu-sc2-md1", cfg)
        self.assertTrue(dec.name.startswith("0042-nat110-loader-diag-xnu-sc2-md1-single-run-"))

        d = make_scratch("gate110_")
        try:
            fake_root = d / "repo"
            (fake_root / "state").mkdir(parents=True)
            req = {tid: {"id": tid, "status": "done"} for tid in S110.REQUIRED_DONE}
            st = {
                "project": {
                    "permissions": {"native": True},
                    "permission_decisions": [{"scope": "native", "value": True, "decision": "docs/decisions/" + dec.name}],
                },
                "tasks": list(req.values()),
            }
            lab_json = fake_root / "state/lab.json"
            lab_json.write_text(json.dumps(st))
            with mock.patch.object(S110, "ROOT", fake_root):
                self.assertIsNone(S110.registry_blocker(dec))

                st["project"]["permissions"]["native"] = False
                lab_json.write_text(json.dumps(st))
                self.assertIsNotNone(S110.registry_blocker(dec))

                st["project"]["permissions"]["native"] = True
                req["NAT-110"]["status"] = "in_progress"
                lab_json.write_text(json.dumps(st))
                self.assertIn("NAT-110", S110.registry_blocker(dec))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
