#!/usr/bin/env python3
"""Host tests of the NAT-041 collector (s24_logd.py) against the DWC3 host model and the real NAT-016 archive.

Evidence kind: host-test. The "device" is the engine compiled into the model of model/model.c; the "USB stack" is a fake
backend that forwards vendor control transfers to the model, so these tests show that the collector, the wire protocol and
the archive agree with each other, not how libusb or the S24's controller behave.
"""
import base64
import json
import os
import pathlib
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modelhost as M  # noqa: E402
import s24_logd as L  # noqa: E402
import usbmon_proto as P  # noqa: E402

A = L.A
_TMP = tempfile.mkdtemp(prefix="nat041-logd-")
_LIB = None


def lib():
    global _LIB
    if _LIB is None:
        _LIB = M.build(out_dir=_TMP)
    return _LIB


def read_rows(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


class Rig:
    """One simulated phone + host: the model machine, a fake clock and the collector writing into a fresh archive."""

    BOOT_A = b"BOOT-A-0123456789"[:16]
    BOOT_B = b"BOOT-B-0123456789"[:16]

    def __init__(self, tc, ring_size=4096, boot_id=None, plugged=True, **colkw):
        self.tc = tc
        self.boot_id = boot_id or self.BOOT_A
        self.m = M.Machine(lib(), ring_size=ring_size, boot_id=self.boot_id)
        tc.assertEqual(self.m.init_rc, 0)
        tc.addCleanup(self.m.close)
        self.now = 100.0
        self.plugged = False
        self.pending_plug = None
        self.reset_on_plug = None
        self.hook = None
        self.ntransfer = 0
        self.fail = 0              # next n control transfers time out
        self.fail_forever = False
        self.queries = []
        self.rng_calls = 0
        self.reply_filter = None   # (req, data) -> data
        self.swallow_out = False
        self.out = pathlib.Path(tempfile.mkdtemp(prefix="logd-", dir=_TMP)) / "attempt"
        self.archive = A.Archive(self.out, "ep0-monitor", "synthetic")
        self.transfers = A.create(self.out / "usb-transfers.jsonl")
        kw = dict(interval=0.02, wait_interval=0.1, dead_after=5.0, grace=2.0, io_timeout_ms=100)
        kw.update(colkw)
        self.col = L.Collector(self, self.archive, self.transfers, rng=self.rng, clock=lambda: self.now,
                               sleep=self.sleep, **kw)
        if plugged:
            self.plug()

    # -- the simulated bus and backend
    def rng(self, n):
        self.rng_calls += 1
        return bytes([0x10 + self.rng_calls]) * n

    def nonce(self, k):
        return bytes([0x10 + k]) * P.NONCE_LEN

    def sleep(self, dt):
        self.now += dt

    def plug(self):
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.tc.assertEqual(rc, M.H_OK, name)
        self.plugged = True

    def unplug(self):
        self.m.detach()
        self.plugged = False

    def reset_device(self, boot_id):
        """The phone restarts the monitor (a new run) without the cable being touched."""
        self.boot_id = boot_id
        self.m.lib.t_new(self.m.ring_size)          # power-on state: new controller, new engine memory
        self.tc.assertEqual(self.m.init(boot_id=boot_id), 0)
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.tc.assertEqual(rc, M.H_OK, name)

    def find(self, vid, pid):
        self.queries.append((vid, pid))
        if self.pending_plug is not None and self.now >= self.pending_plug:
            self.pending_plug = None
            if self.reset_on_plug:
                self.reset_device(self.reset_on_plug)       # the phone restarted while the cable was out
                self.plugged = True
            else:
                self.plug()
        return [RigDevice(self)] if self.plugged else []

    def xfer(self, bm, req, value, index, length, data, timeout_ms):
        self.ntransfer += 1
        if not (0 <= value <= 0xFFFF and 0 <= index <= 0xFFFF and 0 <= length <= 0xFFFF):
            raise AssertionError("wValue/wIndex/wLength do not fit 16 bits: %#x %#x %#x" % (value, index, length))
        if self.hook:
            self.hook(self, self.ntransfer)
        if not self.plugged:
            raise L.UsbGone("no device")
        if self.fail_forever or self.fail > 0:
            self.fail = max(0, self.fail - 1)
            self.now += timeout_ms / 1000.0
            raise L.UsbTimeout("injected")
        self.now += 0.002
        if not (bm & 0x80) and self.swallow_out:
            return len(data)
        rc, got = self.m.ctrl(bm, req, value, index, length, data)
        if rc == M.H_STALL:
            raise L.UsbStall("stall")
        if rc != M.H_OK:
            self.now += timeout_ms / 1000.0
            raise L.UsbTimeout(M.RC_NAMES.get(rc, str(rc)))
        if bm & 0x80:
            return self.reply_filter(req, got) if self.reply_filter else got
        return len(data)

    # -- running and reading results
    def go(self, seconds=1.0, max_bytes=1 << 24):
        self.stop = self.col.run(seconds, max_bytes)
        self.transfers.close()
        self.manifest = L.finish_archive(self.archive, self.stop, self.col.stats, self.out)
        return self.stop

    def boot_dirs(self):
        return sorted((self.out / "boots").iterdir()) if (self.out / "boots").exists() else []

    def frames(self, d):
        return [r["frame"] for r in read_rows(d / "frames.jsonl")]

    def payload(self, d):
        with open(d / "payload.bin", "rb") as f:
            return f.read()

    def events(self):
        return read_rows(self.out / "events.jsonl")

    def errors(self):
        return [e for e in self.events() if e["kind"] == "capture-error"]

    def transfer_rows(self):
        return read_rows(self.out / "usb-transfers.jsonl")


class RigDevice:
    def __init__(self, rig):
        self.rig = rig
        self.info = dict(vid=P.VID, pid=P.PID, bus=1, address=7)

    def control_in(self, req, value, index, length, timeout_ms):
        return self.rig.xfer(0xC0, req, value, index, length, b"", timeout_ms)

    def control_out(self, req, value, index, data, timeout_ms):
        return self.rig.xfer(0x40, req, value, index, len(data), bytes(data), timeout_ms)

    def close(self):
        pass


def alter_info(data, boot_id=None, written=None):
    """A GET_INFO reply with the device boot block and/or the stream length replaced (INFO_FMT offsets 16 and 56)."""
    b = bytearray(data)
    if boot_id is not None:
        b[16:32] = boot_id
    if written is not None:
        b[56:64] = struct.pack("<Q", written)
    return bytes(b)


def texts(frames):
    return [f["text"] for f in frames if f["kind"] == "log" and f.get("dev_kind") == "text"]


def kinds(frames):
    return [f["kind"] for f in frames]


class CaptureTests(unittest.TestCase):
    def test_unattended_capture_of_a_running_device(self):
        r = Rig(self)
        for i in range(3):
            r.m.text("early %d" % i)
        r.m.stage(1, "loader up")

        def hook(rig, n):
            if n in (6, 12, 18):
                rig.m.text("live %d" % n)
        r.hook = hook
        self.assertEqual(r.go(1.0), "deadline")
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 1)
        fr = r.frames(dirs[0])
        self.assertEqual(fr[0]["kind"], "boot")
        self.assertEqual(fr[0]["seq"], 0)
        self.assertEqual(fr[0]["boot_id"], r.nonce(1).hex() + "-" + Rig.BOOT_A.hex())
        self.assertEqual([f["seq"] for f in fr], list(range(len(fr))))
        self.assertEqual(texts(fr), ["early 0", "early 1", "early 2", "live 6", "live 12", "live 18"])
        stages = [f for f in fr if f["kind"] == "stage"]
        self.assertEqual([(f["stage"], f["text"]) for f in stages], [(1, "loader up")])
        self.assertEqual(fr[-1]["kind"], "end")
        self.assertEqual(fr[-1]["reason"], "collector-stop")
        self.assertEqual(r.payload(dirs[0]), b"".join(base64.b64decode(f["data_b64"]) for f in fr))
        self.assertEqual(r.m.violations(), [])
        self.assertEqual(r.manifest["outcome"], "complete-received-stream", r.errors())
        self.assertEqual(r.errors(), [])

    def test_the_nonce_is_sent_before_anything_is_read_from_a_new_device(self):
        r = Rig(self)
        r.go(0.3)
        rows = r.transfer_rows()
        self.assertEqual((rows[0]["dir"], rows[0]["req"]), ("in", P.REQ_GET_INFO))      # resume check
        self.assertEqual((rows[1]["dir"], rows[1]["req"]), ("out", P.REQ_SET_NONCE))
        self.assertEqual(base64.b64decode(rows[1]["data_b64"]), r.nonce(1))
        self.assertEqual((rows[2]["dir"], rows[2]["req"]), ("in", P.REQ_GET_INFO))
        self.assertNotIn(P.REQ_READ_RING, [x["req"] for x in rows[:2]])

    def test_the_collector_waits_for_a_device_that_appears_later(self):
        r = Rig(self, plugged=False)
        r.m.text("logged before the cable went in")
        r.pending_plug = r.now + 0.35
        r.go(1.5)
        self.assertGreaterEqual(len(r.queries), 4)
        self.assertEqual(set(r.queries), {(P.VID, P.PID)})
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 1)
        self.assertEqual(texts(r.frames(dirs[0])), ["logged before the cable went in"])
        self.assertEqual(r.errors(), [])

    def test_steady_logging_through_many_ring_wraps_loses_nothing(self):
        r = Rig(self, ring_size=2112)
        sent = []

        def hook(rig, n):
            if n > 3 and n % 2 == 0 and len(sent) < 600:
                line = "line %03d %s" % (len(sent), "x" * (len(sent) % 17))
                sent.append(line)
                rig.m.text(line)
        r.hook = hook
        r.go(8.0)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(len(sent), 600)
        self.assertEqual(texts(fr), sent)
        self.assertNotIn("drop", kinds(fr))
        self.assertGreater(r.m.written, 4 * 2112)
        self.assertEqual(r.m.violations(), [])
        self.assertEqual(r.manifest["outcome"], "complete-received-stream", r.errors())

    def test_offsets_across_the_32_bit_boundary(self):
        r = Rig(self, ring_size=2112)
        r.m.lib.t_set_stream_base(0xFFFFF000)
        sent = ["wrap %03d %s" % (i, "z" * 12) for i in range(400)]
        it = iter(sent)

        def hook(rig, n):
            if n > 3 and n % 2 == 0:
                s = next(it, None)
                if s:
                    rig.m.text(s)
        r.hook = hook
        r.go(8.0)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(texts(fr), sent)
        end = fr[-1]
        self.assertEqual(end["kind"], "end")
        self.assertGreater(json.loads(base64.b64decode(end["data_b64"]))["next_offset"], 0xFFFFFFFF)
        drops = [f for f in fr if f["kind"] == "drop"]
        self.assertEqual([(d["reason"], json.loads(base64.b64decode(d["data_b64"]))["lost_bytes"]) for d in drops],
                         [("lost-before-connect", 0xFFFFF000)])

    def test_stage_and_text_records_keep_their_device_sequence(self):
        r = Rig(self)
        r.m.text("a")
        r.m.stage(7, "seven")
        r.m.text("b")
        r.go(0.4)
        fr = [f for f in r.frames(r.boot_dirs()[0]) if "dev_seq" in f]
        self.assertEqual([f["dev_seq"] for f in fr], [0, 1, 2])
        self.assertEqual([f["dev_kind"] for f in fr], ["text", "stage", "text"])


