#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-080: the delivery companion of the NAT-078 session. It waits for the loader's receive phase to be ready, streams the padded root image
into the md1 reserve with tools/ios/root_send.py (unmodified), and writes a durable record of what the DEVICE reports and how fast it went.

    <venv with pyusb>/bin/python -I deliver_nat080.py --root FILE --size N --sha256 H --out DIR [--wait-s 300] [--deliver-s 225]
                                                      [--chunk 8388608] [--write-size 262144] [--progress-bytes 67108864]
    deliver_nat080.py --selftest      (opens no device; checks that pyusb imports and a libusb backend loads)

Host only: it opens the USB device 1209:0001 (the NAT-041 monitor device; Samsung's VID is refused by construction) and talks the NAT-076 vendor
protocol plus bulk-OUT endpoint 1. It writes nothing to the phone's storage and never reboots anything. The NAT-041 collector (s24_logd.py) keeps
polling the same device in its own process; it only issues vendor control transfers on endpoint 0 and never claims an interface, sets a
configuration or resets, so the two do not contend for the interface (the collector's rule is stated at the top of s24_logd.py).

Readiness is a property of the device, not of a clock. The companion polls GET_RX with the device UNconfigured (control transfers on endpoint 0
only) and sends nothing until the reply says the receive path is present, the capacity is exactly --size (the engine has been handed the md1
reserve; before the handoff it reports a 512-byte placeholder) and nothing has been committed. Only then does it set the configuration (once;
the bulk endpoint exists after SET_CONFIGURATION(1)) and start the sender. A capacity that is neither the placeholder nor --size, or a device that
already holds committed bytes, is reported and nothing is sent.

Bounds: --wait-s for the device to become ready (a device that never does is reported `never-ready`), --deliver-s for the transfer itself (the
loader gives up at its own cap; the companion stops a little before it, aborts a transfer left armed and reports the device's committed offset:
`cap-reached`). The sender is not retried by this tool.

Record: DIR/delivery.jsonl (fsynced JSON lines: start, loaded, waiting, ready, progress, sender, reconnect, final) and DIR/delivery.json (the summary, written last). Only the
device's own committed offset is reported as delivered. Exit status: 0 delivered, 1 failed, 3 cap-reached, 4 never-ready, 5 refused-by-device
(the device's GET_RX reply is not a fresh receive path of exactly --size bytes: nothing was sent), 2 refused before opening anything (wrong file, size not a
multiple of 16 KiB, --out already exists)."""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SENDER = ROOT / "tools" / "ios" / "root_send.py"
PLACEHOLDER = 512                  # capacity the engine reports before the loader has handed it the reserve (docs/procedures/nat-079)
MIB = 1 << 20
HEARTBEAT_S = 2.0
EXIT = {"delivered": 0, "failed": 1, "refused": 2, "cap-reached": 3, "never-ready": 4, "refused-by-device": 5}


def load_sender():
    spec = importlib.util.spec_from_file_location("nat080_root_send", SENDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nat080_root_send"] = mod
    spec.loader.exec_module(mod)
    return mod


class CapReached(Exception):
    """Raised by the rate-logging transport when the delivery deadline has passed. Not a TransportError, so the sender does not retry it."""


class Journal:
    """Fsynced JSON lines: a record that survives this process being killed."""

    def __init__(self, path, clock=time.time, mono=time.monotonic):
        self.f = open(path, "x")
        self.clock, self.mono = clock, mono

    def emit(self, event, **kw):
        rec = dict(event=event, t_unix=round(self.clock(), 6), t_mono=round(self.mono(), 6), **kw)
        self.f.write(json.dumps(rec, sort_keys=True) + "\n")
        self.f.flush()
        os.fsync(self.f.fileno())

    def close(self):
        self.f.close()


class MeteredTransport:
    """Wraps the sender's transport: counts the bytes the device accepted, logs progress with a host clock, and enforces the delivery deadline.
    Everything is passed through unchanged."""

    def __init__(self, inner, journal, rs, mono, deadline, progress_bytes, total):
        self.inner, self.journal, self.rs, self.mono = inner, journal, rs, mono
        self.deadline, self.progress_bytes, self.total = deadline, progress_bytes, total
        self.t0 = mono()
        self.sent = 0
        self.next_mark = progress_bytes
        self.last = (self.t0, 0)

    def _check(self):
        if self.mono() >= self.deadline:
            raise CapReached("delivery deadline passed after %d bytes written" % self.sent)

    def rx_begin(self, offset, length):
        self._check()
        return self.inner.rx_begin(offset, length)

    def rx_abort(self):
        return self.inner.rx_abort()

    def get_rx(self):
        return self.inner.get_rx()

    def bulk_write(self, data):
        self._check()
        took = self.inner.bulk_write(data)
        self.sent += took
        if self.sent >= self.next_mark:
            now = self.mono()
            dt, db = now - self.last[0], self.sent - self.last[1]
            self.journal.emit("progress", host_bytes=self.sent, seconds=round(now - self.t0, 3),
                              mb_per_s_total=round(self.sent / max(now - self.t0, 1e-9) / 1e6, 3),
                              mb_per_s_recent=round(db / max(dt, 1e-9) / 1e6, 3), fraction=round(self.sent / self.total, 5))
            self.last = (now, self.sent)
            while self.next_mark <= self.sent:
                self.next_mark += self.progress_bytes
        return took

    def reconnect(self):
        self.journal.emit("reconnect", host_bytes=self.sent)
        return self.inner.reconnect()


def stream_sha256(path, block=8 * MIB):
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def probe_ready(rs, open_probe, size):
    """One look at the device with its endpoint 0 only. -> (state, detail): state is 'absent', 'placeholder', 'ready' or 'refuse'."""
    try:
        t = open_probe()
        rx = rs.parse_rx(t.get_rx())
    except (rs.TransportError, rs.RootSendError) as e:
        return "absent", str(e)
    flags, cap, committed = rx["flags"], rx["capacity"], rx["committed"]
    detail = dict(flags=flags, capacity=cap, committed=committed, state=rx["state"], chunk_max=rx["chunk_max"])
    if not flags & rs.RXF_PRESENT:
        return "refuse", dict(detail, why="the engine has no bulk-OUT receive path")
    if cap == PLACEHOLDER:
        return "placeholder", detail
    if cap != size:
        return "refuse", dict(detail, why="capacity %d is neither the placeholder (%d) nor the root size (%d)" % (cap, PLACEHOLDER, size))
    if committed != 0 or rx["state"] != rs.RX_IDLE:
        return "refuse", dict(detail, why="the device already holds committed bytes or an armed transfer: not a fresh boot")
    return "ready", detail


def deliver(rs, data, open_probe, open_send, journal, wait_s, deliver_s, chunk, write_size, progress_bytes,
            mono=time.monotonic, sleep=time.sleep, sender_kw=None):
    """-> (outcome, summary dict). `data` is the whole padded root image (bytes). open_probe() -> a transport that has NOT set the configuration;
    open_send() -> the transport the sender uses (it sets the configuration once)."""
    size = len(data)
    start = mono()
    waited_since = start
    last_beat = None
    while True:
        state, detail = probe_ready(rs, open_probe, size)
        now = mono()
        if state in ("ready", "refuse"):
            break
        if last_beat is None or now - last_beat >= HEARTBEAT_S:
            journal.emit("waiting", seen=state, detail=detail, waited_s=round(now - waited_since, 3))
            last_beat = now
        if now - waited_since >= wait_s:
            return "never-ready", dict(waited_s=round(now - waited_since, 3), last_seen=state, last_detail=detail)
        sleep(0.2)
    if state == "refuse":
        journal.emit("refuse", detail=detail)
        return "refused-by-device", dict(detail=detail)
    ready_at = mono()
    journal.emit("ready", detail=detail, waited_s=round(ready_at - waited_since, 3))
    try:
        inner = open_send()
    except (rs.TransportError, rs.RootSendError) as e:
        err = "%s: %s" % (type(e).__name__, e)
        journal.emit("send-open-failed", error=err)
        return "failed", dict(device=None, host_bytes_written=0, seconds=0.0, error=err, mb_per_s=None, mib_per_s=None, sender=None)
    transport = MeteredTransport(inner, journal, rs, mono, ready_at + deliver_s, progress_bytes, size)
    kw = dict(sender_kw or {})
    kw.update(chunk=chunk, write_size=write_size, log=lambda m: journal.emit("sender", text=m))
    t0 = mono()
    try:
        r = rs.send(transport, data, **kw)
    except CapReached as e:
        outcome, err = "cap-reached", str(e)
    except (rs.RootSendError, rs.TransportError) as e:
        outcome, err = "failed", "%s: %s" % (type(e).__name__, e)
    else:
        outcome, err = "delivered", None
    seconds = mono() - t0
    try:                           # the device's own view, whatever happened; an armed transfer left behind is ended
        rx = rs.parse_rx(transport.inner.get_rx())
        if outcome != "delivered" and rx["state"] == rs.RX_ARMED:
            try:
                transport.inner.rx_abort()
                rx = rs.parse_rx(transport.inner.get_rx())
            except (rs.TransportError, rs.RootSendError):
                pass
        final = {k: rx[k] for k in ("state", "flags", "committed", "capacity", "rx_bytes", "rx_trbs", "rx_errors", "rx_dups", "rx_gaps",
                                    "rx_rejects", "rx_resets", "rx_aborts", "last_trb_status", "last_evt_status", "last_off", "last_len", "last_sum")}
    except (rs.TransportError, rs.RootSendError, CapReached) as e:
        final = dict(error="%s: %s" % (type(e).__name__, e))
    committed = final.get("committed") if final else None
    summary = dict(device=final, host_bytes_written=transport.sent, seconds=round(seconds, 3), error=err,
                   mb_per_s=round(committed / seconds / 1e6, 3) if committed and seconds > 0 else None,
                   mib_per_s=round(committed / seconds / MIB, 3) if committed and seconds > 0 else None,
                   sender=r if outcome == "delivered" else None)
    return outcome, summary


def selftest():
    res = dict(tool="deliver_nat080", python=sys.executable)
    try:
        import usb.backend.libusb1
        import usb.core
        res["libusb_backend"] = usb.backend.libusb1.get_backend() is not None
        res["find_returns_list"] = isinstance(list(usb.core.find(find_all=True, idVendor=0x1209, idProduct=0x0001)), list)
        res["ok"] = bool(res["libusb_backend"])
    except Exception as e:
        res["ok"], res["error"] = False, "%s: %s" % (type(e).__name__, e)
    print(json.dumps(res, sort_keys=True))
    return 0 if res["ok"] else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path)
    ap.add_argument("--size", type=int)
    ap.add_argument("--sha256")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--wait-s", type=float, default=300.0)
    ap.add_argument("--deliver-s", type=float, default=225.0)
    ap.add_argument("--chunk", type=int, default=8 * MIB)
    ap.add_argument("--write-size", type=int, default=256 * 1024)
    ap.add_argument("--progress-bytes", type=int, default=64 * MIB)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.root and a.size and a.sha256 and a.out):
        ap.error("--root, --size, --sha256 and --out are required")
    rs = load_sender()
    # Refuse before anything is opened: the file must be exactly the image the decision names.
    digest, n = stream_sha256(a.root)
    if n != a.size or digest != a.sha256:
        print("refused: %s is %d bytes sha256 %s; expected %d bytes %s" % (a.root, n, digest, a.size, a.sha256), file=sys.stderr)
        return EXIT["refused"]
    try:
        rs.check_size(n)
    except rs.SizeError as e:
        print("refused: %s" % e, file=sys.stderr)
        return EXIT["refused"]
    if a.out.exists():
        print("refused: %s already exists (a delivery record is never overwritten)" % a.out, file=sys.stderr)
        return EXIT["refused"]
    a.out.mkdir(parents=True, exist_ok=False)
    journal = Journal(a.out / "delivery.jsonl")
    journal.emit("start", pid=os.getpid(), root=str(a.root), size=n, sha256=digest, wait_s=a.wait_s, deliver_s=a.deliver_s, chunk=a.chunk,
                 write_size=a.write_size)
    t_load = time.monotonic()
    data = a.root.read_bytes()
    journal.emit("loaded", bytes=len(data), seconds=round(time.monotonic() - t_load, 3))
    t_start = time.time()
    try:
        outcome, summary = deliver(rs, data, lambda: rs.PyUsbTransport(configure=False), lambda: rs.PyUsbTransport(configure=True), journal,
                                   a.wait_s, a.deliver_s, a.chunk, a.write_size, a.progress_bytes)
    except Exception as e:                        # a defect in this tool: still leave a record
        outcome, summary = "failed", dict(error="%s: %s" % (type(e).__name__, e))
    journal.emit("final", outcome=outcome)
    journal.close()
    doc = dict(tool="deliver_nat080", outcome=outcome, started_unix=round(t_start, 3), size=n, sha256=digest, **summary)
    tmp = a.out / "delivery.json.tmp"
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, a.out / "delivery.json")
    print(json.dumps(dict(outcome=outcome, committed=(summary.get("device") or {}).get("committed"), mb_per_s=summary.get("mb_per_s"))))
    return EXIT.get(outcome, 1)


if __name__ == "__main__":
    sys.exit(main())
