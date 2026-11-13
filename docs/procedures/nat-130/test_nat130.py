"""Host tests of the NAT-130 additions to the bulk-OUT receive engine (engine/usbmon.c): RX_BEGIN checksum modes, the SUM
request, GET_RXT phase timing. They run on the NAT-076 DWC3 / non-coherent cache / USB host model (model/model.c, copied with
the NAT-130 port functions added), through the NAT-076 test helpers (loaded by regress76.py with their paths pointed here).

Evidence kind: host-test. The model is not the Exynos 2400 controller, its DRAM or its caches; in particular the model's
CACHED mode is the plain loop, so these tests say nothing about the aarch64 page-table code (test_port130.py runs that under
Unicorn).
"""
import ctypes
import os
import re
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regress76  # noqa: E402

rx, M = regress76.load_suite_module()
KIB = 1024
blob, ref_sum, slurp = rx.blob, rx.ref_sum, rx.slurp
ENGINE_C = os.path.join(HERE, "engine", "usbmon.c")
ENGINE_H = os.path.join(HERE, "engine", "usbmon.h")
GET_RXT, SUM = 0x09, 0x0A
PLAIN, FAST, CACHED, NONE = 0, 1, 2, 3
SREQ_NONE, SREQ_OK, SREQ_REFUSED = 0, 1, 2


def rxt_layout():
    h = slurp(ENGINE_H)
    body = re.search(r"struct usbmon_rxt \{[^\n]*\n(.*?)\n\};", h, re.S).group(1)
    sizes = {"uint8_t": 1, "uint16_t": 2, "uint32_t": 4, "uint64_t": 8}
    off, fields = 0, {}
    for line in body.splitlines():
        m = re.match(r"\s*(uint\d+_t)\s+([\w, \[\]0-9]+);", line)
        if not m:
            continue
        sz = sizes[m.group(1)]
        for name in [x.strip() for x in m.group(2).split(",")]:
            mm = re.match(r"(\w+)(\[(\d+)\])?$", name)
            count = int(mm.group(3)) if mm.group(3) else 1
            off = (off + sz - 1) // sz * sz
            fields[mm.group(1)] = (off, sz, count)
            off += sz * count
    return fields, off


RXT, RXT_SIZE = rxt_layout()


def rxtf(raw):
    out = {}
    for name, (off, sz, count) in RXT.items():
        out[name] = bytes(raw[off:off + count]) if count > 1 else int.from_bytes(raw[off:off + sz], "little")
    return out


def raw_counters(m):
    lib = m.lib
    return (ctypes.c_uint64.in_dll(lib, "model_fast_calls").value, ctypes.c_uint64.in_dll(lib, "model_cached_calls").value)


def counters(m):
    """FAST and CACHED calls since this machine was created (the C counters are global to the library)."""
    a, b = raw_counters(m)
    a0, b0 = m.calls0
    return (a - a0, b - b0)


class V2(rx.Base):
    DIRECT = True
    CAP = 1024 * KIB

    def setUp(self):
        super().setUp()
        self.m.calls0 = raw_counters(self.m)

    def rxt(self):
        rc, raw = self.m.ctrl(0xC0, GET_RXT, 0, 0, RXT_SIZE)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(len(raw), RXT_SIZE)
        return rxtf(raw)

    def sumreq(self, off, n, mode, wlength=16):
        return self.m.ctrl(0x40, SUM, 0, 0, wlength, data=struct.pack("<QII", off, n, mode)[:wlength])[0]

    def putm(self, off, data, mode):
        self.assertEqual(self.begin(off, len(data), flags=mode), M.H_OK)
        rc, took = self.m.bulk_out(data)
        self.assertEqual((rc, took), (M.H_OK, len(data)))
        return self.rx()