class ExceptionTests(unittest.TestCase):
    def test_an_exception_frame_is_fetched_and_the_device_keeps_serving(self):
        r = Rig(self)
        regs = [0x1111111100000000 + i for i in range(31)]

        def hook(rig, n):
            if n == 8:
                rig.m.fault(esr=0x96000045, elr=0xFFFFFFF007004000, far=0x1000, x=regs)
            if n == 20:
                rig.m.text("still alive after the fault")
        r.hook = hook
        r.m.stage(3, "about to fault")
        r.go(1.0)
        fr = r.frames(r.boot_dirs()[0])
        rec = [f for f in fr if f["kind"] == "fault" and f.get("dev_kind") == "fault"]
        exc = [f for f in fr if f["kind"] == "fault" and f.get("source") == "get_exc"]
        self.assertEqual(len(rec), 1)
        self.assertEqual((rec[0]["esr"], rec[0]["elr"], rec[0]["far"], rec[0]["stage"]),
                         (0x96000045, 0xFFFFFFF007004000, 0x1000, 3))
        self.assertEqual(len(exc), 1)
        e = exc[0]
        self.assertEqual((e["esr"], e["elr"], e["far"], e["spsr"], e["valid"], e["stage"], e["count"]),
                         (0x96000045, 0xFFFFFFF007004000, 0x1000, 0x3C5, 1, 3, 1))
        self.assertEqual(e["x"], regs)
        raw = base64.b64decode(e["data_b64"])
        self.assertEqual(len(raw), P.EXC_SIZE)
        self.assertEqual(P.parse_exc(raw)["x"], regs)
        self.assertIn("still alive after the fault", texts(fr))
        self.assertEqual(r.manifest["outcome"], "complete-received-stream", r.errors())

    def test_a_second_fault_is_reported_again_with_the_first_frame_kept(self):
        r = Rig(self)

        def hook(rig, n):
            if n == 8:
                rig.m.fault(esr=1)
            if n == 20:
                rig.m.fault(esr=2)
        r.hook = hook
        r.go(1.0)
        exc = [f for f in r.frames(r.boot_dirs()[0]) if f["kind"] == "fault" and f.get("source") == "get_exc"]
        self.assertEqual([(f["esr"], f["count"]) for f in exc], [(1, 1), (1, 2)])


