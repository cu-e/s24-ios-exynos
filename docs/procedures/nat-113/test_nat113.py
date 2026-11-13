#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-113 host tests (no phone): the pixel report (src/glue113.h) compiled for the host against synthetic physical memory,
the decoder (decode113.py) against its output, and the build's command line rules.

    python3 -B -I docs/procedures/nat-113/test_nat113.py -v
"""
import importlib.util
import os
import random
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


D = _load("nat113_decode", HERE / "decode113.py")

PANEL_PA, W, H, STRIDE = 0xfa200000, 1080, 2340, 4320
REC_VA = 0xfffffff007d10a08
DELTA = 0x18fa400000                      # PA - VA of NAT-111 (KL x0 0x901f90a00 for loader_log VA 0xfffffff007b90a00)
REC_SLOT_PA = (REC_VA + DELTA) % (1 << 64)
REC_PA = 0x900000000

HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define UNUSED __attribute__((unused))
struct region { uint64_t pa, len; uint8_t *b; };
static struct region g_r[3];
static uint64_t g_ticks;
static uint32_t rd32(uint64_t pa)
{
	for (int i = 0; i < 3; i++)
		if (g_r[i].b && pa >= g_r[i].pa && pa + 4 <= g_r[i].pa + g_r[i].len) {
			uint32_t v; memcpy(&v, g_r[i].b + (pa - g_r[i].pa), 4); return v;
		}
	fprintf(stderr, "OOB read at %llx\n", (unsigned long long)pa);
	exit(3);
}
static void emit(const char *b, const char *e) { fputs("R ", stdout); fwrite(b, 1, (size_t)(e - b), stdout); fputc('\n', stdout); }
static void wait_(void) { fputs("W\n", stdout); }
static void tick_(void) { g_ticks++; }
#define N62_EMIT(b, e) emit((b), (e))
#define N62_WAIT() wait_()
#define N113_R32(pa) rd32((uint64_t)(pa))
#define N113_TICK() tick_()
#define NAT062_BURST 4096u
#define NAT062_REC_MAX 448u
struct n62_out { uint32_t sent; uint32_t recs, bytes; };
@N47@
#include "glue113.h"
static uint8_t *load(const char *path, uint64_t *len)
{
	FILE *f = fopen(path, "rb"); if (!f) { *len = 0; return 0; }
	fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
	uint8_t *b = malloc((size_t)n + 1); *len = fread(b, 1, (size_t)n, f); fclose(f); return b;
}
int main(int argc, char **argv)
{
	if (argc != 8) return 2;
	for (int i = 0; i < 3; i++) {
		g_r[i].pa = strtoull(argv[1 + 2 * i], 0, 16);
		g_r[i].b = load(argv[2 + 2 * i], &g_r[i].len);
	}
	nat113_pixels(strtoull(argv[7], 0, 16));
	fprintf(stderr, "ticks=%llu\n", (unsigned long long)g_ticks);
	return 0;
}
'''


def n47_text():
    src = (PROC / "nat-047/src/markerlib47.c").read_text()
    out = []
    for name in ("n47_s", "n47_x", "n47_d"):
        m = re.search(r"static char \*%s\(.*?\n}\n" % name, src, re.S)
        out.append(m.group(0).replace("static char", "static UNUSED char", 1))
    return "\n".join(out)


def panel(fill=None, seed=0):
    """BGRA panel memory: zero, or `fill(x, y) -> (r, g, b)`."""
    b = bytearray(STRIDE * H)
    if fill:
        for y in range(H):
            row = y * STRIDE
            for x in range(W):
                r, g, bl = fill(x, y)
                b[row + 4 * x:row + 4 * x + 4] = bytes((bl, g, r, 0xff))
    return bytes(b)


def recording(frames, w=8, h=4, oldest=0, magic=b"RWREC003", frame_bytes=None):
    """A RWREC003 buffer: header, then per frame 8 bytes of time and w*h*3 bytes of RGB."""
    out = bytearray(magic + struct.pack("<IIIIQ", w, h, len(frames), oldest, 123456789))
    for i, px in enumerate(frames):
        out += struct.pack("<Q", 1000 * i)
        out += px if frame_bytes is None else frame_bytes
    return bytes(out)


needs_cc = unittest.skipUnless(subprocess.run(["cc", "--version"], capture_output=True).returncode == 0, "no host C compiler")


@needs_cc
class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="nat113-"))
        h = cls.tmp / "harness.c"
        h.write_text(HARNESS.replace("@N47@", n47_text()))
        cls.exe = cls.tmp / "harness"
        r = subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-I", str(HERE / "src"), str(h), "-o", str(cls.exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_report(self, panel_bytes, slot=(0, 0), rec=b"", rec_pa=REC_PA, fail_ok=False):
        p, s, r = self.tmp / "panel.bin", self.tmp / "slot.bin", self.tmp / "rec.bin"
        p.write_bytes(panel_bytes)
        s.write_bytes(struct.pack("<QQQ", slot[0], slot[1], 0))
        r.write_bytes(rec)
        out = subprocess.run([str(self.exe), "%x" % PANEL_PA, str(p), "%x" % REC_SLOT_PA, str(s), "%x" % rec_pa, str(r), "%x" % DELTA],
                             capture_output=True, text=True)
        if not fail_ok:
            self.assertEqual(out.returncode, 0, out.stderr)
        recs = [l[2:] for l in out.stdout.splitlines() if l.startswith("R ")]
        waits = out.stdout.splitlines().count("W")
        ticks = int(re.search(r"ticks=(\d+)", out.stderr).group(1)) if "ticks=" in out.stderr else None
        return recs, waits, ticks, out

    def test_black_panel_no_recording(self):
        recs, waits, ticks, _ = self.run_report(panel())
        rep = D.decode(recs)
        self.assertEqual(rep["panel"]["nonzero"], 0)
        self.assertEqual(len(rep["panel"]["rows"]), 234)
        self.assertTrue(all(set(r) == {0} for r in rep["panel"]["rows"]))
        self.assertEqual(rep["recording"]["state"], "none")
        self.assertTrue(rep["complete"])
        self.assertEqual(D.verdict(rep), "P0-black-no-recording")
        self.assertGreater(waits, 1)          # paced: the 32 KiB ring is never overrun by one burst
        self.assertGreaterEqual(ticks, 2340 // 64)

    def test_panel_counts_and_thumbnail(self):
        def fill(x, y):
            return (255, 0, 0) if (x < 540 and y < 1170) else (0, 0, 0)
        recs, _, _, _ = self.run_report(panel(fill))
        rep = D.decode(recs)
        self.assertEqual(rep["panel"]["nonzero"], 540 * 1170)
        rows = rep["panel"]["rows"]
        # sample (x = 5 + 10i, y = 5 + 10j): red (0xe0 in RGB332) iff x < 540 and y < 1170
        self.assertEqual(rows[0][0], 0xe0)
        self.assertEqual(rows[0][53], 0xe0)
        self.assertEqual(rows[0][54], 0)
        self.assertEqual(rows[116][0], 0xe0)
        self.assertEqual(rows[117][0], 0)
        self.assertEqual(D.verdict(rep), "P1-panel-has-pixels")

    def test_alpha_only_is_not_a_pixel(self):
        recs, _, _, _ = self.run_report(panel(lambda x, y: (0, 0, 0)))   # alpha 0xff, RGB 0
        self.assertEqual(D.decode(recs)["panel"]["nonzero"], 0)

    def test_fnv_matches_python(self):
        rnd = random.Random(7)
        pb = bytearray(rnd.randbytes(STRIDE * H))
        recs, _, _, _ = self.run_report(bytes(pb))
        rep = D.decode(recs)
        self.assertEqual(rep["panel"]["fnv"], D.fnv_panel(bytes(pb), W, H, STRIDE))

    def test_recording_frames(self):
        z = bytes(8 * 4 * 3)
        nz = bytes([0] * 95 + [7])
        rec = recording([z, nz, z])
        recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
        rep = D.decode(recs)
        r = rep["recording"]
        self.assertEqual(r["state"], "ok")
        self.assertEqual((r["w"], r["h"], r["frames"]), (8, 4, 3))
        self.assertEqual([f["nzb"] for f in r["list"]], [0, 1, 0])
        self.assertEqual([f["fnv"] for f in r["list"]], [D.fnv_bytes(z), D.fnv_bytes(nz), D.fnv_bytes(z)])
        self.assertEqual(D.verdict(rep), "R1-recording-has-pixels")

    def test_recording_all_zero(self):
        rec = recording([bytes(96)] * 2)
        recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
        self.assertEqual(D.verdict(D.decode(recs)), "R0-recording-black")

    def test_recording_refusals(self):
        rec = recording([bytes(96)])
        cases = {
            "below RAM": ((0x8fe3fff00, len(rec)), "refused"),
            "unaligned": ((REC_PA + 2, len(rec)), "refused"),
            "too long": ((REC_PA, (64 << 20) + 65), "refused"),
            "past RAM": ((0x9fe400000 - 16, 64), "refused"),
            "tiny": ((REC_PA, 16), "refused"),
        }
        for name, (slot, state) in cases.items():
            with self.subTest(name):
                recs, _, _, out = self.run_report(panel(), slot, rec)
                self.assertEqual(D.decode(recs)["recording"]["state"], state, out.stderr)

    def test_recording_half_set_slot(self):
        """Only an all-zero slot is 'none' (no recording asked for); an address without a length is a broken slot: 'refused'."""
        rec = recording([bytes(96)])
        for slot, state in (((0, 0), "none"), ((REC_PA, 0), "refused"), ((0, len(rec)), "refused")):
            with self.subTest(slot=slot):
                recs, _, _, _ = self.run_report(panel(), slot, rec)
                self.assertEqual(D.decode(recs)["recording"]["state"], state)

    def test_recording_bad_header(self):
        for name, rec in {
            "magic": recording([bytes(96)], magic=b"RWREC002"),
            "frames past bytes": recording([bytes(96)] * 3)[:-96],
            "zero width": recording([], w=0),
        }.items():
            with self.subTest(name):
                recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
                self.assertEqual(D.decode(recs)["recording"]["state"], "bad-header")

    def test_reads_stay_in_range(self):
        """With a declared length that just fits, no read leaves [rec_pa, rec_pa + len) (the harness exits 3 otherwise)."""
        rec = recording([bytes([1] * 96)] * 4)
        recs, _, _, out = self.run_report(panel(), (REC_PA, len(rec)), rec)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(D.decode(recs)["recording"]["frames"], 4)

    def test_frame_cap(self):
        rec = recording([bytes(12)] * 120, w=2, h=2)
        recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
        self.assertEqual(len(D.decode(recs)["recording"]["list"]), 96)

    def test_truncated_report_is_incomplete(self):
        recs, _, _, _ = self.run_report(panel())
        rep = D.decode(recs[:100])
        self.assertFalse(rep["complete"])
        self.assertEqual(D.verdict(rep), "X-incomplete")

    def test_ppm_thumbnail(self):
        recs, _, _, _ = self.run_report(panel(lambda x, y: (0, 255, 0)))
        ppm = D.thumbnail_ppm(D.decode(recs))
        self.assertTrue(ppm.startswith(b"P6 108 234 255\n"))
        self.assertEqual(len(ppm), len(b"P6 108 234 255\n") + 108 * 234 * 3)

    def test_rgb332_channels(self):
        for rgb, want in (((255, 0, 0), 0xe0), ((0, 255, 0), 0x1c), ((0, 0, 255), 0x03), ((0x20, 0x40, 0x40), 0x29)):
            with self.subTest(rgb=rgb):
                recs, _, _, _ = self.run_report(panel(lambda x, y: rgb))
                self.assertEqual(D.decode(recs)["panel"]["rows"][3][7], want)

    def test_ends_with_end_record_then_wait(self):
        _, _, _, out = self.run_report(panel())
        lines = out.stdout.splitlines()
        self.assertTrue(lines[-2].startswith("R PX end recs="), lines[-2:])
        self.assertEqual(lines[-1], "W")

    def test_nzb_counts_each_byte(self):
        for pos in range(4):
            with self.subTest(pos=pos):
                px = bytearray(96)
                px[pos] = 1
                rec = recording([bytes(px)])
                recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
                self.assertEqual(D.decode(recs)["recording"]["list"][0]["nzb"], 1)

    def test_magic_first_word_checked(self):
        rec = recording([bytes(96)], magic=b"XWREC003")
        recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
        self.assertEqual(D.decode(recs)["recording"]["state"], "bad-header")

    def test_odd_frame_size_refused(self):
        """w*h*3 not a multiple of 4 would make the word reads of later frames unaligned (MMU off: device memory)."""
        rec = recording([bytes(9)] * 2, w=3, h=1)
        recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
        self.assertEqual(D.decode(recs)["recording"]["state"], "bad-header")

    def test_huge_height_refused_even_with_zero_frames(self):
        rec = recording([], w=4, h=4097)
        recs, _, _, _ = self.run_report(panel(), (REC_PA, len(rec)), rec)
        self.assertEqual(D.decode(recs)["recording"]["state"], "bad-header")


class Build(unittest.TestCase):
    def setUp(self):
        self.b = _load("nat113_build_t", HERE / "build.py")

    def test_drop_base_tokens(self):
        base = "rd=md0 e1sufs=0 nat_attempt=NAT020-83s debug=0xc serial=3 cpus=1 keepsyms=1 -v"
        self.assertEqual(self.b.drop_base_tokens(base), "rd=md0 e1sufs=0 nat_attempt=NAT020-83s debug=0xc serial=3 cpus=1 -v")
        with self.assertRaises(SystemExit):
            self.b.drop_base_tokens(base.replace(" keepsyms=1", ""))
        with self.assertRaises(SystemExit):
            self.b.drop_base_tokens(base + " keepsyms=1")

    def test_field_padding(self):
        field = b"rd=md0 serial=3 keepsyms=1 x".ljust(608, b"\0")
        out = self.b.drop_base_tokens_field(field)
        self.assertEqual(len(out), 608)
        self.assertEqual(out.rstrip(b"\0"), b"rd=md0 serial=3 x")

    def test_check_cmdline(self):
        good = ("rd=md1 nat_attempt=NAT113-sc3 serial=3 cpus=1 loader_return_after=63 rec_secs=30 rec_mb=64 xrd=md0")
        self.b.check_cmdline(good)
        for bad in (good.replace(" rec_mb=64", ""), good + " fb_diff=1", good + " keepsyms=1",
                    good.replace("=63", "=120"), good + " " + "a" * (256 - len(good))):
            with self.subTest(bad=bad[-30:]):
                with self.assertRaises(SystemExit):
                    self.b.check_cmdline(bad)

    def test_watchdog_window(self):
        """The kernel runs unpetted: loader_return_after + 20 s margin must stay inside the 83 s watchdog."""
        self.assertLessEqual(self.b.RETURN_AFTER_NEW + 20, 83)
        self.assertGreaterEqual(self.b.DEADLINE_NEW, 240 + self.b.RETURN_AFTER_NEW + 60 + 25)

    def test_patch_rules_apply_once(self):
        src = (PROC / "nat-062/src/glue62_impl.h").read_text()
        for label, old, new in tuple(self.b.b106.PATCH_RULES) + self.b.PATCH_RULES_113:
            self.assertEqual(src.count(old), 1, label)
            src = src.replace(old, new)
        self.assertEqual(src.count("nat113_pixels(pa_minus_va);"), 1)
        i, j = src.index("nat113_pixels"), src.index("N62_EMIT(b, p);\n\tn62_range")
        self.assertLess(i, j, "the pixel report precedes the KL begin record")
        self.assertIn("if (why == NAT062_WHY_RETURN)", src[src.rindex("{", 0, i) - 40:i])


if __name__ == "__main__":
    unittest.main()
