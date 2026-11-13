"""Host tests of root_send130.send() against the NAT-130 engine in the model (host-test only: no phone)."""
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regress76  # noqa: E402
import root_send130 as S  # noqa: E402

rx, M = regress76.load_suite_module()
KIB = 1024
blob = rx.blob


class ModelTransport130(S.Transport):
    def __init__(self, m):
        self.m = m
        self.begins = []
        self.rxt_filter = None		# f(dict) -> dict
        self.sum_hook = None		# f(off, n, mode) -> raise to fail
        self.bulk_hook = None		# f(index) -> called before each bulk write
        self.no_rxt = False
        self.writes = 0
        self.reconnects = 0

    def rx_begin(self, offset, length, flags=0):
        self.begins.append((offset, length, flags))
        rc, _ = self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", offset, length, flags))
        if rc != M.H_OK:
            raise S.TransportError("RX_BEGIN: %s" % M.RC_NAMES.get(rc, rc))

    def rx_abort(self):
        rc, _ = self.m.ctrl(0x40, 8, 0, 0, 0)
        if rc != M.H_OK:
            raise S.TransportError("RX_ABORT: %s" % M.RC_NAMES.get(rc, rc))

    def get_rx(self):
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        if rc != M.H_OK:
            raise S.TransportError("GET_RX: %s" % M.RC_NAMES.get(rc, rc))
        return raw

    def get_rxt(self):
        if self.no_rxt:
            raise S.TransportError("GET_RXT: stall")
        rc, raw = self.m.ctrl(0xC0, 9, 0, 0, S.RXT_SIZE)
        if rc != M.H_OK:
            raise S.TransportError("GET_RXT: %s" % M.RC_NAMES.get(rc, rc))
        if self.rxt_filter:
            r = S.parse_rxt(raw)
            r = self.rxt_filter(r)
            raw = struct.pack(S.RXT_FORMAT, *[r[k] for k in S.RXT_FIELDS])
        return raw

    def sum_req(self, offset, length, mode):
        if self.sum_hook:
            self.sum_hook(offset, length, mode)
        rc, _ = self.m.ctrl(0x40, 0x0A, 0, 0, 16, data=struct.pack("<QII", offset, length, mode))
        if rc != M.H_OK:
            raise S.TransportError("SUM: %s" % M.RC_NAMES.get(rc, rc))

    def bulk_write(self, data):
        if self.bulk_hook:
            self.bulk_hook(self.writes)
        self.writes += 1
        rc, took = self.m.bulk_out(bytes(data))
        if rc != M.H_OK:
            raise S.TransportError("bulk OUT: %s after %d bytes" % (M.RC_NAMES.get(rc, rc), took))
        return took

    def reconnect(self):
        self.reconnects += 1


class Base(unittest.TestCase):
    CAP = 1024 * KIB
    DIRECT = True

    def setUp(self):
        self.m = M.Machine(rx.lib(), rx_size=self.CAP, rx_direct=self.DIRECT)
        self.assertEqual(self.m.init_rc, 0)
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.t = ModelTransport130(self.m)
        self.log = []

    def tearDown(self):
        self.m.close()

    def send(self, data, **kw):
        kw.setdefault("chunk", 16 * KIB)
        kw.setdefault("write_size", 16 * KIB)
        kw.setdefault("sleep", lambda s: None)
        return S.send(self.t, data, log=self.log.append, **kw)


