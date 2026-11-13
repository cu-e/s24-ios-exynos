#!/usr/bin/env python3
"""NAT-130 sender: tools/ios/root_send.py (unchanged, loaded from its file) plus checksum modes, calibration, post-verification
and per-chunk phase timing for the NAT-130 engine (docs/procedures/nat-130/engine).

Evidence kind: host-test (test_sender130.py drives it against the NAT-130 model). It has not talked to a phone.

What it adds to root_send.send():
  * each chunk's RX_BEGIN carries a checksum mode in its flags (0 PLAIN, 1 FAST, 2 CACHED, 3 NONE);
  * policy "auto": chunk 0 is committed PLAIN (the NAT-078/NAT-127 baseline), then the device sums chunk 0 again with every
    calibration mode through the SUM request (each result must equal the host's sum, else that mode is not used), chunks
    1..none_chunks are committed NONE (the wire alone), the rest with the fastest mode that passed; at the end every NONE chunk
    is summed by the device (SUM) and compared with the host's sum. A NONE chunk that does not verify is fatal, as a wrong
    committed chunk is in root_send (the device cannot rewind). Policy "plain" is root_send's behaviour;
  * a record per chunk: host phase times (RX_BEGIN, bulk write, commit poll) and, with per_chunk_rxt, the device's own phase
    ticks from GET_RXT.
The byte count printed or returned is what the DEVICE reports, as in root_send.
"""
import importlib.util
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
_spec = importlib.util.spec_from_file_location("root_send_v1", os.path.join(ROOT, "tools", "ios", "root_send.py"))
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)

# everything the NAT-080 delivery companion uses from root_send, re-exported unchanged
for _name in ("REQ_RX_BEGIN", "REQ_GET_RX", "REQ_RX_ABORT", "VENDOR_OUT", "VENDOR_IN", "BULK_EP_OUT", "VID", "PID", "RX_IDLE",
              "RX_ARMED", "RX_FAILED", "RXF_PRESENT", "RXF_ENABLED", "RXF_DIRECT", "RX_FORMAT", "RX_SIZE", "RX_FIELDS", "UNIT", "MPS",
              "RootSendError", "SizeError", "DeviceStateError", "DeliveryError", "TransportError", "parse_rx", "chunk_sum",
              "check_size", "Transport"):
    globals()[_name] = getattr(rs, _name)

REQ_GET_RXT = 0x09
REQ_SUM = 0x0A
PLAIN, FAST, CACHED, NONE = 0, 1, 2, 3
MODE_NAMES = {PLAIN: "plain", FAST: "fast", CACHED: "cached", NONE: "none"}
SREQ_OK = 1
RXT_FORMAT = "<4sHHQQII4Q4QIIQIIQQIIII"
RXT_SIZE = struct.calcsize(RXT_FORMAT)
assert RXT_SIZE == 152
RXT_FIELDS = ("magic", "version", "size", "now", "freq", "caps", "last_mode", "t_arm0", "t_arm1", "t_done", "t_sum1", "tot_arm",
              "tot_wire", "tot_sum", "tot_gap", "chunks", "unsummed", "sreq_off", "sreq_len", "sreq_mode", "sreq_sum", "sreq_ticks",
              "sreq_count", "sreq_status", "sreq_refused", "sum_fallbacks")
assert len(RXT_FIELDS) == len(struct.unpack(RXT_FORMAT, bytes(RXT_SIZE)))


def parse_rxt(data):
    if len(data) < RXT_SIZE:
        raise DeviceStateError("GET_RXT returned %d bytes, expected %d" % (len(data), RXT_SIZE))
    r = dict(zip(RXT_FIELDS, struct.unpack(RXT_FORMAT, bytes(data[:RXT_SIZE]))))
    if r["magic"] != b"S24T" or r["version"] != 1 or r["size"] != RXT_SIZE:
        raise DeviceStateError("GET_RXT reply is not a version 1 usbmon_rxt (magic %r version %d size %d)"
                               % (r["magic"], r["version"], r["size"]))
    return r


class PyUsbTransport130(rs.PyUsbTransport):
    """root_send's pyusb transport with the NAT-130 requests. sum_timeout_ms bounds one SUM (a PLAIN sum of 8 MiB took about
    0.3 s per chunk in NAT-127's numbers; the default leaves a wide margin)."""

    sum_timeout_ms = 20000

    def rx_begin(self, offset, length, flags=0):
        self._wrap(self.dev.ctrl_transfer, VENDOR_OUT, REQ_RX_BEGIN, 0, 0, struct.pack("<QII", offset, length, flags),
                   self.timeout_ms)

    def get_rxt(self):
        return bytes(self._wrap(self.dev.ctrl_transfer, VENDOR_IN, REQ_GET_RXT, 0, 0, RXT_SIZE, self.timeout_ms))

    def sum_req(self, offset, length, mode):
        self._wrap(self.dev.ctrl_transfer, VENDOR_OUT, REQ_SUM, 0, 0, struct.pack("<QII", offset, length, mode),
                   max(self.timeout_ms, self.sum_timeout_ms))