class LayoutTests(unittest.TestCase):
    def test_rxt_layout_matches_the_static_asserts(self):
        h = slurp(ENGINE_H)
        self.assertEqual(RXT_SIZE, int(re.search(r"sizeof\(struct usbmon_rxt\) == (\d+)", h).group(1)))
        self.assertEqual(RXT["t_arm0"][0], 32)
        self.assertEqual(RXT["sreq_off"][0], 104)

    def test_v1_rx_struct_is_unchanged(self):
        old = slurp(os.path.join(HERE, "..", "nat-076", "engine", "usbmon.h"))
        new = slurp(ENGINE_H)
        pat = r"struct usbmon_rx \{.*?\n\};"
        self.assertEqual(re.search(pat, old, re.S).group(0), re.search(pat, new, re.S).group(0))

    def test_sender_constants_match(self):
        sys.path.insert(0, HERE)
        import root_send130 as s
        self.assertEqual((s.REQ_GET_RXT, s.REQ_SUM), (GET_RXT, SUM))
        self.assertEqual(s.RXT_SIZE, RXT_SIZE)
        self.assertEqual(list(s.RXT_FIELDS), list(RXT))


class ModeTests(V2):
    def test_flags_zero_is_the_nat076_commit(self):
        d = blob(8 * KIB, 1)
        r = self.putm(0, d, PLAIN)
        self.assertEqual((r["committed"], r["last_sum"]), (len(d), ref_sum(d)))
        self.assertEqual(counters(self.m), (0, 0))
        self.assertEqual(self.rxt()["last_mode"], PLAIN)
        self.clean()

    def test_fast_and_cached_commits_give_the_same_sum(self):
        pos = 0
        for mode, want in ((FAST, (1, 0)), (CACHED, (1, 1))):
            d = blob(16 * KIB, 10 + mode)
            r = self.putm(pos, d, mode)
            self.assertEqual((r["committed"], r["last_sum"]), (pos + len(d), ref_sum(d)))
            self.assertEqual(counters(self.m), want)
            self.assertEqual(self.rxt()["last_mode"], mode)
            self.assertEqual(self.m.dest(pos, len(d)), d)
            pos += len(d)
        self.clean()

    def test_fast_and_cached_still_invalidate_before_reading(self):
        # a stale line the CPU holds must not reach the sum in any mode: the model returns the cached (stale) bytes otherwise
        pos = 0
        for mode in (FAST, CACHED):
            d = blob(8 * KIB, 20 + mode)
            self.m.dest_cpu_dirty(pos, 8 * KIB)
            r = self.putm(pos, d, mode)
            self.assertEqual(r["last_sum"], ref_sum(d))
            pos += len(d)
        self.clean()

    def test_none_commits_without_a_sum_and_counts_it(self):
        d = blob(32 * KIB, 30)
        r = self.putm(0, d, NONE)
        self.assertEqual((r["committed"], r["last_sum"], r["rx_trbs"]), (len(d), 0, 1))
        t = self.rxt()
        self.assertEqual((t["unsummed"], t["last_mode"]), (1, NONE))
        self.assertEqual(counters(self.m), (0, 0))
        self.assertEqual(self.m.dest(0, len(d)), d)
        self.clean()

    def test_modes_mix_across_the_ring(self):
        pos, data = 0, blob(24 * 4 * KIB, 31)
        for k in range(24):
            mode = k % 4
            r = self.putm(pos, data[pos:pos + 4 * KIB], mode)
            pos += 4 * KIB
            self.assertEqual(r["committed"], pos)
            self.assertEqual(r["last_sum"], 0 if mode == NONE else ref_sum(data[pos - 4 * KIB:pos]))
        self.assertEqual(self.rxt()["unsummed"], 6)
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.clean()

    def test_other_flag_bits_still_stall(self):
        before = self.rx()
        for flags in (4, 5, 7, 0x100, 0x10000, 0x80000000, 0xFFFFFFFF):
            with self.subTest(flags=hex(flags)):
                self.assertEqual(self.begin(0, 4 * KIB, flags=flags), M.H_STALL)
        after = self.rx()
        self.assertEqual(after["rx_rejects"], before["rx_rejects"] + 7)
        self.assertEqual((after["state"], after["committed"]), (0, 0))
        self.clean()