class LossAndDamageTests(unittest.TestCase):
    def test_ring_overrun_between_polls_is_a_counted_drop_and_the_rest_is_exact(self):
        r = Rig(self, ring_size=2112)
        state = {}

        def hook(rig, n):
            if n == 6:
                state["written_before"] = rig.m.written
                for i in range(80):
                    rig.m.text("burst %02d ................" % i)
                state["oldest_after"] = rig.m.oldest
        r.hook = hook
        r.go(1.0)
        fr = r.frames(r.boot_dirs()[0])
        drops = [f for f in fr if f["kind"] == "drop" and f["reason"] == "ring-overrun"]
        self.assertEqual(len(drops), 1)
        lost = json.loads(base64.b64decode(drops[0]["data_b64"]))["lost_bytes"]
        self.assertEqual(lost, state["oldest_after"] - state["written_before"])
        self.assertGreater(lost, 0)
        got = texts(fr)
        self.assertEqual(got, ["burst %02d ................" % i for i in range(80 - len(got), 80)])
        self.assertGreater(len(got), 5)
        self.assertEqual(r.manifest["outcome"], "incomplete")
        self.assertIn("producer-reported-drop", [e["reason"] for e in r.errors()])

    def test_records_the_device_dropped_arrive_as_device_reported_drops(self):
        r = Rig(self)
        r.m.text("one")
        r.m.log(P.K_TEXT, b"x" * 2000)          # larger than a record may be: the engine drops it and counts it
        r.m.text("two")
        r.go(0.4)
        fr = r.frames(r.boot_dirs()[0])
        drops = [f for f in fr if f["kind"] == "drop"]
        self.assertEqual([(d["reason"], d["count"]) for d in drops], [("device-reported", 1)])
        self.assertEqual(texts(fr), ["one", "two"])

    def test_a_corrupted_record_header_is_skipped_and_the_following_records_survive(self):
        r = Rig(self)
        lines = ["rec %d %s" % (i, "y" * i) for i in range(10)]
        for s in lines:
            r.m.text(s)
        hits = []

        def corrupt(req, data):
            if req == P.REQ_READ_RING and not hits and len(data) > 8:
                body = bytearray(data)
                pos = 8
                for i in range(3):                                    # walk to the 4th record's header
                    pos += 8 + struct.unpack("<H", bytes(body[pos + 4:pos + 6]))[0]
                body[pos] ^= 0xFF
                hits.append(pos)
                return bytes(body)
            return data
        r.reply_filter = corrupt
        r.go(0.6)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(len(hits), 1)
        drops = [f for f in fr if f["kind"] == "drop"]
        self.assertEqual([d["reason"] for d in drops], ["header-crc"])
        skipped = json.loads(base64.b64decode(drops[0]["data_b64"]))["skipped_bytes"]
        self.assertEqual(skipped, 8 + len(lines[3]))
        self.assertEqual(texts(fr), lines[:3] + lines[4:])
        self.assertEqual(r.manifest["outcome"], "incomplete")

    def test_data_still_in_the_ring_when_the_size_limit_stops_the_run_is_reported_unread(self):
        r = Rig(self, ring_size=4096)
        for i in range(40):
            r.m.text("filler %02d" % i)
        stop = r.go(1.0, max_bytes=2500)
        self.assertEqual(stop, "size-limit")
        self.assertEqual(r.manifest["outcome"], "incomplete")
        reasons = [e["reason"] for e in r.errors()]
        self.assertIn("size-limit", reasons)

    def test_unread_bytes_at_a_disconnect_are_reported(self):
        r = Rig(self)
        r.m.text("first")

        def hook(rig, n):
            if n == 6:
                rig.m.text("written but never read")
                rig.unplug()
        r.hook = hook
        r.go(0.5)
        reasons = [e["reason"] for e in r.errors()]
        # the device vanished after the last GET_INFO showed everything read: the collector cannot know about the last line
        self.assertNotIn("written but never read", [t for d in r.boot_dirs() for t in texts(r.frames(d))])
        self.assertEqual(reasons, [])
        # ... but when the last GET_INFO did show unread bytes, the loss is named

        r2 = Rig(self)
        r2.m.text("one")

        def hook2(rig, n):
            if n == 5 and not hasattr(rig, "done"):
                rig.done = True
                rig.m.text("two")          # written, then GET_INFO sees it, and the cable goes before READ_RING
                rig.hook = lambda rr, nn: rr.unplug() if rr.ntransfer == n + 1 else None
        r2.hook = hook2
        r2.go(0.5)
        self.assertIn("unread-at-end", [e["reason"] for e in r2.errors()])
        ev = [e for e in r2.errors() if e["reason"] == "unread-at-end"][0]
        self.assertGreater(ev["unread_bytes"], 0)


