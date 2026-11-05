"""Exercise compiled C wire validation with owned synthetic bytes, no GPU I/O."""
import ctypes as C
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/platform/gpu/abi"
MAGIC = 0x31584753


class Fake(C.Structure):
    _fields_ = [("calls", C.c_uint64), ("stopped", C.c_uint32), ("reserved", C.c_uint32)]


def frame(op, payload=b"", *, major=1, minor=0, flags=0, reserved=0, request_id=42):
    return struct.pack("<IHHIIQII", MAGIC, major, minor, op, 32 + len(payload), request_id, flags, reserved) + payload


def query(**kwargs):
    return frame(1, struct.pack("<HHHHQ", 1, 1, 0, 0, 0), **kwargs)


def submit(ibs=None, uses=None, deps=None):
    ibs = [(7, 0, 16, 0, 0)] if ibs is None else ibs
    uses = [(7, 1, 0)] if uses is None else uses
    deps = [99] if deps is None else deps
    return frame(11, struct.pack("<QIIII", 1, len(ibs), len(uses), len(deps), 0)
                 + b"".join(struct.pack("<QQQII", *ib) for ib in ibs)
                 + b"".join(struct.pack("<QII", *use) for use in uses)
                 + b"".join(struct.pack("<Q", fence) for fence in deps))


def examples():
    return [query(), frame(2, struct.pack("<QQII", 1, 4096, 3, 0)), frame(3, struct.pack("<Q", 7)),
            frame(4, struct.pack("<IIQ", 0, 0, 0)), frame(5, struct.pack("<Q", 1)),
            frame(6, struct.pack("<QQQII", 7, 0, 4096, 3, 0)), frame(7, struct.pack("<Q", 7)),
            frame(8, struct.pack("<QQQQQII", 1, 7, 0x100000, 0, 4096, 3, 0)),
            frame(9, struct.pack("<QQQ", 1, 0x100000, 4096)),
            frame(10, struct.pack("<QQQII", 7, 0, 4096, 1, 0)), submit(),
            frame(12, struct.pack("<QQ", 99, 100_000_000)), frame(13)]


class GpuAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("cc"):
            raise unittest.SkipTest("host C compiler unavailable")
        cls.temp = tempfile.TemporaryDirectory(prefix="s24-sgpu-abi-")
        cls.lib_path = Path(cls.temp.name) / "abi.so"
        result = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wpedantic", "-shared", "-fPIC",
                                 str(SOURCE / "sgpu_abi.c"), str(SOURCE / "sgpu_fake.c"), "-o", str(cls.lib_path)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(cls.lib_path))
        cls.exchange_fn = cls.lib.sgpu_fake_exchange
        cls.exchange_fn.argtypes = [C.POINTER(Fake), C.c_void_p, C.c_size_t, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        cls.exchange_fn.restype = C.c_uint32

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def exchange(self, wire, *, state=None, capacity=120):
        state = state if state is not None else Fake()
        source = C.create_string_buffer(wire, max(1, len(wire)))
        output = (C.c_uint8 * (capacity + 16))(*([0xA5] * (capacity + 16)))
        length = C.c_size_t(12345)
        status = self.exchange_fn(C.byref(state), source, len(wire), C.byref(output, 8), capacity, C.byref(length))
        self.assertEqual(bytes(output[:8]), b"\xa5" * 8)
        self.assertEqual(bytes(output[-8:]), b"\xa5" * 8)
        self.assertEqual(source.raw[:len(wire)], wire)
        self.assertLessEqual(length.value, capacity)
        data = bytes(output[8:8 + length.value])
        if length.value:
            magic, major, minor, op, size, request_id, reply_status, reserved = struct.unpack("<IHHIIQII", data[:32])
            self.assertEqual((magic, major, minor, size, reply_status, reserved), (MAGIC, 1, 0, len(data), status, 0))
            if len(wire) >= 32:
                self.assertEqual((op, request_id), (struct.unpack_from("<I", wire, 8)[0], struct.unpack_from("<Q", wire, 16)[0]))
            self.assertEqual(bytes(output[8 + length.value:8 + capacity]), b"\x00" * (capacity - length.value))
        return status, data, state

    def rejected(self, wire):
        status, data, state = self.exchange(wire)
        self.assertNotEqual(status, 0)
        self.assertEqual(state.calls, 0, "malformed input reached backend")
        self.assertIn(len(data), (0, 32))

    def test_all_core_request_shapes_and_no_fake_hardware_claim(self):
        for wire in examples():
            with self.subTest(op=struct.unpack_from("<I", wire, 8)[0]):
                status, data, state = self.exchange(wire)
                self.assertEqual(state.calls, 1)
                self.assertEqual(status, 0 if struct.unpack_from("<I", wire, 8)[0] in (1, 13) else 4)
        status, data, _ = self.exchange(query())
        self.assertEqual(status, 0)
        self.assertEqual(len(data), 120)
        self.assertEqual(struct.unpack_from("<Q", data, 32)[0], 0x8000000000000001)
        self.assertEqual(data[40:92], b"\x00" * 52)  # epoch/budget/VA/pages unknown
        self.assertEqual(struct.unpack_from("<I", data, 112)[0], 0)  # profile not verified

    def test_every_truncated_prefix_and_trailing_byte_are_rejected(self):
        for wire in examples():
            for size in range(len(wire)):
                with self.subTest(op=wire[8], size=size):
                    self.rejected(wire[:size])
            self.rejected(wire + b"\x00")
            larger = bytearray(wire + b"\x00")
            struct.pack_into("<I", larger, 12, len(larger))
            self.rejected(bytes(larger))

    def test_headers_negotiation_unknown_opcode_and_required_features(self):
        for wire in [query(major=0), query(major=2), query(minor=1), query(flags=1), query(reserved=1), query(request_id=0),
                     frame(1, struct.pack("<HHHHQ", 2, 3, 0, 0, 0)), frame(1, struct.pack("<HHHHQ", 2, 1, 0, 0, 0)),
                     frame(1, struct.pack("<HHHHQ", 1, 1, 1, 2, 0)), frame(0xFFFFFFFF), frame(14), frame(0x100)]:
            self.rejected(wire)
        wrong_magic = b"1XGS" + query()[4:]
        self.rejected(wrong_magic)
        status, data, state = self.exchange(frame(1, struct.pack("<HHHHQ", 1, 1, 0, 0, 2)))
        self.assertEqual((status, len(data), state.calls), (4, 32, 1))

    def test_reserved_fields_zero_handles_and_range_overflow(self):
        for op, offset in [(2, 20), (4, 4), (4, 8), (6, 28), (8, 44), (10, 28), (11, 20), (11, 48), (11, 52), (11, 68)]:
            wire = bytearray(examples()[op - 1])
            struct.pack_into("<I", wire, 32 + offset, 1)
            self.rejected(bytes(wire))
        for op in (3, 5, 6, 7, 8, 9, 10, 11, 12):
            wire = bytearray(examples()[op - 1])
            struct.pack_into("<Q", wire, 32, 0)
            self.rejected(bytes(wire))
        for wire in [frame(2, struct.pack("<QQII", 0, 4096, 3, 0)),
                     frame(2, struct.pack("<QQII", 128 * 1024 * 1024 + 1, 4096, 3, 0)),
                     frame(2, struct.pack("<QQII", 4096, 8193, 3, 0)),
                     frame(6, struct.pack("<QQQII", 7, 2**64 - 1, 1, 3, 0)),
                     frame(8, struct.pack("<QQQQQII", 1, 7, 2**64 - 4096, 0, 8192, 3, 0)),
                     frame(8, struct.pack("<QQQQQII", 1, 7, 0x100001, 0, 4096, 3, 0)),
                     frame(10, struct.pack("<QQQII", 7, 0, 4096, 3, 0)),
                     frame(12, struct.pack("<QQ", 99, 100_000_001))]:
            self.rejected(wire)

    def test_submit_counts_dependencies_and_ib_reference_validation(self):
        invalid = [submit(ibs=[]), submit(uses=[]), submit(uses=[(8, 1, 0)]), submit(uses=[(7, 2, 0)]),
                   submit(uses=[(7, 1, 0), (7, 1, 0)]), submit(deps=[0]), submit(deps=[99, 99]),
                   submit(ibs=[(7, 2**64 - 4, 8, 0, 0)]), submit(ibs=[(7, 0, 65540, 0, 0)]),
                   submit(ibs=[(7, 1, 16, 0, 0)]), submit(uses=[(7, 8, 0)])]
        for offset in (8, 12, 16):
            wire = bytearray(submit())
            struct.pack_into("<I", wire, 32 + offset, 0xFFFFFFFF)
            invalid.append(bytes(wire))
        for wire in invalid:
            self.rejected(wire)
        maximum = submit(ibs=[(7, 0, 65536, 0, 0)] * 8, uses=[(h, 1, 0) for h in range(7, 71)], deps=list(range(100, 132)))
        status, _, state = self.exchange(maximum)
        self.assertEqual((status, state.calls), (4, 1))

    def test_stop_is_idempotent_and_cannot_manufacture_retirement(self):
        state = Fake()
        for wire in [frame(13), frame(13), query()]:
            self.assertEqual(self.exchange(wire, state=state)[0], 0)
        for wire in [submit(), frame(12, struct.pack("<QQ", 99, 0)), examples()[1]]:
            status, data, state = self.exchange(wire, state=state)
            self.assertEqual((status, len(data)), (8, 32))
        for guessed_completion in (14, 15, 0xFFFF):
            before = state.calls
            status, _, state = self.exchange(frame(guessed_completion, struct.pack("<Q", 99)), state=state)
            self.assertEqual((status, state.calls), (4, before))

    def test_output_capacity_overlap_and_unaligned_storage(self):
        for capacity in (0, 31, 119, 4097):
            status, data, state = self.exchange(query(), capacity=capacity)
            self.assertEqual((status, data, state.calls), (1, b"", 0))
        source = C.create_string_buffer(query(), 256)
        length = C.c_size_t()
        state = Fake()
        status = self.exchange_fn(C.byref(state), source, 48, source, 120, C.byref(length))
        self.assertEqual((status, length.value, state.calls), (5, 0, 0))
        # Byte codec must accept unaligned input; structure casts would be wrong.
        source = C.create_string_buffer(b"!" + query())
        out = C.create_string_buffer(120)
        status = self.exchange_fn(C.byref(state), C.byref(source, 1), 48, out, 120, C.byref(length))
        self.assertEqual((status, length.value), (0, 120))
        self.rejected(b"\x00" * 4097)


if __name__ == "__main__":
    unittest.main()
