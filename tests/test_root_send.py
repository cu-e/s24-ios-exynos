"""tools/ios/root_send.py against the NAT-076 DWC3 model (host-test; no phone, no USB).

The expected values come from the data that was sent, the model's own destination memory and the model's violation list,
and from numbers fixed by hand (checksum vectors, wire bytes written from usbmon.h), not from calling the sender's helpers.
ROOT_SEND_UNDER_TEST points the tests at a mutated copy of the sender (docs/procedures/nat-076/mutate_rx.py).
Needs a C compiler (`cc`); the model library is built once into $TMPDIR.
"""
import contextlib
import importlib.util
import io
import os
import random
import re
import shutil
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SENDER = Path(os.environ.get("ROOT_SEND_UNDER_TEST", ROOT / "tools/ios/root_send.py"))
MODELHOST = ROOT / "docs/procedures/nat-076/modelhost.py"

KIB = 1024
UNIT = 16 * KIB


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rs = load("root_send_under_test", SENDER)
M = None
LIB = None
BUILD_DIR = None


def setUpModule():
    global M, LIB, BUILD_DIR
    if shutil.which("cc") is None:
        raise unittest.SkipTest("no C compiler")
    M = load("nat076_modelhost", MODELHOST)
    BUILD_DIR = tempfile.mkdtemp(prefix="nat076-rs-")
    LIB = M.build(out_dir=BUILD_DIR)


def tearDownModule():
    if BUILD_DIR:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)


def blob(n, seed=1):
    return random.Random(seed).randbytes(n)


# Offsets inside struct usbmon_rx written from usbmon.h, not taken from the sender.
RX_COMMITTED_AT, RX_RXBYTES_AT, RX_ERRORS_AT, RX_ABORTS_AT = 16, 48, 60, 80


def with_field(raw, at, fmt, value):
    raw = bytearray(raw)
    struct.pack_into(fmt, raw, at, value)
    return bytes(raw)


RX_STATE_AT, RX_FLAGS_AT, RX_LAST_LEN_AT, RX_LAST_OFF_AT, RX_LAST_SUM_AT = 8, 12, 96, 104, 112
HEADER = ROOT / "docs/procedures/nat-076/engine/usbmon.h"


def raw_u64(raw, at):
    return struct.unpack_from("<Q", raw, at)[0]


def raw_u32(raw, at):
    return struct.unpack_from("<I", raw, at)[0]


class ModelTransport(rs.Transport):
    """The model machine as a Transport, with hooks for failures a USB link can show."""

    def __init__(self, m):
        self.m = m
        self.begins = []		# (offset, length) of every RX_BEGIN that was sent
        self.bulk_sizes = []
        self.aborts = 0
        self.reconnects = 0
        self.committed_seen = []	# committed offset of every GET_RX reply
        self.bulk_hook = None		# f(index, data) -> data to send, called before the model sees the write
        self.begin_hook = None		# f(index) called before each RX_BEGIN
        self.rx_filter = None		# f(call_index, raw) -> raw: a device that misreports
        self.rx_calls = 0
        self.abort_error = None		# a TransportError text: RX_ABORT fails with it
        self.reconnect_error = None	# a TransportError text: reconnect fails with it
        self.short_take = None		# f(index) -> True: bulk_write reports one byte less than the device took

    def device_rx(self):
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        assert rc == M.H_OK
        return raw

    def rx_begin(self, offset, length):
        if self.begin_hook:
            self.begin_hook(len(self.begins))
        self.begins.append((offset, length))
        rc, _ = self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", offset, length, 0))
        if rc != M.H_OK:
            raise rs.TransportError("RX_BEGIN: %s" % M.RC_NAMES.get(rc, rc))

    def rx_abort(self):
        self.aborts += 1
        if self.abort_error:
            raise rs.TransportError(self.abort_error)
        rc, _ = self.m.ctrl(0x40, 8, 0, 0, 0)
        if rc != M.H_OK:
            raise rs.TransportError("RX_ABORT: %s" % M.RC_NAMES.get(rc, rc))

    def get_rx(self):
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        if rc != M.H_OK:
            raise rs.TransportError("GET_RX: %s" % M.RC_NAMES.get(rc, rc))
        idx = self.rx_calls
        self.rx_calls += 1
        if self.rx_filter:
            raw = self.rx_filter(idx, raw)
        if len(raw) >= 24:
            self.committed_seen.append(raw_u64(raw, RX_COMMITTED_AT))
        return raw

    def bulk_write(self, data):
        idx = len(self.bulk_sizes)
        if self.bulk_hook:
            data = self.bulk_hook(idx, data)
        self.bulk_sizes.append(len(data))
        rc, took = self.m.bulk_out(data)
        if rc != M.H_OK:
            raise rs.TransportError("bulk OUT: %s after %d bytes" % (M.RC_NAMES.get(rc, rc), took))
        if self.short_take and self.short_take(idx):
            return took - 1
        return took

    def reconnect(self):
        self.reconnects += 1
        if self.reconnect_error:
            raise rs.TransportError(self.reconnect_error)
        self.m.bus_reset()
        for name, rc, _ in self.m.enumerate(address=9):
            assert rc == M.H_OK, name