class LifecycleTests(unittest.TestCase):
    def test_a_device_restart_without_a_disconnect_starts_a_new_boot_record(self):
        r = Rig(self)
        r.m.text("run A")

        def hook(rig, n):
            if n == 8:
                rig.reset_device(Rig.BOOT_B)
                rig.m.text("run B")
        r.hook = hook
        r.go(1.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2)
        a, b = r.frames(dirs[0]), r.frames(dirs[1])
        self.assertEqual(texts(a), ["run A"])
        self.assertEqual(texts(b), ["run B"])
        self.assertEqual(a[-1]["kind"], "end")
        self.assertEqual(a[-1]["reason"], "reset-detected")
        self.assertEqual(b[-1]["reason"], "collector-stop")
        self.assertEqual(a[0]["boot_id"], r.nonce(1).hex() + "-" + Rig.BOOT_A.hex())
        self.assertEqual(b[0]["boot_id"], r.nonce(2).hex() + "-" + Rig.BOOT_B.hex())
        self.assertEqual(r.col.stats["resets"], 1)
        self.assertEqual(r.manifest["outcome"], "complete-received-stream", r.errors())

    def test_a_restart_of_the_same_image_is_still_a_new_run(self):
        """The device boot block may be identical between runs: only the nonce tells them apart."""
        r = Rig(self)
        r.m.text("run 1")

        def hook(rig, n):
            if n == 8:
                rig.reset_device(Rig.BOOT_A)
                rig.m.text("run 2")
        r.hook = hook
        r.go(1.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2)
        self.assertNotEqual(r.frames(dirs[0])[0]["boot_id"], r.frames(dirs[1])[0]["boot_id"])
        self.assertEqual(texts(r.frames(dirs[0])) + texts(r.frames(dirs[1])), ["run 1", "run 2"])

    def test_a_short_disconnect_continues_the_same_boot_without_gaps_or_duplicates(self):
        r = Rig(self)
        sent = []

        def hook(rig, n):
            if n > 3 and n % 3 == 0 and len(sent) < 40:
                sent.append("msg %02d" % len(sent))
                rig.m.text(sent[-1])
            if n == 14:
                rig.unplug()
                rig.pending_plug = rig.now + 0.5      # shorter than the grace period
        r.hook = hook
        r.go(3.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 1, [d.name for d in dirs])
        fr = r.frames(dirs[0])
        self.assertEqual(texts(fr), sent)
        self.assertEqual(r.col.stats["resumed"], 1)
        self.assertEqual(fr[-1]["reason"], "collector-stop")
        self.assertEqual(r.manifest["outcome"], "complete-received-stream", r.errors())

    def test_a_long_disconnect_ends_the_boot_and_the_next_connection_is_a_new_one(self):
        r = Rig(self)
        r.m.text("kept")

        def hook(rig, n):
            if n == 8:
                rig.unplug()
                rig.pending_plug = rig.now + 5.0      # longer than the grace period
        r.hook = hook
        r.go(10.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2)
        a, b = r.frames(dirs[0]), r.frames(dirs[1])
        self.assertEqual(a[-1]["reason"], "disconnect")
        self.assertNotEqual(a[0]["boot_id"], b[0]["boot_id"])
        self.assertEqual(r.col.stats["resumed"], 0)


    def test_a_device_that_restarted_while_away_is_not_mistaken_for_the_same_run(self):
        r = Rig(self)
        r.m.text("run A")
        state = {}

        def hook(rig, n):
            if n == 8:
                rig.unplug()
                rig.pending_plug = rig.now + 0.5          # well inside the grace period
                rig.reset_on_plug = Rig.BOOT_B
            elif n > 8 and rig.plugged and not state:
                state["b"] = True
                rig.m.text("run B")
        r.hook = hook
        r.go(2.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2, [d.name for d in dirs])
        a, b = r.frames(dirs[0]), r.frames(dirs[1])
        self.assertEqual(a[-1]["reason"], "disconnect")
        self.assertEqual(b[0]["boot_id"].split("-")[1], Rig.BOOT_B.hex())
        self.assertEqual(r.col.stats["resumed"], 0)
        self.assertEqual(texts(a), ["run A"])
        self.assertEqual(texts(b), ["run B"])

    def test_two_short_disconnects_in_one_run_are_both_bridged(self):
        r = Rig(self)
        sent = []

        def hook(rig, n):
            if n > 3 and n % 3 == 0 and len(sent) < 200:
                sent.append("msg %03d" % len(sent))
                rig.m.text(sent[-1])
            if n in (12, 160):
                rig.unplug()
                rig.pending_plug = rig.now + 1.2          # each gap is shorter than the grace, together they are longer
        r.hook = hook
        r.go(8.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 1, [d.name for d in dirs])
        self.assertEqual(texts(r.frames(dirs[0])), sent)
        self.assertEqual(r.col.stats["resumed"], 2)

    def test_an_interrupt_still_collects_what_the_device_wrote_last(self):
        r = Rig(self)
        r.m.text("early")

        def hook(rig, n):
            if n == 10:
                rig.m.text("last words")
                raise KeyboardInterrupt
        r.hook = hook
        self.assertEqual(r.go(5.0), "interrupted")
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(texts(fr), ["early", "last words"])
        self.assertEqual(fr[-1]["reason"], "collector-stop")
        self.assertEqual(r.manifest["outcome"], "complete-received-stream", r.errors())

    def test_a_sequence_jump_inside_the_stream_is_a_named_drop(self):
        r = Rig(self)
        for i in range(6):
            r.m.text("seq %d" % i)

        def jump(req, data):
            if req != P.REQ_READ_RING or len(data) <= 8:
                return data
            body = bytearray(data[8:])
            pos = 0
            n = 0
            while pos + 8 <= len(body):
                length = struct.unpack("<H", bytes(body[pos + 4:pos + 6]))[0]
                if n >= 2:
                    seq = struct.unpack("<I", bytes(body[pos:pos + 4]))[0]
                    body[pos:pos + 4] = struct.pack("<I", seq + 5)
                    body[pos + 7] = P.crc8(bytes(body[pos:pos + 7]))
                pos += 8 + length
                n += 1
            return data[:8] + bytes(body)
        r.reply_filter = jump
        r.go(0.5)
        fr = r.frames(r.boot_dirs()[0])
        gaps = [f for f in fr if f["kind"] == "drop"]
        self.assertEqual([g["reason"] for g in gaps], ["device-seq-gap"])
        d = json.loads(base64.b64decode(gaps[0]["data_b64"]))
        self.assertEqual((d["expected"], d["received"]), (2, 7))
        self.assertEqual(len(texts(fr)), 6)


    def test_a_changed_device_boot_block_ends_the_boot_even_if_the_nonce_survived(self):
        r = Rig(self)
        r.m.text("before")

        def hook(rig, n):
            if n == 12:
                rig.reply_filter = lambda req, d: alter_info(d, boot_id=b"CHANGED-BOOT-ID!") if req == P.REQ_GET_INFO else d
        r.hook = hook
        r.go(1.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2, [d.name for d in dirs])
        self.assertEqual(r.frames(dirs[0])[-1]["reason"], "reset-detected")
        self.assertEqual(r.frames(dirs[1])[0]["boot_id"].split("-")[1], b"CHANGED-BOOT-ID!".hex())

    def test_a_stream_that_shrinks_ends_the_boot_even_with_the_nonce_intact(self):
        r = Rig(self)
        for i in range(6):
            r.m.text("old stream %d" % i)

        def hook(rig, n):
            if n == 12:
                rig.m.lib.t_set_stream_base(0)       # written and oldest back to 0; nonce and boot block untouched
                rig.m.text("new stream")
        r.hook = hook
        r.go(1.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2, [d.name for d in dirs])
        self.assertEqual(r.frames(dirs[0])[-1]["reason"], "reset-detected")
        self.assertEqual(texts(r.frames(dirs[0])), ["old stream %d" % i for i in range(6)])
        self.assertEqual(texts(r.frames(dirs[1])), ["new stream"])

    def test_a_ring_read_that_lands_far_behind_is_a_reset_not_a_four_gigabyte_overrun(self):
        r = Rig(self)
        for i in range(6):
            r.m.text("old stream %d" % i)

        def hook(rig, n):
            if n == 12:
                rig.m.lib.t_set_stream_base(0)
                rig.m.text("new stream")
                # GET_INFO keeps claiming a long stream, so only the READ_RING reply can reveal the regression
                rig.reply_filter = lambda req, d: alter_info(d, written=10 ** 6) if req == P.REQ_GET_INFO else d
        r.hook = hook
        r.go(1.0)
        dirs = r.boot_dirs()
        self.assertGreaterEqual(len(dirs), 2)
        self.assertEqual(r.frames(dirs[0])[-1]["reason"], "reset-detected")
        for d in dirs:
            self.assertNotIn("ring-overrun", [f.get("reason") for f in r.frames(d) if f["kind"] == "drop"])

    def test_resume_is_refused_when_the_nonce_on_the_device_is_not_ours(self):
        r = Rig(self)
        r.m.text("ours")
        state = {}

        def hook(rig, n):
            if n == 8:
                rig.unplug()
                rig.pending_plug = rig.now + 0.5
            elif n > 8 and rig.plugged and not state:
                state["x"] = True
                rig.m.ctrl(0x40, P.REQ_SET_NONCE, 0, 0, P.NONCE_LEN, b"\x77" * P.NONCE_LEN)
        r.hook = hook
        r.go(2.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2, [d.name for d in dirs])
        self.assertEqual(r.frames(dirs[0])[-1]["reason"], "disconnect")
        self.assertEqual(r.col.stats["resumed"], 0)

    def test_resume_is_refused_when_the_device_boot_block_changed_while_away(self):
        r = Rig(self)
        r.m.text("ours")
        state = {}

        def hook(rig, n):
            if n == 8:
                rig.unplug()
                rig.pending_plug = rig.now + 0.5
            elif n > 8 and rig.plugged and not state:
                state["x"] = True
                rig.reply_filter = lambda req, d: alter_info(d, boot_id=b"OTHER-BOOT-ID!!!") if req == P.REQ_GET_INFO else d
        r.hook = hook
        r.go(2.0)
        dirs = r.boot_dirs()
        self.assertEqual(len(dirs), 2, [d.name for d in dirs])
        self.assertEqual(r.col.stats["resumed"], 0)

    def test_a_corrupt_last_record_is_skipped_and_the_stream_recovers_with_the_next_one(self):
        r = Rig(self)
        lines = ["rec %d %s" % (i, "y" * (i + 3)) for i in range(3)]
        for s in lines:
            r.m.text(s)
        hits = []

        def corrupt(req, data):
            if req == P.REQ_READ_RING and not hits and len(data) > 8:
                body = bytearray(data)
                pos = 8
                for i in range(2):
                    pos += 8 + struct.unpack("<H", bytes(body[pos + 4:pos + 6]))[0]
                body[pos] ^= 0xFF                      # the third and last record header
                hits.append(pos)
                return bytes(body)
            return data
        r.reply_filter = corrupt

        def hook(rig, n):
            if n == 15:
                rig.m.text("after the damage")
        r.hook = hook
        r.go(1.0)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(len(hits), 1)
        self.assertEqual(texts(fr), lines[:2] + ["after the damage"])
        drops = [json.loads(base64.b64decode(f["data_b64"])) for f in fr if f["kind"] == "drop"]
        self.assertEqual([d["reason"] for d in drops], ["header-crc", "header-crc"])
        self.assertEqual(drops[0]["skipped_bytes"], 8 + len(lines[2]) - 7)
        self.assertEqual(drops[1]["skipped_bytes"], 7)

    def test_the_boot_is_closed_when_the_device_stays_away_until_the_collector_stops(self):
        r = Rig(self)

        def hook(rig, n):
            if n == 6:
                rig.unplug()
        r.hook = hook
        r.go(1.0)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual((fr[-1]["kind"], fr[-1]["reason"]), ("end", "disconnect"))

    def test_transient_timeouts_cost_nothing(self):
        r = Rig(self)
        sent = []

        def hook(rig, n):
            if n == 7:
                rig.fail = 5
            if n > 3 and n % 4 == 0 and len(sent) < 20:
                sent.append("t %02d" % len(sent))
                rig.m.text(sent[-1])
        r.hook = hook
        r.go(8.0)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(texts(fr), sent)
        self.assertGreaterEqual(r.col.stats["timeouts"], 5)
        self.assertEqual(r.errors(), [])
        self.assertEqual(len(r.boot_dirs()), 1)

    def test_a_device_that_stops_answering_ends_the_boot_as_unresponsive(self):
        r = Rig(self)
        r.m.text("before silence")

        def hook(rig, n):
            if n == 8:
                rig.fail_forever = True
        r.hook = hook
        r.go(30.0)
        fr = r.frames(r.boot_dirs()[0])
        self.assertEqual(texts(fr), ["before silence"])
        self.assertEqual((fr[-1]["kind"], fr[-1]["reason"]), ("end", "unresponsive"))
        failures = [e for e in r.errors() if e["reason"] == "start-failed"]
        self.assertEqual(len(failures), 1, "an unchanged failure is recorded once, not on every retry")
        self.assertGreater(r.col.stats["start_failures"], 1)

    def test_a_reply_that_is_not_a_monitor_reply_never_starts_a_boot(self):
        r = Rig(self)
        bad = {"n": 0}

        def broken(req, data):
            if req == P.REQ_GET_INFO and bad["n"] < 2:
                bad["n"] += 1
                return b"XXXX" + data[4:]
            return data
        r.reply_filter = broken
        r.go(1.0)
        self.assertGreaterEqual(r.col.stats["start_failures"], 1)
        self.assertEqual(len(r.boot_dirs()), 1)
        self.assertEqual(r.frames(r.boot_dirs()[0])[0]["kind"], "boot")

    def test_a_device_that_does_not_echo_the_nonce_is_not_recorded_as_a_boot(self):
        r = Rig(self)
        r.swallow_out = True
        r.go(0.6)
        self.assertEqual(r.boot_dirs(), [])
        self.assertIn("start-failed", [e["reason"] for e in r.errors()])
        self.assertEqual(r.manifest["outcome"], "incomplete")

    def test_two_matching_devices_are_reported(self):
        r = Rig(self)
        real_find = r.find
        r.find = lambda vid, pid: real_find(vid, pid) * 2
        r.go(0.3)
        self.assertEqual([e["reason"] for e in r.errors()], ["multiple-devices"])


