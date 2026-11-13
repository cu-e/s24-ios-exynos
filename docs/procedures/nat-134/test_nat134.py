"""Host tests of NAT-134: the engine's PEEK request (engine/usbmon.c) on the NAT-076/NAT-130 model, and the host probe logic
(peek134.py run(): order, gating, stop on the first failure, journal before the next request).

Evidence kind: host-test. The model's register file is the test's own; nothing here says what the phone's registers hold or
whether reading them is safe on the phone. That is what the native run measures.
"""
import ctypes
import json
import os
import re
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import peek134 as P  # noqa: E402
import regress134  # noqa: E402

rx, M, _t130 = regress134.load_suites()
ENGINE_C = os.path.join(HERE, "engine", "usbmon.c")
ON = (1 << 20) | (1 << 21)		# MANUAL, CGVAL = 1: clock on
OFF = 1 << 20			# MANUAL = 1, CGVAL = 0: clock manually off
AUTO = 1 << 28			# automatic gating


def c_table(src):
    body = re.search(r"static const uint32_t peek_addr\[\] = \{\n(.*?)\n\};", src, re.S).group(1)
    return [int(x, 16) for x in re.findall(r"0x([0-9a-f]{8})u", body)]


def bind(lib):
    lib.model_peek_set.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    lib.model_peek_set.restype = ctypes.c_int
    lib.model_peek_reset.argtypes = []
    return lib


def reads(lib):
    n = ctypes.c_uint32.in_dll(lib, "model_peek_reads").value
    log = (ctypes.c_uint32 * 1024).in_dll(lib, "model_peek_log")
    return [log[i] for i in range(min(n, 1024))], n


class Base(unittest.TestCase):
    LIB = None

    def lib_path(self):
        return rx.lib()

    def setUp(self):
        self.m = M.Machine(self.lib_path(), rx_size=1024 * 1024, rx_direct=True)
        self.assertEqual(self.m.init_rc, 0)
        self.lib = bind(self.m.lib)
        self.lib.model_peek_reset()
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, M.H_OK, name)
        self.values = {}

    def tearDown(self):
        self.m.close()

    def regfile(self, overrides=None, faults=()):
        self.lib.model_peek_reset()
        self.values = {}
        for i, (a, g, n) in enumerate(P.TABLE):
            v = (0xA5000000 | i) if g not in ("cmu_hsi0", "cmu_peric2") else ON
            v = (overrides or {}).get(a, v)
            self.values[a] = v
            self.assertEqual(self.lib.model_peek_set(a, v, 1 if a in faults else 0), 0)

    def peek(self, index, key=P.PEEK_KEY, length=P.PEEK_SIZE, bm=0xC0):
        return self.m.ctrl(bm, P.PEEK_REQ, index, key, length)


class TableTests(unittest.TestCase):
    def test_engine_table_is_the_host_table(self):
        with open(ENGINE_C) as f:
            self.assertEqual(c_table(f.read()), [a for a, _, _ in P.TABLE])

    def test_table_shape(self):
        addrs = [a for a, _, _ in P.TABLE]
        self.assertEqual(len(addrs), len(set(addrs)))
        self.assertTrue(all(a % 4 == 0 and a < 1 << 32 for a in addrs))
        self.assertLess(len(addrs), 0x10000)
        groups = [g for _, g, _ in P.TABLE]
        self.assertEqual(groups, sorted(groups, key=P.GROUP_ORDER.index))
        for g, gate in P.GATES.items():
            gi = addrs.index(gate)
            self.assertLess(gi, min(i for i, (_, gg, _) in enumerate(P.TABLE) if gg == g), "gate of %s read after the group" % g)

    def test_every_address_is_in_a_nat131_block(self):
        blocks = {"pmu": (0x12860000, 0x10000), "dwc3": (0x17900000, 0x10000), "usbcon": (0x178A0000, 0x200),
                  "cmu_hsi0": (0x17800000, 0x8000), "usbdp": (0x178D0000, 0x800), "tca": (0x178E0000, 0x800),
                  "cmu_peric2": (0x11800000, 0x8000), "gpio": (0x118301A0, 0x20)}
        for a, g, n in P.TABLE:
            base, size = blocks[g]
            self.assertTrue(base <= a < base + size, "%s %#x outside %s" % (n, a, g))

    def test_gate_rule(self):
        self.assertTrue(P.manually_gated(OFF))
        self.assertFalse(P.manually_gated(ON))
        self.assertFalse(P.manually_gated(AUTO))
        self.assertFalse(P.manually_gated(0))
        self.assertFalse(P.manually_gated(1 << 21))


