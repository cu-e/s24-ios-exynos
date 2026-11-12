#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-080 host tests of the delivery companion (deliver_nat080.py). Evidence kind: host-test.

    artifacts/nat-065/venv/bin/python -I docs/procedures/nat-080/test_deliver80.py      (needs `cc`; no USB device is opened)

The companion runs here against the NAT-076 DWC3 model through the NAT-079 rig (docs/procedures/nat-079/test_e2e79.py): the model machine with
the engine up, the loader's receive phase compiled from the loader sources, and the real tools/ios/root_send.py sender. Nothing is faked
between the companion and the engine except the USB wire (a transport object, as in the NAT-076 tests) and the clock: the clock is a
hand-driven counter so that waits, deadlines and rates are computed by hand and no test sleeps.

What it shows: the companion sends nothing until the DEVICE reports a receive path of exactly the root size with nothing committed, works
with a device that is not configured yet, configures it once, writes a durable record, survives a bus reset in the middle of the transfer,
stops at its deadline without retrying and reports the device's committed offset, and reports every other ending (never ready, refused by
the device, a defect found by the sender's checksum, the device not opening) with the exit status the driver relies on. What it is not:
the S24, a real libusb stack, or a measurement of the host-to-phone rate.

Expected values are computed by hand from the data and the clock steps (comments give the arithmetic), not by calling the code under test."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import types
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KIB = 1024
SIZE = 512 * KIB
CHUNK = 128 * KIB
WRITE = 64 * KIB


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


E = load("nat080_e2e79", ROOT / "docs/procedures/nat-079/test_e2e79.py")
D = load("nat080_deliver", HERE / "deliver_nat080.py")
rs, M = E.rs, E.M
# GET_RX reply offsets (usbmon.h struct usbmon_rx_info), fixed by hand
AT_STATE, AT_FLAGS, AT_COMMITTED, AT_CAPACITY = 8, 12, 16, 40


def tearDownModule():
    E.tearDownModule()


class Clock:
    """A clock that moves only when a test moves it. Exact fractions, so 0.2-second sleeps add up without floating-point drift."""

    def __init__(self):
        self.now = Fraction(0)

    def mono(self):
        return float(self.now)

    def sleep(self, s):
        self.now += Fraction(s).limit_denominator(1000)

    advance = sleep


class ClockedTransport(rs.Transport):
    """The model's transport with every bulk write taking `per_write` seconds on the clock; `before_write(n)` may disturb the device before the
    n-th (1-based) bulk write is made."""

    def __init__(self, inner, clock, per_write=0.5, before_write=None):
        self.inner, self.clock, self.per_write, self.before_write = inner, clock, per_write, before_write
        self.writes = []
        self.reconnects = 0

    def rx_begin(self, offset, length):
        return self.inner.rx_begin(offset, length)

    def rx_abort(self):
        return self.inner.rx_abort()

    def get_rx(self):
        return self.inner.get_rx()

    def bulk_write(self, data):
        if self.before_write:
            self.before_write(len(self.writes) + 1)
        took = self.inner.bulk_write(data)
        self.writes.append(took)
        self.clock.advance(self.per_write)
        return took

    def reconnect(self):
        self.reconnects += 1
        return self.inner.reconnect()


def patched(raw, **fields):
    """A real GET_RX reply with some fields overwritten at their fixed offsets."""
    raw = bytearray(raw)
    for name, value in fields.items():
        at, fmt = {"state": (AT_STATE, "<I"), "flags": (AT_FLAGS, "<I"), "committed": (AT_COMMITTED, "<Q"),
                   "capacity": (AT_CAPACITY, "<Q")}[name]
        struct.pack_into(fmt, raw, at, value)
    return bytes(raw)


