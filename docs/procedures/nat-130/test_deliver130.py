"""deliver130.py end to end on the model: the unchanged NAT-080 companion with the NAT-130 sender, a SumCache started before
the device is ready, and the phase summary in delivery.json. Host-test only."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_sender130 as T  # noqa: E402
import root_send130 as S  # noqa: E402
import deliver130  # noqa: E402

KIB = 1024


class DeliverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nat130-deliver-", dir=os.environ.get("TMPDIR")))
        self.m = T.M.Machine(T.rx.lib(), rx_size=48 * 16 * KIB, rx_direct=True)   # the companion wants capacity == root size
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.assertEqual(rc, T.M.H_OK, name)
        m = self.m

        class Fake(T.ModelTransport130):
            def __init__(self, configure=True):
                super().__init__(m)
        self.saved = S.PyUsbTransport
        S.PyUsbTransport = Fake
        deliver130.rs130.PyUsbTransport = Fake

    def tearDown(self):
        S.PyUsbTransport = self.saved
        deliver130.rs130.PyUsbTransport = self.saved
        self.m.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_end_to_end(self):
        import hashlib
        data = T.blob(48 * 16 * KIB, 77)
        root = self.tmp / "root.img"
        root.write_bytes(data)
        out = self.tmp / "out"
        rc = deliver130.main(["--root", str(root), "--size", str(len(data)), "--sha256", hashlib.sha256(data).hexdigest(), "--out", str(out),
                              "--wait-s", "5", "--deliver-s", "60", "--chunk", str(16 * KIB), "--write-size", str(16 * KIB),
                              "--progress-bytes", str(128 * KIB), "--policy", "auto", "--none-chunks", "3"])
        doc = json.loads((out / "delivery.json").read_text())
        self.assertEqual((rc, doc["outcome"]), (0, "delivered"), doc.get("error"))
        self.assertEqual(doc["device"]["committed"], len(data))
        self.assertEqual(self.m.dest(0, len(data)), data)
        self.assertEqual(doc["nat130"]["policy"], "auto")
        self.assertEqual(doc["phases"]["chunks"], 48)
        self.assertEqual(doc["phases"]["by_mode"]["none"]["n"], 3)
        self.assertTrue(all(v["ok"] for v in doc["sender"]["post_verify"]))
        events = [json.loads(l)["event"] for l in (out / "delivery.jsonl").read_text().splitlines()]
        self.assertLess(events.index("sumcache-started"), events.index("ready"))

    def test_selftest_passes_through(self):
        # the companion's own self-test needs pyusb; here only that our wrapper forwards the flag and returns its status
        rc = deliver130.main(["--selftest"])
        self.assertIn(rc, (0, 2))


class SumCacheTests(unittest.TestCase):
    def test_cache_equals_chunk_sum_and_counts(self):
        data = T.blob(10 * 16 * KIB + 8 * KIB, 5)
        c = S.SumCache(data, 0, 16 * KIB)
        c.thread.join()
        for off in range(0, len(data), 16 * KIB):
            piece = data[off:off + 16 * KIB]
            self.assertEqual(c.get(off, piece), S.chunk_sum(piece))
        self.assertEqual(c.stats, dict(hits=11, misses=0))
        self.assertEqual(c.get(4096, data[4096:8192]), S.chunk_sum(data[4096:8192]))	# not a chunk: computed on the spot
        self.assertEqual(c.stats["misses"], 1)


if __name__ == "__main__":
    unittest.main()
