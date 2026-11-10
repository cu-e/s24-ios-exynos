#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-029 host checks: the analyzer's findings re-derived with capstone, which shares no code with it.

Run with a python that has capstone (`python3 -I docs/procedures/nat-029/test_analyze.py`); the
capstone cases skip, and say so, without it. Needs the local artifacts/nat-020/build-003 payload and
Mach-O and artifacts/nat-029/payload-analysis.json (written by analyze_payload.py).
"""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_payload as ap  # noqa: E402

PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
RESULT = ROOT / "artifacts/nat-029/payload-analysis.json"

try:
    import capstone
except ImportError:  # pragma: no cover
    capstone = None


class Decoders(unittest.TestCase):
    """Hand-computed encodings (ARM ARM) for the shapes the analyzer matches."""

    def test_fixed_encodings(self):
        self.assertEqual(ap.cmp_x_imm(0xF100145F), (2, 5))      # cmp x2, #5
        self.assertEqual(ap.movz(0xD2800063), (3, 3, True))      # mov x3, #3
        self.assertEqual(ap.movz(0x52800140), (0, 10, False))    # mov w0, #10
        self.assertIsNone(ap.movz(0xF2800063))                   # movk is not movz
        self.assertEqual(ap.ldr_x_uimm(0xF940092A), (10, 9, 16))  # ldr x10, [x9, #16]
        self.assertEqual(ap.add_imm(0x9101C129), (9, 9, 0x70))   # add x9, x9, #0x70
        self.assertEqual(ap.bl_target(0x1000, 0x94000004), 0x1010)
        self.assertEqual(ap.bl_target(0x1000, 0x97FFFFFF), 0x0FFC)
        self.assertEqual(ap.adrp_target(0x1234, 0x90000009)[0], 0x1000)


@unittest.skipUnless(PAYLOAD.exists() and RESULT.exists(), "local payload/analysis artifacts missing")
class RealPayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = ap.Payload(str(PAYLOAD))
        cls.r = json.loads(RESULT.read_text())

    def test_all_analyzer_checks_passed(self):
        self.assertTrue(all(c["ok"] for c in self.r["checks"]), [c for c in self.r["checks"] if not c["ok"]])

    def test_slot_is_where_the_symbol_and_the_magic_say(self):
        slot = int(self.r["slot"]["va"], 16)
        self.assertEqual(self.p.va(slot, 8), b"XNULDRST")
        # independent of the analyzer's segment walk: the raw bytes of the file at the mapped offset
        for vm, vs, fo, fs in self.p.segs:
            if vm <= slot < vm + fs:
                self.assertEqual(self.p.b[fo + slot - vm:fo + slot - vm + 8], b"XNULDRST")
                break
        else:
            self.fail("slot not file-backed")
        self.assertEqual(int(self.r["slot"]["pa_at_window_base"], 16) - int(self.r["window_base"], 16),
                         slot - self.p.virt_base)

    @unittest.skipIf(capstone is None, "capstone not installed")
    def test_asm_checkpoints_read_back_with_capstone(self):
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        slot = int(self.r["slot"]["va"], 16)
        for s in self.r["asm_checkpoints"]:
            va = int(s["va"], 16)
            ins = list(md.disasm(self.p.va(va, 15 * 4), va))
            txt = ["%s %s" % (i.mnemonic, i.op_str) for i in ins]
            n = s["checkpoint"]
            self.assertEqual(txt[0].split()[0], "adrp", txt[0])
            self.assertIn("%#x" % (slot & ~0xFFF), txt[0])
            self.assertEqual(txt[1], "add x9, x9, #%#x" % (slot & 0xFFF))
            self.assertEqual(txt[2], "ldr x10, [x9, #0x10]")
            self.assertEqual(txt[3], "cmp x10, #%d" % n)
            self.assertEqual(txt[4].split()[0], "b.ne")
            self.assertEqual(txt[5:9], ["mov x0, #0", "mov x1, #0", "mov x2, #2", "mov x3, #%d" % n])
            self.assertEqual(txt[9].split()[1:], ["x11,", "sctlr_el1"])
            self.assertTrue(txt[10].startswith("and x11, x11, #0xfffffffffffffffe") or txt[10].startswith("bic"))
            self.assertEqual(txt[11].split()[0:2], ["msr", "sctlr_el1,"])
            self.assertEqual(txt[12], "isb ")
            self.assertEqual(txt[13], "ldr x9, [x9, #8]")
            self.assertEqual(txt[14], "br x9")
            # the not-taken target of b.ne is the instruction after br x9, i.e. the checkpoint is skippable
            self.assertEqual(int(txt[4].split("#")[1], 16), va + 15 * 4)

    @unittest.skipIf(capstone is None, "capstone not installed")
    def test_c_checkpoint_sites_read_back_with_capstone(self):
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        chk = int(self.r["symbols"].get("_loader_checkpoint", {"va": "0"})["va"], 16) or ap.macho_symbols(
            str(ROOT / "artifacts/nat-020/build-003/kernel.no-storage"))["_loader_checkpoint"]
        for s in self.r["c_checkpoints"]:
            va = int(s["va"], 16)
            prev = list(md.disasm(self.p.va(va - 12, 16), va - 12))
            bl = prev[-1]
            self.assertEqual(bl.mnemonic, "bl")
            self.assertEqual(int(bl.op_str.lstrip("#"), 16), chk)
            movs = [i for i in prev[:-1] if i.mnemonic == "mov" and i.op_str.split(",")[0] in ("w0", "x0") and "#" in i.op_str]
            self.assertGreaterEqual(len(movs), 1, [str(i) for i in prev])
            # the argument is the nearest preceding immediate move into w0/x0 (an earlier call's may be in view)
            self.assertEqual(int(movs[-1].op_str.split("#")[1], 0), s["checkpoint"])

    def test_c_checkpoint_numbers_are_the_source_set(self):
        got = sorted(s["checkpoint"] for s in self.r["c_checkpoints"])
        self.assertEqual(got, sorted(list(range(10, 22)) + list(range(30, 36)) + list(range(40, 45))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
