#!/usr/bin/env python3
"""NAT-117 host tests: the ADT derivation against the IPSW's real D22AP tree, the built payload's ADT, and analyze118.py on the two
real runs (NAT-116 = bounding-path abort, NAT-113 = alive, no frame) and on edited copies of them.
Run: python3 -B -I docs/procedures/nat-117/test_nat117.py"""
import importlib.util, json, struct, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import analyze118 as A  # noqa: E402
import make_adt117 as M  # noqa: E402

BUILD = ROOT / "artifacts/nat-117/build-001"
NAME = "loader-diag-xnu-sc5-md1"
T116 = ROOT / "artifacts/nat-116/analysis/kernel-text.txt"
P116 = ROOT / "artifacts/nat-116/analysis/pixels.json"
T113 = ROOT / "artifacts/nat-113/analysis/kernel-text.txt"
P113 = ROOT / "artifacts/nat-113/analysis/pixels.json"


def adtmod():
    return M.m85._adt()


class AdtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adt = adtmod()
        cls.pinned = (M.m85.B3 / "e1s.adt").read_bytes()
        cls.im4p = M.IM4P.read_bytes()
        cls.out, cls.rec = M.derive(cls.pinned, cls.im4p, cls.adt)
        cls.d22 = M.d22ap_adt(cls.im4p)

    def test_only_product_added_to_nat085(self):
        eph, _ = M.m85.derive(self.pinned, self.adt)
        a, _ = self.adt.parse(eph)
        b, _ = self.adt.parse(self.out)
        self.assertEqual([c.name for c in b.children], [c.name for c in a.children] + ["product"])
        b.children = b.children[:-1]
        self.assertEqual(self.adt.serialize(b), eph)

    def test_product_equals_d22ap_by_mkadt_rule(self):
        real, _ = self.adt.parse(self.d22)
        rp = [c for c in real.children if c.name == "product"][0]
        b, _ = self.adt.parse(self.out)
        bp = [c for c in b.children if c.name == "product"][0]
        want = [(k, b"sRGB\0" if k == "artwork-display-gamut" else v) for k, f, v in rp.props if not f and k not in ("name", "AAPL,phandle")]
        got = [(k, v) for k, f, v in bp.props if k not in ("name", "AAPL,phandle")]
        self.assertEqual(got, want)
        self.assertTrue(all(f == 0 for _, f, _ in bp.props))
        self.assertFalse(any(v.startswith(b"syscfg/") for _, _, v in bp.props))
        self.assertEqual(bp.children, [])

    def test_traits(self):
        p = self.rec["product"]
        self.assertEqual((p["artwork-device-subtype"], p["artwork-scale-factor"], p["artwork-device-idiom"], p["artwork-display-gamut"],
                          p["product-name"]), (2436, 3, "phone", "sRGB", "iPhone X"))

    def test_phandle_unique(self):
        b, _ = self.adt.parse(self.out)
        seen = []

        def walk(n):
            v = n.prop("AAPL,phandle")
            if v is not None:
                seen.append(struct.unpack("<I", v)[0])
            for c in n.children:
                walk(c)
        walk(b)
        self.assertEqual(len(seen), len(set(seen)))

    def test_refuses_wrong_inputs(self):
        with self.assertRaises(ValueError):
            M.d22ap_adt(self.im4p[:-1] + b"\0")
        with self.assertRaises(ValueError):
            M.derive(self.pinned + b"\0", self.im4p, self.adt)
        with self.assertRaises(ValueError):
            M.derive(self.out, self.im4p, self.adt)   # already derived: not the pinned input

    @unittest.skipUnless((BUILD / "build.json").exists(), "build-001 absent")
    def test_payload_carries_this_adt(self):
        d = json.loads((BUILD / "build.json").read_text())
        pf = d["payload_fixes"][NAME]
        self.assertEqual(d["nat085_changes"]["adt"]["output_sha256"], self.rec["output_sha256"])
        self.assertEqual(d["nat085_changes"]["adt_swaps"], 1)
        p = (BUILD / NAME / "Image.payload").read_bytes()
        inner = 389120
        adt_off, adt_size = struct.unpack_from("<QQ", p, inner + 0x20)
        root, _ = self.adt.parse(p, inner + adt_off)
        self.assertIn("product", [c.name for c in root.children])
        self.assertLessEqual(len(self.out), adt_size + 64)
        toks = pf["cmdline"].split()
        self.assertNotIn("wait_dump=1", toks)
        self.assertIn("e1s_wdt_pet=1", toks)
        self.assertIn("loader_return_after=150", toks)
        self.assertLess(len(pf["cmdline"].encode()), 256)
        self.assertEqual(d["nat117_changes"]["kernel_no_storage_sha256"], "cc952151c8d6007fa6ccd3c0e57d0320d85f329166fa23700930b8f2af680b18")


