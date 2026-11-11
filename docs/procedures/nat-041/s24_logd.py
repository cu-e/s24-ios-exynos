#!/usr/bin/env python3
"""s24_logd: unattended host collector for the NAT-041 EP0 log monitor.

Waits for the monitor's USB device (VID 0x1209, PID 0x0001), sends a fresh host nonce, pulls the engine's RAM log ring and
exception frame with vendor control-IN transfers and stores everything through the NAT-016 archive (docs/procedures/
nat-016/archive.py): one directory per invocation, raw bytes fsynced before they are interpreted, one boot record per device
run, gaps and drops accounted for. Besides the archive's JSONL frames, every control transfer is kept in
usb-transfers.jsonl so the raw device bytes survive next to their framed view.

What this tool does not do: it opens only devices with the monitor's VID/PID (never a Samsung Download Mode device), sends
only vendor requests 0x04 (SET_NONCE) and 0x01..0x03 (reads), never SET_CONFIGURATION, never resets or claims anything and
never touches an Android device. Its output is host receipt only: provenance stays 'unqualified-live' until a real run
(NAT-043) has been verified.

Run it with a python that has pyusb (the project's venv python), e.g.
    artifacts/recovery-rescue-20261110-01/venv/bin/python -I docs/procedures/nat-041/s24_logd.py --out artifacts/nat-043/NEW \\
        --provenance unqualified-live --seconds 600
"""
import argparse
import base64
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import usbmon_proto as P  # noqa: E402


