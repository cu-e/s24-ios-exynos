"""Owned fragmented H4 and command-lifecycle cases; compiled C, no UART access."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/platform/bluetooth'
CALLBACK = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint8, C.POINTER(C.c_uint8), C.c_size_t)


class Parser(C.Structure):
    _fields_ = [('storage', C.POINTER(C.c_uint8)), ('capacity', C.c_size_t), ('used', C.c_size_t),
                ('header', C.c_size_t), ('expected', C.c_size_t), ('started_ms', C.c_uint64), ('last_ms', C.c_uint64),
                ('timeout_ms', C.c_uint32), ('direction', C.c_uint32), ('ibs', C.c_uint32),
                ('fault', C.c_uint32), ('clock_seen', C.c_uint32), ('busy', C.c_uint32)]


class Command(C.Structure):
    _fields_ = [('epoch', C.c_uint64), ('started_ms', C.c_uint64), ('last_ms', C.c_uint64),
                ('timeout_ms', C.c_uint32), ('pending', C.c_uint32), ('stopped', C.c_uint32),
                ('quarantined', C.c_uint32), ('clock_seen', C.c_uint32), ('opcode', C.c_uint16), ('credits', C.c_uint8)]


class Reply(C.Structure):
    _fields_ = [('parameters', C.POINTER(C.c_uint8)), ('parameter_bytes', C.c_size_t), ('opcode', C.c_uint16),
                ('credits', C.c_uint8), ('status', C.c_uint8), ('status_valid', C.c_uint8)]


class BluetoothTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'):
            raise unittest.SkipTest('host C compiler unavailable')
        cls.temp = tempfile.TemporaryDirectory(prefix='s24-bt-transport-')
        cls.library = Path(cls.temp.name) / 'transport.so'
        r = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-shared', '-fPIC',
                            str(SOURCE / 'transport.c'), '-o', str(cls.library)], capture_output=True, text=True, timeout=30)
        if r.returncode:
            cls.temp.cleanup()
            raise AssertionError(r.stderr)
        cls.lib = C.CDLL(str(cls.library))
        cls.lib.bt_h4_init.argtypes = [C.POINTER(Parser), C.c_void_p, C.c_size_t, C.c_uint32, C.c_uint32, C.c_uint32]
        cls.lib.bt_h4_feed.argtypes = [C.POINTER(Parser), C.c_void_p, C.c_size_t, C.c_uint64, CALLBACK, C.c_void_p, C.POINTER(C.c_size_t)]
        cls.lib.bt_command_init.argtypes = [C.POINTER(Command), C.c_uint64, C.c_uint8]
        cls.lib.bt_command_begin.argtypes = [C.POINTER(Command), C.c_uint16, C.c_uint64, C.c_uint32]
        cls.lib.bt_command_tick.argtypes = [C.POINTER(Command), C.c_uint64]
        cls.lib.bt_command_event.argtypes = [C.POINTER(Command), C.c_void_p, C.c_size_t, C.c_uint64, C.POINTER(Reply)]
        cls.lib.bt_command_stop.argtypes = [C.POINTER(Command)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def parser(self, *, direction=1, ibs=0, timeout=100, capacity=128):
        p = Parser()
        p.backing = (C.c_uint8 * (capacity + 16))(*([0xA5] * (capacity + 16)))
        self.assertEqual(self.lib.bt_h4_init(C.byref(p), C.byref(p.backing, 8), capacity, direction, ibs, timeout), 0)
        p.frames = []
        return p

    def feed(self, p, data=b'', now=10, callback=None):
        buf = C.create_string_buffer(data, max(1, len(data)))
        cb = CALLBACK(callback or (lambda context, kind, wire, length: p.frames.append((kind, C.string_at(wire, length))) or 0))
        consumed = C.c_size_t(999)
        result = self.lib.bt_h4_feed(C.byref(p), buf, len(data), now, cb, None, C.byref(consumed))
        self.assertLessEqual(consumed.value, len(data))
        self.assertEqual(bytes(p.backing[:8]), b'\xa5' * 8)
        self.assertEqual(bytes(p.backing[-8:]), b'\xa5' * 8)
        return result, consumed.value

    def command(self, credits=1):
        p = Command()
        self.assertEqual(self.lib.bt_command_init(C.byref(p), 1, credits), 0)
        return p

    def event(self, p, wire, now):
        r = Reply()
        buf = C.create_string_buffer(wire, max(1, len(wire)))
        result = self.lib.bt_command_event(C.byref(p), buf, len(wire), now, C.byref(r))
        return result, r, C.string_at(r.parameters, r.parameter_bytes) if r.parameter_bytes else b''

    def test_all_h4_types_every_fragment_boundary_and_opaque_ibs_payload(self):
        examples = [(2, bytes.fromhex('01030c00')), (1, bytes.fromhex('0201200300fdfcfe')),
                    (1, bytes.fromhex('030100026162')), (1, bytes.fromhex('04ff03fdfcfe')),
                    (1, bytes.fromhex('05010003c011fdfe'))]
        for direction, wire in examples:
            for split in range(len(wire) + 1):
                with self.subTest(kind=wire[0], split=split):
                    p = self.parser(direction=direction)
                    self.feed(p, wire[:split])
                    result, used = self.feed(p, wire[split:])
                    self.assertEqual((result, used, p.frames), (0, len(wire) - split, [(wire[0], wire)]))
            p = self.parser(direction=direction)
            for byte in wire:
                self.feed(p, bytes([byte]))
            self.assertEqual(p.frames, [(wire[0], wire)])

    def test_ibs_requires_explicit_mode_and_never_resynchronizes_noise(self):
        p = self.parser(ibs=1)
        stream = bytes.fromhex('fcfdfe04ff03fcfdfe')
        self.assertEqual(self.feed(p, stream), (0, len(stream)))
        self.assertEqual([kind for kind, _ in p.frames], [0xFC, 0xFD, 0xFE, 4])
        for byte in (0xFC, 0xFD, 0xFE, 0, 0xFF):
            p = self.parser()
            self.assertEqual(self.feed(p, bytes([byte]))[0], 3)
            self.assertEqual(self.feed(p, bytes.fromhex('040e03010000')), (3, 0))
            self.assertEqual(p.frames, [])
        self.assertEqual(self.feed(self.parser(), bytes.fromhex('01030c00'))[0], 10)

    def test_frame_size_deadline_clock_and_consumer_quarantine(self):
        p = self.parser(capacity=16)
        self.assertEqual(self.feed(p, bytes.fromhex('020100ffff'))[0], 4)
        self.assertEqual(self.feed(p, b'abc'), (4, 0))
        p = self.parser(timeout=10)
        self.assertEqual(self.feed(p, bytes.fromhex('04ff03'), now=100)[0], 1)
        self.assertEqual(self.feed(p, now=110), (5, 0))
        self.assertEqual(self.feed(p, b'abc', now=111), (5, 0))
        p = self.parser()
        self.feed(p, bytes.fromhex('04ff03'), now=100)
        self.assertEqual(self.feed(p, now=99)[0], 6)
        p = self.parser()
        self.assertEqual(self.feed(p, bytes.fromhex('04ff00'), callback=lambda *args: 1)[0], 9)
        self.assertEqual(self.feed(p, bytes.fromhex('04ff00')), (9, 0))

    def test_frame_and_byte_budgets_yield_with_exact_consumption(self):
        p = self.parser()
        stream = bytes.fromhex('04ff00') * 80
        result, used = self.feed(p, stream)
        self.assertEqual((result, used, len(p.frames)), (2, 192, 64))
        self.assertEqual(self.feed(p, stream[used:]), (0, 48))
        self.assertEqual(len(p.frames), 80)
        wire = bytes.fromhex('0201001027') + b'x' * 10000
        p = self.parser(capacity=12000)
        at = 0
        while at < len(wire):
            result, used = self.feed(p, wire[at:])
            self.assertGreater(used, 0)
            self.assertLessEqual(used, 4096)
            at += used
        self.assertEqual((result, p.frames), (0, [(2, wire)]))

    def test_reentrant_feed_rejected_while_borrowed_frame_is_live(self):
        p = self.parser()
        nested = []
        def emit(*args):
            nested.append(self.feed(p)[0])
            return 0
        self.assertEqual(self.feed(p, bytes.fromhex('04ff00'), callback=emit), (0, 3))
        self.assertEqual(nested, [7])

    def test_command_credits_opcode_matching_and_raw_error_return(self):
        p = self.command(credits=0)
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0x0C03, 100, 50), 6)
        self.assertEqual(self.event(p, bytes.fromhex('040e03010000'), 101)[0], 4)
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0x0C03, 102, 50), 0)
        self.assertEqual(self.event(p, bytes.fromhex('040e0401011000'), 103)[0], 4)
        self.assertTrue(p.pending)
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0x1001, 103, 50), 5)
        self.assertEqual(self.event(p, bytes.fromhex('040f040001030c'), 104)[0], 2)
        self.assertTrue(p.pending)
        result, reply, raw = self.event(p, bytes.fromhex('040e0400030c0c'), 105)
        self.assertEqual((result, reply.status_valid, raw, p.pending, p.credits), (1, 0, b'\x0c', 0, 0))
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0x0C03, 106, 50), 6)

    def test_command_timeout_stop_clock_and_failed_status_are_not_success(self):
        p = self.command()
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0xFC00, 2**64 - 100, 20), 0)
        self.assertEqual(self.lib.bt_command_tick(C.byref(p), 2**64 - 80), 7)
        self.assertTrue(p.pending)
        self.assertEqual(self.event(p, bytes.fromhex('040e040100fc00'), 2**64 - 79)[0], 8)
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0xFC00, 2**64 - 79, 20), 8)
        p = self.command()
        self.lib.bt_command_begin(C.byref(p), 0x0C03, 100, 50)
        self.lib.bt_command_stop(C.byref(p))
        self.assertTrue(p.pending)
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0x1001, 101, 20), 9)
        self.assertEqual(self.event(p, bytes.fromhex('040e0401030c00'), 102)[0], 1)
        self.assertEqual(self.lib.bt_command_begin(C.byref(p), 0x1001, 103, 20), 9)
        p = self.command()
        self.lib.bt_command_begin(C.byref(p), 0x0C03, 100, 50)
        result, reply, _ = self.event(p, bytes.fromhex('040f040c01030c'), 101)
        self.assertEqual((result, reply.status_valid, reply.status, p.pending), (3, 1, 12, 0))
        p = self.command()
        self.lib.bt_command_begin(C.byref(p), 0x0C03, 100, 50)
        self.assertEqual(self.lib.bt_command_tick(C.byref(p), 99), 11)
        self.assertTrue(p.quarantined)


if __name__ == '__main__':
    unittest.main()