class StagedModeTests(V2):
    DIRECT = False

    def test_staged_mode_accepts_only_plain(self):
        for mode in (FAST, CACHED, NONE):
            self.assertEqual(self.begin(0, 4 * KIB, flags=mode), M.H_STALL)
        d = blob(4 * KIB, 40)
        r = self.putm(0, d, PLAIN)
        self.assertEqual(r["last_sum"], ref_sum(d))
        self.assertEqual(self.rxt()["caps"], 1)
        self.assertEqual(self.sumreq(0, 4096, FAST), M.H_STALL)
        self.assertEqual(self.sumreq(0, 4096, PLAIN), M.H_OK)
        self.assertEqual(self.rxt()["sreq_sum"], ref_sum(d))
        self.clean()


class SumRequestTests(V2):
    def test_sum_of_committed_bytes_in_every_mode(self):
        d = blob(64 * KIB, 50)
        self.putm(0, d, NONE)
        for mode in (PLAIN, FAST, CACHED):
            for off, n in ((0, 64 * KIB), (4096, 8192), (63 * KIB, 1024)):
                with self.subTest(mode=mode, off=off, n=n):
                    self.assertEqual(self.sumreq(off, n, mode), M.H_OK)
                    t = self.rxt()
                    self.assertEqual((t["sreq_status"], t["sreq_off"], t["sreq_len"], t["sreq_mode"]), (SREQ_OK, off, n, mode))
                    self.assertEqual(t["sreq_sum"], ref_sum(d[off:off + n]))
                    self.assertGreater(t["sreq_ticks"], 0)
        self.assertEqual(self.rxt()["sreq_count"], 9)
        self.clean()

    def test_sum_sees_what_is_really_in_memory(self):
        d = blob(16 * KIB, 51)
        self.m.set_dma_limit(8 * KIB)		# the controller loses the second half; a NONE commit cannot know
        self.putm(0, d, NONE)
        self.assertEqual(self.sumreq(0, 16 * KIB, CACHED), M.H_OK)
        t = self.rxt()
        self.assertNotEqual(t["sreq_sum"], ref_sum(d))
        self.assertEqual(t["sreq_sum"], ref_sum(self.m.dest(0, 16 * KIB)))

    def test_refusals(self):
        d = blob(16 * KIB, 52)
        self.putm(0, d, PLAIN)
        before = self.rx()
        cases = [
            ("past the committed end", (8 * KIB, 16 * KIB, PLAIN)),
            ("starts past the committed end", (32 * KIB, 512, PLAIN)),
            ("offset wraps", ((1 << 64) - 512, 1024, PLAIN)),
            ("zero length", (0, 0, PLAIN)),
            ("not a multiple of 512", (0, 1000, PLAIN)),
            ("above the chunk limit", (0, 0x800000 + 512, PLAIN)),
            ("mode NONE", (0, 4096, NONE)),
            ("mode 4", (0, 4096, 4)),
            ("mode 0xffffffff", (0, 4096, 0xFFFFFFFF)),
        ]
        for k, (label, args) in enumerate(cases):
            with self.subTest(label):
                self.assertEqual(self.sumreq(*args), M.H_STALL)
                t = self.rxt()
                self.assertEqual((t["sreq_status"], t["sreq_refused"], t["sreq_count"]), (SREQ_REFUSED, k + 1, 0))
        self.assertEqual(self.sumreq(0, 4096, PLAIN, wlength=12), M.H_STALL)
        after = self.rx()
        for f in ("state", "committed", "rx_bytes", "rx_trbs", "rx_errors", "rx_rejects", "last_sum", "last_off"):
            self.assertEqual(after[f], before[f], f)
        self.assertEqual(self.m.dest(0, 16 * KIB), d)
        self.clean()

    def test_refused_while_armed_and_the_transfer_still_completes(self):
        d = blob(8 * KIB, 53)
        self.putm(0, d, PLAIN)
        self.assertEqual(self.begin(8 * KIB, 8 * KIB, flags=NONE), M.H_OK)
        self.assertEqual(self.sumreq(0, 8 * KIB, PLAIN), M.H_STALL)
        e = blob(8 * KIB, 54)
        self.assertEqual(self.m.bulk_out(e), (M.H_OK, 8 * KIB))
        self.assertEqual(self.rx()["committed"], 16 * KIB)
        self.assertEqual(self.sumreq(8 * KIB, 8 * KIB, FAST), M.H_OK)
        self.assertEqual(self.rxt()["sreq_sum"], ref_sum(e))
        self.clean()

    def test_sum_needs_a_configured_device(self):
        m = M.Machine(rx.lib(), rx_size=self.CAP, rx_direct=True)
        try:
            m.attach()
            steps = list(m.enumerate())
            # enumerate() ends with SET_CONFIGURATION(1); undo it
            self.assertEqual(m.ctrl(0x00, 9, 0, 0, 0)[0], M.H_OK)
            self.assertEqual(m.ctrl(0x40, SUM, 0, 0, 16, data=struct.pack("<QII", 0, 512, 0))[0], M.H_STALL)
            self.assertTrue(steps)
        finally:
            m.close()


