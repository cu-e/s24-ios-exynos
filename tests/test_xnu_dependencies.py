"""Adversarial ABI record fixtures; these do not constitute target execution."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/build"))
spec = importlib.util.spec_from_file_location("xnu_dependencies", ROOT / "tools/build/xnu_dependencies.py")
dependencies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dependencies)


def fixture(copies=1):
    """Owned thin Mach-O with a file-backed section holding known integers."""
    command_size = 72 + 80 * copies
    offset = 32 + command_size
    payload = struct.pack("<9Q", 10, 4, 8, 4096, 262144, 128, 24, 24, 1584)
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, 0x100000C, 0, 1, 1, command_size, 0, 0)
    segment = struct.pack("<II16sQQQQiiII", 0x19, command_size, b"", 0, len(payload),
                          offset, len(payload), 3, 3, copies, 0)
    section = struct.pack("<16s16sQQIIIIIIII", b"__s24abi", b"__DATA_CONST", 0,
                          len(payload), offset, 3, 0, 0, 0, 0, 0, 0)
    return bytearray(header + segment + section * copies + payload)


class AbiRecordTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned-abi-object"
            path.write_bytes(data)
            return dependencies.read_abi(path)

    def test_encoded_record_is_read_without_execution(self):
        actual = self.parse(fixture())
        self.assertEqual(actual["max_cpus"], 10)
        self.assertEqual(actual["header_unused_offset"], 1584)
        self.assertEqual(len(actual), 9)

    def test_relocations_and_zerofill_cannot_claim_constant_bytes(self):
        for position, value in [(32 + 72 + 60, 1), (32 + 72 + 64, 1)]:
            data = fixture()
            struct.pack_into("<I", data, position, value)
            with self.subTest(position=position), self.assertRaises(ValueError):
                self.parse(data)

    def test_section_must_be_file_backed_outside_header(self):
        header_alias = fixture()
        struct.pack_into("<I", header_alias, 32 + 72 + 48, 0)
        outside_segment = fixture()
        struct.pack_into("<Q", outside_segment, 32 + 48, 8)
        for data in [header_alias, outside_segment, fixture()[:-1]]:
            with self.assertRaises(ValueError):
                self.parse(data)

    def test_duplicate_missing_and_wrong_size_records_are_rejected(self):
        missing = fixture()
        missing[32 + 72:32 + 72 + 16] = b"__unrelated".ljust(16, b"\0")
        wrong_size = fixture()
        struct.pack_into("<Q", wrong_size, 32 + 72 + 40, 8)
        for data in [fixture(copies=2), missing, wrong_size]:
            with self.assertRaises(ValueError):
                self.parse(data)

    def test_wrong_architecture_or_executable_is_rejected(self):
        for offset, value in [(4, 0x1000007), (12, 2)]:
            data = fixture()
            struct.pack_into("<I", data, offset, value)
            with self.assertRaises(ValueError):
                self.parse(data)


if __name__ == "__main__":
    unittest.main()