PyUsbTransport = PyUsbTransport130


class SumCache:
    """Host checksums of the chunks, computed by a background thread in stream order (NAT-127's sender spent 0.12 s per 8 MiB chunk
    on its own pure-Python sum, in series with the transfer; the venv that has pyusb has no numpy). get() waits for the thread or,
    if the thread has not reached that chunk, computes the sum itself."""

    def __init__(self, data, base, chunk, start=True):
        import threading
        self.data, self.base, self.chunk = data, base, chunk
        self.done = {}
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="sumcache", daemon=True)
        self.stats = dict(hits=0, misses=0)
        if start:
            self.thread.start()

    def _run(self):
        for off in range(self.base, self.base + len(self.data), self.chunk):
            piece = self.data[off - self.base:off - self.base + self.chunk]
            v = chunk_sum(piece)
            with self.lock:
                self.done[(off, len(piece))] = v

    def get(self, off, piece):
        with self.lock:
            v = self.done.get((off, len(piece)))
        if v is not None:
            self.stats["hits"] += 1
            return v
        self.stats["misses"] += 1
        return chunk_sum(piece)


def _device_sum(transport, off, n, mode, clock):
    """-> (sum or None, device ticks or None, host seconds, error text or None)"""
    t = clock()
    try:
        transport.sum_req(off, n, mode)
        r = parse_rxt(transport.get_rxt())
    except (TransportError, RootSendError) as e:
        return None, None, clock() - t, "%s: %s" % (type(e).__name__, e)
    host = clock() - t
    if r["sreq_status"] != SREQ_OK or (r["sreq_off"], r["sreq_len"], r["sreq_mode"]) != (off, n, mode):
        return None, None, host, "device reports status %d for %s" % (r["sreq_status"], (r["sreq_off"], r["sreq_len"], r["sreq_mode"]))
    return r["sreq_sum"], r["sreq_ticks"], host, None


def calibrate(transport, piece, off, modes, log, clock):
    """Sum the committed chunk at `off` again with each mode. -> {mode: dict(ok, ticks, host_s, error)}"""
    want = chunk_sum(piece)
    out = {}
    for mode in modes:
        s, ticks, host, err = _device_sum(transport, off, len(piece), mode, clock)
        ok = err is None and s == want
        if err is None and s != want:
            err = "sum %#x, host %#x" % (s, want)
        out[mode] = dict(ok=ok, ticks=ticks, host_s=round(host, 6), error=err)
        log("calibrate %s: %s" % (MODE_NAMES.get(mode, mode), out[mode]))
    return out


def choose(cal, freq=None):
    """The fastest mode that verified (by device ticks, then host time); PLAIN if none did."""
    good = [(c["ticks"] if c["ticks"] is not None else 1 << 62, c["host_s"], m) for m, c in cal.items() if c["ok"]]
    return min(good)[2] if good else PLAIN


def _post_verify(transport, unsummed, best, verify, verified, clock, log):
    """Sum each chunk committed without a sum (mode NONE) on the device and compare with the host's sum; fatal if it differs."""
    for (voff, vn, vsum) in unsummed:
        s, ticks, host, err = _device_sum(transport, voff, vn, best, clock)
        verify.append(dict(off=voff, n=vn, mode=best, ok=err is None and s == vsum, ticks=ticks, host_s=round(host, 6), error=err))
        if err is not None and best != PLAIN:		# the chosen mode failed now: one more try with PLAIN before giving up
            s, ticks, host, err = _device_sum(transport, voff, vn, PLAIN, clock)
            verify.append(dict(off=voff, n=vn, mode=PLAIN, ok=err is None and s == vsum, ticks=ticks, host_s=round(host, 6), error=err))
        if err is not None:
            raise DeliveryError("chunk at %d (committed without a sum) could not be verified: %s" % (voff, err))
        if s != vsum:
            raise DeliveryError("chunk at %d (committed without a sum) holds wrong data: device %#x host %#x" % (voff, s, vsum))
        verified.add(voff)
        log("verified chunk at %d (%s)" % (voff, MODE_NAMES[verify[-1]["mode"]]))


