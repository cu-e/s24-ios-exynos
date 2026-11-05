"""Compile the owned Wi-Fi input boundary against an explicitly pinned header."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/platform/wifi'
PROFILE = json.loads((SOURCE / 'profile.json').read_text())


class Window(C.Structure):
    _fields_ = [('cpu_start', C.c_size_t), ('bus_start', C.c_uint64), ('bytes', C.c_size_t)]


class WifiPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.include = ROOT / 'references/ath12k-wifi-current/include'
        if not shutil.which('cc') or not (cls.include / 'nw_abi.h').is_file():
            raise unittest.SkipTest('fetch pinned ath12k-wifi-current header and install a host C compiler explicitly')
        if hashlib.sha256((cls.include / 'nw_abi.h').read_bytes()).hexdigest() != PROFILE['donor']['header_sha256']:
            raise AssertionError('donor header differs from reviewed input')
        cls.temp = tempfile.TemporaryDirectory(prefix='s24-wifi-boundary-')
        out = Path(cls.temp.name)
        cls.flags = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-I', str(cls.include)]
        for extra, name in [(['-shared', '-fPIC'], 'boundary.so'), ([str(SOURCE / 'fixture.c')], 'fixture')]:
            r = subprocess.run([*cls.flags, str(SOURCE / 'e1s_wifi.c'), *extra, '-o', str(out / name)], capture_output=True, text=True, timeout=30)
            if r.returncode:
                cls.temp.cleanup()
                raise AssertionError(r.stderr)
        cls.fixture = out / 'fixture'
        cls.lib = C.CDLL(str(out / 'boundary.so'))
        cls.translate = cls.lib.e1s_wifi_translate
        cls.translate.argtypes = [C.POINTER(Window), C.c_size_t, C.c_size_t, C.POINTER(C.c_uint64)]
        cls.translate.restype = C.c_uint32

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_profile_callbacks_and_two_cpu_granules_without_callback_execution(self):
        r = subprocess.run([str(self.fixture)], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout), {'outcome': 'pass', 'environment': 'synthetic-wifi-binding',
                                              'range_pairs': 16384, 'callback_calls': 0, 'device_io': False})

    def test_bus_translation_is_not_cpu_identity_and_preserves_offsets(self):
        w = Window(0x4000000, 0x9ABC0000, 65536)
        for offset in (0, 1, 4095, 4096, 65535):
            with self.subTest(offset=offset):
                bus = C.c_uint64()
                self.assertEqual(self.translate(C.byref(w), w.cpu_start + offset, w.bytes - offset, C.byref(bus)), 0)
                self.assertEqual(bus.value, w.bus_start + offset)
                self.assertNotEqual(bus.value, w.cpu_start + offset)
                self.assertEqual(self.translate(C.byref(w), w.cpu_start + offset, w.bytes - offset + 1, C.byref(bus)), 3)
                self.assertEqual(bus.value, 0)

    def test_null_empty_outside_and_wrapped_dma_windows(self):
        for w, cpu, size in [(Window(0, 0x1000, 4096), 0, 1), (Window(0x1000, 0, 4096), 0x1000, 1),
                             (Window(0x1000, 0x9000, 0), 0x1000, 1), (Window(0x1000, 0x9000, 4096), 0xFFF, 1),
                             (Window(0x1000, 0x9000, 4096), 0x2000, 1), (Window(0x1000, 0x9000, 4096), 0x1000, 0),
                             (Window(0x1000, 2**64 - 1, 4096), 0x1000, 1), (Window(2**64 - 1, 0x9000, 4096), 2**64 - 1, 1)]:
            with self.subTest(cpu=cpu, size=size):
                bus = C.c_uint64(123)
                self.assertEqual(self.translate(C.byref(w), cpu, size, C.byref(bus)), 3)
                self.assertEqual(bus.value, 0)
        bus = C.c_uint64(123)
        self.assertEqual(self.translate(None, 0x1000, 1, C.byref(bus)), 3)
        self.assertEqual(bus.value, 0)

    def test_old_catalog_header_fails_current_abi_assertions(self):
        old = ROOT / 'references/ath12k-wifi/include'
        if not (old / 'nw_abi.h').is_file():
            self.skipTest('fetch the separately pinned catalog header for negative ABI check')
        self.assertEqual(hashlib.sha256((old / 'nw_abi.h').read_bytes()).hexdigest(), PROFILE['stale_catalog_donor']['header_sha256'])
        r = subprocess.run(['cc', '-std=c11', '-I', str(old), '-c', str(SOURCE / 'e1s_wifi.c'), '-o', str(Path(self.temp.name) / 'old.o')],
                           capture_output=True, text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0, 'stale header unexpectedly accepted')
        self.assertTrue('static assertion' in r.stderr or 'preempt_enable' in r.stderr, r.stderr)


if __name__ == '__main__':
    unittest.main()
