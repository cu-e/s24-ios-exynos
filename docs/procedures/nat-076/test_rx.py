#!/usr/bin/env python3
"""Host tests of the NAT-076 bulk-OUT receive engine (engine/usbmon.c) against the DWC3 / cache / USB-host model (model/model.c).

Evidence kind: host-test. The model is a written-down reading of the vendor dwc3 driver (pinned s24-linux commit, see
model/model.c); passing here shows consistency with that reading and with the DMA discipline. It says nothing about the S24's
controller, about the S2MPU/PMMU in front of its DMA (NAT-040 item U5), or about the host-to-phone data rate.

    python3 -I docs/procedures/nat-076/test_rx.py          # from the repository root
"""
import atexit
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdefs  # noqa: E402
import modelhost as M  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
VENDOR = os.path.join(ROOT, "references", "s24-linux")
VENDOR_PIN = "417484173abc2c4fa93e738ea82ad9f2e84911b1"
ENGINE_C = os.path.join(HERE, "engine", "usbmon.c")
ENGINE_H = os.path.join(HERE, "engine", "usbmon.h")
REGS_H = os.path.join(HERE, "engine", "dwc3_regs.h")
SENDER = os.environ.get("ROOT_SEND_UNDER_TEST", os.path.join(ROOT, "tools", "ios", "root_send.py"))	# mutate_rx.py points this at a mutant

