#!/usr/bin/env python3
"""Host tests of the NAT-041 usbmon engine against the DWC3/cache/USB-host model (model/model.c).

Evidence kind: host-test. The model is a written-down reading of the vendor dwc3 driver (see model/model.c); passing here
shows consistency with that reading and with the DMA discipline, not behaviour of the S24's controller.
"""
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

def _slurp(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modelhost as M  # noqa: E402
import usbmon_proto as P  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
VENDOR = os.path.join(ROOT, "references", "s24-linux")
VENDOR_PIN = "417484173abc2c4fa93e738ea82ad9f2e84911b1"
ENGINE_C = os.path.join(HERE, "engine", "usbmon.c")
ENGINE_H = os.path.join(HERE, "engine", "usbmon.h")
REGS_H = os.path.join(HERE, "engine", "dwc3_regs.h")

_TMP = tempfile.mkdtemp(prefix="nat041-test-")
_LIB = None


def lib():
    global _LIB
    if _LIB is None:
        _LIB = M.build(out_dir=_TMP)
    return _LIB


def vendor_file(path):
    r = subprocess.run(["git", "-C", VENDOR, "show", "%s:%s" % (VENDOR_PIN, path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise unittest.SkipTest("pinned vendor tree not available at %s (%s)" % (VENDOR, r.stderr.strip()[:80]))
    return r.stdout


class Base(unittest.TestCase):
    def setUp(self):
        self.m = M.Machine(lib(), ring_size=4096)
        self.assertEqual(self.m.init_rc, 0)

    def tearDown(self):
        self.m.close()

    def up(self):
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)

    def clean(self):
        self.assertEqual(self.m.violations(), [])

    def vendor_in(self, req, length, value=0, index=0):
        return self.m.ctrl(0xC0, req, value, index, length)

    def info(self):
        rc, d = self.vendor_in(P.REQ_GET_INFO, P.INFO_SIZE)
        self.assertEqual(rc, M.H_OK)
        return P.parse_info(d)

    def read_ring(self, off, length=4096):
        rc, d = self.vendor_in(P.REQ_READ_RING, length, value=off & 0xFFFF, index=(off >> 16) & 0xFFFF)
        self.assertEqual(rc, M.H_OK)
        return P.parse_ring_reply(d)

    def read_stream(self, off=0):
        """Read to the end of the stream; -> (records, next offset)"""
        recs = []
        buf = b""
        while True:
            start, end, payload = self.read_ring(off)
            if start != (off & 0xFFFFFFFF):
                raise AssertionError("reply starts at %#x, asked for %#x" % (start, off))
            if not payload:
                break
            buf += payload
            off += len(payload)
            r, used, err = P.split_records(buf)
            self.assertIsNone(err)
            recs += r
            buf = buf[used:]
            off -= len(buf)
            # keep the unconsumed tail for the next read: restart from its first byte
        return recs, off


class EnumerationTests(Base):
    def test_enumeration_descriptors(self):
        self.m.attach()
        steps = {n: (rc, d) for n, rc, d in self.m.enumerate(address=9)}
        for n, (rc, _) in steps.items():
            self.assertEqual(rc, M.H_OK, n)
        dev = steps["get_descriptor_18"][1]
        self.assertEqual(len(dev), 18)
        self.assertEqual(dev[0:2], bytes([18, 1]))
        self.assertEqual(struct.unpack("<HH", dev[8:12]), (P.VID, P.PID))
        self.assertEqual(dev[7], 64)
        self.assertEqual(steps["get_descriptor_8"][1], dev[:8])
        cfg = steps["get_config_18"][1]
        self.assertEqual(struct.unpack("<H", cfg[2:4])[0], 18)
        self.assertEqual(steps["get_config_9"][1], cfg[:9])
        self.assertEqual(self.m.lib.model_host_addr(), 9)
        self.assertEqual(self.info()["flags"] & (P.F_CONNECTED | P.F_CONFIGURED), P.F_CONNECTED | P.F_CONFIGURED)
        self.clean()

    def test_standard_requests_after_enumeration(self):
        self.up()
        rc, d = self.m.ctrl(0x80, 0, 0, 0, 2)
        self.assertEqual((rc, d), (M.H_OK, b"\x01\x00"))
        rc, d = self.m.ctrl(0x80, 8, 0, 0, 1)
        self.assertEqual((rc, d), (M.H_OK, b"\x01"))
        rc, d = self.m.ctrl(0x81, 10, 0, 0, 1)
        self.assertEqual((rc, d), (M.H_OK, b"\x00"))
        rc, d = self.m.ctrl(0x81, 0, 0, 0, 2)
        self.assertEqual((rc, d), (M.H_OK, b"\x00\x00"))
        rc, d = self.m.ctrl(0x82, 0, 0, 0, 2)
        self.assertEqual((rc, d), (M.H_OK, b"\x00\x00"))
        rc, d = self.m.ctrl(0x80, 6, 0x0600, 0, 10)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(d[:2], bytes([10, 6]))
        self.clean()

    def test_superspeed_connection_uses_512_byte_ep0(self):
        for speed, mps in ((0, 64), (4, 512)):
            self.m.close()
            self.m = M.Machine(lib(), ring_size=4096)
            self.m.lib.model_set_speed(speed)
            self.m.attach()
            cmds = [c for c in self.m.cmd_trace() if c[1] & 0xf == 1]
            self.assertEqual([(c[0], (c[2] >> 30) & 3, (c[2] >> 3) & 0x7ff) for c in cmds[-2:]],
                             [(0, 2, mps), (1, 2, mps)], "speed %d" % speed)
            self.clean()

    def test_command_and_register_order_follows_the_vendor_sequence(self):
        cmds = [(ep, c & 0xf, (p0 >> 30) if c & 0xf == 1 else None) for ep, c, p0, p1, p2, r in self.m.cmd_trace()]
        self.assertEqual(cmds, [(0, 9, None), (0, 1, 0), (0, 2, None), (1, 1, 0), (1, 2, None), (0, 6, None)])
        w = self.m.write_trace()
        offs = [o for o, _ in w]

        def first(off, pred=lambda v: True):
            return next(i for i, (o, v) in enumerate(w) if o == off and pred(v))
        from_dctl_reset = first(0xc704, lambda v: v & (1 << 30))
        gctl_dev = first(0xc110, lambda v: (v >> 12) & 3 == 2)
        evt_siz = first(0xc408)
        dcfg_hs = first(0xc700, lambda v: v & 7 == 0)
        dalepena = first(0xc720)
        run = first(0xc704, lambda v: v & (1 << 31))
        self.assertLess(from_dctl_reset, gctl_dev)
        self.assertLess(gctl_dev, evt_siz)
        self.assertLess(evt_siz, dcfg_hs)
        self.assertLess(dcfg_hs, dalepena)
        self.assertLess(dalepena, run)
        self.assertEqual(run, max(i for i, (o, v) in enumerate(w) if o == 0xc704))
        # the last register write of init is RUN_STOP, and after it nothing but events changes the controller
        self.assertEqual(w[-1][0], 0xc704)
        self.assertNotIn(0xc110, offs[run:])
        self.clean()

    def test_idle_poll_writes_nothing(self):
        self.up()
        n = len(self.m.write_trace())
        c = len(self.m.cmd_trace())
        self.m.poll(50)
        self.assertEqual((len(self.m.write_trace()), len(self.m.cmd_trace())), (n, c))

    def test_engine_polled_slowly_still_enumerates(self):
        self.m.set_host(polls_per_step=1, timeout_steps=200)
        self.up()
        self.clean()

    def test_engine_never_polled_times_out_instead_of_hanging(self):
        self.m.set_host(polls_per_step=0, timeout_steps=5)
        self.m.attach()
        rc, _ = self.m.ctrl(0x80, 6, 0x0100, 0, 18)
        self.assertEqual(rc, M.H_TIMEOUT)

    def test_dma_block_is_cache_line_aligned(self):
        self.assertEqual(self.m.lib.t_dma_misaligned(), 0)


class InitFailureTests(unittest.TestCase):
    def machine(self, **kw):
        m = M.Machine(lib(), ring_size=4096, auto_init=False)
        self.addCleanup(m.close)
        return m

    def test_wrong_core_id(self):
        m = self.machine()
        m.lib.model_set_id(0x12340000)
        self.assertEqual(m.init(), -1)
        self.assertEqual(m.write_trace(), [])

    def test_soft_reset_never_completes(self):
        m = self.machine()
        m.lib.model_set_sr_latency(100000)
        self.assertEqual(m.init(), -2)

    def test_command_timeout_and_failure_are_reported(self):
        m = self.machine()
        m.lib.model_set_cmd_latency(100000)
        self.assertEqual(m.init(), -3)
        m2 = M.Machine(lib(), ring_size=4096, auto_init=False)
        self.addCleanup(m2.close)
        m2.lib.model_fail_next_cmd(2)
        self.assertEqual(m2.init(), -3)
        self.assertEqual(m2.violations(), [])

    def test_bad_arguments(self):
        m = self.machine()
        self.assertEqual(m.lib.t_init(b"x" * 16, 100, 0, 0, 0), -6)
        self.assertEqual(m.write_trace(), [])

    def test_slow_commands_within_the_bound_succeed(self):
        m = self.machine()
        m.lib.model_set_cmd_latency(4000)
        self.assertEqual(m.init(), 0)
        self.assertEqual(m.violations(), [])


class StreamTests(Base):
    def test_log_stream_round_trip(self):
        self.up()
        self.m.text("hello")
        self.m.stage(7, "stage seven")
        self.m.log(P.K_MARK, b"\x00\x01binary")
        recs, _ = self.read_stream()
        self.assertEqual([(r[1], r[2]) for r in recs], [(P.K_TEXT, b"hello"), (P.K_STAGE, struct.pack("<I", 7) + b"stage seven"),
                                                         (P.K_MARK, b"\x00\x01binary")])
        self.assertEqual([r[0] for r in recs], [0, 1, 2])
        self.assertEqual(P.decode_record(*recs[1]), {"seq": 1, "kind": "stage", "stage": 7, "text": "stage seven"})
        self.assertEqual(self.m.lib.t_flags() & P.F_FAULT, 0)
        self.clean()

    def test_reads_in_small_pieces_reassemble_the_same_stream(self):
        self.up()
        texts = ["record %d %s" % (i, "x" * (i * 7 % 40)) for i in range(20)]
        for t in texts:
            self.m.text(t)
        whole = b""
        off = 0
        while True:
            start, end, payload = self.read_ring(off, 8 + 13)
            self.assertEqual(start, off)
            self.assertLessEqual(len(payload), 13)
            if not payload:
                break
            whole += payload
            off += len(payload)
        recs, used, err = P.split_records(whole)
        self.assertIsNone(err)
        self.assertEqual(used, len(whole))
        self.assertEqual([r[2].decode() for r in recs], texts)
        self.clean()

    def test_read_at_and_beyond_the_end(self):
        self.up()
        self.m.text("a")
        w = self.m.written
        start, end, payload = self.read_ring(w)
        self.assertEqual((start, end, payload), (w, w, b""))
        start, end, payload = self.read_ring(w + 100)
        self.assertEqual((start, payload), (w, b""))
        self.clean()

    def test_ring_wrap_drops_whole_records_and_reads_start_at_a_header(self):
        self.up()
        payloads = [("%03d" % i) * 60 for i in range(40)]   # 180 byte payloads, 188 with header, 7520 total > 4096
        for p in payloads:
            self.m.text(p)
        oldest = self.m.oldest
        self.assertGreater(oldest, 0)
        self.assertLessEqual(self.m.written - oldest, 4096)
        hdr = self.m.ring_bytes(oldest, 8)
        self.assertEqual(P.crc8(hdr[:7]), hdr[7], "oldest must point at a record header")
        # a reader that is behind (asks for offset 0) is moved to the oldest retained header
        start, end, payload = self.read_ring(0)
        self.assertEqual(start, oldest)
        recs, used, err = P.split_records(payload)
        self.assertIsNone(err)
        self.assertEqual(recs[0][0], oldest // 188)    # whole 188-byte records: the first kept seq equals the dropped count
        self.assertEqual(recs[-1][2].decode(), payloads[-1][:len(recs[-1][2])] if False else recs[-1][2].decode())
        self.assertEqual([r[2].decode() for r in recs], payloads[recs[0][0]:recs[0][0] + len(recs)])
        self.clean()

    def test_offsets_beyond_64k_and_across_the_32_bit_boundary(self):
        self.up()
        for base in (0, 0xFFFFF000, 0x1FFFFFF00):
            self.m.lib.t_set_stream_base(base)
            seq0 = self.m.seq
            texts = ["base %x item %d" % (base, i) for i in range(30)]
            for t in texts:
                self.m.text(t * 3)
            got = []
            off = base
            for _ in range(60):
                start, end, payload = self.read_ring(off & 0xFFFFFFFFFFFF, 80)
                self.assertEqual(start, off & 0xFFFFFFFF)
                if not payload:
                    break
                got.append(payload)
                off += len(payload)
            self.assertEqual(off, self.m.written)
            recs, used, err = P.split_records(b"".join(got))
            self.assertIsNone(err)
            self.assertEqual([r[2].decode() for r in recs], [t * 3 for t in texts])
            self.assertEqual(recs[0][0], seq0)
        self.clean()

    def test_large_stream_read_through_many_wraps(self):
        self.up()
        off = 0
        seen = []
        buf = b""
        for i in range(400):
            self.m.text("line %04d " % i + "y" * (i % 97))
            if i % 7 == 6:
                start, end, payload = self.read_ring(off)
                self.assertGreaterEqual(start, off)
                if start != off:       # fell behind: only the pieces after the gap are usable
                    buf = b""
                    off = start
                buf += payload
                off += len(payload)
                recs, used, err = P.split_records(buf)
                self.assertIsNone(err)
                seen += [int(r[2][5:9]) for r in recs]
                buf = buf[used:]
        self.assertEqual(seen, sorted(seen))
        self.assertGreater(len(seen), 300)
        self.clean()

    def test_oversize_record_is_dropped_and_counted_in_the_stream(self):
        self.up()
        self.m.log(P.K_TEXT, b"z" * 2000)
        self.assertEqual(self.m.dropped, 1)
        self.m.text("after")
        recs, _ = self.read_stream()
        kinds = [(r[1], r[2]) for r in recs]
        self.assertIn((P.K_TEXT, b"after"), kinds)
        drops = [r for r in recs if r[1] == P.K_DROP]
        self.assertEqual([struct.unpack("<I", r[2])[0] for r in drops], [1])
        self.assertEqual(self.info()["dropped"], 1)

    def test_an_interrupted_append_is_never_served(self):
        self.up()
        self.m.text("before")
        w = self.m.written
        self.m.log_interrupted(P.K_TEXT, b"half written record", 12)
        self.assertEqual(self.m.written, w, "an unfinished append must not move the commit point")
        start, end, payload = self.read_ring(0)
        self.assertEqual(end, w)
        self.m.text("after")
        recs, used, err = P.split_records(self.read_ring(0)[2])
        self.assertIsNone(err)
        self.assertEqual([r[2] for r in recs], [b"before", b"after"])
        self.assertEqual([r[0] for r in recs], [0, 2], "the interrupted record keeps its sequence number: a visible gap")
        self.clean()

    def test_record_header_crc_matches_the_reference(self):
        self.m.text("crc")
        hdr = self.m.ring_bytes(0, 8)
        self.assertEqual(hdr[:7], struct.pack("<IHB", 0, 3, P.K_TEXT))
        self.assertEqual(hdr[7], P.crc8(hdr[:7]))
        self.assertEqual(P.crc8(b"123456789"), 0xF4)       # CRC-8/SMBUS check value

    def test_get_info_fields(self):
        self.up()
        self.m.text("x")
        i = self.info()
        self.assertEqual(i["boot_id"], self.m.boot_id)
        self.assertEqual(i["nonce"], b"\x00" * 16)
        self.assertEqual(i["ring_size"], 4096)
        self.assertEqual(i["next_seq"], 1)
        self.assertEqual(i["written"], self.m.written)
        self.assertEqual(i["oldest"], 0)
        self.assertEqual(i["last_err"], 0)
        self.assertEqual(i["setups"], 7)             # 6 enumeration transfers and this GET_INFO
        i2 = self.info()
        self.assertGreater(i2["ticks"], i["ticks"])
        self.assertEqual(i2["setups"], 8)
        rc, d = self.vendor_in(P.REQ_GET_INFO, 16)    # truncated reads are allowed
        self.assertEqual((rc, len(d)), (M.H_OK, 16))
        self.clean()

    def test_stage_updates_the_info_stage(self):
        self.up()
        self.m.stage(0x1234, "ckpt")
        self.assertEqual(self.info()["stage"], 0x1234)

    def test_set_nonce_is_echoed(self):
        self.up()
        nonce = bytes(range(0xA0, 0xB0))
        rc, _ = self.m.ctrl(0x40, P.REQ_SET_NONCE, 0, 0, 16, nonce)
        self.assertEqual(rc, M.H_OK)
        i = self.info()
        self.assertEqual(i["nonce"], nonce)
        self.assertTrue(i["flags"] & P.F_NONCE_SET)
        self.clean()


class FaultTests(Base):
    def test_exception_frame_and_record(self):
        self.up()
        rc, d = self.vendor_in(P.REQ_GET_EXC, P.EXC_SIZE)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(P.parse_exc(d)["valid"], 0)
        self.m.stage(9, "about to fault")
        xs = [0xAAAA000000000000 + i for i in range(31)]
        self.m.fault(esr=0x96000045, elr=0xFFFFFFF007004ABC, far=0xDEAD0000, spsr=0x600003C5, sp=0xFFFFFFF0070F1000, x=xs)
        rc, d = self.vendor_in(P.REQ_GET_EXC, P.EXC_SIZE)
        e = P.parse_exc(d)
        self.assertEqual((e["valid"], e["stage"], e["count"]), (1, 9, 1))
        self.assertEqual((e["esr"], e["elr"], e["far"], e["spsr"], e["sp"]),
                         (0x96000045, 0xFFFFFFF007004ABC, 0xDEAD0000, 0x600003C5, 0xFFFFFFF0070F1000))
        self.assertEqual(e["x"], xs)
        self.assertEqual(e["boot_id"], self.m.boot_id)
        i = self.info()
        self.assertEqual(i["flags"] & (P.F_FAULT | P.F_HOLD), P.F_FAULT | P.F_HOLD)
        self.assertEqual(i["faults"], 1)
        recs, _ = self.read_stream()
        faults = [P.decode_record(*r) for r in recs if r[1] == P.K_FAULT]
        self.assertEqual(faults, [{"seq": faults[0]["seq"], "kind": "fault", "esr": 0x96000045, "elr": 0xFFFFFFF007004ABC,
                                   "far": 0xDEAD0000, "stage": 9}])
        self.clean()

    def test_second_fault_keeps_the_first_frame(self):
        self.up()
        self.m.fault(esr=1, elr=0x1111)
        self.m.fault(esr=2, elr=0x2222)
        e = P.parse_exc(self.vendor_in(P.REQ_GET_EXC, P.EXC_SIZE)[1])
        self.assertEqual((e["esr"], e["elr"], e["count"]), (1, 0x1111, 2))
        recs, _ = self.read_stream()
        self.assertEqual(len([r for r in recs if r[1] == P.K_FAULT]), 2)

    def test_requests_are_served_while_holding(self):
        self.up()
        self.m.fault()
        # the hold loop only polls: everything must still work, including a fresh enumeration after a bus reset
        for _ in range(5):
            self.m.text("while holding")
            self.assertEqual(self.vendor_in(P.REQ_GET_INFO, P.INFO_SIZE)[0], M.H_OK)
        self.m.bus_reset()
        for name, rc, _ in self.m.enumerate(address=3):
            self.assertEqual(rc, M.H_OK, name)
        recs, _ = self.read_stream()
        self.assertEqual(len([r for r in recs if r[2] == b"while holding"]), 5)
        self.clean()


class RequestHandlingTests(Base):
    BAD = [
        ("unknown vendor IN", 0xC0, 0x7F, 0, 0, 16),
        ("PEEK is reserved", 0xC0, P.REQ_PEEK, 0, 0, 16),
        ("GET_INFO with wLength 0", 0xC0, P.REQ_GET_INFO, 0, 0, 0),
        ("GET_INFO with wValue", 0xC0, P.REQ_GET_INFO, 1, 0, 16),
        ("READ_RING shorter than its header", 0xC0, P.REQ_READ_RING, 0, 0, 4),
        ("READ_RING longer than the limit", 0xC0, P.REQ_READ_RING, 0, 0, 4097),
        ("GET_EXC with wIndex", 0xC0, P.REQ_GET_EXC, 0, 1, 16),
        ("class request", 0xA1, 1, 0, 0, 8),
        ("vendor request to an interface", 0xC1, P.REQ_GET_INFO, 0, 0, 16),
        ("GET_DESCRIPTOR string", 0x80, 6, 0x0300, 0, 8),
        ("GET_DESCRIPTOR with language index", 0x80, 6, 0x0100, 9, 18),
        ("GET_STATUS with wrong wLength", 0x80, 0, 0, 0, 4),
        ("GET_STATUS endpoint 1", 0x82, 0, 0, 1, 2),
        ("SET_CONFIGURATION 2", 0x00, 9, 2, 0, 0),
        ("SET_ADDRESS once configured", 0x00, 5, 7, 0, 0),
        ("unknown standard request", 0x00, 0x42, 0, 0, 0),
    ]

    def test_malformed_and_unsupported_requests_stall_and_the_engine_recovers(self):
        self.up()
        stalls = self.m.stalls
        for name, bm, req, value, index, length in self.BAD:
            with self.subTest(name):
                rc, d = self.m.ctrl(bm, req, value, index, length)
                self.assertEqual(rc, M.H_STALL)
                stalls += 1
                self.assertEqual(self.m.stalls, stalls)
                rc, d = self.vendor_in(P.REQ_GET_INFO, P.INFO_SIZE)     # the next valid request works
                self.assertEqual(rc, M.H_OK)
                self.assertEqual(P.parse_info(d)["stalls"], stalls)
        self.clean()

    def test_malformed_out_requests_stall(self):
        self.up()
        for name, req, value, index, length in (("short nonce", P.REQ_SET_NONCE, 0, 0, 8),
                                                ("long nonce", P.REQ_SET_NONCE, 0, 0, 32),
                                                ("nonce with wValue", P.REQ_SET_NONCE, 1, 0, 16),
                                                ("unknown vendor OUT", 0x7E, 0, 0, 4)):
            with self.subTest(name):
                rc, _ = self.m.ctrl(0x40, req, value, index, length, b"\xee" * length)
                self.assertEqual(rc, M.H_STALL)
                self.assertEqual(self.vendor_in(P.REQ_GET_INFO, P.INFO_SIZE)[0], M.H_OK)
        self.assertEqual(self.info()["nonce"], b"\x00" * 16, "a rejected nonce must not be stored")
        self.clean()

    def test_requests_before_the_address_is_set_are_ignored_by_the_wrong_address(self):
        self.m.attach()
        rc, _ = self.m.ctrl(0x80, 6, 0x0100, 0, 18)
        self.assertEqual(rc, M.H_OK)
        rc, _ = self.m.ctrl(0x00, 5, 7, 0, 0)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(self.m.lib.model_host_addr(), 7)
        self.m.lib.model_bus_reset(1)         # host reset: back to address 0, the device must follow
        rc, _ = self.m.ctrl(0x80, 6, 0x0100, 0, 18)
        self.assertEqual(rc, M.H_OK)
        self.clean()

    def test_in_replies_that_end_on_a_packet_boundary_get_a_zero_length_packet(self):
        self.up()
        self.m.log(P.K_TEXT, b"t" * 48)            # 8 + 48 = 56 bytes of stream
        self.assertEqual(self.m.written, 56)
        rc, d = self.vendor_in(P.REQ_READ_RING, 4096, 0, 0)        # 8 + 56 = 64 bytes = one full packet, host wants more
        self.assertEqual((rc, len(d)), (M.H_OK, 64))
        rc, d = self.vendor_in(P.REQ_READ_RING, 64, 0, 0)          # host asked for exactly 64: no ZLP needed
        self.assertEqual((rc, len(d)), (M.H_OK, 64))
        self.clean()

    def test_new_setup_interrupting_a_transfer(self):
        for nrdy in (1, 0):
            with self.subTest(nrdy_after_pending=nrdy):
                self.m.close()
                self.m = M.Machine(lib(), ring_size=4096)
                self.m.lib.model_set_nrdy_after_pending(nrdy)
                self.up()
                # a GET_INFO whose data stage is never read, then a new SETUP
                self.assertEqual(self.m.setup_only([0xC0, P.REQ_GET_INFO, 0, 0, 0, 0, 112, 0]), M.H_OK)
                self.assertEqual(self.m.setup_only([0x80, 6, 0, 1, 0, 0, 18, 0]), M.H_OK)
                rc, d = self.m.lib.model_data_in, None
                got = (M.ctypes.c_uint8 * 64)()
                n = M.ctypes.c_int(0)
                self.assertEqual(self.m.lib.model_data_in(18, got, M.ctypes.byref(n)), M.H_OK)
                self.assertEqual(bytes(got[:n.value])[:2], bytes([18, 1]))
                self.assertEqual(self.m.lib.model_status(0, 1), M.H_OK)
                rc, d = self.vendor_in(P.REQ_GET_INFO, P.INFO_SIZE)
                self.assertEqual(rc, M.H_OK)
                self.clean()


class ResetTests(Base):
    def test_bus_reset_in_every_stage_of_a_transfer(self):
        self.up()
        stages = ("after setup", "after data", "after nonce data")
        for stage in stages:
            with self.subTest(stage):
                if stage == "after nonce data":
                    self.assertEqual(self.m.setup_only([0x40, P.REQ_SET_NONCE, 0, 0, 0, 0, 16, 0]), M.H_OK)
                elif stage == "after data":
                    self.assertEqual(self.m.setup_only([0xC0, P.REQ_GET_INFO, 0, 0, 0, 0, 112, 0]), M.H_OK)
                    got = (M.ctypes.c_uint8 * 200)()
                    n = M.ctypes.c_int(0)
                    self.assertEqual(self.m.lib.model_data_in(112, got, M.ctypes.byref(n)), M.H_OK)
                else:
                    self.assertEqual(self.m.setup_only([0xC0, P.REQ_GET_INFO, 0, 0, 0, 0, 112, 0]), M.H_OK)
                self.m.bus_reset()
                for name, rc, _ in self.m.enumerate(address=11):
                    self.assertEqual(rc, M.H_OK, "%s: %s" % (stage, name))
        self.assertEqual(self.info()["resets"], 1 + len(stages))
        self.clean()

    def test_reset_clears_the_address_and_configuration(self):
        self.up()
        self.m.bus_reset()
        self.assertEqual(self.m.flags & P.F_CONFIGURED, 0)
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.clean()

    def test_disconnect_then_reattach(self):
        self.up()
        self.m.detach()
        self.assertEqual(self.m.flags & (P.F_CONNECTED | P.F_CONFIGURED), 0)
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.assertEqual(self.m.flags & (P.F_CONNECTED | P.F_CONFIGURED), P.F_CONNECTED | P.F_CONFIGURED)
        self.clean()


def parse_defs(src):
    """#define NAME[(params)] body -> {NAME: (params or None, body)}; comments stripped; later duplicates win."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"\\\n", " ", src)
    out = {}
    for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+(\w+)(\(([^)]*)\))?[ \t]+([^\n]*)$", src, re.M):
        params = None if m.group(2) is None else [x.strip() for x in m.group(3).split(",") if x.strip()]
        out[m.group(1)] = (params, m.group(4).strip())
    return out


def call_text(name, args, params):
    return name if params is None else "%s(%s)" % (name, ",".join(str(a) for a in args))


def _split_args(s, i):
    """s[i] == '(' -> (list of argument strings, index after the matching ')')"""
    depth, args, cur = 0, [], ""
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "(":
            depth += 1
            if depth > 1:
                cur += ch
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append(cur)
                return [a.strip() for a in args], j + 1
            cur += ch
        elif ch == "," and depth == 1:
            args.append(cur)
            cur = ""
        else:
            cur += ch
        j += 1
    raise ValueError("unbalanced parentheses in %r" % s)


def _expand(expr, defs, depth=0):
    if depth > 24:
        raise ValueError("macro expansion too deep: %r" % expr)
    out, i = "", 0
    while i < len(expr):
        m = re.compile(r"[A-Za-z_]\w*").match(expr, i)
        if not m:
            out += expr[i]
            i += 1
            continue
        name = m.group(0)
        i = m.end()
        if name in ("BIT", "GENMASK"):
            out += name
            continue
        if name not in defs:
            out += name
            continue
        params, body = defs[name]
        if params is None:
            out += "(" + _expand(body, defs, depth + 1) + ")"
            continue
        if i >= len(expr) or expr[i] != "(":
            out += name
            continue
        args, i = _split_args(expr, i)
        args = [_expand(a, defs, depth + 1) for a in args]
        b = body
        for p, a in zip(params, args):
            b = re.sub(r"\b%s\b" % re.escape(p), "(" + a + ")", b)
        out += "(" + _expand(b, defs, depth + 1) + ")"
    return out


def c_eval(expr, defs):
    e = _expand(expr, defs)
    e = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", e)
    e = re.sub(r"\(u(8|16|32|64)\)", "", e)
    return eval(e, {"__builtins__": {}}, {"BIT": lambda n: 1 << n,
                                          "GENMASK": lambda h, l: ((1 << (h - l + 1)) - 1) << l})


class StaticTests(unittest.TestCase):
    def test_wire_constants_match_the_header(self):
        h = _slurp(ENGINE_H)

        def const(name):
            m = re.search(r"#define\s+%s\s+(0x[0-9a-fA-F]+|\d+)u?\b" % name, h)
            self.assertIsNotNone(m, name)
            return int(m.group(1), 0)
        for hname, pname in (("USBMON_VID", "VID"), ("USBMON_PID", "PID"), ("USBMON_PROTO_VERSION", "PROTO_VERSION"),
                             ("USBMON_REQ_GET_INFO", "REQ_GET_INFO"), ("USBMON_REQ_READ_RING", "REQ_READ_RING"),
                             ("USBMON_REQ_GET_EXC", "REQ_GET_EXC"), ("USBMON_REQ_SET_NONCE", "REQ_SET_NONCE"),
                             ("USBMON_REQ_PEEK", "REQ_PEEK"), ("USBMON_READ_MAX", "READ_MAX"),
                             ("USBMON_NONCE_LEN", "NONCE_LEN"), ("USBMON_BOOT_ID_LEN", "BOOT_ID_LEN"),
                             ("USBMON_K_TEXT", "K_TEXT"), ("USBMON_K_STAGE", "K_STAGE"), ("USBMON_K_FAULT", "K_FAULT"),
                             ("USBMON_K_BOOT", "K_BOOT"), ("USBMON_K_MARK", "K_MARK"), ("USBMON_K_DROP", "K_DROP"),
                             ("USBMON_REC_HDR", "REC_HDR"), ("USBMON_REC_MAX", "REC_MAX")):
            self.assertEqual(const(hname), getattr(P, pname), hname)
        for bit, pname in ((0, "F_NONCE_SET"), (1, "F_FAULT"), (2, "F_HOLD"), (3, "F_CONNECTED"), (4, "F_CONFIGURED")):
            hname = "USBMON_" + pname
            m = re.search(r"#define\s+%s\s+BIT\((\d+)\)" % hname, h)
            self.assertIsNotNone(m, hname)
            self.assertEqual(1 << int(m.group(1)), getattr(P, pname), hname)

    # Names dwc3_regs.h introduces that the vendor headers do not define (the event decoding helpers, which the vendor driver
    # expresses as bit-field structs). Anything else must exist in the pinned headers with the same value.
    OWN_NAMES = ["DWC3_EVT_DEV_RAWTYPE", "DWC3_EVT_DEV_TYPE", "DWC3_EVT_EP_EVENT", "DWC3_EVT_EP_NUM", "DWC3_EVT_EP_PARAMS",
                 "DWC3_EVT_EP_STATUS", "DWC3_EVT_IS_DEVSPEC"]

    def test_dwc3_constants_match_the_pinned_vendor_headers(self):
        text = vendor_file("drivers/usb/dwc3/core.h") + "\n" + vendor_file("drivers/usb/dwc3/gadget.h")
        theirs, ours = parse_defs(text), parse_defs(_slurp(REGS_H))
        own, checked, mismatches = [], 0, []
        for name, (params, body) in sorted(ours.items()):
            if name in ("USBMON_DWC3_REGS_H", "BIT"):
                continue
            if name not in theirs:
                own.append(name)
                continue
            checked += 1
            samples = [()] if params is None else [(1,), (3,), (0x15,)] if len(params) == 1 else [(1, 2)]
            for args in samples:
                va = c_eval(call_text(name, args, params), ours)
                vb = c_eval(call_text(name, args, theirs[name][0]), theirs)
                if va != vb:
                    mismatches.append("%s%s: ours %#x vendor %#x" % (name, args, va, vb))
        self.assertEqual(mismatches, [])
        self.maxDiff = None
        self.assertEqual(sorted(own), sorted(self.OWN_NAMES))
        self.assertGreater(checked, 90)

    def test_the_vendor_cross_check_notices_a_wrong_value(self):
        text = "#define DWC3_DCTL_RUN_STOP\tBIT(31)\n#define DWC3_DEPCMD_CMDACT BIT(10)\n#define X(n) ((n) << 3)\n"
        good = parse_defs(text)
        bad = parse_defs(text.replace("BIT(31)", "BIT(30)").replace("<< 3", "<< 4"))
        self.assertNotEqual(c_eval("DWC3_DCTL_RUN_STOP", good), c_eval("DWC3_DCTL_RUN_STOP", bad))
        self.assertNotEqual(c_eval("X(5)", good), c_eval("X(5)", bad))
        self.assertEqual(c_eval("DWC3_DEPCMD_CMDACT | DWC3_DCTL_RUN_STOP", good), (1 << 10) | (1 << 31))

    def test_the_engine_is_freestanding_aarch64_code(self):
        out = os.path.join(_TMP, "usbmon.o")
        flags = ["-target", "aarch64-freestanding", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-O2", "-Wall",
                 "-Wextra", "-Werror", "-c", "-I", os.path.join(HERE, "engine")]
        r = subprocess.run(["zig", "cc"] + flags + [ENGINE_C, "-o", out], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        syms = undefined_symbols(out)
        self.assertEqual(syms, [], "the engine must not need libc or the compiler runtime: %s" % syms)
        # the testing hook must not be part of the loader build
        self.assertNotIn("usbmon_log_interrupted", defined_symbols(out))
        for fn in ("usbmon_init", "usbmon_poll", "usbmon_log", "usbmon_fault", "usbmon_hold", "usbmon_crc8"):
            self.assertIn(fn, defined_symbols(out))

    def test_dma_block_members_are_only_touched_through_the_port(self):
        src = _slurp(ENGINE_C)
        for lineno, line in enumerate(src.splitlines(), 1):
            for m in re.finditer(r"m->dma\.\w+", line):
                before = line[:m.start()]
                ok = before.rstrip().endswith("&") or re.search(r"usbmon_dma_\w+\([^;]*$", before) or "usbmon_dma_" in line
                self.assertTrue(ok, "line %d reads or writes DMA memory directly: %s" % (lineno, line.strip()))


def _elf_symbols(path):
    data = _slurp(path, "rb")
    assert data[:4] == b"\x7fELF" and data[4] == 2 and data[5] == 1, "not an ELF64 little endian object"
    e_shoff, = struct.unpack_from("<Q", data, 0x28)
    e_shentsize, e_shnum = struct.unpack_from("<HH", data, 0x3A)
    secs = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from("<IIQQQQIIQQ", data, o)
        secs.append((typ, off, size, link, entsize))
    out = []
    for typ, off, size, link, entsize in secs:
        if typ != 2:                                  # SHT_SYMTAB
            continue
        stroff = secs[link][1]
        for k in range(size // entsize):
            nm, info, other, shndx, value, sz = struct.unpack_from("<IBBHQQ", data, off + k * entsize)
            end = data.index(b"\0", stroff + nm)
            out.append((data[stroff + nm:end].decode(), shndx, info))
    return out


def undefined_symbols(path):
    return sorted(n for n, shndx, info in _elf_symbols(path) if n and shndx == 0)


def defined_symbols(path):
    return sorted(n for n, shndx, info in _elf_symbols(path) if n and shndx != 0)


class SeededDefectTests(unittest.TestCase):
    """Each case breaks one line of the engine and requires a named failure: the suite would catch the defect."""

    def build_mutant(self, old, new):
        src = _slurp(ENGINE_C)
        self.assertEqual(src.count(old), 1, "mutation anchor must occur exactly once: %r" % old)
        path = os.path.join(_TMP, "mut-%d.c" % abs(hash(old + new)))
        with open(path, "w") as f:
            f.write(src.replace(old, new))
        # a mutant may leave a parameter unused: only a compile error is a failure here
        return M.build(engine_src=path, out_dir=_TMP, extra=["-I", os.path.join(HERE, "engine")], strict=False)

    def machine(self, old, new, **kw):
        m = M.Machine(self.build_mutant(old, new), ring_size=4096, **kw)
        self.addCleanup(m.close)
        return m

    def enumerate_ok(self, m):
        m.attach()
        return [n for n, rc, _ in m.enumerate() if rc != M.H_OK]

    def test_missing_trb_clean_is_caught(self):
        m = self.machine("usbmon_dma_sync(m->dma.trb, ntrb * sizeof(struct dwc3_trb));", "")
        self.enumerate_ok(m)
        self.assertTrue(any("dirty cache line" in v for v in m.violations()), m.violations())

    def test_missing_setup_invalidate_is_caught(self):
        m = self.machine("usbmon_dma_sync(m->dma.setup, 64);", "")
        self.enumerate_ok(m)
        self.assertTrue(any("stale cache" in v for v in m.violations()), m.violations())

    def test_missing_event_invalidate_is_caught(self):
        m = self.machine("usbmon_dma_sync(m->dma.events, bytes);", "")
        self.enumerate_ok(m)
        self.assertTrue(any("stale cache" in v for v in m.violations()), m.violations())

    def test_missing_reply_clean_is_caught(self):
        m = self.machine("usbmon_dma_sync(m->dma.reply, (len + 63u) & ~63u);", "")
        self.enumerate_ok(m)
        self.assertTrue(any("dirty cache line" in v for v in m.violations()), m.violations())

    def test_missing_zero_length_packet_hangs_the_data_stage(self):
        m = self.machine("int zlp = (len && !(len % m->mps) && len < want);", "int zlp = 0;")
        self.assertEqual(self.enumerate_ok(m), [])
        m.log(P.K_TEXT, b"t" * 48)
        rc, _ = m.ctrl(0xC0, P.REQ_READ_RING, 0, 0, 4096)
        self.assertEqual(rc, M.H_NAKLOOP)

    def test_swapped_transfer_address_words_are_caught(self):
        m = self.machine("(uint32_t)(a >> 32), (uint32_t)a, 0);", "(uint32_t)a, (uint32_t)(a >> 32), 0);")
        self.assertEqual(m.init_rc, -3)

    def test_wrong_resource_index_on_endtransfer_is_caught(self):
        m = self.machine("DWC3_DEPCMD_PARAM(m->ep_rsc[ep]), 0, 0, 0);", "DWC3_DEPCMD_PARAM(0), 0, 0, 0);")
        m.attach()
        self.assertEqual(m.setup_only([0xC0, P.REQ_GET_INFO, 0, 0, 0, 0, 112, 0]), M.H_OK)
        m.bus_reset()
        self.assertTrue(any("resource index" in v for v in m.violations()), m.violations())

    def test_ring_that_drops_bytes_instead_of_records_is_caught(self):
        m = self.machine("m->oldest += USBMON_REC_HDR + ((uint32_t)h[4] | ((uint32_t)h[5] << 8));", "m->oldest += 1;")
        self.assertEqual(self.enumerate_ok(m), [])
        for i in range(60):
            m.text("%03d" % i * 60)
        hdr = m.ring_bytes(m.oldest, 8)
        self.assertNotEqual(P.crc8(hdr[:7]), hdr[7])

    def test_a_poly_change_in_the_crc_is_caught(self):
        m = self.machine("crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);",
                         "crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);")
        m.text("crc")
        hdr = m.ring_bytes(0, 8)
        self.assertNotEqual(hdr[7], P.crc8(hdr[:7]))

    def test_second_fault_overwriting_the_first_is_caught(self):
        m = self.machine("if (!m->exc.valid) {", "if (1) {")
        self.assertEqual(self.enumerate_ok(m), [])
        m.fault(esr=1)
        m.fault(esr=2)
        e = P.parse_exc(m.ctrl(0xC0, P.REQ_GET_EXC, 0, 0, P.EXC_SIZE)[1])
        self.assertNotEqual(e["esr"], 1)

    def test_high_offset_bits_ignored_is_caught(self):
        def scenario(m):
            self.assertEqual(self.enumerate_ok(m), [])
            for i in range(5):
                m.text("line %d" % i)
            m.lib.t_set_stream_base(0x30000)
            m.text("after the base moved")
            rc, d = m.ctrl(0xC0, P.REQ_READ_RING, 0x000A, 0x0003, 4096)      # stream offset 0x3000a
            self.assertEqual(rc, M.H_OK)
            return P.parse_ring_reply(d), m

        # the unmodified engine serves exactly that offset (so the scenario is not vacuous) ...
        good = M.Machine(M.build(out_dir=_TMP), ring_size=4096)
        self.addCleanup(good.close)
        (start, end, payload), _ = scenario(good)
        self.assertEqual(start, 0x3000A)
        self.assertEqual(payload, good.ring_bytes(0x3000A, len(payload)))
        self.assertEqual(len(payload), 8 + len("after the base moved") - 10)
        # ... and the engine that drops wIndex serves something else
        (start, end, payload), _ = scenario(self.machine("off = ((uint64_t)c->index << 16) | c->value;", "off = c->value;"))
        self.assertNotEqual(start, 0x3000A)

    def test_unacknowledged_events_are_caught(self):
        m = self.machine("WR(m, DWC3_GEVNTCOUNT(0), count);", "")
        failed = self.enumerate_ok(m)
        self.assertTrue(failed or m.violations(), "the engine never acknowledging events must show up")

    def test_vendor_requests_with_the_wrong_type_constant_are_caught(self):
        m = self.machine("case 0x40:\t/* vendor, device */", "case 0x20:\t/* vendor, device */")
        m.attach()
        m.enumerate()
        rc, _ = m.ctrl(0xC0, P.REQ_GET_INFO, 0, 0, P.INFO_SIZE)
        self.assertEqual(rc, M.H_STALL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
