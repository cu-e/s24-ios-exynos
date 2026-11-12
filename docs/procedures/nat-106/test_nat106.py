#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-106 host tests: Stage B + hb root builder, build wrapper & glue62_impl.h patcher,
compiled C host harness (-DNAT062_HOST -Wall -Wextra -Werror), payload verification,
analyze_nat106.py (--mode stage-b B0-B6 ladder, hb, stage-a, chain over TAIL_MAX[2]=524288),
derive106.py, and session_nat106.py gate checks. Host-only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
SRC62 = PROC / "nat-062" / "src"

ROOT106 = ROOT / "artifacts/nat-106/pid1-sb2-hb/root.apfs"
ROOT106_JSON = ROOT / "artifacts/nat-106/pid1-sb2-hb/build.json"
JOBS106_DIR = ROOT / "artifacts/nat-106/pid1-sb2-hb/root/LaunchDaemons"
JOBS101_DIR = ROOT / "artifacts/nat-101/pid1-hb/root/LaunchDaemons"
PKG106 = ROOT / "artifacts/nat-106/package-001/package.json"
BUILD106 = ROOT / "artifacts/nat-106/build-001/loader-diag-xnu-sb2-md1/Image.payload"
BUILD104 = ROOT / "artifacts/nat-104/build-001/loader-diag-xnu-hb2-md1/Image.payload"
BUILD106_JSON = ROOT / "artifacts/nat-106/build-001/build.json"
BUILT_GLUE106 = ROOT / "artifacts/nat-106/build-001/loader-diag-xnu-sb2-md1/source/shim/e1s-xnu/glue62_impl.h"
NAT105_ARCHIVE = ROOT / "artifacts/nat-105/run-001/archive"
SCRATCH = ROOT / "artifacts/nat-106/tmp"

HEAD_RETURN = 8192
TAIL_RETURN = 524288
PA = 0x9A2B0A00
LOG_VA = 0xFFFFFFF007B90A00
DELTA = (PA - LOG_VA) % (1 << 64)
PAYLOAD_LEN = 26134288


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RB = load("nat106_test_root", HERE / "build_sb2_hb_root.py")
B = load("nat106_test_build", HERE / "build.py")
D = load("nat106_test_derive", HERE / "derive106.py")
AN = load("nat106_test_analyze", HERE / "analyze_nat106.py")
S106 = load("nat106_test_session", HERE / "session_nat106.py")

needs_cc = unittest.skipUnless(
    subprocess.run(["cc", "--version"], capture_output=True).returncode == 0,
    "no host C compiler",
)


