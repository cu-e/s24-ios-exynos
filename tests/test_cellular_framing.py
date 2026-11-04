"""Owned fixed-wire examples and malformed-frame boundaries, no hardware I/O."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / "src/platform/cellular/contracts/framing.py"
SPEC = importlib.util.spec_from_file_location("cellular_framing", PATH)
framing = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = framing
SPEC.loader.exec_module(framing)


class CellularFramingTests(unittest.TestCase):
    def test_known_sipc5_base_extended_and_fragment_headers(self):
        examples = [
            (bytes.fromhex("f82a0700616263"), None),
            (bytes.fromhex("fa2a09000000616263"), None),
            (bytes.fromhex("fb2a080081616263"), 0x81),
        ]
        for wire, control in examples:
            with self.subTest(wire=wire.hex()):
                f = framing.parse_frame(wire, "sipc5")
                self.assertEqual((f.channel, f.payload, f.control, f.consumed), (42, b"abc", control, len(wire)))

    def test_sipc_padding_is_consumed_without_assuming_zero(self):
        wire = bytes.fromhex("fc2a070061626399")
        f = framing.parse_frame(wire + b"next frame", "sipc5")
        self.assertEqual((f.payload, f.wire_length, f.consumed), (b"abc", 7, 8))

    def test_known_sit_wire_header_is_twelve_not_packed_struct_ten(self):
        wire = bytes.fromhex("cdab070000c00f002a03aabb616263ff")
        f = framing.parse_frame(wire + b"tail", "sit")
        self.assertEqual((f.channel, f.sequence, f.channel_sequence, f.control), (42, 7, 3, 0xC000))
        self.assertEqual((f.extension, f.payload, f.wire_length, f.consumed), (b"\xaa\xbb", b"abc", 15, 16))
        with self.assertRaises(framing.TruncatedFrame):
            framing.parse_frame(wire[:10], "sit")

    def test_every_truncated_prefix_is_rejected(self):
        for mode, wire in [("sipc5", bytes.fromhex("fe2a0900000061626300000000000000")),
                           ("sit", bytes.fromhex("cdab070000c00f002a03aabb616263ff"))]:
            for n in range(len(wire)):
                with self.subTest(mode=mode, bytes=n), self.assertRaises(framing.TruncatedFrame):
                    framing.parse_frame(wire[:n], mode)

    def test_bad_sync_and_unsupported_variant_do_not_guess_a_protocol(self):
        for wire, mode in [(b"\x00\x2a\x04\x00", "sipc5"), (b"\xf9\x2a\x04\x00", "sipc5"), (b"\x00" * 16, "sit")]:
            with self.subTest(mode=mode, wire=wire), self.assertRaises(framing.FrameError):
                framing.parse_frame(wire, mode)
        for mode in [None, "auto", "qmi", ""]:
            with self.subTest(mode=mode), self.assertRaises(framing.FrameError):
                framing.parse_frame(b"\xf8\x2a\x04\x00", mode)

    def test_invalid_lengths_and_32bit_oversize_never_allocate_payload(self):
        for mode, wire in [("sipc5", b"\xf8\x2a\x03\x00"),
                           ("sipc5", b"\xfa\x2a" + struct.pack("<I", 0xFFFFFFFF)),
                           ("sit", struct.pack("<HHHHBBH", 0xABCD, 0, 0, 10, 42, 0, 0))]:
            with self.subTest(mode=mode), self.assertRaises(framing.FrameError):
                framing.parse_frame(wire, mode)
        for budget in [0, -1, framing.MAX_FRAME + 1, True, 1.5]:
            with self.subTest(budget=budget), self.assertRaises(framing.FrameError):
                framing.parse_frame(b"\xf8\x2a\x04\x00", "sipc5", max_frame=budget)


if __name__ == "__main__":
    unittest.main()
