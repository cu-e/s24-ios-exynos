#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-049: start the NAT-041 collector (s24_logd.py, unmodified) for a live run and prove, before the phone is asked to reboot, that
it is polling the bus.

    <venv with pyusb>/bin/python -I collector_launch.py --out RUN/archive --heartbeat RUN/collector-heartbeat.jsonl --seconds 180
    <venv with pyusb>/bin/python -I collector_launch.py --selftest

The collector writes nothing to its archive until a device shows up, so "the archive directory exists" does not show that it looks
at the bus. This launcher puts a thin wrapper around the collector's pyusb backend (s24_logd.PyUsbBackend, otherwise untouched):
every `find()` is passed through, and the wrapper appends fsynced JSONL to --heartbeat: `start` when the backend is created, `poll`
at the first and then every 2 s (number of polls, number of devices found), `found` whenever the number of 1209:0001 devices changes,
`error` if the backend raised. The session driver waits for the first `poll` before it sends the reboot request.

The provenance is always `unqualified-live` (this launcher exists only for the live run; the simulator archives are `synthetic`).
The collector opens only VID 0x1209 / PID 0x0001 and refuses Samsung's VID by construction. `--selftest` opens no device: it checks
that pyusb imports, that a libusb backend loads, and that one `find(0x1209, 0x0001)` returns a list."""
import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGD = HERE.parent / "nat-041" / "s24_logd.py"
HEARTBEAT_S = 2.0


def load_logd():
    spec = importlib.util.spec_from_file_location("nat041_s24_logd", LOGD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nat041_s24_logd"] = mod
    spec.loader.exec_module(mod)
    return mod


class HeartbeatBackend:
    """The collector's backend with a durable record of what it is doing. Everything else is delegated."""

    def __init__(self, inner, path, clock=time.time, mono=time.monotonic):
        self.inner, self.clock, self.mono = inner, clock, mono
        self.f = open(path, "x")
        self.polls = 0
        self.last_beat = None
        self.last_found = None
        self.emit("start", pid=os.getpid())

    def emit(self, event, **kw):
        rec = dict(event=event, t_unix=round(self.clock(), 6), t_mono=round(self.mono(), 6), **kw)
        self.f.write(json.dumps(rec, sort_keys=True) + "\n")
        self.f.flush()
        os.fsync(self.f.fileno())

    def find(self, vid, pid):
        self.polls += 1
        try:
            devs = self.inner.find(vid, pid)
        except Exception as e:
            self.emit("error", polls=self.polls, error=type(e).__name__, detail=str(e))
            raise
        now = self.mono()
        if self.last_beat is None or now - self.last_beat >= HEARTBEAT_S:
            self.last_beat = now
            self.emit("poll", polls=self.polls, found=len(devs))
        if len(devs) != self.last_found:
            self.last_found = len(devs)
            self.emit("found", polls=self.polls, found=len(devs), vid="%04x" % vid, pid="%04x" % pid)
        return devs


def selftest():
    res = dict(tool="collector_launch", python=sys.executable)
    try:
        import usb
        import usb.backend.libusb1
        import usb.core
        res["pyusb"] = getattr(usb, "__version__", "?")
        res["libusb_backend"] = usb.backend.libusb1.get_backend() is not None
        logd = load_logd()
        found = logd.PyUsbBackend().find(logd.P.VID, logd.P.PID)
        res["find_returns_list"] = isinstance(found, list)
        res["monitor_devices_now"] = len(found)
        res["vid_pid"] = "%04x:%04x" % (logd.P.VID, logd.P.PID)
        res["ok"] = bool(res["libusb_backend"] and res["find_returns_list"])
    except Exception as e:                                  # a missing module, no libusb, a backend error: the run must not start
        res["ok"], res["error"] = False, "%s: %s" % (type(e).__name__, e)
    print(json.dumps(res, sort_keys=True))
    return 0 if res["ok"] else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--heartbeat", type=Path)
    ap.add_argument("--seconds", type=float, default=180.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.out or not a.heartbeat:
        ap.error("--out and --heartbeat are required")
    logd = load_logd()
    orig = logd.PyUsbBackend
    logd.PyUsbBackend = lambda *args, **kw: HeartbeatBackend(orig(*args, **kw), a.heartbeat)
    sys.argv = ["s24_logd", "--out", str(a.out), "--provenance", "unqualified-live", "--seconds", str(a.seconds)]
    try:
        return logd.main()
    except (OSError, ValueError) as e:
        print("collector_launch: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