class PeekProtocolTests(Base):
    def test_every_entry_reads_its_address(self):
        self.regfile()
        for i, (a, _, _) in enumerate(P.TABLE):
            rc, raw = self.peek(i)
            self.assertEqual(rc, M.H_OK, i)
            r = P.parse(raw)
            self.assertEqual(r, dict(index=i, count=len(P.TABLE), addr=a, value=self.values[a]))
        log, n = reads(self.lib)
        self.assertEqual(log, [a for a, _, _ in P.TABLE])
        self.assertEqual(self.m.violations(), [])

    def test_refusals_read_nothing(self):
        self.regfile()
        for desc, kw in (("legacy wIndex 0", dict(key=0)), ("wrong key", dict(key=P.PEEK_KEY ^ 1)), ("index past the table", dict(index=len(P.TABLE))),
                         ("index 0xffff", dict(index=0xFFFF)), ("short wLength", dict(length=P.PEEK_SIZE - 1)), ("OUT direction", dict(bm=0x40, length=0))):
            with self.subTest(desc):
                kw.setdefault("index", 0)
                rc, _ = self.peek(**kw)
                self.assertNotEqual(rc, M.H_OK)
                self.assertEqual(reads(self.lib)[1], 0)
        rc, _ = self.peek(0)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(reads(self.lib)[1], 1)
        self.assertEqual(self.m.violations(), [])

    def test_long_wlength_is_truncated_to_the_reply(self):
        self.regfile()
        rc, raw = self.peek(3, length=64)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(len(raw), P.PEEK_SIZE)

    def test_peek_does_not_disturb_delivery(self):
        self.regfile()
        data = rx.blob(64 * 1024, 7)
        for i in range(len(P.TABLE)):
            self.assertEqual(self.peek(i)[0], M.H_OK)
        rc, _ = self.m.ctrl(0x40, 6, 0, 0, 16, data=struct.pack("<QII", 0, len(data), 0))
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(self.m.bulk_out(data)[0], M.H_OK)
        for _ in range(50):
            self.m.poll(20)
        rc, raw = self.m.ctrl(0xC0, 7, 0, 0, 120)
        self.assertEqual(rc, M.H_OK)
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assertEqual(self.m.violations(), [])


class HostRunTests(Base):
    def run_probe(self, **kw):
        fd, path = tempfile.mkstemp(dir=rx._TMP, suffix=".jsonl")
        os.close(fd)
        os.unlink(path)

        def peek(i):
            rc, raw = self.peek(i)
            if rc != M.H_OK:
                raise RuntimeError("PEEK stall rc=%s" % rc)
            return raw
        out = P.run(peek, path, log=lambda s: None, **kw)
        with open(path) as f:
            journal = [json.loads(x) for x in f]
        return out, journal

    def test_full_run(self):
        self.regfile()
        out, journal = self.run_probe()
        self.assertTrue(out["complete"])
        self.assertIsNone(out["error"])
        self.assertEqual([r["addr"] for r in out["rows"]], [a for a, _, _ in P.TABLE])
        self.assertEqual(reads(self.lib)[0], [a for a, _, _ in P.TABLE])
        self.assertEqual([j["event"] for j in journal], ["request", "value"] * len(P.TABLE))

    def test_a_manually_gated_block_is_not_read(self):
        for group, gate in P.GATES.items():
            with self.subTest(group):
                self.regfile({gate: OFF})
                out, journal = self.run_probe()
                read = reads(self.lib)[0]
                skipped = [a for a, g, _ in P.TABLE if g == group]
                self.assertFalse(set(read) & set(skipped))
                self.assertEqual(read, [a for a, g, _ in P.TABLE if g != group])
                self.assertEqual([s["group"] for s in out["skipped"]], [group])
                self.assertIn(dict(event="skip", group=group, reason="clock manually off", gate=gate, gate_value=OFF), journal)

    def test_auto_gated_blocks_are_read(self):
        self.regfile({g: AUTO for g in P.GATES.values()})
        out, _ = self.run_probe()
        self.assertTrue(out["complete"])
        self.assertEqual(out["skipped"], [])

    def test_the_first_failure_stops_the_probe(self):
        self.regfile()
        stop = [i for i, (_, g, _) in enumerate(P.TABLE) if g == "tca"][2]
        calls = []

        def peek(i):
            calls.append(i)
            if i == stop:
                raise RuntimeError("timeout")
            return self.peek(i)[1]
        fd, path = tempfile.mkstemp(dir=rx._TMP)
        os.close(fd)
        out = P.run(peek, path, log=lambda s: None)
        with open(path) as f:
            journal = [json.loads(x) for x in f]
        self.assertFalse(out["complete"])
        self.assertEqual(out["error"]["index"], stop)
        self.assertEqual(calls[-1], stop)
        self.assertEqual(journal[-2], dict(event="request", index=stop, addr=P.TABLE[stop][0], group="tca", name=P.TABLE[stop][2]))
        self.assertEqual(journal[-1]["event"], "error")

    def test_a_reply_for_another_entry_is_an_error(self):
        self.regfile()

        def peek(i):
            return self.peek(i + 1 if i == 5 else i)[1]
        fd, path = tempfile.mkstemp(dir=rx._TMP)
        os.close(fd)
        out = P.run(peek, path, log=lambda s: None)
        self.assertEqual(out["error"]["index"], 5)
        self.assertIn("mismatch", out["error"]["error"])

    def test_bad_magic_and_short_reply(self):
        with self.assertRaises(ValueError):
            P.parse(b"S24X" + bytes(12))
        with self.assertRaises(ValueError):
            P.parse(b"S24P" + bytes(11))


