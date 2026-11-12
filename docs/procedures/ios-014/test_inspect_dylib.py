#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""IOS-014: tests of the pieces of inspect_dylib.py that decide `found`: C string literals, hex constants, and the A64 immediates.
Encodings are written as literals (derived by hand from the Arm ARM), not produced by the code under test."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inspect_dylib as I  # noqa: E402


def words(*ws):
    return b"".join(struct.pack("<I", w) for w in ws)


class Literals(unittest.TestCase):
    def test_adjacent_literals_are_one_string_and_escapes_decode(self):
        src = 'puts("a\\n" "b\\x41" /* gap */ "\\101z");\nputs("two");'
        self.assertEqual(I.string_literals(src), [b"a\nbAAz", b"two"])

    def test_comments_and_include_lines_hold_no_literals(self):
        src = '#include "hakios.gl.h"\n// "no"\n/* "no" */ char c = \'"\'; const char *s = "yes";'
        self.assertEqual(I.string_literals(src), [b"yes"])

    def test_hex_constants_skip_short_ones_and_strings(self):
        src = 'x = 0x1882f0908UL; y = 0xff; s = "0x1234567"; z = 0X180000000;'
        self.assertEqual(sorted(I.hex_constants(src)), [0x180000000, 0x1882f0908])

    def test_a_quote_character_literal_does_not_swallow_the_next_constant(self):
        src = "c = '\"'; v = 0x1234567; s = \"it's\"; w = 0x7654321;"
        self.assertEqual(sorted(I.hex_constants(src)), [0x1234567, 0x7654321])


class Immediates(unittest.TestCase):
    def test_movz_movk_sequence(self):
        # movz x0,#0x8000,lsl #16 ; movk x0,#1,lsl #32  -> 0x180000000
        out = I.decode_movs(words(0xD2B00000, 0xF2C00020), 0x4000)
        self.assertEqual(out[0x80000000], 0x4000)
        self.assertEqual(out[0x180000000], 0x4004)

    def test_movn(self):
        # movn x0,#0 -> all ones ; movn w1,#0xff -> 0xffffff00
        out = I.decode_movs(words(0x92800000, 0x1280 << 16 | 0x1FE1), 0)
        self.assertIn(0xFFFFFFFFFFFFFFFF, out)

    def test_orr_bitmask_immediate(self):
        # orr x0,xzr,#0x180000000 ; orr x0,xzr,#0x5555555555555555
        out = I.decode_movs(words(0xB26107E0, 0xB200F3E0), 0)
        self.assertIn(0x180000000, out)
        self.assertIn(0x5555555555555555, out)

    def test_orr_with_a_real_source_register_is_not_a_constant(self):
        # orr x0,x1,#0x5555555555555555 (Rn=1)
        self.assertEqual(I.decode_movs(words(0xB200F020), 0), {})

    def test_movk_without_movz_is_ignored(self):
        self.assertEqual(I.decode_movs(words(0xF2C00020), 0), {})

    def test_reserved_bitmask_is_none(self):
        self.assertIsNone(I.bitmask_immediate(1, 0, 0, 0x3F))  # all ones is not encodable
        self.assertIsNone(I.bitmask_immediate(0, 1, 0, 1))      # N=1 with a 32-bit register is reserved


if __name__ == "__main__":
    unittest.main()
