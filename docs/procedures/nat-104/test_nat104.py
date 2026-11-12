#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-104 host tests: build wrapper & glue62_impl.h patcher, compiled C host harness (-DNAT062_HOST -Werror), byte-for-byte payload comparison vs NAT-102, analyze_nat104.py (over TAIL_MAX[2]=262144), derive104.py, and session_nat104.py. Evidence kind: host-test. Nothing runs on a phone."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import random
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
PKG104 = ROOT / "artifacts/nat-104/package-001/package.json"
BUILD104 = ROOT / "artifacts/nat-104/build-001/loader-diag-xnu-hb2-md1/Image.payload"
BUILD102 = ROOT / "artifacts/nat-102/build-001/loader-diag-xnu-hb-md1/Image.payload"
BUILD104_JSON = ROOT / "artifacts/nat-104/build-001/build.json"
BUILT_GLUE104 = ROOT / "artifacts/nat-104/build-001/loader-diag-xnu-hb2-md1/source/shim/e1s-xnu/glue62_impl.h"
NAT103_RUN = ROOT / "artifacts/nat-103/run-001"
JOBS_DIR = ROOT / "artifacts/nat-101/pid1-hb/root/LaunchDaemons"
SCRATCH = ROOT / "artifacts/nat-104/tmp"
CMDLINE_OFF, CMDLINE_LEN = 0x48, 608
LOADER_BYTES = 385024
MD0_BYTES = 4194304
HEAD_RETURN = 8192
TAIL_RETURN = 262144
TAIL_RETURN_102 = 32768
HEAD_FINAL = 8192
TAIL_FINAL = 8192

LOG_VA = 0xFFFFFFF007B90A00
PA = 0x9A2B0A00
DELTA = (PA - LOG_VA) % (1 << 64)

sha = lambda b: hashlib.sha256(b).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B = load("nat104_test_build", HERE / "build.py")
D = load("nat104_test_derive", HERE / "derive104.py")
AN = load("nat104_test_analyze", HERE / "analyze_nat104.py")
S104 = load("nat104_test_session", HERE / "session_nat104.py")

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


def pattern(n, seed=1):
    r = random.Random(seed)
    vals = list(range(256))
    out = bytearray()
    while len(out) < n:
        r.shuffle(vals)
        out += bytes(vals)
        out += b"xnu: [ 1.234] CPU0: hello \\ world\r\n"
    return bytes(out[:n])


def encode_kl_lines(raw_bytes, why=2, head_max=HEAD_RETURN, tail_max=TAIL_RETURN, drop_begin=False):
    """Produce NAT-062 formatted KL lines from raw console bytes using literal Python encoding."""
    n = len(raw_bytes)
    head = min(n, head_max)
    tail = min(n - head, tail_max)
    gap = n - head - tail
    lines = []
    if not drop_begin:
        lines.append("KL begin why=%d len=%d head=%d tail=%d gap=%d x0=0x%x" % (why, n, head, tail, gap, PA))
    recs = 0

    def emit_range(lo, hi):
        nonlocal recs
        for off in range(lo, hi, 96):
            chunk = raw_bytes[off:min(hi, off + 96)]
            esc = []
            for b in chunk:
                if b == 0x5C:
                    esc.append("\\\\")
                elif b == 0x0A:
                    esc.append("\\n")
                elif b == 0x0D:
                    esc.append("\\r")
                elif 0x20 <= b < 0x7F:
                    esc.append(chr(b))
                else:
                    esc.append("\\x%02x" % b)
            lines.append("KL %06x %s" % (off, "".join(esc)))
            recs += 1

    emit_range(n - tail, n)
    emit_range(0, head)
    lines.append("KL end why=%d recs=%d bytes=%d" % (why, recs, head + tail))
    return lines


def write_synthetic_archive(root, kl_lines, drops=()):
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