class TimingTests(V2):
    def test_phase_ticks(self):
        t0 = self.rxt()
        self.assertEqual((t0["magic"], t0["version"], t0["size"], t0["freq"], t0["caps"]), (b"S24T", 1, RXT_SIZE, 25600000, 0xF))
        self.assertEqual((t0["chunks"], t0["tot_wire"], t0["tot_sum"], t0["tot_gap"]), (0, 0, 0, 0))
        pos = 0
        prev_sum1 = None
        for k in range(3):
            d = blob(8 * KIB, 60 + k)
            self.putm(pos, d, (PLAIN, FAST, CACHED)[k])
            pos += len(d)
            t = self.rxt()
            self.assertEqual(t["chunks"], k + 1)
            self.assertTrue(t["t_arm0"] <= t["t_arm1"] <= t["t_done"] <= t["t_sum1"] <= t["now"], t)
            if prev_sum1 is not None:
                self.assertGreater(t["t_arm0"], prev_sum1)
            prev_sum1 = t["t_sum1"]
        self.assertGreater(t["tot_wire"], 0)
        self.assertGreater(t["tot_sum"], 0)
        self.assertGreater(t["tot_arm"], 0)
        self.assertGreater(t["tot_gap"], 0)
        self.assertLess(t["tot_gap"], t["t_sum1"])	# the first chunk contributes no gap (no previous commit)
        self.clean()

    def test_a_failed_chunk_is_not_timed(self):
        d = blob(8 * KIB, 70)
        self.m.bulk_fault(1, after=4 * KIB)
        self.assertEqual(self.begin(0, 8 * KIB, flags=FAST), M.H_OK)
        self.m.bulk_out(d)
        r = self.rx()
        self.assertEqual((r["state"], r["committed"], r["rx_errors"]), (2, 0, 1))
        self.assertEqual(self.rxt()["chunks"], 0)
        r = self.putm(0, d, FAST)
        self.assertEqual((r["committed"], r["last_sum"]), (8 * KIB, ref_sum(d)))
        self.assertEqual(self.rxt()["chunks"], 1)


# ---- seeded defects: each must be caught by its scenario, which must pass on the real engine

class P2(rx.Probe):
    def __init__(self, m, direct):
        super().__init__(m, direct)
        m.calls0 = raw_counters(m)

    def rxt(self):
        rc, raw = self.m.ctrl(0xC0, GET_RXT, 0, 0, RXT_SIZE)
        if rc != M.H_OK:
            self.problems.append("GET_RXT rc %s" % rc)
            return {k: 0 for k in RXT}
        return rxtf(raw)

    def sumreq(self, off, n, mode):
        return self.m.ctrl(0x40, SUM, 0, 0, 16, data=struct.pack("<QII", off, n, mode))[0]


def sc_modes(p):
    p.up()
    pos = 0
    for mode in (FAST, CACHED):
        d = blob(8192, 80 + mode)
        p.check(p.begin(pos, 8192, flags=mode) == M.H_OK, "RX_BEGIN mode %d refused" % mode)
        p.m.bulk_out(d)
        r = p.rx()
        p.check(r["last_sum"] == ref_sum(d), "mode %d sum" % mode)
        pos += 8192
    p.check(counters(p.m) == (1, 1), "the port's mode functions were not used: %s" % (counters(p.m),))
    return p.finish()


