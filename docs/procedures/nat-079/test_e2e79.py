#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-079 host tests, USB side: the real tools/ios/root_send.py sender against the NAT-076 DWC3 model, with the exact text of the loader's
receive phase (src/nat079_impl.h) in the same translation unit (fixture79.c). Evidence kind: host-test.

    python3 -I docs/procedures/nat-079/test_e2e79.py        (needs only `cc`)

What it shows: the placeholder handoff works end to end. The engine is up with a 512-byte placeholder, so the sender cannot send a root image;
after nat079_receive_root() has validated the range and passed the CPU self-test the capacity GET_RX reports is the reserve and the sender
delivers into the reserve and nowhere else; every way the phase can end (every byte committed, the cap, a failed self-test, a host that spoke
too early, the engine going down) is reached with the sender in the loop. What it is not: the S24. The model is a reading of the DWC3
documentation; the question whether the S24's controller can DMA into memory above 4 GiB (NAT-040 item U5) is not answered here: the test
that sets a DMA limit shows what the loader and the sender report when it cannot.

Expected values come from the data that was sent, the model's destination memory and its violation list, and numbers fixed by hand (the
GET_RX layout of usbmon.h, the placeholder size), not from calling the code under test."""
import ctypes
import importlib.util
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
KIB = 1024
PAGE = 16 * KIB
HOLD = 512
GUARD = 0xEE				# the model fills its window with this
FREQ = 1000				# fixture79.c's counter frequency
# NAT079_* status codes, written from src/nat079_fixed.h (not parsed from it, so a renumbering is noticed)
DONE, NO_ENGINE, NOT_PRESENT, BAD_ARGS, PREMATURE, SELFTEST, TIMEOUT, ENGINE_DOWN, INCONSISTENT = 0, 1, 2, 3, 4, 5, 6, 7, 8
# GET_RX reply layout (usbmon.h struct usbmon_rx_info): flags at 12, committed at 16, capacity at 40
RX_FLAGS_AT, RX_COMMITTED_AT, RX_CAPACITY_AT = 12, 16, 40
RXF_PRESENT, RXF_ENABLED = 1, 2


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rs = load("nat079_e2e_root_send", ROOT / "tools/ios/root_send.py")
M = load("nat079_e2e_modelhost", PROC / "nat-076/modelhost.py")
MV = load("nat079_e2e_make_variant79", HERE / "make_variant79.py")


class Result(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ("pa", "bytes", "committed", "rx_bytes", "trbs", "errors", "resets", "dups", "gaps", "rejects",
                                              "aborts", "last_sum", "elapsed_ticks", "freq", "selftest_bad_pa")] + \
               [("status", ctypes.c_int32), ("pad", ctypes.c_int32)]


_libs = {}
_tmp = None


def build_lib(direct, cap_s=5, report_s=1):
    """fixture79.c + the engine, with a generated nat079.h of the given parameters. Built once per parameter set."""
    global _tmp
    key = (direct, cap_s, report_s)
    if key in _libs:
        return _libs[key]
    if _tmp is None:
        _tmp = tempfile.mkdtemp(prefix="nat079-e2e-")
    gen = Path(_tmp) / ("gen-%d-%d-%d" % key)
    gen.mkdir()
    (gen / "nat079.h").write_bytes(MV.header_text(cap_s, direct, report_s).encode())
    out = Path(_tmp) / ("libfx-%d-%d-%d.so" % key)
    cmd = ["cc"] + M.CC_FLAGS + ["-I", str(PROC / "nat-076/engine"), "-I", str(PROC / "nat-076/model"), "-I", str(HERE / "src"), "-I", str(gen),
                                 str(PROC / "nat-076/engine/usbmon.c"), str(HERE / "fixture79.c"), "-o", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        raise RuntimeError("fixture build failed or warned (%d):\n%s" % (r.returncode, r.stderr))
    lib = str(out)
    _libs[key] = lib
    return lib


def tearDownModule():
    if _tmp:
        shutil.rmtree(_tmp, ignore_errors=True)


class ModelTransport(rs.Transport):
    """The model machine as the sender's transport."""

    def __init__(self, m):
        self.m = m
        self.begins = []

    def rx_begin(self, offset, length):
        self.begins.append((offset, length))
        rc, _ = self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", offset, length, 0))
        if rc != M.H_OK:
            raise rs.TransportError("RX_BEGIN: %s" % M.RC_NAMES.get(rc, rc))

    def rx_abort(self):
        rc, _ = self.m.ctrl(0x40, 8, 0, 0, 0)
        if rc != M.H_OK:
            raise rs.TransportError("RX_ABORT: %s" % M.RC_NAMES.get(rc, rc))

    def get_rx(self):
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        if rc != M.H_OK:
            raise rs.TransportError("GET_RX: %s" % M.RC_NAMES.get(rc, rc))
        return raw

    def bulk_write(self, data):
        rc, took = self.m.bulk_out(data)
        if rc != M.H_OK:
            raise rs.TransportError("bulk OUT: %s after %d bytes" % (M.RC_NAMES.get(rc, rc), took))
        return took

    def reconnect(self):
        self.m.bus_reset()
        for name, rc, _ in self.m.enumerate(address=9):
            assert rc == M.H_OK, name