class Base(unittest.TestCase):
    CAP = 1024 * KIB
    DIRECT = False

    def setUp(self):
        self.m = M.Machine(LIB, rx_size=self.CAP, rx_direct=self.DIRECT)
        self.assertEqual(self.m.init_rc, 0)
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.t = ModelTransport(self.m)
        self.logs = []

    def tearDown(self):
        self.m.close()

    def send(self, data, **kw):
        kw.setdefault("sleep", lambda s: None)
        kw.setdefault("log", self.logs.append)
        return rs.send(self.t, data, **kw)

    def write_file(self, data):
        d = tempfile.mkdtemp(prefix="rs-file-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = os.path.join(d, "root.img")
        with open(p, "wb") as f:
            f.write(data)
        return p

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(rs, "PyUsbTransport", lambda *a, **k: self.t), \
             mock.patch.object(rs.time, "sleep", lambda s: None), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rs.main(argv)
        return code, out.getvalue(), err.getvalue()

    def assert_model_clean(self):
        self.assertEqual(self.m.violations(), [])

    def device_committed(self):
        return raw_u64(self.t.device_rx(), RX_COMMITTED_AT)


class DeliveryTests(Base):
    def check_delivery(self, size, chunk, write_size):
        data = blob(size, seed=size)
        r = self.send(data, chunk=chunk, write_size=write_size)
        self.assertEqual(self.m.dest(0, size), data)
        self.assertEqual(self.device_committed(), size)
        self.assertEqual(r["committed"], size)
        self.assertEqual(r["retries"], 0)
        self.assertTrue(all(n <= write_size for n in self.t.bulk_sizes), self.t.bulk_sizes)
        self.assertEqual(sum(self.t.bulk_sizes), size)
        # the chunks are contiguous, in order, and none is longer than asked
        pos = 0
        for off, n in self.t.begins:
            self.assertEqual(off, pos)
            self.assertLessEqual(n, chunk)
            pos += n
        self.assertEqual(pos, size)
        self.assert_model_clean()

    def test_staged_small_writes_across_the_trb_ring(self):
        self.check_delivery(160 * KIB, chunk=16 * KIB, write_size=4 * KIB)

    def test_staged_default_sizes(self):
        self.check_delivery(256 * KIB, chunk=256 * KIB, write_size=64 * KIB)

    def test_one_chunk_one_write(self):
        self.check_delivery(UNIT, chunk=UNIT, write_size=UNIT)

    def test_chunk_longer_than_the_device_limit_is_cut_to_it(self):
        self.check_delivery(192 * KIB, chunk=1024 * KIB, write_size=32 * KIB)
        self.assertTrue(all(n <= 64 * KIB for _, n in self.t.begins), self.t.begins)

    def test_base_offset(self):
        data = blob(2 * UNIT, seed=5)
        self.m.dest_poke(0, b"\xA5" * UNIT)
        # the device is at offset 0 and the file belongs at 16 KiB: refused, the device cannot skip ahead
        with self.assertRaises(rs.DeviceStateError):
            self.send(data, base=UNIT, chunk=UNIT, write_size=4 * KIB)
        self.assertEqual(self.t.begins, [])
        self.assertEqual(self.m.dest(0, UNIT), b"\xA5" * UNIT)

    def test_device_count_is_reported_not_the_host_count(self):
        data = blob(3 * UNIT, seed=7)
        first = self.send(data[:UNIT], chunk=UNIT, write_size=UNIT)
        self.assertEqual(first["committed"], UNIT)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(r["resumed_from"], UNIT)
        self.assertEqual(r["bytes_written"], 2 * UNIT)		# the host only sent two thirds ...
        self.assertEqual(r["committed"], 3 * UNIT)		# ... and the device reports all of it
        self.assertEqual(self.m.dest(0, 3 * UNIT), data)

    def test_nothing_to_send_when_the_device_has_it_all(self):
        data = blob(UNIT, seed=3)
        self.send(data, chunk=UNIT, write_size=UNIT)
        self.t.begins.clear()
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.begins, [])
        self.assertEqual(r["committed"], UNIT)

    def test_no_resume_refuses_a_device_that_is_not_at_the_base(self):
        data = blob(2 * UNIT, seed=4)
        self.send(data[:UNIT], chunk=UNIT, write_size=UNIT)
        self.t.begins.clear()
        with self.assertRaises(rs.DeviceStateError):
            self.send(data, chunk=UNIT, write_size=UNIT, resume=False)
        self.assertEqual(self.t.begins, [])

    def test_device_ahead_of_the_file_end_is_refused(self):
        data = blob(3 * UNIT, seed=6)
        self.send(data, chunk=UNIT, write_size=UNIT)
        self.t.begins.clear()
        with self.assertRaises(rs.DeviceStateError):
            self.send(data[:UNIT], chunk=UNIT, write_size=UNIT)		# the device already holds more than this file
        self.assertEqual(self.t.begins, [])

    def test_a_transfer_left_armed_by_an_earlier_run_is_aborted(self):
        data = blob(2 * UNIT, seed=8)
        rc, _ = self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", 0, UNIT, 0))
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(self.m.rx_state, 1)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.aborts, 1)
        self.assertEqual(r["retries"], 0)		# aborted before the first chunk, not found out by a refused RX_BEGIN
        self.assertEqual(r["committed"], 2 * UNIT)
        self.assertEqual(self.m.dest(0, 2 * UNIT), data)
        self.assert_model_clean()

    def test_receive_path_missing_or_file_too_big_for_the_destination(self):
        self.m.close()
        self.m = M.Machine(LIB, rx_size=0)		# the engine built without a receive destination
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.t = ModelTransport(self.m)
        with self.assertRaises(rs.DeviceStateError):
            self.send(blob(UNIT), chunk=UNIT, write_size=UNIT)
        self.assertEqual((self.t.begins, self.t.bulk_sizes), ([], []))
        self.m.close()
        self.m = M.Machine(LIB, rx_size=2 * UNIT)
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.t = ModelTransport(self.m)
        with self.assertRaises(rs.DeviceStateError):
            self.send(blob(3 * UNIT), chunk=UNIT, write_size=UNIT)
        self.assertEqual((self.t.begins, self.t.bulk_sizes), ([], []))


class DirectDeliveryTests(DeliveryTests):
    DIRECT = True

    def test_chunk_longer_than_the_device_limit_is_cut_to_it(self):
        # direct mode takes up to 8 MiB per transfer: nothing is cut here
        self.check_delivery(192 * KIB, chunk=1024 * KIB, write_size=32 * KIB)
        self.assertEqual(self.t.begins, [(0, 192 * KIB)])

    def test_bytes_the_dma_silently_loses_are_not_reported_as_delivered(self):
        # S2MPU/PMMU case (NAT-040 U5): the controller's writes from window offset 24 KiB on go nowhere
        data = blob(4 * UNIT, seed=11)
        self.m.set_dma_limit(24 * KIB)
        with self.assertRaises(rs.DeliveryError) as ctx:
            self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertIn("checksum", str(ctx.exception))
        self.assertEqual(self.m.dest(0, 16 * KIB), data[:16 * KIB])		# the first chunk is intact
        self.assertNotEqual(self.m.dest(0, 4 * UNIT), data)
        self.assertEqual(len(self.t.begins), 2)				# stopped at the bad chunk: no retry, no later chunk

    def test_cli_does_not_print_success_for_lost_bytes(self):
        path = self.write_file(blob(2 * UNIT, seed=12))
        self.m.set_dma_limit(8 * KIB)
        code, out, err = self.run_cli([path, "--chunk", str(UNIT), "--write-size", str(UNIT)])
        self.assertEqual(code, 1)
        self.assertNotIn("committed=", out)
        self.assertIn("checksum", err)


