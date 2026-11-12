#!/usr/bin/env python3
"""NAT-080: the NAT-041 collector and the delivery companion's sender on one model device (host-test).

Evidence kind: host-test. The device is the NAT-076 DWC3 model with the engine the NAT-079 loader runs; the "USB stack" is a Python adapter that
forwards control transfers to the model. What this shows is that the protocols do not get in each other's way: the real collector
(docs/procedures/nat-041/s24_logd.py, unmodified) keeps following the device's log through endpoint-0 vendor requests 0x01-0x05 while the
companion (deliver_nat080.deliver with the real tools/ios/root_send.py sender) streams the image over bulk-OUT, and a bus reset in the middle of
a chunk is survived by the sender's reconnect and resume without the collector losing its run.

What it does not show: libusb. A real pyusb sender claims the interface and calls set_configuration (and may reset the device); whether libusb
lets another process keep issuing control transfers on endpoint 0 at that moment is a property of the host stack that is measured only on the
real device. The model has no notion of an interface claim, so the "no EBUSY" part of the claim is limited to what the adapter can show: the
collector's backend interface (control_in/control_out) cannot claim, configure or reset, and every transfer it made returned ok.

The model is one C state machine, so the two actors take strict turns (the sender hands the bus to the collector at each point where it would
write, the collector runs until its next idle sleep and hands it back). The order of events is the same on every run.
"""
import base64
import json
import struct
import sys
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import importlib.util  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


TD = load("nat080_coexist_td", HERE / "test_deliver80.py")
E, D, rs, M = TD.E, TD.D, TD.rs, TD.M
L = load("nat080_coexist_logd", TD.ROOT / "docs/procedures/nat-041/s24_logd.py")
P = L.P
SIZE, WRITE, CHUNK = TD.SIZE, TD.WRITE, TD.CHUNK
COLLECTOR_REQUESTS = {(0xC0, P.REQ_GET_INFO), (0xC0, P.REQ_READ_RING), (0xC0, P.REQ_GET_EXC), (0x40, P.REQ_SET_NONCE), (0xC0, P.REQ_PEEK)}


def tearDownModule():
    TD.tearDownModule()


class Bus:
    """The collector's backend over the model's endpoint 0, and the turn-taking between it and the sender."""

    TURN_S = 30

    def __init__(self, rig, out):
        self.rig = rig
        self.requests = []				# (bmRequestType, bRequest) of every transfer the collector made
        self.queries = 0
        self.now = 100.0
        self.over = False
        self.error = None
        self.finished = False
        self.stop = None
        self.steps = 0
        self.per_turn = []				# collector transfers made in each of its turns
        self.manifest = None
        self.out = Path(out)
        self.turn_c = threading.Semaphore(0)
        self.turn_s = threading.Semaphore(0)
        self.archive = L.A.Archive(self.out, "ep0-monitor", "synthetic")
        self.transfers = L.A.create(self.out / "usb-transfers.jsonl")
        self.col = L.Collector(self, self.archive, self.transfers, rng=lambda n: bytes([0x21]) * n, clock=self.clock, sleep=self.idle,
                               interval=0.02, wait_interval=0.1, dead_after=5.0, grace=2.0, io_timeout_ms=100)
        self.thread = threading.Thread(target=self.body, daemon=True)
        self.thread.start()

    # -- the backend the collector sees
    def find(self, vid, pid):
        self.queries += 1
        return [Dev(self)]

    def xfer(self, bm, req, value, index, length, data):
        self.requests.append((bm, req))
        rc, got = self.rig.m.ctrl(bm, req, value, index, length, data)
        if rc == M.H_STALL:
            raise L.UsbStall("stall")
        if rc != M.H_OK:
            raise L.UsbTimeout(M.RC_NAMES.get(rc, str(rc)))
        return got if bm & 0x80 else len(data)

    # -- the collector's clock and idle sleep: its turn ends when it has nothing to read
    def clock(self):
        return self.now + (10000.0 if self.over else 0.0)

    def idle(self, dt):
        self.now += dt
        self.turn_s.release()
        self.wait(self.turn_c)

    def wait(self, sem):
        if not sem.acquire(timeout=self.TURN_S):
            raise AssertionError("the other actor did not hand the bus back")

    def body(self):
        try:
            self.wait(self.turn_c)
            if self.over:						# the test ended before the collector was ever given a turn
                return
            self.stop = self.col.run(1000.0, 1 << 20)
        except BaseException as e:				# reported to the sender at its next turn
            self.error = e
        self.finished = True
        self.turn_s.release()

    # -- the sender's side
    def step(self):
        """Give the bus to the collector for one cycle (until its next idle sleep)."""
        if self.finished:
            return
        self.steps += 1
        before = len(self.requests)
        self.turn_c.release()
        self.wait(self.turn_s)
        self.per_turn.append(len(self.requests) - before)
        if self.error is not None:
            raise self.error

    def finish(self):
        """The delivery is over: the collector's deadline passes, it drains the device and ends its run."""
        self.over = True
        self.step()
        self.thread.join(self.TURN_S)
        if self.thread.is_alive():
            raise AssertionError("the collector did not stop")
        self.transfers.close()
        self.manifest = L.finish_archive(self.archive, self.stop, self.col.stats, self.out)


