"""deliver134.py end to end on the NAT-134 model: the probe runs on the delivery connection before the first RX_BEGIN, its
journal is written, a gated group is skipped, a failing read stops the run before any delivery, and --no-peek is NAT-130.
Host-test only."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regress134  # noqa: E402,F401  (must come first: it points the shared NAT-076 helpers at the NAT-134 engine)
sys.path.insert(1, os.path.join(HERE, "..", "nat-130"))
import test_sender130 as T  # noqa: E402
import peek134 as P  # noqa: E402
import deliver134  # noqa: E402
import test_nat134 as N  # noqa: E402

KIB = 1024
S = deliver134.rs130


class DeliverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nat134-deliver-", dir=os.environ.get("TMPDIR")))
        self.m = T.M.Machine(T.rx.lib(), rx_size=24 * 16 * KIB, rx_direct=True)
        self.lib = N.bind(self.m.lib)
        self.lib.model_peek_reset()
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, T.M.H_OK, name)
        m, test = self.m, self
        test.events = []

        class Fake(T.ModelTransport130):
            def __init__(self, configure=True):
                super().__init__(m)

            def rx_begin(self, offset, length, flags=0):
                test.events.append(("rx_begin", offset))
                return super().rx_begin(offset, length, flags)

            def peek(self, index):
                test.events.append(("peek", index))
                rc, raw = m.ctrl(0xC0, P.PEEK_REQ, index, P.PEEK_KEY, P.PEEK_SIZE)
                if rc != T.M.H_OK:
                    raise S.TransportError("PEEK: %s" % rc)
                return raw
        self.saved = S.PyUsbTransport
        S.PyUsbTransport = Fake

    def tearDown(self):
        S.PyUsbTransport = self.saved
        self.m.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def regfile(self, overrides=None, faults=()):
        self.lib.model_peek_reset()
        for i, (a, g, _) in enumerate(P.TABLE):
            v = (overrides or {}).get(a, N.ON if g in ("cmu_hsi0", "cmu_peric2") else 0x5A000000 | i)
            self.lib.model_peek_set(a, v, 1 if a in faults else 0)

    def deliver(self, *extra):
        data = T.blob(24 * 16 * KIB, 91)
        root = self.tmp / "root.img"
        root.write_bytes(data)
        out = self.tmp / "out"
        rc = deliver134.main(["--root", str(root), "--size", str(len(data)), "--sha256", hashlib.sha256(data).hexdigest(), "--out", str(out),
                              "--wait-s", "5", "--deliver-s", "60", "--chunk", str(16 * KIB), "--write-size", str(16 * KIB),
                              "--progress-bytes", str(128 * KIB), "--policy", "auto", "--none-chunks", "2", *extra])
        return rc, json.loads((out / "delivery.json").read_text()), out, data

    def test_probe_then_delivery(self):
        self.regfile()
        rc, doc, out, data = self.deliver()
        self.assertEqual((rc, doc["outcome"]), (0, "delivered"), doc.get("error"))
        self.assertEqual(self.m.dest(0, len(data)), data)
        res = doc["nat134"]["result"]
        self.assertTrue(res["complete"])
        self.assertEqual(len(res["rows"]), len(P.TABLE))
        first_begin = self.events.index(("rx_begin", 0))
        self.assertEqual(self.events[:first_begin], [("peek", i) for i in range(len(P.TABLE))])
        self.assertNotIn("peek", [e[0] for e in self.events[first_begin:]])
        lines = [json.loads(x) for x in (out / "peek.jsonl").read_text().splitlines()]
        self.assertEqual(sum(1 for x in lines if x["event"] == "value"), len(P.TABLE))
        self.assertEqual(self.m.violations(), [])

    def test_gated_group_skipped_and_delivery_goes_on(self):
        self.regfile({P.GATES["tca"]: N.OFF})
        rc, doc, _, data = self.deliver()
        self.assertEqual(doc["outcome"], "delivered")
        self.assertEqual([s["group"] for s in doc["nat134"]["result"]["skipped"]], ["tca"])
        read = N.reads(self.lib)[0]
        self.assertFalse(set(read) & {a for a, g, _ in P.TABLE if g == "tca"})

    def test_a_failed_read_stops_before_any_delivery(self):
        self.regfile()
        stop = [i for i, (_, g, _) in enumerate(P.TABLE) if g == "usbdp"][0]
        real = S.PyUsbTransport.peek

        def peek(self_, index):
            if index == stop:
                raise S.TransportError("timeout")
            return real(self_, index)
        S.PyUsbTransport.peek = peek
        try:
            rc, doc, _, _ = self.deliver()
        finally:
            S.PyUsbTransport.peek = real
        self.assertNotEqual(doc["outcome"], "delivered")
        self.assertIn("register probe stopped at PEEK %d" % stop, doc["error"])
        self.assertNotIn("rx_begin", [e[0] for e in self.events])
        self.assertEqual(doc["nat134"]["result"]["error"]["index"], stop)

    def test_no_peek_is_nat130(self):
        self.regfile()
        rc, doc, out, data = self.deliver("--no-peek")
        self.assertEqual(doc["outcome"], "delivered")
        self.assertNotIn("peek", [e[0] for e in self.events])
        self.assertEqual(N.reads(self.lib)[1], 0)
        self.assertFalse((out / "peek.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
