#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-108 host tests: Stage C1 + hb root builder, build wrapper, payload byte comparison against NAT-106,
analyze_nat108.py (C0-C7 ladder + CLI), derive108.py, and session_nat108.py gate checks. Host-only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import plistlib
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

ROOT108 = ROOT / "artifacts/nat-108/pid1-sc1-hb/root.apfs"
ROOT108_JSON = ROOT / "artifacts/nat-108/pid1-sc1-hb/build.json"
JOBS108_DIR = ROOT / "artifacts/nat-108/pid1-sc1-hb/root/LaunchDaemons"
JOBS106_DIR = ROOT / "artifacts/nat-106/pid1-sb2-hb/root/LaunchDaemons"
PKG108 = ROOT / "artifacts/nat-108/package-001/package.json"
BUILD108 = ROOT / "artifacts/nat-108/build-001/loader-diag-xnu-sc1-md1/Image.payload"
BUILD106 = ROOT / "artifacts/nat-106/build-001/loader-diag-xnu-sb2-md1/Image.payload"
BUILD108_JSON = ROOT / "artifacts/nat-108/build-001/build.json"
NAT105_ARCHIVE = ROOT / "artifacts/nat-105/run-001/archive"
SCRATCH = ROOT / "artifacts/nat-108/tmp"

PAYLOAD_LEN = 26134288
CMDLINE_OFF = 0x48
CMDLINE_LEN = 608


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RB = load("nat108_test_root", HERE / "build_sc1_hb_root.py")
B = load("nat108_test_build", HERE / "build.py")
D = load("nat108_test_derive", HERE / "derive108.py")
AN = load("nat108_test_analyze", HERE / "analyze_nat108.py")
S108 = load("nat108_test_session", HERE / "session_nat108.py")


def make_scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


