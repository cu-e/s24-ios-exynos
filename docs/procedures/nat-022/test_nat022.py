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

class Trigger(unittest.TestCase):
    """canary-trig: the only MMIO is the documented DECON0 kick, and only when safe."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe_trig = Path(cls.tmp.name) / "host_mk_trig"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DMK_HOST=1", "-DMK_TRIG=1", f"-I{HERE/'src'}",
                        str(HERE / "src/markerlib.c"), str(HERE / "src/host_mk.c"), "-o", str(cls.exe_trig)], check=True)

    def trig(self, n, gc, tc, *flags):
        """Run the canary-trig loop against the fake DECON0; return (events, drawn frames)."""
        p = subprocess.run([str(self.exe_trig), "trig", str(n), str(Path(self.tmp.name) / "t.bin"), gc, tc, *flags],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        ev = [l.split() for l in p.stdout.splitlines()]
        return ev, [int(e[1], 16) for e in ev if e[0] == "DRAW"]

    def test_no_mmio_before_first_marker_and_only_contract_offsets(self):
        ev, _ = self.trig(20, "0x103", "0x10")
        self.assertEqual(ev[0][0], "DRAW")           # the framebuffer marker is drawn before any MMIO
        wr = {e[1] for e in ev if e[0] == "WR"}
        self.assertTrue(wr <= {"30", "50"}, wr)       # BADRD/BADWR would have failed the run (exit 5)
        self.assertTrue(wr, "a command-mode DECON must be kicked")

    def test_nothing_written_when_decon_off_video_mmu_or_poisoned(self):
        for args in (("0x0", "0x10"), ("0x1", "0x10"), ("0x2", "0x10"),   # not enabled / enabled but video mode
                     ("0x103", "0x10", "mmu"), ("0x103", "0x10", "poison")):
            ev, frames = self.trig(8, *args)
            self.assertFalse([e for e in ev if e[0] == "WR"], args)
            if "mmu" in args or "poison" in args:
                self.assertFalse([e for e in ev if e[0] == "RD"], args)
            self.assertTrue(frames)

    def test_trigger_sequences_follow_the_vendor_driver(self):
        ev, _ = self.trig(6, "0x103", "0x10")
        wr = [(e[1], int(e[2], 16)) for e in ev if e[0] == "WR"]
        # Kick 1 (HW form): mask, update request with bit 31, unmask leaving HW_TRIG_EN set and the mask clear.
        self.assertEqual(wr[0][0], "30"); self.assertEqual(wr[0][1] & 0x11, 0x11)
        self.assertEqual(wr[1][0], "50"); self.assertTrue(wr[1][1] & 1 << 31)
        self.assertEqual(wr[2][0], "30"); self.assertEqual(wr[2][1] & 0x11, 0x01)
        # Kick 2 (SW form): ends with SW_TRIG_EN | SW_TRIG_DET_EN set and HW_TRIG_EN clear.
        self.assertEqual(wr[3][0], "30"); self.assertEqual(wr[3][1] & 0x103, 0)
        self.assertEqual(wr[5][0], "30"); self.assertEqual(wr[5][1] & 0x103, 0x102)

    def test_report_decodes_with_independent_decoder(self):
        ev, frames = self.trig(40, "0x103", "0x10")
        ds = dec.describe([dec.parse_frame(w) for w in frames])
        d = ds["decon"]
        self.assertEqual(d["global_con"], "0x00000103")
        self.assertEqual(d["trig_con_before"][:6], "0x0000")
        self.assertTrue(d["kick_status"].startswith("sent"))
        self.assertGreaterEqual(d["kicks"], 2)
        self.assertGreater(d["frame_count_now16"], d["frame_count_prev16"])   # the fake counts requests

    def test_skip_status_reported_not_hidden(self):
        for args, text in ((("0x0", "0x10"), "not enabled"), (("0x1", "0x10"), "video mode"), (("0x103", "0x10", "mmu"), "MMU on")):
            _, frames = self.trig(40, *args)
            self.assertIn(text, dec.describe([dec.parse_frame(w) for w in frames])["decon"]["kick_status"])

try:
    import numpy as np
    HAVE_NP = True
except ImportError:            # decode_video.py needs numpy only for the host analysis
    HAVE_NP = False


@unittest.skipUnless(HAVE_NP, "numpy missing")
class VideoDecode(unittest.TestCase):
    """decode_video.analyse against synthetic camera frames: a forward model (perspective, bloom,
    blur, noise) that does not share code with the fit. It checks the geometric fit, not the phone."""
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("decode_video", HERE / "decode_video.py")
        cls.dv = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.dv)
        cls.cfg = dict(x0=230, x1=360, y0=60, y1=1100, umin=21.0, umax=29.0, ustep=0.05,
                       qs=[x for x in np.arange(-0.012, 0.0121, 0.001)], blooms=[0.0, 1.0, 2.0, 3.0, 4.0], max_rms=3.0)

    @staticmethod
    def render(word, u, q, y0, bloom, noise, seed=1):
        bits = [1, 0] + [(word >> (31 - i)) & 1 for i in range(32)]
        rng = np.random.default_rng(seed)
        ys = (np.arange(1280 * 8) + 0.5) / 8.0
        d = ys - y0
        K = d / (u - q * d)                      # band coordinate of every sub-row
        sub = np.zeros_like(ys)
        ok = (K >= 0) & (K < len(bits))
        sub[ok] = np.array(bits, float)[K[ok].astype(int)]
        sub = sub.reshape(1280, 8).mean(axis=1)
        ker = np.exp(-0.5 * (np.arange(-6, 7) / 1.3) ** 2); ker /= ker.sum()
        prof = np.clip(np.convolve(sub, ker, mode="same") * (1.0 + 0.15 * bloom), 0, 1)   # white blooms wider
        img = np.tile((25 + 200 * prof)[:, None], (1, 720))
        img += rng.normal(0, noise, img.shape)
        return np.clip(img, 0, 255).astype(np.uint8)

    def test_decodes_frames_under_perspective_and_bloom(self):
        words = [dec.make_frame(8, 0, 0xA5A5), dec.make_frame(3, 0, 0x10), dec.make_frame(9, 4, 0x3063),
                 dec.make_frame(2, 1, 0x1AE1), dec.make_frame(1, 0, 0x8900)]
        for i, w in enumerate(words):
            for u, q, y0, bloom in ((21.6, -0.003, 105, 2.0), (23.5, 0.002, 98, 1.0), (22.4, -0.006, 111, 3.0)):
                r = self.dv.analyse(self.render(w, u, q, y0, bloom, 3.0, seed=i), self.cfg)
                self.assertEqual(r["status"], "ok", (hex(w), u, q, r))
                self.assertEqual(dec.make_frame(r["frame"]["kind"], r["frame"]["idx"], r["frame"]["data"]), w)

    def test_never_guesses(self):
        img = self.render(dec.make_frame(3, 0, 0x10), 22.0, -0.003, 105, 2.0, 3.0)
        flat = np.full_like(img, 90)
        self.assertNotEqual(self.dv.analyse(flat, self.cfg)["status"], "ok")
        # a band flipped in the payload or in the CRC byte must be rejected, never "repaired"
        for flip in (1 << 20, 1 << 9, 0x01):
            bad = dec.make_frame(3, 0, 0x10) ^ flip
            r = self.dv.analyse(self.render(bad, 22.0, -0.003, 105, 2.0, 3.0), self.cfg)
            self.assertEqual(r["status"], "sync-or-crc-fail", hex(flip))

class Aarch64Build(unittest.TestCase):
    def test_images_build_with_arm64_header(self):
        import shutil
        if not shutil.which("zig"):
            self.skipTest("zig missing")
        out = subprocess.run([sys.executable, str(HERE / "build.py"), "--check-only"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

if __name__ == "__main__":
    unittest.main()