class SeededDefectTests(Base):
    """Each defect is a one-line change to engine/usbmon.c; the tests above must notice it."""
    CASES = {
        "key_ignored": ("if (c->index != USBMON_PEEK_KEY || c->value >= PEEK_COUNT || want < sizeof(p))",
                        "if (c->value >= PEEK_COUNT || want < sizeof(p))", "test_refusals_read_nothing"),
        "bound_off_by_one": ("if (c->index != USBMON_PEEK_KEY || c->value >= PEEK_COUNT || want < sizeof(p))",
                             "if (c->index != USBMON_PEEK_KEY || c->value > PEEK_COUNT || want < sizeof(p))", "test_refusals_read_nothing"),
        "short_wlength_accepted": ("if (c->index != USBMON_PEEK_KEY || c->value >= PEEK_COUNT || want < sizeof(p))",
                                   "if (c->index != USBMON_PEEK_KEY || c->value >= PEEK_COUNT)", "test_refusals_read_nothing"),
        "value_is_the_address": ("p.value = usbmon_peek32((uintptr_t)peek_addr[c->value]);",
                                 "p.value = peek_addr[c->value];", "test_every_entry_reads_its_address"),
        "index_not_echoed": ("p.index = c->value;", "p.index = 0;", "test_every_entry_reads_its_address"),
        "table_entry_swapped": ("\t0x178d0000u,", "\t0x178d0004u,", "test_engine_table_is_the_host_table"),
    }


def _make(name, old, new, test_name):
    def test(self):
        with open(ENGINE_C) as f:
            src = f.read()
        self.assertEqual(src.count(old), 1, "anchor must occur once: %r" % old)
        if test_name == "test_engine_table_is_the_host_table":
            self.assertNotEqual(c_table(src.replace(old, new)), [a for a, _, _ in P.TABLE])
            return
        path = os.path.join(rx._TMP, "mut134-%s.c" % name)
        with open(path, "w") as f:
            f.write(src.replace(old, new))
        lib = M.build(engine_src=path, out_dir=rx._TMP, extra=["-I", os.path.join(HERE, "engine")], strict=False)
        cls = PeekProtocolTests
        case = cls(test_name)
        case.lib_path = lambda: lib
        result = unittest.TestResult()
        case.run(result)
        self.assertTrue(result.failures or result.errors, "defect %s went unnoticed by %s" % (name, test_name))
    return test


def _control(self):
    """The same mechanism on the unmodified engine: every target test passes, so a 'noticed' defect is the defect."""
    for test_name in sorted({t for _, _, t in SeededDefectTests.CASES.values()} - {"test_engine_table_is_the_host_table"}):
        case = PeekProtocolTests(test_name)
        result = unittest.TestResult()
        case.run(result)
        self.assertFalse(result.failures or result.errors, (test_name, result.failures, result.errors))


SeededDefectTests.test_control_unmodified_engine_passes = _control

for _n, (_o, _w, _t) in SeededDefectTests.CASES.items():
    setattr(SeededDefectTests, "test_" + _n, _make(_n, _o, _w, _t))


if __name__ == "__main__":
    unittest.main()