class AutoPolicyTests(Base):
    def test_auto_delivers_and_verifies(self):
        data = blob(40 * 16 * KIB, 1)
        r = self.send(data, none_chunks=4)
        self.assertEqual(r["committed"], len(data))
        self.assertEqual(self.m.dest(0, len(data)), data)
        modes = [b[2] for b in self.t.begins]
        best = {"plain": 0, "fast": 1, "cached": 2}[r["chosen_mode"]]
        self.assertEqual(modes, [S.PLAIN] + [S.NONE] * 4 + [best] * 35)
        self.assertEqual(set(r["calibration"]), {"plain", "fast", "cached"})
        self.assertTrue(all(c["ok"] for c in r["calibration"].values()))
        self.assertEqual([(v["off"], v["ok"]) for v in r["post_verify"]], [(k * 16 * KIB, True) for k in range(1, 5)])
        self.assertEqual(r["rxt_final"]["unsummed"], 4)
        self.assertEqual(len(r["records"]), 40)
        self.assertTrue(all("write_s" in x and "poll_s" in x and "dev" in x for x in r["records"]))
        s = S.summarize(r)
        self.assertEqual(s["chunks"], 40)
        self.assertEqual(s["by_mode"]["none"]["n"], 4)
        self.assertIn("tot_wire_s", s)
        self.assertEqual(self.m.violations(), [])

    def test_post_verify_runs_before_the_final_chunk(self):
        at = []
        self.t.sum_hook = lambda off, n, mode: at.append((len(self.t.begins), off))
        data = blob(10 * 16 * KIB, 11)
        self.send(data, none_chunks=4)
        calib = [a for a in at if a[1] == 0]
        verify = [a for a in at if a[1] != 0]
        self.assertEqual({a[0] for a in calib}, {1})			# after chunk 0, before chunk 1
        self.assertEqual(verify, [(5, k * 16 * KIB) for k in range(1, 5)])	# after chunk 4 (the last NONE), before chunk 5
        self.assertLess(max(a[0] for a in at), 10)

    def test_small_files_keep_a_summed_last_chunk(self):
        for nchunks, want in ((1, [0]), (2, [0, None]), (3, [0, 3, None]), (6, [0, 3, 3, 3, 3, None])):
            with self.subTest(nchunks=nchunks):
                self.tearDown()
                self.setUp()
                r = self.send(blob(nchunks * 16 * KIB, 12 + nchunks))
                modes = [b[2] for b in self.t.begins]
                best = {"plain": 0, "fast": 1, "cached": 2}[r["chosen_mode"]]
                self.assertEqual(modes, [best if w is None else w for w in want])
                self.assertNotEqual(modes[-1], S.NONE)

    def test_a_mode_that_sums_wrong_is_not_chosen(self):
        def lie(r):
            if r["sreq_mode"] == S.CACHED:
                r = dict(r, sreq_sum=(r["sreq_sum"] + 1) & ((1 << 64) - 1))
            return r
        self.t.rxt_filter = lie
        data = blob(12 * 16 * KIB, 2)
        r = self.send(data)
        self.assertFalse(r["calibration"]["cached"]["ok"])
        self.assertNotEqual(r["chosen_mode"], "cached")
        self.assertTrue(all(b[2] != S.CACHED for b in self.t.begins))
        self.assertEqual(self.m.dest(0, len(data)), data)

    def test_calibration_errors_fall_back_to_plain(self):
        def fail(off, n, mode):
            if mode != S.PLAIN:
                raise S.TransportError("SUM: timeout")
        self.t.sum_hook = fail
        data = blob(8 * 16 * KIB, 3)
        r = self.send(data)
        self.assertEqual(r["chosen_mode"], "plain")
        self.assertTrue(r["calibration"]["plain"]["ok"])
        self.assertEqual([v["mode"] for v in r["post_verify"]], [S.PLAIN] * 4)

    def test_a_none_chunk_with_wrong_bytes_is_fatal_at_the_post_verify(self):
        data = blob(10 * 16 * KIB, 4)
        hits = []

        def lose(i):
            # chunk 2 (a NONE chunk) is the 3rd bulk write: the controller drops its second half
            if i == 2:
                self.m.set_dma_limit(2 * 16 * KIB + 8 * KIB)
                hits.append(i)
            elif i == 3:
                self.m.set_dma_limit(1 << 40)
        self.t.bulk_hook = lose
        with self.assertRaises(S.DeliveryError) as e:
            self.send(data)
        self.assertIn("holds wrong data", str(e.exception))
        self.assertEqual(hits, [2])

    def test_a_none_chunk_is_retried_after_a_bus_fault(self):
        data = blob(8 * 16 * KIB, 5)
        done = []

        def fault(i):
            if i == 1 and not done:
                self.m.bulk_fault(1, after=4 * KIB)
                done.append(i)
        self.t.bulk_hook = fault
        r = self.send(data)
        self.assertEqual(r["committed"], len(data))
        self.assertEqual(r["retries"], 1)
        self.assertTrue(all(v["ok"] for v in r["post_verify"]))
        self.assertEqual(self.m.dest(0, len(data)), data)

    def test_device_without_get_rxt(self):
        self.t.no_rxt = True
        data = blob(4 * 16 * KIB, 6)
        with self.assertRaises(S.DeviceStateError):
            self.send(data)
        r = self.send(data, policy="plain", per_chunk_rxt=False)
        self.assertEqual(r["committed"], len(data))
        self.assertEqual({b[2] for b in self.t.begins}, {S.PLAIN})

    def test_fixed_policies(self):
        pos = 0
        for policy, mode in (("fast", S.FAST), ("cached", S.CACHED), ("plain", S.PLAIN)):
            self.t.begins = []
            data = blob(4 * 16 * KIB, 7 + mode)
            r = S.send(self.t, data, base=pos, chunk=16 * KIB, write_size=8 * KIB, policy=policy, sleep=lambda s: None)
            self.assertEqual(r["committed"], pos + len(data))
            self.assertEqual({b[2] for b in self.t.begins}, {mode})
            self.assertEqual(r["post_verify"], [])
            pos += len(data)


class StagedTests(Base):
    DIRECT = False
    CAP = 256 * KIB

    def test_staged_device_gets_plain_only(self):
        data = blob(8 * 16 * KIB, 9)
        r = self.send(data)
        self.assertEqual(r["caps"], 1)
        self.assertEqual({b[2] for b in self.t.begins}, {S.PLAIN})
        self.assertEqual(r["post_verify"], [])
        self.assertEqual(self.m.dest(0, len(data)), data)
        with self.assertRaises(S.DeviceStateError):
            S.send(self.t, data, base=len(data), chunk=16 * KIB, policy="cached", sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