class Dev:
    def __init__(self, bus):
        self.bus = bus
        self.info = dict(vid=P.VID, pid=P.PID, bus=1, address=7)

    def control_in(self, req, value, index, length, timeout_ms):
        return self.bus.xfer(0xC0, req, value, index, length, b"")

    def control_out(self, req, value, index, data, timeout_ms):
        return self.bus.xfer(0x40, req, value, index, len(data), bytes(data))

    def close(self):
        pass


def rows(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


class Coexisting(TD.Case):
    def setUp(self):
        super().setUp()
        self.bus = Bus(self.rig, self.tmp / "collector")
        self.addCleanup(self.cleanup_bus)

    def cleanup_bus(self):
        self.bus.over = True
        self.bus.turn_c.release()					# a thread still waiting for its turn must end, not hang the process
        self.bus.thread.join(5)

    def deliver_with_collector(self, before_write=None, sleep_steps=True, **kw):
        bus = self.bus

        def hook(n):
            if before_write:
                before_write(n)
            bus.step()

        def sleep(s):
            self.clock.sleep(s)
            if sleep_steps:
                bus.step()

        def host():
            try:
                return self.run_deliver(before_write=hook, sleep=sleep, **kw)
            finally:
                bus.finish()

        got, r = self.in_phase(host)
        return got[0], got[1], r

    def collector_frames(self):
        dirs = sorted((self.bus.out / "boots").iterdir())
        self.assertEqual(len(dirs), 1)
        return dirs[0], [r["frame"] for r in rows(dirs[0] / "frames.jsonl")]

    def texts(self, frames):
        return [f["text"] for f in frames if f["kind"] == "log" and f.get("dev_kind") == "text"]

    def test_the_collector_follows_the_log_while_the_image_goes_through_bulk_out(self):
        def write_text(n):
            if n in (2, 5, 8):
                self.rig.m.text("coexist before write %d" % n)

        outcome, summary, r = self.deliver_with_collector(before_write=write_text)
        self.assertEqual(outcome, "delivered")
        self.assertEqual(r.status, E.DONE)
        self.assertEqual(self.reserve(), self.data)
        self.assertTrue(self.rig.untouched_outside_reserve())
        self.assertEqual(self.rig.m.violations(), [])
        self.assertEqual(summary["device"]["committed"], SIZE)
        # the collector: one run, from its first look to its drain, nothing lost, nothing it could not answer
        d, frames = self.collector_frames()
        self.assertEqual([t for t in self.texts(frames) if t.startswith("coexist")],
                         ["coexist before write 2", "coexist before write 5", "coexist before write 8"])
        self.assertEqual(frames[0]["kind"], "boot")
        self.assertEqual(frames[-1]["kind"], "end")
        self.assertEqual(frames[-1]["reason"], "collector-stop")
        self.assertEqual([f["seq"] for f in frames], list(range(len(frames))))
        self.assertNotIn("drop", [f["kind"] for f in frames])
        st = self.bus.col.stats
        self.assertEqual((st["sessions"], st["boots"], st["resets"], st["timeouts"], st["stalls"], st["start_failures"]), (1, 1, 0, 0, 0, 0))
        self.assertEqual(self.bus.stop, "deadline")
        self.assertEqual(self.bus.manifest["outcome"], "complete-received-stream")
        # the archive's payload is its frames' data in order; the records the device sent are, together, the device's ring byte for byte
        with open(d / "payload.bin", "rb") as f:
            kept = f.read()
        self.assertEqual(kept, b"".join(base64.b64decode(f["data_b64"]) for f in frames))
        bodies = [base64.b64decode(f["data_b64"]) for f in frames if "dev_seq" in f]
        self.assertGreater(len(bodies), 0)
        self.assertEqual(self.rig.m.oldest, 0)
        self.assertEqual(sum(P.REC_HDR + len(b) for b in bodies), self.rig.m.written)			# every byte of the device's stream is accounted for

    def test_the_collector_uses_endpoint_zero_vendor_requests_only_and_every_one_is_answered(self):
        self.deliver_with_collector()
        self.assertTrue(self.bus.requests)
        self.assertLessEqual(set(self.bus.requests), COLLECTOR_REQUESTS)
        self.assertEqual(self.bus.requests[0], (0xC0, P.REQ_GET_INFO))				# the resume check comes first
        self.assertEqual(self.bus.requests.count((0x40, P.REQ_SET_NONCE)), 1)			# the nonce is set once per run
        t = rows(self.bus.out / "usb-transfers.jsonl")
        self.assertEqual(len(t), len(self.bus.requests))
        self.assertEqual({row["result"] for row in t}, {"ok"})
        # none of the requests the sender makes (RX_BEGIN 6, GET_RX 7, RX_ABORT 8) is one the collector sends
        self.assertTrue({req for _, req in self.bus.requests}.isdisjoint({6, 7, 8}))

    def test_the_two_alternate_so_transfers_really_overlap_the_stream(self):
        # an armed or half-received chunk is on the bus whenever the collector takes its turn: before the odd writes a chunk has just been armed,
        # before the even ones half of it has been received
        seen = []

        def note(n):
            rx = self.rig.rx()
            seen.append((n, struct.unpack_from("<I", rx, TD.AT_STATE)[0], struct.unpack_from("<Q", rx, TD.AT_COMMITTED)[0]))

        self.deliver_with_collector(before_write=note)
        self.assertEqual(len(seen), SIZE // WRITE)
        self.assertEqual({s[1] for s in seen}, {1})					# ARMED at every one of them
        self.assertEqual([s[2] for s in seen], [(n // 2) * CHUNK for n in range(SIZE // WRITE)])
        self.assertGreaterEqual(self.bus.steps, SIZE // WRITE)
        self.assertEqual(len(self.bus.per_turn), self.bus.steps)
        self.assertGreaterEqual(min(self.bus.per_turn), 1)					# the collector transferred something in every turn it took

    def test_a_bus_reset_in_the_middle_of_a_chunk_is_survived_by_both(self):
        fired = []

        def reset_on_sixth(n):
            if n == 6 and not fired:
                fired.append(n)
                self.rig.m.text("coexist before the bus reset")
                self.rig.m.bus_reset()					# the cable is bumped between the first and second write of the third chunk

        outcome, summary, r = self.deliver_with_collector(before_write=reset_on_sixth)
        # the sender: reconnect and resume, the image arrives exactly
        self.assertEqual(outcome, "delivered")
        self.assertEqual(r.status, E.DONE)
        self.assertEqual(self.reserve(), self.data)
        self.assertEqual(self.xport.reconnects, 1)
        self.assertEqual(summary["sender"]["retries"], 1)
        self.assertGreaterEqual(summary["device"]["rx_resets"], 1)
        self.assertEqual(self.rig.m.violations(), [])
        # the collector: the same run before and after the reset, no timeout, no stall, the reset visible in what the device reports about itself
        d, frames = self.collector_frames()
        st = self.bus.col.stats
        self.assertEqual((st["sessions"], st["boots"], st["resets"], st["timeouts"], st["stalls"], st["start_failures"]), (1, 1, 0, 0, 0, 0))
        self.assertEqual(frames[-1]["reason"], "collector-stop")
        self.assertIn("coexist before the bus reset", self.texts(frames))
        info = json.loads(base64.b64decode(frames[-1]["data_b64"]))["last_info"]
        self.assertGreaterEqual(info["resets"], 1)
        self.assertEqual({row["result"] for row in rows(self.bus.out / "usb-transfers.jsonl")}, {"ok"})
        self.assertLessEqual(set(self.bus.requests), COLLECTOR_REQUESTS)

    def test_three_bus_resets_between_chunks_leave_one_collector_run(self):
        fired = set()

        def reset_between(n):
            if n in (3, 5, 7) and n not in fired:
                fired.add(n)
                self.rig.m.bus_reset()

        outcome, summary, r = self.deliver_with_collector(before_write=reset_between)
        self.assertEqual(outcome, "delivered")
        self.assertEqual(self.reserve(), self.data)
        self.assertEqual(self.xport.reconnects, 3)
        st = self.bus.col.stats
        self.assertEqual((st["sessions"], st["boots"], st["resets"], st["timeouts"], st["stalls"]), (1, 1, 0, 0, 0))
        d, frames = self.collector_frames()
        info = json.loads(base64.b64decode(frames[-1]["data_b64"]))["last_info"]
        self.assertGreaterEqual(info["resets"], 3)

    def test_polling_the_receive_state_in_the_wait_does_not_disturb_the_collector_or_the_transfer(self):
        replies = [self.placeholder_reply] * 4

        def probe():
            live = self.rig.t

            class T(rs.Transport):
                def get_rx(self):
                    return replies.pop(0) if replies else live.get_rx()

            return T()

        outcome, summary, r = self.deliver_with_collector(open_probe=probe, wait_s=60)
        self.assertEqual(outcome, "delivered")
        self.assertEqual(self.reserve(), self.data)
        self.assertEqual(self.events("ready")[0]["waited_s"], 0.8)				# four 0.2 s sleeps, each of them a collector turn
        self.assertGreaterEqual(self.bus.steps, 4)
        st = self.bus.col.stats
        self.assertEqual((st["sessions"], st["boots"], st["resets"], st["timeouts"], st["stalls"]), (1, 1, 0, 0, 0))

    def test_the_collector_reads_the_receive_engines_log_too(self):
        # the loader's own lines (here a text the engine takes while a chunk is armed) reach the host archive, as they must for the analyser
        def during(n):
            if n == 4:
                self.rig.m.stage(7, "chunk armed")

        self.deliver_with_collector(before_write=during)
        d, frames = self.collector_frames()
        stages = [f for f in frames if f["kind"] == "stage"]
        self.assertEqual([(f["stage"], f["text"]) for f in stages], [(7, "chunk armed")])


if __name__ == "__main__":
    unittest.main()
