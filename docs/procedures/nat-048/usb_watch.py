#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-048: timestamped host record of USB enumeration events, for the unattended native runs.

    usb_watch.py --out artifacts/nat-046/RUN/usb-events.jsonl --seconds 240 [--poll 0.1] [--vid 04e8 --vid 18d1] [--all]

Polls the kernel's sysfs view of the USB bus (/sys/bus/usb/devices) and appends one JSON line per event: `start` (with the devices
already present), `appear`, `disappear`, `change` (same device number, other strings) and `stop`. Every line carries `t_unix`
(wall clock) and `t_mono` (CLOCK_MONOTONIC); a device that re-enumerates between two polls (same bus path, new device number) is
reported as `disappear` + `appear`. Lines are fsynced one by one so a killed watcher leaves a usable log.

What it does not do: it reads only the sysfs attributes idVendor, idProduct, product, manufacturer, busnum and devnum; it never
opens a USB device node, never claims or resets anything, never sends a request, never reads the serial number (the log carries
no serial). The default filter keeps only the phone's identities (Samsung 04e8, Google 18d1) and the NAT-041 monitor (1209), so
the log does not list the host's other peripherals. It is an observer: a Download Mode device is only ever read through sysfs.

The log is the host's observation; it says nothing about why the phone re-enumerated."""
import argparse
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

SYSFS = "/sys/bus/usb/devices"
DEFAULT_VIDS = ("04e8", "18d1", "1209")
DEV_RE = re.compile(r"^\d+-\d+(\.\d+)*$")                   # a device, not a root hub (usbN) or an interface (1-4:1.0)
ATTRS = ("idVendor", "idProduct", "product", "manufacturer", "busnum", "devnum")


def read_attr(d, name):
    try:
        return (Path(d) / name).read_text(errors="replace").strip()
    except (OSError, ValueError):
        return None


class Watcher:
    def __init__(self, sysfs=SYSFS, out=None, vids=DEFAULT_VIDS, poll=0.1, clock=time.time, mono=time.monotonic):
        self.sysfs, self.vids, self.poll_s, self.clock, self.mono = Path(sysfs), (set(vids) if vids else None), poll, clock, mono
        self.seq = 0
        self.known = {}
        self.f = open(out, "x") if out else None

    def snapshot(self):
        devs = {}
        try:
            names = sorted(os.listdir(self.sysfs))
        except OSError:
            return devs
        for n in names:
            if not DEV_RE.match(n):
                continue
            d = self.sysfs / n
            a = {k: read_attr(d, k) for k in ATTRS}
            if not a["idVendor"] or not a["idProduct"] or a["devnum"] is None:   # still being enumerated, or gone: next poll
                continue
            if self.vids is not None and a["idVendor"].lower() not in self.vids:
                continue
            devs[n] = dict(path=n, vid=a["idVendor"].lower(), pid=a["idProduct"].lower(), product=a["product"], manufacturer=a["manufacturer"],
                           busnum=a["busnum"], devnum=a["devnum"])
        return devs

    def emit(self, event, **kw):
        self.seq += 1
        rec = dict(seq=self.seq, event=event, t_unix=round(self.clock(), 6), t_mono=round(self.mono(), 6), **kw)
        if self.f:
            self.f.write(json.dumps(rec, sort_keys=True) + "\n")
            self.f.flush()
            os.fsync(self.f.fileno())
        return rec

    def start(self):
        self.known = self.snapshot()
        return [self.emit("start", poll_s=self.poll_s, sysfs=str(self.sysfs), vids=sorted(self.vids) if self.vids else "all",
                          initial=sorted(self.known.values(), key=lambda d: d["path"]))]

    def poll(self):
        now, out = self.snapshot(), []
        for n in sorted(set(self.known) | set(now)):
            old, new = self.known.get(n), now.get(n)
            if old and not new:
                out.append(self.emit("disappear", **old))
            elif new and not old:
                out.append(self.emit("appear", **new))
            elif old["devnum"] != new["devnum"]:                  # re-enumerated between two polls
                out.append(self.emit("disappear", **old))
                out.append(self.emit("appear", **new))
            elif (old["product"], old["manufacturer"], old["pid"]) != (new["product"], new["manufacturer"], new["pid"]):
                out.append(self.emit("change", **new))
        self.known = now
        return out

    def stop(self):
        rec = self.emit("stop")
        if self.f:
            self.f.close()
        return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--poll", type=float, default=0.1)
    ap.add_argument("--sysfs", default=SYSFS)
    ap.add_argument("--vid", action="append", help="hex vendor id to keep (repeatable); default 04e8, 18d1, 1209")
    ap.add_argument("--all", action="store_true", help="log every USB device of the host")
    a = ap.parse_args(argv)
    if a.seconds <= 0 or a.poll <= 0:
        ap.error("--seconds and --poll must be positive")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    w = Watcher(a.sysfs, a.out, None if a.all else tuple(v.lower() for v in (a.vid or DEFAULT_VIDS)), a.poll)
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
    signal.signal(signal.SIGINT, lambda *_: stopping.append(1))
    w.start()
    end = time.monotonic() + a.seconds
    while not stopping and time.monotonic() < end:
        time.sleep(a.poll)
        w.poll()
    w.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