class TestStageCRootBuilder(unittest.TestCase):
    def test_rewrite_var_skel(self):
        self.assertEqual(RB.ROOT, ROOT)
        sample = (
            "d\t755\t0\t0\t/private/var/db\n"
            "l\t/usr/share/zoneinfo\t/private/var/db/timezone/zoneinfo\n"
            "l\t/var/db/timezone/zoneinfo/US/Pacific\t/private/var/db/timezone/localtime"
        )
        got = RB.rewrite_var_skel(sample, ["mobile/Library/Preferences/a.plist", "root/x.plist"])
        self.assertIn("l\t/usr/share/zoneinfo.default\t/private/var/db/timezone/zoneinfo\n", got)
        self.assertIn("l\t/var/db/timezone/zoneinfo/UTC\t/private/var/db/timezone/localtime\n", got)
        self.assertIn("f\t644\t501\t501\t/private/var/mobile/Library/Preferences/a.plist\t/var/mobile/Library/Preferences/a.plist\n", got)
        self.assertIn("f\t644\t0\t0\t/private/var/root/x.plist\t/var/root/x.plist\n", got)
        self.assertIn("d\t700\t501\t501\t/private/var/mobile/tmp\n", got)
        self.assertIn("d\t1777\t0\t0\t/private/var/db/hakios-metal-cache\n", got)
        self.assertTrue(got.endswith("\n"))

        with self.assertRaises(RB.BuildError) as cm_zi:
            RB.rewrite_var_skel("d\t755\t0\t0\t/private/var/db\n", [])
        self.assertIn("zoneinfo", str(cm_zi.exception))
        with self.assertRaises(RB.BuildError) as cm_tz:
            RB.rewrite_var_skel("l\t/usr/share/zoneinfo\t/private/var/db/timezone/zoneinfo\n", [])
        self.assertIn("found 0", str(cm_tz.exception))

        # No spurious leading newline when zoneinfo+localtime are the entire input without trailing \n,
        # and no double newline when they already end with \n.
        for inp in (
            "l\t/usr/share/zoneinfo\t/private/var/db/timezone/zoneinfo\n"
            "l\t/var/db/timezone/zoneinfo/UTC\t/private/var/db/timezone/localtime",
            "l\t/usr/share/zoneinfo\t/private/var/db/timezone/zoneinfo\n"
            "l\t/var/db/timezone/zoneinfo/UTC\t/private/var/db/timezone/localtime\n",
        ):
            empty_pref = RB.rewrite_var_skel(inp, [])
            self.assertNotIn("\n\nd\t", empty_pref)
            self.assertIn("localtime\nd\t700", empty_pref)

    def test_clean_env(self):
        with mock.patch.dict(os.environ, {"OSLOG": "all", "ALLOW": "wifid", "KEEP_ME": "1"}):
            env = RB._clean_env()
        self.assertNotIn("OSLOG", env)
        self.assertNotIn("ALLOW", env)
        self.assertEqual(env["KEEP_ME"], "1")

    def _make_fake_inputs(self, d):
        base = d / "base"
        base_root = base / "root"
        (base_root / "LaunchDaemons").mkdir(parents=True)
        (base_root / "lib").mkdir()
        (base_root / "bin").mkdir()
        (base_root / "etc").mkdir()
        (base_root / "bin/hb").write_bytes(b"hb")
        (base_root / "etc/rc").write_bytes(b"/redwood/bin/hb &\nexec /sbin/launchd.darwin\n")
        (base_root / "etc/var.skel").write_text(
            "l\t/usr/share/zoneinfo\t/private/var/db/timezone/zoneinfo\n"
            "l\t/var/db/timezone/zoneinfo/US/Pacific\t/private/var/db/timezone/localtime\n"
        )
        bb_apple = plistlib.dumps({"Label": "com.apple.backboardd"})
        bb_job = plistlib.dumps({"Label": "com.apple.backboardd", "StandardErrorPath": "/dev/console"})
        (base_root / "LaunchDaemons/com.apple.backboardd.plist").write_bytes(bb_job)
        (base_root / "LaunchDaemons/com.nat085.ps.plist").write_bytes(b"nat085")
        # Pad base_root to exactly 29 files matching SB2_HB_FILE_COUNT (5 above + 24 below)
        for idx in range(24):
            (base_root / f"etc/f{idx:02d}").write_bytes(b"x")
        base_img = base / "root.apfs"
        base_img.write_bytes(b"FAKEBASE")

        recipe = d / "recipe"
        (recipe / "userland").mkdir(parents=True)
        (recipe / "sysimage/rootfs/System/Library/LaunchDaemons").mkdir(parents=True)
        (recipe / "tools/apfs").mkdir(parents=True)
        (recipe / "apfs-work").mkdir(parents=True)
        (recipe / "sysimage/rootfs/System/Library/LaunchDaemons/com.apple.backboardd.plist").write_bytes(bb_apple)
        (recipe / "sysimage/rootfs/System/Library/LaunchDaemons/com.apple.SpringBoard.plist").write_bytes(b"sb")
        mkjobs = recipe / "userland/mkjobs.py"
        mkjobs.write_bytes(b"# mkjobs")
        for f in (recipe / "tools/apfs/mkapfs.py", recipe / "tools/apfs/verify.py", recipe / "apfs-work/apfs-tool"):
            f.write_bytes(b"tool")

        sb_dylib = d / "libhakios.sb.dylib"
        sb_dylib.write_bytes(b"SBDYLIB")

        var_dir = d / "var"
        for rel in RB.EXPECTED_VAR_FILES:
            p = var_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"plist-" + rel.encode())
        return base, recipe, sb_dylib, var_dir, bb_job

    def test_synthetic_build_happy_and_refusals(self):
        d = make_scratch("rbsyn_")
        try:
            base, recipe, sb_dylib, var_dir, bb_job = self._make_fake_inputs(d)
            out = d / "out"
            with mock.patch.object(RB, "ROOT", d), \
                 mock.patch.object(RB, "SB2_HB_ROOT_APFS_SHA256", sha(b"FAKEBASE")), \
                 mock.patch.object(RB, "MKJOBS_SHA256", sha(b"# mkjobs")), \
                 mock.patch.object(RB, "LIBHAKIOS_SB_SHA256", sha(b"SBDYLIB")), \
                 mock.patch.object(RB, "MD0_BYTES", 16), \
                 mock.patch.object(RB.B99, "check_backboardd_plist") as mock_chk:
                state = {
                    "mkjobs_rc": 0,
                    "mkjobs_stderr": "mkjobs err",
                    "apfs_mode_bad": False,
                    "apfs_data_bad": False,
                    "remove_bb": False,
                    "skip_sb": False,
                    "skip_lsd": False,
                }

                def fake_subproc_run(argv, **kw):
                    argv_s = [str(x) for x in argv]
                    if "mkjobs.py" in argv_s[2]:
                        self.assertEqual(kw.get("timeout"), 120)
                        dest = Path(argv_s[5])
                        if not state["skip_sb"]:
                            (dest / "com.apple.SpringBoard.plist").write_bytes(b"com.apple.SpringBoard")
                        if not state["skip_lsd"]:
                            (dest / "com.apple.lsd.plist").write_bytes(b"com.apple.lsd")
                        if state["remove_bb"]:
                            (dest.parent / "etc/f00").unlink()
                        (dest / "com.apple.backboardd.plist").write_bytes(bb_job)
                        return SimpleNamespace(returncode=state["mkjobs_rc"], stdout="jobs ok\n", stderr=state["mkjobs_stderr"])
                    if argv_s[0].endswith("apfs-tool") and argv_s[1] == "cat":
                        self.assertEqual(kw.get("timeout"), 60)
                        cur_root = Path(argv_s[2]).parent / "root"
                        rel = argv_s[3].lstrip("/")
                        data = (cur_root / rel).read_bytes()
                        if state["apfs_data_bad"] and rel == "bin/hb":
                            data = b"CORRUPT"
                        return SimpleNamespace(returncode=0, stdout=data, stderr=b"")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")

                def fake_rb_run(argv, **kw):
                    argv_s = [str(x) for x in argv]
                    if len(argv_s) >= 3 and "mkapfs.py" in argv_s[2]:
                        img_p = Path(argv_s[argv_s.index("-o") + 1])
                        img_p.write_bytes(b"A" * 16)
                        return SimpleNamespace(returncode=0, stdout="line1\nmkapfs: ok\n", stderr="")
                    if len(argv_s) >= 3 and "verify.py" in argv_s[2]:
                        return SimpleNamespace(returncode=0, stdout="V" * 310, stderr="done\n")
                    if argv_s[0].endswith("apfs-tool") and argv_s[1] == "census":
                        cur_root = Path(argv_s[2]).parent / "root"
                        lines = ["headerline", "path\tkind\tmode\tuid\tgid\tsz\tino"]
                        for p in sorted(cur_root.rglob("*")):
                            if p.is_file():
                                m = p.stat().st_mode & 0o7777
                                if state["apfs_mode_bad"] and p.name == "hb":
                                    m = 0o600
                                lines.append("/%s\t8\t%o\t0\t0\t0\t0" % (p.relative_to(cur_root), m))
                            elif p.is_dir():
                                lines.append("/%s\t4\t755\t0\t0\t0\t0" % p.relative_to(cur_root))
                        return SimpleNamespace(returncode=0, stdout="\n".join(lines) + "\n", stderr="")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")

                with mock.patch.object(RB.subprocess, "run", side_effect=fake_subproc_run), \
                     mock.patch.object(RB, "run", side_effect=fake_rb_run):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        RB.main(["--out", str(out), "--base", str(base), "--recipe", str(recipe),
                                 "--sb-dylib", str(sb_dylib), "--var-dir", str(var_dir)])
                    self.assertEqual(mock_chk.call_count, 1)
                    self.assertIn('\n "root_apfs":', buf.getvalue())
                    summary = json.loads(buf.getvalue())
                    self.assertTrue(summary["kernel_readback_ok"])
                    self.assertEqual(summary["files"], 41)
                    bjson_text = (out / "build.json").read_text()
                    self.assertTrue(bjson_text.endswith("\n"))
                    self.assertIn('\n "added_count":', bjson_text)
                    self.assertNotIn(str(d) + "/", bjson_text)
                    bjson = json.loads(bjson_text)
                    self.assertEqual(bjson["root_apfs"]["mkapfs_last_line"], "mkapfs: ok")
                    self.assertEqual(len(bjson["verify_content"]["tail"]), 300)
                    self.assertTrue(bjson["verify_content"]["tail"].endswith("done"))
                    self.assertEqual(bjson["kernel_apfs_lib_readback"]["local_files"], 41)
                    self.assertEqual(bjson["kernel_apfs_lib_readback"]["entries"], len(list(sorted((out / "root").rglob("*")))) - 0)
                    self.assertEqual((out / "root/lib/libhakios.sb.dylib").stat().st_mode & 0o777, 0o755)
                    self.assertEqual((out / "root/etc/inject.conf").read_bytes(), RB.INJECT_CONF)
                    for rel in RB.EXPECTED_VAR_FILES:
                        self.assertEqual((out / "root/var" / rel).stat().st_mode & 0o777, 0o644)
                    self.assertIn("l\t/var/db/timezone/zoneinfo/UTC\t", (out / "root/etc/var.skel").read_text())

                    # Mode chmod check on var files starting as 0o600 + str paths
                    p_var0 = var_dir / RB.EXPECTED_VAR_FILES[0]
                    os.chmod(p_var0, 0o600)
                    out_ch = d / "out_chmod"
                    rec_ch = RB.build(str(out_ch), str(base), str(recipe), str(sb_dylib), str(var_dir))
                    self.assertEqual((out_ch / "root/var" / RB.EXPECTED_VAR_FILES[0]).stat().st_mode & 0o777, 0o644)
                    self.assertEqual(rec_ch["kernel_apfs_lib_readback"]["files_compared"], 41)
                    os.chmod(p_var0, 0o644)

                    # Re-run against existing out triggers SystemExit via main's BuildError handler
                    with self.assertRaises(SystemExit) as cm_ex:
                        RB.main(["--out", str(out), "--base", str(base), "--recipe", str(recipe),
                                 "--sb-dylib", str(sb_dylib), "--var-dir", str(var_dir)])
                    self.assertIn("build_sc1_hb_root:", str(cm_ex.exception))

                    # Refusals on apfs-tool mode mismatch & data mismatch
                    for key in ("apfs_mode_bad", "apfs_data_bad"):
                        state[key] = True
                        with self.assertRaisesRegex(RB.BuildError, "kernel apfs_lib readback mismatch"):
                            RB.build(d / f"out_{key}", base, recipe, sb_dylib, var_dir)
                        state[key] = False

                    # Refusals on tree_diff checks (removed, mode != 755, missing SpringBoard/lsd plist)
                    state["remove_bb"] = True
                    with self.assertRaisesRegex(RB.BuildError, "unexpected removals from base"):
                        RB.build(d / "out_rem", base, recipe, sb_dylib, var_dir)
                    state["remove_bb"] = False

                    os.chmod(sb_dylib, 0o644)
                    real_chmod = os.chmod
                    with mock.patch.object(RB.os, "chmod", side_effect=lambda p, m, **kw: real_chmod(p, m, **kw) if Path(p).name != "libhakios.sb.dylib" else None):
                        with self.assertRaisesRegex(RB.BuildError, "libhakios.sb.dylib mode 644 != 755"):
                            RB.build(d / "out_sb_mode", base, recipe, sb_dylib, var_dir)
                    os.chmod(sb_dylib, 0o755)

                    state["skip_sb"] = True
                    with self.assertRaisesRegex(RB.BuildError, r"^SpringBoard plist missing$"):
                        RB.build(d / "out_skip_sb", base, recipe, sb_dylib, var_dir)
                    state["skip_sb"] = False

                    state["skip_lsd"] = True
                    with self.assertRaisesRegex(RB.BuildError, r"^lsd plist missing$"):
                        RB.build(d / "out_skip_lsd", base, recipe, sb_dylib, var_dir)
                    state["skip_lsd"] = False

                    # Refusal on mkjobs failure (verifying [-600:] slice), mkapfs failure/wrong size, verify failure, inject_conf > 4096
                    state["mkjobs_rc"] = 1
                    state["mkjobs_stderr"] = "J" * 610
                    with self.assertRaisesRegex(RB.BuildError, r"^mkjobs\.py --rest failed: J{600}$"):
                        RB.build(d / "out_mkj", base, recipe, sb_dylib, var_dir)
                    state["mkjobs_rc"] = 0
                    state["mkjobs_stderr"] = "mkjobs err"

                    with mock.patch.object(RB, "MD0_BYTES", 99):
                        with self.assertRaisesRegex(RB.BuildError, r"^root\.apfs size 16 != 99$"):
                            RB.build(d / "out_sz", base, recipe, sb_dylib, var_dir)

                    with mock.patch.object(RB, "INJECT_CONF", b"x" * 4097):
                        with self.assertRaisesRegex(RB.BuildError, "inject.conf exceeds"):
                            RB.build(d / "out_inj", base, recipe, sb_dylib, var_dir)

                    with mock.patch.object(RB, "INJECT_CONF", b"x" * 4096):
                        rec_4k = RB.build(d / "out_inj_ok", base, recipe, sb_dylib, var_dir)
                        self.assertEqual(len((d / "out_inj_ok/root/etc/inject.conf").read_bytes()), 4096)
                        self.assertEqual(rec_4k["files"], 41)

                    def bad_mkapfs(argv, **kw):
                        if len(argv) >= 3 and "mkapfs.py" in str(argv[2]):
                            return SimpleNamespace(returncode=1, stdout="", stderr="M" * 610)
                        return fake_rb_run(argv, **kw)

                    with mock.patch.object(RB, "run", side_effect=bad_mkapfs):
                        with self.assertRaisesRegex(RB.BuildError, r"^mkapfs\.py failed: M{600}$"):
                            RB.build(d / "out_mke", base, recipe, sb_dylib, var_dir)

                    def bad_verify(argv, **kw):
                        if len(argv) >= 3 and "verify.py" in str(argv[2]):
                            return SimpleNamespace(returncode=1, stdout="", stderr="V" * 610)
                        return fake_rb_run(argv, **kw)

                    with mock.patch.object(RB, "run", side_effect=bad_verify):
                        with self.assertRaisesRegex(RB.BuildError, r"^verify\.py content failed: V{600}$"):
                            RB.build(d / "out_ver", base, recipe, sb_dylib, var_dir)

                    # Missing / corrupt inputs refusals (regex-checked so earlier/later checks cannot mask)
                    with self.assertRaisesRegex(RB.BuildError, "not pinned libhakios.sb.dylib"):
                        RB.build(d / "out_bad_sb", base, recipe, d / "missing.dylib", var_dir)
                    with self.assertRaisesRegex(RB.BuildError, "no_var_dir is missing"):
                        RB.build(d / "out_no_var", base, recipe, sb_dylib, d / "no_var_dir")
                    (var_dir / "extra.plist").write_bytes(b"x")
                    with self.assertRaisesRegex(RB.BuildError, "unexpected var/ files"):
                        RB.build(d / "out_bad_var", base, recipe, sb_dylib, var_dir)
                    (var_dir / "extra.plist").unlink()

                    (recipe / "userland/mkjobs.py").write_bytes(b"BADMKJOBS")
                    with self.assertRaisesRegex(RB.BuildError, "mkjobs.py sha256 mismatch"):
                        RB.build(d / "out_bad_mkj_sha", base, recipe, sb_dylib, var_dir)
                    (recipe / "userland/mkjobs.py").write_bytes(b"# mkjobs")

                    sb_p = recipe / "sysimage/rootfs/System/Library/LaunchDaemons/com.apple.SpringBoard.plist"
                    sb_p.unlink()
                    with self.assertRaisesRegex(RB.BuildError, "SpringBoard plist missing from rootfs"):
                        RB.build(d / "out_no_sb_plist", base, recipe, sb_dylib, var_dir)
                    sb_p.write_bytes(b"sb")

                    rc_orig = (base / "root/etc/rc").read_bytes()
                    (base / "root/etc/rc").write_bytes(b"exec /sbin/launchd.darwin\n")
                    with self.assertRaisesRegex(RB.BuildError, "hb/rc lost"):
                        RB.build(d / "out_no_hb", base, recipe, sb_dylib, var_dir)
                    (base / "root/etc/rc").write_bytes(rc_orig)

                    (recipe / "tools/apfs/mkapfs.py").unlink()
                    with self.assertRaisesRegex(RB.BuildError, "mkapfs.py is missing"):
                        RB.build(d / "out_no_tool", base, recipe, sb_dylib, var_dir)
                    (recipe / "tools/apfs/mkapfs.py").write_bytes(b"tool")

                    (base / "root/etc/extra").write_bytes(b"y")
                    with self.assertRaisesRegex(RB.BuildError, "base tree holds 30 files, not 29"):
                        RB.build(d / "out_bad_cnt", base, recipe, sb_dylib, var_dir)
                    (base / "root/etc/extra").unlink()

            # Missing base / missing root.apfs / bad base sha256
            with self.assertRaisesRegex(RB.BuildError, "has no root.apfs and root/"):
                RB.build(d / "out_nobase", d / "missing_base", recipe, sb_dylib, var_dir)
            (base / "root.apfs").unlink()
            with self.assertRaisesRegex(RB.BuildError, "has no root.apfs and root/"):
                RB.build(d / "out_noimg", base, recipe, sb_dylib, var_dir)
            (base / "root.apfs").write_bytes(b"WRONG")
            with self.assertRaisesRegex(RB.BuildError, "base root.apfs is sha256"):
                RB.build(d / "out_badsha", base, recipe, sb_dylib, var_dir)

            hp = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build_sc1_hb_root.py"), "--help"],
                                capture_output=True, text=True)
            self.assertEqual(hp.returncode, 0)
            self.assertIn("NAT-108 Stage C1", hp.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @unittest.skipUnless(ROOT108.is_file() and ROOT108_JSON.is_file(), "pid1-sc1-hb root not built")
    def test_built_stage_c_root(self):
        rec = json.loads(ROOT108_JSON.read_text())
        self.assertEqual(rec["root_apfs"]["bytes"], RB.MD0_BYTES)
        self.assertEqual(rec["root_apfs"]["sha256"], B.MD0_SHA256)
        self.assertEqual(rec["files"], 423)
        self.assertEqual(rec["launchdaemons_plist_count"], 405)
        self.assertEqual(rec["kernel_apfs_lib_readback"]["files_compared"], 423)
        self.assertEqual(rec["kernel_apfs_lib_readback"]["mismatches"], [])
        self.assertEqual(sha(ROOT108.read_bytes()), B.MD0_SHA256)

        root = ROOT108.parent / "root"
        self.assertEqual((root / "etc/inject.conf").read_bytes(), RB.INJECT_CONF)
        self.assertLessEqual(len(RB.INJECT_CONF), 4096)
        self.assertEqual((root / "lib/libhakios.sb.dylib").stat().st_mode & 0o777, 0o755)
        self.assertEqual(sha((root / "lib/libhakios.sb.dylib").read_bytes()), RB.LIBHAKIOS_SB_SHA256)
        for rel in RB.EXPECTED_VAR_FILES:
            p = root / "var" / rel
            self.assertTrue(p.is_file(), rel)
            self.assertEqual(p.stat().st_mode & 0o777, 0o644)
        self.assertTrue((root / "LaunchDaemons/com.apple.SpringBoard.plist").is_file())
        self.assertTrue((root / "LaunchDaemons/com.apple.lsd.plist").is_file())
        self.assertTrue((root / "LaunchDaemons/com.nat085.ps.plist").is_file())
        self.assertTrue((root / "bin/hb").is_file())


class TestBuild108(unittest.TestCase):
    def test_cmdline_with_fb_diff(self):
        self.assertEqual(B.cmdline_with_fb_diff("a b"), "a b fb_diff=1")
        with self.assertRaises(SystemExit):
            B.cmdline_with_fb_diff("a fb_diff=1 b")

    def test_main_out_check_only_and_refusals(self):
        self.assertEqual(B.ROOT, ROOT)
        self.assertEqual(B.MD0_BYTES, 4194304)
        self.assertEqual(B.BURST_NEW, 4096)
        self.assertEqual(B.TAIL_RETURN_NEW, 524288)
        self.assertEqual(B.RETURN_SETTLE_WAITS, 10)
        d = make_scratch("bmain_")
        try:
            before_saved = (B.b106.NAME, B.b106.NEW_TAG, B.b106.MD0_SHA256, B.b106.MD0_BYTES,
                            B.b106.BURST_NEW, B.b106.TAIL_RETURN_NEW, B.b106.RETURN_SETTLE_WAITS, B.b67.APPEND)
            out = d / "b1"
            out.mkdir()
            valid_cmd = "rd=md1 nat_attempt=NAT108-sc1 fb_diff=1 xrd=md0"

            def fake_b106_main():
                self.assertIn("--ramdisk", sys.argv)
                self.assertEqual(sys.argv[sys.argv.index("--ramdisk") + 1],
                                 str(B.ROOT / "artifacts/nat-108/pid1-sc1-hb/root.apfs"))
                self.assertEqual(B.b67.APPEND, before_saved[7] + " fb_diff=1")
                self.assertEqual(B.b106.BURST_NEW, B.BURST_NEW)
                self.assertEqual(B.b106.TAIL_RETURN_NEW, B.TAIL_RETURN_NEW)
                self.assertEqual(B.b106.RETURN_SETTLE_WAITS, B.RETURN_SETTLE_WAITS)
                (out / "build.json").write_text(json.dumps({
                    "nat106_sources": {"build.py": "abc"},
                    "nat106_note": "old",
                    "nat106_changes": {
                        "cmdline": valid_cmd,
                        "md0_sha256": B.MD0_SHA256,
                        "md0_bytes": B.MD0_BYTES,
                        "glue62_impl_sha256": "gsha",
                    },
                }))

            orig_argv = ["build.py", "--out", str(out), "--loader-source", "ignored"]
            with mock.patch.object(sys, "argv", list(orig_argv)):
                with mock.patch.object(B.b106, "main", side_effect=fake_b106_main):
                    B.main()
                self.assertEqual(sys.argv, orig_argv)
            self.assertEqual(before_saved, (B.b106.NAME, B.b106.NEW_TAG, B.b106.MD0_SHA256, B.b106.MD0_BYTES,
                                            B.b106.BURST_NEW, B.b106.TAIL_RETURN_NEW, B.b106.RETURN_SETTLE_WAITS, B.b67.APPEND))
            bjson_txt = (out / "build.json").read_text()
            self.assertIn('\n "nat108_changes":', bjson_txt)
            bj = json.loads(bjson_txt)
            self.assertNotIn("nat106_sources", bj)
            self.assertNotIn("nat106_changes", bj)
            self.assertNotIn("nat106_note", bj)
            self.assertEqual(bj["nat108_changes"]["cmdline"], valid_cmd)
            self.assertEqual(bj["nat108_changes"]["cmdline_bytes"], len(valid_cmd))
            self.assertEqual(bj["nat108_changes"]["fb_diff"], 1)
            self.assertEqual(bj["nat108_changes"]["glue62_impl_sha256"], "gsha")
            self.assertEqual(bj["nat108_sources"]["build.py"], B.sha((HERE / "build.py").read_bytes()))

            # --check-only without --ramdisk must NOT inject --ramdisk and returns early
            seen_chk = []
            with mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", str(out)]):
                with mock.patch.object(B.b106, "main", side_effect=lambda: seen_chk.append(list(sys.argv))):
                    B.main()
            self.assertNotIn("--ramdisk", seen_chk[0])

            # without --out returns early cleanly (and explicit --ramdisk stays unchanged)
            seen_no_out = []
            with mock.patch.object(sys, "argv", ["build.py", "--ramdisk", "custom.apfs"]):
                with mock.patch.object(B.b106, "main", side_effect=lambda: seen_no_out.append(list(sys.argv))):
                    B.main()
            self.assertEqual(seen_no_out[0], ["build.py", "--ramdisk", "custom.apfs"])

            # cmdline validation boundaries (missing fb_diff, missing xrd=md0, exact 256 limit)
            bad_cmds = [
                "rd=md1 xrd=md0",
                "rd=md1 fb_diff=1",
                ("a" * (256 - len(" fb_diff=1 xrd=md0"))) + " fb_diff=1 xrd=md0",
            ]
            for bad in bad_cmds:
                def write_bad(cmd=bad):
                    (out / "build.json").write_text(json.dumps({"nat106_changes": {"cmdline": cmd}}))
                with mock.patch.object(sys, "argv", ["build.py", "--out", str(out), "--ramdisk", "x"]):
                    with mock.patch.object(B.b106, "main", side_effect=write_bad):
                        with self.assertRaises(SystemExit):
                            B.main()
            # Boundary 255 passes!
            cmd_255 = " " + ("a" * (255 - len(" fb_diff=1 xrd=md0") - 1)) + " fb_diff=1 xrd=md0"
            self.assertEqual(len(cmd_255), 255)
            with mock.patch.object(sys, "argv", ["build.py", "--out", str(out), "--ramdisk", "x"]):
                with mock.patch.object(B.b106, "main", side_effect=lambda: (out / "build.json").write_text(
                        json.dumps({"nat106_changes": {"cmdline": cmd_255}}))):
                    B.main()

            hp = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build.py"), "--help"], capture_output=True, text=True)
            self.assertEqual(hp.returncode, 0)
            self.assertIn("--loader-source", hp.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @unittest.skipUnless(BUILD108.is_file() and BUILD106.is_file() and PKG108.is_file(), "NAT-108 build artifacts missing")
    def test_payload_diff_and_package(self):
        p108 = BUILD108.read_bytes()
        p106 = BUILD106.read_bytes()
        self.assertEqual(len(p108), PAYLOAD_LEN)
        self.assertEqual(len(p108), len(p106))

        sweet108 = p108.rfind(b"SWEETXNU")
        sweet106 = p106.rfind(b"SWEETXNU")
        self.assertGreater(sweet108, 0)
        self.assertEqual(sweet108, sweet106)
        cmd_start = sweet108 + CMDLINE_OFF
        cmd108 = p108[cmd_start:cmd_start + CMDLINE_LEN].rstrip(b"\0").decode("ascii")
        cmd106 = p106[cmd_start:cmd_start + CMDLINE_LEN].rstrip(b"\0").decode("ascii")
        self.assertLess(len(cmd108), 256)
        self.assertTrue(cmd108.startswith("rd=md1 "))
        self.assertTrue(cmd108.endswith(" fb_diff=1 xrd=md0"))
        self.assertIn("nat_attempt=NAT108-sc1", cmd108)
        self.assertEqual(
            cmd108,
            cmd106.replace("NAT106-sb2", "NAT108-sc1").replace(" xrd=md0", " fb_diff=1 xrd=md0"),
        )

        md0_bytes = ROOT108.read_bytes()
        md0_off = p108.find(md0_bytes[:64])
        self.assertGreater(md0_off, cmd_start + CMDLINE_LEN)
        self.assertEqual(p108[sweet108:cmd_start], p106[sweet108:cmd_start])
        self.assertEqual(p108[cmd_start + CMDLINE_LEN:md0_off], p106[cmd_start + CMDLINE_LEN:md0_off])
        self.assertEqual(p108[md0_off:md0_off + len(md0_bytes)], md0_bytes)
        self.assertEqual(p108[md0_off + len(md0_bytes):], p106[md0_off + len(md0_bytes):])

        bjson = json.loads(BUILD108_JSON.read_text())["nat108_changes"]
        self.assertEqual(bjson["image_name"], B.NAME)
        self.assertEqual(bjson["cmdline"], cmd108)
        self.assertEqual(bjson["cmdline_bytes"], len(cmd108))
        self.assertEqual(bjson["fb_diff"], 1)
        self.assertEqual(bjson["tail_return_bytes"], 524288)
        self.assertEqual(bjson["burst_bytes"], 4096)
        self.assertEqual(bjson["return_settle_waits"], 10)

        pkg = json.loads(PKG108.read_text())["images"][B.NAME]
        self.assertEqual(pkg["payload_sha256"], sha(p108))
        self.assertEqual(pkg["payload_bytes"], PAYLOAD_LEN)
        self.assertEqual(pkg["recovery_bytes"], 100663296)


class TestAnalyzeStageC(unittest.TestCase):
    def test_helpers_and_patched_tail(self):
        self.assertEqual(AN.TAIL_RETURN_108, 524288)
        before = AN.A106.TAIL_RETURN_106
        with AN.patched_tail():
            self.assertEqual(AN.A106.TAIL_RETURN_106, 524288)
        self.assertEqual(AN.A106.TAIL_RETURN_106, before)
        self.assertTrue(AN._row_is_springboard({"cmd": "/System/Library/CoreServices/SpringBoard.app/SpringBoard"}))
        self.assertTrue(AN._row_is_springboard({"cmd": "other/SpringBoard -Arg"}))
        self.assertFalse(AN._row_is_springboard({"cmd": "/usr/libexec/backboardd"}))

    def test_stage_c_ladder_c0_to_c7(self):
        jobs = AN.A89.read_jobs(JOBS108_DIR) if JOBS108_DIR.is_dir() else [{"label": AN.SPRINGBOARD_LABEL}]

        # C0 no kernel text (including len==0 filtered out & empty unreadable omitted from reason)
        d = make_scratch("c0_")
        try:
            empty_arch = d / "arch"
            empty_arch.mkdir()
            orig_tail = AN.A106.TAIL_RETURN_106
            seen_inside = []
            def fake_ra(arch):
                seen_inside.append(AN.A106.TAIL_RETURN_106)
                return {"boots": [], "dumps": [{"why": 2, "begin": {"len": 0, "gap": 0}, "bytes": b""}], "unreadable": []}
            AN.A106.TAIL_RETURN_106 = 123
            try:
                with mock.patch.object(AN.A97.R2, "read_archive2", side_effect=fake_ra):
                    r0_clean = AN.analyze_stage_c(empty_arch, JOBS108_DIR if JOBS108_DIR.is_dir() else JOBS106_DIR)
                self.assertEqual(seen_inside, [524288])
                self.assertEqual(AN.A106.TAIL_RETURN_106, 123)
            finally:
                AN.A106.TAIL_RETURN_106 = orig_tail
            self.assertEqual(r0_clean["row"], 0)
            self.assertNotIn("unreadable", r0_clean["reason"])

            with mock.patch.object(AN.A97.R2, "read_archive2", return_value={
                "boots": [], "dumps": [{"why": 2, "begin": {"len": 0, "gap": 0}, "bytes": b""}], "unreadable": ["g0"],
            }):
                r0 = AN.analyze_stage_c(empty_arch, JOBS108_DIR if JOBS108_DIR.is_dir() else JOBS106_DIR)
            self.assertEqual(r0["row"], 0)
            self.assertEqual(r0["name"], "no-kernel-text")
            self.assertIn("1 unreadable group", r0["reason"])

            # Mocked analyze_stage_c picks largest why=2 dump & toggles inferred/conflicts cleanly
            small = {"why": 2, "begin": {"len": 1, "gap": 0}, "bytes": b"a",
                     "text": "init: library insertion: only\n",
                     "hole_bytes": 0, "boots": ["12345678"], "closed": True, "holes": [],
                     "conflicts": [], "problems": [], "begin_inferred": False}
            with mock.patch.object(AN.A97.R2, "read_archive2", return_value={"boots": ["b"], "dumps": [small], "unreadable": []}):
                rc_small = AN.analyze_stage_c(empty_arch, JOBS108_DIR if JOBS108_DIR.is_dir() else JOBS106_DIR)
            self.assertEqual(rc_small["row"], 2)
            self.assertNotIn("inferred", rc_small["reason"])
            self.assertNotIn("WARNING", rc_small["reason"])

            big = {"why": 2, "begin": {"len": 50, "gap": 2}, "bytes": b"abcd",
                   "text": "init: library insertion: /redwood/lib/libhakios.sb.dylib SpringBoard\n",
                   "hole_bytes": 3, "boots": ["abcdef99"], "closed": True, "holes": [],
                   "conflicts": [12], "problems": [], "begin_inferred": True}
            with mock.patch.object(AN.A97.R2, "read_archive2", return_value={"boots": ["b"], "dumps": [small, big], "unreadable": []}):
                rc_mock = AN.analyze_stage_c(empty_arch, JOBS108_DIR if JOBS108_DIR.is_dir() else JOBS106_DIR)
            self.assertEqual(rc_mock["row"], 2)
            self.assertEqual(rc_mock["dump"]["boots"], ["abcdef"])
            self.assertEqual(rc_mock["facts"]["unreadable"], [])
            self.assertIn("dump begin inferred", rc_mock["reason"])
            self.assertIn("WARNING: 1 boot conflict", rc_mock["reason"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

        # C1 early blocked
        r1 = AN.analyze_stage_c_text(
            "kernel panic soon\npanic(cpu 0 caller 0x1): oops\ninitproc exited -- no exit reason available -- (signal 0, exit status 1)\n",
            [{"label": "other"}],
        )
        self.assertEqual(r1["row"], 1)
        self.assertFalse(r1["facts"]["springboard_in_jobs"])
        self.assertIn("kernel panic", r1["reason"])
        self.assertIn("initproc exited", r1["reason"])

        # C2 inject / launchd only + top_failed_lookups bounded at 15
        many_fail = "\n".join(f"failed lookup: name = com.test.svc{i:02d}, requestor = x[1]" for i in range(18))
        r2 = AN.analyze_stage_c_text("init: library insertion: /redwood/lib/libhakios.sb.dylib SpringBoard\n" + many_fail, jobs, hole_bytes=4, gap_bytes=0)
        self.assertEqual(r2["row"], 2)
        self.assertTrue(r2["facts"]["springboard_in_jobs"])
        self.assertIn("(hole=4, gap=0)", r2["reason"])
        self.assertEqual(len(r2["facts"]["top_failed_lookups"]), 15)

        r2_gap = AN.analyze_stage_c_text(
            "com.apple.xpc.launchd|1970-01-01 00:00:01.000000 <Notice>: boot-args = rd=md1\n",
            jobs,
            hole_bytes=0,
            gap_bytes=7,
        )
        self.assertEqual(r2_gap["row"], 2)
        self.assertIn("(hole=0, gap=7)", r2_gap["reason"])

        # C3 backboardd alive (via stage_b row 4 without ps row or via ps row)
        t3 = (
            "init: library insertion: /redwood/lib/libhakios.dylib backboardd\n"
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "   14     1 Ss   /usr/libexec/backboardd\n"
            "SWEET hb: n=1 ps pid=15 status=0 ms=4\n"
        )
        r3 = AN.analyze_stage_c_text(t3, jobs)
        self.assertEqual(r3["row"], 3)
        self.assertEqual(r3["name"], "backboardd-alive-no-springboard")
        self.assertNotIn("hole=", r3["reason"])

        r3_swap = AN.analyze_stage_c_text("MiniIOMobileFramebuffer: swap 1 (#0): surfaces 1 0 0 0, layers set 0x1 cleared 0x0\n", jobs)
        self.assertEqual(r3_swap["row"], 3)

        # C4 via sb_hakios alone (no spawn/ps) & via spawn+exit
        r4_hakios = AN.analyze_stage_c_text("hakios: unrelated line\nhakios: SpringBoard activation ok\n", jobs)
        self.assertEqual(r4_hakios["row"], 4)
        self.assertEqual(r4_hakios["facts"]["springboard_hakios_lines"], ["SpringBoard activation ok"])

        t4 = t3 + (
            "com.apple.xpc.launchd|1970-01-01 00:00:05.000000 (user/501/com.apple.SpringBoard) <Notice>: xpcproxy spawned with pid 40\n"
            "com.apple.xpc.launchd|1970-01-01 00:00:06.000000 (user/501/com.apple.SpringBoard [40]) <Notice>: Service exited due to SIGABRT\n"
            "denied attempt to escape CPU monitor\n"
            "failed lookup: name = com.apple.missing.svc, requestor = SpringBoard[40]\n"
        )
        r4 = AN.analyze_stage_c_text(t4, jobs)
        self.assertEqual(r4["row"], 4)
        self.assertEqual(r4["name"], "springboard-exited")
        self.assertIn("Service exited due to SIGABRT", r4["reason"])
        self.assertEqual(r4["facts"]["lsd_cpu_monitor_denials"], 1)
        self.assertEqual(r4["facts"]["top_failed_lookups"], [("com.apple.missing.svc", 1)])

        # C4 via vanished from second ps list (first list had SpringBoard)
        t4_vanish = (
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "   40     1 Ss   /System/Library/CoreServices/SpringBoard.app/SpringBoard\n"
            "SWEET hb: n=1 ps pid=41 status=0 ms=4\n"
            "SWEET hb: n=2 pid=8 ppid=1 up=20\n"
            "  PID  PPID STAT COMM\n"
            "   14     1 Ss   /usr/libexec/backboardd\n"
            "SWEET hb: n=2 ps pid=42 status=0 ms=4\n"
        )
        r4v = AN.analyze_stage_c_text(t4_vanish, jobs)
        self.assertEqual(r4v["row"], 4)
        self.assertIn("absent/zombie in last ps list", r4v["reason"])

        # C5 SpringBoard alive in trailing cut list (two cut lists verify [-1])
        t5_cut = (
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "   14     1 Ss   /usr/libexec/backboardd\n"
            "[... 10 bytes lost in transport ...]\n"
            "  PID  PPID STAT COMM\n"
            "   40     1 Ss   /System/Library/CoreServices/SpringBoard.app/SpringBoard\n"
        )
        r5_cut = AN.analyze_stage_c_text(t5_cut, jobs)
        self.assertEqual(r5_cut["row"], 5)
        self.assertIn("trailing ps list", r5_cut["reason"])

        # C5 complete list
        t5_header = (
            "hakios: SpringBoard setup done\n"
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "   14     1 Ss   /usr/libexec/backboardd\n"
            "   40     1 Ss   /System/Library/CoreServices/SpringBoard.app/SpringBoard\n"
            "SWEET hb: n=1 ps pid=41 status=0 ms=4\n"
        )
        r5 = AN.analyze_stage_c_text(t5_header + "SWEET hb: n=2 pid=8 ppid=1 up=20\n  PID  PPID STAT COMM\n   14     1 Ss   /usr/libexec/backboardd\n", jobs)
        self.assertEqual(r5["row"], 5)
        self.assertIn("alive in last complete ps list", r5["reason"])

        # C6 SpringBoard alive + swaps + 0 diff pixels (complete & trailing)
        t6 = t5_header + (
            "MiniIOMobileFramebuffer: swap 1 (#0): surfaces 1 0 0 0, layers set 0x1 cleared 0x0\n"
            "MiniIOMobileFramebuffer: 0 pixels of the panel changed a frame, all within 0,0 to 0,0\n"
        )
        r6 = AN.analyze_stage_c_text(t6, jobs)
        self.assertEqual(r6["row"], 6)
        self.assertEqual(r6["name"], "fb-swaps-no-diff")
        self.assertIn("complete ps list", r6["reason"])
        r6_cut = AN.analyze_stage_c_text("MiniIOMobileFramebuffer: swap 1 (#0): surfaces 1 0 0 0, layers set 0x1 cleared 0x0\n" + t5_cut, jobs)
        self.assertEqual(r6_cut["row"], 6)
        self.assertIn("trailing ps list", r6_cut["reason"])

        # C7 SpringBoard alive/seen + positive 1 pixel diff (kills > 1 mutant!)
        t7 = t6 + "MiniIOMobileFramebuffer: 1 pixels of the panel changed a frame, all within 10,20 to 30,40\n"
        r7 = AN.analyze_stage_c_text(t7, jobs)
        self.assertEqual(r7["row"], 7)
        self.assertEqual(r7["name"], "panel-pixels-changed")
        self.assertIn("max 1 px/frame", r7["reason"])
        self.assertIn("SpringBoard alive", r7["reason"])

        r7_dead = AN.analyze_stage_c_text(t4 + "MiniIOMobileFramebuffer: 2 pixels of the panel changed a frame, all within 0,0 to 1,1\n", jobs)
        self.assertEqual(r7_dead["row"], 7)
        self.assertIn("SpringBoard seen", r7_dead["reason"])

    @unittest.skipUnless(NAT105_ARCHIVE.is_dir(), "NAT-105 archive missing")
    def test_analyze_cli_dispatch(self):
        d = make_scratch("cli_")
        try:
            jobs101 = ROOT / "artifacts/nat-101/pid1-hb/root/LaunchDaemons"
            for mode, prefix, jobs_dir in (
                ("stage-c", "row C2 ", JOBS106_DIR),
                ("stage-b", "row B2 ", JOBS106_DIR),
                ("hb", "row H5 ", jobs101),
                ("stage-a", "row A1 ", jobs101),
            ):
                out_f = d / f"sub_{mode}" / f"{mode}.json"
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = AN.main(["--mode", mode, "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(jobs_dir), "--out", str(out_f)])
                self.assertEqual(rc, 0)
                self.assertTrue(buf.getvalue().startswith(prefix))
                self.assertTrue(out_f.is_file())
                self.assertIn('\n "row":', out_f.read_text())
            buf_no_out = io.StringIO()
            with contextlib.redirect_stdout(buf_no_out):
                self.assertEqual(AN.main(["--mode", "stage-c", "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(JOBS106_DIR)]), 0)
            self.assertTrue(buf_no_out.getvalue().startswith("row C2 "))

            with mock.patch.object(AN, "analyze_chain", return_value={"row": 1, "_exit_code": 7}) as mc:
                buf2 = io.StringIO()
                with contextlib.redirect_stdout(buf2):
                    rc2 = AN.main(["--mode", "chain", "--archive", str(NAT105_ARCHIVE), "--events", "e", "--report", "r", "--delivery", "del", "--root", "root", "--size", "1", "--sha256", "ab", "--log-out", "lg", "--out", str(d / "co.json"), "--allow-synthetic"])
            self.assertEqual(rc2, 7)
            self.assertEqual(mc.call_count, 1)
            self.assertIn('\n "row": 1', buf2.getvalue())
            self.assertEqual(json.loads(buf2.getvalue()), {"row": 1})
            self.assertTrue(mc.call_args.kwargs["allow_synthetic"])
            self.assertEqual(mc.call_args.kwargs["log_out"], Path("lg"))

            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                for missing in ("--events", "--report", "--delivery", "--root", "--size", "--sha256"):
                    args = ["--mode", "chain", "--archive", str(NAT105_ARCHIVE), "--events", "e", "--report", "r", "--delivery", "del", "--root", "root", "--size", "1", "--sha256", "ab"]
                    idx = args.index(missing)
                    with self.assertRaises(SystemExit):
                        AN.main(args[:idx] + args[idx + 2:])
                with self.assertRaises(SystemExit):
                    AN.main(["--mode", "stage-c", "--archive", str(NAT105_ARCHIVE)])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDeriveAndSession108(unittest.TestCase):
    def test_derive_check_and_refusals(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = D.main(["--check"])
        self.assertEqual(rc, 0)
        self.assertIn("9 substitutions", buf.getvalue())

        saved = (D.SRC_SHA256, D.PAYLOAD_LEN)
        try:
            D.SRC_SHA256 = "0" * 64
            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                self.assertEqual(D.main(["--check"]), 2)
            D.SRC_SHA256 = saved[0]
            D.PAYLOAD_LEN = 123
            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                self.assertEqual(D.main(["--check"]), 2)
        finally:
            D.SRC_SHA256, D.PAYLOAD_LEN = saved

    def test_session_gate_and_registry(self):
        cfg = S108.IMAGES["loader-diag-xnu-sc1-md1"]
        dec = S108.gate("loader-diag-xnu-sc1-md1", cfg)
        self.assertTrue(dec.name.startswith("0041-nat108-loader-diag-xnu-sc1-md1-single-run-"))

        d = make_scratch("gate_")
        try:
            fake_root = d / "repo"
            (fake_root / "state").mkdir(parents=True)
            req = {tid: {"id": tid, "status": "done"} for tid in S108.REQUIRED_DONE}
            st = {
                "project": {
                    "permissions": {"native": True},
                    "permission_decisions": [{"scope": "native", "value": True, "decision": "docs/decisions/" + dec.name}],
                },
                "tasks": list(req.values()),
            }
            lab_json = fake_root / "state/lab.json"
            lab_json.write_text(json.dumps(st))
            with mock.patch.object(S108, "ROOT", fake_root):
                self.assertIsNone(S108.registry_blocker(dec))

                st["project"]["permissions"]["native"] = False
                lab_json.write_text(json.dumps(st))
                self.assertIsNotNone(S108.registry_blocker(dec))

                st["project"]["permissions"]["native"] = True
                req["NAT-108"]["status"] = "in_progress"
                lab_json.write_text(json.dumps(st))
                self.assertIn("NAT-108", S108.registry_blocker(dec))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