class BuildWrapper(unittest.TestCase):
    def md0(self, d, size=MD0_BYTES, fill=b"\x5a"):
        p = Path(d) / "root.apfs"
        p.write_bytes(fill * size)
        return p, sha(fill * size)

    def go(self, argv, record_md0=None, change=None, raises=None, write=True, pin="file", run_prepare=True, final=True):
        seen = {}
        if pin == "file" and "--ramdisk" in argv:
            pin = sha(Path(argv[argv.index("--ramdisk") + 1]).read_bytes())

        def b87_main():
            seen["name"], seen["tag"] = B.b87.NAME, B.b87.NEW_TAG
            if raises:
                raise raises
            if run_prepare:
                src_dir = Path(argv[argv.index("--out") + 1]) / "_src" if "--out" in argv else None
                if src_dir is not None:
                    e1s = src_dir / "shim" / "e1s-xnu"
                    e1s.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(SRC62 / "glue62_impl.h", e1s / "glue62_impl.h")
                    self.assertEqual(B.b62.prepare_tree(src_dir, 360, final), 83)
            if "--out" in argv and write:
                rec = {
                    "nat083_changes": {"md0_image": record_md0},
                    "nat087_changes": change if change is not None else {
                        "image_name": B.NAME,
                        "cmdline_tag": B.NEW_TAG,
                        "cmdline": "rd=md1 x xrd=md0",
                    },
                    "other": 1,
                }
                (Path(argv[argv.index("--out") + 1]) / "build.json").write_text(json.dumps(rec))

        before = (B.b87.NAME, B.b87.NEW_TAG, B.b62.prepare_tree)
        orig_prepare = B.b62.prepare_tree
        with mock.patch.object(B.b87, "main", b87_main), \
             mock.patch.object(B.b62, "prepare_tree", lambda s, d, f=True: 83), \
             mock.patch.object(sys, "argv", ["build.py"] + argv), \
             mock.patch.object(B, "MD0_SHA256", pin if pin not in (None, "file") else B.MD0_SHA256):
            try:
                B.main()
            finally:
                seen["after"] = (B.b87.NAME, B.b87.NEW_TAG)
        self.assertIs(B.b62.prepare_tree, orig_prepare)
        seen["before"] = before[:2]
        return seen

    def test_constants(self):
        self.assertEqual((B.NAME, B.NEW_TAG), ("loader-diag-xnu-hb2-md1", "nat_attempt=NAT104-hb2"))
        self.assertEqual((B.MD0_BYTES, B.BURST_NEW, B.TAIL_RETURN_NEW, B.RETURN_SETTLE_WAITS), (MD0_BYTES, 4096, 262144, 10))
        self.assertEqual(len(B.NAME), len("loader-diag-xnu-hb-md1") + 1)
        self.assertEqual(len(B.NEW_TAG), len("nat_attempt=NAT102-hb1"))

    def test_patch_glue104_and_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "glue62_impl.h"
            orig = (SRC62 / "glue62_impl.h").read_text()
            p.write_text(orig)
            digest = B.patch_glue104(p)
            patched = p.read_text()
            self.assertEqual(digest, sha(patched.encode()))
            self.assertIn("#define NAT062_BURST\t\t4096u", patched)
            self.assertIn("#define NAT062_TAIL_RETURN\t262144u", patched)
            self.assertIn("for (uint32_t w = 0; w < 10u; w++)\n\t\t\tN62_WAIT();", patched)
            self.assertIn("#define NAT062_TAIL_FINAL\t8192u", patched)
            if BUILD104_JSON.is_file():
                rec = json.loads(BUILD104_JSON.read_text())
                self.assertEqual(digest, rec["nat104_changes"]["glue62_impl_sha256"])

            # Refuses 0 or 2 occurrences of every rule without mutating the file
            for label, old, _ in B.PATCH_RULES:
                for count_case, bad_text in (("zero", orig.replace(old, "/*MISSING*/")), ("two", orig + "\n" + old)):
                    p.write_text(bad_text)
                    with self.assertRaises(SystemExit, msg=(label, count_case)) as cm:
                        B.patch_glue104(p)
                    self.assertIn("patch_glue104 %s:" % label, str(cm.exception))
                    self.assertEqual(p.read_text(), bad_text)

    def test_main_success_and_restore(self):
        with tempfile.TemporaryDirectory() as d:
            p, h = self.md0(d)
            seen = self.go(["--ramdisk", str(p), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h))
            raw_rec = (Path(d) / "build.json").read_text()
            rec = json.loads(raw_rec)
            self.assertEqual(raw_rec, json.dumps(rec, indent=1))
            patched = (Path(d) / "_src/shim/e1s-xnu/glue62_impl.h").read_bytes()
        self.assertEqual((seen["name"], seen["tag"]), (B.NAME, B.NEW_TAG))
        self.assertEqual(seen["after"], seen["before"])
        self.assertEqual(rec["other"], 1)
        self.assertEqual(rec["nat104_sources"], {"build.py": sha((HERE / "build.py").read_bytes())})
        self.assertEqual(rec["nat104_changes"], {
            "image_name": B.NAME,
            "cmdline_tag": B.NEW_TAG,
            "md0_sha256": h,
            "md0_bytes": MD0_BYTES,
            "cmdline": "rd=md1 x xrd=md0",
            "glue62_impl_sha256": sha(patched),
            "burst_bytes": 4096,
            "tail_return_bytes": 262144,
            "return_settle_waits": 10,
        })
        self.assertIn("TAIL_RETURN=262144, BURST=4096", rec["nat104_note"])

    def test_refusals_and_edge_cases(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                self.go(["--out", d], run_prepare=False)
            self.assertIn("--ramdisk is required", str(cm.exception))

            bad_sz = Path(d) / "small.apfs"
            bad_sz.write_bytes(b"x" * 10)
            with self.assertRaises(SystemExit) as cm:
                self.go(["--ramdisk", str(bad_sz), "--out", d], run_prepare=False)
            self.assertIn("not 4194304", str(cm.exception))

            p, _ = self.md0(d)
            with self.assertRaises(SystemExit) as cm:
                self.go(["--ramdisk", str(p), "--out", d], pin="0" * 64, run_prepare=False)
            self.assertIn("not the pinned", str(cm.exception))

            p2, h = self.md0(d)
            with self.assertRaises(SystemExit) as cm:
                self.go(["--ramdisk", str(p2), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h), run_prepare=False)
            self.assertEqual(str(cm.exception), "glue62_impl.h hook never ran during prepare_tree")

            with self.assertRaises(SystemExit) as cm:
                self.go(["--ramdisk", str(p2), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h), final=False)
            self.assertEqual(str(cm.exception), "glue62_impl.h hook never ran during prepare_tree")

            with tempfile.TemporaryDirectory() as d2:
                p_no_out, _ = self.md0(d2)
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p_no_out), "--out", d2], write=False)
                self.assertEqual(str(cm.exception), "no build.json was written")

            for bad_md0 in (None, dict(bytes=MD0_BYTES, sha256="f" * 64), dict(bytes=MD0_BYTES - 1, sha256=h)):
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p2), "--out", d], record_md0=bad_md0)
                self.assertIn("build.json records md0", str(cm.exception))

            for bad_ch in ({}, {"image_name": "other", "cmdline_tag": B.NEW_TAG}, {"image_name": B.NAME, "cmdline_tag": "other"}):
                with self.assertRaises(SystemExit) as cm:
                    self.go(["--ramdisk", str(p2), "--out", d], record_md0=dict(bytes=MD0_BYTES, sha256=h), change=bad_ch)
                self.assertIn("does not carry this image's name and tag", str(cm.exception))

        # No --out does not require build.json
        with tempfile.TemporaryDirectory() as d:
            p, _ = self.md0(d)
            seen = self.go(["--ramdisk", str(p)], run_prepare=False)
            self.assertEqual(seen["name"], B.NAME)

        # Raise during b87.main restores globals
        with tempfile.TemporaryDirectory() as d:
            p, _ = self.md0(d)
            with self.assertRaises(RuntimeError):
                self.go(["--ramdisk", str(p), "--out", d], raises=RuntimeError("boom"), run_prepare=False)
        self.assertNotEqual(B.b87.NAME, B.NAME)

        # --check-only skips --ramdisk check
        with tempfile.TemporaryDirectory() as d:
            dpath = Path(d)
            self.go(["--check-only", "--out", d], run_prepare=False, write=False)
            self.assertEqual(os.listdir(dpath), [])

        # Subprocess CLI
        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "build.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--ramdisk is required", r.stderr)


