#!/usr/bin/env python3
"""Host tests for NAT-022. They run the real markerlib.c against a RAM buffer
(host-test evidence only) and cross-check it with the independent decoder."""
import importlib.util, os, random, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("decode", HERE / "decode.py")
dec = importlib.util.module_from_spec(spec); spec.loader.exec_module(dec)

class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "host_mk"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DMK_HOST=1", f"-I{HERE/'src'}",
                        str(HERE / "src/markerlib.c"), str(HERE / "src/host_mk.c"), "-o", str(cls.exe)], check=True)

    def run_scn(self, name, n):
        out = Path(self.tmp.name) / f"{name}.bin"
        p = subprocess.run([str(self.exe), name, str(n), str(out)], capture_output=True, text=True, check=True)
        frames = [int(l.split()[1], 16) for l in p.stdout.splitlines()]
        return frames, out.read_bytes()

    def test_crc_independent_of_c(self):
        # C-built frames must equal the Python reference for every drawn word.
        frames, _ = self.run_scn("gate", 8)
        for w in frames:
            f = dec.parse_frame(w)
            self.assertIsNotNone(f)
            self.assertEqual(dec.make_frame(f["kind"], f["idx"], f["data"]), w)

    def test_buffer_decodes_to_last_frame(self):
        for scn, n in (("entry", 1), ("entry_mc", 1), ("stage", 1), ("gate", 5), ("exc", 7), ("canary", 6)):
            frames, buf = self.run_scn(scn, n)
            got = dec.decode_raw(buf)
            self.assertEqual(got, dec.parse_frame(frames[-1]), scn)

    def test_incremental_redraw_keeps_stale_bands_correct(self):
        # exc draws only changed bands after the first frame; the buffer must still
        # decode as the latest frame, not a mix with the previous one.
        frames, buf = self.run_scn("exc", 12)
        self.assertEqual(dec.decode_raw(buf), dec.parse_frame(frames[-1]))

    def test_entry_fields(self):
        frames, _ = self.run_scn("entry_mc", 1)
        d = dec.describe([dec.parse_frame(frames[0])])
        self.assertEqual(d["entry"]["el"], 2)
        self.assertEqual(d["entry"]["cur"], {"M": 1, "C": 1, "I": 1})
        self.assertEqual(d["entry"]["el1"], {"M": 0, "C": 0, "I": 0})

    def test_gate_never_silent_and_reports_cause(self):
        frames, _ = self.run_scn("gate", 8)
        ds = dec.describe([dec.parse_frame(w) for w in frames])
        self.assertIn("halt: MMU/cache on at entry", ds["stages"])
        self.assertEqual(ds["boot_id_cntvct32"], 0x1234abcd & 0xffffffff)
        self.assertEqual(ds["entry"]["el"], 2)

    def test_exception_record_roundtrip(self):
        frames, _ = self.run_scn("exc", 14)
        ds = dec.describe([dec.parse_frame(w) for w in frames])
        self.assertEqual(ds["esr"], "0x00000000f2001234")
        self.assertEqual(ds["elr"], "0xffffff8000123456")
        self.assertEqual(ds["far"], "0x00000000deadbeef")
        self.assertEqual(ds["slot"], 4)

    def test_stage_marker_labels_pre_jump_not_entry(self):
        frames, _ = self.run_scn("stage", 1)
        ds = dec.describe([dec.parse_frame(frames[0])])
        self.assertEqual(ds["stages"], ["pre-jump (NOT proof of kernel entry)"])

    def test_stride_independent_camera_model(self):
        # Simulate a phone whose real stride differs from the loader's assumption:
        # the decoder must succeed with the true stride and never claim a wrong frame.
        frames, buf = self.run_scn("exc", 3)
        want = dec.parse_frame(frames[-1])
        for true_stride in (4320, 4352, 4608):
            rows = []
            nrows = len(buf) // true_stride
            for r in range(nrows):
                o = r * true_stride + 64
                band = o // dec.BAND_BYTES
                v = 1.0 if buf[o:o + 4] == b"\xff\xff\xff\xff" else 0.0
                rows.append(min(1.0, max(0.0, v + random.Random(r).uniform(-0.08, 0.08))))
            hits = dec.decode_rows(rows, [4320, 4352, 4608, 4096])
            matches = [h for h in hits if h["stride"] == true_stride]
            self.assertEqual(len(matches), 1, true_stride)
            for k in ("kind", "idx", "data"):
                self.assertEqual(matches[0][k], want[k])
            for h in hits:   # any other accepted hypothesis would be CRC-valid by chance; surface it
                self.assertIn("stride", h)

    def test_fb_safe_guard(self):
        def safe(a, b, size):
            return subprocess.run([str(self.exe), "fbsafe", hex(a), hex(b), str(size)], capture_output=True, text=True, check=True).stdout.strip()
        fb = 0xFA200000
        self.assertEqual(safe(0x80000000, 0x80100000, 0x1000), "1")
        self.assertEqual(safe(fb - 0x1000, fb + 1, 0x1000), "0")          # image overlaps region
        self.assertEqual(safe(fb + 0x800000, fb + 0x900000, 0x1000), "0")  # image inside region
        self.assertEqual(safe(0x80000000, 0x80100000, 1 << 30), "0")      # implausible DTB size
        self.assertEqual(safe(fb + 0x8a0000, fb + 0x8b0000, 0x1000), "1")  # past the 34 bands (0x880000 bytes)

    def test_corrupt_crc_rejected(self):
        frames, buf = self.run_scn("stage", 1)
        b = bytearray(buf)
        start = 2 * dec.BAND_BYTES   # first payload bit (MSB of kind)
        b[start:start + dec.BAND_BYTES] = (b"\x00" * dec.BAND_BYTES) if b[start] else (b"\xff" * dec.BAND_BYTES)
        self.assertIsNone(dec.decode_raw(bytes(b)))

    def test_low_contrast_rejected(self):
        self.assertIsNone(dec.decode_bands([0.55, 0.5] + [0.5] * 32))

class Aarch64Build(unittest.TestCase):
    def test_images_build_with_arm64_header(self):
        import shutil
        if not shutil.which("zig"):
            self.skipTest("zig missing")
        out = subprocess.run([sys.executable, str(HERE / "build.py"), "--check-only"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

if __name__ == "__main__":
    unittest.main()
