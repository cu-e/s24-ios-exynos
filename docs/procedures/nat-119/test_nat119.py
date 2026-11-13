#!/usr/bin/env python3
"""NAT-119 host tests: the kernel patch's DECON kick (format strings from the committed patch, register writes), the loader rules
in the built tree, and analyze120.py on the NAT-118 run (no kick lines: D0) and on edited copies.
Run: python3 -B -I docs/procedures/nat-119/test_nat119.py"""
import json, re, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import analyze120 as A  # noqa: E402

PATCH = (HERE / "kernel-combined.patch").read_text()
ADDED = "\n".join(l[1:] for l in PATCH.splitlines() if l.startswith("+") and not l.startswith("+++"))
T118 = ROOT / "artifacts/nat-118/analysis/kernel-text.txt"
P118 = ROOT / "artifacts/nat-118/analysis/pixels.json"
BUILD = ROOT / "artifacts/nat-119/build-001"
SHIM = BUILD / "loader-diag-xnu-sc6-md1/source/shim/e1s-xnu"


def kick_fmt():
    m = re.search(r'printf\("(e1s_decon: kick [^"]*)"', ADDED)
    return m.group(1).encode().decode("unicode_escape").rstrip("\n")


def kick_line(t, n, fc, delta, gc=0x133, tc0=0x3063, tc1=0x3001):
    fmt = kick_fmt().replace("%u", "%d")
    return "[%11.6f]: " % t + fmt % (n, gc, tc0, tc1, fc, delta)


class PatchTests(unittest.TestCase):
    def test_kick_is_nat115_patch_plus_kick_only(self):
        old = (ROOT / "docs/procedures/nat-115/kernel-combined.patch").read_text()
        old_added = [l for l in old.splitlines() if l.startswith("+") and not l.startswith("+++")]
        new_added = [l for l in PATCH.splitlines() if l.startswith("+") and not l.startswith("+++")]
        extra = [l for l in new_added if l not in old_added]
        self.assertTrue(all(l in new_added for l in old_added))
        self.assertTrue(any("e1s_decon_kick();" in l for l in extra))
        # no other hardware register block is mapped by the added lines
        maps = [l for l in extra if "ml_io_map" in l]
        self.assertEqual(len(maps), 1)
        self.assertIn("E1S_DECON0_PA", maps[0])

    def test_writes_only_trig_and_shadow(self):
        body = ADDED[ADDED.index("e1s_decon_kick(void)"):ADDED.index("/* end of e1s_decon */")]
        writes = re.findall(r"e1s_decon\[(E1S_DECON_\w+)\]\s*=(?!=)", body)
        self.assertEqual(sorted(set(writes)), ["E1S_DECON_SHD_REG_UP", "E1S_DECON_TRIG_CON"])
        self.assertIn("0x19100000ULL", ADDED)
        self.assertRegex(ADDED, r"E1S_DECON_TRIG_CON\s+\(0x30 / 4\)")
        self.assertRegex(ADDED, r"E1S_DECON_SHD_REG_UP\s+\(0x50 / 4\)")
        # guarded by enabled + command mode, bounded count
        self.assertIn("(gc & E1S_GC_EN) != E1S_GC_EN || (gc & E1S_GC_CMD) == 0", body)
        self.assertIn("E1S_DECON_MAX_KICKS", body)

    def test_called_at_window_start_and_heartbeat(self):
        self.assertEqual(ADDED.count("\te1s_decon_kick();"), 2)

    @unittest.skipUnless((BUILD / "build.json").exists(), "build absent")
    def test_build_record(self):
        d = json.loads((BUILD / "build.json").read_text())
        rec = json.loads((ROOT / "artifacts/nat-119/kernel-001/rebuild.json").read_text())
        self.assertEqual(d["nat115_changes"]["kernel_no_storage_sha256"], rec["no_storage_sha256"])
        self.assertEqual(rec["expect_strings"]["e1s_decon: kick %u GLOBAL_CON"], 1)
        self.assertEqual(d["nat117_changes"]["adt"]["output_sha256"], "44bbd1d06693d706dfede4ea1e3d85953cb7eb3151854302c2a41fcdceadf79e")
        cmd = d["payload_fixes"]["loader-diag-xnu-sc6-md1"]["cmdline"]
        self.assertIn("e1s_decon_hw=1", cmd.split())
        self.assertLess(len(cmd.encode()), 256)

    @unittest.skipUnless(SHIM.exists(), "build absent")
    def test_loader_rules_in_tree(self):
        mk = (SHIM / "markerlib.c").read_text()
        self.assertIn("{\n\tif (nat119_no_draw)\n\t\treturn;\n", mk)
        g = (SHIM / "glue62_impl.h").read_text()
        self.assertEqual(g.count("nat119_no_draw = 1;"), 1)
        i = g.index("nat119_no_draw = 1;")
        self.assertLess(g.rindex("if (why == NAT062_WHY_RETURN)", 0, i), i)


class AnalyserTests(unittest.TestCase):
    def setUp(self):
        if not T118.exists():
            self.skipTest("NAT-118 run absent")
        self.t = T118.read_text(errors="replace")
        self.px = json.loads(P118.read_text())

    def with_kicks(self, lines):
        a = self.t.index("--- loader_return_after expired ---")
        return self.t[:a] + "\n".join(lines) + "\n" + self.t[a:]

    def test_nat118_is_no_kick(self):
        r = A.classify(self.t, self.px)
        self.assertEqual((r["window"], r["verdict"], r["ios"]), ("W-ok", "D0-no-kick", "F1-new-frame"))

    def test_refreshing(self):
        r = A.classify(self.with_kicks([kick_line(190.0, 1, 1000, 0), kick_line(200.0, 2, 2200, 1200), kick_line(210.0, 3, 3400, 1200)]), self.px)
        self.assertEqual(r["verdict"], "D2-refreshing")
        self.assertEqual(r["frame_rates_hz"], [120.0, 120.0])

    def test_frozen(self):
        r = A.classify(self.with_kicks([kick_line(190.0, 1, 1000, 0), kick_line(200.0, 2, 1000, 0)]), self.px)
        self.assertEqual(r["verdict"], "D1-kick-frozen")

    def test_single_kick_is_frozen_not_refreshing(self):
        r = A.classify(self.with_kicks([kick_line(190.0, 1, 1000, 0)]), self.px)
        self.assertEqual(r["verdict"], "D1-kick-frozen")

    def test_not_kicked_quoted(self):
        r = A.classify(self.with_kicks(["[ 190.0]: e1s_decon: not kicked: GLOBAL_CON 0x20 TRIG_CON 0x0 FRAME_COUNT 0"]), self.px)
        self.assertEqual(r["verdict"], "D0-no-kick")
        self.assertTrue(r["not_kicked"][0].startswith("not kicked"))

    def test_window_first(self):
        r = A.classify(self.t.replace("--- loader_return_after expired ---", "x"), self.px)
        self.assertEqual(r["verdict"], "X-window")


if __name__ == "__main__":
    unittest.main(verbosity=1)
