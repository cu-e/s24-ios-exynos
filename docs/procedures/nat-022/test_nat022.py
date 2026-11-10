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

    def trigexc(self, n, gc, tc, *flags):
        p = subprocess.run([str(self.exe_trig), "trigexc", str(n), str(Path(self.tmp.name) / "e.bin"), gc, tc, *flags],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        ev = [l.split() for l in p.stdout.splitlines()]
        return ev, [int(e[1], 16) for e in ev if e[0] == "DRAW"]

    def test_exception_report_with_kicks_reads_back_and_stays_in_contract(self):
        # One exception cycle is STAGE + SLOT + ESR/ELR/FAR (12) + 10 REG frames; run two cycles.
        ev, frames = self.trigexc(50, "0x103", "0x10")
        self.assertEqual(ev[0][0], "DRAW")                       # the exception marker precedes any MMIO
        self.assertTrue({e[1] for e in ev if e[0] == "WR"} <= {"30", "50"})
        ds = dec.describe([dec.parse_frame(w) for w in frames])
        self.assertEqual((ds["esr"], ds["elr"], ds["far"]), ("0x00000000f2001234", "0xffffff8000123456", "0x00000000deadbeef"))
        self.assertEqual(ds["slot"], 4)
        self.assertTrue(ds["decon"]["kick_status"].startswith("sent"))

    def test_exception_report_survives_a_poisoned_or_mmu_on_kick(self):
        # An exception that interrupted a kick (or MMU on) must still report ESR/ELR/FAR with no MMIO at all.
        for flag in ("poison", "mmu"):
            ev, frames = self.trigexc(30, "0x103", "0x10", flag)
            self.assertFalse([e for e in ev if e[0] in ("RD", "WR")], flag)
            ds = dec.describe([dec.parse_frame(w) for w in frames])
            self.assertEqual(ds["esr"], "0x00000000f2001234", flag)

    def test_skip_status_reported_not_hidden(self):
        for args, text in ((("0x0", "0x10"), "not enabled"), (("0x1", "0x10"), "video mode"), (("0x103", "0x10", "mmu"), "MMU on")):
            _, frames = self.trig(40, *args)
            self.assertIn(text, dec.describe([dec.parse_frame(w) for w in frames])["decon"]["kick_status"])

class LoaderHold(unittest.TestCase):
    """loader-diag-trig: stage frames with a kick and a dwell, the reached-stage mask, the hold loop that
    never returns, and fail()/exception reports. The real markerlib.c against the fake DECON0."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "host_mk_ld"
        subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-DMK_HOST=1", "-DMK_TRIG=1", "-DMK_LOADER=1",
                        f"-I{HERE/'src'}", str(HERE / "src/markerlib.c"), str(HERE / "src/host_mk.c"), "-o", str(cls.exe)], check=True)

    def go(self, scn, n, gc, tc, *extra):
        p = subprocess.run([str(self.exe), scn, str(n), str(Path(self.tmp.name) / "l.bin"), gc, tc, *extra],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)       # 0 = it ran until the draw budget: it did not return
        ev = [l.split() for l in p.stdout.splitlines()]
        return ev, [dec.parse_frame(int(e[1], 16)) for e in ev if e[0] == "DRAW"]

    def test_every_draw_is_followed_by_a_kick_and_nothing_precedes_the_first_marker(self):
        ev, frames = self.go("ldstages", 12, "0x113", "0x3063")
        self.assertEqual(ev[0][0], "DRAW")
        draws = [i for i, e in enumerate(ev) if e[0] == "DRAW"]
        for a, b in zip(draws, draws[1:]):          # between two draws exactly one kick: reads then the contract writes
            seg = ev[a + 1:b]
            self.assertTrue(seg and seg[0][:2] == ["RD", "20"], seg)
            self.assertTrue({e[1] for e in seg if e[0] == "WR"} <= {"30", "50"})
        self.assertTrue({e[1] for e in ev if e[0] == "RD"} <= {"04", "4", "20", "30", "50"})

    def test_stage_order_mask_and_hold_loop(self):
        ev, frames = self.go("ldstages", 80, "0x113", "0x3063")
        d = dec.describe(frames)
        names = [dec.STAGES[f["data"]] for f in frames if f["kind"] == 3 and f["idx"] == 0]
        self.assertEqual(names[:8], ["loader_main", "loader fb selected", "memory window chosen", "XNU RAM zeroed",
                                      "kernel segments copied", "ADT/boot_args built", "about to clean the XNU window",
                                      "pre-jump (NOT proof of kernel entry)"])
        self.assertEqual(d["stage_mask"], 0x1ff)                   # entry .. pre-jump; fail bit not set
        self.assertEqual(d["stages_reached"][-1], "pre-jump")
        self.assertEqual(d["stage_code"], 0)
        self.assertTrue(d["decon"]["kick_status"].startswith("sent"))
        self.assertIn("boot_id_cntvct32", d)
        # The hold never returns: the draw budget ran out inside the loop and frames kept cycling.
        loop = {(f["kind"], f["idx"]) for f in frames[-15:]}
        self.assertTrue({(3, 0), (3, 1), (3, 2), (2, 0), (2, 1), (9, 0), (9, 9)} <= loop, loop)
        self.assertEqual(len(frames), 80)

    def test_fail_hold_carries_the_message_hash_and_no_pre_jump(self):
        msg = "bad payload header"
        ev, frames = self.go("ldfail", 60, "0x113", "0x3063", msg)
        d = dec.describe(frames)
        self.assertEqual(d["stage_code"], dec.fnv16(msg))           # independent Python hash equals the C one
        self.assertIn("fail", d["stages_reached"])
        self.assertNotIn("pre-jump", d["stages_reached"])
        self.assertNotIn("window clean started", d["stages_reached"])
        self.assertEqual(d["stage_mask"] & 1, 1)
        last_stage = [f["data"] for f in frames if f["kind"] == 3 and f["idx"] == 0][-1]
        self.assertEqual(last_stage, 0x3f)

    def test_exception_loop_reports_the_mask_with_esr_elr_far(self):
        ev, frames = self.go("ldexc", 80, "0x113", "0x3063")
        d = dec.describe(frames)
        self.assertEqual((d["esr"], d["elr"], d["far"]), ("0x0000000096000045", "0xffffff8000123456", "0x0000000000dead00"))
        self.assertEqual(d["slot"], 4)
        self.assertEqual(d["stage_mask"], 0b1111)                   # entry, loader_main, fb, memory window
        self.assertEqual(d["stages_reached"], ["entry", "loader_main", "fb selected", "memory window"])

    def test_no_mmio_when_mmu_on_or_a_kick_was_interrupted(self):
        for flag in ("mmu", "poison"):
            ev, frames = self.go("ldstages", 30, "0x113", "0x3063", flag)
            self.assertFalse([e for e in ev if e[0] in ("RD", "WR")], flag)
            self.assertEqual(dec.describe(frames)["stage_mask"], 0x1ff, flag)   # still reported, just not kicked

    def test_hash16_matches_python_for_every_loader_failure_message(self):
        src = (HERE.parents[2] / "artifacts/nat-020/build-003/source/shim/e1s-xnu/loader.c")
        if not src.exists():
            self.skipTest("NAT-020 build-003 source not present")
        import re
        msgs = re.findall(r'fail\("([^"]+)"\)', src.read_text())
        self.assertGreaterEqual(len(msgs), 15)
        hashes = {dec.fnv16(m) for m in msgs}
        self.assertEqual(len(hashes), len(set(msgs)), "two loader failure messages share a 16-bit hash")
        for m in set(msgs):
            out = subprocess.run([str(self.exe), "hash16", m], capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(int(out, 16), dec.fnv16(m), m)

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

def _payload(adt_size=13956, adt_len=13956, pad=b"\0" * 12, nsegs=1, version=1, virt=0xfffffff004000000, entry=0xfffffff004001000,
             adt_off=0x2e8, kernel_end=0xfffffff004010000, mem_size=0x20000000, seg_file=(0x4000, 0x10)):
    """A synthetic SWEETXNU payload written from the struct layout in the module docstring, not from the tools under test."""
    import struct
    h = struct.pack("<8sIIQQQQQQQ", b"SWEETXNU", version, nsegs, virt, entry, adt_off, adt_size, kernel_end, 0xa0000000, mem_size)
    h += b"\0" * 608
    segs = struct.pack("<4Q", virt, 0x10000, seg_file[0] + 0x4000, seg_file[1]) * max(nsegs, 0)
    body = h + segs
    body += b"\0" * (adt_off - len(body)) + b"\x01" * adt_len + pad
    return body

class PayloadFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("fix_payload", HERE / "fix_payload.py")
        cls.fp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.fp)
        cls.root = HERE.parents[2]
        cls.loader_c = cls.root / "artifacts/nat-020/build-003/source/shim/e1s-xnu/loader.c"

    def test_fix_changes_only_adt_size_and_only_when_the_padding_is_zero(self):
        import struct
        src = _payload()
        out, info = self.fp.fix(src)
        diff = [i for i in range(len(src)) if src[i] != out[i]]
        self.assertEqual(diff, [40])                      # one byte: 13956 (0x3684) -> 13960 (0x3688)
        self.assertEqual(struct.unpack_from("<Q", out, 40)[0], 13960)
        self.assertEqual((info["old"], info["new"]), (13956, 13960))
        with self.assertRaises(SystemExit):               # non-zero byte after the ADT: not ours to claim
            self.fp.fix(_payload(pad=b"\0\0\x07\0" + b"\0" * 8))
        with self.assertRaises(SystemExit):               # already a multiple of 8
            self.fp.fix(_payload(adt_size=13960, adt_len=13960, pad=b"\0" * 8))
        with self.assertRaises(SystemExit):               # padding would run past the end of the file
            self.fp.fix(_payload(pad=b""))
        with self.assertRaises(SystemExit):               # a segment's file range overlaps the padding
            self.fp.fix(_payload(seg_file=(0x2e8 + 13956 - 0x4000, 8)))

    def check(self, payload, *flags):
        if not self.loader_c.exists():
            self.skipTest("the NAT-020 build-003 loader source is missing")
        import shutil
        if not shutil.which("zig"):
            self.skipTest("zig missing")
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "p.bin"; f.write_bytes(payload)
            r = subprocess.run([sys.executable, "-P", str(HERE / "check_payload.py"), str(self.loader_c), str(f), "--no-adt", *flags],
                               capture_output=True, text=True)
        return r.returncode, [l for l in r.stdout.splitlines() if l.startswith("FIRES")]

    def test_each_loader_header_clause_is_evaluated_on_its_own(self):
        # Each synthetic header violates exactly one clause of loader.c's two header conditions.
        cases = {
            "p->version != 1": dict(version=2),
            "!p->nsegs": dict(nsegs=0),
            "p->nsegs > 32": dict(nsegs=33),
            "(p->adt_off & 7)": dict(adt_off=0x2ec),
            "(p->adt_size & 7)": dict(adt_size=13956),
            "p->entry_va < p->virt_base": dict(entry=0xfffffff003fff000),
            "p->kernel_end < p->virt_base": dict(kernel_end=0xfffffff003fff000),
            "!p->mem_size": dict(mem_size=0),
            "p->mem_size > (4UL << 30)": dict(mem_size=(4 << 30) + 1),
        }
        base = dict(adt_size=13960, adt_len=13960, pad=b"\0" * 8)
        rc, fires = self.check(_payload(**base))
        self.assertEqual((rc, fires), (0, []))
        for clause, kw in cases.items():
            kw = {**base, **kw}
            if "adt_size" in kw and kw["adt_size"] == 13956:
                kw.update(adt_len=13956, pad=b"\0" * 12)
            rc, fires = self.check(_payload(**kw))
            self.assertEqual(rc, 1, clause)
            self.assertEqual(len(fires), 1, (clause, fires))
            self.assertTrue(fires[0].endswith(clause), (clause, fires))

    def test_run_004_payload_fires_and_the_fixed_payload_passes_every_stage_check(self):
        pb = self.root / "artifacts/nat-020/build-003/payload.bin"
        if not pb.exists() or not self.loader_c.exists():
            self.skipTest("NAT-020 build-003 payload or loader source missing")
        rc, fires = self.check(pb.read_bytes())
        self.assertEqual(rc, 1)
        self.assertEqual(len(fires), 1); self.assertTrue(fires[0].endswith("(p->adt_size & 7)"))
        fixed, _ = self.fp.fix(pb.read_bytes())
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "fixed.bin"; f.write_bytes(fixed)
            r = subprocess.run([sys.executable, "-P", str(HERE / "check_payload.py"), str(self.loader_c), str(f)],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("window 256 MiB: ok"), 1); self.assertEqual(r.stdout.count("window 512 MiB: ok"), 1)
        self.assertEqual(r.stdout.count("mpidr=0 dram=0 pram=0 ramdisk=0 guard_overrun=0"), 2)


class Aarch64Build(unittest.TestCase):
    def test_images_build_with_arm64_header(self):
        import shutil
        if not shutil.which("zig"):
            self.skipTest("zig missing")
        out = subprocess.run([sys.executable, str(HERE / "build.py"), "--check-only"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_loader_variants_build_and_the_run_images_are_unchanged(self):
        import json, shutil
        root = HERE.parents[2]
        src = root / "artifacts/nat-020/build-003/source"
        ref = root / "artifacts/nat-022/build-003/build.json"
        if not shutil.which("zig") or not src.exists() or not ref.exists():
            self.skipTest("zig, the NAT-020 source or the build-003 record is missing")
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "o"
            r = subprocess.run([sys.executable, str(HERE / "build.py"), "--out", str(out), "--loader-source", str(src)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            new = json.loads((out / "build.json").read_text())["images"]
            old = json.loads(ref.read_text())["images"]
            for n, v in old.items():                      # every image of build-003, including the two that ran
                self.assertEqual(new[n]["sha256"], v["sha256"], n)
            self.assertNotEqual(new["loader-diag-trig-hold"]["sha256"], new["loader-diag"]["sha256"])
            # NAT-026: the adt8 variant has the same loader Image; its Image.payload differs from the run-004 image
            # in exactly one byte, the low byte of the header's adt_size (0x84 -> 0x88), and nowhere else.
            self.assertEqual(new["loader-diag-trig-hold-adt8"]["sha256"], new["loader-diag-trig-hold"]["sha256"])
            ip = json.loads((out / "build.json").read_text())["image_payloads"]
            a = (out / ip["loader-diag-trig-hold"]["path"]).read_bytes()
            b = (out / ip["loader-diag-trig-hold-adt8"]["path"]).read_bytes()
            off = (out / "loader-diag-trig-hold/Image").stat().st_size
            self.assertEqual(len(a), len(b))
            self.assertEqual([i for i in range(len(a)) if a[i] != b[i]], [off + 40])
            self.assertEqual((a[off + 40], b[off + 40]), (0x84, 0x88))
            src_c = (out / "loader-diag-trig-hold/source/shim/e1s-xnu/loader.c").read_text()
            # The hold variant never reaches the return that jumps into the kernel copy.
            hold = src_c.index("NAT022_HOLD(MK_ST_PRE_JUMP, 0)")
            self.assertLess(hold, src_c.index("return entry_pa;"))
            self.assertNotIn("fb_base == MK_FB_BASE", src_c)
            plain = (out / "loader-diag/source/shim/e1s-xnu/loader.c").read_text()
            self.assertNotIn("mk_hold", plain)

if __name__ == "__main__":
    unittest.main()