def sc_none(p):
    p.up()
    d = blob(8192, 90)
    p.check(p.begin(0, 8192, flags=NONE) == M.H_OK, "RX_BEGIN NONE refused")
    p.m.bulk_out(d)
    r = p.rx()
    p.check((r["committed"], r["last_sum"]) == (8192, 0), "NONE commit: %s" % ((r["committed"], r["last_sum"]),))
    p.check(p.rxt()["unsummed"] == 1, "unsummed not counted")
    p.check(counters(p.m) == (0, 0), "a sum was taken in mode NONE")
    p.check(p.sumreq(0, 8192, PLAIN) == M.H_OK and p.rxt()["sreq_sum"] == ref_sum(d), "SUM of the NONE chunk")
    return p.finish()


def sc_sum_refusals(p):
    p.up()
    p.chunk(0, blob(8192, 91))
    p.refused("SUM past the committed end", p.sumreq(4096, 8192, PLAIN))
    p.refused("SUM of length 1000", p.sumreq(0, 1000, PLAIN))
    p.refused("SUM above the chunk limit", p.sumreq(0, 0x800000 + 512 if p.direct else 65536 + 512, PLAIN))
    p.refused("SUM mode NONE", p.sumreq(0, 512, NONE))
    p.refused("SUM mode 4", p.sumreq(0, 512, 4))
    p.check(p.rxt()["sreq_count"] == 0, "a refused SUM was counted as done")
    return p.finish()


def sc_flags76(p):
    """sc_refusals of NAT-076 with the flags case moved to a value that is still invalid in NAT-130."""
    p.up()
    p.chunk(0, blob(4096, 4))
    p.refused("length zero", p.begin(4096, 0))
    p.refused("a length that is not a multiple of 512", p.begin(4096, 1000))
    p.refused("flags 4", p.begin(4096, 4096, flags=4))
    p.refused("flags 0x100", p.begin(4096, 4096, flags=0x100))
    if not p.direct:
        p.refused("a checksum mode in staged mode", p.begin(4096, 4096, flags=FAST))
    r = p.rx()
    p.check((r["state"], r["committed"]) == (0, 4096), "a refusal changed the state")
    return p.finish()


def sc_chunk_limit(p):
    p.up()
    p.refused("a chunk over the limit", p.begin(0, (0x800000 if p.direct else 65536) + 512))
    return p.finish()