class FailureTests(Base):
    def test_bus_error_mid_chunk_is_retried_from_the_committed_offset(self):
        data = blob(8 * UNIT, seed=21)
        self.m.bulk_fault(1, after=5000)
        r = self.send(data, chunk=UNIT, write_size=4 * KIB)
        self.assertGreaterEqual(r["retries"], 1)
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assertGreaterEqual(raw_u32(self.t.device_rx(), RX_ERRORS_AT), 1)
        self.assertEqual(self.device_committed(), len(data))
        self.assertEqual(self.committed_is_monotonic(), True)
        self.assert_model_clean()

    def test_trb_error_status_is_retried(self):
        data = blob(4 * UNIT, seed=22)
        self.m.bulk_fault(2, after=UNIT // 2)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertGreaterEqual(r["retries"], 1)
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assert_model_clean()

    def test_short_packet_from_the_host_is_a_failure_and_is_retried(self):
        data = blob(4 * UNIT, seed=23)
        cut = {"done": False}

        def hook(idx, d):
            if idx == 2 and not cut["done"]:
                cut["done"] = True
                return d[:-100]			# the host's last packet is short
            return d
        self.t.bulk_hook = hook
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertGreaterEqual(r["retries"], 1)
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assertEqual(self.device_committed(), len(data))

    def test_host_disconnect_mid_transfer_reconnects_and_resumes(self):
        data = blob(8 * UNIT, seed=24)
        fired = {"n": 0}

        def hook(idx, d):
            if idx == 9 and not fired["n"]:
                fired["n"] = 1
                self.m.bus_reset()		# the cable is pulled in the middle of a chunk
            return d
        self.t.bulk_hook = hook
        r = self.send(data, chunk=UNIT, write_size=4 * KIB)
        self.assertEqual(self.t.reconnects, 1)
        self.assertGreaterEqual(r["retries"], 1)
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assertEqual(self.device_committed(), len(data))
        self.assertTrue(self.committed_is_monotonic())
        self.assert_model_clean()

    def test_the_chunk_that_arrived_before_the_failure_is_not_sent_twice(self):
        data = blob(4 * UNIT, seed=25)
        state = {"n": 0}

        def rx_filter(call, raw):
            # the status read right after the first chunk is lost on the wire; the device did commit the chunk
            state["n"] += 1
            if state["n"] == 2:
                raise rs.TransportError("GET_RX timed out")
            return raw
        self.t.rx_filter = rx_filter
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(r["committed"], len(data))
        self.assertEqual(sorted(set(off for off, _ in self.t.begins)), [0, UNIT, 2 * UNIT, 3 * UNIT])
        self.assertEqual(len(self.t.begins), 4)
        self.assertEqual(self.m.dest(0, len(data)), data)

    def test_retries_are_bounded(self):
        data = blob(2 * UNIT, seed=26)
        self.t.begin_hook = lambda idx: self.m.bulk_fault(2, after=0) if idx >= 1 else None
        with self.assertRaises(rs.DeliveryError):
            self.send(data, chunk=UNIT, write_size=UNIT, max_retries=3)
        # the first chunk is delivered once, the second is tried 1 + 3 times and then given up
        self.assertEqual(len(self.t.begins), 1 + 4)
        self.assertEqual(self.device_committed(), UNIT)
        self.assertEqual(self.m.dest(0, UNIT), data[:UNIT])

    def test_retry_waits_and_waits_longer(self):
        data = blob(2 * UNIT, seed=27)
        self.t.begin_hook = lambda idx: self.m.bulk_fault(2, after=0) if idx >= 1 else None
        naps = []
        with self.assertRaises(rs.DeliveryError):
            self.send(data, chunk=UNIT, write_size=UNIT, max_retries=3, backoff=0.5, sleep=naps.append)
        self.assertEqual(naps, [0.5, 1.0, 1.5])

    def test_device_that_restarted_is_detected(self):
        data = blob(4 * UNIT, seed=28)
        state = {"restarted": False}

        def begin_hook(idx):
            if idx == 1:				# the second chunk fails, and from then on the device answers as if it had just booted
                self.m.bulk_fault(2, after=0)
                state["restarted"] = True

        def rx_filter(call, raw):
            if state["restarted"]:
                raw = bytearray(raw)
                struct.pack_into("<Q", raw, RX_COMMITTED_AT, 0)
                return bytes(raw)
            return raw
        self.t.begin_hook = begin_hook
        self.t.rx_filter = rx_filter
        with self.assertRaisesRegex(rs.DeviceStateError, r"went back from %d to 0.*restarted" % UNIT):
            self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(len(self.t.begins), 2)		# nothing is sent after the restart was seen

    def test_final_count_is_checked_against_the_device(self):
        data = blob(2 * UNIT, seed=29)
        calls = {"n": 0}

        def rx_filter(call, raw):
            calls["n"] += 1
            return raw
        self.t.rx_filter = rx_filter
        # run once to see how many GET_RX calls a clean transfer makes, then make only the last one lie
        self.send(data, chunk=UNIT, write_size=UNIT)
        total = calls["n"]
        self.m.close()
        self.setUp()
        self.t.rx_filter = lambda call, raw: self.lie(raw) if call == total - 1 else raw
        with self.assertRaises(rs.DeliveryError):
            self.send(data, chunk=UNIT, write_size=UNIT)

    @staticmethod
    def lie(raw):
        raw = bytearray(raw)
        struct.pack_into("<Q", raw, RX_COMMITTED_AT, struct.unpack_from("<Q", raw, RX_COMMITTED_AT)[0] - UNIT)
        return bytes(raw)

    def committed_is_monotonic(self):
        seen = self.t.committed_seen
        return all(b >= a for a, b in zip(seen, seen[1:]))


class SizeRuleTests(unittest.TestCase):
    class Mute(rs.Transport):
        def __init__(self):
            self.calls = []

        def __getattribute__(self, name):
            if name in ("rx_begin", "rx_abort", "get_rx", "bulk_write", "reconnect"):
                raise AssertionError("the sender touched the device (%s) for a refused file" % name)
            return super().__getattribute__(name)

    def test_sizes_that_are_not_a_multiple_of_16_kib_are_refused_before_any_io(self):
        for size in (1, 512, 4096, UNIT - 1, UNIT + 1, UNIT + 4096, 3 * UNIT + 512, 0):
            with self.subTest(size=size):
                with self.assertRaises(rs.SizeError):
                    rs.send(self.Mute(), bytes(size))

    def test_bad_base_chunk_and_write_size_are_refused_before_any_io(self):
        data = bytes(UNIT)
        for kw in ({"base": 4096}, {"base": -UNIT}, {"chunk": 0}, {"chunk": 1000}, {"write_size": 0}, {"write_size": 100}):
            with self.subTest(**kw):
                with self.assertRaisesRegex(rs.SizeError, "base offset %d|multiples of 512" % kw.get("base", 0)):
                    rs.send(self.Mute(), data, **kw)

    def test_cli_refuses_such_a_file_without_opening_the_device(self):
        d = tempfile.mkdtemp(prefix="rs-size-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        for size in (20000, UNIT * 2 + 1):
            p = os.path.join(d, "f%d" % size)
            with open(p, "wb") as f:
                f.write(bytes(size))
            opened = []
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(rs, "PyUsbTransport", lambda *a, **k: opened.append(1)), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = rs.main([p])
            self.assertEqual(code, 2, size)
            self.assertEqual(opened, [], size)
            self.assertIn("16 KiB", err.getvalue())
            self.assertEqual(out.getvalue(), "")

    def test_cli_check_only_accepts_a_good_size_without_opening_the_device(self):
        d = tempfile.mkdtemp(prefix="rs-size-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = os.path.join(d, "ok")
        with open(p, "wb") as f:
            f.write(bytes(3 * UNIT))
        opened = []
        out = io.StringIO()
        with mock.patch.object(rs, "PyUsbTransport", lambda *a, **k: opened.append(1)), contextlib.redirect_stdout(out):
            code = rs.main([p, "--check-only"])
        self.assertEqual((code, opened), (0, []))
        self.assertEqual(out.getvalue(), "size %d is a multiple of 16 KiB\n" % (3 * UNIT))


class CliOutputTests(Base):
    def test_cli_prints_the_count_the_device_reports(self):
        data = blob(3 * UNIT, seed=31)
        self.send(data[:UNIT], chunk=UNIT, write_size=UNIT)		# an earlier run left one unit on the device
        code, out, err = self.run_cli([self.write_file(data), "--chunk", str(UNIT), "--write-size", str(UNIT)])
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"^device reports committed=%d " % (3 * UNIT))
        self.assertRegex(out, r"rx_bytes=%d " % (3 * UNIT))
        self.assertRegex(out, r"%d bytes written" % (2 * UNIT))
        self.assertEqual(self.m.dest(0, 3 * UNIT), data)

    def test_cli_fails_when_the_device_count_is_short(self):
        data = blob(2 * UNIT, seed=32)
        # lie in the final status only: count GET_RX calls of a clean run first
        calls = []
        self.t.rx_filter = lambda call, raw: (calls.append(call), raw)[1]
        self.run_cli([self.write_file(data), "--chunk", str(UNIT), "--write-size", str(UNIT)])
        last = calls[-1]
        self.m.close()
        self.setUp()
        self.t.rx_filter = lambda call, raw: FailureTests.lie(raw) if call == last else raw
        code, out, err = self.run_cli([self.write_file(data), "--chunk", str(UNIT), "--write-size", str(UNIT)])
        self.assertEqual(code, 1)
        self.assertNotIn("committed=", out)
        self.assertIn("committed", err)

    def test_cli_reports_a_missing_device_as_a_failure(self):
        def boom(*a, **k):
            raise rs.TransportError("no USB device 1209:0001")
        d = tempfile.mkdtemp(prefix="rs-file-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = os.path.join(d, "r")
        with open(p, "wb") as f:
            f.write(bytes(UNIT))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(rs, "PyUsbTransport", boom), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rs.main([p])
        self.assertEqual(code, 1)
        self.assertIn("no USB device", err.getvalue())
        self.assertEqual(out.getvalue(), "")


def script(raise_at=(), alter=None, raise_text="GET_RX timed out", from_call=None):
    """A GET_RX filter: raise TransportError at the given call indexes; alter(call, raw) -> raw for the others."""
    def f(call, raw):
        if call in raise_at or (from_call is not None and call >= from_call and raise_text is not None and alter is None):
            raise rs.TransportError(raise_text)
        return alter(call, raw) if alter else raw
    return f


class LayoutTests(Base):
    def test_file_that_is_not_a_multiple_of_the_chunk(self):
        data = blob(5 * UNIT, seed=51)
        r = self.send(data, chunk=2 * UNIT, write_size=8 * KIB)
        self.assertEqual(self.t.begins, [(0, 2 * UNIT), (2 * UNIT, 2 * UNIT), (4 * UNIT, UNIT)])
        self.assertEqual((r["chunks"], r["bytes_written"], r["committed"]), (3, 5 * UNIT, 5 * UNIT))
        self.assertEqual(self.m.dest(0, 5 * UNIT), data)
        self.assertTrue(all(n <= 8 * KIB for n in self.t.bulk_sizes))

    def test_second_file_goes_to_the_offset_the_first_one_ended_at(self):
        a, b = blob(3 * UNIT, seed=52), blob(3 * UNIT, seed=53)
        self.send(a, chunk=UNIT, write_size=UNIT)
        self.t.begins.clear()
        r = self.send(b, base=3 * UNIT, chunk=2 * UNIT, write_size=8 * KIB)
        self.assertEqual(self.t.begins, [(3 * UNIT, 2 * UNIT), (5 * UNIT, UNIT)])
        self.assertEqual((r["start_offset"], r["end_offset"], r["resumed_from"], r["committed"]), (3 * UNIT, 6 * UNIT, 3 * UNIT, 6 * UNIT))
        self.assertEqual(self.m.dest(0, 6 * UNIT), a + b)

    def test_resume_in_the_middle_of_a_file_that_has_a_base(self):
        f = blob(3 * UNIT, seed=54)
        self.send(blob(UNIT, seed=55), chunk=UNIT, write_size=UNIT)		# 0..U belongs to something else
        self.send(f[:UNIT], base=UNIT, chunk=UNIT, write_size=UNIT)		# the first third of f went in; then the run died
        self.t.begins.clear()
        r = self.send(f, base=UNIT, chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.begins, [(2 * UNIT, UNIT), (3 * UNIT, UNIT)])
        self.assertEqual((r["resumed_from"], r["bytes_written"], r["committed"]), (2 * UNIT, 2 * UNIT, 4 * UNIT))
        self.assertEqual(self.m.dest(UNIT, 3 * UNIT), f)

    def test_summary_numbers(self):
        data = blob(3 * UNIT, seed=56)
        times = iter([100.0, 104.25])
        r = self.send(data, chunk=UNIT, write_size=UNIT, clock=lambda: next(times))
        self.assertEqual((r["chunks"], r["retries"], r["bytes_written"], r["seconds"]), (3, 0, 3 * UNIT, 4.25))
        self.assertEqual((r["start_offset"], r["end_offset"], r["resumed_from"], r["committed"]), (0, 3 * UNIT, 0, 3 * UNIT))
        self.assertEqual((r["rx_bytes"], r["rx_errors"]), (3 * UNIT, 0))
        self.assertGreaterEqual(r["rx_trbs"], 3)

    def test_a_file_that_ends_exactly_at_the_destination_size_is_accepted(self):
        data = blob(self.CAP, seed=57)
        r = self.send(data, chunk=64 * KIB, write_size=64 * KIB)
        self.assertEqual(r["committed"], self.CAP)
        self.assertEqual(self.m.dest(0, self.CAP), data)

    def test_flags_must_show_a_present_and_enabled_receive_path(self):
        for flags, ok in ((0, False), (1, False), (2, False), (3, True), (7, True)):
            with self.subTest(flags=flags):
                self.m.close()
                self.setUp()
                self.t.rx_filter = lambda call, raw, fl=flags: with_field(raw, RX_FLAGS_AT, "<I", fl)
                if ok:
                    self.assertEqual(self.send(blob(UNIT), chunk=UNIT, write_size=UNIT)["committed"], UNIT)
                else:
                    with self.assertRaisesRegex(rs.DeviceStateError, r"not enabled \(flags %#x\)" % flags):
                        self.send(blob(UNIT), chunk=UNIT, write_size=UNIT)
                    self.assertEqual(self.t.begins, [])


class ConstantsMatchTheDeviceHeader(unittest.TestCase):
    """The numbers the sender uses are the ones usbmon.h defines (the header is the specification)."""

    @staticmethod
    def defines():
        out = {}
        text = HEADER.read_text()
        for m in re.finditer(r"^#define\s+(USBMON_\w+)\s+(?:BIT\((\d+)\)|(0[xX][0-9a-fA-F]+|\d+)u?\b)", text, re.M):
            out[m.group(1)] = 1 << int(m.group(2)) if m.group(2) else int(m.group(3), 0)
        return out

    def test_requests_states_and_flags(self):
        d = self.defines()
        for name, got in (("USBMON_REQ_RX_BEGIN", rs.REQ_RX_BEGIN), ("USBMON_REQ_GET_RX", rs.REQ_GET_RX),
                          ("USBMON_REQ_RX_ABORT", rs.REQ_RX_ABORT), ("USBMON_RX_IDLE", rs.RX_IDLE),
                          ("USBMON_RX_ARMED", rs.RX_ARMED), ("USBMON_RX_FAILED", rs.RX_FAILED),
                          ("USBMON_RXF_PRESENT", rs.RXF_PRESENT), ("USBMON_RXF_ENABLED", rs.RXF_ENABLED),
                          ("USBMON_RXF_DIRECT", rs.RXF_DIRECT)):
            with self.subTest(name):
                self.assertIn(name, d)
                self.assertEqual(got, d[name])


class BaseTransportTests(unittest.TestCase):
    def test_an_incomplete_transport_fails_loudly(self):
        t = rs.Transport()
        for call in (lambda: t.rx_begin(0, 1), t.rx_abort, t.get_rx, lambda: t.bulk_write(b"")):
            with self.assertRaises(NotImplementedError):
                call()
        self.assertIsNone(t.reconnect())


class PollingTests(Base):
    def armed_until(self, polls):
        """A device that reports 'still armed, nothing committed yet' for its first `polls` status reads after the first RX_BEGIN."""
        seen = {"n": 0}

        def f(call, raw):
            if self.t.begins and seen["n"] < polls:
                seen["n"] += 1
                raw = with_field(raw, RX_STATE_AT, "<I", 1)
                return with_field(raw, RX_COMMITTED_AT, "<Q", 0)
            return raw
        return f

    def test_a_chunk_that_is_still_arriving_is_waited_for(self):
        data = blob(UNIT, seed=61)
        self.t.rx_filter = self.armed_until(3)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(r["retries"], 0)
        self.assertEqual(self.t.rx_calls, 1 + 4 + 1)		# start, 3 polls that show ARMED + 1 that does not, final
        self.assertEqual(self.m.dest(0, UNIT), data)

    def test_poll_limit_is_honoured_and_a_stuck_chunk_is_a_failure(self):
        self.t.rx_filter = self.armed_until(10 ** 6)
        with self.assertRaisesRegex(rs.DeliveryError, r"failed 1 times: the chunk at 0 stayed armed after 7 polls"):
            self.send(blob(UNIT, seed=62), chunk=UNIT, write_size=UNIT, poll_limit=7, max_retries=0)
        self.assertEqual(self.t.rx_calls, 1 + 7)

    def test_state_failed_is_a_failure_even_when_the_count_is_right(self):
        data = blob(2 * UNIT, seed=63)
        self.t.rx_filter = script(alter=lambda c, raw: with_field(raw, RX_STATE_AT, "<I", 2) if c == 1 else raw)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(r["retries"], 1)
        self.assertEqual(self.t.begins, [(0, UNIT), (UNIT, UNIT)])		# the chunk had arrived: it is not sent again
        self.assertEqual(self.m.dest(0, 2 * UNIT), data)

    def test_a_short_count_with_an_idle_state_is_a_failure(self):
        data = blob(2 * UNIT, seed=64)
        self.t.rx_filter = script(alter=lambda c, raw: with_field(raw, RX_COMMITTED_AT, "<Q", 0) if c == 1 else raw)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(r["retries"], 1)
        self.assertEqual(len(self.t.begins), 2)
        self.assertTrue(any("state 0 committed 0 after the chunk at 0 (expected %d)" % UNIT in m for m in self.logs), self.logs)

    def test_each_of_the_chunk_checks_alone_is_fatal(self):
        for name, at, fmt in (("last_off", RX_LAST_OFF_AT, "<Q"), ("last_len", RX_LAST_LEN_AT, "<I"), ("last_sum", RX_LAST_SUM_AT, "<Q")):
            with self.subTest(name):
                self.m.close()
                self.setUp()
                self.t.rx_filter = script(alter=lambda c, raw, at=at, fmt=fmt: with_field(
                    raw, at, fmt, struct.unpack_from(fmt, raw, at)[0] ^ 1) if c == 1 else raw)
                with self.assertRaisesRegex(rs.DeliveryError, "different checksum"):
                    self.send(blob(2 * UNIT, seed=65), chunk=UNIT, write_size=UNIT)
                self.assertEqual(len(self.t.begins), 1)

    def test_a_short_acknowledgement_of_a_write_is_a_failure_but_the_chunk_is_not_sent_twice(self):
        data = blob(2 * UNIT, seed=66)
        self.t.short_take = lambda idx: idx == 0
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual(r["retries"], 1)
        self.assertEqual(self.t.begins, [(0, UNIT), (UNIT, UNIT)])
        self.assertTrue(any("short bulk write: device took %d of %d bytes" % (UNIT - 1, UNIT) in m for m in self.logs), self.logs)
        self.assertEqual(self.m.dest(0, 2 * UNIT), data)


class RecoveryTests(Base):
    """What the sender does after a failure, decided from what the device says (call indexes: 0 is the status read at the start,
    then one per poll, one per recovery read, one at the end)."""

    def test_chunk_arrived_but_what_the_device_says_now_does_not_match_the_chunk(self):
        for name, at, fmt in (("last_off", RX_LAST_OFF_AT, "<Q"), ("last_len", RX_LAST_LEN_AT, "<I"), ("last_sum", RX_LAST_SUM_AT, "<Q")):
            with self.subTest(name):
                self.m.close()
                self.setUp()
                self.t.rx_filter = script(raise_at=(1,), alter=lambda c, raw, at=at, fmt=fmt: with_field(
                    raw, at, fmt, struct.unpack_from(fmt, raw, at)[0] ^ 1) if c == 2 else raw)
                with self.assertRaisesRegex(rs.DeviceStateError, r"device committed %d while the host was at 0: the stream is out of step" % UNIT):
                    self.send(blob(2 * UNIT, seed=71), chunk=UNIT, write_size=UNIT)

    def test_a_count_between_the_chunk_start_and_end_is_out_of_step(self):
        self.t.rx_filter = script(raise_at=(1,), alter=lambda c, raw: with_field(raw, RX_COMMITTED_AT, "<Q", 8 * KIB) if c == 2 else raw)
        with self.assertRaisesRegex(rs.DeviceStateError, r"device committed 8192 while the host was at 0"):
            self.send(blob(2 * UNIT, seed=72), chunk=UNIT, write_size=UNIT)
        self.assertEqual(len(self.t.begins), 1)

    def test_a_count_below_what_was_already_committed_is_a_restart_even_above_the_start(self):
        # three chunks; the recovery read after the third chunk says 1 unit, the host had committed 2: back by one chunk
        self.t.rx_filter = script(raise_at=(3,), alter=lambda c, raw: with_field(raw, RX_COMMITTED_AT, "<Q", UNIT) if c == 4 else raw)
        with self.assertRaisesRegex(rs.DeviceStateError, r"went back from %d to %d" % (2 * UNIT, UNIT)):
            self.send(blob(3 * UNIT, seed=73), chunk=UNIT, write_size=UNIT)

    def test_status_read_that_fails_after_a_failure_reconnects_and_goes_on(self):
        data = blob(2 * UNIT, seed=74)
        self.t.rx_filter = script(raise_at=(1, 2))
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual((self.t.reconnects, r["retries"]), (1, 1))
        self.assertTrue(any("reconnecting: GET_RX failed: GET_RX timed out" in m for m in self.logs), self.logs)
        self.assertEqual(self.m.dest(0, 2 * UNIT), data)
        self.assertEqual(len(self.t.begins), 2)

    def test_receive_path_that_is_not_enabled_after_a_failure_reconnects_and_goes_on(self):
        data = blob(2 * UNIT, seed=75)
        self.t.rx_filter = script(raise_at=(1,), alter=lambda c, raw: with_field(raw, RX_FLAGS_AT, "<I", 1) if c == 2 else raw)
        r = self.send(data, chunk=UNIT, write_size=UNIT)
        self.assertEqual((self.t.reconnects, r["retries"]), (1, 1))
        self.assertTrue(any("reconnecting: the receive path is not enabled (flags 0x1)" in m for m in self.logs), self.logs)
        self.assertEqual(self.m.dest(0, 2 * UNIT), data)

    def test_a_device_that_is_still_not_enabled_after_the_reconnect_is_given_up(self):
        self.t.rx_filter = script(raise_at=(1,), alter=lambda c, raw: with_field(raw, RX_FLAGS_AT, "<I", 1) if c >= 2 else raw)
        with self.assertRaisesRegex(rs.DeliveryError, r"device unusable after a reconnect: the receive path is not enabled \(flags 0x1\)"):
            self.send(blob(2 * UNIT, seed=76), chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.reconnects, 1)

    def test_a_device_that_does_not_answer_after_the_reconnect_is_given_up(self):
        self.t.rx_filter = script(raise_at=(1,), from_call=2, raise_text="gone")
        with self.assertRaisesRegex(rs.DeliveryError, r"device unusable after a reconnect: GET_RX failed: gone"):
            self.send(blob(2 * UNIT, seed=77), chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.reconnects, 1)

    def test_a_reconnect_that_fails_is_reported_as_such(self):
        self.t.reconnect_error = "no cable"
        self.t.rx_filter = script(raise_at=(1, 2))
        with self.assertRaisesRegex(rs.DeliveryError, "could not reconnect: no cable"):
            self.send(blob(2 * UNIT, seed=78), chunk=UNIT, write_size=UNIT)

    def armed_after_two_writes(self):
        """The first write of a two-write chunk goes through, the second fails on the host: the device is left ARMED."""
        fired = []

        def hook(idx, d):
            if idx == 1 and not fired:
                fired.append(1)
                raise rs.TransportError("host side timeout")
            return d
        self.t.bulk_hook = hook

    def test_an_armed_transfer_left_by_a_failure_is_aborted_and_the_chunk_is_sent_again(self):
        data = blob(2 * UNIT, seed=79)
        self.armed_after_two_writes()
        r = self.send(data, chunk=2 * UNIT, write_size=UNIT)
        self.assertEqual((self.t.aborts, r["retries"]), (1, 1))
        self.assertEqual(self.t.begins, [(0, 2 * UNIT), (0, 2 * UNIT)])
        self.assertEqual(self.m.dest(0, 2 * UNIT), data)
        self.assert_model_clean()

    def test_an_abort_that_fails_is_reported_in_both_places(self):
        self.armed_after_two_writes()
        self.t.abort_error = "stuck"
        with self.assertRaisesRegex(rs.DeliveryError, r"could not abort the armed transfer at 0: stuck"):
            self.send(blob(2 * UNIT, seed=80), chunk=2 * UNIT, write_size=UNIT)
        # at the start: a transfer left armed by an earlier run
        self.m.close()
        self.setUp()
        self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", 0, UNIT, 0))
        self.t.abort_error = "boom"
        with self.assertRaisesRegex(rs.DeviceStateError, r"could not end the transfer a previous run left armed: boom"):
            self.send(blob(UNIT, seed=81), chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.begins, [])

    def test_an_abort_that_does_not_take_effect_is_not_taken_for_one_that_did(self):
        self.armed_after_two_writes()
        self.t.rx_filter = script(alter=lambda c, raw: with_field(raw, RX_STATE_AT, "<I", 1) if c >= 2 else raw)
        with self.assertRaisesRegex(rs.DeliveryError, r"could not abort the armed transfer at 0: .*still armed after RX_ABORT"):
            self.send(blob(2 * UNIT, seed=82), chunk=2 * UNIT, write_size=UNIT)
        self.m.close()
        self.setUp()
        self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", 0, UNIT, 0))
        self.t.rx_filter = script(alter=lambda c, raw: with_field(raw, RX_STATE_AT, "<I", 1))
        with self.assertRaisesRegex(rs.DeviceStateError, r"left armed: the transfer is still armed after RX_ABORT"):
            self.send(blob(UNIT, seed=83), chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.begins, [])

    def test_the_final_status_read_failing_is_a_delivery_error(self):
        data = blob(2 * UNIT, seed=84)
        n = []
        self.t.rx_filter = lambda call, raw: (n.append(call), raw)[1]
        self.send(data, chunk=UNIT, write_size=UNIT)
        last = n[-1]
        self.m.close()
        self.setUp()
        self.t.rx_filter = script(raise_at=(last,))
        with self.assertRaisesRegex(rs.DeliveryError, "did not answer the final GET_RX: GET_RX timed out"):
            self.send(data, chunk=UNIT, write_size=UNIT)

    def test_a_device_that_does_not_answer_at_the_start_is_not_a_receive_engine(self):
        self.t.rx_filter = script(raise_at=(0,))
        with self.assertRaisesRegex(rs.DeviceStateError, "does not answer GET_RX"):
            self.send(blob(UNIT), chunk=UNIT, write_size=UNIT)
        self.assertEqual(self.t.begins, [])


class DefaultsTests(Base):
    """The defaults the README and --help state: 256 KiB chunks, 64 KiB writes, 5 retries, 2000 polls, 0.05 s back-off."""
    CAP = 2048 * KIB
    DIRECT = True			# the staged engine would cut a chunk to 64 KiB and hide the default

    def test_default_chunk_and_write_size(self):
        data = blob(512 * KIB, seed=91)
        rs.send(self.t, data, sleep=lambda s: None)		# no log, no clock: the defaults are used
        self.assertEqual(self.t.begins, [(0, 256 * KIB), (256 * KIB, 256 * KIB)])
        self.assertEqual(self.t.bulk_sizes, [64 * KIB] * 8)
        self.assertEqual(self.m.dest(0, 512 * KIB), data)

    def test_default_retries_and_backoff(self):
        naps = []
        self.t.begin_hook = lambda idx: self.m.bulk_fault(2, after=0)
        with mock.patch.object(rs.time, "sleep", naps.append), self.assertRaisesRegex(rs.DeliveryError, r"chunk at 0 failed 6 times"):
            rs.send(self.t, blob(UNIT, seed=92), chunk=UNIT, write_size=UNIT)
        self.assertEqual(len(self.t.begins), 6)
        self.assertEqual(len(naps), 5)
        for got, want in zip(naps, (0.05, 0.10, 0.15, 0.20, 0.25)):
            self.assertAlmostEqual(got, want)

    def test_default_poll_limit(self):
        self.t.rx_filter = lambda call, raw: with_field(raw, RX_STATE_AT, "<I", 1) if self.t.begins else raw
        with self.assertRaisesRegex(rs.DeliveryError, "stayed armed after 2000 polls"):
            rs.send(self.t, blob(UNIT, seed=93), chunk=UNIT, write_size=UNIT, max_retries=0, sleep=lambda s: None)
        self.assertEqual(self.t.rx_calls, 1 + 2000)


class CliOptionTests(Base):
    CAP = 2048 * KIB
    DIRECT = True

    def run_spied(self, argv):
        seen = {}
        real_send = rs.send

        def transport(*a, **k):
            seen["transport"] = (a, k)
            return self.t

        def spy(t, data, **kw):
            seen["send"] = kw
            return real_send(t, data, **kw)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(rs, "PyUsbTransport", transport), mock.patch.object(rs, "send", spy), \
             mock.patch.object(rs.time, "sleep", lambda s: None), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rs.main(argv)
        return code, seen, out.getvalue(), err.getvalue()

    def test_defaults(self):
        code, seen, out, err = self.run_spied([self.write_file(blob(UNIT, seed=94))])
        self.assertEqual(code, 0, err)
        self.assertEqual(seen["transport"], ((0x1209, 0x0001, None, None, 5000), {}))
        kw = dict(seen["send"])
        self.assertTrue(callable(kw.pop("log")))
        self.assertEqual(kw, dict(base=0, chunk=262144, write_size=65536, max_retries=5, resume=True))

    def test_every_option_reaches_the_transport_or_the_sender(self):
        self.send(blob(UNIT, seed=95), chunk=UNIT, write_size=UNIT)		# the device is at 16 KiB
        code, seen, out, err = self.run_spied([self.write_file(blob(UNIT, seed=96)), "--vid", "0x1234", "--pid", "5678", "--bus", "2",
                                               "--address", "7", "--timeout-ms", "777", "--base", str(UNIT), "--chunk", "8192",
                                               "--write-size", "4096", "--max-retries", "2", "--no-resume"])
        self.assertEqual(code, 0, err)
        self.assertEqual(seen["transport"], ((0x1234, 5678, 2, 7, 777), {}))
        kw = dict(seen["send"])
        kw.pop("log")
        self.assertEqual(kw, dict(base=UNIT, chunk=8192, write_size=4096, max_retries=2, resume=False))

    def test_help_names_the_tool(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            rs.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("usage:", out.getvalue())
        self.assertIn("bulk-OUT receive engine", out.getvalue())


class ChecksumTests(unittest.TestCase):
    VECTORS = [
        (b"", 0),
        (struct.pack("<Q", 1), 1),
        (struct.pack("<QQ", 1, 2), 1 * 1 + 2 * 3),
        (struct.pack("<QQQ", 5, 0, 7), 5 * 1 + 7 * 5),
        (struct.pack("<QQ", 0, 1 << 63), (1 << 63) * 3 % (1 << 64)),		# wraps modulo 2**64
        (struct.pack("<QQ", (1 << 64) - 1, 0), (1 << 64) - 1),
        (bytes([1, 2, 3, 4, 5, 6, 7, 8]), 0x0807060504030201),		# little endian words
    ]

    def test_hand_computed_vectors(self):
        for data, want in self.VECTORS:
            with self.subTest(data=data.hex()):
                self.assertEqual(rs.chunk_sum(data), want)

    def test_without_numpy_gives_the_same_numbers(self):
        data = blob(4096, seed=41)
        with_np = rs.chunk_sum(data)
        with mock.patch.dict(sys.modules, {"numpy": None}):
            without = rs.chunk_sum(data)
            self.assertEqual([rs.chunk_sum(d) for d, _ in self.VECTORS], [w for _, w in self.VECTORS])
        self.assertEqual(with_np, without)

    def test_input_that_is_not_a_whole_number_of_words_is_rejected(self):
        for blocked in (False, True):
            with self.subTest(numpy_blocked=blocked):
                with mock.patch.dict(sys.modules, {"numpy": None} if blocked else {}):
                    for n in (3, 4, 12, 20):
                        with self.assertRaisesRegex(ValueError, "multiple of 8"):
                            rs.chunk_sum(bytes(n))

    def test_order_and_position_matter(self):
        a = struct.pack("<QQ", 1, 2)
        b = struct.pack("<QQ", 2, 1)
        self.assertNotEqual(rs.chunk_sum(a), rs.chunk_sum(b))


class ParseTests(unittest.TestCase):
    def good(self):
        return bytes(b"S24R" + struct.pack("<HH", 1, 120) + bytes(112))

    def test_a_good_reply_parses(self):
        r = rs.parse_rx(self.good())
        self.assertEqual((r["version"], r["size"], r["committed"]), (1, 120, 0))

    def test_bad_replies_are_refused(self):
        g = self.good()
        for name, raw in (("short", g[:119]), ("magic", b"S24L" + g[4:]), ("version", g[:4] + struct.pack("<H", 2) + g[6:]),
                          ("size", g[:6] + struct.pack("<H", 112) + g[8:]), ("empty", b"")):
            with self.subTest(name):
                with self.assertRaises(rs.DeviceStateError):
                    rs.parse_rx(raw)

    def test_field_positions(self):
        raw = bytearray(self.good())
        struct.pack_into("<I", raw, 8, 2)			# state
        struct.pack_into("<I", raw, 12, 3)			# flags
        struct.pack_into("<Q", raw, 16, 0x1122334455667788)	# committed
        struct.pack_into("<Q", raw, 104, 99)			# last_off
        struct.pack_into("<Q", raw, 112, 0xAABBCCDDEEFF0011)	# last_sum
        r = rs.parse_rx(bytes(raw))
        self.assertEqual((r["state"], r["flags"], r["committed"], r["last_off"], r["last_sum"]),
                         (2, 3, 0x1122334455667788, 99, 0xAABBCCDDEEFF0011))


class PyUsbTransportTests(unittest.TestCase):
    """The wire bytes of the real transport, with a stand-in for usb.core (usbmon.h is the specification)."""

    class FakeDev:
        def __init__(self):
            self.log = []
            self.fail = None

        def set_configuration(self, n):
            self.log.append(("set_configuration", n))

        def reset(self):
            self.log.append(("reset",))

        def ctrl_transfer(self, bm, req, value, index, data_or_len, timeout):
            if self.fail:
                raise self.fail
            self.log.append(("ctrl", bm, req, value, index, data_or_len, timeout))
            return bytes(range(120)) if bm == 0xC0 else 0

        def write(self, ep, data, timeout):
            if self.fail:
                raise self.fail
            self.log.append(("write", ep, bytes(data), timeout))
            return len(data)

    DEFAULT = object()

    def make(self, timeout_ms=1234, devices=((1, 3),), **kw):
        dev = self.FakeDev()
        usb = types.ModuleType("usb")
        core = types.ModuleType("usb.core")
        core.calls = []

        def mock_dev(bus, address):
            return mock.Mock(bus=bus, address=address, **{
                "set_configuration": dev.set_configuration, "ctrl_transfer": dev.ctrl_transfer, "write": dev.write,
                "reset": dev.reset})

        def find(find_all=False, idVendor=None, idProduct=None):
            core.calls.append((find_all, idVendor, idProduct))
            return [mock_dev(b, a) for b, a in core.devices]
        core.devices = list(devices)
        core.find = find
        core.mock_dev = mock_dev
        usb.core = core
        if timeout_ms is not self.DEFAULT:
            kw["timeout_ms"] = timeout_ms
        with mock.patch.dict(sys.modules, {"usb": usb, "usb.core": core}):
            t = rs.PyUsbTransport(**kw)
        return t, dev

    def test_wire_format(self):
        t, dev = self.make()
        t.rx_begin(0x0102030405060708, 16384)
        t.rx_abort()
        raw = t.get_rx()
        n = t.bulk_write(b"abc")
        self.assertEqual(dev.log, [
            ("set_configuration", 1),
            ("ctrl", 0x40, 0x06, 0, 0, struct.pack("<QII", 0x0102030405060708, 16384, 0), 1234),
            ("ctrl", 0x40, 0x08, 0, 0, None, 1234),
            ("ctrl", 0xC0, 0x07, 0, 0, 120, 1234),
            ("write", 0x01, b"abc", 1234),
        ])
        self.assertEqual((raw, n), (bytes(range(120)), 3))

    def test_reconnect_resets_the_port_then_configures_again_and_forgets_the_old_address(self):
        t, dev = self.make(address=3)
        dev.log.clear()
        with mock.patch.dict(sys.modules, {"usb": sys.modules.get("usb"), "usb.core": t.usb}):
            t.reconnect()
        self.assertEqual(dev.log, [("reset",), ("set_configuration", 1)])
        self.assertIsNone(t.address)

    def test_no_set_configuration_when_not_asked(self):
        t, dev = self.make(configure=False)
        self.assertEqual(dev.log, [])

    def test_usb_errors_become_transport_errors(self):
        t, dev = self.make()
        dev.fail = OSError("pipe error")
        for call in (lambda: t.rx_begin(0, 16384), t.rx_abort, t.get_rx, lambda: t.bulk_write(b"x")):
            with self.assertRaisesRegex(rs.TransportError, "OSError: pipe error"):
                call()

    def test_default_timeout_is_five_seconds(self):
        t, dev = self.make(timeout_ms=self.DEFAULT)
        t.rx_abort()
        self.assertEqual(dev.log[-1][-1], 5000)

    def test_the_device_is_looked_up_by_vendor_and_product(self):
        t, dev = self.make()
        self.assertEqual(t.usb.calls, [(True, 0x1209, 0x0001)])
        t, dev = self.make(vid=0x1234, pid=0xABCD)
        self.assertEqual(t.usb.calls, [(True, 0x1234, 0xABCD)])

    def test_no_device(self):
        with self.assertRaisesRegex(rs.TransportError, r"^no USB device 1209:0001$"):
            self.make(devices=())
        with self.assertRaisesRegex(rs.TransportError, r"^no USB device 1234:00ab$"):
            self.make(devices=(), vid=0x1234, pid=0xAB)

    def test_two_matching_devices_are_ambiguous(self):
        with self.assertRaisesRegex(rs.TransportError, r"^2 devices match 1209:0001; pass --bus/--address$"):
            self.make(devices=((1, 3), (1, 4)))

    def test_bus_and_address_select_one_device(self):
        devices = ((1, 3), (2, 4), (2, 5))
        for kw, want in (({"bus": 1}, (1, 3)), ({"address": 3}, (1, 3)), ({"bus": 2, "address": 5}, (2, 5)),
                         ({"bus": 1, "address": 3}, (1, 3))):
            with self.subTest(**kw):
                t, _ = self.make(devices=devices, **kw)
                self.assertEqual((t.dev.bus, t.dev.address), want)
        for kw in ({"bus": 3}, {"address": 9}, {"bus": 1, "address": 4}, {"bus": 2, "address": 3}):
            with self.subTest(**kw):
                with self.assertRaisesRegex(rs.TransportError, "no USB device"):
                    self.make(devices=devices, **kw)

    def test_reconnect_finds_the_device_at_its_new_address_on_the_same_bus(self):
        t, dev = self.make(devices=((1, 3), (2, 8)), bus=1)
        t.usb.devices = [(2, 9), (1, 6)]
        dev.log.clear()
        t.reconnect()
        self.assertEqual((t.dev.bus, t.dev.address), (1, 6))
        self.assertEqual((t.bus, t.address), (1, None))
        self.assertEqual(dev.log, [("reset",), ("set_configuration", 1)])

    def test_reconnect_survives_a_dead_handle_and_waits_for_the_device(self):
        t, dev = self.make()
        dev.reset = mock.Mock(side_effect=OSError("no such device"))
        t.dev.reset = dev.reset
        appear = {"n": 0}
        real_find = t.usb.find

        def find(**kw):
            appear["n"] += 1
            if appear["n"] < 4:
                return []
            return real_find(**kw)
        t.usb.find = find
        naps = []
        with mock.patch.object(rs.time, "sleep", naps.append):
            t.reconnect()
        self.assertEqual(dev.reset.call_count, 1)
        self.assertEqual(naps, [0.25, 0.25, 0.25])
        self.assertEqual(appear["n"], 4)

    def test_reconnect_gives_up_after_five_seconds(self):
        t, dev = self.make()
        t.usb.devices = []
        t.usb.calls.clear()
        naps = []
        with mock.patch.object(rs.time, "sleep", naps.append), self.assertRaisesRegex(rs.TransportError, "did not come back after a port reset"):
            t.reconnect()
        self.assertEqual(len(t.usb.calls), 20)
        self.assertEqual(sum(naps), 5.0)

    def test_reconnect_does_not_configure_when_not_asked(self):
        t, dev = self.make(configure=False)
        dev.log.clear()
        t.reconnect()
        self.assertEqual(dev.log, [("reset",)])


if __name__ == "__main__":
    unittest.main()