@unittest.skipUnless(
    PKG104.is_file() and BUILD104.is_file() and BUILD102.is_file() and BUILD104_JSON.is_file(),
    "built NAT-104/NAT-102 artifacts not present",
)
class BuiltPayload(unittest.TestCase):
    def test_payload_diff_vs_nat102_is_only_three_cmdline_bytes_and_loader(self):
        b104 = BUILD104.read_bytes()
        b102 = BUILD102.read_bytes()
        self.assertEqual(len(b104), len(b102))
        tail_diffs = [
            (i, chr(b102[i]), chr(b104[i]))
            for i in range(LOADER_BYTES, len(b104))
            if b104[i] != b102[i]
        ]
        # NAT102-hb1 -> NAT104-hb2 differs strictly in the cmdline tag digits within the cmdline header field
        self.assertTrue(all(LOADER_BYTES + CMDLINE_OFF <= i < LOADER_BYTES + CMDLINE_OFF + CMDLINE_LEN for i, _, _ in tail_diffs))
        self.assertEqual(len(tail_diffs), 2, tail_diffs)
        cmd104 = b104[LOADER_BYTES + CMDLINE_OFF:LOADER_BYTES + CMDLINE_OFF + CMDLINE_LEN].rstrip(b"\0").decode()
        cmd102 = b102[LOADER_BYTES + CMDLINE_OFF:LOADER_BYTES + CMDLINE_OFF + CMDLINE_LEN].rstrip(b"\0").decode()
        self.assertEqual(cmd104, cmd102.replace("NAT102-hb1", "NAT104-hb2"))
        self.assertLess(len(cmd104), 256)
        self.assertTrue(cmd104.endswith(" xrd=md0"))

    def test_package_and_built_glue_hashes(self):
        pkg_doc = json.loads(PKG104.read_text())
        img = pkg_doc["images"][B.NAME]
        rec_path = ROOT / "artifacts/nat-104/package-001" / B.NAME / "recovery.img"
        self.assertEqual(sha(rec_path.read_bytes()), img["recovery_sha256"])
        self.assertEqual(len(rec_path.read_bytes()), img["recovery_bytes"])
        self.assertEqual(sha(BUILD104.read_bytes()), img["payload_sha256"])
        self.assertEqual(len(BUILD104.read_bytes()), img["payload_bytes"])
        self.assertFalse(pkg_doc["flashed"])
        if BUILT_GLUE104.is_file():
            rec = json.loads(BUILD104_JSON.read_text())
            self.assertEqual(sha(BUILT_GLUE104.read_bytes()), rec["nat104_changes"]["glue62_impl_sha256"])