def sc_timing(p):
    p.up()
    for k in range(3):
        p.chunk(k * 4096, blob(4096, 95 + k))
    t = p.rxt()
    p.check(t["chunks"] == 3, "chunks timed %d" % t["chunks"])
    p.check(0 < t["tot_gap"] < t["t_sum1"] - t["t_arm0"] + t["tot_gap"] and t["tot_gap"] < t["now"] // 2, "tot_gap %d" % t["tot_gap"])
    p.check(t["tot_wire"] > 0 and t["tot_sum"] > 0 and t["tot_arm"] > 0, "a phase total is zero: %s" % t)
    p.check(t["t_arm0"] <= t["t_arm1"] <= t["t_done"] <= t["t_sum1"], "phase order")
    return p.finish()


class SeededDefectTests(unittest.TestCase):
    CASES = {
        "length_not_a_packet_multiple_accepted": (
            "if (!len || (len % USBMON_RX_MPS) || len > rx_chunk_max(m) || len > m->rx_size - off) {",
            "if (!len || len > rx_chunk_max(m) || len > m->rx_size - off) {", sc_flags76, False),
        "chunk_limit_ignored": (
            "if (!len || (len % USBMON_RX_MPS) || len > rx_chunk_max(m) || len > m->rx_size - off) {",
            "if (!len || (len % USBMON_RX_MPS) || len > m->rx_size - off) {", sc_chunk_limit, False),
        "flags_ignored": ("(flags & ~USBMON_RXB_SUM_MASK) || !rx_mode_ok(m, flags & USBMON_RXB_SUM_MASK, 1)", "0", sc_flags76, False),
        "mode_mask_ignored": ("(flags & ~USBMON_RXB_SUM_MASK) || ", "", sc_flags76, True),
        "staged_accepts_modes": ("	if (!m->rx_direct)\n		return 0;\n	if (mode == USBMON_SUM_NONE)", "	if (mode == USBMON_SUM_NONE)",
                                 sc_flags76, False),
        "mode_not_recorded": ("	m->rx_mode = flags & USBMON_RXB_SUM_MASK;\n", "", sc_modes, True),
        "commit_ignores_the_mode": ("m->rx_last_sum = rx_sum_mode(m->rx_dest + m->rx_armed_off, m->rx_armed_len, m->rx_mode);",
                                    "m->rx_last_sum = usbmon_rx_sum(m->rx_dest + m->rx_armed_off, m->rx_armed_len);", sc_modes, True),
        "fast_dispatch_wrong": ("	if (mode == USBMON_SUM_FAST)\n		return usbmon_dest_sum_fast(p, n);\n", "", sc_modes, True),
        "none_still_sums": ("		if (m->rx_mode == USBMON_SUM_NONE) {", "		if (0) {", sc_none, True),
        "none_not_counted": ("			m->rx_unsummed++;\n", "", sc_none, True),
        "sum_req_accepts_uncommitted": ("off > m->rx_committed || len > m->rx_committed - off", "0", sc_sum_refusals, True),
        "sum_req_mode_unchecked": ("mode > USBMON_SUM_CACHED || !rx_mode_ok(m, mode, 0) || ", "", sc_sum_refusals, True),
        "sum_req_any_length": ("	    (len % USBMON_RX_MPS) || len > rx_chunk_max(m) || off > m->rx_committed",
                               "	    off > m->rx_committed", sc_sum_refusals, True),
        "refused_sum_counted": ("	m->sreq_count++;\n", "	m->sreq_count++;\n", sc_sum_refusals, True),
        "gap_includes_the_first_chunk": ("	if (m->rx_timed)\n		m->rx_tot_gap", "	m->rx_tot_gap", sc_timing, True),
        "wire_not_accumulated": ("	m->rx_tot_wire += m->rx_t_done - m->rx_t_arm1;\n", "", sc_timing, True),
        "arm1_before_the_sync": ("	m->rx_t_arm1 = usbmon_ticks();", "	m->rx_t_arm1 = t0;", sc_timing, True),
    }
    # Not seeded: removing the destination sync at the start of rx_sum_req() is equivalent in the model, because a committed
    # range was already invalidated by its commit and nothing writes it afterwards; it stays as a defence for the hardware.
    # "refused_sum_counted" is not a defect (old == new): it documents that the count sits after every refusal check; see
    # test_the_count_is_only_reached_after_the_checks below. It is excluded from the generated tests.

    def run_scenario(self, scenario, direct, lib):
        m = M.Machine(lib, rx_size=256 * KIB, rx_direct=direct)
        try:
            self.assertEqual(m.init_rc, 0)
            return scenario(P2(m, direct))
        finally:
            m.close()

    def build_mutant(self, old, new):
        src = slurp(ENGINE_C)
        self.assertEqual(src.count(old), 1, "mutation anchor must occur exactly once: %r" % old)
        path = os.path.join(rx._TMP, "mut130-%d.c" % abs(hash(old + new)))
        with open(path, "w") as f:
            f.write(src.replace(old, new))
        return M.build(engine_src=path, out_dir=rx._TMP, extra=["-I", os.path.join(HERE, "engine")], strict=False)

    def test_the_count_is_only_reached_after_the_checks(self):
        src = slurp(ENGINE_C)
        body = src[src.index("static int rx_sum_req("):]
        body = body[:body.index("\n}\n")]
        self.assertLess(body.index("return -1;"), body.index("m->sreq_count++;"))


def _make(name, old, new, scenario, direct):
    def test(self):
        self.assertEqual(self.run_scenario(scenario, direct, rx.lib()), [], "the scenario already fails on the real engine")
        found = self.run_scenario(scenario, direct, self.build_mutant(old, new))
        self.assertTrue(found, "the defect went unnoticed")
    return test


for _n, (_o, _w, _s, _d) in SeededDefectTests.CASES.items():
    if _o != _w:
        setattr(SeededDefectTests, "test_" + _n, _make(_n, _o, _w, _s, _d))


if __name__ == "__main__":
    unittest.main()