def send(transport, data, base=0, chunk=8 * 1024 * 1024, write_size=8 * 1024 * 1024, max_retries=5, resume=True, poll_limit=2000,
         backoff=0.05, log=None, clock=None, sleep=None, policy="auto", calib_modes=(PLAIN, FAST, CACHED), none_chunks=4,
         per_chunk_rxt=True, sums=None):
    """root_send.send() with checksum modes (see the module text). -> summary dict (device numbers + per-chunk records)."""
    log = log or (lambda msg: None)
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    if policy not in ("auto", "plain", "fast", "cached"):
        raise ValueError("policy %r" % policy)
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
    try:
        rxt0 = parse_rxt(transport.get_rxt())
        caps = rxt0["caps"]
    except (TransportError, RootSendError) as e:
        if policy != "plain":
            raise DeviceStateError("the device does not answer GET_RXT (not a NAT-130 engine?): %s" % e)
        rxt0, caps = None, 1
    if not rx["flags"] & RXF_DIRECT:
        caps &= 1
    if rx["state"] == RX_ARMED:
        try:
            transport.rx_abort()
            rx = parse_rx(transport.get_rx())
        except TransportError as e:
            raise DeviceStateError("could not end the transfer a previous run left armed: %s" % e)
        if rx["state"] == RX_ARMED:
            raise DeviceStateError("the transfer is still armed after RX_ABORT")
    chunk = min(chunk, rx["chunk_max"])
    off = rx["committed"]
    if off != base and not (resume and base <= off <= end):
        raise DeviceStateError("device committed offset %d is outside the file range %d..%d" % (off, base, end))
    fixed = {"plain": PLAIN, "fast": FAST, "cached": CACHED}.get(policy)
    if fixed is not None and not (caps >> fixed) & 1:
        raise DeviceStateError("the device does not offer checksum mode %s (caps %#x)" % (policy, caps))
    calib_modes = tuple(m for m in calib_modes if (caps >> m) & 1)
    total_chunks = -(-(end - off) // chunk) if off < end else 0
    # NONE chunks are 1..last_none and at least one summed chunk follows them: their post-verification runs right after the
    # last of them, while the loader is still in its receive loop (the loader leaves that loop when the final chunk commits)
    last_none = min(none_chunks, total_chunks - 2) if policy == "auto" and (caps >> NONE) & 1 else 0
    use_none = last_none >= 1
    log("start: device committed %d, sending %d..%d in chunks of %d, policy %s, caps %#x" % (off, base, end, chunk, policy, caps))
    floor = resumed_from = off
    sent_bytes = retries = chunks = 0
    best = fixed if fixed is not None else PLAIN
    cal = None
    records, unsummed, verify, verified = [], [], [], set()
    index = 0

    while off < end:
        n = min(chunk, end - off)
        piece = bytes(data[off - base:off - base + n])
        t_s = clock()
        want_sum = sums.get(off, piece) if sums is not None else chunk_sum(piece)
        host_sum_s = clock() - t_s
        if policy == "auto" and index == 0:
            mode = PLAIN
        elif use_none and 1 <= index <= last_none:
            mode = NONE
        else:
            mode = best
        expect = 0 if mode == NONE else want_sum
        attempt = 0
        rec = dict(index=index, off=off, n=n, mode=mode, host_sum_s=round(host_sum_s, 6))
        while True:
            try:
                t_a = clock()
                transport.rx_begin(off, n, mode)
                t_b = clock()
                for w in range(0, n, write_size):
                    part = piece[w:w + write_size]
                    took = transport.bulk_write(part)
                    if took != len(part):
                        raise TransportError("short bulk write: device took %d of %d bytes" % (took, len(part)))
                    sent_bytes += took
                t_c = clock()
                rx = None
                for _ in range(poll_limit):
                    rx = parse_rx(transport.get_rx())
                    if rx["state"] != RX_ARMED:
                        break
                else:
                    raise TransportError("the chunk at %d stayed armed after %d polls" % (off, poll_limit))
                t_d = clock()
                if rx["state"] == RX_FAILED or rx["committed"] != off + n:
                    raise TransportError("device reports state %d committed %d after the chunk at %d (expected %d)"
                                         % (rx["state"], rx["committed"], off, off + n))
                if rx["last_off"] != off or rx["last_len"] != n or rx["last_sum"] != expect:
                    raise DeliveryError("chunk at %d was committed with a different checksum (device %#x host %#x, mode %s) or "
                                        "position (last_off %d last_len %d): the data in the device is wrong"
                                        % (off, rx["last_sum"], expect, MODE_NAMES[mode], rx["last_off"], rx["last_len"]))
                rec.update(begin_s=round(t_b - t_a, 6), write_s=round(t_c - t_b, 6), poll_s=round(t_d - t_c, 6),
                           at_s=round(t_a - start, 6))
                break
            except TransportError as e:
                attempt += 1
                retries += 1
                log("chunk at %d failed (%s); attempt %d of %d" % (off, e, attempt, max_retries))
                if attempt > max_retries:
                    raise DeliveryError("chunk at %d failed %d times: %s" % (off, attempt, e))
                sleep(backoff * attempt)
                rx = rs._read_after_failure(transport, log)
                if rx["state"] == RX_ARMED:
                    try:
                        rx = rs._abort_armed(transport)
                    except TransportError as e2:
                        raise DeliveryError("could not abort the armed transfer at %d: %s" % (off, e2))
                if rx["committed"] < floor:
                    raise DeviceStateError("device committed offset went back from %d to %d: it restarted" % (floor, rx["committed"]))
                if rx["committed"] == off + n and rx["last_off"] == off and rx["last_len"] == n and rx["last_sum"] == expect:
                    rec.update(recovered=True, at_s=round(clock() - start, 6))
                    break
                if rx["committed"] != off:
                    raise DeviceStateError("device committed %d while the host was at %d: the stream is out of step"
                                           % (rx["committed"], off))
        rec["attempts"] = attempt + 1
        if per_chunk_rxt:
            try:
                t = parse_rxt(transport.get_rxt())
                rec["dev"] = {k: t[k] for k in ("t_arm0", "t_arm1", "t_done", "t_sum1", "last_mode")}
            except (TransportError, RootSendError) as e:
                rec["dev_error"] = str(e)
        if mode == NONE:
            unsummed.append((off, n, want_sum))
        records.append(rec)
        if policy == "auto" and index == 0 and calib_modes:
            cal = calibrate(transport, piece, off, calib_modes, log, clock)
            best = choose(cal)
            log("chosen checksum mode: %s" % MODE_NAMES[best])
        if use_none and index == last_none:
            _post_verify(transport, [u for u in unsummed if u[0] not in verified], best, verify, verified, clock, log)
        off += n
        floor = off
        chunks += 1
        index += 1

    pending = [u for u in unsummed if u[0] not in verified]
    if pending:			# not reached inside the loop (cannot happen with last_none <= total - 2; kept as a guard)
        _post_verify(transport, pending, best, verify, verified, clock, log)
    try:
        rx = parse_rx(transport.get_rx())
    except TransportError as e:
        raise DeliveryError("the device did not answer the final GET_RX: %s" % e)
    if rx["committed"] != end:
        raise DeliveryError("device reports committed %d, expected %d" % (rx["committed"], end))
    try:
        rxt = parse_rxt(transport.get_rxt())
    except (TransportError, RootSendError) as e:
        rxt = dict(error=str(e))
    return {"committed": rx["committed"], "rx_bytes": rx["rx_bytes"], "rx_trbs": rx["rx_trbs"], "rx_errors": rx["rx_errors"],
            "chunks": chunks, "retries": retries, "bytes_written": sent_bytes, "seconds": clock() - start,
            "start_offset": base, "end_offset": end, "resumed_from": resumed_from, "policy": policy, "caps": caps,
            "chosen_mode": MODE_NAMES[best], "calibration": {MODE_NAMES[k]: v for k, v in (cal or {}).items()},
            "post_verify": verify, "rxt_final": {k: v for k, v in rxt.items() if k != "magic"}, "records": records}


def summarize(summary):
    """Phase totals from a send() summary, in seconds (host) and ticks/seconds (device)."""
    recs = summary.get("records") or []
    out = dict(chunks=len(recs))
    for k in ("host_sum_s", "begin_s", "write_s", "poll_s"):
        out[k] = round(sum(r.get(k, 0.0) for r in recs), 6)
    t = summary.get("rxt_final") or {}
    if t.get("freq"):
        f = float(t["freq"])
        for k in ("tot_arm", "tot_wire", "tot_sum", "tot_gap"):
            out[k + "_s"] = round(t[k] / f, 6)
    by_mode = {}
    for r in recs:
        if "write_s" in r:
            b = by_mode.setdefault(MODE_NAMES[r["mode"]], dict(n=0, bytes=0, write_s=0.0, poll_s=0.0))
            b["n"] += 1
            b["bytes"] += r["n"]
            b["write_s"] += r["write_s"]
            b["poll_s"] += r["poll_s"]
    for b in by_mode.values():
        b["wire_mb_s"] = round(b["bytes"] / b["write_s"] / 1e6, 3) if b["write_s"] else None
        b["chunk_mb_s"] = round(b["bytes"] / (b["write_s"] + b["poll_s"]) / 1e6, 3) if b["write_s"] + b["poll_s"] else None
    out["by_mode"] = by_mode
    return out


if __name__ == "__main__":
    sys.exit("use deliver130.py (the NAT-080 delivery companion with this sender)")