class AnalyserTests(unittest.TestCase):
    def run_on(self, text, pixels):
        return A.classify(A.parse(text), pixels)

    @unittest.skipUnless(T116.exists(), "NAT-116 run absent")
    def test_nat116_is_same_abort(self):
        r = self.run_on(T116.read_text(errors="replace"), json.loads(P116.read_text()))
        self.assertEqual((r["window"], r["verdict"]), ("W-ok", "A1-same-abort"))

    @unittest.skipUnless(T113.exists(), "NAT-113 run absent")
    def test_nat113_is_alive_no_frame(self):
        r = self.run_on(T113.read_text(errors="replace"), json.loads(P113.read_text()))
        self.assertEqual((r["window"], r["verdict"]), ("W-ok", "S1-alive-no-frame"))

    @unittest.skipUnless(T116.exists(), "NAT-116 run absent")
    def test_other_abort(self):
        t = T116.read_text(errors="replace").replace("Failed to load bounding path bitmap data", "Some other failure")
        r = self.run_on(t, json.loads(P116.read_text()))
        self.assertEqual(r["verdict"], "A2-other-abort")
        self.assertIn("Some other failure", r["first_exception"]["reason"])

    @unittest.skipUnless(T116.exists(), "NAT-116 run absent")
    def test_new_frame_wins(self):
        px = json.loads(P116.read_text())
        px["frames"] = px["frames"] + [dict(f=2, ns=1, nzb=500000, of=0, fnv=0x12345678)]
        r = self.run_on(T116.read_text(errors="replace"), px)
        self.assertEqual(r["verdict"], "F1-new-frame")

    @unittest.skipUnless(T116.exists(), "NAT-116 run absent")
    def test_logo_or_empty_frames_are_not_new(self):
        px = json.loads(P116.read_text())
        px["frames"] = px["frames"] + [dict(f=2, ns=1, nzb=0, of=0, fnv=0x12345678)]
        r = self.run_on(T116.read_text(errors="replace"), px)
        self.assertEqual(r["verdict"], "A1-same-abort")

    @unittest.skipUnless(T116.exists(), "NAT-116 run absent")
    def test_window_requires_expiry_and_report(self):
        t = T116.read_text(errors="replace")
        px = json.loads(P116.read_text())
        self.assertEqual(self.run_on(t.replace("--- loader_return_after expired ---", "x"), px)["verdict"], "X-window")
        self.assertEqual(self.run_on(t, dict(px, complete=False))["verdict"], "X-window")

    def test_panic_before_return_is_x_window(self):
        t = "[  200.0]: boot\npanic(cpu 0 caller 0x0): something\n--- loader_return_after expired ---\n"
        self.assertEqual(self.run_on(t, dict(complete=True, frames=[]))["verdict"], "X-window")
        t2 = "[  200.0]: boot\n--- loader_return_after expired ---\n--- panic buffer ---\npanic(cpu 0 caller 0x0): x\n"
        self.assertEqual(self.run_on(t2, dict(complete=True, frames=[]))["verdict"], "S1-alive-no-frame")

    def test_no_expiry_without_panic_is_x_window(self):
        t = "[  200.0]: boot\nwhatever\n"
        self.assertEqual(self.run_on(t, dict(complete=True, frames=[]))["verdict"], "X-window")
        self.assertEqual(self.run_on(t + "--- loader_return_after expired ---\n", dict(complete=True, frames=[]))["verdict"],
                         "S1-alive-no-frame")

    def test_sigabrt_alone_counts(self):
        t = ("--- loader_return_after expired ---\ncom.apple.xpc.launchd|1970 (user/501/com.apple.SpringBoard [70]) <Notice>: exited due to SIGABRT\n")
        self.assertEqual(self.run_on(t, dict(complete=True, frames=[]))["verdict"], "A2-other-abort")


if __name__ == "__main__":
    unittest.main(verbosity=1)