class Scripted(rs.Transport):
    """A transport whose GET_RX answers come from a list (the last one repeats); anything else is not expected."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def get_rx(self):
        r = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        return r


def read_journal(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


class Case(unittest.TestCase):
    """One model machine of SIZE bytes, a clock, a journal in a fresh directory."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("cc") is None:
            raise unittest.SkipTest("no C compiler")
        cls.lib = E.build_lib(1)

    def setUp(self):
        self.rig = E.Rig(self.lib, SIZE, 1)
        self.addCleanup(self.rig.close)
        self.data = E.blob(SIZE, 11)
        self.tmp = Path(tempfile.mkdtemp(prefix="nat080-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.clock = Clock()
        self.journal_path = self.tmp / "delivery.jsonl"
        self.journal = D.Journal(self.journal_path, clock=lambda: 1.7e9, mono=self.clock.mono)
        self.addCleanup(self.journal.close)
        self.placeholder_reply = self.rig.rx()
        self.opened = []

    def events(self, name=None):
        evs = read_journal(self.journal_path)
        return [e for e in evs if name is None or e["event"] == name]

    def run_deliver(self, open_probe=None, open_send=None, wait_s=60, deliver_s=1000, per_write=0.5, before_write=None, data=None, **kw):
        """deliver() as the companion calls it, with the clock and the model transport wired in. Must run inside the loader's receive phase
        (the callback), so the engine is polled."""
        self.xport = ClockedTransport(self.rig.t, self.clock, per_write, before_write)

        def probe():
            self.opened.append("probe")
            return open_probe() if open_probe else self.rig.t

        def send():
            self.opened.append("send")
            return open_send(self.xport) if open_send else self.xport

        args = dict(chunk=CHUNK, write_size=WRITE, progress_bytes=2 * CHUNK, mono=self.clock.mono, sleep=self.clock.sleep)
        args.update(kw)
        return D.deliver(rs, self.data if data is None else data, probe, send, self.journal, wait_s, deliver_s, **args)

    def in_phase(self, fn):
        """Run fn inside the loader's receive phase and return (fn's result, the loader's result)."""
        r = self.rig.receive(fn)
        self.assertIsNone(self.rig.host_error)
        return self.rig.host_result, r

    def reserve(self):
        return self.rig.m.dest(self.rig.off, SIZE)


class Probe(Case):
    def probe(self, transport=None, size=SIZE):
        return D.probe_ready(rs, lambda: transport or self.rig.t, size)

    def test_the_engine_with_the_placeholder_is_waited_for(self):
        state, detail = self.probe()
        self.assertEqual(state, "placeholder")
        self.assertEqual((detail["capacity"], detail["committed"]), (512, 0))
        self.assertTrue(detail["flags"] & 1)

    def test_the_reserve_handed_over_is_ready(self):
        got, r = self.in_phase(self.probe)
        self.assertEqual(got[0], "ready")
        self.assertEqual((got[1]["capacity"], got[1]["committed"], got[1]["state"]), (SIZE, 0, 0))

    def test_a_device_that_is_not_configured_is_ready_too(self):
        def look():
            self.rig.m.bus_reset()
            raw = self.rig.rx()
            self.assertEqual(struct.unpack_from("<I", raw, AT_FLAGS)[0] & 2, 0)		# ENABLED is clear: the bulk endpoint does not exist yet
            return self.probe()

        got, _ = self.in_phase(look)
        self.assertEqual(got[0], "ready")

    def test_no_device_a_failing_read_and_a_garbled_reply_are_absent(self):
        def no_device():
            raise rs.TransportError("no USB device 1209:0001")

        state, detail = D.probe_ready(rs, no_device, SIZE)
        self.assertEqual(state, "absent")
        self.assertIn("no USB device", detail)
        state, detail = self.probe(Scripted([rs.TransportError("GET_RX: stall")]))
        self.assertEqual((state, "stall" in detail), ("absent", True))
        state, detail = self.probe(Scripted([self.placeholder_reply[:60]]))		# a short reply
        self.assertEqual(state, "absent")
        self.assertIn("120", detail)
        state, _ = self.probe(Scripted([b"XXXX" + self.placeholder_reply[4:]]))		# not the S24R block
        self.assertEqual(state, "absent")

    def test_every_other_capacity_is_refused(self):
        good = patched(self.placeholder_reply, capacity=SIZE)
        for cap in (0, 1, 511, 513, 1024, SIZE - 16 * KIB, SIZE - 1, SIZE + 1, SIZE + 16 * KIB, 2 * SIZE, 1 << 40):
            state, detail = self.probe(Scripted([patched(good, capacity=cap)]))
            self.assertEqual(state, "refuse", cap)
            self.assertEqual(detail["capacity"], cap)
            self.assertIn("capacity", detail["why"])
        self.assertEqual(self.probe(Scripted([good]))[0], "ready")

    def test_a_device_without_the_receive_path_is_refused_whatever_its_capacity(self):
        for cap in (512, SIZE):
            state, detail = self.probe(Scripted([patched(self.placeholder_reply, flags=2, capacity=cap)]))
            self.assertEqual(state, "refuse", cap)
            self.assertIn("no bulk-OUT receive path", detail["why"])

    def test_committed_bytes_or_a_transfer_in_progress_are_not_a_fresh_boot(self):
        good = patched(self.placeholder_reply, capacity=SIZE)
        for fields in ({"committed": 16 * KIB}, {"committed": SIZE}, {"state": 1}, {"state": 2}, {"state": 1, "committed": 16 * KIB}):
            state, detail = self.probe(Scripted([patched(good, **fields)]))
            self.assertEqual(state, "refuse", fields)
            self.assertIn("committed", detail["why"])
        # the flags other than PRESENT do not matter
        for flags in (1, 3, 5, 7, 0x81):
            self.assertEqual(self.probe(Scripted([patched(good, flags=flags)]))[0], "ready", flags)

    def test_a_placeholder_is_waited_for_even_with_leftover_state(self):
        for fields in ({"committed": 512}, {"state": 1}):
            state, detail = self.probe(Scripted([patched(self.placeholder_reply, **fields)]))
            self.assertEqual(state, "placeholder", fields)

    def test_the_probe_only_reads(self):
        before = self.rig.m.cmd_trace()
        self.probe()
        self.assertEqual(self.rig.t.begins, [])
        new = self.rig.m.cmd_trace()[len(before):]
        self.assertTrue(new)						# the control transfer itself ran ...
        self.assertEqual({c[0] for c in new} - {0, 1}, set())		# ... on the two control endpoints, never on the bulk-OUT endpoint (physical 2)
        self.assertEqual(self.rig.m.violations(), [])


class Waiting(Case):
    def test_a_device_that_never_shows_up_gets_nothing_and_a_heartbeat_record(self):
        def no_device():
            raise rs.TransportError("no USB device 1209:0001")

        outcome, summary = self.run_deliver(open_probe=no_device, wait_s=10)
        self.assertEqual(outcome, "never-ready")
        self.assertNotIn("send", self.opened)			# the sender's transport (which configures the device) was never asked for
        self.assertEqual((summary["waited_s"], summary["last_seen"]), (10.0, "absent"))
        self.assertIn("no USB device", summary["last_detail"])
        beats = self.events("waiting")
        self.assertEqual([e["waited_s"] for e in beats], [0.0, 2.0, 4.0, 6.0, 8.0, 10.0])		# a record every 2 s, the first at the first look
        self.assertEqual([e["seen"] for e in beats], ["absent"] * 6)
        self.assertEqual(self.events("ready") + self.events("refuse"), [])

    def test_the_placeholder_never_replaced_is_never_ready_and_nothing_is_sent(self):
        outcome, summary = self.run_deliver(wait_s=3)		# the rig's engine still holds the 512-byte placeholder
        self.assertEqual(outcome, "never-ready")
        self.assertEqual(summary["last_seen"], "placeholder")
        self.assertEqual(summary["last_detail"]["capacity"], 512)
        self.assertEqual(self.xport.writes, [])
        self.assertEqual(self.rig.t.begins, [])
        self.assertEqual(self.opened.count("send"), 0)

    def test_the_wait_ends_when_the_wait_time_has_passed_not_before(self):
        outcome, summary = self.run_deliver(wait_s=2.6)
        self.assertEqual(outcome, "never-ready")
        self.assertEqual(summary["waited_s"], 2.6)			# probes at 0, 0.2, ... 2.6: the last one is the first at or past 2.6
        self.assertEqual(self.opened.count("probe"), 14)

    def test_a_device_that_comes_up_during_the_wait_is_sent_to_once_ready(self):
        replies = [self.placeholder_reply] * 3

        def probe():
            live = self.rig.t

            class T(rs.Transport):
                def get_rx(self):
                    return replies.pop(0) if replies else live.get_rx()

            return T()

        got, r = self.in_phase(lambda: self.run_deliver(open_probe=probe, wait_s=60))
        outcome, summary = got
        self.assertEqual((outcome, r.status), ("delivered", E.DONE))
        self.assertEqual(self.opened, ["probe"] * 4 + ["send"])	# three placeholders, the live reply, then the sender's transport
        ready = self.events("ready")
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["waited_s"], 0.6)			# three 0.2 s sleeps
        self.assertEqual(ready[0]["detail"]["capacity"], SIZE)
        self.assertEqual(self.events("waiting")[0]["seen"], "placeholder")
        self.assertEqual(self.reserve(), self.data)

    def test_the_heartbeat_is_written_at_the_first_look_even_when_the_device_is_ready_later(self):
        replies = [self.placeholder_reply]

        def probe():
            live = self.rig.t

            class T(rs.Transport):
                def get_rx(self):
                    return replies.pop(0) if replies else live.get_rx()

            return T()

        self.in_phase(lambda: self.run_deliver(open_probe=probe, wait_s=60))
        self.assertEqual([e["seen"] for e in self.events("waiting")], ["placeholder"])


class Refusing(Case):
    def check_refused(self, outcome_summary, why):
        outcome, summary = outcome_summary
        self.assertEqual(outcome, "refused-by-device")
        self.assertIn(why, summary["detail"]["why"])
        self.assertEqual(self.opened.count("send"), 0)			# the sender's transport (which would configure the device) was never opened
        self.assertEqual(self.xport.writes, [])
        self.assertEqual(self.rig.t.begins, [])
        refuse = self.events("refuse")
        self.assertEqual(len(refuse), 1)
        self.assertEqual(refuse[0]["detail"], summary["detail"])
        self.assertEqual(self.events("ready"), [])

    def test_a_root_image_of_another_size_than_the_reserve(self):
        data = E.blob(SIZE + 16 * KIB, 12)
        got, _ = self.in_phase(lambda: self.run_deliver(data=data))
        self.check_refused(got, "capacity")
        self.assertEqual(got[1]["detail"]["capacity"], SIZE)

    def test_a_device_that_already_holds_committed_bytes(self):
        def early():
            self.rig.send(self.data[:CHUNK], chunk=CHUNK, write_size=WRITE)		# somebody delivered the first chunk already
            self.rig.t.begins.clear()
            return self.run_deliver()

        got, _ = self.in_phase(early)
        self.check_refused(got, "committed")
        self.assertEqual(got[1]["detail"]["committed"], CHUNK)

    def test_a_transfer_left_armed(self):
        def armed():
            self.rig.t.rx_begin(0, CHUNK)
            self.rig.t.begins.clear()
            return self.run_deliver()

        got, _ = self.in_phase(armed)
        self.check_refused(got, "armed")
        self.assertEqual(got[1]["detail"]["state"], 1)

    def test_a_refusal_changes_nothing_in_the_device(self):
        def one():
            before = self.rig.rx()
            res = self.run_deliver(data=E.blob(SIZE + 16 * KIB, 13))
            return res, before, self.rig.rx()

        (res, before, after), _ = self.in_phase(one)
        self.assertEqual(res[0], "refused-by-device")
        self.assertEqual(before[:120], after[:120])

    def test_an_engine_without_the_receive_path(self):
        class T(rs.Transport):
            def get_rx(self_):
                return patched(self.placeholder_reply, flags=0)

        outcome, summary = self.run_deliver(open_probe=lambda: T())
        self.assertEqual(outcome, "refused-by-device")
        self.assertIn("no bulk-OUT receive path", summary["detail"]["why"])
        self.assertEqual(self.opened.count("send"), 0)


class Delivering(Case):
    def deliver_in_phase(self, **kw):
        got, r = self.in_phase(lambda: self.run_deliver(**kw))
        return got[0], got[1], r

    def test_the_image_arrives_exactly_and_the_loader_sees_every_byte(self):
        outcome, summary, r = self.deliver_in_phase()
        self.assertEqual(outcome, "delivered")
        self.assertEqual(r.status, E.DONE)
        self.assertEqual((r.committed, r.bytes), (SIZE, SIZE))
        self.assertEqual(self.reserve(), self.data)
        self.assertTrue(self.rig.untouched_outside_reserve())
        self.assertEqual(self.rig.m.violations(), [])
        self.assertEqual(summary["device"]["committed"], SIZE)
        self.assertEqual((summary["device"]["state"], summary["device"]["capacity"]), (0, SIZE))
        self.assertIsNone(summary["error"])
        self.assertEqual(summary["sender"]["committed"], SIZE)

    def test_the_sender_gets_the_chunk_and_write_sizes_that_were_asked_for(self):
        self.deliver_in_phase()
        self.assertEqual([n for _, n in self.rig.t.begins], [CHUNK] * (SIZE // CHUNK))
        self.assertEqual([o for o, _ in self.rig.t.begins], list(range(0, SIZE, CHUNK)))
        self.assertEqual(self.xport.writes, [WRITE] * (SIZE // WRITE))

    def test_the_transport_is_opened_once_and_after_the_probe_said_ready(self):
        self.deliver_in_phase()
        self.assertEqual(self.opened, ["probe", "send"])
        ev = [e["event"] for e in self.events()]
        self.assertLess(ev.index("ready"), ev.index("sender"))

    def test_a_device_that_is_not_configured_is_configured_by_the_sender_transport_only(self):
        seen = []

        def open_send(xport):
            seen.append(("enabled before", struct.unpack_from("<I", self.rig.rx(), AT_FLAGS)[0] & 2))
            rc, _ = self.rig.m.ctrl(0x00, 9, 1, 0, 0)				# SET_CONFIGURATION(1), as PyUsbTransport(configure=True) does
            self.assertEqual(rc, M.H_OK)
            seen.append(("enabled after", struct.unpack_from("<I", self.rig.rx(), AT_FLAGS)[0] & 2))
            return xport

        def unconfigured():
            self.rig.m.bus_reset()
            self.assertEqual(self.rig.m.ctrl(0x00, 5, 9, 0, 0)[0], M.H_OK)		# addressed, not configured
            return self.run_deliver(open_send=open_send)

        got, r = self.in_phase(unconfigured)
        self.assertEqual(got[0], "delivered")
        self.assertEqual(seen, [("enabled before", 0), ("enabled after", 2)])
        self.assertEqual(self.reserve(), self.data)
        self.assertEqual(r.status, E.DONE)

    def test_the_summary_numbers(self):
        outcome, summary, _ = self.deliver_in_phase(per_write=0.5)
        # 8 writes of 64 KiB, half a second each: 4.0 s; 524288 B / 4 s = 131072 B/s
        self.assertEqual(summary["seconds"], 4.0)
        self.assertEqual(summary["host_bytes_written"], SIZE)
        self.assertEqual(summary["mb_per_s"], 0.131)
        self.assertEqual(summary["mib_per_s"], 0.125)
        self.assertIsNone(summary["error"])
        self.assertEqual((summary["sender"]["chunks"], summary["sender"]["retries"], summary["sender"]["bytes_written"]), (4, 0, SIZE))

    def test_progress_records(self):
        self.deliver_in_phase(per_write=0.5, progress_bytes=2 * CHUNK)
        prog = self.events("progress")
        # every 256 KiB: after 4 writes (2.0 s), after 8 writes (4.0 s)
        self.assertEqual([p["host_bytes"] for p in prog], [2 * CHUNK, 4 * CHUNK])
        self.assertEqual([p["seconds"] for p in prog], [2.0, 4.0])
        self.assertEqual([p["fraction"] for p in prog], [0.5, 1.0])
        self.assertEqual([p["mb_per_s_total"] for p in prog], [0.131, 0.131])		# 262144 B / 2 s = 131072 B/s = 0.131 MB/s
        self.assertEqual([p["mb_per_s_recent"] for p in prog], [0.131, 0.131])
        self.assertEqual([p["t_unix"] for p in prog], [1.7e9, 1.7e9])

    def test_progress_marks_move_past_the_bytes_already_sent(self):
        # a mark of one write: every write logs, with the next mark always one write further on
        self.deliver_in_phase(per_write=0.5, progress_bytes=WRITE)
        self.assertEqual([p["host_bytes"] for p in self.events("progress")], [WRITE * i for i in range(1, 9)])

    def test_recent_rate_is_for_the_interval_since_the_previous_record(self):
        def slow_second_half(n):
            if n > 4:
                self.clock.advance(1)				# the writes after the fourth take 1.5 s instead of 0.5 s

        self.deliver_in_phase(per_write=0.5, progress_bytes=4 * WRITE, before_write=slow_second_half)
        prog = self.events("progress")
        self.assertEqual([p["seconds"] for p in prog], [2.0, 8.0])		# 4 writes x 0.5 s, then 4 writes x 1.5 s
        self.assertEqual([p["mb_per_s_total"] for p in prog], [0.131, 0.066])			# 262144/2, 524288/8 -> 131072, 65536 B/s
        self.assertEqual([p["mb_per_s_recent"] for p in prog], [0.131, 0.044])			# 262144 B in 6 s = 43690.7 B/s

    def test_sender_messages_are_in_the_journal(self):
        self.deliver_in_phase()
        texts = [e["text"] for e in self.events("sender")]
        self.assertEqual(texts[0], "start: device committed 0, sending 0..%d in chunks of %d" % (SIZE, CHUNK))

    def test_sender_options_are_passed_through(self):
        def disturbed(n):
            if n == 2:
                raise rs.TransportError("injected")

        outcome, summary, _ = self.deliver_in_phase(before_write=disturbed, sender_kw=dict(max_retries=0))
        self.assertEqual(outcome, "failed")				# no retry allowed: the first failure ends it
        self.assertIn("DeliveryError", summary["error"])
        self.assertIn("failed 1 times", summary["error"])

    def test_a_bus_reset_in_the_middle_of_a_chunk_is_survived_by_reconnect_and_resume(self):
        fired = set()

        def reset_on_sixth(n):
            if n == 6 and n not in fired:
                fired.add(n)
                self.rig.m.bus_reset()					# the cable is bumped between the first and second write of the third chunk

        outcome, summary, r = self.deliver_in_phase(before_write=reset_on_sixth)
        self.assertEqual(outcome, "delivered")
        self.assertEqual(r.status, E.DONE)
        self.assertEqual(self.reserve(), self.data)
        self.assertTrue(self.rig.untouched_outside_reserve())
        self.assertEqual(self.xport.reconnects, 1)
        rec = self.events("reconnect")
        self.assertEqual([e["host_bytes"] for e in rec], [5 * WRITE])		# five writes had succeeded when the sixth found the device reset
        self.assertEqual(summary["sender"]["retries"], 1)
        self.assertEqual(summary["sender"]["resumed_from"], 0)
        # 4 chunks of 2 writes; the third chunk is written once in part (1 write ok, the second fails) and again in full: 8 + 1 = 9 writes
        self.assertEqual(len(self.xport.writes), 9)
        self.assertEqual(summary["host_bytes_written"], 9 * WRITE)
        self.assertGreaterEqual(summary["device"]["rx_resets"], 1)
        self.assertEqual(summary["device"]["committed"], SIZE)
        self.assertEqual(self.rig.m.violations(), [])

    def test_three_bus_resets_in_a_row_between_chunks(self):
        fired = set()

        def reset_between(n):
            if n in (3, 5, 7) and n not in fired:				# the first write of chunks 2, 3, 4
                fired.add(n)
                self.rig.m.bus_reset()

        outcome, summary, r = self.deliver_in_phase(before_write=reset_between)
        self.assertEqual(outcome, "delivered")
        self.assertEqual(self.reserve(), self.data)
        self.assertEqual(summary["sender"]["retries"], 3)
        self.assertEqual(self.xport.reconnects, 3)
        self.assertEqual([e["host_bytes"] for e in self.events("reconnect")], [2 * WRITE, 4 * WRITE, 6 * WRITE])
        self.assertEqual(summary["host_bytes_written"], SIZE)			# every failed write came first in its chunk: nothing was sent twice

    def test_lost_dma_is_found_by_the_sender_and_the_device_view_is_kept(self):
        # DMA writes into the second half of the reserve are silently lost (NAT-040 item U5): the third chunk (256..384 KiB) is committed
        # with a checksum of memory that does not hold the data
        self.rig.m.set_dma_limit(self.rig.off + SIZE // 2)
        outcome, summary, r = self.deliver_in_phase()
        self.assertEqual(outcome, "failed")
        self.assertTrue(summary["error"].startswith("DeliveryError:"), summary["error"])
        self.assertIn("different checksum", summary["error"])
        self.assertEqual(summary["device"]["committed"], 3 * CHUNK)
        self.assertEqual(summary["device"]["state"], 0)
        self.assertIsNone(summary["sender"])
        self.assertEqual(summary["host_bytes_written"], 6 * WRITE)
        self.assertEqual(summary["seconds"], 3.0)				# 6 writes x 0.5 s
        self.assertEqual(summary["mb_per_s"], 0.131)				# the device's committed bytes over time: 393216 B / 3 s = 131072 B/s
        self.assertEqual(self.reserve()[:SIZE // 2], self.data[:SIZE // 2])
        self.assertNotEqual(self.reserve(), self.data)

    def test_a_transfer_that_cannot_open_the_sender_transport_reports_it_and_sends_nothing(self):
        def broken(xport):
            raise rs.TransportError("could not set the configuration: Resource busy")

        got, _ = self.in_phase(lambda: self.run_deliver(open_send=broken))
        outcome, summary = got
        self.assertEqual(outcome, "failed")
        self.assertEqual(summary["error"], "TransportError: could not set the configuration: Resource busy")
        self.assertEqual((summary["device"], summary["host_bytes_written"], summary["seconds"], summary["mb_per_s"], summary["mib_per_s"],
                          summary["sender"]), (None, 0, 0.0, None, None, None))
        self.assertEqual(self.rig.t.begins, [])
        self.assertEqual(self.events("send-open-failed")[0]["error"], summary["error"])
        self.assertEqual(self.events("sender"), [])

    def test_a_sender_transport_that_raises_a_root_send_error_is_reported_too(self):
        def odd(xport):
            raise rs.DeviceStateError("odd")

        got, _ = self.in_phase(lambda: self.run_deliver(open_send=odd))
        self.assertEqual((got[0], got[1]["error"]), ("failed", "DeviceStateError: odd"))

    def test_a_device_that_cannot_be_read_after_the_sender_gave_up_still_gets_a_record(self):
        # the model has no 'device gone' error on endpoint 0; a transport raising on every GET_RX stands in for it
        class Gone(ClockedTransport):
            def get_rx(self_):
                raise rs.TransportError("GET_RX: no device")

        got, _ = self.in_phase(lambda: self.run_deliver(open_send=lambda x: Gone(self.rig.t, self.clock, 0.5, None)))
        outcome, summary = got
        self.assertEqual(outcome, "failed")
        self.assertIn("DeviceStateError", summary["error"])			# the sender cannot even read GET_RX
        self.assertIn("error", summary["device"])
        self.assertIn("no device", summary["device"]["error"])
        self.assertEqual(summary["host_bytes_written"], 0)
        self.assertIsNone(summary["mb_per_s"])


class Deadline(Case):
    def test_the_deadline_stops_the_sender_without_a_retry_and_the_armed_chunk_is_ended(self):
        # ready at t=0, deadline 2.2: writes 1..5 pass (t = 0, .5, 1, 1.5, 2.0), the sixth is refused at t=2.5; chunk 3 is armed with 64 KiB of 128 KiB
        got, r = self.in_phase(lambda: self.run_deliver(deliver_s=2.2, per_write=0.5))
        outcome, summary = got
        self.assertEqual(outcome, "cap-reached")
        self.assertEqual(summary["error"], "delivery deadline passed after %d bytes written" % (5 * WRITE))
        self.assertEqual(summary["host_bytes_written"], 5 * WRITE)
        self.assertEqual(len(self.xport.writes), 5)
        self.assertEqual(self.xport.reconnects, 0)
        self.assertEqual(summary["device"]["committed"], 2 * CHUNK)		# two whole chunks
        self.assertEqual(summary["device"]["state"], 0)			# the third was ended with RX_ABORT: nothing of it is committed
        self.assertEqual(summary["device"]["rx_aborts"], 1)
        self.assertEqual(summary["seconds"], 2.5)
        self.assertEqual(summary["mb_per_s"], 0.105)			# 262144 B / 2.5 s = 104857.6 B/s
        self.assertEqual(summary["mib_per_s"], 0.1)
        self.assertIsNone(summary["sender"])
        self.assertEqual(r.status, E.TIMEOUT)				# the loader's own cap ends the phase later; what it committed is what the device says
        self.assertEqual(r.committed, 2 * CHUNK)
        self.assertEqual(self.reserve()[:2 * CHUNK], self.data[:2 * CHUNK])

    def test_a_deadline_that_has_already_passed_sends_nothing(self):
        got, _ = self.in_phase(lambda: self.run_deliver(deliver_s=0))
        self.assertEqual(got[0], "cap-reached")
        self.assertEqual(got[1]["host_bytes_written"], 0)
        self.assertEqual(got[1]["device"]["committed"], 0)
        self.assertEqual(self.rig.t.begins, [])
        self.assertIsNone(got[1]["mb_per_s"])

    def test_the_deadline_counts_from_the_moment_the_device_was_ready_not_from_the_start(self):
        replies = [self.placeholder_reply] * 5				# five looks, 0.2 s apart: ready at t = 1.0

        def probe():
            live = self.rig.t

            class T(rs.Transport):
                def get_rx(self_):
                    return replies.pop(0) if replies else live.get_rx()

            return T()

        # deadline 1.2 s after ready: writes at 0, .5, 1.0 pass, the fourth is refused at 1.5 -> 3 writes (a chunk and a half)
        got, _ = self.in_phase(lambda: self.run_deliver(open_probe=probe, deliver_s=1.2, wait_s=100))
        self.assertEqual(got[0], "cap-reached")
        self.assertEqual(got[1]["host_bytes_written"], 3 * WRITE)
        self.assertEqual(got[1]["device"]["committed"], CHUNK)

    def test_a_deadline_after_the_last_chunk_does_not_turn_a_delivery_into_a_cap(self):
        # the image takes 4.0 s; the deadline of 4.0 is checked only before a write or an RX_BEGIN, and there is none after the last write
        got, _ = self.in_phase(lambda: self.run_deliver(deliver_s=4.0, per_write=0.5))
        self.assertEqual(got[0], "delivered")
        self.assertEqual(got[1]["host_bytes_written"], SIZE)

    def test_the_deadline_is_inclusive(self):
        # the eighth write starts at t = 3.5: a deadline of exactly 3.5 s refuses it, 3.6 s lets it through
        got, _ = self.in_phase(lambda: self.run_deliver(deliver_s=3.5, per_write=0.5))
        self.assertEqual(got[0], "cap-reached")
        self.assertEqual(got[1]["host_bytes_written"], 7 * WRITE)
        self.assertEqual(got[1]["device"]["committed"], 3 * CHUNK)		# the fourth chunk was armed with 64 KiB and is ended

    def test_a_little_more_time_is_a_delivery(self):
        got, _ = self.in_phase(lambda: self.run_deliver(deliver_s=3.6, per_write=0.5))
        self.assertEqual(got[0], "delivered")


class Metered(unittest.TestCase):
    class Inner(rs.Transport):
        def __init__(self):
            self.calls = []

        def rx_begin(self, offset, length):
            self.calls.append(("rx_begin", offset, length))
            return "begin-result"

        def rx_abort(self):
            self.calls.append(("rx_abort",))
            return "abort-result"

        def get_rx(self):
            self.calls.append(("get_rx",))
            return b"rx-bytes"

        def bulk_write(self, data):
            self.calls.append(("bulk_write", len(data)))
            return len(data) - 1				# the device took one byte less

        def reconnect(self):
            self.calls.append(("reconnect",))
            return "reconnected"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nat080-metered-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.clock = Clock()
        self.journal = D.Journal(self.tmp / "j.jsonl", clock=lambda: 5.0, mono=self.clock.mono)
        self.addCleanup(self.journal.close)
        self.inner = self.Inner()

    def make(self, deadline=100.0, progress=10, total=40):
        return D.MeteredTransport(self.inner, self.journal, rs, self.clock.mono, deadline, progress, total)

    def test_calls_and_results_pass_through_unchanged(self):
        t = self.make()
        self.assertEqual(t.rx_begin(16384, 4096), "begin-result")
        self.assertEqual(t.get_rx(), b"rx-bytes")
        self.assertEqual(t.rx_abort(), "abort-result")
        self.assertEqual(t.reconnect(), "reconnected")
        self.assertEqual(t.bulk_write(b"x" * 8), 7)			# the device's own count is returned, not len(data)
        self.assertEqual(self.inner.calls, [("rx_begin", 16384, 4096), ("get_rx",), ("rx_abort",), ("reconnect",), ("bulk_write", 8)])

    def test_the_bytes_counted_are_the_bytes_the_device_took(self):
        t = self.make()
        t.bulk_write(b"x" * 8)
        t.bulk_write(b"x" * 3)
        self.assertEqual(t.sent, 7 + 2)

    def test_the_deadline_stops_writes_and_begins_but_not_reads_or_aborts(self):
        t = self.make(deadline=10.0)
        self.clock.advance(9.5)
        t.rx_begin(0, 4)
        t.bulk_write(b"abcd")
        self.clock.advance(0.5)						# now == deadline
        for call in (lambda: t.rx_begin(0, 4), lambda: t.bulk_write(b"abcd")):
            with self.assertRaises(D.CapReached):
                call()
        self.assertEqual(t.get_rx(), b"rx-bytes")
        self.assertEqual(t.rx_abort(), "abort-result")
        self.assertEqual(t.reconnect(), "reconnected")
        self.assertEqual(self.inner.calls.count(("bulk_write", 4)), 1)	# the refused write never reached the device

    def test_the_cap_is_not_an_error_the_sender_would_retry(self):
        self.assertFalse(issubclass(D.CapReached, rs.TransportError))
        self.assertFalse(issubclass(D.CapReached, rs.RootSendError))
        self.assertTrue(issubclass(D.CapReached, Exception))

    def test_the_progress_record_is_written_at_the_mark_and_marks_advance(self):
        t = self.make(progress=10, total=40)
        for i in range(12):
            self.clock.advance(1)
            t.bulk_write(b"x" * 4)						# the device takes 3 bytes: 3, 6, 9, 12 ... 36
        recs = [json.loads(l) for l in (self.tmp / "j.jsonl").read_text().splitlines()]
        self.assertEqual([r["event"] for r in recs], ["progress"] * 3)
        self.assertEqual([r["host_bytes"] for r in recs], [12, 21, 30])		# the first write at or past 10, 20, 30
        self.assertEqual([r["seconds"] for r in recs], [4.0, 7.0, 10.0])
        self.assertEqual([r["fraction"] for r in recs], [0.3, 0.525, 0.75])

    def test_a_big_write_that_jumps_over_several_marks_logs_once(self):
        t = self.make(progress=10, total=1000)
        self.clock.advance(1)
        t.bulk_write(b"x" * 56)						# 55 bytes taken: marks 10..50 are all behind it
        self.clock.advance(1)
        t.bulk_write(b"x" * 6)						# 5 more: 60, the next mark is 60
        recs = [json.loads(l) for l in (self.tmp / "j.jsonl").read_text().splitlines()]
        self.assertEqual([r["host_bytes"] for r in recs], [55, 60])

    def test_the_first_record_is_measured_from_the_start_and_rounded_to_milliseconds(self):
        self.clock.now = Fraction(100)						# the clock does not start at zero
        t = self.make(deadline=1000.0, progress=1000, total=3000)
        self.clock.now += Fraction(1, 1000)
        t.bulk_write(b"x" * 1001)						# the device takes 1000 bytes in 0.001 s: 1.0 MB/s over everything and over the interval
        rec = json.loads((self.tmp / "j.jsonl").read_text().splitlines()[0])
        self.assertEqual((rec["host_bytes"], rec["seconds"], rec["mb_per_s_total"], rec["mb_per_s_recent"], rec["fraction"]),
                         (1000, 0.001, 1.0, 1.0, 0.33333))
        self.clock.now += Fraction(16, 10000)
        t.bulk_write(b"x" * 1001)						# 2000 bytes after 0.0026 s: 0.769 MB/s overall, the last 1000 bytes took 0.0016 s: 0.625 MB/s
        rec = json.loads((self.tmp / "j.jsonl").read_text().splitlines()[1])
        self.assertEqual((rec["host_bytes"], rec["seconds"], rec["mb_per_s_total"], rec["mb_per_s_recent"], rec["fraction"]),
                         (2000, 0.003, 0.769, 0.625, 0.66667))

    def test_no_elapsed_time_gives_a_huge_rate_and_not_a_division_by_zero(self):
        t = self.make(progress=1000, total=3000)
        t.bulk_write(b"x" * 1001)
        rec = json.loads((self.tmp / "j.jsonl").read_text().splitlines()[0])
        self.assertEqual((rec["seconds"], rec["mb_per_s_total"], rec["mb_per_s_recent"]), (0.0, 1000000.0, 1000000.0))		# 1000 B / 1e-9 s / 1e6

    def test_reconnect_is_recorded_with_the_bytes_so_far(self):
        t = self.make(progress=1000)
        t.bulk_write(b"x" * 11)
        t.reconnect()
        rec = json.loads((self.tmp / "j.jsonl").read_text().splitlines()[-1])
        self.assertEqual((rec["event"], rec["host_bytes"]), ("reconnect", 10))


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nat080-journal-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_a_record_is_on_disk_and_synced_when_emit_returns(self):
        j = D.Journal(self.tmp / "j.jsonl", clock=lambda: 12.5, mono=lambda: 3.25)
        self.addCleanup(j.close)
        with mock.patch.object(D.os, "fsync", wraps=os.fsync) as fs:
            j.emit("start", b=2, a=1)
            self.assertEqual(fs.call_count, 1)
            self.assertEqual((self.tmp / "j.jsonl").read_text(), '{"a": 1, "b": 2, "event": "start", "t_mono": 3.25, "t_unix": 12.5}\n')
            j.emit("next")
            self.assertEqual(fs.call_count, 2)
        self.assertEqual(len((self.tmp / "j.jsonl").read_text().splitlines()), 2)

    def test_close_closes_the_file(self):
        j = D.Journal(self.tmp / "j.jsonl")
        self.assertFalse(j.f.closed)
        j.close()
        self.assertTrue(j.f.closed)

    def test_an_existing_record_is_never_overwritten(self):
        (self.tmp / "j.jsonl").write_text("old\n")
        with self.assertRaises(FileExistsError):
            D.Journal(self.tmp / "j.jsonl")
        self.assertEqual((self.tmp / "j.jsonl").read_text(), "old\n")

    def test_times_are_rounded_to_microseconds(self):
        j = D.Journal(self.tmp / "j.jsonl", clock=lambda: 1.23456789, mono=lambda: 9.87654321)
        self.addCleanup(j.close)
        j.emit("x")
        rec = json.loads((self.tmp / "j.jsonl").read_text())
        self.assertEqual((rec["t_unix"], rec["t_mono"]), (1.234568, 9.876543))


class Hashing(unittest.TestCase):
    def test_stream_sha256_matches_hashlib_for_every_block_alignment(self):
        tmp = Path(tempfile.mkdtemp(prefix="nat080-hash-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        for n in (0, 1, 7, 8, 9, 15, 16, 17, 100):
            data = bytes((i * 7 + 3) % 256 for i in range(n))
            p = tmp / ("f%d" % n)
            p.write_bytes(data)
            self.assertEqual(D.stream_sha256(p, block=8), (hashlib.sha256(data).hexdigest(), n), n)


    def test_the_default_read_size_is_eight_mebibytes_so_the_image_is_never_held_whole(self):
        reads = []

        class Fake:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                reads.append(n)
                return b"" if len(reads) > 2 else b"12345"

        with mock.patch.object(D, "open", lambda path, mode: Fake(), create=True):
            digest, n = D.stream_sha256("not-a-file")
        self.assertEqual(reads, [8 * 1024 * 1024] * 3)
        self.assertEqual((digest, n), (hashlib.sha256(b"1234512345").hexdigest(), 10))


class Main(Case):
    """The command line: refusals before anything is opened, the record on disk, the exit statuses."""

    def make_root(self, data=None):
        data = self.data if data is None else data
        p = self.tmp / "root.img"
        p.write_bytes(data)
        return p, hashlib.sha256(data).hexdigest()

    def run_main(self, argv, deliver=None, sender=None):
        out, err = io.StringIO(), io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        opened = []
        ns = types.SimpleNamespace(**vars(rs))

        def fake_transport(configure=True):
            opened.append(configure)
            return ClockedTransport(self.rig.t, Clock(), 0.0)

        ns.PyUsbTransport = fake_transport
        stack.enter_context(mock.patch.object(D, "load_sender", lambda: sender or ns))
        if deliver:
            stack.enter_context(mock.patch.object(D, "deliver", deliver))
        with stack:
            code = D.main(argv)
        return code, out.getvalue(), err.getvalue(), opened

    def argv(self, root, sha, out, size=None, *extra):
        return ["--root", str(root), "--size", str(SIZE if size is None else size), "--sha256", sha, "--out", str(out), *extra]

    def test_a_complete_delivery_leaves_the_record_and_exits_0(self):
        root, sha = self.make_root()
        out = self.tmp / "out"
        (code, stdout, stderr, opened), r = self.in_phase(lambda: self.run_main(self.argv(root, sha, out, None, "--chunk", str(CHUNK),
                                                                                           "--write-size", str(WRITE))))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(opened, [False, True])				# the probe never configures; the sender's transport does, once
        self.assertEqual(self.reserve(), self.data)
        doc = json.loads((out / "delivery.json").read_text())
        self.assertEqual((doc["tool"], doc["outcome"], doc["size"], doc["sha256"]), ("deliver_nat080", "delivered", SIZE, sha))
        self.assertEqual(doc["device"]["committed"], SIZE)
        self.assertEqual(doc["host_bytes_written"], SIZE)
        self.assertFalse((out / "delivery.json.tmp").exists())
        self.assertEqual(json.loads(stdout), {"outcome": "delivered", "committed": SIZE, "mb_per_s": doc["mb_per_s"]})
        ev = [e["event"] for e in read_journal(out / "delivery.jsonl")]
        self.assertEqual(ev[:2], ["start", "loaded"])
        self.assertEqual(ev[-1], "final")
        self.assertIn("ready", ev)
        start = read_journal(out / "delivery.jsonl")[0]
        self.assertEqual((start["pid"], start["size"], start["sha256"], start["root"]), (os.getpid(), SIZE, sha, str(root)))
        self.assertEqual(read_journal(out / "delivery.jsonl")[1]["bytes"], SIZE)
        self.assertEqual(read_journal(out / "delivery.jsonl")[-1]["outcome"], "delivered")

    def test_the_wrong_file_is_refused_before_anything_is_opened(self):
        root, sha = self.make_root()
        other = hashlib.sha256(b"other").hexdigest()
        cases = (("wrong hash", self.argv(root, other, self.tmp / "o1")),
                 ("wrong size", self.argv(root, sha, self.tmp / "o2", SIZE + 16 * KIB)),
                 ("short size", self.argv(root, sha, self.tmp / "o3", SIZE - 16 * KIB)))
        for name, argv in cases:
            code, stdout, stderr, opened = self.run_main(argv)
            self.assertEqual(code, 2, name)
            self.assertIn("refused", stderr, name)
            self.assertEqual(opened, [], name)
            self.assertFalse(Path(argv[argv.index("--out") + 1]).exists(), name)		# no record directory either

    def test_a_size_that_is_not_a_multiple_of_16_KiB_is_refused(self):
        data = E.blob(SIZE - 512, 14)
        root, sha = self.make_root(data)
        code, stdout, stderr, opened = self.run_main(self.argv(root, sha, self.tmp / "o", len(data)))
        self.assertEqual(code, 2)
        self.assertIn("16 KiB", stderr)
        self.assertEqual(opened, [])
        self.assertFalse((self.tmp / "o").exists())

    def test_an_existing_output_directory_is_refused_and_left_alone(self):
        root, sha = self.make_root()
        out = self.tmp / "out"
        out.mkdir()
        (out / "keep").write_text("x")
        code, stdout, stderr, opened = self.run_main(self.argv(root, sha, out))
        self.assertEqual(code, 2)
        self.assertIn("already exists", stderr)
        self.assertEqual(opened, [])
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["keep"])

    def test_required_arguments(self):
        root, sha = self.make_root()
        for drop in ("--root", "--size", "--sha256", "--out"):
            argv = self.argv(root, sha, self.tmp / "o")
            i = argv.index(drop)
            del argv[i:i + 2]
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                D.main(argv)
            self.assertEqual(cm.exception.code, 2, drop)

    def test_each_outcome_has_its_own_exit_status(self):
        root, sha = self.make_root()
        expected = {"delivered": 0, "failed": 1, "cap-reached": 3, "never-ready": 4, "refused-by-device": 5}
        self.assertEqual(D.EXIT, dict(expected, refused=2))
        for i, (outcome, code) in enumerate(expected.items()):
            out = self.tmp / ("out%d" % i)
            got, stdout, stderr, opened = self.run_main(self.argv(root, sha, out),
                                                        deliver=lambda *a, **k: (outcome, {"error": "x", "device": {"committed": 7}}))
            self.assertEqual(got, code, outcome)
            doc = json.loads((out / "delivery.json").read_text())
            self.assertEqual((doc["outcome"], doc["error"]), (outcome, "x"))
            self.assertEqual(json.loads(stdout)["committed"], 7)
            last = read_journal(out / "delivery.jsonl")[-1]
            self.assertEqual((last["event"], last["outcome"]), ("final", outcome))

    def test_an_outcome_nobody_knows_is_a_failure(self):
        root, sha = self.make_root()
        got, _, _, _ = self.run_main(self.argv(root, sha, self.tmp / "o"), deliver=lambda *a, **k: ("surprise", {}))
        self.assertEqual(got, 1)

    def test_a_defect_in_the_tool_still_leaves_a_record(self):
        root, sha = self.make_root()
        out = self.tmp / "out"

        def boom(*a, **k):
            raise ValueError("No backend available")

        got, stdout, _, _ = self.run_main(self.argv(root, sha, out), deliver=boom)
        self.assertEqual(got, 1)
        doc = json.loads((out / "delivery.json").read_text())
        self.assertEqual((doc["outcome"], doc["error"]), ("failed", "ValueError: No backend available"))
        self.assertEqual(read_journal(out / "delivery.jsonl")[-1]["outcome"], "failed")
        self.assertIsNone(json.loads(stdout)["committed"])

    def test_the_options_reach_deliver(self):
        root, sha = self.make_root()
        seen = {}

        def spy(rs_, data, open_probe, open_send, journal, wait_s, deliver_s, chunk, write_size, progress_bytes, *rest, **kw):
            seen.update(wait_s=wait_s, deliver_s=deliver_s, chunk=chunk, write_size=write_size, progress_bytes=progress_bytes, n=len(data))
            return "delivered", {}

        self.run_main(self.argv(root, sha, self.tmp / "a"), deliver=spy)
        self.assertEqual(seen, dict(wait_s=300.0, deliver_s=225.0, chunk=8 << 20, write_size=256 << 10, progress_bytes=64 << 20, n=SIZE))
        self.run_main(self.argv(root, sha, self.tmp / "b", None, "--wait-s", "7", "--deliver-s", "9", "--chunk", "1024", "--write-size", "512",
                                "--progress-bytes", "2048"), deliver=spy)
        self.assertEqual(seen, dict(wait_s=7.0, deliver_s=9.0, chunk=1024, write_size=512, progress_bytes=2048, n=SIZE))


class Numbers(Case):
    """The values in the record, with a clock that does not start at zero and steps that do not round on their own."""
    STEP = Fraction(123457, 1000000)						# 0.123457 s per look

    def start_at(self, t):
        self.clock.now = Fraction(t)

    def step_sleep(self, s):
        self.clock.now += self.STEP

    def test_the_wait_is_counted_from_the_first_look_whatever_the_clock_says(self):
        self.start_at(1000)
        outcome, summary = self.run_deliver(wait_s=2.6)
        self.assertEqual((outcome, summary["waited_s"]), ("never-ready", 2.6))
        self.assertEqual(self.opened.count("probe"), 14)
        self.assertEqual([e["waited_s"] for e in self.events("waiting")], [0.0, 2.0])

    def test_waits_are_rounded_to_milliseconds(self):
        self.start_at(1000)
        outcome, summary = self.run_deliver(wait_s=3.0, sleep=self.step_sleep)
        # looks at k * 0.123457 s: the first beat after the one at 0 is the first look at or past 2 s (k = 17: 2.098769 s); the wait ends at k = 25: 3.086425 s
        self.assertEqual(outcome, "never-ready")
        self.assertEqual([e["waited_s"] for e in self.events("waiting")], [0.0, 2.099])
        self.assertEqual(summary["waited_s"], 3.086)

    def test_the_ready_record_has_the_wait_rounded_to_milliseconds(self):
        self.start_at(1000)
        replies = [self.placeholder_reply] * 3

        def probe():
            live = self.rig.t

            class T(rs.Transport):
                def get_rx(self_):
                    return replies.pop(0) if replies else live.get_rx()

            return T()

        self.in_phase(lambda: self.run_deliver(open_probe=probe, wait_s=60, sleep=self.step_sleep))
        self.assertEqual([e["waited_s"] for e in self.events("ready")], [0.37])		# 3 x 0.123457 = 0.370371

    def test_the_summary_seconds_are_the_senders_time_rounded_to_milliseconds(self):
        self.start_at(1000)

        def a_little_more(n):
            if n == 1:
                self.clock.now += Fraction(1, 10000)

        got, _ = self.in_phase(lambda: self.run_deliver(per_write=0.5, before_write=a_little_more))
        self.assertEqual(got[0], "delivered")
        self.assertEqual(got[1]["seconds"], 4.0)					# 8 x 0.5 s + 0.0001 s

    def test_rates_are_rounded_to_milliseconds(self):
        got, _ = self.in_phase(lambda: self.run_deliver(per_write=0.375))		# 8 writes: 3.0 s
        self.assertEqual((got[1]["seconds"], got[1]["mb_per_s"], got[1]["mib_per_s"]), (3.0, 0.175, 0.167))		# 524288 / 3 = 174762.7 B/s

    def test_a_transfer_shorter_than_a_second_has_its_rate(self):
        got, _ = self.in_phase(lambda: self.run_deliver(per_write=0.0625))		# 8 writes: 0.5 s
        self.assertEqual((got[1]["seconds"], got[1]["mb_per_s"], got[1]["mib_per_s"]), (0.5, 1.049, 1.0))

    def test_a_transfer_that_took_no_time_has_no_rate_and_no_error(self):
        got, _ = self.in_phase(lambda: self.run_deliver(per_write=0))
        self.assertEqual(got[0], "delivered")
        self.assertEqual((got[1]["seconds"], got[1]["mb_per_s"], got[1]["mib_per_s"]), (0.0, None, None))

    def run_stub(self, send):
        """deliver() with `send` standing in for the sender; the sender's transport counts the aborts it is asked for."""
        ns = types.SimpleNamespace(**vars(rs))
        ns.send = send

        class Counting(ClockedTransport):
            aborts = 0

            def rx_abort(self_):
                self_.aborts += 1
                return super().rx_abort()

        self.counting = Counting(self.rig.t, self.clock, 0.5, None)
        return self.in_phase(lambda: D.deliver(ns, self.data, lambda: self.rig.t, lambda: self.counting, self.journal, 60, 1000, CHUNK, WRITE, 2 * CHUNK,
                                               mono=self.clock.mono, sleep=self.clock.sleep))

    def test_a_failure_after_time_with_nothing_committed_has_no_rate(self):
        def send(transport, data, **kw):
            self.clock.advance(2)
            raise rs.RootSendError("nothing went through")

        (outcome, summary), _ = self.run_stub(send)
        self.assertEqual((outcome, summary["seconds"], summary["device"]["committed"]), ("failed", 2.0, 0))
        self.assertEqual((summary["mb_per_s"], summary["mib_per_s"]), (None, None))

    def test_an_idle_device_is_not_aborted_after_a_failure(self):
        def send(transport, data, **kw):
            raise rs.RootSendError("nothing went through")

        self.run_stub(send)
        self.assertEqual(self.counting.aborts, 0)

    def test_an_armed_device_is_aborted_after_a_failure_and_the_view_is_read_again(self):
        def send(transport, data, **kw):
            transport.rx_begin(0, CHUNK)					# armed, then the sender gives up
            raise rs.RootSendError("gave up")

        (outcome, summary), _ = self.run_stub(send)
        self.assertEqual((outcome, self.counting.aborts, summary["device"]["state"], summary["device"]["rx_aborts"]), ("failed", 1, 0, 1))

    def test_a_delivery_is_never_followed_by_an_abort(self):
        def send(transport, data, **kw):
            transport.rx_begin(0, CHUNK)					# the sender returns with a chunk armed: not a state this tool ends on a success
            return dict(committed=0)

        (outcome, summary), _ = self.run_stub(send)
        self.assertEqual((outcome, self.counting.aborts), ("delivered", 0))
        self.assertEqual(summary["device"]["state"], 1, "the device's own view is reported as it is")


class MainRecord(Case):
    """What main() leaves on disk, with the clocks it reads replaced."""

    make_root = Main.make_root
    run_main = Main.run_main
    argv = Main.argv

    def run_fake(self, **patches):
        root, sha = self.make_root()
        out = self.tmp / "out"
        made = []

        class J(D.Journal):
            def __init__(self_, *a, **kw):
                super().__init__(*a, **kw)
                made.append(self_)

        real_mono, real_time = D.time.monotonic, D.time.time
        mono_seq, time_seq = [10.0, 11.23456], [1700000000.123456]
        with mock.patch.object(D, "Journal", J), \
                mock.patch.object(D.time, "monotonic", lambda: mono_seq.pop(0) if mono_seq else real_mono()), \
                mock.patch.object(D.time, "time", lambda: time_seq.pop(0) if time_seq else real_time()):
            code, stdout, stderr, _ = self.run_main(self.argv(root, sha, out), deliver=lambda *a, **kw: ("delivered", dict(device=dict(committed=5), mb_per_s=1.5)))
        self.assertEqual(code, 0, stderr)
        return out, made

    def test_the_record_carries_the_load_time_and_the_start_time_rounded_to_milliseconds(self):
        out, _ = self.run_fake()
        loaded = [e for e in read_journal(out / "delivery.jsonl") if e["event"] == "loaded"][0]
        self.assertEqual(loaded["seconds"], 1.235)				# 11.23456 - 10.0
        doc = json.loads((out / "delivery.json").read_text())
        self.assertEqual(doc["started_unix"], 1700000000.123)

    def test_the_summary_is_indented_by_one_space_and_sorted(self):
        out, _ = self.run_fake()
        text = (out / "delivery.json").read_text()
        self.assertTrue(text.startswith('{\n "'), text[:20])
        keys = [l.split('"')[1] for l in text.splitlines() if l.startswith(' "')]
        self.assertEqual(keys, sorted(keys))
        self.assertTrue(text.endswith("}\n"))

    def test_the_journal_is_closed_when_main_returns(self):
        _out, made = self.run_fake()
        self.assertEqual(len(made), 1)
        self.assertTrue(made[0].f.closed)


class SelfTest(unittest.TestCase):
    def run_selftest(self, modules):
        out = io.StringIO()
        names = ["usb", "usb.core", "usb.backend", "usb.backend.libusb1"]
        saved = {n: sys.modules.get(n, KeyError) for n in names}
        try:
            for n in names:
                sys.modules.pop(n, None)
            sys.modules.update(modules)
            with contextlib.redirect_stdout(out):
                code = D.selftest()
        finally:
            for n, m in saved.items():
                if m is KeyError:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m
        return code, json.loads(out.getvalue())

    def fake_usb(self, backend):
        usb = types.ModuleType("usb")
        core = types.ModuleType("usb.core")
        core.find = lambda **kw: iter([])
        be = types.ModuleType("usb.backend")
        lib = types.ModuleType("usb.backend.libusb1")
        lib.get_backend = lambda: backend
        usb.core, usb.backend, be.libusb1 = core, be, lib
        return {"usb": usb, "usb.core": core, "usb.backend": be, "usb.backend.libusb1": lib}

    def test_pyusb_and_a_libusb_backend_are_ok(self):
        code, res = self.run_selftest(self.fake_usb(object()))
        self.assertEqual((code, res["ok"], res["libusb_backend"], res["find_returns_list"]), (0, True, True, True))
        self.assertEqual(res["tool"], "deliver_nat080")

    def test_no_libusb_backend_is_not_ok(self):
        code, res = self.run_selftest(self.fake_usb(None))
        self.assertEqual((code, res["ok"], res["libusb_backend"]), (2, False, False))

    def test_no_pyusb_is_not_ok(self):
        code, res = self.run_selftest({"usb": None, "usb.core": None, "usb.backend": None, "usb.backend.libusb1": None})
        self.assertEqual((code, res["ok"]), (2, False))
        self.assertTrue(res["error"].startswith(("ImportError", "ModuleNotFoundError")), res["error"])

    def test_the_selftest_opens_no_device_and_the_main_flag_runs_it(self):
        mods = self.fake_usb(object())
        finds = []
        mods["usb.core"].find = lambda **kw: finds.append(kw) or iter([])
        out = io.StringIO()
        saved = {n: sys.modules.get(n) for n in mods}
        try:
            sys.modules.update(mods)
            with contextlib.redirect_stdout(out):
                code = D.main(["--selftest"])
        finally:
            for n, m in saved.items():
                if m is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m
        self.assertEqual(code, 0)
        self.assertEqual(finds, [dict(find_all=True, idVendor=0x1209, idProduct=0x0001)])		# the NAT-041 monitor device, never Samsung's 04e8


class Constants(unittest.TestCase):
    def test_the_values_the_driver_and_the_loader_rely_on(self):
        self.assertEqual(D.PLACEHOLDER, 512)				# docs/procedures/nat-079: nat079 hold block
        self.assertEqual(D.MIB, 1 << 20)
        self.assertEqual(D.HEARTBEAT_S, 2.0)
        self.assertEqual(D.SENDER, ROOT / "tools/ios/root_send.py")
        self.assertTrue(D.SENDER.is_file())
        self.assertEqual(rs.VID, 0x1209)				# never Samsung's 0x04e8
        self.assertEqual(rs.PID, 0x0001)

    def test_the_sender_module_loads_by_path_without_pyusb(self):
        mod = D.load_sender()
        self.assertEqual(mod.RX_SIZE, 120)
        self.assertTrue(hasattr(mod, "send"))
        self.assertIs(sys.modules["nat080_root_send"], mod)


if __name__ == "__main__":
    unittest.main(verbosity=1)
