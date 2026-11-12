#!/usr/bin/env python3
"""Send a file to the S24 loader's bulk-OUT receive engine (NAT-076), by offset, in checked chunks, resumable.

Evidence kind of this tool today: host-test (tests/test_root_send.py runs it against the NAT-076 DWC3 model). It has not
talked to a phone. The device side is docs/procedures/nat-076/engine/usbmon.c; the wire protocol is described at the top of
docs/procedures/nat-076/engine/usbmon.h and repeated here as constants:

  0x40 / 0x06 RX_BEGIN  data = <u64 offset, u32 length, u32 flags=0>: arm one bulk-OUT transfer at the committed offset
  0xC0 / 0x07 GET_RX    -> struct usbmon_rx (120 bytes): state, committed offset, counters, checksum of the last chunk
  0x40 / 0x08 RX_ABORT  end an armed transfer; nothing is committed
  bulk OUT endpoint 0x01 (512-byte packets): exactly `length` bytes after RX_BEGIN

Contract of this sender:
  * the file size must be a multiple of 16 KiB (the root image is built in 16 KiB units; a size that is not one is refused
    before anything is sent);
  * every bulk write is at most `write_size` bytes; a chunk (one RX_BEGIN + its writes) is at most `chunk` bytes and never
    more than the device's own chunk limit;
  * after each chunk the device's committed offset, state and checksum of the chunk are compared with what was sent; a chunk
    that the device committed with a wrong checksum is fatal (the device cannot rewind), anything else that goes wrong is
    retried from the device-reported committed offset, at most `max_retries` times per chunk;
  * the byte count that the DEVICE reports (committed offset) is what is printed at the end, never the host's own count.
"""
import argparse
import struct
import sys
import time

REQ_RX_BEGIN = 0x06
REQ_GET_RX = 0x07
REQ_RX_ABORT = 0x08
VENDOR_OUT = 0x40
VENDOR_IN = 0xC0
BULK_EP_OUT = 0x01
VID, PID = 0x1209, 0x0001

RX_IDLE, RX_ARMED, RX_FAILED = 0, 1, 2
RXF_PRESENT, RXF_ENABLED, RXF_DIRECT = 1, 2, 4
RX_FORMAT = "<4sHHIIQQIIQQIIIIIIIIIIIIQQ"
RX_SIZE = struct.calcsize(RX_FORMAT)
assert RX_SIZE == 120
RX_FIELDS = ("magic", "version", "size", "state", "flags", "committed", "armed_off", "armed_len", "chunk_max", "capacity",
             "rx_bytes", "rx_trbs", "rx_errors", "rx_dups", "rx_gaps", "rx_rejects", "rx_resets", "rx_aborts",
             "last_trb_status", "last_residual", "last_evt_status", "last_len", "pad", "last_off", "last_sum")
assert len(RX_FIELDS) == len(struct.unpack(RX_FORMAT, bytes(RX_SIZE)))

UNIT = 16 * 1024		# the root image is built in 16 KiB units
MPS = 512			# bulk packet size at high speed
MASK64 = (1 << 64) - 1


class RootSendError(Exception):
    pass


class SizeError(RootSendError):
    pass


class DeviceStateError(RootSendError):
    pass


class DeliveryError(RootSendError):
    pass


class TransportError(Exception):
    """Raised by a transport for a stall, a timeout, a short write or a lost device."""


def parse_rx(data):
    if len(data) < RX_SIZE:
        raise DeviceStateError("GET_RX returned %d bytes, expected %d" % (len(data), RX_SIZE))
    r = dict(zip(RX_FIELDS, struct.unpack(RX_FORMAT, bytes(data[:RX_SIZE]))))
    if r["magic"] != b"S24R" or r["version"] != 1 or r["size"] != RX_SIZE:
        raise DeviceStateError("GET_RX reply is not a version 1 usbmon_rx (magic %r version %d size %d)"
                               % (r["magic"], r["version"], r["size"]))
    return r


