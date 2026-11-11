"""NAT-047: the NAT-041 collector (s24_logd.py, unmodified) against the simulated phone of sim47.py.

Rig47 plays the role of test_logd.Rig (backend + fake clock + archive) but its "phone" is the built loader running in unicorn:
every transfer first lets the loader run up to the rig's clock, then the model's USB host performs the control transfer, calling
the loader's own aarch64 usbmon_poll each time the device side must run. Evidence kind: host-test."""
import json
import pathlib
import tempfile

import sim47 as S
import s24_logd as L  # noqa: E402  (sim47 put nat-041 on sys.path)
import usbmon_proto as P  # noqa: E402

A = L.A
M = S.M


def read_rows(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


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


class Rig47:
    NOW0 = 100.0

    def __init__(self, tc, sim, tmp_dir, **colkw):
        self.tc, self.sim, self.m = tc, sim, sim.machine
        self.now = self.NOW0
        self.t_base = sim.t                       # the loader's simulated time at rig time NOW0
        self.plugged = False
        self.hook = None
        self.ntransfer = 0
        self.rng_calls = 0
        self.queries = []
        self.out = pathlib.Path(tempfile.mkdtemp(prefix="logd47-", dir=tmp_dir)) / "attempt"
        self.archive = A.Archive(self.out, "ep0-monitor", "synthetic")
        self.transfers = A.create(self.out / "usb-transfers.jsonl")
        kw = dict(interval=0.02, wait_interval=0.1, dead_after=5.0, grace=2.0, io_timeout_ms=100)
        kw.update(colkw)
        self.col = L.Collector(self, self.archive, self.transfers, rng=self.rng, clock=lambda: self.now, sleep=self.sleep, **kw)
        self.manifest = None
        self.stop = None

    # -- time: the loader follows the rig's clock
    def sync(self):
        self.sim.advance(target_t=self.t_base + int((self.now - self.NOW0) * S.FREQ))

    def sleep(self, dt):
        self.now += dt
        self.sync()

    def rng(self, n):
        self.rng_calls += 1
        return bytes([0x10 + self.rng_calls]) * n

    # -- the simulated bus and backend
    def plug(self):
        self.m.attach()
        for name, rc, _ in self.m.enumerate():
            self.tc.assertEqual(rc, M.H_OK, name)
        self.plugged = True

    def unplug(self):
        self.m.detach()
        self.plugged = False

    def find(self, vid, pid):
        self.queries.append((vid, pid))
        return [RigDevice(self)] if self.plugged else []

    def xfer(self, bm, req, value, index, length, data, timeout_ms):
        self.ntransfer += 1
        self.sync()
        if self.hook:
            self.hook(self, self.ntransfer)
        if self.sim.stopped:                       # the loader reset the SoC: the device is gone from the bus
            self.plugged = False
        if not self.plugged:
            raise L.UsbGone("no device")
        self.now += 0.002
        rc, got = self.m.ctrl(bm, req, value, index, length, data)
        if rc == M.H_STALL:
            raise L.UsbStall("stall")
        if rc != M.H_OK:
            self.now += timeout_ms / 1000.0
            raise L.UsbTimeout(M.RC_NAMES.get(rc, str(rc)))
        return got if bm & 0x80 else len(data)

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