KIB = 1024
_TMP = tempfile.mkdtemp(prefix="nat076-test-", dir=os.environ.get("TMPDIR"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
_LIB = None


def lib():
    global _LIB
    if _LIB is None:
        _LIB = M.build(out_dir=_TMP)
    return _LIB


def slurp(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def vendor_file(path):
    r = subprocess.run(["git", "-C", VENDOR, "show", "%s:%s" % (VENDOR_PIN, path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise unittest.SkipTest("pinned vendor tree not available at %s (%s)" % (VENDOR, r.stderr.strip()[:80]))
    return r.stdout


# ---- struct usbmon_rx, laid out from the header text (natural alignment), not from the sender's format string
def header_layout():
    h = slurp(ENGINE_H)
    body = re.search(r"struct usbmon_rx \{[^\n]*\n(.*?)\n\};", h, re.S).group(1)
    sizes = {"uint8_t": 1, "uint16_t": 2, "uint32_t": 4, "uint64_t": 8}
    off, fields = 0, {}
    for line in body.splitlines():
        m = re.match(r"\s*(uint\d+_t)\s+(\w+)(\[(\d+)\])?;", line)
        if not m:
            continue
        sz = sizes[m.group(1)]
        count = int(m.group(4)) if m.group(4) else 1
        off = (off + sz - 1) // sz * sz
        fields[m.group(2)] = (off, sz, count)
        off += sz * count
    return fields, off


LAYOUT, LAYOUT_SIZE = header_layout()


def rxf(raw):
    out = {}
    for name, (off, sz, count) in LAYOUT.items():
        if count > 1:
            out[name] = bytes(raw[off:off + count])
        else:
            out[name] = int.from_bytes(raw[off:off + sz], "little")
    return out


def ref_sum(data):
    """The checksum written out from its definition in usbmon.h (sum of w[i] * (2i+1) mod 2^64), word by word."""
    total = 0
    for i in range(0, len(data), 8):
        total += int.from_bytes(data[i:i + 8], "little") * (2 * (i // 8) + 1)
    return total % (1 << 64)


def blob(n, seed=1):
    import random
    return random.Random(seed).randbytes(n)


class Base(unittest.TestCase):
    CAP = 1024 * KIB
    DIRECT = False

    def setUp(self):
        self.m = M.Machine(lib(), rx_size=self.CAP, rx_direct=self.DIRECT)
        self.assertEqual(self.m.init_rc, 0)
        self.up()

    def tearDown(self):
        self.m.close()

    def up(self):
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)

    def clean(self):
        self.assertEqual(self.m.violations(), [])

    def rx(self):
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        self.assertEqual(rc, M.H_OK)
        return rxf(raw)

    def begin(self, off, n, flags=0, wlength=16):
        return self.m.ctrl(0x40, 6, 0, 0, wlength, data=struct.pack("<QII", off, n, flags)[:wlength])[0]

    def put(self, off, data, expect_rc=M.H_OK):
        """RX_BEGIN + the bulk data of one chunk. -> (rx dict after, accepted)"""
        self.assertEqual(self.begin(off, len(data)), M.H_OK)
        rc, took = self.m.bulk_out(data)
        self.assertEqual(rc, expect_rc)
        return self.rx(), took

    def sentinel(self, off, n):
        return self.m.dest(off, n) == b"\xEE" * n

    def abort(self):
        return self.m.ctrl(0x40, 8, 0, 0, 0)[0]


class ProtocolTests(Base):
    def test_get_rx_describes_the_receive_path(self):
        r = self.rx()
        self.assertEqual((r["magic"], r["version"], r["size"]), (b"S24R", 1, 120))
        self.assertEqual((r["state"], r["committed"], r["capacity"]), (0, 0, self.CAP))
        self.assertEqual(r["flags"], 0b111 if self.DIRECT else 0b011)
        self.assertEqual(r["chunk_max"], 0x800000 if self.DIRECT else 65536)

    def test_configuration_descriptor_announces_the_bulk_endpoint(self):
        rc, d = self.m.ctrl(0x80, 6, 0x0200, 0, 64)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(struct.unpack_from("<H", d, 2)[0], 25)
        self.assertEqual(len(d), 25)
        self.assertEqual(d[9:11], bytes([9, 4]))
        self.assertEqual(d[13], 1)				# bNumEndpoints
        self.assertEqual(d[18:25], bytes([7, 5, 0x01, 0x02, 0x00, 0x02, 0]))	# endpoint 1 OUT, bulk, 512 bytes

    def test_one_chunk(self):
        data = blob(8 * KIB, seed=2)
        r, took = self.put(0, data)
        self.assertEqual(took, len(data))
        self.assertEqual((r["state"], r["committed"], r["rx_bytes"], r["rx_trbs"], r["rx_errors"]), (0, len(data), len(data), 1, 0))
        self.assertEqual((r["last_off"], r["last_len"], r["last_sum"]), (0, len(data), ref_sum(data)))
        self.assertEqual((r["last_trb_status"], r["last_residual"]), (0, 0))
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.clean()

    def test_many_chunks_across_the_trb_ring(self):
        data = blob(40 * 4 * KIB, seed=3)
        pos = 0
        for k in range(40):			# the ring has 3 data slots: 13 laps
            r, _ = self.put(pos, data[pos:pos + 4 * KIB])
            pos += 4 * KIB
            self.assertEqual((r["committed"], r["rx_trbs"], r["state"]), (pos, k + 1, 0))
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assertEqual(r["rx_bytes"], len(data))
        self.clean()

    def test_chunk_sizes(self):
        sizes = [512, 1024, 4096, 16 * KIB, 60 * KIB, 64 * KIB]
        pos = 0
        for k, n in enumerate(sizes):
            d = blob(n, seed=100 + k)
            r, _ = self.put(pos, d)
            self.assertEqual((r["committed"], r["last_sum"]), (pos + n, ref_sum(d)))
            self.assertEqual(self.m.dest(pos, n), d)
            pos += n
        self.clean()

    def test_the_last_chunk_may_end_exactly_at_the_capacity(self):
        cap = self.CAP
        d = blob(64 * KIB, seed=4)
        pos = 0
        while pos + 64 * KIB < cap:
            self.put(pos, d)
            pos += 64 * KIB
        r, _ = self.put(pos, d)
        self.assertEqual(r["committed"], cap)
        self.clean()

    def test_refusals_leave_the_state_alone(self):
        d = blob(4 * KIB, seed=5)
        self.put(0, d)
        before = self.rx()
        cases = [
            ("duplicate offset", lambda: self.begin(0, 4 * KIB), "rx_dups"),
            ("offset inside the committed range", lambda: self.begin(2048, 4 * KIB), "rx_dups"),
            ("gap", lambda: self.begin(8 * KIB, 4 * KIB), "rx_gaps"),
            ("zero length", lambda: self.begin(4 * KIB, 0), "rx_rejects"),
            ("length not a multiple of 512", lambda: self.begin(4 * KIB, 1000), "rx_rejects"),
            ("length 1", lambda: self.begin(4 * KIB, 1), "rx_rejects"),
            ("longer than the chunk limit", lambda: self.begin(4 * KIB, (0x800000 if self.DIRECT else 65536) + 512), "rx_rejects"),
            ("past the capacity", lambda: self.begin(4 * KIB, self.CAP), "rx_rejects"),
            ("flags set", lambda: self.begin(4 * KIB, 4 * KIB, flags=1), "rx_rejects"),
        ]
        for name, call, counter in cases:
            with self.subTest(name):
                self.assertEqual(call(), M.H_STALL)
                after = self.rx()
                self.assertEqual(after["state"], 0)
                self.assertEqual(after["committed"], before["committed"])
                self.assertEqual(after[counter], before[counter] + 1)
                before = after
        self.assertEqual(self.begin(4 * KIB, 4 * KIB, wlength=12), M.H_STALL)		# a short RX_BEGIN block
        self.assertEqual(self.begin(4 * KIB, 4 * KIB, wlength=0), M.H_STALL)
        # none of that disturbed the next, correct chunk
        r, _ = self.put(4 * KIB, blob(4 * KIB, seed=6))
        self.assertEqual(r["committed"], 8 * KIB)
        self.clean()

    def test_begin_while_armed_is_refused_and_the_first_transfer_survives(self):
        a, b = blob(4 * KIB, seed=7), blob(4 * KIB, seed=8)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
        self.assertEqual(self.rx()["state"], 1)
        rc, took = self.m.bulk_out(a)
        self.assertEqual((rc, took), (M.H_OK, 4 * KIB))
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_rejects"]), (0, 4 * KIB, 1))
        self.assertEqual(self.m.dest(0, 4 * KIB), a)
        r, _ = self.put(4 * KIB, b)
        self.assertEqual(r["committed"], 8 * KIB)
        self.clean()

    def test_begin_before_the_device_is_configured_is_refused(self):
        self.m.bus_reset()					# back to the default state: no configuration
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
        self.assertEqual(self.m.ctrl(0xC0, 7, 0, 0, 120)[1][12] & 2, 0)		# ENABLED is clear
        self.up()
        r, _ = self.put(0, blob(4 * KIB, seed=9))
        self.assertEqual(r["committed"], 4 * KIB)

    def test_get_rx_argument_rules(self):
        for value, index, length in ((1, 0, 120), (0, 1, 120), (0, 0, 0)):
            self.assertEqual(self.m.ctrl(0xC0, 7, value, index, length)[0], M.H_STALL, (value, index, length))
        rc, d = self.m.ctrl(0xC0, 7, 0, 0, 16)
        self.assertEqual((rc, len(d)), (M.H_OK, 16))		# a shorter read gets the head of the block
        self.assertEqual(self.m.ctrl(0x40, 7, 0, 0, 0)[0], M.H_STALL)		# GET_RX is an IN request

    def test_abort_ends_an_armed_transfer_and_commits_nothing(self):
        d = blob(8 * KIB, seed=10)
        self.assertEqual(self.begin(0, 8 * KIB), M.H_OK)
        self.m.bulk_out(d[:2 * KIB])
        self.assertEqual(self.abort(), M.H_OK)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_aborts"], r["rx_errors"]), (0, 0, 1, 0))
        r, _ = self.put(0, d)					# the same offset again, now with all the data
        self.assertEqual((r["committed"], r["last_sum"]), (8 * KIB, ref_sum(d)))
        self.assertEqual(self.m.dest(0, 8 * KIB), d)
        self.clean()

    def test_abort_when_idle_does_nothing(self):
        self.assertEqual(self.abort(), M.H_OK)
        r = self.rx()
        self.assertEqual((r["state"], r["rx_aborts"]), (0, 0))
        self.assertEqual(self.m.ctrl(0x40, 8, 0, 0, 4, data=b"abcd")[0], M.H_STALL)	# RX_ABORT carries no data
        self.clean()

    def test_short_packet_fails_the_chunk_and_it_can_be_sent_again(self):
        d = blob(4 * KIB, seed=11)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(d[:4 * KIB - 100])
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_errors"]), (2, 0, 1))
        self.assertTrue(r["last_evt_status"] & 2, r["last_evt_status"])		# the SHORT status bit
        self.assertEqual(r["rx_trbs"], 0)
        r, _ = self.put(0, d)
        self.assertEqual((r["state"], r["committed"], r["rx_errors"]), (0, 4 * KIB, 1))
        self.assertEqual(self.m.dest(0, 4 * KIB), d)
        self.clean()

    def test_bus_error_fails_the_chunk(self):
        d = blob(4 * KIB, seed=12)
        self.m.bulk_fault(1, after=1500)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(d)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_errors"]), (2, 0, 1))
        self.assertTrue(r["last_evt_status"] & 1, r["last_evt_status"])		# BUSERR
        r, _ = self.put(0, d)
        self.assertEqual((r["state"], r["committed"]), (0, 4 * KIB))
        self.clean()

    def test_trb_error_status_fails_the_chunk(self):
        d = blob(4 * KIB, seed=13)
        self.m.bulk_fault(2, after=0)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(d)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_errors"]), (2, 0, 1))
        self.assertEqual(r["last_trb_status"], 3)
        r, _ = self.put(0, d)
        self.assertEqual(r["committed"], 4 * KIB)
        self.clean()

    def test_failed_chunk_never_moves_the_committed_offset_over_good_data(self):
        a, b = blob(4 * KIB, seed=14), blob(4 * KIB, seed=15)
        self.put(0, a)
        self.m.bulk_fault(1, after=0)
        self.assertEqual(self.begin(4 * KIB, 4 * KIB), M.H_OK)
        self.m.bulk_out(b)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"]), (2, 4 * KIB))
        self.assertEqual(self.m.dest(0, 4 * KIB), a)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)		# going back is still refused
        r, _ = self.put(4 * KIB, b)
        self.assertEqual((r["state"], r["committed"]), (0, 8 * KIB))
        self.assertEqual(self.m.dest(0, 8 * KIB), a + b)
        self.clean()

    def test_more_data_than_armed_is_not_taken(self):
        d = blob(2 * KIB, seed=16)
        self.assertEqual(self.begin(0, 1 * KIB), M.H_OK)
        rc, took = self.m.bulk_out(d)
        self.assertEqual((rc, took), (M.H_NAKLOOP, 1 * KIB))		# the controller stops taking data at the end of the TRB
        r = self.rx()
        self.assertEqual((r["state"], r["committed"]), (0, 1 * KIB))
        self.assertEqual(self.m.dest(0, 1 * KIB), d[:1 * KIB])
        self.assertTrue(self.sentinel(1 * KIB, 1 * KIB))		# nothing beyond the chunk was written
        self.clean()

    def test_bus_reset_mid_transfer_keeps_the_committed_offset(self):
        a, b = blob(4 * KIB, seed=17), blob(8 * KIB, seed=18)
        self.put(0, a)
        self.assertEqual(self.begin(4 * KIB, 8 * KIB), M.H_OK)
        self.m.bulk_out(b[:3 * KIB])
        self.m.bus_reset()
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_resets"]), (2, 4 * KIB, 1))
        self.assertEqual(r["flags"] & 2, 0)				# the endpoint is disabled until SET_CONFIGURATION
        self.assertEqual(self.begin(4 * KIB, 8 * KIB), M.H_STALL)
        self.up()
        r, _ = self.put(4 * KIB, b)
        self.assertEqual((r["state"], r["committed"], r["flags"] & 2), (0, 12 * KIB, 2))
        self.assertEqual(self.m.dest(0, 12 * KIB), a + b)
        self.clean()

    def test_disconnect_mid_transfer_and_reattach(self):
        a, b = blob(4 * KIB, seed=19), blob(4 * KIB, seed=20)
        self.put(0, a)
        self.assertEqual(self.begin(4 * KIB, 4 * KIB), M.H_OK)
        self.m.bulk_out(b[:1 * KIB])
        self.m.detach()
        self.m.attach()
        self.up()
        r = self.rx()
        self.assertEqual((r["committed"], r["rx_resets"]), (4 * KIB, 1))
        r, _ = self.put(4 * KIB, b)
        self.assertEqual(r["committed"], 8 * KIB)
        self.assertEqual(self.m.dest(0, 8 * KIB), a + b)
        self.clean()

    def test_resets_while_idle_are_not_counted_as_lost_transfers(self):
        self.put(0, blob(4 * KIB, seed=21))
        self.m.bus_reset()
        self.up()
        r = self.rx()
        self.assertEqual((r["rx_resets"], r["rx_errors"], r["state"], r["committed"]), (0, 0, 0, 4 * KIB))

    def test_repeated_set_configuration_keeps_working(self):
        for _ in range(3):
            self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        r, _ = self.put(0, blob(4 * KIB, seed=22))
        self.assertEqual(r["committed"], 4 * KIB)
        self.assertEqual(self.m.ctrl(0x00, 9, 0, 0, 0)[0], M.H_OK)		# unconfigure: the endpoint goes away
        self.assertEqual(self.rx()["flags"] & 2, 0)
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        self.assertEqual(self.rx()["flags"] & 2, 2)
        r, _ = self.put(4 * KIB, blob(4 * KIB, seed=23))
        self.assertEqual(r["committed"], 8 * KIB)
        self.clean()

    def test_the_log_stream_keeps_working_while_a_transfer_is_armed(self):
        d = blob(4 * KIB, seed=24)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.text("logged while armed")
        rc, info = self.m.ctrl(0xC0, 1, 0, 0, 112)
        self.assertEqual((rc, len(info)), (M.H_OK, 112))
        rc, ring = self.m.ctrl(0xC0, 2, 0, 0, 4096)
        self.assertEqual(rc, M.H_OK)
        self.assertIn(b"logged while armed", ring)
        self.m.bulk_out(d)
        self.assertEqual(self.rx()["committed"], 4 * KIB)
        self.clean()

    def test_standard_endpoint_status_for_the_bulk_endpoint(self):
        self.assertEqual(self.m.ctrl(0x82, 0, 0, 0x01, 2), (M.H_OK, b"\x00\x00"))
        self.assertEqual(self.m.ctrl(0x82, 0, 0, 0x02, 2)[0], M.H_STALL)		# endpoint 2 does not exist
        self.assertEqual(self.m.ctrl(0x02, 1, 0, 0x01, 0)[0], M.H_OK)		# CLEAR_FEATURE(ENDPOINT_HALT) is accepted
        self.clean()

    # ---- every byte of the request block, from the layout in usbmon.h (offset 0..7, length 8..11, flags 12..15)

    def chunk_limit(self):
        return 0x800000 if self.DIRECT else 65536

    def test_the_low_byte_of_the_offset_is_compared(self):
        self.put(0, blob(4 * KIB, seed=40))
        gaps = self.rx()["rx_gaps"]
        for off in (4 * KIB + 1, 4 * KIB + 255, 4 * KIB + (1 << 40), (1 << 63) + 4 * KIB):
            with self.subTest(offset=off):
                self.assertEqual(self.begin(off, 4 * KIB), M.H_STALL)
                gaps += 1
                r = self.rx()
                self.assertEqual((r["rx_gaps"], r["state"], r["committed"]), (gaps, 0, 4 * KIB))
        r, _ = self.put(4 * KIB, blob(4 * KIB, seed=41))
        self.assertEqual(r["committed"], 8 * KIB)
        self.clean()

    def test_every_byte_of_the_length_counts(self):
        # accepted iff 0 < len <= chunk limit, len % 512 == 0 and the chunk fits: the rule written out here, not read from the engine
        lengths = [513, 767, 768, 0x10200, 0x1000200, 0x2000200, 0x80000200, 0xFFFFFE00, 0x100000, 0x7FFFFE00]
        for n in lengths:
            with self.subTest(length=hex(n)):
                ok = n % 512 == 0 and 0 < n <= self.chunk_limit() and n <= self.CAP
                before = self.rx()
                if ok:
                    self.assertEqual(self.begin(0, n), M.H_OK)
                    r = self.rx()
                    self.assertEqual((r["state"], r["armed_off"], r["armed_len"]), (1, 0, n))
                    self.assertEqual(self.abort(), M.H_OK)
                else:
                    self.assertEqual(self.begin(0, n), M.H_STALL)
                    r = self.rx()
                    self.assertEqual((r["state"], r["armed_len"]), (0, before["armed_len"]))
                    self.assertEqual(r["rx_rejects"], before["rx_rejects"] + 1)
        self.clean()

    def test_every_byte_of_the_flags_counts(self):
        rejects = self.rx()["rx_rejects"]
        for flags in (0x1, 0x100, 0x10000, 0x1000000, 0x80000000, 0xFFFFFFFF):
            with self.subTest(flags=hex(flags)):
                self.assertEqual(self.begin(0, 4 * KIB, flags=flags), M.H_STALL)
                rejects += 1
                self.assertEqual(self.rx()["rx_rejects"], rejects)
        self.assertEqual(self.rx()["state"], 0)
        r, _ = self.put(0, blob(4 * KIB, seed=42))
        self.assertEqual(r["committed"], 4 * KIB)

    # ---- what GET_RX reports

    def test_get_rx_names_the_armed_transfer(self):
        self.put(0, blob(8 * KIB, seed=43))
        self.assertEqual(self.begin(8 * KIB, 4 * KIB), M.H_OK)
        r = self.rx()
        self.assertEqual((r["state"], r["armed_off"], r["armed_len"]), (1, 8 * KIB, 4 * KIB))
        self.m.bulk_out(blob(4 * KIB, seed=44))
        self.assertEqual(self.rx()["committed"], 12 * KIB)

    def test_get_rx_names_the_last_completed_chunk(self):
        a, b = blob(8 * KIB, seed=45), blob(4 * KIB, seed=46)
        self.put(0, a)
        r, _ = self.put(8 * KIB, b)
        self.assertEqual((r["last_off"], r["last_len"], r["last_sum"]), (8 * KIB, 4 * KIB, ref_sum(b)))
        self.assertEqual((r["last_trb_status"], r["last_residual"]), (0, 0))
        self.assertEqual(r["last_evt_status"] & 0b11, 0)		# neither the bus-error nor the short-packet bit

    def test_get_rx_reports_the_residual_and_status_of_a_failed_trb(self):
        self.m.bulk_fault(3, after=1024)				# the TRB ends early with status OK and 3072 bytes left
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(blob(4 * KIB, seed=47))
        r = self.rx()
        self.assertEqual((r["state"], r["last_trb_status"], r["last_residual"]), (2, 0, 3 * KIB))
        self.assertEqual(r["committed"], 0)
        self.m.bulk_fault(2, after=0)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(blob(4 * KIB, seed=48))
        r = self.rx()
        self.assertEqual((r["state"], r["last_trb_status"]), (2, 3))
        self.assertEqual(r["last_len"], 0)				# nothing was ever committed: the last-chunk fields stay empty
        self.assertEqual(r["last_off"], 0)

    def test_get_rx_reserved_bytes_are_zero_whatever_was_sent_before(self):
        rc, info = self.m.ctrl(0xC0, 1, 0, 0, 112)			# a longer reply that used the same buffers
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(self.rx()["pad"], 0)

    # ---- requests that must not be mistaken for one another

    def test_set_nonce_after_rx_begin_is_a_nonce_not_a_chunk_request(self):
        r0, _ = self.put(0, blob(4 * KIB, seed=49))
        nonce = bytes(range(0x91, 0xA1))
        self.assertEqual(self.m.ctrl(0x40, 4, 0, 0, 16, data=nonce)[0], M.H_OK)
        rc, info = self.m.ctrl(0xC0, 1, 0, 0, 112)
        self.assertIn(nonce, info)
        r = self.rx()
        for k in ("rx_gaps", "rx_dups", "rx_rejects", "committed", "state"):
            self.assertEqual(r[k], r0[k], k)

    def test_clear_halt_is_accepted_only_for_the_configured_bulk_endpoint(self):
        self.assertEqual(self.m.ctrl(0x02, 1, 0, 0x02, 0)[0], M.H_STALL)	# endpoint 2 does not exist
        self.assertEqual(self.m.ctrl(0x02, 1, 0, 0x81, 0)[0], M.H_STALL)	# nor does an IN endpoint 1
        self.assertEqual(self.m.ctrl(0x02, 1, 1, 0x01, 0)[0], M.H_STALL)	# only ENDPOINT_HALT (feature 0) exists
        self.assertEqual(self.m.ctrl(0x02, 1, 0, 0x01, 2)[0], M.H_STALL)	# and it carries no data
        self.m.ctrl(0x00, 9, 0, 0, 0)					# unconfigured: the endpoint is gone
        self.assertEqual(self.m.ctrl(0x02, 1, 0, 0x01, 0)[0], M.H_STALL)
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        self.assertEqual(self.m.ctrl(0x02, 1, 0, 0x01, 0)[0], M.H_OK)

    # ---- controller behaviour the happy path never shows

    def configure_with_failing(self, code):
        """A fresh machine whose first endpoint command with DEPCMD code `code` after SET_ADDRESS fails once."""
        self.m.close()
        self.m = M.Machine(lib(), rx_size=self.CAP, rx_direct=self.DIRECT)
        self.m.attach()
        for bm, req, value, length in ((0x80, 6, 0x0100, 8), (0x00, 5, 5, 0), (0x80, 6, 0x0100, 18), (0x80, 6, 0x0200, 9),
                                       (0x80, 6, 0x0200, 18)):		# everything a host does before SET_CONFIGURATION
            self.assertEqual(self.m.ctrl(bm, req, value, 0, length)[0], M.H_OK)
        self.m.fail_next_cmd(code)
        return self.m.ctrl(0x00, 9, 1, 0, 0)[0]

    def test_a_failing_endpoint_command_fails_set_configuration_and_a_retry_works(self):
        for name, code in (("DEPSTARTCFG", 9), ("SETEPCONFIG", 1), ("SETTRANSFRESOURCE", 2), ("STARTTRANSFER", 6)):
            with self.subTest(command=name):
                self.assertEqual(self.configure_with_failing(code), M.H_STALL)
                rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
                self.assertEqual(rc, M.H_OK)
                self.assertEqual(rxf(raw)["flags"] & 2, 0)			# not enabled
                self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
                self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)	# the host tries again
                self.assertEqual(self.rx()["flags"] & 2, 2)
                r, _ = self.put(0, blob(4 * KIB, seed=50))
                self.assertEqual(r["committed"], 4 * KIB)
                self.clean()

    def test_a_failing_update_transfer_refuses_the_chunk_without_arming(self):
        self.m.fail_next_cmd(7)
        before = self.rx()
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_rejects"]), (0, 0, before["rx_rejects"] + 1))
        r, _ = self.put(0, blob(4 * KIB, seed=51))
        self.assertEqual((r["committed"], r["rx_errors"]), (4 * KIB, 0))
        self.clean()

    def test_nothing_new_is_started_while_an_end_transfer_is_pending(self):
        self.m.hold_endxfer()
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.assertEqual(self.abort(), M.H_OK)
        self.assertTrue(self.m.held)
        before = self.rx()
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)		# ENDTRANSFER has not completed yet
        self.assertEqual(self.rx()["rx_rejects"], before["rx_rejects"] + 1)
        self.m.release_held()
        r, _ = self.put(0, blob(4 * KIB, seed=52))
        self.assertEqual(r["committed"], 4 * KIB)
        self.clean()

    def test_a_failed_chunk_also_waits_for_the_end_transfer(self):
        self.m.hold_endxfer()
        self.m.bulk_fault(2)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(blob(4 * KIB, seed=53))
        self.assertTrue(self.m.held)					# the engine re-synchronises the endpoint after a failed TRB
        before = self.rx()["rx_rejects"]
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
        self.assertEqual(self.rx()["rx_rejects"], before + 1)
        self.m.release_held()
        r, _ = self.put(0, blob(4 * KIB, seed=54))
        self.assertEqual((r["committed"], r["rx_errors"]), (4 * KIB, 1))
        self.clean()

    def test_the_endpoint_is_not_enabled_while_an_end_transfer_is_pending(self):
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.hold_endxfer()
        self.m.bus_reset()					# the armed transfer is lost; the engine ends it
        self.assertTrue(self.m.held)
        steps = self.m.enumerate()
        self.assertEqual(steps[-1][1], M.H_STALL)			# SET_CONFIGURATION cannot enable the endpoint yet
        self.assertEqual(self.rx()["flags"] & 2, 0)
        self.m.release_held()
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        r, _ = self.put(0, blob(4 * KIB, seed=55))
        self.assertEqual(r["committed"], 4 * KIB)
        self.clean()

    def test_a_completion_event_nobody_asked_for_changes_nothing(self):
        r0, _ = self.put(0, blob(4 * KIB, seed=56))
        spurious = self.m.rx_spurious
        self.m.inject_ep_event(2, 2, status=4)			# XferInProgress+IOC with nothing armed
        self.assertEqual(self.m.rx_spurious, spurious + 1)
        r = self.rx()
        for k in ("committed", "rx_bytes", "rx_trbs", "rx_errors", "state", "last_off", "last_sum"):
            self.assertEqual(r[k], r0[k], k)
        r, _ = self.put(4 * KIB, blob(4 * KIB, seed=57))
        self.assertEqual(r["committed"], 8 * KIB)
        self.clean()

    def test_an_event_for_a_trb_the_controller_still_owns_is_ignored(self):
        d = blob(4 * KIB, seed=58)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.inject_ep_event(2, 2, status=4)			# the TRB's HWO bit is still set
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_errors"]), (1, 0, 0))
        self.m.bulk_out(d)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_errors"], r["last_sum"]), (0, 4 * KIB, 0, ref_sum(d)))
        self.clean()

    def test_a_disconnect_fails_the_armed_transfer_at_once(self):
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.detach()
        self.assertEqual(self.m.rx_state, 2)
        self.m.attach()
        self.up()
        r = self.rx()
        self.assertEqual((r["state"], r["rx_resets"], r["rx_errors"]), (0, 1, 1))		# SET_CONFIGURATION made it idle again


    # ---- the endpoint's own commands, register writes and ring memory (what the controller is told, not only what the host sees)

    DALEPENA = 0xC720
    DEPCMD_CODES = {"SETEPCONFIG": 1, "SETTRANSFRESOURCE": 2, "STARTTRANSFER": 6, "UPDATETRANSFER": 7, "ENDTRANSFER": 8, "DEPSTARTCFG": 9}

    def rx_cmds(self, trace, code=None):
        return [t for t in trace if t[0] == 2 and (code is None or t[1] & 0xF == code)]

    def dalepena_writes(self):
        return [v for off, v in self.m.write_trace() if off == self.DALEPENA]

    def views_agree(self):
        """The engine's record of 'a transfer is active' equals the controller's (two independent sources)."""
        self.assertEqual(self.m.engine_ep_started(2), self.m.hw_ep_started(2))

    def ring_start_address(self):
        start = self.rx_cmds(self.m.cmd_trace(), 6)[-1]
        return (start[2] << 32) | start[3]

    def test_enable_issues_the_vendor_command_sequence(self):
        tr = self.m.cmd_trace()
        i = max(k for k, t in enumerate(tr) if t[0] == 0 and t[1] == 0x409 | (2 << 16))		# DEPSTARTCFG, start config 2, on ep0
        seq = tr[i:i + 4]
        bulk, mps, ep, xfer_in_progress_en = 2, 512, 2, 1 << 9
        self.assertEqual([t[:5] for t in seq[:3]], [
            (0, 0x400 | 9 | (2 << 16), 0, 0, 0),									# CMDACT | DEPSTARTCFG | param 2
            (2, 0x400 | 1, (bulk << 1) | (mps << 3), xfer_in_progress_en | (ep << 25), 0),			# DEPCFG: bulk, 512, INIT, no FIFO
            (2, 0x400 | 2, 1, 0, 0)])									# DEPXFERCFG: one transfer resource
        self.assertEqual((seq[3][0], seq[3][1] & 0xF, seq[3][4]), (2, 6, 0))				# STARTTRANSFER, third parameter 0
        self.assertEqual((seq[3][2] << 32) | seq[3][3], self.ring_start_address())
        self.assertEqual(self.dalepena_writes()[-1], 0b111)						# endpoints 0, 1 and 2 enabled
        self.views_agree()
        self.assertEqual(self.m.hw_ep_started(2), 1)
        self.clean()

    def test_update_transfer_names_the_resource_index_and_has_no_parameters(self):
        rsc = (self.rx_cmds(self.m.cmd_trace(), 6)[-1][5] >> 16) & 0x7F
        n0 = len(self.m.cmd_trace())
        self.put(0, blob(4 * KIB, seed=140))
        upd = self.rx_cmds(self.m.cmd_trace()[n0:], 7)
        self.assertEqual(len(upd), 1)
        self.assertEqual(((upd[0][1] >> 16) & 0x7F, upd[0][2:5]), (rsc, (0, 0, 0)))
        self.clean()

    def test_end_transfer_names_the_resource_index_has_no_parameters_and_is_followed_by_a_fresh_start(self):
        rsc = (self.rx_cmds(self.m.cmd_trace(), 6)[-1][5] >> 16) & 0x7F
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        n0 = len(self.m.cmd_trace())
        self.assertEqual(self.abort(), M.H_OK)
        tr = self.m.cmd_trace()[n0:]
        ends, starts = self.rx_cmds(tr, 8), self.rx_cmds(tr, 6)
        self.assertEqual((len(ends), len(starts)), (1, 1))
        self.assertEqual(((ends[0][1] >> 16) & 0x7F, ends[0][2:5]), (rsc, (0, 0, 0)))
        self.assertEqual(starts[0][4], 0)
        self.assertLess(tr.index(ends[0]), tr.index(starts[0]))
        self.views_agree()
        self.clean()

    def test_dalepena_clears_only_the_receive_endpoint_and_sets_it_again(self):
        before = self.dalepena_writes()[-1]
        self.assertEqual(self.m.ctrl(0x00, 9, 0, 0, 0)[0], M.H_OK)
        off = self.dalepena_writes()[-1]
        self.assertEqual(off, before & ~4)
        self.views_agree()
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        self.assertEqual(self.dalepena_writes()[-1], off | 4)
        self.views_agree()
        self.clean()

    def test_disabling_what_is_not_enabled_touches_no_register(self):
        def writes_during(f):
            n = len(self.dalepena_writes())
            f()
            return len(self.dalepena_writes()) - n
        first = writes_during(lambda: self.m.ctrl(0x00, 9, 0, 0, 0))
        second = writes_during(lambda: self.m.ctrl(0x00, 9, 0, 0, 0))		# already disabled
        self.m.close()
        self.m = M.Machine(lib(), rx_size=0)					# an engine with no receive path at all
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        none = writes_during(lambda: self.m.ctrl(0x00, 9, 0, 0, 0))
        self.assertEqual(self.rx_cmds(self.m.cmd_trace()), [])
        self.assertEqual((first, second, none), (1, 0, 0))
        self.assertEqual(self.m.ctrl(0xC0, 7, 0, 0, 120)[0], M.H_STALL)	# no receive path: GET_RX is not served

    def test_flags_are_exact(self):
        present = 0b101 if self.DIRECT else 0b001
        self.assertEqual(self.rx()["flags"], present | 0b010)
        self.m.ctrl(0x00, 9, 0, 0, 0)
        self.assertEqual(self.rx()["flags"], present)

    def test_ring_slots_are_cleared_by_a_restart_and_the_link_slot_survives(self):
        self.put(0, blob(4 * KIB, seed=141))
        self.put(4 * KIB, blob(4 * KIB, seed=142))
        self.assertTrue(all(any(self.m.trb_slot(i)) for i in (0, 1)), [self.m.trb_slot(i) for i in range(4)])
        self.m.bulk_fault(2)							# the third chunk fails with a TRB status error: slot 2 keeps its status
        self.assertEqual(self.begin(8 * KIB, 4 * KIB), M.H_OK)
        self.m.bulk_out(blob(4 * KIB, seed=143))
        self.assertEqual(self.rx()["state"], 2)
        for i in range(3):
            self.assertEqual(self.m.trb_slot(i), (0, 0, 0, 0), "slot %d" % i)
        ring = self.ring_start_address()
        bpl, bph, size, ctrl = self.m.trb_slot(3)
        self.assertEqual(((bph << 32) | bpl, size, ctrl), (ring, 0, 0x80 | 1))	# link TRB (type 8) back to slot 0, HWO set
        self.assertEqual(self.begin(8 * KIB, 4 * KIB), M.H_OK)			# the next chunk goes into slot 0 again
        self.assertTrue(any(self.m.trb_slot(0)))
        self.assertEqual(self.m.trb_slot(1), (0, 0, 0, 0))
        self.views_agree()

    def test_the_controller_ending_the_transfer_by_itself_is_followed_by_a_fresh_start_not_an_end(self):
        d = blob(4 * KIB, seed=144)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.end_hw_transfer(2)
        self.m.inject_ep_event(2, 1)						# XferComplete: the TRB is still owned by the controller
        self.views_agree()
        self.assertEqual(self.m.engine_ep_started(2), 0)
        self.assertEqual(self.rx()["state"], 1)
        n0 = len(self.m.cmd_trace())
        self.assertEqual(self.abort(), M.H_OK)
        tr = self.m.cmd_trace()[n0:]
        self.assertEqual((self.rx_cmds(tr, 8), len(self.rx_cmds(tr, 6))), ([], 1))
        for i in range(3):
            self.assertEqual(self.m.trb_slot(i), (0, 0, 0, 0), "slot %d" % i)
        self.views_agree()
        r = self.rx()
        self.assertEqual((r["state"], r["flags"] & 2, r["rx_aborts"]), (0, 2, 1))
        r, _ = self.put(0, d)
        self.assertEqual((r["committed"], r["rx_errors"]), (4 * KIB, 0))
        self.clean()

    def test_a_start_that_fails_after_the_controller_ended_the_transfer_disables_the_path_until_the_host_configures_again(self):
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.end_hw_transfer(2)
        self.m.inject_ep_event(2, 1)
        self.m.fail_next_cmd(6)
        self.assertEqual(self.abort(), M.H_OK)
        self.assertEqual(self.rx()["flags"] & 2, 0)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        self.assertEqual(self.rx()["flags"] & 2, 2)
        r, _ = self.put(0, blob(4 * KIB, seed=145))
        self.assertEqual(r["committed"], 4 * KIB)
        self.views_agree()
        self.clean()

    def test_a_restart_that_fails_when_the_end_completes_disables_the_path_until_the_host_configures_again(self):
        self.m.hold_endxfer()
        self.m.bulk_fault(2)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(blob(4 * KIB, seed=146))
        self.assertTrue(self.m.held)
        self.m.fail_next_cmd(6)
        self.m.release_held()
        self.assertEqual(self.rx()["flags"] & 2, 0)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_STALL)
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        r, _ = self.put(0, blob(4 * KIB, seed=147))
        self.assertEqual((r["committed"], r["flags"] & 2), (4 * KIB, 2))
        self.views_agree()
        self.clean()

    def test_a_reset_while_an_end_is_pending_does_not_end_the_transfer_twice_and_nothing_restarts_afterwards(self):
        self.m.hold_endxfer()
        self.m.bulk_fault(2)
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.m.bulk_out(blob(4 * KIB, seed=148))
        self.assertTrue(self.m.held)
        n0 = len(self.m.cmd_trace())
        self.m.bus_reset()
        self.assertEqual(self.rx_cmds(self.m.cmd_trace()[n0:], 8), [])		# vendor: no second ENDTRANSFER while one is pending
        self.clean()
        self.m.release_held()
        self.assertEqual(self.m.hw_ep_started(2), 0)				# disabled: the completion must not start a transfer again
        self.views_agree()
        self.assertEqual(self.rx()["flags"] & 2, 0)
        self.assertEqual(self.rx_cmds(self.m.cmd_trace()[n0:], 6), [])
        self.up()
        r, _ = self.put(0, blob(4 * KIB, seed=149))
        self.assertEqual(r["committed"], 4 * KIB)
        self.clean()

    def test_events_of_a_disabled_endpoint_are_ignored(self):
        self.assertEqual(self.m.ctrl(0x00, 9, 0, 0, 0)[0], M.H_OK)
        before, spurious = self.rx(), self.m.rx_spurious
        self.m.inject_ep_event(2, 2, status=4)
        self.assertEqual(self.m.rx_spurious, spurious)
        self.assertEqual(self.rx(), before)

    def test_a_transfer_the_controller_ended_by_itself_while_nothing_was_armed_is_replaced_by_a_fresh_one(self):
        self.put(0, blob(4 * KIB, seed=150))
        self.m.end_hw_transfer(2)
        spurious = self.m.rx_spurious
        n0 = len(self.m.cmd_trace())
        self.m.inject_ep_event(2, 1)						# XferComplete with nothing armed
        tr = self.m.cmd_trace()[n0:]
        self.assertEqual(self.m.rx_spurious, spurious + 1)
        self.assertEqual((self.rx_cmds(tr, 8), len(self.rx_cmds(tr, 6))), ([], 1))	# no ENDTRANSFER, one STARTTRANSFER
        self.assertEqual(self.m.hw_ep_started(2), 1)
        self.views_agree()
        r, _ = self.put(4 * KIB, blob(4 * KIB, seed=151))			# the next chunk works without configuring again
        self.assertEqual((r["committed"], r["rx_errors"], r["flags"] & 2), (8 * KIB, 0, 2))
        self.views_agree()
        self.clean()

    def test_that_fresh_start_failing_disables_the_path_until_the_host_configures_again(self):
        self.put(0, blob(4 * KIB, seed=154))
        self.m.end_hw_transfer(2)
        self.m.fail_next_cmd(6)
        self.m.inject_ep_event(2, 1)
        self.assertEqual(self.rx()["flags"] & 2, 0)
        self.assertEqual(self.begin(4 * KIB, 4 * KIB), M.H_STALL)
        self.assertEqual(self.m.ctrl(0x00, 9, 1, 0, 0)[0], M.H_OK)
        r, _ = self.put(4 * KIB, blob(4 * KIB, seed=155))
        self.assertEqual(r["committed"], 8 * KIB)
        self.clean()

    def test_a_stray_progress_event_while_a_transfer_is_started_and_nothing_is_armed_changes_nothing(self):
        before, spurious, n0 = self.rx(), self.m.rx_spurious, len(self.m.cmd_trace())
        self.m.inject_ep_event(2, 2)						# XferInProgress, nothing armed
        self.assertEqual(self.m.rx_spurious, spurious + 1)
        self.assertEqual(len(self.m.cmd_trace()), n0)
        self.assertEqual(self.rx(), before)
        self.assertEqual((self.m.engine_ep_started(2), self.m.hw_ep_started(2)), (1, 1))
        r, _ = self.put(0, blob(4 * KIB, seed=156))
        self.assertEqual((r["committed"], r["rx_errors"], r["rx_aborts"]), (4 * KIB, 0, 0))
        self.clean()

    def test_a_stray_completion_while_an_end_is_pending_starts_nothing(self):
        self.m.hold_endxfer()
        self.assertEqual(self.begin(0, 4 * KIB), M.H_OK)
        self.assertEqual(self.abort(), M.H_OK)				# the ENDTRANSFER is issued and its completion is held
        self.assertTrue(self.m.held)
        n0 = len(self.m.cmd_trace())
        self.m.inject_ep_event(2, 1)						# XferComplete while the end is pending
        self.assertEqual(self.m.cmd_trace()[n0:], [])
        self.clean()
        self.m.release_held()
        self.views_agree()
        self.assertEqual(self.m.hw_ep_started(2), 1)				# the restart that the abort asked for happened once
        r, _ = self.put(0, blob(4 * KIB, seed=157))
        self.assertEqual((r["committed"], r["rx_errors"]), (4 * KIB, 0))
        self.clean()

    def test_engine_and_controller_agree_about_an_active_transfer_throughout(self):
        d = blob(4 * KIB, seed=152)
        self.views_agree()
        self.put(0, d)
        self.views_agree()
        self.assertEqual(self.begin(4 * KIB, 4 * KIB), M.H_OK)
        self.abort()
        self.views_agree()
        self.m.bulk_fault(2)
        self.put(4 * KIB, d, expect_rc=M.H_NAKLOOP)
        self.views_agree()
        self.m.ctrl(0x00, 9, 0, 0, 0)
        self.views_agree()
        self.m.ctrl(0x00, 9, 1, 0, 0)
        self.views_agree()
        self.assertEqual(self.begin(4 * KIB, 4 * KIB), M.H_OK)
        self.m.bus_reset()
        self.views_agree()
        self.up()
        self.views_agree()
        self.clean()


class DirectProtocolTests(ProtocolTests):
    DIRECT = True

    def test_a_dirty_cache_line_in_the_destination_is_cleaned_before_the_dma_writes(self):
        d = blob(8 * KIB, seed=30)
        self.m.dest_cpu_dirty(0, 8 * KIB)
        r, _ = self.put(0, d)
        self.assertEqual(self.m.dest(0, 8 * KIB), d)
        self.assertEqual(r["last_sum"], ref_sum(d))
        self.clean()

    def test_bytes_the_dma_loses_show_up_in_the_checksum(self):
        d = blob(16 * KIB, seed=31)
        self.m.set_dma_limit(8 * KIB)
        r, _ = self.put(0, d)
        self.assertEqual(r["committed"], 16 * KIB)			# the engine cannot know ...
        self.assertNotEqual(r["last_sum"], ref_sum(d))			# ... but the checksum of what is really there differs
        self.assertEqual(r["last_sum"], ref_sum(self.m.dest(0, 16 * KIB)))
        self.assertTrue(self.sentinel(8 * KIB, 8 * KIB))
        self.assertTrue(self.m.dma_blocked() > 0)


class StagedProtocolTests(ProtocolTests):
    def test_dirty_cache_lines_in_the_staging_block_are_cleaned_before_the_dma_writes(self):
        d = blob(16 * KIB, seed=153)
        self.m.stage_cpu_dirty(16 * KIB)
        r, _ = self.put(0, d)
        self.assertEqual(self.m.dest(0, 16 * KIB), d)
        self.assertEqual(r["last_sum"], ref_sum(d))
        self.clean()

    def test_nothing_reaches_the_destination_before_the_chunk_completes(self):
        d = blob(8 * KIB, seed=32)
        self.assertEqual(self.begin(0, 8 * KIB), M.H_OK)
        self.m.bulk_out(d[:4 * KIB])
        self.assertTrue(self.sentinel(0, 8 * KIB))
        self.assertEqual(self.rx()["committed"], 0)
        self.m.bulk_out(d[4 * KIB:])
        self.assertEqual(self.m.dest(0, 8 * KIB), d)

    def test_a_failed_chunk_leaves_the_destination_untouched(self):
        d = blob(8 * KIB, seed=33)
        self.m.bulk_fault(1, after=6 * KIB)
        self.assertEqual(self.begin(0, 8 * KIB), M.H_OK)
        self.m.bulk_out(d)
        self.assertTrue(self.sentinel(0, 8 * KIB))

    def test_a_dirty_destination_line_does_not_matter_in_staged_mode(self):
        d = blob(4 * KIB, seed=34)
        self.m.dest_cpu_dirty(0, 4 * KIB)
        self.put(0, d)
        self.assertEqual(self.m.dest(0, 4 * KIB), d)
        self.clean()


class CompatibilityTests(unittest.TestCase):
    """Without a receive destination the engine is the NAT-041 engine."""

    def setUp(self):
        self.m = M.Machine(lib(), rx_size=0)
        self.assertEqual(self.m.init_rc, 0)
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)

    def tearDown(self):
        self.m.close()

    def test_the_configuration_has_no_endpoint(self):
        rc, d = self.m.ctrl(0x80, 6, 0x0200, 0, 64)
        self.assertEqual((rc, len(d), struct.unpack_from("<H", d, 2)[0], d[13]), (M.H_OK, 18, 18, 0))

    def test_the_receive_requests_stall(self):
        self.assertEqual(self.m.ctrl(0xC0, 7, 0, 0, 120)[0], M.H_STALL)
        self.assertEqual(self.m.ctrl(0x40, 6, 0, 0, 16, data=bytes(16))[0], M.H_STALL)
        self.assertEqual(self.m.ctrl(0x40, 8, 0, 0, 0)[0], M.H_STALL)
        self.assertEqual(self.m.ctrl(0x82, 0, 0, 0x01, 2)[0], M.H_STALL)
        self.assertEqual(self.m.bulk_out(bytes(512))[0], M.H_TIMEOUT)

    def test_the_log_still_works(self):
        self.m.text("hello")
        rc, info = self.m.ctrl(0xC0, 1, 0, 0, 112)
        self.assertEqual((rc, len(info), info[:4]), (M.H_OK, 112, b"S24L"))
        self.assertEqual(self.m.violations(), [])

    def test_a_destination_that_is_not_a_multiple_of_512_is_refused(self):
        self.m.close()
        for size in (100, 1000, 512 * 3 + 1):
            m = M.Machine(lib(), rx_size=size)
            self.assertEqual(m.init_rc, -5, size)			# USBMON_E_CFG
            m.close()
        self.m = M.Machine(lib(), rx_size=0)


def undefined_symbols_of(path):
    data = slurp(path, "rb")
    e_shoff, = struct.unpack_from("<Q", data, 0x28)
    e_shentsize, e_shnum = struct.unpack_from("<HH", data, 0x3A)
    secs = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from("<IIQQQQIIQQ", data, o)
        secs.append((typ, off, size, link, entsize))
    out = []
    for typ, off, size, link, entsize in secs:
        if typ != 2:
            continue
        stroff = secs[link][1]
        for k in range(size // entsize):
            nm, info, other, shndx, value, sz = struct.unpack_from("<IBBHQQ", data, off + k * entsize)
            end = data.index(b"\0", stroff + nm)
            out.append((data[stroff + nm:end].decode(), shndx))
    return out


class StaticTests(unittest.TestCase):
    def test_wire_constants_match_the_header_and_the_sender(self):
        h = slurp(ENGINE_H)

        def hconst(name):
            m = re.search(r"#define\s+%s\s+(0x[0-9a-fA-F]+|\d+)u?\b" % name, h)
            self.assertIsNotNone(m, name)
            return int(m.group(1), 0)

        import importlib.util
        sp = importlib.util.spec_from_file_location("root_send_consts", SENDER)
        rs = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(rs)

        def sconst(name):
            return getattr(rs, name)
        for hname, sname in (("USBMON_REQ_RX_BEGIN", "REQ_RX_BEGIN"), ("USBMON_REQ_GET_RX", "REQ_GET_RX"),
                             ("USBMON_REQ_RX_ABORT", "REQ_RX_ABORT"), ("USBMON_VID", "VID"), ("USBMON_PID", "PID")):
            self.assertEqual(hconst(hname), sconst(sname), hname)
        self.assertEqual(hconst("USBMON_RX_MPS"), sconst("MPS"))
        self.assertEqual(hconst("USBMON_RX_IDLE"), sconst("RX_IDLE"))
        # physical endpoint 2 is USB endpoint 0x01 OUT: number 1, direction OUT (gadget.c: physical = 2 * number + direction)
        self.assertEqual(rs.BULK_EP_OUT, 0x01)
        self.assertEqual(hconst("USBMON_RX_EP"), 2)
        self.assertEqual((rs.VENDOR_OUT, rs.VENDOR_IN), (0x40, 0xC0))

    def test_sender_struct_layout_equals_the_header_layout(self):
        spec = {}
        import importlib.util
        sp = importlib.util.spec_from_file_location("root_send_layout", SENDER)
        rs = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(rs)
        self.assertEqual(LAYOUT_SIZE, 120)
        self.assertEqual(rs.RX_SIZE, LAYOUT_SIZE)
        # sender field order and offsets, derived from its format string, against the header
        offs, pos = {}, 0
        for name, ch in zip(rs.RX_FIELDS, re.findall(r"\d*[sHIQ]", rs.RX_FORMAT[1:])):
            size = {"H": 2, "I": 4, "Q": 8}.get(ch[-1]) or int(ch[:-1])
            pos = (pos + size - 1) // size * size if ch[-1] != "s" else pos
            offs[name] = pos
            pos += size
        for name, (off, sz, count) in LAYOUT.items():
            self.assertEqual(offs[name], off, name)
        self.assertEqual(set(offs), set(LAYOUT))

    def test_dwc3_constants_match_the_pinned_vendor_headers(self):
        text = vendor_file("drivers/usb/dwc3/core.h") + "\n" + vendor_file("drivers/usb/dwc3/gadget.h")
        theirs, ours = cdefs.parse_defs(text), cdefs.parse_defs(slurp(REGS_H))
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
                va = cdefs.c_eval(cdefs.call_text(name, args, params), ours)
                vb = cdefs.c_eval(cdefs.call_text(name, args, theirs[name][0]), theirs)
                if va != vb:
                    mismatches.append("%s%s: ours %#x vendor %#x" % (name, args, va, vb))
        self.assertEqual(mismatches, [])
        self.maxDiff = None
        self.assertEqual(sorted(own), sorted(["DWC3_EVT_DEV_RAWTYPE", "DWC3_EVT_DEV_TYPE", "DWC3_EVT_EP_EVENT",
                                              "DWC3_EVT_EP_NUM", "DWC3_EVT_EP_PARAMS", "DWC3_EVT_EP_STATUS",
                                              "DWC3_EVT_IS_DEVSPEC"]))
        self.assertGreater(checked, 95)

    def test_the_bulk_constants_added_for_nat076_are_among_the_checked_ones(self):
        text = vendor_file("drivers/usb/dwc3/core.h") + "\n" + vendor_file("drivers/usb/dwc3/gadget.h")
        theirs = cdefs.parse_defs(text)
        expect = {"DWC3_DEPCMD_UPDATETRANSFER": 7, "DWC3_DEPCMD_TYPE_BULK": 2, "DWC3_DEPCFG_XFER_IN_PROGRESS_EN": 1 << 9,
                  "DWC3_TRB_CTRL_CSP": 1 << 3, "DWC3_TRB_CTRL_IOC": 1 << 11, "DWC3_TRB_CTRL_HWO": 1,
                  "DEPEVT_STATUS_BUSERR": 1, "DEPEVT_STATUS_SHORT": 2, "DEPEVT_STATUS_IOC": 4}
        for name, value in expect.items():
            self.assertIn(name, theirs, name)
            self.assertEqual(cdefs.c_eval(name, theirs), value, name)
        self.assertEqual(cdefs.c_eval("DWC3_TRB_CTRL_TRBCTL(1)", theirs), 1 << 4)		# NORMAL
        self.assertEqual(cdefs.c_eval("DWC3_TRB_CTRL_TRBCTL(8)", theirs), 8 << 4)		# LINK_TRB
        ours = cdefs.parse_defs(slurp(REGS_H))
        for name in expect:
            self.assertEqual(cdefs.c_eval(name, ours), expect[name], name)

    def test_the_vendor_cross_check_notices_a_wrong_value(self):
        text = "#define DWC3_TRB_CTRL_CSP\tBIT(3)\n#define X(n) ((n) << 4)\n"
        good = cdefs.parse_defs(text)
        bad = cdefs.parse_defs(text.replace("BIT(3)", "BIT(4)").replace("<< 4", "<< 5"))
        self.assertNotEqual(cdefs.c_eval("DWC3_TRB_CTRL_CSP", good), cdefs.c_eval("DWC3_TRB_CTRL_CSP", bad))
        self.assertNotEqual(cdefs.c_eval("X(8)", good), cdefs.c_eval("X(8)", bad))

    def test_the_engine_is_freestanding_aarch64_code(self):
        out = os.path.join(_TMP, "usbmon.o")
        flags = ["-target", "aarch64-freestanding", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-O2", "-Wall",
                 "-Wextra", "-Werror", "-c", "-I", os.path.join(HERE, "engine")]
        r = subprocess.run(["zig", "cc"] + flags + [ENGINE_C, "-o", out], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        syms = sorted(n for n, shndx in undefined_symbols_of(out) if n and shndx == 0)
        self.assertEqual(syms, [], "the engine must not need libc or the compiler runtime: %s" % syms)

    def test_destination_memory_is_only_touched_through_the_port(self):
        src = slurp(ENGINE_C)
        for lineno, line in enumerate(src.splitlines(), 1):
            if "rx_dest" in line and not re.search(r"usbmon_dest_|mcopy\(m->rx_dest|m->rx_dest\s*=|cfg->rx_dest|rx_dest\s*=|\(m->rx_dest|!m->rx_dest|m->rx_dest\s*\)", line):
                self.fail("line %d uses the destination directly: %s" % (lineno, line.strip()))

    def test_dma_block_members_are_only_touched_through_the_port(self):
        src = slurp(ENGINE_C)
        for lineno, line in enumerate(src.splitlines(), 1):
            for m in re.finditer(r"m->dma\.\w+", line):
                before = line[:m.start()]
                ok = before.rstrip().endswith("&") or re.search(r"usbmon_dma_\w+\([^;]*$", before) or "usbmon_dma_" in line
                self.assertTrue(ok, "line %d reads or writes DMA memory directly: %s" % (lineno, line.strip()))


class Probe:
    """Drives one machine through a scenario and collects what went wrong instead of raising: the same scenario is run on the
    real engine (it must find nothing) and on an engine with one defect (it must find something)."""

    def __init__(self, m, direct):
        self.m, self.direct, self.problems = m, direct, []

    def check(self, ok, msg):
        if not ok:
            self.problems.append(msg)

    def up(self):
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.check(rc == M.H_OK, "enumeration step %s: rc %s" % (name, rc))

    def rx(self):
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        if rc != M.H_OK or len(raw) != 120:
            self.problems.append("GET_RX failed (rc %s)" % rc)
            return {k: 0 for k in LAYOUT}
        return rxf(raw)

    def begin(self, off, n, flags=0):
        return self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", off, n, flags))[0]

    def chunk(self, off, data):
        self.check(self.begin(off, len(data)) == M.H_OK, "RX_BEGIN %d+%d refused" % (off, len(data)))
        rc, took = self.m.bulk_out(data)
        self.check((rc, took) == (M.H_OK, len(data)), "bulk OUT at %d: rc %s, took %d of %d" % (off, rc, took, len(data)))
        r = self.rx()
        self.check((r["state"], r["committed"]) == (0, off + len(data)), "after the chunk at %d: state %d committed %d" % (off, r["state"], r["committed"]))
        self.check(r["last_sum"] == ref_sum(data), "checksum of the chunk at %d" % off)
        self.check(self.m.dest(off, len(data)) == data, "destination bytes of the chunk at %d" % off)
        end = off + len(data)
        room = min(8192, 256 * KIB - end)
        if room > 0:
            self.check(self.m.dest(end, room) == b"\xEE" * room, "bytes were written beyond the end of the chunk at %d" % off)
        return r

    def refused(self, label, rc):
        self.check(rc == M.H_STALL, "%s was not refused (rc %s)" % (label, rc))

    def finish(self):
        v = self.m.violations()
        self.check(not v, "model violations: %s" % v[:2])
        return self.problems


def sc_basic(p):
    p.up()
    d = blob(3 * 4096, 1)
    for k in range(3):
        p.chunk(k * 4096, d[k * 4096:(k + 1) * 4096])
    return p.finish()


def sc_ring(p):
    p.up()
    d = blob(14 * 4096, 2)
    for k in range(14):			# 3 data slots: four laps of the ring
        p.chunk(k * 4096, d[k * 4096:(k + 1) * 4096])
    return p.finish()


def sc_sizes(p):
    p.up()
    pos = 0
    for k, n in enumerate((512, 1024, 4096, 6144, 16384, 60 * 1024)):
        p.chunk(pos, blob(n, 10 + k))
        pos += n
    return p.finish()


def sc_dirty_destination(p):
    p.up()
    p.m.dest_cpu_dirty(0, 8192)
    p.chunk(0, blob(8192, 3))
    return p.finish()


def sc_refusals(p):
    p.up()
    p.chunk(0, blob(4096, 4))
    p.refused("a repeated offset", p.begin(0, 4096))
    p.refused("an offset inside the committed range", p.begin(2048, 4096))
    p.refused("a gap", p.begin(8192, 4096))
    p.refused("length zero", p.begin(4096, 0))
    p.refused("a length that is not a multiple of 512", p.begin(4096, 1000))
    p.refused("flags", p.begin(4096, 4096, flags=1))
    r = p.rx()
    p.check((r["state"], r["committed"]) == (0, 4096), "a refusal changed the state: %s" % ((r["state"], r["committed"]),))
    # armed: a second RX_BEGIN is refused and the first transfer still completes
    p.check(p.begin(4096, 4096) == M.H_OK, "RX_BEGIN refused")
    p.refused("RX_BEGIN while armed", p.begin(4096, 4096))
    rc, took = p.m.bulk_out(blob(4096, 5))
    p.check((rc, took) == (M.H_OK, 4096), "the armed transfer did not complete")
    p.check(p.rx()["committed"] == 8192, "the armed transfer was not committed")
    return p.finish()


def sc_chunk_limit(p):
    p.up()
    p.refused("a chunk over the limit", p.begin(0, 65536 + 512))
    return p.finish()


def sc_capacity(p):
    p.up()
    pos = 0
    while pos + 65536 < 256 * KIB - 4096:
        p.chunk(pos, blob(65536, pos // 65536))
        pos += 65536
    p.chunk(pos, blob(60 * KIB, 77))			# ends 4 KiB short of the capacity
    pos += 60 * KIB
    p.refused("a chunk that ends past the capacity", p.begin(pos, 8192))
    p.chunk(pos, blob(4096, 78))				# exactly to the end
    p.refused("a chunk at the capacity", p.begin(pos + 4096, 4096))
    return p.finish()


def failed_then_retried(p, setup, label):
    p.up()
    d = blob(4096, 6)
    setup(p.m)
    p.begin(0, 4096)
    p.m.bulk_out(d)
    r = p.rx()
    p.check(r["state"] == 2, "%s: the chunk was not marked failed (state %d)" % (label, r["state"]))
    p.check(r["committed"] == 0, "%s: the committed offset moved over a failed chunk" % label)
    p.check(r["rx_errors"] == 1, "%s: error not counted" % label)
    p.chunk(0, d)
    return p.finish()


def sc_short_packet(p):
    p.up()
    d = blob(4096, 7)
    p.begin(0, 4096)
    p.m.bulk_out(d[:4096 - 100])
    r = p.rx()
    p.check((r["state"], r["committed"], r["rx_errors"]) == (2, 0, 1), "short packet: %s" % ((r["state"], r["committed"], r["rx_errors"]),))
    p.chunk(0, d)
    return p.finish()


def sc_bus_error(p):
    return failed_then_retried(p, lambda m: m.bulk_fault(1, 1500), "bus error")


def sc_trb_error(p):
    return failed_then_retried(p, lambda m: m.bulk_fault(2, 0), "TRB error")


def sc_bus_error_full(p):
    return failed_then_retried(p, lambda m: m.bulk_fault(4, 0), "bus error status with every byte received")


def sc_trb_error_full(p):
    return failed_then_retried(p, lambda m: m.bulk_fault(5, 0), "TRB error status with every byte received")


def sc_short_status_full(p):
    return failed_then_retried(p, lambda m: m.bulk_fault(6, 0), "SHORT status with every byte received")


def sc_residual_only(p):
    return failed_then_retried(p, lambda m: m.bulk_fault(3, 1500), "residual without a status bit")


def sc_bus_reset(p):
    p.up()
    d = blob(8192, 8)
    p.begin(0, 8192)
    p.m.bulk_out(d[:3000 // 512 * 512])
    p.m.bus_reset()
    r = p.rx()
    p.check((r["state"], r["rx_resets"], r["committed"]) == (2, 1, 0), "after a bus reset: %s" % ((r["state"], r["rx_resets"], r["committed"]),))
    p.check(r["flags"] & 2 == 0, "the endpoint stayed enabled across a bus reset")
    p.up()
    p.chunk(0, d)
    return p.finish()


def sc_abort(p):
    p.up()
    d = blob(4096, 9)
    p.begin(0, 4096)
    p.m.bulk_out(d[:1024])
    p.check(p.m.ctrl(0x40, 8, 0, 0, 0)[0] == M.H_OK, "RX_ABORT refused")
    r = p.rx()
    p.check((r["state"], r["rx_aborts"], r["committed"]) == (0, 1, 0), "after RX_ABORT: %s" % ((r["state"], r["rx_aborts"], r["committed"]),))
    p.chunk(0, d)
    return p.finish()


def sc_unconfigure(p):
    p.up()
    p.m.ctrl(0x00, 9, 0, 0, 0)
    p.check(p.rx()["flags"] & 2 == 0, "SET_CONFIGURATION(0) left the endpoint enabled")
    p.up()
    p.chunk(0, blob(4096, 11))
    return p.finish()


class SeededDefectTests(unittest.TestCase):
    """Each case breaks one place in the engine. The scenario is run on the real engine first (it must find nothing: the case
    is not vacuous) and then on the broken engine (it must find something: the suite would catch the defect)."""

    def run_scenario(self, scenario, direct, engine_lib):
        m = M.Machine(engine_lib, rx_size=256 * KIB, rx_direct=direct)
        try:
            self.assertEqual(m.init_rc, 0)
            return scenario(Probe(m, direct))
        finally:
            m.close()

    def build_mutant(self, old, new):
        src = slurp(ENGINE_C)
        self.assertEqual(src.count(old), 1, "mutation anchor must occur exactly once: %r" % old)
        path = os.path.join(_TMP, "mut-%d.c" % abs(hash(old + new)))
        with open(path, "w") as f:
            f.write(src.replace(old, new))
        return M.build(engine_src=path, out_dir=_TMP, extra=["-I", os.path.join(HERE, "engine")], strict=False)

    def seeded(self, old, new, scenario, direct=False):
        self.assertEqual(self.run_scenario(scenario, direct, lib()), [], "the scenario already fails on the real engine")
        found = self.run_scenario(scenario, direct, self.build_mutant(old, new))
        self.assertTrue(found, "the defect went unnoticed")
        return found

    CASES = {
        # controller programming (the vendor sequence)
        "missing_update_transfer": ("if (dep_cmd(m, USBMON_RX_EP, DWC3_DEPCMD_UPDATETRANSFER | DWC3_DEPCMD_PARAM(m->ep_rsc[USBMON_RX_EP]), 0, 0, 0)) {",
                                    "if (0) {", sc_basic, False),
        "missing_csp": ("DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP | DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_HWO",
                        "DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_HWO", sc_basic, False),
        "missing_ioc": ("DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP | DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_HWO",
                        "DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP | DWC3_TRB_CTRL_HWO", sc_basic, False),
        "wrong_trb_type": ("DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP", "DWC3_TRB_CTRL_TRBCTL(2) | DWC3_TRB_CTRL_CSP", sc_basic, False),
        "wrong_max_packet_size": ("DWC3_DEPCFG_MAX_PACKET_SIZE(USBMON_RX_MPS)", "DWC3_DEPCFG_MAX_PACKET_SIZE(1024)", sc_basic, False),
        "missing_xfer_in_progress_enable": ("p1 = DWC3_DEPCFG_XFER_IN_PROGRESS_EN | DWC3_DEPCFG_EP_NUMBER(USBMON_RX_EP);",
                                            "p1 = DWC3_DEPCFG_EP_NUMBER(USBMON_RX_EP);", sc_basic, False),
        "missing_startconfig_2": ("ret = dep_cmd(m, 0, DWC3_DEPCMD_DEPSTARTCFG | DWC3_DEPCMD_PARAM(2), 0, 0, 0);", "ret = 0;", sc_basic, False),
        "endpoint_never_enabled": ("WR(m, DWC3_DALEPENA, RD(m, DWC3_DALEPENA) | DWC3_DALEPENA_EP(USBMON_RX_EP));", "", sc_basic, False),
        "wrong_resource_index_on_endtransfer": ("DWC3_DEPCMD_ENDTRANSFER | DWC3_DEPCMD_CMDIOC | DWC3_DEPCMD_PARAM(m->ep_rsc[USBMON_RX_EP]),",
                                                "DWC3_DEPCMD_ENDTRANSFER | DWC3_DEPCMD_CMDIOC | DWC3_DEPCMD_PARAM(0),", sc_abort, False),
        "enqueue_wraps_onto_the_link_trb": ("m->rx_enq = (uint8_t)((m->rx_enq + 1) % (USBMON_RX_TRBS - 1));",
                                            "m->rx_enq = (uint8_t)((m->rx_enq + 1) % USBMON_RX_TRBS);", sc_ring, False),
        "dequeue_wraps_onto_the_link_trb": ("m->rx_deq = (uint8_t)((m->rx_deq + 1) % (USBMON_RX_TRBS - 1));",
                                            "m->rx_deq = (uint8_t)((m->rx_deq + 1) % USBMON_RX_TRBS);", sc_ring, False),
        # cache discipline
        "missing_stage_invalidate_before_the_copy": ("\tusbmon_dma_sync(m->dma.rxstage, len);\t/* invalidate: the controller wrote these lines behind the CPU */\n",
                                                     "", sc_basic, False),
        "missing_destination_clean_before_the_dma": ("\t\tusbmon_dest_sync(m->rx_dest + off, len);\n", "", sc_dirty_destination, True),
        "missing_destination_invalidate_before_the_checksum": ("\t\tusbmon_dest_sync(m->rx_dest + m->rx_armed_off, m->rx_armed_len);\t/* invalidate before reading */\n",
                                                               "", sc_basic, True),
        "missing_trb_clean_after_filling_it": ("\tusbmon_dma_st32(&t->ctrl, DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP | DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_HWO);\n\tusbmon_dma_sync(m->dma.rxtrb, sizeof(m->dma.rxtrb));",
                                               "\tusbmon_dma_st32(&t->ctrl, DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP | DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_HWO);", sc_basic, False),
        # RX_BEGIN rules
        "duplicate_offset_accepted": ("\tif (off < m->rx_committed) {", "\tif (0) {", sc_refusals, False),
        "gap_accepted": ("\tif (off > m->rx_committed) {", "\tif (0) {", sc_refusals, False),
        "length_not_a_packet_multiple_accepted": ("(len % USBMON_RX_MPS) || ", "", sc_refusals, False),
        "zero_length_accepted": ("if (!len || (len % USBMON_RX_MPS)", "if ((len % USBMON_RX_MPS)", sc_refusals, False),
        "begin_while_armed_accepted": ("if (!m->rx_enabled || m->rx_state == USBMON_RX_ARMED || ", "if (!m->rx_enabled || ", sc_refusals, False),
        "flags_ignored": ("m->rx_restart || flags) {", "m->rx_restart) {", sc_refusals, False),
        "chunk_limit_ignored": ("len > rx_chunk_max(m)", "0", sc_chunk_limit, False),
        "capacity_ignored": (" || len > m->rx_size - off)", ")", sc_capacity, False),
        "capacity_ignored_direct": (" || len > m->rx_size - off)", ")", sc_capacity, True),
        # completion
        "residual_ignored": ("ok = (status == DWC3_TRBSTS_OK) && !residual && ", "ok = (status == DWC3_TRBSTS_OK) && ", sc_residual_only, False),
        "short_status_ignored": ("(DEPEVT_STATUS_BUSERR | DEPEVT_STATUS_SHORT));", "DEPEVT_STATUS_BUSERR);", sc_short_status_full, False),
        "bus_error_status_ignored": ("(DEPEVT_STATUS_BUSERR | DEPEVT_STATUS_SHORT));", "DEPEVT_STATUS_SHORT);", sc_bus_error_full, False),
        "trb_status_ignored": ("ok = (status == DWC3_TRBSTS_OK) && !residual", "ok = !residual", sc_trb_error_full, False),
        "committed_moves_on_failure": ("\tif (!ok) {\n\t\tm->rx_errors++;", "\tif (!ok) {\n\t\tm->rx_committed = m->rx_armed_off + m->rx_armed_len;\n\t\tm->rx_errors++;", sc_trb_error, False),
        "staged_copy_to_the_wrong_offset": ("mcopy(m->rx_dest + off + done, piece, n);", "mcopy(m->rx_dest + done, piece, n);", sc_basic, False),
        "staged_copy_loses_the_tail": ("n = len - done < sizeof(piece) ? len - done : (uint32_t)sizeof(piece);", "n = 4096 < len - done ? 4096 : 4096;", sc_sizes, False),
        "checksum_position_forgotten_staged": ("sum = usbmon_rx_sum_step(sum, w, (done + k) / 8);", "sum = usbmon_rx_sum_step(sum, w, k / 8);", sc_sizes, False),
        "checksum_position_forgotten_direct": ("sum = usbmon_rx_sum_step(sum, usbmon_dest_ld64(p + i), i / 8);",
                                               "sum = usbmon_rx_sum_step(sum, usbmon_dest_ld64(p + i), 0);", sc_basic, True),
        # reset, abort, configuration
        "reset_does_not_fail_the_transfer": ("\tif (m->rx_state == USBMON_RX_ARMED) {\n\t\tm->rx_state = USBMON_RX_FAILED;\n\t\tm->rx_errors++;\n\t\tif (lost)\n\t\t\tm->rx_resets++;\n\t}\n\trx_end(m);",
                                             "\trx_end(m);", sc_bus_reset, False),
        "abort_does_not_end_the_transfer": ("\tm->rx_aborts++;\n\trx_restart(m);", "\tm->rx_aborts++;", sc_abort, False),
        "set_configuration_zero_keeps_the_endpoint": ("\t\t\trx_disable(m, 0);", "\t\t\t(void)0;", sc_unconfigure, False),
    }


def _add_cases():
    def make(old, new, scenario, direct):
        def test(self):
            self.seeded(old, new, scenario, direct)
        return test
    for name, (old, new, scenario, direct) in SeededDefectTests.CASES.items():
        setattr(SeededDefectTests, "test_" + name, make(old, new, scenario, direct))


_add_cases()


class ScenarioHealthTests(unittest.TestCase):
    """The scenarios themselves: each one is clean on the real engine (staged and direct), so a mutant that is caught is caught
    by the defect, not by a broken scenario."""

    def test_every_scenario_is_clean_on_the_real_engine(self):
        scenarios = [sc_basic, sc_ring, sc_sizes, sc_dirty_destination, sc_refusals, sc_capacity, sc_short_packet, sc_bus_error,
                     sc_trb_error, sc_residual_only, sc_bus_error_full, sc_trb_error_full, sc_short_status_full, sc_bus_reset,
                     sc_abort, sc_unconfigure]
        for direct in (False, True):
            for sc in scenarios:
                with self.subTest(scenario=sc.__name__, direct=direct):
                    m = M.Machine(lib(), rx_size=256 * KIB, rx_direct=direct)
                    try:
                        self.assertEqual(sc(Probe(m, direct)), [])
                    finally:
                        m.close()

    def test_a_scenario_notices_a_broken_machine(self):
        m = M.Machine(lib(), rx_size=256 * KIB)
        try:
            p = Probe(m, False)
            p.up()
            p.chunk(0, blob(4096, 1))
            m.dest_poke(0, b"\x00" * 16)			# the destination is corrupted behind the engine's back
            p.check(m.dest(0, 4096) == blob(4096, 1), "destination bytes")
            self.assertTrue(p.problems)
        finally:
            m.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