def u32(raw, at):
    return struct.unpack_from("<I", raw, at)[0]


def u64(raw, at):
    return struct.unpack_from("<Q", raw, at)[0]


class Rig:
    """One simulated machine: the engine up with the 512-byte placeholder at the start of the model's window, the reserve 16 KiB aligned
    further in, 0xEE guard memory on both sides."""

    def __init__(self, lib, size, direct, ring_size=1 << 16):
        self.lib = lib
        self.size = size
        self.m = M.Machine(lib, ring_size=ring_size, auto_init=False)
        self.fx = self.m.lib
        for name, res, args in (("fx_reset", None, [ctypes.c_uint64]), ("fx_set_up", None, [ctypes.c_int]),
                                ("fx_set_stuck", None, [ctypes.c_uint64, ctypes.c_uint64]), ("fx_window_base", ctypes.c_uint64, []),
                                ("fx_window_size", ctypes.c_uint64, []), ("fx_ticks", ctypes.c_uint64, []), ("fx_polls", ctypes.c_uint64, []),
                                ("fx_result_size", ctypes.c_uint32, []), ("fx_rx_dest", ctypes.c_uint64, []),
                                ("fx_rx_size", ctypes.c_uint64, []),
                                ("fx_receive", ctypes.c_int, [ctypes.c_uint64, ctypes.c_uint64, ctypes.POINTER(Result)])):
            f = getattr(self.fx, name)
            f.restype, f.argtypes = res, args
        self.CB = ctypes.CFUNCTYPE(None)
        self.fx.fx_set_cb.argtypes = [self.CB]
        self.fx.fx_reset(1)
        self.fx.t_set_window(size + 5 * PAGE)
        self.base = self.fx.fx_window_base()
        self.pa = ((self.base + HOLD + PAGE - 1) // PAGE) * PAGE + PAGE
        self.off = self.pa - self.base
        assert self.off + size + PAGE <= self.fx.fx_window_size()
        self.init_rc = self.m.init(rx_size=HOLD, rx_direct=direct)
        assert self.init_rc == 0, self.init_rc
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            assert rc == M.H_OK, name
        self.t = ModelTransport(self.m)
        self.host_error = None
        self.host_result = None
        self._cb = None

    def close(self):
        self.m.close()

    def rx(self):
        return self.t.get_rx()

    def capacity(self):
        return u64(self.rx(), RX_CAPACITY_AT)

    def receive(self, host=None, step=1):
        """Call the loader's receive phase. host: a function run once, inside the first engine poll of the loop (the sender), or None."""
        self.fx.fx_reset(step)
        if host is not None:
            def run():
                try:
                    self.host_result = host()
                except Exception as e:				# ctypes would print and swallow it
                    self.host_error = e
            self._cb = self.CB(run)
            self.fx.fx_set_cb(self._cb)
        r = Result()
        rc = self.fx.fx_receive(self.pa, self.size, ctypes.byref(r))
        assert rc == r.status, (rc, r.status)
        return r

    def send(self, data, **kw):
        kw.setdefault("sleep", lambda s: None)
        return rs.send(self.t, data, **kw)

    def window(self):
        return self.m.dest(0, self.fx.fx_window_size())

    def untouched_outside_reserve(self):
        """Every window byte outside [pa, pa + size) still holds the guard value (the placeholder and both guard areas included)."""
        w = self.window()
        return w[:self.off] == bytes([GUARD]) * self.off and w[self.off + self.size:] == bytes([GUARD]) * (len(w) - self.off - self.size)


def blob(n, seed):
    return random.Random(seed).randbytes(n)


class Base(unittest.TestCase):
    DIRECT = 1
    SIZE = 256 * KIB

    @classmethod
    def setUpClass(cls):
        if shutil.which("cc") is None:
            raise unittest.SkipTest("no C compiler")
        cls.lib = build_lib(cls.DIRECT)

    def setUp(self):
        self.rig = Rig(self.lib, self.SIZE, self.DIRECT)
        self.addCleanup(self.rig.close)
        self.data = blob(self.SIZE, 7)


class CheckArgs(unittest.TestCase):
    """The argument rules of the receive phase with every argument free. The aarch64 loader build is specialised to its one call site (test_nat079
    runs that build on a grid), so the comparisons that need an engine range next to the reserve are exercised here, on the host build."""
    @classmethod
    def setUpClass(cls):
        lib = ctypes.CDLL(build_lib(1))
        lib.fx_check_args.restype = ctypes.c_int
        lib.fx_check_args.argtypes = [ctypes.c_uint64] * 6
        cls.f = staticmethod(lib.fx_check_args)

    @staticmethod
    def spec(win, end, pa, n, lo, hi):
        """Whole 16 KiB pages, at least eight, inside [win, end) with no 64-bit wrap, and [lo, hi) does not intersect [pa, pa + n)."""
        if pa % PAGE or n % PAGE or n < 8 * PAGE:
            return BAD_ARGS
        if pa + n >= 1 << 64 or pa < win or pa + n > end:
            return BAD_ARGS
        if lo < pa + n and hi > pa:
            return BAD_ARGS
        return 0

    def test_an_engine_range_that_only_touches_the_reserve_is_accepted_and_one_byte_of_overlap_is_refused(self):
        pa, n = 0x100000, 8 * PAGE
        end = pa + n
        for lo, hi, want in ((end, end + 4096, 0), (end - 1, end + 4096, BAD_ARGS), (end - 1, end, BAD_ARGS), (pa - 4096, pa, 0),
                             (pa - 4096, pa + 1, BAD_ARGS), (pa, pa + 1, BAD_ARGS), (pa - 4096, end + 4096, BAD_ARGS), (0, 1, 0),
                             (end + 1, end + 2, 0)):
            self.assertEqual(self.spec(0, 1 << 40, pa, n, lo, hi), want, (hex(lo), hex(hi)))
            self.assertEqual(self.f(0, 1 << 40, pa, n, lo, hi), want, (hex(lo), hex(hi)))

    def test_the_grid_around_every_other_boundary_agrees_with_the_spec(self):
        win, end = 0x8FE400000, 0x8FE400000 + 4096 * 1024 * KIB
        lo, hi = 0x41000, 0x41000 + 76224
        seen = set()
        for pa in (win, win + PAGE, win - PAGE, win + 77 * 1024 * KIB, end - 8 * PAGE, end - 7 * PAGE, win + 1, win + 512, 0, lo):
            for n in (7 * PAGE, 8 * PAGE, 8 * PAGE + 512, 8 * PAGE + 1, 2475720704, end - win, end - win + PAGE, 0, PAGE, 2 ** 64 - 8 * PAGE):
                want = self.spec(win, end, pa, n, lo, hi)
                seen.add(want)
                self.assertEqual(self.f(win, end, pa, n, lo, hi), want, (hex(pa), hex(n)))
        self.assertEqual(seen, {0, BAD_ARGS})
        # a wrap to exactly zero is refused; the range one block lower is valid
        self.assertEqual(self.f(0, 2 ** 64 - 1, 2 ** 64 - 8 * PAGE, 8 * PAGE, lo, hi), BAD_ARGS)
        self.assertEqual(self.f(0, 2 ** 64 - 1, 2 ** 64 - 16 * PAGE, 8 * PAGE, lo, hi), 0)


class Handoff(Base):
    def test_before_the_handoff_the_capacity_is_the_placeholder_and_the_sender_refuses(self):
        raw = self.rig.rx()
        self.assertEqual(u32(raw, RX_FLAGS_AT) & (RXF_PRESENT | RXF_ENABLED), RXF_PRESENT | RXF_ENABLED)
        self.assertEqual(u64(raw, RX_CAPACITY_AT), HOLD)
        with self.assertRaises(rs.DeviceStateError):
            self.rig.send(self.data)
        self.assertEqual(self.rig.t.begins, [])
        self.assertEqual(self.rig.m.violations(), [])

    def test_the_engine_destination_is_the_reserve_only_after_the_phase(self):
        self.assertEqual(self.rig.fx.fx_rx_dest(), self.rig.base)
        self.assertEqual(self.rig.fx.fx_rx_size(), HOLD)
        seen = {}

        def host():
            seen["capacity"] = self.rig.capacity()
            seen["dest"], seen["size"] = self.rig.fx.fx_rx_dest(), self.rig.fx.fx_rx_size()
            return self.rig.send(self.data)

        r = self.rig.receive(host)
        self.assertEqual(r.status, DONE)
        self.assertEqual(seen["capacity"], self.SIZE)
        self.assertEqual((seen["dest"], seen["size"]), (self.rig.pa, self.SIZE))

    def test_a_host_that_spoke_before_the_handoff_is_reported_and_gets_no_capacity(self):
        t = self.rig.t
        t.rx_begin(0, HOLD)
        t.bulk_write(b"\x5a" * HOLD)
        self.assertEqual(self.rig.m.dest(0, HOLD), b"\x5a" * HOLD)		# it did land in the placeholder, which is why the loader must notice
        r = self.rig.receive()
        self.assertEqual(r.status, PREMATURE)
        self.assertEqual(self.rig.capacity(), HOLD)			# no handoff
        self.assertEqual(self.rig.fx.fx_rx_dest(), self.rig.base)
        with self.assertRaises(rs.DeviceStateError):
            self.rig.send(self.data)
        w = self.rig.window()
        self.assertEqual(w[self.rig.off:self.rig.off + self.SIZE], bytes([GUARD]) * self.SIZE)	# the reserve was not touched at all
        self.assertEqual(self.rig.m.violations(), [])


class Delivery(Base):
    def check_delivered(self, r, clean=True):
        rig = self.rig
        self.assertEqual(r.status, DONE)
        self.assertIsNone(rig.host_error)
        self.assertEqual((r.committed, r.rx_bytes, r.bytes), (self.SIZE, self.SIZE, self.SIZE))
        self.assertEqual(rig.m.dest(rig.off, self.SIZE), self.data)
        self.assertTrue(rig.untouched_outside_reserve())
        if clean:
            self.assertEqual(r.errors, 0)
        self.assertEqual(rig.m.violations(), [])
        self.assertEqual(rig.capacity(), self.SIZE)
        self.assertEqual(u64(rig.rx(), RX_COMMITTED_AT), self.SIZE)

    def test_the_whole_image_arrives_exactly_and_nowhere_else(self):
        r = self.rig.receive(lambda: self.rig.send(self.data))
        self.check_delivered(r)
        self.assertGreater(r.trbs, 0)
        self.assertNotEqual(r.last_sum, 0)

    def test_a_small_chunk_size_gives_the_same_bytes(self):
        r = self.rig.receive(lambda: self.rig.send(self.data, chunk=32 * KIB, write_size=16 * KIB))
        self.check_delivered(r)
        self.assertGreaterEqual(len(self.rig.t.begins), self.SIZE // (32 * KIB))

    def test_a_trb_status_error_in_a_chunk_is_retried_and_the_bytes_still_arrive(self):
        self.rig.m.bulk_fault(2)
        r = self.rig.receive(lambda: self.rig.send(self.data, chunk=64 * KIB))
        self.check_delivered(r, clean=False)
        self.assertGreater(r.errors + r.aborts + r.resets, 0)		# the fault was seen by the engine, not silently absent

    def test_a_bus_error_in_a_chunk_is_retried_and_the_bytes_still_arrive(self):
        self.rig.m.bulk_fault(1, 4096)
        r = self.rig.receive(lambda: self.rig.send(self.data, chunk=64 * KIB))
        self.check_delivered(r, clean=False)
        self.assertGreater(r.errors + r.aborts + r.resets, 0)

    def test_progress_lines_reach_the_ring_while_waiting(self):
        r = self.rig.receive(None, step=5)				# nobody sends: 5 s cap, a line every second
        self.assertEqual(r.status, TIMEOUT)
        ring = bytes(self.rig.m.ring_bytes(0, min(self.rig.m.written, self.rig.m.ring_size)))
        self.assertGreaterEqual(ring.count(b"NAT079 rx MiB=0 trbs=0 err=0 t="), 4)
        self.assertIn(b"NAT079 rx MiB=0 trbs=0 err=0 t=4s", ring)


class Ends(Base):
    def test_no_host_means_the_cap_ends_the_phase_with_nothing_committed(self):
        r = self.rig.receive(None, step=5)
        self.assertEqual(r.status, TIMEOUT)
        self.assertEqual((r.committed, r.rx_bytes, r.trbs), (0, 0, 0))
        self.assertGreaterEqual(r.elapsed_ticks, 5 * FREQ)
        self.assertLess(r.elapsed_ticks, 5 * FREQ + 2 * 5)		# it ends within one round of the cap
        self.assertEqual(r.freq, FREQ)
        self.assertEqual(self.rig.fx.fx_ticks(), self.rig.fx.fx_polls())	# one watchdog round per engine poll, nothing else
        self.assertGreaterEqual(self.rig.fx.fx_polls(), 5 * FREQ // 5)
        self.assertEqual(self.rig.capacity(), self.SIZE)		# the handoff happened: a late host may still deliver
        self.assertTrue(self.rig.untouched_outside_reserve())

    def test_half_an_image_is_a_timeout_that_says_how_much_is_in(self):
        half = self.SIZE // 2
        r = self.rig.receive(lambda: self.rig.send(self.data[:half]), step=5)
        self.assertEqual(r.status, TIMEOUT)
        self.assertIsNone(self.rig.host_error)
        self.assertEqual((r.committed, r.rx_bytes), (half, half))
        self.assertEqual(self.rig.m.dest(self.rig.off, half), self.data[:half])
        rest = self.rig.m.dest(self.rig.off + half, self.SIZE - half)
        stray = [b for b in rest if b != GUARD]
        self.assertLessEqual(len(stray), 8 * 16 * 8)			# only the zeroed words of the self-test's probe pages
        self.assertEqual(set(stray) - {0}, set())
        self.assertTrue(self.rig.untouched_outside_reserve())

    def test_the_engine_going_down_ends_the_phase(self):
        r = self.rig.receive(lambda: self.rig.fx.fx_set_up(0))
        self.assertEqual(r.status, ENGINE_DOWN)
        self.assertEqual(r.committed, 0)

    def test_a_dead_engine_at_the_start_attempts_nothing(self):
        self.rig.fx.fx_reset(1)
        self.rig.fx.fx_set_up(0)
        r = Result()
        rc = self.rig.fx.fx_receive(self.rig.pa, self.SIZE, ctypes.byref(r))
        self.assertEqual(rc, NO_ENGINE)
        self.assertEqual(self.rig.capacity(), HOLD)
        self.assertEqual(self.rig.fx.fx_polls(), 0)

    def test_bad_arguments_leave_the_placeholder(self):
        r = Result()
        for pa, n in ((self.rig.pa + 512, self.SIZE), (self.rig.pa, self.SIZE - 512), (self.rig.base - PAGE, self.SIZE),
                      (self.rig.pa, self.SIZE + 10 * PAGE), (self.rig.pa, 4 * PAGE)):
            self.rig.fx.fx_reset(1)
            self.assertEqual(self.rig.fx.fx_receive(pa, n, ctypes.byref(r)), BAD_ARGS, (pa - self.rig.base, n))
            self.assertEqual(self.rig.capacity(), HOLD)
        self.assertTrue(self.rig.untouched_outside_reserve())


class SelfTest(Base):
    def test_a_reserve_that_cannot_hold_data_keeps_rx_begin_refused(self):
        word = self.rig.pa + 24						# probe page 0 is always the first page of the reserve
        self.rig.fx.fx_reset(1)
        self.rig.fx.fx_set_stuck(word, 1 << 9)
        r = Result()
        rc = self.rig.fx.fx_receive(self.rig.pa, self.SIZE, ctypes.byref(r))
        self.assertEqual(rc, SELFTEST)
        self.assertEqual(r.selftest_bad_pa, word)
        self.assertEqual(self.rig.capacity(), HOLD)			# not handed off
        self.assertEqual(self.rig.fx.fx_rx_dest(), self.rig.base)
        with self.assertRaises(rs.DeviceStateError):
            self.rig.send(self.data)
        rc, _ = self.rig.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", 0, 2 * HOLD, 0))
        self.assertNotEqual(rc, M.H_OK)					# a hand-made RX_BEGIN past the placeholder is refused as well
        self.assertEqual(self.rig.fx.fx_polls(), 0)			# the loop never started
        w = self.rig.window()
        touched = sum(1 for b in w[self.rig.off:self.rig.off + self.SIZE] if b != GUARD)
        self.assertLessEqual(touched, 8 * 16 * 8)			# at most the self-test words of the 8 probe pages
        self.assertTrue(self.rig.untouched_outside_reserve())


class U5(Base):
    """NAT-040 item U5: the controller's DMA writes above some address are lost (S2MPU/PMMU). The model cannot say whether the S24 does that;
    these tests say what the sender and the loader report if it does."""

    def test_lost_dma_in_the_middle_is_caught_by_the_sender_and_leaves_the_loader_waiting(self):
        self.rig.m.set_dma_limit(self.rig.off + self.SIZE // 2)
        r = self.rig.receive(lambda: self.rig.send(self.data, chunk=64 * KIB), step=5)
        self.assertIsInstance(self.rig.host_error, rs.DeliveryError)	# the per-chunk checksum from the device does not match
        self.assertEqual(r.status, TIMEOUT)
        self.assertLess(r.committed, self.SIZE)
        self.assertGreater(self.rig.m.dma_blocked(), 0)
        got = self.rig.m.dest(self.rig.off, self.SIZE)
        self.assertEqual(got[:self.SIZE // 2], self.data[:self.SIZE // 2])	# what arrived before the limit is right
        self.assertNotEqual(got, self.data)

    def test_done_means_committed_not_verified(self):
        """The loader counts committed bytes; it cannot check them (it does not know the sender's checksum). A loss in the last chunk makes
        the sender fail while the loader has seen every byte committed: the sender's exit status and the in-guest hash (NAT-077) are the
        verification, and the evidence must say so."""
        self.rig.m.set_dma_limit(self.rig.off + self.SIZE - 4 * KIB)
        r = self.rig.receive(lambda: self.rig.send(self.data, chunk=64 * KIB), step=5)
        self.assertIsInstance(self.rig.host_error, rs.DeliveryError)
        self.assertEqual(r.status, DONE)
        self.assertNotEqual(self.rig.m.dest(self.rig.off, self.SIZE), self.data)


class Staged(Base):
    """The same contract with the engine's staging block (rx_direct 0): the CPU copies each chunk into the destination. Not the planned
    configuration (the loader runs with the MMU off; see README.md) but a supported build option."""
    DIRECT = 0

    def test_the_whole_image_arrives_exactly_and_nowhere_else(self):
        r = self.rig.receive(lambda: self.rig.send(self.data))
        self.assertEqual(r.status, DONE)
        self.assertIsNone(self.rig.host_error)
        self.assertEqual(self.rig.m.dest(self.rig.off, self.SIZE), self.data)
        self.assertTrue(self.rig.untouched_outside_reserve())
        self.assertEqual(self.rig.m.violations(), [])

    def test_the_capacity_reported_is_still_the_whole_reserve(self):
        seen = {}

        def host():
            raw = self.rig.rx()
            seen["capacity"], seen["chunk_max"] = u64(raw, RX_CAPACITY_AT), u32(raw, 36)

        self.rig.receive(host, step=5)
        self.assertEqual(seen["capacity"], self.SIZE)
        self.assertLessEqual(seen["chunk_max"], 64 * KIB)		# staged chunks are limited by the staging block


if __name__ == "__main__":
    unittest.main()