class SafetyTests(unittest.TestCase):
    def test_only_the_monitor_vid_pid_is_ever_queried(self):
        r = Rig(self)
        r.go(0.3)
        self.assertEqual(set(r.queries), {(0x1209, 0x0001)})

    def test_a_samsung_vendor_id_is_refused(self):
        r = Rig(self)
        with self.assertRaises(ValueError):
            L.Collector(r, r.archive, r.transfers, vid=0x04E8)
        r.transfers.close()
        r.archive.finish("eof")

    def test_only_vendor_requests_are_sent(self):
        r = Rig(self)
        r.m.fault()
        r.go(0.5)
        for row in r.transfer_rows():
            self.assertIn((row["dir"], row["req"]), {("in", 1), ("in", 2), ("in", 3), ("out", 4)})

    def test_every_transfer_is_logged_with_its_data(self):
        r = Rig(self)
        r.m.text("hello")
        r.go(0.4)
        rows = r.transfer_rows()
        self.assertEqual(len(rows), r.col.stats["transfers"])
        ring = [x for x in rows if x["req"] == P.REQ_READ_RING and x["result"] == "ok" and x["n"] > 8]
        self.assertTrue(ring)
        recs, _, err = P.split_records(base64.b64decode(ring[0]["data_b64"])[8:])
        self.assertIsNone(err)
        self.assertEqual(recs[0][2], b"hello")

    def test_the_archive_manifest_names_the_extra_files(self):
        r = Rig(self)
        r.go(0.3)
        self.assertIn("usb-transfers.jsonl", r.manifest["sha256"])
        self.assertIn("collector-summary.json", r.manifest["sha256"])
        self.assertFalse(r.manifest["transport_qualified"])
        self.assertFalse(r.manifest["hardware_execution_proven"])