def _load_archive():
    path = os.path.join(HERE, "..", "nat-016", "archive.py")
    spec = importlib.util.spec_from_file_location("nat016_archive", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A = _load_archive()

VENDOR_IN = 0xC0
VENDOR_OUT = 0x40
REFUSED_VIDS = (0x04E8,)     # Samsung: the phone's own Download Mode / Android USB identities are never opened here
IO_TIMEOUT_MS = 1000
MAX_READS_PER_CYCLE = 64
MAX_READ_FAILURES = 50


class UsbError(Exception):
    pass


class UsbGone(UsbError):
    """The device is no longer there (ENODEV)."""


class UsbTimeout(UsbError):
    """No answer in time, or a transient I/O error: the device may answer later."""


class UsbStall(UsbError):
    """The device stalled the request."""


class UsbAccess(UsbError):
    """Permission denied opening the device."""


class PyUsbDevice:
    def __init__(self, dev, usb_core):
        self.dev = dev
        self.usb = usb_core
        self.info = {"vid": dev.idVendor, "pid": dev.idProduct, "bus": getattr(dev, "bus", None),
                     "address": getattr(dev, "address", None)}

    def _map(self, e):
        errno = getattr(e, "errno", None)
        if errno == 19:
            return UsbGone(str(e))
        if errno == 13:
            return UsbAccess(str(e))
        if errno == 32:
            return UsbStall(str(e))
        return UsbTimeout(str(e))    # 110 (timeout), 5 (I/O error) and anything else unknown: retry, never crash

    def control_in(self, request, value, index, length, timeout_ms):
        try:
            return bytes(self.dev.ctrl_transfer(VENDOR_IN, request, value, index, length, timeout_ms))
        except self.usb.USBError as e:
            raise self._map(e)

    def control_out(self, request, value, index, data, timeout_ms):
        try:
            return int(self.dev.ctrl_transfer(VENDOR_OUT, request, value, index, bytes(data), timeout_ms))
        except self.usb.USBError as e:
            raise self._map(e)

    def close(self):
        try:
            import usb.util
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass


class PyUsbBackend:
    def __init__(self, usb_core=None):
        if usb_core is None:
            import usb.core as usb_core
        self.usb = usb_core

    def find(self, vid, pid):
        try:
            devs = list(self.usb.find(find_all=True, idVendor=vid, idProduct=pid))
        except self.usb.NoBackendError as e:
            raise UsbError("no libusb backend: %s" % e)
        return [PyUsbDevice(d, self.usb) for d in devs]


class Boot:
    """The collector's state for one device run (one NAT-016 boot record)."""

    def __init__(self, boot_id, nonce, dev_boot, next_off):
        self.boot_id = boot_id
        self.nonce = nonce
        self.dev_boot = dev_boot
        self.fseq = 0
        self.next_off = next_off
        self.dev_next_seq = None
        self.exc_faults = None
        self.last_info = None
        self.gone_at = None
        self.read_failures = 0


class Collector:
    def __init__(self, backend, archive, transfers, vid=P.VID, pid=P.PID, rng=os.urandom, clock=time.monotonic,
                 sleep=time.sleep, interval=0.02, wait_interval=0.1, dead_after=30.0, grace=10.0,
                 io_timeout_ms=IO_TIMEOUT_MS):
        if vid in REFUSED_VIDS:
            raise ValueError("refusing to open vendor id 0x%04x" % vid)
        self.backend, self.archive, self.transfers = backend, archive, transfers
        self.vid, self.pid = vid, pid
        self.rng, self.clock, self.sleep = rng, clock, sleep
        self.interval, self.wait_interval = interval, wait_interval
        self.dead_after, self.grace, self.io_timeout_ms = dead_after, grace, io_timeout_ms
        self.live = None
        self.deadline = None
        self.max_bytes = None
        self.stats = dict(sessions=0, boots=0, resumed=0, resets=0, transfers=0, timeouts=0, stalls=0, start_failures=0,
                          frames=0, records=0, drops=0, faults=0)
        self._last_start_failure = None
        self._access_noted = False

    # -- USB I/O with a durable per-transfer log
    def _log_transfer(self, direction, req, value, index, length, result, data=b""):
        self.stats["transfers"] += 1
        row = dict(**A.stamp(), dir=direction, req=req, value=value, index=index, wlength=length, result=result, n=len(data))
        if data:
            row["data_b64"] = base64.b64encode(data).decode()
        A.row(self.transfers, row)

    def _in(self, dev, req, value, index, length):
        try:
            data = dev.control_in(req, value, index, length, self.io_timeout_ms)
        except UsbError as e:
            self._log_transfer("in", req, value, index, length, type(e).__name__)
            self._count(e)
            raise
        self._log_transfer("in", req, value, index, length, "ok", data)
        return data

    def _out(self, dev, req, value, index, data):
        try:
            dev.control_out(req, value, index, data, self.io_timeout_ms)
        except UsbError as e:
            self._log_transfer("out", req, value, index, len(data), type(e).__name__, bytes(data))
            self._count(e)
            raise
        self._log_transfer("out", req, value, index, len(data), "ok", bytes(data))

    def _count(self, e):
        if isinstance(e, UsbTimeout):
            self.stats["timeouts"] += 1
        elif isinstance(e, UsbStall):
            self.stats["stalls"] += 1

    # -- frames
    def _emit(self, boot, kind, payload=b"", **extra):
        f = dict(boot_id=boot.boot_id, seq=boot.fseq, kind=kind, data_b64=base64.b64encode(payload).decode(), **extra)
        boot.fseq += 1
        self.stats["frames"] += 1
        self.archive.receive((json.dumps(f, sort_keys=True, separators=(",", ":")) + "\n").encode())

    @staticmethod
    def _json(obj):
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

    def _drop(self, boot, reason, **detail):
        self.stats["drops"] += 1
        boot.dev_next_seq = None
        self._emit(boot, "drop", self._json(dict(reason=reason, **detail)), reason=reason)

    def _record_frame(self, boot, seq, kind, payload):
        d = P.decode_record(seq, kind, payload)
        fkind = {P.K_STAGE: "stage", P.K_FAULT: "fault", P.K_DROP: "drop"}.get(kind, "log")
        extra = dict(dev_seq=seq, dev_kind=d["kind"])
        if kind == P.K_STAGE and "stage" in d:
            extra.update(stage=d["stage"], text=d["text"])
        elif kind == P.K_FAULT and "esr" in d:
            extra.update(esr=d["esr"], elr=d["elr"], far=d["far"], stage=d["stage"])
        elif kind == P.K_DROP and "count" in d:
            extra.update(count=d["count"], reason="device-reported")
        elif "text" in d:
            extra.update(text=d["text"])
        if kind == P.K_DROP:
            self.stats["drops"] += 1
        if kind == P.K_FAULT:
            self.stats["faults"] += 1
        self.stats["records"] += 1
        self._emit(boot, fkind, payload, **extra)

    # -- session lifecycle
    def _start_failed(self, reason, **detail):
        self.stats["start_failures"] += 1
        if reason != self._last_start_failure:      # one row per distinct reason, not one per retry
            self.archive.error("start-failed", detail=reason, **detail)
            self._last_start_failure = reason
        self.sleep(max(self.wait_interval, self.interval))

    def _begin_boot(self, dev, nonce, info):
        boot_id = "%s-%s" % (nonce.hex(), info["boot_id"].hex())
        boot = Boot(boot_id, nonce, info["boot_id"], info["oldest"])
        self.stats["boots"] += 1
        self._emit(boot, "boot", self._json(dict(usb=dev.info, nonce=nonce.hex(), device_boot_id=info["boot_id"].hex(),
                                                 info={k: (v.hex() if isinstance(v, bytes) else v)
                                                       for k, v in info.items()})))
        boot.last_info = info
        if info["oldest"] > 0:
            self._drop(boot, "lost-before-connect", lost_bytes=info["oldest"])
        self._last_start_failure = None
        return boot

    def _close_live(self, reason):
        boot = self.live
        if boot is None:
            return
        self.live = None
        info = boot.last_info or {}
        unread = max(0, info.get("written", boot.next_off) - boot.next_off)
        if unread:
            self.archive.error("unread-at-end", boot_id=boot.boot_id, unread_bytes=unread, end_reason=reason)
        self._emit(boot, "end", self._json(dict(reason=reason, next_offset=boot.next_off, unread_bytes=unread,
                                                last_info={k: (v.hex() if isinstance(v, bytes) else v)
                                                           for k, v in info.items()})), reason=reason)

    def _mark_gone(self):
        if self.live is not None and self.live.gone_at is None:
            self.live.gone_at = self.clock()

    def _expire_live(self):
        if self.live is not None and self.live.gone_at is not None and self.clock() - self.live.gone_at > self.grace:
            self._close_live("disconnect")

    # -- pulling
    def _is_reset(self, boot, info):
        return (not (info["flags"] & P.F_NONCE_SET) or info["nonce"] != boot.nonce or info["boot_id"] != boot.dev_boot
                or info["written"] < boot.next_off)

    def _get_info(self, dev):
        return P.parse_info(self._in(dev, P.REQ_GET_INFO, 0, 0, P.INFO_SIZE))

    def _read_once(self, dev, boot):
        """One READ_RING. -> bytes the stream position moved, or 'reset'."""
        off = boot.next_off & 0xFFFFFFFF
        raw = self._in(dev, P.REQ_READ_RING, off & 0xFFFF, off >> 16, P.READ_MAX)
        start32, _end32, payload = P.parse_ring_reply(raw)
        delta = (start32 - off) & 0xFFFFFFFF
        if delta >= 1 << 31:
            return "reset"                        # the stream went backwards: not the run we were following
        moved = 0
        if delta:
            self._drop(boot, "ring-overrun", lost_bytes=delta, at_offset=boot.next_off)
            boot.next_off += delta
            moved += delta
        recs, consumed, err = P.split_records(payload)
        for seq, kind, body in recs:
            if boot.dev_next_seq is not None and seq != boot.dev_next_seq:
                self._drop(boot, "device-seq-gap", expected=boot.dev_next_seq, received=seq)
            boot.dev_next_seq = (seq + 1) & 0xFFFFFFFF
            self._record_frame(boot, seq, kind, body)
        boot.next_off += consumed
        moved += consumed
        if err is not None:
            skipped = self._resync(payload, consumed)
            self._drop(boot, "header-crc", skipped_bytes=skipped, at_offset=boot.next_off, detail=err)
            boot.next_off += skipped
            moved += skipped
        return moved

    @staticmethod
    def _resync(payload, pos):
        """Bytes to skip from pos to the next plausible record header, always at least one."""
        for i in range(pos + 1, len(payload) - P.REC_HDR + 1):
            h = payload[i:i + P.REC_HDR]
            if P.crc8(h[:7]) == h[7] and int.from_bytes(h[4:6], "little") <= P.REC_MAX and h[6] in P.KIND_NAMES:
                return i - pos
        return max(1, len(payload) - pos - (P.REC_HDR - 1))

    def _maybe_exception(self, dev, boot, info):
        if not info["flags"] & P.F_FAULT or boot.exc_faults == info["faults"]:
            return
        raw = self._in(dev, P.REQ_GET_EXC, 0, 0, P.EXC_SIZE)
        exc = P.parse_exc(raw)
        boot.exc_faults = info["faults"]
        self.stats["faults"] += 1
        self._emit(boot, "fault", raw, source="get_exc", valid=exc["valid"], esr=exc["esr"], elr=exc["elr"], far=exc["far"],
                   spsr=exc["spsr"], sp=exc["sp"], stage=exc["stage"], count=exc["count"], x=exc["x"])

    def _pump(self, dev, boot, info):
        """Serve one device connection. -> 'gone' | 'reset' | 'unresponsive' | 'deadline' | 'size-limit'."""
        last_ok = self.clock()
        while True:
            if self.clock() >= self.deadline:
                return "deadline"
            if self.archive.offset >= self.max_bytes:
                return "size-limit"
            try:
                if info is None:
                    info = self._get_info(dev)
            except UsbGone:
                return "gone"
            except (UsbTimeout, UsbStall, ValueError) as e:
                if self.clock() - last_ok > self.dead_after:
                    return "unresponsive"
                self.sleep(self.interval)
                continue
            last_ok = self.clock()
            boot.last_info = info
            if self._is_reset(boot, info):
                return "reset"
            progress = 0
            try:
                for _ in range(MAX_READS_PER_CYCLE):
                    if boot.next_off >= info["written"]:
                        break
                    moved = self._read_once(dev, boot)
                    if moved == "reset":
                        return "reset"
                    boot.read_failures = 0
                    if not moved:
                        break
                    progress += moved
                self._maybe_exception(dev, boot, info)
            except UsbGone:
                return "gone"
            except (UsbTimeout, UsbStall, ValueError):
                boot.read_failures += 1
                if boot.read_failures > MAX_READ_FAILURES:
                    return "unresponsive"
            info = None
            if not progress:
                self.sleep(self.interval)

    def _serve(self, dev):
        self.stats["sessions"] += 1
        try:
            info = self._get_info(dev)
            live = self.live
            if (live is not None and info["flags"] & P.F_NONCE_SET and info["nonce"] == live.nonce
                    and info["boot_id"] == live.dev_boot and info["written"] >= live.next_off):
                live.gone_at = None
                self.stats["resumed"] += 1
                boot = live                       # the same run, a USB re-enumeration in between
            else:
                if live is not None:
                    self._close_live("disconnect")
                nonce = self.rng(P.NONCE_LEN)
                self._out(dev, P.REQ_SET_NONCE, 0, 0, nonce)
                info = self._get_info(dev)
                if not info["flags"] & P.F_NONCE_SET or info["nonce"] != nonce:
                    self._start_failed("nonce-not-echoed")
                    return "start-failed"
                boot = self._begin_boot(dev, nonce, info)
                self.live = boot
        except UsbGone:
            self._mark_gone()
            return "gone"
        except UsbAccess as e:
            self._mark_gone()
            if not self._access_noted:
                self._access_noted = True
                self.archive.error("device-access-denied", detail=str(e))
            self.sleep(1.0)
            return "access"
        except (UsbTimeout, UsbStall, ValueError) as e:
            self._mark_gone()
            self._start_failed("%s: %s" % (type(e).__name__, e))
            return "start-failed"
        why = self._pump(dev, boot, info)
        if why == "gone":
            self._mark_gone()
        elif why in ("reset", "unresponsive"):
            if why == "reset":
                self.stats["resets"] += 1
            self._close_live("reset-detected" if why == "reset" else "unresponsive")
        return why

    def _drain(self):
        """Last catch-up pull before the collector stops."""
        boot = self.live
        if boot is None or boot.gone_at is not None:
            return
        # find the device again: a fresh handle is cheaper than keeping one across the loop
        for dev in self.backend.find(self.vid, self.pid)[:1]:
            try:
                info = self._get_info(dev)
                if self._is_reset(boot, info):
                    return
                boot.last_info = info
                for _ in range(MAX_READS_PER_CYCLE):
                    if boot.next_off >= info["written"]:
                        break
                    moved = self._read_once(dev, boot)
                    if moved == "reset" or not moved:
                        break
                self._maybe_exception(dev, boot, info)
            except (UsbError, ValueError):
                pass
            finally:
                dev.close()

    def run(self, seconds, max_bytes):
        if not 0 < seconds <= 6 * 3600 or not 0 < max_bytes <= 1024 ** 3:
            raise ValueError("invalid time/size bound")
        self.deadline = self.clock() + seconds
        self.max_bytes = max_bytes
        stop = "deadline"
        try:
            while True:
                if self.clock() >= self.deadline:
                    stop = "deadline"
                    break
                if self.archive.offset >= self.max_bytes:
                    stop = "size-limit"
                    break
                self._expire_live()
                try:
                    devs = self.backend.find(self.vid, self.pid)
                except UsbError as e:
                    self.archive.error("usb-backend", detail=str(e))
                    stop = "backend-error"
                    break
                if not devs:
                    self.sleep(self.wait_interval)
                    continue
                if len(devs) > 1 and self.stats["sessions"] == 0:
                    self.archive.error("multiple-devices", count=len(devs))
                dev = devs[0]
                try:
                    self._serve(dev)
                finally:
                    dev.close()
        except KeyboardInterrupt:
            stop = "interrupted"
        if stop in ("deadline", "interrupted"):
            self._drain()
        self._close_live("collector-stop" if self.live is not None and self.live.gone_at is None else "disconnect")
        return stop


def finish_archive(archive, stop, stats, out):
    """Seal the archive. NAT-016's finish() records every stop reason except 'eof' as a capture error, which would make
    every deliberate end of an unattended run 'incomplete'. A deadline or interrupt that ended the run after the collector
    had drained the device and closed every boot is the end of the stream the collector chose to read, so it is passed as
    'eof'; the real reason stays in the events log and collector-summary.json. Anything else (size limit, backend error)
    keeps its own name and therefore stays an error."""
    deliberate = stop in ("deadline", "interrupted")
    A.row(archive.events, dict(**A.stamp(), kind="collector-note", reason=stop, deliberate=deliberate))
    A.seal_json(out / "collector-summary.json", dict(stop=stop, stats=stats, tool="s24_logd"))
    return archive.finish("eof" if deliberate else stop)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True, help="new attempt directory (must not exist)")
    p.add_argument("--channel", default="ep0-monitor")
    p.add_argument("--provenance", choices=["synthetic", "unqualified-live"], required=True)
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--max-bytes", type=int, default=32 * 1024 * 1024)
    p.add_argument("--interval", type=float, default=0.02, help="idle poll interval in seconds")
    p.add_argument("--dead-after", type=float, default=30.0, help="seconds without any answer before a boot is ended")
    p.add_argument("--grace", type=float, default=10.0, help="seconds a vanished device may come back as the same run")
    a = p.parse_args()
    archive = A.Archive(a.out, a.channel, a.provenance)
    transfers = A.create(a.out / "usb-transfers.jsonl")
    summary = {}
    try:
        col = Collector(PyUsbBackend(), archive, transfers, interval=a.interval, dead_after=a.dead_after, grace=a.grace)
        stop = col.run(a.seconds, a.max_bytes)
        summary = dict(col.stats)
    except UsbError as e:
        archive.error("usb-backend", detail=str(e))
        stop = "backend-error"
    finally:
        transfers.close()
    result = finish_archive(archive, stop, summary, a.out)
    print(json.dumps(result, indent=2))
    return 0 if result["outcome"] == "complete-received-stream" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as e:
        print("s24_logd: %s" % e, file=sys.stderr)
        sys.exit(2)