def chunk_sum(data):
    """sum over little-endian 64-bit words w[i] of w[i] * (2*i + 1), modulo 2**64 (usbmon_rx_sum_step on the device)."""
    n = len(data)
    if n % 8:
        raise ValueError("checksum input must be a multiple of 8 bytes")
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        w = np.frombuffer(bytes(data), dtype="<u8")
        idx = np.arange(w.size, dtype=np.uint64)
        return int((w * (idx * np.uint64(2) + np.uint64(1))).sum(dtype=np.uint64))
    words = struct.unpack("<%dQ" % (n // 8), bytes(data))
    return sum(w * (2 * i + 1) for i, w in enumerate(words)) & MASK64


def check_size(size):
    if size <= 0 or size % UNIT:
        raise SizeError("size %d is not a positive multiple of 16 KiB (%d); refusing to send" % (size, UNIT))


class Transport:
    """What the sender needs from a USB connection. Every method raises TransportError on failure."""

    def rx_begin(self, offset, length):
        raise NotImplementedError

    def rx_abort(self):
        raise NotImplementedError

    def get_rx(self):
        raise NotImplementedError

    def bulk_write(self, data):
        """-> number of bytes the device took (== len(data) on success)"""
        raise NotImplementedError

    def reconnect(self):
        """Called after a TransportError when the connection may be gone; a no-op where there is nothing to do."""


class PyUsbTransport(Transport):
    """The real device through pyusb/libusb. Not exercised by the host tests (they use the model's transport)."""

    def __init__(self, vid=VID, pid=PID, bus=None, address=None, timeout_ms=5000, configure=True):
        import usb.core
        self.usb = usb.core
        self.vid, self.pid, self.bus, self.address = vid, pid, bus, address
        self.timeout_ms = timeout_ms
        self.configure = configure
        self.dev = None
        self._open()

    def _open(self):
        devs = [d for d in self.usb.find(find_all=True, idVendor=self.vid, idProduct=self.pid)
                if (self.bus is None or d.bus == self.bus) and (self.address is None or d.address == self.address)]
        if not devs:
            raise TransportError("no USB device %04x:%04x" % (self.vid, self.pid))
        if len(devs) > 1:
            raise TransportError("%d devices match %04x:%04x; pass --bus/--address" % (len(devs), self.vid, self.pid))
        self.dev = devs[0]
        if self.configure:
            self.dev.set_configuration(1)	# the engine enables the bulk endpoint at SET_CONFIGURATION(1)

    def _wrap(self, fn, *a):
        try:
            return fn(*a)
        except Exception as e:  # usb.core.USBError, USBTimeoutError, ...
            raise TransportError("%s: %s" % (type(e).__name__, e))

    def rx_begin(self, offset, length):
        self._wrap(self.dev.ctrl_transfer, VENDOR_OUT, REQ_RX_BEGIN, 0, 0, struct.pack("<QII", offset, length, 0),
                   self.timeout_ms)

    def rx_abort(self):
        self._wrap(self.dev.ctrl_transfer, VENDOR_OUT, REQ_RX_ABORT, 0, 0, None, self.timeout_ms)

    def get_rx(self):
        return bytes(self._wrap(self.dev.ctrl_transfer, VENDOR_IN, REQ_GET_RX, 0, 0, RX_SIZE, self.timeout_ms))

    def bulk_write(self, data):
        return int(self._wrap(self.dev.write, BULK_EP_OUT, bytes(data), self.timeout_ms))

    def reconnect(self):
        """Reset the port (the device then drops its configuration and re-enumerates), find it again, configure it again."""
        try:
            self.dev.reset()
        except Exception:
            pass			# the handle may already be dead; _open() finds the device again
        self.address = None		# a re-enumerated device has a new address; the bus filter (if any) stays
        for _ in range(20):
            try:
                self._open()
                return
            except TransportError:
                time.sleep(0.25)
        raise TransportError("the device did not come back after a port reset")


def _read_after_failure(transport, log):
    """GET_RX after a failure. A device that cannot be reached, or whose receive path is no longer enabled (a bus reset drops
    the configuration), is reconnected once; if it is still not usable the delivery has failed."""
    reconnected = False
    while True:
        try:
            rx = parse_rx(transport.get_rx())
            if rx["flags"] & RXF_ENABLED:
                return rx
            why = "the receive path is not enabled (flags %#x)" % rx["flags"]
        except TransportError as e:
            why = "GET_RX failed: %s" % e
        if reconnected:
            raise DeliveryError("device unusable after a reconnect: %s" % why)
        log("reconnecting: %s" % why)
        try:
            transport.reconnect()
        except TransportError as e:
            raise DeliveryError("could not reconnect: %s" % e)
        reconnected = True


def _abort_armed(transport):
    """End an armed transfer (nothing of it is committed) and return the device's view afterwards."""
    transport.rx_abort()
    rx = parse_rx(transport.get_rx())
    if rx["state"] == RX_ARMED:
        raise TransportError("the transfer is still armed after RX_ABORT")
    return rx


def send(transport, data, base=0, chunk=256 * 1024, write_size=64 * 1024, max_retries=5, resume=True, poll_limit=2000,
         backoff=0.05, log=None, clock=None, sleep=None):
    """Send `data` (bytes) to device offset `base`..`base+len(data)`. -> summary dict (the device's own numbers)."""
    log = log or (lambda msg: None)
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    size = len(data)
    check_size(size)
    if base < 0 or base % UNIT:
        raise SizeError("base offset %d is not a multiple of 16 KiB" % base)
    if chunk <= 0 or chunk % MPS or write_size <= 0 or write_size % MPS:
        raise SizeError("chunk and write size must be positive multiples of %d" % MPS)
    end = base + size
    start = clock()

    try:
        rx = parse_rx(transport.get_rx())
    except TransportError as e:
        raise DeviceStateError("the device does not answer GET_RX (no receive engine, or not configured): %s" % e)
    if not (rx["flags"] & RXF_PRESENT) or not (rx["flags"] & RXF_ENABLED):
        raise DeviceStateError("the device's bulk-OUT receive path is not enabled (flags %#x)" % rx["flags"])
    if end > rx["capacity"]:
        raise DeviceStateError("file ends at %d, past the device's destination of %d bytes" % (end, rx["capacity"]))
    if rx["state"] == RX_ARMED:		# a transfer left armed by an earlier run: end it, nothing of it is committed
        try:
            rx = _abort_armed(transport)
        except TransportError as e:
            raise DeviceStateError("could not end the transfer a previous run left armed: %s" % e)
    chunk = min(chunk, rx["chunk_max"])
    off = rx["committed"]
    if off != base and not (resume and base <= off <= end):
        raise DeviceStateError("device committed offset %d is outside the file range %d..%d" % (off, base, end))
    log("start: device committed %d, sending %d..%d in chunks of %d" % (off, base, end, chunk))
    floor = resumed_from = off		# the device must never go back below what it already committed
    sent_bytes = retries = chunks = 0

    while off < end:
        n = min(chunk, end - off)
        piece = bytes(data[off - base:off - base + n])
        want_sum = chunk_sum(piece)
        attempt = 0
        while True:
            try:
                transport.rx_begin(off, n)
                for w in range(0, n, write_size):
                    part = piece[w:w + write_size]
                    took = transport.bulk_write(part)
                    if took != len(part):
                        raise TransportError("short bulk write: device took %d of %d bytes" % (took, len(part)))
                    sent_bytes += took
                rx = None
                for _ in range(poll_limit):
                    rx = parse_rx(transport.get_rx())
                    if rx["state"] != RX_ARMED:
                        break
                else:
                    raise TransportError("the chunk at %d stayed armed after %d polls" % (off, poll_limit))
                if rx["state"] == RX_FAILED or rx["committed"] != off + n:
                    raise TransportError("device reports state %d committed %d after the chunk at %d (expected %d)"
                                         % (rx["state"], rx["committed"], off, off + n))
                if rx["last_off"] != off or rx["last_len"] != n or rx["last_sum"] != want_sum:
                    raise DeliveryError("chunk at %d was committed with a different checksum (device %#x host %#x) or "
                                        "position (last_off %d last_len %d): the data in the device is wrong"
                                        % (off, rx["last_sum"], want_sum, rx["last_off"], rx["last_len"]))
                break
            except TransportError as e:
                attempt += 1
                retries += 1
                log("chunk at %d failed (%s); attempt %d of %d" % (off, e, attempt, max_retries))
                if attempt > max_retries:
                    raise DeliveryError("chunk at %d failed %d times: %s" % (off, attempt, e))
                sleep(backoff * attempt)	# the device refuses a new RX_BEGIN until its ENDTRANSFER has completed
                # recover from what the device says it holds
                rx = _read_after_failure(transport, log)
                if rx["state"] == RX_ARMED:
                    try:
                        rx = _abort_armed(transport)
                    except TransportError as e2:
                        raise DeliveryError("could not abort the armed transfer at %d: %s" % (off, e2))
                if rx["committed"] < floor:
                    raise DeviceStateError("device committed offset went back from %d to %d: it restarted" % (floor, rx["committed"]))
                if rx["committed"] == off + n and rx["last_off"] == off and rx["last_len"] == n and rx["last_sum"] == want_sum:
                    break			# the chunk did arrive; only the host's view of it failed
                if rx["committed"] != off:
                    raise DeviceStateError("device committed %d while the host was at %d: the stream is out of step"
                                           % (rx["committed"], off))
        off += n
        floor = off
        chunks += 1
    try:
        rx = parse_rx(transport.get_rx())
    except TransportError as e:
        raise DeliveryError("the device did not answer the final GET_RX: %s" % e)
    if rx["committed"] != end:
        raise DeliveryError("device reports committed %d, expected %d" % (rx["committed"], end))
    return {"committed": rx["committed"], "rx_bytes": rx["rx_bytes"], "rx_trbs": rx["rx_trbs"], "rx_errors": rx["rx_errors"],
            "chunks": chunks, "retries": retries, "bytes_written": sent_bytes, "seconds": clock() - start,
            "start_offset": base, "end_offset": end, "resumed_from": resumed_from}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--base", type=int, default=0, help="device offset of the first byte (multiple of 16 KiB)")
    ap.add_argument("--chunk", type=int, default=256 * 1024)
    ap.add_argument("--write-size", type=int, default=64 * 1024)
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--vid", type=lambda s: int(s, 0), default=VID)
    ap.add_argument("--pid", type=lambda s: int(s, 0), default=PID)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--address", type=int)
    ap.add_argument("--timeout-ms", type=int, default=5000)
    ap.add_argument("--no-resume", action="store_true", help="refuse a device whose committed offset is not --base")
    ap.add_argument("--check-only", action="store_true", help="validate the file size and exit without opening the device")
    a = ap.parse_args(argv)
    with open(a.file, "rb") as f:
        data = f.read()
    try:
        check_size(len(data))
    except SizeError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    if a.check_only:
        print("size %d is a multiple of 16 KiB" % len(data))
        return 0
    try:
        t = PyUsbTransport(a.vid, a.pid, a.bus, a.address, a.timeout_ms)
        r = send(t, data, base=a.base, chunk=a.chunk, write_size=a.write_size, max_retries=a.max_retries,
                 resume=not a.no_resume, log=lambda m: print(m, file=sys.stderr))
    except RootSendError as e:
        print("failed: %s" % e, file=sys.stderr)
        return 1
    except TransportError as e:
        print("failed: %s" % e, file=sys.stderr)
        return 1
    print("device reports committed=%d rx_bytes=%d rx_trbs=%d rx_errors=%d (host: %d chunks, %d retries, %d bytes written, %.3f s)"
          % (r["committed"], r["rx_bytes"], r["rx_trbs"], r["rx_errors"], r["chunks"], r["retries"], r["bytes_written"],
             r["seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