class FakeUsbCore:
    """Just enough of pyusb's usb.core for PyUsbBackend."""

    class USBError(Exception):
        def __init__(self, msg, errno=None):
            super().__init__(msg)
            self.errno = errno

    class NoBackendError(Exception):
        pass

    def __init__(self):
        self.calls = []
        self.devices = []
        self.raise_on_find = None

    def find(self, **kw):
        self.calls.append(("find", kw))
        if self.raise_on_find:
            raise self.raise_on_find
        return [d for d in self.devices if all(getattr(d, k) == v for k, v in kw.items() if k != "find_all")]


class FakePyUsbDevice:
    idVendor, idProduct, bus, address = 0x1209, 0x0001, 3, 9

    def __init__(self, usb, error=None, reply=b"\x01\x02"):
        self.usb, self.error, self.reply = usb, error, reply

    def ctrl_transfer(self, bm, req, value, index, data_or_len, timeout):
        self.usb.calls.append(("ctrl", bm, req, value, index, data_or_len, timeout))
        if self.error is not None:
            raise self.error
        return list(self.reply) if bm & 0x80 else len(data_or_len)


class PyUsbBackendTests(unittest.TestCase):
    def test_find_filters_by_vid_and_pid_and_wraps_devices(self):
        usb = FakeUsbCore()
        usb.devices = [FakePyUsbDevice(usb)]
        devs = L.PyUsbBackend(usb).find(0x1209, 0x0001)
        self.assertEqual(usb.calls, [("find", dict(find_all=True, idVendor=0x1209, idProduct=0x0001))])
        self.assertEqual(devs[0].info, dict(vid=0x1209, pid=1, bus=3, address=9))

    def test_vendor_request_types_and_arguments(self):
        usb = FakeUsbCore()
        usb.devices = [FakePyUsbDevice(usb)]
        dev = L.PyUsbBackend(usb).find(0x1209, 1)[0]
        self.assertEqual(dev.control_in(2, 0x1234, 0x5678, 4096, 700), b"\x01\x02")
        self.assertEqual(dev.control_out(4, 0, 0, b"n" * 16, 700), 16)
        self.assertEqual(usb.calls[1], ("ctrl", 0xC0, 2, 0x1234, 0x5678, 4096, 700))
        self.assertEqual(usb.calls[2], ("ctrl", 0x40, 4, 0, 0, b"n" * 16, 700))

    def test_libusb_errors_map_to_the_collectors_error_classes(self):
        expect = {19: L.UsbGone, 13: L.UsbAccess, 32: L.UsbStall, 110: L.UsbTimeout, 5: L.UsbTimeout, None: L.UsbTimeout}
        for errno, cls in expect.items():
            usb = FakeUsbCore()
            usb.devices = [FakePyUsbDevice(usb, error=usb.USBError("boom", errno))]
            dev = L.PyUsbBackend(usb).find(0x1209, 1)[0]
            with self.assertRaises(cls, msg="errno %r" % errno):
                dev.control_in(1, 0, 0, 112, 100)
            with self.assertRaises(cls, msg="errno %r" % errno):
                dev.control_out(4, 0, 0, b"x", 100)

    def test_a_missing_libusb_backend_is_an_error_not_a_crash(self):
        usb = FakeUsbCore()
        usb.raise_on_find = usb.NoBackendError("no backend available")
        with self.assertRaises(L.UsbError):
            L.PyUsbBackend(usb).find(0x1209, 1)

    def test_a_backend_failure_ends_the_run_with_a_named_error(self):
        r = Rig(self)

        def failing(vid, pid):
            raise L.UsbError("no libusb backend: test")
        r.find = failing
        self.assertEqual(r.go(0.3), "backend-error")
        self.assertEqual(r.manifest["outcome"], "incomplete")
        self.assertIn("usb-backend", [e["reason"] for e in r.errors()])

    def test_access_denied_is_recorded_once_and_does_not_crash(self):
        r = Rig(self)

        def denied(*a):
            raise L.UsbAccess("permission denied")
        r.hook = lambda rig, n: denied()
        r.go(5.0)
        self.assertEqual([e["reason"] for e in r.errors()].count("device-access-denied"), 1)


class FinishTests(unittest.TestCase):
    def test_a_deadline_after_a_clean_run_is_not_an_archive_error(self):
        r = Rig(self)
        r.m.text("x")
        self.assertEqual(r.go(0.4), "deadline")
        self.assertEqual(r.manifest["outcome"], "complete-received-stream")
        note = [e for e in r.events() if e["kind"] == "collector-note"]
        self.assertEqual([(n["reason"], n["deliberate"]) for n in note], [("deadline", True)])
        with open(r.out / "collector-summary.json") as f:
            self.assertEqual(json.loads(f.read())["stop"], "deadline")

    def test_invalid_bounds_are_refused(self):
        r = Rig(self)
        for sec, mb in ((0, 10), (-1, 10), (7 * 3600, 10), (1, 0), (1, 2 ** 31)):
            with self.assertRaises(ValueError):
                r.col.run(sec, mb)
        r.transfers.close()
        r.archive.finish("eof")


if __name__ == "__main__":
    unittest.main(verbosity=2)
