"""Adversarial byte fixtures guard the verifier; they are not kernel execution evidence."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("xnu_macho_tools", ROOT / "tools/build/xnu_macho_tools.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


def image(names=None, flags=0x200001, protection=5, cpu=0x100000C, base=0xFFFFFFF007004000):
    names = names or ["__TEXT", "__DATA_CONST", "__TEXT_EXEC", "__DATA", "__LINKEDIT"]
    commands = []
    for i, name in enumerate(names):
        prot = 1 if name in ["__TEXT", "__DATA_CONST"] else protection
        commands.append(struct.pack("<II16sQQQQiiII", 0x19, 72, name.encode(), base + i * 0x4000,
                                    0x4000, 0, 0, prot, prot, 0, 0))
    return struct.pack("<IiiIIIII", 0xFEEDFACF, cpu, 0, 2, len(commands), sum(map(len, commands)), flags, 0) + b"".join(commands)


class MachoVerificationTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "owned-byte-fixture"
            path.write_bytes(data)
            return tools.macho(path)

    def test_truncated_header_commands_and_sections_are_rejected(self):
        original = image()
        for cut in [0, 4, 31, 32, len(original) - 1]:
            with self.assertRaises(ValueError):
                self.parse(original[:cut])
        malformed = bytearray(original)
        struct.pack_into("<I", malformed, 36, 0)
        with self.assertRaises(ValueError):
            self.parse(malformed)
        malformed = bytearray(original)
        struct.pack_into("<I", malformed, 32 + 64, 1000)
        with self.assertRaises(ValueError):
            self.parse(malformed)
        with self.assertRaises(ValueError):
            self.parse(image(cpu=0x1000007))

    def test_dynamic_or_default_base_output_cannot_claim_static_kernel_layout(self):
        with self.assertRaisesRegex(ValueError, "Static executable"):
            tools.require_kernel_layout(self.parse(image(flags=0x200005)))
        with self.assertRaisesRegex(ValueError, "high kernel image base"):
            tools.require_kernel_layout(self.parse(image(base=0x100000000)))

    def test_requested_order_and_protection_are_checked_from_encoded_bytes(self):
        good = self.parse(image())
        tools.require_kernel_layout(good)
        names = ["__TEXT", "__TEXT_EXEC", "__DATA_CONST", "__DATA", "__LINKEDIT"]
        with self.assertRaisesRegex(ValueError, "segment ordering"):
            tools.require_kernel_layout(self.parse(image(names=names)))
        with self.assertRaisesRegex(ValueError, "segment protection"):
            tools.require_kernel_layout(self.parse(image(protection=7)))

    def test_pie_pagezero_and_actual_vm_overlap_are_not_inferred_from_order(self):
        with self.assertRaisesRegex(ValueError, "PIE flag"):
            tools.require_kernel_layout(self.parse(image(flags=1)))
        actual = self.parse(image())
        actual["segments"][0]["vmsize"] = 0x8000
        with self.assertRaisesRegex(ValueError, "overlap"):
            tools.require_kernel_layout(actual)
        names = ["__PAGEZERO", "__TEXT", "__DATA_CONST", "__TEXT_EXEC", "__DATA", "__LINKEDIT"]
        with self.assertRaisesRegex(ValueError, "segment ordering"):
            tools.require_kernel_layout(self.parse(image(names=names)))


if __name__ == "__main__":
    unittest.main()