@needs_cc
class CHostHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_scratch("host-")
        impl = cls.tmp / "src"
        impl.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC62 / "glue62.h", impl / "glue62.h")
        shutil.copy2(SRC62 / "glue62_impl.h", impl / "glue62_impl.h")
        B.patch_glue104(impl / "glue62_impl.h")
        h = cls.tmp / "harness.c"
        h.write_text(HARNESS.replace("@N47@", n47_text()))
        cls.exe = cls.tmp / "harness"
        r = subprocess.run(
            ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-I", str(impl), str(h), "-o", str(cls.exe)],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def dump(self, log, why=2, *, x0=None, x1=None, up=1, delta=DELTA):
        x0 = (LOG_VA + delta) % (1 << 64) if x0 is None else x0
        x1 = len(log) if x1 is None else x1
        f = self.tmp / "mem.bin"
        f.write_bytes(log)
        r = subprocess.run(
            [str(self.exe), "%x" % (x0 % (1 << 64)), "%x" % x1, "%x" % delta, str(why), str(up), str(f)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        recs, waits = [], []
        for line in r.stdout.splitlines():
            if line == "W":
                waits.append(len(recs))
            else:
                self.assertTrue(line.startswith("R "), line)
                recs.append(line[2:])
        m = re.match(r"reads=(\d+)", r.stderr.strip().splitlines()[-1])
        return recs, waits, int(m.group(1))

    def parse(self, recs):
        with AN.patched_tail():
            dumps, stray = AN.A102.R2.A62.parse_kl(recs)
        self.assertEqual(stray, [])
        return dumps

    def test_116430_and_exact_window_270336_have_zero_gap_and_full_recovery(self):
        for n in (116430, HEAD_RETURN + TAIL_RETURN):
            with self.subTest(n=n):
                log = pattern(n, seed=n)
                recs, waits, reads = self.dump(log, why=2)
                (d,) = self.parse(recs)
                self.assertEqual((d["status"], d["problems"]), ("complete", []))
                self.assertEqual((d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"]), (HEAD_RETURN, n - HEAD_RETURN, 0))
                self.assertEqual(reads, n)
                self.assertEqual(b"".join(r for _, r in sorted(d["records"])), log)
                # 10 settle waits strictly before the KL begin record
                self.assertEqual(waits[:10], [0] * 10, waits[:15])

    def test_270337_has_gap_of_one(self):
        n = HEAD_RETURN + TAIL_RETURN + 1
        log = pattern(n, seed=77)
        recs, waits, reads = self.dump(log, why=2)
        (d,) = self.parse(recs)
        self.assertEqual((d["status"], d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"], reads), ("complete", HEAD_RETURN, TAIL_RETURN, 1, HEAD_RETURN + TAIL_RETURN))
        by_off = dict(d["records"])
        got = b"".join(by_off[o] for o in sorted(by_off) if o < HEAD_RETURN) + b"?" + b"".join(by_off[o] for o in sorted(by_off) if o >= HEAD_RETURN + 1)
        self.assertEqual(got, log[:HEAD_RETURN] + b"?" + log[HEAD_RETURN + 1:])
        self.assertEqual(waits[:10], [0] * 10)

    def test_why1_final_has_zero_pre_begin_waits_and_keeps_8k_plus_8k_window(self):
        n = 20000
        log = pattern(n, seed=9)
        recs, waits, reads = self.dump(log, why=1)
        (d,) = self.parse(recs)
        self.assertEqual((d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"], reads), (HEAD_FINAL, TAIL_FINAL, n - HEAD_FINAL - TAIL_FINAL, HEAD_FINAL + TAIL_FINAL))
        self.assertTrue(all(w > 0 for w in waits), waits[:5])

    def test_burst_pacing_stays_under_one_third_of_32k_ring(self):
        log = pattern(120000, seed=11)
        recs, waits, _ = self.dump(log, why=2)
        self.assertEqual(waits[:10], [0] * 10)
        # Exclude the 10 pre-begin settle waits and the trailing wait after KL end
        burst_waits = [w for w in waits[10:-1]]
        prev = 1  # index after KL begin record
        for w in burst_waits:
            chunk_bytes = sum(len(r) + 16 for r in recs[prev:w])
            self.assertGreaterEqual(chunk_bytes, 4096)
            self.assertLess(chunk_bytes, 4096 + 448 + 16)
            self.assertLess(chunk_bytes * 3, 32768)
            prev = w

    def test_up_zero_and_bad_address_refused(self):
        recs, waits, reads = self.dump(pattern(100), why=2, up=0)
        self.assertEqual((recs, waits, reads), ([], [], 0))
        recs, _, reads = self.dump(pattern(100), why=2, x0=PA + 8)
        self.assertEqual(reads, 0)
        self.assertTrue(len(recs) == 1 and recs[0].startswith("KL refused why=2 "))


class AnalyzeNat104(unittest.TestCase):
    def make_120k_console(self, at_offset=80000, tail_bytes=40000):
        head = b"init: starting\n/redwood/etc/rc starting hb\n"
        line = b"kernel: [ 45.000] boot noise line 0123456789abcdef\n"
        filler = line * ((at_offset // len(line)) + 2)
        prefix = (head + filler)[:at_offset - 1] + b"\n"
        hb_block = (
            b"SWEET hb: start pid=11 ppid=1 period=10s rounds=60 ps_timeout=8s\n"
            b"SWEET hb: n=1 pid=11 ppid=1 up=0\n"
            b"  PID TTY           TIME CMD\n"
            b"    1 ??         0:00.10 /sbin/launchd\n"
            b"   11 ??         0:00.01 /redwood/bin/hb\n"
            b"   18 ??         0:00.02 /usr/libexec/logd\n"
            b"   19 ??         0:00.00 ps -A\n"
            b"SWEET hb: n=1 ps pid=19 status=0 ms=45\n"
        )
        tline = b"[ 216.000]: tail line 0123456789abcdef\n"
        tail = b"\n--- kernel message buffer ---\n" + (tline * ((tail_bytes // len(tline)) + 1))[:tail_bytes]
        return prefix + hb_block + tail

    def test_patched_tail_restores_on_exit_and_exception(self):
        before = (AN.A87.A65.A62.TAIL_MAX[2], AN.A97.R2.A62.TAIL_MAX[2], AN.A102.R2.A62.TAIL_MAX[2])
        self.assertEqual(before, (TAIL_RETURN_102, TAIL_RETURN_102, TAIL_RETURN_102))
        with AN.patched_tail():
            inside = (AN.A87.A65.A62.TAIL_MAX[2], AN.A97.R2.A62.TAIL_MAX[2], AN.A102.R2.A62.TAIL_MAX[2])
            self.assertEqual(inside, (TAIL_RETURN, TAIL_RETURN, TAIL_RETURN))
        self.assertEqual((AN.A87.A65.A62.TAIL_MAX[2], AN.A97.R2.A62.TAIL_MAX[2], AN.A102.R2.A62.TAIL_MAX[2]), before)
        with self.assertRaises(ZeroDivisionError):
            with AN.patched_tail():
                1 // 0
        self.assertEqual((AN.A87.A65.A62.TAIL_MAX[2], AN.A97.R2.A62.TAIL_MAX[2], AN.A102.R2.A62.TAIL_MAX[2]), before)

    def test_120k_synthetic_archive_with_and_without_begin_reaches_h5_zero_gap(self):
        if not JOBS_DIR.is_dir():
            self.skipTest("JOBS_DIR not present")
        raw = self.make_120k_console(80000)
        self.assertGreater(len(raw), 118000)
        for drop_begin in (False, True):
            with self.subTest(drop_begin=drop_begin), tempfile.TemporaryDirectory() as d:
                arch = Path(d) / "archive"
                write_synthetic_archive(arch, encode_kl_lines(raw, why=2, drop_begin=drop_begin))
                out_json = Path(d) / "out.json"
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = AN.main(["--mode", "hb", "--archive", str(arch), "--jobs-dir", str(JOBS_DIR), "--out", str(out_json)])
                self.assertEqual(rc, 0)
                raw_out = out_json.read_text()
                res = json.loads(raw_out)
                self.assertEqual(raw_out, json.dumps(res, indent=1) + "\n")
                self.assertEqual(res["row"], 5)
                self.assertEqual(res["name"], "hb-ps-lists")
                self.assertEqual(res["facts"]["gap_bytes"], 0)
                self.assertEqual(res["dump"]["begin_inferred"], drop_begin)
                self.assertIn("row H5 hb-ps-lists:", buf.getvalue())
                self.assertIn("hb_marks=1, lists=1, gap=0, hole=0)", buf.getvalue())
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(AN.main(["--mode", "hb", "--archive", str(arch), "--jobs-dir", str(JOBS_DIR)]), 0)

    def test_280k_lost_begin_caps_at_262144_not_infinite(self):
        if not JOBS_DIR.is_dir():
            self.skipTest("JOBS_DIR not present")
        raw = self.make_120k_console(200000) + (b"padding line\n" * 8000)
        self.assertGreater(len(raw), 280000)
        with tempfile.TemporaryDirectory() as d:
            arch = Path(d) / "archive"
            write_synthetic_archive(arch, encode_kl_lines(raw, why=2, tail_max=TAIL_RETURN, drop_begin=True))
            res = AN.analyze_hb(arch, JOBS_DIR)
            self.assertEqual(res["dump"]["begin_inferred"], True)
            self.assertEqual(res["dump"]["begin"]["tail"], TAIL_RETURN)
            self.assertEqual(res["facts"]["gap_bytes"], len(raw) - HEAD_RETURN - TAIL_RETURN)
            self.assertEqual(res["row"], 5)

    def test_nat103_40960_capped_lost_begin_is_refused_by_262144_geometry(self):
        if not (NAT103_RUN / "archive").is_dir() or not JOBS_DIR.is_dir():
            self.skipTest("NAT-103 archive not present")
        res = AN.analyze_hb(NAT103_RUN / "archive", JOBS_DIR)
        self.assertEqual(res["row"], 0)
        self.assertIn("not on the inferred grid", res["reason"])

    def test_stage_a_and_chain_modes_and_cli_errors(self):
        if not JOBS_DIR.is_dir():
            self.skipTest("JOBS_DIR not present")
        raw = (
            b"$ exec /sbin/launchd\n"
            b"restore mode\n"
            b"[  10.000]: Waiting for DSMOS\n"
            + b"x" * 90000
            + b"\n  PID TTY           TIME CMD\n    1 ?? 0:00.1 /sbin/launchd\n   18 ?? 0:00.1 /usr/libexec/logd\n"
        )
        with tempfile.TemporaryDirectory() as d:
            arch = Path(d) / "archive"
            write_synthetic_archive(arch, encode_kl_lines(raw, why=2, drop_begin=True))
            sa = AN.analyze_stage_a(arch, JOBS_DIR)
            self.assertEqual(sa["dump"]["begin_inferred"], True)
            self.assertEqual(sa["dump"]["begin"]["tail"], len(raw) - HEAD_RETURN)
            self.assertEqual(sa["facts"]["gap_bytes"], 0)
            out_sa = Path(d) / "sa.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = AN.main(["--mode", "stage-a", "--archive", str(arch), "--jobs-dir", str(JOBS_DIR), "--out", str(out_sa)])
            self.assertEqual(rc, 0)
            self.assertIn("row A%d" % sa["row"], buf.getvalue())
            self.assertEqual(json.loads(out_sa.read_text())["dump"]["begin"]["gap"], 0)

        if (NAT103_RUN / "archive").is_dir():
            with tempfile.TemporaryDirectory() as d:
                out_c = Path(d) / "chain.json"
                log_c = Path(d) / "log.txt"
                root_img = ROOT / "artifacts/nat-083/system-padded.apfs"
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = AN.main([
                        "--mode", "chain",
                        "--archive", str(NAT103_RUN / "archive"),
                        "--events", str(NAT103_RUN / "usb-events.jsonl"),
                        "--report", str(NAT103_RUN / "report.json"),
                        "--delivery", str(NAT103_RUN / "delivery/delivery.json"),
                        "--root", str(root_img),
                        "--size", str(root_img.stat().st_size),
                        "--sha256", "4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6",
                        "--image", "loader-diag-xnu-hb-md1",
                        "--out", str(out_c),
                        "--log-out", str(log_c),
                    ])
                self.assertEqual(rc, 0)
                chain_raw = buf.getvalue()
                chain_out = json.loads(chain_raw)
                self.assertEqual(chain_raw, json.dumps(chain_out, indent=1) + "\n")
                self.assertEqual(chain_out["verdict"], "PARTIAL")
                self.assertEqual(chain_out["nat087"]["restore"]["row"], 9)
                self.assertTrue(out_c.is_file() and log_c.is_file())

                # Refuses overwriting existing --out (rc=2) and forwards --allow-synthetic
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    rc_exists = AN.main([
                        "--mode", "chain",
                        "--archive", str(NAT103_RUN / "archive"),
                        "--events", str(NAT103_RUN / "usb-events.jsonl"),
                        "--report", str(NAT103_RUN / "report.json"),
                        "--delivery", str(NAT103_RUN / "delivery/delivery.json"),
                        "--root", str(root_img),
                        "--size", str(root_img.stat().st_size),
                        "--sha256", "4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6",
                        "--image", "loader-diag-xnu-hb-md1",
                        "--out", str(out_c),
                    ])
                self.assertEqual(rc_exists, 2)
                seen_argv = []
                def fake_a87():
                    seen_argv.clear()
                    seen_argv.extend(sys.argv)
                    print(json.dumps({"verdict": "simulated-partial"}))
                    return 0
                saved_argv_before = list(sys.argv)
                with mock.patch.object(AN.A87, "main", fake_a87):
                    res_plain = AN.analyze_chain(
                        NAT103_RUN / "archive", NAT103_RUN / "usb-events.jsonl",
                        NAT103_RUN / "report.json", NAT103_RUN / "delivery/delivery.json",
                        root_img, 10, "ab", image="loader-diag-xnu-hb2-md1",
                    )
                    self.assertEqual(sys.argv, saved_argv_before)
                    self.assertNotIn("--out", seen_argv)
                    self.assertNotIn("--log-out", seen_argv)
                    self.assertNotIn("--allow-synthetic", seen_argv)
                    self.assertEqual(res_plain["verdict"], "simulated-partial")

                    res_syn = AN.analyze_chain(
                        NAT103_RUN / "archive", NAT103_RUN / "usb-events.jsonl",
                        NAT103_RUN / "report.json", NAT103_RUN / "delivery/delivery.json",
                        root_img, 10, "ab", image="loader-diag-xnu-hb2-md1", allow_synthetic=True,
                    )
                self.assertEqual(sys.argv, saved_argv_before)
                self.assertEqual(res_syn["verdict"], "simulated-partial")
                self.assertIn("--allow-synthetic", seen_argv)
                self.assertIn("loader-diag-xnu-hb2-md1", seen_argv)

        err1, err2 = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err1):
            with self.assertRaises(SystemExit):
                AN.main(["--mode", "hb", "--archive", "x"])
        self.assertIn("--mode hb requires --jobs-dir", err1.getvalue())
        with contextlib.redirect_stderr(err2):
            with self.assertRaises(SystemExit):
                AN.main([
                    "--mode", "chain", "--archive", "x",
                    "--events", "e", "--report", "r", "--delivery", "d", "--root", "o", "--size", "1",
                ])
        self.assertIn("--mode chain requires --sha256", err2.getvalue())


class SessionDriver104(unittest.TestCase):
    @unittest.skipUnless(PKG104.is_file(), "artifacts/nat-104/package-001 not present")
    def test_committed_driver_matches_derivation(self):
        text, done = D.build()
        self.assertEqual((HERE / "session_nat104.py").read_text(), text)
        self.assertEqual(len(done), 9)
        self.assertTrue(all(n == 1 for _, n in done))

    @unittest.skipUnless(PKG104.is_file(), "artifacts/nat-104/package-001 not present")
    def test_driver_contents_and_gate(self):
        pkg = json.loads(PKG104.read_text())["images"][D.IMAGE_NEW]
        t = (HERE / "session_nat104.py").read_text()
        self.assertEqual(t.count(pkg["recovery_sha256"]), 1)
        self.assertEqual(t.count(pkg["payload_sha256"]), 1)
        self.assertIn("CANARY_LEN=%d" % pkg["payload_bytes"], t)
        for old in (D.OLD_SHA, D.OLD_PAYLOAD_SHA, "artifacts/nat-102/package-001", "nat102-%s-single-run", "artifacts/nat-102/native-attempt", D.IMAGE_OLD):
            self.assertNotIn(old, t)
        self.assertIn("'NAT-097','NAT-101','NAT-102','NAT-104')", t)
        self.assertIn("analyze_nat104.py (--mode chain, stage-a and hb over NAT-104's 8192+262144 return window) (run separately)", t)

        # gate() and registry_blocker() checks over temporary fake ROOT
        cfg = S104.IMAGES[D.IMAGE_NEW]
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)
            (fake / "docs/decisions").mkdir(parents=True)
            (fake / "state").mkdir(parents=True)
            dec = fake / "docs/decisions/0039-nat104-loader-diag-xnu-hb2-md1-single-run-2026-11-12.md"
            dec.write_text("%s\n%s\ndecision 0019\n" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            req = list(S104.REQUIRED_DONE)
            lab = {
                "project": {
                    "permissions": {"native": True},
                    "permission_decisions": [{"scope": "native", "value": True, "decision": "docs/decisions/" + dec.name}],
                },
                "tasks": [{"id": tid, "status": "done"} for tid in req],
            }
            (fake / "state/lab.json").write_text(json.dumps(lab))
            with mock.patch.object(S104, "ROOT", fake):
                self.assertEqual(S104.gate(D.IMAGE_NEW, cfg), dec)
                self.assertIsNone(S104.registry_blocker(dec))
                lab["tasks"][-1]["status"] = "in_progress"
                (fake / "state/lab.json").write_text(json.dumps(lab))
                self.assertIn("NAT-104", S104.registry_blocker(dec))

    def test_drifted_and_missing_substitutions_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session_nat102.py"
            p.write_bytes(D.SRC.read_bytes() + b"# drift\n")
            with mock.patch.object(D, "SRC", p):
                with self.assertRaises(ValueError) as cm:
                    D.build()
            self.assertIn("not the file this derivation was written for", str(cm.exception))

            p.write_text(D.SRC.read_text().replace("'NAT-097','NAT-101','NAT-102')", "'NAT-097','NAT-101')"))
            with mock.patch.object(D, "SRC", p), mock.patch.object(D, "SRC_SHA256", sha(p.read_bytes())):
                with self.assertRaises(ValueError) as cm:
                    D.build()
            self.assertIn("required tasks: expected 1 occurrence(s)", str(cm.exception))

            pkg = json.loads(PKG104.read_text())
            pkg["images"][D.IMAGE_NEW]["payload_bytes"] += 8
            (Path(d) / "package.json").write_text(json.dumps(pkg))
            with mock.patch.object(D, "PACKAGE", Path(d)):
                with self.assertRaises(ValueError) as cm:
                    D.build()
            self.assertIn("CANARY_LEN", str(cm.exception))

    def test_derive_cli(self):
        def call(argv):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = D.main(argv)
            return rc, out.getvalue(), err.getvalue()

        self.assertEqual(call(["--check"]), (0, "ok: session_nat104.py equals the derivation (9 substitutions)\n", ""))
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / "session_nat104.py"
            other.write_text("diff")
            with mock.patch.object(D, "OUT", other):
                self.assertEqual(call(["--check"]), (1, "", "session_nat104.py differs from the derivation\n"))
            fake = Path(d)
            (fake / "docs/procedures/nat-104").mkdir(parents=True)
            out_f = fake / "docs/procedures/nat-104/session_nat104.py"
            with mock.patch.object(D, "ROOT", fake), mock.patch.object(D, "OUT", out_f):
                rc, out, err = call([])
            self.assertEqual((rc, err), (0, ""))
            self.assertEqual(json.loads(out)["out"], "docs/procedures/nat-104/session_nat104.py")
            drifted = Path(d) / "s102.py"
            drifted.write_text(D.SRC.read_text() + "\n# x\n")
            with mock.patch.object(D, "SRC", drifted), mock.patch.object(D, "OUT", Path(d) / "none.py"):
                rc, out, err = call([])
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused:"))

        r = subprocess.run([sys.executable, "-B", "-I", str(HERE / "derive104.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(D.OUT, HERE / "session_nat104.py")


if __name__ == "__main__":
    unittest.main()