def make_scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define NAT062_HOST 1
#define UNUSED __attribute__((unused))
static const uint8_t *g_mem;
static uint64_t g_base, g_len, g_reads;
static int g_up = 1;
static UNUSED uint8_t rd(uint64_t pa)
{
	if (pa < g_base || pa >= g_base + g_len) {
		fprintf(stderr, "OOB read at %llx\n", (unsigned long long)pa);
		exit(3);
	}
	g_reads++;
	return g_mem[pa - g_base];
}
static UNUSED void emit(const char *b, const char *e)
{
	fputs("R ", stdout);
	fwrite(b, 1, (size_t)(e - b), stdout);
	fputc('\n', stdout);
}
static UNUSED void wait_(void) { fputs("W\n", stdout); }
#define N62_UP() g_up
#define N62_EMIT(b, e) emit((b), (e))
#define N62_WAIT() wait_()
#define N62_BYTE(pa) rd((uint64_t)(pa))
@N47@
#include "glue62_impl.h"
int main(int argc, char **argv)
{
	if (argc != 7) return 2;
	uint64_t x0 = strtoull(argv[1], 0, 16), x1 = strtoull(argv[2], 0, 16), delta = strtoull(argv[3], 0, 16);
	uint32_t why = (uint32_t)strtoul(argv[4], 0, 10);
	g_up = atoi(argv[5]);
	FILE *f = fopen(argv[6], "rb");
	static uint8_t buf[0x200000];
	g_len = f ? fread(buf, 1, sizeof buf, f) : 0;
	if (f) fclose(f);
	g_mem = buf;
	g_base = x0;
	nat062_dump_log(x0, x1, delta, why);
	fprintf(stderr, "reads=%llu\n", (unsigned long long)g_reads);
	return 0;
}
"""


def n47_text():
    src = (PROC / "nat-047/src/markerlib47.c").read_text()
    out = []
    for name in ("n47_s", "n47_x", "n47_d"):
        m = re.search(r"static char \*%s\(.*?\n}\n" % name, src, re.S)
        out.append(m.group(0).replace("static char", "static UNUSED char", 1))
    return "\n".join(out)


def write_synthetic_archive(root, kl_lines):
    boot = root / "boots" / "000001-aabbccdd-11223344"
    boot.mkdir(parents=True, exist_ok=True)
    frames = [{"frame": {"kind": "boot", "seq": 0}, "received": {"monotonic_ns": 1000}}]
    seq = 1
    for ln in kl_lines:
        if ln == "__DROP__":
            frames.append({"frame": {"kind": "drop", "seq": seq, "lost_bytes": 1024}, "received": {"monotonic_ns": 1000 + seq * 100}})
        else:
            frames.append({"frame": {"kind": "log", "dev_kind": "text", "dev_seq": seq, "seq": seq, "text": ln}, "received": {"monotonic_ns": 1000 + seq * 100}})
        seq += 1
    (boot / "frames.jsonl").write_text("\n".join(json.dumps(f) for f in frames) + "\n")


class TestSmallRoot(unittest.TestCase):
    def test_built_root_matches_manifest_and_contents(self):
        self.assertEqual(RB.ROOT, ROOT)
        self.assertEqual(ROOT106.stat().st_size, B.MD0_BYTES)
        self.assertEqual(sha(ROOT106.read_bytes()), B.MD0_SHA256)
        raw = ROOT106_JSON.read_text()
        self.assertIn('\n "files": 29,\n', raw)
        meta = json.loads(raw)
        self.assertEqual(meta["files"], 29)
        self.assertFalse(meta["kernel_apfs_lib_readback"]["mismatches"])
        self.assertEqual(meta["nat106_stage_b_hb"]["hb_base"], "artifacts/nat-101/pid1-hb")
        self.assertEqual(meta["nat106_stage_b_hb"]["total_files"], 29)
        self.assertNotIn(str(ROOT), raw)
        root_dir = ROOT106.parent / "root"
        self.assertTrue((root_dir / "bin/hb").is_file())
        self.assertTrue((root_dir / "LaunchDaemons/com.apple.backboardd.plist").is_file())
        self.assertTrue((root_dir / "lib/libhakios.dylib").is_file())
        self.assertEqual((root_dir / "etc/inject.conf").read_bytes(), RB.B99.INJECT_CONF)

    def test_wrapper_checks_main_and_restores_b99_globals(self):
        d = make_scratch("rootwrap_")
        try:
            fake_base = d / "base"
            shutil.copytree(ROOT / "artifacts/nat-101/pid1-hb/root", fake_base / "root", symlinks=True)
            (fake_base / "root.apfs").write_bytes(b"\x00" * 1024)
            with self.assertRaises(RB.BuildError):
                RB.build(d / "out1", fake_base, ROOT / "artifacts/ios-root/recipe", ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")
            self.assertEqual(RB.B99.BASE_FILE_COUNT, 25)

            out2 = d / "out2"
            saved_root = ROOT106.parent / "root"
            fake_b99_ret = {"files": 29, "root_apfs": {"bytes": B.MD0_BYTES, "sha256": B.MD0_SHA256}, "kernel_apfs_lib_readback": {"mismatches": []}}

            def fake_b99_build(out_p, base_p, recipe_p, dylib_p):
                shutil.copytree(saved_root, Path(out_p) / "root", symlinks=True)
                self.assertEqual(RB.B99.BASE_FILE_COUNT, 26)
                self.assertEqual(RB.B99.BASE_ROOT_APFS_SHA256, RB.HB_BASE_ROOT_APFS_SHA256)
                return dict(fake_b99_ret)

            with mock.patch.object(RB.B99, "build", side_effect=fake_b99_build):
                rec = RB.build(str(out2), str(ROOT / "artifacts/nat-101/pid1-hb"), str(ROOT / "artifacts/ios-root/recipe"), str(ROOT / "references/hakios/prebuilt/userland/libhakios.dylib"))
            self.assertEqual(rec["nat106_stage_b_hb"]["total_files"], 29)
            self.assertIn('\n "files": 29,\n', (out2 / "build.json").read_text())
            self.assertEqual(RB.B99.BASE_FILE_COUNT, 25)

            # Wrong file count fails cleanly (with valid root dir so line 50's check is the one hit)
            out_bad_cnt = d / "out_bad_cnt"
            def fake_b99_bad_cnt(out_p, base_p, recipe_p, dylib_p):
                shutil.copytree(saved_root, Path(out_p) / "root", symlinks=True)
                return dict(fake_b99_ret, files=28)

            with mock.patch.object(RB.B99, "build", side_effect=fake_b99_bad_cnt):
                with self.assertRaises(RB.BuildError) as cm_cnt:
                    RB.build(out_bad_cnt, ROOT / "artifacts/nat-101/pid1-hb", ROOT / "artifacts/ios-root/recipe", ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")
            self.assertIn("expected 29 files", str(cm_cnt.exception))

            # Missing bin/hb fails cleanly
            out3 = d / "out3"
            def fake_b99_no_hb(out_p, base_p, recipe_p, dylib_p):
                shutil.copytree(saved_root, Path(out_p) / "root", symlinks=True)
                (Path(out_p) / "root/bin/hb").unlink()
                return dict(fake_b99_ret)

            with mock.patch.object(RB.B99, "build", side_effect=fake_b99_no_hb):
                with self.assertRaises(RB.BuildError):
                    RB.build(out3, ROOT / "artifacts/nat-101/pid1-hb", ROOT / "artifacts/ios-root/recipe", ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")

            # Missing /redwood/bin/hb loop in etc/rc fails cleanly
            out4 = d / "out4"
            def fake_b99_no_rc(out_p, base_p, recipe_p, dylib_p):
                shutil.copytree(saved_root, Path(out_p) / "root", symlinks=True)
                (Path(out_p) / "root/etc/rc").write_bytes(b"#!/bin/sh\n")
                return dict(fake_b99_ret)

            with mock.patch.object(RB.B99, "build", side_effect=fake_b99_no_rc):
                with self.assertRaises(RB.BuildError):
                    RB.build(out4, ROOT / "artifacts/nat-101/pid1-hb", ROOT / "artifacts/ios-root/recipe", ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")

            # main() CLI success and SystemExit wrapping
            buf = io.StringIO()
            with mock.patch.object(RB, "build", return_value=rec) as mb:
                with contextlib.redirect_stdout(buf):
                    RB.main(["--out", str(d / "x"), "--base", str(d / "b"), "--recipe", str(d / "r"), "--dylib", str(d / "dl")])
            self.assertEqual(mb.call_args[0], (d / "x", d / "b", d / "r", d / "dl"))
            self.assertIn('\n "kernel_readback_ok": true\n', buf.getvalue())
            self.assertTrue(json.loads(buf.getvalue())["kernel_readback_ok"])

            # Default arguments in main()
            with mock.patch.object(RB, "build", return_value=rec) as mb2:
                with contextlib.redirect_stdout(io.StringIO()):
                    RB.main([])
            self.assertEqual(mb2.call_args[0][0], ROOT / "artifacts/nat-106/pid1-sb2-hb")
            self.assertEqual(mb2.call_args[0][1], ROOT / "artifacts/nat-101/pid1-hb")
            self.assertEqual(mb2.call_args[0][2], ROOT / "artifacts/ios-root/recipe")
            self.assertEqual(mb2.call_args[0][3], ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")

            with mock.patch.object(RB, "build", side_effect=RB.BuildError("bad input")):
                with self.assertRaises(SystemExit) as cm:
                    RB.main(["--out", str(d / "x")])
            self.assertEqual(str(cm.exception), "build_sb2_hb_root: bad input")

            hp = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build_sb2_hb_root.py"), "--help"], capture_output=True, text=True)
            self.assertEqual(hp.returncode, 0)
            self.assertIn("--recipe", hp.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestBuildAndGlue(unittest.TestCase):
    def test_patch_rules_and_artifacts(self):
        self.assertEqual(B.ROOT, ROOT)
        self.assertEqual(B.NAME, "loader-diag-xnu-sb2-md1")
        self.assertEqual(B.NEW_TAG, "nat_attempt=NAT106-sb2")
        self.assertEqual(B.MD0_BYTES, 4194304)
        self.assertEqual(B.BURST_NEW, 4096)
        self.assertEqual(B.TAIL_RETURN_NEW, TAIL_RETURN)
        self.assertEqual(TAIL_RETURN % 96, 32)
        self.assertEqual(B.RETURN_SETTLE_WAITS, 10)
        self.assertEqual(len(B.PATCH_RULES), 3)

        # Verify _make_patch_rules() defensive errors
        saved_rules = B.b104.PATCH_RULES
        try:
            B.b104.PATCH_RULES = (("tail_return", "a", "wrong"),)
            with self.assertRaises(RuntimeError):
                B._make_patch_rules()
            B.b104.PATCH_RULES = ()
            with self.assertRaises(RuntimeError) as cm_pr:
                B._make_patch_rules()
            self.assertIn("found 0", str(cm_pr.exception))
        finally:
            B.b104.PATCH_RULES = saved_rules

        d = make_scratch("glue_")
        try:
            g = d / "glue62_impl.h"
            shutil.copy2(SRC62 / "glue62_impl.h", g)
            patched_sha = B.patch_glue106(g)
            self.assertEqual(B.b104.PATCH_RULES, saved_rules)
            self.assertEqual(patched_sha, sha(BUILT_GLUE106.read_bytes()))
            txt = g.read_text()
            self.assertIn("#define NAT062_BURST\t\t4096u", txt)
            self.assertIn("#define NAT062_TAIL_RETURN\t524288u", txt)
            self.assertIn("for (uint32_t w = 0; w < 10u; w++)", txt)
            with self.assertRaises(SystemExit):
                B.patch_glue106(g)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        bj = json.loads(BUILD106_JSON.read_text())
        self.assertNotIn("nat104_changes", bj)
        self.assertEqual(bj["nat106_changes"]["image_name"], "loader-diag-xnu-sb2-md1")
        self.assertEqual(bj["nat106_changes"]["cmdline_tag"], "nat_attempt=NAT106-sb2")
        self.assertEqual(bj["nat106_changes"]["tail_return_bytes"], TAIL_RETURN)
        self.assertEqual(bj["nat106_changes"]["md0_sha256"], B.MD0_SHA256)

        pkg = json.loads(PKG106.read_text())
        img = pkg["images"]["loader-diag-xnu-sb2-md1"]
        self.assertEqual(img["payload_bytes"], PAYLOAD_LEN)
        rec = Path(ROOT / "artifacts/nat-106/package-001/loader-diag-xnu-sb2-md1/recovery.img").read_bytes()
        payload = BUILD106.read_bytes()
        self.assertEqual(sha(rec), img["recovery_sha256"])
        self.assertEqual(sha(payload), img["payload_sha256"])
        self.assertEqual(rec[2048:2048 + len(payload)], payload)

        p104 = BUILD104.read_bytes()
        self.assertEqual(len(payload), len(p104))
        self.assertIn(b"nat_attempt=NAT106-sb2 ", payload)
        self.assertNotIn(b"nat_attempt=NAT104-hb2", payload)

    def test_build_main_wrapper_check_only_and_restore(self):
        d = make_scratch("bmain_")
        try:
            rec_path = d / "build.json"
            init_payload = {
                "nat104_sources": {"x": 1},
                "nat104_changes": {"md0_sha256": B.MD0_SHA256, "md0_bytes": B.MD0_BYTES, "cmdline": "c", "glue62_impl_sha256": "g"},
                "nat104_note": "n",
            }
            rec_path.write_text(json.dumps(init_payload))
            orig_tail = B.b104.TAIL_RETURN_NEW
            orig_name = B.b104.NAME

            def check_args_set_and_write():
                self.assertEqual(B.b104.NAME, B.NAME)
                self.assertEqual(B.b104.NEW_TAG, B.NEW_TAG)
                self.assertEqual(B.b104.TAIL_RETURN_NEW, TAIL_RETURN)
                self.assertEqual(B.b104.MD0_BYTES, B.MD0_BYTES)
                self.assertEqual(B.b104.MD0_SHA256, B.MD0_SHA256)

            with mock.patch.object(sys, "argv", ["build.py", "--out", str(d), "--ramdisk", str(ROOT106)]):
                with mock.patch.object(B.b104, "main", side_effect=check_args_set_and_write):
                    B.main()
            self.assertEqual(B.b104.TAIL_RETURN_NEW, orig_tail)
            self.assertEqual(B.b104.NAME, orig_name)
            raw = rec_path.read_text()
            self.assertIn('\n "nat106_sources": {\n', raw)
            out_j = json.loads(raw)
            self.assertNotIn("nat104_changes", out_j)
            self.assertNotIn("nat104_sources", out_j)
            self.assertNotIn("nat104_note", out_j)
            self.assertIn("build.py", out_j["nat106_sources"])
            self.assertEqual(out_j["nat106_changes"]["tail_return_bytes"], TAIL_RETURN)
            self.assertEqual(out_j["nat106_changes"]["md0_sha256"], B.MD0_SHA256)

            # --check-only must not rewrite out/build.json
            rec_path.write_text("SENTINEL")
            with mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", str(d)]):
                with mock.patch.object(B.b104, "main"):
                    B.main()
            self.assertEqual(rec_path.read_text(), "SENTINEL")

            # Missing --out must return without touching disk
            with mock.patch.object(sys, "argv", ["build.py"]):
                with mock.patch.object(B.b104, "main"):
                    B.main()

            # Exception restores globals
            with mock.patch.object(sys, "argv", ["build.py", "--check-only", "--out", str(d)]):
                with mock.patch.object(B.b104, "main", side_effect=RuntimeError("boom")):
                    with self.assertRaises(RuntimeError):
                        B.main()
            self.assertEqual(B.b104.TAIL_RETURN_NEW, orig_tail)

            # Subprocess error check covers __main__ entry point
            hp = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build.py")], capture_output=True, text=True)
            self.assertNotEqual(hp.returncode, 0)
            self.assertIn("--ramdisk", hp.stderr + hp.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @needs_cc
    def test_c_harness_512k_tail_and_roundtrip(self):
        d = make_scratch("cc_")
        try:
            shutil.copy2(BUILT_GLUE106, d / "glue62_impl.h")
            shutil.copy2(SRC62 / "glue62.h", d / "glue62.h")
            (d / "harness.c").write_text(HARNESS.replace("@N47@", n47_text()))
            exe = d / "harness"
            cc = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-I", str(d), str(d / "harness.c"), "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(cc.returncode, 0, cc.stderr)

            log_400k = (b"init: library insertion: /redwood/lib/libhakios.dylib\n" + b"Line " * 81920)[:400 * 1024]
            bin_400 = d / "400k.bin"
            bin_400.write_bytes(log_400k)
            r = subprocess.run([str(exe), hex(PA), hex(len(log_400k)), hex(DELTA), "2", "1", str(bin_400)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            begin_idx = next(i for i, ln in enumerate(lines) if ln.startswith("R KL begin why=2 "))
            self.assertEqual(lines[:begin_idx], ["W"] * 10)
            self.assertIn("gap=0 ", lines[begin_idx])
            self.assertIn("tail=%d " % (len(log_400k) - HEAD_RETURN), lines[begin_idx])

            kl_lines = [ln[2:] for ln in lines if ln.startswith("R KL ")]
            arch_dir = d / "arch400"
            write_synthetic_archive(arch_dir, kl_lines)
            with AN.patched_tail():
                arch = AN.A97.R2.read_archive2(arch_dir)
            self.assertEqual(len(arch["dumps"]), 1)
            self.assertEqual(arch["dumps"][0]["text"], log_400k.decode())
            self.assertEqual(sum(len(v) for v in arch["dumps"][0]["bytes"].values()), len(log_400k))

            log_600k = bytes((i * 17) & 0xFF for i in range(600 * 1024))
            bin_600 = d / "600k.bin"
            bin_600.write_bytes(log_600k)
            r2 = subprocess.run([str(exe), hex(PA), hex(len(log_600k)), hex(DELTA), "2", "1", str(bin_600)], capture_output=True, text=True)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            kl_600 = [ln[2:] for ln in r2.stdout.splitlines() if ln.startswith("R KL ") and not ln.startswith("R KL begin")]
            arch600 = d / "arch600"
            write_synthetic_archive(arch600, kl_600)
            with AN.patched_tail():
                a6 = AN.A97.R2.read_archive2(arch600)
            dump = a6["dumps"][0]
            self.assertTrue(dump["begin_inferred"])
            self.assertEqual(dump["begin"]["tail"], TAIL_RETURN)
            self.assertEqual(dump["begin"]["gap"], len(log_600k) - HEAD_RETURN - TAIL_RETURN)

            r1 = subprocess.run([str(exe), hex(PA), hex(len(log_400k)), hex(DELTA), "1", "1", str(bin_400)], capture_output=True, text=True)
            self.assertEqual(r1.returncode, 0)
            begin1 = next(i for i, ln in enumerate(r1.stdout.splitlines()) if ln.startswith("R KL begin why=1 "))
            self.assertEqual(r1.stdout.splitlines()[:begin1], [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestAnalyze106(unittest.TestCase):
    def test_row_helpers_and_tail_restored(self):
        self.assertTrue(AN._row_is_backboardd({"cmd": "/usr/libexec/backboardd"}))
        self.assertTrue(AN._row_is_backboardd({"cmd": "backboardd -f"}))
        self.assertTrue(AN._row_is_backboardd({"cmd": "/custom/path/backboardd"}))
        self.assertFalse(AN._row_is_backboardd({"cmd": "/usr/libexec/logd"}))
        self.assertTrue(AN._row_alive({"cmd": "backboardd", "stat": "Ss"}))
        self.assertFalse(AN._row_alive({"cmd": "backboardd", "stat": "Zs"}))

        orig_r2 = AN.A87.A65.A62.TAIL_MAX[2]
        self.assertEqual(AN.A104.TAIL_RETURN_104, 262144)
        with AN.patched_tail():
            self.assertEqual(AN.A87.A65.A62.TAIL_MAX[2], TAIL_RETURN)
            self.assertEqual(AN.A104.TAIL_RETURN_104, TAIL_RETURN)
        self.assertEqual(AN.A87.A65.A62.TAIL_MAX[2], orig_r2)
        self.assertEqual(AN.A104.TAIL_RETURN_104, 262144)

        with self.assertRaises(RuntimeError):
            with AN.patched_tail():
                raise RuntimeError("boom")
        self.assertEqual(AN.A87.A65.A62.TAIL_MAX[2], orig_r2)
        self.assertEqual(AN.A104.TAIL_RETURN_104, 262144)

    def test_nat105_regression_and_stage_b_archive_edge_cases(self):
        hb = AN.analyze_hb(NAT105_ARCHIVE, JOBS101_DIR)
        self.assertEqual(hb["row"], 5)
        self.assertEqual(hb["facts"]["gap_bytes"], 0)
        self.assertEqual(hb["facts"]["hole_bytes"], 0)
        sa = AN.analyze_stage_a(NAT105_ARCHIVE, JOBS101_DIR)
        self.assertEqual(sa["row"], 1)
        sb = AN.analyze_stage_b(NAT105_ARCHIVE, JOBS106_DIR)
        self.assertEqual(sb["row"], 2)
        self.assertTrue(sb["facts"]["backboardd_in_jobs"])
        self.assertEqual(sb["facts"]["fb_displays"], [dict(width=1125, height=2436, panel_w=1080, panel_h=2340, stride=4320)])
        self.assertEqual(sb["dump"]["boots"], ["000002"])
        self.assertEqual(sb["facts"]["unreadable"], [])
        self.assertNotIn("dump begin inferred", sb["reason"])
        self.assertNotIn("WARNING:", sb["reason"])

        sb_no_bb = AN.analyze_stage_b(NAT105_ARCHIVE, JOBS101_DIR)
        self.assertFalse(sb_no_bb["facts"]["backboardd_in_jobs"])

        # Synthetic 1-byte why=2 dump kills len > 0 -> len > 1 mutant
        fake_1b = {
            "boots": ["000001-aa"],
            "unreadable": [],
            "dumps": [{
                "why": 2, "boots": ["000001-aa"], "bytes": {0: b"x"}, "hole_bytes": 0, "closed": True,
                "holes": [], "conflicts": [], "problems": [], "begin_inferred": False,
                "begin": {"len": 1, "gap": 0}, "text": "x",
            }],
        }
        with mock.patch.object(AN.A97.R2, "read_archive2", return_value=fake_1b):
            r_1b = AN.analyze_stage_b(NAT105_ARCHIVE, JOBS106_DIR)
        self.assertEqual(r_1b["row"], 1)
        self.assertNotIn("unreadable", r_1b["reason"])
        self.assertNotIn("dump begin inferred", r_1b["reason"])
        self.assertNotIn("WARNING:", r_1b["reason"])

        # Synthetic unreadable / why!=2 / len==0 -> B0; plus begin_inferred and conflicts warnings
        fake_empty = {"boots": ["000001-aa"], "dumps": [{"why": 1, "begin": {"len": 100}}, {"why": 2, "begin": {"len": 0}}], "unreadable": [{"reason": "lost"}]}
        with mock.patch.object(AN.A97.R2, "read_archive2", return_value=fake_empty):
            r0 = AN.analyze_stage_b(NAT105_ARCHIVE, JOBS106_DIR)
        self.assertEqual(r0["row"], 0)
        self.assertIn("1 unreadable group(s)", r0["reason"])

        fake_warn = {
            "boots": ["000001-aa", "000002-bb"],
            "unreadable": [{"reason": "x"}],
            "dumps": [{
                "why": 2, "boots": ["000001-aa", "000002-bb"], "bytes": {0: b"abc"}, "hole_bytes": 0, "closed": True,
                "holes": [], "conflicts": [4], "problems": [], "begin_inferred": True,
                "begin": {"len": 3, "gap": 0}, "text": "xnu\n",
            }],
        }
        with mock.patch.object(AN.A97.R2, "read_archive2", return_value=fake_warn):
            rw = AN.analyze_stage_b(NAT105_ARCHIVE, JOBS106_DIR)
        self.assertEqual(rw["row"], 1)
        self.assertEqual(rw["dump"]["boots"], ["000001", "000002"])
        self.assertEqual(rw["facts"]["unreadable"], [{"reason": "x"}])
        self.assertIn("; dump begin inferred", rw["reason"])
        self.assertIn("; WARNING: 1 boot conflict offset(s)", rw["reason"])

    def test_stage_b_ladder_b0_through_b6(self):
        jobs = AN.A89.read_jobs(JOBS106_DIR)

        d = make_scratch("b0_")
        try:
            empty_arch = d / "empty"
            write_synthetic_archive(empty_arch, [])
            r0 = AN.analyze_stage_b(empty_arch, JOBS106_DIR)
            self.assertEqual(r0["row"], 0)
            self.assertEqual(r0["name"], "no-kernel-text")
            self.assertNotIn("unreadable", r0["reason"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

        # B1: panic and initproc exit before inject / launchd, default hole=0/gap=0
        r1 = AN.analyze_stage_b_text("xnu boot\npanic(cpu 0 caller 0xffff0000): bad things\ninitproc exited -- no exit reason available -- (signal 0, exit status 1)\n", jobs)
        self.assertEqual(r1["row"], 1)
        self.assertEqual(r1["facts"]["panic"], ["bad things"])
        self.assertEqual(r1["facts"]["init_exit"], ["initproc exited -- no exit reason available -- (signal 0, exit status 1"])
        self.assertEqual(r1["facts"]["hole_bytes"], 0)
        self.assertEqual(r1["facts"]["gap_bytes"], 0)
        self.assertIn("; kernel panic: bad things", r1["reason"])
        self.assertIn("; initproc exited -- no exit reason available -- (signal 0, exit status 1", r1["reason"])
        self.assertNotIn("hole=", r1["reason"])

        # B2: single launchd line (launchd_lines == 1 boundary) + hole=0, gap=5 qualifier
        r2_launchd = AN.analyze_stage_b_text(
            "com.apple.xpc.launchd|1970-01-01 00:00:01.000000 (system/com.apple.logd) <Notice>: xpcproxy spawned with pid 11\n",
            jobs,
            gap_bytes=5,
        )
        self.assertEqual(r2_launchd["row"], 2)
        self.assertEqual(r2_launchd["facts"]["launchd_console_lines"], 1)
        self.assertIn("(hole=0, gap=5)", r2_launchd["reason"])

        # B2 with inject line and hole=12
        r2 = AN.analyze_stage_b_text("init: library insertion: backboardd containermanagerd\n", jobs, hole_bytes=12)
        self.assertEqual(r2["row"], 2)
        self.assertEqual(r2["facts"]["inject_lines"], ["backboardd containermanagerd"])
        self.assertIn("(hole=12, gap=0)", r2["reason"])

        # B3 via launchd spawn + exit + zombie
        t3 = (
            "init: library insertion: backboardd containermanagerd\n"
            "com.apple.xpc.launchd|1970-01-01 00:00:02.000000 (system/com.apple.backboardd) <Notice>: xpcproxy spawned with pid 25\n"
            "hakios: failed offset check\n"
            "com.apple.xpc.launchd|1970-01-01 00:00:02.500000 (system/com.apple.backboardd [25]) <Notice>: Service exited due to SIGABRT\n"
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "    1     0 Ss   /sbin/launchd.darwin\n"
            "   25     1 Zs   /usr/libexec/backboardd\n"
            "SWEET hb: n=1 ps pid=26 status=0 ms=5\n"
        )
        r3 = AN.analyze_stage_b_text(t3, jobs)
        self.assertEqual(r3["row"], 3)
        self.assertFalse(r3["facts"]["backboardd_alive_in_last_list"])
        self.assertEqual(len(r3["facts"]["backboardd_exits"]), 1)
        self.assertIn("Service exited due to SIGABRT", r3["reason"])

        # B3 triggered solely by appearing in an earlier ps list then vanishing
        t3_list_only = (
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "   25     1 Ss   /usr/libexec/backboardd\n"
            "SWEET hb: n=1 ps pid=26 status=0 ms=5\n"
            "SWEET hb: n=2 pid=8 ppid=1 up=20\n"
            "  PID  PPID STAT COMM\n"
            "    1     0 Ss   /sbin/launchd.darwin\n"
            "SWEET hb: n=2 ps pid=27 status=0 ms=5\n"
        )
        r3_list = AN.analyze_stage_b_text(t3_list_only, jobs)
        self.assertEqual(r3_list["row"], 3)
        self.assertIn("absent/zombie in last ps list", r3_list["reason"])

        # B4 with earlier complete list (backboardd alive) followed by a cut trailing list
        t4_complete_plus_cut = (
            "init: library insertion: backboardd\n"
            "hakios: ca_vbl=1: ok\n"
            "SWEET hb: n=1 pid=8 ppid=1 up=10\n"
            "  PID  PPID STAT COMM\n"
            "    1     0 Ss   /sbin/launchd.darwin\n"
            "   25     1 Ss   /usr/libexec/backboardd\n"
            "SWEET hb: n=1 ps pid=29 status=0 ms=5\n"
            "SWEET hb: n=2 pid=8 ppid=1 up=20\n"
            "  PID  PPID STAT COMM\n"
            "    1     0 Ss   /sbin/launchd.darwin\n"
        )
        r4 = AN.analyze_stage_b_text(t4_complete_plus_cut, jobs)
        self.assertEqual(r4["row"], 4)
        self.assertEqual(r4["facts"]["eval_list_round"], 1)
        self.assertFalse(r4["facts"]["eval_list_cut"])
        self.assertIn("alive in last complete ps list", r4["reason"])
        self.assertTrue(r4["facts"]["backboardd_alive_in_last_list"])
        self.assertEqual(r4["facts"]["hakios_lines"], ["ca_vbl=1: ok"])

        # B4 when ONLY cut trailing lists exist (two cut lists verify [-1] vs [-0])
        t4_cut_only = (
            "init: library insertion: backboardd\n"
            "  PID  PPID STAT COMM\n"
            "    1     0 Ss   /sbin/launchd.darwin\n"
            "[... 10 bytes lost in transport ...]\n"
            "  PID  PPID STAT COMM\n"
            "   25     1 Ss   /usr/libexec/backboardd\n"
        )
        r4_cut = AN.analyze_stage_b_text(t4_cut_only, jobs)
        self.assertEqual(r4_cut["row"], 4)
        self.assertTrue(r4_cut["facts"]["eval_list_cut"])
        self.assertIn("alive in last trailing ps list", r4_cut["reason"])

        # B5: swaps + 1 pixel boundary (> 1 vs > 0 mutant killed with 1 pixel!) vs 0 pixels
        t5 = t4_complete_plus_cut + (
            "MiniIOMobileFramebuffer: notification port for type 2\n"
            "MiniIOMobileFramebuffer: swap 7 (#3): surfaces 11 0 0 0, layers set 0x1 cleared 0x0\n"
            "MiniIOMobileFramebuffer: swap #3: surfaces in layers 0x1 now (0x0 before): 11 0 0 0\n"
            "MiniIOMobileFramebuffer: 0 pixels of the panel changed a frame, all within 0,0 to 0,0\n"
        )
        r5 = AN.analyze_stage_b_text(t5, jobs)
        self.assertEqual(r5["row"], 5)
        self.assertEqual(r5["reason"], "2 MiniIOMobileFramebuffer swap line(s) seen, no positive pixel-diff line")
        self.assertEqual(r5["facts"]["fb_swaps"][0], dict(kind="swap", swap_id=7, swap_shown=3, surfaces="11 0 0 0"))
        self.assertEqual(r5["facts"]["fb_swaps"][1], dict(kind="layers", swap_shown=3, now="0x1", before="0x0"))
        self.assertEqual(r5["facts"]["fb_notify_types"], [2])

        # B6 exact 1 pixel diff kills > 0 -> > 1 mutant, and full fields on distinct box
        t6 = t5 + (
            "MiniIOMobileFramebuffer: 120 frames in 5000 ms (24 a second), 100 us each in the driver, after 10 us waiting for the GPU and, 10 of them, 50 us for the next refresh; 0 swaps waited for the frame before, 0 gave up; 0 swaps came a refresh late themselves\n"
            "MiniIOMobileFramebuffer: 1 pixels of the panel changed a frame, all within 12,34 to 567,890\n"
        )
        r6 = AN.analyze_stage_b_text(t6, jobs)
        self.assertEqual(r6["row"], 6)
        self.assertEqual(r6["name"], "panel-pixels-changed")
        self.assertEqual(r6["facts"]["fb_pixel_diffs"][-1], dict(pixels=1, left=12, top=34, right=567, bottom=890))
        self.assertEqual(r6["facts"]["fb_stats"][0], dict(frames=120, ms=5000, fps=24))

    def test_analyze_cli_dispatch(self):
        d = make_scratch("cli_")
        try:
            out_sb = d / "sb.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = AN.main(["--mode", "stage-b", "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(JOBS106_DIR), "--out", str(out_sb)])
            self.assertEqual(rc, 0)
            self.assertTrue(buf.getvalue().startswith("row B2 "))
            raw_sb = out_sb.read_text()
            self.assertIn('\n "row": 2,\n', raw_sb)

            buf_hb = io.StringIO()
            with contextlib.redirect_stdout(buf_hb):
                rc_hb = AN.main(["--mode", "hb", "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(JOBS101_DIR)])
            self.assertEqual(rc_hb, 0)
            self.assertTrue(buf_hb.getvalue().startswith("row H5 "))

            buf_sa = io.StringIO()
            with contextlib.redirect_stdout(buf_sa):
                rc_sa = AN.main(["--mode", "stage-a", "--archive", str(NAT105_ARCHIVE), "--jobs-dir", str(JOBS101_DIR)])
            self.assertEqual(rc_sa, 0)
            self.assertTrue(buf_sa.getvalue().startswith("row A1 "))

            base_chain = ["--mode", "chain", "--archive", str(NAT105_ARCHIVE), "--events", "e", "--report", "r", "--delivery", "del", "--root", "root", "--size", "1", "--sha256", "ab"]
            with mock.patch.object(sys, "stderr", new=io.StringIO()):
                for missing_flag in ("--events", "--report", "--delivery", "--root", "--size", "--sha256"):
                    idx = base_chain.index(missing_flag)
                    reduced = base_chain[:idx] + base_chain[idx + 2:]
                    with self.assertRaises(SystemExit):
                        AN.main(reduced)
                with self.assertRaises(SystemExit):
                    AN.main(["--mode", "hb", "--archive", str(NAT105_ARCHIVE)])

            with mock.patch.object(AN, "analyze_chain", return_value={"row": 1, "_exit_code": 7}) as mc:
                buf2 = io.StringIO()
                with contextlib.redirect_stdout(buf2):
                    rc2 = AN.main(base_chain)
            self.assertEqual(rc2, 7)
            self.assertEqual(mc.call_count, 1)
            self.assertIn('\n "row": 1\n', buf2.getvalue())
            self.assertEqual(json.loads(buf2.getvalue()), {"row": 1})

            hp = subprocess.run([sys.executable, "-B", "-I", str(HERE / "analyze_nat106.py"), "--help"], capture_output=True, text=True)
            self.assertEqual(hp.returncode, 0)
            self.assertIn("stage-b", hp.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDeriveAndSession(unittest.TestCase):
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
        cfg = S106.IMAGES["loader-diag-xnu-sb2-md1"]
        dec = S106.gate("loader-diag-xnu-sb2-md1", cfg)
        self.assertTrue(dec.name.startswith("0040-nat106-loader-diag-xnu-sb2-md1-single-run-"))

        d = make_scratch("gate_")
        try:
            fake_root = d / "repo"
            (fake_root / "state").mkdir(parents=True)
            req = {tid: {"id": tid, "status": "done"} for tid in S106.REQUIRED_DONE}
            st = {
                "project": {
                    "permissions": {"native": True},
                    "permission_decisions": [{"scope": "native", "value": True, "decision": "docs/decisions/" + dec.name}],
                },
                "tasks": list(req.values()),
            }
            lab_json = fake_root / "state/lab.json"
            lab_json.write_text(json.dumps(st))
            with mock.patch.object(S106, "ROOT", fake_root):
                self.assertIsNone(S106.registry_blocker(dec))

                st["project"]["permissions"]["native"] = False
                lab_json.write_text(json.dumps(st))
                self.assertIsNotNone(S106.registry_blocker(dec))

                st["project"]["permissions"]["native"] = True
                req["NAT-106"]["status"] = "in_progress"
                lab_json.write_text(json.dumps(st))
                self.assertIn("NAT-106", S106.registry_blocker(dec))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
